# CPIA 데이터 재적재 v2 — 단위별 정규분포 시딩 + 숫자검증 게이트 (설계/결정 기록)

> 작성: 2026-05-29 (3차 세션) | 성격: decision doc (formal writing-plans 스펙 아님 — #1 게이트 통과 후 §3~4만 플랜화 검토)
> 선행: [2026-05-29-cpia-data-coherence-catchup-design.md](./2026-05-29-cpia-data-coherence-catchup-design.md) §7 (l6 컨셉 + 전체 재적재) 를 구체화한 문서.
> 절대 제약: 데이터 적재는 실 prod 그래프(forecaster→optimizer→reporter) 출력만. **mapper_activities(atomizer 앞단 입력) 주입만 스크립트 허용.** forecaster/optimizer/reporter 출력을 fixture 로 쓰지 않는다 — 위 로직은 전부 prod 에 녹인다(별도 test 스크립트로 적재 X). 그래프 시작지점 조정만 허용. 공종 = **건축·토목 한정**. 6월 이전 DELETE 금지(전체 재적재 시 orphan 정리는 별개). commit=요청 시만. main 머지=조형준 프로.

---

## 0. 전수조사 결과 (실코드/실데이터 근거 — 추측 아님)

1. **주입점은 이미 prod 에 있음.** `backfill_optimizer_advice_llm` 은 `_hydrate_mapped`(mapper_activities → Activity) 후 `build_atomized_demo_graph`(`graph.py:544` START→**atomizer**→forecaster→hil_2→optimizer→reporter)를 돌린다. atomizer 노드가 매 재실행마다 Azure 임베딩 + Chroma upsert 를 반복. → "forecaster 부터"는 `build_demo_graph`(`graph.py:501` START→forecaster, atomizer 없음) 로 전환하면 됨.
2. **"l6 로 묶기"는 이미 grain.** 생산성·quadrant·wp 전부 `(wa, l6_main, company)` 집계(`_evm_by_wa_l6_company:238`, `_build_quadrant:732`). 실데이터(건축·토목): **l7_5 활동 689 → (wa,l6,company) WP 54**. 남웅 CUB 철근콘크리트공사 1개에 거푸집·철근조립·콘크리트타설·무근 196행이 이미 롤업. 남은 건 카드 라벨이 l7_5(`activity_label = q.get("l7_5_activity")…` view_builder:569)로 뜨는 것 → l6 라벨로.
3. **단위 혼재 — 핵심.** 54 WP 중 **8개 단위 혼재**, flagship 남웅 철콘이 **4단위(ea·m²·m³·ton)**. 거푸집(m²)+철근(ton)+콘크리트(m³) 합산 불가. 단, 혼재 그룹도 한 단위가 mh 의 ~95%(남웅 철콘 m³ 95.6/96.2%, 토공 m³ 98.9%) — 단 철골(ea/ton 50:50)·C/R조성(4분할)은 진짜 멀티스트림. → **계산 grain = (company, wa, l6, unit) 단위 스트림, 표시 grain = l6 카드.**
4. **seed SSOT 버그 근원.** `seed_dummy_year._build_mapper_row`: `today_cum_qty = plan_total × cum_frac`(**계획곡선 추종**)인데 `today_qty = plan_total/total_days × f3_daily_ratio × prod_factor × noise`(감산) → **누적 ≠ Σ일별**. 분포도 F3(ramp-plateau-late rise, `synthetic/distributions.py`)라 정규분포 아님. forecaster `compute_delay`(aggregate.py)는 이미 point-in-time deficit÷plan_per_day, `_forecast_one_group`(agent.py:88-94)는 이미 main_unit=`max(today_qty_by_unit)` 단일선정(단 **그날 qty 최대라 매일 단위가 바뀜** = 딜레이 들쭉 원인).
5. **mapped_history 소비자.** `api.py:438`(WPSummaryRow) / `:928`(itemsByDate) 가 읽음 → atomizer 건너뛰면 INSERT 빠짐. seed 가 작성(`seed_day:718`)하나 ON CONFLICT `(run_id,wa,l6,company)` 마지막값(collapse). per-unit 이면 키에 unit 추가 or pre-SUM 필요.

---

## 1. 시딩 알고리즘 (입력층 — `seed_dummy_year._build_mapper_row` 교체)

계산 grain = **(company, wa, l6_main, unit) 단위 스트림**. activity_master l7_5 행은 단일 unit → 행 생성은 그대로(689행/풀데이), 분배만 교체.

- **plan 일별 = 정규분포(bell):** 활동 plan_total 을 plan_start~plan_finish 에 종형 배분. 중심=기간 중점, σ=기간/4. 이산화 후 재정규화하여 **Σ(plan 일별)=plan_total 정확 보존**. (현 F3 폐기. 예: 11m³/10일 → ~1,1,2,3,2,2 형태)
- **actual 일별 = plan 일별 × prod_factor(조건):** prod_factor 는 `_pick_diagnosis`(정상 60% · 저하 40%) + `factor_for` 재사용 → 저하(≈0.5)/정상(≈0.9)/회복(≈1.1) 변동, **누적 평균 ~0.85 엔벨로프**. 저하→회복 텍스처 유지(유사사례 RAG ground).
- **활동별 총합 보존:** 활동 plan_finish 직전 구간을 보정해 **Σ(actual 일별)=plan_total**. → 완료 활동 100%, 진행중만 ~15% 뒤처짐 → site 갭이 "진행중 작업" 에서만 현실적 발생(현 과대갭 해소).
- **today_cum_qty = Σ(actual 일별)** (진짜 누적). `plan_total × cum_frac` 버그 제거 → 누적=Σ일별 불변식.
- **mh:** actual mh = plan_mh × (actual 진척 / plan 진척) 정합 (생산성 mh가중 % 분자/분모 일관).

검증 가능 불변식: 활동별 Σ(today_qty over dates) == today_cum_qty(마지막) == plan_total(완료 시).

## 2. 숫자검증 게이트 (적재 전, 결정론적 · LLM 0) — 사용자 1순위

`scripts/verify_seed_numbers.py` (신규, 읽기 전용 집계):
- 2024-04-11~2025-09-24 시딩(입력층) 후 **월별** 집계 + plan 대조:
  - (a) 단위별 Σactual qty vs Σplan qty
  - (b) site 공정율 (mh가중: weight = plan_wv × plan_mh_rev2) actual vs plan
  - (c) Σmh actual vs plan
- 합격 기준(초안): 완료활동 Σactual = plan ±1% · 진행중 actual/plan-to-date = 0.80~0.90 · site 공정율 갭 한 자리~15%pt(과대갭 아님) · 단위별 누적 == Σ일별 정확 일치.
- 실 명령 + 원본출력 + 결론 형식으로 보고. **이 게이트 통과 후에만** 다운스트림(§3~4)·prod 적재 진행.

## 3. 다운스트림 설계 (게이트 후 · writing-plans 로 디테일) — 실 타겟·바꿀 것·엣지

> ⚠️ **live 경로 정정 (4-agent 전수분석)**: 생산성 산출 live 함수는 **`view_builder._build_productivity_views_v2`(:1626)** 단 하나 (optimizer/agent.py:347 호출 → 9 jsonb upsert). `_evm_by_wa_l6_company`·`_compose_evm`·`_build_quadrant`·`_build_wp_summary`·`_build_kpi`·v1 `_build_productivity_views`(:48~806)는 **dead code**(테스트만) — 손대지 말 것. (앞 §0-2 가 인용한 _compose_evm 단위혼재는 live 무영향.)

### 3-A. forecaster — 단위별 스트림 + 딜레이 actual_rate + l6 병목
- 실 타겟: `forecaster/agent.py` `_forecast_one_group`(88-97 main_unit, 157-196 plan/delay), `forecast`(301-357 group 키 (wa,company,l6)); `forecaster/aggregate.py` `compute_delay`(142·150), `fetch_pg_actual_cum_qty`(14-40 WHERE unit=$3), `aggregate_today_by_unit`; `classify.py` `classify_risk_level`(DELAY_DAYS_BOUND=5).
- 현 동작: 그룹당 1 row, `main_unit = max(positive_units by today_qty)`(매일 변동), delay 분모 = `plan_per_day_qty = plan_total/total_days`, actual_cum = main_unit 단일.
- 바꿀 것: ① main_unit 단일선정 → **unit별 스트림 전부 계산**(unit별 productivity·plan_qty(distinct SUM)·actual_cum·compute_delay). ② delay 분모 → **actual_cum_qty / days_elapsed**(실 페이스; 사용자 50÷10=5일). ③ l6 카드값: 생산성 헤드라인 = **plan_mh 가중**, delay = **단위별 병목(max)**, risk_level = 단위별 worst. ④ main_unit 컬럼 = '대표 unit'(병목 or plan_mh 최대)으로 재정의(하위호환).
- 엣지/리스크: actual_cum=0·days_elapsed=0 → 분모 0 (fallback rate + 가드 필수). actual_rate 분모는 느린 현장서 **폭주**(과거 26,517일) → 상한 클램프. 분모 스케일 변경 → `DELAY_DAYS_BOUND=5` 임계 재튜닝(risk_level 대량 재분류). **딜레이 SSOT = aggregate.py 한 곳** — view_builder 만 고치면 −37 재발.

### 3-B. view_builder — l6 rollup·단위별 detail·mh가중·병목 (전부 `_build_productivity_views_v2` 내부)
- 실 타겟: grouped_items 루프(1833-1868, 현 `agg_pp=Σqty/Σworkers` 단위혼재), quadrant/wp_summary(1879-1939), `_wp_name_with_wa`(1870, 현 `{l7_5}·{wa}`), `_build_optimizer_view` details(1250-1257)·`_group_perperson_unit`(1597, 혼재시 None→'%만'), site headline(1755-1827, `_weighted_median(plan_mh)`), KPI delay(2111-2132), 일정영향 override(2142-2158), `_build_s_curve` actual(967-1009 cross-unit SUM).
- 바꿀 것: ① 계산 grain (company,wa,l6,**unit**) 분리 후 카드로 collapse(단위 차원 보존→detail 배열). ② 라벨 `_wp_name_with_wa` l7_5 → **l6_main**. ③ 헤드라인 mh가중(median vs 평균은 §9-open). ④ 카드 detail **단위별 행**(콘크리트 m³/인·철근 ton/인) source = v2 items(mapper l7_5 + activity_master LATERAL, unit 보존). ⑤ delay = 단위별 병목(forecaster 값 소비). ⑥ `_build_s_curve` actual을 (report_date,wa,l6,**unit**) 집계 후 plan_mh 가중(현 cross-unit SUM 제거; planned 곡선은 plan_wv×plan_mh 가중이라 이미 무관).
- 엣지/리스크: **site=Σcard 불변식** — median→평균 바꾸면 SSOT 정합 깨짐(점검). FE `types.ts` perperson 은 단일 number → 단위별은 `details`(string) 텍스트로 넣는 게 무변경 안전. wp_id=`_wp_id_of(wa,l6,company)` 유지(quadrant↔optimizer Jaccard 정합 의존).

### 3-C. catch-up 곡선 + recovery_days
- 실 타겟: `web/lib/diagnosis.ts buildScenarioCurve`(55-87 직선), `diagnose`(90-128), `diagnosis-adapter.ts`(recovery_days_p25/50/75 주입), `view_builder._build_scenarios`(1354-1454, site=Σby_wp:1428; recovery_days = 과거 회복분포 percentile:1396), `ForecastChart.tsx`(catch_up 마커 276-294).
- 현 동작: 곡선 = lastActual→plan[today+recoveryDays] **단일 직선**. recovery_days = 과거 유사 cases 회복분포 median(gap·rate 무관). 곡선은 누적 % 공간, plan_rate/deficit 안 받음.
- 바꿀 것: ① buildScenarioCurve = **boosted = plan_rate × k 점진 수렴**(일별 actual+=boosted, plan+=plan_rate, gap=(boosted−plan)/일로 닫힘). ② catch-up일 = **deficit ÷ (boosted−plan)**. ③ recovery_days gap기반 재정의(Σby_wp=site SSOT 유지). ④ **k 는 BE에서 산출해 scenarios_jsonb로**(FE 상수면 BE recovery_days SSOT와 갈라짐). **k 미확정 — 실 UI 보고(§6).**
- 엣지/리스크: **단위 혼선** — 곡선은 %, deficit÷rate는 물량/페이스 → **%↔물량 환산 정의 필수**. gap≤0이면 곡선 미표시(현 max(1,..)로 가짜 1일 라인). boosted≤plan(k≤1)이면 catch-up ∞ → k 하한. plan_rate 추출 = 인접 차분 vs 전구간 평균(매끄러움 직결, §9-open).

## 4. 주입점·적재 경로 (게이트 후)

- **backfill build_demo_graph 전환**: `backfill_optimizer_advice_llm.py`(:48 import, :225) `build_atomized_demo_graph` → **`build_demo_graph`**(graph.py:475, atomizer 노드 없음) → 재실행마다 Azure 임베딩/Chroma upsert 회피.
- **★ run_id 일원화 (블로커)**: seed 는 mapped_history 를 `_date_run_id`(결정성)로 쓰는데 backfill 은 `uuid4` 새 run_id 로 forecasts/views 작성. `api.py _WP_SUMMARY_SQL` 은 `mh.run_id = pr.run_id` join → **갈라지면 wp_summary 빈다**. → backfill 이 **seed run_id 재사용**(pipeline_runs 새 INSERT 대신 hydrate→ainvoke with seed run_id, --clean 은 그 run_id artifact만 정리)하도록 변경 필수.
- **★ atomized_count / hours_saved KPI (블로커)**: build_demo_graph 는 atomized_ids 안 채움 → reporter `update_site_hours_saved_cum`(graph.py:456-460) hours_saved=0 → 시연 '수작업 절감시간' KPI 0. → reporter 가 `pipeline_runs.atomized_count`(seed 가 n_active 박음, seed_day:747) 읽도록 보완.
- **mapped_history per-unit**: 현 ON CONFLICT `(run_id,wa,l6_main,company)` collapse(마지막 unit만). → **`(wa,l6,company,unit)` pre-SUM 권장**(A_Track 단독, DB migration 불필요). ON CONFLICT 키 확장은 DB 제약 변경=B_Track 협업 → 회피. `api.py _WP_SUMMARY_SQL` self-join(:441)·`_TASKS_ITEMS_SQL`(:920)이 unit row 증가에 견디는지 검증.
- **Chroma 1회 재적재**: seed `--chroma-on`(새 work_content). doc_id=sha256(date|company|l6|work_content) 에 unit 없음 → 같은 l6+work_content 다른 unit dedup(per-unit은 Chroma까지 안 감, retrieve는 l6 레벨 충분 — 확인). live atomizer 가독형식 vs seed work_content 본문 차이는 retrieve가 metadata 기반이라 무해(검증).
- **seed 입력전용 리팩터**: `seed_day` 7~10단계(forecasts:771 / optimizer_advice:781 / daily_reports:797 / view jsonb:808) 제거 → 실 그래프 생성. 1~6단계(pipeline_runs·parser·mapper·mapped_history) 유지(consolidated_reports FK 위해 run_id 필요). 제거 후 `_build_forecast_row`/`_build_optimizer_advice` 등 dead code 정리.

## 5. 실행 순서 (task)

1. #159 디자인 문서 영속화 (본 문서).
2. #160 시딩 알고리즘(§1) + #161 검증 함수(§2) → #162 **GATE**: start~9/24 빌드 + 월별 숫자검증 통과 + 사용자 확인.
3. (게이트 후) #163 forecaster · #164 view_builder · #165 catch-up · #166 주입점/seed → #167 9/24 PoC UI 정합.
4. #168 orphan DELETE + 2024-04-11~2025-09-24 전체 재적재 + 월별 UI 검증.
5. #169 §3~4 writing-plans 경유 여부 결정(게이트 후).

## 6. 미확정 파라미터

- **catch-up 배수 k** (boosted_rate = plan_rate × k): 실 UI 보고 확정. 후보 1.5/2/3x. 너무 가파르지 않게.
- **정규분포 σ**: 기본 기간/4 — 검증 결과 보고 조정 가능.
- **§3~4 writing-plans 경유 여부**: 게이트 통과 후 결정(권장 yes).

---

## 8. #1 게이트 결과 — 통과 (2026-05-29 3차, 사용자 확인)

구현 완료(미commit):
- `pipeline/agents/synthetic/seed_distribution.py` — `bell_distribute`(정규분포 σ=기간/4)·`conserve_actual`(총합보존, tail_frac=0.30)·`cumulative`. 단위테스트 `pipeline/tests/test_seed_distribution.py` **9/9 통과**(0.01s).
- `scripts/seed_dummy_year.py` — `_v2_activity_series`(활동당 시계열 캐시: plan bell + actual 조건엔벨로프 + **stretch 지각완료** + today_cum=Σ일별) + `_activity_delay_ext` + `_build_mapper_row` 교체. 구 F3·`plan_total×cum_frac` 버그 제거.
- `scripts/verify_seed_numbers.py` — **DB write 0** 결정론 검증(activity_master만 읽어 시계열 계산·월별 대조).

**최종 튜닝 파라미터:**
- `conserve_actual` tail_frac = **0.30**
- `DELAY_PROB = 0.55`, `DELAY_EXT_MIN_DAYS = 90`, `DELAY_EXT_MAX_DAYS = 240` (지각완료 stretch)
- bell σ = 기간/4

**검증 결과(2024-04-11~2025-09-24, verify_seed_numbers):**
- 9/24 site 공정율 actual **90.1%** vs plan **99.3%** = **갭 −9.2%pt**, 중간 피크 **−16.8%pt**(2024-12) → behind→partial recover.
- 총합보존: actual 완료 **515/515 통과**(±1%). 지각완료(ext>0) 335/689(가중 62%).
- 진행중 60건 p50 0.79, **지각(plan 완료·actual 미달) 111건 p50 0.66**.
- Σmh 0.82~1.15x. 단위 단위(per-unit) 스트림 기준.
- 막바지 surge: **실제 없음** — s-curve 완만(6→9월 +3.1/+3.2/+2.4%pt, plan과 나란히 감속). "월qty 2.66x"는 9월 plan qty≈0 분모 아티팩트. per-WP catch-up 곡선 가파름은 §3 AI 시나리오(diagnosis.ts, 배수 k·UI)에서 처리.

**다음(§3~4, #169): writing-plans 경유 권장.** forecaster 단위별+딜레이 actual_rate(#163) / view_builder l6 rollup+단위별 detail(#164) / catch-up(#165) / 주입점 build_demo_graph+mapped_history per-unit+Chroma 1회+seed 입력전용(#166) → 9/24 PoC UI(#167) → orphan DELETE+전체 재적재(#168).

## 9. writing-plans 에서 확정할 미해결 결정 (open — 4-agent 분석 종합)

1. **forecasts 저장 grain**: (A) l6 1 row + per-unit JSONB(`delay_by_unit`·`productivity_by_unit`) [**권장** — api.py 소비자 무파손] vs (B) (run_id,wa,l6,company,unit) 다중 row [api join fan-out·중복집계 위험].
2. **catch-up 배수 k**: 실 UI 보고 확정. BE 산출(scenarios_jsonb) 권장 — FE 상수는 fallback만.
3. **days_elapsed 정의**: (today−plan_start).days vs +1 vs 첫 actual일 — delay 분모 off-by-one.
4. **헤드라인 mh가중 = 평균 vs median**: 현 `_weighted_median`. site=Σcard 불변식과 정합 확인.
5. **mh 가중치 source**: `fetch_plan_for_group` 는 plan_mh 를 unit 분해 안 함 → unit별 plan_mh 있나 / plan_qty 비율 근사?
6. **delay actual_rate 분모 상한(클램프) 정책** + actual_cum=0 / days_elapsed=0 fallback rate.
7. **wa 차원**: '표시 grain l6 카드 1개' vs 현 wp_id=(wa,l6,company). wa별 분리 유지 여부(현 유지가 안전).
8. **recovery_days 재정의 시 과거 회복분포 카드**(`recovery_distribution_text`) 존치 vs 폐기 (병기 vs 대체) — 사용자 의도.
9. **run_id 일원화 방식**: backfill 이 seed `_date_run_id` 재사용(pipeline_runs 새 INSERT 생략) — §4 블로커 해법 확정.
10. **per-unit Chroma 여부**: doc_id 에 unit 없어 dedup. retrieve 가 l6 레벨로 충분한지(현재 충분 추정).

> 위 10개는 §3~4 구현 전 결정 필요. #163~166 writing-plans 플랜이 이를 task별로 확정·검증.

## 환경/재개
- dev: `cd web && npm run dev2` (5537). URL: http://127.0.0.1:5537/reports?date=2025-09-24
- 실행: `cd pipeline && set -a; source ../.env.local; set +a; PYTHONPATH=$PWD/..  uv run python ../scripts/...` (AWS PG 43.200.85.209:5532, Chroma 5533)
- 9/24 1일 실그래프: `backfill_optimizer_advice_llm --start-date 2025-09-24 --end-date 2025-09-24 --site m15x-ph3-ibl --clean` (→ views 자동)
- psql: `PGPASSWORD='K7mP2xQ9nR4v' /opt/homebrew/opt/libpq/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia`
