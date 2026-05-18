-- 2026-05-18: mapped_history 신규 테이블
-- 이유: WPSummaryRow.progress_pct 누적 today_qty source. Atomizer (Phase 3) 가 작업일보 mapped 항목을 적재
-- 참조: data-contract decision cpia-wpsummary-progress-path-2026-05-18
CREATE TABLE IF NOT EXISTS mapped_history (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
  report_date DATE NOT NULL,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  wa TEXT NOT NULL,
  l6_main TEXT NOT NULL,
  company TEXT NOT NULL,
  today_qty NUMERIC,
  today_assigned_workers NUMERIC,
  unit TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, wa, l6_main, company)
);
CREATE INDEX IF NOT EXISTS idx_mapped_history_site_date ON mapped_history (site_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_mapped_history_triplet  ON mapped_history (wa, l6_main, company, report_date DESC);
