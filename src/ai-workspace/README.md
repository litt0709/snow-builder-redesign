# Speedy AI Workspace

Thư mục `ai-workspace/` là **bộ nhớ vận hành cục bộ** của Speedy DevKit trong dự án ứng dụng của bạn. Khi nâng cấp Speedy (`/update-speedy` hoặc `install.py`), toàn bộ dữ liệu trong thư mục này luôn được bảo toàn nguyên vẹn.

---

## Cấu trúc Thư mục

| Thư mục / File | Mục đích |
|---|---|
| `.env` *(tạo từ `.env.example`)* | Bật/tắt thu thập audit (`IS_AUDIT=1`), chọn `SPEEDY_GATE_POLICY` (`strict` / `balanced`), cấu hình `SPEEDY_SOURCE_URL`. |
| `docs/` | Knowledge dự án ứng dụng (`architecture/`, `guides/`, `reference/`, `development-rules/`, `development-style/`, `cross-repo/`). |
| `specs/` | Tài liệu đặc tả thiết kế chuẩn hóa cho Người & LLM, tạo và cập nhật lặp lại qua `/specs`. |
| `plans/` | Các bản kế hoạch triển khai theo ngày (`YYYY-MM-DD-<slug>.md`). |
| `sessions/<sid>/` | Trạng thái canonical (`state.json`, `state.md`) và các file Handoff Contract từng bước. |
| `state/` | Chỉ mục cache có kiểm soát (`repomap.json`, `scan_cache.json`, `setup.json`, `issues.json`). |
| `audit/` | Dữ liệu audit 4 lớp cho từng phiên thực thi. |
| `logs/` & `reports/` | Báo cáo tổng kết task và dashboard HTML kết xuất từ `/audit-view`. |
| `tmp/` | Vùng lưu trữ tạm thời và cache khi chạy test/script, có thể dọn sạch an toàn bằng `/cleanup`. |
