-- 2026-05-17 — activity_master.wa 컬럼 alignment
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §4 (activity_master A_LOCAL=22 PROD=21 격차)
--
-- 근거: init.sql:164 의 activity_master 정의에는 `wa TEXT` 가 있지만,
--      20260516_add_activity_master.sql migration 에는 누락. PR 어디선가 init.sql
--      만 갱신하고 별 migration 추가 안 됨. dev 는 docker init 재실행시 wa 가
--      자동 적용되지만 prod 는 옛 init.sql (wa 없음) 로 부팅된 상태.
--      load_master_list.py 가 wa 컬럼에 값 INSERT 하므로 prod alignment 필수.
--
-- 멱등 (IF NOT EXISTS) — dev 적용시 no-op, prod 만 추가.

BEGIN;
ALTER TABLE activity_master
  ADD COLUMN IF NOT EXISTS wa TEXT;
COMMIT;
