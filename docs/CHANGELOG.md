# Changelog — SNOW Builder & Speedy DevKit

Mọi thay đổi quan trọng của SNOW Builder và gói sản phẩm Speedy DevKit tuân thủ chuẩn Semantic Versioning (`MAJOR.MINOR.PATCH`).

## [Unreleased] — 2026-11-27

### Cài Đặt 1 Lệnh, Balanced Smart HITL, Web Themes & Tối Ưu Hiệu Năng
- **Remote 1-Command Installer (`scripts/install.sh`)**: Cài đặt Speedy bằng 1 lệnh `curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash` tại thư mục gốc bất kỳ dự án nào (ưu tiên tag `speedy-vX.Y.Z` cao nhất, tự fallback nhánh mặc định `main`, chặn argument injection với `--` và validate prefix `-`).
- **Ignore 2 Lớp An Toàn Cho Git & Antigravity**:
  - `.gitignore` chỉ thêm `/.speedy/` và `/ai-workspace/` để không chặn bộ quét slash commands của Antigravity.
  - `.git/info/exclude` tự động nhận `/.agents/` và `/AGENTS.md` (khi dự án có `.git/`), vừa không push nhầm Speedy lên repo dự án vừa hiển thị đủ lệnh trên IDE; hỗ trợ rollback nguyên trạng và chuẩn hóa quyền file `0644`.
- **Zero-Config `/update-speedy`**: Lưu nguồn cài đặt vào `.speedy/config/source.local.json` (nằm ngoài `manifest.json`), hỗ trợ branch fallback theo commit SHA, kiểm tra toàn vẹn file `kit_owned` và chuyển mượt từ branch sang tag release.
- **Slash Commands Ngắn Gọn & Không Duplicate**: Bỏ tiền tố `speedy-` trên 10 lệnh Speedy (`/flow`, `/specs`, `/analyst`, `/docs`, `/docs-view`, `/audit-view`, `/refresh-rule`, `/refresh-style`, `/cleanup`, `/repomap`, giữ `/update-speedy`); dùng duy nhất `.agents/skills/<name>/SKILL.md` với YAML frontmatter single-line (bỏ legacy `.agents/workflows/` gây trùng lặp).
- **Chế Độ Mặc Định `balanced` (Smart HITL) & `state complete`**: Chuyển `default_profile` sang `balanced` (tự động đi qua stage rủi ro thấp không có câu hỏi mở; tự khóa HITL khi có `Open questions`, `high_risk`, `REQUEST_CHANGES`, xung đột/release; vẫn hỗ trợ `--policy strict`). Bổ sung lệnh gộp `speedy_cli.py state complete` giảm từ 3–4 lệnh CLI xuống 1 lệnh/stage và cập nhật `src/ai-workspace/.env.example`.
- **Khôi Phục Cốt Lõi AI-DD & 11 Anti-Patterns**: Bổ sung đầy đủ 5 Subsystems, 8 Invariants (gồm **Data Consistency & SSOT**, User Primacy, Simple Responses, Clearly Direction), 11 Anti-Patterns cho LLM và Mental Model 3 pha AI-DD vào `src/.speedy/rules/1..5` và `src/AGENTS.md`.
- **Thư Viện 3 Web Themes (`src/.speedy/docs/themes/`)**: Bổ sung **`2.tabler/`** (Tabler Enterprise Admin) và **`3.midnight/`** (Midnight Pro · Aave-Inspired Dark-First) kèm đầy đủ Design Tokens, Layout Templates và ảnh `preview-light.png` / `preview-dark.png`.
- **Tối Ưu Prompt/Context Zero-Drift & CLI Lazy Imports**: Đồng bộ toàn bộ rules/skills/flows sang `balanced` + `state complete`; chuyển 17 module trong `speedy_cli.py` sang lazy import (-54% cold-start latency: `121.8 ms` → `55.5 ms`) và thêm cờ `--compact` tiết kiệm ~25–30% token JSON output.

## [2.0.0] — 2026-11-27

### Phát hành Kiến trúc Tái thiết kế Hoàn chỉnh (Antigravity Edition)
- **SNOW Builder & Speedy Boundary**: Thiết lập kiến trúc hai lớp độc lập hoàn toàn, tích hợp gốc 100% cho **Antigravity IDE** (`.agents/rules` + `.agents/skills`).
- **Deterministic CLI Harness (`speedy_cli.py`)**: 20 module Python 3.11+ stdlib-only (0 dependency ngoài) quản lý Canonical JSON State Machine (`session.lock` + `state_revision` CAS), Semantic Checksum, Selective Invalidation, Deep Handoff Validator, Context Packet & Compaction.
- **Chiến lược Phân tầng Model Gemini Pro**: Định tuyến tự động theo độ phức tạp và rủi ro (`Gemini Hydrogen` cho điều phối/tài liệu → `Gemini Neon` mặc định chủ lực → `Gemini Carbon` giới hạn nghiêm ngặt cho bài toán phức tạp cao).
- **Adversarial Verification & Honest Audit**: Tích hợp Reviewer độc lập qua `invoke_subagent`, bộ phát hiện **Test Laundering**, Audit 4 lớp trung thực (`null`/`not_measured` khi thiếu nguồn đo), HTML viewers offline (`docs-view`, `audit-view`) và Benchmark Suite (`dev` + `held_out` + paired comparison).
- **Safe Ownership Manifest Installer (`manifest.json`)**: Hỗ trợ `package.py`, `install.py` và `speedy_cli.py update` có staging, phát hiện xung đột tùy chỉnh, bảo toàn 100% `ai-workspace/` và rollback 1 lệnh.
