# Releases and rollback

The CI workflow runs Ruff, formatting, pytest, mypy, Hassfest, and HACS
validation. A SemVer tag such as `v0.1.0` must agree with the version in
`custom_components/openwrt_presence/manifest.json`. A matching tag builds a
manual-install ZIP, creates `SHA256SUMS`, generates release notes from Git
history and pull-request labels, and publishes a GitHub release. Public
repositories also receive a GitHub artifact provenance attestation.

Before tagging:

1. update the manifest and project version together;
2. run all checks documented in `CONTRIBUTING.md`;
3. install the candidate on a supported Home Assistant version;
4. verify initial state, push updates, reconnect, reauthentication, reload, and
   removal; and
5. review release notes for security or migration instructions.

Tags do not deploy the integration to a Home Assistant instance. Users choose
when to install or upgrade through HACS or a manual copy.

## Rollback

With HACS, select an earlier release in the repository's version menu, download
it, and restart Home Assistant. For a manual installation:

1. keep a backup of `/config/custom_components/openwrt_presence`;
2. replace the integration directory with the files from the previous release;
3. restart Home Assistant; and
4. verify that the config entry and trackers load.

Do not downgrade across a release whose notes say its config-entry data is
incompatible without restoring a matching Home Assistant backup.
