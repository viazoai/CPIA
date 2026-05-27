# Design Intent — reporter + exporter

- **Generated**: 2026-05-17 (hil1-forecaster-reporter cycle 신규)
- **Last checked**: 2026-05-26 (deep-dive baseline `ef7c6cd` → HEAD `1ba783f`)
- **본 cycle 갱신 (2026-05-26)**: reporter 본체 코드 변경 0 (161 LOC, PR #19 산물 그대로) — 그러나 **exporter 서브시스템 신규 흡수** (`pipeline/agents/exporter.py` 301 LOC + `pipeline/exporter_routes.py` 47 LOC + `pipeline/agents/exporter_templates/consolidated_template.xlsx` binary). 본 카드는 이제 **두 호출 경로** (graph 내부 reporter_node + graph 외부 FastAPI `/export/run`) 를 한 묶음으로 다룬다. "코드 변경 없음" 라벨은 **무효화** — exporter 신규 6 commit (`99ef43b` → `b3010df` → `38399ac` → `a7e2465` → `4b8a955` → `56bcaee`).
- **Pair files**: `../architecture_overview.md` §2.reporter / `../deep_dive_reporter.md` (533 LOC, 본 cycle 산물)
- **Range**:
  - `pipeline/agents/reporter.py` (161 LOC, 변경 없음)
  - `pipeline/agents/exporter.py` (301 LOC, **신규**)
  - `pipeline/agents/exporter_templates/consolidated_template.xlsx` (binary, **신규**)
  - `pipeline/exporter_routes.py` (47 LOC, **신규**)
  - `pipeline/api.py:31, 203` (`include_router` 1줄, **변경**)
  - `pipeline/tests/test_reporter.py` (177 LOC, 3건, 변경 없음)

핵심 분리선: reporter = LangGraph 마지막 노드 (Mapper+Forecaster+Optimizer 종합 보고서 마크다운 + G8/G2 영속화). exporter = LangGraph 외부 FastAPI 라우트 (parser_* PG jsonb → openpyxl → xlsx bytes 다운로드). 둘은 PG 만 공유, 호출 경로 완전 독립.

---

## T1 — Function Index

### reporter (변경 없음)

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `SYSTEM_PROMPT` | reporter.py:24 | str | 3 부 구조 마크다운 schema (작업 통합 / 진단 / 권고) + 한자 금지 + 들여쓰기 룰 | — |
| `ReporterConfig` | reporter.py:51 | `@dataclass` | Azure 크레덴셜 + LLM model + PG URL + timeout/retries | ✅ |
| `_build_llm_input` | reporter.py:62 | `(mapped, forecast_rows, optimizer_advice, today) -> dict[str, Any]` | LLM user message JSON 빌더 (4 키) | ✅ |
| `_build_summary` | reporter.py:88 | `(mapped, forecast_rows, optimizer_advice) -> dict` | history_csv_row JSONB summary (4 키) | ✅ |
| `report` | reporter.py:114 | `async (mapped, forecast_rows, optimizer_advice, run_id, today, cfg) -> tuple[str, dict]` | 종합 보고서 생성 + PG INSERT (공개 API) | ✅ |

### exporter (★ NEW — 본 cycle 신규)

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `NoDataError` | exporter.py:16 | `class(Exception)` | `(site_id, report_date)` 의 parser_* row 0건 시 raise | ✅ |
| `SheetData` | exporter.py:20 | `@dataclass` | 4 시트 입력 묶음 (output_manpower / occupation_manpower / equipment / quantity) | — |
| `_coerce` | exporter.py:28 | `(row) -> dict` | asyncpg jsonb codec 미등록 시 str → dict fallback | — |
| `fetch_sheet_data` | exporter.py:34 | `async (pg, site_id, report_date) -> SheetData` | parser_reports / parser_activities JOIN pipeline_runs → SheetData (★ NEW `b3010df`) | ✅ |
| `COL_OUTPUT_MANPOWER` | exporter.py:118 | `dict[str, int]` | 시트1 컬럼 매핑 (1-indexed, 12 키) | — |
| `COL_OCCUPATION` | exporter.py:137 | `dict[str, int]` | 시트2 컬럼 매핑 (8 키) | — |
| `COL_EQUIPMENT` | exporter.py:151 | `dict[str, int]` | 시트3 컬럼 매핑 (8 키) | — |
| `COL_QUANTITY` | exporter.py:166 | `dict[str, int]` | 시트4 컬럼 매핑 (16 키, 물량 산식 4 컬럼 포함) | — |
| `_korean_weekday` | exporter.py:189 | `(d: _date) -> str` | weekday → "월"~"일" | — |
| `_fill_timeshift` | exporter.py:193 | `(ws, row, col_start, ts) -> None` | 6 cell 연속 채움 (morning/daytime/overtime/night/all_night/total) | — |
| `_fill_output_manpower` | exporter.py:201 | `(ws, rows, report_date) -> None` | 시트1 fill (BP사 인원/작업 요지 + 4 timeshift 블록) | ✅ |
| `_fill_occupation` | exporter.py:220 | `(ws, rows, report_date) -> None` | 시트2 fill (직종 grain + scalar fallback) | ✅ |
| `_fill_equipment` | exporter.py:242 | `(ws, rows, report_date) -> None` | 시트3 fill (장비 grain + scalar fallback) | ✅ |
| `_fill_quantity` | exporter.py:262 | `(ws, rows, report_date) -> None` | 시트4 fill (물량 산식 D/F/E/G 계산) | ✅ |
| `render_xlsx` | exporter.py:290 | `(sheet_data, report_date, project) -> bytes` | 4 시트 cell write → BytesIO bytes (★ NEW `38399ac`) | ✅ |
| `router` | exporter_routes.py:13 | `APIRouter(prefix="/export", tags=["export"])` | FastAPI 라우터 객체 | — |
| `export_consolidated` | exporter_routes.py:16 | `async (site_id: str, date: str) -> Response` | `GET /export/run` 핸들러 — 한글 파일명 raw_headers UTF-8 패치 (★ NEW `a7e2465`) | ✅ |
| `app.include_router` | api.py:203 | `(exporter_router)` | lifespan-mounted FastAPI 에 1줄 마운트 (★ NEW `4b8a955`) | ✅ |

**T1 커버리지**: reporter 5/5 (그대로) + exporter 17/17 = **22/22 = 100%**.

---

## T2 — Issue Cards

### (A) reporter 카드 — 본 cycle 변경 없음

#### `report` — 종합 보고서 생성 + PG INSERT 공개 API

- **위치**: `pipeline/agents/reporter.py:114-161` (48 LOC, 분기 2)
- **시그니처**: `async def report(mapped: list[Activity], forecast_rows: list[dict], optimizer_advice: list[dict], run_id: uuid.UUID, today: _date, cfg: ReporterConfig) -> tuple[str, dict]`
- **본 cycle 노트**: 코드 변경 0. last_checked stamp 만 갱신 (2026-05-20 → 2026-05-26).
- **이슈**:
  - git log `22d44c2` — Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports 최초 및 본 cycle 종결.
  - 컨테이너 spec: `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3` — Reporter 위치 = Optimizer 다음 (의도적 drift, PM 원안 v2 = Atomizer 다음 병렬).
  - drift backlog: #1 (PoC 성공 기준 #1 직접 미충족 — 본 commit 으로 해소).
- **설계 의도**:
  - 종합 1 종: 사내/발주처 분리 보고서 (원안 2 종) → PoC 시연 단순화 = 종합 1 종 + 3 부 구조.
  - Optimizer 다음: Forecaster + Optimizer 결과 모두 포함하여 1 LLM call 로 종합.
  - empty fallback: `mapped` 빈 list → 짧은 "보고서 생성 실패" MD + PG INSERT skip (FK violation 방지).
  - PG 영속: `daily_reports.history_csv_row` JSONB (postgres.md §5 spec 의 `summary` 필드명 mismatch — drift #N3).
  - `bp_name=None`: 종합 보고서이므로 BP사 단위 없음 (실 schema 의 nullable 활용).
- **대응 패턴**:
  - 발동: `graph.py:reporter_node:444-490` 가 호출 (hil_2 conditional_edge 양쪽 path 합류 — selection=[] 또는 optimizer → reporter)
  - 처리: empty 검사 → AzureOpenAI client (timeout 60s, max_retries 3) → `_build_llm_input` JSON → chat.completions.create → response.choices[0].message.content (None 시 fallback) → `_build_summary` → PGClient connect → `insert_daily_report` (history_csv_row=summary) → close
  - 출력: `(report_md, summary)` tuple
- **관련**:
  - 호출자: `graph.py:reporter_node:444-490`
  - 내부 헬퍼: `_build_llm_input` + `_build_summary`
  - PG INSERT: `db.py:insert_daily_report:405-456` (UPDATE-first 패턴 — Optimizer view_builder 가 먼저 row 만든 경우 UniqueViolation 회피)
  - G8/G2: `db.py:update_site_last_run:1109-1117` + `db.py:update_site_hours_saved_cum:1125-1141`
  - 테스트: `tests/test_reporter.py` 3건
  - 페어 spec: `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3`

#### `_build_llm_input` — LLM user message JSON 빌더

- **위치**: `pipeline/agents/reporter.py:62-86` (25 LOC, 분기 0 — list comprehension)
- **본 cycle 노트**: 변경 없음.
- **설계 의도**: 4 키 schema 명시 (date + activities + forecast + optimizer_advice). 1 부 → activities (mapped 합산용 row 추출, 7 필드: company/trade/l6_main/unit/today_qty/assigned_workers/work_content). 2 부 → forecast (Forecaster row dict 그대로). 3 부 → optimizer_advice (빈 list 시 LLM 이 3 부 생략, SYSTEM_PROMPT 명시). `Activity` TypedDict 전체가 아닌 7 필드만 추출 — 본인 의도 외 노이즈 제거 (mapping_conf, wbs_activity_id 등 LLM 무관).
- **관련**: 호출자 `report:130` / 테스트 `tests/test_reporter.py:test_reporter_empty_optimizer_advice_skips_3bu`.

#### `_build_summary` — daily_reports.history_csv_row JSONB summary

- **위치**: `pipeline/agents/reporter.py:88-112` (25 LOC, 분기 3)
- **본 cycle 노트**: 변경 없음.
- **설계 의도**: 4 핵심 지표 (LLM 비결정성과 분리한 결정성 컬럼).
  - `total_workers`: 전 row `assigned_workers` 합 (BP사 총 인원).
  - `total_qty_by_trade`: `{trade: today_qty 합}` (공종별 일일 물량).
  - `risk_counts`: `{"정상": N, "주의": N, "이상": N}` — Forecaster risk_level 분포.
  - `advice_count`: Optimizer advice row 수 (= 0 시 reporter 3 부 생략).
- **관련**: 호출자 `report:139` / PG INSERT `db.py:insert_daily_report:405-456` (history_csv_row 인자).

#### `ReporterConfig` — Azure + PG + timeout/retries 묶음

- **위치**: `pipeline/agents/reporter.py:51-60` (10 LOC, dataclass)
- **본 cycle 노트**: 변경 없음.
- **설계 의도**: `ForecasterConfig` + `OptimizerConfig` 와 동일 패턴 (Azure 통일, audit-report §3). default timeout=60 / max_retries=3 = forecaster `_call_azure_llm` 패턴 차용. env injection 의도 (`synthetic_daily_report.py:_build_reporter_config`).

#### `reporter_node` G8/G2 영속화 블록

- **위치**: `pipeline/graph.py:444-490`
- **본 cycle 노트**: 변경 없음 (2026-05-19 cf3c143 산물 그대로).
- **설계 의도**: report() 호출 후 동일 cycle 안에서 (1) `update_site_last_run` (G8) → sites.last_run_id 갱신, (2) `update_site_hours_saved_cum` (G2) → `(120-5)/60 * atomized_count` h 누적, (3) `pipeline_runs SET status='completed'` (2026-05-20 fix — cycle 7차 발견 후 reporter 도달 후에도 status='running' 으로 남던 버그 해소). state.site_id None 이면 pipeline_runs 에서 fallback fetch.
- **Suspected related** (이슈 표 #4 참조): atomizer skip 분기에서 `len(None or [])=0` → hours_saved_cum delta=0 silent 누적, 경고 없음. 검증 부재.

---

### (B) exporter 카드 — ★ NEW (본 cycle 신규)

#### E-RX — `render_xlsx` — xlsx bytes 생성 진입점

- **위치**: `pipeline/agents/exporter.py:290-301` (12 LOC, 분기 1)
- **시그니처**: `def render_xlsx(sheet_data: SheetData, report_date: _date, project: str) -> bytes`
- **이슈**:
  - ★ NEW commit `38399ac` (feat(exporter): render_xlsx + 4 시트 _fill_* + COL dict).
  - 시트 이름 한글 고정 ("1.출력인원 현황" / "2.직종별 인원현황" / "3.장비현황" / "4.물량") — template 의 sheet name 과 1:1 매핑. 시트명 변경 시 즉시 KeyError.
- **설계 의도**:
  - openpyxl `load_workbook(TEMPLATE_PATH)` → 4 시트 sheet name 으로 직접 access → 각 `_fill_*` 호출 → `BytesIO` save → bytes 반환. 파일시스템 write 없음 — 모두 메모리 buffer.
  - `DATA_START_ROW = 5` — r1~r4 = template 헤더 (불변), r5 부터 데이터 cell write.
  - **시연자 디자인 불가침** (memory: feedback_no_design_change) 원칙 정합: visual styling (merged cell, column width, font, border) 은 모두 template 에 박혀있어 코드가 손대지 않음. 본문 데이터만 동적 채움.
  - LLM 호출 없음 — 100% 결정성 코드 (reporter 의 LLM 비결정성과 정반대).
- **대응 패턴**:
  - 발동: `exporter_routes.py:36` (`export_consolidated` 핸들러 마지막 라인)
  - 입력: `SheetData` (4 시트 list[dict] 묶음) + `report_date` + `project` 이름
  - 처리: template load → 시트별 `_fill_*` → BytesIO save → bytes
  - 출력: xlsx bytes (수십 KB ~ 수 MB)
- **관련**:
  - 호출자: `exporter_routes.py:36`
  - 헬퍼: `_fill_output_manpower` / `_fill_occupation` / `_fill_equipment` / `_fill_quantity` / `_fill_timeshift`
  - Template: `exporter_templates/consolidated_template.xlsx` (★ NEW `99ef43b`)
- **Suspected related** (이슈 표 #2): sample 파일 (`docs/sample/통합작업일보_M15X*.xlsx`) 의 r5+ 데이터와 cell-by-cell 비교 회귀 테스트 없음. parser 가 잘못된 `today_qty` 박으면 그대로 전파.

#### E-FSD — `fetch_sheet_data` — parser_* JOIN pipeline_runs

- **위치**: `pipeline/agents/exporter.py:34-94` (61 LOC, 분기 2 — NoDataError + 4 SELECT 합집합)
- **시그니처**: `async def fetch_sheet_data(pg: PGClient, site_id: str, report_date: _date) -> SheetData`
- **이슈**:
  - ★ NEW commit `b3010df`.
  - **JOIN 필수 이유**: `parser_reports` / `parser_activities` 에 site_id 컬럼 없음 → `pipeline_runs USING (run_id)` JOIN 으로 site_id 필터. Spec §7.1.
  - 한 site 의 같은 날짜에 여러 run (BP사별 작업일보 다건 처리) 이 있으면 **모든 run 의 jsonb element 가 합집합** — `jsonb_array_elements` 가 N 개 jsonb 배열을 평면화.
- **설계 의도**:
  - 4 SELECT (bp_summaries / job_allocations / equipment_allocations / parser_activities raw) → `SheetData` dataclass 로 합쳐 반환.
  - 4 결과 모두 빈 list 면 `NoDataError(f"해당 ({site_id}, {report_date.isoformat()}) 데이터 없음")` raise → 핸들러가 HTTP 400 으로 변환.
  - `_coerce` 헬퍼 (exporter.py:28-31): asyncpg jsonb codec 미등록 환경에서 jsonb 가 str 로 떨어지는 케이스 흡수 → `json.loads`.
- **대응 패턴**:
  - 발동: `exporter_routes.py:30` (핸들러 안)
  - 입력: 외부에서 만든 PGClient + site_id + report_date
  - 처리: `pg._pool.acquire()` 컨텍스트 → 4 SELECT → list comprehension → SheetData
  - 출력: `SheetData(output_manpower, occupation_manpower, equipment, quantity)` 또는 NoDataError raise
- **관련**:
  - 호출자: `exporter_routes.py:30`
  - PG 의존: `parser_reports.bp_summaries / job_allocations / equipment_allocations` (jsonb 컬럼, 5.18 마이그) + `parser_activities` (정규화 row) + `pipeline_runs.site_id` (JOIN 키)
- **Suspected related** (이슈 표 #7): asyncpg jsonb codec 미등록 환경에서 동작 불일치. `_coerce` fallback 이 안정성을 보장하지만 환경별 일관성 검증 부재.

#### E-FOM — `_fill_output_manpower` — 시트1 fill (BP사 인원/작업 요지)

- **위치**: `pipeline/agents/exporter.py:201-217` (17 LOC, 분기 1 — for loop)
- **시그니처**: `def _fill_output_manpower(ws, rows: list[dict], report_date: _date) -> None`
- **이슈**:
  - ★ NEW `38399ac`.
  - **시트1 col 5 dual-meaning**: r3 라벨="BP사" / r4 라벨="협력업체" 가 **같은 cell** (single cell, single col 5). 코드는 `bp_code or company` 둘 중 하나만 박음 (exporter.py:209). sample 파일이 BP_CODE 박기를 가정 — company-only 케이스 검증 필요.
- **설계 의도**:
  - r5 부터 row 별 cell write: zone / disc_abbrev (trade) / bp_code 또는 company / scope / work_text_yesterday/today/tomorrow.
  - **4 timeshift 블록** (각 6 cell 연속): `workers_yesterday_incr` (col 10~15) / `workers_yesterday_cum` (col 17~22) / `workers_today_incr` (col 24~29) / `workers_today_cum` (col 31~36). 사이 cell (16/23/30) 은 final cum 자리 (r4 라벨 없으나 r5 에 누계값 박힘 → 블록 6 cell + final).
  - 6 timeshift key 순서 hard-coded: `morning / daytime / overtime / night / all_night / total` (_fill_timeshift exporter.py:197).
- **대응 패턴**: 호출자 `render_xlsx:295`, 입력 `wb["1.출력인원 현황"]` worksheet + `SheetData.output_manpower` list[dict], 출력 cell write (return None).
- **관련**: `COL_OUTPUT_MANPOWER` (exporter.py:118) / `_fill_timeshift` (exporter.py:193).

#### E-FOC — `_fill_occupation` — 시트2 fill (직종 grain)

- **위치**: `pipeline/agents/exporter.py:220-239` (20 LOC, 분기 6 — for + 3 isinstance + 1 elif)
- **이슈**:
  - ★ NEW `38399ac`.
  - **scalar fallback 위치 편향**: parser 단계에서 timeshift dict 가 없으면 scalar `workers_cum_t` 를 **yest_cum 블록의 last cell** (col_start+5 = total 자리, exporter.py:235) **에만** 박음. 우측 today_incr / today_cum 블록은 fallback 없음 — 즉 scalar 데이터 cycle 에선 우측 두 블록이 비어있음.
- **설계 의도**:
  - 5 분류 필드: trade / bp_code / manager_code / worker_code / job_type.
  - 3 timeshift 블록 (yest_cum / today_incr / today_cum) — dict 면 6 cell 채움, 아니면 (yest_cum 만) scalar 를 total 자리에 박음.
  - dict 우선 가드 (`isinstance(..., dict)`) — None 또는 scalar 가 dict 로 잘못 해석되는 사고 방지.
- **관련**: `COL_OCCUPATION` (exporter.py:137) / `_fill_timeshift`.
- **Suspected related** (이슈 표 #9): scalar fallback 이 yest_cum 블록에만 박힘 — today_* 블록 누락 가능. 의도 vs 누락 검증 필요.

#### E-FEQ — `_fill_equipment` — 시트3 fill (장비 grain)

- **위치**: `pipeline/agents/exporter.py:242-259` (18 LOC, 분기 6)
- **이슈**:
  - ★ NEW `38399ac`.
  - 시트2 와 **동일 패턴** — "인원" 대신 "대수 (count)" 의미. scalar fallback 도 동일하게 yest_cum 블록에만 박음 (이슈 #9 동일 risk).
- **설계 의도**:
  - 5 분류 필드: trade / bp_code / equipment_big / equipment_mid / equipment_spec (장비 3단 분류).
  - 3 timeshift 블록: count_yesterday_cum / count_today_incr / count_today_cum (scalar fallback = `count_cum_t`).
- **관련**: `COL_EQUIPMENT` (exporter.py:151) / `_fill_timeshift`.

#### E-FQT — `_fill_quantity` — 시트4 fill (Activity 별 물량 진척)

- **위치**: `pipeline/agents/exporter.py:262-287` (26 LOC, 분기 3 — for + 2 if)
- **이슈**:
  - ★ NEW `38399ac`.
  - **물량 산식** (exporter.py:280-286):
    - `A = plan_total_qty` (총물량, col 10)
    - `B = yesterday_cum_qty` (전일누적, col 11)
    - `C = today_qty` (금일실적, col 12)
    - `D = B + C` (금일누적, col 13)
    - `F% = D / A * 100` (진척률, col 14)
    - `E = A - D` (잔여, col 15)
    - `G% = 100 - F%` (잔여율, col 16)
  - **None 안전 가드**: `b` 또는 `c` None 이면 D/F/E/G 모두 skip. `a` falsy (0 또는 None) 이면 F/E/G skip (ZeroDivision 방지). 즉 a=0 이어도 D 는 계산 (B+C 가능하면).
- **설계 의도**:
  - source 가 `parser_activities` 정규화 row (jsonb 아님) — `pa.*` SELECT 직접.
  - 표시 7 분류 필드: zone / trade (or disc_abbrev fallback) / bp_code / company / scope / work_content (rep_work) / unit.
- **관련**: `COL_QUANTITY` (exporter.py:166, 16 키 — 산식 4 컬럼 포함).
- **Suspected related** (이슈 표 #2): 4 시트 산식 회귀 테스트 누락.

#### E-EX — `export_consolidated` `/export/run` 핸들러

- **위치**: `pipeline/exporter_routes.py:16-47` (32 LOC, 분기 3)
- **시그니처**: `@router.get("/run") async def export_consolidated(site_id: str, date: str) -> Response`
- **이슈**:
  - ★ NEW commit `a7e2465` (feat(exporter): /export/run FastAPI endpoint + httpx 통합 테스트).
  - **한글 파일명 우회**: starlette `Response(headers={...})` 경로는 latin-1 강제 → `UnicodeEncodeError`. 대신 `resp.raw_headers.append((b"content-disposition", utf8_bytes))` 로 직접 주입 → RFC 6266 호환 클라이언트가 UTF-8 디코딩. 브라우저에서 "통합작업일보_2025-09-25.xlsx" 그대로 저장.
  - **자체 PG connection**: `PGClient(os.environ["POSTGRES_URL"])` 를 핸들러가 직접 생성 → finally close. lifespan-managed pool (`app.state.pg`) 미사용 (이슈 #3, micro-optimization 후보).
- **설계 의도**:
  - request 계약: `GET /export/run?site_id=<text>&date=<YYYY-MM-DD>` (두 query param 필수).
  - 에러 매핑: date 파싱 실패 → HTTP 400 / site 없음 → 404 / `NoDataError` → 400 (validation 성).
  - 응답: 단순 `Response(content=xlsx_bytes)` (FileResponse / StreamingResponse 아님) — `render_xlsx` 가 이미 bytes 화 완료, streaming 무의미.
  - graph cycle 과 무관한 read-only 경로 — graph state 불변, 진행 중 cycle 에 영향 없음.
- **대응 패턴**:
  - 발동: HTTP `GET /export/run` (FE `ConsolidatedReportCard.tsx` 의 `handleExport`)
  - 처리: date 파싱 → PGClient connect → fetch_site_by_id → fetch_sheet_data → render_xlsx → Response (한글 파일명 raw_headers) → finally PG close
  - 출력: HTTP Response (xlsx bytes + Content-Disposition attachment)
- **관련**:
  - mount: `pipeline/api.py:31, 203` (★ NEW `4b8a955` — `app.include_router(exporter_router)`)
  - `fetch_site_by_id`: `db.py:1220-1229`
  - FE 호출 (현재 sample fallback): `web/app/components/export/ConsolidatedReportCard.tsx:38-59`
  - UI swap 가이드: `docs/collector-exporter-ui-swap.md` (★ NEW `56bcaee`)
- **Suspected related** (이슈 표 #6): A_Track endpoint 준비 완료 + UI swap 가이드 작성 완료. B_Track FE swap 미실행 — 정적 `/sample/cpia-consolidated-report.xlsx` 그대로 다운로드 중.

#### E-TMPL — `consolidated_template.xlsx` (binary)

- **위치**: `pipeline/agents/exporter_templates/consolidated_template.xlsx`
- **이슈**:
  - ★ NEW commit `99ef43b`.
  - **4 시트 dummy 헤더 만 보존** — r1~r4 visual styling (merged cell, column width, font, border) 그대로, r5+ 데이터 row 는 비어있음. 코드는 `cell.value` 만 write 하므로 styling 일관성 자동 보존.
- **설계 의도**:
  - 시연자 (조형준 프로) 시트 디자인 의도 보존 — markup / styling 코드가 만지지 않음 (memory: feedback_no_design_change 정합).
  - 시트 이름 4 개 한글 고정 — `render_xlsx` 가 sheet name 으로 직접 access. 시트명 변경 즉시 KeyError.
- **관련**: `render_xlsx` (TEMPLATE_PATH 로드) / `exporter_templates/__init__.py` (empty package marker).

#### E-MNT — `app.include_router(exporter_router)` lifespan integration

- **위치**: `pipeline/api.py:31, 203` (1 import + 1 router 마운트)
- **이슈**:
  - ★ NEW commit `4b8a955`.
  - **lifespan 의존 회피**: `exporter_routes` 가 `app.state.pg` / `app.state.graph` / `app.state.cfg` 중 어느 것도 안 씀. `PGClient(os.environ["POSTGRES_URL"])` 로 자체 connection 생성.
- **설계 의도**:
  - `include_router` 는 app 객체 정의 직후 (api.py:203) 호출 — lifespan 보다 먼저 실행. 첫 request 시점엔 router 등록 완료.
  - lifespan 이 `POSTGRES_URL` 미설정 시 RuntimeError 로 부팅을 막으므로, exporter 호출 시점에는 항상 env 존재 → `os.environ["POSTGRES_URL"]` KeyError 위험 없음.
  - `APIRouter(prefix="/export", tags=["export"])` 로 정의 — 최종 endpoint `GET /export/run`, swagger UI 의 `export` 그룹.
- **Suspected related** (이슈 표 #3): lifespan PG pool 재사용 micro-optimization 후보 (R-N7 동등). `request.app.state.pg` 사용으로 1줄 변경 가능, connect/close 비용 절감. low-pri.

---

## 의도적 drift 메모 (spec §3 정합)

| 항목 | PM 원안 v2 | 본 cycle | 사유 |
|---|---|---|---|
| Reporter 위치 | Atomizer 다음 (Forecaster 와 병렬) | Optimizer 다음 (hil_2 conditional 분기 합류) | Forecaster + Optimizer 결과 모두 포함하는 종합 보고서 — 1 LLM call 효율 |
| Reporter 출력 | 사내 + 발주처용 2 종 | 종합 1 종 | PoC 시연 단순화 |
| Reporter LLM | Sonnet 4.6 | Azure gpt-5.1-chat-ai-board-test | audit-report §3 (Azure 통일) |
| daily_reports schema | postgres.md §5 (date / summary) | 실 init.sql (report_date / history_csv_row + bp_name 추가) | drift #N3 — schema migration 별 cycle |
| Exporter 위치 | (원안 없음 — 신규 시연 요구사항) | LangGraph 외부 FastAPI `/export/run` 라우트 | graph cycle 무관 on-demand 다운로드 + read-only — graph 영향 격리 |
| Exporter agent rename | CLAUDE.md 2026-05-18 — Reporter → Exporter | A_Track 미시행 (reporter.py / 13 import / GraphConfig.reporter / _AGENTS_META[4] 모두 "Reporter" 잔존) | B_Track 만 rename 반영, A_Track rename 은 후속 PR 로 분리 (이슈 #1) |

---

## 이슈 표 (본 cycle 갱신, 9건)

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| R-N1 (M) | **reporter → exporter rename 미시행** | `pipeline/agents/reporter.py` 파일명 + 13개 import path + `GraphConfig.reporter` 필드 + `_AGENTS_META[4]` (api.py:696-702) | CLAUDE.md (2026-05-18) 결정 vs 실 코드 불일치. 같은 코드베이스에 `reporter.py` (graph 노드) + `exporter.py` (xlsx 라우트) 가 다른 의미로 공존 → 신규 협업자 혼동 가능. | backlog |
| R-N2 (M) | **B_Track FE swap 미실행** | `web/app/components/export/ConsolidatedReportCard.tsx:38-59` | A_Track endpoint (commit `a7e2465`) + UI swap 가이드 (commit `56bcaee`) 준비 완료. 현재 정적 `/sample/cpia-consolidated-report.xlsx` fallback 다운로드. 실제 A_Track endpoint 미호출. | B_Track 작업 대기 |
| 2 | **4 시트 산식 회귀 테스트 누락** | `_fill_quantity` D/F/E/G (exporter.py:280-286) + `_fill_output_manpower` 4 timeshift 블록 + `_fill_occupation/_fill_equipment` scalar fallback | sample 파일 (`docs/sample/통합작업일보_M15X*.xlsx`) r5+ 데이터와 cell-by-cell 비교 fixture 없음. parser 가 잘못된 값 박으면 그대로 전파. | backlog |
| 3 | **lifespan PG pool 재사용 미적용** (R-N7 동등) | exporter_routes.py:23 / reporter.py:148 / graph.py:464 | 각 호출마다 새 PGClient connect/close. 약 수 ms 손해, prod 영향 무시 가능. `request.app.state.pg` 사용으로 1줄 변경 가능. | low-pri backlog |
| 4 | **G2 atomized_count=0 silent 누적 가드 없음** | graph.py:477 | atomizer skip 분기 (Mock fixture 등) 에서 `len(None or [])=0` → hours_saved_cum 누적 0, 경고 없음. | drift backlog |
| 5 | **postgres.md drift #N3** (`summary` ↔ `history_csv_row`) | spec 컬럼명 `summary` ↔ 실 init.sql `history_csv_row` | JSONB 의미 동일하지만 spec / schema 불일치. | drift #N3 |
| 7 | **parser_reports.bp_summaries jsonb codec 환경 의존** | `_coerce` 헬퍼 (exporter.py:28-31) | asyncpg jsonb codec 미등록 환경에서 str 로 떨어지는 케이스 fallback. 환경별 동작 불일치 가능. | 안정성 fix 잔존 |
| 8 | **시트1 col 5 dual-meaning** (BP사 / 협력업체) | `COL_OUTPUT_MANPOWER["bp_code"] = 5` (exporter.py:118, 209) | r3 라벨 "BP사" / r4 라벨 "협력업체" 가 같은 cell. 코드는 `bp_code or company` 박음. sample 이 BP_CODE 박기를 가정. company-only 케이스 검증 필요. | 가정-of-fact |
| 9 | **시트2/3 scalar fallback yest_cum 블록 only** | exporter.py:235 (`C["yest_cum"] + 5` total 자리) + exporter.py:255 (시트3 동일 패턴) | timeshift dict 없을 때 scalar 를 yest_cum 블록 last cell 에만 박음. today_incr / today_cum 블록은 fallback 없음 — scalar 데이터 cycle 에선 우측 두 블록 비어있음. | 의도 vs 누락 검증 필요 |

기존 R-G8 / R-G2 / R-N7 카드 (2026-05-19 cf3c143 산물) 는 본 cycle 변경 없음 — last_checked stamp 만 갱신. R-N7 은 이슈 #3 으로 흡수.

---

## 미해결 핵심 (다음 cycle)

1. **rename 1 PR (R-N1)** — `pipeline/agents/reporter.py` → `consolidated_reporter.py` (또는 새 이름) + 13 import path + `GraphConfig.reporter` + `_AGENTS_META[4]` 정리. A_Track 한정 mechanical change. CLAUDE.md (2026-05-18) 결정 동기화.
2. **exporter 산식 회귀 테스트 (이슈 #2)** — `docs/sample/*.xlsx` r5+ 데이터 fixture + `render_xlsx` 출력 cell-by-cell 비교. parser_* jsonb 의 실제 키 셋 (`workers_yesterday_incr` 등) 검증 동반.
3. **B_Track UI swap 머지 (R-N2)** — `docs/collector-exporter-ui-swap.md` 그대로 `handleExport` 교체 + `.env.local.example` 에 `NEXT_PUBLIC_FASTAPI_BASE` / `NEXT_PUBLIC_DEFAULT_SITE_ID` 추가. 디자인 불가침 (markup / className / Toaster 인터페이스 유지).
4. **G2 silent 0 가드 (이슈 #4)** — graph.py:477 의 atomized_count=0 케이스를 warning log + 보고서 footnote 로 노출.
5. **lifespan PG pool 재사용 (이슈 #3)** — `exporter_routes.py` 핸들러가 `request.app.state.pg` 사용. 1줄 변경.
6. **공통 `_call_azure_llm` 추출** — forecaster + optimizer + reporter 의 timeout/max_retries 패턴 중복 (refactor 후보, low).
7. **drift #N3 schema migration** — postgres.md §5 정정 또는 init.sql 정렬 (persistence 카드 + reporter 카드 양쪽 영향).

---

## 핵심 commit 추적 (본 cycle)

| SHA | 메시지 (요약) | 영향 |
|---|---|---|
| `99ef43b` | feat(exporter): consolidated_template.xlsx | 4 시트 dummy header 만 보존하는 binary template 추가 |
| `b3010df` | feat(exporter): fetch_sheet_data PG SELECT | parser_reports / parser_activities JOIN pipeline_runs, SheetData dataclass |
| `38399ac` | feat(exporter): render_xlsx + 4 시트 _fill_* + COL dict | xlsx rendering core 완성 (4 COL dict + 4 _fill_* + _fill_timeshift 헬퍼) |
| `a7e2465` | feat(exporter): /export/run FastAPI endpoint + httpx 통합 테스트 | exporter_routes.py 신규 — APIRouter + Response 한글 파일명 raw_headers 패치 |
| `4b8a955` | feat(api): lifespan 안에 exporter router include | api.py 의 `app.include_router(exporter_router)` 1줄 |
| `56bcaee` | docs(exporter): B_Track UI swap 가이드 | `docs/collector-exporter-ui-swap.md` 작성 — `NEXT_PUBLIC_FASTAPI_BASE` env + handleExport 교체 코드 + 디자인 불가침 명시 |

본 cycle (`ef7c6cd` → `1ba783f`): reporter 본체 코드 변경 0. exporter 6 commit 신규 서브시스템 1 식 (백엔드 완성, FE swap 미실행). 합계 348 LOC 신규 + 1 라인 api.py 변경.
