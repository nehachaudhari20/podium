# Podium

**Adaptive Revenue Recovery Intelligence** — Razorpay AI Buildathon 2026, Track 03.

Podium is a unified AI revenue-recovery system for merchants: one recovery brain with multiple revenue-risk entry points (payment failure, subscription/mandate, checkout abandonment, receivables).

## Core loop

Revenue at risk → State → Diagnose → Adapt → Coordinate → Allocate → Policy-check → Act → Observe → Learn

## Repository layout

```
config/          Policy, budgets, and action definitions
data/            Generated datasets and hand-crafted scenarios
db/              SQLite schema and seeds
src/podium/      Core recovery modules
scripts/         CLI entry points
tests/           Test suite
app/             Dashboard / API (later phases)
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

## Status

Repository scaffold only. Implementation follows phased rollout (Phase 1: synthetic data — not yet started).
