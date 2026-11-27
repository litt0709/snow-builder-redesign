"""
repomap.py — Bản đồ repository cấp module để định vị nhanh WHERE (code nằm ở đâu).
Chỉ trả về metadata (tên module, đường dẫn, ngôn ngữ, tối đa 3 entry points, link docs liên quan),
không nhồi nhét nội dung mã nguồn hay toàn bộ symbol index vào context window.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import WorkspaceLayout, resolve_within_scope
from scan import ENTRY_POINT_NAMES, IGNORE_DIRS, LANG_EXT_MAP
from storage import atomic_write_json, read_json_safe

CONTAINER_DIR_HINTS = {"module", "modules", "packages", "services", "apps", "libs", "components"}
MAX_ENTRY_POINTS = 3
DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def _split_tokens(text: str) -> List[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text or "")
    return [tok for tok in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if tok]


def _iter_module_dirs(root: Path) -> List[Path]:
    modules: List[Path] = []
    try:
        level1 = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return modules

    for directory in level1:
        if directory.name in IGNORE_DIRS or directory.name.startswith("."):
            continue
        if directory.name.lower() in CONTAINER_DIR_HINTS:
            children = sorted(
                child
                for child in directory.iterdir()
                if child.is_dir() and child.name not in IGNORE_DIRS and not child.name.startswith(".")
            )
            if children:
                modules.extend(children)
                continue
        modules.append(directory)
    return modules


def _walk_module(module_dir: Path, root: Path) -> Dict[str, Any]:
    file_count = 0
    languages: Dict[str, int] = {}
    entry_points: List[str] = []

    for dirpath, dirnames, filenames in os.walk(module_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if filename == ".gitkeep" or filename == ".DS_Store":
                continue
            file_count += 1
            lang = LANG_EXT_MAP.get(Path(filename).suffix.lower())
            if lang:
                languages[lang] = languages.get(lang, 0) + 1
            if filename in ENTRY_POINT_NAMES and len(entry_points) < MAX_ENTRY_POINTS:
                entry_points.append((Path(dirpath) / filename).relative_to(root).as_posix())

    ranked = sorted(languages, key=lambda k: languages[k], reverse=True)
    return {"files": file_count, "languages": ranked[:3], "entry_points": entry_points}


def _collect_docs(layout: WorkspaceLayout, root: Path) -> List[str]:
    docs_dir = layout.docs_dir if root == layout.root else (root / "ai-workspace" / "docs")
    if not docs_dir.is_dir():
        return []
    docs: List[str] = []
    for path in sorted(docs_dir.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(docs_dir).parts):
            continue
        try:
            docs.append(path.relative_to(root).as_posix())
        except ValueError:
            docs.append(path.as_posix())
    return docs


def _match_docs(module_name: str, docs: List[str]) -> List[str]:
    tokens = set(_split_tokens(module_name))
    if not tokens:
        return []
    exact, partial = [], []
    for doc in docs:
        doc_tokens = set(_split_tokens(Path(doc).stem))
        if doc_tokens == tokens:
            exact.append(doc)
        elif tokens <= doc_tokens:
            partial.append(doc)
    return (exact or partial)[:3]


def _structure_checksum(root: Path, modules: List[Path], docs: List[str]) -> str:
    digest = hashlib.sha256()
    for module_dir in modules:
        for dirpath, dirnames, filenames in os.walk(module_dir):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
            visible = [f for f in sorted(filenames) if f not in {".gitkeep", ".DS_Store"}]
            try:
                mt = int(os.stat(dirpath).st_mtime_ns)
            except OSError:
                mt = 0
            digest.update(f"{dirpath}:{mt}:{','.join(visible)}\n".encode("utf-8"))
    digest.update(("|".join(docs)).encode("utf-8"))
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

    module_dirs = _iter_module_dirs(root)
    docs = _collect_docs(layout, root)
    checksum = _structure_checksum(root, module_dirs, docs)

    if use_cache and target.is_file():
        try:
            cached = read_json_safe(target)
            if cached.get("checksum") == checksum and cached.get("root") == str(root):
                cached["cached"] = True
                return cached
        except Exception:
            pass

    modules: List[Dict[str, Any]] = []
    total_files = 0
    for mdir in module_dirs:
        stats = _walk_module(mdir, root)
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
                "docs": _match_docs(rel_name, docs),
            }
        )

    modules.sort(key=lambda item: item["name"])
    payload: Dict[str, Any] = {
        "root": str(root),
        "index_path": target.relative_to(layout.root).as_posix(),
        "checksum": checksum,
        "cached": False,
        "count": {"modules": len(modules), "files": total_files},
        "modules": modules,
    }
    try:
        atomic_write_json(target, payload)
    except OSError:
        pass
    return payload


def _score_module(module: Dict[str, Any], tokens: List[str]) -> int:
    name_tokens = set(_split_tokens(module["name"]))
    path_tokens = set(_split_tokens(module["path"]))
    doc_tokens = set()
    for d in module.get("docs", []):
        doc_tokens |= set(_split_tokens(Path(d).stem))
    entry_tokens = set()
    for ep in module.get("entry_points", []):
        entry_tokens |= set(_split_tokens(ep))

    score = 0
    for token in tokens:
        if token in name_tokens:
            score += 5
        elif any(token in cand for cand in name_tokens):
            score += 3
        if token in path_tokens:
            score += 2
        if token in doc_tokens:
            score += 2
        if token in entry_tokens:
            score += 1
    return score


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
    tokens = _split_tokens(keyword)

    scored = []
    for mod in index.get("modules", []):
        sc = _score_module(mod, tokens) if tokens else 0
        if sc > 0:
            scored.append((sc, mod))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
    if scored and len(tokens) >= 2 and scored[0][0] >= 8:
        min_keep_score = scored[0][0] * 0.55
        scored = [pair for pair in scored if pair[0] >= min_keep_score]
    matches = [
        {
            "name": mod["name"],
            "path": mod["path"],
            "score": sc,
            "files": mod["files"],
            "languages": mod["languages"],
            "entry_points": mod["entry_points"],
            "docs": mod["docs"],
        }
        for sc, mod in scored[:bounded_limit]
    ]

    hint = (
        "Đọc docs liên quan trước (WHAT); sau đó tìm kiếm mã nguồn giới hạn trong các path trên."
        if matches
        else "Không tìm thấy module khớp từ khóa. Thử từ khóa ngắn hơn hoặc chạy scan để kiểm tra cấu trúc dự án."
    )
    return {
        "query": keyword,
        "limit": bounded_limit,
        "total_matches": len(scored),
        "truncated": len(scored) > bounded_limit,
        "count": len(matches),
        "matches": matches,
        "hint": hint,
    }
