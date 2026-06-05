# Báo Cáo Thiết Kế Schema Và Quy Trình Import PostgreSQL

## 1. Mục tiêu và phạm vi

Tài liệu này tổng hợp phần thiết kế schema quan hệ và quy trình import dữ liệu CSV vào PostgreSQL local cho bài toán ecommerce trong repo `datathon_2026`.

Phạm vi tài liệu:
- thiết kế schema `stg`, `core`, `mart`
- lý do chọn khóa, chuẩn hóa, index
- quy trình import từ 13 file CSV vào PostgreSQL
- các bước chuẩn hóa dữ liệu ngay trong tầng database transform
- các challenge kỹ thuật đã gặp và hướng xử lý

Ngoài phạm vi tài liệu:
- pipeline forecast
- EDA/storytelling
- pipeline Python đánh giá chất lượng dữ liệu và làm sạch sâu trong `src/data_quality_pipeline.py`

Tài liệu này phản ánh implementation hiện có trong:
- [01_create_schemas_and_staging.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\01_create_schemas_and_staging.sql)
- [02_create_core_tables.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\02_create_core_tables.sql)
- [03_transform_staging_to_core.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\03_transform_staging_to_core.sql)
- [04_create_marts.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\04_create_marts.sql)
- [05_verify_schema.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql)
- [setup_postgres_local.ps1](E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1)

## 2. Tóm tắt kiến trúc

Kiến trúc được tách thành 3 lớp:

1. `stg`:
   - giữ dữ liệu gần với raw CSV nhất
   - phục vụ audit, replay, debug import
   - hạn chế biến đổi nghiệp vụ ở lớp này

2. `core`:
   - là mô hình quan hệ chuẩn hóa dùng để query và join ổn định
   - loại bỏ các cột dư thừa 3NF
   - đưa quan hệ về đúng grain, đặc biệt với `order_items`, `returns`, `reviews`, `promotions`

3. `mart`:
   - chứa bảng reporting grain theo ngày
   - tách biệt khỏi `core` để không làm nhiễu mô hình giao dịch

Luồng dữ liệu:

`CSV raw -> stg.* -> transform SQL -> core.* -> mart.* -> verification`

Lý do không import thẳng raw vào `core`:
- khó debug khi transform hỏng
- mất khả năng so sánh raw và normalized
- khó phát hiện bản ghi mồ côi, ambiguous mapping và lỗi business logic

## 3. Lý do chọn mô hình schema

### 3.1. Vì sao dùng `stg / core / mart`

Thiết kế một tầng duy nhất sẽ nhanh hơn lúc đầu nhưng có ba vấn đề:
- raw schema chứa dư thừa và grain không nhất quán
- các quyết định chuẩn hóa sẽ trộn lẫn với dữ liệu nguồn, khó rollback
- báo cáo aggregate như `sales` và `web_traffic` không nên nằm chung với transaction core

Ba tầng giải quyết lần lượt:
- `stg` cho data lineage
- `core` cho relational integrity
- `mart` cho analytics/output

### 3.2. Vì sao dùng `INT` cho ID nội bộ

Toàn bộ technical key dùng `INT` vì:
- dataset hiện tại có cardinality thấp hơn nhiều so với giới hạn `INT`
- join nhanh, dễ đọc, đồng nhất với source hiện có
- không cần `BIGINT` ở giai đoạn local/dev hiện tại

Lưu ý:
- các business code như `PROMO-0001`, `RET-000001`, `REV-0000001` vẫn được giữ dưới dạng text unique ở tầng `core`
- đây là quyết định quan trọng để vừa có key kỹ thuật tối ưu join, vừa không mất dấu vết mã nghiệp vụ gốc

### 3.3. Vì sao `zip` được convert sang `varchar` ở `core`

Trong CSV, `zip` xuất hiện như số nguyên, nhưng về mặt domain đây là mã định danh, không phải numeric measure.

Convert `zip` sang `varchar(12)` ở `core` để:
- tránh phụ thuộc vào tính chất số học không tồn tại
- tránh mất số 0 đầu nếu sau này có postal code mới
- chuẩn hóa kiểu giữa `customers`, `orders`, `geography`

### 3.4. Vì sao tạo `order_item_id`

Raw `order_items.csv` không có PK tự nhiên ổn định.

Nếu chỉ dùng `(order_id, product_id)`:
- không đảm bảo duy nhất
- có thể một order có nhiều dòng cùng `product_id`
- không đủ để làm anchor cho `returns` và `reviews`

Do đó `core.order_items` dùng:
- `order_item_id` làm surrogate PK
- `line_number` làm thứ tự dòng trong mỗi order
- `UNIQUE(order_id, line_number)` để đảm bảo grain line-item

Đây là quyết định trung tâm của toàn bộ schema.

## 4. Chuẩn hóa bảng và lý do nghiệp vụ

### 4.1. `customers`

`core.customers` không giữ `city`.

Lý do:
- `city` suy ra từ `zip` qua `geography`
- giữ lại `city` trong `customers` tạo dư thừa và rủi ro lệch dữ liệu

### 4.2. `inventory`

`core.inventory_snapshots` không giữ:
- `product_name`
- `category`
- `segment`

Lý do:
- ba cột này phụ thuộc vào `product_id`
- đây là thuộc tính của dimension `products`, không phải thuộc snapshot tồn kho

### 4.3. `reviews`

`core.reviews` không giữ `customer_id`.

Lý do:
- khách hàng có thể suy ra từ `order_item_id -> order_id -> orders.customer_id`
- nếu giữ `customer_id`, bảng review bị dư thừa và có thể lệch với order gốc

### 4.4. `returns` và `reviews` tham chiếu `order_item_id`

Đây là điểm khó nhất trong thiết kế.

Lý do chọn line-level FK thay vì chỉ `order_id` hoặc `(order_id, product_id)`:
- return/review gắn với một dòng mua hàng cụ thể
- cùng một sản phẩm có thể xuất hiện nhiều lần trong cùng order
- `refund_amount`, `return_quantity`, promotion và discount cần truy được đến dòng gốc

Tradeoff:
- raw source không có sẵn `order_item_id`
- transform phải suy luận từ `order_id + product_id`
- khi có nhiều candidate, hệ thống không tự gán mà đẩy sang `core.load_issues`

Đây là quyết định thiên về correctness hơn convenience.

### 4.5. `promotions` và stacked promo

Raw source có `promo_id` và `promo_id_2`.

Đây là repeating-group pattern, không phù hợp 1NF nếu mang nguyên sang `core`.

Giải pháp:
- `core.promotions` là dimension promotion
- `core.order_item_promotions` là bridge table
- `promo_sequence` ghi lại promo thứ nhất hay thứ hai

Thiết kế này mở được đường cho:
- stacked promotions
- nhiều promotion hơn trong tương lai
- truy vấn line-level promo rõ ràng

### 4.6. `payments` và `shipments`

Hai bảng này được thiết kế như extension của `orders`:
- `payment_id` và `shipment_id` là surrogate PK
- `order_id` có `UNIQUE`

Lý do:
- dữ liệu hiện tại thể hiện giả định mỗi order có tối đa một payment record và tối đa một shipment record
- dùng surrogate key giúp schema đỡ cứng hơn so với shared-PK tuyệt đối

Rủi ro cần ghi nhận:
- nếu business đổi sang partial shipments hoặc multiple payments, schema này cần nới grain

## 5. Danh sách bảng ở từng tầng

### 5.1. Tầng `stg`

13 bảng raw:
- `stg.customers`
- `stg.geography`
- `stg.inventory`
- `stg.orders`
- `stg.order_items`
- `stg.payments`
- `stg.products`
- `stg.promotions`
- `stg.returns`
- `stg.reviews`
- `stg.sales`
- `stg.shipments`
- `stg.web_traffic`

Đặc điểm:
- bám theo CSV
- kiểu dữ liệu đủ chặt để import ổn định
- thêm identity row id cho các bảng line-level cần mapping sau này như `stg.order_items`, `stg.returns`, `stg.reviews`

### 5.2. Tầng `core`

Các bảng normalized:
- `core.geography`
- `core.customers`
- `core.products`
- `core.promotions`
- `core.orders`
- `core.order_items`
- `core.order_item_promotions`
- `core.payments`
- `core.shipments`
- `core.returns`
- `core.reviews`
- `core.inventory_snapshots`
- `core.load_issues`

### 5.3. Tầng `mart`

- `mart.sales_daily`
- `mart.web_traffic_daily`

## 6. Các bước dọn dẹp và chuẩn hóa trong import SQL

Phần import vào PostgreSQL không làm full data cleaning như Python pipeline, nhưng có các bước chuẩn hóa cấu trúc quan trọng:

### 6.1. Chuẩn hóa kiểu dữ liệu

- `zip` từ `int` ở `stg` sang `varchar` ở `core`
- `stackable_flag`, `stockout_flag`, `overstock_flag`, `reorder_flag` từ numeric sang boolean
- business code giữ text nguyên trạng

### 6.2. Loại bỏ dư thừa

Không carry forward các cột dư thừa vào `core`:
- `customers.city`
- `inventory.product_name`
- `inventory.category`
- `inventory.segment`
- `reviews.customer_id`

### 6.3. Tạo surrogate key và line grain

Trong transform:
- tạo `order_item_id`
- tính `line_number` theo từng `order_id`
- tạo bảng mapping tạm `tmp_order_item_map` để nối ngược từ `stg_order_item_id` sang `order_item_id`

### 6.4. Tách repeated promo columns thành bridge table

`promo_id` và `promo_id_2` được unpivot thành:
- `order_item_id`
- `promotion_id`
- `promo_sequence`

### 6.5. Xử lý bản ghi ambiguous thay vì đoán

Với `returns` và `reviews`:
- nếu match đúng 1 dòng `order_item` thì insert vào `core`
- nếu match 0 dòng thì ghi vào `core.load_issues`
- nếu match nhiều dòng thì cũng ghi vào `core.load_issues`

Nguyên tắc ở đây là:
- không silent data loss
- không tự gán sai
- lỗi phải observable

## 7. Chiến lược index

Các index được tạo chủ yếu cho:
- PK / UNIQUE
- FK join path
- các cột ngày hay filter

Index đáng chú ý:
- `idx_core_orders_customer_id`
- `idx_core_orders_shipping_zip_code`
- `idx_core_orders_order_date`
- `idx_core_order_items_order_id`
- `idx_core_order_items_product_id`
- `idx_core_returns_order_item_id`
- `idx_core_reviews_order_item_id`
- `idx_core_shipments_ship_date`
- `idx_core_inventory_product_id_snapshot_date`

Lý do:
- các truy vấn transaction/report thường xuất phát từ `orders`
- `order_items` là table trung tâm nên cần tối ưu đường join sang `orders`, `products`, `returns`, `reviews`, `promotions`

## 8. Quy trình import PostgreSQL

Runner chính là [setup_postgres_local.ps1](E:\AI Thuc Chien\VSF\datathon_2026\scripts\setup_postgres_local.ps1).

Quy trình thực thi:

1. kiểm tra binary PostgreSQL và kết nối
2. tạo database nếu chưa tồn tại
3. chạy `01_create_schemas_and_staging.sql`
4. truncate staging
5. dùng `\copy` để load toàn bộ 13 CSV vào `stg`
6. chạy `02_create_core_tables.sql`
7. chạy `03_transform_staging_to_core.sql`
8. chạy `04_create_marts.sql`
9. chạy `05_verify_schema.sql`

Điểm đáng chú ý:
- import dùng `\copy` thay vì `COPY` server-side để tránh phụ thuộc quyền truy cập filesystem của PostgreSQL service
- runner fail-fast nếu thiếu file CSV hoặc lệnh `psql` lỗi

## 9. Verification

File [05_verify_schema.sql](E:\AI Thuc Chien\VSF\datathon_2026\sql\05_verify_schema.sql) kiểm tra ba mức:

1. có đủ schema `stg`, `core`, `mart`
2. có đủ các bảng bắt buộc
3. xác nhận design constraint đặc thù:
   - `core.returns` phải có `order_item_id`
   - `core.reviews` không được có `customer_id`

Trước khi apply lên instance thật, runner đã được smoke-test trên một PostgreSQL cluster tạm độc lập.

## 10. Kết quả import thực tế

Import đã được chạy thành công lên PostgreSQL local `127.0.0.1:5432`, database `datathon_2026`.

### 10.1. Số dòng staging

| Bảng | Số dòng |
|---|---:|
| `stg.customers` | 121,930 |
| `stg.geography` | 39,948 |
| `stg.inventory` | 60,247 |
| `stg.orders` | 646,945 |
| `stg.order_items` | 714,669 |
| `stg.payments` | 646,945 |
| `stg.products` | 2,412 |
| `stg.promotions` | 50 |
| `stg.returns` | 39,939 |
| `stg.reviews` | 113,551 |
| `stg.sales` | 3,833 |
| `stg.shipments` | 566,067 |
| `stg.web_traffic` | 3,652 |

### 10.2. Số dòng core và mart sau transform

| Bảng | Số dòng |
|---|---:|
| `core.geography` | 39,948 |
| `core.customers` | 121,930 |
| `core.products` | 2,412 |
| `core.promotions` | 50 |
| `core.orders` | 646,945 |
| `core.order_items` | 714,669 |
| `core.order_item_promotions` | 276,522 |
| `core.payments` | 646,945 |
| `core.shipments` | 566,067 |
| `core.returns` | 39,935 |
| `core.reviews` | 113,549 |
| `core.inventory_snapshots` | 60,247 |
| `core.load_issues` | 6 |
| `mart.sales_daily` | 3,833 |
| `mart.web_traffic_daily` | 3,652 |

### 10.3. Load issues

| Entity | Issue type | Count |
|---|---|---:|
| `returns` | `ambiguous_order_item` | 4 |
| `reviews` | `ambiguous_order_item` | 2 |

Diễn giải:
- có 4 return records và 2 review records không thể map chắc chắn về đúng `order_item_id`
- đây không phải import failure
- đây là tín hiệu dữ liệu nguồn chưa đủ chi tiết cho line-level mapping tuyệt đối

## 11. Các challenge chính và cách xử lý

### Challenge 1: Raw source không có `order_item_id`

Vấn đề:
- `returns` và `reviews` chỉ mang `order_id + product_id`
- nhưng mô hình đúng phải map về line item

Giải pháp:
- tạo `order_item_id` ở `core.order_items`
- tạo `tmp_order_item_map`
- chỉ insert khi mapping duy nhất
- ghi vào `core.load_issues` nếu ambiguous

Lý do chọn giải pháp này:
- đúng mô hình dữ liệu hơn
- tránh tự động gán sai line item
- dễ audit hơn

### Challenge 2: Repeated promo columns

Vấn đề:
- raw có `promo_id` và `promo_id_2`
- đây là cấu trúc vi phạm tinh thần 1NF nếu giữ nguyên trong relational core

Giải pháp:
- tách thành `core.order_item_promotions`
- dùng `promo_sequence` để bảo toàn thứ tự promo

### Challenge 3: Dư thừa dữ liệu giữa các bảng

Vấn đề:
- `customers.city`, `inventory.product_name/category/segment`, `reviews.customer_id` là các cột có thể suy ra từ dimension/transaction khác

Giải pháp:
- không carry sang `core`
- chỉ giữ ở `stg` để trace raw

### Challenge 4: Import file từ local machine vào PostgreSQL service

Vấn đề:
- `COPY` server-side phụ thuộc filesystem access của service account
- dễ fail khi path nằm ngoài quyền truy cập của PostgreSQL server

Giải pháp:
- dùng `psql \copy` từ client side trong PowerShell runner

### Challenge 5: Verification sau import

Vấn đề:
- create table thành công chưa đủ chứng minh schema đúng với yêu cầu logic

Giải pháp:
- thêm file `05_verify_schema.sql`
- kiểm tra schema, table existence và design constraints đặc thù

## 12. Những điểm còn mở

Có ba điểm nên trao đổi thêm với senior:

1. `payments` hiện đang giả định 1 order = 1 payment record.
   - nếu tương lai có split payments, cần đổi grain.

2. `shipments` hiện đang giả định 1 order có tối đa 1 shipment record.
   - nếu có partial shipment, schema phải nới.

3. `web_traffic` hiện đang có grain theo ngày và chỉ còn 1 record mỗi ngày.
   - nếu business muốn track theo source per day, cần xem lại source và chuyển PK sang `(traffic_date, traffic_source)`.

## 13. Khuyến nghị bước tiếp theo

Đề xuất theo thứ tự ưu tiên:

1. dựng một layer `views` cho analytics:
   - `v_order_item_detail`
   - `v_customer_order_history`
   - `v_returns_enriched`
   - `v_reviews_enriched`

2. xử lý 6 dòng trong `core.load_issues`:
   - xác định có thể enrich từ raw hay cần rule nghiệp vụ bổ sung

3. nếu muốn productionize hơn:
   - thêm audit table cho từng lần load
   - thêm checksum / source file metadata
   - thêm idempotent job wrapper thay vì runner thủ công

4. nếu muốn đồng bộ với pipeline Python cleaning:
   - quyết định rõ raw source của PostgreSQL là `data/raw` hay `data/processed`
   - hiện tại DB import đang đọc từ `data/raw`, còn cleaning pipeline là một luồng riêng

## 14. Kết luận

Thiết kế hiện tại ưu tiên ba mục tiêu:
- giữ raw có thể audit được
- đưa transaction schema về grain và chuẩn hóa hợp lý
- không đoán dữ liệu khi source không đủ chi tiết

Điểm mạnh của giải pháp:
- join path rõ ràng
- 3NF tốt hơn đáng kể so với raw CSV
- import runner tái chạy được
- có verification và cơ chế cách ly lỗi bằng `core.load_issues`

Điểm đánh đổi:
- một số bản ghi `returns` và `reviews` chưa map được 100% vào line-level
- import database chưa gộp full data cleaning vào cùng pipeline

Đây là trạng thái đủ tốt để:
- báo cáo kiến trúc cho senior
- dùng làm nền cho analytics/query
- tiếp tục mở rộng sang DQ pipeline hoặc production-grade ETL sau đó
