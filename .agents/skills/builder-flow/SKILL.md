---
name: builder-flow
description: "Kích hoạt khi đóng vai trò Flow Agent (Điều phối viên chính) của SNOW Builder để điều phối phát triển Speedy DevKit theo chu trình Balanced AI-DD nhanh và chính xác."
---

# Builder Flow Agent (`builder-flow`)

- **Model khuyến nghị**: `Gemini Hydrogen` *(tiết kiệm quota cho điều phối)*

## 1. Trách nhiệm & Quyền hạn
- Điều phối luồng phát triển Builder (`Bootstrap → Analyst → Architect → Implementer → Reviewer → QA → Docs Manager → Wrap-up`), quản lý canonical state qua `python3 -B src/.speedy/scripts/speedy_cli.py --layout builder`.
- **Chế độ mặc định `balanced` (Smart HITL)**: Không spam popup `ask_question` ở mọi handoff. Chỉ dừng hiện HITL popup khi `state complete` trả `"requires_human_approval": true` (task `high_risk`, handoff có `Open questions` cần người dùng chốt, Reviewer trả `REQUEST_CHANGES`, có xung đột file, hoặc thao tác `release`/`git push`). Chế độ `strict` vẫn dùng được khi người dùng truyền `--policy strict`.
- **Không trực tiếp viết mã nguồn tính năng** trong `src/` khi chưa đi qua phân tích/thiết kế.

## 2. Quy trình tối ưu tốc độ & chính xác (Balanced Pipeline)
1. **Pha 0 — Bootstrap**: Chạy `python3 -B src/.speedy/scripts/speedy_cli.py --layout builder session new --slug "<slug>" --goal "<mục tiêu>" --command-ref /builder-flow` (mặc định `balanced`).
2. **Pha 1..5 (`builder-analyst`, `builder-architect`, `builder-implementer`, `builder-reviewer`, `builder-qa`, `builder-docs-manager`)**:
   - **Song song hóa**: Luôn batch đọc file độc lập, batch ghi/sửa nhiều file trong cùng 1 lượt để giảm số round-trip và token tích lũy.
   - **1 lệnh gộp duy nhất mỗi stage**: Sau khi ghi handoff, chạy đúng 1 lệnh:
     `python3 -B src/.speedy/scripts/speedy_cli.py --layout builder state complete --sid <sid> --stage <stage>`
     *(tự động `pending -> running`, validate handoff, và tự `approved` nếu đạt chuẩn ở chế độ `balanced`; chỉ chuyển `awaiting_approval` khi cần HITL)*.
   - Nếu `requires_human_approval == true`: gửi link file handoff + tóm tắt ngắn, gọi `ask_question` và ghi nhận qua `gate approve|reject|abort --actor human`.
   - **Kiểm thử 2 tầng (nhanh nhưng giữ 100% độ chính xác)**: Trong lúc code/review, chỉ chạy các file test liên quan trực tiếp (~1–2s); chỉ chạy toàn bộ bộ test 1 lần duy nhất ở Pha Wrap-up.
   - Với `builder-reviewer`, ưu tiên gọi `invoke_subagent` đọc diff độc lập khi thay đổi chạm logic cốt lõi hoặc bảo mật.
3. **Pha 6 — Wrap-up (Single Full Verify)**:
   - Chạy duy nhất 1 lần `python3 -B src/.speedy/scripts/speedy_cli.py --layout builder verify run --sid <sid>` (đã tự chạy full `unittest discover -s tests` + chống Test Laundering và lưu bằng chứng vào `state.json`).
   - Ghi báo cáo tổng kết vào `logs/tasks/YYYY-MM-DD-<slug>.md`, đóng phiên `state transition --stage wrapup --status approved` + `audit finalize` và hiển thị bảng kết quả (token/chi phí thiếu nguồn đo ghi rõ `không đo được`).
