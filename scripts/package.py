#!/usr/bin/env python3
"""
scripts/package.py — Công cụ đóng gói Speedy DevKit từ SNOW Builder (`src/`).
Tái sử dụng trực tiếp `installer_core.py` (DRY 100%) để:
1. Sinh hoặc làm mới `src/.speedy/manifest.json` với SHA-256 chuẩn xác.
2. Đóng gói bản xuất sạch ra thư mục đích (ví dụ `dist/speedy-package`) và kiểm định tính toàn vẹn.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

BUILDER_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = BUILDER_ROOT / "src"
CORE_SCRIPTS = SRC_DIR / ".speedy" / "scripts"
if str(CORE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(CORE_SCRIPTS))

from contracts import SpeedyError  # noqa: E402
from installer_core import export_clean_package, verify_package_integrity, write_manifest_in_place  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Đóng gói sản phẩm Speedy DevKit từ src/.")
    parser.add_argument("--src", default=str(SRC_DIR), help="Thư mục nguồn Speedy (mặc định: ./src)")
    parser.add_argument("--out", help="Thư mục xuất gói sạch (ví dụ: dist/speedy-package)")
    parser.add_argument(
        "--refresh-manifest-only",
        action="store_true",
        help="Chỉ cập nhật và xác thực src/.speedy/manifest.json tại chỗ",
    )
    args = parser.parse_args(argv)

    src_path = Path(args.src).resolve()
    try:
        if args.refresh_manifest_only or not args.out:
            manifest = write_manifest_in_place(src_path)
            verify_package_integrity(src_path)
            print(
                json.dumps(
                    {
                        "status": "manifest_refreshed",
                        "version": manifest["version"],
                        "file_count": manifest["file_count"],
                        "manifest_path": str(src_path / ".speedy" / "manifest.json"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        result = export_clean_package(src_path, Path(args.out))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except SpeedyError as err:
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return err.exit_code


if __name__ == "__main__":
    sys.exit(main())
