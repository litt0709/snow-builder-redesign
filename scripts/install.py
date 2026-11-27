#!/usr/bin/env python3
"""
scripts/install.py — Công cụ cài đặt / cập nhật / rollback Speedy DevKit vào dự án ứng dụng của người dùng.
Hỗ trợ:
- `--dry-run` (mặc định an toàn khi không truyền `--apply`)
- Kiểm tra xung đột thông qua `.speedy/manifest.json`
- Bảo toàn 100% `ai-workspace/` và các tùy chỉnh riêng trong `.agents/` của dự án
- Tự động sao lưu và hỗ trợ `--rollback <backup_dir>`
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
from installer_core import (  # noqa: E402
    apply_install_or_update,
    rollback_from_backup,
    write_manifest_in_place,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cài đặt hoặc cập nhật Speedy DevKit vào dự án đích.")
    parser.add_argument("--target", required=True, help="Đường dẫn thư mục gốc dự án ứng dụng của người dùng")
    parser.add_argument("--package", default=str(SRC_DIR), help="Thư mục gói Speedy nguồn (mặc định: ./src)")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ hiển thị kế hoạch cài đặt, không ghi file")
    parser.add_argument("--apply", action="store_true", help="Thực thi ghi file kèm tạo bản backup")
    parser.add_argument("--skip-conflicts", action="store_true", help="Giữ nguyên các file dự án bị xung đột")
    parser.add_argument("--force-overwrite", action="store_true", help="Ghi đè cả file xung đột (có lưu backup)")
    parser.add_argument("--no-gitignore", action="store_true", help="Không tự động thêm thư mục Speedy vào .gitignore dự án đích")
    parser.add_argument("--source-url", help="URL Git hoặc đường dẫn nguồn lưu vào .speedy/config/source.local.json cho /update-speedy")
    parser.add_argument("--source-ref", help="Tag hoặc nhánh Git đã dùng khi cài đặt")
    parser.add_argument("--source-kind", choices=["tag", "branch", "local", "git"], help="Loại nguồn cài đặt")
    parser.add_argument("--installed-commit", help="Commit SHA của phiên bản đã cài đặt")
    parser.add_argument("--rollback", help="Khôi phục từ đường dẫn thư mục backup")
    args = parser.parse_args(argv)

    target_path = Path(args.target).expanduser().resolve()
    pkg_path = Path(args.package).expanduser().resolve()

    try:
        if args.rollback:
            res = rollback_from_backup(Path(args.rollback).expanduser().resolve(), target_path)
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0

        if not (pkg_path / ".speedy" / "manifest.json").is_file():
            write_manifest_in_place(pkg_path)

        source_meta = None
        if args.source_url:
            source_meta = {
                "source_url": args.source_url,
                "source_ref": args.source_ref,
                "source_kind": args.source_kind or "git",
                "installed_commit": args.installed_commit,
            }

        is_dry = args.dry_run or not args.apply
        res = apply_install_or_update(
            pkg_path,
            target_path,
            dry_run=is_dry,
            force_overwrite_conflicts=args.force_overwrite,
            allow_with_conflicts_skipped=args.skip_conflicts,
            update_gitignore=not args.no_gitignore,
            source_meta=source_meta,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except SpeedyError as err:
        print(json.dumps(err.to_dict(), ensure_ascii=False, indent=2), file=sys.stderr)
        return err.exit_code


if __name__ == "__main__":
    sys.exit(main())
