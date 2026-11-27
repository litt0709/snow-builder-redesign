# `/refresh-rule` (`speedy-refresh-rule`) — Cập Nhật Quy Ước Lập Trình Dự Án

## Mô tả
Quét mã nguồn và các file cấu hình linter/formatter hiện có của dự án để cập nhật quy ước lập trình thực tế vào `ai-workspace/docs/development-rules/`, giữ nguyên phần nguyên tắc nền tảng trong `principles.md`.

## Input & Output
- **Input**: Mã nguồn ứng dụng và cấu hình (`.editorconfig`, `pyproject.toml`, `eslint`, `prettierrc`, `tsconfig.json`, `checkstyle.xml`...).
- **Output**:
  - `ai-workspace/docs/development-rules/coding-convention.md`
  - `ai-workspace/docs/development-rules/review.md` (mở đầu tham chiếu `principles.md`, không chép lặp)
  - `ai-workspace/docs/development-rules/test.md`
  - Chỉ bổ sung vào cuối mục *"Ghi chú riêng dự án"* của `principles.md` nếu có quy ước đặc thù có bằng chứng.

## Scope & Gate
- **Scope**: Chỉ đọc vùng ứng dụng (bỏ qua `.speedy/`, `.agents/`, `ai-workspace/`); chỉ ghi vào `ai-workspace/docs/development-rules/`.
- **Gate**: Chỉ ghi nhận những quy ước có bằng chứng từ file thực tế; phần chưa có dữ kiện ghi rõ `[chưa đủ evidence]`, không tự đoán.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Dự án trống chưa có code thì dừng và thông báo chưa có mẫu mã nguồn để trích xuất.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /refresh-rule`.
