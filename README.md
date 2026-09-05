# Podium

**Adaptive Revenue Recovery Intelligence** — Razorpay AI Buildathon 2026, Track 03.

Podium is a unified AI revenue-recovery system for merchants: one recovery brain with multiple revenue-risk entry points (payment failure, subscription/mandate, checkout abandonment, receivables).

## Monorepo layout

```
Podium/
  backend/     Python recovery engine (src/recovery, configs, tests)
  frontend/    Merchant command center (React + Vite, mock-backed Phase 9)
```

## Core loop

Revenue at risk → State → Diagnose → Adapt → Coordinate → Allocate → Policy-check → Act → Observe → Learn

## Quick start

### Backend

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

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens the Phase 9 command center on Vite (mock services — no backend required).

See [frontend/README.md](frontend/README.md) for routes, architecture, and scripts.

## Status

Phases 1–8: backend recovery intelligence, receivables/PTP, outcome-driven learning.

Phase 9: production-grade frontend command center (mock service layer; API integration in Phase 10).
