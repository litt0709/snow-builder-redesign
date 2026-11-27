"""
audit_viewer.py — Kết xuất các file JSON trong `audit/` thành bảng điều khiển HTML độc lập theo tháng.
- Escape HTML toàn bộ dữ liệu để chống XSS.
- Hiển thị trung thực `null` / `not_measured` và empty state rõ ràng khi chưa có dữ liệu.
- Hỗ trợ `--no-open` cho môi trường CI/test/headless.
"""

from __future__ import annotations

import html
import re
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from audit import AUDIT_FILENAMES, is_audit_enabled, sanitize_text
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
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _safe(val: Any) -> str:
    if val is None:
        return "null"
    return html.escape(str(val), quote=True)


def _fmt_num(val: Any) -> str:
    if val is None or val == "not_available":
        return "null"
    try:
        f = float(val)
        return f"{int(f):,}" if f.is_integer() else f"{f:,.4f}"
    except (TypeError, ValueError):
        return "null"


def _fmt_ms(ms: Any) -> str:
    if ms is None:
        return "null"
    try:
        sec = int(float(ms) / 1000)
        if sec < 60:
            return f"{sec}s"
        m, r = divmod(sec, 60)
        return f"{m}m {r}s"
    except (TypeError, ValueError):
        return "null"


def load_runs(audit_root: Path) -> List[Dict[str, Any]]:
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

        ident = f01.get("task_identity", {})
        usage = f04.get("usage_cost", {})
        tperf = f04.get("time_performance", {})
        qual = f03.get("quality_verification", {})
        out = f03.get("outcome_failure_analysis", {})
        started = str(ident.get("started_at") or f01.get("created_at") or "")
        month = started[:7] if MONTH_RE.match(started[:7]) else run_dir.name[:7]

        runs.append(
            {
                "run_id": ident.get("run_id") or run_dir.name,
                "task_id": ident.get("task_id") or run_dir.name,
                "command_ref": ident.get("command_ref"),
                "description": sanitize_text(ident.get("sanitized_task_description"), max_len=400),
                "month": month,
                "started_at": started,
                "outcome": out.get("outcome") or f04.get("final_summary", {}).get("outcome") or "partial",
                "completion_level": out.get("completion_level") or "claimed",
                "total_tokens": usage.get("total_tokens"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cost": usage.get("total_estimated_cost"),
                "source": usage.get("source") or "not_measured",
                "unpriced_models": usage.get("unpriced_models") or [],
                "missing_metrics": usage.get("missing_metrics") or [],
                "wall_ms": tperf.get("wall_time_ms") or tperf.get("total_wall_clock_duration_ms"),
                "human_wait_ms": tperf.get("human_wait_ms"),
                "model_time_ms": tperf.get("model_time_ms"),
                "tool_time_ms": tperf.get("tool_time_ms"),
                "models_by_agent": f01.get("ai_agent_configuration", {}).get("models_by_agent") or {},
                "ac_passed": qual.get("acceptance_criteria_passed", 0),
                "ac_total": qual.get("acceptance_criteria_total", 0),
                "build_status": qual.get("build_status", "not_available"),
            }
        )
    return runs


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
    all_runs = load_runs(audit_root) if enabled else []
    selected = [r for r in all_runs if r.get("month") == target_month]

    if not enabled:
        reason = "audit_disabled"
        msg = "Audit đang tắt (IS_AUDIT=0). Bật IS_AUDIT=1 để thu thập dữ liệu cho các phiên tiếp theo."
    elif not all_runs:
        reason = "no_audit_data"
        msg = "Chưa có dữ liệu audit nào được ghi nhận."
    elif not selected:
        reason = "no_tasks_for_month"
        msg = f"Không có phiên làm việc nào trong tháng {target_month}."
    else:
        reason = "ok"
        msg = "Đã tải dữ liệu audit thành công."

    known_tokens = [float(r["total_tokens"]) for r in selected if isinstance(r.get("total_tokens"), (int, float))]
    known_costs = [float(r["cost"]) for r in selected if isinstance(r.get("cost"), (int, float))]

    rows_html = []
    for r in selected:
        models_str = ", ".join(f"{k}: {v}" for k, v in sorted((r.get("models_by_agent") or {}).items())) or "not_recorded"
        cost_str = f"${float(r['cost']):.4f}" if isinstance(r.get("cost"), (int, float)) else "null"
        rows_html.append(
            f"<tr>"
            f"<td><code>{_safe(r['run_id'])}</code></td>"
            f"<td>{_safe(r['task_id'])}</td>"
            f"<td>{_safe(r['outcome'])} ({_safe(r['completion_level'])})</td>"
            f"<td>{_safe(models_str)}</td>"
            f"<td>{_safe(_fmt_num(r['total_tokens']))} <small>({_safe(r['source'])})</small></td>"
            f"<td>{_safe(cost_str)}</td>"
            f"<td>wall={_safe(_fmt_ms(r['wall_ms']))} / human={_safe(_fmt_ms(r['human_wait_ms']))} / tool={_safe(_fmt_ms(r['tool_time_ms']))}</td>"
            f"<td>{_safe(r['ac_passed'])}/{_safe(r['ac_total'])}</td>"
            f"</tr>"
        )

    table_body = (
        "".join(rows_html)
        if rows_html
        else f'<tr><td colspan="8" class="empty">{_safe(msg)}</td></tr>'
    )
    total_tok_str = _fmt_num(sum(known_tokens)) if known_tokens else "null"
    total_cost_str = f"${sum(known_costs):.4f}" if known_costs else "null"

    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speedy Audit View — {_safe(target_month)}</title>
<style>
:root {{ --bg:#0f1117; --surface:#171a23; --line:#272c3a; --fg:#e8eaf0; --muted:#949bb0; --accent:#10b981; }}
@media (prefers-color-scheme: light) {{ :root {{ --bg:#f8fafc; --surface:#ffffff; --line:#e2e8f0; --fg:#0f172a; --muted:#64748b; --accent:#059669; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg); padding:28px; }}
.wrap {{ max-width:1360px; margin:0 auto; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:20px 0; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; }}
.card span {{ display:block; font-size:12px; color:var(--muted); text-transform:uppercase; }}
.card strong {{ display:block; font-size:22px; margin-top:6px; }}
.notice {{ background:var(--surface); border-left:4px solid var(--accent); padding:12px 16px; border-radius:8px; margin-bottom:16px; }}
table {{ width:100%; border-collapse:collapse; background:var(--surface); border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:13px; }}
th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
th {{ color:var(--muted); font-weight:700; }}
.empty {{ color:var(--muted); text-align:center; padding:24px; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>Speedy Audit Dashboard — {_safe(target_month)}</h1>
  <p style="color:var(--muted)">Antigravity IDE · Giá trị thiếu nguồn đo được giữ nguyên là <code>null</code> (không suy đoán).</p>
  {"" if reason == "ok" else f'<div class="notice">{_safe(msg)}</div>'}
  <div class="kpis">
    <div class="card"><span>Số phiên trong tháng</span><strong>{len(selected)}</strong></div>
    <div class="card"><span>Known Tokens</span><strong>{_safe(total_tok_str)}</strong></div>
    <div class="card"><span>Chi phí tham khảo</span><strong>{_safe(total_cost_str)}</strong></div>
    <div class="card"><span>Trạng thái dữ liệu</span><strong>{_safe(reason)}</strong></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Session (SID)</th>
        <th>Task</th>
        <th>Kết quả</th>
        <th>Models (Gemini)</th>
        <th>Tokens</th>
        <th>Ref Cost</th>
        <th>Thời gian (Wall/Human/Tool)</th>
        <th>AC</th>
      </tr>
    </thead>
    <tbody>{table_body}</tbody>
  </table>
</div>
</body>
</html>
"""
    payload = html_doc.encode("utf-8")
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
