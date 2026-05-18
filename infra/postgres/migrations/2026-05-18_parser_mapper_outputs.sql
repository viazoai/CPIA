-- Parser / Mapper 산출 영속화.
-- 의도: 각 에이전트 결과를 BI / 대시보드에서 SELECT 가능하도록 PG 강제 적재.
-- 기존: state["parsed"] / state["mapped"] 가 LangGraph state (=checkpoints jsonb) 에만
-- 있어 외부 SELECT 불가능했음. 본 cycle 에서 정규화 + JSONB 하이브리드로 풀어 박음.

BEGIN;

-- 1. Parser 메타 + 시트1~3 (1 run = 1 row, idempotent on run_id).
CREATE TABLE IF NOT EXISTS parser_reports (
    id                    bigserial PRIMARY KEY,
    run_id                uuid        NOT NULL,
    report_date           date        NOT NULL,
    project               text        NOT NULL,
    bp_summaries          jsonb       NOT NULL,
    job_allocations       jsonb       NOT NULL,
    equipment_allocations jsonb       NOT NULL,
    activity_count        int         NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_reports_run_uniq UNIQUE (run_id)
);
CREATE INDEX IF NOT EXISTS parser_reports_report_date_idx ON parser_reports (report_date);

-- 2. Parser 시트4 — Activity[] raw (Mapper 호출 전 / l6_main, wa 미채움).
CREATE TABLE IF NOT EXISTS parser_activities (
    id              bigserial PRIMARY KEY,
    run_id          uuid        NOT NULL,
    report_date     date        NOT NULL,
    idx             int         NOT NULL,
    l5_disc         text,
    trade           text,
    company         text        NOT NULL,
    unit            text,
    today_qty       double precision,
    work_content    text,
    plan_total_qty  double precision,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_activities_run_idx_uniq UNIQUE (run_id, idx)
);
CREATE INDEX IF NOT EXISTS parser_activities_run_idx     ON parser_activities (run_id);
CREATE INDEX IF NOT EXISTS parser_activities_company_idx ON parser_activities (company);

-- 3. Mapper 결과 — Activity[] enriched (wa/l6_main/conf/source).
--    parser_activities.idx 와 1:1 매칭 (동일 run_id + idx).
CREATE TABLE IF NOT EXISTS mapper_activities (
    id                bigserial PRIMARY KEY,
    run_id            uuid        NOT NULL,
    report_date       date        NOT NULL,
    idx               int         NOT NULL,
    company           text        NOT NULL,
    trade             text,
    unit              text,
    today_qty         double precision,
    wa                text,
    l6_main           text,
    mapping_conf      double precision,
    mapping_source    text,
    requires_review   boolean     NOT NULL DEFAULT false,
    assigned_workers  double precision,
    worker_source     text,
    plan_total_qty    double precision,
    plan_mh           double precision,
    conditions        jsonb       NOT NULL DEFAULT '[]'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT mapper_activities_run_idx_uniq UNIQUE (run_id, idx)
);
CREATE INDEX IF NOT EXISTS mapper_activities_run_idx     ON mapper_activities (run_id);
CREATE INDEX IF NOT EXISTS mapper_activities_wa_l6_idx   ON mapper_activities (wa, l6_main);
CREATE INDEX IF NOT EXISTS mapper_activities_company_idx ON mapper_activities (company);

COMMIT;
