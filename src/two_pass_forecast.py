from __future__ import annotations

import argparse
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor, early_stopping
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


SEED = 42
LAGS = [1, 2, 3, 7, 14, 28, 30, 56, 90, 182, 365]
ROLL_WINDOWS = [7, 14, 28, 56]
DEFAULT_HORIZON_DAYS = 548
DEFAULT_TUNE_CUTOFFS = ["2018-06-30", "2019-06-30", "2020-06-30"]
DEFAULT_FINAL_HOLDOUT_CUTOFF = "2021-06-30"
DEFAULT_KNOT1_GRID = ["2018-07-01", "2019-01-01", "2019-07-01", "2020-03-01"]
DEFAULT_KNOT2_GRID = ["2021-07-01", "2022-01-01", "2022-07-01"]
DIRECT_HORIZON_BUCKETS = [
    ("h001_030", 1, 30),
    ("h031_180", 31, 180),
    ("h181_365", 181, 365),
    ("h366_548", 366, 548),
]
MODEL_METRIC_COLS = [
    "MAE",
    "RMSE",
    "R2",
    "bias_pred_minus_true",
    "MAE_1_180",
    "MAE_181_365",
    "MAE_366_548",
]
BENCHMARK_MODELS = [
    "direct_ridge_seasonal_delta",
    "direct_elasticnet_seasonal_delta",
    "seasonal_naive_365",
    "seasonal_growth_anchor",
    "pass_1_trend_hinge",
    "pass_2_hybrid_regime_lgbm",
    "blend_pass2_seasonal",
    "blend_pass2_growth",
    "median_anchor_ensemble",
]
PRIMARY_SELECTION_MODELS = [
    "direct_ridge_seasonal_delta",
    "direct_elasticnet_seasonal_delta",
    "pass_1_trend_hinge",
    "pass_2_hybrid_regime_lgbm",
]


def ensure_report_subdirs(report_dir: Path) -> dict[str, Path]:
    paths = {
        "selection": report_dir / "forecasting" / "selection",
        "validation": report_dir / "forecasting" / "validation",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def parse_date_grid(raw: str | None, defaults: Sequence[str]) -> list[pd.Timestamp]:
    if raw is None or raw.strip() == "":
        values = list(defaults)
    else:
        values = [p.strip() for p in raw.split(",") if p.strip()]

    unique_ordered = list(dict.fromkeys(values))
    return sorted(pd.Timestamp(v) for v in unique_ordered)


def ensure_datetime_index(series: pd.Series) -> pd.Series:
    out = series.copy()
    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    return out


def bucket_name_for_horizon(horizon_days: int) -> str:
    for bucket_name, start_day, end_day in DIRECT_HORIZON_BUCKETS:
        if start_day <= horizon_days <= end_day:
            return bucket_name
    raise ValueError(f"Horizon {horizon_days} is outside the supported 1-{DEFAULT_HORIZON_DAYS} range.")


def bucket_bounds(bucket_name: str) -> tuple[int, int]:
    for name, start_day, end_day in DIRECT_HORIZON_BUCKETS:
        if name == bucket_name:
            return start_day, end_day
    raise ValueError(f"Unknown bucket name: {bucket_name}")


@dataclass(frozen=True)
class RegimeConfig:
    knot1: pd.Timestamp
    knot2: pd.Timestamp

    def validate(self) -> None:
        if self.knot2 <= self.knot1:
            raise ValueError(
                f"Invalid regime knots: knot2 ({self.knot2.date()}) must be later than knot1 ({self.knot1.date()})."
            )


def build_regime_feature_frame(ds: pd.Series, regime: RegimeConfig) -> pd.DataFrame:
    hinge_1 = np.maximum(0.0, (ds - regime.knot1).dt.days.astype(float))
    hinge_2 = np.maximum(0.0, (ds - regime.knot2).dt.days.astype(float))

    is_pre = (ds < regime.knot1).astype(int)
    is_mid = ((ds >= regime.knot1) & (ds < regime.knot2)).astype(int)
    is_post = (ds >= regime.knot2).astype(int)

    return pd.DataFrame(
        {
            "hinge_1": hinge_1,
            "hinge_2": hinge_2,
            "is_pre_covid": is_pre,
            "is_covid_period": is_mid,
            "is_post_rebound": is_post,
        }
    )


def build_trend_design_matrix(
    dates: Iterable[pd.Timestamp],
    start_date: pd.Timestamp,
    regime: RegimeConfig,
) -> pd.DataFrame:
    ds = pd.to_datetime(pd.Series(dates))
    t_days = (ds - pd.Timestamp(start_date)).dt.days.astype(float)
    t_years = t_days / 365.25

    X = pd.DataFrame(
        {
            "t_days": t_days,
            "t_years": t_years,
        }
    )
    X = pd.concat([X, build_regime_feature_frame(ds, regime)], axis=1)

    day_of_year = ds.dt.dayofyear.astype(float)
    for k in range(1, 6):
        angle = 2 * np.pi * k * day_of_year / 365.25
        X[f"sin_year_{k}"] = np.sin(angle)
        X[f"cos_year_{k}"] = np.cos(angle)

    dow_dummies = pd.get_dummies(ds.dt.dayofweek, prefix="dow", dtype=float)
    month_dummies = pd.get_dummies(ds.dt.month, prefix="month", dtype=float)
    X = pd.concat([X, dow_dummies, month_dummies], axis=1)
    return X


def validate_regime_features(regime: RegimeConfig) -> None:
    ds = pd.Series(pd.date_range("2012-01-01", "2025-12-31", freq="D"))
    X = build_trend_design_matrix(ds, pd.Timestamp(ds.min()), regime)

    if "t_years_2" in X.columns or "t_years_3" in X.columns:
        raise AssertionError("Global polynomial terms should not exist.")

    if (X["hinge_1"] < 0).any() or (X["hinge_2"] < 0).any():
        raise AssertionError("Hinge features must be non-negative.")

    after_k1 = ds >= regime.knot1
    after_k2 = ds >= regime.knot2
    if (X.loc[after_k1, "hinge_1"].diff().dropna() < 0).any():
        raise AssertionError("hinge_1 must be monotonic after knot1.")
    if (X.loc[after_k2, "hinge_2"].diff().dropna() < 0).any():
        raise AssertionError("hinge_2 must be monotonic after knot2.")

    regime_sum = X[["is_pre_covid", "is_covid_period", "is_post_rebound"]].sum(axis=1)
    if not regime_sum.eq(1).all():
        raise AssertionError("Regime flags must be mutually exclusive and exhaustive.")


@dataclass
class TrendSeasonalForecaster:
    alpha: float = 2.0
    regime: RegimeConfig | None = None

    def __post_init__(self) -> None:
        self.model = Ridge(alpha=self.alpha)
        self.start_date: pd.Timestamp | None = None
        self.columns: list[str] = []

    def fit(
        self,
        dates: Iterable[pd.Timestamp],
        y: pd.Series,
        sample_weight: pd.Series | np.ndarray | None = None,
    ) -> "TrendSeasonalForecaster":
        if self.regime is None:
            raise ValueError("TrendSeasonalForecaster requires a regime configuration.")
        self.regime.validate()

        ds = pd.to_datetime(pd.Series(dates))
        self.start_date = pd.Timestamp(ds.min())
        X = build_trend_design_matrix(ds, self.start_date, self.regime)
        self.columns = X.columns.tolist()
        y_log = np.log1p(pd.Series(y).astype(float).values)
        self.model.fit(X.values, y_log, sample_weight=sample_weight)
        return self

    def predict(self, dates: Iterable[pd.Timestamp]) -> np.ndarray:
        if self.start_date is None or self.regime is None:
            raise RuntimeError("Model must be fitted before prediction.")
        ds = pd.to_datetime(pd.Series(dates))
        X = build_trend_design_matrix(ds, self.start_date, self.regime)
        X = X.reindex(columns=self.columns, fill_value=0.0)
        pred_log = self.model.predict(X.values)
        return np.clip(np.expm1(pred_log), a_min=0.0, a_max=None)


def build_known_future_feature_frame(
    dates: Iterable[pd.Timestamp],
    start_date: pd.Timestamp,
    regime: RegimeConfig,
) -> pd.DataFrame:
    ds = pd.to_datetime(pd.Series(dates))
    X = build_trend_design_matrix(ds, start_date, regime)
    X["is_month_start"] = ds.dt.is_month_start.astype(float)
    X["is_month_end"] = ds.dt.is_month_end.astype(float)
    X["sin_dow"] = np.sin(2 * np.pi * ds.dt.dayofweek.astype(float) / 7.0)
    X["cos_dow"] = np.cos(2 * np.pi * ds.dt.dayofweek.astype(float) / 7.0)
    X = X.add_prefix("target_")
    X.index = pd.Index(ds.values, name="Date")
    return X


def build_origin_context_frame(y_series: pd.Series) -> pd.DataFrame:
    y = ensure_datetime_index(y_series.astype(float))
    y_log = np.log1p(y)
    X = pd.DataFrame(index=y.index)
    X["origin_log_level"] = y_log

    direct_lags = [1, 7, 14, 28, 56, 90, 182, 365]
    for lag in direct_lags:
        X[f"origin_log_lag_{lag}"] = y_log.shift(lag)

    for window in ROLL_WINDOWS:
        X[f"origin_log_roll_mean_{window}"] = y_log.rolling(window).mean()
        X[f"origin_log_roll_std_{window}"] = y_log.rolling(window).std(ddof=0)

    X["origin_log_momentum_7"] = X["origin_log_level"] - X["origin_log_lag_7"]
    X["origin_log_momentum_28"] = X["origin_log_level"] - X["origin_log_lag_28"]
    X["origin_log_momentum_365"] = X["origin_log_level"] - X["origin_log_lag_365"]
    return X


def build_direct_training_frame(
    y_series: pd.Series,
    regime: RegimeConfig,
    bucket_name: str,
) -> tuple[pd.DataFrame, pd.Series]:
    start_day, end_day = bucket_bounds(bucket_name)
    y = ensure_datetime_index(y_series.astype(float))
    log_y = np.log1p(y)
    start_date = pd.Timestamp(y.index.min())
    origin_features = build_origin_context_frame(y)
    target_features = build_known_future_feature_frame(y.index, start_date, regime)
    target_index_series = pd.Series(y.index, index=y.index)

    bucket_frames: list[pd.DataFrame] = []
    for horizon_days in range(start_day, end_day + 1):
        target_log = log_y.shift(-horizon_days)
        anchor_log = log_y.shift(365 - horizon_days)
        X_h = pd.concat([origin_features, target_features.shift(-horizon_days)], axis=1)
        X_h["horizon_days"] = float(horizon_days)
        X_h["horizon_scaled"] = float(horizon_days) / DEFAULT_HORIZON_DAYS
        X_h["target_date"] = target_index_series.shift(-horizon_days)
        X_h["seasonal_delta_log"] = target_log - anchor_log
        X_h = X_h.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
        bucket_frames.append(X_h)

    if not bucket_frames:
        raise ValueError(f"No training rows available for direct bucket {bucket_name}.")

    frame = pd.concat(bucket_frames, ignore_index=True)
    y_target = frame["seasonal_delta_log"].copy()
    X = frame.drop(columns=["seasonal_delta_log", "target_date"])
    return X, y_target


def make_direct_linear_estimator(model_kind: str) -> Pipeline:
    if model_kind == "ridge":
        estimator = Ridge(alpha=4.0)
    elif model_kind == "elasticnet":
        estimator = ElasticNet(alpha=0.001, l1_ratio=0.1, max_iter=20000, random_state=SEED)
    else:
        raise ValueError(f"Unsupported direct model kind: {model_kind}")

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("regressor", estimator),
        ]
    )


def reconstruct_from_seasonal_delta(
    seasonal_delta_log: pd.Series,
    future_dates: pd.Series,
    anchor_history: pd.Series,
    lag_days: int = 365,
) -> pd.Series:
    hist = ensure_datetime_index(anchor_history.astype(float)).copy()
    future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()
    z_hat = pd.Series(seasonal_delta_log.values, index=pd.to_datetime(seasonal_delta_log.index)).sort_index()

    preds: dict[pd.Timestamp, float] = {}
    for d in future_ds:
        anchor_date = d - pd.Timedelta(days=lag_days)
        anchor_value = hist.get(anchor_date, np.nan)
        if np.isnan(anchor_value):
            anchor_value = preds.get(anchor_date, np.nan)
        if np.isnan(anchor_value):
            anchor_value = float(hist.iloc[-1])

        pred_level = float(np.expm1(float(z_hat.loc[d]) + np.log1p(anchor_value)))
        preds[d] = max(0.0, pred_level)
        hist.loc[d] = preds[d]

    return pd.Series(preds).sort_index()


@dataclass
class DirectSeasonalDeltaForecaster:
    model_kind: str
    regime: RegimeConfig

    def __post_init__(self) -> None:
        self.start_date: pd.Timestamp | None = None
        self.bucket_models: dict[str, Pipeline] = {}
        self.bucket_feature_columns: dict[str, list[str]] = {}

    def fit(self, y_series: pd.Series) -> "DirectSeasonalDeltaForecaster":
        y = ensure_datetime_index(y_series.astype(float))
        self.start_date = pd.Timestamp(y.index.min())
        self.regime.validate()

        for bucket_name, _, _ in DIRECT_HORIZON_BUCKETS:
            X_bucket, y_bucket = build_direct_training_frame(y, self.regime, bucket_name)
            model = make_direct_linear_estimator(self.model_kind)
            model.fit(X_bucket, y_bucket)
            self.bucket_models[bucket_name] = model
            self.bucket_feature_columns[bucket_name] = X_bucket.columns.tolist()
        return self

    def predict(self, history: pd.Series, future_dates: pd.Series) -> pd.Series:
        if self.start_date is None:
            raise RuntimeError("DirectSeasonalDeltaForecaster must be fitted before prediction.")

        hist = ensure_datetime_index(history.astype(float))
        future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()
        origin_date = pd.Timestamp(hist.index.max())

        origin_context = build_origin_context_frame(hist).loc[[origin_date]].copy()
        target_features = build_known_future_feature_frame(future_ds, self.start_date, self.regime)

        z_preds: dict[pd.Timestamp, float] = {}
        for horizon_days, d in enumerate(future_ds, start=1):
            bucket_name = bucket_name_for_horizon(horizon_days)
            X_row = pd.concat([origin_context.reset_index(drop=True), target_features.loc[[d]].reset_index(drop=True)], axis=1)
            X_row["horizon_days"] = float(horizon_days)
            X_row["horizon_scaled"] = float(horizon_days) / DEFAULT_HORIZON_DAYS
            if X_row.isna().any().any():
                X_row = X_row.fillna({"origin_log_level": float(origin_context["origin_log_level"].iloc[0])}).fillna(0.0)
            X_row = X_row.reindex(columns=self.bucket_feature_columns[bucket_name], fill_value=0.0)
            z_preds[d] = float(self.bucket_models[bucket_name].predict(X_row)[0])

        z_series = pd.Series(z_preds).sort_index()
        return reconstruct_from_seasonal_delta(
            seasonal_delta_log=z_series,
            future_dates=future_ds,
            anchor_history=hist,
            lag_days=365,
        )


def single_feature_row(
    history: pd.Series,
    current_date: pd.Timestamp,
    baseline_value: float,
    start_date: pd.Timestamp,
    regime: RegimeConfig,
) -> dict[str, float]:
    d = pd.Timestamp(current_date)
    hist = ensure_datetime_index(history)
    row: dict[str, float] = {}

    for lag in LAGS:
        row[f"lag_{lag}"] = float(hist.get(d - pd.Timedelta(days=lag), np.nan))

    for w in ROLL_WINDOWS:
        vals = [hist.get(d - pd.Timedelta(days=i), np.nan) for i in range(1, w + 1)]
        vals_np = np.array(vals, dtype=float)
        if np.isnan(vals_np).any():
            row[f"roll_mean_{w}"] = np.nan
            row[f"roll_std_{w}"] = np.nan
        else:
            row[f"roll_mean_{w}"] = float(vals_np.mean())
            row[f"roll_std_{w}"] = float(vals_np.std(ddof=0))

    lag_1 = row.get("lag_1", np.nan)
    lag_7 = row.get("lag_7", np.nan)
    row["lag_diff_1_7"] = lag_1 - lag_7 if not np.isnan(lag_1) and not np.isnan(lag_7) else np.nan
    row["lag_ratio_1_7"] = (
        lag_1 / max(abs(lag_7), 1e-6) if not np.isnan(lag_1) and not np.isnan(lag_7) else np.nan
    )

    row["dow"] = d.dayofweek
    row["dom"] = d.day
    row["month"] = d.month
    row["doy"] = d.dayofyear
    row["woy"] = int(d.isocalendar().week)
    row["is_month_start"] = int(d.is_month_start)
    row["is_month_end"] = int(d.is_month_end)
    row["sin_dow"] = np.sin(2 * np.pi * row["dow"] / 7.0)
    row["cos_dow"] = np.cos(2 * np.pi * row["dow"] / 7.0)
    row["sin_doy"] = np.sin(2 * np.pi * row["doy"] / 365.25)
    row["cos_doy"] = np.cos(2 * np.pi * row["doy"] / 365.25)

    row["t_days"] = float((d - pd.Timestamp(start_date)).days)
    row["t_years"] = row["t_days"] / 365.25

    regime_row = build_regime_feature_frame(pd.Series([d]), regime).iloc[0].to_dict()
    for k, v in regime_row.items():
        row[k] = float(v)

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
    dates = pd.to_datetime(y.index)
    baseline_pred = baseline_model.predict(dates)
    baseline_map = dict(zip(dates, baseline_pred))

    rows: list[dict[str, float]] = []
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


def build_sample_weights(dates: pd.Series) -> np.ndarray:
    return np.ones(len(dates), dtype=float)


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


def seasonal_naive_forecast(history: pd.Series, future_dates: pd.Series, lag_days: int = 365) -> pd.Series:
    hist = ensure_datetime_index(history.astype(float))
    future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()
    preds: dict[pd.Timestamp, float] = {}
    for d in future_ds:
        lag_val = hist.get(d - pd.Timedelta(days=lag_days), np.nan)
        if np.isnan(lag_val):
            lag_val = float(hist.iloc[-1])
        preds[d] = float(lag_val)
    return pd.Series(preds).sort_index()


def estimate_recent_growth_multiplier(history: pd.Series, lag_days: int = 365, lookback_days: int = 180) -> float:
    hist = ensure_datetime_index(history.astype(float))
    ratios: list[float] = []
    for d in hist.index[-lookback_days:]:
        lag_val = hist.get(d - pd.Timedelta(days=lag_days), np.nan)
        cur_val = float(hist.loc[d])
        if np.isnan(lag_val) or abs(lag_val) < 1e-6:
            continue
        ratios.append(cur_val / float(lag_val))

    if not ratios:
        return 1.0

    ratio = float(np.median(ratios))
    return float(np.clip(ratio, 0.85, 1.20))


def growth_adjusted_anchor_forecast(
    history: pd.Series,
    future_dates: pd.Series,
    lag_days: int = 365,
    lookback_days: int = 180,
) -> pd.Series:
    seasonal = seasonal_naive_forecast(history, future_dates, lag_days=lag_days)
    growth = estimate_recent_growth_multiplier(history, lag_days=lag_days, lookback_days=lookback_days)
    horizon = len(seasonal)
    if horizon == 0:
        return seasonal

    damp = np.linspace(1.0, 0.45, horizon)
    growth_factor = 1.0 + damp * (growth - 1.0)
    pred = seasonal.values * growth_factor
    return pd.Series(np.clip(pred, 0.0, None), index=seasonal.index)


def make_seasonal_blend_weights(horizon_days: int) -> np.ndarray:
    if horizon_days <= 0:
        return np.array([], dtype=float)
    if horizon_days == 1:
        return np.array([0.2], dtype=float)

    x = np.arange(horizon_days, dtype=float)
    anchors_x = np.array([0.0, min(179.0, horizon_days - 1), min(364.0, horizon_days - 1), horizon_days - 1], dtype=float)
    anchors_y = np.array([0.10, 0.25, 0.55, 0.80], dtype=float)
    weights = np.interp(x, anchors_x, anchors_y)
    return np.clip(weights, 0.0, 1.0)


def blend_with_seasonal_anchor(model_pred: pd.Series, anchor_pred: pd.Series, seasonal_weights: np.ndarray) -> pd.Series:
    model_aligned, anchor_aligned = model_pred.align(anchor_pred, join="inner")
    if len(model_aligned) != len(seasonal_weights):
        raise ValueError("Blend weights length must match forecast horizon.")
    blended = (1.0 - seasonal_weights) * model_aligned.values + seasonal_weights * anchor_aligned.values
    return pd.Series(blended, index=model_aligned.index)


def median_ensemble(predictions: Sequence[pd.Series]) -> pd.Series:
    if not predictions:
        raise ValueError("Median ensemble requires at least one prediction series.")
    aligned = pd.concat(predictions, axis=1)
    return aligned.median(axis=1)


def metrics_frame(
    y_true: pd.Series,
    y_pred: pd.Series,
    model_name: str,
    fold_name: str,
    stage: str,
    target_col: str,
) -> dict[str, float | str]:
    errors = y_pred.values - y_true.values
    abs_errors = np.abs(errors)

    def slice_mae(start: int, end: int | None) -> float:
        segment = abs_errors[start:end]
        return float(segment.mean()) if len(segment) else np.nan

    return {
        "stage": stage,
        "target": target_col,
        "fold": fold_name,
        "model": model_name,
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "R2": float(r2_score(y_true, y_pred)),
        "bias_pred_minus_true": float(errors.mean()),
        "MAE_1_180": slice_mae(0, 180),
        "MAE_181_365": slice_mae(180, 365),
        "MAE_366_548": slice_mae(365, None),
    }


def seasonal_anchor_candidates(
    train_series: pd.Series,
    horizon_days: int,
    pass1_pred: pd.Series,
    pass2_pred: pd.Series,
    growth_anchor: pd.Series,
    seasonal_anchor: pd.Series,
) -> dict[str, pd.Series]:
    weights = make_seasonal_blend_weights(horizon_days)
    blend_pass2_seasonal = blend_with_seasonal_anchor(pass2_pred, seasonal_anchor, weights)
    blend_pass2_growth = blend_with_seasonal_anchor(pass2_pred, growth_anchor, weights)
    median_anchor = median_ensemble([seasonal_anchor, growth_anchor, blend_pass2_growth])

    return {
        "seasonal_naive_365": seasonal_anchor,
        "seasonal_growth_anchor": growth_anchor,
        "pass_1_trend_hinge": pass1_pred,
        "pass_2_hybrid_regime_lgbm": pass2_pred,
        "blend_pass2_seasonal": blend_pass2_seasonal,
        "blend_pass2_growth": blend_pass2_growth,
        "median_anchor_ensemble": median_anchor,
    }


def fit_core_models(
    sales: pd.DataFrame,
    target_col: str,
    regime: RegimeConfig,
    residual_val_days: int,
) -> tuple[pd.Series, TrendSeasonalForecaster, LGBMRegressor, list[str]]:
    train_df = sales[["Date", target_col]].copy().sort_values("Date")
    train_series = pd.Series(train_df[target_col].values, index=train_df["Date"])
    pass1 = TrendSeasonalForecaster(alpha=2.0, regime=regime).fit(train_df["Date"], train_df[target_col])
    X_res, y_res, d_res = build_residual_training_frame(train_series, pass1, return_dates=True)
    residual_model = fit_lightgbm_residual_model(
        X=X_res,
        y=y_res,
        dates=d_res,
        residual_val_days=residual_val_days,
        use_sample_weight=False,
    )
    return train_series, pass1, residual_model, X_res.columns.tolist()


def fit_direct_models(
    train_series: pd.Series,
    regime: RegimeConfig,
) -> dict[str, DirectSeasonalDeltaForecaster]:
    return {
        "direct_ridge_seasonal_delta": DirectSeasonalDeltaForecaster(model_kind="ridge", regime=regime).fit(train_series),
        "direct_elasticnet_seasonal_delta": DirectSeasonalDeltaForecaster(model_kind="elasticnet", regime=regime).fit(train_series),
    }


def generate_candidate_forecasts(
    train_series: pd.Series,
    future_dates: pd.Series,
    baseline_model: TrendSeasonalForecaster,
    residual_model: LGBMRegressor,
    feature_columns: list[str],
    direct_models: dict[str, DirectSeasonalDeltaForecaster] | None = None,
) -> dict[str, pd.Series]:
    future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()
    horizon_days = len(future_ds)

    pass1_pred = pd.Series(baseline_model.predict(future_ds), index=future_ds)
    pass2_pred = predict_hybrid_recursive(train_series, future_ds, baseline_model, residual_model, feature_columns)
    seasonal_anchor = seasonal_naive_forecast(train_series, future_ds, lag_days=365)
    growth_anchor = growth_adjusted_anchor_forecast(train_series, future_ds, lag_days=365, lookback_days=180)

    candidates = seasonal_anchor_candidates(
        train_series=train_series,
        horizon_days=horizon_days,
        pass1_pred=pass1_pred,
        pass2_pred=pass2_pred,
        growth_anchor=growth_anchor,
        seasonal_anchor=seasonal_anchor,
    )
    if direct_models is not None:
        for model_name, model in direct_models.items():
            candidates[model_name] = model.predict(train_series, future_ds)
    return candidates


def evaluate_models_for_cutoffs(
    sales: pd.DataFrame,
    target_col: str,
    cutoffs: list[str],
    horizon_days: int,
    regime: RegimeConfig,
    residual_val_days: int,
    stage: str,
) -> pd.DataFrame:
    df = sales[["Date", target_col]].copy().sort_values("Date")
    rows: list[dict[str, float | str]] = []

    for cutoff_str in cutoffs:
        cutoff = pd.Timestamp(cutoff_str)
        train_df = df[df["Date"] <= cutoff].copy()
        valid_df = df[(df["Date"] > cutoff) & (df["Date"] <= cutoff + pd.Timedelta(days=horizon_days))].copy()
        if len(train_df) < 730 or len(valid_df) < min(365, horizon_days):
            continue

        train_series, pass1, residual_model, feature_columns = fit_core_models(
            sales=train_df,
            target_col=target_col,
            regime=regime,
            residual_val_days=residual_val_days,
        )
        direct_models = fit_direct_models(train_series, regime)
        preds = generate_candidate_forecasts(
            train_series=train_series,
            future_dates=valid_df["Date"],
            baseline_model=pass1,
            residual_model=residual_model,
            feature_columns=feature_columns,
            direct_models=direct_models,
        )
        y_valid = pd.Series(valid_df[target_col].values, index=valid_df["Date"])
        for model_name, pred in preds.items():
            rows.append(metrics_frame(y_valid, pred, model_name, cutoff_str, stage, target_col))

    return pd.DataFrame(rows)


def summarize_metrics(metrics_df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        metrics_df.groupby(["stage", "target", "model"])[MODEL_METRIC_COLS]
        .mean()
        .reset_index()
        .sort_values(["stage", "target", "MAE", "RMSE"])
    )
    return summary


def evaluate_pass1_mae_for_regime(
    sales: pd.DataFrame,
    target_col: str,
    cutoffs: list[str],
    horizon_days: int,
    regime: RegimeConfig,
) -> float:
    df = sales[["Date", target_col]].copy().sort_values("Date")
    maes: list[float] = []
    for cutoff_str in cutoffs:
        cutoff = pd.Timestamp(cutoff_str)
        train_df = df[df["Date"] <= cutoff].copy()
        valid_df = df[(df["Date"] > cutoff) & (df["Date"] <= cutoff + pd.Timedelta(days=horizon_days))].copy()
        if len(train_df) < 730 or len(valid_df) < min(365, horizon_days):
            continue
        pass1 = TrendSeasonalForecaster(alpha=2.0, regime=regime).fit(train_df["Date"], train_df[target_col])
        pred = pd.Series(pass1.predict(valid_df["Date"]), index=valid_df["Date"])
        y_valid = pd.Series(valid_df[target_col].values, index=valid_df["Date"])
        maes.append(float(mean_absolute_error(y_valid, pred)))
    return float(np.mean(maes)) if maes else float("inf")


def evaluate_pass2_mae_for_regime(
    sales: pd.DataFrame,
    target_col: str,
    cutoffs: list[str],
    horizon_days: int,
    regime: RegimeConfig,
    residual_val_days: int,
) -> float:
    df = sales[["Date", target_col]].copy().sort_values("Date")
    maes: list[float] = []
    for cutoff_str in cutoffs:
        cutoff = pd.Timestamp(cutoff_str)
        train_df = df[df["Date"] <= cutoff].copy()
        valid_df = df[(df["Date"] > cutoff) & (df["Date"] <= cutoff + pd.Timedelta(days=horizon_days))].copy()
        if len(train_df) < 730 or len(valid_df) < min(365, horizon_days):
            continue

        train_series, pass1, residual_model, feature_columns = fit_core_models(
            sales=train_df,
            target_col=target_col,
            regime=regime,
            residual_val_days=residual_val_days,
        )
        pred = predict_hybrid_recursive(
            history=train_series,
            future_dates=valid_df["Date"],
            baseline_model=pass1,
            residual_model=residual_model,
            feature_columns=feature_columns,
        )
        y_valid = pd.Series(valid_df[target_col].values, index=valid_df["Date"])
        maes.append(float(mean_absolute_error(y_valid, pred)))
    return float(np.mean(maes)) if maes else float("inf")


def select_best_regime(
    sales: pd.DataFrame,
    target_col: str,
    tune_cutoffs: list[str],
    horizon_days: int,
    knot1_grid: list[pd.Timestamp],
    knot2_grid: list[pd.Timestamp],
    residual_val_days: int,
) -> tuple[RegimeConfig, pd.DataFrame, pd.DataFrame]:
    pairs: list[RegimeConfig] = []
    for k1, k2 in product(knot1_grid, knot2_grid):
        cfg = RegimeConfig(knot1=pd.Timestamp(k1), knot2=pd.Timestamp(k2))
        if cfg.knot2 > cfg.knot1:
            pairs.append(cfg)

    if not pairs:
        raise ValueError("No valid knot pairs found. Check knot grids.")

    pass1_rows = []
    for cfg in pairs:
        pass1_mae = evaluate_pass1_mae_for_regime(
            sales=sales,
            target_col=target_col,
            cutoffs=tune_cutoffs,
            horizon_days=horizon_days,
            regime=cfg,
        )
        pass1_rows.append(
            {
                "knot1": cfg.knot1.strftime("%Y-%m-%d"),
                "knot2": cfg.knot2.strftime("%Y-%m-%d"),
                "pass1_mae": pass1_mae,
            }
        )
    pass1_df = pd.DataFrame(pass1_rows).sort_values("pass1_mae").reset_index(drop=True)

    top_k = min(3, len(pass1_df))
    pass2_rows = []
    for _, row in pass1_df.head(top_k).iterrows():
        cfg = RegimeConfig(knot1=pd.Timestamp(row["knot1"]), knot2=pd.Timestamp(row["knot2"]))
        pass2_mae = evaluate_pass2_mae_for_regime(
            sales=sales,
            target_col=target_col,
            cutoffs=tune_cutoffs,
            horizon_days=horizon_days,
            regime=cfg,
            residual_val_days=residual_val_days,
        )
        pass2_rows.append(
            {
                "knot1": cfg.knot1.strftime("%Y-%m-%d"),
                "knot2": cfg.knot2.strftime("%Y-%m-%d"),
                "pass1_mae": float(row["pass1_mae"]),
                "pass2_mae": pass2_mae,
            }
        )
    pass2_df = pd.DataFrame(pass2_rows).sort_values("pass2_mae").reset_index(drop=True)
    best = pass2_df.iloc[0]
    return RegimeConfig(pd.Timestamp(best["knot1"]), pd.Timestamp(best["knot2"])), pass1_df, pass2_df


def select_submission_models(
    tune_summary: pd.DataFrame,
    holdout_summary: pd.DataFrame,
) -> pd.DataFrame:
    tune_revenue = tune_summary[
        (tune_summary["stage"] == "tune")
        & (tune_summary["target"] == "Revenue")
        & (tune_summary["model"].isin(PRIMARY_SELECTION_MODELS))
    ].copy()
    holdout_revenue = holdout_summary[
        (holdout_summary["stage"] == "holdout")
        & (holdout_summary["target"] == "Revenue")
        & (holdout_summary["model"].isin(PRIMARY_SELECTION_MODELS))
    ][["model", "MAE", "RMSE", "bias_pred_minus_true"]].rename(
        columns={
            "MAE": "holdout_MAE",
            "RMSE": "holdout_RMSE",
            "bias_pred_minus_true": "holdout_bias",
        }
    )
    ranked = tune_revenue.merge(holdout_revenue, on="model", how="left")
    ranked = ranked.sort_values(["MAE", "RMSE"]).reset_index(drop=True)
    ranked["submission_rank"] = np.arange(1, len(ranked) + 1)
    return ranked


def create_submission_for_model(
    sales: pd.DataFrame,
    test_dates: pd.Series,
    target_col: str,
    regime: RegimeConfig,
    residual_val_days: int,
) -> dict[str, pd.Series]:
    train_series, pass1, residual_model, feature_columns = fit_core_models(
        sales=sales,
        target_col=target_col,
        regime=regime,
        residual_val_days=residual_val_days,
    )
    direct_models = fit_direct_models(train_series, regime)
    return generate_candidate_forecasts(
        train_series=train_series,
        future_dates=test_dates,
        baseline_model=pass1,
        residual_model=residual_model,
        feature_columns=feature_columns,
        direct_models=direct_models,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train forecast models, evaluate on 548-day pseudo-private folds, and export submissions.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"), help="Directory containing Kaggle CSV files.")
    parser.add_argument("--out-dir", type=Path, default=Path("submissions"), help="Directory to write submission files.")
    parser.add_argument("--report-dir", type=Path, default=Path("reports"), help="Directory to write report artifacts.")
    parser.add_argument(
        "--knot1-grid",
        type=str,
        default=",".join(DEFAULT_KNOT1_GRID),
        help="Comma-separated knot1 candidate dates.",
    )
    parser.add_argument(
        "--knot2-grid",
        type=str,
        default=",".join(DEFAULT_KNOT2_GRID),
        help="Comma-separated knot2 candidate dates.",
    )
    parser.add_argument(
        "--disable-knot-search",
        action="store_true",
        help="Disable knot search and use the first knot from each grid as fixed knots.",
    )
    parser.add_argument(
        "--residual-val-days",
        type=int,
        default=180,
        help="Validation window length (days) for LightGBM residual early stopping.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    out_dir = args.out_dir
    report_dir = args.report_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_paths = ensure_report_subdirs(report_dir)

    sales = pd.read_csv(data_dir / "sales.csv", parse_dates=["Date"]).sort_values("Date")
    sample_sub = pd.read_csv(data_dir / "sample_submission.csv", parse_dates=["Date"])
    test_dates = sample_sub["Date"]

    knot1_grid = parse_date_grid(args.knot1_grid, DEFAULT_KNOT1_GRID)
    knot2_grid = parse_date_grid(args.knot2_grid, DEFAULT_KNOT2_GRID)

    if args.disable_knot_search:
        best_regime = RegimeConfig(knot1=knot1_grid[0], knot2=knot2_grid[0])
        best_regime.validate()
        pass1_search_df = pd.DataFrame(
            [{"knot1": best_regime.knot1.strftime("%Y-%m-%d"), "knot2": best_regime.knot2.strftime("%Y-%m-%d"), "pass1_mae": np.nan}]
        )
        pass2_search_df = pd.DataFrame(
            [{"knot1": best_regime.knot1.strftime("%Y-%m-%d"), "knot2": best_regime.knot2.strftime("%Y-%m-%d"), "pass1_mae": np.nan, "pass2_mae": np.nan}]
        )
    else:
        best_regime, pass1_search_df, pass2_search_df = select_best_regime(
            sales=sales,
            target_col="Revenue",
            tune_cutoffs=DEFAULT_TUNE_CUTOFFS,
            horizon_days=DEFAULT_HORIZON_DAYS,
            knot1_grid=knot1_grid,
            knot2_grid=knot2_grid,
            residual_val_days=args.residual_val_days,
        )

    best_regime.validate()
    validate_regime_features(best_regime)

    tune_detail = evaluate_models_for_cutoffs(
        sales=sales,
        target_col="Revenue",
        cutoffs=DEFAULT_TUNE_CUTOFFS,
        horizon_days=DEFAULT_HORIZON_DAYS,
        regime=best_regime,
        residual_val_days=args.residual_val_days,
        stage="tune",
    )
    holdout_detail = evaluate_models_for_cutoffs(
        sales=sales,
        target_col="Revenue",
        cutoffs=[DEFAULT_FINAL_HOLDOUT_CUTOFF],
        horizon_days=DEFAULT_HORIZON_DAYS,
        regime=best_regime,
        residual_val_days=args.residual_val_days,
        stage="holdout",
    )
    tune_summary = summarize_metrics(tune_detail)
    holdout_summary = summarize_metrics(holdout_detail)

    selection = select_submission_models(tune_summary, holdout_summary)
    selected_top2 = selection.head(2).copy()

    selected_top2.to_csv(report_paths["selection"] / "selected_models.csv", index=False)
    pass1_search_df.to_csv(report_paths["selection"] / "knot_search_pass1.csv", index=False)
    pass2_search_df.to_csv(report_paths["selection"] / "knot_search_top3_pass2.csv", index=False)
    tune_detail.to_csv(report_paths["validation"] / "model_tuning_detail.csv", index=False)
    tune_summary.to_csv(report_paths["validation"] / "model_tuning_summary.csv", index=False)
    holdout_detail.to_csv(report_paths["validation"] / "model_holdout_detail.csv", index=False)
    holdout_summary.to_csv(report_paths["validation"] / "model_holdout_summary.csv", index=False)

    # Keep combined files for continuity with earlier runs.
    pd.concat([tune_detail, holdout_detail], ignore_index=True).to_csv(
        report_paths["validation"] / "model_comparison.csv", index=False
    )
    pd.concat([tune_summary, holdout_summary], ignore_index=True).to_csv(
        report_paths["validation"] / "model_comparison_summary.csv", index=False
    )

    submission_models = selected_top2["model"].tolist()
    revenue_candidates = create_submission_for_model(
        sales=sales,
        test_dates=test_dates,
        target_col="Revenue",
        regime=best_regime,
        residual_val_days=args.residual_val_days,
    )
    cogs_candidates = create_submission_for_model(
        sales=sales,
        test_dates=test_dates,
        target_col="COGS",
        regime=best_regime,
        residual_val_days=args.residual_val_days,
    )
    submission_frames = []
    for model_name in submission_models:
        revenue_pred = revenue_candidates[model_name]
        cogs_pred = cogs_candidates[model_name]
        submission_frames.append(
            pd.DataFrame(
                {
                    "Date": test_dates.dt.strftime("%Y-%m-%d"),
                    "Revenue": revenue_pred.values,
                    "COGS": cogs_pred.values,
                }
            )
        )

    submission_frames[0].to_csv(out_dir / "submission_pass1.csv", index=False)
    submission_frames[1].to_csv(out_dir / "submission_pass2.csv", index=False)

    print("Selected regime:")
    print(f"  knot1 = {best_regime.knot1.date()}")
    print(f"  knot2 = {best_regime.knot2.date()}")
    print("\nSelected submission models:")
    print(selected_top2[["submission_rank", "model", "MAE", "holdout_MAE"]].to_string(index=False))
    print("\nWrote:")
    print(f"  - {(out_dir / 'submission_pass1.csv').resolve()}")
    print(f"  - {(out_dir / 'submission_pass2.csv').resolve()}")
    print(f"  - {(report_paths['validation'] / 'model_tuning_summary.csv').resolve()}")
    print(f"  - {(report_paths['validation'] / 'model_holdout_summary.csv').resolve()}")
    print(f"  - {(report_paths['selection'] / 'selected_models.csv').resolve()}")


if __name__ == "__main__":
    main()
