# CPIA UI Data Integrity Phase 2 — Design Spec (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement the plan task-by-task. Spec scope is locked — do NOT renegotiate scope. Use `superpowers:writing-plans` next.

**작성일**: 2026-05-21
**수정**: 2026-05-21 v2 (5-reviewer 피드백 반영 — DELETE 제거, WHERE 필터 방식)
**Track**: A_Track
**기반**: Phase 1 (`2026-05-21-cpia-data-canonicalization-phase1-design.md`) 완료, PR #38 merged.
**시연 마감**: D-15 (2026-06-05)
**디자인 가드**: `web/app/components/**` markup·className 변경 0 (시연자 조형준 프로 의도 보존). textContent 만 변경 허용 — 사용자 직접 요청 부분.

---

## Goal

530일 더미 적재 후 dev server 5536 에서 발견된 6 RC 일괄 정합화. 사용자 신고:

1. Tasks 9-25 1162 건 + Review 475 알림 + WBS 트리에 비건축·비토목 공종 (전기/설비/UT/소방/제어) 활성 — 저번 세션에 건축+토목만 적재하기로 했는데 격리 안 됨
2. Reports WP 클릭 시 옆 카드 4 슬롯 (진단/유사사례/권고/상세) 모두 `cold_start` fallback
3. Reports WP 목록 productivity 표시 `4 (4 1차/일... m²)` 형식 — `80.1%` 만 원함
4. Export ZONE 67% 빈칸, "출력인원 현황" 탭 이름 + 조출/주간/연장 컬럼 숨기기, 4번 탭 "물량" 으로
5. Dashboard fixture JSON 의존 — 실 PG 데이터로 swap
6. WP 카드 자연어 형식: "보통 인당 N unit 작업하는데 오늘은 인당 M unit (P%) 로 작업했습니다 … 이유" (사용자 확정 A안)

## Architecture

```
┌─── PG public schema (AWS 43.200.85.209:5532) ────────────────────────────────┐
│                                                                              │
│  [DB 변경 없음] backup_20260521 무손실 + public row 그대로                  │
│  ├─ mapper_activities      239,344 row 보존                                 │
│  ├─ parser_activities      239,344 row 보존                                 │
│  ├─ parser_reports.jsonb   bp_summaries / job_allocations / equipment 그대로 │
│  └─ requires_review        flag 보존                                         │
│                                                                              │
│  [BACKFILL v2 확장] daily_reports.jsonb 6 → 9 컬럼                          │
│  └─ optimizer_view_jsonb / scenarios_jsonb / s_curve_jsonb 추가 갱신        │
│     (mapper SELECT 자체에 trade IN ('건축','토목') 필터 → 비건축·비토목 자동 제외) │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── BE / route WHERE 필터 (사용자 명시: backup 안 건드림 = flag 방식) ────────┐
│  모든 mock route + view_builder + transforms 의 mapper SELECT 에            │
│  WHERE ma.trade IN ('건축','토목') 추가                                     │
│  → row 보존 + BE 가 화면에 가림                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── ChromaDB daily_activities (43.200.85.209:5533) ───────────────────────────┐
│  [BACKFILL] mapper_activities 530일 (건축+토목만) → ~27,484 row upsert      │
│  - metadata: l7_5_activity / l6_main / company / date / unit / perperson    │
│  - run_id="backfill_v2" (synthetic_v2 옛 10,056 row 보존)                   │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── pipeline/agents/optimizer/ 코드 변경 ─────────────────────────────────────┐
│  view_builder._build_productivity_views_v2                                   │
│   - SELECT 에 ma.wa 추가 + WHERE ma.trade IN ('건축','토목')               │
│   - quadrant/wp_summary 의 wp_id = _wp_id_of(wa, l6, company)               │
│   - return dict 9 key (kpi/productivity/cb/tb/q/wp/ov/sc/scurve)            │
│   - by_wp 미할당 WP 마다 _build_deterministic_cold_start 자동 채움          │
│  retrieve.py 의 metadatas/documents 필터에 l7_5_activity 추가 (호출자가      │
│   사전 fetch — collection.get(where=…) 는 view_builder 호출자가 실행)        │
└──────────────────────────────────────────────────────────────────────────────┘

┌─── web/app FE 변경 (markup/className 0, textContent 만) ─────────────────────┐
│  reports/WPSummaryTable.tsx       display_label 무시 → "${productivity}%"   │
│  charts/QuadrantScatter.tsx       tooltip 일관성                            │
│  export/ConsolidatedReportCard    탭 라벨 1→"작업사항", 4→"물량" 유지       │
│  export/SheetTable                OUTPUT_MANPOWER_COLS 의 early/day/overtime │
│  api/mock/dashboard               loadFixture → loadReal("dashboard_perf")  │
│  api/mock/consolidated            site_id 하드코딩 + disc_abbrev 필터        │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

- Python 3.11 + asyncpg + Azure OpenAI text-embedding-3-small (1536d)
- ChromaDB HttpClient
- Next.js 15 App Router + TypeScript
- LangGraph + FastAPI + PostgresSaver (변경 없음)

---

## §1 — BE WHERE 필터로 비건축·비토목 격리 (DB 변경 0)

### 1.1 검증 결과

```
mapper_activities trade 분포 (530일, is_mock=FALSE):
  건축:129,248 / 전기:36,465 / 설비:33,859 / UT:14,666 /
  소방전기:8,500 / 소방설비:7,799 / 제어:4,560 / 토목:3,870 / 공통가설:377
  → ~30% (~107K row) 가 비건축·비토목 — 화면에 보이는 게 문제, row 자체는 보존

requires_review=TRUE: 462 건 모두 9-25 일자
backup_20260521 schema: 19 테이블 byte-exact 보존 — 본 작업 영향 0
```

### 1.2 WHERE 절 추가 위치 (사용자 명시: "백업 안 건드림 = flag 방식")

| 위치 | 변경 |
|---|---|
| `web/app/api/mock/agent-tasks/route.ts` | mapper / parser SELECT 에 `WHERE ma.trade IN ('건축','토목')` |
| `web/app/api/mock/review/route.ts` | mapper SELECT WHERE 추가 + wbs tree count 도 같이 |
| `web/app/api/mock/consolidated/route.ts` | parser_reports.jsonb 안 `elem->>'disc_abbrev' IN ('건축','토목')` filter + site_id 하드코딩 (`'m15x-ph3-ibl'`) |
| `pipeline/agents/optimizer/view_builder.py` | `_build_productivity_views_v2` SQL 의 mapper JOIN 에 `WHERE ma.trade IN ('건축','토목')` |
| `web/lib/transforms.ts` | `deriveStageProgress`, `wbsTreeBuild` 의 mapper 카운트 SQL |
| `web/lib/fixtures.ts` | `loadReal("sites_summary")` 의 review_pending / abnormal_count 등 |
| `scripts/backfill_chroma_daily_activities.py` | mapper SELECT WHERE (Chroma 적재 시 자동 격리) |

→ DB schema 변경 0. backup_20260521 무관. public schema row 무변경. 시연 중 "전기 보여달라" 요청 시 WHERE 절 1줄 제거하면 즉시 노출 가능 (사용자 명시 backup 우려 해결).

### 1.3 검증

```bash
# (a) WHERE 절이 모든 mock route 에 적용됐는지 grep
$ grep -nE "trade IN \('건축'" web/app/api/mock/**/route.ts pipeline/agents/optimizer/view_builder.py web/lib/transforms.ts web/lib/fixtures.ts scripts/backfill_chroma_daily_activities.py
# 기대: 7+ 곳 모두 hit

# (b) backup_20260521 row 수 무변화
$ psql -At -c "SELECT 'mapper', COUNT(*) FROM backup_20260521.mapper_activities UNION ALL SELECT 'parser', COUNT(*) FROM backup_20260521.parser_activities UNION ALL ..."
# 기대: snapshot 과 byte-exact 동일

# (c) public row 수 무변화 (DELETE 없음)
$ psql -At -c "SELECT COUNT(*) FROM public.mapper_activities WHERE is_mock = FALSE"
# 기대: 239,344 (그대로)
```

### 1.4 예상 시각 영향

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
retrieve.py 4 함수 (line 34/49/73/120): `collection.get` 안 호출. 호출자가 사전 fetch 한
  `metadatas: list[dict]` / `documents: list[str]` 받아 Python 으로 필터링.
```

### 2.2 wp_id 형식 통일 (P0 — 매칭 0/15 직접 원인)

**파일**: `pipeline/agents/optimizer/view_builder.py:1089, 1106`

- `_build_productivity_views_v2` SELECT 에 `ma.wa` 추가
- quadrant 의 `wp_id = _wp_id_of(it["wa"], it["l6_main"], it["company"])`
- wp_summary 의 `wp_id = _wp_id_of(it["wa"], it["l6_main"], it["company"])`
- → optimizer_view.by_wp keys 와 자동 매칭

### 2.3 _build_productivity_views_v2 가 9 key 반환

함수 끝 return dict 에 3 key 추가. 신규 헬퍼 4개 (`_build_optimizer_view` 외):

```python
advice_rows = await pg.fetch_all(
    "SELECT * FROM optimizer_advice WHERE run_id IN ("
    "  SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today,
)
forecast_rows = await pg.fetch_all(
    "SELECT * FROM forecasts WHERE run_id IN ("
    "  SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today,
)
master_lookup = {(r["l7_5_activity"], r["company"]): r for r in items}   # § 2.4 가 사용
chroma_cases_lookup = await _fetch_chroma_cases_lookup(items, today)     # § 2.4 가 사용
wa_lookup = _build_wa_lookup(items)
optimizer_view = _build_optimizer_view(advice_rows, forecast_rows, items, wa_lookup)

# 빈 WP 채움 (§2.4)
for q in quadrant:
    if q["wp_id"] not in optimizer_view["by_wp"]:
        optimizer_view["by_wp"][q["wp_id"]] = _build_deterministic_cold_start(
            q, master_lookup.get((q["l7_5_activity"], q["company"])),
            chroma_cases_lookup.get(q["wp_id"], []),
            workers=q["workers"], risk_level=q["risk_level"], delay_days=q["delay_days"],
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

**신규 헬퍼 schema** (Phase C 시간 추정 반영, P1-F4):

- `_build_wa_lookup(items) -> dict[(l6, company), list[wa]]` — fan-out 용
- `_fetch_chroma_cases_lookup(items, today) -> dict[wp_id, list[dict]]` — ChromaDB collection.get(where=…) 호출
- `_build_scenarios(items, optimizer_view, today) -> {"site": {…}, "by_wp": {wp_id: {…}}}` — 회복 시나리오 4개 (no_action / p25 / p50 / p75)
- `_build_s_curve(items, today) -> list[{date, planned, actual, recovery?}]` — 60일 시계열 + 마지막 actual 기준 30일 forecast

### 2.4 Deterministic cold_start fallback (LLM 호출 0, 5~7 룰 매트릭스 — 사용자 결정 P-2)

**파일**: `pipeline/agents/optimizer/view_builder.py` (신규 함수)

사용자 결정 (P-2): cause 분기를 `(productivity, impact, delay_days, trade)` 4축 매트릭스로 확장 → 8 가지 문장 골격. recommendations 룰 5개 이상.

```python
def _build_deterministic_cold_start(q, master, chroma_cases, workers, risk_level, delay_days):
    pp_today = q["perperson"]; pp_master = master["daily_qty"] / max(master["daily_workers"], 1) if master else 0
    pct = pp_today / pp_master * 100 if pp_master else 0
    unit = q["perperson_unit"] or "단위미상"
    impact = q["impact"]; trade = q["trade"]

    # 8 cause 분기 (productivity × impact × delay × trade)
    cause = _pick_cause(pct, impact, delay_days, trade)
    # → 예: "인력 분산 + 후속 양생 의존성", "동시 작업 간섭", "자재 대기",
    #       "기상 영향 (강수일)", "선행 작업 지연 파급", "장비 가용성 저하",
    #       "정상 범위 — 일시적 변동", "회복 추세 진입"

    diagnosis = _compose_diagnosis(pp_master, pp_today, pct, unit, cause)
    # 최대 140자 보장 (디자인 가드 — P1-D1). 초과 시 cause 절 trim.

    similar_cases = [
        {"date": c["date"],
         "description": f"{c['company']} · {c['l7_5_activity']} · "
                        f"{c['pp_then']:.2f} {unit} ({c['pct_then']:.0f}%)",
         "outcome": (f"{c['recovery_days']}일 후 {c['pp_recovered']:.2f} {unit} "
                     f"({c['pct_recovered']:.0f}%) 회복") if c.get("recovery_days") else "미회복"}
        for c in chroma_cases[:3]
    ]

    # 5+ rule recommendations (사용자 결정 P-2)
    recommendations = _pick_recommendations(pct, impact, delay_days, workers, trade)
    # → 룰 5개:
    # R1: pct<70 + impact>50 → "인력 +1명 검토"
    # R2: delay_days>2 → "후속 작업 일정 영향 확인"
    # R3: trade=='건축' + pct<80 → "선행 토목 인터페이스 점검"
    # R4: pct<60 + impact<30 → "장비 가용성 / 자재 수급 확인"
    # R5: 90<=pct<100 + delay_days==0 → "현 페이스 유지 — 검증 완료"
    # WP 마다 0~2개 hit

    details = [
        {"label": "위험 평가", "value": risk_level or "—"},          # P1-D2: 색 없이 텍스트만
        {"label": "마스터 인당", "value": f"{pp_master:.2f} {unit}"},
        {"label": "오늘 인당", "value": f"{pp_today:.2f} {unit} ({pct:.1f}%)"},
        {"label": "유사 사례", "value": f"{len(chroma_cases)}건"},
        {"label": "평균 회복 일수",
         "value": (f"{sum(c.get('recovery_days') or 0 for c in chroma_cases)/max(len(chroma_cases),1):.1f}일"
                   if chroma_cases else "—")},
        {"label": "일정 영향", "value": f"+{delay_days}일"},
    ]
    return {"diagnosis": diagnosis, "similar_cases": similar_cases,
            "recommendations": recommendations, "details": details,
            "source": "deterministic_cold_start"}    # § 5.3 검증 sentinel
```

### 2.5 optimizer.retrieve 검색 key 보강 (P0-F1 정정)

**파일**: `pipeline/agents/optimizer/retrieve.py:34, 49, 73, 120`

**실 함수 시그니처**: `collection.get` 안 호출. 호출자가 `metadatas: list[dict]` / `documents: list[str]` 사전 fetch.

→ 검색 책임 분리:
- **호출자 (view_builder._fetch_chroma_cases_lookup)** 가 `collection.get(where=…)` 실행
- **retrieve.py 4 함수** 는 fetched metadatas 받아 Python 필터링에 l7_5_activity 추가

```python
# retrieve.py — 각 함수 시그니처에 l7_5_activity 추가 (Optional)
def fetch_degradation_cases(metadatas, documents, company, l6_main, today, *, l7_5_activity=None, …):
    for m in metadatas:
        if m["company"] != company or m["l6_main"] != l6_main:
            continue
        if l7_5_activity and m.get("l7_5_activity") != l7_5_activity:
            continue
        …

# 호출자 (view_builder._fetch_chroma_cases_lookup) 의 ChromaDB get
where = {"$and": [{"company": company}, {"l6_main": l6_main}]}
if l7_5_activity:
    where["$and"].append({"l7_5_activity": l7_5_activity})
results = collection.get(where=where, ...)
# fallback chain
if not results["ids"]:
    where = {"$and": [{"company": company}, {"l6_main": l6_main}]}
    results = collection.get(where=where, ...)
if not results["ids"] and l7_5_activity:
    where = {"$and": [{"l6_main": l6_main}, {"l7_5_activity": l7_5_activity}]}
    results = collection.get(where=where, ...)
```

### 2.6 ChromaDB daily_activities 530일 backfill

**파일**: `scripts/backfill_chroma_daily_activities.py` (신규)

```python
# 1. mapper_activities 530일 (WHERE trade IN ('건축','토목')) iterate
# 2. _format_document(row, mode="backfill") — Phase 1 commit 9252ac7 형식
# 3. embedding (text-embedding-3-small 1536d) — asyncio.gather n=4 (rate limit 대응)
# 4. ChromaDB upsert
#    - id: sha256(date|l7_5|l6|company|run_id)
#    - metadata: l7_5_activity, l6_main, company, date, today_qty, assigned_workers,
#                unit, perperson, productivity_pct, run_id="backfill_v2"
# 5. distinct (date, l7_5, l6, company) 그룹 — ~27,484 row (실 측정)
```

- 비용: $0.50 미만 (text-embedding-3-small)
- 시간: 10~15 분 (asyncio.gather n=4, 429 retry/backoff 포함)
- idempotent (sha256 dedup, 같은 id 재upsert 시 변경 0)

### 2.7 사용자 A안 형식 매핑 (확정)

| OptimizerOutput 필드 | A안 매핑 (자연어 풍부) |
|---|---|
| `diagnosis` (string) | "이 작업은 보통 인당 2.50 m³ 작업하는데, 오늘은 인당 1.70 m³ (67.3%) 로 작업했습니다. 인력 분산 + 후속 양생 의존성…" (최대 140자) |
| `similar_cases[]` | 3 row, 자연어 ("09-15 · 남웅건설 · 1.7 m³ (67%) → 3일 후 2.2 m³ (87%) 회복") |
| `recommendations[]` | 0~2 row rule-based ("인력 +1명 검토", "후속 작업 일정 영향 확인") |
| `details[]` | 6 항목 (위험·마스터 인당·오늘 인당·유사 사례·평균 회복·일정 영향) |

→ **markup 변경 0**. 기존 `OptimizerResult.tsx` 4 슬롯 그대로 받아 렌더. risk_level 색상 className 추가 0 (사용자 결정 — 텍스트만).

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
- LLM 호출 0 (deterministic 5+ 룰 매트릭스)
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

- const 배열 항목 제거는 "markup/className 변경 0" 가드 적용 외로 명시 (사용자 직접 요청)

### 3.5 Export Consolidated route — site_id 하드코딩 + ZONE fallback + disc_abbrev 필터 (P0-F2, S-2)

**파일**: `web/app/api/mock/consolidated/route.ts`

```sql
-- (1) parser_reports.jsonb 안 disc_abbrev (실 키 이름) 으로 필터
-- (2) site_id 하드코딩 ('m15x-ph3-ibl') — 사용자 결정 P-S1: 시연 v1 single-site
-- (3) bp_summaries.zone 빈 값 fallback = split_part(ma.wa, '-', 1)
SELECT pr.report_date,
       COALESCE(NULLIF(bs->>'zone', ''), split_part(ma.wa, '-', 1), '—') AS zone,
       bs->>'disc_abbrev' AS trade, bs->>'bp_code' AS bp_code, …
FROM parser_reports pr,
     jsonb_array_elements(pr.bp_summaries) bs
LEFT JOIN mapper_activities ma
       ON ma.run_id = pr.run_id
      AND ma.company = bs->>'bp_code'
      AND ma.l6_main = bs->>'disc_abbrev'    -- 실 키 이름
WHERE pr.is_mock = FALSE
  AND pr.report_date = $1
  AND pr.site_id = 'm15x-ph3-ibl'            -- 시연 v1 single-site
  AND (bs->>'disc_abbrev') IN ('건축','토목')  -- BE 필터 (§1)
```

- DB row 갱신 0 (raw 그대로 두고 read-time 채움)
- bp_summaries.zone 이 비었을 때만 fallback
- bp_summaries 의 trade 키 이름이 `disc_abbrev` 인 점 반영 (P0-F2 정정)

### 3.6 Dashboard fixture → 실 DB swap

**파일**: `web/app/api/mock/dashboard/route.ts` + `web/lib/fixtures.ts`

- 현재: `loadFixture("dashboard")` + `loadFixture("sites")` (JSON 직접)
- 변경: `loadReal("dashboard_performance")` + `loadReal("dashboard_impact")` 신규
- DashboardFixture type 그대로 (markup 변경 0)
- 채움 (530일 daily_reports 집계):
  - `fleet_kpi.avg_productivity` = `AVG(kpi_jsonb.productivity_today)`
  - `fleet_kpi.avg_delay` = `AVG(kpi_jsonb.delay_days)`
  - `fleet_kpi.abnormal_total` = `COUNT(*) WHERE risk_level <> '정상'`
  - `fleet_kpi.recoverable_days` = `SUM(kpi_jsonb.recovery_days)`
  - `fleet_trend` (60일치) = 시계열
  - `site_sparklines` = 1 site × 30일 productivity
  - `impact.site_distribution` / `monthly_trend` = forecasts + sites 집계

**Phase G 전 spike (P1-P3)**: 작업 직전 30분 spike — `SELECT AVG(...) FROM daily_reports` 6개 KPI manual 쿼리 → fixture 값과 비교표 작성. 자릿수 / 단위 차이가 크면 표시 형식 (round / K) 조정 후 swap 진행.

### 3.7 Home loadReal 검증 (sites 정적 컬럼)

**파일**: `web/lib/fixtures.ts:120-160` (loadReal("sites_summary"))

- `sites.hours_saved / fte_saved / headcount` 컬럼이 prototype 시점 값일 가능성
- 변경: `sites` 정적 컬럼 대신 `daily_reports.kpi_jsonb` 530일 SUM 으로 즉시 계산
- PG row 안 건드림 (read-time 계산)

---

## §4 — Atomizer + Optimizer 코드 변경 (BE)

§2.2, §2.3, §2.4, §2.5, §2.6 에서 상세. 추가 사항:

### 4.1 atomizer.py 변경 없음

- Phase 1 commit 9252ac7 이 이미 `_format_document` 갱신 (mode="backfill" 시 perperson 포함)
- `backfill_chroma_daily_activities.py` 가 그 형식 그대로 사용

### 4.2 backfill_daily_report_views_v2.py 의 _JSONB_COLS 확장 + 전체 일자 backfill (C-1)

**파일**: `scripts/backfill_daily_report_views_v2.py:40-47`

```diff
  _JSONB_COLS = (
      "kpi_jsonb", "productivity_jsonb", "contractor_bars_jsonb",
      "trade_bars_jsonb", "quadrant_jsonb", "wp_summary_jsonb",
+     "optimizer_view_jsonb", "scenarios_jsonb", "s_curve_jsonb",
  )
```

**중요 (C-1)**: §1 WHERE 필터 + §2.2 wp_id 통일이 기존 daily_reports 530일 row 모두에 retroactive 적용되어야 함. `--all-dates` 옵션으로 전체 재 backfill 실행. §5.2 검증은 530일 모든 일자에 대해 100% 매칭률.

### 4.3 9-25 dry-run 게이트 (사용자 명시 요구 — 블로커)

530일 전체 적용 **전** 필수. 컨펌 체크리스트 5개 (P1-P4):

```bash
# 1. 9-25 단일 일자만 backfill
PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_daily_report_views_v2.py --date 2025-09-25
PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_chroma_daily_activities.py --date 2025-09-25

# 2. dev server 5536 reload → /reports → 9-25 WP 5개 클릭 → 카드 4 슬롯 검토
# 컨펌 5 항목:
#   (a) 4 슬롯 모두 비어있지 않음
#   (b) WP 5개의 diagnosis 문장 골격이 3가지 이상 (cause 분기 다양성)
#   (c) recommendations 가 WP 마다 다름 (0~2 rule hit)
#   (d) similar_cases 3건이 자연어로 읽힘
#   (e) "경영진 앞에서 부끄럽지 않은가" yes/no
# 3. 사용자 컨펌 → 530일 전체 적용 (Phase E)
# 4. 컨펌 못 받으면 §2.4 cause 룰 / recommendations 룰 재조정 → 9-25 다시
# 5. 3회 iteration 후에도 컨펌 못 받으면 fallback narrative 결정 (시연 시 "AI 미세 조율 중" 표현)
```

---

## §5 — Tests + 검증 (CLAUDE.md §3 Verification Before Done 강제)

### 5.1 BE WHERE 필터 검증 (§1)

```bash
# (a) WHERE 절 적용 위치 검증
$ grep -nE "trade IN \('건축'" web/app/api/mock/**/route.ts pipeline/agents/optimizer/view_builder.py web/lib/transforms.ts web/lib/fixtures.ts scripts/backfill_chroma_daily_activities.py
# 기대: 7+ 곳 모두 hit

# (b) public schema 무변화 (DB DELETE 없음)
$ psql -At -c "SELECT COUNT(*) FROM public.mapper_activities WHERE is_mock=FALSE"
# 기대: 239,344 (그대로)

# (c) backup_20260521 무변화
$ psql -At -c "SELECT 'mapper', COUNT(*) FROM backup_20260521.mapper_activities"
# 기대: 239,344 (그대로)
```

### 5.2 wp_id 매칭률 검증 (530일 모두 100%) — C-1

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
FROM d
ORDER BY pr.report_date DESC
"
# 기대: 530일 모든 일자 N/N (100%) — 단 한 일자도 mismatch 없음
```

### 5.3 카드 4 슬롯 채움률 검증 (deterministic source sentinel)

```bash
$ psql -At -c "
SELECT pr.report_date::text,
  COUNT(*) FILTER (WHERE wp.value->>'diagnosis' = '' OR wp.value->>'diagnosis' IS NULL) ||'/'|| COUNT(*) AS empty_ratio,
  COUNT(*) FILTER (WHERE wp.value->>'source' = 'deterministic_cold_start') ||'/'|| COUNT(*) AS det_ratio
FROM daily_reports dr JOIN pipeline_runs pr USING (run_id),
     jsonb_each(dr.optimizer_view_jsonb->'by_wp') wp
WHERE dr.is_mock=FALSE GROUP BY pr.report_date ORDER BY 1 DESC LIMIT 10
"
# 기대: empty_ratio 0/N (빈 카드 0), det_ratio 가 advice 없는 WP 만큼 (일자별 가변)
```

### 5.4 UI Playwright screenshot 검증 (5 화면)

```bash
# /review     — WBS 트리에 비건축·비토목 노드 사라짐, 알림 수 ~250 미만
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
- `test_deterministic_cause_8_branches`: (pct, impact, delay, trade) 4축 → 8 가지 cause 문자열 골격 hit
- `test_recommendations_5_rules`: 5 rule 매트릭스 검증
- `test_retrieve_with_l7_5_activity`: retrieve 함수에 l7_5_activity 통과 시 다른 l7_5 row hit 0
- `test_chroma_backfill_dedup`: 같은 (date, l7_5, l6, company) 2회 atomize → ChromaDB count 변화 0
- `test_cold_start_fallback_chain`: l7_5 hit 없을 때 (company, l6) fallback, 그것도 없을 때 (l6, l7_5) fallback, 그것도 없을 때 빈 list
- `test_diagnosis_length_under_140`: 모든 가능 cause × unit 조합에서 diagnosis 길이 ≤ 140

### 5.6 Idempotency 검증

```bash
$ python scripts/backfill_daily_report_views_v2.py --all-dates
$ psql -At -c "SELECT md5(string_agg(dr.optimizer_view_jsonb::text, '' ORDER BY pr.report_date)) FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) WHERE dr.is_mock=FALSE"
# 1회 md5 캡쳐 → 2회 실행 후 동일성 검증 → byte-exact 동일
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

### 6.1 구현 순서 (8 phase, ~12~15시간) — F-4 재계산

| Phase | 작업 | 변경 범위 | 소요 |
|---|---|---|---|
| A | 안전망 setup | backup_20260521 snapshot 검증 SQL + grep 가드 script | 30분 |
| B | BE WHERE 필터 (§1) | 7+ 위치에 `WHERE trade IN ('건축','토목')` 추가 | 1시간 |
| C | BE 코드 변경 (§2, §4) | view_builder + retrieve + 4 신규 헬퍼 + tests | **6~8시간** (F-4 재추정) |
| D | 9-25 dry-run + 사용자 컨펌 (5 기준) | 단일 일자 backfill + Playwright | 30분~3시간 (iteration 가능) |
| E | 530일 전체 backfill | PG 9컬럼 + ChromaDB 27,484 row (asyncio.gather n=4) | 30~45분 |
| F | UI textContent fix (§3.1~3.4) | WPSummaryTable / QuadrantScatter / SheetTable / ConsolidatedReportCard | 1시간 |
| G | Dashboard fixture swap (§3.6~3.7) | loadReal 신규 + dashboard route + spike 30분 | 2.5시간 |
| H | 전 검증 + PR | §5 모든 검증 + commit + PR body | 1시간 |
| **합** | | | **~12~15시간 (1.5~2일)** |

D-15 마감까지 충분. iteration buffer ~6일.

### 6.2 Phase A 안전망 setup

```sql
-- backup_20260521 row count snapshot (DELETE 가 없어도 sanity 위해)
CREATE TABLE _audit_pre_phase2 AS
SELECT 'mapper' AS t, COUNT(*) AS n FROM backup_20260521.mapper_activities UNION ALL
SELECT 'parser', COUNT(*) FROM backup_20260521.parser_activities UNION ALL
SELECT 'pipeline_runs', COUNT(*) FROM backup_20260521.pipeline_runs UNION ALL
SELECT 'parser_reports', COUNT(*) FROM backup_20260521.parser_reports UNION ALL
SELECT 'daily_reports', COUNT(*) FROM backup_20260521.daily_reports UNION ALL
SELECT 'forecasts', COUNT(*) FROM backup_20260521.forecasts;

-- 작업 후 동일 SQL 재실행 → snapshot 과 byte-exact 일치 검증
```

### 6.3 Phase B WHERE 절 추가 — DB row 안 건드림

DELETE 가 없으므로 schema prefix 명시 / 트랜잭션 dry-run 불필요. grep 으로 WHERE 절 적용 위치 검증만.

### 6.4 Phase D dry-run 게이트 (블로커)

§4.3 컨펌 체크리스트 5개 모두 통과해야 Phase E 진행. 3회 iteration 후에도 컨펌 못 받으면 fallback narrative 결정 (사용자 + 시연자 합의).

### 6.5 Rollback 절차 (단순화 — DB 변경이 없으니 BE/FE git revert 만)

**L1: 단일 phase rollback** — atomic commit 후 `git revert <SHA>`

**L2: daily_reports.jsonb rollback** (Phase E 만 영향)
- backup_20260521 에서 daily_reports.jsonb 9컬럼만 복사:
  ```sql
  UPDATE public.daily_reports dr SET
    kpi_jsonb = b.kpi_jsonb,
    productivity_jsonb = b.productivity_jsonb,
    contractor_bars_jsonb = b.contractor_bars_jsonb,
    trade_bars_jsonb = b.trade_bars_jsonb,
    quadrant_jsonb = b.quadrant_jsonb,
    wp_summary_jsonb = b.wp_summary_jsonb,
    optimizer_view_jsonb = b.optimizer_view_jsonb,
    scenarios_jsonb = b.scenarios_jsonb,
    s_curve_jsonb = b.s_curve_jsonb
  FROM backup_20260521.daily_reports b
  WHERE dr.run_id = b.run_id;
  ```
- ~5분, FK 위반 없음 (UPDATE 만)

**L3: ChromaDB rollback** — `delete(where={"run_id": "backfill_v2"})` (synthetic_v2 / 기존 row 보존)

### 6.6 Risk 정리

| Risk | 영향 | 완화 |
|---|---|---|
| Phase B WHERE 누락 1곳 | 일부 화면에 비건축·비토목 노출 | §5.1 grep 검증 — 7+ 위치 모두 hit 확인 |
| ChromaDB 27,484 적재 실패 | cold_start fallback 만 → 카드 자연어 단순화 | upsert idempotent. asyncio.gather n=4 + 429 retry/backoff |
| 사용자 9-25 컨펌 못 받음 | Phase E 차단, 일정 지연 | §4.3 룰 재조정 30분 단위 iteration. 3회 후 fallback narrative |
| Dashboard 530일 집계 약함 | 시연 첫인상 약화 | Phase G 직전 30분 spike, fixture 값 비교 후 표시 형식 조정 |
| diagnosis 텍스트 overflow | 카드 시각 균형 깨짐 | 최대 140자 보장 (cause 절 trim 분기), §5.5 test |
| **보안: /api/mock/* 무인증** | 내부 fleet KPI 가 tunnel 통해 노출 | **시연 v1 = single-site m15x-ph3-ibl 하드코딩 (사용자 결정 P-S1). 시연 후 후속 phase 에서 auth 도입.** |
| **보안: ChromaDB metadata company** | 협력사명 노출 (network 도달 가능 시) | **시연 환경 내부 network 만 가정. PoC 후 5533 firewall + company 해시화 검토.** |

### 6.7 Commit 단위 (atomic, ~12 commit)

- A: 1 commit (audit snapshot scripts)
- B: 1 commit (BE WHERE 필터 7+ 위치 묶음)
- C: 5~6 commit (view_builder wp_id / retrieve l7_5 / 4 신규 헬퍼 / fallback / tests / backfill 확장)
- D: 0 commit (9-25 dry-run, 데이터만)
- E: 1 commit (530일 backfill audit log + idempotency md5)
- F: 1 commit (UI textContent fix 4 컴포넌트 묶음)
- G: 2 commit (loadReal 신규 / dashboard route swap + spike 결과)
- H: 1 commit (검증 audit log + PR body)

---

## 결정 사항 요약 (v2)

| 결정 | 근거 |
|---|---|
| 격리 방식 = **BE WHERE 필터** (DB 변경 0) | 사용자 push back: "백업 안 건드린다 = 플래그 방식" (DELETE 아니라 row 보존) |
| 4번 탭 이름 = "물량" | 사용자 명시 |
| 1번 탭 컬럼 = early/day/overtime 제거 | 사용자 명시 |
| WP 카드 형식 = A안 (자연어 풍부, perperson 비교) | 사용자 mockup 선택 |
| **deterministic 룰 = cause 8 + recommendations 5 매트릭스** | P-2: 경영진 좀속 클릭 시 템플릿 발각 방지 |
| **risk_level 색상 = 텍스트만 (디자인 가드 완전 준수)** | P1-D2: OptimizerResult.tsx 색상 className 없음 검증. 사용자 결정 가드 우선. |
| **시연 보안 = single-site m15x-ph3-ibl 하드코딩** | P-S1: 시연 v1 무인증 OK, 후속 phase 에서 auth |
| Consolidated route 키 = `disc_abbrev` (실 키 이름) | P0-F2: 실 데이터 검증 |
| retrieve.py 검색 = 호출자 측 collection.get + retrieve 측 Python 필터 | P0-F1: 실 함수 시그니처 검증 |
| wp_id 통일 = 모든 530일 row 재 backfill | C-1: §5.2 100% all-days 검증 |
| Phase C 시간 추정 6~8h (3~4h 에서 재계산) | F-4: 4 신규 헬퍼 (`_build_scenarios/_build_s_curve/_build_wa_lookup/_build_deterministic_cold_start`) 반영 |
| diagnosis 최대 140자 | D-1: 카드 시각 균형 |
| dry-run 컨펌 5 기준 | P-4: product 적합성 명시 |
| Spec review subagent 스킵 | 사용자 명시 ("스코프 리뷰만 제외, 그 외 5 persona 리뷰는 돌림") |

---

## Threat Model (S-5 — 시연 v1 가정)

| 위협 | 가능성 | 완화 |
|---|---|---|
| /api/mock/* 외부 호출자가 fleet KPI 스크랩 | 시연 v1 = 내부 network 만, 낮음 | site_id 하드코딩으로 single-site 노출만. 후속 phase auth 도입 |
| ChromaDB 5533 외부 접근으로 company 메타 노출 | 시연 v1 = 내부 network 만, 낮음 | PoC 후 firewall + company 해시화 검토 |
| L2 rollback 권한 escalation | 시연자 = 운영자 동일, 낮음 | rollback SQL 은 UPDATE 만 (TRUNCATE 없음). FK 위반 위험 0 |
| 화면 record 시 회사명 / worker count 노출 | 외부 공유 시 위험, 중간 | 시연 후 외부 공유 시 회사명 alias 처리 결정 |

후속 phase 에서 다룰 보안 항목: (1) `/api/mock/*` 인증 도입, (2) PG role 분리 (`cpia_app` / `cpia_migrator`), (3) ChromaDB 5533 auth token / VPN 격리, (4) company 해시화.

---

## 다음 단계

1. spec 검토 (사용자) → 변경 요청 있으면 반영
2. `superpowers:writing-plans` 스킬로 implementation plan 생성
3. `superpowers:executing-plans` 으로 atomic commit 단위 실행
4. PR 생성 → 조형준 프로님 검토 후 main 머지
