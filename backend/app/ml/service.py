from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.features import EnergyFeatureRow, build_feature_vector
from app.models import EnergyReading, Entity
from app.services import period_start

ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "energy_isolation_forest.joblib"
DATASET_NAME = "UCI Individual Household Electric Power Consumption"
DATASET_DOI = "10.24432/C58K54"


@dataclass(frozen=True)
class ModelArtifact:
    model: Any
    metadata: dict[str, Any]


def load_model_artifact(path: Path = ARTIFACT_PATH) -> ModelArtifact:
    if not path.exists():
        raise HTTPException(status_code=503, detail="model_not_ready")
    try:
        import joblib
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="model_runtime_not_ready") from exc

    payload = joblib.load(path)
    if not isinstance(payload, dict) or "model" not in payload:
        raise HTTPException(status_code=503, detail="model_artifact_invalid")
    metadata = dict(payload.get("metadata") or {})
    return ModelArtifact(model=payload["model"], metadata=metadata)


async def load_energy_feature_rows(db: AsyncSession, period: str, limit: int) -> list[EnergyFeatureRow]:
    start = period_start(period)
    rows = (
        await db.execute(
            select(EnergyReading, Entity.name)
            .join(Entity, Entity.entity_id == EnergyReading.entity_id, isouter=True)
            .where(EnergyReading.recorded_at >= start)
            .order_by(EnergyReading.recorded_at.desc())
            .limit(limit)
        )
    ).all()

    feature_rows: list[EnergyFeatureRow] = []
    for reading, entity_name in reversed(rows):
        feature_rows.append(
            EnergyFeatureRow(
                id=str(reading.id),
                entity_id=reading.entity_id,
                device_name=entity_name or reading.entity_id,
                recorded_at=reading.recorded_at,
                power_w=float(reading.power_w or 0),
                energy_kwh=float(reading.energy_kwh or 0),
                features=build_feature_vector(reading.power_w, reading.energy_kwh, reading.recorded_at),
            )
        )
    return feature_rows


def severity_for_score(score: float) -> str:
    if score >= 0.12:
        return "high"
    if score >= 0.06:
        return "medium"
    return "low"


def reason_for(row: EnergyFeatureRow, score: float) -> str:
    if row.power_w >= 1500:
        return "Высокая мгновенная мощность относительно ML-профиля"
    if row.recorded_at.hour < 6 and row.power_w >= 700:
        return "Нетипичное ночное потребление по ML-профилю"
    if score >= 0.12:
        return "Сильное отклонение от обученного профиля потребления"
    return "Отклонение от обученного профиля потребления"


async def detect_energy_anomalies(db: AsyncSession, period: str, limit: int) -> dict[str, Any]:
    artifact = load_model_artifact()
    rows = await load_energy_feature_rows(db, period, limit)
    metadata = artifact.metadata
    model_name = metadata.get("model_name", "IsolationForest")
    trained_at = metadata.get("trained_at") or datetime.now(UTC).isoformat()
    dataset = metadata.get("dataset", DATASET_NAME)

    if not rows:
        return {
            "model": {"name": model_name, "dataset": dataset, "trained_at": trained_at, "confidence": "ml"},
            "summary": {"total": 0, "anomalies": 0, "period": period},
            "anomalies": [],
            "timeline": [],
        }

    feature_matrix = [row.features for row in rows]
    raw_scores = artifact.model.decision_function(feature_matrix)
    predictions = artifact.model.predict(feature_matrix)

    timeline = []
    anomalies = []
    for row, raw_score, prediction in zip(rows, raw_scores, predictions, strict=True):
        anomaly_score = round(float(-raw_score), 4)
        is_anomaly = int(prediction) == -1
        timeline.append(
            {
                "timestamp": row.recorded_at.isoformat(),
                "power_w": round(row.power_w, 2),
                "energy_kwh": round(row.energy_kwh, 3),
                "anomaly_score": anomaly_score,
                "anomaly": is_anomaly,
            }
        )
        if is_anomaly:
            anomalies.append(
                {
                    "id": row.id,
                    "entity_id": row.entity_id,
                    "device_name": row.device_name,
                    "recorded_at": row.recorded_at.isoformat(),
                    "power_w": round(row.power_w, 2),
                    "energy_kwh": round(row.energy_kwh, 3),
                    "anomaly_score": anomaly_score,
                    "severity": severity_for_score(anomaly_score),
                    "reason": reason_for(row, anomaly_score),
                }
            )

    return {
        "model": {"name": model_name, "dataset": dataset, "trained_at": trained_at, "confidence": "ml"},
        "summary": {"total": len(rows), "anomalies": len(anomalies), "period": period},
        "anomalies": anomalies,
        "timeline": timeline,
    }

