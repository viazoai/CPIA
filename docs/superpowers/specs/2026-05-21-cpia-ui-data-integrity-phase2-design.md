# CPIA UI Data Integrity Phase 2 — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement the plan task-by-task. Spec scope is locked — do NOT renegotiate scope. Use `superpowers:writing-plans` next.

**작성일**: 2026-05-21
**Track**: A_Track
**기반**: Phase 1 (`2026-05-21-cpia-data-canonicalization-phase1-design.md`) 완료, PR #38 merged.
**시연 마감**: D-15 (2026-06-05)
**디자인 가드**: `web/app/components/**` markup·className 변경 0 (textContent 만 변경 허용 — 사용자 직접 요청 부분)

---

## Goal

530일 더미 적재 후 dev server 5536 에서 발견된 6 RC 일괄 정합화. 사용자 신고:
1. Tasks 9-25 1162 건 + Review 475 알림 + WBS 트리에 비건축·비토목 공종 (전기/설비/UT/소방/제어) 활성 — **저번 세션에 건축+토목만 적재하기로 했는데 격리 안 됨**
2. Reports WP 클릭 시 옆 카드 4 슬롯 (진단/유사사례/권고/상세) 모두 `cold_start` fallback
3. Reports WP 목록 productivity 표시 `4 (4 1차/일... m²)` 형식 — `80.1%` 만 원함
4. Export ZONE 67% 빈칸, "출력인원 현황" 탭 이름 + 조출/주간/연장 컬럼 숨기기, 4번 탭 "물량" 으로
5. Dashboard fixture JSON 의존 — 실 PG 데이터로 swap
6. WP 카드 자연어 형식: "보통 인당 N unit 작업하는데 오늘은 인당 M unit (P%) 로 작업했습니다 … 이유" (사용자 확정 A안)

## Architecture

```
┌─── PG public schema (AWS 43.200.85.209:5532) ────────────────────────────────┐
│                                                                              │
│  [DELETE] trade NOT IN ('건축','토목') row 격리                             │
│  ├─ mapper_activities      ~107K row 제거 (전기/설비/UT/소방/제어/공통가설) │
│  ├─ parser_activities      ~107K row 종속 제거                              │
│  ├─ parser_reports.jsonb   bp_summaries / job_allocations / equipment_alloc │
│  │                          안 trade 필터 (jsonb_array 재구성)              │
│  └─ requires_review        격리 후 잔존 자연 감소                            │
│                                                                              │
│  [BACKFILL v2 확장] daily_reports.jsonb 6 → 9 컬럼                          │
│  └─ optimizer_view_jsonb / scenarios_jsonb / s_curve_jsonb 추가 갱신        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── PG backup_20260521 schema (사용자 1년 더미 보존) ─────────────────────────┐
│  19 테이블 byte-exact 유지 — 본 작업 영향 0 (snapshot 검증 강제)            │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── ChromaDB daily_activities (43.200.85.209:5533) ───────────────────────────┐
│  [BACKFILL] mapper_activities 530일 (건축+토목) → 27,484 row upsert         │
│  - metadata: l7_5_activity / l6_main / company / date / unit / perperson    │
│  - run_id="backfill_v2" (synthetic_v2 옛 10,056 row 보존)                   │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── pipeline/agents/optimizer/ 코드 변경 ─────────────────────────────────────┐
│  view_builder._build_productivity_views_v2                                   │
│   - SELECT 에 ma.wa 추가                                                     │
│   - quadrant/wp_summary 의 wp_id = _wp_id_of(wa, l6, company)               │
│   - return dict 9 key (kpi/productivity/cb/tb/q/wp/ov/sc/scurve)            │
│   - by_wp 미할당 WP 마다 _build_deterministic_cold_start 자동 채움          │
│  retrieve.py 4 함수 l7_5_activity arg 추가                                   │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── web/app FE 변경 (markup/className 0, textContent 만) ─────────────────────┐
│  reports/WPSummaryTable.tsx       display_label 무시 → "${productivity}%"   │
│  charts/QuadrantScatter.tsx       tooltip 일관성                            │
│  export/ConsolidatedReportCard    탭 라벨 1→"작업사항", 4→"물량" 유지       │
│  export/SheetTable                OUTPUT_MANPOWER_COLS 의 early/day/overtime │
│  api/mock/dashboard               loadFixture → loadReal("dashboard_perf")  │
│  api/mock/consolidated            zone 빈 값 fallback (split_part wa)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

- Python 3.11 + asyncpg + Azure OpenAI text-embedding-3-small (1536d)
- ChromaDB HttpClient
- Next.js 15 App Router + TypeScript
- LangGraph + FastAPI + PostgresSaver (변경 없음)

---

## §1 — DB 정합화 (Root Cause: 격리 미적용)

### 1.1 검증 결과

```
mapper_activities trade 분포 (530일, is_mock=FALSE):
  건축:129,248 / 전기:36,465 / 설비:33,859 / UT:14,666 /
  소방전기:8,500 / 소방설비:7,799 / 제어:4,560 / 토목:3,870 / 공통가설:377
  → ~30% (~107K row) 가 비건축·비토목

requires_review=TRUE: 462 건 모두 9-25 일자 — 격리 전 prototype 잔존
backup_20260521 schema: 19 테이블 (건축 129K + 토목 3.8K + 그외 = 239K) byte-exact 보존
```

### 1.2 작업

| 단계 | SQL (public schema 명시) |
|---|---|
| ① parser_activities 종속 제거 | `DELETE FROM public.parser_activities pa USING public.mapper_activities ma WHERE pa.run_id=ma.run_id AND pa.idx=ma.idx AND ma.trade NOT IN ('건축','토목') AND ma.is_mock=FALSE` |
| ② mapper_activities 제거 | `DELETE FROM public.mapper_activities WHERE trade NOT IN ('건축','토목') AND is_mock=FALSE` |
| ③ parser_reports.jsonb 안 trade 필터 | `bp_summaries / job_allocations / equipment_allocations` jsonb 배열 재구성 (helper SQL: `jsonb_agg(elem) FILTER (WHERE elem->>'trade' IN ('건축','토목'))`) |
| ④ 재 backfill | §2 의 backfill v2 9 컬럼 갱신 |

### 1.3 안전망 5단계 (사용자 명시 요구 — backup 무손실)

1. **DELETE 전 backup_20260521 row count snapshot** (6 테이블) — `_audit_pre_phase2` 테이블 저장
2. **SQL 안 schema prefix 명시** — `public.X` (절대 `backup_20260521.X` 안 들어가게)
3. **트랜잭션 dry-run** — `BEGIN; DELETE …; SELECT trade,COUNT(*) …; ROLLBACK;`
4. **DELETE 후 backup_20260521 무변화 검증** — snapshot 과 byte-exact 일치 (보고 형식 강제)
5. **L2 rollback 1줄 SQL × 6 테이블 보존** — §6.5

### 1.4 예상 영향

- Tasks Parser/Mapper 카운트: 9-25 1162 → ~349 (건축 291 + 토목 58)
- Review WBS 트리: 설비/UT/전기/소방/제어 노드 사라짐
- Reports WP 목록 row 일부 제거 (비건축·비토목 WP)

---

## §2 — Reports WP 카드 매칭 + 4 슬롯 채움

### 2.1 Root Cause (실 코드 검증)

```
backfill_daily_report_views_v2.py 의 _JSONB_COLS = 6 (kpi/productivity/cb/tb/q/wp)
  → optimizer_view_jsonb / scenarios_jsonb / s_curve_jsonb 미갱신 (9-25 prototype 잔존)

view_builder._build_productivity_views_v2 의 wp_id = f"WP-{it['id']}" (mapper.id 정수)
view_builder._build_optimizer_view 의 wp_id = _wp_id_of(wa, l6_main, company) (kebab)
  → 두 식별자 형식 완전 불일치 → 9-25 매칭 0/15 (실 검증)

optimizer_advice: 5,071 row · 459 distinct date (71일 비어있음)
ChromaDB daily_activities: 10,056 row (synthetic_v2 30일치만, l7_5_activity 키 없음)
optimizer.retrieve 검색 key: (company, l6_main) 만 — l7_5_activity 안 봄
```

### 2.2 wp_id 형식 통일

**파일**: `pipeline/agents/optimizer/view_builder.py:1089, 1106`

- `_build_productivity_views_v2` SELECT 에 `ma.wa` 추가
- quadrant 의 `wp_id = _wp_id_of(it["wa"], it["l6_main"], it["company"])`
- wp_summary 의 `wp_id = _wp_id_of(it["wa"], it["l6_main"], it["company"])`
- → optimizer_view.by_wp keys 와 자동 매칭

### 2.3 _build_productivity_views_v2 가 optimizer_view + scenarios + s_curve 도 반환

함수 끝 return dict 에 3 key 추가:

```python
advice_rows = await pg.fetch_all(
    "SELECT * FROM optimizer_advice WHERE run_id IN (SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today,
)
forecast_rows = await pg.fetch_all(
    "SELECT * FROM forecasts WHERE run_id IN (SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today,
)
wa_lookup = _build_wa_lookup(items)
optimizer_view = _build_optimizer_view(advice_rows, forecast_rows, items, wa_lookup)

# 빈 WP 채움 (Section 2.4)
for q in quadrant:
    if q["wp_id"] not in optimizer_view["by_wp"]:
        optimizer_view["by_wp"][q["wp_id"]] = _build_deterministic_cold_start(
            q, master_lookup, chroma_cases_lookup
        )

scenarios = _build_scenarios(items, optimizer_view, today)
s_curve = _build_s_curve(items, today)

return {
    "kpi": kpi, "productivity": productivity_dict,
    "contractor_bars": contractor_bars, "trade_bars": trade_bars,
    "quadrant": quadrant, "wp_summary": wp_summary,
    "optimizer_view": optimizer_view, "scenarios": scenarios, "s_curve": s_curve,
}
```

### 2.4 Deterministic cold_start fallback (LLM 호출 0)

**파일**: `pipeline/agents/optimizer/view_builder.py` (신규 함수 `_build_deterministic_cold_start`)

```python
def _build_deterministic_cold_start(
    q: dict,                          # quadrant item (wp_id, perperson, perperson_unit, productivity, impact, …)
    master: dict,                     # activity_master row (daily_qty, daily_workers, unit)
    chroma_cases: list[dict],         # ChromaDB retrieve.fetch_degradation_cases (최대 3건)
    workers: int, risk_level: str, delay_days: int,
) -> dict:
    pp_today = q["perperson"]
    pp_master = master["daily_qty"] / max(master["daily_workers"], 1)
    pct = pp_today / pp_master * 100 if pp_master else 0
    unit = q["perperson_unit"] or "단위미상"
    cause = (
        "인력 분산 또는 후속 작업 의존성에 따른 페이스 저하 가능성"
        if pct < 70 else
        "동시 작업 간섭 또는 자재 대기에 따른 일시적 감소 가능성"
        if pct < 90 else ""
    )
    diagnosis = (
        f"이 작업은 보통 인당 {pp_master:.2f} {unit} 작업하는데, "
        f"오늘은 인당 {pp_today:.2f} {unit} ({pct:.1f}%) 로 작업했습니다."
        + (f" {cause}" if cause else "")
    )
    similar_cases = [
        {
            "date": c["date"],
            "description": f"{c['company']} · {c['l7_5_activity']} · "
                           f"{c['pp_then']:.2f} {unit} ({c['pct_then']:.0f}%)",
            "outcome": (
                f"{c['recovery_days']}일 후 {c['pp_recovered']:.2f} {unit} "
                f"({c['pct_recovered']:.0f}%) 회복"
            ) if c.get("recovery_days") else "미회복",
        }
        for c in chroma_cases[:3]
    ]
    recommendations: list[str] = []
    if pct < 70 and q["impact"] > 50:
        recommendations.append(f"인력 +1명 검토 (현 {workers}명 → {workers+1}명, 회복 단축 기대)")
    if delay_days > 0:
        recommendations.append("후속 작업 일정 영향 확인")
    details = [
        {"label": "위험 평가", "value": risk_level or "—"},
        {"label": "마스터 인당", "value": f"{pp_master:.2f} {unit}"},
        {"label": "오늘 인당", "value": f"{pp_today:.2f} {unit} ({pct:.1f}%)"},
        {"label": "유사 사례", "value": f"{len(chroma_cases)}건"},
        {"label": "평균 회복 일수",
         "value": (f"{sum(c.get('recovery_days') or 0 for c in chroma_cases)/max(len(chroma_cases),1):.1f}일"
                   if chroma_cases else "—")},
        {"label": "일정 영향", "value": f"+{delay_days}일"},
    ]
    return {"diagnosis": diagnosis, "similar_cases": similar_cases,
            "recommendations": recommendations, "details": details}
```

### 2.5 optimizer.retrieve 검색 key 보강

**파일**: `pipeline/agents/optimizer/retrieve.py` (line 34, 49, 73, 120 의 4 함수)

각 함수 시그니처에 `l7_5_activity: Optional[str] = None` 추가, 검색 filter:

```python
where = {"$and": [{"company": company}, {"l6_main": l6_main}]}
if l7_5_activity:
    where["$and"].append({"l7_5_activity": l7_5_activity})
results = collection.get(where=where, ...)

# fallback chain
if not results["ids"]:
    where = {"$and": [{"company": company}, {"l6_main": l6_main}]}
    results = collection.get(where=where, ...)
if not results["ids"]:
    where = {"$and": [{"l6_main": l6_main}, {"l7_5_activity": l7_5_activity}]} if l7_5_activity else None
    if where: results = collection.get(where=where, ...)
```

### 2.6 ChromaDB daily_activities 530일 backfill (신규 스크립트)

**파일**: `scripts/backfill_chroma_daily_activities.py` (신규)

```python
# 1. mapper_activities 530일 (건축+토목) iterate
# 2. _format_document(row, mode="backfill") — Phase 1 commit 9252ac7 형식
# 3. embedding (text-embedding-3-small 1536d)
# 4. ChromaDB upsert
#    - id: sha256(date|l7_5|l6|company|run_id)
#    - metadata: l7_5_activity, l6_main, company, date, today_qty, assigned_workers,
#                unit, perperson, productivity_pct, run_id="backfill_v2"
# 5. distinct (date, l7_5, l6, company) 그룹 — 27,484 row 예상
```

- 비용: $0.50 미만 (text-embedding-3-small)
- 시간: 5~10 분
- idempotent (sha256 dedup)

### 2.7 사용자 A안 형식 매핑 (확정)

| OptimizerOutput 필드 | A안 매핑 (자연어 풍부) |
|---|---|
| `diagnosis` (string) | "이 작업은 보통 인당 2.50 m³ 작업하는데, 오늘은 인당 1.70 m³ (67.3%) 로 작업했습니다. 인력 분산…" |
| `similar_cases[]` | 3 row, 자연어 ("09-15 · 남웅건설 · 1.7 m³ (67%) → 3일 후 2.2 m³ (87%) 회복") |
| `recommendations[]` | 1-2 row rule-based ("인력 +1명 검토", "후속 작업 일정 영향 확인") |
| `details[]` | 6 항목 (위험·마스터 인당·오늘 인당·유사 사례·평균 회복·일정 영향) |

→ **markup 변경 0**. 기존 `OptimizerResult.tsx` 4 슬롯 그대로 받아 렌더.

### 2.8 100% 적재된 필드만 사용 (사용자 명시 확인)

| 필드 | 데이터 소스 |
|---|---|
| today_perperson | `mapper_activities.today_qty / assigned_workers` |
| master_perperson | `activity_master.daily_qty / daily_workers` |
| WP 식별 | `mapper_activities.{l7_5_activity, l6_main, company, wa}` |
| unit | `activity_master.unit` |
| similar_cases | `optimizer_advice.degradation_cases` (있을 때) + ChromaDB retrieve (없을 때) |
| risk_level / delay_days | `forecasts` row |

- 새 데이터 시뮬레이션 0
- LLM 호출 0
- view_builder 가 적재된 필드 그대로 읽어 자연어 템플릿 합성

---

## §3 — UI 표현 단순화 + Export 정리 + Dashboard fixture swap

### 3.1 Reports WP 목록 productivity 표시

**파일**: `web/app/components/reports/WPSummaryTable.tsx:82`

```diff
- {row.display_label ?? `${row.productivity}%`}
+ {`${row.productivity.toFixed(1)}%`}
```

- markup/className 변경 0
- 예: `80.1%`

### 3.2 QuadrantScatter Tooltip 일관성

**파일**: `web/app/components/charts/QuadrantScatter.tsx:45`

```diff
- <b>{p.display_label ?? `${p.productivity}%`}</b>
+ <b>{`${p.productivity.toFixed(1)}%`}</b>
```

### 3.3 Export 탭 이름

**파일**: `web/app/components/export/ConsolidatedReportCard.tsx:20-25`

```diff
- output_manpower:     "1. 출력인원 현황",
+ output_manpower:     "1. 작업사항",
  occupation_manpower: "2. 직종별 인원현황",
  equipment:           "3. 장비현황",
  quantity:            "4. 물량",
```

### 3.4 Export 1번 탭 컬럼 정리

**파일**: `web/app/components/export/SheetTable.tsx:86-98`

`OUTPUT_MANPOWER_COLS` 에서 `early / day / overtime` 3 항목 제거.

```diff
  export const OUTPUT_MANPOWER_COLS = [
    { key: "pjt", label: "PJT" },
    { key: "zone", label: "Zone" },
    { key: "trade", label: "공종" },
    { key: "bp_code", label: "BP사", ... },
    { key: "scope", label: "Scope" },
    { key: "prev_work", label: "전일 작업사항", ... },
    { key: "today_work", label: "금일 작업사항", ... },
    { key: "next_work", label: "명일 작업사항", ... },
-   { key: "early", label: "조출", ... },
-   { key: "day", label: "주간", ... },
-   { key: "overtime", label: "연장", ... },
  ] as const;
```

### 3.5 Export ZONE 빈칸 채움 (사용자 확정 — wa prefix 추출)

**파일**: `web/app/api/mock/consolidated/route.ts`

bp_summaries 매핑 시 LEFT JOIN `mapper_activities` 추가, `split_part(ma.wa, '-', 1)` 로 ZONE fallback:

```sql
SELECT pr.report_date,
       COALESCE(NULLIF(bs.zone, ''), split_part(ma.wa, '-', 1), '—') AS zone,
       bs.trade, bs.bp_code, bs.scope, ...
FROM parser_reports pr,
     jsonb_array_elements(pr.bp_summaries) bs
LEFT JOIN mapper_activities ma ON ma.run_id = pr.run_id
                              AND ma.company = bs->>'bp_code'
                              AND ma.l6_main = bs->>'trade'
WHERE pr.is_mock = FALSE AND pr.report_date = $1
```

- DB row 갱신 0 (raw 그대로 두고 read-time 채움)
- bp_summaries.zone 이 비었을 때만 fallback

### 3.6 Dashboard fixture → 실 DB swap

**파일**: `web/app/api/mock/dashboard/route.ts` + `web/lib/fixtures.ts`

- 현재: `loadFixture("dashboard")` + `loadFixture("sites")` (JSON 직접)
- 변경: `loadReal("dashboard_performance")` + `loadReal("dashboard_impact")` 신규
- DashboardFixture type 그대로 (markup 변경 0)
- 채움:
  - `fleet_kpi.avg_productivity` = `AVG(kpi_jsonb.productivity_today)` 530일
  - `fleet_kpi.avg_delay` = `AVG(kpi_jsonb.delay_days)` 530일
  - `fleet_kpi.abnormal_total` = `COUNT(*) WHERE risk_level <> '정상'` 530일
  - `fleet_kpi.recoverable_days` = `SUM(kpi_jsonb.recovery_days)` 530일
  - `fleet_trend` (60일치) = 시계열
  - `site_sparklines` = 1 site × 30일 productivity
  - `impact.site_distribution` / `monthly_trend` = forecasts + sites 집계

### 3.7 Home loadReal 검증 (sites 정적 컬럼)

**파일**: `web/lib/fixtures.ts:120-160` (loadReal("sites_summary"))

- `sites.hours_saved / fte_saved / headcount` 컬럼이 prototype 시점 값일 가능성
- 변경: `sites` 정적 컬럼 대신 `daily_reports.kpi_jsonb` 530일 SUM 으로 즉시 계산
- PG row 안 건드림 (read-time 계산)

---

## §4 — Atomizer + Optimizer 코드 변경 (BE)

§2.2, §2.3, §2.4, §2.5, §2.6 에서 상세 정의. 추가 사항:

### 4.1 atomizer.py 변경 없음

- Phase 1 commit 9252ac7 이 이미 `_format_document` 갱신 (mode="backfill" 시 perperson 포함)
- backfill_chroma_daily_activities.py 는 그 형식 그대로 사용

### 4.2 backfill_daily_report_views_v2.py 의 _JSONB_COLS 확장

**파일**: `scripts/backfill_daily_report_views_v2.py:40-47`

```diff
  _JSONB_COLS = (
      "kpi_jsonb", "productivity_jsonb", "contractor_bars_jsonb",
      "trade_bars_jsonb", "quadrant_jsonb", "wp_summary_jsonb",
+     "optimizer_view_jsonb", "scenarios_jsonb", "s_curve_jsonb",
  )
```

`update_one` 의 SET 절 자동으로 9 컬럼 SET.

### 4.3 9-25 dry-run 게이트 (사용자 명시 요구 — 블로커)

530일 전체 적용 **전** 필수 단계:

```bash
# 1. 9-25 단일 일자만 backfill
PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_daily_report_views_v2.py --date 2025-09-25
PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_chroma_daily_activities.py --date 2025-09-25

# 2. dev server 5536 reload → /reports → 9-25 WP 클릭 → 카드 4 슬롯 시각 검토
# 3. 사용자 컨펌 (screenshot 보고) → 530일 전체 적용
# 4. 컨펌 못 받으면 4.3 deterministic 템플릿 / 권고 규칙 재조정 → 9-25 다시
```

---

## §5 — Tests + 검증 (CLAUDE.md §3 Verification Before Done 강제)

### 5.1 DB 정합화 검증

```bash
$ psql -At -c "SELECT trade, COUNT(*) FROM public.mapper_activities WHERE is_mock=FALSE GROUP BY trade ORDER BY 2 DESC"
# 기대: 건축|129248, 토목|3870 만

$ psql -At -c "SELECT t, COUNT(*) FROM (SELECT 'mapper' AS t, mapper_activities FROM backup_20260521.mapper_activities ...) sub GROUP BY t"
# 기대: snapshot 과 byte-exact 동일 (6 테이블)

$ psql -At -c "SELECT COUNT(*) FROM public.mapper_activities WHERE requires_review=TRUE AND trade IN ('건축','토목')"
# 기대: 잔존 수 보고만
```

### 5.2 wp_id 매칭률 검증

```bash
$ psql -At -c "
WITH d AS (
  SELECT pr.report_date, dr.wp_summary_jsonb, dr.optimizer_view_jsonb->'by_wp' AS by_wp
  FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) WHERE dr.is_mock=FALSE
)
SELECT pr.report_date::text,
  (SELECT COUNT(*) FILTER (WHERE d.by_wp ? (elem->>'wp_id'))
   FROM jsonb_array_elements(d.wp_summary_jsonb) elem) ||'/'||
   jsonb_array_length(d.wp_summary_jsonb) AS matched
FROM d ORDER BY pr.report_date DESC LIMIT 10
"
# 기대: 모든 일자 N/N (100%)
```

### 5.3 카드 4 슬롯 채움률 검증

```bash
$ psql -At -c "
SELECT pr.report_date::text,
  COUNT(*) FILTER (WHERE wp.value->>'diagnosis' = '' OR wp.value->>'diagnosis' = 'cold_start') ||'/'|| COUNT(*) AS cold_ratio
FROM daily_reports dr JOIN pipeline_runs pr USING (run_id),
     jsonb_each(dr.optimizer_view_jsonb->'by_wp') wp
WHERE dr.is_mock=FALSE GROUP BY pr.report_date ORDER BY 1 DESC LIMIT 10
"
# 기대: cold_start 비율 0% (deterministic fallback 보장)
```

### 5.4 UI Playwright screenshot 검증 (5 화면)

```bash
# /review     — WBS 트리에 비건축/비토목 노드 사라짐, 알림 수 ~250 미만
# /tasks      — 9-25 Parser/Mapper 카운트 ~349
# /export     — 1번 탭 "작업사항", 조출/주간/연장 컬럼 0, ZONE 채워짐, 4번 탭 "물량"
# /reports    — WP 클릭 시 카드 4 슬롯 모두 자연어 채워짐 (A안)
# /dashboard  — PG 530일 실 데이터 (fleet_trend / sparklines 동적 생성)
```

### 5.5 unit pytest

**파일**: `pipeline/tests/optimizer/test_view_builder_phase2.py` (신규)

- `test_wp_id_unified`: quadrant·wp_summary 의 wp_id 가 `_wp_id_of(wa, l6, company)` 형식
- `test_build_productivity_views_v2_returns_9_keys`: return dict 키 9개
- `test_deterministic_cold_start_diagnosis`: input `(master=2.5, today=1.7, unit="m3")` → diagnosis 텍스트에 "보통 인당 2.50 m3" + "오늘은 인당 1.70 m3 (68.0%)" 포함
- `test_retrieve_with_l7_5_activity`: ChromaDB filter 에 l7_5_activity 통과 시 다른 l7_5 row hit 0
- `test_chroma_backfill_dedup`: 같은 (date, l7_5, l6, company) 2회 atomize → ChromaDB count 변화 0
- `test_cold_start_fallback_chain`: l7_5 hit 없을 때 (company, l6) fallback, 그것도 없을 때 (l6, l7_5) fallback, 그것도 없을 때 빈 list

### 5.6 Idempotency 검증

```bash
$ python scripts/backfill_daily_report_views_v2.py --all-dates
$ psql -At -c "SELECT md5(string_agg(dr.optimizer_view_jsonb::text, '' ORDER BY pr.report_date)) FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) WHERE dr.is_mock=FALSE"
# 1회 md5 캡쳐 → 2회 실행 후 동일성 검증
# 기대: 두 md5 byte-exact 동일
```

### 5.7 보고 형식 강제 (CLAUDE.md §3.4)

```
$ <실 명령어>
<실 출력 — 원본 그대로 (수정/생략 X)>
→ <결론>
```

(b) 실 출력 빠지면 미실시로 간주.

---

## §6 — Migration 단계 + 시간 추정 + Rollback

### 6.1 구현 순서 (8 phase, ~10시간)

| Phase | 작업 | 변경 범위 | 소요 |
|---|---|---|---|
| A | 안전망 setup | snapshot SQL + rollback script | 30분 |
| B | DB 정합화 (§1) | 비건축·비토목 DELETE + parser_reports.jsonb filter | 1시간 |
| C | BE 코드 변경 (§2, §4) | view_builder + retrieve + fallback + tests | 3~4시간 |
| D | 9-25 dry-run + 사용자 컨펌 | 단일 일자 backfill + Playwright | 30분 |
| E | 530일 전체 backfill | PG 9컬럼 + ChromaDB 27,484 row | 30분 |
| F | UI textContent fix (§3.1~3.4) | WPSummaryTable / QuadrantScatter / SheetTable / ConsolidatedReportCard | 1시간 |
| G | Dashboard fixture swap (§3.6~3.7) | loadReal 신규 + dashboard route | 2시간 |
| H | 전 검증 + PR | §5 모든 검증 + commit + PR body | 1시간 |
| **합** | | | **~10시간 (1.5일)** |

### 6.2 Phase A 안전망 setup

```sql
CREATE TABLE _audit_pre_phase2 AS
SELECT 'mapper' AS t, COUNT(*) AS n FROM backup_20260521.mapper_activities UNION ALL
SELECT 'parser', COUNT(*) FROM backup_20260521.parser_activities UNION ALL
SELECT 'pipeline_runs', COUNT(*) FROM backup_20260521.pipeline_runs UNION ALL
SELECT 'parser_reports', COUNT(*) FROM backup_20260521.parser_reports UNION ALL
SELECT 'daily_reports', COUNT(*) FROM backup_20260521.daily_reports UNION ALL
SELECT 'forecasts', COUNT(*) FROM backup_20260521.forecasts;
```

### 6.3 Phase B DELETE 실행 시 schema 명시

`public.X` 명시 (절대 `backup_20260521.X` 안 들어가게).

### 6.4 Phase D dry-run 게이트 (블로커)

사용자 시각 컨펌 못 받으면 **Phase E (530일) 진행 X**.

### 6.5 Rollback 절차 (3 levels)

**L1: 단일 phase rollback**

- 각 phase atomic commit + `git revert <SHA>`

**L2: DB 완전 복원** (~10분)

```sql
TRUNCATE public.mapper_activities; INSERT INTO public.mapper_activities SELECT * FROM backup_20260521.mapper_activities;
TRUNCATE public.parser_activities; INSERT INTO public.parser_activities SELECT * FROM backup_20260521.parser_activities;
TRUNCATE public.pipeline_runs;     INSERT INTO public.pipeline_runs SELECT * FROM backup_20260521.pipeline_runs;
TRUNCATE public.parser_reports;    INSERT INTO public.parser_reports SELECT * FROM backup_20260521.parser_reports;
TRUNCATE public.daily_reports;     INSERT INTO public.daily_reports SELECT * FROM backup_20260521.daily_reports;
TRUNCATE public.forecasts;         INSERT INTO public.forecasts SELECT * FROM backup_20260521.forecasts;
```

**L3: ChromaDB rollback** — `delete(where={"run_id": "backfill_v2"})` (synthetic_v2 / 기존 row 보존)

### 6.6 Risk 정리

| Risk | 영향 | 완화 |
|---|---|---|
| DELETE 후 daily_reports.jsonb 안 옛 wp_id mismatch | 일부 일자 카드 안 보임 | Phase B 후 즉시 Phase E (전체 재 backfill) — 같은 commit 묶음 |
| ChromaDB 27,484 적재 실패 | cold_start fallback 만 → 카드 자연어 단순화 | upsert idempotent. fallback path 도 자연어 유효 |
| 사용자 9-25 컨펌 못 받음 | Phase E 차단, 일정 지연 | 4.3 템플릿 조정 후 30분 단위 iteration |
| 시연 직전 PG 장애 | 전체 시연 차단 | backup_20260521 보존. L2 rollback 10분 |
| 디자인 가드 위반 (markup 변경) | 디자이너 push back | git diff `web/app/components/**/*.tsx` 가 className/markup 0 검증 |

### 6.7 Commit 단위 (atomic, ~12 commit)

- A: 1 commit (audit snapshot scripts)
- B: 1 commit (DELETE migration SQL + 검증)
- C: 5~6 commit (view_builder wp_id / retrieve l7_5 / atomizer 보강 / fallback / tests / backfill 확장)
- D: 0 commit (9-25 dry-run, 데이터만)
- E: 1 commit (530일 backfill audit log + idempotency md5)
- F: 1 commit (UI textContent fix 4 컴포넌트 묶음)
- G: 2 commit (loadReal 신규 / route swap)
- H: 1 commit (검증 audit log + PR body)

---

## 결정 사항 요약

| 결정 | 근거 |
|---|---|
| 격리 방식 = DB row DELETE | 사용자 명시 ("DB row DELETE (깔끔함 우선)") |
| 4번 탭 이름 = "물량" | 사용자 명시 ("4번을 '물량' 으로") |
| 1번 탭 컬럼 = early/day/overtime 5 컬럼 숨김 | 사용자 명시 ("조출/주간/야간/잔업/철야 5 컬럼 전부 숨기기") |
| WP 카드 형식 = A안 (자연어 풍부, perperson 비교) | 사용자 mockup 선택 ("1번 좋다") + "5 ton/인 → 4 ton/인 + 이유" 자연어 |
| optimizer_view fallback = deterministic (LLM 호출 0) | 시연 비용 안전 + spec §8 perperson 산식 그대로 |
| 적재 데이터만 사용, 새 시뮬레이션 0 | 사용자 명시 ("스키마별 표현만 좀 더 많이 맞게 바꿔주는거지?") |
| ChromaDB 530일 27,484 row 신규 적재 | 사용자 명시 ("WP 에서 선택했을때 그 WP 에 해당하는게 애초에 크로마에 안 들어있으면 조회 안 될거잖아") |
| 9-25 dry-run 사용자 컨펌 = Phase E 블로커 | 사용자 명시 ("일괄로 때려넣기 전에 즉 스펙 문서 작성하기 전에 더미 한번 보여줘서 나랑 검토") |
| backup_20260521 무손실 = 명시적 검증 | 사용자 명시 ("백업한 거 날아가지 않게 주의") |
| Spec review subagent 스킵 | 사용자 명시 ("스코프 리뷰하는 건 돌리지마") |

---

## 다음 단계

1. spec 검토 (사용자) → 변경 요청 있으면 반영
2. `superpowers:writing-plans` 스킬로 implementation plan 생성
3. `superpowers:executing-plans` 으로 atomic commit 단위 실행
4. PR 생성 → 조형준 프로님 검토 후 main 머지
