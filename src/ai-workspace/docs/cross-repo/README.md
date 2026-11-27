# Kiến Thức Liên Dự Án (Cross-Repo Knowledge)

Thư mục này lưu trữ các bản tóm tắt kỹ thuật có chọn lọc từ các dịch vụ/kho mã nguồn liên quan để truy xuất theo cơ chế **Lazy-Load**, giúp tiết kiệm ngữ cảnh và không phải quét lại repo ngoài ở mỗi phiên làm việc.

---

## Quy Trình Tra Cứu Tiết Kiệm Token

1. Luôn truy vấn `registry.json` trước bằng CLI:
   ```bash
   python3 .speedy/scripts/speedy_cli.py knowledge cross-repo --query "<từ khóa>"
   ```
2. Chỉ mở đúng file `<repo-id>/<topic-id>.md` xuất hiện trong kết quả khớp.
3. Nếu không có kết quả khớp (`matches: []`), đề xuất người dùng bổ sung bằng `/docs cross-repo <repo-id> "<mô tả>"` — tuyệt đối không tự suy đoán API của hệ thống ngoài.
4. Chỉ đọc mã nguồn ngoài khi người dùng cung cấp đường dẫn và quyền truy cập hợp lệ; không lưu khóa bí mật vào tài liệu.
