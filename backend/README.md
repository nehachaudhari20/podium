# Podium Backend

Adaptive Revenue Recovery Intelligence — Python engine (Razorpay AI Buildathon 2026).

## Layout

```
backend/
  src/recovery/   Core Python package (import as `recovery`)
    api/          Thin FastAPI product adapter (Phase 10)
  config/         Policy, budgets, actions
  data/           Generated datasets and scenarios
  db/             SQLite schema
  scripts/        CLI helpers
  tests/          Test suite
```

## Docker

From the monorepo root:

```bash
docker compose up --build
```

Backend image: `backend/Dockerfile` (API on port 8000).  
Frontend image: `frontend/Dockerfile` (nginx on port 3000).

On first start the backend entrypoint generates `data/recovery.db` if missing.

## Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -e ".[dev,gemini]" # required — makes `recovery` importable
```

Copy env template and add your Gemini key:

```bash
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
```

## Commands

```bash
podium-generate
podium-run-case --case-id case_hero_sub_001
podium-api                     # HTTP API on http://127.0.0.1:8000
python scripts/smoke_gemini_reasoning.py case_hero_sub_001
pytest tests/ -q
```

## HTTP API (Phase 10)

Thin FastAPI layer over existing recovery services — **no duplicated business logic**.

```bash
podium-api
# or: uvicorn recovery.api.main:app --reload --host 127.0.0.1 --port 8000
```

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Liveness |
| `GET /api/overview` | KPIs, pulse, opportunities, active cases |
| `GET /api/customers` | Customer directory |
| `GET /api/customers/{id}` | Customer 360 |
| `GET /api/recovery/cases` | Recovery workspace |
| `GET /api/recovery/cases/{id}` | Case brain (live propose) |
| `POST /api/recovery/cases/{id}/run` | Execute agentic recovery |
| `GET /api/learning/*` | Learning summary / actions / calibration |
| `GET /api/analytics` | Portfolio analytics |
| `GET /api/audit` | Audit trail |
| `GET /api/scenarios` + `POST .../run` | Backend-aware simulator |
| `GET /api/config` | Read-only policy/economics YAML |
| `GET /api/search` | Global search |
| `GET /api/notifications` | Derived operational alerts |

CORS is limited to local Vite origins (`localhost:5173`, `4173`).

**Never exposed:** `p_pay_anyway`, `case_ground_truth`, or other evaluator-only fields.

## Hero customer

- `cust_hero_001` — NovaTech Solutions Pvt Ltd
- `case_hero_sub_001` / `case_hero_chk_001` / `case_hero_inv_001`
