# HITL Gate Template — Chuẩn Phê Duyệt Trên Antigravity IDE

Nguồn quy chuẩn cho mọi cổng phê duyệt của con người (Human-in-the-Loop) trong Speedy DevKit.

---

## 1. Trình Tự 4 Bước Bắt Buộc Tại Mỗi Stage Gate

1. **Ghi & Validate Artifact**:
   ```bash
   python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage <stage> --status awaiting_approval
   ```
2. **Hiển Thị Thông Báo Link Artifact**:
   Gửi ngắn gọn (1–3 dòng) kèm link tới file handoff vừa tạo để người dùng mở kiểm tra trực tiếp trên Antigravity IDE.
3. **Gọi Công Cụ `ask_question`**:
   - Câu hỏi ngắn gọn nêu rõ tên stage, phạm vi tác động, rủi ro chính và bước tiếp theo.
   - Các phương án lựa chọn chuẩn:
     - `(Recommended) Approve — Phê duyệt và chuyển sang bước tiếp theo`
     - `Request Changes — Yêu cầu chỉnh sửa lại bước hiện tại`
     - `Abort — Dừng phiên làm việc`
   *(Fallback: nếu môi trường CLI thu gọn không hiển thị hộp thoại `ask_question`, đặt câu hỏi rõ ràng trong tin nhắn chat và dừng chờ người dùng gõ câu trả lời xác nhận).*
4. **Ghi Nhận Vào Canonical State**:
   ```bash
   python3 .speedy/scripts/speedy_cli.py gate approve|reject|abort \
     --sid <sid> --stage <stage> \
     --actor human --interaction-ref "ask_question:<stage>" \
     [--feedback "<ghi chú của người dùng>"]
   ```
