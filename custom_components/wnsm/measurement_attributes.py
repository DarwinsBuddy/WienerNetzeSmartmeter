"""Helpers for consistent measurement attributes on sensors."""

from __future__ import annotations

from typing import Any


def set_messwert_attributes(attributes: dict[str, Any], values: list[int | float | None]) -> None:
    """Set standard Messwert attributes.

    Semantics:
    - messwert1: most recent candidate measurement value
    - messwert2: second most recent candidate measurement value
    """
    attributes["messwert1"] = values[0] if len(values) > 0 else None
    attributes["messwert2"] = values[1] if len(values) > 1 else None
