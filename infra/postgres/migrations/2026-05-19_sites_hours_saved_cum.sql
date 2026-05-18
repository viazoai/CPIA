-- G2 — sites.hours_saved_cum 컬럼 추가. 단위 = 시간 (h).
-- 적재 산식: reporter→END edge 가 ((AS_IS_MIN - TO_BE_MIN) / 60.0) × atomized_count 누적 UPDATE.
-- 상수: AS_IS_MIN=120 (일보당 사람 수작업 분), TO_BE_MIN=5 (일보당 AI 처리 분) → 1.917h/일보.

BEGIN;

ALTER TABLE sites
    ADD COLUMN IF NOT EXISTS hours_saved_cum NUMERIC DEFAULT 0 NOT NULL;

COMMENT ON COLUMN sites.hours_saved_cum IS 'cumulative hours saved since launch. UNIT: hours.';

COMMIT;
