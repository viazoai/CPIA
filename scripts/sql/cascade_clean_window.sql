-- 전 윈도우 cleaning — pipeline_runs / mapper_activities 보존
-- forecasts / optimizer_advice / daily_reports 만 cascade DELETE
-- 사용법:
--   psql ... -v site_id="'m15x-ph3-ibl'" -v start_date="'2024-04-11'" -v end_date="'2025-09-24'" -f cascade_clean_window.sql

BEGIN;

WITH target AS (
  SELECT run_id FROM pipeline_runs
  WHERE site_id = :site_id
    AND report_date BETWEEN :start_date AND :end_date
)
DELETE FROM daily_reports WHERE run_id IN (SELECT run_id FROM target);

WITH target AS (
  SELECT run_id FROM pipeline_runs
  WHERE site_id = :site_id
    AND report_date BETWEEN :start_date AND :end_date
)
DELETE FROM optimizer_advice WHERE run_id IN (SELECT run_id FROM target);

WITH target AS (
  SELECT run_id FROM pipeline_runs
  WHERE site_id = :site_id
    AND report_date BETWEEN :start_date AND :end_date
)
DELETE FROM forecasts WHERE run_id IN (SELECT run_id FROM target);

-- pipeline_runs / mapper_activities 보존

SELECT
  'pipeline_runs_kept' AS k,
  COUNT(*) AS n
FROM pipeline_runs
WHERE site_id = :site_id AND report_date BETWEEN :start_date AND :end_date
UNION ALL
SELECT 'mapper_kept', COUNT(*)
FROM mapper_activities ma
JOIN pipeline_runs pr USING (run_id)
WHERE pr.site_id = :site_id AND pr.report_date BETWEEN :start_date AND :end_date;

COMMIT;
