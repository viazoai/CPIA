# Design Intent — parser

- **Generated**: 2026-06-01 (d317be9 — parser 헤더기반 다포맷 7-task + parser_node async multi-file merge)
- **Git baseline → HEAD**: `1ba783f` (2026-05-26 A_Track) → `d317be9` (2026-06-01 Merge A_Track)
- **Pair files**:
  - `../deep_dive_parser.md` (897 줄, 본 갱신의 raw grounding — 정확한 함수표/라인번호)
  - `../architecture_overview.md` (시스템 다이어그램)
- **Range** (9 파일 / 2,114 LOC):
  - `pipeline/agents/parser.py` (664 LOC) — **본 cycle: header-based 다포맷 7-task (LLM 검증 제거)**
  - `pipeline/agents/parser_post.py` (201 LOC) — 본 cycle 코드 변경 0
  - `pipeline/agents/parser_llm.py` (660 LOC) — **DEPRECATED 2026-05-20**, 코드 보존
  - `pipeline/agents/parser_node.py` (64 LOC) — **본 cycle: 25 LOC sync wrapper → async N병렬 concat merge**
  - `pipeline/agents/collector.py` (70 LOC) — legacy CLI 경로 (run_one_cycle 전용)
  - `pipeline/agents/collector_node.py` (63 LOC) — D-12 graph 진입 노드
  - `pipeline/collector/filename_parser.py` (64 LOC) — YYMMDD/YYYYMMDD 파일명 분해
  - `pipeline/collector/idle_worker.py` (260 LOC) — IMAP IDLE listener
  - `pipeline/collector/config.py` (68 LOC) — env 로드 + fail-fast 자격증명
- **스펙**:
  - `docs/superpowers/plans/2026-06-01-cpia-parser-header-based-multiformat.md`
  - `docs/superpowers/specs/2026-06-01-cpia-parser-header-based-multiformat-design.md`
  - `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`
  - `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md`

**한 줄 요약**: 작업일보 xlsx/xlsm 1개 → 4 시트 (출력인원/직종/장비/물량) 통합 `ParsedDailyReport`. 본 cycle 의 핵심 변화는 **parser 가 header-based 다포맷으로 확장** (issue#52 업체작업일보 컬럼시프트 garbage 해소 — 시트4 컬럼을 헤더 텍스트로 해석, BP 코드 다중 패턴, 시트2/3 final_flag 조건부 게이트, .xlsm 날짜 수용) + **무력 LLM 검증 wrapper 완전 제거** + **parser_node 가 25 LOC sync 1줄 wrapper → 64 LOC async N병렬 concat merge** 로 multi-file 통합. parser 내부 결정성 보장 정책 (openpyxl rule + header 매핑만, LLM 0 호출) 유지.

---

## 1. 7 필수 섹션 — Overview

Parser 서브시스템 진입점은 **여전히 `parse_daily_report(xlsx_path)`** (`pipeline/agents/parser.py:625`) 1개. 동기 함수, openpyxl rule-based + header-based 추출만 (~5초 / cycle / 첨부 1건). **LLM 검증 wrapper 는 본 cycle (`ac0a8c5`) 으로 완전 제거** — 현재 parser 서브시스템은 LLM 0 호출, 완전 결정론적.

본 cycle (`1ba783f` → `d317be9`) 의 6 commit 은 **parser 헤더기반 다포맷 7-task + parser_node async multi-file merge**:

| Commit | 변경 |
|---|---|
| `65a8027` | `fix(parser)`: `_DATE_PATTERN` 이 8자리 날짜+.xlsm 조합 수용 (업체작업일보) |
| `7d2befc` | `feat(parser)`: BP코드 다중 패턴 (`PH_X-NNN` + `M15X_PHn_NNN`) — `_BP_PATTERNS` 2종 |
| `25bb85d` | `feat(parser)`: 시트4 헤더 기반 컬럼 해석 (`_resolve_sheet4_columns` / `_build_activity`) — column shift 해소 (통합+업체) |
| `c0699dc` | `feat(parser)`: 시트2/3 final_flag 조건부 완화 (`has_final_flag` — 'O' 없는 업체포맷만) |
| `ac0a8c5` | `feat(parser)`: 업체포맷 E2E 통합 + **무력 LLM 검증 제거** (demo_inputs 10개 골든) |
| `a8d17e4` | `feat(graph)`: multi-file async parser merge + hil_1 resume falsy-fix |

issue#52 근본원인 (design spec §1.1 인용): 업체작업일보엔 '업체명' 컬럼이 없어 `col7` 이후가 1칸 좌측 시프트 → `company←Scope("F02 5F")`, `work_content←단위("M")`, `unit←총물량` garbage. 헤더 텍스트 기반 컬럼 resolve 로 통합/업체 양식을 단일 코드로 흡수해 정상화.

골든 (회귀 고정): 통합 byte-identical `act=1193 / bp_summaries=99 / job=975 / equip=1111`, 업체 골든 `act=33 / bp=1 / job=76 / equip=68`.

---

## 2. T1 — Function Index

### 2.1 parser.py (664 LOC) — 본 cycle: header-based 다포맷 7-task

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `ParseError` | parser.py:30 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 | — |
| `_normalize_unit` | parser.py:47 | `(s: str) -> str` | 단위 대소문자 통일 (M2→m2) | — |
| `_disc_abbrev_to_kr` | parser.py:52 | `(abbrev: str\|None) -> str\|None` | 공종 약자 → 한글 (AR→건축 등) | — |
| `_is_admin_job` | parser.py:59 | `(job_type: str) -> bool` | 관리자 직종 noise 판정 | — |
| `_is_total_row` | parser.py:64 | `(row: tuple) -> bool` | 시트2 합계 row 판정 (현재 미참조 — dead) | — |
| `_ffill` | parser.py:72 | `(rows, header_end, fill_cols) -> list[tuple[int, list]]` | 헤더 이후 row forward-fill (현재 미참조 — dead) | — |
| `_BP_PATTERNS` | parser.py:97 | `tuple[re.Pattern, ...]` | 통합 `PH_X-NNN` + 업체 `M15X_PHn_NNN` 2 정규식 | ✅ |
| `_is_bp_code` | parser.py:103 | `(v: object) -> bool` | `_BP_PATTERNS` 중 하나라도 match | ✅ |
| `_safe_int` | parser.py:110 | `(v: object) -> int` | None / 비정수 → 0 | — |
| `_shift_dict_sum` | parser.py:119 | `(ws, start, end, col_start) -> TimeShiftCounts` | 6 칸 시간대 group 합 (시트1) | — |
| `_parse_sheet1_bp_summaries` | parser.py:128 | `(ws) -> list[BPSummary]` | 시트1 rule — col 30 merged group boundary | ✅ |
| `_shift_dict_row` | parser.py:248 | `(ws, r, col_start) -> TimeShiftCounts` | 6 칸 시간대 단일 row (시트2/3) | — |
| `_parse_sheet2_job_allocations` | parser.py:256 | `(ws) -> list[JobAllocation]` | 시트2 rule — Mm01 group + final_flag 조건부 게이트 | ✅ |
| `_safe_num` | parser.py:342 | `(v: object) -> float\|None` | None / 비수치 → None | — |
| `_norm_header` | parser.py:353 | `(v: object) -> str` | 헤더 셀 공백 제거 정규화 (매핑 비교용) | — |
| `_resolve_sheet4_columns` | parser.py:357 | `(ws, header_rows=(3, 4)) -> dict[str, int]` | 시트4 헤더 텍스트 → {필드: 컬럼인덱스} (통합/업체 흡수) | ✅ |
| `_build_activity` | parser.py:403 | `(ws, r, cols, trade, bp_code, company_raw) -> Activity` | cols 인덱스 기준 단일 row → Activity dict | ✅ |
| `_parse_sheet4_activities` | parser.py:458 | `(ws) -> list[Activity]` | 시트4 rule — 헤더 해석 후 통합/업체 분기 추출 | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:512 | `(ws) -> list[EquipmentAllocation]` | 시트3 rule — col 2+3+4 + final_flag 조건부 게이트 | ✅ |
| `_DATE_PATTERN` | parser.py:589 | `re.Pattern` | `_YYYYMMDD.(xlsx\|xlsm)` 또는 `_YYMMDD.(xlsx\|xlsm)` | ✅ |
| `_extract_meta` | parser.py:592 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → (report_date ISO, project) | — |
| `parse_daily_report` | parser.py:625 | `(xlsx_path: Path\|str) -> ParsedDailyReport` | **공개 API** 4 시트 통합 (LLM 검증 없음) | ✅ |

### 2.2 parser_post.py (201 LOC) — 본 cycle 코드 변경 0

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_is_real_bp` | parser_post.py:21 | `(value: str\|None) -> bool` | marker (FAB/CUB/소계) drop 판정 | — |
| `filter_marker_rows` | parser_post.py:32 | `(raw_rows, target_key) -> list[dict]` | marker row 제거 | — |
| `pair_bp_summaries` | parser_post.py:44 | `(raw_rows: list[dict]) -> list[dict]` | 시트1 2-row pairing (BP + 회사명) | ✅ |
| `normalize_company` | parser_post.py:92 | `(raw: str\|None) -> str\|None` | ㈜/괄호 제거 | — |
| `split_company_and_zone` | parser_post.py:108 | `(raw: str\|None) -> str\|None` | 회사명 끝 FAB/CUB suffix 제거 | ✅ |
| `extract_zone` | parser_post.py:120 | `(v6: str\|None) -> str\|None` | col 6 (Scope) → 명시적 FAB/CUB 토큰 | ✅ |
| `transform_job_allocations` | parser_post.py:143 | `(raw_rows) -> list[dict]` | JobAllocationRaw → JobAllocation | — |
| `transform_equipment_allocations` | parser_post.py:163 | `(raw_rows) -> list[dict]` | EquipmentAllocationRaw → EquipmentAllocation | — |
| `transform_bp_summaries` | parser_post.py:183 | `(raw_rows) -> list[dict]` | filter + pair + normalize 4-step | ✅ |

### 2.3 parser_llm.py (660 LOC) — DEPRECATED 2026-05-20

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `parse_daily_report_llm` | parser_llm.py:503 | `async (xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport` | DEPRECATED chunk LLM path | ✅ |

### 2.4 parser_node.py (64 LOC) — 본 cycle: async N병렬 multi-file merge

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_merge_reports` | parser_node.py:18 | `(reports: list[ParsedDailyReport]) -> ParsedDailyReport` | N개 리포트 concat (5 리스트 이어붙임, report_date 불일치 시 warning) | ✅ NEW |
| `parser_node` | parser_node.py:40 | `async (state: CPIAState) -> dict[str, Any]` | `input_files` 전체 Semaphore(4) + to_thread 병렬 파싱 → `_merge_reports` → `{"parsed": merged}` | ✅ |

### 2.5 collector.py (70 LOC, legacy CLI)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `CollectorConfig` | collector.py:23 | `dataclass(file_concurrency: int = 4)` | 파일 단위 병렬 환경 | — |
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | 디렉토리 xlsx/xlsm sorted list | — |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | N xlsx Semaphore 병렬 파싱 | — |

### 2.6 collector_node.py (63 LOC, D-12) + filename_parser.py (64 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `collector_node` | collector_node.py:16 | `async (state: CPIAState) -> dict[str, Any]` | input_files[0] 검증 + filename_parser + collector_inbox UPDATE | — |
| `ParsedFilename` | filename_parser.py:15 | `frozen dataclass(kind/project/bp_name/trade/zone/date)` | 첨부 파일명 분해 결과 | — |
| `parse_filename` | filename_parser.py:25 | `(name: str) -> ParsedFilename\|None` | `업체작업일보_` / `통합작업일보_` 정규식 분해 | ✅ |

### 2.7 collector/idle_worker.py (260 LOC) + config.py (68 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `request_shutdown` | idle_worker.py:37 | `() -> None` | `_shutdown` event set | — |
| `_extract_attachments` | idle_worker.py:41 | `(msg: Message) -> list[tuple[str, bytes]]` | email.Message → 첨부 list (RFC 2047 decode) | — |
| `_save_to_input_dir` | idle_worker.py:63 | `(att_name, att_bytes, date_iso, cfg) -> Path` | `data/input/<YYYYMMDD>/` 저장 (uuid suffix on 충돌) | — |
| `_to_dead_letter` | idle_worker.py:81 | `(att_name, att_bytes, cfg) -> None` | 파일명 미일치 → dead_letter | — |
| `run_for_attachment` | idle_worker.py:90 | `async (path, meta, site_id, message_id, cfg) -> None` | semaphore + graph.ainvoke + inbox status | — |
| `_process_one` | idle_worker.py:153 | `async (imap, uid, cfg) -> None` | UNSEEN 메일 1통 dedup + 첨부별 fire-and-forget | — |
| `_drain_new` / `idle_loop` | idle_worker.py:214, 228 | `async (..., cfg) -> None` | IMAP IDLE 유지 + reconnect backoff | — |
| `load_collector_config` | config.py:35 | `(graph_cfg: GraphConfig) -> CollectorConfig` | env 로드 + enabled 시 자격증명 fail-fast | — |

---

## 3. T2 — Issue Cards

### 3.1 `parse_daily_report` — 4 시트 통합 공개 API (LLM 검증 제거)

- **위치**: `pipeline/agents/parser.py:625-664` (40 LOC)
- **시그니처**: `def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport`
- **본 cycle 변경**: LLM 검증 wrapper 호출 제거 (`ac0a8c5`) — 4 시트 추출 후 즉시 `ParsedDailyReport` return. 호출자는 graph 안에서 `parser_node` (async N병렬, `parser_node.py:40`), CLI 에서 `collect_and_parse` (`collector.py:52`).
- **이슈** (deep_dive §7 / §13.1):
  - 2026-05-26 까지 있던 `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` + `_should_verify_llm` (env `CPIA_PARSER_VERIFY_LLM`) 가 **전부 삭제**. 제거 이유: issues 가 stderr 로만 떨어져 DB 적재·운영 알람 없음 → 무력 (실효 0). LLM 1~2 호출이 cycle 당 ~$0.55 + 지연만 추가.
  - grep 확인: parser.py 에 `verify_sheet` / `VERIFY_LLM` / `chat.completions` 0건 (deep_dive §7).
  - 추출 정확도는 demo_inputs 10개 골든 byte-diff 회귀로 대체 보장.
- **설계 의도**:
  - 단일 진입점: pipeline 전체에서 Parser 는 본 함수만 호출 (graph + CLI 양쪽)
  - 결정성 보장: 같은 xlsx → 같은 dict (LLM 0 호출, openpyxl rule + header 매핑만)
  - `read_only=False` 등가: `load_workbook(data_only=True)` — 시트1 의 `merged_cells.ranges` 필요 (parser.py:638-639)
- **대응 패턴**:
  - 입력: xlsx/xlsm 절대 경로 (Path 또는 str)
  - 처리: `load_workbook(data_only=True)` → 4 시트 누락 검증 → `_extract_meta` → 각 시트 rule 파서 호출 (시트1/2/3/4) → 즉시 dict return
  - 출력: `ParsedDailyReport` (BPSummary[] + JobAllocation[] + EquipmentAllocation[] + Activity[] + worker_outputs=[] + report_meta=None)
- **관련**:
  - graph 호출: `pipeline/agents/parser_node.py:54` (`await asyncio.to_thread(parse_daily_report, p)`)
  - CLI 호출: `pipeline/agents/collector.py` (`collect_and_parse` 안에서 to_thread wrap)
  - 후속: `mapper_node` 가 `state["parsed"]` 로 읽음 (merge 후 단일 dict)
- **Suspected related**: `_extract_meta`, `_parse_sheet1_bp_summaries`, `_parse_sheet4_activities`, `parser_node`, `_merge_reports`

---

### 3.2 ★ NEW `_resolve_sheet4_columns` — 시트4 헤더 텍스트 기반 컬럼 해석 (issue#52 컬럼시프트 본체)

- **위치**: `pipeline/agents/parser.py:357-400` (44 LOC)
- **시그니처**: `def _resolve_sheet4_columns(ws, header_rows: tuple[int, int] = (3, 4)) -> dict[str, int]`
- **본 cycle 변경**: **신규 NEW** (`25bb85d`).
- **이슈** (design spec §1, §1.1 인용):
  - issue#52: 업체작업일보를 파이프라인에 넣으니 `parser_activities` 33행이 전부 `trade="UT"` / `company="F02 5F"` / `work_content="M"` 오값으로 저장됨.
  - 근본원인: 업체포맷엔 '업체명' 컬럼이 없어 `col7` 이후가 **1칸 좌측 시프트**. 통합포맷 가정 (`col6=회사명/col8=work_content/col9=unit/col12=today_qty`) 이 업체포맷 실헤더 (`col6=Scope/col7=작업내용/col8=단위/col9=총물량/col11=금일실적`) 와 어긋나 `company←Scope`, `work_content←단위`, `unit←총물량` garbage.
  - 헤더 2-row 스택: row3 (주 라벨 `공종`/`BP사`/`업체명`/`작업내용`/`단위`/`총물량`/`금일실적`/`금일누적`) + row4 (`[A][B][C][D]`·`F%` 마커) 를 함께 읽음.
  - **주의 (회귀 결합)**: `F%` 는 row4 전용 마커라 `h3`/`h4` 를 직접 재테스트. `h = h3 or h4` 가 h3 빈 경우만 h4 살리므로, 이 elif 순서·재테스트 방식을 바꾸면 통합포맷 progress(F%) 누락 → `act=1193` 회귀 깨짐 (주석 경고 parser.py:391-393).
  - 필수 5종 (`trade/bp/work_content/unit/today_qty`) 누락 시 `ParseError(f"시트4 헤더 매핑 실패: {missing}")` (parser.py:398-399).
- **설계 의도**:
  - 하드코딩 컬럼 인덱스 → 헤더명 기반 resolve 로 전환. '업체명' 헤더 존재 여부 (`company_col`) 로 통합/업체 자동 분기 — 두 양식 단일 코드 처리 (design spec §3).
  - `today_qty` 는 `금일실적[C]` (실적), `today_cum` 은 `금일누적[D]` 분리 — 업체포맷에서 today_qty 가 누적 120 아닌 실적 30 으로 정확화.
- **대응 패턴**:
  - 입력: openpyxl ws (시트4)
  - 처리: col 1..max_column 순회 → 각 컬럼의 row3/row4 헤더 `_norm_header` 정규화 → 키워드 매핑 (`공종`→trade, `BP사`→bp, `업체명`→company_col, `대표물량`/`작업내용`→work_content, ...) → 필수 5종 검증
  - 출력: `dict[str, int]` (필드명 → 1-based 컬럼 인덱스). `company_col` / `scope` / `plan_total` / `yesterday_cum` / `today_cum` / `progress` 는 optional
- **관련**:
  - 호출자: `_parse_sheet4_activities` (parser.py:468)
  - 후속: `_build_activity` 가 반환 cols 인덱스로 셀 읽음
  - 테스트: `test_resolve_sheet4_columns_integrated` (test_parser.py:90) — `cols["progress"]==14` 회귀 고정
- **Suspected related**: `_norm_header`, `_build_activity`, `_parse_sheet4_activities`, `_is_bp_code`

---

### 3.3 ★ NEW `_build_activity` — cols 인덱스 기준 단일 row → Activity dict

- **위치**: `pipeline/agents/parser.py:403-455` (53 LOC)
- **시그니처**: `def _build_activity(ws, r: int, cols: dict[str, int], trade, bp_code, company_raw) -> Activity`
- **본 cycle 변경**: **신규 NEW** (`25bb85d`).
- **이슈** (design spec §1.1):
  - 기존 `_parse_sheet4_activities` 가 Activity dict 를 하드코딩 col 번호로 직접 생성하던 것을 분리. issue#52 컬럼시프트 해소를 위해 셀 읽기를 `cols` 인덱스 (헤더 해석 결과) 로만 수행.
  - optional 컬럼 (`plan_total`/`yesterday_cum`/`today_cum`/`progress`/`scope`) 부재 시 None — 업체포맷이 해당 헤더 없어도 안전.
  - `today_qty` default `0.0` (parser.py:431) — 통합포맷 회귀 테스트 (`test_parse_sheet4_today_qty_zero_default`) 호환.
- **설계 의도**:
  - 기존 Activity dict shape·default 를 **그대로 재현**하되 컬럼 위치만 cols 인덱스로 해석 (하드코딩 → 헤더 기반, parser.py:404-407 docstring).
  - Parser 초기값 고정: `worker_source="parsed"`, `assigned_workers=0.0`, `requires_review=False`, mapping 관련 None, `conditions=[]` (parser.py:447-454) — Mapper 가 이후 덮어씀.
  - company 정규화 (`normalize_company(split_company_and_zone(company_raw))`) + zone (`extract_zone(scope)`) 은 시트1/4 공통 정책 (옵션 2).
- **대응 패턴**:
  - 입력: ws + row r + cols 매핑 + ffill 된 (trade, bp_code, company_raw)
  - 처리: cols 키 존재 여부로 optional 컬럼 안전 read → `_safe_num` 수치 coerce → 39 필드 dict 구성
  - 출력: `Activity` dict (Parser 채움 16필드 + 나머지 None/default)
- **관련**:
  - 호출자: `_parse_sheet4_activities` (통합 분기 parser.py:486, 업체 분기 후반)
  - 후속: mapper `map_activity` 가 work_content + cols 수치 소비
- **Suspected related**: `_resolve_sheet4_columns`, `_safe_num`, `extract_zone`, `split_company_and_zone`, `normalize_company`

---

### 3.4 `_parse_sheet4_activities` — 헤더 해석 후 통합/업체 분기 추출

- **위치**: `pipeline/agents/parser.py:458-511` (54 LOC)
- **시그니처**: `def _parse_sheet4_activities(ws) -> list[Activity]`
- **본 cycle 변경**: 하드코딩 col 인덱스 ffill → `_resolve_sheet4_columns` 헤더 해석 + 통합/업체 분기로 전면 전환 (`25bb85d`).
- **이슈** (deep_dive §5.4, design spec §1.1):
  - issue#52 컬럼시프트 garbage — 시트4 가 column shift 본체. 통합/업체 두 포맷이 같은 코드로 흡수돼야 함.
  - `has_company_col = "company_col" in cols` 로 분기:
    - **통합포맷** (company_col 존재): trade ffill + company 는 BP행에 종속 (독립 ffill 아님). `bp` 컬럼 채워지면 같은 행 `company_col` 갱신.
    - **업체포맷** (company_col 없음): BP사 컬럼 코드행 ~ 다음 코드행 group, company = group 내 첫 non-bp 값. trade 는 group 시작 직전까지 누적 ffill.
  - Activity row = `work_content` 채워있는 row 만 → `_build_activity`.
- **설계 의도**:
  - 시트4 는 mapper 의 LLM rerank 입력 + EVM 의 EV 분자 → work_content / today_qty 정확도 중요.
  - 헤더 기반 resolve 로 통합 (act=1193) 과 업체 (act=33) 두 골든 동시 만족 (design spec §6).
- **대응 패턴**:
  - 입력: openpyxl ws (시트4)
  - 처리: `_resolve_sheet4_columns(ws)` → company_col 유무 분기 → ffill stream / group walk → `_build_activity`
  - 출력: `list[Activity]` (통합 1,193 / 업체 33건)
- **관련**:
  - 후속: mapper `map_activity` (`build_embedding_input` + `build_llm_input`)
  - 호출자: `parse_daily_report` (parser.py:651)
- **Suspected related**: `_resolve_sheet4_columns`, `_build_activity`, `_is_bp_code`, `extract_zone`

---

### 3.5 ★ NEW `_BP_PATTERNS` / `_is_bp_code` — BP 코드 다중 패턴 (통합 + 업체)

- **위치**: `_BP_PATTERNS` `pipeline/agents/parser.py:97-100`, `_is_bp_code` `parser.py:103-107`
- **시그니처**: `_BP_PATTERNS: tuple[re.Pattern[str], ...]`, `def _is_bp_code(v: object) -> bool`
- **본 cycle 변경**: 단일 정규식 (`^PH[_\- ]?X[_\- ]?\d+$`) → **2 패턴 tuple** OR 로 확장 (`7d2befc`).
- **이슈** (design spec §1.1, plan Task 2):
  - issue#52 업체포맷 BP 코드 (`M15X_PH4_041`) 가 통합포맷 정규식 (`PH_X-088`) 에 안 맞아 시트2/3/4 group boundary 식별 실패 → `job=0 eq=0` garbage.
  - `_BP_PATTERNS` (parser.py:97-100): 통합 `^PH[_\- ]?X[_\- ]?\d+$` + 업체 `^[A-Za-z][A-Za-z0-9]*_PH\d+_\d+$` 2 정규식. 둘 중 하나라도 match 면 BP 코드.
- **설계 의도**:
  - 헤더명 기반 컬럼 resolve 와 짝 — BP 코드 자체도 양식별로 다르므로 패턴 OR 로 통합/업체 단일 식별.
  - 시트1 (col 5) / 시트2 (col 3) / 시트3 (col 3) / 시트4 (bp 컬럼) group boundary marker 로 공용.
- **대응 패턴**:
  - 입력: 셀 값 (object)
  - 처리: `str(v).strip()` → `_BP_PATTERNS` 각 패턴 `match` (대소문자 무시)
  - 출력: bool
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries` (parser.py:193), `_parse_sheet2_job_allocations` (parser.py:284), `_parse_sheet3_equipment_allocations` (parser.py:526), `_parse_sheet4_activities` (parser.py:490, 497)
  - 테스트: `test_subcon_e2e_golden` (test_parser_subcon.py:21) — `bp_code == "M15X_PH4_041"`
- **Suspected related**: `_parse_sheet2_job_allocations`, `_parse_sheet3_equipment_allocations`, `_parse_sheet4_activities`

---

### 3.6 ★ NEW `_DATE_PATTERN` — 8자리 날짜 + .xlsm 수용 (업체작업일보)

- **위치**: `pipeline/agents/parser.py:589`
- **시그니처**: `_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.(?:xlsx|xlsm)$|_(\d{6})\.(?:xlsx|xlsm)$")`
- **본 cycle 변경**: `.xlsx` 만 → `.xlsx`/`.xlsm` 둘 다 + 8자리 (`YYYYMMDD`) / 6자리 (`YYMMDD`) 양쪽 수용 (`65a8027`).
- **이슈** (design spec §1 표):
  - issue#52: `.xlsm` 3개 (업체작업일보) 가 `parse_daily_report` 진입 즉시 `ParseError` — 기존 `_DATE_PATTERN` 이 8자리+`.xlsm` 미지원 → 정상 추출 0건.
  - `_extract_meta` (parser.py:592) 가 본 패턴으로 파일명에서 date 추출 실패 시 `ParseError(f"파일명에서 날짜 추출 실패: ...")` (parser.py:602).
- **설계 의도**:
  - 업체작업일보가 매크로 포함 `.xlsm` + 8자리 날짜 (`_20250925.xlsm`) 를 쓰므로 확장자·자릿수 모두 일반화.
  - 6자리 (`YYMMDD`) → `20YY-MM-DD`, 8자리 (`YYYYMMDD`) → `YYYY-MM-DD` 변환 (parser.py:596-600).
- **대응 패턴**:
  - 입력: 파일 basename
  - 처리: 두 alternation regex search → group(1) 있으면 8자리, group(4) 있으면 6자리
  - 출력: `_extract_meta` 안에서 ISO date 문자열
- **관련**:
  - 호출자: `_extract_meta` (parser.py:594)
  - 테스트: plan Task 1 — `test_date_pattern_xlsm` (8자리+.xlsm 수용)
- **Suspected related**: `_extract_meta`, `parse_filename` (filename_parser, 별도 prefix 검증)

---

### 3.7 `_parse_sheet2_job_allocations` — Mm01 group + final_flag 조건부 게이트

- **위치**: `pipeline/agents/parser.py:256-339` (84 LOC)
- **시그니처**: `def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]`
- **본 cycle 변경**: col 25='O' 강제 게이트 → **`has_final_flag` 조건부 완화** (`c0699dc`).
- **이슈** (deep_dive §5.2, design spec §1.1):
  - issue#52 업체포맷은 col25 final_flag 'O' 마커가 **전혀 없음** → 통합포맷 가정의 'O' 게이트가 모든 row 를 drop → `job=0` garbage.
  - `has_final_flag = any(ws.cell(r, 25).value == "O" ...)` (parser.py:269) 로 포맷 감지: 'O' 가 하나라도 있으면 통합포맷 → group 시작·직종 row 둘 다 `col 25=='O'` 게이트 유지 (parser.py:282, 312). 'O' 가 전혀 없는 업체포맷은 게이트 완화.
  - group 시작: col 4='Mm01' + col 2 + col 3 채워있음 + col 3 = `_is_bp_code` (+ 통합포맷이면 col 25='O').
  - `_is_admin_job` filter + cross-check (직종 cum.t 합 vs grand_total col 24) 는 silent.
- **설계 의도**:
  - `Mm01` = 매 group 첫 번째 직종 코드 (관리자 코드) → group boundary 결정론적 marker.
  - final_flag 게이트를 **포맷별 조건부**로 만들어 통합 (게이트 유지) / 업체 (게이트 완화) 단일 코드 흡수.
- **대응 패턴**:
  - 입력: openpyxl ws (시트2)
  - 처리: `has_final_flag` 감지 → starts 식별 → group range → 회사명 추출 → 각 row 변환 (`Mm##`→manager_code)
  - 출력: `list[JobAllocation]` (통합 975 / 업체 76건)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:649)
  - mapper 영향: JobAllocation.workers_cum_t → `_prorate_workers_with_mh` 분모
- **Suspected related**: `_is_admin_job`, `_disc_abbrev_to_kr`, `_shift_dict_row`, `_is_bp_code`

---

### 3.8 `_parse_sheet3_equipment_allocations` — col 2+3+4 + final_flag 조건부 게이트

- **위치**: `pipeline/agents/parser.py:512-583` (72 LOC)
- **시그니처**: `def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]`
- **본 cycle 변경**: col 25='O' 강제 게이트 → **`has_final_flag` 조건부 완화** (`c0699dc`, 시트2 와 동일 게이트).
- **이슈** (deep_dive §5.3):
  - 시트2 와 같은 issue#52 final_flag 부재 문제 → 업체포맷 `eq=0` garbage. 시트2 와 동일 `has_final_flag` 게이트 적용.
  - group 시작 row: col 2 (공종) + col 3 (`_is_bp_code`) + col 4 (장비 대분류) 모두 채워있음.
  - **헤더 reprint row 회피**: col 2 에 "장비 투입" 문자열 포함되면 skip (parser.py 안 substring filter).
  - 장비 row = col 4 채워있음 + (통합포맷이면 col 25='O').
- **설계 의도**:
  - 시트3 boundary 는 (공종+BP+장비 대분류) 3-key — `Mm##` 같은 단일 marker 없음.
  - 헤더가 시트 중간에 재출력되는 경우 ("장비 투입") 명시 substring filter 필요.
- **대응 패턴**:
  - 입력: openpyxl ws (시트3)
  - 처리: `has_final_flag` 감지 → starts → group → 장비 row 변환 (equipment_big/mid/spec + 3 시간대)
  - 출력: `list[EquipmentAllocation]` (통합 1,111 / 업체 68건)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:650)
  - 호출자: 없음 — mapper 는 현재 EquipmentAllocation 미사용 (PoC 1차)
- **Suspected related**: `_shift_dict_row`, `_is_bp_code`

---

### 3.9 `_parse_sheet1_bp_summaries` — col 30 merged group boundary

- **위치**: `pipeline/agents/parser.py:128-245` (118 LOC)
- **시그니처**: `def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]`
- **본 cycle 변경**: 코드 변경 없음 (`_is_bp_code` 다중 패턴화 간접 영향만 — col 5 BP 코드 식별이 업체포맷도 매칭).
- **이슈** (deep_dive §5.1):
  - col 30 (금일 투입 그룹 Total) merged range 또는 단독 row 가 group boundary.
  - BP 코드 row + 회사명 row 인접 pair (옵션 2). company 정규화 = `split_company_and_zone` + `normalize_company`. zone = `extract_zone(col 6)`.
  - sub-section 합계 row skip (bp+company 둘 다 None) + 빈 placeholder skip (company None & cum=0 & incr=0).
  - solo merged + 다음 row 흡수 (회사명 단독 row).
  - **주의**: ws 는 `read_only=False` 등가 (`merged_cells.ranges` 필요).
  - 기대 산출량: 통합 작업일보 1건 ≈ 99 그룹 → 99 BPSummary.
- **설계 의도**:
  - 시트1 grouping 은 col 30 (그룹 Total) merged 범위 기준 — col 5 (BP 코드/회사명) 자체로는 boundary 불명확.
  - 시트1 출력은 mapper 의 `auto_bp_zone_match` deterministic input → zone 정확도 중요.
- **대응 패턴**:
  - 입력: openpyxl ws (시트1)
  - 처리: col 30 merged_cells.ranges 수집 → solo row 식별 → group range 결정 (solo+next 흡수) → 각 group → BPSummary 변환 (`extract_zone` + 4 시간대 group sum)
  - 출력: `list[BPSummary]` (99건 기대)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:648)
  - mapper 영향: BPSummary.zone → `resolve_wa` step 1 (`auto_bp_zone_match`) input
- **Suspected related**: `extract_zone`, `split_company_and_zone`, `normalize_company`, `_is_bp_code`

---

### 3.10 ★ NEW `parser_node` — async N병렬 multi-file merge

- **위치**: `pipeline/agents/parser_node.py:40-64` (25 LOC)
- **시그니처**: `async def parser_node(state: CPIAState) -> dict[str, Any]`
- **본 cycle 변경**: 옛 25 LOC sync 1줄 wrapper (`input_files[0]` 1개만 파싱) → **64 LOC async N병렬 concat merge** (`a8d17e4`).
- **이슈** (deep_dive §9.3):
  - multi-file (N 업체파일) 통합 필요 — graph 가 1 run 으로 optimizer 까지 통합 검토 (PoC: 업체별 일보 10개 동시 적재).
  - sync `parse_daily_report` 를 그대로 호출하면 FastAPI 이벤트 루프 block → mapper~ 진행 중 게이지 polling 응답 안 됨.
  - 별도 merge 노드 없이 parser_node 가 concat 책임 (graph 노드 수 절감).
- **설계 의도**:
  - `state["input_files"]` **전체**를 `asyncio.Semaphore(4)` + `asyncio.to_thread(parse_daily_report, p)` 로 `gather` — sync parse 를 thread 로 off-load 해 이벤트 루프 block 회피 (parser_node.py:43-45 docstring).
  - `_merge_reports` 로 N개 → 1 concat → `{"parsed": merged}` (별도 merge 노드 불필요).
  - internal parser.py 변경 0 — 1 첨부 = 1 ParsedDailyReport, merge 는 parser_node 책임.
  - graph 에서 `_parser_p` async wrapper 가 `await _parser(state)` (parser_node 가 async 이므로 await 필수, graph.py:532-535).
- **대응 패턴**:
  - 입력: `state["input_files"]` (List[str], 전체 사용) — 비어있으면 `RuntimeError`
  - 처리: Path 변환 → Semaphore(4) + to_thread gather → `_merge_reports`
  - 출력: `{"parsed": merged}` — partial state update (단일 merged dict)
- **관련**:
  - 호출자: `pipeline/graph.py` `graph.add_node("parser", _parser_p)`
  - 직전 노드: `collector_node` (collector_node.py:16) / 직후 노드: `mapper_node` (`state["parsed"]` 소비)
  - 테스트: `test_parser_node.py`
- **Suspected related**: `_merge_reports`, `parse_daily_report`, `collector_node`, `mapper_node`

---

### 3.11 ★ NEW `_merge_reports` — N개 ParsedDailyReport concat

- **위치**: `pipeline/agents/parser_node.py:18-37` (20 LOC)
- **시그니처**: `def _merge_reports(reports: list[ParsedDailyReport]) -> ParsedDailyReport`
- **본 cycle 변경**: **신규 NEW** (`a8d17e4`).
- **이슈** (deep_dive §9.4):
  - multi-file 통합 시 N개 리포트를 1 ParsedDailyReport 로 합쳐야 mapper 가 단일 `state["parsed"]` 로 읽음 (state-key drift fix `6b9db7c` 호환).
  - 각 업체가 서로 다른 작업을 한다는 전제 → 5 리스트 (bp_summaries / job_allocations / equipment_allocations / activities / worker_outputs) 단순 이어붙임.
  - `report_date` 는 모든 파일 동일 가정 — 불일치 시 `log.warning("parser_node merge: report_date 불일치 ...")` (parser_node.py:27) 만 남기고 첫 파일 날짜 사용.
- **설계 의도**:
  - merge 를 별도 graph 노드 아닌 parser_node 내부 helper 로 — 노드 수 절감 + 결정론적 concat.
  - `report_meta` 는 첫 업체 것 (site 대표).
  - 10 업체파일 → 통합 `activities=330` (PoC graph multi-file).
- **대응 패턴**:
  - 입력: `list[ParsedDailyReport]` (N개)
  - 처리: base = reports[0] → 5 리스트 nested comprehension concat → report_date 불일치 warning
  - 출력: 단일 통합 `ParsedDailyReport`
- **관련**:
  - 호출자: `parser_node` (parser_node.py:57)
  - 후속: `{"parsed": merged}` → mapper_node
- **Suspected related**: `parser_node`, `parse_daily_report`

---

### 3.12 `parse_filename` — `업체작업일보_` / `통합작업일보_` 정규식 분해

- **위치**: `pipeline/collector/filename_parser.py:25-64` (40 LOC)
- **시그니처**: `def parse_filename(name: str) -> ParsedFilename | None`
- **본 cycle 변경**: 코드 변경 없음 (D-12 신설 유지).
- **이슈**:
  - prefix 2종 hardcoded: `업체작업일보_` 또는 `통합작업일보_` (filename_parser.py:28) — 그 외 모두 None → caller `_to_dead_letter` 격리.
  - date 토큰: 6자리 (`YYMMDD`) 또는 8자리 (`YYYYMMDD`), 그 외 None.
  - 통합 모드: bp_name/trade/zone 모두 None. 업체별 모드: 끝 4 토큰 분해.
- **설계 의도**:
  - 메일 첨부 파일명 규약을 **graph 진입 전** 검증 — 잘못된 파일이 graph 안으로 들어가지 않게 게이트.
  - dataclass(frozen=True) — 결정적 hashable 결과.
- **대응 패턴**:
  - 입력: 파일 basename
  - 처리: stem split('_') → prefix 검증 → date 형식 검증 → kind 별 토큰 분해
  - 출력: `ParsedFilename(kind, project, bp_name, trade, zone, date)` 또는 None
- **관련**:
  - 호출자: `collector_node` (검증), `idle_worker._process_one`
  - 후속: `_save_to_input_dir` 가 date 로 `data/input/<YYYYMMDD>/` 디렉토리 생성
  - 참고: parser 의 `_DATE_PATTERN` (parser.py:589) 와 별개 — parser 는 .xlsm/.xlsx 확장자 포함 패턴, filename_parser 는 prefix + 토큰 분해
- **Suspected related**: `collector_node`, `_to_dead_letter`, `_save_to_input_dir`, `_DATE_PATTERN`

---

### 3.13 `extract_zone` — col 6 (Scope) 옵션 2 보수 매칭

- **위치**: `pipeline/agents/parser_post.py:120-140` (21 LOC)
- **시그니처**: `def extract_zone(v6: str | None) -> str | None`
- **본 cycle 변경**: 코드 변경 없음.
- **이슈** (deep_dive §6.2):
  - 옵션 2 (spec §2.1) 보수 매칭: 단일 토큰 'FAB'/'CUB' → 결정, 시작 토큰 ('FAB 전구간') → 결정, 양쪽 ('FAB/CUB') / 텍스트 중간 ('M15X FAB F04') → None (모호).
- **설계 의도**:
  - 시트1 BPSummary.zone + 시트4 Activity.zone 의 deterministic 활용 — mapper `auto_bp_zone_match` (step 1) input.
  - 모호 케이스 명시적 None → mapper step 2 (`auto_llm_rerank`) fallback.
- **대응 패턴**:
  - 입력: col 6 (Scope) raw 문자열
  - 처리: regex 5단계 (양쪽 / 단일 토큰 / 시작 토큰 / 텍스트 중간 / 기타)
  - 출력: "FAB" / "CUB" / None
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries` (parser.py:211), `_build_activity` (parser.py:419)
  - 페어: `split_company_and_zone` (parser_post.py:108)
- **Suspected related**: `split_company_and_zone`, mapper `auto_bp_zone_match`

---

### 3.14 `split_company_and_zone` — 회사명 끝 FAB/CUB suffix 분리

- **위치**: `pipeline/agents/parser_post.py:108-117` (10 LOC)
- **시그니처**: `def split_company_and_zone(raw: str | None) -> str | None`
- **본 cycle 변경**: 코드 변경 없음.
- **이슈** (deep_dive §6.1):
  - 옵션 2 (scope ≠ wa): suffix 는 회사명 정규화에만 사용, zone 정보 반환 X.
  - 예: '에스비테크CUB' → '에스비테크', '광건티엔씨FAB(수장2)' → '광건티엔씨'.
- **설계 의도**:
  - 회사명 끝 FAB/CUB suffix 가 mapper 정확 일치 SQL (`fetch_bp_candidates`) mismatch 유발 → 정규화 단계에서 제거.
  - zone 정보는 명시적 col 6 (`extract_zone`) 만 신뢰.
- **대응 패턴**:
  - 입력: raw company 문자열
  - 처리: `normalize_company` (㈜ / 괄호 제거) → `_TRAILING_FABCUB_RE` 제거
  - 출력: str 또는 None
- **관련**:
  - 호출자: 시트1/2/3 group 회사명 추출 + `_build_activity` (parser.py:418)
  - 페어: `extract_zone` (parser_post.py:120)
- **Suspected related**: `normalize_company`, mapper `fetch_bp_candidates`

---

### 3.15 `transform_bp_summaries` — filter + pair + normalize 4-step (LLM path 정제)

- **위치**: `pipeline/agents/parser_post.py:183-201` (19 LOC)
- **시그니처**: `def transform_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **본 cycle 변경**: 코드 변경 없음.
- **이슈**:
  - 4-step: `filter_marker_rows` → `pair_bp_summaries` → `normalize_company` → company OR bp_code 있어야 통과.
  - `83b61ec` (이전 cycle) `today_incr_total` 필드 누락 fix (mapper KeyError 회피).
  - 현재 rule path 는 raw 단계 없이 직접 entity 생성 (parser.py `_parse_sheet1_bp_summaries`) — 본 함수는 **deprecated LLM path 잔존용**.
- **설계 의도**:
  - LLM/rule output 공통 정제 — rule 추출 본문 raw 상태로 두고 정제 분리 (단위 테스트 가능성).
  - LLM path 회귀 시 재활용 가능.
- **대응 패턴**:
  - 입력: raw_rows (BPSummaryRaw, LLM 추출 형식)
  - 처리: 4-step 파이프라인
  - 출력: 정제된 BPSummary list
- **관련**:
  - 현재 호출자: `parser_llm.py` 만 (DEPRECATED)
  - 후속: mapper `_prorate_workers_with_mh` (`today_incr_total`) + `build_bp_context`
- **Suspected related**: `pair_bp_summaries`, `filter_marker_rows`

---

### 3.16 `pair_bp_summaries` — 2-row pairing (BP 코드 + 회사명)

- **위치**: `pipeline/agents/parser_post.py:44-89` (46 LOC)
- **시그니처**: `def pair_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **본 cycle 변경**: 코드 변경 없음.
- **이슈**:
  - BP 코드 row (is_bp_code=true) + 다음 회사명 row (is_korean_company=true) + 같은 zone/disc_abbrev → 1 BPSummary 머지. 그 외 each row = 1 BPSummary.
  - rule path 는 group 안에서 직접 처리 — 본 함수는 LLM path 만 사용.
- **설계 의도**:
  - 시트1 2-row 그룹 (BP 코드 + 한글 회사명) 패턴이 LLM output 에서 발생 → 정규화 단계에서 머지.
  - 정규성 기준: zone + disc_abbrev 일치 (PoC 3사 검증 통과).
- **대응 패턴**: while-i loop, current + next row 패턴 매칭 → 머지 또는 single 유지
- **관련**: 호출자 `transform_bp_summaries`
- **Suspected related**: `transform_bp_summaries`, `filter_marker_rows`

---

### 3.17 `parse_daily_report_llm` — DEPRECATED 2026-05-20 (현 cycle 잔존)

- **위치**: `pipeline/agents/parser_llm.py:503` (660 LOC 파일 전체)
- **시그니처**: `async def parse_daily_report_llm(xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport`
- **본 cycle 변경**: 코드 변경 없음. graph entry (`parser_node`) 에서 호출되지 않음.
- **이슈** (deep_dive §8):
  - 파일 헤더: chunk LLM parsing 으로 ParsedDailyReport 생성했으나 5/20 부터 `parse_daily_report` (rule-based) 로 대체됨.
  - 대체 이유: chunk LLM 270 호출 → 4-5 분 / cycle, ~$3 / cycle vs rule → ~5 초 / cycle, LLM 0 호출 (본 cycle LLM 검증 wrapper 도 제거됨).
  - env flag `CPIA_PARSER=llm` graph entry 분기 — **미구현** (현재 caller 직접 수정으로만 회귀 가능).
- **설계 의도 (잔존)**:
  - **fallback 경로**: rule path 가 새 양식에서 실패하는 비상 경로 (POC 외 사이트 양식 지원 시).
  - `_sheet_to_payload` 재사용: parser_post 의 transform_* 와 정합.
  - chunked LLM call retry 패턴 (`_llm_extract_sync` parser_llm.py:389): 4 retry trigger — 향후 LLM 보조 parse 재도입 시 참조 가능 (현재 parser.py 의 LLM 검증 wrapper 는 제거됨).
- **대응 패턴**: 현재 호출 X — caller (collector.py, run_one_cycle.py) 가 `parse_daily_report` (rule) 로 교체됨 (`888e927`).
- **관련**: 페어 `parse_daily_report` (parser.py:625)
- **제거 backlog**: issue #N8 — env flag deprecation 후 다음 cycle 제거.
- **Suspected related**: `transform_bp_summaries`, `transform_job_allocations`, `transform_equipment_allocations`

---

## 4. 변경 사항 정리 (1ba783f → d317be9, 본 cycle)

| Commit | 변경 | 영향 파일 |
|---|---|---|
| `65a8027` | fix(parser): `_DATE_PATTERN` 이 8자리 날짜+.xlsm 조합 수용 (업체작업일보) | `pipeline/agents/parser.py` |
| `7d2befc` | feat(parser): BP코드 다중 패턴 (`PH_X-NNN` + `M15X_PHn_NNN`) — `_BP_PATTERNS` 2종 | `pipeline/agents/parser.py` |
| `25bb85d` | feat(parser): 시트4 헤더 기반 컬럼 해석 (`_resolve_sheet4_columns` / `_build_activity`) — column shift 해소 | `pipeline/agents/parser.py` |
| `c0699dc` | feat(parser): 시트2/3 final_flag 조건부 완화 (`has_final_flag` — 'O' 없는 업체포맷만) | `pipeline/agents/parser.py` |
| `ac0a8c5` | feat(parser): 업체포맷 E2E 통합 + **무력 LLM 검증 제거** (demo_inputs 10개 골든) | `pipeline/agents/parser.py` |
| `a8d17e4` | feat(graph): multi-file async parser merge + hil_1 resume falsy-fix | `pipeline/agents/parser_node.py`, `pipeline/graph.py` |
| `d317be9` | Merge branch 'A_Track' (2026-06-01) | — |

**골든**: 통합 byte-identical (`act=1193 / bp=99 / job=975 / equip=1111`) + 업체 골든 (`act=33 / bp=1 / job=76 / equip=68`).

baseline 이전 흡수 commit (이전 design_intent_parser.md 에 이미 반영, 본 cycle 변경 아님):
- D-12: `55cad90` (collector_node + parser_node 분리), `6b9db7c` (state-key drift `parsed_reports`→`parsed`)
- `702ac06`, `05426ad`, `ae144a2`, `83b32f3` (4 시트 refactor)
- `15c58bf` (`split_company_and_zone` / `extract_zone` 신설)
- `888e927` (caller `parser_llm` → `parse_daily_report` 교체)
- `83b61ec` (`transform_bp_summaries` `today_incr_total` fix)

---

## 5. 이슈 표 (deep_dive §14 동기화)

| # | 이슈 | 위치 | 영향 | 상태 |
|---:|---|---|---|---|
| 1 | ~~`parser_warning` PG 영속화~~ — LLM 검증 wrapper 제거로 무효화 | (parser.py) | LLM 검증 issues 자체가 사라짐 | resolved (`ac0a8c5`) |
| 2 | `parser_llm.py` 660 LOC DEPRECATED 잔존 — env flag 회귀 path 미구현 | parser_llm.py | caller 직접 수정으로만 회귀 가능 | backlog (issue #N8) |
| 3 | `BPSummary.disc_abbrev` 시트1 추출 안 됨 | parser.py:231 | 항상 None (시트1 col 에 공종 없음) → mapper 의존 안 함 | by design |
| 4 | `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` 항상 None | parser.py:441-446 | Master List 1:N 제약 — Mapper 가 채워야 함 | by design (PoC) |
| 5 | `_is_total_row` / `_ffill` 미참조 (dead code) | parser.py:64, 72 | 헤더기반 전환 후 호출처 없음 — 제거 후보 | minor (cleanup) |
| 6 | 시트4 헤더 매핑이 `F%` elif 순서·재테스트에 결합 | parser.py:391-395 | 순서 바꾸면 통합 progress 누락 → act=1193 회귀 깨짐 | by design (주석 경고) |
| 7 | 시트2 raw company suffix (`창원기전CUB(22.9kV)`) zone 활용 미구현 | parser.py:256 | 시트2 group 의 zone 정보 손실 | spec §8 |
| 8 | `BPSummary.work_text_today` BP 별 분리 안 됨 — group 안 `\|` join | parser.py:234-236 | BP-zone 분리 후에도 work_text 통합 | spec §8 |
| 9 | 다른 사이트 일보 양식 (시트명·col 좌표 다름) 미지원 | parser.py 전체 | 시트4 만 헤더기반, 시트1/2/3 은 여전히 col 좌표 hardcoded | spec §8 |
| 10 | `_merge_reports` report_date 불일치 시 warning 만 (첫 파일 날짜 사용) | parser_node.py:25-27 | 서로 다른 날짜 파일 섞이면 잘못된 date 로 적재 | by design (PoC 동일날짜 가정) |
| 11 | `data_only=True` + 시트1 merged_cells.ranges 필요 (read_only 불가) | parser.py:638-639 | 큰 xlsx 메모리 risk | 현재 PoC 양식 OK |
| 12 | `Mm01` 패턴이 시트2/3 group boundary — 다른 코드 체계 호환 X | parser.py:275 | "Mm01" 문자열 hardcoded | by design (POC 양식) |
| 13 | `_extract_meta` project 추출 — 시트1 첫 3 row 의 "M15X/IBL/PJT" substring 매칭 | parser.py:605-614 | 다른 사이트명 미지원 (실패 시 파일명 fallback) | spec §8 |
| 14 | `parse_filename` 의 통합/업체별 prefix hardcoded | filename_parser.py:28 | 그 외 파일명 dead_letter 행 | by design |
| 15 | `idle_worker._GRAPH_SEM = Semaphore(2)` — 한 listener 가 동시 graph 2개만 | idle_worker.py:34 | 첨부 N개 동시 도착 시 직렬화 | env `CPIA_COLLECTOR_CONCURRENCY` 로 조정 가능 |

---

## 6. 검증 status (deep_dive §15 동기화)

| Phase | 항목 | 상태 |
|---|---|---|
| V1 (5/20) | 4 시트 rule cross-check (시트2 0 warnings) | 완료 |
| V2 (5/20) | Mapper 5 case simulation (`auto_bp_zone_match` 60% deterministic) | 완료 |
| D-12 | `collector_node` / `parser_node` 분리 + state-key drift fix | 완료 (`55cad90`, `6b9db7c`) |
| 06-01 | header-based 다포맷 7-task (issue#52 컬럼시프트 garbage 해소) | 완료 (`65a8027`~`ac0a8c5`) — 통합 byte-identical + 업체 골든 33/1/76/68 |
| 06-01 | parser_node async N병렬 multi-file merge | 완료 (`a8d17e4`) — 10 업체 → activities 330 |
| 06-01 test | `test_parser_subcon.py` 39 LOC + `test_parser.py` 갱신 | 완료 |
| V3 | 146 case full simulation (POC 3사) | pending |
| V5 | 10 업체 POC 전체 cycle + Reports UI 12 정량 기준 | pending |

---

## 7. 미해결 / Backlog (issue # 매핑)

- **issue #N8**: `parser_llm.py` 660 LOC 제거 — env flag `CPIA_PARSER=llm` 회귀 path 구현 또는 완전 제거
- **issue #4**: `Activity` 의 `wbs_activity_id` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 필드 Parser 단계 항상 None — Mapper Master List 1:N 제약 해소 후 채우기
- **issue #5**: `_is_total_row` / `_ffill` dead code — 헤더기반 전환 후 호출처 없음, cleanup 후보
- **issue #6**: 시트4 헤더 매핑이 `F%` elif 순서·재테스트에 결합 — 변경 시 act=1193 회귀 (주석 경고로만 방어)
- **issue #7**: 시트2 raw company suffix zone 활용
- **issue #8**: `BPSummary.work_text_today` BP 단위 분리 검토
- **issue #9**: 다른 사이트 일보 양식 지원 (시트1/2/3 col 좌표 hardcoded — 시트4 만 헤더기반)
- **issue #10**: `_merge_reports` report_date 불일치 robust 처리 (현재 첫 파일 날짜 사용 + warning)
- **issue #12**: `Mm01` 패턴 hardcoded — 다른 코드 체계 일보 호환
- **issue #15**: `Semaphore(2)` bottleneck — 첨부 N개 동시 도착 시 throughput 한계 (env tuning 가능)

---

*최종 수정: 2026-06-01 — parser 헤더기반 다포맷 7-task 흡수 (issue#52 업체작업일보 컬럼시프트 garbage 해소): 시트4 `_resolve_sheet4_columns` / `_build_activity` 헤더 기반 컬럼 해석, `_BP_PATTERNS` BP 코드 다중 패턴, 시트2/3 `has_final_flag` 조건부 게이트, `_DATE_PATTERN` .xlsm+8자리 수용, 무력 LLM 검증 wrapper 완전 제거. parser_node 25 LOC sync wrapper → async N병렬 `_merge_reports` concat. baseline `1ba783f → d317be9`. T2 카드 5개 신규 (`_resolve_sheet4_columns`, `_build_activity`, `_BP_PATTERNS`/`_is_bp_code`, `_DATE_PATTERN`, `_merge_reports`) + parser_node 갱신.*
*이전 수정: 2026-05-26 — D-12 graph 진입점 분리 (`collector_node` + `parser_node`) + IMAP IDLE listener (`idle_worker`) 구조 흡수. parser 본체 코드 변경 0.*
