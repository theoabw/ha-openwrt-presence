"""Tests for stream ordering and recovery behavior."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.openwrt_presence.api import ObserverAuthError
from custom_components.openwrt_presence.manager import ConnectionManager
from custom_components.openwrt_presence.models import (
    IntegrityError,
    parse_event,
    parse_snapshot,
)
from custom_components.openwrt_presence.store import ObserverStore

from .helpers import EPOCH, client, event, snapshot


def manager_with_store() -> tuple[ConnectionManager, ObserverStore]:
    """Construct a manager for direct event integrity tests."""
    store = ObserverStore()
    store.apply_snapshot(parse_snapshot(snapshot()), available=True)
    manager = cast(
        ConnectionManager,
        object.__new__(ConnectionManager),
    )
    manager._store = store
    return manager, store


def test_presence_event_applies_immediately() -> None:
    """A valid presence-changing event updates state in the same callback."""
    manager, store = manager_with_store()
    manager._apply_event(
        parse_event(event("client.presence_changed", 5, data=client("absent")))
    )

    assert store.sequence == 5
    assert next(iter(store.clients.values())).state == "absent"


@pytest.mark.parametrize(
    "raw",
    [
        event("client.presence_changed", 6, data=client("absent")),
        event(
            "client.presence_changed",
            5,
            data=client("absent"),
            epoch="11111111111111111111111111111111",
        ),
        event("future.state_event", 5, data={}),
    ],
)
def test_gap_epoch_and_unknown_event_require_snapshot(raw: dict) -> None:
    """Any ambiguous stream change pauses normal event application."""
    manager, _ = manager_with_store()
    with pytest.raises(IntegrityError):
        manager._apply_event(parse_event(raw))


def test_duplicate_is_ignored() -> None:
    """A duplicate event cannot roll state backward."""
    manager, store = manager_with_store()
    manager._apply_event(
        parse_event(event("client.presence_changed", 4, data=client("absent")))
    )
    assert next(iter(store.clients.values())).state == "present"
    assert store.stream_epoch == EPOCH


async def test_start_waits_for_stream_snapshot(hass) -> None:
    """The WebSocket snapshot bootstraps state without an HTTP snapshot."""
    stream_events = [
        parse_event(
            event(
                "stream.hello",
                4,
                data={"protocol_version": "v1", "replay": False},
            )
        ),
        parse_event(event("state.snapshot", 4, data=snapshot())),
    ]
    release = asyncio.Event()

    async def stream():
        for item in stream_events:
            yield item
        await release.wait()

    entry = MagicMock()
    entry.title = "Observer"
    entry.async_create_background_task.side_effect = lambda _hass, coroutine, _name: (
        asyncio.create_task(coroutine)
    )
    store = ObserverStore()
    api = MagicMock()
    api.async_stream = stream
    api.async_close = AsyncMock()
    manager = ConnectionManager(
        hass,
        entry,
        api,
        store,
        on_auth_failed=AsyncMock(),
    )

    await manager.async_start()

    assert store.available
    assert store.sequence == 4
    assert next(iter(store.clients.values())).state == "present"
    release.set()
    await manager.async_stop()


async def test_invalid_initial_stream_cleans_up(hass) -> None:
    """Setup failure closes transport and leaves no background task."""

    async def stream():
        yield parse_event(event("client.updated", 1, data=client()))

    entry = MagicMock()
    entry.title = "Observer"
    entry.async_create_background_task.side_effect = lambda _hass, coroutine, _name: (
        asyncio.create_task(coroutine)
    )
    api = MagicMock()
    api.async_stream = stream
    api.async_close = AsyncMock()
    manager = ConnectionManager(
        hass,
        entry,
        api,
        ObserverStore(),
        on_auth_failed=AsyncMock(),
    )

    with pytest.raises(IntegrityError):
        await manager.async_start()

    api.async_close.assert_awaited()
    assert manager._task is None


async def test_auth_failure_after_start_requests_reauthentication(hass) -> None:
    """Authentication loss after setup invokes the config-entry flow."""
    release = asyncio.Event()

    async def stream():
        yield parse_event(
            event(
                "stream.hello",
                4,
                data={"protocol_version": "v1", "replay": False},
            )
        )
        yield parse_event(event("state.snapshot", 4, data=snapshot()))
        await release.wait()
        raise ObserverAuthError
        yield  # pragma: no cover

    entry = MagicMock()
    entry.title = "Observer"
    entry.async_create_background_task.side_effect = lambda _hass, coroutine, _name: (
        asyncio.create_task(coroutine)
    )
    api = MagicMock()
    api.async_stream = stream
    api.async_close = AsyncMock()
    reauthenticate = AsyncMock()
    manager = ConnectionManager(
        hass,
        entry,
        api,
        ObserverStore(),
        on_auth_failed=reauthenticate,
    )

    await manager.async_start()
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    reauthenticate.assert_awaited_once()
    assert not manager._store.available
    await manager.async_stop()
