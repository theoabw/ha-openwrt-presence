"""Home Assistant entity behavior tests."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_presence.config_flow import CONF_ENABLE_NEW_TRACKERS
from custom_components.openwrt_presence.const import (
    CONF_AGENT_ID,
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)
from custom_components.openwrt_presence.device_tracker import OpenWrtClientTracker
from custom_components.openwrt_presence.models import (
    parse_client,
    parse_info,
    parse_snapshot,
)
from custom_components.openwrt_presence.store import ObserverStore

from .helpers import AGENT_ID, CLIENT_ID, TOKEN, client, info, snapshot


def make_tracker(
    hass, state: str = "present"
) -> tuple[OpenWrtClientTracker, ObserverStore]:
    """Create an enabled tracker backed by authoritative in-memory state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=AGENT_ID,
        options={CONF_ENABLE_NEW_TRACKERS: True},
    )
    entry.add_to_hass(hass)
    store = ObserverStore()
    store.apply_snapshot(parse_snapshot(snapshot(state)), available=True)
    return OpenWrtClientTracker(entry, store, CLIENT_ID), store


async def test_literal_state_mapping_and_namespaced_identity(hass) -> None:
    """Present, absent, unknown, and unavailable remain distinguishable."""
    tracker, store = make_tracker(hass)
    tracker.hass = hass

    assert tracker.unique_id == f"{AGENT_ID}_{CLIENT_ID}"
    assert tracker.is_connected is True
    assert tracker.available
    assert tracker.mac_address == "02:00:00:00:00:01"

    store.update_client(parse_client(client("absent")), 5)
    assert tracker.is_connected is False
    store.update_client(parse_client(client("unknown")), 6)
    assert tracker.is_connected is None
    store.set_available(False)
    assert not tracker.available
    assert tracker.is_connected is None


async def test_authoritative_snapshot_omission_means_away(hass) -> None:
    """A registered client omitted after restart is away, not unavailable."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=AGENT_ID,
        title="Router",
        data={
            "host": "router.local",
            "port": 8787,
            CONF_TOKEN: TOKEN,
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: True,
            CONF_AGENT_ID: AGENT_ID,
        },
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "device_tracker",
        DOMAIN,
        f"{AGENT_ID}_{CLIENT_ID}",
        config_entry=entry,
        suggested_object_id="phone",
    )

    async def start_with_empty_snapshot(manager) -> None:
        manager._store.apply_snapshot(
            parse_snapshot(snapshot(clients=[])), available=True
        )

    with (
        patch(
            "custom_components.openwrt_presence.ObserverClient.async_get_info",
            AsyncMock(return_value=parse_info(info())),
        ),
        patch(
            "custom_components.openwrt_presence.ConnectionManager.async_start",
            autospec=True,
            side_effect=start_with_empty_snapshot,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("device_tracker.phone")
    assert state is not None
    assert state.state == STATE_NOT_HOME


async def test_disabled_by_default(hass) -> None:
    """New client trackers require explicit user opt-in."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=AGENT_ID)
    entry.add_to_hass(hass)
    store = ObserverStore()
    store.apply_snapshot(parse_snapshot(snapshot()), available=True)
    tracker = OpenWrtClientTracker(entry, store, CLIENT_ID)

    assert not tracker.entity_registry_enabled_default


async def test_config_entry_creates_push_tracker_and_unloads(hass) -> None:
    """A real config-entry setup writes push state and unloads cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=AGENT_ID,
        title="Observer",
        data={
            "host": "router.local",
            "port": 8787,
            CONF_TOKEN: TOKEN,
            CONF_USE_SSL: False,
            CONF_VERIFY_SSL: True,
            CONF_AGENT_ID: AGENT_ID,
        },
        options={CONF_ENABLE_NEW_TRACKERS: True},
    )
    entry.add_to_hass(hass)

    async def start_with_snapshot(manager) -> None:
        manager._store.apply_snapshot(parse_snapshot(snapshot()), available=True)

    with (
        patch(
            "custom_components.openwrt_presence.ObserverClient.async_get_info",
            AsyncMock(return_value=parse_info(info())),
        ),
        patch(
            "custom_components.openwrt_presence.ConnectionManager.async_start",
            autospec=True,
            side_effect=start_with_snapshot,
        ) as start,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    states = hass.states.async_all("device_tracker")
    assert len(states) == 1
    assert states[0].state == STATE_HOME
    entity_id = states[0].entity_id
    assert entity_id == "device_tracker.client_02_00_00_00_00_01"
    start.assert_awaited_once()

    entry.runtime_data.store.update_client(parse_client(client("absent")), 5)
    assert hass.states.get(entity_id).state == STATE_NOT_HOME

    second_id = "mac:02:00:00:00:00:02"
    entry.runtime_data.store.update_client(
        parse_client(client("present", second_id)), 6
    )
    await hass.async_block_till_done()
    assert len(hass.states.async_all("device_tracker")) == 2

    with patch(
        "custom_components.openwrt_presence.ConnectionManager.async_stop",
        AsyncMock(),
    ) as stop:
        assert await hass.config_entries.async_unload(entry.entry_id)
    stop.assert_awaited_once()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
