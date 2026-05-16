-- 2026-05-16 — activity_master 테이블 추가
--
-- 근거: A_Track Phase 0 합의 (docs/schema/postgres.md §2)
--   Mapper 가 Chroma `wbs_master` 검색 후 메타데이터 (plan_total_qty, plan_mh,
--   plan_start/finish) 가 필요한데 Chroma metadata 만으로는 SQL JOIN·날짜 필터링·
--   인덱스 활용이 부족. PG 에 정규화 적재해 SQL JOIN 가능하게 함.
--
-- 적재: scripts/load_master_list.py — Master List xlsx 에서 1회 적재 (PoC 범위 189 row).
--
-- 적용 절차:
--   docker exec -i cpia-postgres psql -U cpia -d cpia < postgres/migrations/20260516_add_activity_master.sql

CREATE TABLE IF NOT EXISTS activity_master (
    wbs_activity_id   TEXT PRIMARY KEY,        -- 'TNMCB1F6501A03030034'

    -- 계층 라벨 (Master List col 14~22)
    l5_disc           TEXT NOT NULL,           -- '건축' / '설비' / ...
    l6_main           TEXT,                    -- '철근콘크리트공사'
    l6_code           TEXT,                    -- '03'
    l7_sub            TEXT,                    -- '거푸집공사'
    l7_code           TEXT,                    -- '030'
    l7_5_activity     TEXT,                    -- '기초공사 : 거푸집 공사'
    sub_work_area     TEXT,                    -- 'B1F 연결공동구 FAB-WWT'

    -- 업체·단위
    company           TEXT,                    -- '남웅건설'
    unit              TEXT,                    -- 'M2' / 'Ton' / 'M3'

    -- Plan 값 (Rev.2 채택 + 이력)
    plan_total_qty    NUMERIC,                 -- 500.0
    plan_mh_rev2      NUMERIC,                 -- 456.0  (분배 + 진단 사용)
    plan_mh_rev1      NUMERIC,
    plan_mh_rev0      NUMERIC,
    plan_wv           NUMERIC,                 -- = plan_mh_rev2 * 4.9 (참고용)

    -- 일정 (Rev.2)
    plan_start        DATE,
    plan_finish       DATE,

    -- 실적 (Master List 자체 컬럼, 작업일보와는 별개)
    actual_start      DATE,
    actual_finish     DATE,

    -- 적재 메타
    source_file       TEXT,                    -- 'WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx'
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actmaster_lookup
    ON activity_master (l5_disc, company, unit);

CREATE INDEX IF NOT EXISTS idx_actmaster_period
    ON activity_master (plan_start, plan_finish);
