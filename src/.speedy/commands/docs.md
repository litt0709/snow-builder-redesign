# `/docs` — Biên Soạn Knowledge Base Gọn Nhẹ & Cross-Repo

## Mô tả
Kích hoạt vai trò Writer (`Gemini Hydrogen`) để quét cấu trúc module runtime (qua `repomap build`), lập **Topic Map** và biên soạn bộ tài liệu chuẩn hóa 4 trụ cột vào `ai-workspace/docs/` (hoặc ghi tóm tắt liên dự án với cú pháp `/docs cross-repo <repo-id> "<mô tả>"`), sau đó chạy `knowledge index` để đồng bộ Master Map `INDEX.md` và Harness Index `repomap.json`.

## Input & Output
- **Input**: Chủ đề tài liệu cần tạo/cập nhật hoặc thông tin repo liên kết.
- **Output**:
  - Chế độ thường:
    - `ai-workspace/docs/architecture/architecture.md` (System Blueprint: Tech Stack, Mermaid, Schema, API, ADR)
    - `ai-workspace/docs/architecture/<domain>.md` (Domain Cards <= 150 dòng/file, kèm `tags:` và `source_ref | sha256`)
    - `ai-workspace/docs/guides/quickstart.md` & `ai-workspace/docs/CHANGELOG.md`
    - `ai-workspace/docs/INDEX.md` (tự sinh bằng `python3 -B .speedy/scripts/speedy_cli.py knowledge index`)
  - Chế độ `cross-repo`: `ai-workspace/docs/cross-repo/<repo-id>/<topic-id>.md` và cập nhật `ai-workspace/docs/cross-repo/registry.json` qua `speedy_cli.py knowledge register-cross-repo`.

## Scope & Gate
- **Scope**: **Chỉ ghi vào `ai-workspace/docs/`** (không bao giờ ghi vào `docs/` ở root dự án ứng dụng). Bỏ qua hoàn toàn `.speedy/`, `.agents/` và `ai-workspace/` khi lập Topic Map; không mô tả cơ chế nội bộ của Speedy DevKit trong tài liệu ứng dụng.
- **Completion Gate**: Mọi module trong Topic Map bắt buộc có file chi tiết thực tế và đã chạy `python3 -B .speedy/scripts/speedy_cli.py knowledge index` để cập nhật `INDEX.md` + `repomap.json`.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Nếu người dùng yêu cầu viết tài liệu cho thành phần nội bộ DevKit hoặc repo ngoài chưa cấp quyền đọc, từ chối rõ ràng và nêu lý do vi phạm ranh giới.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /docs`.
