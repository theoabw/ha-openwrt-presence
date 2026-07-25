"""Push device trackers for observed network clients."""

from __future__ import annotations

from homeassistant.components.device_tracker.entity import ScannerEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import OpenWrtPresenceConfigEntry
from .config_flow import CONF_ENABLE_NEW_TRACKERS
from .store import ObserverStore

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenWrtPresenceConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up all known clients and retain dynamic discovery."""
    store = entry.runtime_data.store
    _async_migrate_legacy_entity_ids(hass, entry)
    known = set(store.clients) | _registered_client_ids(hass, entry)

    def entity(client_id: str) -> OpenWrtClientTracker:
        return OpenWrtClientTracker(entry, store, client_id)

    async_add_entities(entity(client_id) for client_id in sorted(known))

    @callback
    def async_client_added(client_id: str) -> None:
        if client_id in known:
            return
        known.add(client_id)
        async_add_entities([entity(client_id)])

    entry.async_on_unload(store.subscribe_new_clients(async_client_added))


@callback
def _registered_client_ids(
    hass: HomeAssistant, entry: OpenWrtPresenceConfigEntry
) -> set[str]:
    """Return clients retained in the entity registry across restarts."""
    registry = er.async_get(hass)
    unique_id_prefix = f"{entry.unique_id}_mac:"
    return {
        registry_entry.unique_id.removeprefix(f"{entry.unique_id}_")
        for registry_entry in registry.entities.values()
        if registry_entry.domain == "device_tracker"
        and registry_entry.platform == "openwrt_presence"
        and registry_entry.config_entry_id == entry.entry_id
        and registry_entry.unique_id.startswith(unique_id_prefix)
    }


@callback
def _async_migrate_legacy_entity_ids(
    hass: HomeAssistant, entry: OpenWrtPresenceConfigEntry
) -> None:
    """Replace the initial, implementation-heavy generated entity IDs.

    Entity unique IDs remain namespaced by observer and MAC address.  Only the
    Home Assistant-facing entity ID is shortened, and only when it still has
    the exact generated form used by the first integration release.
    """
    registry = er.async_get(hass)
    legacy_prefix = f"device_tracker.openwrt_presence_{entry.unique_id}_mac_"
    unique_id_prefix = f"{entry.unique_id}_mac:"

    for registry_entry in registry.entities.values():
        if (
            registry_entry.domain != "device_tracker"
            or registry_entry.platform != "openwrt_presence"
            or registry_entry.config_entry_id != entry.entry_id
            or not registry_entry.entity_id.startswith(legacy_prefix)
            or not registry_entry.unique_id.startswith(unique_id_prefix)
        ):
            continue
        mac = registry_entry.unique_id.removeprefix(unique_id_prefix)
        registry.async_update_entity(
            registry_entry.entity_id,
            new_entity_id=f"device_tracker.client_{mac.replace(':', '_')}",
        )


class OpenWrtClientTracker(ScannerEntity):
    """One observer-specific network client tracker."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False

    def __init__(
        self,
        entry: OpenWrtPresenceConfigEntry,
        store: ObserverStore,
        client_id: str,
    ) -> None:
        self._entry = entry
        self._store = store
        self._client_id = client_id
        self._attr_mac_address = client_id.removeprefix("mac:").upper()
        self._attr_name = f"Client {self._attr_mac_address}"

    @property
    def unique_id(self) -> str:
        """Namespace registry identity by observer and client."""
        return f"{self._entry.unique_id}_{self._client_id}"

    @property
    def available(self) -> bool:
        """Return whether observer state is authoritative."""
        return self._store.available

    @property
    def is_connected(self) -> bool | None:
        """Project observer state literally."""
        client = self._store.clients.get(self._client_id)
        if client is None:
            return False
        if client.state == "unknown":
            return None
        return client.state == "present"

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Disable new trackers unless explicitly opted in."""
        return bool(self._entry.options.get(CONF_ENABLE_NEW_TRACKERS, False))

    async def async_added_to_hass(self) -> None:
        """Subscribe only while the entity is enabled and loaded."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._store.subscribe_client(self._client_id, self._async_write)
        )
        self.async_on_remove(self._store.subscribe_availability(self._async_write))

    @callback
    def _async_write(self) -> None:
        self.async_write_ha_state()
