-- infra/postgres/migrations/2026-05-16_downstream_agents.sql
-- Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §8

-- §8.1: pipeline_runs.atomized_count
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS atomized_count INTEGER DEFAULT 0;

-- §8.2: forecasts 재정의 (PoC 단계 빈 테이블 — DROP + CREATE)
DROP TABLE IF EXISTS forecasts;

CREATE TABLE forecasts (
    id                       BIGSERIAL PRIMARY KEY,
    run_id                   UUID NOT NULL REFERENCES pipeline_runs(run_id),
    company                  TEXT NOT NULL,
    l6_main                  TEXT NOT NULL,

    today_qty_by_unit        JSONB,
    today_assigned_workers   NUMERIC,

    plan_total_qty_by_unit   JSONB,
    plan_mh_sum              NUMERIC,

    rag_n_similar            INT,
    similar_cases            JSONB,

    assessment               TEXT,
    reasoning                TEXT,
    expected_completion      DATE,
    delay_days               INT,
    risk_level               TEXT,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';

-- §8.3: optimizer_advice 컬럼 rename
ALTER TABLE optimizer_advice RENAME COLUMN trade TO l6_main;

-- Fix: forecasts.run_id ON DELETE CASCADE 복구 (BASE 에 있었으나 DROP+CREATE 시 누락)
ALTER TABLE forecasts DROP CONSTRAINT forecasts_run_id_fkey;
ALTER TABLE forecasts ADD CONSTRAINT forecasts_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id) ON DELETE CASCADE;
