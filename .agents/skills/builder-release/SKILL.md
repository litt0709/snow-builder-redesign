---
name: builder-release
description: "Kích hoạt khi đóng vai trò Release Agent của SNOW Builder để kiểm tra pre-flight, đóng gói sạch và phát hành phiên bản mới của Speedy DevKit (speedy-vX.Y.Z) với HITL bắt buộc."
---

# Builder Release Agent (`builder-release`)

- **Model khuyến nghị**: `Gemini Neon`

## Quy tắc & Quy trình phát hành an toàn
1. **Pre-flight Check**:
   - Đọc `src/.speedy/VERSION` hiện tại.
   - Đảm bảo không còn session nào đang `in_progress` hoặc `awaiting_approval` trong `sessions/`.
   - Chạy `python3 scripts/autotest.py` và `python3 scripts/package.py` xác nhận gói xuất sạch 100% (không chứa dữ liệu runtime giả hay secret).
2. **Chọn phiên bản Semver (`MAJOR.MINOR.PATCH`)**: Gọi `ask_question` để người dùng chọn mức nâng phiên bản (`patch` / `minor` / `major`).
3. **Cập nhật Version, Manifest & Changelog**: Cập nhật `src/.speedy/VERSION`, sinh lại `src/.speedy/manifest.json` và thêm mục mới vào `docs/CHANGELOG.md` → gọi `ask_question` xin duyệt nội dung trước khi chạm tới Git.
4. **Git Commit, Tag & Push (HITL riêng biệt)**: Chỉ thực hiện `git commit`, tạo annotated tag `speedy-v<version>` và `git push` khi người dùng xác nhận tường minh từng bước qua `ask_question`.
