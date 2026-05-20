# Design Intent — optimizer

- **Generated**: 2026-05-20 (view_builder 752 LOC 신규 + `_build_scenarios` percentile 4 시나리오 cycle)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**:
  - `pipeline/agents/optimizer/agent.py` (199 LOC)
  - `pipeline/agents/optimizer/prompt.py` (315 LOC)
  - `pipeline/agents/optimizer/retrieve.py` (161 LOC)
  - `pipeline/agents/optimizer/synthetic_daily_report.py` (498 LOC)
  - `pipeline/agents/optimizer/synthetic_v2.py` (363 LOC)
  - **`pipeline/agents/optimizer/view_builder.py` (752 LOC, NEW)**
  - `pipeline/agents/reporter.py` (161 LOC, optimizer 와 연계)
  - 합계 **~2,449 LOC** (이전 1,485 → +964, view_builder 신설 영향)
- **스펙**:
  - `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` (21 결정)
  - `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md` §5.3 (reporter)
  - `docs/superpowers/specs/2026-05-19-cpia-reports-gap-and-parser-design.md` §3-5 (view_builder + scenarios)

Forecaster 가 진단한 risky 공종 중 HIL 2 에서 선택된 그룹에 대해 Chroma 과거 유사 패턴 retrieve → LLM 으로 맥락 기반 조언 + **daily_reports 의 8 + 1 view jsonb 산출 (view_builder.py 752 LOC 신규)**. `_build_scenarios` (2026-05-19) — recovery_distribution → percentile 기반 4 시나리오 (no_action / optimistic_p25 / base_p50 / pessimistic_p75). 결정 #20 (recovery_distribution 코드단 deterministic, LLM override) + 결정 #8 (retrieve 책임은 hil_2_node 에).

---

## T1 — Function Index

### agent.py (199 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `optimize` | agent.py:~50 | `async (forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id, mapped) -> list[dict]` | 선택 그룹별 LLM 호출 + optimizer_advice INSERT + 8+1 view jsonb 산출 + daily_reports UPSERT | ✅ |
| `_compute_recovery_distribution` | agent.py:99 | `(cases: list[dict]) -> dict[str, int]` | 결정 #20: Counter([c["recovery"]["recovery_days"] for c in cases]) — LLM 출력 override | ✅ |
| `_compose_cold_start_row` | agent.py:~130 | `(r, cases, run_id) -> dict` | 케이스 < 3 시 cold_start 신호 보존 row | ✅ |
| `_compose_row` | agent.py:~150 | `(r, cases, llm_output, run_id) -> dict` | LLM 출력 + cases merge → optimizer_advice row | ✅ |
| `_call_azure_llm` | agent.py:~175 | `(llm_input, cfg, azure) -> dict` | Azure gpt-5.1 호출 (fail-fast, 결정 #10) | ✅ |

### prompt.py (315 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `build_llm_user_input` | prompt.py:~50 | `(forecast_row, degradation_cases) -> dict` | forecast row + recovery trajectory → LLM user message JSON | ✅ |
| `SYSTEM_PROMPT` | prompt.py | constant | 한글+영어, 선택지 제시 톤 (명령형 회피) | — |
| `FEW_SHOT_MESSAGES` | prompt.py | constant | 3개 회복 패턴 샘플 (user/assistant 6 메시지) | — |

### retrieve.py (161 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `fetch_degradation_cases` | retrieve.py:~30 | `(metadatas, documents, company, l6_main, today, baseline_unit, baseline_value, n=5) -> list[dict]` | Step 1: 저하 case top-N recency (incident ∋ 장비대기/자재미입고/돌관 ∧ prod < baseline×0.85) | ✅ |
| `fetch_recovery_trajectory` | retrieve.py:~80 | `(metadatas, company, l6_main, case_date, today, baseline_unit, baseline_value, window=7) -> dict` | Step 2: case_date+1~+7 회복 trajectory (recovery_days = first✓ or None) | ✅ |
| `_group_baseline` | retrieve.py:~120 | `(metadatas, company, l6_main, baseline_unit) -> Optional[float]` | 정상 row 들의 productivity 평균 (None → cold_start) | ✅ |
| `_group_day_productivity` | retrieve.py:~145 | `(metas_of_day, baseline_unit) -> float` | 당일 그룹 생산성 = Σtoday_qty[unit] / assigned_workers | — |

### view_builder.py (752 LOC, NEW)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_build_productivity_views` | view_builder.py | `async (pg, run_id, site_id, today) -> dict` | site/by_contractor/by_l6/by_wp EVM snapshot (today dict) | ✅ |
| `_evm_for_group` | view_builder.py | `async (pg, run_id, site_id, today) -> dict` | site 전체 EVM (progress = cum_actual / plan_qty_full) | ✅ |
| `_evm_by_group` | view_builder.py | `async (pg, run_id, site_id, today, group_key) -> dict` | group_key (company/l6_main/wa_l6_company) 별 EVM (FULL OUTER JOIN) | ✅ |
| `_evm_by_wa_l6_company` | view_builder.py | `async (pg, run_id, site_id, today) -> dict` | wa anchor 유지 EVM (mapper anchor) | ✅ |
| `_compose_evm` | view_builder.py | `(plan_row, actual_row) -> dict` | plan_row + actual_row → EV/PV/AC/SPI/CPI | ✅ |
| `_build_kpi` | view_builder.py | `async (...) -> dict` | 헤더 KPI (productivity_today, spi, cpi, target, delay_days, expected_completion) | ✅ |
| `_build_contractor_bars` | view_builder.py | `(by_contractor: dict) -> list[BarItem]` | CPI desc sorted BarItem list | ✅ |
| `_build_trade_bars` | view_builder.py | `(by_l6: dict) -> list[BarItem]` | by_l6 → BarItem list | ✅ |
| `_build_quadrant` | view_builder.py | `async (pg, run_id, site_id, today) -> dict` | (wa, l6, company) per WP 산점도 (productivity vs impact P90) | ✅ |
| `_compute_impact_p90` | view_builder.py | `(raw_impacts: list) -> float` | raw_impacts P90 percentile (fallback: max) | ✅ |
| `_normalize_impact` | view_builder.py | `(raw, p90) -> float` | raw → 0~100 (P90 ceiling) | — |
| `_quadrant_label` | view_builder.py | `(productivity, impact) -> str` | "risk"/"caution"/"watch"/"safe" 분류 | ✅ |
| `_wp_id_of` | view_builder.py | `(wa, l6_main, company) -> str` | kebab-case wp_id 생성 (cub-철근콘크리트공사-남웅건설) | — |
| `_build_wp_summary` | view_builder.py | `async (...) -> dict` | quadrant 기반 WP 표 (status + baseline + progress + dates) | ✅ |
| `_build_optimizer_view` | view_builder.py | `(advice_rows, forecast) -> dict` | {by_wp: {wp_id: {diagnosis, similar_cases, recommendations, details}}, default_wp_id} | ✅ |
| **`_build_scenarios`** | view_builder.py | `(advice_rows, forecast) -> dict` | **site + by_wp 4 시나리오 (no_action / optimistic_p25 / base_p50 / pessimistic_p75)** | ✅ |
| `_expand_recovery_to_days` | view_builder.py | `(recovery_distribution: dict) -> list[int]` | recovery_distribution → percentile 산출 가능 list (not_recovered cap +30) | ✅ |
| `_percentile` | view_builder.py | `(days: list, q: float) -> float` | days list + q ∈ [0,1] → quantiles percentile | — |
| `_coerce_date` | view_builder.py | `(v) -> date \| None` | expected_completion date/str/None 안전 coerce (2026-05-19 fix) | ✅ |
| `_match_forecast_by_company_l6` | view_builder.py | `(forecast, company, l6_main) -> dict \| None` | (company, l6_main) lookup helper | — |
| `_scenario` | view_builder.py | `(name, base_completion, recovery_days) -> dict` | 단일 시나리오 dict (recovery ≤ 0 → no_action pass) | ✅ |
| `_build_s_curve` | view_builder.py | `async (...) -> list[dict]` | planned/actual/forecast/recovery 4 곡선 unified datapoint | ✅ |
| `_merge_curves` | view_builder.py | `(planned, actual, forecast, recovery) -> list[dict]` | date 단위 datapoint 합성 | ✅ |
| `_extend_forecast` | view_builder.py | `(actual_history: list, remaining_days: int) -> list[dict]` | 현 추세 linear 연장 (rate × remaining_days) | ✅ |

### synthetic_v2.py (363 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `generate_synthetic_v2_group` | synthetic_v2.py | `(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days, seed, reference_date) -> list[dict]` | state machine 90일 시계열 row 생성 (회복 룰 7건) | ✅ |
| `_BP_TOTAL` | synthetic_v2.py | constant dict | 27 (company, l6_main) 그룹별 BP사 총 인원 (spec §3.4) | — |

### synthetic_daily_report.py (498 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `generate_fake_daily_report` | synthetic_daily_report.py | `(report_date, scenarios, activity_pools, baseline_workers, baseline_qty, seed) -> list[Activity]` | Activity list 직접 생성 (Parser/Mapper skip, spec §10.2) | ✅ |
| `_check_synthetic_v2_loaded` | synthetic_daily_report.py | `async (cfg) -> bool` | synthetic v2 적재 확인 (CLI step 1) | — |
| `_ensure_site` | synthetic_daily_report.py | `async (pg, site_id, name) -> None` | sites ON CONFLICT DO NOTHING INSERT | — |
| `_load_baseline_inputs` | synthetic_daily_report.py | `async (pg, scenarios, days) -> tuple` | activity_pool + baseline_workers + baseline_qty | — |
| `_initial_state` | synthetic_daily_report.py | `(run_id, report_date, mapped) -> dict` | build_demo_graph 진입 state | — |
| `build_demo_graph_config` | synthetic_daily_report.py | `() -> GraphConfig` | demo graph 용 config | — |

---

## T2 — Issue Cards

### `optimize` — Orchestration Core (view_builder 통합)

- **위치**: `pipeline/agents/optimizer/agent.py:~50` (~150 LOC)
- **시그니처**: `async def optimize(forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id, mapped) -> list[dict]`
- **이슈**:
  - git log: `7fa3dd9 feat(optimizer): build view jsonb + daily_reports UPSERT (partial write 가드) + state.site_id`
  - git log: `3781e5b optimizer: add _build_scenarios + scenarios_jsonb upsert`
  - 결정 #8 (retrieve 책임 hil_2_node 에) + #10 (LLM fail-fast) + #11 (cold_start < 3 cases)
- **설계 의도**:
  - `pre_optimizer_cases` (hil_2_node 사전 영속) 재활용 — retrieve 재호출 X (결정 #8)
  - cases < 3 → LLM skip + cold_start row 생성 (결정 #11)
  - cases ≥ 3 → Azure LLM → recommendations + diagnosis
  - **NEW (2026-05-18)**: view_builder 8+1 jsonb 산출 + daily_reports UPSERT (partial write 가드)
- **대응 패턴**:
  - 입력: forecast (list[dict]), hil_2_selection (list[key]), pre_optimizer_cases (dict[key, cases]), run_id, today, cfg, site_id, mapped
  - 처리:
    - Selection iteration: 각 key 마다 cases → cold_start or LLM → row
    - `insert_optimizer_advice` (PG)
    - view_builder 9 호출:
      - `_build_productivity_views` → productivity_jsonb
      - `_build_quadrant` → quadrant_jsonb
      - `_build_kpi` → kpi_jsonb
      - `_build_contractor_bars` → contractor_bars_jsonb
      - `_build_trade_bars` → trade_bars_jsonb
      - `_build_wp_summary` → wp_summary_jsonb
      - `_build_s_curve` → s_curve_jsonb
      - `_build_optimizer_view` → optimizer_view_jsonb
      - `_build_scenarios` → scenarios_jsonb (2026-05-19)
    - `upsert_daily_report_view_col` 9회 (db.py:1034, partial write 가드)
  - 출력: list[dict] (optimizer_advice rows)
- **관련**:
  - 호출자: graph.py `optimizer_node` (graph.py:415)
  - 후속: reporter_node (graph.py:435) — 종합 보고서 + daily_reports.report_md INSERT
  - 테스트: `test_optimizer_scenarios.py` (10 case, scenarios 산출 + cold_start graceful)
- **Suspected related** (2026-05-19):
  - `_build_scenarios` (view_builder.py) — 본 함수의 가장 큰 신규 의존
  - db.py `upsert_daily_report_view_col` (db.py:1034) — 9 view jsonb 적재 진입점

---

### `_build_scenarios` — percentile 기반 공기단축 4 시나리오

- **위치**: `pipeline/agents/optimizer/view_builder.py:_build_scenarios` (NEW 2026-05-19)
- **시그니처**: `def _build_scenarios(advice_rows, forecast) -> dict`
- **이슈**:
  - git log: `3781e5b optimizer: add _build_scenarios + scenarios_jsonb upsert` (2026-05-19)
  - git log: `105ee6a fix: review feedback — recovery wiring + e2e negative + date coerce + import top` (2026-05-19)
  - migration: `infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql`
  - spec: `2026-05-19-cpia-reports-gap-and-parser-design.md` §5.1~5.4
- **설계 의도**:
  - **percentile-based 4 시나리오** (recovery_distribution → days list → percentile):
    - `no_action`: 회복 없음 (delta_days=0)
    - `optimistic_p25`: P25 quantile (빠른 회복)
    - `base_p50`: 중앙값
    - `pessimistic_p75`: P75 quantile (느린 회복)
  - `not_recovered` → +30 days cap (상한 설정)
  - PM 가 시나리오별 expected_completion 비교 → 의사결정
- **대응 패턴**:
  - 입력: advice_rows (optimizer 출력), forecast (forecaster 출력)
  - 처리:
    - `_expand_recovery_to_days` — distribution → list[int]
    - `_percentile` 3회 — P25 / P50 / P75
    - site 단위 (모든 advice 병합) + by_wp 단위 ((company, l6_main) grouping)
  - 출력: `{site: {no_action, p25, p50, p75}, by_wp: {key: {...}}}`
- **관련**:
  - 호출자: `optimize` (agent.py:~50)
  - 영속: `daily_reports.scenarios_jsonb` (db.py:1034 `upsert_daily_report_view_col`)
  - BFF 소비: `web/lib/transforms.ts` 의 deriveSCurve / recovery sub
  - 테스트: `test_optimizer_scenarios.py` (10 case)
- **Suspected related** (2026-05-19):
  - `_compute_recovery_distribution` (agent.py:99) — 본 함수의 input 원천
  - `_coerce_date` (view_builder.py) — expected_completion date/str 안전 coerce
  - reporter 의 scenarios recovery override (105ee6a)

---

### `_build_productivity_views` — EVM 산식 4 view

- **위치**: `pipeline/agents/optimizer/view_builder.py:_build_productivity_views` (2026-05-17 신설)
- **시그니처**: `async def _build_productivity_views(pg, run_id, site_id, today) -> dict`
- **이슈**:
  - git log: `2788cfa feat(view_builder): _build_productivity_views + _compose_evm` (2026-05-17 초기)
  - git log: `87d5cbf fix(view_builder): EVM 산식 컨셉 변경 — 분모=마스터플랜 전체, 분자=mapper_activities 전체` (2026-05-19)
  - 2026-05-19 변경: mapped CTE 제거 — plan side 가 mapper_activities 매핑 결과에 종속 X
- **설계 의도**:
  - **EVM 산식** (spec §3):
    - progress = cum_actual_qty / plan_qty_full
    - EV = progress × plan_mh_full
    - PV = cum_plan_mh (누적 계획 MH)
    - AC = cum_actual_mh (누적 실제 MH)
    - SPI = EV / PV × 100
    - CPI = EV / AC × 100
  - 4 view: today (site 전체) / by_contractor / by_l6 / by_wp (wa_l6_company)
- **대응 패턴**:
  - 입력: pg, run_id, site_id, today
  - 처리: 4 group_key 별 `_evm_by_group` 또는 `_evm_for_group` 호출
  - 출력: `{today: {...}, by_contractor: {...}, by_l6: {...}, by_wp: {...}}`
- **관련**:
  - 호출자: `optimize` (agent.py:~50) — productivity_jsonb 산출
  - PG: `activity_master` (plan) + `mapper_activities` (actual)
  - 테스트: `test_view_builder_evm.py`
- **Suspected related** (2026-05-19):
  - `_evm_for_group`, `_evm_by_group` — EVM 산출 core
  - `_compose_evm` — plan + actual → EVM 산식 단일 진입점

---

### `_build_quadrant` — 4분면 분류 (impact P90 normalize)

- **위치**: `pipeline/agents/optimizer/view_builder.py:_build_quadrant` (2026-05-18 신설)
- **시그니처**: `async def _build_quadrant(pg, run_id, site_id, today) -> dict`
- **이슈**:
  - git log: `48e14cd feat(view_builder): _build_quadrant + impact P90` (2026-05-18)
- **설계 의도**:
  - WP 별 산점도 점 (productivity vs impact)
  - **impact 정규화**: raw_impact = sum(plan_total_qty × plan_mh) → P90 percentile 기준 ceiling (min(100, raw/p90×100))
  - **4분면 label**:
    - `risk`: low_prod (<80) AND high_impact (≥50)
    - `caution`: low_prod (<80) AND low_impact
    - `watch`: high_impact (≥50) AND high_prod
    - `safe`: low_impact AND high_prod
- **대응 패턴**:
  - 입력: pg, run_id, site_id, today
  - 처리:
    - SELECT (wa, l6_main, company) per WP
    - `_compute_impact_p90` — raw impacts P90
    - 각 WP 마다 (productivity, impact) → `_quadrant_label`
  - 출력: `[{wp_id, wa, l6_main, company, productivity, impact, label}, ...]`
- **관련**:
  - 호출자: `optimize` (agent.py:~50) — quadrant_jsonb 산출
  - BFF 소비: FE 4분면 산점도 (Layer 2 § 02 중앙)
- **Suspected related** (2026-05-18):
  - `_compute_impact_p90` (view_builder.py) — P90 산출
  - `_normalize_impact` — 0~100 ceiling
  - `_quadrant_label` — 분류 함수

---

### `_build_s_curve` — planned/actual/forecast/recovery 4 곡선

- **위치**: `pipeline/agents/optimizer/view_builder.py:_build_s_curve` (2026-05-18 신설)
- **시그니처**: `async def _build_s_curve(pg, run_id, site_id, today) -> list[dict]`
- **이슈**:
  - git log: `42bc99a feat(view_builder): _build_s_curve + _merge_curves` (2026-05-18)
- **설계 의도**:
  - planned/actual/forecast/recovery 4 곡선을 date 단위 unified datapoint 로 합성
  - forecast = 현 추세 linear 연장 (마지막 actual rate × remaining days)
  - recovery = scenarios 의 best case (optimistic_p25) reflective
- **대응 패턴**:
  - 입력: pg, run_id, site_id, today
  - 처리:
    - planned (activity_master.plan_start/finish + plan_total_qty)
    - actual (mapped_history 누적)
    - forecast (`_extend_forecast` linear)
    - recovery (scenarios.optimistic_p25 적용)
    - `_merge_curves` date 정합
  - 출력: `[{date, planned, actual, forecast, recovery}, ...]`
- **관련**:
  - 호출자: `optimize` (agent.py:~50) — s_curve_jsonb 산출
  - BFF 소비: `web/lib/transforms.ts` G20 deriveSCurve (4 sub)
- **Suspected related** (2026-05-18):
  - `_merge_curves` — date 정합
  - `_extend_forecast` — linear 연장

---

### `_build_optimizer_view` — by_wp 상세 4 섹션

- **위치**: `pipeline/agents/optimizer/view_builder.py:_build_optimizer_view` (2026-05-18 신설)
- **시그니처**: `def _build_optimizer_view(advice_rows, forecast) -> dict`
- **이슈**:
  - git log: `f25d945 feat(view_builder): _build_optimizer_view — 4 섹션` (2026-05-18)
- **설계 의도**:
  - by_wp 상세 패널 (Layer 2 § 02 왼쪽): 진단 / 유사사례 / 권고 / 상세 4 섹션
  - default_wp_id = 가장 큰 risk WP (FE 초기 선택)
- **대응 패턴**:
  - 입력: advice_rows, forecast
  - 처리: WP별 4 section 조립
  - 출력: `{by_wp: {wp_id: {diagnosis, similar_cases, recommendations, details}}, default_wp_id}`
- **관련**:
  - 호출자: `optimize` (agent.py:~50)
  - BFF 소비: `/api/runs/{run_id}/optimizer` (api.py:378)
- **Suspected related** (2026-05-18):
  - `_wp_id_of` — kebab-case wp_id 생성

---

### `_build_kpi` + `_build_contractor_bars` + `_build_trade_bars` + `_build_wp_summary`

- **위치**: `pipeline/agents/optimizer/view_builder.py` (b20549d, 2026-05-18)
- **시그니처**: 각각 `async def(...)`
- **이슈**:
  - git log: `b20549d feat(view_builder): _build_kpi + bars` (2026-05-18)
- **설계 의도**:
  - 헤더 KPI / Contractor (CPI desc) / Trade (l6) 바차트 / WP 표 (quadrant 기반)
- **대응 패턴**:
  - 입력: pg + state
  - 처리: 각각 도메인 별 aggregation
  - 출력: jsonb dict
- **관련**:
  - 호출자: `optimize` (agent.py:~50)
  - BFF 소비: FE Dashboard / Layer 2
  - **NOTE**: `_build_kpi` / `_build_wp_summary` / `_build_quadrant` 일부는 production cycle 5 에서 빈 dict {} 로 산출됨 (Phase 2 백로그 — activity_master.plan_start/finish 의존성 필요, issue #N4)
- **Suspected related** (2026-05-18):
  - `_quadrant_label` — wp_summary status 매핑
  - `_wp_id_of` — kebab-case wp_id

---

### `_compute_recovery_distribution` — 코드단 deterministic Counter

- **위치**: `pipeline/agents/optimizer/agent.py:99`
- **시그니처**: `def _compute_recovery_distribution(cases: list[dict]) -> dict[str, int]`
- **이슈**:
  - 결정 #20 (spec §2.6.4): LLM 출력 무시, 코드 값이 정답
  - agent.py:99 주석 ★: "코드단 deterministic — LLM 응답 무관"
- **설계 의도**:
  - LLM 비결정성 제거 — recovery_days 는 retrieve.py 의 결정론 결과 (productivity ≥ baseline×0.95 first day) 만 사용
  - `_build_scenarios` percentile 산출의 input
- **대응 패턴**:
  - 입력: cases (각 case 의 recovery.recovery_days 포함)
  - 처리: Counter([c["recovery"]["recovery_days"] for c in cases])
  - 출력: `{"d+1": N, "d+2": N, ..., "not_recovered": N}`
- **관련**:
  - 호출자: `_compose_row` (agent.py:~150)
  - 후속: `_build_scenarios` (view_builder.py)
- **Suspected related**:
  - retrieve.py `fetch_recovery_trajectory` — recovery_days 산출 원천

---

### `_call_azure_llm` — Azure gpt-5.1 호출 (fail-fast)

- **위치**: `pipeline/agents/optimizer/agent.py:~175`
- **시그니처**: `async def _call_azure_llm(llm_input, cfg, azure) -> dict`
- **이슈**:
  - 결정 #10: fail-fast (LLM crash 전체 fail, retry X)
  - PoC 시연 — 비결정성 차단 우선
- **설계 의도**:
  - 시연 path 단순화 — LLM 실패 시 cycle 전체 fail (조용한 fallback X)
  - 다음 cycle 회복 — error log + 사용자 수동 retry
- **대응 패턴**:
  - 입력: llm_input (prompt + cases), cfg, azure client
  - 처리: messages 조립 → Azure gpt-5.1 호출 → JSON parse
  - 출력: dict (LLM JSON response) 또는 Exception (fail-fast)
- **관련**:
  - 호출자: `optimize` (agent.py:~50) inner loop
- **Suspected related**:
  - prompt.py SYSTEM_PROMPT / FEW_SHOT_MESSAGES

---

### `fetch_degradation_cases` — 2-step retrieve Step 1

- **위치**: `pipeline/agents/optimizer/retrieve.py:~30`
- **시그니처**: `def fetch_degradation_cases(metadatas, documents, company, l6_main, today, baseline_unit, baseline_value, n=5) -> list[dict]`
- **이슈**:
  - 결정 #14: 저하 정의 = conditions ∋ {장비대기, 자재미입고, 돌관} **and** productivity < baseline×0.85
  - 결정 #19: conditions = comma-joined str (예: "맑음,장비대기")
- **설계 의도**:
  - hil_2 preview 용 + Optimizer LLM input
  - top-N recency (날짜 내림차순) — 최근 사례 우선
  - worker_source ∈ {synthetic_v2, mh_prorated} 만 (synthetic noise 제외)
- **대응 패턴**:
  - 입력: Chroma metadatas + documents (hil_2 coll.get F5 1회 호출 결과)
  - 처리: filter (incident keyword + prod threshold) → recency sort → top-N
  - 출력: list[dict] (date, conditions, productivity, assigned_workers, activities)
- **관련**:
  - 호출자: graph.py `hil_2_node` (graph.py:351~355) — Chroma F5 정정
  - 페어: `fetch_recovery_trajectory` — Step 2 (각 case 의 recovery)
- **Suspected related**:
  - `fetch_recovery_trajectory` — 본 함수 결과 의 사후 호출
  - `_group_baseline` — baseline_value 산출 source

---

### `fetch_recovery_trajectory` — 2-step retrieve Step 2

- **위치**: `pipeline/agents/optimizer/retrieve.py:~80`
- **시그니처**: `def fetch_recovery_trajectory(metadatas, company, l6_main, case_date, today, baseline_unit, baseline_value, window=7) -> dict`
- **이슈**:
  - 결정 #13: 회복 정의 = productivity ≥ baseline × 0.95 → 첫 ✓까지 일수 (1-based)
  - window=7 (case_date+1~+7)
- **설계 의도**:
  - case 별 recovery_days 결정 — `_compute_recovery_distribution` input
  - 미회복 → recovery_days=None → distribution 의 "not_recovered" 키
- **대응 패턴**:
  - 입력: Chroma metadatas, company, l6_main, case_date, today, baseline, window=7
  - 처리: case_date+1 ~ +7 일 productivity 측정 → ≥ baseline×0.95 first day
  - 출력: `{trajectory: [...], recovery_days: int | None}`
- **관련**:
  - 호출자: graph.py `hil_2_node` (graph.py:351~355) — for case in cases loop
  - 페어: `fetch_degradation_cases` — Step 1
- **Suspected related**:
  - `_compute_recovery_distribution` (agent.py:99) — recovery_days 의 indirect 소비

---

### `_group_baseline` — baseline value 산출 (cold_start 분기)

- **위치**: `pipeline/agents/optimizer/retrieve.py:~120`
- **시그니처**: `def _group_baseline(metadatas, company, l6_main, baseline_unit) -> Optional[float]`
- **이슈**:
  - F7 정정 (spec §8.2): None 분기 명시
  - cold_start signal: baseline_value=None or main_unit=None
- **설계 의도**:
  - 조건 incident 없는 행들의 productivity 평균 (정상 baseline)
  - 데이터 부족 시 None → hil_2_node 에서 `pre_cases[key]=[]` + cold_start payload
- **대응 패턴**:
  - 입력: metadatas (Chroma get 결과), company, l6_main, baseline_unit
  - 처리: filter (incident 없음) → productivity 평균
  - 출력: float 또는 None
- **관련**:
  - 호출자: hil_2_node (graph.py:358~371)
- **Suspected related**:
  - graph.py hil_2_node — None 분기 처리 직접 소비

---

### `generate_synthetic_v2_group` — state machine 7 회복 룰

- **위치**: `pipeline/agents/optimizer/synthetic_v2.py:generate_synthetic_v2_group`
- **시그니처**: `def generate_synthetic_v2_group(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days, seed, reference_date) -> list[dict]`
- **이슈**:
  - spec §4.1 7 회복 룰
  - 결정 #22: work_content = l7_5_activity 단순 활동명 (조건 텍스트 X)
  - 결정 #19: conditions = comma-joined str
  - 결정성: random.Random(seed) 만 (전역 random 금지)
- **설계 의도**:
  - 90일 synthetic 시계열 → Chroma `daily_activities` 적재
  - 7 회복 룰: 장비대기 (1d/2d), 우천 (2d+), 자재미입고, 야간연장, 돌관, ...
- **대응 패턴**:
  - 입력: company, l6_main, activity_pool, baseline_*, days, seed, reference_date
  - 처리: state machine (90일 loop, 회복 룰 7건 random.Random(seed) 적용)
  - 출력: list[dict] (Chroma 적재 row)
- **관련**:
  - 호출자: `scripts/load_master_list.py` (synthetic v2 적재 CLI)
- **Suspected related**:
  - `_BP_TOTAL` (synthetic_v2.py) — 그룹별 BP 총 인원

---

### `generate_fake_daily_report` — Demo Activity 직접 생성

- **위치**: `pipeline/agents/optimizer/synthetic_daily_report.py:generate_fake_daily_report`
- **시그니처**: `def generate_fake_daily_report(report_date, scenarios, activity_pools, baseline_workers, baseline_qty, seed) -> list[Activity]`
- **이슈**:
  - spec §10.2: Activity list 직접 생성 (Parser/Mapper skip)
  - conditions = list[str] (mapper 호환)
- **설계 의도**:
  - synthetic_daily_report.py CLI 의 input — build_demo_graph 진입
  - 데모 시연용 (forecaster → hil_2 → optimizer → reporter 경로)
- **대응 패턴**:
  - 입력: report_date, scenarios (n개), activity_pools, baseline_*, seed
  - 처리: scenarios iteration, 각 scenario 마다 n_activities random.Random(seed) 생성
  - 출력: list[Activity] (mapper 호환)
- **관련**:
  - 호출자: synthetic_daily_report.py main (`python -m pipeline.agents.optimizer.synthetic_daily_report ...`)
  - graph: build_demo_graph 진입
- **Suspected related**:
  - `_initial_state` (synthetic_daily_report.py)
  - `build_demo_graph_config`

---

## 변경 사항 정리 (cf3c143..HEAD, optimizer 13 commits)

| Commit | 날짜 | 변경 |
|---|---|---|
| 2788cfa | 2026-05-17 | feat(view_builder): _build_productivity_views + _compose_evm (EVM core 초기) |
| b20549d | 2026-05-18 | feat(view_builder): _build_kpi + bars |
| 48e14cd | 2026-05-18 | feat(view_builder): _build_quadrant + impact P90 |
| 42bc99a | 2026-05-18 | feat(view_builder): _build_s_curve + _merge_curves + _extend_forecast |
| f25d945 | 2026-05-18 | feat(view_builder): _build_optimizer_view — 4 섹션 |
| 7fa3dd9 | 2026-05-18 | feat(optimizer): build view jsonb + daily_reports UPSERT + state.site_id |
| e432dc2 | 2026-05-18 | feat(view_builder): _evm_by_group 구현 (group_key 다형성) |
| 64318f6 | 2026-05-18 | feat(backfill): daily_report_views 기존 cycle 채움 |
| c404086 | 2026-05-19 | fix(view_builder): _evm_for_group plan scope actual scope |
| 82ca0b4 | 2026-05-19 | fix(view_builder): _evm_for_group mapped CTE filter |
| 87d5cbf | 2026-05-19 | fix(view_builder): EVM 산식 컨셉 변경 — 분모=마스터플랜 전체 |
| 3781e5b | 2026-05-19 | optimizer: add _build_scenarios + scenarios_jsonb upsert |
| 105ee6a | 2026-05-19 | fix: review feedback — recovery wiring + e2e negative + date coerce |

## 설계 결정 (spec 2026-05-16 의 21 결정 중 핵심)

| # | 결정 | 위치 |
|---|---|---|
| #8 | pre_optimizer_cases 사전 영속 (retrieve 재호출 X) | graph.py hil_2_node |
| #10 | fail-fast (LLM crash 전체 fail) | agent.py `_call_azure_llm` |
| #11 | cold_start < 3 cases → LLM skip | agent.py `_compose_cold_start_row` |
| #13 | recovery ≥ baseline × 0.95 | retrieve.py `fetch_recovery_trajectory` |
| #14 | degradation ∋ incident **∧** < baseline × 0.85 | retrieve.py `fetch_degradation_cases` |
| #19 | conditions = comma-joined str | atomizer/optimizer 통일 |
| #20 | recovery_distribution = 코드단 Counter (LLM override) | agent.py `_compute_recovery_distribution` |
| #22 | work_content = 단순 활동명 (조건 텍스트 X) | synthetic_v2.py |

## 미해결 / Backlog

- **view_builder 함수 밀도 (18 helper + 8 public)** — 향후 섹션별 모듈 분리 검토
- **RAG fixture_prod vs synthetic_v2 ±10% mismatch** — cycle C 검증 pending (issue #N1)
- **scenarios 시나리오명 i18n** — no_action/optimistic_p25/base_p50/pessimistic_p75 영문 고정
- **kpi_jsonb / wp_summary_jsonb / quadrant_jsonb** Phase 2 — activity_master.plan_start/finish 의존성 (issue #N4)
- **EVM 산식 반복** — `_compose_evm` 패턴이 _evm_for_group / _evm_by_group 에서 반복, 제네릭 aggregation fn 추상화 검토
