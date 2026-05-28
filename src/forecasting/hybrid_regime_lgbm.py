from __future__ import annotations

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor, early_stopping

from forecasting.config import LAGS, ROLL_WINDOWS, SEED
from forecasting.regime import RegimeConfig, build_regime_feature_frame
from forecasting.trend_hinge import TrendSeasonalForecaster
from forecasting.utils import build_sample_weights, ensure_datetime_index


def single_feature_row(
    history: pd.Series,
    current_date: pd.Timestamp,
    baseline_value: float,
    start_date: pd.Timestamp,
    regime: RegimeConfig,
) -> dict[str, float]:
    hist = ensure_datetime_index(history.astype(float))
    d = pd.Timestamp(current_date)

    row: dict[str, float] = {}
    for lag in LAGS:
        row[f"lag_{lag}"] = float(hist.get(d - pd.Timedelta(days=lag), np.nan))

    for window in ROLL_WINDOWS:
        recent = hist.loc[(hist.index < d) & (hist.index >= d - pd.Timedelta(days=window))]
        row[f"roll_mean_{window}"] = float(recent.mean()) if len(recent) else np.nan
        row[f"roll_std_{window}"] = float(recent.std()) if len(recent) else np.nan

    ds = pd.Series([d])
    t_days = float((d - pd.Timestamp(start_date)).days)
    row["t_days"] = t_days
    row["t_years"] = t_days / 365.25
    row["month"] = int(d.month)
    row["dow"] = int(d.dayofweek)
    row["doy"] = int(d.dayofyear)
    row["is_weekend"] = int(d.dayofweek >= 5)
    row["is_month_end"] = int(d.is_month_end)
    row["is_month_start"] = int(d.is_month_start)

    for k in (1, 2, 3):
        row[f"sin_{k}"] = float(np.sin(2 * np.pi * k * row["doy"] / 365.25))
        row[f"cos_{k}"] = float(np.cos(2 * np.pi * k * row["doy"] / 365.25))

    lag_1 = row.get("lag_1", np.nan)
    lag_7 = row.get("lag_7", np.nan)
    row["lag_diff_1_7"] = lag_1 - lag_7 if not np.isnan(lag_1) and not np.isnan(lag_7) else np.nan
    row["lag_ratio_1_7"] = (
        lag_1 / max(abs(lag_7), 1e-6) if not np.isnan(lag_1) and not np.isnan(lag_7) else np.nan
    )

    for prefix, count in [("m", 12), ("d", 7)]:
        base = row["month"] if prefix == "m" else row["dow"]
        for v in range(1, count):
            row[f"{prefix}_{v}"] = int(base == v)

    regime_row = build_regime_feature_frame(ds, regime).iloc[0].to_dict()
    for k, v in regime_row.items():
        row[k] = float(v)

    row["days_since_knot2"] = max(0.0, float((d - regime.knot2).days))
    roll_mean_28 = row.get("roll_mean_28", np.nan)
    roll_mean_56 = row.get("roll_mean_56", np.nan)
    row["momentum_ratio"] = (
        roll_mean_28 / max(abs(roll_mean_56), 1e-6) if not np.isnan(roll_mean_28) and not np.isnan(roll_mean_56) else np.nan
    )
    lag_365 = row.get("lag_365", np.nan)
    row["yoy_growth_28d"] = (
        roll_mean_28 / max(abs(lag_365), 1e-6) if not np.isnan(roll_mean_28) and not np.isnan(lag_365) else np.nan
    )

    row["baseline"] = baseline_value
    row["baseline_minus_lag1"] = baseline_value - lag_1 if not np.isnan(lag_1) else np.nan
    return row


def build_residual_training_frame(
    y_series: pd.Series,
    baseline_model: TrendSeasonalForecaster,
    return_dates: bool = False,
) -> tuple[pd.DataFrame, pd.Series] | tuple[pd.DataFrame, pd.Series, pd.Series]:
    if baseline_model.regime is None or baseline_model.start_date is None:
        raise ValueError("Baseline model must be fitted with a regime configuration before residual frame creation.")

    y = ensure_datetime_index(y_series.astype(float))
    dates = pd.Series(y.index)
    baseline_pred = baseline_model.predict(dates)
    baseline_map = dict(zip(dates, baseline_pred))

    rows = []
    for d in dates:
        row = single_feature_row(
            history=y,
            current_date=d,
            baseline_value=float(baseline_map[d]),
            start_date=baseline_model.start_date,
            regime=baseline_model.regime,
        )
        row["date"] = d
        row["residual"] = float(y.loc[d] - baseline_map[d])
        rows.append(row)

    frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    frame = frame.dropna().reset_index(drop=True)
    y_resid = frame["residual"].copy()
    X = frame.drop(columns=["date", "residual"])
    dts = frame["date"].copy()
    if return_dates:
        return X, y_resid, dts
    return X, y_resid


def fit_lightgbm_residual_model(
    X: pd.DataFrame,
    y: pd.Series,
    dates: pd.Series | None = None,
    residual_val_days: int = 180,
    use_sample_weight: bool = False,
) -> LGBMRegressor:
    if dates is None:
        date_series = pd.Series(pd.RangeIndex(start=0, stop=len(X), step=1))
    else:
        date_series = pd.Series(dates).reset_index(drop=True)

    X_ = X.reset_index(drop=True)
    y_ = y.reset_index(drop=True)

    model = LGBMRegressor(
        objective="regression",
        metric="l1",
        n_estimators=2500,
        learning_rate=0.03,
        num_leaves=31,
        max_depth=-1,
        min_child_samples=30,
        subsample=0.9,
        subsample_freq=1,
        colsample_bytree=0.9,
        reg_alpha=0.05,
        reg_lambda=0.2,
        random_state=SEED,
        verbosity=-1,
    )

    sample_weight = None
    if use_sample_weight:
        sample_weight = build_sample_weights(date_series)

    use_early_stopping = False
    train_mask: pd.Series | None = None
    val_mask: pd.Series | None = None
    if len(X_) >= residual_val_days + 200:
        if np.issubdtype(date_series.dtype, np.datetime64):
            cutoff = pd.Timestamp(date_series.max()) - pd.Timedelta(days=residual_val_days)
            train_mask = pd.to_datetime(date_series) <= cutoff
        else:
            split_at = len(X_) - residual_val_days
            train_mask = pd.Series(np.arange(len(X_)) < split_at)

        val_mask = ~train_mask
        if train_mask.sum() >= 200 and val_mask.sum() >= 50:
            use_early_stopping = True

    if use_early_stopping and train_mask is not None and val_mask is not None:
        X_train = X_.loc[train_mask].copy()
        y_train = y_.loc[train_mask].copy()
        X_val = X_.loc[val_mask].copy()
        y_val = y_.loc[val_mask].copy()
        callbacks = [early_stopping(100, first_metric_only=True, verbose=False)]
        if sample_weight is not None:
            sw = np.asarray(sample_weight)
            sw_train = sw[train_mask.values]
            sw_val = sw[val_mask.values]
            model.fit(
                X_train,
                y_train,
                sample_weight=sw_train,
                eval_set=[(X_val, y_val)],
                eval_sample_weight=[sw_val],
                eval_metric="l1",
                callbacks=callbacks,
            )
        else:
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                eval_metric="l1",
                callbacks=callbacks,
            )
    else:
        model.fit(X_, y_, sample_weight=sample_weight)

    return model


def predict_hybrid_recursive(
    history: pd.Series,
    future_dates: pd.Series,
    baseline_model: TrendSeasonalForecaster,
    residual_model: LGBMRegressor,
    feature_columns: list[str],
) -> pd.Series:
    if baseline_model.regime is None or baseline_model.start_date is None:
        raise ValueError("Baseline model must be fitted before recursive prediction.")

    hist = ensure_datetime_index(history.astype(float))
    future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()

    preds: dict[pd.Timestamp, float] = {}
    for d in future_ds:
        base_val = float(baseline_model.predict([d])[0])
        row = single_feature_row(
            history=hist,
            current_date=d,
            baseline_value=base_val,
            start_date=baseline_model.start_date,
            regime=baseline_model.regime,
        )
        X_row = pd.DataFrame([row]).reindex(columns=feature_columns)

        for col in X_row.columns:
            if X_row[col].isna().any():
                if col.startswith("lag_") or col.startswith("roll_"):
                    X_row[col] = X_row[col].fillna(base_val)
                else:
                    X_row[col] = X_row[col].fillna(0.0)

        resid_hat = float(residual_model.predict(X_row)[0])
        y_hat = max(0.0, base_val + resid_hat)
        preds[d] = y_hat
        hist.loc[d] = y_hat

    return pd.Series(preds).sort_index()
