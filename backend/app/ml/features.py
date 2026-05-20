from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

FEATURE_COLUMNS = ["power_w", "energy_kwh", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos"]


@dataclass(frozen=True)
class EnergyFeatureRow:
    id: str
    entity_id: str
    device_name: str
    recorded_at: datetime
    power_w: float
    energy_kwh: float
    features: list[float]


def cyclic_features(recorded_at: datetime) -> tuple[float, float, float, float]:
    hour_angle = (recorded_at.hour + recorded_at.minute / 60) / 24 * math.tau
    weekday_angle = recorded_at.weekday() / 7 * math.tau
    return (
        math.sin(hour_angle),
        math.cos(hour_angle),
        math.sin(weekday_angle),
        math.cos(weekday_angle),
    )


def build_feature_vector(power_w: float | None, energy_kwh: float | None, recorded_at: datetime) -> list[float]:
    hour_sin, hour_cos, weekday_sin, weekday_cos = cyclic_features(recorded_at)
    return [
        float(power_w or 0),
        float(energy_kwh or 0),
        hour_sin,
        hour_cos,
        weekday_sin,
        weekday_cos,
    ]

