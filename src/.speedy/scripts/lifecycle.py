"""
lifecycle.py — Quản lý vòng đời Session, State Machine deterministic, Human Gate,
Resume có kiểm tra tính toàn vẹn, Selective Invalidation và UoW Single-Writer Scheduler.
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contracts import (
    FLOW_STAGE_ROUTES,
    STAGE_FILES,
    ErrorCode,
    FlowMode,
    GatePolicy,
    SessionStatus,
    SpeedyError,
    StageStatus,
    WorkspaceLayout,
    sanitize_slug,
    validate_sid,
)
from handoff import extract_reviewer_verdict, normalize_stage_id, validate_handoff
from policy import (
    check_retry_and_doom_loop,
    classify_intent,
    compute_failure_fingerprint,
    resolve_execution_budget,
    select_gemini_model,
    stage_requires_human_gate,
    validate_stage_status_transition,
)
from scaffold import scaffold_plan
from storage import (
    atomic_write_json,
    atomic_write_text,
    compute_workspace_snapshot,
    load_session_state,
    mutate_session_state_cas,
    read_json_safe,
    render_state_markdown,
    semantic_checksum,
    session_dir_for,
    session_lock,
    state_json_path,
    state_md_path,
    utc_now_iso,
)


def _load_policy_file(layout: WorkspaceLayout) -> Optional[Dict[str, Any]]:
    cfg_path = layout.speedy_dir / "config" / "policy.default.json"
    if cfg_path.is_file():
        try:
            return read_json_safe(cfg_path)
        except SpeedyError:
            return None
    return None


def _read_env_value(layout: WorkspaceLayout, key: str) -> Optional[str]:
    env_val = os.environ.get(key, "").strip()
    if env_val:
        return env_val
    env_file = layout.runtime_root / ".env"
    if not env_file.is_file():
        return None
    try:
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            k, v = clean.split("=", 1)
            if k.strip() == key:
                val = v.strip().strip('"').strip("'")
                return val or None
    except OSError:
        return None
    return None


def _generate_unique_sid(layout: WorkspaceLayout, slug: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    short_slug = sanitize_slug(slug, max_len=28)
    for _ in range(20):
        token = secrets.token_hex(3)
        candidate = f"{today}-{short_slug}-{token}"
        if not (layout.sessions_dir / candidate).exists():
            return candidate
    raise SpeedyError(ErrorCode.LOCK_CONFLICT, "Không thể sinh SID duy nhất sau 20 lần thử.")


def create_session(
    layout: WorkspaceLayout,
    *,
    slug: str,
    goal: str,
    mode: Optional[str] = None,
    policy_profile: Optional[str] = None,
    execution_mode: str = "antigravity_subagent",
    allowed_paths: Optional[Sequence[str]] = None,
    forbidden_paths: Optional[Sequence[str]] = None,
    command_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Khởi tạo session mới với SID chống đụng độ, canonical `state.json`, `state.md` và plan."""
    clean_goal = (goal or slug or "").strip()
    if not clean_goal:
        raise SpeedyError(ErrorCode.INVALID_INPUT, "Mục tiêu (goal) không được để trống khi tạo session.")

    intent_info = classify_intent(clean_goal, target_paths=allowed_paths)
    resolved_mode = mode or str(intent_info["intent"])
    if resolved_mode not in FLOW_STAGE_ROUTES:
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"Flow mode không hợp lệ: '{resolved_mode}'.",
            remediation=f"Chọn một trong: {list(FLOW_STAGE_ROUTES.keys())}",
        )

    policy_cfg = _load_policy_file(layout)
    env_policy = (_read_env_value(layout, "SPEEDY_GATE_POLICY") or "").lower()
    if env_policy not in {GatePolicy.STRICT.value, GatePolicy.BALANCED.value}:
        env_policy = ""
    profile = (
        policy_profile
        or env_policy
        or str((policy_cfg or {}).get("default_profile") or GatePolicy.BALANCED.value)
    )
    budget = resolve_execution_budget(profile, policy_cfg)

    sid = _generate_unique_sid(layout, slug or clean_goal)
    sdir = session_dir_for(layout, sid)
    sdir.mkdir(parents=True, exist_ok=True)
    plan_path = scaffold_plan(layout, sid, slug or clean_goal, clean_goal)

    route = list(FLOW_STAGE_ROUTES[resolved_mode])
    snapshot = compute_workspace_snapshot(layout.root, focus_paths=allowed_paths)
    high_risk = bool(intent_info.get("high_risk"))
    complex_arch = bool(intent_info.get("complex_architecture"))

    stages: Dict[str, Dict[str, Any]] = {}
    for stage_id in route:
        model_rec = select_gemini_model(
            stage_id,
            high_risk=high_risk,
            complex_architecture=complex_arch,
        )
        stages[stage_id] = {
            "status": StageStatus.APPROVED.value if stage_id == "bootstrap" else StageStatus.PENDING.value,
            "recommended_model": model_rec["model"],
            "model_tier": model_rec["tier"],
            "artifact_path": None,
            "artifact_checksum": None,
            "revision": 0,
            "updated_at": utc_now_iso(),
        }

    first_work_stage = route[1] if len(route) > 1 else "wrapup"
    now = utc_now_iso()
    state: Dict[str, Any] = {
        "schema_version": 2,
        "state_revision": 1,
        "sid": sid,
        "slug": sanitize_slug(slug or clean_goal),
        "goal": clean_goal,
        "command_ref": command_ref,
        "workspace_root": str(layout.root),
        "layout_kind": layout.kind,
        "mode": resolved_mode,
        "policy": budget["gate_policy"],
        "execution_mode": execution_mode,
        "high_risk": high_risk,
        "risk_reasons": intent_info.get("risk_reasons", []),
        "complex_architecture": complex_arch,
        "route": route,
        "scope": {
            "allowed_paths": list(allowed_paths or []),
            "forbidden_paths": list(forbidden_paths or []),
        },
        "current_stage": first_work_stage,
        "status": SessionStatus.IN_PROGRESS.value,
        "stages": stages,
        "budget": budget,
        "baseline_snapshot": snapshot,
        "code_snapshot": snapshot,
        "plan_path": plan_path.relative_to(layout.root).as_posix(),
        "artifacts": {},
        "approvals": {},
        "verification": [],
        "uows": [],
        "uow_attempts": 0,
        "retry_count": 0,
        "failure_history": [],
        "audit_dir": None,
        "blocked_reason": None,
        "next_action": f"Thực thi stage '{first_work_stage}' với model khuyến nghị {stages[first_work_stage]['recommended_model']}.",
        "created_at": now,
        "updated_at": now,
    }

    with session_lock(sdir, owner="session_new"):
        atomic_write_json(state_json_path(layout, sid), state)
        atomic_write_text(state_md_path(layout, sid), render_state_markdown(state))

    return {
        "sid": sid,
        "mode": resolved_mode,
        "policy": state["policy"],
        "route": route,
        "current_stage": first_work_stage,
        "recommended_model": stages[first_work_stage]["recommended_model"],
        "session_dir": sdir.relative_to(layout.root).as_posix(),
        "state_json_path": state_json_path(layout, sid).relative_to(layout.root).as_posix(),
        "state_md_path": state_md_path(layout, sid).relative_to(layout.root).as_posix(),
        "plan_path": state["plan_path"],
        "budget": budget,
    }


def list_sessions(layout: WorkspaceLayout) -> List[Dict[str, Any]]:
    if not layout.sessions_dir.is_dir():
        return []
    items: List[Dict[str, Any]] = []
    for child in sorted(layout.sessions_dir.iterdir(), reverse=True):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        sjson = child / "state.json"
        if sjson.is_file():
            try:
                data = read_json_safe(sjson)
                items.append(
                    {
                        "sid": data.get("sid", child.name),
                        "slug": data.get("slug"),
                        "mode": data.get("mode"),
                        "status": data.get("status"),
                        "current_stage": data.get("current_stage"),
                        "state_revision": data.get("state_revision"),
                        "updated_at": data.get("updated_at"),
                    }
                )
            except SpeedyError:
                items.append({"sid": child.name, "status": "corrupted"})
    return items


def resolve_target_sid(layout: WorkspaceLayout, explicit_sid: Optional[str], *, for_mutation: bool) -> str:
    """
    Không phụ thuộc vào một file `active_session.json` toàn cục dễ đụng độ:
    - Mọi thao tác thay đổi (`for_mutation=True`) bắt buộc truyền `--sid` tường minh.
    - Thao tác chỉ đọc nếu bỏ trống `--sid`: tự chọn nếu chỉ có đúng 1 session đang mở,
      nếu có >= 2 session đang mở thì báo lỗi yêu cầu chọn SID rõ ràng.
    """
    if explicit_sid:
        return validate_sid(explicit_sid)
    if for_mutation:
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            "Thao tác thay đổi state/gate bắt buộc phải truyền '--sid <SID>' tường minh.",
            remediation="Chạy 'speedy_cli.py session list' để lấy SID cần thao tác.",
        )

    sessions = list_sessions(layout)
    active = [
        s for s in sessions if s.get("status") in {SessionStatus.IN_PROGRESS.value, SessionStatus.AWAITING_APPROVAL.value}
    ]
    if len(active) == 1:
        return str(active[0]["sid"])
    if len(active) > 1:
        sids = [s["sid"] for s in active]
        raise SpeedyError(
            ErrorCode.INVALID_INPUT,
            f"Có nhiều session đang hoạt động ({sids}); không tự đoán session.",
            remediation="Truyền tường minh '--sid <SID>' hoặc hỏi người dùng chọn session cần tiếp tục.",
        )
    if len(sessions) == 1:
        return str(sessions[0]["sid"])
    raise SpeedyError(
        ErrorCode.NOT_FOUND,
        "Không tìm thấy session đang hoạt động.",
        remediation="Tạo session mới bằng 'speedy_cli.py session new --slug ... --goal ...'.",
    )


def _selective_invalidation_check(layout: WorkspaceLayout, state: Dict[str, Any]) -> List[str]:
    """
    Kiểm tra tính tươi mới (freshness) của các artifact đã duyệt và code snapshot:
    - Nếu file handoff của `analyst` hoặc `architect` bị sửa nội dung sau khi duyệt -> hủy approval của stage đó và các stage phía sau.
    - Nếu code trên đĩa thay đổi so với snapshot lúc review/test -> giữ nguyên approval của `analyst`/`architect`,
      nhưng đánh dấu kết quả `reviewer`/`tester` cũ là stale (quay về `pending`).
    """
    invalidated: List[str] = []
    route: List[str] = state.get("route", [])
    stages: Dict[str, Dict[str, Any]] = state.get("stages", {})
    approvals: Dict[str, Dict[str, Any]] = state.get("approvals", {})

    # 1. Kiểm tra semantic checksum của từng artifact đã duyệt
    upstream_changed_idx: Optional[int] = None
    for idx, stage_id in enumerate(route):
        info = stages.get(stage_id, {})
        rel_art = info.get("artifact_path")
        if not rel_art:
            continue
        art_file = layout.root / rel_art
        if not art_file.is_file():
            if info.get("status") == StageStatus.APPROVED.value:
                upstream_changed_idx = idx if upstream_changed_idx is None else min(upstream_changed_idx, idx)
            continue
        live_checksum = semantic_checksum(art_file.read_text(encoding="utf-8", errors="replace"))
        approved_entry = approvals.get(stage_id)
        if approved_entry and approved_entry.get("artifact_checksum") != live_checksum:
            upstream_changed_idx = idx if upstream_changed_idx is None else min(upstream_changed_idx, idx)

    if upstream_changed_idx is not None:
        for stage_id in route[upstream_changed_idx:]:
            if stage_id == "bootstrap":
                continue
            st_info = stages.get(stage_id, {})
            if st_info.get("status") in {StageStatus.APPROVED.value, StageStatus.AWAITING_APPROVAL.value}:
                st_info["status"] = StageStatus.PENDING.value
                approvals.pop(stage_id, None)
                invalidated.append(stage_id)

    # 2. Nếu chỉ mã nguồn thay đổi sau khi reviewer/tester đã chạy -> chỉ invalidate reviewer/tester, giữ analyst/architect!
    allowed_paths = state.get("scope", {}).get("allowed_paths") or None
    live_snapshot = compute_workspace_snapshot(layout.root, focus_paths=allowed_paths)
    recorded_snap_id = (state.get("code_snapshot") or {}).get("snapshot_id")
    if recorded_snap_id and live_snapshot["snapshot_id"] != recorded_snap_id:
        for code_dependent_stage in ("reviewer", "tester", "verify_report"):
            if code_dependent_stage in stages and stages[code_dependent_stage].get("status") in {
                StageStatus.APPROVED.value,
                StageStatus.AWAITING_APPROVAL.value,
            }:
                stages[code_dependent_stage]["status"] = StageStatus.PENDING.value
                approvals.pop(code_dependent_stage, None)
                if code_dependent_stage not in invalidated:
                    invalidated.append(code_dependent_stage)
        state["code_snapshot"] = live_snapshot

    if invalidated:
        # Đưa current_stage về stage đầu tiên chưa hoàn thành trong route
        for stage_id in route:
            if stages.get(stage_id, {}).get("status") != StageStatus.APPROVED.value:
                state["current_stage"] = stage_id
                state["status"] = SessionStatus.IN_PROGRESS.value
                state["next_action"] = (
                    f"Phát hiện thay đổi làm stale {invalidated}; cần thực hiện lại từ stage '{stage_id}'."
                )
                break

    return invalidated


def resume_session(layout: WorkspaceLayout, sid: Optional[str]) -> Dict[str, Any]:
    """Kiểm tra toàn diện state, artifact, approval và code snapshot trước khi tiếp tục."""
    target_sid = resolve_target_sid(layout, sid, for_mutation=False)
    invalidated_stages: List[str] = []

    def _mutator(state: Dict[str, Any]) -> None:
        nonlocal invalidated_stages
        invalidated_stages = _selective_invalidation_check(layout, state)

    updated = mutate_session_state_cas(layout, target_sid, _mutator, owner="session_resume")
    cur_stage = updated["current_stage"]
    st_info = updated["stages"].get(cur_stage, {})

    return {
        "sid": target_sid,
        "status": updated["status"],
        "mode": updated["mode"],
        "policy": updated["policy"],
        "current_stage": cur_stage,
        "current_stage_status": st_info.get("status"),
        "recommended_model": st_info.get("recommended_model"),
        "uow_attempts": updated.get("uow_attempts", 0),
        "invalidated_stages": invalidated_stages,
        "awaiting_human_approval": updated["status"] == SessionStatus.AWAITING_APPROVAL.value,
        "next_action": updated["next_action"],
        "state_revision": updated["state_revision"],
    }


def transition_stage(
    layout: WorkspaceLayout,
    *,
    sid: str,
    stage: str | int | float,
    target_status: str,
    expected_revision: Optional[int] = None,
    failure_reason: Optional[str] = None,
    failure_command: Optional[str] = None,
    has_new_hypothesis: bool = False,
) -> Dict[str, Any]:
    """
    Chuyển trạng thái của một stage theo máy trạng thái hữu hạn:
    - Chặn nhảy cóc qua stage trước đó chưa `approved` (trừ trường hợp implementer -> reviewer trong feature/fix).
    - Trước khi sang `awaiting_approval` hoặc `approved`, bắt buộc validate Handoff Contract!
    - Trong chế độ `strict`, cấm gọi `state transition --status approved` cho stage cần human gate (phải qua `gate approve`).
    """
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    if target_status not in {s.value for s in StageStatus}:
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Trạng thái stage không hợp lệ: '{target_status}'.")

    result_summary: Dict[str, Any] = {}

    def _mutator(state: Dict[str, Any]) -> None:
        if state.get("status") == SessionStatus.ABORTED.value:
            raise SpeedyError(ErrorCode.INVALID_TRANSITION, "Session đã bị aborted, không thể chuyển tiếp stage.")

        route: List[str] = state.get("route", [])
        stages: Dict[str, Dict[str, Any]] = state.get("stages", {})
        if stage_id not in stages:
            raise SpeedyError(
                ErrorCode.INVALID_TRANSITION,
                f"Stage '{stage_id}' không thuộc route của mode '{state.get('mode')}': {route}",
            )

        idx = route.index(stage_id)
        # Kiểm tra các stage tiên quyết phía trước đã đạt chưa
        for prev_stage in route[:idx]:
            prev_status = stages[prev_stage].get("status")
            # Ngoại lệ hợp lệ duy nhất: trong feature/fix flow, implementer hoàn tất artifact có thể chuyển sang reviewer trước khi gate review
            if prev_stage == "implementer" and stage_id == "reviewer" and prev_status in {
                StageStatus.AWAITING_APPROVAL.value,
                StageStatus.APPROVED.value,
            }:
                continue
            if prev_status not in {StageStatus.APPROVED.value, StageStatus.SKIPPED.value}:
                raise SpeedyError(
                    ErrorCode.GATE_REQUIRED,
                    f"Không thể chạy '{stage_id}' khi stage tiên quyết '{prev_stage}' đang ở trạng thái '{prev_status}'.",
                    stage=stage_id,
                    remediation=f"Hoàn tất và xin phê duyệt stage '{prev_stage}' trước.",
                )

        current_st = stages[stage_id].get("status", StageStatus.PENDING.value)
        validate_stage_status_transition(current_st, target_status)

        policy_mode = state.get("policy", GatePolicy.STRICT.value)
        high_risk = bool(state.get("high_risk"))
        val: Optional[Dict[str, Any]] = None
        # Nếu hoàn tất công việc của stage có handoff -> bắt buộc validate handoff trên đĩa trước khi xét gate
        if target_status in {StageStatus.AWAITING_APPROVAL.value, StageStatus.APPROVED.value} and stage_id in STAGE_FILES:
            scope_cfg = state.get("scope", {})
            val = validate_handoff(
                layout,
                sid,
                stage_id,
                allowed_paths=scope_cfg.get("allowed_paths") or None,
                forbidden_paths=scope_cfg.get("forbidden_paths") or None,
            )
            if not val["valid"]:
                raise SpeedyError(
                    ErrorCode.CONTRACT_VIOLATION,
                    f"Handoff của stage '{stage_id}' chưa đạt contract: {val['errors']}",
                    stage=stage_id,
                    path=val["file_path"],
                    details=val,
                    remediation="Điền đầy đủ 5 headings + Resume Metadata và xóa toàn bộ placeholder [FILL].",
                )

        has_open_q = bool(val.get("has_open_questions")) if val else False
        reviewer_req_changes = bool(val and stage_id == "reviewer" and val.get("reviewer_verdict") == "REQUEST_CHANGES")
        needs_human = stage_requires_human_gate(
            stage_id,
            policy_mode,
            high_risk=high_risk,
            has_open_questions=has_open_q,
        ) or reviewer_req_changes
        # Trong feature/fix ở chế độ strict, implementer đi tiếp sang reviewer để review độc lập rồi mới dừng ở gate reviewer
        if stage_id == "implementer" and "reviewer" in route and not has_open_q:
            needs_human = False

        if target_status == StageStatus.APPROVED.value and needs_human:
            reason_hint = (
                "Handoff còn mục 'Open questions' cần người dùng xác nhận"
                if has_open_q
                else "Reviewer trả về REQUEST_CHANGES"
                if reviewer_req_changes
                else f"Stage '{stage_id}' bắt buộc có phê duyệt của con người trong chế độ '{policy_mode}'"
            )
            raise SpeedyError(
                ErrorCode.GATE_REQUIRED,
                f"{reason_hint}.",
                stage=stage_id,
                remediation="Chuyển sang 'awaiting_approval', gửi link artifact cho User rồi dùng 'gate approve --actor human'.",
            )

        if val is not None:
            stages[stage_id]["artifact_path"] = val["file_path"]
            stages[stage_id]["artifact_checksum"] = val["semantic_checksum"]
            stages[stage_id]["revision"] = val["revision"]
            state.setdefault("artifacts", {})[stage_id] = {
                "path": val["file_path"],
                "semantic_checksum": val["semantic_checksum"],
                "revision": val["revision"],
                "updated_at": utc_now_iso(),
            }
            if stage_id == "implementer":
                scope_cfg = state.get("scope", {})
                state["code_snapshot"] = compute_workspace_snapshot(
                    layout.root,
                    focus_paths=scope_cfg.get("allowed_paths") or None,
                )

        if target_status == StageStatus.FAILED.value:
            fp = compute_failure_fingerprint(
                "stage_failure",
                failure_command or stage_id,
                failure_reason or "unspecified_failure",
            )
            max_attempts = int(state.get("budget", {}).get("max_uow_attempts", 3))
            check_retry_and_doom_loop(
                uow_attempts=int(state.get("uow_attempts", 0)),
                max_uow_attempts=max_attempts,
                failure_history=state.get("failure_history", []),
                new_fingerprint=fp,
                has_new_hypothesis=has_new_hypothesis,
            )
            state["uow_attempts"] = int(state.get("uow_attempts", 0)) + 1
            state["retry_count"] = int(state.get("retry_count", 0)) + 1
            state.setdefault("failure_history", []).append(
                {
                    "stage": stage_id,
                    "fingerprint": fp,
                    "reason": failure_reason or "unspecified_failure",
                    "timestamp": utc_now_iso(),
                }
            )

        stages[stage_id]["status"] = target_status
        stages[stage_id]["updated_at"] = utc_now_iso()
        state["current_stage"] = stage_id

        # Tự động giải phóng các UoW đang chạy của stage khi stage hoàn tất/chờ duyệt
        if target_status in {StageStatus.AWAITING_APPROVAL.value, StageStatus.APPROVED.value}:
            for uow in state.get("uows", []):
                if uow.get("stage") == stage_id and uow.get("status") == "running":
                    uow["status"] = "completed"
                    uow["completed_at"] = utc_now_iso()

        if target_status == StageStatus.AWAITING_APPROVAL.value:
            state["status"] = SessionStatus.AWAITING_APPROVAL.value
            state["next_action"] = f"Hiển thị link artifact của '{stage_id}' và chờ User chọn Approve / Request Changes / Abort."
        elif target_status == StageStatus.APPROVED.value:
            if stage_id == "wrapup":
                # Kiểm tra verification bắt buộc đạt PASS và đúng snapshot hiện tại nếu có thay đổi code (feature/fix)
                if state.get("mode") in {FlowMode.FEATURE.value, FlowMode.FIX.value}:
                    verifications = state.get("verification") or []
                    if not verifications:
                        raise SpeedyError(
                            ErrorCode.VERIFICATION_FAILED,
                            "Không thể hoàn tất session (wrapup) khi chưa có bằng chứng verification nào được ghi nhận.",
                            stage="wrapup",
                            remediation="Chạy 'speedy_cli.py verify run --sid <sid>' trước khi đóng phiên.",
                        )
                    latest_v = verifications[-1]
                    if latest_v.get("overall_status") != "PASS":
                        raise SpeedyError(
                            ErrorCode.VERIFICATION_FAILED,
                            f"Không thể hoàn tất session (wrapup) khi kết quả verification mới nhất là '{latest_v.get('overall_status')}' (yêu cầu PASS).",
                            stage="wrapup",
                            remediation="Sửa lỗi và chạy lại 'speedy_cli.py verify run --sid <sid>' đến khi overall_status == PASS.",
                        )
                    live_snap = compute_workspace_snapshot(
                        layout.root,
                        focus_paths=state.get("scope", {}).get("allowed_paths") or None,
                    )
                    verified_snap_id = (latest_v.get("snapshot") or {}).get("snapshot_id")
                    if verified_snap_id and verified_snap_id != live_snap["snapshot_id"]:
                        raise SpeedyError(
                            ErrorCode.VERIFICATION_FAILED,
                            "Mã nguồn đã thay đổi sau lần chạy verification cuối cùng (stale verification snapshot).",
                            stage="wrapup",
                            remediation="Chạy lại 'speedy_cli.py verify run --sid <sid>' trên snapshot mã nguồn hiện tại.",
                        )
                state["status"] = SessionStatus.COMPLETED.value
                state["next_action"] = "Session đã hoàn tất kèm đầy đủ bằng chứng."
            else:
                next_stage = route[idx + 1] if idx + 1 < len(route) else "wrapup"
                state["current_stage"] = next_stage
                state["status"] = SessionStatus.IN_PROGRESS.value
                state["next_action"] = f"Chuyển sang thực thi stage '{next_stage}'."
        elif target_status == StageStatus.BLOCKED.value:
            state["status"] = SessionStatus.BLOCKED.value
            state["blocked_reason"] = failure_reason or "Blocked"
            state["next_action"] = f" Xử lý blocker tại '{stage_id}': {state['blocked_reason']}"
        elif target_status == StageStatus.FAILED.value:
            state["status"] = SessionStatus.IN_PROGRESS.value
            state["next_action"] = f"Chẩn đoán lỗi và thử lại '{stage_id}' (attempt {state['uow_attempts']})."

        result_summary.update(
            {
                "sid": sid,
                "stage": stage_id,
                "stage_status": target_status,
                "session_status": state["status"],
                "current_stage": state["current_stage"],
                "next_action": state["next_action"],
            }
        )

    prev_ts_box: Dict[str, Optional[str]] = {"ts": None}

    def _mutator_capture_ts(state: Dict[str, Any]) -> None:
        st_info = (state.get("stages") or {}).get(stage_id, {})
        prev_ts_box["ts"] = st_info.get("updated_at") or state.get("updated_at") or state.get("created_at")
        _mutator(state)

    updated = mutate_session_state_cas(layout, sid, _mutator_capture_ts, expected_revision=expected_revision)
    result_summary["state_revision"] = updated["state_revision"]

    # Tự động ghi telemetry sang Audit 4 lớp (non-fatal)
    audit_dir = updated.get("audit_dir")
    if audit_dir:
        try:
            from audit import AUDIT_FILENAMES, _parse_iso_ms, finalize_audit, record_stage_telemetry

            model_info = select_gemini_model(
                stage_id,
                high_risk=bool(updated.get("high_risk")),
                complex_architecture=bool(updated.get("complex_architecture")),
                repeated_failure=int(updated.get("uow_attempts", 0)) >= 2,
            )
            dur_ms: Optional[int] = None
            if target_status in {StageStatus.APPROVED.value, StageStatus.AWAITING_APPROVAL.value, StageStatus.FAILED.value}:
                start_ms = _parse_iso_ms(prev_ts_box.get("ts"))
                end_ms = _parse_iso_ms(utc_now_iso())
                if start_ms is not None and end_ms is not None:
                    dur_ms = max(0, end_ms - start_ms)
            record_stage_telemetry(
                layout,
                audit_dir=audit_dir,
                stage=stage_id,
                status=target_status,
                model=model_info.get("model"),
                duration_ms=dur_ms,
                note=failure_reason or target_status,
                retry_count=int(updated.get("retry_count", 0)),
            )
            if stage_id == "wrapup" and target_status == StageStatus.APPROVED.value:
                inp_file = resolve_within_scope(layout.root, audit_dir) / AUDIT_FILENAMES[0]
                if inp_file.is_file():
                    inp_data = read_json_safe(inp_file)
                    if not (inp_data.get("task_identity") or {}).get("ended_at"):
                        finalize_audit(
                            layout,
                            audit_dir=audit_dir,
                            outcome="success",
                            completion_level="verified",
                        )
        except Exception:
            pass

    return result_summary


def _refresh_docs_harness(layout: WorkspaceLayout, result: Dict[str, Any]) -> None:
    try:
        from repomap import build_repomap, generate_docs_index_md

        if layout.docs_dir.is_dir() and any(layout.docs_dir.rglob("*.md")):
            idx_res = generate_docs_index_md(layout)
            result["knowledge_index_synced"] = idx_res["index_md_path"]
        else:
            build_repomap(layout, use_cache=True)
        result["repomap_refreshed"] = True
    except Exception as exc:
        result["repomap_refreshed"] = False
        result["repomap_refresh_error"] = str(exc)


def complete_stage(
    layout: WorkspaceLayout,
    *,
    sid: str,
    stage: str | int | float,
) -> Dict[str, Any]:
    """
    Lệnh gộp 1 bước giúp tăng tốc điều phối (giảm từ 3 lần khởi động CLI xuống còn 1 lần):
    - Nếu stage đang `pending` -> tự chuyển sang `running`.
    - Validate handoff trên đĩa và đánh giá tự động xem có cần dừng HITL không.
    - Nếu `balanced` + không `high_risk` + không có `Open questions` + không `REQUEST_CHANGES` -> chuyển thẳng sang `approved`.
    - Ngược lại -> chuyển sang `awaiting_approval` và trả `requires_human_approval=True` để Agent gọi `ask_question`.
    """
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    state = load_session_state(layout, sid)
    cur_status = str((state.get("stages") or {}).get(stage_id, {}).get("status") or StageStatus.PENDING.value)
    if cur_status == StageStatus.PENDING.value:
        transition_stage(layout, sid=sid, stage=stage_id, target_status=StageStatus.RUNNING.value)

    try:
        res = transition_stage(layout, sid=sid, stage=stage_id, target_status=StageStatus.APPROVED.value)
        res["requires_human_approval"] = False
        res["auto_passed"] = True
        if stage_id == "docs":
            _refresh_docs_harness(layout, res)
        return res
    except SpeedyError as err:
        if err.code != ErrorCode.GATE_REQUIRED:
            raise
        res = transition_stage(layout, sid=sid, stage=stage_id, target_status=StageStatus.AWAITING_APPROVAL.value)
        res["requires_human_approval"] = True
        res["auto_passed"] = False
        res["gate_reason"] = err.message
        return res


def record_gate_decision(
    layout: WorkspaceLayout,
    *,
    sid: str,
    stage: str | int | float,
    decision: str,  # "approve" | "reject" | "abort"
    actor: str,
    interaction_ref: str,
    feedback: Optional[str] = None,
    return_to_stage: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ghi nhận quyết định tại cổng phê duyệt (Stage Gate).
    - Chặn tuyệt đối trường hợp LLM tự gọi approve mà không có bằng chứng tương tác từ con người.
    - Khóa quyết định với `semantic_checksum` hiện tại của artifact.
    """
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    if decision not in {"approve", "reject", "abort"}:
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Quyết định gate không hợp lệ: '{decision}'.")

    if actor.strip().lower() != "human" or not (interaction_ref or "").strip():
        raise SpeedyError(
            ErrorCode.GATE_REQUIRED,
            "Từ chối ghi nhận gate: bắt buộc '--actor human' và '--interaction-ref <mã tham chiếu hỏi đáp>' từ tương tác thực của người dùng.",
            stage=stage_id,
            remediation="Gọi công cụ ask_question để nhận phản hồi thật của User trước khi ghi nhận gate.",
        )

    outcome: Dict[str, Any] = {}

    def _mutator(state: Dict[str, Any]) -> None:
        route: List[str] = state.get("route", [])
        stages: Dict[str, Dict[str, Any]] = state.get("stages", {})
        if stage_id not in stages:
            raise SpeedyError(ErrorCode.INVALID_INPUT, f"Stage '{stage_id}' không tồn tại trong session.")

        st_info = stages[stage_id]
        if decision == "abort":
            st_info["status"] = StageStatus.ABORTED.value
            state["status"] = SessionStatus.ABORTED.value
            state["blocked_reason"] = feedback or "Người dùng chọn Abort tại gate."
            state["next_action"] = "Phiên làm việc đã dừng theo yêu cầu của người dùng."
            outcome.update({"decision": "aborted", "session_status": state["status"], "current_stage": stage_id})
            return

        if st_info.get("status") != StageStatus.AWAITING_APPROVAL.value:
            raise SpeedyError(
                ErrorCode.INVALID_TRANSITION,
                f"Stage '{stage_id}' đang ở trạng thái '{st_info.get('status')}', chưa sẵn sàng tại 'awaiting_approval'.",
                stage=stage_id,
                remediation="Chạy 'state transition --status awaiting_approval' (kèm validate handoff) trước khi duyệt gate.",
            )

        if decision == "approve":
            # Đối chiếu lại artifact trên đĩa không bị sửa trộm sau lúc awaiting_approval
            rel_art = st_info.get("artifact_path")
            live_checksum = st_info.get("artifact_checksum")
            if rel_art:
                art_file = layout.root / rel_art
                if not art_file.is_file():
                    raise SpeedyError(ErrorCode.STALE_ARTIFACT, f"Artifact '{rel_art}' đã bị xóa trước khi duyệt.")
                live_checksum = semantic_checksum(art_file.read_text(encoding="utf-8", errors="replace"))
                if live_checksum != st_info.get("artifact_checksum"):
                    raise SpeedyError(
                        ErrorCode.STALE_ARTIFACT,
                        f"Nội dung '{rel_art}' đã thay đổi sau khi validate; cần validate lại trước khi approve.",
                        stage=stage_id,
                    )

            # Nếu đây là gate của reviewer trong feature/fix, kiểm tra nếu reviewer trả REQUEST_CHANGES thì không thể tiến sang tester!
            if stage_id == "reviewer" and rel_art:
                if state.get("mode") in {FlowMode.FEATURE.value, FlowMode.FIX.value}:
                    rev_text = (layout.root / rel_art).read_text(encoding="utf-8", errors="replace")
                    verdict = extract_reviewer_verdict(rev_text)
                    if verdict == "REQUEST_CHANGES" or verdict is None:
                        raise SpeedyError(
                            ErrorCode.CONTRACT_VIOLATION,
                            "Handoff của Reviewer có verdict REQUEST_CHANGES; không thể chuyển sang Tester, hãy dùng 'gate reject --return-to implementer'.",
                            stage=stage_id,
                        )
                if "implementer" in stages and stages["implementer"].get("status") == StageStatus.AWAITING_APPROVAL.value:
                    stages["implementer"]["status"] = StageStatus.APPROVED.value

            st_info["status"] = StageStatus.APPROVED.value
            st_info["updated_at"] = utc_now_iso()
            state.setdefault("approvals", {})[stage_id] = {
                "actor": "human",
                "interaction_ref": interaction_ref.strip(),
                "artifact_checksum": live_checksum,
                "artifact_revision": st_info.get("revision", 1),
                "feedback": feedback,
                "approved_at": utc_now_iso(),
            }
            idx = route.index(stage_id)
            next_stage = route[idx + 1] if idx + 1 < len(route) else "wrapup"
            state["current_stage"] = next_stage
            state["status"] = SessionStatus.IN_PROGRESS.value
            state["next_action"] = f"Đã duyệt '{stage_id}'; tiếp tục sang stage '{next_stage}'."
            outcome.update(
                {
                    "decision": "approved",
                    "approved_stage": stage_id,
                    "current_stage": next_stage,
                    "session_status": state["status"],
                    "artifact_checksum": live_checksum,
                }
            )
            return

        # decision == "reject" (Request Changes)
        max_attempts = int(state.get("budget", {}).get("max_uow_attempts", 3))
        current_attempts = int(state.get("uow_attempts", 0)) + 1
        state["uow_attempts"] = current_attempts
        state["retry_count"] = int(state.get("retry_count", 0)) + 1

        target_back = normalize_stage_id(return_to_stage) if return_to_stage else (
            "implementer" if stage_id in {"reviewer", "tester"} and "implementer" in stages else stage_id
        )
        if target_back not in stages:
            target_back = stage_id

        back_idx = route.index(target_back)
        stage_idx = route.index(stage_id)
        for reset_st in route[back_idx : stage_idx + 1]:
            stages[reset_st]["status"] = StageStatus.PENDING.value
            state.get("approvals", {}).pop(reset_st, None)

        if current_attempts >= max_attempts:
            stages[target_back]["status"] = StageStatus.BLOCKED.value
            state["status"] = SessionStatus.BLOCKED.value
            state["current_stage"] = target_back
            state["blocked_reason"] = (
                f"Vượt giới hạn số vòng sửa tự động ({current_attempts}/{max_attempts}). Yêu cầu gần nhất: {feedback or 'Request Changes'}"
            )
            state["next_action"] = "Đã hết ngân sách attempt của UoW; chờ người dùng quyết định hướng xử lý."
        else:
            stages[target_back]["status"] = StageStatus.RUNNING.value
            # Nếu lặp lỗi nhiều lần trên architect/reviewer, nâng gợi ý model theo policy
            rec = select_gemini_model(
                target_back,
                high_risk=bool(state.get("high_risk")),
                complex_architecture=bool(state.get("complex_architecture")),
                repeated_failure=current_attempts >= 2,
            )
            stages[target_back]["recommended_model"] = rec["model"]
            state["status"] = SessionStatus.IN_PROGRESS.value
            state["current_stage"] = target_back
            state["next_action"] = (
                f"Thực hiện lại '{target_back}' theo yêu cầu chỉnh sửa (attempt {current_attempts}/{max_attempts}): {feedback or 'Cập nhật theo góp ý'}"
            )

        outcome.update(
            {
                "decision": "request_changes",
                "current_stage": state["current_stage"],
                "session_status": state["status"],
                "uow_attempts": current_attempts,
                "max_uow_attempts": max_attempts,
            }
        )

    gate_ts_box: Dict[str, Optional[str]] = {"ts": None}

    def _mutator_with_ts(state: Dict[str, Any]) -> None:
        gate_ts_box["ts"] = (state.get("stages") or {}).get(stage_id, {}).get("updated_at")
        _mutator(state)

    updated = mutate_session_state_cas(layout, sid, _mutator_with_ts, owner="gate_decision")
    outcome["sid"] = sid
    outcome["state_revision"] = updated["state_revision"]
    outcome["next_action"] = updated["next_action"]
    if updated.get("audit_dir"):
        try:
            from audit import _parse_iso_ms, record_stage_telemetry

            wait_ms: Optional[int] = None
            s_ms = _parse_iso_ms(gate_ts_box.get("ts"))
            e_ms = _parse_iso_ms(utc_now_iso())
            if s_ms is not None and e_ms is not None:
                wait_ms = max(0, e_ms - s_ms)
            model_info = select_gemini_model(stage_id, high_risk=bool(updated.get("high_risk")))
            record_stage_telemetry(
                layout,
                audit_dir=updated["audit_dir"],
                stage=stage_id,
                status=decision,
                model=model_info.get("model"),
                human_wait_ms=wait_ms,
                note=f"gate:{decision}",
                retry_count=int(updated.get("retry_count", 0)),
            )
        except Exception:
            pass
    if decision == "approve" and stage_id == "docs":
        _refresh_docs_harness(layout, outcome)
    return outcome


def register_worker_uow(
    layout: WorkspaceLayout,
    *,
    sid: str,
    uow_id: str,
    stage: str,
    objective: str,
    write_paths: Sequence[str],
) -> Dict[str, Any]:
    """
    Bộ lập lịch UoW gọn nhẹ (mục 3.11):
    - Chặn 2 worker đang chạy ghi đè cùng vùng file (single-writer contract).
    - Cưỡng chế `max_parallel_workers`.
    """
    validate_sid(sid)
    stage_id = normalize_stage_id(stage)
    norm_writes = [p.strip().strip("/") for p in write_paths if p and p.strip()]

    def _overlaps(a: str, b: str) -> bool:
        return a == b or a.startswith(b + "/") or b.startswith(a + "/")

    registered: Dict[str, Any] = {}

    def _mutator(state: Dict[str, Any]) -> None:
        uows: List[Dict[str, Any]] = state.setdefault("uows", [])
        active_uows = [u for u in uows if u.get("status") == "running"]
        max_workers = int(state.get("budget", {}).get("max_parallel_workers", 2))

        if len(active_uows) >= max_workers:
            raise SpeedyError(
                ErrorCode.BUDGET_EXCEEDED,
                f"Số worker chạy song song đã chạm trần ({len(active_uows)}/{max_workers}).",
                remediation="Chờ worker hiện tại hoàn tất trước khi tách thêm worker mới.",
            )

        for active in active_uows:
            for existing_path in active.get("write_paths", []):
                for candidate_path in norm_writes:
                    if _overlaps(existing_path, candidate_path):
                        raise SpeedyError(
                            ErrorCode.SCOPE_VIOLATION,
                            f"Xung đột vùng ghi giữa UoW '{uow_id}' và UoW đang chạy '{active.get('uow_id')}' tại '{candidate_path}'.",
                            remediation="Tách phạm vi file độc lập hoàn toàn hoặc chạy tuần tự một writer duy nhất.",
                        )

        rec = select_gemini_model(stage_id, high_risk=bool(state.get("high_risk")))
        entry = {
            "uow_id": uow_id,
            "stage": stage_id,
            "objective": objective,
            "write_paths": norm_writes,
            "assigned_model": rec["model"],
            "status": "running",
            "started_at": utc_now_iso(),
        }
        uows.append(entry)
        registered.update(entry)

    mutate_session_state_cas(layout, sid, _mutator, owner="uow_scheduler")
    return registered


def complete_worker_uow(
    layout: WorkspaceLayout,
    *,
    sid: str,
    uow_id: str,
    status: str = "completed",
) -> Dict[str, Any]:
    """Đánh dấu một UoW đã hoàn tất hoặc thất bại để giải phóng slot `max_parallel_workers` và vùng ghi."""
    validate_sid(sid)
    if status not in {"completed", "failed"}:
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Trạng thái đóng UoW không hợp lệ: '{status}'.")

    updated_entry: Dict[str, Any] = {}

    def _mutator(state: Dict[str, Any]) -> None:
        uows: List[Dict[str, Any]] = state.get("uows", [])
        for uow in reversed(uows):
            if uow.get("uow_id") == uow_id:
                uow["status"] = status
                uow["completed_at"] = utc_now_iso()
                updated_entry.update(uow)
                return
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Không tìm thấy UoW '{uow_id}' trong session '{sid}'.")

    mutate_session_state_cas(layout, sid, _mutator, owner="uow_scheduler")
    return updated_entry
