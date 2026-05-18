-- Parser 풀 스키마 — 통합 작업일보 4시트 + 업체별 시트6/Cover 풀 커버리지.
-- 의도: state.py 의 TimeShiftCounts + 4 entity 확장 + WorkerOutput + ReportMeta
-- 대응 PG 적재. BI / 대시보드 SELECT 용이성 우선.
--
-- 시간대 6 필드 (조출/주간/연장/야간/철야/Total) 는 jsonb 1 컬럼/그룹 (사용자 결정).
-- 그 외 메타 / 식별자는 정규화 컬럼.

BEGIN;

-- 1. parser_activities 컬럼 확장 — 시트4 풀 커버리지
ALTER TABLE parser_activities
    ADD COLUMN IF NOT EXISTS zone                TEXT,
    ADD COLUMN IF NOT EXISTS bp_code             TEXT,
    ADD COLUMN IF NOT EXISTS scope               TEXT,
    ADD COLUMN IF NOT EXISTS yesterday_cum_qty   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS today_cum_qty       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS progress_percent    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS remaining_qty       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS remaining_percent   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS note                TEXT,
    ADD COLUMN IF NOT EXISTS work_location_code  TEXT,
    ADD COLUMN IF NOT EXISTS wbs_mid_name        TEXT,
    ADD COLUMN IF NOT EXISTS wbs_sub_name        TEXT,
    ADD COLUMN IF NOT EXISTS wbs_detail_name     TEXT;

CREATE INDEX IF NOT EXISTS parser_activities_zone_idx     ON parser_activities (zone);
CREATE INDEX IF NOT EXISTS parser_activities_bp_code_idx  ON parser_activities (bp_code);

-- 2. mapper_activities 컬럼 확장 — mapper 가 parser 결과 보존 + Mapper enrich 합본
ALTER TABLE mapper_activities
    ADD COLUMN IF NOT EXISTS zone                TEXT,
    ADD COLUMN IF NOT EXISTS bp_code             TEXT,
    ADD COLUMN IF NOT EXISTS scope               TEXT,
    ADD COLUMN IF NOT EXISTS yesterday_cum_qty   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS today_cum_qty       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS progress_percent    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS remaining_qty       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS remaining_percent   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS note                TEXT,
    ADD COLUMN IF NOT EXISTS work_location_code  TEXT,
    ADD COLUMN IF NOT EXISTS wbs_mid_name        TEXT,
    ADD COLUMN IF NOT EXISTS wbs_sub_name        TEXT,
    ADD COLUMN IF NOT EXISTS wbs_detail_name     TEXT;

CREATE INDEX IF NOT EXISTS mapper_activities_zone_idx    ON mapper_activities (zone);
CREATE INDEX IF NOT EXISTS mapper_activities_bp_code_idx ON mapper_activities (bp_code);

-- 3. parser_job_allocations — 시트2 정규화 (BP사 × 직종 × 시간대)
CREATE TABLE IF NOT EXISTS parser_job_allocations (
    id                     bigserial PRIMARY KEY,
    run_id                 uuid        NOT NULL,
    report_date            date        NOT NULL,
    idx                    int         NOT NULL,
    bp_code                text,
    company                text        NOT NULL,
    disc_abbrev            text,
    manager_code           text,           -- Mm## (관리자/근로자 코드)
    worker_code            text,           -- sk## (기능공 코드)
    job_type               text        NOT NULL,
    workers_yesterday_cum  jsonb,          -- TimeShiftCounts (전일누계)
    workers_today_incr     jsonb,          -- TimeShiftCounts (금일투입)
    workers_today_cum      jsonb,          -- TimeShiftCounts (금일누계)
    final_flag             text,           -- O/X
    workers_cum_t          int         NOT NULL DEFAULT 0,  -- 편의 Total
    created_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_job_allocations_run_idx_uniq UNIQUE (run_id, idx)
);
CREATE INDEX IF NOT EXISTS parser_job_allocations_run_idx     ON parser_job_allocations (run_id);
CREATE INDEX IF NOT EXISTS parser_job_allocations_company_idx ON parser_job_allocations (company);
CREATE INDEX IF NOT EXISTS parser_job_allocations_job_idx     ON parser_job_allocations (job_type);

-- 4. parser_equipment_allocations — 시트3 정규화 (BP사 × 장비 × 시간대)
CREATE TABLE IF NOT EXISTS parser_equipment_allocations (
    id                    bigserial PRIMARY KEY,
    run_id                uuid        NOT NULL,
    report_date           date        NOT NULL,
    idx                   int         NOT NULL,
    bp_code               text,
    company               text        NOT NULL,
    disc_abbrev           text,
    equipment_big         text        NOT NULL,
    equipment_mid         text        NOT NULL,
    equipment_spec        text,
    count_yesterday_cum   jsonb,          -- TimeShiftCounts (전일투입누계)
    count_today_incr      jsonb,          -- TimeShiftCounts (금일투입)
    count_today_cum       jsonb,          -- TimeShiftCounts (금일투입누계)
    final_flag            text,
    count_cum_t           int         NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_equipment_allocations_run_idx_uniq UNIQUE (run_id, idx)
);
CREATE INDEX IF NOT EXISTS parser_equipment_allocations_run_idx      ON parser_equipment_allocations (run_id);
CREATE INDEX IF NOT EXISTS parser_equipment_allocations_company_idx  ON parser_equipment_allocations (company);
CREATE INDEX IF NOT EXISTS parser_equipment_allocations_big_mid_idx  ON parser_equipment_allocations (equipment_big, equipment_mid);

-- 5. parser_worker_outputs — 시트6 (업체별만), 개별 작업자 단위
CREATE TABLE IF NOT EXISTS parser_worker_outputs (
    id                  bigserial PRIMARY KEY,
    run_id              uuid        NOT NULL,
    report_date         date        NOT NULL,
    idx                 int         NOT NULL,
    bp_name             text,           -- 업체명 (1 run × N 업체)
    worker_name         text        NOT NULL,
    job_type            text,
    wbs_mid_name        text,
    wbs_sub_name        text,
    wbs_detail_name     text,
    work_location_code  text,
    work_content        text,
    shift_morning       int         NOT NULL DEFAULT 0,
    shift_daytime       int         NOT NULL DEFAULT 0,
    shift_overtime      int         NOT NULL DEFAULT 0,
    shift_night         int         NOT NULL DEFAULT 0,
    shift_all_night     int         NOT NULL DEFAULT 0,
    note                text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_worker_outputs_run_idx_uniq UNIQUE (run_id, idx)
);
CREATE INDEX IF NOT EXISTS parser_worker_outputs_run_idx     ON parser_worker_outputs (run_id);
CREATE INDEX IF NOT EXISTS parser_worker_outputs_bp_idx      ON parser_worker_outputs (bp_name);
CREATE INDEX IF NOT EXISTS parser_worker_outputs_worker_idx  ON parser_worker_outputs (worker_name);

-- 6. parser_report_meta — Cover (업체별만), 1 run × N 업체
CREATE TABLE IF NOT EXISTS parser_report_meta (
    id              bigserial PRIMARY KEY,
    run_id          uuid        NOT NULL,
    report_date     date        NOT NULL,
    bp_name         text        NOT NULL,
    project_name    text,
    project_code    text,
    site_id         text,
    writer          text,
    reviewer        text,
    approval        text,
    document_no     text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT parser_report_meta_run_bp_uniq UNIQUE (run_id, bp_name)
);
CREATE INDEX IF NOT EXISTS parser_report_meta_run_idx ON parser_report_meta (run_id);

COMMIT;
