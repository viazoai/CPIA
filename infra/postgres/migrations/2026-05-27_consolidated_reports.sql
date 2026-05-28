-- infra/postgres/migrations/2026-05-27_consolidated_reports.sql
-- (D-1 / D-2 / D-3 / D-4 / S-1) graph cycle 마다 1번 UPSERT — site×date 합집합 xlsx 사전생성
-- 본 cycle: 2026-05-27-cpia-exporter-graph-integration-design.md

CREATE TABLE IF NOT EXISTS consolidated_reports (
  site_id       TEXT        NOT NULL REFERENCES sites(site_id),
  report_date   DATE        NOT NULL,
  xlsx_bytes    BYTEA       NOT NULL,
  run_id        UUID        NOT NULL REFERENCES pipeline_runs(run_id),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  byte_size     INTEGER     GENERATED ALWAYS AS (length(xlsx_bytes)) STORED,
  is_mock       BOOLEAN     NOT NULL DEFAULT FALSE,
  PRIMARY KEY (site_id, report_date)
);

CREATE INDEX IF NOT EXISTS idx_consolidated_reports_date
  ON consolidated_reports (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_consolidated_reports_run
  ON consolidated_reports (run_id);

COMMENT ON TABLE consolidated_reports IS
  '(B-1 / T-A / N-1 / S-1) graph cycle 마다 1번 UPSERT — site×date 합집합 xlsx 사전생성. 본 cycle 2026-05-27.';
