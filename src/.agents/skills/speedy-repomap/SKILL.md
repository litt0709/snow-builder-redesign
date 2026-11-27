---
name: speedy-repomap
description: >-
  Sinh chỉ mục và truy vấn nhanh top-N module liên quan theo từ khóa để định vị mã nguồn tiết kiệm token. Kích hoạt khi gọi /repomap.
---

# Speedy RepoMap (`/repomap`)

1. Đọc hướng dẫn tại [.speedy/commands/repomap.md](../../../.speedy/commands/repomap.md).
2. Chạy truy vấn định vị module:
   ```bash
   python3 .speedy/scripts/speedy_cli.py repomap query "<từ khóa>" --limit 5
   ```
3. Trình bày danh sách module, entry point và đường dẫn tài liệu liên quan mà không đọc toàn bộ file `repomap.json`.
