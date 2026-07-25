"""In-memory observer state and targeted subscriptions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from homeassistant.core import callback

from .models import Client, Snapshot

Listener = Callable[[], None]
NewClientListener = Callable[[str], None]


@dataclass(slots=True)
class ObserverStore:
    """Authoritative state for one observer config entry."""

    clients: dict[str, Client] = field(default_factory=dict)
    stream_epoch: str | None = None
    sequence: int | None = None
    available: bool = False
    _client_listeners: dict[str, set[Listener]] = field(default_factory=dict)
    _availability_listeners: set[Listener] = field(default_factory=set)
    _new_client_listeners: set[NewClientListener] = field(default_factory=set)

    @callback
    def apply_snapshot(self, snapshot: Snapshot, *, available: bool) -> None:
        """Atomically replace state and notify only changed clients."""
        previous = self.clients
        current = {client.id: client for client in snapshot.clients}
        self.clients = current
        self.stream_epoch = snapshot.stream_epoch
        self.sequence = snapshot.sequence

        for client_id in current.keys() - previous.keys():
            for listener in tuple(self._new_client_listeners):
                listener(client_id)

        changed_ids = {
            client_id
            for client_id in current.keys() | previous.keys()
            if current.get(client_id) != previous.get(client_id)
        }
        for client_id in changed_ids:
            self._notify_client(client_id)
        self.set_available(available)

    @callback
    def update_client(self, client: Client, sequence: int) -> None:
        """Apply one validated event immediately."""
        is_new = client.id not in self.clients
        changed = self.clients.get(client.id) != client
        self.clients[client.id] = client
        self.sequence = sequence
        if is_new:
            for listener in tuple(self._new_client_listeners):
                listener(client.id)
        if changed:
            self._notify_client(client.id)

    @callback
    def remove_client(self, client_id: str, sequence: int) -> None:
        """Remove evicted source state while retaining registry identity."""
        if self.clients.pop(client_id, None) is not None:
            self._notify_client(client_id)
        self.sequence = sequence

    @callback
    def advance(self, sequence: int) -> None:
        """Advance after a known event without client state data."""
        self.sequence = sequence

    @callback
    def set_available(self, available: bool) -> None:
        """Set transport integrity availability."""
        if self.available == available:
            return
        self.available = available
        for listener in tuple(self._availability_listeners):
            listener()

    @callback
    def subscribe_client(
        self, client_id: str, listener: Listener
    ) -> Callable[[], None]:
        """Subscribe to changes for one client."""
        listeners = self._client_listeners.setdefault(client_id, set())
        listeners.add(listener)

        @callback
        def unsubscribe() -> None:
            listeners.discard(listener)
            if not listeners:
                self._client_listeners.pop(client_id, None)

        return unsubscribe

    @callback
    def subscribe_availability(self, listener: Listener) -> Callable[[], None]:
        """Subscribe to observer availability."""
        self._availability_listeners.add(listener)
        return lambda: self._availability_listeners.discard(listener)

    @callback
    def subscribe_new_clients(self, listener: NewClientListener) -> Callable[[], None]:
        """Subscribe to dynamically observed clients."""
        self._new_client_listeners.add(listener)
        return lambda: self._new_client_listeners.discard(listener)

    @callback
    def _notify_client(self, client_id: str) -> None:
        for listener in tuple(self._client_listeners.get(client_id, ())):
            listener()
