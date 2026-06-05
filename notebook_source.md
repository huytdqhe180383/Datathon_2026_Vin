[markdown]
# E-Commerce Data Storytelling: Từ tăng trưởng doanh thu đến rủi ro hoàn trả

---

Notebook này kể lại câu chuyện kinh doanh qua **3 chương phân tích**, mỗi chương trả lời một câu hỏi chiến lược:

| Chương | Câu hỏi chiến lược | Phương pháp chính |
|:------:|:------|:------|
| **0** | Ai đang mua, và ai là "Core Customer"? | Phân loại RFM, Biện giải ngưỡng Churn, Phân tích nhân khẩu học (Demographics) |
| **1** | Khuyến mãi có thực sự tạo thêm giá trị? | Phân tích Matched-pair (bóc tách Selection Bias & Cannibalization theo Segment) |
| **2** | Rủi ro chất lượng và Churn nằm ở đâu? | Kiểm định Chi-Square, Phân tích lý do hoàn trả & Simpson's Paradox |

> **Lưu ý về LTV (Life-Time Value):** Trong giới hạn của dữ liệu lịch sử, chưa có mô hình dự phóng (predictive model như BG/NBD hay Gamma-Gamma). Các chỉ số giá trị vòng đời ở đây được tính bằng **Historical ARPU (Average Revenue Per User)** — tức tổng doanh thu thực tế chia cho số khách hàng. Đây là proxy hợp lý nhưng không phải "true LTV".
[code]
from pathlib import Path
import warnings
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Bỏ qua toàn bộ FutureWarning về palette/hue của seaborn 0.14
warnings.filterwarnings("ignore", category=FutureWarning, module="seaborn")

sns.set_theme(style="whitegrid", context="talk")
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["axes.titlesize"] = 16
plt.rcParams["axes.labelsize"] = 12

DATA_DIR = Path("../data/raw")

customers = pd.read_csv(DATA_DIR / "customers.csv", parse_dates=["signup_date"])
orders = pd.read_csv(DATA_DIR / "orders.csv", parse_dates=["order_date"])
order_items = pd.read_csv(DATA_DIR / "order_items.csv", low_memory=False)
promotions = pd.read_csv(DATA_DIR / "promotions.csv", parse_dates=["start_date", "end_date"])
returns = pd.read_csv(DATA_DIR / "returns.csv", parse_dates=["return_date"])
products = pd.read_csv(DATA_DIR / "products.csv")
reviews = pd.read_csv(DATA_DIR / "reviews.csv", parse_dates=["review_date"])
web_traffic = pd.read_csv(DATA_DIR / "web_traffic.csv", parse_dates=["date"])

order_items["gross_revenue"] = order_items["quantity"] * order_items["unit_price"]
order_items["net_revenue"] = order_items["gross_revenue"] - order_items["discount_amount"].fillna(0.0)
order_items["promo_used_line"] = order_items[["promo_id", "promo_id_2"]].notna().any(axis=1)

# Tối ưu RAM: chỉ lấy các cột cần thiết trước khi kết nối (merge)
order_value = (
    order_items.groupby("order_id", as_index=False)
    .agg(
        gross_revenue=("gross_revenue", "sum"),
        net_revenue=("net_revenue", "sum"),
        discount_amount=("discount_amount", "sum"),
        total_quantity=("quantity", "sum"),
        promo_used=("promo_used_line", "max"),
    )
)

# Khấu trừ tiền hoàn trả (refund_amount) khỏi doanh thu Net để ra doanh thu thực tế
returns_summary = returns.groupby("order_id", as_index=False)["refund_amount"].sum()
order_value = order_value.merge(returns_summary, on="order_id", how="left")
order_value["refund_amount"] = order_value["refund_amount"].fillna(0.0)
order_value["final_revenue"] = order_value["net_revenue"] - order_value["refund_amount"]

orders_enriched = orders.merge(order_value, on="order_id", how="left")
cols_to_merge = ["customer_id", "acquisition_channel", "age_group", "city"]
orders_enriched = orders_enriched.merge(
    customers[cols_to_merge],
    on="customer_id",
    how="left"
)

# --- TÍNH TOÁN RFM & RECENCY ---
max_date = orders["order_date"].max()

rfm = (
    orders_enriched.groupby("customer_id", as_index=False)
    .agg(
        last_order_date=("order_date", "max"),
        Frequency=("order_id", "nunique"),
        Historical_ARPU=("final_revenue", "sum")
    )
)
rfm["Recency"] = (max_date - rfm["last_order_date"]).dt.days
rfm["Historical_ARPU_per_order"] = rfm["Historical_ARPU"] / rfm["Frequency"]

# Định nghĩa Churn Risk: Recency > 365 ngày (1 năm)
rfm["Churn_Risk"] = rfm["Recency"] > 365

# Phân điểm RFM (1-4, 4 là tốt nhất; Recency 4 = gần đây nhất)
rfm["R_Score"] = pd.qcut(rfm["Recency"], q=4, labels=[4, 3, 2, 1], duplicates='drop')
rfm["F_Score"] = pd.qcut(rfm["Frequency"].rank(method='first'), q=4, labels=[1, 2, 3, 4])
rfm["M_Score"] = pd.qcut(rfm["Historical_ARPU"], q=4, labels=[1, 2, 3, 4], duplicates='drop')

def assign_segment(row):
    if row["R_Score"] == 4 and row["F_Score"] >= 3 and row["M_Score"] >= 3:
        return "Champion"
    elif row["R_Score"] >= 3 and row["F_Score"] >= 3:
        return "Loyal"
    elif row["Churn_Risk"]:
        return "At Risk / Churned"
    else:
        return "Standard"

rfm["Segment"] = rfm.apply(assign_segment, axis=1)
customers_rfm = customers.merge(rfm, on="customer_id", how="left")
[markdown]
---
## Chương 0. Đặc điểm nhân khẩu học khách hàng & Phân khúc cốt lõi (RFM)

**Mục đích:** Trước khi đi vào các câu hỏi chiến lược, chúng ta cần hiểu *ai đang mua hàng*, *ai là khách hàng cốt lõi ("Core Customers")*, và đặc biệt phải **biện giải khoa học** cho việc định nghĩa một khách hàng ngưng hoạt động (Churn Threshold).

Chương này tiếp cận qua 3 bước phân tích đa chiều logic:
1. **Biện giải ngưỡng Churn (365 ngày):** Phân tích tính thời vụ (Seasonality) và phân phối chu kỳ mua lại của khách hàng để tìm ra điểm cắt tối ưu về mặt thống kê.
2. **Phân loại RFM:** Xác định các nhóm Champion, Loyal, Standard và At Risk dựa trên hành vi giao dịch thực tế sau khi trừ khoản hoàn tiền.
3. **Lồng ghép nhân khẩu học & RFM:** Đối chiếu nhóm tuổi với phân khúc mua sắm để tìm ra chân dung nhóm khách hàng cốt lõi thực sự mang lại dòng doanh thu lớn nhất cho thương hiệu.

---

### 1. Biện giải khoa học về ngưỡng Churn Risk (Recency > 365 ngày)

Để lý giải cho việc chọn mốc 365 ngày làm điểm cắt Churn thay vì các mốc ngắn hơn như 90 hay 180 ngày, chúng ta phân tích hai yếu tố:
- **Yếu tố thời vụ (Seasonality):** Kiểm tra lượng đơn hàng theo từng tháng để xem khách hàng có thói quen mua sắm mang tính chu kỳ năm hay không.
- **Yếu tố hành vi (Purchase Interval Distribution):** Tính phân phối tích lũy (CDF) của số ngày giữa 2 đơn hàng liên tiếp của cùng 1 khách hàng để xem bao nhiêu phần trăm đơn hàng mua lại được hoàn thành trong vòng 1 năm.
[code]
# 1. Tính toán thời gian giữa các đơn hàng liên tiếp của khách hàng mua lặp lại
orders_sorted = orders.sort_values(by=["customer_id", "order_date"])
orders_sorted["prev_order_date"] = orders_sorted.groupby("customer_id")["order_date"].shift(1)
orders_sorted["days_between"] = (orders_sorted["order_date"] - orders_sorted["prev_order_date"]).dt.days

repeat_intervals = orders_sorted["days_between"].dropna()
pct_within_365 = (repeat_intervals <= 365).mean() * 100

# 2. Tính toán seasonality theo tháng của năm
orders["month_of_year"] = orders["order_date"].dt.month
monthly_seasonality = orders.groupby("month_of_year").size()

# 3. Vẽ biểu đồ biện giải
fig, axes = plt.subplots(1, 2, figsize=(18, 6))

# Đồ thị 1: Monthly Seasonality
sns.barplot(
    x=monthly_seasonality.index,
    y=monthly_seasonality.values,
    hue=monthly_seasonality.index,
    palette="crest",
    legend=False,
    ax=axes[0]
)
axes[0].set_title("Số đơn hàng theo Tháng trong năm (Monthly Seasonality)", fontsize=15)
axes[0].set_xlabel("Tháng trong năm", fontsize=12)
axes[0].set_ylabel("Số lượng đơn hàng", fontsize=12)
axes[0].set_xticks(range(12))
axes[0].set_xticklabels([f"T{i}" for i in range(1, 13)])

# Đồ thị 2: Cumulative Distribution of Repeat Intervals
sorted_intervals = np.sort(repeat_intervals)
y_values = np.arange(1, len(sorted_intervals) + 1) / len(sorted_intervals)

axes[1].plot(sorted_intervals, y_values * 100, color="#1f77b4", linewidth=2.5)
axes[1].axvline(x=365, color="#d62728", linestyle="--", linewidth=2)
axes[1].axhline(y=pct_within_365, color="#d62728", linestyle="--", linewidth=1.5)
axes[1].text(390, 25, f"Ngưỡng Churn 365 ngày\n(Chiếm {pct_within_365:.1f}% đơn lặp lại)", color="#d62728", fontsize=11, fontweight="bold")
axes[1].set_title("Phân phối tích lũy Khoảng cách đơn mua lại", fontsize=15)
axes[1].set_xlabel("Số ngày giữa 2 đơn hàng liên tiếp", fontsize=12)
axes[1].set_ylabel("Tỷ lệ tích lũy (%)", fontsize=12)
axes[1].set_xlim(0, 1000)
axes[1].yaxis.set_major_formatter(lambda x, pos: f"{x:.0f}%")

plt.tight_layout()
plt.show()

# In thêm thông số để biện hộ
print(f"Tần suất đơn hàng trung bình/khách/năm trong năm hoạt động: {orders.groupby(['customer_id', orders['order_date'].dt.year]).size().mean():.2f} đơn/năm")
[markdown]
#### **Biện hộ Thống kê & Logic Kinh doanh cho ngưỡng 365 ngày:**
1. **Tính thời vụ rõ rệt (Annual Seasonality):** Biểu đồ seasonality cho thấy lượng mua hàng đạt cực đại vào mùa Xuân/Hè (Tháng 4 - Tháng 8) và tăng vào Tháng 12. Đây là chu kỳ thời vụ đặc trưng. Nếu chọn ngưỡng churn ngắn (ví dụ: 90 ngày hoặc 180 ngày), hệ thống sẽ gắn nhãn sai nhiều khách hàng trung thành nhưng chỉ mua sắm theo mùa (ví dụ: chỉ mua đồ đi biển vào mùa hè hoặc mua quà tặng dịp Noel).
2. **Khoảng cách mua lại (Purchase Intervals):** Kết quả phân phối CDF chứng minh rằng **75.7%** hành vi quay lại của khách hàng lặp lại (repeat buyers) xảy ra trong vòng 365 ngày (1 năm). Sau 365 ngày, biểu đồ CDF trở nên rất phẳng, cho thấy cơ hội khách hàng quay lại mua mà không cần can thiệp tiếp thị là cực kỳ thấp (nằm trong phần đuôi 24.3% trải dài đến nhiều năm).
3. **Tần suất thấp đặc trưng:** Trung bình mỗi khách hàng chỉ đặt **1.79 đơn hàng mỗi năm** trong các năm họ hoạt động. Do đó, một chu kỳ năm (365 ngày) là khoảng thời gian hợp lý nhất để đánh giá một tài khoản còn active hay đã ngưng hoạt động.

---

### 2. Phân loại RFM và Biểu đồ Quy mô Segments
Dựa trên logic Churn 365 ngày và doanh thu đã trừ hoàn trả, đây là kết quả phân loại quy mô phân khúc RFM.
[code]
# Biểu đồ Segment & Nhóm tuổi quy mô cơ bản
fig, axes = plt.subplots(1, 2, figsize=(18, 6))

segment_counts = customers_rfm["Segment"].value_counts()
sns.barplot(
    x=segment_counts.index, y=segment_counts.values,
    hue=segment_counts.index, palette="crest", legend=False, ax=axes[0]
)
axes[0].set_title("Quy mô khách hàng theo RFM Segment", fontsize=16)
axes[0].set_ylabel("Số lượng khách hàng")

age_counts = customers_rfm["age_group"].dropna().value_counts().sort_index()
sns.barplot(
    x=age_counts.index, y=age_counts.values,
    hue=age_counts.index, palette="Blues_d", legend=False, ax=axes[1]
)
axes[1].set_title("Quy mô khách hàng theo nhóm tuổi", fontsize=16)
axes[1].set_ylabel("Số khách hàng")
axes[1].tick_params(axis="x", rotation=30)

plt.tight_layout()
plt.show()

# Bảng Summary theo Segment (Sử dụng final_revenue đã khấu trừ hoàn tiền)
segment_summary = (
    customers_rfm.groupby("Segment", as_index=False)
    .agg(
        Customers=("customer_id", "nunique"),
        Avg_Recency=("Recency", "mean"),
        Avg_Frequency=("Frequency", "mean"),
        Total_Revenue=("Historical_ARPU", "sum"),
        Avg_Historical_ARPU=("Historical_ARPU", "mean")
    )
).sort_values("Total_Revenue", ascending=False)

display(segment_summary.style.format({
    "Customers": "{:,.0f}",
    "Avg_Recency": "{:,.1f} days",
    "Avg_Frequency": "{:,.2f} orders",
    "Total_Revenue": "${:,.0f}",
    "Avg_Historical_ARPU": "${:,.0f}"
}).background_gradient(cmap="YlGnBu", subset=["Total_Revenue", "Avg_Historical_ARPU"]))
[markdown]
### 3. Lồng ghép Demographic (Nhóm tuổi) và RFM để tìm "Core Customer"

Để tìm mối tương quan giữa nhóm tuổi (Demographic) và phân khúc RFM, chúng ta thực hiện cross-tabulation (bảng chéo) và vẽ biểu đồ stacked bar chart để đánh giá tỷ lệ phân bổ tuổi trong từng segment.
[code]
# 1. Tính toán crosstab tỉ lệ % nhóm tuổi nằm trong từng Segment (Row Percentages)
crosstab_pct = pd.crosstab(customers_rfm["Segment"], customers_rfm["age_group"], normalize="index") * 100

# 2. Vẽ biểu đồ Stacked Bar Chart để trực quan hóa cơ cấu nhóm tuổi trong Segment
fig, ax = plt.subplots(figsize=(12, 6))
crosstab_pct.plot(kind="bar", stacked=True, colormap="viridis_r", edgecolor="white", width=0.6, ax=ax)
ax.set_title("Cơ cấu Nhóm tuổi trong từng Phân khúc RFM (%)", fontsize=16)
ax.set_xlabel("Phân khúc RFM", fontsize=12)
ax.set_ylabel("Tỷ lệ phần trăm (%)", fontsize=12)
ax.legend(title="Nhóm tuổi", bbox_to_anchor=(1.05, 1), loc="upper left")
ax.yaxis.set_major_formatter(lambda x, pos: f"{x:.0f}%")
plt.xticks(rotation=0)
plt.tight_layout()
plt.show()

# 3. Hiển thị bảng crosstab được style gradient
display(crosstab_pct.style.format("{:.1f}%").background_gradient(cmap="Blues", axis=1))
[markdown]
#### **Phân tích Đa chiều về Demographic & RFM:**

1. **Hành vi mua sắm độc lập với độ tuổi (Demographic-Independent Behavior):**
   Từ bảng chéo (crosstab), chúng ta thấy một điểm bất ngờ: **Tỷ lệ cơ cấu nhóm tuổi trong từng phân khúc RFM gần như tương đồng tuyệt đối**.
   - Ví dụ: Ở nhóm Champion, nhóm 25-34 tuổi chiếm **29.7%** và 35-44 tuổi chiếm **26.1%**.
   - Trong nhóm At Risk / Churned, nhóm 25-34 cũng chiếm **29.9%** và 35-44 chiếm **26.1%**.
   - Sự phân bổ giữa các segment Champion, Loyal, Standard, Churned đều giống hệt nhau ở mọi nhóm tuổi. Điều này chứng tỏ: **độ tuổi không ảnh hưởng đến hành vi tiêu dùng hay xác suất churn của khách hàng**. Quyết định chi tiêu và rời bỏ là do sản phẩm và trải nghiệm chung của thương hiệu, không bị chi phối bởi độ tuổi.

2. **Hiệu ứng quy mô (Volume Effect) xác định Core Target Audience:**
   Mặc dù hành vi tiêu dùng của các nhóm tuổi là như nhau, song vì nhóm **25-34** và **35-44** có quy mô khách hàng lớn nhất trong hệ thống:
   - Nhóm **25-44** (gộp chung 2 nhóm tuổi này) chiếm đến **55.8%** tổng số khách hàng Champion và **55.5%** tổng số khách hàng Loyal.
   - *Kết luận:* **Khách hàng từ 25 đến 44 tuổi chính là Core Target Audience thực sự** của thương hiệu. Họ chi phối gần 60% doanh thu từ Champion và Loyal không phải vì họ chi tiêu nhiều hơn trên mỗi đơn hàng, mà vì **quy mô quân số của họ quá áp đảo**.
   - *Đề xuất VIP CRM:* Mọi nỗ lực tăng trưởng và giữ chân VIP (Champion/Loyal) nên tập trung nghiên cứu sở thích thời trang, size và thói quen sinh hoạt của nhóm tuổi **25-44** này để đạt hiệu quả doanh thu cao nhất.

---

### Bảng tổng hợp theo nhóm tuổi (Đã sửa: Khấu trừ hoàn trả - Final Revenue)

Chúng ta kiểm tra bảng số liệu tổng doanh thu thực tế (final_revenue = net_revenue - refund_amount) và ARPU của từng nhóm tuổi để xác nhận.
[code]
age_value = (
    orders_enriched.dropna(subset=["age_group"])
    .groupby("age_group", as_index=False)
    .agg(
        Customers=("customer_id", "nunique"),
        Orders=("order_id", "nunique"),
        Total_Revenue=("final_revenue", "sum"),
        Avg_Order_Value=("final_revenue", "mean")
    )
)
age_value["Orders_per_Customer"] = age_value["Orders"] / age_value["Customers"]
age_value["Historical_ARPU"] = age_value["Total_Revenue"] / age_value["Customers"]

age_summary = age_value.sort_values("Total_Revenue", ascending=False)

display(age_summary.style.format({
    "Customers": "{:,.0f}",
    "Orders": "{:,.0f}",
    "Total_Revenue": "${:,.0f}",
    "Avg_Order_Value": "${:,.0f}",
    "Orders_per_Customer": "{:,.2f}",
    "Historical_ARPU": "${:,.0f}"
}).background_gradient(cmap="YlGnBu", subset=["Total_Revenue", "Historical_ARPU"]))
[markdown]
### Thành phố nào chịu chi hơn? (Đã sửa: Khấu trừ hoàn trả)
[code]
city_value = (
    orders_enriched.dropna(subset=["city"])
    .groupby("city", as_index=False)
    .agg(customers=("customer_id", "nunique"), total_revenue=("final_revenue", "sum"))
)
city_value["historical_arpu"] = city_value["total_revenue"] / city_value["customers"]

city_plot = city_value.sort_values("customers", ascending=False).head(15)

fig, ax = plt.subplots(figsize=(12, 7))
sns.scatterplot(
    data=city_plot,
    x="customers",
    y="total_revenue",
    size="historical_arpu",
    sizes=(200, 1600),
    hue="historical_arpu",
    palette="viridis",
    ax=ax,
    legend="brief",
)
ax.set_title("Thành phố: quy mô vs doanh thu thực tế (bubble = Historical ARPU)", fontsize=16)
ax.set_xlabel("Số khách hàng")
ax.set_ylabel("Tổng doanh thu thực tế (final revenue)")

for _, row in city_plot.sort_values("historical_arpu", ascending=False).head(5).iterrows():
    ax.annotate(
        row["city"],
        (row["customers"], row["total_revenue"]),
        xytext=(6, 6),
        textcoords="offset points",
        fontsize=10,
    )

plt.tight_layout()
plt.show()
[markdown]
---
**Nhận định từ Chương 0:** Chúng ta đã biết *ai đang mua* và phân loại được nhóm Core Customers bằng RFM. Câu hỏi tiếp theo là: **Khuyến mãi (Promotions) có thực sự mang lại giá trị tăng thêm (Incremental Lift) cho doanh nghiệp, hay đang âm thầm ăn mòn doanh thu và gây ra hiệu ứng ăn mòn (Cannibalization) trên diện rộng?**
[markdown]
## Chương 1. Khuyến mãi có thực sự tạo thêm giá trị hay chỉ bị dính Selection Bias?

> **Cảnh báo Selection Bias:**
> Nếu chỉ so sánh giá trị đơn hàng trung bình (AOV) của tất cả đơn có Promo và không Promo, ta dễ bị ảo tưởng. Người mua nhiều / mua sỉ thường là người có xu hướng dùng code nhiều nhất, khiến AOV của đơn Promo tự nhiên cao hơn.
>
> **Giải pháp: Matched-pair Analysis (Phân tích ghép cặp theo Tần suất mua)**. Ta phân chia nhóm khách hàng theo Tần suất mua (`Frequency_Bucket`): 1 đơn, 2-3 đơn, 4-5 đơn, 6+ đơn. Trong từng bucket, ta so sánh AOV giữa nhóm Có Promo và Không Promo để thấy rõ **Incremental Lift**.
>
> *Lưu ý về định nghĩa:* **Tần suất mua hàng** ở đây được tính là **tổng số đơn hàng** mà mỗi khách hàng đã đặt trong toàn bộ lịch sử giao dịch của hệ thống.
>
> *Lưu ý về thuật ngữ:*
> - **Giá trị đơn thực tế (Net AOV - sau giảm giá):** Số tiền thực tế khách hàng thanh toán cho mỗi đơn hàng (phản ánh dòng tiền thực thu về).
> - **Giá trị đơn gốc (Gross AOV - trước giảm giá):** Giá trị của các sản phẩm khách chọn mua trước khi áp dụng coupon chiết khấu (phản ánh nhu cầu chọn hàng).
> - **Số lượng sản phẩm / Đơn (Quantity):** Tổng số lượng sản phẩm được đặt trong một đơn hàng.
[code]
# Phân loại Frequency Buckets cho Matched-pair
def get_freq_bucket(f):
    if pd.isna(f): return "Unknown"
    if f == 1: return "1 Order"
    elif 2 <= f <= 3: return "2-3 Orders"
    elif 4 <= f <= 5: return "4-5 Orders"
    else: return "6+ Orders"

orders_matched = orders_enriched.merge(
    customers_rfm[["customer_id", "Frequency"]], on="customer_id", how="inner"
)
orders_matched["Frequency_Bucket"] = orders_matched["Frequency"].apply(get_freq_bucket)

freq_order = ["1 Order", "2-3 Orders", "4-5 Orders", "6+ Orders"]

fig, axes = plt.subplots(1, 2, figsize=(18, 6))

# Biểu đồ AOV Naive (có CI) - fix hue warning
orders_enriched["promo_label"] = orders_enriched["promo_used"].map({True: "Co Promo", False: "Khong Promo"})
sns.barplot(
    data=orders_enriched,
    x="promo_label",
    y="net_revenue",
    hue="promo_label",
    palette={"Khong Promo": "#6c757d", "Co Promo": "#e76f51"},
    legend=False,
    ax=axes[0],
    errorbar=("ci", 95),
    order=["Khong Promo", "Co Promo"]
)
axes[0].set_title("Giá trị đơn thực tế: Có vs Không Promo (Naive)", fontsize=15)
axes[0].set_xlabel("Dùng Promo")
axes[0].set_ylabel("Giá trị thanh toán thực tế / Đơn ($)")

# Biểu đồ Matched Pair (có CI)
sns.barplot(
    data=orders_matched,
    x="Frequency_Bucket",
    y="net_revenue",
    hue="promo_used",
    palette={True: "#e76f51", False: "#6c757d"},
    order=freq_order,
    ax=axes[1],
    errorbar=("ci", 95)
)
axes[1].set_title("Giá trị đơn thực tế theo Tần suất mua", fontsize=15)
axes[1].set_xlabel("Tần suất mua hàng (Tổng số đơn hàng đã mua)")
axes[1].set_ylabel("Giá trị thanh toán thực tế / Đơn ($)")
axes[1].legend(title="Dùng Promo", labels=["Không", "Có"])

plt.tight_layout()
plt.show()

# Tính Incremental Lift % theo bucket tần suất mua hàng
matched_summary = orders_matched.groupby(
    ["Frequency_Bucket", "promo_used"], as_index=False
)["net_revenue"].mean()
pivot_matched = matched_summary.pivot(
    index="Frequency_Bucket", columns="promo_used", values="net_revenue"
).reindex(freq_order)
pivot_matched.columns = ["Gia_tri_don_Khong_Promo", "Gia_tri_don_Co_Promo"]
pivot_matched["Thay_doi_Gia_tri_thuc_thu"] = (
    (pivot_matched["Gia_tri_don_Co_Promo"] - pivot_matched["Gia_tri_don_Khong_Promo"])
    / pivot_matched["Gia_tri_don_Khong_Promo"]
)

display(pivot_matched.style.format({
    "Gia_tri_don_Khong_Promo": "${:,.1f}",
    "Gia_tri_don_Co_Promo": "${:,.1f}",
    "Thay_doi_Gia_tri_thuc_thu": "{:,.1%}"
}).background_gradient(cmap="Reds", subset=["Thay_doi_Gia_tri_thuc_thu"]))
[markdown]
### 2. Tính toán tác động của Khuyến mãi theo phân khúc RFM (Chứng minh Cannibalization)

Để làm rõ câu hỏi liệu khuyến mại có thật sự kém hiệu quả đối với khách VIP (Champion/Loyal) hay không, chúng ta thực hiện kiểm tra chi tiết thông số Thay đổi Doanh thu thực tế (Net AOV Lift), Thay đổi Giá trị đơn hàng gốc (Gross AOV Lift), và Thay đổi Số lượng sản phẩm/đơn (Quantity Lift) giữa đơn Có Promo và Không Promo theo từng phân khúc RFM.
[code]
# 1. Kết nối thông tin phân khúc RFM vào bảng orders_enriched
orders_rfm_promo = orders_enriched.merge(
    customers_rfm[["customer_id", "Segment"]], on="customer_id", how="left"
)

# 2. Tính toán giá trị trung bình
promo_rfm_metrics = (
    orders_rfm_promo.groupby(["Segment", "promo_used"])
    .agg(
        avg_net_rev=("final_revenue", "mean"),
        avg_gross_rev=("gross_revenue", "mean"),
        avg_quantity=("total_quantity", "mean")
    )
    .reset_index()
)

# 3. Pivot để tính Lift % cho từng Segment
pivoted_rfm = promo_rfm_metrics.pivot(
    index="Segment", columns="promo_used", values=["avg_net_rev", "avg_gross_rev", "avg_quantity"]
)
pivoted_rfm.columns = [f"{col[0]}_{'Promo' if col[1] else 'NoPromo'}" for col in pivoted_rfm.columns]

pivoted_rfm["Net_AOV_Lift"] = (pivoted_rfm["avg_net_rev_Promo"] - pivoted_rfm["avg_net_rev_NoPromo"]) / pivoted_rfm["avg_net_rev_NoPromo"] * 100
pivoted_rfm["Gross_AOV_Lift"] = (pivoted_rfm["avg_gross_rev_Promo"] - pivoted_rfm["avg_gross_rev_NoPromo"]) / pivoted_rfm["avg_gross_rev_NoPromo"] * 100
pivoted_rfm["Quantity_Lift"] = (pivoted_rfm["avg_quantity_Promo"] - pivoted_rfm["avg_quantity_NoPromo"]) / pivoted_rfm["avg_quantity_NoPromo"] * 100

# Chỉnh cột và sắp xếp lại để dễ đọc hơn
display_cols = ["Net_AOV_Lift", "Gross_AOV_Lift", "Quantity_Lift"]
pivoted_rfm_display = pivoted_rfm[display_cols].rename(columns={
    "Net_AOV_Lift": "Thay đổi Giá trị đơn thực tế (Net)",
    "Gross_AOV_Lift": "Thay đổi Giá trị đơn gốc (Gross)",
    "Quantity_Lift": "Thay đổi Số lượng sản phẩm / Đơn"
})

display(pivoted_rfm_display.style.format("{:+.2f}%").background_gradient(cmap="Reds", axis=0))

# 4. Vẽ biểu đồ so sánh các Lift trên từng RFM segment
lift_df = pivoted_rfm_display.reset_index()
lift_melted = lift_df.melt(id_vars="Segment", var_name="Metric", value_name="Lift")

fig, ax = plt.subplots(figsize=(14, 6))
sns.barplot(
    data=lift_melted,
    x="Segment",
    y="Lift",
    hue="Metric",
    palette={"Thay đổi Giá trị đơn thực tế (Net)": "#f43f5e", "Thay đổi Giá trị đơn gốc (Gross)": "#fb7185", "Thay đổi Số lượng sản phẩm / Đơn": "#10b981"},
    ax=ax
)
ax.axhline(0, color="black", linestyle="--", linewidth=1.5)
ax.set_title("Tác động của Khuyến mãi (Lift %) theo từng Phân khúc RFM", fontsize=16)
ax.set_xlabel("Phân khúc RFM", fontsize=13)
ax.set_ylabel("Mức độ thay đổi (Lift %)", fontsize=13)
ax.yaxis.set_major_formatter(lambda x, pos: f"{x:+.0f}%")
plt.tight_layout()
plt.show()
[markdown]
#### **Phân tích Biểu đồ & Hợp nhất Cannibalization trên các phân khúc:**

1. **Tỷ lệ sử dụng Promo đồng đều:** Mỗi phân khúc đều có tỷ lệ dùng coupon gần như tương đương (khoảng **38.1% - 38.5%**). Cho thấy sự phổ biến của việc áp dụng code mua hàng của tất cả khách hàng.
2. **Hiện tượng ăn mòn (Cannibalization) xảy ra đồng loạt:**
   - Ở hai nhóm VIP **Champion** và **Loyal**, khi áp dụng khuyến mại, **doanh thu thực tế (Net AOV) giảm mạnh lần lượt là -31.26% và -32.69%**. Đồng thời, **giá trị đơn hàng gốc (Gross AOV) cũng giảm ~20%**. Trong khi đó, **số lượng sản phẩm trong giỏ (Quantity Lift) hầu như không đổi (+1.3% - +1.4%)**.
   - Điều này cho thấy khách VIP không hề mua thêm đồ để hưởng khuyến mại; thay vào đó họ chỉ áp coupon giảm giá cho đơn hàng mà họ vẫn sẽ mua như bình thường, hoặc chuyển hướng sang sản phẩm có giá trị thấp hơn khi có giảm giá. Đây là **bằng chứng định lượng** về việc Promo làm sụt giảm nặng nề doanh thu của nhóm VIP đang đóng góp 76% doanh thu của store.
3. **Standard cũng không có Incremental Lift:**
   - Trước đây ta giả định rằng đối với nhóm **Standard**, promo có thể giúp họ tăng quy mô giỏ hàng để nâng lên Loyal. Tuy nhiên, thông số thực tế cho thấy nhóm Standard cũng bị **sụt giảm thực thu -31.18%**, **giỏ hàng gốc giảm -19.59%**, và **số lượng sản phẩm thực chất chỉ tăng +1.10%** (mức tăng thấp nhất trong tất cả các nhóm).
   - *Kết luận:* Khuyến mãi không hoạt động hiệu quả trên *bất kỳ* phân khúc nào trong hệ thống. Cannibalization là một vấn đề mang tính hệ thống của cửa hàng, không chỉ riêng ở tập VIP.

---
### Hiệu suất chuyển đổi web traffic

Thay vì chỉ nhìn số đơn hàng, chúng ta đo tỷ lệ `Orders / 1,000 sessions` để đánh giá chuyển đổi thực tế. 

**Lưu ý về biểu đồ:** Để các nguồn traffic dễ phân biệt hơn, chúng ta dùng **Subplots** (tách riêng từng nguồn) thay vì chồng các đường lên nhau gây rối mắt.
[code]
# Sử dụng data weekly để tính CI trong mỗi tháng
orders_weekly = (
    orders.assign(week=orders["order_date"].dt.to_period("W").dt.to_timestamp())
    .groupby(["week", "order_source"], as_index=False)
    .size()
    .rename(columns={"size": "orders"})
)
web_weekly = (
    web_traffic.assign(week=web_traffic["date"].dt.to_period("W").dt.to_timestamp())
    .groupby(["week", "traffic_source"], as_index=False)["sessions"]
    .sum()
)
source_eff_weekly = orders_weekly.merge(
    web_weekly, left_on=["week", "order_source"], right_on=["week", "traffic_source"]
)
source_eff_weekly["orders_per_1000_sessions"] = (
    source_eff_weekly["orders"] / source_eff_weekly["sessions"] * 1000
)
source_eff_weekly["quarter"] = source_eff_weekly["week"].dt.to_period("Q").dt.to_timestamp()

top_sources = (
    source_eff_weekly.groupby("order_source")["orders_per_1000_sessions"]
    .mean()
    .sort_values(ascending=False)
    .head(4)
    .index
    .tolist()
)

plot_df = source_eff_weekly[source_eff_weekly["order_source"].isin(top_sources)].copy()

# --- SUBPLOTS: tách riêng từng nguồn traffic ---
n_sources = len(top_sources)
fig, axes = plt.subplots(n_sources, 1, figsize=(14, 4 * n_sources), sharex=True, sharey=True)

colors = sns.color_palette("husl", n_sources)
for idx, source in enumerate(top_sources):
    ax = axes[idx]
    source_data = plot_df[plot_df["order_source"] == source]
    sns.lineplot(
        data=source_data,
        x="quarter",
        y="orders_per_1000_sessions",
        color=colors[idx],
        linewidth=2,
        ax=ax,
        errorbar=("ci", 95),
        err_style="band"
    )
    avg_val = source_data["orders_per_1000_sessions"].mean()
    ax.axhline(y=avg_val, color=colors[idx], linestyle="--", alpha=0.5, linewidth=1)
    ax.set_title(f"{source}  (avg = {avg_val:.1f})", fontsize=14, fontweight="bold")
    ax.set_ylabel("Orders/1K sessions")
    ax.set_xlabel("")

axes[-1].set_xlabel("Quarter", fontsize=13)
fig.suptitle("Hiệu suất chuyển đổi theo nguồn traffic (kèm 95% CI)", fontsize=18, y=1.01)
plt.tight_layout()
plt.show()
[markdown]
---
**Nhận định từ Chương 1:** Phân tích matched-pair và phân tích theo RFM segment giúp làm sáng tỏ rằng khuyến mại đang gây ra hiệu ứng ăn mòn doanh số (Cannibalization) trên diện rộng cho tất cả các tập khách hàng mà không hề giúp mở rộng quy mô giỏ hàng (Quantity Lift gần như bằng 0). Câu hỏi cuối cùng: **Nguyên nhân Churn thực sự nằm ở đâu, và chất lượng sản phẩm có ảnh hưởng hay không?**
[markdown]
## Chương 2. Nguyên nhân Churn & Chất lượng sản phẩm (Kiểm định Chi-Square & Simpson's Paradox)

**Mục đích:** Vì Churn Risk được tính từ hành vi ngưng mua (Recency > 365 ngày), chúng ta sẽ thực hiện kiểm định thống kê để xác định xem liệu việc khách hàng hoàn trả hàng (Returns) có làm tăng tỷ lệ Churn hay không. Ngoài ra, chúng ta sẽ phân tích sâu lý do hoàn trả và tỷ lệ hoàn trả theo nhóm khách hàng (độ tuổi & RFM) cùng tỷ lệ hoàn trả danh mục để tránh mắc phải **Simpson's Paradox** khi đánh giá chất lượng sản phẩm.

Đây là chương quan trọng nhằm bảo đảm **tính nghiêm ngặt về mặt phương pháp luận** trước khi đưa ra các đề xuất hành động và quyết định đầu tư.
[code]
# Lọc orders có trả hàng
returns_summary = returns.groupby("order_id", as_index=False).agg(
    return_qty=("return_quantity", "sum"),
    refund_sum_val=("refund_amount", "sum")
)

# Gắn thông tin trả hàng vào enriched orders
orders_returns = orders_enriched.merge(returns_summary, on="order_id", how="left")
orders_returns["has_return"] = orders_returns["order_id"].isin(returns["order_id"])

# Gắn thêm Churn risk của khách hàng
orders_returns = orders_returns.merge(
    customers_rfm[["customer_id", "Churn_Risk"]], on="customer_id", how="left"
)

# --- 1. KIỂM ĐỊNH CHI-SQUARE CHO MỐI QUAN HỆ RETURNS - CHURN RISK ---
from scipy.stats import chi2_contingency
contingency_table = pd.crosstab(orders_returns["has_return"], orders_returns["Churn_Risk"])
chi2_stat, p_val, dof, expected = chi2_contingency(contingency_table)

print("=== Bảng liên hợp (Contingency Table: has_return vs Churn_Risk) ===")
print(contingency_table)
print(f"Chi-Square Statistic: {chi2_stat:.4f}")
print(f"p-value: {p_val:.4f}")

# --- 2. TÍNH TOÁN TỶ LỆ HOÀN TRẢ THEO CATEGORY (ITEMS & REVENUE) ---
order_items_enriched = order_items.merge(products[["product_id", "category"]], on="product_id", how="left")
total_ordered_qty = order_items_enriched.groupby("category")["quantity"].sum()
total_rev = order_items_enriched.groupby("category")["net_revenue"].sum()

returns_enriched = returns.merge(products[["product_id", "category"]], on="product_id", how="left")
total_returned_qty = returns_enriched.groupby("category")["return_quantity"].sum()
total_refund = returns_enriched.groupby("category")["refund_amount"].sum()

category_metrics = pd.DataFrame({
    "Ordered_Qty": total_ordered_qty,
    "Returned_Qty": total_returned_qty,
    "Revenue": total_rev,
    "Refund_Amount": total_refund
})
category_metrics["Return_Rate"] = category_metrics["Returned_Qty"] / category_metrics["Ordered_Qty"]
category_metrics["Refund_to_Rev_Ratio"] = category_metrics["Refund_Amount"] / category_metrics["Revenue"]
category_metrics = category_metrics.sort_values("Refund_Amount", ascending=False)

print("\n=== Chỉ số hoàn trả theo Category ===")
display(category_metrics.style.format({
    "Ordered_Qty": "{:,.0f}",
    "Returned_Qty": "{:,.0f}",
    "Revenue": "${:,.0f}",
    "Refund_Amount": "${:,.0f}",
    "Return_Rate": "{:.2%}",
    "Refund_to_Rev_Ratio": "{:.2%}"
}))
[markdown]
### 3. Phân tích Lý do hoàn trả & Tỷ lệ hoàn trả theo Nhóm khách hàng

Chúng ta bóc tách lý do hoàn trả phổ biến nhất từ dữ liệu và tính toán xem nhóm khách hàng nào (theo RFM Segment và theo Nhóm tuổi) đang có tỷ lệ hoàn trả đơn hàng cao nhất để xác định xem rò rỉ vận hành nằm ở đâu.
[code]
# 3.1. Phân tích lý do hoàn trả (Return Reasons)
reason_counts = returns["return_reason"].value_counts().reset_index()
reason_counts.columns = ["Ly_do_hoan_tra", "So_luong"]
reason_counts["Ty_le"] = reason_counts["So_luong"] / reason_counts["So_luong"].sum() * 100

# 3.2. Tính toán tỷ lệ hoàn trả đơn hàng theo Segment và Nhóm tuổi
# Kết nối thêm cột Segment từ customers_rfm vào orders_returns nếu chưa có
if "Segment" not in orders_returns.columns:
    orders_returns = orders_returns.merge(customers_rfm[["customer_id", "Segment"]], on="customer_id", how="left")

segment_returns = (
    orders_returns.groupby("Segment", as_index=False)
    .agg(
        Tong_don=("order_id", "nunique"),
        Don_bi_hoan_tra=("has_return", "sum")
    )
)
segment_returns["Ty_le_hoan_tra"] = segment_returns["Don_bi_hoan_tra"] / segment_returns["Tong_don"] * 100
segment_returns = segment_returns.sort_values("Ty_le_hoan_tra", ascending=False)

age_returns = (
    orders_returns.dropna(subset=["age_group"])
    .groupby("age_group", as_index=False)
    .agg(
        Tong_don=("order_id", "nunique"),
        Don_bi_hoan_tra=("has_return", "sum")
    )
)
age_returns["Ty_le_hoan_tra"] = age_returns["Don_bi_hoan_tra"] / age_returns["Tong_don"] * 100
age_returns = age_returns.sort_values("Ty_le_hoan_tra", ascending=False)

# Hiển thị bảng styled
print("=== Tỷ lệ hoàn trả theo Phân khúc RFM ===")
display(segment_returns.style.format({
    "Tong_don": "{:,.0f}",
    "Don_bi_hoan_tra": "{:,.0f}",
    "Ty_le_hoan_tra": "{:.2f}%"
}).background_gradient(cmap="Reds", subset=["Ty_le_hoan_tra"]))

print("\n=== Tỷ lệ hoàn trả theo Nhóm tuổi ===")
display(age_returns.style.format({
    "Tong_don": "{:,.0f}",
    "Don_bi_hoan_tra": "{:,.0f}",
    "Ty_le_hoan_tra": "{:.2f}%"
}).background_gradient(cmap="Reds", subset=["Ty_le_hoan_tra"]))
[code]
# 3.3. Vẽ biểu đồ trực quan hóa Chương 2
fig, axes = plt.subplots(2, 2, figsize=(18, 14))

# Plot 1: Tác động của hoàn trả lên Churn Risk (với 95% CI)
orders_returns["return_label"] = orders_returns["has_return"].map(
    {True: "Co hoan tra", False: "Khong hoan tra"}
)
sns.barplot(
    data=orders_returns,
    x="return_label",
    y="Churn_Risk",
    hue="return_label",
    palette={"Khong hoan tra": "#adb5bd", "Co hoan tra": "#e76f51"},
    legend=False,
    ax=axes[0, 0],
    errorbar=("ci", 95),
    order=["Khong hoan tra", "Co hoan tra"]
)
axes[0, 0].set_title(f"Đơn hàng bị hoàn trả vs Churn Risk?\n(Chi-Square p-value = {p_val:.2f})", fontsize=14)
axes[0, 0].set_xlabel("Trạng thái hoàn trả của đơn hàng")
axes[0, 0].set_ylabel("Tỷ lệ khách hàng ngưng hoạt động")
axes[0, 0].yaxis.set_major_formatter(lambda x, pos: f"{x:.1%}")

# Plot 2: Tỉ lệ hoàn trả thực tế theo Category (loại bỏ Simpson's Paradox)
category_metrics_reset = category_metrics.reset_index()
sns.barplot(
    data=category_metrics_reset,
    x="Return_Rate",
    y="category",
    hue="category",
    palette="rocket",
    legend=False,
    ax=axes[0, 1]
)
axes[0, 1].xaxis.set_major_formatter(lambda x, pos: f"{x:.1%}")
axes[0, 1].set_title("Tỷ lệ hoàn trả thực tế theo Category\n(Items Returned / Items Ordered)", fontsize=14)
axes[0, 1].set_xlabel("Tỷ lệ hoàn trả (%)")
axes[0, 1].set_ylabel("Category")

# Plot 3: Phân phối lý do hoàn trả (Return Reasons)
sns.barplot(
    data=reason_counts,
    x="Ty_le",
    y="Ly_do_hoan_tra",
    hue="Ly_do_hoan_tra",
    palette="viridis",
    legend=False,
    ax=axes[1, 0]
)
axes[1, 0].xaxis.set_major_formatter(lambda x, pos: f"{x:.0f}%")
axes[1, 0].set_title("Phân phối Lý do hoàn trả sản phẩm (%)", fontsize=14)
axes[1, 0].set_xlabel("Tỷ lệ phần trăm (%)")
axes[1, 0].set_ylabel("Lý do hoàn trả")

# Plot 4: Tỷ lệ hoàn trả đơn hàng theo RFM Segment
sns.barplot(
    data=segment_returns,
    x="Ty_le_hoan_tra",
    y="Segment",
    hue="Segment",
    palette="coolwarm",
    legend=False,
    ax=axes[1, 1]
)
axes[1, 1].xaxis.set_major_formatter(lambda x, pos: f"{x:.2f}%")
axes[1, 1].set_title("Tỷ lệ hoàn trả đơn hàng theo Phân khúc RFM", fontsize=14)
axes[1, 1].set_xlabel("Tỷ lệ hoàn trả đơn (%)")
axes[1, 1].set_ylabel("Phân khúc RFM")

plt.tight_layout()
plt.show()
[markdown]
### Nhận xét và Biện hộ Thống kê Chương 2:

1. **Báo cáo kiểm định Returns vs. Churn Risk:**
   - Đơn hàng có hoàn trả có tỷ lệ thuộc nhóm khách ngưng hoạt động là **47.7%**, so với **47.4%** ở nhóm không hoàn trả. Sự khác biệt chỉ là **0.3%**.
   - Kiểm định Chi-Square cho giá trị **p-value = 0.31**, lớn hơn nhiều so với ngưỡng ý nghĩa 0.05. Do đó, **không có sự khác biệt có ý nghĩa thống kê** về tỷ lệ ngưng hoạt động lâu dài giữa các đơn hàng có và không có hoàn trả. Sự cố hoàn trả đơn lẻ chưa trực tiếp thúc đẩy khách hàng rời bỏ dịch vụ.
   
2. **Simpson's Paradox & Thiên lệch Quy mô trong hoàn trả:**
   - Nếu chỉ nhìn vào tổng số tiền hoàn trả, **Streetwear** đóng góp khoản thiệt hại khổng lồ **$406.7M** (chiếm ~80% toàn hệ thống).
   - Tuy nhiên, khi đối chiếu tỷ lệ hoàn trả thực tế ở cấp độ sản phẩm (`Returned_Qty / Ordered_Qty`), **Streetwear chỉ có tỷ lệ hoàn trả là 3.38%**, thấp hơn danh mục **GenZ (3.52%)** và **Outdoor (3.45%)**.
   - Streetwear dẫn đầu về số tiền hoàn trả thuần túy do quy mô doanh thu khổng lồ của nó ($12.56B, chiếm hơn 80% toàn store). Đây là minh chứng rõ rệt cho **Simpson's Paradox (hoặc Quy mô thiên lệch)**. Streetwear không có dấu hiệu chất lượng sản phẩm kém hơn các dòng khác, nhưng do quy mô lớn, chỉ cần giảm nhẹ tỷ lệ hoàn trả tại đây sẽ đem lại hiệu quả tiết kiệm chi phí ròng rất lớn cho doanh nghiệp.

3. **Lý do hoàn trả phổ biến nhất:**
   - Lý do hoàn trả phổ biến nhất là **`wrong_size` (Sai kích cỡ)** chiếm tới **34.97%** tổng số ca hoàn trả.
   - Theo sau là **`defective` (Lỗi sản phẩm)** chiếm **20.08%** và **`not_as_described` (Không đúng mô tả)** chiếm **17.61%**.
   - *Nhận định:* Các lý do liên quan đến lỗi vận hành/chất lượng sản phẩm (Sai kích cỡ, Lỗi sản phẩm, Không đúng mô tả) chiếm tổng cộng tới **72.66%** lý do hoàn trả. Điều này chỉ ra lỗi không nằm ở việc khách hàng "đổi ý" (chỉ chiếm 17.35%) mà phần lớn do thông tin kích cỡ chưa chuẩn xác và chất lượng sản xuất/kiểm định chưa nghiêm ngặt.

4. **Tỷ lệ hoàn trả theo phân khúc khách hàng:**
   - **Tỷ lệ hoàn trả theo RFM Segment:** Nhóm **Standard** có tỷ lệ hoàn trả đơn hàng cao nhất (**5.92%**), tiếp theo là At Risk (**5.64%**), Loyal (**5.62%**) và Champion (**5.50%**).
   - **Tỷ lệ hoàn trả theo Nhóm tuổi:** Nhóm tuổi **45-54** có tỷ lệ hoàn trả cao nhất (**5.64%**), tiếp theo là 35-44 (**5.62%**), 25-34 (**5.56%**), 18-24 (**5.54%**) và thấp nhất là 55+ (**5.43%**).
   - *Nhận định:* Sự chênh lệch tỷ lệ hoàn trả đơn hàng giữa các phân khúc RFM và nhóm tuổi là **vô cùng nhỏ** (chỉ dao động trong khoảng hẹp 5.4% - 5.9%). Điều này chứng tỏ rủi ro hoàn trả là **rủi ro vận hành chung trên toàn hệ thống** (do kích cỡ sản phẩm và lỗi kỹ thuật của nhà máy), không chịu ảnh hưởng bởi đặc tính nhân khẩu học hay giá trị của phân khúc khách hàng.

---
## Kết luận hành động

### 1. Giữ chân tập Champion/Loyal (RFM-driven Retention)

| Insight | Hành động |
|:--------|:---------|
| Tập Champion/Loyal đóng góp phần lớn doanh thu thực tế | Xây dựng chương trình loyalty riêng, early access sản phẩm mới phi tiền tệ |
| Nhóm \"At Risk/Churned\" có Recency > 365 ngày | Chạy chiến dịch win-back cá nhân hóa (email/SMS) trước mốc 365 ngày |
| RFM scoring cho phép phân loại động (dynamic) | Tích hợp RFM scoring vào CRM để auto-trigger các campaign theo segment |

### 2. Khuyến mãi cần đánh giá trên Incremental Lift (không phải doanh thu gộp)

| Insight | Hành động |
|:--------|:---------|
| So sánh doanh thu trung bình naive bị nhiễu bởi Selection Bias | Luôn dùng matched-pair hoặc A/B test để đo lường hiệu quả thực tế của promo |
| Promo gây ra Cannibalization/giảm doanh thu net ~31% ở mọi phân khúc (VIP lẫn Standard) với số lượng sản phẩm tăng chưa đầy 1.5% | Giảm thiểu tối đa việc phát coupon đại trà cho toàn bộ các tập khách hàng. Chuyển dịch ngân sách sang hình thức VIP privileges và marketing cá nhân hóa không kèm discount. |
| Các kênh traffic có hiệu suất chuyển đổi khác nhau | Phân bổ ngân sách quảng cáo theo `orders/1,000 sessions` thay vì chỉ nhìn traffic volume |

### 3. Phòng ngừa tổn thất vận hành bằng cách giảm rủi ro hoàn trả

| Insight | Hành động |
|:--------|:---------|
| Khác biệt về Churn ở cấp đơn hàng có hoàn trả không có ý nghĩa thống kê (p-value = 0.31) | Sự cố hoàn trả đơn lẻ chưa làm khách rời bỏ ngay lập tức, nhưng ma sát vận hành này vẫn cần được hạn chế để bảo vệ doanh thu thực tế. |
| Streetwear gây rò rỉ lớn nhất ($406.7M refund) nhưng do thiên lệch quy mô (Return rate thực tế chỉ 3.38%, thấp hơn GenZ và Outdoor) | Tập trung cải tiến nhẹ bảng size (size chart) và mô tả sản phẩm của Streetwear (giảm nhẹ 0.2% return rate giúp tiết kiệm ròng hơn $25M). Kiểm tra chất lượng sản phẩm dòng GenZ/Outdoor vì có tỷ lệ hoàn trả sản phẩm cao nhất. |
| Giảm return rate = tiết kiệm trực tiếp chi phí vận hành | Đầu tư vào hướng dẫn trước khi mua (bảng size chuẩn xác hơn, video review thực tế, đánh giá chi tiết của khách hàng trước). |

---

> **Lưu ý về phương pháp:**
> - **Historical ARPU** là proxy, không phải true LTV. Để tính LTV chính xác, cần mô hình dự phóng như BG/NBD + Gamma-Gamma.
> - **Churn Risk** dựa trên ngưỡng 365 ngày cố định. Trong thực tế, ngưỡng này nên được tính toán từ phân phối Recency của từng ngành hàng cụ thể.
> - **Matched-pair analysis** là bước đầu của causal inference. Để có kết quả chắc chắn hơn, cần thiết kế A/B test hoặc sử dụng propensity score matching.

Notebook này phù hợp để dùng như một bản kể chuyện dữ liệu ở vòng trình bày: mỗi biểu đồ trả lời một câu hỏi quản trị, mỗi chương dẫn đến chương tiếp theo theo logic tự nhiên.
