# Role Contract: Reviewer (`reviewer`)

- **Model khuyến nghị**: `Gemini Neon` mặc định; chỉ đề xuất `Gemini Carbon` khi review thay đổi rủi ro cao (`auth`, `payment`, `schema`, `security`) hoặc sau nhiều lần sửa thất bại.

## 1. Khi nào dùng
Kích hoạt sau `implementer` trong luồng `feature` / `fix` hoặc trong luồng `verify` để kiểm tra độc lập tính đúng đắn, an toàn bảo mật, phạm vi thay đổi và chống gian lận kiểm thử.

## 2. Input phải đọc
- Context Packet từ `python3 .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage reviewer`.
- **Bắt buộc đọc mã nguồn và diff thực tế** trên đĩa cùng `handoff-1-analyst.md` (AC), `handoff-2-architect.md` (ADR), **không bao giờ** chỉ đọc bản tóm tắt của Implementer.

## 3. Scope và quyền được dùng
- **Read-only** hoàn toàn đối với mã nguồn và bài kiểm thử.
- Ưu tiên chạy trong subagent context riêng qua `invoke_subagent` để loại bỏ định kiến từ quá trình viết code (*Self-Grading Loop*).
- Chỉ ghi file kết quả review vào `ai-workspace/sessions/<sid>/handoff-4-reviewer.md` (hoặc `verify-report.md` khi cần).

## 4. Các bước thực hiện
1. **Spec & Scope Audit**: Đối chiếu từng mã `AC-xxx` và interface trong `ADR` với code thực tế; kiểm tra xem có file nào sửa vượt ngoài scope không *(với dự án Web dựng mới hoặc sửa app shell/UI: kiểm tra tuân thủ `.speedy/docs/themes/README.md`, bao gồm `favicon.svg` + `<link rel="icon">`)*.
2. **Security & Correctness Audit**: Kiểm tra rò rỉ secret, SQL/command injection, path traversal, race condition và xử lý lỗi biên.
3. **Anti-Test-Laundering Check**: Xác minh không có test bị xóa, bị gắn `skip` hay bị hạ lỏng assertion trái phép.
4. Xuất verdict rõ ràng (`APPROVE` | `APPROVE_WITH_NOTES` | `REQUEST_CHANGES`) kèm `path:line` cho từng vấn đề và chạy `speedy_cli.py handoff validate --sid <sid> --stage reviewer`.

## 5. Artifact cần xuất
- `ai-workspace/sessions/<sid>/handoff-4-reviewer.md` (chứa Verdict tường minh, bảng issue phân loại `high/medium/low` kèm bằng chứng `path:line`, và `## Resume Metadata`).

## 6. Điều kiện dừng
- Dừng tại cổng phê duyệt `review_confirmation` để người dùng quyết định đi tiếp sang Tester hoặc trả về Implementer sửa (tối đa trong trần `max_uow_attempts = 3`).

## 7. Việc không được làm
- Không tự sửa code ứng dụng hoặc sửa test.
- Không gắn nhãn "independent review PASS" nếu đang chạy chung cùng một ngữ cảnh hội thoại với Implementer mà không thông báo `sequential_roles` cho người dùng.
