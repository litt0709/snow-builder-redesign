# `/repomap` — Unified Harness Indexing (Định Vị Siêu Nhanh WHERE & WHAT)

## Mô tả
Xây dựng và truy vấn **Unified Harness Index** (`ai-workspace/state/repomap.json`) gồm bản đồ module đa tầng (`src/`, `web/src/`, `functions/src/`, `services/`...), `key_files`, public `symbols` và `docs_index` — trả lời đồng thời **WHAT (tài liệu nào)** và **WHERE (file/symbol nào)** chỉ với vài trăm byte JSON, không quét toàn repo gây tốn token.

## Lệnh thực thi
```bash
# 1. Đồng bộ Unified Harness Index + tự sinh Master Map ai-workspace/docs/INDEX.md
python3 -B .speedy/scripts/speedy_cli.py knowledge index

# 2. Truy vấn hợp nhất cả Tài liệu (doc_matches) & Mã nguồn (code_matches kèm matched_files/matched_symbols)
python3 -B .speedy/scripts/speedy_cli.py knowledge query "<từ khóa>" [--limit 5]

# (Hoặc dùng trực tiếp repomap build / repomap query)
python3 -B .speedy/scripts/speedy_cli.py repomap build [--root .] [--no-cache]
python3 -B .speedy/scripts/speedy_cli.py repomap query "<từ khóa>" [--limit 5]
```

## Quy Tắc Sử Dụng Cho Agent (Tiết Kiệm Token Tối Đa)
1. Luôn chạy `knowledge query` (hoặc `repomap query`) trước khi tìm kiếm trong mã nguồn; **không đọc trực tiếp toàn bộ `repomap.json`**.
2. Đọc `doc_matches` (hoặc `ai-workspace/docs/INDEX.md`) trước để nắm **WHAT**.
3. Mở thẳng `matched_files` / `matched_symbols` trong các thư mục `path` trả về (**WHERE**) thay vì duyệt toàn dự án.
4. Khi `matches: []`, thử từ khóa ngắn hơn hoặc chạy `knowledge index` để làm mới chỉ mục.
