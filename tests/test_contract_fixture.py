"""Compatibility tests for the agent-owned protocol fixture."""

import json
from pathlib import Path

from custom_components.openwrt_presence.const import PROTOCOL_VERSION
from custom_components.openwrt_presence.manager import ConnectionManager
from custom_components.openwrt_presence.models import (
    parse_client,
    parse_event,
    parse_info,
    parse_snapshot,
)
from custom_components.openwrt_presence.store import ObserverStore

FIXTURE = Path(__file__).parent / "fixtures" / "protocol-v1.json"


def test_agent_contract_fixture_is_consumable() -> None:
    """The reference agent payloads remain valid integration input."""
    raw = json.loads(FIXTURE.read_text())

    assert raw["fixture_version"] == 1
    assert raw["protocol_version"] == PROTOCOL_VERSION
    assert parse_info(raw["info"]).version == "fixture"

    snapshot = parse_snapshot(raw["snapshot"])
    assert {
        connection.provider
        for client in snapshot.clients
        for connection in client.connections
    } == {"ubus", "wired-arp"}
    events = [parse_event(item) for item in raw["events"]]
    assert snapshot.sequence == 4
    assert [event.type for event in events] == [
        "stream.hello",
        "state.snapshot",
        "client.presence_changed",
    ]

    store = ObserverStore()
    store.apply_snapshot(snapshot, available=True)
    assert len(store.clients) == 2
    manager = object.__new__(ConnectionManager)
    manager._store = store
    manager._validate_hello(events[0])
    manager._apply_event(events[2])

    assert store.sequence == 5
    assert parse_client(events[2].data).state == "absent"
    assert next(iter(store.clients.values())).state == "absent"
