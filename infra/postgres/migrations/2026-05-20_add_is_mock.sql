-- 2026-05-20: mock 데이터 백업 + 시연 fallback 용 is_mock 컬럼 추가
-- sites.is_mock 은 이미 존재 (제외)
-- 참조: spec 2026-05-20-cpia-frontend-data-binding-design.md §4
-- partial unique index 영향 X — index column set 에 is_mock 미포함

ALTER TABLE pipeline_runs       ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_reports      ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_activities   ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE mapper_activities   ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE forecasts           ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE optimizer_advice    ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE daily_reports       ADD COLUMN IF NOT EXISTS is_mock BOOL NOT NULL DEFAULT FALSE;
