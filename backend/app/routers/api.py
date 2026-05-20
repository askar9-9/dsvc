from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.routers import actions, areas, auth, automations, dashboard, devices, energy, entities, events, homes, integrations, ml

api = APIRouter(prefix="/api")


@api.get("/health", include_in_schema=False)
async def health() -> dict[str, Any]:
    return {"ok": True, "service": "smart-home-backend"}


api.include_router(auth.router)
api.include_router(homes.router)
api.include_router(integrations.router)
api.include_router(areas.router)
api.include_router(devices.router)
api.include_router(entities.router)
api.include_router(actions.router)
api.include_router(events.router)
api.include_router(automations.router)
api.include_router(energy.router)
api.include_router(ml.router)
api.include_router(dashboard.router)
