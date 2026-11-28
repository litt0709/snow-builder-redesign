---
name: specs
description: "Tạo mới hoặc cập nhật lặp lại tài liệu đặc tả thiết kế theo từng Phase/Version tại ai-workspace/specs/ với INDEX.md (Active Spec Pointer) và Anti-Spam Split Guard chống tách file rác liên tục. Kích hoạt khi gọi /specs."
---

# Speedy Specs (`/specs`)

1. Đọc [.speedy/commands/specs.md](../../../.speedy/commands/specs.md) và hợp đồng vai trò tại [.speedy/roles/specs.md](../../../.speedy/roles/specs.md) (khuyến nghị **Gemini Neon**).
2. Kiểm tra `ai-workspace/specs/INDEX.md` (SSOT trỏ đúng 1 **Active Spec** duy nhất dạng `01-v1-<slug>.md`, `02-v2-<slug>.md`...):
   - **Mặc định**: Đọc và **cập nhật/hợp nhất** vào `Active Spec` hiện tại, tăng minor version (`v1.0` → `v1.1`).
   - **Anti-Spam Split Guard**: Chỉ tách sang file Phase/Version mới khi thực sự bắt đầu Phase/Version mới khác với Active hiện tại; **tuyệt đối không** tách file mới khi người dùng chỉ nhắc lại *"phase mới"* / *"bản mới"* để bổ sung tiếp cho Active Spec đang mở (`Draft`/`Active`). Nếu nằm vùng ranh giới mơ hồ → hỏi đúng 1 câu qua `ask_question`.
   - Khi tách sang file mới: đóng file cũ (`Status: Completed/Frozen`), ghi 3–5 dòng **`Kế thừa từ Phase trước`** đầu file mới, và cập nhật `Active Spec` trong `ai-workspace/specs/INDEX.md`.
3. Trình bày theo cấu trúc 6 phần mạch lạc (`1. Tổng quan`, `2. Goal`, `3. Mission`, `4. Các Step thực hiện`, `5. Trade-off & Pitfall`, `6. Tài liệu tham khảo`) + `Lịch sử Cập nhật`; ưu tiên bảng/bullet ngắn gọn cho cả người đọc và LLM.
4. Không sửa mã nguồn ứng dụng; gửi link file spec kèm tóm tắt nội dung vừa thêm/sửa rồi dừng lại.
