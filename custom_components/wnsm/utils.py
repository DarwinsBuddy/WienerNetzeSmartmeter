"""Utility functions and convenience methods to avoid boilerplate."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import reduce
from typing import Optional


def today(tz: Optional[timezone] = None) -> datetime:
    """Return today's timestamp at the start of the day."""
    return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)


def before(timestamp: Optional[datetime] = None, days=1) -> datetime:
    """Subtract ``days`` from the given datetime."""
    if timestamp is None:
        timestamp = today()
    return timestamp - timedelta(days=days)


def strint(string: str) -> Optional[int]:
    """Convert a digit-only string to an int while preserving other values."""
    if string is not None and string.isdigit():
        return int(string)
    return string


def is_valid_access(data: list | dict, accessor: str | int) -> bool:
    """Check whether a nested dict/list accessor can be applied safely."""
    if isinstance(accessor, int) and isinstance(data, list):
        return accessor < len(data)
    if isinstance(accessor, str) and isinstance(data, dict):
        return accessor in data
    return False


def dict_path(path: str, dictionary: dict) -> Optional[str]:
    """Access nested dictionary/list attributes using ``.`` separated keys."""
    try:
        return reduce(
            lambda acc, i: acc[i] if is_valid_access(acc, i) else None,
            [strint(s) for s in path.split(".")],
            dictionary,
        )
    except KeyError as exception:
        logging.warning("Could not find key '%s' in response", exception.args[0])
    except Exception as exception:
        logging.exception(exception)
    return None


def translate_dict(dictionary: dict, attrs_list: list[tuple[str, str]]) -> dict[str, str]:
    """Map selected source attributes into the flattened HA attribute schema."""
    result = {}
    for src, destination in attrs_list:
        result[destination] = dict_path(src, dictionary)
    return result
