"""Kiểm thử nghiệm thu Bước 6: Toàn bộ User Commands, Liên kết Skills -> Commands, Viewers & Cleanup."""

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
CLI_PATH = SRC_ROOT / ".speedy" / "scripts" / "speedy_cli.py"


def _cli(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), "--workspace", str(ws), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=20,
    )


class TestStep6UserCommandsAndViewers(unittest.TestCase):
    def test_all_command_specs_exist_and_zero_broken_links_from_skills(self) -> None:
        expected_commands = {
            "flow.md",
            "specs.md",
            "analyst.md",
            "docs.md",
            "refresh-rule.md",
            "refresh-style.md",
            "docs-view.md",
            "audit-view.md",
            "cleanup.md",
            "update-speedy.md",
            "repomap.md",
            "hitl-template.md",
            "audit-lifecycle.md",
        }
        cmd_dir = SRC_ROOT / ".speedy" / "commands"
        actual = {p.name for p in cmd_dir.glob("*.md")}
        self.assertEqual(actual, expected_commands)

        banned = re.compile(r"copilot|vscode_askQuestions|\.vscode\b|\.github\b|commit-push|create-pr|linecorp\.com", re.IGNORECASE)
        for cname in expected_commands:
            content = (cmd_dir / cname).read_text(encoding="utf-8")
            self.assertIsNone(banned.search(content), f"Command spec {cname} còn sót từ khóa cấm")

        # Kiểm tra mọi Markdown link trong src/AGENTS.md, src/.agents/skills/*/SKILL.md và src/.agents/workflows/*.md đều trỏ tới file có thật!
        link_re = re.compile(r"\]\(([^)#\s]+)\)")
        check_sources = [
            SRC_ROOT / "AGENTS.md",
            *list((SRC_ROOT / ".agents" / "skills").glob("*/SKILL.md")),
            *list((SRC_ROOT / ".agents" / "workflows").glob("*.md")),
        ]
        for md_file in check_sources:
            raw = md_file.read_text(encoding="utf-8")
            for m in link_re.finditer(raw):
                href = m.group(1)
                if href.startswith(("http://", "https://")):
                    continue
                resolved = (md_file.parent / href).resolve()
                self.assertTrue(
                    resolved.is_file(),
                    f"Broken link '{href}' trong {md_file.relative_to(SRC_ROOT)} -> không tìm thấy {resolved}",
                )

    def test_docs_view_audit_view_states_and_cleanup_completed_vs_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "app"
            shutil.copytree(SRC_ROOT, ws)

            # 1. Audit-view khi chưa có dữ liệu -> status_reason = no_audit_data
            av_empty = json.loads(_cli(ws, "audit-view", "--month", "2026-11", "--no-open").stdout)
            self.assertEqual(av_empty["status_reason"], "no_audit_data")
            self.assertEqual(av_empty["status"], "created")

            # Audit-view khi IS_AUDIT=0 -> status_reason = audit_disabled
            (ws / "ai-workspace" / ".env").write_text("IS_AUDIT=0\n", encoding="utf-8")
            av_off = json.loads(_cli(ws, "audit-view", "--month", "2026-11", "--no-open").stdout)
            self.assertEqual(av_off["status_reason"], "audit_disabled")
            self.assertEqual(av_off["status"], "updated")
            (ws / "ai-workspace" / ".env").write_text("IS_AUDIT=1\n", encoding="utf-8")

            # 2. Docs-view: created -> unchanged -> updated khi sửa tài liệu
            d1 = json.loads(_cli(ws, "docs-view", "--no-open").stdout)
            d2 = json.loads(_cli(ws, "docs-view", "--no-open").stdout)
            self.assertEqual(d1["status"], "created")
            self.assertEqual(d2["status"], "unchanged")

            (ws / "ai-workspace" / "docs" / "guides" / "quickstart.md").write_text("# Quickstart\nBắt đầu nhanh.\n", encoding="utf-8")
            d3 = json.loads(_cli(ws, "docs-view", "--no-open").stdout)
            self.assertEqual(d3["status"], "updated")

            # 3. Cleanup: xóa session cũ đã aborted/completed nhưng giữ nguyên session đang in_progress
            old_aborted = ws / "ai-workspace" / "sessions" / "2025-01-10-old-task-aa11bb"
            old_aborted.mkdir(parents=True, exist_ok=True)
            (old_aborted / "state.json").write_text(
                json.dumps({"sid": "2025-01-10-old-task-aa11bb", "status": "aborted"}), encoding="utf-8"
            )

            active_sess = json.loads(_cli(ws, "session", "new", "--slug", "live-work", "--goal", "Đang chạy").stdout)
            live_sid = active_sess["sid"]

            dry = json.loads(_cli(ws, "cleanup", "--older-than", "30").stdout)
            self.assertTrue(dry["dry_run"])
            self.assertIn("ai-workspace/sessions/2025-01-10-old-task-aa11bb", dry["candidates"]["sessions"])
            self.assertIn(f"ai-workspace/sessions/{live_sid}", dry["protected_active_sessions"])

            applied = json.loads(_cli(ws, "cleanup", "--older-than", "30", "--apply").stdout)
            self.assertFalse(applied["dry_run"])
            self.assertFalse(old_aborted.exists())
            self.assertTrue((ws / "ai-workspace" / "sessions" / live_sid / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
