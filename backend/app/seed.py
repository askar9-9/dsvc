from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Area, Automation, Device, EnergyReading, Entity, EntityState, Event, Home, Integration, User, utcnow


EXPECTED_SEED_COUNTS = {
    "users": 1,
    "homes": 1,
    "integrations": 1,
    "areas": 4,
    "devices": 12,
    "entities": 15,
    "automations": 5,
    "entity_states": 15,
    "energy_readings": 336,
    "events": 60,
}


async def seed_counts(db: AsyncSession) -> dict[str, int]:
    models = {
        "users": User,
        "homes": Home,
        "integrations": Integration,
        "areas": Area,
        "devices": Device,
        "entities": Entity,
        "automations": Automation,
        "entity_states": EntityState,
        "energy_readings": EnergyReading,
        "events": Event,
    }
    counts: dict[str, int] = {}
    for name, model in models.items():
        counts[name] = (await db.execute(select(func.count()).select_from(model))).scalar_one()
    return counts


async def seed_database(db: AsyncSession) -> None:
    existing = (await db.execute(select(User).where(User.username == "testadmin"))).scalar_one_or_none()
    if existing is not None:
        return

    now = datetime.now(UTC)
    user = User(name="Test Admin", username="testadmin", password_hash=hash_password("testpass123"), is_admin=True)
    home = Home(
        name="Smart Home",
        latitude=43.238949,
        longitude=76.889709,
        elevation=700,
        time_zone="Asia/Almaty",
        currency="KZT",
        unit_system={"temperature": "C", "length": "metric"},
    )
    db.add_all([user, home])
    await db.flush()

    integration = Integration(home_id=home.id, name="Demo Integration", domain="demo", config_json={"mock": True})
    db.add(integration)
    await db.flush()

    areas = {
        "living": Area(home_id=home.id, name="Гостиная", icon="mdi:sofa"),
        "kitchen": Area(home_id=home.id, name="Кухня", icon="mdi:stove"),
        "bedroom": Area(home_id=home.id, name="Спальня", icon="mdi:bed"),
        "hallway": Area(home_id=home.id, name="Коридор", icon="mdi:door"),
    }
    db.add_all(areas.values())
    await db.flush()

    device_specs = [
        ("Living Room Ceiling", "light", "living", "Philips", "Hue A19"),
        ("Living Room Floor Lamp", "light", "living", "IKEA", "Tradfri"),
        ("Bedroom Light", "light", "bedroom", "Philips", "Hue E27"),
        ("Hallway Light", "light", "hallway", "Aqara", "Ceiling T1"),
        ("Kitchen Outlet", "switch", "kitchen", "Sonoff", "S31"),
        ("Hallway Outlet", "switch", "hallway", "Aqara", "Plug"),
        ("Living Room Temperature", "sensor", "living", "Aqara", "Temp"),
        ("Kitchen Humidity", "sensor", "kitchen", "Aqara", "Humidity"),
        ("Bedroom Climate", "climate", "bedroom", "Midea", "AC"),
        ("Main Energy Meter", "energy_meter", "hallway", "Shelly", "Pro 3EM"),
        ("Hallway Motion", "sensor", "hallway", "Aqara", "Motion"),
        ("Hallway Lux", "sensor", "hallway", "Aqara", "Illuminance"),
    ]
    devices: list[Device] = []
    for name, type_, area_key, manufacturer, model in device_specs:
        device = Device(
            home_id=home.id,
            area_id=areas[area_key].id,
            integration_id=integration.id,
            name=name,
            type=type_,
            manufacturer=manufacturer,
            model=model,
            status="online",
        )
        db.add(device)
        devices.append(device)
    await db.flush()

    entities: list[Entity] = []

    def add_entity(device: Device, entity_id: str, domain: str, name: str, state: str, attrs: dict[str, Any] | None = None, unit: str | None = None, device_class: str | None = None) -> Entity:
        entity = Entity(
            entity_id=entity_id,
            device_id=device.id,
            area_id=device.area_id,
            domain=domain,
            platform="demo",
            name=name,
            original_name=name,
            state=state,
            attributes_json=attrs or {},
            unit_of_measurement=unit,
            device_class=device_class,
        )
        db.add(entity)
        entities.append(entity)
        return entity

    add_entity(devices[0], "light.living_room_ceiling", "light", "Living Room Ceiling", "off", {"brightness": 0})
    add_entity(devices[1], "light.living_room_floor_lamp", "light", "Living Room Floor Lamp", "on", {"brightness": 55})
    add_entity(devices[2], "light.bedroom_light", "light", "Bedroom Light", "off", {"brightness": 0})
    add_entity(devices[3], "light.hallway", "light", "Hallway Light", "off", {"brightness": 0})
    add_entity(devices[4], "switch.kitchen_outlet", "switch", "Kitchen Outlet", "off")
    add_entity(devices[5], "switch.hallway_outlet", "switch", "Hallway Outlet", "off")
    add_entity(devices[6], "sensor.living_room_temperature", "sensor", "Living Room Temperature", "22.5", {"friendly_name": "LR Temperature"}, "°C", "temperature")
    add_entity(devices[6], "sensor.living_room_battery", "sensor", "Living Room Sensor Battery", "88", {}, "%", "battery")
    add_entity(devices[7], "sensor.kitchen_humidity", "sensor", "Kitchen Humidity", "45", {}, "%", "humidity")
    add_entity(devices[7], "sensor.kitchen_temperature", "sensor", "Kitchen Temperature", "23.1", {}, "°C", "temperature")
    add_entity(devices[8], "climate.bedroom", "climate", "Bedroom Climate", "heat", {"current_temperature": 21, "target_temperature": 22, "hvac_mode": "heat"}, None, "temperature")
    add_entity(devices[9], "sensor.main_energy_power", "sensor", "Main Energy Power", "650", {"energy_meter": True}, "W", "power")
    add_entity(devices[9], "sensor.main_energy_total", "sensor", "Main Energy Total", "1245.2", {"state_class": "total_increasing"}, "kWh", "energy")
    add_entity(devices[10], "binary_sensor.hallway_motion", "binary_sensor", "Hallway Motion", "off", {"device_class": "motion"}, None, "motion")
    add_entity(devices[11], "sensor.hallway_lux", "sensor", "Hallway Lux", "15", {}, "lx", "illuminance")
    await db.flush()

    areas["living"].temperature_entity_id = "sensor.living_room_temperature"
    areas["kitchen"].temperature_entity_id = "sensor.kitchen_temperature"
    areas["kitchen"].humidity_entity_id = "sensor.kitchen_humidity"

    automations = [
        Automation(
            home_id=home.id,
            name="Свет в коридоре при движении",
            description="Включает свет при движении и низкой освещенности",
            trigger_json={"type": "state_changed", "entity_id": "binary_sensor.hallway_motion", "to": "on"},
            condition_json={"entity_id": "sensor.hallway_lux", "operator": "lt", "value": 30},
            action_json={"domain": "light", "action": "turn_on", "target": {"entity_id": "light.hallway"}, "data": {"brightness": 80}},
        ),
        Automation(
            home_id=home.id,
            name="Выключить всё при уходе",
            trigger_json={"type": "state_changed", "entity_id": "switch.hallway_outlet", "to": "off"},
            condition_json=None,
            action_json={"domain": "light", "action": "turn_off", "target": {"entity_id": "light.living_room_ceiling"}},
        ),
        Automation(
            home_id=home.id,
            name="Климат по расписанию",
            trigger_json={"type": "state_changed", "entity_id": "sensor.living_room_temperature", "to": "20"},
            condition_json=None,
            action_json={"domain": "climate", "action": "set_temperature", "target": {"entity_id": "climate.bedroom"}, "data": {"temperature": 23}},
        ),
        Automation(
            home_id=home.id,
            name="Предупреждение высокого потребления",
            trigger_json={"type": "state_changed", "entity_id": "sensor.main_energy_power", "to": "2000"},
            condition_json={"entity_id": "sensor.main_energy_power", "operator": "gt", "value": 1400},
            action_json={"domain": "switch", "action": "turn_off", "target": {"entity_id": "switch.kitchen_outlet"}},
        ),
        Automation(
            home_id=home.id,
            name="Свет сцена Вечер",
            trigger_json={"type": "state_changed", "entity_id": "switch.kitchen_outlet", "to": "on"},
            condition_json=None,
            action_json={"domain": "light", "action": "turn_on", "target": {"entity_id": "light.living_room_floor_lamp"}, "data": {"brightness": 35}},
        ),
    ]
    db.add_all(automations)

    for entity in entities:
        db.add(EntityState(entity_id=entity.entity_id, state=entity.state, attributes_json=entity.attributes_json, last_changed=now, last_updated=now))

    energy_entities = ["sensor.main_energy_power", "sensor.main_energy_total"]
    rng = random.Random(42)
    for hour in range(7 * 24):
        recorded_at = now - timedelta(hours=7 * 24 - hour)
        daily_curve = 0.6 + 0.4 * math.sin((recorded_at.hour - 8) / 24 * math.tau)
        power = max(120, 650 + daily_curve * 450 + rng.randint(-80, 120))
        for entity_id in energy_entities:
            db.add(EnergyReading(entity_id=entity_id, power_w=power if entity_id.endswith("_power") else power * 0.08, energy_kwh=round(power / 1000, 3), recorded_at=recorded_at))

    event_entities = [entity.entity_id for entity in entities]
    for index in range(60):
        entity_id = event_entities[index % len(event_entities)]
        db.add(
            Event(
                entity_id=entity_id,
                event_type="state_changed",
                old_state="off" if index % 2 else "on",
                new_state="on" if index % 2 else "off",
                source="system",
                metadata_json={"seed": True},
                created_at=now - timedelta(minutes=60 - index),
            )
        )

    await db.commit()
