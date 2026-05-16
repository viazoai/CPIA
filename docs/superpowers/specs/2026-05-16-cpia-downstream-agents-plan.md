# CPIA Downstream Agents (Atomizer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **사용자 전역 CLAUDE.md 하드룰 모두 강제** (모든 Task / Step 에 적용):
> - **Real code or no claim** — 추측 보고 금지, 실 명령어 + 실 출력 + 의도 일치 3요소 필수
> - **No fixes without root cause** — 증상만 가리는 패치 금지
> - **No features beyond ask** — speculative abstraction / 미요청 configurability 금지
> - **No fabrication** — 함수/시그니처 모르면 grep, 외부 라이브러리는 context7 MCP
> - **No 한자** — 코드/문서/응답 어디에도 한자 (物, 量, 個 등) 금지
> - **TDD as default** — 실패 테스트 먼저 → 구현 → green 확인 → 그제서야 done
> - **Verification before done** — `$ <명령어>` + `<실 출력 원본>` + `→ <결론>` 3요소 보고 강제
> - **`from __future__ import annotations`** — 모든 .py 첫 줄
> - **`@tool` 함수 시그니처는 `Optional[X]`** — `X | None` 금지 (`typing.get_type_hints()` 제약)
>
> **2026-05-16 plan reviewer 정정**: 1 Blocker (PGClient `_pool` 패턴) + 3 Critical (의존 순서, wbs_master 사전조건, graph.py lambda) + 4 Warning (namwong 48→47, LLM timeout, B 트랙 알림 외) 모두 반영.

**Goal:** Atomizer 에이전트 (LLM 없음, Chroma daily_activities 적재) 와 그 prerequisite `_prorate_mh()` (Mapper sub-step) 를 spec `2026-05-16-cpia-downstream-agents-design.md` 결정 11~13 에 따라 구현하고 graph.py 의 mapper_node + atomizer_node 까지 연결한다.

**Architecture:** mapper.py 의 `map_activity()` 후 batch 함수 `_prorate_mh()` 가 (company, l6_main) 단위 BP사 총 인원 분배 → 결과 mapped 를 atomizer.py 가 Chroma `daily_activities` 컬렉션에 결정성 doc_id 로 upsert. graph.py 가 두 노드를 LangGraph StateGraph 로 연결.

**Tech Stack:** Python 3.11 + uv + asyncpg (pool 패턴) + chromadb 0.5+ + openai (Azure) + pytest + LangGraph 0.2+. 환경: 로컬 Docker (PG :5432 + Chroma :8000), Azure OpenAI text-embedding-3-small (1536d).

---

## File Structure

### 신규 파일 (Create)

| 파일 | 책임 |
|---|---|
| `pipeline/agents/atomizer.py` | Atomizer 구현 (`atomize()`, `_make_doc_id()`, `_build_metadata()`, `AtomizerConfig`) |
| `pipeline/tests/test_prorate_mh.py` | `_prorate_mh()` unit + integration 테스트 |
| `pipeline/tests/test_atomizer.py` | Atomizer unit + integration 테스트 (`@pytest.mark.slow`) |
| `pipeline/tests/test_db.py` | PGClient 신규 4 메서드 테스트 |
| `pipeline/tests/test_graph_e2e.py` | graph.py E2E 회귀 (`@pytest.mark.slow @golden`) |
| `infra/postgres/migrations/2026-05-16_downstream_agents.sql` | DDL 마이그레이션 (3 컬럼 변경) |
| `scripts/verify_bp_summaries.py` | Task 0 — 시트1 today_incr_total 의미 검증 일회성 스크립트 |

### 기존 파일 (Modify)

| 파일 | 변경 |
|---|---|
| `pipeline/state.py:11-44` | Activity TypedDict docstring 정정 (spec §2.2) |
| `pipeline/db.py:13-68` | PGClient 신규 4 메서드 추가 (`_pool` 패턴 그대로 유지) |
| `pipeline/agents/mapper.py` | `_prorate_mh()` batch 함수 추가 (map_activity 와 별개 top-level) |
| `pipeline/graph.py` | 빈 파일 → `mapper_node`, `atomizer_node`, StateGraph 정의 |
| `infra/postgres/init.sql` | pipeline_runs.atomized_count + forecasts 재정의 + optimizer_advice 컬럼 rename (3곳 동기화 중 1) |
| `docs/schema/postgres.md` | §3 / §6 / §7 / §12 변경 (3곳 동기화 중 2) |

### 변경 없음 (Verify only)

- `pipeline/agents/parser.py` — Parser 변경 없음
- `pipeline/agents/mapper.py` 의 `map_activity()` — 1 Activity 당 동작 그대로
- `pipeline/chroma_client.py` — `get_or_create_daily_activities()` 이미 있음

---

## Task 분해 요약 (의존 순서 명시)

```
Task 0       Task 1                                Task 2
(BP 검증)    (state docstring)                     (postgres 3곳)
   │            │                                     │
   ↓            ↓                                     ↓
Task 0.5 (PGClient 4 메서드)
   │ Step 1~4 (fetch_l6_plan_mh_map / insert_pipeline_run / delete_pipeline_run)
   │   ─── 독립 (Task 2 의존 X)
   │ Step 5~9 (update_run_atomized_count)
   │   ─── Task 2 의존 (atomized_count 컬럼 필요)
   ↓
Task 3 (_prorate_mh) ── Task 0.5 Step 1~4 의존
   ↓
Task 4 (atomizer.py) ── Task 0.5 모든 step + Task 2 의존
   ↓
Task 5 (graph.py E2E) ── Task 3 + Task 4 의존
```

총 7 Task. **Task 0/1/2 병렬 가능, Task 0.5 의 update_run_atomized_count 만 Task 2 다음**.

---

### Task 0: bp_summaries.today_incr_total 의미 사전 검증

**Files:**
- Create: `scripts/verify_bp_summaries.py`

**의도:** spec §9.2 Phase 2 의 미해결 사안 "세보 1387명 비정상치 확인". `_prorate_mh()` 의 분모 (BP사 총 인원) 가 진짜 "그 날 신규 투입" 인지 확인. 잘못된 의미라면 분배 결과 전체가 흔들림.

- [ ] **Step 1: 검증 스크립트 작성**

```python
# scripts/verify_bp_summaries.py
"""시트1 today_incr_total 의미 검증 — 세보엠이씨 1387 의 출처.

검증 가설:
  H1 (그 날 신규 투입): 시트1 col28 = 그 날 BP사 신규 인원
  H2 (누계):           시트1 col28 = 9/3~9/25 누계 인원

방법:
  - 9/25 작업일보의 세보엠이씨 시트1 row raw 셀 값 dump
  - col28 (today_incr) 컬럼 헤더 라벨 + 값 + col35 (today_cum) 의 비율 확인
  - 비율이 1/22~1/23 (1일/22일 누계) 정도면 H1, 1.0 이면 H2

Parser 의 cell 인덱스 (col28 / col35) 는 pipeline/agents/parser.py:_parse_sheet1_bp_summaries
의 BP_INCR_COL=28 / BP_CUM_COL=35 와 정합.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
xlsx = ROOT / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"

wb = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)
ws = wb["1.출력인원 현황"]
rows = list(ws.iter_rows(values_only=True))

print("=== 시트1 헤더 (R1~R5) ===")
for i, r in enumerate(rows[:5]):
    non_empty = [(j, c) for j, c in enumerate(r) if c not in (None, "")]
    print(f"R{i+1}: {non_empty[:10]}")

print()
print("=== 세보엠이씨 row 발견 ===")
for i, r in enumerate(rows):
    co = r[3] if len(r) > 3 else None
    if co and isinstance(co, str) and "세보" in co:
        col28 = r[28] if len(r) > 28 else None
        col35 = r[35] if len(r) > 35 else None
        ratio = col28 / col35 if col28 and col35 else None
        print(f"R{i+1}: company={co!r} | col28(today_incr)={col28} | col35(today_cum)={col35} | ratio={ratio}")

wb.close()
```

- [ ] **Step 2: 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_bp_summaries.py
```

Expected: 세보 row 의 ratio 가 H1 (≈0.003~0.05, 22일 누계 분의 1일) 또는 H2 (≈1.0) 둘 중 하나로 판정.

- [ ] **Step 3: 의미 확정 + spec 갱신 (필요 시)**

H1 채택 → spec 그대로. H2 발견 → spec §9.2 Phase 2 사안을 Phase 1 으로 끌어올리고 `_prorate_mh()` 분모 재정의, **Task 3 진입 차단**.

- [ ] **Step 4: 결과 보고 + commit**

```bash
git add scripts/verify_bp_summaries.py
git commit -m "verify: bp_summaries today_incr_total 의미 사전 검증 스크립트

세보 1387 의 의미 (H1 그 날 신규 vs H2 누계) 확정용.
9/25 실 작업일보 raw 셀 값 + col28/col35 ratio dump.
스크립트는 일회성 — 결과는 spec §9.2 갱신 또는 Task 3 차단.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 0.5: PGClient 신규 4 메서드 (`_pool` 패턴 정합)

**Files:**
- Modify: `pipeline/db.py:1-69`
- Create: `pipeline/tests/test_db.py`

**의도:** spec 결정 #12+#13. PGClient 기존 패턴 (`asyncpg.Pool`, `async with self._pool.acquire() as conn:`) 그대로 유지하고 4 메서드 추가. fixture 의 raw SQL 제거.

**메서드 4개:**
1. `fetch_l6_plan_mh_map(company, l6_list)` — Task 3 `_prorate_mh` 용 batch 쿼리
2. `update_run_atomized_count(run_id, count)` — Task 4 `atomize()` 종료 시 호출 (silent no-op 방지)
3. `insert_pipeline_run(run_id, site_id, date, status='running')` — integration test fixture 용
4. `delete_pipeline_run(run_id)` — fixture cleanup 용

#### Step 1~4: `fetch_l6_plan_mh_map` + `insert_pipeline_run` + `delete_pipeline_run` (Task 2 의존 X)

- [ ] **Step 1: 실패 test 3건 작성 (fetch / insert / delete)**

```python
# pipeline/tests/test_db.py
from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from pipeline.db import PGClient


@pytest.fixture
async def pg():
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    yield pg
    await pg.close()


# ── fetch_l6_plan_mh_map ──────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_l6_plan_mh_map_namwong(pg):
    """남웅건설 단일 l6 — spec §3.4 기준값 1,676,807."""
    result = await pg.fetch_l6_plan_mh_map("남웅건설", ["철근콘크리트공사"])
    assert result == {"철근콘크리트공사": 1_676_807}


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_l6_plan_mh_map_sebo_multi(pg):
    """세보엠이씨 멀티 l6 — spec §3.4 top 3 검증."""
    l6_list = ["기계소화설비", "일반공조설비공사", "냉동기설비공사"]
    result = await pg.fetch_l6_plan_mh_map("세보엠이씨", l6_list)
    assert result["기계소화설비"] == 744_043
    assert result["일반공조설비공사"] == 708_154
    assert result["냉동기설비공사"] == 268_341


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_l6_plan_mh_map_empty_list(pg):
    """l6_list = [] → {} 빈 dict."""
    result = await pg.fetch_l6_plan_mh_map("남웅건설", [])
    assert result == {}


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fetch_l6_plan_mh_map_unknown_company(pg):
    """미등록 BP사 → {} 빈 dict."""
    result = await pg.fetch_l6_plan_mh_map("ZZZ_unknown_BP", ["철근콘크리트공사"])
    assert result == {}


# ── insert / delete pipeline_run ──────────────────────────────────


@pytest.mark.slow
@pytest.mark.asyncio
async def test_insert_delete_pipeline_run(pg):
    """insert_pipeline_run + delete_pipeline_run 왕복."""
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    # 검증: row 존재
    async with pg._pool.acquire() as conn:
        row = await conn.fetchrow("SELECT run_id FROM pipeline_runs WHERE run_id=$1", run_id)
    assert row is not None
    # cleanup
    await pg.delete_pipeline_run(run_id)
    async with pg._pool.acquire() as conn:
        row = await conn.fetchrow("SELECT run_id FROM pipeline_runs WHERE run_id=$1", run_id)
    assert row is None
```

- [ ] **Step 2: 실패 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_db.py -v -m slow
```

Expected: 5 FAIL with `AttributeError: 'PGClient' object has no attribute 'fetch_l6_plan_mh_map'` (+ 같은 류).

- [ ] **Step 3: 3 메서드 구현 (`_pool` 패턴 그대로)**

```python
# pipeline/db.py — 기존 PGClient 클래스에 메서드 추가
import uuid


async def fetch_l6_plan_mh_map(
    self, company: str, l6_list: list[str],
) -> dict[str, int]:
    """단일 GROUP BY 쿼리로 (company) 의 여러 l6 plan_mh 합을 한 번에 조회.

    Spec §3.2 — _prorate_mh() 의 N+1 회피용.
    빈 l6_list / 미등록 BP사 → {} 반환.
    """
    if not l6_list:
        return {}
    assert self._pool is not None, "connect() 미호출"
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT l6_main, sum(plan_mh_rev2) AS s
            FROM activity_master
            WHERE company = $1 AND l6_main = ANY($2::text[])
            GROUP BY l6_main
            """,
            company, l6_list,
        )
    return {r["l6_main"]: int(r["s"] or 0) for r in rows}


async def insert_pipeline_run(
    self, run_id: uuid.UUID, site_id: str, date: str,
    status: str = "running",
) -> None:
    """integration test fixture 용 — pipeline_runs row INSERT.
    
    Spec §4.4 — Atomizer 가 INSERT 책임 X (fixture / FastAPI 가 사전 INSERT).
    """
    assert self._pool is not None, "connect() 미호출"
    async with self._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pipeline_runs (run_id, site_id, date, status) "
            "VALUES ($1, $2, $3, $4)",
            run_id, site_id, date, status,
        )


async def delete_pipeline_run(self, run_id: uuid.UUID) -> None:
    """integration test fixture cleanup 용."""
    assert self._pool is not None, "connect() 미호출"
    async with self._pool.acquire() as conn:
        await conn.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)
```

- [ ] **Step 4: 5 test 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_db.py -v -m slow -k "fetch_l6 or insert_delete"
```

Expected: 5 passed.

#### Step 5~9: `update_run_atomized_count` (Task 2 의존 — atomized_count 컬럼 필요)

**⚠️ 의존 차단**: Task 2 가 먼저 commit + DB 마이그레이션 적용 완료 후 진입.

- [ ] **Step 5: 실패 test 2건 작성**

```python
# pipeline/tests/test_db.py — 추가


@pytest.mark.slow
@pytest.mark.asyncio
async def test_update_run_atomized_count_happy(pg):
    """pipeline_runs row 사전 INSERT → atomized_count UPDATE 성공."""
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    try:
        await pg.update_run_atomized_count(run_id, 48)
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT atomized_count, current_node FROM pipeline_runs WHERE run_id=$1",
                run_id,
            )
        assert row["atomized_count"] == 48
        assert row["current_node"] == "atomizer"
    finally:
        await pg.delete_pipeline_run(run_id)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_update_run_atomized_count_missing_row_raises(pg):
    """pipeline_runs row 미존재 → RuntimeError."""
    fake_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="pipeline_runs.*미존재"):
        await pg.update_run_atomized_count(fake_id, 48)
```

- [ ] **Step 6: 실패 확인 (update_run_atomized_count 미존재 OR atomized_count 컬럼 미존재)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_db.py::test_update_run_atomized_count_happy -v -m slow
```

Expected: FAIL with `AttributeError: 'PGClient' object has no attribute 'update_run_atomized_count'`.

- [ ] **Step 7: `update_run_atomized_count` 구현 (`_pool` 패턴)**

```python
async def update_run_atomized_count(self, run_id: uuid.UUID, count: int) -> None:
    """Atomizer 종료 시 호출. pipeline_runs row 가 사전 INSERT 되어 있어야 함.

    Spec §4.4 — silent no-op 방지를 위해 affected row 검증.
    0 row 면 RuntimeError → integration test fixture 의 INSERT 빠짐 신호.
    """
    assert self._pool is not None, "connect() 미호출"
    async with self._pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE pipeline_runs SET atomized_count = $1, current_node = 'atomizer' "
            "WHERE run_id = $2",
            count, run_id,
        )
    # asyncpg result: "UPDATE N" — 0 면 row 미존재
    if result.endswith(" 0"):
        raise RuntimeError(f"pipeline_runs(run_id={run_id}) 미존재 — fixture 설정 확인")
```

- [ ] **Step 8: 2 test 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_db.py -v -m slow -k update_run
```

Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add pipeline/db.py pipeline/tests/test_db.py
git commit -m "db: PGClient 신규 4 메서드 (_pool 패턴 그대로)

Spec §3.2 + §4.4 (결정 #12+#13).

- fetch_l6_plan_mh_map: 단일 GROUP BY batch (N+1 회피)
- insert_pipeline_run / delete_pipeline_run: integration test fixture 용
- update_run_atomized_count: silent no-op 방지 (0 row → RuntimeError)

모두 기존 _pool 패턴 (async with self._pool.acquire() as conn) 그대로.

테스트 7건 (4 fetch + 1 insert/delete + 2 update) — 실 PG @pytest.mark.slow.
세보 mh top 3 (744043/708154/268341) byte-level 검증.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 1: state.py Activity docstring 정정

**Files:**
- Modify: `pipeline/state.py:11-44`

**의도:** spec §2.2 의 docstring 정합. 옵션 X 의 결정 박제. 필드 추가/제거 없음.

- [ ] **Step 1: 현재 state.py 정독**

```bash
cat pipeline/state.py | head -50
```

- [ ] **Step 2: state.py docstring 적용 (Edit)**

```python
# pipeline/state.py:11-44 정정 후
class Activity(TypedDict):
    """작업일보 1행 = 매핑 단위. spec 2026-05-16 §2 참조.

    옵션 X 채택 ((company, l6_main) 단위 분배):
    - 같은 (company, l6_main) Activity 들이 동일 assigned_workers reference
    - PoC 단계: wbs_activity_id / l7_sub / l7_5_activity / sub_work_area /
      plan_total_qty / plan_mh 는 항상 None (Master List 1:N 라 단일값 결정 불가)
      Forecaster / Reporter 는 (company, l6_main) candidate 를 PG 에서 직접 조회.
    """

    # WBS 매핑 (Mapper 이후 채워짐, 그 전엔 None)
    wbs_activity_id: str | None       # PoC: None — 1:N 단일 wbs 결정 불가
    l5_disc: str                      # Parser 가 채움 (한글)
    l6_main: str | None               # Mapper LLM 결정
    l7_sub: str | None                # PoC: None — 1:N
    l7_5_activity: str | None         # PoC: None — 1:N
    sub_work_area: str | None         # PoC: None — 1:N

    # 작업일보 원천 (Parser 가 채움)
    trade: str
    company: str
    unit: str
    today_qty: float                  # 9/25 89.5% None → 0.0 표시
    work_content: str
    conditions: list[str]

    # (company, l6_main) 단위 분배 결과 (_prorate_mh sub-step 이후)
    # 분배 공식: BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)
    assigned_workers: float           # (company, l6_main) 단위 단일값
    worker_source: Literal[
        "parsed",                     #   = 작업일보 명시 그대로 (드문 케이스)
        "mh_prorated",                #   = _prorate_mh() 적용됨 (기본)
        "user_corrected",             #   = H-i-L 1 사용자 보정 (Phase 2)
    ]

    # Master List 조회값 (PoC: None — Forecaster 가 PG 에서 Σ 조회)
    plan_total_qty: float | None
    plan_mh: float | None

    # 매핑 결과 (Mapper 이후) — mapping-layer.md §3 추가 필드
    wa: str | None                    # Mapper WA 결정 4단계
    mapping_conf: float | None        # LLM rerank confidence (0.0~1.0)
    mapping_source: str | None        # 'auto_bp_single'/'auto_l6_single'/...

    # H-i-L 1 플래그
    requires_review: bool             # mapping_conf < 0.7 또는 mapping_source='hil_required'
```

- [ ] **Step 3: 기존 테스트 회귀 (unit only)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v -x -m "not slow" 2>&1 | tail -20
```

Expected: 모든 unit pass (TypedDict 는 런타임 영향 없음, docstring 만).

- [ ] **Step 4: Commit**

```bash
git add pipeline/state.py
git commit -m "state: Activity docstring 정정 — 옵션 X (company, l6_main) grain 박제

Spec §2.2 — 필드 추가/제거 X, docstring 만.

기존 unit test (Parser 22건 + Mapper golden 79건) 회귀 통과.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: postgres 3곳 동기화

**Files:**
- Create: `infra/postgres/migrations/2026-05-16_downstream_agents.sql`
- Modify: `infra/postgres/init.sql`
- Modify: `docs/schema/postgres.md`

**의도:** spec §8.4 결정 #11 — 3곳 동기화 의무.

**⚠️ Task 0.5 Step 5~9 의 prerequisite**: atomized_count 컬럼이 본 Task 의 마이그레이션 적용 후 존재.

- [ ] **Step 1: 마이그레이션 파일 작성**

```sql
-- infra/postgres/migrations/2026-05-16_downstream_agents.sql
-- Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §8

-- §8.1: pipeline_runs.atomized_count
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS atomized_count INTEGER DEFAULT 0;

-- §8.2: forecasts 재정의 (PoC 단계 빈 테이블 — DROP + CREATE)
DROP TABLE IF EXISTS forecasts;

CREATE TABLE forecasts (
    id                       BIGSERIAL PRIMARY KEY,
    run_id                   UUID NOT NULL REFERENCES pipeline_runs(run_id),
    company                  TEXT NOT NULL,
    l6_main                  TEXT NOT NULL,

    today_qty_by_unit        JSONB,
    today_assigned_workers   NUMERIC,

    plan_total_qty_by_unit   JSONB,
    plan_mh_sum              NUMERIC,

    rag_n_similar            INT,
    similar_cases            JSONB,

    assessment               TEXT,
    reasoning                TEXT,
    expected_completion      DATE,
    delay_days               INT,
    risk_level               TEXT,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';

-- §8.3: optimizer_advice 컬럼 rename
ALTER TABLE optimizer_advice RENAME COLUMN trade TO l6_main;
```

- [ ] **Step 2: 로컬 DB 마이그레이션 적용**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
docker exec -i cpia-pg-local psql -U cpia -d cpia < infra/postgres/migrations/2026-05-16_downstream_agents.sql
```

Expected: ALTER + DROP + CREATE + 3 CREATE INDEX + ALTER (총 6 명령).

- [ ] **Step 3: 적용 검증 (3 컬럼 변경)**

```bash
docker exec cpia-pg-local psql -U cpia -d cpia -c "\d pipeline_runs" | grep atomized_count
docker exec cpia-pg-local psql -U cpia -d cpia -c "\d forecasts" | head -20
docker exec cpia-pg-local psql -U cpia -d cpia -c "\d optimizer_advice" | grep l6_main
```

Expected:
- `atomized_count | integer | ... default 0`
- forecasts: `today_qty_by_unit jsonb` / `l6_main text` 등 새 컬럼
- optimizer_advice: `l6_main` (trade 없음)

- [ ] **Step 4: init.sql 동기화**

`infra/postgres/init.sql` 의 pipeline_runs / forecasts / optimizer_advice 정의를 마이그레이션 결과와 동일하게 정정:

- pipeline_runs: `atomized_count INTEGER DEFAULT 0` 추가
- forecasts: 전체 CREATE TABLE 위 §8.2 SQL 과 동일하게 교체
- optimizer_advice: `trade TEXT NOT NULL` → `l6_main TEXT NOT NULL`

- [ ] **Step 5: postgres.md 동기화**

`docs/schema/postgres.md`:
- §3 pipeline_runs 표에 `atomized_count INTEGER DEFAULT 0` 행 추가
- §6 forecasts 표 정정 (trade → l6_main, today_qty / plan_unit_productivity → JSONB by_unit, plan_mh_sum 등)
- §7 optimizer_advice 표 정정 (trade → l6_main)
- §12 변경 이력 한 줄 추가: "2026-05-16 | downstream-agents spec §8 적용 — forecasts (company, l6_main) grain 정정 + pipeline_runs.atomized_count + optimizer_advice rename | A 트랙"

- [ ] **Step 6: init.sql cold-start syntax 검증**

```bash
pipeline/.venv/bin/python3 -c "
sql = open('infra/postgres/init.sql').read()
assert 'atomized_count' in sql, 'init.sql 누락: atomized_count'
assert 'today_qty_by_unit' in sql, 'init.sql 누락: today_qty_by_unit'
assert 'l6_main' in sql.split('CREATE TABLE optimizer_advice')[1].split(';')[0], 'init.sql 누락: l6_main in optimizer_advice'
assert 'trade TEXT NOT NULL' not in sql.split('CREATE TABLE optimizer_advice')[1].split(';')[0], 'init.sql 잔존: optimizer_advice.trade'
print('✓ init.sql 동기화 검증 통과')
"
```

- [ ] **Step 7: Commit**

```bash
git add infra/postgres/migrations/2026-05-16_downstream_agents.sql infra/postgres/init.sql docs/schema/postgres.md
git commit -m "postgres: 3곳 동기화 — pipeline_runs.atomized_count + forecasts grain + optimizer_advice rename

Spec §8.4 (결정 #11). 마이그레이션 + init.sql + postgres.md 3곳.

- pipeline_runs.atomized_count INTEGER DEFAULT 0
- forecasts 재정의: trade → l6_main, today_qty/plan_unit_productivity → JSONB by_unit
- optimizer_advice.trade RENAME TO l6_main
- 로컬 DB 마이그레이션 적용 검증

PoC 단계 빈 테이블 — DROP+CREATE 안전.
B 트랙 알림: 다음 docker-compose down -v && up 시 forecasts schema 갱신됨.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `_prorate_mh()` batch 분배

**Files:**
- Modify: `pipeline/agents/mapper.py` (top-level 함수 추가)
- Create: `pipeline/tests/test_prorate_mh.py`

**의존**: Task 0.5 Step 1~4 (`fetch_l6_plan_mh_map`).

- [ ] **Step 1: 5 unit test 작성 (mock pg)**

```python
# pipeline/tests/test_prorate_mh.py
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pipeline.agents.mapper import _prorate_mh
from pipeline.state import Activity, BPSummary, ParsedDailyReport


def _act(company: str, l6: str | None, **kw) -> Activity:
    return {
        "wbs_activity_id": None, "l5_disc": "건축",
        "l6_main": l6, "l7_sub": None, "l7_5_activity": None,
        "sub_work_area": None, "trade": "건축", "company": company,
        "unit": "m2", "today_qty": 0.0, "work_content": "test",
        "conditions": [], "assigned_workers": 0.0, "worker_source": "parsed",
        "plan_total_qty": None, "plan_mh": None,
        "wa": "CUB", "mapping_conf": 0.9, "mapping_source": "auto_bp_single",
        "requires_review": False, **kw,
    }


def _summ(company: str, today_incr: int) -> BPSummary:
    return {
        "bp_code": None, "company": company, "disc_abbrev": "건축",
        "zone": "CUB", "scope": None,
        "work_text_yesterday": None, "work_text_today": None, "work_text_tomorrow": None,
        "today_incr_total": today_incr, "today_cum_total": 0,
    }


@pytest.mark.asyncio
async def test_prorate_single_l6():
    """남웅 88명, l6=1 → 88.0 그대로."""
    mapped = [_act("남웅건설", "철근콘크리트공사") for _ in range(3)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("남웅건설", 88)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 1_676_807})

    result = await _prorate_mh(mapped, parsed, pg)

    assert all(a["assigned_workers"] == 88.0 for a in result)
    assert all(a["worker_source"] == "mh_prorated" for a in result)


@pytest.mark.asyncio
async def test_prorate_zero_total():
    """bp_total=0 → 0.0."""
    mapped = [_act("XYZ", "철근콘크리트공사")]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("XYZ", 0)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 100})

    result = await _prorate_mh(mapped, parsed, pg)
    assert result[0]["assigned_workers"] == 0.0


@pytest.mark.asyncio
async def test_prorate_zero_plan_mh():
    """Σmh=0 → 균등 분배."""
    mapped = [_act("XYZ", f"l6_{i}") for i in range(4)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("XYZ", 80)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(
        return_value={"l6_0": 0, "l6_1": 0, "l6_2": 0, "l6_3": 0}
    )

    result = await _prorate_mh(mapped, parsed, pg)
    for a in result:
        assert a["assigned_workers"] == 20.0


@pytest.mark.asyncio
async def test_prorate_unmapped_skip():
    """l6_main=None Activity → assigned_workers 미변경."""
    mapped = [
        _act("남웅건설", "철근콘크리트공사"),
        _act("남웅건설", None, requires_review=True),
    ]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("남웅건설", 88)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(return_value={"철근콘크리트공사": 1_676_807})

    result = await _prorate_mh(mapped, parsed, pg)
    assert result[0]["assigned_workers"] == 88.0
    assert result[0]["worker_source"] == "mh_prorated"
    assert result[1]["assigned_workers"] == 0.0
    assert result[1]["worker_source"] == "parsed"


@pytest.mark.asyncio
async def test_prorate_multi_l6_share():
    """3 l6, 인원 100 → plan_mh 비율 (50/30/20%) → 50/30/20명."""
    mapped = [_act("CO", f"l6_{i}") for i in range(3)]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("CO", 100)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }
    pg = AsyncMock()
    pg.fetch_l6_plan_mh_map = AsyncMock(
        return_value={"l6_0": 500, "l6_1": 300, "l6_2": 200}
    )

    result = await _prorate_mh(mapped, parsed, pg)
    lookup = {a["l6_main"]: a["assigned_workers"] for a in result}
    assert lookup["l6_0"] == 50.0
    assert lookup["l6_1"] == 30.0
    assert lookup["l6_2"] == 20.0
```

- [ ] **Step 2: 실패 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_prorate_mh.py -v
```

Expected: 5 FAIL with `ImportError: cannot import name '_prorate_mh'`.

- [ ] **Step 3: `_prorate_mh()` 구현 (mapper.py 에 추가)**

```python
# pipeline/agents/mapper.py — top-level 추가 (map_activity 아래)
from collections import defaultdict


async def _prorate_mh(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    pg: PGClient,
) -> list[Activity]:
    """(company, l6_main) 단위 BP사 총 인원 분배 — 옵션 X 알고리즘.

    Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §3.
    """
    bp_total: dict[str, int] = defaultdict(int)
    for s in parsed_report["bp_summaries"]:
        bp_total[s["company"]] += s["today_incr_total"]

    bp_l6: dict[str, set[str]] = defaultdict(set)
    for a in mapped:
        if a["l6_main"] is not None:
            bp_l6[a["company"]].add(a["l6_main"])

    workers_lookup: dict[tuple[str, str], float] = {}
    for company, l6_set in bp_l6.items():
        total_n = bp_total.get(company, 0)
        if total_n == 0 or not l6_set:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = 0.0
            continue

        l6_mh: dict[str, int] = await pg.fetch_l6_plan_mh_map(company, list(l6_set))

        sum_mh = sum(l6_mh.values())
        if sum_mh == 0:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = total_n / len(l6_set)
        else:
            for l6, mh in l6_mh.items():
                workers_lookup[(company, l6)] = total_n * mh / sum_mh

    out: list[Activity] = []
    for a in mapped:
        if a["l6_main"] is not None:
            key = (a["company"], a["l6_main"])
            a = {
                **a,
                "assigned_workers": workers_lookup.get(key, 0.0),
                "worker_source": "mh_prorated",
            }
        out.append(a)
    return out
```

- [ ] **Step 4: 5 unit test 통과 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_prorate_mh.py -v
```

Expected: 5 passed.

- [ ] **Step 5: integration test 1건 작성 (실 PG)**

```python
# pipeline/tests/test_prorate_mh.py — 추가
import os
from pipeline.db import PGClient


@pytest.fixture
async def real_pg():
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    yield pg
    await pg.close()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_prorate_sebo_real_pg(real_pg):
    """세보엠이씨 1387명, 13 l6 → spec §3.4 byte-level 일치."""
    sebo_l6s = [
        "기계소화설비", "일반공조설비공사", "냉동기설비공사",
        "CABINET배기설비공사", "VOC설비공사", "비상배기덕트설비공사",
        "ACID배기설비공사", "위생배관공사",
        "ALKALI배기설비공사", "H/G배기설비공사", "DCC설비공사",
        "NPW배관공사", "H-VAC설비공사",
    ]
    mapped = [_act("세보엠이씨", l6) for l6 in sebo_l6s]
    parsed: ParsedDailyReport = {
        "report_date": "2025-09-25", "project": "test",
        "bp_summaries": [_summ("세보엠이씨", 1387)],
        "job_allocations": [], "equipment_allocations": [], "activities": [],
    }

    result = await _prorate_mh(mapped, parsed, real_pg)
    lookup = {a["l6_main"]: round(a["assigned_workers"], 1) for a in result}

    assert lookup["기계소화설비"] == 421.7
    assert lookup["일반공조설비공사"] == 401.4
    assert lookup["냉동기설비공사"] == 152.1
    assert round(sum(lookup.values()), 0) == 1387
```

- [ ] **Step 6: integration test 통과**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_prorate_mh.py -v -m slow
```

Expected: 1 passed.

- [ ] **Step 7: 골든 회귀 통과 유지**

`_prorate_mh()` 는 `map_activity()` 와 별개 함수. 회귀 영향 X 확인.

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_mapper_golden.py -v -m slow 2>&1 | tail -10
```

Expected: 79건 golden 회귀 그대로.

- [ ] **Step 8: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/tests/test_prorate_mh.py
git commit -m "mapper: _prorate_mh() batch 분배 (옵션 X (company, l6_main) grain)

Spec §3 (결정 #3+#4).

알고리즘: BP사 총 인원 × candidate Σplan_mh 비율 분배.

엣지: bp_total=0 → 0, Σplan_mh=0 → 균등, l6_main=None → 변경 X.

테스트:
- 5 unit (mock pg) — 분배 알고리즘 정확성
- 1 integration (실 PG) — 세보 1387 / 13 l6 / spec §3.4 byte-level
- golden 79 회귀 통과 유지

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: atomizer.py + 테스트

**Files:**
- Create: `pipeline/agents/atomizer.py`
- Create: `pipeline/tests/test_atomizer.py`

**의존**: Task 0.5 (모든 step) + Task 2.

- [ ] **Step 1: atomizer.py 의 helper + AtomizerConfig (no I/O)**

```python
# pipeline/agents/atomizer.py
"""Atomizer agent — mapped Activity[] → Chroma daily_activities 적재.

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §4.

LLM 없음 (Azure embedding 만). 1 mapped Activity = 1 Chroma doc.
doc_id = sha256(date|company|l6_main|work_content)[:16] (결정성 upsert).
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, ParsedDailyReport


@dataclass
class AtomizerConfig:
    """Atomizer 호출에 필요한 환경."""

    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    batch_size: int = 16
    azure_timeout: float = 30.0
    azure_max_retries: int = 3
    embedding_dim: int = 1536  # Azure text-embedding-3-small 고정


def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str:
    """결정성 doc id — spec §4.2 (✓ Verified `73ff80435e312c41` for sample)."""
    raw = f"{date}|{company}|{l6_main}|{work_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_metadata(a: Activity, date: str, run_id: str) -> dict[str, Any]:
    """Chroma metadata — spec §4.1. scalar only (list → CSV, None → "")."""
    return {
        "date": date, "run_id": run_id,
        "company": a["company"],
        "l5_disc": a["l5_disc"],
        "l6_main": a["l6_main"] or "",
        "wa": a["wa"] or "",
        "unit": a["unit"],
        "today_qty": float(a["today_qty"]),
        "assigned_workers": float(a["assigned_workers"]),
        "worker_source": a["worker_source"],
        "mapping_conf": float(a["mapping_conf"] or 0.0),
        "conditions": ",".join(a["conditions"]),
    }
```

- [ ] **Step 2: 6 unit test 작성 (no I/O)**

```python
# pipeline/tests/test_atomizer.py
from __future__ import annotations

import pytest

from pipeline.agents.atomizer import _build_metadata, _make_doc_id
from pipeline.state import Activity


def _sample_activity() -> Activity:
    return {
        "wbs_activity_id": None, "l5_disc": "건축",
        "l6_main": "철근콘크리트공사", "l7_sub": None,
        "l7_5_activity": None, "sub_work_area": None,
        "trade": "건축", "company": "남웅건설", "unit": "m2",
        "today_qty": 0.0, "work_content": "기초 거푸집 설치",
        "conditions": [], "assigned_workers": 88.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None, "plan_mh": None,
        "wa": "CUB", "mapping_conf": 0.82, "mapping_source": "auto_bp_single",
        "requires_review": False,
    }


def test_make_doc_id_determinism():
    """spec §4.7 ✓ Verified."""
    id1 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    id2 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    assert id1 == id2 == "73ff80435e312c41"


def test_make_doc_id_changes():
    id1 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    id2 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 타설")
    assert id1 != id2


def test_make_doc_id_format():
    id_ = _make_doc_id("2025-09-25", "ZZZ", "L6", "WORK")
    assert len(id_) == 16
    assert all(c in "0123456789abcdef" for c in id_)


def test_build_metadata_scalar_only():
    meta = _build_metadata(_sample_activity(), "2025-09-25", "test-run")
    for k, v in meta.items():
        assert isinstance(v, (str, int, float, bool)), f"{k} = {type(v).__name__}"


def test_build_metadata_conditions_csv():
    a = _sample_activity()
    a["conditions"] = ["우천", "병행작업"]
    meta = _build_metadata(a, "2025-09-25", "test-run")
    assert meta["conditions"] == "우천,병행작업"


def test_build_metadata_none_to_empty_string():
    a = _sample_activity()
    a["wa"] = None
    meta = _build_metadata(a, "2025-09-25", "test-run")
    assert meta["wa"] == ""
```

- [ ] **Step 3: 6 unit pass 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_atomizer.py -v
```

Expected: 6 passed.

- [ ] **Step 4: `atomize()` 함수 구현**

```python
# pipeline/agents/atomizer.py — 추가
async def atomize(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    run_id: uuid.UUID,
    cfg: AtomizerConfig,
) -> list[str]:
    """mapped → Chroma daily_activities 적재. atomized_ids 반환.

    Spec §4.5.
    """
    valid = [a for a in mapped if a["l6_main"] is not None]
    if not valid:
        return []

    date = parsed_report["report_date"]
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    ids = [_make_doc_id(date, a["company"], a["l6_main"], a["work_content"]) for a in valid]
    documents = [a["work_content"] for a in valid]
    metadatas = [_build_metadata(a, date, str(run_id)) for a in valid]

    embeddings: list[list[float]] = []
    for i in range(0, len(documents), cfg.batch_size):
        chunk = documents[i : i + cfg.batch_size]
        resp = azure.embeddings.create(model=cfg.embedding_model, input=chunk)
        embeddings.extend([d.embedding for d in resp.data])

    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    coll.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        await pg.update_run_atomized_count(run_id, len(ids))
    finally:
        await pg.close()

    return ids
```

- [ ] **Step 5: integration test 작성 (Task 0.5 의 PGClient 메서드 사용)**

⚠️ **namwong 48 row 의 정합**: spec golden (`mapping-layer.md §9.1`) 은 남웅 **47 row** (R125 비계 제외) 가 (CUB, 철근콘크리트공사) 매핑. 시트4 의 48 row 중 1 row = "비계 설치" 는 hil_required 가능성. 본 test 는 **47 row 만 매핑 가정** 으로 검증.

```python
# pipeline/tests/test_atomizer.py — 추가
import os
import uuid

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.parser import parse_daily_report
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient


@pytest.fixture
def cfg() -> AtomizerConfig:
    return AtomizerConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


@pytest.fixture
async def run_row(cfg):
    """integration test 용 pipeline_runs row 사전 INSERT — Task 0.5 메서드 사용."""
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        yield run_id
        await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.mark.slow
@pytest.mark.asyncio
async def test_atomize_empty():
    """valid=[] → return []. Azure/Chroma/PG 호출 없음."""
    cfg = AtomizerConfig(
        azure_endpoint="", azure_api_key="", azure_api_version="",
        embedding_model="", postgres_url="", chroma_host="", chroma_port=0,
    )
    parsed = {"report_date": "2025-09-25", "project": "test",
              "bp_summaries": [], "job_allocations": [], "equipment_allocations": [], "activities": []}
    result = await atomize([], parsed, uuid.uuid4(), cfg)
    assert result == []


@pytest.mark.slow
@pytest.mark.asyncio
async def test_atomize_skip_unmapped(cfg):
    """l6_main=None Activity → skip (Chroma 적재 X). 통과 = atomize 가 빈 valid 면 호출 안 함."""
    parsed = {"report_date": "2025-09-25", "project": "test",
              "bp_summaries": [], "job_allocations": [], "equipment_allocations": [], "activities": []}
    mapped = [{**_sample_activity(), "l6_main": None}]
    result = await atomize(mapped, parsed, uuid.uuid4(), cfg)
    assert result == []


@pytest.mark.slow
@pytest.mark.asyncio
async def test_atomize_namwong_47(cfg, run_row):
    """9/25 남웅 47 row (비계 제외) → Chroma 적재. assigned_workers=88 일관.

    실 데이터 reproduce: spec §1.2 시뮬 + golden 79건 mapping-layer §9.1.
    """
    from pipeline.agents.mapper import _prorate_mh

    xlsx_path = "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    parsed = parse_daily_report(xlsx_path)

    # 남웅 48 row 중 비계 제외 = 47 row
    namwong_raw = [a for a in parsed["activities"] if a["company"] == "남웅건설"]
    assert len(namwong_raw) == 48, f"남웅 행 수: {len(namwong_raw)} (예상 48)"
    namwong = [
        {**a, "wa": "CUB", "l6_main": "철근콘크리트공사",
         "mapping_conf": 0.82, "mapping_source": "auto_bp_single",
         "requires_review": False}
        for a in namwong_raw
        if "비계" not in a["work_content"]  # 비계 1 row 제외 (golden)
    ]
    assert len(namwong) == 47, f"비계 제외 후: {len(namwong)} (예상 47)"

    # _prorate_mh 적용
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        namwong = await _prorate_mh(namwong, parsed, pg)
    finally:
        await pg.close()

    assert all(a["assigned_workers"] == 88.0 for a in namwong)

    ids = await atomize(namwong, parsed, run_row, cfg)
    assert len(ids) == 47

    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    rows = coll.get(ids=ids, include=["metadatas"])
    assert len(rows["ids"]) == 47
    assert all(m["assigned_workers"] == 88.0 for m in rows["metadatas"])


@pytest.mark.slow
@pytest.mark.asyncio
async def test_atomize_upsert_idempotent(cfg, run_row):
    """같은 (date, company, l6, work) 2회 호출 → Chroma row 수 같음 (upsert dedup)."""
    parsed = {"report_date": "2025-09-25", "project": "test",
              "bp_summaries": [], "job_allocations": [], "equipment_allocations": [], "activities": []}
    mapped = [_sample_activity()]
    ids1 = await atomize(mapped, parsed, run_row, cfg)
    ids2 = await atomize(mapped, parsed, run_row, cfg)
    assert ids1 == ids2


@pytest.mark.slow
@pytest.mark.asyncio
async def test_atomize_missing_run_raises(cfg):
    """fixture 없이 호출 → RuntimeError."""
    parsed = {"report_date": "2025-09-25", "project": "test",
              "bp_summaries": [], "job_allocations": [], "equipment_allocations": [], "activities": []}
    mapped = [_sample_activity()]
    fake_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="pipeline_runs.*미존재"):
        await atomize(mapped, parsed, fake_id, cfg)
```

- [ ] **Step 6: integration test 통과**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_atomizer.py -v -m slow 2>&1 | tail -30
```

Expected: 5 passed (empty / skip_unmapped / namwong_47 / upsert / missing_run).

- [ ] **Step 7: Commit**

```bash
git add pipeline/agents/atomizer.py pipeline/tests/test_atomizer.py
git commit -m "atomizer: mapped → Chroma daily_activities 적재 (LLM 없음, 임베딩만)

Spec §4 (결정 #7+#8+#9+#13).

테스트:
- 6 unit (helper 만, no I/O)
- 5 integration (실 Chroma + Azure + PG, @pytest.mark.slow)
  - test_atomize_namwong_47: 9/25 실 데이터 47 row (비계 제외, golden 부합) + assigned_workers=88
  - test_atomize_upsert_idempotent: 같은 doc_id 재호출 dedup
  - test_atomize_missing_run_raises: pipeline_runs 미존재 → RuntimeError

fixture 가 PGClient.insert_pipeline_run / delete_pipeline_run 사용 (raw SQL X).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: graph.py mapper_node + atomizer_node + E2E 회귀

**Files:**
- Modify: `pipeline/graph.py` (빈 파일 → 두 노드 + StateGraph)
- Create: `pipeline/tests/test_graph_e2e.py`

**의존**: Task 3 + Task 4.

- [ ] **Step 1: graph.py 작성 (inner async def — closure 패턴)**

```python
# pipeline/graph.py
"""LangGraph StateGraph — Phase 1 mapper_node + atomizer_node 만.

Spec: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §1.

interrupt 2개 + Reporter/Forecaster/Optimizer 통합은 차후 graph.py spec 에서.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState, ParsedDailyReport


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig


async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """mapper_node — map_activity (각 Activity) + _prorate_mh (batch 분배)."""
    parsed: ParsedDailyReport = state["parsed"]

    mapped: list[Activity] = []
    for activity in parsed["activities"]:
        result = await map_activity(activity, parsed_report=parsed, cfg=cfg.mapper)
        mapped.append(result)

    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    try:
        mapped = await _prorate_mh(mapped, parsed, pg)
    finally:
        await pg.close()

    return {"mapped": mapped, "current_node": "mapper"}


async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """atomizer_node — atomize (Chroma daily_activities 적재)."""
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]

    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)

    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


def build_graph(cfg: GraphConfig):
    """LangGraph StateGraph — Phase 1 (mapper + atomizer 만).
    
    inner async def 로 cfg 캡처 — lambda 회피 (reviewer C3 권고).
    """
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    graph.add_node("mapper", _mapper)
    graph.add_node("atomizer", _atomizer)
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "atomizer")
    graph.add_edge("atomizer", END)
    return graph.compile()
```

- [ ] **Step 2: E2E test 작성 (wbs_master 사전조건 fixture + LLM timeout)**

```python
# pipeline/tests/test_graph_e2e.py
from __future__ import annotations

import os
import uuid

import pytest

from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.parser import parse_daily_report
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.graph import GraphConfig, build_graph


@pytest.fixture
def cfg() -> GraphConfig:
    common_pg = os.environ["POSTGRES_URL"]
    common_chroma_host = os.environ["CHROMA_HOST"]
    common_chroma_port = int(os.environ.get("CHROMA_PORT", "8000"))
    common_chroma_ssl = os.environ.get("CHROMA_SSL", "false").lower() == "true"
    return GraphConfig(
        mapper=MapperConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            llm_model=os.environ["LLM_MODEL"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host, chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
        atomizer=AtomizerConfig(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            embedding_model=os.environ["EMBEDDING_MODEL"],
            postgres_url=common_pg,
            chroma_host=common_chroma_host, chroma_port=common_chroma_port,
            chroma_ssl=common_chroma_ssl,
        ),
    )


@pytest.fixture
def wbs_master_ready(cfg):
    """사전조건: wbs_master 컬렉션에 충분한 row 적재되어 있는지 검증.
    
    Reviewer C2 — mapper_node 의 LLM 호출이 wbs_master query 결과 의존.
    누락 시 BP filter fallback → 정확도 폭락. PoC 단계 ~100 row 적재 가정.
    """
    chroma = ChromaClient(
        host=cfg.atomizer.chroma_host,
        port=cfg.atomizer.chroma_port,
        ssl=cfg.atomizer.chroma_ssl,
    )
    coll = chroma.get_or_create_wbs_master()
    count = coll.count()
    assert count >= 100, (
        f"wbs_master Chroma 컬렉션 row 수: {count} < 100. "
        f"`scripts/load_master_list.py` 실행 필요."
    )


@pytest.fixture
async def run_row(cfg):
    pg = PGClient(cfg.atomizer.postgres_url)
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        yield run_id
        await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.mark.slow
@pytest.mark.golden
@pytest.mark.timeout(600)  # 10분 — 실 mapper LLM 호출 47회 × ~5초 = 240초 안전 마진
@pytest.mark.asyncio
async def test_graph_e2e_namwong_47(cfg, wbs_master_ready, run_row):
    """E2E: 9/25 작업일보 (남웅 47 row 만, 비계 제외) → mapper → atomizer → Chroma 적재.

    실 mapper LLM 호출 (Azure gpt-5.1) 47회 + Chroma 임베딩.
    비용 ~$0.02, 시간 ~4~8분.
    """
    xlsx_path = "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    parsed = parse_daily_report(xlsx_path)

    # 남웅 48 row 중 비계 제외 → 47 row (golden mapping-layer §9.1)
    namwong_acts = [
        a for a in parsed["activities"]
        if a["company"] == "남웅건설" and "비계" not in a["work_content"]
    ]
    assert len(namwong_acts) == 47

    parsed_filtered = {**parsed, "activities": namwong_acts}

    state = {
        "run_id": str(run_row), "date": "2025-09-25",
        "input_files": [xlsx_path],
        "raw_texts": {}, "parsed": parsed_filtered,
        "mapped": [], "hil_1_corrections": {}, "atomized_ids": [],
        "report_md": "", "forecast": [], "hil_2_selection": [], "optimizer_advice": [],
        "current_node": "", "status": "running",
    }

    graph = build_graph(cfg)
    final = await graph.ainvoke(state)

    # mapper 통과 — 모든 Activity l6_main 채워짐
    assert len(final["mapped"]) == 47
    assert all(a["l6_main"] == "철근콘크리트공사" for a in final["mapped"])
    # _prorate_mh — assigned_workers 88
    assert all(a["assigned_workers"] == 88.0 for a in final["mapped"])
    # atomizer 통과
    assert len(final["atomized_ids"]) == 47
```

- [ ] **Step 3: E2E test 실행 (실 Azure 호출, ~4~8분, ~$0.02)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_graph_e2e.py -v -m slow --timeout=600 2>&1 | tail -30
```

Expected: 1 passed.

- [ ] **Step 4: 전체 회귀**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short 2>&1 | tail -40
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v -m slow --tb=short --timeout=600 2>&1 | tail -40
```

Expected:
- unit: atomizer 6 + prorate 5 + parser 22 + ... 모두 pass
- slow: golden 79 + db 7 + prorate integration 1 + atomizer 5 + e2e 1 모두 pass

- [ ] **Step 5: Commit**

```bash
git add pipeline/graph.py pipeline/tests/test_graph_e2e.py
git commit -m "graph: Phase 1 StateGraph — mapper_node + atomizer_node 연결

Spec §1 (Task 5).

- GraphConfig: MapperConfig + AtomizerConfig 묶음
- mapper_node: map_activity + _prorate_mh
- atomizer_node: atomize (Chroma 적재)
- inner async def 로 cfg 캡처 (lambda 회피, reviewer C3)
- StateGraph: START → mapper → atomizer → END

E2E test_graph_e2e_namwong_47:
- wbs_master_ready fixture (사전조건: count >= 100, reviewer C2)
- @pytest.mark.timeout(600) — 실 Azure LLM 47회 호출 안전 마진
- 9/25 남웅 47 row (비계 제외, golden 부합) → mapped 47 + assigned_workers=88 일관 + Chroma 47 row

Reporter/Forecaster/Optimizer + interrupt 2개 통합은 graph.py 통합 spec 차후.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## 종료 — 회귀 + PR

- [ ] **전체 unit + slow 회귀 최종 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short 2>&1 | tail -40
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v -m slow --tb=short --timeout=600 2>&1 | tail -40
```

Expected:
- unit: 모두 pass
- slow: golden 79 + db 7 + prorate 1 + atomizer 5 + e2e 1 모두 pass

- [ ] **PR 작성**

```bash
git push origin A_Track
gh pr create --base main --title "downstream-agents Phase 1: Atomizer + _prorate_mh + graph.py" --body "$(cat <<'EOF'
## Summary

Spec `docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md` 의 Phase 1 (Task 0~5) 구현.

핵심 결정 11~13 (옵션 X / PGClient 확장 / fixture INSERT) 반영.

- `_prorate_mh()`: (company, l6_main) 단위 BP사 총 인원 분배
- `atomizer.py`: LLM 없음, Chroma daily_activities 적재 (결정성 doc_id upsert)
- `graph.py`: mapper_node + atomizer_node 선형 그래프 (inner async def)
- postgres 3곳 동기화 (init.sql + migration + postgres.md)
- PGClient 신규 4 메서드 (`_pool` 패턴)

## Test plan

- [ ] unit: atomizer 6 + prorate 5 + parser 22 회귀 pass
- [ ] slow integration: db 7 + prorate 1 + atomizer 5 + graph e2e 1 + golden 79 pass
- [ ] 실 9/25 작업일보 → 남웅 47 row (비계 제외) → Chroma 적재 + assigned_workers=88 일관

**B 트랙 알림**: 다음 `docker-compose down -v && up` 시 forecasts schema 갱신됨 (옵션 X (company, l6_main) grain 정정).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 다음 사이클 (별도 brainstorming)

본 plan 완료 후 다음 brainstorming 4 사이클 (의존 순서):

1. **Reporter 구현 spec** — l5_disc/l6_main group by + gpt-5.1 prompt + summary JSONB
2. **Forecaster 구현 spec** — (company, l6_main) RAG + Plan 이중 비교 + LLM TBD
3. **Optimizer 구현 spec** — hil_2_selection + 회복 패턴 + LLM TBD
4. **graph.py 통합 spec** — interrupt 2개 + Reporter/Forecaster/Optimizer 연결 + FastAPI `/run`·`/resume`·`/status`

각 사이클은 본 plan 패턴 (Task 0~N TDD) 동일 적용.
