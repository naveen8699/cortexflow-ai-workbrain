-- WorkBrain Database Schema
-- Cloud SQL instance : csql-workbrain
-- Database          : workbrain
-- Schema            : workbrain_schema
-- App user          : workbrain_user  (UPSERT access only — no DROP, TRUNCATE, etc.)
--
-- Run this as a superuser (postgres or Cloud SQL IAM admin):
--   PGPASSWORD=<ADMIN_PW> psql -h 127.0.0.1 -U postgres -d workbrain -f schema.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. SCHEMA
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS workbrain_schema;

-- All objects created below live in workbrain_schema.
-- The app connects with search_path=workbrain_schema so unqualified
-- table names (e.g. "meetings") resolve correctly.
SET search_path TO workbrain_schema;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. TABLES
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meetings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL DEFAULT 'demo_user',
    title           TEXT,
    transcript      TEXT NOT NULL,
    summary         TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    processed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS action_items (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT NOT NULL DEFAULT 'demo_user',
    meeting_id          UUID REFERENCES workbrain_schema.meetings(id) ON DELETE SET NULL,
    title               TEXT NOT NULL,
    owner               TEXT NOT NULL DEFAULT 'demo_user',
    deadline            TIMESTAMPTZ,
    priority            INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    complexity          INTEGER NOT NULL DEFAULT 3 CHECK (complexity BETWEEN 1 AND 5),
    duration_minutes    INTEGER NOT NULL DEFAULT 60,
    status              TEXT NOT NULL DEFAULT 'pending',
    calendar_event_id   TEXT,
    task_id             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cognitive_state (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT NOT NULL DEFAULT 'demo_user',
    owner               TEXT NOT NULL,
    load_score          FLOAT NOT NULL,
    capacity            FLOAT NOT NULL DEFAULT 480.0,
    overload_flag       BOOLEAN NOT NULL DEFAULT FALSE,
    context_switches    INTEGER NOT NULL DEFAULT 0,
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS decisions_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL DEFAULT 'demo_user',
    meeting_id  UUID REFERENCES workbrain_schema.meetings(id) ON DELETE SET NULL,
    agent       TEXT NOT NULL,
    decision    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    metadata    JSONB,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_meetings_user    ON workbrain_schema.meetings(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_status  ON workbrain_schema.meetings(user_id, status);
CREATE INDEX IF NOT EXISTS idx_actions_user     ON workbrain_schema.action_items(user_id);
CREATE INDEX IF NOT EXISTS idx_actions_owner    ON workbrain_schema.action_items(user_id, owner);
CREATE INDEX IF NOT EXISTS idx_actions_meeting  ON workbrain_schema.action_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_cognitive_user   ON workbrain_schema.cognitive_state(user_id, owner);
CREATE INDEX IF NOT EXISTS idx_cognitive_time   ON workbrain_schema.cognitive_state(owner, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_user   ON workbrain_schema.decisions_log(user_id);
CREATE INDEX IF NOT EXISTS idx_decisions_meet   ON workbrain_schema.decisions_log(meeting_id);
CREATE INDEX IF NOT EXISTS idx_decisions_ts     ON workbrain_schema.decisions_log(timestamp DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. PERMISSIONS FOR workbrain_user
--    Only SELECT, INSERT, UPDATE on all 4 tables.
--    No DELETE, DROP, TRUNCATE, or schema-level DDL.
-- ─────────────────────────────────────────────────────────────────────────────

-- Grant USAGE on the schema (required to see objects inside it)
GRANT USAGE ON SCHEMA workbrain_schema TO workbrain_user;

-- Grant SELECT + INSERT + UPDATE on every existing table
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA workbrain_schema TO workbrain_user;

-- Also apply to any tables created in the future (ALTER DEFAULT PRIVILEGES)
ALTER DEFAULT PRIVILEGES IN SCHEMA workbrain_schema
    GRANT SELECT, INSERT, UPDATE ON TABLES TO workbrain_user;

-- Grant usage on sequences (needed for gen_random_uuid() via pgcrypto and serial columns)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA workbrain_schema TO workbrain_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA workbrain_schema
    GRANT USAGE, SELECT ON SEQUENCES TO workbrain_user;

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. SET DEFAULT search_path FOR workbrain_user
--    So the app doesn't need to qualify every table as workbrain_schema.meetings
-- ─────────────────────────────────────────────────────────────────────────────
ALTER ROLE workbrain_user SET search_path TO workbrain_schema;

-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFY (optional — run manually to confirm)
-- ─────────────────────────────────────────────────────────────────────────────
-- \dn+                                     -- list schemas
-- \dt workbrain_schema.*                   -- list tables in schema
-- \dp workbrain_schema.*                   -- show permissions
-- SELECT current_schema();                 -- should show workbrain_schema when logged in as workbrain_user
