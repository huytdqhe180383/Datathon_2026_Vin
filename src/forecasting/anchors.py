from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from forecasting.utils import ensure_datetime_index


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
