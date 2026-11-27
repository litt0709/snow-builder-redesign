"""
storage.py — Lưu trữ bền vững: ghi JSON atomic, session lock chống xung đột đồng thời,
compare-and-swap (CAS) trên state_revision, semantic checksum cho artifact, snapshot mã nguồn,
side-effect checkpoint và sinh tự động state.md từ canonical state.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Optional

from contracts import (
    STAGE_LABELS,
    ErrorCode,
    SpeedyError,
    StageStatus,
    WorkspaceLayout,
    validate_sid,
)

_IGNORE_SNAPSHOT_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    "dist",
    "build",
    "target",
    ".speedy",
    "ai-workspace",
    ".agents",
    "sessions",
    "logs",
    "reports",
    "tmp",
}

_VOLATILE_MD_LINE_RE = re.compile(
    r"^\s*[-*]\s*\*\*(Updated At|Date|Timestamp|Generated At)\*\*\s*:",
    re.IGNORECASE,
)

_STATUS_ICONS = {
    StageStatus.APPROVED.value: "✅",
    StageStatus.RUNNING.value: "🔄",
    StageStatus.AWAITING_APPROVAL.value: "⏸️",
    StageStatus.PENDING.value: "⏳",
    StageStatus.FAILED.value: "❌",
    StageStatus.BLOCKED.value: "🚫",
    StageStatus.ABORTED.value: "🛑",
    StageStatus.SKIPPED.value: "⏭️",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Ghi file nguyên tử bằng temp file cùng thư mục + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(str(tmp_path), 0o644)
        except OSError:
            pass
        os.replace(str(tmp_path), str(path))
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, rendered)


def read_json_safe(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Không tìm thấy file JSON: {path}", path=str(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SpeedyError(
            ErrorCode.CONTRACT_VIOLATION,
            f"File JSON bị hỏng cấu trúc: {path} ({exc})",
            path=str(path),
        ) from exc
    if not isinstance(data, dict):
        raise SpeedyError(ErrorCode.CONTRACT_VIOLATION, f"Root JSON phải là object: {path}", path=str(path))
    return data


def _is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


@contextmanager
def session_lock(
    session_dir: Path,
    *,
    owner: str = "orchestrator",
    ttl_seconds: float = 30.0,
    wait_timeout: float = 3.0,
) -> Iterator[Path]:
    """
    Khóa độc quyền trên phiên làm việc (`session.lock`).
    - Có owner, PID và thời điểm hết hạn (`expires_at`).
    - Chỉ thu hồi stale lock khi đã quá hạn VÀ tiến trình giữ khóa không còn sống.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    lock_path = session_dir / "session.lock"
    deadline = time.monotonic() + max(0.05, wait_timeout)

    while True:
        now = time.time()
        payload = json.dumps(
            {
                "owner": owner,
                "pid": os.getpid(),
                "acquired_at": now,
                "expires_at": now + ttl_seconds,
            }
        ).encode("utf-8")
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
            break
        except FileExistsError:
            # Kiểm tra stale lock
            can_reclaim = False
            try:
                existing = json.loads(lock_path.read_text(encoding="utf-8"))
                exp = float(existing.get("expires_at", 0))
                holder_pid = int(existing.get("pid", -1))
                if now > exp and not _is_pid_alive(holder_pid):
                    can_reclaim = True
            except Exception:
                # File đang được ghi dở hoặc hỏng; chỉ dọn nếu mtime đã quá ttl_seconds
                try:
                    if now - lock_path.stat().st_mtime > ttl_seconds:
                        can_reclaim = True
                except OSError:
                    pass

            if can_reclaim:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass

            if time.monotonic() >= deadline:
                raise SpeedyError(
                    ErrorCode.LOCK_CONFLICT,
                    f"Session đang bị khóa bởi tiến trình khác: {lock_path}",
                    path=str(lock_path),
                    remediation="Chờ thao tác đang chạy hoàn tất trước khi cập nhật state đồng thời.",
                )
            time.sleep(0.05)

    try:
        yield lock_path
    finally:
        try:
            if lock_path.exists():
                current = json.loads(lock_path.read_text(encoding="utf-8"))
                if int(current.get("pid", -1)) == os.getpid():
                    lock_path.unlink()
        except Exception:
            pass


def semantic_checksum(content: str) -> str:
    """
    Tính SHA-256 trên phần nội dung ngữ nghĩa của artifact:
    - Bỏ phần `## Resume Metadata` và các dòng timestamp vận hành thuần túy,
      nhằm đảm bảo cập nhật metadata tiến độ không làm mất hiệu lực approval của người dùng.
    """
    lines = []
    in_resume_meta = False
    for raw_line in (content or "").replace("\r\n", "\n").splitlines():
        stripped = raw_line.strip()
        if re.match(r"^##\s+Resume Metadata\b", stripped, re.IGNORECASE):
            in_resume_meta = True
            continue
        if in_resume_meta and stripped.startswith("## "):
            in_resume_meta = False
        if in_resume_meta:
            continue
        if _VOLATILE_MD_LINE_RE.match(raw_line):
            continue
        lines.append(raw_line.rstrip())

    canonical = "\n".join(lines).strip()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_workspace_snapshot(
    workspace_root: Path,
    *,
    focus_paths: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Tính fingerprint cho trạng thái mã nguồn thực tế trên đĩa (bao gồm cả dirty/untracked files,
    không phụ thuộc việc có `.git` hay không).
    """
    root = workspace_root.resolve()
    digest = hashlib.sha256()
    file_count = 0
    tracked_samples = []

    candidates: list[Path] = []
    if focus_paths:
        for rel in focus_paths:
            target = (root / rel).resolve()
            if target.is_file():
                candidates.append(target)
            elif target.is_dir():
                for dirpath, dirnames, filenames in os.walk(target):
                    dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_SNAPSHOT_DIRS and not d.startswith("."))
                    for fname in sorted(filenames):
                        candidates.append(Path(dirpath) / fname)
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in _IGNORE_SNAPSHOT_DIRS and not d.startswith("."))
            for fname in sorted(filenames):
                if fname == ".DS_Store" or fname.endswith((".pyc", ".bak", ".lock")):
                    continue
                candidates.append(Path(dirpath) / fname)

    seen = set()
    for file_path in sorted(candidates):
        if file_path in seen or not file_path.is_file():
            continue
        seen.add(file_path)
        try:
            rel_posix = file_path.relative_to(root).as_posix()
        except ValueError:
            continue
        file_count += 1
        # Nếu focus_paths được truyền (evidence cụ thể) thì băm nội dung thật; toàn repo thì băm nội dung cho file <= 512KB
        try:
            stat = file_path.stat()
            if focus_paths or stat.st_size <= 524288:
                fhash = file_sha256(file_path)[:16]
            else:
                fhash = f"sz{stat.st_size}:mt{int(stat.st_mtime_ns)}"
            digest.update(f"{rel_posix}:{fhash}\n".encode("utf-8"))
            if len(tracked_samples) < 25:
                tracked_samples.append(rel_posix)
        except OSError:
            continue

    return {
        "snapshot_id": digest.hexdigest()[:24],
        "files_counted": file_count,
        "sample_paths": tracked_samples,
        "captured_at": utc_now_iso(),
    }


def session_dir_for(layout: WorkspaceLayout, sid: str) -> Path:
    validate_sid(sid)
    return layout.sessions_dir / sid


def state_json_path(layout: WorkspaceLayout, sid: str) -> Path:
    return session_dir_for(layout, sid) / "state.json"


def state_md_path(layout: WorkspaceLayout, sid: str) -> Path:
    return session_dir_for(layout, sid) / "state.md"


def render_state_markdown(state: Dict[str, Any]) -> str:
    """Sinh bản hiển thị `state.md` trực tiếp từ canonical `state.json` (SSOT duy nhất)."""
    sid = state.get("sid", "")
    slug = state.get("slug", "task")
    goal = state.get("goal", "")
    mode = state.get("mode", "feature")
    policy = state.get("policy", "strict")
    status = state.get("status", "in_progress")
    current_stage = state.get("current_stage", "bootstrap")
    rev = state.get("state_revision", 1)
    updated_at = state.get("updated_at", "")
    next_action = state.get("next_action", "")
    blocked_reason = state.get("blocked_reason")

    stages_map: Dict[str, Dict[str, Any]] = state.get("stages", {})
    route = state.get("route") or list(stages_map.keys())
    rows = []
    for stage_id in route:
        info = stages_map.get(stage_id, {})
        st = info.get("status", StageStatus.PENDING.value)
        icon = _STATUS_ICONS.get(st, "⏳")
        label = STAGE_LABELS.get(stage_id, stage_id)
        artifact = info.get("artifact_path") or "-"
        if artifact != "-":
            artifact = f"[{Path(artifact).name}](./{Path(artifact).name})"
        model_used = info.get("recommended_model", "-")
        rows.append(f"| `{stage_id}` | {label} | {icon} `{st}` | {model_used} | {artifact} |")

    table = "\n".join(rows)
    blocker_block = f"\n- **Blocked Reason**: {blocked_reason}" if blocked_reason else ""
    return f"""# Session State — {slug}

- **SID**: `{sid}`
- **Goal**: {goal}
- **Flow Mode**: `{mode}` | **Gate Policy**: `{policy}`
- **Current Stage**: `{current_stage}` | **Overall Status**: `{status}`
- **State Revision**: `{rev}` | **UoW Attempts**: `{state.get("uow_attempts", 0)}/{state.get("budget", {}).get("max_uow_attempts", 3)}`
- **Next Action**: {next_action}{blocker_block}
- **Updated At**: `{updated_at}`

## Stage Pipeline

| Stage ID | Vai trò | Trạng thái | Model khuyến nghị | Artifact |
|---|---|---|---|---|
{table}
"""


def load_session_state(layout: WorkspaceLayout, sid: str) -> Dict[str, Any]:
    path = state_json_path(layout, sid)
    if not path.is_file():
        raise SpeedyError(
            ErrorCode.NOT_FOUND,
            f"Không tìm thấy canonical state cho session '{sid}'.",
            path=str(path),
            remediation="Chạy 'speedy_cli.py session list' để kiểm tra SID hợp lệ hoặc tạo mới bằng 'session new'.",
        )
    return read_json_safe(path)


def mutate_session_state_cas(
    layout: WorkspaceLayout,
    sid: str,
    mutator: Callable[[Dict[str, Any]], None],
    *,
    expected_revision: Optional[int] = None,
    owner: str = "orchestrator",
) -> Dict[str, Any]:
    """
    Cập nhật canonical `state.json` an toàn dưới `session_lock` với cơ chế Compare-And-Swap (`state_revision`),
    đồng thời tự động kết xuất lại `state.md`.
    """
    sdir = session_dir_for(layout, sid)
    with session_lock(sdir, owner=owner):
        state = load_session_state(layout, sid)
        current_rev = int(state.get("state_revision", 1))
        if expected_revision is not None and current_rev != expected_revision:
            raise SpeedyError(
                ErrorCode.CAS_CONFLICT,
                f"Xung đột phiên bản state (expected={expected_revision}, actual={current_rev}).",
                remediation="Đọc lại state mới nhất bằng 'state get' trước khi cập nhật.",
                details={"expected_revision": expected_revision, "actual_revision": current_rev},
            )

        mutator(state)
        state["state_revision"] = current_rev + 1
        state["updated_at"] = utc_now_iso()

        atomic_write_json(state_json_path(layout, sid), state)
        atomic_write_text(state_md_path(layout, sid), render_state_markdown(state))
        return state


def record_side_effect_checkpoint(
    layout: WorkspaceLayout,
    sid: str,
    operation_id: str,
    phase: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ghi nhận checkpoint trước/sau thao tác có side-effect để tránh replay mù quáng sau khi gián đoạn."""
    sdir = session_dir_for(layout, sid)
    cp_path = sdir / "checkpoints.json"
    with session_lock(sdir, owner="checkpoint"):
        data: Dict[str, Any] = {"operations": {}}
        if cp_path.is_file():
            data = read_json_safe(cp_path)
        ops = data.setdefault("operations", {})
        entry = ops.setdefault(operation_id, {})
        entry["phase"] = phase  # "started" | "completed" | "failed"
        entry["updated_at"] = utc_now_iso()
        if details:
            entry["details"] = details
        atomic_write_json(cp_path, data)
        return entry
