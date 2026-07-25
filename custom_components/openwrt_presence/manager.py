"""One push connection manager per observer entry."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import ObserverAuthError, ObserverClient, ObserverError
from .const import PROTOCOL_VERSION
from .models import (
    Event,
    IntegrityError,
    ProtocolError,
    parse_client,
    parse_snapshot,
)
from .store import ObserverStore

_LOGGER = logging.getLogger(__name__)

_CLIENT_EVENTS = {"client.updated", "client.presence_changed"}
_NON_CLIENT_EVENTS = {
    "connection.added",
    "connection.removed",
    "provider.status",
    "state.resynchronized",
}


class ConnectionManager:
    """Maintain one ordered observer stream with snapshot recovery."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: ObserverClient,
        store: ObserverStore,
        *,
        on_auth_failed: Callable[[], Awaitable[None]],
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._client = client
        self._store = store
        self._on_auth_failed = on_auth_failed
        self._task: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._stopping = False

    async def async_start(self) -> None:
        """Start the connection loop and wait for its authoritative snapshot."""
        if self._task is not None:
            return
        self._ready = asyncio.get_running_loop().create_future()
        self._task = self._entry.async_create_background_task(
            self._hass,
            self._async_run(),
            f"{self._entry.title} observer stream",
        )
        try:
            async with asyncio.timeout(15):
                await asyncio.shield(self._ready)
        except TimeoutError as err:
            await self.async_stop()
            raise ObserverError("observer stream did not provide a snapshot") from err
        except Exception:
            await self.async_stop()
            raise

    async def async_stop(self) -> None:
        """Stop reconnects and close the active stream."""
        self._stopping = True
        self._store.set_available(False)
        await self._client.async_close()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        if self._ready is not None and not self._ready.done():
            self._ready.cancel()

    async def _async_run(self) -> None:
        delay = 1.0
        while not self._stopping:
            self._store.set_available(False)
            try:
                await self._async_consume_stream()
                if not self._stopping:
                    raise ObserverError("observer stream closed")
            except asyncio.CancelledError:
                raise
            except ObserverAuthError as err:
                self._store.set_available(False)
                if self._set_initial_error(err):
                    return
                _LOGGER.warning(
                    "Authentication failed for observer %s", self._entry.title
                )
                await self._on_auth_failed()
                return
            except (ObserverError, ProtocolError, IntegrityError) as err:
                if self._set_initial_error(err):
                    return
                if not self._stopping:
                    _LOGGER.warning(
                        "Observer %s stream lost integrity: %s",
                        self._entry.title,
                        err,
                    )
            self._store.set_available(False)
            if self._stopping:
                return
            await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
            delay = min(delay * 2, 60)

    async def _async_consume_stream(self) -> None:
        saw_hello = False
        saw_snapshot = False
        async for event in self._client.async_stream():
            if not saw_hello:
                self._validate_hello(event)
                saw_hello = True
                continue
            if not saw_snapshot:
                if event.type != "state.snapshot":
                    raise IntegrityError("stream did not begin with a snapshot")
                snapshot = parse_snapshot(event.data)
                if (
                    snapshot.stream_epoch != event.stream_epoch
                    or snapshot.sequence != event.sequence
                ):
                    raise IntegrityError("snapshot envelope does not match payload")
                self._store.apply_snapshot(snapshot, available=True)
                if self._ready is not None and not self._ready.done():
                    self._ready.set_result(None)
                saw_snapshot = True
                continue
            self._apply_event(event)
        if not saw_snapshot:
            raise IntegrityError("stream closed before authoritative snapshot")

    def _set_initial_error(self, err: Exception) -> bool:
        """Fail config-entry setup before the first authoritative snapshot."""
        if self._ready is None or self._ready.done():
            return False
        self._ready.set_exception(err)
        return True

    @staticmethod
    def _validate_hello(event: Event) -> None:
        if event.type != "stream.hello" or not isinstance(event.data, dict):
            raise IntegrityError("stream did not begin with hello")
        if event.data.get("protocol_version") != PROTOCOL_VERSION:
            raise IntegrityError("stream protocol version changed")
        if event.data.get("replay") is not False:
            raise IntegrityError("unexpected replay capability")

    def _apply_event(self, event: Event) -> None:
        epoch = self._store.stream_epoch
        sequence = self._store.sequence
        if epoch is None or sequence is None:
            raise IntegrityError("event received without a snapshot")
        if event.type == "stream.heartbeat":
            if event.stream_epoch != epoch or event.sequence != sequence:
                raise IntegrityError("heartbeat does not match current state")
            return
        if event.type in ("stream.hello", "state.snapshot", "stream.shutdown"):
            raise IntegrityError("unexpected stream control event")
        if event.stream_epoch != epoch:
            raise IntegrityError("stream epoch changed")
        if event.sequence <= sequence:
            return
        if event.sequence != sequence + 1:
            raise IntegrityError("stream sequence gap")

        if event.type in _CLIENT_EVENTS:
            client = parse_client(event.data)
            self._store.update_client(client, event.sequence)
            return
        if event.type == "client.removed":
            client = parse_client(event.data)
            self._store.remove_client(client.id, event.sequence)
            return
        if event.type in _NON_CLIENT_EVENTS:
            self._store.advance(event.sequence)
            return
        raise IntegrityError(f"unknown state event {event.type!r}")
