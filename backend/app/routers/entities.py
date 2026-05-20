from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.models import Entity, EntityState
from app.routers.deps import CurrentUser, Db
from app.schemas import EntityStatePatch
from app.serializers import entity_out
from app.services import get_entity_or_404, set_entity_state

router = APIRouter()


@router.get("/entities")
async def list_entities(_: CurrentUser, db: Db, domain: str | None = None, area_id: uuid.UUID | None = None, device_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    stmt = select(Entity).order_by(Entity.entity_id)
    if domain:
        stmt = stmt.where(Entity.domain == domain)
    if area_id:
        stmt = stmt.where(Entity.area_id == area_id)
    if device_id:
        stmt = stmt.where(Entity.device_id == device_id)
    return [entity_out(entity) for entity in (await db.execute(stmt)).scalars().all()]


@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str, _: CurrentUser, db: Db) -> dict[str, Any]:
    return entity_out(await get_entity_or_404(db, entity_id))


@router.patch("/entities/{entity_id}/state")
async def patch_entity_state(entity_id: str, payload: EntityStatePatch, user: CurrentUser, db: Db) -> dict[str, Any]:
    entity = await get_entity_or_404(db, entity_id)
    await set_entity_state(db, entity, payload.state, payload.attributes, source="user", user_id=user.id)
    await db.commit()
    return {"entity_id": entity.entity_id, "state": entity.state, "attributes": entity.attributes_json or {}, "last_changed": entity.updated_at}


@router.get("/entities/{entity_id}/history")
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
