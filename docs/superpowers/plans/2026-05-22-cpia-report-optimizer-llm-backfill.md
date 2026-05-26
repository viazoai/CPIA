# CPIA Report Optimizer LLM Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 9/22 광건 수장공사 FAB 4섹션 (진단/유사사례/권고/상세) placeholder + 빈 string + 258일 delay 부실 화면을 LLM-driven 자연어 진단 + 5건+ 사례 + 4건+ 권고 + qty 기반 합리적 delay 로 교체하는 15일치 (2025-09-08 ~ 2025-09-22) BE 데이터 적재 + 9/25 회귀 검증.

**Architecture:** A1~A9 + 옵션 B (cold_start LLM) + 옵션 C (retrieve filter 완화) 는 이미 코드 적용됨 (PoC 검증 OK). 본 plan 은 (1) 코드 reconcile + dead code 제거, (2) LLM 병렬화 4×, (3) atomizer 포함 backfill graph 신설, (4) 일반화된 backfill 스크립트 + 자동 검증, (5) parser conditions 추출 + dummy 정책 fix, (6) 15일 cycle 실행 + 9/25 회귀 + UI 시각 확인 순으로 구성.

**Tech Stack:**
- Python 3.9.6, pipeline/.venv (CPIA 글로벌 venv)
- LangGraph StateGraph + asyncpg + asyncio.Semaphore
- Azure OpenAI `gpt-5.1-chat-ai-board-test` (chat) + `text-embedding-3-small-ai-board-test` (embedding 1536d)
- PostgreSQL AWS RDS (`43.200.85.209:5532/cpia`, POSTGRES_URL in `.env.local`)
- ChromaDB `daily_activities` collection
- Playwright MCP (UI 시각 확인)

**환경 제약:**
- `from __future__ import annotations` 필수
- `@tool` 함수 시그니처는 `Optional[X]` (CPIA 글로벌 룰)
- 한자 절대 금지 (코드/주석/문서 — 한글 + 영어만)
- FE 디자인 불변 — `web/components/reports/OptimizerResult.tsx` / `WPSummaryTable.tsx` 손대지 않음
- 시연 마감 2026-06-05 (목)

---

## File Structure

### 생성 (Create)
| 경로 | 책임 |
|---|---|
| `scripts/backfill_optimizer_advice_llm.py` | 15일 backfill orchestrator. mapped hydrate + pipeline_runs INSERT + build_atomized_demo_graph 호출 + 각 일자 후 backfill_v2 자동 재산출 + B5 통과 기준 자동 출력. 멱등 (--clean) |
| `scripts/verify_backfill_passing.py` | B5 통과 기준 5가지 자동 검증. PG SELECT + 비율 출력 |
| `scripts/measure_work_content_keyword_hits.py` | C1-pre. 9/22 mapper 의 parser_activities.work_content 에 `장비대기/자재미입고/우천/돌관/야간연장` keyword grep, hit 율 출력 |
| `scripts/backfill_mapper_conditions.py` | C1 백필. 기존 mapper_activities.conditions=[] row 를 parser_activities.work_content 재파싱 후 갱신 |
| `scripts/cleanup_over_plan_qty.py` | C2 cleanup. plan_total_qty 초과 row 진단 (수정 X — 사용자 결정 후 적용) |
| `pipeline/agents/forecaster/__init__.py` 의 build_atomized_demo_graph (또는 `pipeline/graph.py` 안에 추가) | B6. atomizer→forecaster→hil_2→optimizer→reporter graph |
| `tests/test_backfill_idempotency.py` | B4 멱등성 unit test (같은 일자 두 번 실행 → advice 행 수 동일) |
| `tests/test_compute_delay_qty.py` | A7 compute_delay qty 산식 회귀 보호 (over-delivered = 음수 / 산식 깨지면 fail) |
| `tests/test_llm_concurrency.py` | B3 병렬화 회귀 보호 (mock Azure 4 동시 호출 검증) |

### 수정 (Modify)
| 경로 | 변경 요지 |
|---|---|
| `pipeline/agents/optimizer/agent.py:75-117` | B2. `_compose_cold_start_row` 함수 정의 dead code 제거 |
| `pipeline/agents/forecaster/agent.py:266-316` | B3. `forecast()` group 루프 asyncio.gather + Semaphore |
| `pipeline/agents/forecaster/agent.py` LLM 호출부 (forecast prompt 의 azure.chat.completions.create) | B3. `asyncio.to_thread` 감쌈 |
| `pipeline/agents/optimizer/agent.py:185-194` | B3. forecast 루프 asyncio.gather + Semaphore |
| `pipeline/agents/optimizer/agent.py` `_call_azure_llm` | B3. async 변형 + `asyncio.to_thread` |
| `pipeline/agents/atomizer.py:34` | B3. `batch_size: int = 16` → `64` |
| `pipeline/graph.py:493` 뒤 | B6. `build_atomized_demo_graph` 신설 (build_demo_graph 카피 + atomizer 노드 prepend) |
| `pipeline/agents/parser_post.py` | C1. `_extract_conditions(work_content, note) -> list[str]` 추가 + `transform_*` 호출 후 결과의 `activities[i].conditions` 박음 |
| `pipeline/agents/parser.py` 또는 `pipeline/agents/mapper.py` | C1. parser_post 결과의 conditions list 가 mapper_activities.conditions jsonb 까지 흘러가는지 확인 + 누락 시 wiring |
| `pipeline/state.py` Activity TypedDict | C1. `conditions: list[str]` 필드 확인 (이미 있으면 skip) |
| `scripts/seed_dummy_year.py` | C2. per-day qty 분배를 `plan_total_qty / plan_period_days × 변동성` cap. plan 초과 시 자동 cap |
| `scripts/backfill_chroma_daily_activities.py` | C2. plan 초과 row warn + cap (C4 의 정합 보강은 시연 후) |
| `pipeline/agents/forecaster/aggregate.py` `compute_delay` / `fetch_chroma_actual` docstring | C5. mh 컬럼 (`expected_in_window_mh / mh_gap / actual_in_window_mh`) 의미 명시 — reference only |

### 참조 (Read-only)
- `docs/superpowers/specs/2026-05-22-cpia-report-optimizer-llm-backfill-design.md` (spec)
- `scripts/poc_optimizer_5day_backfill.py` (B4 base — 1일 PoC 검증 OK)
- `pipeline/api.py` (`_build_prod_graph_config` — backfill 스크립트가 호출)
- `pipeline/agents/atomizer.py` (`atomize()` 함수 시그니처 + `assert_pipeline_run_exists`)

---

## Phase 0 — Reconcile + Dead Code 제거

### Task 1: B1 — git diff 검토 + A3 확인 + 단일 commit

**Files:**
- Read: `pipeline/agents/optimizer/agent.py`, `prompt.py`, `retrieve.py`, `view_builder.py`, `forecaster/agent.py`, `aggregate.py`, `graph.py` (unstaged)
- Read: `scripts/poc_optimizer_5day_backfill.py` (untracked)
- Modify: 없음 (commit 만)

**전제:** writing-plans 단계에서 확인 — `git diff --stat` 7 파일 173+ 라인 변경, 모두 A1~A9 + 옵션 B + 옵션 C 적용분. revert 흔적 없음. A3 `_normalize_impact_share` rename 이미 view_builder.py:1327 에 적용됨.

- [ ] **Step 1: 현 unstaged diff 정독 + 한자 grep 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git diff --stat
git diff pipeline/agents/optimizer/agent.py pipeline/agents/optimizer/prompt.py pipeline/agents/optimizer/retrieve.py pipeline/agents/optimizer/view_builder.py pipeline/agents/forecaster/agent.py pipeline/agents/forecaster/aggregate.py pipeline/graph.py | grep -nP '[\x{4E00}-\x{9FFF}]'
```

Expected: 한자 grep 결과 0건 (한자 금지 룰).

- [ ] **Step 2: A3 `_normalize_impact_share` rename 적용 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -n "_normalize_impact\b\|_normalize_impact_share" pipeline/agents/optimizer/view_builder.py
```

Expected:
- line 374: `def _normalize_impact(raw_impact: float, p90: float) -> float:` (원래 2-arg)
- line 743: `_normalize_impact(r["raw_impact"], p90)` (2-arg caller)
- line 1327: `def _normalize_impact_share(impacts: list[float]) -> list[float]:` (rename 됨)
- line 1502: `_normalize_impact_share([it["impact_raw"] for it in items])` (caller rename 됨)

미적용 시: `replace_all` 로 line 1246 부근 함수명 `_normalize_impact` → `_normalize_impact_share` rename + caller (line 1418) 같이 수정.

- [ ] **Step 3: PoC 스크립트 (untracked) 의 한자 + import 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -nP '[\x{4E00}-\x{9FFF}]' scripts/poc_optimizer_5day_backfill.py
pipeline/.venv/bin/python3 -c "import ast; ast.parse(open('scripts/poc_optimizer_5day_backfill.py').read()); print('OK')"
```

Expected: 한자 0건 + AST parse OK.

- [ ] **Step 4: 단일 commit (A1~A9 + 옵션 B + 옵션 C + PoC 스크립트)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/optimizer/agent.py \
        pipeline/agents/optimizer/prompt.py \
        pipeline/agents/optimizer/retrieve.py \
        pipeline/agents/optimizer/view_builder.py \
        pipeline/agents/forecaster/agent.py \
        pipeline/agents/forecaster/aggregate.py \
        pipeline/graph.py \
        scripts/poc_optimizer_5day_backfill.py \
        docs/superpowers/specs/2026-05-22-cpia-report-optimizer-llm-backfill-design.md \
        docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
git status
git commit -m "$(cat <<'EOF'
feat(report): 4섹션 풍부화 — retrieve 완화 + delay qty 산식 + cold_start LLM

A1: retrieve company filter Optional + None skip (cross-company case retrieve)
A2: graph.hil_2_node where 절 company 제거
A3: view_builder._normalize_impact_share rename (line 374 arity 충돌 해소)
A4: similar_cases description 에 main_unit + workers 명시
A5: 회복분포 풀어쓰기 ("d+2: 1건" → "2일 후 정상 회복 1건")
A6: fetch_degradation_cases worker_source 화이트리스트 제거 + degradation AND→OR
A7: compute_delay qty 기반 산식 (remaining_qty / pace → expected_completion)
A8: fetch_pg_actual_cum_qty 신설 (mapper_activities source of truth)
A9: forecaster._forecast_one_group 정합 (PG actual_cum_qty + expected_completion 박기)
B(option a): cold_start (cases<3) 도 LLM 호출 + prompt.py 빈 array 가이드 추가
C(option c): retrieve filter 완화 (worker_source + degradation OR)

PoC 검증 (9/22 광건 수장공사 FAB):
- delay 258일 → -8일 (앞당김)
- cases 0 → 5건
- LLM-driven advice 비율 2.8% → 100%

Spec: docs/superpowers/specs/2026-05-22-cpia-report-optimizer-llm-backfill-design.md
Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

- [ ] **Step 5: clean tree 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git status
git log --oneline -1
```

Expected: working tree clean, HEAD = 방금 만든 commit.

---

### Task 2: B2 — `_compose_cold_start_row` dead code 제거

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py:75-117` (함수 정의 + import 정리)

**전제:** Task 1 끝난 직후 시점에서, 호출자는 이미 제거됨 (line 190~ 의 `if len(cases) < 3` 분기 삭제). 함수 정의만 잔존.

- [ ] **Step 1: dead 여부 grep 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -rn "_compose_cold_start_row" pipeline/ scripts/ tests/
```

Expected: `pipeline/agents/optimizer/agent.py:75` (정의) 한 곳만. caller 0 건 = dead code 확정.

- [ ] **Step 2: 함수 정의 + 관련 import 제거**

`pipeline/agents/optimizer/agent.py:75-117` 의 `_compose_cold_start_row` 함수 정의 통째 삭제. 만약 함수가 사용하는 import (예: `_compose_cold_start_row` 만 사용하던 모듈) 가 다른 곳에서 안 쓰이면 같이 정리. 단, dead import 정리는 `_compose_cold_start_row` 전용일 때만 — 다른 곳도 쓰면 그대로 둠.

- [ ] **Step 3: import 정리 후 syntax check + 호출 회귀 grep**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -c "from pipeline.agents.optimizer.agent import optimize; print(optimize.__name__)"
grep -rn "_compose_cold_start_row" pipeline/ scripts/ tests/
```

Expected:
- `optimize` import OK
- grep 결과 0건 (함수 흔적 완전 제거)

- [ ] **Step 4: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/optimizer/agent.py
git commit -m "$(cat <<'EOF'
refactor(optimizer): remove _compose_cold_start_row dead code

B2(option a) 확정 — 모든 그룹이 _compose_row path (LLM 호출). 함수 정의 잔존
은 dead code. caller 는 Task 1 의 옵션 B 적용 commit 에서 이미 제거됨.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

## Phase 1 — LLM 병렬화 + atomizer 통합 graph

### Task 3: B3 — `CPIA_LLM_CONCURRENCY` 환경변수 + Semaphore 헬퍼

**Files:**
- Create: `pipeline/agents/_concurrency.py` (단일 SemaphoreFactory)
- Test: `tests/test_llm_concurrency.py`

**Why 별도 파일:** forecaster + optimizer + (필요 시) atomizer 가 같은 `CPIA_LLM_CONCURRENCY` 값을 공유해야 함. asyncio.Semaphore 는 같은 event loop 안에서만 의미 있어 각 함수 진입 시 `get_llm_semaphore()` 호출.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_llm_concurrency.py`:

```python
"""B3 — LLM 병렬화 Semaphore 테스트.

CPIA_LLM_CONCURRENCY=N 일 때 동시에 최대 N개만 진입.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from pipeline.agents._concurrency import get_llm_semaphore


@pytest.mark.asyncio
async def test_semaphore_default_4(monkeypatch):
    monkeypatch.delenv("CPIA_LLM_CONCURRENCY", raising=False)
    sem = get_llm_semaphore()
    assert sem._value == 4  # 기본 4


@pytest.mark.asyncio
async def test_semaphore_env_override(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    sem = get_llm_semaphore()
    assert sem._value == 2


@pytest.mark.asyncio
async def test_semaphore_caps_concurrent(monkeypatch):
    """동시 진입자 ≤ N — 5개 task 를 2 동시 제한으로 돌리면 max concurrent = 2."""
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    sem = get_llm_semaphore()
    in_flight = 0
    max_in_flight = 0

    async def work():
        nonlocal in_flight, max_in_flight
        async with sem:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1

    await asyncio.gather(*(work() for _ in range(5)))
    assert max_in_flight == 2
```

- [ ] **Step 2: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_llm_concurrency.py -v
```

Expected: FAIL with `ModuleNotFoundError: pipeline.agents._concurrency`.

- [ ] **Step 3: 최소 구현**

`pipeline/agents/_concurrency.py`:

```python
"""LLM 동시성 제어 — forecaster + optimizer + atomizer 공유.

env: CPIA_LLM_CONCURRENCY (기본 4)
사용: `async with get_llm_semaphore(): await asyncio.to_thread(azure_sync_call, ...)`
"""
from __future__ import annotations

import asyncio
import os

_DEFAULT = 4


def get_llm_semaphore() -> asyncio.Semaphore:
    """Lazy 생성 (event loop 별). 같은 loop 안에서는 같은 인스턴스가 자연스럽게 공유됨."""
    n = int(os.environ.get("CPIA_LLM_CONCURRENCY", str(_DEFAULT)))
    return asyncio.Semaphore(max(1, n))
```

**Note:** Semaphore 가 task 별로 다른 인스턴스가 되면 제한 효과 X. 그래서 forecaster.forecast() / optimizer.optimize() 가 **함수 entry 에서 한 번** Semaphore 생성 + 같은 그룹/forecast 루프 안에서 공유하는 패턴 (Task 4, 5 에서 적용).

- [ ] **Step 4: 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_llm_concurrency.py -v
```

Expected: 3 passed.

- [ ] **Step 5: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/_concurrency.py tests/test_llm_concurrency.py
git commit -m "$(cat <<'EOF'
feat(concurrency): get_llm_semaphore() + CPIA_LLM_CONCURRENCY (default 4)

forecaster + optimizer + atomizer 공유 Semaphore. Task 4/5 에서 group/forecast
루프 entry 시 한 번 생성 후 asyncio.gather 안에서 공유.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 4: B3 — forecaster.forecast() group 루프 병렬화

**Files:**
- Modify: `pipeline/agents/forecaster/agent.py:266-316` (`forecast()` 함수)

**현재 (forecaster/agent.py:297-313):**

```python
for (wa, company, l6_main), activities in groups.items():
    row = await _forecast_one_group(
        company, l6_main, activities, run_id, today, pg, coll, azure, cfg,
    )
    row["wa"] = wa
    await pg.insert_forecast(row)
    forecast_rows.append(row)
```

직렬 — group 약 120건 × 1 LLM call 이라 1일 cycle ~10분.

**변경 후 (병렬 4):** ~2.5분.

- [ ] **Step 1: forecaster/agent.py 코드 정독**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -c "import ast, inspect
from pipeline.agents.forecaster import agent
src = inspect.getsource(agent.forecast)
print(src)"
```

목표: `forecast()` 함수의 group 루프 + `pg.insert_forecast` 호출 순서 확인. asyncpg pool 이 thread-safe 인지 확인 (CPIAState 의 db.py 의 PGClient).

- [ ] **Step 2: 회귀 보호 테스트 작성**

`tests/test_forecaster_concurrency.py`:

```python
"""B3 — forecaster.forecast() 가 Semaphore 로 동시성 제한.

monkeypatch _forecast_one_group → 진입자 카운트.
mock pg.insert_forecast 도 진입자 카운트 (asyncpg pool acquire 보호 확인용).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_forecast_respects_semaphore(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    from pipeline.agents.forecaster import agent as forecaster_agent

    in_flight = 0
    max_in_flight = 0

    async def fake_one_group(*args, **kwargs):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {
            "company": "c", "l6_main": "l", "wa": "w",
            "assigned_workers": 0, "today_qty_by_unit": {},
            "main_unit": None, "assessment": "정상",
        }

    # 8 groups
    mapped = [
        {"company": f"c{i}", "l6_main": f"l{i}", "wa": f"w{i}",
         "work_content": "x", "trade": "건축"}
        for i in range(8)
    ]
    with patch.object(forecaster_agent, "_forecast_one_group", side_effect=fake_one_group), \
         patch.object(forecaster_agent, "PGClient") as MockPG, \
         patch.object(forecaster_agent, "ChromaClient"), \
         patch.object(forecaster_agent, "AzureOpenAI"):
        MockPG.return_value.connect = AsyncMock()
        MockPG.return_value.close = AsyncMock()
        MockPG.return_value.assert_pipeline_run_exists = AsyncMock()
        MockPG.return_value.insert_forecast = AsyncMock()
        cfg = type("Cfg", (), {
            "postgres_url": "x", "chroma_host": "x", "chroma_port": 0, "chroma_ssl": False,
            "azure_api_key": "x", "azure_api_version": "x", "azure_endpoint": "x",
            "azure_timeout": 1, "azure_max_retries": 0,
        })()
        await forecaster_agent.forecast(mapped, uuid.uuid4(), date(2025, 9, 22), cfg)

    assert max_in_flight == 2, f"expected max 2, got {max_in_flight}"
```

- [ ] **Step 3: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_forecaster_concurrency.py -v
```

Expected: FAIL with `assert max_in_flight == 2` → **현재 직렬 코드는 max_in_flight == 1** (`asyncio.gather` 미사용 + Semaphore 미진입, 한 번에 1개씩 순차). 병렬화 구현 후 정확히 2 가 되어야 통과.

(만약 fail message 가 `8` 이면 `asyncio.gather` 만 적용하고 Semaphore 미진입 — Step 4 구현 시 `async with sem:` 누락. 두 fail case 가 자가 진단용 신호로 작동.)

- [ ] **Step 4: 구현 — forecast() 안 asyncio.gather + Semaphore**

`pipeline/agents/forecaster/agent.py:266` 의 `forecast()` 안:

```python
from pipeline.agents._concurrency import get_llm_semaphore

async def forecast(
    mapped: list[Activity],
    run_id: uuid.UUID,
    today: date,
    cfg: ForecasterConfig,
) -> list[dict[str, Any]]:
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    try:
        await pg.assert_pipeline_run_exists(run_id)

        groups: dict[tuple[str | None, str, str], list[Activity]] = {}
        for a in mapped:
            if a["l6_main"] is None:
                continue
            if not a.get("work_content"):
                continue
            key = (a.get("wa"), a["company"], a["l6_main"])
            groups.setdefault(key, []).append(a)

        sem = get_llm_semaphore()

        async def _one(key, activities):
            wa, company, l6_main = key
            async with sem:
                row = await _forecast_one_group(
                    company, l6_main, activities, run_id, today, pg, coll, azure, cfg,
                )
            row["wa"] = wa
            await pg.insert_forecast(row)
            return row

        tasks = [_one(k, v) for k, v in groups.items()]
        forecast_rows = await asyncio.gather(*tasks)
        return forecast_rows
    finally:
        await pg.close()
```

**핵심:**
- `async with sem:` 만 LLM 호출 부분 (`_forecast_one_group`) 을 감쌈
- `pg.insert_forecast` 는 sem 밖 — asyncpg pool 이 자체 thread-safe (acquire 직렬화)
- 헤더에 `import asyncio` 추가 (이미 있으면 skip)
- `from pipeline.agents._concurrency import get_llm_semaphore` 추가

- [ ] **Step 5: 통과 확인 + 회귀 (forecaster 기존 test) 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_forecaster_concurrency.py tests/forecaster -v 2>&1 | tail -30
```

Expected: 새 test pass + 기존 forecaster test 회귀 0.

- [ ] **Step 6: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/agent.py tests/test_forecaster_concurrency.py
git commit -m "$(cat <<'EOF'
perf(forecaster): forecast() group 루프 asyncio.gather + Semaphore (4×)

직렬 group ~120건 × 1 LLM call → 약 10분/일.
asyncio.gather + get_llm_semaphore() (CPIA_LLM_CONCURRENCY=4) → 약 2.5분/일.

LLM 호출 (_forecast_one_group) 만 Semaphore 안. pg.insert_forecast 는 밖
(asyncpg pool 이 thread-safe 보장).

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 5: B3 — optimizer.optimize() forecast 루프 병렬화 + `_call_azure_llm` async

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py:185` 부근 + `_call_azure_llm` 정의부

**현재 (optimizer/agent.py:185-194):**

```python
for r in forecast:
    key = f"{r['company']}|{r['l6_main']}"
    if key not in hil_2_selection:
        continue
    cases = pre_optimizer_cases.get(key, [])
    llm_input = build_llm_user_input(r, cases)
    llm_output = _call_azure_llm(llm_input, cfg, azure)  # sync fail-fast
    advice_rows.append(_compose_row(r, cases, llm_output, run_id))
```

`_call_azure_llm` 는 sync — `asyncio.to_thread` 로 감싸야 실 병렬.

- [ ] **Step 1: optimizer/agent.py 정독**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -nA 12 "def _call_azure_llm" pipeline/agents/optimizer/agent.py
```

확인 사항:
- `_call_azure_llm` 시그니처
- 안에서 `azure.chat.completions.create(...)` sync 호출만 있는지 (외부 mutable state 공유 없어야 to_thread 안전)

- [ ] **Step 2: 회귀 보호 테스트**

`tests/test_optimizer_concurrency.py`:

```python
"""B3 — optimizer.optimize() 가 Semaphore 로 동시성 제한 (4 → 2 → max 2)."""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_optimize_respects_semaphore(monkeypatch):
    monkeypatch.setenv("CPIA_LLM_CONCURRENCY", "2")
    from pipeline.agents.optimizer import agent as optimizer_agent

    in_flight = 0
    max_in_flight = 0

    async def fake_call(*a, **kw):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return {"diagnosis": "x", "recommendations": [{"rank": 1, "text": "x"}]}

    forecast = [
        {"company": f"c{i}", "l6_main": f"l{i}", "main_unit": "m",
         "assessment": "이상", "today_productivity": 0.5,
         "today_conditions": "", "wa": "FAB"}
        for i in range(6)
    ]
    hil_sel = [f"{r['company']}|{r['l6_main']}" for r in forecast]

    cfg = type("Cfg", (), {
        "postgres_url": "x", "chroma_host": "x", "chroma_port": 0, "chroma_ssl": False,
        "azure_api_key": "x", "azure_api_version": "x", "azure_endpoint": "x",
        "azure_timeout": 1, "azure_max_retries": 0,
    })()

    with patch.object(optimizer_agent, "_call_azure_llm_async", side_effect=fake_call), \
         patch.object(optimizer_agent, "PGClient") as MockPG, \
         patch.object(optimizer_agent, "AzureOpenAI"):
        MockPG.return_value.connect = AsyncMock()
        MockPG.return_value.close = AsyncMock()
        MockPG.return_value.insert_optimizer_advice = AsyncMock()
        MockPG.return_value._pool = AsyncMock()
        await optimizer_agent.optimize(
            forecast=forecast,
            hil_2_selection=hil_sel,
            pre_optimizer_cases={k: [] for k in hil_sel},
            mapped=[],
            run_id=uuid.uuid4(),
            site_id=None,
            today=None,
            cfg=cfg,
        )

    assert max_in_flight == 2
```

(주의: `optimize()` 시그니처는 실 코드 확인 필요 — Task 5 Step 1 의 정독에서 정확한 kwargs 추출 후 fixture 보정)

- [ ] **Step 3: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_optimizer_concurrency.py -v
```

Expected: FAIL (`_call_azure_llm_async` 아직 없음 + 직렬 path).

- [ ] **Step 4: 구현**

`pipeline/agents/optimizer/agent.py` 수정:

```python
import asyncio
from pipeline.agents._concurrency import get_llm_semaphore

# 기존 _call_azure_llm 옆에 async wrapper 추가
async def _call_azure_llm_async(llm_input: dict, cfg, azure) -> dict:
    """sync _call_azure_llm 을 asyncio.to_thread 로 감쌈 — 실 병렬 효과."""
    return await asyncio.to_thread(_call_azure_llm, llm_input, cfg, azure)


# optimize() 안 for r in forecast 루프 교체:
async def _process_one(r, cases, sem):
    async with sem:
        llm_input = build_llm_user_input(r, cases)
        llm_output = await _call_azure_llm_async(llm_input, cfg, azure)
    return _compose_row(r, cases, llm_output, run_id)

sem = get_llm_semaphore()
tasks = []
for r in forecast:
    key = f"{r['company']}|{r['l6_main']}"
    if key not in hil_2_selection:
        continue
    cases = pre_optimizer_cases.get(key, [])
    tasks.append(_process_one(r, cases, sem))

advice_rows = await asyncio.gather(*tasks) if tasks else []
```

- [ ] **Step 5: 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_optimizer_concurrency.py tests/optimizer -v 2>&1 | tail -30
```

Expected: 새 test pass + 기존 optimizer test 회귀 0.

- [ ] **Step 6: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/optimizer/agent.py tests/test_optimizer_concurrency.py
git commit -m "$(cat <<'EOF'
perf(optimizer): optimize() forecast 루프 asyncio.gather + to_thread (4×)

sync azure.chat.completions.create → _call_azure_llm_async (asyncio.to_thread).
get_llm_semaphore() 로 forecaster 와 같은 4 동시성 제한 공유.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 6: B3 — atomizer batch_size 16 → 64

**Files:**
- Modify: `pipeline/agents/atomizer.py:34` (default)
- Modify: `pipeline/api.py:101` 부근 (`_build_prod_graph_config` 의 `AtomizerConfig(...)` 인스턴스화)

**Why 64:** Azure OpenAI embedding `text-embedding-3-small` 의 input array limit 은 2048. 64 는 안전 margin. 1일 cycle 의 ~200 doc embedding 이 3~4 batch → 1 batch 로 축소 → 호출 횟수 ¼.

- [ ] **Step 1: 현 호출부 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -nA 6 "AtomizerConfig(" pipeline/api.py
sed -n '30,40p' pipeline/agents/atomizer.py
```

확인:
- `atomizer.py:34` default 가 16
- `api.py:101 atomizer_cfg = AtomizerConfig(...)` 에서 batch_size 명시 override 하는지

- [ ] **Step 2: default + 호출부 변경**

`pipeline/agents/atomizer.py:34`:

```python
# BEFORE:
batch_size: int = 16
# AFTER:
batch_size: int = 64  # 2026-05-22: Azure OpenAI embedding input limit 2048, 64 안전. 1일 cycle 호출 ¼.
```

`pipeline/api.py` 의 `AtomizerConfig(...)` 가 batch_size 를 명시 override 하면 거기서도 64. 명시 안 하면 default 그대로 64.

- [ ] **Step 3: 검증 — sanity import**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -c "
from pipeline.agents.atomizer import AtomizerConfig
c = AtomizerConfig(postgres_url='x', chroma_host='x', chroma_port=0,
                   azure_api_key='x', azure_api_version='x', azure_endpoint='x')
print(f'batch_size = {c.batch_size}')
"
```

Expected: `batch_size = 64`.

(주의: AtomizerConfig 필수 kwargs 확인 — 위 dummy 가 통과하려면 모든 필수 필드 채워야)

- [ ] **Step 4: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/atomizer.py pipeline/api.py
git commit -m "$(cat <<'EOF'
perf(atomizer): batch_size default 16 → 64

Azure OpenAI embedding text-embedding-3-small input array limit 2048.
1일 cycle ~200 doc embedding 이 3~4 batch → 1 batch 로 축소.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 7: B6 — `build_atomized_demo_graph` 신설

**Files:**
- Modify: `pipeline/graph.py` (build_demo_graph 옆에 build_atomized_demo_graph 추가)
- Test: `tests/test_atomized_demo_graph_smoke.py`

**Why:** 15일 backfill 의 (atomizer → forecaster → hil_2 → optimizer → reporter) 한 graph 로 단순화. atomizer 가 conditions 갱신 (C1) 까지 흡수 — mapper_activities.conditions 새로 채워지면 atomize 가 Chroma metadata 갱신.

**Design:**
- 기존 `build_graph` (line 533) 의 `mapper → atomizer → forecaster → hil_2 → optimizer → reporter` 에서 **mapper / hil_1 제외**
- 진입 state 가정: `mapped` 가 PG `mapper_activities` 에서 hydrate 된 상태로 들어옴 (backfill 스크립트 책임)
- atomize 호출 전 `pipeline_runs` INSERT 필수 — 스크립트가 책임

- [ ] **Step 1: 기존 build_graph + build_demo_graph 정독**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
sed -n '440,565p' pipeline/graph.py
```

확인:
- atomizer_node 정의 (build_graph 안 `_atomizer` 클로저)
- atomizer 가 `state["mapped"]` 읽고 Chroma 적재 후 `atomized_ids` state 갱신

- [ ] **Step 2: smoke test 작성**

`tests/test_atomized_demo_graph_smoke.py`:

```python
"""B6 — build_atomized_demo_graph compile + 노드 순서 검증."""
from __future__ import annotations

import pytest


def test_build_atomized_demo_graph_compiles(monkeypatch):
    """LangGraph compile 성공 + atomizer 가 entry 다음 노드."""
    from pipeline.graph import build_atomized_demo_graph
    from pipeline.api import _build_prod_graph_config

    cfg = _build_prod_graph_config()
    graph = build_atomized_demo_graph(cfg)
    g = graph.get_graph()
    nodes = {n.id for n in g.nodes.values()}
    assert "atomizer" in nodes
    assert "forecaster" in nodes
    assert "hil_2" in nodes
    assert "optimizer" in nodes
    assert "reporter" in nodes

    # START → atomizer
    edges = [(e.source, e.target) for e in g.edges]
    assert any(s == "__start__" and t == "atomizer" for s, t in edges), edges
    assert any(s == "atomizer" and t == "forecaster" for s, t in edges)
```

- [ ] **Step 3: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_atomized_demo_graph_smoke.py -v
```

Expected: FAIL — `ImportError: cannot import name 'build_atomized_demo_graph'`.

- [ ] **Step 4: 구현 — graph.py 에 build_atomized_demo_graph 추가**

`pipeline/graph.py` 의 `build_demo_graph` (line 493) 함수 끝난 뒤에 추가:

```python
def build_atomized_demo_graph(cfg: GraphConfig):
    """START → atomizer → forecaster → hil_2 → (optimizer | reporter) → END.

    2026-05-22 (Plan B6) — mapper / hil_1 만 skip. mapped 는 호출자가
    PG mapper_activities 에서 hydrate 해서 state['mapped'] 에 주입한 상태로 진입.
    pipeline_runs INSERT 도 호출자 책임 (atomizer.assert_pipeline_run_exists fail-fast).

    15일 backfill 의 표준 graph. C1 (parser conditions 추출) 결과가
    mapper_activities.conditions 에 박힌 후 atomize 가 Chroma metadata 갱신.
    """
    graph = StateGraph(CPIAState)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    async def _hil_2(state: CPIAState) -> dict:
        return await hil_2_node(state, cfg)

    async def _optimizer(state: CPIAState) -> dict:
        return await optimizer_node(state, cfg)

    async def _reporter(state: CPIAState) -> dict:
        return await reporter_node(state, cfg)

    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_node("hil_2", _hil_2)
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)
    graph.add_edge(START, "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile(checkpointer=build_checkpointer())
```

`atomizer_node` 가 graph.py 안에 이미 정의돼 있는지 확인:

```bash
grep -n "async def atomizer_node\|from pipeline.agents.atomizer" pipeline/graph.py | head
```

없으면 build_graph 의 `_atomizer` 패턴을 그대로 차용 + 필요 시 atomizer_node 헬퍼 추출.

- [ ] **Step 5: 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_atomized_demo_graph_smoke.py -v
```

Expected: PASS.

- [ ] **Step 6: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/graph.py tests/test_atomized_demo_graph_smoke.py
git commit -m "$(cat <<'EOF'
feat(graph): build_atomized_demo_graph (atomizer → forecaster → ... → reporter)

15일 backfill 전용 graph. mapper / hil_1 만 skip. mapped 는 PG hydrate
가정. C1 (parser conditions 추출) 결과를 atomize 가 Chroma metadata 갱신.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

## Phase 2 — backfill 스크립트 일반화 + 자동 검증

### Task 8: B4 — `backfill_optimizer_advice_llm.py` 일반화 (rename + 옵션 확장)

**Files:**
- Create: `scripts/backfill_optimizer_advice_llm.py` (기반: `scripts/poc_optimizer_5day_backfill.py`)
- Keep: `scripts/poc_optimizer_5day_backfill.py` (1일 검증 OK — 보존, 새 스크립트 안정화 시 삭제)
- Test: `tests/test_backfill_idempotency.py`

**스크립트 책임 (spec B4):**
- `--days N` (기본 15) 또는 `--start-date / --end-date` range
- `--site m15x-ph3-ibl` / `--trades 건축,토목`
- `--clean`: 같은 (site, date) 의 dummy_seed + 이전 PoC run_id 의 advice/forecasts cascade delete (멱등)
- 각 일자별: mapper_activities hydrate → pipeline_runs INSERT → `build_atomized_demo_graph.ainvoke` → HIL_2 interrupt → auto-select-all → resume
- 각 일자 끝난 후 `backfill_v2 --date YYYY-MM-DD` 자동 호출 (view jsonb 갱신)
- 마지막에 Task 9 (B5) 의 `verify_backfill_passing.py` 자동 호출

- [ ] **Step 1: 기존 PoC 스크립트 정독 + 일반화 포인트 파악**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
wc -l scripts/poc_optimizer_5day_backfill.py
grep -n "^def \|^async def " scripts/poc_optimizer_5day_backfill.py
```

일반화 대상:
- `TARGET_DATES` 하드코딩 → CLI arg
- `SAMPLE_DATE` 하드코딩 제거
- `_run_one_date` 가 `build_demo_graph` → `build_atomized_demo_graph` 호출 (Task 7)
- `--clean` 옵션 추가

- [ ] **Step 2: 멱등성 회귀 보호 테스트 (mock)**

`tests/test_backfill_idempotency.py`:

```python
"""B4 — 같은 (site, date) 두 번 실행 → advice 행 수 동일 + run_id 1개만 잔존."""
from __future__ import annotations

import pytest


def test_clean_returns_ordered_statements():
    """--clean 시 cascade DELETE 4 statement 순서 (advice → forecasts → daily_reports → pipeline_runs)."""
    from scripts.backfill_optimizer_advice_llm import _delete_previous_artifacts_statements

    stmts = _delete_previous_artifacts_statements(site_id="m15x-ph3-ibl", target_date="2025-09-22")
    # list[tuple[str, list]] — asyncpg.execute 는 단일 statement 만 지원하므로 분리 호출.
    assert isinstance(stmts, list) and len(stmts) == 4
    keywords_in_order = [
        "DELETE FROM optimizer_advice",
        "DELETE FROM forecasts",
        "DELETE FROM daily_reports",
        "DELETE FROM pipeline_runs",
    ]
    for (sql, params), expected_kw in zip(stmts, keywords_in_order):
        assert expected_kw in sql
        assert "m15x-ph3-ibl" in params
        assert "2025-09-22" in params
```

(이 테스트는 실 DB 없이 SQL builder helper 만 검증 — 진짜 멱등성은 D1 단계의 실 backfill 실행 결과로 확인. helper 반환은 `list[tuple[str, list]]` 로 통일 — asyncpg 의 `pg._pool.execute` 가 multi-statement string 한 번 호출 불가하기 때문에 4 statement 를 분리해 순차 호출.)

- [ ] **Step 3: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_backfill_idempotency.py -v
```

Expected: FAIL — `ImportError: backfill_optimizer_advice_llm`.

- [ ] **Step 4: 구현 — `scripts/backfill_optimizer_advice_llm.py`**

PoC 스크립트 (poc_optimizer_5day_backfill.py) 카피 + 변경:

핵심 변경:
1. `import argparse` 의 옵션 확장 — `--days`, `--start-date`, `--end-date`, `--site`, `--trades`, `--clean`, `--dry-run`
2. `from pipeline.graph import build_atomized_demo_graph` (build_demo_graph 대체)
3. `_delete_previous_artifacts_statements(site_id, target_date) -> list[tuple[str, list]]` (pure SQL builder, 테스트 가능):
   ```python
   def _delete_previous_artifacts_statements(site_id: str, target_date: str) -> list[tuple[str, list]]:
       sub = ("SELECT run_id FROM pipeline_runs "
              "WHERE site_id=$1 AND report_date=$2")
       params = [site_id, target_date]
       return [
           (f"DELETE FROM optimizer_advice WHERE run_id IN ({sub})", params),
           (f"DELETE FROM forecasts WHERE run_id IN ({sub})", params),
           (f"DELETE FROM daily_reports WHERE run_id IN ({sub})", params),
           (f"DELETE FROM pipeline_runs WHERE site_id=$1 AND report_date=$2", params),
       ]
   ```
   (mapper_activities 는 mock 가 아니라 실 데이터 — DELETE 금지. parser_activities / collector_artifacts 도 보존)
4. `_delete_previous_artifacts(pg, site_id, target_date)` 가 위 4 statement 를 asyncpg 로 순차 실행 (`pg._pool.execute(sql, *params)` 4회):
5. `_run_one_date` 의 graph 호출:
   ```python
   graph = build_atomized_demo_graph(cfg)
   first = await graph.ainvoke(state, config=g_cfg)
   ```
6. 끝부분에 `subprocess.run(["scripts/backfill_v2.py", "--date", d.isoformat()])` 자동 호출 (또는 직접 import 후 함수 호출)
7. 모든 일자 끝나면 `subprocess.run(["pipeline/.venv/bin/python3", "scripts/verify_backfill_passing.py", "--start-date", ..., "--end-date", ...])`

- [ ] **Step 5: SQL builder 테스트 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_backfill_idempotency.py -v
```

Expected: PASS.

- [ ] **Step 6: dry-run smoke (DB 변경 0)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py --start-date 2025-09-22 --end-date 2025-09-22 --site m15x-ph3-ibl --trades 건축,토목 --dry-run
```

Expected: `dry-run — DB 변경 없음` 메시지 + 9/22 mapper_activities 행 수 출력 (≈ 435).

- [ ] **Step 7: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add scripts/backfill_optimizer_advice_llm.py tests/test_backfill_idempotency.py
git commit -m "$(cat <<'EOF'
feat(backfill): backfill_optimizer_advice_llm.py 일반화

PoC 5일 스크립트 → 일반화. --days / --start-date / --end-date / --site /
--trades / --clean / --dry-run. build_atomized_demo_graph (Task 7) 호출.
각 일자 후 backfill_v2 자동 호출 + 끝나면 verify_backfill_passing.py 자동.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 9: B5 — 통과 기준 자동 검증 스크립트

**Files:**
- Create: `scripts/verify_backfill_passing.py`

**5가지 자동 + 2가지 수동 분리:**
| # | 기준 | 자동/수동 |
|---|---|---|
| 1 | diagnosis 평균 ≥ 50자, placeholder = 0% | **자동** |
| 2 | degradation_cases 4필드 채워진 비율 ≥ 90% | **자동** |
| 3 | recommendations {rank, text} schema, text 빈 string = 0% | **자동** |
| 4 | details 6칸 non-"—" 비율 ≥ 80% | **자동** |
| 5 | quadrant ↔ by_wp wp_id 교집합 ≥ 80% | **자동** |
| 6 | UI 시각 확인 (광건/태우/세보엠이씨) | 수동 (Task 17) |
| 7 | delay_days 분포 (over-delivered = 음수, under-delivered = 양수) | **자동** (추가) |

- [ ] **Step 1: 스크립트 구조 + SQL 작성**

`scripts/verify_backfill_passing.py`:

```python
"""B5 통과 기준 5가지 + delay 분포 자동 검증.

usage: python scripts/verify_backfill_passing.py --start-date 2025-09-08 --end-date 2025-09-22 --site m15x-ph3-ibl
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402


PLACEHOLDER_PATTERN = "신규 작업 —"


async def check_diagnosis_length(pg, site_id, start_date, end_date) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT diagnosis, run_id FROM optimizer_advice oa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id=$1 AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock=false
        """,
        site_id, start_date, end_date,
    )
    n = len(rows)
    if n == 0:
        return {"name": "diagnosis 평균 길이", "n": 0, "value": None, "pass": False}
    avg_len = sum(len(r["diagnosis"] or "") for r in rows) / n
    placeholder_n = sum(1 for r in rows if PLACEHOLDER_PATTERN in (r["diagnosis"] or ""))
    placeholder_pct = placeholder_n / n * 100
    passed = avg_len >= 50 and placeholder_n == 0
    return {
        "name": "diagnosis 평균 ≥ 50자, placeholder 0%",
        "n": n, "avg_len": avg_len, "placeholder_pct": placeholder_pct,
        "pass": passed,
    }


async def check_degradation_cases(pg, site_id, start_date, end_date) -> dict:
    rows = await pg._pool.fetch(
        """
        SELECT degradation_cases FROM optimizer_advice oa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id=$1 AND pr.report_date BETWEEN $2 AND $3
          AND pr.is_mock=false
        """,
        site_id, start_date, end_date,
    )
    total = 0
    complete = 0
    for r in rows:
        cases = r["degradation_cases"] or []
        for c in cases:
            total += 1
            if all(c.get(k) is not None for k in ("conditions", "activities", "productivity", "recovery")):
                complete += 1
    pct = complete / total * 100 if total else 0.0
    return {
        "name": "degradation_cases 4필드 ≥ 90%",
        "total": total, "complete": complete, "pct": pct,
        "pass": pct >= 90,
    }


# ... (check_recommendations / check_details / check_quadrant_wp / check_delay_distribution 추가)
```

(check_recommendations: schema 검증 — recommendations[].text 가 비-empty str. check_details: daily_reports.optimizer_view_jsonb.by_wp[wp].details 6칸 non-"—". check_quadrant_wp: quadrant_jsonb.wps[i].wp_id 와 by_wp.keys() 교집합. check_delay_distribution: forecasts.delay_days vs (actual_cum_qty/plan_total_qty) — over-delivered=음수 이어야)

상세 5번 (quadrant ↔ by_wp wp_id) 의 schema 는 view_builder.py 의 `_build_optimizer_view` 가 박는 `by_wp` 형태 + `_build_quadrant` 의 `wps[].wp_id` 확인 후 SQL 작성.

- [ ] **Step 2: 스크립트 단독 smoke 실행 (현 PG 상태 그대로)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-22 --end-date 2025-09-22 --site m15x-ph3-ibl
```

Expected (PoC 검증 결과 반영):
- 9/22 단일 일자라 1 일자 advice 행 수 출력
- 1번 (diagnosis) pass (광건 fab 등 LLM 자연어)
- 2번 (degradation_cases) — A6 후 광건 5건 등 채워짐 → 90%+ 가능성
- 3번 (recommendations) — view_builder 가 text 키만 추출하니 0% empty 가능
- 4번 (details 6칸) — view_jsonb 갱신 후 측정
- 5번 (quadrant ↔ by_wp) — C3 보강 전이라 ~80% 미달 가능 (Task 18 에서 보강)
- 7번 (delay 분포) — 광건 -8일 over-delivered 케이스 음수 확인

미달 항목은 그 자체가 정보 — Task 11 (D1) 본 실행 후 재측정.

- [ ] **Step 3: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add scripts/verify_backfill_passing.py
git commit -m "$(cat <<'EOF'
feat(verify): B5 통과 기준 5가지 + delay 분포 자동 검증

usage: python scripts/verify_backfill_passing.py --start-date X --end-date Y --site Z

5가지 자동 + delay_days 분포. UI 시각 확인 (#6) 만 Task 17 수동.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

## Phase 3 — C1 (conditions 추출) + C2 (dummy 정책)

### Task 10: C1-pre — work_content 키워드 hit 율 측정 (gate)

**Files:**
- Create: `scripts/measure_work_content_keyword_hits.py`

**Gate 룰:** hit 율 ≥ 10% 면 Task 11 (C1) 진행. 미달 시 키워드 확장 또는 외부 날씨 데이터 보강 결정 (사용자에게 다시 질문 → 별도 phase).

- [ ] **Step 1: 스크립트 작성**

`scripts/measure_work_content_keyword_hits.py`:

```python
"""C1-pre — 9/22 mapper 의 parser_activities.work_content 에 키워드 hit 율 측정.

hit 율 ≥ 10% 면 C1 (parser_post _extract_conditions) 진행.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402

KEYWORDS = ["장비대기", "자재미입고", "우천", "돌관", "야간연장", "흐림", "맑음"]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="m15x-ph3-ibl")
    p.add_argument("--date", default="2025-09-22")
    p.add_argument("--trades", default="건축,토목")
    args = p.parse_args()

    trades = args.trades.split(",")
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT COALESCE(pa.work_content, '') AS wc, COALESCE(ma.note, '') AS note
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN parser_activities pa
              ON pa.run_id = ma.run_id AND pa.idx = ma.idx
            WHERE pr.site_id=$1 AND pr.report_date=$2
              AND ma.trade = ANY($3::text[])
              AND ma.is_mock = false
            """,
            args.site, args.date, trades,
        )
        n = len(rows)
        if n == 0:
            print(f"row 0 — site={args.site} date={args.date} trades={trades}")
            return
        print(f"total rows: {n}")
        for kw in KEYWORDS:
            hits = sum(1 for r in rows if kw in r["wc"] or kw in r["note"])
            pct = hits / n * 100
            print(f"  '{kw}': {hits}/{n} ({pct:.1f}%)")
        any_hit = sum(1 for r in rows if any(kw in r["wc"] or kw in r["note"] for kw in KEYWORDS))
        print(f"any keyword: {any_hit}/{n} ({any_hit / n * 100:.1f}%)")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 실행 + hit 율 보고**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/measure_work_content_keyword_hits.py --date 2025-09-22
```

Expected: 9/22 약 435 row 중 키워드 hit 율 출력. 결과 보고 의 (a)(b)(c) 분기:
- (a) any keyword ≥ 10%: Task 11 (C1) 진행
- (b) 1~9%: 사용자에게 보고 + 키워드 확장 옵션 제시
- (c) 0%: parser 가 work_content 에 conditions 정보를 안 적는 가능성 — Task 11 skip + C1 별도 phase

- [ ] **Step 3: commit (스크립트만, 결과는 보고 후 결정)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add scripts/measure_work_content_keyword_hits.py
git commit -m "$(cat <<'EOF'
feat(measure): C1-pre work_content 키워드 hit 율 측정 스크립트

9/22 mapper 의 parser_activities.work_content + ma.note 에 키워드 grep.
hit 율 ≥ 10% 면 Task 11 (C1 parser conditions 추출) 진행 게이트.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 11: C1 — parser_post `_extract_conditions` + 백필 (C1-pre 통과 시)

**Files:**
- Modify: `pipeline/agents/parser_post.py` (`_extract_conditions` 추가)
- Modify: `pipeline/agents/parser.py` 또는 `mapper.py` (parsed['activities'][i]['conditions'] 가 mapper_activities.conditions 까지 흘러가는지 확인)
- Create: `scripts/backfill_mapper_conditions.py` (기존 [] row 백필)
- Test: `tests/test_extract_conditions.py`

**Gate:** Task 10 의 hit 율 ≥ 10% 면 진행. 미달 시 skip + 사용자 보고.

- [ ] **Step 1: parser → mapper → mapper_activities.conditions 데이터 흐름 정독**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -n "conditions" pipeline/agents/parser.py pipeline/agents/parser_post.py pipeline/agents/mapper.py pipeline/state.py | head -30
grep -n "insert_mapper_activities" pipeline/db.py | head
```

확인:
- `Activity` TypedDict 의 `conditions: list[str]` 필드 존재 여부
- parser → parsed.activities[i].conditions 박는 곳
- mapper → Activity dict 의 conditions 가 db.py insert_mapper_activities_batch 의 jsonb 컬럼 매핑되는지

- [ ] **Step 2: 실패 테스트**

`tests/test_extract_conditions.py`:

```python
"""C1 — _extract_conditions(work_content, note) → list[str]."""
from __future__ import annotations

import pytest

from pipeline.agents.parser_post import _extract_conditions


@pytest.mark.parametrize("wc, note, expected", [
    ("타워크레인 장비대기 발생", "", ["장비대기"]),
    ("RC slab 콘크리트 타설", "우천으로 오후 중단", ["우천"]),
    ("야간연장 + 돌관 투입", "", ["야간연장", "돌관"]),
    ("자재미입고 발생", "", ["자재미입고"]),
    ("정상 작업", "", []),
    ("", "", []),
])
def test_extract_conditions(wc, note, expected):
    result = _extract_conditions(wc, note)
    assert sorted(result) == sorted(expected)
```

- [ ] **Step 3: 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_extract_conditions.py -v
```

Expected: FAIL — `cannot import name '_extract_conditions'`.

- [ ] **Step 4: 구현**

`pipeline/agents/parser_post.py` 에 추가:

```python
_CONDITION_KEYWORDS = ("장비대기", "자재미입고", "우천", "돌관", "야간연장")


def _extract_conditions(work_content: str | None, note: str | None) -> list[str]:
    """work_content + note 에서 conditions 키워드 추출.

    키워드 spec §C1: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장.
    중복 제거 + 등장 순서 유지.
    """
    text = f"{work_content or ''} {note or ''}"
    found: list[str] = []
    for kw in _CONDITION_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)
    return found
```

- [ ] **Step 5: 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 -m pytest tests/test_extract_conditions.py -v
```

Expected: 6 passed.

- [ ] **Step 6: parser → mapper 흐름에 wiring**

Step 1 정독 결과 기반으로:
- Activity TypedDict 에 `conditions: list[str]` 가 이미 있고 mapper 가 그대로 전달 — parser 의 transform 함수에서 `_extract_conditions` 호출만 추가
- 없으면 Activity TypedDict + db.py insert 매핑 추가 (PG schema 의 conditions 컬럼이 jsonb 라 형식 변경 X)

- [ ] **Step 7: 백필 스크립트 (기존 [] row 갱신)**

`scripts/backfill_mapper_conditions.py`:

```python
"""C1 백필 — mapper_activities.conditions=[] row 를 work_content 재파싱."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402
from pipeline.agents.parser_post import _extract_conditions  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="m15x-ph3-ibl")
    p.add_argument("--start-date", required=True)
    p.add_argument("--end-date", required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT ma.run_id, ma.idx, COALESCE(pa.work_content, '') AS wc,
                   COALESCE(ma.note, '') AS note, ma.conditions
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN parser_activities pa
              ON pa.run_id = ma.run_id AND pa.idx = ma.idx
            WHERE pr.site_id=$1 AND pr.report_date BETWEEN $2 AND $3
              AND ma.is_mock = false
              AND (ma.conditions IS NULL OR ma.conditions::text = '[]')
            """,
            args.site, args.start_date, args.end_date,
        )
        print(f"백필 후보 rows: {len(rows)}")
        updated = 0
        for r in rows:
            new_conds = _extract_conditions(r["wc"], r["note"])
            if not new_conds:
                continue
            if args.dry_run:
                updated += 1
                continue
            await pg._pool.execute(
                "UPDATE mapper_activities SET conditions=$1::jsonb WHERE run_id=$2 AND idx=$3",
                json.dumps(new_conds), r["run_id"], r["idx"],
            )
            updated += 1
        print(f"갱신 rows: {updated}")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 8: dry-run + 실행 + 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/backfill_mapper_conditions.py --start-date 2025-09-08 --end-date 2025-09-22 --dry-run
# 결과 확인 후
pipeline/.venv/bin/python3 scripts/backfill_mapper_conditions.py --start-date 2025-09-08 --end-date 2025-09-22
pipeline/.venv/bin/python3 -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv('.env.local')
from pipeline.db import PGClient
async def main():
    pg = PGClient(os.environ['POSTGRES_URL']); await pg.connect()
    r = await pg._pool.fetchrow('''
        SELECT count(*) FILTER (WHERE conditions::text != '[]') AS non_empty, count(*) AS total
        FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id='m15x-ph3-ibl' AND pr.report_date BETWEEN '2025-09-08' AND '2025-09-22'
          AND ma.is_mock=false
    ''')
    print(f'conditions non-empty: {r[\"non_empty\"]}/{r[\"total\"]} ({r[\"non_empty\"]/r[\"total\"]*100:.1f}%)')
    await pg.close()
asyncio.run(main())
"
```

Expected: `conditions non-empty` 비율이 0% → ≥ Task 10 의 hit 율 수준 (10%+).

- [ ] **Step 9: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/parser_post.py scripts/backfill_mapper_conditions.py tests/test_extract_conditions.py
git commit -m "$(cat <<'EOF'
feat(parser): _extract_conditions 키워드 추출 + 기존 [] row 백필

키워드: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장. work_content + note grep.
mapper_activities.conditions=[] row 백필 스크립트 동봉.

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

### Task 12: C2 — dummy 생성 정책 fix + plan 초과 cleanup

**Files:**
- Modify: `scripts/seed_dummy_year.py` (per-day qty 분배에 plan_total_qty cap)
- Modify: `scripts/backfill_chroma_daily_activities.py` (plan 초과 warn + cap)
- Create: `scripts/cleanup_over_plan_qty.py` (진단 only — 수정 적용은 별도 결정)

**사용자 결정 (시연 전 적용)**: plan_total_qty 기반 분배 + 시연 영향 부작용 검토.

- [ ] **Step 1: 현 dummy 분배 로직 정독**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -n "today_qty\|plan_total_qty\|random\|np.random" scripts/seed_dummy_year.py | head -30
grep -n "today_qty\|plan_total_qty" scripts/backfill_chroma_daily_activities.py | head -20
```

확인:
- per-day qty 가 어떻게 분배되는지
- plan_total_qty 가 fixture / lookup 어디서 오는지

- [ ] **Step 2: cleanup 진단 스크립트 (먼저 — 시연 화면 부작용 측정)**

`scripts/cleanup_over_plan_qty.py`:

```python
"""C2 진단 — plan_total_qty 초과 row 식별. 적용은 별도 결정."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from pipeline.db import PGClient  # noqa: E402


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="m15x-ph3-ibl")
    p.add_argument("--trades", default="건축,토목")
    args = p.parse_args()

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, unit,
                   SUM(today_qty)::float AS cum_qty,
                   MAX(plan_total_qty)::float AS plan_qty
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            WHERE pr.site_id=$1 AND ma.trade = ANY($2::text[]) AND ma.is_mock=false
            GROUP BY company, l6_main, unit
            HAVING MAX(plan_total_qty) > 0 AND SUM(today_qty) > MAX(plan_total_qty)
            ORDER BY SUM(today_qty) / NULLIF(MAX(plan_total_qty), 0) DESC
            """,
            args.site, args.trades.split(","),
        )
        print(f"over-plan 그룹: {len(rows)}")
        for r in rows[:20]:
            ratio = r["cum_qty"] / r["plan_qty"]
            print(f"  {r['company'][:20]:<20} | {r['l6_main'][:20]:<20} | {r['unit']:<5} | "
                  f"{r['cum_qty']:>8.0f} / {r['plan_qty']:>8.0f} = {ratio*100:.0f}%")
    finally:
        await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 진단 실행 + 사용자에게 보고 (부작용 검토)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/cleanup_over_plan_qty.py
```

Expected: over-plan 그룹 list (광건 수장공사 m2 108% 포함). 다른 over-plan 그룹들이 시연 화면 (광건/태우/세보엠이씨 외) 에 영향 주는지 사용자 검토.

→ **사용자 결정 게이트**: cleanup 적용 (cap) vs 그대로 두기 (광건은 A8 의 PG source 변경으로 이미 우회됨).

- [ ] **Step 4: seed_dummy_year.py 의 per-day qty cap 적용**

(Step 1 정독 결과 기반) per-day 분배 함수에 plan_total_qty 누적 cap 추가. 예시 patch:

```python
# pseudo:
def distribute_qty(plan_total_qty, plan_period_days, day_idx, prior_cum):
    daily_target = plan_total_qty / plan_period_days
    today_qty = daily_target * (1 + random.uniform(-0.3, 0.3))
    # 누적이 plan 을 초과하면 cap
    if prior_cum + today_qty > plan_total_qty:
        today_qty = max(0, plan_total_qty - prior_cum)
    return today_qty
```

- [ ] **Step 5: backfill_chroma_daily_activities.py 도 같은 cap 적용**

ChromaDB 도 같은 일관성 — plan 초과 row 는 적재하지 않거나 cap.

- [ ] **Step 6: dummy seed 재실행 + 진단 재검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
# (사용자 결정 후 — over-plan 데이터 재생성 여부)
# 광건 fab 의 mapper sum / plan 비율이 100% 이내로 조정됐는지 확인
pipeline/.venv/bin/python3 scripts/cleanup_over_plan_qty.py
```

Expected: over-plan 그룹 수 감소 (이상적으로는 0).

- [ ] **Step 7: commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add scripts/seed_dummy_year.py scripts/backfill_chroma_daily_activities.py scripts/cleanup_over_plan_qty.py
git commit -m "$(cat <<'EOF'
fix(dummy): per-day qty 분배에 plan_total_qty 누적 cap

광건 수장공사 mapper sum 108% > plan 원인 해소.
seed_dummy_year + backfill_chroma_daily_activities 양쪽 cap 적용.
cleanup_over_plan_qty.py 는 진단 only (적용은 별도 결정).

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
EOF
)"
```

---

## Phase 4 — dry-run + 15일 실행 + 9/25 회귀 + UI

### Task 13: B3-verify — 1일 dry-run (Azure rate limit 측정)

**Files:** 없음 (실행 only)

**목적:** 15일 본 실행 전 1일치 (9/22) backfill 만 먼저 돌려서:
- Azure OpenAI rate limit (TPM/RPM) 초과 발생 여부
- 실 wall time 측정 (≤ 5분 / 일 예상)
- LLM 호출 횟수 & 비용 추정

- [ ] **Step 1: dry-run 실행 (실 cycle 1일치)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-09-22 --end-date 2025-09-22 \
  --site m15x-ph3-ibl --trades 건축,토목 --clean 2>&1 | tee /tmp/cpia_backfill_1day.log
```

Expected:
- ~5분 wall time
- atomizer: ~5초
- forecaster: ~120 LLM call (~2.5분)
- optimizer: ~30~60 LLM call (~1.5분)
- backfill_v2 재산출 ~30초

- [ ] **Step 2: rate limit 검증**

```bash
grep -i "429\|rate.limit\|quota\|throttl" /tmp/cpia_backfill_1day.log
```

Expected: 0건. 있으면:
- `CPIA_LLM_CONCURRENCY=2` 로 하향 후 재실행
- 안 되면 `=1` (직렬) 로

- [ ] **Step 3: 결과 검증 (verify 스크립트)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-22 --end-date 2025-09-22 --site m15x-ph3-ibl
```

Expected:
- 1번 (diagnosis ≥50자) pass
- 2번 (4필드 ≥90%) pass
- 3번 (text empty 0%) pass
- 4번 (details 6칸 ≥80%) pass
- 7번 (delay 분포) — 광건 fab 행이 음수 (-8일)

- [ ] **Step 4: 결과 보고 (사용자 검토)**

PoC 1일 결과를 사용자에게 보고:
- wall time
- rate limit 발생 여부
- 통과 기준 5건 + delay 분포
- 광건 fab UI 화면 단일 점 클릭 시 4섹션 (Playwright MCP 또는 사용자 직접 확인)

→ **게이트:** 모든 OK 면 Task 14 (D1 15일) 진행. 미달 시 trouble shoot.

---

### Task 14: D1 — 15일 cycle 본 실행 (2025-09-08 ~ 2025-09-22)

**Files:** 없음 (실행 only)

- [ ] **Step 1: clean 옵션으로 15일 본 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-09-08 --end-date 2025-09-22 \
  --site m15x-ph3-ibl --trades 건축,토목 --clean 2>&1 | tee /tmp/cpia_backfill_15day.log
```

Expected: ~75분 wall time (15 × 5). 진행 중 rate limit 발생 시 즉시 abort + Task 13 의 보정 적용 후 재시작.

- [ ] **Step 2: 일자별 advice 행 수 검증 (멱등성)**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv('.env.local')
from pipeline.db import PGClient
async def main():
    pg = PGClient(os.environ['POSTGRES_URL']); await pg.connect()
    rows = await pg._pool.fetch('''
        SELECT pr.report_date, COUNT(oa.*) AS advice_n,
               COUNT(*) FILTER (WHERE oa.diagnosis ~ '신규 작업 —') AS placeholder_n
        FROM pipeline_runs pr LEFT JOIN optimizer_advice oa USING (run_id)
        WHERE pr.site_id='m15x-ph3-ibl' AND pr.report_date BETWEEN '2025-09-08' AND '2025-09-22'
          AND pr.is_mock=false
        GROUP BY pr.report_date ORDER BY pr.report_date
    ''')
    for r in rows:
        print(f'{r[\"report_date\"]}: advice={r[\"advice_n\"]}, placeholder={r[\"placeholder_n\"]}')
    await pg.close()
asyncio.run(main())
"
```

Expected:
- 15 일자별 advice ≥ 50 row
- placeholder = 0 (B2 적용 후)

- [ ] **Step 3: 통과 기준 5건 + delay 분포 자동 검증**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-08 --end-date 2025-09-22 --site m15x-ph3-ibl
```

Expected: 모든 5 + delay 분포 통과.

5번 (quadrant ↔ by_wp) 미달 → Task 18 (C3) 보강 필요. 보강 후 재측정.

- [ ] **Step 4: 결과를 별도 log 로 보존**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-08 --end-date 2025-09-22 --site m15x-ph3-ibl > docs/superpowers/specs/2026-05-22-cpia-backfill-d1-verify.log 2>&1
git add docs/superpowers/specs/2026-05-22-cpia-backfill-d1-verify.log
git commit -m "data(verify): 15일 backfill 통과 기준 log

Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md
"
```

---

### Task 15: D2 — 9/25 회귀 (build_atomized_demo_graph)

**Files:** 없음 (실행 only)

**전제:** 9/25 mapper_activities 가 이미 PG 에 적재됨 (시연 기준일이라 사전 처리됨). 같은 backfill 스크립트 사용.

- [ ] **Step 1: 9/25 사전 상태 확인**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv('.env.local')
from pipeline.db import PGClient
async def main():
    pg = PGClient(os.environ['POSTGRES_URL']); await pg.connect()
    r = await pg._pool.fetchrow('''
        SELECT COUNT(*) AS mapper_n, COUNT(DISTINCT pr.run_id) AS run_n
        FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
        WHERE pr.site_id='m15x-ph3-ibl' AND pr.report_date='2025-09-25'
          AND ma.is_mock=false AND ma.trade = ANY(ARRAY['건축','토목'])
    ''')
    print(f'9/25 mapper rows: {r[\"mapper_n\"]} from {r[\"run_n\"]} runs')
    await pg.close()
asyncio.run(main())
"
```

Expected: mapper_n ≥ 100, run_n ≥ 1. 0 이면 사용자에게 보고 (D2 skip + raw 처리 필요).

- [ ] **Step 2: 9/25 1일 backfill 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-09-25 --end-date 2025-09-25 \
  --site m15x-ph3-ibl --trades 건축,토목 --clean 2>&1 | tee /tmp/cpia_backfill_925.log
```

Expected: ~5분, rate limit 0, advice ≥ 50.

- [ ] **Step 3: 9/25 통과 기준**

```bash
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-25 --end-date 2025-09-25 --site m15x-ph3-ibl
```

Expected: 5건 모두 pass.

- [ ] **Step 4: 결과 log 보존**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-25 --end-date 2025-09-25 --site m15x-ph3-ibl > docs/superpowers/specs/2026-05-22-cpia-backfill-d2-925-verify.log 2>&1
git add docs/superpowers/specs/2026-05-22-cpia-backfill-d2-925-verify.log
git commit -m "data(verify): 9/25 회귀 통과 기준 log"
```

---

### Task 16: D3 — UI `/reports` 시각 확인 (Playwright MCP)

**Files:** 없음 (수동 확인 + screenshot)

**시연 critical:** 9/22 / 9/25 / 9/8 3 일자 의 `/reports` 페이지 4섹션 시각 확인 (광건 / 태우 / 세보엠이씨 wp 점 클릭).

- [ ] **Step 1: 웹 dev server 띄움 (이미 떠 있으면 skip)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web"
npm run dev &
sleep 8
curl -s http://localhost:5536/api/health | head
```

- [ ] **Step 2: Playwright MCP 로 9/22 광건 점 클릭**

(Claude Code agent 가 Playwright MCP 직접 호출)
- `mcp__plugin_playwright_playwright__browser_navigate` → `http://localhost:5536/reports?site=m15x-ph3-ibl&date=2025-09-22`
- `browser_snapshot` 으로 페이지 구조
- 4분면 산점도 광건 점 (impact 최대) hover + click
- 4섹션 (진단 / 유사 과거 사례 / 권고사항 / 상세 현황) snapshot

Expected:
- 진단: 자연어 (placeholder 패턴 X)
- 유사 사례: ≥ 3건
- 권고: ≥ 3건 자연어
- 상세: delay -8 ~ 0일 범위, 단위 명시 "생산성 0.52 m/인 (인원 107명)", 회복분포 풀어쓰기

- [ ] **Step 3: 9/25 광건/태우/세보엠이씨 3 wp 점 클릭**

같은 절차로 시연 기준일 9/25 의 3 wp 화면 caputre.

- [ ] **Step 4: screenshot 보존**

`docs/superpowers/specs/2026-05-22-cpia-d3-ui-{date}-{wp}.png` 형식으로 저장.

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add docs/superpowers/specs/2026-05-22-cpia-d3-ui-*.png
git commit -m "data(verify): D3 UI 시각 확인 screenshot (9/22, 9/25 광건/태우/세보)"
```

- [ ] **Step 5: 사용자 검토 게이트**

screenshot 사용자에게 보고 + OK 면 시연 준비 완료. 미달 시:
- 진단/권고/사례 부실 → optimizer prompt / retrieve 추가 fix (별도 phase)
- 단위/회복분포 표현 → view_builder fix (이미 적용된 부분 회귀 확인)
- delay 이상치 → compute_delay 산식 (A7) 회귀 확인

---

## Phase 5 — 보조 (시연 영향 후순위)

### Task 17: C3 — quadrant ↔ wp_id 매칭 보강 (Task 14 의 통과 기준 5 미달 시)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` (`_build_optimizer_view` 의 wa_lookup miss 처리)

**Gate:** Task 14 (D1) 의 5번 (quadrant ↔ by_wp wp_id 교집합 ≥ 80%) 통과 시 **skip**. 미달 시만 진행.

- [ ] **Step 1: 미스매치 패턴 파악**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
# verify_backfill_passing.py 의 5번 결과 상세 분석:
pipeline/.venv/bin/python3 -c "
# quadrant.wps[].wp_id 와 by_wp.keys() 의 set 차이 출력 — 어느 wp_id 가 매칭 안 되는지
"
```

- [ ] **Step 2: view_builder.py 의 wa_lookup miss 시 fallback**

`_build_optimizer_view` 안 wa_lookup miss path 에 같은 (company, l6_main) advice 를 zone 별 wp_id 에 동일 적용하는 분기 추가.

(상세 위치는 view_builder.py:1020+ `_build_optimizer_view` 정독 후 patch)

- [ ] **Step 3: verify 재실행**

```bash
pipeline/.venv/bin/python3 scripts/verify_backfill_passing.py --start-date 2025-09-08 --end-date 2025-09-22 --site m15x-ph3-ibl
```

Expected: 5번 ≥ 80%.

- [ ] **Step 4: commit**

```bash
git add pipeline/agents/optimizer/view_builder.py
git commit -m "fix(view_builder): wa_lookup miss 시 zone fan-out fallback (quadrant ↔ wp_id 매칭)"
```

---

### Task 18: C5 — forecast mh 컬럼 docstring (의미 명시)

**Files:**
- Modify: `pipeline/agents/forecaster/aggregate.py` `compute_delay` / `fetch_chroma_actual` docstring

- [ ] **Step 1: mh 컬럼 reference 의미 docstring 보강**

이미 git diff 의 docstring 에 일부 명시됨 — 보강:

```python
# compute_delay docstring 끝에 추가
"""
부수 mh 컬럼 (reference only, UI 표시 X):
  - expected_in_window_mh: plan_mh_per_day × window_days (기준 mh)
  - actual_in_window_mh:   실 누적 인시 (Chroma window 기반)
  - mh_gap:                expected - actual (참고만)
  delay 산출은 위 qty 기반 산식 — mh 컬럼은 향후 mh-based KPI 위한 reference.
"""
```

- [ ] **Step 2: 검증 — 한자 0 + import OK**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -nP '[\x{4E00}-\x{9FFF}]' pipeline/agents/forecaster/aggregate.py
pipeline/.venv/bin/python3 -c "from pipeline.agents.forecaster.aggregate import compute_delay, fetch_chroma_actual; print('OK')"
```

Expected: 한자 0 + import OK.

- [ ] **Step 3: commit**

```bash
git add pipeline/agents/forecaster/aggregate.py
git commit -m "docs(aggregate): mh 컬럼 reference 의미 docstring 명시 (C5)"
```

---

### Task 19: C4 — Chroma backfill 정합 (시연 후 phase 분리)

**시연 영향 적음**: A8 의 PG actual_cum_qty source 변경으로 광건 fab delay 우회. C4 는 RAG retrieve 의 의미적 정확도 향상 부수 효과만.

**시연 마감 (2026-06-05) 이후 별도 plan 으로 분리.** 본 plan 에서는 skip.

(필요 시 별도 spec + plan 작성)

---

## 통과 기준 (전체 plan 의 success criterion)

15일 cycle + 9/25 회귀 + UI 시각 확인 끝난 후:

| # | 기준 | 자동/수동 | 통과 라인 |
|---|---|---|---|
| 1 | diagnosis 평균 ≥ 50자, placeholder = 0% | 자동 (verify_backfill_passing.py) | Task 14 |
| 2 | degradation_cases 4필드 채워진 비율 ≥ 90% | 자동 | Task 14 |
| 3 | recommendations text empty = 0% | 자동 | Task 14 |
| 4 | details 6칸 non-"—" ≥ 80% | 자동 | Task 14 |
| 5 | quadrant ↔ by_wp wp_id 교집합 ≥ 80% | 자동 | Task 14 (미달 시 Task 17) |
| 6 | 9/22, 9/25 UI 광건/태우/세보엠이씨 wp 점 클릭 시 진단 자연어 + 사례 ≥3 + 권고 ≥3 | 수동 (screenshot) | Task 16 |
| 7 | delay_days 분포 — over-delivered 음수, under-delivered 양수 | 자동 | Task 14 |

미달 시 phase 분리 (Task 17 + 추후 spec).

---

## 비용 / 시간 추정

- 1일 cycle ≈ 5분 (병렬 4×)
- 15일 ≈ 75분
- 9/25 추가 1일 ≈ 5분
- LLM 비용 ~$15~30 (gpt-5.1-chat ~2,700 chat call + embedding ~3,000)
- 시연 마감 (2026-06-05) 전 1~2회 재실행 여유 있음

---

## 변경 영향 / 리스크

- **FE 디자인 불변** (CPIA 메모리 룰): `OptimizerResult.tsx` / `WPSummaryTable.tsx` 손대지 않음. BE 데이터 적재만.
- **PG schema 변경 없음** (C5 (a) 채택).
- **회귀 위험**: 9/25 실 cycle 의 advice 생성 흐름과 호환 — Task 15 (D2) 가 검증.
- **Azure rate limit**: Task 13 dry-run 에서 측정. 초과 시 CPIA_LLM_CONCURRENCY=2 또는 1 로 하향.
- **dummy 정책 fix (C2) 부작용**: cleanup_over_plan_qty.py 진단 결과로 사용자 검토 후 적용.

---

## 작업 룰 (전역 CLAUDE.md 룰 반영)

- 모든 .py 파일 첫 줄: `from __future__ import annotations`
- 한자 절대 금지 — 코드 / 주석 / 문서 어디에도 (한글 + 영어만)
- venv: `pipeline/.venv/bin/python3` (시스템 python3 사용 금지)
- 작업 시작 전 해당 코드 정독 — grep / Read 로 실 함수 시그니처 확인 (Real research before guess)
- 각 step 검증 보고: `$ <명령>` / `<실 출력>` / `→ <결론>` 3 요소 필수 (verification before done)
- 작업 끝 시 commit message 에 `Plan: docs/superpowers/plans/2026-05-22-cpia-report-optimizer-llm-backfill.md` line 포함
