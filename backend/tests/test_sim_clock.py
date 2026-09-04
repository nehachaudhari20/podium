"""Phase 2 — simulated clock unit tests."""

from __future__ import annotations

from datetime import datetime, timezone

from recovery.execution.sim_clock import SimulatedClock


def test_advance_hours():
    clock = SimulatedClock(datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc))
    clock.advance_hours(24)
    assert clock.now == datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc)


def test_cooldown_remaining_hours():
    clock = SimulatedClock(datetime(2026, 2, 2, 10, 0, tzinfo=timezone.utc))
    last = datetime(2026, 2, 2, 4, 0, tzinfo=timezone.utc)
    remaining = clock.hours_until_cooldown_clear(last, cooldown_hours=24)
    assert remaining == 18


def test_cooldown_clear_returns_zero():
    clock = SimulatedClock(datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc))
    last = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    assert clock.hours_until_cooldown_clear(last, cooldown_hours=24) == 0
