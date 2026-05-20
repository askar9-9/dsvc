from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.eventbus import event_bus
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models import Area, Automation, Device, EnergyReading, Entity, EntityState, Event, Home, User
from app.services import (
    call_action,
    create_default_entity_for_device,
    delete_by_id,
    device_out,
    energy_summary,
    entity_out,
    get_default_home,
    get_entity_or_404,
    period_start,
    run_automation,
    set_entity_state,
)

api = APIRouter(prefix="/api")
CurrentUser = Annotated[User, Depends(get_current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


class LoginRequest(BaseModel):
    username: str
    password: str


class HomeCreate(BaseModel):
    name: str
    time_zone: str = "Asia/Almaty"
    latitude: float | None = None
    longitude: float | None = None
    currency: str = "KZT"


class AreaCreate(BaseModel):
    name: str
    icon: str | None = None
    floor_id: uuid.UUID | None = None
    temperature_entity_id: str | None = None
    humidity_entity_id: str | None = None


class AreaUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    floor_id: uuid.UUID | None = None
    temperature_entity_id: str | None = None
    humidity_entity_id: str | None = None


class DeviceCreate(BaseModel):
    name: str
    type: str
    area_id: uuid.UUID | None = None
    manufacturer: str | None = None
    model: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    name_by_user: str | None = None
    area_id: uuid.UUID | None = None
    status: str | None = None
    manufacturer: str | None = None
    model: str | None = None


class EntityStatePatch(BaseModel):
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class ActionCall(BaseModel):
    domain: str
    action: str
    target: dict[str, Any]
    data: dict[str, Any] = Field(default_factory=dict)


class AutomationCreate(BaseModel):
    name: str
    description: str = ""
    is_enabled: bool = True
    mode: str = "single"
    trigger: dict[str, Any]
    condition: dict[str, Any] | None = None
    action: dict[str, Any]


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    mode: str | None = None
    trigger: dict[str, Any] | None = None
    condition: dict[str, Any] | None = None
    action: dict[str, Any] | None = None


def user_out(user: User, include_created: bool = False) -> dict[str, Any]:
    data = {"id": str(user.id), "name": user.name, "username": user.username, "is_admin": user.is_admin}
    if include_created:
        data["created_at"] = user.created_at
    return data


def home_out(home: Home) -> dict[str, Any]:
    return {
        "id": str(home.id),
        "name": home.name,
        "latitude": home.latitude,
        "longitude": home.longitude,
        "time_zone": home.time_zone,
        "currency": home.currency,
        "created_at": home.created_at,
    }


async def area_out(db: AsyncSession, area: Area) -> dict[str, Any]:
    device_count = (await db.execute(select(func.count(Device.id)).where(Device.area_id == area.id))).scalar_one()
    entity_count = (await db.execute(select(func.count(Entity.id)).where(Entity.area_id == area.id))).scalar_one()
    return {
        "id": str(area.id),
        "home_id": str(area.home_id),
        "name": area.name,
        "icon": area.icon,
        "floor_id": str(area.floor_id) if area.floor_id else None,
        "temperature_entity_id": area.temperature_entity_id,
        "humidity_entity_id": area.humidity_entity_id,
        "device_count": device_count,
        "entity_count": entity_count,
        "created_at": area.created_at,
        "updated_at": area.updated_at,
    }


def automation_out(automation: Automation) -> dict[str, Any]:
    return {
        "id": str(automation.id),
        "name": automation.name,
        "description": automation.description,
        "is_enabled": automation.is_enabled,
        "mode": automation.mode,
        "trigger": automation.trigger_json,
        "condition": automation.condition_json,
        "action": automation.action_json,
        "last_triggered": automation.last_triggered,
        "created_at": automation.created_at,
    }


@api.get("/health", include_in_schema=False)
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "smart-home-backend"}


@api.post("/auth/login")
async def login(payload: LoginRequest, db: Db) -> dict[str, Any]:
    user = (await db.execute(select(User).where(User.username == payload.username))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "expires_in": settings.jwt_expires_seconds,
        "user": user_out(user),
    }


@api.post("/auth/logout")
async def logout(_: CurrentUser) -> dict[str, bool]:
    return {"ok": True}


@api.get("/auth/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    return user_out(user, include_created=True)


@api.get("/homes")
async def list_homes(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    homes = (await db.execute(select(Home).order_by(Home.created_at))).scalars().all()
    return [home_out(home) for home in homes]


@api.post("/homes", status_code=201)
async def create_home(payload: HomeCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = Home(**payload.model_dump(), unit_system={"temperature": "C", "length": "metric"})
    db.add(home)
    await db.commit()
    await db.refresh(home)
    return home_out(home)


@api.get("/areas")
async def list_areas(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    areas = (await db.execute(select(Area).order_by(Area.created_at))).scalars().all()
    return [await area_out(db, area) for area in areas]


@api.post("/areas", status_code=201)
async def create_area(payload: AreaCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = await get_default_home(db)
    area = Area(home_id=home.id, **payload.model_dump())
    db.add(area)
    await db.commit()
    await db.refresh(area)
    return await area_out(db, area)


@api.patch("/areas/{area_id}")
async def update_area(area_id: uuid.UUID, payload: AreaUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    area = await db.get(Area, area_id)
    if area is None:
        raise HTTPException(404, "Area not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(area, key, value)
    await db.commit()
    await db.refresh(area)
    return await area_out(db, area)


@api.delete("/areas/{area_id}", status_code=204)
async def delete_area(area_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Area, area_id)
    return Response(status_code=204)


@api.get("/devices")
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


@api.post("/devices", status_code=201)
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


@api.get("/devices/{device_id}")
async def get_device(device_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    device = (await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id == device_id))).scalar_one_or_none()
    if device is None:
        raise HTTPException(404, "Device not found")
    return device_out(device, detailed=True)


@api.patch("/devices/{device_id}")
async def update_device(device_id: uuid.UUID, payload: DeviceUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    device = await db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, "Device not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, key, value)
    await db.commit()
    result = await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id == device.id))
    return device_out(result.scalar_one(), detailed=True)


@api.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Device, device_id)
    return Response(status_code=204)


@api.get("/entities")
async def list_entities(_: CurrentUser, db: Db, domain: str | None = None, area_id: uuid.UUID | None = None, device_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    stmt = select(Entity).order_by(Entity.entity_id)
    if domain:
        stmt = stmt.where(Entity.domain == domain)
    if area_id:
        stmt = stmt.where(Entity.area_id == area_id)
    if device_id:
        stmt = stmt.where(Entity.device_id == device_id)
    return [entity_out(entity) for entity in (await db.execute(stmt)).scalars().all()]


@api.get("/entities/{entity_id}")
async def get_entity(entity_id: str, _: CurrentUser, db: Db) -> dict[str, Any]:
    return entity_out(await get_entity_or_404(db, entity_id))


@api.patch("/entities/{entity_id}/state")
async def patch_entity_state(entity_id: str, payload: EntityStatePatch, user: CurrentUser, db: Db) -> dict[str, Any]:
    entity = await get_entity_or_404(db, entity_id)
    await set_entity_state(db, entity, payload.state, payload.attributes, source="user", user_id=user.id)
    await db.commit()
    return {"entity_id": entity.entity_id, "state": entity.state, "attributes": entity.attributes_json or {}, "last_changed": entity.updated_at}


@api.get("/entities/{entity_id}/history")
async def entity_history(
    entity_id: str,
    _: CurrentUser,
    db: Db,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
) -> list[dict[str, Any]]:
    stmt = select(EntityState).where(EntityState.entity_id == entity_id).order_by(EntityState.last_changed)
    if from_:
        stmt = stmt.where(EntityState.last_changed >= from_)
    if to:
        stmt = stmt.where(EntityState.last_changed <= to)
    rows = (await db.execute(stmt)).scalars().all()
    return [{"state": row.state, "attributes": row.attributes_json or {}, "last_changed": row.last_changed, "last_updated": row.last_updated} for row in rows]


@api.post("/actions/call")
async def actions_call(payload: ActionCall, user: CurrentUser, db: Db) -> dict[str, Any]:
    return await call_action(db, payload.domain, payload.action, payload.target, payload.data, source="user", user_id=user.id)


@api.get("/automations")
async def list_automations(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Automation).order_by(Automation.created_at))).scalars().all()
    return [automation_out(row) for row in rows]


@api.post("/automations", status_code=201)
async def create_automation(payload: AutomationCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = await get_default_home(db)
    automation = Automation(home_id=home.id, trigger_json=payload.trigger, condition_json=payload.condition, action_json=payload.action, **payload.model_dump(exclude={"trigger", "condition", "action"}))
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation_out(automation)


@api.get("/automations/{automation_id}")
async def get_automation(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(404, "Automation not found")
    return automation_out(automation)


@api.patch("/automations/{automation_id}")
async def update_automation(automation_id: uuid.UUID, payload: AutomationUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(404, "Automation not found")
    mapping = {"trigger": "trigger_json", "condition": "condition_json", "action": "action_json"}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(automation, mapping.get(key, key), value)
    await db.commit()
    await db.refresh(automation)
    return automation_out(automation)


@api.delete("/automations/{automation_id}", status_code=204)
async def delete_automation(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Automation, automation_id)
    return Response(status_code=204)


@api.post("/automations/{automation_id}/run")
async def run_automation_endpoint(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(404, "Automation not found")
    run = await run_automation(db, automation, triggered_by="manual")
    await db.commit()
    return {"ok": True, "run_id": str(run.id), "automation_id": str(automation.id), "triggered_at": run.started_at}


@api.get("/events")
async def list_events(
    _: CurrentUser,
    db: Db,
    entity_id: str | None = None,
    device_id: uuid.UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    stmt = select(Event)
    count_stmt = select(func.count(Event.id))
    filters = []
    if entity_id:
        filters.append(Event.entity_id == entity_id)
    if device_id:
        entity_ids = select(Entity.entity_id).where(Entity.device_id == device_id)
        filters.append(Event.entity_id.in_(entity_ids))
    if from_:
        filters.append(Event.created_at >= from_)
    if to:
        filters.append(Event.created_at <= to)
    if filters:
        stmt = stmt.where(and_(*filters))
        count_stmt = count_stmt.where(and_(*filters))
    total = (await db.execute(count_stmt)).scalar_one()
    rows = (await db.execute(stmt.order_by(Event.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "id": str(row.id),
                "entity_id": row.entity_id,
                "event_type": row.event_type,
                "old_state": row.old_state,
                "new_state": row.new_state,
                "source": row.source,
                "user_id": str(row.user_id) if row.user_id else None,
                "automation_id": str(row.automation_id) if row.automation_id else None,
                "metadata": row.metadata_json or {},
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@api.get("/events/stream")
async def events_stream(_: CurrentUser, request: Request) -> EventSourceResponse:
    async def generator():
        async for event in event_bus.stream():
            if await request.is_disconnected():
                break
            yield {"data": json.dumps(event.sse_payload(), default=str)}

    return EventSourceResponse(generator())


@api.get("/energy/summary")
async def get_energy_summary(_: CurrentUser, db: Db, period: str = "day") -> dict[str, Any]:
    return await energy_summary(db, period)


@api.get("/energy/consumption")
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


@api.get("/energy/devices")
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


@api.get("/energy/forecast")
async def energy_forecast(_: CurrentUser, db: Db) -> dict[str, Any]:
    rows = (
        await db.execute(select(EnergyReading.power_w, EnergyReading.energy_kwh).order_by(EnergyReading.recorded_at.desc()).limit(24))
    ).all()
    values = list(reversed(rows)) or [(0, 0)]
    forecast = [{"hour": index, "predicted_kwh": round(float(row[1] or 0), 3), "predicted_power_w": round(float(row[0] or 0), 2)} for index, row in enumerate(values[:24])]
    return {"period_hours": 24, "forecast": forecast, "total_predicted_kwh": round(sum(item["predicted_kwh"] for item in forecast), 3), "confidence": "mock"}


@api.get("/dashboard")
async def dashboard(_: CurrentUser, db: Db) -> dict[str, Any]:
    home = await get_default_home(db)
    areas = (await db.execute(select(Area).order_by(Area.created_at))).scalars().all()
    area_cards = []
    for area in areas:
        devices_total = (await db.execute(select(func.count(Device.id)).where(Device.area_id == area.id))).scalar_one()
        devices_online = (await db.execute(select(func.count(Device.id)).where(Device.area_id == area.id, Device.status == "online"))).scalar_one()
        temp = None
        humidity = None
        if area.temperature_entity_id:
            temp_entity = (await db.execute(select(Entity).where(Entity.entity_id == area.temperature_entity_id))).scalar_one_or_none()
            temp = temp_entity.state if temp_entity else None
        if area.humidity_entity_id:
            humidity_entity = (await db.execute(select(Entity).where(Entity.entity_id == area.humidity_entity_id))).scalar_one_or_none()
            humidity = humidity_entity.state if humidity_entity else None
        area_cards.append({"id": str(area.id), "name": area.name, "icon": area.icon, "temperature": temp, "humidity": humidity, "devices_online": devices_online, "devices_total": devices_total})
    summary = await energy_summary(db, "day")
    devices_total = (await db.execute(select(func.count(Device.id)))).scalar_one()
    devices_online = (await db.execute(select(func.count(Device.id)).where(Device.status == "online"))).scalar_one()
    automations_active = (await db.execute(select(func.count(Automation.id)).where(Automation.is_enabled.is_(True)))).scalar_one()
    recent = await list_events(_, db, from_=None, to=None, limit=10, offset=0)
    return {
        "home": {"id": str(home.id), "name": home.name},
        "areas": area_cards,
        "summary": {
            "devices_total": devices_total,
            "devices_online": devices_online,
            "automations_active": automations_active,
            "energy_today_kwh": summary["total_kwh"],
            "current_power_w": summary["current_power_w"],
        },
        "recent_events": recent["events"],
    }
