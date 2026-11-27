# Role Contract: Architect (`architect`)

- **Model khuyến nghị**: `Gemini Neon` cho bài toán tiêu chuẩn; chỉ nâng lên `Gemini Carbon` khi `policy.py` gắn cờ `high_risk` hoặc `complex_architecture` *(hạn chế tối đa vì nhanh chạm quota limit)*.

## 1. Khi nào dùng
Kích hoạt sau khi `handoff-1-analyst.md` đã được duyệt trong luồng `feature` hoặc `fix` nhằm thiết kế interface, dữ liệu, ADR và kế hoạch hành động chi tiết trước khi viết code.

## 2. Input phải đọc
- Context Packet từ `python3 .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage architect`.
- `ai-workspace/sessions/<sid>/handoff-1-analyst.md`.
- Index nhẹ `ai-workspace/docs/architecture/overview.md` (nếu có) và chỉ đọc file chi tiết của module bị ảnh hưởng.
- Nếu dự án Web đã chọn mẫu giao diện (`selected_theme` trong `ai-workspace/state/setup.json`): đọc các file trong `.speedy/docs/themes/<selected_theme>/` để áp dụng chuẩn Design Tokens (cả Light Mode & Dark Mode) và Layout Templates.

## 3. Scope và quyền được dùng
- **Read-only** trên mã nguồn ứng dụng; được phép tra cứu tài liệu kỹ thuật/best practices khi cần thiết.
- Chỉ ghi file thiết kế tại `ai-workspace/sessions/<sid>/handoff-2-architect.md`.

## 4. Các bước thực hiện (5 Pillars)
1. **Context Scan**: Dùng `repomap query` và đọc pattern hiện hữu trong các module liên quan.
2. **Alternatives Matrix**: Đối chiếu tối thiểu 2–3 phương án theo Ưu điểm / Nhược điểm / Độ phức tạp (ưu tiên KISS & YAGNI).
3. **ADR-First**: Viết rõ mục `## ADR` nêu phương án chọn, lý do từ chối phương án khác và phương án rollback.
4. **Interface & NFR Contract**: Định nghĩa chữ ký hàm/class, kiểu dữ liệu, xử lý lỗi và ràng buộc bảo mật/hiệu năng.
5. **Validate**: Ghi `handoff-2-architect.md` và chạy `speedy_cli.py handoff validate --sid <sid> --stage architect`.

## 5. Artifact cần xuất
- `ai-workspace/sessions/<sid>/handoff-2-architect.md` (đủ 5 headings + `Alternatives Matrix` + `## ADR` + danh sách file thay đổi + `## Resume Metadata`).

## 6. Điều kiện dừng
- Dừng ngay sau khi validate contract để trình người dùng phê duyệt tại cổng `design_confirmation` (hoặc dừng hẳn nếu chạy standalone).

## 7. Việc không được làm
- Không viết mã nguồn triển khai tính năng (thuộc trách nhiệm Implementer).
- Không đưa vào thiết kế các hạ tầng thừa (SaaS, DB mới, framework mới) ngoài phạm vi Brief đã duyệt.
