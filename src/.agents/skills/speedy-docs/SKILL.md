---
name: speedy-docs
description: >-
  Lập Topic Map 2 cấp và biên soạn tài liệu kỹ thuật ứng dụng hoặc cross-repo vào ai-workspace/docs/. Kích hoạt khi gọi /docs.
---

# Speedy Docs (`/docs`)

1. Đọc đặc tả tại [.speedy/commands/docs.md](../../../.speedy/commands/docs.md) và hợp đồng vai trò tại [.speedy/roles/writer.md](../../../.speedy/roles/writer.md) (khuyến nghị **Gemini Hydrogen**).
2. Khởi tạo phiên audit bằng `python3 .speedy/scripts/speedy_cli.py session new --slug "docs" --goal "<yêu cầu>" --command-ref /docs`.
3. Chạy `speedy_cli.py scan .` và `speedy_cli.py repomap build`, lập Topic Map (loại trừ hoàn toàn `.speedy/`, `.agents/`, `ai-workspace/`).
4. Ghi `overview.md` (index nhẹ) và toàn bộ file chi tiết từng module vào `ai-workspace/docs/` (hoặc `ai-workspace/docs/cross-repo/` kèm `registry.json`), đối chiếu Completion Gate rồi finalize audit.
