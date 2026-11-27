---
name: specs
description: "Tạo mới hoặc cập nhật lặp lại tài liệu đặc tả thiết kế khoa học, dễ đọc cho cả người và LLM tại ai-workspace/specs/ (gồm Tổng quan, Goal, Mission, Các Step thực hiện, Trade-off & Pitfall, Tài liệu tham khảo). Kích hoạt khi gọi /specs."
---

# Speedy Specs (`/specs`)

1. Đọc [.speedy/commands/specs.md](../../../.speedy/commands/specs.md) và hợp đồng vai trò tại [.speedy/roles/specs.md](../../../.speedy/roles/specs.md) (khuyến nghị **Gemini Neon**).
2. Kiểm tra thư mục `ai-workspace/specs/`:
   - Nếu đã có file spec phù hợp: đọc toàn bộ nội dung hiện tại để **cập nhật/hợp nhất** bảo toàn các yêu cầu đã chốt và tăng `Version`.
   - Nếu chưa có: tạo mới file `ai-workspace/specs/<slug>.md` (`v1.0`).
   - Nếu mơ hồ giữa cập nhật file cũ hay tạo mới, hoặc yêu cầu mâu thuẫn với bản cũ: gọi `ask_question` làm rõ ngắn gọn trước khi ghi.
3. Trình bày theo cấu trúc 6 phần mạch lạc (`1. Tổng quan`, `2. Goal`, `3. Mission`, `4. Các Step thực hiện`, `5. Trade-off & Pitfall`, `6. Tài liệu tham khảo`) + `Lịch sử Cập nhật`; ưu tiên bảng/bullet ngắn gọn, dễ nắm bắt cho cả người đọc và LLM.
4. Không sửa mã nguồn ứng dụng; gửi link file spec kèm tóm tắt nội dung vừa thêm/sửa rồi dừng lại.
