from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select

from app.models import Area, Automation, Device, Entity
from app.routers.deps import CurrentUser, Db
from app.routers.events import query_events
from app.services import energy_summary, get_default_home

router = APIRouter()


@router.get("/dashboard")
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
    recent = await query_events(db, limit=10, offset=0)
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
