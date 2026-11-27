"""
policy.py — Hàm quyết định thuần túy: phân loại intent theo rủi ro, chọn model Gemini,
resolve ngân sách thực thi hữu hạn, kiểm tra chuyển trạng thái và phát hiện doom-loop.
Không thực hiện file I/O và không gọi subprocess hay API LLM.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Dict, List, Optional, Sequence

from contracts import (
    FLOW_STAGE_ROUTES,
    ErrorCode,
    FlowMode,
    GatePolicy,
    SpeedyError,
    StageStatus,
)

_FIX_KEYWORDS = {
    "fix", "bug", "lỗi", "sửa", "repair", "patch", "broken", "crash",
    "error", "regression", "hotfix", "defect", "issue", "fail", "failure",
    "debug", "incorrect", "wrong", "unexpected", "không hoạt động",
    "không chạy", "bị lỗi", "lỗi sai", "treo", "exception", "traceback",
}

_SIMPLE_KEYWORDS = {
    "simple", "nhanh", "typo", "rename", "comment", "update readme",
    "cập nhật readme", "đơn giản", "minor", "wording", "label", "caption",
    "chính tả",
}

_VERIFY_KEYWORDS = {
    "verify", "kiểm tra", "review", "check", "audit", "validate",
    "xác minh", "confirm", "inspect", "đánh giá", "test existing",
    "verify-only", "chỉ kiểm tra",
}

_SETUP_KEYWORDS = {
    "setup", "khởi tạo speedy", "onboarding", "scan baseline", "cài đặt ban đầu",
}

_FEATURE_KEYWORDS = {
    "feature", "tính năng mới", "thêm tính năng", "xây dựng", "implement", "create", "add", "thêm",
}


def _kw_hit(normalized: str, tokens: set[str], kw: str) -> bool:
    if " " in kw or "-" in kw:
        return f" {kw} " in f" {normalized} "
    return kw in tokens

# Các từ khóa/vùng nhạy cảm không bao giờ được tự động xếp vào simple flow
HIGH_RISK_SIGNALS = {
    "auth", "authentication", "authorize", "authorization", "jwt", "oauth",
    "token", "session", "cookie", "password", "passwd", "secret", "credential",
    "crypto", "encrypt", "permission", "rbac", "acl", "security",
    "payment", "billing", "invoice", "wallet", "transaction", "checkout",
    "schema", "migration", "database", "alembic", "prisma", "flyway", "sql",
    "breaking", "public api", "production", "concurrency", "lock",
}

COMPLEX_ARCHITECTURE_SIGNALS = {
    "architecture", "kiến trúc", "distributed", "state machine", "concurrency",
    "race condition", "deadlock", "refactor core", "multi-tenant", "sharding",
    "consensus", "compiler", "engine", "security model",
}

SAFE_SIMPLE_EXTENSIONS = {".md", ".txt", ".json", ".properties", ".toml", ".yaml", ".yml"}

DEFAULT_POLICY_CONFIG: Dict[str, object] = {
    "default_profile": "balanced",
    "model_routing": {
        "light_model": "Gemini Hydrogen",
        "standard_model": "Gemini Neon",
        "complex_model": "Gemini Carbon",
        "light_roles": ["orchestrator", "docs-manager", "docs", "writer", "wrapup", "bootstrap"],
        "standard_roles": ["analyst", "specs", "implementer", "tester", "root_cause", "verify_report"],
        "complex_eligible_roles": ["architect", "reviewer"],
    },
    "profiles": {
        "strict": {
            "gate_policy": "strict",
            "auto_pass_stages": ["bootstrap"],
            "max_uow_attempts": 3,
            "max_parallel_workers": 2,
            "stage_deadline_seconds": 600,
            "max_tool_calls": 60,
            "max_context_packet_bytes": 16384,
            "max_tool_output_bytes": 12288,
            "max_measured_tokens": None,
            "max_reference_cost": None,
        },
        "balanced": {
            "gate_policy": "balanced",
            "auto_pass_stages": [
                "bootstrap",
                "analyst",
                "architect",
                "implementer",
                "reviewer",
                "tester",
                "docs",
                "verify_report",
                "wrapup",
            ],
            "hitl_triggers": [
                "high_risk",
                "open_questions",
                "reviewer_request_changes",
                "verification_failed",
                "file_conflicts",
                "release_or_push",
            ],
            "max_uow_attempts": 3,
            "max_parallel_workers": 2,
            "stage_deadline_seconds": 600,
            "max_tool_calls": 60,
            "max_context_packet_bytes": 16384,
            "max_tool_output_bytes": 12288,
            "max_measured_tokens": None,
            "max_reference_cost": None,
        },
    },
}


def _normalize(text: str) -> str:
    norm = unicodedata.normalize("NFC", text or "").lower()
    norm = re.sub(r"[^\w\s./-]", " ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def detect_risk_signals(text: str, target_paths: Optional[Sequence[str]] = None) -> Dict[str, object]:
    normalized = _normalize(text)
    combined = normalized + " " + " ".join((p or "").lower() for p in (target_paths or []))
    tokens = set(re.split(r"[^a-z0-9_]+", combined))

    matched_risk: List[str] = []
    for signal in sorted(HIGH_RISK_SIGNALS):
        if " " in signal:
            if signal in combined:
                matched_risk.append(signal)
        elif signal in tokens or any(part == signal for part in re.split(r"[/._-]+", combined)):
            matched_risk.append(signal)

    matched_complex: List[str] = []
    for signal in sorted(COMPLEX_ARCHITECTURE_SIGNALS):
        if signal in combined:
            matched_complex.append(signal)

    non_simple_paths: List[str] = []
    if target_paths:
        if len(target_paths) > 1:
            non_simple_paths.append(f"multiple_files({len(target_paths)})")
        for p in target_paths:
            dot_idx = p.rfind(".")
            ext = p[dot_idx:].lower() if dot_idx != -1 else ""
            if ext not in SAFE_SIMPLE_EXTENSIONS:
                non_simple_paths.append(p)

    return {
        "high_risk": bool(matched_risk),
        "risk_reasons": matched_risk,
        "complex_architecture": bool(matched_complex),
        "complexity_reasons": matched_complex,
        "non_simple_paths": non_simple_paths,
    }


def select_gemini_model(
    role: str,
    *,
    high_risk: bool = False,
    complex_architecture: bool = False,
    repeated_failure: bool = False,
) -> Dict[str, object]:
    """
    Phân bổ model Gemini trên Antigravity theo đúng thứ tự ưu tiên của thiết kế:
    - Tác vụ nhẹ / điều phối / tài liệu -> Gemini Hydrogen
    - Tác vụ bình thường -> Gemini Neon
    - Nội dung cực kỳ phức tạp / rủi ro cao (chỉ cho architect/reviewer) -> Gemini Carbon (kèm cảnh báo quota)
    """
    role_norm = (role or "").strip().lower()
    if role_norm.endswith("-docs-manager"):
        base_role = "docs-manager"
    else:
        base_role = role_norm.rsplit("-", 1)[-1] if "-" in role_norm and role_norm != "docs-manager" else role_norm

    light_roles = {"orchestrator", "flow", "docs-manager", "docs", "writer", "bootstrap", "wrapup"}
    carbon_eligible = {"architect", "reviewer"}

    if role_norm in light_roles or base_role in light_roles:
        return {
            "model": "Gemini Hydrogen",
            "tier": "light",
            "subagent_hint": "flash",
            "quota_warning": False,
            "reason": "Tác vụ điều phối / tài liệu nhẹ — ưu tiên Gemini Hydrogen để tiết kiệm quota.",
        }

    if (role_norm in carbon_eligible or base_role in carbon_eligible) and (high_risk or complex_architecture or repeated_failure):
        triggers = []
        if high_risk:
            triggers.append("high_risk_domain")
        if complex_architecture:
            triggers.append("complex_architecture")
        if repeated_failure:
            triggers.append("repeated_failure")
        return {
            "model": "Gemini Carbon",
            "tier": "complex_restricted",
            "subagent_hint": "pro",
            "quota_warning": True,
            "escalation_triggers": triggers,
            "reason": "Bài toán có độ phức tạp/rủi ro cao — dùng có kiểm soát Gemini Carbon (lưu ý giới hạn quota nhanh đầy).",
        }

    return {
        "model": "Gemini Neon",
        "tier": "standard",
        "subagent_hint": "inherit",
        "quota_warning": False,
        "reason": "Tác vụ phát triển/kiểm thử tiêu chuẩn — dùng mặc định Gemini Neon.",
    }


def classify_intent(
    text: str,
    *,
    target_paths: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Phân loại intent dựa trên nội dung yêu cầu VÀ tín hiệu rủi ro/phạm vi file."""
    normalized = _normalize(text)
    if not normalized:
        raise SpeedyError(ErrorCode.INVALID_INPUT, "Nội dung yêu cầu không được rỗng khi phân loại intent.")

    tokens = set(normalized.split())
    risk_info = detect_risk_signals(text, target_paths=target_paths)

    scores = {
        FlowMode.SETUP.value: 0,
        FlowMode.FIX.value: 0,
        FlowMode.VERIFY.value: 0,
        FlowMode.SIMPLE.value: 0,
        FlowMode.FEATURE.value: 0,
    }

    for kw in _SETUP_KEYWORDS:
        if _kw_hit(normalized, tokens, kw):
            scores[FlowMode.SETUP.value] += 4
    for kw in _FIX_KEYWORDS:
        if _kw_hit(normalized, tokens, kw):
            scores[FlowMode.FIX.value] += 3
    for kw in _VERIFY_KEYWORDS:
        if _kw_hit(normalized, tokens, kw):
            scores[FlowMode.VERIFY.value] += 3
    for kw in _SIMPLE_KEYWORDS:
        if _kw_hit(normalized, tokens, kw):
            scores[FlowMode.SIMPLE.value] += 3
    for kw in _FEATURE_KEYWORDS:
        if _kw_hit(normalized, tokens, kw):
            scores[FlowMode.FEATURE.value] += 3

    best_mode = max(scores, key=lambda k: scores[k])
    if scores[best_mode] == 0:
        best_mode = FlowMode.FEATURE.value

    has_risk_blocker = bool(
        risk_info["high_risk"]
        or risk_info["complex_architecture"]
        or risk_info["non_simple_paths"]
    )
    downgraded_from_simple = scores[FlowMode.SIMPLE.value] > 0 and has_risk_blocker
    # Chặn xếp vào simple nếu có rủi ro cao hoặc sửa code/nhiều file
    if best_mode == FlowMode.SIMPLE.value and has_risk_blocker:
        best_mode = FlowMode.FIX.value if scores[FlowMode.FIX.value] > 0 else FlowMode.FEATURE.value

    stages = FLOW_STAGE_ROUTES[best_mode]
    stage_models = {
        stage: select_gemini_model(
            stage,
            high_risk=bool(risk_info["high_risk"]),
            complex_architecture=bool(risk_info["complex_architecture"]),
        )
        for stage in stages
    }

    return {
        "intent": best_mode,
        "route": stages,
        "high_risk": risk_info["high_risk"],
        "risk_reasons": risk_info["risk_reasons"],
        "complex_architecture": risk_info["complex_architecture"],
        "escalated_from_simple": downgraded_from_simple,
        "recommended_models": stage_models,
    }


def resolve_execution_budget(
    profile_name: str = GatePolicy.BALANCED.value,
    policy_config: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Chốt ngân sách hữu hạn trước khi chạy stage; ghi rõ giới hạn nào host không tự đo được."""
    cfg = policy_config or DEFAULT_POLICY_CONFIG
    profiles = cfg.get("profiles", DEFAULT_POLICY_CONFIG["profiles"])
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"Profile chính sách không hợp lệ: '{profile_name}'",
            remediation="Dùng 'balanced' (mặc định) hoặc 'strict'.",
        )

    raw = dict(profiles[profile_name])
    max_attempts = int(raw.get("max_uow_attempts") or 3)
    max_workers = int(raw.get("max_parallel_workers") or 2)
    deadline_s = int(raw.get("stage_deadline_seconds") or 600)
    max_tools = int(raw.get("max_tool_calls") or 60)
    packet_bytes = int(raw.get("max_context_packet_bytes") or 16384)
    output_bytes = int(raw.get("max_tool_output_bytes") or 12288)

    if max_attempts < 1 or deadline_s <= 0 or max_tools <= 0:
        raise SpeedyError(
            ErrorCode.CONTRACT_VIOLATION,
            "Ngân sách thực thi bắt buộc phải hữu hạn và > 0 cho attempts, deadline và tool_calls.",
        )

    return {
        "gate_policy": raw.get("gate_policy", profile_name),
        "auto_pass_stages": list(raw.get("auto_pass_stages", ["bootstrap"])),
        "max_uow_attempts": max_attempts,
        "max_parallel_workers": max_workers,
        "stage_deadline_seconds": deadline_s,
        "max_tool_calls": max_tools,
        "max_context_packet_bytes": packet_bytes,
        "max_tool_output_bytes": output_bytes,
        "max_measured_tokens": raw.get("max_measured_tokens"),
        "max_reference_cost": raw.get("max_reference_cost"),
        "enforcement": {
            "uow_attempts": "workflow_enforced",
            "stage_deadline_seconds": "workflow_enforced",
            "context_packet_bytes": "workflow_enforced",
            "tool_output_bytes": "workflow_enforced",
            "measured_tokens": "unsupported_by_host" if raw.get("max_measured_tokens") is None else "workflow_enforced",
            "reference_cost": "unsupported_by_host" if raw.get("max_reference_cost") is None else "workflow_enforced",
        },
    }


def stage_requires_human_gate(
    stage: str,
    gate_policy: str,
    high_risk: bool = False,
    has_open_questions: bool = False,
) -> bool:
    """
    Xác định một stage có bắt buộc dừng chờ người dùng phê duyệt (HITL) hay không:
    - Chế độ `strict`: dừng mọi stage chuyên môn.
    - Chế độ `balanced` (mặc định): chỉ dừng HITL khi task có `high_risk=True` hoặc handoff có `Open questions` cần người dùng chốt; các stage rủi ro thấp đạt chuẩn tự động đi tiếp.
    """
    if stage in {"bootstrap", "wrapup", "root_cause"}:
        return False
    if gate_policy == GatePolicy.STRICT.value or high_risk or has_open_questions:
        return True
    return False


def compute_failure_fingerprint(error_class: str, command: str, diagnostic_summary: str) -> str:
    normalized = f"{error_class.strip().lower()}|{command.strip()}|{_normalize(diagnostic_summary)[:200]}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def check_retry_and_doom_loop(
    *,
    uow_attempts: int,
    max_uow_attempts: int,
    failure_history: Sequence[Dict[str, object]],
    new_fingerprint: str,
    has_new_hypothesis: bool = False,
) -> None:
    """Chặn vượt ngân sách attempt của UoW hoặc lặp lại y hệt lỗi cũ mà không có giả thuyết mới."""
    if uow_attempts >= max_uow_attempts:
        raise SpeedyError(
            ErrorCode.BUDGET_EXCEEDED,
            f"Đã chạm trần số lần thử của UoW ({uow_attempts}/{max_uow_attempts}).",
            remediation="Báo cáo phần đã đạt/chưa đạt và xin quyết định từ người dùng (Approve mở rộng budget / Abort).",
        )

    previous_fps = [str(item.get("fingerprint", "")) for item in failure_history]
    if new_fingerprint in previous_fps and not has_new_hypothesis:
        raise SpeedyError(
            ErrorCode.DOOM_LOOP_DETECTED,
            f"Phát hiện Doom Loop: lặp lại cùng failure fingerprint '{new_fingerprint}' mà không có chẩn đoán/giả thuyết mới.",
            remediation="Phân tích nguyên nhân gốc mới hoặc dừng lại hỏi người dùng, không chạy lại cách sửa cũ.",
        )


def validate_stage_status_transition(current_status: str, next_status: str) -> None:
    allowed = {
        StageStatus.PENDING.value: {
            StageStatus.RUNNING.value,
            StageStatus.SKIPPED.value,
            StageStatus.ABORTED.value,
        },
        StageStatus.RUNNING.value: {
            StageStatus.AWAITING_APPROVAL.value,
            StageStatus.APPROVED.value,
            StageStatus.FAILED.value,
            StageStatus.BLOCKED.value,
            StageStatus.ABORTED.value,
        },
        StageStatus.AWAITING_APPROVAL.value: {
            StageStatus.APPROVED.value,
            StageStatus.RUNNING.value,
            StageStatus.BLOCKED.value,
            StageStatus.ABORTED.value,
        },
        StageStatus.APPROVED.value: {
            StageStatus.RUNNING.value,  # Khi bị selective invalidation hoặc request changes
            StageStatus.AWAITING_APPROVAL.value,
        },
        StageStatus.FAILED.value: {
            StageStatus.RUNNING.value,
            StageStatus.BLOCKED.value,
            StageStatus.ABORTED.value,
        },
        StageStatus.BLOCKED.value: {
            StageStatus.RUNNING.value,
            StageStatus.ABORTED.value,
        },
        StageStatus.ABORTED.value: set(),
        StageStatus.SKIPPED.value: {StageStatus.RUNNING.value},
    }
    if next_status not in allowed.get(current_status, set()):
        raise SpeedyError(
            ErrorCode.INVALID_TRANSITION,
            f"Không thể chuyển trạng thái stage từ '{current_status}' sang '{next_status}'.",
            remediation="Kiểm tra tiến trình hiện tại bằng 'speedy_cli.py state get --sid <sid>'.",
        )
