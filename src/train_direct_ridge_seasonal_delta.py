from __future__ import annotations

import argparse
from pathlib import Path

from forecasting.config import DEFAULT_KNOT1, DEFAULT_KNOT2
from train_direct_seasonal_delta import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Train direct_ridge_seasonal_delta and write one Kaggle submission CSV.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--out-file", type=Path, default=Path("submissions/submission_direct_ridge_seasonal_delta.csv"))
    parser.add_argument("--knot1", type=str, default=DEFAULT_KNOT1)
    parser.add_argument("--knot2", type=str, default=DEFAULT_KNOT2)
    args = parser.parse_args()

    out_file = run(args.data_dir, args.out_file, args.knot1, args.knot2, model_kind="ridge")
    print(f"Wrote: {out_file.resolve()}")


if __name__ == "__main__":
    main()
