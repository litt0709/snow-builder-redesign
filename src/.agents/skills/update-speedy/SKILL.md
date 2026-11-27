---
name: update-speedy
description: "Kiểm tra phiên bản mới nhất, đối chiếu Ownership Manifest xung đột, tạo bản sao lưu và cập nhật engine Speedy an toàn mà không chạm vào ai-workspace/. Kích hoạt khi người dùng gọi /update-speedy."
---

# Cập Nhật Speedy DevKit (`/update-speedy`)

1. Đọc quy trình chi tiết tại [.speedy/commands/update-speedy.md](../../../.speedy/commands/update-speedy.md).
2. Chạy bước kiểm tra dry-run (tự động đọc nguồn đã lưu tại `.speedy/config/source.local.json`, `SPEEDY_SOURCE_URL`, `ai-workspace/.env` hoặc `.speedy/config/source.json`; tuyệt đối không tự dùng `git remote origin` của dự án ứng dụng):
   ```bash
   python3 .speedy/scripts/speedy_cli.py update
   ```
   *(Nếu kết quả trả về `"status": "UP_TO_DATE"` thì báo người dùng đã ở phiên bản mới nhất và dừng lại).*
3. Trình bày ngắn gọn phiên bản/commit hiện tại vs bản mới, danh sách file sẽ thêm/cập nhật/xóa bỏ và các file xung đột (nếu có), sau đó gọi `ask_question` xin xác nhận (`Approve — Giữ nguyên file dự án xung đột (--skip-conflicts)` / `Approve — Ghi đè cả file xung đột (--force-overwrite)` / `Abort`).
4. Khi người dùng Approve, chạy lệnh áp dụng (tự tạo backup rollback và tự đồng bộ `.gitignore`):
   ```bash
   python3 .speedy/scripts/speedy_cli.py update --apply --skip-conflicts
   ```
   *(Hoặc thay `--skip-conflicts` bằng `--force-overwrite` nếu người dùng chọn ghi đè).*
5. Xác minh lại catalog sau khi cập nhật:
   ```bash
   python3 .speedy/scripts/speedy_cli.py catalog --no-cache
   ```
   và báo cáo đường dẫn `backup_dir` để người dùng có thể rollback 1 lệnh nếu cần.
