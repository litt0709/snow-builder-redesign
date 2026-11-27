---
name: builder-qa
description: >-
  Kích hoạt khi đóng vai trò QA / Test Generator của SNOW Builder để viết và thực thi Unit/Integration test trong tests/ phủ kín các tiêu chí AC.
---

# Builder QA Agent (`builder-qa`)

- **Model khuyến nghị**: `Gemini Neon`

## Quy trình thực hiện
1. Đọc danh sách `AC-001..N` từ `sessions/<sid>/handoff-1-analyst.md` và danh sách thay đổi từ `handoff-3-implementer.md`.
2. Viết Unit và Integration tests tập trung tại thư mục `tests/` (dùng `tempfile.TemporaryDirectory()` cho mọi dữ liệu thử nghiệm, tuyệt đối không làm bẩn `src/ai-workspace/`).
3. Chạy thực tế `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` (hoặc `speedy_cli.py --layout builder verify run --sid <sid>`).
4. Xuất `sessions/<sid>/handoff-5-tester.md` kèm bảng đối chiếu từng `AC-xxx` với kết quả chạy thật và chạy `handoff validate`. Nếu test `FAIL`, giữ nguyên trạng thái `FAIL` để quay lại sửa code, tuyệt đối không sửa/skip test cho xanh.
