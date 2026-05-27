# Deep Dive — reporter + exporter 서브시스템

- **Cycle**: 2026-05-19 ~ 2026-05-25 (baseline `ef7c6cd` → HEAD `1ba783f`)
- **Pair docs**: `architecture_overview.md`, `design-intent/design_intent_reporter.md`
- **본 cycle 신규**: `exporter.py` (301 LOC) + `exporter_routes.py` (47 LOC) + `consolidated_template.xlsx` — Exporter 서브시스템이 reporter 옆에 신설됨. reporter 자체는 변경 없음 (161 LOC, 안정화).
- **핵심 분리선**: reporter = LangGraph 그래프 내부 마지막 노드 (Mapper+Forecaster+Optimizer 종합 보고서 마크다운 + G8/G2 영속화). exporter = LangGraph 외부의 FastAPI 라우트로 동작 (parser_* PG jsonb → openpyxl → xlsx bytes 다운로드). 둘은 PG 만 공유하고 호출 경로는 완전히 다르다.

---

## 1. Overview

CPIA 파이프라인은 작업일보 파일 1건이 들어오면 Collector → Parser → Mapper → (HIL 1) → Atomizer → Forecaster → (Optimizer) → **Reporter** → END 로 동작한다. Reporter 는 그래프의 마지막 노드로, Mapper / Forecaster / Optimizer 가 만든 state 를 한 번에 받아 Azure gpt-5.1 로 종합 마크다운 보고서 1 종을 만들고, `daily_reports` row 를 UPSERT 한 뒤, `sites` 테이블의 G8 (`last_run_id`) + G2 (`hours_saved_cum`) 두 누적 컬럼을 갱신한다. 즉 reporter 는 "한 cycle 완주" 의 signal 역할도 겸한다.

**Exporter** 는 본 cycle 신설된 별도 서브시스템이다. LangGraph 그래프 안에는 들어가 있지 않다. 대신 FastAPI 라우트 `GET /export/run?site_id&date` 가 호출되면 — 그 시점에 parser_reports / parser_activities (Parser 가 영속화한 jsonb) 를 SELECT 해서 `SheetData` 로 모은 뒤, `consolidated_template.xlsx` 를 openpyxl 로 열어 4 시트에 cell-by-cell write 하고 xlsx bytes 를 `Response` 로 즉시 반환한다. 즉 exporter 는 "현재 시점의 모든 BP사 작업일보를 1 파일로 합쳐 PM 이 받아간다" 는 사용자 액션에 응답하는 on-demand 다운로드 경로이며, graph cycle 과 무관하게 호출 가능하다. 이 cycle 에선 FE 의 `ConsolidatedReportCard.tsx` 가 아직 sample fallback 만 다운로드하지만, 백엔드 endpoint 는 통합 테스트까지 통과 (commit `a7e2465`).

CLAUDE.md (2026-05-18) 의 "Reporter → Exporter rename" 이력 때문에 명명이 헷갈리지만 — A_Track 의 pipeline/ 안에서는 두 파일이 공존한다. `pipeline/agents/reporter.py` (그래프 노드) 는 LangGraph cycle 의 종합 보고서 생성기로 유지되고, 새로 추가된 `pipeline/agents/exporter.py` 는 통합 xlsx 다운로드 전담이다. rename backlog 는 미시행 (이슈 표 §12 참조).

---

## 2. 파일 + LOC + 책임

| 파일 | LOC | 본 cycle 변경 | 책임 |
|---|---|---|---|
| `pipeline/agents/reporter.py` | 161 | 변경 없음 (PR #19 cycle 산물 그대로) | LangGraph reporter_node 가 호출. Mapper+Forecaster+Optimizer state → Azure gpt-5.1 종합 보고서 마크다운 + `_build_summary` JSONB + `insert_daily_report` UPSERT |
| `pipeline/agents/exporter.py` | 301 | **신규** (commit `99ef43b` + `b3010df` + `38399ac`) | `fetch_sheet_data` 가 parser_reports / parser_activities jsonb SELECT → `SheetData` → `render_xlsx` 가 openpyxl 로 4 시트 채워 bytes 반환 |
| `pipeline/agents/exporter_templates/consolidated_template.xlsx` | (binary) | **신규** (commit `99ef43b`) | 4 시트 headerrow (r3+r4) dummy + r5 부터 빈 data row. openpyxl 이 본 파일을 load 한 뒤 r5 부터 cell 채움 |
| `pipeline/agents/exporter_templates/__init__.py` | 1 | 신규 | 패키지 marker (empty) |
| `pipeline/exporter_routes.py` | 47 | **신규** (commit `a7e2465`) | FastAPI `APIRouter(prefix="/export")` 정의. `GET /run?site_id&date` → fetch_sheet_data → render_xlsx → Response (Content-Disposition 한글 파일명 raw_headers 패치 포함) |
| `pipeline/api.py:31, 203` | (참조) | **변경** (commit `4b8a955`) | lifespan-mounted FastAPI 의 `app.include_router(exporter_router)` 1 줄 추가 |
| `docs/collector-exporter-ui-swap.md` | — | 신규 (commit `56bcaee`) | B_Track UI swap 가이드 — `NEXT_PUBLIC_FASTAPI_BASE` env 와 `handleExport` 교체 코드 |
| `pipeline/graph.py:444-490` | (참조) | 이전 cycle 산물 | `reporter_node` — `report()` 호출 + G8/G2 + pipeline_runs.status='completed' 갱신 (cycle 7차 발견 fix) |
| `pipeline/db.py:405-456` | (참조) | 이전 cycle 산물 | `insert_daily_report` — UPDATE-first 패턴 (Optimizer view_builder 가 먼저 row 만든 경우 UniqueViolation 회피) |
| `pipeline/db.py:1109-1141` | (참조) | 이전 cycle 산물 | `update_site_last_run` (G8) + `update_site_hours_saved_cum` (G2) + 상수 `AS_IS_MIN=120` / `TO_BE_MIN=5` |

**3 파일 합계 (reporter + exporter + routes)**: 509 LOC. 본 cycle 신규는 348 LOC (exporter + routes + template marker), 기존 reporter 는 변경 없음.

---

## 3. reporter.py 흐름 — 그래프 마지막 노드

### 3.1 진입점 `reporter_node` (`pipeline/graph.py:444-490`)

reporter_node 는 graph 의 conditional edge 양쪽에서 합류한다.

```
hil_2 ─┬─ (hil_2_selection 비어있음)        ─┐
       │   = Optimizer skip path             │
       │                                     ├─→ reporter ─→ END
       └─ (hil_2_selection 있음) → optimizer ─┘
           = Optimizer 호출 path
```

(graph.py:521-527 의 `add_conditional_edges("hil_2", lambda s: "optimizer" if s.get("hil_2_selection") else "reporter", ...)` + `add_edge("optimizer", "reporter")` + `add_edge("reporter", END)`)

reporter_node 함수의 실제 흐름:

1. `run_id` 와 `today` 를 state 에서 꺼내 UUID / date 변환 (graph.py:450-451).
2. `report(mapped, forecast_rows, optimizer_advice, run_id, today, cfg)` 호출 — 이게 reporter.py 의 공개 함수 (3.2 참조).
3. **G8/G2 영속화 블록** (graph.py:461-488):
   - 별 PGClient 인스턴스 생성 (`PGClient(cfg.mapper.postgres_url)` — reporter 가 자체 PG client 가 없어 mapper 의 URL 재사용).
   - `state.get("site_id")` 가 None 이면 `pipeline_runs` 에서 직접 `SELECT site_id WHERE run_id=$1` 으로 fallback fetch.
   - `update_site_last_run` → `sites.last_run_id = run_id` (db.py:1109-1117).
   - `update_site_hours_saved_cum(atomized_count=len(state.get("atomized_ids", []) or []))` → `sites.hours_saved_cum += delta_h` (db.py:1125-1141).
   - `pipeline_runs SET status='completed', completed_at=NOW() WHERE run_id=$1` (graph.py:482-486) — 2026-05-20 fix (cycle 7차 발견: reporter 도달 후에도 status='running' 으로 남던 버그).
4. return `{"report_md": report_md, "current_node": "reporter", "status": "completed"}`.

### 3.2 `report()` 공개 함수 (`pipeline/agents/reporter.py:115-161`)

reporter 의 단일 공개 API. 6 인자 (mapped + forecast_rows + optimizer_advice + run_id + today + cfg) 받아 `(report_md, summary)` tuple 반환.

```
mapped empty? ─yes→ ("# 보고서 생성 실패\n매핑 데이터 없음.", {})  + PG INSERT skip (FK violation 방지)
              │
              no
              ↓
AzureOpenAI client (timeout=60s, max_retries=3) 생성
              ↓
_build_llm_input(mapped, forecast_rows, optimizer_advice, today) → 4 키 dict
              ↓
chat.completions.create(model=cfg.llm_model, messages=[SYSTEM_PROMPT, user_json])
              ↓
report_md = response.choices[0].message.content  (None 시 "# 보고서 생성 실패\nLLM 빈 응답." fallback)
              ↓
summary = _build_summary(mapped, forecast_rows, optimizer_advice)  → 4 키 dict (운영 감사용)
              ↓
PGClient.connect() → insert_daily_report(run_id, report_date, report_md, history_csv_row=summary, bp_name=None) → close()
              ↓
return (report_md, summary)
```

**SYSTEM_PROMPT 의도** (`reporter.py:25-49`):
- 3 부 마크다운 구조 고정: "1부 작업 통합" (mapped 합산, trade/BP사별 인원·물량) / "2부 생산성 진단" (forecast row 별 risk_level + reasoning) / "3부 PM 선택 공종 권고" (optimizer_advice 비어있으면 전체 생략).
- 한자 금지 + HTML 금지 + 들여쓰기 최대 2단계 + assessment=None (cold_start) 경우 "데이터 부족 — 판단 보류" 그대로 유지 룰 명시.

**`_build_llm_input`** (`reporter.py:62-86`): 4 top-level key — `date` (isoformat) + `activities` (mapped 의 7 필드만 추출: company/trade/l6_main/unit/today_qty/assigned_workers/work_content) + `forecast` (forecast_rows pass-through) + `optimizer_advice` (pass-through). LLM 무관 노이즈 (mapping_conf, wbs_activity_id 등) 제거.

**`_build_summary`** (`reporter.py:88-112`): 결정성 컬럼. LLM 비결정성과 분리. 4 키:
- `total_workers`: 전 row `assigned_workers` 합 (BP사 총 인원).
- `total_qty_by_trade`: `{trade: today_qty 합}` (공종별 일일 물량).
- `risk_counts`: `{"정상": N, "주의": N, "이상": N}` — Forecaster risk_level 분포.
- `advice_count`: Optimizer advice row 수 (= 0 이면 reporter 3 부 생략).

---

## 4. 종합 보고서 schema — `daily_reports` row 컬럼별

`daily_reports` 테이블 (init.sql:33-41) 은 reporter 와 Optimizer 의 view_builder 가 공동 작성한다. 두 agent 가 같은 row 를 UPSERT 하기 때문에 책임 분리가 중요하다.

| 컬럼 | 타입 | 누가 채우는가 | 의미 |
|---|---|---|---|
| `id` | BIGSERIAL PK | PG default | row PK |
| `run_id` | UUID FK → pipeline_runs | reporter (or optimizer 가 먼저 INSERT 시) | cycle 식별자 |
| `report_date` | DATE NOT NULL | reporter (or optimizer) | 작업일자 |
| `bp_name` | TEXT (nullable) | reporter 가 `None` 박음 | BP사명 — 종합 보고서는 BP사 단위 없음. nullable 활용 |
| `report_md` | TEXT NOT NULL | **reporter 만** (`UPDATE … SET report_md=$5`) | Azure gpt-5.1 종합 마크다운 보고서 (3 부 구조) |
| `history_csv_row` | JSONB | **reporter 만** (`_build_summary` 결과) | 4 키 운영 summary (total_workers, total_qty_by_trade, risk_counts, advice_count) |
| `kpi_jsonb` | JSONB | optimizer view_builder | Dashboard KPI 카드 데이터 |
| `contractor_bars_jsonb` | JSONB | optimizer view_builder | 협력사별 막대 차트 |
| `trade_bars_jsonb` | JSONB | optimizer view_builder | 공종별 막대 차트 |
| `quadrant_jsonb` | JSONB | optimizer view_builder | 4분면 risk×productivity 산점 |
| `wp_summary_jsonb` | JSONB | optimizer view_builder | WP 단위 요약 |
| `s_curve_jsonb` | JSONB | optimizer view_builder | S-curve 그래프 데이터 |
| `optimizer_view_jsonb` | JSONB | optimizer view_builder | Optimizer 권고 view |
| `productivity_jsonb` | JSONB | optimizer view_builder | 생산성 추이 |
| `scenarios_jsonb` | JSONB | optimizer view_builder | 시나리오 비교 |
| `created_at` | TIMESTAMPTZ | PG default | row 생성 시각 |

→ **reporter 책임 = `report_md` + `history_csv_row` (+ bp_name=NULL) 두 컬럼.** 나머지 9 jsonb 컬럼은 모두 optimizer 의 `_VIEW_JSONB_COLS` 화이트리스트 (db.py:1050-1060) 가 `upsert_daily_report_view_col` 로 분리 UPSERT.

**UPDATE-first 패턴** (db.py:430-456): 두 agent 가 같은 (run_id, site_id, report_date) row 를 작성하는데 어느 쪽이 먼저 도착할지 모르므로, `insert_daily_report` 는 UPDATE 시도 → row 없음 ("UPDATE 0") 이면 그제서야 INSERT. `upsert_daily_report_view_col` 도 동일 패턴. 이는 partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL` 가 ON CONFLICT 와 안정 매칭이 안 되는 경우의 우회.

**postgres.md drift #N3**: spec 은 컬럼명 `summary` 인데 실제 init.sql 은 `history_csv_row`. JSONB 의미 동일하지만 schema migration 미시행 — backlog 잔존.

---

## 5. G8 / G2 — `sites` 테이블 누적 컬럼

reporter_node 가 한 cycle 완주 신호로 갱신하는 두 누적 컬럼. 둘 다 init.sql 의 `sites` 테이블 (init.sql:141-155 + 2026-05-19 migration).

### 5.1 G8 — `sites.last_run_id`

```sql
UPDATE sites SET last_run_id = $1, updated_at = now() WHERE site_id = $2
```

(db.py:1109-1117). reporter_node graph.py:473 에서 호출. FE Dashboard 의 "최근 cycle" / "마지막 분석 일자" 카드가 본 컬럼을 통해 forecasts / optimizer_advice 의 최신 run 을 찾는 anchor 가 된다. 본 cycle 추가 전엔 항상 NULL → FE 카드 빈 상태.

### 5.2 G2 — `sites.hours_saved_cum`

```sql
UPDATE sites SET hours_saved_cum = hours_saved_cum + $1, updated_at = now() WHERE site_id = $2
```

(db.py:1125-1141). 산식:

```python
AS_IS_MIN = 120  # 일보당 사람 수작업 분
TO_BE_MIN = 5    # 일보당 AI 처리 분
delta_h = (AS_IS_MIN - TO_BE_MIN) / 60.0 * atomized_count
```

= `(120 - 5) / 60 * atomized_count` = `1.9167 h * atomized_count`.

**atomized_count source**: `len(state.get("atomized_ids", []) or [])` (graph.py:477). atomizer_node 가 `return {"atomized_ids": [...], "current_node": "atomizer"}` 로 적재한 ID 리스트의 길이. 즉 본 cycle 에서 Chroma `daily_activities` 에 신규 임베딩된 activity 수 = AI 가 처리한 "원시 작업 단위" 수.

마이그레이션: `infra/postgres/migrations/2026-05-19_sites_hours_saved_cum.sql` — `ADD COLUMN IF NOT EXISTS hours_saved_cum NUMERIC DEFAULT 0 NOT NULL`. 단위 = 시간 (h). FE 의 `/api/dashboard/impact` (api.py:643-655) 가 SELECT 해서 카드에 표시.

**검증** (2026-05-19 raw audit): run_id=627e2c4d, atomized_count=4 → delta=7.67h.

**Suspected related issue** (drift backlog): atomizer skip 분기 (Mock fixture path 등) 에선 `state["atomized_ids"]` 가 set 안 됨. `len(None or [])` = 0 으로 silent 0 누적 → 경고 없음. 검증 부재.

---

## 6. exporter.py 흐름 — xlsx 생성 전담

exporter 는 reporter 와 완전히 별개의 호출 경로다. LangGraph 안에 들어가지 않고 FastAPI 라우트가 호출한다.

### 6.1 진입 — `render_xlsx(sheet_data, report_date, project) -> bytes` (exporter.py:290-301)

```python
def render_xlsx(sheet_data: SheetData, report_date: _date, project: str) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"template not found: {TEMPLATE_PATH}")
    wb = load_workbook(TEMPLATE_PATH)
    _fill_output_manpower(wb["1.출력인원 현황"], sheet_data.output_manpower, report_date)
    _fill_occupation(    wb["2.직종별 인원현황"], sheet_data.occupation_manpower, report_date)
    _fill_equipment(     wb["3.장비현황"], sheet_data.equipment, report_date)
    _fill_quantity(      wb["4.물량"], sheet_data.quantity, report_date)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

흐름은 단순하다:

1. `TEMPLATE_PATH = Path(__file__).parent / "exporter_templates" / "consolidated_template.xlsx"` (exporter.py:106) — openpyxl 로 load.
2. wb 의 4 시트를 sheet 이름으로 직접 access. 시트 이름은 한글 고정 ("1.출력인원 현황" / "2.직종별 인원현황" / "3.장비현황" / "4.물량").
3. 각 시트마다 전용 `_fill_*` 함수 호출. `DATA_START_ROW = 5` (exporter.py:107) — r1~r4 는 template 헤더, r5 부터 데이터.
4. `BytesIO` 에 save → bytes 반환. 파일시스템 write X — 모두 메모리 buffer.

### 6.2 `consolidated_template.xlsx` 의 역할

본 cycle commit `99ef43b` 로 추가된 binary 파일. **헤더 (r1~r4) 만 보존하는 dummy template**. 실제 데이터 row (r5+) 는 비어있고, `_fill_*` 함수가 cell-by-cell 로 채운다. 의도:

- xlsx 의 시트 이름, merged cell, column width, font, border 등 visual styling 은 모두 template 에 박혀있어 코드가 손댈 필요 없음.
- 본문 데이터만 동적으로 채움 — openpyxl 이 cell.value 만 write 하면 styling 은 row 5+ 의 빈 cell style 이 적용되며 시각적 일관성 보존.
- **시연자 디자인 불가침** (memory: feedback_no_design_change) 원칙과 정합 — markup / styling 코드가 만지지 않는다.

### 6.3 COL_* dict — 1-indexed 컬럼 매핑 사전

각 시트별 column 번호 (openpyxl 의 1-indexed) 를 의미 키워드로 매핑한 dict 4개 (`COL_OUTPUT_MANPOWER` / `COL_OCCUPATION` / `COL_EQUIPMENT` / `COL_QUANTITY`).

```python
COL_OUTPUT_MANPOWER = {
    "project": 2, "zone": 3, "trade": 4, "bp_code": 5, "scope": 6,
    "work_y": 7, "work_t": 8, "work_n": 9,
    "yest_incr": 10, "yest_cum": 17, "today_incr": 24, "today_cum": 31,
}
```

핵심: **placeholder 가 아니라 실 sample 파일 (`docs/sample/통합작업일보_M15X*.xlsx`) 의 r3+r4+r5 헤더를 openpyxl 로 덤프해서 직접 추출한 컬럼 번호**. 시트1 의 경우 r3 = 대분류 라벨 ("BP사", "전일incr", "금일cum"), r4 = 세분류 라벨 ("협력업체", "조출/주간/연장/야간/철야/Total"), 그리고 r5 부터 데이터 시작. 시트1 의 timeshift 블록 (조출/주간/연장/야간/철야/Total) 은 6 cell 연속이라서 `yest_incr=10` 시작 → cell 10~15 가 6 timeshift + cell 16 이 final cum 자리. 이래서 `yest_cum=17` 로 7 cell 점프.

### 6.4 `_fill_timeshift(ws, row, col_start, ts)` 헬퍼 (exporter.py:193-198)

```python
def _fill_timeshift(ws, row: int, col_start: int, ts: dict | None) -> None:
    if not ts: return
    for i, key in enumerate(["morning", "daytime", "overtime", "night", "all_night", "total"]):
        ws.cell(row=row, column=col_start + i, value=ts.get(key, 0))
```

6 연속 cell 채우기. parser 단계에서 `workers_yesterday_incr` 같은 필드가 timeshift dict `{"morning": N, "daytime": N, ...}` 일 때 6 cell 일괄 write. dict 아니면 skip.

---

## 7. 4 시트 각각의 의미

### 7.1 시트1 — `1.출력인원 현황` (BP사별 인원/작업 요지)

**소스**: `parser_reports.bp_summaries` JSONB (5.18 마이그레이션의 `jsonb`).

```sql
SELECT jsonb_array_elements(pt.bp_summaries) AS row
FROM parser_reports pt
JOIN pipeline_runs pr USING (run_id)
WHERE pr.site_id = $1 AND pt.report_date = $2
```

(exporter.py:44-53). **site_id 컬럼이 parser_reports 에 없어서 pipeline_runs 와 JOIN 필수** — 한 site 의 같은 날짜에 여러 run (BP사별 작업일보 다건 처리) 이 있으면 모든 run 의 jsonb element 가 합집합 (Spec §7.1).

**`_fill_output_manpower`** (exporter.py:201-217): r5 부터 row 별로:
- zone / disc_abbrev (trade) / bp_code 또는 company / scope.
- `work_text_yesterday/today/tomorrow` 세 텍스트 셀 — 작업 요지.
- 4 timeshift 블록: `workers_yesterday_incr` (col 10~) / `workers_yesterday_cum` (col 17~) / `workers_today_incr` (col 24~) / `workers_today_cum` (col 31~). 각 블록 = 6 cell (morning/daytime/overtime/night/all_night/total).

**의도**: 시트1 의 col 5 는 r3 라벨="BP사" / r4 라벨="협력업체" 인데 같은 칸 (single cell, dual-meaning). 코드는 `bp_code or company` 둘 중 하나만 박는다 (exporter.py:209).

### 7.2 시트2 — `2.직종별 인원현황` (직종 grain 인원)

**소스**: `parser_reports.job_allocations` JSONB.

**`_fill_occupation`** (exporter.py:220-239): trade / bp_code / manager_code / worker_code / job_type 5 필드 + 3 timeshift 블록 (yest_cum / today_incr / today_cum). 단, scalar fallback 패턴이 있다 — parser 단계에서 timeshift dict 가 없으면 `workers_cum_t` scalar 값을 yest_cum 블록의 "total" 자리 (col_start + 5) 에만 박음 (exporter.py:235).

### 7.3 시트3 — `3.장비현황` (장비 grain)

**소스**: `parser_reports.equipment_allocations` JSONB.

**`_fill_equipment`** (exporter.py:242-259): trade / bp_code / equipment_big / equipment_mid / equipment_spec 5 필드 (장비 3단 분류) + 3 timeshift 블록 (count_yesterday_cum / count_today_incr / count_today_cum, scalar fallback = `count_cum_t`). 시트2와 동일 패턴이지만 "인원" 대신 "대수 (count)".

### 7.4 시트4 — `4.물량` (Activity 별 물량 진척)

**소스**: `parser_activities` 테이블 raw row (jsonb 아닌 정규화 컬럼).

```sql
SELECT pa.*
FROM parser_activities pa
JOIN pipeline_runs pr USING (run_id)
WHERE pr.site_id = $1 AND pa.report_date = $2
ORDER BY pa.run_id, pa.idx
```

(exporter.py:74-84).

**`_fill_quantity`** (exporter.py:262-287): zone / trade / bp_code / company / scope / work_content (rep_work) / unit. 그리고 **물량 산식**:

```
A = plan_total_qty       (총물량)
B = yesterday_cum_qty    (전일누적)
C = today_qty            (금일실적)
D = B + C                (금일누적)        col 13
F% = D / A * 100         (진척률)         col 14
E = A - D                (잔여)            col 15
G% = 100 - F%            (잔여율)         col 16
```

D / F / E / G 는 `b, c, a` 가 None 아니면 계산 후 write (exporter.py:280-286). a 가 0 또는 None 이면 F/E/G skip (ZeroDivision 방지).

### 7.5 NoDataError 처리 (exporter.py:16-17, 86-87)

4 SELECT 결과가 전부 비어있으면 `NoDataError(f"해당 ({site_id}, {report_date.isoformat()}) 데이터 없음")` raise. `_coerce` (exporter.py:28-31) 는 asyncpg jsonb codec 미등록 시 jsonb 가 str 로 떨어지는 케이스를 흡수하는 fallback.

---

## 8. exporter_routes.py — `/export/run` FastAPI 엔드포인트

```python
@router.get("/run")
async def export_consolidated(site_id: str, date: str) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        site = await fetch_site_by_id(pg, site_id)
        if not site:
            raise HTTPException(404, f"site_id={site_id} 없음")
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError as e:
            raise HTTPException(400, str(e))
    finally:
        await pg.close()

    xlsx_bytes = render_xlsx(data, report_date, project=site.get("name") or "CPIA")
    filename = f"통합작업일보_{date}.xlsx"
    resp = Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    cd_value = f'attachment; filename="{filename}"'.encode("utf-8")
    resp.raw_headers.append((b"content-disposition", cd_value))
    return resp
```

### 8.1 request 계약

- `GET /export/run?site_id=<text>&date=<YYYY-MM-DD>` — site_id 와 date 둘 다 query param.
- date 파싱 실패 → `HTTPException(400)`.
- `fetch_site_by_id` (db.py:1220-1229) 가 None → `HTTPException(404)`.
- `fetch_sheet_data` 가 `NoDataError` → `HTTPException(400)` (400 인 이유: validation 성 — 해당 date 에 parser_* 결과가 없으면 client 가 잘못된 date 를 줬다고 본다).

### 8.2 PG connection 수명

`/export/run` 핸들러가 직접 `PGClient(os.environ["POSTGRES_URL"])` 생성 → connect → finally close. **lifespan-managed pool (`app.state.pg`) 을 안 쓴다**. 이유는 컨텍스트상 명시되지 않지만 — exporter_routes 가 다른 endpoint 와 달리 app state 의존성을 회피해서 단독 테스트 가능성을 우선한 듯 보임 (suspected, 검증 안 됨). microoptimization 후보로 lifespan pool 재사용 (R-N7 카드 동등 issue) 이 backlog.

### 8.3 한글 파일명 인코딩 우회 (exporter_routes.py:38-46)

```python
filename = f"통합작업일보_{date}.xlsx"
# Content-Disposition 한글 파일명 → starlette Response(headers=...) 는 기본 latin-1 인코딩이라 실패.
# raw_headers 에 UTF-8 바이트로 직접 주입.
resp = Response(content=xlsx_bytes, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
cd_value = f'attachment; filename="{filename}"'.encode("utf-8")
resp.raw_headers.append((b"content-disposition", cd_value))
```

Starlette `Response(headers={...})` 경로는 latin-1 강제라 한글 파일명에서 `UnicodeEncodeError`. 대신 `raw_headers` (list[tuple[bytes, bytes]]) 에 UTF-8 인코딩한 bytes 를 직접 append → RFC 6266 호환 클라이언트가 UTF-8 로 디코딩. 브라우저 다운로드 시 "통합작업일보_2025-09-25.xlsx" 로 그대로 저장됨.

### 8.4 응답 형태 — `Response` (BytesIO 우회)

`FileResponse` / `StreamingResponse` 가 아닌 단순 `Response(content=xlsx_bytes)`. 이유는 `render_xlsx` 가 이미 BytesIO → bytes 변환을 끝낸 상태이므로 streaming 무의미. 작은 xlsx (수십 KB ~ 수 MB) 라 메모리 부담 없음.

---

## 9. FE 가 어디서 호출 — `ConsolidatedReportCard.tsx`

위치: `web/app/components/export/ConsolidatedReportCard.tsx:38-59` 의 `handleExport`.

### 9.1 현재 상태 (본 cycle 시점)

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중… (${report.date} 통합 작업일보 생성)`);
  try {
    await new Promise((r) => setTimeout(r, 1500));
    const a = document.createElement("a");
    a.href = "/sample/cpia-consolidated-report.xlsx";   // ← 정적 sample fallback
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`통합 작업일보 다운로드 완료 (${report.date})`, { id });
  } catch {
    toast.error("Exporter 실행에 실패했습니다.", { id });
  } finally {
    setBusy(false);
  }
};
```

코드 주석 (line 33-37) 에 명시: "PoC: Exporter 에이전트 호출은 A_Track 구현 대기. 시연 fallback — 약 1.5초 로딩 토스트 후 docs/sample 의 통합 작업일보 그대로 다운로드. 추후 A_Track FastAPI POST /export/run?date= 가 준비되면 a.href 를 그 응답 URL 로 swap."

→ **A_Track endpoint 는 본 cycle 에 준비 완료, B_Track FE swap 은 미실행** (cross-track PR 분리 원칙).

### 9.2 미래 상태 (UI swap 가이드 명시, `docs/collector-exporter-ui-swap.md`)

```typescript
const handleExport = async () => {
  if (busy) return;
  setBusy(true);
  const id = toast.loading(`Exporter 에이전트 작동 중…`);
  try {
    const siteId = process.env.NEXT_PUBLIC_DEFAULT_SITE_ID || "m15x-ph3-ibl";
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_FASTAPI_BASE}/export/run?site_id=${siteId}&date=${report.date}`,
    );
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `통합작업일보_${report.date}.xlsx`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success(`통합 작업일보 다운로드 완료`, { id });
  } catch (e) {
    toast.error(`Exporter 실행 실패: ${(e as Error).message}`, { id });
  } finally {
    setBusy(false);
  }
};
```

### 9.3 env 추가 사항

`.env.local.example` 에:
```
NEXT_PUBLIC_FASTAPI_BASE=http://localhost:8000
NEXT_PUBLIC_DEFAULT_SITE_ID=m15x-ph3-ibl
```

CORS / 인증 통일이 필요해지면 Next.js BFF 경로 (`web/app/api/export/[date]/route.ts`) 를 신설해 FastAPI fetch 후 stream pipe 하는 대안 제시 (가이드 문서 §"BFF proxy 대안"). PoC 에선 직접 fetch 도 충분.

### 9.4 디자인 불가침 보장

UI swap 가이드의 마지막 절: "본 swap 은 `handleExport` 내부 로직만 교체. 컴포넌트의 markup / className / Tailwind 클래스 / Toaster 인터페이스는 그대로 유지. 시연자 의도 보존." → memory: `feedback_no_design_change` 와 정합.

---

## 10. FastAPI lifespan integration

### 10.1 마운팅 1 라인 (commit `4b8a955`)

`pipeline/api.py:31, 203`:

```python
from pipeline.exporter_routes import router as exporter_router
...
app = FastAPI(title="CPIA Pipeline API", version="0.1.0", lifespan=lifespan)
app.include_router(exporter_router)
```

`exporter_router` 는 `APIRouter(prefix="/export", tags=["export"])` 로 정의됐으므로 최종 endpoint = `GET /export/run`. OpenAPI 의 `tags=["export"]` 로 swagger UI 에서 별 그룹으로 표시.

### 10.2 lifespan 과의 관계

`lifespan` (api.py:147-195) 은 PG pool (`app.state.pg`) + LangGraph compiled graph (`app.state.graph`) + GraphConfig (`app.state.cfg`) + 선택적 Collector IMAP IDLE task 를 셋업한다. 그러나 — **exporter_routes 는 이 셋 중 어느 것도 안 쓴다.** `exporter_routes.py:23-24` 가 `PGClient(os.environ["POSTGRES_URL"])` 로 자체 connection 을 생성. 즉 exporter 는 lifespan 의 의존성에서 자유로워 단독 호출 가능.

**의의**: exporter 는 graph cycle (`graph.ainvoke` / `Command(resume)`) 과 무관한 read-only 경로. lifespan 이 셋업한 graph 인스턴스를 안 건드리므로, exporter 호출이 진행 중인 graph cycle 의 상태에 영향을 미치지 않는다. 또한 `POSTGRES_URL` 환경 변수 미설정 시 lifespan 자체가 RuntimeError 로 부팅을 막으므로, exporter 가 호출되는 시점에는 항상 env 가 존재 — `os.environ["POSTGRES_URL"]` 의 KeyError 위험 없음.

### 10.3 RouterMounting 이 lifespan 보다 먼저 실행되는 이유

`include_router` 는 FastAPI app 객체 정의 직후 (api.py:203) 호출. lifespan 은 첫 request 가 오기 직전에 실행되므로 router 등록이 더 빠르다. 따라서 `/export/run` 은 lifespan 이 마치는 시점에는 이미 등록된 상태.

---

## 11. 데이터 흐름 통합 표 — reporter vs exporter 분리

| 항목 | reporter | exporter |
|---|---|---|
| 호출 trigger | LangGraph cycle 종결 (`reporter_node`) | FE 사용자가 "Export 엑셀" 버튼 클릭 → `GET /export/run` |
| 호출 경로 | in-process (graph.ainvoke) | HTTP (FastAPI router) |
| 입력 source | LangGraph state (mapped / forecast / optimizer_advice + run_id + date) | PG SELECT (parser_reports jsonb 3 + parser_activities row) |
| 출력 sink | PG `daily_reports` UPSERT + `sites.last_run_id/hours_saved_cum` UPDATE + `pipeline_runs.status='completed'` | HTTP Response (xlsx bytes, Content-Disposition attachment) |
| LLM 호출 | Azure gpt-5.1 (1 call/cycle) | 없음 — 결정성 코드만 |
| 결정성 | summary (`history_csv_row`) 만 결정성, `report_md` 는 LLM 비결정성 | 100% 결정성 (template + cell write) |
| 의존성 | Mapper + Forecaster + Optimizer 결과 모두 필요 | Parser 결과만 필요 (Mapper 미사용) |
| graph cycle 위치 | 마지막 노드 (END 직전) | graph 외부 |
| 호출 빈도 | per cycle 1회 (자동) | per PM 액션 N회 (수동) |
| PG connection | `PGClient(cfg.mapper.postgres_url)` (별 인스턴스) | `PGClient(os.environ["POSTGRES_URL"])` (handler 직접 생성) |
| FE 표면 | Dashboard 카드 (history_csv_row + 9 view_jsonb) | "Export 엑셀" 버튼 다운로드 |
| 시연 의의 | "AI 가 종합 보고서 한 페이지로 정리" 메시지 | "AS-IS 수작업 통합 → TO-BE AI 5분 이내" 시간 단축 메시지 |

---

## 12. 이슈 표

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| 1 | **reporter → exporter rename 미시행** | `pipeline/agents/reporter.py` 파일명 + 13개 import path + `GraphConfig.reporter` 필드 + `_AGENTS_META[4]` (api.py:696-702) 모두 "Reporter" / "보고" 명명 | CLAUDE.md (2026-05-18) 가 "Agent rename: Reporter → Exporter" 결정 — B_Track 만 반영, A_Track rename 은 후속 PR 로 분리. 현재는 같은 코드베이스에 `reporter.py` (graph 노드) + `exporter.py` (xlsx 라우트) 가 다른 의미로 공존하여 신규 협업자 혼동 가능. | backlog |
| 2 | **4 시트 산식 검증 누락** | `_fill_quantity` 의 D/F/E/G 계산 (exporter.py:280-286) | sample 파일 (`docs/sample/통합작업일보_M15X*.xlsx`) 의 r5+ 데이터와 비교한 정합 테스트 없음. parser 가 잘못된 `today_qty` 박으면 그대로 전파. | backlog |
| 3 | **lifespan pool 재사용 미적용 (R-N7 동등)** | exporter_routes.py:23 / reporter.py:148 / graph.py:464 | 각 호출마다 새 PGClient connect/close. 약 수 ms 손해, prod 영향 무시 가능. | low-pri backlog |
| 4 | **atomized_count silent 0 누적** (G2) | graph.py:477 | atomizer skip 분기 (Mock fixture 등) 에서 `len(None or [])=0` → hours_saved_cum 누적 0, 경고 없음. | drift backlog |
| 5 | **postgres.md drift #N3** (`summary` vs `history_csv_row`) | spec 컬럼명 `summary` ↔ 실 init.sql `history_csv_row` | JSONB 의미 동일하지만 spec / schema 불일치. | drift #N3 |
| 6 | **FE swap 미실행** | `web/app/components/export/ConsolidatedReportCard.tsx:38-59` | A_Track endpoint 준비 완료 + UI swap 가이드 작성 완료. B_Track 작업 대기. 현재 정적 sample 다운로드. | B_Track 작업 대기 |
| 7 | **parser_reports.bp_summaries jsonb codec** | exporter.py:28-31 `_coerce` 헬퍼 | asyncpg jsonb codec 미등록 환경에서 str 로 떨어지는 케이스를 흡수하는 fallback 존재. 환경별 동작 불일치 가능성. | 안정성 fix 잔존 |
| 8 | **시트1 col 5 dual-meaning** (BP사 / 협력업체) | `COL_OUTPUT_MANPOWER["bp_code"] = 5` (exporter.py:118, 209) | r3 라벨 "BP사" / r4 라벨 "협력업체" 가 같은 cell. 코드는 `bp_code or company` 박는다. sample 파일이 BP_CODE 박기를 가정. company-only 케이스 검증 필요. | 가정-of-fact |
| 9 | **시트2/3 timeshift dict fallback scalar 박는 위치** | exporter.py:235 (yest_cum+5 = total 자리) | timeshift dict 없을 때 scalar `workers_cum_t` 를 yest_cum 블록의 마지막 cell (col_start+5) 에 박음. 우측 today_incr / today_cum 블록은 fallback 없음 — 즉 scalar 데이터 cycle 에선 우측 두 블록이 비어있음. | 의도 vs 누락 검증 필요 |

---

## 13. 다음 cycle 권고 (backlog)

1. **rename 1 PR** — `reporter.py` → `consolidated_reporter.py` (또는 새 이름) + 13 import path 정리. A_Track 한정 mechanical change.
2. **exporter 산식 회귀 테스트** — `docs/sample/*.xlsx` r5+ 데이터를 fixture 로 박고 `render_xlsx` 출력과 cell-by-cell 비교. parser_*  jsonb 의 실제 키 셋 검증도 동반.
3. **lifespan PG pool 재사용** — `exporter_routes.py` 핸들러가 `request.app.state.pg` 를 사용하도록 변경. 1줄 변경 + connect/close 비용 절감.
4. **G2 silent 0 가드** — graph.py:477 의 atomized_count=0 케이스를 warning log + 보고서 footnote 로 노출.
5. **B_Track UI swap 머지** — `docs/collector-exporter-ui-swap.md` 그대로 `handleExport` 교체 + `.env.local.example` 추가.

---

## 14. 핵심 commit 추적

| SHA | 메시지 (요약) | 영향 |
|---|---|---|
| `99ef43b` | feat(exporter): consolidated_template.xlsx | 4 시트 dummy header 만 보존하는 binary template 추가 |
| `b3010df` | feat(exporter): fetch_sheet_data PG SELECT | parser_reports / parser_activities JOIN pipeline_runs, SheetData dataclass |
| `38399ac` | feat(exporter): render_xlsx + 4 시트 _fill_* + COL dict | xlsx rendering core 완성 (8 COL dict 정의 + 4 _fill_* + _fill_timeshift 헬퍼) |
| `a7e2465` | feat(exporter): /export/run FastAPI endpoint + httpx 통합 테스트 | exporter_routes.py 신규 — APIRouter + Response 한글 파일명 raw_headers 패치 |
| `4b8a955` | feat(api): lifespan 안에 exporter router include | api.py 의 `app.include_router(exporter_router)` 1줄 |
| `56bcaee` | docs(exporter): B_Track UI swap 가이드 | `docs/collector-exporter-ui-swap.md` 작성 — `NEXT_PUBLIC_FASTAPI_BASE` env + handleExport 교체 코드 + 디자인 불가침 명시 |

본 cycle (`ef7c6cd` → `1ba783f`) reporter 본체 코드 변경 0. exporter 6 commit 으로 신규 서브시스템 1식 (백엔드 완성, FE swap 미실행) 추가.
