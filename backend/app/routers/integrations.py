from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Device, Integration
from app.routers.deps import CurrentUser, Db
from app.schemas import IntegrationCreate, IntegrationImport, IntegrationUpdate
from app.serializers import device_out, integration_out
from app.services import delete_by_id, discovery_preview, get_default_home, get_integration_or_404, import_discovered_devices, supported_integration_domain

router = APIRouter()


@router.get("/integrations")
async def list_integrations(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    integrations = (await db.execute(select(Integration).order_by(Integration.created_at))).scalars().all()
    return [await integration_out(db, integration) for integration in integrations]


@router.post("/integrations", status_code=201)
async def create_integration(payload: IntegrationCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    if not supported_integration_domain(payload.domain):
        raise HTTPException(400, "Unsupported integration domain")
    home = await get_default_home(db)
    integration = Integration(home_id=home.id, name=payload.name, domain=payload.domain, config_json=payload.config)
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return await integration_out(db, integration)


@router.get("/integrations/{integration_id}")
async def get_integration(integration_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    integration = await get_integration_or_404(db, integration_id)
    return await integration_out(db, integration)


@router.patch("/integrations/{integration_id}")
async def update_integration(integration_id: uuid.UUID, payload: IntegrationUpdate, _: CurrentUser, db: Db) -> dict[str, Any]:
    integration = await get_integration_or_404(db, integration_id)
    if payload.name is not None:
        integration.name = payload.name
    if payload.config is not None:
        integration.config_json = payload.config
    await db.commit()
    await db.refresh(integration)
    return await integration_out(db, integration)


@router.delete("/integrations/{integration_id}", status_code=204)
async def delete_integration(integration_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Integration, integration_id)
    return Response(status_code=204)


@router.get("/integrations/{integration_id}/discovery")
async def discover_integration_devices(integration_id: uuid.UUID, _: CurrentUser, db: Db) -> list[dict[str, Any]]:
    integration = await get_integration_or_404(db, integration_id)
    return await discovery_preview(db, integration)


@router.post("/integrations/{integration_id}/import")
async def import_integration_devices(integration_id: uuid.UUID, payload: IntegrationImport, _: CurrentUser, db: Db) -> dict[str, Any]:
    integration = await get_integration_or_404(db, integration_id)
    result = await import_discovered_devices(db, integration, payload.discovered_ids)
    imported_ids = [device.id for device in result["imported"]]
    imported_devices = []
    if imported_ids:
        rows = (
            await db.execute(select(Device).options(selectinload(Device.area), selectinload(Device.entities)).where(Device.id.in_(imported_ids)).order_by(Device.created_at))
        ).scalars()
        imported_devices = [device_out(device, detailed=True) for device in rows]
    return {
        "integration_id": str(integration.id),
        "imported": len(imported_devices),
        "skipped": result["skipped"],
        "devices": imported_devices,
    }
