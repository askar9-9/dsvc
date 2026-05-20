from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.core.errors import install_error_handlers
from app.database import SessionLocal
from app.models import Entity
from app.routers.api import api
from app.seed import seed_database
from app.services import set_entity_state


async def simulator() -> None:
    rng = random.Random()
    while True:
        await asyncio.sleep(30)
        async with SessionLocal() as db:
            rows = (
                await db.execute(
                    select(Entity).where(
                        Entity.entity_id.in_(
                            ["sensor.living_room_temperature", "sensor.kitchen_temperature", "sensor.kitchen_humidity", "sensor.main_energy_power"]
                        )
                    )
                )
            ).scalars()
            for entity in rows:
                if entity.device_class == "temperature":
                    value = round(20 + rng.random() * 5, 1)
                elif entity.device_class == "humidity":
                    value = round(35 + rng.random() * 20, 1)
                elif entity.device_class == "power":
                    value = round(500 + rng.random() * 700, 1)
                else:
                    continue
                await set_entity_state(db, entity, str(value), {}, source="system")
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with SessionLocal() as db:
        if settings.seed_enabled:
            await seed_database(db)
    sim_task = asyncio.create_task(simulator()) if settings.sim_enabled else None
    try:
        yield
    finally:
        if sim_task:
            sim_task.cancel()


app = FastAPI(title="Smart Home MVP", docs_url="/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else [item.strip() for item in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
install_error_handlers(app)
app.include_router(api)
