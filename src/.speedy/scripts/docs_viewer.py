"""
docs_viewer.py — Kết xuất toàn bộ tài liệu Markdown trong `docs/` thành trang HTML đọc cục bộ.
- Hoạt động 100% offline, không gửi request ra internet và không vỡ nếu chưa có `mermaid.min.js`.
- Nếu có `.speedy/assets/mermaid.min.js` thì tự động kích hoạt vẽ biểu đồ SVG; nếu không vẫn hiển thị khối sơ đồ rõ đẹp.
- Chặn `javascript:` URL và escape toàn bộ nội dung HTML không an toàn.
"""

from __future__ import annotations

import html
import os
import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from contracts import ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope
from storage import atomic_write_bytes

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*```([^`]*)\s*$")
LIST_RE = re.compile(r"^\s*[-+*]\s+(.+)$")
ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^\s)]+)\)")
CODE_RE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True)
class DocsViewResult:
    status: str  # "created" | "updated" | "unchanged"
    path: Path
    files_rendered: int


def _slugify(text: str, seen: Dict[str, int]) -> str:
    base = re.sub(r"[^\w\- ]", "", text.lower(), flags=re.UNICODE)
    base = re.sub(r"[\s_]+", "-", base).strip("-") or "section"
    cnt = seen.get(base, 0)
    seen[base] = cnt + 1
    return base if cnt == 0 else f"{base}-{cnt + 1}"


def _safe_href(raw_url: str) -> str:
    parts = urlsplit(raw_url)
    if parts.scheme.lower() in {"javascript", "vbscript", "data"}:
        return "#"
    return html.escape(raw_url, quote=True)


def _render_inline(text: str) -> str:
    escaped = html.escape(text, quote=False)
    escaped = LINK_RE.sub(lambda m: f'<a href="{_safe_href(html.unescape(m.group(2)))}">{m.group(1)}</a>', escaped)
    escaped = CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _is_table_sep(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def _render_md_body(markdown: str, seen_ids: Dict[str, int]) -> Tuple[str, List[Tuple[int, str, str]]]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    headings: List[Tuple[int, str, str]] = []
    idx = 0

    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            lang = fence.group(1).strip().split()[0].lower() if fence.group(1).strip() else ""
            idx += 1
            buf: List[str] = []
            while idx < len(lines) and not FENCE_RE.match(lines[idx]):
                buf.append(lines[idx])
                idx += 1
            if idx < len(lines):
                idx += 1
            escaped_code = html.escape("\n".join(buf))
            if lang == "mermaid":
                out.append(f'<pre class="mermaid">{escaped_code}</pre>')
            else:
                cls = f' class="language-{html.escape(lang, quote=True)}"' if lang else ""
                out.append(f"<pre><code{cls}>{escaped_code}</code></pre>")
            continue

        hd = HEADING_RE.match(line)
        if hd:
            lvl = len(hd.group(1))
            title = hd.group(2)
            hid = _slugify(title, seen_ids)
            out.append(f'<h{lvl} id="{hid}">{_render_inline(title)}</h{lvl}>')
            headings.append((lvl, hid, title))
            idx += 1
            continue

        if "|" in line and idx + 1 < len(lines) and _is_table_sep(lines[idx + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            idx += 2
            rows: List[List[str]] = []
            while idx < len(lines) and "|" in lines[idx] and lines[idx].strip():
                rows.append([c.strip() for c in lines[idx].strip().strip("|").split("|")])
                idx += 1
            thead = "".join(f"<th>{_render_inline(h)}</th>" for h in headers)
            tbody = "".join("<tr>" + "".join(f"<td>{_render_inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f'<div class="tablewrap"><table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table></div>')
            continue

        ul = LIST_RE.match(line)
        ol = ORDERED_RE.match(line)
        if ul or ol:
            pat = LIST_RE if ul else ORDERED_RE
            tag = "ul" if ul else "ol"
            items: List[str] = []
            while idx < len(lines):
                m = pat.match(lines[idx])
                if not m:
                    break
                items.append(f"<li>{_render_inline(m.group(1))}</li>")
                idx += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith(">"):
            quotes: List[str] = []
            while idx < len(lines) and lines[idx].startswith(">"):
                quotes.append(_render_inline(lines[idx][1:].lstrip()))
                idx += 1
            out.append(f"<blockquote>{'<br>'.join(quotes)}</blockquote>")
            continue

        out.append(f"<p>{_render_inline(line.strip())}</p>")
        idx += 1

    return "\n".join(out), headings


def render_docs_site(
    layout: WorkspaceLayout,
    *,
    docs_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    open_browser: bool = False,
) -> DocsViewResult:
    target_docs = resolve_within_scope(layout.root, docs_dir) if docs_dir else layout.docs_dir
    if not target_docs.is_dir():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Thư mục tài liệu không tồn tại: {target_docs}", path=str(target_docs))

    out_file = (
        resolve_within_scope(layout.root, output_path)
        if output_path
        else (target_docs / "index.html")
    )

    md_files = sorted(
        [
            p
            for p in target_docs.rglob("*.md")
            if not any(part.startswith(".") for part in p.relative_to(target_docs).parts)
            and p.resolve() != out_file.resolve()
        ],
        key=lambda p: p.relative_to(target_docs).as_posix(),
    )

    seen_ids: Dict[str, int] = {}
    toc_items: List[str] = []
    sections: List[str] = []

    if not md_files:
        sections.append('<section class="doc"><p class="empty">Chưa có tài liệu Markdown nào trong thư mục này.</p></section>')
    else:
        for md in md_files:
            rel = md.relative_to(target_docs).as_posix()
            fid = _slugify(f"doc-{rel[:-3]}", seen_ids)
            body_html, headings = _render_md_body(md.read_text(encoding="utf-8", errors="replace"), seen_ids)
            sub_links = "".join(
                f'<a class="sublink" href="#{hid}">{html.escape(htext)}</a>'
                for lvl, hid, htext in headings
                if lvl == 2
            )
            toc_items.append(f'<div class="toc-group"><a class="toc-file" href="#{fid}">{html.escape(rel)}</a>{sub_links}</div>')
            sections.append(
                f'<article class="doc" id="{fid}"><div class="doc-meta">{html.escape(rel)}</div>{body_html}</article>'
            )

    mermaid_js = layout.speedy_dir / "assets" / "mermaid.min.js"
    mermaid_script = ""
    if mermaid_js.is_file():
        rel_asset = Path(os.path.relpath(str(mermaid_js), str(out_file.parent))).as_posix()
        mermaid_script = (
            f'<script src="{html.escape(rel_asset, quote=True)}"></script>'
            "<script>if(window.mermaid){mermaid.initialize({startOnLoad:true,securityLevel:'strict'});}</script>"
        )

    page = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speedy Docs Viewer</title>
<style>
:root {{ --bg:#0f1117; --surface:#171a23; --line:#272c3a; --fg:#e8eaf0; --muted:#949bb0; --accent:#10b981; --code:#1e2230; }}
@media (prefers-color-scheme: light) {{ :root {{ --bg:#f8fafc; --surface:#ffffff; --line:#e2e8f0; --fg:#0f172a; --muted:#64748b; --accent:#059669; --code:#f1f5f9; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); line-height:1.7; }}
.shell {{ max-width:1440px; margin:0 auto; display:grid; grid-template-columns:280px minmax(0,1fr); gap:32px; padding:0 24px; }}
nav {{ position:sticky; top:0; max-height:100vh; overflow:auto; padding:24px 0; border-right:1px solid var(--line); padding-right:16px; }}
.toc-file {{ display:block; font-weight:700; color:var(--fg); text-decoration:none; margin-top:10px; font-size:13px; }}
.sublink {{ display:block; padding-left:12px; color:var(--muted); text-decoration:none; font-size:12px; margin-top:3px; }}
.toc-file:hover, .sublink:hover {{ color:var(--accent); }}
main {{ padding:24px 0 96px; }}
.doc {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:24px 28px; margin-bottom:24px; }}
.doc-meta {{ font-size:12px; color:var(--accent); font-family:ui-monospace,monospace; margin-bottom:8px; }}
pre {{ background:var(--code); padding:14px; border-radius:8px; overflow:auto; border:1px solid var(--line); }}
code {{ background:var(--code); padding:2px 5px; border-radius:4px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:0.9em; }}
pre code {{ background:none; padding:0; }}
.tablewrap {{ overflow-x:auto; margin:12px 0; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ border:1px solid var(--line); padding:8px 10px; text-align:left; }}
blockquote {{ margin:12px 0; padding:8px 14px; border-left:3px solid var(--accent); color:var(--muted); }}
@media (max-width:900px) {{ .shell {{ grid-template-columns:1fr; }} nav {{ position:static; border-right:0; max-height:none; }} }}
</style>
</head>
<body>
<div class="shell">
  <nav><strong>TÀI LIỆU DỰ ÁN</strong>{"".join(toc_items)}</nav>
  <main>{"".join(sections)}</main>
</div>
{mermaid_script}
</body>
</html>
"""
    payload = page.encode("utf-8")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if not out_file.exists():
        atomic_write_bytes(out_file, payload)
        status = "created"
    elif out_file.read_bytes() == payload:
        status = "unchanged"
    else:
        atomic_write_bytes(out_file, payload)
        status = "updated"

    if open_browser:
        webbrowser.open(out_file.as_uri())

    return DocsViewResult(status=status, path=out_file, files_rendered=len(md_files))
