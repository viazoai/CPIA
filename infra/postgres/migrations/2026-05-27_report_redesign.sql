-- 2026-05-27_report_redesign.sql
-- 본 spec: docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md §4.2.7
-- nullable + default 없음 → Postgres metadata-only, lock < 1s

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS site_summary_text TEXT;

ALTER TABLE forecasts
  ADD COLUMN IF NOT EXISTS point_in_time_delay_days INTEGER;
