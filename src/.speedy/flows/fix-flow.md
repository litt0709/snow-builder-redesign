# Fix Flow — Truy Nguyên Nguyên Nhân Gốc & Kiểm Thử Hồi Quy

Áp dụng khi `FLOW_MODE = fix`. Thực hiện bước Pre-flight tái hiện lỗi trước khi đi vào pipeline kiểm soát chặt của `feature-flow.md`.

---

## Bước 0.4 — Fix Pre-flight & Tái Hiện Lỗi (`root_cause` · `Gemini Neon`)

1. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage root_cause --status running`.
2. Nếu tồn tại `ai-workspace/state/issues.json`, kiểm tra xem lỗi này có trùng lặp hoặc liên quan tới issue đã ghi nhận trước đó không.
3. Dùng `speedy_cli.py repomap query "<từ khóa lỗi>"` để khoanh vùng module phát sinh lỗi, đọc mã nguồn và **tái hiện lỗi thực tế** (hoặc xác định điều kiện Fail-to-Pass cụ thể).
4. Khởi tạo và điền đầy đủ `ai-workspace/sessions/<sid>/root-cause.md`:
   - Vị trí phát sinh lỗi (`path:line`).
   - Điều kiện và lệnh tái hiện lỗi (chứng minh trạng thái lỗi trước khi sửa).
   - Phân tích nguyên nhân gốc rễ (Root Cause), tránh vá tạm phần ngọn.
5. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage root_cause --status approved` (tự động validate `root-cause.md`).

---

## Chuyển Tiếp Vào Pipeline Chính

- Tiếp tục nạp và thực thi `.speedy/flows/feature-flow.md` từ **Bước 1 (Analyst)** trở đi:
  - **Analyst**: Đọc `root-cause.md` để khóa phạm vi bản vá hẹp nhất, không mở rộng sang refactor ngoài lề.
  - **Tester**: Bắt buộc có bài kiểm thử hồi quy (**Fail-to-Pass**) cho lỗi vừa sửa cùng bộ kiểm thử hiện hữu (**Pass-to-Pass**).
