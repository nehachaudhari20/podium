"""Thin FastAPI product API over existing Podium recovery services.

Never expose evaluator-only fields (p_pay_anyway / case_ground_truth).
"""

from __future__ import annotations

from recovery.api.main import app, create_app

__all__ = ["app", "create_app"]
