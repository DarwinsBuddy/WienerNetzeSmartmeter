"""
Utility functions and convenience methods to avoid boilerplate
"""
from __future__ import annotations
from functools import reduce
from datetime import datetime, timedelta
import logging


def today() -> datetime:
    """
    today's timestamp (start of day)
    """
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def before(timestamp=None, days=1) -> datetime:
    """
    subtract {days} days from given datetime (default: 1)
    """
    if timestamp is None:
        timestamp = today()
    return timestamp - timedelta(days=days)


def strint(string: str) -> int | None:
    """
    convenience function for easily convert None-able str to in
    """
    if string is not None and string.isdigit():
        return int(string)
    return string


def is_valid_access(data: list | dict, accessor: str | int) -> bool:
    """
    convenience function for double-checking if attribute of list or dict can be accessed
    """
    if isinstance(accessor, int) and isinstance(data, list):
        return accessor < len(data)
    if isinstance(accessor, str) and isinstance(data, dict):
        return accessor in data
    else:
        return False


def dict_path(path: str, dictionary: dict) -> str | None:
    """
    convenience function for accessing nested attributes within a dict
    """
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


def translate_dict(
    dictionary: dict, attrs_list: list[tuple[str, str]]
) -> dict[str, str]:
    """
    Given a response dictionary and an attribute mapping (with nested accessors separated by '.')
    returns a dictionary including all "picked" attributes addressed by attrs_list
    """
    result = {}
    for src, destination in attrs_list:
        value = dict_path(src, dictionary)
        if value is not None:
            result[destination] = value
    return result
