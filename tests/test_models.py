"""Tests for bounded protocol parsing."""

import pytest

from custom_components.openwrt_presence.api import validate_host
from custom_components.openwrt_presence.models import (
    ProtocolError,
    UnsupportedObserverError,
    parse_client,
    parse_info,
    parse_snapshot,
)

from .helpers import CLIENT_ID, client, info, snapshot


def test_parse_contract() -> None:
    """Parse the exact sister-repository v1 contract."""
    parsed_info = parse_info(info())
    parsed_snapshot = parse_snapshot(snapshot())

    assert parsed_info.agent_id == "00112233445566778899aabbccddeeff"
    assert parsed_snapshot.clients[0].id == CLIENT_ID
    assert parsed_snapshot.clients[0].mac_address == "02:00:00:00:00:01"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "not-a-client"),
        ("state", "away"),
        ("present", False),
        ("connections", [None] * 129),
    ],
)
def test_reject_invalid_client(field: str, value: object) -> None:
    """Reject inconsistent, unbounded, or unsupported state."""
    raw = client()
    raw[field] = value
    with pytest.raises(ProtocolError):
        parse_client(raw)


def test_reject_duplicate_snapshot_clients() -> None:
    """A snapshot cannot ambiguously contain one ID twice."""
    with pytest.raises(ProtocolError):
        parse_snapshot(snapshot(clients=[client(), client()]))


def test_reject_wrong_protocol() -> None:
    """Reject an endpoint that does not implement the supported protocol."""
    raw = info()
    raw["protocol_version"] = "v2"
    with pytest.raises(UnsupportedObserverError):
        parse_info(raw)


def test_accept_compatible_implementation_name() -> None:
    """Protocol compatibility must not depend on reference branding."""
    raw = info()
    raw["name"] = "another-compatible-observer"

    assert parse_info(raw).agent_id == "00112233445566778899aabbccddeeff"


@pytest.mark.parametrize(
    "host",
    [
        "http://router.local",
        "user:password@router.local",
        "router.local/v1/info",
        " router.local",
        "file:///etc/passwd",
    ],
)
def test_reject_credential_or_url_host_input(host: str) -> None:
    """Only a host can enter URL construction."""
    with pytest.raises(ValueError):
        validate_host(host)
