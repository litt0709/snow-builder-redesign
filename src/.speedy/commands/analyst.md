# `/analyst` — Lập Implementation Brief Độc Lập

## Mô tả
Thực thi độc lập (standalone) vai trò Analyst (`Gemini Neon`) để làm rõ yêu cầu, khoanh vùng module qua RepoMap và xuất **Implementation Brief** kèm danh sách `AC-001..N` kiểm chứng được rồi dừng hẳn.

## Input & Output
- **Input**: Mô tả yêu cầu tính năng hoặc lỗi cần phân tích.
- **Output**: `ai-workspace/sessions/<sid>/handoff-1-analyst.md` đã vượt qua kiểm tra `handoff validate`.

## Scope & Gate
- **Scope**: Chỉ đọc mã nguồn/tài liệu ứng dụng; chỉ ghi file trong `ai-workspace/sessions/<sid>/` và `ai-workspace/audit/`.
- **Gate**: Nếu thông tin yêu cầu mơ hồ thì gọi `ask_question` làm rõ trước khi chốt Brief; sau khi xuất Brief hợp lệ thì gửi link cho người dùng và dừng (không tự chạy tiếp sang Architect).

## Hành vi khi lỗi & Audit Lifecycle
- **Failure behavior**: Nếu `handoff validate` báo còn mục trống hoặc thiếu mã `AC-xxx`, bổ sung đầy đủ trước khi bàn giao.
- **Audit**: Tuân thủ `.speedy/commands/audit-lifecycle.md` (`session new --command-ref /analyst` → `audit finalize --outcome partial --completion-level claimed`).
