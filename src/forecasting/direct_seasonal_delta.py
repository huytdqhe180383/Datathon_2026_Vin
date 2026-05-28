from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from forecasting.anchors import estimate_recent_growth_multiplier
from forecasting.config import DEFAULT_HORIZON_DAYS, DIRECT_HORIZON_BUCKETS, SEED
from forecasting.regime import RegimeConfig, build_trend_design_matrix
from forecasting.utils import ensure_datetime_index


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


def build_known_future_feature_frame(ds: pd.Series, start_date: pd.Timestamp, regime: RegimeConfig) -> pd.DataFrame:
    ds = pd.to_datetime(pd.Series(ds))
    X = build_trend_design_matrix(ds, start_date, regime)
    X["doy"] = ds.dt.dayofyear.astype(float)
    X["woy"] = ds.dt.isocalendar().week.astype(int)
    X["weekofmonth"] = ((ds.dt.day - 1) // 7 + 1).astype(int)
    X.index = pd.to_datetime(ds.values)
    return X


def build_origin_context_frame(y_series: pd.Series) -> pd.DataFrame:
    y = ensure_datetime_index(y_series.astype(float))
    y_log = np.log1p(y)

    X = pd.DataFrame(index=y.index)
    X["origin_log_level"] = y_log

    direct_lags = [1, 7, 14, 28, 56, 90, 182, 365]
    for lag in direct_lags:
        X[f"origin_log_lag_{lag}"] = y_log.shift(lag)

    for window in [7, 14, 28, 56, 90]:
        X[f"origin_log_roll_mean_{window}"] = y_log.rolling(window, min_periods=max(2, window // 2)).mean()
        X[f"origin_log_roll_std_{window}"] = y_log.rolling(window, min_periods=max(2, window // 2)).std()

    X["origin_log_momentum_7"] = X["origin_log_level"] - X["origin_log_lag_7"]
    X["origin_log_momentum_28"] = X["origin_log_level"] - X["origin_log_lag_28"]
    X["origin_log_momentum_365"] = X["origin_log_level"] - X["origin_log_lag_365"]
    return X


def build_direct_training_frame(
    y_series: pd.Series,
    regime: RegimeConfig,
    bucket_name: str,
) -> tuple[pd.DataFrame, pd.Series]:
    y = ensure_datetime_index(y_series.astype(float))
    start_day, end_day = bucket_bounds(bucket_name)
    start_date = pd.Timestamp(y.index.min())

    origin_context = build_origin_context_frame(y)
    target_features = build_known_future_feature_frame(y.index, start_date, regime)
    target_log = np.log1p(y)

    rows: list[pd.Series] = []
    for origin_date in y.index:
        for horizon_days in range(start_day, end_day + 1):
            target_date = origin_date + pd.Timedelta(days=horizon_days)
            if target_date not in y.index:
                continue
            anchor_date = target_date - pd.Timedelta(days=365)
            anchor_val = y.get(anchor_date, np.nan)
            if np.isnan(anchor_val):
                continue

            anchor_log = np.log1p(float(anchor_val))
            row = pd.concat([origin_context.loc[origin_date], target_features.loc[target_date]])
            row["horizon_days"] = float(horizon_days)
            row["horizon_scaled"] = float(horizon_days) / DEFAULT_HORIZON_DAYS
            row["anchor_log"] = anchor_log
            row["seasonal_delta_log"] = float(target_log.loc[target_date] - anchor_log)
            row["target_date"] = target_date
            rows.append(row)

    if not rows:
        return pd.DataFrame(), pd.Series(dtype=float)

    frame = pd.DataFrame(rows).dropna().reset_index(drop=True)
    y_target = frame["seasonal_delta_log"].copy()
    X = frame.drop(columns=["seasonal_delta_log", "target_date"])
    return X, y_target


def make_direct_linear_estimator(model_kind: str) -> Pipeline:
    if model_kind == "ridge":
        estimator = Ridge(alpha=4.0)
    elif model_kind == "elasticnet":
        estimator = ElasticNet(alpha=0.1, l1_ratio=0.5, max_iter=20000, random_state=SEED)
    else:
        raise ValueError(f"Unknown model kind: {model_kind}")

    return Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            ("model", estimator),
        ]
    )


def reconstruct_from_seasonal_delta(
    seasonal_delta_log: pd.Series,
    future_dates: pd.Series,
    anchor_history: pd.Series,
    lag_days: int = 365,
) -> pd.Series:
    z_hat = pd.Series(seasonal_delta_log.values, index=pd.to_datetime(seasonal_delta_log.index)).sort_index()
    hist = ensure_datetime_index(anchor_history.astype(float)).copy()
    growth = estimate_recent_growth_multiplier(anchor_history, lag_days=lag_days, lookback_days=90)

    preds: dict[pd.Timestamp, float] = {}
    for d in pd.to_datetime(pd.Series(future_dates)).sort_values():
        anchor_date = d - pd.Timedelta(days=lag_days)
        if anchor_date in hist.index:
            anchor_value = float(hist.loc[anchor_date])
        elif anchor_date in preds:
            anchor_value = float(preds[anchor_date])
        else:
            anchor_value = float(hist.iloc[-1]) * growth

        pred = np.expm1(float(z_hat.loc[d]) + np.log1p(anchor_value))
        pred = float(max(0.0, pred))
        preds[d] = pred
        hist.loc[d] = pred

    return pd.Series(preds).sort_index()


@dataclass
class DirectSeasonalDeltaForecaster:
    model_kind: str
    regime: RegimeConfig

    def __post_init__(self) -> None:
        self.bucket_models = {name: make_direct_linear_estimator(self.model_kind) for name, _, _ in DIRECT_HORIZON_BUCKETS}
        self.start_date: pd.Timestamp | None = None
        self.fitted = False

    def fit(self, y_series: pd.Series) -> "DirectSeasonalDeltaForecaster":
        y = ensure_datetime_index(y_series.astype(float))
        self.regime.validate()
        self.start_date = pd.Timestamp(y.index.min())
        for bucket_name, _, _ in DIRECT_HORIZON_BUCKETS:
            X_bucket, y_bucket = build_direct_training_frame(y, self.regime, bucket_name)
            if X_bucket.empty:
                continue
            self.bucket_models[bucket_name].fit(X_bucket, y_bucket)
        self.fitted = True
        return self

    def predict(self, history: pd.Series, future_dates: pd.Series) -> pd.Series:
        if not self.fitted or self.start_date is None:
            raise RuntimeError("DirectSeasonalDeltaForecaster must be fitted before prediction.")

        hist = ensure_datetime_index(history.astype(float))
        origin_date = pd.Timestamp(hist.index.max())

        origin_context = build_origin_context_frame(hist)
        origin_row = origin_context.loc[origin_date].copy()

        future_ds = pd.to_datetime(pd.Series(future_dates)).sort_values()
        target_features = build_known_future_feature_frame(future_ds, self.start_date, self.regime)

        z_preds: dict[pd.Timestamp, float] = {}
        for d in future_ds:
            horizon_days = int((d - origin_date).days)
            bucket_name = bucket_name_for_horizon(horizon_days)

            anchor_date = d - pd.Timedelta(days=365)
            anchor_val = hist.get(anchor_date, np.nan)
            if np.isnan(anchor_val):
                anchor_val = float(hist.iloc[-1])
            anchor_log = np.log1p(anchor_val)

            X_row = pd.concat([origin_row, target_features.loc[d]])
            X_row["horizon_days"] = float(horizon_days)
            X_row["horizon_scaled"] = float(horizon_days) / DEFAULT_HORIZON_DAYS
            X_row["anchor_log"] = anchor_log
            X_row = X_row.to_frame().T.fillna(0.0)

            z_preds[d] = float(self.bucket_models[bucket_name].predict(X_row)[0])

        z_series = pd.Series(z_preds).sort_index()
        return reconstruct_from_seasonal_delta(
            seasonal_delta_log=z_series,
            future_dates=future_ds,
            anchor_history=hist,
            lag_days=365,
        )
