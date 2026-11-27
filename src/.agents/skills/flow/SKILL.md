---
name: flow
description: "Chạy quy trình AI-DD đầy đủ (feature, fix, simple, verify, setup) với Handoff Contract, Context Packet tiết kiệm token và kiểm soát Stage Gate nghiêm ngặt. Kích hoạt khi người dùng gọi /flow hoặc yêu cầu triển khai task theo quy trình Speedy."
---

# Speedy Flow (`/flow`)

1. Đọc `AGENTS.md` và `.speedy/commands/flow.md`.
2. Nạp hợp đồng điều phối tại [.speedy/roles/orchestrator.md](../../../.speedy/roles/orchestrator.md) (khuyến nghị dùng **Gemini Hydrogen** cho điều phối).
3. Chạy `python3 .speedy/scripts/speedy_cli.py intent "<yêu cầu>"` để phân loại `mode` và đánh giá tín hiệu rủi ro; khởi tạo session bằng `session new` hoặc tiếp tục bằng `session resume --sid <sid>`.
4. Chỉ đọc đúng một file luồng tại `.speedy/flows/<mode>-flow.md` (không nạp trước toàn bộ các file flow khác).
5. Ở mỗi stage: gọi `context prepare`, thực thi theo `.speedy/roles/<role>.md`, chạy `state transition --status awaiting_approval`, hiển thị link artifact và gọi `ask_question` xin phép người dùng trước khi `gate approve --actor human`.
6. Kết thúc bằng bằng chứng kiểm thử từ `speedy_cli.py verify run` và báo cáo audit trung thực.
