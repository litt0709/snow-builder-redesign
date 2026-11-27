"""Kiểm thử nghiệm thu Bước 5: Knowledge 4 Lớp, RepoMap Top-N, Freshness, Cross-Repo, Compaction & Promotion."""

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
CLI_PATH = SRC_ROOT / ".speedy" / "scripts" / "speedy_cli.py"


def _cli(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), "--workspace", str(ws), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )


class TestStep5KnowledgeAndRetrieval(unittest.TestCase):
    def test_baseline_principles_and_cross_repo_shipped_cleanly(self) -> None:
        principles = SRC_ROOT / "ai-workspace" / "docs" / "development-rules" / "principles.md"
        self.assertTrue(principles.is_file())
        txt = principles.read_text(encoding="utf-8")
        for kw in ("KISS", "YAGNI", "DRY", "Readability", "Minimal Scope"):
            self.assertIn(kw, txt)

        reg = json.loads((SRC_ROOT / "ai-workspace" / "docs" / "cross-repo" / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(reg["schema_version"], 1)
        self.assertEqual(reg["repos"], [])

    def test_repomap_top_n_doc_linking_no_fake_match_and_cache_invalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)
            for mod_name in ("auth_service", "billing_service", "catalog_service", "notify_service"):
                mdir = ws / "services" / mod_name
                mdir.mkdir(parents=True, exist_ok=True)
                (mdir / "main.py").write_text("def run():\n    return True\n", encoding="utf-8")

            # Tạo doc cho billing_service để kiểm tra repomap gắn link doc (WHAT)
            doc_billing = ws / "ai-workspace" / "docs" / "architecture" / "services-billing-service.md"
            stamp = json.loads(_cli(ws, "knowledge", "stamp-ref", "--source", "services/billing_service/main.py").stdout)[
                "source_ref_line"
            ]
            doc_billing.write_text(f"# Billing Service\n\n{stamp}\n\nXử lý hóa đơn.\n", encoding="utf-8")

            # 1. Top-N giới hạn đúng limit=2 dù có 4 module khớp "service"
            q1 = json.loads(_cli(ws, "repomap", "query", "service", "--limit", "2").stdout)
            self.assertEqual(q1["limit"], 2)
            self.assertEqual(len(q1["matches"]), 2)
            self.assertTrue(q1["truncated"])
            self.assertEqual(q1["total_matches"], 4)

            # 2. Module có doc được gắn link doc tự động
            q_bill = json.loads(_cli(ws, "repomap", "query", "billing").stdout)
            self.assertEqual(q_bill["matches"][0]["path"], "services/billing_service")
            self.assertIn("ai-workspace/docs/architecture/services-billing-service.md", q_bill["matches"][0]["docs"])

            # 3. Từ khóa không tồn tại -> matches=[] (không bịa module giả)
            q_none = json.loads(_cli(ws, "repomap", "query", "blockchain_quantum_xyz").stdout)
            self.assertEqual(q_none["matches"], [])

            # 4. Kiểm tra độ tươi mới tài liệu: ban đầu fresh -> sửa main.py -> phát hiện stale_docs!
            fresh_before = json.loads(_cli(ws, "knowledge", "check-freshness").stdout)
            self.assertEqual(fresh_before["fresh_count"], 1)
            self.assertEqual(fresh_before["stale_count"], 0)

            (ws / "services" / "billing_service" / "main.py").write_text(
                "def run(v2=True):\n    return v2\n", encoding="utf-8"
            )
            fresh_after = json.loads(_cli(ws, "knowledge", "check-freshness").stdout)
            self.assertEqual(fresh_after["stale_count"], 1)
            self.assertEqual(
                fresh_after["stale_docs"][0]["doc_path"],
                "ai-workspace/docs/architecture/services-billing-service.md",
            )

    def test_cross_repo_lessons_promotion_gate_reviewer_refs_and_compaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)
            (ws / "orders").mkdir(parents=True, exist_ok=True)
            (ws / "orders" / "handler.py").write_text("def handle():\n    return 200\n", encoding="utf-8")

            # 1. Cross-repo registry: đăng ký và truy vấn chỉ trả topic liên quan
            topic_file = ws / "ai-workspace" / "docs" / "cross-repo" / "shared-identity" / "jwt-verify.md"
            topic_file.parent.mkdir(parents=True, exist_ok=True)
            topic_file.write_text("# JWT Verify\nNguồn: shared-identity\n", encoding="utf-8")

            reg_res = _cli(
                ws,
                "knowledge",
                "register-cross-repo",
                "--repo-id",
                "shared-identity",
                "--topic-id",
                "jwt-verify",
                "--path",
                "shared-identity/jwt-verify.md",
                "--keyword",
                "jwt",
                "--keyword",
                "token",
                "--description",
                "Xác thực dùng chung",
            )
            self.assertEqual(reg_res.returncode, 0, reg_res.stderr)

            cr_hit = json.loads(_cli(ws, "knowledge", "cross-repo", "--query", "xác thực jwt").stdout)
            self.assertEqual(cr_hit["count"], 1)
            self.assertTrue(cr_hit["matches"][0]["exists"])

            # 2. Tạo session + kiểm tra Reviewer nhận con trỏ tới file code thật `orders/handler.py`
            sess = json.loads(_cli(ws, "session", "new", "--slug", "order-jwt", "--goal", "Kiểm tra đơn hàng jwt").stdout)
            sid = sess["sid"]
            sdir = ws / "ai-workspace" / "sessions" / sid
            (sdir / "handoff-1-analyst.md").write_text(
                f"## Summary\nBrief\n## Scope\n`orders/handler.py`\n## Risks\nNone\n## Dependencies\nNone\n## Open questions\nKhông có\n## Acceptance Criteria\n- AC-001: Trả mã 200.\n## Resume Metadata\n```json\n{{\"sid\":\"{sid}\",\"stage\":\"analyst\",\"revision\":1,\"input_refs\":[],\"next_action\":\"next\",\"verification_refs\":[]}}\n```\n",
                encoding="utf-8",
            )
            (sdir / "handoff-3-implementer.md").write_text(
                f"## Summary\nĐã sửa `orders/handler.py`\n## Scope\n`orders/handler.py`\n## Risks\nNone\n## Dependencies\nNone\n## Open questions\nKhông có\n## Resume Metadata\n```json\n{{\"sid\":\"{sid}\",\"stage\":\"implementer\",\"revision\":1,\"input_refs\":[],\"next_action\":\"review\",\"verification_refs\":[]}}\n```\n",
                encoding="utf-8",
            )

            rev_pkt = json.loads(_cli(ws, "context", "prepare", "--sid", sid, "--stage", "reviewer").stdout)
            ref_kinds = {r["kind"]: r["path"] for r in rev_pkt["input_refs"]}
            self.assertEqual(ref_kinds.get("actual_source_file"), "orders/handler.py")
            self.assertEqual(len(rev_pkt["cross_repo_matches"]), 1)

            # 3. Compaction giữ nguyên goal, AC, decisions, next_action
            cmp_res = json.loads(_cli(ws, "context", "compact", "--sid", sid).stdout)
            self.assertEqual(cmp_res["checkpoint"]["sid"], sid)
            self.assertTrue(any("AC-001" in x for x in cmp_res["checkpoint"]["acceptance_criteria"]))

            # 4. Lesson promotion: đề xuất thành công nhưng cấm AI tự promote khi không có --actor human
            prop = json.loads(
                _cli(
                    ws,
                    "knowledge",
                    "propose-lesson",
                    "--sid",
                    sid,
                    "--title",
                    "Luôn kiểm tra hạn token",
                    "--lesson",
                    "Kiểm tra exp claim trước khi giải mã payload.",
                ).stdout
            )
            lesson_id = prop["lesson"]["id"]

            blocked_prom = _cli(
                ws,
                "knowledge",
                "promote-lesson",
                "--sid",
                sid,
                "--lesson-id",
                lesson_id,
                "--actor",
                "llm",
                "--interaction-ref",
                "auto",
            )
            self.assertNotEqual(blocked_prom.returncode, 0)
            self.assertIn("GATE_REQUIRED", blocked_prom.stderr)

            ok_prom = json.loads(
                _cli(
                    ws,
                    "knowledge",
                    "promote-lesson",
                    "--sid",
                    sid,
                    "--lesson-id",
                    lesson_id,
                    "--actor",
                    "human",
                    "--interaction-ref",
                    "ask_question#lesson1",
                ).stdout
            )
            self.assertTrue(ok_prom["promoted"])
            self.assertTrue((ws / ok_prom["target_doc"]).is_file())


if __name__ == "__main__":
    unittest.main()
