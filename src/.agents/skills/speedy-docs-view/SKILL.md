---
name: speedy-docs-view
description: >-
  Kết xuất bộ tài liệu Markdown trong ai-workspace/docs/ thành trang HTML đọc cục bộ có mục lục phân cấp. Kích hoạt khi gọi /docs-view.
---

# Speedy Docs Viewer (`/docs-view`)

1. Đọc [.speedy/commands/docs-view.md](../../../.speedy/commands/docs-view.md).
2. Chạy lệnh deterministic:
   ```bash
   python3 .speedy/scripts/speedy_cli.py docs-view --no-open
   ```
   *(Chỉ thêm `--open` thay cho `--no-open` nếu người dùng yêu cầu mở thẳng trình duyệt).*
3. Gửi link tới file `ai-workspace/docs/index.html` vừa kết xuất kèm trạng thái (`created` / `updated` / `unchanged`).
