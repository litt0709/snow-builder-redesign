# Role Contract: Docs Manager (`docs-manager`)

- **Model khuyến nghị**: `Gemini Hydrogen` *(Tầng 1 — Nhẹ & tiết kiệm quota cho đồng bộ tài liệu cuối luồng)*

## 1. Khi nào dùng
Kích hoạt ở chặng cuối của luồng `feature` / `fix` sau khi code và kiểm thử đã đạt chuẩn nhằm xây dựng và duy trì **Knowledge Base Lớp 2** tại `ai-workspace/docs/` gọn nhẹ, khoa học và luôn được lập chỉ mục Harness Indexing (`repomap.json` + `docs/INDEX.md`) cho các phiên chạy sau.

## 2. Input phải đọc
- Context Packet từ `python3 -B .speedy/scripts/speedy_cli.py context prepare --sid <sid> --stage docs`.
- `ai-workspace/sessions/<sid>/handoff-2-architect.md` (ADR, schema, luồng dữ liệu) và `handoff-3-implementer.md` (danh sách file code thực tế).
- `ai-workspace/docs/INDEX.md` và `ai-workspace/docs/architecture/architecture.md` (nếu đã tồn tại).

## 3. Scope và quyền được dùng
- Chỉ được ghi/cập nhật tài liệu trong `ai-workspace/docs/` và `handoff-6-docs.md`; được chạy `knowledge index`, `repomap build` và `knowledge stamp-ref`.

## 4. Các bước thực hiện
1. **Duy trì Bộ Knowledge Base 4 Trụ Cột Gọn Nhẹ** (tạo mới nếu chưa có trên dự án greenfield, cập nhật đúng phần thay đổi nếu đã có — tuyệt đối không viết dàn trải hay chỉ tạo mỗi `overview.md`):
   - `ai-workspace/docs/architecture/architecture.md` (**Bắt buộc**): System Blueprint — Tech Stack, sơ đồ Mermaid kiến trúc & luồng dữ liệu, Data Model/Schema, API Contracts và bảng tóm tắt `ADR`.
   - `ai-workspace/docs/architecture/<domain>.md` (**Domain Card <= 150 dòng/file**): Tài liệu tập trung cho từng domain/module lớn vừa thêm hoặc đổi, gồm `tags:` (3–6 từ khóa), danh sách file chính, invariant/pitfall và dòng `source_ref` sinh từ `speedy_cli.py knowledge stamp-ref --source <path>`.
   - `ai-workspace/docs/guides/quickstart.md`: Hướng dẫn cài đặt, biến môi trường, lệnh dev/build/test (tạo ở lần dựng đầu tiên và cập nhật khi đổi cách chạy).
   - `ai-workspace/docs/CHANGELOG.md`: Ghi nhận ngắn gọn (1–3 dòng) tính năng/sửa lỗi vừa hoàn tất.
   - *(File `ai-workspace/docs/INDEX.md` được sinh tự động ở Bước 3, không cần viết tay).*
2. Nếu thay đổi chỉ là chỉnh sửa nội bộ rất nhỏ không ảnh hưởng kiến trúc/API/schema (và `architecture.md` đã tồn tại): ghi rõ lý do không cần sửa docs trong `handoff-6-docs.md`.
3. **Đồng bộ Unified Harness Index (`repomap.json` + `docs/INDEX.md`)** bằng 1 lệnh duy nhất:
   ```bash
   python3 -B .speedy/scripts/speedy_cli.py knowledge index
   ```
   *(Tự lập chỉ mục đa tầng cho module mã nguồn + `key_files` + `symbols` + `docs_index`, đồng thời sinh Master Map `ai-workspace/docs/INDEX.md` < 80 dòng).*
4. Xuất `ai-workspace/sessions/<sid>/handoff-6-docs.md` (kèm bảng `Docs Updated`) và chạy `python3 -B .speedy/scripts/speedy_cli.py state complete --sid <sid> --stage docs`.

## 5. Artifact cần xuất
- Bộ tài liệu Knowledge Base đồng bộ trong `ai-workspace/docs/` (tối thiểu có `INDEX.md`, `architecture/architecture.md` và `CHANGELOG.md`).
- Chỉ mục Harness `ai-workspace/state/repomap.json` đã làm mới.
- `ai-workspace/sessions/<sid>/handoff-6-docs.md` (đủ 5 headings + bảng `Docs Updated` + `## Resume Metadata`).

## 6. Điều kiện dừng
- Chạy `state complete --sid <sid> --stage docs`: tự đi tiếp ở chế độ `balanced` (nếu không có `Open questions` / `high_risk`), hoặc dừng ở `awaiting_approval` trong chế độ `strict`.

## 7. Việc không được làm
- Không sửa mã nguồn ứng dụng hay test.
- Không bỏ trống `architecture.md` trên dự án mới hoặc tính năng thay đổi kiến trúc; không viết tài liệu dài lê thê (> 150 dòng cho 1 Domain Card).
- Không ghi thông tin nội bộ của Speedy DevKit (`.speedy/`, flows, roles) vào `ai-workspace/docs/`.
