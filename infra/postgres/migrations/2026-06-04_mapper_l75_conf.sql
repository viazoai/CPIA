-- infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql
-- l7.5 선정 신뢰도(0~1). mapping_conf(l6 conf)와 별개.
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l75_conf double precision;
-- HIL 대안: l6 밑 l7.5 후보 top-K [{label, score}]
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l7_5_alternatives jsonb;
