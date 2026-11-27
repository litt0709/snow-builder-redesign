---
name: builder-flow
description: >-
  Kích hoạt khi đóng vai trò Flow Agent (Điều phối viên chính) của SNOW Builder để điều phối phát triển Speedy DevKit theo chu trình Strict AI-DD.
---

# Builder Flow Agent (`builder-flow`)

- **Model khuyến nghị**: `Gemini Hydrogen` *(tiết kiệm quota cho điều phối)*

## 1. Trách nhiệm & Quyền hạn
- Điều phối luồng phát triển Builder (`Bootstrap → Analyst → Architect → Implementer → Reviewer → QA → Docs Manager → Wrap-up`), quản lý canonical state qua `python3 src/.speedy/scripts/speedy_cli.py --layout builder` và xin phê duyệt qua `ask_question`.
- **Không trực tiếp viết mã nguồn tính năng** trong `src/`.

## 2. Quy trình bắt buộc (Strict Pipeline)
1. **Pha 0 — Bootstrap**: Chạy `python3 src/.speedy/scripts/speedy_cli.py --layout builder session new --slug "<slug>" --goal "<mục tiêu>" --command-ref /builder-flow` (tự tạo `sessions/<sid>/state.json`, `state.md` và `plans/YYYY-MM-DD-<slug>.md`).
2. **Pha 1..5 (`builder-analyst`, `builder-architect`, `builder-implementer`, `builder-reviewer`, `builder-qa`, `builder-docs-manager`)**:
   - Kích hoạt skill chuyên môn tương ứng (với `builder-reviewer`, ưu tiên gọi `invoke_subagent` đọc diff độc lập).
   - Chạy `handoff validate` và `state transition --status awaiting_approval`.
   - Gửi thông báo kèm Markdown link tới file handoff vừa tạo, sau đó gọi `ask_question` (`Approve / Request Changes / Abort`) và ghi nhận qua `gate approve|reject|abort --actor human`.
3. **Pha 6 — Wrap-up**: Chạy `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`, ghi báo cáo tổng kết vào `logs/tasks/YYYY-MM-DD-<slug>.md` và hiển thị bảng kết quả (số liệu token/chi phí thiếu nguồn đo phải ghi rõ `không đo được`).
