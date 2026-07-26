#!/usr/bin/env python3
"""Check duplicated release and compatibility metadata for drift."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

manifest = json.loads(
    (ROOT / "custom_components/openwrt_presence/manifest.json").read_text()
)
project = tomllib.loads((ROOT / "pyproject.toml").read_text())
hacs = json.loads((ROOT / "hacs.json").read_text())
fixture = json.loads((ROOT / "tests/fixtures/protocol-v1.json").read_text())
constants = (ROOT / "custom_components/openwrt_presence/const.py").read_text()
requirements = (ROOT / "requirements_test.txt").read_text().splitlines()
compatibility = (ROOT / "docs/protocol-compatibility.md").read_text()

manifest_version = manifest["version"]
project_version = project["project"]["version"]
if manifest_version != project_version:
    raise SystemExit(
        f"manifest version {manifest_version} != project version {project_version}"
    )
if manifest_version != "0.0.0":
    raise SystemExit("release metadata must keep the 0.0.0 template version")

found = re.search(r'^PROTOCOL_VERSION: Final = "(v\d+)"$', constants, re.MULTILINE)
if found is None:
    raise SystemExit("could not find PROTOCOL_VERSION")
protocol_version = found.group(1)
if fixture.get("protocol_version") != protocol_version:
    raise SystemExit("contract fixture does not match PROTOCOL_VERSION")
if fixture.get("info", {}).get("protocol_version") != protocol_version:
    raise SystemExit("fixture info does not match PROTOCOL_VERSION")

home_assistant_requirement = next(
    (
        line.removeprefix("homeassistant==")
        for line in requirements
        if line.startswith("homeassistant==")
    ),
    None,
)
if home_assistant_requirement is None:
    raise SystemExit("requirements_test.txt does not pin Home Assistant")
minimum_home_assistant = hacs["homeassistant"]
if home_assistant_requirement.split(".")[:2] != minimum_home_assistant.split(".")[:2]:
    raise SystemExit(
        "pinned and minimum Home Assistant versions use different releases"
    )

expected_row = (
    f"| Next release (unreleased) | {minimum_home_assistant} | {protocol_version} |"
)
if expected_row not in compatibility:
    raise SystemExit("protocol compatibility table does not match release metadata")

agent_fixture_path = (
    ROOT.parent / "openwrt-presence-agent" / "api" / "fixtures" / "v1.json"
)
if agent_fixture_path.exists():
    agent_fixture = json.loads(agent_fixture_path.read_text())
    if fixture != agent_fixture:
        raise SystemExit(
            "HA fixture differs from ../openwrt-presence-agent/api/fixtures/v1.json"
        )

print(
    f"consistent template_version={manifest_version} "
    f"homeassistant={minimum_home_assistant} protocol={protocol_version}"
)
