# Báo Cáo Đánh Giá Chuyên Gia Độc Lập — SNOW Builder & Speedy DevKit v2.0

- **Ngày kiểm định**: `2026-11-27`
- **Vai trò đánh giá**: Independent System Reviewer (Subagent tách biệt ngữ cảnh — `conversationId: b7548210-f2cf-46c8-9934-432e871d382f`)
- **Mức độ khắt khe**: `11/20 (Demanding)`
- **Phạm vi**: Toàn bộ SNOW Builder root, sản phẩm `src/` (`Speedy DevKit v2.0.0`), 20 module Python stdlib-only, bộ tài liệu/skills/rules Antigravity và 33 kịch bản kiểm thử.

---

## 1. Tổng Kết Kết Quả Qua 2 Vòng Đánh Giá

| Vòng | Verdict | Điểm Tổng | Phân loại lỗi | Kết quả kiểm thử |
|---|---|---|---|---|
| **Vòng 1 (Pre-fix)** | `REQUEST_CHANGES` | `7.5 / 10` *(score-locked do 2 lỗi HIGH)* | `0 CRITICAL · 2 HIGH · 5 MEDIUM · 2 LOW` | 32/32 tests PASS |
| **Vòng 2 (Re-Review)** | **`APPROVE`** | **`9.2 / 10`** *(Kiến trúc & Harness: `9.3/10` · WOW Factor: `9.0/10`)* | **`0 CRITICAL · 0 HIGH · 0 MEDIUM · 0 LOW`** | **33/33 tests PASS · `manifest.json` 100/100 SHA-256** |

---

## 2. Chi Tiết 9 Phát Hiện & Xác Nhận Khắc Phục (`H-01` → `L-02`)

| Mã | Mức độ | Vấn đề phát hiện ở Vòng 1 | Bản vá đã xác minh ở Vòng 2 | Trạng thái |
|---|---|---|---|---|
| `H-01` | HIGH | `wrapup -> approved` chỉ kiểm tra danh sách `verification` không rỗng, có thể lọt khi `overall_status` là `FAIL`/`PARTIAL_ENV_ONLY` hoặc mã nguồn bị sửa sau khi verify. | `lifecycle.py` cưỡng chế `latest.overall_status == "PASS"` và khớp `snapshot_id` hiện tại; `verification.py` đồng bộ `focus_paths=allowed_paths`. | **VERIFIED FIXED** |
| `H-02` | HIGH | `gate approve` trên `reviewer` chặn `REQUEST_CHANGES` cả ở `verify` mode (gây deadlock) và dùng chuỗi tìm `"APPROVE"` dễ bị đánh lừa bởi văn xuôi. | `handoff.py` thêm `extract_reviewer_verdict` bắt dòng `Verdict:` tường minh; `lifecycle.py` chỉ chặn `REQUEST_CHANGES` khi `mode in {"feature", "fix"}`. | **VERIFIED FIXED** |
| `M-01` | MEDIUM | `antigravity-hooks.example.json` thiếu matcher `read_file`/`write_to_file`/`replace_file_content`/`multi_replace_file_content` và cố định đường dẫn `../.speedy/...`. | Cập nhật matcher đầy đủ, lệnh shell tự phân giải đường dẫn từ cả `.agents/` lẫn workspace root; `hook_guard.py` kiểm tra thêm `AbsolutePath`. | **VERIFIED FIXED** |
| `M-02` | MEDIUM | `register_worker_uow` chưa có API đóng UoW, gây cạn `max_parallel_workers=2` sau 2 lần gọi. | Thêm `complete_worker_uow` (`state uow --status completed|failed`) và tự giải phóng UoW đang chạy khi stage hoàn tất. | **VERIFIED FIXED** |
| `M-03` | MEDIUM | Một số tham số đường dẫn CLI (`audit`, `verify --diff-file`, `benchmark`, `update --rollback`) chưa qua `resolve_within_scope`. | Cưỡng chế `resolve_within_scope(layout.root, ...)` tại toàn bộ điểm vào CLI tương ứng. | **VERIFIED FIXED** |
| `M-04` | MEDIUM | `--skip-conflicts` ghi đè toàn bộ `manifest.json`; `SPEEDY_GATE_POLICY`/`SPEEDY_SOURCE_URL` trong `ai-workspace/.env` chưa được đọc; đường dẫn backup trong `update-speedy.md` lệch tên thư mục. | Bảo toàn hash `prev_files` khi `--skip-conflicts`; đọc `SPEEDY_GATE_POLICY` & `SPEEDY_SOURCE_URL` từ env/`.env`; đồng bộ đường dẫn `ai-workspace/tmp/backups/speedy-backup-<timestamp>/`. | **VERIFIED FIXED** |
| `M-05` | MEDIUM | Trên layout `builder`, `cleanup --include-logs` có thể quét nhầm `logs/audit/` khi `--include-audit=False`. | Loại trừ `layout.audit_dir` khỏi vòng quét `--include-logs` trong `cleanup.py`. | **VERIFIED FIXED** |
| `L-01` | LOW | Dead code `if False` và import thừa trong `benchmark.py`; đo dung lượng bằng `str(rm_res)` thay vì JSON. | Xóa dead code/unused import và dùng `json.dumps(rm_res, ensure_ascii=False)`. | **VERIFIED FIXED** |
| `L-02` | LOW | `scaffold.py` ném `ValueError` thay vì `SpeedyError`; `policy.default.json` thiếu `verify_report` ở `balanced`; `CHANGELOG.md` ghi 18 module thay vì 20; chưa có test kiểm tra 4 file JSON schema. | Chuẩn hóa `SpeedyError`, bổ sung `verify_report`, cập nhật `20 module Python`, bổ sung test kiểm tra 4 file `src/.speedy/schemas/*.schema.json`. | **VERIFIED FIXED** |

---

## 3. Ghi Chú Bàn Giao (Non-Blocking)
- Giới hạn tự nhiên duy nhất đã được công bố trung thực: `live_ide_llm_e2e` có trạng thái `NOT_VERIFIED_BY_SCRIPT` (xem [reports/2026-11-27-verification-report.md](2026-11-27-verification-report.md)). Khuyến nghị người dùng chạy thêm 1 smoke-test ngắn trực tiếp trên giao diện Antigravity IDE sau khi nghiệm thu.
