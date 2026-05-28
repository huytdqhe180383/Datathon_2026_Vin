from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from forecasting.config import DEFAULT_KNOT1, DEFAULT_KNOT2
from forecasting.direct_seasonal_delta import DirectSeasonalDeltaForecaster
from forecasting.io import build_submission_frame, load_sales, load_sample_submission, validate_submission_shape
from forecasting.regime import RegimeConfig


def train_single_target(
    sales: pd.DataFrame,
    target_col: str,
    test_dates: pd.Series,
    regime: RegimeConfig,
    model_kind: str,
) -> pd.Series:
    train_df = sales[["Date", target_col]].copy().sort_values("Date")
    train_series = pd.Series(train_df[target_col].values, index=train_df["Date"])
    model = DirectSeasonalDeltaForecaster(model_kind=model_kind, regime=regime).fit(train_series)
    return model.predict(train_series, test_dates)


def run(data_dir: Path, out_file: Path, knot1: str, knot2: str, model_kind: str) -> Path:
    sales = load_sales(data_dir)
    sample_sub = load_sample_submission(data_dir)
    regime = RegimeConfig(pd.Timestamp(knot1), pd.Timestamp(knot2))
    regime.validate()

    revenue_pred = train_single_target(sales, "Revenue", sample_sub["Date"], regime, model_kind)
    cogs_pred = train_single_target(sales, "COGS", sample_sub["Date"], regime, model_kind)

    submission = build_submission_frame(sample_sub["Date"], revenue_pred, cogs_pred)
    validate_submission_shape(submission, sample_sub)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    submission.to_csv(out_file, index=False)
    return out_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Train direct seasonal-delta linear model and write one Kaggle submission CSV.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-file", type=Path, default=Path("submissions/submission_direct_ridge_seasonal_delta.csv"))
    parser.add_argument("--knot1", type=str, default=DEFAULT_KNOT1)
    parser.add_argument("--knot2", type=str, default=DEFAULT_KNOT2)
    parser.add_argument("--model-kind", choices=["ridge", "elasticnet"], default="ridge")
    args = parser.parse_args()

    out_file = run(args.data_dir, args.out_file, args.knot1, args.knot2, args.model_kind)
    print(f"Wrote: {out_file.resolve()}")


if __name__ == "__main__":
    main()
