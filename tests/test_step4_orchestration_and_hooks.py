"""Kiểm thử nghiệm thu Bước 4: Orchestration Flows, Strict vs Balanced Policy & Antigravity Guard Hook."""

from __future__ import annotations

import json
import os
import re
import shutil
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

from contracts import ErrorCode, SpeedyError, resolve_layout  # noqa: E402
from hook_guard import evaluate_pre_tool_use  # noqa: E402
from lifecycle import create_session, record_gate_decision, transition_stage  # noqa: E402
from storage import load_session_state, session_dir_for  # noqa: E402


def _make_ws(tmp: str) -> Path:
    ws = Path(tmp) / "app"
    shutil.copytree(SRC_ROOT, ws)
    (ws / "orders").mkdir(parents=True, exist_ok=True)
    (ws / "orders" / "service.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    return ws


def _handoff_doc(sid: str, stage: str, extra: str = "") -> str:
    role_block = ""
    if stage == "analyst":
        role_block = "## Acceptance Criteria\n- AC-001: Tính tổng đơn hàng chính xác.\n"
    elif stage == "architect":
        role_block = "## ADR\n- Quyết định: Dùng hàm thuần `total(items)`.\n"
    elif stage == "reviewer":
        role_block = extra or ""
    elif stage == "tester":
        role_block = "## AC Coverage Matrix\n| AC | Result |\n|---|---|\n| AC-001 | PASS |\n"

    summary_line = "- **Verdict**: `APPROVE`\nĐạt yêu cầu." if stage == "reviewer" and not extra else (extra or "Hoàn tất bước thực hiện.")
    return f"""# Handoff — {stage}

## Summary
{summary_line}

## Scope
- `orders/service.py`

## Risks
- Không có rủi ro mở rộng.

## Dependencies
- Tuân thủ pipeline hiện tại.

## Open questions
Không có

{role_block}
## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "{stage}",
  "revision": 1,
  "input_refs": [],
  "next_action": "Tiếp tục bước kế tiếp",
  "verification_refs": []
}}
```
"""


class TestStep4OrchestrationAndHooks(unittest.TestCase):
    def test_all_six_flow_playbooks_present_and_clean(self) -> None:
        expected = {
            "flow.md",
            "setup-flow.md",
            "feature-flow.md",
            "fix-flow.md",
            "simple-flow.md",
            "verify-flow.md",
        }
        flows_dir = SRC_ROOT / ".speedy" / "flows"
        actual = {p.name for p in flows_dir.glob("*.md")}
        self.assertEqual(actual, expected)

        banned = re.compile(r"copilot|vscode_askQuestions|\.vscode\b|\.github\b|commit-push|create-pr", re.IGNORECASE)
        for fname in expected:
            txt = (flows_dir / fname).read_text(encoding="utf-8")
            self.assertIsNone(banned.search(txt), f"Flow {fname} còn chứa từ khóa cũ")
            self.assertIn("speedy_cli.py", txt)

    def test_request_changes_retry_cap_and_abort_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_ws(tmp)
            layout = resolve_layout(ws)
            sess = create_session(layout, slug="order-sum", goal="Tính tổng đơn hàng", mode="simple")
            sid = sess["sid"]
            sdir = session_dir_for(layout, sid)

            (sdir / "handoff-3-implementer.md").write_text(_handoff_doc(sid, "implementer"), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="implementer", target_status="running")
            transition_stage(layout, sid=sid, stage="implementer", target_status="awaiting_approval")

            # Vòng Request Changes 1 & 2: quay lại implementer (running)
            r1 = record_gate_decision(
                layout, sid=sid, stage="implementer", decision="reject", actor="human", interaction_ref="ask#1", feedback="Thiếu kiểm tra rỗng"
            )
            self.assertEqual(r1["session_status"], "in_progress")
            self.assertEqual(r1["uow_attempts"], 1)

            transition_stage(layout, sid=sid, stage="implementer", target_status="awaiting_approval")
            r2 = record_gate_decision(
                layout, sid=sid, stage="implementer", decision="reject", actor="human", interaction_ref="ask#2", feedback="Vẫn sai kiểu trả về"
            )
            self.assertEqual(r2["session_status"], "in_progress")
            self.assertEqual(r2["uow_attempts"], 2)

            # Lần thứ 3 chạm trần max_uow_attempts = 3 -> tự động chuyển sang blocked!
            transition_stage(layout, sid=sid, stage="implementer", target_status="awaiting_approval")
            r3 = record_gate_decision(
                layout, sid=sid, stage="implementer", decision="reject", actor="human", interaction_ref="ask#3", feedback="Lần 3 chưa đạt"
            )
            self.assertEqual(r3["session_status"], "blocked")
            self.assertEqual(r3["uow_attempts"], 3)

            # Abort chặn mọi chuyển trạng thái về sau
            record_gate_decision(
                layout, sid=sid, stage="implementer", decision="abort", actor="human", interaction_ref="ask#4"
            )
            with self.assertRaises(SpeedyError) as ab_err:
                transition_stage(layout, sid=sid, stage="wrapup", target_status="running")
            self.assertEqual(ab_err.exception.code, ErrorCode.INVALID_TRANSITION)

    def test_balanced_profile_auto_passes_only_low_risk_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = _make_ws(tmp)
            layout = resolve_layout(ws)
            sess = create_session(
                layout,
                slug="balanced-doc",
                goal="Cập nhật hướng dẫn đơn hàng",
                mode="setup",
                policy_profile="balanced",
            )
            sid = sess["sid"]
            sdir = session_dir_for(layout, sid)

            # Trong balanced + không high_risk: stage docs được phép approved trực tiếp sau khi handoff hợp lệ
            (sdir / "handoff-6-docs.md").write_text(_handoff_doc(sid, "docs"), encoding="utf-8")
            transition_stage(layout, sid=sid, stage="docs", target_status="running")
            res = transition_stage(layout, sid=sid, stage="docs", target_status="approved")
            self.assertEqual(res["stage_status"], "approved")

            # Ngược lại: với task high_risk (auth/jwt), ngay cả khi chọn balanced vẫn bắt buộc dừng ở gate!
            risky = create_session(
                layout,
                slug="balanced-auth",
                goal="Thêm jwt auth middleware",
                mode="feature",
                policy_profile="balanced",
            )
            rsid = risky["sid"]
            rsdir = session_dir_for(layout, rsid)
            (rsdir / "handoff-1-analyst.md").write_text(_handoff_doc(rsid, "analyst"), encoding="utf-8")
            transition_stage(layout, sid=rsid, stage="analyst", target_status="running")
            with self.assertRaises(SpeedyError) as gate_err:
                transition_stage(layout, sid=rsid, stage="analyst", target_status="approved")
            self.assertEqual(gate_err.exception.code, ErrorCode.GATE_REQUIRED)
            st = load_session_state(layout, rsid)
            self.assertTrue(st["high_risk"])

            # Mặc định khi không truyền policy_profile -> là balanced + complete_stage tự auto-pass khi không có Open questions
            from lifecycle import complete_stage

            auto_sess = create_session(
                layout,
                slug="smart-balanced",
                goal="Cập nhật giao diện nút lưu",
                mode="feature",
            )
            self.assertEqual(auto_sess["policy"], "balanced")
            asid = auto_sess["sid"]
            asdir = session_dir_for(layout, asid)
            (asdir / "handoff-1-analyst.md").write_text(_handoff_doc(asid, "analyst"), encoding="utf-8")
            c1 = complete_stage(layout, sid=asid, stage="analyst")
            self.assertEqual(c1["stage_status"], "approved")
            self.assertFalse(c1["requires_human_approval"])

            # Nếu handoff có mục Open questions thật sự -> balanced BẮT BUỘC dừng awaiting_approval để hỏi user
            arch_with_q = _handoff_doc(asid, "architect").replace(
                "## Open questions\nKhông có",
                "## Open questions\n1. Bạn muốn lưu cài đặt vào localStorage hay cookie?",
            )
            (asdir / "handoff-2-architect.md").write_text(arch_with_q, encoding="utf-8")
            c2 = complete_stage(layout, sid=asid, stage="architect")
            self.assertEqual(c2["stage_status"], "awaiting_approval")
            self.assertTrue(c2["requires_human_approval"])

            # Reviewer trả REQUEST_CHANGES -> KHÔNG BAO GIỜ auto-pass ngay cả ở balanced
            record_gate_decision(
                layout, sid=asid, stage="architect", decision="approve", actor="human", interaction_ref="ask#q1"
            )
            (asdir / "handoff-3-implementer.md").write_text(_handoff_doc(asid, "implementer"), encoding="utf-8")
            c3 = complete_stage(layout, sid=asid, stage="implementer")
            self.assertEqual(c3["stage_status"], "approved")
            rev_req = _handoff_doc(asid, "reviewer").replace("`APPROVE`", "`REQUEST_CHANGES`")
            (asdir / "handoff-4-reviewer.md").write_text(rev_req, encoding="utf-8")
            c4 = complete_stage(layout, sid=asid, stage="reviewer")
            self.assertEqual(c4["stage_status"], "awaiting_approval")
            self.assertTrue(c4["requires_human_approval"])

    def test_antigravity_pre_tool_use_hook_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws_str = str(Path(tmp).resolve())

            # 1. Lệnh rm -rf ~ bị deny cứng
            d1 = evaluate_pre_tool_use(
                {
                    "workspacePaths": [ws_str],
                    "cwd": ws_str,
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf ~"}},
                }
            )
            self.assertEqual(d1["decision"], "deny")

            # 2. Ghi file vượt ra ngoài workspacePaths bị deny cứng
            d2 = evaluate_pre_tool_use(
                {
                    "workspacePaths": [ws_str],
                    "cwd": ws_str,
                    "toolCall": {"name": "write_file", "args": {"Path": "/etc/hosts"}},
                }
            )
            self.assertEqual(d2["decision"], "deny")

            # 3. git push bắt buộc force_ask
            d3 = evaluate_pre_tool_use(
                {
                    "workspacePaths": [ws_str],
                    "cwd": ws_str,
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "git push origin main"}},
                }
            )
            self.assertEqual(d3["decision"], "force_ask")

            # 4. Chạy unittest trong workspace được allow; kiểm tra cả giao thức CLI stdin/stdout
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "hook_guard.py")],
                input=json.dumps(
                    {
                        "workspacePaths": [ws_str],
                        "cwd": ws_str,
                        "toolCall": {"name": "run_command", "args": {"CommandLine": "python3 -m unittest"}},
                    }
                ),
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout)["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
