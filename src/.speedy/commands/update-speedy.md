# `/update-speedy` (`speedy-update`) — Cập Nhật Engine Speedy An Toàn

## Mô tả
Kiểm tra phiên bản mới, tải/nạp gói vào vùng staging, đối chiếu **Ownership Manifest** (`.speedy/manifest.json`), tạo bản sao lưu khôi phục (rollback) và cập nhật các file kit-owned mà **bảo toàn 100% `ai-workspace/`**.

## Quy Tắc An Toàn Bắt Buộc
1. **Nguồn cập nhật tường minh**: Lấy từ biến môi trường `SPEEDY_SOURCE_URL`, tham số `--source` hoặc khóa `source_url` trong `.speedy/config/source.json`. **Tuyệt đối không** mặc định lấy `git remote origin` của dự án ứng dụng. Nếu chưa cấu hình nguồn từ xa và không truyền đường dẫn gói cục bộ → dừng và hướng dẫn cấu hình.
2. **Bảo toàn Runtime & Tùy chỉnh**:
   - Không bao giờ sửa hoặc xóa `ai-workspace/` hay các file `.env` bí mật của dự án.
   - Nếu người dùng đã chỉnh sửa `AGENTS.md` hoặc một file kit-owned (khác SHA-256 gốc trong `manifest.json`), dừng báo xung đột và hỏi qua `ask_question` trước khi ghi đè.
3. **Staging, Backup & Rollback**:
   - Xác thực `VERSION` và `manifest.json` tại vùng staging trước khi áp dụng.
   - Tự động lưu bản backup trước khi cập nhật để khôi phục nguyên trạng nếu xảy ra lỗi giữa chừng.

## Quy Trình Thực Hiện
1. Đọc `.speedy/VERSION` hiện tại và xác định nguồn gói mới (local directory hoặc tag `speedy-vX.Y.Z` từ `source_url`).
2. Chạy kiểm tra dry-run liệt kê danh sách file sẽ thêm mới, cập nhật, xóa bỏ (theo manifest cũ/mới) và file bị xung đột tùy chỉnh.
3. Gọi `ask_question` trình bày bản đối chiếu phiên bản để người dùng xác nhận `Approve / Abort`.
4. Tạo backup tại `ai-workspace/tmp/backups/speedy-backup-<timestamp>/`, áp dụng cập nhật và xác minh lại bằng `python3 .speedy/scripts/speedy_cli.py catalog --no-cache`.
