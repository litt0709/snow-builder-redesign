---
trigger: glob
globs: "ai-workspace/sessions/**"
description: "Quy ước bảo toàn dữ liệu khi thao tác trong ai-workspace/sessions/."
---

# Quy tắc Session Artifacts

- `state.json` là nguồn trạng thái canonical duy nhất, chỉ cập nhật qua `python3 .speedy/scripts/speedy_cli.py` (`state` / `gate`); `state.md` được sinh tự động từ `state.json`.
- Mọi file handoff (`handoff-1-analyst.md` .. `handoff-6-docs.md`) bắt buộc có đủ 5 headings nội dung (`## Summary`, `## Scope`, `## Risks`, `## Dependencies`, `## Open questions`) và khối JSON `## Resume Metadata`.
- Không tự ý xóa lịch sử handoff hoặc file bằng chứng trong `evidence/`.
