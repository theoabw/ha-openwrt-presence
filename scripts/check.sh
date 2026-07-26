#!/bin/sh
set -eu

repo_dir="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_dir"

for command in python3 shellcheck jq zip unzip; do
	command -v "$command" >/dev/null 2>&1 || {
		echo "missing required command: $command" >&2
		exit 1
	}
done

python3 -c 'import mypy, pytest, ruff' 2>/dev/null || {
	echo "missing Python test dependencies; activate the documented virtual environment" >&2
	exit 1
}

python3 -m ruff check .
python3 -m ruff format --check .
python3 -m pytest
python3 -m mypy custom_components
python3 scripts/check-consistency.py
shellcheck -s sh scripts/build-release.sh scripts/check.sh
jq empty \
	hacs.json \
	custom_components/openwrt_presence/manifest.json \
	custom_components/openwrt_presence/strings.json \
	custom_components/openwrt_presence/translations/en.json \
	tests/fixtures/protocol-v1.json

release_dir="$(mktemp -d)"
trap 'rm -rf "$release_dir"' EXIT
scripts/build-release.sh 9.8.7 "$release_dir"
test "$(
	unzip -p \
		"$release_dir/openwrt-presence-9.8.7.zip" \
		custom_components/openwrt_presence/manifest.json |
		jq -r '.version'
)" = "9.8.7"
test "$(
	jq -r '.version' custom_components/openwrt_presence/manifest.json
)" = "0.0.0"
