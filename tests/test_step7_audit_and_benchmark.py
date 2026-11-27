"""Kiểm thử nghiệm thu Bước 7: Audit Edge Cases (Unpriced Model, Corrupted JSON, XSS, Zero Completion) & Benchmark Suite."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = WORKSPACE_ROOT / "src"
SCRIPTS_DIR = SRC_ROOT / ".speedy" / "scripts"
CLI_PATH = SCRIPTS_DIR / "speedy_cli.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark import compare_paired_runs, summarize_trial_records  # noqa: E402


def _cli(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), "--workspace", str(ws), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )


class TestStep7AuditAndBenchmark(unittest.TestCase):
    def test_audit_unpriced_model_corrupted_json_secret_masking_and_xss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)

            # 1. Tạo session chứa chuỗi XSS và secret để kiểm tra redaction & HTML escaping
            s_res = json.loads(
                _cli(
                    ws,
                    "session",
                    "new",
                    "--slug",
                    "xss-task",
                    "--goal",
                    "Fix <img src=x onerror=alert(1)> password=super_secret_pw",
                ).stdout
            )
            audit_dir = s_res["audit"]["audit_dir"]

            # 2. Finalize với một model chưa có trong bảng giá -> total_estimated_cost PHẢI là null, không đoán giá!
            unpriced_usage = json.dumps(
                [
                    {
                        "agent": "architect",
                        "model": "gemini-99-unpriced-preview",
                        "input_tokens": 5000,
                        "output_tokens": 1200,
                    }
                ]
            )
            fin = json.loads(
                _cli(
                    ws,
                    "audit",
                    "finalize",
                    "--audit-dir",
                    audit_dir,
                    "--usage-json",
                    unpriced_usage,
                    "--usage-source",
                    "test_meter",
                ).stdout
            )
            self.assertEqual(fin["total_tokens"], 6200)
            self.assertIsNone(fin["total_estimated_cost"])
            self.assertIn("gemini-99-unpriced-preview", fin["unpriced_models"])

            # 3. Giả lập một thư mục audit khác có JSON bị hỏng -> audit-view vẫn chạy tốt không bị crash!
            broken_dir = ws / "ai-workspace" / "audit" / f"{s_res['sid'][:10]}-corrupted-run"
            broken_dir.mkdir(parents=True, exist_ok=True)
            (broken_dir / "01-input-context.json").write_text("{corrupted_json_here", encoding="utf-8")

            av = _cli(ws, "audit-view", "--month", s_res["sid"][:7], "--no-open")
            self.assertEqual(av.returncode, 0, av.stderr)
            av_json = json.loads(av.stdout)
            self.assertEqual(av_json["tasks"], 1)
            html_out = Path(av_json["path"]).read_text(encoding="utf-8")
            self.assertNotIn("super_secret_pw", html_out)
            self.assertNotIn("<img src=x", html_out)

    def test_benchmark_zero_completion_undefined_and_paired_regression_vs_pareto(self) -> None:
        # 1. Không có trial nào hoàn tất -> tokens_per_verified_completion phải là None (không phải 0!)
        zero_summary = summarize_trial_records(
            [
                {"task_id": "T1", "verified_completed": False, "attempts": 3, "measured_tokens": 12000, "compute_ms": 5000},
            ]
        )
        self.assertIsNone(zero_summary["tokens_per_verified_completion"])

        # 2. Candidate tiết kiệm 40% token và giữ nguyên 100% pass (>= 3 trials) -> PARETO_IMPROVED
        base_trials = [
            {"task_id": "T1", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 10000, "compute_ms": 4000},
            {"task_id": "T2", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 12000, "compute_ms": 5000},
            {"task_id": "T3", "verified_completed": True, "attempts": 2, "gate_violation": False, "measured_tokens": 14000, "compute_ms": 6000},
        ]
        cand_good = [
            {"task_id": "T1", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 5000, "compute_ms": 2500},
            {"task_id": "T2", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 6000, "compute_ms": 3000},
            {"task_id": "T3", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 7000, "compute_ms": 3200},
        ]
        cmp_good = compare_paired_runs(base_trials, cand_good)
        self.assertEqual(cmp_good["verdict"], "PARETO_IMPROVED")
        self.assertEqual(cmp_good["regression_rate"], 0.0)

        # 3. Candidate nhanh hơn nhưng làm gãy T2 (pass-to-pass regression) -> REJECT_REGRESSION ngay lập tức!
        cand_regressed = [
            {"task_id": "T1", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 3000, "compute_ms": 1000},
            {"task_id": "T2", "verified_completed": False, "attempts": 3, "gate_violation": False, "measured_tokens": 3000, "compute_ms": 1000},
            {"task_id": "T3", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 3000, "compute_ms": 1000},
        ]
        cmp_bad = compare_paired_runs(base_trials, cand_regressed)
        self.assertEqual(cmp_bad["verdict"], "REJECT_REGRESSION")
        self.assertIn("T2", cmp_bad["regressions"])

    def test_cli_context_funnel_benchmark_dev_and_held_out_splits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "multi_service_app"
            shutil.copytree(SRC_ROOT, ws)
            # Tạo 8 modules có kích thước đáng kể để kiểm chứng khả năng cắt giảm > 60% bytes mà vẫn đạt 100% oracle recall
            for mod in ("auth", "billing", "catalog", "inventory", "notification", "reporting", "search", "shipping"):
                mdir = ws / "services" / mod
                mdir.mkdir(parents=True, exist_ok=True)
                (mdir / "main.py").write_text(
                    f"# Module {mod}\n" + ("def helper_fn(x):\n    return x + 1\n" * 80),
                    encoding="utf-8",
                )

            suite_payload = {
                "tasks": [
                    {
                        "id": "BM-01",
                        "split": "dev",
                        "prompt": "Thêm tính năng chiết khấu hóa đơn cho billing",
                        "query": "billing",
                        "expected_mode": "feature",
                        "oracle_modules": ["services/billing"],
                    },
                    {
                        "id": "BM-02",
                        "split": "dev",
                        "prompt": "Sửa nhanh lỗi jwt token hết hạn",
                        "query": "auth",
                        "target_paths": ["services/auth/main.py"],
                        "expected_mode": "fix",
                        "oracle_modules": ["services/auth"],
                    },
                    {
                        "id": "BM-03",
                        "split": "held_out",
                        "prompt": "Kiểm tra tồn kho kho hàng",
                        "query": "inventory",
                        "expected_mode": "verify",
                        "oracle_modules": ["services/inventory"],
                    },
                    {
                        "id": "BM-04",
                        "split": "held_out",
                        "prompt": "Thêm phương thức giao hàng hỏa tốc",
                        "query": "shipping",
                        "expected_mode": "feature",
                        "oracle_modules": ["services/shipping"],
                    },
                ]
            }
            tasks_path = ws / "ai-workspace" / "tmp" / "bench_tasks.json"
            tasks_path.write_text(json.dumps(suite_payload, ensure_ascii=False), encoding="utf-8")

            res = _cli(ws, "benchmark", "suite", "--tasks-file", "ai-workspace/tmp/bench_tasks.json")
            self.assertEqual(res.returncode, 0, res.stderr)
            report = json.loads(res.stdout)
            self.assertEqual(report["overall"]["routing_accuracy"], 1.0)
            self.assertEqual(report["overall"]["oracle_recall_rate"], 1.0)
            self.assertEqual(report["held_out"]["oracle_recall_rate"], 1.0)
            self.assertGreaterEqual(report["overall"]["mean_bytes_reduction_ratio"], 0.65)


if __name__ == "__main__":
    unittest.main()
