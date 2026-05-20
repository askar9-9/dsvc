from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.models import EnergyReading
from app.routers.deps import CurrentUser, Db
from app.services import energy_summary, get_entity_or_404, period_start

router = APIRouter()


@router.get("/energy/summary")
async def get_energy_summary(_: CurrentUser, db: Db, period: str = "day") -> dict[str, Any]:
    return await energy_summary(db, period)


@router.get("/energy/consumption")
async def energy_consumption(_: CurrentUser, db: Db, period: str = "day", granularity: str = "hour") -> dict[str, Any]:
    start = period_start(period)
    rows = (
        await db.execute(
            select(
                func.date_trunc(granularity, EnergyReading.recorded_at).label("bucket"),
                func.sum(EnergyReading.energy_kwh),
                func.avg(EnergyReading.power_w),
            )
            .where(EnergyReading.recorded_at >= start)
            .group_by("bucket")
            .order_by("bucket")
        )
    ).all()
    return {"period": period, "granularity": granularity, "data": [{"timestamp": row[0], "kwh": round(float(row[1] or 0), 3), "power_w": round(float(row[2] or 0), 2)} for row in rows]}


@router.get("/energy/devices")
async def energy_devices(_: CurrentUser, db: Db, period: str = "day") -> list[dict[str, Any]]:
    start = period_start(period)
    rows = (
        await db.execute(
            select(EnergyReading.entity_id, func.sum(EnergyReading.energy_kwh), func.avg(EnergyReading.power_w))
            .where(EnergyReading.recorded_at >= start)
            .group_by(EnergyReading.entity_id)
        )
    ).all()
    total = sum(float(row[1] or 0) for row in rows) or 1
    out = []
    for entity_id, kwh, avg_power in rows:
        entity = await get_entity_or_404(db, entity_id)
        current = float(entity.state or 0) if str(entity.state).replace(".", "", 1).isdigit() else float(avg_power or 0)
        seven_day_avg = (
            await db.execute(select(func.avg(EnergyReading.power_w)).where(EnergyReading.entity_id == entity_id, EnergyReading.recorded_at >= datetime.now(UTC) - timedelta(days=7)))
        ).scalar_one() or 0
        anomaly = current > float(seven_day_avg) * 1.4 if seven_day_avg else False
        item = {
            "entity_id": entity_id,
            "device_name": entity.name,
            "kwh": round(float(kwh or 0), 3),
            "current_power_w": round(current, 2),
            "percentage": round(float(kwh or 0) / total * 100, 2),
            "anomaly": anomaly,
        }
        if anomaly:
            item["anomaly_reason"] = "Потребление выше среднего за 7 дней более чем на 40%"
        out.append(item)
    return out


@router.get("/energy/forecast")
async def energy_forecast(_: CurrentUser, db: Db) -> dict[str, Any]:
    rows = (
        await db.execute(select(EnergyReading.power_w, EnergyReading.energy_kwh).order_by(EnergyReading.recorded_at.desc()).limit(24))
    ).all()
    values = list(reversed(rows)) or [(0, 0)]
    forecast = [{"hour": index, "predicted_kwh": round(float(row[1] or 0), 3), "predicted_power_w": round(float(row[0] or 0), 2)} for index, row in enumerate(values[:24])]
    return {"period_hours": 24, "forecast": forecast, "total_predicted_kwh": round(sum(item["predicted_kwh"] for item in forecast), 3), "confidence": "mock"}
