#!/bin/sh
set -eu

[ "$#" -eq 2 ] || {
	echo "usage: build-release.sh VERSION OUTPUT_DIR" >&2
	exit 2
}

version="$1"
output_dir="$(mkdir -p "$2" && realpath "$2")"
repo_dir="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
archive="$output_dir/openwrt-presence-${version}.zip"

manifest_version="$(
	jq -r '.version' \
		"$repo_dir/custom_components/openwrt_presence/manifest.json"
)"
project_version="$(
	cd "$repo_dir"
	python3 -c \
		'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
)"
[ "$version" = "$manifest_version" ] || {
	echo "version $version does not match manifest $manifest_version" >&2
	exit 1
}
[ "$version" = "$project_version" ] || {
	echo "version $version does not match project $project_version" >&2
	exit 1
}

rm -f "$archive"
(
	cd "$repo_dir"
	find custom_components/openwrt_presence \
		-type f \
		! -path '*/__pycache__/*' \
		! -name '*.pyc' \
		-print |
		LC_ALL=C sort |
		zip -X -q "$archive" -@
)

unzip -t "$archive"
echo "$archive"
