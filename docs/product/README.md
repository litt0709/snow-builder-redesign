# Bản Đồ Sản Phẩm Speedy DevKit (`src/`)

> **TL;DR**: Tài liệu ánh xạ toàn bộ kiến trúc, thành phần, 11 slash commands, 9 vai trò, 3 bộ Web Themes và cơ chế vận hành **Balanced AI-DD (Smart HITL)** của **Speedy DevKit** (`src/`) — gói sản phẩm độc lập 100% dành cho **Antigravity (App / CLI / IDE)**.

---

## 1. Phân Vùng Trách Nhiệm Trong `src/`

| Đường dẫn trong `src/` | Quyền sở hữu | Vai trò khi cài sang dự án ứng dụng |
|---|---|---|
| `AGENTS.md` | Kit-owned *(hỏi trước khi ghi đè nếu user đã sửa)* | Entry-point router, bảng Nguyên tắc cốt lõi (User Primacy, Simple Responses, SSOT, Balanced AI-DD, 11 Anti-Patterns), phân tầng Gemini và bảng 11 slash commands |
| `.agents/rules/` | Kit-owned | Rule `always_on` siêu gọn (`00-core-invariants.md`) và 2 rule `glob` (`10-session-context.md`, `20-docs-boundary.md`) |
| `.agents/skills/` | Kit-owned | **11 slash commands ngắn gọn** (`/flow`, `/specs`, `/analyst`, `/docs`, `/docs-view`, `/audit-view`, `/refresh-rule`, `/refresh-style`, `/cleanup`, `/repomap`, `/update-speedy`) — nguồn duy nhất, không trùng lặp legacy workflows |
| `.speedy/VERSION`, `.speedy/manifest.json` | Kit-owned | Phiên bản SemVer và danh mục SHA-256 kiểm soát xung đột cài đặt/cập nhật & dọn file obsolete |
| `.speedy/roles/` | Kit-owned | SSOT hợp đồng **9 vai trò** (`orchestrator`, `specs`, `analyst`, `architect`, `implementer`, `reviewer`, `tester`, `docs-manager`, `writer`) |
| `.speedy/flows/` | Kit-owned | Kịch bản **5 chế độ** (`setup`, `feature`, `fix`, `simple`, `verify`) tối ưu cho `balanced` Smart HITL và `state complete` |
| `.speedy/commands/` | Kit-owned | Đặc tả chi tiết **11 lệnh người dùng** và 2 template chuẩn (`hitl-template.md`, `audit-lifecycle.md`) |
| `.speedy/rules/` | Kit-owned | Bộ luật lõi AI-DD (`1.principle.md` với 5 Subsystems + 11 Anti-Patterns → `2.framework.md` → `3.orchestration-flow.md` → `4.logs.md` → `5.testing.md`) |
| `.speedy/docs/themes/` | Kit-owned | Thư viện **4 bộ Web Design Systems** hỗ trợ Light & Dark Mode kèm ảnh preview (`1.default`, `2.tabler`, `3.midnight`, `4.apple`) |
| `.speedy/schemas/` & `.speedy/config/` | Kit-owned | JSON Schema hợp đồng, cấu hình `balanced` mặc định + phân tầng Gemini (`Hydrogen` / `Neon` / `Carbon`) và `source.json` |
| `.speedy/scripts/` | Kit-owned | Lõi Python 3.11+ stdlib CLI deterministic (`speedy_cli.py` với **Lazy Imports**, cờ **`--compact`**, `state complete`, `installer_core.py`) |
| `ai-workspace/` | **User Runtime (Preserved 100%)** | Bộ nhớ vận hành dự án (`specs/`, `docs/`, `plans/`, `sessions/`, `state/`, `audit/`, `logs/`, `reports/`, `tmp/`, `.env.example`) — **không bao giờ bị xóa/ghi đè khi update** |

---

## 2. Thư Viện Web Themes Dựng Sẵn (`.speedy/docs/themes/`)

Khi chạy `/flow` lần đầu trên dự án Web, Speedy tự quét `.speedy/docs/themes/` và bật `ask_question` để người dùng chọn mẫu:

| Thư mục | Tên mẫu | Đặc trưng thiết kế | Chế độ màu |
|---|---|---|---|
| `1.default/` | **Sky Clean & Soft Elevation** | Sáng thoáng Light-First (Sky Blue `#0284c7`, nền `#f1f5f9`, thẻ trắng viền rõ, Collapsible Sidebar) + Dark Deep Navy Cyan | Light-First + Dark Mode |
| `2.tabler/` | **Tabler Enterprise Admin** | Chuẩn Bootstrap 5 / Tabler, font Inter, viền 1px sắc nét, KPI sparkline, Data Table & Dark Sidebar | Light + Dark Mode |
| `3.midnight/` | **Midnight Pro (Aave-Inspired)** | Dark-first obsidian (`#09090d`), border bo tròn mềm (`20px–24px` & full-pill), font geometric, emoji icon & Bento Explore Table | Dark-First + Light Mode |
| `4.apple/` | **Apple Minimalist & Storefront** | Tinh khiết chuẩn Apple.com (`#ffffff` / `#f5f5f7`, Apple Blue `#0071e3`, tiêu đề 2 tông màu, Sticky Split Configurator, thẻ chọn viền `2px` & nút Full-Pill) | Light-First + Dark OLED |

---

## 3. Cơ Chế Cài Đặt 1 Lệnh, Ignore 2 Lớp & Cập Nhật `/update-speedy`

- **Cài đặt 1 lệnh**: `curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash` (ưu tiên tag `speedy-vX.Y.Z`, fallback nhánh `main`).
- **Ignore 2 lớp an toàn cho cả Git lẫn Antigravity**:
  - `.gitignore`: chỉ ghi `/.speedy/` và `/ai-workspace/`.
  - `.git/info/exclude`: ghi `/.agents/` và `/AGENTS.md` để Git không push nhầm nhưng Antigravity vẫn quét đầy đủ slash commands.
- **Zero-Config `/update-speedy`**: Lưu nguồn vào `.speedy/config/source.local.json` (nằm ngoài `manifest.json`), hỗ trợ backup & rollback nguyên trạng 1 lệnh.
