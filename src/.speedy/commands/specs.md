# `/specs` (`speedy-specs`) — Tạo & Cập Nhật Tài Liệu Đặc Tả Thiết Kế

## Mô tả
Thực thi vai trò **Specs Designer** (`Gemini Neon`) để ghi nhận yêu cầu từ chủ dự án (Owner) thành tài liệu thiết kế ngắn gọn, khoa học và mạch lạc tại `ai-workspace/specs/<slug>.md`. Tài liệu được tối ưu cho cả con người đọc duyệt lẫn LLM sử dụng làm đầu vào chính xác ở các bước `/flow` hoặc `/analyst`.

Hỗ trợ gọi **nhiều lần** trên cùng một file spec: mỗi lần chạy tiếp theo sẽ đọc bản hiện có, hợp nhất bổ sung/điều chỉnh đúng chỗ, giữ nguyên các quyết định đã chốt và cập nhật mục `Lịch sử Cập nhật`.

## Input & Output
- **Input**: Mô tả ý tưởng, yêu cầu tính năng/kiến trúc mới, hoặc các điểm cần bổ sung/chỉnh sửa (có thể kèm tên file spec mục tiêu, ví dụ `ai-workspace/specs/payment-gateway.md`).
- **Output**: `ai-workspace/specs/<slug>.md` tuân thủ cấu trúc chuẩn 6 phần:
  1. **Tổng quan** (bối cảnh, bài toán, IN/OUT scope)
  2. **Goal** (mục tiêu cụ thể, đo lường được)
  3. **Mission** (giá trị cốt lõi & nguyên tắc bất biến)
  4. **Các Step thực hiện** (lộ trình từng bước theo phụ thuộc & checkpoint)
  5. **Trade-off & Pitfall** (đánh đổi kỹ thuật và bẫy cần tránh)
  6. **Tài liệu tham khảo** (module/file, docs nội bộ, chuẩn bên ngoài)
  - Kèm bảng **Lịch sử Cập nhật** (`Version | Ngày | Thay đổi`).

## Quy Trình Create vs Update (Chạy Lặp Nhiều Lần)
1. **Kiểm tra `ai-workspace/specs/`**:
   - Nếu chưa có file tương ứng → **Tạo mới** (`v1.0`).
   - Nếu đã có file tương ứng → **Đọc toàn bộ bản cũ**, xác định phần cần thêm/sửa/bỏ, hợp nhất có kiểm soát và tăng phiên bản (`v1.0` → `v1.1`).
   - Nếu không rõ nên cập nhật file nào hay tạo file mới → hỏi nhanh người dùng qua `ask_question`.
2. **Bảo đảm dễ nắm bắt cho Người & LLM**:
   - 100% Tiếng Việt rõ ràng (giữ nguyên thuật ngữ kỹ thuật, tên file, API, CLI).
   - Ưu tiên bảng và bullet ngắn gọn; không viết thừa, không lặp ý.
   - Đánh dấu rõ `[Giả định]` hoặc `[Câu hỏi mở]` nếu còn chi tiết cần Owner chốt thêm.

## Scope & Gate
- **Scope**: Chỉ đọc tham khảo repo (nếu cần, ưu tiên `repomap query`) và chỉ ghi file trong `ai-workspace/specs/`. Không sửa mã nguồn ứng dụng.
- **Gate**: Nếu yêu cầu mới mâu thuẫn với spec hiện tại hoặc thiếu tiêu chí cốt lõi → gọi `ask_question` làm rõ trước khi cập nhật. Sau khi ghi file, trả về link file + tóm tắt các điểm mới/đã đổi rồi dừng (không tự chạy code).
