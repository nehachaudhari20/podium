-- Podium — Adaptive Revenue Recovery Intelligence
-- Phase 1 core schema

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    segment         TEXT NOT NULL CHECK (segment IN ('b2c', 'b2b_smb', 'b2b_enterprise')),
    opt_out         INTEGER NOT NULL DEFAULT 0 CHECK (opt_out IN (0, 1)),
    prior_contacts_7d INTEGER NOT NULL DEFAULT 0,
    lifetime_value  REAL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_cases (
    case_id             TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL REFERENCES customers(customer_id),
    lane                TEXT NOT NULL CHECK (
                            lane IN ('subscription_payment', 'checkout_abandonment', 'receivable')
                        ),
    amount              REAL NOT NULL CHECK (amount > 0),
    currency            TEXT NOT NULL DEFAULT 'INR',
    status              TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    workflow_state      TEXT NOT NULL DEFAULT 'detected',
    created_at          TEXT NOT NULL,
    recovery_window_end TEXT NOT NULL,
    source_ref_id       TEXT NOT NULL,
    failure_reason      TEXT,
    recoverability_hint TEXT,
    days_overdue        INTEGER,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    estimated_recovery_prob REAL,
    is_hero             INTEGER NOT NULL DEFAULT 0 CHECK (is_hero IN (0, 1)),
    UNIQUE (lane, source_ref_id)
);

-- Evaluator-only counterfactual ground truth. Runtime decision modules must NOT query this table.
CREATE TABLE IF NOT EXISTS case_ground_truth (
    case_id           TEXT PRIMARY KEY REFERENCES recovery_cases(case_id) ON DELETE CASCADE,
    p_pay_anyway      REAL NOT NULL CHECK (p_pay_anyway >= 0.0 AND p_pay_anyway <= 1.0),
    generation_seed   INTEGER NOT NULL,
    feature_snapshot  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id    TEXT PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customers(customer_id),
    case_id       TEXT REFERENCES recovery_cases(case_id),
    amount        REAL NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'INR',
    status        TEXT NOT NULL,
    failure_reason TEXT,
    payment_method TEXT,
    attempted_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL REFERENCES customers(customer_id),
    case_id         TEXT REFERENCES recovery_cases(case_id),
    plan_name       TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'INR',
    billing_cycle   TEXT NOT NULL,
    mandate_status  TEXT NOT NULL,
    failed_at       TEXT
);

CREATE TABLE IF NOT EXISTS checkout_sessions (
    session_id     TEXT PRIMARY KEY,
    customer_id    TEXT NOT NULL REFERENCES customers(customer_id),
    case_id        TEXT REFERENCES recovery_cases(case_id),
    cart_value     REAL NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'INR',
    stage          TEXT NOT NULL,
    intent_score   REAL,
    abandoned_at   TEXT NOT NULL,
    items_count    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    case_id      TEXT REFERENCES recovery_cases(case_id),
    amount       REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'INR',
    due_date     TEXT NOT NULL,
    days_overdue INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL,
    invoice_type TEXT NOT NULL DEFAULT 'b2b'
);

CREATE TABLE IF NOT EXISTS promises_to_pay (
    promise_id   TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES recovery_cases(case_id),
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    promised_amount REAL NOT NULL,
    promise_date TEXT NOT NULL,
    due_date     TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('active', 'kept', 'missed', 'cancelled')),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_history (
    contact_id   TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    case_id      TEXT REFERENCES recovery_cases(case_id),
    channel      TEXT NOT NULL,
    direction    TEXT NOT NULL DEFAULT 'outbound',
    outcome      TEXT,
    contacted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_action_log (
    action_id    TEXT PRIMARY KEY,
    case_id      TEXT NOT NULL REFERENCES recovery_cases(case_id),
    action_type  TEXT NOT NULL,
    channel      TEXT,
    cost         REAL NOT NULL DEFAULT 0,
    outcome      TEXT,
    executed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS merchant_budgets (
    budget_id    INTEGER PRIMARY KEY CHECK (budget_id = 1),
    contact_capacity_per_day      INTEGER NOT NULL,
    voice_call_slots_per_day      INTEGER NOT NULL,
    human_escalation_hours_per_day REAL NOT NULL,
    discount_budget_total         REAL NOT NULL,
    retry_attempts_pool           INTEGER NOT NULL,
    effective_from TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_customer ON recovery_cases(customer_id);
CREATE INDEX IF NOT EXISTS idx_cases_lane ON recovery_cases(lane);
CREATE INDEX IF NOT EXISTS idx_cases_status ON recovery_cases(status);
CREATE INDEX IF NOT EXISTS idx_ground_truth_case ON case_ground_truth(case_id);
