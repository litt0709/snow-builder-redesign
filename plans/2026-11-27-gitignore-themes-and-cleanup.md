# Kế Hoạch — Auto `.gitignore`, Thư Viện `themes/` (Light + Dark) & Dọn Thư Mục Thừa

- **Ngày**: `2026-11-27`
- **Mục tiêu**:
  1. Tự động thêm block ignore (`.agents/`, `.speedy/`, `ai-workspace/`, `AGENTS.md`) vào `.gitignore` của dự án đích khi cài Speedy qua CLI (idempotent, có backup & rollback, hỗ trợ `--no-gitignore`), và bổ sung hướng dẫn cài đặt CLI chi tiết trong `README.md`.
  2. Bổ sung thư mục mẫu thiết kế `src/.speedy/docs/themes/` (kit-owned để tự động cập nhật khi thêm mẫu mới) cùng mẫu đầu tiên `1.default/` chuyển thể từ `/Users/snow/Documents/www/snow-retro/docs/design/` và hoàn thiện đầy đủ cả **Light Mode & Dark Mode**.
  3. Tích hợp **HITL Gate chọn Theme** trong lần đầu chạy `/flow` dựng dự án Web (`flow.md`, `setup-flow.md`, `feature-flow.md`, `architect.md`).
  4. Xóa các thư mục/file không sử dụng trong source code (`logs/` rỗng ở Builder root, `.DS_Store`, báo cáo trung gian cũ nếu không còn tham chiếu).
