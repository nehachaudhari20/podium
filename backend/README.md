# Podium Backend

Adaptive Revenue Recovery Intelligence — Python engine (Razorpay AI Buildathon 2026).

## Layout

```
backend/
  src/recovery/   Core Python package (import as `recovery`)
  config/         Policy, budgets, actions
  data/           Generated datasets and scenarios
  db/             SQLite schema
  scripts/        CLI helpers
  tests/          Test suite
```

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
podium-run-case --case-id case_0012
python scripts/smoke_gemini_reasoning.py case_0012
pytest tests/ -q
```
