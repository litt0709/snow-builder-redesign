---
trigger: always_on
description: "Ranh giới SNOW Builder vs Speedy Product (src/), strict gate và phân tầng model Gemini trên Antigravity."
---

# Quy tắc bất biến SNOW Builder

- Đọc `AGENTS.md` trước mọi tác vụ; chỉ nạp thêm rule trong `rules/` hoặc skill `builder-*` cần cho bước hiện tại.
- Khi sửa bất kỳ file nào trong `src/`, **bắt buộc** đọc thêm `src/AGENTS.md`: tuyệt đối không ghi dữ liệu runtime giả vào `src/ai-workspace/` và không trỏ đường dẫn từ `src/` ngược ra Builder.
- Mọi `plans/`, `sessions/`, `reports/`, `logs/` phát sinh khi phát triển DevKit phải ghi tại **root Builder**.
- Mặc định `balanced` (Smart HITL): ghi handoff -> chạy 1 lệnh `python3 -B src/.speedy/scripts/speedy_cli.py --layout builder state complete --sid <sid> --stage <stage>` -> chỉ dừng gọi `ask_question` khi `requires_human_approval == true` (có `Open questions`, `high_risk`, `REQUEST_CHANGES`, hoặc release). Hỗ trợ `--policy strict` khi cần duyệt từng bước.
- Phân tầng Gemini: **Gemini Hydrogen** (`builder-flow`, `builder-docs-manager`, `builder-writer`) -> **Gemini Neon** (mặc định chủ lực) -> **Gemini Carbon** (hạn chế tối đa, chỉ dùng cho bài toán kiến trúc/review cực khó).
