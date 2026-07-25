"""Constants for the OpenWrt Presence integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "openwrt_presence"
PLATFORMS: Final = (Platform.DEVICE_TRACKER,)

CONF_TOKEN: Final = "token"
CONF_USE_SSL: Final = "use_ssl"
CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_AGENT_ID: Final = "agent_id"
CONF_ZONE: Final = "zone"

DEFAULT_PORT: Final = 8787
DEFAULT_USE_SSL: Final = False
DEFAULT_VERIFY_SSL: Final = True
DEFAULT_ZONE: Final = "zone.home"

PROTOCOL_VERSION: Final = "v1"

MAX_RESPONSE_BYTES: Final = 2 * 1024 * 1024
MAX_EVENT_BYTES: Final = 256 * 1024
MAX_CLIENTS: Final = 2048
MAX_CONNECTIONS_PER_CLIENT: Final = 128
MAX_STRING_LENGTH: Final = 512

EVENT_CLIENT_CHANGED: Final = "client_changed"
EVENT_CLIENT_ADDED: Final = "client_added"
EVENT_AVAILABILITY_CHANGED: Final = "availability_changed"
