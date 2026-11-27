# `/audit-view` — Kết Xuất Bảng Điều Khiển Audit Tháng

## Mô tả
Tổng hợp các bản ghi Audit 4 lớp trong `ai-workspace/audit/` thành báo cáo HTML độc lập theo tháng (`YYYY-MM`).

## Lệnh thực thi
```bash
python3 .speedy/scripts/speedy_cli.py audit-view [--month YYYY-MM] [--audit-dir ai-workspace/audit] --no-open
```

## Input & Output
- **Input**: Các thư mục phiên chạy trong `ai-workspace/audit/`.
- **Output**: File HTML tại `ai-workspace/reports/audit-view/<YYYY-MM>.html` và JSON stdout gồm `status` (`created` | `updated` | `unchanged`), `status_reason` (`ok` | `audit_disabled` | `no_audit_data` | `no_tasks_for_month`), `tasks`, `path`, `uri`.

## Scope, Hành vi khi lỗi & Miễn trừ Audit
- **Scope**: Chỉ đọc JSON trong `ai-workspace/audit/` và ghi báo cáo vào `ai-workspace/reports/audit-view/`.
- **Trung thực dữ liệu**: Giữ nguyên `null` / `not_measured` cho mọi chỉ số thiếu nguồn đo; tách bạch thời gian `wall`, `human_wait` và `tool`.
- **Failure behavior**: Báo lỗi exit code != 0 nếu tham số `--month` sai định dạng `YYYY-MM`.
- **Audit**: Thuần hiển thị nên miễn trừ tạo phiên audit mới.
