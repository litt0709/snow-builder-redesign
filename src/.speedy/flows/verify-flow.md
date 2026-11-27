# Verify Flow — Kiểm Chứng Độc Lập Mã Nguồn Đã Có

Áp dụng khi `FLOW_MODE = verify`. Luồng này **chỉ kiểm tra và báo cáo**, tuyệt đối không tự ý sửa đổi mã nguồn ứng dụng.

---

## Bước V1 — Khóa Phạm Vi & Yêu Cầu Gốc

Gọi `ask_question` (nếu thông tin trong prompt ban đầu chưa chỉ rõ) để xác nhận:
1. Tài liệu yêu cầu gốc / danh sách AC cần đối chiếu.
2. Thư mục hoặc module mã nguồn cần kiểm chứng.

---

## Bước V2 — Reviewer Độc Lập (`invoke_subagent` · `Gemini Neon` / `Gemini Carbon`)

1. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage reviewer --status running`.
2. Gọi `invoke_subagent` (read-only) thực hiện theo `.speedy/roles/reviewer.md`: đọc mã nguồn thực tế, đối chiếu từng yêu cầu gốc, rà soát bảo mật và ghi `ai-workspace/sessions/<sid>/handoff-4-reviewer.md`.
3. Chuyển `awaiting_approval`, gửi link `handoff-4-reviewer.md` và hỏi người dùng qua `ask_question`:
   - `(Recommended) Tiếp tục bước Tester để chạy kiểm thử & đo độ phủ AC`
   - `Bỏ qua bước viết thêm test, chuyển thẳng sang tổng hợp Verify Report`
   - `Abort — Dừng phiên`

---

## Bước V3 — Thực Thi Kiểm Thử Hiện Hữu (`tester` · Tùy chọn theo V2)

- Nếu người dùng chọn chạy kiểm thử: thực thi `speedy_cli.py verify run --sid <sid>`, ghi nhận bằng chứng thật và xuất `handoff-5-tester.md` (hoặc đánh dấu `skipped` cho stage `tester` nếu người dùng chọn bỏ qua).

---

## Bước V4 — Xuất Báo Cáo Xác Minh (`verify_report`) & Wrap-up

1. Tổng hợp `ai-workspace/sessions/<sid>/verify-report.md` (phân loại trung thực từng hạng mục: `PASS` | `FAIL` | `PARTIAL` | `NOT_VERIFIED`, không đánh đồng `SKIP` thành `PASS`).
2. Chuyển `verify_report` sang `awaiting_approval`, gửi link báo cáo và gọi `ask_question`:
   - Nếu phát hiện lỗi và người dùng muốn sửa ngay: đóng phiên `verify` hiện tại và khởi tạo phiên mới với `.speedy/flows/fix-flow.md`.
   - Nếu hoàn tất kiểm tra: `gate approve` cho `verify_report`, hoàn tất `wrapup` và finalize audit.
