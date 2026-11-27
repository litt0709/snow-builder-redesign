---
trigger: always_on
description: "Ranh giới vận hành, kiểm soát strict stage gate và phân tầng model Gemini cho Speedy DevKit."
---

# Quy tắc bất biến Speedy DevKit

- Đọc `AGENTS.md` và chỉ nạp đúng role/flow contract của bước hiện tại (`.speedy/roles/`, `.speedy/flows/`).
- Chỉ sửa file trong `scope` đã được duyệt; quyền sửa file của IDE không đồng nghĩa quyền tự chuyển stage.
- Mặc định `strict`: ghi artifact -> chạy `python3 .speedy/scripts/speedy_cli.py handoff validate` -> gửi link file -> gọi `ask_question` chờ người dùng duyệt.
- Phân tầng Gemini: **Gemini Hydrogen** (orchestrator, docs, writer) -> **Gemini Neon** (task bình thường) -> **Gemini Carbon** (chỉ bài toán cực khó/rủi ro cao, hạn chế tối đa quota).
- Không tự ý commit/push/tag, không sửa/skip test trái phép, không ghi secret hoặc ước lượng giả số liệu token.
