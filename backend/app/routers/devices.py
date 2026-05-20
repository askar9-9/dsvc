from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Device
from app.routers.deps import CurrentUser, Db
from app.schemas import DeviceCreate, DeviceUpdate
from app.serializers import device_out
from app.services import create_default_entity_for_device, delete_by_id, get_default_home

router = APIRouter()


@router.get("/devices")
async def list_devices(
    _: CurrentUser,
    db: Db,
    area_id: uuid.UUID | None = None,
    type: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(Device).options(selectinload(Device.area), selectinload(Device.entities)).order_by(Device.created_at)
    if area_id:
        stmt = stmt.where(Device.area_id == area_id)
    if type:
        stmt = stmt.where(Device.type == type)
    if status:
        stmt = stmt.where(Device.status == status)
    return [device_out(device) for device in (await db.execute(stmt)).scalars().all()]


@router.post("/devices", status_code=201)
async def create_device(payload: DeviceCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    if payload.type not in {"light", "switch", "sensor", "climate", "energy_meter"}:
        raise HTTPException(400, "Unsupported device type")
    home = await get_default_home(db)
    device = Device(home_id=home.id, **payload.model_dump())
    db.add(device)
    await db.flush()
    await create_default_entity_for_device(db, device)
    await db.commit()
    result = await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id == device.id))
    return device_out(result.scalar_one(), detailed=True)


@router.get("/devices/{device_id}")
async def get_device(device_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    device = (await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id == device_id))).scalar_one_or_none()
    if device is None:
        raise HTTPException(404, "Device not found")
    return device_out(device, detailed=True)


@router.patch("/devices/{device_id}")
async def update_device(device_id: uuid.UUID, payload: DeviceUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, key, value)
    await db.commit()
    result = await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id == device.id))
    return device_out(result.scalar_one(), detailed=True)


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Device, device_id)
    return Response(status_code=204)
