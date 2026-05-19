-- Phase B: daily_reports 에 view jsonb 8개 + mapper_activities 에 cum_workers 2 컬럼

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS kpi_jsonb              JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS contractor_bars_jsonb  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS trade_bars_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS quadrant_jsonb         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS wp_summary_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS s_curve_jsonb          JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS optimizer_view_jsonb   JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS productivity_jsonb     JSONB DEFAULT '{}'::jsonb;

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS site_id text;

CREATE UNIQUE INDEX IF NOT EXISTS daily_reports_run_site_date_uq
  ON daily_reports (run_id, site_id, report_date)
  WHERE site_id IS NOT NULL;

ALTER TABLE mapper_activities
  ADD COLUMN IF NOT EXISTS cum_workers_today      DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_actual_mh_today    DOUBLE PRECISION;
