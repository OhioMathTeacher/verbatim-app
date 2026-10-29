-- Turn counts for the daily caps, and nothing else: no message text, no codes, no address.
-- Apply with --command, not --file (the D1 import API rejects the cached OAuth login):
--   npx wrangler d1 execute verbatim-class-counts --remote --command "$(cat schema.sql)"
CREATE TABLE IF NOT EXISTS counts (
  day  TEXT    NOT NULL,          -- YYYY-MM-DD (America/New_York)
  k    TEXT    NOT NULL,          -- "all", or "sid:" + the random session id in the student's file
  n    INTEGER NOT NULL,
  PRIMARY KEY (day, k)
);
