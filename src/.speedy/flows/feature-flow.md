# Feature Flow — Chu Trình AI-DD Nhanh & Chính Xác

Áp dụng cho `FLOW_MODE = feature` (và phần sau Bước 0.4 của `fix-flow.md`).
**Quy ước tăng tốc bắt buộc**: Luôn dùng `python3 -B`, batch song song các file đọc/ghi độc lập, và dùng **1 lệnh gộp duy nhất** `state complete` cuối mỗi stage thay vì gọi tách 3 lệnh.

---

## Quy Tắc Kết Thúc Mỗi Stage (Smart Gate)
Sau khi ghi file handoff của stage, chạy đúng 1 lệnh:
```bash
python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>
```
- Nếu `"requires_human_approval": false` (`balanced` không `high_risk`, không `Open questions`, không `REQUEST_CHANGES`) → **đi tiếp ngay** sang stage kế tiếp.
- Nếu `"requires_human_approval": true` → gửi link artifact + tóm tắt ngắn → gọi `ask_question` (`Approve / Request Changes / Abort`) → ghi nhận qua `gate approve|reject|abort --sid <sid> --stage <stage> --actor human --interaction-ref <ref>`.

---

## Bước 1 — Analyst (`Gemini Neon`)
1. Chạy `context prepare --sid <sid> --stage analyst` (kết hợp `repomap query` trong 1 lệnh shell).
2. Đọc `.speedy/roles/analyst.md`, khóa Scope/Non-goals và định nghĩa `AC-001..N` kiểm chứng được vào `ai-workspace/sessions/<sid>/handoff-1-analyst.md` (nêu rõ câu hỏi vào `## Open questions` nếu còn điểm mơ hồ).
3. Chạy `state complete --sid <sid> --stage analyst`.

## Bước 2 — Architect (`Gemini Neon` | `Gemini Carbon` nếu phức tạp/rủi ro cao)
1. Đọc `.speedy/roles/architect.md` + `handoff-1-analyst.md` *(nếu là dự án Web có `selected_theme` trong `ai-workspace/state/setup.json`, đọc thêm `.speedy/docs/themes/<selected_theme>/`)*.
2. Lập bảng so sánh phương án, mục `## ADR` (đảm bảo **SSOT**, SOLID/KISS/DRY/YAGNI) và kế hoạch UoW vào `ai-workspace/sessions/<sid>/handoff-2-architect.md`.
3. Chạy `state complete --sid <sid> --stage architect`.

## Bước 3 — Implementer (`Gemini Neon`)
1. Đọc `.speedy/roles/implementer.md` + `handoff-2-architect.md`.
2. Batch chỉnh sửa mã nguồn trong `scope` đã duyệt; chạy **targeted test / lint nhanh** cho riêng module bị ảnh hưởng (không chạy thừa full suite).
3. Ghi `ai-workspace/sessions/<sid>/handoff-3-implementer.md` → chạy `state complete --sid <sid> --stage implementer`.

## Bước 4 — Reviewer Độc Lập (`invoke_subagent` · `Gemini Neon` / `Gemini Carbon`)
1. **Ưu tiên gọi `invoke_subagent`** (read-only) đọc `.speedy/roles/reviewer.md`, `AC`/`ADR` và diff thực tế để chống *Self-Grading Loop* (kiểm tra bảo mật, SSOT, 11 Anti-Patterns). Nếu không dùng được subagent, chạy tuần tự và ghi rõ `sequential_roles`.
2. Ghi `ai-workspace/sessions/<sid>/handoff-4-reviewer.md` (nêu rõ `Verdict: APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES`) → chạy `state complete --sid <sid> --stage reviewer`.
   - Nếu `REQUEST_CHANGES`: CLI tự khóa ở `awaiting_approval`; quay lại Bước 3 sửa triệt để (tối đa `max_uow_attempts = 3`).

## Bước 5 — Tester & Verification Gate (`Gemini Neon`)
1. Đọc `.speedy/roles/tester.md`, viết Unit/Integration tests phủ kín 100% `AC-001..N` (cấm Test Laundering).
2. Chạy **1 lần Verification đầy đủ duy nhất**:
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py verify run --sid <sid>
   ```
   *(Nếu `FAIL`, giữ nguyên `FAIL` và quay về Bước 3 sửa đúng nguyên nhân gốc).*
3. Ghi `ai-workspace/sessions/<sid>/handoff-5-tester.md` (bảng đối chiếu `AC-xxx` vs kết quả thật) → chạy `state complete --sid <sid> --stage tester`.

## Bước 6 — Docs Manager & Knowledge Sync (`Gemini Hydrogen`)
1. Đọc `.speedy/roles/docs-manager.md` + `handoff-2-architect.md` + `handoff-3-implementer.md`.
2. Đảm bảo **Bộ Knowledge Base Lớp 2** trong `ai-workspace/docs/` đầy đủ cho các phiên chạy sau (tạo mới nếu chưa có, cập nhật phần thay đổi nếu đã có):
   - `ai-workspace/docs/architecture/overview.md` (Index nhẹ + link tới tài liệu chi tiết)
   - `ai-workspace/docs/architecture/architecture.md` (**Bắt buộc**: Tech Stack, sơ đồ Mermaid luồng dữ liệu, Data Model/Schema, API Contracts & các quyết định ADR)
   - `ai-workspace/docs/architecture/<module>.md` (nếu thêm/đổi module lớn, kèm `source_ref`), `ai-workspace/docs/guides/quickstart.md` (lần đầu hoặc khi đổi lệnh chạy) và `ai-workspace/docs/CHANGELOG.md`.
3. Chạy `python3 -B .speedy/scripts/speedy_cli.py repomap build` để làm mới chỉ mục mã nguồn cho các phiên sau.
4. Ghi `ai-workspace/sessions/<sid>/handoff-6-docs.md` → chạy `state complete --sid <sid> --stage docs`.

## Bước 7 — Wrap-up & Báo Cáo Trung Thực (`Gemini Hydrogen`)
1. Đóng phiên & audit trong 1 lệnh chain:
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage wrapup --status running && python3 -B .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage wrapup --status approved && python3 -B .speedy/scripts/speedy_cli.py audit finalize --audit-dir <audit_dir> --outcome success --completion-level verified --ac-passed <N> --ac-total <N> --build-status pass
   ```
2. Ghi báo cáo ngắn gọn tại `ai-workspace/logs/tasks/YYYY-MM-DD-<slug>.md` và hiển thị bảng tổng kết kèm link artifact (số liệu token/chi phí thiếu nguồn đo ghi rõ `không đo được`).
