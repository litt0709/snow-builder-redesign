# Bản Đồ Sản Phẩm Speedy DevKit (`src/`)

> Tài liệu ánh xạ toàn bộ thành phần nằm trong `src/` — gói sản phẩm độc lập được xuất và cài đặt vào dự án ứng dụng trên **Antigravity IDE**.

---

## 1. Phân Vùng Trách Nhiệm Trong `src/`

| Đường dẫn trong `src/` | Thuộc quyền sở hữu | Vai trò khi cài sang dự án ứng dụng |
|---|---|---|
| `AGENTS.md` | Kit-owned (hỏi trước khi ghi đè nếu user đã sửa) | Entry-point định tuyến ngắn gọn và quy tắc chọn model Gemini |
| `.agents/rules/` | Kit-owned | Rule `always_on` cực gọn và rule `model_decision` / `glob` cho Antigravity IDE |
| `.agents/skills/` | Kit-owned | 9 skill lệnh chính (`speedy-flow`, `speedy-analyst`, `speedy-docs`, `speedy-docs-view`, `speedy-audit-view`, `speedy-refresh-rule`, `speedy-refresh-style`, `speedy-cleanup`, `speedy-update`) + `speedy-repomap` |
| `.speedy/VERSION`, `.speedy/manifest.json` | Kit-owned | Phiên bản semver và danh mục SHA-256 kiểm soát xung đột cài đặt/cập nhật |
| `.speedy/roles/` | Kit-owned | SSOT hợp đồng 8 vai trò (`orchestrator`, `analyst`, `architect`, `implementer`, `reviewer`, `tester`, `docs-manager`, `writer`) |
| `.speedy/flows/` | Kit-owned | Quy trình 5 chế độ (`setup`, `feature`, `fix`, `simple`, `verify`) |
| `.speedy/commands/` | Kit-owned | Đặc tả chi tiết 9 lệnh người dùng và template HITL/Audit |
| `.speedy/rules/` | Kit-owned | Bộ nguyên tắc vận hành nội bộ của Speedy (`1.principle.md` → `5.testing.md`) |
| `.speedy/schemas/` & `.speedy/config/` | Kit-owned | JSON Schema hợp đồng, cấu hình phân tầng Gemini (`Hydrogen` / `Neon` / `Carbon`) và ngân sách thực thi |
| `.speedy/scripts/` | Kit-owned | Lõi Python CLI deterministic (`speedy_cli.py` và các module chuyên trách) |
| `ai-workspace/` | **User Runtime (Preserved 100%)** | Nơi lưu `docs/`, `plans/`, `sessions/`, `state/`, `audit/`, `reports/` của dự án ứng dụng — **không bao giờ bị xóa/ghi đè khi update Speedy** |
