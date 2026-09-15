-- Ledger schema for the foreman skill: loops, receipts, verifications, decisions, dispatches.
--
-- Load it with:  sqlite3 foreman.db < ledger/schema.sql
-- The CLI does this for you:  python3 ledger/foreman.py init
--
-- The ledger is the only place work lives. A loop is not done because a model
-- said so; it is done because the receipts and the verification exist.

PRAGMA foreign_keys = ON;

-- One row per piece of work. Everything else in this file hangs off a loop.
CREATE TABLE IF NOT EXISTS loops (
  id          INTEGER PRIMARY KEY,          -- loop number, printed by the CLI
  title       TEXT NOT NULL,                -- one line stating the work
  owner       TEXT,                         -- lane or person accountable for it
  state       TEXT NOT NULL DEFAULT 'open'  -- lifecycle state, one of the six below
              CHECK (state IN ('open', 'claimed', 'blocked', 'needs_you', 'done', 'killed')),
  task_class  TEXT,                         -- lane key from templates/routing.yaml, for example coder
  created_at  TEXT NOT NULL,                -- ISO 8601 UTC, set when the loop is added
  updated_at  TEXT NOT NULL,                -- ISO 8601 UTC, rewritten on every state change
  due_at      TEXT,                         -- ISO 8601 UTC or YYYY-MM-DD, null when there is no date
  parent_id   INTEGER REFERENCES loops (id),-- parent loop, null for a top-level loop
  notes       TEXT                          -- free text: block reason, kill reason, context
);

-- The scanner and the list command both filter on state, so index it.
CREATE INDEX IF NOT EXISTS idx_loops_state ON loops (state);

-- Artifacts filed against a loop. Four kinds cover the doctrine: the brief sent
-- out, the worker output that came back, each inspector verdict, and the
-- verification receipt. A loop cannot reach done without an inspection receipt
-- with verdict PASS and a verification receipt.
CREATE TABLE IF NOT EXISTS receipts (
  id         INTEGER PRIMARY KEY,           -- receipt number
  loop_id    INTEGER NOT NULL REFERENCES loops (id) ON DELETE CASCADE,
  kind       TEXT NOT NULL                  -- which of the four artifacts this is
             CHECK (kind IN ('brief', 'worker_output', 'inspection', 'verification')),
  path       TEXT NOT NULL,                 -- file on disk holding the artifact
  model      TEXT,                          -- model that produced the artifact
  verdict    TEXT                           -- PASS or FAIL for inspections, null otherwise
             CHECK (verdict IS NULL OR verdict IN ('PASS', 'FAIL')),
  created_at TEXT NOT NULL                  -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_receipts_loop ON receipts (loop_id);
CREATE INDEX IF NOT EXISTS idx_receipts_loop_kind ON receipts (loop_id, kind, verdict);

-- Independent checks of a claim. The verifier is never the worker that made the
-- claim, and the method is a command, a query or a read-back, not an opinion.
CREATE TABLE IF NOT EXISTS verifications (
  id            INTEGER PRIMARY KEY,        -- verification number
  loop_id       INTEGER NOT NULL REFERENCES loops (id) ON DELETE CASCADE,
  method        TEXT NOT NULL,              -- how the claim was checked, for example: ran the suite
  result        TEXT NOT NULL,              -- what the check returned, for example: 42 passed
  evidence_path TEXT,                       -- file holding the raw output of the check
  created_at    TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_verifications_loop ON verifications (loop_id);

-- Questions are rows, never prose in a chat. One question per row, with the
-- options offered, the option chosen, and who ruled.
CREATE TABLE IF NOT EXISTS decisions (
  id         INTEGER PRIMARY KEY,           -- decision number
  loop_id    INTEGER NOT NULL REFERENCES loops (id) ON DELETE CASCADE,
  question   TEXT NOT NULL,                 -- the single question being asked
  options    TEXT,                          -- comma separated list of choices offered
  chosen     TEXT,                          -- the option picked, null until ruled
  decided_by TEXT,                          -- who ruled on it
  created_at TEXT NOT NULL                  -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_decisions_loop ON decisions (loop_id);

-- One row per model call sent to a worker or an inspector. This is the evidence
-- the bake-off reads: who ran, in which class, at what cost, with how many
-- blockers and how many retries before a pass.
CREATE TABLE IF NOT EXISTS dispatches (
  id         INTEGER PRIMARY KEY,           -- dispatch number
  loop_id    INTEGER NOT NULL REFERENCES loops (id) ON DELETE CASCADE,
  task_class TEXT,                          -- lane the work belongs to
  model      TEXT NOT NULL,                 -- model that ran
  effort     TEXT,                          -- reasoning effort setting, when the model takes one
  latency_ms INTEGER,                       -- wall clock time of the call in milliseconds
  tokens_in  INTEGER,                       -- input tokens billed
  tokens_out INTEGER,                       -- output tokens billed
  quota_pool TEXT,                          -- subscription or quota pool the call drew from
  blockers   INTEGER NOT NULL DEFAULT 0,    -- inspector blockers this dispatch produced
  retries    INTEGER NOT NULL DEFAULT 0,    -- retries needed before the work passed
  verdict    TEXT,                          -- PASS or FAIL for the dispatch as a whole
  created_at TEXT NOT NULL                  -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_dispatches_loop ON dispatches (loop_id);
CREATE INDEX IF NOT EXISTS idx_dispatches_class ON dispatches (task_class, created_at);

-- Loops that can be picked up right now: open, with no blocker left standing.
-- An inspection FAIL counts as a blocker that is still standing until a later
-- inspection on the same loop returns PASS.
CREATE VIEW IF NOT EXISTS loops_ready AS
SELECT *
FROM loops l
WHERE l.state = 'open'
  AND NOT EXISTS (
    SELECT 1
    FROM receipts f
    WHERE f.loop_id = l.id
      AND f.kind = 'inspection'
      AND f.verdict = 'FAIL'
      AND NOT EXISTS (
        SELECT 1
        FROM receipts p
        WHERE p.loop_id = l.id
          AND p.kind = 'inspection'
          AND p.verdict = 'PASS'
          AND p.id > f.id
      )
  );

-- The gate. A loop may not move to done until the evidence for it exists.
-- The message is written for a person, because it is the message a session will
-- read out loud when it tries to close a loop early.
CREATE TRIGGER IF NOT EXISTS loops_done_requires_evidence
BEFORE UPDATE OF state ON loops
WHEN NEW.state = 'done'
  AND OLD.state <> 'done'
  AND (
    NOT EXISTS (
      SELECT 1 FROM receipts
      WHERE loop_id = NEW.id AND kind = 'inspection' AND verdict = 'PASS'
    )
    OR NOT EXISTS (
      SELECT 1 FROM receipts
      WHERE loop_id = NEW.id AND kind = 'verification'
    )
  )
BEGIN
  SELECT RAISE(ABORT, 'a loop cannot be done without an inspection receipt with verdict PASS and a verification receipt');
END;

-- A loop cannot be born done either. Evidence comes first.
CREATE TRIGGER IF NOT EXISTS loops_insert_done_refused
BEFORE INSERT ON loops
WHEN NEW.state = 'done'
BEGIN
  SELECT RAISE(ABORT, 'a loop cannot be created in state done');
END;
