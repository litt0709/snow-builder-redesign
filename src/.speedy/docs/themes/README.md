# Speedy Web Themes Library (`.speedy/docs/themes/`)

Thư mục này chứa các bộ **Design System & Layout Template** dựng sẵn dành cho dự án Web (hỗ trợ đầy đủ **Light Mode** và **Dark Mode**). Khi chạy `/flow` lần đầu để dựng dự án Web, Speedy sẽ tự động quét các thư mục con tại đây và bật **HITL Gate (`ask_question`)** để người dùng chọn mẫu áp dụng.

## 1. Danh Sách Mẫu Hiện Có

| Thư mục | Tên mẫu | Phong cách | Ảnh xem trước | Hỗ trợ chế độ |
|---|---|---|---|---|
| `1.default/` | **Sky Clean & Soft Elevation** | Sáng thoáng Light-First (nền `#f1f5f9`, thẻ trắng viền rõ, Sky Blue `#0284c7`), Dark Mode Deep Navy + Sky Cyan (`#38bdf8`), Collapsible Sidebar `240px → 70px` | [preview-light.png](1.default/preview-light.png) · [preview-dark.png](1.default/preview-dark.png) | **Light-First + Dark Mode** |
| `2.tabler/` | **Tabler Enterprise Admin** | Giao diện quản trị doanh nghiệp sắc nét chuẩn Tabler (Bootstrap 5, font Inter, viền 1px mảnh, KPI sparkline, Data Table & Dark Sidebar) | [preview-light.png](2.tabler/preview-light.png) · [preview-dark.png](2.tabler/preview-dark.png) | **Light Mode + Dark Mode** |
| `3.midnight/` | **Midnight Pro (Aave-Inspired)** | Dark-first obsidian sang trọng, border bo tròn mềm mại (`20px–24px` & full-pill), font geometric sắc nét, filter emoji icon & Bento Explore Table | [preview-light.png](3.midnight/preview-light.png) · [preview-dark.png](3.midnight/preview-dark.png) | **Dark-First + Light Mode** |
| `4.apple/` | **Apple Minimalist & Storefront** | Tinh khiết chuẩn Apple.com (`#ffffff` / `#f5f5f7`, Apple Blue `#0071e3`, tiêu đề 2 tông màu, Sticky Split Configurator, thẻ chọn viền `2px` & nút Full-Pill; Dark OLED `#000000`) | [preview-light.png](4.apple/preview-light.png) · [preview-dark.png](4.apple/preview-dark.png) | **Light-First + Dark OLED** |

---

## 2. Quy Tắc Bất Biến Về UI/UX, Typography & Spacing (Áp Dụng Cho Mọi Theme)

Để giao diện dựng ra luôn thoáng, sắc nét, không bị dính chữ hay bí bách, `Architect` và `Implementer` **BẮT BUỘC** tuân thủ 4 chốt chặn sau:

### 2.1. Strict 6-Level Type Scale (Cấm cỡ chữ lẻ như `10.5px`, `11.5px`, `13.5px`)
Chỉ sử dụng đúng **6 bậc cỡ chữ chuẩn** sau để đảm bảo nhịp điệu đồng đều trên toàn bộ ứng dụng:

| Bậc | Cỡ chữ | `line-height` | `font-weight` | `letter-spacing` | Phạm vi sử dụng |
|---|---|---|---|---|---|
| `xs` (Micro) | `12px` (`0.75rem`) | `1.4` | `500–600` | `0.02em` (hoặc `0.06em` nếu uppercase) | Badge, pretitle, timestamp *(cấm nhỏ hơn `12px` cho nội dung đọc)* |
| `sm` (Secondary) | `14px` (`0.875rem`) | `1.55` | `400–500` | `0` | Nhãn form, bảng dữ liệu, metadata, nút nhỏ, menu item |
| `base` (Body) | `15px–16px` (`0.9375rem–1rem`) | `1.6` | `400` | `0` | Văn bản đọc chính, mô tả, nội dung chính *(chống cảm giác chữ quá bé)* |
| `lg` (Card Title) | `18px` (`1.125rem`) | `1.35` | `600` | `-0.01em` | Tiêu đề Card, tiêu đề nhóm section, modal title |
| `xl` (Page Title) | `24px` (`1.5rem`) | `1.3` | `700` | `-0.015em` | Tiêu đề chính của trang (`h1`) |
| `2xl` (Hero / KPI) | `28px–32px` (`1.75rem–2rem`) | `1.2` | `700` | `-0.02em` | Hero banner, con số KPI nổi bật (`font-variant-numeric: tabular-nums`) |

- **Tối ưu Tiếng Việt có dấu**: Tuyệt đối giữ `letter-spacing: 0` cho mọi chữ `< 20px` (Body, Button, Input, Table, Label) và `line-height >= 1.5` để dấu thanh (`ệ`, `ộ`, `ử`) không bao giờ dính sát nhau.

### 2.2. Sàn Khoảng Thở Tối Thiểu (Spacing Floor — Chống Dính & Bí Bách)
- **Page Container**: `padding-inline: 24px` (mobile `16px`), khoảng cách giữa các section lớn **`>= 32px`** (`gap: 32px` / `space-y-8`).
- **Card & Panel**: Padding bên trong **`20px–24px`** (`p-5` / `p-6`); khoảng cách giữa các card **`16px–20px`** (`gap-4` / `gap-5`); khoảng cách tiêu đề ↔ mô tả phụ **`6px–8px`**.
- **Button & Input (Touch & Click Ergonomics)**: Chiều cao tối thiểu **`40px`** (`min-height: 40px`); padding nút **`10px 18px`**; padding ô input **`10px 14px`**; khoảng cách icon ↔ chữ **`8px`** (`gap: 8px`).
- **Data Table**: Padding từng ô tối thiểu **`12px 16px`**, chiều cao hàng tối thiểu **`48px`**.

### 2.3. Tailwind CSS v4 Cascade Guardrail (Tránh Mất Padding/Margin)
- Khi dùng **Tailwind CSS v4** (`@import "tailwindcss";`), **BẮT BUỘC** bọc toàn bộ reset (`html, body`) trong `@layer base { ... }` và bọc các class dùng chung (`.btn`, `.card`, `.input`) trong `@layer components { ... }`.
- **Cấm** viết CSS unlayered đặt `padding`/`margin` cố định lên component class (vì CSS unlayered ghi đè `@layer utilities` khiến `p-6`, `px-4`, `mb-6` của Tailwind bị vô hiệu hóa!).

### 2.4. Checklist Tự Kiểm Tra UI Trước Khi Hoàn Tất Implementer
- [ ] Không còn cỡ chữ lẻ (`10.5px`, `13.5px`...) hoặc chữ `< 12px` cho nội dung đọc.
- [ ] Toàn bộ Button/Input có `min-height >= 40px`, Card có `padding >= 20px`, Section cách nhau `>= 32px`.
- [ ] Không có CSS unlayered đè lên Tailwind utilities; Light Mode & Dark Mode đều đủ độ tương phản.

---

## 3. Quy Ước Mở Rộng Mẫu Mới
Để bổ sung thêm mẫu theme trong tương lai, tạo thư mục dạng `<stt>.<ten-theme>/` gồm:
- `1.DESIGN_SYSTEM_AND_TOKENS.md`: Bảng màu **Light Mode + Dark Mode** (CSS variables), Strict Type Scale, Elevation/Shadow, Radius & Spacing Tokens.
- `2.LAYOUT_AND_TEMPLATES.md`: Bố cục trang và các khối UI chuẩn tương thích cả Light & Dark Mode.
- `preview-light.png` & `preview-dark.png`: 2 ảnh minh họa giao diện mẫu ở Light Mode và Dark Mode.
