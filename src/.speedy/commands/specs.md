# `/specs` — Tạo & Tiến Hóa Đặc Tả Thiết Kế Theo Phase / Version

## Mô tả
Thực thi vai trò **Specs Designer** (`Gemini Neon`) để ghi nhận yêu cầu từ chủ dự án (Owner) thành hệ thống tài liệu đặc tả thiết kế ngắn gọn, khoa học tại `ai-workspace/specs/`. Tài liệu được tổ chức theo từng **Phase / Version** thông qua con trỏ SSOT `INDEX.md`, giúp tránh phình to 1 file duy nhất nhưng vẫn ngăn chặn việc tách file rác liên tục.

## Cấu Trúc Thư Mục Chuẩn (`ai-workspace/specs/`)
```text
ai-workspace/specs/
├── INDEX.md                  # SSOT mục lục siêu nhẹ (~15 dòng): trỏ đúng 1 Active Spec duy nhất
├── 01-v1-<slug>.md           # Phase 1 (Status: Completed / Frozen khi đã qua phase mới)
└── 02-v2-<slug>.md           # Phase 2 (Status: Active ← mọi lệnh /specs sau đó tự bám vào đây)
```

- **`INDEX.md`** lưu 3 thông tin cốt lõi: `Active Spec`, `Active Phase / Version`, và bảng mục lục (`# | File | Phase / Version | Status | Mục tiêu chính`).
- Mỗi file spec tuân thủ cấu trúc chuẩn 6 phần:
  1. **Tổng quan** (bối cảnh, bài toán, IN/OUT scope; kèm mục **`Kế thừa từ Phase trước`** 3–5 dòng nếu là Phase `>= 2`)
  2. **Goal** (mục tiêu đo lường được)
  3. **Mission** (giá trị cốt lõi & nguyên tắc bất biến)
  4. **Các Step thực hiện** (lộ trình từng bước theo phụ thuộc & checkpoint)
  5. **Trade-off & Pitfall** (đánh đổi kỹ thuật & bẫy cần tránh)
  6. **Tài liệu tham khảo** (module/file, docs nội bộ, chuẩn bên ngoài)
  - Kèm bảng **Lịch sử Cập nhật** (`Version | Ngày | Thay đổi`).

## Quy Trình Create / Update / Split (Anti-Spam Split Guard — 4 Chốt)

Khi chạy `/specs`, đọc `ai-workspace/specs/INDEX.md` + header của `Active Spec` rồi quyết định theo đúng 4 chốt chặn:

1. **Chốt 1 — Phân biệt Ngữ Nghĩa (`Khởi tạo Phase Mới` vs `Tham chiếu Phase Đang Mở`)**:
   - *Khởi tạo mới*: *"bắt đầu phase mới..."*, *"xong v1 rồi, sang v2..."*, *"tách sang phase 2 về..."*, hoặc nêu rõ số/tên Phase/Version **khác** `Active Phase / Version` hiện tại.
   - *Tham chiếu tiếp tục*: *"trong phase mới này thêm..."*, *"ở bản mới sửa lại..."*, *"v2 bổ sung..."* khi `Active Spec` **đã là** phase/version đó → **cập nhật thẳng vào `Active Spec`**, không tách file.
2. **Chốt 2 — Chống Tách Liên Tiếp (Anti-Churn)**:
   - Nếu `Active Spec` hiện tại đang ở trạng thái `Draft` (chưa `Approved`/`Completed`) **và** cùng chủ đề/mục tiêu → **mặc định không tách file**, hợp nhất vào `Active Spec` dù người dùng nhắc cụm từ *"phase mới"* nhiều lượt liên tiếp.
3. **Chốt 3 — Smart Confirmation Gate (Chỉ hỏi 1 câu khi nằm vùng ranh giới)**:
   - Chỉ khi `Active Spec` chưa đóng (`Draft`/`Active`) **nhưng** yêu cầu mới lệch hẳn sang chủ đề khác hoặc người dùng nhấn mạnh muốn tách → gọi `ask_question` **đúng 1 câu** với 2 lựa chọn:
     - `(Recommended) Cập nhật tiếp vào <active-file> (Phase hiện tại)`
     - `Đóng <active-file> & tạo file Phase/Version mới <next-file>`
   - Nếu `Active Spec` đã `Approved` / `Completed` và người dùng yêu cầu bắt đầu Phase/Version mới → **tự tách ngay** không hỏi thừa.
4. **Chốt 4 — Kế Thừa Ngữ Cảnh & Cập Nhật Con Trỏ SSOT**:
   - Khi tách sang file mới (`02-v2-<slug>.md`):
     1. Đổi `Status` của file cũ sang `Completed` (hoặc `Frozen / Baseline`).
     2. Ghi mục **`Kế thừa từ Phase trước`** (3–5 dòng tóm tắt nền tảng còn hiệu lực + link file trước) ngay đầu file mới để LLM chạy `/flow` sau này chỉ cần đọc `INDEX.md` + `Active Spec`.
     3. Cập nhật `Active Spec` và bảng mục lục trong `ai-workspace/specs/INDEX.md`.
- **Soft Size Guard**: Nếu file `Active Spec` vượt quá ~**350–400 dòng**, chỉ nhắc nhẹ 1 dòng ở cuối phản hồi gợi ý tách phase mới ở lần sau, không tự ý cắt ngang.

## Scope & Gate
- **Scope**: Chỉ đọc tham khảo repo (ưu tiên `repomap query` & `ai-workspace/docs/`) và chỉ ghi file trong `ai-workspace/specs/`. Không sửa mã nguồn ứng dụng.
- **Gate**: Nếu yêu cầu mâu thuẫn với spec hiện tại hoặc thiếu ràng buộc cốt lõi → gọi `ask_question` làm rõ trước khi ghi. Sau khi ghi, trả về link file spec + `INDEX.md` + tóm tắt thay đổi rồi dừng lại.
