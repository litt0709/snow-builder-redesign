# `/cleanup` — Dọn Dẹp An Toàn Artifact Cũ

## Mô tả
Quét và dọn dẹp các thư mục phiên đã kết thúc (`completed` / `aborted`) quá hạn lưu trữ cùng dữ liệu tạm trong `ai-workspace/tmp/`, bảo vệ tuyệt đối phiên đang chạy.

## Lệnh thực thi
```bash
# Bước 1: Luôn chạy dry-run trước (mặc định không xóa file)
python3 .speedy/scripts/speedy_cli.py cleanup [--older-than 30] [--include-plans] [--include-logs] [--include-reports] [--include-audit]

# Bước 2: Chỉ sau khi người dùng xác nhận mới thêm --apply
python3 .speedy/scripts/speedy_cli.py cleanup [--older-than 30] [...] --apply
```

## Scope & Gate Bắt Buộc
- **Không bao giờ xóa**:
  - Các session đang ở trạng thái `in_progress`, `awaiting_approval`, `running` hoặc `blocked`.
  - Thư mục `ai-workspace/state/` và `ai-workspace/docs/`.
  - Dữ liệu `ai-workspace/audit/` trừ khi người dùng bật rõ `--include-audit` và duyệt danh sách dry-run.
- **HITL Gate**: Bắt buộc hiển thị kết quả dry-run và gọi `ask_question` xác nhận trước khi chạy `--apply`.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Nếu file `state.json` của một session bị hỏng không xác định được trạng thái hoàn tất, tự động xếp vào diện bảo vệ (`protected_active_sessions`), không xóa mù quáng.
- **Audit**: Ghi nhận qua `.speedy/commands/audit-lifecycle.md` khi thực hiện xóa thật (`--apply`).
