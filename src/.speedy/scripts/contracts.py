"""
contracts.py — Kiểu dữ liệu, enum, mã lỗi, layout resolver và kiểm soát ranh giới đường dẫn.
Thuần Python stdlib, không phụ thuộc IDE, subprocess hay LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    GATE_REQUIRED = "GATE_REQUIRED"
    STALE_ARTIFACT = "STALE_ARTIFACT"
    LOCK_CONFLICT = "LOCK_CONFLICT"
    CAS_CONFLICT = "CAS_CONFLICT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    DOOM_LOOP_DETECTED = "DOOM_LOOP_DETECTED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


class SpeedyError(Exception):
    """Ngoại lệ có cấu trúc để CLI xuất diagnostic rõ ràng ra stderr và mã thoát chuẩn."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        stage: Optional[str] = None,
        path: Optional[str] = None,
        remediation: Optional[str] = None,
        details: Optional[Dict[str, object]] = None,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.path = path
        self.remediation = remediation
        self.details = details or {}
        self.exit_code = exit_code

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "error_code": self.code.value,
            "message": self.message,
        }
        if self.stage:
            payload["stage"] = self.stage
        if self.path:
            payload["path"] = self.path
        if self.remediation:
            payload["remediation"] = self.remediation
        if self.details:
            payload["details"] = self.details
        return payload


class FlowMode(str, Enum):
    SETUP = "setup"
    FEATURE = "feature"
    FIX = "fix"
    SIMPLE = "simple"
    VERIFY = "verify"


class GatePolicy(str, Enum):
    STRICT = "strict"
    BALANCED = "balanced"


class EnforcementLevel(str, Enum):
    ADVISORY = "advisory"
    WORKFLOW_ENFORCED = "workflow_enforced"
    RUNTIME_ENFORCED = "runtime_enforced"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    FAILED = "failed"
    BLOCKED = "blocked"
    ABORTED = "aborted"
    SKIPPED = "skipped"


class SessionStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ABORTED = "aborted"


STAGE_FILES: Dict[str, str] = {
    "root_cause": "root-cause.md",
    "analyst": "handoff-1-analyst.md",
    "architect": "handoff-2-architect.md",
    "implementer": "handoff-3-implementer.md",
    "reviewer": "handoff-4-reviewer.md",
    "tester": "handoff-5-tester.md",
    "docs": "handoff-6-docs.md",
    "verify_report": "verify-report.md",
}

STAGE_LABELS: Dict[str, str] = {
    "bootstrap": "Bootstrap",
    "root_cause": "Root Cause Pre-flight",
    "analyst": "Analyst",
    "architect": "Architect",
    "implementer": "Implementer",
    "reviewer": "Reviewer",
    "tester": "Tester",
    "docs": "Docs Manager",
    "verify_report": "Verify Report",
    "wrapup": "Wrap-up",
}

FLOW_STAGE_ROUTES: Dict[str, List[str]] = {
    FlowMode.SETUP.value: ["bootstrap", "docs", "wrapup"],
    FlowMode.FEATURE.value: [
        "bootstrap",
        "analyst",
        "architect",
        "implementer",
        "reviewer",
        "tester",
        "docs",
        "wrapup",
    ],
    FlowMode.FIX.value: [
        "bootstrap",
        "root_cause",
        "analyst",
        "architect",
        "implementer",
        "reviewer",
        "tester",
        "docs",
        "wrapup",
    ],
    FlowMode.SIMPLE.value: ["bootstrap", "implementer", "wrapup"],
    FlowMode.VERIFY.value: ["bootstrap", "reviewer", "tester", "verify_report", "wrapup"],
}

REQUIRED_HANDOFF_HEADINGS: Sequence[str] = (
    "## Summary",
    "## Scope",
    "## Risks",
    "## Dependencies",
    "## Open questions",
)

SID_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9_-]{1,64}$")


def sanitize_slug(value: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", (value or "").strip().lower())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-_")
    return (cleaned[:max_len].rstrip("-_")) or "task"


def validate_sid(sid: str) -> str:
    if not sid or not SID_PATTERN.match(sid):
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"SID không hợp lệ: '{sid}'",
            remediation="Dùng định dạng YYYY-MM-DD-<slug>-<6hex> (chỉ gồm chữ thường, số, gạch ngang/dưới).",
        )
    return sid


@dataclass(frozen=True)
class WorkspaceLayout:
    """
    Ánh xạ đường dẫn dùng chung cho cả Speedy Product (ai-workspace/) và SNOW Builder (root).
    Tránh fork hai bản CLI khác nhau.
    """

    root: Path
    kind: str  # "product" | "builder"
    speedy_dir: Path
    runtime_root: Path
    sessions_dir: Path
    plans_dir: Path
    state_dir: Path
    audit_dir: Path
    logs_dir: Path
    reports_dir: Path
    docs_dir: Path
    tmp_dir: Path


def resolve_layout(base_dir: str | Path = ".", layout_mode: str = "auto") -> WorkspaceLayout:
    root = Path(base_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SpeedyError(
            ErrorCode.NOT_FOUND,
            f"Thư mục workspace không tồn tại: {root}",
            path=str(root),
        )

    if layout_mode not in {"auto", "product", "builder"}:
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"layout_mode không hợp lệ: {layout_mode}",
            remediation="Chọn một trong: auto, product, builder.",
        )

    has_product_ws = (root / "ai-workspace").is_dir() and (root / ".speedy").is_dir()
    has_builder_ws = (root / "src" / ".speedy").is_dir() and (root / "sessions").is_dir()

    if layout_mode == "product" or (layout_mode == "auto" and has_product_ws):
        rt = root / "ai-workspace"
        return WorkspaceLayout(
            root=root,
            kind="product",
            speedy_dir=root / ".speedy",
            runtime_root=rt,
            sessions_dir=rt / "sessions",
            plans_dir=rt / "plans",
            state_dir=rt / "state",
            audit_dir=rt / "audit",
            logs_dir=rt / "logs",
            reports_dir=rt / "reports",
            docs_dir=rt / "docs",
            tmp_dir=rt / "tmp",
        )

    if layout_mode == "builder" or (layout_mode == "auto" and has_builder_ws):
        return WorkspaceLayout(
            root=root,
            kind="builder",
            speedy_dir=root / "src" / ".speedy",
            runtime_root=root,
            sessions_dir=root / "sessions",
            plans_dir=root / "plans",
            state_dir=root / "sessions" / "_state",
            audit_dir=root / "logs" / "audit",
            logs_dir=root / "logs",
            reports_dir=root / "reports",
            docs_dir=root / "docs",
            tmp_dir=root / "tmp",
        )

    # Mặc định theo cấu trúc Product cho dự án mới cài Speedy
    rt = root / "ai-workspace"
    return WorkspaceLayout(
        root=root,
        kind="product",
        speedy_dir=root / ".speedy",
        runtime_root=rt,
        sessions_dir=rt / "sessions",
        plans_dir=rt / "plans",
        state_dir=rt / "state",
        audit_dir=rt / "audit",
        logs_dir=rt / "logs",
        reports_dir=rt / "reports",
        docs_dir=rt / "docs",
        tmp_dir=rt / "tmp",
    )


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_within_scope(
    workspace_root: Path,
    candidate: str | Path,
    *,
    allowed_prefixes: Optional[Iterable[str]] = None,
    forbidden_prefixes: Optional[Iterable[str]] = None,
) -> Path:
    """
    Giải quyết đường dẫn an toàn:
    1. Chặn path traversal (`..`) vượt ra ngoài `workspace_root`.
    2. Chặn symlink trỏ ra ngoài `workspace_root`.
    3. Kiểm tra `allowed_prefixes` và `forbidden_prefixes` (nếu có).
    """
    root_resolved = workspace_root.resolve()
    cand_path = Path(candidate)

    # Kiểm tra các phần tử '..' thô nếu đường dẫn là tương đối
    raw_target = (root_resolved / cand_path) if not cand_path.is_absolute() else cand_path

    # Nếu bản thân candidate hoặc cha gần nhất là symlink trỏ ra ngoài root -> chặn ngay
    resolved_target = raw_target.resolve(strict=False)
    if not _is_within(resolved_target, root_resolved):
        raise SpeedyError(
            ErrorCode.SCOPE_VIOLATION,
            f"Đường dẫn vượt khỏi workspace_root (path traversal hoặc symlink escape): {candidate}",
            path=str(candidate),
            remediation="Chỉ thao tác trên đường dẫn con nằm bên trong workspace hiện tại.",
        )

    rel_posix = resolved_target.relative_to(root_resolved).as_posix()
    if rel_posix == ".":
        rel_posix = ""

    if forbidden_prefixes:
        for prefix in forbidden_prefixes:
            norm = prefix.strip().strip("/")
            if not norm:
                continue
            if rel_posix == norm or rel_posix.startswith(norm + "/"):
                raise SpeedyError(
                    ErrorCode.SCOPE_VIOLATION,
                    f"Đường dẫn nằm trong vùng bị cấm ('{prefix}'): {rel_posix}",
                    path=rel_posix,
                    remediation="Xin người dùng cập nhật scope nếu thực sự cần chạm vào vùng này.",
                )

    if allowed_prefixes:
        normalized_allowed = [p.strip().strip("/") for p in allowed_prefixes if p and p.strip()]
        if normalized_allowed and "." not in normalized_allowed and "*" not in normalized_allowed:
            matched = any(
                rel_posix == allowed or rel_posix.startswith(allowed + "/")
                for allowed in normalized_allowed
            )
            if not matched:
                raise SpeedyError(
                    ErrorCode.SCOPE_VIOLATION,
                    f"Đường dẫn '{rel_posix}' nằm ngoài allowed_paths đã duyệt: {normalized_allowed}",
                    path=rel_posix,
                    remediation="Chỉ sửa các đường dẫn trong scope đã duyệt hoặc mở rộng scope qua HITL Gate.",
                )

    return resolved_target


@dataclass
class UoWContract:
    """Hợp đồng giao việc cho một Unit of Work (single-writer / bounded worker)."""

    uow_id: str
    stage: str
    objective: str
    allowed_write_paths: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"
    assigned_model: str = "Gemini Neon"
