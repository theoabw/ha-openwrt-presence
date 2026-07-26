# Releases and rollback

The CI workflow runs Ruff, formatting, pytest, mypy, Hassfest, and HACS
validation. Checked-in release metadata stays at the `0.0.0` template version.
A signed SemVer tag such as `v0.2.0` supplies the real version when the workflow
builds the manual-install ZIP. The workflow injects that version into the
archive's integration manifest without modifying the source branch, creates
`SHA256SUMS`, generates release notes from Git history and pull-request labels,
and publishes a GitHub release. Public repositories also receive a GitHub
artifact provenance attestation.

Before tagging:

1. choose the release version and create a signed annotated SemVer tag from
   `main`;
2. run all checks documented in `CONTRIBUTING.md`;
3. install the candidate on a supported Home Assistant version;
4. verify initial state, push updates, reconnect, reauthentication, reload, and
   removal; and
5. review release notes for security or migration instructions.

Contributors do not select or update release versions in pull requests.

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
