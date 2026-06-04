# CPIA Export 통합 작업일보 정합 — 최종 적재 데이터 기준 재구성 Design

> **For agentic workers:** 이 spec 은 `superpowers:writing-plans` 로 구현 플랜화한 뒤 `superpowers:subagent-driven-development` 로 태스크별 실행한다.

**Goal:** Export(통합 작업일보) 화면이 시드일(9/13~24)에 시트1~3을 비우는 문제를 "파서 스테이지 테이블 대신 최종 적재 데이터(mapper_activities) 기준으로 시트를 조립"해 해소하고, BP사 컬럼을 업체명으로 정합하며, 시트1 작업사항 셀 포맷을 통일한다. Report 현장 생산성 12.6% 회귀는 근본원인을 문서화만 한다(코드 수정은 다음 세션).

**Architecture:** Export 단건 뷰는 두 경로가 있다 — (1) 화면: `web/app/api/mock/consolidated/route.ts` → `ConsolidatedReportCard`/`SheetTable`, (2) xlsx 다운로드: FastAPI `/export/run` → `pipeline/agents/exporter.py`. 두 경로 모두 시트1~3을 `parser_reports` jsonb 에서 읽는데, 시드일은 이 테이블이 의도적으로 비어 있다(`scripts/seed_dummy_year.py:621` 이 `[],[],[]` 적재). 시트별로 "풍부한 parser 데이터가 있으면 사용, 없으면 `mapper_activities` 에서 재구성" 하는 폴백을 양 경로에 동일 적용한다.

**Tech Stack:** Next.js 14 API Route(TypeScript, `@/lib/pg` 직접 SELECT) + Python LangGraph(`pipeline/agents/exporter.py`, asyncpg) + PostgreSQL(`43.200.85.209:5532/cpia`). 화면 컴포넌트는 vitest, 파이프라인은 pytest.

---

## 1. 배경 — 실 코드·실 DB 로 확인한 현상

### 1.1 시드일 시트1~3 이 비는 이유 (Issue 4)

시드 생성기 `scripts/seed_dummy_year.py` 의 `seed_day()` 는 파서/매퍼 스테이지를 거치지 않고 최종 적재 데이터(`mapper_activities` + `parser_activities`)만 직접 만든다. `parser_reports` 는 `insert_parser_report(run_id, d, PROJECT, [], [], [], n_active)`(L620-621) 로 `bp_summaries`/`job_allocations`/`equipment_allocations` 를 **빈 리스트**로 적재한다.

실 DB 확인 (site `m15x-ph3-ibl`):

```
$ 9/22~25 정규화/jsonb 행수
 report_date | bp(시트1) | job(시트2) | equip(시트3) | acts(시트4) | is_mock
 2025-09-22  |    0      |    0       |     0        |   172       |  f
 2025-09-23  |    0      |    0       |     0        |   172       |  f
 2025-09-24  |    0      |    0       |     0        |   171       |  f
 2025-09-25  |    7      |   88       |    136       |   115       |  f   ← 실 업로드
```

저장된 consolidated xlsx 도 동일 — 9/24 는 시트1=0행·시트2=0행·시트3=0행·시트4=171행, 9/25 는 7/88/136/115.

`/api/mock/consolidated?date=` 단건 route 는 시트1~3 을 `parser_reports` jsonb 에서, 시트4 만 `parser_activities`+`mapper_activities` JOIN 에서 읽는다(route.ts:112-242). 그래서 시드일은 시트4 만 보인다. **표시 누락이 아니라 파서 스테이지 테이블이 비어 있는 것** — 단, 최종 적재 `mapper_activities` 에는 업체별 실적이 있다.

### 1.2 최종 적재 데이터(mapper_activities)가 보유한 컬럼

9/24 mapper_activities 실측: 20개사, 171행, **전 행 `assigned_workers`(투입인원) 보유**. 시트별 재구성 가능 여부:

| 시트 | 시드일 재구성 | 근거 (mapper_activities 컬럼) |
|---|---|---|
| 1.출력인원 | ✅ | `company`(업체명)·`trade`·`wa`(zone)·`assigned_workers`(투입인원) + `parser_activities.work_content`(작업내용) |
| 4.물량 | ✅ (이미 동작) | `company`·`bp_code`·`trade`·`wa`·`unit`·`today_qty`·`yesterday_cum_qty`·`plan_total_qty` |
| 2.직종별 | ⚠️ 부분만 | 투입인원은 있으나 **직종(job_type) 컬럼 없음** |
| 3.장비 | ❌ | **장비 컬럼이 mapper_activities 에 없음** |

직종(job_type)·장비(equipment)는 실 업로드(9/25)에서만 parser 가 채운다.

### 1.3 시트1 그레인 (실측 확정)

9/25 `bp_summaries` 7행 = **업체별 1행** (광건/글로벌유명/남웅건설/동신패널/선보/장평건설/태우), `zone`·`disc_abbrev` 는 null, `bp_code` 1개/사, `today_incr_total`=업체 일일 총 투입인원. 시드 재구성 그레인도 **per-company** 로 맞춘다(9/24 → 20행). `(company, wa)`=26행은 9/25 의 zone=null 그레인과 불일치하므로 채택하지 않는다.

### 1.4 BP사 컬럼이 코드로 보이는 이유 (Issue 1/3)

화면 route 의 시트1/2/3 은 "BP사" 컬럼(label) 에 `bp_code ?? company` 로 **코드 우선** 출력(route.ts:187/201/217). 시트4 만 "BP 코드"(`bp_code`) + "BP사"(`company`) 두 컬럼으로 분리(SheetTable.tsx:130-131). xlsx `exporter.py` 시트1 도 `row.get("bp_code") or row.get("company")`(exporter.py:256). 데이터에는 `company`(예: 광건)·`bp_code`(예: PH_X-070)가 둘 다 있으나 코드가 노출된다.

### 1.5 작업사항 셀 포맷 불일치 (Issue 2)

`SheetTable.tsx` 시트1: 전일(`prev_work`)·명일(`next_work`)은 `truncate`(한 줄 + …), 금일(`today_work`)은 `whitespace-normal`(줄바꿈). 데이터는 셋 다 `\n` 으로 구분된 멀티라인 작업항목이라 전일은 한 줄로 잘리고 금일만 길게 펼쳐져 정렬이 어긋난다.

### 1.6 Report 현장 생산성 12.6% 회귀 — 근본원인 (Issue 5, 문서화만)

`현장 생산성` = `kpi.productivity_today` = `view_builder._build_productivity_views_v2` 의 `site_wv_median`. 이 함수는 두 경로:

- **PRIMARY**(view_builder.py:1714-1739): `ma.l7_5_activity IS NOT NULL` 일 때, plan 을 `(company, l6_main, l7_5_activity)` 그룹 **SUM** 으로 JOIN 하되 actual 은 **per-row(개별 mapper 행, 미집계)**.
- **FALLBACK**(:1745-1780): l7.5 NULL 일 때만, `(company, l6_main, unit)` 로 actual·plan 둘 다 SUM 집계.

l7.5 기능 **이전**엔 `parser.py:445` 가 prod run 의 `l7_5_activity=None` 하드코딩 → PRIMARY 0행 → FALLBACK(집계, ~90%). **이후**엔 mapper 가 l7.5 를 채움 → PRIMARY 활성. PRIMARY 는 actual 을 행별로 두는데 plan 분모는 l7_5 그룹 전체 SUM 이라 **grain 불일치** — 다행 그룹일수록 행 수만큼 나눠짐.

실측 (9/25, l7.5 NOT NULL·plan 매칭·건축/토목 40행, 전부 today_qty>0):

```
$ 그룹 집계 vs per-row 생산성
 group              | rows | per-row 평균 | 그룹집계
 광건 경량벽체      |  18  |   17.5%      |  314%
 동신 Glass Wool    |  15  |    3.3%      |   50%
```

가중 중앙값 = 12.6%, simple_mean = 66.1% (격차가 0근처 쏠림 증거). `git diff 84442ce..HEAD -- view_builder.py` = **빈 출력**(이번 브랜치 무변경) → 잠재 경로가 l7.5 데이터로 활성화된 것. **이번 세션은 코드 수정 없음.** 수정 방향(PRIMARY 를 l7_5 grain 으로 집계 vs FALLBACK 고정)은 다음 세션에서 실 run 으로 비교 후 결정.

---

## 2. 설계 결정

- **D1.** Export 시트1~3 은 시트별로 "풍부한 parser 데이터(`parser_reports` jsonb / 정규화 테이블)가 있으면 사용, 없으면 `mapper_activities` 에서 재구성" 하는 폴백. 9/25+ 실 업로드는 기존 parser 경로 그대로(검증됨), 시드일만 재구성 경로.
- **D2.** 시트1 재구성 그레인 = **per-company** (9/25 bp_summaries 그레인과 일치). 시드일 9/24 → 20행(실측: 9/24·9/25 mapper 는 전부 `trade IN ('건축','토목')` 라 trade 필터 적용해도 업체수 불변 — 9/24 all_trades=20=arch_civil=20).
- **D3.** 시트2(직종)/시트3(장비)는 시드일 원천이 최종 데이터에도 없음 → **시드일 빈상태** 유지(합성하지 않음). 실 업로드일만 채움.
- **D4.** 시트4(물량)는 현행 유지(이미 모든 날 동작).
- **D5.** 시트1/2/3 "BP사" 컬럼 = 업체명. route·exporter.py 4개 매핑 모두 **`company` 우선, `bp_code` 폴백**(`company ?? bp_code` / `company or bp_code`) 동일 방향으로 통일(폴백 방향 뒤집힘 주의). 컬럼 label·마크업 불변, 표시 값만 코드→업체명.
- **D6.** 시트1 전일/금일/명일 작업사항 셀 = `whitespace-pre-line` + `line-clamp-3` 로 세 컬럼 동일 처리(테스트와 정합 위해 `line-clamp-3` 고정). `\n` 보존, 높이 제한.
- **D7.** 화면(route.ts)·xlsx(exporter.py) 두 경로에 동일 폴백 로직을 미러링.
- **D8.** Report 생산성 12.6% 는 §1.6 근본원인 문서화만. 코드 변경 0.

---

## 3. 컴포넌트별 설계

### A. Export 소스 전환 — 시트1~3 (D1·D2·D3·D7)

**A-1. 화면 route `web/app/api/mock/consolidated/route.ts`**

단건 detail 에서 `bp_summaries` 가 비어 있으면(`length===0`) 시트1 을 `mapper_activities`(+ `parser_activities.work_content`) 에서 per-company 재구성한다. `job_allocations`/`equipment_allocations` 가 비면 시트2/3 은 빈 배열 유지(현행과 동일).

재구성 SQL(시드일 시트1) — `(company)` 그룹, site_id 는 pipeline_runs JOIN:

```sql
SELECT ma.company,
       MAX(ma.trade)                              AS trade,
       SUM(COALESCE(ma.assigned_workers,0))::float AS workers_total,
       string_agg(DISTINCT NULLIF(pa.work_content,''), E'\n')  AS work_today
FROM mapper_activities ma
JOIN pipeline_runs pr USING (run_id)
LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
WHERE pr.report_date = $date AND pr.site_id = 'm15x-ph3-ibl'
  AND ma.is_mock = $useMock
  AND ma.trade IN ('건축','토목')
GROUP BY ma.company
```

→ `OutputManpowerRow` 매핑: `zone`=`companyWa[company]`(기존 최빈 wa 맵 재사용), `trade`, `bp_code`=`company`(시드는 bp_code 빈값이라 `company ?? bp_code`=company, D5 동일 방향), `scope`=""(시드 무), `main_work`/`today_work`=`work_today`, `prev_work`/`next_work`=""(시드는 전일/명일 텍스트 원천 없음 → 빈값), `early`/`overtime`=0, `day`=`round(workers_total)`.

기존 9/25 경로(`bp_summaries.map(...)`)는 유지하되 D5 적용(`bp_code: s.company ?? s.bp_code`).

**A-2. xlsx `pipeline/agents/exporter.py`**

`fetch_sheet_data` 에서 `bp_rows` 가 비면 동일 per-company 재구성 쿼리로 `output_manpower` 채움(시트2/3 은 빈 유지). `_fill_output_manpower` 는 재구성 dict 키(`company`/`disc_abbrev`/`work_text_today`/`workers_today_*`)와 호환되게 매핑. NoDataError 는 4시트 모두 0건일 때만(현행 유지).

### B. BP사 = 업체명 (D5)

- route 시트1: A-1 에서 `bp_code` 필드=업체명.
- route 시트2(:201)·시트3(:217): `bp_code: j.company ?? j.bp_code` / `e.company ?? e.bp_code`.
- exporter.py 시트1(:256): `row.get("company") or row.get("bp_code")`. 시트2(:272)/시트3(:292) 동일 우선순위.
- `SheetTable.tsx` 컬럼 label "BP사" 불변(디자인 보존). 표시 값만 업체명.

### C. 작업사항 셀 포맷 통일 (D6)

`SheetTable.tsx` `OUTPUT_MANPOWER_COLS`(:92-94): `prev_work`·`today_work`·`next_work` 셋 다 `cellClass` 를 `max-w-[200px] whitespace-pre-line line-clamp-3 text-ink-mid`(금일만 `text-ink`) 로 통일. `truncate` 제거. line-clamp 은 코드베이스에 이미 사용 중(NotificationBell 등) — Tailwind 내장.

### D. Report 생산성 — 문서화만 (D8)

§1.6 가 근본원인 기록. 코드/플랜 태스크 없음. 다음 세션 진입 메모는 [[cpia_report_ssot_decision]] / [[cpia_card_source_wp_summary_dummy]] 연계.

---

## 4. 데이터 흐름

```
Export 단건 (date 지정)
  ├ parser_reports.bp_summaries 있음? ─yes→ 시트1 = bp_summaries 매핑 (BP사=company)
  │                                  └no → 시트1 = mapper_activities per-company 재구성
  ├ job_allocations 있음?            ─yes→ 시트2 = 매핑 (BP사=company)  └no→ 시트2 = []
  ├ equipment_allocations 있음?      ─yes→ 시트3 = 매핑 (BP사=company)  └no→ 시트3 = []
  └ 시트4 = parser_activities + mapper_activities JOIN (현행, 전일 모두)
```

xlsx(exporter.py) 동일 분기.

---

## 5. 테스트 전략

- **route 단위(vitest)** — 시드일(bp_summaries 빈) → 시트1 행수 = 업체수(9/24=20), `bp_code` 필드=업체명, 시트2/3=[], 시트4 그대로. 실 업로드일(9/25, bp_summaries 7) → 시트1 7행 유지 + `bp_code`=company, 시트2/3 풍부값 유지. (실 DB fixture 또는 mock rows)
- **exporter render(pytest)** — `fetch_sheet_data` 가 빈 bp_rows 일 때 per-company output_manpower 생성, `render_xlsx` 시트1 에 업체명·투입인원·작업내용 기입. 시트2/3 빈 유지. MergedCell-safe 회귀.
- **SheetTable(vitest, 가능하면)** — 시트1 작업사항 3컬럼 cellClass 에 `truncate` 없음 + `line-clamp-3` 존재(계약 고정).
- **라이브 UI 확인** — 시드일(9/24) Export: 시트1(업체명·투입인원·작업)·시트4 노출, 시트2/3 빈. 실 업로드일(9/25): 4시트 정상 + BP사=업체명, 작업사항 3컬럼 정렬 정합. (npm dev :5537, FastAPI :8000 — 코드 변경 시 uvicorn 재시작)

---

## 6. 범위 밖 / Known Issue

- **Report 현장 생산성 12.6% 코드 수정**(§1.6) — 다음 세션. 이번 spec 은 원인 문서화만.
- 시드일 시트2(직종)/시트3(장비) **합성 적재** — 채택 안 함(D3). 원천 데이터 없음.
- 9/25 `assigned_workers` 오염(mh-누계 단위, 예 동신패널 6630) — 본 작업 범위 밖(시드 재구성은 깨끗한 fractional workers 사용, 합산이 정상 headcount).

---

## 7. 제약 (불가침)

- **디자인 불가침**: layout/style/markup 변경은 C(작업사항 셀 클래스, 사용자 명시 요청)만. 그 외는 BE/route/데이터 변환. 컬럼 label·테이블 구조 불변.
- **한자 금지**: 코드/문서/주석 어디에도.
- **main 직접 푸시 금지**: 작업 브랜치(`feature/review-l75-hil` 또는 신규)에서, 머지는 사용자 확인.
- **DB**: `postgresql://cpia:***@43.200.85.209:5532/cpia`, site `m15x-ph3-ibl`. reset 은 9/25 만 삭제·시드 보존.
