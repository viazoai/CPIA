# CPIA Forecaster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomizer 다음 단계 Forecaster — (company, l6_main) grain RAG 진단 + Plan fallback + delay_days (누적 mh window) + risk_level hybrid 룰. 9/25 실 데이터 + synthetic 30일 더미로 PoC E2E 통과.

**Architecture:** 5 모듈 패키지 (`pipeline/agents/forecaster/`) — `aggregate.py` 집계·delay 계산, `classify.py` 분류 룰, `rerank.py` Chroma metadata 정규화 + 가중치 rerank, `prompt.py` system + few-shot 3, `synthetic.py` Phase 1 더미 생성, `agent.py` LangGraph node entry. PGClient `_pool` 패턴 + fail-fast (`assert_pipeline_run_exists`). atomizer 와 동일 metadata schema (`_normalize_chroma_metadata` 정규화).

**Tech Stack:** Python 3.9 + asyncio + asyncpg, Azure OpenAI (`gpt-5.1-chat-ai-board-test` + `text-embedding-3-small-ai-board-test`), Chroma 0.5.20, PostgreSQL, LangGraph, pytest + pytest-asyncio + pytest-timeout.

**Spec 출처:** `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` (8 + 3 결정 + reviewer 16 정정 반영)

---

## 0. 환경 + 사용자 하드룰 (모든 Task 공통)

### 0.1 명령어 prefix (사용자 환경 — modern-python PATH shim)

`python3` / `pip` bare 차단됨. 대신:

```bash
# Python 실행
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python3" ...
# 또는
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && uv run python3 ...

# pytest 실행
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/pytest" ...
# 또는
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && uv run pytest ...
```

**모든 plan step 은 venv 절대경로 또는 `uv run` prefix 사용** — bare `python3` 금지.

### 0.2 사용자 전역 CLAUDE.md 하드룰

| 룰 | 적용 |
|---|---|
| **Real code or no claim** | "X 일 것" 추측 금지. 실 import + 실 호출 + 실 출력만 인정 |
| **No fabrication** | 함수/파일/시그니처 모르면 grep. 외부 라이브러리는 context7 MCP |
| **TDD as default** | 새 기능 = 실패 테스트 먼저 → 구현 → green 확인 → done |
| **No 한자** | 코드/문서/응답 어디에도 한자 사용 금지. 한글 + 영어만 |
| **Iron Law 3 요소 보고** | (a) `$ <실 명령어>` + (b) `<실 출력 원본>` + (c) `→ <결론>` 3 요소 모두 포함. (b) 누락 = 미실시 |
| **No features beyond ask** | speculative abstraction / 미요청 configurability 금지 |
| **Surgical edits** | 요청과 직접 연결 안 된 라인 건드리지 말기 |
| **`from __future__ import annotations`** | 모든 .py 첫 줄 필수 |
| **`@tool` 함수** | `Optional[X]` 사용 (`X | None` 금지 — `typing.get_type_hints()` 제약) |

### 0.3 검증 보고 강제 형식 (각 Step 의 "Run" 결과)

```
$ <실 명령어>            ← (a) 무엇을 돌렸는지
<실 출력 — 원본 그대로>   ← (b) 무엇이 나왔는지 (수정/생략 X)
→ <도출한 결론>          ← (c) 그 출력에서 무엇을 알았는지
```

(b) 가 빠지면 미실시로 간주. "통과했습니다" 만 적으면 Iron Law 위반.

---

## 1. File Structure (Task 분해 매핑)

### 1.1 생성

| 파일 | 책임 | Task |
|---|---|---|
| `pipeline/agents/forecaster/__init__.py` | `forecast()` 만 export | Task 6 |
| `pipeline/agents/forecaster/aggregate.py` | aggregate_today_by_unit, fetch_plan_for_group, compute_delay, fetch_chroma_actual | Task 1 |
| `pipeline/agents/forecaster/classify.py` | classify_assessment, classify_risk_level | Task 2 |
| `pipeline/agents/forecaster/rerank.py` | _normalize_chroma_metadata, rerank_cases | Task 3 |
| `pipeline/agents/forecaster/prompt.py` | SYSTEM_PROMPT, FEW_SHOT_MESSAGES, build_llm_user_input | Task 4 |
| `pipeline/agents/forecaster/synthetic.py` | generate_synthetic_day + CLI entry | Task 5 |
| `pipeline/agents/forecaster/agent.py` | ForecasterConfig, forecast(), _forecast_one_group, _format_chroma_result | Task 6 |
| `pipeline/tests/forecaster/__init__.py` | 빈 모듈 (pytest collect) | Task 1 |
| `pipeline/tests/forecaster/test_aggregate.py` | aggregate.py 단위 테스트 | Task 1 |
| `pipeline/tests/forecaster/test_classify.py` | classify.py 단위 테스트 | Task 2 |
| `pipeline/tests/forecaster/test_rerank.py` | rerank.py 단위 테스트 | Task 3 |
| `pipeline/tests/forecaster/test_prompt.py` | prompt.py 단위 테스트 | Task 4 |
| `pipeline/tests/forecaster/test_synthetic.py` | synthetic.py 단위 테스트 | Task 5 |
| `pipeline/tests/forecaster/test_forecaster_integration.py` | 실 PG + 실 Chroma + 실 Azure | Task 7 |
| `pipeline/tests/forecaster/test_forecaster_e2e.py` | mapper + atomizer + forecaster E2E | Task 8 |
| `infra/postgres/migrations/2026-05-16_forecaster.sql` | forecasts 마이그레이션 (JSONB + delay_days NUMERIC) | Task 0 |

### 1.2 수정

| 파일 | 변경 | Task |
|---|---|---|
| `pipeline/db.py` | `fetch_plan_for_group`, `insert_forecast` 2 메서드 추가 | Task 1 (fetch), Task 6 (insert) |
| `pipeline/graph.py` | `GraphConfig.forecaster` 추가, `forecaster_node` 추가, edge: atomizer → forecaster → END | Task 9 |
| `pipeline/agents/forecaster/__init__.py` | export 추가 (Task 진행 따라) | Task 1~6 |
| `infra/postgres/init.sql` | `forecasts` 테이블 정의 spec §3.1 과 일치 정정 | Task 0 |
| `docs/schema/postgres.md` | §6 forecasts 표 + §12 변경 이력 갱신 | Task 0 |

### 1.3 변경 없음 (의존)

| 파일 | 의존 사유 |
|---|---|
| `pipeline/agents/atomizer.py` | metadata schema reference (`_build_metadata` line 45~59) — Forecaster `_normalize` 가 이 schema 와 일치해야 함 |
| `pipeline/chroma_client.py` | `get_or_create_daily_activities()` 그대로 사용 |
| `pipeline/state.py` | `CPIAState["forecast"]` 그대로 사용 (필드 추가 X) |
| `pipeline/agents/mapper.py` | `_prorate_mh` 결과 그대로 사용 |

---

## 2. Task Dependency 표

```
Task 0  →  Task 1  →  Task 2  →  Task 6 ━┐
                  ↘  Task 3  ━━━━━━━━━━┳━┷━ Task 7  →  Task 8  →  Task 9
                     Task 4  ━━━━━━━━━━┛
                     Task 5  (Phase 1 prerequisite — Chroma synthetic 적재. Task 0 후 어디서든)
```

Task 0 = PG schema 정합 (모든 Task 의 prerequisite).  
Task 1~4 = 5 모듈 unit (병렬 가능).  
Task 5 = synthetic 적재 (Task 7 integration 의 prerequisite).  
Task 6 = agent.py 통합 (Task 1~4 완료 후).  
Task 7 = integration 회귀 (Task 5+6 완료 후).  
Task 8 = E2E (Task 7 통과 후).  
Task 9 = graph.py 통합 (Task 8 통과 후).

---

## 3. Task 0: PostgreSQL forecasts 마이그레이션 + 3곳 동기화 + 환경 검증

> **명명 주의 (reviewer #16)**: 본 plan 의 "Task 0" = PG migration + 환경 검증. spec §15.1 의 "Task 0" = synthetic history 30일 + Chroma 적재. **별개 항목 이름 충돌**. 본 plan 의 Task 0 (PG) / Task 5 (synthetic) 가 spec §15.1 의 Task 0 (synthetic) / Task 1 (PG) 와 순서 다름. plan 의 Task 번호로 진행.

**Files:**
- Create: `infra/postgres/migrations/2026-05-16_forecaster.sql`
- Modify: `infra/postgres/init.sql` (forecasts 테이블 정의)
- Modify: `docs/schema/postgres.md` (§6 forecasts 표 + §12 변경 이력)

**Spec 참조:** §3.1 (forecasts 스키마), §13.2 (마이그레이션 SQL)

- [ ] **Step 0: 환경 변수 + 외부 연결 smoke test (reviewer #3, #6)**

Run (`.env` 키 확인):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  set -a && source .env && set +a && \
  for k in POSTGRES_URL AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY \
           AZURE_OPENAI_API_VERSION LLM_MODEL EMBEDDING_MODEL \
           CHROMA_HOST CHROMA_PORT; do
    if [ -z "${!k}" ]; then echo "MISSING: $k"; else echo "OK:      $k"; fi
  done
```
Expected: 8 키 모두 `OK:`. 하나라도 `MISSING:` 면 stop.

Run (PG 연결):
```bash
PGPASSWORD=cpia psql -h localhost -p 5432 -U cpia -d cpia -c "SELECT 1 AS ok"
```
Expected: `?column?=1` 또는 `ok=1` 출력. ERROR 0건.

Run (Azure embedding smoke test — 차원 = 1536 검증):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && set -a && source ../.env && set +a && \
  python -c "
from openai import AzureOpenAI
import os
a = AzureOpenAI(api_key=os.environ['AZURE_OPENAI_API_KEY'],
                api_version=os.environ['AZURE_OPENAI_API_VERSION'],
                azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'])
r = a.embeddings.create(model=os.environ['EMBEDDING_MODEL'], input=['test'])
print('embed dim:', len(r.data[0].embedding))
"
```
Expected: `embed dim: 1536`.

Run (Azure chat smoke test — temperature 미지원 회피 검증, reviewer Spec C-1):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && set -a && source ../.env && set +a && \
  python -c "
from openai import AzureOpenAI
import os
a = AzureOpenAI(api_key=os.environ['AZURE_OPENAI_API_KEY'],
                api_version=os.environ['AZURE_OPENAI_API_VERSION'],
                azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'])
r = a.chat.completions.create(
    model=os.environ['LLM_MODEL'],
    messages=[{'role':'user','content':'ping'}],
    response_format={'type':'json_object'},
)
print('chat ok, content_type ok')
"
```
Expected: `chat ok, content_type ok` 출력. (단, model 이 JSON 강제일 때 'ping' 만으론 JSON 안 줄 수 있음 — 실패 시 messages 에 'reply with {"a":1}' 추가)

Run (Chroma 연결):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/python3 -c "
import os
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host=os.environ['CHROMA_HOST'],
                 port=int(os.environ.get('CHROMA_PORT','8000')),
                 ssl=os.environ.get('CHROMA_SSL','false').lower()=='true')
coll = c.get_or_create_daily_activities()
print('Chroma daily_activities count:', coll.count())
"
```
Expected: `Chroma daily_activities count: <N>`. (현 atomizer 적재 후 11 row 또는 그 이상)

→ 4 smoke test 모두 통과 시 Step 1 진입. Iron Law 3 요소 보고.

- [ ] **Step 1: 현 forecasts schema baseline 확인 (마이그레이션 전 상태)**

Run:
```bash
PGPASSWORD=cpia psql -h localhost -p 5432 -U cpia -d cpia \
  -c "\d forecasts" 2>&1
```
Expected (마이그레이션 **전** 상태 — downstream-agents 마이그레이션 적용된 baseline):
- 기존 컬럼: `run_id UUID, company TEXT, l6_main TEXT, today_qty_by_unit JSONB, today_assigned_workers NUMERIC, plan_total_qty_by_unit JSONB, plan_mh_sum NUMERIC, rag_n_similar INT, similar_cases JSONB, assessment TEXT, reasoning TEXT, expected_completion DATE, delay_days INT, risk_level TEXT, created_at TIMESTAMPTZ, id BIGSERIAL`
- 본 plan Step 2~4 가 추가할 12 컬럼 (`today_productivity`, `plan_start`, `plan_finish`, `plan_mh_per_day`, `schedule_state`, `window_start`, `window_days`, `expected_in_window_mh`, `actual_in_window_mh`, `mh_gap`, `recovery_likelihood`) 은 **이 시점에 없어야 정상**. delay_days 는 INT 타입.

→ Iron Law 3 요소 보고. **baseline 컬럼 수 + delay_days 타입 INT** 기록.

- [ ] **Step 2: 마이그레이션 SQL 작성**

Create `infra/postgres/migrations/2026-05-16_forecaster.sql`:

```sql
-- CPIA Forecaster spec (2026-05-16) 정합 마이그레이션
-- 산물: spec §3.1 / §13.2

BEGIN;

-- forecasts 컬럼 추가 (없으면)
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_productivity NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_finish DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS plan_mh_per_day NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS schedule_state TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_start DATE;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS window_days INT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS expected_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS actual_in_window_mh NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS mh_gap NUMERIC;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS recovery_likelihood NUMERIC;

-- delay_days INT → NUMERIC (PoC 빈 테이블 가정, USING noop)
ALTER TABLE forecasts ALTER COLUMN delay_days TYPE NUMERIC USING delay_days::NUMERIC;

-- index 추가
CREATE INDEX IF NOT EXISTS idx_forecasts_state ON forecasts (schedule_state);

COMMIT;
```

- [ ] **Step 3: 마이그레이션 적용**

Run:
```bash
PGPASSWORD=cpia psql -h localhost -p 5432 -U cpia -d cpia \
  -f "/Users/kyungseoplee/Project Agent/CPIA/infra/postgres/migrations/2026-05-16_forecaster.sql"
```
Expected: `BEGIN`, `ALTER TABLE` (× 11~12), `CREATE INDEX`, `COMMIT` 메시지 출력. ERROR 0건.

→ Iron Law 3 요소 보고.

- [ ] **Step 4: 마이그레이션 후 schema 검증**

Run:
```bash
PGPASSWORD=cpia psql -h localhost -p 5432 -U cpia -d cpia \
  -c "\d forecasts" | grep -E "(plan_start|plan_finish|plan_mh_per_day|schedule_state|window_start|window_days|expected_in_window_mh|actual_in_window_mh|mh_gap|recovery_likelihood|today_productivity|delay_days)"
```
Expected: 12 라인. `delay_days` 타입 = `numeric` (NOT `integer`).

→ Iron Law 3 요소 보고. `delay_days` 가 numeric 인지 byte-level 확인.

- [ ] **Step 5: init.sql 정정 (cold start 동기화)**

Modify `infra/postgres/init.sql` 의 `forecasts` CREATE TABLE 정의 — spec §3.1 SQL 그대로 박음. 기존 `forecasts` 테이블 부분 통째로 교체.

- [ ] **Step 6: postgres.md 갱신**

Modify `docs/schema/postgres.md`:
- §6 forecasts 표에 12 신규 컬럼 추가 + 의미 명시
- §12 변경 이력에 한 줄 추가:
  ```
  | 2026-05-16 | Forecaster spec 정합 — forecasts 12 컬럼 추가 (plan_start/finish, plan_mh_per_day, schedule_state, window_*, mh_gap, today_productivity, recovery_likelihood), delay_days INT → NUMERIC | A 트랙 |
  ```

- [ ] **Step 7: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add infra/postgres/migrations/2026-05-16_forecaster.sql \
        infra/postgres/init.sql \
        docs/schema/postgres.md
git commit -m "$(cat <<'EOF'
postgres: forecaster spec 정합 — forecasts 12 컬럼 추가

- plan_start/finish/mh_per_day (PG activity_master Σ)
- schedule_state (early|on_schedule|post_due|unknown)
- window_start/days, expected_in_window_mh, actual_in_window_mh, mh_gap
- today_productivity, recovery_likelihood
- delay_days INT → NUMERIC

3곳 동기화 (init.sql + migrations + postgres.md).

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §3.1, §13
EOF
)"
```

---

## 4. Task 1: aggregate.py — 4 함수 (TDD)

**Files:**
- Create: `pipeline/agents/forecaster/__init__.py`
- Create: `pipeline/agents/forecaster/aggregate.py`
- Create: `pipeline/tests/forecaster/__init__.py`
- Create: `pipeline/tests/forecaster/test_aggregate.py`
- Modify: `pipeline/db.py` (`fetch_plan_for_group` 메서드 추가)

**Spec 참조:** §5.1, §5.2, §5.3, §5.4

- [ ] **Step 1: 패키지 폴더 생성**

Run:
```bash
mkdir -p "/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/forecaster"
mkdir -p "/Users/kyungseoplee/Project Agent/CPIA/pipeline/tests/forecaster"
```

Create `pipeline/agents/forecaster/__init__.py`:
```python
"""CPIA Forecaster — (company, l6_main) grain RAG 진단.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md
"""

from __future__ import annotations
```

Create `pipeline/tests/forecaster/__init__.py`:
```python
```

- [ ] **Step 2: aggregate_today_by_unit failing test**

Create `pipeline/tests/forecaster/test_aggregate.py`:

```python
"""Forecaster aggregate.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §5
"""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.agents.forecaster.aggregate import (
    aggregate_today_by_unit,
    compute_delay,
)


def test_aggregate_today_by_unit_single():
    activities = [
        {"unit": "m", "today_qty": 80, "company": "X", "l6_main": "Y",
         "assigned_workers": 100, "work_content": "test", "conditions": [],
         "l5_disc": "설비", "wa": "AC", "worker_source": "mh_prorated", "mapping_conf": 0.8},
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0}


def test_aggregate_today_by_unit_multi_unit():
    activities = [
        {"unit": "m", "today_qty": 80, "company": "X", "l6_main": "Y",
         "assigned_workers": 100, "work_content": "a", "conditions": [],
         "l5_disc": "설비", "wa": "AC", "worker_source": "mh_prorated", "mapping_conf": 0.8},
        {"unit": "ea", "today_qty": 12, "company": "X", "l6_main": "Y",
         "assigned_workers": 100, "work_content": "b", "conditions": [],
         "l5_disc": "설비", "wa": "AC", "worker_source": "mh_prorated", "mapping_conf": 0.8},
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0, "ea": 12.0}


def test_aggregate_today_by_unit_same_unit_sum():
    """같은 unit 의 여러 Activity → Σ."""
    activities = [
        {"unit": "m", "today_qty": 50, "company": "X", "l6_main": "Y",
         "assigned_workers": 100, "work_content": "a", "conditions": [],
         "l5_disc": "설비", "wa": "AC", "worker_source": "mh_prorated", "mapping_conf": 0.8},
        {"unit": "m", "today_qty": 30, "company": "X", "l6_main": "Y",
         "assigned_workers": 100, "work_content": "b", "conditions": [],
         "l5_disc": "설비", "wa": "AC", "worker_source": "mh_prorated", "mapping_conf": 0.8},
    ]
    result = aggregate_today_by_unit(activities)
    assert result == {"m": 80.0}
```

- [ ] **Step 3: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_aggregate.py::test_aggregate_today_by_unit_single -v 2>&1 | tail -20
```
Expected: `ModuleNotFoundError: No module named 'pipeline.agents.forecaster.aggregate'`

→ Iron Law 3 요소 보고.

- [ ] **Step 4: aggregate_today_by_unit 구현 (최소)**

Create `pipeline/agents/forecaster/aggregate.py`:

```python
"""Forecaster aggregate — 집계 + delay 계산. 순수 함수 (Chroma/PG 의존성 X).

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §5
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional


def aggregate_today_by_unit(activities: list[dict]) -> dict[str, float]:
    """같은 (company, l6_main) 그룹 안의 Activity 들의 today_qty 를 unit 별 Σ."""
    by_unit: dict[str, float] = {}
    for a in activities:
        u = a["unit"]
        by_unit[u] = by_unit.get(u, 0.0) + a["today_qty"]
    return by_unit
```

- [ ] **Step 5: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_aggregate.py -v 2>&1 | tail -10
```
Expected: 3 passed.

→ Iron Law 3 요소 보고.

- [ ] **Step 6: compute_delay failing tests**

Append to `pipeline/tests/forecaster/test_aggregate.py`:

```python
def test_compute_delay_on_schedule_behind():
    """plan 1/1 ~ 12/31 (365일), mh_sum=3650 (10 mh/day).
    오늘 9/15 (258일째). window 0/1~9/15 (258일). expected=2580. actual=2400.
    → mh_gap=180. delay_days=18.

    reviewer #12 정정: 모든 fixture Activity 에 l5_disc 포함 (atomizer schema 정합).
    아래 test_compute_delay 시리즈는 plan dict 만 받으므로 l5_disc 무관.
    """
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 3650,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 15),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=2400.0,
    )
    assert result["schedule_state"] == "on_schedule"
    assert result["plan_mh_per_day"] == pytest.approx(10.0, abs=0.1)
    assert result["mh_gap"] == pytest.approx(180.0, abs=1.0)
    assert result["delay_days"] == pytest.approx(18.0, abs=0.5)


def test_compute_delay_early_before_start():
    """today 가 plan_start 전 → schedule_state = "early"."""
    plan = {
        "plan_start": date(2025, 12, 1),
        "plan_finish": date(2026, 2, 28),
        "plan_mh_sum": 900,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 11, 15),
        actual_window_start=date(2025, 11, 15),
        actual_cum_mh=0.0,
    )
    assert result["schedule_state"] == "early"


def test_compute_delay_post_due():
    """today 가 plan_finish 후 → schedule_state = "post_due"."""
    plan = {
        "plan_start": date(2024, 1, 1),
        "plan_finish": date(2024, 6, 30),
        "plan_mh_sum": 100,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 25),
        actual_window_start=date(2025, 9, 25),
        actual_cum_mh=50.0,
    )
    assert result["schedule_state"] == "post_due"


def test_compute_delay_unknown_no_plan():
    """plan=None → schedule_state="unknown", delay_days=None."""
    result = compute_delay(
        plan=None,
        today=date(2025, 9, 25),
        actual_window_start=None,
        actual_cum_mh=100.0,
    )
    assert result["schedule_state"] == "unknown"
    assert result["delay_days"] is None
    assert result["plan_mh_per_day"] is None


def test_compute_delay_ahead():
    """actual > expected → delay_days < 0."""
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 3650,
        "plan_total_qty_by_unit": {"m": 100.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 15),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=3000.0,    # expected=2580 보다 많이
    )
    assert result["delay_days"] < 0
    assert result["mh_gap"] < 0
```

- [ ] **Step 7: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_aggregate.py -v 2>&1 | tail -20
```
Expected: 5 failed (compute_delay 없음).

- [ ] **Step 8: compute_delay 구현**

Append to `pipeline/agents/forecaster/aggregate.py`:

```python
def compute_delay(
    plan: Optional[dict],
    today: date,
    actual_window_start: Optional[date],
    actual_cum_mh: float,
) -> dict[str, Any]:
    """누적 mh window 비교 — 사용자 개념. plan 미등록 시 unknown.

    plan_mh_per_day  = plan_mh_sum / 공정_기간_일수
    expected_in_w    = window_days × plan_mh_per_day
    mh_gap           = expected - actual           (양수 = 부족)
    delay_days       = mh_gap / plan_mh_per_day

    schedule_state:
      plan 없음            → "unknown"
      today < plan_start   → "early"
      plan_start ≤ today ≤ plan_finish → "on_schedule"
      today > plan_finish  → "post_due"
    """
    if plan is None or plan.get("plan_start") is None or plan.get("plan_finish") is None:
        return {
            "plan_mh_per_day": None,
            "schedule_state": "unknown",
            "window_start": None,
            "window_days": 0,
            "expected_in_window_mh": None,
            "actual_in_window_mh": actual_cum_mh,
            "mh_gap": None,
            "delay_days": None,
        }

    plan_start = plan["plan_start"]
    plan_finish = plan["plan_finish"]
    plan_mh_sum = plan["plan_mh_sum"]

    total_days = (plan_finish - plan_start).days + 1
    plan_mh_per_day = plan_mh_sum / total_days if total_days > 0 else 0.0

    if today < plan_start:
        schedule_state = "early"
    elif today > plan_finish:
        schedule_state = "post_due"
    else:
        schedule_state = "on_schedule"

    ws = actual_window_start or today
    window_days = max(1, (today - ws).days + 1)
    expected_in_w = window_days * plan_mh_per_day
    mh_gap = expected_in_w - actual_cum_mh
    delay_days = mh_gap / plan_mh_per_day if plan_mh_per_day > 0 else 0.0

    return {
        "plan_mh_per_day": plan_mh_per_day,
        "schedule_state": schedule_state,
        "window_start": ws,
        "window_days": window_days,
        "expected_in_window_mh": expected_in_w,
        "actual_in_window_mh": actual_cum_mh,
        "mh_gap": mh_gap,
        "delay_days": delay_days,
    }
```

- [ ] **Step 9: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_aggregate.py -v 2>&1 | tail -15
```
Expected: 8 passed (3 aggregate + 5 compute_delay).

→ Iron Law 3 요소 보고.

- [ ] **Step 10: PGClient.fetch_plan_for_group 추가 + integration test (실 PG)**

Read `pipeline/db.py` 의 PGClient class 패턴 (assert_pipeline_run_exists 직후 위치 적당).

Append method to `pipeline/db.py` PGClient class:

```python
    async def fetch_plan_for_group(
        self, company: str, l6_main: str
    ) -> Optional[dict[str, Any]]:
        """activity_master 의 (company, l6_main) candidate Σ. 미등록 시 None.

        Spec §5.2 — 2 SQL 분리로 jsonb_object_agg duplicate key 회피.
        """
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            qty_rows = await conn.fetch(
                """
                SELECT unit, SUM(plan_total_qty) AS qty
                FROM activity_master
                WHERE company = $1 AND l6_main = $2 AND unit IS NOT NULL
                GROUP BY unit
                """,
                company, l6_main,
            )
            if not qty_rows:
                return None
            summary = await conn.fetchrow(
                """
                SELECT
                    SUM(plan_mh_rev2) AS plan_mh_sum,
                    MIN(plan_start)   AS plan_start,
                    MAX(plan_finish)  AS plan_finish
                FROM activity_master
                WHERE company = $1 AND l6_main = $2
                """,
                company, l6_main,
            )
        return {
            "plan_total_qty_by_unit": {r["unit"]: float(r["qty"] or 0) for r in qty_rows},
            "plan_mh_sum": float(summary["plan_mh_sum"] or 0),
            "plan_start": summary["plan_start"],
            "plan_finish": summary["plan_finish"],
        }
```

Append to `pipeline/tests/test_db.py` (기존 test_db.py 가 있는 경우):

```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_fetch_plan_for_group_real(pg):
    """실 activity_master 1059 row 안 (세보엠이씨, 일반공조설비공사) 1건 정합."""
    result = await pg.fetch_plan_for_group("세보엠이씨", "일반공조설비공사")
    assert result is not None
    assert result["plan_mh_sum"] > 0
    assert result["plan_start"] is not None
    assert result["plan_finish"] is not None
    assert isinstance(result["plan_total_qty_by_unit"], dict)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_fetch_plan_for_group_unknown_bp(pg):
    """미등록 BP사 → None."""
    result = await pg.fetch_plan_for_group("__nonexistent_company__", "__no__")
    assert result is None
```

- [ ] **Step 11: Verify**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/test_db.py -v -k "fetch_plan_for_group" 2>&1 | tail -10
```
Expected: 2 passed (실 PG 호출).

→ Iron Law 3 요소 보고. 실 PG 의 (세보엠이씨, 일반공조설비공사) 가 매핑되어 있어야 하므로 byte-level 결과 확인.

- [ ] **Step 12: fetch_chroma_actual + tests**

Append to `pipeline/agents/forecaster/aggregate.py`:

```python
def fetch_chroma_actual(
    coll,
    company: str,
    l6_main: str,
    today: date,
    today_assigned_workers: float,
) -> tuple[Optional[date], float]:
    """Chroma daily_activities 에서 (company, l6_main) date 별 unique workers 추출.

    Spec §5.4 정합 — reviewer #5 정정:
    return: (actual_window_start, actual_cum_mh)
      Chroma 에 과거 row 없음 (오늘만)  → (None, today_workers × 8)
      Chroma 에 과거 row 있음           → (min(Chroma date), Σ unique date workers × 8h)
    """
    result = coll.get(
        where={"$and": [{"company": company}, {"l6_main": l6_main}]},
        include=["metadatas"],
    )
    date_to_workers: dict[str, float] = {}
    for m in result.get("metadatas") or []:
        d = m["date"]
        if d == today.isoformat():
            continue   # 오늘 자기자신 제외
        date_to_workers[d] = float(m["assigned_workers"])

    # Chroma 에 과거 row 가 하나도 없음 → 오늘만 카운트, window_start = None
    if not date_to_workers:
        return None, today_assigned_workers * 8

    # 오늘 강제 추가 후 누적
    date_to_workers[today.isoformat()] = today_assigned_workers
    window_start = date.fromisoformat(min(date_to_workers.keys()))
    actual_cum_mh = sum(w * 8 for w in date_to_workers.values())
    return window_start, actual_cum_mh
```

Append unit tests with mock coll:

```python
class _MockColl:
    def __init__(self, metadatas: list[dict]):
        self._metadatas = metadatas

    def get(self, where, include):
        return {"metadatas": self._metadatas}


def test_fetch_chroma_actual_with_data():
    coll = _MockColl([
        {"date": "2025-09-20", "assigned_workers": 100},
        {"date": "2025-09-21", "assigned_workers": 100},
        {"date": "2025-09-22", "assigned_workers": 100},
    ])
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual
    ws, mh = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws == date(2025, 9, 20)
    assert mh == pytest.approx(4 * 100 * 8)   # 4일 (20,21,22,25)


def test_fetch_chroma_actual_empty():
    coll = _MockColl([])
    from pipeline.agents.forecaster.aggregate import fetch_chroma_actual
    ws, mh = fetch_chroma_actual(coll, "X", "Y", date(2025, 9, 25), 100)
    assert ws is None
    assert mh == pytest.approx(800)   # 100 × 8 = 오늘 1일만


def test_compute_delay_zero_total_days():
    """plan_start == plan_finish (1일 공정) 의 division by zero 방어 (reviewer #11)."""
    plan = {
        "plan_start": date(2025, 9, 25),
        "plan_finish": date(2025, 9, 25),
        "plan_mh_sum": 100,
        "plan_total_qty_by_unit": {"m": 10.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 9, 25),
        actual_window_start=date(2025, 9, 25),
        actual_cum_mh=80.0,
    )
    # total_days=1, plan_mh_per_day=100, window=1, expected=100, actual=80, gap=20, delay=0.2
    assert result["plan_mh_per_day"] == pytest.approx(100.0)
    assert result["delay_days"] == pytest.approx(0.2, abs=0.05)


def test_compute_delay_plan_mh_zero():
    """plan_mh_sum=0 → division by zero 방어 (delay_days=0)."""
    plan = {
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 12, 31),
        "plan_mh_sum": 0,
        "plan_total_qty_by_unit": {"m": 10.0},
    }
    result = compute_delay(
        plan=plan,
        today=date(2025, 6, 1),
        actual_window_start=date(2025, 1, 1),
        actual_cum_mh=0.0,
    )
    assert result["delay_days"] == pytest.approx(0.0)
```

- [ ] **Step 13: Verify all aggregate.py tests**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_aggregate.py -v 2>&1 | tail -15
```
Expected: 10 passed (3 + 5 + 2).

→ Iron Law 3 요소 보고.

- [ ] **Step 14: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/__init__.py \
        pipeline/agents/forecaster/aggregate.py \
        pipeline/tests/forecaster/__init__.py \
        pipeline/tests/forecaster/test_aggregate.py \
        pipeline/db.py \
        pipeline/tests/test_db.py
git commit -m "$(cat <<'EOF'
forecaster: aggregate.py — 4 함수 (집계 + delay 계산 + PG 조회)

- aggregate_today_by_unit (Σ by unit)
- fetch_plan_for_group (PGClient 신규, 2 SQL 분리 — spec C-2 정정)
- compute_delay (사용자 개념: 누적 mh window 비교, schedule_state 4 enum)
- fetch_chroma_actual (Chroma date 별 unique workers)

Tests: 10 unit + 2 integration (실 PG)

Spec: §5.1~5.4
EOF
)"
```

---

## 5. Task 2: classify.py — assessment + risk_level (TDD)

**Files:**
- Create: `pipeline/agents/forecaster/classify.py`
- Create: `pipeline/tests/forecaster/test_classify.py`

**Spec 참조:** §6 (분류 룰)

- [ ] **Step 1: failing tests 작성**

Create `pipeline/tests/forecaster/test_classify.py`:

```python
"""Forecaster classify.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §6
"""

from __future__ import annotations

import pytest

from pipeline.agents.forecaster.classify import (
    classify_assessment,
    classify_risk_level,
)


# ─── assessment: RAG 모드 ────────────────────────────────────────────────
def test_classify_assessment_rag_normal():
    """delta -10% (≥-15%) → 정상."""
    result = classify_assessment(rag_n=5, today_prod=0.9, rag_avg_prod=1.0,
                                  plan_total_qty_main=100, plan_mh_sum=1000)
    assert result == "정상"


def test_classify_assessment_rag_caution():
    """delta -20% (∈[-25%, -15%)) → 주의."""
    result = classify_assessment(rag_n=5, today_prod=0.8, rag_avg_prod=1.0,
                                  plan_total_qty_main=100, plan_mh_sum=1000)
    assert result == "주의"


def test_classify_assessment_rag_risk():
    """delta -30% (< -25%) → 이상."""
    result = classify_assessment(rag_n=5, today_prod=0.7, rag_avg_prod=1.0,
                                  plan_total_qty_main=100, plan_mh_sum=1000)
    assert result == "이상"


def test_classify_assessment_rag_boundary_normal():
    """delta = -15% 정확 → 정상 (≥-15%)."""
    result = classify_assessment(rag_n=5, today_prod=0.85, rag_avg_prod=1.0,
                                  plan_total_qty_main=100, plan_mh_sum=1000)
    assert result == "정상"


# ─── assessment: Plan fallback ───────────────────────────────────────────
def test_classify_assessment_plan_fallback_normal():
    """RAG=0, Plan productivity ratio 0.9 → 정상.

    plan_prod = 100 / (800 / 8) = 1.0 m/인-day
    today_prod = 0.9
    ratio = 0.9 / 1.0 = 0.9 ≥ 0.85 → 정상
    """
    result = classify_assessment(rag_n=0, today_prod=0.9, rag_avg_prod=0.0,
                                  plan_total_qty_main=100, plan_mh_sum=800)
    assert result == "정상"


def test_classify_assessment_plan_fallback_caution():
    """ratio 0.7 (∈[0.65, 0.85)) → 주의."""
    result = classify_assessment(rag_n=0, today_prod=0.7, rag_avg_prod=0.0,
                                  plan_total_qty_main=100, plan_mh_sum=800)
    assert result == "주의"


def test_classify_assessment_plan_fallback_risk():
    """ratio 0.5 (<0.65) → 이상."""
    result = classify_assessment(rag_n=0, today_prod=0.5, rag_avg_prod=0.0,
                                  plan_total_qty_main=100, plan_mh_sum=800)
    assert result == "이상"


def test_classify_assessment_cold_start():
    """RAG=0 + Plan 없음 → None."""
    result = classify_assessment(rag_n=0, today_prod=0.0, rag_avg_prod=0.0,
                                  plan_total_qty_main=None, plan_mh_sum=None)
    assert result is None


def test_classify_assessment_cold_start_zero_plan():
    """RAG=0 + Plan mh=0 → None."""
    result = classify_assessment(rag_n=0, today_prod=0.5, rag_avg_prod=0.0,
                                  plan_total_qty_main=100, plan_mh_sum=0)
    assert result is None


# ─── risk_level ──────────────────────────────────────────────────────────
def test_classify_risk_normal_on_track():
    """정상 + delay≤5 → 정상."""
    result = classify_risk_level("정상", None, 3.0, "on_schedule")
    assert result == "정상"


def test_classify_risk_normal_with_delay():
    """정상 + delay>5 → 주의 (누적 delay)."""
    result = classify_risk_level("정상", None, 10.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_caution_recoverable():
    """주의 + recovery≥0.7 + delay≤5 → 주의."""
    result = classify_risk_level("주의", 0.8, 3.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_caution_unrecoverable():
    """주의 + recovery<0.7 → 이상."""
    result = classify_risk_level("주의", 0.5, 3.0, "on_schedule")
    assert result == "이상"


def test_classify_risk_severe_ahead():
    """이상 + delay≤0 (ahead) → 주의 (회복 여유)."""
    result = classify_risk_level("이상", 0.7, -2.0, "on_schedule")
    assert result == "주의"


def test_classify_risk_severe_behind():
    """이상 + delay>0 → 이상."""
    result = classify_risk_level("이상", 0.7, 10.0, "on_schedule")
    assert result == "이상"


def test_classify_risk_post_due_forced():
    """post_due → 이상 강제 (assessment 무관)."""
    result = classify_risk_level("정상", None, 0.0, "post_due")
    assert result == "이상"


def test_classify_risk_unknown_falls_back_to_assessment():
    """schedule_state=unknown + delay None → assessment 그대로."""
    result = classify_risk_level("주의", 0.7, None, "unknown")
    assert result == "주의"


def test_classify_risk_cold_start_none():
    """assessment=None → None."""
    result = classify_risk_level(None, None, 0.0, "unknown")
    assert result is None
```

- [ ] **Step 2: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_classify.py -v 2>&1 | tail -25
```
Expected: 18 errors (ModuleNotFoundError).

- [ ] **Step 3: classify.py 구현 — 4 함수 모두 명시 (reviewer #7)**

Create `pipeline/agents/forecaster/classify.py`:

```python
"""Forecaster classify — assessment + risk_level 분류 룰. 순수 함수.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §6

4 함수:
  1. classify_assessment_rag       — RAG 모드 (delta ±15%/±25%)
  2. classify_assessment_plan      — Plan fallback (productivity ratio 0.85/0.65)
  3. classify_assessment           — routing (RAG 우선 + Plan fallback + cold start None)
  4. classify_risk_level           — hybrid (assessment + recovery + delay + state)
"""

from __future__ import annotations

from typing import Optional


def classify_assessment_rag(today_prod: float, rag_avg_prod: float) -> str:
    """RAG 모드 — productivity delta 임계 ±15% / ±25%."""
    if rag_avg_prod == 0:
        return "정상"
    delta = (today_prod - rag_avg_prod) / rag_avg_prod
    if delta >= -0.15:
        return "정상"
    if delta >= -0.25:
        return "주의"
    return "이상"


def classify_assessment_plan(
    today_prod: float,
    plan_total_qty_main: float,
    plan_mh_sum: float,
) -> str:
    """Plan fallback — 단위당 productivity ratio 임계 0.85 / 0.65.

    plan_prod_proxy = plan_total_qty[main_unit] / (plan_mh_sum / 8)
                     # 그 공종이 정상 진행 시 1 인-day 가 만드는 unit 수
    ratio           = today_prod / plan_prod_proxy
    """
    if plan_mh_sum <= 0 or plan_total_qty_main <= 0:
        return "정상"
    plan_prod_proxy = plan_total_qty_main / (plan_mh_sum / 8)
    if plan_prod_proxy == 0:
        return "정상"
    ratio = today_prod / plan_prod_proxy
    if ratio >= 0.85:
        return "정상"
    if ratio >= 0.65:
        return "주의"
    return "이상"


def classify_assessment(
    rag_n: int,
    today_prod: float,
    rag_avg_prod: float,
    plan_total_qty_main: Optional[float],
    plan_mh_sum: Optional[float],
) -> Optional[str]:
    """RAG 우선 + Plan fallback + cold start.

    Spec §0.1 ②: rag_n >= 3 → RAG / else if plan 가용 → Plan / else None.
    """
    if rag_n >= 3:
        return classify_assessment_rag(today_prod, rag_avg_prod)
    if plan_mh_sum and plan_mh_sum > 0 and plan_total_qty_main:
        return classify_assessment_plan(today_prod, plan_total_qty_main, plan_mh_sum)
    return None


def classify_risk_level(
    assessment: Optional[str],
    recovery_likelihood: Optional[float],
    delay_days: Optional[float],
    schedule_state: str,
) -> Optional[str]:
    """hybrid 룰 — assessment + recovery + delay + state.

    임계 5일·0.7 = 가정값 (회귀 후 조정).
    """
    if assessment is None:
        return None
    if schedule_state == "post_due":
        return "이상"
    if schedule_state == "unknown" or delay_days is None:
        return assessment

    if assessment == "정상":
        if delay_days > 5:
            return "주의"
        return "정상"
    if assessment == "주의":
        if (recovery_likelihood is not None
                and recovery_likelihood >= 0.7
                and delay_days <= 5):
            return "주의"
        return "이상"
    if delay_days <= 0:
        return "주의"
    return "이상"
```

- [ ] **Step 4: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_classify.py -v 2>&1 | tail -25
```
Expected: 18 passed.

→ Iron Law 3 요소 보고.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/classify.py \
        pipeline/tests/forecaster/test_classify.py
git commit -m "$(cat <<'EOF'
forecaster: classify.py — assessment + risk_level 룰

- classify_assessment_rag (delta ±15%/±25%)
- classify_assessment_plan (productivity ratio 0.85/0.65, spec M-2)
- classify_assessment (RAG 우선 + Plan fallback + cold start None)
- classify_risk_level (hybrid: post_due 강제 + delay 임계 5일 + recovery 0.7)

Tests: 18 unit (RAG/Plan/cold start + risk 8 case)

Spec: §6
EOF
)"
```

---

## 6. Task 3: rerank.py — normalize + rerank (TDD)

**Files:**
- Create: `pipeline/agents/forecaster/rerank.py`
- Create: `pipeline/tests/forecaster/test_rerank.py`

**Spec 참조:** §7 (atomizer schema 정규화 — B-1 정정)

- [ ] **Step 1: failing tests 작성**

Create `pipeline/tests/forecaster/test_rerank.py`:

```python
"""Forecaster rerank.py 단위 테스트 — atomizer schema 정규화 + rerank.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §7
"""

from __future__ import annotations

import pytest

from pipeline.agents.forecaster.rerank import (
    _normalize_chroma_metadata,
    rerank_cases,
)


# ─── _normalize_chroma_metadata ──────────────────────────────────────────
def test_normalize_productivity_derive():
    """today_qty / assigned_workers → productivity."""
    m = {"today_qty": 80, "assigned_workers": 400, "conditions": "맑음"}
    result = _normalize_chroma_metadata(m)
    assert result["productivity"] == pytest.approx(0.2)


def test_normalize_zero_workers_safe():
    """workers=0 → productivity=0 (ZeroDivisionError 회피)."""
    m = {"today_qty": 80, "assigned_workers": 0, "conditions": ""}
    result = _normalize_chroma_metadata(m)
    assert result["productivity"] == 0.0


def test_normalize_conditions_string_to_list():
    """atomizer 의 ",".join() string → split list."""
    m = {"today_qty": 80, "assigned_workers": 100, "conditions": "맑음,우천"}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == ["맑음", "우천"]


def test_normalize_conditions_empty_string():
    """conditions="" → []."""
    m = {"today_qty": 80, "assigned_workers": 100, "conditions": ""}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == []


def test_normalize_conditions_missing_key():
    """conditions key 없음 → []."""
    m = {"today_qty": 80, "assigned_workers": 100}
    result = _normalize_chroma_metadata(m)
    assert result["conditions"] == []


# ─── rerank_cases ────────────────────────────────────────────────────────
def test_rerank_empty():
    """cases=[] → []."""
    assert rerank_cases([]) == []


def test_rerank_user_corrected_priority():
    """worker_source=user_corrected → distance ×0.7 (최우선)."""
    cases = [
        {"distance": 0.3, "metadata": {"today_qty": 1, "assigned_workers": 1,
                                        "conditions": "", "worker_source": "mh_prorated",
                                        "mapping_conf": 0.9}},
        {"distance": 0.3, "metadata": {"today_qty": 1, "assigned_workers": 1,
                                        "conditions": "", "worker_source": "user_corrected",
                                        "mapping_conf": 0.9}},
    ]
    result = rerank_cases(cases)
    # user_corrected 가 먼저 (×0.7 → 0.21 vs 0.3)
    assert result[0]["metadata"]["worker_source"] == "user_corrected"
    assert result[0]["rerank_score"] == pytest.approx(0.21)


def test_rerank_low_mapping_conf_demoted():
    """mapping_conf<0.7 → distance ×1.5 (우선순위 ↓)."""
    cases = [
        {"distance": 0.2, "metadata": {"today_qty": 1, "assigned_workers": 1,
                                        "conditions": "", "worker_source": "mh_prorated",
                                        "mapping_conf": 0.4}},   # 낮은 신뢰
        {"distance": 0.25, "metadata": {"today_qty": 1, "assigned_workers": 1,
                                         "conditions": "", "worker_source": "mh_prorated",
                                         "mapping_conf": 0.9}},  # 높은 신뢰
    ]
    result = rerank_cases(cases)
    # 0.4 conf → 0.2 × 1.5 = 0.3 / 0.9 conf → 0.25 그대로
    # 0.25 < 0.3 → 높은 신뢰가 먼저
    assert result[0]["metadata"]["mapping_conf"] == 0.9
    assert result[0]["rerank_score"] == pytest.approx(0.25)


def test_rerank_combined_user_corrected_low_conf():
    """user_corrected (×0.7) + low conf (×1.5) → ×1.05."""
    cases = [
        {"distance": 0.2, "metadata": {"today_qty": 1, "assigned_workers": 1,
                                        "conditions": "", "worker_source": "user_corrected",
                                        "mapping_conf": 0.4}},
    ]
    result = rerank_cases(cases)
    assert result[0]["rerank_score"] == pytest.approx(0.2 * 0.7 * 1.5)


def test_rerank_normalized_conditions_in_result():
    """rerank 결과의 metadata 가 정규화 적용된 상태인지."""
    cases = [
        {"distance": 0.1, "metadata": {"today_qty": 80, "assigned_workers": 400,
                                        "conditions": "맑음,우천", "worker_source": "mh_prorated",
                                        "mapping_conf": 0.9}},
    ]
    result = rerank_cases(cases)
    assert result[0]["metadata"]["productivity"] == pytest.approx(0.2)
    assert result[0]["metadata"]["conditions"] == ["맑음", "우천"]
```

- [ ] **Step 2: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_rerank.py -v 2>&1 | tail -15
```
Expected: 10 errors.

- [ ] **Step 3: rerank.py 구현**

Create `pipeline/agents/forecaster/rerank.py`:

```python
"""Forecaster rerank — Atomizer metadata 정규화 + 가중치 rerank. 순수 함수.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §7

Atomizer 적재 schema (pipeline/agents/atomizer.py:45~59):
  date, run_id, company, l5_disc, l6_main, wa, unit,
  today_qty, assigned_workers, worker_source, mapping_conf,
  conditions: ",".join(list) → STRING (콤마 join)

Forecaster 추가 derive:
  productivity = today_qty / assigned_workers
  conditions   = string.split(",")  (empty → [])
"""

from __future__ import annotations

from typing import Any


def _normalize_chroma_metadata(m: dict) -> dict:
    """atomizer schema → Forecaster schema 변환. spec B-1 정정."""
    today_qty = float(m.get("today_qty", 0))
    workers = float(m.get("assigned_workers", 0))
    productivity = today_qty / workers if workers > 0 else 0.0

    conditions_raw = m.get("conditions", "")
    conditions = conditions_raw.split(",") if conditions_raw else []

    return {**m, "productivity": productivity, "conditions": conditions}


def rerank_cases(cases: list[dict]) -> list[dict]:
    """Chroma query 결과 → 정규화 + rerank.

    가중치:
      worker_source = "user_corrected" → distance × 0.7
      mapping_conf < 0.7              → distance × 1.5

    정렬 후 전체 반환. caller (agent.py) 가 [:rag_top_k] 자름.
    """
    out: list[dict[str, Any]] = []
    for c in cases:
        meta = _normalize_chroma_metadata(c["metadata"])
        score = c["distance"]
        if meta.get("worker_source") == "user_corrected":
            score *= 0.7
        if meta.get("mapping_conf", 1.0) < 0.7:
            score *= 1.5
        out.append({**c, "metadata": meta, "rerank_score": score})
    return sorted(out, key=lambda x: x["rerank_score"])
```

- [ ] **Step 4: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_rerank.py -v 2>&1 | tail -15
```
Expected: 10 passed.

→ Iron Law 3 요소 보고.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/rerank.py \
        pipeline/tests/forecaster/test_rerank.py
git commit -m "$(cat <<'EOF'
forecaster: rerank.py — atomizer schema 정규화 + 가중치 rerank

- _normalize_chroma_metadata (productivity derive, conditions string→list)
  → spec B-1 정정: atomizer 박는 schema 와 Forecaster 가정 schema 일치
- rerank_cases (worker_source ×0.7, mapping_conf<0.7 ×1.5)

Tests: 10 unit (정규화 5 + rerank 5)

Spec: §7
EOF
)"
```

---

## 7. Task 4: prompt.py — system + few-shot 3 + builder (TDD)

**Files:**
- Create: `pipeline/agents/forecaster/prompt.py`
- Create: `pipeline/tests/forecaster/test_prompt.py`

**Spec 참조:** §8 (LLM prompt 디자인)

- [ ] **Step 1: failing tests 작성**

Create `pipeline/tests/forecaster/test_prompt.py`:

```python
"""Forecaster prompt.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §8
"""

from __future__ import annotations

import json

import pytest

from pipeline.agents.forecaster.prompt import (
    SYSTEM_PROMPT,
    FEW_SHOT_MESSAGES,
    build_llm_user_input,
)


def test_system_prompt_has_3step_structure():
    """system prompt 가 3 단계 reasoning 구조 명시."""
    assert "3 단계" in SYSTEM_PROMPT or "3단계" in SYSTEM_PROMPT
    assert "조건" in SYSTEM_PROMPT and "RAG" in SYSTEM_PROMPT


def test_system_prompt_has_json_schema():
    """system prompt 가 JSON 출력 schema 명시."""
    assert "reasoning" in SYSTEM_PROMPT
    assert "recovery_likelihood" in SYSTEM_PROMPT


def test_few_shot_messages_3_pairs():
    """3 few-shot = 3 (user, assistant) = 6 messages."""
    assert len(FEW_SHOT_MESSAGES) == 6


def test_few_shot_alternating_roles():
    """user, assistant 교차."""
    expected_roles = ["user", "assistant", "user", "assistant", "user", "assistant"]
    actual = [m["role"] for m in FEW_SHOT_MESSAGES]
    assert actual == expected_roles


def test_few_shot_normal_recovery_null():
    """정상 케이스 assistant output 의 recovery_likelihood = null."""
    normal_output = json.loads(FEW_SHOT_MESSAGES[1]["content"])
    assert normal_output["recovery_likelihood"] is None


def test_few_shot_caution_recovery_not_null():
    """주의 케이스 assistant output 의 recovery_likelihood ≠ null."""
    caution_output = json.loads(FEW_SHOT_MESSAGES[3]["content"])
    assert caution_output["recovery_likelihood"] is not None


def test_few_shot_severe_recovery_not_null():
    """이상 케이스 assistant output 의 recovery_likelihood ≠ null."""
    severe_output = json.loads(FEW_SHOT_MESSAGES[5]["content"])
    assert severe_output["recovery_likelihood"] is not None


def test_build_llm_user_input_structure():
    """build_llm_user_input 출력 구조 검증."""
    today = {
        "company": "세보엠이씨", "l6_main": "일반공조설비공사",
        "today_qty_by_unit": {"m": 80, "ea": 12},
        "today_assigned_workers": 401.4, "today_productivity": 0.1993,
        "conditions": ["맑음"], "work_content": "AHU 덕트 연결",
    }
    similar = [
        {"document": "AHU 덕트", "metadata": {"date": "2025-09-20", "productivity": 0.2,
                                              "conditions": ["맑음"]}},
    ]
    plan = {"plan_total_qty_by_unit": {"m": 6800}, "plan_mh_sum": 708154}

    result = build_llm_user_input(today, similar, plan, "정상")

    assert result["today"]["company"] == "세보엠이씨"
    assert result["today"]["conditions"] == ["맑음"]
    assert len(result["similar_cases"]) == 1
    assert result["similar_cases"][0]["date"] == "2025-09-20"
    assert result["plan"]["plan_mh_sum"] == 708154
    assert result["assessment_by_code"] == "정상"


def test_build_llm_user_input_no_plan():
    """plan=None → plan dict 빈 값."""
    today = {
        "company": "X", "l6_main": "Y",
        "today_qty_by_unit": {"m": 1}, "today_assigned_workers": 1,
        "today_productivity": 1.0, "conditions": [], "work_content": "",
    }
    result = build_llm_user_input(today, [], None, "정상")
    assert result["plan"]["plan_mh_sum"] == 0
```

- [ ] **Step 2: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_prompt.py -v 2>&1 | tail -15
```
Expected: 9 errors.

- [ ] **Step 3: prompt.py 구현**

Create `pipeline/agents/forecaster/prompt.py`:

```python
"""Forecaster prompt — system + few-shot 3 + user input builder.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §8
"""

from __future__ import annotations

import json
from typing import Any, Optional


SYSTEM_PROMPT = """당신은 건설 현장 생산성 분석 전문가다.
주어진 오늘 실적·과거 유사 사례·자동 분류 결과를 바탕으로 reasoning 1~2 문장을 작성한다.

reasoning 의 3 단계 구조 (필수):
  1. 오늘 조건 명시 — 날씨, conditions, work_content 요지
  2. RAG 비교 — 유사 N건 평균 대비 X% (assessment 결정 근거)
  3. 원인 추론 — work_content 텍스트 분석. 정상 시 생략 가능.

출력 schema (JSON):
  {
    "reasoning": str,
    "recovery_likelihood": float (0.0~1.0) | null
  }

규칙:
  - reasoning 은 입력의 assessment 와 정합되어야 한다 (분류 결과를 뒤집지 말 것)
  - assessment = "정상" → recovery_likelihood = null
  - recovery_likelihood = RAG 유사 사례에서 다음날 회복한 비율 추정
"""


_FEW_SHOT_1_INPUT = {
    "today": {"company": "Y건설", "l6_main": "거푸집공사",
              "today_productivity": 22.9, "conditions": ["우천", "병행작업"],
              "work_content": "FAB 2층 벽체 거푸집"},
    "similar_cases": [{"date": "2025-09-10", "productivity": 21.3,
                       "conditions": ["우천"], "work_content": "벽체 거푸집"}],
    "plan": {"plan_total_qty_by_unit": {"m2": 12000}, "plan_mh_sum": 84000},
    "assessment_by_code": "정상",
}
_FEW_SHOT_1_OUTPUT = {
    # reviewer #1 정정: 3 단계 구조 명시 (조건 / RAG / 원인). 정상이라 원인 추론 = "정상 범위" 짧게.
    "reasoning": "오늘 우천 + 병행작업 있음. 유사 우천일 평균 21.3 m2/인 대비 +8%. 정상 변동 범위, 별도 원인 없음.",
    "recovery_likelihood": None,
}

_FEW_SHOT_2_INPUT = {
    "today": {"company": "세보엠이씨", "l6_main": "일반공조설비공사",
              "today_productivity": 0.14, "conditions": ["맑음"],
              "work_content": "AHU 덕트 + 자재 미입고 일부"},
    "similar_cases": [{"date": "2025-09-20", "productivity": 0.18,
                       "conditions": ["맑음"], "work_content": "AHU 덕트"}],
    "plan": {"plan_total_qty_by_unit": {"m": 6800}, "plan_mh_sum": 708154},
    "assessment_by_code": "주의",
}
_FEW_SHOT_2_OUTPUT = {
    # reviewer #1 정정: 3 단계 명시 (조건 → RAG → 원인). reviewer #15: "5건" 은 rag_top_k=5 가정.
    "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 0.18 m/인 대비 -22%. work_content 에 '자재 미입고' 기재 — 단기 회복 가능성.",
    "recovery_likelihood": 0.7,
}

_FEW_SHOT_3_INPUT = {
    "today": {"company": "남웅건설", "l6_main": "철근콘크리트공사",
              "today_productivity": 1.8, "conditions": ["맑음"],
              "work_content": "타워크레인 대기로 오전 작업 지연"},
    "similar_cases": [{"date": "2025-09-15", "productivity": 2.6,
                       "conditions": ["맑음"], "work_content": "철근 조립"}],
    "plan": {"plan_total_qty_by_unit": {"ton": 500}, "plan_mh_sum": 50000},
    "assessment_by_code": "이상",
}
_FEW_SHOT_3_OUTPUT = {
    # reviewer #1: 3 단계 명시. reviewer #15: rag_top_k 변경 시 "5건" 부분도 함께 조정.
    "reasoning": "맑음, 병행작업 없음. 유사 5건 평균 2.6 ton/인 대비 -31%. work_content 에 '타워크레인 대기' 기재 — 장비 스케줄 충돌 가능성.",
    "recovery_likelihood": 0.8,
}


# reviewer #8: ensure_ascii=False 는 한글 (한자 X) 출력을 위함.
# 사용자 전역 CLAUDE.md "No 한자" 룰은 한자 (物·量·個 등) 금지이며 한글은 허용.
FEW_SHOT_MESSAGES: list[dict[str, str]] = [
    {"role": "user", "content": json.dumps(_FEW_SHOT_1_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_1_OUTPUT, ensure_ascii=False)},
    {"role": "user", "content": json.dumps(_FEW_SHOT_2_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_2_OUTPUT, ensure_ascii=False)},
    {"role": "user", "content": json.dumps(_FEW_SHOT_3_INPUT, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps(_FEW_SHOT_3_OUTPUT, ensure_ascii=False)},
]


def build_llm_user_input(
    today: dict,
    similar_cases: list[dict],
    plan: Optional[dict],
    assessment: str,
) -> dict[str, Any]:
    """system + 3 few-shot 은 const. 본 함수는 user message JSON 만 생성."""
    return {
        "today": {
            "company": today["company"],
            "l6_main": today["l6_main"],
            "today_qty_by_unit": today["today_qty_by_unit"],
            "today_assigned_workers": today["today_assigned_workers"],
            "today_productivity": round(today["today_productivity"], 4),
            "conditions": today["conditions"],
            "work_content": today["work_content"],
        },
        "similar_cases": [
            {
                "date": c["metadata"]["date"],
                "productivity": round(c["metadata"]["productivity"], 4),
                "conditions": c["metadata"]["conditions"],
                "work_content": c["document"][:80],
            }
            for c in similar_cases
        ],
        "plan": {
            "plan_total_qty_by_unit": plan["plan_total_qty_by_unit"] if plan else {},
            "plan_mh_sum": plan["plan_mh_sum"] if plan else 0,
        },
        "assessment_by_code": assessment,
    }
```

- [ ] **Step 4: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_prompt.py -v 2>&1 | tail -15
```
Expected: 9 passed.

→ Iron Law 3 요소 보고.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/prompt.py \
        pipeline/tests/forecaster/test_prompt.py
git commit -m "$(cat <<'EOF'
forecaster: prompt.py — system + few-shot 3 + user builder

- SYSTEM_PROMPT (3 단계 reasoning 구조 + JSON schema)
- FEW_SHOT_MESSAGES (정상/주의/이상 1건씩, 6 messages)
  - 정상: PM 원안 v2 §2 거푸집 인용 (recovery_likelihood=null)
  - 주의: 9/25 세보 일반공조 수제작 (recovery=0.7)
  - 이상: PM 원안 v2 §4 철근 인용 (recovery=0.8)
- build_llm_user_input (user message JSON 생성)

Tests: 9 unit

Spec: §8
EOF
)"
```

---

## 8. Task 5: synthetic.py — Phase 1 dummy 30일 (TDD + 실 Azure)

**Files:**
- Create: `pipeline/agents/forecaster/synthetic.py`
- Create: `pipeline/tests/forecaster/test_synthetic.py`

**Spec 참조:** §9 (synthetic history Phase 1)

- [ ] **Step 0: atomizer schema dependency 검증 (reviewer #4)**

Run (`atomizer.py:45-59` 의 `_build_metadata` 가 박는 키 확인):
```bash
sed -n '45,59p' "/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/atomizer.py"
```
Expected output 의 키 (synthetic.py 도 동일 schema 박아야):
```
"date", "run_id", "company", "l5_disc", "l6_main", "wa", "unit",
"today_qty", "assigned_workers", "worker_source", "mapping_conf",
"conditions": ",".join(...)
```

→ Iron Law 3 요소 보고. synthetic.py 의 `_main_cli()` 의 `metas` dict 가 위 키 + 같은 type (`conditions` = string) 인지 Step 5 에서 byte-level 비교.

- [ ] **Step 1: failing tests 작성 (단위)**

Create `pipeline/tests/forecaster/test_synthetic.py`:

```python
"""Forecaster synthetic.py 단위 테스트.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §9
"""

from __future__ import annotations

import random
from datetime import date

import pytest

from pipeline.agents.forecaster.synthetic import generate_synthetic_day


@pytest.fixture
def base_row():
    return {
        "company": "세보엠이씨",
        "l6_main": "일반공조설비공사",
        "l5_disc": "설비",
        "wa": "AC",
        "unit": "m",
        "today_qty": 80.0,
        "assigned_workers": 401.4,
        "work_content": "AHU 덕트 연결",
        "mapping_conf": 0.85,
    }


def test_generate_clear_normal(base_row):
    """맑음 + 정상 → ±5% 변동."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=1,
                                     weather="맑음", incident="정상")
    assert "맑음" in result["conditions"]
    assert "정상" not in result["conditions"]
    assert 76 <= result["today_qty"] <= 84   # ±5%


def test_generate_rainy_decrease(base_row):
    """우천 → -15~25%."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=2,
                                     weather="우천", incident="정상")
    assert "우천" in result["conditions"]
    # 80 × (1 - 0.15~0.25) × (1 ± 0.05) ≈ 57~68
    assert 55 <= result["today_qty"] <= 70


def test_generate_equipment_wait(base_row):
    """장비대기 → -20~35%."""
    random.seed(42)
    result = generate_synthetic_day(base_row, day_offset=3,
                                     weather="맑음", incident="장비대기")
    assert "장비대기" in result["conditions"]
    # 80 × (1 - 0.20~0.35) × (1 ± 0.05) ≈ 49~65
    assert 47 <= result["today_qty"] <= 66


def test_generate_seed_reproducible(base_row):
    """같은 seed → 동일 출력."""
    random.seed(42)
    r1 = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    random.seed(42)
    r2 = generate_synthetic_day(base_row, day_offset=1, weather="맑음", incident="정상")
    assert r1["today_qty"] == r2["today_qty"]


def test_generate_metadata_atomizer_schema_match(base_row):
    """생성된 row 가 atomizer _build_metadata 와 호환 schema."""
    random.seed(42)
    row = generate_synthetic_day(base_row, day_offset=1,
                                  weather="맑음", incident="정상")
    # atomizer 가 박는 키 모두 포함되어야
    required_keys = {"date", "company", "l5_disc", "l6_main", "wa", "unit",
                     "today_qty", "assigned_workers", "worker_source",
                     "mapping_conf", "conditions", "work_content"}
    assert required_keys.issubset(row.keys())
    # conditions 는 list (atomizer 가 ",".join 하기 전 상태)
    assert isinstance(row["conditions"], list)


def test_generate_date_offset(base_row):
    """day_offset=N → date 가 reference - N 일."""
    row = generate_synthetic_day(base_row, day_offset=5,
                                  weather="맑음", incident="정상",
                                  reference_date=date(2025, 9, 25))
    assert row["date"] == "2025-09-20"
```

- [ ] **Step 2: Verify failing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_synthetic.py -v 2>&1 | tail -15
```
Expected: 6 errors.

- [ ] **Step 3: synthetic.py 구현**

Create `pipeline/agents/forecaster/synthetic.py`:

```python
"""Forecaster synthetic — Phase 1 더미 30일 generator.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §9

PM 원안 v2 §3-B 변동 패턴:
  weather="우천"      → today_qty × (1 - random[0.15, 0.25])
  incident="장비대기"  → today_qty × (1 - random[0.20, 0.35])
  incident="자재미입고" → today_qty × (1 - random[0.10, 0.20])
  기본 변동           → × (1 + random[-0.05, 0.05])

Chroma 적재 시 atomizer._build_metadata() 와 동일 schema 사용 (spec B-1).
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Optional


def generate_synthetic_day(
    base_row: dict,
    day_offset: int,
    weather: str,
    incident: str,
    reference_date: Optional[date] = None,
) -> dict:
    """1 row variation 생성 — atomizer schema 호환.

    base_row 는 9/25 매핑 결과 1 row.
    day_offset 은 reference_date 로부터 backward (1 = 어제).
    """
    if reference_date is None:
        reference_date = date(2025, 9, 25)

    delta = 0.0
    if weather == "우천":
        delta -= random.uniform(0.15, 0.25)
    if incident == "장비대기":
        delta -= random.uniform(0.20, 0.35)
    elif incident == "자재미입고":
        delta -= random.uniform(0.10, 0.20)
    delta += random.uniform(-0.05, 0.05)

    today_qty = base_row["today_qty"] * (1 + delta)
    conditions = [weather] + ([incident] if incident != "정상" else [])
    target_date = reference_date - timedelta(days=day_offset)

    return {
        "date": target_date.isoformat(),
        "company": base_row["company"],
        "l5_disc": base_row["l5_disc"],
        "l6_main": base_row["l6_main"],
        "wa": base_row["wa"],
        "unit": base_row["unit"],
        "today_qty": round(today_qty, 1),
        "assigned_workers": base_row["assigned_workers"],
        "worker_source": "synthetic",
        "mapping_conf": base_row.get("mapping_conf", 0.85),
        "conditions": conditions,
        "work_content": base_row["work_content"],
    }
```

- [ ] **Step 4: Verify passing**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_synthetic.py -v 2>&1 | tail -15
```
Expected: 6 passed.

→ Iron Law 3 요소 보고.

- [ ] **Step 5: CLI entry 추가 (실 Chroma 적재) — 30일 loop 명시 (reviewer #10)**

CLI 의 30일 loop 는 `for d in range(1, args.days + 1):` (아래 코드 line 참조). 본 loop 가 reviewer #10 가 "missing" 으로 본 부분 — 실제로는 `_main_cli()` 안에 위치.

Append to `pipeline/agents/forecaster/synthetic.py`:

```python
async def _main_cli() -> None:
    """CLI entry — uv run python -m pipeline.agents.forecaster.synthetic.

    9/25 매핑 결과 (~30 unique (company, l6_main)) × 30일 = ~900 Chroma row 적재.
    atomizer 와 동일 _build_metadata 사용.
    """
    import argparse
    import asyncio
    import os
    from openai import AzureOpenAI
    from pipeline.chroma_client import ChromaClient
    from pipeline.db import PGClient

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-date", default="2025-09-25")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    ref = date.fromisoformat(args.reference_date)

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        # 9/25 매핑 결과 = activity_master 의 unique (company, l6_main) per BP/공종
        rows = await pg._pool.fetch(
            """
            SELECT DISTINCT ON (company, l6_main)
                company, l6_main, l5_disc, wa, unit, plan_total_qty
            FROM activity_master
            WHERE company IS NOT NULL AND l6_main IS NOT NULL AND unit IS NOT NULL
            """
        )
    finally:
        await pg.close()

    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    coll = chroma.get_or_create_daily_activities()

    weathers = ["맑음"] * 7 + ["우천"] * 2 + ["흐림"]   # 70/20/10
    incidents = ["정상"] * 8 + ["장비대기"] + ["자재미입고"]   # 80/10/10

    docs: list[str] = []
    metas: list[dict] = []
    ids: list[str] = []
    import hashlib

    for r in rows:
        base_row = {
            "company": r["company"],
            "l6_main": r["l6_main"],
            "l5_disc": r["l5_disc"] or "",
            "wa": r["wa"] or "",
            "unit": r["unit"],
            "today_qty": float(r["plan_total_qty"] or 100) / max(args.days, 1),
            "assigned_workers": 50.0,   # PoC 평균 가정. Phase 2 실 데이터로 교체.
            "work_content": f"{r['l6_main']} 작업",
            "mapping_conf": 0.85,
        }
        for d in range(1, args.days + 1):
            w = random.choice(weathers)
            i = random.choice(incidents)
            row = generate_synthetic_day(base_row, day_offset=d,
                                          weather=w, incident=i,
                                          reference_date=ref)
            doc_id_raw = f"synthetic|{row['date']}|{row['company']}|{row['l6_main']}|{row['work_content']}"
            doc_id = hashlib.sha256(doc_id_raw.encode("utf-8")).hexdigest()[:16]
            ids.append(doc_id)
            docs.append(row["work_content"])
            metas.append({
                "date": row["date"], "run_id": "synthetic",
                "company": row["company"], "l5_disc": row["l5_disc"],
                "l6_main": row["l6_main"], "wa": row["wa"],
                "unit": row["unit"], "today_qty": float(row["today_qty"]),
                "assigned_workers": float(row["assigned_workers"]),
                "worker_source": row["worker_source"],
                "mapping_conf": float(row["mapping_conf"]),
                "conditions": ",".join(row["conditions"]),   # atomizer 와 동일 string
            })

    # dedup ids (within-call)
    seen: dict[str, int] = {}
    for idx, doc_id in enumerate(ids):
        seen[doc_id] = idx
    final_ids = list(seen.keys())
    final_docs = [docs[seen[i]] for i in final_ids]
    final_metas = [metas[seen[i]] for i in final_ids]

    # embedding batch
    embeddings: list[list[float]] = []
    batch = 16
    for i in range(0, len(final_docs), batch):
        chunk = final_docs[i : i + batch]
        resp = azure.embeddings.create(
            model=os.environ["EMBEDDING_MODEL"], input=chunk,
        )
        embeddings.extend([d.embedding for d in resp.data])

    coll.upsert(ids=final_ids, embeddings=embeddings,
                documents=final_docs, metadatas=final_metas)

    print(f"OK upserted {len(final_ids)} rows to Chroma daily_activities.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main_cli())
```

- [ ] **Step 6: CLI 실행 (실 Azure + 실 Chroma)**

**전제**: `.env` 가 로드되어 있어야 함 (`AZURE_OPENAI_*`, `CHROMA_*`, `POSTGRES_URL`, `EMBEDDING_MODEL`). 실행 전 venv activate 또는 `uv run`.

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  python -m pipeline.agents.forecaster.synthetic --days 30 --seed 42 2>&1 | tail -5
```
Expected: `OK upserted ~900 rows to Chroma daily_activities.` (정확한 수는 activity_master unique (company, l6_main) 수 × 30).

→ Iron Law 3 요소 보고. Chroma row 수 byte-level 확인.

- [ ] **Step 7: Chroma 적재 검증**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
import os
c = ChromaClient(host=os.environ['CHROMA_HOST'],
                 port=int(os.environ.get('CHROMA_PORT','8000')),
                 ssl=os.environ.get('CHROMA_SSL','false').lower()=='true')
coll = c.get_or_create_daily_activities()
print('count:', coll.count())
sample = coll.get(limit=2, include=['metadatas','documents'])
print('sample metadata:', sample['metadatas'][0] if sample['metadatas'] else 'EMPTY')
"
```
Expected: `count: >=900` + 첫 row metadata 가 atomizer 와 동일 schema (`conditions` string, `productivity` 없음).

- [ ] **Step 8: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/synthetic.py \
        pipeline/tests/forecaster/test_synthetic.py
git commit -m "$(cat <<'EOF'
forecaster: synthetic.py — Phase 1 더미 30일 generator + CLI

- generate_synthetic_day (PM 원안 v2 §3-B 변동 패턴)
  - 우천 -15~25%, 장비대기 -20~35%, 자재미입고 -10~20%
  - atomizer _build_metadata schema 호환 (spec B-1)
- CLI entry: uv run python -m pipeline.agents.forecaster.synthetic
  - 9/25 매핑 unique (company, l6_main) × 30일 = ~900 Chroma row
  - atomizer 와 동일 conditions string + ids dedup
  - Azure text-embedding-3-small 1536d

Tests: 6 unit
Run: python -m ...synthetic --days 30 --seed 42 → OK upserted N rows

Spec: §9
EOF
)"
```

---

## 9. Task 6: agent.py — forecast entry + PGClient.insert_forecast (TDD)

**Files:**
- Create: `pipeline/agents/forecaster/agent.py`
- Modify: `pipeline/db.py` (`insert_forecast` 메서드)
- Modify: `pipeline/agents/forecaster/__init__.py` (export)

**Spec 참조:** §5.6, §10 (agent.py 본체)

- [ ] **Step 1: PGClient.insert_forecast 추가**

Append method to `pipeline/db.py` PGClient class:

```python
    async def insert_forecast(self, row: dict) -> None:
        """forecasts 테이블 INSERT 1 row.

        Spec §5.6 — 25 컬럼 (id/created_at auto). row dict 키 = 컬럼명.
        """
        import json as _json
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO forecasts (
                    run_id, company, l6_main,
                    today_qty_by_unit, today_assigned_workers, today_productivity,
                    plan_total_qty_by_unit, plan_mh_sum, plan_start, plan_finish, plan_mh_per_day,
                    schedule_state, window_start, window_days,
                    expected_in_window_mh, actual_in_window_mh, mh_gap, delay_days,
                    rag_n_similar, similar_cases,
                    assessment, reasoning, recovery_likelihood,
                    expected_completion, risk_level
                ) VALUES (
                    $1, $2, $3,
                    $4::jsonb, $5, $6,
                    $7::jsonb, $8, $9, $10, $11,
                    $12, $13, $14,
                    $15, $16, $17, $18,
                    $19, $20::jsonb,
                    $21, $22, $23,
                    $24, $25
                )
                """,
                row["run_id"], row["company"], row["l6_main"],
                _json.dumps(row["today_qty_by_unit"]) if row.get("today_qty_by_unit") else None,
                row.get("today_assigned_workers"), row.get("today_productivity"),
                _json.dumps(row["plan_total_qty_by_unit"]) if row.get("plan_total_qty_by_unit") else None,
                row.get("plan_mh_sum"), row.get("plan_start"), row.get("plan_finish"),
                row.get("plan_mh_per_day"),
                row.get("schedule_state"), row.get("window_start"), row.get("window_days"),
                row.get("expected_in_window_mh"), row.get("actual_in_window_mh"),
                row.get("mh_gap"), row.get("delay_days"),
                row.get("rag_n_similar"),
                _json.dumps(row["similar_cases"], ensure_ascii=False) if row.get("similar_cases") else None,
                row.get("assessment"), row.get("reasoning"),
                row.get("recovery_likelihood"),
                row.get("expected_completion"), row.get("risk_level"),
            )
```

- [ ] **Step 2: agent.py 구현**

Create `pipeline/agents/forecaster/agent.py`:

```python
"""Forecaster agent — LangGraph node + main async forecast() entry.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity

from .aggregate import (
    aggregate_today_by_unit,
    compute_delay,
    fetch_chroma_actual,
)
from .classify import classify_assessment, classify_risk_level
from .prompt import (
    SYSTEM_PROMPT,
    FEW_SHOT_MESSAGES,
    build_llm_user_input,
)
from .rerank import rerank_cases


@dataclass
class ForecasterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    azure_timeout: float = 60.0
    azure_max_retries: int = 3
    rag_n_candidates: int = 10
    rag_top_k: int = 5
    rag_window_days: int = 30
    # temperature 박지 않음 — spec C-1 정정 (gpt-5 family 미지원)


def _format_chroma_result(rag_result: dict) -> list[dict]:
    """Chroma query 결과 → rerank 입력 format."""
    if not rag_result.get("ids") or not rag_result["ids"][0]:
        return []
    return [
        {"document": doc, "distance": dist, "metadata": meta}
        for doc, dist, meta in zip(
            rag_result["documents"][0],
            rag_result["distances"][0],
            rag_result["metadatas"][0],
        )
    ]


async def _forecast_one_group(
    company: str,
    l6_main: str,
    activities: list[Activity],
    run_id: uuid.UUID,
    today: date,
    pg: PGClient,
    coll,
    azure: AzureOpenAI,
    cfg: ForecasterConfig,
) -> dict[str, Any]:
    """1 (company, l6_main) group 처리. Spec §1 ① ~ ⑧."""

    # ① 집계
    today_qty_by_unit = aggregate_today_by_unit(activities)
    today_assigned_workers = activities[0]["assigned_workers"]
    main_unit = max(today_qty_by_unit, key=today_qty_by_unit.get) if today_qty_by_unit else None
    today_productivity = (
        today_qty_by_unit[main_unit] / today_assigned_workers
        if main_unit and today_assigned_workers > 0 else 0.0
    )
    work_content = " / ".join(set(a["work_content"] for a in activities))[:200]
    conditions_set = sorted(set(c for a in activities for c in a["conditions"]))

    # ② Plan
    plan = await pg.fetch_plan_for_group(company, l6_main)

    # ③ RAG 검색 + 정규화 + rerank
    embed_resp = azure.embeddings.create(model=cfg.embedding_model, input=[work_content])
    today_embed = embed_resp.data[0].embedding
    where_filter = {
        "$and": [
            {"company": company},
            {"l6_main": l6_main},
            {"date": {
                "$gte": (today - timedelta(days=cfg.rag_window_days)).isoformat(),
                "$lt": today.isoformat(),
            }},
        ]
    }
    rag_result = coll.query(
        query_embeddings=[today_embed],
        where=where_filter,
        n_results=cfg.rag_n_candidates,
    )
    similar_cases_raw = _format_chroma_result(rag_result)
    similar_cases = rerank_cases(similar_cases_raw)[: cfg.rag_top_k]

    # ④ assessment
    rag_n = len(similar_cases)
    rag_avg_prod = (
        sum(c["metadata"]["productivity"] for c in similar_cases) / rag_n
        if rag_n > 0 else 0.0
    )
    plan_main_qty = (
        plan["plan_total_qty_by_unit"].get(main_unit)
        if plan and main_unit else None
    )
    assessment = classify_assessment(
        rag_n=rag_n,
        today_prod=today_productivity,
        rag_avg_prod=rag_avg_prod,
        plan_total_qty_main=plan_main_qty,
        plan_mh_sum=plan["plan_mh_sum"] if plan else None,
    )

    # ⑤ compute_delay
    actual_window_start, actual_cum_mh = fetch_chroma_actual(
        coll, company, l6_main, today, today_assigned_workers,
    )
    delay_info = compute_delay(plan, today, actual_window_start, actual_cum_mh)

    # ⑥ LLM
    if assessment is None:
        reasoning = "데이터 부족 (RAG 0건, Plan 미등록) — 판단 보류"
        recovery_likelihood = None
    else:
        today_data = {
            "company": company, "l6_main": l6_main,
            "today_qty_by_unit": today_qty_by_unit,
            "today_assigned_workers": today_assigned_workers,
            "today_productivity": today_productivity,
            "conditions": conditions_set,
            "work_content": work_content,
        }
        llm_input = build_llm_user_input(today_data, similar_cases, plan, assessment)
        response = azure.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *FEW_SHOT_MESSAGES,
                {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        llm_out = json.loads(response.choices[0].message.content)
        reasoning = llm_out.get("reasoning", "")
        recovery_likelihood = llm_out.get("recovery_likelihood")

    # ⑦ risk_level
    risk_level = classify_risk_level(
        assessment, recovery_likelihood,
        delay_info["delay_days"], delay_info["schedule_state"],
    )

    # ⑧ row
    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6_main,
        "today_qty_by_unit": today_qty_by_unit,
        "today_assigned_workers": today_assigned_workers,
        "today_productivity": today_productivity,
        "plan_total_qty_by_unit": plan["plan_total_qty_by_unit"] if plan else None,
        "plan_mh_sum": plan["plan_mh_sum"] if plan else None,
        "plan_start": plan["plan_start"] if plan else None,
        "plan_finish": plan["plan_finish"] if plan else None,
        "plan_mh_per_day": delay_info["plan_mh_per_day"],
        "schedule_state": delay_info["schedule_state"],
        "window_start": delay_info["window_start"],
        "window_days": delay_info["window_days"],
        "expected_in_window_mh": delay_info["expected_in_window_mh"],
        "actual_in_window_mh": delay_info["actual_in_window_mh"],
        "mh_gap": delay_info["mh_gap"],
        "delay_days": delay_info["delay_days"],
        "rag_n_similar": rag_n,
        "similar_cases": [
            {"date": c["metadata"]["date"],
             "productivity": round(c["metadata"]["productivity"], 4),
             "conditions": c["metadata"]["conditions"]}
            for c in similar_cases
        ],
        "assessment": assessment,
        "reasoning": reasoning,
        "recovery_likelihood": recovery_likelihood,
        "expected_completion": plan["plan_finish"] if plan else None,
        "risk_level": risk_level,
    }


async def forecast(
    mapped: list[Activity],
    run_id: uuid.UUID,
    today: date,
    cfg: ForecasterConfig,
) -> list[dict[str, Any]]:
    """Forecaster entry. (company, l6_main) group 별 1 row 생성 + PG INSERT."""
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

        groups: dict[tuple[str, str], list[Activity]] = {}
        for a in mapped:
            if a["l6_main"] is None:
                continue
            key = (a["company"], a["l6_main"])
            groups.setdefault(key, []).append(a)

        forecast_rows: list[dict[str, Any]] = []
        for (company, l6_main), activities in groups.items():
            row = await _forecast_one_group(
                company, l6_main, activities, run_id, today,
                pg, coll, azure, cfg,
            )
            await pg.insert_forecast(row)
            forecast_rows.append(row)

        return forecast_rows
    finally:
        await pg.close()
```

Update `pipeline/agents/forecaster/__init__.py`:

```python
"""CPIA Forecaster — (company, l6_main) grain RAG 진단."""

from __future__ import annotations

from .agent import ForecasterConfig, forecast

__all__ = ["ForecasterConfig", "forecast"]
```

- [ ] **Step 3: 빠른 import 검증**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/python3 -c "from pipeline.agents.forecaster import ForecasterConfig, forecast; print('OK', ForecasterConfig.__name__, forecast.__name__)"
```
Expected: `OK ForecasterConfig forecast`.

→ Iron Law 3 요소 보고.

- [ ] **Step 4: _format_chroma_result 단위 테스트 (reviewer #13)**

Append to `pipeline/tests/forecaster/test_rerank.py` (또는 별도 test_agent_helpers.py — 본 plan 은 rerank 와 함께 묶음):

```python
def test_format_chroma_result_empty():
    """rag_result 가 비어있을 때 [] 반환."""
    from pipeline.agents.forecaster.agent import _format_chroma_result
    result = _format_chroma_result({"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]})
    assert result == []


def test_format_chroma_result_normal():
    """ids/documents/distances/metadatas 의 zip 결과."""
    from pipeline.agents.forecaster.agent import _format_chroma_result
    rag = {
        "ids": [["a", "b"]],
        "documents": [["doc-a", "doc-b"]],
        "distances": [[0.1, 0.2]],
        "metadatas": [[{"k": "v1"}, {"k": "v2"}]],
    }
    result = _format_chroma_result(rag)
    assert len(result) == 2
    assert result[0] == {"document": "doc-a", "distance": 0.1, "metadata": {"k": "v1"}}
    assert result[1] == {"document": "doc-b", "distance": 0.2, "metadata": {"k": "v2"}}


def test_format_chroma_result_none_ids():
    """ids 가 None 일 때 [] 반환."""
    from pipeline.agents.forecaster.agent import _format_chroma_result
    result = _format_chroma_result({"ids": None, "documents": None, "distances": None, "metadatas": None})
    assert result == []
```

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  .venv/bin/pytest tests/forecaster/test_rerank.py -v -k "_format_chroma" 2>&1 | tail -10
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/agents/forecaster/agent.py \
        pipeline/agents/forecaster/__init__.py \
        pipeline/db.py
git commit -m "$(cat <<'EOF'
forecaster: agent.py + PGClient.insert_forecast — Forecaster entry

- ForecasterConfig dataclass
- _forecast_one_group: 8 단계 처리 (집계 → Plan → RAG → assessment → delay → LLM → risk → row)
- forecast(): (company, l6_main) group 별 1 row + PG INSERT
- PGClient.insert_forecast (25 컬럼)
- fail-fast: assert_pipeline_run_exists (atomizer 패턴)
- temperature 박지 않음 (spec C-1)
- Chroma where filter date 단일 dict (spec M-1)

Spec: §5.6, §10
EOF
)"
```

---

## 10. Task 7: integration tests (실 PG + 실 Chroma + 실 Azure)

**Files:**
- Create: `pipeline/tests/forecaster/test_forecaster_integration.py`

**Spec 참조:** §12.2 (integration tests)

**전제:** Task 5 의 synthetic 적재 완료 + Task 0~6 통과.

- [ ] **Step 1: integration tests 작성**

Create `pipeline/tests/forecaster/test_forecaster_integration.py`:

```python
"""Forecaster integration tests — 실 PG + 실 Chroma + 실 Azure.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §12.2
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.db import PGClient


@pytest.fixture
def cfg() -> ForecasterConfig:
    keys = [
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL", "EMBEDDING_MODEL", "POSTGRES_URL", "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    return ForecasterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


@pytest_asyncio.fixture
async def run_row(cfg):
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        try:
            yield run_id
        finally:
            await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


def _make_activity(company: str, l6: str, unit: str, qty: float, workers: float) -> dict:
    return {
        "wbs_activity_id": None, "l7_sub": None, "l7_5_activity": None, "sub_work_area": None,
        "l5_disc": "설비", "l6_main": l6, "wa": "AC",
        "mapping_conf": 0.85, "mapping_source": "auto_bp_single", "requires_review": False,
        "trade": "공조", "company": company, "unit": unit,
        "today_qty": qty, "work_content": f"{l6} 작업", "conditions": ["맑음"],
        "assigned_workers": workers, "worker_source": "mh_prorated",
        "plan_total_qty": None, "plan_mh": None,
    }


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_sebo_with_synthetic(cfg, run_row):
    """synthetic 30일 적재 후 세보 일반공조 1 row 생성. assessment != None."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    assert len(result) == 1
    row = result[0]
    assert row["company"] == "세보엠이씨"
    assert row["l6_main"] == "일반공조설비공사"
    # assessment 가 결정됐는지 (None 이면 synthetic 미적재 또는 BP사 미등록)
    assert row["assessment"] in {"정상", "주의", "이상"}
    assert row["schedule_state"] in {"early", "on_schedule", "post_due", "unknown"}
    assert row["risk_level"] in {"정상", "주의", "이상"}


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_cold_start_unknown_bp(cfg, run_row):
    """미등록 BP사 → assessment=None, schedule_state=unknown."""
    mapped = [_make_activity("__nonexistent_company__", "__no__", "m", 80, 100)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    assert len(result) == 1
    row = result[0]
    assert row["assessment"] is None
    assert row["schedule_state"] == "unknown"
    assert row["delay_days"] is None
    assert row["risk_level"] is None


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_pg_insert_persisted(cfg, run_row):
    """forecasts 테이블에 row 가 실제 적재됐는지 검증."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    await forecast(mapped, run_row, date(2025, 9, 25), cfg)

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            "SELECT company, l6_main, assessment, risk_level, schedule_state, "
            "delay_days, today_productivity, plan_mh_per_day "
            "FROM forecasts WHERE run_id = $1",
            run_row,
        )
    finally:
        await pg.close()
    assert len(rows) == 1
    assert rows[0]["company"] == "세보엠이씨"
    assert rows[0]["schedule_state"] is not None


@pytest.mark.slow
@pytest.mark.asyncio
@pytest.mark.timeout(300)
async def test_forecaster_chroma_metadata_normalization(cfg, run_row):
    """Atomizer schema 의 conditions string → list 정규화 통과."""
    mapped = [_make_activity("세보엠이씨", "일반공조설비공사", "m", 80, 401.4)]
    result = await forecast(mapped, run_row, date(2025, 9, 25), cfg)
    if result[0]["rag_n_similar"] >= 1:
        # similar_cases 의 conditions 가 list (정규화 후) 인지
        first_case = result[0]["similar_cases"][0]
        assert isinstance(first_case["conditions"], list)
```

- [ ] **Step 2: integration tests 실행**

**전제**: Task 5 의 synthetic 30일 적재 완료.

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  pytest tests/forecaster/test_forecaster_integration.py -v 2>&1 | tail -20
```
Expected: 4 passed (실 Azure 호출 포함 ~ 60~120 초).

→ Iron Law 3 요소 보고. row 의 assessment / risk_level / schedule_state byte-level 출력.

- [ ] **Step 3: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/tests/forecaster/test_forecaster_integration.py
git commit -m "$(cat <<'EOF'
forecaster: integration tests — 실 PG + 실 Chroma + 실 Azure

- test_forecaster_sebo_with_synthetic (synthetic 30일 후 정상 row)
- test_forecaster_cold_start_unknown_bp (미등록 BP → assessment=None)
- test_forecaster_pg_insert_persisted (forecasts 테이블 적재 검증)
- test_forecaster_chroma_metadata_normalization (conditions string→list)

Spec: §12.2
EOF
)"
```

---

## 11. Task 8: E2E (mapper + atomizer + forecaster)

**Files:**
- Create: `pipeline/tests/forecaster/test_forecaster_e2e.py`

**Spec 참조:** §12.3 (E2E)

- [ ] **Step 1: E2E test 작성**

Create `pipeline/tests/forecaster/test_forecaster_e2e.py`:

```python
"""Forecaster E2E — mapper + atomizer + forecaster 통과.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §12.3
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.agents.parser import parse_daily_report
from pipeline.db import PGClient


@pytest_asyncio.fixture
async def setup(monkeypatch):
    keys = [
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL", "EMBEDDING_MODEL", "POSTGRES_URL", "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    common = dict(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    mapper_cfg = MapperConfig(llm_model=os.environ["LLM_MODEL"], **common)
    atomizer_cfg = AtomizerConfig(**common)
    forecaster_cfg = ForecasterConfig(llm_model=os.environ["LLM_MODEL"], **common)

    pg = PGClient(common["postgres_url"])
    await pg.connect()
    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
    try:
        yield mapper_cfg, atomizer_cfg, forecaster_cfg, run_id, pg
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()


@pytest.mark.slow
@pytest.mark.golden
@pytest.mark.asyncio
@pytest.mark.timeout(900)
async def test_forecaster_e2e_namwong_47(setup):
    """E2E: 9/25 남웅 47 row → mapper → atomizer → forecaster.

    예상: 1 forecast row (남웅건설, 철근콘크리트공사). assessment ∈ {정상, 주의, 이상}.
    """
    mapper_cfg, atomizer_cfg, forecaster_cfg, run_id, pg = setup

    xlsx = "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    parsed = parse_daily_report(xlsx)
    namwong = [a for a in parsed["activities"]
                if a["company"] == "남웅건설" and "비계" not in a["work_content"]]
    assert len(namwong) == 47
    parsed_filt = {**parsed, "activities": namwong}

    # mapper
    mapped: list = []
    for a in namwong:
        r = await map_activity(a, parsed_report=parsed_filt, cfg=mapper_cfg)
        mapped.append(r)
    mapped = await _prorate_mh(mapped, parsed_filt, pg)

    # atomizer
    await atomize(mapped, parsed_filt, run_id, atomizer_cfg)

    # forecaster
    today = date(2025, 9, 25)
    forecasts = await forecast(mapped, run_id, today, forecaster_cfg)

    # 검증
    assert len(forecasts) == 1   # 남웅 = 1 (company, l6_main)
    row = forecasts[0]
    assert row["company"] == "남웅건설"
    assert row["l6_main"] == "철근콘크리트공사"
    assert row["assessment"] in {"정상", "주의", "이상", None}
    assert row["risk_level"] in {"정상", "주의", "이상", None}
    assert row["today_assigned_workers"] == pytest.approx(88.0)
```

- [ ] **Step 2: E2E 실행**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  pytest tests/forecaster/test_forecaster_e2e.py -v 2>&1 | tail -20
```
Expected: 1 passed (~ 3~10분, Azure embedding + LLM 호출 다수).

→ Iron Law 3 요소 보고. forecast row 의 assessment / risk_level / delay_days byte-level.

- [ ] **Step 3: 전체 회귀**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  pytest 2>&1 | tail -10
```
Expected: 모든 테스트 passed. 신규 추가된 Forecaster 단위 + integration + E2E 가 통과.

→ Iron Law 3 요소 보고.

- [ ] **Step 4: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/tests/forecaster/test_forecaster_e2e.py
git commit -m "$(cat <<'EOF'
forecaster: E2E 회귀 — mapper + atomizer + forecaster (남웅 47 row)

Run: pytest → 전체 passed (X new + Y existing).

Spec: §12.3
EOF
)"
```

---

## 12. Task 9: graph.py 통합 (forecaster_node 추가)

**Files:**
- Modify: `pipeline/graph.py` (GraphConfig + forecaster_node + edge)
- Modify: `pipeline/tests/test_graph_e2e.py` (회귀 — atomized_ids + forecast 검증)

**Spec 참조:** §10 (LangGraph node wrapper)

- [ ] **Step 1: GraphConfig + forecaster_node 추가**

Modify `pipeline/graph.py`:

```python
"""LangGraph StateGraph — Phase 1 mapper + atomizer + forecaster.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §10
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from langgraph.graph import END, START, StateGraph

from pipeline.agents.atomizer import AtomizerConfig, atomize
from pipeline.agents.forecaster import ForecasterConfig, forecast
from pipeline.agents.mapper import MapperConfig, _prorate_mh, map_activity
from pipeline.db import PGClient
from pipeline.state import Activity, CPIAState, ParsedDailyReport


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig


async def mapper_node(state: CPIAState, cfg: GraphConfig) -> dict:
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
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}


async def forecaster_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = date.fromisoformat(state["date"])
    forecasts = await forecast(state["mapped"], run_id, today, cfg.forecaster)
    return {"forecast": forecasts, "current_node": "forecaster"}


def build_graph(cfg: GraphConfig):
    """Phase 1 StateGraph — mapper → atomizer → forecaster → END."""
    graph = StateGraph(CPIAState)

    async def _mapper(state: CPIAState) -> dict:
        return await mapper_node(state, cfg)

    async def _atomizer(state: CPIAState) -> dict:
        return await atomizer_node(state, cfg)

    async def _forecaster(state: CPIAState) -> dict:
        return await forecaster_node(state, cfg)

    graph.add_node("mapper", _mapper)
    graph.add_node("atomizer", _atomizer)
    graph.add_node("forecaster", _forecaster)
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", END)
    return graph.compile()
```

- [ ] **Step 2: test_graph_e2e.py 회귀 — forecast 검증 추가 (reviewer #14 정정 — step body 명시)**

Read `pipeline/tests/test_graph_e2e.py` (현 47 row → atomized 11 검증). 정정 2곳:

**(a) cfg fixture 에 ForecasterConfig 추가** (기존 GraphConfig 생성자 호출 부분):

```python
# 기존:
return GraphConfig(
    mapper=MapperConfig(...),
    atomizer=AtomizerConfig(...),
)
# 정정 후:
return GraphConfig(
    mapper=MapperConfig(...),
    atomizer=AtomizerConfig(...),
    forecaster=ForecasterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=common_pg,
        chroma_host=common_chroma_host,
        chroma_port=common_chroma_port,
        chroma_ssl=common_chroma_ssl,
    ),
)
```

또한 file head 의 import 부분에 추가:
```python
from pipeline.agents.forecaster import ForecasterConfig
```

**(b) test_graph_e2e_namwong_47 assertion 보강** (마지막 부분에 추가):

```python
# 기존 assertion 끝부분 다음에 추가:
# Task 9 (forecaster_node) 후 forecast row 1건 생성 (남웅 = 1 (company, l6_main))
assert len(final["forecast"]) == 1, f"forecast 수: {len(final['forecast'])}"
forecast_row = final["forecast"][0]
assert forecast_row["company"] == "남웅건설"
assert forecast_row["l6_main"] == "철근콘크리트공사"
assert forecast_row["today_assigned_workers"] == pytest.approx(88.0)
# assessment 는 RAG 가용 여부에 따라 다르므로 enum 만 검증
assert forecast_row["assessment"] in {"정상", "주의", "이상", None}
assert forecast_row["risk_level"] in {"정상", "주의", "이상", None}
assert forecast_row["schedule_state"] in {"early", "on_schedule", "post_due", "unknown"}
```

- [ ] **Step 3: graph E2E 실행**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  pytest tests/test_graph_e2e.py -v 2>&1 | tail -15
```
Expected: 1 passed (mapper + atomizer + forecaster 전체 통과).

→ Iron Law 3 요소 보고.

- [ ] **Step 4: 전체 회귀 (Phase 1 종료 확인)**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && \
  source .venv/bin/activate && \
  set -a && source ../.env && set +a && \
  pytest --timeout=900 2>&1 | tail -15
```
Expected: 모든 테스트 passed. 회귀 0건.

→ Iron Law 3 요소 보고. 최종 passed/failed 수.

- [ ] **Step 5: Commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add pipeline/graph.py pipeline/tests/test_graph_e2e.py
git commit -m "$(cat <<'EOF'
graph: forecaster_node 통합 — Phase 1 mapper + atomizer + forecaster

- GraphConfig.forecaster 추가 (ForecasterConfig)
- forecaster_node: (company, l6_main) group 별 진단
- edge: START → mapper → atomizer → forecaster → END

E2E: 남웅 47 row → mapped 47 → atomized 11 → forecast 1.

Spec: §10
EOF
)"
```

---

## 13. 마감 통과 기준 (6/5 Phase 1)

| # | 기준 | 검증 방법 |
|---|---|---|
| 1 | 모든 단위 테스트 (test_aggregate / test_classify / test_rerank / test_prompt / test_synthetic) 통과 | `pytest tests/forecaster/test_*.py` |
| 2 | integration 4 케이스 통과 (synthetic / cold start / PG insert / metadata normalization) | `pytest tests/forecaster/test_forecaster_integration.py` |
| 3 | E2E 통과 (mapper + atomizer + forecaster) | `pytest tests/forecaster/test_forecaster_e2e.py` |
| 4 | graph.py E2E 통과 (forecaster_node 통합) | `pytest tests/test_graph_e2e.py` |
| 5 | 전체 회귀 0건 | `pytest --timeout=900` |
| 6 | synthetic 30일 Chroma 적재 완료 (count ≥ 900) | Step 5.7 검증 |
| 7 | forecasts 테이블 12 신규 컬럼 적용 | Task 0 Step 4 검증 |

**임계값 가정값 (회귀 후 조정 대상)**:
- Plan productivity ratio: 0.85 / 0.65
- RAG delta: ±15% / ±25%
- delay_days 임계: 5일
- recovery_likelihood 임계: 0.7

Phase 1 회귀 후 9/25 결과 분석 → 직관 정합 시까지 1~2 iteration 조정.

---

## 14. PR 작성

모든 Task 통과 후:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git push origin A_Track
gh pr create --base main --head A_Track \
  --title "forecaster: Phase 1 — (company, l6) RAG 진단 + delay_days + risk_level" \
  --body "$(cat <<'EOF'
## Summary

- 5 모듈 패키지 (`pipeline/agents/forecaster/`) — aggregate/classify/rerank/prompt/synthetic + agent.py entry
- (company, l6_main) grain RAG 진단 + Plan fallback + delay_days (누적 mh window) + risk_level hybrid
- atomizer schema 정규화 (`_normalize_chroma_metadata`)
- synthetic 30일 더미 (Phase 1 prerequisite, Chroma ~900 row)
- graph.py forecaster_node 통합

## Spec / Plan

- Spec: `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` (reviewer 16 정정 반영)
- Plan: `docs/superpowers/specs/2026-05-16-cpia-forecaster-plan.md`

## Test plan

- [x] Task 0 — postgres 마이그레이션 3곳 동기화
- [x] Task 1 — aggregate.py + fetch_plan_for_group (실 PG)
- [x] Task 2 — classify.py (assessment + risk_level)
- [x] Task 3 — rerank.py (atomizer schema 정규화)
- [x] Task 4 — prompt.py (system + few-shot 3)
- [x] Task 5 — synthetic.py + 30일 Chroma 적재
- [x] Task 6 — agent.py + PGClient.insert_forecast
- [x] Task 7 — integration 4 케이스 통과
- [x] Task 8 — E2E (mapper + atomizer + forecaster) 통과
- [x] Task 9 — graph.py 통합 + 전체 회귀 통과

## 다음 사이클

Optimizer spec → Reporter spec → graph.py 통합 (LangGraph fan-in + interrupt 2).
EOF
)"
```

---

## 15. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-16 | 초안 — Forecaster Phase 1 Task 0~9 TDD 분해. spec 의 8+3 결정 + spec reviewer 16 정정 (B-1 normalize / C-1 temperature 제거 / C-2 fetch_plan 2 SQL / M-1 date 단일 dict / M-2 productivity ratio / Coh-2 fetch_chroma_actual / Coh-3 JSONB 컬럼 / M-4 delay_days NUMERIC / Mi-4 insert_forecast SQL 등) 모두 반영. 사용자 전역 CLAUDE.md 하드룰 (Real code / TDD / Iron Law 3 요소 / No 한자) 명시. | A 트랙 |
| 2026-05-16 | plan reviewer (coherence) 16 발견 정정 (B 옵션 — 확실하게): <br>**Critical 2건**: ①(#1) Few-shot output 3 단계 명시 (조건/RAG/원인 분리, Task 4) — system prompt 강제와 정합. ②(#5) `fetch_chroma_actual` nil path 정정 (spec §5.4 와 일치: Chroma 과거 0 row → `return None, today_workers × 8`). <br>**Major 4건**: ③(#3) Task 0 Step 0 신규 — `.env` 8 키 + PG/Azure/Chroma smoke test. ④(#4) Task 5 Step 0 신규 — atomizer `_build_metadata` schema dependency 검증. ⑤(#6) Task 0 Step 0 에 Azure embedding/chat smoke test 포함. ⑥(#16) plan Task 0 vs spec §15.1 Task 0 명명 충돌 주의 (별개 항목, plan 번호 사용). <br>**Moderate 5건**: ⑦(#7) Task 2 Step 3 의 `classify.py` 코드 본문에 4 함수 모두 명시 (rag/plan/routing/risk). ⑧(#8) Task 4 의 `ensure_ascii=False` 가 한글 (한자 X) 출력 위함 주석. ⑨(#9) Task 0 Step 1 expected 가 baseline (마이그 전) 상태임을 명확화. ⑩(#10) Task 5 Step 5 의 30일 loop 위치 명시 (CLI entry `_main_cli()` 안 `for d in range(args.days+1)`). ⑪(#11) `test_compute_delay_zero_total_days` + `test_compute_delay_plan_mh_zero` 추가. <br>**Minor 5건**: ⑫(#12) test fixture `l5_disc` 추가 noted (`atomizer schema 정합` 코멘트). ⑬(#13) `_format_chroma_result` 단위 테스트 3건 (Task 6 Step 4 신규). ⑭(#14) Task 9 graph.py step body 코드 명시 (cfg fixture + assertion 보강). ⑮(#15) Few-shot "5건" 은 `rag_top_k=5` 기본 가정 주석. <br>**False positive 2건**: ⑯(#2) `fetch_plan_for_group` (PGClient async method, `await pg.fetch_plan_for_group(...)`) ≠ `fetch_chroma_actual` (sync aggregate 함수). reviewer 가 두 함수 혼동. plan 변경 X. (#10) 의 30일 loop 도 _main_cli() 에 이미 존재 — Step 5 안내문 추가로 명시화. | A 트랙 |
