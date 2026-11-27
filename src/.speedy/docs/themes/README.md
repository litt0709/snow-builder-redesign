# Speedy Web Themes Library (`.speedy/docs/themes/`)

Thư mục này chứa các bộ **Design System & Layout Template** dựng sẵn dành cho dự án Web (hỗ trợ đầy đủ **Light Mode** và **Dark Mode**). Khi chạy `/flow` lần đầu để dựng dự án Web, Speedy sẽ tự động quét các thư mục con tại đây và bật **HITL Gate (`ask_question`)** để người dùng chọn mẫu áp dụng.

## Danh Sách Mẫu Hiện Có

| Thư mục | Tên mẫu | Phong cách | Ảnh xem trước | Hỗ trợ chế độ |
|---|---|---|---|---|
| `1.default/` | **Apple Clean & Glassmorphism** | Hiện đại, tối giản, thẻ nổi bo tròn mềm, kính mờ glassmorphism, lưới 8pt, tối ưu Dashboard & Web App | [preview-light.png](1.default/preview-light.png) · [preview-dark.png](1.default/preview-dark.png) | **Light Mode + Dark Mode** |
| `2.tabler/` | **Tabler Enterprise Admin** | Giao diện quản trị doanh nghiệp sắc nét chuẩn Tabler (Bootstrap 5, font Inter, viền 1px mảnh, KPI sparkline, Data Table & Dark Sidebar) | [preview-light.png](2.tabler/preview-light.png) · [preview-dark.png](2.tabler/preview-dark.png) | **Light Mode + Dark Mode** |
| `3.midnight/` | **Midnight Pro (Aave-Inspired)** | Dark-first obsidian sang trọng, border bo tròn mềm mại (`20px–24px` & full-pill), font geometric sắc nét, filter emoji icon & Bento Explore Table | [preview-light.png](3.midnight/preview-light.png) · [preview-dark.png](3.midnight/preview-dark.png) | **Dark-First + Light Mode** |

## Quy Ước Mở Rộng Mẫu Mới
Để bổ sung thêm mẫu theme trong tương lai, chỉ cần tạo thư mục mới dạng `<stt>.<ten-theme>/` (ví dụ `2.editorial-minimal/`, `3.cyber-slate/`) gồm:
- `1.DESIGN_SYSTEM_AND_TOKENS.md`: Bảng màu đầy đủ **Light Mode + Dark Mode** (CSS variables), Typography, Elevation/Shadow, Radius & Spacing.
- `2.LAYOUT_AND_TEMPLATES.md`: Bố cục trang chủ/dashboard và các khối UI chuẩn tương thích cả Light & Dark Mode.
- `preview-light.png` & `preview-dark.png`: 2 ảnh minh họa giao diện mẫu ở Light Mode và Dark Mode để người dùng mở xem trước khi chọn.
