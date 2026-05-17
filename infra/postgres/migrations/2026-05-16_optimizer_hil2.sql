-- CPIA Optimizer + hil_2 + synthetic v2 spec (2026-05-16, v3.1) 정합 마이그레이션
-- 산물: spec §3.1 (optimizer_advice 5 컬럼) + §3.2 (forecasts 2 컬럼 — today_productivity 는 Phase 1 시점 이미 있음)

BEGIN;

-- 1. optimizer_advice 5 컬럼 추가 + recommendations TEXT→JSONB
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS forecast_assessment TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS degradation_cases JSONB;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS recovery_distribution JSONB;
ALTER TABLE optimizer_advice ALTER COLUMN recommendations TYPE JSONB
    USING (CASE WHEN recommendations IS NULL THEN NULL ELSE recommendations::JSONB END);

CREATE INDEX IF NOT EXISTS idx_optimizer_advice_company_l6 ON optimizer_advice (company, l6_main);
CREATE INDEX IF NOT EXISTS idx_optimizer_advice_run ON optimizer_advice (run_id);

-- 2. forecasts 2 컬럼 추가 (main_unit + today_conditions) — today_productivity 은 이미 있음
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS main_unit TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_conditions TEXT;

COMMIT;

-- Rollback policy: forward-only (PoC). ALTER COLUMN recommendations TYPE JSONB 부분은
-- 1회용 — 재실행 시 PG 가 same-type ALTER 를 허용하더라도 cast 노이즈 발생 가능.
-- DB 가 이미 적용된 환경에서는 본 마이그레이션 전체를 다시 돌리지 말 것.
