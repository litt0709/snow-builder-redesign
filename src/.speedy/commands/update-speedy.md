# `/update-speedy` — Cập Nhật Engine Speedy An Toàn

## Mô tả
Kiểm tra phiên bản/commit mới nhất từ nguồn đã lưu lúc cài đặt, tải gói vào vùng staging, đối chiếu **Ownership Manifest** (`.speedy/manifest.json`), tự động tạo bản sao lưu khôi phục (rollback), đồng bộ `.gitignore` và cập nhật các file kit-owned mà **bảo toàn 100% `ai-workspace/`**.

## Quy Tắc An Toàn Bắt Buộc
1. **Nguồn cập nhật tường minh**: Tự động phân giải theo thứ tự ưu tiên `--source` → biến môi trường `SPEEDY_SOURCE_URL` → `ai-workspace/.env` → `.speedy/config/source.local.json` (tự ghi lúc cài bằng 1 lệnh) → `.speedy/config/source.json`. **Tuyệt đối không** mặc định lấy `git remote origin` của dự án ứng dụng.
2. **Ưu tiên Tag SemVer, tự fallback nhánh mặc định**: Nếu repo nguồn có tag `speedy-vX.Y.Z`, lấy tag cao nhất theo SemVer; nếu repo chưa có tag nào, tự động đối chiếu commit mới nhất trên nhánh mặc định (hoặc `--ref <branch|tag>`).
3. **Bảo toàn Runtime & Tùy chỉnh**:
   - Không bao giờ sửa hoặc xóa `ai-workspace/` hay các file `.env` bí mật của dự án.
   - Nếu người dùng đã chỉnh sửa `AGENTS.md` hoặc một file kit-owned (khác SHA-256 gốc trong `manifest.json`), dừng báo xung đột và hỏi qua `ask_question` trước khi ghi đè.
4. **Staging, Backup, Auto `.gitignore` & Rollback**:
   - Xác thực `VERSION` và `manifest.json` tại vùng staging trước khi áp dụng.
   - Tự động lưu bản backup tại `ai-workspace/tmp/backups/speedy-backup-<timestamp>/` trước khi ghi và đồng bộ block ignore `/.agents/`, `/.speedy/`, `/ai-workspace/`, `/AGENTS.md` vào `.gitignore` root dự án.

## Quy Trình Thực Hiện
1. Chạy dry-run kiểm tra bản mới và danh sách thay đổi/xung đột:
   ```bash
   python3 .speedy/scripts/speedy_cli.py update
   ```
   Nếu trả về `"status": "UP_TO_DATE"` → báo đã ở bản mới nhất và dừng.
2. Gọi `ask_question` trình bày bản đối chiếu phiên bản/commit và file thay đổi để người dùng xác nhận (`Approve --skip-conflicts` / `Approve --force-overwrite` / `Abort`).
3. Khi được duyệt, áp dụng cập nhật:
   ```bash
   python3 .speedy/scripts/speedy_cli.py update --apply --skip-conflicts
   ```
4. Xác minh lại hệ thống sau khi cập nhật:
   ```bash
   python3 .speedy/scripts/speedy_cli.py catalog --no-cache
   ```
5. Nếu cần khôi phục nguyên trạng về trước khi cập nhật:
   ```bash
   python3 .speedy/scripts/speedy_cli.py update --rollback ai-workspace/tmp/backups/<ten-backup>
   ```
