# `/refresh-style` — Cập Nhật Style Guide Dự Án (Brownfield & Greenfield)

## Mô tả
Thiết lập bộ Style Guide chuẩn mực tại `ai-workspace/docs/development-style/STYLE.md` theo 2 chế độ:
- **Chế độ Brownfield (Dự án đã có mã nguồn)**: Phân tích phong cách viết code thực tế của các kỹ sư cũ (**① Repo Style — ưu tiên số 1**) và bổ sung chuẩn ngành (**② Industry Reference Style — ưu tiên số 2**).
- **Chế độ Greenfield (Dự án mới chưa có mã nguồn)**: Dựa trên ngôn ngữ & framework vừa chốt (từ `handoff-2-architect.md`), dùng `search_web` tra cứu **Official Style Guide & Principal Engineer Patterns** mới nhất của từng công nghệ (ví dụ formatting, import order, naming, typing, error handling, component/service structure) để tạo `STYLE.md` trước khi Implementer viết dòng code đầu tiên.

## Input & Output
- **Input**:
  - *Brownfield*: Tối đa 500 file mã nguồn đại diện của dự án + tài liệu style guide chính thức của ngôn ngữ/framework.
  - *Greenfield*: Tech Stack / Framework đã chốt + tra cứu `search_web` tài liệu style guide chính thức.
- **Output**: `ai-workspace/docs/development-style/STYLE.md` tách bạch rõ `① Repo Style` *(nếu brownfield)* và `② Industry Reference Style` kèm nguồn trích dẫn.

## Scope & Gate
- **Scope**: Chỉ ghi file vào `ai-workspace/docs/development-style/`; ở dự án brownfield tuyệt đối không để Industry Style ghi đè Repo Style đang dùng.
- **Gate**: Nếu môi trường tắt mạng hoặc không tra cứu được nguồn ngoài, ghi trung thực `[không tra cứu ngoài — áp dụng Repo Style / chuẩn cốt lõi]`, không bịa URL hay nội dung.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Bỏ qua thư mục thư viện bên thứ ba (`node_modules`, `.venv`, `vendor`, `target`); báo rõ số file thực tế đã khảo sát (hoặc danh sách framework đã tra cứu nếu greenfield).
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /refresh-style`.
