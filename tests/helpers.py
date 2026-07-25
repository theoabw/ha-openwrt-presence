"""Sanitized observer protocol fixtures."""

from __future__ import annotations

from typing import Any

AGENT_ID = "00112233445566778899aabbccddeeff"
EPOCH = "ffeeddccbbaa99887766554433221100"
CLIENT_ID = "mac:02:00:00:00:00:01"
TOKEN = "sanitized-test-token"
NOW = "2026-07-23T12:00:00Z"


def info() -> dict[str, Any]:
    """Return valid observer info."""
    return {
        "name": "openwrt-presence-agent",
        "protocol_version": "v1",
        "agent_id": AGENT_ID,
        "version": "test",
        "capabilities": ["wifi_snapshot", "wifi_events", "websocket"],
    }


def client(state: str = "present", client_id: str = CLIENT_ID) -> dict[str, Any]:
    """Return a valid client."""
    present = {"present": True, "absent": False, "unknown": None}[state]
    return {
        "id": client_id,
        "state": state,
        "present": present,
        "connections": (
            [
                {
                    "id": "ubus:hostapd.wlan0",
                    "provider": "ubus",
                    "source_instance": "hostapd.wlan0",
                    "connected_at": NOW,
                    "last_seen_at": NOW,
                }
            ]
            if state == "present"
            else []
        ),
        "first_seen_at": NOW,
        "last_seen_at": NOW,
    }


def snapshot(
    state: str = "present", *, sequence: int = 4, clients: list | None = None
) -> dict[str, Any]:
    """Return a valid snapshot."""
    return {
        "stream_epoch": EPOCH,
        "sequence": sequence,
        "generated_at": NOW,
        "clients": [client(state)] if clients is None else clients,
    }


def event(
    event_type: str,
    sequence: int,
    *,
    data: Any = None,
    epoch: str = EPOCH,
) -> dict[str, Any]:
    """Return a valid stream event."""
    return {
        "type": event_type,
        "event_id": f"{epoch}:{sequence}",
        "stream_epoch": epoch,
        "sequence": sequence,
        "timestamp": NOW,
        "data": data,
    }
