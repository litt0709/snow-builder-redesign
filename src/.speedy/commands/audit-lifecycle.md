# Vòng Đời Audit Dùng Chung Cho Các Lệnh Độc Lập

Áp dụng cho mọi skill/command tạo hoặc cập nhật dữ liệu dự án khi chạy độc lập bên ngoài `/flow` (ví dụ: `/analyst`, `/docs`, `/refresh-rule`, `/refresh-style`, `/cleanup --apply`).
*(Miễn trừ cho `/docs-view` và `/audit-view` vì chỉ kết xuất giao diện đọc).*

---

## Bước 1 — Khởi Tạo Session & Audit Riêng Biệt

Luôn tạo một `sid` mới cho mỗi lần chạy lệnh độc lập để không trộn lẫn lịch sử với các phiên khác:

```bash
python3 .speedy/scripts/speedy_cli.py session new \
  --slug "<tên-lệnh>" \
  --goal "<yêu cầu đã làm sạch>" \
  --command-ref "/<tên-lệnh>"
```
Lấy `sid` và `audit.audit_dir` từ JSON stdout (nếu `IS_AUDIT=0` thì `audit.enabled=false`, bỏ qua Bước 2).

---

## Bước 2 — Đóng Phiên Audit Trung Thực

Sau khi hoàn tất công việc của lệnh:

```bash
python3 .speedy/scripts/speedy_cli.py audit finalize \
  --audit-dir "<audit_dir>" \
  --outcome <success|partial|failed> \
  --completion-level <verified|claimed>
```
- Không truyền số liệu token ước lượng: khi không có nguồn đo thực tế, CLI tự động giữ `null` và `source: "not_measured"`.
