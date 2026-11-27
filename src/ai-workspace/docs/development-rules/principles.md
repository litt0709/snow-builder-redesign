# Nguyên Tắc Phát Triển Chung (Baseline Development Principles)

> **Lưu ý**: File này là nền tảng cố định đi kèm bộ khung phát triển. Lệnh `/refresh-rule` không được xóa hoặc ghi đè 5 nguyên tắc gốc bên dưới, chỉ được phép bổ sung quy ước đặc thù có bằng chứng của dự án vào mục **Ghi chú riêng dự án** ở cuối file.

---

## 1. KISS (Keep It Simple, Stupid)
- Ưu tiên giải pháp đơn giản, dễ hiểu và trực tiếp nhất đáp ứng đúng yêu cầu.
- Tránh tạo lớp trừu tượng sớm khi mới chỉ có một trường hợp sử dụng duy nhất.

## 2. YAGNI (You Aren't Gonna Need It)
- Chỉ cài đặt đúng chức năng nằm trong phạm vi đã được phê duyệt.
- Không viết trước cấu hình, tham số dự phòng hay tính năng giả định cho tương lai chưa xác định.

## 3. DRY (Don't Repeat Yourself)
- Mọi quy tắc nghiệp vụ, công thức tính toán hoặc cấu trúc dữ liệu dùng chung phải có một nguồn sự thật duy nhất (Single Source of Truth).
- Không sao chép cùng một khối xử lý sang nhiều nơi gây lệch hành vi khi bảo trì.

## 4. Readability (Tính Dễ Đọc & Minh Bạch)
- Đặt tên hàm, lớp, biến thể hiện rõ ý định nghiệp vụ.
- Mỗi hàm tập trung giải quyết một nhiệm vụ rõ ràng; xử lý lỗi tường minh thay vì nuốt lỗi âm thầm.

## 5. Minimal Scope (Kỷ Luật Phạm Vi Tối Thiểu)
- Chỉ chỉnh sửa những dòng và tập tin thực sự liên quan tới yêu cầu hiện tại.
- Không kết hợp sửa định dạng hàng loạt hoặc tái cấu trúc ngoài phạm vi trong cùng một thay đổi tính năng/sửa lỗi.

---

## Ghi chú riêng dự án
*(Chỉ bổ sung convention có bằng chứng thực tế từ mã nguồn dự án)*
