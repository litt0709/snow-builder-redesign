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

    def test_auto_stage_verification_git_telemetry_and_viewer_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)
            # Khởi tạo git repo để kiểm tra tự đo files_changed
            subprocess.run(["git", "init", "-q"], cwd=str(ws), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(ws), check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(ws), check=True)
            (ws / "app.py").write_text("x = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "app.py"], cwd=str(ws), check=True)
            subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(ws), check=True)

            s_res = json.loads(
                _cli(ws, "session", "new", "--slug", "auto-tel", "--goal", "Add health endpoint").stdout
            )
            sid = s_res["sid"]
            audit_dir = ws / s_res["audit"]["audit_dir"]

            # Ghi handoff analyst hợp lệ và chạy state complete -> tự ghi stage telemetry + models_by_agent!
            (ws / "ai-workspace" / "sessions" / sid / "handoff-1-analyst.md").write_text(
                f"# Brief\n\n## Summary\nAdd health.\n\n## Scope\n- app.py\n\n### Acceptance Criteria\n- **AC-001**: OK.\n\n"
                f"## Risks\nLow.\n\n## Dependencies\nNone.\n\n## Open questions\nKhông có.\n\n"
                f"## Resume Metadata\n```json\n{{\"sid\":\"{sid}\",\"stage\":\"analyst\",\"revision\":1,\"input_refs\":[],\"next_action\":\"architect\",\"verification_refs\":[]}}\n```\n",
                encoding="utf-8",
            )
            cmp_res = _cli(ws, "state", "complete", "--sid", sid, "--stage", "analyst")
            self.assertEqual(cmp_res.returncode, 0, cmp_res.stderr)

            f01 = json.loads((audit_dir / "01-input-context.json").read_text(encoding="utf-8"))
            f02 = json.loads((audit_dir / "02-behavior-trace.json").read_text(encoding="utf-8"))
            self.assertIn("analyst", f01["ai_agent_configuration"]["models_by_agent"])
            self.assertGreaterEqual(len(f02["execution_trace"]["steps"]), 1)

            # Chỉnh sửa app.py và chạy verify run -> tự sync unit_test_result & tool_time_ms!
            (ws / "app.py").write_text("x = 2\n", encoding="utf-8")
            ver = _cli(ws, "verify", "run", "--sid", sid, "--check", f"unit_integration={sys.executable} -c \"assert 1==1\"")
            self.assertEqual(ver.returncode, 0, ver.stderr)
            f03 = json.loads((audit_dir / "03-verification-results.json").read_text(encoding="utf-8"))
            self.assertEqual(f03["quality_verification"]["unit_test_result"]["status"], "pass")

            # Finalize không truyền --files-changed -> tự đo app.py qua git!
            fin = json.loads(
                _cli(ws, "audit", "finalize", "--audit-dir", s_res["audit"]["audit_dir"], "--outcome", "success", "--completion-level", "verified", "--ac-passed", "1", "--ac-total", "1").stdout
            )
            self.assertTrue(fin["finalized"])
            f03_after = json.loads((audit_dir / "03-verification-results.json").read_text(encoding="utf-8"))
            self.assertEqual(f03_after["repository_changes"]["change_measurement_status"], "measured")
            self.assertEqual(f03_after["repository_changes"]["files_changed"], 1)
            self.assertIn("app.py", f03_after["repository_changes"]["changed_file_paths"])

            # Audit-view hiển thị đầy đủ Model usage, Step summary (không cột token null), Unit test = pass, Files changed = 1
            av = json.loads(_cli(ws, "audit-view", "--month", sid[:7], "--no-open").stdout)
            html_out = Path(av["path"]).read_text(encoding="utf-8")
            self.assertIn("Gemini Neon", html_out)
            self.assertIn("analyst", html_out)
            self.assertIn("N/A", html_out)
            self.assertNotIn("<th>Input</th>", html_out)

    def test_antigravity_transcript_auto_metering_and_pricing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)
            brain_dir = Path(tmp) / "fake_brain"
            log_dir = brain_dir / "conv-1234" / ".system_generated" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            s_res = json.loads(
                _cli(ws, "session", "new", "--slug", "meter-test", "--goal", "Test token metering").stdout
            )
            sid = s_res["sid"]
            audit_dir_rel = s_res["audit"]["audit_dir"]
            f01 = json.loads((ws / audit_dir_rel / "01-input-context.json").read_text(encoding="utf-8"))
            started_at = f01["task_identity"]["started_at"]

            # Ghi mock transcript.jsonl giống định dạng thật của Antigravity IDE
            (log_dir / "transcript.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"step_index": 1, "type": "TOOL_OUTPUT", "content": f"sid={sid}"}),
                        json.dumps(
                            {
                                "step_index": 2,
                                "type": "PLANNER_RESPONSE",
                                "status": "DONE",
                                "created_at": started_at,
                                "model": "gemini-4-neon-medium",
                                "input_tokens": 10000,
                                "cache_read_tokens": 20000,
                                "output_tokens": 2000,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            env_with_brain = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "ANTIGRAVITY_BRAIN_DIR": str(brain_dir)}
            fin_proc = subprocess.run(
                [
                    sys.executable,
                    str(CLI_PATH),
                    "--workspace",
                    str(ws),
                    "audit",
                    "finalize",
                    "--audit-dir",
                    audit_dir_rel,
                    "--outcome",
                    "success",
                    "--completion-level",
                    "verified",
                ],
                capture_output=True,
                text=True,
                env=env_with_brain,
                timeout=20,
            )
            self.assertEqual(fin_proc.returncode, 0, fin_proc.stderr)
            fin = json.loads(fin_proc.stdout)
            self.assertEqual(fin["usage_source"], "antigravity_transcript")
            # total_tokens = (fresh 10000 + cached 20000) + output 2000 = 32000
            self.assertEqual(fin["total_tokens"], 32000)
            # cost = (10000/1e6)*0.5 + (20000/1e6)*0.125 + (2000/1e6)*3.0 = 0.005 + 0.0025 + 0.006 = 0.0135
            self.assertAlmostEqual(fin["total_estimated_cost"], 0.0135, places=6)


if __name__ == "__main__":
    unittest.main()
