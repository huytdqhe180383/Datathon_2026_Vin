# Datathon 2026

This repo combines two tracks of work for the competition:

- A forecasting pipeline that produces `Revenue` and `COGS` submissions for the 548-day target horizon
- A set of EDA and storytelling notebooks that turn the raw commerce tables into a presentation-ready business narrative

## What is in the repo

- `data/raw/`: source competition files
- `data/processed/`: placeholder for transformed datasets
- `notebooks/`: EDA, baseline, and storytelling notebooks
- `src/`: forecasting training and diagnostics scripts
- `tests/`: unit tests for forecasting utilities
- `reports/`: saved validation, model-selection, and diagnostics outputs
- `submissions/`: generated submission CSVs

## Main files

- `notebooks/data_storytelling.ipynb`: business-facing notebook with customer value, promo effectiveness, and return-risk analysis
- `notebooks/eda_raw_data.ipynb`: raw data exploration
- `notebooks/eda_task_focused.ipynb`: task-oriented EDA
- `src/two_pass_forecast.py`: main training, evaluation, model selection, and submission export script
- `src/analyze_forecast_failures.py`: diagnostics for horizon-level forecast errors

## Environment setup

Python 3.10+ is recommended.

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install numpy pandas matplotlib seaborn scikit-learn lightgbm nbconvert nbclient jupyter-core pytest
```

## Run the storytelling notebook

From the repo root:

```bash
python -m nbconvert --to notebook --execute --inplace notebooks/data_storytelling.ipynb
```

The notebook is structured as a narrative rather than a loose EDA dump. It now answers three business questions:

1. Which customers drive the most value, and how concentrated is revenue?
2. Are promotions creating healthy demand, and which traffic sources convert most efficiently?
3. Which product categories and return reasons are creating the largest quality and refund risk?

The notebook writes charts and printed takeaways back into the same `.ipynb` file.

## Run the forecasting pipeline

```bash
python src/two_pass_forecast.py --data-dir data/raw --out-dir submissions --report-dir reports
```

Key outputs:

- `submissions/submission_pass1.csv`
- `submissions/submission_pass2.csv`
- `reports/forecasting/selection/selected_models.csv`
- `reports/forecasting/validation/model_tuning_summary.csv`
- `reports/forecasting/validation/model_holdout_summary.csv`

## Run diagnostics

```bash
python src/analyze_forecast_failures.py
```

This writes error diagnostics to `reports/forecasting/diagnostics/`.

## Run tests

```bash
pytest -q
```

## Notes

- The forecasting workflow uses a 548-day horizon by default.
- Validation artifacts already stored under `reports/` can be used to compare candidate models without retraining immediately.
- `data_storytelling.ipynb` is presentation-friendly and uses the real dataset schema rather than placeholder joins or assumed columns.
