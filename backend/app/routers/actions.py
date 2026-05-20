from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.routers.deps import CurrentUser, Db
from app.schemas import ActionCall
from app.services import call_action

router = APIRouter()


@router.post("/actions/call")
async def actions_call(payload: ActionCall, user: CurrentUser, db: Db) -> dict[str, Any]:
    return await call_action(db, payload.domain, payload.action, payload.target, payload.data, source="user", user_id=user.id)
