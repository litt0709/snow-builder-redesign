"""
audit_viewer.py — Kết xuất các file JSON trong `audit/` thành bảng điều khiển HTML độc lập theo tháng.
- Giữ nguyên layout bản gốc Speedy: 4 KPI tổng quan, biểu đồ Monthly trend (tokens/cost),
  Model usage breakdown, và giao diện 2 cột Sidebar + Task Detail Panel có Step summary & Quality cards.
- Escape HTML toàn bộ dữ liệu để chống XSS.
- Hiển thị trung thực `null` / `not_measured` và empty state rõ ràng khi chưa có dữ liệu.
- Hỗ trợ `--no-open` cho môi trường CI/test/headless.
"""

from __future__ import annotations

import html
import json
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from audit import (
    AUDIT_FILENAMES,
    _compute_reference_cost,
    _load_pricing,
    collect_antigravity_transcript_usage,
    is_audit_enabled,
    sanitize_text,
)
from contracts import ErrorCode, SpeedyError, WorkspaceLayout, resolve_within_scope
from storage import atomic_write_bytes

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class AuditViewResult:
    status: str  # "created" | "updated" | "unchanged"
    path: Path
    month: str
    tasks: int
    status_reason: str
    message: str


def _read_dict_tolerant(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _get(data: Dict[str, Any], *path: str, default: Any = None) -> Any:
    curr: Any = data
    for key in path:
        if not isinstance(curr, dict) or key not in curr:
            return default
        curr = curr[key]
    return curr


def _first(*values: Any, default: Any = None) -> Any:
    for val in values:
        if val not in (None, "", [], {}, "not_available"):
            return val
    return default


def _number(val: Any) -> Optional[float]:
    if val in (None, "", "not_available"):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int_or_none(val: Any) -> Optional[int]:
    num = _number(val)
    return None if num is None else int(num)


def _month_from_ts(val: Any) -> Optional[str]:
    if not val:
        return None
    txt = str(val)
    if len(txt) >= 7 and MONTH_RE.match(txt[:7]):
        return txt[:7]
    return None


def _duration_from_ts(started_at: Any, ended_at: Any) -> Optional[int]:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
        return max(0, int((end - start).total_seconds() * 1000))
    except ValueError:
        return None


def _safe(val: Any) -> str:
    if val is None:
        return "null"
    return html.escape(str(val), quote=True)


def _fmt_num(val: Any, fallback: str = "N/A") -> str:
    num = _number(val)
    if num is None:
        return fallback
    if num.is_integer():
        return f"{int(num):,}"
    return f"{num:,.4f}".rstrip("0").rstrip(".")


def _fmt_ms(ms: Any, fallback: str = "N/A") -> str:
    num = _number(ms)
    if num is None:
        return fallback
    sec = int(num / 1000)
    if sec < 60:
        return f"{sec}s"
    m, r = divmod(sec, 60)
    if m < 60:
        return f"{m}m {r}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _fmt_cost(val: Any, currency: Any = None, fallback: str = "N/A") -> str:
    num = _number(val)
    if num is None:
        return fallback
    prefix = "$" if not currency or str(currency).upper() == "USD" else f"{html.escape(str(currency))} "
    return f"{prefix}{num:.4f}"


def _fmt_files_changed(val: Any, measurement_status: Any) -> str:
    if measurement_status == "measured" and _number(val) == 0:
        return "No Change"
    if measurement_status == "not_measured" and _number(val) is None:
        return "Not measured"
    return _fmt_num(val)


def _bar_width(val: Any, maximum: float) -> str:
    num = _number(val) or 0
    if maximum <= 0:
        return "0%"
    return f"{max(3, min(100, int(num / maximum * 100)))}%" if num > 0 else "0%"


def _models_by_agent(f01: Dict[str, Any], f04: Dict[str, Any], f02: Dict[str, Any]) -> Dict[str, str]:
    models: Dict[str, str] = {}
    for cand in (
        _get(f04, "final_summary", "models_by_agent", default={}),
        _get(f01, "ai_agent_configuration", "models_by_agent", default={}),
    ):
        if isinstance(cand, dict):
            for k, v in cand.items():
                if v:
                    models[str(k)] = str(v)
    for ev in _get(f02, "execution_trace", "events", default=[]):
        if not isinstance(ev, dict):
            continue
        agent = _first(ev.get("agent"), ev.get("agent_name"))
        model = ev.get("model")
        if agent and model:
            models[str(agent)] = str(model)
    fallback_model = _first(
        _get(f01, "ai_agent_configuration", "model"),
        _get(f04, "final_summary", "model"),
    )
    if fallback_model and not models:
        models["default"] = str(fallback_model)
    return models


def _enrich_from_session_state(run: Dict[str, Any], sessions_dir: Optional[Path]) -> None:
    """Làm giàu chỉ đọc từ `sessions/<sid>/state.json` cho các phiên cũ chưa ghi đầy đủ telemetry vào audit/."""
    if not sessions_dir or not sessions_dir.is_dir():
        return
    sid = str(run.get("run_id") or "")
    if not sid:
        return
    st_path = sessions_dir / sid / "state.json"
    st = _read_dict_tolerant(st_path)
    if not st:
        return

    from policy import select_gemini_model

    stages = st.get("stages") or {}
    route = st.get("route") or list(stages.keys())
    high_risk = bool(st.get("high_risk"))

    # 1. Enrich models_by_agent nếu trống
    if not run.get("models_by_agent"):
        inferred_models: Dict[str, str] = {}
        for st_name in route:
            info = stages.get(st_name)
            if isinstance(info, dict) and info.get("status") not in {None, "pending", "skipped"}:
                inferred_models[st_name] = select_gemini_model(st_name, high_risk=high_risk)["model"]
        if inferred_models:
            run["models_by_agent"] = inferred_models

    # 2. Enrich steps từ state.stages nếu trống hoặc chỉ có 1 event audit_start
    existing_steps = run.get("steps") or []
    only_start_step = len(existing_steps) == 1 and str(existing_steps[0].get("agent")) == "orchestrator"
    if not existing_steps or only_start_step:
        synth_steps: List[Dict[str, Any]] = []
        prev_ts = st.get("created_at")
        for st_name in route:
            info = stages.get(st_name)
            if not isinstance(info, dict):
                continue
            st_status = info.get("status")
            if st_status in {None, "pending"}:
                continue
            cur_ts = info.get("updated_at")
            dur = _duration_from_ts(prev_ts, cur_ts)
            if cur_ts:
                prev_ts = cur_ts
            synth_steps.append(
                {
                    "agent": st_name,
                    "model": select_gemini_model(st_name, high_risk=high_risk)["model"],
                    "duration_ms": dur,
                    "note": str(st_status),
                }
            )
        if synth_steps:
            run["steps"] = synth_steps

    # 3. Enrich wall_ms nếu thiếu
    if run.get("wall_ms") is None:
        run["wall_ms"] = _duration_from_ts(st.get("created_at"), st.get("updated_at"))

    # 4. Enrich unit_test & build_status từ state.verification
    verifications = st.get("verification") or []
    if verifications and isinstance(verifications[-1], dict):
        latest_v = verifications[-1]
        for layer in latest_v.get("layers") or []:
            if not isinstance(layer, dict):
                continue
            lname = layer.get("layer")
            lstatus = str(layer.get("status") or "")
            if lname == "unit_integration" and lstatus != "NOT_APPLICABLE" and not run.get("unit_test"):
                run["unit_test"] = lstatus.lower()
            elif lname == "build" and lstatus != "NOT_APPLICABLE" and not run.get("build_status"):
                run["build_status"] = lstatus.lower()


def _enrich_from_antigravity_transcript(run: Dict[str, Any], layout: Optional[WorkspaceLayout]) -> None:
    """Làm giàu chỉ đọc số đo token & chi phí thật từ `transcript.jsonl` cho các phiên chưa ghi usage vào 04-cost-time.json."""
    if run.get("total_tokens") is not None:
        return
    usage_items = collect_antigravity_transcript_usage(
        sid=str(run.get("run_id") or ""),
        started_at=run.get("started_at"),
        ended_at=run.get("ended_at"),
    )
    if not usage_items:
        return
    in_tok = sum(int(u.get("input_tokens") or 0) for u in usage_items)
    cached_tok = sum(int(u.get("cached_input_tokens") or 0) for u in usage_items)
    out_tok = sum(int(u.get("output_tokens") or 0) for u in usage_items)
    run["input_tokens"] = in_tok
    run["cached_input_tokens"] = cached_tok
    run["output_tokens"] = out_tok
    run["total_tokens"] = in_tok + out_tok
    run["source"] = "antigravity_transcript"
    if layout is not None:
        pricing = _load_pricing(layout)
        cost_res = _compute_reference_cost(usage_items, pricing)
        if cost_res["total_cost"] is not None:
            run["cost"] = cost_res["total_cost"]
            run["currency"] = "USD"
    # Ghi nhận model thật nếu chưa có
    models_map = run.setdefault("models_by_agent", {})
    for u in usage_items:
        m = u.get("model")
        if m and m not in models_map.values():
            models_map.setdefault("antigravity", str(m))


def load_runs(
    audit_root: Path,
    sessions_dir: Optional[Path] = None,
    layout: Optional[WorkspaceLayout] = None,
) -> List[Dict[str, Any]]:
    if not audit_root.is_dir():
        return []
    runs: List[Dict[str, Any]] = []
    for run_dir in sorted(p for p in audit_root.iterdir() if p.is_dir()):
        f01 = _read_dict_tolerant(run_dir / AUDIT_FILENAMES[0])
        f02 = _read_dict_tolerant(run_dir / AUDIT_FILENAMES[1])
        f03 = _read_dict_tolerant(run_dir / AUDIT_FILENAMES[2])
        f04 = _read_dict_tolerant(run_dir / AUDIT_FILENAMES[3])
        if not any((f01, f02, f03, f04)):
            continue

        ident = _get(f01, "task_identity", default={})
        final_summary = _get(f04, "final_summary", default={})
        usage = _get(f04, "usage_cost", default={})
        tperf = _get(f04, "time_performance", default={})
        qual = _get(f03, "quality_verification", default={})
        repo_changes = _get(f03, "repository_changes", default={})
        out = _get(f03, "outcome_failure_analysis", default={})

        started = _first(ident.get("started_at"), f01.get("created_at"), f04.get("created_at"))
        ended = ident.get("ended_at")
        month = _month_from_ts(started) or run_dir.name[:7]
        duration_ms = _first(
            tperf.get("wall_time_ms"),
            tperf.get("total_wall_clock_duration_ms"),
            final_summary.get("total_duration_ms"),
            _duration_from_ts(started, ended),
        )
        missing_metrics: List[str] = []
        for src in (f01, usage, final_summary):
            mm = src.get("missing_metrics") if isinstance(src, dict) else None
            if isinstance(mm, list):
                missing_metrics.extend(str(item) for item in mm)

        events = _get(f02, "execution_trace", "events", default=[])
        steps = _get(f02, "execution_trace", "steps", default=[])
        if not steps and isinstance(events, list) and events:
            steps = [
                {
                    "agent": ev.get("agent") or ev.get("agent_name"),
                    "model": ev.get("model"),
                    "tool_call_count": 1 if ev.get("tool_time_ms") else None,
                    "duration_ms": _first(ev.get("tool_time_ms"), ev.get("model_time_ms"), ev.get("human_wait_ms")),
                    "note": ev.get("note") or ev.get("event_type"),
                }
                for ev in events
                if isinstance(ev, dict)
            ]

        run_entry = {
            "folder": run_dir.name,
            "path": str(run_dir),
            "month": month,
            "run_id": _first(ident.get("run_id"), final_summary.get("run_id"), run_dir.name),
            "task_id": _first(ident.get("task_id"), final_summary.get("task_id"), run_dir.name),
            "jira_ticket": _first(ident.get("jira_ticket"), final_summary.get("jira_ticket")),
            "command_ref": _first(ident.get("command_ref")),
            "description": sanitize_text(ident.get("sanitized_task_description"), max_len=400),
            "started_at": started,
            "ended_at": ended,
            "outcome": _first(out.get("outcome"), final_summary.get("outcome"), default="partial"),
            "completion_level": _first(out.get("completion_level"), final_summary.get("completion_level"), default="claimed"),
            "input_tokens": _int_or_none(usage.get("input_tokens")),
            "cached_input_tokens": _int_or_none(usage.get("cached_input_tokens")),
            "output_tokens": _int_or_none(usage.get("output_tokens")),
            "reasoning_tokens": _int_or_none(usage.get("reasoning_tokens")),
            "total_tokens": _int_or_none(usage.get("total_tokens")),
            "cost": _number(usage.get("total_estimated_cost")),
            "currency": "USD" if usage.get("currency_pricing_source") or usage.get("total_estimated_cost") is not None else None,
            "source": usage.get("source") or "not_measured",
            "wall_ms": _int_or_none(duration_ms),
            "human_wait_ms": _int_or_none(tperf.get("human_wait_ms")),
            "model_time_ms": _int_or_none(tperf.get("model_time_ms")),
            "tool_time_ms": _int_or_none(tperf.get("tool_time_ms")),
            "models_by_agent": _models_by_agent(f01, f04, f02),
            "events": events if isinstance(events, list) else [],
            "steps": steps if isinstance(steps, list) else [],
            "tool_call_count": _get(f02, "execution_trace", "tool_call_count"),
            "files_changed": _first(repo_changes.get("files_changed"), final_summary.get("files_changed")),
            "change_measurement_status": _first(repo_changes.get("change_measurement_status"), default="not_measured"),
            "changed_file_paths": repo_changes.get("changed_file_paths") or [],
            "unit_test": _first(_get(qual, "unit_test_result", "status")),
            "build_status": _first(qual.get("build_status")),
            "security_scan": _first(_get(qual, "security_scan_result", "status")),
            "ac_passed": qual.get("acceptance_criteria_passed"),
            "ac_total": qual.get("acceptance_criteria_total"),
            "missing_metrics": sorted(set(missing_metrics)),
        }
        _enrich_from_session_state(run_entry, sessions_dir)
        _enrich_from_antigravity_transcript(run_entry, layout)
        runs.append(run_entry)
    return runs


def _aggregate_steps(steps: List[Dict[str, Any]], fallback_label: str = "Flow") -> List[Dict[str, Any]]:
    grouped: Dict[tuple, Dict[str, Any]] = {}
    numeric_keys = ("input_tokens", "cached_tokens", "output_tokens", "request_count", "tool_call_count", "duration_ms", "cost")
    for step in steps:
        if not isinstance(step, dict):
            continue
        agent_label = step.get("agent") or fallback_label
        model = _first(step.get("model"), default="Unknown model")
        prompt_ref = step.get("prompt_ref")
        prompt_excerpt = sanitize_text(step.get("prompt_excerpt"), max_len=500) if step.get("prompt_excerpt") else None
        key = (agent_label, str(model), prompt_ref, prompt_excerpt)
        if key not in grouped:
            grouped[key] = {
                "agent": agent_label,
                "model": model,
                "prompt_ref": prompt_ref,
                "prompt_excerpt": prompt_excerpt,
                "turn_count": 0,
                "notes": [],
                **{k: None for k in numeric_keys},
            }
        summary = grouped[key]
        summary["turn_count"] += 1
        summary["notes"].append(step.get("note"))
        for k in numeric_keys:
            val = _number(step.get(k))
            if val is not None:
                summary[k] = (summary[k] or 0) + val
    out: List[Dict[str, Any]] = []
    for summary in grouped.values():
        notes = summary.pop("notes")
        summary["note"] = notes[0] if notes and all(n == notes[0] for n in notes) else None
        out.append(summary)
    return out


def _sum_number(runs: List[Dict[str, Any]], key: str) -> Optional[float]:
    vals = [_number(r.get(key)) for r in runs]
    vals = [v for v in vals if v is not None]
    return sum(vals) if vals else None


def _count_known(runs: List[Dict[str, Any]], key: str) -> int:
    return sum(1 for r in runs if r.get(key) not in (None, "", "not_available"))


def _aggregate_months(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    months = sorted({r["month"] for r in runs if r.get("month")})
    out: List[Dict[str, Any]] = []
    for m in months:
        m_runs = [r for r in runs if r.get("month") == m]
        out.append(
            {
                "month": m,
                "tasks": len(m_runs),
                "tokens": _sum_number(m_runs, "total_tokens"),
                "cost": _sum_number(m_runs, "cost"),
                "wall_ms": _sum_number(m_runs, "wall_ms"),
            }
        )
    return out


def _model_summary(runs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in runs:
        for model in (r.get("models_by_agent") or {}).values():
            counts[str(model)] = counts.get(str(model), 0) + 1
    return counts


def _render_kpi(label: str, value: str, hint: str) -> str:
    return f'<div class="kpi"><span>{_safe(label)}</span><strong>{_safe(value)}</strong><em>{_safe(hint)}</em></div>'


def _render_month_chart(months: List[Dict[str, Any]]) -> str:
    max_tokens = max([_number(item.get("tokens")) or 0 for item in months], default=0)
    max_cost = max([_number(item.get("cost")) or 0 for item in months], default=0)
    rows: List[str] = []
    for item in months:
        rows.append(
            '<div class="trendrow">'
            f'<span>{_safe(item["month"])}</span>'
            '<div class="trendbars">'
            f'<div class="trendbar tokens" title="Tokens: {_safe(_fmt_num(item.get("tokens")))}"><i style="width:{_bar_width(item.get("tokens"), max_tokens)}"></i></div>'
            f'<div class="trendbar cost" title="Cost: {_safe(_fmt_cost(item.get("cost")))}"><i style="width:{_bar_width(item.get("cost"), max_cost)}"></i></div>'
            "</div>"
            f'<b>{_safe(item["tasks"])} tasks</b>'
            "</div>"
        )
    legend = '<p class="legend"><span class="dot tokens"></span>Tokens <span class="dot cost"></span>Cost</p>'
    return legend + ("".join(rows) or '<p class="empty">Chưa có dữ liệu audit.</p>')


def _render_model_breakdown(models: Dict[str, int]) -> str:
    total = max(1, sum(models.values()))
    parts = [
        f'<div class="modelrow"><span>{_safe(model)}</span><div class="bar"><i style="width:{_bar_width(cnt, total)}"></i></div><b>{_safe(cnt)}</b></div>'
        for model, cnt in sorted(models.items(), key=lambda item: (-item[1], item[0]))
    ]
    return "".join(parts) or '<p class="empty">Chưa có dữ liệu model.</p>'


def _task_display_name(run: Dict[str, Any]) -> Any:
    return run.get("task_id") or run.get("command_ref") or run.get("run_id")


def _render_task_sidebar(runs: List[Dict[str, Any]]) -> str:
    items: List[str] = []
    for idx, run in enumerate(runs):
        active = " active" if idx == 0 else ""
        sub = f"Session: {run.get('run_id')} | {run.get('outcome')}"
        items.append(
            f'<button type="button" class="task-item{active}" data-task-index="{idx}">'
            f"<strong>{_safe(_task_display_name(run))}</strong>"
            f"<small>{_safe(sub)}</small>"
            "</button>"
        )
    return "".join(items) or '<p class="empty">Không có phiên nào trong tháng này.</p>'


def _render_steps_table(run: Dict[str, Any]) -> str:
    summaries = _aggregate_steps(run.get("steps") or [], run.get("command_ref") or "Flow")
    if not summaries:
        return '<p class="empty">Chưa có bảng tóm tắt từng bước cho phiên này.</p>'
    show_agent = any(s.get("agent") for s in summaries)
    show_tokens = any(
        s.get("input_tokens") is not None or s.get("output_tokens") is not None or s.get("cached_tokens") is not None
        for s in summaries
    )
    show_requests = any(s.get("request_count") is not None for s in summaries)
    show_tools = any(s.get("tool_call_count") is not None for s in summaries)
    show_cost = any(s.get("cost") is not None for s in summaries)
    show_prompt = any(s.get("prompt_ref") or s.get("prompt_excerpt") for s in summaries)
    show_note = any(s.get("note") for s in summaries)

    headers: List[str] = []
    if show_agent:
        headers.append("Agent / Flow")
    headers.extend(["Turns", "Model"])
    if show_tokens:
        headers.extend(["Input", "Cached", "Output"])
    if show_cost:
        headers.append("Cost")
    if show_requests:
        headers.append("Requests")
    if show_tools:
        headers.append("Tool calls")
    headers.append("Time")
    if show_prompt:
        headers.append("Prompt used")
    if show_note:
        headers.append("Status / Note")

    rows: List[str] = []
    for s in summaries:
        cells: List[str] = []
        if show_agent:
            cells.append(_safe(s.get("agent")))
        cells.extend([_safe(s.get("turn_count")), _safe(s.get("model"))])
        if show_tokens:
            cells.extend(
                [
                    _safe(_fmt_num(s.get("input_tokens"))),
                    _safe(_fmt_num(s.get("cached_tokens"))),
                    _safe(_fmt_num(s.get("output_tokens"))),
                ]
            )
        if show_cost:
            cells.append(_safe(_fmt_cost(s.get("cost"))))
        if show_requests:
            cells.append(_safe(_fmt_num(s.get("request_count"))))
        if show_tools:
            cells.append(_safe(_fmt_num(s.get("tool_call_count"))))
        cells.append(_safe(_fmt_ms(s.get("duration_ms"))))
        if show_prompt:
            pref = s.get("prompt_ref")
            pex = s.get("prompt_excerpt")
            phtml = f"<code>{_safe(pref)}</code>" if pref else ""
            if pex:
                phtml += f"<small>{_safe(pex)}</small>"
            cells.append(phtml)
        if show_note:
            cells.append(_safe(s.get("note")))
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")

    header_html = "".join(f"<th>{_safe(h)}</th>" for h in headers)
    return f'<div class="tablewrap"><table><thead><tr>{header_html}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _render_task_panel(run: Dict[str, Any], idx: int) -> str:
    models = run.get("models_by_agent") or {}
    model_pills = "".join(
        f'<span class="pill">{_safe(agent)}: {_safe(model)}</span>'
        for agent, model in sorted(models.items())
    )
    visibility = "" if idx == 0 else " hidden"
    meta_parts = [
        f"<strong>Session:</strong> {_safe(run.get('run_id'))}",
        f"<strong>Task:</strong> {_safe(run.get('task_id'))}",
    ]
    if run.get("command_ref"):
        meta_parts.append(f"<strong>Command:</strong> {_safe(run.get('command_ref'))}")
    if run.get("jira_ticket"):
        meta_parts.append(f"<strong>Jira:</strong> {_safe(run.get('jira_ticket'))}")
    if run.get("started_at"):
        meta_parts.append(f"<strong>Started:</strong> {_safe(run.get('started_at'))}")

    time_hint_parts = []
    if run.get("human_wait_ms") is not None:
        time_hint_parts.append(f"human {_fmt_ms(run.get('human_wait_ms'))}")
    if run.get("tool_time_ms") is not None:
        time_hint_parts.append(f"tool {_fmt_ms(run.get('tool_time_ms'))}")
    if run.get("tool_call_count") is not None:
        time_hint_parts.append(f"{run.get('tool_call_count')} tool calls")
    time_hint = " · ".join(time_hint_parts) or "wall clock"

    desc_html = f"<p>{_safe(run.get('description'))}</p>" if run.get("description") else ""
    models_html = f"<p><strong>Models:</strong> {model_pills}</p>" if model_pills else ""

    tok_hint = (
        f"in {_fmt_num(run.get('input_tokens'))} / out {_fmt_num(run.get('output_tokens'))} ({run.get('source')})"
        if run.get("total_tokens") is not None
        else "not_measured (host chưa cấp telemetry)"
    )
    cost_hint = "public API price list" if run.get("cost") is not None else "cần dữ liệu token từ host"
    task_cards = "".join(
        [
            _render_kpi("Total tokens", _fmt_num(run.get("total_tokens")), tok_hint),
            _render_kpi("Estimated cost", _fmt_cost(run.get("cost"), run.get("currency")), cost_hint),
            _render_kpi("Duration", _fmt_ms(run.get("wall_ms")), time_hint),
            _render_kpi("Outcome", str(run.get("outcome")), f"level: {run.get('completion_level')}"),
        ]
    )

    qual_cards = "".join(
        [
            _render_kpi("Unit test", str(run.get("unit_test")), "") if run.get("unit_test") else "",
            _render_kpi("Build", str(run.get("build_status")), "") if run.get("build_status") else "",
            _render_kpi("Security scan", str(run.get("security_scan")), "") if run.get("security_scan") else "",
            (
                _render_kpi("Acceptance", f"{run.get('ac_passed')}/{run.get('ac_total')}", "")
                if run.get("ac_passed") is not None and run.get("ac_total") is not None
                else ""
            ),
        ]
    )

    return f"""<section class="task-panel" id="task-panel-{idx}"{visibility}>
    <h2>{_safe(_task_display_name(run))}</h2>
    <p class="submeta">{" · ".join(meta_parts)}</p>
    {desc_html}
    {models_html}
    <div class="cards">{task_cards}</div>
    <h3>Step summary</h3>
    {_render_steps_table(run)}
    <h3>Quality &amp; verification</h3>
    <div class="cards">{qual_cards or '<p class="empty">Chưa có dữ liệu kiểm chứng.</p>'}</div>
    <p><strong>Files changed:</strong> {_safe(_fmt_files_changed(run.get("files_changed"), run.get("change_measurement_status")))}</p>
</section>"""


def render_audit_dashboard(
    layout: WorkspaceLayout,
    *,
    month: Optional[str] = None,
    audit_dir: Optional[str] = None,
    output_path: Optional[str] = None,
    open_browser: bool = False,
) -> AuditViewResult:
    target_month = month or datetime.now().strftime("%Y-%m")
    if not MONTH_RE.match(target_month):
        raise SpeedyError(ErrorCode.INVALID_INPUT, f"Tháng không đúng định dạng YYYY-MM: '{target_month}'.")

    audit_root = resolve_within_scope(layout.root, audit_dir) if audit_dir else layout.audit_dir
    out_file = (
        resolve_within_scope(layout.root, output_path)
        if output_path
        else (layout.reports_dir / "audit-view" / f"{target_month}.html")
    )

    enabled = is_audit_enabled(layout)
    all_runs = load_runs(audit_root, sessions_dir=layout.sessions_dir, layout=layout) if enabled else []
    selected = [r for r in all_runs if r.get("month") == target_month]

    if not enabled:
        reason = "audit_disabled"
        msg = "Audit đang tắt (IS_AUDIT=0). Bật IS_AUDIT=1 trong ai-workspace/.env để thu thập dữ liệu cho các phiên tiếp theo."
    elif not all_runs:
        reason = "no_audit_data"
        msg = "Chưa có dữ liệu audit nào được ghi nhận trong ai-workspace/audit."
    elif not selected:
        reason = "no_tasks_for_month"
        msg = f"Không có phiên làm việc nào trong tháng {target_month}."
    else:
        reason = "ok"
        msg = "Đã tải dữ liệu audit thành công."

    previous_runs = [r for r in all_runs if r.get("month") and r["month"] < target_month]
    months = _aggregate_months(all_runs)
    sorted_runs = sorted(selected, key=lambda r: str(r.get("started_at") or ""), reverse=True)
    known_tokens = _sum_number(selected, "total_tokens")
    known_cost = _sum_number(selected, "cost")
    known_duration = _sum_number(selected, "wall_ms")

    kpis_html = "".join(
        [
            _render_kpi("Tasks this month", str(len(selected)), f"{len(previous_runs)} previous tasks"),
            _render_kpi("Known tokens", _fmt_num(known_tokens), f"known in {_count_known(selected, 'total_tokens')} tasks"),
            _render_kpi("Known cost", _fmt_cost(known_cost), f"known in {_count_known(selected, 'cost')} tasks"),
            _render_kpi("Wall time", _fmt_ms(known_duration), f"known in {_count_known(selected, 'wall_ms')} tasks"),
        ]
    )
    sidebar_html = _render_task_sidebar(sorted_runs)
    panels_html = (
        "".join(_render_task_panel(r, idx) for idx, r in enumerate(sorted_runs))
        or f'<p class="empty">{_safe(msg)}</p>'
    )
    notice_cls = "notice warn" if reason == "audit_disabled" else "notice"
    notice_html = "" if reason == "ok" else f'<section class="{notice_cls}"><strong>{_safe(msg)}</strong></section>'

    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speedy Audit View - {_safe(target_month)}</title>
<style>
:root {{ --bg:#fcfcfd; --fg:#17181c; --muted:#6f7683; --line:#e8e9ee; --accent:#06c755; --accent-ink:#058a44; --code-bg:#f1f2f6; --surface:#ffffff; --warn:#b7791f; --bad:#c53030; --cost:#3b82f6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#0f1013; --fg:#e9eaee; --muted:#989fac; --line:#24262d; --accent-ink:#41d98a; --code-bg:#1b1d24; --surface:#14161b; --warn:#f6ad55; --bad:#fc8181; --cost:#60a5fa; }} }}
* {{ box-sizing:border-box }}
body {{ margin:0; background:var(--bg); color:var(--fg); font-size:14px; line-height:1.65; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Hiragino Kaku Gothic ProN","Yu Gothic",Meiryo,sans-serif; }}
.shell {{ max-width:1500px; margin:0 auto; padding:28px 32px 120px; }}
.header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:24px; border-bottom:1px solid var(--line); padding-bottom:18px; margin-bottom:22px; }}
.meta {{ color:var(--muted); font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin:0 0 6px; }}
h1 {{ font-size:28px; margin:0; letter-spacing:.01em }}
h2 {{ font-size:19px; margin:0 0 8px; }}
h3 {{ font-size:15px; margin:24px 0 10px; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin:18px 0; }}
.kpi {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }}
.kpi span {{ display:block; color:var(--muted); font-size:12px; font-weight:700; }}
.kpi strong {{ display:block; font-size:22px; margin:4px 0; word-break:break-word; }}
.kpi em {{ color:var(--muted); font-style:normal; font-size:12px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:12px 0; }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.panel {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:16px; min-width:0; }}
.modelrow {{ display:grid; grid-template-columns:minmax(150px,240px) 1fr 44px; gap:10px; align-items:center; margin:8px 0; }}
.bar {{ height:9px; background:var(--code-bg); border-radius:999px; overflow:hidden; }}
.bar i {{ display:block; height:100%; background:var(--accent); }}
.trendrow {{ display:grid; grid-template-columns:70px 1fr 70px; gap:10px; align-items:center; margin:10px 0; }}
.trendbars {{ display:flex; flex-direction:column; gap:3px; }}
.trendbar {{ height:7px; background:var(--code-bg); border-radius:999px; overflow:hidden; }}
.trendbar i {{ display:block; height:100%; }}
.trendbar.tokens i {{ background:var(--accent); }}
.trendbar.cost i {{ background:var(--cost); }}
.legend {{ color:var(--muted); font-size:12px; margin:0 0 10px; }}
.dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin:0 4px 0 10px; }}
.dot.tokens {{ background:var(--accent); }}
.dot.cost {{ background:var(--cost); }}
.legend .dot:first-child {{ margin-left:0; }}
.layout {{ display:grid; grid-template-columns:240px 1fr; gap:16px; margin-top:16px; }}
.sidebar {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:8px; align-self:start; max-height:70vh; overflow:auto; }}
.task-item {{ display:block; width:100%; text-align:left; border:0; background:none; color:var(--fg); padding:10px 12px; border-radius:6px; cursor:pointer; font:inherit; }}
.task-item:hover {{ background:var(--code-bg); }}
.task-item.active {{ background:var(--accent); color:#fff; }}
.task-item strong {{ display:block; font-size:13px; }}
.task-item small {{ display:block; color:inherit; opacity:.75; font-size:11px; margin-top:2px; }}
.content {{ background:var(--surface); border:1px solid var(--line); border-radius:8px; padding:20px; min-width:0; }}
.task-panel.hidden, [hidden] {{ display:none !important; }}
.submeta {{ color:var(--muted); font-size:12px; }}
.tablewrap {{ overflow:auto; border:1px solid var(--line); border-radius:8px; background:var(--surface); margin:8px 0; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; text-align:left; }}
th {{ background:var(--code-bg); white-space:nowrap; font-weight:800; }}
tr:last-child td {{ border-bottom:0; }}
td code {{ display:block; font-size:12px; background:var(--code-bg); border-radius:4px; padding:2px 6px; }}
td small {{ display:block; color:var(--muted); margin-top:4px; max-width:260px; white-space:pre-wrap; }}
.empty {{ color:var(--muted); padding:16px; }}
.pill {{ display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; margin:2px; color:var(--muted); font-size:12px; }}
.notice {{ background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:8px; padding:14px 16px; margin:16px 0; }}
.notice.warn {{ border-left-color:var(--warn); }}
@media (max-width:900px) {{ .header {{ display:block; }} .kpis, .grid, .layout {{ grid-template-columns:1fr; }} .shell {{ padding:20px 16px 80px; }} .sidebar {{ max-height:none; }} }}
</style>
</head>
<body>
<div class="shell">
  <header class="header">
    <div><p class="meta">Speedy Audit View</p><h1>AI efficiency dashboard - {_safe(target_month)}</h1></div>
    <p class="meta">Data source: ai-workspace/audit</p>
  </header>
  {notice_html}
  <section class="kpis">{kpis_html}</section>
  <section class="grid">
    <div class="panel"><h2>Monthly trend (tokens / cost)</h2>{_render_month_chart(months)}</div>
    <div class="panel"><h2>Model usage</h2>{_render_model_breakdown(_model_summary(selected))}</div>
  </section>
  <section class="layout">
    <nav class="sidebar" id="sidebar">{sidebar_html}</nav>
    <div class="content" id="content">{panels_html}</div>
  </section>
</div>
<script>
document.querySelectorAll('.task-item').forEach(item => {{
  item.addEventListener('click', () => {{
    const index = item.dataset.taskIndex;
    document.querySelectorAll('.task-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.task-panel').forEach(el => el.setAttribute('hidden', ''));
    item.classList.add('active');
    const panel = document.getElementById('task-panel-' + index);
    if (panel) panel.removeAttribute('hidden');
  }});
}});
</script>
</body>
</html>
"""
    payload = html_doc.encode("utf-8")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    if not out_file.exists():
        atomic_write_bytes(out_file, payload)
        status = "created"
    elif out_file.read_bytes() == payload:
        status = "unchanged"
    else:
        atomic_write_bytes(out_file, payload)
        status = "updated"

    if open_browser:
        webbrowser.open(out_file.as_uri())

    return AuditViewResult(
        status=status,
        path=out_file,
        month=target_month,
        tasks=len(selected),
        status_reason=reason,
        message=msg,
    )
