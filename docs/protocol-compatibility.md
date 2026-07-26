# Protocol compatibility

| Integration | Minimum Home Assistant | API protocol | Verified observer source |
|---|---:|---:|---|
| Next release (unreleased) | 2026.7.0 | v1 | Any conforming v1 implementation; the reference is [`openwrt-presence-agent`](https://github.com/theoabw/openwrt-presence-agent) |
| 0.1.0 | 2026.7.0 | v1 | Any conforming v1 implementation; the reference is [`openwrt-presence-agent`](https://github.com/theoabw/openwrt-presence-agent) |

Compatibility is based on protocol behavior rather than repository name,
implementation language, package name, branding, or matching release numbers.

> [!IMPORTANT]
> Protocol compatibility is not router hardware verification. The Flint 3
> configuration below is currently the only router and firmware combination
> live-tested end to end by this project. Flint 2 and all other router
> combinations remain unverified.

The end-to-end hardware test uses the reference observer on a GL.iNet Flint 3
(`GL-BE9300`) running GL.iNet firmware 4.9.0, an OpenWrt
`23.05-SNAPSHOT` base, Linux `5.4.213`, target `ipq53xx/generic`, and package
architecture `aarch64_cortex-a53_neon-vfpv4`.

The integration requires these authenticated read-only API capabilities:

- `GET /v1/info` returning a bounded implementation name, protocol `v1`, persistent
  32-character `agent_id`, and `wifi_snapshot`, `wifi_events`, and `websocket`
  capabilities;
- `GET /v1/clients` returning a complete bounded snapshot; and
- `GET /v1/events` upgrading to a WebSocket that sends `stream.hello`,
  `state.snapshot`, then strictly ordered events and heartbeats.

The reference observer additionally advertises `wired_snapshot` and
`wired_events` when it provides Ethernet presence through active ARP
reconciliation and fresh Linux neighbor events. These are additive v1
capabilities: the integration consumes normalized client connections without
special-casing their provider, and continues accepting conforming Wi-Fi-only
observers that expose the original required capability set.

The mirrored interoperability fixture includes one Wi-Fi connection and one
wired connection. This verifies that both travel through the same bounded
snapshot, store, entity, and event model; it does not make router-hardware or
wired-latency guarantees.

The stable `agent_id` is the Home Assistant config-entry identity. A complete
snapshot carries a runtime epoch and sequence. Presence-changing
`client.presence_changed` and `client.updated` events must carry a complete
client object compatible with the observer's v1 schema.

Event replay is not required or used. Any disconnect, epoch change, sequence
gap, malformed state-changing event, or event whose state impact is unknown
causes the integration to mark trackers unavailable and reconnect. The next
complete authoritative stream snapshot restores state.

The current reference observer does not advertise the proposed
`_openwrt-presence-agent._tcp.local.` Zeroconf service, so manual configuration
is the working setup path for that implementation. The integration already
accepts a future announcement containing `agent_id` and optional `tls`
properties, but no discovery claim is made for the current observer release.
