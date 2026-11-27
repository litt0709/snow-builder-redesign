---
name: speedy-update
description: >-
  Kiểm tra phiên bản, đối chiếu manifest xung đột, tạo bản sao lưu và cập nhật engine Speedy an toàn mà không chạm vào ai-workspace/. Kích hoạt khi gọi /update-speedy.
---

# Speedy Update (`/update-speedy`)

1. Đọc quy trình chi tiết tại [.speedy/commands/update-speedy.md](../../../.speedy/commands/update-speedy.md).
2. Kiểm tra nguồn cập nhật từ biến môi trường `SPEEDY_SOURCE_URL` hoặc `.speedy/config/source.json` (tuyệt đối không tự dùng remote `origin` của ứng dụng).
3. Chạy kiểm tra phiên bản và xung đột ở chế độ staging/dry-run, hiển thị danh sách file kit-owned sẽ cập nhật và gọi `ask_question` xin xác nhận trước khi áp dụng kèm bản backup rollback.
