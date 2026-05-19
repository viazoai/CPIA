# CPIA Reports 강화 — Parser MH 환산 + EVM CPI 진단 + WP 4칸 연결 + 공기단축 시나리오

> 작성: 2026-05-19. Brainstorming cycle 산출. Brain decisions 흡수:
> - [[decisions/cpia-d3-ewma-drop-2026-05-18]] (FE diagnosis-adapter mock 영구) 정합
> - [[decisions/cpia-wpsummary-grain-2026-05-18]] (wp_id triplet) 정합
> - [[decisions/cpia-tasks-stage-source-y-2026-05-19]] (PG row count 옵션 Y) 정합
> - data-contract D-12 (OptimizerOutput[] 결정) — 본 spec 에선 view_builder.by_wp dict 그대로 노출 + FE 가 dict lookup (대체 path 채택, §6 명시)
>
> 본 spec 은 PoC 데모 마감 2026-06-05 (목) 까지의 단일 cycle scope. 한국방송회관 / Cost_agent 등 타 프로젝트 무관.

---

## §0. Problem statement

`/reports` 페이지에 진입했을 때 다음 영역이 비어 보임:
1. 업체별 현장 생산성 (`/ 01` ProductivityBarToggle)
2. 공종별 현장 생산성 (`/ 01` ProductivityBarToggle 토글)
3. 리스크/대안 검토 (`/ 02` WP 클릭 시 우측 진단/유사사례/권고사항/상세현황 4칸)
4. 공기단축 예측 시나리오 (`/ 03` ForecastChart)

원인 3 가지 (전수조사 확인):

| 원인 | 위치 | 영향 |
|---|---|---|
| **A. FE 가 mock 호출** | `web/app/(app)/reports/page.tsx:28` 의 `fetch("/api/mock/report")` | 모든 영역 실 데이터 안 옴 |
| **B. EVM AC 산식 결손** | `pipeline/agents/mapper.py:486-501` 의 `cum_workers_today × 8.0` — 8h 고정 + 단일 일자치 (이름 misleading) | CPI = EV/AC 가 비현실적 (AC 분모가 1/30 ~ 1/100 수준 → CPI 폭주). 업체별/공종별/WP 별 막대 신뢰 불가 |
| **C. WP 클릭 shape 불일치** | BE = `optimizer_view_jsonb.by_wp[wp_id]` dict / FE = `<OptimizerResult output={detail.optimizer}>` single | WP 클릭해도 같은 데이터 또는 빈값 |

본 spec 의 목표 = 세 원인 동시 해소 + 공기단축 시나리오 신설.

---

## §1. Scope / Non-scope

### Scope (본 cycle 변경)

| Layer | 변경 | 책임 |
|---|---|---|
| Parser | 변경 0 (기존 parser_job_allocations 시트2 jsonb 6칸 그대로 사용) | A_Track |
| Mapper | mapper.py:476-502 의 prorate 산식을 시간대 가중 MH 환산으로 교체 | A_Track |
| Optimizer view_builder | `_build_scenarios()` 신규 + daily_reports.scenarios_jsonb UPSERT 추가 | A_Track |
| PG migration | `2026-05-19_scenarios_jsonb.sql` 신설 (1 컬럼) | A_Track |
| FE API route | `web/app/api/reports/[site]/[date]/route.ts` (신설), `web/app/api/reports/[site]/list/route.ts` (신설) | B_Track |
| FE page | `reports/page.tsx:28` fetch 교체 + OptimizerResult by_wp lookup 어댑터 | B_Track |
| FE adapter | `web/lib/diagnosis-adapter.ts` scenarios fallback 분기 | B_Track |
| FE types | `web/lib/fixtures.ts` ReportDetail shape 업데이트 (optimizer_view + scenarios) | B_Track |

### Non-scope (의도적 drift)

- **FE 컴포넌트 render / Tailwind / 디자인 변경 0** — 조형준 프로 디자인 보존. (사용자 명시 2026-05-19)
- ProductivityDiagnosis EWMA / band — D-3 결정 영구 (FE adapter mock 유지)
- HIL 1 resume — 별 cycle
- AgentStageProgress (옵션 Y) 의 stash PG 테이블 변경 — 별 cycle (BE-T1~T7)
- mapped_history.trade 컬럼 추가 — 별 cycle (D-16)

---

## §2. EVM CPI 산식 정의 (사용자 옵션 B 채택)

본 cycle 의 "현장 생산성" = EVM CPI (= Earned Value / Actual Cost).

### §2.1 변수

| 변수 | 산식 | 데이터 source | Grain |
|---|---|---|---|
| `PV` (Planned Value, 누적 계획 MH) | `Σ am.plan_mh_rev2 × LEAST(1.0, GREATEST(0.0, (today − am.plan_start + 1) / (am.plan_finish − am.plan_start + 1)))` | `activity_master` | site / company / l6_main / (wa, l6_main, company) |
| `EV` (Earned Value, 획득가치 MH) | `(Σ ma.today_cum_qty / Σ am.plan_total_qty) × Σ am.plan_mh_rev2` | `mapper_activities.today_cum_qty` (시트4 col 12 — 시계열 누적 OK) + `activity_master` | 위 동일 |
| `AC` (Actual Cost, 누적 실 MH) | `Σ ma.cum_actual_mh_today` | `mapper_activities.cum_actual_mh_today` (본 cycle 산식 fix 후 진짜 누적 — §3) | 위 동일 |
| **CPI** | `EV / AC × 100` | derived | 위 동일 (%) |
| **SPI** | `EV / PV × 100` | derived | 위 동일 (%) |

### §2.2 의미

- **CPI 100%** = 계획 인공 대비 실 인공 동등 (효율 정상)
- **CPI > 100%** = 더 적은 인공으로 동일 진척 (효율 우위)
- **CPI < 100%** = 더 많은 인공 (효율 열위)
- **SPI 100%** = 계획 진척률 = 실 진척률 (일정 정상)
- **SPI < 100%** = 진척 지연

### §2.3 ProductivityBar status 매핑 (변경 0, view_builder.py:283-288 그대로)

```python
def _bar_status(cpi: float) -> str:
    if cpi >= 90: return "normal"
    if cpi >= 80: return "caution"
    return "risk"
```

---

## §3. Parser MH 환산 (mapper.py:476-502 교체)

### §3.1 시계열 누적 가정 (검증 V1)

Parser 가 이미 시트2 의 `workers_yesterday_cum` / `workers_today_incr` / `workers_today_cum` 시간대 6칸 dict 를 `parser_job_allocations` 에 적재 중. 시트4 의 `today_cum_qty = yesterday_cum_qty + today_qty` 시계열 누적 산식 (parser_llm.py:289-291) 과 동일 패턴으로 시트2 도 시계열 누적 가정.

**가정**: `workers_today_cum.total` = plan_start 시점부터 today 까지의 **history 누적 인원-day** (시간대 6칸 분해).

**검증 V1 (Phase 0)**: 실 DB 1 row sample 로 `yesterday_cum.total + today_incr.total ≈ today_cum.total` 확인. 깨지면 spec G-1 으로 분기.

### §3.2 시간대 가중치

| 시간대 | 가중 시간 | 근거 |
|---|---|---|
| `morning` (조출) | 2h | 통상 06:00 ~ 08:00 전 작업 |
| `daytime` (주간) | 8h | 표준 근무 |
| `overtime` (연장) | 4h | 통상 17:00 ~ 21:00 |
| `night` (야간) | 8h | 22:00 ~ 06:00 |
| `all_night` (철야) | 12h | 야간 + 익일 조출 연속 |

**근거 출처 명시**: 산업안전공단 시간대 정의 참조. PoC 단계 가중치 — Phase 2 에서 회사 표준노임단가 또는 실 노무비 데이터로 보정 가능.

### §3.3 신규 산식 (mapper.py 교체)

**삭제 대상** (mapper.py:476-502):
```python
# 기존 — 8h 고정, daily 의미
for a in out:
    if a.get("l6_main"):
        c = a["company"]
        workers_c = job_alloc_company_sum.get(c, 0)  # ← workers_cum_t total (시간대 합산만)
        ...
        a["cum_workers_today"] = workers_c × ratio
        a["cum_actual_mh_today"] = a["cum_workers_today"] × 8.0
```

**신규** (위 위치 교체):
```python
# 1. company 단위 시간대 가중 누적 MH (시트2 jsonb 6칸 분해 + 가중치)
_SHIFT_WEIGHTS = {
    "morning":   2.0,
    "daytime":   8.0,
    "overtime":  4.0,
    "night":     8.0,
    "all_night": 12.0,
}

def _weighted_mh_from_shift(shift_dict: dict | None) -> float:
    """parser_job_allocations.workers_today_cum jsonb → 가중 MH."""
    if not shift_dict:
        return 0.0
    return sum(
        float(shift_dict.get(k, 0) or 0) * w
        for k, w in _SHIFT_WEIGHTS.items()
    )

# company 단위 history 누적 MH 합
company_weighted_mh: dict[str, float] = {}
for ja in parsed_report.get("job_allocations", []):
    if ja.get("final_flag") != "O":
        continue
    c = ja.get("company")
    if c:
        mh = _weighted_mh_from_shift(ja.get("workers_today_cum"))
        company_weighted_mh[c] = company_weighted_mh.get(c, 0.0) + mh

# 2. l6 비례 분배 (기존 분배 로직 유지)
for a in out:
    if a.get("l6_main"):
        c = a["company"]
        weighted_mh_c = company_weighted_mh.get(c, 0.0)
        company_mh = company_total_plan_mh.get(c, 0.0)
        plan_mh_val = float(a.get("plan_mh") or 0)
        n_l6 = len(active_l6_for_company[c]) if c else 0
        if company_mh > 0 and plan_mh_val > 0:
            cum_actual_mh = weighted_mh_c * (plan_mh_val / company_mh)
            prorate_method = "plan_mh"
        elif n_l6 > 0:
            cum_actual_mh = weighted_mh_c / n_l6
            prorate_method = "uniform_fallback"
        else:
            cum_actual_mh = 0.0
            prorate_method = "zero"
        # cum_workers_today 는 보조 — MH ÷ 8h 환산값 (BI 호환 유지)
        a = {
            **a,
            "cum_actual_mh_today": cum_actual_mh,
            "cum_workers_today": cum_actual_mh / 8.0,
            "prorate_method": prorate_method,
        }
    prorated.append(a)
```

### §3.4 변경 사항 요약

| 항목 | 변경 | 영향 |
|---|---|---|
| `mapper_activities.cum_actual_mh_today` | 의미 fix (8h 고정 → 시간대 가중) | view_builder SQL 변경 0, 의미만 누적 MH 로 정합 |
| `mapper_activities.cum_workers_today` | 의미 보조 (MH ÷ 8h 역산) | BI 호환용. 사용처 없으면 향후 폐기 검토 |
| 신규 컬럼 | 없음 | migration 0 (mapper layer only) |
| Test | `pipeline/tests/test_mapper_weighted_mh.py` 신설 | §7 V2 |

---

## §4. 적재 스키마 변경

### §4.1 신규 migration

`infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql`:
```sql
-- 공기단축 예측 시나리오 jsonb — site 전체 + WP 별 4 시나리오
BEGIN;

ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS scenarios_jsonb JSONB DEFAULT '{}'::jsonb;

COMMENT ON COLUMN daily_reports.scenarios_jsonb IS
  'optimizer view_builder._build_scenarios() 산출. shape: {site: {no_action, optimistic_p25, base_p50, pessimistic_p75}, by_wp: {[wp_id]: 동일 4 키}}. 각 키 = {expected_completion: date, recovery_days: int, delta_days: int}.';

COMMIT;
```

### §4.2 변경 0 (보존)

기존 `daily_reports.{kpi,contractor_bars,trade_bars,quadrant,wp_summary,s_curve,optimizer_view,productivity}_jsonb` 8 컬럼 그대로. view_builder 의 산출 SQL 도 변경 0 — AC 가 §3 으로 정합되면 자동으로 정확한 값 노출.

---

## §5. `scenarios_jsonb` 산식 + shape

### §5.1 shape

```jsonc
{
  "site": {
    "no_action": {
      "expected_completion": "2026-12-31",
      "recovery_days": 0,
      "delta_days": 0,
      "case_count": 0
    },
    "optimistic_p25": {
      "expected_completion": "2026-12-10",
      "recovery_days": 21,
      "delta_days": -21,
      "case_count": 23
    },
    "base_p50":      { /* 동일 4 키 */ },
    "pessimistic_p75": { /* 동일 4 키 */ }
  },
  "by_wp": {
    "<wp_id>": { /* 동일 4 시나리오 (각 wp 의 recovery_distribution 기반) */ }
  }
}
```

`wp_id` 형식 = `f"{wa}-{slug(l6_main)}-{slug(company)}"` (view_builder.py:357 `_wp_id_of` 그대로 재사용).

### §5.2 산출 산식

**입력**:
- `forecast: list[dict]` — `forecasts` row 들. `expected_completion`, `delay_days`, `wa`, `company`, `l6_main` 포함.
- `advice_rows: list[dict]` — `optimizer_advice` row 들. `recovery_distribution` 포함.

**Step 1 — recovery_distribution 을 percentile 산출 가능한 list 로 expand**:
```python
def _expand_recovery_to_days(dist: dict[str, int]) -> list[int]:
    """{'d+1': 3, 'd+2': 5, 'not_recovered': 2} → [1,1,1, 2,2,2,2,2, 30,30].
    
    not_recovered 는 +30 일 캡 (산식 안정성). 실 의미는 "회복 안 됨" 으로 별도 노출 가능.
    """
    out: list[int] = []
    for key, count in (dist or {}).items():
        if key == "not_recovered":
            out.extend([30] * int(count))
        elif key.startswith("d+"):
            d = int(key[2:])
            out.extend([d] * int(count))
    return out
```

**Step 2 — percentile 산출** (numpy 의존성 없이 statistics 표준):
```python
import statistics

def _percentile(days: list[int], q: float) -> int:
    """q in [0,1]. 빈 list → 0."""
    if not days:
        return 0
    sorted_days = sorted(days)
    # quantiles 10분위 후 q×10 인덱스
    if len(sorted_days) < 4:
        # 데이터 부족 — q 비례 단순 선택
        idx = min(len(sorted_days) - 1, int(q * len(sorted_days)))
        return sorted_days[idx]
    cuts = statistics.quantiles(sorted_days, n=100, method="inclusive")
    return int(round(cuts[max(0, min(98, int(q * 100) - 1))]))
```

**Step 3 — site / by_wp 시나리오 산출**:
```python
def _build_scenarios(
    advice_rows: list[dict],
    forecast: list[dict],
) -> dict:
    # site 전체: 모든 advice 의 recovery_distribution merge
    site_days: list[int] = []
    for advice in advice_rows:
        site_days.extend(_expand_recovery_to_days(advice.get("recovery_distribution") or {}))
    site_no_action = _site_expected_completion(forecast)  # MAX(expected_completion) 또는 가중평균
    site_scenarios = {
        "no_action": {
            "expected_completion": site_no_action.isoformat() if site_no_action else None,
            "recovery_days": 0,
            "delta_days": 0,
            "case_count": len(site_days),
        },
        "optimistic_p25":  _scenario(site_no_action, _percentile(site_days, 0.25), len(site_days)),
        "base_p50":        _scenario(site_no_action, _percentile(site_days, 0.50), len(site_days)),
        "pessimistic_p75": _scenario(site_no_action, _percentile(site_days, 0.75), len(site_days)),
    }
    
    # by_wp: advice 별 (company, l6_main) → forecast 매칭으로 wa lookup → wp_id
    by_wp: dict[str, dict] = {}
    for advice in advice_rows:
        f = _match_forecast(advice, forecast)
        if f is None:
            continue
        wp_id = _wp_id_of(f.get("wa"), advice["l6_main"], advice["company"])
        wp_days = _expand_recovery_to_days(advice.get("recovery_distribution") or {})
        wp_no_action = f.get("expected_completion")
        by_wp[wp_id] = {
            "no_action": {
                "expected_completion": wp_no_action.isoformat() if wp_no_action else None,
                "recovery_days": 0,
                "delta_days": 0,
                "case_count": len(wp_days),
            },
            "optimistic_p25":  _scenario(wp_no_action, _percentile(wp_days, 0.25), len(wp_days)),
            "base_p50":        _scenario(wp_no_action, _percentile(wp_days, 0.50), len(wp_days)),
            "pessimistic_p75": _scenario(wp_no_action, _percentile(wp_days, 0.75), len(wp_days)),
        }
    
    return {"site": site_scenarios, "by_wp": by_wp}


def _scenario(no_action_date: date | None, recovery_days: int, case_count: int) -> dict:
    if no_action_date is None or recovery_days <= 0:
        return {
            "expected_completion": no_action_date.isoformat() if no_action_date else None,
            "recovery_days": recovery_days,
            "delta_days": 0,
            "case_count": case_count,
        }
    new_date = no_action_date - timedelta(days=recovery_days)
    return {
        "expected_completion": new_date.isoformat(),
        "recovery_days": recovery_days,
        "delta_days": -recovery_days,
        "case_count": case_count,
    }
```

### §5.3 산출 위치

`pipeline/agents/optimizer/agent.py` 의 `optimize()` 함수 (현 line 170-196) 의 view_jsonbs 박는 블록에 1 줄 추가:
```python
view_jsonbs = {
    "productivity_jsonb": productivity,
    "kpi_jsonb": await _build_kpi(pg, site_id, today, productivity),
    "contractor_bars_jsonb": _build_contractor_bars(productivity),
    "trade_bars_jsonb": _build_trade_bars(productivity),
    "quadrant_jsonb": quadrant,
    "wp_summary_jsonb": await _build_wp_summary(pg, site_id, today, productivity, quadrant),
    "s_curve_jsonb": await _build_s_curve(pg, site_id, today),
    "optimizer_view_jsonb": _build_optimizer_view(advice_rows, forecast, mapped),
    "scenarios_jsonb": _build_scenarios(advice_rows, forecast),  # ← 신규
}
```

### §5.4 cold_start / 데이터 부족 처리

| 상황 | 동작 |
|---|---|
| `advice_rows` 가 0개 (optimizer 미실행) | scenarios_jsonb = `{}` 빈 dict |
| `recovery_distribution` 가 모두 0건 | `_expand_recovery_to_days` → 빈 list → percentile 0 → 모든 시나리오 = no_action 과 동일 (delta 0) |
| `recovery_distribution` 가 `not_recovered` 만 | percentile 모두 30 (+30 cap) → 시나리오 3개 모두 "recovery 어려움" 신호 |
| `forecast` 매칭 실패 | by_wp 에 미포함 (silently skip) |

---

## §6. FE 매핑 (FE UI 변경 0)

### §6.1 신규 endpoint

`web/app/api/reports/[site]/list/route.ts` (신설):
```typescript
// GET /api/reports/{site}/list
// → ReportDaily[] (date list, 좌측 sticky panel 용)
// SQL: SELECT report_date, ... FROM daily_reports WHERE site_id=$1 ORDER BY report_date DESC LIMIT 30
```

`web/app/api/reports/[site]/[date]/route.ts` (신설):
```typescript
// GET /api/reports/{site}/{date}
// → ReportDetail (단일 일자 상세, 9 jsonb 풀어서 노출)
// SQL: SELECT 
//   kpi_jsonb              AS kpi,
//   productivity_jsonb     AS productivity,
//   contractor_bars_jsonb  AS contractor_bars,
//   trade_bars_jsonb       AS trade_bars,
//   quadrant_jsonb         AS quadrant,
//   wp_summary_jsonb       AS wp_summary,
//   s_curve_jsonb          AS s_curve,
//   optimizer_view_jsonb   AS optimizer_view,
//   scenarios_jsonb        AS scenarios
// FROM daily_reports WHERE site_id=$1 AND report_date=$2 LIMIT 1
```

### §6.2 page.tsx 변경 (3 곳)

| 위치 | 변경 |
|---|---|
| `reports/page.tsx:28` | `fetch("/api/mock/report")` → `fetch("/api/reports/{site}/list")` + 첫 date 자동 선택 시 lazy fetch `/api/reports/{site}/{date}` |
| `reports/page.tsx:188` | `output={detail.optimizer}` → `output={detail.optimizer_view?.by_wp?.[selectedWpId ?? ""] ?? detail.optimizer_view?.by_wp?.[detail.optimizer_view?.default_wp_id ?? ""] ?? {} as OptimizerOutput}` |
| `reports/page.tsx:59` | `diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID))` → 그대로 (어댑터 내부에서 scenarios 분기) |

### §6.3 diagnosis-adapter 어댑터 (분기 추가)

`web/lib/diagnosis-adapter.ts`:
```typescript
export function toDiagnosisInput(
  kpi: ReportKpi,
  sCurve: SCurvePoint[],
  siteId: string,
  scenarios?: ReportDetail["scenarios"],  // ← 신규 optional param
): DiagnosisInput {
  // ... 기존 mock 로직 ...
  
  // scenarios 가 있으면 base_p50 의 recovery_days / delta_days 를 mock 대체
  if (scenarios?.site?.base_p50) {
    return {
      ...mockBase,
      recovery: {
        p25: scenarios.site.optimistic_p25?.recovery_days ?? 0,
        p50: scenarios.site.base_p50.recovery_days,
        p75: scenarios.site.pessimistic_p75?.recovery_days ?? 0,
      },
      // scenarios 의 expected_completion 곡선은 ForecastChart 가 그대로 그림
    };
  }
  
  return mockBase;  // FE adapter mock fallback (D-3 정합)
}
```

ForecastChart 호출부 (page.tsx:195):
```tsx
<ForecastChart
  diagnosis={diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID, detail.scenarios))}
  recoveryActive={selectedWpId !== null}
  delayDays={detail.kpi.delay_days}
  recoveryDays={detail.kpi.recovery_days}
/>
```

ForecastChart **컴포넌트 내부 변경 0** — diagnosis prop 의 recovery 객체만 mock → real 로 자동 전환.

### §6.4 fixtures.ts type 갱신

`web/lib/fixtures.ts`:
```typescript
export type ReportDetail = {
  kpi: ReportKpi;
  productivity: ProductivityView;       // ← 추가 (productivity_jsonb)
  contractor_bars: BarItem[];
  trade_bars: BarItem[];
  quadrant: QuadrantPoint[];
  wp_summary: WPSummaryRow[];
  s_curve: SCurvePoint[];
  optimizer_view: {                     // ← 변경 (optimizer → optimizer_view, by_wp dict)
    by_wp: Record<string, OptimizerOutput>;
    default_wp_id: string | null;
  };
  scenarios?: {                         // ← 신규 optional (cold_start 시 undefined)
    site: ScenarioSet;
    by_wp: Record<string, ScenarioSet>;
  };
  raw_data?: RawDataRow[];
};

export type ScenarioSet = {
  no_action: Scenario;
  optimistic_p25: Scenario;
  base_p50: Scenario;
  pessimistic_p75: Scenario;
};

export type Scenario = {
  expected_completion: string | null;
  recovery_days: number;
  delta_days: number;
  case_count: number;
};
```

### §6.5 mock fixture 정리

- `web/app/api/mock/report/route.ts` 은 **유지** (`/reports?mock=1` 같은 fallback 또는 e2e 시 사용 — 본 cycle 에선 prod path 만 endpoint 교체).
- 추가 작업으로 mock fixture 의 shape 도 신규 ReportDetail 정합으로 갱신 (FE 컴파일 깨지지 않도록).

---

## §7. 검증 plan (Iron Law — Real code 만 인정)

### V1 — Parser 시계열 누적 가정 검증

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -c "
import asyncio
from pipeline.db import PGClient
async def main():
    pg = PGClient('<POSTGRES_URL>')
    await pg.connect()
    rows = await pg._pool.fetch('''
        SELECT bp_code, company,
               workers_yesterday_cum->>'total' AS y_total,
               workers_today_incr->>'total' AS today_incr,
               workers_today_cum->>'total' AS today_cum
        FROM parser_job_allocations
        WHERE final_flag='O'
        LIMIT 10
    ''')
    for r in rows:
        y = int(r['y_total'] or 0)
        i = int(r['today_incr'] or 0)
        c = int(r['today_cum'] or 0)
        ok = (y + i == c)
        print(f'{r[\"company\"]:20s}: {y:4d} + {i:3d} = {y+i:4d} vs cum {c:4d}  {\"OK\" if ok else \"DRIFT\"}')
    await pg.close()
asyncio.run(main())
"
```

**기대 출력**: 모든 row 가 `OK` (시계열 누적 가정 성립). 1 row 라도 `DRIFT` 면 G-1 분기 (시간대 합산 의미 — 시트2 의 cum 은 daily total 일 가능성, 다른 데이터 source 모색).

### V2 — Mapper 가중 MH unit test

`pipeline/tests/test_mapper_weighted_mh.py` (신설):
```python
def test_weighted_mh_from_shift():
    # 주간 10명 + 연장 5명 + 야간 2명
    shift = {"morning": 0, "daytime": 10, "overtime": 5, "night": 2, "all_night": 0, "total": 17}
    # 10×8 + 5×4 + 2×8 = 80 + 20 + 16 = 116
    assert _weighted_mh_from_shift(shift) == 116.0

def test_weighted_mh_from_shift_with_all_night():
    # 철야 3명 만
    shift = {"morning": 0, "daytime": 0, "overtime": 0, "night": 0, "all_night": 3, "total": 3}
    # 3×12 = 36
    assert _weighted_mh_from_shift(shift) == 36.0

def test_weighted_mh_from_none():
    assert _weighted_mh_from_shift(None) == 0.0

def test_prorate_with_weighted_mh():
    # company A: workers_today_cum daytime=100 → 800 MH
    # l6 plan_mh: l6-1=600, l6-2=200 (sum=800)
    # → l6-1 = 800 × 600/800 = 600, l6-2 = 800 × 200/800 = 200
    parsed_report = {
        "job_allocations": [{
            "company": "A", "final_flag": "O",
            "workers_today_cum": {"morning":0, "daytime":100, "overtime":0, "night":0, "all_night":0, "total":100},
        }],
    }
    mapped = [
        {"company": "A", "l6_main": "l6-1", "plan_mh": 600.0},
        {"company": "A", "l6_main": "l6-2", "plan_mh": 200.0},
    ]
    # _prorate_workers_with_mh 호출
    result = _prorate_workers_with_mh(mapped, parsed_report)
    assert result[0]["cum_actual_mh_today"] == 600.0
    assert result[1]["cum_actual_mh_today"] == 200.0
    assert result[0]["prorate_method"] == "plan_mh"
```

### V3 — view_builder EVM 정합

```bash
PYTHONPATH=. pipeline/.venv/bin/python3 -c "
import asyncio
from pipeline.db import PGClient
async def main():
    pg = PGClient('<POSTGRES_URL>')
    await pg.connect()
    row = await pg._pool.fetchrow('''
        SELECT kpi_jsonb, productivity_jsonb 
        FROM daily_reports 
        WHERE site_id='m15x-ph3-ibl' 
        ORDER BY report_date DESC LIMIT 1
    ''')
    print(row['kpi_jsonb'])
    print(row['productivity_jsonb']['today'])
    await pg.close()
asyncio.run(main())
"
```

**기대 검증**:
- `kpi_jsonb.productivity_today` ∈ [50, 150] 범위 (현 폭주값 X)
- `productivity_jsonb.today.spi`, `cpi` 둘 다 0보다 큼
- `productivity_jsonb.by_contractor` 가 비어있지 않음
- AC `ac` 가 PV `pv` 와 같은 자릿수 (3~4배 차이 이내)

### V4 — scenarios_jsonb 단조성

`pipeline/tests/test_optimizer_scenarios.py` (신설):
```python
def test_scenarios_monotonic():
    """p25 ≤ p50 ≤ p75 단조 증가."""
    dist = {"d+1": 2, "d+3": 3, "d+5": 3, "d+10": 2}
    days = _expand_recovery_to_days(dist)
    p25, p50, p75 = _percentile(days, 0.25), _percentile(days, 0.50), _percentile(days, 0.75)
    assert p25 <= p50 <= p75

def test_scenarios_no_action_zero_delta():
    """no_action delta_days = 0."""
    advice_rows = [{"recovery_distribution": {"d+5": 3}}]
    forecast = [{"expected_completion": date(2026, 12, 31), "wa": "WA-1", "company": "A", "l6_main": "L6"}]
    out = _build_scenarios(advice_rows, forecast)
    assert out["site"]["no_action"]["delta_days"] == 0
    assert out["site"]["base_p50"]["delta_days"] == -5

def test_scenarios_cold_start():
    """advice 0건 → 빈 dict."""
    assert _build_scenarios([], []) == {"site": {...}, "by_wp": {}}  # site 는 no_action only
```

### V5 — E2E (Playwright)

`web/e2e/reports-real-data.spec.ts` (신설):
```typescript
test("reports page shows real EVM CPI + WP click toggles 4 panels", async ({ page }) => {
  // 1. /reports 진입
  await page.goto("/reports");
  
  // 2. ProductivityBarToggle 의 contractor bar 첫 row value > 0 (mock 아니라 real)
  await expect(page.locator('[data-testid="contractor-bar-row"]').first().locator('.bar-value')).not.toContainText("0.0");
  
  // 3. QuadrantScatter 의 첫 점 클릭
  await page.locator('[data-testid="quadrant-point"]').first().click();
  
  // 4. OptimizerResult 4 칸 (진단/유사사례/권고사항/상세현황) 모두 비어있지 않음
  await expect(page.locator('text=진단')).toBeVisible();
  await expect(page.locator('text=진단 데이터 없음')).not.toBeVisible();  // diagnosis 실 데이터
  await expect(page.locator('text=유사 사례 없음')).not.toBeVisible();
  
  // 5. ForecastChart 의 recovery 곡선 (data-line) 존재
  await expect(page.locator('[data-line="recovery"]')).toBeVisible();
});
```

---

## §8. 마이그레이션 순서 (atomic commits)

| # | Commit | 영향 |
|---|---|---|
| 1 | `db: add scenarios_jsonb column to daily_reports` (migration) | DB 1 컬럼 추가, 기존 row 영향 0 (default `{}`) |
| 2 | `mapper: replace 8h fixed with shift-weighted MH` (mapper.py + test V2) | mapper_activities.cum_actual_mh_today 의미 fix, downstream forecaster/optimizer 자동 정합 |
| 3 | `optimizer: add _build_scenarios + scenarios_jsonb upsert` (view_builder + agent + test V4) | daily_reports.scenarios_jsonb 채워짐 |
| 4 | `web: add /api/reports/[site]/list + /[date] endpoints + types update` | FE 가 mock 대신 실 DB 호출 가능 |
| 5 | `web: switch reports/page.tsx from mock to real + by_wp lookup + scenarios fallback` | FE 가 실 데이터로 전환 |
| 6 | `web: e2e test reports-real-data.spec.ts` (V5) | regression 방지 |

각 commit 은 단독으로 빌드/테스트 통과. 6 까지 끝나면 reports 페이지가 실 데이터로 동작.

---

## §9. 위험 / 가정

| 위험 | 가정 | 검증 |
|---|---|---|
| 시트2 cum 이 시계열 누적이 아님 (가능성 ~10%) | parser_llm.py:289 의 시트4 패턴이 시트2 에도 동일 적용 | V1 (실 sample row) — DRIFT 시 G-1 분기 (시간대 합산 + atomizer 누적 path 로 대체) |
| 시간대 가중치 (2/8/4/8/12) 가 실 현장과 차이 | 산업안전공단 시간대 정의 — PoC 수준 적정 | Phase 2 에서 회사 표준노임단가표로 보정 |
| recovery_distribution 이 cold_start 일수록 비현실적 percentile | `_expand_recovery_to_days` 가 빈 list 시 graceful degrade (시나리오 = no_action) | V4 test_scenarios_cold_start |
| FE OptimizerResult 의 `details: dict[]` shape 가 by_wp dict 안의 `details` shape 와 정합 안 됨 | view_builder.py:602-609 의 details shape (label/value 쌍) 이 FE OptimizerOutput.details type 과 동일 | V5 E2E 진단 박스 시각 확인 |
| daily_reports 의 site_id 가 mapper 적재 시 None 인 row 가 있음 (drift) | optimizer.optimize() 가 site_id 받음 (state.site_id) — graph.py 검증 | atomizer / graph node 확인 (별 task) |

---

## §10. 향후 cycle 위임

- ProductivityDiagnosis EWMA 부활 검토 (D-3 REVISED 의 향후)
- `mapped_history.day_mh` 컬럼 추가 (옵션 α path — 시드가 충분히 누적된 후 대안)
- recommendations 별 시나리오 (옵션 2 — Phase 2)
- 시간대 가중치 회사 표준노임단가 보정
- mock fixture 정리 / fixture 영구 삭제 (실 endpoint 안정화 후)

---

*spec 끝. 본 cycle 의 implementation plan 은 별도 `docs/superpowers/plans/2026-05-19-cpia-reports-parser-mh-plan.md` 에 후속 작성.*
