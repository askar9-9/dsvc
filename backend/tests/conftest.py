from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://smart_home:smart_home@127.0.0.1:5432/smart_home")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, engine, get_db
from app.main import app
from app.models import Base
from app.seed import seed_database


async def _reset_database() -> None:
    try:
        await engine.dispose()
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        message = str(exc)
        unavailable = (
            "Connect call failed" in message
            or "Connection refused" in message
            or "Operation not permitted" in message
            or 'role "smart_home" does not exist' in message
        )
        if unavailable:
            pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
        raise

    async with SessionLocal() as db:
        await seed_database(db)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[None]:
    await _reset_database()
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(database: None) -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db


@pytest_asyncio.fixture
async def client(database: None) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with SessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    response = await client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass123"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
