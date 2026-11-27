# Speedy DevKit — Workspace Router (Antigravity IDE)

> **THÔNG BÁO AGENT**: Đọc file này đầu tiên. Giữ ngữ cảnh tinh gọn: chỉ nạp đúng flow/role/tài liệu của bước đang thực hiện.

---

## 1. Ranh Giới Không Gian Làm Việc

- **Mã nguồn ứng dụng**: Nằm ở các thư mục của dự án (ngoài `.speedy/`, `ai-workspace/`, `.agents/`).
- **Lõi DevKit (`.speedy/`)**: Chứa CLI deterministic (`.speedy/scripts/speedy_cli.py`), role contracts (`.speedy/roles/`), flows (`.speedy/flows/`), commands (`.speedy/commands/`) và rules (`.speedy/rules/`). Không sửa `.speedy/` khi làm task ứng dụng.
- **Bộ nhớ vận hành (`ai-workspace/`)**: Nơi duy nhất lưu `specs/`, `plans/`, `sessions/`, `state/`, `audit/`, `logs/`, `reports/` và tài liệu kỹ thuật ứng dụng `ai-workspace/docs/`.
  - **Content Boundary**: `ai-workspace/docs/` chỉ mô tả kiến trúc và nghiệp vụ của ứng dụng, tuyệt đối không ghi nội dung internal của Speedy DevKit vào đây.

---

## 2. Quy Tắc Bất Biến & Phân Tầng Model Gemini

1. **Correctness-First & Smart Gate (`balanced`)**: Mặc định chạy chế độ `balanced`. Sau mỗi stage chuyên môn: ghi artifact → chạy `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>` → chỉ dừng gọi `ask_question` khi có `Open questions`, `high_risk`, `REQUEST_CHANGES`, xung đột hoặc release (hoặc khi bật `--policy strict`). Quyền sửa file của IDE không thay thế phê duyệt tại các cổng bắt buộc.
2. **Evidence-First**: Chỉ báo hoàn tất khi các tiêu chí nghiệm thu (`AC`) và bộ kiểm thử liên quan đã chạy thật kèm bằng chứng. Không sửa test/assertion trái phép để làm xanh kết quả.
3. **Retrieval Tiết Kiệm Token**: Định vị module bằng `python3 .speedy/scripts/speedy_cli.py repomap query "<từ khóa>"` → đọc index `ai-workspace/docs/architecture/overview.md` (nếu có) → chỉ đọc tài liệu và file code trong phạm vi đã thu hẹp. Không đọc trực tiếp file `repomap.json`.
4. **Thứ tự ưu tiên Model trên Antigravity**:
   - **Gemini Hydrogen**: Dùng cho điều phối (`orchestrator`), đồng bộ và viết tài liệu (`docs-manager`, `writer`).
   - **Gemini Neon**: Mặc định chủ lực cho các tác vụ bình thường (`analyst`, `implementer`, `tester`, và `architect`/`reviewer` mức tiêu chuẩn).
   - **Gemini Carbon**: **Hạn chế tối đa** (do rất nhanh chạm quota limit) — chỉ dùng cho `architect` hoặc `reviewer` khi xử lý bài toán có độ phức tạp hoặc rủi ro cao.
5. **Minimal Scope & Ngôn ngữ**: Chỉ sửa đúng phạm vi đã duyệt; không tự ý commit/push/xóa dữ liệu ngoài `ai-workspace/tmp/`. Phản hồi và viết tài liệu bằng **Tiếng Việt** rõ ràng, súc tích.

---

## 3. Điểm Vào Nhanh (Antigravity Skills / Commands)

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
