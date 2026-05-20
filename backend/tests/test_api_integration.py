from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Area, AutomationRun, Entity, EntityState, Event
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
