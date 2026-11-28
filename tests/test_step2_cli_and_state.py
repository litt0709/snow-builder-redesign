"""Kiểm thử toàn diện Bước 2: Deterministic CLI, Canonical State Machine, Gate, Context, Verify & Audit."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = WORKSPACE_ROOT / "src" / ".speedy" / "scripts"
CLI_PATH = SCRIPTS_DIR / "speedy_cli.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from contracts import ErrorCode, SpeedyError, resolve_layout, resolve_within_scope  # noqa: E402
from lifecycle import (  # noqa: E402
    create_session,
    record_gate_decision,
    register_worker_uow,
    resume_session,
    transition_stage,
)
from storage import session_dir_for, session_lock  # noqa: E402
from verification import detect_test_laundering  # noqa: E402


def _make_temp_product_workspace(tmp_dir: str) -> Path:
    ws = Path(tmp_dir) / "app"
    shutil.copytree(WORKSPACE_ROOT / "src", ws)
    (ws / "payments").mkdir(parents=True, exist_ok=True)
    (ws / "payments" / "main.py").write_text("def charge(amount: int) -> int:\n    return amount\n", encoding="utf-8")
    return ws


def _run_cli(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, str(CLI_PATH), "--workspace", str(ws), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _valid_analyst_md(sid: str, extra_summary: str = "Phân tích luồng thanh toán.") -> str:
    return f"""# Handoff 1 — Analyst

- **Updated At**: `2026-11-27T20:00:00Z`

## Summary
{extra_summary}

## Scope
- **IN scope**:
  - `payments/main.py`
- **OUT of scope**:
  - Không sửa module khác.

## Risks
- Rủi ro làm tròn số tiền -> kiểm tra kiểu int.

## Dependencies
- Không phụ thuộc dịch vụ ngoài.

## Open questions
Không có

## Acceptance Criteria
- AC-001: Hàm `charge(100)` trả về `100`.

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "analyst",
  "revision": 1,
  "input_refs": [],
  "next_action": "Chuyển sang Architect",
  "verification_refs": []
}}
```
"""


def _valid_architect_md(sid: str) -> str:
    return f"""# Handoff 2 — Architect

## Summary
Thiết kế interface thanh toán đơn giản, rõ ràng.

## Scope
- `payments/main.py`

## Risks
- Tương thích ngược hoàn toàn.

## Dependencies
- Input từ Analyst.

## Open questions
Không có

## ADR
- **Quyết định**: Giữ hàm thuần túy `charge(amount: int) -> int` có kiểm tra âm.

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "architect",
  "revision": 1,
  "input_refs": ["ai-workspace/sessions/{sid}/handoff-1-analyst.md"],
  "next_action": "Chuyển sang Implementer",
  "verification_refs": []
}}
```
"""


def _valid_implementer_md(sid: str) -> str:
    return f"""# Handoff 3 — Implementer

## Summary
Đã cập nhật `payments/main.py` đúng thiết kế.

## Scope
- `payments/main.py`

## Risks
- Không có rủi ro mở rộng.

## Dependencies
- Thiết kế từ Architect.

## Open questions
Không có

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "implementer",
  "revision": 1,
  "input_refs": ["ai-workspace/sessions/{sid}/handoff-2-architect.md"],
  "next_action": "Chuyển sang Reviewer",
  "verification_refs": []
}}
```
"""


def _valid_reviewer_md(sid: str, verdict: str = "APPROVE") -> str:
    return f"""# Handoff 4 — Reviewer

## Summary
- **Verdict**: `{verdict}`
- Đã kiểm tra độc lập mã nguồn đối chiếu với AC-001 và ADR.

## Scope
- `payments/main.py`

## Risks
- Không phát hiện lỗ hổng hay test laundering.

## Dependencies
- Handoff 1, 2, 3.

## Open questions
Không có

## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "reviewer",
  "revision": 1,
  "input_refs": ["ai-workspace/sessions/{sid}/handoff-3-implementer.md"],
  "next_action": "Chờ User duyệt review",
  "verification_refs": []
}}
```
"""


class TestStep2CliAndStateMachine(unittest.TestCase):
    def test_solid_dependency_direction(self) -> None:
        forbidden_in_pure = {"subprocess", "adapters", "storage", "speedy_cli", "audit_viewer", "docs_viewer"}
        for pure_file in ("contracts.py", "policy.py"):
            tree = ast.parse((SCRIPTS_DIR / pure_file).read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            overlap = imported & forbidden_in_pure
            self.assertEqual(overlap, set(), f"Module thuần {pure_file} vi phạm hướng phụ thuộc: {overlap}")

    def test_risk_aware_intent_and_gemini_model_routing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)

            # 1. Thay đổi đơn giản README -> simple
            r_simple = _run_cli(ws, "intent", "sửa nhanh typo trong readme", "--path", "README.md")
            self.assertEqual(r_simple.returncode, 0, r_simple.stderr)
            d_simple = json.loads(r_simple.stdout)
            self.assertEqual(d_simple["intent"], "simple")

            # 2. Nhãn "nhanh" nhưng chạm auth/jwt -> KHÔNG được vào simple!
            r_risk = _run_cli(ws, "intent", "sửa nhanh config jwt token", "--path", "config/auth.json")
            self.assertEqual(r_risk.returncode, 0)
            d_risk = json.loads(r_risk.stdout)
            self.assertNotEqual(d_risk["intent"], "simple")
            self.assertTrue(d_risk["high_risk"])
            self.assertTrue(d_risk["escalated_from_simple"])
            # Khi high_risk, architect và reviewer được phép đề xuất Gemini Carbon có cảnh báo quota
            self.assertEqual(d_risk["recommended_models"]["architect"]["model"], "Gemini Carbon")
            self.assertTrue(d_risk["recommended_models"]["architect"]["quota_warning"])

            # 3. Kiểm tra phân tầng mặc định: Hydrogen (orchestrator/docs/writer) -> Neon (task thường)
            m_orch = json.loads(_run_cli(ws, "model", "--role", "orchestrator").stdout)
            self.assertEqual(m_orch["model"], "Gemini Hydrogen")
            m_impl = json.loads(_run_cli(ws, "model", "--role", "implementer", "--high-risk").stdout)
            self.assertEqual(m_impl["model"], "Gemini Neon")
            m_arch_normal = json.loads(_run_cli(ws, "model", "--role", "architect").stdout)
            self.assertEqual(m_arch_normal["model"], "Gemini Neon")

    def test_path_containment_and_symlink_escape_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            outside_file = Path(tmp) / "secret_outside.txt"
            outside_file.write_text("TOP_SECRET", encoding="utf-8")

            # Path traversal '..'
            with self.assertRaises(SpeedyError) as ctx1:
                resolve_within_scope(ws, "../secret_outside.txt")
            self.assertEqual(ctx1.exception.code, ErrorCode.SCOPE_VIOLATION)

            # Symlink escape
            evil_link = ws / "payments" / "escape_link.txt"
            evil_link.symlink_to(outside_file)
            with self.assertRaises(SpeedyError) as ctx2:
                resolve_within_scope(ws, "payments/escape_link.txt")
            self.assertEqual(ctx2.exception.code, ErrorCode.SCOPE_VIOLATION)

            # Out of allowed_paths
            with self.assertRaises(SpeedyError) as ctx3:
                resolve_within_scope(ws, "other/file.py", allowed_prefixes=["payments"])
            self.assertEqual(ctx3.exception.code, ErrorCode.SCOPE_VIOLATION)

    def test_session_collision_and_explicit_sid_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            s1 = json.loads(_run_cli(ws, "session", "new", "--slug", "same-task", "--goal", "Add feature A").stdout)
            s2 = json.loads(_run_cli(ws, "session", "new", "--slug", "same-task", "--goal", "Add feature B").stdout)
            self.assertNotEqual(s1["sid"], s2["sid"])
            self.assertNotEqual(s1["plan_path"], s2["plan_path"])

            # Có 2 session đang mở -> gọi session get không có --sid phải báo lỗi yêu cầu chọn SID
            ambig = _run_cli(ws, "session", "get")
            self.assertNotEqual(ambig.returncode, 0)
            self.assertIn("INVALID_INPUT", ambig.stderr)

    def test_strict_lifecycle_handoff_validator_and_selective_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            layout = resolve_layout(ws)
            created = create_session(
                layout,
                slug="payment-tax",
                goal="Thêm tính thuế cho module thanh toán",
                mode="feature",
                allowed_paths=["payments"],
            )
            sid = created["sid"]

            # 1. Scaffold chứa [FILL] -> validate phải FAIL
            _run_cli(ws, "scaffold", "--sid", sid, "--stage", "analyst", "--slug", "payment-tax")
            bad_val = _run_cli(ws, "handoff", "validate", "--sid", sid, "--stage", "analyst")
            self.assertNotEqual(bad_val.returncode, 0)
            self.assertIn("CONTRACT_VIOLATION", bad_val.stderr)

            # 2. Không được nhảy cóc sang implementer khi analyst chưa được duyệt
            with self.assertRaises(SpeedyError) as skip_err:
                transition_stage(layout, sid=sid, stage="implementer", target_status="running")
            self.assertEqual(skip_err.exception.code, ErrorCode.GATE_REQUIRED)

            # 3. Điền handoff hợp lệ cho Analyst -> chuyển sang awaiting_approval
            sdir = session_dir_for(layout, sid)
            (sdir / "handoff-1-analyst.md").write_text(_valid_analyst_md(sid), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="analyst", target_status="running")
            transition_stage(layout, sid=sid, stage="analyst", target_status="awaiting_approval")

            # 4. Cấm LLM tự gọi gate approve
            with self.assertRaises(SpeedyError) as llm_err:
                record_gate_decision(
                    layout, sid=sid, stage="analyst", decision="approve", actor="llm", interaction_ref="fake"
                )
            self.assertEqual(llm_err.exception.code, ErrorCode.GATE_REQUIRED)

            # 5. Human approve hợp lệ -> sang architect
            app1 = record_gate_decision(
                layout, sid=sid, stage="analyst", decision="approve", actor="human", interaction_ref="ask_question#1"
            )
            self.assertEqual(app1["current_stage"], "architect")

            # 6. Đổi dòng Updated At (metadata thuần vận hành) KHÔNG làm mất approval của Analyst!
            updated_ts_md = _valid_analyst_md(sid).replace("2026-11-27T20:00:00Z", "2026-11-27T21:30:00Z")
            (sdir / "handoff-1-analyst.md").write_text(updated_ts_md, encoding="utf-8")
            resumed_clean = resume_session(layout, sid)
            self.assertEqual(resumed_clean["invalidated_stages"], [])

            # 7. Hoàn tất Architect, Implementer, Reviewer
            (sdir / "handoff-2-architect.md").write_text(_valid_architect_md(sid), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="architect", target_status="running")
            transition_stage(layout, sid=sid, stage="architect", target_status="awaiting_approval")
            record_gate_decision(
                layout, sid=sid, stage="architect", decision="approve", actor="human", interaction_ref="ask_question#2"
            )

            (sdir / "handoff-3-implementer.md").write_text(_valid_implementer_md(sid), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="implementer", target_status="running")
            transition_stage(layout, sid=sid, stage="implementer", target_status="awaiting_approval")

            (sdir / "handoff-4-reviewer.md").write_text(_valid_reviewer_md(sid), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="reviewer", target_status="running")
            transition_stage(layout, sid=sid, stage="reviewer", target_status="awaiting_approval")
            record_gate_decision(
                layout, sid=sid, stage="reviewer", decision="approve", actor="human", interaction_ref="ask_question#3"
            )

            # 8. Selective invalidation: Sửa code `payments/main.py` -> chỉ làm stale `reviewer`, GIỮ NGUYÊN approval của `analyst` và `architect`!
            (ws / "payments" / "main.py").write_text(
                "def charge(amount: int) -> int:\n    return max(0, amount)\n",
                encoding="utf-8",
            )
            resumed_dirty_code = resume_session(layout, sid)
            self.assertEqual(resumed_dirty_code["invalidated_stages"], ["reviewer"])
            self.assertEqual(resumed_dirty_code["current_stage"], "reviewer")

            # 9. Sửa nội dung chuyên môn của `handoff-1-analyst.md` -> làm stale cả analyst lẫn architect phía sau!
            (sdir / "handoff-1-analyst.md").write_text(
                _valid_analyst_md(sid, extra_summary="Đổi hoàn toàn yêu cầu sang đa tiền tệ."),
                encoding="utf-8",
            )
            resumed_dirty_spec = resume_session(layout, sid)
            self.assertIn("analyst", resumed_dirty_spec["invalidated_stages"])
            self.assertIn("architect", resumed_dirty_spec["invalidated_stages"])
            self.assertEqual(resumed_dirty_spec["current_stage"], "analyst")

    def test_concurrency_cas_uow_conflict_and_attempt_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            layout = resolve_layout(ws)
            created = create_session(layout, slug="conc-test", goal="Kiểm tra khóa đồng thời", mode="simple")
            sid = created["sid"]
            sdir = session_dir_for(layout, sid)

            # 1. CAS conflict khi truyền sai expected_revision
            with self.assertRaises(SpeedyError) as cas_err:
                transition_stage(layout, sid=sid, stage="implementer", target_status="running", expected_revision=999)
            self.assertEqual(cas_err.exception.code, ErrorCode.CAS_CONFLICT)

            # 2. Session lock chặn writer thứ hai khi khóa đang được giữ
            with session_lock(sdir, owner="holder", wait_timeout=0.1):
                with self.assertRaises(SpeedyError) as lock_err:
                    with session_lock(sdir, owner="intruder", wait_timeout=0.1):
                        pass
                self.assertEqual(lock_err.exception.code, ErrorCode.LOCK_CONFLICT)

            # 3. UoW scheduler chặn hai worker ghi đè cùng file
            register_worker_uow(
                layout, sid=sid, uow_id="uow-1", stage="implementer", objective="Edit A", write_paths=["payments/main.py"]
            )
            with self.assertRaises(SpeedyError) as uow_err:
                register_worker_uow(
                    layout, sid=sid, uow_id="uow-2", stage="implementer", objective="Edit B", write_paths=["payments"]
                )
            self.assertEqual(uow_err.exception.code, ErrorCode.SCOPE_VIOLATION)

            # 4. Doom-loop & giới hạn 3 attempts
            transition_stage(layout, sid=sid, stage="implementer", target_status="running")
            transition_stage(
                layout,
                sid=sid,
                stage="implementer",
                target_status="failed",
                failure_reason="TypeError line 2",
                failure_command="pytest",
            )
            transition_stage(layout, sid=sid, stage="implementer", target_status="running")
            with self.assertRaises(SpeedyError) as doom_err:
                transition_stage(
                    layout,
                    sid=sid,
                    stage="implementer",
                    target_status="failed",
                    failure_reason="TypeError line 2",
                    failure_command="pytest",
                    has_new_hypothesis=False,
                )
            self.assertEqual(doom_err.exception.code, ErrorCode.DOOM_LOOP_DETECTED)

    def test_context_packet_verify_laundering_audit_viewers_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            s_out = json.loads(
                _run_cli(ws, "session", "new", "--slug", "ctx-audit", "--goal", "Add charge API token=my_secret_123").stdout
            )
            sid = s_out["sid"]
            audit_dir = s_out["audit"]["audit_dir"]

            # Ghi handoff Analyst để Context Packet trích xuất AC-001
            (ws / "ai-workspace" / "sessions" / sid / "handoff-1-analyst.md").write_text(
                _valid_analyst_md(sid), encoding="utf-8"
            )
            pkt = json.loads(_run_cli(ws, "context", "prepare", "--sid", sid, "--stage", "implementer", "--query", "payments").stdout)
            self.assertTrue(any("AC-001" in ac for ac in pkt["acceptance_criteria"]))
            self.assertEqual(pkt["recommended_model"]["model"], "Gemini Neon")
            self.assertGreaterEqual(len(pkt["repomap_matches"]), 1)

            # Kiểm tra phát hiện Test Laundering
            sneaky_diff = """--- a/tests/test_pay.py
+++ b/tests/test_pay.py
@@ -1,4 +1,3 @@
+@unittest.skip("tạm ẩn test lỗi")
 def test_charge():
-    assert charge(100) == 100
+    pass
"""
            launder = detect_test_laundering(sneaky_diff, approved_ac_change=False)
            self.assertTrue(launder["suspicious"])
            self.assertGreaterEqual(len(launder["findings"]), 2)

            # Chạy verify thực tế (pass)
            ver = _run_cli(
                ws,
                "verify",
                "run",
                "--sid",
                sid,
                "--check",
                f"unit_integration={sys.executable} -c \"assert 1 + 1 == 2; print('api_key=TOPSECRET123 OK')\"",
            )
            self.assertEqual(ver.returncode, 0, ver.stderr)
            ver_json = json.loads(ver.stdout)
            self.assertEqual(ver_json["overall_status"], "PASS")
            # Evidence đã che secret
            unit_layer = [x for x in ver_json["layers"] if x["layer"] == "unit_integration"][0]
            self.assertIn("[REDACTED]", unit_layer["output_preview"])
            self.assertNotIn("TOPSECRET123", unit_layer["output_preview"])

            # Kiểm tra Audit trung thực khi không có nguồn đo token + mask secret ở 01-input-context.json
            f01 = json.loads((ws / audit_dir / "01-input-context.json").read_text(encoding="utf-8"))
            self.assertNotIn("my_secret_123", json.dumps(f01))
            self.assertIn("[REDACTED]", json.dumps(f01))

            _run_cli(ws, "audit", "event", "--audit-dir", audit_dir, "--agent", "implementer", "--model", "Gemini Neon", "--human-wait-ms", "1500", "--tool-time-ms", "400")
            fin_unmeasured = json.loads(_run_cli(ws, "audit", "finalize", "--audit-dir", audit_dir, "--outcome", "success", "--completion-level", "verified", "--ac-passed", "1", "--ac-total", "1", "--build-status", "pass").stdout)
            self.assertEqual(fin_unmeasured["usage_source"], "not_measured")
            self.assertIsNone(fin_unmeasured["total_tokens"])
            self.assertIsNone(fin_unmeasured["total_estimated_cost"])

            # Khi truyền usage thật của Gemini Neon + subagent có included_in_parent=True -> không cộng trùng lặp!
            usage_sample = json.dumps([
                {"agent": "implementer", "model": "Gemini Neon", "input_tokens": 10000, "cached_input_tokens": 2000, "output_tokens": 1000},
                {"agent": "reviewer", "model": "Gemini Neon", "input_tokens": 3000, "output_tokens": 500, "included_in_parent": True},
            ])
            fin_measured = json.loads(
                _run_cli(ws, "audit", "finalize", "--audit-dir", audit_dir, "--usage-json", usage_sample, "--usage-source", "explicit_test_meter").stdout
            )
            self.assertEqual(fin_measured["total_tokens"], 11000)
            self.assertIsNotNone(fin_measured["total_estimated_cost"])

            # Render docs-view & audit-view (created -> unchanged, XSS escaped)
            (ws / "ai-workspace" / "docs" / "architecture" / "overview.md").write_text(
                "# Overview <script>alert(1)</script>\n\n| Module | Mô tả |\n|---|---|\n| payments | Xử lý thanh toán |\n",
                encoding="utf-8",
            )
            dv1 = json.loads(_run_cli(ws, "docs-view", "--no-open").stdout)
            dv2 = json.loads(_run_cli(ws, "docs-view", "--no-open").stdout)
            self.assertEqual(dv1["status"], "created")
            self.assertEqual(dv2["status"], "unchanged")
            rendered_docs_html = Path(dv1["path"]).read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", rendered_docs_html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered_docs_html)

            av1 = json.loads(_run_cli(ws, "audit-view", "--month", sid[:7], "--no-open").stdout)
            self.assertEqual(av1["status"], "created")
            self.assertEqual(av1["tasks"], 1)

            # Cleanup bảo vệ tuyệt đối session đang in_progress ngay cả khi --older-than 0 --apply
            (ws / "ai-workspace" / "tmp" / "scratch.txt").write_text("temp", encoding="utf-8")
            cl_dry = json.loads(_run_cli(ws, "cleanup", "--older-than", "0").stdout)
            self.assertTrue(cl_dry["dry_run"])
            self.assertEqual(cl_dry["deleted_count"], 0)
            self.assertTrue((ws / "ai-workspace" / "tmp" / "scratch.txt").exists())

            cl_apply = json.loads(_run_cli(ws, "cleanup", "--older-than", "0", "--apply").stdout)
            self.assertFalse(cl_apply["dry_run"])
            self.assertFalse((ws / "ai-workspace" / "tmp" / "scratch.txt").exists())
            self.assertTrue((ws / "ai-workspace" / "sessions" / sid / "state.json").exists())

    def test_unified_harness_repomap_knowledge_index_and_context_injection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_temp_product_workspace(tmp)
            # Tạo cấu trúc dự án thực tế 2 cấp: functions/src/subsonic + web/src/pages
            sub_dir = ws / "functions" / "src" / "subsonic"
            sub_dir.mkdir(parents=True, exist_ok=True)
            (sub_dir / "opensubsonic.ts").write_text(
                "export function handleOpenSubsonicStream(id: string) { return id; }\n"
                "export class CatalogSnapshotBuilder {}\n",
                encoding="utf-8",
            )
            web_pages = ws / "web" / "src" / "pages"
            web_pages.mkdir(parents=True, exist_ok=True)
            (web_pages / "BooksPage.tsx").write_text(
                "export function BooksPage() { return null; }\n",
                encoding="utf-8",
            )
            # Tạo Active Spec + Domain Doc
            specs_dir = ws / "ai-workspace" / "specs"
            specs_dir.mkdir(parents=True, exist_ok=True)
            (specs_dir / "01-v1-audio.md").write_text("# Audio System v1\n", encoding="utf-8")
            (specs_dir / "INDEX.md").write_text(
                "# Specs Index\n- **Active Spec**: `01-v1-audio.md`\n",
                encoding="utf-8",
            )
            (ws / "ai-workspace" / "docs" / "architecture" / "opensubsonic-api.md").write_text(
                "# OpenSubsonic Streaming API\n\nTags: opensubsonic, stream, redirect, catalog\n\n"
                "## Zero-Egress 302 Redirect\nStream audio directly from Drive.\n",
                encoding="utf-8",
            )

            # 1. Chạy knowledge index -> sinh docs/INDEX.md (< 80 dòng) + idempotent + repomap.json v2
            idx_res = json.loads(_run_cli(ws, "knowledge", "index").stdout)
            self.assertEqual(idx_res["status"], "created")
            index_md_path = ws / "ai-workspace" / "docs" / "INDEX.md"
            self.assertTrue(index_md_path.is_file())
            self.assertLess(len(index_md_path.read_text(encoding="utf-8").splitlines()), 80)
            self.assertGreaterEqual(idx_res["modules_count"], 2)
            self.assertGreaterEqual(idx_res["docs_count"], 1)
            idx_res2 = json.loads(_run_cli(ws, "knowledge", "index").stdout)
            self.assertEqual(idx_res2["status"], "unchanged")

            # 2. Kiểm tra cache hit và cache invalidation khi sửa nội dung file code (AC-001)
            rm_cached = json.loads(_run_cli(ws, "repomap", "build").stdout)
            self.assertTrue(rm_cached["cached"])
            (sub_dir / "opensubsonic.ts").write_text(
                "export function handleOpenSubsonicStream(id: string) { return id; }\n"
                "export class CatalogSnapshotBuilder {}\n"
                "export function buildDriveRedirectUrl(id: string) { return id; }\n",
                encoding="utf-8",
            )
            rm_fresh = json.loads(_run_cli(ws, "repomap", "build").stdout)
            self.assertFalse(rm_fresh["cached"])

            # 3. Chạy knowledge query -> khớp cả symbol mới thêm lẫn domain doc (AC-002)
            q_res = json.loads(_run_cli(ws, "knowledge", "query", "opensubsonic").stdout)
            self.assertTrue(
                any(m["path"] == "functions/src/subsonic" and "handleOpenSubsonicStream" in m["matched_symbols"] for m in q_res["code_matches"]),
                q_res,
            )
            self.assertTrue(
                any(d["path"].endswith("opensubsonic-api.md") for d in q_res["doc_matches"]),
                q_res,
            )
            q_new_sym = json.loads(_run_cli(ws, "knowledge", "query", "DriveRedirect").stdout)
            self.assertTrue(
                any("buildDriveRedirectUrl" in m["matched_symbols"] for m in q_new_sym["code_matches"]),
                q_new_sym,
            )

            # 4. Context prepare tự nạp INDEX.md + active_spec + doc_matches (AC-004)
            s_out = json.loads(_run_cli(ws, "session", "new", "--slug", "subsonic-fix", "--goal", "Fix opensubsonic stream").stdout)
            pkt = json.loads(_run_cli(ws, "context", "prepare", "--sid", s_out["sid"], "--stage", "analyst", "--query", "opensubsonic").stdout)
            ref_kinds = {r["kind"] for r in pkt["input_refs"]}
            self.assertIn("spec_index", ref_kinds)
            self.assertIn("active_spec", ref_kinds)
            self.assertIn("knowledge_master_index", ref_kinds)
            self.assertTrue(any(d["path"].endswith("opensubsonic-api.md") for d in pkt["doc_matches"]))

            # 5. AC-005: hoàn tất stage docs tự động refresh repomap & knowledge index
            state_path = ws / "ai-workspace" / "sessions" / s_out["sid"] / "state.json"
            st = json.loads(state_path.read_text(encoding="utf-8"))
            for prev in ("bootstrap", "root_cause", "analyst", "architect", "implementer", "reviewer", "tester"):
                if prev in st["stages"]:
                    st["stages"][prev]["status"] = "approved"
            st["current_stage"] = "docs"
            state_path.write_text(json.dumps(st), encoding="utf-8")
            (ws / "ai-workspace" / "sessions" / s_out["sid"] / "handoff-6-docs.md").write_text(
                f"# Docs Sync\n\n## Summary\nĐã đồng bộ docs.\n\n## Scope\n- ai-workspace/docs/INDEX.md\n\n"
                f"## Risks\nKhông.\n\n## Dependencies\nKhông.\n\n## Open questions\nKhông.\n\n"
                f"## Resume Metadata\n```json\n{{\"sid\":\"{s_out['sid']}\",\"stage\":\"docs\",\"revision\":1,\"input_refs\":[],\"next_action\":\"wrapup\",\"verification_refs\":[]}}\n```\n",
                encoding="utf-8",
            )
            docs_cmp = json.loads(_run_cli(ws, "state", "complete", "--sid", s_out["sid"], "--stage", "docs").stdout)
            self.assertTrue(docs_cmp.get("repomap_refreshed"))
            self.assertEqual(docs_cmp.get("knowledge_index_synced"), "ai-workspace/docs/INDEX.md")


if __name__ == "__main__":
    unittest.main()
