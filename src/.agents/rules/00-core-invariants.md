---
trigger: always_on
description: "Ranh giới vận hành, Smart HITL (balanced), 11 Anti-Patterns, SSOT và phân tầng model Gemini cho Speedy DevKit."
---

# Quy tắc bất biến Speedy DevKit

- Đọc `AGENTS.md`; chỉ nạp đúng role/flow của bước hiện tại (`.speedy/roles/`, `.speedy/flows/`), dùng `repomap query` trước khi đọc source.
- Giữ đúng `scope` và **SSOT** (cấm phân mảnh công thức/số liệu giữa các view); tránh 11 Anti-Patterns tại `.speedy/rules/1.principle.md`.
- Mặc định `balanced` (Smart HITL): ghi artifact → chạy 1 lệnh `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>` → chỉ gọi `ask_question` khi `requires_human_approval == true` (`Open questions`, `high_risk`, `REQUEST_CHANGES`, xung đột hoặc release; hỗ trợ `--policy strict`).
- Tối ưu tốc độ & token: batch song song các thao tác độc lập, dùng `python3 -B`, chọn đúng tầng **Gemini Hydrogen** (`orchestrator`/`docs`/`writer`) → **Gemini Neon** (mặc định) → **Gemini Carbon** (giới hạn chặt cho kiến trúc/review cực khó).
- Không tự ý commit/push/tag, không Test Laundering (xóa/skip/lỏng assert), không ghi secret hay bịa số liệu token.
