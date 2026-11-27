---
name: analyst
description: "Phân tích yêu cầu độc lập (standalone), định vị module qua RepoMap và xuất Implementation Brief kèm danh sách AC kiểm chứng được rồi dừng lại. Kích hoạt khi gọi /analyst."
---

# Speedy Analyst (`/analyst`)

1. Đọc [.speedy/commands/analyst.md](../../../.speedy/commands/analyst.md) và hợp đồng vai trò tại [.speedy/roles/analyst.md](../../../.speedy/roles/analyst.md) (khuyến nghị **Gemini Neon**).
2. Khởi tạo session độc lập qua `python3 .speedy/scripts/speedy_cli.py session new --slug "<slug>" --goal "<yêu cầu>" --command-ref /analyst`.
3. Dùng `speedy_cli.py repomap query "<từ khóa>"` để định vị module liên quan trước khi đọc tài liệu hoặc mã nguồn.
4. Điền `handoff-1-analyst.md`, chạy `speedy_cli.py handoff validate --sid <sid> --stage analyst`, finalize audit rồi gửi link cho người dùng và dừng hẳn (không tự chuyển sang Architect).
