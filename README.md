# Podium — Adaptive Revenue Recovery Intelligence

**Podium** is an adaptive revenue recovery intelligence platform designed to help merchants recover revenue that is at risk across the entire customer journey.

Revenue loss rarely happens in isolation. A customer may experience a failed subscription payment, abandon a high-intent checkout, or have an overdue invoice — sometimes all at the same time.

Podium brings these revenue risks into a **single recovery brain** that can understand context, decide what intervention makes sense, coordinate actions across revenue streams, enforce business constraints, execute recovery actions, observe outcomes, and learn from them.

### The Podium Loop

**Detect → Understand → Decide → Coordinate → Act → Observe → Learn**

---

## What Podium Does

Podium turns fragmented revenue-recovery workflows into a unified, adaptive recovery system.

For every revenue-risk case, Podium can:

* Understand the customer's current recovery context
* Diagnose the likely reason behind the revenue risk
* Generate and evaluate multiple recovery actions
* Estimate the potential value of each intervention
* Account for intervention cost and available recovery capacity
* Coordinate recovery actions across the same customer's revenue streams
* Apply deterministic policies and business constraints before execution
* Execute simulated recovery interventions
* Observe the resulting outcome
* Re-plan when the situation changes
* Learn from historical recovery outcomes

The result is a system that doesn't simply ask **"How do we recover this payment?"**

It asks:

> **"What is the best recovery decision for this customer, at this moment, given the context, economics, constraints, and previous outcomes?"**

---

## Key Features

### 1. Unified Revenue Recovery

Podium supports multiple revenue-risk entry points through a common recovery framework:

* **Subscription & payment failures**
* **Checkout abandonment**
* **Receivables & overdue invoices**
* **Promise-to-pay recovery**

Instead of creating a separate recovery workflow for every revenue problem, Podium applies a shared recovery lifecycle across them.

### 2. Stateful Recovery

Every recovery case has a persistent state rather than being treated as a one-time event.

Cases can move through states such as:

**Detected → Diagnosed → Waiting → Action → Outcome → Recovered / Escalated / Exhausted**

The system remembers previous actions, outcomes, cooldowns, contacts, promises, and recovery attempts.

This allows Podium to answer:

**"What has already happened with this customer?"**

before deciding what should happen next.

### 3. Adaptive Recovery Intelligence

Podium combines multiple forms of intelligence rather than relying on a single model.

It uses:

* Deterministic signals for reliable facts
* Statistical / ML-style signals for recovery estimation
* LLM reasoning for contextual interpretation and strategy generation
* Historical outcomes as learning evidence
* A closed-loop agentic process for observe → reason → plan → act → observe → re-plan

The system is designed so that intelligence proposes decisions while deterministic systems enforce the rules governing them.

### 4. Economic Decision-Making

Not every recoverable rupee is worth pursuing at any cost.

Podium evaluates recovery actions using:

**Expected Recovery Value**

`Amount at Risk × Estimated Recovery Probability`

and:

**Expected Net Value**

`Expected Recovery Value − Intervention Cost`

This allows Podium to distinguish between:

* A cheap intervention that is highly efficient
* An expensive intervention that is justified for a high-value case
* An intervention whose expected value is negative
* Cases that should be deferred when recovery capacity is scarce

### 5. Cross-Revenue Coordination

A customer can have multiple revenue risks simultaneously.

Podium creates a customer-level recovery view so different recovery workflows don't blindly compete with each other.

It can detect situations such as:

* Multiple contact attempts too close together
* Conflicting recovery actions
* Multiple incentives being offered
* Limited human-escalation capacity
* Customer recovery fatigue

Podium can therefore **sequence, defer, or consolidate recovery actions** instead of treating every case independently.

### 6. Policy-Governed Recovery

Adaptive intelligence does not have unrestricted control.

Deterministic policy remains authoritative.

Podium can enforce constraints such as:

* Contact limits
* Cooldown periods
* Incentive ceilings
* Human escalation limits
* Recovery capacity
* Customer opt-out
* Escalation thresholds

**AI recommends. The system enforces.**

Every important policy decision can also be recorded in the audit trail.

### 7. Promise-to-Pay Recovery

For receivables, Podium supports a structured **Promise-to-Pay** lifecycle.

A recovery case can move through:

**Overdue → Promise Requested → Promise Active → Promise Due → Payment Observed → Kept / Broken / Partial**

A promise becomes part of the customer's recovery state.

If the promise is kept, the case can be recovered.

If it is broken, Podium can treat that as a new observation and re-plan the recovery strategy.

Partial payments are also supported so the system can track the remaining exposure.

### 8. Outcome-Driven Learning

Recovery doesn't end when an action is executed.

Podium records what actually happened and uses those outcomes as learning evidence.

It tracks signals such as:

* Action effectiveness
* Observed recovery outcomes
* Historical observations
* Prediction confidence
* Calibration
* Cross-lane performance
* Re-planning behavior

This allows future recovery decisions to be informed by what has actually worked before.

### 9. Explainable Recovery Decisions

Podium doesn't hide the reasoning behind a recovery action.

For a case, the merchant can inspect:

* Customer context
* Diagnosis
* Candidate actions
* Recovery estimates
* Intervention costs
* Expected net value
* Coordination constraints
* Policy checks
* Selected action
* Outcome
* Learning evidence

The goal is not just to provide an answer, but to make the recovery decision understandable.

### 10. Recovery Simulation

Podium includes a scenario-driven recovery simulator for observing the complete recovery loop.

Scenarios can demonstrate:

* Payment failures
* Checkout abandonment
* Receivable recovery
* Promise-to-pay
* Broken promises
* Re-planning
* Capacity constraints
* Cross-revenue coordination

The simulator makes it possible to observe how Podium changes its decision as new events and outcomes occur.

### 11. Customer-Level Recovery View

Podium treats the **customer**, not just the transaction, as an important unit of recovery.

A Customer 360 view can bring together:

* Subscription risk
* Checkout risk
* Receivable risk
* Recovery history
* Current state
* Contact history
* Coordination decisions
* Recovery outcomes

This allows merchants to understand the customer's complete revenue relationship before deciding what to do next.

### 12. Full Recovery Audit Trail

Recovery decisions are observable from detection through outcome.

Podium records events around:

* State transitions
* Intelligence decisions
* Economics
* Coordination
* Policy
* Actions
* Outcomes
* Learning

This creates an auditable history of **what Podium decided, why it decided it, and what happened afterward.**

---

## The Core Idea

Podium brings five capabilities together:

**Stateful Recovery**  
Remember what has already happened.

**Adaptive Recovery**  
Determine what should happen next.

**Economic Decision-Making**  
Determine what is worth doing.

**Cross-Revenue Coordination**  
Understand the customer as a whole.

**Outcome-Driven Learning**  
Improve future decisions from observed results.

Together, they create a continuous recovery loop:

**Revenue Risk → Context → Intelligence → Economics → Coordination → Policy → Action → Outcome → Learning**

### Podium in One Line

> **Podium doesn't just identify revenue at risk — it continuously decides how that revenue should be recovered across the entire customer relationship.**

---

## Repository layout

```
Podium/
  backend/          Python recovery engine + thin FastAPI adapter
  frontend/         Merchant command center (React + Vite + TypeScript)
  docker-compose.yml
```

| Layer | Role |
|---|---|
| **Backend** | Source of truth for recovery intelligence, economics, policy, simulation, and learning |
| **Frontend** | Ops command center UI (Overview, Recovery, Customer 360, Simulator, Learning, Audit, …) |
| **API adapter** | Thin FastAPI layer — no duplicated business logic |

---

## How to run

### Option A — Docker Compose (recommended)

Runs **frontend + backend** together — the full product in one command.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose).

From the repo root:

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| **UI** | http://localhost:3000 |
| **API** | http://localhost:8000 |
| **Health** | http://localhost:8000/api/health |

- First start generates `recovery.db` inside the backend container if it is missing.
- Stop with `Ctrl+C`, or run in the background: `docker compose up --build -d`
- Tear down: `docker compose down`

Optional LLM (Gemini) for richer reasoning: set `GEMINI_API_KEY` in `backend/.env` before building, or pass it via Compose `environment` / env file. Without a key, the engine falls back to deterministic intelligence.

---

### Option B — Local development (without Docker)

Run API and UI in two terminals.

#### 1. Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
# source venv/bin/activate

pip install -e ".[dev]"
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
# Optional: set GEMINI_API_KEY in .env

podium-generate                 # if data/recovery.db is missing
podium-api                      # http://127.0.0.1:8000
```

#### 2. Frontend

```bash
cd frontend
npm install
copy .env.example .env          # Windows
# cp .env.example .env          # macOS / Linux
```

Ensure `frontend/.env` contains:

```env
VITE_DATA_MODE=api
VITE_API_BASE_URL=http://127.0.0.1:8000
```

```bash
npm run dev                     # http://localhost:5173
```

#### Frontend-only (mock data, no backend)

```env
VITE_DATA_MODE=mock
```

```bash
cd frontend
npm run dev
```

The top bar shows **Live API** or **Test Mode**. Do not mix live and mock sources on one screen.

---

## Useful commands

| Command | Where | Purpose |
|---|---|---|
| `docker compose up --build` | repo root | Full stack |
| `podium-api` | `backend/` | Start FastAPI |
| `podium-generate` | `backend/` | Generate SQLite demo DB |
| `podium-run-case --case-id …` | `backend/` | Run one case from CLI |
| `pytest tests/ -q` | `backend/` | Backend tests |
| `npm run dev` | `frontend/` | Vite dev server |
| `npm run test` | `frontend/` | Frontend tests |
| `npm run build` | `frontend/` | Production build |

---

## Demo hero customer

- **Customer:** NovaTech Solutions Pvt Ltd (`cust_hero_001`)
- **Cases:** `case_hero_sub_001` · `case_hero_chk_001` · `case_hero_inv_001`

Use these in Recovery, Customer 360, and the simulator for the end-to-end demo path.

---

## More detail

- [backend/README.md](backend/README.md) — engine setup, CLI, API endpoints
- [frontend/README.md](frontend/README.md) — UI architecture, env modes, routes

---

## License / context

Built for **Razorpay AI Buildathon 2026** (Track 03).
