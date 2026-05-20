# Design Intent — mapper

- **Generated**: 2026-05-20 (`resolve_wa` 7단계 확대 + shift-weighted MH + BP-별 컨텍스트 cycle)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**:
  - `pipeline/agents/mapper.py` (571 LOC, 이전 393 → +178)
  - `pipeline/tests/test_mapper_resolve_wa.py` (10 case 신규, 2026-05-20)
  - `pipeline/tests/test_mapper_weighted_mh.py` (7 case 신규, 2026-05-16)
  - `pipeline/tests/test_mapper_alternatives.py`, `test_mapper_company_normalize.py`, `test_mapper_helpers.py`, `test_mapper_u1a.py`, `test_mapper_u1b.py`, `test_mapper_golden.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md` (resolve_wa 7단계 + bp_context 분리)
  - `docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md` (shift-weighted MH)

Parser 출력 Activity 를 WBS 매핑. **6단계 흐름 (BP filter → 임베딩 → Chroma top-K → LLM rerank → 분류 → WA 결정 7단계)**. `resolve_wa` 가 이전 5단계 (0+1+2+3+4) 에서 **7단계 (0~6)** 로 확대 — 신규 source 2종: `auto_bp_zone_match` (BP-zone deterministic, fix C) + `auto_llm_rerank` (LLM rerank fallback, 옵션 A). 사용자 push back 3개 정합 ("scope ≠ wa", "시트1 에서 FAB/CUB 알 수 있음", "오른쪽 작업으로 wa 판단"). `_weighted_mh_from_shift` + `_prorate_workers_with_mh` 신규 — 8h 고정 → 시간대 가중 MH (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12, 산업안전공단 근거). `build_bp_context` 가 BP 코드별 분리 (이전: 회사 단위 집계).

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_SHIFT_WEIGHTS` | mapper.py:28 | `dict[str, int]` | 시간대 가중치 상수 (조출 2/주간 8/연장 4/야간 8/철야 12) | — |
| `_weighted_mh_from_shift` | mapper.py:37 | `(shift_dict: dict\|None) -> float` | TimeShiftCounts → 가중 MH 환산 | ✅ |
| `_prorate_workers_with_mh` | mapper.py:48 | `(mapped, parsed_report, company_total_plan_mh, active_l6_for_company) -> list[dict]` | company 단위 시간대 가중 MH → l6 비례 분배 | ✅ |
| `_TRADE_KEYWORDS` | mapper.py:95 | `tuple[str, ...]` | 기능공 직종 keyword (16개) | — |
| `_MGR_KEYWORDS` | mapper.py:117 | `tuple[str, ...]` | 관리자/감독 keyword (10개) | — |
| `_NOISE_KEYWORDS` | mapper.py:131 | `tuple[str, ...]` | 소계 row 판별 keyword | — |
| `_is_trade_job` | mapper.py:134 | `(job: str) -> bool` | 시트2 직종 noise 필터 | ✅ |
| `WAResolution` | mapper.py:144 | `@dataclass(frozen=True)` | WA 결정 결과 (value + 7 source Literal) | — |
| `build_embedding_input` | mapper.py:159 | `(activity: Activity) -> str` | 임베딩용 input (회사/작업/단위/공종, 숫자 제외) | ✅ |
| `build_bp_context` | mapper.py:172 | `(company: str, parsed_report) -> str` | BP 코드별 분리 컨텍스트 (시트1+2+3 join) | ✅ |
| `build_llm_input` | mapper.py:231 | `(activity: Activity, parsed_report) -> str` | LLM 분류용 풍부 input (embedding + bp_context + bp_code) | ✅ |
| `resolve_wa` | mapper.py:248 | `(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution` | **WA 결정 7단계 (0:auto_chroma_top1 / 1:auto_bp_zone_match / 2:auto_llm_rerank / 3:auto_bp_single / 4:auto_l6_single / 5:auto_sheet1_text / 6:hil_required)** | ✅ |
| `_select_top_k_alternatives` | mapper.py:312 | `(candidates: list[dict], k: int=3) -> list[dict]` | RAG candidate score 상위 K (FE dropdown 용 alternatives jsonb) | ✅ |
| `MapperConfig` | mapper.py:324 | `@dataclass` | Mapper config (Azure endpoint / Chroma / PG URL / conf_threshold) | — |
| `map_activity` | mapper.py:341 | `async (activity, parsed_report, cfg, bp_cand_lookup=None) -> Activity` | 6단계 통합 흐름 (BP filter → 임베딩 → Chroma → LLM → WA 결정) | ✅ |
| `_prorate_mh` | mapper.py:496 | `async (mapped, parsed_report, pg) -> list[Activity]` | (company, l6_main) 단위 인원 분배 + plan_mh propagate (U1.A/B) | ✅ |

---

## T2 — Issue Cards

### `resolve_wa` — WA 결정 7단계 (주력)

- **위치**: `pipeline/agents/mapper.py:248-310` (63 LOC)
- **시그니처**: `def resolve_wa(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution`
- **이슈**:
  - git log: `dc69f14 feat(mapper): build_bp_context BP 별 분리 + resolve_wa auto_bp_zone_match + auto_llm_rerank` (2026-05-20)
  - git log: `787575b test(mapper): resolve_wa 7 단계 unit test 신설` (2026-05-20, 10 case)
  - 사용자 push back (spec §0.3):
    - "scope ≠ wa, 오른쪽 작업으로 wa 판단" → 옵션 A (auto_llm_rerank)
    - "soft hint = 1번 시트에서 FAB / CUB 알 수 있음" → fix C (auto_bp_zone_match)
    - "work_text 기반 판단 신뢰" → step 2 fallback
  - **목표**: hil_required 58% → 25% 이내 (spec §0.2)
- **설계 의도**:
  - 이전 5단계 (0+1+2+3+4) → 7단계 (0~6) 확대
  - **신규 step 1 `auto_bp_zone_match`** (deterministic + LLM override):
    - 조건: `activity.bp_code == BPSummary.bp_code && BPSummary.zone in cand_wa_set`
    - 동작: BPSummary.zone 그대로 채택 (LLM 선택과 무관 deterministic)
    - 근거: 사용자 "시트1 에서 FAB/CUB 알 수 있음"
    - **conf 무관 → requires_review=False**
  - **신규 step 2 `auto_llm_rerank`** (fallback when BP-zone fail):
    - 조건: `chosen_wa && (chosen_wa, l6_choice) in cand_pool`
    - 동작: LLM 이 선택한 (wa, l6) 채택
    - 근거: 사용자 "scope ≠ wa, 오른쪽 작업으로 wa 판단"
  - `WAResolution.source` Literal 4종 → 7종 확대
- **대응 패턴**:
  - 입력: activity, l6_choice (LLM 선택), cand_pool: list[(wa, l6_main)], parsed_report, chosen_wa
  - 처리: 7-step ladder (조건 매칭 시 즉시 return)
    - **step 0** `auto_chroma_top1` (cand_pool 빈 시, BP 미등록 BP사) — Task 4
    - **step 1** `auto_bp_zone_match` (BP-zone deterministic) — fix C
    - **step 2** `auto_llm_rerank` (LLM rerank fallback) — 옵션 A
    - **step 3** `auto_bp_single` (BP scope WA 단일) — legacy
    - **step 4** `auto_l6_single` (L6 결정 후 wa 단일) — legacy
    - **step 5** `auto_sheet1_text` (회사 단위 zone 교집합) — legacy
    - **step 6** `hil_required` (모든 조건 실패)
  - 출력: WAResolution(value=str|None, source=Literal[7종])
- **관련**:
  - 호출자: mapper.py:341 (`map_activity`) step 6 — `requires_review = (confidence < cfg.conf_threshold) or (wa_result.source == "hil_required")`
  - 테스트: `test_mapper_resolve_wa.py` 10 case (각 단계별 트리거 + skip + fallback)
  - 페어 함수: `build_bp_context` (BP-별 분리, 본 함수 의 LLM input 강화)
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:172) — step 1 deterministic 의 LLM 신뢰도 보강
  - graph.py:67~68 — fetch_bp_candidates 전 정규화 (cand_pool 빈 케이스 root cause)

---

### `_weighted_mh_from_shift` — 시간대 가중 MH 환산

- **위치**: `pipeline/agents/mapper.py:37-46` (10 LOC)
- **시그니처**: `def _weighted_mh_from_shift(shift_dict: dict | None) -> float`
- **이슈**:
  - git log: `8089e7a mapper: replace 8h fixed prorate with shift-weighted MH` (2026-05-16)
  - docstring: "시트2 workers_today_cum jsonb (TimeShiftCounts) → 가중 MH. spec §3.2 가중치 (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12) 적용. None / 빈 dict / 키 누락 → 0.0 처리."
  - spec `2026-05-19-cpia-reports-parser-mh-design.md` §3 — EVM CPI = EV/AC 분모 정합
- **설계 의도**:
  - 이전: `cum_workers_today × 8.0` (daily total) — AC 분모 과소 → CPI 폭주
  - 변경: `Σ(shift_dict[k] × weight_k)` — 실 누적 인공 (man-hour)
  - 가중치 근거: 산업안전공단 표준 — 조출 (06:00~08:00 2h) / 주간 (표준 8h) / 연장 (17:00~21:00 4h) / 야간 (22:00~06:00 8h) / 철야 (12h 연속)
- **대응 패턴**:
  - 입력: TimeShiftCounts dict (morning/daytime/overtime/night/all_night/total)
  - 처리: 5-key weighted sum (total 키 무시)
  - 출력: float MH
- **관련**:
  - 호출자: `_prorate_workers_with_mh` (mapper.py:48) — l6 비례 분배 input
  - 테스트: `test_mapper_weighted_mh.py` 7 case (daytime/mixed/all_night/morning_overtime/None/empty/missing_keys)
- **Suspected related** (2026-05-16):
  - `_prorate_workers_with_mh` — 본 함수의 유일한 caller
  - state.py `TimeShiftCounts` (line 17) — 본 함수의 input 스키마

---

### `_prorate_workers_with_mh` — U1.A/B 알고리즘

- **위치**: `pipeline/agents/mapper.py:48-91` (44 LOC)
- **시그니처**: `def _prorate_workers_with_mh(mapped, parsed_report, company_total_plan_mh, active_l6_for_company) -> list[dict]`
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
  - 처리: company 단위 weighted_mh 합 → l6 비례 분배 (3 fallback)
  - 출력: list[dict] (cum_actual_mh_today + cum_workers_today + worker_source)
- **관련**:
  - 호출자: `_prorate_mh` (mapper.py:496) — atomizer/forecaster 진입 전
  - 테스트: `test_mapper_weighted_mh.py` 5 case (plan_mh_basic / uniform_fallback / final_flag_x / no_l6 / cum_workers_today_div_8)
  - 후속 영속: `insert_mapper_activities_batch` (db.py:621) — cum_actual_mh_today + cum_workers_today 컬럼
- **Suspected related** (2026-05-16):
  - `_weighted_mh_from_shift` — input 의존
  - `_prorate_mh` (mapper.py:496) — 본 함수의 wrapper (PG fetch_l6_plan_mh_map 통합)

---

### `_prorate_mh` — (company, l6_main) 단위 인원 + plan_mh propagate

- **위치**: `pipeline/agents/mapper.py:496-571` (76 LOC)
- **시그니처**: `async def _prorate_mh(mapped, parsed_report, pg) -> list[Activity]`
- **이슈**:
  - U1.A/B 알고리즘 외피 — PG fetch_l6_plan_mh_map 호출 통합
  - assigned_workers / worker_source / plan_mh / cum_actual_mh_today / cum_workers_today 채움
- **설계 의도**:
  - mapper_node 의 PG 영속 직전 분배 step
  - assigned_workers = bp_total × (plan_mh / sum_mh) [정상] / bp_total / n_l6 [균등] / 0 [무할당]
- **대응 패턴**:
  - 입력: mapped (Activity list), parsed_report, pg (PGClient)
  - 처리: 5 phase (BP 인원 수집 → L6 plan MH fetch → 정규화 → plan_mh propagate → cum_actual_mh 산출)
  - 출력: Activity list (worker_source ∈ {parsed, mh_prorated, user_corrected})
- **관련**:
  - 호출자: graph.py `mapper_node` (graph.py:48) 안 — atomizer 진입 전
  - 테스트: `test_mapper_u1a.py`, `test_mapper_u1b.py`
  - PG: `fetch_l6_plan_mh_map` (db.py:106) — l6_main → plan_mh dict 한 번에 조회 (N+1 회피)
- **Suspected related** (2026-05-16):
  - `_prorate_workers_with_mh` — 본 함수의 내부 호출
  - db.py `fetch_l6_plan_mh_map` — PG 조회 단일 진입점

---

### `build_bp_context` — BP 코드별 분리 컨텍스트

- **위치**: `pipeline/agents/mapper.py:172-228` (57 LOC)
- **시그니처**: `def build_bp_context(company: str, parsed_report) -> str`
- **이슈**:
  - git log: `dc69f14 feat(mapper): build_bp_context BP 별 분리 ...` (2026-05-20)
  - 변경: 회사 단위 집계 → **BP 코드별 분리 + zone 명시**
  - 주석 (mapper.py:182~183): "한 회사가 여러 BP site (FAB+CUB) 운영 시 LLM 가 work_content 의 BP 와 zone 매칭 가능"
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
  - 호출자: `build_llm_input` (mapper.py:231) — LLM 분류용 풍부 input
  - 테스트: `test_mapper_helpers.py`
  - mapper 영향: 옵션 A (`auto_llm_rerank`) 정확도 강화
- **Suspected related** (2026-05-20):
  - `build_llm_input` (mapper.py:231) — 본 함수의 caller, activity.bp_code 명시 추가
  - `resolve_wa` step 2 (`auto_llm_rerank`) — 본 함수 output 의 indirect 소비

---

### `build_llm_input` — LLM 분류용 풍부 input (activity.bp_code 명시)

- **위치**: `pipeline/agents/mapper.py:231-246` (16 LOC)
- **시그니처**: `def build_llm_input(activity: Activity, parsed_report) -> str`
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
  - 호출자: `map_activity` (mapper.py:341) step 4
  - 페어: `build_embedding_input` (mapper.py:159) — 단순 input (임베딩 전용)
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:172) — 본 함수의 component
  - `resolve_wa` (mapper.py:248) — 본 함수 output 의 LLM choice 가 step 2 input

---

### `map_activity` — 6단계 통합 흐름

- **위치**: `pipeline/agents/mapper.py:341-493` (153 LOC)
- **시그니처**: `async def map_activity(activity: Activity, parsed_report, cfg, bp_cand_lookup=None) -> Activity`
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
  - 호출자: graph.py `mapper_node` (graph.py:48) — Semaphore 4 병렬 + `asyncio.gather`
  - 페어: `resolve_wa` (mapper.py:248), `build_llm_input` (mapper.py:231)
- **Suspected related** (2026-05-20):
  - `_select_top_k_alternatives` (mapper.py:312) — top-K alternatives 추출
  - db.py `insert_mapper_activities_batch` (db.py:621) — alternatives 컬럼 적재

---

### `_select_top_k_alternatives` — RAG candidate 상위 K (alternatives jsonb)

- **위치**: `pipeline/agents/mapper.py:312-322` (11 LOC)
- **시그니처**: `def _select_top_k_alternatives(candidates: list[dict], k: int = 3) -> list[dict]`
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
  - 호출자: `map_activity` (mapper.py:341)
  - 테스트: `test_mapper_alternatives.py`
- **Suspected related** (2026-05-19):
  - db.py `insert_mapper_activities_batch` (db.py:621) — alternatives jsonb 컬럼
  - web BFF transform — FE review page 의 dropdown 옵션 source

---

### `_is_trade_job` — 시트2 직종 noise 필터

- **위치**: `pipeline/agents/mapper.py:134-142` (9 LOC)
- **시그니처**: `def _is_trade_job(job: str) -> bool`
- **이슈**:
  - `_TRADE_KEYWORDS` (16개): 형틀/철근/배관/배전 등
  - `_MGR_KEYWORDS` (10개): 소장/감독/BIM 등 — 관리자 제외
  - `_NOISE_KEYWORDS` (2개): "기능공 투입 Total" 류 — 합계 row 제외
- **설계 의도**:
  - 시트2 의 기능공 직종만 통과 — `build_bp_context` Phase 2 의 top-8 정렬 정확도
  - 관리자/감독/노이즈 제거 → LLM input quality 향상
- **대응 패턴**:
  - 입력: job_type 문자열
  - 처리: TRADE keyword match AND NOT MGR/NOISE
  - 출력: bool
- **관련**:
  - 호출자: `build_bp_context` Phase 2 (mapper.py:172) — 시트2 노이즈 제거
  - 테스트: `test_mapper_helpers.py`
- **Suspected related** (2026-05-20):
  - `build_bp_context` (mapper.py:172) — 유일한 caller

---

### `build_embedding_input` — 임베딩 input (숫자 제외)

- **위치**: `pipeline/agents/mapper.py:159-170` (12 LOC)
- **시그니처**: `def build_embedding_input(activity: Activity) -> str`
- **이슈**:
  - 임베딩용 단순 input — 회사/작업/단위/공종만, 숫자 (qty/MH) 제외
  - rerank 정확도와 분리 — 임베딩은 semantic distance, LLM rerank 는 풍부 input
- **설계 의도**:
  - Chroma `wbs_master` 의 doc 와 cosine distance 측정
  - 숫자는 noise — semantic distance 왜곡
- **대응 패턴**:
  - 입력: Activity
  - 처리: 4 필드 join (company, work_content, unit, l5_disc)
  - 출력: 짧은 텍스트
- **관련**:
  - 호출자: `map_activity` step 2
- **Suspected related** (2026-05-20):
  - `build_llm_input` (mapper.py:231) — 본 함수의 결과 + bp_context

---

### `_normalize_unit` — 단위 대소문자 통일 (legacy, parser_post 와 중복 가능성)

- **위치**: 본 함수는 mapper 가 아닌 parser 측 (parser.py:40). mapper 측엔 별도 정의 없음.

---

### `_disc_abbrev_to_kr` — 공종 약자 → 한글 (legacy)

- **위치**: 본 함수는 parser 측 (parser.py:45). mapper 는 정규화된 한글 disc 만 받음.

---

## 변경 사항 정리 (cf3c143..HEAD)

| Commit | 변경 |
|---|---|
| 8089e7a | mapper: replace 8h fixed prorate with shift-weighted MH (`_weighted_mh_from_shift` + `_prorate_workers_with_mh` 신규) |
| dc69f14 | feat(mapper): build_bp_context BP 별 분리 + resolve_wa auto_bp_zone_match + auto_llm_rerank |
| 787575b | test(mapper): resolve_wa 7 단계 unit test 신설 (10 case) |
| 4cd36e3 | feat(mapper): U1.B cum_workers prorate (plan_mh 비율) + uniform fallback |

## 설계 의도 변화 요약

| 항목 | 이전 | 현재 | 근거 |
|---|---|---|---|
| WA 결정 우선순위 | LLM 우선 | **BP-zone 우선 → LLM fallback** | Fix C (사용자 요구) |
| cand_pool 빈 시 | hil_required | **auto_chroma_top1** | Task 4 (BP 보조 메타) |
| MH 환산 | 8h 고정 | **시간대 가중 (조출 2/주간 8/연장 4/야간 8/철야 12)** | EVM CPI 정합 |
| BP 컨텍스트 | 회사 단위 | **BP 코드별 + zone 명시** | LLM 정확도 강화 |
| alternatives | 없음 | **top-K (default 3) jsonb 적재** | FE dropdown |

## 미해결 / Backlog

- hil_required 58% → 25% 검증 — V3 (146 case full simulation) pending
- `test_mapper_resolve_wa.py` 10 case 외 추가 케이스 (spec §7 V4 의 12 unit test 완료 후 점검)
- mapper.py 에 TODO/FIXME 주석 없음 (검색 결과)
