"""
benchmark.py — Bộ đo lường và đối chiếu hiệu quả theo mục 4.2 specs/design.md:
1. Đo lường hiệu quả cắt giảm ngữ cảnh (Context Funnel: RepoMap + Context Packet vs Naive Preload)
   trên cả tập `dev` và tập `held_out` có oracle định trước, bảo đảm không đánh rơi oracle recall.
2. So sánh ghép cặp (Paired Trial Comparison) giữa `baseline` và `candidate`:
   - Tính cả các lần chạy fail/retry/abort trong mẫu số.
   - Nếu `completed == 0` -> `tokens_per_verified_completion = null` (không ghi `0` giả).
   - Tự động gắn cờ `REJECT_REGRESSION` nếu giảm correctness hoặc vi phạm gate/scope;
     gắn cờ `INCONCLUSIVE` khi kích thước mẫu nhỏ (< 3 trials).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contracts import ErrorCode, SpeedyError, WorkspaceLayout
from policy import classify_intent
from repomap import build_repomap, query_repomap
from scan import IGNORE_DIRS


def _percentile(sorted_vals: Sequence[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(float(sorted_vals[0]), 2)
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return round(float(sorted_vals[lo]), 2)
    frac = idx - lo
    return round(float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac), 2)


def _total_application_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(p in IGNORE_DIRS or p.startswith(".") for p in rel_parts):
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def evaluate_context_and_routing_suite(
    layout: WorkspaceLayout,
    tasks: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Đánh giá chất lượng định tuyến (`intent` + risk guard) và chất lượng thu hẹp ngữ cảnh
    (`repomap` + `context prepare`) đối chiếu với đáp án chuẩn (`oracle_modules`, `expected_mode`).
    Tất cả số liệu dung lượng đều gắn nhãn rõ `utf8_bytes_proxy`.
    """
    if not tasks:
        raise SpeedyError(ErrorCode.INVALID_INPUT, "Danh sách task benchmark không được rỗng.")

    build_repomap(layout, use_cache=False)
    naive_repo_bytes = max(1, _total_application_bytes(layout.root))

    per_split: Dict[str, List[Dict[str, Any]]] = {"dev": [], "held_out": []}
    for idx, task in enumerate(tasks):
        split = "held_out" if task.get("split") == "held_out" else "dev"
        task_id = str(task.get("id") or f"T-{idx + 1:02d}")
        prompt = str(task["prompt"])
        target_paths = task.get("target_paths")
        expected_mode = str(task["expected_mode"])
        oracle_modules = set(task.get("oracle_modules") or [])
        query_kw = str(task.get("query") or prompt)

        intent_res = classify_intent(prompt, target_paths=target_paths)
        mode_ok = intent_res["intent"] == expected_mode

        rm_res = query_repomap(layout, query_kw, limit=5)
        matched_paths = {m["path"] for m in rm_res.get("matches", [])}
        oracle_hit = oracle_modules <= matched_paths

        # Đo kích thước thực tế khi chỉ đọc các module được định vị + Context Packet
        scoped_bytes = 0
        for mpath in matched_paths:
            mod_abs = layout.root / mpath
            if mod_abs.is_dir():
                for f in mod_abs.rglob("*"):
                    if f.is_file() and not f.name.startswith("."):
                        scoped_bytes += f.stat().st_size

        repomap_json_bytes = len(json.dumps(rm_res, ensure_ascii=False).encode("utf-8"))
        speedy_loaded_bytes = repomap_json_bytes + scoped_bytes
        reduction_ratio = round(1.0 - (speedy_loaded_bytes / naive_repo_bytes), 4)

        per_split[split].append(
            {
                "task_id": task_id,
                "split": split,
                "expected_mode": expected_mode,
                "predicted_mode": intent_res["intent"],
                "routing_correct": mode_ok,
                "oracle_modules": sorted(oracle_modules),
                "retrieved_modules": sorted(matched_paths),
                "oracle_recall_hit": oracle_hit,
                "naive_repo_bytes_proxy": naive_repo_bytes,
                "speedy_scoped_bytes_proxy": speedy_loaded_bytes,
                "bytes_reduction_ratio": reduction_ratio,
            }
        )

    def _summarize(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not items:
            return {"task_count": 0}
        n = len(items)
        routing_acc = round(sum(1 for x in items if x["routing_correct"]) / n, 4)
        oracle_rec = round(sum(1 for x in items if x["oracle_recall_hit"]) / n, 4)
        avg_red = round(sum(x["bytes_reduction_ratio"] for x in items) / n, 4)
        return {
            "task_count": n,
            "routing_accuracy": routing_acc,
            "oracle_recall_rate": oracle_rec,
            "mean_bytes_reduction_ratio": avg_red,
            "measurement_unit": "utf8_bytes_proxy",
        }

    all_items = per_split["dev"] + per_split["held_out"]
    return {
        "approval_driver": "simulated_test_driver",
        "overall": _summarize(all_items),
        "dev": _summarize(per_split["dev"]),
        "held_out": _summarize(per_split["held_out"]),
        "tasks": all_items,
    }


def summarize_trial_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tính bộ chỉ số chuẩn mục 4.2 trên danh sách các bản ghi trial:
    Mỗi bản ghi gồm: `task_id`, `verified_completed` (bool), `attempts` (int), `gate_violation` (bool),
    `compute_ms` (number|None), `human_wait_ms` (number|None), `measured_tokens` (int|None), `reference_cost` (float|None).
    """
    total = len(records)
    if total == 0:
        raise SpeedyError(ErrorCode.INVALID_INPUT, "Không có bản ghi trial nào để tổng hợp.")

    completed = [r for r in records if bool(r.get("verified_completed"))]
    first_attempt_ok = [r for r in completed if int(r.get("attempts", 1)) == 1]
    violations = sum(1 for r in records if bool(r.get("gate_violation")))

    compute_times = sorted(float(r["compute_ms"]) for r in records if r.get("compute_ms") is not None)
    human_waits = sorted(float(r["human_wait_ms"]) for r in records if r.get("human_wait_ms") is not None)

    all_have_tokens = all(r.get("measured_tokens") is not None for r in records)
    all_have_cost = all(r.get("reference_cost") is not None for r in records)
    token_coverage = round(sum(1 for r in records if r.get("measured_tokens") is not None) / total, 4)

    tokens_per_comp: Optional[float] = None
    if len(completed) > 0 and all_have_tokens:
        total_tokens = sum(int(r["measured_tokens"]) for r in records)
        tokens_per_comp = round(total_tokens / len(completed), 2)

    cost_per_comp: Optional[float] = None
    if len(completed) > 0 and all_have_cost:
        total_cost = sum(float(r["reference_cost"]) for r in records)
        cost_per_comp = round(total_cost / len(completed), 6)

    return {
        "trial_count": total,
        "verified_completed_count": len(completed),
        "verified_completion_rate": round(len(completed) / total, 4),
        "first_attempt_success_rate": round(len(first_attempt_ok) / total, 4),
        "gate_scope_violations": violations,
        "compute_p50_ms": _percentile(compute_times, 50),
        "compute_p95_ms": _percentile(compute_times, 95),
        "human_wait_p50_ms": _percentile(human_waits, 50),
        "token_telemetry_coverage": token_coverage,
        "tokens_per_verified_completion": tokens_per_comp,
        "reference_cost_per_verified_completion": cost_per_comp,
    }


def compare_paired_runs(
    baseline_records: Sequence[Dict[str, Any]],
    candidate_records: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """So sánh ghép cặp theo `task_id` để phát hiện regression (pass-to-pass bị hỏng) và đánh giá tối ưu."""
    base_summary = summarize_trial_records(baseline_records)
    cand_summary = summarize_trial_records(candidate_records)

    base_by_task: Dict[str, List[bool]] = {}
    cand_by_task: Dict[str, List[bool]] = {}
    for r in baseline_records:
        base_by_task.setdefault(str(r["task_id"]), []).append(bool(r.get("verified_completed")))
    for r in candidate_records:
        cand_by_task.setdefault(str(r["task_id"]), []).append(bool(r.get("verified_completed")))

    shared_tasks = sorted(set(base_by_task.keys()) & set(cand_by_task.keys()))
    regressions: List[str] = []
    for tid in shared_tasks:
        base_pass = all(base_by_task[tid])
        cand_pass = all(cand_by_task[tid])
        if base_pass and not cand_pass:
            regressions.append(tid)

    regression_rate = round(len(regressions) / len(shared_tasks), 4) if shared_tasks else 0.0

    # Phân định kết quả tuân thủ bất biến Correctness-First
    if cand_summary["gate_scope_violations"] > 0 or regressions or (
        cand_summary["verified_completion_rate"] < base_summary["verified_completion_rate"]
    ):
        verdict = "REJECT_REGRESSION"
    elif min(base_summary["trial_count"], cand_summary["trial_count"]) < 3:
        verdict = "INCONCLUSIVE_SMALL_SAMPLE"
    else:
        tok_improved = False
        if (
            base_summary["tokens_per_verified_completion"]
            and cand_summary["tokens_per_verified_completion"]
            and cand_summary["tokens_per_verified_completion"] <= 0.8 * base_summary["tokens_per_verified_completion"]
        ):
            tok_improved = True

        lat_improved = False
        if (
            base_summary["compute_p50_ms"]
            and cand_summary["compute_p50_ms"]
            and cand_summary["compute_p50_ms"] <= 0.8 * base_summary["compute_p50_ms"]
        ):
            lat_improved = True

        verdict = "PARETO_IMPROVED" if (tok_improved or lat_improved) else "NEUTRAL_OR_INCONCLUSIVE"

    return {
        "approval_driver": "simulated_test_driver",
        "verdict": verdict,
        "shared_task_count": len(shared_tasks),
        "regressions": regressions,
        "regression_rate": regression_rate,
        "baseline": base_summary,
        "candidate": cand_summary,
    }
