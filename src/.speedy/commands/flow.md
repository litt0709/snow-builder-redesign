# `/flow` (`speedy-flow`) — Điều Phối Chu Trình AI-DD Đầy Đủ

## Mô tả
Điểm vào chính để triển khai mọi tác vụ phần mềm (`feature`, `fix`, `simple`, `verify`, `setup`) với cơ chế định tuyến theo rủi ro, Context Packet tiết kiệm token và kiểm soát cổng phê duyệt nghiêm ngặt trên Antigravity IDE.

## Input & Output
- **Input**: Yêu cầu bằng ngôn ngữ tự nhiên (hoặc `--sid <SID>` khi tiếp tục phiên cũ).
- **Output**:
  - `ai-workspace/sessions/<sid>/state.json`, `state.md` và chuỗi file `handoff-*.md`.
  - Bằng chứng kiểm thử trong `ai-workspace/sessions/<sid>/evidence/`.
  - Báo cáo tổng kết trong `ai-workspace/logs/tasks/` và 4 file JSON trong `ai-workspace/audit/`.

## Scope & Gate
- **Scope**: Mã nguồn ứng dụng nằm trong `allowed_paths` đã được duyệt ở Brief/Design; bộ nhớ vận hành ghi vào `ai-workspace/`.
- **Gate**: Mặc định `strict` — dùng công cụ `ask_question` xin phép người dùng sau mỗi stage chuyên môn trước khi gọi `speedy_cli.py gate approve --actor human`.

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Lỗi hợp đồng handoff hoặc lỗi kiểm thử giữ nguyên trạng thái trung thực, phân loại lỗi và retry có giới hạn tối đa 3 attempts trên mỗi UoW; chạm trần hoặc lặp lỗi cũ (Doom-Loop) thì dừng báo blocker.
- **Audit**: Tự động khởi tạo lúc `session new` và đóng tại bước Wrap-up qua `speedy_cli.py audit finalize`.
