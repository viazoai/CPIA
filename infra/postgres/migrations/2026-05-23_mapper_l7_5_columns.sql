-- spec §8 / §9 — mapper_activities 에 l5_disc / l7_sub / l7_5_activity / sub_work_area 컬럼 추가
-- (activity_master 의 l5_disc / l7_sub / l7_5_activity / sub_work_area 를 row 별로 propagate)

ALTER TABLE mapper_activities
    ADD COLUMN IF NOT EXISTS l5_disc TEXT,
    ADD COLUMN IF NOT EXISTS l7_sub TEXT,
    ADD COLUMN IF NOT EXISTS l7_5_activity TEXT,
    ADD COLUMN IF NOT EXISTS sub_work_area TEXT;
