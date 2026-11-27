---
name: speedy-cleanup
description: >-
  Liệt kê dry-run và dọn dẹp an toàn các session đã hoàn tất/hủy hoặc file tạm cũ mà không đụng tới session đang chạy. Kích hoạt khi gọi /cleanup.
---

# Speedy Cleanup (`/cleanup`)

1. Đọc quy tắc an toàn tại [.speedy/commands/cleanup.md](../../../.speedy/commands/cleanup.md).
2. Luôn chạy **dry-run trước**:
   ```bash
   python3 .speedy/scripts/speedy_cli.py cleanup [--older-than 30]
   ```
3. Trình bày danh sách sẽ xóa và danh sách session đang hoạt động được bảo vệ, sau đó gọi `ask_question` để người dùng xác nhận trước khi chạy lại kèm cờ `--apply`.
