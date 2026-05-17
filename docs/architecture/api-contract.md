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

## §6. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-17 | 초안 — PG↔types.ts 매핑 + 8 endpoint + derived 계산식 + 환경 분리 정책 | A_Track |
