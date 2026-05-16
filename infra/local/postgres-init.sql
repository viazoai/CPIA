-- 로컬 우선 PoC 스키마 — Task 10 마이그레이션 시 B 트랙 init.sql 로 교체.
-- 컬럼 정의는 docs/schema/postgres.md §2 그대로.

CREATE TABLE IF NOT EXISTS activity_master (
    wbs_activity_id   TEXT PRIMARY KEY,
    wa                TEXT,                              -- 'CUB' / 'FAB' (Master C4)
    l5_disc           TEXT NOT NULL,
    l6_main           TEXT,
    l6_code           TEXT,
    l7_sub            TEXT,
    l7_code           TEXT,
    l7_5_activity     TEXT,
    sub_work_area     TEXT,
    company           TEXT,
    unit              TEXT,
    plan_total_qty    NUMERIC,
    plan_mh_rev2      NUMERIC,
    plan_mh_rev1      NUMERIC,
    plan_mh_rev0      NUMERIC,
    plan_wv           NUMERIC,
    plan_start        DATE,
    plan_finish       DATE,
    actual_start      DATE,
    actual_finish     DATE,
    source_file       TEXT,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_actmaster_lookup ON activity_master (l5_disc, company, unit);
CREATE INDEX IF NOT EXISTS idx_actmaster_wa_l6 ON activity_master (wa, l6_main);
CREATE INDEX IF NOT EXISTS idx_actmaster_period ON activity_master (plan_start, plan_finish);
