# Changelog — SNOW Builder & Speedy DevKit

Mọi thay đổi quan trọng của SNOW Builder và gói sản phẩm Speedy DevKit tuân thủ chuẩn Semantic Versioning (`MAJOR.MINOR.PATCH`).

## [Unreleased] — 2026-11-27

### Cải Tiến Cài Đặt 1 Lệnh Từ Git, Auto `.gitignore` & Zero-Config `/update-speedy`
- **Remote 1-Command Installer (`scripts/install.sh`)**: Hỗ trợ cài Speedy bằng 1 lệnh `curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash` tại thư mục gốc bất kỳ dự án nào, ưu tiên tag `speedy-vX.Y.Z` cao nhất và tự động fallback nhánh mặc định (`main`) nếu chưa gắn tag.
- **Auto `.gitignore` & Rollback sạch**: Tự tạo mới `.gitignore` (nếu chưa có) hoặc nối idempotent block `/.agents/`, `/.speedy/`, `/ai-workspace/`, `/AGENTS.md` để không đẩy nhầm Speedy lên repo dự án đích; hỗ trợ rollback nguyên trạng.
- **Zero-Config `/update-speedy`**: Tự lưu nguồn cài đặt vào `.speedy/config/source.local.json` (nằm ngoài `manifest.json`), đổi tên skill thành `update-speedy` để `/update-speedy` khớp trực tiếp trên Antigravity IDE, hỗ trợ branch fallback + chuyển mượt sang tag release, và chặn argument injection trong các lệnh `git`.
- **Slash Commands Ngắn Gọn & Tương Thích Dual-Surface (App / CLI / IDE Standalone)**:
  - Bỏ tiền tố `speedy-` trên toàn bộ 10 lệnh Speedy (`/flow`, `/specs`, `/analyst`, `/docs`, `/docs-view`, `/audit-view`, `/refresh-rule`, `/refresh-style`, `/cleanup`, `/repomap`, giữ `/update-speedy`).
  - Bổ sung thin workflow wrappers tại `.agents/workflows/` cho cả SNOW Builder (10 lệnh `/builder-*`) và Speedy DevKit (11 lệnh) kèm chuẩn hóa YAML frontmatter single-line để menu slash command `/` hoạt động ngay trên **Antigravity IDE standalone** lẫn **Antigravity App 2.0 / CLI**.

## [2.0.0] — 2026-11-27

### Phát hành Kiến trúc Tái thiết kế Hoàn chỉnh (Antigravity Edition)
- **SNOW Builder & Speedy Boundary**: Thiết lập kiến trúc hai lớp độc lập hoàn toàn, tích hợp gốc 100% cho **Antigravity IDE** (`.agents/rules` + `.agents/skills`).
- **Deterministic CLI Harness (`speedy_cli.py`)**: 20 module Python 3.11+ stdlib-only (0 dependency ngoài) quản lý Canonical JSON State Machine (`session.lock` + `state_revision` CAS), Semantic Checksum, Selective Invalidation, Deep Handoff Validator, Context Packet & Compaction.
- **Chiến lược Phân tầng Model Gemini Pro**: Định tuyến tự động theo độ phức tạp và rủi ro (`Gemini Hydrogen` cho điều phối/tài liệu → `Gemini Neon` mặc định chủ lực → `Gemini Carbon` giới hạn nghiêm ngặt cho bài toán phức tạp cao).
- **Adversarial Verification & Honest Audit**: Tích hợp Reviewer độc lập qua `invoke_subagent`, bộ phát hiện **Test Laundering**, Audit 4 lớp trung thực (`null`/`not_measured` khi thiếu nguồn đo), HTML viewers offline (`docs-view`, `audit-view`) và Benchmark Suite (`dev` + `held_out` + paired comparison).
- **Safe Ownership Manifest Installer (`manifest.json`)**: Hỗ trợ `package.py`, `install.py` và `speedy_cli.py update` có staging, phát hiện xung đột tùy chỉnh, bảo toàn 100% `ai-workspace/` và rollback 1 lệnh.
