from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from forecasting import (
    DEFAULT_FINAL_HOLDOUT_CUTOFF,
    DEFAULT_HORIZON_DAYS,
    DEFAULT_KNOT1,
    DEFAULT_KNOT1_GRID,
    DEFAULT_KNOT2,
    DEFAULT_KNOT2_GRID,
    DEFAULT_TUNE_CUTOFFS,
    DIRECT_HORIZON_BUCKETS,
    RegimeConfig,
    TrendSeasonalForecaster,
    blend_with_seasonal_anchor,
    bucket_bounds,
    bucket_name_for_horizon,
    build_residual_training_frame,
    build_sample_weights,
    build_trend_design_matrix,
    ensure_datetime_index,
    estimate_recent_growth_multiplier,
    fit_lightgbm_residual_model,
    growth_adjusted_anchor_forecast,
    make_seasonal_blend_weights,
    median_ensemble,
    parse_date_grid,
    predict_hybrid_recursive,
    reconstruct_from_seasonal_delta,
    seasonal_naive_forecast,
    single_feature_row,
    validate_regime_features,
)
from train_direct_elasticnet_seasonal_delta import run as run_direct_elasticnet
from train_direct_ridge_seasonal_delta import run as run_direct_ridge
from train_hybrid_regime_lgbm import run as run_hybrid_regime_lgbm
from train_trend_hinge import run as run_trend_hinge


MODEL_DEFAULT_OUTFILES = {
    "trend_hinge_ridge": Path("submissions/submission_trend_hinge_ridge.csv"),
    "hybrid_regime_lgbm": Path("submissions/submission_hybrid_regime_lgbm.csv"),
    "direct_ridge_seasonal_delta": Path("submissions/submission_direct_ridge_seasonal_delta.csv"),
    "direct_elasticnet_seasonal_delta": Path("submissions/submission_direct_elasticnet_seasonal_delta.csv"),
}


def _run_trend_hinge(data_dir: Path, out_file: Path, knot1: str, knot2: str, residual_val_days: int) -> Path:
    _ = residual_val_days
    return run_trend_hinge(data_dir, out_file, knot1, knot2)


def _run_hybrid(data_dir: Path, out_file: Path, knot1: str, knot2: str, residual_val_days: int) -> Path:
    return run_hybrid_regime_lgbm(data_dir, out_file, knot1, knot2, residual_val_days)


def _run_direct_ridge(data_dir: Path, out_file: Path, knot1: str, knot2: str, residual_val_days: int) -> Path:
    _ = residual_val_days
    return run_direct_ridge(data_dir, out_file, knot1, knot2)


def _run_direct_elasticnet(data_dir: Path, out_file: Path, knot1: str, knot2: str, residual_val_days: int) -> Path:
    _ = residual_val_days
    return run_direct_elasticnet(data_dir, out_file, knot1, knot2)


MODEL_RUNNERS: dict[str, Callable[[Path, Path, str, str, int], Path]] = {
    "trend_hinge_ridge": _run_trend_hinge,
    "hybrid_regime_lgbm": _run_hybrid,
    "direct_ridge_seasonal_delta": _run_direct_ridge,
    "direct_elasticnet_seasonal_delta": _run_direct_elasticnet,
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Single-model forecast trainer. Use --model to train one algorithm and write one submission CSV."
    )
    parser.add_argument("--model", choices=sorted(MODEL_RUNNERS.keys()), default="hybrid_regime_lgbm")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-file", type=Path, default=None, help="Optional explicit output CSV path.")
    parser.add_argument("--knot1", type=str, default=DEFAULT_KNOT1)
    parser.add_argument("--knot2", type=str, default=DEFAULT_KNOT2)
    parser.add_argument(
        "--residual-val-days",
        type=int,
        default=180,
        help="Hybrid residual validation window. Ignored by non-hybrid models.",
    )
    args = parser.parse_args()

    out_file = args.out_file if args.out_file is not None else MODEL_DEFAULT_OUTFILES[args.model]
    out_path = MODEL_RUNNERS[args.model](args.data_dir, out_file, args.knot1, args.knot2, args.residual_val_days)
    print(f"Model: {args.model}")
    print(f"Wrote: {out_path.resolve()}")


if __name__ == "__main__":
    main()
