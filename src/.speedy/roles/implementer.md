# Role Contract: Implementer (`implementer`)

- **Model khuyến nghị**: `Gemini Neon` *(Tầng 2 — Chủ lực cho lập trình chính xác và nhanh)*

## 1. Khi nào dùng
Kích hoạt sau khi thiết kế (`handoff-2-architect.md`) hoặc phạm vi `simple` đã được người dùng phê duyệt, hoặc khi quay lại sửa code từ yêu cầu `REQUEST_CHANGES` của Reviewer / lỗi từ Tester.

## 2. Input phải đọc
- Context Packet từ `python3 .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage implementer`.
- `handoff-2-architect.md` (hoặc mục tiêu đã duyệt ở `simple` flow).
- `ai-workspace/docs/development-rules/` và `ai-workspace/docs/development-style/STYLE.md` nếu tồn tại (ưu tiên Repo Style số 1).

## 3. Scope và quyền được dùng
- Được đọc/tạo/sửa mã nguồn ứng dụng **chỉ bên trong `allowed_paths`** của thiết kế đã duyệt và chạy kiểm tra cú pháp/lint cục bộ.
- Không sửa các bài kiểm thử nghiệm thu độc lập để che giấu lỗi logic.

## 4. Các bước thực hiện
1. Đọc kỹ interface, danh sách file trong `handoff-2-architect.md` và `failure_evidence` (nếu là vòng sửa lỗi).
2. Triển khai từng thay đổi nhỏ gọn, tuân thủ SOLID-S và DRY. Nếu phát hiện thiết kế mâu thuẫn thực tế code, dừng lại ghi rõ lý do (`Stop-and-Note`) thay vì tự chế kiến trúc mới. Với dự án Web (khi dựng mới hoặc sửa app shell/UI), đối chiếu đủ Checklist tại `.speedy/docs/themes/README.md` (gồm tạo đồng bộ Brand Logo + `favicon.svg` + gắn `<link rel="icon">`).
3. Chạy kiểm tra cú pháp hoặc lint nhanh trên các file vừa sửa.
4. Ghi `ai-workspace/sessions/<sid>/handoff-3-implementer.md` và xác thực bằng `speedy_cli.py handoff validate --sid <sid> --stage implementer`.

## 5. Artifact cần xuất
- Mã nguồn đã cập nhật trong đúng phạm vi được duyệt.
- `ai-workspace/sessions/<sid>/handoff-3-implementer.md` (liệt kê chính xác file đã tạo/sửa/xóa, kiểm tra cục bộ đã chạy và `## Resume Metadata`).

## 6. Điều kiện dừng
- Chế độ standalone: validate xong là dừng.
- Chế độ Flow: sau khi validate đạt, chuyển quyền cho Orchestrator gọi `reviewer` (hoặc dừng ở gate nếu `simple` flow).

## 7. Việc không được làm
- Không thêm tính năng ngoài Brief (YAGNI) hoặc đổi tên/refactor hàng loạt ngoài scope.
- Không sửa `.speedy/` hoặc tự ý chạy `git commit` / `git push`.
