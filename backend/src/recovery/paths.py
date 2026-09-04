"""Project path helpers."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
GENERATED_DIR = DATA_DIR / "generated"
SCENARIOS_DIR = DATA_DIR / "scenarios"
DB_DIR = PROJECT_ROOT / "db"
DEFAULT_DB_PATH = DATA_DIR / "recovery.db"
