-- 2026-05-17 — activity_master 에 site_id 컬럼 추가 (현장별 WBS 분리)
--
-- 근거: 사용자 명시 — "현장명도 잘 넣어야돼 현장별로 wbs가 다르니까 마스터리스트가 다를거야"
--   현재 activity_master 는 m15x-ph3-ibl 1 site 의 WBS 만 적재되어 있으나
--   향후 다른 site WBS 추가 시 같은 (wbs_activity_id) 가 충돌. site_id 로 격리.
--
-- 절차 (apply 시):
--   1. ALTER ADD COLUMN site_id TEXT NOT NULL DEFAULT 'm15x-ph3-ibl'
--      → 기존 row 1059 (또는 적재량) 자동 backfill
--   2. ALTER COLUMN site_id DROP DEFAULT
--      → 신규 row 는 loader 가 명시 site_id 박아야 함 (--site-id 인자)
--   3. PRIMARY KEY 재구성 (wbs_activity_id 단독 → (site_id, wbs_activity_id) 복합)
--      → 같은 wbs_activity_id 가 다른 site 에 존재 가능
--   4. CREATE INDEX
--      - (site_id, company) — Mapper fetch_bp_candidates (Task 2)
--      - (site_id, l5_disc, l6_main) — WBSTree (api_helpers/wbs_tree.py)
--      - (site_id, plan_start, plan_finish) — Forecaster/Optimizer 기간 필터
--
-- 적용 명령 (dev + prod 양쪽):
--   /usr/bin/psql 'postgresql://cpia:cpia@127.0.0.1:5432/cpia' \
--     -f infra/postgres/migrations/2026-05-17_activity_master_site_id.sql
--   /usr/bin/psql 'postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia' \
--     -f infra/postgres/migrations/2026-05-17_activity_master_site_id.sql

BEGIN;

-- (1) 컬럼 추가 + 기존 row backfill
ALTER TABLE activity_master
    ADD COLUMN IF NOT EXISTS site_id TEXT NOT NULL DEFAULT 'm15x-ph3-ibl';

-- (2) 신규 row 는 명시 site_id 박아야 함
ALTER TABLE activity_master
    ALTER COLUMN site_id DROP DEFAULT;

-- (3) PRIMARY KEY 재구성 — 같은 wbs_activity_id 가 다른 site 에 존재 가능
ALTER TABLE activity_master
    DROP CONSTRAINT IF EXISTS activity_master_pkey;
ALTER TABLE activity_master
    ADD PRIMARY KEY (site_id, wbs_activity_id);

-- (4) 인덱스
CREATE INDEX IF NOT EXISTS idx_actmaster_site_company
    ON activity_master (site_id, company);

CREATE INDEX IF NOT EXISTS idx_actmaster_site_l6
    ON activity_master (site_id, l5_disc, l6_main);

CREATE INDEX IF NOT EXISTS idx_actmaster_site_period
    ON activity_master (site_id, plan_start, plan_finish);

COMMIT;

-- 적용 검증 (수동 실행)
-- SELECT site_id, COUNT(*) FROM activity_master GROUP BY site_id ORDER BY site_id;
-- \d+ activity_master
