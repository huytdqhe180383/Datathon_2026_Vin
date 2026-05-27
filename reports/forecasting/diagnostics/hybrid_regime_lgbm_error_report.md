# Hybrid Regime LGBM Error Analysis

## 1) Objective
Analyze error behavior of `pass_2_hybrid_regime_lgbm` and identify where/why the model still misses, despite being the strongest model so far.

## 2) Scope and Inputs
- Model: `pass_2_hybrid_regime_lgbm`
- Target: `Revenue`
- Horizon: 548 days
- Regime used in latest run: `knot1=2020-03-01`, `knot2=2023-01-01`
- Tune folds: `2018-06-30`, `2019-06-30`, `2020-06-30`, `2021-06-30`
- Holdout fold: `2021-06-30`
- Source: `reports/forecasting/diagnostics/hybrid_regime_lgbm_error_by_fold.csv`
- Source: `reports/forecasting/diagnostics/hybrid_regime_lgbm_error_by_month.csv`
- Source: `reports/forecasting/diagnostics/hybrid_regime_lgbm_error_by_actual_quantile.csv`
- Source: `reports/forecasting/diagnostics/hybrid_regime_lgbm_error_stage_summary.csv`
- Source: `reports/forecasting/validation/model_holdout_summary.csv`

## 3) Executive Summary
- This is still the best model on holdout (`MAE=637,478`) and also the best leaderboard-facing submission so far.
- Holdout performance is strong relative to alternatives: `54.6%` better MAE than `seasonal_naive_365` (`1,404,517`).
- Holdout performance is strong relative to alternatives: `23.2%` better MAE than `pass_1_trend_hinge` (`830,257`).
- Core error pattern is amplitude compression: overpredicts low-demand days.
- Core error pattern is amplitude compression: underpredicts high-demand/spike days.
- Fold behavior is not stable: bias flips sign by period (strong overprediction in 2018-2019 fold windows, strong underprediction in 2020 window).

## 4) Error Decomposition

### 4.1 Stage-level summary
| Stage | MAE | RMSE | Bias (pred-true) | Underpredict rate |
|---|---:|---:|---:|---:|
| tune (mean of 4 folds) | 1,073,481 | 1,431,822 | +323,865 | 0.425 |
| holdout (2021-06-30) | 637,478 | 898,048 | -83,592 | 0.535 |

Interpretation:
- Holdout is materially easier than average tune fold.
- Mean tune bias is positive, but holdout bias is mildly negative.
- This confirms regime-sensitive calibration, not one-directional error.

### 4.2 Fold instability
| Fold | MAE | Bias | Underpredict rate |
|---|---:|---:|---:|
| 2018-06-30 | 1,831,578 | +1,558,131 | 0.113 |
| 2019-06-30 | 907,811 | +683,652 | 0.182 |
| 2020-06-30 | 917,056 | -862,731 | 0.870 |
| 2021-06-30 | 637,478 | -83,592 | 0.535 |

Interpretation:
- Large sign flips in bias show that model calibration depends heavily on the train/valid regime pairing.
- Worst fold (`2018-06-30`) is dominated by overprediction; 2020 fold is dominated by underprediction.

### 4.3 Holdout error by horizon segment
| Segment | MAE |
|---|---:|
| days 1-30 | 577,124 |
| days 31-90 | 924,082 |
| days 91-180 | 369,028 |
| days 181-365 | 777,449 |
| days 366-548 | 543,926 |

Interpretation:
- Main weakness on this holdout is the `31-90` window and secondarily `181-365`.
- Long-tail (`366-548`) is better than mid-horizon here, so error is not purely "long horizon drift".

### 4.4 Holdout error by demand level (actual quantiles)
| Actual quantile bin | Mean actual | Mean pred | MAE | Bias |
|---|---:|---:|---:|---:|
| Q1 (lowest demand) | 1,261,699 | 1,533,500 | 400,974 | +271,801 |
| Q2 | 1,877,192 | 2,098,732 | 547,693 | +221,540 |
| Q3 | 2,498,999 | 2,575,328 | 511,755 | +76,329 |
| Q4 | 3,430,055 | 3,223,218 | 711,848 | -206,838 |
| Q5 (highest demand) | 5,327,791 | 4,548,653 | 1,014,978 | -779,138 |

Interpretation:
- The model regresses toward the middle: positive bias for low quantiles.
- The model regresses toward the middle: negative bias for high quantiles.
- This is exactly the compression pattern that limits leaderboard gain.

### 4.5 Holdout monthly stress points
Worst months by MAE (holdout fold `2021-06-30`):
| Month | MAE | Bias |
|---|---:|---:|
| 2021-08 | 1,311,733 | +1,272,868 |
| 2022-05 | 999,092 | +109,676 |
| 2022-08 | 927,427 | -309,846 |
| 2022-03 | 885,739 | -682,919 |
| 2022-06 | 860,289 | -205,641 |

Interpretation:
- Largest errors cluster around abrupt local regime changes.
- Bias direction changes month-to-month, reinforcing that calibration is locally unstable.

## 5) Why Score Is Still Capped
- The model already beats all local comparators on holdout, but it loses score on high-demand tails (underestimation in top quantile).
- The model already beats all local comparators on holdout, but it loses score on a few shock months with large directional miss.
- The model already beats all local comparators on holdout, but it loses score on fold-dependent calibration shifts (bias sign flips).
- These are consistent with leaderboard outcomes where MAE remains above top-tier submissions.

## 6) Actionable Next Steps
1. Add post-prediction calibration for amplitude by fitting a monotonic mapping on validation folds (`y_hat -> y`) to reduce low/high quantile compression.
2. Add asymmetric residual objective that penalizes underprediction on high-demand regime (`is_post_rebound=1`) slightly more than overprediction.
3. Add a month-local bias correction layer by learning fold-robust month-of-year intercept adjustments on residuals.
4. Keep this report as baseline reference and compare future models against this exact decomposition (fold, horizon, quantile, month), not only aggregate MAE.

## 7) Bottom Line
`pass_2_hybrid_regime_lgbm` is currently the strongest model, but its remaining error is concentrated in **tail amplitude underestimation and month-local calibration shifts**. Reducing those two effects is the highest-leverage path to improve leaderboard MAE further.
