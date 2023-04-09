import requests
from urllib import parse


def post_data_matcher(expected: dict = None):
    if expected is None:
        expected = dict()

    def match(request: requests.PreparedRequest):
        flag = dict(parse.parse_qsl(request.body)) == expected
        if not flag:
            print(f'ACTUAL:   {dict(parse.parse_qsl(request.body))}')
            print(f'EXPECTED: {expected}')
        return flag

    return match


def json_matcher(expected: dict = None):
    if expected is None:
        expected = dict()

    def match(request: requests.Request):
        return request.json() == expected

    return match
