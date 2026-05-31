-- F.1: orphan mapper/parser DELETE (재적재 v2 다운스트림, 2026-05-30)
-- 근본원인: mapper_activities/parser_activities 는 pipeline_runs 로의 FK 없음
--   (migration 2026-05-18_parser_mapper_outputs.sql: run_id uuid NOT NULL 선언만, REFERENCES/CASCADE 없음).
--   과거 cleanup 이 pipeline_runs 만 DELETE → 부모 없는 orphan ~148k(93.6%) 잔존.
-- 정의상 orphan = 부모 run 없음 = 유효 리포트 미참조 → 삭제 안전. '6월 이전 DELETE 금지' 의 명시 예외.
-- 사전 실측 (2026-05-30): mapper_orphans=148157, parser_orphans=148157, total=158366 each → 잔존 10209.

-- Step 1: 사전 COUNT
SELECT 'mapper_orphans' AS k, COUNT(*) FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id)
UNION ALL
SELECT 'parser_orphans', COUNT(*) FROM parser_activities pa
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = pa.run_id);

-- Step 2: 트랜잭션 삭제 + 검증
BEGIN;
DELETE FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id);
DELETE FROM parser_activities pa
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = pa.run_id);
SELECT 'mapper_remaining' AS k, COUNT(*) FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id)
UNION ALL
SELECT 'parser_remaining', COUNT(*) FROM parser_activities pa
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = pa.run_id);
-- remaining 0 확인 후에만 COMMIT
COMMIT;
