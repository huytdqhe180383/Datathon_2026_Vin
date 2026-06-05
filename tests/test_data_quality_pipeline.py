from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

from data_quality_pipeline import DataCleaner, DataQualityAssessor


def build_sample_tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.DataFrame(
            [
                {
                    "customer_id": 1,
                    "zip": 1000,
                    "city": " Ha Noi ",
                    "signup_date": "2024-01-01",
                    "gender": " Female ",
                    "age_group": "25-34",
                    "acquisition_channel": " Social ",
                },
                {
                    "customer_id": 2,
                    "zip": None,
                    "city": "HCM",
                    "signup_date": "bad-date",
                    "gender": "Male",
                    "age_group": "35-44",
                    "acquisition_channel": "Email",
                },
                {
                    "customer_id": 2,
                    "zip": None,
                    "city": "HCM",
                    "signup_date": "bad-date",
                    "gender": "Male",
                    "age_group": "35-44",
                    "acquisition_channel": "Email",
                },
            ]
        ),
        "geography": pd.DataFrame(
            [
                {"zip": 1000, "city": "ha noi", "region": "north", "district": "d1"},
            ]
        ),
        "orders": pd.DataFrame(
            [
                {
                    "order_id": 10,
                    "order_date": "2024-01-02",
                    "customer_id": 1,
                    "zip": 1000,
                    "order_status": " Completed ",
                    "payment_method": "Card",
                    "device_type": "Mobile",
                    "order_source": "App",
                },
                {
                    "order_id": 11,
                    "order_date": "2024-01-03",
                    "customer_id": 99,
                    "zip": 9999,
                    "order_status": " Completed ",
                    "payment_method": "Card",
                    "device_type": "Desktop",
                    "order_source": "Web",
                },
            ]
        ),
        "order_items": pd.DataFrame(
            [
                {
                    "order_id": 10,
                    "product_id": 101,
                    "quantity": 2,
                    "unit_price": 50.0,
                    "discount_amount": None,
                    "promo_id": None,
                    "promo_id_2": None,
                },
                {
                    "order_id": 11,
                    "product_id": 999,
                    "quantity": 0,
                    "unit_price": -10.0,
                    "discount_amount": 100.0,
                    "promo_id": " PROMO1 ",
                    "promo_id_2": None,
                },
            ]
        ),
        "payments": pd.DataFrame(
            [
                {"order_id": 10, "payment_method": "Card", "payment_value": 100.0, "installments": 1},
                {"order_id": 11, "payment_method": "Card", "payment_value": 50.0, "installments": 1},
            ]
        ),
        "products": pd.DataFrame(
            [
                {
                    "product_id": 101,
                    "product_name": " Shirt ",
                    "category": " Apparel ",
                    "segment": " Casual ",
                    "size": "M",
                    "color": "Blue",
                    "price": 50.0,
                    "cogs": 20.0,
                }
            ]
        ),
        "promotions": pd.DataFrame(
            [
                {
                    "promo_id": "PROMO1",
                    "promo_name": "New Year",
                    "promo_type": "PERCENT",
                    "discount_value": 10.0,
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-10",
                    "applicable_category": " Apparel ",
                    "promo_channel": " App ",
                    "stackable_flag": 1,
                    "min_order_value": 0,
                }
            ]
        ),
        "returns": pd.DataFrame(
            [
                {
                    "return_id": "RET-1",
                    "order_id": 10,
                    "product_id": 101,
                    "return_date": "2024-01-05",
                    "return_reason": "late",
                    "return_quantity": 1,
                    "refund_amount": 20.0,
                }
            ]
        ),
        "reviews": pd.DataFrame(
            [
                {
                    "review_id": "REV-1",
                    "order_id": 10,
                    "product_id": 101,
                    "customer_id": 1,
                    "review_date": "2024-01-06",
                    "rating": 5,
                    "review_title": " Great ",
                }
            ]
        ),
        "sales": pd.DataFrame(
            [{"Date": "2024-01-02", "Revenue": 100.0, "COGS": 40.0}]
        ),
        "shipments": pd.DataFrame(
            [
                {"order_id": 10, "ship_date": "2024-01-01", "delivery_date": "2024-01-04", "shipping_fee": 5.0},
                {"order_id": 11, "ship_date": "2024-01-02", "delivery_date": "2024-01-05", "shipping_fee": 5.0},
            ]
        ),
        "inventory": pd.DataFrame(
            [
                {
                    "snapshot_date": "2024-01-31",
                    "product_id": 101,
                    "stock_on_hand": 10,
                    "units_received": 5,
                    "units_sold": 3,
                    "stockout_days": 0,
                    "days_of_supply": 30.0,
                    "fill_rate": 1.0,
                    "stockout_flag": 0,
                    "overstock_flag": 0,
                    "reorder_flag": 0,
                    "sell_through_rate": 0.3,
                    "product_name": " Shirt ",
                    "category": " Apparel ",
                    "segment": " Casual ",
                    "year": 2024,
                    "month": 1,
                }
            ]
        ),
        "web_traffic": pd.DataFrame(
            [
                {
                    "date": "2024-01-02",
                    "sessions": 100,
                    "unique_visitors": 80,
                    "page_views": 200,
                    "bounce_rate": 0.5,
                    "avg_session_duration_sec": 60.0,
                    "traffic_source": " Organic ",
                }
            ]
        ),
    }


def test_assessor_reports_missing_duplicates_orphans_and_business_rule_flags():
    assessor = DataQualityAssessor(build_sample_tables())
    reports = assessor.generate_reports()

    completeness = reports["completeness"]
    uniqueness = reports["uniqueness"]
    referential = reports["referential_integrity"]
    validity = reports["validity"]
    accuracy = reports["accuracy"]

    promo_missing = completeness.loc[
        (completeness["table_name"] == "order_items")
        & (completeness["column_name"] == "promo_id"),
        "missing_count",
    ].iloc[0]
    assert promo_missing == 1

    customer_pk_unique = uniqueness.loc[
        (uniqueness["table_name"] == "customers")
        & (uniqueness["check_name"] == "pk_uniqueness"),
        "invalid_count",
    ].iloc[0]
    assert customer_pk_unique == 1

    orphan_orders = referential.loc[
        referential["check_name"] == "orders.customer_id -> customers.customer_id",
        "orphan_count",
    ].iloc[0]
    assert orphan_orders == 1

    invalid_signup_dates = validity.loc[
        (validity["table_name"] == "customers")
        & (validity["column_name"] == "signup_date"),
        "invalid_count",
    ].iloc[0]
    assert invalid_signup_dates == 2

    invalid_quantity = accuracy.loc[
        accuracy["check_name"] == "order_items.quantity > 0",
        "invalid_count",
    ].iloc[0]
    assert invalid_quantity == 1


def test_cleaner_fills_normalizes_deduplicates_and_generates_order_item_id():
    cleaner = DataCleaner(build_sample_tables())
    cleaned_tables, summary = cleaner.clean()

    order_items = cleaned_tables["order_items"]
    customers = cleaned_tables["customers"]
    inventory = cleaned_tables["inventory"]
    reviews = cleaned_tables["reviews"]
    promotions = cleaned_tables["promotions"]

    assert order_items["order_item_id"].tolist() == [1, 2]
    assert order_items["discount_amount"].tolist()[0] == 0.0
    assert order_items["promo_id"].tolist()[0] == "NO_PROMO"
    assert customers["customer_id"].tolist() == [1]
    assert "city" not in customers.columns
    assert set(["product_name", "category", "segment"]).isdisjoint(inventory.columns)
    assert "customer_id" not in reviews.columns
    assert promotions["promo_id"].tolist()[0] == "NO_PROMO"
    assert order_items["promo_id"].tolist()[1] == "PROMO1"
    assert order_items["order_id"].tolist() == [10, 11]

    before_after = summary.set_index("table_name")
    assert before_after.loc["customers", "rows_before"] == 3
    assert before_after.loc["customers", "rows_after"] == 1
