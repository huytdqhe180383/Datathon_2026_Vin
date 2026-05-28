from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd


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


def build_sample_weights(dates: pd.Series, lam: float = 3.0) -> np.ndarray:
    ds = pd.to_datetime(pd.Series(dates))
    if len(ds) == 0:
        return np.array([], dtype=float)
    t = (ds - ds.min()).dt.days.astype(float)
    max_t = float(t.max()) if len(t) else 0.0
    if max_t <= 0.0:
        return np.ones(len(ds), dtype=float)
    w = np.exp(float(lam) * t / max_t)
    w = w / w.mean()
    return w.to_numpy(dtype=float)


def ensure_report_subdirs(report_dir: Path) -> dict[str, Path]:
    paths = {
        "selection": report_dir / "forecasting" / "selection",
        "validation": report_dir / "forecasting" / "validation",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
