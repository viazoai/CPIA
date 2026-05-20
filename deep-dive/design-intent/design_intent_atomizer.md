# Design Intent — atomizer

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Last checked**: 2026-05-20 (git SHA: `ef7c6cd`) — **코드 변경 없음** (cf3c143 이후 commit 0). T1/T2 카드 그대로 유효.
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/agents/atomizer.py` (141 LOC, 이전 118 → +23 docstring + None 가드) + `pipeline/tests/test_atomizer.py` + `pipeline/tests/test_atomizer_atomized_count.py` + `pipeline/tests/test_atomizer_mapped_history.py`
- **Note**: 이전 cycle (cf3c143) 에 흡수된 안전 처리 hotfix — None work_content/conditions filter 가드.

Mapper 출력 Activity → Azure 임베딩 → Chroma `daily_activities` 적재. LLM 호출 없음, 임베딩만. 결정성 doc_id (SHA256 16자) + within-call dedup + fail-fast PG 검증.

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `AtomizerConfig` | atomizer.py:24 | `@dataclass` | Azure 크레덴셜 + Chroma host + batch/timeout/dim 설정 | ✅ |
| `_make_doc_id` | atomizer.py:39 | `(date, company, l6_main, work_content) -> str` | 결정성 doc id (SHA256 16자 prefix) | ✅ |
| `_build_metadata` | atomizer.py:45 | `(a: Activity, date, run_id) -> dict[str, Any]` | Activity → Chroma metadata dict (12 필드 스칼라) | ✅ |
| `atomize` | atomizer.py:62 | `async (mapped, parsed_report, run_id, cfg) -> list[str]` | Mapper output → Chroma upsert (공개 API) | ✅ |

---

## T2 — Issue Cards

### `atomize` — Chroma 적재 공개 API

- **위치**: `pipeline/agents/atomizer.py:62-118` (57 LOC, 분기 3)
- **시그니처**: `async def atomize(mapped: list[Activity], parsed_report: ParsedDailyReport, run_id: uuid.UUID, cfg: AtomizerConfig) -> list[str]`
- **이슈**:
  - git log `1cff755` (atomizer: mapped → Chroma daily_activities 적재 (LLM 없음, 임베딩만)) — 최초.
  - git log `282309b` (atomizer/db: code quality fixes (fail-fast + test value)) — fail-fast PG 검증 추가, Azure embedding 전 호출하여 cost/orphan 방지.
  - docstring (atomizer.py:62): "mapped → Chroma daily_activities 적재. atomized_ids 반환. Spec §4.5."
  - 인라인 주석 (atomizer.py:71-73): "fail-fast: pipeline_runs row 미존재 시 Azure embedding / Chroma upsert 전 즉시 raise. 같은 PG connection 을 끝까지 재사용하여 update_run_atomized_count 까지 단일 try/finally 안에서 처리한다."
  - 인라인 주석 (atomizer.py:85-89): "doc_id 는 (date, company, l6_main, work_content) hash — 같은 BP사가 같은 l6 에 같은 work_content 를 여러 번 적은 경우 (예: 남웅 47 row → 11 unique work_content) 동일 doc_id 가 생성된다. Chroma 0.5.20 upsert/get 은 within-call 중복 id 를 거부 → 단일 호출 내에서 미리 dedup (마지막 등장 metadata 채택)."
- **설계 의도**:
  - fail-fast: Azure embedding (과금) 전에 PG row 존재 확인 → orphan Chroma row 방지.
  - resource 일관성: PG connection 1개를 `assert_pipeline_run_exists` → Chroma upsert → `update_run_atomized_count` 까지 단일 try/finally 로 묶음 (leak 방지).
  - within-call dedup: Chroma 0.5.20 의 upsert 가 같은 batch 내 중복 id 거부 → Python 단에서 dedup. 마지막 등장 metadata 채택 (Chroma upsert semantics 와 일치).
  - 결정성: 같은 입력 → 같은 doc_id, idempotent upsert (실 테스트: `test_atomize_upsert_idempotent`).
- **대응 패턴**:
  - 발동: `graph.py:atomizer_node` 가 호출
  - 입력: mapped Activity list + parsed_report (report_date 추출용) + run_id + cfg
  - 처리: valid filter (l6_main is not None) → PG fail-fast → doc_id dedup → Azure embedding batch → Chroma upsert → PG count UPDATE
  - 출력: atomized_ids (dedup 후 unique id list)
- **관련**:
  - `_make_doc_id` / `_build_metadata` (내부 헬퍼)
  - `chroma_client.py:get_or_create_daily_activities:30`
  - `db.py:assert_pipeline_run_exists:127` + `db.py:update_run_atomized_count:183`
  - 테스트: `test_atomizer.py:133-271` (5 케이스: empty / skip_unmapped / namwong_47 / upsert_idempotent / missing_run_raises)
  - 페어 spec: `docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §4`
- **Suspected related** (2026-05-17 stale):
  - Forecaster `_forecast_one_group` 의 Chroma query — 본 함수가 적재한 동일 컬렉션 검색.
  - Optimizer `retrieve.py:fetch_degradation_cases` — 동일 컬렉션 metadata 필터링.

---

### `_make_doc_id` — 결정성 SHA256 16자 prefix

- **위치**: `pipeline/agents/atomizer.py:39-42` (4 LOC)
- **시그니처**: `def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str`
- **이슈**:
  - docstring (atomizer.py:39): "결정성 doc id — spec §4.2 (✓ Verified `73ff80435e312c41` for sample)."
  - 테스트 (atomizer.py:test_make_doc_id_determinism:48-52): "남웅건설 + 철근콘크리트공사 + 기초 거푸집 설치 + 2025-09-25 → 73ff80435e312c41" hardcoded 검증.
- **설계 의도**:
  - 결정성: 4-tuple → 항상 같은 id (SHA256 순수 함수). 실행 reproducibility 보장.
  - 16 hex (64-bit) 충분히 unique — Chroma 인덱싱 효율.
  - 같은 work_content 반복 입력 시 upsert (수정) semantics — 새 row 추가 아님.
- **대응 패턴**:
  - 발동: `atomize` 내부에서 valid row 마다
  - 입력: date + company + l6_main + work_content (4 str)
  - 처리: pipe join → SHA256 → hex[:16]
  - 출력: 16자 hex str
- **관련**:
  - `atomize` 호출자
  - 테스트: `test_atomizer.py:48-66` (determinism + changes + format 3 케이스)
- **Suspected related** (2026-05-17 stale):
  - site_id 미포함 — multi-site 운영 진입 시 ID schema 변경 후보.

---

### `_build_metadata` — Activity → Chroma metadata 12 필드

- **위치**: `pipeline/agents/atomizer.py:45-59` (15 LOC)
- **시그니처**: `def _build_metadata(a: Activity, date: str, run_id: str) -> dict[str, Any]`
- **이슈**:
  - 필드 12개: `date, run_id, company, l5_disc, l6_main, wa, unit, today_qty, assigned_workers, worker_source, mapping_conf, conditions`.
  - `conditions` CSV 변환 (atomizer.py:57): `",".join(a["conditions"])` — list → str.
  - None 처리: `l6_main or ""`, `wa or ""`, `mapping_conf or 0.0` (atomizer.py:51-55).
- **설계 의도**:
  - Chroma metadata 는 scalar 만 허용 (list/dict X) → CSV string 으로 평탄화. 검색 단에서는 substring in 으로 역검증 (`retrieve.py:fetch_degradation_cases`).
  - None 안전: filter/group 시 NoneType 에러 방지를 위해 "" / 0.0 캐스트.
  - run_id 박힘: 운영 감사 + 디버깅 trace.
- **대응 패턴**:
  - 발동: `atomize` 내부 각 Activity 마다
  - 입력: 1 Activity + date + run_id str
  - 처리: 12 필드 dict 구성 (None → 빈 문자열/0.0)
  - 출력: Chroma metadata dict
- **관련**:
  - `atomize:62`
  - `forecaster/rerank.py:_normalize_chroma_metadata:20` (역정규화 — CSV → list 복원)
  - 테스트: `test_atomizer.py:67-84` (3 케이스: scalar / conditions_csv / none_to_empty_string)
- **Suspected related** (2026-05-17 stale):
  - `rerank.py:_normalize_chroma_metadata` — 본 함수의 CSV → list 역정규화 책임.
  - audit drift D-6 (recovery_distribution conditions 필터) — 본 함수의 conditions CSV 표현이 source.

---

### `AtomizerConfig` — Azure/Chroma 설정 + batch/timeout

- **위치**: `pipeline/agents/atomizer.py:24-37` (14 LOC)
- **시그니처**: `@dataclass class AtomizerConfig`
- **이슈**:
  - 필드: `azure_endpoint / azure_api_key / azure_api_version / embedding_model / postgres_url / chroma_host / chroma_port / chroma_ssl=False / batch_size=16 / azure_timeout=30.0 / azure_max_retries=3 / embedding_dim=1536`.
  - git log `1cff755` 초기 — 9개 필드 → `282309b` 에서 구조 변경 없음.
- **설계 의도**:
  - batch_size=16: Azure embedding 배치 API 의 cost vs timeout 균형 (large batch = timeout 위험).
  - `embedding_dim=1536`: text-embedding-3-small 차원. 현재 코드에서 직접 사용 X — Chroma cold start 시 참고용 (의심: 미사용 가능).
  - retry 3 — 일시 실패 대비.
- **대응 패턴**:
  - 발동: `GraphConfig.atomizer` 에 박힘
  - 입력: 없음
  - 처리: dataclass init
  - 출력: instance
- **관련**:
  - `graph.py:GraphConfig:33`
  - 테스트: `test_atomizer.py:91-92` (cfg fixture)
- **Suspected related** (2026-05-17 stale):
  - `embedding_dim=1536` 의 실 소비처 미확인. dead field 가능성.

---

## 관찰

- **LLM 호출 없음**: 임베딩만 (Azure embeddings.create). LLM 비용 0.
- **한자 사용 0건** (자료 없음 — grep 결과 한글 + 영문 + 숫자만).
- **TODO/FIXME 없음** (grep 결과 0건).
- **테스트 커버리지**: 11 케이스 (unit 6 + integration 5), 결정성 + idempotency + fail-fast 모두 검증.
- **임베딩 텍스트 = work_content 단독**: documents 는 work_content (atomizer.py:101), metadata 는 별개. 도메인 의미 유사도 중심 설계.
- **`embedding_dim` 의심**: AtomizerConfig 필드만 있고 코드 내 사용처 grep 결과 미발견. cold start 참고용 또는 dead field.

---

## 2026-05-19 FE↔BE 연결 + 6 BE 적재 보완 cycle 변경 (Git SHA cf3c143)

### T1 갱신

- `_build_metadata` (atomizer.py:45) — "conditions get default [] 안전 처리": `",".join(a.get("conditions") or [])` (atomizer.py:58). 이전 `a["conditions"]` → KeyError 회피.
- `atomize` (atomizer.py:62) — "valid 필터: l6_main 외 work_content truthy 추가": `valid = [a for a in mapped if a["l6_main"] is not None and a.get("work_content")]` (atomizer.py:69). 빈 work_content 인 mapper 산출 row 를 Azure embedding 호출 전 제거.

### T2 신규 카드

#### A-N1: work_content 빈 activity skip

- **위치**: `pipeline/agents/atomizer.py:69` (valid 필터 라인 1줄, 단 atomize 의 전제 조건 변경)
- **변경 라인**: `valid = [a for a in mapped if a["l6_main"] is not None and a.get("work_content")]`
- **이슈**:
  - 본 cycle 신규 (PR #28, 2026-05-19) — 이전 cycle 까지는 `l6_main is not None` 만 검사, work_content=None 인 mapper 출력 row 가 valid 에 포함됐음.
  - 실 prod cycle 에서 mapper 출력 일부에 work_content=None 발생 (parser LLM 의 누락 케이스). Azure embedding API 가 input 의 빈 string / None 에 HTTP 400.
- **설계 의도**:
  - Azure embedding pre-call guard — 빈 input list 가 들어가지 않도록 valid 단계에서 제거.
  - mapped_history INSERT 의 `mh_valid = [...l6_main is not None and wa is not None]` 필터 (atomizer.py:116) 와 동일 패턴 → 둘 다 fail-fast 책임을 atomizer 가 가짐.
  - parser/mapper 의 work_content 누락 책임은 별 cycle (mapper drift) — atomizer 는 일단 통과만 시킴.
- **대응 패턴**:
  - 발동: `atomize` 진입 시 즉시.
  - 입력: mapped Activity list.
  - 처리: l6_main not None AND work_content truthy 검사.
  - 출력: valid Activity list (이후 fail-fast / dedup / embedding 모두 이 위에서 수행).
- **관련**:
  - mapped_history 의 wa/l6_main 필터 (atomizer.py:116) — 자매 필터.
  - 실 검증: run_id=627e2c4d (2026-05-19) 에서 mapped row 일부가 work_content=None → valid 통과 4/N, atomized_count=4.
- **Suspected related** (2026-05-19 stale):
  - 본 cycle 은 atomizer-only 회피. parser LLM 단의 work_content 누락 자체는 mapper drift backlog 별도.
  - Forecaster 의 동일 가드 (F-N1) — 같은 None 입력에 양쪽 모두 방어 (이중 안전망).

#### A-N2: conditions None 안전 처리

- **위치**: `pipeline/agents/atomizer.py:58`
- **변경 라인**: `"conditions": ",".join(a.get("conditions") or []),`
- **이슈**:
  - 본 cycle 신규 (PR #28, 2026-05-19) — 이전 코드는 `",".join(a["conditions"])` → mapper 가 conditions 키를 set 안 한 경우 KeyError.
  - state.py 의 Activity TypedDict 정의에는 conditions 키 있으나 mapper 의 일부 path 에서 누락 (특히 default fallback).
- **설계 의도**:
  - 방어적 dict 접근: `a.get("conditions") or []` — None / 누락 모두 빈 list 로 fallback.
  - Chroma metadata 의 conditions 컬럼은 CSV 평탄화 — 빈 list → 빈 str. 검색 단 (forecaster `_normalize_chroma_metadata`) 는 빈 str 도 list[] 로 역변환 가능.
  - 책임 분리: 본 함수는 conditions 누락 책임을 mapper 에 묻지 않고 그냥 빈 값으로 처리 (atomizer 가 mapper drift 의 buffer 역할).
- **대응 패턴**:
  - 발동: `_build_metadata` 내부 (atomize 의 각 valid row 마다).
  - 입력: Activity dict.
  - 처리: `.get("conditions") or []` 로 빈 list fallback → `",".join(...)`.
  - 출력: 빈 str 또는 CSV str.
- **관련**:
  - state.py Activity TypedDict — conditions 키 정의 위치.
  - mapper.py — conditions 누락 path (drift, 별 cycle).
  - Forecaster F-N2 — 동일 패턴 (atomizer 와 forecaster 양쪽에 같은 가드).
- **Suspected related** (2026-05-19 stale):
  - mapper 의 conditions 누락 자체는 별 cycle — mapper drift backlog 에 등록 필요.
