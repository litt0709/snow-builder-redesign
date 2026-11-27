# Speedy DevKit — Workspace Router & Core Principles (Antigravity)

> **THÔNG BÁO AGENT**: Đọc toàn bộ file này trước khi thực hiện bất kỳ tác vụ nào. Giữ ngữ cảnh tinh gọn: chỉ nạp thêm role/tài liệu/code liên quan trực tiếp đến bước hiện tại.

---

## 1. Ranh Giới Không Gian Làm Việc

- **Mã nguồn ứng dụng**: Nằm ở các thư mục của dự án (ngoài `.speedy/`, `ai-workspace/`, `.agents/`).
- **Lõi DevKit (`.speedy/`)**: Chứa CLI deterministic (`.speedy/scripts/speedy_cli.py`), bộ luật cốt lõi (`.speedy/rules/1..5`), role contracts (`.speedy/roles/`), flows (`.speedy/flows/`) và commands (`.speedy/commands/`). Không sửa `.speedy/` khi làm task ứng dụng.
- **Bộ nhớ vận hành (`ai-workspace/`)**: Nơi duy nhất lưu `specs/`, `plans/`, `sessions/`, `state/`, `audit/`, `logs/`, `reports/`, `tmp/` và tài liệu kỹ thuật ứng dụng `ai-workspace/docs/` (tuyệt đối không ghi tài liệu nội bộ Speedy vào `ai-workspace/docs/`).

---

## 2. Nguyên Tắc Bắt Buộc (Core Principles)

| Nguyên tắc | Quy tắc thực thi |
|---|---|
| **User Primacy (Tối thượng)** | Mọi chỉ thị từ User là ưu tiên số 1. Khi User còn băn khoăn hoặc yêu cầu còn điểm mở, Agent đóng vai trò cố vấn chuyên môn: phân tích sắc bén, đa chiều và đề xuất giải pháp tối ưu nhất. |
| **Simple Responses (Tối thượng)** | Phản hồi trực diện, ngắn gọn, khúc chiết bằng **Tiếng Việt** (giữ nguyên thuật ngữ kỹ thuật, CLI, path). Biến vấn đề phức tạp thành dễ hiểu; ưu tiên bảng/sơ đồ, tuyệt đối không viết dài dòng lan man. |
| **Clearly Direction** | Mã nguồn, cấu trúc module, tài liệu và luồng vận hành phải tường minh, đơn giản và dễ hiểu nhất có thể; triệt tiêu sự phức tạp mơ hồ không cần thiết. |
| **Core Architecture (SOLID, KISS, DRY, YAGNI)** | Thiết kế mô-đun độc lập qua contract/interface rõ ràng, không lặp logic, không xây tính năng thừa. |
| **Data Consistency & SSOT** | Mọi số liệu, trạng thái hoặc công thức nghiệp vụ xuất hiện ở nhiều màn hình/endpoint (list, table, modal, chart, API) **BẮT BUỘC** dùng chung một hàm nguồn duy nhất trong core; cấm phân mảnh công thức hay hardcode ở từng view gây mâu thuẫn dữ liệu. |
| **Generality & Zero-Hardcode** | Thiết kế giải pháp, thuật toán và cấu hình mang tính tổng quát, dễ tái sử dụng, không hardcode đường dẫn cá nhân hay dữ liệu tạm. |
| **Correctness-First & Evidence-First** | Ưu tiên tính đúng đắn trên hết. Chỉ báo hoàn tất khi các tiêu chí `AC` và kiểm thử liên quan đã chạy thật kèm bằng chứng; cấm Test Laundering (không xóa/skip/lỏng test). |
| **Balanced AI-DD & Smart Gate** | Mặc định chạy `balanced`: ghi artifact → chạy `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>` → chỉ dừng gọi `ask_question` khi có `Open questions`, `high_risk`, `REQUEST_CHANGES`, xung đột hoặc release (hỗ trợ `--policy strict` khi cần duyệt từng bước). |
| **Scope Discipline & Anti-Patterns** | Chỉ sửa đúng phạm vi đã duyệt; lỗi ngoài phạm vi chỉ ghi nhận (`Stop-and-Note`). Tuân thủ 11 Anti-Patterns bắt buộc tránh tại [.speedy/rules/1.principle.md](.speedy/rules/1.principle.md). Không tự ý `git commit`/`push`/xóa dữ liệu ngoài `ai-workspace/tmp/`. |
| **Context Optimization & Gemini Tiers** | Retrieval theo bậc thang: `repomap query` → `ai-workspace/docs/architecture/overview.md` → chỉ mở đúng file liên quan. Chọn đúng tầng model: **Gemini Hydrogen** (`orchestrator`, `docs-manager`, `writer`) → **Gemini Neon** (mặc định chủ lực) → **Gemini Carbon** (hạn chế tối đa, chỉ dùng cho `architect`/`reviewer` vùng cực khó/rủi ro cao). |

---

## 3. Điểm Vào Nhanh (Slash Commands)

| Skill / Slash Command | Chức năng | Đặc tả chi tiết |
|---|---|---|
| `/flow` | Điều phối pipeline `feature` / `fix` / `simple` / `verify` | [.speedy/commands/flow.md](.speedy/commands/flow.md) |
| `/specs` | Tạo & cập nhật lặp lại tài liệu thiết kế tại `ai-workspace/specs/` | [.speedy/commands/specs.md](.speedy/commands/specs.md) |
| `/analyst` | Phân tích yêu cầu & xuất Implementation Brief độc lập | [.speedy/commands/analyst.md](.speedy/commands/analyst.md) |
| `/docs` | Lập Topic Map & biên soạn tài liệu kỹ thuật ứng dụng / cross-repo | [.speedy/commands/docs.md](.speedy/commands/docs.md) |
| `/docs-view`, `/audit-view` | Kết xuất HTML đọc tài liệu và bảng điều khiển hiệu quả AI | [.speedy/commands/docs-view.md](.speedy/commands/docs-view.md) · [.speedy/commands/audit-view.md](.speedy/commands/audit-view.md) |
| `/refresh-rule`, `/refresh-style` | Trích xuất coding convention và style guide từ mã nguồn thực tế | [.speedy/commands/refresh-rule.md](.speedy/commands/refresh-rule.md) · [.speedy/commands/refresh-style.md](.speedy/commands/refresh-style.md) |
| `/cleanup`, `/update-speedy` | Dọn dẹp artifact cũ có xác nhận và cập nhật engine an toàn | [.speedy/commands/cleanup.md](.speedy/commands/cleanup.md) · [.speedy/commands/update-speedy.md](.speedy/commands/update-speedy.md) |
| `/repomap` | Định vị nhanh module mã nguồn trước khi đọc file | [.speedy/commands/repomap.md](.speedy/commands/repomap.md) |

---

## 4. Checklist Vòng Đời Task

- **Trước khi code**: Đọc `AGENTS.md` + [.speedy/rules/1.principle.md](.speedy/rules/1.principle.md) (khi cần thiết kế/code); làm rõ yêu cầu & `AC`; kiểm tra `repomap` & `overview.md`.
- **Trong & sau khi code**: Giữ đúng `Scope` & `SSOT` (không phân mảnh logic giữa các view); chạy `state complete` & verification thực tế; cập nhật `ai-workspace/docs/` nếu đổi kiến trúc; không để file nháp ngoài `ai-workspace/tmp/`.
