"""Adapters that normalise official-API responses to the internal shape.

The integration's sensors, statistics importer and config flow were all
originally written against the private *portal* API. To keep those
consumers untouched when we switch to :class:`OfficialSmartmeter`, this
module translates the public ``WN_SMART_METER_API`` payloads into the
dictionary layout that :mod:`wnsm.const` describes with
``ATTRS_ZAEHLPUNKTE_CALL``, ``ATTRS_HISTORIC_DATA`` and
``ATTRS_BEWEGUNGSDATEN``.

The adapters are deliberately pure (no I/O, no global state) so they can
be unit-tested in isolation and composed freely inside both the config
flow and the async wrapper.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from . import constants as const

# Public type aliases keep the downstream call sites readable.
OfficialZaehlpunkt = Dict[str, Any]
OfficialMesswerte = Dict[str, Any]
InternalZaehlpunkt = Dict[str, Any]
InternalHistoric = Dict[str, Any]
InternalBewegungsdaten = Dict[str, Any]

# Role-code lookup used by the internal API. Matches
# :class:`wnsm.api.constants.RoleType`. The official spec does not return
# a role directly, so we derive it from the requested ``wertetyp`` and the
# meter's ``anlage.typ`` (TAGSTROM → consuming, BEZUG → feeding).
_ROLE_CONSUMING_DAILY = "V001"
_ROLE_CONSUMING_QUARTER = "V002"
_ROLE_FEEDING_DAILY = "E001"
_ROLE_FEEDING_QUARTER = "E002"


def zaehlpunkt_to_internal(
    official: OfficialZaehlpunkt,
    *,
    customer_id: Optional[str] = None,
) -> InternalZaehlpunkt:
    """Translate a single official ``Zaehlpunkt`` to the internal shape.

    Fields missing from the public API (``isDefault``, ``isActive``,
    coordinates, …) are filled with sensible defaults so that the
    existing ``translate_dict``/``ATTRS_ZAEHLPUNKTE_CALL`` pipeline keeps
    working.

    Parameters
    ----------
    official:
        A payload as returned by ``GET /zaehlpunkte`` or
        ``GET /zaehlpunkte/{zp}`` on the official gateway.
    customer_id:
        Optional ``geschaeftspartner`` value. The official API does not
        expose the customer id, so callers that still need it must
        forward it explicitly (e.g. from config flow input).
    """
    anlage = official.get("anlage") or {}
    geraet = official.get("geraet") or {}
    idex = official.get("idex") or {}
    verbrauchsstelle = _normalise_verbrauchsstelle(
        official.get("verbrauchsstelle") or {}
    )

    return {
        "geschaeftspartner": customer_id,
        "zaehlpunktnummer": official.get("zaehlpunktnummer"),
        "customLabel": official.get("zaehlpunktname"),
        "equipmentNumber": geraet.get("equipmentnummer"),
        "geraetNumber": geraet.get("geraetenummer"),
        "verbrauchsstelle": verbrauchsstelle,
        "anlage": {
            "typ": anlage.get("typ"),
            "sparte": anlage.get("sparte"),
            "anlage": anlage.get("anlage"),
        },
        # The public API does not surface these flags. Assume "active +
        # default" because the API only returns meters the customer owns
        # and opted into; inactive meters simply aren't returned.
        "isDefault": True,
        "isActive": True,
        "isSmartMeterMarketReady": True,
        "idexStatus": {
            "granularity": {
                "status": idex.get("granularity"),
            },
            "customerInterface": idex.get("customerInterface"),
            "displayLocked": idex.get("displayLocked"),
        },
    }


def zaehlpunkte_to_internal(
    officials: Iterable[OfficialZaehlpunkt],
    *,
    customer_id: Optional[str] = None,
) -> List[InternalZaehlpunkt]:
    """Vectorised version of :func:`zaehlpunkt_to_internal`.

    Returns a list with the same ordering as the input iterable so the
    call site can re-use any positional cross-references.
    """
    return [
        zaehlpunkt_to_internal(zp, customer_id=customer_id)
        for zp in officials
    ]


def messwerte_to_historic_data(
    official: OfficialMesswerte,
) -> List[InternalHistoric]:
    """Translate ``/zaehlpunkte/{zp}/messwerte`` to ``ATTRS_HISTORIC_DATA`` input.

    The official payload groups readings by ``zaehlwerke``; each group
    corresponds to one OBIS code / unit pair. We return one dict per
    group with ``messwerte`` already converted to the lightweight shape
    consumed by the sensors (``value``, ``timestamp``, ``zeitBis``,
    ``quality``, ``isEstimated``).
    """
    zaehlwerke = official.get("zaehlwerke") or []
    return [
        {
            "obisCode": zw.get("obisCode"),
            "einheit": zw.get("einheit"),
            "messwerte": [
                _messwert_to_internal(mw) for mw in (zw.get("messwerte") or [])
            ],
        }
        for zw in zaehlwerke
    ]


def messwerte_to_bewegungsdaten(
    official: OfficialMesswerte,
    *,
    wertetyp: Union[const.Wertetyp, str],
    anlagen_typ: Optional[str] = None,
    customer_id: Optional[str] = None,
    obis_code: Optional[str] = None,
) -> InternalBewegungsdaten:
    """Translate messwerte to the ``ATTRS_BEWEGUNGSDATEN`` input shape.

    When the official response contains multiple ``zaehlwerke`` the first
    one matching ``obis_code`` is used, or the first one overall if no
    OBIS filter is given. This mirrors how the existing importer treats
    the private API's single-series payload.
    """
    wertetyp_value = _coerce_wertetyp(wertetyp)
    zaehlwerke = official.get("zaehlwerke") or []
    zw = _pick_zaehlwerk(zaehlwerke, obis_code)
    role = _derive_role(wertetyp_value, anlagen_typ)
    granularitaet = _derive_granularitaet(wertetyp_value)

    return {
        "descriptor": {
            "geschaeftspartnernummer": customer_id,
            "zaehlpunktnummer": official.get("zaehlpunkt"),
            "rolle": role,
            "aggregat": "NONE",
            "granularitaet": granularitaet,
            "einheit": zw.get("einheit") if zw else None,
            "obisCode": zw.get("obisCode") if zw else obis_code,
        },
        "values": [
            _messwert_to_internal(mw)
            for mw in (zw.get("messwerte") if zw else [])
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalise_verbrauchsstelle(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Align official field names with the legacy verbrauchsstelle keys.

    The portal API used ``anlageHausnummer`` where the official API uses
    ``hausnummer1``; ``translate_dict`` reads the legacy name, so we
    emit both.
    """
    hausnummer = (raw.get("hausnummer1") or "").strip()
    if raw.get("hausnummer2"):
        hausnummer = f"{hausnummer}{raw['hausnummer2']}".strip()

    return {
        **raw,
        "anlageHausnummer": hausnummer or None,
        "hausnummer": hausnummer or None,
        # Coordinates are not published by the public API.
        "laengengrad": None,
        "breitengrad": None,
    }


def _messwert_to_internal(mw: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one ``Messwert`` to the lightweight shape consumed downstream.

    Downstream consumers mix two naming conventions:

    * The ``Importer`` reads ``wert``, ``zeitpunktVon`` and ``geschaetzt`` –
      the German field names used by the legacy portal API.
    * The ``WNSMSensor.get_meter_reading_from_historic_data`` helper reads
      ``messwert``.
    * New code we write in this project prefers the English aliases
      (``value``, ``timestamp``, ``isEstimated``).

    Emitting both keeps every consumer happy with a single adapter.
    """
    quality = mw.get("qualitaet")
    value = mw.get("messwert")
    zeit_von = mw.get("zeitVon")
    zeit_bis = mw.get("zeitBis")
    is_estimated = quality is not None and quality != "VAL"
    return {
        # English aliases (new code)
        "value": value,
        "timestamp": zeit_von,
        "zeitVon": zeit_von,
        "zeitBis": zeit_bis,
        "quality": quality,
        # "VAL" is the "validated" marker used by Wiener Netze; anything
        # else (e.g. "ERS" for "Ersatzwert") is an estimate/replacement.
        "isEstimated": is_estimated,
        # Legacy portal-API keys consumed by the Importer / sensor
        "wert": value,
        "messwert": value,
        "zeitpunktVon": zeit_von,
        "zeitpunktBis": zeit_bis,
        "geschaetzt": is_estimated,
    }


def _pick_zaehlwerk(
    zaehlwerke: List[Dict[str, Any]],
    obis_code: Optional[str],
) -> Optional[Dict[str, Any]]:
    if not zaehlwerke:
        return None
    if obis_code is None:
        return zaehlwerke[0]
    for zw in zaehlwerke:
        if zw.get("obisCode") == obis_code:
            return zw
    return zaehlwerke[0]


def _coerce_wertetyp(value: Union[const.Wertetyp, str]) -> str:
    if isinstance(value, const.Wertetyp):
        return value.value
    return const.Wertetyp.from_str(value).value


def _derive_role(wertetyp: str, anlagen_typ: Optional[str]) -> str:
    """Map ``wertetyp`` + ``anlage.typ`` to a legacy ``RoleType`` code."""
    is_quarter = wertetyp == const.Wertetyp.QUARTER_HOUR.value
    if anlagen_typ:
        try:
            category = const.AnlagenType.from_str(anlagen_typ)
        except NotImplementedError:
            category = const.AnlagenType.CONSUMING
    else:
        category = const.AnlagenType.CONSUMING

    if category is const.AnlagenType.FEEDING:
        return _ROLE_FEEDING_QUARTER if is_quarter else _ROLE_FEEDING_DAILY
    return _ROLE_CONSUMING_QUARTER if is_quarter else _ROLE_CONSUMING_DAILY


def _derive_granularitaet(wertetyp: str) -> str:
    if wertetyp == const.Wertetyp.QUARTER_HOUR.value:
        return "QH"
    if wertetyp == const.Wertetyp.METER_READ.value:
        return "MR"
    return "D"


__all__ = [
    "zaehlpunkt_to_internal",
    "zaehlpunkte_to_internal",
    "messwerte_to_historic_data",
    "messwerte_to_bewegungsdaten",
]
