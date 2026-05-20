from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query

from app.ml.service import detect_energy_anomalies
from app.routers.deps import CurrentUser, Db

router = APIRouter()

Period = Literal["day", "week", "month"]


@router.get("/ml/anomalies")
async def ml_anomalies(
    _: CurrentUser,
    db: Db,
    period: Period = "day",
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return await detect_energy_anomalies(db, period, limit)

