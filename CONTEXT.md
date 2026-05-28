# Datathon 2026 E-commerce Storytelling

Bối cảnh phân tích tập trung vào dữ liệu thương mại điện tử của Datathon 2026, phục vụ câu chuyện kinh doanh xoay quanh hành vi và giá trị khách hàng.

## Language

**Customer**:
Một cá nhân/tổ chức được định danh duy nhất bằng `customer_id` trong `customers.csv`; các thuộc tính như `acquisition_channel`, `age_group`, `city`, `signup_date` là hồ sơ gốc của khách hàng.
_Avoid_: Account, User (trừ khi mô hình hóa riêng)

**Active Customer**:
Một **Customer** có ít nhất một **Paid Order** trong khoảng thời gian gần đây (mặc định 90 ngày).
_Avoid_: Engaged Customer (nếu không định nghĩa rõ)

**Paid Order**:
Một **Order** có `order_id` xuất hiện trong `payments.csv` (đối chiếu trùng khớp theo `order_id`).
_Avoid_: Completed Order (nếu không có trạng thái hoàn tất rõ ràng)

**Recency / Churn Risk**:
Recency được tính dựa trên **Paid Order** gần nhất; Churn Risk = Recency vượt ngưỡng (mặc định 90 ngày).
_Avoid_: Inactive (nếu chưa gắn rõ ngưỡng thời gian)

**Acquisition Channel**:
Kênh thu hút khách hàng gắn cố định với **Customer**, lấy từ `customers.csv` (first-touch).
_Avoid_: Order Source (nếu nói về nguồn của từng đơn)

**Customer Value (Net)**:
Giá trị khách hàng tính trên doanh thu **sau giảm giá và trừ hoàn tiền** (refund) từ `returns.csv`.
_Avoid_: Gross Revenue (nếu chưa trừ refund)

**Refund Allocation**:
Hoàn tiền được gán ở **cấp Order** (theo `order_id` trong `returns.csv`), sau đó trừ vào doanh thu order trước khi cộng lên Customer Value.
_Avoid_: Line-item Allocation (nếu không có mapping rõ ràng)

**New Customer**:
Một **Customer** có **Paid Order đầu tiên** trong giai đoạn phân tích; các khách còn lại là **Returning Customer**.
_Avoid_: First-time Buyer (nếu không gắn rõ giai đoạn)

**Churned Customer**:
Một **Customer** có Recency vượt ngưỡng (mặc định 90 ngày) tính theo **Paid Order** gần nhất.
_Avoid_: Dormant (nếu không gắn rõ ngưỡng)

**Core Customer**:
Nhóm khách hàng thuộc RFM Segment **Champion** hoặc **Loyal**.
_Avoid_: VIP (nếu không gắn rõ tiêu chí RFM)

## Relationships

- Một **Active Customer** là một **Customer** có đơn hàng đã thanh toán trong 90 ngày gần nhất.
- Một **Paid Order** là một **Order** có bản ghi thanh toán trong `payments.csv`.
- Recency/Churn Risk được tính từ **Paid Order** (dù quan sát hiện tại cho thấy mọi order đều có payment).
- **Acquisition Channel** là thuộc tính cố định của **Customer**, không thay đổi theo đơn hàng.
- **Customer Value (Net)** trừ đi refund để phản ánh giá trị thực nhận.
- Refund được gán ở cấp **Order** rồi mới roll-up lên **Customer**.
- **New Customer** được xác định bởi paid order đầu tiên trong giai đoạn phân tích.
- **Churned Customer** trùng tiêu chí với Churn Risk: Recency > 90 ngày.
- **Core Customer** = Champion + Loyal.

## Example dialogue

> **Dev:** “Một **Active Customer** là ai?”
> **Domain expert:** “Là **Customer** có đơn đã thanh toán trong 90 ngày gần đây.”
> **Dev:** “Đơn đã thanh toán được xác định thế nào?”
> **Domain expert:** “Đối chiếu `order_id` với `payments.csv`; có bản ghi thì là **Paid Order**.”

## Flagged ambiguities

- Thực tế hiện tại: quan sát thấy mọi `order_id` đều có bản ghi trong `payments.csv`, nhưng định nghĩa **Paid Order** vẫn dựa trên đối chiếu payment để tránh giả định sai khi dữ liệu thay đổi.
