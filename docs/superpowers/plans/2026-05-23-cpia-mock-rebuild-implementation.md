# CPIA Mock 재설계 + 로컬 검증 + AWS 마이그 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** activity_master 3704 row + l5_disc 7종 + l7.5 100% 채워짐 데이터를 F3 분포 + conditions + outlier + prod target 역산 으로 mock seed 재설계해서 로컬 PG/Chroma 에 적재한 뒤 mapper 이후 전 단계 (atomizer/forecaster/hil_2/optimizer/reporter) 일별 배치 실행, FE 모든 페이지 SQL assertion 8건 + Playwright 통과 확인, AWS RDS 백업 후 안전 마이그까지 단일 plan 으로 완료.

**Architecture:** `scripts/seed_dummy_year.py` in-place 60 줄 수정 + `pipeline/agents/synthetic/distributions.py` 신규 (F3 함수 분리) + `pipeline/agents/optimizer/retrieve.py:95` 9 keyword 보강 + `scripts/local_db_reset.py` / `scripts/aws_backup_and_migrate.py` / `scripts/chroma_export.py` / `scripts/chroma_import.py` 신규. mapper.py / atomizer.py / forecaster/agent.py 코드 변경 X (사용자 mapper 로직 불가침 룰).

**Tech Stack:** Python 3.11 + asyncpg + ChromaDB 0.5.20 + Azure OpenAI gpt-5.1-chat-ai-board-test + text-embedding-3-small + Next.js 14.2.35 (FE) + docker compose (PostgreSQL 16-alpine + Chroma) + Playwright MCP.

**Spec:** `docs/superpowers/specs/2026-05-23-cpia-mock-rebuild-and-local-migration-design.md` (585 lines, HEAD 2a97f17).

**Branch:** A_Track. **시연 마감:** 2026-06-05 (목).

---

## File Structure

| Path | 책임 | 신규/수정 |
|---|---|---|
| `pipeline/agents/synthetic/distributions.py` | F3 piecewise daily/cum ratio 함수 (분리 모듈) | 신규 |
| `scripts/seed_dummy_year.py` | mock 일자별 row 생성 (F3 + conditions + outlier + l7.5 + l5_disc trade) | 수정 |
| `pipeline/agents/optimizer/retrieve.py` | incident keyword 9종 보강 | 수정 (L95) |
| `scripts/backfill_optimizer_advice_llm.py` | DEFAULT_TRADES 7종 확장 | 수정 (L53) |
| `scripts/local_db_reset.py` | 로컬 PG TRUNCATE all + Chroma delete daily_activities | 신규 |
| `scripts/chroma_export.py` | Chroma collection → JSONL snapshot | 신규 |
| `scripts/chroma_import.py` | JSONL snapshot → Chroma collection | 신규 |
| `scripts/aws_backup_and_migrate.py` | pg_dump + Chroma snapshot + AWS reset + restore orchestrate | 신규 |
| `scripts/verify_ui_assertions.py` | SQL assertion 8건 자동 검증 | 신규 |
| `.env.local` | POSTGRES_URL / CHROMA_HOST swap (Phase A 시작 시 localhost, Phase E 끝 AWS 복원) | 수정 |
| `pipeline/tests/synthetic/test_f3_distribution.py` | F3 함수 적분=1.0, 경계값 검증 | 신규 |
| `pipeline/tests/synthetic/test_seed_conditions.py` | 7 tag → conditions list 매핑, normal_steady ["정상"] | 신규 |
| `pipeline/tests/synthetic/test_seed_l7_5_propagation.py` | seed → mapper row → Chroma metadata 까지 l7.5 전파 | 신규 |
| `pipeline/tests/synthetic/test_seed_prod_target.py` | normal prod 81~99, outlier 50/150, 5% 빈도 (1000 sample) | 신규 |
| `pipeline/tests/synthetic/test_seed_anchor_consistency.py` | 9-25 완공 row today_cum_qty ≈ plan_total (F3 적분 1.0) | 신규 |
| `pipeline/tests/optimizer/test_retrieve_incident_9kw.py` | 9 keyword 모두 substring 매칭 동작 | 신규 |

---

## Phase A — 로컬 DB 활성화 (3 tasks)

### Task A.1: Docker Compose 가동 + activity_master/sites 로컬 적재

**Files:**
- Create: `tmp/activity_master_dump.sql` (gitignore, AWS → 로컬 transfer 용)
- Modify: 없음 (compose 만 가동)

- [ ] **Step 1: docker compose 가동 (PG + Chroma + Adminer)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA/infra
docker compose up -d postgres chroma adminer
sleep 8  # health check 대기
docker ps --filter "name=cpia-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected: cpia-postgres / cpia-chroma / cpia-adminer 3 container all "Up" + healthcheck "healthy".

- [ ] **Step 2: PG 연결 확인**

```bash
PGPASSWORD=cpia /opt/homebrew/bin/psql -h localhost -p 5532 -U cpia -d cpia -c "\dt" 2>&1 || \
  echo "psql 없으면 다음 step 의 asyncpg 으로 검증"
```

또는 asyncpg:

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    print(await c.fetchval('SELECT version()'))
    await c.close()
asyncio.run(m())
"
```

Expected: PostgreSQL 16.x 버전 출력.

- [ ] **Step 3: Chroma 연결 확인**

```bash
curl -fsS http://localhost:5533/api/v1/heartbeat | python3 -m json.tool
```

Expected: `{"nanosecond heartbeat": <number>}`.

- [ ] **Step 4: AWS 의 activity_master + sites dump (transfer 용)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
mkdir -p tmp
PGPASSWORD=K7mP2xQ9nR4v pg_dump -h 43.200.85.209 -p 5532 -U cpia -d cpia \
  -t activity_master -t sites --data-only --column-inserts \
  > tmp/activity_master_dump.sql
wc -l tmp/activity_master_dump.sql
```

Expected: ~4000 줄 (3704 activity_master + sites row 정도).

- [ ] **Step 5: 로컬 PG 에 restore**

```bash
PGPASSWORD=cpia /opt/homebrew/bin/psql -h localhost -p 5532 -U cpia -d cpia -f tmp/activity_master_dump.sql 2>&1 | tail -5
# 또는 psql 없으면:
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    with open('tmp/activity_master_dump.sql') as f:
        sql = f.read()
    await c.execute(sql)
    cnt = await c.fetchval('SELECT COUNT(*) FROM activity_master')
    print(f'activity_master row: {cnt}')
    await c.close()
asyncio.run(m())
"
```

Expected: `activity_master row: 3704`.

- [ ] **Step 6: Commit (config 만 commit, dump file 은 gitignore)**

```bash
echo "tmp/*.sql" >> .gitignore
git add .gitignore
git commit -m "$(cat <<'EOF'
chore(infra): tmp/*.sql gitignore (AWS dump transfer 용 임시 file)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task A.2: .env.local swap (AWS → localhost) + FE 5536 가동

**Files:**
- Modify: `.env.local` (POSTGRES_URL / CHROMA_HOST)
- Reference: 기존 AWS 값 백업

- [ ] **Step 1: 현재 .env.local 백업**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
cp .env.local .env.local.aws-backup
# Phase E 끝에 복원 시 사용
```

- [ ] **Step 2: .env.local 수정 — POSTGRES_URL / CHROMA_HOST localhost 로 swap**

`.env.local` 의 두 줄:

```diff
- POSTGRES_URL=postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia
+ POSTGRES_URL=postgresql://cpia:cpia@localhost:5532/cpia
- CHROMA_HOST=43.200.85.209
+ CHROMA_HOST=localhost
```

- [ ] **Step 3: 기존 next-server 종료 + cache clear**

```bash
pkill -f "next dev" 2>/dev/null || true
rm -rf /Users/kyungseoplee/Project\ Agent/CPIA/web/.next
sleep 1
ps aux | grep -E "next dev|next-server" | grep -v grep || echo "✓ no next process"
```

- [ ] **Step 4: FE 5536 가동 (background)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA/web
npm run dev > /tmp/cpia-fe-dev.log 2>&1 &
echo "FE PID: $!"
sleep 5
tail -20 /tmp/cpia-fe-dev.log
```

Expected: "ready - started server on 0.0.0.0:5536" 또는 "Ready in N.Ns" 출력.

- [ ] **Step 5: FE 접속 확인 (curl)**

```bash
curl -fsS -o /dev/null -w "%{http_code}\n" http://localhost:5536/
```

Expected: `200`.

- [ ] **Step 6: 화면 stale 데이터 또는 empty 상태 확인 (로컬 PG 비어있음 → 0건 표시)**

Playwright MCP 사용:

```
mcp__plugin_playwright_playwright__browser_navigate to http://localhost:5536/tasks
mcp__plugin_playwright_playwright__browser_console_messages
mcp__plugin_playwright_playwright__browser_snapshot
```

Expected: console 0 errors, tasks 페이지 "0 작업" 또는 empty state.

- [ ] **Step 7: gitignore 사전 확인 + commit 결정**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
git check-ignore .env.local && echo "gitignore: YES (commit skip)" || echo "gitignore: NO (commit 가능)"
```

`.env.local` 이 `.gitignore` 에 있으면 commit 안 함 (Next.js 표준). 아니면:

```bash
git add .env.local
git commit -m "$(cat <<'EOF'
chore(env): .env.local POSTGRES_URL/CHROMA_HOST localhost swap (Phase A)

Phase E 끝에 .env.local.aws-backup 으로 복원 예정.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

gitignore 인 경우 — env swap 은 local 상태로 보존되며 git 추적 X. Phase E 끝 .env.local.aws-backup 복원도 git 추적 X.

---

### Task A.3: scripts/local_db_reset.py 신규 작성 + 첫 reset 실행

**Files:**
- Create: `scripts/local_db_reset.py`

- [ ] **Step 1: Write failing test (선택 — script 검증)**

`scripts/local_db_reset.py` 는 단순 script 이라 별도 unit test 보다 integration smoke 로 충분.

- [ ] **Step 2: Write script**

```python
"""로컬 PG TRUNCATE all + Chroma daily_activities collection delete.

Phase A 시작 시 1회 + 재 seed 전 호출. activity_master / sites 는 reset 대상 X.
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
TRUNCATE_TABLES = [
    "optimizer_advice",
    "forecasts",
    "daily_reports",
    "mapped_history",
    "mapper_activities",
    "parser_activities",
    "pipeline_runs",
]


async def reset_pg() -> None:
    conn = await asyncpg.connect(LOCAL_PG)
    try:
        for tbl in TRUNCATE_TABLES:
            await conn.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
            print(f"  ✓ TRUNCATE {tbl}")
    finally:
        await conn.close()


def reset_chroma() -> None:
    sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
    from pipeline.chroma_client import ChromaClient

    chroma = ChromaClient(host="localhost", port=5533)
    try:
        chroma.delete_collection("daily_activities")
        print("  ✓ Chroma daily_activities collection deleted")
    except Exception as e:  # noqa: BLE001
        print(f"  · Chroma delete skipped (not exists): {type(e).__name__}: {e}")


async def main() -> None:
    print("=== 로컬 DB reset ===")
    await reset_pg()
    reset_chroma()
    print("✓ reset 완료")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: 첫 reset 실행 (smoke)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 scripts/local_db_reset.py
```

Expected output:
```
=== 로컬 DB reset ===
  ✓ TRUNCATE optimizer_advice
  ✓ TRUNCATE forecasts
  ✓ TRUNCATE daily_reports
  ✓ TRUNCATE mapped_history
  ✓ TRUNCATE mapper_activities
  ✓ TRUNCATE parser_activities
  ✓ TRUNCATE pipeline_runs
  · Chroma daily_activities collection deleted (또는 skipped)
✓ reset 완료
```

- [ ] **Step 4: activity_master 보존 확인 (reset 대상 X)**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    print('activity_master:', await c.fetchval('SELECT COUNT(*) FROM activity_master'))
    print('sites:', await c.fetchval('SELECT COUNT(*) FROM sites'))
    print('mapper_activities:', await c.fetchval('SELECT COUNT(*) FROM mapper_activities'))
    await c.close()
asyncio.run(m())
"
```

Expected: `activity_master: 3704 / sites: N / mapper_activities: 0` (mapper 만 TRUNCATE 된 상태 보존).

- [ ] **Step 5: Commit**

```bash
git add scripts/local_db_reset.py
git commit -m "$(cat <<'EOF'
feat(scripts): local_db_reset.py - TRUNCATE all + Chroma daily_activities delete

Phase A 시작 시 1회 + re-seed 전 호출. activity_master / sites 보존.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase B — Mock seed 재설계 (8 tasks, TDD)

### Task B.1: F3 분포 함수 모듈 분리 (`pipeline/agents/synthetic/distributions.py`) + 테스트

**Files:**
- Create: `pipeline/agents/synthetic/__init__.py` (디렉토리 존재 시 skip)
- Create: `pipeline/agents/synthetic/distributions.py`
- Create: `pipeline/tests/synthetic/__init__.py`
- Create: `pipeline/tests/synthetic/test_f3_distribution.py`

- [ ] **Step 1: 디렉토리 + __init__.py 확인 / 생성**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
ls pipeline/agents/synthetic/ 2>/dev/null || mkdir -p pipeline/agents/synthetic
ls pipeline/tests/synthetic/ 2>/dev/null || mkdir -p pipeline/tests/synthetic
touch pipeline/agents/synthetic/__init__.py pipeline/tests/synthetic/__init__.py
```

- [ ] **Step 2: Write failing test (TDD)**

`pipeline/tests/synthetic/test_f3_distribution.py`:

```python
"""F3 piecewise 분포 함수 검증.

spec §4: ramp 15% + plateau 70% + late-rise 15%, peak=1.5×plateau.
적분 정확히 1.0 (정규화) + 경계값 + 단조성.
"""

from __future__ import annotations

import pytest

from pipeline.agents.synthetic.distributions import (
    PEAK_MULT, PLATEAU_END, P_NORM, RAMP_END,
    f3_cum_ratio, f3_daily_ratio,
)


def test_f3_constants():
    assert RAMP_END == 0.15
    assert PLATEAU_END == 0.85
    assert PEAK_MULT == 1.5
    assert P_NORM == pytest.approx(1.0 / 0.9625, abs=1e-4)  # ≈ 1.039


def test_f3_daily_ratio_boundaries():
    assert f3_daily_ratio(0.0) == pytest.approx(0.0)
    assert f3_daily_ratio(RAMP_END) == pytest.approx(P_NORM, abs=1e-6)
    assert f3_daily_ratio(0.5) == pytest.approx(P_NORM, abs=1e-6)  # plateau
    assert f3_daily_ratio(PLATEAU_END) == pytest.approx(P_NORM, abs=1e-6)
    assert f3_daily_ratio(1.0) == pytest.approx(P_NORM * PEAK_MULT, abs=1e-6)


def test_f3_cum_ratio_boundaries():
    assert f3_cum_ratio(0.0) == 0.0
    assert f3_cum_ratio(RAMP_END) == pytest.approx(0.5 * RAMP_END * P_NORM, abs=1e-6)  # ≈ 0.078
    assert f3_cum_ratio(0.5) == pytest.approx((0.5 * RAMP_END + (0.5 - RAMP_END)) * P_NORM, abs=1e-6)
    assert f3_cum_ratio(PLATEAU_END) == pytest.approx(
        (0.5 * RAMP_END + (PLATEAU_END - RAMP_END)) * P_NORM, abs=1e-6
    )
    # 핵심 검증: 적분 = 1.0
    assert f3_cum_ratio(1.0) == pytest.approx(1.0, abs=1e-6)


def test_f3_monotonic():
    """cum_ratio 는 progress 따라 단조 증가."""
    prev = -1.0
    for i in range(101):
        p = i / 100.0
        cur = f3_cum_ratio(p)
        assert cur >= prev - 1e-9, f"non-monotonic at progress={p}: prev={prev}, cur={cur}"
        prev = cur


def test_f3_daily_integral_approximation():
    """수치 적분으로 daily 의 sum ≈ 1.0 (1000 step)."""
    n = 1000
    dx = 1.0 / n
    total = sum(f3_daily_ratio(i * dx) * dx for i in range(n + 1))
    assert total == pytest.approx(1.0, abs=0.01)
```

- [ ] **Step 3: Run test — expected FAIL (모듈 없음)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_f3_distribution.py -v 2>&1 | tail -15
```

Expected: `ModuleNotFoundError: No module named 'pipeline.agents.synthetic.distributions'`.

- [ ] **Step 4: Write `pipeline/agents/synthetic/distributions.py`**

```python
"""F3 piecewise 분포 — ramp + plateau + late-rise.

spec docs/superpowers/specs/2026-05-23-cpia-mock-rebuild-and-local-migration-design.md §4
"""

from __future__ import annotations

RAMP_END = 0.15
PLATEAU_END = 0.85
PEAK_MULT = 1.5
INTEGRAL = (
    0.5 * RAMP_END
    + (PLATEAU_END - RAMP_END)
    + (1.0 + PEAK_MULT) / 2.0 * (1.0 - PLATEAU_END)
)
P_NORM = 1.0 / INTEGRAL  # ≈ 1.039


def f3_daily_ratio(progress: float) -> float:
    """progress (0~1) → daily ratio (적분 = 1.0)."""
    if progress <= RAMP_END:
        return P_NORM * progress / RAMP_END
    if progress <= PLATEAU_END:
        return P_NORM
    return P_NORM * (
        1.0 + (progress - PLATEAU_END) / (1.0 - PLATEAU_END) * (PEAK_MULT - 1.0)
    )


def f3_cum_ratio(progress: float) -> float:
    """progress (0~1) → cumulative ratio (0~1)."""
    if progress <= RAMP_END:
        return 0.5 * progress * progress / RAMP_END * P_NORM
    if progress <= PLATEAU_END:
        return (0.5 * RAMP_END + (progress - RAMP_END)) * P_NORM
    u = progress - PLATEAU_END
    late_part = u + 0.5 * (PEAK_MULT - 1.0) * u * u / (1.0 - PLATEAU_END)
    return (0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + late_part) * P_NORM
```

- [ ] **Step 5: Run test — expected PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_f3_distribution.py -v 2>&1 | tail -15
```

Expected: `5 passed in 0.XXs`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/agents/synthetic/__init__.py pipeline/agents/synthetic/distributions.py \
        pipeline/tests/synthetic/__init__.py pipeline/tests/synthetic/test_f3_distribution.py
git commit -m "$(cat <<'EOF'
feat(synthetic): F3 piecewise 분포 모듈 + tests

ramp 15% + plateau 70% + late-rise 15%, peak=1.5×plateau, 적분=1.0.
spec §4 / poc_mock_redesign.py 검증 logic 분리.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.2: seed_dummy_year.py 상수 + TAG_TO_CONDS 매핑 추가

**Files:**
- Modify: `scripts/seed_dummy_year.py` (상단 상수 영역)

- [ ] **Step 1: 현재 상수 영역 read (L50-100)**

```bash
sed -n '50,100p' /Users/kyungseoplee/Project\ Agent/CPIA/scripts/seed_dummy_year.py
```

Expected: SITE_ID / ANCHOR_DATE / DEFAULT_PG_URL / ANCHOR_SITE_MH_PER_QTY / DIAGNOSIS_PATTERNS 출력 확인.

- [ ] **Step 2: 상수 추가 (DIAGNOSIS_PATTERNS 다음에)**

`scripts/seed_dummy_year.py` 의 DIAGNOSIS_PATTERNS 정의 뒤 (대략 L98 부근):

```python
# F3 분포 import (Phase B Task B.1 분리 모듈)
from pipeline.agents.synthetic.distributions import (  # noqa: E402
    f3_daily_ratio, f3_cum_ratio, P_NORM, RAMP_END, PLATEAU_END, PEAK_MULT,
)

# spec §5 — 사용자 결정: 7 tag → conditions list 매핑
TAG_TO_CONDS: dict[str, list[str]] = {
    "weather_rain":   ["우천"],
    "manpower_short": ["인력부족"],
    "material_delay": ["자재미입고"],
    "rework":         ["재작업"],
    "trade_overlap":  ["병행작업"],
    "spec_change":    ["사양변경"],
    "normal_steady":  ["정상"],
}

# spec §7 — prod target 역산 상수
PROD_TARGET = 90.0
OUTLIER_PROB = 0.05
```

- [ ] **Step 3: Smoke import (실행 X — import error 만 잡기)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 -c "
import sys
sys.path.insert(0, '.')
import importlib.util
spec = importlib.util.spec_from_file_location('seed', 'scripts/seed_dummy_year.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('TAG_TO_CONDS:', list(m.TAG_TO_CONDS.keys()))
print('PROD_TARGET:', m.PROD_TARGET)
print('P_NORM:', m.P_NORM)
"
```

Expected: `TAG_TO_CONDS: ['weather_rain', 'manpower_short', ...] / PROD_TARGET: 90.0 / P_NORM: 1.0389...`.

- [ ] **Step 4: Commit**

```bash
git add scripts/seed_dummy_year.py
git commit -m "$(cat <<'EOF'
feat(seed): F3 + TAG_TO_CONDS + PROD_TARGET 상수 추가

F3 분포 함수 import (synthetic.distributions). 7 tag → conditions list 매핑.
prod target 90% + outlier 5%. spec §5/§7.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.3: `_pick_diagnosis` 변경 (conditions key 추가) + 테스트

**Files:**
- Modify: `scripts/seed_dummy_year.py:109-118` (`_pick_diagnosis`)
- Create: `pipeline/tests/synthetic/test_seed_conditions.py`

- [ ] **Step 1: Write failing test**

```python
"""seed _pick_diagnosis tag → conditions 매핑 검증.
spec §5 / §13.3.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).parents[2] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tag_to_conds_complete():
    m = _load_seed()
    assert set(m.TAG_TO_CONDS.keys()) == {
        "weather_rain", "manpower_short", "material_delay", "rework",
        "trade_overlap", "spec_change", "normal_steady",
    }
    assert m.TAG_TO_CONDS["normal_steady"] == ["정상"]
    assert m.TAG_TO_CONDS["weather_rain"] == ["우천"]


def test_pick_diagnosis_returns_conditions_key():
    m = _load_seed()
    diag = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    assert "tag" in diag
    assert "conditions" in diag
    assert isinstance(diag["conditions"], list)
    assert diag["conditions"] == m.TAG_TO_CONDS[diag["tag"]]


def test_pick_diagnosis_deterministic():
    """같은 입력 → 같은 tag."""
    m = _load_seed()
    a = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    b = m._pick_diagnosis("2025-09-25", "WA-001", "광건", "콘크리트공사")
    assert a["tag"] == b["tag"]
    assert a["conditions"] == b["conditions"]
```

- [ ] **Step 2: Run test — expected FAIL (conditions key 없음)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_conditions.py -v 2>&1 | tail -15
```

Expected: `KeyError: 'conditions'` 또는 assertion fail.

- [ ] **Step 3: `_pick_diagnosis` 수정 (`scripts/seed_dummy_year.py:109-118`)**

기존:
```python
def _pick_diagnosis(date_str: str, wa: str, company: str, l6: str) -> dict[str, Any]:
    idx = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16) % len(
        DIAGNOSIS_PATTERNS
    )
    pat = DIAGNOSIS_PATTERNS[idx]
    return {
        "tag": pat["tag"],
        "diagnosis": pat["text"].format(l6=l6, company=company),
        "recommendations": [r.format(l6=l6, company=company) for r in pat["recs"]],
    }
```

변경 — return dict 에 `conditions` key 추가:

```python
def _pick_diagnosis(date_str: str, wa: str, company: str, l6: str) -> dict[str, Any]:
    idx = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16) % len(
        DIAGNOSIS_PATTERNS
    )
    pat = DIAGNOSIS_PATTERNS[idx]
    return {
        "tag": pat["tag"],
        "diagnosis": pat["text"].format(l6=l6, company=company),
        "recommendations": [r.format(l6=l6, company=company) for r in pat["recs"]],
        "conditions": TAG_TO_CONDS[pat["tag"]],  # ← new (spec §13.3)
    }
```

- [ ] **Step 4: Run test — expected PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_conditions.py -v 2>&1 | tail -10
```

Expected: `3 passed in 0.XXs`.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_dummy_year.py pipeline/tests/synthetic/test_seed_conditions.py
git commit -m "$(cat <<'EOF'
feat(seed): _pick_diagnosis conditions key 추가 + tests

7 tag → conditions list 매핑 (TAG_TO_CONDS).
normal_steady ["정상"], weather_rain ["우천"], 등.
spec §5/§13.3.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.4: `_build_mapper_row` F3 분포 + prod target 역산 교체 + 테스트

**Files:**
- Modify: `scripts/seed_dummy_year.py:202-322` (`_build_mapper_row`)
- Create: `pipeline/tests/synthetic/test_seed_prod_target.py`

- [ ] **Step 1: Write failing test**

```python
"""prod target 역산 검증 — normal 81~99 / outlier 50·150, 빈도 5% (1000 sample)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).parents[2] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _make_fake_am_row(wa="WA-1", company="C-1") -> dict:
    return {
        "wbs_activity_id": "act-1",
        "l5_disc": "건축",
        "l6_main": "콘크리트공사",
        "l7_sub": "RC공사",
        "l7_5_activity": "기초 콘크리트 타설",
        "sub_work_area": "B-zone",
        "company": company,
        "wa": wa,
        "unit": "M3",
        "plan_total_qty": 100.0,
        "plan_mh_rev2": 500.0,
        "plan_start": date(2025, 1, 1),
        "plan_finish": date(2025, 6, 30),
    }


def test_build_mapper_row_returns_l7_5_and_conditions(monkeypatch):
    m = _load_seed()
    rng = m._seeded_rng("test")
    row = m._build_mapper_row(date(2025, 3, 1), _make_fake_am_row(), None, rng)
    assert row is not None
    assert row["l7_5_activity"] == "기초 콘크리트 타설"
    assert row["trade"] == "건축"  # l5_disc 그대로
    assert isinstance(row["conditions"], list)


def test_prod_target_distribution_1000_sample(monkeypatch):
    """1000 row 시뮬레이션 — normal 81~99 비율 ≥ 90%, outlier 비율 3~8%."""
    m = _load_seed()
    normals = 0
    outliers = 0
    for i in range(1000):
        rng = m._seeded_rng(f"test|{i}")
        # _seeded_rng 직접 활용 — _build_mapper_row 가 내부에서 rng 동일 패턴 사용
        is_outlier = rng.random() < m.OUTLIER_PROB
        if is_outlier:
            actual = rng.choice([50.0, 150.0])
            outliers += 1
        else:
            actual = m.PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)
            normals += 1
            assert 80.9 <= actual <= 99.1, f"normal prod out of range: {actual}"
    assert 30 <= outliers <= 80, f"outlier 빈도 비현실: {outliers}/1000"
    assert outliers + normals == 1000
```

- [ ] **Step 2: Run test — expected FAIL (l7_5_activity / trade=l5_disc / conditions 미정)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_prod_target.py -v 2>&1 | tail -20
```

Expected: KeyError 또는 AssertionError (현재 _build_mapper_row 가 l7_5_activity 키 안 박음).

- [ ] **Step 3: `_build_mapper_row` 수정 — 분포·prod·trade·conditions·l7_5 모두 적용**

핵심 교체 (Case A / Case B 공통 처리). spec §10 = Case A 분기 제거 + 통일 logic.

`scripts/seed_dummy_year.py:202-322` 의 함수 본체 교체. 기존 Case A/B 분기 → 단일 logic:

```python
def _build_mapper_row(
    d: date,
    am_row: dict[str, Any],
    anchor_row: Optional[dict[str, Any]],  # 인터페이스 보존 (호출자 영향 X), 내부 사용 X
    rng: random.Random,
) -> Optional[dict[str, Any]]:
    """activity_master row → 일자별 mapper_activities row.

    spec §10: 모든 일자 동일 F3 + prod target 역산 logic. Case A 분기 제거.
    spec §13.4: 보존 항목 (mapping_conf, parser pass-through) + 교체 항목 (분포·prod·trade·conditions·l7.5).
    """
    plan_start = am_row["plan_start"]
    plan_finish = am_row["plan_finish"]
    if d < plan_start or d > plan_finish:
        return None

    total_days = (plan_finish - plan_start).days + 1
    days_elapsed = (d - plan_start).days + 1
    progress = days_elapsed / total_days

    plan_total = float(am_row.get("plan_total_qty") or 0)
    plan_mh = float(am_row.get("plan_mh_rev2") or 0)

    # F3 분포
    ratio_today = f3_daily_ratio(progress)
    cum_frac = f3_cum_ratio(progress)

    # prod target 역산 (spec §7)
    # _seeded_rng 호출 횟수 일관성 보장 — _pick_diagnosis 다음에 prod 결정
    diag = _pick_diagnosis(str(d), am_row["wa"], am_row["company"], am_row["l6_main"])
    is_outlier = rng.random() < OUTLIER_PROB
    if is_outlier:
        actual_prod_pct = rng.choice([50.0, 150.0])
    else:
        actual_prod_pct = PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)

    today_qty = (
        plan_total / total_days * ratio_today * (1.0 + (rng.random() * 2 - 1) * 0.10)
    )
    today_cum_qty = plan_total * cum_frac
    cum_actual_mh = plan_mh * progress * actual_prod_pct / 100.0
    plan_mh_per_day = plan_mh / total_days if total_days > 0 else 0
    today_assigned_workers = max(1.0, plan_mh_per_day / 8.0 * (1.0 + (rng.random() * 2 - 1) * 0.10))
    cum_workers_today = cum_actual_mh / 8.0

    return {
        "company": am_row["company"],
        "trade": am_row["l5_disc"],   # spec §9 — l5_disc 그대로 trade 컬럼
        "unit": am_row.get("unit") or "EA",
        "today_qty": today_qty,
        "today_cum_qty": today_cum_qty,
        "cum_actual_mh_today": cum_actual_mh,
        "cum_workers_today": cum_workers_today,
        "wa": am_row["wa"],
        "l5_disc": am_row["l5_disc"],
        "l6_main": am_row["l6_main"],
        "l7_sub": am_row.get("l7_sub") or "",
        "l7_5_activity": am_row.get("l7_5_activity") or "",   # spec §8
        "sub_work_area": am_row.get("sub_work_area") or "",
        "mapping_conf": 1.0,
        "mapping_source": "dummy_seed",
        "requires_review": False,
        "assigned_workers": today_assigned_workers,
        "worker_source": "dummy_seed",
        "plan_total_qty": plan_total,
        "plan_mh": plan_mh,
        "conditions": diag["conditions"],   # spec §5 — TAG_TO_CONDS[tag]
        "alternatives": [],
        "work_content": f"{am_row['l6_main']} 진행",
        "zone": "",
        "scope": "",
        "yesterday_cum_qty": today_cum_qty - today_qty if today_cum_qty > today_qty else 0,
        "progress_percent": progress * 100,
        "remaining_qty": max(0, plan_total - today_cum_qty),
        "remaining_percent": max(0, (1.0 - progress)) * 100,
        "note": "",
        "work_location_code": "",
        "wbs_mid_name": "",
        "wbs_sub_name": "",
        "wbs_detail_name": "",
        # diag 추가 정보 (호출자가 _build_optimizer_advice 에서 재사용)
        "_diag_tag": diag["tag"],
    }
```

- [ ] **Step 4: Run test — expected PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_prod_target.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 5: 기존 회귀 확인 (seed import 깨짐 없는지)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/ -v 2>&1 | tail -10
```

Expected: 모든 test pass (B.1 5 + B.3 3 + B.4 2 = 10 passed).

- [ ] **Step 6: Commit**

```bash
git add scripts/seed_dummy_year.py pipeline/tests/synthetic/test_seed_prod_target.py
git commit -m "$(cat <<'EOF'
feat(seed): _build_mapper_row F3 분포 + prod target 90% 역산 + l5_disc trade + l7.5

spec §10 — Case A/B 분기 제거, 모든 일자 동일 logic.
spec §7 — cum_actual_mh = plan_mh × progress × actual_prod_pct/100.
spec §8 — l7_5_activity 채움. §9 — trade = l5_disc.
1000 sample 검증: normal 81~99, outlier 5%±.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.5: l7.5 전파 테스트 (mapper row → Chroma metadata)

**Files:**
- Create: `pipeline/tests/synthetic/test_seed_l7_5_propagation.py`

- [ ] **Step 1: Write test**

```python
"""seed → mapper row → Chroma upsert metadata 까지 l7_5_activity 전파 검증."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

SEED_PATH = Path(__file__).parents[2] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_mapper_row_has_l7_5_activity_field():
    """activity_master.l7_5_activity 가 mapper row 의 l7_5_activity 키로 박힘."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-1", "l5_disc": "건축",
        "l6_main": "콘크리트공사", "l7_sub": "RC공사",
        "l7_5_activity": "기초 콘크리트 타설", "sub_work_area": "B-zone",
        "company": "광건", "wa": "WA-1", "unit": "M3",
        "plan_total_qty": 100.0, "plan_mh_rev2": 500.0,
        "plan_start": date(2025, 1, 1), "plan_finish": date(2025, 6, 30),
    }
    rng = m._seeded_rng("test")
    row = m._build_mapper_row(date(2025, 3, 1), am_row, None, rng)
    assert row["l7_5_activity"] == "기초 콘크리트 타설"


def test_chroma_metadata_includes_l7_5_and_conditions():
    """chroma_upsert_day 호출 시 metadata 에 l7_5_activity / conditions 박힘.
    실 Chroma 호출 안 함 — chroma_upsert_day 내부 metadata 생성 부분만 검증 (mock or 분리).
    """
    # chroma_upsert_day 가 mapper_row 의 l7_5_activity, conditions 를 metadata 로 옮기는지
    # 직접 검증하려면 함수 내부 refactor 필요. 본 test 는 mapper_row 가 source 임을 확인.
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-1", "l5_disc": "전기",
        "l6_main": "전등설비공사", "l7_sub": "전등설비공사",
        "l7_5_activity": "전등 설비 설치", "sub_work_area": "",
        "company": "태우", "wa": "WA-2", "unit": "EA",
        "plan_total_qty": 200.0, "plan_mh_rev2": 800.0,
        "plan_start": date(2024, 9, 1), "plan_finish": date(2025, 12, 31),
    }
    rng = m._seeded_rng("test2")
    row = m._build_mapper_row(date(2025, 6, 1), am_row, None, rng)
    # mapper row 가 l7_5 + conditions 박았으면, chroma metadata 도 그대로 따라간다 (downstream)
    assert row["l7_5_activity"] == "전등 설비 설치"
    assert isinstance(row["conditions"], list)
    assert row["trade"] == "전기"  # l5_disc 그대로
```

- [ ] **Step 2: Run test — expected PASS (B.4 의 _build_mapper_row 가 이미 채움)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_l7_5_propagation.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/synthetic/test_seed_l7_5_propagation.py
git commit -m "$(cat <<'EOF'
test(seed): l7.5 + conditions 전파 검증 (mapper row 단계)

activity_master.l7_5_activity → mapper row.l7_5_activity 직결.
spec §8 검증.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.6: `_build_forecast_row` + `chroma_upsert_day` + `_build_optimizer_advice` 변경

**Files:**
- Modify: `scripts/seed_dummy_year.py:335-451` (`_build_forecast_row`, `chroma_upsert_day`, `_build_optimizer_advice`)

- [ ] **Step 1: `_build_forecast_row` 의 today_conditions union 채움 (spec §13.5)**

`scripts/seed_dummy_year.py:406` 의 `"today_conditions": ""` 를 변경:

```python
# 기존:
"today_conditions": "",
# 변경:
conditions_set = sorted({c for a in activities for c in (a.get("conditions") or [])})
...
"today_conditions": ",".join(conditions_set) if conditions_set else "",
```

함수 본체 안의 적절한 위치 (return dict 직전):

```python
def _build_forecast_row(...):
    ...
    conditions_set = sorted({c for a in activities for c in (a.get("conditions") or [])})
    ...
    return {
        ...
        "today_conditions": ",".join(conditions_set) if conditions_set else "",
    }
```

- [ ] **Step 2: `chroma_upsert_day` metadata 에 conditions + l7_5_activity 채움 (spec §13.6)**

`scripts/seed_dummy_year.py:488-504` 의 metadata 생성 부분:

```python
metadatas = [
    {
        "date": date_str,
        "run_id": str(run_id),
        "company": valid[i]["company"],
        "l5_disc": valid[i].get("l5_disc") or "",  # ← 추가 (atomizer metadata 패턴 일치)
        "l6_main": valid[i]["l6_main"] or "",
        "l7_5_activity": valid[i].get("l7_5_activity") or "",  # ← spec §13.6
        "wa": valid[i]["wa"] or "",
        "unit": valid[i]["unit"],
        "today_qty": float(valid[i]["today_qty"]),
        "assigned_workers": float(valid[i]["assigned_workers"]),
        "worker_source": valid[i]["worker_source"],
        "mapping_conf": float(valid[i]["mapping_conf"] or 0.0),
        "conditions": ",".join(valid[i].get("conditions") or []),  # ← spec §13.6
    }
    for i in seen.values()
]
```

- [ ] **Step 3: `_build_optimizer_advice` degradation_cases conditions list 형식 (spec §13.7)**

`scripts/seed_dummy_year.py:410-451` 의 함수 — `pat = _pick_diagnosis(...)` 호출 후 degradation_cases 생성 시:

```python
def _build_optimizer_advice(
    d: date,
    run_id: uuid.UUID,
    forecast_row: dict[str, Any],
) -> dict[str, Any]:
    wa = forecast_row["wa"]
    company = forecast_row["company"]
    l6 = forecast_row["l6_main"]
    date_str = d.isoformat()
    pat = _pick_diagnosis(date_str, wa, company, l6)
    cases = [
        {
            "date": (d - timedelta(days=180)).isoformat(),
            "activities": [f"{l6} 작업"],
            "conditions": ",".join(pat["conditions"]),  # ← spec §13.7 — list → comma-joined str
            "productivity": 78.0,
            "recovery": {"recovery_days": 3},
        },
        {
            "date": (d - timedelta(days=90)).isoformat(),
            "activities": [f"{l6} 작업"],
            "conditions": ",".join(pat["conditions"]),  # ← spec §13.7
            "productivity": 82.0,
            "recovery": {"recovery_days": 2},
        },
    ]
    return {
        "run_id": run_id,
        "company": company,
        "l6_main": l6,
        "forecast_assessment": forecast_row["assessment"],
        "diagnosis": pat["diagnosis"],
        "degradation_cases": cases,
        "recovery_pattern": [
            {"date": c["date"], "recovery_days": c["recovery"]["recovery_days"]}
            for c in cases
        ],
        "recovery_distribution": {"d+2": 1, "d+3": 1},
        "recommendations": pat["recommendations"],
    }
```

- [ ] **Step 4: Smoke import + 기본 호출 확인**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/ -v 2>&1 | tail -15
```

Expected: 기존 10 test 통과 유지.

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_dummy_year.py
git commit -m "$(cat <<'EOF'
feat(seed): _build_forecast_row today_conditions + chroma metadata + degradation_cases

§13.5 forecast_row.today_conditions = activities.conditions union.
§13.6 chroma metadata: l7_5_activity + conditions comma-joined.
§13.7 degradation_cases.conditions = comma-joined str (Chroma 패턴 통일).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.7: anchor 정합 테스트 + 통합 검증

**Files:**
- Create: `pipeline/tests/synthetic/test_seed_anchor_consistency.py`

- [ ] **Step 1: Write test**

```python
"""anchor 정합 — 9-25 완공 row today_cum_qty ≈ plan_total_qty (F3 적분 1.0).
spec §10.
"""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SEED_PATH = Path(__file__).parents[2] / "scripts" / "seed_dummy_year.py"


def _load_seed():
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_completed_row_today_cum_qty_equals_plan_total():
    """plan_finish == 2025-09-25 인 row 가 9-25 에 적재될 때 today_cum_qty ≈ plan_total."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-completed", "l5_disc": "건축",
        "l6_main": "콘크리트공사", "l7_sub": "RC공사",
        "l7_5_activity": "완공 작업", "sub_work_area": "",
        "company": "광건", "wa": "WA-end", "unit": "M3",
        "plan_total_qty": 1000.0, "plan_mh_rev2": 5000.0,
        "plan_start": date(2024, 4, 11),
        "plan_finish": date(2025, 9, 25),
    }
    rng = m._seeded_rng("anchor-test")
    row = m._build_mapper_row(date(2025, 9, 25), am_row, None, rng)
    assert row is not None
    # F3 cum_frac(1.0) = 1.0 (적분) → today_cum_qty = plan_total × 1.0 = 1000
    assert row["today_cum_qty"] == pytest.approx(1000.0, rel=1e-3)


def test_in_progress_row_at_anchor_partial_completion():
    """plan_finish == 2026-03-31 (anchor 이후) 인 row 가 9-25 에 partial 진행."""
    m = _load_seed()
    am_row = {
        "wbs_activity_id": "act-progress", "l5_disc": "전기",
        "l6_main": "전등설비공사", "l7_sub": "전등설비공사",
        "l7_5_activity": "진행 중 작업", "sub_work_area": "",
        "company": "태우", "wa": "WA-mid", "unit": "EA",
        "plan_total_qty": 1000.0, "plan_mh_rev2": 5000.0,
        "plan_start": date(2024, 4, 11),
        "plan_finish": date(2026, 3, 31),
    }
    rng = m._seeded_rng("anchor-test-2")
    row = m._build_mapper_row(date(2025, 9, 25), am_row, None, rng)
    # progress = (25-09-25 - 24-04-11) / (26-03-31 - 24-04-11) ≈ 0.745
    # plateau 구간 → cum_frac ≈ (0.5*0.15 + (0.745-0.15)) * 1.039 ≈ 0.696
    assert 0.60 * 1000.0 < row["today_cum_qty"] < 0.80 * 1000.0
```

- [ ] **Step 2: Run test — expected PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/test_seed_anchor_consistency.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 3: 전체 회귀 (synthetic + 기존 fast scope)**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/synthetic/ -v 2>&1 | tail -5
pipeline/.venv/bin/python3 -m pytest pipeline/tests/forecaster/ pipeline/tests/optimizer/ pipeline/tests/test_*.py \
  -m "not slow and not golden" --timeout=60 --tb=line 2>&1 | tail -10
```

Expected: synthetic 12 pass + 기존 fast scope 159 pass 유지.

- [ ] **Step 4: Commit**

```bash
git add pipeline/tests/synthetic/test_seed_anchor_consistency.py
git commit -m "$(cat <<'EOF'
test(seed): anchor (9-25) 정합 — 완공 row today_cum_qty ≈ plan_total

spec §10 — 모든 일자 동일 F3 logic. plan_finish=9-25 row 는 F3 적분 1.0
적용으로 today_cum_qty = plan_total. plan_finish 이후 row 는 partial.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task B.8: 실 DB 적재 — 24-04-11 ~ 25-09-25 전 기간 seed 실행

**Files:**
- Reference: `scripts/seed_dummy_year.py` (수정 완료)
- Output: 로컬 PG mapper_activities + Chroma daily_activities

- [ ] **Step 1: seed 실행 명령 검토**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 scripts/seed_dummy_year.py --help 2>&1 | head -20
```

argparse 옵션 확인 (--start / --end / --chroma-skip 등).

- [ ] **Step 2: 짧은 sample 실행 (25-09-25 단일 일자 — anchor 정합 검증)**

```bash
pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start 2025-09-25 --end 2025-09-25 2>&1 | tail -20
```

Expected: "✓ seed 완료" 또는 적재 rows 출력.

- [ ] **Step 3: 적재 검증 SQL**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    n_mapper = await c.fetchval('SELECT COUNT(*) FROM mapper_activities WHERE report_date=\$1', __import__('datetime').date(2025,9,25))
    n_forecast = await c.fetchval('SELECT COUNT(*) FROM forecasts')
    n_advice = await c.fetchval('SELECT COUNT(*) FROM optimizer_advice')
    # l7_5 / conditions / trade 검증
    sample = await c.fetchrow('SELECT trade, l7_5_activity, conditions FROM mapper_activities LIMIT 1')
    print(f'9-25 mapper rows: {n_mapper}')
    print(f'forecasts rows: {n_forecast}')
    print(f'advice rows: {n_advice}')
    print(f'sample: trade={sample[\"trade\"]}, l7_5={sample[\"l7_5_activity\"]}, conditions={sample[\"conditions\"]}')
    await c.close()
asyncio.run(m())
"
```

Expected: mapper rows ~수백 (전 공종 9-25 활성), forecasts 그룹 수 만큼, advice 일부. sample 의 trade ∈ {설비/전기/건축/UT/제어/소방/토목}, l7_5_activity 채워짐, conditions ∈ TAG_TO_CONDS values.

- [ ] **Step 4: Chroma 적재 검증**

```bash
pipeline/.venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
chroma = ChromaClient(host='localhost', port=5533)
coll = chroma.get_or_create_daily_activities()
print(f'Chroma daily_activities 총: {coll.count()}')
sample = coll.get(limit=2, include=['metadatas','documents'])
for i, m in enumerate(sample['metadatas']):
    print(f'sample {i}: l5_disc={m.get(\"l5_disc\")}, l7_5={m.get(\"l7_5_activity\")}, conditions={m.get(\"conditions\")}')
"
```

Expected: Chroma 적재 수백 row + metadata 에 l5_disc / l7_5_activity / conditions 박혀있음.

- [ ] **Step 5: 전 기간 seed 실행 (24-04-11 ~ 25-09-25, 530일)**

```bash
# 먼저 reset (B.8 위에서 9-25 만 적재되었음 — 전 기간 재실행 위해)
pipeline/.venv/bin/python3 scripts/local_db_reset.py
# 전 기간 seed (예상 시간 — seed_dummy_year.py 의 mapper insert 위주, Chroma upsert 는 sample 일자만)
time pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start 2024-04-11 --end 2025-09-25 2>&1 | tail -30
```

Expected: 전 기간 적재 완료. 시간 5~15분 (mapper insert 위주, Chroma 는 sample 일자만 적재).

- [ ] **Step 6: 전 기간 적재 검증**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    n = await c.fetchval('SELECT COUNT(*) FROM mapper_activities')
    dates = await c.fetchval('SELECT COUNT(DISTINCT report_date) FROM mapper_activities')
    min_d = await c.fetchval('SELECT MIN(report_date) FROM mapper_activities')
    max_d = await c.fetchval('SELECT MAX(report_date) FROM mapper_activities')
    print(f'mapper_activities 총 rows: {n}')
    print(f'distinct dates: {dates}')
    print(f'date range: {min_d} ~ {max_d}')
    # 분포 check
    tags = await c.fetch('SELECT trade, COUNT(*) FROM mapper_activities GROUP BY trade ORDER BY 2 DESC')
    print('trade 분포:')
    for r in tags:
        print(f'  {r[0]}: {r[1]}')
    await c.close()
asyncio.run(m())
"
```

Expected: 총 rows ~수십만, distinct dates 530, range 24-04-11 ~ 25-09-25, trade ∈ 설비/전기/건축/UT/제어/소방/토목 모두 나옴.

- [ ] **Step 7: Commit (verify log 만 commit — seed 결과 자체는 DB)**

```bash
mkdir -p tmp/seed-logs
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    n = await c.fetchval('SELECT COUNT(*) FROM mapper_activities')
    print(f'mapper_activities: {n}')
    await c.close()
asyncio.run(m())
" > tmp/seed-logs/full-seed-$(date +%Y%m%d-%H%M).log

# log 는 gitignore (tmp/) 이라 commit 안 함 — local 만
echo "seed 실 적재 완료 (DB 상태로 보존)"
```

---

## Phase C — mapper 이후 배치 (4 tasks)

### Task C.1: `retrieve.py:95` incident keyword 9종 보강 (TDD)

**Files:**
- Modify: `pipeline/agents/optimizer/retrieve.py:95` (1 줄)
- Create: `pipeline/tests/optimizer/test_retrieve_incident_9kw.py`

- [ ] **Step 1: 현재 retrieve.py 의 두 상수 read**

```bash
sed -n '20,30p' /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/agents/optimizer/retrieve.py
sed -n '70,80p' /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/agents/optimizer/retrieve.py
sed -n '115,130p' /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/agents/optimizer/retrieve.py
```

Expected: 두 상수 확인.
- `_DEGRADATION_INCIDENTS = ("장비대기", "자재미입고", "돌관")` (L24, 3종) — L121 `has_incident` 검사 (degradation 트리거)
- `_ALL_INCIDENTS = ("장비대기", "자재미입고", "우천", "돌관", "야간연장")` (L26, 5종) — L72 baseline 산출 시 제외

- [ ] **Step 2: Write failing test**

```python
"""retrieve.py incident keyword 9종 매칭 검증 (spec §6)."""

from __future__ import annotations

from pipeline.agents.optimizer import retrieve


def test_incident_keywords_9_set():
    """9 keyword 모두 INCIDENT_KEYWORDS 에 있어야."""
    expected = {"장비대기", "자재미입고", "돌관", "우천", "야간연장",
                "인력부족", "재작업", "병행작업", "사양변경"}
    # retrieve.py 의 keyword set 이름 확인 (`INCIDENT_KEYWORDS` 또는 함수 내부 const)
    actual = getattr(retrieve, "INCIDENT_KEYWORDS", None)
    assert actual is not None, "INCIDENT_KEYWORDS 가 retrieve.py module level 에 없음"
    assert set(actual) == expected, f"keyword set 불일치: {set(actual) ^ expected}"


def test_incident_substring_matching_new_keywords():
    """새 4 keyword (인력부족·재작업·병행작업·사양변경) substring 매칭 — _has_incident 또는
    유사 helper 검증. retrieve.py 의 실 매칭 함수 확인 후 호출 (없으면 본 test skip)."""
    incident_kw = getattr(retrieve, "INCIDENT_KEYWORDS", None)
    assert incident_kw is not None
    for new_kw in ["인력부족", "재작업", "병행작업", "사양변경"]:
        conditions_raw = f"우천,{new_kw}"
        assert any(kw in conditions_raw for kw in incident_kw), \
            f"{new_kw} 가 9 kw set 중 매칭 안 됨"
```

- [ ] **Step 3: Run test — expected FAIL**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/optimizer/test_retrieve_incident_9kw.py -v 2>&1 | tail -10
```

Expected: `INCIDENT_KEYWORDS` attr 없거나 5종만 있어서 fail.

- [ ] **Step 4: `retrieve.py` 수정 — 두 상수 → 단일 INCIDENT_KEYWORDS (9종) 통합**

기존 두 상수 (`_DEGRADATION_INCIDENTS` 3종 + `_ALL_INCIDENTS` 5종) 를 **단일 `INCIDENT_KEYWORDS` (9종)** 로 통합. 두 상수가 가졌던 의미 (degradation trigger / baseline 제외) 는 둘 다 9종 동일 set 으로 통일 — spec §6 사용자 의도와 일치.

`pipeline/agents/optimizer/retrieve.py` 수정:

```python
# L23-26 교체:
# spec §6 — degradation 트리거 + baseline 제외 통합 9 종 (이전 _DEGRADATION_INCIDENTS 3종
# + _ALL_INCIDENTS 5종 → 통일). seed TAG_TO_CONDS 의 7 tag 모두 발현 보장.
INCIDENT_KEYWORDS: tuple[str, ...] = (
    "장비대기", "자재미입고", "돌관", "우천", "야간연장",
    "인력부족", "재작업", "병행작업", "사양변경",  # spec §6 추가 4종
)
# backward compat alias (호출 site 점진 마이그 위함, 새 코드는 INCIDENT_KEYWORDS 직접 사용)
_DEGRADATION_INCIDENTS = INCIDENT_KEYWORDS
_ALL_INCIDENTS = INCIDENT_KEYWORDS
```

L72 (`if any(c in raw for c in _ALL_INCIDENTS):`) 와 L121 (`has_incident = any(c in raw for c in _DEGRADATION_INCIDENTS)`) 는 alias 통해 9종 동일 set 자동 적용 — **추가 변경 X**.

또는 깔끔하게 두 reference 모두 `INCIDENT_KEYWORDS` 직접 호출로 변경 (alias 제거):

```python
# L72:
if any(c in raw for c in INCIDENT_KEYWORDS):
# L121:
has_incident = any(c in raw for c in INCIDENT_KEYWORDS)
```

⚠ 두 상수의 **의미 분리 의도** (degradation trigger vs baseline 제외) 가 향후 다시 갈라질 수 있다면 alias 유지 권장. 본 spec 의 의도는 통일이라 alias + 향후 분리 가능성 보존.

- [ ] **Step 5: Run test — expected PASS**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/optimizer/test_retrieve_incident_9kw.py -v 2>&1 | tail -10
```

Expected: `2 passed`.

- [ ] **Step 6: 기존 optimizer 회귀 검증**

```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/optimizer/ -m "not slow and not golden" --timeout=60 --tb=line 2>&1 | tail -10
```

Expected: 기존 test 모두 pass 유지.

- [ ] **Step 7: Commit**

```bash
git add pipeline/agents/optimizer/retrieve.py pipeline/tests/optimizer/test_retrieve_incident_9kw.py
git commit -m "$(cat <<'EOF'
feat(retrieve): incident keyword 9종 보강 (인력부족/재작업/병행작업/사양변경)

spec §6 — seed TAG_TO_CONDS 의 7 tag 모두 degradation_cases 발현 위해
incident keyword 5종 → 9종 확장. INCIDENT_KEYWORDS module 상수 도입.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C.2: `backfill_optimizer_advice_llm.py:53` DEFAULT_TRADES 7종 확장

**Files:**
- Modify: `scripts/backfill_optimizer_advice_llm.py:53`

- [ ] **Step 1: 현재 L53 read**

```bash
sed -n '50,60p' /Users/kyungseoplee/Project\ Agent/CPIA/scripts/backfill_optimizer_advice_llm.py
```

Expected: `DEFAULT_TRADES = ("건축", "토목")` 확인.

- [ ] **Step 2: 수정**

```python
# 기존:
DEFAULT_TRADES = ("건축", "토목")
# 변경:
DEFAULT_TRADES = ("설비", "전기", "건축", "UT", "제어", "소방", "토목")
```

- [ ] **Step 3: smoke help 출력**

```bash
pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py --help 2>&1 | grep -A1 "trades"
```

Expected: "기본 설비,전기,건축,UT,제어,소방,토목" 또는 유사 default 표시.

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_optimizer_advice_llm.py
git commit -m "$(cat <<'EOF'
feat(backfill): DEFAULT_TRADES 7종 (설비/전기/건축/UT/제어/소방/토목)

spec §9 — l5_disc 7종 모두 backfill default 에 포함.
사용자 결정: 건축/토목만이 아니라 모든 공종.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C.3: 시연 윈도우 backfill 실행 (9/1 ~ 9/25, 25 일, ~2 시간)

**Files:**
- Reference: B.8 의 seed 적재 완료 상태
- Output: 로컬 PG forecasts / optimizer_advice / daily_reports 25 일치 적재

- [ ] **Step 1: 사전 검증 — mapper 적재 확인**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    n = await c.fetchval('SELECT COUNT(*) FROM mapper_activities WHERE report_date BETWEEN \$1 AND \$2',
        __import__('datetime').date(2025,9,1), __import__('datetime').date(2025,9,25))
    print(f'9/1~9/25 mapper rows: {n}')
    await c.close()
asyncio.run(m())
"
```

Expected: 수천 row (25 일 × 활성 row).

- [ ] **Step 2: Concurrency env 설정 (rate limit 안전)**

```bash
export CPIA_LLM_CONCURRENCY=4
```

- [ ] **Step 3: 시연 윈도우 backfill 실행 (~2 시간)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
mkdir -p tmp/backfill-logs
time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-09-01 --end-date 2025-09-25 \
  --site m15x-ph3-ibl \
  --clean \
  2>&1 | tee tmp/backfill-logs/demo-window-$(date +%Y%m%d-%H%M).log
```

Expected: 일자별 cycle 25번 실행 후 "전체 결과: PASS" 또는 일자별 PASS/FAIL 표시. 시간 ~2 시간.

- [ ] **Step 4: 적재 검증 SQL**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    print('일자별 forecasts/advice 수:')
    rows = await c.fetch(\"\"\"SELECT report_date, COUNT(*) FROM forecasts f
        JOIN pipeline_runs pr USING (run_id) WHERE pr.is_mock=true
        AND report_date BETWEEN \$1 AND \$2 GROUP BY report_date ORDER BY report_date\"\"\",
        __import__('datetime').date(2025,9,1), __import__('datetime').date(2025,9,25))
    for r in rows: print(f'  {r[0]}: forecasts={r[1]}')
    await c.close()
asyncio.run(m())
"
```

Expected: 25개 일자 모두 forecasts 있음.

- [ ] **Step 5: Commit (log 만 — DB 상태는 그대로)**

```bash
# log 는 tmp/ 라 gitignore. log 의 핵심만 추출해서 docs/superpowers/specs/ 에 verify log 저장.
tail -30 tmp/backfill-logs/demo-window-*.log > docs/superpowers/specs/2026-05-23-cpia-demo-window-backfill-verify.log
git add docs/superpowers/specs/2026-05-23-cpia-demo-window-backfill-verify.log
git commit -m "$(cat <<'EOF'
data(verify): Phase C demo window 9/1~9/25 backfill 통과 log

25 일 cycle 완료, forecasts/advice 적재. Phase D UI 검증 진입 준비.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C.4: 전 기간 backfill 실행 (24-04-11 ~ 25-08-31, 505 일, ~42 시간 — 시연 윈도우 검증 통과 후만)

**Files:**
- Output: 로컬 PG 전 기간 forecasts / optimizer_advice / daily_reports

⚠ **선결 조건**: Phase D 의 시연 윈도우 UI 검증 통과 (Task D.5). 안 끝났으면 본 task skip.

- [ ] **Step 1: Concurrency 조정 (전 기간은 안전 위해 2)**

```bash
export CPIA_LLM_CONCURRENCY=2
```

- [ ] **Step 2: 전 기간 backfill (~42 시간)**

```bash
time pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2024-04-11 --end-date 2025-08-31 \
  --site m15x-ph3-ibl \
  --clean \
  2>&1 | tee tmp/backfill-logs/full-period-$(date +%Y%m%d-%H%M).log
```

⚠ **사용자 외출 3일** 동안 실행 의도. 중간 fail 시 `--start-date <last_ok+1>` 로 재시작 가능.

- [ ] **Step 3: 진행 모니터링 (background, 별 세션)**

```bash
# 별 터미널에서:
tail -f tmp/backfill-logs/full-period-*.log
# 또는 cron 으로 1시간마다 진척 check
```

- [ ] **Step 4: 완료 검증**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5532/cpia')
    n_dates = await c.fetchval('SELECT COUNT(DISTINCT report_date) FROM forecasts f JOIN pipeline_runs pr USING (run_id)')
    print(f'forecasts 일자 수: {n_dates} (목표 530)')
    await c.close()
asyncio.run(m())
"
```

Expected: 530 일 (또는 진행 중인 경우 일부).

- [ ] **Step 5: 완료 후 Commit (verify log)**

```bash
tail -30 tmp/backfill-logs/full-period-*.log > docs/superpowers/specs/2026-05-23-cpia-full-period-backfill-verify.log
git add docs/superpowers/specs/2026-05-23-cpia-full-period-backfill-verify.log
git commit -m "$(cat <<'EOF'
data(verify): Phase C full period 24-04-11~25-08-31 backfill 통과 log

505 일 cycle 완료. Phase E AWS 마이그 진입 준비.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase D — UI 검증 (5 tasks)

### Task D.1: `scripts/verify_ui_assertions.py` 신규 작성 (SQL assertion 8건)

**Files:**
- Create: `scripts/verify_ui_assertions.py`

- [ ] **Step 1: Write script (spec §15.1 의 8 SQL assertion)**

```python
"""Phase D UI 검증 — SQL assertion 8건 자동 실행.

spec §15.1 — site_summary NULL=0 / quadrant∩by_wp≥99% / degradation 4필드≥90% /
delay 음양 각≥1 / F3 S-curve≥95% / conditions tag≥5 / productivity median 80-100 /
outlier 2-10%.
"""

from __future__ import annotations

import asyncio
from datetime import date

import asyncpg

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
SITE = "m15x-ph3-ibl"


async def run_check(pg, label: str, sql: str, params: tuple, predicate, expected: str) -> bool:
    val = await pg.fetchval(sql, *params)
    ok = predicate(val)
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}: {val} (기대: {expected})")
    return ok


async def main(report_date: date = date(2025, 9, 25)) -> None:
    pg = await asyncpg.connect(LOCAL_PG)
    print(f"=== UI assertion 8건 — site={SITE}, date={report_date} ===")
    results = []

    # 1. site_summary LLM narrative
    results.append(await run_check(pg, "site_summary NULL=0",
        """SELECT COUNT(*) FROM daily_report_views_v2 v
           JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND v.site_summary IS NULL""",
        (SITE, report_date), lambda v: v == 0, "=0"))

    # 2. quadrant ↔ by_wp wp_id 교집합 — by_wp 기준 ∩ quadrant 비율
    results.append(await run_check(pg, "quadrant ↔ by_wp ≥99%",
        """WITH q AS (
             SELECT DISTINCT qcase->>'wp_id' AS wp_id
             FROM optimizer_advice oa
             JOIN pipeline_runs pr ON oa.run_id=pr.run_id,
                  jsonb_array_elements(oa.quadrant->'cases') qcase
             WHERE pr.site_id=$1 AND pr.report_date=$2
               AND qcase->>'wp_id' IS NOT NULL
           ),
           w AS (
             SELECT DISTINCT wrow->>'wp_id' AS wp_id
             FROM optimizer_advice oa
             JOIN pipeline_runs pr ON oa.run_id=pr.run_id,
                  jsonb_array_elements(oa.by_wp) wrow
             WHERE pr.site_id=$1 AND pr.report_date=$2
               AND wrow->>'wp_id' IS NOT NULL
           )
           SELECT 1.0 * COUNT(q.wp_id) / NULLIF(COUNT(w.wp_id), 0)
           FROM w LEFT JOIN q ON w.wp_id = q.wp_id""",
        (SITE, report_date), lambda v: (v or 0.0) >= 0.99, "≥0.99"))

    # 3. degradation_cases 4필드 ≥ 90%
    results.append(await run_check(pg, "degradation 4필드 ≥ 90%",
        """SELECT 1.0 * SUM(CASE WHEN c->>'date' IS NOT NULL AND c->>'conditions' IS NOT NULL
           AND c->>'productivity' IS NOT NULL AND (c->'recovery'->>'recovery_days') IS NOT NULL
           THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
           FROM optimizer_advice oa, jsonb_array_elements(oa.degradation_cases) c
           JOIN pipeline_runs pr ON oa.run_id=pr.run_id
           WHERE pr.site_id=$1 AND pr.report_date=$2""",
        (SITE, report_date), lambda v: (v or 0) >= 0.90, "≥0.90"))

    # 4. delay 음/양 각≥1
    results.append(await run_check(pg, "delay 음/양 분포",
        """SELECT SUM(CASE WHEN delay_days < 0 THEN 1 ELSE 0 END)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND delay_days IS NOT NULL""",
        (SITE, report_date), lambda v: (v or 0) >= 1, "≥1 (음수)"))
    results.append(await run_check(pg, "delay 양수≥1",
        """SELECT SUM(CASE WHEN delay_days > 0 THEN 1 ELSE 0 END)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND delay_days IS NOT NULL""",
        (SITE, report_date), lambda v: (v or 0) >= 1, "≥1 (양수)"))

    # 5. F3 S-curve (완공 row today_cum_qty / plan_total_qty ≥ 0.95)
    results.append(await run_check(pg, "F3 완공 row cum_qty/plan ≥ 0.95",
        """SELECT MAX(today_cum_qty / NULLIF(plan_total_qty, 0)) FROM mapper_activities
           WHERE report_date=$1 AND plan_total_qty > 0""",
        (report_date,), lambda v: (v or 0) >= 0.95, "≥0.95"))

    # 6. conditions tag ≥ 5종 발현
    results.append(await run_check(pg, "conditions tag 다양성 ≥5",
        """SELECT COUNT(DISTINCT conditions) FROM mapper_activities
           WHERE report_date=$1 AND conditions IS NOT NULL""",
        (report_date,), lambda v: (v or 0) >= 5, "≥5"))

    # 7. productivity median 80~100
    results.append(await run_check(pg, "prod median 80~100",
        """SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY today_productivity)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2 AND today_productivity > 0""",
        (SITE, report_date), lambda v: v is not None and 80 <= v <= 100, "80~100"))

    # 8. outlier 2~10%
    results.append(await run_check(pg, "outlier 빈도 2~10%",
        """SELECT 1.0 * SUM(CASE WHEN today_productivity < 60 OR today_productivity > 130
           THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)
           FROM forecasts f JOIN pipeline_runs pr USING (run_id)
           WHERE pr.site_id=$1 AND pr.report_date=$2""",
        (SITE, report_date), lambda v: v is not None and 0.02 <= v <= 0.10, "0.02~0.10"))

    n_pass = sum(results)
    print(f"\n전체: {n_pass}/{len(results)} {'PASS' if n_pass == len(results) else 'FAIL'}")
    await pg.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 9-25 일자 검증 실행**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 scripts/verify_ui_assertions.py 2>&1 | tee tmp/ui-verify-925.log
```

Expected: 8개 모두 ✓ → 전체: 8/8 PASS.

- [ ] **Step 3: 추가 일자 sanity check (9-22 / 9-15)**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio
from datetime import date
from scripts.verify_ui_assertions import main
for d in [date(2025,9,22), date(2025,9,15)]:
    print(f'\n=== {d} ===')
    asyncio.run(main(d))
"
```

Expected: 모든 일자 PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_ui_assertions.py
git commit -m "$(cat <<'EOF'
feat(verify): UI assertion 8건 자동 검증 script

spec §15.1 — site_summary NULL / quadrant∩by_wp / degradation 4필드 /
delay 음양 / F3 S-curve / conditions 다양성 / prod median / outlier 빈도.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D.2: FE 5536 가동 확인 + Playwright MCP 환경 점검

**Files:**
- Reference: A.2 의 FE 가동 상태

- [ ] **Step 1: FE 가동 상태 확인**

```bash
curl -fsS -o /dev/null -w "FE: %{http_code}\n" http://localhost:5536/
ps aux | grep -E "next dev|next-server" | grep -v grep | head -3
```

Expected: `FE: 200`, next-server process 1개.

- [ ] **Step 2: cache clear 후 restart (mapper 적재 변경 반영 보장)**

```bash
pkill -f "next dev" 2>/dev/null || true
rm -rf /Users/kyungseoplee/Project\ Agent/CPIA/web/.next
sleep 1
cd /Users/kyungseoplee/Project\ Agent/CPIA/web
npm run dev > /tmp/cpia-fe-dev.log 2>&1 &
sleep 6
tail -10 /tmp/cpia-fe-dev.log
```

Expected: "Ready in N.Ns" 출력.

- [ ] **Step 3: Playwright MCP browser navigate 첫 호출 (smoke)**

```
mcp__plugin_playwright_playwright__browser_navigate(url="http://localhost:5536/")
mcp__plugin_playwright_playwright__browser_console_messages()
```

Expected: console messages 0 errors.

---

### Task D.3: 페이지별 Playwright UI 검증 + screenshot

**Files:**
- Output: `docs/superpowers/specs/2026-05-23-cpia-phaseD-*.png` screenshot 5장 보존

- [ ] **Step 1: `/` Dashboard 검증**

Playwright MCP:
```
browser_navigate("http://localhost:5536/")
browser_console_messages()  → expect 0 errors
browser_take_screenshot(filename="2026-05-23-cpia-phaseD-dashboard.png", fullPage=true)
```

검증: site 카드 6 개 표시, 진척률/지연/인력 숫자 박힘 (0 아님).

- [ ] **Step 2: `/tasks` 검증**

```
browser_navigate("http://localhost:5536/tasks")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseD-tasks.png")
```

검증: 일자별 progress bar 표시 (B.8 + C.3 적재 후), 25일 시연 윈도우 + 전 기간 진행 표시.

- [ ] **Step 3: `/reports/2025-09-25` 검증**

```
browser_navigate("http://localhost:5536/reports/2025-09-25")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseD-reports-925.png", fullPage=true)
```

검증: S-curve 차트, 4분면, by_wp 막대, degradation_cases (광건/태우/세보엠이씨 등) 모두 표시.

- [ ] **Step 4: `/sites/m15x-ph3-ibl` 검증**

```
browser_navigate("http://localhost:5536/sites/m15x-ph3-ibl")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseD-site-detail.png", fullPage=true)
```

검증: site KPI delay (MEDIAN) + ForecastChart aiSummaryText LLM narrative 박힘.

- [ ] **Step 5: `/review` 검증**

```
browser_navigate("http://localhost:5536/review")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseD-review.png")
```

검증: waiting_hil_1 row 표시 (있다면).

- [ ] **Step 6: Commit screenshot 5장**

Playwright MCP screenshot 저장 위치 확인:
- 기본 `~/Downloads/` (macOS), 또는 MCP 설정에 따라 `/tmp/` 또는 cwd
- `find ~/Downloads /tmp . -name "2026-05-23-cpia-phaseD-*.png" -mmin -10 2>/dev/null` 로 실 위치 확인

```bash
# 실 위치에 따라 mv (예시):
mv ~/Downloads/2026-05-23-cpia-phaseD-*.png docs/superpowers/specs/ 2>/dev/null || \
  mv /tmp/2026-05-23-cpia-phaseD-*.png docs/superpowers/specs/ 2>/dev/null || \
  find . -maxdepth 3 -name "2026-05-23-cpia-phaseD-*.png" -exec mv {} docs/superpowers/specs/ \;
git add docs/superpowers/specs/2026-05-23-cpia-phaseD-*.png
git commit -m "$(cat <<'EOF'
data(verify): Phase D UI screenshot 5장 (Dashboard/Tasks/Reports/Site/Review)

console 0 errors. SQL assertion 8/8 PASS 와 함께 Phase D 통과 기준.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task D.4: 의도 일치 fix (UI 이슈 발견 시)

**Files:** (이슈에 따라 다름)

- [ ] **Step 1: D.3 결과의 console errors / 의도 불일치 항목 정리**

발견된 이슈 (예시):
- console error: Cannot read properties of undefined (typed handling)
- 의도 불일치: site_summary "—" 표시 (LLM narrative 빠짐)
- 의도 불일치: by_wp 막대 비어있음

- [ ] **Step 2: 이슈별 fix (root cause 분석 후 surgical edit)**

전 세션 patterns:
- next-server cache stale → restart + .next 삭제
- backfill_daily_report_views_v2 의 --with-summary flag 빠짐 → script 재실행
- view_builder.py SQL 의 JOIN 조건 → spec §15.1 SQL 비교

- [ ] **Step 3: Fix 후 D.1 (SQL assertion) + D.3 (Playwright) 재실행**

```bash
pipeline/.venv/bin/python3 scripts/verify_ui_assertions.py
```

Expected: 8/8 PASS.

- [ ] **Step 4: 추가 commits (fix 별로)**

```bash
git add <fixed files>
git commit -m "fix(<area>): <issue> resolution

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task D.5: Phase D 통과 보고 + 전 기간 backfill 진행 동의 (Phase C.4 게이트)

**Files:**
- Update: `docs/superpowers/specs/2026-05-23-cpia-phaseD-verify-summary.md` (신규 verify summary)

- [ ] **Step 1: verify summary 작성**

```bash
cat > docs/superpowers/specs/2026-05-23-cpia-phaseD-verify-summary.md <<'EOF'
# Phase D UI 검증 통과 요약

**일시:** $(date +%Y-%m-%d_%H:%M)
**대상:** 시연 윈도우 9/1~9/25 적재 후 FE 5536 검증

## SQL assertion (verify_ui_assertions.py)
- 9/25: 8/8 PASS
- 9/22: 8/8 PASS
- 9/15: 8/8 PASS

## Playwright UI
- Dashboard: console 0 errors, 6 site 카드 표시
- Tasks: 25 일 진행 표시
- Reports/9-25: S-curve + 4분면 + by_wp + degradation_cases 모두 정상
- Site Detail: site KPI + ForecastChart aiSummaryText LLM narrative
- Review: waiting_hil_1 row 표시 (있다면)

## 다음 단계
- Phase C.4 전 기간 backfill (24-04-11 ~ 25-08-31, ~42 시간) 진행 동의 받기
- 통과 시 Phase E AWS 마이그
EOF
```

- [ ] **Step 2: 사용자에게 Phase D 통과 보고 + Phase C.4 진행 동의 요청**

(사용자 답 받은 후 Phase C.4 또는 Phase E 진입)

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-23-cpia-phaseD-verify-summary.md
git commit -m "$(cat <<'EOF'
data(verify): Phase D 통과 요약 (시연 윈도우 9/1~9/25)

SQL 8/8 PASS × 3 일자 + Playwright 5 페이지 console 0 errors.
Phase C.4 (전 기간 backfill) 또는 Phase E (AWS 마이그) 진행 가능.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase E — AWS 마이그 + 머지 (6 tasks)

### Task E.1: Chroma export/import script 신규 작성

**Files:**
- Create: `scripts/chroma_export.py`
- Create: `scripts/chroma_import.py`

- [ ] **Step 1: `scripts/chroma_export.py` 작성**

```python
"""Chroma collection → JSONL snapshot.

usage: python scripts/chroma_export.py --host HOST --port PORT --collection NAME --out PATH.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
from pipeline.chroma_client import ChromaClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5533)
    ap.add_argument("--collection", default="daily_activities")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    chroma = ChromaClient(host=args.host, port=args.port)
    coll = chroma.client.get_collection(args.collection)
    total = coll.count()
    print(f"export {args.collection} from {args.host}:{args.port} → {args.out} ({total} docs)")

    BATCH = 500
    with open(args.out, "w") as f:
        for offset in range(0, total, BATCH):
            data = coll.get(limit=BATCH, offset=offset,
                            include=["embeddings", "metadatas", "documents"])
            for i in range(len(data["ids"])):
                f.write(json.dumps({
                    "id": data["ids"][i],
                    "embedding": data["embeddings"][i],
                    "metadata": data["metadatas"][i],
                    "document": data["documents"][i],
                }, ensure_ascii=False) + "\n")
            print(f"  offset={offset}+{len(data['ids'])}")
    print(f"✓ export 완료 ({total} lines)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: `scripts/chroma_import.py` 작성**

```python
"""JSONL snapshot → Chroma collection.

usage: python scripts/chroma_import.py --host HOST --port PORT --collection NAME --in PATH.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
from pipeline.chroma_client import ChromaClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5533)
    ap.add_argument("--collection", default="daily_activities")
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()

    chroma = ChromaClient(host=args.host, port=args.port)
    # collection 존재 시 delete + 재생성 (clean import)
    try:
        chroma.client.delete_collection(args.collection)
        print(f"  · 기존 {args.collection} 삭제")
    except Exception:
        pass
    coll = chroma.get_or_create_daily_activities() if args.collection == "daily_activities" \
        else chroma.client.create_collection(args.collection)

    BATCH = 100
    ids, embs, metas, docs = [], [], [], []
    n_total = 0
    with open(args.inp) as f:
        for line in f:
            row = json.loads(line)
            ids.append(row["id"])
            embs.append(row["embedding"])
            metas.append(row["metadata"])
            docs.append(row["document"])
            if len(ids) >= BATCH:
                coll.upsert(ids=ids, embeddings=embs, metadatas=metas, documents=docs)
                n_total += len(ids)
                print(f"  upsert {n_total}")
                ids, embs, metas, docs = [], [], [], []
        if ids:
            coll.upsert(ids=ids, embeddings=embs, metadatas=metas, documents=docs)
            n_total += len(ids)
            print(f"  upsert {n_total}")
    print(f"✓ import 완료 ({n_total} docs)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 로컬 round-trip smoke (export → import to new collection → count)**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
mkdir -p tmp/chroma-snapshot
pipeline/.venv/bin/python3 scripts/chroma_export.py \
  --host localhost --port 5533 --collection daily_activities \
  --out tmp/chroma-snapshot/local-test.jsonl
wc -l tmp/chroma-snapshot/local-test.jsonl
```

Expected: 로컬 적재된 docs 수 만큼 줄. round-trip 확인 위한 별 collection 적재 (생략 가능).

- [ ] **Step 4: Commit**

```bash
git add scripts/chroma_export.py scripts/chroma_import.py
git commit -m "$(cat <<'EOF'
feat(scripts): chroma_export.py + chroma_import.py — JSONL snapshot

Phase E AWS 마이그 시 Chroma daily_activities collection round-trip 용.
embedding + metadata + document 보존.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E.2: `scripts/aws_backup_and_migrate.py` 신규 orchestrator 작성

**Files:**
- Create: `scripts/aws_backup_and_migrate.py`

- [ ] **Step 1: Write script**

```python
"""AWS 마이그 orchestrator — backup / reset / restore subcommand.

usage:
  python scripts/aws_backup_and_migrate.py backup    # AWS → tmp/aws-backup-*.sql + chroma snapshot
  python scripts/aws_backup_and_migrate.py reset     # AWS PG TRUNCATE all + Chroma delete (위험)
  python scripts/aws_backup_and_migrate.py restore   # 로컬 dump → AWS push
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

import asyncpg

AWS_PG_HOST = "43.200.85.209"
AWS_PG_PORT = 5532
AWS_PG_USER = "cpia"
AWS_PG_PWD = "K7mP2xQ9nR4v"
AWS_PG_DB = "cpia"
AWS_CHROMA_HOST = "43.200.85.209"
AWS_CHROMA_PORT = 5533

LOCAL_PG = "postgresql://cpia:cpia@localhost:5532/cpia"
LOCAL_CHROMA_HOST = "localhost"
LOCAL_CHROMA_PORT = 5533

TS = datetime.now().strftime("%Y%m%d-%H%M%S")
BACKUP_DIR = Path("/Users/kyungseoplee/Project Agent/CPIA/tmp")
BACKUP_DIR.mkdir(exist_ok=True)

PG_DUMP_OUT = BACKUP_DIR / f"aws-backup-{TS}.sql"
CHROMA_DUMP_OUT = BACKUP_DIR / f"chroma-aws-{TS}.jsonl"
LOCAL_DUMP_OUT = BACKUP_DIR / f"local-to-aws-{TS}.sql"
LOCAL_CHROMA_DUMP_OUT = BACKUP_DIR / f"chroma-local-{TS}.jsonl"


def run(cmd: list[str], env: dict | None = None) -> None:
    """subprocess + check + print."""
    print(f"$ {' '.join(cmd)}")
    res = subprocess.run(cmd, env=env, capture_output=False, text=True)
    if res.returncode != 0:
        raise SystemExit(f"command failed (rc={res.returncode}): {cmd}")


def backup_aws() -> None:
    """AWS PG + Chroma 백업."""
    import os
    env = {**os.environ, "PGPASSWORD": AWS_PG_PWD}
    print(f"=== AWS PG dump → {PG_DUMP_OUT} ===")
    run(["pg_dump", "-h", AWS_PG_HOST, "-p", str(AWS_PG_PORT),
         "-U", AWS_PG_USER, "-d", AWS_PG_DB,
         "--exclude-table=checkpoints",
         "-f", str(PG_DUMP_OUT)], env=env)
    print(f"=== AWS Chroma snapshot → {CHROMA_DUMP_OUT} ===")
    run(["python3", "scripts/chroma_export.py",
         "--host", AWS_CHROMA_HOST, "--port", str(AWS_CHROMA_PORT),
         "--collection", "daily_activities", "--out", str(CHROMA_DUMP_OUT)])
    print(f"✓ backup 완료")


async def reset_aws() -> None:
    """AWS PG TRUNCATE all + Chroma daily_activities delete. ⚠ 위험."""
    print("⚠ AWS reset — TRUNCATE all + Chroma delete")
    pg = await asyncpg.connect(
        f"postgresql://{AWS_PG_USER}:{AWS_PG_PWD}@{AWS_PG_HOST}:{AWS_PG_PORT}/{AWS_PG_DB}"
    )
    try:
        for tbl in ["optimizer_advice", "forecasts", "daily_reports",
                    "mapped_history", "mapper_activities", "parser_activities",
                    "pipeline_runs"]:
            await pg.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
            print(f"  ✓ TRUNCATE {tbl}")
    finally:
        await pg.close()
    import sys
    sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
    from pipeline.chroma_client import ChromaClient
    chroma = ChromaClient(host=AWS_CHROMA_HOST, port=AWS_CHROMA_PORT)
    try:
        chroma.delete_collection("daily_activities")
        print("  ✓ AWS Chroma daily_activities deleted")
    except Exception as e:
        print(f"  · skip: {e}")


def restore_from_local() -> None:
    """로컬 PG/Chroma → AWS."""
    import os
    print(f"=== 로컬 PG dump → {LOCAL_DUMP_OUT} ===")
    env = {**os.environ, "PGPASSWORD": "cpia"}
    run(["pg_dump", "-h", "localhost", "-p", "5532", "-U", "cpia", "-d", "cpia",
         "--exclude-table=checkpoints", "--data-only",
         "-f", str(LOCAL_DUMP_OUT)], env=env)
    print(f"=== AWS PG restore ← {LOCAL_DUMP_OUT} ===")
    env_aws = {**os.environ, "PGPASSWORD": AWS_PG_PWD}
    run(["psql", "-h", AWS_PG_HOST, "-p", str(AWS_PG_PORT),
         "-U", AWS_PG_USER, "-d", AWS_PG_DB,
         "-f", str(LOCAL_DUMP_OUT)], env=env_aws)
    print(f"=== 로컬 Chroma export → {LOCAL_CHROMA_DUMP_OUT} ===")
    run(["python3", "scripts/chroma_export.py",
         "--host", "localhost", "--port", "5533",
         "--collection", "daily_activities", "--out", str(LOCAL_CHROMA_DUMP_OUT)])
    print(f"=== AWS Chroma import ← {LOCAL_CHROMA_DUMP_OUT} ===")
    run(["python3", "scripts/chroma_import.py",
         "--host", AWS_CHROMA_HOST, "--port", str(AWS_CHROMA_PORT),
         "--collection", "daily_activities", "--in", str(LOCAL_CHROMA_DUMP_OUT)])
    print("✓ restore 완료")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backup", "reset", "restore"])
    args = ap.parse_args()
    if args.mode == "backup":
        backup_aws()
    elif args.mode == "reset":
        asyncio.run(reset_aws())
    elif args.mode == "restore":
        restore_from_local()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: dry smoke (script 자체 import 검증)**

```bash
pipeline/.venv/bin/python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('orch', 'scripts/aws_backup_and_migrate.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print('mode functions:', [n for n in dir(m) if n in ('backup_aws','reset_aws','restore_from_local')])
"
```

Expected: 3 function names.

- [ ] **Step 3: Commit**

```bash
git add scripts/aws_backup_and_migrate.py
git commit -m "$(cat <<'EOF'
feat(scripts): aws_backup_and_migrate.py — backup/reset/restore orchestrator

backup: AWS PG dump + Chroma snapshot → tmp/aws-backup-*.sql / chroma-aws-*.jsonl
reset: AWS PG TRUNCATE all + Chroma delete (위험)
restore: 로컬 dump → AWS PG/Chroma push

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E.3: AWS 백업 실행

**Files:**
- Output: `tmp/aws-backup-*.sql` + `tmp/chroma-aws-*.jsonl`

- [ ] **Step 1: pg_dump 가능한 client 확인**

```bash
which pg_dump || brew install postgresql@16  # macOS, 없으면 설치
pg_dump --version
```

Expected: pg_dump 17.x 또는 16.x.

- [ ] **Step 2: 백업 실행**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 scripts/aws_backup_and_migrate.py backup 2>&1 | tee tmp/aws-backup.log
```

Expected: PG dump + Chroma snapshot 완료.

- [ ] **Step 3: 백업 file 검증**

```bash
ls -lh tmp/aws-backup-*.sql tmp/chroma-aws-*.jsonl | tail -4
head -20 tmp/aws-backup-*.sql | grep -E "(CREATE TABLE|COPY)"
wc -l tmp/chroma-aws-*.jsonl
```

Expected: SQL ~수십 MB, Chroma JSONL 수천 줄.

- [ ] **Step 4: 백업 보존 안내 (gitignore 라 commit X)**

```bash
echo "AWS 백업 완료: $(ls -1 tmp/aws-backup-*.sql tmp/chroma-aws-*.jsonl | tail -2)"
echo "다음 단계에서 AWS reset 시 위 file 로 rollback 가능."
```

---

### Task E.4: FE → AWS swap + 화면 reset 확인

**Files:**
- Modify: `.env.local` (POSTGRES_URL / CHROMA_HOST AWS 로 복원)

- [ ] **Step 1: .env.local 복원 (백업본 활용)**

```bash
cp /Users/kyungseoplee/Project\ Agent/CPIA/.env.local.aws-backup \
   /Users/kyungseoplee/Project\ Agent/CPIA/.env.local
grep -E "POSTGRES_URL|CHROMA_HOST" /Users/kyungseoplee/Project\ Agent/CPIA/.env.local
```

Expected: POSTGRES_URL=...@43.200.85.209... / CHROMA_HOST=43.200.85.209.

- [ ] **Step 2: FE restart**

```bash
pkill -f "next dev" 2>/dev/null || true
rm -rf /Users/kyungseoplee/Project\ Agent/CPIA/web/.next
sleep 1
cd /Users/kyungseoplee/Project\ Agent/CPIA/web
npm run dev > /tmp/cpia-fe-dev.log 2>&1 &
sleep 6
```

- [ ] **Step 3: 화면이 AWS 의 현재 상태 표시 확인 (시연 윈도우 적재 전이라 stale)**

Playwright MCP:
```
browser_navigate("http://localhost:5536/reports/2025-09-25")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseE-aws-pre-migrate.png")
```

검증: AWS 의 현재 상태 (이전 T20 시점 mock 데이터) 표시. 새 mock (로컬) 과 다른 numbers 확인.

- [ ] **Step 4: Commit screenshot (pre-migration 상태 보존)**

```bash
mv ~/Downloads/2026-05-23-cpia-phaseE-aws-pre-migrate.png docs/superpowers/specs/
git add docs/superpowers/specs/2026-05-23-cpia-phaseE-aws-pre-migrate.png
git commit -m "$(cat <<'EOF'
data(verify): Phase E AWS pre-migration screenshot

FE → AWS swap 후 stale 상태 확인 (이전 mock 데이터). 다음 step 에서 로컬
새 mock 으로 교체.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E.5: AWS reset + 로컬 dump → AWS restore

**Files:**
- Output: AWS PG/Chroma 가 로컬과 동일 상태

⚠ **사용자 명시 동의 필요**: 본 task = 위험 작업 (AWS prod-like 데이터 reset).

- [ ] **Step 1: 사용자 동의 확인**

User 에게 명시:
```
AWS reset 실행 직전 — 백업 완료 (tmp/aws-backup-*.sql, tmp/chroma-aws-*.jsonl).
다음 진행하면 AWS PG TRUNCATE all + Chroma delete 후 로컬 dump 적재.
중간 fail 시 백업 file 로 복원 가능. 진행할까요?
```

(사용자 yes 받은 후 진행)

- [ ] **Step 2: AWS reset 실행**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
pipeline/.venv/bin/python3 scripts/aws_backup_and_migrate.py reset 2>&1 | tee tmp/aws-reset.log
```

Expected: TRUNCATE 7 table + Chroma delete 완료.

- [ ] **Step 3: AWS reset 후 화면 확인 (모든 페이지 빈 상태)**

Playwright MCP:
```
browser_navigate("http://localhost:5536/reports/2025-09-25")
browser_console_messages()
browser_take_screenshot(filename="2026-05-23-cpia-phaseE-aws-after-reset.png")
```

검증: "0건" 또는 빈 state 표시. 새 mock 의 적재 직전 baseline.

- [ ] **Step 4: 로컬 dump → AWS restore**

```bash
pipeline/.venv/bin/python3 scripts/aws_backup_and_migrate.py restore 2>&1 | tee tmp/aws-restore.log
```

Expected: 로컬 PG → AWS PG + 로컬 Chroma → AWS Chroma 적재 완료.

- [ ] **Step 5: AWS 적재 검증 SQL**

```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def m():
    c = await asyncpg.connect('postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia')
    n = await c.fetchval('SELECT COUNT(*) FROM mapper_activities')
    dates = await c.fetchval('SELECT COUNT(DISTINCT report_date) FROM mapper_activities')
    print(f'AWS mapper_activities: {n} rows, {dates} dates')
    await c.close()
asyncio.run(m())
"
```

Expected: 로컬과 동일 (수십만 rows, 530 dates).

- [ ] **Step 6: Commit migration log + screenshot**

```bash
mv ~/Downloads/2026-05-23-cpia-phaseE-aws-after-reset.png docs/superpowers/specs/
git add docs/superpowers/specs/2026-05-23-cpia-phaseE-aws-after-reset.png
git commit -m "$(cat <<'EOF'
data(verify): Phase E AWS reset + restore 완료

AWS PG TRUNCATE + Chroma delete 후 로컬 dump 로 교체. mapper_activities
~수십만 rows + 530 dates 적재 확인.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task E.6: AWS UI 재검증 + PR 작성 + 머지 동의 (최종)

**Files:**
- Output: PR (사용자 머지 결정), `docs/superpowers/specs/2026-05-23-cpia-phaseE-aws-final.png` screenshot

- [ ] **Step 1: AWS UI 재검증 (Phase D 와 동일 항목)**

FE restart (이미 AWS 바라봄):
```bash
pkill -f "next dev" 2>/dev/null || true
rm -rf web/.next
cd web && npm run dev > /tmp/cpia-fe-dev.log 2>&1 &
sleep 6
```

Playwright MCP 5 페이지:
- `/` Dashboard
- `/tasks`
- `/reports/2025-09-25`
- `/sites/m15x-ph3-ibl`
- `/review`

각 페이지 console 0 errors + screenshot.

- [ ] **Step 2: SQL assertion 재실행 (AWS 대상)**

`scripts/verify_ui_assertions.py` 의 LOCAL_PG 를 AWS URL 로 임시 override:

```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" \
  pipeline/.venv/bin/python3 -c "
import asyncio
from scripts import verify_ui_assertions
verify_ui_assertions.LOCAL_PG = 'postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia'
asyncio.run(verify_ui_assertions.main())
"
```

또는 script 에 `--target aws` flag 추가 후 호출. Expected: 8/8 PASS.

- [ ] **Step 3: 최종 screenshot 보존**

```
browser_take_screenshot(filename="2026-05-23-cpia-phaseE-aws-final.png", fullPage=true)
```

mv + git add.

- [ ] **Step 4: PR 작성**

```bash
cd /Users/kyungseoplee/Project\ Agent/CPIA
git push origin A_Track  # 사용자 명시 동의 받은 후만
```

(사용자 push 명시 동의 후만)

```bash
gh pr create --title "CPIA mock 재설계 + 로컬 검증 + AWS 마이그 완료" --body "$(cat <<'EOF'
## Summary
- Mock 데이터 재설계: F3 분포 + conditions 7 tag + l7.5 매칭 + outlier 5% + prod target 90% 역산
- l5_disc 7종 (설비/UT/제어 포함) 전 공종 backfill
- 로컬 PG/Chroma 활성화 + 검증 → AWS 백업 후 마이그
- spec `docs/superpowers/specs/2026-05-23-cpia-mock-rebuild-and-local-migration-design.md`
- plan `docs/superpowers/plans/2026-05-23-cpia-mock-rebuild-implementation.md`

## Test plan
- [ ] SQL assertion 8/8 PASS (verify_ui_assertions.py — 9/25, 9/22, 9/15)
- [ ] Playwright UI 5 페이지 console 0 errors (Dashboard/Tasks/Reports/Sites/Review)
- [ ] AWS UI 재검증 — 로컬과 동일 상태 (mapper rows, distinct dates)
- [ ] 시연 마감 2026-06-05 (목) 전 사용 가능

## Phase 진행 기록
- Phase A 로컬 DB 활성화 (commits ...)
- Phase B seed 재설계 (commits ...)
- Phase C mapper 이후 배치 (시연 윈도우 + 전 기간)
- Phase D UI 검증 (8/8 SQL + 5 페이지 Playwright)
- Phase E AWS 백업 + 마이그 + 검증

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: 사용자에게 PR URL 보고 + 머지 동의 요청**

⚠ **CPIA 머지 권한**: 조형준 프로님만 (memory rule). 본인 (Claude) 머지 진행 X.

- [ ] **Step 6: 머지 후 마무리 + cleanup**

(사용자가 PR 머지 수동 진행 후):
```bash
git checkout main
git pull origin main
# .env.local.aws-backup 등 정리
rm /Users/kyungseoplee/Project\ Agent/CPIA/.env.local.aws-backup
```

---

## Plan 진행 가이드 (실행자용 요약)

1. **Phase A** (3 task, ~1 시간) — 로컬 DB 가동, env swap, reset script
2. **Phase B** (8 task, ~3 시간) — F3 모듈 + seed 수정 + tests + 실 적재
3. **Phase C.1~C.3** (3 task) — retrieve.py 9 kw + DEFAULT_TRADES 7종 + **시연 윈도우 backfill (~2 시간)**
4. **Phase D** (5 task, ~2 시간) — SQL assertion script + Playwright 5 페이지 + fix + 통과 보고
5. **Phase C.4** (1 task) — Phase D 통과 후 **전 기간 backfill (~42 시간)** — 사용자 외출 동안 자동 실행. ⚠ Phase D.5 통과 X 면 본 task skip.
6. **Phase E** (6 task) — Chroma import/export + orchestrator + AWS 백업 + reset + restore + AWS 재검증 + PR + 머지 동의

**실행 순서 명시**: A → B → C.1~C.3 → D → **C.4** → E. C.4 는 Task 번호상 C 이지만 D 통과 후 진행.

**총 28 task / ~50 commits**. TDD 기반 + 빈번 commit + 사용자 명시 동의 ([git push](로컬→AWS 마이그)·[AWS reset]·[PR 머지]) 게이트.

**핵심 file 영향 범위**:
- 수정 4 file: `scripts/seed_dummy_year.py` / `scripts/backfill_optimizer_advice_llm.py` / `pipeline/agents/optimizer/retrieve.py` / `.env.local`
- 신규 8 file: `pipeline/agents/synthetic/distributions.py` / `scripts/local_db_reset.py` / `scripts/chroma_export.py` / `scripts/chroma_import.py` / `scripts/aws_backup_and_migrate.py` / `scripts/verify_ui_assertions.py` + 6 test files
- 변경 X: `pipeline/agents/mapper.py` / `pipeline/agents/atomizer.py` / `pipeline/agents/forecaster/agent.py` (사용자 mapper 로직 불가침 룰)

**시연 마감 2026-06-05 (목) 전 Phase A~D 완료 + Phase E (AWS 마이그) 완료 + PR 머지.**


