from __future__ import annotations

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models import Entity
from app.services import condition_matches


def test_password_hash_and_verify() -> None:
    password_hash = hash_password("testpass123")
    assert verify_password("testpass123", password_hash)
    assert not verify_password("wrong", password_hash)


def test_jwt_roundtrip() -> None:
    import uuid

    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert decode_access_token(token) == user_id


def test_condition_matches_string_and_numeric_operators() -> None:
    entity = Entity(entity_id="sensor.temp", domain="sensor", name="Temp", state="22", attributes_json={})
    assert condition_matches(entity, {"operator": "eq", "value": "22"})
    assert condition_matches(entity, {"operator": "ne", "value": "23"})
    assert condition_matches(entity, {"operator": "lt", "value": 30})
    assert condition_matches(entity, {"operator": "gt", "value": 20})
    assert not condition_matches(entity, {"operator": "gt", "value": 30})
