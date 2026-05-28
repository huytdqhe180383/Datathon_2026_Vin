from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_sales(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "sales.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)


def load_sample_submission(data_dir: Path) -> pd.DataFrame:
    return pd.read_csv(data_dir / "sample_submission.csv", parse_dates=["Date"]).sort_values("Date").reset_index(drop=True)


def build_submission_frame(dates: pd.Series, revenue: pd.Series, cogs: pd.Series) -> pd.DataFrame:
    ds = pd.to_datetime(pd.Series(dates)).sort_values().reset_index(drop=True)
    revenue_aligned = pd.Series(revenue.values, index=pd.to_datetime(revenue.index)).reindex(ds).values
    cogs_aligned = pd.Series(cogs.values, index=pd.to_datetime(cogs.index)).reindex(ds).values
    return pd.DataFrame(
        {
            "Date": ds.dt.strftime("%Y-%m-%d"),
            "Revenue": revenue_aligned,
            "COGS": cogs_aligned,
        }
    )


def validate_submission_shape(submission: pd.DataFrame, sample_sub: pd.DataFrame) -> None:
    if len(submission) != len(sample_sub):
        raise ValueError(f"Submission row count mismatch: expected {len(sample_sub)}, got {len(submission)}")
    expected_dates = sample_sub["Date"].dt.strftime("%Y-%m-%d")
    if not submission["Date"].equals(expected_dates):
        raise ValueError("Submission date order does not match sample_submission.")
    if submission[["Revenue", "COGS"]].isna().any().any():
        raise ValueError("Submission contains missing values.")
    if (submission[["Revenue", "COGS"]] < 0).any().any():
        raise ValueError("Submission contains negative predictions.")
