# Design Intent — atomizer

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Last updated**: 2026-05-26 (HEAD `1ba783f`) — **본 cycle 활발히 변경됨** (이전 "코드 변경 없음" 라벨 무효화).
  - atomizer 직접 commit 3건: `a3db32a` (Chroma init retry + upsert batch=100 split, HNSW hang 방어) / `9252ac7` (`_format_document` 신규 + `_build_metadata` 12→15 필드) / `b560dd4` (batch_size 16→64)
  - 인접 migration 1건: `16f1b88` (`mapped_history.trade` 컬럼 신설, atomizer.py 코드 미반영 → 이슈 A-N3)
- **Pair file**: `../deep_dive_atomizer.md` (524 LOC, 본 카드 갱신의 입력 자료)
- **Range**: `pipeline/agents/atomizer.py` (196 LOC, 이전 141 → +55) + `pipeline/tests/test_atomizer.py` (271 LOC) + `pipeline/tests/test_atomizer_atomized_count.py` (29 LOC) + `pipeline/tests/test_atomizer_mapped_history.py` (288 LOC) + `infra/postgres/migrations/2026-05-18_mapped_history.sql` + `infra/postgres/migrations/2026-05-19_mapped_history_trade.sql`

Mapper 출력 Activity → Azure 임베딩 → Chroma `daily_activities` + PG `mapped_history` 적재. LLM 호출 없음, 임베딩만. 결정성 doc_id (SHA256 16자) + within-call dedup + fail-fast PG 검증 + Chroma init 3 retry + HNSW hang 방어 (upsert 100 doc split) + mapped_history 조건부 INSERT (`wa AND l6_main` 둘 다 not None).

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `AtomizerConfig` | atomizer.py:24 | `@dataclass` (12 필드) | Azure 크레덴셜 + Chroma host + batch=64/timeout/dim 설정 | ✅ |
| `_make_doc_id` | atomizer.py:42 | `(date, company, l6_main, work_content) -> str` | 결정성 doc id (SHA256 16자 prefix) | ✅ |
| `_build_metadata` | atomizer.py:48 | `(a: Activity, date, run_id) -> dict[str, Any]` | Activity → Chroma metadata dict (★ 12→15 필드, l7_5_activity / perperson / productivity_pct 추가) | ✅ |
| `_format_document` (★ NEW 9252ac7) | atomizer.py:71 | `(a: dict, date, perperson=None, productivity_pct=None) -> str` | 사람이 읽을 수 있는 doc 텍스트 (live / backfill 2 모드) | ✅ |
| `atomize` | atomizer.py:93 | `async (mapped, parsed_report, run_id, cfg) -> list[str]` | Mapper output → Chroma upsert + mapped_history INSERT + count UPDATE (공개 API) | ✅ |

---

## T2 — Issue Cards

### `atomize` — Chroma + mapped_history 적재 공개 API

- **위치**: `pipeline/agents/atomizer.py:93-196` (104 LOC, 분기 6 — 본 cycle +47 LOC)
- **시그니처**: `async def atomize(mapped: list[Activity], parsed_report: ParsedDailyReport, run_id: uuid.UUID, cfg: AtomizerConfig) -> list[str]`
- **본 cycle 변경** (2026-05-26 갱신):
  - `a3db32a` (2026-05-20): Chroma init 3 retry (`atomizer.py:145-157`) + upsert 100 doc split (`atomizer.py:160-167`). 이전 1000+ doc 통째 upsert 가 HNSW build 단계에서 4시간 hang 한 사례 (cycle 153bfa17/d38605f9) 가 commit 메시지에 명시.
  - `9252ac7` (2026-05-21): `documents` 가 `work_content` 단독 임베딩 → `_format_document` 결과 (자연어 헤더+본문). 임베딩 의미 유사도가 단어 수준 → 문장 수준으로 격상.
  - `b560dd4` (2026-05-22): Azure embedding batch 13회 → 4회 (200 doc 기준).
  - `16f1b88` (인접): mapped_history.trade 컬럼 신설 commit 이 "atomizer.py:130 mh_rows 생성 시 Activity.trade 박기" 약속했으나 atomizer.py:179-189 mh_rows dict 와 `insert_mapped_history_batch` SQL 둘 다 trade 키 누락 → trade 컬럼 항상 NULL (이슈 A-N3).
- **이슈** (누적):
  - git log `1cff755` (atomizer: mapped → Chroma daily_activities 적재, 최초)
  - git log `282309b` (fail-fast + test value 추가)
  - git log `cf3c143` (work_content/conditions None 가드 → A-N1, A-N2)
  - git log `a3db32a` / `9252ac7` / `b560dd4` (본 cycle 3건)
  - docstring (atomizer.py:99): "mapped → Chroma daily_activities 적재. atomized_ids 반환. Spec §4.5."
  - 인라인 주석 (atomizer.py:106-108): "fail-fast: pipeline_runs row 미존재 시 Azure embedding / Chroma upsert 전 즉시 raise. 같은 PG connection 을 끝까지 재사용하여 update_run_atomized_count 까지 단일 try/finally 안에서 처리한다."
  - 인라인 주석 (atomizer.py:122-125): "doc_id 는 (date, company, l6_main, work_content) hash — 같은 BP사가 같은 l6 에 같은 work_content 를 여러 번 적은 경우 (예: 남웅 47 row → 11 unique) 동일 doc_id → Chroma 0.5.20 upsert 가 within-call 중복 id 거부 → Python 단 dedup (마지막 등장 metadata 채택)."
  - 인라인 주석 (atomizer.py:142-144): "ChromaClient init 의 user_identity HTTP 호출 timeout (Errno 60) 방어. 첫 init cold start latency + network 변동을 위해 3 retry + exponential backoff."
  - 인라인 주석 (atomizer.py:158-159): "Chroma 0.5.20 batch 권장 100 doc. 1000+ doc 통째 upsert 시 HNSW build hang 위험 (이전 cycle 153bfa17/d38605f9 4시간 stuck 사례)."
- **설계 의도**:
  - **fail-fast**: Azure embedding (과금) 전에 PG row 존재 확인 → orphan Chroma row 방지.
  - **resource 일관성**: PG connection 1개를 `assert_pipeline_run_exists` → Chroma upsert → `insert_mapped_history_batch` → `update_run_atomized_count` 까지 단일 try/finally 로 묶음 (asyncpg pool leak 방지).
  - **within-call dedup**: Chroma 0.5.20 의 upsert 가 같은 batch 내 중복 id 거부 → Python 단에서 dedup. 마지막 등장 metadata 채택.
  - **결정성**: 같은 입력 → 같은 doc_id, idempotent upsert (테스트: `test_atomize_upsert_idempotent`).
  - **HNSW hang 방어 (★ 본 cycle)**: 100 doc 단위 upsert split 으로 Chroma 0.5.20 의 HNSW build hang 우회.
  - **2단계 적재 (★ 본 cycle 강화)**: Chroma valid (`l6_main is not None AND work_content truthy`) 와 mapped_history valid (`l6_main is not None AND wa is not None`) 는 **다른 필터** — mapped_history 는 wa 미매핑 row 제외 (WBS 매핑 완료된 것만 누적 — Phase 3 결정).
- **대응 패턴**:
  - 발동: `graph.py:atomizer_node` 가 호출 (production graph + b560dd4 cycle 신규 `build_atomized_demo_graph` 양쪽)
  - 입력: mapped Activity list + parsed_report (report_date 추출용) + run_id + cfg
  - 처리: valid filter → PG fail-fast → doc_id dedup → `_format_document` doc 텍스트 빌드 → Azure embedding batch (64) → Chroma init 3 retry → Chroma upsert 100 doc split → mapped_history 조건부 INSERT → PG count UPDATE
  - 출력: atomized_ids (dedup 후 unique id list)
- **관련**:
  - `_make_doc_id` / `_build_metadata` / `_format_document` (★ NEW) (내부 헬퍼)
  - `chroma_client.py:get_or_create_daily_activities:30`
  - `db.py:assert_pipeline_run_exists:176` + `db.py:get_pipeline_run:504` + `db.py:insert_mapped_history_batch:458` + `db.py:update_run_atomized_count:238`
  - 테스트: `test_atomizer.py` (11 케이스) + `test_atomizer_atomized_count.py` + `test_atomizer_mapped_history.py` (4 케이스)
  - 페어 spec: `docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §4`
- **Suspected related** (2026-05-26 갱신):
  - Forecaster `_forecast_one_group` 의 Chroma query — 본 함수가 적재한 동일 컬렉션 검색.
  - Optimizer `retrieve.py:fetch_degradation_cases` — `pipeline/agents/optimizer/retrieve.py:13` 의 "conditions 는 atomizer 와 동일 comma-joined str (결정 #19)" 주석이 본 함수의 CSV 평탄화 표현에 직접 의존.

---

### `_make_doc_id` — 결정성 SHA256 16자 prefix

- **위치**: `pipeline/agents/atomizer.py:42-45` (4 LOC) — 본 cycle 변경 없음
- **시그니처**: `def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str`
- **이슈**:
  - docstring (atomizer.py:43): "결정성 doc id — spec §4.2 (✓ Verified `73ff80435e312c41` for sample)."
  - 테스트 (`test_atomizer.py:48-52`): "남웅건설 + 철근콘크리트공사 + 기초 거푸집 설치 + 2025-09-25 → 73ff80435e312c41" hardcoded 검증.
- **설계 의도**:
  - 결정성: 4-tuple → 항상 같은 id (SHA256 순수 함수). 실행 reproducibility 보장.
  - 16 hex (64-bit) 충분히 unique — Chroma 인덱싱 효율.
  - 같은 work_content 반복 입력 시 upsert (덮어쓰기) semantics — 새 row 추가 아님.
  - **★ 본 cycle 함의**: `_format_document` 결과가 바뀌어도 doc_id 는 `work_content` 만 hashing → backfill (Task 13) 이 풀 형식으로 upsert 해도 같은 row 갱신 (idempotent invariant).
- **대응 패턴**:
  - 발동: `atomize` 내부에서 valid row 마다
  - 입력: date + company + l6_main + work_content (4 str)
  - 처리: pipe join → SHA256 → hex[:16]
  - 출력: 16자 hex str
- **관련**:
  - `atomize` 호출자
  - 테스트: `test_atomizer.py:48-66` (determinism + changes + format 3 케이스)
- **Suspected related**:
  - site_id 미포함 — multi-site 운영 진입 시 ID schema 변경 후보 (PoC 단계는 1 site 가정, 본 cycle 검증 미실시).

---

### `_build_metadata` — Activity → Chroma metadata 15 필드 (★ 본 cycle 12→15 확장)

- **위치**: `pipeline/agents/atomizer.py:48-68` (21 LOC, 이전 15 → +6)
- **시그니처**: `def _build_metadata(a: Activity, date: str, run_id: str) -> dict[str, Any]`
- **본 cycle 변경** (`9252ac7`, 2026-05-21):
  - 필드 12 → 15 확장: `l7_5_activity` (Mapper Task 6 결과, live atomize 시점에 채워짐) + `perperson` (live=0 placeholder, backfill Task 13 에서 view_builder 산식 결과) + `productivity_pct` (동일)
  - None 가드 강화: `a.get("perperson", 0) or 0` 이중 가드 (atomizer.py:63-64) — `.get(default=0)` 가 None 반환 케이스 (key 존재하지만 값이 None) 까지 방어
  - docstring 신설 (atomizer.py:49-51): "Phase 1 (2026-05-21): l7_5_activity + perperson + productivity_pct 추가. live atomize 시점엔 perperson/productivity_pct=0 placeholder, backfill (Task 13) 에서 view_builder 산식 결과로 풀 값 채움."
- **이슈** (누적):
  - 필드 15개 (★ 갱신): `date, run_id, company, l5_disc, l6_main, l7_5_activity, wa, unit, today_qty, assigned_workers, perperson, productivity_pct, worker_source, mapping_conf, conditions`.
  - `conditions` CSV 변환 (atomizer.py:67): `",".join(a.get("conditions") or [])` — list → str (cf3c143 cycle 의 A-N2 None 가드 유지).
  - None 처리: `l6_main or ""` / `l7_5_activity or ""` / `wa or ""` / `mapping_conf or 0.0` (atomizer.py:57-66).
- **설계 의도**:
  - Chroma metadata 는 scalar (str/int/float/bool) 만 허용, list/dict 금지 → CSV string 으로 평탄화. 검색 단에서는 substring in 으로 역검증 (`forecaster/rerank.py:_normalize_chroma_metadata`).
  - None 안전: filter/group 시 NoneType 에러 방지를 위해 "" / 0.0 캐스트.
  - run_id 박힘: 운영 감사 + 디버깅 trace.
  - **★ Phase 1 의도 (perperson/productivity_pct live=0)**: live atomize 시점엔 마스터 비교값 없음 → placeholder 0 으로 적재. backfill Task 13 이 동일 doc_id 로 풀 값 upsert 하면 자연스럽게 갱신. doc_id idempotency 보장 (위 `_make_doc_id` 카드 참조).
  - **★ l7_5_activity 의도**: Mapper Task 6 의 l7.5 결정 결과를 Chroma 검색 metadata 에 노출 → Forecaster / Optimizer 가 l6_main + l7.5 동시 필터 가능.
- **대응 패턴**:
  - 발동: `atomize` 내부 각 valid Activity 마다
  - 입력: 1 Activity + date + run_id str
  - 처리: 15 필드 dict 구성 (None → 빈 문자열/0.0)
  - 출력: Chroma metadata dict
- **관련**:
  - `atomize:93`
  - `forecaster/rerank.py:_normalize_chroma_metadata:20` (역정규화 — CSV → list 복원)
  - 테스트: `test_atomizer.py:67-84` (3 케이스: scalar / conditions_csv / none_to_empty_string) — **★ 본 cycle l7.5/perperson/productivity_pct 추가 케이스 미실시 (검증 pending)**
- **Suspected related** (2026-05-26 갱신):
  - `rerank.py:_normalize_chroma_metadata` — CSV → list 역정규화 책임.
  - audit drift D-6 (recovery_distribution conditions 필터) — 본 함수의 conditions CSV 표현이 source.
  - **★ NEW**: view_builder backfill Task 13 (perperson / productivity_pct 산식 적재 책임) — 본 함수는 live placeholder 만, 풀 값은 backfill 이 채움.

---

### `_format_document` — 사람이 읽을 수 있는 doc 텍스트 (★ NEW 9252ac7)

- **위치**: `pipeline/agents/atomizer.py:71-90` (20 LOC, 본 cycle 신규)
- **시그니처**: `def _format_document(a: dict, date: str, perperson: float | None = None, productivity_pct: float | None = None) -> str`
- **본 cycle 신규** (`9252ac7`, 2026-05-21):
  - 이전 임베딩 텍스트 = `valid[i]["work_content"]` 단독 (atomizer.py 직전 commit) → 사람이 읽을 수 있는 헤더 + 본문 형식으로 변경.
  - 도메인 의미 유사도가 work_content 단어에만 의존해 일반화 부족 → 문장 수준 임베딩으로 격상.
- **이슈**:
  - docstring (atomizer.py:77-80): "ChromaDB 문서 텍스트. 2 모드 분기 (C6): live (atomize 호출): perperson=None -> 짧은 형식 (마스터 비교값 없음). backfill (Task 13 호출): perperson=값 -> 풀 형식 (인당 + %)."
  - 2 모드 출력:
    - live: `[2025-09-25] 남웅건설 · 철근콘크리트공사 · 기초 거푸집 설치` / `시공량 12.5 ㎥ / 인원 8 명` / `조건: 정상`
    - backfill: 동일 head + body 에 `-> 인당 1.56 ㎥/인 (78.0%)` 추가
  - 분기 조건 (atomizer.py:87): `if perperson is None or productivity_pct is None or not unit` → short form fallback. **unit 빈 str 시 backfill 모드 무시** (이슈 A-N5).
  - `conds` 가 빈 list 면 "정상" 으로 fallback (atomizer.py:84).
- **설계 의도**:
  - 임베딩 의미 유사도를 단어 → 문장 수준으로 격상. Forecaster / Optimizer 의 유사 이력 검색 품질 개선.
  - **2 모드 의도**: live 시점엔 마스터 비교값 (perperson / productivity_pct) 이 없음 → short form. backfill (Task 13) 이 view_builder 산식 결과로 동일 doc_id 를 풀 form 으로 upsert.
  - doc_id idempotency 보장 (위 `_make_doc_id` 카드 참조) → documents 형식이 바뀌어도 같은 row 갱신.
  - `head.rstrip(" ·")` — l6_main 또는 l7_5_activity 가 빈 str 일 때 trailing `·` 제거 (가독성).
- **대응 패턴**:
  - 발동: `atomize` (live, atomizer.py:133) + Task 13 backfill (다른 모듈)
  - 입력: Activity dict + date (+ perperson + productivity_pct in backfill)
  - 처리: head 빌드 → body_basic 빌드 → perperson 분기 → 3 줄 자연어 텍스트 합성
  - 출력: 사람이 읽을 수 있는 multi-line str (Azure embedding input)
- **관련**:
  - `atomize:133` (live 호출자)
  - view_builder backfill Task 13 (backfill 호출자, 다른 모듈)
  - `forecaster/rerank.py` (본 텍스트가 임베딩 source 라는 점에서 검색 품질에 영향)
- **Suspected related**:
  - **A-N5 (M)**: unit 빈 str 시 backfill 모드 무시 — unit None 인 Activity 비율 측정 필요.
  - chroma_client.py:31 docstring "doc text = work_content" 가 본 cycle 이후 stale (이슈 A-N7).

---

### `AtomizerConfig` — Azure/Chroma 설정 + batch=64/timeout

- **위치**: `pipeline/agents/atomizer.py:24-39` (16 LOC, 이전 14 → +2)
- **시그니처**: `@dataclass class AtomizerConfig` (12 필드)
- **본 cycle 변경** (`b560dd4`, 2026-05-22):
  - `batch_size: int = 64` (이전 16). 인라인 주석 (atomizer.py:34-36): "Azure embedding input limit 2048, 64 안전. 1일 cycle ~200 doc 이 1 batch."
  - 1일 cycle ~200 doc 기준: 13 batch (16) → 4 batch (64) → **Azure HTTP 호출 ¼**.
  - cycle `888c535d` (a3db32a commit msg): 1162 mapped row → mh=285 → atomized=64 (dedup 후) → 19분 1초 cycle. 본 batch 변경 이후 호출 횟수 절감.
- **이슈** (누적):
  - 필드 12개: `azure_endpoint / azure_api_key / azure_api_version / embedding_model / postgres_url / chroma_host / chroma_port / chroma_ssl=False / batch_size=64 (★) / azure_timeout=30.0 / azure_max_retries=3 / embedding_dim=1536`.
  - git log `1cff755` 초기 → `282309b` 구조 변경 없음 → `b560dd4` batch_size 만 변경.
- **설계 의도**:
  - **batch_size=64 (★ 본 cycle)**: Azure embedding input array limit 2048 (Azure docs) 의 안전 margin. 1000 doc 도 4 batch 만에 처리. 단일 batch 가 커지면 HTTP timeout (30s) 위험 증가하지만 doc 본문이 짧아 (3 줄 자연어) 64 는 안전. `cfg.azure_timeout=30.0 + max_retries=3` 가 backup.
  - `embedding_dim=1536`: text-embedding-3-small 차원. 코드 내 직접 소비처 grep 결과 없음 — dead field 의심 (이슈 A-N6, design-intent 이전 stale 그대로 유효).
  - retry 3 — 일시 실패 대비.
- **대응 패턴**:
  - 발동: `GraphConfig.atomizer` 에 박힘 (`graph.py:44`)
  - 입력: 없음
  - 처리: dataclass init
  - 출력: instance
- **관련**:
  - `graph.py:GraphConfig:44`
  - 테스트: `test_atomizer.py:91-92` (cfg fixture)
- **Suspected related** (2026-05-26 갱신):
  - **A-N6**: `embedding_dim=1536` 의 실 소비처 미확인. 다음 cycle 삭제 또는 Chroma init 차원 검증에 사용.
  - **A-N8**: `_CHROMA_UPSERT_BATCH = 100` 이 함수 내부 hardcoded — config 외부화 안 됨. HNSW hang 재현 시 즉시 조정 어려움 → AtomizerConfig 에 `chroma_upsert_batch: int = 100` 필드 추가 검토.
  - **A-N9**: Chroma init retry 3 회 + exponential backoff (1s, 2s) 이 dataclass 외부 설정 아님 — Azure SDK 의 `max_retries=3` (cfg) 과 일관성 떨어짐 → `chroma_init_max_retries` 필드 추가 검토.

---

### Chroma upsert batch split + init 3 retry (★ NEW a3db32a — atomize 내부 패턴)

- **위치**: `pipeline/agents/atomizer.py:145-167` (23 LOC, 본 cycle 신규)
- **변경 라인**:
  - init 3 retry: `for _attempt in range(3):` + `await asyncio.sleep(2**_attempt)` (atomizer.py:147-155)
  - upsert split: `_CHROMA_UPSERT_BATCH = 100` + `for _j in range(0, len(ids), _CHROMA_UPSERT_BATCH):` (atomizer.py:160-167)
- **이슈**:
  - git log `a3db32a` (2026-05-20) "fix(pipeline): 78사 통합일보 1 cycle — ChromaClient init 3 retry + upsert batch=100 split (HNSW hang 방어)"
  - 인라인 주석 (atomizer.py:142-144): "ChromaClient init 의 user_identity HTTP 호출 timeout (Errno 60) 방어. mapper 의 동시 init 문제와 다르게 atomizer 는 단일 호출이지만, 첫 init 의 cold start latency + network 변동을 위해 3 retry + exponential backoff."
  - 인라인 주석 (atomizer.py:158-159): "Chroma 0.5.20 batch 권장 100 doc. 1000+ doc 통째 upsert 시 HNSW build hang 위험 (이전 cycle 153bfa17/d38605f9 atomizer 4시간 stuck 사례)."
  - `asyncio.sleep` 사용 위해 `import asyncio` 신설 (atomizer.py:11, `# noqa: F401 — used by ChromaClient init retry wrap (L110)` 주석 — 단 실제 사용처는 L155 로 주석 stale 의심).
- **설계 의도**:
  - **init 3 retry**: ChromaClient 의 `user_identity` HTTP 호출이 cold start 시 timeout (macOS Errno 60) → 1s / 2s exponential backoff 로 3 회 재시도. 3 회 모두 실패 시 `_last_err` 타입 + 메시지 포함하여 RuntimeError raise.
  - **upsert 100 doc split**: Chroma 0.5.20 의 HNSW build 단계가 1000+ doc 통째 upsert 시 hang. 이전 cycle 153bfa17 / d38605f9 에서 atomizer 가 4시간 stuck 한 실제 사례 (commit msg 인용). 100 doc 단위 split 으로 각 batch HNSW build 완료 보장.
  - 인접 fail-fast 와 통일된 raise 정책 — silent retry 가 아닌 명시적 실패.
- **대응 패턴**:
  - 발동: `atomize` 의 Chroma 적재 단계 (Azure embedding 직후)
  - 입력: ids / embeddings / documents / metadatas list
  - 처리: init 3 retry → 100 doc 단위 upsert split → Chroma 컬렉션 적재
  - 출력: 없음 (side effect — Chroma 적재)
- **관련**:
  - `chroma_client.py:ChromaClient.__init__` (user_identity HTTP 호출 위치)
  - `chroma_client.py:get_or_create_daily_activities:30`
  - cycle `888c535d` (1162 mapped → mh=285 → atomized=64) 실 검증
- **Suspected related**:
  - **A-N8 / A-N9**: 두 패턴 모두 config 외부화 안 됨 — `AtomizerConfig` 확장 후보.
  - mapper 의 동시 init 문제와 다른 root cause — atomizer 는 단일 호출 cold start, mapper 는 동시성.

---

### mapped_history 조건부 INSERT (atomize 내부 패턴, ★ 본 cycle 활발히 변경됨)

- **위치**: `pipeline/agents/atomizer.py:169-190` (22 LOC)
- **본 cycle 변경**: trade 컬럼 신설 (`16f1b88`) 약속 미반영 (이슈 A-N3) + Activity 키 mismatch (이슈 A-N4)
- **이슈**:
  - 입력 조건 (atomizer.py:171): `mh_valid = [a for a in mapped if a["l6_main"] is not None and a["wa"] is not None]` — Chroma valid (`l6_main is not None AND work_content truthy`) 와 **다른 필터**. wa 미매핑 row 제외 (Phase 3 결정).
  - mh_rows dict (atomizer.py:179-189) 6 키: `wa / l6_main / company / today_qty / today_assigned_workers / unit` — **trade 키 누락** (A-N3) + **`today_assigned_workers` 키가 Activity TypedDict 정의에 없음** (A-N4, Activity 는 `assigned_workers` 만 정의).
  - site_id / report_date 조달 (atomizer.py:174-178): atomizer 는 state 에서 site_id 미수령 → `get_pipeline_run(run_id)` 으로 PG lookup. asyncpg DATE → datetime.date 매핑이 mapped_history.report_date (PG DATE) 에 그대로 들어감.
  - batch INSERT 로직 (`db.py:458-502`): `con.executemany` 1 회 + `ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE SET today_qty = EXCLUDED.today_qty, today_assigned_workers = EXCLUDED.today_assigned_workers, unit = EXCLUDED.unit` (마지막 등장 값 채택, Phase 0 합의). **trade 컬럼은 UPDATE SET 절에도 없음**.
- **설계 의도**:
  - **2단계 필터 분리**: Chroma 는 unmapped 도 의미 임베딩 가치 있음 → 적재. mapped_history 는 WBS 누적 진행률 source → wa 매핑 완료된 것만 누적.
  - **마지막 등장 값 채택 (합계 아님)**: 같은 (run_id, wa, l6_main, company) 재호출 시 today_qty / today_assigned_workers / unit 을 EXCLUDED 값으로 갱신. Phase 0 합의.
  - **단일 connection**: `pg = PGClient(...); await pg.connect()` 한 번으로 fail-fast / lookup / INSERT / count UPDATE 모두 처리 → asyncpg pool leak 방지.
- **대응 패턴**:
  - 발동: `atomize` 의 mh_valid 가 비지 않을 때
  - 입력: mh_valid Activity list + run_id
  - 처리: `get_pipeline_run` lookup → mh_rows dict 빌드 → `insert_mapped_history_batch` (executemany + ON CONFLICT)
  - 출력: 없음 (side effect — PG INSERT)
- **관련**:
  - `db.py:get_pipeline_run:504` + `db.py:insert_mapped_history_batch:458`
  - migration `2026-05-18_mapped_history.sql` (9 컬럼 + UNIQUE + 2 index)
  - migration `2026-05-19_mapped_history_trade.sql` (trade TEXT 컬럼 신설, atomizer 미반영)
  - 테스트: `test_atomizer_mapped_history.py` (4 케이스: valid / wa None skip / l6 None skip / grouping)
- **Suspected related** (2026-05-26 NEW):
  - **A-N3 (M)**: trade 컬럼 NULL — mh_rows dict + SQL 모두 trade 추가 필요. `SELECT COUNT(*) FILTER (WHERE trade IS NOT NULL) FROM mapped_history` 로 실 DB 즉시 검증 가능 (검증 미실시).
  - **A-N4 (L)**: `today_assigned_workers` 키 mismatch — Activity TypedDict 에는 `assigned_workers` 만. PG mapped_history.today_assigned_workers 가 항상 NULL 일 가능성 (검증 미실시).
  - **A-N10**: assert_pipeline_run_exists + get_pipeline_run 가 같은 row 를 두 번 SELECT — get_pipeline_run 1 회로 통합 가능.
  - **A-N11**: state.site_id 미보유 라운드트립 — state 스키마 확장 검토.

---

## 관찰

- **LLM 호출 없음**: 임베딩만 (Azure embeddings.create). LLM 비용 0.
- **★ 임베딩 텍스트 = `_format_document` 결과 (2026-05-21 변경)**: 이전 work_content 단독 → 사람이 읽을 수 있는 자연어 multi-line. documents 가 자연어가 되면서 의미 유사도 검색이 단어 수준 → 문장 수준에서 작동.
- **한자 사용 0건** (grep 결과 한글 + 영문 + 숫자만).
- **TODO/FIXME 없음** (grep 결과 0건).
- **테스트 커버리지**: 15 케이스 (`test_atomizer.py` 11 + `test_atomizer_atomized_count.py` 1 + `test_atomizer_mapped_history.py` 4 + `test_atomizer.py` cfg fixture 등 합계 588 LOC) — 단 **★ 본 cycle 신규 (l7_5_activity / perperson / productivity_pct metadata + `_format_document` 2 모드) 케이스 미실시 (검증 pending)**.
- **★ Chroma daily_activities 컬렉션 metadata 15 필드** (`9252ac7` cycle 12 → 15 확장): `date, run_id, company, l5_disc, l6_main, l7_5_activity, wa, unit, today_qty, assigned_workers, perperson, productivity_pct, worker_source, mapping_conf, conditions`.
- **★ Chroma upsert split 100 + init 3 retry** (`a3db32a`): hardcoded, config 외부화 안 됨 (A-N8 / A-N9).
- **★ Azure embedding batch 64** (`b560dd4`): 200 doc 기준 13 → 4 batch (호출 ¼).
- **★ mapped_history.trade 약속 미반영** (`16f1b88` 인접 migration): trade 컬럼은 신설됐으나 atomizer.py 의 mh_rows dict + insert_mapped_history_batch SQL 둘 다 trade 키 누락 → 항상 NULL (A-N3).
- **★ 실 cycle 검증**: `888c535d` (78사 통합 1 cycle, 19분 1초) — pa=ma=1162, mh=285, fc=293, opt=25, dr=1, 9 jsonb 다 채움 (`a3db32a` commit msg 인용).

---

## 누적 이슈 표 (본 cycle 신규 9건 + 기존 2건 유지)

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| A-N1 | atomizer | M | (cf3c143 cycle) work_content 빈 activity skip — `valid = [a for a in mapped if a["l6_main"] is not None and a.get("work_content")]`. Azure embedding API 가 빈 input 에 HTTP 400 차단. **본 cycle 도 유지** | — (유효, 변경 없음) |
| A-N2 | atomizer | L | (cf3c143 cycle) conditions None 안전 처리 — `",".join(a.get("conditions") or [])`. mapper 가 conditions 키 누락 시 KeyError 회피. **본 cycle 도 유지** | — (유효, 변경 없음) |
| **A-N3** | atomizer / mapped_history | **M** | `2026-05-19_mapped_history_trade.sql` (16f1b88) 가 trade 컬럼 신설 + commit msg 가 "atomizer.py:130 mh_rows 생성 시 Activity.trade (state.py:30) 박기" 의도 명시했으나 atomizer.py:179-189 mh_rows dict + `insert_mapped_history_batch` SQL 둘 다 trade 키 누락 → 현재 trade 컬럼 항상 NULL | mh_rows dict 에 `"trade": a["trade"]` 추가 + insert_mapped_history_batch SQL 의 컬럼 / VALUES / ON CONFLICT SET 모두 trade 포함하도록 수정. 실 DB `SELECT COUNT(*) FILTER (WHERE trade IS NOT NULL) FROM mapped_history` 로 사전 검증 |
| **A-N4** | atomizer | **L** | `mh_rows` 가 `a.get("today_assigned_workers")` 키 lookup (atomizer.py:185) — `Activity` TypedDict (state.py:32-94) 에는 `today_assigned_workers` 정의 없음 (`assigned_workers` 만 존재). PG mapped_history.today_assigned_workers 항상 NULL 가능 | mh_rows 빌드 시 `a.get("assigned_workers")` 로 교체 검토. 단 mapper 가 today_assigned_workers 키 별도 set 하는지 실 DB query 로 검증 우선 |
| **A-N5** | atomizer / `_format_document` | **M** | `_format_document` 의 backfill 분기 (atomizer.py:87) 가 `not unit` 도 short form fallback → unit 빈 str 인 Activity 가 있으면 perperson/productivity_pct 값 있어도 풀 form 못 만듦. backfill 효과 일부 손실 | unit None 인 mapped row 비율 측정 + backfill cycle test |
| **A-N6** | atomizer / config | **L** | `AtomizerConfig.embedding_dim=1536` 필드 코드 내 소비처 grep 결과 없음 (이전 design-intent 카드의 stale 의심 그대로 유효) | 다음 cycle 삭제 또는 Chroma init 시 차원 검증에 사용 |
| **A-N7** | atomizer / chroma_client | **L** | `chroma_client.py:31` docstring "doc text = work_content" 가 `9252ac7` 이후 stale (`_format_document` 결과로 변경됨) | docstring 1줄 갱신 |
| **A-N8** | atomizer | **L** | `_CHROMA_UPSERT_BATCH = 100` 이 함수 내부 hardcoded — env / config 외부화 안 됨. HNSW hang 재현 시 즉시 조정 어려움 | AtomizerConfig 에 `chroma_upsert_batch: int = 100` 필드 추가 검토 |
| **A-N9** | atomizer | **L** | Chroma init retry 3 회 + exponential backoff (1s, 2s) 이 dataclass 외부 설정 아님 — Azure SDK 의 `max_retries=3` (cfg) 과 일관성 떨어짐 | AtomizerConfig 에 `chroma_init_max_retries` 필드 추가 검토 |
| **A-N10** | atomizer | **L** | `assert_pipeline_run_exists` + `get_pipeline_run` 가 같은 pipeline_runs row 를 두 번 SELECT (한 cycle 안) — fail-fast 와 site_id/report_date lookup 통합 가능 | get_pipeline_run 호출 한 번으로 양쪽 책임 통합, assert 는 None 분기로 대체 |
| **A-N11** | atomizer / state | **L** | atomizer 가 `state["site_id"]` 미신뢰 (PG lookup) — state.py 의 CPIAState 가 site_id 를 가지면 PG 라운드트립 1 회 절감 가능 | state 스키마 확장 검토 (graph orchestration 결정 필요) |

**Pending 검증** (다음 cycle 즉시 확인 가능):
- A-N3: `SELECT COUNT(*) FILTER (WHERE trade IS NOT NULL) FROM mapped_history`
- A-N4: `SELECT COUNT(*) FILTER (WHERE today_assigned_workers IS NOT NULL) FROM mapped_history`

---

## 본 cycle 변경 요약 (2026-05-26)

| Commit | 일자 | 영향 함수 | LOC 변화 | 의도 |
|---|---|---|---|---|
| `a3db32a` | 2026-05-20 | `atomize` (Chroma init + upsert) | 141 → 164 | HNSW hang 방어 (3 retry + 100 split). 이전 cycle 4시간 stuck 사례 |
| `9252ac7` | 2026-05-21 | `_format_document` (NEW) + `_build_metadata` (+3 필드) | 164 → 195 | 임베딩 텍스트 자연어화 + l7.5/perperson/productivity_pct metadata 노출 |
| `b560dd4` | 2026-05-22 | `AtomizerConfig.batch_size` | 195 → 196 | Azure embedding 호출 13 → 4 batch (¼) |
| `16f1b88` (인접) | — | (migration only) | — | mapped_history.trade 컬럼 신설 — **atomizer.py 미반영 (A-N3)** |

**이전 design-intent 라벨 "코드 변경 없음" 은 본 cycle 활발한 변경으로 무효화됨.**

---

*최종 수정: 2026-05-26 (HEAD `1ba783f`). 이전 design-intent 카드 (2026-05-17 generated / 2026-05-20 last-checked `ef7c6cd`) 의 "코드 변경 없음, last_checked 만 stamp" 라벨은 본 cycle 무효화. atomizer 직접 commit 3건 (`a3db32a` Chroma retry+batch, `9252ac7` documents format + metadata 풍부화, `b560dd4` batch_size 64) + 인접 migration 1건 (`16f1b88` mapped_history.trade, atomizer 코드 미반영) 누적. T1 1→5 (1 신규), T2 4→7 (3 신규), 이슈 표 2→11 (9 신규).*
