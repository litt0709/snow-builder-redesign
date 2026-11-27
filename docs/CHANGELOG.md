# Changelog — SNOW Builder & Speedy DevKit

Mọi thay đổi quan trọng của SNOW Builder và gói sản phẩm Speedy DevKit tuân thủ chuẩn Semantic Versioning (`MAJOR.MINOR.PATCH`).

## [2.0.0] — 2026-11-27

### Phát hành Kiến trúc Tái thiết kế Hoàn chỉnh (Antigravity Edition)
- **SNOW Builder & Speedy Boundary**: Thiết lập kiến trúc hai lớp độc lập hoàn toàn, tích hợp gốc 100% cho **Antigravity IDE** (`.agents/rules` + `.agents/skills`).
- **Deterministic CLI Harness (`speedy_cli.py`)**: 20 module Python 3.11+ stdlib-only (0 dependency ngoài) quản lý Canonical JSON State Machine (`session.lock` + `state_revision` CAS), Semantic Checksum, Selective Invalidation, Deep Handoff Validator, Context Packet & Compaction.
- **Chiến lược Phân tầng Model Gemini Pro**: Định tuyến tự động theo độ phức tạp và rủi ro (`Gemini Hydrogen` cho điều phối/tài liệu → `Gemini Neon` mặc định chủ lực → `Gemini Carbon` giới hạn nghiêm ngặt cho bài toán phức tạp cao).
- **Adversarial Verification & Honest Audit**: Tích hợp Reviewer độc lập qua `invoke_subagent`, bộ phát hiện **Test Laundering**, Audit 4 lớp trung thực (`null`/`not_measured` khi thiếu nguồn đo), HTML viewers offline (`docs-view`, `audit-view`) và Benchmark Suite (`dev` + `held_out` + paired comparison).
- **Safe Ownership Manifest Installer (`manifest.json`)**: Hỗ trợ `package.py`, `install.py` và `speedy_cli.py update` có staging, phát hiện xung đột tùy chỉnh, bảo toàn 100% `ai-workspace/` và rollback 1 lệnh.
