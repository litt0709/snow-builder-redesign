# Kế hoạch Tổng thể: Tái xây dựng SNOW Builder & Speedy DevKit (v2.0 — Antigravity Edition)

- **Ngày lập**: `2026-11-27`
- **Session khởi tạo**: `2026-11-27-speedy-redesign-b0` (cập nhật Revision 2 theo phản hồi tại Gate Bước 1)
- **Chế độ quản trị**: `strict` (Correctness-first; duyệt từng stage; không tự approve thay con người)
- **Baseline kỹ thuật**: Python 3.11+ stdlib-only (môi trường hiện tại: Python `3.14.7`, Git `2.50.1`, macOS `arm64`)
- **IDE mục tiêu duy nhất**: **Antigravity IDE / Antigravity 2.0** (`.agents/rules/` + `.agents/skills/`; loại bỏ hoàn toàn `.github/` Copilot, `.vscode/` và các lệnh `commit-push`, `create-pr`).

---

## 1. Chiến lược Phân tầng Model Gemini & Tối ưu Token ("WOW" cho User)

### 1.1. Chính sách định tuyến Model (Gemini Pro Support)

| Tầng ưu tiên | Model | Vai trò mặc định | Quy tắc vận hành & Bảo vệ Quota |
|---|---|---|---|
| **Tầng 1 — Tác vụ nhẹ / Điều phối** | `Gemini Hydrogen` | `orchestrator` (`builder-flow`), `docs-manager`, `writer` | Ưu tiên sử dụng cho routing, tổng hợp handoff, đồng bộ changelog và viết tài liệu để tiết kiệm quota tối đa. |
| **Tầng 2 — Tác vụ bình thường (Mặc định)** | `Gemini Neon` | `analyst`, `implementer`, `tester` (`builder-qa`, `builder-autotest`, `builder-release`), cùng `architect`/`reviewer` ở mức độ thông thường | Model chủ lực cân bằng tốc độ, độ chính xác và chi phí cho đại đa số công việc hàng ngày. |
| **Tầng 3 — Độ phức tạp cao (Giới hạn nghiêm ngặt)** | `Gemini Carbon` | Chỉ nâng cấp cho `architect` hoặc `reviewer` khi gặp bài toán kiến trúc hóc búa hoặc thay đổi rủi ro cao (`auth`, `schema`, `security`, `core`) | **Hạn chế tối đa** vì rất nhanh hết limit; bắt buộc có tín hiệu rủi ro/phức tạp cao mới đề xuất sử dụng. |

### 1.2. Kiến trúc Đột phá kết hợp SOTA & Antigravity Native

| Trụ cột | Giải pháp Kiến trúc v2.0 | Giá trị mang lại |
|---|---|---|
| **3-Tier Progressive Disclosure** | • **Tier 0 (`always_on` < 400 tokens)**: `AGENTS.md` + `.agents/rules/00-core-invariants.md` cực ngắn.<br>• **Tier 1 (Skills `.agents/skills/*/SKILL.md`)**: chỉ nạp `name + description` cho đến khi kích hoạt.<br>• **Tier 2 (`context prepare` CLI)**: xuất **Context Packet** (~1–2 KB) chỉ chứa con trỏ `AC`, `ADR`, `repomap` top-5 và `failure_evidence`. | Giảm **60–80% context rác** mỗi turn; tối ưu Prompt Prefix Caching trên Antigravity. |
| **Deterministic FSM & CAS State** | Canonical `state.json` (ghi atomic + `session.lock` + `state_revision` CAS + **Semantic Checksum** tách khỏi tiến độ vận hành) + **Deep Handoff Validator**. | Chuyển stage chính xác 100%, resume mượt sau gián đoạn, không mất approval cũ khi cập nhật trạng thái. |
| **Adversarial Review & Chống Test Laundering** | Dùng `invoke_subagent` gọi Reviewer với context độc lập trên Antigravity + bộ quét diff phát hiện xóa assertion / thêm `skip` trái phép trong `verify`. | Chặn triệt để *Self-Grading Loop* và *Premature Victory*. |
| **Ownership Manifest Installer** | `manifest.json` lưu SHA-256 từng file kit-owned, cài đặt/cập nhật có dry-run, backup & rollback, bảo toàn 100% `ai-workspace/`. | Triển khai và nâng cấp Speedy vào mọi dự án trong vài giây mà không ảnh hưởng cấu hình riêng của user. |

---

## 2. Cấu trúc Lõi Kỹ thuật (`src/.speedy/`)

```text
src/.speedy/
├── VERSION                          # Semver (2.0.0)
├── manifest.json                    # Ownership manifest + SHA-256 của file kit-owned
├── config/
│   ├── policy.default.json          # strict / balanced + finite budgets + Gemini model_routing
│   ├── model-pricing.json           # Cấu hình Gemini Hydrogen / Neon / Carbon & quota notes
│   ├── source.json                  # Cấu hình nguồn update (không hardcode repo nội bộ)
│   └── antigravity-hooks.example.json # Mẫu PreToolUse hook opt-in cho Antigravity
├── schemas/                         # JSON Schemas cho state, handoff, context-packet, audit
├── roles/                           # SSOT 8 Role Contracts
├── flows/                           # 5 luồng: setup, feature, fix, simple, verify
├── commands/                        # 9 lệnh người dùng cốt lõi + hitl/audit/repomap
├── rules/                           # Bộ nguyên tắc vận hành Speedy (1..5)
└── scripts/                         # Lõi Python 3.11+ stdlib (dùng chung cho cả Product & Builder)
    ├── speedy_cli.py                # CLI entry point (JSON stdout, diagnostic stderr)
    ├── contracts.py                 # Enums, dataclasses, path containment guard
    ├── policy.py                    # Risk-aware intent, gate policy, model tier, budget, doom-loop
    ├── storage.py                   # Atomic JSON, session lock, state_revision CAS, semantic hash
    ├── lifecycle.py                 # Session create/resume, FSM transition, gate, UoW scheduler
    ├── handoff.py                   # Deep validator (5 headings + resume metadata + scope/placeholder)
    ├── scaffold.py                  # Template generator sạch cho plan/handoff/ADR/report
    ├── scan.py                      # Inventory codebase + tooling/test runner detection
    ├── repomap.py                   # Module-level WHERE index + top-N ranked query
    ├── context.py                   # Retrieval ladder, freshness check, Context Packet builder
    ├── catalog.py                   # Compact index của roles/flows/commands/rules
    ├── verification.py              # Impact test plan, runner, bounded output, test-laundering check
    ├── benchmark.py                 # Local eval runner (dev vs held-out, paired comparison)
    ├── adapters.py                  # Antigravity capability & telemetry mapping
    ├── audit.py                     # 4-layer honest audit + secret masking
    ├── audit_viewer.py              # Standalone monthly HTML dashboard
    ├── docs_viewer.py               # Standalone responsive HTML docs reader
    ├── cleanup.py                   # Safe dry-run & selective retention cleanup
    └── hook_guard.py                # Opt-in Antigravity PreToolUse safety guard
```

---

## 3. Bộ Lệnh Người Dùng Chuẩn (9 Commands / Skills trên Antigravity)

Đã lược bỏ `commit-push` và `create-pr` theo yêu cầu tinh gọn:
1. `speedy-flow` (`/flow`): Điều phối tự động `feature` / `fix` / `simple` / `verify`.
2. `speedy-analyst` (`/analyst`): Phân tích yêu cầu & xuất Implementation Brief độc lập.
3. `speedy-docs` (`/docs`): Lập Topic Map 2 cấp & viết tài liệu ứng dụng / cross-repo.
4. `speedy-docs-view` (`/docs-view`): Render bộ tài liệu `ai-workspace/docs/` ra HTML offline.
5. `speedy-audit-view` (`/audit-view`): Render dashboard hiệu quả AI theo tháng.
6. `speedy-refresh-rule` (`/refresh-rule`): Quét và cập nhật coding conventions thực tế.
7. `speedy-refresh-style` (`/refresh-style`): Tổng hợp Repo Style & Industry Style Guide.
8. `speedy-cleanup` (`/cleanup`): Dry-run và dọn dẹp artifact cũ có xác nhận.
9. `speedy-update` (`/update-speedy`): Kiểm tra phiên bản, staging, backup và cập nhật engine an toàn.
*(Kèm tiện ích định vị nhanh `speedy-repomap` cho agent và developer).*

---

## 4. Lộ trình 10 Bước & Quyết định đã chốt

- **Quyết định đã chốt cùng User**:
  1. Chế độ duyệt khi build: `strict`.
  2. Quy ước đường dẫn rules: dùng `rules/` tại Builder và `.speedy/rules/` tại Product.
  3. Lược bỏ hoàn toàn `.github/` (Copilot), `.vscode/`, `commit-push` và `create-pr`; chỉ tập trung 100% cho **Antigravity IDE**.
  4. Thứ tự ưu tiên model Gemini: `Gemini Hydrogen` (nhẹ/tài liệu/orchestrator) → `Gemini Neon` (task thường) → `Gemini Carbon` (chỉ bài toán phức tạp cao, hạn chế dùng).
  5. Xóa thư mục tham khảo `refs/` tại **Bước 9** sau khi toàn bộ kiểm thử E2E đã PASS.
