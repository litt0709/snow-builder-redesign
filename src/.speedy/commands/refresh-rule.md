# `/refresh-rule` — Cập Nhật Quy Ước Lập Trình Dự Án (Brownfield & Greenfield)

## Mô tả
Xây dựng và cập nhật bộ quy ước kỹ thuật chuẩn **Principal Engineer** vào `ai-workspace/docs/development-rules/`, giữ nguyên phần nguyên tắc nền tảng trong `principles.md`:
- **Chế độ Brownfield (Dự án đã có mã nguồn)**: Quét mã nguồn và cấu hình linter/formatter thực tế để trích xuất đúng quy ước của các kỹ sư cũ (không phá vỡ convention sẵn có).
- **Chế độ Greenfield (Dự án mới chưa có mã nguồn)**: Dựa trên Tech Stack / Framework đã chốt (từ `handoff-2-architect.md` hoặc yêu cầu của User), dùng `search_web` tra cứu **best practices & lint/architecture rules chính thức mới nhất** của từng framework/ngôn ngữ để thiết lập chuẩn mực ngay từ dòng code đầu tiên.

## Input & Output
- **Input**:
  - *Brownfield*: Mã nguồn ứng dụng và cấu hình (`.editorconfig`, `pyproject.toml`, `eslint`, `biome.json`, `prettierrc`, `tsconfig.json`, `checkstyle.xml`...).
  - *Greenfield*: Danh sách ngôn ngữ/framework đã chọn + tài liệu chính thức từ `search_web`.
- **Output**:
  - `ai-workspace/docs/development-rules/coding-convention.md` (quy ước đặt tên, cấu trúc thư mục, xử lý lỗi, typing, bảo mật, anti-patterns của từng framework).
  - `ai-workspace/docs/development-rules/review.md` (checklist review chuẩn Principal Engineer, tham chiếu `principles.md` — không chép lặp).
  - `ai-workspace/docs/development-rules/test.md` (chuẩn viết Unit/Integration test cho stack của dự án).
  - Chỉ bổ sung vào cuối mục *"Ghi chú riêng dự án"* của `principles.md` nếu có quy ước đặc thù có bằng chứng.

## Scope & Gate
- **Scope**: Chỉ đọc vùng ứng dụng (bỏ qua `.speedy/`, `.agents/`, `ai-workspace/`); chỉ ghi vào `ai-workspace/docs/development-rules/`.
- **Gate**:
  - *Brownfield*: Chỉ ghi nhận quy ước có bằng chứng từ file thực tế; phần chưa rõ ghi `[chưa đủ evidence]`.
  - *Greenfield*: Ghi rõ nguồn tham chiếu chính thức (URL/tài liệu chuẩn của framework); nếu tắt mạng thì ghi trung thực `[offline — áp dụng chuẩn cốt lõi của ngôn ngữ/framework]`, không bịa URL.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Nếu dự án vừa trống vừa chưa xác định ngôn ngữ/framework, dừng và hỏi người dùng chọn Tech Stack trước khi sinh rules.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /refresh-rule`.
