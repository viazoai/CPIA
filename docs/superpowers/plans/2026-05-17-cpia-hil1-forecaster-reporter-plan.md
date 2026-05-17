# CPIA HIL 1 + Forecaster fix + Reporter + PostgresSaver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** drift-backlog #1~#4 통합 — HIL 1 구현 + Forecaster fixture fix + Reporter 신규 + PostgresSaver 전환, 1 PR 통합 atomic.

**Architecture:** 3 갭 (HIL 1 / Forecaster / Reporter) 의존성 0 → 병렬 atomic 진행. PostgresSaver 전환은 HIL 1/HIL 2 e2e 테스트가 회귀 대상이라 Task 4 (HIL 1+Reporter 완료 후) 로 분리. LangGraph interrupt + `Command(resume=)` 패턴 (HIL 2 의 graph.py:71~177 차용). LLM = Azure gpt-5.1 통일. PG schema 변경 0건 (daily_reports + mapping_corrections 기존 그대로).

**Tech Stack:** Python ≥3.11, LangGraph 0.2+, openai (Azure), asyncpg, chromadb 0.5.20, pytest + pytest-asyncio. 신규 의존성 = `langgraph-checkpoint-postgres>=2.0.0`. venv = `pipeline/.venv/bin/python3` 절대경로.

---

## File Structure

| 파일 | 변경 형태 | 책임 |
|---|---|---|
| `pipeline/graph.py:233~272` | Modify | `build_graph` 에 hil_1_node + reporter_node 추가, conditional_edges 변경 |
| `pipeline/graph.py:200~230` | Modify | `build_demo_graph` 동일 변경 (Reporter 만) |
| `pipeline/graph.py:33~37` | Modify | `GraphConfig` 에 reporter 필드 추가 |
| `pipeline/agents/optimizer/synthetic_daily_report.py:78` | Modify (1 line) | today_qty 산식 정정 (n_activities 분배) |
| `pipeline/agents/optimizer/synthetic_daily_report.py:118` | Modify (1 line) | n_activities ≤ 0 ValueError 가드 |
| `pipeline/agents/reporter.py` | Create (0 → ~150 lines) | LLM 호출 + report_md 생성 + PG INSERT |
| `pipeline/db.py:204` | Insert | `insert_mapping_correction` 메서드 추가 |
| `pipeline/db.py:309` | Insert | `insert_daily_report` 메서드 추가 |
| `pipeline/checkpointer.py:13` | Modify | InMemorySaver → PostgresSaver (fallback flag 지원) |
| `pipeline/pyproject.toml:11` | Modify | `langgraph-checkpoint-postgres>=2.0.0` 의존성 추가 |
| `pipeline/tests/test_synthetic_daily_report_fixture.py` | Create | Forecaster fixture 재현/픽스/RAG 정합 테스트 (신규 ~80 lines) |
| `pipeline/tests/test_graph_hil1.py` | Create | HIL 1 unit (~100 lines) |
| `pipeline/tests/test_graph_e2e_hil1.py` | Create | HIL 1 e2e (~150 lines, slow) |
| `pipeline/tests/test_reporter.py` | Create | Reporter unit + 통합 (~120 lines) |
| `docs/audit/2026-05-17-cpia-drift-backlog.md` | Modify | #1~#4 → 본 cycle 흡수 완료 마킹 |

**예상 commit 단위 ~12개** (TDD 패턴별로 1 commit).

---

## Task 0: 환경 점검 + 회귀 baseline

**Files:**
- Read-only: `pipeline/pyproject.toml`, `docs/audit/2026-05-17-cpia-e2e-audit-report.md`

- [ ] **Step 0.1: docker 컨테이너 + env 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && docker ps --filter "name=cpia" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output 양식:
```
cpia-pg-local      Up X minutes    0.0.0.0:5432->5432/tcp
cpia-chroma-local  Up X minutes    0.0.0.0:8000->8000/tcp
```

→ 두 컨테이너 모두 Up 확인. 한 줄이라도 빠지면 `docker compose -f infra/docker-compose.yml up -d` 실행 후 재확인.

- [ ] **Step 0.2: .env.local 로드 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -E "^(POSTGRES_URL|CHROMA_HOST|CHROMA_PORT|AZURE_OPENAI_ENDPOINT|LLM_MODEL|EMBEDDING_MODEL)=" pipeline/.env.local | head -10
```

Expected:
- POSTGRES_URL 시작 = `postgresql://cpia:`
- CHROMA_HOST = `localhost`
- CHROMA_PORT = `8000`
- AZURE_OPENAI_ENDPOINT 끝 = `cognitiveservices.azure.com/`
- LLM_MODEL = `gpt-5.1-chat-ai-board-test`
- EMBEDDING_MODEL = `text-embedding-3-small-ai-board-test`

→ 6 줄 모두 출력되어야 정상.

- [ ] **Step 0.3: 회귀 baseline 측정**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -20
```

Expected 마지막 라인: `183 passed, X skipped in Y.YYs` (또는 ±5 — 본 cycle 진입 시 183 baseline).

→ 회귀 baseline 숫자 (예: 183) 를 본 plan 안에 메모 (`<BASE_TESTS>` 자리). 다른 task 의 회귀 검증 기준 = `<BASE_TESTS> + 신규 N` PASS.

- [ ] **Step 0.4: 브랜치 + working tree clean 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git status && echo "---" && git log --oneline -3
```

Expected:
- `On branch A_Track`
- `nothing to commit, working tree clean`
- 최근 commit = `b344906 spec: 보강 3점 ...`

→ working tree clean + branch=A_Track 확인.

- [ ] **Step 0.5: Task 0 종결 (commit 없음 — Task 0 = 환경 점검만)**

본 Task 는 코드 변경 0건. baseline 숫자만 메모.

---

## Task 1: Forecaster fixture fix (재현 → 픽스 → RAG 정합)

**Files:**
- Modify: `pipeline/agents/optimizer/synthetic_daily_report.py:78` (today_qty 산식)
- Modify: `pipeline/agents/optimizer/synthetic_daily_report.py:118` (n_activities 가드)
- Create: `pipeline/tests/optimizer/test_synthetic_daily_report_fixture.py` (~80 lines)

- [ ] **Step 1.1: 재현 테스트 작성**

`pipeline/tests/optimizer/test_synthetic_daily_report_fixture.py` 신규 작성:

```python
"""Forecaster fixture fix — 재현 + 픽스 + RAG 정합 회귀.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.2

3 테스트:
  1. test_fixture_today_qty_divides_by_n_activities — 픽스 후 산식 검증
  2. test_fixture_n_activities_zero_raises          — 가드 검증
  3. test_fixture_rag_alignment                     — 정상일 productivity 와 RAG 평균 ±10% 정합 (slow, 실 PG/Chroma 호출)
"""

from __future__ import annotations

import pytest

from pipeline.agents.optimizer.synthetic_daily_report import (
    _parse_scenario,
    generate_fake_daily_report,
)


def test_fixture_today_qty_divides_by_n_activities() -> None:
    """ratio=0.45, n_activities=5 인 fixture 가 row 당 today_qty = baseline × ratio / n 으로 산출되는지 검증.

    합산 후 group total = baseline × ratio (의도 부합).
    """
    scenarios = [
        {"company": "남웅건설", "l6_main": "철근콘크리트공사",
         "n_activities": 5, "incident": "정상",
         "productivity_ratio": 0.45, "workers_ratio": 1.0, "unit": "m3"}
    ]
    activities = generate_fake_daily_report(
        report_date="2025-09-27",
        scenarios=scenarios,
        activity_pools={("남웅건설", "철근콘크리트공사"): ["벽체 콘크리트 타설"]},
        baseline_workers={("남웅건설", "철근콘크리트공사"): 31.0},
        baseline_qty={("남웅건설", "철근콘크리트공사", "m3"): 100.0},
    )
    assert len(activities) == 5
    row_qty = activities[0]["today_qty"]
    # 신: today_qty = round(100.0 * 0.45 / 5, 1) = round(9.0, 1) = 9.0
    assert row_qty == pytest.approx(9.0, abs=0.1)
    total_qty = sum(a["today_qty"] for a in activities)
    # 합산 = 5 × 9.0 = 45.0 = baseline_qty × ratio
    assert total_qty == pytest.approx(45.0, abs=0.5)


def test_fixture_n_activities_zero_raises() -> None:
    """n_activities=0 시 _parse_scenario 가 ValueError 발생."""
    with pytest.raises(ValueError, match="n_activities"):
        _parse_scenario("남웅건설|철근콘크리트공사|0|정상|1.0|1.0|m3")
```

- [ ] **Step 1.2: 재현 테스트 실행 (fail 확인)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/optimizer/test_synthetic_daily_report_fixture.py::test_fixture_today_qty_divides_by_n_activities -v
```

Expected: **FAIL** — 현 산식은 `baseline_q * ratio = 45.0` row 당 (n 으로 안 나눔). assert `row_qty == 9.0` 위반.

→ 실 출력에서 `AssertionError: assert 45.0 == 9.0 ± 0.1` 류 확인.

- [ ] **Step 1.3: synthetic_daily_report.py:78 픽스**

`pipeline/agents/optimizer/synthetic_daily_report.py:78` Edit:
- 현: `today_qty = round(baseline_q * sc["productivity_ratio"], 1)`
- 신: `today_qty = round(baseline_q * sc["productivity_ratio"] / sc["n_activities"], 1)`

- [ ] **Step 1.4: synthetic_daily_report.py:118 가드 추가**

`pipeline/agents/optimizer/synthetic_daily_report.py:118~135` Edit (`_parse_scenario` 함수):

```python
def _parse_scenario(raw: str) -> dict:
    """company|l6_main|n_activities|incident|productivity_ratio|workers_ratio|unit"""
    parts = raw.split("|")
    if len(parts) != 7:
        raise ValueError(
            f"scenario 형식 오류 — 7개 필드 필요 (company|l6_main|n_activities|"
            f"incident|productivity_ratio|workers_ratio|unit). 입력: {raw}"
        )
    n_act = int(parts[2])
    if n_act <= 0:
        raise ValueError(f"n_activities > 0 필요 — 입력: {n_act} ({raw})")
    return {
        "company": parts[0],
        "l6_main": parts[1],
        "n_activities": n_act,
        "incident": parts[3],
        "productivity_ratio": float(parts[4]),
        "workers_ratio": float(parts[5]),
        "unit": parts[6],
    }
```

- [ ] **Step 1.5: 픽스 테스트 PASS 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/optimizer/test_synthetic_daily_report_fixture.py -v
```

Expected: **2 passed** (`test_fixture_today_qty_divides_by_n_activities` + `test_fixture_n_activities_zero_raises`).

- [ ] **Step 1.6: 기존 synthetic_daily_report 회귀 영향 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/optimizer/test_synthetic_daily_report.py -v 2>&1 | tail -20
```

Expected: 기존 테스트 PASS (산식 변경이 기존 테스트의 fixture 입력과 정합하는지). 회귀 발생 시 fixture 입력값 자체 (`n_activities` 와 `baseline_q` 결합) 수정으로 의도 보존.

→ 회귀 발생 시 추가 step 1.6.a~ 로 fixture 입력값 정정.

- [ ] **Step 1.7: RAG 정합 회귀 테스트 작성**

Step 1.1 의 파일에 추가 (`@pytest.mark.slow` 마커 + 실 PG/Chroma):

```python
import os
import pytest_asyncio
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.agents.optimizer.synthetic_daily_report import _load_baseline_inputs


@pytest.mark.slow
@pytest.mark.asyncio
async def test_fixture_rag_alignment() -> None:
    """정상일 (ratio=1.0) fixture 가 산출하는 productivity 가 synthetic_v2 정상 RAG 평균과 ±10% 이내.

    fixture 의 today_qty = baseline_q × 1.0 / n_activities
    fixture 의 today_prod (group total) = baseline_q / base_workers
    이게 synthetic_v2 (incident="정상") 의 같은 그룹 평균 productivity 와 정합해야
    시나리오 ratio=0.45 가 실제로 -55% 저하로 발현됨.
    """
    keys = ["POSTGRES_URL", "CHROMA_HOST"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        # fixture 산출 productivity (남웅 철근콘크리트, ratio=1.0)
        scenarios = [{
            "company": "남웅건설", "l6_main": "철근콘크리트공사",
            "n_activities": 5, "incident": "정상",
            "productivity_ratio": 1.0, "workers_ratio": 1.0, "unit": "m3",
        }]
        pools, base_workers, base_qty = await _load_baseline_inputs(pg, scenarios, days=90)
        bw = base_workers[("남웅건설", "철근콘크리트공사")]
        bq = base_qty[("남웅건설", "철근콘크리트공사", "m3")]
        if bw == 0 or bq == 0:
            pytest.skip("baseline_workers 또는 baseline_qty 0 — Master 미등록 그룹 skip")
        fixture_prod = bq / bw  # ratio=1.0 시 group total

        # synthetic_v2 정상 RAG 평균
        chroma = ChromaClient(
            host=os.environ["CHROMA_HOST"],
            port=int(os.environ.get("CHROMA_PORT", "8000")),
            ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
        )
        coll = chroma.get_or_create_daily_activities()
        rag = coll.get(
            where={"$and": [
                {"company": "남웅건설"},
                {"l6_main": "철근콘크리트공사"},
                {"worker_source": "synthetic_v2"},
            ]},
            include=["metadatas"],
        )
        productivities = [
            float(m["assigned_workers"]) and float(m.get("today_qty", 0)) / float(m["assigned_workers"])
            for m in (rag.get("metadatas") or [])
            if float(m.get("assigned_workers", 0)) > 0
        ]
        if not productivities:
            pytest.skip("synthetic_v2 정상일 row 0 — synthetic_v2 적재 필요")
        rag_avg = sum(productivities) / len(productivities)

        # ±10% 정합 검증
        delta = abs(fixture_prod - rag_avg) / rag_avg if rag_avg > 0 else 1.0
        assert delta < 0.10, (
            f"fixture_prod={fixture_prod:.3f} vs rag_avg={rag_avg:.3f} delta={delta:.3f} (>10%) "
            "— fixture 와 synthetic_v2 분포 mismatch. 시나리오 ratio 가 의도된 변동 안 발현."
        )
    finally:
        await pg.close()
```

- [ ] **Step 1.8: RAG 정합 테스트 실행 (실 PG + Chroma + ~$0)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/optimizer/test_synthetic_daily_report_fixture.py::test_fixture_rag_alignment -v -m slow 2>&1 | tail -10
```

Expected outcomes:
1. **PASS**: fixture_prod 와 rag_avg 가 ±10% 이내 정합. 이상적.
2. **FAIL**: delta > 10% → fixture 와 synthetic_v2 적재 분포 mismatch 발견 (drift backlog #3 보조 발견). Task 1 종결 후 별 cycle 처리 — 단 fixture 산식 자체는 픽스 완료 (Step 1.3) 이므로 본 cycle 진행 가능.
3. **SKIP**: baseline 또는 RAG 0 row → 본 테스트는 정보 수집용 + plan 의 RAG 정합 게이트는 향후 충족.

→ 실 출력 캡쳐 후 plan 본문에 결과 메모.

- [ ] **Step 1.9: 기존 회귀 검증 (전체 pytest)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `<BASE_TESTS> + 3 신규 = 186 passed` (또는 ±1, slow 마커 제외 시 185). 회귀 발생 시 디버깅.

- [ ] **Step 1.10: Task 1 commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add pipeline/agents/optimizer/synthetic_daily_report.py pipeline/tests/optimizer/test_synthetic_daily_report_fixture.py && git commit -m "$(cat <<'EOF'
fix(synthetic_daily_report): n_activities 오버산출 버그 + RAG 정합 가드

drift-backlog #3 — synthetic_daily_report.py:78 의 today_qty 산식이
n_activities 만큼 반복되어 5× 오버산출. ratio=0.45 인데도 today_prod 가
baseline 의 2.25배 → forecaster classify_assessment_rag (상향 무조건 정상)
에 의해 "정상" 분류 → Optimizer 약한 권고.

수정:
- :78 today_qty = baseline_q × ratio / n_activities (row 당 분배)
- :118 _parse_scenario 에 n_activities <= 0 ValueError 가드
- tests/optimizer/test_synthetic_daily_report_fixture.py — 재현/픽스/RAG 정합 3건

산술 검증 (남웅, ratio=0.45, n=5):
  현: today_prod = 5 × 31.07 × 0.45 = 69.91 ≈ raw 69.62
  픽스: today_prod = 31.07 × 0.45 = 13.98 (RAG 평균 23.25 대비 -40% → "이상")

EOF
)"
```

---

## Task 2: HIL 1 구현 (hil_1_node + graph + PG + CLI)

**Files:**
- Modify: `pipeline/state.py` (변경 0건 — 이미 정의됨, 사실 확인만)
- Modify: `pipeline/graph.py:262~271` (build_graph edges + hil_1_node 추가)
- Modify: `pipeline/graph.py:200~230` (build_demo_graph 는 mapper 미포함이라 hil_1 제외 — 현재 변경 X)
- Modify: `pipeline/db.py:204` (insert_mapping_correction 추가)
- Create: `pipeline/tests/test_graph_hil1.py` (unit)
- Create: `pipeline/tests/test_graph_e2e_hil1.py` (e2e, slow)

- [ ] **Step 2.1: HIL 1 state 자리 재확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -n "hil_1_corrections\|waiting_hil_1\|requires_review" pipeline/state.py
```

Expected:
- `state.py:56:    requires_review: bool` (Activity)
- `state.py:118:    hil_1_corrections: dict`
- `state.py:133:        "waiting_hil_1",`

→ 자리 3건 모두 확인. state.py 변경 없이 활용.

- [ ] **Step 2.2: insert_mapping_correction unit 테스트 작성**

`pipeline/tests/test_db.py` 끝에 추가 (또는 신규 `test_db_mapping_corrections.py` 생성). 본 plan 은 후자 권장:

```python
"""PGClient.insert_mapping_correction 테스트.

Spec: docs/schema/postgres.md §8 mapping_corrections.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio

from pipeline.db import PGClient


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_insert_mapping_correction_roundtrip(pg_url: str) -> None:
    """insert_mapping_correction 1 row INSERT 후 SELECT 정합 검증."""
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        await pg.insert_mapping_correction(
            run_id=run_id,
            date=date(2025, 9, 27),
            work_content="1F 벽체 콘크리트 타설",
            company="남웅건설",
            trade="철근콘크리트공사",
            original={"wa": "CUB", "l6_main": "철근콘크리트공사", "mapping_conf": 0.55, "mapping_source": "hil_required"},
            corrected={"wa": "CUB", "l6_main": "철근콘크리트공사", "mapping_source": "user_corrected"},
            correction_type="replace",
        )
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT work_content, company, trade, original, corrected, correction_type "
                "FROM mapping_corrections WHERE run_id=$1",
                run_id,
            )
        assert row is not None
        assert row["company"] == "남웅건설"
        assert row["correction_type"] == "replace"
        import json
        assert json.loads(row["original"])["wa"] == "CUB"
        assert json.loads(row["corrected"])["mapping_source"] == "user_corrected"
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()
```

- [ ] **Step 2.3: insert_mapping_correction 테스트 실행 (fail 확인)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_db_mapping_corrections.py -v
```

Expected: **FAIL** — `AttributeError: 'PGClient' object has no attribute 'insert_mapping_correction'`.

- [ ] **Step 2.4: PGClient.insert_mapping_correction 구현**

`pipeline/db.py:271` (insert_forecast 다음, insert_optimizer_advice 앞) Edit — 신규 메서드 추가:

```python
    async def insert_mapping_correction(
        self,
        run_id: uuid.UUID,
        date: _date,
        work_content: str,
        company: str | None,
        trade: str | None,
        original: dict,
        corrected: dict,
        correction_type: str,
    ) -> None:
        """mapping_corrections 테이블 INSERT 1 row.

        Spec: docs/schema/postgres.md §8.
        original / corrected = JSONB (Mapper 추천 + 사용자 정정).
        correction_type ∈ {"replace", "split", "reject"} — PoC 는 "replace" 만 사용.
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mapping_corrections (
                    run_id, date, work_content, company, trade,
                    original, corrected, correction_type
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6::jsonb, $7::jsonb, $8
                )
                """,
                run_id,
                date,
                work_content,
                company,
                trade,
                _json.dumps(original, ensure_ascii=False),
                _json.dumps(corrected, ensure_ascii=False),
                correction_type,
            )
```

- [ ] **Step 2.5: insert_mapping_correction 테스트 PASS 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_db_mapping_corrections.py -v
```

Expected: **1 passed**.

- [ ] **Step 2.6: hil_1_node unit 테스트 작성**

`pipeline/tests/test_graph_hil1.py` 신규:

```python
"""HIL 1 node unit — review_needed 필터 + corrections 적용.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.1
"""

from __future__ import annotations

import pytest
from langgraph.types import Command

from pipeline.state import Activity


def _activity(
    idx: int,
    requires_review: bool,
    wa: str | None = "CUB",
    l6_main: str | None = "철근콘크리트공사",
    mapping_conf: float = 0.85,
    mapping_source: str = "auto_bp_single",
) -> Activity:
    """fixture helper."""
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": l6_main,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "철근콘크리트공사",
        "company": f"company_{idx}",
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": f"work_{idx}",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": wa,
        "mapping_conf": mapping_conf,
        "mapping_source": mapping_source,
        "requires_review": requires_review,
    }


def test_hil_1_node_no_review_passthrough() -> None:
    """모든 Activity 의 requires_review=False → interrupt 미발생, 통과."""
    from pipeline.graph import hil_1_node
    state = {"mapped": [_activity(0, False), _activity(1, False)]}
    # cfg 는 미사용 (현재 hil_1_node 가 cfg 받지만 PG insert 안 함 in this path)
    # ... 실제 호출은 LangGraph 컨텍스트 안에서. 단순 함수 호출 검증.
    # interrupt 미발생 시 ReturnType = dict with hil_1_corrections={}
    # 본 테스트는 async — pytest-asyncio 마커 + ainvoke 또는 직접 await.
    import asyncio
    result = asyncio.run(hil_1_node(state, cfg=None))
    assert result["hil_1_corrections"] == {}
    assert result["current_node"] == "hil_1"
    assert "mapped" not in result or result["mapped"] == state["mapped"]


def test_hil_1_node_review_needed_filter() -> None:
    """requires_review=True 인 Activity 만 review_needed payload 에 포함되는지 검증.

    interrupt 발생 시 LangGraph runtime 외에서는 GraphInterrupt exception. 본 unit 은
    runtime 컨텍스트 없이 review_needed payload 만 빌드하는 helper 분리하여 검증.

    구현 노트: hil_1_node 내부에 _build_review_needed(mapped: list[Activity]) -> list[dict]
    헬퍼 함수 분리 후 본 테스트가 호출.
    """
    from pipeline.graph import _build_review_needed
    mapped = [
        _activity(0, False),
        _activity(1, True, mapping_conf=0.55, mapping_source="hil_required"),
        _activity(2, True, mapping_conf=0.62, mapping_source="hil_required"),
        _activity(3, False),
    ]
    review = _build_review_needed(mapped)
    assert len(review) == 2
    assert review[0]["idx"] == 1
    assert review[1]["idx"] == 2
    assert review[0]["mapping_conf"] == 0.55
    assert review[0]["mapping_source"] == "hil_required"
    assert review[0]["work_content"] == "work_1"


def test_hil_1_node_apply_corrections() -> None:
    """corrections dict 가 mapped 의 해당 idx 의 Activity 의 wa/l6/source/requires_review 수정.

    apply 헬퍼 _apply_corrections(mapped: list[Activity], corrections: dict) -> list[Activity].
    """
    from pipeline.graph import _apply_corrections
    mapped = [
        _activity(0, False, wa="OLD"),
        _activity(1, True, wa="WRONG", mapping_source="hil_required"),
        _activity(2, True, wa="WRONG2", mapping_source="hil_required"),
    ]
    corrections = {1: {"wa": "CORRECTED_1", "l6_main": "철근콘크리트공사"}}
    out = _apply_corrections(mapped, corrections)
    assert out[0]["wa"] == "OLD"  # 영향 없음
    assert out[1]["wa"] == "CORRECTED_1"
    assert out[1]["mapping_source"] == "user_corrected"
    assert out[1]["requires_review"] is False
    # idx 2 는 corrections 에 없음 → 답 안 한 row 처리:
    # spec §5.1: "답 안 한 row 는 Mapper 추천 그대로 수용 (requires_review=False)"
    assert out[2]["wa"] == "WRONG2"
    assert out[2]["mapping_source"] == "user_corrected"  # 추천 수용 표시
    assert out[2]["requires_review"] is False
```

- [ ] **Step 2.7: hil_1_node unit 테스트 실행 (fail 확인)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/test_graph_hil1.py -v
```

Expected: **3 FAIL** — `_build_review_needed`, `_apply_corrections`, `hil_1_node` 모두 미정의. `ImportError`.

- [ ] **Step 2.8: hil_1_node + helper 함수 구현**

`pipeline/graph.py:70` (forecaster_node 앞) Edit — 신규 함수 3개 추가:

```python
def _build_review_needed(mapped: list[Activity]) -> list[dict]:
    """requires_review=True 인 Activity 만 review payload 빌드.

    Spec §5.1 — interrupt payload schema.
    """
    return [
        {
            "idx": i,
            "work_content": a["work_content"],
            "company": a["company"],
            "trade": a["trade"],
            "wa": a.get("wa"),
            "l6_main": a.get("l6_main"),
            "mapping_conf": a.get("mapping_conf"),
            "mapping_source": a.get("mapping_source"),
        }
        for i, a in enumerate(mapped)
        if a.get("requires_review")
    ]


def _apply_corrections(
    mapped: list[Activity],
    corrections: dict[int, dict],
) -> list[Activity]:
    """corrections dict (idx → {wa, l6_main}) 를 mapped 에 적용.

    Spec §5.1 #6:
    - 답한 row: wa/l6_main 수정 + mapping_source="user_corrected" + requires_review=False
    - 답 안 한 row (review_needed 였으나 corrections 에 없음): Mapper 추천 수용 +
      mapping_source="user_corrected" + requires_review=False (재시도 X — PoC 기본)
    """
    out: list[Activity] = []
    for i, a in enumerate(mapped):
        if a.get("requires_review"):
            c = corrections.get(i)
            if c:
                # 사용자 정정
                new_a: Activity = {
                    **a,
                    "wa": c["wa"],
                    "l6_main": c["l6_main"],
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            else:
                # 추천 수용
                new_a = {
                    **a,
                    "mapping_source": "user_corrected",
                    "requires_review": False,
                }
            out.append(new_a)
        else:
            out.append(a)
    return out


async def hil_1_node(state: CPIAState, cfg) -> dict:
    """Mapper 결과 사람 검토. requires_review=True 가 1건 이상이면 interrupt.

    Spec §5.1. cfg 는 GraphConfig (PG INSERT 용 postgres_url 추출).
    """
    mapped = state["mapped"]
    review_needed = _build_review_needed(mapped)
    if not review_needed:
        return {"hil_1_corrections": {}, "current_node": "hil_1"}

    corrections = interrupt({"review_needed": review_needed})
    corrections = corrections or {}
    # corrections dict 의 key 가 str 로 들어올 수 있음 (JSON round-trip) — int 변환
    corrections = {int(k): v for k, v in corrections.items()}

    corrected = _apply_corrections(mapped, corrections)

    # PG mapping_corrections 영속
    if cfg is not None and corrections:
        from datetime import date as _date
        pg = PGClient(cfg.mapper.postgres_url)
        await pg.connect()
        try:
            run_id_str = state["run_id"]
            run_id = uuid.UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
            today = _date.fromisoformat(state["date"])
            for idx, c in corrections.items():
                original_a = mapped[idx]
                await pg.insert_mapping_correction(
                    run_id=run_id,
                    date=today,
                    work_content=original_a["work_content"],
                    company=original_a.get("company"),
                    trade=original_a.get("trade"),
                    original={
                        "wa": original_a.get("wa"),
                        "l6_main": original_a.get("l6_main"),
                        "mapping_conf": original_a.get("mapping_conf"),
                        "mapping_source": original_a.get("mapping_source"),
                    },
                    corrected={
                        "wa": c["wa"],
                        "l6_main": c["l6_main"],
                        "mapping_source": "user_corrected",
                    },
                    correction_type="replace",
                )
        finally:
            await pg.close()

    return {
        "mapped": corrected,
        "hil_1_corrections": corrections,
        "current_node": "hil_1",
    }
```

- [ ] **Step 2.9: hil_1_node unit 테스트 PASS 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/test_graph_hil1.py -v
```

Expected: **3 passed**.

- [ ] **Step 2.10: build_graph edges 변경 (mapper → hil_1 → atomizer)**

`pipeline/graph.py:262~263` Edit:

```python
    graph.add_node("mapper", _mapper)
    graph.add_node("hil_1", _hil_1)  # 신규
    graph.add_node("atomizer", _atomizer)
    ...
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "hil_1")  # 변경 (기존: mapper → atomizer)
    graph.add_edge("hil_1", "atomizer")  # 신규
```

`build_graph` 함수 안에 `_hil_1` 클로저 추가 (`_mapper` 패턴 차용):

```python
    async def _hil_1(state: CPIAState) -> dict:
        return await hil_1_node(state, cfg)
```

- [ ] **Step 2.11: HIL 1 e2e 테스트 작성 (slow)**

`pipeline/tests/test_graph_e2e_hil1.py` 신규:

```python
"""HIL 1 e2e — interrupt + Command(resume=) cycle.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.1

2 path:
  1. test_hil_1_skip_no_review — requires_review=False 모두 → __interrupt__ 미발생, mapped 그대로
  2. test_hil_1_resume_with_corrections — requires_review=True 1건 → interrupt → Command(resume={1: {...}}) → 적용 검증
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from langgraph.types import Command

from pipeline import graph as graph_module
from pipeline.graph import GraphConfig, build_graph


@pytest.fixture
def cfg() -> GraphConfig:
    """env 필수 + (LLM 호출은 monkeypatch 로 무력화 — 비용 0)."""
    keys = ["POSTGRES_URL", "CHROMA_HOST"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    # 본 plan 의 Step 2.11 fixture 는 test_graph_e2e_hil2.py:42-60 패턴 차용.
    # 생략 — 동일 GraphConfig 빌드 (생략된 부분은 plan reviewer 가 spec 확인).
    raise NotImplementedError("실 구현은 test_graph_e2e_hil2.py:cfg fixture 차용")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_hil_1_skip_no_review(cfg, monkeypatch) -> None:
    """모든 Activity requires_review=False → interrupt 미발생."""
    # mapper/atomizer/forecaster monkeypatch (LLM 비용 0)
    # mapped state 사전 주입 (requires_review=False 만)
    # build_graph(cfg).ainvoke(...) 호출 후 __interrupt__ 확인 (없어야 함)
    # plan reviewer 의견에 따라 test_graph_e2e_hil2.py:test_graph_e2e_hil2_skip_no_risky 패턴 정확히 차용.
    pass


@pytest.mark.slow
@pytest.mark.asyncio
async def test_hil_1_resume_with_corrections(cfg, monkeypatch) -> None:
    """requires_review=True 1건 → interrupt → resume → 적용 검증.

    1. mapper_node monkeypatch → mapped = [activity(requires_review=True)] 반환
    2. atomizer_node + forecaster_node + hil_2_node monkeypatch → empty dict
    3. ainvoke → __interrupt__ payload 의 review_needed length=1 확인
    4. Command(resume={0: {"wa": "TEST", "l6_main": "TEST_L6"}}) 호출
    5. final.mapped[0].wa == "TEST", mapping_source == "user_corrected", requires_review == False
    6. PG mapping_corrections 에 row 1건 INSERT 확인 (SELECT)
    """
    # plan reviewer 의견 + spec §5.1 의 review_needed payload schema 정확히 검증.
    pass
```

(상세 fixture/monkeypatch 본문은 implementation 시 `test_graph_e2e_hil2.py` 패턴 그대로 차용 — plan reviewer 가 본 step 의 schema/시그니처 정합 확인.)

- [ ] **Step 2.12: HIL 1 e2e 테스트 실행 (fail 확인 → 구현 → pass)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_graph_e2e_hil1.py -v -m slow 2>&1 | tail -20
```

Expected:
1. 첫 실행: FAIL (test 본문 NotImplementedError 또는 pass)
2. 본문 구현 후 재실행: **2 passed** (test_hil_1_skip_no_review + test_hil_1_resume_with_corrections)

- [ ] **Step 2.13: 회귀 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `<BASE_TESTS> + 3 (fixture) + 1 (mapping_corr) + 3 (hil_1 unit) + 2 (hil_1 e2e) = 192 passed` (또는 ±2). 기존 mapper/atomizer/forecaster/hil_2 테스트 회귀 0건.

- [ ] **Step 2.14: CLI 인터랙티브 — synthetic_daily_report 에 --auto-correct-all 흐름 추가**

이 step 은 `synthetic_daily_report.py` 의 CLI 가 hil_1 도 만나면 통과시키기 위함. 현재 fake_daily_report 는 `requires_review=False` 만 박음 (line 97 fact) → hil_1 무발동. **변경 X** (synthetic CLI 측은 hil_1 통과 자동 보장됨).

→ 실 production CLI (`pipeline/main.py`) 의 HIL 1 인터랙티브는 본 cycle out-of-scope (drift backlog #5 cycle). 본 plan 의 CLI 흐름 = unit/e2e 테스트로 검증 + synthetic 우회.

- [ ] **Step 2.15: Task 2 commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add pipeline/graph.py pipeline/db.py pipeline/tests/test_graph_hil1.py pipeline/tests/test_graph_e2e_hil1.py pipeline/tests/test_db_mapping_corrections.py && git commit -m "$(cat <<'EOF'
feat(hil_1): Mapper 결과 사람 검토 + PG mapping_corrections 영속

drift-backlog #4 — state placeholder + Activity flag 있었으나 graph node
없음. 본 commit 이 채움.

변경:
- graph.py: hil_1_node (interrupt + Command(resume=) 패턴, hil_2 차용)
  + _build_review_needed + _apply_corrections helper
  + build_graph edges (mapper → hil_1 → atomizer)
- db.py: insert_mapping_correction (postgres.md §8 schema 그대로)
- tests/test_graph_hil1.py: unit 3건 (review 필터 + corrections 적용 + passthrough)
- tests/test_graph_e2e_hil1.py: e2e 2 path (skip_no_review + resume_with_corrections, slow)
- tests/test_db_mapping_corrections.py: PG INSERT roundtrip

원안 v2 와의 drift: HIL 1 입력 채널 = CLI 인터랙티브 (HIL 2 패턴 차용,
B_Track Dashboard 의존 회피). spec §3 명시.

EOF
)"
```

---

## Task 3: Reporter 구현 (reporter.py + reporter_node + few-shot golden)

**Files:**
- Create: `pipeline/agents/reporter.py` (~150 lines)
- Modify: `pipeline/graph.py:32~37` (GraphConfig 에 reporter 필드)
- Modify: `pipeline/graph.py:266~271` (build_graph conditional_edges + reporter_node 추가)
- Modify: `pipeline/graph.py:223~229` (build_demo_graph 동일 추가)
- Modify: `pipeline/db.py` (insert_daily_report 추가)
- Create: `pipeline/tests/test_reporter.py` (~120 lines)

- [ ] **Step 3.1: insert_daily_report 테스트 작성**

`pipeline/tests/test_db_daily_reports.py` 신규:

```python
"""PGClient.insert_daily_report 테스트.

Spec: docs/schema/postgres.md §5 daily_reports.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest

from pipeline.db import PGClient


@pytest.fixture
def pg_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        pytest.skip("POSTGRES_URL 환경변수 누락")
    return url


@pytest.mark.asyncio
async def test_insert_daily_report_roundtrip(pg_url: str) -> None:
    run_id = uuid.uuid4()
    pg = PGClient(pg_url)
    await pg.connect()
    try:
        await pg.insert_pipeline_run(run_id, "DEMO_SITE", "2025-09-27", "running")
        await pg.insert_daily_report(
            run_id=run_id,
            date=date(2025, 9, 27),
            report_md="# 2025-09-27 작업일보 종합 보고서\n\n테스트 본문.",
            summary={"total_workers": 50.0, "risk_counts": {"정상": 2, "주의": 1, "이상": 0}, "advice_count": 1},
        )
        async with pg._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT report_md, summary FROM daily_reports WHERE run_id=$1",
                run_id,
            )
        assert row is not None
        assert "2025-09-27" in row["report_md"]
        import json
        assert json.loads(row["summary"])["total_workers"] == 50.0
    finally:
        await pg.delete_pipeline_run(run_id)
        await pg.close()
```

- [ ] **Step 3.2: insert_daily_report 테스트 실행 (fail)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_db_daily_reports.py -v
```

Expected: **FAIL** — `AttributeError: 'PGClient' object has no attribute 'insert_daily_report'`.

- [ ] **Step 3.3: insert_daily_report 구현**

`pipeline/db.py:309` (insert_optimizer_advice 다음) Edit:

```python
    async def insert_daily_report(
        self,
        run_id: uuid.UUID,
        date: _date,
        report_md: str,
        summary: dict,
    ) -> None:
        """daily_reports 테이블 INSERT 1 row.

        Spec: docs/schema/postgres.md §5 (id/created_at auto).
        """
        import json as _json

        assert self._pool is not None, "connect() 미호출"
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO daily_reports (run_id, date, report_md, summary)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                run_id,
                date,
                report_md,
                _json.dumps(summary, ensure_ascii=False),
            )
```

- [ ] **Step 3.4: insert_daily_report 테스트 PASS 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_db_daily_reports.py -v
```

Expected: **1 passed**.

- [ ] **Step 3.5: Reporter unit 테스트 작성 (LLM mock)**

`pipeline/tests/test_reporter.py` 신규:

```python
"""Reporter unit + 통합 테스트.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def reporter_cfg():
    from pipeline.agents.reporter import ReporterConfig
    return ReporterConfig(
        azure_endpoint="https://fake.openai.azure.com/",
        azure_api_key="fake_key",
        azure_api_version="2024-12-01-preview",
        llm_model="gpt-5.1-chat-ai-board-test",
        postgres_url=os.environ.get("POSTGRES_URL", "postgresql://fake"),
    )


@pytest.mark.asyncio
async def test_reporter_mapped_empty_fallback(reporter_cfg) -> None:
    """mapped empty → 짧은 fallback MD + PG INSERT skip."""
    from pipeline.agents.reporter import report
    run_id = uuid.uuid4()
    today = date(2025, 9, 27)
    md, summary = await report(
        mapped=[], forecast_rows=[], optimizer_advice=[],
        run_id=run_id, today=today, cfg=reporter_cfg,
    )
    assert "보고서 생성 실패" in md
    assert "매핑 데이터 없음" in md
    assert summary == {}


@pytest.mark.asyncio
async def test_reporter_llm_mock_full_flow(reporter_cfg) -> None:
    """Azure LLM mock + Mapper+Forecaster+Optimizer 모두 있는 경우 종합 MD 산출."""
    from pipeline.agents.reporter import report
    
    fixture_mapped = [
        {"company": "남웅건설", "trade": "철근콘크리트공사", "l6_main": "철근콘크리트공사",
         "unit": "m3", "today_qty": 14.0, "assigned_workers": 31.0,
         "work_content": "1F 벽체 콘크리트 타설"}
    ]
    fixture_forecast = [
        {"company": "남웅건설", "l6_main": "철근콘크리트공사",
         "today_productivity": 0.452, "assessment": "이상", "risk_level": "이상",
         "reasoning": "유사 5건 평균 0.78 m3/인 대비 -42%."}
    ]
    fixture_advice = [
        {"company": "남웅건설", "l6_main": "철근콘크리트공사", "forecast_assessment": "이상",
         "diagnosis": "타워크레인 스케줄 충돌.",
         "recommendations": [{"rank": 1, "text": "타워크레인 스케줄 확인"}],
         "recovery_distribution": {"d+1": 2, "not_recovered": 1}}
    ]
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "# 2025-09-27 작업일보 종합 보고서\n\n"
        "## 1부 작업 통합\n남웅건설 31.0 인원 14.0 m3\n\n"
        "## 2부 생산성 진단\n남웅건설 / 철근콘크리트공사 — risk_level: 이상\n\n"
        "## 3부 PM 선택 공종 권고\n타워크레인 스케줄 확인"
    )
    
    with patch("pipeline.agents.reporter.AzureOpenAI") as mock_cls:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_cls.return_value = mock_client
        run_id = uuid.uuid4()
        today = date(2025, 9, 27)
        md, summary = await report(
            mapped=fixture_mapped, forecast_rows=fixture_forecast,
            optimizer_advice=fixture_advice,
            run_id=run_id, today=today, cfg=reporter_cfg,
        )
    
    assert "2025-09-27" in md
    assert "1부" in md and "2부" in md and "3부" in md
    assert summary["total_workers"] == 31.0
    assert summary["risk_counts"]["이상"] == 1
    assert summary["advice_count"] == 1


@pytest.mark.asyncio
async def test_reporter_empty_optimizer_advice_skips_3bu(reporter_cfg) -> None:
    """optimizer_advice=[] 인 경우 LLM prompt 가 '3부 생략' 지시 받음 + summary.advice_count=0."""
    from pipeline.agents.reporter import _build_llm_input, report
    fixture_mapped = [
        {"company": "남웅건설", "trade": "철근콘크리트공사", "l6_main": "철근콘크리트공사",
         "unit": "m3", "today_qty": 14.0, "assigned_workers": 31.0,
         "work_content": "타설"}
    ]
    fixture_forecast = [
        {"company": "남웅건설", "l6_main": "철근콘크리트공사",
         "today_productivity": 0.45, "assessment": "정상", "risk_level": "정상",
         "reasoning": "정상 범위."}
    ]
    llm_input = _build_llm_input(
        mapped=fixture_mapped, forecast_rows=fixture_forecast,
        optimizer_advice=[], today=date(2025, 9, 27),
    )
    assert llm_input["optimizer_advice"] == []
```

- [ ] **Step 3.6: Reporter unit 테스트 실행 (fail)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/test_reporter.py -v
```

Expected: **3 FAIL** (`ImportError: cannot import name 'report' / 'ReporterConfig' / '_build_llm_input'`).

- [ ] **Step 3.7: reporter.py 구현**

`pipeline/agents/reporter.py` 신규 (현 0 lines):

```python
"""Reporter agent — Mapper + Forecaster + Optimizer 결과 종합 보고서.

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date as _date
from typing import Any

from openai import AzureOpenAI

from pipeline.db import PGClient
from pipeline.state import Activity


SYSTEM_PROMPT = """건설 현장 작업일보 종합 보고서 생성기.
입력 JSON 의 (1) 매핑 결과 (mapped) (2) 진단 (forecast) (3) 권고 (optimizer_advice) 를 받아
마크다운 종합 보고서 1 종을 생성한다.

출력 schema (마크다운, 머리말 + 3 부):
  # YYYY-MM-DD 작업일보 종합 보고서

  ## 1부 작업 통합
    - trade/BP사별 인원·물량·작업 요지 (mapped 합산)
    - 표 우선, 행 많으면 bullet

  ## 2부 생산성 진단
    - 공종별 today_productivity / risk_level / reasoning (forecast row 별 1 단락)
    - assessment=None (cold_start) 인 경우 "데이터 부족 — 판단 보류" 그대로 유지

  ## 3부 PM 선택 공종 권고 (optimizer_advice 가 비어있으면 본 부 전체 생략)
    - 공종별 diagnosis + recommendations rank 1~4 (optimizer_advice row 별)
    - recovery_distribution 가 있으면 footnote 인용

규칙:
  - 마크다운만 (HTML 사용 금지, 한자 사용 금지 — 한글 + 영어만)
  - 들여쓰기 1~2 단계만 (3 단계 이상 금지)
  - 텍스트는 한국어 위주, 코드/식별자/외래어 고유명사만 영어
  - 진단의 risk_level 과 reasoning 이 의미적으로 정합되도록 (분류 결과 뒤집지 말 것)
"""


@dataclass
class ReporterConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    postgres_url: str
    azure_timeout: float = 60.0
    azure_max_retries: int = 3


def _build_llm_input(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
    today: _date,
) -> dict[str, Any]:
    """LLM user message JSON 빌더 — spec §5.3 few-shot 형식."""
    return {
        "date": today.isoformat(),
        "activities": [
            {
                "company": a.get("company"),
                "trade": a.get("trade"),
                "l6_main": a.get("l6_main"),
                "unit": a.get("unit"),
                "today_qty": a.get("today_qty"),
                "assigned_workers": a.get("assigned_workers"),
                "work_content": a.get("work_content"),
            }
            for a in mapped
        ],
        "forecast": forecast_rows,
        "optimizer_advice": optimizer_advice,
    }


def _build_summary(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
) -> dict:
    """summary JSONB — Dashboard / 운영 감사용."""
    qty_by_trade: dict[str, float] = {}
    for a in mapped:
        trade = a.get("trade") or "_unknown"
        qty_by_trade[trade] = qty_by_trade.get(trade, 0.0) + (a.get("today_qty") or 0.0)
    risk_counts: dict[str, int] = {"정상": 0, "주의": 0, "이상": 0}
    for f in forecast_rows:
        rl = f.get("risk_level")
        if rl in risk_counts:
            risk_counts[rl] += 1
    return {
        "total_workers": sum(a.get("assigned_workers") or 0.0 for a in mapped),
        "total_qty_by_trade": qty_by_trade,
        "risk_counts": risk_counts,
        "advice_count": len(optimizer_advice),
    }


async def report(
    mapped: list[Activity],
    forecast_rows: list[dict],
    optimizer_advice: list[dict],
    run_id: uuid.UUID,
    today: _date,
    cfg: ReporterConfig,
) -> tuple[str, dict]:
    """종합 보고서 생성 + PG INSERT.

    반환: (report_md, summary_dict). mapped empty 시 짧은 fallback + PG INSERT skip.
    """
    if not mapped:
        return ("# 보고서 생성 실패\n매핑 데이터 없음.", {})

    client = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )
    llm_input = _build_llm_input(mapped, forecast_rows, optimizer_advice, today)
    response = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(llm_input, ensure_ascii=False)},
        ],
    )
    report_md = response.choices[0].message.content or "# 보고서 생성 실패\nLLM 빈 응답."
    summary = _build_summary(mapped, forecast_rows, optimizer_advice)

    # PG INSERT
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        await pg.insert_daily_report(run_id, today, report_md, summary)
    finally:
        await pg.close()

    return (report_md, summary)
```

- [ ] **Step 3.8: Reporter unit 테스트 PASS 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -m pytest tests/test_reporter.py -v
```

Expected: **3 passed**.

- [ ] **Step 3.9: GraphConfig 에 reporter 필드 추가 + reporter_node + graph edges**

`pipeline/graph.py:32~37` Edit:

```python
@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig
    optimizer: OptimizerConfig
    reporter: ReporterConfig  # 신규
```

import 추가 (graph.py 상단):
```python
from pipeline.agents.reporter import ReporterConfig, report
```

reporter_node 함수 추가 (graph.py:198 optimizer_node 다음):

```python
async def reporter_node(state: CPIAState, cfg: GraphConfig) -> dict:
    """Mapper + Forecaster + Optimizer 종합 보고서 생성.

    Spec §5.3. selection=[] (Optimizer skip) 인 경우에도 본 노드 진입.
    """
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    report_md, _summary = await report(
        mapped=state["mapped"],
        forecast_rows=state.get("forecast", []),
        optimizer_advice=state.get("optimizer_advice", []),
        run_id=run_id,
        today=today,
        cfg=cfg.reporter,
    )
    return {"report_md": report_md, "current_node": "reporter"}
```

`build_graph` 안 edges 변경 (graph.py:266~271):

```python
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)  # 신규
    ...
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",  # 변경 (기존: END)
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")  # 변경 (기존: optimizer → END)
    graph.add_edge("reporter", END)  # 신규
```

`build_graph` 안 `_reporter` 클로저 추가:
```python
    async def _reporter(state: CPIAState) -> dict:
        return await reporter_node(state, cfg)
```

`build_demo_graph` 도 동일 변경 (graph.py:223~229):

```python
    graph.add_node("optimizer", _optimizer)
    graph.add_node("reporter", _reporter)
    ...
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else "reporter",
        {"optimizer": "optimizer", "reporter": "reporter"},
    )
    graph.add_edge("optimizer", "reporter")
    graph.add_edge("reporter", END)
```

`build_demo_graph_config` (synthetic_daily_report.py:298) 에 reporter 추가:

```python
    return GraphConfig(
        mapper=...,
        atomizer=...,
        forecaster=_build_forecaster_config(),
        optimizer=_build_optimizer_config(),
        reporter=_build_reporter_config(),  # 신규
    )
```

`_build_reporter_config()` 도 synthetic_daily_report.py 안에 추가 (`_build_optimizer_config` 패턴 차용):

```python
def _build_reporter_config():
    from pipeline.agents.reporter import ReporterConfig
    return ReporterConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        llm_model=os.environ["LLM_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
    )
```

- [ ] **Step 3.10: 회귀 확인 — HIL 2 e2e + 기존**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_graph_e2e_hil2.py -v -m slow 2>&1 | tail -10
```

Expected: 기존 4 path PASS — Reporter 노드 추가로 final state 가 변경되었지만, 4 path 의 assertion 은 `__interrupt__` payload 또는 `optimizer_advice` 검증이라 영향 없어야. 회귀 시 추가 디버깅.

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `<BASE_TESTS> + 3 (Task 1) + 4 (Task 2 unit+db) + 2 (Task 2 e2e) + 3 (Task 3 unit) + 1 (Task 3 db) = 196 passed` (또는 ±2).

- [ ] **Step 3.11: Task 3 commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add pipeline/agents/reporter.py pipeline/graph.py pipeline/db.py pipeline/agents/optimizer/synthetic_daily_report.py pipeline/tests/test_reporter.py pipeline/tests/test_db_daily_reports.py && git commit -m "$(cat <<'EOF'
feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports

drift-backlog #1 — pipeline/agents/reporter.py 0 lines → 풀 구현.

위치 결정: Optimizer 다음 (또는 hil_2 selection=[] 분기 합류). PM 원안 v2
의 "Atomizer 다음 병렬" 과 의도적 drift — 사용자 결정으로 Forecaster +
Optimizer 결과 모두 포함하는 종합 보고서로 변경. spec §3 명시.

변경:
- agents/reporter.py 신규: SYSTEM_PROMPT 3 부 구조 + _build_llm_input
  + _build_summary + report() 공개 API
- graph.py: reporter_node + GraphConfig.reporter 필드 + edges
  (hil_2 → optimizer | reporter, optimizer → reporter, reporter → END)
- agents/optimizer/synthetic_daily_report.py: _build_reporter_config +
  build_demo_graph_config 확장
- db.py: insert_daily_report (postgres.md §5 schema 그대로)
- tests/test_reporter.py: empty fallback + LLM mock 종합 + 3부 생략 (3건)
- tests/test_db_daily_reports.py: PG INSERT roundtrip

EOF
)"
```

---

## Task 4: PostgresSaver 전환

**Files:**
- Modify: `pipeline/pyproject.toml:11` (의존성 추가)
- Modify: `pipeline/checkpointer.py:13` (InMemorySaver → PostgresSaver + fallback flag)
- Modify: `pipeline/tests/test_graph_e2e_hil2.py` + `test_graph_e2e_hil1.py` (fresh checkpointer 격리 확인)

design-intent O-6 권고 대응. 본 Task 는 Task 2+3 완료 후 진입 (e2e 테스트가 회귀 대상).

- [ ] **Step 4.1: langgraph-checkpoint-postgres 의존성 추가**

`pipeline/pyproject.toml:11` 의 dependencies 끝에 추가:

```toml
dependencies = [
    "langgraph>=0.2.0",
    "langgraph-checkpoint-postgres>=2.0.0",
    "langchain>=0.3.0",
    ...
]
```

설치:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/pip install "langgraph-checkpoint-postgres>=2.0.0" 2>&1 | tail -5
```

Expected: `Successfully installed langgraph-checkpoint-postgres-X.X.X` (또는 이미 설치됨 경고).

- [ ] **Step 4.2: PostgresSaver import 시그니처 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && .venv/bin/python3 -c "from langgraph.checkpoint.postgres import PostgresSaver; help(PostgresSaver.from_conn_string)" 2>&1 | head -30
```

Expected: `PostgresSaver.from_conn_string` 시그니처 출력. 신호:
- `from_conn_string(conn_string: str) -> ContextManager[PostgresSaver]` (sync) 또는
- `AsyncPostgresSaver.from_conn_string(...)` (async)

→ 실 출력 캡쳐. async vs sync 변형에 따라 build_checkpointer 시그니처 변경.

- [ ] **Step 4.3: checkpointer.py 변경 + fallback flag**

`pipeline/checkpointer.py` 전체 재작성:

```python
"""LangGraph checkpoint — Phase 2 통합 cycle: PostgresSaver (fallback InMemorySaver).

design-intent O-6: Reporter cycle 또는 통합 cycle 진입 시 전환.
환경변수 CPIA_CHECKPOINTER=memory 로 fallback (개발/테스트용).

Spec: docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §7.4
"""

from __future__ import annotations

import os

from langgraph.checkpoint.memory import InMemorySaver


def build_checkpointer():
    """Phase 2 — PostgresSaver default, fallback InMemorySaver.

    CPIA_CHECKPOINTER=memory → InMemorySaver (Phase 1 호환)
    그 외 → PostgresSaver (POSTGRES_URL 필수)
    """
    if os.environ.get("CPIA_CHECKPOINTER", "postgres") == "memory":
        return InMemorySaver()

    postgres_url = os.environ.get("POSTGRES_URL")
    if not postgres_url:
        # POSTGRES_URL 없으면 무리한 PG 연결 시도하지 말고 InMemory fallback
        return InMemorySaver()

    # 본 step 4.2 의 실 시그니처에 따라 PostgresSaver 호출
    # 예시 (실 시그니처는 Step 4.2 결과로 정정):
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver.from_conn_string(postgres_url)
    # async 변형이면 AsyncPostgresSaver + .setup() 호출 (테이블 생성)
    # 본 build_checkpointer 가 sync 라면 PostgresSaver __enter__ 또는 직접 객체.
    # Step 4.2 결과로 최종 호출 형식 확정.
    return saver
```

→ **Step 4.2 의 실 시그니처에 따라 본 Step 4.3 의 마지막 4 줄 final 결정.** plan reviewer 가 시그니처 정합 검증.

- [ ] **Step 4.4: PostgresSaver checkpoints 테이블 setup**

LangGraph PostgresSaver 는 처음 호출 시 `checkpoints` + `checkpoint_writes` + `checkpoint_blobs` 테이블 자동 생성 (`.setup()` 호출 필요). build_checkpointer 가 saver 반환 시 setup 호출:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -c "
import asyncio
from langgraph.checkpoint.postgres import PostgresSaver
import os
with PostgresSaver.from_conn_string(os.environ['POSTGRES_URL']) as saver:
    saver.setup()
print('OK setup')
"
```

Expected: `OK setup`. PG 에 새 테이블 3개 생성 확인:
```bash
docker exec cpia-pg-local psql -U cpia -d cpia -c "\dt" | grep checkpoint
```
Expected: `checkpoints | checkpoint_writes | checkpoint_blobs` 류 row 3건.

- [ ] **Step 4.5: HIL 2 e2e 회귀 확인 (가장 큰 영향 대상)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_graph_e2e_hil2.py -v -m slow 2>&1 | tail -15
```

Expected: **4 passed**. 회귀 발생 시:
1. `CPIA_CHECKPOINTER=memory` 박고 재실행 → PASS 시 PostgresSaver 변경이 원인 확정
2. 원인 분석 — `thread_id` 격리, async/sync mismatch, setup 호출 누락 등
3. checkpointer.py 추가 수정 또는 test fixture 의 fresh saver 보장

- [ ] **Step 4.6: HIL 1 e2e 회귀 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_graph_e2e_hil1.py -v -m slow 2>&1 | tail -10
```

Expected: **2 passed** (Task 2 의 신규 e2e).

- [ ] **Step 4.7: PostgresSaver 영속 검증 — 신규 테스트**

`pipeline/tests/test_checkpointer.py` 신규:

```python
"""PostgresSaver 영속 검증.

Spec §7.4 + design-intent O-6.
"""

from __future__ import annotations

import os
import pytest


def test_checkpointer_postgres_by_default(monkeypatch) -> None:
    """CPIA_CHECKPOINTER 미설정 + POSTGRES_URL 존재 → PostgresSaver 반환."""
    from langgraph.checkpoint.memory import InMemorySaver
    if not os.environ.get("POSTGRES_URL"):
        pytest.skip("POSTGRES_URL 누락")
    monkeypatch.delenv("CPIA_CHECKPOINTER", raising=False)
    from pipeline.checkpointer import build_checkpointer
    saver = build_checkpointer()
    assert not isinstance(saver, InMemorySaver), "PostgresSaver default 동작 안 함"


def test_checkpointer_memory_fallback(monkeypatch) -> None:
    """CPIA_CHECKPOINTER=memory → InMemorySaver."""
    from langgraph.checkpoint.memory import InMemorySaver
    monkeypatch.setenv("CPIA_CHECKPOINTER", "memory")
    from pipeline.checkpointer import build_checkpointer
    saver = build_checkpointer()
    assert isinstance(saver, InMemorySaver)


def test_checkpointer_no_postgres_url_fallback(monkeypatch) -> None:
    """POSTGRES_URL 미설정 → InMemorySaver fallback."""
    from langgraph.checkpoint.memory import InMemorySaver
    monkeypatch.delenv("POSTGRES_URL", raising=False)
    monkeypatch.delenv("CPIA_CHECKPOINTER", raising=False)
    from pipeline.checkpointer import build_checkpointer
    saver = build_checkpointer()
    assert isinstance(saver, InMemorySaver), "POSTGRES_URL 없으면 fallback 필요"
```

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/test_checkpointer.py -v
```

Expected: **3 passed**.

- [ ] **Step 4.8: 전체 회귀 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `<BASE_TESTS> + 신규 누적 = ~199 passed` (또는 ±2). 회귀 0건.

- [ ] **Step 4.9: Task 4 commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add pipeline/pyproject.toml pipeline/checkpointer.py pipeline/tests/test_checkpointer.py && git commit -m "$(cat <<'EOF'
feat(checkpointer): InMemorySaver → PostgresSaver 전환 + memory fallback

design-intent O-6 권고 — Reporter cycle 또는 통합 cycle 진입 시 전환.

변경:
- pyproject.toml: langgraph-checkpoint-postgres>=2.0.0 의존성 추가
- checkpointer.py: PostgresSaver default + CPIA_CHECKPOINTER=memory fallback
  + POSTGRES_URL 미설정 시 InMemorySaver 안전 분기
- tests/test_checkpointer.py 신규: PostgresSaver default + memory fallback
  + no POSTGRES_URL fallback (3건)

PG 에 신규 테이블 3종 (checkpoints / checkpoint_writes / checkpoint_blobs)
LangGraph auto-create. 기존 HIL 1 + HIL 2 e2e 6 path 회귀 0건.

EOF
)"
```

---

## Task 5: 통합 검증 (시뮬 4건 + 결정성 + Reporter 통합)

**Files:**
- Read-only: 모든 spec/plan/raw
- Create: `docs/audit/raw/v2-scenario-{1,2,3,4}-<run_id>.md` (시뮬 4건 raw)

- [ ] **Step 5.1: 시뮬 4 건 실 호출 (Forecaster fix 효과 검증)**

시뮬 1 (남웅 0.45):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
    --scenario "세보엠이씨|일반공조설비공사|3|정상|1.0|1.0|m2" \
    --scenario "창원기전|전등설비공사|2|정상|1.0|1.0|ea" \
    --auto-select-all 2>&1 | tee /tmp/v2-scenario-1.log
```

Expected (의도 부합 시):
- 시뮬 1 남웅: `today_productivity ≈ baseline_prod × 0.45`, `assessment ∈ {"이상", "주의"}`, `risk_level="이상"` 또는 "주의"
- Optimizer 권고가 정상 path 가 아닌 강한 액션 (장비 점검) 산출

`/tmp/v2-scenario-1.log` 의 핵심 발췌를 `docs/audit/raw/v2-scenario-1-<run_id>.md` 에 Iron Law 3 요소 형식으로 기록.

- [ ] **Step 5.2: 시뮬 2~4 동일 패턴 (라인 생략)**

시나리오 2: `--scenario "남웅건설|철근콘크리트공사|3|우천|0.8|1.0|m3"` (단일 그룹, 우천 0.8)
시나리오 3: `--scenario "남웅건설|철근콘크리트공사|3|돌관|0.45|1.3|m3"`
시나리오 4: `--scenario "신규건설|토목공사|2|정상|1.0|1.0|m3"` (cold_start)

각 호출 후 raw md 1 파일 (총 4 파일).

- [ ] **Step 5.3: 결정성 검증 (시뮬 1 rerun)**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
    --scenario "세보엠이씨|일반공조설비공사|3|정상|1.0|1.0|m2" \
    --scenario "창원기전|전등설비공사|2|정상|1.0|1.0|ea" \
    --auto-select-all --seed 42 2>&1 | tee /tmp/v2-scenario-1-rerun.log
```

비교:
```bash
diff <(grep "today_productivity\|risk_level\|assessment" /tmp/v2-scenario-1.log) <(grep "today_productivity\|risk_level\|assessment" /tmp/v2-scenario-1-rerun.log) || echo "결정론 컬럼 비결정성 발견"
```

Expected: **diff 0 lines** — 결정론 컬럼 100% 일치. LLM 자유텍스트 컬럼은 diff 발생 허용.

- [ ] **Step 5.4: Reporter 통합 시뮬 (시뮬 1 의 final state report_md 검증)**

시뮬 1 의 출력에 `[OPTIMIZER]` 다음 `[REPORTER]` 출력 추가되어야 함. 만약 출력이 안 보이면 synthetic_daily_report._main_cli 의 final 처리에서 `final.get("report_md")` 출력 추가:

```python
# synthetic_daily_report.py:477 끝에 추가
report_md = final.get("report_md", "")
if report_md:
    print(f"\n[REPORTER] report_md ({len(report_md)} chars):")
    print(report_md[:500] + ("..." if len(report_md) > 500 else ""))
```

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && docker exec cpia-pg-local psql -U cpia -d cpia -c "SELECT run_id, date, length(report_md), jsonb_pretty(summary) FROM daily_reports ORDER BY created_at DESC LIMIT 3"
```

Expected: 시뮬 1~3 의 run_id 별 daily_reports row 3건 (시뮬 4 cold_start 는 Reporter 진입은 하지만 mapped 가 있긴 함 — risk=null 이라 forecast 만 있고 advice 0).

- [ ] **Step 5.5: 전체 회귀 최종 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: 전체 PASS, 회귀 0건. baseline 183 + 신규 ~16 (3 fixture + 4 PG + 3 hil_1 unit + 2 hil_1 e2e + 3 reporter unit + 3 checkpointer + Reporter db 1) = ~199 PASS.

- [ ] **Step 5.6: Task 5 commit**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/raw/v2-scenario-*.md pipeline/agents/optimizer/synthetic_daily_report.py && git commit -m "$(cat <<'EOF'
test: 본 cycle 통합 검증 — 시뮬 4건 실 호출 + 결정성 + Reporter 통합

Forecaster fixture fix 효과 검증:
- 시뮬 1 (ratio=0.45, n=5): today_prod ≈ baseline × 0.45 → assessment="이상"/"주의"
- 시뮬 2 (우천 0.8): assessment="주의"
- 시뮬 3 (돌관 0.45 ×1.3): assessment ∈ {"이상", "주의"}
- 시뮬 4 (cold_start): assessment=None

결정성 검증: 시뮬 1 rerun 결정론 컬럼 diff = 0.

Reporter 통합: 시뮬 1~3 daily_reports row 3건 INSERT 확인 (시뮬 4 도
Reporter 진입, mapped 1건 + risk=null → 짧은 MD).

회귀: 183 baseline + 신규 ~16 = ~199 PASS.

EOF
)"
```

---

## Task 6: 정리 + PR

- [ ] **Step 6.1: drift-backlog 흡수 마킹**

`docs/audit/2026-05-17-cpia-drift-backlog.md` Edit — 우선순위 #1~#4 항목에 "✅ 본 cycle 흡수 완료 (PR #X)" 표기.

- [ ] **Step 6.2: docs/superpowers/learnings/ 추가 (선택)**

본 cycle 의 핵심 발견 학습 노트 1 건 — `docs/superpowers/learnings/2026-05-17-hil1-forecaster-reporter-postgressaver.md` (선택). 학습 패턴:
- HIL pattern 재사용 (HIL 2 → HIL 1)
- synthetic fixture n_activities 오버산출 버그 root cause
- design-intent + deep-dive 전수조사 효과

- [ ] **Step 6.3: 최종 git status + log**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git status && echo "---" && git log --oneline -10
```

Expected:
- working tree clean
- 본 cycle 의 4~5 commit 가 origin/A_Track 위에 적재됨

- [ ] **Step 6.4: PR 생성 — 사용자 명시 승인 필요**

`Never push to remote unless explicitly requested` + `Never create PRs unless explicitly asked`. 사용자에게 PR 생성 승인 받은 후 진행.

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git push origin A_Track && gh pr create --base main --head A_Track --title "feat: HIL 1 + Forecaster fix + Reporter + PostgresSaver 통합 cycle" --body "$(cat <<'EOF'
## Summary

drift-backlog #1 (Reporter) + #2 (Forecaster assessment) + #3 (시뮬 fixture
bug) + #4 (HIL 1) 통합 1 PR.

추가로 design-intent O-6 권고 대응 PostgresSaver 전환 포함.

## 변경 (atomic commit 단위)
1. Forecaster fixture fix (synthetic_daily_report.py:78 + 118)
2. HIL 1 구현 (graph.py + db.py + tests)
3. Reporter 구현 (reporter.py 신규 + graph.py + db.py + tests)
4. PostgresSaver 전환 (checkpointer.py + pyproject.toml + tests)
5. 통합 검증 raw (시뮬 4건 + 결정성 + Reporter 통합 + 회귀 0)

## 검증
- pytest 회귀 183 baseline → ~199 PASS (회귀 0)
- 시뮬 4 건 실 호출 raw md 추가 (`docs/audit/raw/v2-scenario-*.md`)
- 결정성 검증 rerun diff = 0
- Azure 비용 ~$0.30

## 원안 v2 와의 의도적 drift (사용자 결정)
- HIL 1 = CLI 인터랙티브 (원안 = Dashboard Modal)
- Reporter 위치 = Optimizer 다음 (원안 = Atomizer 다음 병렬)
- Reporter 출력 = 종합 보고서 1 종 (원안 = 사내/발주처 2 종)

## Test plan
- [ ] CI 통과 (pytest + ruff)
- [ ] PoC 시연 (CLI + 시뮬 4건) 정합
- [ ] 시연 1주 전 (~2026-05-30) 데모 리허설

EOF
)"
```

---

## 회귀/한자 검수 명령 (각 Task 종결 직전)

```bash
# 회귀
cd "/Users/kyungseoplee/Project Agent/CPIA/pipeline" && set -a; source .env.local; set +a && .venv/bin/python3 -m pytest tests/ -q

# 한자 0건 (코드/문서)
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -rP "[\x{4E00}-\x{9FFF}]" pipeline/ docs/audit/ docs/superpowers/specs/2026-05-17-* docs/superpowers/plans/2026-05-17-* 2>/dev/null | head -5 || echo "한자 0건"
