"""Load coordination thresholds from config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from recovery.config import load_yaml


@dataclass(frozen=True, slots=True)
class CoordinationConfig:
    enabled: bool
    max_customer_contacts_per_window: int
    contact_window_hours: int
    min_gap_between_customer_contacts_hours: int
    max_simultaneous_human_escalations: int
    max_active_incentives: int
    prefer_system_actions_before_contact: bool
    defer_lower_value_contacts: bool


def load_coordination_config(config_dir: Path | None = None) -> CoordinationConfig:
    raw = load_yaml("coordination.yaml", config_dir)
    return CoordinationConfig(
        enabled=bool(raw.get("enabled", True)),
        max_customer_contacts_per_window=int(raw.get("max_customer_contacts_per_window", 1)),
        contact_window_hours=int(raw.get("contact_window_hours", 24)),
        min_gap_between_customer_contacts_hours=int(
            raw.get("min_gap_between_customer_contacts_hours", 24)
        ),
        max_simultaneous_human_escalations=int(raw.get("max_simultaneous_human_escalations", 1)),
        max_active_incentives=int(raw.get("max_active_incentives", 1)),
        prefer_system_actions_before_contact=bool(
            raw.get("prefer_system_actions_before_contact", True)
        ),
        defer_lower_value_contacts=bool(raw.get("defer_lower_value_contacts", True)),
    )
