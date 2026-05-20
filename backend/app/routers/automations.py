from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from app.models import Automation
from app.routers.deps import CurrentUser, Db
from app.schemas import AutomationCreate, AutomationUpdate
from app.serializers import automation_out
from app.services import delete_by_id, get_default_home, run_automation

router = APIRouter()


@router.get("/automations")
async def list_automations(_: CurrentUser, db: Db) -> list[dict[str, Any]]:
    rows = (await db.execute(select(Automation).order_by(Automation.created_at))).scalars().all()
    return [automation_out(row) for row in rows]


@router.post("/automations", status_code=201)
async def create_automation(payload: AutomationCreate, _: CurrentUser, db: Db) -> dict[str, Any]:
    home = await get_default_home(db)
    automation = Automation(
        home_id=home.id,
        trigger_json=payload.trigger,
        condition_json=payload.condition,
        action_json=payload.action,
        **payload.model_dump(exclude={"trigger", "condition", "action"}),
    )
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation_out(automation)


@router.get("/automations/{automation_id}")
async def get_automation(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(404, "Automation not found")
    return automation_out(automation)


@router.patch("/automations/{automation_id}")
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


@router.delete("/automations/{automation_id}", status_code=204)
async def delete_automation(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> Response:
    await delete_by_id(db, Automation, automation_id)
    return Response(status_code=204)


@router.post("/automations/{automation_id}/run")
async def run_automation_endpoint(automation_id: uuid.UUID, _: CurrentUser, db: Db) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(404, "Automation not found")
    run = await run_automation(db, automation, triggered_by="manual")
    await db.commit()
    return {"ok": True, "run_id": str(run.id), "automation_id": str(automation.id), "triggered_at": run.started_at}
