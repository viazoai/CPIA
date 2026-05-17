# Design Intent — persistence (PostgreSQL + ChromaDB)

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/db.py` (309) + `pipeline/chroma_client.py` (40) — 합계 349 LOC

PostgreSQL asyncpg pool 래퍼 + ChromaDB HTTP 클라이언트. 7 테이블 중 `mapping_corrections` 는 schema 만 존재 (HIL 1 미구현 dead schema). Chroma 2 컬렉션 (`wbs_master` Mapper RAG + `daily_activities` Forecaster/Optimizer 유사 이력).

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `PGClient` | db.py:18 | `class PGClient` | asyncpg 풀 래퍼 | — |
| `PGClient.connect` | db.py:24 | `async () -> None` | pool 생성 | — |
| `PGClient.close` | db.py:32 | `async () -> None` | pool 정리 | — |
| `PGClient.fetch_bp_candidates` | db.py:38 | `async (company) -> list[dict]` | BP사 → (wa, l6) 후보 풀 | ✅ |
| `PGClient.fetch_activity` | db.py:56 | `async (wbs_activity_id) -> dict\|None` | ActivityID 단건 조회 | — (미사용 의심) |
| `PGClient.fetch_l6_plan_mh_map` | db.py:72 | `async (company, l6_list) -> dict[str,int]` | N+1 회피: 여러 l6 plan_mh 합 한 번에 | ✅ |
| `PGClient.insert_pipeline_run` | db.py:98 | `async (run_id, site_id, date, status='running') -> None` | pipeline_runs 1 row | — |
| `PGClient.delete_pipeline_run` | db.py:121 | `async (run_id) -> None` | test cleanup | — |
| `PGClient.assert_pipeline_run_exists` | db.py:127 | `async (run_id) -> None` | Atomizer fail-fast | ✅ |
| `PGClient.fetch_plan_for_group` | db.py:145 | `async (company, l6_main) -> dict\|None` | (company, l6_main) 그룹 Plan Σ | ✅ |
| `PGClient.update_run_atomized_count` | db.py:183 | `async (run_id, count) -> None` | Atomizer 종료 UPDATE | ✅ |
| `PGClient.insert_forecast` | db.py:205 | `async (row: dict) -> None` | forecasts INSERT (27 컬럼) | ✅ |
| `PGClient.insert_optimizer_advice` | db.py:273 | `async (row: dict) -> None` | optimizer_advice INSERT (9 컬럼) | ✅ |
| `ChromaClient` | chroma_client.py:14 | `class ChromaClient` | HTTP server wrapper | — |
| `ChromaClient.get_or_create_wbs_master` | chroma_client.py:23 | `() -> Collection` | wbs_master 컬렉션 (1 doc = 1 (WA, L6) 그룹) | ✅ |
| `ChromaClient.get_or_create_daily_activities` | chroma_client.py:30 | `() -> Collection` | daily_activities 컬렉션 (1 doc = 1 Activity) | ✅ |

---

## T2 — Issue Cards

### `insert_forecast` — forecasts 27 컬럼 INSERT

- **위치**: `pipeline/db.py:205-271` (67 LOC, 분기 3)
- **시그니처**: `async def insert_forecast(self, row: dict) -> None`
- **이슈**:
  - git log `d920c85` (optimizer/Task 1: state.py 3 필드 + Forecaster row 2 필드 (main_unit + today_conditions) + Forecaster spec §3/§10 drift 동기화 (v3.1))
  - git log `07a63a6` (optimizer/Task 0 fix: postgres.md 인덱스 이름 통일 + migration forward-only 주석)
  - docstring (db.py:205): "forecasts 테이블 INSERT 1 row. Spec §5.6 + optimizer cycle Task 1 (v3.1) — 27 컬럼 (id/created_at auto, main_unit + today_conditions Task 1 추가). row dict 키 = 컬럼명."
  - 메타: `docs/schema/postgres.md:175~227` (forecasts 테이블 정의), `docs/superpowers/plans/2026-05-16-cpia-optimizer-hil2-plan.md:62` "insert_forecast 25→27 컬럼 (v3.1)".
- **설계 의도**:
  - v3.1 진화 흔적 보존: 25 컬럼 → 27 컬럼 (`main_unit` + `today_conditions` 추가). Forecaster row 가 Optimizer 입력 schema 와 정합되도록 (HIL 2 payload `today_conditions` 박힘).
  - JSON 인코딩 컬럼 5종 (`today_qty_by_unit`, `plan_total_qty_by_unit`, `similar_cases` 등) — `::jsonb` 캐스트.
  - 한글 보존: `ensure_ascii=False` (similar_cases 등 한국어 도메인 데이터).
- **대응 패턴**:
  - 발동: Forecaster `_forecast_one_group` 그룹별 진단 완료 후
  - 입력: 27 필드 dict (run_id, company, l6_main, today_*, plan_*, schedule_state, rag_*, assessment, reasoning, recovery_likelihood, expected_completion, risk_level, main_unit, today_conditions)
  - 처리: 27 컬럼 INSERT, JSON 컬럼은 `json.dumps(..., ensure_ascii=False)`
  - 출력: 없음 (raise on error)
- **관련**:
  - `agents/forecaster/agent.py:_forecast_one_group:190-226` (row 생성)
  - 페어 schema: `docs/schema/postgres.md:175-227`
  - 테스트: `pipeline/tests/forecaster/test_forecaster_integration.py` (implicit), `pipeline/tests/optimizer/test_integration.py:259` (byte-level JSONB)
- **Suspected related** (2026-05-17 stale):
  - `insert_optimizer_advice` (db.py:273) — 같은 JSON 인코딩 패턴.
  - audit drift #2 (assessment bias) — 본 INSERT 결과를 Optimizer 가 소비.

---

### `insert_optimizer_advice` — optimizer_advice 9 컬럼 INSERT + JSONB falsy 보호

- **위치**: `pipeline/db.py:273-309` (37 LOC, 분기 4)
- **시그니처**: `async def insert_optimizer_advice(self, row: dict) -> None`
- **이슈**:
  - git log `36e24e9` (optimizer/Task 6: agent.py optimize + cold_start + _compute_recovery_distribution + PG insert_optimizer_advice (TDD 4 신규))
  - docstring (db.py:273): "optimizer_advice 테이블 INSERT 1 row — 9 컬럼 (id/created_at auto). Spec §9 + §3.1.1 — JSONB falsy 회피 (is not None) — cold_start 의 빈 dict/list 도 INSERT."
  - 인라인 패턴 (db.py:299-307): `_json.dumps(row["degradation_cases"], ensure_ascii=False) if row.get("degradation_cases") is not None else None`
- **설계 의도**:
  - cold_start 의 의도된 빈 dict/list 도 영속 (signal 보존). Python falsy (`{}`, `[]`) 가 NULL 로 떨어지는 것을 막기 위해 `is not None` 명시 체크.
  - 9 컬럼 = (run_id, company, l6_main, forecast_assessment, diagnosis, degradation_cases JSONB, recovery_pattern JSONB, recovery_distribution JSONB, recommendations JSONB) — JSON 4종.
- **대응 패턴**:
  - 발동: Optimizer `optimize()` 선택된 그룹별 advice 1건 생성 후
  - 입력: 9 필드 dict (cold_start row 포함 — `degradation_cases={}`, `recommendations=[]`)
  - 처리: JSONB 4 컬럼 각각 `is not None` 체크 후 `json.dumps(ensure_ascii=False)` 또는 NULL
  - 출력: 없음
- **관련**:
  - `agents/optimizer/agent.py:_compose_cold_start_row:61` / `_compose_row:75` (row 형성)
  - 페어 schema: `docs/schema/postgres.md:255~274`
  - 테스트: `pipeline/tests/optimizer/test_integration.py:266 test_insert_optimizer_advice_byte_level` (정상 + cold_start row JSONB cast 검증, ensure_ascii=False 한글 보존)
- **Suspected related** (2026-05-17 stale):
  - `insert_forecast` 의 JSON 인코딩 패턴 — 같은 ensure_ascii=False.
  - audit drift D-3 (PM 원안 권고 vs LLM advice 의미 일치) — 본 INSERT 의 recommendations JSON 검증 후보.

---

### `fetch_l6_plan_mh_map` — N+1 회피 GROUP BY

- **위치**: `pipeline/db.py:72-96` (25 LOC, 분기 2)
- **시그니처**: `async def fetch_l6_plan_mh_map(self, company: str, l6_list: list[str]) -> dict[str, int]`
- **이슈**:
  - git log `f524792` (spec: forecaster design.md 신규 commit + chromadb where 정오표 (권고 #4))
  - docstring (db.py:72-78): "단일 GROUP BY 쿼리로 (company) 의 여러 l6 plan_mh 합을 한 번에 조회. Spec 3.2 — `_prorate_mh()` 의 N+1 회피용. 빈 l6_list / 미등록 BP사 -> {} 반환."
  - 메타: `docs/schema/postgres.md:77`, `docs/schema/mapping-layer.md:79`.
- **설계 의도**:
  - N+1 회피: BP사 단일 인원 분배 시 매 l6 마다 SELECT 호출 비용 회피. 한 번에 `WHERE company=$1 AND l6 = ANY($2) GROUP BY l6`.
  - 경계 조건 명시: 빈 리스트 → `{}` 즉시 반환 (SQL 호출 없음).
- **대응 패턴**:
  - 발동: `mapper.py:_prorate_mh` 호출 시
  - 입력: company + l6_main list
  - 처리: 단일 GROUP BY SQL
  - 출력: `dict[l6_main: str, Σplan_mh: int]`
- **관련**:
  - `agents/mapper.py:_prorate_mh:347` (호출자)
  - 테스트: `test_db.py:51-78` (4 케이스: 단일/멀티/빈/미등록)
- **Suspected related** (2026-05-17 stale):
  - `fetch_plan_for_group` (db.py:145) — 비슷한 GROUP BY 의도, 단건용.

---

### `assert_pipeline_run_exists` — Atomizer fail-fast

- **위치**: `pipeline/db.py:127-143` (17 LOC, 분기 1)
- **시그니처**: `async def assert_pipeline_run_exists(self, run_id: UUID) -> None`
- **이슈**:
  - docstring (db.py:127): "Atomizer fail-fast 검증 — pipeline_runs row 미존재 시 즉시 RuntimeError. Spec 4.5 — Azure embedding + Chroma upsert 전에 row 존재 확인하여 cost / orphan 방지. update_run_atomized_count 의 0-row RuntimeError 와 동일 메시지 사용."
- **설계 의도**:
  - 비용 절감: Azure embedding 호출(과금) 전에 pipeline_runs row 가 존재해야 ID 일관성 유지. 미존재 시 즉시 실패하여 orphan Chroma row 방지.
  - 일관된 에러 메시지: `update_run_atomized_count` 의 0-row RuntimeError 와 동일.
- **대응 패턴**:
  - 발동: Atomizer 진입 직후
  - 입력: run_id
  - 처리: SELECT 1 FROM pipeline_runs WHERE run_id=$1, 없으면 raise
  - 출력: 없음 (성공) / RuntimeError (실패)
- **관련**:
  - `agents/atomizer.py:atomize:62` 의 fail-fast (atomizer.py:77)
  - 테스트: `test_db.py:137-152` (happy + missing 케이스), `test_atomizer.py:test_atomize_missing_run_raises:258`
- **Suspected related** (2026-05-17 stale):
  - `update_run_atomized_count` — 같은 fail-fast 패턴.

---

### `update_run_atomized_count` — 0-row RuntimeError 검증

- **위치**: `pipeline/db.py:183-203` (21 LOC, 분기 1)
- **시그니처**: `async def update_run_atomized_count(self, run_id: UUID, count: int) -> None`
- **이슈**:
  - docstring (db.py:183): "Atomizer 종료 시 호출. pipeline_runs row 가 사전 INSERT 되어 있어야 함. Spec 4.4 — silent no-op 방지를 위해 affected row 검증. 0 row 면 RuntimeError -> integration test fixture 의 INSERT 빠짐 신호."
- **설계 의도**:
  - silent no-op 방지: PG UPDATE 가 0 row 영향 시 조용히 통과하지 않고 raise (fixture 누락 신호).
  - 동시에 `current_node='atomizer'` 도 UPDATE.
- **대응 패턴**:
  - 발동: Atomizer Chroma upsert 완료 후
  - 입력: run_id + atomized_ids 개수
  - 처리: UPDATE pipeline_runs SET atomized_count=$1, current_node='atomizer' WHERE run_id=$2 → affected row check
  - 출력: 없음 / RuntimeError
- **관련**:
  - `agents/atomizer.py:atomize` (end)
  - 테스트: `test_db.py:107-130` (happy + missing 케이스)
- **Suspected related** (2026-05-17 stale): `assert_pipeline_run_exists` — 한 쌍.

---

### `fetch_plan_for_group` — (company, l6_main) 단건 Plan Σ

- **위치**: `pipeline/db.py:145-181` (37 LOC, 분기 2)
- **시그니처**: `async def fetch_plan_for_group(self, company: str, l6_main: str) -> dict | None`
- **이슈**:
  - docstring (db.py:145): "activity_master 의 (company, l6_main) candidate Σ. 미등록 시 None. Spec §5.2 — 2 SQL 분리로 jsonb_object_agg duplicate key 회피."
  - 메타: `docs/schema/postgres.md:145~182`.
- **설계 의도**:
  - 2 SQL 분리: jsonb_object_agg duplicate key 회피 위해 plan_total_qty (unit 별) 와 plan_mh_sum (전체) 별도 쿼리.
  - 미등록 시 None — 호출자 (Forecaster) 가 cold_start 분기 진입.
- **대응 패턴**:
  - 발동: Forecaster `_forecast_one_group` ② Plan fetch 단계
  - 입력: company + l6_main
  - 처리: 2 SQL (plan_total_qty + plan_mh_sum) merge
  - 출력: `{plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish, ...} | None`
- **관련**:
  - `agents/forecaster/agent.py:_forecast_one_group:95`
  - 테스트: `test_db.py:156-170` (real + unknown)
- **Suspected related** (2026-05-17 stale): `fetch_l6_plan_mh_map` (GROUP BY 묶음 버전).

---

### `fetch_bp_candidates` — Mapper BP filter

- **위치**: `pipeline/db.py:38-54` (17 LOC, 분기 1)
- **시그니처**: `async def fetch_bp_candidates(self, company: str) -> list[dict]`
- **이슈**:
  - docstring (db.py:38): "BP filter — 그 BP사의 (WA, L6) 후보 풀. 활동 마스터에서 company 가 일치하는 row 의 DISTINCT (wa, l6_main) 반환."
  - 메타: `docs/schema/mapping-layer.md:129` "① BP filter — cand_pool = pg.query(...)".
- **설계 의도**:
  - Mapper 6단계 ① BP scope 좁히기: Chroma 전체 검색이 아닌 회사 단위 후보 풀에서 시작 (정확도/속도).
  - WA 결정 4단계 1·2 단계 (`auto_bp_single`, `auto_l6_single`) 입력.
- **대응 패턴**:
  - 발동: `mapper.py:map_activity` 진입
  - 입력: company
  - 처리: `SELECT DISTINCT wa, l6_main FROM activity_master WHERE company=$1`
  - 출력: `list[{wa, l6_main}]`
- **관련**:
  - `agents/mapper.py:map_activity:208`
  - 테스트: `test_db.py:27-35` (남웅건설)
- **Suspected related** (2026-05-17 stale): `mapper.py:resolve_wa:166`.

---

### `get_or_create_wbs_master` — Chroma WBS RAG 컬렉션

- **위치**: `pipeline/chroma_client.py:23-28` (6 LOC)
- **시그니처**: `def get_or_create_wbs_master(self) -> Collection`
- **이슈**:
  - docstring: "1 doc = 1 (WA, L6) 그룹. doc text = mapping-layer.md §5.2 형식."
  - 메타: `docs/schema/mapping-layer.md:284-308` (컬렉션 구조), 라인 310 ("text-embedding-3-small-ai-board-test 1536d").
- **설계 의도**:
  - 컬렉션 분리: Mapper 의 후보 좁히기는 `wbs_master` (189 doc), Forecaster/Optimizer 의 유사 이력 검색은 `daily_activities`. 검색 의도가 달라 컬렉션 분리.
  - cosine 거리 명시 (`metadata={"hnsw:space": "cosine"}`).
- **대응 패턴**:
  - 발동: Mapper `map_activity` ③ Chroma Top-K 단계
  - 입력: 없음
  - 처리: `client.get_or_create_collection("wbs_master", metadata=...)`
  - 출력: Collection
- **관련**:
  - `agents/mapper.py:map_activity:251`
  - 페어 schema: `docs/schema/mapping-layer.md:284-308`
- **Suspected related** (2026-05-17 stale): `get_or_create_daily_activities`.

---

### `get_or_create_daily_activities` — Chroma 유사 이력 컬렉션

- **위치**: `pipeline/chroma_client.py:30-35` (6 LOC)
- **시그니처**: `def get_or_create_daily_activities(self) -> Collection`
- **이슈**:
  - docstring: "1 doc = 1 Activity (시트4 line). doc text = work_content."
  - 메타: `docs/schema/mapping-layer.md:319-336` (적재 구조), `:346-355` (Forecaster RAG 검색 where 필터).
- **설계 의도**:
  - 임베딩 대상은 `work_content` 단독 (숫자/BP 컨텍스트 제외). 도메인 유사도가 작업 내용 중심.
  - 메타데이터로 `date / run_id / company / l6_main / unit / today_qty / assigned_workers / worker_source / mapping_conf / conditions` 박힘 — retrieval 이후 필터링/분석용.
- **대응 패턴**:
  - 발동: Atomizer 적재 시 + Forecaster/Optimizer 검색 시
  - 입력: 없음
  - 처리: `client.get_or_create_collection("daily_activities", metadata=...)`
  - 출력: Collection
- **관련**:
  - `agents/atomizer.py:atomize:111` (upsert)
  - `agents/forecaster/agent.py:_forecast_one_group:100-119` (query)
  - `agents/optimizer/retrieve.py:fetch_degradation_cases` (in-memory filter on metadatas)
- **Suspected related** (2026-05-17 stale):
  - audit drift D-6 (recovery_distribution conditions 필터 검증) — 본 컬렉션의 conditions metadata 사용 path.

---

## 미해결 / 관찰

- **`mapping_corrections` dead schema**: `infra/postgres/init.sql` 에 테이블 정의는 있으나 `pipeline/db.py` 에 INSERT/SELECT 함수 없음. HIL 1 미구현 (drift backlog #4) 와 연결.
- **`PGClient.fetch_activity` 미사용 의심**: `grep -rn "fetch_activity" pipeline/` 결과 `test_db.py` 만 호출, agent 코드 미호출. Mapper 가 Chroma + activity_master 직접 JOIN 으로 통합한 흔적. 삭제 후보.
- **연결 설정 default**: `PGClient.__init__` 은 DSN 외부 주입 강제 (default 없음), `ChromaClient` 는 port=8000 default. homelab (5532/5533) vs A 로컬 Docker (5532/5533) 동시 운용 흔적 — `.env.example` 참조.

---

## 2026-05-17 hil1-forecaster-reporter cycle 변경 (Git SHA d57b0c5)

### T1 신규 함수 2

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `PGClient.insert_mapping_correction` | db.py:315 | `async (run_id, report_date, original, corrected) -> None` | HIL 1 사용자 정정 영속 — `mapping_corrections` 1 row INSERT | ✅ |
| `PGClient.insert_daily_report` | db.py:347 | `async (run_id, report_date, report_md, history_csv_row, bp_name=None) -> None` | Reporter 종합 MD 영속 — `daily_reports` 1 row INSERT | ✅ |

### O-2 해소

- `mapping_corrections` dead schema (이전 cycle 미해결) → 본 cycle `insert_mapping_correction` 으로 활성화. drift #4 흡수.

### 신규 drift (본 cycle 발견)

- **#N2 mapping_corrections schema mismatch**: `postgres.md §8` 명시 (id + run_id + date + work_content + company + trade + original + corrected + correction_type + created_at — 10 컬럼) vs `infra/postgres/init.sql:127` 실 정의 (id + run_id + report_date + original + corrected + created_at — 6 컬럼만). 본 cycle 의 `insert_mapping_correction` 은 실 schema 정합 = 4 인자 (run_id + report_date + original + corrected). work_content/company/trade/correction_type 은 `original` / `corrected` JSONB 안에 합쳐 박음 (work_content GIN index 의도 충족 X — 별 cycle schema migration).
- **#N3 daily_reports schema mismatch**: `postgres.md §5` 명시 (date / summary) vs `init.sql:33` 실 정의 (report_date / history_csv_row + bp_name nullable 추가). 본 cycle 의 `insert_daily_report` 는 실 schema 정합 = 5 인자. summary dict → history_csv_row 컬럼.

---

### T2 신규 카드

#### `PGClient.insert_mapping_correction` — HIL 1 사용자 정정 영속

- **위치**: `pipeline/db.py:315-345` (31 LOC, 분기 0)
- **시그니처**: `async def insert_mapping_correction(self, run_id: uuid.UUID, report_date: _date, original: dict, corrected: dict) -> None`
- **이슈**:
  - git log `1bb78fb` (feat(hil_1): Mapper 결과 사람 검토 + PG mapping_corrections 영속) — 본 cycle 신규.
  - drift backlog #4 (HIL 1 구현) + O-2 (mapping_corrections dead schema) 동시 해소.
  - schema drift `#N2` (postgres.md §8 10 컬럼 vs init.sql 6 컬럼) — 실 schema 정합 signature 채택.
  - docstring (db.py:315-326): "mapping_corrections 테이블 INSERT 1 row. 실 schema (infra/postgres/init.sql:127) = id, run_id, report_date, original JSONB, corrected JSONB, created_at — 6 컬럼. postgres.md §8 의 work_content/company/trade/correction_type top-level 컬럼은 실 PG 미반영 (drift backlog 별 cycle). 본 cycle 은 code-only scope → original/corrected JSONB 안에 합쳐서 박음."
- **설계 의도**:
  - 실 schema 정합 + JSONB 합쳐 박음 (work_content/company/trade/correction_type 등) — 의미 보존, schema migration 별 cycle.
  - Mapper 자가 학습 기반: 다음 run 진입 시 `mapping_corrections` 검색 가능 (postgres.md:311 의도, 단 work_content GIN index 부재 — 별 cycle).
  - 단순 patten = forecaster.insert_forecast / optimizer.insert_optimizer_advice 와 동일 (pool acquire + execute + json.dumps).
- **대응 패턴**:
  - 발동: `graph.hil_1_node` 가 corrections idx 마다 호출
  - 입력: run_id + report_date + original dict (work_content/company/trade 합쳐) + corrected dict (correction_type 합쳐)
  - 처리: pool.acquire → conn.execute (INSERT 4 컬럼, JSONB cast) → release
  - 출력: None
- **관련**:
  - 호출자: `graph.hil_1_node:160`
  - 테스트: `tests/test_db_mapping_corrections.py::test_insert_mapping_correction_roundtrip` (PG INSERT + SELECT 검증)
  - schema: `infra/postgres/init.sql:127` (실) vs `docs/schema/postgres.md §8` (spec drift)
- **Suspected related** (2026-05-17 stale):
  - `insert_forecast` + `insert_optimizer_advice` 동일 패턴 — 향후 공통 helper 추출 후보 (low).
  - schema migration 별 cycle 진입 시 work_content/company/trade/correction_type 컬럼 추가 + 본 함수 signature 확장 → JSONB 안 합치기 제거.

#### `PGClient.insert_daily_report` — Reporter 종합 MD 영속

- **위치**: `pipeline/db.py:347-385` (39 LOC, 분기 1 — None 처리)
- **시그니처**: `async def insert_daily_report(self, run_id: uuid.UUID, report_date: _date, report_md: str, history_csv_row: dict | None, bp_name: str | None = None) -> None`
- **이슈**:
  - git log `22d44c2` (feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports) — 본 cycle 신규.
  - drift backlog #1 (Reporter 미구현) 흡수.
  - schema drift `#N3` (postgres.md §5 date/summary vs init.sql report_date/history_csv_row/bp_name) — 실 schema 정합 signature.
  - docstring (db.py:347-358): "daily_reports 테이블 INSERT 1 row. 실 schema (infra/postgres/init.sql:33) = id, run_id, report_date, bp_name (nullable), report_md, history_csv_row (jsonb, nullable), created_at. postgres.md §5 의 'date' / 'summary' 필드명 mismatch (drift backlog 별 cycle). 종합 보고서 (Reporter 위치 = Optimizer 다음 drift) → bp_name=None. Reporter 의 summary dict (total_workers / risk_counts / advice_count) 는 history_csv_row 컬럼에 박음."
- **설계 의도**:
  - 실 schema 정합 5 인자 — date→report_date / summary→history_csv_row 명시 mapping (postgres.md spec 의 의미 동일).
  - `bp_name=None` default — 종합 보고서 (Reporter 위치 = Optimizer 다음 drift, 1 종) 가정. 향후 BP사별 보고서 구현 시 인자 채움.
  - `history_csv_row` 가 None 가능 (mapped empty fallback path) — JSON dumps 시 None 처리.
- **대응 패턴**:
  - 발동: `reporter.report` 가 LLM 호출 + summary 산출 후 1회 호출
  - 입력: run_id + report_date + report_md (LLM 산출) + history_csv_row (summary dict 또는 None) + bp_name=None
  - 처리: pool.acquire → conn.execute (INSERT 5 컬럼, JSONB cast None 처리) → release
  - 출력: None
- **관련**:
  - 호출자: `reporter.report:154` (agents/reporter.py)
  - 테스트: `tests/test_db_daily_reports.py::test_insert_daily_report_roundtrip` (PG INSERT + SELECT 검증)
  - schema: `infra/postgres/init.sql:33` (실) vs `docs/schema/postgres.md §5` (spec drift)
  - 실 검증: `docs/audit/raw/v2-scenario-1-156657ed.md` (시뮬 1 의 PG SELECT — report_md 1481 chars + history_csv_row 4 키)
- **Suspected related** (2026-05-17 stale):
  - reporter 카드 `_build_summary` — history_csv_row 의 4 키 (total_workers / total_qty_by_trade / risk_counts / advice_count) 생산자.
  - B_Track Dashboard 의 daily_reports SELECT — 향후 history_csv_row 활용 (drift #5 통합 cycle).
