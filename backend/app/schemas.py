from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class HomeCreate(BaseModel):
    name: str
    time_zone: str = "Asia/Almaty"
    latitude: float | None = None
    longitude: float | None = None
    currency: str = "KZT"


class AreaCreate(BaseModel):
    name: str
    icon: str | None = None
    floor_id: uuid.UUID | None = None
    temperature_entity_id: str | None = None
    humidity_entity_id: str | None = None


class AreaUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    floor_id: uuid.UUID | None = None
    temperature_entity_id: str | None = None
    humidity_entity_id: str | None = None


class DeviceCreate(BaseModel):
    name: str
    type: str
    area_id: uuid.UUID | None = None
    manufacturer: str | None = None
    model: str | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    name_by_user: str | None = None
    area_id: uuid.UUID | None = None
    status: str | None = None
    manufacturer: str | None = None
    model: str | None = None


class EntityStatePatch(BaseModel):
    state: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class ActionCall(BaseModel):
    domain: str
    action: str
    target: dict[str, Any]
    data: dict[str, Any] = Field(default_factory=dict)


class AutomationCreate(BaseModel):
    name: str
    description: str = ""
    is_enabled: bool = True
    mode: str = "single"
    trigger: dict[str, Any]
    condition: dict[str, Any] | None = None
    action: dict[str, Any]


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_enabled: bool | None = None
    mode: str | None = None
    trigger: dict[str, Any] | None = None
    condition: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
