from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.eventbus import DomainEvent, event_bus
from app.models import (
    Area,
    Automation,
    AutomationRun,
    Device,
    EnergyReading,
    Entity,
    EntityState,
    Event,
    Home,
    Integration,
    utcnow,
)


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return "_".join(part for part in cleaned.split("_") if part) or "device"


DISCOVERY_CATALOG: dict[str, list[dict[str, Any]]] = {
    "demo": [
        {
            "discovered_id": "demo.porch_light",
            "name": "Porch Light",
            "type": "light",
            "manufacturer": "Demo",
            "model": "DL-100",
            "entities": [
                {
                    "entity_id": "light.porch_light",
                    "domain": "light",
                    "name": "Porch Light",
                    "state": "off",
                    "attributes": {"brightness": 0},
                }
            ],
        },
        {
            "discovered_id": "demo.garage_outlet",
            "name": "Garage Outlet",
            "type": "switch",
            "manufacturer": "Demo",
            "model": "DS-10",
            "entities": [
                {
                    "entity_id": "switch.garage_outlet",
                    "domain": "switch",
                    "name": "Garage Outlet",
                    "state": "off",
                    "attributes": {},
                }
            ],
        },
        {
            "discovered_id": "demo.office_climate",
            "name": "Office Climate",
            "type": "climate",
            "manufacturer": "Demo",
            "model": "DC-22",
            "entities": [
                {
                    "entity_id": "climate.office",
                    "domain": "climate",
                    "name": "Office Climate",
                    "state": "off",
                    "attributes": {"current_temperature": 22, "target_temperature": 22, "hvac_mode": "off"},
                    "device_class": "temperature",
                }
            ],
        },
        {
            "discovered_id": "demo.balcony_sensor",
            "name": "Balcony Sensor",
            "type": "sensor",
            "manufacturer": "Demo",
            "model": "DT-2",
            "entities": [
                {
                    "entity_id": "sensor.balcony_temperature",
                    "domain": "sensor",
                    "name": "Balcony Temperature",
                    "state": "21.5",
                    "attributes": {"friendly_name": "Balcony Temperature"},
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                },
                {
                    "entity_id": "sensor.balcony_humidity",
                    "domain": "sensor",
                    "name": "Balcony Humidity",
                    "state": "41",
                    "attributes": {},
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                },
            ],
        },
        {
            "discovered_id": "demo.solar_meter",
            "name": "Solar Meter",
            "type": "energy_meter",
            "manufacturer": "Demo",
            "model": "DE-3",
            "entities": [
                {
                    "entity_id": "sensor.solar_meter_power",
                    "domain": "sensor",
                    "name": "Solar Meter Power",
                    "state": "0",
                    "attributes": {"energy_meter": True},
                    "unit_of_measurement": "W",
                    "device_class": "power",
                },
                {
                    "entity_id": "sensor.solar_meter_total",
                    "domain": "sensor",
                    "name": "Solar Meter Total",
                    "state": "0",
                    "attributes": {"state_class": "total_increasing"},
                    "unit_of_measurement": "kWh",
                    "device_class": "energy",
                },
            ],
        },
    ],
    "mqtt": [
        {
            "discovered_id": "mqtt.living_room_strip",
            "name": "MQTT Living Room Strip",
            "type": "light",
            "manufacturer": "MQTT",
            "model": "RGB-Strip",
            "entities": [
                {
                    "entity_id": "light.mqtt_living_room_strip",
                    "domain": "light",
                    "name": "MQTT Living Room Strip",
                    "state": "off",
                    "attributes": {
                        "brightness": 0,
                        "state_topic": "home/living_room/strip/state",
                        "command_topic": "home/living_room/strip/set",
                        "brightness_state_topic": "home/living_room/strip/brightness/state",
                        "brightness_command_topic": "home/living_room/strip/brightness/set",
                    },
                }
            ],
        },
        {
            "discovered_id": "mqtt.garage_relay",
            "name": "MQTT Garage Relay",
            "type": "switch",
            "manufacturer": "MQTT",
            "model": "Relay-1",
            "entities": [
                {
                    "entity_id": "switch.mqtt_garage_relay",
                    "domain": "switch",
                    "name": "MQTT Garage Relay",
                    "state": "off",
                    "attributes": {
                        "state_topic": "home/garage/relay/state",
                        "command_topic": "home/garage/relay/set",
                    },
                }
            ],
        },
        {
            "discovered_id": "mqtt.office_sensor",
            "name": "MQTT Office Sensor",
            "type": "sensor",
            "manufacturer": "MQTT",
            "model": "TH-1",
            "entities": [
                {
                    "entity_id": "sensor.mqtt_office_temperature",
                    "domain": "sensor",
                    "name": "MQTT Office Temperature",
                    "state": "22.4",
                    "attributes": {
                        "state_topic": "home/office/sensor/temperature",
                    },
                    "unit_of_measurement": "°C",
                    "device_class": "temperature",
                },
                {
                    "entity_id": "sensor.mqtt_office_humidity",
                    "domain": "sensor",
                    "name": "MQTT Office Humidity",
                    "state": "43",
                    "attributes": {
                        "state_topic": "home/office/sensor/humidity",
                    },
                    "unit_of_measurement": "%",
                    "device_class": "humidity",
                },
            ],
        },
    ],
}


def supported_integration_domain(domain: str) -> bool:
    return domain in DISCOVERY_CATALOG


async def get_default_home(db: AsyncSession) -> Home:
    home = (await db.execute(select(Home).order_by(Home.created_at).limit(1))).scalar_one_or_none()
    if home is None:
        raise HTTPException(404, "Home not found")
    return home


async def get_entity_or_404(db: AsyncSession, entity_id: str) -> Entity:
    entity = (await db.execute(select(Entity).where(Entity.entity_id == entity_id))).scalar_one_or_none()
    if entity is None:
        raise HTTPException(404, "Entity not found")
    return entity


async def create_default_entity_for_device(db: AsyncSession, device: Device) -> Entity:
    object_id = slugify(device.name_by_user or device.name)
    base = {
        "device_id": device.id,
        "area_id": device.area_id,
        "platform": "demo",
        "name": device.name_by_user or device.name,
        "original_name": device.name,
    }
    if device.type == "light":
        entity = Entity(entity_id=f"light.{object_id}", domain="light", state="off", attributes_json={"brightness": 0}, **base)
    elif device.type == "switch":
        entity = Entity(entity_id=f"switch.{object_id}", domain="switch", state="off", attributes_json={}, **base)
    elif device.type == "climate":
        entity = Entity(
            entity_id=f"climate.{object_id}",
            domain="climate",
            state="off",
            attributes_json={"current_temperature": 22, "target_temperature": 22, "hvac_mode": "off"},
            device_class="temperature",
            **base,
        )
    elif device.type == "energy_meter":
        entity = Entity(
            entity_id=f"sensor.{object_id}_power",
            domain="sensor",
            state="0",
            attributes_json={"friendly_name": device.name, "energy_meter": True},
            unit_of_measurement="W",
            device_class="power",
            **base,
        )
    else:
        entity = Entity(
            entity_id=f"sensor.{object_id}",
            domain="sensor",
            state="0",
            attributes_json={"friendly_name": device.name},
            unit_of_measurement="",
            **base,
        )
    db.add(entity)
    await db.flush()
    return entity


async def get_integration_or_404(db: AsyncSession, integration_id: uuid.UUID) -> Integration:
    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(404, "Integration not found")
    return integration


async def discovery_preview(db: AsyncSession, integration: Integration) -> list[dict[str, Any]]:
    if not supported_integration_domain(integration.domain):
        raise HTTPException(400, "Unsupported integration domain")
    entity_ids = [entity["entity_id"] for item in DISCOVERY_CATALOG[integration.domain] for entity in item["entities"]]
    existing = set((await db.execute(select(Entity.entity_id).where(Entity.entity_id.in_(entity_ids)))).scalars().all())
    return [
        {
            "discovered_id": item["discovered_id"],
            "name": item["name"],
            "type": item["type"],
            "manufacturer": item.get("manufacturer"),
            "model": item.get("model"),
            "suggested_entity_id": item["entities"][0]["entity_id"],
            "entities": [
                {
                    "entity_id": entity["entity_id"],
                    "domain": entity["domain"],
                    "platform": integration.domain,
                    "name": entity["name"],
                    "attributes": entity.get("attributes") or {},
                    "unit_of_measurement": entity.get("unit_of_measurement"),
                    "device_class": entity.get("device_class"),
                }
                for entity in item["entities"]
            ],
            "already_imported": any(entity["entity_id"] in existing for entity in item["entities"]),
        }
        for item in DISCOVERY_CATALOG[integration.domain]
    ]


async def import_discovered_devices(db: AsyncSession, integration: Integration, discovered_ids: list[str] | None = None) -> dict[str, Any]:
    if not supported_integration_domain(integration.domain):
        raise HTTPException(400, "Unsupported integration domain")
    catalog = {item["discovered_id"]: item for item in DISCOVERY_CATALOG[integration.domain]}
    selected_ids = discovered_ids or list(catalog)
    unknown = [item_id for item_id in selected_ids if item_id not in catalog]
    if unknown:
        raise HTTPException(400, f"Unknown discovered_id: {unknown[0]}")

    imported: list[Device] = []
    skipped: list[dict[str, Any]] = []
    for item_id in selected_ids:
        item = catalog[item_id]
        entity_ids = [entity["entity_id"] for entity in item["entities"]]
        existing = (await db.execute(select(Entity.entity_id).where(Entity.entity_id.in_(entity_ids)).limit(1))).scalar_one_or_none()
        if existing is not None:
            skipped.append({"discovered_id": item_id, "reason": "already_imported", "entity_id": existing})
            continue

        device = Device(
            home_id=integration.home_id,
            integration_id=integration.id,
            name=item["name"],
            type=item["type"],
            manufacturer=item.get("manufacturer"),
            model=item.get("model"),
            status="online",
        )
        db.add(device)
        await db.flush()
        now = utcnow()
        for entity_spec in item["entities"]:
            entity = Entity(
                entity_id=entity_spec["entity_id"],
                device_id=device.id,
                area_id=device.area_id,
                domain=entity_spec["domain"],
                platform=integration.domain,
                name=entity_spec["name"],
                original_name=entity_spec["name"],
                state=str(entity_spec["state"]),
                attributes_json=entity_spec.get("attributes") or {},
                unit_of_measurement=entity_spec.get("unit_of_measurement"),
                device_class=entity_spec.get("device_class"),
                created_at=now,
                updated_at=now,
            )
            db.add(entity)
            db.add(
                EntityState(
                    entity_id=entity.entity_id,
                    state=entity.state,
                    attributes_json=entity.attributes_json,
                    last_changed=now,
                    last_updated=now,
                    created_at=now,
                )
            )
        imported.append(device)
    await db.commit()
    return {"imported": imported, "skipped": skipped}


async def set_entity_state(
    db: AsyncSession,
    entity: Entity,
    state: str,
    attributes: dict[str, Any] | None = None,
    *,
    source: str = "user",
    user_id: uuid.UUID | None = None,
    automation_id: uuid.UUID | None = None,
    publish: bool = True,
) -> Entity:
    old_state = entity.state
    now = utcnow()
    merged_attributes = dict(entity.attributes_json or {})
    if attributes:
        merged_attributes.update(attributes)
    entity.state = str(state)
    entity.attributes_json = merged_attributes
    entity.updated_at = now
    db.add(EntityState(entity_id=entity.entity_id, state=entity.state, attributes_json=merged_attributes, last_changed=now, last_updated=now))
    db.add(
        Event(
            entity_id=entity.entity_id,
            event_type="state_changed",
            old_state=old_state,
            new_state=entity.state,
            source=source,
            user_id=user_id,
            automation_id=automation_id,
            metadata_json={"attributes": merged_attributes},
            created_at=now,
        )
    )
    await db.flush()
    event = DomainEvent(
        type="state_changed",
        entity_id=entity.entity_id,
        old_state=old_state,
        new_state=entity.state,
        attributes=merged_attributes,
        source=source,
        timestamp=now,
        user_id=user_id,
        automation_id=automation_id,
    )
    if publish:
        await event_bus.publish(event)
    if source != "automation":
        await evaluate_automations(db, event)
    return entity


async def call_action(
    db: AsyncSession,
    domain: str,
    action: str,
    target: dict[str, Any],
    data: dict[str, Any] | None = None,
    *,
    source: str = "user",
    user_id: uuid.UUID | None = None,
    automation_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    entity_id = target.get("entity_id")
    if not entity_id:
        raise HTTPException(400, "target.entity_id is required")
    entity = await get_entity_or_404(db, entity_id)
    data = data or {}

    if domain in {"sensor", "energy_meter"} or entity.domain == "sensor" and action not in {"read"}:
        raise HTTPException(400, "Entity is read-only")
    if domain != entity.domain and not (domain == "energy_meter" and entity.device_class in {"power", "energy"}):
        raise HTTPException(400, "Domain does not match entity")

    if domain in {"light", "switch"}:
        if action == "turn_on":
            new_state = "on"
        elif action == "turn_off":
            new_state = "off"
        elif action == "toggle":
            new_state = "off" if entity.state == "on" else "on"
        else:
            raise HTTPException(400, "Unsupported action")
        attrs = {"brightness": data["brightness"]} if domain == "light" and "brightness" in data else {}
    elif domain == "climate":
        attrs = {}
        new_state = entity.state
        if action == "set_temperature":
            if "temperature" not in data:
                raise HTTPException(400, "temperature is required")
            attrs["target_temperature"] = data["temperature"]
        elif action == "set_mode":
            mode = data.get("hvac_mode") or data.get("mode")
            if mode not in {"heat", "cool", "off"}:
                raise HTTPException(400, "hvac_mode must be heat, cool, or off")
            attrs["hvac_mode"] = mode
            new_state = mode
        else:
            raise HTTPException(400, "Unsupported action")
    else:
        raise HTTPException(400, "Unsupported domain")

    await set_entity_state(db, entity, new_state, attrs, source=source, user_id=user_id, automation_id=automation_id)
    await db.commit()
    await db.refresh(entity)
    return {"ok": True, "entity_id": entity.entity_id, "new_state": entity.state, "attributes": entity.attributes_json or {}}


def condition_matches(entity: Entity | None, condition: dict[str, Any] | None) -> bool:
    if not condition:
        return True
    if entity is None:
        return False
    op = condition.get("operator", "eq")
    expected = condition.get("value")
    actual: Any = entity.state
    try:
        actual_num = float(actual)
        expected_num = float(expected)
    except (TypeError, ValueError):
        actual_num = expected_num = None
    if op == "eq":
        return str(actual) == str(expected)
    if op == "ne":
        return str(actual) != str(expected)
    if op == "lt":
        return actual_num is not None and expected_num is not None and actual_num < expected_num
    if op == "gt":
        return actual_num is not None and expected_num is not None and actual_num > expected_num
    return False


async def evaluate_automations(db: AsyncSession, event: DomainEvent) -> None:
    automations = (
        await db.execute(select(Automation).where(Automation.is_enabled.is_(True), Automation.trigger_json["type"].astext == "state_changed"))
    ).scalars()
    for automation in automations:
        trigger = automation.trigger_json or {}
        if trigger.get("entity_id") != event.entity_id:
            continue
        if trigger.get("to") is not None and str(trigger["to"]) != str(event.new_state):
            continue
        condition = automation.condition_json
        condition_entity = None
        if condition and condition.get("entity_id"):
            condition_entity = (await db.execute(select(Entity).where(Entity.entity_id == condition["entity_id"]))).scalar_one_or_none()
        if not condition_matches(condition_entity, condition):
            continue
        await run_automation(db, automation, triggered_by=f"state_changed:{event.entity_id}")


async def run_automation(db: AsyncSession, automation: Automation, triggered_by: str = "manual") -> AutomationRun:
    started = utcnow()
    run = AutomationRun(automation_id=automation.id, triggered_by=triggered_by, status="running", started_at=started)
    db.add(run)
    await db.flush()
    try:
        action = automation.action_json or {}
        await call_action(
            db,
            action.get("domain"),
            action.get("action"),
            action.get("target") or {"entity_id": action.get("target_entity_id")},
            action.get("data") or {},
            source="automation",
            automation_id=automation.id,
        )
        run.status = "completed"
        run.finished_at = utcnow()
        automation.last_triggered = started
        db.add(
            Event(
                event_type="automation_triggered",
                source="automation",
                automation_id=automation.id,
                metadata_json={"triggered_by": triggered_by},
                created_at=started,
            )
        )
        await event_bus.publish(DomainEvent(type="automation_triggered", automation_id=automation.id, timestamp=started, metadata={"triggered_by": triggered_by}))
    except Exception:
        run.status = "failed"
        run.finished_at = utcnow()
        raise
    finally:
        await db.flush()
    return run


def period_start(period: str) -> datetime:
    now = datetime.now(UTC)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def energy_summary(db: AsyncSession, period: str = "day") -> dict[str, Any]:
    home = await get_default_home(db)
    start = period_start(period)
    end = datetime.now(UTC)
    total = (await db.execute(select(func.coalesce(func.sum(EnergyReading.energy_kwh), 0)).where(EnergyReading.recorded_at >= start))).scalar_one()
    current_power = (await db.execute(select(func.coalesce(func.sum(EnergyReading.power_w), 0)).where(EnergyReading.recorded_at >= end - timedelta(hours=1)))).scalar_one()
    peak = (await db.execute(select(func.coalesce(func.max(EnergyReading.power_w), 0)).where(EnergyReading.recorded_at >= start))).scalar_one()
    device_count = (await db.execute(select(func.count(Device.id)))).scalar_one()
    return {
        "period": period,
        "total_kwh": round(float(total), 3),
        "total_cost": round(float(total) * 18.0, 2),
        "currency": home.currency,
        "current_power_w": round(float(current_power), 2),
        "peak_power_w": round(float(peak), 2),
        "device_count": device_count,
        "date_from": start,
        "date_to": end,
    }


async def delete_by_id(db: AsyncSession, model: type[Any], item_id: uuid.UUID) -> None:
    result = await db.execute(delete(model).where(model.id == item_id))
    if result.rowcount == 0:
        raise HTTPException(404, "Resource not found")
    await db.commit()
