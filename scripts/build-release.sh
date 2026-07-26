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

case "$version" in
	''|*[!0-9.]*|.*|*..*|*.)
		echo "invalid release version: $version" >&2
		exit 1
		;;
esac
[ "$(printf '%s' "$version" | awk -F. '{ print NF }')" -eq 3 ] || {
	echo "invalid release version: $version" >&2
	exit 1
}

manifest_version="$(
	jq -r '.version' \
		"$repo_dir/custom_components/openwrt_presence/manifest.json"
)"
project_version="$(
	cd "$repo_dir"
	python3 -c \
		'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
)"
[ "$manifest_version" = "0.0.0" ] || {
	echo "manifest must keep the 0.0.0 release-template version" >&2
	exit 1
}
[ "$project_version" = "0.0.0" ] || {
	echo "project must keep the 0.0.0 release-template version" >&2
	exit 1
}

staging_dir="$(mktemp -d)"
trap 'rm -rf "$staging_dir"' EXIT
mkdir -p "$staging_dir/custom_components"
cp -R \
	"$repo_dir/custom_components/openwrt_presence" \
	"$staging_dir/custom_components/"
jq --arg version "$version" \
	'.version = $version' \
	"$staging_dir/custom_components/openwrt_presence/manifest.json" \
	> "$staging_dir/manifest.json"
mv \
	"$staging_dir/manifest.json" \
	"$staging_dir/custom_components/openwrt_presence/manifest.json"

rm -f "$archive"
(
	cd "$staging_dir"
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
