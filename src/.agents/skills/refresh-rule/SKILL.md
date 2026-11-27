---
name: refresh-rule
description: "Quét mã nguồn và cấu hình dự án để cập nhật coding convention vào ai-workspace/docs/development-rules/ mà không ghi đè nguyên tắc nền principles.md. Kích hoạt khi gọi /refresh-rule."
---

# Speedy Refresh Rules (`/refresh-rule`)

1. Đọc đầy đủ quy trình và guardrails tại [.speedy/commands/refresh-rule.md](../../../.speedy/commands/refresh-rule.md).
2. Khởi tạo session audit cho `/refresh-rule`, chạy `python3 .speedy/scripts/speedy_cli.py scan .` và trích xuất convention có bằng chứng thực tế từ dự án.
3. Ghi `coding-convention.md`, `review.md`, `test.md` trong `ai-workspace/docs/development-rules/` (giữ nguyên vẹn phần cốt lõi của `principles.md`), sau đó finalize audit và báo cáo kết quả.
