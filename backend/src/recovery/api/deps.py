"""API dependencies — SQLite connection lifecycle."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

from recovery.db import connect, init_schema
from recovery.paths import DEFAULT_DB_PATH

# Forbidden — never SELECT or serialize these.
FORBIDDEN_API_FIELDS = frozenset({"p_pay_anyway", "case_ground_truth", "ground_truth"})


def get_db_path() -> Path:
    return DEFAULT_DB_PATH


def get_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = connect(get_db_path())
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def assert_safe_payload(payload: object, path: str = "root") -> None:
    """Defense-in-depth: reject forbidden evaluator keys in API payloads."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_API_FIELDS or "p_pay_anyway" in str(key).lower():
                raise ValueError(f"Forbidden field blocked at {path}.{key}")
            assert_safe_payload(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_safe_payload(item, f"{path}[{i}]")
