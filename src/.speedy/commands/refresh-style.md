# `/refresh-style` (`speedy-refresh-style`) — Cập Nhật Style Guide Dự Án

## Mô tả
Phân tích phong cách viết code thực tế của dự án (**① Repo Style — ưu tiên số 1**) và bổ sung tham chiếu chuẩn ngành (**② Industry Reference Style — ưu tiên số 2**) vào `ai-workspace/docs/development-style/STYLE.md`.

## Input & Output
- **Input**: Tối đa 500 file mã nguồn đại diện của dự án + tài liệu style guide chính thức của ngôn ngữ/framework (khi có quyền tra cứu web).
- **Output**: `ai-workspace/docs/development-style/STYLE.md` tách bạch rõ hai phần `① Repo Style` và `② Industry Reference Style` kèm nguồn trích dẫn.

## Scope & Gate
- **Scope**: Chỉ ghi file vào `ai-workspace/docs/development-style/`; không để Industry Style ghi đè Repo Style.
- **Gate**: Nếu môi trường tắt mạng hoặc không tra cứu được nguồn ngoài, ghi trung thực `[không tra cứu ngoài — chỉ áp dụng Repo Style]`, không bịa URL hay nội dung.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Bỏ qua thư mục thư viện bên thứ ba (`node_modules`, `.venv`, `vendor`, `target`); báo rõ số file thực tế đã khảo sát.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /refresh-style`.
