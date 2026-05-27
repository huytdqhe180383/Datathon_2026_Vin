from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "src"))

import two_pass_forecast as tpf


def test_default_validation_protocol_matches_leaderboard_horizon():
    assert tpf.DEFAULT_HORIZON_DAYS == 548
    assert tpf.DEFAULT_TUNE_CUTOFFS == ["2018-06-30", "2019-06-30", "2020-06-30", "2021-06-30"]
    assert tpf.DEFAULT_FINAL_HOLDOUT_CUTOFF == "2021-06-30"
    assert tpf.DEFAULT_KNOT2_GRID == ["2021-07-01", "2022-01-01", "2022-07-01", "2022-10-01", "2023-01-01"]


def test_horizon_blend_schedule_becomes_more_conservative_later():
    weights = tpf.make_seasonal_blend_weights(548)

    assert len(weights) == 548
    assert float(weights[0]) < float(weights[-1])
    assert np.all(np.diff(weights) >= -1e-9)
    assert 0.0 <= float(weights.min()) <= 1.0
    assert 0.0 <= float(weights.max()) <= 1.0


def test_seasonal_anchor_blend_interpolates_between_model_and_anchor():
    model_pred = pd.Series([10.0, 20.0, 30.0])
    anchor_pred = pd.Series([100.0, 200.0, 300.0])
    weights = np.array([0.0, 0.5, 1.0])

    blended = tpf.blend_with_seasonal_anchor(model_pred, anchor_pred, weights)

    assert blended.tolist() == [10.0, 110.0, 300.0]


def test_seasonal_naive_365_falls_back_to_last_value_when_lag_missing():
    history = pd.Series(
        [10.0, 11.0, 12.0],
        index=pd.to_datetime(["2022-01-01", "2022-01-02", "2022-01-03"]),
    )
    future = pd.Series(pd.to_datetime(["2022-01-04", "2023-01-02"]))

    pred = tpf.seasonal_naive_forecast(history, future, lag_days=365)

    assert pred.iloc[0] == 12.0
    assert pred.iloc[1] == 11.0


def test_horizon_bucket_assignment_uses_four_direct_forecast_ranges():
    assert tpf.bucket_name_for_horizon(1) == "h001_030"
    assert tpf.bucket_name_for_horizon(30) == "h001_030"
    assert tpf.bucket_name_for_horizon(31) == "h031_180"
    assert tpf.bucket_name_for_horizon(180) == "h031_180"
    assert tpf.bucket_name_for_horizon(181) == "h181_365"
    assert tpf.bucket_name_for_horizon(365) == "h181_365"
    assert tpf.bucket_name_for_horizon(366) == "h366_548"
    assert tpf.bucket_name_for_horizon(548) == "h366_548"


def test_seasonal_delta_reconstruction_uses_prior_predictions_after_day_365():
    future_dates = pd.Series(pd.to_datetime(["2023-01-01", "2024-01-01"]))
    seasonal_delta_log = pd.Series([0.0, np.log(2.0)], index=future_dates)
    anchor_history = pd.Series([100.0], index=pd.to_datetime(["2022-01-01"]))

    pred = tpf.reconstruct_from_seasonal_delta(
        seasonal_delta_log=seasonal_delta_log,
        future_dates=future_dates,
        anchor_history=anchor_history,
        lag_days=365,
    )

    assert np.isclose(pred.loc[pd.Timestamp("2023-01-01")], 100.0)
    assert np.isclose(pred.loc[pd.Timestamp("2024-01-01")], 201.0)


def test_recency_sample_weights_increase_and_mean_normalize():
    dates = pd.Series(pd.to_datetime(["2022-01-01", "2022-01-10", "2022-01-20"]))
    w = tpf.build_sample_weights(dates, lam=3.0)

    assert len(w) == 3
    assert float(w[0]) < float(w[-1])
    assert np.isclose(float(np.mean(w)), 1.0)
