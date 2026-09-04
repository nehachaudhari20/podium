#!/usr/bin/env python3
"""Smoke test Gemini reasoning for one recovery case."""

from __future__ import annotations

import sys

from recovery.db import connect
from recovery.env_loader import load_project_env
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
from recovery.paths import DEFAULT_DB_PATH


def main() -> None:
    load_project_env()
    case_id = sys.argv[1] if len(sys.argv) > 1 else "case_0012"
    conn = connect(DEFAULT_DB_PATH)
    try:
        context = build_recovery_context(conn, case_id)
        insight = GeminiReasoningIntelligence().interpret(context)
        print(insight)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
