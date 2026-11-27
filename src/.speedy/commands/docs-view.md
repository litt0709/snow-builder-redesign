# `/docs-view` (`speedy-docs-view`) — Kết Xuất Trình Đọc Tài Liệu HTML

## Mô tả
Kết xuất toàn bộ tài liệu Markdown bên trong `ai-workspace/docs/` thành một trang HTML độc lập, hoạt động offline kèm cây mục lục phân cấp.

## Lệnh thực thi
```bash
python3 .speedy/scripts/speedy_cli.py docs-view [--docs-dir ai-workspace/docs] [--output ai-workspace/docs/index.html] --no-open
```

## Input & Output
- **Input**: Các file `*.md` trong `ai-workspace/docs/`.
- **Output**: File HTML tại `ai-workspace/docs/index.html` và 1 JSON trên stdout chứa `status` (`created` | `updated` | `unchanged`), `path`, `relative_path`, `uri`, `files_rendered`.

## Scope, Hành vi khi lỗi & Miễn trừ Audit
- **Scope**: Chỉ đọc `ai-workspace/docs/` và ghi file HTML đích; escape toàn bộ thẻ HTML không an toàn và chặn URL `javascript:`.
- **Browser behavior**: Mặc định chạy với `--no-open` để an toàn trên môi trường agent/CI; chỉ truyền `--open` khi người dùng yêu cầu mở trình duyệt. Luôn gửi kèm link tới file HTML trong phản hồi chat.
- **Failure behavior**: Trả exit code != 0 kèm thông báo JSON trên stderr nếu thư mục docs không tồn tại hoặc vượt khỏi workspace.
- **Audit**: Thuần hiển thị nên miễn trừ tạo phiên audit mới.
