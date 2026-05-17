# CPIA E2E Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PM 조형준 원안 v2 (`planning/CPIA_PoC_실행계획_v2.md`) 와 CPIA 현 구현의 단계별 일치도를 검증하고, 드리프트 우선순위 backlog 을 산출한다.

**Architecture:** 코드 변경 0건의 audit cycle. 9 단계 (Collector → … → Dashboard) 매트릭스 + 시뮬 4 건 실 호출 raw + cross-cutting 검증 + 우선순위 backlog. Iron Law 3 요소 ($ 명령어 + 실 출력 + 결론) 형식 준수.

**Tech Stack:** macOS Apple Silicon · Python 3.9.6 (`pipeline/.venv/bin/python3` 절대경로) · PostgreSQL 16 · ChromaDB 0.5.20 · Azure OpenAI gpt-5.1 · LangGraph 1.2.0 · `synthetic_daily_report` CLI.

**Spec 참조:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` (v1, 320 lines, 12 섹션).

**TDD 적용:** ✗ (audit 는 코드 변경 X). 대신 spec §7.5 의 "동일 fixture 2 회 → 동일 결정론 출력" 결정성 검증을 Task 1 에 포함.

**전역 CLAUDE.md 하드룰 (모든 task 적용):**
- Real code or no claim · No fabrication · Iron Law 3 요소 · No 한자 · 한국어 작성

---

## File Structure

생성/수정 파일 (모두 `docs/audit/` 하위, 코드 변경 X):

```
docs/audit/
├── 2026-05-17-cpia-e2e-audit-report.md   # 단계별 매트릭스 + cross-cutting + 시뮬 요약 (메인 산출물)
├── 2026-05-17-cpia-drift-backlog.md      # 드리프트 우선순위 + defer
├── .gitkeep                              # 디렉토리 보존
└── raw/
    ├── scenario-1-<run_id>.md            # PM 원안 데모 재현 raw
    ├── scenario-2-<run_id>.md            # 주의 (우천 -20%) raw
    ├── scenario-3-<run_id>.md            # 이상 (돌관 -45%) raw
    └── scenario-4-<run_id>.md            # cold_start raw
```

수정 X (단, plan 진행 중 추가로 발견되는 드리프트는 audit-report.md 의 §5 "추가 발견 드리프트" 에 추가).

---

## Task 분해 (6 task)

| # | 이름 | 단위 | bite-sized step |
|---|------|------|-----------------|
| 0 | 사전 준비 (디렉토리 + 골격 파일 + 회귀 baseline) | 1 commit | 7 step |
| 1 | 시뮬 4 건 실 호출 + raw + 결정성 검증 + Azure 비용 실측 | 1 commit (atomic) | 14 step |
| 2 | 9 단계 매트릭스 (Collector → Dashboard) | 1 commit | 11 step |
| 3 | Cross-cutting (v1→v2 + Synthetic 패턴 + 의도된 변경) | 1 commit | 5 step |
| 4 | 추가 발견 드리프트 + 우선순위 backlog (사용자 게이트) | 1 commit | 6 step |
| 5 | Executive Summary + limitation + 본 cycle 종결 (사용자 push 승인) | 1 commit | 6 step |

전체 ~ 49 step, audit 실 작업 시간 추정 4~6 시간 (시뮬 4 건 Azure 호출 ~ 30 분 + 매트릭스 + 문서).

---

## Task 0: 사전 준비

**Files:**
- Create: `docs/audit/.gitkeep`
- Create: `docs/audit/raw/.gitkeep`
- Create: `docs/audit/2026-05-17-cpia-e2e-audit-report.md` (골격)
- Create: `docs/audit/2026-05-17-cpia-drift-backlog.md` (골격)

### Step 0.1: 디렉토리 생성

Run:
```bash
mkdir -p "/Users/kyungseoplee/Project Agent/CPIA/docs/audit/raw" && touch "/Users/kyungseoplee/Project Agent/CPIA/docs/audit/.gitkeep" "/Users/kyungseoplee/Project Agent/CPIA/docs/audit/raw/.gitkeep"
```

Expected: 명령 exit 0, ls 시 `docs/audit/raw/.gitkeep` 존재.

- [ ] **Step 0.1 완료**

### Step 0.2: 회귀 baseline 캡쳐 (이후 cycle 회귀 비교용)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -p no:slow --tb=no -q 2>&1 | tail -3
```

Expected: `141 passed` 또는 `183 passed` (slow 마커 제외). 이 숫자를 audit-report §0 Executive Summary 에 박는다.

LLM 비용 호출 없음 (slow 마커 = integration / E2E 는 제외). 단순 unit 회귀.

- [ ] **Step 0.2 완료** — 회귀 숫자 = `<N> passed` 기록

### Step 0.3: audit-report 골격 작성

Create `docs/audit/2026-05-17-cpia-e2e-audit-report.md`:

```markdown
# CPIA E2E Audit Report (2026-05-17)

> Spec: docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md
> Plan: docs/superpowers/plans/2026-05-17-cpia-e2e-audit-plan.md
> Branch: A_Track HEAD <c40c0be>
> 회귀 baseline: <N> passed (unit, slow 제외)

## 0. Executive Summary
(Task 5 에서 작성)

## 1. 단계별 매트릭스

### 1.1 Collector
(Task 2 에서 작성)

### 1.2 Parser
### 1.3 Mapper
### 1.4 HIL 1
### 1.5 Atomizer
### 1.6 Reporter
### 1.7 Forecaster
### 1.8 HIL 2
### 1.9 Optimizer
### 1.10 Dashboard

## 2. 컨셉 v1→v2 cross-cutting
(Task 3 에서 작성)

## 3. 의도된 변경 (drift 제외, marked)
(Task 3 에서 작성)

## 4. 시뮬 시나리오 4 건 결과
(Task 1 에서 작성, raw 부록 링크 포함)

## 5. 추가 발견 드리프트
(Task 4 에서 작성)

## 6. Limitation
(Task 5 에서 작성 — LLM 비결정성 / 시뮬 1 회 한계)
```

- [ ] **Step 0.3 완료**

### Step 0.4: drift-backlog 골격 작성

Create `docs/audit/2026-05-17-cpia-drift-backlog.md`:

```markdown
# CPIA Drift Backlog (2026-05-17)

> Spec: docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md
> Report: docs/audit/2026-05-17-cpia-e2e-audit-report.md
> 우선순위 산출 기준: 영향도 (high/med/low) × 의존성 × PoC 데모 시연 영향

## 우선순위 #1 — TBD (Task 4 에서 작성)

## 우선순위 #2 — TBD

## 우선순위 #3 — TBD

## defer 항목 (별 cycle 으로 미루기 OK)
(Task 4 에서 작성)
```

- [ ] **Step 0.4 완료**

### Step 0.5: 두 골격 파일 + .gitkeep 2 개 git add

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/.gitkeep docs/audit/raw/.gitkeep docs/audit/2026-05-17-cpia-e2e-audit-report.md docs/audit/2026-05-17-cpia-drift-backlog.md && git status
```

Expected: 4 file staged (.gitkeep × 2 + report 골격 + backlog 골격). uncommitted modification 0.

- [ ] **Step 0.5 완료**

### Step 0.6: commit

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git commit -m "$(cat <<'EOF'
audit/Task 0: docs/audit/ 디렉토리 + 골격 2 파일 + 회귀 baseline 캡쳐

- docs/audit/2026-05-17-cpia-e2e-audit-report.md (12 § 골격, Task 1~5 가 채움)
- docs/audit/2026-05-17-cpia-drift-backlog.md (우선순위 + defer 골격)
- docs/audit/.gitkeep + raw/.gitkeep
- 회귀 baseline: <N> passed (unit, slow 제외)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: `4 files changed, M insertions(+)`. git log 에 신규 commit.

- [ ] **Step 0.6 완료**

### Step 0.7: 회귀 baseline 숫자를 audit-report §0 골격에 박기

Use Edit tool on `docs/audit/2026-05-17-cpia-e2e-audit-report.md`:
- old: `회귀 baseline: <N> passed (unit, slow 제외)`
- new: 실 숫자 (예: `회귀 baseline: 141 passed (unit, slow 제외)`)

- [ ] **Step 0.7 완료**

---

## Task 1: 시뮬 4 건 실 호출 + raw + 결정론 컬럼 분류

**목적:** spec §7 의 4 시나리오를 `synthetic_daily_report` CLI 로 실 호출, 각 시나리오의 단계별 raw 출력을 `docs/audit/raw/` 에 캡쳐. 시나리오 1 호출 직후 reviewer 권고 #1 (assessment 컬럼이 LLM 자유텍스트인지 결정론인지) 을 확인하고 audit-report §6 limitation 에 반영할 컬럼 분류를 결정.

**전제:**
- PG (cpia-pg-local) + Chroma (cpia-chroma-local) docker 컨테이너 가동 중
- Azure 호출 가능 (.env.local 의 AZURE_OPENAI_API_KEY 유효)
- synthetic_v2 2,430 row 가 Chroma 에 이미 적재됨

**Files:**
- Create: `docs/audit/raw/scenario-1-<run_id>.md`
- Create: `docs/audit/raw/scenario-2-<run_id>.md`
- Create: `docs/audit/raw/scenario-3-<run_id>.md`
- Create: `docs/audit/raw/scenario-4-<run_id>.md`

### Step 1.1: 시뮬 호출 사전 환경 확인

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && docker ps --format "{{.Names}}: {{.Status}}" | grep -E "cpia-(pg|chroma)-local"
```

Expected:
```
cpia-pg-local: Up X minutes
cpia-chroma-local: Up X minutes
```

둘 다 Up 상태 아니면 abort 후 사용자 안내.

- [ ] **Step 1.1 완료**

### Step 1.2: synthetic_v2 적재 확인

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host='localhost', port=8765, ssl=False)
coll = c.get_or_create_daily_activities()
r = coll.get(where={'worker_source': 'synthetic_v2'}, limit=1)
print(f'synthetic_v2 row 존재: {bool(r.get(\"ids\"))}')
print(f'first id: {r[\"ids\"][0] if r.get(\"ids\") else None}')
"
```

Expected: `synthetic_v2 row 존재: True` + `first id: <uuid>`. False 면 audit abort, synthetic_v2 적재 cycle 부터 다시.

- [ ] **Step 1.2 완료**

### Step 1.3: 시나리오 1 (PM 원안 데모 재현) 실 호출

PM 원안 §2 데모 시나리오 = "철근 이상+장비대기 / 거푸집 정상 / 콘크리트 정상". synthetic_daily_report CLI 의 scenario 포맷 = `company|l6_main|n_activities|incident|productivity_ratio|workers_ratio|unit`.

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --report-date 2025-09-27 \
  --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
  --scenario "세보건설|거푸집공사|3|정상|1.0|1.0|m2" \
  --scenario "한일건설|콘크리트타설|2|정상|1.0|1.0|m3" \
  --auto-select-all 2>&1 | tee /tmp/scenario-1.log
```

Expected:
- `synthetic_v2 적재 확인 완료` 로그
- `pipeline_runs INSERT run_id=<uuid>` (정확히 1 회)
- `forecast row 3건 — 남웅 risk=주의 또는 이상 / 세보 risk=정상 / 한일 risk=정상`
- `__interrupt__ payload risky_groups=N건`
- `Command(resume=[...])` 후 optimizer advice 출력

**Azure 호출 실패 시 정책 (모든 시나리오 공통):**
- 실패 traceback `/tmp/scenario-<N>.log` 그대로 보존
- 사용자에게 보고 후 plan abort (다음 시나리오 진행 X) — 부분 raw 데이터는 신뢰 불가
- 사용자 결정 후 retry 또는 시나리오 skip 결정

**run_id 추출 (Step 1.4 에서 사용):**
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "
import asyncio
from pipeline.db import PGClient
async def main():
    pg = PGClient('postgresql://cpia:cpia@localhost:5433/cpia')
    await pg.connect()
    row = await pg._pool.fetchrow(\"SELECT run_id, started_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 1\")
    print(f'latest run_id: {row[\"run_id\"]} (started {row[\"started_at\"]})')
    await pg.close()
asyncio.run(main())
"
```

Expected: `latest run_id: <uuid> (started ...)`. 이 uuid 를 Step 1.4 의 `<RUN_ID>` 자리에 박는다.

- [ ] **Step 1.3 완료** — run_id 메모 (예: `e666d916-...`)

### Step 1.4: 시나리오 1 raw 캡쳐 — PG + Chroma + log 통합

Run (run_id 는 Step 1.3 에서 확보):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "
import asyncio, json
from pipeline.db import PGClient
async def main():
    pg = PGClient('postgresql://cpia:cpia@localhost:5433/cpia')
    await pg.connect()
    forecasts = await pg._pool.fetch(\"SELECT * FROM forecasts WHERE run_id = '<RUN_ID>'\")
    advice = await pg._pool.fetch(\"SELECT * FROM optimizer_advice WHERE run_id = '<RUN_ID>'\")
    print('=== forecasts ===')
    for r in forecasts: print(json.dumps(dict(r), default=str, ensure_ascii=False, indent=2))
    print('=== optimizer_advice ===')
    for r in advice: print(json.dumps(dict(r), default=str, ensure_ascii=False, indent=2))
    await pg.close()
asyncio.run(main())
" 2>&1 | tee /tmp/scenario-1-db.log
```

Expected:
- forecasts 3 row (남웅 / 세보 / 한일)
- optimizer_advice 1~3 row (risky 만)

`<RUN_ID>` 는 Step 1.3 결과로 치환.

- [ ] **Step 1.4 완료**

### Step 1.5: 시나리오 1 raw 파일 작성

Create `docs/audit/raw/scenario-1-<run_id>.md` (Iron Law 3 요소 형식):

```markdown
# Scenario 1 raw — PM 원안 데모 재현

**Spec 인용:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` §7.1
**Run ID:** <run_id>
**날짜:** 2025-09-27
**Fixture:** 남웅(철콘 m3, 장비대기, 0.45) + 세보(거푸집 m2, 정상, 1.0) + 한일(콘크리트 m3, 정상, 1.0)

## 1. 단계별 raw

### 1.1 가짜 작업일보 생성 (Parser/Mapper skip — fake_daily_report)

$ pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report ...

<Step 1.3 의 표준 출력 verbatim 인용 — 생략/요약 X>

→ Activity 10 건 생성 (남웅 5 + 세보 3 + 한일 2)

### 1.2 pipeline_runs INSERT

<Step 1.3 log 에서 run_id 부분 quote>

→ run_id=<uuid>, status=running

### 1.3 Forecaster row 3 건

<Step 1.4 의 forecasts 출력 quote>

→ 남웅 today_productivity=<X>, risk_level=<주의/이상>, assessment=<...>
   세보 today_productivity=<Y>, risk_level=정상
   한일 today_productivity=<Z>, risk_level=정상

### 1.4 HIL 2 interrupt payload

<Step 1.3 log 에서 __interrupt__ 부분 quote>

→ risky_groups=N 건 (남웅 1 건 예상), preview_cases=5 건 fetch_degradation_cases 결과

### 1.5 Optimizer advice (--auto-select-all)

<Step 1.4 의 optimizer_advice 출력 quote>

→ rank 1~4 권고 + recovery_distribution + diagnosis

## 2. 결정론/비결정론 컬럼 분류 (reviewer 권고 #1)

Step 1.3 결과 + Step 1.4 결과 검토 후 컬럼별 분류:

| 컬럼 | 결정론 / 비결정론 |
|------|------------------|
| today_productivity | 결정론 (산술) |
| risk_level | <분기 임계값 기반 → 결정론 추정> 또는 <LLM 호출 → 비결정론> |
| assessment | <검토 후 결정> |
| reasoning | 비결정론 (LLM 자유텍스트) |
| recommendations | 비결정론 (LLM 자유텍스트) |
| recovery_distribution | 결정론 (코드단 산출) |

→ audit-report §6 limitation 섹션에 이 분류 박기.

## 3. PoC 원안 §2 데모 권고사항 패턴 일치도

PM 원안 §2 Optimizer 출력 예시:
- "내일 오전 타워크레인 스케줄 확인 필수"
- "장비 확보 시 다음날 자연 복귀 가능성 높음"
- "잔여 물량 기준 D+N 이내 정상화 시 공기 영향 없음"

Step 1.4 의 실 LLM advice 와 비교:
<수동 검토 — 의미적 유사도, 어느 권고가 원안 예시와 일치하는지>

→ 일치도 평가 (`완전 일치` / `부분 일치` / `드리프트`)
```

`<...>` placeholder 는 Step 1.3 + 1.4 결과로 치환.

- [ ] **Step 1.5 완료**

### Step 1.6: 시나리오 2 (주의 우천 -20%) 실 호출

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --report-date 2025-09-28 \
  --scenario "남웅건설|철근콘크리트공사|3|우천|0.8|1.0|m3" \
  --auto-select-all 2>&1 | tee /tmp/scenario-2.log
```

Expected:
- forecast row 1 건 — productivity_ratio=0.8 → today_productivity ≈ baseline × 0.8 → risk_level=주의 또는 이상 (임계값에 따라)
- `incident="우천"` → conditions=["맑음", "우천"]

Azure 호출 실패 시 정책 = Step 1.3 의 정책 동일 적용.

run_id 추출 = Step 1.3 의 run_id 추출 명령 재실행 (latest 가 시나리오 2).

- [ ] **Step 1.6 완료** — run_id 메모

### Step 1.7: 시나리오 2 raw 캡쳐 + raw 파일 작성

Step 1.4 의 PG 조회 명령을 시나리오 2 run_id 로 치환 (`<RUN_ID>` 자리에 Step 1.6 메모한 uuid) 후 재실행 → `/tmp/scenario-2-db.log` 에 tee. 그 다음 raw 파일 작성.

Create `docs/audit/raw/scenario-2-<run_id>.md` (Step 1.5 template 동일, fixture 만 변경):

```markdown
# Scenario 2 raw — 주의 (우천 -20%)

**Spec 인용:** §7.2
**Fixture:** 남웅(철콘 m3, 우천, 0.8, 1.0)

## 1. 단계별 raw
<Step 1.6 log + PG 조회 결과>

## 2. 검증 포인트
- risk_level 분기: <주의 또는 이상>
- conditions: ["맑음", "우천"]
- Optimizer cold_start vs 정상 advice 분기: <어느 path>
```

- [ ] **Step 1.7 완료**

### Step 1.8: 시나리오 3 (이상 돌관 -45%) 실 호출

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --report-date 2025-09-29 \
  --scenario "남웅건설|철근콘크리트공사|3|돌관|0.45|1.3|m3" \
  --auto-select-all 2>&1 | tee /tmp/scenario-3.log
```

Expected:
- forecast row 1 건 — today_qty = baseline × 0.45, workers = baseline × 1.3
- risk_level=이상 (강한 productivity drop)
- recovery_distribution 산출 (Optimizer advice 의 JSONB 필드)

Azure 실패 정책 + run_id 추출 = Step 1.3 동일 적용.

- [ ] **Step 1.8 완료** — run_id 메모

### Step 1.9: 시나리오 3 raw 캡쳐 + raw 파일 작성

Step 1.4 의 PG 조회 명령을 시나리오 3 run_id (Step 1.8 메모) 로 치환 후 재실행 → `/tmp/scenario-3-db.log` 에 tee. 그 다음 raw 파일 작성.

Create `docs/audit/raw/scenario-3-<run_id>.md`:

```markdown
# Scenario 3 raw — 이상 (돌관 -45%)
**Spec 인용:** §7.3
**Fixture:** 남웅(철콘 m3, 돌관, 0.45, 1.3)

## 1. 단계별 raw
## 2. 검증 포인트
- risk_level=이상 트리거 여부
- recovery_distribution: {정상복귀: N, 부분복귀: N, 미복귀: N} JSONB
```

- [ ] **Step 1.9 완료**

### Step 1.10: 시나리오 4 (cold_start) 실 호출

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --report-date 2025-09-30 \
  --scenario "신규건설|토목공사|2|정상|1.0|1.0|m3" \
  --auto-select-all 2>&1 | tee /tmp/scenario-4.log
```

Expected:
- forecast row 1 건 — baseline=None (Chroma 에 history 없음)
- hil_2_node 의 `no_main_unit` 또는 `cold_start_no_baseline` payload note
- Optimizer cold_start path → advice 가 "history 부족" 메시지 또는 placeholder

신규 회사 (Chroma 에 worker_source!=synthetic_v2 등 조건 매칭 안 됨) 라서 baseline_workers/qty 0 또는 None 반환 가능. 산출 path 확인.

Azure 실패 정책 + run_id 추출 = Step 1.3 동일 적용.

- [ ] **Step 1.10 완료** — run_id 메모

### Step 1.11: 시나리오 4 raw 캡쳐 + raw 파일 작성

Step 1.4 의 PG 조회 명령을 시나리오 4 run_id (Step 1.10 메모) 로 치환 후 재실행 → `/tmp/scenario-4-db.log` 에 tee. 그 다음 raw 파일 작성.

Create `docs/audit/raw/scenario-4-<run_id>.md`:

```markdown
# Scenario 4 raw — cold_start (신규 회사)
**Spec 인용:** §7.4
**Fixture:** 신규건설(토목 m3, 정상, 1.0, 1.0)

## 1. 단계별 raw
## 2. 검증 포인트
- baseline=None 분기 발현 여부 (hil_2_node:122 `baseline_value is None`)
- cold_start payload note: "no_main_unit" 또는 "cold_start_no_baseline"
- Optimizer advice 의 cold_start path 결과
```

- [ ] **Step 1.11 완료**

### Step 1.12: 결정성 검증 — 시나리오 1 rerun 호출

시나리오 1 을 한 번 더 호출 (Step 1.3 동일 명령 — Azure LLM 비결정성 노출 컬럼 확인).

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --report-date 2025-09-27 \
  --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
  --scenario "세보건설|거푸집공사|3|정상|1.0|1.0|m2" \
  --scenario "한일건설|콘크리트타설|2|정상|1.0|1.0|m3" \
  --auto-select-all 2>&1 | tee /tmp/scenario-1-rerun.log
```

Expected: 새 run_id 생성. Step 1.3 동일 정상 종료.

run_id 추출 (Step 1.3 명령) → 메모 (`RERUN_RUN_ID`).

- [ ] **Step 1.12 완료** — rerun run_id 메모

### Step 1.13: 결정성 검증 — rerun PG 조회 + diff

Step 1.4 의 PG 조회 명령을 `<RERUN_RUN_ID>` 로 치환 후 재실행 → `/tmp/scenario-1-rerun-db.log` 에 tee.

Run (`<RERUN_RUN_ID>` 자리에 Step 1.12 메모한 uuid):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "
import asyncio, json
from pipeline.db import PGClient
async def main():
    pg = PGClient('postgresql://cpia:cpia@localhost:5433/cpia')
    await pg.connect()
    forecasts = await pg._pool.fetch(\"SELECT * FROM forecasts WHERE run_id = '<RERUN_RUN_ID>'\")
    advice = await pg._pool.fetch(\"SELECT * FROM optimizer_advice WHERE run_id = '<RERUN_RUN_ID>'\")
    print('=== forecasts ===')
    for r in forecasts: print(json.dumps(dict(r), default=str, ensure_ascii=False, indent=2))
    print('=== optimizer_advice ===')
    for r in advice: print(json.dumps(dict(r), default=str, ensure_ascii=False, indent=2))
    await pg.close()
asyncio.run(main())
" 2>&1 | tee /tmp/scenario-1-rerun-db.log
```

그 다음 결정론 컬럼만 grep diff:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && diff <(grep -E '"today_productivity"|"risk_level"|"recovery_distribution"' /tmp/scenario-1-db.log) <(grep -E '"today_productivity"|"risk_level"|"recovery_distribution"' /tmp/scenario-1-rerun-db.log) && echo "결정론 컬럼 일치" || echo "결정론 컬럼 결과 차이 발생 (anomaly)"
```

Expected:
- today_productivity / risk_level / recovery_distribution = 두 호출 결과 동일 (결정론) → `결정론 컬럼 일치`
- reasoning / recommendations 는 diff 명령에서 제외 (비결정성 정상)

→ 이 fact 를 `scenario-1-<run_id>.md` §2 결정론/비결정론 분류 표에 박기.

- [ ] **Step 1.13 완료**

### Step 1.14: 4 raw 파일 + 결정성 검증 결과 commit + Azure 비용 실측 기록

Azure 비용 실측 추정 (`tee` 한 로그에서 토큰 카운트 grep):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -E "tokens|usage|prompt_tokens|completion_tokens" /tmp/scenario-1.log /tmp/scenario-2.log /tmp/scenario-3.log /tmp/scenario-4.log /tmp/scenario-1-rerun.log 2>&1 | head -30
```

Expected: 각 시나리오 LLM 호출 회수 + 토큰 카운트. 단가 ($0.000002/in + $0.000010/out per gpt-5.1 추정) 곱 = 실측 비용. spec §7 의 "~$0.3" 예상 검증 (실측이 ±2× 차이 이내면 OK).

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/raw/ && git commit -m "$(cat <<'EOF'
audit/Task 1: 시뮬 4 건 실 호출 + raw 캡쳐 + 결정론 컬럼 분류

- scenario-1-<id>.md (PM 원안 데모 재현, 남웅 철콘+세보 거푸집+한일 콘크리트)
- scenario-2-<id>.md (주의, 남웅 우천 -20%)
- scenario-3-<id>.md (이상, 남웅 돌관 -45%)
- scenario-4-<id>.md (cold_start, 신규건설 신규 l6_main)
- 결정성 검증: 시나리오 1 2 회 실행 → today_productivity/risk_level/recovery_distribution 동일,
  reasoning/recommendations 차이 (LLM 비결정성)

Azure 비용 실측: $<X.XX> (spec §7 예상 ~$0.3 대비 ±N×)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 1.14 완료**

---

## Task 2: 9 단계 매트릭스

**목적:** spec §3.2 의 5 컬럼 (원안 quote / 실 fact / 일치도 / 영향도 / 우선순위) 으로 9 단계 매트릭스 작성. 시뮬 4 건 raw 출력을 fact 로 활용 + 추가 grep 보완.

**Files:**
- Modify: `docs/audit/2026-05-17-cpia-e2e-audit-report.md` §1.1 ~ §1.10

각 단계는 독립 sub-step (10 단계 × 매트릭스 작성 ≈ 30 step). 단계별 1 sub-step 으로 묶음.

### Step 2.1: Collector (§1.1)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && wc -l pipeline/agents/collector.py
```

Expected: `0 pipeline/agents/collector.py`

Edit `docs/audit/2026-05-17-cpia-e2e-audit-report.md` §1.1:
```markdown
### 1.1 Collector

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "지정 폴더(`input/YYYYMMDD/`)를 감시하여 새 파일을 감지하고 텍스트를 추출" (`planning/CPIA_PoC_실행계획_v2.md` §4 Week 2) |
| 실 구현 fact | `$ wc -l pipeline/agents/collector.py` → `0 pipeline/agents/collector.py` |
| 일치도 | 미구현 |
| 영향도 | high (PoC 데모 입력 진입점 부재 — 파일 드롭 → Parser 흐름 불가) |
| 우선순위 권고 | #N (Task 4 에서 확정) |
```

- [ ] **Step 2.1 완료**

### Step 2.2: Parser (§1.2)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && wc -l pipeline/agents/parser.py && head -30 pipeline/agents/parser.py
```

Expected: `306 lines` + 작업일보 파싱 함수 존재.

Edit `audit-report` §1.2:
```markdown
### 1.2 Parser

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "비정형 텍스트에서 공종별 [인원·물량·작업내용·조건]을 추출하여 JSON으로 변환 ... Claude Sonnet 4.6 호출. **작업내용(work_content) 텍스트 보존 필수** — Atomizer 임베딩의 핵심 원천" (§4 Week 2) |
| 실 구현 fact | `$ wc -l pipeline/agents/parser.py` → `306 lines`. <head -30 출력 quote>. work_content 필드 = `pipeline/state.py:30 Activity.work_content: str` 정의. |
| 일치도 | <시뮬 1 raw 의 Step 1.5 §1.1 결과로 판단 — 일치/부분/미구현/드리프트 중 1>. 단, Parser 는 시뮬에서 skip (synthetic_daily_report 가 직접 Activity 주입) — 코드 존재 = 일치, 실 호출 검증 X. |
| 영향도 | high |
| 우선순위 권고 | #N |
```

- [ ] **Step 2.2 완료**

### Step 2.3: Mapper (§1.3)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && wc -l pipeline/agents/mapper.py && grep -n "def map_activity\|def _prorate_mh\|mapping_conf\|requires_review" pipeline/agents/mapper.py | head -10
```

Edit `audit-report` §1.3:
```markdown
### 1.3 Mapper

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "작업일보의 작업 내용 기술을 공정표 WBS 코드에 의미 기반으로 매핑 ... 확신도 낮은 항목은 `requires_review: true` 플래그" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/mapper.py` → `393 lines`. `map_activity` + `_prorate_mh` + `requires_review` + `mapping_conf` 모두 존재. <grep 출력 quote>. |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer (정상 작동) |
```

- [ ] **Step 2.3 완료**

### Step 2.4: HIL 1 (§1.4) — drift 1호

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -n "hil_1\|hil1\|interrupt" pipeline/state.py pipeline/graph.py pipeline/agents/mapper.py | head -20
```

Expected: `state.py:118 hil_1_corrections`, `state.py:133 waiting_hil_1`, mapper.py 에 interrupt 0건, graph.py 에 hil_1_node 0건.

추가 검증 — `build_graph` 의 노드 목록을 dump 해서 hil_1 부재 확정:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -c "
from pipeline.graph import build_graph, GraphConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster import ForecasterConfig
from pipeline.agents.optimizer.agent import OptimizerConfig
# 노드만 dump 하면 되니까 config 인스턴스는 dummy
cfg = GraphConfig(
    mapper=MapperConfig.__new__(MapperConfig),
    atomizer=AtomizerConfig.__new__(AtomizerConfig),
    forecaster=ForecasterConfig.__new__(ForecasterConfig),
    optimizer=OptimizerConfig.__new__(OptimizerConfig),
)
g = build_graph(cfg)
print('nodes:', list(g.get_graph().nodes.keys()))
"
```

Expected: `nodes: ['__start__', 'mapper', 'atomizer', 'forecaster', 'hil_2', 'optimizer', '__end__']`. `hil_1` 부재.

만약 GraphConfig dataclass 가 dummy 인스턴스 생성 불가하면 fallback = `grep "add_node" pipeline/graph.py` 출력으로 노드 목록 확인.

Edit `audit-report` §1.4:
```markdown
### 1.4 HIL 1 (Mapper 직후) — drift 1호

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일. LangGraph `interrupt()` → 담당자 수정 → `corrections.json` 누적" (§4 Week 3). PoC 성공 기준 #2: "Mapper: 의미 기반 자동 매핑 + H-i-L 1 검증·수정 피드백 루프" (§5). |
| 실 구현 fact | `$ grep -n "hil_1\|interrupt" pipeline/state.py pipeline/graph.py pipeline/agents/mapper.py`<br><grep 출력 quote: state.py:118 hil_1_corrections / state.py:133 waiting_hil_1 / graph.py 의 interrupt 는 hil_2 만 / mapper.py interrupt 0 hits><br>`$ pipeline/.venv/bin/python3 -c "from pipeline.graph import build_graph; ..."` → build_graph 에 hil_1_node 부재. |
| 일치도 | **드리프트 (placeholder)** — state 자리만 있고 노드/interrupt 미구현 |
| 영향도 | high (PoC 성공 기준 #2 미충족, 데모 시연 단계 누락) |
| 우선순위 권고 | #N (Task 4 에서 확정 — Collector / Reporter 와 비교한 우선순위) |
```

- [ ] **Step 2.4 완료**

### Step 2.5: Atomizer (§1.5)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && wc -l pipeline/agents/atomizer.py && grep -n "def atomize\|chroma\|metadata\|content" pipeline/agents/atomizer.py | head -15
```

Edit `audit-report` §1.5:
```markdown
### 1.5 Atomizer

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "오늘 작업 기록을 Vector DB에 임베딩·적재 — 이후 Forecaster·Optimizer의 검색 대상 ... Sheet4(수치)와 Sheet1(텍스트)를 날짜+업체 키로 JOIN하여 하나의 레코드로 구성" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/atomizer.py` → `118 lines`. <grep 출력>. 시뮬 1 raw §1.4 의 Chroma row insert 확인 (synthetic_daily_report 가 atomize 호출). |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer |
```

- [ ] **Step 2.5 완료**

### Step 2.6: Reporter (§1.6) — drift

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && wc -l pipeline/agents/reporter.py
```

Expected: `0 pipeline/agents/reporter.py`

Edit `audit-report` §1.6:
```markdown
### 1.6 Reporter — drift

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일. Mapper 확정 JSON → Claude Sonnet 4.6 → 통합 Daily Report 생성 + history.csv 업데이트" (§4 Week 3). PoC 성공 기준 #1: "작업일보 파일 투입 → 통합 Daily Report 자동 생성" (§5). |
| 실 구현 fact | `$ wc -l pipeline/agents/reporter.py` → `0 pipeline/agents/reporter.py` |
| 일치도 | **미구현** |
| 영향도 | high (PoC 성공 기준 #1 미충족, 경영진 데모의 핵심 산출물 부재) |
| 우선순위 권고 | #N |
```

- [ ] **Step 2.6 완료**

### Step 2.7: Forecaster (§1.7)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && ls pipeline/agents/forecaster/ && wc -l pipeline/agents/forecaster/*.py
```

Edit `audit-report` §1.7:
```markdown
### 1.7 Forecaster

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "오늘 생산성이 과거 유사 상황 대비 적정한지 진단하고 리스크 공종 목록 생성 ... ChromaDB에서 유사 조건 과거 기록 5건 조회 ... Claude Opus 4.7 ... Cold Start: Vector DB에 유사 기록이 3건 미만이면 WBS Man-Hour 기반 계획 생산성을 fallback" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/forecaster/*.py` → agent.py 276, aggregate.py 119, classify.py 114, prompt.py 134, rerank.py 50, synthetic.py 189, constants.py 8, `__init__.py` 8. 시뮬 1~4 raw §1.3 의 forecast row 결과 cite. |
| 일치도 | 일치 (RAG 기반 상대 비교 동작 확인 — 시뮬 1 raw 의 risk_level 분기) |
| 영향도 | high |
| 우선순위 권고 | defer (단, productivity_ratio ↔ risk_level 임계값 정합은 별 cycle backlog — 이전 cycle 발견 한계) |
```

- [ ] **Step 2.7 완료**

### Step 2.8: HIL 2 (§1.8)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -n "hil_2_node\|interrupt" pipeline/graph.py | head -10
```

Edit `audit-report` §1.8:
```markdown
### 1.8 HIL 2 (Forecaster → Optimizer)

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일하되 역할 변경: 리스크 공종 목록 표시 + PM이 **조언 대상 공종** 선택 (최적화 의뢰 공종 선택)" (§4 Week 3) |
| 실 구현 fact | `$ grep -n "hil_2_node\|interrupt" pipeline/graph.py` → graph.py:71 hil_2_node + graph.py:172 `selected = interrupt({"risky_groups": payload_groups})`. 시뮬 1 raw §1.4 의 interrupt payload 확인. |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer |
```

- [ ] **Step 2.8 완료**

### Step 2.9: Optimizer (§1.9)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && ls pipeline/agents/optimizer/ && wc -l pipeline/agents/optimizer/agent.py pipeline/agents/optimizer/prompt.py pipeline/agents/optimizer/retrieve.py
```

Edit `audit-report` §1.9:
```markdown
### 1.9 Optimizer

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "PM이 선택한 공종의 저하 원인을 과거 패턴 기반으로 진단하고, 회복 시나리오와 구체적 조언을 제시 ... ChromaDB에서 '이 공종이 비슷하게 저하됐던 과거 상황' 검색 ... Claude Opus 4.7이 원인·회복 패턴·권고사항 종합" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/optimizer/*.py` → agent.py 156, prompt.py 315, retrieve.py 161. 시뮬 1 raw §1.5 의 optimizer_advice row 결과 cite (rank 1~4 + recovery_distribution). |
| 일치도 | 일치 (맥락 조언 + recovery_distribution 동작) |
| 영향도 | high |
| 우선순위 권고 | defer (단, 시뮬 1 §3 PoC 원안 권고사항 패턴 일치도 결과에 따라 재조정 가능) |
```

- [ ] **Step 2.9 완료**

### Step 2.10: Dashboard (§1.10)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && ls web/app/ && ls web/app/components/ 2>/dev/null | head -10
```

Edit `audit-report` §1.10:
```markdown
### 1.10 Dashboard

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "Layer 1: 6개 현장 현황 카드 (공정률·생산성 이상 공종·보고 상태) / Layer 2: 현장 상세 (S-curve·생산성 진단 결과·Optimizer 조언·보고서 링크) ... Streamlit" (§4 Week 4) |
| 실 구현 fact | `$ ls web/app/components/` → home/ landing/ reports/ review/ tasks/ ... (Next.js, 의도된 변경). B_Track 진행 중. Layer 1/2 분리 = home/StatusHeader, OpsKpiCard 등. |
| 일치도 | 의도된 변경 (Streamlit → Next.js, spec §6 marked) — 구현 중 (B_Track) |
| 영향도 | med (의도된 변경, B_Track 트랙 별도 진행) |
| 우선순위 권고 | defer (B_Track audit 는 별 cycle) |
```

- [ ] **Step 2.10 완료**

### Step 2.11: Task 2 commit

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/2026-05-17-cpia-e2e-audit-report.md && git commit -m "$(cat <<'EOF'
audit/Task 2: 9 단계 매트릭스 — Collector ~ Dashboard 5 컬럼 작성

일치도 분포:
- 일치 N건 (Mapper, Atomizer, Forecaster, HIL 2, Optimizer)
- 미구현 N건 (Collector, Reporter)
- 드리프트 1건 (HIL 1 placeholder)
- 의도된 변경 1건 (Dashboard Streamlit→Next.js)
- 일치 (skip) 1건 (Parser — 시뮬에서 미호출)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2.11 완료**

---

## Task 3: Cross-cutting — v1→v2 + Synthetic 패턴 + 의도된 변경

**목적:** spec §5 (컨셉 v1→v2 6 변경) + §4 #7 #8 (Synthetic 변동/회복 패턴 매트릭스, reviewer 권고 #2) + §6 (의도된 변경 4 건 marked) 을 audit-report §2 + §3 에 작성.

**Files:**
- Modify: `docs/audit/2026-05-17-cpia-e2e-audit-report.md` §2, §3

### Step 3.1: 컨셉 v1→v2 6 변경 검증

Run (6 검증 명령 차례로):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
# 1. 품셈 제거
grep -rn "품셈\|pumssem" pipeline/ 2>/dev/null | head -5
# 2. Forecaster RAG
grep -n "chroma\|fetch_degradation" pipeline/agents/forecaster/agent.py | head -10
# 3. Optimizer 맥락 조언 (수치 계산 X)
grep -n "재배치\|reassign\|head.*calc" pipeline/agents/optimizer/agent.py | head -5
# 4. Atomizer 추가
ls pipeline/agents/atomizer.py
# 5. ChromaDB + 임베딩
grep -n "ChromaClient\|text-embedding" pipeline/chroma_client.py
# 6. Synthetic 90일 (의도된 확대)
pipeline/.venv/bin/python3 -c "
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host='localhost', port=8765, ssl=False)
coll = c.get_or_create_daily_activities()
r = coll.get(where={'worker_source': 'synthetic_v2'}, limit=10000, include=['metadatas'])
print(f'synthetic_v2 row 수: {len(r[\"ids\"])}')
"
```

각 결과 quote.

- [ ] **Step 3.1 완료**

### Step 3.2: audit-report §2 작성

Edit `audit-report` §2 — spec §5 의 6 변경 매트릭스 (Step 3.1 결과 그대로 박기). 일치도 컬럼:
- 품셈 제거: `0 hits` → 일치
- Forecaster RAG: Chroma 호출 + `fetch_degradation_cases` 존재 → 일치
- Optimizer 맥락 조언: 재배치 수치 계산 코드 부재 → 일치
- Atomizer: 파일 존재 → 일치
- ChromaDB + 임베딩: chroma_client.py 동작 → 일치
- Synthetic 90일: 2,430 row 적재 확인 → 의도된 변경 (확대)

- [ ] **Step 3.2 완료**

### Step 3.3: Synthetic 변동/회복 패턴 매트릭스 (reviewer 권고 #2)

먼저 synthetic state machine 7 룰이 어느 파일에 박혀있는지 확정:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && find pipeline -name "synthetic*.py" -type f 2>/dev/null | xargs wc -l
```

Expected: `pipeline/agents/optimizer/synthetic_v2.py` (363 lines) — 7 룰 소유. 만약 `pipeline/synthetic/generate_history.py` 등 다른 위치도 있으면 본 plan 의 grep target 을 그 파일로 변경.

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && grep -n "def \|^_\|incident\|우천\|야간\|장비대기\|돌관\|복귀" pipeline/agents/optimizer/synthetic_v2.py | head -40
```

원안 §3.B 의 4 변동 패턴 + 2 회복 패턴 vs synthetic_v2.py 의 7 룰 매트릭스 작성. audit-report §2 의 하위 섹션으로:

```markdown
### 2.7 Synthetic 변동/회복 패턴 매트릭스 (drift 후보 #7, #8)

| 원안 패턴 (§3.B) | synthetic_v2.py 룰 | 일치도 |
|----------------|--------------------|--------|
| 우천일 -15~25% | <grep 결과 — productivity_ratio 우천 분기 존재 여부 + 정확한 범위> | <일치/부분/드리프트> |
| 야간 연장 50% 초과 시 익일 -10% | <grep 결과> | <일치도> |
| 장비 대기 -20~35% | <grep 결과 — productivity_ratio=0.45 등이 이 범위에 들어가는지> | |
| 병행작업 겹침 -10~20% | <grep 결과> | |
| 정상일 ±5% | <grep 결과> | |
| 장비 대기 → 다음날 정상 복귀 (80%) | <grep — incident=장비대기 직후 productivity_ratio=1.0 분기> | |
| 우천 연속 2일 → 3일차 +10% 만회 | <grep — 우천 연속 incident state machine 검증> | |
```

각 룰을 fact 로 확인 + 일치도 라벨링.

- [ ] **Step 3.3 완료**

### Step 3.4: audit-report §3 의도된 변경 4 건 marked

Edit `audit-report` §3 — spec §6 의 4 변경 표 그대로 + 각 변경의 사유 + 본 audit 가 drift 분류 X 라고 명시.

```markdown
## 3. 의도된 변경 (drift 제외, marked)

본 audit 에서 다음 4 항목은 의도된 변경으로 marked, 매트릭스 일치도 컬럼에 `의도된 변경` 표기, drift backlog 에 포함 X.

| # | 변경 | 원안 | 현 구현 | 의도 |
|---|------|------|---------|------|
| 1 | LLM 인프라 | Claude Sonnet 4.6 + Opus 4.7 | Azure OpenAI gpt-5.1-chat-ai-board-test + gpt-5-mini | 사용자/회사 Azure 계정 제약 |
| 2 | Dashboard 스택 | Streamlit | Next.js + TypeScript (web/) | B_Track 디자인 시스템 / UI 정밀도 |
| 3 | Persistence | JSON 파일 | PostgreSQL + Chroma | 확장성 / 동시성 / 운영 안정성 |
| 4 | Synthetic 스케일 | 30일치 | 90일 × 27 그룹 = 2,430 row | baseline 통계 의미 확보 (n ≥ 30 per 그룹) |
```

- [ ] **Step 3.4 완료**

### Step 3.5: Task 3 commit

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/2026-05-17-cpia-e2e-audit-report.md && git commit -m "$(cat <<'EOF'
audit/Task 3: Cross-cutting — v1→v2 6 변경 + Synthetic 패턴 + 의도된 변경 4

§2 컨셉 v1→v2: 일치 5건 + 의도된 변경 1건 (Synthetic 90일 확대)
§2.7 Synthetic 변동/회복 패턴: <일치도 분포>
§3 의도된 변경 marked: Azure LLM / Next.js Dashboard / PG+Chroma persistence / Synthetic 90일

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3.5 완료**

---

## Task 4: 추가 발견 드리프트 + 우선순위 backlog

**목적:** 시뮬 4 건 raw + 단계별 매트릭스 작성 중 드러난 추가 드리프트를 audit-report §5 에 정리. 그 다음 사전 식별 8 건 + 추가 발견 합쳐 우선순위 분류해 drift-backlog.md 작성.

**Files:**
- Modify: `docs/audit/2026-05-17-cpia-e2e-audit-report.md` §5
- Modify: `docs/audit/2026-05-17-cpia-drift-backlog.md` (전체)

### Step 4.1: 시뮬 raw 4 건 + 매트릭스 검토 → 추가 드리프트 추출

raw/scenario-1~4.md 와 audit-report §1.1~1.10 / §2 / §3 을 다시 읽고, spec §4 의 8 사전 드리프트 외에 새로 드러난 항목 추출. 예상 후보:
- forecast_assessment vs risk_level 분기 일관성 (이전 cycle E2E demo 한계)
- productivity_ratio ↔ risk_level 임계값 정합
- Optimizer LLM advice 의 원안 권고사항 패턴 일치도
- cold_start path 에서 advice 가 placeholder 인지 의미 있는 메시지인지

추출된 항목 = audit-report §5 에 list 로 박기.

- [ ] **Step 4.1 완료**

### Step 4.2: audit-report §5 작성

Edit `audit-report` §5 — 추가 드리프트 항목별 [원안 quote / 시뮬 raw 인용 / 영향도 / 우선순위] 형식.

```markdown
## 5. 추가 발견 드리프트

(사전 식별 8 건 외에 시뮬 + 매트릭스 작성 중 드러난 항목)

### 5.1 forecast_assessment vs risk_level 분기 일관성
- 원안 의도: §4 Week 3 Forecaster 출력 예시
- 시뮬 fact: `docs/audit/raw/scenario-2-<id>.md` §1 — assessment=정상 인데 risk_level=주의 한 case
- 영향도: med
- 우선순위 권고: #N

### 5.2 productivity_ratio ↔ risk_level 임계값 정합
...

### 5.3 Optimizer 권고사항 vs 원안 §2 데모 예시 일치도
- 시뮬 1 raw §3 결과 cite
- 영향도: low (의미 일치는 LLM 비결정)
- 우선순위 권고: defer

### 5.4 cold_start path 메시지 quality
- 시뮬 4 raw §2 cite
- 영향도: low/med
- 우선순위 권고: defer
```

- [ ] **Step 4.2 완료**

### Step 4.3: 우선순위 분류 기준 결정

영향도 + PoC 데모 시연 의존성 + 후속 cycle 진입 가능성 3 차원으로 분류:

| 우선순위 | 기준 |
|---------|------|
| #1 | high 영향도 + PoC 성공 기준 미충족 + 후속 cycle 진입 가능 |
| #2 | high 영향도 + 다른 #1 항목과 의존성 |
| #3 | med 영향도 + 후속 cycle 단독 진입 가능 |
| defer | low 영향도 또는 cosmetic 또는 별 cycle 우선 |

사전 식별 8 건 + 추가 발견 N 건 모두 이 기준으로 분류.

- [ ] **Step 4.3 완료** — 분류 기준 결정

### Step 4.4: drift-backlog.md 본문 작성

Edit `docs/audit/2026-05-17-cpia-drift-backlog.md`:

```markdown
# CPIA Drift Backlog (2026-05-17)

## 우선순위 #1 — <이름, 예: Reporter 구현>
- 출처: audit-report §1.6
- 영향도: high
- 원안 §: §4 Week 3 + §5 PoC 성공 기준 #1
- 의존성: 없음 (단독 진입 가능)
- 권고 다음 cycle: brainstorming → spec → plan
- 산출 추정: <Sonnet 호출 / history.csv 통합 보고서 / Streamlit Dashboard 연동>

## 우선순위 #2 — <이름>
...

## 우선순위 #3 — <이름>
...

## defer 항목
- <이름> — 영향도 low or 별 cycle 우선
- ...
```

audit-report § 인용 + 원안 § 인용 + 의존성 + 권고 다음 cycle 형식 + 산출 추정.

- [ ] **Step 4.4 완료**

### Step 4.5: 사용자 검토 게이트 (우선순위 합의)

drift-backlog.md 작성 후 사용자에게 우선순위 합의 요청:

> "Drift backlog 작성 완료. 우선순위 #1~#3 + defer 분류는 다음과 같습니다: ... 이 순서로 다음 cycle 진입 OK 인지, 또는 우선순위 재조정 필요한 항목이 있는지 알려주세요."

사용자 응답에 따라 backlog 수정 또는 그대로 commit.

- [ ] **Step 4.5 완료** — 사용자 OK

### Step 4.6: Task 4 commit

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/ && git commit -m "$(cat <<'EOF'
audit/Task 4: 추가 발견 드리프트 + 우선순위 backlog

§5 추가 발견: N건
backlog 우선순위 #1 ~ #N + defer 분류 (사용자 합의)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4.6 완료**

---

## Task 5: Executive Summary + limitation + 본 cycle 종결

**목적:** audit-report §0 Executive Summary + §6 Limitation (reviewer 권고 #3 흡수) + §4 시뮬 4 건 결과 요약 + 본 cycle commit 마무리 + push.

**Files:**
- Modify: `docs/audit/2026-05-17-cpia-e2e-audit-report.md` §0, §4, §6

### Step 5.1: audit-report §4 시뮬 시나리오 4 건 결과 요약

Edit `audit-report` §4:

```markdown
## 4. 시뮬 시나리오 4 건 결과

각 시나리오의 raw 출력 = `docs/audit/raw/scenario-<N>-<run_id>.md` 참조.

### 4.1 시나리오 1 — PM 원안 데모 재현
- run_id: <uuid>
- fixture: 남웅 철콘 0.45 + 세보 거푸집 1.0 + 한일 콘크리트 1.0
- 결과:
  - forecast row 3
  - risk_level: 남웅 <주의/이상>, 세보 정상, 한일 정상
  - HIL 2 interrupt: risky_groups N건
  - Optimizer advice: rank 1~4 + recovery_distribution
- 검증 포인트 충족: <Yes/No, 어느 포인트>
- PoC 권고사항 패턴 일치도: <완전/부분/드리프트>

### 4.2 시나리오 2 — 주의 (우천 -20%)
...
### 4.3 시나리오 3 — 이상 (돌관 -45%)
...
### 4.4 시나리오 4 — cold_start
...
```

- [ ] **Step 5.1 완료**

### Step 5.2: audit-report §6 Limitation 작성

Edit `audit-report` §6:

```markdown
## 6. Limitation

### 6.1 LLM 비결정성 컬럼
시나리오 1 결정성 검증 (Task 1 Step 1.12) 결과:
- 결정론 컬럼: today_productivity / risk_level / recovery_distribution
- 비결정론 컬럼: reasoning / recommendations / diagnosis 텍스트
- assessment 컬럼: <Task 1 Step 1.5 §2 분류 결과 cite>

비결정론 컬럼의 audit 평가는 "의미적 일치" 기준이며, 동일 fixture 의 다회 호출 결과가 어휘/순서 차이는 normal, 의미 차이는 anomaly 로 분류.

### 6.2 시뮬 1 회 한계
시나리오 1~4 각각 단일 호출 (시나리오 1 만 2 회 결정성 검증). 다회 호출 통계적 신뢰는 미확보 — 비결정 컬럼의 의미 분산은 정성 평가.

### 6.3 audit 범위 외
- 갭 자체의 구현 (Reporter / HIL 1 / Collector 등) — 별 cycle
- B_Track Next.js Dashboard 의 internal audit — 별 cycle (의도된 변경 marked 만)
- 코드 스타일 / 한자 / cosmetic — 별 채널
```

- [ ] **Step 5.2 완료**

### Step 5.3: audit-report §0 Executive Summary 작성

Edit `audit-report` §0:

```markdown
## 0. Executive Summary

### 일치도 분포
- 일치 N건 (Mapper, Atomizer, Forecaster, HIL 2, Optimizer, Parser-skip)
- 미구현 N건 (Collector, Reporter)
- 드리프트 N건 (HIL 1 placeholder + 추가 발견 §5)
- 의도된 변경 marked N건 (Dashboard Streamlit→Next.js + §3 cross-cutting 4)

### 우선순위 후속 cycle 후보
1. <우선순위 #1 이름>
2. <우선순위 #2 이름>
3. <우선순위 #3 이름>

상세는 `docs/audit/2026-05-17-cpia-drift-backlog.md`.

### 회귀 baseline (audit 시작 시점)
<Task 0 Step 0.2 결과 cite>

### 시뮬 4 건 Azure 비용 실측
<Task 1 commit msg cite — 예: ~$0.3>
```

- [ ] **Step 5.3 완료**

### Step 5.4: 회귀 재검증 (audit 가 코드 변경 X 보증)

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -p no:slow --tb=no -q 2>&1 | tail -3
```

Expected: Task 0 Step 0.2 와 동일 숫자 (audit 는 코드 변경 X — 회귀 0건).

다르면 abort 후 origin 추적.

- [ ] **Step 5.4 완료**

### Step 5.5: 본 cycle commit + 사용자 push 승인 + push

먼저 사용자 push 승인 확인 (전역 룰 "Never push without explicit request"):

> "Audit cycle 최종 commit + origin/A_Track push 진행해도 될까요? 본 cycle 산출물 = audit-report 1 + drift-backlog 1 + raw 4 = 6 파일."

사용자 OK 받은 후 commit + push 실행. 사용자 거부 시 commit 만 하고 push 보류.

Run (사용자 OK 받은 후):
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add docs/audit/2026-05-17-cpia-e2e-audit-report.md && git commit -m "$(cat <<'EOF'
audit/Task 5: Executive Summary + §4 시뮬 결과 요약 + §6 Limitation

§0 일치도 분포 + 우선순위 #1~#3 후보 + 회귀 baseline + Azure 비용
§4 시뮬 4 시나리오 결과 요약 (raw 부록 링크)
§6 Limitation — LLM 비결정성 컬럼 + 시뮬 1 회 한계 + audit 범위 외

회귀: <N> passed (코드 변경 0건 — Task 0 baseline 과 동일)
0 한자 검수 통과

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)" && git push origin A_Track
```

Expected: commit + push 모두 성공.

- [ ] **Step 5.5 완료**

### Step 5.6: 최종 review 게이트

사용자에게 보고:

> "Audit cycle 종결. 산출물:
> 1. audit-report: `docs/audit/2026-05-17-cpia-e2e-audit-report.md`
> 2. drift-backlog: `docs/audit/2026-05-17-cpia-drift-backlog.md`
> 3. raw 부록 4 건
>
> 우선순위 #1 = <X> → 다음 cycle brainstorming 으로 진입할까요? 또는 다른 결정?"

사용자 응답 대기. 본 cycle 끝.

- [ ] **Step 5.6 완료**

---

## 회고 + 후속 cycle 핸드오프

본 plan 종결 후:

1. **drift-backlog 우선순위 #1** → 별 cycle (brainstorming) 진입
2. **위반 패턴** — audit 진행 중 발견된 "사용자 인식 vs 실 코드 mismatch" (HIL 1 등) 류는 사용자 memory 에 패턴 기록 후 다음 cycle 부터 grep 우선

### 본 plan 의 산출 가치 측정 (spec §10 ↔ plan step 매핑)

| # | spec §10 기준 | plan step 매핑 |
|---|---------------|----------------|
| 1 | 9 단계 매트릭스 5 컬럼 모두 fact 박힘 | Task 2 Step 2.1~2.10 + Task 2 Step 2.11 commit |
| 2 | 시뮬 4 건 raw (Iron Law 3 요소 형식) | Task 1 Step 1.3~1.11 + Step 1.13 (결정성) + Step 1.14 commit |
| 3 | PM 원안 §quote verbatim | Task 2 각 step 의 "원안 의도" 컬럼 + Task 3 Step 3.2 / 3.3 |
| 4 | 의도된 변경 4 marked | Task 3 Step 3.4 |
| 5 | 드리프트 8+ backlog 배치 | Task 4 Step 4.1~4.4 |
| 6 | LLM 비결정성 limitation 명시 | Task 1 Step 1.13 결정성 검증 → Task 5 Step 5.2 §6 Limitation |

6 기준 모두 충족 시 audit 통과. 미충족 항목 = next iteration 으로 보강.

---

*작성: Claude Opus 4.7 (1M context) | 2026-05-17 | 사용자 = evan@sk.com*
*Spec: docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md*
