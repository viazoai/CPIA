# CPIA FE↔BE 연결 BE 구현 Plan (2026-05-18)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 본 cycle (2026-05-18) data-contract delta-and-decisions cycle 의 9 신규 결정을 BE 측 실 구현으로 매핑. 10 gap 중 9 구현 + 1 mock 영구 (G-9 일부, D-3 EWMA 드랍).

**Architecture:** FastAPI (pipeline/api.py 0 → ~600 lines, 11 endpoint) ↔ Next.js BFF (web/app/api/ 11 route) ↔ FE 5 page (시각화 chip/색상/아이콘 그대로 유지, 데이터 흐름만 변경). PostgreSQL 변경 = forecasts.wa TEXT 컬럼 추가 + mapped_history 신규 테이블. LangGraph Forecaster wa 차원 추가 + Atomizer 가 mapped_history INSERT.

**Tech Stack:** Python 3.11 (pipeline/.venv, uv 관리) / FastAPI / asyncpg / LangGraph 0.2 / AsyncPostgresSaver / Next.js App Router (web/) / Azure OpenAI gpt-5.1-chat-ai-board-test + text-embedding-3-small-ai-board-test (1536d) / PostgreSQL prod 5532 (cloudflared tunnel cpia-pg.zoai.uk).

**전역 룰:**
- Iron Law 3 요소 ($ 명령 + 실 출력 + 결론)
- TDD as default (신규 = 실패 테스트 먼저)
- PoC 마감 = 2026-06-05 (D-18 남음)
- FE 시각화 (chip / 색상 / 아이콘 / 라벨) 절대 변경 X — 사용자 명시
- main 머지 = 조형준 프로 권한
- `push --force` 절대 금지

---

## Phase 0 — BE 산식 합의 (선행)

> 본 phase = BE 담당과의 사전 합의. 산식 결정 후 Phase 1+ 진행. 결정 미달 시 mock 영구 (D-3 노선) 또는 보류.

### Task 0.1: `AgentTaskItem.status` 의 `processing` 정의

**의도**: `/tasks` 우측 표의 5 치 중 `processing` (sky color, animated Loader2) 의 BE 산출 정의. LangGraph batch 라 단일 row 특정 X.

**옵션** (3 후보):
- (i) 단계의 첫 미처리 row 1 건 임의 선택 (mock 휴리스틱 정합)
- (ii) state 구조에 처리 시각 timestamp 추가 (구현 부담)
- (iii) `processing` 산출 안 함 (항상 빈 셋, 시각화 단조)

**결정 권고**: (i) — 단순. BE = "현재 active 단계의 received - processed 중 첫 1 건 idx" 만 표시.

### Task 0.2: `AgentTaskItem.status` 의 `blocked` 정의

**의도**: `blocked` (rose color, AlertOctagon) 의 BE 산출 정의.

**옵션** (3 후보):
- (i) `mapped[i].mapping_source = 'hil_required' AND mapped[i].mapping_conf < 0.3` (낮은 confidence)
- (ii) LangGraph error 추적 — agent 안 error 시 그 activity 표시 (state 구조 확장)
- (iii) Forecaster.risk_level = '이상' 인 activity (단 grain 다름)

**결정 권고**: (i) — Mapper LLM 의 hil_required 중 confidence 매우 낮은 1 case = "BE 가 매핑 실패" 의미. 시연 명확.

### Task 0.3: `s_curve` 의 MH 누적 + 환산 산식 (G-9)

**사용자 의도**: "계획은 masterlist와 매핑시켜서 mh기준으로 하고 actual이 현재 작업일보 매핑된거 기반으로, 그리고 만회나 그런것들은 forecaster 받아야돼"

**계획 곡선 산식**: 
```sql
-- 활동 마스터의 plan_mh 를 시작~종료 일자 균등 분배 후 누적
WITH am_per_day AS (
  SELECT
    generate_series(plan_start, plan_finish, '1 day')::date AS d,
    plan_mh_rev2 / (plan_finish - plan_start + 1)::numeric AS daily_mh
  FROM activity_master WHERE site_id = :site_id
)
SELECT d AS date, SUM(SUM(daily_mh)) OVER (ORDER BY d) AS planned_cum_mh
FROM am_per_day GROUP BY d;
```

**실적 곡선 산식**:
```sql
-- mapped_history 의 today_qty 를 activity_master 의 (plan_mh / plan_total_qty) 로 환산 후 누적
SELECT
  mh.report_date AS date,
  SUM(SUM(mh.today_qty * COALESCE(am.plan_mh_rev2 / NULLIF(am.plan_total_qty, 0), 0))) OVER (ORDER BY mh.report_date) AS actual_cum_mh
FROM mapped_history mh
JOIN activity_master am ON am.wa=mh.wa AND am.l6_main=mh.l6_main AND am.company=mh.company
WHERE mh.site_id = :site_id
GROUP BY mh.report_date;
```

**회복 곡선 산식**:
- forecasts.recovery_likelihood + optimizer_advice.recovery_distribution → 일자별 회복 가능 MH 분배
- Phase 0 합의 사항 — 산식 디테일 미정

**결정 권고**: 위 산식 채택. 회복 곡선만 BE 담당과 추가 합의.

### Task 0.4: `DailyTask.progress_percent` 8 단계 인덱스 산식

**의도**: `pipeline_runs.current_node` 기반 진척률.

**산식**:
```python
NODE_PERCENT = {
    "collector": 12.5, "parser": 25.0, "mapper": 37.5,
    "hil_1": 37.5,  # interrupt 상태
    "atomizer": 50.0, "reporter": 62.5,
    "forecaster": 75.0, "optimizer": 87.5,
    "completed": 100.0,
}
```

**결정 권고**: 위 매핑 채택.

### Task 0.5: `recoverable_days` 산식 (G-5)

**의도**: /dashboard Performance KPI 카드 의 "회복 가능 일수".

**산식**:
```sql
SELECT SUM(
  COALESCE(
    (recovery_distribution->>'d+1')::int * 1 +
    (recovery_distribution->>'d+2')::int * 2 +
    (recovery_distribution->>'d+3')::int * 3 +
    (recovery_distribution->>'d+5')::int * 5 +
    (recovery_distribution->>'d+7')::int * 7
  , 0)
) AS recoverable_days
FROM optimizer_advice WHERE run_id IN (SELECT last_run_id FROM sites);
```

**결정 권고**: 위 산식 채택.

### Task 0.6: `mapping_corrections` schema 정합 (drift #N2)

**의도**: postgres.md spec 의 (original, corrected) JSONB 안에 work_content / company / trade / correction_type 박는 우회 path → 본 cycle 에서 schema 정합 검토 또는 영구 우회.

**결정 권고**: 본 cycle 영구 우회 (JSONB 안에 합쳐 박음). 다음 cycle 에 schema 정합 정정.

---

## Phase 1 — DB schema migration

### Task 1.1: `forecasts.wa` 컬럼 추가 migration

**Files:**
- Create: `infra/postgres/migrations/2026-05-18_forecasts_wa.sql`
- Test: `pipeline/tests/test_db_forecasts_wa.py`

**Steps:**
- [ ] 실패 테스트 작성 — `test_forecasts_has_wa_column` (information_schema 조회)
- [ ] migration SQL 작성 — `ALTER TABLE forecasts ADD COLUMN wa TEXT;` + `idx_forecasts_company_l6` 삭제 + `idx_forecasts_wa_company_l6` 신규
- [ ] migration 적용 (dev + prod)
- [ ] 테스트 PASS 검증
- [ ] commit: `feat(schema): forecasts.wa TEXT 컬럼 추가`

### Task 1.2: `mapped_history` 신규 테이블 migration

**Files:**
- Create: `infra/postgres/migrations/2026-05-18_mapped_history.sql`
- Test: `pipeline/tests/test_db_mapped_history.py`

**Steps:**
- [ ] 실패 테스트 (table 존재 + UNIQUE constraint + 2 인덱스)
- [ ] migration SQL:
```sql
CREATE TABLE IF NOT EXISTS mapped_history (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
  report_date DATE NOT NULL,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  wa TEXT NOT NULL,
  l6_main TEXT NOT NULL,
  company TEXT NOT NULL,
  today_qty NUMERIC,
  today_assigned_workers NUMERIC,
  unit TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, wa, l6_main, company)
);
CREATE INDEX idx_mapped_history_site_date ON mapped_history (site_id, report_date DESC);
CREATE INDEX idx_mapped_history_triplet  ON mapped_history (wa, l6_main, company, report_date DESC);
```
- [ ] migration 적용 + 테스트 PASS
- [ ] commit: `feat(schema): mapped_history 신규 테이블 + UNIQUE + 2 인덱스`

---

## Phase 2 — Forecaster wa 재구조

### Task 2.1: `state.py` Activity TypedDict 검토

**Files:**
- Read: `pipeline/state.py` (변경 0 — Activity 의 `wa: str | None` 이 이미 존재)

**Steps:**
- [ ] Activity 의 wa field 확인 (state.py:51) — 변경 X
- [ ] Forecaster 가 사용하는 wa 가 mapped 의 wa 와 정합 확인

### Task 2.2: `forecaster/agent.py` group_by tuple 3 → 4

**Files:**
- Modify: `pipeline/agents/forecaster/agent.py:229~277`
- Test: `pipeline/tests/test_forecaster_wa_grain.py`

**Steps:**
- [ ] 실패 테스트 — 동일 (company, l6_main) 의 다른 wa 가 2 row 로 분리되는지
- [ ] groups dict key = `(a["company"], a["l6_main"])` → `(a["wa"], a["company"], a["l6_main"])`
- [ ] forecast row dict 의 wa 필드 추가 (line 191~226)
- [ ] insert_forecast helper 의 wa 컬럼 INSERT 추가 (db.py:205)
- [ ] 테스트 PASS + 회귀 197 PASS 유지
- [ ] commit: `perf(forecaster): wa 차원 group_by 추가 (Q1 triplet grain)`

### Task 2.3: `classify_assessment` / `classify_risk_level` 검토

**Files:**
- Read: `pipeline/agents/forecaster/classify.py`

**Steps:**
- [ ] 입력에 wa 의존 logic 없음 확인 (산식이 group 별 독립)
- [ ] 변경 X 또는 wa 컬럼만 row dict 에 추가

---

## Phase 3 — Atomizer mapped_history INSERT

### Task 3.1: `db.py` `insert_mapped_history_batch` helper 신규

**Files:**
- Modify: `pipeline/db.py:380+` (append after insert_daily_report)
- Test: `pipeline/tests/test_db_mapped_history_helper.py`

**Steps:**
- [ ] 실패 테스트 — batch INSERT + ON CONFLICT 멱등성
- [ ] helper 산식:
```python
async def insert_mapped_history_batch(
    self,
    run_id: uuid.UUID,
    report_date: date,
    site_id: str,
    rows: list[dict],  # [{wa, l6_main, company, today_qty, today_assigned_workers, unit}, ...]
) -> None:
    if not rows:
        return
    await self._pool.executemany(
        """
        INSERT INTO mapped_history (run_id, report_date, site_id, wa, l6_main, company, today_qty, today_assigned_workers, unit)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE SET
          today_qty = EXCLUDED.today_qty,
          today_assigned_workers = EXCLUDED.today_assigned_workers
        """,
        [(run_id, report_date, site_id, r["wa"], r["l6_main"], r["company"], r["today_qty"], r["today_assigned_workers"], r["unit"]) for r in rows],
    )
```
- [ ] 테스트 PASS
- [ ] commit: `feat(db): insert_mapped_history_batch helper`

### Task 3.2: `atomizer.py` mapped_history INSERT 통합

**Files:**
- Modify: `pipeline/agents/atomizer.py`

**Steps:**
- [ ] state.mapped 순회 안에 triplet group_by 산식 추가
- [ ] insert_mapped_history_batch 호출 (Chroma 적재 직후)
- [ ] 회귀 + 실 prod 1 cycle 검증 (row 30~80 INSERT)
- [ ] commit: `feat(atomizer): mapped_history PG 적재 (Q2)`

---

## Phase 4 — FastAPI 신규 구현 (pipeline/api.py 0 → 11 endpoint)

### Task 4.1: `pipeline/api.py` 골격 + lifespan + LangGraph 통합

**Files:**
- Create: `pipeline/api.py` (현재 0 lines)
- Test: `pipeline/tests/test_api_smoke.py`

**Steps:**
- [ ] FastAPI app 생성 + asyncpg pool lifespan
- [ ] LangGraph build_graph + checkpointer 통합
- [ ] 스모크 테스트 — `/health` 200 OK
- [ ] commit: `feat(api): FastAPI 골격 + lifespan + LangGraph build`

### Task 4.2: POST `/api/runs/:run_id/hil_1/resume` (G-10)

**Files:**
- Modify: `pipeline/api.py`
- Test: `pipeline/tests/test_api_hil1_resume.py`

**Steps:**
- [ ] 실패 테스트 — corrections body 받으면 graph 재개 + next_node 반환
- [ ] endpoint 구현 — body 검증 (string key 필수) + LangGraph Command(resume=corrections) + ainvoke
- [ ] hil_1_node 가 int(k) 변환 처리 (drift #N5 우회)
- [ ] mapping_corrections PG 적재 (Phase 0 결정 정합)
- [ ] 테스트 PASS
- [ ] commit: `feat(api): POST /api/runs/:id/hil_1/resume (G-10)`

### Task 4.3 ~ 4.11: 나머지 10 endpoint

각 endpoint = 1 task × ~30 line. 산식은 Phase 0 + data-contract/crosswalk.md §F 참조.

| # | Endpoint | 응답 type | Phase 0 산식 | brain slug |
|---|---|---|---|---|
| 4.3 | GET `/api/sites` | `Site[]` | api-contract §3.1 SQL | (D-1) |
| 4.4 | GET `/api/runs/:id/optimizer` | `OptimizerOutput[]` | optimizer_advice row 그대로 | [[cpia-optimizer-array-grain-2026-05-18]] |
| 4.5 | GET `/api/runs/:id/wp_summary` | `WPSummaryRow[]` | activity_master + mapped_history join | [[cpia-wpsummary-progress-path-2026-05-18]] |
| 4.6 | GET `/api/sites/:id/reports?days=30` | `ReportDaily[]` | pipeline_runs JOIN forecasts GROUP BY date | (G-4) |
| 4.7 | GET `/api/dashboard/performance` | `fleet_kpi` 4 field | 전 site AVG/SUM + recoverable_days (Task 0.5) | (G-5) |
| 4.8 | GET `/api/dashboard/impact` | `ImpactSiteDistribution[]` | sites 컬럼 직접 | (G-6) |
| 4.9 | GET `/api/agents/status` | `AgentStatus[]` 7 | hard-code 메타 + active_count (Task 0.4) | (G-7) |
| 4.10 | GET `/api/sites/:id/wbs_tree` | `WBSNode` | activity_master GROUP BY 트리 derive | (G-3) |
| 4.11 | GET `/api/tasks?site_id=X&days=30` | `{ tasks, progressByDate, itemsByDate }` | mapped_history + state checkpoint snapshot | [[cpia-tasks-page-be-formulas-2026-05-18]] |

각 task = 실패 테스트 → 구현 → PASS → commit.

---

## Phase 5 — BFF route 신규 (web/app/api/)

### Task 5.1 ~ 5.11: BFF proxy 11 route

각 task = FastAPI endpoint 1 개 ↔ Next.js BFF route 1 개. ~10 line × 11 = ~110 lines 총.

**파일 패턴**:
```
web/app/api/sites/route.ts                          → FastAPI /api/sites
web/app/api/runs/[run_id]/optimizer/route.ts        → /api/runs/:id/optimizer
web/app/api/runs/[run_id]/wp_summary/route.ts       → /api/runs/:id/wp_summary
web/app/api/sites/[site_id]/reports/route.ts        → /api/sites/:id/reports
web/app/api/dashboard/performance/route.ts          → /api/dashboard/performance
web/app/api/dashboard/impact/route.ts               → /api/dashboard/impact
web/app/api/agents/status/route.ts                  → /api/agents/status
web/app/api/sites/[site_id]/wbs_tree/route.ts       → /api/sites/:id/wbs_tree
web/app/api/tasks/route.ts                          → /api/tasks
web/app/api/runs/[run_id]/hil_1/resume/route.ts     → POST /api/runs/:id/hil_1/resume
```

각 route = FastAPI 호출 + 응답 그대로 반환. 환경변수 `FASTAPI_URL=http://127.0.0.1:8001`.

---

## Phase 6 — FE 변경 (시각화 X, 데이터 흐름만)

### Task 6.1: `web/lib/types.ts` OptimizerOutput[] 변경

**Files:**
- Modify: `web/lib/fixtures.ts:34` — `optimizer: OptimizerOutput` → `optimizer: OptimizerOutput[]`

**Steps:**
- [ ] type 변경
- [ ] 회귀 — TypeScript 컴파일 통과
- [ ] commit: `refactor(types): ReportDetail.optimizer 배열 (D-12 실 구현)`

### Task 6.2: `data/mock_report.json` 갱신

**Files:**
- Modify: `data/mock_report.json` — `optimizer: {...}` → `optimizer: [{...}]` + wp_summary 의 wp_id 형식 `wa-l6-company` 로 갱신

**Steps:**
- [ ] mock 단일 → 배열 변환
- [ ] wp_id mock = "FAB-거푸집공사-A건설" 형식 (Q3 정합)
- [ ] commit: `chore(mock): optimizer 배열 + wp_id triplet 형식`

### Task 6.3: `web/app/(app)/reports/page.tsx:156` 갱신

**Files:**
- Modify: `web/app/(app)/reports/page.tsx:156`

**Steps:**
- [ ] `<OptimizerResult output={detail.optimizer} />` → `<OptimizerResult output={detail.optimizer.find(o => o.wp_id === selectedWpId) ?? detail.optimizer[0]} />`
- [ ] FE 시각화 (chip / 색상 / 아이콘) 변경 X 검증
- [ ] commit: `feat(reports): § 03 Optimizer selectedWpId 기반 1 개 선택`

### Task 6.4: `web/app/(app)/review/page.tsx` corrections POST

**Files:**
- Modify: `web/app/(app)/review/page.tsx:51~62`

**Steps:**
- [ ] handleConfirmAll() 가 corrections 객체 생성 후 fetch POST 호출:
```typescript
const corrections: Record<string, { wa: string; l6_main: string }> = {};
cards.filter(c => c.confidence >= 0.8 && c.status === "unconfirmed").forEach(c => {
  const idx = parseInt(c.id.split("-").pop()!, 10).toString();  // r-xxxxxxxx-001 → "1"
  const [wa, l6] = c.ai_mapped_wp_id.split("-", 2);
  corrections[idx] = { wa, l6_main: l6 };
});
const res = await fetch(`/api/runs/${runId}/hil_1/resume`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ corrections }),
});
```
- [ ] FE 시각화 (버튼 / 카드 chip) 변경 X 검증
- [ ] commit: `feat(review): handleConfirmAll → /hil_1/resume POST (G-10)`

### Task 6.5 ~ 6.10: 각 page 의 mock fetch → real BFF route swap

각 task = 1 page 의 `fetch("/api/mock/...")` → `fetch("/api/...")` 로 변경. mock route 5 개는 보존 (선택 fallback).

---

## Phase 7 — 회귀 + 시연 검증

### Task 7.1: 회귀 197 PASS 유지

**Steps:**
- [ ] `pipeline/.venv/bin/python3 -m pytest pipeline/tests/` 197+ PASS 확인
- [ ] 신규 test ~25 추가 (Phase 1~6 의 각 task TDD)
- [ ] 회귀 PASS

### Task 7.2: prod 실 1193 cycle 1 회 성공

**Steps:**
- [ ] colima Chroma 안정성 patch (mapper.py 의 ChromaClient 재사용)
- [ ] 또는 Chroma 호스트 직접 설치
- [ ] prod 실 일보 1 cycle (1193 activities) graph 통과
- [ ] forecasts row count 검증 (1 row → ~150 row triplet group)
- [ ] mapped_history 30~80 row INSERT 검증

### Task 7.3: FE 5 page 실 데이터 시각화 검증

**Steps:**
- [ ] FastAPI + BFF + Next.js dev 재시작
- [ ] /home + /dashboard + /tasks + /review + /reports 5 page 200 OK + 실 BE 데이터 표시
- [ ] /reports § 03 WPSummaryTable 의 N row 표시 (실 prod ~50~100)
- [ ] /reports § 03 Optimizer 4 분면 클릭 시 그 WP 의 Optimizer 권고 표시
- [ ] /review confirm 액션 → mapping_corrections PG row 적재 + graph 재개

### Task 7.4: 사장님 시연 시나리오 리허설

**Steps:**
- [ ] 시연 시나리오 v1: /home → /dashboard → /tasks → /review (확정) → /reports (5 섹션 인과 흐름)
- [ ] 사장님 질문 대응 시나리오 ("이 숫자는?" / "이게 왜 이상?")
- [ ] D-Day 2026-06-05 (목) 시연 준비 완료

---

## 산출물

- **brain decisions** (본 cycle 흡수): 9 신규 + 2 feedback memory (이미 저장 완료 2026-05-18)
- **data-contract 카탈로그 갱신**: 7 파일 (이미 갱신 완료 2026-05-18)
- **PR 1 개** (위 Phase 1~7 통합 commit):
  - migrations 2 (forecasts.wa + mapped_history)
  - Forecaster wa 재구조
  - Atomizer mapped_history INSERT
  - FastAPI 11 endpoint
  - BFF 11 route
  - FE type/page 6+ 변경
  - 회귀 197+25 PASS

**조형준 프로 머지 결정**.

---

## 다음 cycle (Plan 종료 후)

- ChatMessage Hybrid (DB derive) — D-4 followup
- s_curve 회복 곡선 디테일 (Phase 0.3 의 회복 곡선만 보류 부분)
- /dashboard/diagnosis-preview 라우트 제거 (D-3 EWMA 드랍 정합)
- mapping_corrections schema 정합 (drift #N2)
- multi-site 확장 (multi-building 지원)
