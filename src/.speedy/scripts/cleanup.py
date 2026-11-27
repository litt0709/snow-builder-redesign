"""
cleanup.py — Dọn dẹp an toàn các artifact cũ:
- Mặc định chạy `dry_run=True` để hiển thị danh sách sẽ xóa trước khi người dùng xác nhận.
- Bảo vệ tuyệt đối: các session đang ở trạng thái `in_progress`, `awaiting_approval`, `running`, `blocked`,
  cùng thư mục `state/` và `docs/`.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from contracts import SessionStatus, WorkspaceLayout
from storage import read_json_safe

SAFE_TERMINAL_SESSION_STATUSES = {
    SessionStatus.COMPLETED.value,
    SessionStatus.ABORTED.value,
}


def _is_older_than_days(name_or_mtime_path: Path, cutoff_date: datetime) -> bool:
    prefix = name_or_mtime_path.name[:10]
    try:
        dt = datetime.strptime(prefix, "%Y-%m-%d")
        return dt <= cutoff_date
    except ValueError:
        try:
            mtime_dt = datetime.fromtimestamp(name_or_mtime_path.stat().st_mtime)
            return mtime_dt <= cutoff_date
        except OSError:
            return False


def run_cleanup(
    layout: WorkspaceLayout,
    *,
    older_than_days: int = 30,
    include_plans: bool = False,
    include_logs: bool = False,
    include_reports: bool = False,
    include_audit: bool = False,
    apply: bool = False,
) -> Dict[str, Any]:
    cutoff = datetime.now() - timedelta(days=max(0, int(older_than_days)))
    candidates: Dict[str, List[str]] = {
        "sessions": [],
        "tmp": [],
        "plans": [],
        "logs": [],
        "reports": [],
        "audit": [],
    }
    protected_sessions: List[str] = []
    removable_sids: List[str] = []

    if layout.sessions_dir.is_dir():
        for sdir in sorted(p for p in layout.sessions_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
            sjson = sdir / "state.json"
            status = "unknown"
            if sjson.is_file():
                try:
                    status = str(read_json_safe(sjson).get("status", "unknown"))
                except Exception:
                    status = "corrupted"
            if status not in SAFE_TERMINAL_SESSION_STATUSES:
                protected_sessions.append(sdir.relative_to(layout.root).as_posix())
                continue
            if _is_older_than_days(sdir, cutoff):
                candidates["sessions"].append(sdir.relative_to(layout.root).as_posix())
                removable_sids.append(sdir.name)

    if layout.tmp_dir.is_dir():
        for item in sorted(layout.tmp_dir.iterdir()):
            if item.name == ".gitkeep":
                continue
            candidates["tmp"].append(item.relative_to(layout.root).as_posix())

    if include_plans and layout.plans_dir.is_dir() and removable_sids:
        for pfile in sorted(layout.plans_dir.glob("*.md")):
            txt = pfile.read_text(encoding="utf-8", errors="ignore")
            if any(sid in txt for sid in removable_sids) and _is_older_than_days(pfile, cutoff):
                candidates["plans"].append(pfile.relative_to(layout.root).as_posix())

    if include_logs and layout.logs_dir.is_dir():
        for lfile in sorted(layout.logs_dir.rglob("*")):
            if layout.audit_dir in lfile.parents:
                continue
            if lfile.is_file() and lfile.name != ".gitkeep" and _is_older_than_days(lfile, cutoff):
                candidates["logs"].append(lfile.relative_to(layout.root).as_posix())

    if include_reports and layout.reports_dir.is_dir():
        for rfile in sorted(layout.reports_dir.rglob("*")):
            if rfile.is_file() and rfile.name != ".gitkeep" and _is_older_than_days(rfile, cutoff):
                candidates["reports"].append(rfile.relative_to(layout.root).as_posix())

    if include_audit and layout.audit_dir.is_dir():
        for adir in sorted(p for p in layout.audit_dir.iterdir() if p.is_dir()):
            if any(sid in adir.name for sid in removable_sids) or _is_older_than_days(adir, cutoff):
                # Không xóa audit của session đang active
                if not any(Path(ps).name in adir.name for ps in protected_sessions):
                    candidates["audit"].append(adir.relative_to(layout.root).as_posix())

    deleted: List[str] = []
    if apply:
        for group in candidates.values():
            for rel_target in group:
                abs_target = (layout.root / rel_target).resolve()
                if abs_target.is_dir():
                    shutil.rmtree(abs_target)
                    deleted.append(rel_target)
                elif abs_target.is_file():
                    abs_target.unlink()
                    deleted.append(rel_target)

    total_candidates = sum(len(v) for v in candidates.values())
    return {
        "dry_run": not apply,
        "older_than_days": older_than_days,
        "total_candidates": total_candidates,
        "candidates": candidates,
        "protected_active_sessions": protected_sessions,
        "deleted_count": len(deleted),
        "deleted": deleted,
    }
