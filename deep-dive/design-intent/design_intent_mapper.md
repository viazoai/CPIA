# Design Intent — mapper

- **Generated**: 2026-05-20 (resolve_wa 7단계 확대 + shift-weighted MH + BP-별 컨텍스트 cycle)
- **Last checked**: 2026-05-26 (`1ba783f` — l7.5 4 컬럼 propagate cycle stamp)
- **Git SHA**: `1ba783f` (A_Track HEAD, branch A_Track) — baseline `ef7c6cd` (2026-05-20)
- **Pair file**:
  - `../deep_dive_mapper.md` (610 줄 전수 walk-through, 2026-05-26)
  - `../architecture_overview.md`
- **Range**:
  - `pipeline/agents/mapper.py` (604 LOC, baseline 571 → +33 LOC, 미세 시그니처 변경)
  - `pipeline/db.py:insert_mapper_activities_batch` (33 → 37 컬럼, commit `d40c84f`)
  - `infra/postgres/migrations/2026-05-23_mapper_l7_5_columns.sql` (8 LOC, 신규)
  - `pipeline/tests/test_mapper_resolve_wa.py` (10 case)
  - `pipeline/tests/test_mapper_weighted_mh.py` (7 case)
  - `pipeline/tests/test_mapper_alternatives.py`, `test_mapper_company_normalize.py`, `test_mapper_helpers.py`, `test_mapper_u1a.py`, `test_mapper_u1b.py`, `test_mapper_golden.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md` (resolve_wa 7단계 + bp_context 분리)
  - `docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md` (shift-weighted MH)

Parser 출력 Activity 를 WBS 매핑. **6단계 흐름 (BP filter → 임베딩 → Chroma top-K → LLM rerank → 분류 → WA 결정 7단계)**. `resolve_wa` 가 이전 5단계 (0+1+2+3+4) 에서 **7단계 (0~6)** 로 확대 — 신규 source 2종: `auto_bp_zone_match` (BP-zone deterministic, fix C) + `auto_llm_rerank` (LLM rerank fallback, 옵션 A). 사용자 push back 3개 정합 ("scope ≠ wa", "시트1 에서 FAB/CUB 알 수 있음", "오른쪽 작업으로 wa 판단"). `_weighted_mh_from_shift` + `_prorate_workers_with_mh` 신규 — 8h 고정 → 시간대 가중 MH (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12, 산업안전공단 근거). `build_bp_context` 가 BP 코드별 분리 (이전: 회사 단위 집계). **2026-05-23 cycle (d40c84f)**: `mapper_activities` 에 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가, PoC 단계엔 대부분 None (Master List 1:N 제약, M-2 참조).

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_WBS_MASTER_CACHE` | mapper.py:30 | `dict[tuple, Any]` | Chroma collection singleton cache (key = (host, port, ssl)) | — |
| `_WBS_MASTER_LOCK` | mapper.py:31 | `asyncio.Lock` | singleton init 경쟁 회피 | — |
| `_get_wbs_master_coll` | mapper.py:34 | `async (cfg: MapperConfig) -> Any` | wbs_master collection singleton getter (2026-05-20 hang fix) | — |
| `_SHIFT_WEIGHTS` | mapper.py:52 | `dict[str, float]` | 시간대 가중치 상수 (조출 2/주간 8/연장 4/야간 8/철야 12) | — |
| `_weighted_mh_from_shift` | mapper.py:61 | `(shift_dict: dict\|None) -> float` | TimeShiftCounts → 가중 MH 환산 | ✅ |
| `_prorate_workers_with_mh` | mapper.py:72 | `(mapped, parsed_report, company_total_plan_mh, active_l6_for_company) -> list[dict]` | company 단위 시간대 가중 MH → l6 비례 분배 | ✅ |
| `_TRADE_KEYWORDS` | mapper.py:119 | `tuple[str, ...]` | 기능공 직종 keyword (20개) | — |
| `_MGR_KEYWORDS` | mapper.py:141 | `tuple[str, ...]` | 관리자/감독 keyword (12개) | — |
| `_NOISE_KEYWORDS` | mapper.py:155 | `tuple[str, ...]` | 소계 row 판별 keyword (2개) | — |
| `_is_trade_job` | mapper.py:158 | `(job: str) -> bool` | 시트2 직종 noise 필터 | ✅ |
| `WAResolution` | mapper.py:167 | `@dataclass(frozen=True)` | WA 결정 결과 (value + 7 source Literal) | — |
| `build_embedding_input` | mapper.py:183 | `(activity: Activity) -> str` | 임베딩용 input (회사/작업/단위/공종, 숫자 제외) | ✅ |
| `build_bp_context` | mapper.py:196 | `(company: str, parsed_report) -> str` | BP 코드별 분리 컨텍스트 (시트1+2+3 join) | ✅ |
| `build_llm_input` | mapper.py:255 | `(activity: Activity, parsed_report) -> str` | LLM 분류용 풍부 input (embedding + bp_context + bp_code) | ✅ |
| `resolve_wa` | mapper.py:272 | `(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution` | **WA 결정 7단계 (0:auto_chroma_top1 / 1:auto_bp_zone_match / 2:auto_llm_rerank / 3:auto_bp_single / 4:auto_l6_single / 5:auto_sheet1_text / 6:hil_required)** | ✅ |
| `_select_top_k_alternatives` | mapper.py:336 | `(candidates: list[dict], k: int=3) -> list[dict]` | RAG candidate score 상위 K (FE dropdown 용 alternatives jsonb) | ✅ |
| `MapperConfig` | mapper.py:347 | `@dataclass` | Mapper config (Azure endpoint / Chroma / PG URL / conf_threshold) | — |
| `map_activity` | mapper.py:365 | `async (activity, parsed_report, cfg, bp_cand_lookup=None) -> Activity` | 6단계 통합 흐름 (BP filter → 임베딩 → Chroma → LLM → WA 결정) | ✅ |
| `_prorate_mh` | mapper.py:529 | `async (mapped, parsed_report, pg) -> list[Activity]` | (company, l6_main) 단위 인원 분배 + plan_mh propagate (U1.A/B) | ✅ |
| `insert_mapper_activities_batch` | db.py:639 | `async (run_id, report_date, activities: list[Activity]) -> None` | mapper_activities 37 컬럼 INSERT + ON CONFLICT UPDATE (멱등) | ✅ (신규) |

LOC delta: baseline 571 → HEAD 604 (+33 LOC). 본 cycle 자체 신규 commit `d40c84f` 는 db.py 와 migration 만 변경, mapper.py 33 LOC 증분은 baseline 직전 cycle 의 코멘트 정리 + `asyncio.to_thread` wrap 보강.

---

## T2 — Issue Cards

### `resolve_wa` — WA 결정 7단계 (주력)

- **위치**: `pipeline/agents/mapper.py:272-333` (62 LOC)
- **시그니처**: `def resolve_wa(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution`
- **Last checked**: 2026-05-26 (stamp only — 7단계 ladder 변경 없음)
- **이슈**:
  - git log: `dc69f14 feat(mapper): build_bp_context BP 별 분리 + resolve_wa auto_bp_zone_match + auto_llm_rerank` (2026-05-20)
  - git log: `787575b test(mapper): resolve_wa 7 단계 unit test 신설` (2026-05-20, 10 case)
  - 사용자 push back (spec §0.3):
    - "scope ≠ wa, 오른쪽 작업으로 wa 판단" → 옵션 A (auto_llm_rerank)
    - "soft hint = 1번 시트에서 FAB / CUB 알 수 있음" → fix C (auto_bp_zone_match)
    - "work_text 기반 판단 신뢰" → step 2 fallback
  - **목표**: hil_required 58% → 25% 이내 (spec §0.2). full cycle 5 (POC 3사) 에서 1.4% 측정, V3 (146 case) 검증 pending
- **설계 의도**:
  - 이전 5단계 (0+1+2+3+4) → 7단계 (0~6) 확대
  - **신규 step 1 `auto_bp_zone_match`** (deterministic + LLM override):
    - 조건: `activity.bp_code == BPSummary.bp_code && BPSummary.zone in cand_wa_set`
    - 동작: BPSummary.zone 그대로 채택 (LLM 선택과 무관 deterministic)
    - 근거: 사용자 "시트1 에서 FAB/CUB 알 수 있음"
    - **conf 무관 → requires_review=False**
    - full cycle 5 (844d4c3) 실측: mapping_source `auto_bp_zone_match` 74% — 가장 흔한 source
  - **신규 step 2 `auto_llm_rerank`** (fallback when BP-zone fail):
    - 조건: `chosen_wa && (chosen_wa, l6_choice) in cand_pool`
    - 동작: LLM 이 선택한 (wa, l6) 채택
    - 근거: 사용자 "scope ≠ wa, 오른쪽 작업으로 wa 판단"
  - `WAResolution.source` Literal 4종 → 7종 확대
- **대응 패턴**:
  - 입력: activity, l6_choice (LLM 선택), cand_pool: list[(wa, l6_main)], parsed_report, chosen_wa
  - 처리: 7-step ladder (조건 매칭 시 즉시 return)
    - **step 0** `auto_chroma_top1` (cand_pool 빈 시, BP 미등록 BP사) — Task 4, mapper.py:286-287
    - **step 1** `auto_bp_zone_match` (BP-zone deterministic) — fix C, mapper.py:294-299
    - **step 2** `auto_llm_rerank` (LLM rerank fallback) — 옵션 A, mapper.py:304-305
    - **step 3** `auto_bp_single` (BP scope WA 단일) — legacy, mapper.py:308-310
    - **step 4** `auto_l6_single` (L6 결정 후 wa 단일) — legacy, mapper.py:313-315
    - **step 5** `auto_sheet1_text` (회사 단위 zone 교집합) — legacy, mapper.py:321-330
    - **step 6** `hil_required` (모든 조건 실패) — mapper.py:333
  - 출력: WAResolution(value=str|None, source=Literal[7종])
- **관련**:
  - 호출자: `map_activity` (mapper.py:507) step 6 — `requires_review = (confidence < cfg.conf_threshold) or (wa_result.source == "hil_required")` (mapper.py:515)
  - 테스트: `test_mapper_resolve_wa.py` 10 case (각 단계별 트리거 + skip + fallback)
  - 페어 함수: `build_bp_context` (BP-별 분리, 본 함수 의 LLM input 강화)
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:196) — step 1 deterministic 의 LLM 신뢰도 보강
  - graph.py:67~68 — fetch_bp_candidates 전 정규화 (cand_pool 빈 케이스 root cause)

---

### `_weighted_mh_from_shift` — 시간대 가중 MH 환산

- **위치**: `pipeline/agents/mapper.py:61-69` (9 LOC)
- **시그니처**: `def _weighted_mh_from_shift(shift_dict: dict | None) -> float`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - git log: `8089e7a mapper: replace 8h fixed prorate with shift-weighted MH` (2026-05-16)
  - docstring (mapper.py:62-66): "시트2 workers_today_cum jsonb (TimeShiftCounts) → 가중 MH. spec §3.2 가중치 (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12) 적용. None / 빈 dict / 키 누락 → 0.0 처리."
  - spec `2026-05-19-cpia-reports-parser-mh-design.md` §3 — EVM CPI = EV/AC 분모 정합
- **설계 의도**:
  - 이전: `cum_workers_today × 8.0` (daily total) — AC 분모 과소 → CPI 폭주
  - 변경: `Σ(shift_dict[k] × weight_k)` — 실 누적 인공 (man-hour)
  - 가중치 근거: 산업안전공단 표준 — 조출 (06:00~08:00 2h) / 주간 (표준 8h) / 연장 (17:00~21:00 4h) / 야간 (22:00~06:00 8h) / 철야 (12h 연속)
  - `total` 키는 가중치 sum 에서 무시 (Parser 가 채워둔 sanity check 용)
- **대응 패턴**:
  - 입력: TimeShiftCounts dict (morning/daytime/overtime/night/all_night/total)
  - 처리: 5-key weighted sum (total 키 무시)
  - 출력: float MH
- **관련**:
  - 호출자: `_prorate_workers_with_mh` (mapper.py:88) — 유일한 caller, l6 비례 분배 input
  - 테스트: `test_mapper_weighted_mh.py` 7 case (daytime/mixed/all_night/morning_overtime/None/empty/missing_keys)
- **Suspected related** (2026-05-16):
  - `_prorate_workers_with_mh` — 본 함수의 유일한 caller
  - state.py `TimeShiftCounts` (line 17) — 본 함수의 input 스키마

---

### `_prorate_workers_with_mh` — U1.A/B 알고리즘

- **위치**: `pipeline/agents/mapper.py:72-115` (44 LOC)
- **시그니처**: `def _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company) -> list[dict]`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - git log: `8089e7a mapper: replace 8h fixed prorate with shift-weighted MH` (2026-05-16, 신규)
  - mapper_activities.cum_actual_mh_today 의미 변경: "daily 인원수" → "누적 가중 MH"
  - 4cd36e3: U1.B cum_workers prorate (plan_mh 비율) + uniform fallback
- **설계 의도**:
  - 시트2 기능공 인원 → 시트4 activity 의 (company, l6_main) 단위 분배
  - 3 fallback path:
    - **plan_mh 비례** (정상): `cum_actual_mh = weighted_mh_c × (plan_mh / company_mh)`
    - **uniform_fallback** (plan_mh 미제공): `cum_actual_mh = weighted_mh_c / n_l6`
    - **zero** (n_l6=0): `cum_actual_mh = 0`
  - `cum_workers_today = cum_actual_mh / 8.0` (보조 필드, 일 단위 환산)
- **대응 패턴**:
  - 입력: mapped (Activity list), parsed_report, company_total_plan_mh dict, active_l6_for_company dict
  - 처리: company 단위 weighted_mh 합 (final_flag='O' 만) → l6 비례 분배 (3 fallback)
  - 출력: list[dict] (cum_actual_mh_today + cum_workers_today + prorate_method)
- **관련**:
  - 호출자: `_prorate_mh` (mapper.py:597) — atomizer/forecaster 진입 전
  - 테스트: `test_mapper_weighted_mh.py` 5 case (plan_mh_basic / uniform_fallback / final_flag_x / no_l6 / cum_workers_today_div_8)
  - 후속 영속: `insert_mapper_activities_batch` (db.py:639) — cum_actual_mh_today + cum_workers_today 컬럼
- **Suspected related** (2026-05-16):
  - `_weighted_mh_from_shift` — input 의존
  - `_prorate_mh` (mapper.py:529) — 본 함수의 wrapper (PG fetch_l6_plan_mh_map 통합)

---

### `_prorate_mh` — (company, l6_main) 단위 인원 + plan_mh propagate

- **위치**: `pipeline/agents/mapper.py:529-604` (76 LOC)
- **시그니처**: `async def _prorate_mh(mapped, parsed_report, pg) -> list[Activity]`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - U1.A/B 알고리즘 외피 — PG fetch_l6_plan_mh_map 호출 통합
  - assigned_workers / worker_source / plan_mh / cum_actual_mh_today / cum_workers_today 채움
  - M-6: `for company, l6_set in bp_l6.items(): await pg.fetch_l6_plan_mh_map(...)` (mapper.py:557) N+1. POC 규모 (3 BP사) 에서는 문제 없으나 10+ BP사 확장 시 슬로우
- **설계 의도**:
  - mapper_node 의 PG 영속 직전 분배 step
  - assigned_workers = bp_total × (plan_mh / sum_mh) [정상] / bp_total / n_l6 [균등] / 0 [무할당]
- **대응 패턴**:
  - 입력: mapped (Activity list), parsed_report, pg (PGClient)
  - 처리: 5 phase (BP 인원 수집 → L6 plan MH fetch → 정규화 → plan_mh propagate → cum_actual_mh 산출)
  - 출력: Activity list (worker_source ∈ {parsed, mh_prorated, user_corrected})
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:50) 안 — atomizer 진입 전
  - 테스트: `test_mapper_u1a.py`, `test_mapper_u1b.py`
  - PG: `fetch_l6_plan_mh_map` (db.py:106) — l6_main → plan_mh dict 한 번에 조회 (N+1 회피)
- **Suspected related** (2026-05-16):
  - `_prorate_workers_with_mh` — 본 함수의 내부 호출 (mapper.py:597)
  - db.py `fetch_l6_plan_mh_map` — PG 조회 단일 진입점

---

### `build_bp_context` — BP 코드별 분리 컨텍스트

- **위치**: `pipeline/agents/mapper.py:196-252` (57 LOC)
- **시그니처**: `def build_bp_context(company: str, parsed_report) -> str`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - git log: `dc69f14 feat(mapper): build_bp_context BP 별 분리 ...` (2026-05-20)
  - 변경: 회사 단위 집계 → **BP 코드별 분리 + zone 명시**
  - 주석 (mapper.py:206~207): "BP 코드별 분리 + zone 명시. 한 회사가 여러 BP site (FAB+CUB) 운영 시 LLM 가 work_content 의 BP 와 zone 매칭 가능. 옵션 A 의 정확성 강화."
- **설계 의도**:
  - 이전 한계: "주요작업 텍스트 (BP사 기재): FAB F03 / CUB 9층" — FAB/CUB 구분 모호
  - 신규: "PH_X-001 (zone=FAB): FAB F03 4F. PH1 패드천공 [Incr 56명, Cum 150,565명-일]" — 명시적
  - LLM 의 옵션 A (auto_llm_rerank) 정확성 강화 — work_content 의 BP code 와 zone 매칭 가능
- **대응 패턴**:
  - 입력: company (str), parsed_report
  - 처리: 3 phase
    - Phase 1: 시트1 (BPSummary filter by company, 각 BP 코드별 1 라인)
    - Phase 2: 시트2 (`_is_trade_job` 필터, top-8 직종)
    - Phase 3: 시트3 (count_cum_t 내림차순, top-5 장비)
  - 출력: 3 block join 문자열
- **관련**:
  - 호출자: `build_llm_input` (mapper.py:260) — LLM 분류용 풍부 input
  - 테스트: `test_mapper_helpers.py`
  - mapper 영향: 옵션 A (`auto_llm_rerank`) 정확도 강화
- **Suspected related** (2026-05-20):
  - `build_llm_input` (mapper.py:255) — 본 함수의 caller, activity.bp_code 명시 추가
  - `resolve_wa` step 2 (`auto_llm_rerank`) — 본 함수 output 의 indirect 소비

---

### `build_llm_input` — LLM 분류용 풍부 input (activity.bp_code 명시)

- **위치**: `pipeline/agents/mapper.py:255-269` (15 LOC)
- **시그니처**: `def build_llm_input(activity: Activity, parsed_report) -> str`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - git log: `dc69f14 feat(mapper): build_bp_context BP 별 분리 + ...` (2026-05-20)
  - 변경: activity.bp_code 가 LLM input 에 명시적으로 포함됨
- **설계 의도**:
  - embedding_input (단순 회사/작업/공종) + bp_context (시트1+2+3 풍부 BP-별 컨텍스트) 결합
  - candidates 에 ★ 마크 (BP 마스터 등록 여부) — LLM 의 candidate 정확도 향상
- **대응 패턴**:
  - 입력: activity, parsed_report
  - 처리: embedding_input + build_bp_context + activity.bp_code 직접 명시
  - 출력: LLM 분류용 텍스트
- **관련**:
  - 호출자: `map_activity` (mapper.py:451) step 4
  - 페어: `build_embedding_input` (mapper.py:183) — 단순 input (임베딩 전용)
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:196) — 본 함수의 component
  - `resolve_wa` (mapper.py:272) — 본 함수 output 의 LLM choice 가 step 2 input

---

### `map_activity` — 6단계 통합 흐름

- **위치**: `pipeline/agents/mapper.py:365-526` (162 LOC)
- **시그니처**: `async def map_activity(activity: Activity, parsed_report, cfg, bp_cand_lookup=None) -> Activity`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - dc69f14: build_bp_context + bp_code 명시 통합
  - PG cand_pool batch fetch (graph.py:74) 와 협력 — bp_cand_lookup 캐시 받음
- **설계 의도**:
  - 6 step pipeline:
    - ① BP filter (bp_cand_lookup 캐시 우선 → PG fetch 후퇴) → cand_pool
    - ② 임베딩 input (단순)
    - ③ Chroma Top-K (n_results=top_k, cosine distance, include="distances")
    - ④ LLM input (풍부)
    - ⑤ LLM 분류 (Azure gpt-5.1) → JSON `{choice, confidence, reason}`
    - ⑥ WA 결정 (`resolve_wa` 7단계)
  - alternatives jsonb 적재 (`_select_top_k_alternatives`) — FE dropdown 용
- **대응 패턴**:
  - 출력: Activity (wa + l6_main + mapping_source + mapping_conf + requires_review + alternatives)
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:50) — Semaphore 4 병렬 + `asyncio.gather`
  - 페어: `resolve_wa` (mapper.py:272), `build_llm_input` (mapper.py:255)
- **Suspected related** (2026-05-20):
  - `_select_top_k_alternatives` (mapper.py:336) — top-K alternatives 추출
  - db.py `insert_mapper_activities_batch` (db.py:639) — alternatives 컬럼 적재

---

### `_select_top_k_alternatives` — RAG candidate 상위 K (alternatives jsonb)

- **위치**: `pipeline/agents/mapper.py:336-344` (9 LOC)
- **시그니처**: `def _select_top_k_alternatives(candidates: list[dict], k: int = 3) -> list[dict]`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - 신규 2026-05-19 cycle — `mapper_activities.alternatives` jsonb 컬럼 (G23) 적재용
  - migration: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql` (jsonb + GIN index)
- **설계 의도**:
  - LLM 선택 외 top-K (default k=3) 후보를 FE dropdown 에서 사용
  - HIL 1 의 corrections payload 가 alternatives 중에서 선택 가능 (review modal)
- **대응 패턴**:
  - 입력: candidates (Chroma query 결과, score 포함)
  - 처리: score 내림차순 정렬, top-K
  - 출력: list[dict] (wa, l6_main, score)
- **관련**:
  - 호출자: `map_activity` (mapper.py:525)
  - 테스트: `test_mapper_alternatives.py`
- **Suspected related** (2026-05-19):
  - db.py `insert_mapper_activities_batch` (db.py:639) — alternatives jsonb 컬럼
  - web BFF transform — FE review page 의 dropdown 옵션 source

---

### `_is_trade_job` — 시트2 직종 noise 필터

- **위치**: `pipeline/agents/mapper.py:158-164` (7 LOC)
- **시그니처**: `def _is_trade_job(job: str) -> bool`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - `_TRADE_KEYWORDS` (20개): 형틀/철근/콘크리트/타설/조적/방수/도장/비계/용접/배관/전기공/덕트/단열/내장/타일/미장/양생/철골/보온/케이블
  - `_MGR_KEYWORDS` (12개): 소장/관리자/감독/감리/안전/Shop/BIM/공무/설계/품질/운영/창고
  - `_NOISE_KEYWORDS` (2개): "기능공 투입 Total" / "기능공 투입 total" — 합계 row 제외
- **설계 의도**:
  - 시트2 의 기능공 직종만 통과 — `build_bp_context` Phase 2 의 top-8 정렬 정확도
  - 관리자/감독/노이즈 제거 → LLM input quality 향상
- **대응 패턴**:
  - 입력: job_type 문자열
  - 처리: NOT NOISE AND NOT MGR AND (any TRADE keyword match)
  - 출력: bool
- **관련**:
  - 호출자: `build_bp_context` Phase 2 (mapper.py:229) — 시트2 노이즈 제거
  - 테스트: `test_mapper_helpers.py`
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:196) — 유일한 caller

---

### `build_embedding_input` — 임베딩 input (숫자 제외)

- **위치**: `pipeline/agents/mapper.py:183-193` (11 LOC)
- **시그니처**: `def build_embedding_input(activity: Activity) -> str`
- **Last checked**: 2026-05-26 (stamp only)
- **이슈**:
  - 임베딩용 단순 input — 회사/작업/단위/공종만, 숫자 (qty/MH) 제외
  - rerank 정확도와 분리 — 임베딩은 semantic distance, LLM rerank 는 풍부 input
- **설계 의도**:
  - Chroma `wbs_master` 의 doc 와 cosine distance 측정
  - 숫자는 noise — semantic distance 왜곡 (v2 의 "배관공 165168" 류 방지)
- **대응 패턴**:
  - 입력: Activity
  - 처리: 4 필드 join (company, work_content, unit, trade)
  - 출력: 짧은 텍스트
- **관련**:
  - 호출자: `map_activity` (mapper.py:405) step 2
- **Suspected related** (2026-05-20):
  - `build_llm_input` (mapper.py:255) — 본 함수의 결과 + bp_context

---

### `insert_mapper_activities_batch` — mapper_activities 37 컬럼 INSERT (신규 카드)

- **위치**: `pipeline/db.py:639` (127 LOC)
- **시그니처**: `async def insert_mapper_activities_batch(run_id, report_date, activities: list[Activity]) -> None`
- **Last checked**: 2026-05-26 (신규 카드, commit `d40c84f`)
- **이슈**:
  - git log: `d40c84f` (2026-05-23) — mapper_activities 에 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가
  - 33 컬럼 → 37 컬럼 확장. migration: `infra/postgres/migrations/2026-05-23_mapper_l7_5_columns.sql` (8 LOC)
  - **PoC 단계엔 4 컬럼 대부분 None** — Master List 1:N 제약 (M-2 참조)
- **설계 의도**:
  - mapper_activities 를 mapper.py 결과 + Parser 시트4 원천 + activity_master propagate 4 컬럼의 단일 INSERT 진입점
  - ON CONFLICT (run_id, idx) DO UPDATE — 멱등 (run_id 재시도 안전)
  - 4 컬럼 propagate 책임: Parser (`l5_disc`) + activity_master JOIN (`l7_sub`, `l7_5_activity`, `sub_work_area`)
  - 단, activity_master 가 (company, work_content) 기준 1:N 매칭이면 propagate 결과 ambiguous → None 으로 fallback
- **대응 패턴**:
  - 입력: run_id (UUID), report_date (date), activities (list[Activity] — Mapper return)
  - 처리: 37 컬럼 INSERT (parser 시트4 12 + 업체별 일보 4 + WBS 매핑 5 + 분배 5 + RAG 1 + master propagate 4 + conditions 1 + 키 3 + zone/bp_code/scope 3)
  - 출력: PG INSERT side effect
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:50 끝부분)
  - 페어: migration `2026-05-23_mapper_l7_5_columns.sql`, `2026-05-19_mapper_alternatives.sql`
  - 영향: Forecaster (wa/l6_main GROUP BY) + Atomizer (Chroma doc metadata) + FE BFF transform (alternatives, requires_review)
- **Suspected related** (2026-05-23):
  - `map_activity` — 4 컬럼 채울 책임이 mapper.py 가 아니라 Parser + activity_master 에 있음
  - `pipeline/agents/parser.py` (`l5_disc` 추출)

---

## 변경 사항 정리 (ef7c6cd..1ba783f)

| Commit | 변경 |
|---|---|
| `d40c84f` (2026-05-23) | `mapper_activities` 에 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가 (migration + db.py INSERT). PoC 단계 대부분 None, Master List 1:N 정리 후 fill 예정 |
| (이전 cycle 흡수) | `8089e7a` `_weighted_mh_from_shift` + `_prorate_workers_with_mh` (8h 고정 → 시간대 가중), `dc69f14` `build_bp_context` BP별 + `resolve_wa` `auto_bp_zone_match` + `auto_llm_rerank`, `787575b` `test_mapper_resolve_wa.py` 10 case, `4cd36e3` `cum_workers prorate` |

mapper.py LOC delta: 571 (baseline) → 604 (HEAD, +33 LOC). 본 cycle 신규 commit `d40c84f` 자체는 mapper.py 가 아닌 db.py 변경. 33 LOC 증분은 baseline 직전 cycle 의 코멘트 정리 + asyncio.to_thread wrap 보강에서 발생.

## 설계 의도 변화 요약

| 항목 | 이전 | 현재 | 근거 |
|---|---|---|---|
| WA 결정 우선순위 | LLM 우선 | **BP-zone 우선 → LLM fallback** | Fix C (사용자 요구) |
| cand_pool 빈 시 | hil_required | **auto_chroma_top1** | Task 4 (BP 보조 메타) |
| MH 환산 | 8h 고정 | **시간대 가중 (조출 2/주간 8/연장 4/야간 8/철야 12)** | EVM CPI 정합 |
| BP 컨텍스트 | 회사 단위 | **BP 코드별 + zone 명시** | LLM 정확도 강화 |
| alternatives | 없음 | **top-K (default 3) jsonb 적재** | FE dropdown |
| mapper_activities 컬럼 | 33 | **37 (l5_disc + l7_sub + l7_5_activity + sub_work_area)** | 2026-05-23 l7.5 propagate (PoC 단계 None) |

---

## 이슈 표 (deep_dive 2026-05-26 동기화, 8건)

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| M-1 | 매핑 정확도 | M | `hil_required 58% → 25%` 목표는 spec §0.2 — full cycle 5 (POC 3사) 에서 1.4% 로 측정됐으나 데이터 편향 가능. V3 (146 case 전체 simulation) 검증 pending | 다음 cycle |
| M-2 | l7.5 propagate | M | `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 — mapper.py 자체에선 채우지 않음 (Parser + activity_master propagate 의존). **PoC 단계 항상 None** (Master List 1:N 제약). 영향: HIL 1 dropdown 의 컨텍스트 풍부도 손실 + FE WBS tree 의 l7.5 노드 표시 불가 | activity_master 1:1 제약 정리 후 N+1 회피 fetch 통합 |
| M-3 | LLM null 처리 | L | mapper.py:493 — `choice is None or not (0 <= choice < len(candidates))` → 즉시 hil_required. LLM 이 "choice": null 응답할 때 (`response_format=json_object` 라도) 흔함. 별도 retry 없음 (PoC 의도) | Phase 2 — 1회 retry with same prompt 검토 |
| M-4 | Chroma cache key | L | `_WBS_MASTER_CACHE` key = `(host, port, ssl)` — DB 스왑 / collection 갱신 시 stale 가능. process 단위 cache 라 재시작으로 해결 가능 | 검토 보류 |
| M-5 | `assigned_workers` 와 `cum_workers_today` 의 의미 분기 | L | `assigned_workers` = BP 총인원 × plan_mh 비례 (단순 헤드카운트), `cum_workers_today` = 가중 MH / 8 (환산 명-일). 두 필드를 FE 가 혼동할 위험 | FE BFF transform 에 주석 추가 |
| M-6 | `_prorate_mh` 의 sequential await | L | mapper.py:557 — `for company, l6_set in bp_l6.items(): await pg.fetch_l6_plan_mh_map(...)` N+1. POC 규모 (3 BP사) 에서는 문제 없으나 10+ BP사 확장 시 슬로우 | 단일 GROUP BY 로 통합 가능 |
| M-7 | mapping_source `user_corrected` 의 Literal 누락 | L | 라벨이 mapper.py 가 아닌 graph.py `_apply_corrections` (graph.py:191) 에서만 생성됨. `WAResolution.source` Literal (mapper.py:172) 에는 `user_corrected` 가 없음 — 코멘트/문서에서만 언급. type-check skip 되는 silent gap | Literal 8종으로 확장 + `_apply_corrections` 가 WAResolution 재구성하도록 통일 |
| M-8 | Forecaster 의존 — wa NULL row 누락 | M | forecasts.wa 컬럼 (2026-05-18 신규) 이 mapper_activities.wa 에 의존. resolve_wa step 6 (`hil_required`) 가 wa=None 반환 시 forecast bucket GROUP BY (company, l6_main, wa) 에서 그 row 가 NULL bucket 으로 빠짐 → 진단에서 누락. HIL 1 사용자 보정 전 시점 forecast 가 underestimate | full cycle E2E 검증 시 wa NULL row count 모니터링 + Forecaster 가 wa NULL bucket 도 진단하도록 분리 |

---

## 미해결 / Backlog

- M-1: hil_required 58% → 25% 검증 — V3 (146 case full simulation) pending
- M-2: l7.5 4 컬럼 — activity_master 1:N 정리 후 propagate fill (마감 후 cycle 로 이연)
- M-7: `user_corrected` Literal 통일 — graph.py / mapper.py 어디서 생성할지 결정
- M-8: Forecaster wa NULL bucket 분리 — full cycle E2E 검증 결과 따라 우선순위 조정
- `test_mapper_resolve_wa.py` 10 case 외 추가 케이스 (spec §7 V4 의 12 unit test 완료 후 점검)
- mapper.py 에 TODO/FIXME 주석 없음 (검색 결과)

---

*최종 수정: 2026-05-26 (`1ba783f`, l7.5 4 컬럼 propagate cycle stamp + insert_mapper_activities_batch 카드 신규 + 이슈표 M-2/M-7/M-8 갱신)*
*이전 수정: 2026-05-20 (`ef7c6cd`, resolve_wa 7단계 확대 + shift-weighted MH + BP-별 컨텍스트 cycle)*
