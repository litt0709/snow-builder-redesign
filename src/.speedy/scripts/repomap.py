"""
repomap.py — Unified Harness Index (RepoMap + Docs Knowledge Index) để định vị siêu nhanh WHERE & WHAT.
- 100% Python stdlib, chỉ lưu metadata gọn nhẹ (module, key_files, public symbols, docs_index),
  không nhồi nội dung mã nguồn vào context window.
- Hỗ trợ nhận diện đa tầng (src/, app/, web/src/, functions/src/, services/, packages/...),
  truy vấn hợp nhất cả code lẫn tài liệu và tự động sinh Master Map `docs/INDEX.md`.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from contracts import WorkspaceLayout, resolve_within_scope
from scan import ENTRY_POINT_NAMES, IGNORE_DIRS, LANG_EXT_MAP
from storage import atomic_write_json, atomic_write_text, read_json_safe

CONTAINER_DIR_HINTS = {
    "src",
    "app",
    "apps",
    "web",
    "frontend",
    "client",
    "backend",
    "server",
    "api",
    "functions",
    "module",
    "modules",
    "packages",
    "services",
    "libs",
    "lib",
    "pkg",
    "cmd",
    "internal",
    "core",
    "components",
}
NESTED_SRC_HINTS = {"src", "app", "lib", "internal", "pkg"}
EXTRA_SKIP_DIRS = {".turbo", ".vite", "out"}

MAX_ENTRY_POINTS = 3
MAX_KEY_FILES = 10
MAX_SYMBOLS = 15
MAX_DOC_HEADINGS = 8
MAX_DOC_KEYWORDS = 14
MAX_SYMBOL_SCAN_BYTES = 16384
MAX_FILE_SIZE_FOR_SYMBOLS = 512 * 1024
DEFAULT_LIMIT = 5
MAX_LIMIT = 20

_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "your",
    "are",
    "was",
    "not",
    "all",
    "can",
    "use",
    "using",
    "cua",
    "cac",
    "cho",
    "voi",
    "trong",
    "nhu",
    "khi",
    "sau",
    "truoc",
    "tong",
    "quan",
    "muc",
    "tieu",
}

_PY_SYM_RE = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z][A-Za-z0-9_]{2,})\b", re.MULTILINE)
_JS_SYM_RE = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function|class|interface|type|const)\s+([A-Za-z][A-Za-z0-9_]{2,})\b",
    re.MULTILINE,
)
_GENERIC_SYM_RE = re.compile(
    r"^(?:pub\s+|public\s+|protected\s+)?(?:async\s+)?(?:func|fn|struct|enum|trait|class|interface)\s+(?:\([^)]*\)\s+)?([A-Za-z][A-Za-z0-9_]{2,})\b",
    re.MULTILINE,
)
_H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$", re.MULTILINE)
_TAGS_RE = re.compile(r"(?i)(?:tags|keywords)\s*:\s*([^\n]+)")
_SOURCE_REF_RE = re.compile(r"source_ref`?\s*:", re.IGNORECASE)
_ACTIVE_SPEC_LINE_RE = re.compile(r"Active\s+Spec[^:\n]*:\s*`?([^\s`|\n()\[\]]+\.md)`?", re.IGNORECASE)


def _split_tokens(text: str) -> List[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text or "")
    return [tok for tok in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if len(tok) >= 2]


def _is_ignored_dir(name: str) -> bool:
    return name in IGNORE_DIRS or name in EXTRA_SKIP_DIRS or name.startswith(".")


def _has_direct_code_files(directory: Path) -> bool:
    try:
        for entry in directory.iterdir():
            if entry.is_file() and entry.suffix.lower() in LANG_EXT_MAP:
                return True
    except OSError:
        return False
    return False


def _list_child_dirs(directory: Path) -> List[Path]:
    try:
        return sorted(p for p in directory.iterdir() if p.is_dir() and not _is_ignored_dir(p.name))
    except OSError:
        return []


def _iter_module_specs(root: Path) -> List[Tuple[Path, bool]]:
    """
    Trả về danh sách `(module_dir, shallow_only)`:
    - Unwrap tối đa 2 cấp container phổ biến (vd: `web/src/pages`, `functions/src/subsonic`).
    - Nếu thư mục container có file mã nguồn trực tiếp bên cạnh thư mục con, tách riêng mục `(dir, True)`
      để không bị bỏ sót file gốc lẫn không đếm trùng file trong thư mục con.
    """
    specs: List[Tuple[Path, bool]] = []
    for d1 in _list_child_dirs(root):
        if d1.name.lower() not in CONTAINER_DIR_HINTS:
            specs.append((d1, False))
            continue

        children = _list_child_dirs(d1)
        if not children:
            specs.append((d1, False))
            continue

        if _has_direct_code_files(d1):
            specs.append((d1, True))

        for d2 in children:
            if d2.name.lower() in NESTED_SRC_HINTS:
                grandchildren = _list_child_dirs(d2)
                if grandchildren:
                    if _has_direct_code_files(d2):
                        specs.append((d2, True))
                    for d3 in grandchildren:
                        specs.append((d3, False))
                    continue
            specs.append((d2, False))

    return specs


def _extract_symbols(path: Path) -> List[str]:
    ext = path.suffix.lower()
    if ext not in LANG_EXT_MAP:
        return []
    name_low = path.name.lower()
    if name_low.endswith((".min.js", ".min.css", ".bundle.js", ".d.ts", ".map")):
        return []
    try:
        if path.stat().st_size > MAX_FILE_SIZE_FOR_SYMBOLS:
            return []
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            head = fh.read(MAX_SYMBOL_SCAN_BYTES)
    except OSError:
        return []

    if ext == ".py":
        found = _PY_SYM_RE.findall(head)
    elif ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        found = _JS_SYM_RE.findall(head)
    else:
        found = _GENERIC_SYM_RE.findall(head)

    out: List[str] = []
    seen = set()
    for sym in found:
        if sym.startswith("_") or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= 6:
            break
    return out


def _walk_module(module_dir: Path, root: Path, *, shallow_only: bool = False) -> Dict[str, Any]:
    file_count = 0
    languages: Dict[str, int] = {}
    entry_points: List[str] = []
    non_test_files: List[str] = []
    test_files: List[str] = []
    symbols: List[str] = []
    seen_syms = set()

    def _process_file(fpath: Path) -> None:
        nonlocal file_count
        fname = fpath.name
        if fname in {".gitkeep", ".DS_Store"}:
            return
        file_count += 1
        lang = LANG_EXT_MAP.get(fpath.suffix.lower())
        if lang:
            languages[lang] = languages.get(lang, 0) + 1
            if "test" in fname.lower() or "spec" in fname.lower():
                if len(test_files) < MAX_KEY_FILES:
                    test_files.append(fname)
            else:
                if len(non_test_files) < MAX_KEY_FILES:
                    non_test_files.append(fname)
            if len(symbols) < MAX_SYMBOLS:
                for sym in _extract_symbols(fpath):
                    if sym not in seen_syms:
                        seen_syms.add(sym)
                        symbols.append(sym)
                        if len(symbols) >= MAX_SYMBOLS:
                            break
        if fname in ENTRY_POINT_NAMES and len(entry_points) < MAX_ENTRY_POINTS:
            entry_points.append(fpath.relative_to(root).as_posix())

    if shallow_only:
        try:
            for entry in sorted(module_dir.iterdir()):
                if entry.is_file():
                    _process_file(entry)
        except OSError:
            pass
    else:
        for dirpath, dirnames, filenames in os.walk(module_dir):
            dirnames[:] = sorted(d for d in dirnames if not _is_ignored_dir(d))
            base = Path(dirpath)
            for fname in sorted(filenames):
                _process_file(base / fname)

    ranked_langs = sorted(languages, key=lambda k: languages[k], reverse=True)
    key_files = (non_test_files + test_files)[:MAX_KEY_FILES]
    return {
        "files": file_count,
        "languages": ranked_langs[:3],
        "entry_points": entry_points,
        "key_files": key_files,
        "symbols": symbols,
    }


def _strip_md(text: str) -> str:
    cleaned = re.sub(r"[`*_~]", "", text or "")
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _doc_category(rel_under_docs: Path) -> str:
    if len(rel_under_docs.parts) <= 1:
        return "general"
    top = rel_under_docs.parts[0].lower()
    mapping = {
        "architecture": "architecture",
        "guides": "guides",
        "reference": "reference",
        "development-rules": "rules",
        "development-style": "style",
        "cross-repo": "cross-repo",
    }
    return mapping.get(top, top)


def _build_docs_index(layout: WorkspaceLayout, root: Path) -> List[Dict[str, Any]]:
    docs_dir = layout.docs_dir if root == layout.root else (root / "ai-workspace" / "docs")
    if not docs_dir.is_dir():
        return []

    entries: List[Dict[str, Any]] = []
    for md_path in sorted(docs_dir.rglob("*.md")):
        rel_docs = md_path.relative_to(docs_dir)
        if any(part.startswith(".") for part in rel_docs.parts):
            continue
        if rel_docs.as_posix() == "INDEX.md":
            continue
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel_root = md_path.relative_to(root).as_posix()
        except ValueError:
            rel_root = md_path.as_posix()

        h1_m = _H1_RE.search(text)
        title = _strip_md(h1_m.group(1)) if h1_m else md_path.stem
        headings = [_strip_md(h) for h in _H2_RE.findall(text)[:MAX_DOC_HEADINGS]]
        source_refs = len(_SOURCE_REF_RE.findall(text))

        kw_pool: List[str] = []
        kw_pool.extend(_split_tokens(md_path.stem))
        kw_pool.extend(_split_tokens(title))
        for h in headings:
            kw_pool.extend(_split_tokens(h))
        for tag_line in _TAGS_RE.findall(text[:1024]):
            kw_pool.extend(_split_tokens(tag_line))

        keywords: List[str] = []
        seen_kw = set()
        for tok in kw_pool:
            if tok in _STOP_WORDS or tok in seen_kw:
                continue
            seen_kw.add(tok)
            keywords.append(tok)
            if len(keywords) >= MAX_DOC_KEYWORDS:
                break

        entries.append(
            {
                "path": rel_root,
                "category": _doc_category(rel_docs),
                "title": title[:120],
                "headings": headings,
                "keywords": keywords,
                "lines": text.count("\n") + 1,
                "source_refs": source_refs,
            }
        )
    return entries


def _match_docs(module_name: str, key_files: List[str], docs_index: List[Dict[str, Any]]) -> List[str]:
    mod_tokens = set(_split_tokens(module_name))
    file_tokens = set()
    for kf in key_files[:5]:
        file_tokens |= set(_split_tokens(Path(kf).stem))
    if not mod_tokens:
        return []

    scored: List[Tuple[int, str]] = []
    for doc in docs_index:
        doc_path = doc["path"]
        stem_tokens = set(_split_tokens(Path(doc_path).stem))
        kw_tokens = set(doc.get("keywords") or [])
        sc = 0
        if stem_tokens == mod_tokens:
            sc += 10
        elif mod_tokens <= stem_tokens:
            sc += 6
        overlap_mod = mod_tokens & kw_tokens
        overlap_files = file_tokens & kw_tokens
        sc += len(overlap_mod) * 3 + len(overlap_files) * 2
        if sc >= 4:
            scored.append((sc, doc_path))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [p for _, p in scored[:3]]


def _structure_checksum(root: Path, module_specs: List[Tuple[Path, bool]], docs_dir: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"harness-v2\n")

    def _hash_file_entry(fpath: Path) -> None:
        if fpath.name in {".gitkeep", ".DS_Store"}:
            return
        if fpath.suffix.lower() in LANG_EXT_MAP:
            try:
                st = fpath.stat()
                digest.update(f"F:{fpath}:{int(st.st_mtime_ns)}:{st.st_size}\n".encode("utf-8"))
            except OSError:
                digest.update(f"F:{fpath}:0:0\n".encode("utf-8"))
        else:
            digest.update(f"N:{fpath.name}\n".encode("utf-8"))

    for module_dir, shallow_only in module_specs:
        if shallow_only:
            try:
                mt = int(os.stat(module_dir).st_mtime_ns)
                entries = sorted(p for p in module_dir.iterdir() if p.is_file())
            except OSError:
                mt, entries = 0, []
            digest.update(f"S:{module_dir}:{mt}\n".encode("utf-8"))
            for fpath in entries:
                _hash_file_entry(fpath)
        else:
            for dirpath, dirnames, filenames in os.walk(module_dir):
                dirnames[:] = sorted(d for d in dirnames if not _is_ignored_dir(d))
                try:
                    mt = int(os.stat(dirpath).st_mtime_ns)
                except OSError:
                    mt = 0
                digest.update(f"D:{dirpath}:{mt}\n".encode("utf-8"))
                base = Path(dirpath)
                for fname in sorted(filenames):
                    _hash_file_entry(base / fname)
    if docs_dir.is_dir():
        for md_path in sorted(docs_dir.rglob("*.md")):
            rel_docs = md_path.relative_to(docs_dir)
            if any(part.startswith(".") for part in rel_docs.parts) or rel_docs.as_posix() == "INDEX.md":
                continue
            try:
                st = md_path.stat()
                digest.update(f"DOC:{rel_docs.as_posix()}:{int(st.st_mtime_ns)}:{st.st_size}\n".encode("utf-8"))
            except OSError:
                continue
    return digest.hexdigest()[:16]


def build_repomap(
    layout: WorkspaceLayout,
    root_dir: str = ".",
    *,
    out_path: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    root = resolve_within_scope(layout.root, root_dir)
    target = resolve_within_scope(layout.root, out_path) if out_path else (layout.state_dir / "repomap.json")
    docs_dir = layout.docs_dir if root == layout.root else (root / "ai-workspace" / "docs")

    module_specs = _iter_module_specs(root)
    checksum = _structure_checksum(root, module_specs, docs_dir)

    if use_cache and target.is_file():
        try:
            cached = read_json_safe(target)
            if cached.get("checksum") == checksum and cached.get("root") == str(root) and cached.get("schema_version") == 2:
                cached["cached"] = True
                return cached
        except Exception:
            pass

    docs_index = _build_docs_index(layout, root)
    modules: List[Dict[str, Any]] = []
    total_files = 0
    for mdir, shallow_only in module_specs:
        stats = _walk_module(mdir, root, shallow_only=shallow_only)
        if stats["files"] == 0:
            continue
        rel_name = mdir.relative_to(root).as_posix()
        total_files += stats["files"]
        modules.append(
            {
                "name": rel_name,
                "path": rel_name,
                "files": stats["files"],
                "languages": stats["languages"],
                "entry_points": stats["entry_points"],
                "key_files": stats["key_files"],
                "symbols": stats["symbols"],
                "docs": _match_docs(rel_name, stats["key_files"], docs_index),
            }
        )

    modules.sort(key=lambda item: item["name"])
    payload: Dict[str, Any] = {
        "schema_version": 2,
        "root": str(root),
        "index_path": target.relative_to(layout.root).as_posix(),
        "checksum": checksum,
        "cached": False,
        "count": {"modules": len(modules), "files": total_files, "docs": len(docs_index)},
        "modules": modules,
        "docs_index": docs_index,
    }
    try:
        atomic_write_json(target, payload)
    except OSError:
        pass
    return payload


def _score_module(module: Dict[str, Any], tokens: List[str]) -> Tuple[int, List[str], List[str]]:
    name_tokens = set(_split_tokens(module["name"]))
    path_tokens = set(_split_tokens(module["path"]))
    doc_tokens = set()
    for d in module.get("docs", []):
        doc_tokens |= set(_split_tokens(Path(d).stem))
    entry_tokens = set()
    for ep in module.get("entry_points", []):
        entry_tokens |= set(_split_tokens(ep))

    matched_files: List[str] = []
    matched_symbols: List[str] = []
    score = 0

    for token in tokens:
        if token in name_tokens:
            score += 6
        elif any(token in cand for cand in name_tokens):
            score += 3
        if token in path_tokens:
            score += 2
        if token in doc_tokens:
            score += 2
        if token in entry_tokens:
            score += 1

        for kf in module.get("key_files", []):
            kf_stem = Path(kf).stem
            kf_toks = _split_tokens(kf_stem)
            if token in kf_toks:
                score += 4
                if kf not in matched_files:
                    matched_files.append(kf)
            elif len(token) >= 4 and (token in kf_stem.lower() or any(token in kt for kt in kf_toks)):
                score += 2
                if kf not in matched_files:
                    matched_files.append(kf)

        for sym in module.get("symbols", []):
            sym_toks = _split_tokens(sym)
            if token in sym_toks:
                score += 4
                if sym not in matched_symbols:
                    matched_symbols.append(sym)
            elif len(token) >= 4 and (token in sym.lower() or any(token in st for st in sym_toks)):
                score += 2
                if sym not in matched_symbols:
                    matched_symbols.append(sym)

    return score, matched_files[:5], matched_symbols[:6]


def _score_doc(doc: Dict[str, Any], tokens: List[str]) -> Tuple[int, List[str]]:
    title_raw = doc.get("title", "")
    title_low = title_raw.lower()
    title_toks = set(_split_tokens(title_raw))
    path_toks = set(_split_tokens(doc.get("path", "")))
    kw_toks = set(doc.get("keywords") or [])
    matched_headings: List[str] = []
    score = 0

    for token in tokens:
        if token in title_toks:
            score += 6
        elif token in title_low or any(token in t for t in title_toks):
            score += 3
        if token in kw_toks:
            score += 3
        elif any(token in k for k in kw_toks):
            score += 1
        if token in path_toks:
            score += 2
        for h in doc.get("headings", []):
            h_toks = _split_tokens(h)
            if token in h_toks or token in h.lower() or any(token in ht for ht in h_toks):
                score += 3
                if h not in matched_headings:
                    matched_headings.append(h)

    return score, matched_headings[:4]


def query_repomap(
    layout: WorkspaceLayout,
    keyword: str,
    *,
    root_dir: str = ".",
    limit: int = DEFAULT_LIMIT,
    out_path: Optional[str] = None,
) -> Dict[str, Any]:
    bounded_limit = max(1, min(int(limit), MAX_LIMIT))
    index = build_repomap(layout, root_dir=root_dir, out_path=out_path, use_cache=True)
    tokens = [t for t in _split_tokens(keyword) if t not in _STOP_WORDS] or _split_tokens(keyword)

    scored_mods: List[Tuple[int, Dict[str, Any], List[str], List[str]]] = []
    for mod in index.get("modules", []):
        if not tokens:
            continue
        sc, m_files, m_syms = _score_module(mod, tokens)
        if sc > 0:
            scored_mods.append((sc, mod, m_files, m_syms))

    scored_mods.sort(key=lambda item: (-item[0], item[1]["name"]))
    if scored_mods and scored_mods[0][0] >= 6:
        min_keep = scored_mods[0][0] * 0.6
        scored_mods = [item for item in scored_mods if item[0] >= min_keep]

    matches = [
        {
            "name": mod["name"],
            "path": mod["path"],
            "score": sc,
            "files": mod["files"],
            "languages": mod["languages"],
            "entry_points": mod["entry_points"],
            "matched_files": m_files or mod.get("key_files", [])[:3],
            "matched_symbols": m_syms,
            "docs": mod["docs"],
        }
        for sc, mod, m_files, m_syms in scored_mods[:bounded_limit]
    ]

    scored_docs: List[Tuple[int, Dict[str, Any], List[str]]] = []
    for doc in index.get("docs_index", []):
        if not tokens:
            continue
        dsc, m_heads = _score_doc(doc, tokens)
        if dsc > 0:
            scored_docs.append((dsc, doc, m_heads))
    scored_docs.sort(key=lambda item: (-item[0], item[1]["path"]))
    doc_matches = [
        {
            "path": doc["path"],
            "title": doc["title"],
            "category": doc["category"],
            "score": dsc,
            "matched_headings": m_heads,
            "lines": doc["lines"],
        }
        for dsc, doc, m_heads in scored_docs[:bounded_limit]
    ]

    hint = (
        "Đọc doc_matches trước (WHAT); sau đó mở trực tiếp matched_files / matched_symbols trong các path trên (WHERE)."
        if (matches or doc_matches)
        else "Không tìm thấy module hoặc tài liệu khớp từ khóa. Thử từ khóa ngắn hơn hoặc chạy `knowledge index`."
    )
    return {
        "query": keyword,
        "limit": bounded_limit,
        "total_matches": len(scored_mods),
        "truncated": len(scored_mods) > bounded_limit,
        "count": len(matches),
        "matches": matches,
        "doc_matches": doc_matches,
        "hint": hint,
    }


def generate_docs_index_md(layout: WorkspaceLayout, root_dir: str = ".") -> Dict[str, Any]:
    """
    Đồng bộ `repomap.json` (Unified Harness Index) và sinh file Master Knowledge Map `docs/INDEX.md` (< 80 dòng)
    để cả con người lẫn LLM nắm toàn cảnh dự án trong 1 lần đọc.
    """
    repomap = build_repomap(layout, root_dir=root_dir, use_cache=False)
    docs_dir = layout.docs_dir
    docs_dir.mkdir(parents=True, exist_ok=True)
    index_md = docs_dir / "INDEX.md"

    # Kiểm tra Active Spec (nếu có)
    active_spec_line = "_Chưa có spec trong `specs/`_"
    spec_index = layout.runtime_root / "specs" / "INDEX.md"
    if spec_index.is_file():
        spec_txt = spec_index.read_text(encoding="utf-8", errors="replace")
        m = _ACTIVE_SPEC_LINE_RE.search(spec_txt)
        if m:
            active_spec_line = f"`{m.group(1)}` (xem `specs/INDEX.md`)"

    docs_index = repomap.get("docs_index", [])
    modules = repomap.get("modules", [])

    lines = [
        "# Knowledge Base Index (Master Map)",
        "",
        "<!-- auto-generated by speedy knowledge index -->",
        f"- **Active Spec**: {active_spec_line}",
        f"- **Indexed**: `{len(docs_index)}` tài liệu · `{len(modules)}` modules · `{repomap['count']['files']}` files (`{repomap['index_path']}`)",
        "- **Truy vấn nhanh cho LLM**: `python3 -B .speedy/scripts/speedy_cli.py knowledge query \"<từ khóa>\"`",
        "",
        "## 1. Bản Đồ Tài Liệu (WHAT)",
        "",
    ]

    if not docs_index:
        lines.append("_Chưa có tài liệu Markdown nào trong `docs/`. Chạy `/docs` hoặc hoàn tất `/flow` để khởi tạo._")
    else:
        docs_rel = docs_dir.relative_to(layout.root)
        lines.extend(["| Nhóm | Tài liệu | Tiêu đề | Dòng |", "|---|---|---|---:|"])
        for doc in docs_index[:30]:
            try:
                rel_link = Path(doc["path"]).relative_to(docs_rel).as_posix()
            except ValueError:
                rel_link = doc["path"]
            safe_title = str(doc["title"]).replace("|", "\\|")
            lines.append(f"| `{doc['category']}` | [{rel_link}]({rel_link}) | {safe_title} | {doc['lines']} |")

    lines.extend(["", "## 2. Bản Đồ Module Mã Nguồn (WHERE)", ""])
    if not modules:
        lines.append("_Chưa phát hiện module mã nguồn nào._")
    else:
        lines.extend(["| Module (`path`) | Files | Ngôn ngữ | Key Files / Entry |", "|---|---:|---|---|"])
        for mod in modules[:25]:
            langs = ", ".join(mod.get("languages") or []) or "-"
            kf = ", ".join(f"`{f}`" for f in (mod.get("key_files") or [])[:3]) or "-"
            lines.append(f"| `{mod['path']}` | {mod['files']} | {langs} | {kf} |")
        if len(modules) > 25:
            lines.append(f"\n_...và {len(modules) - 25} module khác (dùng `repomap query` để tìm nhanh)._")

    content = "\n".join(lines).rstrip() + "\n"
    if not index_md.exists():
        atomic_write_text(index_md, content)
        status = "created"
    elif index_md.read_text(encoding="utf-8", errors="replace") == content:
        status = "unchanged"
    else:
        atomic_write_text(index_md, content)
        status = "updated"

    return {
        "status": status,
        "index_md_path": index_md.relative_to(layout.root).as_posix(),
        "repomap_path": repomap["index_path"],
        "docs_count": len(docs_index),
        "modules_count": len(modules),
        "files_count": repomap["count"]["files"],
    }
