"""YAML configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from recovery.paths import CONFIG_DIR


def load_yaml(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or CONFIG_DIR) / name
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_policy(config_dir: Path | None = None) -> dict[str, Any]:
    return load_yaml("policy.yaml", config_dir)


def load_recovery_budget(config_dir: Path | None = None) -> dict[str, Any]:
    return load_yaml("recovery_budget.yaml", config_dir)


def load_actions(config_dir: Path | None = None) -> dict[str, Any]:
    return load_yaml("actions.yaml", config_dir)


def load_economics(config_dir: Path | None = None) -> dict[str, Any]:
    return load_yaml("economics.yaml", config_dir)


def load_learning(config_dir: Path | None = None) -> dict[str, Any]:
    return load_yaml("learning.yaml", config_dir)
