-- 2026-05-18: forecasts grain 을 (run_id, company, l6_main) → (run_id, wa, company, l6_main) 로 확장
-- 이유: WPSummaryRow grain 결정 (wa, l6_main, company) triplet 반영
-- 참조: data-contract decision cpia-wpsummary-grain-2026-05-18
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS wa TEXT;
DROP INDEX IF EXISTS idx_forecasts_company_l6;
CREATE INDEX IF NOT EXISTS idx_forecasts_wa_company_l6 ON forecasts (wa, company, l6_main);
