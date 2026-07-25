"""OpenWrt Presence integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    ObserverAuthError,
    ObserverClient,
    ObserverConnectionError,
    ObserverError,
    ObserverNotReadyError,
)
from .const import (
    CONF_AGENT_ID,
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DOMAIN,
    PLATFORMS,
)
from .manager import ConnectionManager
from .models import ProtocolError, UnsupportedObserverError
from .runtime import OpenWrtPresenceRuntimeData
from .store import ObserverStore

type OpenWrtPresenceConfigEntry = ConfigEntry[OpenWrtPresenceRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: OpenWrtPresenceConfigEntry
) -> bool:
    """Set up one observer from a config entry."""
    client = ObserverClient(
        async_get_clientsession(hass, verify_ssl=entry.data[CONF_VERIFY_SSL]),
        host=entry.data["host"],
        port=entry.data["port"],
        token=entry.data[CONF_TOKEN],
        use_ssl=entry.data[CONF_USE_SSL],
        verify_ssl=entry.data[CONF_VERIFY_SSL],
    )
    try:
        info = await client.async_get_info()
        if info.agent_id != entry.data[CONF_AGENT_ID]:
            raise ConfigEntryNotReady("observer identity changed")
    except ObserverAuthError as err:
        raise ConfigEntryAuthFailed from err
    except (ObserverConnectionError, ObserverNotReadyError) as err:
        raise ConfigEntryNotReady from err
    except (ObserverError, ProtocolError, UnsupportedObserverError) as err:
        raise ConfigEntryNotReady from err

    store = ObserverStore()

    async def async_start_reauth() -> None:
        entry.async_start_reauth(hass)

    manager = ConnectionManager(
        hass,
        entry,
        client,
        store,
        on_auth_failed=async_start_reauth,
    )
    try:
        await manager.async_start()
    except ObserverAuthError as err:
        raise ConfigEntryAuthFailed from err
    except (ObserverError, ProtocolError, UnsupportedObserverError) as err:
        raise ConfigEntryNotReady from err
    entry.runtime_data = OpenWrtPresenceRuntimeData(
        client=client,
        manager=manager,
        store=store,
        info=info,
    )
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, info.agent_id)},
        name=entry.title,
        manufacturer="OpenWrt Client Observation API",
        model="Presence Agent",
        sw_version=info.version,
        configuration_url=client.base_url,
    )

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await manager.async_stop()
        raise
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: OpenWrtPresenceConfigEntry
) -> bool:
    """Unload one observer and all of its tasks."""
    await entry.runtime_data.manager.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unloaded
