from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from forecasting.regime import RegimeConfig, build_trend_design_matrix


@dataclass
class TrendSeasonalForecaster:
    alpha: float = 2.0
    regime: RegimeConfig | None = None

    def __post_init__(self) -> None:
        self.model = Ridge(alpha=self.alpha)
        self.start_date: pd.Timestamp | None = None
        self.feature_columns: list[str] | None = None

    def fit(
        self,
        dates: pd.Series,
        y: pd.Series,
        sample_weight: pd.Series | np.ndarray | None = None,
    ) -> "TrendSeasonalForecaster":
        if self.regime is None:
            raise ValueError("TrendSeasonalForecaster requires a regime configuration.")
        self.regime.validate()
        ds = pd.to_datetime(pd.Series(dates))
        self.start_date = pd.Timestamp(ds.min())
        X = build_trend_design_matrix(ds, self.start_date, self.regime)
        self.feature_columns = X.columns.tolist()
        y_log = np.log1p(pd.Series(y).values.astype(float))
        self.model.fit(X.values, y_log, sample_weight=sample_weight)
        return self

    def predict(self, dates: Iterable[pd.Timestamp]) -> np.ndarray:
        if self.start_date is None or self.regime is None or self.feature_columns is None:
            raise RuntimeError("Model must be fitted before prediction.")
        ds = pd.to_datetime(pd.Series(list(dates)))
        X = build_trend_design_matrix(ds, self.start_date, self.regime)
        X = X.reindex(columns=self.feature_columns, fill_value=0.0)
        pred_log = self.model.predict(X.values)
        pred = np.expm1(pred_log)
        return np.clip(pred, 0.0, None)
