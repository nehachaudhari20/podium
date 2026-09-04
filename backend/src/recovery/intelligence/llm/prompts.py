"""Prompt templates for LLM intelligence."""

from __future__ import annotations

import json

import yaml

from recovery.intelligence.diagnosis import VALID_CAUSES
from recovery.intelligence.llm.sanitize import context_for_prompt
from recovery.models.recovery_context import RecoveryContext
from recovery.paths import CONFIG_DIR

_ACTIONS_PATH = CONFIG_DIR / "actions.yaml"
_CATALOG_CACHE: dict[str, dict[str, str]] | None = None


def _load_action_catalog() -> dict[str, dict[str, str]]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        with _ACTIONS_PATH.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        actions = data.get("actions") or []
        _CATALOG_CACHE = {
            a["id"]: {"label": a.get("label", a["id"]), "channel": a.get("channel", "system")}
            for a in actions
            if isinstance(a, dict) and "id" in a
        }
    return _CATALOG_CACHE


def valid_action_ids() -> frozenset[str]:
    return frozenset(_load_action_catalog())


def action_metadata(action_id: str) -> dict[str, str]:
    catalog = _load_action_catalog()
    if action_id not in catalog:
        raise ValueError(f"Unknown action_id: {action_id!r}")
    return catalog[action_id]


_REASONING_SCHEMA = {
    "summary": "string — concise interpretation of the recovery situation",
    "likely_cause": f"one of {list(VALID_CAUSES)}",
    "confidence": "float 0.0-1.0",
    "key_factors": ["string factors supporting the interpretation"],
}

_STRATEGY_SCHEMA = {
    "strategies": [
        {
            "action_id": "id from the allowed action catalog",
            "rationale": "why this action fits the context",
            "priority": "integer rank (1 = highest)",
            "confidence": "float 0.0-1.0",
        }
    ]
}


def _context_block(context: RecoveryContext) -> str:
    safe = context_for_prompt(context)
    return json.dumps(safe, indent=2, sort_keys=True)


def build_reasoning_prompt(context: RecoveryContext) -> tuple[str, str]:
    system = (
        "You are Podium's recovery reasoning engine for Razorpay revenue recovery. "
        "Interpret the provided RecoveryContext and propose a diagnosis interpretation. "
        "Respond with JSON only — no markdown, no prose outside the JSON object. "
        "Never infer or mention hidden evaluator fields such as p_pay_anyway or ground truth. "
        "You propose interpretation only; you do not execute actions."
    )
    user = (
        "Analyze this recovery context and return JSON matching this schema:\n"
        f"{json.dumps(_REASONING_SCHEMA, indent=2)}\n\n"
        f"RecoveryContext:\n{_context_block(context)}"
    )
    return system, user


def build_strategy_prompt(
    context: RecoveryContext,
    reasoning_summary: str,
    likely_cause: str,
) -> tuple[str, str]:
    action_ids = sorted(valid_action_ids())
    system = (
        "You are Podium's recovery strategy planner. "
        "Given recovery context and reasoning, propose ranked recovery actions. "
        "Use only action_id values from the allowed catalog. "
        "Respond with JSON only — no markdown, no prose outside the JSON object. "
        "You propose strategies only; you do not execute actions."
    )
    user = (
        "Given the reasoning below, propose recovery strategies as JSON matching this schema:\n"
        f"{json.dumps(_STRATEGY_SCHEMA, indent=2)}\n\n"
        f"Allowed action_id values: {action_ids}\n\n"
        f"Reasoning summary: {reasoning_summary}\n"
        f"Likely cause: {likely_cause}\n\n"
        f"RecoveryContext:\n{_context_block(context)}"
    )
    return system, user
