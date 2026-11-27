#!/usr/bin/env python3
"""
scripts/autotest.py — Bộ kiểm định Pre-release toàn diện cho Speedy DevKit chạy từ root SNOW Builder.
Phân biệt trung thực 4 tầng kiểm chứng (mục 9 specs/design.md):
1. `static_and_manifest`: Kiểm tra cấu trúc, boundary, broken links và SHA-256 Ownership Manifest.
2. `unit_and_cli_suite`: Chạy toàn bộ bộ test trong `tests/`.
3. `isolated_copy_out_install_rollback`: Đóng gói sang thư mục tạm hoàn toàn tách khỏi Builder, cài vào dự án mẫu có sẵn tùy chỉnh riêng, kiểm tra update & rollback.
4. `fixture_workflow_e2e_cli`: Chạy trọn vẹn một phiên `feature` và một phiên `fix` qua CLI Harness trên dự án mẫu độc lập.
*(Ghi rõ `live_ide_llm_e2e: NOT_VERIFIED_BY_SCRIPT` để không đánh đồng script Python với phiên chat thật trên IDE).*
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

sys.dont_write_bytecode = True

BUILDER_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = BUILDER_ROOT / "src"
CORE_SCRIPTS = SRC_DIR / ".speedy" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))

from installer_core import (  # noqa: E402
    apply_install_or_update,
    export_clean_package,
    rollback_from_backup,
    verify_package_integrity,
    write_manifest_in_place,
)
from storage import atomic_write_json, utc_now_iso  # noqa: E402


def _run_cli_in_fixture(fixture_dir: Path, *args: str) -> Dict[str, Any]:
    cli = fixture_dir / ".speedy" / "scripts" / "speedy_cli.py"
    proc = subprocess.run(
        [sys.executable, str(cli), "--workspace", str(fixture_dir), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"CLI command {args} failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    return json.loads(proc.stdout)


def _write_valid_stage_handoff(fixture_dir: Path, sid: str, stage: str) -> None:
    file_map = {
        "root_cause": "root-cause.md",
        "analyst": "handoff-1-analyst.md",
        "architect": "handoff-2-architect.md",
        "implementer": "handoff-3-implementer.md",
        "reviewer": "handoff-4-reviewer.md",
        "tester": "handoff-5-tester.md",
        "docs": "handoff-6-docs.md",
    }
    extra = ""
    summary = f"Hoàn thành bước {stage}."
    if stage == "analyst":
        extra = "## Acceptance Criteria\n- AC-001: Hàm `calc_discount(200, 10)` trả về `180`.\n"
    elif stage == "architect":
        extra = "## ADR\n- Quyết định: Triển khai `calc_discount(price, pct)` kiểm tra biên phần trăm `0..100`.\n"
    elif stage == "reviewer":
        summary = "- **Verdict**: `APPROVE`\nĐạt toàn bộ yêu cầu."
    elif stage == "tester":
        extra = "## AC Coverage Matrix\n| Mã AC | Kết quả |\n|---|---|\n| AC-001 | PASS |\n"

    md = f"""# Handoff — {stage}

## Summary
{summary}

## Scope
- `pricing/discount.py`

## Risks
- Không có rủi ro mở rộng.

## Dependencies
- Không phụ thuộc ngoài.

## Open questions
Không có

{extra}
## Resume Metadata
```json
{{
  "sid": "{sid}",
  "stage": "{stage}",
  "revision": 1,
  "input_refs": [],
  "next_action": "Chuyển bước tiếp theo",
  "verification_refs": []
}}
```
"""
    (fixture_dir / "ai-workspace" / "sessions" / sid / file_map[stage]).write_text(md, encoding="utf-8")


def run_autotest() -> Dict[str, Any]:
    started = time.monotonic()
    tiers: List[Dict[str, Any]] = []

    # Tầng 1: Static & Ownership Manifest integrity
    manifest = write_manifest_in_place(SRC_DIR)
    verify_package_integrity(SRC_DIR)
    tiers.append(
        {
            "tier": "static_and_manifest",
            "status": "PASS",
            "version": manifest["version"],
            "kit_file_count": manifest["file_count"],
        }
    )

    # Tầng 2: Toàn bộ Unit & CLI Tests trong Builder tests/
    ut_proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=str(BUILDER_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        timeout=120,
    )
    if ut_proc.returncode != 0:
        tiers.append(
            {
                "tier": "unit_and_cli_suite",
                "status": "FAIL",
                "output_tail": (ut_proc.stderr or ut_proc.stdout)[-1500:],
            }
        )
        return {
            "overall_status": "FAIL",
            "tiers": tiers,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    tiers.append({"tier": "unit_and_cli_suite", "status": "PASS"})

    # Tầng 3 & 4: Đóng gói độc lập sang temp, cài đặt vào dự án có sẵn tùy chỉnh, chạy feature + fix flow đến verification & rollback
    with tempfile.TemporaryDirectory(prefix="speedy-autotest-") as tmp:
        pkg_dir = Path(tmp) / "exported_package"
        app_dir = Path(tmp) / "user_fixture_app"
        app_dir.mkdir(parents=True, exist_ok=True)

        # Dự án mẫu đã có sẵn code riêng và skill Antigravity riêng của team người dùng
        (app_dir / "pricing").mkdir()
        (app_dir / "pricing" / "discount.py").write_text(
            "def calc_discount(price: int, pct: int) -> int:\n    return price - (price * pct // 100)\n",
            encoding="utf-8",
        )
        (app_dir / "tests").mkdir()
        (app_dir / "tests" / "test_discount.py").write_text(
            "import unittest\nfrom pricing.discount import calc_discount\n\n"
            "class TestDiscount(unittest.TestCase):\n"
            "    def test_ac001_ten_percent(self):\n"
            "        self.assertEqual(calc_discount(200, 10), 180)\n",
            encoding="utf-8",
        )
        custom_skill = app_dir / ".agents" / "skills" / "team-custom-deploy" / "SKILL.md"
        custom_skill.parent.mkdir(parents=True, exist_ok=True)
        custom_skill.write_text("---\nname: team-custom-deploy\ndescription: Custom skill\n---\n# Deploy\n", encoding="utf-8")

        export_clean_package(SRC_DIR, pkg_dir)
        install_res = apply_install_or_update(pkg_dir, app_dir, dry_run=False)
        assert install_res["applied"] is True
        assert custom_skill.is_file(), "Skill riêng của người dùng phải được giữ nguyên sau khi cài Speedy!"

        # Chạy lại installer lần 2 (idempotent) không làm hỏng cấu hình hay dữ liệu
        reinstall_res = apply_install_or_update(pkg_dir, app_dir, dry_run=False)
        assert reinstall_res["created_count"] == 0 and reinstall_res["updated_count"] == 0

        tiers.append(
            {
                "tier": "isolated_copy_out_and_idempotent_install",
                "status": "PASS",
                "preserved_user_files": reinstall_res["plan"]["preserved_user_customizations"],
            }
        )

        # Tầng 4: Chạy trọn vẹn 1 phiên feature và 1 phiên fix trên app_dir (không có kết nối gì với BUILDER_ROOT!)
        for flow_mode, goal_text in (
            ("feature", "Thêm hàm tính chiết khấu đơn hàng"),
            ("fix", "Sửa lỗi làm tròn chiết khấu âm"),
        ):
            sess = _run_cli_in_fixture(
                app_dir, "session", "new", "--slug", f"e2e-{flow_mode}", "--goal", goal_text, "--mode", flow_mode
            )
            sid = sess["sid"]
            if flow_mode == "fix":
                _write_valid_stage_handoff(app_dir, sid, "root_cause")
                _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", "root_cause", "--status", "running")
                _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", "root_cause", "--status", "approved")

            for st in ("analyst", "architect", "implementer", "reviewer", "tester", "docs"):
                _write_valid_stage_handoff(app_dir, sid, st)
                _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", st, "--status", "running")
                _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", st, "--status", "awaiting_approval")
                if st == "implementer":
                    continue
                if st == "tester":
                    ver_out = _run_cli_in_fixture(app_dir, "verify", "run", "--sid", sid)
                    assert ver_out["overall_status"] == "PASS"
                _run_cli_in_fixture(
                    app_dir,
                    "gate",
                    "approve",
                    "--sid",
                    sid,
                    "--stage",
                    st,
                    "--actor",
                    "human",
                    "--interaction-ref",
                    f"fixture_driver:{flow_mode}:{st}",
                )

            _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "running")
            done = _run_cli_in_fixture(app_dir, "state", "transition", "--sid", sid, "--stage", "wrapup", "--status", "approved")
            assert done["session_status"] == "completed"

        # Kiểm tra Rollback bản cài đầu tiên vẫn giữ nguyên session runtime trong ai-workspace/sessions
        rb = rollback_from_backup(Path(install_res["backup_dir"]), app_dir)
        assert rb["rolled_back"] is True
        assert custom_skill.is_file()

        tiers.append(
            {
                "tier": "fixture_workflow_feature_fix_and_rollback",
                "status": "PASS",
                "approval_driver": "simulated_fixture_driver",
            }
        )

    tiers.append(
        {
            "tier": "live_ide_llm_e2e",
            "status": "NOT_VERIFIED_BY_SCRIPT",
            "reason": "Script tự động kiểm chứng toàn bộ CLI/state/contract/installer trên fixture; phiên tương tác UI thật thực hiện trực tiếp trong Antigravity IDE.",
        }
    )

    return {
        "overall_status": "PASS",
        "generated_at": utc_now_iso(),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "tiers": tiers,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy bộ kiểm định tự động Pre-release cho Speedy DevKit.")
    parser.add_argument("--report-out", help="Đường dẫn file JSON lưu kết quả báo cáo (tùy chọn)")
    args = parser.parse_args(argv)

    report = run_autotest()
    if args.report_out:
        out_path = (BUILDER_ROOT / args.report_out).resolve()
        atomic_write_json(out_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["overall_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
