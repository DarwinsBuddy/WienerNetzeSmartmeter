"""Unit tests for the official Wiener Netze Smart Meter API client.

These tests exercise :class:`wnsm.api.official_client.OfficialSmartmeter`
against a ``requests_mock`` backend, so no real Wiener Netze credentials
are required. They focus on the four aspects that are easy to get wrong:

* OAuth2 client_credentials token handling and caching
* Header wiring (``Authorization`` + ``x-Gateway-APIKey``)
* Query parameter assembly for each endpoint
* Normalisation of ``{"items": ...}`` vs bare-array responses

The file intentionally sits at ``tests/`` (not ``tests/it/``) so that
collection does not execute ``tests/it/__init__.py``, which eager-imports
``homeassistant`` – a dependency we don't want to require for unit tests
of pure API-client code.
"""
# pylint: disable=redefined-outer-name,wrong-import-position
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Bootstrap: load the three API submodules directly from their files so we
# don't trigger ``wnsm/__init__.py`` (which imports ``homeassistant``).
#
# When ``homeassistant`` *is* installed (CI or a dev env that installed
# ``tests/requirements.txt``) the stub below is harmless – it just shadows
# the real package modules with loader-less placeholders that redirect
# submodule lookups to the real files on disk. Either way, ``from
# wnsm.api... import ...`` in the test body Just Works.
# ---------------------------------------------------------------------------
_WNSM_ROOT: Path = (
    Path(__file__).resolve().parent.parent / "custom_components" / "wnsm"
)


def _install_stub_package(name: str, path: Path) -> types.ModuleType:
    """Register an empty namespace package so submodule imports resolve."""
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    module.__path__ = [str(path)]  # type: ignore[attr-defined]
    sys.modules[name] = module
    return module


def _load_file(fullname: str, path: Path) -> types.ModuleType:
    """Load a .py file as ``fullname`` without going through ``importlib`` caches."""
    if fullname in sys.modules:
        return sys.modules[fullname]
    spec = importlib.util.spec_from_file_location(fullname, path)
    assert spec is not None and spec.loader is not None, f"no loader for {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module


_install_stub_package("wnsm", _WNSM_ROOT)
_install_stub_package("wnsm.api", _WNSM_ROOT / "api")
_load_file("wnsm.api.constants", _WNSM_ROOT / "api" / "constants.py")
_load_file("wnsm.api.errors", _WNSM_ROOT / "api" / "errors.py")
_load_file("wnsm.api.official_client", _WNSM_ROOT / "api" / "official_client.py")
_load_file("wnsm.api.adapter", _WNSM_ROOT / "api" / "adapter.py")


# ---------------------------------------------------------------------------
# Extra bootstrap for :mod:`wnsm.api.client_factory`. The factory lives
# above the homeassistant boundary (it imports ``homeassistant.const`` for
# the legacy username/password keys and transitively loads the scraper
# client). We stub all three out so the pure-Python shim code is testable
# without installing ``homeassistant``, ``lxml`` or ``python-dateutil``.
# ---------------------------------------------------------------------------
def _install_stub_module(name: str, **attrs: Any) -> types.ModuleType:
    """Create (or extend) a fake module with the given attributes."""
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


if "homeassistant" not in sys.modules:
    _install_stub_module("homeassistant")
_install_stub_module(
    "homeassistant.const",
    CONF_USERNAME="username",
    CONF_PASSWORD="password",
)


class _StubSmartmeter:
    """Placeholder for the legacy scraper – the factory only needs the class
    object to switch on, the test never instantiates it."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs


_install_stub_module("wnsm.api.client", Smartmeter=_StubSmartmeter)

# Load wnsm.const + client_factory from the real files now that all
# cross-package imports resolve against the stubs above.
_load_file("wnsm.const", _WNSM_ROOT / "const.py")
_load_file(
    "wnsm.api.client_factory", _WNSM_ROOT / "api" / "client_factory.py"
)

import pytest  # noqa: E402
from requests_mock import Mocker  # noqa: E402

from wnsm.api import constants as const  # noqa: E402
from wnsm.api.errors import (  # noqa: E402
    SmartmeterConnectionError,
    SmartmeterLoginError,
    SmartmeterQueryError,
)
from wnsm.api.official_client import OfficialSmartmeter  # noqa: E402

CLIENT_ID = "cid-test"
CLIENT_SECRET = "secret-test"  # noqa: S105 - test fixture
API_KEY = "gateway-key-test"
ACCESS_TOKEN = "token-abc123"


def _mock_token(
    requests_mock: Mocker,
    *,
    token: str = ACCESS_TOKEN,
    expires_in: int = 3600,
    status: int = 200,
    body: Optional[Dict[str, Any]] = None,
) -> None:
    """Register the OAuth2 token endpoint mock."""
    payload: Dict[str, Any] = body if body is not None else {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": "profile",
    }
    requests_mock.post(
        const.OFFICIAL_TOKEN_URL, json=payload, status_code=status
    )


def _make_client(**overrides: Any) -> OfficialSmartmeter:
    kwargs: Dict[str, Any] = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "api_key": API_KEY,
    }
    kwargs.update(overrides)
    return OfficialSmartmeter(**kwargs)


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("requests_mock")
def test_login_success_stores_token(requests_mock: Mocker):
    _mock_token(requests_mock)

    client = _make_client()
    token = client.login()

    assert token == ACCESS_TOKEN
    history = requests_mock.request_history
    assert len(history) == 1
    assert history[0].url == const.OFFICIAL_TOKEN_URL
    body = history[0].text
    assert "grant_type=client_credentials" in body
    assert f"client_id={CLIENT_ID}" in body
    assert "client_secret=secret-test" in body
    # Scope is intentionally omitted by default – see issue #276 and the
    # reference wrapper at tschoerk/Wiener-Netze-Smart-Meter-API. Sending
    # ``scope=profile`` causes "scope not associated with the client"
    # errors on apps that weren't explicitly provisioned with it.
    assert "scope=" not in body
    # Gateway is strict about Content-Type; make sure we pin it.
    assert history[0].headers.get("Content-Type") == (
        "application/x-www-form-urlencoded"
    )


@pytest.mark.usefixtures("requests_mock")
def test_login_sends_scope_only_when_explicitly_configured(requests_mock: Mocker):
    _mock_token(requests_mock)

    _make_client(scope="profile").login()

    body = requests_mock.request_history[0].text
    assert "scope=profile" in body


@pytest.mark.usefixtures("requests_mock")
def test_login_error_raises_login_error(requests_mock: Mocker):
    _mock_token(
        requests_mock,
        status=401,
        body={"error": "invalid_client"},
    )

    with pytest.raises(SmartmeterLoginError) as exc_info:
        _make_client().login()

    assert exc_info.value.code == 401


@pytest.mark.usefixtures("requests_mock")
def test_login_missing_access_token_raises(requests_mock: Mocker):
    _mock_token(requests_mock, body={"token_type": "Bearer"})

    with pytest.raises(SmartmeterLoginError):
        _make_client().login()


def test_login_connection_error_raises_connection_error():
    # Deliberately not using requests_mock: we want the underlying transport
    # to actually fail so we can prove the exception gets wrapped.
    client = _make_client(token_url="http://127.0.0.1:1/nope")
    with pytest.raises(SmartmeterConnectionError):
        client.login()


# ---------------------------------------------------------------------------
# zaehlpunkte()
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkte_sends_correct_headers_and_returns_list(requests_mock: Mocker):
    _mock_token(requests_mock)
    sample = [
        {
            "zaehlpunktnummer": "AT0010000000000000001000000000001",
            "zaehlpunktname": "Haushalt",
            "anlage": {"anlage": "42", "sparte": "STROM", "typ": "TAGSTROM"},
            "geraet": {"equipmentnummer": "E1", "geraetenummer": "G1"},
            "idex": {
                "customerInterface": "ENABLED",
                "displayLocked": False,
                "granularity": "QUARTER_HOUR",
            },
            "verbrauchsstelle": {
                "haus": "",
                "hausnummer1": "1",
                "hausnummer2": "",
                "land": "AT",
                "ort": "Wien",
                "postleitzahl": "1010",
                "stockwerk": "",
                "strasse": "Ringstr.",
                "strasseZusatz": "",
                "tuernummer": "",
            },
        }
    ]
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte",
        json=sample,
    )

    client = _make_client(web_profile_id="profile-1")
    result = client.zaehlpunkte()

    assert result == sample

    call = requests_mock.request_history[-1]
    assert call.headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert call.headers["x-Gateway-APIKey"] == API_KEY
    assert call.qs.get("webprofileid") == ["profile-1"]


@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkte_unwraps_items_envelope(requests_mock: Mocker):
    _mock_token(requests_mock)
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte",
        json={"items": [{"zaehlpunktnummer": "AT0001"}]},
    )

    result = _make_client().zaehlpunkte()

    assert result == [{"zaehlpunktnummer": "AT0001"}]


@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkte_forwards_query_parameters(requests_mock: Mocker):
    _mock_token(requests_mock)
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte",
        json=[],
    )

    _make_client().zaehlpunkte(zaehlpunkt="AT00XX", result_type="full")

    call = requests_mock.request_history[-1]
    # requests_mock lower-cases query-string keys *and* values in .qs
    assert call.qs["zaehlpunkt"] == ["at00xx"]
    assert call.qs["resulttype"] == ["full"]


# ---------------------------------------------------------------------------
# zaehlpunkt(zp)
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("requests_mock")
def test_zaehlpunkt_detail(requests_mock: Mocker):
    _mock_token(requests_mock)
    zp = "AT0010000000000000001000000000001"
    payload = {"zaehlpunktnummer": zp, "zaehlpunktname": "Haushalt"}
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte/{zp}",
        json=payload,
    )

    result = _make_client().zaehlpunkt(zp)

    assert result == payload


def test_zaehlpunkt_requires_id():
    with pytest.raises(ValueError):
        _make_client().zaehlpunkt("")


# ---------------------------------------------------------------------------
# messwerte()
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("requests_mock")
def test_messwerte_single_zp_builds_expected_query(requests_mock: Mocker):
    _mock_token(requests_mock)
    zp = "AT0010000000000000001000000000001"
    payload = {
        "zaehlpunkt": zp,
        "zaehlwerke": [
            {
                "einheit": "WH",
                "obisCode": "1-1:1.9.0",
                "messwerte": [
                    {
                        "messwert": 123,
                        "qualitaet": "VAL",
                        "zeitVon": "2026-04-10T00:00:00Z",
                        "zeitBis": "2026-04-10T00:15:00Z",
                    }
                ],
            }
        ],
    }
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte/{zp}/messwerte",
        json=payload,
    )

    result = _make_client().messwerte(
        datum_von=date(2026, 4, 10),
        datum_bis=date(2026, 4, 11),
        wertetyp=const.Wertetyp.QUARTER_HOUR,
        zaehlpunkt=zp,
    )

    assert result == payload
    call = requests_mock.request_history[-1]
    assert call.qs["datumvon"] == ["2026-04-10"]
    assert call.qs["datumbis"] == ["2026-04-11"]
    assert call.qs["wertetyp"] == ["quarter_hour"]


@pytest.mark.usefixtures("requests_mock")
def test_messwerte_bulk_unwraps_items(requests_mock: Mocker):
    _mock_token(requests_mock)
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte/messwerte",
        json={"items": [{"zaehlpunkt": "AT01", "zaehlwerke": []}]},
    )

    result = _make_client().messwerte(
        datum_von="2026-04-01",
        datum_bis="2026-04-10",
        wertetyp="DAY",
    )

    assert result == [{"zaehlpunkt": "AT01", "zaehlwerke": []}]


def test_messwerte_rejects_unknown_wertetyp():
    with pytest.raises(ValueError):
        _make_client().messwerte(
            datum_von="2026-04-01",
            datum_bis="2026-04-02",
            wertetyp="HOURLY",
        )


# ---------------------------------------------------------------------------
# Token caching & refresh
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("requests_mock")
def test_token_is_cached_between_requests(requests_mock: Mocker):
    _mock_token(requests_mock)
    requests_mock.get(f"{const.OFFICIAL_API_URL}/zaehlpunkte", json=[])

    client = _make_client()
    client.zaehlpunkte()
    client.zaehlpunkte()

    token_calls = [
        h for h in requests_mock.request_history
        if h.url == const.OFFICIAL_TOKEN_URL
    ]
    assert len(token_calls) == 1


@pytest.mark.usefixtures("requests_mock")
def test_token_refresh_on_401(requests_mock: Mocker):
    _mock_token(requests_mock)
    # First resource call returns 401, second returns success.
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte",
        [
            {"status_code": 401, "json": {"error": "expired"}},
            {"status_code": 200, "json": []},
        ],
    )

    result = _make_client().zaehlpunkte()

    assert result == []
    token_calls = [
        h for h in requests_mock.request_history
        if h.url == const.OFFICIAL_TOKEN_URL
    ]
    # Expect: initial token + one forced refresh after the 401.
    assert len(token_calls) == 2


@pytest.mark.usefixtures("requests_mock")
def test_non_200_error_response_raises_query_error(requests_mock: Mocker):
    _mock_token(requests_mock)
    requests_mock.get(
        f"{const.OFFICIAL_API_URL}/zaehlpunkte",
        status_code=500,
        text="boom",
    )

    with pytest.raises(SmartmeterQueryError) as exc_info:
        _make_client().zaehlpunkte()

    assert exc_info.value.code == 500


# ---------------------------------------------------------------------------
# Date coercion helpers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (date(2026, 4, 10), "2026-04-10"),
        (datetime(2026, 4, 10, 12, 34, 56), "2026-04-10"),
        ("2026-04-10T00:00:00Z", "2026-04-10T00:00:00Z"),  # passthrough
    ],
)
def test_format_date_helper(value, expected):
    from wnsm.api.official_client import _format_date

    assert _format_date(value) == expected


def test_format_date_rejects_unsupported_type():
    from wnsm.api.official_client import _format_date

    with pytest.raises(TypeError):
        _format_date(1234567890)  # type: ignore[arg-type]


def test_messwerte_date_round_trip_via_helper():
    today = date.today()
    last_week = today - timedelta(days=7)

    from wnsm.api.official_client import _format_date

    assert _format_date(last_week) == last_week.isoformat()
    assert _format_date(today) == today.isoformat()


# ===========================================================================
# Adapter tests (official -> internal shape)
# ===========================================================================
from wnsm.api import adapter  # noqa: E402


_OFFICIAL_ZP = {
    "zaehlpunktnummer": "AT0010000000000000001000000000001",
    "zaehlpunktname": "Haushalt",
    "anlage": {"anlage": "42", "sparte": "STROM", "typ": "TAGSTROM"},
    "geraet": {"equipmentnummer": "E1", "geraetenummer": "G1"},
    "idex": {
        "customerInterface": "ENABLED",
        "displayLocked": False,
        "granularity": "QUARTER_HOUR",
    },
    "verbrauchsstelle": {
        "haus": "Haus A",
        "hausnummer1": "12",
        "hausnummer2": "b",
        "land": "AT",
        "ort": "Wien",
        "postleitzahl": "1010",
        "stockwerk": "",
        "strasse": "Ringstr.",
        "strasseZusatz": "",
        "tuernummer": "",
    },
}


def test_adapter_zaehlpunkt_maps_core_fields():
    internal = adapter.zaehlpunkt_to_internal(_OFFICIAL_ZP, customer_id="CUST42")

    assert internal["zaehlpunktnummer"] == _OFFICIAL_ZP["zaehlpunktnummer"]
    assert internal["customLabel"] == "Haushalt"
    assert internal["equipmentNumber"] == "E1"
    assert internal["geraetNumber"] == "G1"
    assert internal["geschaeftspartner"] == "CUST42"
    assert internal["anlage"]["typ"] == "TAGSTROM"
    assert internal["verbrauchsstelle"]["postleitzahl"] == "1010"
    assert internal["verbrauchsstelle"]["anlageHausnummer"] == "12b"
    assert internal["isActive"] is True
    assert internal["isDefault"] is True
    assert internal["idexStatus"]["granularity"]["status"] == "QUARTER_HOUR"


def test_adapter_translate_dict_integration():
    """Output must round-trip through translate_dict + ATTRS_ZAEHLPUNKTE_CALL."""
    # Load the small, HA-free helpers on demand so we don't need the full
    # component package at import time.
    _load_file("wnsm.utils", _WNSM_ROOT / "utils.py")
    _load_file("wnsm.const", _WNSM_ROOT / "const.py")
    from wnsm.utils import translate_dict
    from wnsm.const import ATTRS_ZAEHLPUNKTE_CALL

    internal = adapter.zaehlpunkt_to_internal(_OFFICIAL_ZP, customer_id="CUST42")
    translated = translate_dict(internal, ATTRS_ZAEHLPUNKTE_CALL)

    assert translated["zaehlpunktnummer"] == _OFFICIAL_ZP["zaehlpunktnummer"]
    assert translated["customerId"] == "CUST42"
    assert translated["label"] == "Haushalt"
    assert translated["type"] == "TAGSTROM"
    assert translated["zip"] == "1010"
    assert translated["active"] is True


def test_adapter_zaehlpunkte_list():
    result = adapter.zaehlpunkte_to_internal(
        [_OFFICIAL_ZP, _OFFICIAL_ZP],
        customer_id="CUST42",
    )
    assert len(result) == 2
    assert all(r["customLabel"] == "Haushalt" for r in result)


_OFFICIAL_MESSWERTE = {
    "zaehlpunkt": "AT0010000000000000001000000000001",
    "zaehlwerke": [
        {
            "einheit": "WH",
            "obisCode": "1-1:1.9.0",
            "messwerte": [
                {
                    "messwert": 150,
                    "qualitaet": "VAL",
                    "zeitVon": "2026-04-10T00:00:00Z",
                    "zeitBis": "2026-04-10T00:15:00Z",
                },
                {
                    "messwert": 175,
                    "qualitaet": "ERS",
                    "zeitVon": "2026-04-10T00:15:00Z",
                    "zeitBis": "2026-04-10T00:30:00Z",
                },
            ],
        }
    ],
}


def test_adapter_historic_data_shape():
    historic = adapter.messwerte_to_historic_data(_OFFICIAL_MESSWERTE)

    assert len(historic) == 1
    series = historic[0]
    assert series["obisCode"] == "1-1:1.9.0"
    assert series["einheit"] == "WH"
    assert len(series["messwerte"]) == 2
    first = series["messwerte"][0]
    assert first["value"] == 150
    assert first["timestamp"] == "2026-04-10T00:00:00Z"
    assert first["isEstimated"] is False
    second = series["messwerte"][1]
    assert second["isEstimated"] is True  # ERS != VAL


def test_adapter_bewegungsdaten_consuming_quarter_hour():
    bd = adapter.messwerte_to_bewegungsdaten(
        _OFFICIAL_MESSWERTE,
        wertetyp=const.Wertetyp.QUARTER_HOUR,
        anlagen_typ="TAGSTROM",
        customer_id="CUST42",
    )

    descriptor = bd["descriptor"]
    assert descriptor["zaehlpunktnummer"] == _OFFICIAL_MESSWERTE["zaehlpunkt"]
    assert descriptor["rolle"] == "V002"  # consuming + QH
    assert descriptor["granularitaet"] == "QH"
    assert descriptor["einheit"] == "WH"
    assert descriptor["geschaeftspartnernummer"] == "CUST42"
    assert len(bd["values"]) == 2


def test_adapter_bewegungsdaten_feeding_daily():
    bd = adapter.messwerte_to_bewegungsdaten(
        _OFFICIAL_MESSWERTE,
        wertetyp="DAY",
        anlagen_typ="BEZUG",
    )
    assert bd["descriptor"]["rolle"] == "E001"  # feeding + daily
    assert bd["descriptor"]["granularitaet"] == "D"


def test_adapter_bewegungsdaten_handles_empty_zaehlwerke():
    empty = {"zaehlpunkt": "AT0001", "zaehlwerke": []}
    bd = adapter.messwerte_to_bewegungsdaten(
        empty,
        wertetyp=const.Wertetyp.DAY,
        anlagen_typ="TAGSTROM",
    )
    assert bd["values"] == []
    assert bd["descriptor"]["einheit"] is None


def test_adapter_bewegungsdaten_picks_obis_match():
    multi = {
        "zaehlpunkt": "AT0001",
        "zaehlwerke": [
            {"obisCode": "1-1:1.8.0", "einheit": "WH", "messwerte": []},
            {"obisCode": "1-1:1.9.0", "einheit": "WH", "messwerte": [
                {"messwert": 1, "qualitaet": "VAL", "zeitVon": "x", "zeitBis": "y"}
            ]},
        ],
    }
    bd = adapter.messwerte_to_bewegungsdaten(
        multi,
        wertetyp="QUARTER_HOUR",
        anlagen_typ="TAGSTROM",
        obis_code="1-1:1.9.0",
    )
    assert bd["descriptor"]["obisCode"] == "1-1:1.9.0"
    assert len(bd["values"]) == 1


def test_adapter_messwert_emits_legacy_keys():
    """The Importer reads ``wert``, ``zeitpunktVon`` and ``geschaetzt``;
    :meth:`WNSMSensor.get_meter_reading_from_historic_data` reads
    ``messwert``. Both naming conventions must be present."""
    historic = adapter.messwerte_to_historic_data(_OFFICIAL_MESSWERTE)
    mw = historic[0]["messwerte"][0]

    # Legacy portal keys consumed by importer.py + wnsm_sensor.py
    assert mw["wert"] == 150
    assert mw["messwert"] == 150
    assert mw["zeitpunktVon"] == "2026-04-10T00:00:00Z"
    assert mw["zeitpunktBis"] == "2026-04-10T00:15:00Z"
    assert mw["geschaetzt"] is False
    # Estimated reading gets geschaetzt=True
    estimated = historic[0]["messwerte"][1]
    assert estimated["geschaetzt"] is True


# ===========================================================================
# Client factory + _OfficialSmartmeterShim tests
# ===========================================================================
from wnsm.api import client_factory  # noqa: E402
from wnsm.api.client_factory import (  # noqa: E402
    _OfficialSmartmeterShim,
    make_client,
)
from wnsm.const import (  # noqa: E402
    AUTH_METHOD_LEGACY,
    AUTH_METHOD_OFFICIAL,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CUSTOMER_ID,
    CONF_WEB_PROFILE_ID,
)


def _official_entry() -> Dict[str, Any]:
    return {
        CONF_AUTH_METHOD: AUTH_METHOD_OFFICIAL,
        CONF_CLIENT_ID: CLIENT_ID,
        CONF_CLIENT_SECRET: CLIENT_SECRET,
        CONF_API_KEY: API_KEY,
        CONF_WEB_PROFILE_ID: "profile-1",
        CONF_CUSTOMER_ID: "CUST42",
    }


def test_make_client_returns_shim_for_official():
    shim = make_client(_official_entry())
    assert isinstance(shim, _OfficialSmartmeterShim)
    assert shim.customer_id == "CUST42"
    assert isinstance(shim.client, OfficialSmartmeter)
    assert shim.client.client_id == CLIENT_ID
    assert shim.client.api_key == API_KEY
    assert shim.client.web_profile_id == "profile-1"


def test_make_client_returns_legacy_smartmeter_for_legacy():
    from wnsm.api.client import Smartmeter as _StubSmartmeterRef

    legacy_entry: Dict[str, Any] = {
        CONF_AUTH_METHOD: AUTH_METHOD_LEGACY,
        "username": "user",
        "password": "pass",  # noqa: S106 - test fixture
    }
    client = make_client(legacy_entry)
    assert isinstance(client, _StubSmartmeterRef)
    # Stub records the positional args so we can prove the factory
    # forwarded the right fields.
    assert client.args == ("user", "pass")


def test_make_client_defaults_to_legacy_when_method_missing():
    """Entries created before the auth_method key was introduced must
    still resolve to the legacy scraper – otherwise upgrading the
    integration would break every existing install."""
    from wnsm.api.client import Smartmeter as _StubSmartmeterRef

    entry: Dict[str, Any] = {"username": "u", "password": "p"}  # noqa: S106
    client = make_client(entry)
    assert isinstance(client, _StubSmartmeterRef)


class _FakeOfficialClient:
    """In-memory stand-in for :class:`OfficialSmartmeter`.

    Captures the calls the shim makes and returns canned responses so
    we can assert on both sides of the translation without touching the
    network. Implements just the slice of :class:`OfficialSmartmeter`
    the shim actually invokes.
    """

    def __init__(self, *, zaehlpunkte_response: Any, messwerte_response: Any):
        self._zaehlpunkte_response = zaehlpunkte_response
        self._messwerte_response = messwerte_response
        self.login_calls = 0
        self.zaehlpunkte_calls = 0
        self.messwerte_calls: list[Dict[str, Any]] = []

    def login(self) -> str:
        self.login_calls += 1
        return "tok"

    def zaehlpunkte(self) -> list[Dict[str, Any]]:
        self.zaehlpunkte_calls += 1
        return self._zaehlpunkte_response

    def messwerte(self, **kwargs: Any) -> Any:
        self.messwerte_calls.append(kwargs)
        return self._messwerte_response


def _make_shim(
    *,
    zaehlpunkte_response: Any = None,
    messwerte_response: Any = None,
    customer_id: Optional[str] = "CUST42",
) -> tuple[_OfficialSmartmeterShim, _FakeOfficialClient]:
    fake = _FakeOfficialClient(
        zaehlpunkte_response=zaehlpunkte_response or [_OFFICIAL_ZP],
        messwerte_response=messwerte_response or _OFFICIAL_MESSWERTE,
    )
    shim = _OfficialSmartmeterShim(client=fake, customer_id=customer_id)
    return shim, fake


def test_shim_login_delegates_to_client():
    shim, fake = _make_shim()
    assert shim.login() == "tok"
    assert fake.login_calls == 1


def test_shim_zaehlpunkte_wraps_in_legacy_contract():
    shim, fake = _make_shim()

    contracts = shim.zaehlpunkte()

    assert fake.zaehlpunkte_calls == 1
    assert len(contracts) == 1
    contract = contracts[0]
    assert contract["geschaeftspartner"] == "CUST42"
    assert len(contract["zaehlpunkte"]) == 1
    zp = contract["zaehlpunkte"][0]
    assert zp["zaehlpunktnummer"] == _OFFICIAL_ZP["zaehlpunktnummer"]
    assert zp["isActive"] is True
    assert zp["anlage"]["typ"] == "TAGSTROM"


def test_shim_historical_data_returns_single_dict():
    shim, fake = _make_shim()

    result = shim.historical_data(
        zaehlpunktnummer="AT0010000000000000001000000000001",
        date_from=date(2026, 4, 10),
        date_until=date(2026, 4, 11),
        valuetype=const.ValueType.METER_READ,
    )

    # Legacy portal API returns a single {obisCode, einheit, messwerte}
    # object per request. The shim must flatten the zaehlwerke list.
    assert isinstance(result, dict)
    assert result["obisCode"] == "1-1:1.9.0"
    assert result["einheit"] == "WH"
    assert len(result["messwerte"]) == 2
    # The importer and sensor expect legacy key names on each entry.
    assert result["messwerte"][0]["messwert"] == 150
    assert result["messwerte"][0]["wert"] == 150

    # And the call should have been routed to the per-zp messwerte
    # endpoint with the right query parameters.
    assert len(fake.messwerte_calls) == 1
    call = fake.messwerte_calls[0]
    assert call["zaehlpunkt"] == "AT0010000000000000001000000000001"
    assert call["wertetyp"] is const.Wertetyp.METER_READ


def test_shim_historical_data_handles_empty_response():
    shim, _ = _make_shim(
        messwerte_response={"zaehlpunkt": "AT0001", "zaehlwerke": []}
    )

    result = shim.historical_data(
        zaehlpunktnummer="AT0001",
        date_from=date(2026, 4, 10),
        date_until=date(2026, 4, 11),
    )

    assert result == {"obisCode": None, "einheit": None, "messwerte": []}


def test_shim_historical_data_requires_zaehlpunkt():
    shim, _ = _make_shim()
    with pytest.raises(ValueError):
        shim.historical_data()


def test_shim_bewegungsdaten_routes_through_adapter():
    shim, fake = _make_shim()

    bd = shim.bewegungsdaten(
        zaehlpunktnummer="AT0010000000000000001000000000001",
        date_from=date(2026, 4, 10),
        date_until=date(2026, 4, 11),
        valuetype=const.ValueType.QUARTER_HOUR,
    )

    descriptor = bd["descriptor"]
    assert descriptor["zaehlpunktnummer"] == _OFFICIAL_MESSWERTE["zaehlpunkt"]
    # TAGSTROM (consuming) + quarter-hour → V002
    assert descriptor["rolle"] == "V002"
    assert descriptor["granularitaet"] == "QH"
    assert descriptor["geschaeftspartnernummer"] == "CUST42"
    assert len(bd["values"]) == 2
    # Importer reads wert/zeitpunktVon/geschaetzt – those must survive
    # the adapter round-trip end-to-end.
    first = bd["values"][0]
    assert first["wert"] == 150
    assert first["zeitpunktVon"] == "2026-04-10T00:00:00Z"
    assert first["geschaetzt"] is False

    # The shim should have pre-fetched zaehlpunkte to derive the role.
    assert fake.zaehlpunkte_calls == 1


def test_shim_bewegungsdaten_requires_zaehlpunkt():
    shim, _ = _make_shim()
    with pytest.raises(ValueError):
        shim.bewegungsdaten()


def test_shim_bewegungsdaten_caches_zaehlpunkte_lookup():
    """The role-lookup for bewegungsdaten calls should reuse the cached
    zaehlpunkte list instead of hitting the API again per request."""
    shim, fake = _make_shim()

    shim.bewegungsdaten(
        zaehlpunktnummer="AT0010000000000000001000000000001",
        date_from=date(2026, 4, 10),
        date_until=date(2026, 4, 11),
    )
    shim.bewegungsdaten(
        zaehlpunktnummer="AT0010000000000000001000000000001",
        date_from=date(2026, 4, 10),
        date_until=date(2026, 4, 11),
    )

    assert fake.zaehlpunkte_calls == 1  # cached, not re-fetched
    assert len(fake.messwerte_calls) == 2


def test_shim_coerces_value_type_to_wertetyp():
    assert (
        _OfficialSmartmeterShim._coerce_wertetyp(const.ValueType.DAY)
        is const.Wertetyp.DAY
    )
    assert (
        _OfficialSmartmeterShim._coerce_wertetyp(const.ValueType.METER_READ)
        is const.Wertetyp.METER_READ
    )
    assert (
        _OfficialSmartmeterShim._coerce_wertetyp(None)
        is const.Wertetyp.QUARTER_HOUR
    )


@pytest.mark.parametrize(
    "method",
    ["base_information", "verbrauch", "verbrauchRaw", "consumptions"],
)
def test_shim_unsupported_methods_raise(method: str):
    shim, _ = _make_shim()
    with pytest.raises(NotImplementedError) as exc_info:
        getattr(shim, method)()
    # The error message must name the missing method so users know
    # exactly what the official API lacks.
    assert method in str(exc_info.value)


def test_shim_is_login_expired_tracks_internal_token():
    shim, _ = _make_shim()
    # Fake client never populated ``_token`` – we consider that expired.
    assert shim.is_login_expired() is True
