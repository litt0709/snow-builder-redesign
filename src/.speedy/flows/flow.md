# Flow Router — Bộ Định Tuyến AI-DD

Đọc yêu cầu của người dùng, phân loại `Flow Mode` bằng CLI deterministic và chỉ nạp đúng 1 kịch bản luồng tương ứng.

---

## 1. Bước 0a — Kiểm tra Setup dự án (Lazy Check)

- Nếu `ai-workspace/state/setup.json` đã tồn tại (`status` là `done` hoặc `skipped`) → chuyển sang Bước 0b.
- Nếu dự án mới hoàn toàn (chưa có mã nguồn ứng dụng ngoài `.speedy/`, `.agents/`, `ai-workspace/`) → chuyển sang Bước 0b.
- Nếu dự án đã có mã nguồn nhưng chưa có `setup.json` → nạp `.speedy/flows/setup-flow.md` thực hiện trước khi vào luồng chính.

---

## 2. Bước 0b — Phân loại Intent & Đánh giá Rủi ro (Python-First)

Chạy lệnh deterministic (không đoán cảm tính):

```bash
python3 .speedy/scripts/speedy_cli.py intent "<nội dung yêu cầu>" [--path <file-dự-kiến>]
```

- Nhận kết quả JSON: `intent` (`feature` | `fix` | `simple` | `verify` | `setup`), `route`, `high_risk` và `recommended_models`.
- **Quy tắc an toàn**: Nếu yêu cầu chạm tới `auth`, `payment`, `schema`, `migration`, `security` hoặc nhiều file mã nguồn, CLI tự động chặn lọt vào `simple` và nâng lên `feature` / `fix`.

---

## 3. Bước 0c — Khởi tạo Session & Hiển thị Banner Định tuyến

```bash
python3 .speedy/scripts/speedy_cli.py session new --slug "<slug>" --goal "<yêu cầu>" --mode <intent> --command-ref /flow
```

Hiển thị banner ngắn gọn trước khi bắt đầu stage đầu tiên:

```markdown
🎯 **Flow Mode**: `<MODE>` | **Policy**: `strict` | **Session**: `<sid>`
🗺️ **Route**: `<chuỗi stage từ JSON>`
🤖 **Phân bổ Model**: Orchestrator/Docs (`Gemini Hydrogen`) · Dev/Test (`Gemini Neon`) · Escalation nếu rủi ro cao (`Gemini Carbon`)
```

---

## 3.5. Bước 0d — HITL Gate Chọn Theme Cho Dự Án Web (Lần Đầu Dựng Project)

Chỉ kích hoạt **1 lần duy nhất** khi dựng dự án Web mới (hoặc `ai-workspace/state/setup.json` chưa có trường `selected_theme`) và yêu cầu có giao diện **Web / Frontend / Dashboard / Landing Page**:
1. Quét danh sách các thư mục mẫu trong `.speedy/docs/themes/` (ví dụ `1.default` — *Apple Clean & Glassmorphism · Light + Dark Mode*, và các mẫu mới được bổ sung sau này).
2. Gọi `ask_question` để người dùng chọn mẫu theme mong muốn (kèm tùy chọn *"Tự thiết kế / Không dùng mẫu sẵn"*).
3. Ghi lựa chọn vào `ai-workspace/state/setup.json` (`"selected_theme": "<ten-thu-muc>"` hoặc `"custom"`).
4. Truyền đường dẫn `.speedy/docs/themes/<selected_theme>/` cho `Architect` và `Implementer` để đảm bảo giao diện hỗ trợ nhất quán cả **Light Mode** và **Dark Mode**.

---

## 4. Nạp Kịch Bản Theo Mode (Không Preload Toàn Bộ)

| Mode | File kịch bản duy nhất cần đọc |
|---|---|
| `setup` | `.speedy/flows/setup-flow.md` |
| `feature` | `.speedy/flows/feature-flow.md` |
| `fix` | `.speedy/flows/fix-flow.md` |
| `simple` | `.speedy/flows/simple-flow.md` |
| `verify` | `.speedy/flows/verify-flow.md` |

---

## 5. Quy Ước Stage Gate Chuẩn Trên Antigravity IDE

Trước mọi cổng phê duyệt (`strict` mặc định):
1. Ghi file handoff vào `ai-workspace/sessions/<sid>/`.
2. Chạy `python3 .speedy/scripts/speedy_cli.py state transition --sid <sid> --stage <stage> --status awaiting_approval` (tự động chạy Deep Handoff Validator).
3. Gửi thông báo ngắn kèm Markdown link tới file artifact để người dùng bấm mở xem.
4. Gọi công cụ `ask_question` với 3 lựa chọn: `(Recommended) Approve — Tiếp tục` / `Request Changes — Chỉnh sửa lại` / `Abort — Dừng phiên`.
5. Ghi nhận quyết định thực tế của người dùng qua `python3 .speedy/scripts/speedy_cli.py gate approve|reject|abort --sid <sid> --stage <stage> --actor human --interaction-ref <mã-lượt-hỏi>`.
