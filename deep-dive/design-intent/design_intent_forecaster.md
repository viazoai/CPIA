# Design Intent — forecaster

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Last refreshed**: 2026-05-26 (git SHA `1ba783f`, branch A_Track) — **"코드 변경 없음" 라벨 무효화.** 본 cycle 의 forecaster 관련 5 커밋 (6a89848 / 6ba0126 / 9856889 / bc04c94 / 1e24dc6) 반영.
- **Pair file**: `../deep_dive_forecaster.md` (544 줄, 동 cycle 정합 baseline)
- **Range**: `pipeline/agents/forecaster/` 8 파일 — agent **339** / aggregate 202 / synthetic 189 / prompt 134 / classify 114 / rerank 50 / constants 8 / __init__ 8 = **1044 LOC** (이전 893 → +151).
- **Note**: 본 cycle 의 핵심 차분은 agent.py (+60 LOC) — asyncio.gather 4× 병렬 + plan_main_qty atomic distinct SUM fix + cold start reasoning 4 분기 + Chroma try/except 2단 방어. aggregate.py 는 `fetch_pg_actual_cum_qty` 신설 + `compute_delay` qty 기반 산식 전환.

Mapper 출력 + Chroma 유사 과거 일일 활동 retrieval → 공종별 생산성 진단 (정상/주의/이상/None). 임계값 hardcoding (RAG_NORMAL_BOUND=0.15, RAG_WARN_BOUND=0.25, PLAN_NORMAL_RATIO=0.85, PLAN_WARN_RATIO=0.65, DELAY_DAYS_BOUND=5, RECOVERY_LIKELIHOOD_BOUND=0.7). PG `forecasts` **28 컬럼** INSERT (wa 추가, Phase 2).

---

## T1 — Function Index

### agent.py (339 LOC, +60 본 cycle)
| Function/Class | File:Line | Signature | T2? |
|---|---|---|---|
| `ForecasterConfig` | agent.py:40 | `@dataclass` (Azure + DB + Chroma + rag_n_candidates/top_k/window_days) | — |
| `_format_chroma_result` | agent.py:59 | `(rag_result: dict) -> list[dict]` | — |
| `_forecast_one_group` | agent.py:73 | `async (company, l6_main, activities, run_id, today, pg, coll, azure, cfg) -> dict` | ✅ |
| `forecast` | agent.py:283 | `async (mapped, run_id, today, cfg) -> list[dict]` | ✅ |

### aggregate.py (202 LOC, +83 본 cycle)
| Function | File:Line | T2? |
|---|---|---|
| `fetch_pg_actual_cum_qty` | aggregate.py:14 | ✅ (★ NEW) |
| `aggregate_today_by_unit` | aggregate.py:43 | ✅ |
| `compute_delay` | aggregate.py:52 | ✅ (★ 산식 전환 + docstring) |
| `fetch_chroma_actual` | aggregate.py:157 | ✅ (시그니처 확장) |

### classify.py (114 LOC, 미세 변경)
| Function/Constant | File:Line | T2? |
|---|---|---|
| `RAG_NORMAL_BOUND = 0.15` ~ `RECOVERY_LIKELIHOOD_BOUND = 0.7` | classify.py:19-24 | — |
| `classify_assessment_rag` | classify.py:27 | ✅ |
| `classify_assessment_plan` | classify.py:41 | ✅ |
| `classify_assessment` | classify.py:65 | ✅ |
| `classify_risk_level` | classify.py:83 | ✅ |

### rerank.py / prompt.py / synthetic.py / constants.py / __init__.py
| Symbol | File:Line | T2? |
|---|---|---|
| `_normalize_chroma_metadata` | rerank.py:20 | ✅ |
| `rerank_cases` | rerank.py:32 | ✅ |
| `SYSTEM_PROMPT` / `FEW_SHOT_MESSAGES` | prompt.py:12 / 33-88 | — |
| `build_llm_user_input` | prompt.py:103 | ✅ |
| `generate_synthetic_day` | synthetic.py:21 | ✅ |
| `WORK_HOURS_PER_DAY` | constants.py:8 | re-export from pipeline.constants |

### _concurrency.py (★ NEW 1e24dc6, agents/_concurrency.py)
| Function | File:Line | T2? |
|---|---|---|
| `get_llm_semaphore` | _concurrency.py:15 | ✅ (★ NEW) |

---

## T2 — Issue Cards

> 본 cycle 변경 카드는 ★ 표기. 그 외 카드는 cycle 영향 없음 (시그니처/문구 동일).

---

### 본 cycle 변경 카드

#### `plan_main_qty atomic distinct SUM` (★ NEW, commit 6a89848)

- **위치**: `pipeline/agents/forecaster/agent.py:156-164` (group 안 distinct SUM 로직)
- **변경**:
  - 이전: `plan_main_qty = plan["plan_total_qty_by_unit"][main_unit]` (activity_master 의 (company, l6_main) 전체 l6 SUM).
  - 현재: `plan_qtys = {round(float(a["plan_total_qty"]), 4) for a in activities if a.get("unit")==main_unit and a.get("plan_total_qty") is not None}; plan_main_qty = sum(plan_qtys) if plan_qtys else None` — group 안 mapper_activities 의 main_unit 매칭 `plan_total_qty` 의 **distinct value SUM**.
- **이슈**:
  - 6a89848 commit message: 9/22 site AVG delay = 2,501 일. outlier 분석 — 진특수 방수 l6 SUM=10,523 vs atomic=194 (54×) → delay 26,517; 현대계장 자동제어 228,312 vs 6,065 (38×) → 2,622; 장평건설 포장 30,100 vs 12,380 → 1,358.
  - 원인: `plan_total_qty_by_unit[main_unit]` 는 activity_master 의 전체 l6 SUM. 매칭된 atomic activity 가 그 l6 의 일부일 때 분모 과대 → `remaining_qty / pace = remaining_days` 폭주.
- **설계 의도**:
  - atomic 1:1 매칭 정합화 — group 안의 매칭된 atomic 만 합산.
  - mapper.plan_total_qty 는 atomic 매칭 broadcast (같은 wbs 가 multiple mapper row 면 동일 값) → `set` 으로 double count 방지.
  - `plan_main_qty` 는 ② `classify_assessment_plan` 의 `plan_prod_proxy` 분자, ⑤ `compute_delay` 의 `remaining_qty` 분자에 동시 사용 → 두 path 모두 atomic 단위로 정상화.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ④ assessment 직전 (agent.py:156).
  - 입력: group 의 `activities` list.
  - 처리: main_unit 매칭 row 의 `plan_total_qty` distinct set → SUM.
  - 출력: `plan_main_qty` (None 가능 — main_unit 없거나 매칭 0건).
- **검증** (commit message):
  - 진특수 방수 → top5 에서 사라짐. 자동제어공사 2,622 → -170 (앞당김). 장평건설 포장 1,358 → 512 (-62%).
  - **잔존**: 동신패널 외장판넬 167,871 그대로 (atomic 1행 only — dummy seed anomaly, 산식과 무관). 9-22 outlier **부분 해결, 일부 잔존**.
  - 회귀: 159 passed.
- **관련**:
  - `compute_delay` (aggregate.py:52) — `plan_total_qty_main` 분모 정상화.
  - `classify_assessment_plan` (classify.py:41) — `plan_prod_proxy` 분자 정상화.
  - Plan: `docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md`
- **Suspected related** (2026-05-26 stale):
  - 동신패널 외장판넬 케이스 — dummy seed `plan=29,122 m2 vs today_qty=0.185 m2` 비율 자체가 비현실. 산식 fix 와 별도 데이터 cleanse 필요.

---

#### `asyncio.gather + Semaphore 4×` (★ NEW, commit 6ba0126)

- **위치**: `pipeline/agents/forecaster/agent.py:314-335` (forecast() group 루프).
- **변경**:
  - 이전: group 루프 직렬 (for k, v in groups.items(): row = await _forecast_one_group(...)).
  - 현재: `sem = get_llm_semaphore()` 1회 → `_one(k, v)` 안에서 `async with sem:` → `tasks = [_one(k, v) ...]; await asyncio.gather(*tasks)`.
- **이슈**:
  - 6ba0126 commit message: ~120 group × 1 LLM call 직렬 10분 → 병렬 4× 약 2.5분.
  - get_llm_semaphore() 가 매 호출 새 인스턴스 반환 (`_concurrency.py:18`) → caller 가 entry 에서 1회만 호출하고 closure 로 공유해야 함. 매 _one() 호출마다 새로 받으면 4× 효과 무산.
- **설계 의도**:
  - Concurrency 경계 분리: LLM 호출 (azure.chat.completions.create) 만 sem 안. `pg.insert_forecast` 는 asyncpg pool 이 thread-safe → sem 밖 (lock 잡힌 채 DB write 대기 회피).
  - sem 인스턴스 closure 공유 — entry 에서 1회 (`agent.py:314`), `_one()` 안에서 `async with sem:` 으로 참조 (`agent.py:318`).
  - TDD: `pipeline/tests/test_forecaster_concurrency.py` — cap 2 / 8 group → max_in_flight == 2 검증.
- **대응 패턴**:
  - 발동: `forecast()` entry (agent.py:283).
  - 입력: groups dict + cfg.
  - 처리: sem 생성 → `_one()` 클로저 정의 → tasks list → `asyncio.gather`.
  - 출력: forecast row list (asyncpg pool 동시 write 안전).
- **관련**:
  - `get_llm_semaphore` (pipeline/agents/_concurrency.py:15).
  - `pipeline/tests/test_forecaster_concurrency.py` (TDD).
- **Suspected related** (2026-05-26 stale):
  - 회귀: T1 의 A8 (fetch_pg_actual_cum_qty 신설) 로 wa_grain.test 의 pg_mock.fetch_all 누락 → AsyncMock 추가. e2e.test_forecaster_e2e_namwong_47 은 sites seed mismatch (대소문자) 로 `@pytest.mark.skip` 마킹 (별 task).

---

#### `get_llm_semaphore() 흡수` (★ NEW, commit 1e24dc6 — _concurrency 공용 모듈)

- **위치**: `pipeline/agents/_concurrency.py:15` (forecaster import: agent.py:20).
- **변경**:
  - `get_llm_semaphore() -> asyncio.Semaphore` 헬퍼 신설 (env `CPIA_LLM_CONCURRENCY`, default 4).
  - forecaster + optimizer + atomizer 가 같은 모듈 import → 같은 event loop 안에서는 같은 인스턴스가 자연 공유.
- **이슈**:
  - 1e24dc6 commit message: "forecaster + optimizer + atomizer 공유" — 세 agent 가 같은 Azure quota 를 두고 경쟁하므로 한 곳에서 cap 관리.
  - Lazy 생성 (event loop 별) — 매 호출 새 인스턴스 반환. caller 가 함수 entry 에서 1회 받아 closure 로 공유해야 함 (6ba0126 이 명시).
- **설계 의도**:
  - env 통제 (테스트는 `CPIA_LLM_CONCURRENCY=2` 로 cap 조절).
  - 모듈 분리 — agent 별 sem 만들지 말고 1곳에서 import (atomizer/optimizer 도 동일).
  - `max(1, n)` 가드 — env 잘못 (=0) 일 때 deadlock 방지.
- **대응 패턴**:
  - 발동: forecaster `forecast()` entry / optimizer entry / atomizer entry.
  - 입력: env CPIA_LLM_CONCURRENCY.
  - 처리: `asyncio.Semaphore(max(1, n))`.
  - 출력: Semaphore (caller 가 closure 로 공유).
- **관련**:
  - forecaster `agent.py:314` 호출.
  - optimizer / atomizer 동일 패턴 (cross-agent).
- **Suspected related** (2026-05-26 stale):
  - "매 호출 새 인스턴스" 시맨틱은 함정 — 개별 agent 가 헬퍼를 잘못 쓰면 cap 무효. 향후 caching (loop id 기반) 검토.

---

#### `fetch_pg_actual_cum_qty` — Chroma 우회 PG SELECT 패턴 (★ NEW, deep_dive 발견)

- **위치**: `pipeline/agents/forecaster/aggregate.py:14-40`.
- **시그니처**: `async def fetch_pg_actual_cum_qty(pg, company, l6_main, today, main_unit) -> float`.
- **이슈**:
  - aggregate.py:22-24 docstring 인용: "2026-05-22: Chroma 는 mapper 의 일부만 backfill 되어 있어 actual_cum_qty 산출에 부적합. PG mapper_activities 가 source of truth. 시연 환경 (mock=false) 만 합산."
  - 광건 수장공사 케이스: Chroma 에 mapper_activities 의 22% 만 적재 → Chroma 산출 actual_cum_qty 가 부정확.
  - `fetch_chroma_actual` 는 동일 시그니처 확장 (`today_qty_main`, `main_unit` 인자 추가, `(window_start, actual_cum_mh, actual_cum_qty)` 3-tuple 반환) 으나 caller 가 `_chroma_qty` 를 **무시** (agent.py:176).
- **설계 의도**:
  - **Source of truth 분리**: `actual_cum_mh` 는 Chroma window (인시 누적, 진단용 reference), `actual_cum_qty` 는 PG mapper_activities (compute_delay 분모). 데이터 신뢰도 다른 두 path 를 직접 분리.
  - `mock=false` 필터 — 시연 환경 의도 (synthetic 30일 dummy seed 제외).
  - main_unit 없으면 0.0 early return (가드).
  - 호출자 합산: `actual_cum_qty = pg_cum_qty + today_qty_main` (agent.py:186) — PG 누적 + 오늘 더함.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑤ compute_delay 직전 (agent.py:185).
  - 입력: pg client + company + l6_main + today + main_unit.
  - 처리: `SELECT SUM(today_qty) FROM mapper_activities WHERE company AND l6_main AND unit AND report_date < today AND is_mock=false`.
  - 출력: float (today 이전 누적 qty).
- **관련**:
  - `fetch_chroma_actual` (aggregate.py:157) — mh 만 사용 (qty 반환값은 deprecated reference).
  - `compute_delay` (aggregate.py:52) — `plan_total_qty_main - actual_cum_qty` 분모.
- **Suspected related** (2026-05-26 stale):
  - Chroma backfill 완비 시 본 함수 deprecate 가능 — 다만 mock 분리는 PG side 가 자연스러움.

---

#### `compute_delay` — qty 기반 산식 전환 + mh reference only (★ T18 docstring bc04c94)

- **위치**: `pipeline/agents/forecaster/aggregate.py:52-154`.
- **변경**:
  - 이전: `mh_gap / plan_mh_per_day` (mh-window deficit 기반).
  - 현재: `remaining_qty / pace → expected_completion → delay_days = (expected_completion - plan_finish).days`.
- **이슈**:
  - bc04c94 commit: docstring 만 추가 (산식 자체 변경 없음 — 산식 변경은 선행 commit). T18 mh 컬럼 4 종 (`plan_mh_per_day` / `expected_in_window_mh` / `actual_in_window_mh` / `mh_gap`) 의 "reference only" 의미 명문화.
  - aggregate.py:75-80 docstring 인용: "위 4값은 forecast row jsonb 에 박혀 UI 미사용. 향후 mh 기반 KPI 위한 잠재 자산."
- **설계 의도**:
  - qty 기반 정합 — "양 충족인데 mh 부족이면 큰 delay" 의 false positive 제거.
  - mh 컬럼 schema 보존 — PG `forecasts` 28 컬럼 영향 회피 + 향후 mh-KPI 자산.
  - pace fallback: `avg_pace_qty > 0` 이면 사용, 아니면 `today_qty_main` 으로 대체 (cold start 보호).
  - pace 0 (실 진행 0 + 오늘 0) → `delay_days = None` (산출 불가 명시).
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑤ (agent.py:187).
  - 입력: plan + today + actual_window_start + actual_cum_mh + actual_cum_qty + plan_total_qty_main + today_qty_main.
  - 처리: schedule_state 결정 → mh 4 컬럼 (reference) → qty 산식 (delay_days, expected_completion).
  - 출력: 11-key dict (mh 4 + qty 5 + schedule_state + window_start/days).
- **관련**:
  - `fetch_chroma_actual` (actual_cum_mh source).
  - `fetch_pg_actual_cum_qty` (actual_cum_qty source).
  - `classify_risk_level` (delay_days / schedule_state consumer).
- **Suspected related** (2026-05-26 stale):
  - mh 4 컬럼 UI 미연동 → 의도적 (이슈 #1).

---

### Cycle 영향 없음 카드 (시그니처/문구 동일, 이전 stale)

#### `classify_assessment` — RAG 우선 + Plan fallback + cold start

- **위치**: `pipeline/agents/forecaster/classify.py:65-80` (16 LOC, 분기 3).
- **시그니처**: `def classify_assessment(rag_n, today_prod, rag_avg_prod, plan_total_qty_main, plan_mh_sum) -> Optional[str]`.
- **이슈**: docstring (classify.py:72-74) "Spec §0.1 ②: rag_n >= 3 → RAG / else if plan 가용 → Plan / else None". audit drift #2 의 routing entry point.
- **설계 의도**: 우선순위 명시 (RAG > Plan > cold_start None). cold_start 신호 보존 — 두 path 실패 시 None 반환 → `_forecast_one_group` 이 cold start reasoning 4 분기 텍스트 박음.
- **대응 패턴**: 발동 ④ → rag_n>=3 → RAG / plan_mh_sum>0 AND plan_total_qty_main → Plan / 그 외 None.
- **관련**: `classify_assessment_rag`, `classify_assessment_plan`, `_forecast_one_group`, `test_classify.py:16-92` (8 케이스).
- **Suspected related** (본 cycle 영향 없음): plan_main_qty 분자 변경 (★ 6a89848) 으로 Plan path 결과는 atomic 단위로 정상화 — 본 routing 자체 변경 없음.

#### `classify_assessment_rag` — RAG 임계 (±15% / ±25%)
- **위치**: `classify.py:27-38` (12 LOC). 시그니처 / 임계 (`RAG_NORMAL_BOUND=0.15`, `RAG_WARN_BOUND=0.25`) 변경 없음. boundary `eps=1e-9` (classify.py:33). 본 cycle 무관.

#### `classify_assessment_plan` — Plan ratio (0.85/0.65)
- **위치**: `classify.py:41-62` (22 LOC). `plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / WORK_HOURS_PER_DAY)`. 본 cycle 분자 (`plan_total_qty_main`) 가 atomic distinct SUM 으로 normalize 됨 (★ 6a89848) — 함수 자체는 변경 없음.

#### `classify_risk_level` — hybrid 룰
- **위치**: `classify.py:83-114` (32 LOC, 분기 6). 시그니처 / 임계 (`DELAY_DAYS_BOUND=5`, `RECOVERY_LIKELIHOOD_BOUND=0.7`) 변경 없음. `delay_days` 가 qty 기반으로 바뀐 영향 받음 (input 의 의미 변화).

#### `rerank_cases` / `_normalize_chroma_metadata`
- **위치**: `rerank.py:32-50` / `rerank.py:20-30`. 본 cycle 변경 없음. worker_source=user_corrected → ×0.7, mapping_conf<0.7 → ×1.5.

#### `aggregate_today_by_unit`
- **위치**: `aggregate.py:43-49` (7 LOC). 본 cycle 변경 없음.

#### `generate_synthetic_day`
- **위치**: `synthetic.py:21-63`. 본 cycle 변경 없음. PM 원안 v2 §3-B 변동 패턴.

#### `build_llm_user_input`
- **위치**: `prompt.py:103-134`. 본 cycle 변경 없음.

#### `_forecast_one_group` — 그룹별 진단 ① ~ ⑧ (★ +73 LOC, 본 cycle 핵심)
- **위치**: `agent.py:73-280` (208 LOC, 분기 7+). 본 cycle 차분:
  - ① 집계: `today_qty_by_unit > 0` 인 unit 만 positive_units → main_unit 결정 (qty=0 unit 제외, agent.py:90).
  - ③ RAG: Chroma preflight count (agent.py:118) + cap=5 + try/except 2단 방어 (agent.py:130).
  - ④ assessment: plan_main_qty atomic distinct SUM (★ 6a89848, agent.py:156-164).
  - ⑤ compute_delay: `fetch_pg_actual_cum_qty` 우회 + `actual_cum_qty = pg_cum_qty + today_qty_main` 합산 (agent.py:185-186).
  - ⑥ LLM: cold start reasoning **4 분기** 텍스트 (main_unit None / plan None / plan_main_qty None / RAG <3 — agent.py:198-209). 이전 3 분기에서 1개 추가 (plan_main_qty None — unit 분류 불일치 분리).
  - ⑧ row 28 컬럼 (wa 추가, Phase 2).
- **설계 의도**: 8 단계 책임 분리. cold start 신호 명시화 (None assessment + reasoning 텍스트). v3.1 main_unit + today_conditions 필드 + Phase 2 wa 동기화.

#### `forecast` — entry + asyncio.gather (★ +24 LOC, 본 cycle 핵심)
- **위치**: `agent.py:283-339` (57 LOC). 본 cycle 차분:
  - sem closure 공유 (★ 6ba0126, agent.py:314).
  - asyncio.gather (agent.py:334-335).
  - work_content 빈 activity skip (agent.py:309-310, 이전 cycle PR #28).
  - wa 차원 group key (agent.py:311, 991c7dd Phase 2).
  - `pg.assert_pipeline_run_exists(run_id)` (agent.py:303) — fixture 미설정 silent no-op 방지.

---

## 이슈 표 (2026-05-26 cycle, deep_dive 9건 발견 반영)

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| 1 | mh 4 컬럼 (`plan_mh_per_day` / `expected_in_window_mh` / `actual_in_window_mh` / `mh_gap`) UI 미연동 — reference only | aggregate.py:75-80 docstring (bc04c94) | PG 저장만, KPI 미산출 | 의도적 (T18 docstring 명문화, 향후 mh-KPI 자산) |
| 2 | 9-22 outlier 잔존 — 동신패널 외장판넬 `plan=29,122 m2 vs today_qty=0.185 m2` (atomic 1행 only) | dummy seed 데이터 | `expected_completion = 2485-07-15` 류 비현실 값 가능 | 부분 해결 (★ 6a89848 산식 fix, 데이터 cleanse 별 task) |
| 3 | Chroma HNSW "ef or M too small" boundary case | agent.py:114-138 | Plan fallback graceful degrade. cap=5 + try/except 2단 방어 (cycle 8차 재발 후 보강) | mitigated |
| 4 | LLM cold start **4 분기** reasoning 텍스트 (main_unit None / plan None / plan_main_qty None / RAG <3) | agent.py:198-209 | None assessment 시 LLM skip + 텍스트 박음 | 의도적 (cold start 신호 보존, plan unit 불일치 케이스 분리) |
| 5 | Chroma `actual_cum_qty` 부정확 (광건 수장공사 22% 만 backfill) | aggregate.py:175-178 docstring | PG `fetch_pg_actual_cum_qty` 로 우회 — Chroma 반환값은 보조 reference | mitigated (split path) |
| 6 | `classify_assessment_plan` 의 `plan_mh_sum<=0` 또는 `plan_total_qty_main<=0` → "정상" 반환 | classify.py:52 | 방어이지만 위험 누락 가능 (Plan 데이터 누락 = 정상 위장) | 의도적 (cold start 처리), None 변경 검토 가능 |
| 7 | `aggregate_today_by_unit` 의 `today_assigned_workers = activities[0]["assigned_workers"]` group 내 동일 가정 | agent.py:88 + state.py:35 | spec 위반 시 silent 오차 | spec 옵션 X 채택 — `_prorate_mh` 이후 동일성 보장 |
| 8 | `expected_completion` None 시 `plan_finish` 로 대체 (PoC) | agent.py:275 | PG schema 영향 회피 | 의도적 (Phase 2 에 추세 외삽 예정) |
| 9 | synthetic.py 의 `random.seed default=42` | synthetic.py:86 | cold start 다양성 제한 | 의도적 (재현성) |

> 그 외 deep_dive 발견 항목은 `deep-dive/deep_dive_forecaster.md §16` 참조.

---

## 관찰

- **본 cycle 의 핵심 변화 3선**:
  1. `plan_main_qty` atomic distinct SUM (★ 6a89848) — 9-22 outlier 의 산식 root cause 해결 (잔존 outlier 는 seed 데이터 issue).
  2. `asyncio.gather + Semaphore 4×` (★ 6ba0126) — 10분 → 2.5분 (4× 병렬).
  3. `fetch_pg_actual_cum_qty` 우회 (★ aggregate.py:14) — Chroma backfill 불완전 회피, PG source of truth.
- **공용 모듈화**: `get_llm_semaphore()` (★ 1e24dc6) 가 forecaster + optimizer + atomizer 공통 cap. agent 별 sem 만들지 말 것.
- **mh / qty 산식 분리**: mh 4 컬럼은 reference only (UI 미연동 — 의도적). delay 산출은 qty 기반.
- **cold start 4 분기**: main_unit None / plan None / plan_main_qty None / RAG <3 — assessment=None 분기 명시화 (LLM skip + 텍스트 박음).
- **한자 사용 0건**: prompt.py SYSTEM_PROMPT + few-shot 모두 한글만.
- **TODO/NotImplementedError 0건**.

---

## 참고

- **Spec / Plan**:
  - `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` (§5 aggregate, §6 classify, §7 rerank, §8 prompt, §9 synthetic, §10 agent)
  - `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` (§2.3 WORK_HOURS 승격, v3.1 main_unit / today_conditions)
  - `docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md` (T1 / T4 / T18 round — 본 cycle 작업)
- **Pair docs**:
  - `deep-dive/deep_dive_forecaster.md` (544 줄 cycle baseline, 본 카드의 raw grounding)
  - `deep-dive/architecture_overview.md` (전체 LangGraph 흐름)
- **DB schema**:
  - `infra/postgres/init.sql:47-99` (forecasts 28 컬럼)
  - `infra/postgres/migrations/2026-05-16_forecaster.sql`, `2026-05-18_forecasts_wa.sql`
- **Tests**:
  - `pipeline/tests/forecaster/test_agent.py` / `test_aggregate.py` / `test_classify.py` / `test_forecaster_e2e.py` / `test_forecaster_integration.py` / `test_forecaster_wa_grain.py` / `test_prompt.py` / `test_rerank.py` / `test_synthetic.py`
  - `pipeline/tests/test_forecaster_concurrency.py` (★ 6ba0126 TDD)
