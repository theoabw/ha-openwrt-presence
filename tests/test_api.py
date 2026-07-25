"""Tests for bounded HTTP and WebSocket transport behavior."""

from collections.abc import AsyncIterator

import pytest
from aiohttp import ClientSession, web

from custom_components.openwrt_presence.api import (
    ObserverAuthError,
    ObserverClient,
    ObserverConnectionError,
    ObserverNotReadyError,
    ObserverResponseError,
    validate_host,
)
from custom_components.openwrt_presence.const import MAX_RESPONSE_BYTES

from .helpers import TOKEN, event, info, snapshot

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def client_for_server(server, session: ClientSession) -> ObserverClient:
    """Build a client for one aiohttp test server."""
    return ObserverClient(
        session,
        host=server.host,
        port=server.port,
        token=TOKEN,
        use_ssl=False,
        verify_ssl=True,
    )


@pytest.mark.parametrize(
    "host",
    [
        "",
        " router.local",
        "router.local ",
        "http://router.local",
        "user@router.local",
        "router.local/path",
        "router local",
    ],
)
def test_validate_host_rejects_url_and_credential_syntax(host: str) -> None:
    """Host input cannot smuggle paths, schemes, or credentials."""
    with pytest.raises(ValueError):
        validate_host(host)


async def test_http_info_and_snapshot(aiohttp_server) -> None:
    """Successful reads authenticate and parse bounded protocol payloads."""

    async def get_info(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return web.json_response(info())

    async def get_snapshot(_request: web.Request) -> web.Response:
        return web.json_response(snapshot())

    app = web.Application()
    app.router.add_get("/v1/info", get_info)
    app.router.add_get("/v1/clients", get_snapshot)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        parsed_info = await client.async_get_info()
        parsed_snapshot = await client.async_get_snapshot()

    assert parsed_info.agent_id == info()["agent_id"]
    assert parsed_snapshot.sequence == 4


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, ObserverAuthError),
        (403, ObserverAuthError),
        (503, ObserverNotReadyError),
        (500, ObserverResponseError),
    ],
)
async def test_http_status_mapping(
    aiohttp_server, status: int, error: type[Exception]
) -> None:
    """HTTP failures retain actionable transport categories."""

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(status=status)

    app = web.Application()
    app.router.add_get("/v1/info", handler)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        with pytest.raises(error):
            await client.async_get_info()


@pytest.mark.parametrize(
    ("case", "content_type"),
    [
        ("invalid_json", "application/json"),
        ("wrong_type", "text/plain"),
        ("oversized", "application/json"),
    ],
)
async def test_http_rejects_invalid_or_oversized_payloads(
    aiohttp_server, case: str, content_type: str
) -> None:
    """Malformed, mislabeled, and oversized responses stay bounded."""
    body = {
        "invalid_json": b"not json",
        "wrong_type": b"{}",
        "oversized": b"x" * (MAX_RESPONSE_BYTES + 1),
    }[case]

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(body=body, content_type=content_type)

    app = web.Application()
    app.router.add_get("/v1/info", handler)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        with pytest.raises(ObserverResponseError):
            await client.async_get_info()


async def test_websocket_yields_valid_events(aiohttp_server) -> None:
    """Text frames are parsed into validated event envelopes."""

    async def handler(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_json(
            event(
                "stream.hello",
                4,
                data={"protocol_version": "v1", "replay": False},
            )
        )
        await socket.close()
        return socket

    app = web.Application()
    app.router.add_get("/v1/events", handler)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        events = [item async for item in client.async_stream()]

    assert [item.type for item in events] == ["stream.hello"]


async def test_websocket_rejects_binary_frames(aiohttp_server) -> None:
    """Unexpected WebSocket frame types cannot bypass protocol parsing."""

    async def handler(request: web.Request) -> web.WebSocketResponse:
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_bytes(b"not a protocol event")
        await socket.close()
        return socket

    app = web.Application()
    app.router.add_get("/v1/events", handler)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        stream: AsyncIterator = client.async_stream()
        with pytest.raises(ObserverResponseError):
            await anext(stream)


async def test_websocket_auth_failure_is_actionable(aiohttp_server) -> None:
    """A rejected WebSocket handshake starts reauthentication."""

    async def handler(_request: web.Request) -> web.Response:
        return web.Response(status=401)

    app = web.Application()
    app.router.add_get("/v1/events", handler)
    server = await aiohttp_server(app)
    async with ClientSession() as session:
        client = await client_for_server(server, session)
        with pytest.raises(ObserverAuthError):
            await anext(client.async_stream())


async def test_connection_failure_is_normalized(unused_tcp_port: int) -> None:
    """Low-level connection errors do not leak through the API boundary."""
    async with ClientSession() as session:
        client = ObserverClient(
            session,
            host="127.0.0.1",
            port=unused_tcp_port,
            token=TOKEN,
            use_ssl=False,
            verify_ssl=True,
        )
        with pytest.raises(ObserverConnectionError):
            await client.async_get_info()
