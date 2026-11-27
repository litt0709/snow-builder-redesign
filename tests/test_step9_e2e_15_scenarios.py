"""
Kiểm thử nghiệm thu Bước 9: Đối chiếu trực tiếp toàn bộ 15 kịch bản bắt buộc trong mục 9 `specs/design.md`
cùng bộ Benchmark 20 tác vụ trên 2 tech stack đại diện (Python + TypeScript).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = WORKSPACE_ROOT / "src"
SCRIPTS_DIR = SRC_ROOT / ".speedy" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark import compare_paired_runs  # noqa: E402
from installer_core import apply_install_or_update, export_clean_package  # noqa: E402


def _cli(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    cli_path = ws / ".speedy" / "scripts" / "speedy_cli.py"
    return subprocess.run(
        [sys.executable, str(cli_path), "--workspace", str(ws), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=30,
    )


def _write_handoff(
    ws: Path,
    sid: str,
    stage: str,
    *,
    scope_path: str = "calc/math_ops.py",
    extra_body: str = "",
    summary_override: str | None = None,
) -> None:
    fname_map = {
        "root_cause": "root-cause.md",
        "analyst": "handoff-1-analyst.md",
        "architect": "handoff-2-architect.md",
        "implementer": "handoff-3-implementer.md",
        "reviewer": "handoff-4-reviewer.md",
        "tester": "handoff-5-tester.md",
        "docs": "handoff-6-docs.md",
        "verify_report": "verify-report.md",
    }
    role_sec = ""
    summary = f"Hoàn tất {stage}."
    if stage == "analyst":
        role_sec = f"## Acceptance Criteria\n- AC-001: Hành vi trên `{scope_path}` đạt chuẩn.\n{extra_body}\n"
    elif stage == "architect":
        role_sec = "## ADR\n- Quyết định: Giữ hàm thuần không phụ thuộc ngoài.\n"
    elif stage == "reviewer":
        summary = summary_override if summary_override is not None else "- **Verdict**: `APPROVE`\nKhông phát hiện vi phạm."
    elif stage == "tester":
        role_sec = "## AC Coverage Matrix\n| AC | Result |\n|---|---|\n| AC-001 | PASS |\n"
    if summary_override is not None and stage != "reviewer":
        summary = summary_override

    content = f"""# Handoff — {stage}

## Summary
{summary}

## Scope
- **IN scope**:
  - `{scope_path}`
- **OUT of scope**:
  - Các module khác.

## Risks
- Không có rủi ro mở rộng.

## Dependencies
- Theo kế hoạch session `{sid}`.

## Open questions
Không có

{role_sec}
## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "{stage}",
  "revision": 1,
  "input_refs": [],
  "next_action": "Bước kế tiếp",
  "verification_refs": []
}}
```
"""
    (ws / "ai-workspace" / "sessions" / sid / fname_map[stage]).write_text(content, encoding="utf-8")


class TestStep9AllFifteenScenarios(unittest.TestCase):
    """Kiểm chứng 15/15 kịch bản mục 9 specs/design.md trên gói Speedy copy-out hoàn toàn độc lập."""

    def test_scenarios_1_to_10_end_to_end_on_isolated_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = Path(tmp) / "speedy_pkg"
            app_dir = Path(tmp) / "isolated_app"
            app_dir.mkdir()

            # Kịch bản 10: Product copy-out — đóng gói và cài sang thư mục tách biệt hoàn toàn với Builder
            export_clean_package(SRC_ROOT, pkg_dir)
            (app_dir / "calc").mkdir()
            (app_dir / "calc" / "math_ops.py").write_text(
                "def divide(a: int, b: int) -> float:\n    return a / b\n",
                encoding="utf-8",
            )
            (app_dir / "tests").mkdir()
            (app_dir / "tests" / "test_math.py").write_text(
                "import unittest\nfrom calc.math_ops import divide\n\n"
                "class TestMath(unittest.TestCase):\n"
                "    def test_ac001_divide(self):\n"
                "        self.assertEqual(divide(10, 2), 5.0)\n",
                encoding="utf-8",
            )
            apply_install_or_update(pkg_dir, app_dir, dry_run=False)

            # Kịch bản 1: Setup project mới — scan đúng ngôn ngữ python & unittest, không bịa lint/build không có
            scan_out = json.loads(_cli(app_dir, "scan", ".").stdout)
            self.assertEqual(scan_out["lang"], "python")
            self.assertIsNotNone(scan_out["detected_tooling"]["test"])
            self.assertIsNone(scan_out["detected_tooling"]["lint"])

            # Kịch bản 2, 5, 6, 7, 9: Feature nhỏ + Handoff rỗng bị chặn + Ngoài scope bị chặn + Interrupt/Resume + Audit thiếu usage
            feat_sess = json.loads(
                _cli(
                    app_dir,
                    "session",
                    "new",
                    "--slug",
                    "add-multiply",
                    "--goal",
                    "Thêm hàm multiply vào calc",
                    "--mode",
                    "feature",
                    "--allow-path",
                    "calc",
                    "--allow-path",
                    "tests",
                ).stdout
            )
            fsid = feat_sess["sid"]
            faudit = feat_sess["audit"]["audit_dir"]

            # Kịch bản 6: Handoff rỗng bị validator chặn cứng
            (app_dir / "ai-workspace" / "sessions" / fsid / "handoff-1-analyst.md").write_text(
                "## Summary\n\n## Scope\n\n## Risks\n\n## Dependencies\n\n## Open questions\n",
                encoding="utf-8",
            )
            empty_check = _cli(app_dir, "handoff", "validate", "--sid", fsid, "--stage", "analyst")
            self.assertNotEqual(empty_check.returncode, 0)

            # Kịch bản 7: Handoff khai báo sửa đường dẫn ngoài allowed_paths (`secret_admin/hack.py`) -> bị chặn!
            _write_handoff(app_dir, fsid, "analyst", scope_path="secret_admin/hack.py")
            oos_check = _cli(app_dir, "handoff", "validate", "--sid", fsid, "--stage", "analyst")
            self.assertNotEqual(oos_check.returncode, 0)
            self.assertIn("ngoài allowed_paths", oos_check.stderr)

            # Điền lại đúng scope `calc/math_ops.py` và duyệt Analyst + Architect
            _write_handoff(app_dir, fsid, "analyst", scope_path="calc/math_ops.py")
            _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "analyst", "--status", "running")
            _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "analyst", "--status", "awaiting_approval")
            _cli(app_dir, "gate", "approve", "--sid", fsid, "--stage", "analyst", "--actor", "human", "--interaction-ref", "g1")

            _write_handoff(app_dir, fsid, "architect", scope_path="calc/math_ops.py")
            _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "architect", "--status", "running")
            _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "architect", "--status", "awaiting_approval")
            _cli(app_dir, "gate", "approve", "--sid", fsid, "--stage", "architect", "--actor", "human", "--interaction-ref", "g2")

            # Kịch bản 5: Gián đoạn & Resume — tiếp tục đúng tại `implementer`, giữ nguyên 2 approvals trước đó!
            resumed = json.loads(_cli(app_dir, "session", "resume", "--sid", fsid).stdout)
            self.assertEqual(resumed["current_stage"], "implementer")
            self.assertEqual(resumed["invalidated_stages"], [])

            # Hoàn tất Implementer -> Reviewer -> Tester (chạy verify thật) -> Docs -> Wrapup
            (app_dir / "calc" / "math_ops.py").write_text(
                "def divide(a: int, b: int) -> float:\n    return a / b\n\n"
                "def multiply(a: int, b: int) -> int:\n    return a * b\n",
                encoding="utf-8",
            )
            (app_dir / "tests" / "test_math.py").write_text(
                "import unittest\nfrom calc.math_ops import divide, multiply\n\n"
                "class TestMath(unittest.TestCase):\n"
                "    def test_ac001_divide(self):\n"
                "        self.assertEqual(divide(10, 2), 5.0)\n"
                "    def test_ac002_multiply(self):\n"
                "        self.assertEqual(multiply(3, 4), 12)\n",
                encoding="utf-8",
            )
            for st in ("implementer", "reviewer", "tester", "docs"):
                _write_handoff(app_dir, fsid, st, scope_path="calc/math_ops.py")
                _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", st, "--status", "running")
                _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", st, "--status", "awaiting_approval")
                if st == "implementer":
                    continue
                if st == "tester":
                    vr = _cli(app_dir, "verify", "run", "--sid", fsid)
                    self.assertEqual(vr.returncode, 0, vr.stderr)
                _cli(app_dir, "gate", "approve", "--sid", fsid, "--stage", st, "--actor", "human", "--interaction-ref", f"g-{st}")

            _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "wrapup", "--status", "running")
            feat_done = json.loads(
                _cli(app_dir, "state", "transition", "--sid", fsid, "--stage", "wrapup", "--status", "approved").stdout
            )
            self.assertEqual(feat_done["session_status"], "completed")

            # Kịch bản 9: Audit thiếu usage -> hiện null & not_measured, không có token/cost giả
            aud_fin = json.loads(_cli(app_dir, "audit", "finalize", "--audit-dir", faudit, "--outcome", "success").stdout)
            self.assertEqual(aud_fin["usage_source"], "not_measured")
            self.assertIsNone(aud_fin["total_tokens"])
            self.assertIsNone(aud_fin["total_estimated_cost"])

            # Kịch bản 3: Fix có regression — tái hiện test FAIL trước khi sửa -> sửa lỗi chia cho 0 -> test PASS sau sửa!
            fix_sess = json.loads(
                _cli(app_dir, "session", "new", "--slug", "fix-div-zero", "--goal", "Sửa lỗi chia cho 0", "--mode", "fix").stdout
            )
            xsid = fix_sess["sid"]
            # Thêm regression test trước khi sửa -> verify run PHẢI FAIL!
            (app_dir / "tests" / "test_math.py").write_text(
                "import unittest\nfrom calc.math_ops import divide\n\n"
                "class TestMath(unittest.TestCase):\n"
                "    def test_div_zero_raises_value_error(self):\n"
                "        with self.assertRaises(ValueError):\n"
                "            divide(10, 0)\n",
                encoding="utf-8",
            )
            fail_before_fix = _cli(app_dir, "verify", "run", "--sid", xsid)
            self.assertNotEqual(fail_before_fix.returncode, 0, "Test tái hiện lỗi phải FAIL trước khi sửa!")

            # Áp dụng bản vá -> verify run PASS!
            (app_dir / "calc" / "math_ops.py").write_text(
                "def divide(a: int, b: int) -> float:\n"
                "    if b == 0:\n        raise ValueError('Cannot divide by zero')\n"
                "    return a / b\n",
                encoding="utf-8",
            )
            pass_after_fix = _cli(app_dir, "verify", "run", "--sid", xsid)
            self.assertEqual(pass_after_fix.returncode, 0, pass_after_fix.stderr)

            # Kịch bản 4: Verify-only — không sửa bất kỳ dòng code nào của ứng dụng
            snap_before = (app_dir / "calc" / "math_ops.py").read_bytes()
            ver_sess = json.loads(
                _cli(app_dir, "session", "new", "--slug", "verify-math", "--goal", "Kiểm tra module calc", "--mode", "verify").stdout
            )
            vsid = ver_sess["sid"]
            _write_handoff(app_dir, vsid, "reviewer")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "reviewer", "--status", "running")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "reviewer", "--status", "awaiting_approval")
            _cli(app_dir, "gate", "approve", "--sid", vsid, "--stage", "reviewer", "--actor", "human", "--interaction-ref", "v1")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "tester", "--status", "skipped")
            _write_handoff(app_dir, vsid, "verify_report")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "verify_report", "--status", "running")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "verify_report", "--status", "awaiting_approval")
            _cli(app_dir, "gate", "approve", "--sid", vsid, "--stage", "verify_report", "--actor", "human", "--interaction-ref", "v2")
            _cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "wrapup", "--status", "running")
            ver_done = json.loads(_cli(app_dir, "state", "transition", "--sid", vsid, "--stage", "wrapup", "--status", "approved").stdout)
            self.assertEqual(ver_done["session_status"], "completed")
            self.assertEqual((app_dir / "calc" / "math_ops.py").read_bytes(), snap_before)

            # Kịch bản 8: Cài lại / Update không mất runtime sessions vừa tạo ở trên
            reinst = apply_install_or_update(pkg_dir, app_dir, dry_run=False)
            self.assertTrue(reinst["applied"])
            self.assertTrue((app_dir / "ai-workspace" / "sessions" / fsid / "state.json").is_file())

    def test_scenarios_11_to_15_stale_budget_assumptions_laundering_and_20_task_benchmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg_dir = Path(tmp) / "speedy_pkg"
            ws = Path(tmp) / "polyglot_app"
            ws.mkdir()
            export_clean_package(SRC_ROOT, pkg_dir)
            apply_install_or_update(pkg_dir, ws, dry_run=False)

            # Tạo dự án đại diện 2 tech stack: Python backend (5 services) + TypeScript frontend (5 modules)
            py_mods = ("auth_api", "billing_api", "orders_api", "inventory_api", "shipping_api")
            ts_mods = ("checkout_ui", "profile_ui", "catalog_ui", "analytics_ui", "notifications_ui")
            for pm in py_mods:
                d = ws / "services" / pm
                d.mkdir(parents=True)
                (d / "app.py").write_text(f"# {pm}\n" + ("def handle(req):\n    return req\n" * 60), encoding="utf-8")
            for tm in ts_mods:
                d = ws / "packages" / tm
                d.mkdir(parents=True)
                (d / "index.ts").write_text(f"// {tm}\n" + ("export const render = () => true;\n" * 60), encoding="utf-8")

            # Kịch bản 13: Context/knowledge mismatch — gắn nhãn [ASSUMPTION] rõ ràng & phát hiện doc stale khi sửa source
            stamp = json.loads(_cli(ws, "knowledge", "stamp-ref", "--source", "services/auth_api/app.py").stdout)["source_ref_line"]
            (ws / "ai-workspace" / "docs" / "architecture" / "services-auth-api.md").write_text(
                f"# Auth API\n{stamp}\n", encoding="utf-8"
            )
            (ws / "services" / "auth_api" / "app.py").write_text("# Modified auth\ndef handle(req):\n    return None\n", encoding="utf-8")
            fresh = json.loads(_cli(ws, "knowledge", "check-freshness").stdout)
            self.assertEqual(fresh["stale_count"], 1)

            sess = json.loads(_cli(ws, "session", "new", "--slug", "assump-check", "--goal", "Kiểm tra giả định auth").stdout)
            sid = sess["sid"]
            _write_handoff(
                ws,
                sid,
                "analyst",
                scope_path="services/auth_api/app.py",
                extra_body="- [ASSUMPTION] Chưa xác minh TTL của refresh token.",
            )
            pkt = json.loads(_cli(ws, "context", "prepare", "--sid", sid, "--stage", "architect").stdout)
            self.assertEqual(len(pkt["open_assumptions"]), 1)

            # Kịch bản 14: Test Laundering bị chặn trực tiếp trong `verify run` khi truyền diff thêm @skip!
            bad_patch = ws / "ai-workspace" / "tmp" / "launder.diff"
            bad_patch.write_text(
                "--- a/tests/test_auth.py\n+++ b/tests/test_auth.py\n@@ -1,3 +1,4 @@\n+@pytest.mark.skip('hide broken test')\n def test_token():\n     assert True\n",
                encoding="utf-8",
            )
            launder_run = _cli(
                ws,
                "verify",
                "run",
                "--sid",
                sid,
                "--diff-file",
                "ai-workspace/tmp/launder.diff",
                "--check",
                f"unit_integration={sys.executable} -c \"print('green')\"",
            )
            self.assertNotEqual(launder_run.returncode, 0)
            self.assertIn("VERIFICATION_FAILED", launder_run.stderr)

            # Kịch bản 15: Suite Benchmark 20 tasks trên 2 tech stack (10 dev + 10 held_out) + Paired Comparison
            tasks_20 = []
            all_mods = [(f"services/{m}", m) for m in py_mods] + [(f"packages/{m}", m) for m in ts_mods]
            for idx, (mpath, mname) in enumerate(all_mods):
                # 1 task feature + 1 task fix/verify cho mỗi module -> tổng cộng 20 tasks!
                split = "dev" if idx < 5 else "held_out"
                tasks_20.append(
                    {
                        "id": f"T-{idx * 2 + 1:02d}",
                        "split": split,
                        "prompt": f"Thêm tính năng mới cho module {mname}",
                        "query": mname,
                        "expected_mode": "feature",
                        "oracle_modules": [mpath],
                    }
                )
                is_auth = "auth" in mname
                tasks_20.append(
                    {
                        "id": f"T-{idx * 2 + 2:02d}",
                        "split": split,
                        "prompt": (
                            f"Sửa nhanh lỗi token trong {mname}" if is_auth else f"Kiểm tra chất lượng code module {mname}"
                        ),
                        "query": mname,
                        "target_paths": [f"{mpath}/app.py"] if is_auth else None,
                        "expected_mode": "fix" if is_auth else "verify",
                        "oracle_modules": [mpath],
                    }
                )

            tfile = ws / "ai-workspace" / "tmp" / "suite20.json"
            tfile.write_text(json.dumps({"tasks": tasks_20}, ensure_ascii=False), encoding="utf-8")
            bm_proc = _cli(ws, "benchmark", "suite", "--tasks-file", "ai-workspace/tmp/suite20.json")
            self.assertEqual(bm_proc.returncode, 0, bm_proc.stderr)
            bm = json.loads(bm_proc.stdout)
            self.assertEqual(bm["overall"]["task_count"], 20)
            self.assertEqual(bm["dev"]["task_count"], 10)
            self.assertEqual(bm["held_out"]["task_count"], 10)
            self.assertEqual(bm["overall"]["routing_accuracy"], 1.0)
            self.assertEqual(bm["overall"]["oracle_recall_rate"], 1.0)
            self.assertGreaterEqual(bm["overall"]["mean_bytes_reduction_ratio"], 0.75)

            # Kiểm chứng thêm Kịch bản 11 & 12 qua paired comparison không cho phép vi phạm gate/scope
            violating_cand = [
                {"task_id": "T-01", "verified_completed": True, "attempts": 1, "gate_violation": True, "measured_tokens": 2000, "compute_ms": 800},
                {"task_id": "T-02", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 2000, "compute_ms": 800},
                {"task_id": "T-03", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 2000, "compute_ms": 800},
            ]
            clean_base = [
                {"task_id": "T-01", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 5000, "compute_ms": 2000},
                {"task_id": "T-02", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 5000, "compute_ms": 2000},
                {"task_id": "T-03", "verified_completed": True, "attempts": 1, "gate_violation": False, "measured_tokens": 5000, "compute_ms": 2000},
            ]
            self.assertEqual(compare_paired_runs(clean_base, violating_cand)["verdict"], "REJECT_REGRESSION")

    def test_reviewer_regression_guards_and_schemas(self) -> None:
        """Kiểm định hồi quy cho toàn bộ 9 phát hiện từ Independent System Reviewer (H-01..L-02)."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            ws.mkdir()
            apply_install_or_update(SRC_ROOT, ws, dry_run=False)
            (ws / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

            # M-04b: SPEEDY_GATE_POLICY trong ai-workspace/.env được áp dụng khi không truyền --policy
            (ws / "ai-workspace" / ".env").write_text("SPEEDY_GATE_POLICY=balanced\n", encoding="utf-8")
            p_env = _cli(ws, "session", "new", "--slug", "env-pol", "--goal", "Kiểm tra policy env", "--mode", "verify")
            self.assertEqual(p_env.returncode, 0, p_env.stderr)
            self.assertEqual(json.loads(p_env.stdout)["policy"], "balanced")

            # H-02: Verify mode cho phép approve reviewer có REQUEST_CHANGES để đi tiếp sang tester
            sid_ver = json.loads(p_env.stdout)["sid"]
            _cli(ws, "state", "transition", "--sid", sid_ver, "--stage", "reviewer", "--status", "running")
            _write_handoff(
                ws,
                sid_ver,
                "reviewer",
                scope_path="app.py",
                summary_override="- **Verdict**: `REQUEST_CHANGES`\nPhát hiện lỗ hổng cần kiểm chứng thêm bằng tester (không thể APPROVE lúc này).",
            )
            _cli(ws, "state", "transition", "--sid", sid_ver, "--stage", "reviewer", "--status", "awaiting_approval")
            ok_ver_gate = _cli(
                ws,
                "gate",
                "approve",
                "--sid",
                sid_ver,
                "--stage",
                "reviewer",
                "--actor",
                "human",
                "--interaction-ref",
                "ask#ver1",
            )
            self.assertEqual(ok_ver_gate.returncode, 0, ok_ver_gate.stderr)
            self.assertEqual(json.loads(ok_ver_gate.stdout)["current_stage"], "tester")

            # H-02 (feature mode): Spoof chữ "APPROVE" trong prose khi Verdict là REQUEST_CHANGES vẫn bị chặn!
            p_feat = _cli(ws, "session", "new", "--slug", "h01-h02", "--goal", "Thêm tính năng H01 H02", "--mode", "feature", "--policy", "strict")
            sid = json.loads(p_feat.stdout)["sid"]
            for stg in ("analyst", "architect"):
                _cli(ws, "state", "transition", "--sid", sid, "--stage", stg, "--status", "running")
                _write_handoff(ws, sid, stg, scope_path="app.py")
                _cli(ws, "state", "transition", "--sid", sid, "--stage", stg, "--status", "awaiting_approval")
                _cli(ws, "gate", "approve", "--sid", sid, "--stage", stg, "--actor", "human", "--interaction-ref", f"ask#{stg}")

            # M-02: UoW hoàn tất giải phóng slot max_parallel_workers
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "implementer", "--status", "running")
            u1 = _cli(ws, "state", "uow", "--sid", sid, "--uow-id", "U1", "--stage", "implementer", "--objective", "A", "--write-path", "a.py")
            u2 = _cli(ws, "state", "uow", "--sid", sid, "--uow-id", "U2", "--stage", "implementer", "--objective", "B", "--write-path", "b.py")
            self.assertEqual(u1.returncode, 0, u1.stderr)
            self.assertEqual(u2.returncode, 0, u2.stderr)
            u_done = _cli(ws, "state", "uow", "--sid", sid, "--uow-id", "U1", "--status", "completed")
            self.assertEqual(u_done.returncode, 0, u_done.stderr)
            u3 = _cli(ws, "state", "uow", "--sid", sid, "--uow-id", "U3", "--stage", "implementer", "--objective", "C", "--write-path", "a.py")
            self.assertEqual(u3.returncode, 0, u3.stderr)

            _write_handoff(ws, sid, "implementer", scope_path="app.py")
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "implementer", "--status", "awaiting_approval")

            _cli(ws, "state", "transition", "--sid", sid, "--stage", "reviewer", "--status", "running")
            _write_handoff(
                ws,
                sid,
                "reviewer",
                scope_path="app.py",
                summary_override="- **Verdict**: `REQUEST_CHANGES`\nKhông thể APPROVE trước khi sửa lỗi biên.",
            )
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "reviewer", "--status", "awaiting_approval")
            spoof_gate = _cli(
                ws,
                "gate",
                "approve",
                "--sid",
                sid,
                "--stage",
                "reviewer",
                "--actor",
                "human",
                "--interaction-ref",
                "ask#spoof",
            )
            self.assertNotEqual(spoof_gate.returncode, 0)
            self.assertIn("CONTRACT_VIOLATION", spoof_gate.stderr)

            # Sửa verdict thành APPROVE để đi tiếp tới tester & wrapup test H-01
            _cli(ws, "gate", "reject", "--sid", sid, "--stage", "reviewer", "--actor", "human", "--interaction-ref", "ask#rej", "--feedback", "Sửa xong", "--return-to", "reviewer")
            _write_handoff(ws, sid, "reviewer", scope_path="app.py", summary_override="- **Verdict**: `APPROVE`")
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "reviewer", "--status", "awaiting_approval")
            self.assertEqual(
                _cli(ws, "gate", "approve", "--sid", sid, "--stage", "reviewer", "--actor", "human", "--interaction-ref", "ask#revok").returncode,
                0,
            )

            # H-01a: Verify FAIL không được phép wrapup approved
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "tester", "--status", "running")
            fail_v = _cli(ws, "verify", "run", "--sid", sid, "--check", f"unit_integration={sys.executable} -c \"import sys; sys.exit(1)\"")
            self.assertNotEqual(fail_v.returncode, 0)
            _write_handoff(ws, sid, "tester", scope_path="app.py")
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "tester", "--status", "awaiting_approval")
            _cli(ws, "gate", "approve", "--sid", sid, "--stage", "tester", "--actor", "human", "--interaction-ref", "ask#tst")
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "docs", "--status", "running")
            _write_handoff(ws, sid, "docs", scope_path="app.py")
            _cli(ws, "state", "transition", "--sid", sid, "--stage", "docs", "--status", "awaiting_approval")
            _cli(ws, "gate", "approve", "--sid", sid, "--stage", "docs", "--actor", "human", "--interaction-ref", "ask#docs")

            _cli(ws, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "running")
            wrap_fail = _cli(ws, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "approved")
            self.assertNotEqual(wrap_fail.returncode, 0)
            self.assertIn("VERIFICATION_FAILED", wrap_fail.stderr)

            # H-01b: Verify PASS nhưng code bị sửa sau đó (stale snapshot) -> vẫn bị chặn ở wrapup!
            pass_v = _cli(ws, "verify", "run", "--sid", sid, "--check", f"unit_integration={sys.executable} -c \"print('ok')\"")
            self.assertEqual(pass_v.returncode, 0, pass_v.stderr)
            (ws / "app.py").write_text("def add(a, b):\n    return a + b + 1\n", encoding="utf-8")
            wrap_stale = _cli(ws, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "approved")
            self.assertNotEqual(wrap_stale.returncode, 0)
            self.assertIn("VERIFICATION_FAILED", wrap_stale.stderr)

            # Chạy lại verify PASS trên snapshot mới -> wrapup thành công!
            pass_v2 = _cli(ws, "verify", "run", "--sid", sid, "--check", f"unit_integration={sys.executable} -c \"print('ok')\"")
            self.assertEqual(pass_v2.returncode, 0, pass_v2.stderr)
            wrap_ok = _cli(ws, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "approved")
            self.assertEqual(wrap_ok.returncode, 0, wrap_ok.stderr)

            # M-03: Chặn path traversal trên CLI (audit, verify --diff-file, benchmark)
            trav_aud = _cli(ws, "audit", "event", "--audit-dir", "../../etc", "--agent", "x")
            self.assertNotEqual(trav_aud.returncode, 0)
            self.assertIn("SCOPE_VIOLATION", trav_aud.stderr)
            trav_bm = _cli(ws, "benchmark", "suite", "--tasks-file", "../../etc/passwd")
            self.assertNotEqual(trav_bm.returncode, 0)
            self.assertIn("SCOPE_VIOLATION", trav_bm.stderr)

            # M-04a: --skip-conflicts bảo toàn hash cũ trong manifest để lần cập nhật sau vẫn phát hiện xung đột
            agents_md = ws / "AGENTS.md"
            agents_md.write_text("# Custom user AGENTS.md\n", encoding="utf-8")
            upd_skip = apply_install_or_update(SRC_ROOT, ws, dry_run=False, allow_with_conflicts_skipped=True)
            self.assertEqual(upd_skip["skipped_conflicts_count"], 1)
            upd_next = apply_install_or_update(SRC_ROOT, ws, dry_run=True)
            self.assertEqual(len(upd_next["plan"]["conflicts"]), 1)

            # M-05: Layout builder cleanup --include-logs không đụng vào logs/audit khi --include-audit=False
            b_ws = Path(tmp) / "builder_sim"
            (b_ws / "src" / ".speedy" / "scripts").mkdir(parents=True)
            (b_ws / "logs" / "audit" / "2020-01-01-old").mkdir(parents=True)
            (b_ws / "logs" / "audit" / "2020-01-01-old" / "01-input-context.json").write_text("{}", encoding="utf-8")
            (b_ws / "logs" / "2020-01-01-app.log").write_text("old", encoding="utf-8")
            cl_res = _cli(ws, "--workspace", str(b_ws), "--layout", "builder", "cleanup", "--older-than", "0", "--include-logs")
            self.assertEqual(cl_res.returncode, 0, cl_res.stderr)
            cl_data = json.loads(cl_res.stdout)
            self.assertEqual(cl_data["candidates"]["logs"], ["logs/2020-01-01-app.log"])
            self.assertEqual(cl_data["candidates"]["audit"], [])

            # L-02: Mọi JSON schema trong src/.speedy/schemas/ đều hợp lệ và có metadata JSON Schema
            schema_files = sorted((SRC_ROOT / ".speedy" / "schemas").glob("*.schema.json"))
            self.assertEqual(len(schema_files), 4)
            for sf in schema_files:
                sdata = json.loads(sf.read_text(encoding="utf-8"))
                self.assertIn("$schema", sdata)
                self.assertIn("required", sdata)


if __name__ == "__main__":
    unittest.main()
