from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.features import build_feature_vector
from app.ml import service as ml_service
from app.models import EnergyReading
from app.routers import ml as ml_router


def test_energy_feature_generation_is_deterministic_and_handles_missing_values() -> None:
    recorded_at = datetime(2026, 5, 21, 3, 30, tzinfo=UTC)

    first = build_feature_vector(None, None, recorded_at)
    second = build_feature_vector(None, None, recorded_at)

    assert first == second
    assert first[0] == 0
    assert first[1] == 0
    assert len(first) == 6


@pytest.mark.asyncio
async def test_ml_anomalies_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/ml/anomalies")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ml_anomalies_contract(auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_detect_energy_anomalies(_db: Any, period: str, limit: int) -> dict[str, Any]:
        assert period == "day"
        assert limit == 100
        return {
            "model": {
                "name": "IsolationForest",
                "dataset": "UCI Individual Household Electric Power Consumption",
                "trained_at": "2026-05-21T00:00:00+00:00",
                "confidence": "ml",
            },
            "summary": {"total": 1, "anomalies": 1, "period": period},
            "anomalies": [
                {
                    "id": "reading-1",
                    "entity_id": "sensor.main_energy_power",
                    "device_name": "Main Energy Power",
                    "recorded_at": "2026-05-21T00:00:00+00:00",
                    "power_w": 1800,
                    "energy_kwh": 1.8,
                    "anomaly_score": 0.16,
                    "severity": "high",
                    "reason": "Высокая мгновенная мощность относительно ML-профиля",
                }
            ],
            "timeline": [
                {
                    "timestamp": "2026-05-21T00:00:00+00:00",
                    "power_w": 1800,
                    "energy_kwh": 1.8,
                    "anomaly_score": 0.16,
                    "anomaly": True,
                }
            ],
        }

    monkeypatch.setattr(ml_router, "detect_energy_anomalies", fake_detect_energy_anomalies)

    response = await auth_client.get("/api/ml/anomalies", params={"period": "day"})

    assert response.status_code == 200
    body = response.json()
    assert body["model"]["name"] == "IsolationForest"
    assert body["model"]["confidence"] == "ml"
    assert body["summary"] == {"total": 1, "anomalies": 1, "period": "day"}
    assert body["timeline"][0]["anomaly"] is True
    assert body["anomalies"][0]["severity"] == "high"


@pytest.mark.asyncio
async def test_ml_anomalies_reports_missing_model(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/ml/anomalies", params={"period": "day"})

    assert response.status_code == 503
    assert response.json() == {"error": "model_not_ready", "message": "model_not_ready"}


@pytest.mark.asyncio
async def test_ml_anomalies_handles_empty_energy_readings(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ml_service,
        "load_model_artifact",
        lambda: ml_service.ModelArtifact(
            model=object(),
            metadata={
                "model_name": "IsolationForest",
                "dataset": "UCI Individual Household Electric Power Consumption",
                "trained_at": "2026-05-21T00:00:00+00:00",
            },
        ),
    )
    await db_session.execute(delete(EnergyReading))
    await db_session.commit()

    body = await ml_service.detect_energy_anomalies(db_session, "day", 100)

    assert body["summary"] == {"total": 0, "anomalies": 0, "period": "day"}
    assert body["timeline"] == []
    assert body["anomalies"] == []
