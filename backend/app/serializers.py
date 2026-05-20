from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Area, Automation, Device, Entity, Event, Home, User


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


def entity_out(entity: Entity) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "domain": entity.domain,
        "name": entity.name,
        "device_id": str(entity.device_id) if entity.device_id else None,
        "area_id": str(entity.area_id) if entity.area_id else None,
        "state": entity.state,
        "attributes": entity.attributes_json or {},
        "unit_of_measurement": entity.unit_of_measurement,
        "device_class": entity.device_class,
        "last_changed": entity.updated_at,
        "last_updated": entity.updated_at,
    }


def device_out(device: Device, detailed: bool = False) -> dict[str, Any]:
    data = {
        "id": str(device.id),
        "name": device.name,
        "name_by_user": device.name_by_user,
        "type": device.type,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "area_id": str(device.area_id) if device.area_id else None,
        "area_name": device.area.name if device.area else None,
        "status": device.status,
        "entity_count": len(device.entities),
        "created_at": device.created_at,
        "updated_at": device.updated_at,
    }
    if detailed:
        data["entities"] = [entity_out(entity) for entity in device.entities]
    return data


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


def event_out(event: Event) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "old_state": event.old_state,
        "new_state": event.new_state,
        "source": event.source,
        "user_id": str(event.user_id) if event.user_id else None,
        "automation_id": str(event.automation_id) if event.automation_id else None,
        "metadata": event.metadata_json or {},
        "created_at": event.created_at,
    }
