# CPIA Optimizer + hil_2 + synthetic v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Forecaster Phase 1 종결 시점에서 hil_2 (LangGraph interrupt) + Optimizer (case-by-case 회복 패턴 RAG + Azure gpt-5.1 LLM advice) + synthetic v2 (시계열 회복 7 룰 + 90일 + l7_5_activity from PG) + 가짜 작업일보 + Forecaster 권고 4건 정합을 한 cycle 에 구축 — PoC 데모 시연 가능 상태 (2026-06-05 마감).

**Architecture:** Forecaster cycle 패턴 답습 — `pipeline/agents/optimizer/` 5 모듈 패키지 + `pipeline/checkpointer.py` (InMemorySaver) + `graph.py` 확장 (`forecaster → hil_2 → (selection? optimizer : END) → END` conditional edge). hil_2_node 가 retrieve preview 1회 + state["pre_optimizer_cases"] 영속화 → Optimizer 가 LLM 만 호출 (재호출 회피). recovery_distribution 은 코드단 deterministic 산출 (LLM override). state.py CPIAState 3 필드 + Forecaster row **2 필드** (main_unit + today_conditions — today_productivity 는 Phase 1 시점 이미 박힘, v3.1 정정) 추가.

**Tech Stack:** Python 3.9.6 + asyncio + asyncpg / LangGraph 1.2.0 / chromadb 0.5.20 (validate_where 제약) / Azure OpenAI gpt-5.1-chat-ai-board-test + text-embedding-3-small 1536d / PostgreSQL 16 / pytest + pytest-asyncio.

**Spec:** `/Users/kyungseoplee/Project Agent/CPIA/docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` (v3.1, 23 결정 사항). plan reviewer 1회차 v1 발견 통합 정정 (Blocker 1 + Critical 4 + Major 7 + Moderate 3).

---

## Hard Rules (전역 CLAUDE.md — 매 step 준수 의무)

- **Real code or no claim** — 추측 금지. 실 import + 실 호출 + 실 출력만
- **No fixes without root cause** — 증상만 가리는 패치 금지
- **No fabrication** — 모르면 grep / context7 MCP
- **No 한자** — 한글 + 영어만 (`物`, `量`, `個` 류 금지)
- **TDD as default** — 실패 테스트 먼저 → 구현 → green 확인
- **Iron Law 3요소 보고**: `$ <실 명령어>` + `<실 출력 원본>` + `→ <도출한 결론>` 셋 다
- **Surgical edits** — 요청과 직접 연결 안 된 라인 X
- **from __future__ import annotations** — 모든 .py 첫 줄 필수
- **@tool 함수 시그니처** — `Optional[X]` (`X | None` 금지)
- **환경**: macOS Apple Silicon, Python 3.9.6, `pipeline/.venv/bin/python3` 절대경로
- **psql 바이너리 미존재** — SQL 실행은 `pipeline/.venv/bin/python3 -c "asyncpg.execute(...)"` 또는 `docker exec -i cpia-pg-local psql -U cpia -d cpia < file.sql` (Critical #2 정정)
- **LLM**: Azure gpt-5.1, temperature 박지 않음. Embedding text-embedding-3-small 1536d

---

## File Structure

### 신규 파일 (Create)
```
pipeline/constants.py                                   # WORK_HOURS_PER_DAY=8 (Task 0)
pipeline/checkpointer.py                                # build_checkpointer() InMemorySaver (Task 8)
pipeline/agents/optimizer/__init__.py                   # OptimizerConfig + optimize() (Task 6)
pipeline/agents/optimizer/agent.py                      # optimize() + _compute_recovery_distribution + cold_start (Task 6)
pipeline/agents/optimizer/retrieve.py                   # 2 함수 + _group_baseline + _group_day_productivity (Task 4)
pipeline/agents/optimizer/prompt.py                     # SYSTEM_PROMPT + FEW_SHOT 3 + build_llm_user_input (Task 5)
pipeline/agents/optimizer/synthetic_v2.py               # state machine 7 룰 + CLI (Task 2~3)
pipeline/agents/optimizer/synthetic_daily_report.py     # 가짜 작업일보 + build_demo_graph CLI (Task 11)
infra/postgres/migrations/2026-05-16_optimizer_hil2.sql # PG migration (Task 0)
pipeline/tests/optimizer/__init__.py
pipeline/tests/optimizer/test_retrieve.py               # 12 unit (Task 4)
pipeline/tests/optimizer/test_synthetic_v2.py           # 10 unit (Task 2)
pipeline/tests/optimizer/test_prompt.py                 # 3 unit (Task 5)
pipeline/tests/optimizer/test_agent.py                  # 4 unit (Task 6)
pipeline/tests/optimizer/test_integration.py            # 4 integration (Task 7)
pipeline/tests/test_graph_e2e_hil2.py                   # 4 E2E (Task 9)
pipeline/tests/optimizer/test_synthetic_daily_report.py # 1 E2E + unit (Task 11)
```

### 수정 파일 (Modify)
```
pipeline/agents/forecaster/constants.py                 # re-export pipeline.constants (Task 0)
pipeline/agents/forecaster/aggregate.py                 # docstring × 8 → WORK_HOURS_PER_DAY (Task 10)
pipeline/agents/forecaster/classify.py                  # 임계값 inline → 상수화 (Task 10)
pipeline/agents/forecaster/agent.py                     # row dict 에 main_unit + today_conditions 추가 (Task 1 — today_productivity 이미 박힘)
pipeline/state.py                                       # CPIAState 3 필드 (Task 1)
pipeline/db.py                                          # insert_forecast 25→27 컬럼 (v3.1) + insert_optimizer_advice 신규 (Task 1 + 6)
pipeline/graph.py                                       # hil_2_node + optimizer_node + conditional edge + GraphConfig.optimizer + build_demo_graph (Task 8 + 11)
infra/postgres/init.sql                                 # cold start 동기화 (Task 0)
docs/schema/postgres.md                                 # §6 forecasts + §7 optimizer_advice 동기화 (Task 0)
docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md  # §3 row 구조 + §10 agent.py 명세 drift 동기화 (Task 1)
pipeline/tests/forecaster/test_aggregate.py             # literal 8 → WORK_HOURS_PER_DAY import (Task 10)
pipeline/tests/forecaster/test_classify.py              # boundary 1px epsilon test (Task 10)
```

### 영향 없는 파일 (touch X)
collector.py / parser.py / mapper.py / atomizer.py / reporter.py / chroma_client.py / api.py

---

## Task 0: PG migration + 3곳 동기화 + WORK_HOURS_PER_DAY 승격 + 환경 smoke

**Files:** `infra/postgres/migrations/2026-05-16_optimizer_hil2.sql` (Create), `pipeline/constants.py` (Create), `pipeline/agents/forecaster/constants.py` (Modify, re-export), `infra/postgres/init.sql` (Modify), `docs/schema/postgres.md` (Modify).

**Spec:** §3.1 + §3.2 + §3.3 + §11.2.

- [ ] **Step 0.1: 회귀 baseline 확인 (sourced from Forecaster Phase 1 회귀, 141 passed)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git status   # working tree clean 확인 (수동 verify, conflict 시 stop)
git checkout A_Track && git pull origin A_Track   # conflict 발생 시 stop + 사용자 보고
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -5
```

Expected: `141 passed in ~520s` (±2분 환경 변동 허용). 0 fail.

- [ ] **Step 0.2: `pipeline/constants.py` 생성**

```python
"""Pipeline-wide constants (cross-agent shared)."""
from __future__ import annotations

WORK_HOURS_PER_DAY: int = 8
```

- [ ] **Step 0.3: `pipeline/agents/forecaster/constants.py` re-export 정정**

```python
"""Forecaster constants — pipeline.constants 로 승격 (backward compat re-export)."""
from __future__ import annotations
from pipeline.constants import WORK_HOURS_PER_DAY  # noqa: F401
```

- [ ] **Step 0.4: 회귀 — forecaster 141 passed 유지**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -5
```

Expected: `141 passed`. 0 fail (re-export 가 동일 symbol 라 import path 영향 없음).

- [ ] **Step 0.5: PG migration SQL 작성 (v3.1 정정 — today_productivity ALTER 제거)**

`infra/postgres/migrations/2026-05-16_optimizer_hil2.sql`:

```sql
-- CPIA Optimizer + hil_2 + synthetic v2 spec (2026-05-16, v3.1) 정합 마이그레이션
-- 산물: spec §3.1 (optimizer_advice 5 컬럼) + §3.2 (forecasts 2 컬럼 — today_productivity 는 Phase 1 시점 이미 있음)

BEGIN;

-- 1. optimizer_advice 5 컬럼 추가 + recommendations TEXT→JSONB
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS forecast_assessment TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS degradation_cases JSONB;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS recovery_distribution JSONB;
ALTER TABLE optimizer_advice ALTER COLUMN recommendations TYPE JSONB
    USING (CASE WHEN recommendations IS NULL THEN NULL ELSE recommendations::JSONB END);

CREATE INDEX IF NOT EXISTS idx_optimizer_advice_company_l6 ON optimizer_advice (company, l6_main);
CREATE INDEX IF NOT EXISTS idx_optimizer_advice_run ON optimizer_advice (run_id);

-- 2. forecasts 2 컬럼 추가 (main_unit + today_conditions) — today_productivity 은 이미 있음
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS main_unit TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_conditions TEXT;

COMMIT;
```

- [ ] **Step 0.6: PG migration 실행 — asyncpg 또는 docker exec (Critical #2 정정: psql 바이너리 미존재)**

옵션 (a) — asyncpg 로 SQL 파일 실행:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && set -a && source .env && set +a
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, os
async def main():
    conn = await asyncpg.connect(os.environ['POSTGRES_URL'])
    with open('infra/postgres/migrations/2026-05-16_optimizer_hil2.sql') as f:
        sql = f.read()
    await conn.execute(sql)
    print('migration applied OK')
    await conn.close()
asyncio.run(main())
"
```

옵션 (b) — docker exec:

```bash
docker exec -i cpia-pg-local psql -U cpia -d cpia < infra/postgres/migrations/2026-05-16_optimizer_hil2.sql
```

Verify:

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, os
async def main():
    conn = await asyncpg.connect(os.environ['POSTGRES_URL'])
    cols = await conn.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='optimizer_advice' ORDER BY ordinal_position\")
    print('optimizer_advice:', [c['column_name'] for c in cols])
    cols = await conn.fetch(\"SELECT column_name FROM information_schema.columns WHERE table_name='forecasts' AND column_name IN ('main_unit', 'today_productivity', 'today_conditions') ORDER BY column_name\")
    print('forecasts new cols:', [c['column_name'] for c in cols])
    await conn.close()
asyncio.run(main())
"
```

Expected:
- `optimizer_advice` 컬럼 (9개): id, run_id, l6_main, diagnosis, recovery_pattern, **recommendations(jsonb)**, created_at, **company, forecast_assessment, degradation_cases, recovery_distribution**
- `forecasts new cols`: `['main_unit', 'today_conditions', 'today_productivity']` (3개 — today_productivity 이미 있음)

- [ ] **Step 0.7: `infra/postgres/init.sql` 동기화 (cold start)**

Read 후 `optimizer_advice` + `forecasts` 정의를 마이그레이션과 일치하게 수정 (today_productivity 는 forecasts 정의에 이미 있음, 변경 없음).

- [ ] **Step 0.8: `docs/schema/postgres.md` 동기화 (문서)**

§6 forecasts 표 (main_unit + today_conditions 추가) + §7 optimizer_advice 표 (5 컬럼 + recommendations JSONB) + §12 변경 이력에 본 spec 한 줄 추가.

- [ ] **Step 0.9: 환경 smoke — Azure + PG + Chroma 호출**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg, chromadb, os
from openai import AzureOpenAI

async def main():
    conn = await asyncpg.connect(os.environ['POSTGRES_URL'])
    n = await conn.fetchval('SELECT count(*) FROM activity_master')
    print(f'PG activity_master = {n} rows')
    await conn.close()

    c = chromadb.HttpClient(host='localhost', port=8000)
    coll = c.get_collection('daily_activities')
    print(f'Chroma daily_activities = {coll.count()} rows')

    azure = AzureOpenAI(
        api_key=os.environ['AZURE_OPENAI_API_KEY'],
        api_version=os.environ['AZURE_OPENAI_API_VERSION'],
        azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'],
    )
    resp = azure.embeddings.create(model=os.environ['EMBEDDING_MODEL'], input=['smoke test'])
    print(f'Azure embedding dim = {len(resp.data[0].embedding)}')

asyncio.run(main())
"
```

Expected: PG row > 0, Chroma row > 0 (~821 baseline + atomizer 적재), embedding dim = 1536.

- [ ] **Step 0.10: Commit**

```bash
git add pipeline/constants.py pipeline/agents/forecaster/constants.py \
    infra/postgres/migrations/2026-05-16_optimizer_hil2.sql infra/postgres/init.sql \
    docs/schema/postgres.md
git commit -m "$(cat <<'EOF'
optimizer/Task 0: PG migration + WORK_HOURS pipeline/constants 승격 + 3곳 동기화

- pipeline/constants.py 생성 (WORK_HOURS_PER_DAY=8)
- forecaster/constants.py 를 re-export (backward compat)
- PG: optimizer_advice 5 컬럼 추가 + recommendations TEXT→JSONB
- PG: forecasts 2 컬럼 추가 (main_unit + today_conditions) — today_productivity 은 Phase 1 이미 박힘 (v3.1)
- init.sql + postgres.md 3곳 동기화
- 회귀: 141 passed 0 fail 유지

spec: docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §3 + §11.2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: state.py CPIAState 3 필드 + Forecaster row 2 필드 + spec drift 동기화

**목표 (v3.1 정정):** Forecaster row 에 `main_unit` + `today_conditions` **2 필드만** 추가. `today_productivity` 는 Phase 1 시점에 이미 박혀있음 (`agent.py:163,196` + `db.py:218,241`).

**Files:** `pipeline/state.py:106-135` (Modify), `pipeline/agents/forecaster/agent.py:189-223` (Modify), `pipeline/db.py:205-265` (Modify, 25→27 컬럼), `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` (Modify, **§3 row 구조 + §10 agent.py 명세** drift), `pipeline/tests/forecaster/test_agent.py` (Test).

**Spec:** §2.1 + §2.2 (v3.1) + §11.1 (v3.1 정정 — §3 + §10 위치).

- [ ] **Step 1.1: Failing test — Forecaster row 에 main_unit + today_conditions 박혔는지 검증 (today_productivity 검증 X, 이미 박힘)**

`pipeline/tests/forecaster/test_agent.py` 추가:

```python
@pytest.mark.asyncio
async def test_forecast_row_has_main_unit_and_today_conditions():
    """spec §2.2 (v3.1) — Forecaster row 가 main_unit + today_conditions 2 필드 추가 (today_productivity 이미 박힘)."""
    mapped = [{"company": "남웅건설", "l6_main": "철근콘크리트공사",
               "unit": "m3", "today_qty": 80.0, "assigned_workers": 88.0,
               "work_content": "기초공사 거푸집", "conditions": "맑음",
               "l5_disc": "건축", "wa": "CUB", "worker_source": "mh_prorated",
               "mapping_conf": 0.85}]
    cfg = _make_test_forecaster_config()
    rows = await forecast(mapped, uuid.uuid4(), date(2025, 9, 25), cfg)
    assert "main_unit" in rows[0], "v3.1: main_unit 신규 필드"
    assert "today_conditions" in rows[0], "v3.1: today_conditions 신규 필드"
    # today_productivity 는 Phase 1 시점 이미 박힘 — 기존 검증
    assert "today_productivity" in rows[0]
```

- [ ] **Step 1.2: Run — FAIL (KeyError: 'main_unit' or 'today_conditions')**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/forecaster/test_agent.py::test_forecast_row_has_main_unit_and_today_conditions -v
```

Expected: FAIL with assertion (main_unit / today_conditions 둘 다 없음).

- [ ] **Step 1.3: `pipeline/agents/forecaster/agent.py:189-223` row dict 에 2 필드 추가**

`_forecast_one_group()` return dict 의 마지막 부분 (line 223 직전) 에:

```python
return {
    # ... 기존 25 필드 ...
    "risk_level": risk_level,
    "main_unit": main_unit,                                              # ★ v3.1 신규
    "today_conditions": ",".join(sorted(conditions_set)) if conditions_set else "",  # ★ v3.1 신규
}
```

`conditions_set` 은 같은 그룹 Activity 들의 conditions 합집합 (Phase 1 시점 이미 변수로 있음, line 164 `today_data["conditions"]` 와 동일 set).

- [ ] **Step 1.4: Run — PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/forecaster/test_agent.py::test_forecast_row_has_main_unit_and_today_conditions -v
```

Expected: PASS.

- [ ] **Step 1.5: `pipeline/db.py:205-265` insert_forecast 25→27 컬럼 정정 (v3.1)**

```sql
INSERT INTO forecasts (
    run_id, company, l6_main,
    today_qty_by_unit, today_assigned_workers, today_productivity,
    plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish, plan_mh_per_day,
    schedule_state, window_start, window_days,
    expected_in_window_mh, actual_in_window_mh, mh_gap, delay_days,
    rag_n_similar, similar_cases,
    assessment, reasoning, recovery_likelihood,
    expected_completion, risk_level,
    main_unit, today_conditions                       -- ★ v3.1 신규 2개
) VALUES ($1, ..., $25, $26, $27)
```

`row.get("main_unit")` + `row.get("today_conditions")` 추가.

- [ ] **Step 1.6: 회귀 — 기존 141 + 신규 1 = 142**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -5
```

Expected: `142 passed`. 0 fail.

- [ ] **Step 1.7: `pipeline/state.py:106-135` CPIAState 3 필드 추가**

```python
class CPIAState(TypedDict):
    # ... 기존 필드 ...
    hil_2_selection: list[str]
    pre_optimizer_cases: dict[str, list[dict]]
    optimizer_advice: list[dict]
```

- [ ] **Step 1.8: 회귀 (state.py 추가만, 142 passed 유지)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -5
```

Expected: `142 passed`.

- [ ] **Step 1.9: Forecaster spec design.md §3 row 구조 + §10 agent.py 명세 drift 동기화 (Critical F1 정정)**

`docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md`:
- **§3 row 구조** (NOT §6 = classify) 의 row dict 정의에 `main_unit` + `today_conditions` 2 필드 추가 (today_productivity 는 이미 박힘)
- **§10 agent.py 명세** `_forecast_one_group()` 코드 블록 정정:
  - main_unit positive_units 필터 (qty=0 제외)
  - reasoning 4 분기 (cold start)
  - return dict 에 2 필드 박음
- §18 변경 이력 한 줄 ("optimizer cycle Task 1 동반 — main_unit + today_conditions 2 필드 추가 (today_productivity 이미 박힘)")

- [ ] **Step 1.10: Commit**

```bash
git add pipeline/state.py pipeline/agents/forecaster/agent.py pipeline/db.py \
    pipeline/tests/forecaster/test_agent.py \
    docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md
git commit -m "optimizer/Task 1: state.py 3 필드 + Forecaster row 2 필드 (main_unit + today_conditions) + Forecaster spec §3/§10 drift 동기화 (v3.1)"
```

---

## Task 2: synthetic_v2.py state machine 7 룰 (TDD)

**Files:** `pipeline/agents/optimizer/synthetic_v2.py` (Create), `pipeline/tests/optimizer/test_synthetic_v2.py` (Create).

**Spec:** §4.1 (룰 7) + §4.2 (state machine) + §4.3 (l7_5_activity 풀).

- [ ] **Step 2.1: Failing test — 룰 2 (장비대기 익일 80% 정상 복귀, **통계 검증** N=100)**

```python
def test_state_machine_equip_wait_recovery_d1_statistical():
    """룰 2: 장비대기 → 익일 정상 80% 통계 (N=100 sample, 0.7~0.9 band)."""
    recovered = 0
    total = 0
    for seed in range(100):
        rows = generate_synthetic_v2_group(
            company="남웅건설", l6_main="철근콘크리트공사",
            activity_pool=["기초공사 : 거푸집 공사"], baseline_workers=88.0,
            baseline_qty_per_day=20.0, unit="m3", days=10, seed=seed,
        )
        for i in range(len(rows) - 1):
            if "장비대기" in rows[i]["conditions"]:
                total += 1
                if "장비대기" not in rows[i + 1]["conditions"]:
                    recovered += 1
    if total >= 20:  # 충분 sample
        ratio = recovered / total
        assert 0.7 <= ratio <= 0.9, f"룰 2 익일 80% 복귀 = {ratio:.2%} (expected 0.70~0.90)"
```

- [ ] **Step 2.2: Run — FAIL (module not found)**
- [ ] **Step 2.3: `synthetic_v2.py` state machine 구현 (spec §4.2 의사코드)**
- [ ] **Step 2.4: Run — PASS**
- [ ] **Step 2.5~2.12: 룰 3/4/5/6/7 각각 Failing test → 구현 → PASS (통계 검증)**
- [ ] **Step 2.13: Failing test — work_content 단순 활동명 (결정 #22)**

```python
def test_work_content_is_simple_activity_name():
    pool = ["기초공사 : 거푸집 공사", "RC Wall : 철근 조립"]
    rows = generate_synthetic_v2_group(..., activity_pool=pool, days=30, seed=42)
    for r in rows:
        assert r["work_content"] in pool
        assert " / " not in r["work_content"]
```

- [ ] **Step 2.14: PASS**
- [ ] **Step 2.15: Failing test — assigned_workers prorate ± 10% noise (돌관 X 일 때)**
- [ ] **Step 2.16: PASS**
- [ ] **Step 2.17: Failing test — conditions comma-joined str (결정 #19)**
- [ ] **Step 2.18: PASS**
- [ ] **Step 2.19: Failing test — seed 재현성**
- [ ] **Step 2.20: PASS**
- [ ] **Step 2.21: 회귀 + commit**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -5
```

Expected: `152 passed` (142 + 10 신규 unit).

---

## Task 3: synthetic_v2 CLI + 현 synthetic 810 DROP + v2 적재 + baseline 재산출

**Files:** Modify `pipeline/agents/optimizer/synthetic_v2.py` (CLI `_main_cli()` 추가).

**Spec:** §4.5 (BASELINE_WORKERS 27 그룹 enumeration 참조) + §4.7 (810 DROP) + §4.8 (baseline 재산출).

- [ ] **Step 3.1: CLI 구현**

activity_master 에서 (company, l6_main) 별 distinct l7_5_activity 풀 + plan_total_qty 조회 → BASELINE_WORKERS (`downstream-agents-design.md §3.4` 표 27 그룹 그대로 / 또는 PG `_prorate_mh` 결과 fetch) → 각 그룹 generate_synthetic_v2_group → Chroma upsert with `worker_source="synthetic_v2"`.

- [ ] **Step 3.2: 현 synthetic 810 row DROP (Major F3 정정 — mh_prorated 보존 명시)**

```python
# CLI 첫 단계
coll.delete(where={"worker_source": "synthetic"})
# ★ NOTE: only "synthetic" 삭제. "mh_prorated" (atomizer 적재 9/25 실 작업일보) 와 "synthetic_v2" (다음 적재) 는 보존.
```

Verify before delete:
```bash
pipeline/.venv/bin/python3 -c "
import chromadb
c = chromadb.HttpClient(host='localhost', port=8000)
coll = c.get_collection('daily_activities')
print(coll.get(where={'worker_source': 'mh_prorated'}, include=['metadatas'])['metadatas'][:2])
"
```

Expected: mh_prorated 11 row 보존 확인.

- [ ] **Step 3.3: CLI 실 호출 (실 Azure embedding, Critical F4 — cost/time 가시화)**

```bash
PYTHONPATH=$(pwd) pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_v2 \
    --reference-date 2025-09-25 --days 90 --seed 42
```

Expected:
- Cost: 27 그룹 × 90일 = ~2,430 row × 평균 30 tokens (활동명) ≈ 73K input tokens × `text-embedding-3-small` $0.02/1M = **~$0.0015 (거의 무료)**
- Time: batch 16 × 152 batch × API 왕복 ~0.3s = **45~60초** 예상
- Output: `OK upserted ~2430 rows to Chroma daily_activities. worker_source="synthetic_v2".`

(±200 row 변동 허용 — incident 분포 random 차이)

- [ ] **Step 3.4: 적재 분포 verify**

```bash
pipeline/.venv/bin/python3 -c "
import chromadb
from collections import Counter
c = chromadb.HttpClient(host='localhost', port=8000)
coll = c.get_collection('daily_activities')
result = coll.get(where={'worker_source': 'synthetic_v2'}, include=['metadatas'])
n = len(result['ids'])
pairs = Counter((m['company'], m['l6_main']) for m in result['metadatas'])
conds = Counter()
for m in result['metadatas']:
    for c in (m.get('conditions') or '').split(','):
        if c.strip(): conds[c.strip()] += 1
print(f'synthetic_v2 rows = {n}, unique groups = {len(pairs)}')
print(f'conditions: {dict(conds.most_common(10))}')
"
```

Expected: `~2430 rows, unique = 27, conditions {맑음, 우천, 흐림, 장비대기, 자재미입고, 야간연장, 돌관}` 다 등장.

- [ ] **Step 3.5: baseline_value 재산출 (§4.8 의무)**

```bash
pipeline/.venv/bin/python3 -c "
import chromadb
c = chromadb.HttpClient(host='localhost', port=8000)
coll = c.get_collection('daily_activities')
result = coll.get(where={'\$and': [{'company': '남웅건설'}, {'l6_main': '철근콘크리트공사'}, {'worker_source': 'synthetic_v2'}, {'unit': 'm3'}]}, include=['metadatas'])
INCIDENT = ('장비대기', '자재미입고', '우천', '돌관', '야간연장')
prods = [m['today_qty']/m['assigned_workers'] for m in result['metadatas']
         if not any(c in (m.get('conditions') or '') for c in INCIDENT)
         and m['assigned_workers'] > 0 and m['today_qty'] > 0]
baseline = sum(prods)/len(prods) if prods else None
print(f'남웅 철콘 m3 baseline_v2 = {baseline:.3f} (n={len(prods)}) [현 placeholder=15.981]')
"
```

Expected: baseline_v2 출력.

- [ ] **Step 3.6: spec §1.2 [3] placeholder → 실 v2 값 갱신** (큰 shift > 20% 시 룰 가중치 재조정 검토)

- [ ] **Step 3.7: 회귀 + commit**

---

## Task 4: retrieve.py 2 함수 + 헬퍼 (TDD)

**Files:** `pipeline/agents/optimizer/retrieve.py` (Create), `pipeline/tests/optimizer/test_retrieve.py` (Create).

**Spec:** §5.1~§5.4.

- [ ] **Step 4.1~4.24: 12 test (spec §12.1 의 retrieve 10 + boundary 2)**

각 test 별 (Failing → 구현 → PASS) cycle. 핵심 test:
- `test_fetch_degradation_cases_filters_incident_str_substring`
- `test_fetch_degradation_cases_excludes_future_date`
- `test_fetch_degradation_cases_excludes_recovered`
- `test_fetch_degradation_cases_excludes_legacy_synthetic`
- `test_fetch_degradation_cases_top_n_recency`
- `test_fetch_degradation_cases_includes_dolgwan`
- `test_fetch_recovery_trajectory_window_clipped_by_today`
- `test_fetch_recovery_trajectory_recovery_days_first_recovered`
- `test_fetch_recovery_trajectory_no_recovery`
- `test_group_baseline_normal_only_excludes_all_incidents`
- `test_group_baseline_none_when_no_normal_rows`
- `test_group_day_productivity_baseline_unit_zero_workers`

- [ ] **Step 4.25: 회귀 + commit (152 + 12 = 164 passed)**

---

## Task 5: prompt.py system + few-shot 3 + build_llm_user_input (TDD)

**Files:** `pipeline/agents/optimizer/prompt.py` (Create), `pipeline/tests/optimizer/test_prompt.py` (Create).

**Spec:** §6.1~§6.3.

- [ ] **Step 5.1: Failing test — `test_system_prompt_korean_no_command_tone` (Moderate F6 정정 — 한자 검수 spec 예시 자체 검증)**

```python
def test_system_prompt_korean_no_command_tone():
    """spec §6.1: 한글 + 명령형 회피 + 한자 0건. spec 예시 인용 시도 한자 잔존 가능성 — 검수 보호."""
    from pipeline.agents.optimizer.prompt import SYSTEM_PROMPT
    # 한자 검수 (CJK U+4E00~U+9FFF)
    cjk_found = [ch for ch in SYSTEM_PROMPT if '一' <= ch <= '鿿']
    assert not cjk_found, f"한자 발견: {cjk_found[:5]}"
    # 명령형 tone 회피
    for cmd in ("확인 필수", "반드시 ", "해야 합니다"):
        assert cmd not in SYSTEM_PROMPT, f"명령형 tone 발견: {cmd}"
    # 한글 포함 (단순 sanity)
    assert "권장" in SYSTEM_PROMPT or "권고" in SYSTEM_PROMPT
```

- [ ] **Step 5.2: PASS — spec §6.1 SYSTEM_PROMPT 그대로 구현. 한자 0건 확인.**

- [ ] **Step 5.3~5.6: `test_few_shot_messages_count_3` + `test_build_llm_user_input_includes_today_conditions` (Failing → 구현 → PASS)**

- [ ] **Step 5.7: 회귀 + commit (164 + 3 = 167)**

---

## Task 6: agent.py optimize() + _compute_recovery_distribution + PGClient.insert_optimizer_advice + cold_start

**Files:** `pipeline/agents/optimizer/agent.py` (Create), `pipeline/agents/optimizer/__init__.py` (Create), `pipeline/db.py` (Modify, insert_optimizer_advice), `pipeline/tests/optimizer/test_agent.py` (Create).

**Spec:** §7 + §9.

- [ ] **Step 6.1: Failing test — `test_optimize_skip_when_not_in_selection`**

- [ ] **Step 6.2: 구현 + PASS**

- [ ] **Step 6.3: Failing test — `test_optimize_cold_start_when_cases_less_than_3`**

- [ ] **Step 6.4: 구현 + PASS (diagnosis="cold_start")**

- [ ] **Step 6.5: Failing test — `test_optimize_uses_pre_cases_no_retrieve_recall` (v2 정정 — pytest-mock 미설치 우회, source-level 검증)**

```python
def test_optimize_source_does_not_call_retrieve():
    """결정 #8 + F5: agent.py optimize() 가 retrieve.fetch_degradation_cases / fetch_recovery_trajectory 호출 X.
    
    pytest-mock 의존성 회피 — source-level 검증 (inspect.getsource).
    pre_optimizer_cases (state 사전 영속) 만 사용 보장.
    """
    import inspect
    from pipeline.agents.optimizer import agent
    src = inspect.getsource(agent)
    assert "fetch_degradation_cases" not in src, \
        "agent.py 가 retrieve.fetch_degradation_cases 호출 X (pre_optimizer_cases 만 사용)"
    assert "fetch_recovery_trajectory" not in src, \
        "agent.py 가 retrieve.fetch_recovery_trajectory 호출 X"
```

- [ ] **Step 6.6: PASS — agent.py optimize() 가 pre_optimizer_cases 만 사용, retrieve import X**

- [ ] **Step 6.7: Failing test — `test_compute_recovery_distribution_deterministic`**

```python
def test_compute_recovery_distribution_deterministic():
    cases = [
        {"recovery": {"recovery_days": 1}},
        {"recovery": {"recovery_days": 1}},
        {"recovery": {"recovery_days": 2}},
        {"recovery": {"recovery_days": None}},
    ]
    dist = _compute_recovery_distribution(cases)
    assert dist == {"d+1": 2, "d+2": 1, "not_recovered": 1}
```

- [ ] **Step 6.8: PASS — Counter 기반 산출**

- [ ] **Step 6.9: `insert_optimizer_advice` 신규 메서드 (db.py)** — spec §9 의 9 컬럼 INSERT (JSONB falsy `is not None` 보호)

- [ ] **Step 6.10: 회귀 + commit (167 + 4 = 171)**

---

## Task 7: optimizer integration tests (실 PG + 실 Chroma + 실 Azure)

**Files:** `pipeline/tests/optimizer/test_integration.py` (Create).

**Spec:** §12.2.

- [ ] **Step 7.1: `test_synthetic_v2_chroma_upsert_distribution` (90일 × 27 그룹 적재 분포)**
- [ ] **Step 7.2: `test_synthetic_v2_baseline_recheck_after_load` (§4.8)**
- [ ] **Step 7.3: `test_optimize_namwong_e2e` (남웅 1 그룹 실 LLM)**
- [ ] **Step 7.4: `test_insert_optimizer_advice_byte_level` (9 컬럼 JSONB)**
- [ ] **Step 7.5: 회귀 + commit (171 + 4 = 175). 단 integration 은 `@pytest.mark.slow` — default `pytest pipeline/tests/` 가 slow 포함하는지 확인 (`pyproject.toml` 의 `addopts` 또는 `pytest.ini` 의 marker config).**

---

## Task 8: checkpointer.py InMemorySaver + graph.py hil_2/optimizer + conditional edge

**Files:** `pipeline/checkpointer.py` (Create, 현 0 byte 재작성), `pipeline/graph.py` (Modify).

**Spec:** §8.

- [ ] **Step 8.1: `checkpointer.py` 신규**

```python
"""LangGraph checkpoint — Phase 1 PoC: InMemorySaver."""
from __future__ import annotations
from langgraph.checkpoint.memory import InMemorySaver

def build_checkpointer():
    return InMemorySaver()
```

- [ ] **Step 8.2: `graph.py` 수정 — `hil_2_node` (coll.get 1회 + None 분기)**

- [ ] **Step 8.3: `graph.py` 수정 — `optimizer_node` (state["pre_optimizer_cases"] 전달)**

- [ ] **Step 8.4: `graph.py` 수정 — `GraphConfig.optimizer: OptimizerConfig` + conditional_edges + compile(checkpointer=...)**

- [ ] **Step 8.5: Major F6 — 기존 Forecaster E2E test 영향 검증**

기존 `pipeline/tests/test_graph_e2e.py` 가 `forecaster → END` 가정 → 본 cycle `forecaster → hil_2` 변경 후 영향:
- 기존 fixture 의 forecast row 가 risky=정상 만 → hil_2_node 가 `return {"hil_2_selection": [], "pre_optimizer_cases": {}}` → conditional edge END 직행
- expected: 기존 E2E 1 test 가 그대로 passes (interrupt 발생 X). 단 state 에 hil_2_selection / pre_optimizer_cases / optimizer_advice 필드 추가 검증 (assertion 수정 필요 시)

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/test_graph_e2e.py -v --tb=short
```

Expected: 기존 1 passed. fail 시 fixture 의 forecast row risk_level 점검 (정상 만 박혀야 hil_2 interrupt 회피).

- [ ] **Step 8.6: commit**

---

## Task 9: graph E2E (interrupt + Command(resume=) + 4 path)

**Files:** `pipeline/tests/test_graph_e2e_hil2.py` (Create).

**Spec:** §12.3.

- [ ] **Step 9.1: `test_graph_e2e_hil2_interrupt_payload` (risky=이상 1건 → __interrupt__ + preview_cases)**
- [ ] **Step 9.2: `test_graph_e2e_hil2_resume_optimizer` (Command(resume=[key]) → optimizer → END)**
- [ ] **Step 9.3: `test_graph_e2e_hil2_skip_no_risky` (risky 0건 → END 직행)**
- [ ] **Step 9.4: `test_graph_e2e_hil2_resume_empty_selection` (PM 빈 선택 → END)**
- [ ] **Step 9.5: 회귀 + commit (175 + 4 = 179)**

---

## Task 10: Forecaster Minor 권고 정리

**Files:** `pipeline/agents/forecaster/aggregate.py`, `classify.py`, `tests/forecaster/test_aggregate.py`, `tests/forecaster/test_classify.py`.

**Spec:** §11.3.

- [ ] **Step 10.1: aggregate.py docstring `× 8` → `× WORK_HOURS_PER_DAY` + test_aggregate.py:216 literal `8` → import**

- [ ] **Step 10.2: classify.py 임계값 6개 (-0.15, -0.25, 0.85, 0.65, 5, 0.7) → 모듈 상수**

```python
RAG_NORMAL_BOUND = 0.15        # ratio: |today - rag|/rag <= 0.15 → 정상
RAG_WARN_BOUND = 0.25          # 0.15 < ratio <= 0.25 → 주의
PLAN_NORMAL_RATIO = 0.85
PLAN_WARN_RATIO = 0.65
DELAY_DAYS_BOUND = 5
RECOVERY_LIKELIHOOD_BOUND = 0.7
```

- [ ] **Step 10.3: boundary 1px epsilon test 추가 (eps=1e-9 보호)**

```python
def test_classify_assessment_rag_boundary_epsilon():
    assert classify_assessment_rag(rag_avg=1.0, today_productivity=0.75 - 1e-10) == "이상"
    assert classify_assessment_rag(rag_avg=1.0, today_productivity=0.75 + 1e-10) == "주의"
```

- [ ] **Step 10.4: 회귀 + commit (179 + 1 = 180)**

---

## Task 11: synthetic_daily_report.py 가짜 작업일보 + build_demo_graph + CLI

**Files:** `pipeline/agents/optimizer/synthetic_daily_report.py` (Create), `pipeline/graph.py` (Modify, build_demo_graph), `pipeline/tests/optimizer/test_synthetic_daily_report.py` (Create).

**Spec:** §10.

- [ ] **Step 11.1: `synthetic_daily_report.py` 의 `generate_fake_daily_report()` 구현** — spec §10.2 (work_content = activity_name 단순, conditions str, workers_ratio scenario 파라미터).

- [ ] **Step 11.2: `graph.py` 의 `build_demo_graph()` 추가** — spec §10.3 (START → forecaster → hil_2 → (optimizer | END) → END).

- [ ] **Step 11.3: CLI `_main_cli()` 구현 — Critical F3 정정: site_id 처리 + Major F8 정정: --auto-select-all flag**

> ⚠️ **사전 의존성 (v2 coherence F6 정정)**: Task 3 (synthetic v2 적재) **완료 필수**. CLI 의 첫 step 이 `coll.get(where={"worker_source": "synthetic_v2"}, limit=1)` 0 hit 시 **abort + 안내 msg**. Task 3 안 돌렸으면 본 step 진입 X.

```bash
PYTHONPATH=$(pwd) pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --site-id DEMO_SITE \
    --auto-select-all \
    --scenario "남웅건설|철근콘크리트공사|5|돌관|0.45|1.3|m3" \
    --scenario "세보엠이씨|기계소화설비|3|정상|1.0|1.0|m"
```

CLI 내부 흐름:
1. synthetic v2 적재 확인 (`coll.get(where={"worker_source": "synthetic_v2"}, limit=1)` 0 → abort + msg)
2. **sites 테이블 ON CONFLICT DO NOTHING 사전 INSERT** (DEMO_SITE default):
   ```python
   await conn.execute("INSERT INTO sites (site_id, name) VALUES ($1, $2) ON CONFLICT DO NOTHING", site_id, "Demo Site")
   ```
3. `pg.insert_pipeline_run(run_id, site_id, date, status='running')`
4. `mapped = generate_fake_daily_report(...)`
5. `initial_state = {run_id, date, mapped, ...}` + `build_demo_graph(cfg).ainvoke(initial_state, config)`
6. `__interrupt__` 발생 → payload 출력
7. **`--auto-select-all` flag** → 자동 `Command(resume=[모든 risky key])` (interactive 우회). flag 없으면 input() prompt
8. result["optimizer_advice"] 출력

- [ ] **Step 11.4: E2E test — `test_demo_graph_e2e_namwong_dolgwan`**

```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_demo_graph_e2e_namwong_dolgwan():
    """가짜 작업일보 (남웅 돌관) → build_demo_graph → __interrupt__ + Command(resume) → advice."""
    # synthetic v2 적재 선행 가정 (Task 3 완료 후)
    # PG insert_pipeline_run
    # build_demo_graph + ainvoke → __interrupt__
    # Command(resume=["남웅건설|철근콘크리트공사"]) → optimizer advice row 검증
    ...
```

- [ ] **Step 11.5: CLI 실 호출 (auto-select-all, 비대화)**

```bash
PYTHONPATH=$(pwd) pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 --site-id DEMO_SITE --auto-select-all \
    --scenario "남웅건설|철근콘크리트공사|5|돌관|0.45|1.3|m3"
```

Expected: synthetic v2 적재 확인 → DEMO_SITE INSERT → pipeline_runs INSERT → graph invoke → __interrupt__ payload 출력 → auto resume → Optimizer advice row 1건 출력. 종료 코드 0.

- [ ] **Step 11.6: 회귀 + commit (180 + 2 = 182)**

---

## Task 12: 회귀 + 0 한자 검수 (최종)

- [ ] **Step 12.1: 전체 회귀 (175~185 band 허용)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -q --tb=no 2>&1 | tail -10
```

Expected: **`182 passed` ± slow 마커 default 처리에 따라 175~185 band**. Task 별 누적: 141 base → 142 (T1) → 152 (T2) → 164 (T4) → 167 (T5) → 171 (T6) → 175 (T7) → 179 (T9) → 180 (T10) → 182 (T11) = **182 passed expected**.

- [ ] **Step 12.2: 0 한자 검수**

```bash
git ls-files | grep -E '\.(py|md|sql)$' | xargs grep -P '[\x{4e00}-\x{9fff}]' 2>/dev/null | head -20
```

Expected: 0 hit.

- [ ] **Step 12.3: spec/plan 변경 이력 마지막 commit + push 준비**

```bash
git add docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md \
    docs/superpowers/plans/2026-05-16-cpia-optimizer-hil2-plan.md
git commit -m "optimizer/Task 12: 본 cycle 종결 — 회귀 182 passed + 0 한자 검수 + 변경 이력 갱신"
git push origin A_Track
```

---

## Plan Review Loop

본 plan v2 작성 후 `plan-document-reviewer` (coherence + feasibility) 재 dispatch.

## Execution Handoff

reviewer PASS + 사용자 review gate 통과 후:

1. **Subagent-Driven** (추천) — fresh subagent per task + 2-stage review
2. **Inline Execution** — `superpowers:executing-plans`

---

## 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-16 | 초안 v1 — Task 0~12 분해, bite-sized step (TDD). | A 트랙 |
| 2026-05-16 | v2 정정 — plan reviewer 1회차 통합 (Blocker 1 + Critical 4 + Major 7 + Moderate 3). 주요 변경: ① **Forecaster row "3 필드" → "2 필드"** (main_unit + today_conditions. today_productivity 는 Phase 1 시점 이미 박힘) ② Task 1 step 1.1 failing test 정정 (today_productivity 검증 제거) ③ Task 1 step 1.5 INSERT 25→27 컬럼 ④ Task 1 step 1.9 Forecaster spec section 참조 정정 (§6 → **§3 row 구조 + §10 agent.py 명세**, §6 = classify) ⑤ Task 0 step 0.5 SQL 의 today_productivity ALTER 제거 ⑥ Task 0 step 0.6 psql → asyncpg/docker exec (psql 바이너리 미존재) ⑦ Task 3 step 3.2 mh_prorated 보존 명시 ⑧ Task 3 step 3.3 cost 가시화 (~$0.0015 / 45~60s) ⑨ Task 6 step 6.5 mocker.spy(obj, name) 형식 ⑩ Task 8 step 8.5 기존 Forecaster E2E test 영향 명시 ⑪ Task 11 step 11.3 site_id DEMO_SITE default + ON CONFLICT INSERT + `--auto-select-all` flag (interactive 자동화) ⑫ Task 12 step 12.1 회귀 175~185 band (182 expected) ⑬ Task 5 step 5.1 한자 검수 spec 예시 자체 검증 ⑭ Task 2 state machine test 통계 검증 (N=100, 0.7~0.9) ⑮ Task 0 step 0.1 baseline 출처 명시 (Forecaster Phase 1) + ±2분 환경 변동 허용. | A 트랙 |
| 2026-05-17 | 본 cycle 종결 (Task 12 완료) — commit chain 16건 (T0~T11 + T0/T4/T5 fix 3건 + T12). 회귀 누적 183 passed (plan expected 182 = +1 from T5 fix boundary, 175~185 band 안). 0 한자 검수 통과. spec 정정 2건 동시 적용: ① §1.2 [3] baseline placeholder 15.981 → 31.072 (n=54, Task 3 실 적재 결과 +94% — 사용자 결정 = 의도된 구조적 차이) ② §10.2 conditions: str → list[str] (state.Activity 계약 정합, Task 11 implementer 발견). spec/plan 2 파일 git 추적 시작. | A 트랙 |
