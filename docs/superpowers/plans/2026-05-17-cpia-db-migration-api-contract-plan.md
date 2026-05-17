# CPIA DB Migration + API Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A 로컬에서 작성/검증한 pipeline 산출 (PR #19 schema/코드 + 더미 시드) 을 homelab prod PG/Chroma 에 단방향 반영하여 prod 시뮬 1건 end-to-end 호출이 작동하는 상태를 만든다. 동시에 B_Track 가 fetch 할 수 있도록 `docs/architecture/api-contract.md` 계약 spec 을 박는다.

**Architecture:** infra/postgres/init.sql 갱신 + 멱등 ALTER migration 1건 + Markdown api-contract.md 신규 + seed_sites.sql 신규 = 5 산출. 그 후 prod 측 적용 (옵션 A: cloudflared tunnel 통한 5 sql sequence / 옵션 B: 조형준 측 docker volume 재생성) + 데이터 시드 3 호출 (load_master_list / synthetic_v2 / sites seed) + 시뮬 1건 호출. 코드 변경 0 — agents 가 GraphConfig DI 라 환경변수 swap 만으로 dev↔prod 전환.

**Tech Stack:** PostgreSQL 16 (asyncpg), ChromaDB 0.5.20 (cloudflared TCP tunnel), Python 3.11 + uv, Azure OpenAI (gpt-5.1-chat-ai-board-test + text-embedding-3-small 1536d), LangGraph 0.2+ (PostgresSaver).

**선행 (이미 완료)**:
- PR #19 main 머지 — HIL 1 + Forecaster fix + Reporter + PostgresSaver
- viazoai/CPIA#21 — homelab PG cpia user password sync (K7mP2xQ9nR4v)
- prod tunnel 검증 (2026-05-17 16:30): `cloudflared access tcp --hostname cpia-pg.zoai.uk --url localhost:5532` + cpia/K7mP2xQ9nR4v 접속 OK
- A_LOCAL 회귀 baseline: 197 PASS + 1 xfailed

**Hard Gate (Task 6/7/9 진입 전 사용자/조형준 측 조치)**: prod Chroma tunnel hostname 확정 (추정 `cpia-chroma.zoai.uk`, HTTP 443 SSL 모드 권장) + 활성.

---

## File Structure

| 파일 | 변경 종류 | 책임 |
|---|---|---|
| `infra/postgres/init.sql` | Modify | sites 테이블 정의에 4 컬럼 (location/headcount/hours_saved/fte_saved) 추가. 재 init 시 final schema 1회 적용 |
| `infra/postgres/migrations/2026-05-17_db_alignment.sql` | Create | sites +4 컬럼 멱등 ALTER. 운영 중 PG 에 sequence apply 용 (옵션 A) |
| `scripts/seed_sites.sql` | Create | fixture `data/mock_sites.json` 6건 INSERT (5 mock + 1 real m15x-ph3-ibl) |
| `docs/schema/postgres.md` | Modify | mapping_corrections (drift #N2) / daily_reports (drift #N3) / sites (4 신규) 실 init.sql 정합 정정 |
| `docs/architecture/api-contract.md` | Create | PG↔types.ts 매핑 표 + 8 endpoint 명세 + sample JSON + derived 계산식 + 환경 분리 정책 (~500 lines) |
| `.env.prod` (선택) | Create | prod 환경변수 별 파일 (`ln -sf .env.prod .env` 로 활성). 또는 inline override |

`pipeline/` 코드 변경 = **0**. agents 가 GraphConfig DI 받음, config 가 환경변수 읽음.

---

## Task 0: 환경 점검 + 회귀 baseline + tunnel Hard Gate

**의존**: 없음 (시작 task)

**Files:** 없음 (검증만)

- [ ] **Step 0.1: 작업 디렉토리 + 브랜치 확인**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git status
git rev-parse --abbrev-ref HEAD
```
Expected: branch=A_Track, working tree clean (또는 본 cycle 의 spec commit 만).

- [ ] **Step 0.2: dev 회귀 baseline 재확인 (197 PASS + 1 xfailed)**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/ -q --no-header 2>&1 | tail -5
```
Expected: `197 passed, 1 xfailed in ...s` (PR #19 시점과 동일). 만약 mismatch 면 stop + 조사.

- [ ] **Step 0.3: dev PG (5432) 연결 확인**

Run:
```bash
nc -zv localhost 5432 2>&1 | head -2
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5432/cpia')
    tables = await c.fetch(\"SELECT count(*) FROM pg_tables WHERE schemaname='public'\")
    print(f'A_LOCAL tables = {tables[0][0]}')
    await c.close()
asyncio.run(main())
"
```
Expected: 5432 OPEN, `A_LOCAL tables = 11` (init.sql 7 + LangGraph 자동 4).

- [ ] **Step 0.4: prod PG (5532 tunnel) 연결 확인 (= cloudflared tunnel 활성 검증)**

Run:
```bash
# tunnel 안 떠있으면 띄움 (이미 떠있으면 reuse)
pgrep -f "cloudflared access tcp.*cpia-pg" > /dev/null || \
  cloudflared access tcp --hostname cpia-pg.zoai.uk --url localhost:5532 > /tmp/cf-cpia-pg.log 2>&1 &
sleep 3

pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia', timeout=10)
    tables = await c.fetch(\"SELECT count(*) FROM pg_tables WHERE schemaname='public'\")
    print(f'PROD tables = {tables[0][0]}')
    await c.close()
asyncio.run(main())
"
```
Expected: `PROD tables = 7` (init.sql 옛 버전, LangGraph 4 자동테이블 없음).

- [ ] **Step 0.5: prod Chroma tunnel Hard Gate**

```bash
# 조형준 측 확정 hostname 으로 try (cpia-chroma.zoai.uk 추정)
curl -fsS "https://cpia-chroma.zoai.uk/api/v1/heartbeat" 2>&1 | head -3
```
Expected: `{"nanosecond heartbeat": ...}` 류 JSON 응답.

만약 fail (DNS NXDOMAIN / 401 / 403) → **STOP + 사용자에게 조형준 측 확정 hostname 요청**. 본 plan Task 6/7/9 진입 불가.

성공 시 Chroma 환경변수 후속 task 용 export:
```bash
export PROD_CHROMA_HOST=cpia-chroma.zoai.uk
export PROD_CHROMA_PORT=443
export PROD_CHROMA_SSL=true
```

- [ ] **Step 0.6: A_LOCAL ↔ PROD schema diff 재확인**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
TABLES = ['sites', 'pipeline_runs', 'activity_master', 'forecasts', 'optimizer_advice', 'mapping_corrections', 'daily_reports']
async def main():
    a = await asyncpg.connect(host='127.0.0.1', port=5432, user='cpia', password='cpia', database='cpia')
    p = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    for t in TABLES:
        an = await a.fetchval(f"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}'")
        pn = await p.fetchval(f"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}'")
        print(f"{t:25s}  A_LOCAL={an}  PROD={pn}  {'✓' if an==pn else '⚠️'}")
    await a.close(); await p.close()
asyncio.run(main())
PY
```
Expected (spec §4 정합):
```
sites                      A_LOCAL=8   PROD=8   ✓
pipeline_runs              A_LOCAL=9   PROD=8   ⚠️
activity_master            A_LOCAL=22  PROD=21  ⚠️
forecasts                  A_LOCAL=29  PROD=9   ⚠️
optimizer_advice           A_LOCAL=11  PROD=7   ⚠️
mapping_corrections        A_LOCAL=6   PROD=6   ✓
daily_reports              A_LOCAL=7   PROD=7   ✓
```

→ 결론: prod 가 2026-05-14 시점의 init.sql 만 적용된 상태. 본 cycle Task 5 에서 5 migrations sequence apply 또는 docker volume 재생성으로 정합.

---

## Task 1: init.sql 갱신 + 신규 migration sql

**의존**: Task 0 완료

**Files:**
- Modify: `infra/postgres/init.sql` (sites 블록)
- Create: `infra/postgres/migrations/2026-05-17_db_alignment.sql`

- [ ] **Step 1.1: 현재 init.sql 의 sites 블록 확인**

Run:
```bash
grep -n -A 15 "CREATE TABLE IF NOT EXISTS sites" infra/postgres/init.sql
```
Expected: line ~145 부근에 8 컬럼 정의 (site_id / name / plan_progress / actual_progress / status / last_run_id / is_mock / updated_at).

- [ ] **Step 1.2: init.sql 의 sites 블록에 4 컬럼 추가**

Use Edit tool — `is_mock BOOLEAN NOT NULL DEFAULT TRUE,` 다음에 4 컬럼 + 코멘트 추가:

```sql
    is_mock           BOOLEAN      NOT NULL DEFAULT TRUE,
    -- 2026-05-17: B_Track Dashboard Layer 1 카드 필드 (api-contract.md §3.1)
    location          TEXT,
    headcount         INT,
    hours_saved       NUMERIC,
    fte_saved         NUMERIC,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
```

- [ ] **Step 1.3: 신규 migration sql 작성**

Create `infra/postgres/migrations/2026-05-17_db_alignment.sql`:

```sql
-- 2026-05-17 — sites +4 컬럼 (B_Track Dashboard Layer 1 카드)
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §5
-- 멱등 (IF NOT EXISTS) — 두 번 돌려도 무방

BEGIN;
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS location    TEXT,
  ADD COLUMN IF NOT EXISTS headcount   INT,
  ADD COLUMN IF NOT EXISTS hours_saved NUMERIC,
  ADD COLUMN IF NOT EXISTS fte_saved   NUMERIC;
COMMIT;
```

- [ ] **Step 1.4: dev PG (5432) 에 migration 적용 (멱등 검증)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5432/cpia')
    sql = open('infra/postgres/migrations/2026-05-17_db_alignment.sql').read()
    await c.execute(sql)
    cols = await c.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='sites' ORDER BY ordinal_position")
    print('sites columns after migration:')
    for r in cols: print(f"  {r['column_name']}")
    await c.close()
asyncio.run(main())
PY
```
Expected (12 컬럼, 4 신규 = location, headcount, hours_saved, fte_saved):
```
sites columns after migration:
  site_id
  name
  plan_progress
  actual_progress
  status
  last_run_id
  is_mock
  location
  headcount
  hours_saved
  fte_saved
  updated_at
```

- [ ] **Step 1.5: migration 두 번 돌려서 멱등 검증**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5432/cpia')
    sql = open('infra/postgres/migrations/2026-05-17_db_alignment.sql').read()
    await c.execute(sql)  # 2회차
    print('2회차 OK (멱등 검증)')
    await c.close()
asyncio.run(main())
PY
```
Expected: `2회차 OK (멱등 검증)`. ALTER COLUMN 이 이미 있어도 `IF NOT EXISTS` 로 skip.

- [ ] **Step 1.6: dev 회귀 재실행 (sites +4 컬럼 후)**

Run:
```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -m pytest pipeline/ -q --no-header 2>&1 | tail -5
```
Expected: `197 passed, 1 xfailed` (기존 test 가 sites SELECT 안 함, 회귀 무관).

- [ ] **Step 1.7: commit**

```bash
git add infra/postgres/init.sql infra/postgres/migrations/2026-05-17_db_alignment.sql
git commit -m "$(cat <<'EOF'
feat(schema): sites +4 컬럼 (location/headcount/hours_saved/fte_saved)

B_Track Dashboard Layer 1 카드 필드. init.sql 갱신 + 멱등 ALTER migration.
- location TEXT — 현장 위치 (청주/평택/미국/이천)
- headcount INT — 현장 전체 근무 인원 (Impact 분모)
- hours_saved NUMERIC — 월 절감 시간
- fte_saved NUMERIC — 확보 FTE

dev 회귀 197 PASS + 1 xfailed 유지 (sites SELECT path 없음, 무관).
멱등 검증: 2회차 ALTER 도 IF NOT EXISTS 로 skip.

Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §5

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: docs/schema/postgres.md 정정 (drift #N2 + #N3 흡수)

**의존**: Task 1 완료

**Files:**
- Modify: `docs/schema/postgres.md`

- [ ] **Step 2.1: postgres.md §5 daily_reports 블록 정정**

현재 spec (잘못):
```sql
date             DATE NOT NULL,
summary          JSONB,
```

실 init.sql 정합으로 정정:
```sql
report_date      DATE NOT NULL,
bp_name          TEXT,
history_csv_row  JSONB,
```

코멘트도 정정 — `summary` 명칭이 reporter.py 의 변수명, 컬럼명은 `history_csv_row` (CSV row 누적 의도).

- [ ] **Step 2.2: postgres.md §8 mapping_corrections 블록 정정**

현재 spec (잘못):
```sql
CREATE TABLE mapping_corrections (
    id, run_id, date NOT NULL,
    work_content TEXT NOT NULL,
    company TEXT, trade TEXT,
    original JSONB NOT NULL,
    corrected JSONB NOT NULL,
    correction_type TEXT,
    created_at
);
CREATE INDEX ... GIN (work_content);
```

실 init.sql 정합 (6 컬럼만, JSONB 안에 박음):
```sql
CREATE TABLE mapping_corrections (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    report_date     DATE NOT NULL,
    original        JSONB NOT NULL,     -- {work_content, company, trade, wa, l6_main, mapping_conf, mapping_source}
    corrected       JSONB NOT NULL,     -- {wa, l6_main, mapping_source, correction_type}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mapping_corrections_date ON mapping_corrections (report_date DESC);
```

`§11 미해결 사안` 의 ② 항목 (Mapper 자가학습) 옆에 별 섹션 추가:

```markdown
### 미래 의도 (drift D-1 / 자가학습 cycle 묶음)

위 §11 ② 의 Mapper 자가학습 기능 구현 시점에 mapping_corrections schema 를 다음과
같이 확장한다 (별 PR 묶음):
- work_content TEXT (top-level), company TEXT, trade TEXT, correction_type TEXT
- GIN index on to_tsvector('simple', work_content)
- 백필 SQL: UPDATE ... SET work_content = original->>'work_content' WHERE work_content IS NULL
- insert_mapping_correction signature 변경 (4 인자 추가)
- fetch_similar_corrections SELECT 함수 신규

본 cycle (2026-05-17) 는 현 호출 path 0 검증 후 YAGNI 룰로 보류.
```

- [ ] **Step 2.3: postgres.md §1 sites 블록 정정 (4 신규 컬럼 반영)**

`CREATE TABLE sites` 블록에 4 컬럼 추가 (Task 1.2 의 init.sql 과 동일).

- [ ] **Step 2.4: postgres.md §12 변경 이력에 본 cycle 라인 추가**

```markdown
| 2026-05-17 | mapping_corrections / daily_reports 실 init.sql 정합 정정 (drift #N2+#N3 흡수). sites +4 컬럼 (location/headcount/hours_saved/fte_saved). 마이그레이션: `2026-05-17_db_alignment.sql` | A 트랙 |
```

- [ ] **Step 2.5: postgres.md 정합 grep 검증 (date → report_date / summary → history_csv_row 흔적)**

Run:
```bash
grep -n "summary\|^    date " docs/schema/postgres.md | head -10
```
Expected: `summary` 표기 1~2건 (변경 이력 또는 reporter.py 변수명 언급 한정), `date` 컬럼 표기 0건.

- [ ] **Step 2.6: commit**

```bash
git add docs/schema/postgres.md
git commit -m "$(cat <<'EOF'
docs(schema): postgres.md 실 init.sql 정합 정정 (drift #N2+#N3 흡수)

- §5 daily_reports: date → report_date, summary → history_csv_row, +bp_name (drift #N3)
- §8 mapping_corrections: 4 컬럼만 (work_content/company/trade/correction_type top-level 제거, drift #N2)
  + 미래 의도 (drift D-1 자가학습 cycle 묶음) 별 섹션 명시
- §1 sites: +4 컬럼 (location/headcount/hours_saved/fte_saved)
- §12 변경 이력 라인 추가

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: docs/architecture/api-contract.md 신규 작성

**의존**: Task 2 완료

**Files:**
- Create: `docs/architecture/api-contract.md` (0 → ~500 lines)

- [ ] **Step 3.1: api-contract.md 헤더 + 환경 분리 정책 (§1)**

Create `docs/architecture/api-contract.md` 첫 섹션:

```markdown
# CPIA API Contract

> **A_Track (pipeline) ↔ B_Track (web/) 계약 spec**. 본 문서는 PG schema 와 `web/lib/types.ts` 간 매핑 + endpoint 8건 명세. FastAPI 구현 (pipeline/api.py) 은 별 cycle, 본 문서는 계약만.
>
> 작성: 2026-05-17, 기반 PR #19 + spec `docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md`

## §1. 환경 분리 정책

| 환경 | 용도 | POSTGRES_URL | CHROMA_HOST |
|---|---|---|---|
| dev | A_Track 본인 개발 + 회귀 197 PASS + 빠른 iteration | localhost:5432 (cpia-pg-local) | localhost:8000 |
| prod | 데모 + 서비스 + B_Track fetch | 127.0.0.1:5532 (cloudflared tunnel cpia-pg.zoai.uk) | cpia-chroma.zoai.uk:443 SSL |

전환 = `.env.local` 한 줄 swap 또는 inline env override. **코드 변경 0** (agents 가 GraphConfig DI).

dev 가 prod 안 가리키는 사유: Azure 비용 매 회귀 (~$0.5×197=$100+), Chroma upsert 오염, cloudflared latency, 동시 작업 충돌.
```

- [ ] **Step 3.2: PG↔types.ts 매핑 표 (§2)**

```markdown
## §2. PG↔types.ts 매핑

### §2.1 Site (sites + forecasts LEFT JOIN 집계)

| types.ts field | 출처 | 산식 |
|---|---|---|
| id                       | sites.site_id              | 직접 |
| name                     | sites.name                 | 직접 |
| location                 | sites.location             | 직접 (신규 컬럼) |
| status                   | sites.status               | 직접 ('normal'/'caution'/'risk'/'unknown') |
| progress_planned         | sites.plan_progress        | 직접 (rename) |
| progress_actual          | sites.actual_progress      | 직접 (rename) |
| gap_percent              | derived                    | actual_progress - plan_progress |
| productivity_today       | forecasts agg              | MAX(forecasts.today_productivity WHERE run_id=last_run_id) |
| spi                      | derived                    | actual_progress / plan_progress (zero-guard) |
| abnormal_trades          | forecasts agg              | COUNT(forecasts WHERE risk_level<>'정상' AND run_id=last_run_id) |
| fte_saved                | sites.fte_saved            | 직접 (신규 컬럼) |
| hours_saved              | sites.hours_saved          | 직접 (신규 컬럼) |
| headcount                | sites.headcount            | 직접 (신규 컬럼) |
| total_hours              | derived                    | headcount × 140 |
| ai_replacement_rate      | derived                    | hours_saved / total_hours × 100 (zero-guard) |
| expected_completion      | forecasts agg              | MAX(forecasts.expected_completion WHERE run_id=last_run_id) |
| recovered_completion     | optimizer_advice agg       | MAX(... recovery 반영 expected_completion, Phase 2) — PoC 는 expected_completion 동일 |
| delay_days               | forecasts agg              | MAX(forecasts.delay_days WHERE run_id=last_run_id) |
| recovery_days            | optimizer_advice agg       | MAX(... recovery_distribution 기반) — PoC 는 0 또는 단순 추정 |

### §2.2 ReviewItem (LangGraph state.mapped + requires_review filter)

| types.ts field | 출처 | 산식 |
|---|---|---|
| id                  | derived             | f"r-{run_id[:8]}-{idx:03d}" (idx = mapped 배열 index) |
| bp_name             | state.mapped[idx].company | 직접 |
| work_content        | state.mapped[idx].work_content | 직접 |
| quantity            | state.mapped[idx].quantity | 직접 |
| unit                | state.mapped[idx].unit | 직접 |
| ai_mapped_wp_id     | state.mapped[idx].wa | 직접 |
| ai_mapped_path      | derived             | "{l5_disc} > {l6_main} > {l7_sub} {l7_5_activity}" |
| confidence          | state.mapped[idx].mapping_conf | 직접 |
| status              | derived             | 'unconfirmed' (HIL 1 interrupt 시점) |
| alternative_wps     | (Phase 2)           | 본 PoC 빈 배열 |

### §2.3 ReportDetail (daily_reports + forecasts + optimizer_advice)

| types.ts field | 출처 |
|---|---|
| kpi                 | daily_reports.history_csv_row JSONB (total_workers / risk_counts / advice_count) + forecasts/optimizer_advice 집계 |
| s_curve             | (Phase 2 — PoC 빈 배열 또는 단순 plan_progress/actual_progress 점) |
| contractor_bars     | mapped Activity 의 company 별 productivity 집계 |
| trade_bars          | forecasts row 별 today_productivity / l6_main |
| quadrant            | forecasts row 별 (productivity vs impact = remaining qty) |
| raw_data            | mapped Activity[] 직접 |

### §2.4 OptimizerOutput (optimizer_advice 직접)

| types.ts field | 출처 |
|---|---|
| wp_id              | optimizer_advice.l6_main (또는 company+l6_main 조합) |
| diagnosis          | optimizer_advice.diagnosis |
| similar_cases      | optimizer_advice.degradation_cases JSONB |
| recommendations    | optimizer_advice.recommendations JSONB (ranked list) |
| details            | derived (recovery_distribution 등) |
```

- [ ] **Step 3.3: Endpoint 8건 명세 (§3)**

```markdown
## §3. Endpoints (8)

### §3.1 GET /api/sites

**용도**: Dashboard Layer 1 카드 (전 site 리스트 + derived/aggregate)

**Query params**: 없음

**Response 200**: `Site[]`

**Sample**:
```json
[
  {
    "id": "m15x-ph3-ibl",
    "name": "M15X Ph-3 IBL",
    "location": "청주",
    "status": "risk",
    "progress_planned": 38.5,
    "progress_actual": 34.2,
    "gap_percent": -4.3,
    "productivity_today": 88,
    "spi": 0.89,
    "abnormal_trades": 1,
    "fte_saved": 1.6,
    "hours_saved": 221,
    "headcount": 65,
    "total_hours": 9100,
    "ai_replacement_rate": 2.4,
    "expected_completion": "2026-08-12",
    "recovered_completion": "2026-08-03",
    "delay_days": 14,
    "recovery_days": 9
  }
]
```

**SQL** (FastAPI 구현 시 참조):
```sql
SELECT s.site_id, s.name, s.location, s.status,
       s.plan_progress, s.actual_progress,
       (s.actual_progress - s.plan_progress) AS gap_percent,
       CASE WHEN s.plan_progress > 0 THEN s.actual_progress / s.plan_progress ELSE NULL END AS spi,
       COALESCE(f.today_productivity, 0) AS productivity_today,
       COALESCE(f.abnormal_trades, 0) AS abnormal_trades,
       s.fte_saved, s.hours_saved, s.headcount,
       (s.headcount * 140) AS total_hours,
       CASE WHEN s.headcount > 0 THEN s.hours_saved / (s.headcount * 140) * 100 ELSE 0 END AS ai_replacement_rate,
       f.expected_completion, f.delay_days
FROM sites s
LEFT JOIN LATERAL (
  SELECT MAX(today_productivity) AS today_productivity,
         COUNT(*) FILTER (WHERE risk_level <> '정상') AS abnormal_trades,
         MAX(expected_completion) AS expected_completion,
         MAX(delay_days) AS delay_days
  FROM forecasts WHERE run_id = s.last_run_id
) f ON TRUE;
```

### §3.2 GET /api/sites/:site_id

**용도**: Site detail page (Forecaster/Optimizer 집계 포함)

**Response**: `Site & { forecasts: ForecastRow[], advice: OptimizerOutput[] }`

### §3.3 GET /api/runs/:run_id

**Response**: `RunStatus = { run_id, site_id, report_date, status, current_node, atomized_count, started_at, completed_at, error }` (pipeline_runs row)

### §3.4 GET /api/runs/:run_id/report

**Response**: `{ report_md: string, history_csv_row: object, bp_name: string | null }` (daily_reports row)

### §3.5 GET /api/runs/:run_id/forecasts

**Response**: `ForecastRow[]` — forecasts WHERE run_id = :run_id

### §3.6 GET /api/runs/:run_id/optimizer

**Response**: `OptimizerOutput[]` — optimizer_advice WHERE run_id = :run_id

### §3.7 GET /api/runs/:run_id/review

**Response**: `ReviewItem[]` — LangGraph checkpoint state.mapped 중 `requires_review=True`

**구현 노트**: PostgresSaver 의 checkpoints 테이블 에서 thread_id=run_id 의 최신 state snapshot fetch → mapped filter → ReviewItem shape 변환.

### §3.8 POST /api/runs/:run_id/hil_1/resume

**Request body**: `{ corrections: { [idx: string]: { wa: string, l6_main: string } } }`

(주의: dict key 는 **string** 필수, int 면 LangGraph TypeError — drift #N5)

**Response**: `{ next_node: string }` (resume 후 진행 노드)

**구현 노트**: LangGraph `Command(resume=corrections)` 호출 + ainvoke 재진입. hil_1_node 가 int(k) 변환 처리.
```

- [ ] **Step 3.4: derived 계산식 + 의도된 비포함 (§4)**

```markdown
## §4. Derived 계산식 (API layer 가 채움)

```python
gap_percent          = actual_progress - plan_progress
spi                  = actual_progress / plan_progress if plan_progress > 0 else None
total_hours          = headcount * 140
ai_replacement_rate  = hours_saved / total_hours * 100 if total_hours > 0 else 0
productivity_today   = max(f.today_productivity for f in forecasts) if forecasts else 0
abnormal_trades      = sum(1 for f in forecasts if f.risk_level != '정상')
delay_days           = max((f.delay_days for f in forecasts), default=0)
expected_completion  = max((f.expected_completion for f in forecasts), default=None)
recovered_completion = expected_completion  # PoC, Phase 2 = Optimizer recovery 반영
recovery_days        = 0  # PoC, Phase 2 = recovery_distribution 기반
```

## §5. 의도된 비포함 (다음 cycle 권고)

- 구현 FastAPI `pipeline/api.py` — 다음 cycle (drift D-4)
- web/lib/fixtures.ts → 실 API swap — FastAPI 구현 cycle 의 점진 (drift D-5)
- HIL 1 review POST API (현재 GET 만) — 위 §3.8 정의됨
- SSE / WebSocket 진행 상태 stream — Phase 2
- 인증/인가 — homelab 내부 trust 만, Phase 2 (Cloudflare Access)
- pagination / filter — sites/runs 적은 PoC 라 불필요, Phase 2
```

- [ ] **Step 3.5: api-contract.md 변경 이력 (§6)**

```markdown
## §6. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-17 | 초안 — PG↔types.ts 매핑 + 8 endpoint + derived 계산식 + 환경 분리 정책 | A_Track |
```

- [ ] **Step 3.6: api-contract.md lines check (~200-300 lines 목표)**

Run:
```bash
wc -l docs/architecture/api-contract.md
```
Expected: `200~350 docs/architecture/api-contract.md` 라인. 너무 작으면 (~50) 빠진 § 있음, 너무 크면 (~500+) 불필요한 sample 과다.

- [ ] **Step 3.7: commit**

```bash
git add docs/architecture/api-contract.md
git commit -m "$(cat <<'EOF'
docs(architecture): api-contract.md 신규 (PG↔types.ts + 8 endpoint)

A_Track ↔ B_Track 계약 spec. FastAPI 구현 (pipeline/api.py) 은 다음 cycle,
본 문서는 계약만.

- §1 환경 분리 정책 (dev/prod, 코드 변경 0)
- §2 PG↔types.ts 매핑 (Site/ReviewItem/ReportDetail/OptimizerOutput 4 type)
- §3 endpoint 8건 명세 (path/method/query/response shape/sample JSON/SQL)
- §4 derived 계산식 (gap_percent/spi/total_hours/ai_replacement_rate/집계)
- §5 의도된 비포함 (FastAPI 구현 / fixture swap / SSE / auth / pagination = 다음 cycle)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: scripts/seed_sites.sql 신규

**의존**: Task 1 완료 (sites +4 컬럼 schema)

**Files:**
- Create: `scripts/seed_sites.sql`

- [ ] **Step 4.1: fixture data/mock_sites.json 실측 재확인 (6 site)**

Run:
```bash
pipeline/.venv/bin/python3 -c "
import json
sites = json.load(open('data/mock_sites.json'))
print(f'총 {len(sites)} site')
for s in sites:
    print(f\"  {s['id']:18s} {s['name']:20s} {s['location']:8s} {s['status']:8s} plan={s['progress_planned']:5.1f} actual={s['progress_actual']:5.1f} headcount={s['headcount']:3d} hours_saved={s['hours_saved']:4d} fte_saved={s['fte_saved']}\")
"
```
Expected: 6 site 정확 (m15x-ph3-ibl / y1-ph1-obl / indiana-hac / pt3-extension / m15x-obl-pt7 / y1-ph1-ibl).

- [ ] **Step 4.2: scripts/seed_sites.sql 작성 (fixture 와 1:1)**

Create `scripts/seed_sites.sql`:

```sql
-- 2026-05-17 — sites 6 seed (fixture data/mock_sites.json → PG)
-- 5 mock + 1 real (m15x-ph3-ibl PoC). is_mock 으로 구분.
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §7.3
-- fixture 와 1:1 정합: id/name/location/status/plan_progress/actual_progress/headcount/hours_saved/fte_saved

INSERT INTO sites (site_id, name, location, status, plan_progress, actual_progress, headcount, hours_saved, fte_saved, is_mock)
VALUES
  ('m15x-ph3-ibl',   'M15X Ph-3 IBL',   '청주', 'risk',    38.5, 34.2,  65, 221, 1.6, FALSE),
  ('y1-ph1-obl',     'Y-1 Ph-1 OBL',    '평택', 'normal',  62.1, 62.5, 130, 832, 5.9, TRUE),
  ('indiana-hac',    'Indiana Fab HAC', '미국', 'normal',  48.7, 48.6,  60, 353, 2.5, TRUE),
  ('pt3-extension',  'P&T 3 증축',       '이천', 'normal',  71.4, 72.6,  50, 255, 1.8, TRUE),
  ('m15x-obl-pt7',   'M15X OBL & PT7',  '청주', 'normal',  22.8, 22.5,  50, 246, 1.7, TRUE),
  ('y1-ph1-ibl',     'Y-1 Ph-1 IBL',    '평택', 'normal',  55.6, 55.8,  90, 248, 1.8, TRUE)
ON CONFLICT (site_id) DO UPDATE SET
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  status = EXCLUDED.status,
  plan_progress = EXCLUDED.plan_progress,
  actual_progress = EXCLUDED.actual_progress,
  headcount = EXCLUDED.headcount,
  hours_saved = EXCLUDED.hours_saved,
  fte_saved = EXCLUDED.fte_saved,
  is_mock = EXCLUDED.is_mock,
  updated_at = NOW();
```

- [ ] **Step 4.3: dev PG 에 seed 적용 (idempotent 검증)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5432/cpia')
    sql = open('scripts/seed_sites.sql').read()
    await c.execute(sql)
    n = await c.fetchval('SELECT count(*) FROM sites')
    real = await c.fetchval("SELECT site_id FROM sites WHERE is_mock=FALSE")
    print(f'sites row count = {n}')
    print(f'real (is_mock=FALSE) = {real}')
    await c.close()
asyncio.run(main())
PY
```
Expected:
```
sites row count = 6
real (is_mock=FALSE) = m15x-ph3-ibl
```

- [ ] **Step 4.4: seed 두 번 돌려서 idempotent 검증 (ON CONFLICT DO UPDATE)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://cpia:cpia@localhost:5432/cpia')
    sql = open('scripts/seed_sites.sql').read()
    await c.execute(sql)  # 2회차
    n = await c.fetchval('SELECT count(*) FROM sites')
    print(f'2회차 후 sites row count = {n}')  # 여전히 6 (DO UPDATE, 중복 INSERT X)
    await c.close()
asyncio.run(main())
PY
```
Expected: `2회차 후 sites row count = 6`. ON CONFLICT 덕분에 중복 안 됨.

- [ ] **Step 4.5: commit**

```bash
git add scripts/seed_sites.sql
git commit -m "$(cat <<'EOF'
feat(seed): sites 6 seed (5 mock + 1 real, data/mock_sites.json 정합)

fixture 와 1:1 동기: id/name/location/status/plan_progress/actual_progress/
headcount/hours_saved/fte_saved.

real (is_mock=FALSE): m15x-ph3-ibl (M15X Ph-3 IBL, 청주, risk)
mock (5건): y1-ph1-obl, indiana-hac, pt3-extension, m15x-obl-pt7, y1-ph1-ibl

ON CONFLICT (site_id) DO UPDATE 으로 idempotent. dev 적용 + 2회차 검증 OK.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: prod schema sync (옵션 A 우선, 옵션 B fallback)

**의존**: Task 1 commit. (옵션 B 만 추가 의존: 조형준 측 git pull + docker 권한)

**Files:** 없음 (prod 측 sql 적용만, 본인 commit 없음)

### Step 5.0: 옵션 A vs B 결정

조형준 측 응답 가능 + prod 머신 git/docker 권한 있음 → 옵션 B (가장 깔끔).
조형준 측 응답 없음 / 1시간 이상 대기 / A 머신 단독 진행 → 옵션 A (cloudflared tunnel 통해 5 sql sequence).

**권고 우선순위**: 본 cycle 진행 속도 위해 옵션 A 우선 (본인 권한만으로 가능). 옵션 B 는 조형준 측 응답 시점에 prod 머신 cleaner init 원하면 전환.

### 옵션 A — A 머신에서 cloudflared tunnel 통해 5 sql sequence apply

- [ ] **Step 5A.1: cloudflared tunnel 활성 재확인**

Run:
```bash
nc -zv localhost 5532 2>&1 | head -2
```
Expected: `Connection to localhost port 5532 [tcp/*] succeeded!`. fail 면 Task 0.4 재실행.

- [ ] **Step 5A.2: prod 의 현 schema 재dump (적용 전 baseline)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    for t in ['sites', 'pipeline_runs', 'activity_master', 'forecasts', 'optimizer_advice']:
        n = await c.fetchval(f"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}'")
        print(f'{t}: {n} cols')
    await c.close()
asyncio.run(main())
PY
```
Expected (baseline): sites=8, pipeline_runs=8, activity_master=21, forecasts=9, optimizer_advice=7.

- [ ] **Step 5A.2.5: prod 의 데이터 보존 가드 (Critical — `2026-05-16_downstream_agents.sql` 의 `DROP TABLE forecasts` 가 silent data loss)**

`2026-05-16_downstream_agents.sql` 의 `DROP TABLE IF EXISTS forecasts; CREATE TABLE forecasts ...` 패턴은 prod 에 forecasts 데이터가 있으면 silent 손실. apply 전 모든 영향 테이블 row=0 확인 필수. 0 아니면 hard STOP (옵션 B 또는 데이터 보존 계획 수립).

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg, sys
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    all_zero = True
    for t in ['forecasts', 'optimizer_advice', 'pipeline_runs', 'mapping_corrections', 'daily_reports', 'activity_master', 'sites']:
        try:
            n = await c.fetchval(f'SELECT count(*) FROM "{t}"')
        except Exception:
            n = -1
        ok = (n == 0)
        all_zero = all_zero and ok
        print(f'{t:25s} rows = {n}  {"OK (empty)" if ok else "⚠️ NON-EMPTY"}')
    await c.close()
    if not all_zero:
        print('\n=== HARD STOP ===')
        print('prod 가 비어있지 않음 — Step 5A.3 의 DROP TABLE 이 데이터 손실.')
        print('대응: 옵션 B 로 전환 (조형준 측 docker compose down -v) 또는')
        print('     데이터 보존 계획 수립 (pg_dump → 마이그 후 restore)')
        sys.exit(1)
    print('\n=== ALL EMPTY — Step 5A.3 진입 안전 ===')
asyncio.run(main())
PY
```
Expected: 모든 `rows = 0` + `ALL EMPTY — Step 5A.3 진입 안전`. exit 0.

만약 non-empty 면 `HARD STOP` + exit 1 → Step 5A.3 진입 금지. 사용자에게 옵션 B 전환 또는 데이터 보존 계획 협의.

- [ ] **Step 5A.3: 5 sql sequence apply**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg

async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    for f in [
        'infra/postgres/migrations/2026-05-16_downstream_agents.sql',
        'infra/postgres/migrations/2026-05-16_forecaster.sql',
        'infra/postgres/migrations/2026-05-16_optimizer_hil2.sql',
        'infra/postgres/migrations/20260516_add_activity_master.sql',
        'infra/postgres/migrations/2026-05-17_db_alignment.sql',
    ]:
        sql = open(f).read()
        try:
            await c.execute(sql)
            print(f'OK {f}')
        except Exception as e:
            print(f'FAIL {f} — {type(e).__name__}: {str(e)[:100]}')
            raise
    await c.close()
asyncio.run(main())
PY
```
Expected: 모든 5건 OK. 만약 `DROP TABLE IF EXISTS forecasts` 등에서 fail (data loss 우려) → STOP (prod 가 empty 확인 다시 — `SELECT count(*) FROM forecasts` = 0 검증 후 재진입).

- [ ] **Step 5A.4: prod schema diff 재확인 (A_LOCAL = PROD 정합 검증)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
TABLES = ['sites', 'pipeline_runs', 'activity_master', 'forecasts', 'optimizer_advice', 'mapping_corrections', 'daily_reports']
async def main():
    a = await asyncpg.connect(host='127.0.0.1', port=5432, user='cpia', password='cpia', database='cpia')
    p = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    all_ok = True
    for t in TABLES:
        an = await a.fetchval(f"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}'")
        pn = await p.fetchval(f"SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}'")
        ok = an == pn
        all_ok = all_ok and ok
        print(f"{t:25s}  A_LOCAL={an}  PROD={pn}  {'✓' if ok else '⚠️'}")
    print(f"\n{'ALL OK' if all_ok else 'DIFF FOUND'}")
    await a.close(); await p.close()
asyncio.run(main())
PY
```
Expected:
```
sites                      A_LOCAL=12  PROD=12  ✓
pipeline_runs              A_LOCAL=9   PROD=9   ✓
activity_master            A_LOCAL=22  PROD=22  ✓
forecasts                  A_LOCAL=29  PROD=29  ✓
optimizer_advice           A_LOCAL=11  PROD=11  ✓
mapping_corrections        A_LOCAL=6   PROD=6   ✓
daily_reports              A_LOCAL=7   PROD=7   ✓

ALL OK
```

- [ ] **Step 5A.5: 검증 결과 raw 저장 (옵션 — Task 9 commit 시 함께)**

Run:
```bash
mkdir -p docs/audit/raw
pipeline/.venv/bin/python3 <<'PY' > docs/audit/raw/2026-05-17-prod-schema-sync.txt
import asyncio, asyncpg
TABLES = ['sites', 'pipeline_runs', 'activity_master', 'forecasts', 'optimizer_advice', 'mapping_corrections', 'daily_reports']
async def main():
    p = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    for t in TABLES:
        rows = await p.fetch(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='{t}' ORDER BY ordinal_position")
        print(f'=== {t} ===')
        for r in rows:
            print(f"  {r['column_name']:32s} {r['data_type']}")
    await p.close()
asyncio.run(main())
PY
echo "saved: docs/audit/raw/2026-05-17-prod-schema-sync.txt"
```

### 옵션 B — 조형준 측에서 docker volume 재생성 (fallback / 권고 X if prod 가 비어있지 않으면)

- [ ] **Step 5B.1 (조형준 측 실행)**: prod 머신에서 git pull A_Track + docker compose down -v && up -d

```bash
# (조형준 측) prod 머신에서
cd /path/to/CPIA
git fetch origin A_Track
git checkout A_Track
git pull
cd infra
docker compose down -v
docker compose up -d
docker compose ps   # 4 컨테이너 Up 확인
```

→ 본 cycle 의 갱신된 init.sql 1회 적용 + LangGraph checkpoints 자동 생성 (첫 시뮬 호출 시).

- [ ] **Step 5B.2 (본인 측 검증)**: Step 5A.4 와 동일 schema diff 호출. ALL OK 확인.

---

## Task 6: prod activity_master + Chroma wbs_master 적재

**의존**: Task 5 완료 (prod schema sync) + Hard Gate (Chroma tunnel)

**Files:** 없음 (데이터 적재)

- [ ] **Step 6.1: prod tunnel 양쪽 활성 재확인 (PG + Chroma)**

Run:
```bash
# PG tunnel (cloudflared access tcp, 5532 listening)
pgrep -f "cloudflared access tcp.*cpia-pg" > /dev/null && echo "PG tunnel UP" || echo "PG tunnel DOWN — STOP"
nc -zv localhost 5532 2>&1 | head -1

# Chroma tunnel (HTTP heartbeat)
curl -fsS "https://cpia-chroma.zoai.uk/api/v1/heartbeat" 2>&1 | head -3
```
Expected: `PG tunnel UP`, `5532 succeeded`, Chroma heartbeat JSON. fail 면 STOP (Task 0.4 / 0.5 재실행).

- [ ] **Step 6.2: load_master_list.py prod 호출**

Run:
```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
PYTHONPATH="$(pwd)" \
  uv run --project pipeline scripts/load_master_list.py \
  --filter-companies 남웅건설 세보엠이씨 창원기전
```
Expected 출력:
```
[load] 전체 (WA, L6) 그룹: 102
[load] filter 적용 후 그룹: 30
[load] 적재 row: 1059
[load] PG activity_master upsert: 1059 rows
[load] Chroma wbs_master upsert: 30 groups
```

Azure embedding 비용: ~$0.01 (30 doc × text-embedding-3-small).

- [ ] **Step 6.3: prod activity_master row 검증**

Run:
```bash
pipeline/.venv/bin/python3 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    n = await c.fetchval('SELECT count(*) FROM activity_master')
    print(f'PROD activity_master rows = {n}')
    # sample row
    sample = await c.fetchrow('SELECT wbs_activity_id, company, l5_disc, l6_main, unit, plan_total_qty FROM activity_master LIMIT 1')
    print(f'sample: {dict(sample)}')
    await c.close()
asyncio.run(main())
"
```
Expected: `PROD activity_master rows = 1059`, sample row 가 의미 있는 값 (company in {남웅건설, 세보엠이씨, 창원기전}).

- [ ] **Step 6.4: prod Chroma wbs_master group 검증**

ChromaClient method 확정 (`pipeline/chroma_client.py:23`): `get_or_create_wbs_master() → Collection`.

Run:
```bash
CHROMA_HOST=cpia-chroma.zoai.uk CHROMA_PORT=443 CHROMA_SSL=true \
PYTHONPATH="$(pwd)" pipeline/.venv/bin/python3 -c "
import os
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ['CHROMA_PORT']), ssl=os.environ.get('CHROMA_SSL','false').lower()=='true')
coll = c.get_or_create_wbs_master()
print(f'PROD Chroma wbs_master count = {coll.count()}')
"
```
Expected: `PROD Chroma wbs_master count = 30`.

- [ ] **Step 6.5: 검증 raw 저장**

Run:
```bash
echo "Task 6 적재 결과 (2026-05-17)" > docs/audit/raw/2026-05-17-prod-task6-master-load.txt
echo "PG activity_master: 1059 rows" >> docs/audit/raw/2026-05-17-prod-task6-master-load.txt
echo "Chroma wbs_master: 30 groups"  >> docs/audit/raw/2026-05-17-prod-task6-master-load.txt
echo "saved: docs/audit/raw/2026-05-17-prod-task6-master-load.txt"
```

---

## Task 7: prod Chroma synthetic_v2 적재

**의존**: Task 6 완료 (activity_master prod 적재 — synthetic_v2 가 PG 읽어서 적재)

**Files:** 없음 (데이터 적재)

- [ ] **Step 7.0: prod tunnel 양쪽 활성 재확인 (Step 6.1 와 동일 명령)**

```bash
pgrep -f "cloudflared access tcp.*cpia-pg" > /dev/null && echo "PG tunnel UP" || echo "PG tunnel DOWN — STOP"
nc -zv localhost 5532 2>&1 | head -1
curl -fsS "https://cpia-chroma.zoai.uk/api/v1/heartbeat" 2>&1 | head -3
```

- [ ] **Step 7.1: synthetic_v2.py prod 호출**

Run:
```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
PYTHONPATH="$(pwd)" \
  pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_v2 \
  --reference-date 2025-09-25 --days 90 --seed 42
```
Expected 출력 (마지막 line, synthetic_v2.py:357 의 print):
```
OK upserted N rows to Chroma daily_activities. worker_source="synthetic_v2".
```

N 은 30 groups × 90일 × skip 룰 적용 — A_LOCAL 실측 기준 ~2000~2700 row 예상 (정확 값은 plan 실행 시 확인).

Azure embedding 비용: ~$0.05 (~2000 doc × text-embedding-3-small).

- [ ] **Step 7.2: prod Chroma daily_activities 의 synthetic_v2 source 검증**

ChromaClient method 확정 (`pipeline/chroma_client.py:30`): `get_or_create_daily_activities() → Collection`.

Run:
```bash
CHROMA_HOST=cpia-chroma.zoai.uk CHROMA_PORT=443 CHROMA_SSL=true \
PYTHONPATH="$(pwd)" pipeline/.venv/bin/python3 -c "
import os
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ['CHROMA_PORT']), ssl=os.environ.get('CHROMA_SSL','false').lower()=='true')
coll = c.get_or_create_daily_activities()
n = coll.count()
# worker_source='synthetic_v2' filter count
res = coll.get(where={'worker_source': 'synthetic_v2'}, limit=1)
print(f'PROD daily_activities count = {n}')
print(f'sample (synthetic_v2 filter): {res[\"ids\"][:1] if res[\"ids\"] else \"none\"}')
"
```
Expected: count > 0, sample id 있음.

- [ ] **Step 7.3: 검증 raw 저장**

Run:
```bash
echo "Task 7 적재 결과 (2026-05-17)" > docs/audit/raw/2026-05-17-prod-task7-synthetic-v2.txt
echo "Chroma daily_activities synthetic_v2 source: <Step 7.2 출력값>" >> docs/audit/raw/2026-05-17-prod-task7-synthetic-v2.txt
echo "saved: docs/audit/raw/2026-05-17-prod-task7-synthetic-v2.txt"
```

---

## Task 8: prod sites 6 seed (5 mock + 1 real)

**의존**: Task 5 완료 (prod schema sync — sites +4 컬럼)

**Files:** 없음 (데이터 적재)

- [ ] **Step 8.1: scripts/seed_sites.sql prod 적용**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    sql = open('scripts/seed_sites.sql').read()
    await c.execute(sql)
    n = await c.fetchval('SELECT count(*) FROM sites')
    real = await c.fetchval("SELECT site_id FROM sites WHERE is_mock=FALSE")
    print(f'PROD sites rows = {n}')
    print(f'PROD real site = {real}')
    await c.close()
asyncio.run(main())
PY
```
Expected:
```
PROD sites rows = 6
PROD real site = m15x-ph3-ibl
```

- [ ] **Step 8.2: 검증 raw 저장**

Run:
```bash
echo "Task 8 적재 결과 (2026-05-17)" > docs/audit/raw/2026-05-17-prod-task8-sites-seed.txt
echo "PROD sites: 6 rows (5 mock + 1 real m15x-ph3-ibl)" >> docs/audit/raw/2026-05-17-prod-task8-sites-seed.txt
echo "saved: docs/audit/raw/2026-05-17-prod-task8-sites-seed.txt"
```

---

## Task 9: prod 시뮬 1건 end-to-end 검증 (= Done 정의)

**의존**: Task 6 + Task 7 + Task 8 모두 완료

**Files:** 없음 (검증만, raw 저장은 Task 10 commit 묶음)

- [ ] **Step 9.0: prod tunnel 양쪽 활성 재확인 (Step 6.1 와 동일 명령)**

```bash
pgrep -f "cloudflared access tcp.*cpia-pg" > /dev/null && echo "PG tunnel UP" || echo "PG tunnel DOWN — STOP"
nc -zv localhost 5532 2>&1 | head -1
curl -fsS "https://cpia-chroma.zoai.uk/api/v1/heartbeat" 2>&1 | head -3
```

- [ ] **Step 9.1: prod 시뮬 호출 (synthetic_daily_report --site-id m15x-ph3-ibl --auto-select-all)**

**Critical**: `--auto-select-all` 필수. 없으면 synthetic_daily_report.py:456 의 `if args.auto_select_all:` 분기를 안 타고 line 464 `input("선택> ")` 대화형 prompt 로 진입 → 비대화형 (자동/sub-agent) 환경에서 EOFError 또는 무한 blocking. spec §9.2 의 "HIL 2 명시 auto-resume" 의 실 구현 path = `--auto-select-all` flag.

Run:
```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
CPIA_CHECKPOINTER=postgres \
PYTHONPATH="$(pwd)" \
  pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --site-id m15x-ph3-ibl \
  --site-name "M15X Ph-3 IBL" \
  --date 2025-09-25 \
  --auto-select-all \
  2>&1 | tee docs/audit/raw/2026-05-17-prod-task9-sim-stdout.txt
```
Expected 마지막 line 패턴:
```
[OK] run_id=<uuid> site_id=m15x-ph3-ibl date=2025-09-25
...
[OK] reporter generated daily_report (chars=...)
```

Azure 비용: ~$0.1 (Mapper LLM + Forecaster reasoning LLM + Optimizer LLM + Reporter LLM).

- [ ] **Step 9.2: prod PG row count delta 검증**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    for t in ['pipeline_runs', 'forecasts', 'optimizer_advice', 'daily_reports', 'mapping_corrections', 'checkpoints']:
        try:
            n = await c.fetchval(f'SELECT count(*) FROM "{t}"')
            print(f'{t:25s} rows = {n}')
        except Exception as e:
            print(f'{t:25s} ERROR: {e}')
    await c.close()
asyncio.run(main())
PY
```
Expected (각 ≥ 1, mapping_corrections = 0, checkpoints 자동 생성):
```
pipeline_runs             rows = 1
forecasts                 rows = N (N ≥ 1, ~3-5 예상)
optimizer_advice          rows = M (0 ≤ M ≤ N)
daily_reports             rows = 1
mapping_corrections       rows = 0
checkpoints               rows = K (K ≥ 1)
```

- [ ] **Step 9.3: prod Chroma daily_activities row 검증 (Atomizer 적재)**

Run:
```bash
CHROMA_HOST=cpia-chroma.zoai.uk CHROMA_PORT=443 CHROMA_SSL=true \
PYTHONPATH="$(pwd)" pipeline/.venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host='cpia-chroma.zoai.uk', port=443, ssl=True)
coll = c.get_or_create_daily_activities()
# Atomizer 가 적재한 worker_source 값 (synthetic_v2 와 분리)
all_count = coll.count()
print(f'PROD daily_activities total = {all_count}')
# 본 시뮬 호출의 run_id 로 filter (Step 9.1 의 [OK] 라인에서 추출)
"
```

- [ ] **Step 9.4: daily_reports 의 report_md 본문 sample 출력 (Reporter 결과 검증)**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    row = await c.fetchrow("SELECT run_id, report_date, length(report_md) AS chars, history_csv_row FROM daily_reports ORDER BY created_at DESC LIMIT 1")
    print(f'run_id      = {row["run_id"]}')
    print(f'report_date = {row["report_date"]}')
    print(f'chars       = {row["chars"]}')
    print(f'history_csv_row = {row["history_csv_row"]}')
    md_head = await c.fetchval("SELECT substring(report_md from 1 for 500) FROM daily_reports ORDER BY created_at DESC LIMIT 1")
    print('--- report_md head 500 chars ---')
    print(md_head)
    await c.close()
asyncio.run(main())
PY
```
Expected: chars > 500, history_csv_row JSON 가 total_workers/risk_counts/advice_count 포함, report_md head 가 "# 작업일보 종합 보고서" 류 markdown 시작.

- [ ] **Step 9.5: 검증 결과 raw 저장**

Run:
```bash
pipeline/.venv/bin/python3 <<'PY' > docs/audit/raw/2026-05-17-prod-task9-row-delta.txt
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect(host='127.0.0.1', port=5532, user='cpia', password='K7mP2xQ9nR4v', database='cpia')
    print('=== PROD row delta (after sim 1 call) ===')
    for t in ['pipeline_runs', 'forecasts', 'optimizer_advice', 'daily_reports', 'mapping_corrections', 'checkpoints']:
        try:
            n = await c.fetchval(f'SELECT count(*) FROM "{t}"')
            print(f'{t:25s} rows = {n}')
        except Exception as e:
            print(f'{t:25s} ERROR: {e}')
    row = await c.fetchrow("SELECT run_id::TEXT, report_date::TEXT, status FROM pipeline_runs ORDER BY started_at DESC LIMIT 1")
    print(f'\nlast pipeline_runs: {dict(row)}')
    await c.close()
asyncio.run(main())
PY
echo "saved: docs/audit/raw/2026-05-17-prod-task9-row-delta.txt"
```

---

## Task 10: PR 작성 + 본 cycle 종결

**의존**: Task 1~9 모두 완료

**Files:**
- (commit 5건 묶음): Task 1, 2, 3, 4 + Task 9 raw 검증

- [ ] **Step 10.1: Task 9 raw 검증 commit (Task 5~8 은 prod 작업이라 code commit 없음)**

```bash
git add docs/audit/raw/2026-05-17-prod-*.txt
git commit -m "$(cat <<'EOF'
chore(verify): prod 시뮬 1건 end-to-end 통과 (raw 검증)

Task 5 (schema sync) / Task 6 (master load) / Task 7 (synthetic_v2) /
Task 8 (sites seed) / Task 9 (sim 1 e2e) raw 결과.

PROD pipeline_runs / forecasts / optimizer_advice / daily_reports /
checkpoints 각 row ≥ 1, mapping_corrections=0 (HIL 1 우회).

Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §9

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 10.2: 본 cycle commit 묶음 확인**

Run:
```bash
git log --oneline origin/main..HEAD
```
Expected: 5건 (spec + Task 1 + Task 2 + Task 3 + Task 4 + Task 9 raw) — 6건일 수도. spec commit (f4c2db6 류) + Task commits + raw commit.

- [ ] **Step 10.3: PR 작성**

Run:
```bash
gh pr create --title "feat: DB migration + API contract (B 안 + 데이터 시드 + 환경 분리)" \
  --body "$(cat <<'EOF'
## Summary

A_Track 의 PR #19 산출 (schema/코드) 을 homelab prod PG/Chroma 에 반영 + 데이터 시드 + B_Track 가 fetch 할 수 있도록 PG↔types.ts 매핑과 endpoint 8건 spec 박음. **FastAPI 구현은 다음 cycle**.

- 본 cycle scope (9 산출): infra/postgres/init.sql + migrations/2026-05-17_db_alignment.sql + scripts/seed_sites.sql + docs/schema/postgres.md + docs/architecture/api-contract.md + prod schema sync + activity_master 1059 + synthetic_v2 적재 + sites 6 seed + 시뮬 1건 검증
- B 안 채택: mapping_corrections schema 손 안 댐 (현 호출 path 0, 자가학습 cycle 의 묶음). sites +4 컬럼만 본 cycle.
- 데이터 시드 4건: prod 가 데모 가능 상태로 완성
- 환경 분리: dev (5432) + prod (5532 tunnel), 코드 변경 0

## 의도된 drift (다음 cycle 권고)
- D-1 mapping_corrections 자가학습 (별 cycle 묶음)
- D-2 daily_reports history_csv_row 유지
- D-3 atomizer Chroma 그대로
- D-4 FastAPI 구현 (= 다음 cycle 권고 #1)
- D-5 web fixture → 실 API swap
- D-6 시뮬 결과 이관 (휘발)
- D-7 Mapper 자가학습 D-1 묶음

## 검증
- dev 회귀: 197 PASS + 1 xfailed (PR #19 시점 그대로 유지, 코드 변경 0)
- prod 시뮬 1건 end-to-end: pipeline_runs / forecasts / optimizer_advice / daily_reports / checkpoints 각 row ≥ 1, mapping_corrections=0 (HIL 1 우회)
- prod schema diff: A_LOCAL ↔ PROD = 0 격차 (Task 5 sync 후)
- Azure 비용: 시뮬 1건 ~$0.1 + master embedding ~$0.01 + synthetic_v2 ~$0.05 = ~$0.16

## Test plan
- [ ] CI 회귀 통과 (197 PASS + 1 xfailed)
- [ ] reviewer 가 docs/audit/raw/2026-05-17-prod-*.txt 의 row 수 확인
- [ ] reviewer 가 docs/architecture/api-contract.md 의 8 endpoint 명세 검토
- [ ] reviewer 가 sites 6 fixture 정합 확인

## 사전 조건 (선행 완료)
- PR #19 main 머지 완료
- issue viazoai/CPIA#21 (homelab PG 비밀번호 sync) 완료

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR # 생성. URL 사용자에게 paste.

- [ ] **Step 10.4: 본 cycle 종결 보고**

표 형식 보고:
- 본 cycle scope 9 산출 + drift 7
- 회귀 197 PASS + 1 xfailed 유지
- prod 시뮬 통과 + row delta
- PR # pending 조형준 리뷰
- 다음 cycle 권고: FastAPI 구현 (drift D-4 흡수)

---

## 회귀 영향 정리

- **pipeline 코드 변경 0** → 회귀 197 PASS + 1 xfailed 그대로
- **sql 변경 (sites +4)** → dev/prod 모두 sites SELECT path 없음, 무관
- **시드 데이터 (sites 6 / activity_master 1059 / synthetic_v2 ~2000)** → test fixture 와 별도, dev test 의 conftest fixture 가 사용
- **새 테스트 추가 0** → 본 cycle 은 schema + spec + 데이터 시드

## 비용 / 리스크

| 항목 | 추정 |
|---|---|
| Azure (Task 6 master embedding) | ~$0.01 |
| Azure (Task 7 synthetic_v2 ~2000 doc) | ~$0.05 |
| Azure (Task 9 시뮬 1건) | ~$0.1 |
| 총 Azure | **~$0.16** |
| 시뮬 호출 시간 | Task 6 ~30s + Task 7 ~2분 + Task 9 ~3분 = **~6분** |
| prod 망쳤을 때 복구 | docker compose down -v && up -d (empty 라 데이터 손실 0) |

## 다음 cycle 권고

| 우선순위 | cycle | scope |
|---|---|---|
| #1 | FastAPI `pipeline/api.py` 구현 (drift D-4) | api-contract.md 의 8 endpoint 구현, uvicorn, dev/prod 환경변수 분기 |
| #2 | web/ fixture → 실 API swap (drift D-5) | route handler 의 loadFixture → fetch FastAPI |
| #3 | Mapper 자가학습 (drift D-1 + D-7) | mapping_corrections schema 확장 + 백필 + INSERT 변경 + SELECT 신규 + Mapper 로직 + 테스트 |
| #4 | RAG 정합 (drift #N1 xfail 해소) | synthetic_v2 적재 분포 정렬 → Forecaster RAG ≥3 보장 |
