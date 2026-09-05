# Podium

**Adaptive Revenue Recovery Intelligence** — Razorpay AI Buildathon 2026, Track 03.

Podium is a unified AI revenue-recovery system for merchants: one recovery brain with multiple revenue-risk entry points (payment failure, subscription/mandate, checkout abandonment, receivables).

## Monorepo layout

```
Podium/
  backend/     Python recovery engine + thin FastAPI adapter
  frontend/    Merchant command center (React + Vite)
```

## Core loop

Revenue at risk → State → Diagnose → Adapt → Coordinate → Allocate → Policy-check → Act → Observe → Learn

## Quick start with Docker (recommended)

From the repo root:

```bash
docker compose up --build
```

- UI:  http://localhost:3000
- API: http://localhost:8000  
- Health: http://localhost:8000/api/health

Stop with `Ctrl+C`, or background with `docker compose up --build -d`.

### Local (without Docker)

#### Backend API

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -e ".[dev]"
podium-generate          # if data/recovery.db is missing
podium-api               # http://127.0.0.1:8000
```

#### Frontend

```bash
cd frontend
npm install
# .env: VITE_DATA_MODE=api, VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev              # http://localhost:5173
```

Frontend-only (no backend):

```bash
# frontend/.env
VITE_DATA_MODE=mock
npm run dev
```

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md).

## Status

Phases 1–8: backend recovery intelligence, receivables/PTP, outcome-driven learning.

Phase 9: production-grade frontend command center (mock services).

Phase 10: frontend wired to real backend via thin FastAPI adapter (`VITE_DATA_MODE=api`).
