"""Kiểm thử nghiệm thu Bước 1 (Revision 2): Skeleton Antigravity-only, Boundary & Phân tầng Gemini."""

import json
import re
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = WORKSPACE_ROOT / "src"


class TestStep1SkeletonAndBoundary(unittest.TestCase):
    """Đảm bảo cấu trúc Builder và Speedy thuần Antigravity, đúng phân tầng model Gemini."""

    def test_builder_required_structure_exists(self) -> None:
        required = [
            "AGENTS.md",
            "README.md",
            ".gitignore",
            ".agents/rules",
            ".agents/skills",
            "rules/1.principle.md",
            "rules/2.framework.md",
            "rules/3.orchestration-flow.md",
            "rules/4.logs.md",
            "rules/5.testing.md",
            "docs/OVERVIEW.md",
            "docs/ARCHITECTURE.md",
            "docs/product/README.md",
            "docs/CHANGELOG.md",
            "plans",
            "sessions",
            "scripts",
            "tests",
            "src",
        ]
        for rel in required:
            self.assertTrue((WORKSPACE_ROOT / rel).exists(), f"Thiếu đường dẫn Builder: {rel}")

    def test_speedy_product_required_structure_exists(self) -> None:
        required = [
            "AGENTS.md",
            ".agents/rules",
            ".agents/skills",
            ".speedy/VERSION",
            ".speedy/flows",
            ".speedy/commands",
            ".speedy/docs/themes/README.md",
            ".speedy/docs/themes/1.default/1.DESIGN_SYSTEM_AND_TOKENS.md",
            ".speedy/docs/themes/1.default/2.LAYOUT_AND_TEMPLATES.md",
            ".speedy/docs/themes/1.default/preview-light.png",
            ".speedy/docs/themes/1.default/preview-dark.png",
            ".speedy/docs/themes/2.tabler/1.DESIGN_SYSTEM_AND_TOKENS.md",
            ".speedy/docs/themes/2.tabler/2.LAYOUT_AND_TEMPLATES.md",
            ".speedy/docs/themes/2.tabler/preview-light.png",
            ".speedy/docs/themes/2.tabler/preview-dark.png",
            ".speedy/docs/themes/3.midnight/1.DESIGN_SYSTEM_AND_TOKENS.md",
            ".speedy/docs/themes/3.midnight/2.LAYOUT_AND_TEMPLATES.md",
            ".speedy/docs/themes/3.midnight/preview-light.png",
            ".speedy/docs/themes/3.midnight/preview-dark.png",
            ".speedy/rules/1.principle.md",
            ".speedy/rules/2.framework.md",
            ".speedy/rules/3.orchestration-flow.md",
            ".speedy/rules/4.logs.md",
            ".speedy/rules/5.testing.md",
            ".speedy/roles",
            ".speedy/schemas",
            ".speedy/scripts",
            ".speedy/config/policy.default.json",
            ".speedy/config/model-pricing.json",
            ".speedy/config/source.json",
            "ai-workspace/README.md",
            "ai-workspace/.env.example",
            "ai-workspace/.gitignore",
            "ai-workspace/docs/architecture",
            "ai-workspace/docs/guides",
            "ai-workspace/docs/reference",
            "ai-workspace/docs/development-rules",
            "ai-workspace/docs/development-style",
            "ai-workspace/docs/cross-repo",
            "ai-workspace/specs",
            "ai-workspace/plans",
            "ai-workspace/sessions",
            "ai-workspace/state",
            "ai-workspace/audit",
            "ai-workspace/logs",
            "ai-workspace/reports",
            "ai-workspace/tmp",
        ]
        for rel in required:
            self.assertTrue((SRC_ROOT / rel).exists(), f"Thiếu đường dẫn Speedy Product: {rel}")

    def test_removed_copilot_vscode_and_git_pr_commands(self) -> None:
        # Không tồn tại thư mục .github hay .vscode ở cả Builder và Product
        for forbidden_dir in [
            WORKSPACE_ROOT / ".github",
            WORKSPACE_ROOT / ".vscode",
            SRC_ROOT / ".github",
            SRC_ROOT / ".vscode",
        ]:
            self.assertFalse(forbidden_dir.exists(), f"Thư mục đã loại bỏ vẫn tồn tại: {forbidden_dir}")

        binary_exts = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif", ".pdf"}
        # Không còn tham chiếu copilot / vscode / commit-push / create-pr trong AGENTS, README, docs, rules và src/
        check_files = [
            WORKSPACE_ROOT / "AGENTS.md",
            WORKSPACE_ROOT / "README.md",
            *list((WORKSPACE_ROOT / "rules").rglob("*.md")),
            *list((WORKSPACE_ROOT / "docs").rglob("*.md")),
            *[p for p in SRC_ROOT.rglob("*") if p.is_file() and p.name != ".gitkeep" and p.suffix.lower() not in binary_exts],
        ]
        banned_terms = [
            re.compile(r"copilot", re.IGNORECASE),
            re.compile(r"\.vscode\b", re.IGNORECASE),
            re.compile(r"\.github\b", re.IGNORECASE),
            re.compile(r"vscode_askQuestions"),
            re.compile(r"commit-push"),
            re.compile(r"create-pr"),
        ]
        for file_path in check_files:
            content = file_path.read_text(encoding="utf-8")
            rel = file_path.relative_to(WORKSPACE_ROOT).as_posix()
            for pattern in banned_terms:
                self.assertIsNone(
                    pattern.search(content),
                    f"Còn sót từ khóa cần loại bỏ '{pattern.pattern}' tại {rel}",
                )

    def test_gemini_model_hierarchy_configured(self) -> None:
        policy = json.loads((SRC_ROOT / ".speedy/config/policy.default.json").read_text(encoding="utf-8"))
        tiers = policy["model_routing"]["tiers"]
        self.assertEqual(tiers["light"]["model"], "Gemini Hydrogen")
        self.assertEqual(tiers["standard"]["model"], "Gemini Neon")
        self.assertEqual(tiers["complex_restricted"]["model"], "Gemini Carbon")
        self.assertEqual(tiers["complex_restricted"]["quota_guard"], "strict_limit")

        pricing = json.loads((SRC_ROOT / ".speedy/config/model-pricing.json").read_text(encoding="utf-8"))
        self.assertEqual(set(pricing["models"].keys()), {"gemini-hydrogen", "gemini-neon", "gemini-carbon"})

    def test_product_has_no_builder_parent_references_or_fake_data(self) -> None:
        forbidden_patterns = [
            re.compile(r"snow-builder", re.IGNORECASE),
            re.compile(r"\bbuilder-(analyst|architect|implementer|qa|flow|autotest|release|reviewer|writer|docs-manager)\b"),
            re.compile(r"linecorp\.com", re.IGNORECASE),
            re.compile(r"rules/core"),
        ]
        md_link_re = re.compile(r"\]\((\.\./[^)#\s]+)")
        src_resolved = SRC_ROOT.resolve()
        binary_exts = {".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif", ".pdf"}
        for file_path in SRC_ROOT.rglob("*"):
            if not file_path.is_file() or file_path.name == ".gitkeep" or file_path.suffix.lower() in binary_exts:
                continue
            content = file_path.read_text(encoding="utf-8")
            rel = file_path.relative_to(SRC_ROOT).as_posix()
            for pattern in forbidden_patterns:
                if rel == "ai-workspace/.env.example" and pattern.pattern == r"snow-builder":
                    continue
                self.assertIsNone(
                    pattern.search(content),
                    f"Phát hiện tham chiếu cấm '{pattern.pattern}' trong file Product: src/{rel}",
                )
            for link_match in md_link_re.finditer(content):
                target_resolved = (file_path.parent / link_match.group(1)).resolve()
                self.assertTrue(
                    target_resolved.is_relative_to(src_resolved),
                    f"Link tương đối '{link_match.group(1)}' trong src/{rel} trỏ vượt ra ngoài src/!",
                )

        for rel in ["ai-workspace/sessions", "ai-workspace/audit", "ai-workspace/plans", "ai-workspace/state"]:
            items = [p.name for p in (SRC_ROOT / rel).iterdir() if p.name != ".gitkeep"]
            self.assertEqual(items, [], f"Thư mục runtime {rel} chứa dữ liệu giả: {items}")


if __name__ == "__main__":
    unittest.main()
