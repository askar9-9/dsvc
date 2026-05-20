from __future__ import annotations

import argparse
import io
import math
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.ml.features import FEATURE_COLUMNS
from app.ml.service import DATASET_DOI, DATASET_NAME

UCI_ZIP_URL = "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip"
RAW_FILE = "household_power_consumption.txt"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "app" / "ml" / "artifacts" / "energy_isolation_forest.joblib"


def read_dataset(dataset_path: Path | None) -> pd.DataFrame:
    if dataset_path is not None:
        return pd.read_csv(dataset_path, sep=";", na_values="?")

    with urllib.request.urlopen(UCI_ZIP_URL, timeout=60) as response:
        archive = zipfile.ZipFile(io.BytesIO(response.read()))
        with archive.open(RAW_FILE) as raw:
            return pd.read_csv(raw, sep=";", na_values="?")


def hourly_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["recorded_at"] = pd.to_datetime(data["Date"] + " " + data["Time"], dayfirst=True, errors="coerce")
    data["power_w"] = pd.to_numeric(data["Global_active_power"], errors="coerce") * 1000
    data["energy_kwh"] = data["power_w"] / 60 / 1000
    data = data.dropna(subset=["recorded_at", "power_w", "energy_kwh"])
    hourly = (
        data.set_index("recorded_at")[["power_w", "energy_kwh"]]
        .resample("h")
        .agg({"power_w": "mean", "energy_kwh": "sum"})
        .dropna()
        .reset_index()
    )
    hour_angle = (hourly["recorded_at"].dt.hour + hourly["recorded_at"].dt.minute / 60) / 24 * 2 * 3.141592653589793
    weekday_angle = hourly["recorded_at"].dt.weekday / 7 * 2 * 3.141592653589793
    hourly["hour_sin"] = hour_angle.map(math.sin)
    hourly["hour_cos"] = hour_angle.map(math.cos)
    hourly["weekday_sin"] = weekday_angle.map(math.sin)
    hourly["weekday_cos"] = weekday_angle.map(math.cos)
    return hourly[FEATURE_COLUMNS]


def train(dataset_path: Path | None, output_path: Path) -> None:
    features = hourly_features(read_dataset(dataset_path))
    model = IsolationForest(random_state=42, contamination=0.03)
    model.fit(features)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "metadata": {
                "model_name": "IsolationForest",
                "dataset": DATASET_NAME,
                "dataset_doi": DATASET_DOI,
                "trained_at": datetime.now(UTC).isoformat(),
                "features": FEATURE_COLUMNS,
                "contamination": 0.03,
                "samples": int(len(features)),
            },
        },
        output_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the household energy anomaly IsolationForest model.")
    parser.add_argument("--dataset", type=Path, default=None, help="Optional local UCI household_power_consumption.txt path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    train(args.dataset, args.output)


if __name__ == "__main__":
    main()
