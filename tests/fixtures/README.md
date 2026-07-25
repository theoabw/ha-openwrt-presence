# Protocol fixtures

`protocol-v1.json` mirrors
`openwrt-presence-agent/api/fixtures/v1.json`. It contains only synthetic
identifiers and timestamps.

The integration parses the fixture through its real models and stream state
manager. When changing the protocol, update the agent-owned fixture first,
mirror it here, and update the compatibility table in the same change. The
local consistency check compares both copies automatically when the sibling
agent repository is checked out beside this repository.
