---
name: audit-view
description: "Kết xuất dữ liệu Audit 4 lớp trong ai-workspace/audit/ thành bảng điều khiển HTML theo tháng. Kích hoạt khi gọi /audit-view."
---

# Speedy Audit Viewer (`/audit-view`)

1. Đọc [.speedy/commands/audit-view.md](../../../.speedy/commands/audit-view.md).
2. Chạy lệnh deterministic:
   ```bash
   python3 .speedy/scripts/speedy_cli.py audit-view [--month YYYY-MM] --no-open
   ```
3. Gửi link tới file HTML trong `ai-workspace/reports/audit-view/` kèm tóm tắt số phiên và trạng thái dữ liệu.
