"""Client for the official Wiener Netze Smart Meter API (WN_SMART_METER_API).

This module talks to the public, OAuth2-secured gateway documented at
``https://api-portal.wienerstadtwerke.at``. The endpoints and schemas are
defined by the ``WN_SMART_METER_API`` OpenAPI specification:

- ``GET /zaehlpunkte``
- ``GET /zaehlpunkte/{zaehlpunkt}``
- ``GET /zaehlpunkte/messwerte``
- ``GET /zaehlpunkte/{zaehlpunkt}/messwerte``

Unlike :mod:`wnsm.api.client`, no HTML scraping is required: a
``client_credentials`` token exchange is enough to obtain a bearer token.
Every request additionally carries the per-application ``x-Gateway-APIKey``
header issued by Wiener Netze.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Union
from urllib.parse import urljoin

import requests

from . import constants as const
from .errors import (
    SmartmeterConnectionError,
    SmartmeterLoginError,
    SmartmeterQueryError,
)

logger = logging.getLogger(__name__)

# Types accepted for the ``datumVon`` / ``datumBis`` parameters. ``str`` is
# passed through unchanged to allow callers to supply vendor-specific
# formats (e.g. datetimes including a time component) when needed.
DateLike = Union[str, date, datetime]

# The only grant type we use. The Wiener Netze gateway (webMethods) accepts
# client_credentials on the ``getAccessToken`` endpoint when the application
# has been configured with a client_id/secret pair in the portal.
_GRANT_TYPE: str = "client_credentials"


@dataclass
class _Token:
    """In-memory representation of a cached OAuth2 access token."""

    access_token: str
    expires_at: float  #: monotonic epoch seconds at which the token expires

    def is_valid(self, leeway: int = const.OFFICIAL_TOKEN_REFRESH_LEEWAY_SECONDS) -> bool:
        return bool(self.access_token) and (time.time() + leeway) < self.expires_at


@dataclass
class OfficialSmartmeter:
    """Thin wrapper around the official Wiener Netze Smart Meter API.

    The client is intentionally synchronous so that it can be used from the
    Home Assistant executor (``hass.async_add_executor_job``) just like the
    existing :class:`wnsm.api.client.Smartmeter`.

    Parameters
    ----------
    client_id, client_secret:
        OAuth2 credentials from the Wiener Netze API developer portal.
    api_key:
        The ``x-Gateway-APIKey`` value assigned to the application.
    web_profile_id:
        Optional default ``webProfileId`` passed as a query parameter to
        every resource call. Leave ``None`` to omit it.
    scope:
        OAuth2 scope to request. Defaults to ``profile`` which is the scope
        shown in the Wiener Netze portal.
    base_url / token_url:
        Overrides primarily useful in tests.
    session:
        Optional :class:`requests.Session` to reuse an external connection
        pool. A fresh session is created if omitted.
    """

    client_id: str
    client_secret: str
    api_key: str
    web_profile_id: Optional[str] = None
    # Scope is intentionally optional and defaults to *None* – the
    # reference wrapper at
    # https://github.com/tschoerk/Wiener-Netze-Smart-Meter-API omits the
    # scope field entirely, and issue #276 in this repo shows that the
    # gateway rejects ``scope=profile`` for apps that were not explicitly
    # provisioned with it ("The supplied scope (profile) is not
    # associated with the client"). Users whose apps *do* require a
    # scope can still set it via the config flow.
    scope: Optional[str] = None
    base_url: str = const.OFFICIAL_API_URL
    token_url: str = const.OFFICIAL_TOKEN_URL
    timeout: float = 30.0
    session: requests.Session = field(default_factory=requests.Session)
    _token: Optional[_Token] = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def login(self) -> str:
        """Obtain an access token via the client_credentials grant.

        Returns the raw bearer token. Raises :class:`SmartmeterLoginError`
        on any non-2xx response or malformed payload.
        """
        data: Dict[str, str] = {
            "grant_type": _GRANT_TYPE,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if self.scope:
            data["scope"] = self.scope

        try:
            response = self.session.post(
                self.token_url,
                data=data,
                headers={
                    "Accept": "application/json",
                    # ``requests`` sets this implicitly when ``data`` is
                    # a dict, but the Wiener Netze gateway is strict –
                    # set it explicitly so intermediate proxies cannot
                    # strip or rewrite the content type.
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SmartmeterConnectionError(
                f"Could not reach token endpoint: {exc}"
            ) from exc

        if response.status_code != 200:
            raise SmartmeterLoginError(
                "OAuth2 token request failed",
                code=response.status_code,
                error_response=response.text,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SmartmeterLoginError(
                f"OAuth2 token response was not valid JSON: {exc}",
                error_response=response.text,
            ) from exc

        access_token = payload.get("access_token")
        if not access_token:
            raise SmartmeterLoginError(
                "OAuth2 token response did not contain an access_token",
                error_response=response.text,
            )

        # ``expires_in`` is expressed in seconds according to RFC 6749 and
        # webMethods honours that. Fall back to the documented default if
        # the server omits it.
        expires_in = int(
            payload.get("expires_in") or const.OFFICIAL_TOKEN_VALIDITY_SECONDS
        )
        self._token = _Token(
            access_token=access_token,
            expires_at=time.time() + expires_in,
        )
        logger.debug(
            "Obtained official API token, expires in %ss (scope=%s)",
            expires_in,
            payload.get("scope", self.scope),
        )
        return access_token

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing it transparently."""
        if self._token is None or not self._token.is_valid():
            self.login()
        assert self._token is not None  # for type checkers
        return self._token.access_token

    # ------------------------------------------------------------------
    # Low-level request plumbing
    # ------------------------------------------------------------------
    def _get(
        self,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """GET ``path`` on the official API, returning the decoded JSON."""
        token = self._ensure_token()

        # ``urljoin`` only concatenates correctly when the base ends with a
        # trailing slash, so we normalise explicitly rather than relying on
        # the caller to get the slashes right.
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

        params: Dict[str, Any] = {}
        if self.web_profile_id:
            params["webProfileId"] = self.web_profile_id
        if query:
            # Callers win over the default profile id if they pass one.
            params.update({k: v for k, v in query.items() if v is not None})

        headers = {
            "Authorization": f"Bearer {token}",
            "x-Gateway-APIKey": self.api_key,
            "Accept": "application/json",
        }

        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise SmartmeterConnectionError(
                f"Failed to call {url}: {exc}"
            ) from exc

        if response.status_code == 401:
            # Token might have been revoked out-of-band. Force a refresh
            # once and retry; any further 401 is a genuine auth error.
            logger.info("Official API returned 401, refreshing token and retrying")
            self._token = None
            token = self._ensure_token()
            headers["Authorization"] = f"Bearer {token}"
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise SmartmeterConnectionError(
                    f"Failed to retry {url}: {exc}"
                ) from exc

        if response.status_code != 200:
            raise SmartmeterQueryError(
                f"Unexpected status {response.status_code} from {url}",
                code=response.status_code,
                error_response=response.text,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise SmartmeterQueryError(
                f"Response from {url} was not valid JSON: {exc}",
                error_response=response.text,
            ) from exc

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------
    def zaehlpunkte(
        self,
        *,
        zaehlpunkt: Optional[str] = None,
        result_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """``GET /zaehlpunkte`` – list all meters for the authenticated customer.

        The OpenAPI spec models the response as ``{"items": Zaehlpunkt}``
        but in practice the gateway returns a JSON array of
        :class:`Zaehlpunkt` objects. We accept both and always return a
        plain list to simplify downstream consumers.
        """
        query: Dict[str, Any] = {}
        if zaehlpunkt:
            query["zaehlpunkt"] = zaehlpunkt
        if result_type:
            query["resultType"] = result_type

        raw = self._get("zaehlpunkte", query=query)
        return _as_list(raw)

    def zaehlpunkt(self, zaehlpunkt: str) -> Dict[str, Any]:
        """``GET /zaehlpunkte/{zaehlpunkt}`` – details for a single meter."""
        if not zaehlpunkt:
            raise ValueError("zaehlpunkt must be a non-empty string")
        return self._get(f"zaehlpunkte/{zaehlpunkt}")

    def messwerte(
        self,
        datum_von: DateLike,
        datum_bis: DateLike,
        wertetyp: Union[const.Wertetyp, str],
        *,
        zaehlpunkt: Optional[str] = None,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetch measurement values.

        Calls ``GET /zaehlpunkte/{zaehlpunkt}/messwerte`` when a specific
        meter is supplied, otherwise the bulk ``GET /zaehlpunkte/messwerte``
        endpoint. The ``datumVon`` / ``datumBis`` parameters are formatted as
        ``YYYY-MM-DD`` when a date/datetime is passed; plain strings are
        forwarded unchanged so callers can opt into a different format.
        """
        query: Dict[str, Any] = {
            "datumVon": _format_date(datum_von),
            "datumBis": _format_date(datum_bis),
            "wertetyp": _coerce_wertetyp(wertetyp),
        }

        if zaehlpunkt:
            return self._get(
                f"zaehlpunkte/{zaehlpunkt}/messwerte",
                query=query,
            )

        raw = self._get("zaehlpunkte/messwerte", query=query)
        # The bulk endpoint returns either ``{"items": ...}`` or a raw
        # array; normalise to a list for the caller.
        return _as_list(raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _format_date(value: DateLike) -> str:
    """Format a date/datetime/string as ``YYYY-MM-DD``.

    Strings are returned unchanged to keep the door open for callers who
    need to supply an ISO 8601 datetime.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.date().strftime(const.OFFICIAL_API_DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(const.OFFICIAL_API_DATE_FORMAT)
    raise TypeError(
        f"datumVon/datumBis must be str, date or datetime, got {type(value).__name__}"
    )


def _coerce_wertetyp(value: Union[const.Wertetyp, str]) -> str:
    if isinstance(value, const.Wertetyp):
        return value.value
    return const.Wertetyp.from_str(value).value


def _as_list(raw: Any) -> List[Dict[str, Any]]:
    """Normalise the API's ``items`` / bare-array duality to a list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        items = raw.get("items")
        if items is None:
            # Some variants wrap a single object instead of an array.
            return [raw]
        if isinstance(items, list):
            return items
        return [items]
    # Anything else is unexpected but we refuse to silently discard it.
    raise SmartmeterQueryError(
        f"Unexpected payload type from official API: {type(raw).__name__}"
    )


__all__ = ["OfficialSmartmeter"]
