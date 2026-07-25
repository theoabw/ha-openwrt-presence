"""Bounded HTTP and WebSocket client for the observer protocol."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from aiohttp import (
    ClientConnectionError,
    ClientResponse,
    ClientSession,
    ClientSSLError,
    ClientWebSocketResponse,
    ClientWSTimeout,
    ServerTimeoutError,
    WSMsgType,
    WSServerHandshakeError,
)
from yarl import URL

from .const import MAX_EVENT_BYTES, MAX_RESPONSE_BYTES
from .models import (
    Event,
    ObserverInfo,
    ProtocolError,
    Snapshot,
    parse_event,
    parse_info,
    parse_snapshot,
)


class ObserverError(Exception):
    """Base transport error."""


class ObserverConnectionError(ObserverError):
    """The observer could not be reached."""


class ObserverAuthError(ObserverError):
    """Observer authentication failed."""


class ObserverTLSError(ObserverConnectionError):
    """TLS connection or certificate validation failed."""


class ObserverNotReadyError(ObserverError):
    """The observer has no authoritative state yet."""


class ObserverResponseError(ObserverError):
    """The observer returned an invalid response."""


def validate_host(host: str) -> str:
    """Validate a host without accepting URL syntax or credentials."""
    normalized = host.strip()
    if (
        not normalized
        or len(normalized) > 253
        or normalized != host
        or any(char in normalized for char in "/@?#\\")
        or "://" in normalized
        or any(char.isspace() for char in normalized)
    ):
        raise ValueError("invalid host")
    try:
        URL.build(scheme="http", host=normalized, port=1)
    except ValueError as err:
        raise ValueError("invalid host") from err
    return normalized


class ObserverClient:
    """Read-only observer API client."""

    def __init__(
        self,
        session: ClientSession,
        *,
        host: str,
        port: int,
        token: str,
        use_ssl: bool,
        verify_ssl: bool,
    ) -> None:
        """Initialize the client without performing I/O."""
        self._session = session
        self._host = validate_host(host)
        self._port = port
        self._token = token
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl
        scheme = "https" if use_ssl else "http"
        self._base_url = URL.build(scheme=scheme, host=self._host, port=port)
        self._ws: ClientWebSocketResponse | None = None

    @property
    def base_url(self) -> str:
        """Return a credential-free base URL."""
        return str(self._base_url)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    @property
    def _ssl(self) -> bool:
        return self._verify_ssl

    async def async_get_info(self) -> ObserverInfo:
        """Fetch stable identity and protocol capabilities."""
        return parse_info(await self._async_get_json("/v1/info"))

    async def async_get_snapshot(self) -> Snapshot:
        """Fetch authoritative client state."""
        return parse_snapshot(await self._async_get_json("/v1/clients"))

    async def _async_get_json(self, path: str) -> Any:
        url = self._base_url.with_path(path)
        try:
            async with asyncio.timeout(10):
                response = await self._session.get(
                    url,
                    headers=self._headers,
                    allow_redirects=False,
                    ssl=self._ssl,
                )
                async with response:
                    self._raise_for_status(response)
                    payload = await self._read_bounded(response)
        except ObserverError:
            raise
        except ClientSSLError as err:
            raise ObserverTLSError("TLS validation failed") from err
        except (
            TimeoutError,
            ClientConnectionError,
            ServerTimeoutError,
        ) as err:
            raise ObserverConnectionError("observer connection failed") from err
        try:
            return json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ObserverResponseError("observer returned invalid JSON") from err

    @staticmethod
    def _raise_for_status(response: ClientResponse) -> None:
        if response.status in (401, 403):
            raise ObserverAuthError("authentication failed")
        if response.status == 503:
            raise ObserverNotReadyError("observer is not ready")
        if response.status != 200:
            raise ObserverResponseError(
                f"observer returned unexpected HTTP status {response.status}"
            )
        content_type = response.headers.get("Content-Type", "")
        if not content_type.lower().startswith("application/json"):
            raise ObserverResponseError("observer returned unexpected content type")

    @staticmethod
    async def _read_bounded(response: ClientResponse) -> bytes:
        length = response.content_length
        if length is not None and length > MAX_RESPONSE_BYTES:
            raise ObserverResponseError("observer response is too large")
        payload = await response.content.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ObserverResponseError("observer response is too large")
        return payload

    async def async_stream(self) -> AsyncIterator[Event]:
        """Yield validated WebSocket event envelopes."""
        url = self._base_url.with_scheme("wss" if self._use_ssl else "ws").with_path(
            "/v1/events"
        )
        try:
            async with asyncio.timeout(10):
                ws = await self._session.ws_connect(
                    url,
                    headers=self._headers,
                    ssl=self._ssl,
                    heartbeat=30,
                    timeout=ClientWSTimeout(ws_receive=75),
                    max_msg_size=MAX_EVENT_BYTES,
                )
            if ws._response.history:
                await ws.close()
                raise ObserverResponseError("observer stream redirected unexpectedly")
            self._ws = ws
            async with ws:
                async for message in ws:
                    if message.type is WSMsgType.TEXT:
                        try:
                            raw = json.loads(message.data)
                            yield parse_event(raw)
                        except (json.JSONDecodeError, ProtocolError) as err:
                            raise ObserverResponseError(
                                "observer returned an invalid event"
                            ) from err
                    elif message.type in (
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSED,
                        WSMsgType.ERROR,
                    ):
                        break
                    elif message.type is not WSMsgType.PING:
                        raise ObserverResponseError(
                            "observer returned an unsupported WebSocket message"
                        )
                if ws.exception() is not None:
                    raise ObserverConnectionError("observer stream failed")
        except ObserverError:
            raise
        except WSServerHandshakeError as err:
            if err.status in (401, 403):
                raise ObserverAuthError("stream authentication failed") from err
            raise ObserverConnectionError("observer stream handshake failed") from err
        except ClientSSLError as err:
            raise ObserverTLSError("stream TLS validation failed") from err
        except (
            TimeoutError,
            ClientConnectionError,
            ServerTimeoutError,
        ) as err:
            raise ObserverConnectionError("observer stream failed") from err
        finally:
            self._ws = None

    async def async_close(self) -> None:
        """Close the active stream."""
        if self._ws is not None:
            await self._ws.close()
