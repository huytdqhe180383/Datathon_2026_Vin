from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

import two_pass_forecast as tpf


def seasonal_naive_forecast(train_series: pd.Series, valid_dates: pd.Series, lag: int = 365) -> pd.Series:
    train = pd.Series(train_series.values, index=pd.to_datetime(train_series.index)).sort_index()
    preds = []
    for d in pd.to_datetime(valid_dates):
        v = train.get(d - pd.Timedelta(days=lag), np.nan)
        if pd.isna(v):
            v = train.iloc[-1]
        preds.append(float(v))
    return pd.Series(preds, index=pd.to_datetime(valid_dates))


def pass2_oracle_predict(
    train_series: pd.Series,
    valid_dates: pd.Series,
    valid_true: pd.Series,
    baseline_model: tpf.TrendSeasonalForecaster,
    residual_model,
    feature_cols: list[str],
) -> pd.Series:
    full_hist = pd.concat([train_series, valid_true]).sort_index()
    start_date = full_hist.index.min()
    preds: dict[pd.Timestamp, float] = {}
    for d in pd.to_datetime(valid_dates):
        base = float(baseline_model.predict([d])[0])
        row = tpf.single_feature_row(full_hist, d, base, start_date)
        X = pd.DataFrame([row]).reindex(columns=feature_cols)
        for c in X.columns:
            if X[c].isna().any():
                if c.startswith("lag_") or c.startswith("roll_"):
                    X[c] = X[c].fillna(base)
                else:
                    X[c] = X[c].fillna(0.0)
        resid = float(residual_model.predict(X)[0])
        preds[d] = max(0.0, base + resid)
    return pd.Series(preds).sort_index()


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    sales = pd.read_csv(root / "data" / "raw" / "sales.csv", parse_dates=["Date"]).sort_values("Date")
    report_dir = root / "reports" / "forecasting" / "diagnostics"
    report_dir.mkdir(parents=True, exist_ok=True)

    cutoffs = ["2019-12-31", "2020-12-31", "2021-06-30", "2021-12-31"]
    rows_horizon = []
    rows_oracle = []
    rows_dist = []

    for cutoff_str in cutoffs:
        cutoff = pd.Timestamp(cutoff_str)
        train_df = sales[sales["Date"] <= cutoff][["Date", "Revenue"]].copy()
        valid_df = sales[(sales["Date"] > cutoff) & (sales["Date"] <= cutoff + pd.Timedelta(days=365))][
            ["Date", "Revenue"]
        ].copy()
        if valid_df.empty:
            continue

        y_train = pd.Series(train_df["Revenue"].values, index=train_df["Date"])
        y_valid = pd.Series(valid_df["Revenue"].values, index=valid_df["Date"])

        pass1 = tpf.TrendSeasonalForecaster(alpha=2.0).fit(train_df["Date"], train_df["Revenue"])
        pass1_pred = pd.Series(pass1.predict(valid_df["Date"]), index=valid_df["Date"])

        X_res, y_res = tpf.build_residual_training_frame(y_train, pass1)
        pass2_model = tpf.fit_lightgbm_residual_model(X_res, y_res)
        pass2_pred = tpf.predict_hybrid_recursive(
            y_train, valid_df["Date"], pass1, pass2_model, X_res.columns.tolist()
        )

        seasonal_pred = seasonal_naive_forecast(y_train, valid_df["Date"], lag=365)

        for model_name, pred in [
            ("pass_1_trend_fourier", pass1_pred),
            ("pass_2_hybrid_lgbm", pass2_pred),
            ("seasonal_naive_365", seasonal_pred),
        ]:
            e = np.abs(y_valid.values - pred.values)
            rows_horizon.append(
                {
                    "fold": cutoff_str,
                    "model": model_name,
                    "mae_all": float(e.mean()),
                    "mae_1_30": float(e[:30].mean()),
                    "mae_31_90": float(e[30:90].mean()),
                    "mae_91_180": float(e[90:180].mean()),
                    "mae_181_365": float(e[180:].mean()),
                    "pred_mean": float(pred.mean()),
                    "true_mean": float(y_valid.mean()),
                    "mean_error_pred_minus_true": float((pred.values - y_valid.values).mean()),
                }
            )

        oracle_pred = pass2_oracle_predict(
            y_train, valid_df["Date"], y_valid, pass1, pass2_model, X_res.columns.tolist()
        )
        rows_oracle.append(
            {
                "fold": cutoff_str,
                "mae_recursive": float(np.mean(np.abs(y_valid.values - pass2_pred.values))),
                "mae_oracle_lags": float(np.mean(np.abs(y_valid.values - oracle_pred.values))),
                "recursive_minus_oracle_gap": float(
                    np.mean(np.abs(y_valid.values - pass2_pred.values))
                    - np.mean(np.abs(y_valid.values - oracle_pred.values))
                ),
                "recursive_bias_mean_error": float((pass2_pred.values - y_valid.values).mean()),
            }
        )

        # Distribution-level failure analysis for latest fold only (closest to leaderboard regime)
        if cutoff_str == "2021-12-31":
            err = pass2_pred.values - y_valid.values
            aerr = np.abs(err)
            q = pd.qcut(y_valid, 5, duplicates="drop")
            q_df = pd.DataFrame({"actual": y_valid.values, "aerr": aerr, "err": err, "bin": q.astype(str).values})
            grp = q_df.groupby("bin").agg(n=("aerr", "size"), mae=("aerr", "mean"), bias=("err", "mean")).reset_index()
            grp["fold"] = cutoff_str
            rows_dist.extend(grp.to_dict(orient="records"))

    horizon_df = pd.DataFrame(rows_horizon)
    oracle_df = pd.DataFrame(rows_oracle)
    dist_df = pd.DataFrame(rows_dist)

    horizon_df.to_csv(report_dir / "error_horizon_diagnostics.csv", index=False)
    oracle_df.to_csv(report_dir / "recursive_vs_oracle_diagnostics.csv", index=False)
    dist_df.to_csv(report_dir / "error_by_actual_quantile_latest_fold.csv", index=False)

    # Compact summary for quick reading
    summary = (
        horizon_df.groupby("model")[["mae_all", "mae_1_30", "mae_31_90", "mae_91_180", "mae_181_365"]]
        .mean()
        .sort_values("mae_all")
        .reset_index()
    )
    summary.to_csv(report_dir / "error_horizon_summary.csv", index=False)

    print("Wrote diagnostics:")
    print((report_dir / "error_horizon_diagnostics.csv").resolve())
    print((report_dir / "recursive_vs_oracle_diagnostics.csv").resolve())
    print((report_dir / "error_by_actual_quantile_latest_fold.csv").resolve())
    print((report_dir / "error_horizon_summary.csv").resolve())
    print("\nHorizon summary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    run()
