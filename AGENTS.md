# SNOW Builder — Build Workspace (Antigravity Edition)

> **THÔNG BÁO AGENT**: Đọc file này đầu tiên trước mọi tác vụ. Giữ context tối giản: chỉ đọc thêm tài liệu liên quan trực tiếp đến bước hiện tại.

---

## 1. Tổng quan & Ranh giới Bắt buộc

- **SNOW Builder** (root repo): Xưởng chế tạo, kiểm thử, đóng gói và phát hành DevKit dành riêng cho **Antigravity IDE**.
- **Speedy DevKit** (`src/`): Sản phẩm đầu ra **hoàn toàn độc lập**, copy-and-use để cài vào dự án ứng dụng của người dùng trên Antigravity IDE.
- **Ranh giới tuyệt đối**:
  - Khi Builder sửa `src/`, mọi `plans/`, `sessions/`, `reports/`, `logs/` của quá trình phát triển DevKit phải ghi ở **root Builder**, tuyệt đối không ghi dữ liệu giả vào `src/ai-workspace/`.
  - Khi sửa bất kỳ file nào trong `src/`, bắt buộc đọc thêm [src/AGENTS.md](src/AGENTS.md) để đảm bảo **không bao giờ** trỏ đường dẫn ngược ra ngoài `src/` (như `../../rules/` hay tên namespace `builder-*`).
  - Tài liệu tổng quan: [docs/OVERVIEW.md](docs/OVERVIEW.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/product/README.md](docs/product/README.md).

---

## 2. Nguyên tắc Bắt buộc & Phân tầng Model (Gemini Pro)

| Nguyên tắc | Quy tắc thực thi |
|---|---|
| **Core (KISS, DRY, YAGNI, SOLID)** | Lõi nhỏ stdlib Python, hợp đồng role tập trung một nơi, chỉ tích hợp thuần Antigravity (`.agents/`). |
| **Correctness-First** | Khi tốc độ/token xung đột với tính đúng đắn, luôn ưu tiên correctness. Không bỏ gate/test để lấy số đẹp. |
| **Strict AI-DD & Evidence-First** | Mặc định `strict`: ghi artifact → validate contract → cập nhật canonical `state.json` → xin human approval (`ask_question`). Không báo "xong" khi chưa có verification evidence. |
| **Lazy Load & Context Packet** | Index trước (`repomap`, `overview.md`) → tài liệu chi tiết sau → source liên quan cuối cùng. Không preload toàn bộ `rules/`, `docs/` hay `sessions/`. |
| **Scope Discipline & Portable** | Chỉ sửa trong scope đã duyệt. Không hardcode đường dẫn máy cá nhân hay URL nội bộ. |
| **Ngôn ngữ & Trình bày** | 100% Tiếng Việt rõ ràng (giữ thuật ngữ kỹ thuật, CLI command, JSON key, path). Ưu tiên bảng/list súc tích. |

### Thứ tự ưu tiên Model trên Antigravity (Tối ưu Quota & Hiệu năng)

| Mức ưu tiên | Model | Vai trò / Tác vụ áp dụng | Quy tắc kiểm soát Quota |
|---|---|---|---|
| **1 — Nhẹ / Tiết kiệm** | **Gemini Hydrogen** | `orchestrator` (`builder-flow`), `docs-manager`, `writer`, dọn dẹp & tổng hợp báo cáo | Ưu tiên cho điều phối và viết tài liệu ít phức tạp logic. |
| **2 — Mặc định chủ lực** | **Gemini Neon** | `analyst`, `implementer`, `tester` (`builder-qa`, `builder-autotest`, `builder-release`), và `architect`/`reviewer` cho task thường | Dùng mặc định cho hầu hết tác vụ phân tích, code và kiểm thử. |
| **3 — Phức tạp cao (Hạn chế)** | **Gemini Carbon** | Chỉ dùng cho `architect` hoặc `reviewer` khi bài toán có độ phức tạp/rủi ro rất cao (core engine, bảo mật, kiến trúc khó) | **Hạn chế tối đa** vì rất nhanh chạm quota limit; không dùng cho task thường. |

---

## 3. Hệ thống Tài liệu (SSOT)

| Phân loại | Đường dẫn | Khi nào đọc | Nội dung chính |
|---|---|---|---|
| **Rules** | `rules/` | Đọc file liên quan trước khi thiết kế/code | `1.principle.md`, `2.framework.md`, `3.orchestration-flow.md`, `4.logs.md`, `5.testing.md` |
| **Docs** | `docs/` | Đọc khi sửa kiến trúc Builder/Product | `OVERVIEW.md`, `ARCHITECTURE.md`, `product/README.md`, `CHANGELOG.md` |
| **Specs** | `specs/design.md` | Đối chiếu đặc tả thiết kế gốc | Đặc tả kiến trúc, contract, benchmark và Antigravity settings |
| **Plans & Sessions** | `plans/`, `sessions/` | Tra cứu task hiện tại / resume | Kế hoạch `YYYY-MM-DD-<goal>.md`, canonical `state.json` và handoff |
| **Tests & Scripts** | `tests/`, `scripts/` | Khi chạy kiểm thử, đóng gói, cài đặt | `autotest.py`, `package.py`, `install.py` và bộ unit/integration/E2E tests |

---

## 4. Checklist Vòng đời Task

**Trước khi code:**
- [ ] Đã đọc `AGENTS.md` và rule liên quan trong `rules/`? (Nếu chạm `src/`, đã đọc `src/AGENTS.md`?)
- [ ] Phạm vi & tiêu chí nghiệm thu (`AC`) đã rõ? Nếu mơ hồ → hỏi lại User ngay.
- [ ] Đã khởi tạo kế hoạch tại `plans/YYYY-MM-DD-<goal>.md` và session tại `sessions/<sid>/`?

**Trong & sau khi code:**
- [ ] Đã validate Handoff Contract (5 headings + Resume Metadata) và chạy kiểm thử thực tế tại `tests/`?
- [ ] `src/` vẫn độc lập 100%, không rò rỉ tham chiếu Builder hay dữ liệu runtime giả?
- [ ] Đã dừng chờ User phê duyệt tại Stage Gate trước khi sang bước tiếp theo hoặc release?
