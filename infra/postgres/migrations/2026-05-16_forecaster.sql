-- CPIA Forecaster spec (2026-05-16) 정합 마이그레이션
-- 산물: spec §3.1 / §13.2

BEGIN;

-- forecasts 컬럼 추가 (없으면)
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_qty_by_unit JSONB;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_productivity NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_total_qty_by_unit JSONB;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_finish DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_mh_per_day NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS schedule_state TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_days INT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS expected_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS actual_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS mh_gap NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS recovery_likelihood NUMERIC;

-- delay_days INT → NUMERIC (PoC 빈 테이블 가정, USING noop)
ALTER TABLE forecasts ALTER COLUMN delay_days TYPE NUMERIC USING delay_days::NUMERIC;

-- index 추가
CREATE INDEX IF NOT EXISTS idx_forecasts_state ON forecasts (schedule_state);

COMMIT;
