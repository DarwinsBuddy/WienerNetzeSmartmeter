from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


@dataclass
class DayValuePoint:
    """Normalized DAY reading point."""

    value_kwh: float
    reading_date: str
    source_timestamp: datetime


def _unit_factor(unit: str | None) -> float | None:
    if unit is None:
        return None
    unit = unit.upper()
    if unit == "WH":
        return 1e-3
    if unit == "KWH":
        return 1.0
    return None


def extract_day_points(messwerte: dict[str, Any]) -> list[DayValuePoint]:
    """Extract normalized DAY points from translated messwerte payload."""
    values = messwerte.get("values", [])
    factor = _unit_factor(messwerte.get("unitOfMeasurement"))
    if not values or factor is None:
        return []

    points: list[DayValuePoint] = []
    for value in values:
        timestamp = dt_util.parse_datetime(value.get("zeitBis") or value.get("zeitVon"))
        messwert = value.get("messwert")
        if timestamp is None or messwert is None:
            continue
        points.append(
            DayValuePoint(
                value_kwh=messwert * factor,
                reading_date=timestamp.isoformat(),
                source_timestamp=timestamp,
            )
        )
    return points


def latest_two_day_points(messwerte: dict[str, Any]) -> list[DayValuePoint]:
    """Return up to two latest normalized DAY points (newest first)."""
    points = sorted(
        extract_day_points(messwerte),
        key=lambda point: point.source_timestamp,
        reverse=True,
    )
    return points[:2]


def latest_day_point(messwerte: dict[str, Any]) -> DayValuePoint | None:
    """Return latest normalized DAY point, if any."""
    latest_points = latest_two_day_points(messwerte)
    if not latest_points:
        return None
    return latest_points[0]
