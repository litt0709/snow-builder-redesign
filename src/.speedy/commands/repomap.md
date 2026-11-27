# `/repomap` — Định Vị Nhanh Module Mã Nguồn

## Mô tả
Xây dựng và truy vấn chỉ mục cấp module để trả lời câu hỏi **WHERE — mã nguồn liên quan nằm ở đâu** chỉ với vài trăm byte JSON, tránh quét toàn bộ dự án gây tốn token.

## Lệnh thực thi
```bash
# Sinh hoặc làm mới chỉ mục (có cache tự động theo cấu trúc thư mục)
python3 .speedy/scripts/speedy_cli.py repomap build [--root .] [--no-cache]

# Truy vấn top-N module phù hợp nhất (mặc định 5, tối đa 20)
python3 .speedy/scripts/speedy_cli.py repomap query "<từ khóa>" [--limit 5]
```

## Quy Tắc Sử Dụng Cho Agent
1. Luôn chạy `repomap query` trước khi tìm kiếm trong mã nguồn; **không đọc trực tiếp toàn bộ file `repomap.json`**.
2. Nếu module khớp có trường `docs` khác rỗng → đọc file tài liệu đó trước (**WHAT**).
3. Chỉ tìm kiếm và đọc mã nguồn bên trong các thư mục `path` được trả về.
4. Khi `matches: []`, thử thu hẹp/đổi từ khóa đồng nghĩa thay vì tự bịa đường dẫn module.
