from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.models import Area
from app.routers.deps import CurrentUser, Db
from app.schemas import AreaCreate, AreaUpdate
from app.serializers import area_out
from app.services import delete_by_id, get_default_home

router = APIRouter()


@router.get("/areas")
async def list_areas(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    areas = (await db.execute(select(Area).order_by(Area.created_at))).scalars().all()
    return [await area_out(db, area) for area in areas]


@router.post("/areas", status_code=201)
async def create_area(payload: AreaCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = await get_default_home(db)
    area = Area(home_id=home.id, **payload.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return await area_out(db, area)


@router.patch("/areas/{area_id}")
async def update_area(area_id: uuid.UUID, payload: AreaUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    area = await db.get(Area, area_id)
    if area is None:
        raise HTTPException(404, "Area not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(area, key, value)
    await db.commit()
    await db.refresh(area)
    return await area_out(db, area)


@router.delete("/areas/{area_id}", status_code=204)
async def delete_area(area_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Area, area_id)
    return Response(status_code=204)
