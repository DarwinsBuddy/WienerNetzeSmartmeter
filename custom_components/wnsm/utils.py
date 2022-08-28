from functools import reduce
import datetime as dt
import logging


def today() -> dt.datetime:
    return dt.datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)

def before(d=None, days=1) -> dt.datetime:
    if d is None:
        d = today()
    return d - dt.timedelta(days=days)

def strint(s: str) -> str | int:
    if s is not None and s.isdigit():
        return int(s)
    return s

def is_valid_access(data: list | dict, accessor: str | int) -> bool:
    if type(accessor) == int and type(data) == list:
        return accessor < len(data)
    elif type(accessor) == str and type(data) == dict:
        return accessor in data
    else:
        return False

def dict_path(path: str, d: dict) -> str:
    try:
        return reduce(lambda acc, i: acc[i] if is_valid_access(acc, i) else None, [strint(s) for s in path.split('.')], d)
    except KeyError as e:
        logging.warning(f"Could not find key '{e.args[0]}' in response")
    except Exception as e:
        logging.exception(e)
    return None


def translate_dict(d: dict, attrs_list: list[tuple[str, str]]) -> dict[str, str]:
    result = {}
    for src, dest in attrs_list:
        value = dict_path(src, d)
        if value is not None:
            result[dest] = value
    return result
