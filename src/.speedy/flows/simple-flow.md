# Simple Flow — Luồng Nhanh Cho Thay Đổi Nhỏ An Toàn

Áp dụng khi `FLOW_MODE = simple`.

---

## Điều Kiện Tiên Quyết Bắt Buộc (Preconditions)

Tất cả điều kiện sau phải đúng đồng thời:
1. Chỉ chỉnh sửa **1 file** văn bản hoặc cấu hình tĩnh (`.md`, `.txt`, `.json`, `.toml`, `.yaml`, `.properties`).
2. Không thay đổi hành vi runtime, API contract, database schema, dependency hoặc các vùng nhạy cảm (`auth`, `payment`, `security`).

> Nếu bất kỳ điều kiện nào không thỏa mãn, dừng luồng `simple` ngay lập tức và chuyển sang `.speedy/flows/feature-flow.md`.

---

## Bước S1 — Xác Nhận Phạm Vi Với Người Dùng

1. Nêu ngắn gọn tên file duy nhất sẽ sửa và nội dung thay đổi dự kiến.
2. Gọi `ask_question` để người dùng chọn `Approve` / `Abort` trước khi sửa file.

---

## Bước S2 — Implementer & Kiểm Tra Phù Hợp (`Gemini Neon`)

1. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage implementer --status running`.
2. Đọc `.speedy/roles/implementer.md`, thực hiện thay đổi trên đúng 1 file đã duyệt (không chạm sang file thứ hai).
3. Nếu là file cấu hình `.json`/`.toml`, chạy kiểm tra cú pháp tương ứng qua `speedy_cli.py verify run --sid <sid>`.
4. Ghi `ai-workspace/sessions/<sid>/handoff-3-implementer.md`, chuyển `awaiting_approval`, gửi link file và xác nhận tại cổng `ask_question` → `speedy_cli.py gate approve --sid <sid> --stage implementer --actor human --interaction-ref <ref>`.

---

## Bước S3 — Wrap-up (`Gemini Hydrogen`)

Chạy `state transition --sid <sid> --stage wrapup --status running` → `approved`, ghi tóm tắt vào `ai-workspace/logs/tasks/`, finalize audit và hiển thị bảng kết quả ngắn gọn.
