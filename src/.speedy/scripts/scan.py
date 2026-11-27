"""
scan.py — Inventory dự án: phát hiện ngôn ngữ, framework, entry points, file cấu hình
và bộ công cụ lint/type/test/build có sẵn (không tự bịa lệnh nếu dự án không khai báo).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import WorkspaceLayout, resolve_within_scope
from storage import atomic_write_json, compute_workspace_snapshot, read_json_safe

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".speedy",
    "ai-workspace",
    ".agents",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".cache",
    ".pytest_cache",
}

LANG_EXT_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".swift": "swift",
    ".kt": "kotlin",
}

CONFIG_LANG_MAP = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "package.json": "javascript",
    "tsconfig.json": "typescript",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java",
    "build.gradle": "java",
    "Gemfile": "ruby",
    "composer.json": "php",
}

FRAMEWORK_INDICATORS = {
    "django": "django",
    "fastapi": "fastapi",
    "flask": "flask",
    "next": "nextjs",
    "react": "react",
    "vue": "vue",
    "nuxt": "nuxt",
    "express": "express",
    "nestjs": "nestjs",
    "svelte": "svelte",
    "spring-boot": "spring-boot",
    "quarkus": "quarkus",
    "gin-gonic": "gin",
    "labstack/echo": "echo",
}

ENTRY_POINT_NAMES = {
    "main.py",
    "app.py",
    "server.py",
    "run.py",
    "manage.py",
    "index.ts",
    "index.js",
    "server.ts",
    "server.js",
    "app.ts",
    "App.tsx",
    "App.jsx",
    "main.ts",
    "main.go",
    "main.rs",
    "Main.java",
    "index.php",
}


def _detect_tooling(root: Path, lang: str) -> Dict[str, Optional[List[str]]]:
    """Phát hiện lệnh test/lint/type/build thực sự có căn cứ trong manifest của dự án."""
    detected: Dict[str, Optional[List[str]]] = {
        "lint": None,
        "typecheck": None,
        "test": None,
        "build": None,
    }

    pkg_json = root / "package.json"
    if pkg_json.is_file():
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
            if "lint" in scripts:
                detected["lint"] = ["npm", "run", "lint"]
            if "typecheck" in scripts:
                detected["typecheck"] = ["npm", "run", "typecheck"]
            if "test" in scripts and "no test specified" not in str(scripts["test"]).lower():
                detected["test"] = ["npm", "test"]
            if "build" in scripts:
                detected["build"] = ["npm", "run", "build"]
        except Exception:
            pass

    if lang == "python":
        if detected["test"] is None and ((root / "tests").is_dir() or (root / "test").is_dir()):
            test_dir = "tests" if (root / "tests").is_dir() else "test"
            detected["test"] = ["python3", "-m", "unittest", "discover", "-s", test_dir]
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            content = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            if "[tool.ruff" in content and detected["lint"] is None:
                detected["lint"] = ["python3", "-m", "ruff", "check", "."]
            if "[tool.mypy" in content and detected["typecheck"] is None:
                detected["typecheck"] = ["python3", "-m", "mypy", "."]
    elif lang == "go" and (root / "go.mod").is_file():
        detected["test"] = detected["test"] or ["go", "test", "./..."]
        detected["build"] = detected["build"] or ["go", "build", "./..."]
    elif lang == "rust" and (root / "Cargo.toml").is_file():
        detected["test"] = detected["test"] or ["cargo", "test"]
        detected["build"] = detected["build"] or ["cargo", "check"]

    return detected


def _detect_framework(root: Path) -> str:
    for fname in ("package.json", "pyproject.toml", "requirements.txt", "go.mod", "pom.xml", "build.gradle"):
        fpath = root / fname
        if not fpath.is_file():
            continue
        try:
            raw = fpath.read_text(encoding="utf-8", errors="ignore").lower()
            for indicator, fw in FRAMEWORK_INDICATORS.items():
                if indicator in raw:
                    return fw
        except OSError:
            continue
    return "none"


def scan_project(
    layout: WorkspaceLayout,
    target_path: str = ".",
    *,
    sid: Optional[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    root = resolve_within_scope(layout.root, target_path)
    snapshot = compute_workspace_snapshot(root)
    cache_path = layout.state_dir / "scan_cache.json"

    if use_cache and cache_path.is_file():
        try:
            cached = read_json_safe(cache_path)
            if cached.get("snapshot_id") == snapshot["snapshot_id"] and cached.get("root") == str(root):
                cached["cached"] = True
                return cached
        except Exception:
            pass

    ext_counter: Counter[str] = Counter()
    entry_points: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for fname in sorted(filenames):
            ext = Path(fname).suffix.lower()
            if ext in LANG_EXT_MAP:
                ext_counter[ext] += 1
            if fname in ENTRY_POINT_NAMES and len(entry_points) < 10:
                entry_points.append((Path(dirpath) / fname).relative_to(root).as_posix())

    lang = "unknown"
    if (root / "tsconfig.json").is_file():
        lang = "typescript"
    else:
        for cfg_name, cfg_lang in CONFIG_LANG_MAP.items():
            if (root / cfg_name).is_file():
                lang = cfg_lang
                break
    if lang == "unknown" and ext_counter:
        lang = LANG_EXT_MAP.get(ext_counter.most_common(1)[0][0], "unknown")

    key_files = [
        name
        for name in (*CONFIG_LANG_MAP.keys(), "README.md", "AGENTS.md", ".env.example", "Makefile", "Dockerfile")
        if (root / name).exists()
    ]

    result: Dict[str, Any] = {
        "root": str(root),
        "snapshot_id": snapshot["snapshot_id"],
        "lang": lang,
        "languages_breakdown": {LANG_EXT_MAP[k]: v for k, v in ext_counter.most_common(5)},
        "framework": _detect_framework(root),
        "entry_points": entry_points,
        "key_files": key_files,
        "detected_tooling": _detect_tooling(root, lang),
        "files_counted": snapshot["files_counted"],
        "sid": sid or "",
        "cached": False,
    }

    if use_cache:
        try:
            atomic_write_json(cache_path, result)
        except OSError:
            pass
    return result
