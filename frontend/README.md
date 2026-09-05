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
    → Mock implementations (Phase 9)
    → Real API adapters (Phase 10)
```

Domain types live in `src/types/domain.ts`. Seeded data lives in `src/mock/`.

UI components must not import mock data directly — always go through services.

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
- `/recovery/:caseId` Case detail / Recovery Brain
- `/customers` Customer directory
- `/customers/:customerId` Customer 360
- `/revenue-risks` Revenue risks + capacity
- `/learning` Learning center
- `/analytics` Analytics
- `/simulator` Scenario lab
- `/audit` Audit log
- `/settings` Settings

## Hero scenario

Priya Nair (`C1029`) with:

- Subscription ₹2,499
- Checkout ₹7,400
- Receivable ₹38,000
- Total ₹47,899

## Notes

- Top bar shows **Test Mode** while services are mock-backed.
- No backend API integration in this phase.
