-- 공기단축 예측 시나리오 jsonb — site 전체 + WP 별 4 시나리오
BEGIN;

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS scenarios_jsonb JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN daily_reports.scenarios_jsonb IS
  'optimizer view_builder._build_scenarios() 산출. shape: {site: {no_action, optimistic_p25, base_p50, pessimistic_p75}, by_wp: {[wp_id]: 동일 4 키}}. 각 키 = {expected_completion: date, recovery_days: int, delta_days: int, case_count: int}.';

COMMIT;
