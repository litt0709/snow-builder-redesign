"""Kiểm thử nghiệm thu Bước 3: SSOT Role Contracts, Antigravity Rules/Skills & Tích hợp CLI."""

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


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    out: dict[str, str] = {}
    current_key = None
    for raw_line in match.group(1).splitlines():
        if not raw_line.strip():
            continue
        if not raw_line.startswith(" ") and ":" in raw_line:
            k, v = raw_line.split(":", 1)
            current_key = k.strip()
            val = v.strip().strip('"').strip("'")
            out[current_key] = "" if val in {">-", ">", "|"} else val
        elif current_key:
            out[current_key] = (out[current_key] + " " + raw_line.strip()).strip()
    return out


class TestStep3RolesAndAntigravityAdapter(unittest.TestCase):
    def test_all_eight_speedy_role_contracts_complete(self) -> None:
        expected_roles = {
            "orchestrator",
            "analyst",
            "specs",
            "architect",
            "implementer",
            "reviewer",
            "tester",
            "docs-manager",
            "writer",
        }
        roles_dir = SRC_ROOT / ".speedy" / "roles"
        found = {p.stem for p in roles_dir.glob("*.md")}
        self.assertEqual(found, expected_roles)

        required_sections = [
            "## 1. Khi nào dùng",
            "## 2. Input phải đọc",
            "## 3. Scope và quyền được dùng",
            "## 4. Các bước thực hiện",
            "## 5. Artifact cần xuất",
            "## 6. Điều kiện dừng",
            "## 7. Việc không được làm",
        ]
        for role_name in expected_roles:
            content = (roles_dir / f"{role_name}.md").read_text(encoding="utf-8")
            for sec in required_sections:
                self.assertIn(sec[:18], content, f"Role contract '{role_name}.md' thiếu mục '{sec}'")
            # Mỗi role phải nêu rõ model Gemini khuyến nghị
            self.assertRegex(content, r"Gemini (Hydrogen|Neon|Carbon)")

    def test_antigravity_rules_valid_and_always_on_compact(self) -> None:
        rule_files = [
            WORKSPACE_ROOT / ".agents" / "rules" / "00-builder-invariants.md",
            WORKSPACE_ROOT / ".agents" / "rules" / "10-product-isolation.md",
            SRC_ROOT / ".agents" / "rules" / "00-core-invariants.md",
            SRC_ROOT / ".agents" / "rules" / "10-session-context.md",
            SRC_ROOT / ".agents" / "rules" / "20-docs-boundary.md",
        ]
        for rfile in rule_files:
            self.assertTrue(rfile.is_file(), f"Thiếu file rule Antigravity: {rfile}")
            raw = rfile.read_text(encoding="utf-8")
            fm = _parse_frontmatter(raw)
            self.assertIn(fm.get("trigger"), {"always_on", "glob", "model_decision"})
            self.assertTrue(fm.get("description"), f"Rule {rfile.name} thiếu description")
            if fm.get("trigger") == "glob":
                self.assertTrue(fm.get("globs"), f"Rule glob {rfile.name} thiếu trường globs")
            if fm.get("trigger") == "always_on":
                # Đảm bảo rule always_on siêu nhẹ (< 1.500 bytes) để tiết kiệm ngân sách token
                self.assertLess(len(raw.encode("utf-8")), 1500, f"Rule always_on {rfile.name} quá dài")

    def test_speedy_and_builder_skills_valid_and_no_legacy_terms(self) -> None:
        expected_speedy_skills = {
            "flow",
            "specs",
            "analyst",
            "docs",
            "docs-view",
            "audit-view",
            "refresh-rule",
            "refresh-style",
            "cleanup",
            "update-speedy",
            "repomap",
        }
        expected_builder_skills = {
            "builder-flow",
            "builder-analyst",
            "builder-architect",
            "builder-implementer",
            "builder-reviewer",
            "builder-qa",
            "builder-autotest",
            "builder-docs-manager",
            "builder-writer",
            "builder-release",
        }

        speedy_dirs = {p.name for p in (SRC_ROOT / ".agents" / "skills").iterdir() if p.is_dir()}
        builder_dirs = {p.name for p in (WORKSPACE_ROOT / ".agents" / "skills").iterdir() if p.is_dir()}
        self.assertEqual(speedy_dirs, expected_speedy_skills)
        self.assertEqual(builder_dirs, expected_builder_skills)
        # Không tạo duplicate legacy .agents/workflows/ song song với .agents/skills/
        self.assertFalse((SRC_ROOT / ".agents" / "workflows").exists())
        self.assertFalse((WORKSPACE_ROOT / ".agents" / "workflows").exists())

        banned = re.compile(r"copilot|vscode_askQuestions|\.vscode\b|\.github\b|commit-push|create-pr", re.IGNORECASE)
        for root_skills, expected in (
            (SRC_ROOT / ".agents" / "skills", expected_speedy_skills),
            (WORKSPACE_ROOT / ".agents" / "skills", expected_builder_skills),
        ):
            for sname in expected:
                smd = root_skills / sname / "SKILL.md"
                self.assertTrue(smd.is_file(), f"Thiếu {smd}")
                content = smd.read_text(encoding="utf-8")
                fm = _parse_frontmatter(content)
                self.assertEqual(fm.get("name"), sname)
                self.assertTrue(fm.get("description"))
                self.assertIsNone(banned.search(content), f"Skill {sname} còn chứa từ khóa cũ bị loại bỏ")

    def test_cli_catalog_and_skill_to_role_integration_smoke(self) -> None:
        """Kiểm thử tích hợp thật trên workspace copy-out: CLI discover đủ skills/roles và khởi chạy được session cho skill."""
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "exported_app"
            shutil.copytree(SRC_ROOT, ws)
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

            cat_proc = subprocess.run(
                [sys.executable, str(ws / ".speedy/scripts/speedy_cli.py"), "--workspace", str(ws), "catalog"],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            self.assertEqual(cat_proc.returncode, 0, cat_proc.stderr)
            catalog = json.loads(cat_proc.stdout)
            self.assertFalse(catalog["is_behavioral_verification"])
            self.assertEqual(catalog["count"]["roles"], 9)
            self.assertEqual(catalog["count"]["antigravity_skills"], 11)
            self.assertEqual(catalog["count"]["antigravity_rules"], 3)

            # Kiểm tra định tuyến model cho role specs -> Gemini Neon
            specs_model_proc = subprocess.run(
                [sys.executable, str(ws / ".speedy/scripts/speedy_cli.py"), "--workspace", str(ws), "model", "--role", "specs"],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            self.assertEqual(specs_model_proc.returncode, 0, specs_model_proc.stderr)
            self.assertEqual(json.loads(specs_model_proc.stdout)["model"], "Gemini Neon")

            # Mô phỏng skill speedy-analyst gọi CLI khởi tạo session + nạp Context Packet
            sess_proc = subprocess.run(
                [
                    sys.executable,
                    str(ws / ".speedy/scripts/speedy_cli.py"),
                    "--workspace",
                    str(ws),
                    "session",
                    "new",
                    "--slug",
                    "smoke-skill",
                    "--goal",
                    "Phân tích API đặt hàng",
                    "--command-ref",
                    "/analyst",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            self.assertEqual(sess_proc.returncode, 0, sess_proc.stderr)
            sid = json.loads(sess_proc.stdout)["sid"]

            ctx_proc = subprocess.run(
                [
                    sys.executable,
                    str(ws / ".speedy/scripts/speedy_cli.py"),
                    "--workspace",
                    str(ws),
                    "context",
                    "prepare",
                    "--sid",
                    sid,
                    "--stage",
                    "analyst",
                ],
                capture_output=True,
                text=True,
                env=env,
                timeout=15,
            )
            self.assertEqual(ctx_proc.returncode, 0, ctx_proc.stderr)
            pkt = json.loads(ctx_proc.stdout)
            self.assertEqual(pkt["recommended_model"]["model"], "Gemini Neon")
            self.assertTrue((ws / ".speedy" / "roles" / "analyst.md").is_file())


if __name__ == "__main__":
    unittest.main()
