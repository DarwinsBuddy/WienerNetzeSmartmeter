"""Factory that returns the right Smartmeter implementation for a HA entry.

The sensor and importer code paths in this integration are written
against the legacy :class:`wnsm.api.client.Smartmeter` method surface
(``login``/``zaehlpunkte``/``historical_data``/``bewegungsdaten``/…).
When the user picks the official OAuth2 API in the config flow, we
still want those call sites to Just Work. :func:`make_client` therefore
returns either:

* the legacy :class:`Smartmeter` – for entries that were created via the
  username/password branch of the config flow, or
* an :class:`_OfficialSmartmeterShim` – a thin adapter around
  :class:`OfficialSmartmeter` that exposes the same method names and
  translates the responses into the legacy shape via
  :mod:`wnsm.api.adapter`.

The shim intentionally does not try to emulate endpoints that do not
exist on the public API. ``base_information``/``verbrauch``/
``verbrauchRaw``/``consumptions`` all raise ``NotImplementedError`` with
a clear message so users running the official API get a predictable
failure instead of a mysterious ``AttributeError``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from ..const import (
    AUTH_METHOD_LEGACY,
    AUTH_METHOD_OFFICIAL,
    CONF_API_KEY,
    CONF_AUTH_METHOD,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CUSTOMER_ID,
    CONF_SCOPE,
    CONF_WEB_PROFILE_ID,
)
from . import adapter
from .client import Smartmeter
from .constants import ValueType, Wertetyp
from .official_client import OfficialSmartmeter

_LOGGER = logging.getLogger(__name__)


# The sensor/importer speak in :class:`ValueType`; the official API
# client speaks in :class:`Wertetyp`. Keep the mapping in one place.
_VALUE_TYPE_TO_WERTETYP: Dict[ValueType, Wertetyp] = {
    ValueType.METER_READ: Wertetyp.METER_READ,
    ValueType.DAY: Wertetyp.DAY,
    ValueType.QUARTER_HOUR: Wertetyp.QUARTER_HOUR,
}


_UNSUPPORTED_MSG = (
    "The official WN_SMART_METER_API does not expose a '{method}' "
    "equivalent. Use the legacy username/password integration if you "
    "need that call."
)


def make_client(entry_data: Dict[str, Any]):
    """Return a Smartmeter-compatible client for the given HA entry data.

    The returned object always provides the legacy method names used by
    :class:`wnsm.AsyncSmartmeter.AsyncSmartmeter`. The caller does not
    need to know whether it is talking to the scraper or the official
    API shim.
    """
    method = entry_data.get(CONF_AUTH_METHOD, AUTH_METHOD_LEGACY)
    if method == AUTH_METHOD_OFFICIAL:
        client = OfficialSmartmeter(
            client_id=entry_data[CONF_CLIENT_ID],
            client_secret=entry_data[CONF_CLIENT_SECRET],
            api_key=entry_data[CONF_API_KEY],
            web_profile_id=entry_data.get(CONF_WEB_PROFILE_ID) or None,
            scope=entry_data.get(CONF_SCOPE) or None,
        )
        return _OfficialSmartmeterShim(
            client=client,
            customer_id=entry_data.get(CONF_CUSTOMER_ID) or None,
        )

    return Smartmeter(
        entry_data[CONF_USERNAME],
        entry_data[CONF_PASSWORD],
    )


@dataclass
class _OfficialSmartmeterShim:
    """Adapt :class:`OfficialSmartmeter` to the legacy Smartmeter surface.

    Only the four methods the sensor and importer actually use are
    implemented:

    * :meth:`login`
    * :meth:`zaehlpunkte` – wrapped into the legacy contract/zaehlpunkte
      nesting expected by :meth:`AsyncSmartmeter.contracts2zaehlpunkte`.
    * :meth:`historical_data` – returns the first matching zaehlwerk
      flattened to a single dict, mirroring the legacy response shape.
    * :meth:`bewegungsdaten` – returns the descriptor/values dict the
      importer consumes.

    Every other legacy method raises :class:`NotImplementedError`.
    """

    client: OfficialSmartmeter
    customer_id: Optional[str] = None
    _zp_cache: Optional[List[Dict[str, Any]]] = field(
        default=None, init=False, repr=False
    )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def login(self) -> str:
        return self.client.login()

    def is_login_expired(self) -> bool:  # pragma: no cover - trivial
        """Match the legacy Smartmeter surface.

        :class:`OfficialSmartmeter` refreshes its token lazily inside
        ``_get``; callers that poll ``is_login_expired`` always see a
        valid token as long as ``login`` has been called at least once.
        """
        token = getattr(self.client, "_token", None)
        return token is None or not token.is_valid()

    # ------------------------------------------------------------------
    # zaehlpunkte()
    # ------------------------------------------------------------------
    def zaehlpunkte(self) -> List[Dict[str, Any]]:
        """Return the list of contracts with nested zaehlpunkte.

        The legacy portal API groups meters by ``geschaeftspartner``
        (contract). The official API returns a flat list, so we wrap
        it in a single synthetic contract. The customer id (if known)
        is propagated so :func:`AsyncSmartmeter.contracts2zaehlpunkte`
        can annotate the children correctly.
        """
        raw = self.client.zaehlpunkte()
        internal = adapter.zaehlpunkte_to_internal(
            raw, customer_id=self.customer_id
        )
        self._zp_cache = internal
        return [
            {
                "geschaeftspartner": self.customer_id,
                "zaehlpunkte": internal,
            }
        ]

    # ------------------------------------------------------------------
    # historical_data()
    # ------------------------------------------------------------------
    def historical_data(
        self,
        zaehlpunktnummer: Optional[str] = None,
        date_from: Optional[Union[datetime, str]] = None,
        date_until: Optional[Union[datetime, str]] = None,
        valuetype: ValueType = ValueType.METER_READ,
    ) -> Dict[str, Any]:
        """Fetch a historical series for a single meter.

        Returns a single dict – not a list – so that downstream
        ``translate_dict(response, ATTRS_HISTORIC_DATA)`` produces the
        ``{obisCode, unitOfMeasurement, values}`` payload the sensor
        expects.
        """
        if not zaehlpunktnummer:
            raise ValueError(
                "historical_data requires a zaehlpunktnummer when using the "
                "official API"
            )
        wertetyp = self._coerce_wertetyp(valuetype)
        raw = self.client.messwerte(
            datum_von=date_from,
            datum_bis=date_until,
            wertetyp=wertetyp,
            zaehlpunkt=zaehlpunktnummer,
        )
        payload = raw if isinstance(raw, dict) else {}
        series = adapter.messwerte_to_historic_data(payload)
        if series:
            # Match the legacy portal behaviour of returning a single
            # series per request. If several zaehlwerke are present the
            # first one is the headline reading.
            return series[0]
        return {"obisCode": None, "einheit": None, "messwerte": []}

    # ------------------------------------------------------------------
    # bewegungsdaten()
    # ------------------------------------------------------------------
    def bewegungsdaten(
        self,
        zaehlpunktnummer: Optional[str] = None,
        date_from: Optional[Union[datetime, str]] = None,
        date_until: Optional[Union[datetime, str]] = None,
        valuetype: ValueType = ValueType.QUARTER_HOUR,
        aggregat: Optional[str] = None,  # noqa: ARG002 - kept for compat
    ) -> Dict[str, Any]:
        """Fetch meter movements for the importer.

        The importer iterates ``values`` and expects ``wert``,
        ``zeitpunktVon`` and ``geschaetzt`` keys – those are emitted by
        ``adapter._messwert_to_internal`` alongside the English aliases.
        """
        if not zaehlpunktnummer:
            raise ValueError(
                "bewegungsdaten requires a zaehlpunktnummer when using the "
                "official API"
            )
        wertetyp = self._coerce_wertetyp(valuetype)
        raw = self.client.messwerte(
            datum_von=date_from,
            datum_bis=date_until,
            wertetyp=wertetyp,
            zaehlpunkt=zaehlpunktnummer,
        )
        payload = raw if isinstance(raw, dict) else {}
        return adapter.messwerte_to_bewegungsdaten(
            payload,
            wertetyp=wertetyp,
            anlagen_typ=self._anlagen_typ_for(zaehlpunktnummer),
            customer_id=self.customer_id,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _anlagen_typ_for(self, zaehlpunkt: str) -> Optional[str]:
        """Best-effort lookup of ``anlage.typ`` for role derivation.

        Falls back to ``None`` (which the adapter treats as
        "consuming") if the list cannot be pre-fetched. This keeps the
        data path resilient when ``zaehlpunkte`` has not been called
        yet – the first call will populate the cache and subsequent
        requests get the correct role.
        """
        if self._zp_cache is None:
            try:
                self.zaehlpunkte()
            except Exception as exc:  # pylint: disable=broad-except
                _LOGGER.debug(
                    "Could not pre-fetch zaehlpunkte while deriving role: %s",
                    exc,
                )
                return None
        for zp in self._zp_cache or []:
            if zp.get("zaehlpunktnummer") == zaehlpunkt:
                return (zp.get("anlage") or {}).get("typ")
        return None

    @staticmethod
    def _coerce_wertetyp(value: Optional[ValueType]) -> Wertetyp:
        if value is None:
            return Wertetyp.QUARTER_HOUR
        return _VALUE_TYPE_TO_WERTETYP.get(value, Wertetyp.QUARTER_HOUR)

    # ------------------------------------------------------------------
    # Unsupported legacy endpoints
    # ------------------------------------------------------------------
    def base_information(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(
            _UNSUPPORTED_MSG.format(method="base_information")
        )

    def verbrauch(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(_UNSUPPORTED_MSG.format(method="verbrauch"))

    def verbrauchRaw(  # noqa: N802 - matches legacy API name
        self, *args: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            _UNSUPPORTED_MSG.format(method="verbrauchRaw")
        )

    def consumptions(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError(
            _UNSUPPORTED_MSG.format(method="consumptions")
        )


__all__ = ["make_client", "_OfficialSmartmeterShim"]
