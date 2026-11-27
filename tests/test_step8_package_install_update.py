"""Kiểm thử nghiệm thu Bước 8: Ownership Manifest, Đóng gói sạch, Xung đột Cài đặt/Cập nhật, Obsolete Cleanup & Rollback."""

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

from contracts import ErrorCode, SpeedyError  # noqa: E402
from installer_core import (  # noqa: E402
    apply_install_or_update,
    export_clean_package,
    rollback_from_backup,
    update_from_source,
    write_manifest_in_place,
)


class TestStep8PackageInstallUpdateRollback(unittest.TestCase):
    def test_package_install_conflict_preservation_obsolete_removal_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg_v1 = Path(tmp) / "pkg_v1"
            pkg_v2 = Path(tmp) / "pkg_v2"
            user_app = Path(tmp) / "user_app"
            user_app.mkdir(parents=True, exist_ok=True)

            # Dự án của user đã có sẵn AGENTS.md tùy chỉnh và một rule riêng trong .agents/rules/
            user_agents_md = "# Custom Project Rules\nQuy định riêng của team.\n"
            (user_app / "AGENTS.md").write_text(user_agents_md, encoding="utf-8")
            custom_rule = user_app / ".agents" / "rules" / "99-team-rule.md"
            custom_rule.parent.mkdir(parents=True, exist_ok=True)
            custom_rule.write_text("---\ntrigger: always_on\ndescription: Team rule\n---\n# Team\n", encoding="utf-8")

            export_clean_package(SRC_ROOT, pkg_v1)

            # 1. Cài đặt khi có xung đột AGENTS.md mà chưa chỉ định cách xử lý -> phải chặn lại (không ghi đè âm thầm!)
            with self.assertRaises(SpeedyError) as conf_err:
                apply_install_or_update(pkg_v1, user_app, dry_run=False)
            self.assertEqual(conf_err.exception.code, ErrorCode.CONTRACT_VIOLATION)
            self.assertEqual((user_app / "AGENTS.md").read_text(encoding="utf-8"), user_agents_md)

            # 2. Cài đặt với allow_with_conflicts_skipped=True -> cài đầy đủ Speedy nhưng GIỮ NGUYÊN AGENTS.md và 99-team-rule.md!
            inst = apply_install_or_update(pkg_v1, user_app, dry_run=False, allow_with_conflicts_skipped=True)
            self.assertTrue(inst["applied"])
            self.assertEqual((user_app / "AGENTS.md").read_text(encoding="utf-8"), user_agents_md)
            self.assertTrue(custom_rule.is_file())
            self.assertTrue((user_app / ".speedy" / "scripts" / "speedy_cli.py").is_file())

            # Người dùng tạo dữ liệu runtime thật trong ai-workspace/sessions/
            rt_session_file = user_app / "ai-workspace" / "sessions" / "2026-11-27-real-work-123abc" / "state.json"
            rt_session_file.parent.mkdir(parents=True, exist_ok=True)
            rt_session_file.write_text('{"sid": "2026-11-27-real-work-123abc"}', encoding="utf-8")

            # 3. Chuẩn bị gói v2.1.0: nâng VERSION, thêm 1 file mới, và xóa 1 file kit-owned cũ (repomap.md) để test dọn obsolete
            export_clean_package(SRC_ROOT, pkg_v2)
            (pkg_v2 / ".speedy" / "VERSION").write_text("2.1.0\n", encoding="utf-8")
            (pkg_v2 / ".speedy" / "commands" / "new-helper.md").write_text("# New Helper\n", encoding="utf-8")
            (pkg_v2 / ".speedy" / "commands" / "repomap.md").unlink()
            write_manifest_in_place(pkg_v2)

            # Update qua update_from_source (local source): giữ nguyên ai-workspace/, giữ AGENTS.md, xóa đúng file obsolete repomap.md!
            upd = update_from_source(
                user_app,
                source=str(pkg_v2),
                dry_run=False,
                allow_with_conflicts_skipped=True,
            )
            self.assertTrue(upd["applied"])
            self.assertEqual((user_app / ".speedy" / "VERSION").read_text(encoding="utf-8").strip(), "2.1.0")
            self.assertTrue((user_app / ".speedy" / "commands" / "new-helper.md").is_file())
            self.assertFalse((user_app / ".speedy" / "commands" / "repomap.md").exists())
            self.assertTrue(rt_session_file.is_file(), "Update phải bảo toàn tuyệt đối dữ liệu runtime ai-workspace!")
            self.assertTrue(custom_rule.is_file())

            # 4. Rollback từ bản backup của đợt update -> khôi phục lại 2.0.0 và file repomap.md, gỡ bỏ new-helper.md, giữ nguyên runtime!
            rb = rollback_from_backup(Path(upd["backup_dir"]), user_app)
            self.assertTrue(rb["rolled_back"])
            self.assertEqual((user_app / ".speedy" / "VERSION").read_text(encoding="utf-8").strip(), "2.0.0")
            self.assertTrue((user_app / ".speedy" / "commands" / "repomap.md").is_file())
            self.assertFalse((user_app / ".speedy" / "commands" / "new-helper.md").exists())
            self.assertTrue(rt_session_file.is_file())

    def test_update_from_git_remote_annotated_tag(self) -> None:
        """Kiểm chứng cập nhật qua Git repository cục bộ có annotated tag `speedy-v2.0.1`."""
        with tempfile.TemporaryDirectory() as tmp:
            bare_repo = Path(tmp) / "remote.git"
            work_repo = Path(tmp) / "work_repo"
            target_app = Path(tmp) / "target_app"

            export_clean_package(SRC_ROOT, target_app)
            export_clean_package(SRC_ROOT, work_repo / "src")
            (work_repo / "src" / ".speedy" / "VERSION").write_text("2.0.1\n", encoding="utf-8")
            write_manifest_in_place(work_repo / "src")

            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.com",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.com",
            }
            subprocess.run(["git", "init", "--bare", str(bare_repo)], check=True, capture_output=True)
            subprocess.run(["git", "init", str(work_repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(work_repo), "add", "."], check=True, capture_output=True, env=env)
            subprocess.run(["git", "-C", str(work_repo), "commit", "-m", "release 2.0.1"], check=True, capture_output=True, env=env)
            subprocess.run(
                ["git", "-C", str(work_repo), "tag", "-a", "speedy-v2.0.1", "-m", "Annotated v2.0.1"],
                check=True,
                capture_output=True,
                env=env,
            )
            subprocess.run(
                ["git", "-C", str(work_repo), "push", str(bare_repo), "HEAD", "speedy-v2.0.1"],
                check=True,
                capture_output=True,
                env=env,
            )

            res = update_from_source(target_app, source=str(bare_repo), dry_run=False)
            self.assertTrue(res["applied"])
            self.assertEqual((target_app / ".speedy" / "VERSION").read_text(encoding="utf-8").strip(), "2.0.1")

            # Gọi update lần nữa khi đã ở bản mới nhất -> trả UP_TO_DATE
            up_to_date = update_from_source(target_app, source=str(bare_repo), dry_run=False)
            self.assertEqual(up_to_date["status"], "UP_TO_DATE")

    def test_auto_gitignore_idempotent_and_rollback(self) -> None:
        """Khi cài Speedy, tự động thêm block ignore cho .agents/.speedy/ai-workspace/AGENTS.md và rollback sạch."""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "pkg"
            export_clean_package(SRC_ROOT, pkg)
            app = Path(tmp) / "user_app"
            app.mkdir()
            (app / ".gitignore").write_text("node_modules/\n.env\n", encoding="utf-8")

            res1 = apply_install_or_update(pkg, app, dry_run=False)
            self.assertTrue(res1["applied"])
            self.assertEqual(res1["gitignore"]["action"], "appended")
            gi_text = (app / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("node_modules/", gi_text)
            self.assertIn("/.agents/", gi_text)
            self.assertIn("/.speedy/", gi_text)
            self.assertIn("/ai-workspace/", gi_text)
            self.assertIn("/AGENTS.md", gi_text)

            # Cài lại lần 2 -> không nhân đôi block .gitignore
            res2 = apply_install_or_update(pkg, app, dry_run=False)
            self.assertEqual(res2["gitignore"]["action"], "unchanged")
            self.assertEqual((app / ".gitignore").read_text(encoding="utf-8").count("# >>> Speedy DevKit (local) >>>"), 1)

            # Rollback về trước khi cài -> khôi phục đúng .gitignore gốc của user
            rollback_from_backup(Path(res1["backup_dir"]), app)
            self.assertEqual((app / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n.env\n")


if __name__ == "__main__":
    unittest.main()
