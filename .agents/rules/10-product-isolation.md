---
trigger: glob
globs: "src/**"
description: "Cưỡng chế tính độc lập tuyệt đối của gói Speedy Product khi Builder chỉnh sửa src/."
---

# Cô lập Gói Sản Phẩm (`src/`)

- Mọi file trong `src/` sẽ được đóng gói xuất ra dự án của người dùng như một bộ DevKit độc lập 100%.
- **Tuyệt đối cấm** trong `src/`:
  - Đường dẫn tương đối trỏ ngược ra Builder (`../../rules`, `../AGENTS.md`).
  - Tên namespace của Builder (`snow-builder`, `builder-flow`, `builder-analyst`...).
  - URL nội bộ hardcode hoặc dữ liệu phiên chạy giả trong `src/ai-workspace/sessions/` và `src/ai-workspace/audit/`.
- Sau khi sửa `src/`, luôn chạy `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` để kiểm chứng ranh giới.
