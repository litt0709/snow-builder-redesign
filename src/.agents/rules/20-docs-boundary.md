---
trigger: glob
globs: "ai-workspace/docs/**"
description: "Ranh giới nội dung và cơ chế lazy-load cho tài liệu kỹ thuật trong ai-workspace/docs/."
---

# Quy tắc Tài liệu Dự án (`ai-workspace/docs/`)

- Chỉ ghi kiến thức kỹ thuật và nghiệp vụ của **application runtime**; tuyệt đối không mô tả cấu trúc nội bộ của Speedy DevKit (`.speedy/`, `.agents/`, `ai-workspace/`).
- `architecture/overview.md` đóng vai trò là chỉ mục nhẹ (index); chi tiết từng module phải tách thành file riêng để các agent khác đọc theo cơ chế lazy-load.
- Khi đọc tài liệu: mở `overview.md` trước, chỉ đọc đúng file module liên quan và đối chiếu lại mã nguồn nếu nghi ngờ tài liệu đã cũ.
