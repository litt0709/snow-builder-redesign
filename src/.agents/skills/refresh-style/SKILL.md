---
name: refresh-style
description: "Quét mã nguồn dự án để tổng hợp Repo Style (ưu tiên #1) và tra cứu Industry Reference Style (ưu tiên #2) vào ai-workspace/docs/development-style/STYLE.md. Kích hoạt khi gọi /refresh-style."
---

# Speedy Refresh Style (`/refresh-style`)

1. Đọc đầy đủ quy trình và guardrails tại [.speedy/commands/refresh-style.md](../../../.speedy/commands/refresh-style.md).
2. Khởi tạo session audit cho `/refresh-style`, phân tích các mẫu đặt tên, cấu trúc file, xử lý lỗi và logging thực tế của dự án.
3. Tra cứu nguồn chuẩn ngành công khai (nếu có quyền truy cập mạng; nếu không thì ghi rõ chỉ dùng Repo Style), xuất `ai-workspace/docs/development-style/STYLE.md` và finalize audit.
