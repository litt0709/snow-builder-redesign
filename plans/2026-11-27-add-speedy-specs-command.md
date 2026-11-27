# Kế Hoạch — Bổ Sung Slash Command `/specs` & Role `specs` Cho Speedy DevKit

- **Ngày**: `2026-11-27`
- **Phạm vi**: `src/.speedy/roles/specs.md`, `src/.speedy/commands/specs.md`, `src/.agents/skills/speedy-specs/SKILL.md`, `src/ai-workspace/specs/.gitkeep`, `src/.speedy/scripts/{policy.py,installer_core.py}`, `src/.speedy/config/policy.default.json`, `src/AGENTS.md`, `src/ai-workspace/README.md`, `src/.speedy/manifest.json`, và bộ tests liên quan.

## Mục tiêu & Tiêu chí Nghiệm thu
- **AC-001**: Có đủ role contract `src/.speedy/roles/specs.md` (đủ 7 mục chuẩn, khuyến nghị `Gemini Neon`), command spec `src/.speedy/commands/specs.md`, và Antigravity skill `src/.agents/skills/speedy-specs/SKILL.md` (kích hoạt qua `/specs`).
- **AC-002**: File đặc tả ghi tại `ai-workspace/specs/<slug>.md` theo cấu trúc 6 phần chuẩn (Tổng quan, Goal, Mission, Các Step thực hiện, Trade-off & Pitfall, Tài liệu tham khảo) + Lịch sử cập nhật; trình bày ngắn gọn, khoa học cho cả người đọc và LLM.
- **AC-003**: Hỗ trợ chạy lặp lại nhiều lần (tạo mới khi chưa có; đọc & hợp nhất bảo toàn yêu cầu cũ + tăng version khi cập nhật).
- **AC-004**: `ai-workspace/specs/.gitkeep` được seed khi cài đặt, sạch dữ liệu giả trong `src/`, và được bảo toàn 100% khi chạy `/update-speedy`.
- **AC-005**: `speedy_cli.py model --role specs` trả về `Gemini Neon`, `speedy_cli.py catalog` nhận diện đủ `9` roles, `11` skills, `13` commands; toàn bộ `scripts/autotest.py` đạt **PASS**.
