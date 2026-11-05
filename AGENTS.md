# Agent instructions

Repository-specific rules for automated and agent-assisted contributions.
`CONTRIBUTING.md` remains the source of truth for everyone; these notes make the
parts that are easy to get wrong explicit.

## Before opening a pull request

- Run `scripts/check.sh` in the documented virtual environment. It covers
  formatting, linting, typing, the test suite, shell scripts, metadata
  consistency, and a reproducible release build.
- In the pull request body, state what you tested and what you did not, with
  versions where they matter. Passing the test suite is not a compatibility
  claim. Only a real Home Assistant installation and observed behaviour are.

## Never include identifiers or credentials

Tests, fixtures, logs, diagnostics, commit messages, issues, and pull request
bodies must not contain a bearer token, an authorization header, a real MAC
address, hostname, household IP address, or a raw client inventory. Use
reserved values instead:

- IPv4 and IPv6 from RFC 5737 and RFC 3849, for example `192.0.2.10` and
  `2001:db8::1`;
- locally administered MAC addresses such as `02:00:00:00:00:01`;
- placeholder tokens built from obvious patterns rather than copied values.

## Behaviour the integration keeps

- Push only. No polling coordinator, no departure delay, and no
  integration-side debounce.
- A transport failure, an integrity failure, or an unparseable snapshot becomes
  `unavailable`. It never becomes a fabricated departure.
- Trackers are source specific and disabled by default.
- Observations are mapped literally. Occupancy policy, grouping, and automation
  stay in Home Assistant, not in this integration.

## Protocol compatibility

A change that affects the observer contract updates
`docs/protocol-compatibility.md`, the contract fixture in `tests/fixtures/`, and
the tests that consume it in the same change.

## Pull request titles

Pull requests are squash-merged and the title becomes the commit subject on
`main`. Follow the format in `CONTRIBUTING.md`: `type(scope): imperative
summary`, lowercase, without a trailing period.

## Private notes

`.project-notes/` is ignored on purpose. Planning notes and internal decision
logs do not belong in commits or pull requests.
