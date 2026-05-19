# Design Intent — mapper

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/agents/mapper.py` (393 LOC) + 4 테스트 파일

Parser 출력 Activity 를 WBS 매핑. 6단계 흐름 (BP filter → 임베딩 → Chroma top-K → LLM rerank → 분류 → WA 결정 4단계). PoC 79건 시뮬 자동 정확도 98.7% (mapping-layer.md v3). `requires_review=True` 인 row 가 HIL 1 큐 입력 (HIL 1 노드 자체는 미구현).

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_is_trade_job` | mapper.py:64 | `(job: str) -> bool` | 시트2 기능공 추출 (관리자/Noise 제외) | ✅ |
| `WAResolution` | mapper.py:74 | `@dataclass(frozen=True)` | WA 결정 4단계 출력 (value + source) | ✅ |
| `build_embedding_input` | mapper.py:86 | `(activity) -> str` | 임베딩용 단순 input (회사/작업/단위/공종) | ✅ |
| `build_bp_context` | mapper.py:99 | `(company, parsed_report) -> str` | BP사 단위 풍부 컨텍스트 (시트1+2+3 join) | ✅ |
| `build_llm_input` | mapper.py:150 | `(activity, parsed_report) -> str` | LLM 분류용 최종 input (작업line + BP 컨텍스트) | ✅ |
| `resolve_wa` | mapper.py:166 | `(activity, l6_choice, cand_pool, parsed_report) -> WAResolution` | WA 결정 4단계 (BP scope → L6 → 시트1 자연어 → H-i-L) | ✅ |
| `MapperConfig` | mapper.py:191 | `@dataclass` | Azure/PG/Chroma 접속 + top_k/threshold | ✅ |
| `map_activity` | mapper.py:208 | `async (activity, parsed_report, cfg) -> Activity` | 6단계 통합 (공개 API) | ✅ |
| `_prorate_mh` | mapper.py:347 | `async (mapped, parsed_report, pg) -> list[Activity]` | (company, l6_main) 단위 BP 인원 비례 분배 | ✅ |

---

## T2 — Issue Cards

### `map_activity` — 6단계 매핑 통합 (공개 API)

- **위치**: `pipeline/agents/mapper.py:208-345` (138 LOC, 분기 10+)
- **시그니처**: `async def map_activity(activity: Activity, parsed_report: ParsedDailyReport | None, cfg: MapperConfig) -> Activity`
- **이슈**:
  - git log `dd6359d` (A_Track: Mapper + Forecaster + Optimizer + hil_2 PoC 데모 가능 상태 #15)
  - git log `f2b4a3b` (optimizer/Task 12: 본 cycle 종결 — spec/plan commit + 회귀 183 passed + 0 한자 검수)
  - docstring (mapper.py:208): "6단계 흐름 (mapping-layer.md §3). ① BP filter (PG) → ② 임베딩 input (단순) → ③ Chroma Top-K → BP filter ∩ → ④ LLM input (풍부) → ⑤ LLM 분류 → ⑥ WA 결정 4단계."
  - 인라인 주석 단계별 명시 (① ~ ⑥): "임베딩 후보가 BP filter 통과 0개 → BP filter 전체 fallback" (mapper.py:272-276)
  - 메타: `docs/schema/mapping-layer.md:121 §3` (6단계 흐름 상세), `:213` (v3 시뮬 98.7% (79/79), 토큰 84,474), `docs/schema/example-walkthrough.md:140-151` (실행 예시 confidence 0.78/0.82)
- **설계 의도**:
  - 6단계 책임 분리: BP filter (정확도/속도) → 임베딩 (코사인 유사) → LLM 분류 (semantic rerank) → WA 결정 (deterministic rule).
  - 임베딩 vs LLM input 분리 (mapping-layer.md §3.1): v2 시뮬에서 동일 input 사용 시 97.5% (배관공 165,168 같은 큰 숫자가 임베딩 오염) → v3 분리 후 98.7% 회복.
  - fallback 정책: 임베딩 후보가 BP filter 통과 0개 → BP filter 전체 사용 (의도된 설계).
  - `requires_review` 결정 위치: `confidence < cfg.conf_threshold or wa_result.source == "hil_required"` (mapper.py:335) — confidence 0.7 hardcoded threshold.
- **대응 패턴**:
  - 발동: `graph.py:mapper_node` 가 각 activity 마다 호출
  - 입력: 1 Activity + ParsedDailyReport (BP 컨텍스트용) + MapperConfig
  - 처리: 6 단계 순차 (PG → Embed → Chroma → LLM → WA → review)
  - 출력: Activity (mapped_activity_id, mapping_confidence, mapping_source, requires_review 채워진 상태)
- **관련**:
  - `graph.py:mapper_node:40` (호출자)
  - `_prorate_mh` (후처리)
  - 테스트: `test_mapper_node.py:31-92` (남웅/세보 2 케이스), `test_mapper_golden.py:91-124` (79건 ≥95% 정확도)
  - 페어 spec: `docs/schema/mapping-layer.md`
- **Suspected related** (2026-05-17 stale):
  - HIL 1 (mapper → hil_1 → atomizer) — `requires_review=True` row 가 HIL 1 큐 입력. drift backlog #4.
  - WA 3단계 (시트1 자연어 LLM 추론) — TODO 미활성 (`resolve_wa:184`).

---

### `_prorate_mh` — BP사 단위 인원 비례 분배

- **위치**: `pipeline/agents/mapper.py:347-393` (47 LOC, 분기 7)
- **시그니처**: `async def _prorate_mh(mapped: list[Activity], parsed_report: ParsedDailyReport, pg: PGClient) -> list[Activity]`
- **이슈**:
  - git log `a0a7a82` (optimizer/Task 8) / `44466c5` (optimizer/Task 9) commit 메시지 명시.
  - docstring (mapper.py:347-350): "(company, l6_main) 단위 BP사 총 인원 분배 — 옵션 X 알고리즘. Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §3."
  - 인라인 주석: "분배 공식: BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)"
- **설계 의도**:
  - BP사 1일 투입 인원을 어떤 l6 (공종) 에 얼마나 분배할지 — Plan 의 plan_mh 비율로 결정.
  - PG fetch 1회 (`fetch_l6_plan_mh_map`) 로 N+1 회피.
  - Edge case 명시: plan_mh 합 0 → 균등 분배 / l6_main=None → skip.
- **대응 패턴**:
  - 발동: `mapper_node` 가 모든 row 매핑 후 batch 단위로 호출
  - 입력: mapped Activity list + parsed_report (시트1 BPSummary 사용) + PG client
  - 처리: BP사별 today_incr_total 합산 → fetch_l6_plan_mh_map → 비례 분배 → assigned_workers 채움
  - 출력: 동일 list (assigned_workers 채워짐)
- **관련**:
  - `db.py:fetch_l6_plan_mh_map:72` (N+1 회피 SQL)
  - `state.py:Activity.assigned_workers / worker_source`
  - 테스트: `test_prorate_mh.py:64-207` (단일/zero_total/zero_plan_mh/unmapped_skip/multi_share/세보 real_pg 6 케이스)
- **Suspected related** (2026-05-17 stale):
  - Atomizer `_build_metadata` 가 assigned_workers float 으로 저장 → Forecaster 가 productivity 계산 시 사용.

---

### `resolve_wa` — WA 결정 4단계

- **위치**: `pipeline/agents/mapper.py:166-189` (24 LOC, 분기 4)
- **시그니처**: `def resolve_wa(activity, l6_choice, cand_pool, parsed_report) -> WAResolution`
- **이슈**:
  - docstring (mapper.py:166): "WA 결정 4단계 (mapping-layer.md §4)."
  - 인라인 주석 4단계 명시: "1단계 — BP scope WA 단일 / 2단계 — L6 결정 후 그 L6 의 WA 단일 / 3단계 — 시트1 자연어 LLM 추론 (PoC 비활성, GATE 2 활성) / 4단계 — H-i-L 강제"
  - TODO (mapper.py:184): `# TODO: GATE 2 진입 시 llm_infer_wa() 추가`
  - 메타: `docs/schema/mapping-layer.md:218-262 §4` (4단계 알고리즘, PoC 결과 1단계 30% / 2단계 9% / 4단계 61%).
- **설계 의도**:
  - 자동 결정 우선 (1·2 단계) → 자연어 LLM 추론 보류 (GATE 2 위임) → 모호한 경우 사람 검토 (HIL 1).
  - `WAResolution.source` 라벨로 의사결정 경로 추적 (운영 감사용).
  - 4단계 hil_required 는 PoC 에서 61% (남웅건설) — HIL 1 가 필수임을 정량적으로 입증.
- **대응 패턴**:
  - 발동: `map_activity` ⑥ 단계
  - 입력: activity + L6 분류 결과 + BP 후보 풀 + parsed_report
  - 처리: 4 단계 룰 순차 → 첫 매치에서 즉시 반환
  - 출력: WAResolution(value, source)
- **관련**:
  - `WAResolution` (mapper.py:74)
  - 테스트: `test_mapper_helpers.py:74-114` (bp_scope_single / l6_single / hil_required 3 케이스)
  - 페어 spec: `docs/schema/mapping-layer.md:218-262`
- **Suspected related** (2026-05-17 stale):
  - WA 3단계 활성화 (GATE 2) — TODO 진입 시 `llm_infer_wa()` 별도 함수 추가.
  - HIL 1 — `hil_required` source 인 row 가 drift backlog #4 의 input.

---

### `build_bp_context` — BP사 단위 풍부 컨텍스트

- **위치**: `pipeline/agents/mapper.py:99-148` (50 LOC, 분기 6)
- **시그니처**: `def build_bp_context(company: str, parsed_report: ParsedDailyReport | None) -> str`
- **이슈**:
  - docstring: "LLM input 용 BP사 단위 풍부 컨텍스트 (시트1+2+3 join)."
  - 인라인 주석: "시트2 — 기능공만, noise 제거" (`_is_trade_job` 호출), "시트3 — 장비"
  - 메타: `docs/schema/mapping-layer.md:164-201 §3.1` — "v2 시뮬: 동일 input 사용 시 97.5% (임베딩이 큰 숫자 '배관공 165,168' 에 휘둘림). v3: 임베딩·LLM input 분리 후 98.7% 회복."
- **설계 의도**:
  - LLM 분류 정확도 향상: BP사 단위로 시트1(주요작업 today) + 시트2(기능공 인원) + 시트3(장비) 정보를 묶어 컨텍스트 제공.
  - 임베딩 input 과 분리 (`build_embedding_input` 은 단순). v2 임베딩 오염 회피.
  - 기능공 필터 (`_is_trade_job`) — 관리자 직종 노이즈 제외.
- **대응 패턴**:
  - 발동: `build_llm_input` 내부 호출
  - 입력: company + ParsedDailyReport (시트1/2/3 모두 사용)
  - 처리: 3 시트 join 한 multi-line str 생성
  - 출력: LLM context str
- **관련**:
  - `_is_trade_job` (mapper.py:64)
  - `build_llm_input` (mapper.py:150)
  - 테스트: `test_mapper_helpers.py:66-72 test_build_llm_input_rich`
- **Suspected related** (2026-05-17 stale): 없음.

---

### `MapperConfig` — Azure/PG/Chroma 환경 + threshold

- **위치**: `pipeline/agents/mapper.py:191-206` (16 LOC)
- **시그니처**: `@dataclass class MapperConfig`
- **이슈**:
  - 필드: `azure_endpoint / azure_api_key / azure_api_version / llm_model / embedding_model / postgres_url / chroma_host / chroma_port / chroma_ssl=False / top_k=15 / max_candidates=8 / conf_threshold=0.7`.
  - git log `dd6359d` (Mapper + Forecaster + Optimizer PoC).
  - 메타: `docs/schema/mapping-layer.md:218-262` — confidence threshold 0.7 v3 시뮬 결과.
- **설계 의도**:
  - 설정 응집: 6단계가 모두 같은 cfg 사용. `top_k=15` (Chroma) + `max_candidates=8` (LLM 입력 후보) — 검색→분류 깔때기.
  - `conf_threshold=0.7` — `requires_review` 결정 임계값. mapping-layer.md v3 결과 기반.
- **대응 패턴**:
  - 발동: `GraphConfig.mapper` 에 박혀 `mapper_node` 입력
  - 입력: 없음 (생성자만)
  - 처리: dataclass init
  - 출력: instance
- **관련**:
  - `graph.py:GraphConfig:33`
  - 테스트: 12개 이상 (fixture cfg)
- **Suspected related** (2026-05-17 stale):
  - `conf_threshold` 0.7 변경 시 `requires_review` 분포 영향 → HIL 1 큐 크기 변동.

---

### `WAResolution` — WA 결정 출력 frozen

- **위치**: `pipeline/agents/mapper.py:74-84` (11 LOC)
- **시그니처**: `@dataclass(frozen=True) class WAResolution`
- **이슈**:
  - 필드: `value: str | None`, `source: Literal["auto_bp_single","auto_l6_single","auto_sheet1_text","hil_required"]`.
  - 4 source 라벨 = WA 4단계 라벨 그대로.
- **설계 의도**:
  - frozen=True — 불변 객체 (resolve_wa 출력 변조 방지).
  - source 라벨로 의사결정 경로 추적. `auto_sheet1_text` 는 GATE 2 위임 (현재 미반환).
- **대응 패턴**:
  - 발동: `resolve_wa` 반환
  - 입력: 없음
  - 처리: 없음
  - 출력: instance
- **관련**:
  - `resolve_wa` (mapper.py:166)
  - `map_activity` (mapper.py:208-345, source 라벨 사용)
- **Suspected related** (2026-05-17 stale): GATE 2 WA 3단계 활성화 시 `auto_sheet1_text` 라벨 처음 등장.

---

### `build_llm_input` — LLM 분류용 최종 input

- **위치**: `pipeline/agents/mapper.py:150-164` (15 LOC)
- **시그니처**: `def build_llm_input(activity, parsed_report) -> str`
- **이슈**:
  - docstring (mapper.py:150): "LLM input — 작업line + BP사 단위 풍부 컨텍스트 (mapping-layer.md §3.1)."
  - 인라인: `today_str = activity["today_qty"] if activity["today_qty"] not in (None, 0) else "-"` — 0/None 은 "-" 으로 표기.
- **설계 의도**:
  - 임베딩 input (단순) vs LLM input (풍부) 분리 의도의 후반부. 0/None 의도적 표기로 LLM 가독성 향상.
- **대응 패턴**:
  - 발동: `map_activity` ④ 단계
  - 입력: 1 Activity + parsed_report
  - 처리: `build_bp_context` 호출 + 작업 line concat
  - 출력: LLM user message str
- **관련**:
  - `build_bp_context` (호출자)
  - `map_activity` (호출자)
  - 테스트: `test_mapper_helpers.py:66-72`
- **Suspected related** (2026-05-17 stale): 없음.

---

### `build_embedding_input` — 임베딩용 단순 input

- **위치**: `pipeline/agents/mapper.py:86-96` (11 LOC)
- **시그니처**: `def build_embedding_input(activity: Activity) -> str`
- **이슈**:
  - docstring (mapper.py:86): "임베딩 input — 작업line 자체만 (mapping-layer.md §3.1). 숫자·BP 컨텍스트 제외. v2 의 숫자 오염 (배관공 165168 등) 방지."
- **설계 의도**:
  - 임베딩 모델 입력에서 큰 숫자 제외 — v2 시뮬 97.5% → v3 98.7% 회복의 핵심 변경.
  - 회사 + 작업 + 단위 + 공종만 — 의미 유사도 중심.
- **대응 패턴**:
  - 발동: `map_activity` ② 단계
  - 입력: 1 Activity
  - 처리: 4 필드 concat
  - 출력: 임베딩 str
- **관련**:
  - `map_activity:208`
  - 테스트: `test_mapper_helpers.py:55-64 test_build_embedding_input_simple`
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_is_trade_job` — 시트2 기능공 추출

- **위치**: `pipeline/agents/mapper.py:64-72` (9 LOC, 분기 3)
- **시그니처**: `def _is_trade_job(job: str) -> bool`
- **이슈**:
  - docstring: "시트2 직종 noise 제거."
  - 키워드 화이트리스트 + 블랙리스트:
    - `_TRADE_KEYWORDS` (46개): 형틀/철근/콘크리트/타설/조적/배관공 등
    - `_MGR_KEYWORDS` (11개): 소장/관리자/감독/감리/안전/Shop/BIM 등
    - `_NOISE_KEYWORDS` (2개): "기능공 투입 Total"
- **설계 의도**:
  - 3단 필터: noise 제거 → 관리자 제외 → 기능공 키워드 매치. 순서 중요.
  - parser.py 의 `_is_admin_job` 과는 반대 방향 (whitelist 기반).
- **대응 패턴**:
  - 발동: `build_bp_context` 시트2 순회 중
  - 입력: job_type 문자열
  - 처리: noise → mgr → trade 순차 체크
  - 출력: True/False
- **관련**:
  - `build_bp_context` (호출자)
  - `parser.py:_is_admin_job` — 반대 방향 패턴
- **Suspected related** (2026-05-17 stale): 없음.

---

## 관찰

- **mapping-layer.md v3 일치**: 코드와 spec (docs/schema/mapping-layer.md) 6단계 흐름, threshold, 4단계 WA 결정, top_k 값 모두 일치 확인.
- **LLM prompt 순수 한글**: SYSTEM/USER 메시지 모두 한국어, 한자 0건 (mapper.py:283-299).
- **PoC 정확도 (v3 시뮬)**: 자동 98.7% (79/79), confidence 0.55 1건 → HIL 1 발동 → 운영 정확도 100%. WA 결정 1단계 30% (세보) + 2단계 9% (창원) + 4단계 61% (남웅).
- **dead code 후보**: `WAResolution.source="auto_sheet1_text"` 라벨은 정의만 있고 GATE 2 활성화 전까지 반환되지 않음 (의도된 미활성).

---

## 2026-05-19 FE↔BE 연결 + 6 BE 적재 보완 cycle (Git SHA cf3c143, PR #28)

### T1 신규 / 변경

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_select_top_k_alternatives` | `pipeline/agents/mapper.py:213-221` | `(candidates: list[dict[str, Any]], k: int = 3) -> list[dict[str, Any]]` | G23 — RAG candidate 중 score 내림차순 top-K 추출, FE review dropdown 용 `{wa, l6_main, score}` jsonb payload | ✅ |

T1 변경 (기존 함수):

| Function/Class | File:Line | 본 cycle 노트 |
|---|---|---|
| `map_activity` | `pipeline/agents/mapper.py:242-394` | Chroma `coll.query(...)` 의 `include` 에 `"distances"` 추가 (mapper.py:290). candidates 원소에 `score = 1.0 - dist` 채움 (mapper.py:298-305). 정상 return path 에 `"alternatives": _select_top_k_alternatives(candidates, k=3)` 추가 (mapper.py:393). HIL 3 경로 (Chroma empty mapper.py:311 / JSON parse fail mapper.py:351 / choice out-of-range mapper.py:362) 는 alternatives 키 안 set — DB DEFAULT '[]' 적용. |

### T2 신규 카드

#### M-G23-1 — RAG top-K alternatives jsonb 적재

- **위치**: `pipeline/agents/mapper.py:213-221` (helper) + `pipeline/agents/mapper.py:393` (호출).
- **이슈**:
  - 마이그: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql` — `mapper_activities` 에 `alternatives jsonb NOT NULL DEFAULT '[]'` 컬럼 추가.
  - FE review 페이지의 "대안 WP 후보" dropdown 데이터 소스. 본 cycle 직전엔 dropdown 이 비어있었음.
  - 본 cycle 검증 (run_id=627e2c4d): mapper_activities 6/6 row 의 alternatives jsonb 가 `[{"wa":..., "l6_main":..., "score":...}, ...]` 3건씩 채워짐 (alt_ok=6/6).
- **설계 의도**:
  - top_k=15 Chroma 결과 (cfg 기본값, mapper.py:237) 중 score 내림차순 정렬 → 상위 K=3 만 dropdown 노출. 너무 많은 후보가 PM 의 review UI 를 흐리지 않도록 hard cap.
  - score 정의 = `1.0 - cosine_distance` — Chroma collection 이 `hnsw:space=cosine` 으로 생성된 가정 (mapper.py:296-297 주석).
  - 반환 dict 키 = `{wa, l6_main, score}` 만 — `doc_text` 등 raw 는 제외 (FE 가 별도 SELECT 시 join).
  - 정렬 안정성: Python `sorted` 는 stable — 동일 score 시 candidates 순서 유지 (Chroma 검색 순서 = 기본 distance 오름차순).
- **대응 패턴**:
  - 발동: `map_activity` 의 ⑥ 단계 (정상 LLM choice 통과 후)
  - 입력: 누적 candidates list (Chroma top_k 까지 + max_candidates 컷오프)
  - 처리: `sorted(candidates, key=lambda c: c["score"], reverse=True)[:k]` → `{wa, l6_main, score}` map
  - 출력: `list[dict]` (≤ K 길이, 비어있을 수 있음)
- **관련**:
  - 호출자: `map_activity:393`
  - PG INSERT 경로: `mapper_activities.alternatives` 컬럼 (db.py:652 / 693 / 727 부근)
  - 마이그: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql`
  - FE 소비처: `web/app/sites/[id]/review` (B_Track) — alternatives jsonb 를 `<select>` options 로 렌더

#### M-G23-2 — HIL 경로의 alternatives 미적용

- **위치**: `pipeline/agents/mapper.py:311-319` (Chroma empty) + `pipeline/agents/mapper.py:351-358` (LLM JSON parse fail) + `pipeline/agents/mapper.py:362-369` (choice out-of-range) 3 군데.
- **이슈**:
  - 본 cycle 의도적 설계 — `requires_review=True` 로 빠지는 3 HIL 경로는 `alternatives` 키를 return dict 에 안 채움.
  - PG INSERT 시 컬럼이 빠지면 DB DEFAULT '[]' (마이그) 적용 → FE 가 "후보 0개" 로 정상 표시.
- **설계 의도**:
  - HIL 경로 = 자동 매핑 실패 = candidates 자체가 의미 없는 상태 (빈 / LLM 거절 / 범위 밖). 그 candidates 의 top-K 를 보여주는 건 사용자 혼란.
  - FE 가 후보 0개일 때 자유 입력 필드만 노출 (B_Track 의 design 의도).
  - 의도된 silent — assertion 안 함, DB DEFAULT 가 안전망.
- **대응 패턴**:
  - 발동: HIL 3 경로 진입
  - 입력: 동일
  - 처리: return dict 에 alternatives 키 생략
  - 출력: PG row 의 alternatives = '[]'::jsonb
- **관련**:
  - 페어 카드: M-G23-1 (정상 path)
  - DB DEFAULT: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql`
- **Suspected related** (2026-05-19 stale):
  - LLM JSON parse fail 경로 (mapper.py:351) 에서도 일부 candidates 는 의미 있을 수 있음 — 후속 cycle 에서 "LLM fail 이지만 top-K score 자체는 노출" 옵션 검토 가능 (drift backlog, low).

#### M-G23-3 — score 음수 가능성

- **위치**: `pipeline/agents/mapper.py:304` (`"score": 1.0 - dist`).
- **이슈**:
  - Chroma cosine distance ∈ [0, 2] (벡터가 반대 방향이면 dist=2 → score=-1). 실제로는 임베딩 모델 (text-embedding-3-small) 출력의 코사인 유사도가 음수 영역에 들어가는 케이스가 드물지만 이론상 가능.
  - 본 cycle 검증 (run_id=627e2c4d) 의 6 row 에서는 score ∈ [0.32, 0.78] 관측 — 음수 미발생.
- **설계 의도**:
  - cosine 정의 그대로 노출 (clamp 없음) — 본 cycle 의도. clamping 은 FE 책임으로 위임 (`max(0, score)` 또는 progress bar 음수 처리).
  - score 가 음수면 사용자에게도 "매우 부적합" 신호로 의미 있음 — backend 에서 0 으로 깎으면 정보 손실.
- **대응 패턴**:
  - 발동: `map_activity` ③ 단계
  - 입력: Chroma distance float
  - 처리: `1.0 - dist` 직역
  - 출력: float (음수 가능)
- **관련**:
  - FE clamping: `web/app/sites/[id]/review` (B_Track) 의 progress bar / 색상 매핑 검토 필요 (drift backlog #FE-score-clamp).
- **Suspected related** (2026-05-19 stale, Drift backlog):
  - Chroma collection `hnsw:space` 확인 — `cosine` 이 아니라 `l2` 인 경우 distance range 가 [0, ∞) → score 가 매우 큰 음수. `pipeline/chroma_client.py` 의 collection 생성 시 metadata 검증 후 cycle. low priority.
