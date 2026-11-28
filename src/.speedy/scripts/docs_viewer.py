"""
docs_viewer.py — Kết xuất toàn bộ tài liệu Markdown trong `docs/` thành trang HTML đọc cục bộ.
- Giữ nguyên layout bản gốc Speedy: Sidebar cây thư mục/file có icon + IntersectionObserver active highlight,
  khối "ON THIS PAGE" cho từng tài liệu, và Modal phóng to/kéo thả sơ đồ Mermaid.
- Hoạt động 100% offline, không gửi request ra internet và không vỡ nếu chưa có `mermaid.min.js`.
- Chặn `javascript:` / `vbscript:` / `data:` URL và escape toàn bộ nội dung HTML không an toàn.
"""

from __future__ import annotations

import html
import os
import re
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

from contracts import ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope
from storage import atomic_write_bytes

HIDDEN_PARTS = {".git", ".pytest_cache", "__pycache__"}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*```([^`]*)\s*$")
LIST_RE = re.compile(r"^\s*([-+*])\s+(.+)$")
ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.+)$")
HR_RE = re.compile(r"\s{0,3}([-*_])(?:\s*\1){2,}\s*")
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^\s)]+)(?:\s+"[^"]*")?\)')
LINK_RE = re.compile(r'(?<!!)\[([^\]]+)\]\(([^\s)]+)(?:\s+"[^"]*")?\)')
CODE_RE = re.compile(r"`([^`]+)`")
HTML_COMMENT_RE = re.compile(r"^\s*<!--.*?-->\s*$")
TAGS_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:tags|keywords)(?:\*\*)?\s*:\s*(.+)$", re.IGNORECASE)
SOURCE_REF_LINE_RE = re.compile(
    r"^\s*[-*]\s*`?source_ref`?\s*:\s*`?([^|`\n]+)`?\s*\|\s*`?sha256`?\s*:\s*`?([a-fA-F0-9]{8,64})`?\s*$",
    re.IGNORECASE,
)

_DIR_PRIORITY = {
    "guides": 1,
    "architecture": 2,
    "development-rules": 3,
    "development-style": 4,
    "reference": 5,
    "cross-repo": 6,
}


def _human_sort_key(rel_posix: str) -> Tuple[int, int, str]:
    low = rel_posix.lower()
    if low == "index.md":
        return (0, 0, low)
    if low in {"architecture/overview.md", "overview.md", "readme.md"}:
        return (0, 1, low)
    if low == "guides/quickstart.md":
        return (1, 0, low)
    if low.startswith("guides/"):
        return (1, 1, low)
    if low == "architecture/architecture.md":
        return (2, 0, low)
    if low.startswith("architecture/"):
        return (2, 1, low)
    if low.startswith("development-rules/"):
        return (3, 0, low)
    if low.startswith("development-style/"):
        return (4, 0, low)
    if low.startswith("reference/"):
        return (5, 0, low)
    if low.startswith("cross-repo/"):
        return (6, 0, low)
    if low == "changelog.md":
        return (9, 0, low)
    return (7, 0, low)

FOLDER_ICON = (
    '<svg class="toc-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>'
    "</svg>"
)
FILE_ICON = (
    '<svg class="toc-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>'
    '<polyline points="14 2 14 8 20 8"></polyline>'
    "</svg>"
)


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


def _safe_url(
    raw_url: str,
    source_dir: Path,
    output_dir: Path,
    doc_id_map: Optional[Dict[Path, str]] = None,
) -> str:
    parts = urlsplit(raw_url)
    if parts.scheme.lower() in {"javascript", "vbscript", "data"}:
        return "#"
    if parts.scheme or raw_url.startswith(("#", "/", "//")):
        return html.escape(raw_url, quote=True)
    target = (source_dir / parts.path).resolve()
    if doc_id_map and target in doc_id_map:
        return f"#{doc_id_map[target]}"
    relative = Path(os.path.relpath(str(target), str(output_dir))).as_posix()
    return html.escape(urlunsplit(("", "", relative, parts.query, parts.fragment)), quote=True)


def _render_inline(
    text: str,
    source_dir: Path,
    output_dir: Path,
    doc_id_map: Optional[Dict[Path, str]] = None,
) -> str:
    escaped = html.escape(text, quote=False)

    def _image(match: re.Match) -> str:
        url = _safe_url(html.unescape(match.group(2)), source_dir, output_dir, doc_id_map)
        return f'<img src="{url}" alt="{match.group(1)}">'

    def _link(match: re.Match) -> str:
        url = _safe_url(html.unescape(match.group(2)), source_dir, output_dir, doc_id_map)
        return f'<a href="{url}">{match.group(1)}</a>'

    escaped = IMAGE_RE.sub(_image, escaped)
    escaped = LINK_RE.sub(_link, escaped)
    escaped = CODE_RE.sub(r"<code>\1</code>", escaped)
    escaped = re.sub(
        r"\*\*(.+?)\*\*|__(.+?)__",
        lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>",
        escaped,
    )
    escaped = re.sub(
        r"(?<!\*)\*([^*]+)\*|(?<!_)_([^_]+)_",
        lambda m: f"<em>{m.group(1) or m.group(2)}</em>",
        escaped,
    )
    return escaped


def _table_cells(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_table_sep(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def _is_block_start(lines: List[str], idx: int) -> bool:
    line = lines[idx]
    return bool(
        HEADING_RE.match(line)
        or FENCE_RE.match(line)
        or LIST_RE.match(line)
        or ORDERED_RE.match(line)
        or line.startswith(">")
        or HR_RE.fullmatch(line)
        or ("|" in line and idx + 1 < len(lines) and _is_table_sep(lines[idx + 1]))
    )


def _render_md_body(
    markdown: str,
    source_dir: Path,
    output_dir: Path,
    seen_ids: Dict[str, int],
    doc_id_map: Optional[Dict[Path, str]] = None,
) -> Tuple[str, List[Tuple[int, str, str]], List[str], List[Tuple[str, str]]]:
    raw_lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: List[str] = []
    tags: List[str] = []
    source_refs: List[Tuple[str, str]] = []
    in_fence = False
    for line_idx, raw_line in enumerate(raw_lines):
        if FENCE_RE.match(raw_line):
            in_fence = not in_fence
            lines.append(raw_line)
            continue
        if not in_fence:
            if HTML_COMMENT_RE.match(raw_line):
                continue
            sr_m = SOURCE_REF_LINE_RE.match(raw_line)
            if sr_m:
                source_refs.append((sr_m.group(1).strip(), sr_m.group(2).strip()))
                continue
            if line_idx < 15:
                tg_m = TAGS_LINE_RE.match(raw_line)
                if tg_m:
                    for part in re.split(r"[,;|]+", tg_m.group(1)):
                        cleaned = part.strip().strip("`*_")
                        if cleaned and cleaned not in tags:
                            tags.append(cleaned)
                    continue
        lines.append(raw_line)

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
            out.append(f'<h{lvl} id="{hid}">{_render_inline(title, source_dir, output_dir, doc_id_map)}</h{lvl}>')
            headings.append((lvl, hid, title))
            idx += 1
            continue

        if HR_RE.fullmatch(line):
            out.append("<hr>")
            idx += 1
            continue

        if "|" in line and idx + 1 < len(lines) and _is_table_sep(lines[idx + 1]):
            headers = _table_cells(line)
            idx += 2
            rows: List[List[str]] = []
            while idx < len(lines) and "|" in lines[idx] and lines[idx].strip():
                rows.append(_table_cells(lines[idx]))
                idx += 1
            thead = "".join(f"<th>{_render_inline(h, source_dir, output_dir, doc_id_map)}</th>" for h in headers)
            tbody = "".join(
                "<tr>" + "".join(f"<td>{_render_inline(c, source_dir, output_dir, doc_id_map)}</td>" for c in r) + "</tr>"
                for r in rows
            )
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
                item_text = m.group(2) if tag == "ul" else m.group(1)
                items.append(f"<li>{_render_inline(item_text, source_dir, output_dir, doc_id_map)}</li>")
                idx += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith(">"):
            quotes: List[str] = []
            while idx < len(lines) and lines[idx].startswith(">"):
                quotes.append(_render_inline(lines[idx][1:].lstrip(), source_dir, output_dir, doc_id_map))
                idx += 1
            out.append(f"<blockquote><p>{'<br>'.join(quotes)}</p></blockquote>")
            continue

        paragraph = [line.strip()]
        idx += 1
        while idx < len(lines) and lines[idx].strip() and not _is_block_start(lines, idx):
            paragraph.append(lines[idx].strip())
            idx += 1
        out.append(f"<p>{_render_inline(' '.join(paragraph), source_dir, output_dir, doc_id_map)}</p>")

    return "\n".join(out), headings, tags, source_refs


def _render_document(
    doc_path: Path,
    docs_dir: Path,
    output_dir: Path,
    seen_ids: Dict[str, int],
    file_id: str,
    doc_id_map: Dict[Path, str],
) -> Tuple[str, List[Tuple[int, str, str]], List[str]]:
    rel = doc_path.relative_to(docs_dir).as_posix()
    body, headings, tags, source_refs = _render_md_body(
        doc_path.read_text(encoding="utf-8", errors="replace"),
        doc_path.parent,
        output_dir,
        seen_ids,
        doc_id_map,
    )
    title_formatted = html.escape(rel[:-3].upper().replace("/", " / "))

    tags_html = ""
    if tags:
        pills = "".join(f'<span class="doc-tag">{html.escape(t)}</span>' for t in tags[:10])
        tags_html = f'<div class="doc-tags">{pills}</div>'

    toc_links: List[str] = []
    for lvl, hid, htext in headings:
        if lvl >= 2:
            lvl_cls = f"level-{lvl}" if lvl <= 4 else "level-4"
            toc_links.append(f'<a href="#{hid}" class="doc-toc-link {lvl_cls}">{html.escape(htext)}</a>')

    doc_toc_html = ""
    if toc_links:
        doc_toc_html = (
            '<div class="doc-toc">'
            '<div class="doc-toc-title">ON THIS PAGE</div>'
            f'<div class="doc-toc-links">{"".join(toc_links)}</div>'
            "</div>"
        )

    refs_html = ""
    if source_refs:
        ref_items = "".join(
            f"<li><code>{html.escape(src)}</code> <span>({html.escape(sha)})</span></li>"
            for src, sha in source_refs
        )
        refs_html = (
            '<details class="source-refs">'
            f"<summary>📎 Nguồn mã đối chiếu ({len(source_refs)})</summary>"
            f"<ul>{ref_items}</ul>"
            "</details>"
        )

    header_html = (
        '<div class="doc-header">'
        f'<p class="meta">{html.escape(rel)}</p>'
        f'<h1 id="{file_id}">{title_formatted}</h1>'
        f"{tags_html}{doc_toc_html}"
        "</div>"
    )
    return f'<section class="document">{header_html}{body}{refs_html}</section>', headings, tags


def _build_toc_html(doc_infos: List[Dict[str, Any]]) -> str:
    root_node: Dict[str, Any] = {"dirs": {}, "files": []}
    for info in doc_infos:
        parts = Path(info["relative_path"]).parts
        curr = root_node
        for dir_name in parts[:-1]:
            if dir_name not in curr["dirs"]:
                curr["dirs"][dir_name] = {"dirs": {}, "files": []}
            curr = curr["dirs"][dir_name]
        curr["files"].append(info)

    def _render_node(node: Dict[str, Any]) -> str:
        parts_html: List[str] = []
        # Root-level priority files (e.g., INDEX.md) before subfolders, CHANGELOG.md after
        top_files = [i for i in node["files"] if i["relative_path"].lower() != "changelog.md"]
        tail_files = [i for i in node["files"] if i["relative_path"].lower() == "changelog.md"]

        def _render_file(info: Dict[str, Any]) -> str:
            file_name = info["relative_path"].split("/")[-1]
            file_title = html.escape(file_name[:-3] if file_name.endswith(".md") else file_name)
            file_id = info["file_id"]
            search_blob = " ".join(
                [
                    info["relative_path"],
                    info.get("title", ""),
                    " ".join(h[2] for h in info.get("headings", [])),
                    " ".join(info.get("tags", [])),
                ]
            ).lower()
            return (
                f'<div class="toc-file" data-search="{html.escape(search_blob, quote=True)}">'
                f'<a href="#{file_id}" class="toc-file-link">{FILE_ICON}<span>{file_title}</span></a>'
                "</div>"
            )

        for info in top_files:
            parts_html.append(_render_file(info))

        for dir_name, sub_node in sorted(
            node["dirs"].items(),
            key=lambda kv: (_DIR_PRIORITY.get(kv[0].lower(), 7), kv[0].lower()),
        ):
            content_html = _render_node(sub_node)
            parts_html.append(
                '<details class="toc-folder" open>'
                f"<summary>{FOLDER_ICON}<span>{html.escape(dir_name)}</span></summary>"
                f'<div class="toc-folder-content">{content_html}</div>'
                "</details>"
            )

        for info in tail_files:
            parts_html.append(_render_file(info))

        return "".join(parts_html)

    return _render_node(root_node)


TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Workspace documentation</title>
<style>
:root { --bg:#fcfcfd; --fg:#17181c; --muted:#6f7683; --line:#e8e9ee; --accent:#06c755; --accent-ink:#058a44; --code-bg:#f1f2f6; --code-fg:#b3306b; --surface:#ffffff; }
@media (prefers-color-scheme: dark) { :root { --bg:#0f1013; --fg:#e9eaee; --muted:#989fac; --line:#24262d; --accent-ink:#41d98a; --code-bg:#1b1d24; --code-fg:#ff8fb3; --surface:#14161b; } }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--fg); font-size:15px; line-height:1.85; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,sans-serif; }
.shell { max-width:1500px; margin:0 auto; padding:0 32px; display:grid; grid-template-columns:250px minmax(0,1fr); gap:40px; }
nav.toc { position:sticky; top:0; align-self:start; max-height:100vh; overflow:auto; padding:28px 0; font-size:13px; }
nav.toc p { color:var(--muted); font-weight:700; letter-spacing:.08em; margin:0 0 12px; }
nav.toc summary { cursor:pointer; font-weight:600; color:var(--fg); padding:5px 8px; user-select:none; border-radius:4px; margin:2px 0; display:flex; align-items:center; gap:6px; font-size:13px; list-style:none; }
nav.toc summary::-webkit-details-marker { display:none; }
nav.toc summary:hover { color:var(--accent-ink); background:var(--surface); }
.toc-folder-content { padding-left:10px; border-left:1px solid var(--line); margin-left:6px; margin-bottom:4px; }
.toc-file { margin:2px 0; }
.toc-file-link { display:flex; align-items:center; gap:6px; padding:5px 8px; color:var(--muted); text-decoration:none; border-left:2px solid transparent; border-radius:0 4px 4px 0; font-size:13px; text-overflow:ellipsis; overflow:hidden; white-space:nowrap; }
.toc-file-link:hover { color:var(--fg); background:var(--surface); }
.toc-file-link.on { color:var(--accent-ink); border-left-color:var(--accent); font-weight:700; background:var(--surface); }
.toc-icon { opacity:0.7; flex-shrink:0; }
.toc-search { width:100%; padding:6px 10px; margin:0 0 12px; border:1px solid var(--line); border-radius:6px; background:var(--surface); color:var(--fg); font-size:12px; outline:none; }
.toc-search:focus { border-color:var(--accent); }
.doc-tags { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 12px; }
.doc-tag { background:var(--code-bg); color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:1px 9px; font-size:11px; font-weight:600; }
.source-refs { margin-top:24px; background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:8px 14px; font-size:12px; color:var(--muted); }
.source-refs summary { cursor:pointer; font-weight:600; user-select:none; }
.source-refs ul { margin:8px 0 4px; padding-left:18px; }
.source-refs li { margin:2px 0; }
.doc-header { margin-bottom:32px; padding-bottom:16px; border-bottom:1px solid var(--line); }
.doc-header h1 { font-size:24px; font-weight:800; letter-spacing:.03em; margin:4px 0 16px; color:var(--fg); }
.doc-toc { background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:12px 16px; margin:16px 0 4px; }
.doc-toc-title { font-size:11px; font-weight:700; color:var(--muted); letter-spacing:.08em; text-transform:uppercase; margin:0 0 8px; }
.doc-toc-links { display:flex; flex-direction:column; gap:4px; }
.doc-toc-link { color:var(--accent-ink); text-decoration:none; font-size:13px; font-weight:500; }
.doc-toc-link:hover { text-decoration:underline; }
.doc-toc-link.level-3 { padding-left:14px; }
.doc-toc-link.level-4 { padding-left:28px; }
pre.mermaid { background:var(--surface); border:1px solid var(--line); color:var(--fg); cursor:pointer; position:relative; transition:border-color 0.2s; border-radius:8px; padding:16px; overflow:auto; }
pre.mermaid:hover { border-color:var(--accent); }
.mermaid-zoom-btn { position:absolute; top:8px; right:8px; z-index:10; background:var(--surface); color:var(--muted); border:1px solid var(--line); padding:4px 8px; border-radius:4px; font-size:12px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:4px; opacity:0.7; transition:opacity 0.2s, color 0.2s; }
pre.mermaid:hover .mermaid-zoom-btn, .mermaid-zoom-btn:hover { opacity:1; color:var(--accent-ink); border-color:var(--accent); }
.mermaid-modal { display:none; position:fixed; inset:0; z-index:1000; background:rgba(0,0,0,0.7); backdrop-filter:blur(8px); align-items:center; justify-content:center; flex-direction:column; }
.mermaid-modal.active { display:flex; }
.mermaid-modal-header { position:absolute; top:16px; right:16px; display:flex; gap:8px; z-index:1001; }
.mermaid-modal-btn { background:var(--surface); color:var(--fg); border:1px solid var(--line); border-radius:6px; padding:8px 12px; font-size:13px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px; user-select:none; box-shadow:0 4px 12px rgba(0,0,0,0.2); }
.mermaid-modal-btn:hover { background:var(--code-bg); color:var(--accent-ink); border-color:var(--accent); }
.mermaid-modal-body { width:94vw; height:90vh; overflow:hidden; display:flex; align-items:center; justify-content:center; cursor:grab; user-select:none; }
.mermaid-modal-body:active { cursor:grabbing; }
.mermaid-modal-body svg { max-width:none !important; max-height:none !important; background:var(--surface); color:var(--fg); padding:24px; border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,0.3); transition:transform 0.05s ease-out; transform-origin:center center; }
main { padding:28px 0 120px; min-width:0 }
section.document { margin-bottom:56px; }
h1 { font-size:26px; margin:8px 0 4px; letter-spacing:.01em }
h2 { font-size:20px; margin:44px 0 12px; padding-bottom:8px; border-bottom:2px solid var(--line) }
h3 { font-size:16px; margin:28px 0 8px }
h4 { font-size:14px; margin:20px 0 6px; color:var(--muted) }
p, li { overflow-wrap:anywhere }
a { color:var(--accent-ink) }
img { max-width:100%; height:auto; border-radius:8px; border:1px solid var(--line); }
code { background:var(--code-bg); color:var(--code-fg); padding:1px 5px; border-radius:4px; font-size:.9em; font-family:ui-monospace,SFMono-Regular,Menlo,monospace }
pre { background:var(--code-bg); padding:14px 16px; border-radius:8px; overflow:auto }
pre code { background:none; color:inherit; padding:0 }
blockquote { margin:12px 0; padding:6px 16px; border-left:3px solid var(--line); color:var(--muted) }
hr { border:0; border-top:1px solid var(--line); margin:32px 0 }
.tablewrap { overflow-x:auto; margin:14px 0; border:1px solid var(--line); border-radius:8px }
table { border-collapse:collapse; width:100%; font-size:13px; background:var(--surface) }
th, td { border-bottom:1px solid var(--line); padding:9px 12px; text-align:left; vertical-align:top }
th { background:var(--code-bg); font-weight:700; white-space:nowrap }
tbody tr:last-child td { border-bottom:0 }
.meta { color:var(--muted); font-size:13px; margin:0 0 8px }
.empty { color:var(--muted); padding:24px; background:var(--surface); border:1px solid var(--line); border-radius:8px; }
@media (max-width:900px) { .shell { grid-template-columns:1fr } nav.toc { display:none } }
@media print { nav.toc { display:none } .shell { display:block } .tablewrap { break-inside:avoid } }
</style>
</head>
<body>
<div class="shell">
  <nav class="toc" aria-label="Table of contents"><p>CONTENTS</p><input type="search" class="toc-search" id="toc-search" placeholder="Lọc tài liệu / từ khóa..." aria-label="Lọc tài liệu">{toc}</nav>
  <main>{content}</main>
</div>
<div class="mermaid-modal" id="mermaid-modal">
  <div class="mermaid-modal-header">
    <button class="mermaid-modal-btn" id="mm-zoom-in" title="Zoom In">➕ Zoom In</button>
    <button class="mermaid-modal-btn" id="mm-zoom-out" title="Zoom Out">➖ Zoom Out</button>
    <button class="mermaid-modal-btn" id="mm-reset" title="Reset">🔄 Reset</button>
    <button class="mermaid-modal-btn" id="mm-close" title="Close (ESC)">✖ Đóng</button>
  </div>
  <div class="mermaid-modal-body" id="mermaid-modal-body"></div>
</div>
<script>
const links = [...document.querySelectorAll('nav.toc a')];
const byId = new Map(links.map(a => [a.getAttribute('href').slice(1), a]));
const io = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    links.forEach(link => link.classList.remove('on'));
    const link = byId.get(entry.target.id);
    if (link) {
      link.classList.add('on');
      let parent = link.closest('details');
      while (parent) {
        parent.open = true;
        parent = parent.parentElement ? parent.parentElement.closest('details') : null;
      }
    }
  }
}, { rootMargin: '0px 0px -75% 0px' });
document.querySelectorAll('main h1[id]').forEach(target => io.observe(target));
const searchInput = document.getElementById('toc-search');
if (searchInput) {
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim().toLowerCase();
    document.querySelectorAll('.toc-file').forEach(el => {
      const hay = el.dataset.search || '';
      el.style.display = (!q || hay.includes(q)) ? '' : 'none';
    });
    document.querySelectorAll('.toc-folder').forEach(folder => {
      const visible = [...folder.querySelectorAll('.toc-file')].some(el => el.style.display !== 'none');
      folder.style.display = (!q || visible) ? '' : 'none';
      if (q && visible) folder.open = true;
    });
  });
}
</script>
{mermaid_block}
</body>
</html>
"""

MERMAID_INTERACTIVE_SCRIPT = """<script src="{mermaid_asset}"></script>
<script type="module">
if (window.mermaid) {
  const isDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: isDark ? 'dark' : 'default' });
  await mermaid.run({ querySelector: 'pre.mermaid' });

  const modal = document.getElementById('mermaid-modal');
  const modalBody = document.getElementById('mermaid-modal-body');
  let currentSvg = null;
  let scale = 1, panX = 0, panY = 0, isDragging = false, startX = 0, startY = 0;

  function updateTransform() {
    if (currentSvg) currentSvg.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
  }
  function resetZoom() { scale = 1; panX = 0; panY = 0; updateTransform(); }
  function openModal(svgElement) {
    modalBody.innerHTML = '';
    currentSvg = svgElement.cloneNode(true);
    currentSvg.style.width = 'auto';
    currentSvg.style.height = 'auto';
    modalBody.appendChild(currentSvg);
    resetZoom();
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  function closeModal() {
    modal.classList.remove('active');
    modalBody.innerHTML = '';
    currentSvg = null;
    document.body.style.overflow = '';
  }

  document.querySelectorAll('pre.mermaid').forEach(pre => {
    const btn = document.createElement('button');
    btn.className = 'mermaid-zoom-btn';
    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line><line x1="11" y1="8" x2="11" y2="14"></line><line x1="8" y1="11" x2="14" y2="11"></line></svg> 🔍 Phóng to';
    pre.appendChild(btn);
    pre.addEventListener('click', () => {
      const svg = pre.querySelector('svg');
      if (svg) openModal(svg);
    });
  });

  document.getElementById('mm-zoom-in').addEventListener('click', e => { e.stopPropagation(); scale *= 1.25; updateTransform(); });
  document.getElementById('mm-zoom-out').addEventListener('click', e => { e.stopPropagation(); scale = Math.max(0.2, scale / 1.25); updateTransform(); });
  document.getElementById('mm-reset').addEventListener('click', e => { e.stopPropagation(); resetZoom(); });
  document.getElementById('mm-close').addEventListener('click', closeModal);
  modal.addEventListener('click', e => { if (e.target === modal || e.target === modalBody) closeModal(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal.classList.contains('active')) closeModal(); });
  modalBody.addEventListener('wheel', e => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 1.15 : 0.85;
    scale = Math.min(Math.max(0.2, scale * delta), 8);
    updateTransform();
  }, { passive: false });
  modalBody.addEventListener('mousedown', e => {
    if (e.button !== 0) return;
    isDragging = true; startX = e.clientX - panX; startY = e.clientY - panY;
  });
  window.addEventListener('mousemove', e => {
    if (!isDragging) return;
    panX = e.clientX - startX; panY = e.clientY - startY; updateTransform();
  });
  window.addEventListener('mouseup', () => { isDragging = false; });
}
</script>"""


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
            if not any(part in HIDDEN_PARTS or part.startswith(".") for part in p.relative_to(target_docs).parts)
            and p.resolve() != out_file.resolve()
        ],
        key=lambda p: _human_sort_key(p.relative_to(target_docs).as_posix()),
    )

    seen_ids: Dict[str, int] = {}
    doc_id_map: Dict[Path, str] = {}
    file_ids: List[str] = []
    for md in md_files:
        rel = md.relative_to(target_docs).as_posix()
        fid = _slugify(f"file-{rel[:-3].replace('/', '-')}", seen_ids)
        doc_id_map[md.resolve()] = fid
        file_ids.append(fid)

    doc_infos: List[Dict[str, Any]] = []
    sections: List[str] = []

    if not md_files:
        sections.append('<section class="document"><p class="empty">Chưa có tài liệu Markdown nào trong thư mục này.</p></section>')
        toc_html = '<p class="empty">Chưa có mục lục.</p>'
    else:
        for md, fid in zip(md_files, file_ids):
            rendered, headings, tags = _render_document(md, target_docs, out_file.parent, seen_ids, fid, doc_id_map)
            sections.append(rendered)
            rel = md.relative_to(target_docs).as_posix()
            doc_infos.append(
                {
                    "relative_path": rel,
                    "file_id": fid,
                    "title": rel[:-3],
                    "headings": headings,
                    "tags": tags,
                }
            )
        toc_html = _build_toc_html(doc_infos)

    mermaid_js = layout.speedy_dir / "assets" / "mermaid.min.js"
    mermaid_block = ""
    if mermaid_js.is_file():
        rel_asset = Path(os.path.relpath(str(mermaid_js), str(out_file.parent))).as_posix()
        mermaid_block = MERMAID_INTERACTIVE_SCRIPT.replace("{mermaid_asset}", html.escape(rel_asset, quote=True))

    page = (
        TEMPLATE.replace("{toc}", toc_html)
        .replace("{content}", "\n".join(sections))
        .replace("{mermaid_block}", mermaid_block)
    )
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
