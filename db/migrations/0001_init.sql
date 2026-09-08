-- 0001_init.sql
-- -----------------------------------------------------------------------
-- Replaces the flat JSON files (data/events.json, data/audit_log.jsonl,
-- data/live_links.json, data/commitments.jsonl) with real tables. This is
-- the SQL analog of Revyn's prisma/schema.prisma + prisma/migrations/0_init
-- — same idea (a real, queryable, persistent store), no Prisma/Postgres
-- dependency needed since SQLite ships in Python's standard library.
--
-- Every table uses TEXT/INTEGER/REAL only (SQLite's actual storage
-- classes) rather than pretending SQLite has a real BOOLEAN or DATETIME
-- type — booleans are stored as 0/1 INTEGER, timestamps as ISO-8601 TEXT,
-- which is what Python's sqlite3 module round-trips cleanly without a
-- custom adapter.

-- One row per synthetic (or real, once you swap generate_data.py for a
-- live API pull) at-risk revenue event. This table is INSERT-then-mostly-
-- read: events don't change after generation.
CREATE TABLE events (
    event_id                 TEXT PRIMARY KEY,
    type                     TEXT NOT NULL CHECK (type IN ('payment_failure', 'checkout_abandonment', 'overdue_invoice')),
    customer_id              TEXT NOT NULL,
    merchant_category        TEXT NOT NULL,
    amount                   REAL NOT NULL,
    currency                 TEXT NOT NULL DEFAULT 'INR',
    error_code               TEXT,           -- payment_failure only
    failure_reason           TEXT,           -- payment_failure only
    abandon_reason           TEXT,           -- checkout_abandonment only
    days_overdue             INTEGER,        -- overdue_invoice only
    prior_attempts           INTEGER NOT NULL DEFAULT 0,
    opted_out_of_comms       INTEGER NOT NULL DEFAULT 0,   -- 0/1
    created_at               TEXT NOT NULL,
    _base_recoverable_prob    REAL NOT NULL
);

-- Current progress of ONE event through diagnose -> decide -> act. This is
-- what the new per-event API endpoints read and write (mirrors Revyn's
-- src/app/api/recover/[id]/{decide,payment-link} operating on a single
-- event instead of a whole batch). A row here can be "half done" — e.g.
-- diagnosed but not yet decided — which audit_log (append-only, only
-- written once a real action is taken) deliberately cannot represent.
CREATE TABLE event_status (
    event_id                  TEXT PRIMARY KEY REFERENCES events(event_id),
    root_cause                TEXT,
    diagnosis_reasoning       TEXT,
    diagnosis_method          TEXT,   -- 'ai_llm' | 'rule_based' | 'rule_based_fallback'
    diagnosis_confidence      REAL,
    intervention              TEXT,
    intervention_reasoning    TEXT,
    payment_link_id           TEXT,
    updated_at                TEXT NOT NULL
);

-- Append-only decision history — every diagnose/decide/act cycle that
-- actually RAN (batch, promise-tracking, or a per-event API action) adds a
-- row here. Never updated in place, only inserted — this is what makes it
-- an audit trail rather than just a status cache (that's event_status's
-- job).
CREATE TABLE audit_log (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id                  TEXT NOT NULL REFERENCES events(event_id),
    run_type                  TEXT NOT NULL,   -- 'batch' | 'promise' | 'api' | 'live'
    timestamp                 TEXT NOT NULL,
    amount_at_risk            REAL NOT NULL,
    root_cause                TEXT NOT NULL,
    diagnosis_reasoning       TEXT NOT NULL,
    diagnosis_method          TEXT NOT NULL DEFAULT 'rule_based',
    diagnosis_confidence      REAL,
    intervention              TEXT NOT NULL,
    intervention_reasoning    TEXT NOT NULL,
    stopping_rule_applied     INTEGER NOT NULL DEFAULT 0,
    outcome_recovered         INTEGER,   -- NULL = not yet resolved (e.g. a pending promise)
    gross_amount_recovered    REAL NOT NULL DEFAULT 0,
    intervention_cost         REAL NOT NULL DEFAULT 0,
    net_amount_recovered      REAL NOT NULL DEFAULT 0,
    reply_category            TEXT,      -- promise-tracking runs only
    commitment_made           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_audit_log_event_id ON audit_log(event_id);
CREATE INDEX idx_audit_log_intervention ON audit_log(intervention);
CREATE INDEX idx_audit_log_recovered ON audit_log(outcome_recovered);

-- One row per commitment extracted from a (simulated, for now) customer
-- reply. status starts 'pending' and is updated in place once resolved —
-- unlike audit_log, this one DOES get updated, because "the promise" is a
-- single ongoing thing being tracked, not a log of discrete actions.
CREATE TABLE commitments (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id             TEXT NOT NULL REFERENCES events(event_id),
    raw_reply            TEXT NOT NULL,
    promised_by          TEXT,
    confidence           REAL NOT NULL,
    extraction_method    TEXT NOT NULL,   -- 'ai_llm' | 'regex_fallback'
    status               TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'kept', 'broken')),
    created_at           TEXT NOT NULL,
    resolved_at          TEXT
);
CREATE INDEX idx_commitments_event_id ON commitments(event_id);

-- Real Razorpay test-mode Payment Links. payment_link_id is Razorpay's own
-- ID, used as the primary key since it's already globally unique — no
-- reason to invent a surrogate key on top of it.
CREATE TABLE live_links (
    payment_link_id           TEXT PRIMARY KEY,
    event_id                  TEXT NOT NULL REFERENCES events(event_id),
    amount                    REAL NOT NULL,
    root_cause                TEXT NOT NULL,
    intervention              TEXT NOT NULL,
    intervention_reasoning    TEXT NOT NULL,
    short_url                 TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'created',  -- created | paid | expired | cancelled
    outcome_recovered         INTEGER NOT NULL DEFAULT 0,
    created_at                TEXT NOT NULL
);
CREATE INDEX idx_live_links_event_id ON live_links(event_id);

-- Tracks which migration files have already been applied — see db/migrate.py.
-- This is the same purpose Prisma's own internal migrations table serves.
CREATE TABLE _migrations (
    filename      TEXT PRIMARY KEY,
    applied_at    TEXT NOT NULL
);
