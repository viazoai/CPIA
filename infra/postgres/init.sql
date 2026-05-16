-- CPIA PostgreSQL 초기 스키마
-- Phase 0 합의 (docs/schema/postgres.md) 기반 — 본 파일과 schema 문서는 항상 동기화한다.
-- 스키마 변경은 ALTER TABLE 직접 X. infra/postgres/migrations/ 에 YYYYMMDD_*.sql 로 누적한다.
--
-- LangGraph PostgresSaver 의 `checkpoints` 테이블은 여기서 만들지 않는다
-- (PostgresSaver.setup() 이 첫 실행 시 자체 생성).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- 1. pipeline_runs — 파이프라인 실행 단위
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id          UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id         TEXT,
    report_date     DATE            NOT NULL,
    status          TEXT            NOT NULL
                                    CHECK (status IN ('running','waiting_hil_1','waiting_hil_2','completed','failed')),
    current_node    TEXT,
    error           TEXT,
    started_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_date    ON pipeline_runs (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_site    ON pipeline_runs (site_id, report_date DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status  ON pipeline_runs (status);

-- ---------------------------------------------------------------------------
-- 2. daily_reports — Reporter 산출물 (통합 작업일보 MD)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_reports (
    id              BIGSERIAL       PRIMARY KEY,
    run_id          UUID            NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    report_date     DATE            NOT NULL,
    bp_name         TEXT,
    report_md       TEXT            NOT NULL,
    history_csv_row JSONB,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_reports_run  ON daily_reports (run_id);
CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports (report_date DESC);

-- ---------------------------------------------------------------------------
-- 3. forecasts — Forecaster 산출물 (공종별 생산성 진단)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecasts (
    id                   BIGSERIAL  PRIMARY KEY,
    run_id               UUID       NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    trade                TEXT       NOT NULL,
    assessment           TEXT       NOT NULL
                                    CHECK (assessment IN ('normal','caution','risk')),
    reasoning            TEXT,
    similar_cases        JSONB,
    expected_completion  DATE,
    risk_level           TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forecasts_run   ON forecasts (run_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_trade ON forecasts (trade);

-- ---------------------------------------------------------------------------
-- 4. optimizer_advice — Optimizer 산출물 (맥락 기반 조언)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS optimizer_advice (
    id                BIGSERIAL    PRIMARY KEY,
    run_id            UUID         NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    trade             TEXT         NOT NULL,
    diagnosis         TEXT,
    recovery_pattern  JSONB,
    recommendations   TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_optimizer_advice_run ON optimizer_advice (run_id);

-- ---------------------------------------------------------------------------
-- 5. mapping_corrections — H-i-L 1 누적 (Mapper 프롬프트 feedback 데이터)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mapping_corrections (
    id            BIGSERIAL    PRIMARY KEY,
    run_id        UUID         REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    report_date   DATE         NOT NULL,
    original      JSONB        NOT NULL,
    corrected     JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mapping_corrections_date ON mapping_corrections (report_date DESC);

-- ---------------------------------------------------------------------------
-- 6. sites — Dashboard Layer 1 카드 소스 (5 mock + 1 실 PoC)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sites (
    site_id           TEXT         PRIMARY KEY,
    name              TEXT         NOT NULL,
    plan_progress     NUMERIC(5,2),
    actual_progress   NUMERIC(5,2),
    status            TEXT         CHECK (status IN ('normal','caution','risk','unknown')) DEFAULT 'unknown',
    last_run_id       UUID         REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    is_mock           BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 7. activity_master — WBS Master List (load_master_list.py 가 적재)
--    docs/schema/postgres.md §3 (Master List 적재 테이블, infra/local 와 동일)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_master (
    wbs_activity_id   TEXT PRIMARY KEY,
    wa                TEXT,
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
