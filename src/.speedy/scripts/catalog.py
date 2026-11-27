"""
catalog.py — Sinh chỉ mục nhẹ (compact index) cho các thành phần của Speedy & Antigravity skills.
Lưu ý bất biến: Catalog chỉ là index định danh file, KHÔNG PHẢI bằng chứng behavioral verification.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List

from contracts import WorkspaceLayout
from storage import atomic_write_json, read_json_safe


def _extract_summary(md_file: Path) -> str:
    try:
        text = md_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm:
        desc_match = re.search(r"description\s*:\s*[>-]?\s*\n?(.+)", fm.group(1))
        if desc_match:
            return desc_match.group(1).strip().strip('"').strip("'")[:140]

    sec = re.search(r"##\s+(?:Mô tả|Description|Vai trò)\s*\n(.*?)(?:\n##|\Z)", text, re.DOTALL)
    if sec:
        for line in sec.group(1).splitlines():
            if line.strip():
                return line.strip()[:140]

    for line in text.splitlines():
        clean = line.strip()
        if clean and not clean.startswith(("#", "---", ">")):
            return clean[:140]
    return ""


def _scan_md_folder(folder: Path) -> List[Dict[str, str]]:
    if not folder.is_dir():
        return []
    out: List[Dict[str, str]] = []
    for f in sorted(folder.glob("*.md")):
        out.append({"name": f.stem, "file": f.name, "description": _extract_summary(f)})
    return out


def _scan_antigravity_skills(skills_root: Path) -> List[Dict[str, str]]:
    if not skills_root.is_dir():
        return []
    out: List[Dict[str, str]] = []
    for skill_dir in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            out.append(
                {
                    "name": skill_dir.name,
                    "file": f"{skill_dir.name}/SKILL.md",
                    "description": _extract_summary(skill_md),
                }
            )
    return out


def build_catalog(layout: WorkspaceLayout, *, use_cache: bool = True) -> Dict[str, Any]:
    speedy = layout.speedy_dir
    agents_root = (layout.root / "src" / ".agents") if layout.kind == "builder" else (layout.root / ".agents")

    commands_dir = speedy / "commands"
    flows_dir = speedy / "flows"
    roles_dir = speedy / "roles"
    rules_dir = speedy / "rules"
    skills_dir = agents_root / "skills"
    agy_rules_dir = agents_root / "rules"

    tracked_files: List[Path] = []
    for d in (commands_dir, flows_dir, roles_dir, rules_dir, agy_rules_dir):
        if d.is_dir():
            tracked_files.extend(sorted(d.glob("*.md")))
    if skills_dir.is_dir():
        tracked_files.extend(sorted(skills_dir.glob("*/SKILL.md")))

    digest = hashlib.sha256()
    for f in tracked_files:
        try:
            st = f.stat()
            digest.update(f"{f}:{st.st_size}:{int(st.st_mtime_ns)}\n".encode("utf-8"))
        except OSError:
            continue
    checksum = digest.hexdigest()[:16]

    cache_path = layout.state_dir / "catalog_cache.json"
    if use_cache and cache_path.is_file():
        try:
            cached = read_json_safe(cache_path)
            if cached.get("checksum") == checksum:
                cached["cached"] = True
                return cached
        except Exception:
            pass

    commands = _scan_md_folder(commands_dir)
    flows = _scan_md_folder(flows_dir)
    roles = _scan_md_folder(roles_dir)
    rules = _scan_md_folder(rules_dir)
    antigravity_skills = _scan_antigravity_skills(skills_dir)
    antigravity_rules = _scan_md_folder(agy_rules_dir)

    result: Dict[str, Any] = {
        "is_behavioral_verification": False,
        "note": "Catalog chỉ xác nhận chỉ mục cấu hình tĩnh, không thay thế kiểm thử thực thi.",
        "checksum": checksum,
        "cached": False,
        "count": {
            "commands": len(commands),
            "flows": len(flows),
            "roles": len(roles),
            "rules": len(rules),
            "antigravity_skills": len(antigravity_skills),
            "antigravity_rules": len(antigravity_rules),
        },
        "commands": commands,
        "flows": flows,
        "roles": roles,
        "rules": rules,
        "antigravity_skills": antigravity_skills,
        "antigravity_rules": antigravity_rules,
    }
    if use_cache:
        try:
            atomic_write_json(cache_path, result)
        except OSError:
            pass
    return result
