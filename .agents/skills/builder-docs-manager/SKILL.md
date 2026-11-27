---
name: builder-docs-manager
description: >-
  Kích hoạt khi đóng vai trò Docs Manager của SNOW Builder để đồng bộ docs/, rules/ và AGENTS.md sau khi hoàn tất thay đổi kiến trúc hoặc mã nguồn.
---

# Builder Docs Manager (`builder-docs-manager`)

- **Model khuyến nghị**: `Gemini Hydrogen`

## Quy trình thực hiện
1. Đọc `sessions/<sid>/handoff-3-implementer.md` để nắm chính xác các thay đổi đã triển khai.
2. Cập nhật đúng phần liên quan trong `docs/OVERVIEW.md`, `docs/ARCHITECTURE.md`, `docs/product/README.md`, `docs/CHANGELOG.md` và `src/ai-workspace/README.md` (tuân thủ DRY, không chép lặp).
3. Kiểm tra `AGENTS.md`, `src/AGENTS.md` và `rules/` luôn khớp 100% với hành vi thực tế của CLI và skills.
4. Xuất `sessions/<sid>/handoff-6-docs.md` và chạy `handoff validate`.
