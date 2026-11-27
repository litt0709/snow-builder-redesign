---
name: flow
description: "Chạy quy trình AI-DD đầy đủ (feature, fix, simple, verify, setup) theo chế độ Balanced Smart HITL, tối ưu tốc độ & token với Handoff Contract và Verification Gate. Kích hoạt khi gọi /flow."
---

# Speedy Flow (`/flow`)

1. Đọc `AGENTS.md` (nếu chưa đọc trong phiên) và nạp [.speedy/roles/orchestrator.md](../../../.speedy/roles/orchestrator.md) (khuyến nghị **Gemini Hydrogen**).
2. **Khởi tạo 1 bước**: Chạy thẳng `python3 -B .speedy/scripts/speedy_cli.py session new --slug "<slug>" --goal "<yêu cầu>" --command-ref /flow` *(tự phân loại `mode`, `high_risk`, model tier và tạo plan/state — không cần gọi riêng lệnh `intent`)*, hoặc `session resume --sid <sid>`.
3. Chỉ đọc **đúng 1 file kịch bản** `.speedy/flows/<mode>-flow.md` (và với dự án Web chưa có `selected_theme`, chọn theme trong `.speedy/docs/themes/`).
4. **Vòng lặp Stage tốc độ cao**:
   - Batch song song các lượt đọc/ghi độc lập; chỉ chạy targeted test cục bộ khi đang code.
   - Sau khi ghi handoff, chạy đúng **1 lệnh gộp**: `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>`.
   - Chỉ gọi `ask_question` + `gate approve|reject|abort --actor human` khi `requires_human_approval == true` (có `Open questions`, `high_risk`, `REQUEST_CHANGES`, xung đột/release, hoặc `--policy strict`).
5. **Wrap-up (1 lần verify duy nhất)**: Chạy `python3 -B .speedy/scripts/speedy_cli.py verify run --sid <sid>` → đóng phiên `state transition --stage wrapup --status approved` → `audit finalize` và báo cáo trung thực.
