# Design Intent — forecaster

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Last checked**: 2026-05-20 (git SHA: `ef7c6cd`) — **코드 변경 없음** (cf3c143 이후 commit 0). T1/T2 카드 그대로 유효.
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/agents/forecaster/` 8 파일 (agent 279 / prompt 134 / classify 114 / rerank 50 / aggregate 119 / synthetic 189 / constants 8 / __init__ 8) + 9+ 테스트 — 합계 **893 LOC**
- **Note**: `classify.py:34` PM 원안 v2 정합 (저하 분류 의도) — drift #2 root cause 는 #3 input over-산출이었고 이미 해소됨.

Mapper 출력 + Chroma 유사 과거 일일 활동 retrieval → 공종별 생산성 진단 (정상/주의/이상). 임계값 hardcoding (RAG_NORMAL_BOUND=0.15, RAG_WARN_BOUND=0.25, PLAN_NORMAL_RATIO=0.85, PLAN_WARN_RATIO=0.65). PG `forecasts` 27 컬럼 INSERT. **audit drift #2 (assessment "정상" bias)** + **drift #3 (synthetic productivity_ratio bug)** 대상.

---

## T1 — Function Index

### agent.py
| Function/Class | File:Line | Signature | T2? |
|---|---|---|---|
| `ForecasterConfig` | agent.py:35 | `@dataclass` (Azure + DB + Chroma 설정) | — |
| `_format_chroma_result` | agent.py:53 | `(rag_result: dict) -> list[dict]` | — |
| `_forecast_one_group` | agent.py:67 | `async (company, l6_main, activities, run_id, today, pg, coll, azure, cfg) -> dict` | ✅ |
| `forecast` | agent.py:229 | `async (mapped, run_id, today, cfg) -> list[dict]` | ✅ |

### prompt.py
| Object | File:Line | Type | T2? |
|---|---|---|---|
| `SYSTEM_PROMPT` | prompt.py:12 | str (3 단계 reasoning) | — |
| `FEW_SHOT_MESSAGES` | prompt.py:93 | list[dict] (3 pair) | — |
| `build_llm_user_input` | prompt.py:103 | `(today, similar_cases, plan, assessment) -> dict` | ✅ |

### classify.py
| Function/Constant | File:Line | T2? |
|---|---|---|
| `RAG_NORMAL_BOUND = 0.15` | classify.py:19 | — |
| `RAG_WARN_BOUND = 0.25` | classify.py:20 | — |
| `PLAN_NORMAL_RATIO = 0.85` | classify.py:21 | — |
| `PLAN_WARN_RATIO = 0.65` | classify.py:22 | — |
| `classify_assessment_rag` | classify.py:27 | ✅ |
| `classify_assessment_plan` | classify.py:41 | ✅ |
| `classify_assessment` | classify.py:65 | ✅ |
| `classify_risk_level` | classify.py:83 | ✅ |

### rerank.py
| Function | File:Line | T2? |
|---|---|---|
| `_normalize_chroma_metadata` | rerank.py:20 | ✅ |
| `rerank_cases` | rerank.py:32 | ✅ |

### aggregate.py
| Function | File:Line | T2? |
|---|---|---|
| `aggregate_today_by_unit` | aggregate.py:14 | ✅ |
| `compute_delay` | aggregate.py:23 | ✅ |
| `fetch_chroma_actual` | aggregate.py:86 | ✅ |

### synthetic.py
| Function | File:Line | T2? |
|---|---|---|
| `generate_synthetic_day` | synthetic.py:21 | ✅ |
| `_main_cli` | synthetic.py:65 | — |

### constants.py / __init__.py
| Symbol | File:Line | Note |
|---|---|---|
| `WORK_HOURS_PER_DAY` | constants.py:8 | pipeline.constants 에서 re-export |
| `ForecasterConfig / forecast / WORK_HOURS_PER_DAY` | __init__.py:5-6 | 모듈 export |

---

## T2 — Issue Cards

### `classify_assessment` — RAG 우선 + Plan fallback + cold start (drift #2 핵심)

- **위치**: `pipeline/agents/forecaster/classify.py:65-81` (17 LOC, 분기 3)
- **시그니처**: `def classify_assessment(rag_n, today_prod, rag_avg_prod, plan_total_qty_main, plan_mh_sum) -> Optional[str]`
- **이슈**:
  - git log `44466c5` (optimizer/Task 10: Forecaster Minor 권고 정리 (docstring/literal/임계값 상수화/boundary epsilon))
  - git log `4f67343` (forecaster: classify.py — assessment + risk_level 룰)
  - docstring (classify.py:72-74): "RAG 우선 + Plan fallback + cold start. Spec §0.1 ②: rag_n >= 3 → RAG / else if plan 가용 → Plan / else None."
  - 메타: `docs/audit/2026-05-17-cpia-drift-backlog.md §2` — "Drift #2: assessment '정상' highly stable bias 가 Optimizer 약한 권고로 전파되는 핵심 사슬. 가설 A LLM prompt 선호 / 가설 B 결정론 코드 path / 가설 C input 자체."
- **설계 의도**:
  - 우선순위 명시: RAG (≥3건) > Plan fallback > cold_start (None).
  - cold_start 신호 보존: 두 path 모두 실패 시 None 반환 → 호출자 (`_forecast_one_group`) 가 reasoning="데이터 부족" 박음.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ④ 단계
  - 입력: rag_n + today_prod + rag_avg + plan_total_qty_main + plan_mh_sum
  - 처리: rag_n>=3 → RAG / plan_mh_sum>0 AND plan_total_qty_main → Plan / 그 외 None
  - 출력: "정상" | "주의" | "이상" | None
- **관련**:
  - `classify_assessment_rag` (classify.py:27)
  - `classify_assessment_plan` (classify.py:41)
  - `_forecast_one_group` (agent.py:67)
  - 테스트: `test_classify.py:16-92` (8 케이스: rag normal/caution/risk/boundary + plan fallback 4 + cold_start)
- **Suspected related** (2026-05-17 stale):
  - audit drift #2 — 본 함수가 진단 결정 path 의 routing 책임. 가설 검증 entry point.

---

### `classify_assessment_rag` — RAG 임계값 (±15% / ±25%)

- **위치**: `pipeline/agents/forecaster/classify.py:27-39` (13 LOC, 분기 2)
- **시그니처**: `def classify_assessment_rag(today_prod: float, rag_avg_prod: float) -> str`
- **이슈**:
  - 임계 상수: `RAG_NORMAL_BOUND=0.15`, `RAG_WARN_BOUND=0.25` (classify.py:19-20).
  - 보호 코드 (`classify_assessment_rag`): `rag_avg_prod == 0 → return "정상"` 의 edge case 처리. boundary epsilon `eps=1e-9`.
- **설계 의도**:
  - 상대 비교: delta = (today − rag_avg) / rag_avg → ±15% 이내 정상 / ±25% 이내 주의 / 외 이상.
  - rag_avg=0 edge → "정상" (의도된 fallback, 0 으로 나누기 방지).
  - boundary epsilon: float 비교 안정성 (test_classify_assessment_rag_boundary_epsilon 검증).
- **대응 패턴**:
  - 발동: `classify_assessment` rag_n≥3 path
  - 입력: today_prod + rag_avg
  - 처리: delta 산출 → 임계값 비교
  - 출력: 정상/주의/이상
- **관련**:
  - 테스트: `test_classify.py:16-46` (normal/caution/risk/boundary 4 케이스 + boundary_epsilon)
- **Suspected related** (2026-05-17 stale):
  - drift #2 가설 B (임계값 정합): 0.15/0.25 가 현 데이터에 비해 보수적일 가능성 — 임계값 조정 후보.

---

### `classify_assessment_plan` — Plan ratio 임계 (0.85/0.65)

- **위치**: `pipeline/agents/forecaster/classify.py:41-63` (23 LOC, 분기 3)
- **시그니처**: `def classify_assessment_plan(today_prod, plan_total_qty_main, plan_mh_sum) -> str`
- **이슈**:
  - 임계 상수: `PLAN_NORMAL_RATIO=0.85`, `PLAN_WARN_RATIO=0.65`.
  - 식: `plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / WORK_HOURS_PER_DAY)`, `ratio = today_prod / plan_prod_proxy`.
- **설계 의도**:
  - RAG <3건 일 때 plan 기준 fallback. 일일 평균 생산성 (plan_total_qty / 공정일수) 대비 today 비율로 판정.
  - 0.85 normal threshold — 의도적으로 보수적 (15% 부족까지 정상).
- **대응 패턴**:
  - 발동: `classify_assessment` plan path
  - 입력: today_prod + plan_total_qty_main + plan_mh_sum
  - 처리: plan_prod_proxy 계산 → ratio 임계값 비교
  - 출력: 정상/주의/이상
- **관련**:
  - `WORK_HOURS_PER_DAY` (constants.py)
  - 테스트: `test_classify.py:49-92` (fallback normal/caution/risk 3 + cold_start)
- **Suspected related** (2026-05-17 stale):
  - drift #2 가설 B: 0.85 ratio 가 너무 관대 (정상 bias 의 source) — 회귀 후 조정 권고.

---

### `classify_risk_level` — hybrid 룰 (assessment + recovery + delay + state)

- **위치**: `pipeline/agents/forecaster/classify.py:83-115` (33 LOC, 분기 6)
- **시그니처**: `def classify_risk_level(assessment, recovery_likelihood, delay_days, schedule_state) -> Optional[str]`
- **이슈**:
  - docstring: "hybrid 룰 — assessment + recovery + delay + state. 임계 DELAY_DAYS_BOUND·RECOVERY_LIKELIHOOD_BOUND = 가정값 (회귀 후 조정)."
  - 임계 상수 (classify.py:23-24): `DELAY_DAYS_BOUND=5`, `RECOVERY_LIKELIHOOD_BOUND=0.7`.
  - hard rule: `schedule_state=="post_due"` → "이상" 강제.
  - 9 테스트 케이스 (test_classify.py:95-148) — boundary 모두 검증.
- **설계 의도**:
  - assessment 만으로 부족한 위험도 보정: `delay_days` (공정 지연) + `recovery_likelihood` (회복 가능성) 결합.
  - post_due 무조건 이상: 공정 마감 지난 작업은 어떤 assessment 든 이상.
  - 회복 가능 시 등급 강하: 주의 + recovery≥0.7 + delay≤5 → 주의 유지 (악화 방지). 회복 불가 시 → 이상 승격.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑦ 단계
  - 입력: assessment + recovery_likelihood (LLM 출력) + delay_days + schedule_state
  - 처리: post_due 우선 → unknown 우회 → 4 단계 룰
  - 출력: 정상/주의/이상 | None
- **관련**:
  - `_forecast_one_group:182` (호출자)
  - 테스트: `test_classify.py:95-148` (9 케이스)
- **Suspected related** (2026-05-17 stale):
  - DELAY_DAYS_BOUND=5 vs PM 원안 v2 "D+3" — 변형 흔적.
  - RECOVERY_LIKELIHOOD_BOUND=0.7 vs PM 원안 v2 "80% 회복" — conservative 편차.

---

### `compute_delay` — 누적 mh window 비교 + schedule_state

- **위치**: `pipeline/agents/forecaster/aggregate.py:23-84` (62 LOC, 분기 4)
- **시그니처**: `def compute_delay(plan, today, actual_window_start, actual_cum_mh) -> dict[str, Any]`
- **이슈**:
  - docstring (aggregate.py:23-41): "누적 mh window 비교 — 사용자 개념. plan 미등록 시 unknown. plan_mh_per_day = plan_mh_sum / 공정_기간_일수. expected_in_w = window_days × plan_mh_per_day. mh_gap = expected - actual (양수 = 부족). delay_days = mh_gap / plan_mh_per_day. schedule_state: plan 없음 → unknown / today < plan_start → early / 사이 → on_schedule / 초과 → post_due."
  - 인라인: reviewer #11 (total_days=1 division by zero 방어), reviewer #12 (Activity schema l5_disc 필드 추가).
- **설계 의도**:
  - 사용자 개념: window (Chroma min date ~ today) 안의 실제 mh 누적 vs 기대치 비교 — Plan 절대값 비교가 아닌 window 상대.
  - schedule_state 4 enum 명시 (unknown/early/on_schedule/post_due) — classify_risk_level 입력.
  - delay_days 음수 = ahead (recovery 여유).
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑤ 단계
  - 입력: plan dict + today date + actual_window_start + actual_cum_mh
  - 처리: plan_mh_per_day 산출 → window 비교 → schedule_state 결정
  - 출력: `{schedule_state, window_start, window_days, expected_in_window_mh, actual_in_window_mh, mh_gap, delay_days}`
- **관련**:
  - `fetch_chroma_actual` (aggregate.py:86) — actual_window_start / actual_cum_mh 산출
  - 테스트: `test_aggregate.py:106-262` (7 케이스: on_schedule_behind / early / post_due / unknown / ahead / zero_total_days / plan_mh_zero)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `fetch_chroma_actual` — Chroma 과거 누적 mh (reviewer #5 정정)

- **위치**: `pipeline/agents/forecaster/aggregate.py:86-120` (35 LOC, 분기 3)
- **시그니처**: `def fetch_chroma_actual(coll, company, l6_main, today, today_assigned_workers) -> tuple[Optional[date], float]`
- **이슈**:
  - docstring (aggregate.py:93-99): "Chroma daily_activities 에서 (company, l6_main) date 별 unique workers 추출. Spec §5.4 정합 — reviewer #5 정정. return: (actual_window_start, actual_cum_mh). Chroma 에 과거 row 없음 (오늘만) → (None, today_workers × WORK_HOURS_PER_DAY). Chroma 에 과거 row 있음 → (min(Chroma date), Σ unique date workers × WORK_HOURS_PER_DAY)."
- **설계 의도**:
  - reviewer #5 정정 흔적: window_start 는 과거만 (오늘 제외), 누적 mh 는 오늘 포함 — 두 개념 분리.
  - unique date workers: 같은 date 의 여러 row 가 BP사 합산되어 있으므로 max 또는 sum 정책 명시 필요.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑤ 단계 (compute_delay 직전)
  - 입력: Chroma collection + company + l6_main + today + today_assigned_workers
  - 처리: Chroma where 필터 → metadatas iterate → date 별 workers max → window_start + cum_mh
  - 출력: (window_start | None, cum_mh)
- **관련**:
  - `compute_delay` (호출자)
  - 테스트: `test_aggregate.py:205-220` (with_data + empty 2 케이스)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_forecast_one_group` — 그룹별 진단 ① ~ ⑧

- **위치**: `pipeline/agents/forecaster/agent.py:67-227` (161 LOC, 분기 5+)
- **시그니처**: `async def _forecast_one_group(company, l6_main, activities, run_id, today, pg, coll, azure, cfg) -> dict[str, Any]`
- **이슈**:
  - git log `d920c85` (optimizer/Task 1: state.py 3 필드 + Forecaster row 2 필드 (main_unit + today_conditions) + Forecaster spec §3/§10 drift 동기화 (v3.1))
  - git log `3d34d54` (forecaster: agent.py + PGClient.insert_forecast — Forecaster entry)
  - docstring: "1 (company, l6_main) group 처리. Spec §1 ① ~ ⑧."
  - 단계별 주석 (agent.py:81-226): "① aggregate / ② Plan fetch / ③ RAG search / ④ assessment / ⑤ compute_delay / ⑥ LLM call + cold start paths / ⑦ risk_level / ⑧ row construction".
  - cold_start reasoning 3 경로 (agent.py:144-155): main_unit=None / plan=None / plan_main_qty=None (unit 분류 불일치) / RAG <3건 fallback.
  - v3.1 신규 필드 (agent.py:224-225): `main_unit` + `today_conditions`.
- **설계 의도**:
  - 8 단계 책임 분리. 각 단계 spec §1 1:1 매핑.
  - cold_start 명시적 분기 — None assessment 일 때 reasoning 3종 + LLM skip.
  - v3.1 동기화: state.py + spec §3/§10 + postgres.md + 본 함수의 row 조립 모두 함께 변경 (drift 회피).
- **대응 패턴**:
  - 발동: `forecast` 가 그룹별 호출
  - 입력: 그룹 activities + cfg + share (pg, coll, azure)
  - 처리: 8 단계 순차
  - 출력: forecast row dict (27 필드)
- **관련**:
  - `aggregate_today_by_unit / compute_delay / fetch_chroma_actual / classify_* / build_llm_user_input` 모두 호출
  - `db.py:insert_forecast`
  - 테스트: `test_agent.py:62 test_forecast_row_has_main_unit_and_today_conditions` (v3.1 신규 필드)
  - 페어 spec: `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §1`
- **Suspected related** (2026-05-17 stale):
  - audit drift #2 — 본 함수의 ④ 단계 (classify_assessment) 결과가 Optimizer 로 전파.

---

### `forecast` — Forecaster 그룹 fan-out entry

- **위치**: `pipeline/agents/forecaster/agent.py:229-276` (48 LOC, 분기 2)
- **시그니처**: `async def forecast(mapped, run_id, today, cfg) -> list[dict]`
- **이슈**:
  - 단순 entry: 그룹 분할 → `_forecast_one_group` 순차 호출 → PG insert.
- **설계 의도**:
  - 그룹 분할 책임 단일화: (company, l6_main) 키로 mapped 그룹화.
  - 동일 resource (pg, coll, azure) 를 그룹 호출 간 공유 (connection 재사용).
- **대응 패턴**:
  - 발동: `graph.py:forecaster_node` 호출
  - 입력: mapped list + run_id + today + ForecasterConfig
  - 처리: 그룹화 → 그룹별 처리 → PG insert
  - 출력: forecast row list
- **관련**:
  - `graph.py:forecaster_node:64`
  - 테스트: `test_forecaster_e2e.py` (slow)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `rerank_cases` — worker_source / mapping_conf 가중치

- **위치**: `pipeline/agents/forecaster/rerank.py:32-51` (20 LOC, 분기 2)
- **시그니처**: `def rerank_cases(cases: list[dict]) -> list[dict]`
- **이슈**:
  - docstring: "Chroma query 결과 → 정규화 + rerank. 가중치: worker_source = 'user_corrected' → distance × 0.7 / mapping_conf < 0.7 → distance × 1.5. 정렬 후 전체 반환. caller (agent.py) 가 [:rag_top_k] 자름."
- **설계 의도**:
  - 신뢰도 가중: HIL 1 통과 row (`user_corrected`) 우대 + 매핑 신뢰도 낮은 row 페널티.
  - cut 책임 분리: 자르기는 caller 책임 (rerank 자체는 전체 정렬만).
- **대응 패턴**:
  - 발동: `_forecast_one_group` ③ RAG search 단계
  - 입력: Chroma result 가 들어간 dict list
  - 처리: 정규화 → 가중치 distance 재계산 → 정렬
  - 출력: 정렬된 list
- **관련**:
  - `_normalize_chroma_metadata` (rerank.py:20)
  - 테스트: `test_rerank.py` (11 케이스: user_corrected priority / low_mapping_conf demoted / combined / boundary 등)
- **Suspected related** (2026-05-17 stale):
  - HIL 1 미구현 — `worker_source="user_corrected"` row 가 현재 데이터에 없음 (생성되지 않음). 활성 시 본 가중치 발동.

---

### `_normalize_chroma_metadata` — atomizer schema → Forecaster schema

- **위치**: `pipeline/agents/forecaster/rerank.py:20-30` (11 LOC)
- **시그니처**: `def _normalize_chroma_metadata(m: dict) -> dict`
- **이슈**:
  - 변환: today_qty / assigned_workers → productivity 산출, conditions CSV → list[str] 복원.
- **설계 의도**:
  - atomizer 의 CSV 평탄화 (`_build_metadata`) 를 역정규화. `conditions in` 검사가 list 기반.
  - productivity 즉시 계산하여 rerank 가 사용 가능하게.
- **대응 패턴**:
  - 발동: `rerank_cases` 내부
  - 입력: Chroma metadata dict (CSV 형식)
  - 처리: 산술 + split
  - 출력: 정규화 dict
- **관련**:
  - `atomizer.py:_build_metadata:45` (CSV 평탄화 source)
  - 테스트: `test_rerank.py` (5 normalize 케이스)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `aggregate_today_by_unit` — unit별 today_qty Σ

- **위치**: `pipeline/agents/forecaster/aggregate.py:14-21` (8 LOC, 분기 1)
- **시그니처**: `def aggregate_today_by_unit(activities) -> dict[str, float]`
- **이슈**:
  - 단순 reduce: defaultdict[float] 으로 unit 별 합산.
- **설계 의도**:
  - main_unit (positive_units 중 max qty) 산출 사전 작업.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ① 단계
  - 입력: activities list
  - 처리: unit 별 today_qty 합
  - 출력: `{unit: total}` dict
- **관련**:
  - 테스트: `test_aggregate.py` (3 케이스)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `generate_synthetic_day` — 변동 패턴 1일 (drift #3 관련)

- **위치**: `pipeline/agents/forecaster/synthetic.py:21-63` (43 LOC, 분기 3)
- **시그니처**: `def generate_synthetic_day(base_row, day_offset, weather, incident, reference_date=None) -> dict`
- **이슈**:
  - 파일 docstring (synthetic.py:5-9): "PM 원안 v2 §3-B 변동 패턴: weather='우천' → today_qty × (1 - random[0.15, 0.25]) / incident='장비대기' → × (1 - random[0.20, 0.35]) / incident='자재미입고' → × (1 - random[0.10, 0.20]) / 기본 변동 → × (1 + random[-0.05, 0.05])."
  - 인라인 (synthetic.py:45): `today_qty × (1 + delta)` — 곱셈 1회.
- **설계 의도**:
  - PM 원안 v2 패턴 코드화: 4종 변동 (정상 ±5% / 우천 -15~25% / 장비대기 -20~35% / 자재미입고 -10~20%).
  - 결정성 (seed): test_generate_seed_reproducible 검증.
  - atomizer schema 호환: metadata 필드 동일 (test_generate_metadata_atomizer_schema_match).
- **대응 패턴**:
  - 발동: `_main_cli` 또는 test 가 day_offset 별 호출
  - 입력: base_row + day_offset + weather + incident + reference_date
  - 처리: incident 별 delta 계산 → today_qty 변동
  - 출력: synthetic row dict
- **관련**:
  - `_main_cli` (synthetic.py:65)
  - 테스트: `test_synthetic.py:31-87` (clear/rainy/equipment/seed/schema_match/offset 6 케이스)
- **Suspected related** (2026-05-17 stale):
  - audit drift #3 — `synthetic_daily_report.py:generate_fake_daily_report` 와 별개. 본 함수는 Phase 1 dummy 30일 적재용.
  - 두 synthetic path 통합 권고 (drift D-2).

---

### `build_llm_user_input` — LLM 입력 JSON 구조화

- **위치**: `pipeline/agents/forecaster/prompt.py:103-134` (32 LOC)
- **시그니처**: `def build_llm_user_input(today, similar_cases, plan, assessment) -> dict`
- **이슈**:
  - reviewer #8: ensure_ascii=False 한글 출력.
  - 메타: prompt.py 의 SYSTEM_PROMPT (라인 12-91) 가 본 user input 구조와 짝.
- **설계 의도**:
  - LLM 입력 schema 명시화 — JSON dict 로 today/similar/plan/assessment 분리.
  - LLM 출력 reasoning + recovery_likelihood 두 필드만 책임 (assessment 는 코드 산출).
- **대응 패턴**:
  - 발동: `_forecast_one_group` ⑥ 단계
  - 입력: 4 dict
  - 처리: 평탄화 + ensure_ascii=False
  - 출력: LLM user message JSON
- **관련**:
  - 테스트: `test_prompt.py` (2 케이스)
- **Suspected related** (2026-05-17 stale): 없음.

---

## 관찰

- **audit drift 핵심**: classify_assessment / classify_assessment_rag / classify_assessment_plan 의 임계값 (0.15/0.25/0.85/0.65) 이 drift #2 의 가설 B (임계값 정합) 검증 대상.
- **cold_start 2 path**: `synthetic.py:_main_cli` (Phase 1 dummy 30일) + `atomizer.py:atomize` (실 데이터) — 통합 권고 (drift D-2).
- **한자 사용 0건**: prompt.py SYSTEM_PROMPT + few-shot 모두 한글만.
- **TODO/NotImplementedError 0건**.
- **테스트 커버리지**: 72 케이스 (classify 21 + aggregate 10 + rerank 13 + synthetic 6 + prompt 2 + agent 1 + e2e + integration).

---

## 2026-05-19 FE↔BE 연결 + 6 BE 적재 보완 cycle 변경 (Git SHA cf3c143)

### T1 갱신

- `forecast` (agent.py:229) — group 빌드 단계에서 "work_content 빈 activity skip": `if not a.get("work_content"): continue` (agent.py:255). 빈 work_content 만 모인 group 의 빈 embedding 호출 회피.
- `_forecast_one_group` (agent.py:67) — "work_content / conditions None 안전 처리":
  - agent.py:91 `work_content = " / ".join(set(a["work_content"] for a in activities if a.get("work_content")))[:200]` (빈 활동 필터 + 200 자 cut).
  - agent.py:92 `conditions_set = sorted(set(c for a in activities for c in (a.get("conditions") or [])))` (None 빈 list fallback).

### T2 신규 카드

#### F-N1: work_content 빈 activity / group skip

- **위치**: `pipeline/agents/forecaster/agent.py:255` (forecast group 빌드 라인) + agent.py:91 (group 안 work_content 합치기 단계)
- **변경 라인**:
  - `forecast` (agent.py:251-258): group key 산출 직전 `if not a.get("work_content"): continue`.
  - `_forecast_one_group` (agent.py:91): `" / ".join(set(... if a.get("work_content")))`.
- **이슈**:
  - 본 cycle 신규 (PR #28, 2026-05-19) — 이전 코드는 a["work_content"] 가 None / "" 인 activity 도 group 에 포함. work_content 가 모두 None 인 group → 합쳐진 work_content="" → `azure.embeddings.create(input=[""])` HTTP 400.
  - atomizer A-N1 과 동일한 빈 입력 문제. 이중 안전망 (atomizer 에서 1차 제거 + forecaster 에서 2차 제거).
- **설계 의도**:
  - Azure embedding pre-call guard — 빈 input 회피.
  - 2 단계 필터: ① group 빌드 시 빈 work_content activity 자체 제외 (`forecast` 안), ② group 안에서 합치기 시 truthy 만 join (`_forecast_one_group` 안). ② 가 ① 의 안전망 (방어적).
  - work_content="" 인 group 이 entirely empty → group dict 에 key 추가 안 됨 → embedding 호출 자체 안 일어남.
- **대응 패턴**:
  - 발동: `forecast` 의 mapped iterate 단계 (agent.py:252).
  - 입력: mapped Activity list.
  - 처리: l6_main not None + work_content truthy 모두 통과한 row 만 group 진입.
  - 출력: 빈 work_content group 0 개 (downstream 안전).
- **관련**:
  - atomizer A-N1 (atomizer.py:69) — 자매 가드 (이중 안전망).
  - 실 검증: run_id=627e2c4d (2026-05-19) 에서 forecasts=4 정상 생성.
- **Suspected related** (2026-05-19 stale):
  - parser LLM 의 work_content 누락 자체는 mapper drift — 별 cycle.

#### F-N2: conditions None 안전 처리

- **위치**: `pipeline/agents/forecaster/agent.py:92`
- **변경 라인**: `conditions_set = sorted(set(c for a in activities for c in (a.get("conditions") or [])))`
- **이슈**:
  - 본 cycle 신규 (PR #28, 2026-05-19) — 이전 코드는 `a["conditions"]` 직접 접근 → mapper 가 conditions 키 누락한 경우 KeyError. atomizer A-N2 와 정확히 동일 패턴.
- **설계 의도**:
  - 방어적 dict 접근: `.get("conditions") or []` — None / 누락 모두 빈 list fallback.
  - atomizer A-N2 와 정합 — 동일한 mapper drift 에 대해 atomizer / forecaster 양쪽에 같은 가드 (방어적 일관성).
  - 결과 `conditions_set` 는 sorted set → forecast row 의 `today_conditions` CSV 필드 (agent.py:225) source.
- **대응 패턴**:
  - 발동: `_forecast_one_group` ① 집계 단계 (agent.py:92).
  - 입력: group 의 activities list.
  - 처리: 각 activity 의 conditions (없으면 [])  → flatten → set → sorted list.
  - 출력: conditions_set (이후 today_conditions / similar_cases conditions 비교에 사용).
- **관련**:
  - atomizer A-N2 (atomizer.py:58) — 동일 패턴.
  - forecast row 27 컬럼의 today_conditions (db.py:insert_forecast 의 main_unit + today_conditions 쌍).
  - mapper.py — conditions 누락 path (drift, 별 cycle).
- **Suspected related** (2026-05-19 stale):
  - mapper 의 conditions 누락 자체는 mapper drift backlog 별도 cycle.
