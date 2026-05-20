from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token, verify_password
from app.models import User
from app.routers.deps import CurrentUser, Db
from app.schemas import LoginRequest
from app.serializers import user_out

router = APIRouter()


@router.post("/auth/login")
async def login(payload: LoginRequest, db: Db) -> dict[str, Any]:
    user = (await db.execute(select(User).where(User.username == payload.username))).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "expires_in": settings.jwt_expires_seconds,
        "user": user_out(user),
    }


@router.post("/auth/logout")
async def logout(_: CurrentUser) -> dict[str, bool]:
    return {"ok": True}


@router.get("/auth/me")
async def me(user: CurrentUser) -> dict[str, Any]:
    return user_out(user, include_created=True)
