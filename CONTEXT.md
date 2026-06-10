# Datathon 2026 E-commerce Storytelling

Bối cảnh phân tích tập trung vào dữ liệu thương mại điện tử của Datathon 2026, phục vụ câu chuyện kinh doanh xoay quanh hành vi và giá trị khách hàng.

## Language

**Customer**:
Một cá nhân/tổ chức được định danh duy nhất bằng `customer_id` trong `customers.csv`; các thuộc tính như `acquisition_channel`, `age_group`, `city`, `signup_date` là hồ sơ gốc của khách hàng.
_Avoid_: Account, User (trừ khi mô hình hóa riêng)

**Active Customer**:
Một **Customer** có ít nhất một **Paid Order** trong khoảng thời gian gần đây (mặc định 90 ngày).
_Avoid_: Engaged Customer (nếu không định nghĩa rõ)

**Ordering Customer**:
Một **Customer** có ít nhất một **Order** trong phạm vi phân tích; dùng làm denominator cho các metric như repeat-customer rate.
_Avoid_: Active Customer (nếu không dùng ngưỡng recency)

**Paid Order**:
Một **Order** có `order_id` xuất hiện trong `payments.csv` (đối chiếu trùng khớp theo `order_id`).
_Avoid_: Completed Order (nếu không có trạng thái hoàn tất rõ ràng)

**Recency / Churn Risk**:
Recency được tính dựa trên **Paid Order** gần nhất; Churn Risk = Recency vượt ngưỡng (mặc định 90 ngày).
_Avoid_: Inactive (nếu chưa gắn rõ ngưỡng thời gian)

**Acquisition Channel**:
Kênh thu hút khách hàng gắn cố định với **Customer**, lấy từ `customers.csv` (first-touch).
_Avoid_: Order Source (nếu nói về nguồn của từng đơn)

**Order Source**:
Nguồn phát sinh của một **Order**, dùng để phân tích hành vi hoặc outcome ở cấp đơn hàng.
_Avoid_: Acquisition Channel (nếu đang nói về nguồn của từng đơn)

**Customer Zip Code**:
Mã bưu chính thuộc hồ sơ gốc của **Customer**, dùng cho phân tích địa lý ở cấp khách hàng.
_Avoid_: Shipping Zip Code (nếu đang nói về nơi giao hàng của từng đơn)

**Shipping Zip Code**:
Mã bưu chính giao hàng của một **Order**, dùng cho phân tích địa lý ở cấp đơn hàng, giao hàng, hoặc doanh thu theo điểm đến.
_Avoid_: Customer Zip Code (nếu đang nói về nơi giao hàng)

**Customer City**:
Thành phố thuộc hồ sơ địa lý của **Customer**, được hiểu theo **Customer Zip Code**; dùng cho phân tích segmentation hoặc profile ở cấp khách hàng.
_Avoid_: Shipping City (nếu đang nói về nơi giao hàng hoặc outcome của đơn)

**Shipping City**:
Thành phố giao hàng của một **Order**, được hiểu theo **Shipping Zip Code**; dùng cho phân tích delivery, order outcome, hoặc doanh thu theo điểm đến.
_Avoid_: Customer City (nếu đang nói về nơi giao hàng)

**Geography Area**:
Vùng địa lý được chọn theo đúng term người dùng yêu cầu, ví dụ City, Region, hoặc District; nếu câu hỏi chỉ nói chung về location thì mặc định dùng City để giữ phân tích đơn giản.
_Avoid_: Forcing Region/District (nếu câu hỏi chỉ yêu cầu city hoặc location chung)

**Benchmark Net Revenue**:
Doanh thu theo chuẩn benchmark, tính từ giá trị dòng hàng sau giảm giá; không trừ refund trừ khi câu hỏi yêu cầu rõ về refund, refunded amount, hoặc final revenue after refunds.
_Avoid_: Payment Revenue, Refund-Adjusted Revenue (nếu câu hỏi không nhắc refund)

**Refund-Adjusted Customer Value**:
Giá trị khách hàng sau khi trừ refund từ **Benchmark Net Revenue**, dùng khi phân tích giá trị thực nhận của **Customer**.
_Avoid_: Benchmark Net Revenue (nếu đã trừ refund), Gross Revenue

**Line-Item Refund**:
Một refund gắn với dòng hàng đã mua khi có thể map duy nhất về `order_item_id`; khi tính metric cấp **Order** hoặc **Customer** thì roll-up từ các line-item refund này.
_Avoid_: Order-Level Refund Allocation (nếu chưa roll-up)

**Returned Order**:
Một **Order** có `order_status = 'returned'`; dùng cho các metric về returned orders, return rate, hoặc returned quantity khi câu hỏi không nhắc rõ refund records.
_Avoid_: Line-Item Refund (nếu câu hỏi nói về trạng thái order)

**Load Issue**:
Bản ghi nguồn không thể map chắc chắn vào mô hình `core`, ví dụ refund/review có nhiều candidate `order_item_id`; các bản ghi này được ghi nhận để audit thay vì tự động gán sai.
_Avoid_: Allocated Refund, Clean Record

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
- Một **Ordering Customer** là một **Customer** có ít nhất một **Order** trong phạm vi phân tích, không đồng nghĩa với **Active Customer**.
- Một **Paid Order** là một **Order** có bản ghi thanh toán trong `payments.csv`.
- Recency/Churn Risk được tính từ **Paid Order** (dù quan sát hiện tại cho thấy mọi order đều có payment).
- **Acquisition Channel** là thuộc tính cố định của **Customer**, không thay đổi theo đơn hàng.
- **Order Source** là thuộc tính của từng **Order**, không thay thế cho **Acquisition Channel**.
- **Customer Zip Code** và **Shipping Zip Code** là hai khái niệm khác nhau; một bên thuộc hồ sơ khách hàng, một bên thuộc từng đơn hàng.
- **Customer City** đi theo **Customer Zip Code**; **Shipping City** đi theo **Shipping Zip Code**.
- Khi câu hỏi chỉ nói "city", hãy chọn city theo grain của metric: customer/profile metrics dùng **Customer City**, còn order/revenue/delivery outcome metrics dùng **Shipping City**.
- Với geography, term người dùng yêu cầu là nguồn quyết định: city dùng City, region dùng Region, district dùng District; nếu chỉ nói chung "location" thì dùng City.
- **Benchmark Net Revenue** không trừ refund trừ khi câu hỏi yêu cầu rõ về refund hoặc final revenue after refunds.
- **Refund-Adjusted Customer Value** trừ đi refund để phản ánh giá trị thực nhận của **Customer**.
- **Line-Item Refund** được roll-up lên **Order** hoặc **Customer** khi cần tính metric tổng hợp.
- **Returned Order** và **Line-Item Refund** là hai khái niệm khác nhau; một bên là trạng thái order, một bên là bản ghi refund ở line-item grain.
- **Load Issue** không được dùng như dữ liệu đã phân bổ trong metric chuẩn.
- **New Customer** được xác định bởi paid order đầu tiên trong giai đoạn phân tích.
- **Churned Customer** trùng tiêu chí với Churn Risk: Recency > 90 ngày.
- **Core Customer** = Champion + Loyal.
- Repeat-customer rate dùng denominator là **Ordering Customer**, không phải toàn bộ registered **Customer** và không phải **Active Customer** trừ khi câu hỏi yêu cầu rõ.

## Example dialogue

> **Dev:** “Một **Active Customer** là ai?”
> **Domain expert:** “Là **Customer** có đơn đã thanh toán trong 90 ngày gần đây.”
> **Dev:** “Đơn đã thanh toán được xác định thế nào?”
> **Domain expert:** “Đối chiếu `order_id` với `payments.csv`; có bản ghi thì là **Paid Order**.”

## Flagged ambiguities

- Thực tế hiện tại: quan sát thấy mọi `order_id` đều có bản ghi trong `payments.csv`, nhưng định nghĩa **Paid Order** vẫn dựa trên đối chiếu payment để tránh giả định sai khi dữ liệu thay đổi.
