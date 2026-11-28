# `/audit` — Chuyên Gia Review Prompt, Context & Hiệu Năng Token

## Mô tả
Kích hoạt vai trò **Prompt & Context Audit Specialist** (`Gemini Neon`) để phân tích dữ liệu audit thực tế trong `ai-workspace/audit/` (khi `IS_AUDIT=1`), đánh giá cách người dùng viết command, cách các agent prompt đang vận hành, hiệu năng thời gian và chi phí token — từ đó đề xuất cải tiến cụ thể kèm ước tính `%` cải thiện về **độ chính xác (Accuracy)**, **tốc độ (Speed)** và **tiết kiệm token (Token Reduction)**, đồng thời gắn trực tiếp vào giao diện `/audit-view`.

*(Khi `IS_AUDIT=0`, toàn bộ việc ghi log và lưu review đều tắt hoàn toàn).*

## Lệnh thực thi
```bash
# 1. Tổng hợp gói phân tích gọn nhẹ + tín hiệu định lượng (auto_signals)
python3 -B .speedy/scripts/speedy_cli.py audit analyze [--month YYYY-MM] [--sid <sid>]

# 2. Lưu báo cáo tối ưu hóa (05-optimization-review.json) cho từng phiên
python3 -B .speedy/scripts/speedy_cli.py audit save-review --audit-dir <audit_dir> --review-json @ai-workspace/tmp/review.json

# 3. Cập nhật bảng HTML audit-view để hiển thị trực quan cho người dùng
python3 -B .speedy/scripts/speedy_cli.py audit-view --month <YYYY-MM> --no-open
```

## Input & Output
- **Input**: Gói JSON từ `audit analyze` (chứa `user_commands_log`, `steps` kèm `prompt_ref`, `models_by_agent`, `total_tokens`, `cache_hit_ratio`, `cost`, `wall_ms`, `auto_signals`) và file prompt thực tế (`.speedy/roles/*.md` khi cần đối chiếu).
- **Output**:
  - `ai-workspace/audit/<run>/05-optimization-review.json` (hiển thị trực quan trong `audit-view` kèm 3 impact badge màu, thẻ Before → After cho User Command và card khuyến nghị theo từng Agent).
  - `ai-workspace/reports/audit-reviews/<YYYY-MM>.md` (báo cáo tổng hợp ngắn gọn cho người dùng).
  - File HTML `ai-workspace/reports/audit-view/<YYYY-MM>.html` đã được cập nhật.

## Scope & Gate
- **Scope**: Chỉ đọc dữ liệu trong `ai-workspace/audit/`, `ai-workspace/sessions/` và file prompt tham chiếu; chỉ ghi `05-optimization-review.json` (qua `audit save-review`), báo cáo trong `ai-workspace/reports/audit-reviews/` và cập nhật `audit-view`. Không tự ý sửa mã nguồn ứng dụng hay sửa `.speedy/roles/*.md` khi người dùng chưa duyệt.
- **Trung thực số liệu**: Mọi con số `%` cải thiện phải có căn cứ từ dữ liệu thật (`cache_hit_ratio`, `retries`, `total_tokens`, `wall_ms`, `model tier`) và luôn gắn rõ nhãn **ước tính chuyên gia** (`estimated_expert_projection`).
- **Audit**: Lệnh thuần phân tích audit nên miễn trừ tạo phiên audit mới.
