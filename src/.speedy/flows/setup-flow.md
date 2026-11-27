# Setup Flow — Khởi Tạo Baseline Cho Dự Án Hiện Hữu

Chỉ chạy một lần khi phát hiện dự án đã có mã nguồn ứng dụng nhưng chưa khởi tạo `ai-workspace/state/setup.json`.

---

## Bước S1 — Đề xuất cấu hình `.gitignore` & Xin xác nhận

1. Kiểm tra `.gitignore` tại gốc dự án: chỉ đề xuất thêm phần ignore riêng cho vùng thuộc DevKit nếu người dùng không muốn commit DevKit chung vào repo ứng dụng (`.speedy/`, `ai-workspace/`, `.agents/`, `AGENTS.md`) — **tuyệt đối không xóa hay sửa các dòng `.gitignore` có sẵn của ứng dụng**.
2. Gọi `ask_question` hỏi người dùng:
   - `(Recommended) Chạy Setup — Quét cấu trúc dự án và sinh tài liệu nền vào ai-workspace/docs/`
   - `Bỏ qua Setup — Ghi trạng thái skipped và đi thẳng vào task hiện tại`
3. Nếu người dùng chọn Bỏ qua: ghi `{"status": "skipped"}` vào `ai-workspace/state/setup.json` và quay lại luồng chính.

---

## Bước S2 — Quét Codebase & Xây Chỉ Mục RepoMap (Deterministic)

```bash
python3 .speedy/scripts/speedy_cli.py scan . --sid <sid>
python3 .speedy/scripts/speedy_cli.py repomap build
```

Dùng kết quả JSON (`lang`, `framework`, `entry_points`, `detected_tooling`) làm dữ kiện thực tế — không tự suy đoán cấu hình không tồn tại.

---

## Bước S3 — Biên Soạn Tài Liệu Nền & Quy Ước Dự Án

1. Đọc `.speedy/roles/writer.md` (khuyến nghị **Gemini Hydrogen**): lập Topic Map 2 cấp cho các module ứng dụng (loại trừ hoàn toàn `.speedy/`, `.agents/`, `ai-workspace/`), tạo `ai-workspace/docs/architecture/overview.md`, các file chi tiết module và `ai-workspace/docs/CHANGELOG.md`.
2. Đọc `.speedy/commands/refresh-rule.md` và thực thi để tạo quy ước thực tế tại `ai-workspace/docs/development-rules/`.
3. Đọc `.speedy/commands/refresh-style.md` và thực thi để tạo `ai-workspace/docs/development-style/STYLE.md`.

---

## Bước S4 — Đánh Dấu Hoàn Tất Setup

Ghi `ai-workspace/state/setup.json`:
```json
{
  "status": "done",
  "updated_at": "YYYY-MM-DD",
  "overview_path": "ai-workspace/docs/architecture/overview.md"
}
```
Hiển thị link tới `overview.md` và chuyển tiếp vào luồng chính của người dùng.
