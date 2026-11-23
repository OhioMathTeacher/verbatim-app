-- Turn counts for the daily caps, and teachers' classes. No message text, no student names
-- or codes, no address.
-- Apply with --command, not --file (the D1 import API rejects the cached OAuth login):
--   npx wrangler d1 execute verbatim-class-counts --remote --command "$(cat schema.sql)"
CREATE TABLE IF NOT EXISTS counts (
  day  TEXT    NOT NULL,          -- YYYY-MM-DD (America/New_York)
  k    TEXT    NOT NULL,          -- "all" (house passcodes), "class:<id>", or "sid:" + the random session id
  n    INTEGER NOT NULL,
  PRIMARY KEY (day, k)
);

-- One row per class a teacher made on activities/teacher.html. The key and the passcode are
-- encrypted (secret CLASS_KEY); the two hashes are keyed and used only for lookup.
CREATE TABLE IF NOT EXISTS classes (
  id           TEXT    PRIMARY KEY,
  pass_hash    TEXT    NOT NULL UNIQUE,
  teacher_hash TEXT    NOT NULL UNIQUE,
  pass_enc     TEXT    NOT NULL,
  key_enc      TEXT    NOT NULL,
  name         TEXT    NOT NULL DEFAULT '',
  active       INTEGER NOT NULL DEFAULT 1,
  uses         INTEGER NOT NULL DEFAULT 0,
  created      TEXT    NOT NULL
);
