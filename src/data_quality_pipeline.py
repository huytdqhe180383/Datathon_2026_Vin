from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd


TABLE_SPECS: "OrderedDict[str, dict[str, Any]]" = OrderedDict(
    {
        "customers": {
            "filename": "customers.csv",
            "pk": ["customer_id"],
            "fk": ["zip"],
            "date_columns": ["signup_date"],
            "categorical_columns": ["city", "gender", "age_group", "acquisition_channel"],
            "drop_columns": ["city"],
            "dtype": {
                "customer_id": "Int32",
                "zip": "Int32",
                "city": "string",
                "signup_date": "string",
                "gender": "string",
                "age_group": "string",
                "acquisition_channel": "string",
            },
        },
        "geography": {
            "filename": "geography.csv",
            "pk": ["zip"],
            "fk": [],
            "date_columns": [],
            "categorical_columns": ["city", "region", "district"],
            "drop_columns": [],
            "dtype": {
                "zip": "Int32",
                "city": "string",
                "region": "string",
                "district": "string",
            },
        },
        "inventory": {
            "filename": "inventory.csv",
            "pk": ["snapshot_date", "product_id"],
            "fk": ["product_id"],
            "date_columns": ["snapshot_date"],
            "categorical_columns": ["category", "segment"],
            "drop_columns": ["product_name", "category", "segment"],
            "dtype": {
                "snapshot_date": "string",
                "product_id": "Int32",
                "stock_on_hand": "Int32",
                "units_received": "Int32",
                "units_sold": "Int32",
                "stockout_days": "Int32",
                "days_of_supply": "Float64",
                "fill_rate": "Float64",
                "stockout_flag": "Int8",
                "overstock_flag": "Int8",
                "reorder_flag": "Int8",
                "sell_through_rate": "Float64",
                "product_name": "string",
                "category": "string",
                "segment": "string",
                "year": "Int16",
                "month": "Int8",
            },
        },
        "orders": {
            "filename": "orders.csv",
            "pk": ["order_id"],
            "fk": ["customer_id", "zip"],
            "date_columns": ["order_date"],
            "categorical_columns": ["order_status", "payment_method", "device_type", "order_source"],
            "drop_columns": [],
            "dtype": {
                "order_id": "Int32",
                "order_date": "string",
                "customer_id": "Int32",
                "zip": "Int32",
                "order_status": "string",
                "payment_method": "string",
                "device_type": "string",
                "order_source": "string",
            },
        },
        "order_items": {
            "filename": "order_items.csv",
            "pk": [],
            "fk": ["order_id", "product_id"],
            "date_columns": [],
            "categorical_columns": [],
            "drop_columns": [],
            "dtype": {
                "order_id": "Int32",
                "product_id": "Int32",
                "quantity": "Int16",
                "unit_price": "Float64",
                "discount_amount": "Float64",
                "promo_id": "string",
                "promo_id_2": "string",
            },
        },
        "payments": {
            "filename": "payments.csv",
            "pk": ["order_id"],
            "fk": ["order_id"],
            "date_columns": [],
            "categorical_columns": ["payment_method"],
            "drop_columns": [],
            "dtype": {
                "order_id": "Int32",
                "payment_method": "string",
                "payment_value": "Float64",
                "installments": "Int8",
            },
        },
        "products": {
            "filename": "products.csv",
            "pk": ["product_id"],
            "fk": [],
            "date_columns": [],
            "categorical_columns": ["category", "segment", "size", "color"],
            "drop_columns": [],
            "dtype": {
                "product_id": "Int32",
                "product_name": "string",
                "category": "string",
                "segment": "string",
                "size": "string",
                "color": "string",
                "price": "Float64",
                "cogs": "Float64",
            },
        },
        "promotions": {
            "filename": "promotions.csv",
            "pk": ["promo_id"],
            "fk": [],
            "date_columns": ["start_date", "end_date"],
            "categorical_columns": ["promo_type", "applicable_category", "promo_channel"],
            "drop_columns": [],
            "dtype": {
                "promo_id": "string",
                "promo_name": "string",
                "promo_type": "string",
                "discount_value": "Float64",
                "start_date": "string",
                "end_date": "string",
                "applicable_category": "string",
                "promo_channel": "string",
                "stackable_flag": "Int8",
                "min_order_value": "Float64",
            },
        },
        "returns": {
            "filename": "returns.csv",
            "pk": ["return_id"],
            "fk": ["order_id", "product_id"],
            "date_columns": ["return_date"],
            "categorical_columns": ["return_reason"],
            "drop_columns": [],
            "dtype": {
                "return_id": "string",
                "order_id": "Int32",
                "product_id": "Int32",
                "return_date": "string",
                "return_reason": "string",
                "return_quantity": "Int16",
                "refund_amount": "Float64",
            },
        },
        "reviews": {
            "filename": "reviews.csv",
            "pk": ["review_id"],
            "fk": ["order_id", "product_id", "customer_id"],
            "date_columns": ["review_date"],
            "categorical_columns": [],
            "drop_columns": ["customer_id"],
            "dtype": {
                "review_id": "string",
                "order_id": "Int32",
                "product_id": "Int32",
                "customer_id": "Int32",
                "review_date": "string",
                "rating": "Int8",
                "review_title": "string",
            },
        },
        "sales": {
            "filename": "sales.csv",
            "pk": ["Date"],
            "fk": [],
            "date_columns": ["Date"],
            "categorical_columns": [],
            "drop_columns": [],
            "dtype": {
                "Date": "string",
                "Revenue": "Float64",
                "COGS": "Float64",
            },
        },
        "shipments": {
            "filename": "shipments.csv",
            "pk": ["order_id"],
            "fk": ["order_id"],
            "date_columns": ["ship_date", "delivery_date"],
            "categorical_columns": [],
            "drop_columns": [],
            "dtype": {
                "order_id": "Int32",
                "ship_date": "string",
                "delivery_date": "string",
                "shipping_fee": "Float64",
            },
        },
        "web_traffic": {
            "filename": "web_traffic.csv",
            "pk": ["date"],
            "fk": [],
            "date_columns": ["date"],
            "categorical_columns": ["traffic_source"],
            "drop_columns": [],
            "dtype": {
                "date": "string",
                "sessions": "Int32",
                "unique_visitors": "Int32",
                "page_views": "Int32",
                "bounce_rate": "Float64",
                "avg_session_duration_sec": "Float64",
                "traffic_source": "string",
            },
        },
    }
)


REFERENTIAL_CHECKS = [
    ("orders.customer_id -> customers.customer_id", "orders", "customer_id", "customers", "customer_id"),
    ("order_items.product_id -> products.product_id", "order_items", "product_id", "products", "product_id"),
    ("customers.zip -> geography.zip", "customers", "zip", "geography", "zip"),
    ("orders.zip -> geography.zip", "orders", "zip", "geography", "zip"),
]


def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for table_name, spec in TABLE_SPECS.items():
        csv_path = raw_dir / spec["filename"]
        tables[table_name] = pd.read_csv(
            csv_path,
            low_memory=False,
            dtype=spec["dtype"],
        )
    return tables


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    for column in cleaned.columns:
        if pd.api.types.is_string_dtype(cleaned[column]) or cleaned[column].dtype == object:
            cleaned[column] = cleaned[column].astype("string").str.strip()
    return cleaned


def _parse_dates(df: pd.DataFrame, date_columns: list[str]) -> pd.DataFrame:
    parsed = df.copy()
    for column in date_columns:
        parsed[column] = pd.to_datetime(parsed[column], errors="coerce")
    return parsed


class DataQualityAssessor:
    def __init__(self, tables: dict[str, pd.DataFrame]) -> None:
        self.tables = {name: df.copy() for name, df in tables.items()}

    def generate_reports(self) -> dict[str, pd.DataFrame]:
        return {
            "completeness": self._completeness_report(),
            "uniqueness": self._uniqueness_report(),
            "referential_integrity": self._referential_integrity_report(),
            "validity": self._validity_report(),
            "accuracy": self._accuracy_report(),
        }

    def save_reports(self, output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: dict[str, Path] = {}
        for report_name, report_df in self.generate_reports().items():
            path = output_dir / f"{report_name}.csv"
            report_df.to_csv(path, index=False)
            saved[report_name] = path
        return saved

    def _completeness_report(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for table_name, df in self.tables.items():
            total_rows = len(df)
            for column_name in df.columns:
                missing_count = int(df[column_name].isna().sum())
                missing_pct = (missing_count / total_rows * 100.0) if total_rows else 0.0
                rows.append(
                    {
                        "table_name": table_name,
                        "column_name": column_name,
                        "row_count": total_rows,
                        "missing_count": missing_count,
                        "missing_pct": round(missing_pct, 4),
                    }
                )
        return pd.DataFrame(rows)

    def _uniqueness_report(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for table_name, df in self.tables.items():
            duplicate_rows = int(df.duplicated().sum())
            rows.append(
                {
                    "table_name": table_name,
                    "check_name": "exact_duplicate_rows",
                    "invalid_count": duplicate_rows,
                    "invalid_pct": round((duplicate_rows / len(df) * 100.0) if len(df) else 0.0, 4),
                }
            )

            pk_columns = TABLE_SPECS[table_name]["pk"]
            if pk_columns:
                pk_duplicate_count = int(df[df[pk_columns].notna().all(axis=1)].duplicated(subset=pk_columns).sum())
                rows.append(
                    {
                        "table_name": table_name,
                        "check_name": "pk_uniqueness",
                        "invalid_count": pk_duplicate_count,
                        "invalid_pct": round((pk_duplicate_count / len(df) * 100.0) if len(df) else 0.0, 4),
                        "pk_columns": ",".join(pk_columns),
                    }
                )
        return pd.DataFrame(rows)

    def _referential_integrity_report(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for check_name, child_table, child_column, parent_table, parent_column in REFERENTIAL_CHECKS:
            child_series = self.tables[child_table][child_column]
            parent_values = set(self.tables[parent_table][parent_column].dropna().tolist())
            child_not_null = child_series.dropna()
            orphan_mask = ~child_not_null.isin(parent_values)
            orphan_count = int(orphan_mask.sum())
            total_checked = int(len(child_not_null))
            orphan_pct = (orphan_count / total_checked * 100.0) if total_checked else 0.0
            rows.append(
                {
                    "check_name": check_name,
                    "child_table": child_table,
                    "child_column": child_column,
                    "parent_table": parent_table,
                    "parent_column": parent_column,
                    "checked_count": total_checked,
                    "orphan_count": orphan_count,
                    "orphan_pct": round(orphan_pct, 4),
                }
            )
        return pd.DataFrame(rows)

    def _validity_report(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for table_name, spec in TABLE_SPECS.items():
            df = self.tables[table_name]
            for column in spec["date_columns"]:
                parsed = pd.to_datetime(df[column], errors="coerce")
                invalid_count = int(df[column].notna().sum() - parsed.notna().sum())
                rows.append(
                    {
                        "table_name": table_name,
                        "column_name": column,
                        "invalid_count": invalid_count,
                        "invalid_pct": round((invalid_count / len(df) * 100.0) if len(df) else 0.0, 4),
                    }
                )
        return pd.DataFrame(rows)

    def _accuracy_report(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        order_items = self.tables["order_items"].copy()
        shipments = self.tables["shipments"].copy()
        orders = self.tables["orders"].copy()

        rows.append(self._metric_row("order_items.quantity > 0", order_items["quantity"] <= 0))
        rows.append(self._metric_row("order_items.unit_price > 0", order_items["unit_price"] <= 0))

        discount_amount = order_items["discount_amount"].fillna(0)
        gross_value = order_items["unit_price"].fillna(0) * order_items["quantity"].fillna(0)
        rows.append(self._metric_row("order_items.discount_amount <= quantity * unit_price", discount_amount > gross_value))

        orders_with_dates = _parse_dates(orders, TABLE_SPECS["orders"]["date_columns"])
        shipments_with_dates = _parse_dates(shipments, TABLE_SPECS["shipments"]["date_columns"])
        shipment_join = shipments_with_dates.merge(
            orders_with_dates[["order_id", "order_date"]],
            on="order_id",
            how="left",
        )
        rows.append(self._metric_row("shipments.ship_date >= orders.order_date", shipment_join["ship_date"] < shipment_join["order_date"]))
        return pd.DataFrame(rows)

    @staticmethod
    def _metric_row(check_name: str, invalid_mask: pd.Series) -> dict[str, Any]:
        invalid_count = int(invalid_mask.fillna(False).sum())
        total_checked = int(len(invalid_mask))
        return {
            "check_name": check_name,
            "checked_count": total_checked,
            "invalid_count": invalid_count,
            "invalid_pct": round((invalid_count / total_checked * 100.0) if total_checked else 0.0, 4),
        }


class DataCleaner:
    def __init__(self, tables: dict[str, pd.DataFrame]) -> None:
        self.raw_tables = {name: df.copy() for name, df in tables.items()}

    def clean(self) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
        cleaned_tables = {name: df.copy() for name, df in self.raw_tables.items()}
        rows_before = {name: len(df) for name, df in cleaned_tables.items()}

        cleaned_tables = self._fill_missing_values(cleaned_tables)
        cleaned_tables = self._normalize_strings(cleaned_tables)
        cleaned_tables = self._parse_date_columns(cleaned_tables)
        cleaned_tables = self._drop_null_key_rows(cleaned_tables)
        cleaned_tables = self._deduplicate(cleaned_tables)
        cleaned_tables = self._normalize_schema(cleaned_tables)
        cleaned_tables = self._generate_order_item_id(cleaned_tables)
        cleaned_tables = self._optimize_categoricals(cleaned_tables)

        summary_rows: list[dict[str, Any]] = []
        for table_name, df in cleaned_tables.items():
            rows_after = len(df)
            net_change = rows_after - rows_before[table_name]
            summary_rows.append(
                {
                    "table_name": table_name,
                    "rows_before": rows_before[table_name],
                    "rows_after": rows_after,
                    "rows_removed": max(rows_before[table_name] - rows_after, 0),
                    "rows_added": max(rows_after - rows_before[table_name], 0),
                    "net_change": net_change,
                }
            )
        summary = pd.DataFrame(summary_rows).sort_values("table_name").reset_index(drop=True)
        return cleaned_tables, summary

    def save_cleaned_tables(self, cleaned_tables: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths: dict[str, Path] = {}
        for table_name, spec in TABLE_SPECS.items():
            file_path = output_dir / spec["filename"]
            cleaned_tables[table_name].to_csv(file_path, index=False, date_format="%Y-%m-%d")
            saved_paths[table_name] = file_path
        return saved_paths

    @staticmethod
    def save_summary(summary: pd.DataFrame, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        summary.to_csv(output_path, index=False)

    @staticmethod
    def print_summary(summary: pd.DataFrame) -> None:
        print(summary.to_string(index=False))

    def _fill_missing_values(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        order_items = tables["order_items"].copy()
        order_items["discount_amount"] = order_items["discount_amount"].fillna(0.0)
        order_items["promo_id"] = order_items["promo_id"].fillna("NO_PROMO")
        tables["order_items"] = order_items

        promotions = tables["promotions"].copy()
        has_no_promo = promotions["promo_id"].fillna("").eq("NO_PROMO").any()
        if not has_no_promo:
            no_promo_row = pd.DataFrame(
                [
                    {
                        "promo_id": "NO_PROMO",
                        "promo_name": "no_promo",
                        "promo_type": "no_promo",
                        "discount_value": 0.0,
                        "start_date": pd.NA,
                        "end_date": pd.NA,
                        "applicable_category": pd.NA,
                        "promo_channel": "none",
                        "stackable_flag": 0,
                        "min_order_value": 0.0,
                    }
                ]
            ).astype(promotions.dtypes.to_dict())
            promotions = pd.concat([no_promo_row, promotions], ignore_index=True)
        tables["promotions"] = promotions
        return tables

    def _normalize_strings(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        normalized: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            stripped = _strip_strings(df)
            for column in TABLE_SPECS[table_name]["categorical_columns"]:
                stripped[column] = stripped[column].astype("string").str.lower()
            normalized[table_name] = stripped
        return normalized

    def _parse_date_columns(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        parsed: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            parsed[table_name] = _parse_dates(df, TABLE_SPECS[table_name]["date_columns"])
        return parsed

    def _drop_null_key_rows(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        cleaned: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            key_columns = TABLE_SPECS[table_name]["pk"] + TABLE_SPECS[table_name]["fk"]
            if key_columns:
                cleaned[table_name] = df.dropna(subset=key_columns).reset_index(drop=True)
            else:
                cleaned[table_name] = df.reset_index(drop=True)
        return cleaned

    def _deduplicate(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        deduped: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            deduped[table_name] = df.drop_duplicates().reset_index(drop=True)
        return deduped

    def _normalize_schema(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        normalized: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            drop_columns = [column for column in TABLE_SPECS[table_name]["drop_columns"] if column in df.columns]
            normalized[table_name] = df.drop(columns=drop_columns).reset_index(drop=True)
        return normalized

    @staticmethod
    def _generate_order_item_id(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        order_items = tables["order_items"].copy()
        order_items.insert(0, "order_item_id", range(1, len(order_items) + 1))
        tables["order_items"] = order_items
        return tables

    def _optimize_categoricals(self, tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        optimized: dict[str, pd.DataFrame] = {}
        for table_name, df in tables.items():
            compact = df.copy()
            for column in TABLE_SPECS[table_name]["categorical_columns"]:
                if column in compact.columns:
                    compact[column] = compact[column].astype("category")
            optimized[table_name] = compact
        return optimized


def run_pipeline(raw_dir: Path, processed_dir: Path) -> None:
    tables = load_raw_tables(raw_dir)

    assessor = DataQualityAssessor(tables)
    dq_report_dir = processed_dir / "dq_reports"
    assessor.save_reports(dq_report_dir)

    cleaner = DataCleaner(tables)
    cleaned_tables, summary = cleaner.clean()
    cleaner.save_cleaned_tables(cleaned_tables, processed_dir)
    cleaner.save_summary(summary, processed_dir / "row_count_summary.csv")
    cleaner.print_summary(summary)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Assess and clean ecommerce CSV datasets.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_pipeline(args.raw_dir, args.processed_dir)


if __name__ == "__main__":
    main()
