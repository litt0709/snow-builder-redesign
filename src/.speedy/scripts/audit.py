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
REVIEW_FILENAME = "05-optimization-review.json"

STAGE_PROMPT_REFS: Dict[str, str] = {
    "bootstrap": ".speedy/flows/flow.md",
    "root_cause": ".speedy/flows/fix-flow.md",
    "analyst": ".speedy/roles/analyst.md",
    "architect": ".speedy/roles/architect.md",
    "implementer": ".speedy/roles/implementer.md",
    "reviewer": ".speedy/roles/reviewer.md",
    "tester": ".speedy/roles/tester.md",
    "docs": ".speedy/roles/docs-manager.md",
    "verify_report": ".speedy/flows/verify-flow.md",
    "wrapup": ".speedy/flows/feature-flow.md",
    "audit": ".speedy/roles/audit.md",
}

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
    "token_reduction_pct",
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
    # Prefix fallback cho biến thể hậu tố tốc độ/effort (vd: gemini-4-neon-medium -> gemini-4-neon)
    for key, entry in models.items():
        if not isinstance(entry, dict):
            continue
        for alias in entry.get("aliases", []):
            norm_a = _normalize_model_key(alias)
            if norm_a.startswith("gemini-") and norm.startswith(norm_a + "-"):
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


_INTERNAL_CHANGE_PREFIXES = (
    ".speedy/",
    ".agents/",
    "AGENTS.md",
    "ai-workspace/",
    "sessions/",
    "logs/",
    "reports/",
    "plans/",
    "state/",
)


def _measure_git_changed_files(root: Path, commit_before: Optional[str] = None) -> Optional[List[str]]:
    """Đo danh sách file mã nguồn/tài liệu ứng dụng thay đổi qua git (bỏ qua artifact nội bộ DevKit)."""
    try:
        chk = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if chk.returncode != 0 or chk.stdout.strip().lower() != "true":
            return None
    except Exception:
        return None

    changed: set[str] = set()
    try:
        if commit_before:
            diff_proc = subprocess.run(
                ["git", "diff", "--name-only", f"{commit_before}..HEAD"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=4,
            )
            if diff_proc.returncode == 0:
                for line in diff_proc.stdout.splitlines():
                    p = line.strip()
                    if p:
                        changed.add(p)
        st_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=4,
        )
        if st_proc.returncode == 0:
            for line in st_proc.stdout.splitlines():
                if len(line) > 3:
                    raw_path = line[3:].strip()
                    if " -> " in raw_path:
                        raw_path = raw_path.split(" -> ", 1)[1].strip()
                    raw_path = raw_path.strip('"')
                    if raw_path:
                        changed.add(raw_path)
    except Exception:
        return None

    filtered = sorted(
        p for p in changed if not any(p == pref.rstrip("/") or p.startswith(pref) for pref in _INTERNAL_CHANGE_PREFIXES)
    )
    return filtered


def _parse_iso_ms(ts: Optional[str]) -> Optional[int]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except ValueError:
        return None


def collect_antigravity_transcript_usage(
    *,
    sid: str,
    started_at: Optional[str],
    ended_at: Optional[str] = None,
    brain_dir: Optional[Path] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Tự động đọc số đo token thật từ file `transcript.jsonl` chuẩn của Antigravity IDE
    (`~/.gemini/antigravity/brain/<conversation-id>/.system_generated/logs/transcript.jsonl`):
    - Chỉ khớp chính xác hội thoại chứa `sid` và cộng các lượt `PLANNER_RESPONSE` trong khung giờ `[started_at, ended_at]`.
    - Nếu không tìm thấy log (vd: chạy CI/headless/test) -> trả `None` (tuyệt đối không bịa số).
    """
    if not sid:
        return None
    env_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    root_brain = brain_dir or (Path(env_dir).expanduser() if env_dir else (Path.home() / ".gemini" / "antigravity" / "brain"))
    if not root_brain.is_dir():
        return None

    start_ms = _parse_iso_ms(started_at)
    end_ms = _parse_iso_ms(ended_at) if ended_at else None
    min_mtime_s = (start_ms / 1000.0 - 120.0) if start_ms is not None else 0.0

    matched_transcript: Optional[Path] = None
    try:
        candidates = sorted(
            root_brain.glob("*/.system_generated/logs/transcript.jsonl"),
            key=lambda p: p.stat().st_mtime if p.is_file() else 0.0,
            reverse=True,
        )
    except OSError:
        return None

    for cand in candidates[:40]:
        try:
            if not cand.is_file():
                continue
            if start_ms is not None and cand.stat().st_mtime < min_mtime_s:
                continue
            raw_text = cand.read_text(encoding="utf-8", errors="ignore")
            if sid in raw_text:
                matched_transcript = cand
                break
        except OSError:
            continue

    if matched_transcript is None:
        return None

    import json

    window_start = (start_ms - 15_000) if start_ms is not None else None
    window_end = (end_ms + 15_000) if end_ms is not None else None
    by_model: Dict[str, Dict[str, Any]] = {}

    try:
        for line in matched_transcript.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "PLANNER_RESPONSE" not in line or "input_tokens" not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "PLANNER_RESPONSE":
                continue
            ts_ms = _parse_iso_ms(obj.get("created_at"))
            if ts_ms is not None:
                if window_start is not None and ts_ms < window_start:
                    continue
                if window_end is not None and ts_ms > window_end:
                    continue
            fresh_in = int(obj.get("input_tokens") or 0)
            cached_in = int(obj.get("cache_read_tokens") or 0)
            out_tok = int(obj.get("output_tokens") or 0)
            if fresh_in == 0 and cached_in == 0 and out_tok == 0:
                continue
            model_name = str(obj.get("model") or "unknown")
            bucket = by_model.setdefault(
                model_name,
                {
                    "agent": "antigravity",
                    "model": model_name,
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "request_count": 0,
                },
            )
            # Antigravity transcript tách riêng input_tokens (fresh) và cache_read_tokens (cached)
            bucket["input_tokens"] += fresh_in + cached_in
            bucket["cached_input_tokens"] += cached_in
            bucket["output_tokens"] += out_tok
            bucket["request_count"] += 1
    except OSError:
        return None

    return list(by_model.values()) if by_model else None


def collect_antigravity_prompt_trace(
    *,
    sid: str,
    started_at: Optional[str],
    ended_at: Optional[str] = None,
    brain_dir: Optional[Path] = None,
    max_items: int = 10,
) -> List[str]:
    """
    Trích xuất tối đa `max_items` lệnh/prompt của User (đã sanitize secret) trong khung giờ phiên
    từ `transcript.jsonl` của Antigravity IDE để phục vụ `/audit` review cách viết command.
    """
    if not sid:
        return []
    env_dir = os.environ.get("ANTIGRAVITY_BRAIN_DIR")
    root_brain = brain_dir or (Path(env_dir).expanduser() if env_dir else (Path.home() / ".gemini" / "antigravity" / "brain"))
    if not root_brain.is_dir():
        return []

    start_ms = _parse_iso_ms(started_at)
    end_ms = _parse_iso_ms(ended_at) if ended_at else None
    min_mtime_s = (start_ms / 1000.0 - 120.0) if start_ms is not None else 0.0

    matched_transcript: Optional[Path] = None
    try:
        candidates = sorted(
            root_brain.glob("*/.system_generated/logs/transcript.jsonl"),
            key=lambda p: p.stat().st_mtime if p.is_file() else 0.0,
            reverse=True,
        )
    except OSError:
        return []

    for cand in candidates[:40]:
        try:
            if not cand.is_file():
                continue
            if start_ms is not None and cand.stat().st_mtime < min_mtime_s:
                continue
            if sid in cand.read_text(encoding="utf-8", errors="ignore"):
                matched_transcript = cand
                break
        except OSError:
            continue

    if matched_transcript is None:
        return []

    import json

    window_start = (start_ms - 60_000) if start_ms is not None else None
    window_end = (end_ms + 15_000) if end_ms is not None else None
    prompts: List[str] = []
    seen = set()

    try:
        for line in matched_transcript.read_text(encoding="utf-8", errors="ignore").splitlines():
            if "USER_INPUT" not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "USER_INPUT":
                continue
            ts_ms = _parse_iso_ms(obj.get("created_at"))
            if ts_ms is not None:
                if window_start is not None and ts_ms < window_start:
                    continue
                if window_end is not None and ts_ms > window_end:
                    continue
            raw_content = obj.get("content")
            if not raw_content:
                continue
            cleaned = str(sanitize_text(raw_content, max_len=240)).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                prompts.append(cleaned)
                if len(prompts) >= max_items:
                    break
    except OSError:
        return []
    return prompts


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


def record_stage_telemetry(
    layout: WorkspaceLayout,
    *,
    audit_dir: str,
    stage: str,
    status: str,
    model: Optional[str] = None,
    duration_ms: Optional[int] = None,
    human_wait_ms: Optional[int] = None,
    note: Optional[str] = None,
    retry_count: Optional[int] = None,
    prompt_ref: Optional[str] = None,
    prompt_excerpt: Optional[str] = None,
) -> Dict[str, Any]:
    """Tự động ghi telemetry stage (event + step + model + prompt_ref) từ lifecycle/gate mà không cần LLM gọi thủ công."""
    if not is_audit_enabled(layout):
        return {"logged": False, "reason": "audit_disabled"}

    dir_path = resolve_within_scope(layout.root, audit_dir)
    trace_path = dir_path / AUDIT_FILENAMES[1]
    input_path = dir_path / AUDIT_FILENAMES[0]
    if not trace_path.is_file():
        return {"logged": False, "reason": "trace_missing"}

    trace_data = read_json_safe(trace_path)
    exec_trace = trace_data.setdefault("execution_trace", {})
    events = exec_trace.setdefault("events", [])
    steps = exec_trace.setdefault("steps", [])
    resolved_prompt_ref = prompt_ref or STAGE_PROMPT_REFS.get(stage)

    now = utc_now_iso()
    ev: Dict[str, Any] = {
        "timestamp": now,
        "category": "stage_transition",
        "agent": sanitize_text(stage, max_len=60),
        "enforcement_level": "runtime_enforced",
        "summary": sanitize_text(note or f"stage:{stage}->{status}", max_len=300),
    }
    if model:
        ev["model"] = sanitize_text(model, max_len=80)
    if resolved_prompt_ref:
        ev["prompt_ref"] = sanitize_text(resolved_prompt_ref, max_len=160)
    if duration_ms is not None and int(duration_ms) >= 0:
        ev["model_time_ms"] = int(duration_ms)
    if human_wait_ms is not None and int(human_wait_ms) >= 0:
        ev["human_wait_ms"] = int(human_wait_ms)
    events.append(ev)

    exec_trace["turn_count"] = int(exec_trace.get("turn_count") or 0) + 1
    if retry_count is not None:
        exec_trace["retry_count"] = int(retry_count)

    if status in {"approved", "awaiting_approval", "failed"} or human_wait_ms is not None:
        step_entry: Dict[str, Any] = {
            "step_index": len(steps) + 1,
            "agent": sanitize_text(stage, max_len=60),
            "model": sanitize_text(model, max_len=80) if model else None,
            "duration_ms": int(duration_ms) if (duration_ms is not None and int(duration_ms) >= 0) else None,
            "note": sanitize_text(note or status, max_len=160),
        }
        if resolved_prompt_ref:
            step_entry["prompt_ref"] = sanitize_text(resolved_prompt_ref, max_len=160)
        if prompt_excerpt:
            step_entry["prompt_excerpt"] = sanitize_text(prompt_excerpt, max_len=280)
        steps.append(step_entry)

    atomic_write_json(trace_path, trace_data)

    if model and input_path.is_file():
        inp_data = read_json_safe(input_path)
        inp_data.setdefault("ai_agent_configuration", {}).setdefault("models_by_agent", {})[stage] = str(
            sanitize_text(model, max_len=80)
        )
        atomic_write_json(input_path, inp_data)

    return {"logged": True, "stage": stage, "status": status}


def sync_verification_to_audit(
    layout: WorkspaceLayout,
    *,
    audit_dir: str,
    verify_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Tự động đồng bộ kết quả từ `verify run` sang `03-verification-results.json` và `02-behavior-trace.json`."""
    if not is_audit_enabled(layout):
        return {"synced": False, "reason": "audit_disabled"}

    dir_path = resolve_within_scope(layout.root, audit_dir)
    trace_path = dir_path / AUDIT_FILENAMES[1]
    ver_path = dir_path / AUDIT_FILENAMES[2]
    if not ver_path.is_file():
        return {"synced": False, "reason": "verification_file_missing"}

    f03 = read_json_safe(ver_path)
    qual = f03.setdefault("quality_verification", {})
    layers = verify_summary.get("layers") or []
    total_tool_ms = 0
    executed_checks = 0

    for layer in layers:
        if not isinstance(layer, dict):
            continue
        lname = str(layer.get("layer") or "")
        lstatus = str(layer.get("status") or "NOT_APPLICABLE")
        dur = int(layer.get("duration_ms") or 0)
        if lstatus != "NOT_APPLICABLE":
            total_tool_ms += max(0, dur)
            executed_checks += 1
        cmd = layer.get("command")
        cmd_str = " ".join(str(x) for x in cmd) if isinstance(cmd, list) else (str(cmd) if cmd else None)
        if lname == "unit_integration" and lstatus != "NOT_APPLICABLE":
            qual["unit_test_result"] = {"status": lstatus.lower(), "command": sanitize_text(cmd_str, max_len=240)}
        elif lname == "build" and lstatus != "NOT_APPLICABLE":
            qual["build_status"] = lstatus.lower()

    qual["test_laundering_suspicious"] = bool((verify_summary.get("test_laundering") or {}).get("suspicious"))
    atomic_write_json(ver_path, f03)

    if trace_path.is_file():
        f02 = read_json_safe(trace_path)
        exec_trace = f02.setdefault("execution_trace", {})
        exec_trace["tool_call_count"] = int(exec_trace.get("tool_call_count") or 0) + max(1, executed_checks)
        exec_trace.setdefault("events", []).append(
            {
                "timestamp": utc_now_iso(),
                "category": "verification_run",
                "agent": "tester",
                "enforcement_level": "runtime_enforced",
                "tool_time_ms": total_tool_ms,
                "summary": f"verify:{verify_summary.get('overall_status')} ({executed_checks} checks)",
            }
        )
        atomic_write_json(trace_path, f02)

    return {"synced": True, "tool_time_ms": total_tool_ms, "checks": executed_checks}


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
    if not f01["task_identity"].get("user_commands_log"):
        cmd_log = collect_antigravity_prompt_trace(
            sid=str(f01.get("task_identity", {}).get("run_id") or ""),
            started_at=f01.get("task_identity", {}).get("started_at"),
            ended_at=now,
        )
        if cmd_log:
            f01["task_identity"]["user_commands_log"] = cmd_log

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
    if not measured_usage:
        sid_val = str(f01.get("task_identity", {}).get("run_id") or "")
        auto_usage = collect_antigravity_transcript_usage(
            sid=sid_val,
            started_at=f01.get("task_identity", {}).get("started_at"),
            ended_at=now,
        )
        if auto_usage:
            measured_usage = auto_usage
            usage_source = "antigravity_transcript"

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
        if not f02["execution_trace"].get("steps"):
            f02["execution_trace"]["steps"] = [
                {
                    "step_index": i + 1,
                    "agent": sanitize_text(u.get("agent"), max_len=60),
                    "model": sanitize_text(u.get("model"), max_len=80),
                    "input_tokens": int(u.get("input_tokens") or 0),
                    "cached_tokens": int(u.get("cached_input_tokens") or 0),
                    "output_tokens": int(u.get("output_tokens") or 0),
                    "request_count": int(u.get("request_count") or 1),
                    "included_in_parent": bool(u.get("included_in_parent", False)),
                }
                for i, u in enumerate(measured_usage)
            ]
    else:
        usage_cost["source"] = "not_measured"

    if files_changed is not None:
        f03["repository_changes"]["change_measurement_status"] = "measured"
        f03["repository_changes"]["files_changed"] = int(files_changed)
    else:
        auto_changed = _measure_git_changed_files(layout.root, f01.get("task_identity", {}).get("git_commit_before"))
        if auto_changed is not None:
            f03["repository_changes"]["change_measurement_status"] = "measured"
            f03["repository_changes"]["files_changed"] = len(auto_changed)
            f03["repository_changes"]["changed_file_paths"] = auto_changed[:50]

    existing_build = f03.get("quality_verification", {}).get("build_status")
    effective_build = build_status if build_status != "not_available" else (existing_build or "not_available")
    f03["quality_verification"]["build_status"] = effective_build
    existing_ac_total = int(f03.get("quality_verification", {}).get("acceptance_criteria_total") or 0)
    if ac_total > 0 or existing_ac_total == 0:
        f03["quality_verification"]["acceptance_criteria_passed"] = int(ac_passed)
        f03["quality_verification"]["acceptance_criteria_total"] = int(ac_total)
    eff_ac_passed = int(f03["quality_verification"]["acceptance_criteria_passed"])
    eff_ac_total = int(f03["quality_verification"]["acceptance_criteria_total"])
    f03["outcome_failure_analysis"]["outcome"] = outcome
    f03["outcome_failure_analysis"]["completion_level"] = completion_level
    f03["outcome_failure_analysis"]["remaining_work"] = None if outcome == "success" else "Pending verification or follow-up."

    summary = f04["final_summary"]
    summary["outcome"] = outcome
    summary["completion_level"] = completion_level
    summary["acceptance_criteria_passed_total"] = f"{eff_ac_passed}/{eff_ac_total}"
    summary["build_test_security_status"] = effective_build
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


def _clamp_pct(val: Any) -> int:
    try:
        return max(0, min(95, int(round(float(val)))))
    except (TypeError, ValueError):
        return 0


def _norm_impact(raw: Any) -> Dict[str, int]:
    d = raw if isinstance(raw, dict) else {}
    return {
        "accuracy_gain_pct": _clamp_pct(d.get("accuracy_gain_pct")),
        "speed_gain_pct": _clamp_pct(d.get("speed_gain_pct")),
        "token_reduction_pct": _clamp_pct(d.get("token_reduction_pct")),
    }


def save_audit_review(
    layout: WorkspaceLayout,
    *,
    audit_dir: str,
    review_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Lưu báo cáo tối ưu hóa Prompt & Context (`05-optimization-review.json`) đã sanitize & chuẩn hóa."""
    if not is_audit_enabled(layout):
        return {"saved": False, "reason": "audit_disabled"}
    if not isinstance(review_payload, dict):
        raise SpeedyError(ErrorCode.INVALID_INPUT, "review_payload phải là JSON object.")

    dir_path = resolve_within_scope(layout.root, audit_dir)
    if not dir_path.is_dir():
        raise SpeedyError(ErrorCode.NOT_FOUND, f"Thư mục audit không tồn tại: {audit_dir}", path=audit_dir)

    user_reviews: List[Dict[str, Any]] = []
    for item in (review_payload.get("user_command_reviews") or [])[:10]:
        if not isinstance(item, dict):
            continue
        user_reviews.append(
            {
                "original_command": sanitize_text(item.get("original_command") or "", max_len=280),
                "issue": sanitize_text(item.get("issue") or "", max_len=360),
                "improved_command": sanitize_text(item.get("improved_command") or "", max_len=360),
                "impact": _norm_impact(item.get("impact")),
            }
        )

    agent_reviews: List[Dict[str, Any]] = []
    for item in (review_payload.get("agent_prompt_reviews") or [])[:15]:
        if not isinstance(item, dict):
            continue
        prio = str(item.get("priority") or "medium").strip().lower()
        if prio not in {"high", "medium", "low"}:
            prio = "medium"
        agent_name = str(sanitize_text(item.get("agent") or "general", max_len=60))
        agent_reviews.append(
            {
                "agent": agent_name,
                "prompt_ref": sanitize_text(item.get("prompt_ref") or STAGE_PROMPT_REFS.get(agent_name) or "", max_len=160),
                "priority": prio,
                "finding": sanitize_text(item.get("finding") or "", max_len=360),
                "recommendation": sanitize_text(item.get("recommendation") or "", max_len=420),
                "impact": _norm_impact(item.get("impact")),
            }
        )

    normalized = redact_payload(
        {
            "schema_version": "1.0",
            "reviewed_at": utc_now_iso(),
            "reviewer_role": "prompt_context_engineering_specialist",
            "basis": "estimated_expert_projection",
            "overall_summary": sanitize_text(review_payload.get("overall_summary") or "", max_len=600),
            "estimated_impact": _norm_impact(review_payload.get("estimated_impact")),
            "user_command_reviews": user_reviews,
            "agent_prompt_reviews": agent_reviews,
        }
    )

    out_path = dir_path / REVIEW_FILENAME
    atomic_write_json(out_path, normalized)
    return {
        "saved": True,
        "audit_dir": dir_path.relative_to(layout.root).as_posix(),
        "review_path": out_path.relative_to(layout.root).as_posix(),
        "user_command_reviews": len(user_reviews),
        "agent_prompt_reviews": len(agent_reviews),
        "estimated_impact": normalized["estimated_impact"],
    }


def analyze_audit_runs(
    layout: WorkspaceLayout,
    *,
    month: Optional[str] = None,
    sid: Optional[str] = None,
    audit_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Tạo Audit Analysis Packet gọn nhẹ + tín hiệu định lượng (`auto_signals`) cho chuyên gia `/audit`."""
    if not is_audit_enabled(layout):
        return {"enabled": False, "reason": "audit_disabled", "runs_count": 0, "runs": []}

    from audit_viewer import load_runs

    audit_root = resolve_within_scope(layout.root, audit_dir) if audit_dir else layout.audit_dir
    all_runs = load_runs(audit_root, sessions_dir=layout.sessions_dir, layout=layout)

    if sid:
        selected = [r for r in all_runs if r.get("run_id") == sid]
    elif month:
        selected = [r for r in all_runs if r.get("month") == month]
    else:
        target_month = datetime.now().strftime("%Y-%m")
        selected = [r for r in all_runs if r.get("month") == target_month] or all_runs[-10:]

    packet_runs: List[Dict[str, Any]] = []
    sum_tokens = 0
    sum_cached = 0
    sum_in = 0
    sum_cost = 0.0
    cost_known = 0
    wall_vals: List[int] = []

    for r in sorted(selected, key=lambda x: str(x.get("started_at") or ""), reverse=True):
        in_tok = int(r.get("input_tokens") or 0)
        cached_tok = int(r.get("cached_input_tokens") or 0)
        tot_tok = r.get("total_tokens")
        cache_ratio = round(cached_tok / in_tok, 3) if in_tok > 0 else None
        if isinstance(tot_tok, int):
            sum_tokens += tot_tok
            sum_in += in_tok
            sum_cached += cached_tok
        if isinstance(r.get("cost"), (int, float)):
            sum_cost += float(r["cost"])
            cost_known += 1
        if isinstance(r.get("wall_ms"), int):
            wall_vals.append(int(r["wall_ms"]))

        signals: List[str] = []
        if cache_ratio is not None and cache_ratio < 0.5 and in_tok > 50_000:
            signals.append(f"low_cache_hit:{int(cache_ratio * 100)}%")
        if isinstance(tot_tok, int) and tot_tok > 2_000_000:
            signals.append(f"high_token_session:{tot_tok:,}")
        if isinstance(r.get("human_wait_ms"), int) and r["human_wait_ms"] > 120_000:
            signals.append(f"long_human_wait:{r['human_wait_ms'] // 1000}s")
        if int(r.get("retries") or 0) >= 2:
            signals.append(f"high_retry_count:{r.get('retries')}")
        desc = str(r.get("description") or "").strip()
        if desc and len(desc.split()) < 6:
            signals.append("vague_short_prompt")
        if r.get("unit_test") in {None, "not_available"}:
            signals.append("missing_unit_test_telemetry")

        run_dir_path = Path(r["path"])
        try:
            rel_audit_dir = run_dir_path.relative_to(layout.root).as_posix()
        except ValueError:
            rel_audit_dir = r["path"]

        packet_runs.append(
            {
                "sid": r.get("run_id"),
                "task_id": r.get("task_id"),
                "audit_dir": rel_audit_dir,
                "command_ref": r.get("command_ref"),
                "description": desc,
                "user_commands_log": r.get("user_commands_log") or [],
                "outcome": r.get("outcome"),
                "completion_level": r.get("completion_level"),
                "models_by_agent": r.get("models_by_agent") or {},
                "total_tokens": tot_tok,
                "cached_input_tokens": r.get("cached_input_tokens"),
                "cache_hit_ratio": cache_ratio,
                "cost": r.get("cost"),
                "wall_ms": r.get("wall_ms"),
                "human_wait_ms": r.get("human_wait_ms"),
                "tool_time_ms": r.get("tool_time_ms"),
                "files_changed": r.get("files_changed"),
                "unit_test": r.get("unit_test"),
                "build_status": r.get("build_status"),
                "steps": [
                    {
                        "agent": s.get("agent"),
                        "model": s.get("model"),
                        "prompt_ref": s.get("prompt_ref"),
                        "duration_ms": s.get("duration_ms"),
                        "note": s.get("note"),
                    }
                    for s in (r.get("steps") or [])[:15]
                ],
                "has_review": bool(r.get("optimization_review")),
                "auto_signals": signals,
            }
        )

    return {
        "enabled": True,
        "filter": {"month": month, "sid": sid},
        "runs_count": len(packet_runs),
        "summary": {
            "total_tokens": sum_tokens if sum_tokens > 0 else None,
            "overall_cache_hit_ratio": round(sum_cached / sum_in, 3) if sum_in > 0 else None,
            "total_estimated_cost": round(sum_cost, 4) if cost_known > 0 else None,
            "avg_wall_ms": int(sum(wall_vals) / len(wall_vals)) if wall_vals else None,
        },
        "runs": packet_runs,
    }
