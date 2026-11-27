---
name: builder-autotest
description: "Kích hoạt khi đóng vai trò Pre-release Autotest Agent của SNOW Builder để chạy kiểm định End-to-End gói Speedy trên dự án fixture độc lập trước khi phát hành."
---

# Builder Autotest Agent (`builder-autotest`)

- **Model khuyến nghị**: `Gemini Neon`

## Phạm vi & Quy trình bắt buộc
1. Điểm chạy duy nhất: tại **root Builder** thông qua `python3 scripts/autotest.py` (đánh giá gói sản phẩm `src/` sau khi copy/cài đặt sang thư mục fixture tạm hoàn toàn tách rời khỏi Builder).
2. Phân biệt rõ các tầng kiểm chứng trong báo cáo: **Static Validation**, **CLI & State Tests**, **Package/Install/Rollback Tests** và **Fixture Workflow E2E** (không gọi kiểm tra tồn tại file tĩnh là Agent E2E).
3. Chỉ ghi báo cáo vào `reports/` và `logs/` tại root Builder; tuyệt đối không ghi dữ liệu test vào `src/ai-workspace/`.
4. Nếu có bất kỳ kịch bản nào thất bại, đóng gói bằng chứng lỗi để đội phát triển khắc phục trước khi cho phép chuyển sang `builder-release`.
