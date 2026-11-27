"""
audit.py — Quản lý Audit 4 lớp trung thực cho Speedy DevKit trên Antigravity IDE:
- 01-input-context.json
- 02-behavior-trace.json
- 03-verification-results.json
- 04-cost-time.json

Nguyên tắc bất biến:
- Thiếu nguồn đo token/chi phí -> giữ `null` và `source: "not_measured"`, liệt kê rõ `missing_metrics`.
- Bảng giá Gemini Pro chỉ dùng làm chi phí quy đổi tham khảo (`public_api_price_list`); model chưa có giá -> `null`.
- Không cộng trùng lặp usage của tiến trình cha và subagent con khi đã có tổng hợp.
- Tự động che mọi khóa nhạy cảm (`[REDACTED]`), không lưu raw prompt hay chain-of-thought.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts import ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope, sanitize_slug, validate_sid
from storage import atomic_write_json, mutate_session_state_cas, read_json_safe, utc_now_iso

AUDIT_FILENAMES = (
    "01-input-context.json",
    "02-behavior-trace.json",
    "03-verification-results.json",
    "04-cost-time.json",
)

MISSING_USAGE_METRICS = [
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
    "model_cost",
    "total_estimated_cost",
]

_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|cookie|passwd|password|secret|token|pat|credential)",
    re.IGNORECASE,
)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|passwd|password|secret|token|pat|credential)(\s*[=:]\s*)([^\s,;\"']+)"
)
_METRIC_ALLOW_KEYS = frozenset(MISSING_USAGE_METRICS) | {
    "cached_tokens",
    "max_tokens",
    "max_measured_tokens",
    "known_tokens",
}


def _read_env_map(layout: WorkspaceLayout) -> Dict[str, str]:
    env_file = layout.runtime_root / ".env"
    values: Dict[str, str] = {}
    if not env_file.is_file():
        return values
    for raw in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def is_audit_enabled(layout: WorkspaceLayout) -> bool:
    raw = os.environ.get("IS_AUDIT", _read_env_map(layout).get("IS_AUDIT", "1"))
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def sanitize_text(value: Any, max_len: int = 500) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    cleaned = str(value).replace("\r", " ").replace("\n", " ")
    cleaned = _SECRET_ASSIGN_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", cleaned)
    return cleaned[: max_len - 3] + "..." if len(cleaned) > max_len else cleaned


def redact_payload(data: Any) -> Any:
    if isinstance(data, dict):
        out: Dict[str, Any] = {}
        for k, v in data.items():
            safe_k = str(sanitize_text(k, max_len=120))
            if k not in _METRIC_ALLOW_KEYS and _SECRET_KEY_RE.search(str(k)):
                out[safe_k] = "[REDACTED]"
            else:
                out[safe_k] = redact_payload(v)
        return out
    if isinstance(data, list):
        return [redact_payload(item) for item in data]
    return sanitize_text(data)


def _normalize_model_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def _load_pricing(layout: WorkspaceLayout) -> Optional[Dict[str, Any]]:
    for cand in (
        layout.runtime_root / "config" / "model-pricing.json",
        layout.speedy_dir / "config" / "model-pricing.json",
    ):
        if cand.is_file():
            try:
                data = read_json_safe(cand)
                if isinstance(data.get("models"), dict):
                    return data
            except SpeedyError:
                continue
    return None


def _lookup_model_price(model_name: str, pricing: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    norm = _normalize_model_key(model_name)
    models = pricing.get("models", {})
    if norm in models:
        return models[norm]
    for key, entry in models.items():
        if not isinstance(entry, dict):
            continue
        aliases = {_normalize_model_key(a) for a in entry.get("aliases", [])}
        aliases.add(_normalize_model_key(entry.get("display_name", "")))
        aliases.add(_normalize_model_key(key))
        if norm in aliases:
            return entry
    return None


def _compute_reference_cost(
    usage_items: List[Dict[str, Any]],
    pricing: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Tính chi phí quy đổi tham khảo từ số đo token thật:
    - Bỏ qua các bản ghi con có `included_in_parent=True` để không cộng trùng hai lần.
    - Nếu có bất kỳ model nào không có trong bảng giá -> trả `total_cost=None` (không đoán bằng model khác).
    """
    if not pricing or not usage_items:
        return {"total_cost": None, "unpriced_models": [], "fully_priced": False}

    total = 0.0
    unpriced: List[str] = []
    counted_any = False

    for item in usage_items:
        if item.get("included_in_parent"):
            continue
        model = str(item.get("model") or "unknown")
        price = _lookup_model_price(model, pricing)
        if price is None:
            if model not in unpriced:
                unpriced.append(model)
            continue
        in_tok = int(item.get("input_tokens") or 0)
        cached_tok = int(item.get("cached_input_tokens") or 0)
        out_tok = int(item.get("output_tokens") or 0)
        fresh_in = max(in_tok - cached_tok, 0)
        total += (fresh_in / 1_000_000) * float(price.get("input", 0))
        total += (cached_tok / 1_000_000) * float(price.get("cached_input", 0))
        total += (out_tok / 1_000_000) * float(price.get("output", 0))
        counted_any = True

    fully_priced = counted_any and len(unpriced) == 0
    return {
        "total_cost": round(total, 6) if fully_priced else None,
        "unpriced_models": unpriced,
        "fully_priced": fully_priced,
    }


def _git_head_and_branch(root: Path) -> Dict[str, Optional[str]]:
    def _run(*args: str) -> Optional[str]:
        try:
            proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=4)
            return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None
        except Exception:
            return None

    return {"branch": _run("branch", "--show-current"), "commit": _run("rev-parse", "HEAD")}


def _parse_iso_ms(ts: Optional[str]) -> Optional[int]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def start_audit(
    layout: WorkspaceLayout,
    *,
    sid: str,
    slug: str,
    goal: str,
    mode: str = "feature",
    policy: str = "strict",
    command_ref: Optional[str] = None,
    prompt_ref: Optional[str] = None,
    budget: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    validate_sid(sid)
    if not is_audit_enabled(layout):
        return {"enabled": False, "audit_dir": None, "files": []}

    today = sid[:10]
    safe_slug = sanitize_slug(slug)
    run_dir = layout.audit_dir / f"{today}-{sid}-{safe_slug}"
    run_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    git_meta = _git_head_and_branch(layout.root)

    f01 = {
        "schema_version": "2.0",
        "layer": "input_context",
        "created_at": now,
        "task_identity": redact_payload(
            {
                "task_id": safe_slug,
                "run_id": sid,
                "started_at": now,
                "ended_at": None,
                "workspace": str(layout.root),
                "branch": git_meta["branch"],
                "git_commit_before": git_meta["commit"],
                "git_commit_after": None,
                "task_type": mode,
                "command_ref": sanitize_text(command_ref, max_len=120) if command_ref else None,
                "prompt_ref": sanitize_text(prompt_ref, max_len=200) if prompt_ref else None,
                "sanitized_task_description": sanitize_text(goal, max_len=800),
            }
        ),
        "ai_agent_configuration": {
            "provider": "gemini-pro-antigravity",
            "ide": "Antigravity IDE",
            "gate_policy": policy,
            "models_by_agent": {},
            "budget": budget or {},
        },
        "sanitization_policy": {
            "chain_of_thought_logged": False,
            "secrets_redacted": True,
        },
    }

    f02 = {
        "schema_version": "2.0",
        "layer": "behavior_trace",
        "created_at": now,
        "execution_trace": {
            "turn_count": None,
            "tool_call_count": None,
            "steps": [],
            "events": [
                {
                    "timestamp": now,
                    "category": "audit_start",
                    "agent": "orchestrator",
                    "enforcement_level": "workflow_enforced",
                    "summary": "Initialized 4-layer Speedy audit.",
                }
            ],
            "retry_count": 0,
            "loop_redundant_action_detected": False,
        },
    }

    f03 = {
        "schema_version": "2.0",
        "layer": "verification_results",
        "created_at": now,
        "repository_changes": {
            "change_measurement_status": "not_measured",
            "files_changed": None,
            "changed_file_paths": [],
        },
        "quality_verification": {
            "build_status": "not_available",
            "unit_test_result": {"status": "not_available", "command": None},
            "acceptance_criteria_passed": 0,
            "acceptance_criteria_total": 0,
            "test_laundering_suspicious": False,
        },
        "outcome_failure_analysis": {
            "outcome": "partial",
            "completion_level": "claimed",
            "remaining_work": "Audit initialized; awaiting verification evidence.",
        },
    }

    f04 = {
        "schema_version": "2.0",
        "layer": "cost_time",
        "created_at": now,
        "usage_cost": {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "total_tokens": None,
            "total_estimated_cost": None,
            "currency_pricing_source": None,
            "cost_basis": None,
            "unpriced_models": [],
            "accounting_semantics": "exclude_included_in_parent_to_prevent_double_count",
            "source": "not_measured",
            "missing_metrics": list(MISSING_USAGE_METRICS),
        },
        "time_performance": {
            "wall_time_ms": None,
            "human_wait_ms": None,
            "model_time_ms": None,
            "tool_time_ms": None,
            "total_wall_clock_duration_ms": None,
        },
        "final_summary": {
            "task_id": safe_slug,
            "run_id": sid,
            "task_type": mode,
            "outcome": "partial",
            "completion_level": "claimed",
            "acceptance_criteria_passed_total": "0/0",
            "build_test_security_status": "not_available",
            "total_duration_ms": None,
            "files_changed": None,
            "missing_metrics": list(MISSING_USAGE_METRICS),
        },
    }

    rel_files: List[str] = []
    for fname, payload in zip(AUDIT_FILENAMES, (f01, f02, f03, f04)):
        fpath = run_dir / fname
        atomic_write_json(fpath, payload)
        rel_files.append(fpath.relative_to(layout.root).as_posix())

    rel_dir = run_dir.relative_to(layout.root).as_posix()
    # Liên kết vào session state nếu session tồn tại
    try:
        mutate_session_state_cas(layout, sid, lambda st: st.update({"audit_dir": rel_dir}), owner="audit_start")
    except SpeedyError:
        pass

    return {"enabled": True, "sid": sid, "audit_dir": rel_dir, "files": rel_files}


def record_audit_event(
    layout: WorkspaceLayout,
    *,
    audit_dir: str,
    agent: str,
    category: str = "stage_event",
    model: Optional[str] = None,
    summary: Optional[str] = None,
    enforcement_level: str = "workflow_enforced",
    human_wait_ms: Optional[int] = None,
    model_time_ms: Optional[int] = None,
    tool_time_ms: Optional[int] = None,
) -> Dict[str, Any]:
    if not is_audit_enabled(layout):
        return {"logged": False, "reason": "audit_disabled"}

    dir_path = resolve_within_scope(layout.root, audit_dir)
    trace_path = dir_path / AUDIT_FILENAMES[1]
    input_path = dir_path / AUDIT_FILENAMES[0]

    trace_data = read_json_safe(trace_path)
    events = trace_data.setdefault("execution_trace", {}).setdefault("events", [])
    ev: Dict[str, Any] = {
        "timestamp": utc_now_iso(),
        "category": sanitize_text(category, max_len=60),
        "agent": sanitize_text(agent, max_len=60),
        "enforcement_level": sanitize_text(enforcement_level, max_len=40),
    }
    if model:
        ev["model"] = sanitize_text(model, max_len=80)
    if summary:
        ev["summary"] = sanitize_text(summary, max_len=300)
    for key_ms, val_ms in (
        ("human_wait_ms", human_wait_ms),
        ("model_time_ms", model_time_ms),
        ("tool_time_ms", tool_time_ms),
    ):
        if val_ms is not None and int(val_ms) >= 0:
            ev[key_ms] = int(val_ms)
    events.append(ev)
    atomic_write_json(trace_path, trace_data)

    if model and input_path.is_file():
        inp_data = read_json_safe(input_path)
        inp_data.setdefault("ai_agent_configuration", {}).setdefault("models_by_agent", {})[agent] = str(
            sanitize_text(model, max_len=80)
        )
        atomic_write_json(input_path, inp_data)

    return {"logged": True, "audit_dir": audit_dir, "event_count": len(events)}


def finalize_audit(
    layout: WorkspaceLayout,
    *,
    audit_dir: str,
    outcome: str = "partial",
    completion_level: str = "claimed",
    ac_passed: int = 0,
    ac_total: int = 0,
    build_status: str = "not_available",
    files_changed: Optional[int] = None,
    measured_usage: Optional[List[Dict[str, Any]]] = None,
    usage_source: Optional[str] = None,
) -> Dict[str, Any]:
    if not is_audit_enabled(layout):
        return {"finalized": False, "reason": "audit_disabled"}

    dir_path = resolve_within_scope(layout.root, audit_dir)
    f01 = read_json_safe(dir_path / AUDIT_FILENAMES[0])
    f02 = read_json_safe(dir_path / AUDIT_FILENAMES[1])
    f03 = read_json_safe(dir_path / AUDIT_FILENAMES[2])
    f04 = read_json_safe(dir_path / AUDIT_FILENAMES[3])

    now = utc_now_iso()
    f01["task_identity"]["ended_at"] = now
    git_meta = _git_head_and_branch(layout.root)
    f01["task_identity"]["git_commit_after"] = git_meta["commit"]

    start_ms = _parse_iso_ms(f01.get("task_identity", {}).get("started_at"))
    end_ms = _parse_iso_ms(now)
    wall_ms = max(0, end_ms - start_ms) if (start_ms is not None and end_ms is not None) else None

    events = f02.get("execution_trace", {}).get("events", [])
    sum_human = [int(e["human_wait_ms"]) for e in events if isinstance(e.get("human_wait_ms"), int)]
    sum_model = [int(e["model_time_ms"]) for e in events if isinstance(e.get("model_time_ms"), int)]
    sum_tool = [int(e["tool_time_ms"]) for e in events if isinstance(e.get("tool_time_ms"), int)]

    time_perf = f04["time_performance"]
    time_perf["wall_time_ms"] = wall_ms
    time_perf["total_wall_clock_duration_ms"] = wall_ms
    time_perf["human_wait_ms"] = sum(sum_human) if sum_human else None
    time_perf["model_time_ms"] = sum(sum_model) if sum_model else None
    time_perf["tool_time_ms"] = sum(sum_tool) if sum_tool else None

    usage_cost = f04["usage_cost"]
    if measured_usage and usage_source:
        non_dup = [u for u in measured_usage if not u.get("included_in_parent")]
        in_tok = sum(int(u.get("input_tokens") or 0) for u in non_dup)
        cached_tok = sum(int(u.get("cached_input_tokens") or 0) for u in non_dup)
        out_tok = sum(int(u.get("output_tokens") or 0) for u in non_dup)
        usage_cost["input_tokens"] = in_tok
        usage_cost["cached_input_tokens"] = cached_tok
        usage_cost["output_tokens"] = out_tok
        usage_cost["total_tokens"] = in_tok + out_tok
        usage_cost["source"] = sanitize_text(usage_source, max_len=80)
        usage_cost["missing_metrics"] = [
            m for m in MISSING_USAGE_METRICS if m not in {"input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"}
        ]

        pricing = _load_pricing(layout)
        cost_res = _compute_reference_cost(non_dup, pricing)
        usage_cost["unpriced_models"] = cost_res["unpriced_models"]
        usage_cost["total_estimated_cost"] = cost_res["total_cost"]
        if cost_res["fully_priced"]:
            usage_cost["currency_pricing_source"] = ".speedy/config/model-pricing.json"
            usage_cost["cost_basis"] = "public_api_price_list"
            usage_cost["missing_metrics"] = [
                m for m in usage_cost["missing_metrics"] if m not in {"model_cost", "total_estimated_cost"}
            ]
        f02["execution_trace"]["steps"] = [
            {
                "step_index": i + 1,
                "agent": sanitize_text(u.get("agent"), max_len=60),
                "model": sanitize_text(u.get("model"), max_len=80),
                "input_tokens": int(u.get("input_tokens") or 0),
                "cached_tokens": int(u.get("cached_input_tokens") or 0),
                "output_tokens": int(u.get("output_tokens") or 0),
                "included_in_parent": bool(u.get("included_in_parent", False)),
            }
            for i, u in enumerate(measured_usage)
        ]
    else:
        usage_cost["source"] = "not_measured"

    if files_changed is not None:
        f03["repository_changes"]["change_measurement_status"] = "measured"
        f03["repository_changes"]["files_changed"] = int(files_changed)

    f03["quality_verification"]["build_status"] = build_status
    f03["quality_verification"]["acceptance_criteria_passed"] = int(ac_passed)
    f03["quality_verification"]["acceptance_criteria_total"] = int(ac_total)
    f03["outcome_failure_analysis"]["outcome"] = outcome
    f03["outcome_failure_analysis"]["completion_level"] = completion_level
    f03["outcome_failure_analysis"]["remaining_work"] = None if outcome == "success" else "Pending verification or follow-up."

    summary = f04["final_summary"]
    summary["outcome"] = outcome
    summary["completion_level"] = completion_level
    summary["acceptance_criteria_passed_total"] = f"{ac_passed}/{ac_total}"
    summary["build_test_security_status"] = build_status
    summary["total_duration_ms"] = wall_ms
    summary["files_changed"] = f03["repository_changes"]["files_changed"]
    summary["missing_metrics"] = usage_cost["missing_metrics"]

    for fname, payload in zip(AUDIT_FILENAMES, (f01, f02, f03, f04)):
        atomic_write_json(dir_path / fname, payload)

    return {
        "finalized": True,
        "audit_dir": audit_dir,
        "outcome": outcome,
        "completion_level": completion_level,
        "usage_source": usage_cost["source"],
        "total_tokens": usage_cost["total_tokens"],
        "total_estimated_cost": usage_cost["total_estimated_cost"],
        "unpriced_models": usage_cost["unpriced_models"],
    }
