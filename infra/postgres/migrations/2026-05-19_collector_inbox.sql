-- 2026-05-19 — collector_inbox 신규 (메일 dedup + run 추적)
-- Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §5.3

BEGIN;

CREATE TABLE IF NOT EXISTS collector_inbox (
  message_id          TEXT PRIMARY KEY,
  received_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  site_id             TEXT NOT NULL,
  report_date         DATE NOT NULL,
  bp_name             TEXT NOT NULL,
  attachment_filename TEXT NOT NULL,
  attachment_path     TEXT NOT NULL,
  run_id              UUID REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
  parse_status        TEXT NOT NULL DEFAULT 'pending'
                        CHECK (parse_status IN ('pending','running','completed','failed','dead_letter')),
  error               TEXT,
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS collector_inbox_site_date_idx
  ON collector_inbox (site_id, report_date);

CREATE INDEX IF NOT EXISTS collector_inbox_status_idx
  ON collector_inbox (parse_status)
  WHERE parse_status IN ('pending','running','failed');

COMMIT;
