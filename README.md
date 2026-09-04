# Podium

**Adaptive Revenue Recovery Intelligence** — Razorpay AI Buildathon 2026, Track 03.

Podium is a unified AI revenue-recovery system for merchants: one recovery brain with multiple revenue-risk entry points (payment failure, subscription/mandate, checkout abandonment, receivables).

## Monorepo layout

```
Podium/
  backend/     Python recovery engine (src/recovery, configs, tests)
  frontend/    Merchant dashboard (Phase 8+, empty for now)
```

## Core loop

Revenue at risk → State → Diagnose → Adapt → Coordinate → Allocate → Policy-check → Act → Observe → Learn

## Quick start

All development happens in `backend/`:

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev,gemini]"
copy .env.example .env
podium-generate
pytest tests/ -q
```

See [backend/README.md](backend/README.md) for full setup and CLI commands.

## Status

Phase 1–3C complete: synthetic data, subscription recovery pipeline, recovery context, deterministic + Gemini intelligence.
