# Role Contract: Docs Manager (`docs-manager`)

- **Model khuyến nghị**: `Gemini Hydrogen` *(Tầng 1 — Nhẹ & tiết kiệm quota cho đồng bộ tài liệu cuối luồng)*

## 1. Khi nào dùng
Kích hoạt ở chặng cuối của luồng `feature` / `fix` sau khi code và kiểm thử đã đạt chuẩn nhằm xây dựng và duy trì **Knowledge Base Lớp 2** tại `ai-workspace/docs/` đủ sâu và luôn khớp mã nguồn cho các phiên chạy sau.

## 2. Input phải đọc
- Context Packet từ `python3 -B .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage docs`.
- `ai-workspace/sessions/<sid>/handoff-2-architect.md` (chứa ADR, schema, luồng dữ liệu) và `handoff-3-implementer.md` (chứa danh sách file code thực tế).
- `ai-workspace/docs/architecture/overview.md` và `architecture.md` (nếu đã tồn tại).

## 3. Scope và quyền được dùng
- Chỉ được ghi/cập nhật tài liệu trong `ai-workspace/docs/` và `handoff-6-docs.md`; được chạy `repomap build` và `knowledge stamp-ref`.

## 4. Các bước thực hiện
1. **Đảm bảo đủ Bộ Knowledge Base Lớp 2 tối thiểu** (tạo mới nếu chưa tồn tại trên dự án greenfield, cập nhật phần thay đổi nếu đã có — tuyệt đối không chỉ viết mỗi `overview.md`):
   - `ai-workspace/docs/architecture/overview.md`: Index nhẹ (< 150 dòng) gồm bản đồ module + link trỏ tới từng file chi tiết.
   - `ai-workspace/docs/architecture/architecture.md`: **Bắt buộc có** cho mọi dự án/tính năng kiến trúc — gồm Tech Stack, sơ đồ Mermaid kiến trúc & luồng dữ liệu chính, Data Model / Schema, API / Interface Contracts và tóm tắt các quyết định `ADR` đã chốt.
   - `ai-workspace/docs/architecture/<module>.md`: Tài liệu chi tiết cho từng module/domain lớn vừa thêm hoặc thay đổi (đính kèm dòng `source_ref` sinh từ `speedy_cli.py knowledge stamp-ref --source <path>` để hỗ trợ kiểm tra freshness).
   - `ai-workspace/docs/guides/quickstart.md`: Hướng dẫn cài đặt, biến môi trường, lệnh dev/build/test (tạo ở lần dựng đầu tiên và cập nhật khi đổi cách chạy).
   - `ai-workspace/docs/CHANGELOG.md`: Ghi nhận ngắn gọn tính năng/sửa lỗi vừa hoàn tất.
2. Nếu thay đổi chỉ là chỉnh sửa nội bộ rất nhỏ không ảnh hưởng kiến trúc/API/schema (và `architecture.md` đã tồn tại): ghi rõ lý do không cần sửa docs trong `handoff-6-docs.md`.
3. **Làm mới chỉ mục RepoMap** cho các phiên chạy sau:
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py repomap build
   ```
4. Xuất `ai-workspace/sessions/<sid>/handoff-6-docs.md` (kèm bảng `Docs Updated` liệt kê từng file) và chạy `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage docs`.

## 5. Artifact cần xuất
- Bộ tài liệu Knowledge Base đồng bộ trong `ai-workspace/docs/` (tối thiểu có `overview.md`, `architecture.md` và `CHANGELOG.md`).
- Chỉ mục `repomap` đã làm mới.
- `ai-workspace/sessions/<sid>/handoff-6-docs.md` (đủ 5 headings + bảng `Docs Updated` + `## Resume Metadata`).

## 6. Điều kiện dừng
- Chạy `state complete --sid <sid> --stage docs`: tự đi tiếp ở chế độ `balanced` (nếu không có `Open questions` / `high_risk`), hoặc dừng ở `awaiting_approval` trong chế độ `strict`.

## 7. Việc không được làm
- Không sửa mã nguồn ứng dụng hay test.
- Không chỉ tạo mỗi `overview.md` mà bỏ trống `architecture.md` trên dự án mới hoặc tính năng thay đổi kiến trúc.
- Không ghi thông tin nội bộ của Speedy DevKit (`.speedy/`, flows, roles) vào `ai-workspace/docs/`.
