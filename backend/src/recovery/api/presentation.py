"""Light presentation seeds used only when live backend aggregates are empty/thin.

Live values always win when they are non-zero / sufficiently populated.
Never used for diagnosis, policy, selected action, or case state.
"""

from __future__ import annotations

from typing import Any

# Learning center (Phase 9 demo density) — used only when experience store is thin.
LEARNING_SUMMARY = {
    "outcomesObserved": 12842,
    "actionsTracked": 18,
    "highConfidenceActions": 11,
    "calibrationScore": 0.084,
    "lastUpdate": "2 minutes ago",
}

LEARNING_EFFECTIVENESS = [
    {"action": "Payment Link", "attempts": 128, "recoveryRate": 72.0, "avgCost": 2.0, "trend": "up"},
    {"action": "Invoice Reminder", "attempts": 214, "recoveryRate": 64.0, "avgCost": 2.0, "trend": "flat"},
    {"action": "Retry", "attempts": 342, "recoveryRate": 57.0, "avgCost": 0.0, "trend": "up"},
    {"action": "Human Follow-up", "attempts": 92, "recoveryRate": 41.0, "avgCost": 500.0, "trend": "down"},
    {"action": "Checkout Reminder", "attempts": 186, "recoveryRate": 58.0, "avgCost": 1.0, "trend": "up"},
    {"action": "Statement Resend", "attempts": 74, "recoveryRate": 39.0, "avgCost": 1.0, "trend": "flat"},
]

LEARNING_EVIDENCE = [
    {
        "action": "Payment Link",
        "observations": 128,
        "recoveries": 92,
        "observedRecovery": 72.0,
        "confidence": "high",
    },
    {
        "action": "Invoice Reminder",
        "observations": 214,
        "recoveries": 137,
        "observedRecovery": 64.0,
        "confidence": "high",
    },
    {
        "action": "Human Follow-up",
        "observations": 92,
        "recoveries": 38,
        "observedRecovery": 41.0,
        "confidence": "medium",
    },
]

LEARNING_CHANGES = [
    {"action": "Payment Link", "delta": 6},
    {"action": "Invoice Reminder", "delta": 1},
    {"action": "Human Follow-up", "delta": -8},
]

LEARNING_CALIBRATION = [
    {"predicted": "40–50%", "observed": 47},
    {"predicted": "50–60%", "observed": 55},
    {"predicted": "60–70%", "observed": 66},
    {"predicted": "70–80%", "observed": 74},
    {"predicted": "80–90%", "observed": 84},
]

LEARNING_CROSS_LANE = [
    {"action": "Payment Link", "subscription": 61, "checkout": 54, "receivable": 72},
    {"action": "Reminder", "subscription": 55, "checkout": 62, "receivable": 64},
    {"action": "Human Follow-up", "subscription": 70, "checkout": 48, "receivable": 81},
]

LANE_RECOVERED_FALLBACK = {
    "subscription": {"recovered": 820000.0, "rate": 63.0},
    "checkout": {"recovered": 640000.0, "rate": 58.0},
    "receivable": {"recovered": 1280000.0, "rate": 71.0},
}

OVERVIEW_DELTAS = {
    "revenueAtRiskDelta": 4.2,
    "recoveredDelta": 8.1,
    "recoveryRateDelta": 1.4,
    "expectedRecoveryDelta": -2.3,
}

ANALYTICS_COSTS = {
    "interventionCost": 148000.0,
}


def thin_learning(outcomes_observed: int) -> bool:
    return outcomes_observed < 30


def merge_lane_breakdown(live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prefer live recovered; if a lane is 0, fill presentation amounts so charts aren't empty."""
    out = []
    for row in live:
        lane = row["lane"]
        recovered = float(row.get("recovered") or 0)
        rate = float(row.get("rate") or 0)
        source = "api"
        if recovered <= 0 and lane in LANE_RECOVERED_FALLBACK:
            seed = LANE_RECOVERED_FALLBACK[lane]
            recovered = seed["recovered"]
            rate = seed["rate"]
            source = "presentation"
        out.append({**row, "recovered": recovered, "rate": rate, "source": source})
    return out


def merge_learning_summary(live: dict[str, Any]) -> dict[str, Any]:
    if not thin_learning(int(live.get("outcomesObserved") or 0)):
        return {**live, "source": "api"}
    seed = LEARNING_SUMMARY
    return {
        "outcomesObserved": max(int(live.get("outcomesObserved") or 0), seed["outcomesObserved"]),
        "actionsTracked": max(int(live.get("actionsTracked") or 0), seed["actionsTracked"]),
        "highConfidenceActions": max(
            int(live.get("highConfidenceActions") or 0), seed["highConfidenceActions"]
        ),
        "calibrationScore": seed["calibrationScore"]
        if float(live.get("calibrationScore") or 1) > 0.2
        else live.get("calibrationScore", seed["calibrationScore"]),
        "lastUpdate": seed["lastUpdate"],
        "source": "presentation",
        "liveOutcomesObserved": live.get("outcomesObserved", 0),
    }


def merge_effectiveness(live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(live) >= 6 and sum(int(x.get("attempts") or 0) for x in live) >= 30:
        return [{**x, "trend": x.get("trend") or "flat"} for x in live]
    # Prefer seed table, overlay any live actions that have attempts
    by_name = {x["action"].lower(): x for x in live}
    merged = []
    for seed in LEARNING_EFFECTIVENESS:
        key = seed["action"].lower()
        if key in by_name and int(by_name[key].get("attempts") or 0) >= 5:
            live_row = by_name[key]
            merged.append(
                {
                    **seed,
                    "attempts": live_row["attempts"],
                    "recoveryRate": live_row["recoveryRate"],
                    "avgCost": live_row["avgCost"],
                    "trend": live_row.get("trend") or seed["trend"],
                    "source": "api",
                }
            )
        else:
            merged.append({**seed, "source": "presentation"})
    return merged


def merge_evidence(live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if live and sum(int(x.get("observations") or 0) for x in live) >= 30:
        return live
    return [{**x, "source": "presentation"} for x in LEARNING_EVIDENCE]


def merge_calibration(live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if live and any(float(x.get("observed") or 0) > 0 for x in live):
        return live
    return list(LEARNING_CALIBRATION)


def merge_cross_lane(live: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if live and any(
        (r.get("subscription") or 0) + (r.get("checkout") or 0) + (r.get("receivable") or 0) > 0
        for r in live
    ):
        # If rows exist but all zeros, still fall back
        nonzero = any(
            (r.get("subscription") or 0) + (r.get("checkout") or 0) + (r.get("receivable") or 0) > 0
            for r in live
        )
        if nonzero:
            return live
    return list(LEARNING_CROSS_LANE)


def learning_changes() -> list[dict[str, Any]]:
    return [{**x, "source": "presentation"} for x in LEARNING_CHANGES]
