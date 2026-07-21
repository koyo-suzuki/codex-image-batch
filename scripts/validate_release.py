#!/usr/bin/env python3
"""Validate files required to distribute Codex Image Batch."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "codex-image-batch"
SKILL_NAME = "generate-image-batch"


def load_json(relative_path: str) -> dict:
    path = ROOT / relative_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"{relative_path} must contain an object")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    manifest = load_json(".codex-plugin/plugin.json")
    marketplace = load_json(".agents/plugins/marketplace.json")
    example = load_json("jobs.example.json")
    skill_path = ROOT / "skills" / SKILL_NAME / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    require(manifest.get("name") == PLUGIN_NAME, "plugin name mismatch")
    require(manifest.get("version") == "1.2.0", "unexpected plugin version")
    require(manifest.get("skills") == "./skills/", "skill directory is not exported")
    require(skill_path.is_file(), "skill entrypoint is missing")

    require(marketplace.get("name") == PLUGIN_NAME, "marketplace name mismatch")
    plugins = marketplace.get("plugins")
    require(isinstance(plugins, list) and len(plugins) == 1, "marketplace must expose one plugin")
    require(plugins[0].get("name") == PLUGIN_NAME, "marketplace plugin mismatch")
    require(plugins[0].get("source", {}).get("path") == "./", "marketplace must install the repository root")

    require(example.get("parallelism") == 100, "example must default to 100-way burst execution")
    require(len(example.get("jobs", [])) == 10, "example must contain 10 independent prompts")
    require(all("variants" not in job for job in example["jobs"]), "example must not use variants")
    require("one prompt and one output image" in skill, "skill is missing the one-prompt contract")
    require("1 through 100" in skill, "skill is missing the 100-way concurrency contract")
    require("wave.map" in skill and "wave_dispatched" in skill, "skill is missing the burst-start invariant")
    require("Promise.allSettled" in skill, "skill is missing bounded async orchestration")
    require("tools.image_gen__imagegen" in skill, "skill is not wired to built-in image generation")

    install_source = "codex plugin marketplace add koyo-suzuki/codex-image-batch"
    install_plugin = "codex plugin add codex-image-batch@codex-image-batch"
    require(install_source in readme and install_plugin in readme, "README install commands are missing")
    require((ROOT / "LICENSE").is_file(), "LICENSE is missing")

    print("Release validation passed: plugin, marketplace, 100-way burst orchestration, README")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
