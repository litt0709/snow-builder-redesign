---
name: audit
description: "Đóng vai chuyên gia Prompt & Context Engineering rà soát các user command, agent prompt, hiệu năng và chi phí token từ dữ liệu audit để đề xuất tối ưu kèm ước tính % cải thiện và đồng bộ lên audit-view. Kích hoạt khi gọi /audit."
---

# Speedy Audit Advisor (`/audit`)

1. Đọc [.speedy/commands/audit.md](../../../.speedy/commands/audit.md) và hợp đồng vai trò tại [.speedy/roles/audit.md](../../../.speedy/roles/audit.md) (khuyến nghị **Gemini Neon**).
2. Chạy lệnh tổng hợp dữ liệu (Python-first, tiết kiệm token):
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py audit analyze [--month YYYY-MM] [--sid <sid>]
   ```
   *(Nếu `enabled == false` do `IS_AUDIT=0` hoặc `runs_count == 0` → báo rõ người dùng và dừng lại).*
3. Đóng vai **Principal Prompt & Context Engineering Specialist**, phân tích các `user_commands_log`, `steps` (`prompt_ref`, `model`, `duration_ms`), `total_tokens`, `cache_hit_ratio`, `cost` và `auto_signals` để đưa ra khuyến nghị cụ thể (Before → After cho User Command; điểm nghẽn & đề xuất cho từng Agent Prompt) kèm ước tính `%` cải thiện (`accuracy_gain_pct`, `speed_gain_pct`, `token_reduction_pct`).
4. Lưu kết quả chuẩn hóa vào từng phiên qua `python3 -B .speedy/scripts/speedy_cli.py audit save-review --audit-dir <audit_dir> --review-json <json-hoặc-@file>`, xuất tóm tắt tại `ai-workspace/reports/audit-reviews/<YYYY-MM>.md`, và chạy `python3 -B .speedy/scripts/speedy_cli.py audit-view --month <YYYY-MM> --no-open` để cập nhật ngay bảng HTML.
