-- forecasts.point_in_time_delay_days — 시점 누계 부족분의 일수 환산
--
-- 배경:
--   docs/superpowers/specs/2026-05-27-cpia-report-redesign-design.md §4.2.3 신규 차원.
--   기존 Forecaster 의 forward delay 는 "오늘 생산성이 유지되면 완료가 며칠 밀리나" 를
--   미래 지점 기준으로 계산. 본 컬럼은 "그 날짜 시점에 누계 실 vs 누계 계획 부족분이
--   며칠치 plan 분량인가" 를 과거 누적 기준으로 계산해 보조 차원으로 제공.
--   nullable + default 없음 → Postgres metadata-only ALTER, lock < 1s.
--
-- 산식 (§4.2.3):
--   round(deficit_qty / plan_per_day_qty)
--     deficit_qty       = 누계 계획 - 누계 실 (음수면 초과 달성 → 0 clamp)
--     plan_per_day_qty  = 해당 공정 일평균 계획 물량
--
-- 채우는 곳 (writer):
--   - pipeline/agents/forecaster/aggregate.py::_compute_point_in_time_deficit_days (Task 6)
--   - pipeline/db.py::insert_forecast (Task 7, $29 placeholder 로 컬럼 추가)
--
-- 읽는 곳 (reader):
--   - pipeline/agents/optimizer/prompt.py::DIAG v10 (Task 9) — risk_level=이상 시
--     forward delay 와 함께 보조 인용 차원으로 LLM 컨텍스트에 주입.

BEGIN;

ALTER TABLE forecasts
    ADD COLUMN IF NOT EXISTS point_in_time_delay_days INTEGER;

COMMENT ON COLUMN forecasts.point_in_time_delay_days IS
    '시점 누계 부족분의 일수 환산. 산식: round(deficit_qty / plan_per_day_qty) — deficit_qty=누계 계획-누계 실 (음수 시 0 clamp), plan_per_day_qty=일평균 계획. Forecaster forward delay (미래 지점 추정) 와는 별개 차원으로, 그 날짜 시점의 누계 부족분을 일수로 환산. Writer: pipeline/agents/forecaster/aggregate.py::_compute_point_in_time_deficit_days + pipeline/db.py::insert_forecast. Reader: Optimizer DIAG prompt v10 — risk_level=이상 시 보조 인용 차원. Spec: 2026-05-27-cpia-report-redesign-design.md §4.2.3.';

COMMIT;
