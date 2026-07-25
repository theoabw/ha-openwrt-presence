"""Tests for targeted in-memory state updates."""

from custom_components.openwrt_presence.models import parse_client, parse_snapshot
from custom_components.openwrt_presence.store import ObserverStore

from .helpers import CLIENT_ID, client, snapshot


def test_immediate_targeted_state_mapping() -> None:
    """Presence updates synchronously notify only the affected client."""
    store = ObserverStore()
    store.apply_snapshot(parse_snapshot(snapshot()), available=True)
    writes = 0

    def write() -> None:
        nonlocal writes
        writes += 1

    store.subscribe_client(CLIENT_ID, write)
    store.update_client(parse_client(client("absent")), 5)

    assert store.clients[CLIENT_ID].state == "absent"
    assert store.sequence == 5
    assert writes == 1


def test_transport_loss_changes_only_availability() -> None:
    """A transport failure does not rewrite the observer presence value."""
    store = ObserverStore()
    store.apply_snapshot(parse_snapshot(snapshot()), available=True)

    store.set_available(False)

    assert not store.available
    assert store.clients[CLIENT_ID].state == "present"


def test_snapshot_adds_dynamic_client_once() -> None:
    """New-client discovery is stable across repeated snapshots."""
    store = ObserverStore()
    added: list[str] = []
    store.subscribe_new_clients(added.append)

    parsed = parse_snapshot(snapshot())
    store.apply_snapshot(parsed, available=True)
    store.apply_snapshot(parsed, available=True)

    assert added == [CLIENT_ID]
