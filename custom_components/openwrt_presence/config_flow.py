"""UI configuration for OpenWrt Presence."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    ObserverAuthError,
    ObserverClient,
    ObserverConnectionError,
    ObserverNotReadyError,
    ObserverResponseError,
    ObserverTLSError,
    validate_host,
)
from .const import (
    CONF_AGENT_ID,
    CONF_TOKEN,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_PORT,
    DEFAULT_USE_SSL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .models import ProtocolError, UnsupportedObserverError

CONF_ENABLE_NEW_TRACKERS = "enable_new_trackers"


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, "")
            ): TextSelector(),
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_TOKEN, default=""): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_USE_SSL,
                default=defaults.get(CONF_USE_SSL, DEFAULT_USE_SSL),
            ): BooleanSelector(),
            vol.Required(
                CONF_VERIFY_SSL,
                default=defaults.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
            ): BooleanSelector(),
        }
    )


async def _validate_input(
    hass: Any, data: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    host = validate_host(data[CONF_HOST])
    token = data[CONF_TOKEN]
    if not isinstance(token, str) or not 1 <= len(token) <= 4096:
        raise ValueError("invalid token")
    port = int(data[CONF_PORT])
    use_ssl = bool(data[CONF_USE_SSL])
    verify_ssl = bool(data[CONF_VERIFY_SSL])
    normalized: dict[str, Any] = {
        CONF_HOST: host,
        CONF_PORT: port,
        CONF_TOKEN: token,
        CONF_USE_SSL: use_ssl,
        CONF_VERIFY_SSL: verify_ssl,
    }
    client = ObserverClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        host=host,
        port=port,
        token=token,
        use_ssl=use_ssl,
        verify_ssl=verify_ssl,
    )
    info = await client.async_get_info()
    await client.async_get_snapshot()
    normalized[CONF_AGENT_ID] = info.agent_id
    return normalized, info.agent_id


def _error_key(err: Exception) -> str:
    if isinstance(err, ObserverAuthError):
        return "invalid_auth"
    if isinstance(err, ObserverTLSError):
        return "invalid_tls"
    if isinstance(err, ObserverNotReadyError):
        return "not_ready"
    if isinstance(err, ObserverConnectionError):
        return "cannot_connect"
    if isinstance(err, UnsupportedObserverError):
        return "unsupported_observer"
    if isinstance(err, (ObserverResponseError, ProtocolError, ValueError)):
        return "invalid_response"
    return "unknown"


class OpenWrtPresenceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one protocol-compatible observer."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle manual setup."""
        return await self._async_configure(user_input)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> config_entries.ConfigFlowResult:
        """Handle compatible observer discovery."""
        agent_id = discovery_info.properties.get("agent_id")
        if (
            not isinstance(agent_id, str)
            or len(agent_id) != 32
            or any(char not in "0123456789abcdef" for char in agent_id)
        ):
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(agent_id)
        self._abort_if_unique_id_configured()
        self._discovery = {
            CONF_HOST: str(discovery_info.ip_address),
            CONF_PORT: discovery_info.port or DEFAULT_PORT,
            CONF_USE_SSL: discovery_info.properties.get("tls") == "true",
            CONF_VERIFY_SSL: True,
        }
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm a discovered observer and collect its token."""
        if user_input is not None:
            return await self._async_configure({**self._discovery, **user_input})
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
        )

    async def _async_configure(
        self, user_input: dict[str, Any] | None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, agent_id = await _validate_input(self.hass, user_input)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                await self.async_set_unique_id(agent_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"OpenWrt observer {agent_id[:8]}", data=data
                )
        defaults = user_input or self._discovery
        return self.async_show_form(
            step_id="user", data_schema=_schema(defaults), errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Replace a rejected bearer token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {**entry.data, CONF_TOKEN: user_input[CONF_TOKEN]}
            try:
                data, agent_id = await _validate_input(self.hass, candidate)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                await self.async_set_unique_id(agent_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_and_abort(
                    entry, data_updates={CONF_TOKEN: data[CONF_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Update connectivity without changing observer identity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = dict(user_input)
            if not candidate[CONF_TOKEN]:
                candidate[CONF_TOKEN] = entry.data[CONF_TOKEN]
            try:
                data, agent_id = await _validate_input(self.hass, candidate)
            except Exception as err:  # noqa: BLE001
                errors["base"] = _error_key(err)
            else:
                await self.async_set_unique_id(agent_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return OpenWrtPresenceOptionsFlow()


class OpenWrtPresenceOptionsFlow(config_entries.OptionsFlow):
    """Configure how newly observed trackers are registered."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_NEW_TRACKERS,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_NEW_TRACKERS, False
                        ),
                    ): BooleanSelector()
                }
            ),
        )
