from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


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


def build_trend_design_matrix(ds: pd.Series, start_date: pd.Timestamp, regime: RegimeConfig) -> pd.DataFrame:
    ds = pd.to_datetime(pd.Series(ds)).reset_index(drop=True)
    t_days = (ds - pd.Timestamp(start_date)).dt.days.astype(float)
    t_years = t_days / 365.25

    dow = ds.dt.dayofweek
    month = ds.dt.month
    doy = ds.dt.dayofyear.astype(float)

    X = pd.DataFrame(
        {
            "t_days": t_days,
            "t_years": t_years,
            "is_weekend": (dow >= 5).astype(int),
            "is_month_end": ds.dt.is_month_end.astype(int),
            "is_month_start": ds.dt.is_month_start.astype(int),
            "month": month,
            "dow": dow,
        }
    )
    for k in (1, 2, 3):
        X[f"sin_{k}"] = np.sin(2 * np.pi * k * doy / 365.25)
        X[f"cos_{k}"] = np.cos(2 * np.pi * k * doy / 365.25)

    X = pd.concat([X, build_regime_feature_frame(ds, regime)], axis=1)

    month_dummies = pd.get_dummies(month, prefix="m", drop_first=True)
    dow_dummies = pd.get_dummies(dow, prefix="d", drop_first=True)
    X = pd.concat([X, month_dummies, dow_dummies], axis=1)
    return X.fillna(0.0)


def validate_regime_features(regime: RegimeConfig) -> None:
    ds = pd.Series(pd.date_range("2018-01-01", "2024-12-31", freq="D"))
    X = build_trend_design_matrix(ds, pd.Timestamp(ds.min()), regime)

    if "t_years_2" in X.columns or "t_years_3" in X.columns:
        raise AssertionError("Global polynomial trend terms must not be present.")

    if not (X["hinge_1"] >= 0).all() or not (X["hinge_2"] >= 0).all():
        raise AssertionError("Hinge features must be non-negative.")

    after_k1 = ds >= regime.knot1
    after_k2 = ds >= regime.knot2
    if not X.loc[after_k1, "hinge_1"].is_monotonic_increasing:
        raise AssertionError("hinge_1 must be monotonic after knot1.")
    if not X.loc[after_k2, "hinge_2"].is_monotonic_increasing:
        raise AssertionError("hinge_2 must be monotonic after knot2.")

    regime_sum = X[["is_pre_covid", "is_covid_period", "is_post_rebound"]].sum(axis=1)
    if not regime_sum.eq(1).all():
        raise AssertionError("Regime flags must be mutually exclusive and exhaustive.")
