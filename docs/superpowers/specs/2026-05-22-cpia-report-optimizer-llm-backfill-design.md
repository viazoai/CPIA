# CPIA Report Optimizer LLM Backfill — Design

> 작성: 2026-05-22 (브레인스토밍 끝, 사용자 모든 결정 수령)
> 목표: 현장 일일 리포트 4섹션 (진단 / 유사 과거 사례 / 권고사항 / 상세 현황) 데이터 부실 해소.

---

## 1. 배경 — 사용자가 본 부실 화면

`/reports` 9/22 광건 수장공사 FAB (4분면 산점도 가장 큰 점, impact 72.4%) 클릭 시:

```
>>> 진단
신규 작업 — 광건 수장공사 의 과거 유사 이력 부족. 마스터 baseline 기준 일일 quota 권고로 갈음.   ← placeholder, 의미 X
>>> 유사 과거 사례
유사 사례 없음 — 데이터 누적 후 갱신                                                                 ← 통째 비어있음
>>> 권고사항
1.                                                                                                   ← list 마커만, 텍스트 빈 string
>>> 상세 현황
일정 영향: 258일 지연                                                                                 ← 양은 plan 108% 충족인데 mh 만으로 258 산출
```

진단 결과:

| 문제 | Root cause |
|---|---|
| 진단 placeholder | `_compose_cold_start_row` 가 `cases<3` 일 때 LLM bypass, 고정 텍스트 박음 |
| 유사 사례 0건 | Chroma retrieve 가 `company` hard filter + `worker_source` 화이트리스트 + degradation incident AND 조건 → 합성 3사 (남웅·세보·창원) 외 75사 모두 0 |
| 권고 빈 string | `_compose_cold_start_row.recommendations[0]` 가 `{rank, action, rationale}` dict 인데 view_builder 는 `r.get("text")` 만 추출 → key mismatch |
| 일정 영향 258일 (양은 충족인데) | `compute_delay` 가 mh-window deficit 기준 → qty 108% over-delivered 인데도 mh underestimate (Chroma actual underestimate) 로 huge gap |
| 표현 단위 모호 ("생산성 0.5") | view_builder description 에 `main_unit` 미명시 |
| 회복 분포 가시성 (`d+2: 1건`) | abbreviation 그대로 노출 |

근본 원인 정리 — 4분면 점 8 중 LLM 진단 받은 게 **0건**. 모두 cold_start placeholder + deterministic fallback.

---

## 2. 확정된 fix (이미 적용 + PoC 검증 OK)

### A1. retrieve company filter 풀기
`pipeline/agents/optimizer/retrieve.py` 의 `_group_baseline`, `fetch_degradation_cases`, `fetch_recovery_trajectory` 의 `company` 인자 → `Optional[str]`. `None` 이면 company 비교 skip. → cross-company case retrieve 가능.

### A2. hil_2 retrieve where 절 정리
`pipeline/graph.py:351-355` `coll.get(where={"$and":[{"company":...},{"l6_main":...}]})` → `coll.get(where={"l6_main": r["l6_main"]})`. 호출자에서 `company=None` 전달.

### A3. view_builder `_normalize_impact` rename
`pipeline/agents/optimizer/view_builder.py` 의 line 1246 `_normalize_impact(impacts: list)` → `_normalize_impact_share` 로 rename (line 374 의 `_normalize_impact(raw, p90)` 와 이름 충돌 해소). line 1418 caller 같이.

### A4. description format — 단위 + 인원
`_build_optimizer_view` 의 similar_cases description:
```
BEFORE: f"{conditions} - {activities[0]}, 생산성 {productivity:.1f}"
AFTER : f"{conditions} - {activities[0]}, 생산성 {productivity:.2f} {main_unit}/인 (인원 {workers:.0f}명)"
```
main_unit 출처: `matched_f.main_unit` (forecast row).

### A5. 회복분포 풀어쓰기
```
BEFORE: "d+2: 1건 / d+3: 1건 / not_recovered: 1건"
AFTER : "2일 후 정상 회복 1건 / 3일 후 정상 회복 1건 / 미회복 1건"
```

### A6. retrieve degradation filter 완화
`fetch_degradation_cases`:
- `worker_source` 화이트리스트 제거 (`synthetic_v2 + mh_prorated` → 전체 인정)
- degradation 정의 완화: `conditions ∋ incident` **AND** `prod < baseline×0.85` → **OR**

### A7. compute_delay qty 기반 산식
`pipeline/agents/forecaster/aggregate.py` `compute_delay`:
```
remaining_qty   = max(0, plan_total_qty_main − actual_cum_qty)
avg_pace_qty    = actual_cum_qty / window_days
remaining_days  = remaining_qty / (avg_pace_qty if >0 else today_qty_main)
expected_completion = today + remaining_days
delay_days      = (expected_completion − plan_finish).days
                  (양수=지연, 음수=앞당김, 0=일정 충족)
```
부수 mh 컬럼 (`expected_in_window_mh`, `mh_gap`, `actual_in_window_mh`) 은 reference 만 유지.

### A8. fetch_pg_actual_cum_qty 신설
`aggregate.py` 에 신규 helper. `mapper_activities` 가 source of truth (Chroma 는 mapper 의 22% 만 backfill 되어 underestimate).
```sql
SELECT SUM(today_qty) FROM mapper_activities
WHERE company=? AND l6_main=? AND unit=? AND report_date<? AND is_mock=false
```

**TODO (post-PoC, multi-site 시)**: 현재 site_id filter 부재 — 시연 이후 6 site 확장 시 (CLAUDE.md "5개 mock + 1개 실 PoC") 같은 (company, l6_main, unit) 가 cross-site sum 됨. forecast() 시그니처에 site_id 추가 + WHERE 절 확장 필요.

### A9. forecaster `_forecast_one_group` 정합
`pipeline/agents/forecaster/agent.py` 에서:
- `fetch_chroma_actual` 그대로 (mh + workers 산출만)
- `fetch_pg_actual_cum_qty` 추가 호출 → `compute_delay` 에 전달
- `forecast row.expected_completion` = `delay_info["expected_completion"]` (plan_finish fallback)

### PoC 검증 결과 (9/22 광건 수장공사 FAB)
| 지표 | BEFORE | AFTER |
|---|---|---|
| advice LLM-driven 비율 | 2.8% | **100%** (옵션 B+C 적용 후) |
| 광건 cases | 0 | **5건** |
| 광건 진단 | placeholder | LLM 자연어 |
| 광건 권고 | 빈 string | **4건** 자연어 |
| 회복분포 | `d+2: 1건 / not_recovered: 1건` | `2일 후 정상 회복 ... / 미회복 1건` |
| 일정 영향 | **258일 지연** | **−8일 (앞당김)** |
| description | `생산성 0.5` | `생산성 0.52 m/인 (인원 107명)` |

---

## 3. Spec 본문 작업

### B1. 사용자 직접 수정분 reconcile
PoC 중 사용자가 `prompt.py` / `agent.py` (optimizer) / `retrieve.py` / `aggregate.py` / `forecaster/agent.py` 일부 직접 수정. system reminder 가 의도된 변경이라 announce. 최종 spec 작성 직전 Read 로 현 상태 확인 + A1~A9 와 충돌 없는지 reconcile.

### B2. `_compose_cold_start_row` 함수 정책 통일 (옵션 (a) 확정)
**결정: 옵션 (a) 채택.** PoC 가 advice LLM-driven 비율 2.8% → 100%, 광건 fab cold_start placeholder → LLM 자연어 진단·권고 4건으로 검증 완료. cases<3 도 `_compose_row` path 로 보냄. `_compose_cold_start_row` 함수 제거.

B1 reconcile 은 코드 sync 만 — 사용자 직접 수정 흔적 (system reminder 가 announce) 이 옵션 (a) 와 충돌 없는지 git diff 로만 확인.

**A6 (filter 완화) 와의 관계**: A6 와 B2(a) 는 **둘 다 필요**. 둘이 같은 문제 (cold_start placeholder) 의 서로 다른 면을 fix:
- **A6**: degradation filter 의 AND→OR + worker_source 화이트리스트 제거 — retrieve **범위** 확대 (광건 cases 0 → 5)
- **B2(a)**: `cases<3` threshold 폐기 — cases 0 인 그룹도 LLM 호출하여 baseline 기준 진단
- A6 적용으로 대부분 그룹이 cases≥3 가 되지만, 일부 (Chroma 누락 그룹) 는 여전히 0건 → B2(a) 가 그 fallback path

### B3. LLM 병렬화 (사용자 명시 요청)
**현재**: forecaster `_forecast_one_group` 직렬, optimizer `optimize()` 직렬. group/advice 1개씩. atomizer 는 이미 batch (16) 라 병렬화 불필요 — `batch_size` 만 키움.

**변경**:
- `forecaster.forecast()` 의 group 루프 → `asyncio.gather` + `asyncio.Semaphore(4)`
- `optimizer.optimize()` 의 forecast 루프 → 같은 패턴
- `_forecast_one_group` 내부 `azure.embeddings.create` / `azure.chat.completions.create` sync 호출 → `asyncio.to_thread` 로 감싸기 (실 병렬 효과)
- `optimizer._call_azure_llm` 도 동일
- `atomizer.AtomizerConfig.batch_size` 디폴트 **16 → 64** (embedding API 는 input limit 이 큼)
- PG insert 는 thread-safe 보장 (asyncpg pool acquire 사용)
- 병렬도는 env `CPIA_LLM_CONCURRENCY` (기본 4) 단일 변수로 통일 — forecaster/optimizer 둘 다 같은 값 공유

**예상 효과**: 1일 cycle ≈ 16분 직렬 → **4분 병렬 (4×)**. 15일 ≈ 60분.

### B6. atomizer 단계 PoC 포함 (사용자 push back)
**현재 PoC**: `build_demo_graph` (forecaster → hil_2 → optimizer → reporter) 사용 — atomizer skip. Chroma 는 기존 `backfill_chroma_daily_activities.py` 결과 그대로 사용.

**문제**:
- C1 (parser conditions 추출) 적용 → `mapper_activities.conditions` 새로 채워짐 → atomizer 가 Chroma 재적재해야 metadata 의 `conditions` 가 갱신됨
- C4 (Chroma 정합) — mapper 의 22% 만 적재된 문제 → atomizer 다시 돌려서 모든 mapper row 적재 필요

**변경**:
- 새 graph: `build_atomized_demo_graph` = **atomizer** → forecaster → hil_2 → optimizer → reporter (mapper + hil_1 만 skip, mapped 는 PG mapper_activities 에서 hydrate)
- 또는 PoC 스크립트가 graph 호출 전 `atomize(mapped, parsed_report, run_id, cfg.atomizer)` 명시 호출
- atomize 의 batch_size 64 로 호출 → 1일 atomize ≈ 5초 (15일 ≈ 75초)

**시연 critical 판단**: C1/C4 적용 안 하면 atomize skip 가능. C1 채택했으니 atomize 포함 필요.

### B4. backfill 스크립트 일반화
`scripts/poc_optimizer_5day_backfill.py` → `scripts/backfill_optimizer_advice_llm.py` rename + 일반화:
- `--days N` (기본 15)
- `--start-date YYYY-MM-DD` / `--end-date YYYY-MM-DD` (range)
- `--site m15x-ph3-ibl`
- `--trades 건축,토목` (기본)
- `--clean` — 같은 (site, date) 의 비-dummy_seed 흔적 + dummy_seed advice/forecasts 정리 (멱등)
- 각 일자 후 `backfill_v2 --date` 자동 호출 (view jsonb 갱신)
- 마지막에 통과 기준 5가지 자동 출력 (B5)

### B5. 통과 기준 자동 검증
실행 후 PG diff 검증 자동:
1. `optimizer_advice.diagnosis` 평균 길이 ≥ 50자 (cold_start placeholder = 63자지만 그건 옵션 B 적용 후 0건이어야)
2. `optimizer_advice.degradation_cases` jsonb 의 `conditions/activities/productivity/recovery` 4필드 모두 채워진 비율 ≥ 90%
3. `optimizer_advice.recommendations` 가 `[{rank, text}, ...]` schema (text 키 빈 string 0%)
4. `daily_reports.optimizer_view_jsonb.by_wp[wp_id].details` 6칸 모두 non-`"—"` 비율 ≥ 80%
5. quadrant 의 wp_id 와 by_wp wp_id 교집합 비율 ≥ 80% (default_wp 가 LLM 진단 받을 확률)

### C1. conditions 추출 (parser)
**현재**: 실 작업일보 `parser_activities.conditions` 컬럼 없음. `mapper_activities.conditions` 컬럼은 jsonb (list) 인데 100% `[]`.

**변경**:
- `pipeline/agents/parser_post.py` 또는 `parser.py` 에 `_extract_conditions(work_content: str, note: str) -> list[str]` 추가
- 키워드 grep: `장비대기`, `자재미입고`, `우천`, `돌관`, `야간연장`, `흐림`, `맑음` (외 후보 추가)
- 추출 대상: `work_content` + `note` (비고) + 작업일보 의 기상 필드 (있다면)
- `parsed['activities'][i]['conditions']` 에 list 박음
- `mapper_node` 의 `insert_mapper_activities_batch` 가 conditions list → jsonb 저장
- 기존 빈 `[]` row 백필 옵션: `scripts/backfill_conditions.py` (work_content 재파싱)

### C2. dummy 생성 정책 fix
**현재 문제**: `seed_dummy_year.py` 와 `backfill_chroma_daily_activities.py` 가 plan_total_qty 무시하고 임의 분배. 결과: 광건 수장공사 mapper sum 62K m2 > plan 57K m2 (108%, over-delivered).

**변경**:
- `seed_dummy_year.py` 의 per-day qty 분배 시 `plan_total_qty / plan_period_days × 변동성` 으로 cap
- backfill 가 plan 초과 발생 시 warn + 자동 cap
- 기존 backfill 데이터: 별도 cleanup 스크립트 (`scripts/cleanup_over_plan_qty.py`) 옵션 — over 분 비례 축소 또는 그대로 유지 (시연 영향 적음)

### C3. quadrant ↔ advice wp_id 매칭 보강
**현재**: 옵션 B+C 적용 후에도 quadrant 8 wp 중 1건 (fab-수장공사-선보) 이 advice fan-out 매칭 안 됨 → deterministic fallback.

**원인**: forecaster risky 그룹 key (`company|l6_main`) vs quadrant wp_id (`{zone}-{l6_main}-{company}`). wa_lookup fan-out 이 모든 wa 를 cover 못 함.

**변경**:
- `view_builder._build_optimizer_view` 의 wa_lookup miss 시 `mapper_activities` 에서 그 (company, l6_main) 의 wa list 재조회
- 또는 forecaster 가 처음부터 wa 별로 분리해서 forecast row 생성 (현재 wa=FAB / wa=CUB 분리는 됨, 그러나 advice 는 (company, l6_main) 단위)
- 가장 안전: `_build_deterministic_cold_start` 가 fan-out 매칭 안 된 wp 만 적용하되, advice 가 있으면 같은 (company, l6_main) advice 를 zone 별 wp_id 에 동일 적용

### C4. Chroma backfill 정합
**현재**: `backfill_chroma_daily_activities.py` 가 mapper_activities row 중 일부만 적재 (광건 수장공사 1년치 2,526 mapper row → 420 Chroma row, 17%).

**변경**:
- backfill 스크립트가 같은 (company, l6_main, date) row 를 모두 적재
- 또는 group 단위 1 row 로 합쳐서 적재 (assigned_workers / qty 합산) — RAG retrieve 의미 단위 일치
- conditions 추출 (C1) 결과 같이 적재

→ 우선 actual_cum_qty 는 PG 로 우회했으니 (A8) 시연 critical 아님. spec 의 별도 phase 가능 — 결정 사용자에게 다시 받음.

### C5. forecast 컬럼 의미 정정
**현재**: qty 기반 산식으로 변경됐는데 `expected_in_window_mh / mh_gap / actual_in_window_mh` 컬럼명 mh 그대로. UI 표시 X (reference 만).

**변경 후보**:
- (a) 컬럼 그대로 유지 (PG schema 변경 없음, reference 의미 명시)
- (b) 새 컬럼 추가 (`expected_in_window_qty`, `qty_gap`, `actual_in_window_qty`) — UI/대시보드에서 의미적으로 정확
- → **(a) 채택** — 시연 critical 아니고 schema 변경 영향 큼

---

## 4. 실행 plan — 15일치 PoC

### 4.1. 일자 / 범위
- **15일** = `2025-09-08 ~ 2025-09-22` (시연 기준일 9/25 의 직전 15일 안에서 9/22 까지)
- **site**: `m15x-ph3-ibl` (mock=false 1 site)
- **trade filter**: `건축 + 토목`
- mapper_activities 의 이 trade row 가 일평균 약 435건 (9/22 기준) — 그룹 약 117

### 4.2. 1일 cycle 시간 추정
| 단계 | LLM 호출 | 직렬 시간 | 병렬 4 시간 |
|---|---|---|---|
| atomizer (batch 64) | ~200 doc embedding (3~4 batch) | ~5초 | ~5초 |
| forecaster | ~120 group (건축+토목 중 wa 분리) | ~10분 | **~2.5분** |
| optimizer | ~60 risky | ~5분 | **~1.5분** |
| reporter + view_builder + PG insert | 0 LLM | ~1분 | ~1분 |
| 1일 cycle 총 | | ~16분 | **~5분** |
| **15일 직렬 cycle** | | ~4시간 | **~75분** |

### 4.3. 실행 순서
1. **B1**: 사용자 revert 흔적 reconcile (git diff 로 코드 sync 확인)
2. **B2**: cold_start 정책 통일 (옵션 (a) 확정 적용)
3. **B3**: LLM 병렬화 코드 적용 (forecaster + optimizer + Semaphore + to_thread + atomizer batch 64)
4. **C1-pre**: parser work_content 키워드 hit 율 사전 측정 — 9/22 mapper_activities 의 work_content 435건에 `장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장` grep, hit 율 ≥10% 면 C1 진행, 미달 시 키워드 확장 또는 외부 데이터 (날씨 등) 보강 결정
5. **C1**: parser conditions 추출 추가 + 기존 mapper_activities conditions 백필 스크립트 (C1-pre 통과 시)
6. **B6**: `build_atomized_demo_graph` 신설 (atomizer → forecaster → hil_2 → optimizer → reporter)
   - **`backfill_optimizer_advice_llm.py` (B4) 책임**: graph 호출 전 `pipeline_runs` INSERT (status='running') + `mapped` PG hydrate 둘 다 수행. atomizer 가 `assert_pipeline_run_exists(run_id)` fail-fast 이므로 INSERT 누락 시 atomize 진입 단계에서 RuntimeError
   - doc_id 멱등: `_make_doc_id(date, company, l6_main, work_content)` sha256 — 같은 (date, company, l6_main, work_content) 가 일자별 다른 run_id 로 upsert 되면서 metadata.run_id 가 마지막 일자로 덮어쓰여 retrieve 출처 일자 추적이 어그러질 가능성. atomizer 의 `_build_metadata` 가 run_id 외에 date 도 박으니까 retrieve 시 date 만으로 일자 추적 가능 — OK
7. **C2**: dummy 생성 정책 fix (시연 영향 적음, 후순위)
8. **B4**: backfill 스크립트 일반화 — mapped hydrate → atomize → demo graph
9. **B3-verify (1일 dry-run)**: 15일 backfill 전 1일치만 먼저 돌려서 Azure OpenAI rate limit (TPM/RPM) + wall time 측정. `ai-board-test` 엔드포인트 quota 초과 시 Semaphore 하향 조정 (4 → 2 등). 통과 후 D 실행
10. **D 실행**:
   - 15일 cycle: `python scripts/backfill_optimizer_advice_llm.py --days 15 --site m15x-ph3-ibl --trades 건축,토목 --clean`
   - 각 일자 후 backfill_v2 자동 재산출
   - 마지막에 B5 통과 기준 5가지 자동 출력
11. **D-9/25 회귀**: 시연 기준일 9/25 단일 cycle 별도 실행 — 기존 cycle (Parser → Mapper → ... → Reporter) 가 새 코드와 호환되는지 + 시연 화면 (광건 fab 등) 풍부함 확인
12. **D3**: UI `/reports` 에서 15일치 일자 클릭 → 4분면 점 클릭 → 4섹션 풍부함 확인
13. **C3**: 통과 기준 5 (wp_id 매칭 ≥ 80%) 미달 시 quadrant ↔ wp_id fan-out 보강
14. **C4, C5**: 시연 이후 또는 시간 여유 시 추가 진행

### 4.4. 비용 추정
- forecaster LLM 1일 ~120 × 15일 = 1,800 calls
- optimizer LLM 1일 ~60 × 15일 = 900 calls
- 총 ~2,700 calls × gpt-5.1-chat ≈ **$15~30** 추정

---

## 5. 통과 기준 (success criterion)

15일 cycle 끝난 후:

| # | 기준 | 목표 |
|---|---|---|
| 1 | diagnosis 평균 길이 | ≥ 50자, placeholder 패턴 (`"신규 작업 —"`) = 0% |
| 2 | degradation_cases 4필드 채워진 비율 | ≥ 90% |
| 3 | recommendations `{rank, text}` schema, text 빈 string | = 0% |
| 4 | details 6칸 non-`"—"` 비율 | ≥ 80% |
| 5 | quadrant ↔ by_wp wp_id 교집합 | ≥ 80% (UI default_wp 가 LLM 진단 받을 확률) |
| 6 | 시연 일자 (9/22 등) UI 광건/태우/세보엠이씨 wp 클릭 시 진단 자연어 + 사례 ≥3건 + 권고 ≥3건 | 시각 확인 |
| 7 | `delay_days` 분포 | **그룹 별 `actual_cum_qty / plan_total_qty_main` 비율로 판정** — over-delivered (≥1.0) 그룹은 음수 (앞당김, 광건처럼 −8일 수준), under-delivered 그룹은 양수 (지연). 산식 자체가 깨지지 않으면 모든 그룹이 합리적 (―∞~+∞) 범위 안에 산출 |

미달 시 phase 분리 — 별도 fix 진행.

---

## 6. 변경 영향 / 리스크

- **FE 디자인 불변** (CPIA 메모리 룰): `OptimizerResult.tsx` / `WPSummaryTable.tsx` 등 손대지 않음. BE 데이터 적재만.
- **PG schema 변경 없음** (C5 (a) 채택).
- **회귀 위험**: 9/25 실 cycle (시연 기준일) 의 advice 생성 흐름과 호환. fix 모두 same path 공유.
- **LLM 비용**: 15일 PoC ~$15~30. 시연 마감 (6/5) 전 한 번 더 돌릴 여유 있음.
- **Chroma backfill 정합 (C4)**: 별도 phase 로 분리 가능. actual_cum_qty 는 PG 로 우회했으니 시연 critical 아님.
- **conditions 추출 (C1)**: 추출 안 해도 옵션 B+C 로 cases 가 채워짐 (degradation 정의가 OR 조건이라). C1 은 RAG retrieve 의미적 정확도 ↑ 부수 효과만. 후순위 가능.

---

## 7. 다음 단계

1. spec-document-reviewer 루프 (이 문서 자동 검토)
2. 사용자 검토 게이트
3. `superpowers:writing-plans` skill 호출 → 실행 plan 생성
4. plan 실행 (위 4.3 순서)
