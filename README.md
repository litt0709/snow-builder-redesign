# SNOW Builder & Speedy DevKit v2.0 (Antigravity IDE)

Hệ thống công cụ hỗ trợ phát triển phần mềm bằng AI theo phương pháp **Strict AI-DD (AI-Driven Development)**, thiết kế chuyên biệt cho **Antigravity IDE** với ba mục tiêu cốt lõi: **Chính xác (Correctness-first) · Nhanh · Tiết kiệm Token & Quota**.

---

## 1. Kiến trúc Hai Lớp

| Lớp | Thư mục | Vai trò | Namespace |
|---|---|---|---|
| **SNOW Builder** | Root (`.`) | Xưởng thiết kế, phát triển, kiểm thử tự động, đóng gói và phát hành DevKit | `builder-*` |
| **Speedy DevKit** | `src/` | Bộ công cụ độc lập cài vào dự án ứng dụng của người dùng trên Antigravity IDE | Không có prefix `builder-` |

---

## 2. Phân tầng Model Thông minh (Gemini Pro Ecosystem)

| Tầng | Model ưu tiên | Đối tượng áp dụng | Ghi chú Quota |
|---|---|---|---|
| **Nhẹ & Nhanh** | **Gemini Hydrogen** | `orchestrator`, `docs-manager`, `writer` | Tiết kiệm tối đa quota cho điều phối & tài liệu |
| **Tiêu chuẩn (Mặc định)** | **Gemini Neon** | `analyst`, `implementer`, `tester` (và `architect`/`reviewer` mức thường) | Chủ lực cho các tác vụ phát triển hàng ngày |
| **Chuyên sâu (Giới hạn)** | **Gemini Carbon** | `architect`, `reviewer` cho bài toán cực khó / rủi ro cao | **Hạn chế dùng** vì rất nhanh chạm giới hạn quota |

---

## 3. Cấu trúc Thư mục Chính

```text
snow-builder/
├── AGENTS.md                  # Router & ranh giới vận hành Builder
├── README.md                  # Tài liệu hướng dẫn nhanh
├── .agents/                   # Tích hợp Antigravity cho Builder (rules + skills builder-*)
├── rules/                     # Bộ nguyên tắc cốt lõi của Builder (1..5)
├── docs/                      # Tài liệu kiến trúc Builder & bản đồ Product
├── plans/                     # Kế hoạch phát triển DevKit
├── sessions/                  # Canonical state & handoff của Builder
├── scripts/                   # Công cụ đóng gói (package.py), cài đặt (install.py), autotest.py
├── tests/                     # Bộ kiểm thử static, CLI, boundary, installer và fixture E2E
└── src/                       # Speedy DevKit — sản phẩm xuất độc lập 100%
    ├── AGENTS.md              # Router & ranh giới Speedy trong dự án ứng dụng
    ├── .agents/               # Tích hợp Antigravity cho Speedy (rules + skills)
    ├── .speedy/               # Lõi engine: VERSION, manifest, roles, flows, commands, docs/themes, rules, schemas, scripts
    └── ai-workspace/          # Bộ nhớ vận hành tại dự án đích (specs, docs, plans, sessions, state, audit, reports)
```

---

## 4. Cài Đặt Speedy Bằng 1 Lệnh Từ Git & Cập Nhật `/update-speedy`

### 4.1. Cài Đặt 1 Lệnh Tại Bất Kỳ Máy Nào (Khuyến Nghị)

Mở terminal tại **thư mục gốc dự án ứng dụng của bạn** và chạy đúng 1 lệnh:

```bash
curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash
```

Lệnh trên sẽ tự động:
1. Tải bản mới nhất từ Git (ưu tiên tag phát hành `speedy-vX.Y.Z` cao nhất; tự động lấy nhánh `main` nếu chưa gắn tag) vào thư mục tạm rồi dọn sạch sau khi xong.
2. Cài đặt Speedy DevKit vào dự án (bảo toàn 100% file có sẵn của dự án nhờ `--skip-conflicts` và tự tạo backup tại `ai-workspace/tmp/backups/`).
3. **Tự động cập nhật ignore 2 lớp an toàn cho cả Git lẫn Antigravity IDE**:
   - Ghi `/.speedy/` và `/ai-workspace/` vào `.gitignore` (tạo mới nếu chưa có, nối idempotent nếu đã có).
   - Ghi `/.agents/` và `/AGENTS.md` vào `.git/info/exclude` (nếu dự án là Git repo) thay vì `.gitignore` — giúp Git không đẩy nhầm Speedy lên repo dự án nhưng **Antigravity IDE vẫn quét và hiển thị đầy đủ slash commands (`/flow`, `/specs`, `/docs`, `/update-speedy`...)**.
4. Tự động ghi nhớ nguồn cài đặt vào `.speedy/config/source.local.json` (nằm ngoài manifest) để **các lần sau cập nhật Speedy bạn chỉ cần gõ slash command `/update-speedy`** trên Antigravity IDE.

**Các biến thể hữu ích khi chạy 1 lệnh:**
- Xem trước kế hoạch cài đặt (dry-run, không ghi file):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash -s -- --dry-run
  ```
- Giữ nguyên `.gitignore` (nếu muốn commit Speedy vào repo dự án):
  ```bash
  curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash -s -- --no-gitignore
  ```
- Cài từ repo nội bộ / Private repo qua SSH hoặc fork riêng:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/litt0709/snow-builder-redesign/main/scripts/install.sh | bash -s -- --source git@github.com:litt0709/snow-builder-redesign.git
  ```

### 4.2. Cập Nhật Speedy Ở Các Lần Sau
Trong Antigravity IDE tại dự án đã cài Speedy, chỉ cần gõ:
```text
/update-speedy
```
Agent sẽ tự động chạy `python3 .speedy/scripts/speedy_cli.py update` (đọc nguồn từ `.speedy/config/source.local.json`), hiển thị danh sách thay đổi/xung đột, xin xác nhận qua `ask_question`, tạo backup rollback, cập nhật engine và đồng bộ `.gitignore` mà **bảo toàn 100% `ai-workspace/`**.

### 4.3. Cài Đặt Cục Bộ Từ Thư Mục SNOW Builder & Công Cụ Khác

```bash
# Xem trước kế hoạch cài đặt cục bộ (Dry-run)
python3 scripts/install.py --target /path/to/your-app --dry-run

# Cài đặt cục bộ
python3 scripts/install.py --target /path/to/your-app --apply --skip-conflicts

# Khôi phục nguyên trạng 1 lệnh nếu cần rollback (bao gồm cả .gitignore và source.local.json)
python3 scripts/install.py --target /path/to/your-app --rollback /path/to/your-app/ai-workspace/tmp/backups/<ten-backup>

# Đóng gói riêng thành thư mục độc lập để chia sẻ
python3 scripts/package.py --out dist/speedy-package

# Chạy kiểm thử toàn bộ Builder & Speedy
PYTHONDONTWRITEBYTECODE=1 python3 scripts/autotest.py --report-out reports/autotest-final.json
```

- **Tài liệu chi tiết**:
  - [Hướng dẫn Antigravity Settings, Cài đặt & Sử dụng](docs/ANTIGRAVITY_GUIDE.md)
  - [Tổng quan hệ thống](docs/OVERVIEW.md)
  - [Kiến trúc Harness & Lõi CLI](docs/ARCHITECTURE.md)
  - [Bản đồ sản phẩm Speedy](docs/product/README.md)
  - [Đặc tả tái xây dựng gốc](specs/design.md)
