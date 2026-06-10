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
    atomized_count  INTEGER         DEFAULT 0,
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
-- 3. forecasts — Forecaster 산출물 ((company, l6_main) grain 진단)
--    spec §3.1 정합 (2026-05-16 마이그레이션 적용)
--    + Optimizer hil_2 spec §3.2 (main_unit + today_conditions 2 컬럼 추가, 2026-05-16_optimizer_hil2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS forecasts (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    company TEXT NOT NULL,
    l6_main TEXT NOT NULL,

    -- 오늘 실측 (그 (company, l6_main) 단위 집계)
    today_qty_by_unit JSONB,                  -- {"m": 80.0, "ea": 12.0}
    today_assigned_workers NUMERIC,
    today_productivity NUMERIC,               -- by main_unit (max qty)
    main_unit TEXT,                           -- 생산성 산정 단위 (Forecaster 가 max qty 단위로 선택)
    today_conditions TEXT,                    -- 오늘 conditions comma-joined str (Optimizer 가 재사용)

    -- Plan 기준 (PG activity_master Σ)
    plan_total_qty_by_unit JSONB,
    plan_mh_sum NUMERIC,
    plan_start DATE,                          -- MIN(activity_master.plan_start)
    plan_finish DATE,                         -- MAX(activity_master.plan_finish)
    plan_mh_per_day NUMERIC,                  -- plan_mh_sum / (plan_finish - plan_start + 1)

    -- 누적 mh window 비교
    schedule_state TEXT,                      -- "early|on_schedule|post_due|unknown"
    window_start DATE,
    window_days INT,
    expected_in_window_mh NUMERIC,
    actual_in_window_mh NUMERIC,
    mh_gap NUMERIC,                           -- 양수 = 부족
    delay_days NUMERIC,                       -- mh_gap / plan_mh_per_day

    -- RAG
    rag_n_similar INT,
    similar_cases JSONB,                      -- top-5 brief (productivity, conditions list)

    -- 진단 (assessment 코드 ④, reasoning + recovery_likelihood LLM ⑥)
    assessment TEXT,                          -- "정상|주의|이상" or NULL (cold start)
    reasoning TEXT,
    recovery_likelihood NUMERIC,              -- 0.0~1.0 or NULL

    -- 종합 (코드 ⑦ hybrid)
    expected_completion DATE,                 -- PoC: = plan_finish 그대로. Phase 2 추세 외삽.
    risk_level TEXT,                          -- "정상|주의|이상" or NULL

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX IF NOT EXISTS idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';
CREATE INDEX IF NOT EXISTS idx_forecasts_state       ON forecasts (schedule_state);

-- ---------------------------------------------------------------------------
-- 4. optimizer_advice — Optimizer 산출물 (맥락 기반 조언)
--    spec §3.1 정합 (2026-05-16_optimizer_hil2 마이그레이션 적용)
--    +5 컬럼 (company, forecast_assessment, degradation_cases, recovery_distribution)
--    recommendations TEXT → JSONB ranked list
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS optimizer_advice (
    id                     BIGSERIAL    PRIMARY KEY,
    run_id                 UUID         NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    l6_main                TEXT         NOT NULL,
    company                TEXT,                          -- (company, l6_main) grain (Forecaster 와 정합)
    diagnosis              TEXT,                          -- '장비 대기로 인한 저하 추정'
    forecast_assessment    TEXT,                          -- '주의' | '이상' (Forecaster row 참조)
    recovery_pattern       JSONB,                         -- [{date, recovery_days}, ...]  degradation_cases 와 1:1
    degradation_cases      JSONB,                         -- retrieve.fetch_degradation_cases 결과 (감사 추적)
    recovery_distribution  JSONB,                         -- {"d+1": 3, "d+2": 1, "not_recovered": 1}
    recommendations        JSONB,                         -- [{rank, text}, ...] ranked list
    briefing               TEXT,                          -- 경영진 브리핑 한 단락 (2026-06-10 A+C)
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_optimizer_advice_run        ON optimizer_advice (run_id);
CREATE INDEX IF NOT EXISTS idx_optimizer_advice_company_l6 ON optimizer_advice (company, l6_main);

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
    -- 2026-05-17: B_Track Dashboard Layer 1 카드 필드 (api-contract.md §3.1)
    location          TEXT,
    headcount         INT,
    hours_saved       NUMERIC,
    fte_saved         NUMERIC,
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
