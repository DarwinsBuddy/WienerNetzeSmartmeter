"""Utility functions and convenience methods to avoid boilerplate."""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo
from functools import reduce
import logging
from typing import Any

from homeassistant.util import dt as dt_util


def today(tz: tzinfo | None = None) -> datetime:
    """Return today's timestamp (start of day)."""
    if tz is None:
        default_tz = dt_util.DEFAULT_TIME_ZONE
        if isinstance(default_tz, str):
            tz = dt_util.get_time_zone(default_tz) or dt_util.UTC
        else:
            tz = default_tz or dt_util.UTC
    return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)


def before(timestamp: datetime | None = None, days: int = 1) -> datetime:
    """Subtract `days` from timestamp, using today() if timestamp is None."""
    if timestamp is None:
        timestamp = today()
    return timestamp - timedelta(days=days)


def build_reading_date_attributes(
    zaehlpunkt_response: dict[str, Any],
) -> tuple[list[datetime], dict[str, Any]]:
    """Build consistent reading-date related attributes for sensors."""
    reading_dates = [before(today(), 1), before(today(), 2)]
    attributes = {
        **zaehlpunkt_response,
        "reading_dates": [reading_date.isoformat() for reading_date in reading_dates],
        "reading_date": None,
        "yesterday": reading_dates[0].isoformat(),
        "day_before_yesterday": reading_dates[1].isoformat(),
    }
    return reading_dates, attributes


def strint(string: str | None) -> int | str | None:
    """Convert digit-only strings to int, otherwise return value unchanged."""
    if string is not None and string.isdigit():
        return int(string)
    return string


def is_valid_access(data: list[Any] | dict[str, Any], accessor: str | int) -> bool:
    """Check whether accessor can be used on list/dict values."""
    if isinstance(accessor, int) and isinstance(data, list):
        return accessor < len(data)
    if isinstance(accessor, str) and isinstance(data, dict):
        return accessor in data
    return False


def dict_path(path: str, dictionary: dict[str, Any]) -> Any | None:
    """Access nested dictionary/list values using dotted path syntax."""
    try:
        return reduce(
            lambda acc, i: acc[i] if is_valid_access(acc, i) else None,
            [strint(s) for s in path.split(".")],
            dictionary,
        )
    except KeyError as exception:
        logging.warning("Could not find key '%s' in response", exception.args[0])
    except Exception as exception:  # pylint: disable=broad-except
        logging.exception(exception)
    return None


def safeget(dct: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely read nested dict keys, returning default on missing key."""
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            return default
    return dct


def translate_dict(
    dictionary: dict[str, Any], attrs_list: list[tuple[str, str]]
) -> dict[str, Any]:
    """Translate selected values from source dictionary into a flat mapping."""
    result: dict[str, Any] = {}
    for src, destination in attrs_list:
        value = dict_path(src, dictionary)
        if value is not None:
            result[destination] = value
    return result
