from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.eventbus import DomainEvent, event_bus
from app.models import Area, AutomationRun, Device, Entity, EntityState, Event, Integration
from app.seed import EXPECTED_SEED_COUNTS, seed_counts, seed_database

pytestmark = pytest.mark.asyncio


async def test_seed_counts_and_idempotency(db_session: AsyncSession) -> None:
    assert await seed_counts(db_session) == EXPECTED_SEED_COUNTS

    await seed_database(db_session)

    assert await seed_counts(db_session) == EXPECTED_SEED_COUNTS


async def test_auth_required(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized", "message": "Not authenticated"}


async def test_login_success_and_failure(client: AsyncClient) -> None:
    success = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass123"})
    failure = await client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})

    assert success.status_code == 200
    body = success.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["username"] == "testadmin"
    assert failure.status_code == 401


async def test_events_stream_accepts_query_token(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    login = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass123"})
    token = login.json()["access_token"]

    missing = await client.get("/api/events/stream")
    invalid = await client.get("/api/events/stream", params={"token": "not-a-token"})

    async def one_event():
        yield DomainEvent(type="state_changed", entity_id="light.hallway", new_state="on")

    monkeypatch.setattr(event_bus, "stream", one_event)
    valid = await client.get("/api/events/stream", params={"token": token})

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert "light.hallway" in valid.text


async def test_dashboard_shape(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["home"]["name"] == "Smart Home"
    assert len(body["areas"]) == EXPECTED_SEED_COUNTS["areas"]
    assert body["summary"]["devices_total"] == EXPECTED_SEED_COUNTS["devices"]
    assert body["summary"]["devices_online"] == EXPECTED_SEED_COUNTS["devices"]
    assert body["summary"]["automations_active"] == EXPECTED_SEED_COUNTS["automations"]
    assert {"devices_total", "devices_online", "automations_active", "energy_today_kwh", "current_power_w"} == set(body["summary"])
    assert isinstance(body["recent_events"], list)


async def test_areas_crud(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/areas", json={"name": "Office", "icon": "mdi:desk"})
    assert created.status_code == 201
    area = created.json()
    assert area["name"] == "Office"
    assert area["device_count"] == 0

    listed = await auth_client.get("/api/areas")
    assert listed.status_code == 200
    assert any(item["id"] == area["id"] for item in listed.json())

    updated = await auth_client.patch(f"/api/areas/{area['id']}", json={"name": "Study"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Study"

    deleted = await auth_client.delete(f"/api/areas/{area['id']}")
    assert deleted.status_code == 204


async def test_devices_crud(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    area = (await db_session.execute(select(Area).where(Area.name == "Коридор"))).scalar_one()
    created = await auth_client.post(
        "/api/devices",
        json={"name": "Desk Lamp", "type": "light", "area_id": str(area.id), "manufacturer": "Demo"},
    )
    assert created.status_code == 201
    device = created.json()
    assert device["name"] == "Desk Lamp"
    assert device["area_id"] == str(area.id)
    assert device["entity_count"] == 1
    assert device["entities"][0]["entity_id"] == "light.desk_lamp"

    listed = await auth_client.get("/api/devices", params={"type": "light", "status": "online"})
    assert listed.status_code == 200
    assert any(item["id"] == device["id"] for item in listed.json())

    updated = await auth_client.patch(f"/api/devices/{device['id']}", json={"name_by_user": "Work Lamp"})
    assert updated.status_code == 200
    assert updated.json()["name_by_user"] == "Work Lamp"

    deleted = await auth_client.delete(f"/api/devices/{device['id']}")
    assert deleted.status_code == 204


async def test_integrations_auth_required(client: AsyncClient) -> None:
    response = await client.get("/api/integrations")

    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized", "message": "Not authenticated"}


async def test_integrations_crud_contract(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/integrations", json={"name": "Pairing Hub", "domain": "demo", "config": {"room": "lab"}})

    assert created.status_code == 201
    integration = created.json()
    assert integration["name"] == "Pairing Hub"
    assert integration["domain"] == "demo"
    assert integration["config"] == {"room": "lab"}
    assert integration["device_count"] == 0
    assert "T" in integration["created_at"]

    listed = await auth_client.get("/api/integrations")
    assert listed.status_code == 200
    assert any(item["id"] == integration["id"] for item in listed.json())

    fetched = await auth_client.get(f"/api/integrations/{integration['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == integration["id"]

    updated = await auth_client.patch(f"/api/integrations/{integration['id']}", json={"name": "Updated Hub", "config": {"room": "office"}})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Hub"
    assert updated.json()["config"] == {"room": "office"}

    deleted = await auth_client.delete(f"/api/integrations/{integration['id']}")
    assert deleted.status_code == 204


async def test_integration_discovery_and_idempotent_import(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    created = await auth_client.post("/api/integrations", json={"name": "Discovery Hub", "domain": "demo"})
    integration = created.json()

    discovery = await auth_client.get(f"/api/integrations/{integration['id']}/discovery")
    assert discovery.status_code == 200
    discovered = discovery.json()
    assert len(discovered) == 5
    assert discovered[0]["discovered_id"] == "demo.porch_light"
    assert discovered[0]["suggested_entity_id"] == "light.porch_light"
    assert all(item["already_imported"] is False for item in discovered)

    imported = await auth_client.post(f"/api/integrations/{integration['id']}/import", json={})
    assert imported.status_code == 200
    import_body = imported.json()
    assert import_body["integration_id"] == integration["id"]
    assert import_body["imported"] == 5
    assert import_body["skipped"] == []
    assert len(import_body["devices"]) == 5
    assert import_body["devices"][0]["entities"]

    linked_devices = (
        await db_session.execute(select(func.count(Device.id)).where(Device.integration_id == integration["id"]))
    ).scalar_one()
    imported_states = (
        await db_session.execute(select(func.count(EntityState.id)).where(EntityState.entity_id.in_(["light.porch_light", "sensor.solar_meter_total"])))
    ).scalar_one()
    assert linked_devices == 5
    assert imported_states == 2

    repeated = await auth_client.post(f"/api/integrations/{integration['id']}/import", json={})
    assert repeated.status_code == 200
    repeat_body = repeated.json()
    assert repeat_body["imported"] == 0
    assert len(repeat_body["skipped"]) == 5

    rediscovery = await auth_client.get(f"/api/integrations/{integration['id']}/discovery")
    assert all(item["already_imported"] is True for item in rediscovery.json())


async def test_mqtt_integration_discovery_import_and_actions(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    created = await auth_client.post("/api/integrations", json={"name": "MQTT Broker", "domain": "mqtt", "config": {"host": "mock-broker"}})
    assert created.status_code == 201
    integration = created.json()
    assert integration["domain"] == "mqtt"

    discovery = await auth_client.get(f"/api/integrations/{integration['id']}/discovery")
    assert discovery.status_code == 200
    discovered = discovery.json()
    assert [item["discovered_id"] for item in discovered] == [
        "mqtt.living_room_strip",
        "mqtt.garage_relay",
        "mqtt.office_sensor",
    ]
    strip = discovered[0]["entities"][0]
    assert strip["entity_id"] == "light.mqtt_living_room_strip"
    assert strip["platform"] == "mqtt"
    assert strip["attributes"]["command_topic"] == "home/living_room/strip/set"
    assert strip["attributes"]["brightness_state_topic"] == "home/living_room/strip/brightness/state"
    sensor_entities = discovered[2]["entities"]
    assert sensor_entities[0]["attributes"]["state_topic"] == "home/office/sensor/temperature"
    assert sensor_entities[1]["device_class"] == "humidity"

    imported = await auth_client.post(
        f"/api/integrations/{integration['id']}/import",
        json={"discovered_ids": ["mqtt.living_room_strip", "mqtt.garage_relay"]},
    )
    assert imported.status_code == 200
    import_body = imported.json()
    assert import_body["imported"] == 2
    assert import_body["skipped"] == []

    linked_devices = (
        await db_session.execute(select(func.count(Device.id)).where(Device.integration_id == integration["id"]))
    ).scalar_one()
    linked_entities = (
        await db_session.execute(
            select(Entity).where(Entity.entity_id.in_(["light.mqtt_living_room_strip", "switch.mqtt_garage_relay"])).order_by(Entity.entity_id)
        )
    ).scalars().all()
    initial_states = (
        await db_session.execute(
            select(func.count(EntityState.id)).where(EntityState.entity_id.in_(["light.mqtt_living_room_strip", "switch.mqtt_garage_relay"]))
        )
    ).scalar_one()
    assert linked_devices == 2
    assert [entity.platform for entity in linked_entities] == ["mqtt", "mqtt"]
    assert linked_entities[0].attributes_json["state_topic"] == "home/living_room/strip/state"
    assert initial_states == 2

    light_action = await auth_client.post(
        "/api/actions/call",
        json={
            "domain": "light",
            "action": "turn_on",
            "target": {"entity_id": "light.mqtt_living_room_strip"},
            "data": {"brightness": 55},
        },
    )
    assert light_action.status_code == 200
    assert light_action.json()["new_state"] == "on"
    assert light_action.json()["attributes"]["brightness"] == 55
    assert light_action.json()["attributes"]["command_topic"] == "home/living_room/strip/set"

    switch_action = await auth_client.post(
        "/api/actions/call",
        json={"domain": "switch", "action": "turn_on", "target": {"entity_id": "switch.mqtt_garage_relay"}},
    )
    assert switch_action.status_code == 200
    assert switch_action.json()["new_state"] == "on"

    repeated = await auth_client.post(
        f"/api/integrations/{integration['id']}/import",
        json={"discovered_ids": ["mqtt.living_room_strip", "mqtt.garage_relay"]},
    )
    assert repeated.status_code == 200
    repeat_body = repeated.json()
    assert repeat_body["imported"] == 0
    assert len(repeat_body["skipped"]) == 2
    assert {item["reason"] for item in repeat_body["skipped"]} == {"already_imported"}


async def test_integration_import_validation_errors(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    unsupported = await auth_client.post("/api/integrations", json={"name": "Zigbee", "domain": "zigbee"})
    assert unsupported.status_code == 400
    assert unsupported.json() == {"error": "bad_request", "message": "Unsupported integration domain"}

    integration = (await db_session.execute(select(Integration).where(Integration.domain == "demo").limit(1))).scalar_one()
    unknown = await auth_client.post(f"/api/integrations/{integration.id}/import", json={"discovered_ids": ["demo.missing"]})
    assert unknown.status_code == 400
    assert unknown.json() == {"error": "bad_request", "message": "Unknown discovered_id: demo.missing"}


async def test_contract_nullable_fields_and_date_serialization(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/devices", json={"name": "Loose Sensor", "type": "sensor"})

    assert created.status_code == 201
    device = created.json()
    assert device["area_id"] is None
    assert device["area_name"] is None
    assert device["manufacturer"] is None
    assert device["model"] is None
    assert device["name_by_user"] is None
    assert "T" in device["created_at"]

    entity = device["entities"][0]
    assert entity["area_id"] is None
    assert entity["unit_of_measurement"] == ""
    assert entity["device_class"] is None
    assert "T" in entity["last_changed"]


async def test_action_call_writes_state_history_and_event(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    response = await auth_client.post(
        "/api/actions/call",
        json={"domain": "light", "action": "turn_on", "target": {"entity_id": "light.bedroom_light"}, "data": {"brightness": 70}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["new_state"] == "on"
    assert body["attributes"]["brightness"] == 70

    states = (
        await db_session.execute(select(func.count(EntityState.id)).where(EntityState.entity_id == "light.bedroom_light", EntityState.state == "on"))
    ).scalar_one()
    event = (
        await db_session.execute(
            select(Event).where(Event.entity_id == "light.bedroom_light", Event.new_state == "on", Event.source == "user").order_by(Event.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    assert states >= 1
    assert event is not None


async def test_motion_trigger_runs_hallway_automation(auth_client: AsyncClient, db_session: AsyncSession) -> None:
    response = await auth_client.patch("/api/entities/binary_sensor.hallway_motion/state", json={"state": "on"})

    assert response.status_code == 200
    hallway = (await db_session.execute(select(Entity).where(Entity.entity_id == "light.hallway"))).scalar_one()
    run_count = (await db_session.execute(select(func.count(AutomationRun.id)))).scalar_one()
    automation_event = (
        await db_session.execute(
            select(Event).where(Event.event_type == "automation_triggered", Event.source == "automation").order_by(Event.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    state_event = (
        await db_session.execute(
            select(Event).where(Event.entity_id == "light.hallway", Event.source == "automation", Event.new_state == "on").order_by(Event.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()

    assert hallway.state == "on"
    assert hallway.attributes_json["brightness"] == 80
    assert run_count == 1
    assert automation_event is not None
    assert state_event is not None
    assert automation_event.metadata_json == {"triggered_by": "state_changed:binary_sensor.hallway_motion"}


async def test_events_contract_pagination_and_serialization(auth_client: AsyncClient) -> None:
    await auth_client.patch("/api/entities/light.bedroom_light/state", json={"state": "on"})
    await auth_client.patch("/api/entities/light.bedroom_light/state", json={"state": "off"})

    page = await auth_client.get("/api/events", params={"entity_id": "light.bedroom_light", "limit": 1, "offset": 1})
    clamped = await auth_client.get("/api/events", params={"limit": 999, "offset": -5})

    assert page.status_code == 200
    body = page.json()
    assert body["total"] >= 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert {"id", "entity_id", "event_type", "old_state", "new_state", "source", "user_id", "automation_id", "metadata", "created_at"} == set(event)
    assert "T" in event["created_at"]

    assert clamped.status_code == 200
    assert clamped.json()["limit"] == 200
    assert clamped.json()["offset"] == 0


async def test_energy_endpoints_return_expected_fields(auth_client: AsyncClient) -> None:
    summary = await auth_client.get("/api/energy/summary")
    consumption = await auth_client.get("/api/energy/consumption")
    devices = await auth_client.get("/api/energy/devices")
    forecast = await auth_client.get("/api/energy/forecast")

    assert summary.status_code == 200
    assert {"period", "total_kwh", "total_cost", "currency", "current_power_w", "peak_power_w", "device_count", "date_from", "date_to"} <= set(summary.json())
    assert consumption.status_code == 200
    assert {"period", "granularity", "data"} <= set(consumption.json())
    assert devices.status_code == 200
    assert {"entity_id", "device_name", "kwh", "current_power_w", "percentage", "anomaly"} <= set(devices.json()[0])
    assert forecast.status_code == 200
    assert {"period_hours", "forecast", "total_predicted_kwh", "confidence"} <= set(forecast.json())
