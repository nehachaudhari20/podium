"""Deterministic simulated clock for Phase 2 execution."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone


class SimulatedClock:
    """Advances virtual time during recovery simulation."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime.now(timezone.utc)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)

    def advance_hours(self, hours: float) -> datetime:
        if hours <= 0:
            return self.now
        self.now = self.now + timedelta(hours=hours)
        return self.now

    def hours_until_cooldown_clear(self, last_retry_at: datetime | None, cooldown_hours: int) -> float:
        if last_retry_at is None:
            return 0.0
        last = last_retry_at if last_retry_at.tzinfo else last_retry_at.replace(tzinfo=timezone.utc)
        elapsed = self.now - last
        remaining = timedelta(hours=cooldown_hours) - elapsed
        if remaining.total_seconds() <= 0:
            return 0.0
        return math.ceil(remaining.total_seconds() / 3600)
