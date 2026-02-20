"""
client.py — Low-level, HMAC-SHA256-signed REST client for Binance Futures Testnet.

Responsibilities
----------------
* Build the correct endpoint URL for every request.
* Inject ``timestamp``, ``recvWindow``, and ``signature`` into every
  private (signed) request automatically.
* Log every outgoing request and incoming response at DEBUG level.
* Translate non-2xx responses into a typed :class:`BinanceAPIError`.
* Translate network failures into a typed :class:`NetworkError`.

All other modules depend on this layer — they must not import ``requests``
directly.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from config import Config, config as _default_config
from logger import get_logger

log = get_logger("client")


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class BinanceAPIError(Exception):
    """Raised when the Binance REST API returns a non-2xx HTTP status."""

    def __init__(self, code: int | str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class NetworkError(Exception):
    """Raised on connection timeouts, DNS failures, and other transport errors."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class BinanceFuturesClient:
    """
    Thread-safe, stateless HTTP client for Binance USDT-M Futures Testnet.

    A single :class:`requests.Session` is reused for connection pooling.
    The ``X-MBX-APIKEY`` header is set once at construction time.
    """

    def __init__(self, cfg: Config = _default_config) -> None:
        cfg.validate()
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-MBX-APIKEY": cfg.api_key,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
        )
        log.debug(
            "BinanceFuturesClient ready  base_url=%s  recv_window=%s ms",
            cfg.base_url,
            cfg.recv_window,
        )

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1_000)

    def _sign(self, params: dict) -> dict:
        """
        Clone *params*, add ``timestamp`` / ``recvWindow``, then compute and
        append the HMAC-SHA256 ``signature``.  Returns the augmented dict.
        """
        params = dict(params)
        params["timestamp"] = self._now_ms()
        params["recvWindow"] = self._cfg.recv_window
        payload = urlencode(params)
        sig = hmac.new(
            self._cfg.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    def _url(self, path: str, *, v2: bool = False) -> str:
        api_path = self._cfg.fapi_v2 if v2 else self._cfg.fapi_v1
        return f"{self._cfg.base_url}{api_path}{path}"

    def _parse(self, response: requests.Response) -> Any:
        """
        Parse JSON from *response*.

        Raises :class:`BinanceAPIError` for any non-2xx status.
        Logs the raw request/response at DEBUG level for the log file.
        """
        # Structured debug log — goes to file only (INFO threshold on console)
        log.debug(
            ">>> %s %s  params=%s",
            response.request.method,
            response.url,
            response.request.body or "",
        )
        log.debug(
            "<<< HTTP %s  body=%s",
            response.status_code,
            response.text[:400],
        )

        try:
            data = response.json()
        except ValueError:
            data = {"msg": response.text, "code": response.status_code}

        if not response.ok:
            if isinstance(data, dict):
                code = data.get("code", response.status_code)
                msg  = data.get("msg", "Unknown error")
            else:
                code, msg = response.status_code, str(data)
            log.error("Binance API error  code=%s  msg=%s", code, msg)
            raise BinanceAPIError(code, msg)

        return data

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        signed: bool = False,
        v2: bool = False,
    ) -> Any:
        """
        Generic request dispatcher.  All public methods delegate here.

        Converts :class:`requests.exceptions.RequestException` sub-classes
        into :class:`NetworkError` so callers only need two ``except`` clauses.
        """
        p = params or {}
        d = data or {}
        if signed:
            # For DELETE/GET the signature goes in query params;
            # for POST the entire signed payload goes in the request body.
            if method in ("GET", "DELETE"):
                p = self._sign({**p, **d})
                d = {}
            else:
                d = self._sign({**p, **d})
                p = {}

        url = self._url(path, v2=v2)
        try:
            resp = self._session.request(
                method,
                url,
                params=p,
                data=d,
                timeout=self._cfg.timeout,
            )
        except ReadTimeout as exc:
            log.error("Request timed out: %s", exc)
            raise NetworkError(f"Request timed out after {self._cfg.timeout}s") from exc
        except ConnectionError as exc:
            log.error("Connection error: %s", exc)
            raise NetworkError(f"Connection failed: {exc}") from exc
        except RequestException as exc:
            log.error("Network error: %s", exc)
            raise NetworkError(str(exc)) from exc

        return self._parse(resp)

    # ── Public API ───────────────────────────────────────────────────────────

    def get(
        self,
        path: str,
        params: dict | None = None,
        *,
        signed: bool = False,
        v2: bool = False,
    ) -> Any:
        return self._request("GET", path, params=params, signed=signed, v2=v2)

    def post(
        self,
        path: str,
        data: dict | None = None,
        *,
        v2: bool = False,
    ) -> Any:
        return self._request("POST", path, data=data, signed=True, v2=v2)

    def delete(
        self,
        path: str,
        params: dict | None = None,
        *,
        v2: bool = False,
    ) -> Any:
        return self._request("DELETE", path, params=params, signed=True, v2=v2)
