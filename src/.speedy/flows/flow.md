# Flow Router — Bộ Định Tuyến AI-DD

Đọc yêu cầu của người dùng, phân loại `Flow Mode` bằng CLI deterministic và chỉ nạp đúng 1 kịch bản luồng tương ứng.

---

## 1. Bước 0a — Kiểm tra Setup, Rules & Style dự án (Lazy Check)

- **Dự án đã có mã nguồn (Brownfield)**:
  - Nếu chưa có `ai-workspace/state/setup.json` → nạp `.speedy/flows/setup-flow.md` (tự động chạy `scan`, `repomap build`, `/docs` nền, **`/refresh-rule`** và **`/refresh-style`** để nắm đúng convention & code style của các kỹ sư cũ).
  - Nếu `setup.json` đã có (`status == "done"`) nhưng chưa có `ai-workspace/docs/development-rules/coding-convention.md` hoặc `ai-workspace/docs/development-style/STYLE.md` → chạy bổ sung 1 lần `/refresh-rule` & `/refresh-style` (chế độ Brownfield).
- **Dự án mới hoàn toàn (Greenfield)**:
  - Chuyển thẳng sang Bước 0b; ngay sau khi `Architect` chốt Tech Stack/Framework (cuối Bước 2 của `feature-flow.md`), luồng sẽ tự động chạy 1 lần `/refresh-rule` & `/refresh-style` (chế độ Greenfield — `search_web` chuẩn Principal Engineer cho các framework đã chọn) trước khi `Implementer` viết dòng code đầu tiên.

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
🎯 **Flow Mode**: `<MODE>` | **Policy**: `<balanced|strict>` | **Session**: `<sid>`
🗺️ **Route**: `<chuỗi stage từ JSON>`
🤖 **Phân bổ Model**: Orchestrator/Docs (`Gemini Hydrogen`) · Dev/Test (`Gemini Neon`) · Escalation nếu rủi ro cao (`Gemini Carbon`)
```

---

## 3.5. Bước 0d — HITL Gate Chọn Theme Cho Dự Án Web (Lần Đầu Dựng Project)

Chỉ kích hoạt **1 lần duy nhất** khi dựng dự án Web mới (hoặc `ai-workspace/state/setup.json` chưa có trường `selected_theme`) và yêu cầu có giao diện **Web / Frontend / Dashboard / Landing Page**:
1. Quét danh sách các thư mục mẫu trong `.speedy/docs/themes/` (ví dụ `1.default` — *Sky Clean*, `2.tabler` — *Tabler Enterprise*, `3.midnight` — *Midnight Pro*, `4.apple` — *Apple Minimalist*, và các mẫu mới được bổ sung sau này).
2. Gọi `ask_question` để người dùng chọn mẫu theme mong muốn (kèm tùy chọn *"Tự thiết kế / Không dùng mẫu sẵn"*).
3. Ghi lựa chọn vào `ai-workspace/state/setup.json` (`"selected_theme": "<ten-thu-muc>"` hoặc `"custom"`).
4. Truyền `.speedy/docs/themes/README.md` (quy tắc Typography, Spacing, Brand Logo & Favicon bắt buộc) cùng `.speedy/docs/themes/<selected_theme>/` (nếu chọn mẫu) cho `Architect` và `Implementer` để đảm bảo giao diện nhất quán cả **Light Mode**, **Dark Mode** và đầy đủ **Brand Logo + Favicon**.

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

## 5. Quy Ước Stage Gate Chuẩn (`balanced` Mặc Định vs `strict`)

Cuối mỗi stage chuyên môn:
1. Ghi file handoff vào `ai-workspace/sessions/<sid>/`.
2. Chạy **1 lệnh gộp duy nhất**:
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage <stage>
   ```
   *(Tự động chuyển `running`, chạy Deep Handoff Validator, và chuyển `approved` ngay nếu đạt chuẩn ở chế độ `balanced`; chỉ dừng `awaiting_approval` khi `requires_human_approval == true`)*.
3. **Chỉ khi `requires_human_approval == true`** (có `Open questions`, `high_risk`, `REQUEST_CHANGES`, hoặc chạy `--policy strict`):
   - Gửi thông báo ngắn kèm Markdown link tới file artifact.
   - Gọi `ask_question` (`(Recommended) Approve — Tiếp tục` / `Request Changes — Chỉnh sửa lại` / `Abort — Dừng phiên`).
   - Ghi nhận quyết định qua `python3 -B .speedy/scripts/speedy_cli.py gate approve|reject|abort --sid <sid> --stage <stage> --actor human --interaction-ref <mã-lượt-hỏi>`.
