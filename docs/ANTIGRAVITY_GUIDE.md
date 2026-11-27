# Hướng Dẫn Cài Đặt, Sử Dụng & Cấu Hình Antigravity IDE Cho Speedy DevKit v2.0

> Tài liệu hướng dẫn vận hành thực tế cho **Speedy DevKit v2.0** và **SNOW Builder** trên **Antigravity IDE / Antigravity 2.0**.

---

## 1. Cấu Hình Antigravity IDE Được Khuyến Nghị

> *Lưu ý minh bạch*: Các thiết lập dưới đây căn cứ theo tài liệu chính thức của Antigravity IDE (tháng 11/2026); tên menu cụ thể có thể thay đổi nhẹ theo phiên bản ứng dụng trên máy người dùng.

### 1.1. Tách Ba Lớp Kiểm Soát

| Lớp kiểm soát | Phạm vi tác dụng | Ghi chú quan trọng |
|---|---|---|
| **Antigravity Permissions & Sandbox** | Cho phép đọc/sửa file trong workspace và chạy lệnh test an toàn không hỏi vụn vặt từng dòng | Quyền sửa file của IDE **không** tự động phê duyệt chuyển stage của Speedy |
| **Plan Review Policy** | Kiểm soát việc duyệt kế hoạch tổng của IDE (`Always Ask` cho chế độ `strict`) | Độc lập với Handoff Gate của từng vai trò chuyên môn |
| **Speedy Stage Gate (`strict`)** | Chặn chuyển stage qua `speedy_cli.py` cho đến khi có `ask_question` xác nhận từ con người | Cưỡng chế ở mức `workflow_enforced` |

### 1.2. Thiết Lập Khuyến Nghị Trong Settings Của Antigravity

| Mục cấu hình | Giá trị khuyến nghị |
|---|---|
| **Conversation Mode** | `Planning` đối với `/flow` (`feature` / `fix`) |
| **Plan Review Policy** | `Always Ask` (khi chạy `strict`) |
| **Terminal Sandbox** | **Bật** (`Proceed in Sandbox` hoặc `Default`) |
| **Non-Workspace File Access** | `Ask` hoặc `Deny` (không mở toàn bộ thư mục `~`) |
| **MCP Servers** | Mặc định tắt các server không dùng để tiết kiệm hàng nghìn token schema mỗi lượt |

**Danh sách quyền lệnh gợi ý (nếu dùng Permission Rules mới, lưu ý thứ tự `Deny > Ask > Allow`):**
- **Allow**: `command(git status)`, `command(git diff)`, `command(git log)` (chỉ thêm lệnh test cụ thể sau khi đã kiểm tra script của dự án).
- **Ask**: `command(git commit)`, `command(git push)`, `command(git tag)`, `command(git reset)`, `command(git rebase)`, `command(git clean)`, `command(rm)`, `command(sudo)`.
- **Deny**: `command(rm -rf /)`, `command(rm -rf ~)`.

**Kích hoạt thêm lớp bảo vệ `runtime_enforced` (Tùy chọn / Opt-in):**
Sao chép `.speedy/config/antigravity-hooks.example.json` thành `.agents/hooks.json` trong dự án để kích hoạt `hook_guard.py` tự động kiểm tra mọi lời gọi `run_command`, `write_file`, `edit_file` trước khi thực thi.

---

## 2. Chiến Lược Chọn Model Gemini Pro (Tối Ưu Tốc Độ & Bảo Vệ Quota)

| Thứ tự ưu tiên | Model trên Antigravity | Khi nào chọn | Lý do |
|---|---|---|---|
| **1 — Nhẹ & Nhanh** | **Gemini Hydrogen** | Khi chạy điều phối (`speedy-flow`), viết hoặc đồng bộ tài liệu (`speedy-docs`, `docs-manager`), dọn dẹp (`speedy-cleanup`) | Tốc độ phản hồi cực nhanh, tốn rất ít quota. |
| **2 — Mặc định chủ lực** | **Gemini Neon** | Mặc định cho hầu hết công việc hàng ngày: phân tích (`analyst`), viết code (`implementer`), viết test (`tester`), và thiết kế/review mức độ thường | Cân bằng tốt nhất giữa độ chính xác lập trình và hạn mức sử dụng. |
| **3 — Chuyên sâu (Hạn chế)** | **Gemini Carbon** | **Chỉ bật** cho `architect` hoặc `reviewer` độc lập khi gặp bài toán kiến trúc cực khó hoặc vùng rủi ro cao (`auth`, `payment`, `schema`, `security`) | **Rất nhanh chạm giới hạn quota** — không bật cố định cho toàn bộ phiên dài. |

---

## 3. Cài Đặt Speedy Vào Dự Án Ứng Dụng

Từ thư mục **SNOW Builder**:

```bash
# Bước 1: Xem trước kế hoạch cài đặt (Dry-run an toàn, không ghi file)
python3 scripts/install.py --target /duong/dan/du-an-cua-ban --dry-run

# Bước 2: Cài đặt chính thức (bảo toàn 100% các skill/rule riêng đã có của dự án)
python3 scripts/install.py --target /duong/dan/du-an-cua-ban --apply --skip-conflicts
```

Nếu muốn xuất riêng một thư mục gói sạch để chia sẻ cho đồng nghiệp:
```bash
python3 scripts/package.py --out dist/speedy-v2.0.0
```

---

## 4. Sử Dụng Hàng Ngày, Resume, Cập Nhật & Phát Hành

### 4.1. Các Skill / Lệnh Chính Trong Dự Án Đích
- Gọi `/speedy-flow` (hoặc mô tả yêu cầu kèm `/flow`): Tự động phân loại `feature` / `fix` / `simple` / `verify`, khởi tạo session, nạp Context Packet gọn nhẹ và dừng xin duyệt ở từng cổng quan trọng.
- Gọi `/speedy-specs` (hoặc `/specs`): Ghi nhận và cập nhật lặp lại tài liệu đặc tả thiết kế chuẩn 6 phần tại `ai-workspace/specs/`, dễ đọc cho cả Owner lẫn LLM ở các phiên sau.
- Gọi `/speedy-analyst`: Lập riêng bản Implementation Brief + danh sách `AC-001..N` rồi dừng.
- Gọi `/speedy-docs`: Quét 2 cấp lập Topic Map và viết bộ tài liệu kiến trúc vào `ai-workspace/docs/`.
- Gọi `/speedy-docs-view` và `/speedy-audit-view`: Xuất báo cáo HTML đọc offline tại chỗ.
- Gọi `/speedy-cleanup`: Xem dry-run và dọn dẹp các phiên cũ đã hoàn tất.

### 4.2. Tiếp Tục Công Việc Trên Phiên Chat Mới (Resume)
Không cần dán lại lịch sử chat cũ. Mở cuộc trò chuyện mới trên Antigravity và gửi:
> *"Tiếp tục session `<SID>` từ trạng thái đã lưu. Chạy `python3 .speedy/scripts/speedy_cli.py session resume --sid <SID>` và chỉ đọc artifact liên quan tới `current_stage`."*

CLI sẽ tự động đối chiếu semantic checksum của các bản thiết kế đã duyệt và snapshot mã nguồn hiện tại để tiếp tục đúng bước đang dở.

### 4.3. Cập Nhật & Khôi Phục (Rollback)
```bash
# Kiểm tra bản cập nhật mới ở chế độ dry-run
python3 .speedy/scripts/speedy_cli.py update --source /duong/dan/hoac/git-url

# Áp dụng cập nhật (ai-workspace/ luôn được giữ nguyên 100%)
python3 .speedy/scripts/speedy_cli.py update --source /duong/dan/hoac/git-url --apply --skip-conflicts

# Khôi phục nguyên trạng trong 1 giây nếu cần
python3 .speedy/scripts/speedy_cli.py update --rollback ai-workspace/tmp/backups/<ten-thu-muc-backup>
```

### 4.4. Phát Hành Phiên Bản Mới Từ SNOW Builder
Kích hoạt skill `builder-release`: chạy `python3 scripts/autotest.py` kiểm định toàn diện → chọn mức nâng SemVer (`MAJOR.MINOR.PATCH`) → cập nhật `src/.speedy/VERSION`, `manifest.json` & `docs/CHANGELOG.md` → xác nhận qua HITL trước khi tạo tag `speedy-vX.Y.Z`.
