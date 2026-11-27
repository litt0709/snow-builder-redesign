# Feature Flow — Chu Trình AI-DD Đầy Đủ

Áp dụng cho `FLOW_MODE = feature` (và phần sau Bước 0.4 của `fix-flow.md`).

---

## Bước 1 — Analyst (`Gemini Neon`)
1. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage analyst --status running`.
2. Chuẩn bị Context Packet: `python3 .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage analyst`.
3. Đọc `.speedy/roles/analyst.md`, tra cứu `repomap query` và tạo `ai-workspace/sessions/<sid>/handoff-1-analyst.md` (có mã `AC-001..N` rõ ràng).
4. Chạy `speedy_cli.py state transition --sid <sid> --stage analyst --status awaiting_approval`.
5. **HITL Gate (`brief_confirmation`)**: Gửi link `handoff-1-analyst.md` → gọi `ask_question` → ghi nhận qua `speedy_cli.py gate approve|reject|abort --sid <sid> --stage analyst --actor human --interaction-ref <ref>`.

---

## Bước 2 — Architect (`Gemini Neon` | `Gemini Carbon` nếu phức tạp/rủi ro cao)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage architect --status running`.
2. Chuẩn bị Context Packet: `speedy_cli.py context prepare --sid <sid> --stage architect`.
3. Đọc `.speedy/roles/architect.md`, lập bảng so sánh phương án, mục `## ADR` và interface chi tiết vào `ai-workspace/sessions/<sid>/handoff-2-architect.md`. *(Nếu là dự án Web có `selected_theme` trong `ai-workspace/state/setup.json`, đọc thêm `.speedy/docs/themes/<selected_theme>/` để đồng bộ Design Tokens Light/Dark Mode vào thiết kế).*
4. Chạy `speedy_cli.py state transition --sid <sid> --stage architect --status awaiting_approval`.
5. **HITL Gate (`design_confirmation`)**: Gửi link `handoff-2-architect.md` → gọi `ask_question` → ghi nhận qua `speedy_cli.py gate`.

---

## Bước 3 — Implementer (`Gemini Neon`)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage implementer --status running`.
2. Chuẩn bị Context Packet: `speedy_cli.py context prepare --sid <sid> --stage implementer`.
3. Đọc `.speedy/roles/implementer.md`, viết mã nguồn đúng trong `scope` của thiết kế và xuất `ai-workspace/sessions/<sid>/handoff-3-implementer.md`.
4. Chạy `speedy_cli.py state transition --sid <sid> --stage implementer --status awaiting_approval` rồi **chuyển thẳng sang Bước 4 (Reviewer)** để có đánh giá độc lập trước khi trình người dùng.

---

## Bước 4 — Reviewer Độc Lập (`invoke_subagent` · `Gemini Neon` / `Gemini Carbon`)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage reviewer --status running`.
2. Chuẩn bị Context Packet: `speedy_cli.py context prepare --sid <sid> --stage reviewer`.
3. **Ưu tiên gọi `invoke_subagent`** (read-only) đọc `.speedy/roles/reviewer.md`, `handoff-1-analyst.md`, `handoff-2-architect.md` và mã nguồn/diff thực tế trên đĩa để tránh *Self-Grading Loop*. Nếu môi trường không dùng được subagent, chạy tuần tự và báo rõ `sequential_roles`.
4. Ghi `ai-workspace/sessions/<sid>/handoff-4-reviewer.md` (Verdict: `APPROVE` | `APPROVE_WITH_NOTES` | `REQUEST_CHANGES`) và chuyển `awaiting_approval`.
5. **HITL Gate (`review_confirmation`)**: Gửi link `handoff-4-reviewer.md` + `handoff-3-implementer.md` → gọi `ask_question`:
   - Nếu `APPROVE` và người dùng duyệt: `speedy_cli.py gate approve --sid <sid> --stage reviewer --actor human --interaction-ref <ref>` → sang Bước 5.
   - Nếu `REQUEST_CHANGES` hoặc người dùng yêu cầu sửa: `speedy_cli.py gate reject --sid <sid> --stage reviewer --return-to implementer --actor human --interaction-ref <ref>` → quay lại Bước 3 (tối đa trong trần `max_uow_attempts = 3`; chạm trần CLI tự chuyển sang `blocked`).

---

## Bước 5 — Tester & Verification Gate (`Gemini Neon`)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage tester --status running` và `context prepare --sid <sid> --stage tester`.
2. Đọc `.speedy/roles/tester.md`, viết Unit/Integration tests phủ kín toàn bộ `AC-001..N`.
3. **Chạy Verification thực tế kèm kiểm tra chống Test Laundering**:
   ```bash
   python3 .speedy/scripts/speedy_cli.py verify run --sid <sid>
   ```
   *(Nếu `FAIL`, không được tự đổi thành `PASS`; ghi rõ lỗi và hỏi người dùng quay về Bước 3 sửa hoặc dừng).*
4. Ghi `ai-workspace/sessions/<sid>/handoff-5-tester.md`, chuyển `awaiting_approval` và thực hiện **HITL Gate (`delivery_confirmation`)**.

---

## Bước 6 — Docs Manager (`Gemini Hydrogen`)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage docs --status running` và đọc `.speedy/roles/docs-manager.md`.
2. Đồng bộ đúng tài liệu bị ảnh hưởng trong `ai-workspace/docs/` và ghi `ai-workspace/sessions/<sid>/handoff-6-docs.md`.
3. Trong chế độ `strict`: chuyển `awaiting_approval` → gửi link → gọi `ask_question` → `gate approve`. *(Trong chế độ `balanced` không rủi ro cao: cho phép chuyển `approved` sau khi `handoff validate` đạt).*

---

## Bước 7 — Wrap-up & Báo Cáo Trung Thực (`Gemini Hydrogen`)
1. Chạy `speedy_cli.py state transition --sid <sid> --stage wrapup --status running` → `speedy_cli.py state transition --sid <sid> --stage wrapup --status approved`.
2. Ghi báo cáo tổng kết tại `ai-workspace/logs/tasks/YYYY-MM-DD-<slug>.md` và đóng audit bằng `speedy_cli.py audit finalize --audit-dir <audit_dir> --outcome success --completion-level verified --ac-passed <N> --ac-total <N> --build-status pass`.
3. Hiển thị bảng tổng kết các stage, link tới session/report và số liệu thời gian/token từ `04-cost-time.json` (nếu `not_measured` thì ghi rõ `không đo được`).
