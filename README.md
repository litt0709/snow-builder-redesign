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

## 4. Cài Đặt Speedy Vào Dự Án Của Bạn Qua CLI

Từ thư mục gốc của **SNOW Builder**, dùng `scripts/install.py` để cài đặt Speedy DevKit vào bất kỳ dự án ứng dụng nào:

```bash
# 1. Xem trước kế hoạch cài đặt (Dry-run an toàn, không ghi file)
python3 scripts/install.py --target /path/to/your-app --dry-run

# 2. Cài đặt chính thức vào dự án đích
#    - Tự động thêm block ignore (/.agents/, /.speedy/, /ai-workspace/, /AGENTS.md)
#      vào .gitignore của dự án để khi push Git không làm nặng repo ứng dụng.
#    - Tự động tạo bản backup tại ai-workspace/tmp/backups/ trước khi ghi.
python3 scripts/install.py --target /path/to/your-app --apply --skip-conflicts
```

**Tùy chọn CLI hữu ích khác:**
- Giữ nguyên `.gitignore` (nếu bạn muốn commit Speedy chung vào repo):
  ```bash
  python3 scripts/install.py --target /path/to/your-app --apply --no-gitignore
  ```
- Khôi phục nguyên trạng 1 lệnh nếu cần rollback (bao gồm cả `.gitignore`):
  ```bash
  python3 scripts/install.py --target /path/to/your-app --rollback /path/to/your-app/ai-workspace/tmp/backups/<ten-backup>
  ```
- Đóng gói riêng thành thư mục độc lập để chia sẻ:
  ```bash
  python3 scripts/package.py --out dist/speedy-package
  ```
- Chạy kiểm thử toàn bộ Builder & Speedy:
  ```bash
  PYTHONDONTWRITEBYTECODE=1 python3 scripts/autotest.py --report-out reports/autotest-final.json
  ```

- **Tài liệu chi tiết**:
  - [Hướng dẫn Antigravity Settings, Cài đặt & Sử dụng](docs/ANTIGRAVITY_GUIDE.md)
  - [Tổng quan hệ thống](docs/OVERVIEW.md)
  - [Kiến trúc Harness & Lõi CLI](docs/ARCHITECTURE.md)
  - [Bản đồ sản phẩm Speedy](docs/product/README.md)
  - [Đặc tả tái xây dựng gốc](specs/design.md)
