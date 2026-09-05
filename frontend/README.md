# Podium Frontend

Production-grade merchant command center for Adaptive Revenue Recovery Intelligence.

## Stack

- React + TypeScript + Vite
- React Router
- Tailwind CSS
- Lucide React
- Recharts (restrained analytics charts)
- Vitest + Testing Library

## Architecture

```text
UI Components
  → Frontend services (`src/services`)
    → Api* implementations when VITE_DATA_MODE=api  (default)
    → Mock* implementations when VITE_DATA_MODE=mock
      → FastAPI thin adapter
        → Existing Podium Python recovery engine
```

Domain types live in `src/types/domain.ts`. Mock seed data lives in `src/mock/` (mock mode only).

UI components must not import mock data directly — always go through services.

## Environment

Copy `.env.example` to `.env`:

```bash
VITE_DATA_MODE=api
VITE_API_BASE_URL=http://127.0.0.1:8000
```

| Value | Behavior |
|---|---|
| `api` (default) | Live backend via FastAPI |
| `mock` | Phase 9 seeded demo data (no backend required) |

Top bar shows **Live API** or **Test Mode** accordingly. Do not mix sources on one screen.

## Run with backend (Phase 10)

Terminal 1 — API:

```bash
cd backend
pip install -e ".[dev]"
podium-api
# or: uvicorn recovery.api.main:app --reload --port 8000
```

Terminal 2 — UI:

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173  
Backend: http://127.0.0.1:8000  
Health: http://127.0.0.1:8000/api/health

## Scripts

```bash
npm install
npm run dev
npm run build
npm run test
npm run lint
```

## Routes

- `/` Overview
- `/recovery` Recovery workspace
- `/recovery/:caseId` Case detail / Recovery Brain (**Run Recovery** calls backend)
- `/customers` Customer directory
- `/customers/:customerId` Customer 360
- `/revenue-risks` Revenue risks + capacity
- `/learning` Learning center
- `/analytics` Analytics
- `/simulator` Scenario lab (**Run on Backend**)
- `/audit` Audit log
- `/settings` Settings (read-only policy from YAML in API mode)

## Hero scenario (live backend)

API mode uses the real backend hero:

- Customer: **NovaTech Solutions Pvt Ltd** (`cust_hero_001`)
- Subscription `case_hero_sub_001` — ₹5,000
- Checkout `case_hero_chk_001` — ₹20,000
- Receivable `case_hero_inv_001` — ₹80,000
- Total — ₹1,05,000

Mock mode still uses the Phase 9 Priya Nair seed for frontend-only demos.

## End-to-end demo

1. Start backend + frontend (API mode)
2. Open Overview — live KPIs
3. Recovery → open a hero case
4. Inspect diagnosis / candidates / Why this action?
5. Click **Run Recovery** — Python agentic loop executes
6. Outcome + audit update from backend
7. Customer 360 + Learning + Audit reflect the run
