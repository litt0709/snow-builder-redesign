# `/docs` (`speedy-docs`) — Biên Soạn Tài Liệu Kỹ Thuật & Cross-Repo

## Mô tả
Kích hoạt vai trò Writer (`Gemini Hydrogen`) để quét 2 cấp module runtime, lập **Topic Map** và biên soạn bộ tài liệu phân mảnh vào `ai-workspace/docs/` (hoặc ghi tóm tắt liên dự án với cú pháp `/docs cross-repo <repo-id> "<mô tả>"`).

## Input & Output
- **Input**: Chủ đề tài liệu cần tạo/cập nhật hoặc thông tin repo liên kết.
- **Output**:
  - Chế độ thường: `ai-workspace/docs/architecture/overview.md` (index nhẹ), các file chi tiết từng module có gắn `source_ref | sha256`, và `ai-workspace/docs/CHANGELOG.md`.
  - Chế độ `cross-repo`: `ai-workspace/docs/cross-repo/<repo-id>/<topic-id>.md` và cập nhật `ai-workspace/docs/cross-repo/registry.json` qua `speedy_cli.py knowledge register-cross-repo`.

## Scope & Gate
- **Scope**: **Chỉ ghi vào `ai-workspace/docs/`** (không bao giờ ghi vào `docs/` ở root dự án ứng dụng). Bỏ qua hoàn toàn `.speedy/`, `.agents/` và `ai-workspace/` khi lập Topic Map; không mô tả cơ chế nội bộ của Speedy DevKit trong tài liệu ứng dụng.
- **Completion Gate**: Mọi module trong Topic Map bắt buộc có file chi tiết thực tế được dẫn link từ `overview.md`.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Nếu người dùng yêu cầu viết tài liệu cho thành phần nội bộ DevKit hoặc repo ngoài chưa cấp quyền đọc, từ chối rõ ràng và nêu lý do vi phạm ranh giới.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` với `--command-ref /docs`.
