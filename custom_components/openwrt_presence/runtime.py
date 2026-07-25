"""Typed config-entry runtime data."""

from dataclasses import dataclass

from .api import ObserverClient
from .manager import ConnectionManager
from .models import ObserverInfo
from .store import ObserverStore


@dataclass(slots=True)
class OpenWrtPresenceRuntimeData:
    """One observer's integration runtime."""

    client: ObserverClient
    manager: ConnectionManager
    store: ObserverStore
    info: ObserverInfo
