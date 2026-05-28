import pandas as pd
from pathlib import Path

DATA_DIR = Path("data/raw")

print("Loading data...")
customers = pd.read_csv(DATA_DIR / "customers.csv", parse_dates=["signup_date"])
orders = pd.read_csv(DATA_DIR / "orders.csv", parse_dates=["order_date"])
order_items = pd.read_csv(DATA_DIR / "order_items.csv", low_memory=False)

print("Processing order items...")
order_items["gross_revenue"] = order_items["quantity"] * order_items["unit_price"]
order_items["net_revenue"] = order_items["gross_revenue"] - order_items["discount_amount"].fillna(0.0)
order_items["promo_used_line"] = order_items[["promo_id", "promo_id_2"]].notna().any(axis=1)

print("Aggregating order values...")
order_value = (
    order_items.groupby("order_id", as_index=False)
    .agg(
        gross_revenue=("gross_revenue", "sum"),
        net_revenue=("net_revenue", "sum"),
        discount_amount=("discount_amount", "sum"),
        total_qty=("quantity", "sum"),
        promo_used=("promo_used_line", "max"),
    )
)

print("Enriching orders...")
orders_enriched = orders.merge(order_value, on="order_id", how="left")
cols_to_merge = ["customer_id", "acquisition_channel", "age_group", "city"]
orders_enriched = orders_enriched.merge(
    customers[cols_to_merge],
    on="customer_id",
    how="left"
)

# RFM calculation
print("Calculating RFM...")
max_date = orders["order_date"].max()
rfm = (
    orders_enriched.groupby("customer_id", as_index=False)
    .agg(
        last_order_date=("order_date", "max"),
        Frequency=("order_id", "nunique"),
        Historical_ARPU=("net_revenue", "sum")
    )
)
rfm["Recency"] = (max_date - rfm["last_order_date"]).dt.days

# Frequency Bucket
def get_freq_bucket(f):
    if pd.isna(f): return "Unknown"
    if f == 1: return "1 Order"
    elif 2 <= f <= 3: return "2-3 Orders"
    elif 4 <= f <= 5: return "4-5 Orders"
    else: return "6+ Orders"

rfm["Frequency_Bucket"] = rfm["Frequency"].apply(get_freq_bucket)

# Merge back frequency bucket to orders
print("Merging frequency buckets...")
orders_matched = orders_enriched.merge(
    rfm[["customer_id", "Frequency_Bucket"]], on="customer_id", how="inner"
)

# Calculate summary by Frequency_Bucket and promo_used
print("Calculating summaries...")
summary = orders_matched.groupby(["Frequency_Bucket", "promo_used"]).agg(
    avg_net_rev=("net_revenue", "mean"),
    avg_gross_rev=("gross_revenue", "mean"),
    avg_qty=("total_qty", "mean"),
    avg_discount=("discount_amount", "mean"),
    count=("order_id", "count")
).reset_index()

print("\n--- RESULTS ---")
print(summary.to_string(index=False))

# Calculate lift metrics
print("\n--- LIFT METRICS ---")
pivot_net = summary.pivot(index="Frequency_Bucket", columns="promo_used", values="avg_net_rev")
pivot_gross = summary.pivot(index="Frequency_Bucket", columns="promo_used", values="avg_gross_rev")
pivot_qty = summary.pivot(index="Frequency_Bucket", columns="promo_used", values="avg_qty")

freq_order = ["1 Order", "2-3 Orders", "4-5 Orders", "6+ Orders"]
pivot_net = pivot_net.reindex(freq_order)
pivot_gross = pivot_gross.reindex(freq_order)
pivot_qty = pivot_qty.reindex(freq_order)

net_lift = (pivot_net[True] - pivot_net[False]) / pivot_net[False] * 100
gross_lift = (pivot_gross[True] - pivot_gross[False]) / pivot_gross[False] * 100
qty_lift = (pivot_qty[True] - pivot_qty[False]) / pivot_qty[False] * 100

lift_df = pd.DataFrame({
    "Net_Revenue_Lift_%": net_lift,
    "Gross_Revenue_Lift_%": gross_lift,
    "Quantity_Lift_%": qty_lift
})
print(lift_df.to_string())
