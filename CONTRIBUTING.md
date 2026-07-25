# Contributing

Contributions are welcome. Reports from real Home Assistant installations,
compatibility findings for other OpenWrt Client Observation API
implementations, documentation corrections, focused bug fixes, and
privacy-preserving test fixtures are especially useful.

Before opening an issue or pull request:

- search existing reports;
- state the exact Home Assistant version and observer implementation/version;
- describe the expected and observed behavior;
- include the smallest relevant, sanitized error or log excerpt; and
- remove bearer tokens, authorization headers, MAC addresses, hostnames, IP
  addresses, raw client inventories, and other identifying household data.

Installation success alone does not establish protocol compatibility. A useful
compatibility report exercises authentication, the initial snapshot, immediate
push updates, disconnect availability, snapshot recovery, and clean reload or
unload.

## Code changes

Keep the integration focused on mapping observer state into Home Assistant.
Changes must preserve literal state mapping, immediate valid push updates,
source-specific tracker identity, and the distinction between absence and
transport unavailability. Do not add router mutation, implicit departure
timing, person inference, or cross-observer aggregation to source trackers.

Protocol behavior changes must update focused tests and
`docs/protocol-compatibility.md`. User-visible behavior must include matching
installation, configuration, security, troubleshooting, or migration
documentation where relevant.

Do not add manifest claims, services, platforms, translations, HACS metadata,
or release automation for functionality that does not exist and is not covered
by tests.

Create the pinned development environment:

```sh
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements_test.txt
```

Then run the complete local check:

```sh
scripts/check.sh
```

It runs Ruff, formatting, pytest, strict mypy, version/protocol consistency,
shell and JSON validation, and a release ZIP build. CI additionally runs the
hosted Hassfest and HACS validators.

The integration is deliberately layered:

- `api.py` owns bounded HTTP/WebSocket transport, authentication, TLS, and
  transport error categories;
- `models.py` validates untrusted wire data into immutable protocol models;
- `manager.py` owns the ordered stream, reconnect, and integrity lifecycle;
- `store.py` holds authoritative in-memory state and targeted subscriptions;
- `device_tracker.py` projects store state into Home Assistant entities;
- `config_flow.py` owns discovery, setup, reauthentication, reconfiguration,
  and options; and
- `runtime.py` groups the objects owned by one config entry.

Sanitized payloads in `tests/fixtures/` mirror the agent's public contract
fixtures. Protocol changes must update both repositories' fixtures and
compatibility documentation.

Use Home Assistant fixtures and helpers compatible with the declared minimum
Home Assistant version. Keep changes small, preserve unrelated work, and add a
regression test for bug fixes.

Private planning notes, product specifications, research dumps, and internal
decision logs do not belong in commits. Keep them in the ignored
`.project-notes/` directory when useful locally.

AI tools may assist a contribution, but the contributor remains responsible for
understanding and reviewing the submitted code, documentation, tests,
provenance, licensing, security, and privacy implications.
