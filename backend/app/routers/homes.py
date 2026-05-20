from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.models import Home
from app.routers.deps import CurrentUser, Db
from app.schemas import HomeCreate
from app.serializers import home_out

router = APIRouter()


@router.get("/homes")
async def list_homes(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    homes = (await db.execute(select(Home).order_by(Home.created_at))).scalars().all()
    return [home_out(home) for home in homes]


@router.post("/homes", status_code=201)
async def create_home(payload: HomeCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = Home(**payload.model_dump(), unit_system={"temperature": "C", "length": "metric"})
    db.add(home)
    await db.commit()
    await db.refresh(home)
    return home_out(home)
