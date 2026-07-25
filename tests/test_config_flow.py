"""Tests for manual, duplicate, reauth, and reconfigure flows."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openwrt_presence.const import (
    CONF_AGENT_ID,
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from .helpers import AGENT_ID, TOKEN

INPUT = {
    CONF_HOST: "router.local",
    CONF_PORT: 8787,
    CONF_TOKEN: TOKEN,
    CONF_USE_SSL: False,
    CONF_VERIFY_SSL: True,
}
DATA = {**INPUT, CONF_AGENT_ID: AGENT_ID}


async def test_manual_flow(hass) -> None:
    """Manual configuration validates and stores the stable identity."""
    with (
        patch(
            "custom_components.openwrt_presence.config_flow._validate_input",
            AsyncMock(return_value=(DATA, AGENT_ID)),
        ),
        patch(
            "custom_components.openwrt_presence.async_setup_entry",
            AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA
    assert result["result"].unique_id == AGENT_ID


async def test_duplicate_prevention(hass) -> None:
    """Two addresses for one observer cannot create duplicate entries."""
    MockConfigEntry(domain=DOMAIN, unique_id=AGENT_ID, data=DATA).add_to_hass(hass)
    with patch(
        "custom_components.openwrt_presence.config_flow._validate_input",
        AsyncMock(return_value=(DATA, AGENT_ID)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_only_token(hass) -> None:
    """Reauthentication preserves observer identity and connectivity data."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=AGENT_ID, data=DATA, title="Observer"
    )
    entry.add_to_hass(hass)
    new_data = {**DATA, CONF_TOKEN: "replacement"}
    with patch(
        "custom_components.openwrt_presence.config_flow._validate_input",
        AsyncMock(return_value=(new_data, AGENT_ID)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "replacement"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_TOKEN] == "replacement"
    assert entry.unique_id == AGENT_ID


async def test_reconfigure_updates_endpoint_and_preserves_identity(hass) -> None:
    """Reconfiguration changes connectivity without replacing the observer."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=AGENT_ID, data=DATA, title="Observer"
    )
    entry.add_to_hass(hass)
    updated = {**DATA, CONF_HOST: "new-router.local", CONF_PORT: 8788}
    submitted = {key: value for key, value in updated.items() if key != CONF_AGENT_ID}
    with patch(
        "custom_components.openwrt_presence.config_flow._validate_input",
        AsyncMock(return_value=(updated, AGENT_ID)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], submitted
        )

    assert result["type"] is FlowResultType.ABORT
    assert entry.data[CONF_HOST] == "new-router.local"
    assert entry.data[CONF_PORT] == 8788
    assert entry.unique_id == AGENT_ID


async def test_options_enable_new_trackers(hass) -> None:
    """The options flow persists the new-tracker preference."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=AGENT_ID, data=DATA, title="Observer"
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"enable_new_trackers": True}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["enable_new_trackers"] is True
