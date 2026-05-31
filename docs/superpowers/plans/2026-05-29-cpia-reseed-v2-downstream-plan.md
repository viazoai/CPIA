# CPIA 재적재 v2 다운스트림 — 단위별 SSOT + 실 prod 그래프 적재 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** #1 게이트를 통과한 현실적 seed(정규분포+조건엔벨로프+총합보존+stretch)를 **실 prod 그래프(forecaster→optimizer→reporter)** 에 흘려, 9/24 리포트 화면의 생산성·딜레이·공기단축 숫자가 단위(unit)별로 일관되게(SSOT) 나오게 한 뒤, **같은 로직으로 전 기간(2024-04-11~2025-09-24)을 월별 재적재하고 매월 UI 를 직접 검토·보완해 전체 재적재까지 완료**한다.

**Architecture:** seed 는 mapper_activities 입력만 채우고(fixture forecasts/advice write 제거), backfill 이 atomizer 없는 `build_demo_graph` 를 seed 와 **같은 run_id** 로 돌려 forecasts/views 를 실제 생성한다. forecaster 가 단위별 스트림으로 bottleneck delay 를 산출(딜레이 SSOT), view_builder 가 **실 seeded today_qty**(현 `_simulate_today_qty` 폐기)로 단위별 생산성 카드를 만들고, catch-up 곡선은 BE 산출 배수 k 로 점진 수렴한다.

**Tech Stack:** Python 3.9 (`from __future__ import annotations`, `uv run`), LangGraph, asyncpg/PostgreSQL(AWS 43.200.85.209:5532), ChromaDB(5533), Next.js/TypeScript(web/, `npm run dev2` 5537), pytest.

---

## 0. 컨텍스트 · 정독으로 확정한 사실 (구현 전 필독)

> 본 플랜의 모든 라인번호/코드는 2026-05-29 3차 세션 실파일 정독 기준. 선행 설계: [`docs/superpowers/specs/2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md`](../specs/2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md) §3·§4·§8·§9.

### 0.1 절대 제약 (사용자 verbatim — 위반 시 무효)
- **데이터 적재는 실 prod 그래프 출력만.** mapper_activities(atomizer 앞단 입력) 주입만 스크립트 허용. forecaster/optimizer/reporter 출력을 fixture 로 쓰지 않는다 — 로직은 전부 prod 에 녹인다. 그래프 시작지점 조정만 허용.
- 공종 = **건축·토목 한정**. 6월 이전 DELETE 금지(전체 재적재 orphan 정리는 Group F 의 명시 예외). commit = 사용자 요청 시만. main 머지 = 조형준 프로.
- **★ 모든 Task 의 `Commit` step 은 이 제약 하에 — 사용자 승인 시에만 실행**(미승인 시 working tree 유지, push/PR 금지).
- **★ 2026-05-29 제약 조정 (사용자 verbatim):** (1) **DB 적재는 금지가 아님 — "정제해서 DB 적재" 가 최종 목표.** 정상 seed/backfill/views 적재는 승인 대기 없이 진행. 단 F.1 orphan **대량 DELETE** 만 실행 직전 실 COUNT 인용 후 진행(안전 확인 보고용). (2) **TaskCreate 허용** — 필요 시 sub-task 생성 가능(단 #163~168 6개 골격은 유지). (3) commit/push 와 main 머지는 여전히 사용자 승인/조형준 프로.
- **★ 진짜 목표(사용자 verbatim, 2026-05-29):** 적재만이 아니라 **prod 파이프라인(특히 optimizer)이 실 LLM 으로 제대로 돌아 의도대로 적재 → UI 로 직접 확인 → 이상(특히 "원래 LLM 산출이어야 하는데 cold start/옛 잔재로 룰베이스로 뽑힌 것") 캐치·보완.** ⇒ 모든 게이트(E·G)에 **LLM-driven 검증 차원** 필수(아래 0.3⑨).

### 0.2 seed v2 가 이미 채우는 것 (#1 게이트 통과 자산)
`scripts/seed_dummy_year.py:_build_mapper_row`(:331) 가 활동·일자별로 채우는 실값:
- `today_qty` = `series["actual_daily"][idx]` (조건 factor 반영 현실값, :355)
- `today_cum_qty` = `series["cum_qty"][idx]` (Σ일별, 구 `plan_total×cum_frac` 버그 제거, :356)
- `assigned_workers` = `max(1.0, series["mh_daily"][idx] / 8.0)` (mh 기반 현실값, :363)
- `cum_actual_mh_today`, `conditions`, `work_content`(저하/회복), `plan_total_qty`, `plan_mh`, `unit`
→ **view_builder 가 실 today_qty/workers 를 그대로 쓰면 조건이 생산성에 흐른다.** (현재는 안 흐름 — 0.3 ①)

### 0.3 정독으로 새로 발견한 결정적 사실 (스펙 §3~4 보강)
1. **★ `_build_productivity_views_v2` 가 실 today_qty 를 버린다.** `view_builder.py:1707` 가 `_simulate_today_qty(daily_qty_master, daily_workers_master, seed)` 로 today_qty/workers 를 **난수 재생성**(seed=sha256(date|l7_5|company), 중심 85% ±20% + outlier). `r["today_qty"]`(실 seeded)는 SELECT(:1645)만 하고 미사용. → **생산성 카드가 조건 무관·forecaster 와 불일치.** #164 핵심 = 시뮬 폐기 후 실값 사용.
2. **forecasts 테이블 = JSONB 자유컬럼 없음.** `insert_forecast`(db.py:260) 29 고정컬럼. `today_qty_by_unit`·`plan_total_qty_by_unit` 만 jsonb. → per-unit delay/productivity JSONB 추가 = migration(B_Track). **회피: 카드에 보이는 delay 는 bottleneck 스칼라 1개 → 기존 `delay_days` 컬럼에 저장. per-unit detail(m³/인 등)은 view_builder 가 mapper_activities(unit 보존)에서 직접 계산.** migration 0.
3. **run_id 일원화 = 1줄 교체.** backfill 에 이미 `_dummy_seed_run_id(d)`(:97, seed `_date_run_id` 와 동일 sha256) 존재. `_run_one_date` 의 `run_id = uuid.uuid4()`(:216)만 이걸로 교체 + pipeline_runs INSERT 를 `ON CONFLICT DO NOTHING`(seed 가 이미 INSERT) 로.
4. **hours_saved 블로커.** `reporter_node`(graph.py:456-460) 가 `atomized_count=len(state["atomized_ids"])`. `build_demo_graph` 는 atomizer 노드 없음 → atomized_ids=[] → hours_saved 증분 0. seed 는 `pipeline_runs.atomized_count = n_active`(seed_day:747) 를 이미 박음. → reporter 가 그 컬럼을 읽도록 보완.
5. **seed_day 7~9단계 = fixture write.** `seed_day`(:658) 1~6(pipeline_runs/parser/mapper/mapped_history) 는 입력. 7(forecasts via `_build_forecast_row`:771) · 8(optimizer_advice:781) · 9(daily_reports/view jsonb) 가 fixture. → 제거 대상. `_build_forecast_row`(:422)·`_build_optimizer_advice`(:496)·`_classify_assessment`(:412) dead code.
6. **mapped_history collapse.** `insert_mapped_history_batch`(db.py:462) ON CONFLICT `(run_id,wa,l6_main,company)` last-value. seed 가 unit 별 row 를 보내도 마지막 unit 만 생존. **단 리포트 생산성 화면(view_builder v2)·s_curve·forecaster 는 mapper_activities 직독** — mapped_history 미사용. 소비처는 `api.py:_WP_SUMMARY_SQL`(:419, wp_summary endpoint)·`_TASKS_ITEMS_SQL`(:920, l6/company 이름만). → #166 에서 소비처 live 여부 확인 후 결정(과설계 금지).
7. **딜레이 SSOT = `forecaster/aggregate.py:compute_delay` 한 곳.** view_builder KPI delay 는 `forecasts.delay_days` MEDIAN(view_builder.py:1948). view_builder 만 고치면 −37 재발.
8. **dead code (손대지 말 것):** `_evm_by_wa_l6_company`·`_compose_evm`·`_build_quadrant`·`_build_wp_summary`·`_build_kpi`·v1 `_build_productivity_views`. live 생산성 경로 = `_build_productivity_views_v2`(:1626) 단 하나(optimizer/agent.py 가 호출 → 9 jsonb upsert).
9. **★ 룰베이스 잔재 = 실측 확정 (2026-05-29 DB recon).** optimizer_advice `diagnosis LIKE '오늘 생산성은 정상 범위로 판단됨%'` = **5,891 rows / 416 runs**, created 2026-05-26~27. **현 코드엔 그 문구 없음**(grep 0) → 과거 버전이 남긴 DB 잔재 = 사용자가 말한 "옛 잔재 룰베이스". 저하/회복 WP 의 LLM 서사("…분기점입니다")도 현 코드에 없음 = 진짜 LLM. `is_mock` 전부 FALSE(oa 26,132 / pr 1,094) → LLM-vs-룰 구분 신호로 **무용**. ⇒ **재적재가 잔재를 실 LLM 출력으로 덮어쓰는 게 핵심.** orphan mapper/parser = 각 148,157(93.6%). 쓰레기 날짜 `pipeline_runs.report_date='2099-01-01'` 1건. 스키마 2개(public + backup_20260521). **LLM-provenance 판별 신호(workflow w0eld2c6l 확정):** ① backfill stdout `optimizer_advice rows=N (LLM-driven=X, cold_start=Y)` 의 X≥1 ② `scenarios_jsonb.by_wp[*]` 에 `rationale` 키 존재(LLM `_wp_block_from_llm` view_builder:1376 vs 룰 `_wp_block_deterministic` :1386 omit) ③ 잔재 SQL `diagnosis LIKE '오늘 생산성은 정상 범위로 판단됨%'`=0 ④ 동일 입력 2회 시 diagnosis 텍스트 varies(LLM)·생산성 숫자 동일(룰) ⑤ Chroma upsert 로그 0(build_demo_graph=atomizer 없음). **FE 함정:** ForecastChart 캡션 "…기반 LLM 산출"(:427-430)이 룰베이스에도 무조건 표시 → 캡션만 믿지 말고 ②로 교차검증.

---

## 1. 미해결 결정 확정 (설계 §9 의 10건 — 본 플랜에서 lock)

| # | 결정 | 채택 | 근거 |
|---|------|------|------|
| 1 | forecasts 저장 grain | **l6 1 row, bottleneck delay 스칼라.** per-unit detail 은 view_builder 계산 | 0.3②: forecasts JSONB 자유컬럼 없음 → migration 회피. api 소비자 무파손 |
| 2 | catch-up 배수 k | **BE 산출 → `scenarios_jsonb`.** 기본 k=2.0, 실 UI(#167) 보고 사용자 최종 확정 | 사용자 deferral("실 UI 보고"). FE 상수는 fallback만 |
| 3 | days_elapsed 정의 | **`(today − plan_start).days`** (현 `compute_delay:146 today_offset` 그대로) | 기존 코드 컨벤션 일치. off-by-one 일관 |
| 4 | 헤드라인 평균 vs median | **현 `_weighted_median` 유지** | site=Σcard 불변식 보존(안전). 변경 시 SSOT 정합 깨짐 |
| 5 | mh 가중치 source | unit별 plan_mh = `fetch_plan_for_group` 가 unit 분해 안 함 → **view_builder 는 activity_master LATERAL 의 unit별 `plan_mh_rev2` SUM 사용**(이미 row 별 보유:1647) | mapper row 별 plan_mh 가 이미 unit 단위 |
| 6 | delay actual_rate 분모 클램프/fallback | **actual_cum=0 or days_elapsed≤0 → 기존 `plan_per_day_qty` fallback. delay_days 절대값 `min(delay, total_days)` 캡** | aggregate.py 폭주(26,517일) 재발 방지 |
| 7 | wa 차원 | **현 `wp_id=(wa,l6,company)` 유지** | quadrant↔optimizer Jaccard 정합 의존. 안전 |
| 8 | 회복분포 카드 존치 | **gap기반 recovery_days 로 대체** (회복분포 텍스트는 이미 상세현황서 제거됨) | 메모리 2차: "회복분포 제거". 중복 방지 |
| 9 | run_id 일원화 방식 | **backfill 이 `_dummy_seed_run_id` 재사용** + pipeline_runs INSERT ON CONFLICT DO NOTHING | 0.3③ |
| 10 | per-unit Chroma | **안 함** (doc_id 에 unit 없음, retrieve 는 l6 레벨 충분) | 설계 §4. atomizer 없는 build_demo_graph 라 Chroma 미접근 |

---

## 2. 파일 구조 (생성/수정 대상)

**수정 (BE):**
- `pipeline/agents/forecaster/aggregate.py` — `compute_delay` 분모 actual_rate + 클램프 (Task 3.1)
- `pipeline/agents/forecaster/agent.py` — `_forecast_one_group` 단위별 bottleneck delay (Task 3.2)
- `pipeline/agents/forecaster/classify.py` — `DELAY_DAYS_BOUND` 재튜닝 (Task 3.3)
- `pipeline/agents/optimizer/view_builder.py` — `_simulate_today_qty` 폐기·실 qty·l6 라벨·단위별 detail·s_curve unit grain (Task 4.1~4.4) + `_build_scenarios` recovery_days gap기반·k (Task 5.1)
- `pipeline/graph.py` — `reporter_node` hours_saved 를 pipeline_runs.atomized_count 에서 (Task 6.2)
- `scripts/backfill_optimizer_advice_llm.py` — `build_demo_graph` 전환 + run_id 재사용 (Task 6.1)
- `scripts/seed_dummy_year.py` — `seed_day` 입력전용(7~9 제거) + dead code 정리 (Task 6.3)

**수정 (FE):**
- `web/lib/diagnosis.ts` — `buildScenarioCurve` boosted rate 점진 (Task 5.2)
- `web/lib/types.ts` / `web/lib/diagnosis-adapter.ts` — k 전달 필드 (Task 5.2)

**신규 (test):**
- `pipeline/tests/forecaster/test_compute_delay_actual_rate.py` (Task 3.1)
- `pipeline/tests/forecaster/test_forecast_bottleneck_unit.py` (Task 3.2)
- `pipeline/tests/test_view_builder_real_qty.py` (Task 4.1)
- `web/lib/__tests__/diagnosis-catchup.test.ts` 또는 기존 패턴 (Task 5.2)
- `scripts/verify_downstream_coherence.py` — 9/24 컴포넌트 정합 결정론 검증 (Task 7.1, DB write 0)
- `scripts/sql/delete_orphan_mapper.sql` — orphan mapper/parser NOT EXISTS DELETE (Task F.1)

**전 기간 재적재(Group F/G)는 기존 스크립트 재사용(신규 0):** `clean_window.py`·`seed_dummy_year.py`(★날짜 `--start/--end`, trades 공백구분 `건축 토목`)·`backfill_optimizer_advice_llm.py`(Task 6.1 전환분, 날짜 `--start-date/--end-date`, trades 콤마 `건축,토목`)·`backfill_daily_report_views_v2.py`·`verify_backfill_passing.py`. **두 스크립트의 --trades 파싱이 다름**(seed=nargs="+", backfill=split(",")) — 복붙 주의.

**참조만 (수정 X — dead code):** view_builder v1 함수군(0.3⑧), api.py `_WP_SUMMARY_SQL`(소비처 확인용).

---

## 3. Task Group A (#163) — forecaster 단위별 + 딜레이 actual_rate + bottleneck

> 딜레이 SSOT. 순수함수 우선 TDD. 게이트: 9/24 seeded 데이터로 delay 분포가 현실적(지각 WP 가 +N일, 정상 WP 가 0).

### Task 3.1: compute_delay 분모 → actual_rate (deficit ÷ 누적평균일생산)

**Files:**
- Modify: `pipeline/agents/forecaster/aggregate.py:142-167`
- Test: `pipeline/tests/forecaster/test_compute_delay_actual_rate.py` (Create)

현재(`aggregate.py:142-150`): `plan_per_day_qty = plan_total/total_days; deficit = plan_qty_to_date − actual_cum; delay_days = round(deficit / plan_per_day_qty)`.
변경: 분모를 **실제 누적평균일생산 `actual_rate = actual_cum_qty / days_elapsed`** 로. (사용자 예: deficit 50 ÷ actual_rate 10 = 5일)

- [ ] **Step 1: 실패 테스트 작성**

```python
# pipeline/tests/forecaster/test_compute_delay_actual_rate.py
from __future__ import annotations
from datetime import date
from pipeline.agents.forecaster.aggregate import compute_delay

def _plan(start, finish, mh=800.0):
    return {"plan_start": start, "plan_finish": finish, "plan_mh_sum": mh}

def test_delay_uses_actual_rate_not_plan_rate():
    # 100일 plan, 총 1000 qty. 10일 경과, 실적 50 누적(계획 100 대비 50 부족).
    # 실제 페이스 = 50/10 = 5/일. delay = 50 부족 ÷ 5 = 10일.
    # (구 plan_rate: plan_per_day=10 → 50/10 = 5일. 둘이 달라야 actual_rate 적용 증명.)
    plan = _plan(date(2025, 1, 1), date(2025, 4, 10))  # 100일
    out = compute_delay(
        plan, today=date(2025, 1, 10), actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0, actual_cum_qty=50.0, plan_total_qty_main=1000.0, today_qty_main=5.0,
    )
    assert out["delay_days"] == 10  # actual_rate 기반 (구 5 아님)

def test_delay_fallback_to_plan_rate_when_actual_zero():
    plan = _plan(date(2025, 1, 1), date(2025, 4, 10))
    out = compute_delay(
        plan, today=date(2025, 1, 10), actual_window_start=None,
        actual_cum_mh=0.0, actual_cum_qty=0.0, plan_total_qty_main=1000.0, today_qty_main=0.0,
    )
    # actual_cum=0 → 분모 0 폭주 금지. plan_per_day fallback (deficit 100 ÷ 10 = 10일).
    assert out["delay_days"] == 10

def test_delay_capped_at_total_days():
    plan = _plan(date(2025, 1, 1), date(2025, 1, 11))  # 11일 plan
    out = compute_delay(
        plan, today=date(2025, 1, 11), actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0, actual_cum_qty=1.0, plan_total_qty_main=1100.0, today_qty_main=0.1,
    )
    # 거의 0 페이스 → delay 폭주를 total_days(11) 로 캡.
    assert out["delay_days"] <= 11
```

- [ ] **Step 2: 실패 확인** — `cd pipeline && uv run pytest tests/forecaster/test_compute_delay_actual_rate.py -v` → 첫 테스트 FAIL(현 5 반환).

- [ ] **Step 3: 구현** — `aggregate.py:142-167` 의 point-in-time 분기 교체:

```python
        plan_per_day_qty = plan_total_qty_main / total_days if total_days > 0 else 0.0
        remaining_qty = max(0.0, plan_total_qty_main - actual_cum_qty)

        # --- 主: point-in-time 누계 부족분 ÷ 실제 누적평균일생산 (2026-05-29 reseed v2) ---
        today_offset = (today - plan_start).days  # days_elapsed (결정 §9-3)
        # 실제 페이스(actual_rate) = 누적실적 / 경과일. 0 이면 plan_per_day 로 fallback (결정 §9-6).
        actual_rate = (actual_cum_qty / today_offset) if today_offset > 0 and actual_cum_qty > 0 else 0.0
        rate_denom = actual_rate if actual_rate > 0 else plan_per_day_qty
        if rate_denom > 0 and today_offset > 0:
            plan_qty_to_date = min(plan_per_day_qty * today_offset, plan_total_qty_main)
            deficit_qty = max(0.0, plan_qty_to_date - actual_cum_qty)
            raw_delay = round(deficit_qty / rate_denom)
            delay_days = max(-total_days, min(total_days, raw_delay))  # 캡 (결정 §9-6)
            if deficit_qty > 0:
                delay_basis = (
                    f"계획누적 {plan_qty_to_date:,.0f} − 실제 {actual_cum_qty:,.0f} "
                    f"= {deficit_qty:,.0f} 부족 ÷ 실제페이스 {rate_denom:,.1f}/일 "
                    f"→ {delay_days}일 지연"
                )
            else:
                delay_basis = (
                    f"계획누적 {plan_qty_to_date:,.0f} 대비 실제 {actual_cum_qty:,.0f} "
                    f"— 부족 없음 (일정 충족)"
                )
        else:
            delay_days = 0
        point_in_time_delay_days = delay_days
        expected_completion = plan_finish + timedelta(days=delay_days)
```

(forward 외삽 블록 170-179 는 그대로 유지 — `forward_delay_days` 참고 보존.)

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/forecaster/test_compute_delay_actual_rate.py -v` → 3 passed. + 회귀 `uv run pytest tests/test_aggregate_v10.py -v` (기존 compute_delay 테스트 — 변경된 분모로 기대값 조정 필요 시 함께 수정하고 사유 주석).

- [ ] **Step 5: Commit** — `git add pipeline/agents/forecaster/aggregate.py pipeline/tests/forecaster/test_compute_delay_actual_rate.py && git commit`

### Task 3.2: _forecast_one_group 단위별 스트림 → bottleneck delay

**Files:**
- Modify: `pipeline/agents/forecaster/agent.py:87-196` (집계~compute_delay)
- Test: `pipeline/tests/forecaster/test_forecast_bottleneck_unit.py` (Create)

현재(`agent.py:90-92`): `main_unit = max(positive_units by today_qty)` 단일 선정 → 그 unit 만 delay. 혼재 WP(남웅 철콘 ea·m²·m³·ton)면 매일 main_unit 이 바뀌고 다른 unit 지연이 묻힘.
변경: **positive unit 전부 per-unit delay 계산 → bottleneck(max delay) 을 카드 delay 로. main_unit = bottleneck unit.**

설계 노트:
- per-unit actual_cum = `fetch_pg_actual_cum_qty(pg, company, l6, today, unit)` 를 unit 마다 호출(이미 unit 인자 받음, aggregate.py:14).
- per-unit plan_qty = 그룹 내 `unit==u` 활동의 `plan_total_qty` distinct SUM (현 main_unit 한정 로직 agent.py:157-163 을 unit 루프로).
- per-unit delay = `compute_delay(plan, today, ..., actual_cum_qty=u_cum, plan_total_qty_main=u_plan, today_qty_main=u_today)`.
- 카드 `delay_days` = max(per-unit delay), main_unit = 그 unit, `today_productivity` = main_unit today_qty / workers (RAG 비교용 유지).

- [ ] **Step 1: 실패 테스트 (단위 헬퍼 추출)** — 순수 헬퍼 `_bottleneck_unit(per_unit_delays: dict[str,int]) -> str|None` 를 agent.py 에 추가하고 테스트:

```python
# pipeline/tests/forecaster/test_forecast_bottleneck_unit.py
from __future__ import annotations
from pipeline.agents.forecaster.agent import _bottleneck_unit

def test_bottleneck_picks_max_delay_unit():
    assert _bottleneck_unit({"m3": 2, "ton": 9, "m2": 0}) == "ton"

def test_bottleneck_none_when_empty():
    assert _bottleneck_unit({}) is None

def test_bottleneck_negative_all_picks_least_ahead():
    # 전부 앞섬(음수)이면 가장 덜 앞선(최댓값) unit.
    assert _bottleneck_unit({"m3": -5, "ton": -1}) == "ton"
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/forecaster/test_forecast_bottleneck_unit.py -v` → FAIL (`_bottleneck_unit` 미정의).

- [ ] **Step 3: 구현** — agent.py 에 헬퍼 추가:

```python
def _bottleneck_unit(per_unit_delays: dict[str, int]) -> str | None:
    """unit별 delay_days 중 최댓값(가장 지연된) unit = 병목. 빈 dict → None."""
    if not per_unit_delays:
        return None
    return max(per_unit_delays, key=lambda u: per_unit_delays[u])
```

그리고 `_forecast_one_group` ⑤(174-196) 를 unit 루프로 확장: positive_units 각각에 대해 plan_qty(distinct SUM)·actual_cum(`fetch_pg_actual_cum_qty` per unit)·`compute_delay` 호출 → `per_unit_delays[u] = delay_info_u["delay_days"]`. `main_unit = _bottleneck_unit(per_unit_delays)` 로 재지정, 카드 `delay_info` = bottleneck unit 의 것. (actual_cum=0 unit 은 delay None → 제외.)

- [ ] **Step 4: delay −37 회귀 테스트 추가** — 메모리 SSOT 근본원인(`actual_cum=Σtoday_qty(전체 row)` vs `plan_total=DISTINCT` 불일치 → remaining 0 → today−finish=−37)이 unit별 distinct SUM 으로 닫히는지 회귀로 박는다. test_forecast_bottleneck_unit.py 에 추가: 같은 (wa,company,l6) 에 동일 plan_total_qty 가 여러 mapper row 로 broadcast 된 경우 actual_cum 이 plan_total 을 초과해도 delay_days 가 음의 비현실값(−30 미만)이 아닌지 assert.

- [ ] **Step 5: 통과 확인** — `uv run pytest tests/forecaster/ -v` → green. 회귀 `uv run pytest tests/test_forecaster_concurrency.py tests/test_db_forecasts_wa.py -v`.

- [ ] **Step 6: Commit (사용자 승인 시)**

### Task 3.3: DELAY_DAYS_BOUND 재튜닝 + risk 분포 검증

**Files:**
- Modify: `pipeline/agents/forecaster/classify.py:23`
- Verify: `scripts/verify_downstream_coherence.py` (Task 7.1 에서 생성 — 여기선 임시 점검)

분모 변경(plan_rate→actual_rate)으로 지연 WP 의 delay_days 가 커진다 → `DELAY_DAYS_BOUND=5`(classify.py:23) 임계에 더 많이 걸려 risk_level 대량 격상 가능.

- [ ] **Step 1: 9/24 실 분포 측정** — Task 3.1~3.2 적용 후, seed 된 9/24 데이터로 forecaster 만 돌려 delay_days 분포 출력(임시 스크립트 또는 verify):
  Run: `cd pipeline && set -a; source ../.env.local; set +a; PYTHONPATH=$PWD/.. uv run python -c "..."` (그룹별 delay_days 히스토그램).
  Expected: 지각 WP(설계 §8: 지각 111건 p50 0.66) 가 +N일, 정상 WP 0.
- [ ] **Step 2: 임계 결정** — 분포 보고 `DELAY_DAYS_BOUND` 를 조정(예: 정상 WP 가 주의로 새지 않는 하한). **실 출력 인용** 후 값 확정.
- [ ] **Step 3: 적용 + 재측정** — 변경 후 risk_level(정상/주의/이상) 비율이 의도(정상 다수, 지각만 주의/이상)와 일치 확인.
- [ ] **Step 4: Commit**

**게이트 A:** 9/24 forecaster delay 분포가 "지각 WP 만 지연, 정상 WP 0" + risk_level 분포 현실적. 실 명령+출력+결론 보고.

**✅ Group A 완료 — 검증 (2026-05-29):**
- 3.1: `compute_delay` 분모 plan_rate→actual_rate + 캡. `tests/forecaster/test_compute_delay_actual_rate.py` 3 passed. 회귀 `test_aggregate_v10.py`(2건 7→14 actual_rate 로 교정) + `test_aggregate.py`(4건 forward 모델 stale → point-in-time 으로 갱신: behind ~45, ahead 0, zero_total 0, plan_mh_zero ~5) 모두 green. **forecaster 전체 89 passed, 1 skipped.**
- 3.2: `_bottleneck_unit` 헬퍼(3 passed) + `_forecast_one_group` ②-b 에 positive unit 전부 per-unit delay → bottleneck 으로 main_unit 재지정·today_productivity 재산출. `fetch_pg_actual_cum_qty` = `SUM(today_qty)`(per-activity, 과다집계 아님), plan 만 distinct SUM.
- 3.3: **재튜닝 불필요** — 9/24 delay 전부 0(bound 미발동), risk_level 정상 9/이상 1/주의 1(健全).
- **9/24 재실행(3.1+3.2): advice LLM 11/11, 잔재 0, delay {neg:0,zero:11,pos:0}.** 전부 0 = **정상**: 11 WP 모두 on_schedule(plan_finish 9/30~11/28, 진행중), seed bell 분포가 중반에 누적이 linear 계획-to-date 를 추월(예: 수장 선보 actual 159.8 > 계획 144.1) → deficit 0. 수식 정확(단위테스트가 deficit→+N 증명).
- ⚠️ **미해결(Group E 사용자 판단)**: 9/24 showcase 에 schedule delay 가 안 보임(bell-actual 이 linear-plan 추월). 데모에서 "D+N 지연" 을 9/24 에 노출하려면 seed/계획곡선 조정 필요. risk(이상/주의)는 productivity_ratio 로 표현되니 데모상 무용은 아님. **pre-existing 회귀**: `test_forecaster_integration.py::test_forecaster_sebo_with_synthetic`(assessment None) — HEAD 에서도 FAIL(seeded Chroma/plan 의존 slow test, 내 변경 무관).

---

## 4. Task Group B (#164) — view_builder 실 qty·l6 라벨·단위별 detail

> live 경로 `_build_productivity_views_v2`(:1626) 내부만. **시뮬 폐기가 핵심.**

### Task 4.1: `_simulate_today_qty` 폐기 → 실 seeded today_qty/workers 사용

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1689-1736` (row별 산식)
- Test: `pipeline/tests/test_view_builder_real_qty.py` (Create)

현재(:1703-1710): `seed=sha256(...); sim=_simulate_today_qty(...); perperson=sim["today_qty"]/sim["workers"]`. 실 `r["today_qty"]`/`r["assigned_workers"]` 미사용.
변경: `perperson = r["today_qty"] / r["assigned_workers"]` (실값). `_simulate_today_qty` 호출 제거.

- [ ] **Step 1: 실패 테스트** — 산식을 순수 헬퍼로 추출해 테스트 가능하게. `_row_productivity(today_qty, assigned_workers, daily_qty_master, daily_workers_master) -> dict(perperson, productivity)` 추출:

```python
# pipeline/tests/test_view_builder_real_qty.py
from __future__ import annotations
from pipeline.agents.optimizer.view_builder import _row_productivity

def test_real_qty_drives_productivity():
    # master daily = 10 qty / 2 workers = 5/인. 실적 6 qty / 2 workers = 3/인 → 60%.
    out = _row_productivity(today_qty=6.0, assigned_workers=2.0,
                            daily_qty_master=10.0, daily_workers_master=2.0)
    assert round(out["perperson"], 2) == 3.0
    assert round(out["productivity"], 1) == 60.0  # 조건 저하가 그대로 반영

def test_zero_workers_safe():
    out = _row_productivity(0.0, 0.0, 10.0, 2.0)
    assert out["perperson"] == 0.0
    assert out["productivity"] == 0.0
```

- [ ] **Step 2: 실패 확인** — `cd pipeline && uv run pytest tests/test_view_builder_real_qty.py -v` → FAIL (`_row_productivity` 미정의).

- [ ] **Step 3: 구현** — 헬퍼 추가 + `_build_productivity_views_v2:1701-1733` 에서 sim 제거:

```python
def _row_productivity(
    today_qty: float, assigned_workers: float,
    daily_qty_master: float, daily_workers_master: float,
) -> dict[str, float]:
    """실 seeded today_qty/workers 로 perperson + productivity%. (구 _simulate_today_qty 폐기)"""
    perperson = (today_qty / assigned_workers) if assigned_workers > 0 else 0.0
    master_perperson = (daily_qty_master / daily_workers_master) if daily_workers_master > 0 else 0.0
    productivity = min(_compute_productivity(perperson, master_perperson), 150.0)
    return {"perperson": perperson, "productivity": productivity}
```

★ 회귀 주의: `_simulate_today_qty` 를 제거하면 이를 import·assert 하는 `pipeline/tests/optimizer/test_view_builder_v2.py:16,30,31,40` 가 collection 단계에서 깨진다 — **같은 커밋에서 그 테스트 케이스(시뮬 동작 검증)도 제거/교체**할 것.

루프 내부(:1701-1733)에서 `sim=...` 3줄 삭제하고:
```python
        rp = _row_productivity(
            float(r["today_qty"] or 0.0), float(r["assigned_workers"] or 0.0),
            daily_qty_master, daily_workers_master,
        )
        perperson = rp["perperson"]
        master_perperson = daily_qty_master / daily_workers_master
        productivity = rp["productivity"]
        impact_raw = max(0.0, 100 - productivity) * plan_mh
```
items.append 의 `"today_qty": r["today_qty"]`, `"workers": r["assigned_workers"]` (실값).
**`_simulate_today_qty`(:1471) 는 다른 호출처 grep 확인 후 dead 면 제거**(`grep -rn "_simulate_today_qty" pipeline/`).

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_view_builder_real_qty.py -v` → 2 passed. + grep dead 확인.
- [ ] **Step 5: Commit**

### Task 4.2: 카드 라벨 l7_5 → l6_main

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1870-1872` (`_wp_name_with_wa`)

현재(:1870): `return f"{it['l7_5_activity']} · {wa}"`. → l6 표시최소단위(설계 §0-2: 남웅 무근/거푸집/철근 → 철근콘크리트공사 1개).
변경: `it['l6_main']` 사용.

- [ ] **Step 1**: `_wp_name_with_wa` 를 l6 기준으로:
```python
    def _wp_name_with_wa(it: dict) -> str:
        wa = it.get("wa")
        return f"{it['l6_main']} · {wa}" if wa else it["l6_main"]
```
- [ ] **Step 2: 검증** — 9/24 PoC(Task 7) 시 quadrant/wp_summary 의 wp_name 이 "철근콘크리트공사 · {wa}" 로 표기. (단독 테스트는 Task 7 통합검증에 포함.)
- [ ] **Step 3: Commit**

### Task 4.3: 카드 단위별 detail (혼재 WP 의 m³/인·ton/인 분리)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1838-1939` (grouped_items / quadrant / wp_summary)

현재(:1851): `agg_pp = agg_today_qty/agg_workers` — group(=wp_id) 의 today_qty 를 unit 무시 SUM(m²+ton+m³ 혼합). 혼재 WP 헤드라인 perperson 무의미.
변경: grouped_items 에 **`units_detail: list[{unit, perperson, productivity}]`** 추가(group 내 unit 별 집계). 헤드라인 perperson/unit 은 plan_mh 최대 unit(대표) 값. wp_summary/quadrant detail 에 units_detail 노출.

- [ ] **Step 1**: grouped_items 빌드(:1839-1868)에 unit별 집계 추가:
```python
        from collections import defaultdict as _dd
        by_unit = _dd(list)
        for it in grp:
            by_unit[it.get("unit")].append(it)
        units_detail = []
        for u, urs in by_unit.items():
            u_qty = sum((x.get("today_qty") or 0) for x in urs)
            u_workers = sum((x.get("workers") or 0) for x in urs)
            u_mh = sum((x.get("plan_mh") or 0) for x in urs)
            u_prods = [x["productivity"] for x in urs if x.get("productivity") is not None]
            units_detail.append({
                "unit": u,
                "perperson": round(u_qty / u_workers, 2) if u_workers else 0.0,
                "productivity": round(_stats.median(u_prods), 1) if u_prods else 0.0,
                "plan_mh": u_mh,
            })
        # 대표 unit = plan_mh 최대 (헤드라인 perperson_unit)
        rep = max(units_detail, key=lambda d: d["plan_mh"]) if units_detail else None
```
grouped_items dict 에 `"units_detail": sorted(units_detail, key=lambda d:-d["plan_mh"])`, `"rep_unit": rep["unit"] if rep else None`, `"rep_perperson": rep["perperson"] if rep else None` 추가.

- [ ] **Step 2**: quadrant(:1879-1904)·wp_summary(:1906-1939) 의 `perperson_unit`/`display_label` 을 단일 `it["unit"]`(head) → `it["rep_unit"]`/`it["rep_perperson"]` 로, 그리고 `"units_detail": it["units_detail"]` 필드 추가. (FE `types.ts` 에 `units_detail?` optional 추가 — 미사용 컴포넌트 무영향, 설계 §3-B 엣지: 단일 number 호환 위해 추가 필드로.)

- [ ] **Step 3: 검증** — Task 7 통합. 남웅 철콘 카드에 m³/인·ton/인·m²/인 분리 표기 + 헤드라인은 m³(plan_mh 최대) 확인.
- [ ] **Step 4: Commit**

### Task 4.4: s_curve actual 단위별 grain

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:967-1009` (actual WITH 절)

현재: `am_agg`/`day_qty` 가 (wa, l6_main) 그레인 → `cum_qty/plan_qty` 가 unit 혼합. 혼재 WP 의 진척률 왜곡.
변경: `unit` 차원 추가 — am_agg·day_qty GROUP BY 에 unit, full_grid/cum_actual PARTITION 에 unit. weight = unit별 `SUM(plan_wv*plan_mh_rev2)`.

- [ ] **Step 1**: actual SQL(:968-1009) 수정 — `am_agg` 에 `, unit` GROUP BY 추가, `day_qty` 에 `, ma.unit` GROUP BY 추가(`AND ma.unit IS NOT NULL`), `full_grid`/`cum_actual` USING 과 PARTITION 에 unit 포함. 최종 `SUM(weight * LEAST(1, cum_qty/NULLIF(plan_qty,0)))` 는 (wa,l6,unit) 단위로 누적 후 date 합. (planned 곡선 :940-953 은 이미 plan_wv×plan_mh 가중 SUM 이라 무변경 — 주석으로 명시.)
- [ ] **Step 2: 검증** — Task 7 통합: 9/24 s_curve actual % 가 #1 게이트 검증값(90.1%)과 ±2%pt 내. (verify_seed_numbers 의 단위별 집계와 대조.)
- [ ] **Step 3: Commit**

**게이트 B:** 9/24 view_builder 생산성 카드가 (a) 조건 저하 WP 가 낮은 %(시뮬 아님), (b) 라벨 l6, (c) 혼재 WP 단위별 detail, (d) s_curve actual ≈ #1 게이트값.

**✅ Group B 완료 — 구현+독립리뷰 (2026-05-29/30):**
- 4.1: `_simulate_today_qty` 폐기(import random 동반 제거) → `_row_productivity`(view_builder.py:1484, 실 r["today_qty"]/r["assigned_workers"] 사용 :1697-1718). `test_view_builder_real_qty.py` 신규 2 passed + `test_view_builder_v2.py` 시뮬테스트 제거·정합 → **15 passed**. grep `_simulate_today_qty` = docstring만.
- 4.2: `_wp_name_with_wa`(:1888) l7_5→l6_main 라벨. **grain 은 이미 `_wp_id_of(wa,l6_main,company)`** (l7_5 아님) → 라벨 변경만으로 중복카드 없음(리뷰 확인).
- 4.3: grouped_items `units_detail:[{unit,perperson,productivity(median),plan_mh}]` + `rep_unit`/`rep_perperson`(plan_mh 최대) → quadrant·wp_summary 노출. zero-guard 전부 有. `web/lib/types.ts` `UnitDetail`+`units_detail?` (TYPE only). `tsc --noEmit` 0 errors.
- 4.4: actual s_curve 에 unit 차원(am_agg/day_qty GROUP BY+unit, cum_actual PARTITION+unit, weight 단위별). **NULL-unit 실측 = mapper 0/158366·activity_master 0/3704 → `unit IS NOT NULL` 제외 0건 = 안전.** planned 곡선 불변(byte-identical+주석).
- ⚠️ **잔여**: (a) s_curve actual ≈ 90.1%±2 최종검증 = 실 run 필요 → **Group E**. (b) day_qty 에 site_id 필터 없음(이전 SSOT 작업의 의도적 tradeoff "단일 site 데모", orphan 93.6% 누락 방지) → 멀티site 잠재버그, **post-PoC 플래그**. (c) pre-existing `test_backfill_jsonb_cols_has_9`(scenarios_jsonb) 실패 = 이전 uncommitted scenarios 작업 산물(내 변경 무관).
- 📌 **귀속**: 리뷰어가 본 over-scope view_builder 재작성(`_build_optimizer_view`/`_diagnosis_prefix`/`_quadrant_status3`/scenarios-from-jsonb)·web 6컴포넌트 markup 변경은 **세션 시작 시 이미 M(이전 세션 uncommitted)** — Group B 서브에이전트 산물 아님. CPIA 디자인 불가침/PR 검토는 조형준 프로 영역.

---

## 5. Task Group C (#165) — catch-up 곡선 BE k + 점진 수렴

> 곡선이 plan_rate×k 로 점진 만회. k 는 BE 산출(scenarios_jsonb), 기본 2.0, #167 서 사용자 확정.

### Task 5.1: BE `_build_scenarios` — recovery_days gap기반 + k 산출

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1354-1454`

현재: recovery_days = LLM scenarios 또는 과거 회복분포 percentile(:1387). gap·rate 무관. site=Σby_wp(:1428, 유지).
변경: per-wp recovery_days = **gap기반 catch-up일 = deficit ÷ (boosted_rate − plan_rate)**, boosted_rate = plan_rate × k. k 기본 2.0(`_CATCHUP_K = float(os.environ.get("CPIA_CATCHUP_K", "2.0"))`). scenarios_jsonb 에 `catch_up_multiplier_k` 동봉. site recovery_days = Σ(by_wp) 유지(SSOT).

- [ ] **Step 1: 순수 헬퍼 테스트** — `_catchup_days(deficit_qty, plan_rate, k) -> int`:
```python
def test_catchup_days_gap_based():
    # deficit 100, plan_rate 10/일, k=2 → boosted 20, 초과율 10 → 100/10 = 10일.
    assert _catchup_days(100.0, 10.0, 2.0) == 10
def test_catchup_k_le_1_returns_cap():
    # k<=1 이면 만회 불가 → 캡(예 999) 반환, ∞ 금지.
    assert _catchup_days(100.0, 10.0, 1.0) >= 999
```
- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_view_builder_scenarios.py -k catchup -v` (없으면 신규 파일).
- [ ] **Step 3: 구현** — `_catchup_days` + `_build_scenarios` 의 wp 블록을 forecast(plan_total_qty_by_unit, plan_start/finish, actual deficit)에서 plan_rate·deficit 추출해 gap기반 recovery_days 산출. LLM scenarios 가 있으면 그 expected_completion 우선이되 recovery_days 는 gap기반으로 재산출. `catch_up_multiplier_k` 를 site/by_wp 블록에 추가.
- [ ] **Step 4: 통과 확인** + 회귀 `uv run pytest tests/test_view_builder_optimizer_view.py -v`.
- [ ] **Step 5: Commit**

### Task 5.2: FE `buildScenarioCurve` — boosted rate 점진 + k 소비

**Files:**
- Modify: `web/lib/diagnosis.ts:55-87` (`buildScenarioCurve`), `web/lib/types.ts`(`ScenariosSite` 에 k optional), `web/lib/diagnosis-adapter.ts:29-31`

현재(:62-65): catchUpSlope = (planAtCatchUp − lastActual)/span 단일 직선. recovery_days 가 곡선 형태 결정.
변경: boosted = plan_rate × k 로 일별 누적(actual += boosted, plan += plan_rate)하여 gap 이 (boosted−plan)/일로 닫히는 **점진 수렴 곡선**. catch_up 시점 = gap 이 0 되는 날.

- [ ] **Step 1: 실패 테스트** (기존 FE 테스트 패턴 확인 후) — boosted rate 곡선이 직선이 아니라 plan 기울기의 k배로 수렴하는지 assert.
- [ ] **Step 2: 구현** — `buildScenarioCurve` 를 k·plan_rate 기반으로. plan_rate 는 s_curve planned 의 인접 차분(today 부근). k 는 `scenariosSite.catch_up_multiplier_k ?? 2.0`. 곡선은 %공간이므로 **%↔물량 환산**: plan_rate_pct = planned[today+1] − planned[today] (일별 % 증가분), boosted_pct = plan_rate_pct × k. actual 라인 = lastActual + Σ boosted_pct, plan 도달(actual ≥ planned[i])하면 catch_up.
- [ ] **Step 3: 통과 확인** — FE 테스트 + `cd web && npm run build` (타입 통과).
- [ ] **Step 4: Commit**

**게이트 C:** catch-up 곡선이 plan 기울기의 k배로 점진 수렴(직선 아님), catch_up 시점 = deficit÷(boosted−plan), site recovery_days = Σby_wp.

**✅ Group C 완료 — catch-up 점진 수렴 (2026-05-30, 사용자 "점진 수렴 해야돼"):**
- FE `buildScenarioCurve`(web/lib/diagnosis.ts:55) 직선 chord → **plan 곡선 증분 × boostK 누적**(점진). `boostK = 1 + gap0/planSpan` → LLM recovery_days 시점에 plan 에 **정확히 도달**(자동 산출이라 고정 k 1.5/2/3x 선택 불필요). planSpan≤0 평탄 시 직선 fallback. 디자인 불가침 무관(lib 곡선 로직, markup/style 무변경).
- 수치검증: S-curve plan 에서 progressive `[40,54.6,74.1,86.3,92.3,96]` ≠ linear `[40,51.2,62.4,73.6,84.8,96]`, 둘 다 catch-up 96 도달. `tsc --noEmit` 0 errors.
- Task 5.1(BE `_build_scenarios` gap기반 recovery_days override)는 **의도적 미적용** — LLM scenarios recovery_days 보존(사용자 LLM-driven 우선; 룰 공식으로 LLM 값 덮어쓰지 않음). 곡선은 그 LLM recovery_days 를 target 으로 점진 수렴.
- 미수행(저우선 follow-up): buildScenarioCurve 는 module-internal(미export)이라 vitest 단위테스트 대신 수치검증으로 대체. export 후 vitest 추가는 추후.

---

## 6. Task Group D (#166) — 주입점·seed 입력전용

> 실 prod 그래프로 적재되도록 plumbing. 절대제약(0.1) 준수.

### Task 6.1: backfill `build_demo_graph` 전환 + run_id 일원화

**Files:**
- Modify: `scripts/backfill_optimizer_advice_llm.py:48`(import), `:216-223`(run_id/INSERT), `:225`(graph)

- [ ] **Step 1**: import 교체 — `from pipeline.graph import build_demo_graph`(atomizer 없음, Chroma/임베딩 회피).
- [ ] **Step 2**: `_run_one_date`(:216) run_id 일원화:
```python
    run_id = _dummy_seed_run_id(d)  # seed _date_run_id 와 동일 — _WP_SUMMARY_SQL join 정합
    await pg._pool.execute(
        "INSERT INTO pipeline_runs (run_id, site_id, report_date, status) "
        "VALUES ($1, $2, $3, 'running') ON CONFLICT (run_id) DO UPDATE SET status='running'",
        run_id, site_id, d,
    )
```
- [ ] **Step 3**: `:225` `build_atomized_demo_graph(cfg)` → `build_demo_graph(cfg)`.
- [ ] **Step 4: 검증** — Task 7 에서 9/24 1일 실행 후 `forecasts.run_id == _dummy_seed_run_id(9/24)` 확인. (Chroma upsert 로그 0 = atomizer 미진입 증명.)
- [ ] **Step 5: Commit**

### Task 6.2: reporter hours_saved — pipeline_runs.atomized_count 에서

**Files:**
- Modify: `pipeline/graph.py:456-460` (`reporter_node`)

`build_demo_graph` 는 atomizer 없음 → `state["atomized_ids"]=[]` → hours_saved 0. seed 가 `pipeline_runs.atomized_count`(seed_day:747) 박음.
- [ ] **Step 1**: reporter_node 에서 atomized_count 를 state 우선, 없으면 pipeline_runs 에서 fetch:
```python
            atomized_count = len(state.get("atomized_ids", []) or [])
            if atomized_count == 0:
                async with pg._pool.acquire() as _con2:
                    _r = await _con2.fetchrow("SELECT atomized_count FROM pipeline_runs WHERE run_id=$1", run_id)
                atomized_count = (_r["atomized_count"] or 0) if _r else 0
            await update_site_hours_saved_cum(pg, site_id=site_id, atomized_count=atomized_count)
```
- [ ] **Step 2: 검증** — Task 7 후 `sites.hours_saved_cum > 0` 확인.
- [ ] **Step 3: Commit**

### Task 6.3: seed 입력전용 리팩터 (7~9 제거 + dead code)

**Files:**
- Modify: `scripts/seed_dummy_year.py:771-` (seed_day 7~9), 삭제: `_build_forecast_row`(:422), `_build_optimizer_advice`(:496), `_classify_assessment`(:412), `_build_daily_report`(있으면)

- [ ] **Step 1**: `seed_day` 의 7(forecasts:771-779)·8(optimizer_advice:781-)·9(daily_reports/view jsonb) 블록 제거. 1~6(pipeline_runs·parser·mapper·mapped_history) 유지. return counts 에서 forecasts/advice 카운트 제거.
- [ ] **Step 2**: dead code 된 `_build_forecast_row`·`_build_optimizer_advice`·`_classify_assessment` + 그 전용 import 제거 (autoflake 가 import 지우니 사용처 없는지 grep 먼저).
- [ ] **Step 3: 검증** — `cd pipeline && uv run pytest tests/test_seed_distribution.py tests/test_seed_trade_filter.py -v` (회귀). seed 1일 dry: 9/24 seed 후 `SELECT count(*) FROM forecasts WHERE run_id=_date_run_id(9/24)` = 0(실 그래프 전).
- [ ] **Step 4: Commit**

### Task 6.4: mapped_history 소비처 확인 후 결정 (과설계 금지)

**Files:** 조사 후 필요 시 `pipeline/db.py:462` 또는 `scripts/seed_dummy_year.py:757-769`

- [ ] **Step 1: 소비처 live 확인** — `_WP_SUMMARY_SQL`(api.py:419) `/api/runs/{id}/wp_summary` 와 `_TASKS_ITEMS_SQL`(:920) 가 **현 리포트 화면(reports?date=)에서 호출되는지** web/ grep + Playwright network 로 확인.
- [ ] **Step 2: 분기**:
  - 호출 안 됨(생산성 화면은 view_builder jsonb 만) → **변경 없음**, 본 task 주석으로 "mapped_history collapse 는 live 무영향" 기록.
  - 호출됨 → seed 의 mh_rows(seed_dummy_year:758) 를 (wa,l6,company) **pre-SUM**(혼재 WP 는 대표 unit qty 만, 또는 unit별 row 를 별도 키로) 로 보정. ON CONFLICT 키 변경(=DB migration=B_Track)은 회피.
- [ ] **Step 3: Commit (변경 시)**

**게이트 D:** seed=입력만(forecasts 0), backfill 이 build_demo_graph + seed run_id 로 forecasts/views 생성, hours_saved>0.

**✅ Group D 완료 — 실 e2e 검증 (2026-05-29):**
- 6.1: import 블로커(`from pipeline.graph import build_demo_graph` 누락 → NameError) 수정. run_id 일원화·ON CONFLICT·call 모두 적용. `_dummy_seed_run_id(9/24)=f57e8ae0-3f76-00c2-3047-c2abc8da3dd8` = seed `_date_run_id` 동일(검증 True).
- 6.2: `graph.py:456-469` hours_saved atomized_count fallback 이미 적용. 실행 후 `sites.hours_saved_cum=62316.58>0`.
- 6.3: seed 입력전용(steps 7~9 제거·helper 삭제) 적용 + `_diag_tag` 죽은코드 제거. `pytest tests/test_seed_distribution.py` 9 passed.
- 6.4: **no-op 확정** — BFF `web/app/api/mock/report/[date]/route.ts:22,48` 가 `wp_summary` 를 `daily_reports.wp_summary_jsonb`(view_builder, mapper 직독)에서 읽음 → `_WP_SUMMARY_SQL`(mapped_history) 미사용 → collapse live 무영향. `_hydrate_mapped` 는 `JOIN pipeline_runs USING(run_id)` 라 orphan 자동 제외.
- **9/24 harness 스모크**: `backfill --start-date 2025-09-24 --end-date 2025-09-24 --trades 건축,토목 --clean` → mapped 60 → `optimizer_advice rows=11 (LLM-driven=11, cold_start=0)`, forecast_n=11, 잔재 0, jsonb 4종 생성. **유일 FAIL = delay_days {neg:0,pos:0,zero:11} 전부 0 → Group A(#163) 타깃.**

---

## 7. Task Group E (#167) — 9/24 PoC 실그래프 → UI 정합

### Task 7.1: 9/24 1일 실 적재 체인 + 결정론 검증 스크립트

**Files:**
- Create: `scripts/verify_downstream_coherence.py` (DB write 0 — 컴포넌트 정합 검증)

- [ ] **Step 1: 체인 실행** (clean 재현):
```bash
cd pipeline && set -a; source ../.env.local; set +a
# (a) seed 입력 (9/24 1일) — 입력전용. ★seed 플래그 주의: 날짜는 --start/--end(not --start-date), --trades 는 공백구분(seed_dummy_year.py:934-935·956 nargs="+", 기본 ["건축","토목"])
PYTHONPATH=$PWD/.. uv run python ../scripts/seed_dummy_year.py --start 2025-09-24 --end 2025-09-24 --trades 건축 토목
# (b) 실 그래프 (build_demo_graph, seed run_id 재사용, --clean=artifacts만)
PYTHONPATH=$PWD/.. CPIA_REPORTER_SKIP=1 uv run python ../scripts/backfill_optimizer_advice_llm.py --start-date 2025-09-24 --end-date 2025-09-24 --site m15x-ph3-ibl --clean
```
Expected: forecast_n>0, advice LLM-driven, Chroma upsert 로그 없음(atomizer 미진입).

- [ ] **Step 2: 정합 검증 스크립트** — `verify_downstream_coherence.py` 로 9/24 DB 읽어:
  - forecasts.delay_days(bottleneck) vs view_builder kpi.delay_days(MEDIAN) 방향 일치
  - 생산성 카드 productivity 가 실 today_qty 기반(시뮬 아님 — 동일 입력 2회 실행 시 동일값 = 결정성)
  - 혼재 WP units_detail 단위별 분리
  - s_curve actual ≈ #1 게이트 90.1% (±2%pt)
  - site recovery_days == Σ by_wp
  - **★ LLM-provenance (사용자 #1 우려, §0.3⑨)**: ① backfill stdout `optimizer_advice rows=N (LLM-driven=X, cold_start=Y)` 의 X≥1(전 WP LLM) ② `scenarios_jsonb.by_wp[*]` 에 `rationale` 키 ≥1 존재(룰베이스 percentile fallback 아님) ③ 잔재 SQL `diagnosis LIKE '오늘 생산성은 정상 범위로 판단됨%'` = 0 ④ 동일 입력 2회 실행 시 diagnosis 텍스트 varies(LLM)·생산성 숫자 동일(룰) ⑤ Chroma upsert 로그 0(atomizer 미진입). **실 출력 인용.**
  Run: `PYTHONPATH=$PWD/.. uv run python ../scripts/verify_downstream_coherence.py --date 2025-09-24`
  **실 명령+원본출력+결론 형식 보고.**

- [ ] **Step 3: Commit**

### Task 7.2: UI 정합 (Playwright) + 사용자 리뷰

- [ ] **Step 1: views 재산출** — `PYTHONPATH=$PWD/.. uv run python ../scripts/backfill_daily_report_views_v2.py --date 2025-09-24 --site m15x-ph3-ibl --with-summary`
- [ ] **Step 2: 화면 검증** — `cd web && npm run dev2`(5537) → `http://127.0.0.1:5537/reports?date=2025-09-24` Playwright 로: 생산성 카드/분포도/목록/KPI/공기단축 곡선의 숫자가 서로 일관(컴포넌트별 불일치 0). 스크린샷.
- [ ] **Step 3: k 확정** — 사용자에게 catch-up 곡선(k=2.0 기본) 보여주고 1.5/2/3x 중 최종 확정 → `CPIA_CATCHUP_K` 또는 기본값 반영.
- [ ] **Step 4: 사용자 리뷰 게이트** — 9/24 화면 OK 받기.

**게이트 E (전체 PoC):** 9/24 reports 화면의 생산성·딜레이·공기단축이 단위별 일관 + 결정론(2회 동일) + 사용자 승인.

**🔶 Group E 진행 — 9/24 재적재(A+B+D) 실측 (2026-05-30):**
- ✅ LLM-driven: advice 11/11 LLM·cold_start 0·잔재 0, scenarios by_wp 10/10 `rationale` 有(룰 fallback 아님), site_summary_text LLM 有.
- ✅ B 산출: wp_name = l6 라벨("도장공사·FAB"), productivity 실 qty 다양(37.8/49/58/63/78/87/96/97/113/130/150 — 시뮬 균일 아님), units_detail 有(외장판넬·FAB 2 units).
- 🔴 **헤드라인 anomaly (사용자 "이상점 캐치" 직격)**: **KPI/site_summary delay = 72일** (s_curve actual 71.1% vs planned 89.1%) **인데 per-WP forecasts delay_days = 전부 0**. 근본원인 = **이중 plan-to-date 기준**: s_curve planned 는 `plan_wv` **가중(S-curve)** → 89.1%, forecaster delay 는 **linear**(`plan_total/total_days`) → 각 WP actual_cum 이 linear 계획-to-date 초과 → deficit 0. 두 기준이 "뒤처짐" 판단을 반대로 냄. (이전 "9/24 WP 지연 안 보임" 도 같은 뿌리.)
  - **결정 필요(사용자/조형준)**: (A) forecaster delay 기준을 s_curve 와 동일한 `plan_wv` 가중 plan-to-date 로 통일 → WP 지연 가시화 + site==ΣWP 정합(권장, 단 잠긴 결정 §3 linear 변경). (B) s_curve planned 를 linear 로 → site 도 ~0(데모상 "72일 지연" 서사 소멸). (C) 현행 유지 + 라벨로 두 개념 구분 명시.
  - ⚠️ **F/G(전기간 532일 재적재) 전에 이 baseline 을 확정해야 함** — 잘못된 baseline 으로 18h 재적재 시 낭비.
- ⏸ Group C(#165 catch-up k·곡선)·9/24 delay 가시화 = 본 anomaly 결정과 함께 사용자 UI 검토에서 확정.

**✅ 결정 A 구현 완료 (2026-05-30, 사용자 "A로 통일"):**
- `fetch_pg_planned_qty_to_date(pg, company, l6_main, today, unit)` 신규(aggregate.py) — activity_master 에서 `SUM(plan_total_qty × LEAST(1, (today-plan_start+1)/(plan_finish-plan_start+1)))` = **s_curve planned 와 동일 공식**의 activity 단위 가중 계획-to-date. compute_delay 에 `planned_qty_to_date_main` 옵션 추가(미전달 시 linear fallback=기존 테스트 보존), `_forecast_one_group` ②-b 루프+⑤ 에서 주입. 단위테스트 `test_delay_uses_weighted_planned_to_date_when_provided` 포함 **28 passed**.
- **9/24 재적재 결과**: delay {neg:0, **pos:1**, zero:10} — 포장공사 장평건설 m2 = **25일(주의)**, 나머지 0(가중 계획 충족/앞섬 = 정상). B5 6/6 PASS. advice 11/11 LLM, 잔재 0.
- **🔴 잔여 결정(사용자/조형준)**: site KPI delay=72 vs 활성 WP(1개 25일) **numeric 차이 = scope/coverage** — `activity_master` 173 (wa,l6,unit) 그룹 중 **9/24 mapper 실적 있는 건 10개뿐**(163개=94%가 당일 비활성). s_curve=전체 프로젝트 누적, WP 카드=당일 활성 subset. baseline 은 이제 통일됨(둘 다 가중). 선택: ① 현행 유지(site=전체, 카드=당일활성, 방법론 일관) ② s_curve/KPI 도 활성 WP 만 집계(site≈ΣWP) ③ 비활성 지연 WP 도 카드 노출. → **9/24 UI 보고 결정.**
- ⚠️ **재발 gotcha (★ F/G 전 주의)**: PostToolUse 포매터(autoflake류)가 **호출부보다 먼저 추가한 import 를 "unused" 로 제거** → 함수본문 NameError(pytest/import-time 미검출, build_demo_graph 블로커와 동일 class) → asyncpg cleanup 이 socket-write 대기로 **15분 행**. **교훈: import 는 호출부 추가 후 또는 동시에. import 변경 시 실 그래프 1회 e2e 로 검증(pytest 만으론 부족).**

**✅ scope 결정 = 건축·토목 한정 (2026-05-30, 사용자 결정: 전체 흡수 시 설비/전기 phantom):**
- `_build_s_curve`(view_builder.py:897~)의 activity_master 4쿼리(site_total_weight·plan_end·planned CTE+MIN(plan_start) 서브쿼리·am_agg)에 `l5_disc IN ('건축','토목')`, mapper day_qty 에 `ma.trade IN ('건축','토목')` 추가. (`activity_master.l5_disc` = 공종: 건축/토목/설비/전기/소방/제어/UT. mapper 는 `trade`.)
- **결정론 숫자검증(LLM 없이, 사용자 요구)**: 건축·토목 9/24 **planned 98.4% / actual 98.2%**(gap 0.2%p=on-track). 건축·토목 weight = 전체 52.6% → 나머지 47.4%(설비 등, 실적 0)가 **"72일" phantom 의 원인**. 재빌드 후 **KPI delay 72→5**. activity_master 건축·토목 그룹 47 / 전체 173.
- ⇒ **데모 진실 narrative: 건축·토목 거의 정시, 포장공사 장평건설 25일이 유일 laggard.** site(5)≈WP 정합 회복. 72일 폐기.
- 재빌드 명령(결정론): `backfill_daily_report_views_v2.py --date <D> --site m15x-ph3-ibl` (**--with-summary 없이 = LLM 미호출**). ★ F/G 월배치에서 site_summary(LLM narrative)는 별도 `--with-summary` 필요.

---

## 8. Task Group F (#168) — orphan 정리 + 전 기간 월별 재적재

> 게이트 E(9/24 PoC 사용자 승인) 통과 후 시작. **선행 필수**: Task 6.1(build_demo_graph 전환+run_id 재사용)·6.2(hours_saved)·6.3(seed 입력전용) 완료 — 안 되면 전 기간 wp_summary 가 빈다(run_id 갈라짐, audit 블로커).

### Task F.1: orphan mapper/parser DELETE (1회, 트랜잭션)

**Files:** Create `scripts/sql/delete_orphan_mapper.sql` (또는 psql 직접)

근본원인(audit 확정): `mapper_activities`/`parser_activities` 는 `pipeline_runs` 로의 **FK 없음**(migration `2026-05-18_parser_mapper_outputs.sql` — `run_id uuid NOT NULL` 선언만, REFERENCES/CASCADE 없음). 과거 cleanup 이 pipeline_runs 만 DELETE → orphan ~148k(93.6%) 잔존. **`backfill_optimizer_advice_llm.py:70-74` 의 'mapper 는 CASCADE FK' 주석은 오기재** — 믿지 말 것.

- [ ] **Step 1: 사전 COUNT** (기대 ~148k):
```sql
SELECT 'mapper_orphans' AS k, COUNT(*) FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id)
UNION ALL
SELECT 'parser_orphans', COUNT(*) FROM parser_activities pa
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = pa.run_id);
```
- [ ] **Step 2: 트랜잭션 삭제 + 검증** (부모 run 없는 행만 = 정의상 이미 고아라 유효 리포트 미참조):
```sql
BEGIN;
DELETE FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id);
DELETE FROM parser_activities pa
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = pa.run_id);
SELECT COUNT(*) AS remaining FROM mapper_activities ma
  WHERE NOT EXISTS (SELECT 1 FROM pipeline_runs pr WHERE pr.run_id = ma.run_id);  -- 0 확인 후에만
COMMIT;
```
- 제약 정합: NOT EXISTS = report_date 가 아니라 **부모 존재 여부** 기준 → 6월 이전 '유효한'(부모 run 있는) 데이터 무손상. '6월 이전 DELETE 금지' 의 명시 예외(설계 §0·메모리). **실 COUNT+검증=0 인용 후 COMMIT.**
- [ ] **Step 3: Commit (사용자 승인 시)** — SQL 파일만.

### Task F.2: Chroma 윈도우 재적재 (stale RAG 방지)

seed v2 의 work_content(저하/회복 narrative)가 바뀜 → 유사사례 RAG ground 갱신 필요. build_demo_graph 는 atomizer 없어 backfill 이 Chroma 안 건드림 → **Chroma 적재는 seed `--chroma-on` 책임**.

- [ ] **Step 1**: 전 기간 Chroma daily_activities 의 해당 site/date doc 선삭제 — `clean_window.py`(Chroma doc 삭제 포함:73). ⚠️ `clean_window.py` 는 mapper/parser 도 DELETE(:26-34)하고 DSN/SITE_ID 가 **파일 하드코딩**(43.200.85.209/m15x-ph3-ibl) — 입력 보존 흐름과 충돌하므로 **F.3 seed 재실행 직전에만** 또는 Chroma-only 경로 사용.
- [ ] **Step 2**: F.3 월별 seed 시 `--chroma-on` 으로 재적재. doc_id=sha256(date|company|l6|work_content) 에 unit 없음 → per-unit dedup(결정 #10, retrieve l6 레벨 무해) 확인.
- [ ] **Step 3: 검증** — 9/24 retrieve 가 새 work_content 기반 저하/회복 사례 반환(0건 아님) 확인.

### Task F.3: 월별 18 배치 재적재 루프

2024-04-11~2025-09-24 = **18 월배치 / 532일**. 배치당 seed(입력)→backfill(실그래프)→views→verify. 일자당 ~2-3분 × 532 ≈ 18~27h → 월별 분할·백그라운드·멱등 재실행(seed `_date_run_id` 결정성 + backfill `--clean`).

- [ ] **Step 0: 사전 점검** — `verify_backfill_passing.py` 가 `pipeline_runs.is_mock` WHERE 사용(:54 등). 컬럼은 migration `2026-05-20_add_is_mock.sql` 로 추가됨 + seed 가 `is_mock=FALSE` INSERT(seed_dummy_year.py:751) → 실 AWS DB 엔 존재. `\d pipeline_runs | grep is_mock` 5초 확인만(없으면 migration 적용). ★멱등성: `cleanup_dummy`(seed_dummy_year.py:624)는 pipeline_runs 만 DELETE(mapper FK 없음) → 같은 run_id `ON CONFLICT (run_id,idx)` upsert. activity_master row set 안정이라 idx 일치하나, 활동 수 줄면 stale high-idx mapper 잔존 가능(F.1 orphan 아님 — 부모 run 존재). 데모 범위 OK, 이상조사 시 인지.
- [ ] **Step 1: 배치 명령** (월 경계로 `M_START`/`M_END` 치환. ★seed=`--start/--end`, backfill=`--start-date/--end-date`):
```bash
cd pipeline && set -a; source ../.env.local; set +a
M_START=2025-09-01; M_END=2025-09-24
# ★ 플래그 footgun: seed = 날짜 --start/--end + trades 공백구분(nargs="+"); backfill = 날짜 --start-date/--end-date + trades 콤마(.split(","))
PYTHONPATH=$PWD/.. uv run python ../scripts/seed_dummy_year.py --start $M_START --end $M_END --trades 건축 토목 --chroma-on
PYTHONPATH=$PWD/.. uv run python ../scripts/backfill_optimizer_advice_llm.py --start-date $M_START --end-date $M_END --site m15x-ph3-ibl --trades 건축,토목 --clean
PYTHONPATH=$PWD/.. uv run python ../scripts/backfill_daily_report_views_v2.py --start-date $M_START --end-date $M_END --site m15x-ph3-ibl --with-summary
PYTHONPATH=$PWD/.. uv run python ../scripts/verify_backfill_passing.py --start-date $M_START --end-date $M_END --site m15x-ph3-ibl
```
- 18 배치 날짜범위: `2024-04-11~04-30, 05-01~05-31, 06-01~06-30, 07-01~07-31, 08-01~08-31, 09-01~09-30, 10-01~10-31, 11-01~11-30, 12-01~12-31, 2025-01-01~01-31, 02-01~02-28, 03-01~03-31, 04-01~04-30, 05-01~05-31, 06-01~06-30, 07-01~07-31, 08-01~08-31, 09-01~09-24`.
- [ ] **Step 2: 배치별 게이트** — `verify_backfill_passing` exit 0(6기준 PASS) + 각 월 **Group G UI 검증** 통과해야 다음 월. ⚠️ 초기 sparse 월(2024-04~05)은 활동 적어 `backfill_daily_report_views_v2` skip ratio>30% RuntimeError(:205) 위험 — 월별 임계/예외 처리.
- [ ] **Step 3**: 18배치 + Group G 전부 통과 = 전체 재적재 완료. **실 명령+요약출력+결론 보고.**

**게이트 F:** orphan 0, 전 기간 forecasts/views = seed run_id, wp_summary 안 빔, 18개월 verify PASS.

## 9. Task Group G (#168 cont.) — 월별 UI 직접 검토·보완 루프 (각 F.3 배치 후 반복)

> 사용자 핵심 요구: **"월별 적재 끝날 때마다 직접 UI 들어가서 확인·검토, 이상하면 보완."** 각 월(F.3 배치) 직후 반복. 총 18회.

### Task G.1: 월별 UI 정합 검토 (각 월 반복)

- [ ] **Step 1: 화면 열기** — `cd web && npm run dev2`(5537). 월별 **2 anchor**: ① 그 달 **마지막 적재일**(누적 최대, 이상 다발), ② **중순(~15일) 대표일**(s_curve 중간 todayIdx). URL `http://127.0.0.1:5537/reports?date=YYYY-MM-DD` (★`?date=` 명시 — 미지정 시 latest fallback). 좌측 ReportDailyList 에 status flip/불연속 보이면 그 날짜 1개 추가.
- [ ] **Step 2: 15항목 정합 체크리스트** (Playwright 또는 육안):
  1. KPI 생산성 = trend 카드 큰 숫자 = 90일 라인 끝점 (kpi vs s_curve)
  2. WP 목록 productivity = 분포도 같은 wp_id X좌표 (wp_summary vs quadrant)
  3. 카드 delay = KPI delay_days = '현황 D+N' 마커
  4. **site recovery_days == Σ(WP recovery_days)** (SSOT — 큰 갭 = forecaster Σ/distinct 버그=−37 류)
  5. 우측 WP detail '공기 단축 -d일' = 목록 = AI권고 '−d일 만회' (3곳 동일)
  6. s_curve 실적선 끝 = 선택 report_date, 단조증가, 끝값 = trend 숫자
  7. catch-up = 점진 slope(직선/수직 점프 아님), plan 도달 후 stop
  8. 완공일 순서: 계획 ≤ AI시나리오, 현황(예측) = 계획+delay_days
  9. WP명 = l6 인간 라벨(l7_5/빈 wa/path 아님)
  10. 혼재 unit WP = 단위별 detail(ton/인 등) 노출
  11. 공종 bar ↔ WP 목록 trade 일치(필터 커플링)
  12. 4사분면 칩 필터 = 분포도+목록 동시 필터, 카운트 일치
  13. 점 색(위치 4색) vs 목록 status(3-tier) 의도적 차이 확인
  14. 빈칸/NaN%/Loading/EMPTY_OPTIMIZER placeholder 0
  15. AI 시나리오 traceability 문구 recovery_days = 헤드라인, case_count>0
  16. **★ LLM-provenance (BE, 사용자 #1 우려)**: 그 달 anchor 날짜에 ① 잔재 SQL `diagnosis LIKE '오늘 생산성은 정상 범위로 판단됨%'`=0 ② `scenarios_jsonb.by_wp[*].rationale` 존재(전부 NULL 이면 룰베이스 percentile fallback = FLAG) ③ optimizer_advice 전 WP 가 LLM(`LLM-driven=advice_n`, cold_start 0 또는 정당한 신규작업만). 정상 WP 카드도 그 날짜 실제 조건 반영(캔드 문구 아님).
  17. **★ 내러티브 provenance**: ForecastChart 현황요약/AI권고가 LLM `site_summary_text` 기반(daily_reports.site_summary_text NOT NULL)인지 — NULL 이면 FE 룰베이스 `situationNarrative()`(ForecastChart.tsx:478-502) fallback 으로 조용히 대체됨(마커 없음). "…기반 LLM 산출" 캡션(:427-430)은 무조건 표시되므로 캡션 신뢰 금지, 16-② rationale 로 교차검증.
- [ ] **Step 3: 이상 발견 시 anomaly 프로세스**:
  - **RECORD**: `/reports?date=` 스크린샷(URL 보이게) + 1줄(date/COMPONENT/EXPECTED vs ACTUAL 실수치). `gbrain put` `[[projects/CPIA]]` 태그로 영속(compaction 대비). 그 달 이상 다 기록 후 수정 착수.
  - **ISOLATE**: DevTools Network `GET /api/mock/report/<date>` raw JSON(kpi/s_curve/wp_summary/quadrant/scenarios/optimizer_view jsonb)과 화면값 대조 → BE/FE 결정론 분리.
  - **TRIAGE**: (a) payload 가 이미 틀림 → BE view_builder(jsonb 조립) (b) delay/recovery site≠Σwp·recovery 0/∞ → forecaster 집계(−37 류, aggregate.py) (c) payload 맞는데 화면 틀림 → FE(diagnosis.ts todayIdx/buildScenarioCurve, page.tsx 필터, NaN 가드). **(d) payload 잘 형성됐는데 LLM 아니라 룰베이스/템플릿(잔재) — 16-②(rationale NULL)·17(site_summary_text NULL)·잔재 SQL 로 탐지** → 근본원인 = 그 날짜 실 그래프 미실행(NameError/retry-drop agent.py:237-246) 또는 scenarios deterministic fallback(`_wp_block_deterministic`). FIX = 그 날짜 **실 그래프 재실행**(FE fallback·fixture·CPIA_DEMO_FALLBACK 우회 금지).
  - **FIX**: 해당 layer 만 surgical. BE=pipeline/(A_Track), FE=web/(B_Track). **payload 가 틀리면 payload 를 고침 — FE fallback 으로 가리지 말 것.**
  - **RE-RUN**: 실 그래프로만 그 월 재실행(`CPIA_DEMO_FALLBACK` 켜서 fixture 로 우회 금지 — prod-graph-only 위반). FE-only 면 브라우저 hard reload.
  - **RE-VERIFY**: 같은 anchor URL 재열람 + 영향 커플링 회귀 + after 스크린샷. brain 페이지 open→resolved(수정 commit·layer) 갱신.
- [ ] **Step 4: 사용자 게이트** — 각 월 화면 OK 받고 다음 월. (18회 반복.)

**게이트 G (전체 완료):** 18개월 UI 전부 정합 + 이상 0(또는 보완 완료) + 매월 사용자 승인 → **전체 재적재 + 검증 완료**.

## 10. 실행 순서 요약 (의존성)

```
[9/24 PoC 로직 검증]                                    [전 기간 운영]
A(#163 forecaster delay) ─┐
B(#164 view_builder 실qty)─┤→ E(#167 PoC 9/24)→[OK]→ F.1(orphan)→F.2(Chroma)→ [F.3 월배치 → G.1 UI검토 → 사용자OK] ×18 → 완료
C(#165 catch-up k)        ─┤
D(#166 seed입력+주입점)   ─┘   harness(D)=E·F 필수
```
권장 순서: **D.6.1~6.3(harness) → A → B → C → E(9/24 PoC+사용자 OK) → F.1 → F.2 → [F.3 월배치 → G.1 UI검토·보완 → 사용자 OK] ×18 → 완료**. A/B/C 순수함수는 D 없이 단위테스트 가능, 통합검증(E)·전기간(F/G)은 D 필요.

## 11. 환경/재개
- 검증: `cd pipeline && set -a; source ../.env.local; set +a; PYTHONPATH=$PWD/.. uv run python ../scripts/verify_seed_numbers.py`
- 테스트: `cd pipeline && uv run pytest tests/ -q`
- UI: `cd web && npm run dev2` (5537) → `http://127.0.0.1:5537/reports?date=2025-09-24`
- psql: `PGPASSWORD='K7mP2xQ9nR4v' /opt/homebrew/opt/libpq/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia`
