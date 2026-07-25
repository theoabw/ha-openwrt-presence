"""Validated observer protocol models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .const import (
    MAX_CLIENTS,
    MAX_CONNECTIONS_PER_CLIENT,
    MAX_STRING_LENGTH,
    PROTOCOL_VERSION,
)

type PresenceState = Literal["present", "absent", "unknown"]

_AGENT_ID = re.compile(r"^[0-9a-f]{32}$")
_CLIENT_ID = re.compile(r"^mac:[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")


class ProtocolError(Exception):
    """Base exception for invalid observer protocol data."""


class UnsupportedObserverError(ProtocolError):
    """The endpoint is not a supported observer."""


class IntegrityError(ProtocolError):
    """Stream state can no longer be trusted."""


@dataclass(frozen=True, slots=True)
class ObserverInfo:
    """Stable observer identity and capabilities."""

    agent_id: str
    version: str
    capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class Connection:
    """One client connection reported by an observer."""

    id: str
    provider: str
    source_instance: str
    connected_at: datetime
    last_seen_at: datetime
    stale: bool


@dataclass(frozen=True, slots=True)
class Client:
    """One source-specific observed client."""

    id: str
    state: PresenceState
    connections: tuple[Connection, ...]
    first_seen_at: datetime
    last_seen_at: datetime

    @property
    def mac_address(self) -> str:
        """Return the normalized MAC address."""
        return self.id.removeprefix("mac:").upper()


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Authoritative observer state."""

    stream_epoch: str
    sequence: int
    generated_at: datetime
    clients: tuple[Client, ...]


@dataclass(frozen=True, slots=True)
class Event:
    """One ordered observer event."""

    type: str
    stream_epoch: str
    sequence: int
    data: Any


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _string(value: Any, label: str, *, maximum: int = MAX_STRING_LENGTH) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ProtocolError(f"{label} must be a bounded non-empty string")
    return value


def _datetime(value: Any, label: str) -> datetime:
    text = _string(value, label, maximum=64)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as err:
        raise ProtocolError(f"{label} must be an RFC 3339 timestamp") from err
    if parsed.tzinfo is None:
        raise ProtocolError(f"{label} must include a timezone")
    return parsed


def parse_info(value: Any) -> ObserverInfo:
    """Parse and validate `/v1/info`."""
    raw = _mapping(value, "info")
    _string(raw.get("name"), "name", maximum=128)
    if raw.get("protocol_version") != PROTOCOL_VERSION:
        raise UnsupportedObserverError("unsupported protocol version")
    agent_id = _string(raw.get("agent_id"), "agent_id", maximum=32)
    if not _AGENT_ID.fullmatch(agent_id):
        raise ProtocolError("agent_id is invalid")
    capabilities = raw.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) > 16:
        raise ProtocolError("capabilities must be a bounded list")
    parsed_capabilities = frozenset(
        _string(item, "capability", maximum=64) for item in capabilities
    )
    required = {"wifi_snapshot", "wifi_events", "websocket"}
    if not required.issubset(parsed_capabilities):
        raise UnsupportedObserverError("required observer capabilities are missing")
    return ObserverInfo(
        agent_id=agent_id,
        version=_string(raw.get("version"), "version", maximum=64),
        capabilities=parsed_capabilities,
    )


def parse_connection(value: Any) -> Connection:
    """Parse one connection."""
    raw = _mapping(value, "connection")
    stale = raw.get("stale", False)
    if not isinstance(stale, bool):
        raise ProtocolError("connection stale must be boolean")
    return Connection(
        id=_string(raw.get("id"), "connection id", maximum=128),
        provider=_string(raw.get("provider"), "provider", maximum=64),
        source_instance=_string(
            raw.get("source_instance"), "source_instance", maximum=128
        ),
        connected_at=_datetime(raw.get("connected_at"), "connected_at"),
        last_seen_at=_datetime(raw.get("last_seen_at"), "last_seen_at"),
        stale=stale,
    )


def parse_client(value: Any) -> Client:
    """Parse one observer client."""
    raw = _mapping(value, "client")
    client_id = _string(raw.get("id"), "client id", maximum=128)
    if not _CLIENT_ID.fullmatch(client_id):
        raise ProtocolError("client id is invalid")
    state = raw.get("state")
    if state not in ("present", "absent", "unknown"):
        raise ProtocolError("client state is invalid")
    expected_present = {"present": True, "absent": False, "unknown": None}[state]
    if raw.get("present") is not expected_present:
        raise ProtocolError("client present flag conflicts with state")
    connections = raw.get("connections")
    if (
        not isinstance(connections, list)
        or len(connections) > MAX_CONNECTIONS_PER_CLIENT
    ):
        raise ProtocolError("client connections must be a bounded list")
    return Client(
        id=client_id,
        state=state,
        connections=tuple(parse_connection(item) for item in connections),
        first_seen_at=_datetime(raw.get("first_seen_at"), "first_seen_at"),
        last_seen_at=_datetime(raw.get("last_seen_at"), "last_seen_at"),
    )


def parse_snapshot(value: Any) -> Snapshot:
    """Parse an authoritative snapshot."""
    raw = _mapping(value, "snapshot")
    epoch = _string(raw.get("stream_epoch"), "stream_epoch", maximum=32)
    if not _AGENT_ID.fullmatch(epoch):
        raise ProtocolError("stream_epoch is invalid")
    sequence = raw.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ProtocolError("snapshot sequence is invalid")
    clients = raw.get("clients")
    if not isinstance(clients, list) or len(clients) > MAX_CLIENTS:
        raise ProtocolError("snapshot clients must be a bounded list")
    parsed = tuple(parse_client(item) for item in clients)
    if len({client.id for client in parsed}) != len(parsed):
        raise ProtocolError("snapshot contains duplicate client ids")
    return Snapshot(
        stream_epoch=epoch,
        sequence=sequence,
        generated_at=_datetime(raw.get("generated_at"), "generated_at"),
        clients=parsed,
    )


def parse_event(value: Any) -> Event:
    """Parse the common envelope of a stream event."""
    raw = _mapping(value, "event")
    event_type = _string(raw.get("type"), "event type", maximum=64)
    _string(raw.get("event_id"), "event_id", maximum=128)
    epoch = _string(raw.get("stream_epoch"), "stream_epoch", maximum=32)
    if not _AGENT_ID.fullmatch(epoch):
        raise ProtocolError("event stream_epoch is invalid")
    sequence = raw.get("sequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise ProtocolError("event sequence is invalid")
    _datetime(raw.get("timestamp"), "timestamp")
    reason = raw.get("reason")
    if reason is not None:
        _string(reason, "reason", maximum=128)
    return Event(
        type=event_type,
        stream_epoch=epoch,
        sequence=sequence,
        data=raw.get("data"),
    )
