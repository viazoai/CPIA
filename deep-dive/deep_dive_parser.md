# Deep Dive — Parser Subsystem

- **Generated**: 2026-06-01 (d317be9 — parser 헤더기반 다포맷 7-task + parser_node async multi-file merge)
- **Git baseline → HEAD**: `1ba783f` (2026-05-26 A_Track) → `d317be9` (2026-06-01 Merge A_Track)
- **Pair docs**:
  - `./architecture_overview.md` (시스템 다이어그램)
  - `./design-intent/design_intent_parser.md` (T1/T2 카드)
- **Range**:
  - `pipeline/agents/parser.py` (664 LOC, header-based 다포맷 — LLM 검증 제거)
  - `pipeline/agents/parser_post.py` (201 LOC)
  - `pipeline/agents/parser_llm.py` (660 LOC, **DEPRECATED 2026-05-20**)
  - `pipeline/agents/parser_node.py` (64 LOC, async N병렬 multi-file merge)
  - `pipeline/agents/collector.py` (70 LOC, legacy)
  - `pipeline/agents/collector_node.py` (63 LOC, D-12 신규)
  - `pipeline/collector/filename_parser.py` (64 LOC)
  - `pipeline/collector/idle_worker.py` (260 LOC)
  - `pipeline/collector/config.py` (68 LOC)

---

## 1. Overview

Parser 서브시스템은 작업일보 xlsx 1개를 **4 시트** (`1.출력인원 현황` / `2.직종별 인원현황` / `3.장비현황` / `4.물량`) 통합 `ParsedDailyReport` (TypedDict) 로 변환한다. 핵심 entry 는 `parse_daily_report(xlsx_path)` 1개 — 동기 함수, openpyxl rule-based 추출만 (~5초 / cycle / 첨부 1건). 2026-06-01 부터 LLM 검증 wrapper 는 **완전 제거** (무력 — issues 가 stderr 로만 떨어져 운영 가치 없고 cycle 시간만 늘림).

핵심 아이디어 4 가지:

1. **rule-based + header-based 다포맷**: openpyxl 으로 셀 좌표 + 정규식 + merged range 분석. 결정성 보장. 같은 xlsx → 같은 output. 시트4 는 컬럼을 **헤더 텍스트** (`_resolve_sheet4_columns`) 로 해석해 통합/업체 두 포맷의 컬럼 시프트를 흡수 (issue#52 garbage 해소).
2. **BP 코드 다중 패턴** (`_BP_PATTERNS` parser.py:97): 통합포맷 `PH_X-088` + 업체포맷 `M15X_PH4_041` 두 정규식 OR.
3. **시트2/3 final_flag 조건부 게이트**: col25 에 `O` 가 하나라도 있으면 통합포맷으로 보고 `final_flag=='O'` 게이트 유지, 'O' 가 전혀 없는 업체포맷은 게이트 완화 (`has_final_flag` 분기).
4. **parser_post 공통 정제** (`split_company_and_zone` / `extract_zone` / `pair_bp_summaries` / `transform_bp_summaries`): rule path 와 deprecated LLM path 양쪽이 같은 정제 pipeline 통과.

`parse_daily_report` 는 graph 의 `parser_node` (async N병렬 multi-file merge) 가 `state["input_files"]` **전체**에 대해 호출 → `_merge_reports` 로 1 통합 `ParsedDailyReport` 로 concat. 그 앞 단계는 `collector_node` (D-12) — `state["input_files"][0]` 경로 검증 + `parse_filename` 으로 (bp_name / date / project) 분해 + `collector_inbox` UPDATE.

본 cycle 의 주요 변경 (baseline `1ba783f` → HEAD `d317be9`) 는 **parser 헤더기반 다포맷 7-task + parser_node async multi-file merge**:
- `65a8027 fix(parser): _DATE_PATTERN 이 8자리 날짜+.xlsm 조합 수용 (업체작업일보)`
- `7d2befc feat(parser): BP코드 다중 패턴 (PH_X-NNN + M15X_PHn_NNN)`
- `25bb85d feat(parser): 시트4 헤더 기반 컬럼 해석 — column shift 해소 (통합+업체)`
- `c0699dc feat(parser): 시트2/3 final_flag 조건부 완화 ('O' 없는 업체포맷만)`
- `ac0a8c5 feat(parser): 업체포맷 E2E 통합 + 무력 LLM 검증 제거 (demo_inputs 10개 골든)`
- `a8d17e4 feat(graph): multi-file async parser merge + hil_1 resume falsy-fix`
- 골든 (통합 byte-identical / 업체 골든 고정): 통합 `act=1193 / bp_summaries=99 / job=975 / equip=1111`, 업체 `act=33 / bp=1 / job=76 / equip=68`.

---

## 2. 파일 목록 + LOC

| 파일 | LOC | 역할 | 상태 |
|---|---:|---|---|
| `pipeline/agents/parser.py` | 664 | 4 시트 rule-based + header-based 다포맷 추출 + 공개 API `parse_daily_report` (LLM 검증 제거됨) | active |
| `pipeline/agents/parser_post.py` | 201 | 회사명/zone 정규화 + BP 코드 pair + raw → entity transform | active |
| `pipeline/agents/parser_llm.py` | 660 | LLM chunk parsing 기반 `parse_daily_report_llm` (async) | **DEPRECATED 2026-05-20** — 코드 보존 |
| `pipeline/agents/parser_node.py` | 64 | graph 노드 — `input_files` 전체 async N병렬 파싱 + `_merge_reports` concat | active |
| `pipeline/agents/collector.py` | 70 | legacy: `discover_daily_reports` + `collect_and_parse` (asyncio.Semaphore 4 병렬) | active (CLI / run_one_cycle 만) |
| `pipeline/agents/collector_node.py` | 63 | graph 진입 노드 — `input_files[0]` 검증 + filename_parser + collector_inbox UPDATE | active (D-12) |
| `pipeline/collector/filename_parser.py` | 64 | 첨부 파일명 → `ParsedFilename(kind/project/bp_name/trade/zone/date)` | active |
| `pipeline/collector/idle_worker.py` | 260 | IMAP IDLE listener — UNSEEN fetch → 첨부 추출 → `collector_inbox` INSERT → `run_for_attachment` fire-and-forget | active (FastAPI startup task) |
| `pipeline/collector/config.py` | 68 | `CollectorConfig` env 로드 + fail-fast 자격증명 검증 | active |

**합계**: 9 파일 / 2,114 LOC.

---

## 3. 4 시트 추출 흐름 다이어그램

```
                            +---------------------+
                            |  IMAP IDLE 메일 도착 |
                            |  (idle_worker.py)   |
                            +----------+----------+
                                       | RFC822 fetch + 첨부 추출
                                       v
                        +--------------+----------------+
                        |  _save_to_input_dir            |
                        |  data/input/<YYYYMMDD>/*.xlsx  |
                        |  + insert_collector_inbox      |
                        +--------------+----------------+
                                       | create_task(run_for_attachment)
                                       v
                        +--------------+----------------+
                        |  build_graph().ainvoke(state) |
                        |  state.input_files = [p1..pN] |
                        +--------------+----------------+
                                       | START -> collector
                                       v
+--------------------------------+   +----------------------------------+
|  collector_node                |   |  parser_node (async N병렬 merge) |
|  (collector_node.py:16)        |-->|  (parser_node.py:40)             |
|  - path exists 검증            |   |  - Semaphore(4) + to_thread      |
|  - parse_filename(name)        |   |  - gather(parse_daily_report xN) |
|  - collector_inbox UPDATE(run) |   |  - _merge_reports -> 1 concat    |
|  - return {bp_name,date,project}|  |  - return {"parsed": merged}     |
+--------------------------------+   +--------------+-------------------+
                                                    | (파일별 N회)
                                                    v
                                  +-----------------+-----------------+
                                  |  parse_daily_report (parser.py:625)|
                                  |  openpyxl.load_workbook(data_only) |
                                  |  required_sheets 4종 검증           |
                                  |  _extract_meta -> (date, project)  |
                                  +-----------------+------------------+
                                                    |
              +-------------------+-----------------+-----------------+-------------------+
              v                   v                                   v                   v
   +----------+-----+   +--------+--------+                   +------+-------+   +------+--------+
   | 시트1 BPSummary |   | 시트2 JobAlloc  |                   | 시트3 EqAlloc |   | 시트4 Act      |
   | parser.py:128  |   | parser.py:256   |                   | parser.py:512|   | parser.py:458  |
   | col 30 merged  |   | col 4='Mm01' +  |                   | col 2+3+4 +  |   | _resolve_      |
   | group boundary |   | final_flag 게이트|                  | final_flag   |   |   sheet4_cols  |
   | + BP/회사 pair |   | (조건부 'O')    |                   | (조건부 'O') |   | (헤더 기반)    |
   +-------+--------+   +--------+--------+                   +------+-------+   +------+--------+
           |                     |                                   |                  |
           v                     v                                   v                  v
   +-------+--------+   +--------+--------+                   +------+-------+   +------+--------+
   |split_company_  |   | _shift_dict_row|                   |_shift_dict_  |   | _build_      |
   |  and_zone +    |   |  yest/incr/cum |                   |  row x3      |   |   activity   |
   |extract_zone +  |   |  (3 시간대)    |                   |              |   | (cols 인덱스)|
   |normalize_      |   |                |                   |              |   | extract_zone |
   |  company       |   |                |                   |              |   |              |
   +-------+--------+   +--------+--------+                   +------+-------+   +------+--------+
           |                     |                                   |                  |
           +---------------------+--------+------------------+-------+------------------+
                                          |
                                          v
                              +-----------+------------+
                              | ParsedDailyReport dict |
                              | {report_date, project, |
                              |  bp_summaries[],       |
                              |  job_allocations[],    |
                              |  equipment_allocations,|
                              |  activities[],         |
                              |  worker_outputs=[],    |
                              |  report_meta=None}     |
                              +-----------+------------+
                                          |  (LLM 검증 wrapper 제거 — 즉시 return)
                                          v
                              +-----------+------------+
                              | return ParsedDailyReport|
                              +-----------+------------+
                                          |
                                          v  parser_node 가 N개 모아 _merge_reports
                              +-----------+------------+
                              | merged ParsedDailyReport|
                              | (parsed → state["parsed"])
                              +-----------+------------+
                                          |
                                          v
                              +-----------+------------+
                              |  mapper_node           |
                              |  state["parsed"] 사용  |
                              +------------------------+
```

---

## 4. Public + Private 함수 전수 표

### parser.py (664 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `ParseError` | parser.py:30 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 |
| `_normalize_unit` | parser.py:47 | `(s: str) -> str` | 단위 대소문자 통일 (M2→m2) |
| `_disc_abbrev_to_kr` | parser.py:52 | `(abbrev: str\|None) -> str\|None` | 공종 약자 → 한글 (AR→건축 등) |
| `_is_admin_job` | parser.py:59 | `(job_type: str) -> bool` | 관리자 직종 noise 판정 (BP소장 등) |
| `_is_total_row` | parser.py:64 | `(row: tuple) -> bool` | 시트2 합계 row 판정 (현재 미참조 — dead) |
| `_ffill` | parser.py:72 | `(rows, header_end, fill_cols) -> list[tuple[int, list]]` | 헤더 이후 row forward-fill (현재 미참조 — dead) |
| `_BP_PATTERNS` | parser.py:97 | `tuple[re.Pattern, ...]` | 통합 `PH_X-NNN` + 업체 `M15X_PHn_NNN` 2 정규식 |
| `_is_bp_code` | parser.py:103 | `(v: object) -> bool` | `_BP_PATTERNS` 중 하나라도 match |
| `_safe_int` | parser.py:110 | `(v: object) -> int` | None / 비정수 → 0 |
| `_shift_dict_sum` | parser.py:119 | `(ws, start, end, col_start) -> TimeShiftCounts` | 6 칸 시간대 group 합 (시트1) |
| `_parse_sheet1_bp_summaries` | parser.py:128 | `(ws) -> list[BPSummary]` | 시트1 — col 30 merged group boundary |
| `_shift_dict_row` | parser.py:248 | `(ws, r, col_start) -> TimeShiftCounts` | 6 칸 시간대 단일 row (시트2/3) |
| `_parse_sheet2_job_allocations` | parser.py:256 | `(ws) -> list[JobAllocation]` | 시트2 — Mm01 group + final_flag 조건부 게이트 |
| `_safe_num` | parser.py:342 | `(v: object) -> float\|None` | None / 비수치 → None |
| `_norm_header` | parser.py:353 | `(v: object) -> str` | 헤더 셀 공백 제거 정규화 (매핑 비교용) |
| `_resolve_sheet4_columns` | parser.py:357 | `(ws, header_rows=(3,4)) -> dict[str, int]` | 시트4 헤더 텍스트 → {필드: 컬럼인덱스} (통합/업체 흡수) |
| `_build_activity` | parser.py:403 | `(ws, r, cols, trade, bp_code, company_raw) -> Activity` | cols 인덱스 기준 단일 row → Activity dict |
| `_parse_sheet4_activities` | parser.py:458 | `(ws) -> list[Activity]` | 시트4 — 헤더 해석 후 통합/업체 분기 추출 |
| `_parse_sheet3_equipment_allocations` | parser.py:512 | `(ws) -> list[EquipmentAllocation]` | 시트3 — col 2+3+4 + final_flag 조건부 게이트 |
| `_DATE_PATTERN` | parser.py:589 | `re.Pattern` | `_YYYYMMDD.(xlsx\|xlsm)` 또는 `_YYMMDD.(xlsx\|xlsm)` |
| `_extract_meta` | parser.py:592 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → (report_date ISO, project) |
| `parse_daily_report` | parser.py:625 | `(xlsx_path: Path\|str) -> ParsedDailyReport` | **공개 API** 4 시트 통합 (LLM 검증 없음) |

### parser_post.py (201 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `_is_real_bp` | parser_post.py:21 | `(value: str\|None) -> bool` | marker (FAB/CUB/소계 등) drop 판정 |
| `filter_marker_rows` | parser_post.py:32 | `(raw_rows, target_key="company_or_bp") -> list[dict]` | marker row 제거 (소계/합계) |
| `pair_bp_summaries` | parser_post.py:44 | `(raw_rows: list[dict]) -> list[dict]` | 시트1 2-row pairing (BP 코드 + 회사명) |
| `normalize_company` | parser_post.py:92 | `(raw: str\|None) -> str\|None` | ㈜prefix / 괄호 sub-context 제거 |
| `split_company_and_zone` | parser_post.py:108 | `(raw: str\|None) -> str\|None` | 회사명 끝 FAB/CUB suffix 제거 |
| `extract_zone` | parser_post.py:120 | `(v6: str\|None) -> str\|None` | col 6 (Scope) → 명시적 FAB/CUB 토큰 |
| `transform_job_allocations` | parser_post.py:143 | `(raw_rows: list[dict]) -> list[dict]` | JobAllocationRaw → JobAllocation |
| `transform_equipment_allocations` | parser_post.py:163 | `(raw_rows: list[dict]) -> list[dict]` | EquipmentAllocationRaw → EquipmentAllocation |
| `transform_bp_summaries` | parser_post.py:183 | `(raw_rows: list[dict]) -> list[dict]` | filter + pair + normalize 4-step |

### parser_node.py (64 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `_merge_reports` | parser_node.py:18 | `(reports: list[ParsedDailyReport]) -> ParsedDailyReport` | N개 리포트 concat (bp/job/equip/activities/worker_outputs 이어붙임, report_date 불일치 시 warning) |
| `parser_node` | parser_node.py:40 | `async (state: CPIAState) -> dict[str, Any]` | `input_files` 전체 Semaphore(4) + to_thread 병렬 파싱 → `_merge_reports` → `{"parsed": merged}` |

### collector.py (70 LOC, legacy)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `CollectorConfig` | collector.py:23 | `dataclass(file_concurrency: int = 4)` | 파일 단위 병렬 환경 |
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | 디렉토리 안 xlsx/xlsm 파일 sorted list |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | N xlsx Semaphore 병렬 파싱 |

### collector_node.py (63 LOC, D-12)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `collector_node` | collector_node.py:16 | `async (state: CPIAState) -> dict[str, Any]` | input_files[0] 검증 + filename_parser + collector_inbox UPDATE |

### collector/filename_parser.py (64 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `ParsedFilename` | filename_parser.py:15 | `frozen dataclass(kind, project, bp_name, trade, zone, date)` | 첨부 파일명 분해 결과 |
| `parse_filename` | filename_parser.py:25 | `(name: str) -> ParsedFilename\|None` | `업체작업일보_` / `통합작업일보_` 정규식 분해 |

### collector/idle_worker.py (260 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `request_shutdown` | idle_worker.py:37 | `() -> None` | `_shutdown` event set (graceful exit) |
| `_extract_attachments` | idle_worker.py:41 | `(msg: Message) -> list[tuple[str, bytes]]` | email.Message → 첨부 list (RFC 2047 decode) |
| `_save_to_input_dir` | idle_worker.py:63 | `(att_name, att_bytes, date_iso, cfg) -> Path` | `data/input/<YYYYMMDD>/<name>` 저장 (충돌 시 uuid suffix) |
| `_to_dead_letter` | idle_worker.py:81 | `(att_name, att_bytes, cfg) -> None` | 파일명 미일치 → dead_letter 폴더 + log |
| `run_for_attachment` | idle_worker.py:90 | `async (path, meta, site_id, message_id, cfg) -> None` | semaphore + graph.ainvoke + inbox status 처리 |
| `_process_one` | idle_worker.py:153 | `async (imap, uid, cfg) -> None` | UNSEEN 메일 1통 dedup + 첨부별 fire-and-forget |
| `_drain_new` | idle_worker.py:214 | `async (imap, cfg) -> None` | UNSEEN search → 전부 처리 |
| `idle_loop` | idle_worker.py:228 | `async (cfg: CollectorConfig) -> None` | FastAPI startup task — IDLE 유지 + reconnect backoff |

### collector/config.py (68 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `CollectorConfig` | config.py:15 | `frozen dataclass (host, port, user, app_password, ..., enabled)` | IMAP + PG + graph wiring |
| `load_collector_config` | config.py:35 | `(graph_cfg: GraphConfig) -> CollectorConfig` | env 로드 + enabled 시 자격증명 fail-fast |

### parser_llm.py (660 LOC, DEPRECATED 2026-05-20)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `ParserConfig` | parser_llm.py:55 | `dataclass (azure_endpoint, api_key, version, llm_model, sheet_concurrency=3)` | LLM 호출 환경 |
| `_extract_date_from_filename` | parser_llm.py:72 | `(p: Path) -> str` | 파일명 → ISO date |
| `_sheet_to_payload` | parser_llm.py:87 | `(ws, header_rows, body_start, max_body_rows, row_filter, ffill_cols) -> tuple` | ws → (header_map, body_rows) raw payload |
| `_is_job_alloc_signal_row` | parser_llm.py:137 | `(d: dict) -> bool` | 시트2 signal row filter |
| `_is_real_bp` | parser_llm.py:158 | `(value: str\|None) -> bool` | (parser_post 와 중복) |
| `_is_equipment_signal_row` | parser_llm.py:172 | `(d: dict) -> bool` | 시트3 signal row filter |
| `_llm_extract_sync` | parser_llm.py:389 | `(client, model, system, payload, response_key, retries, max_tokens) -> Any` | LLM 1 호출 + retry (length/content_filter/empty list 4 trigger) |
| `_llm_extract_chunked` | parser_llm.py:469 | `(client, model, system, header_map, rows, response_key, chunk_size=30, max_tokens) -> list` | rows chunk 분할 호출 |
| `parse_daily_report_llm` | parser_llm.py:503 | `async (xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport` | **DEPRECATED** — 6 시트 LLM chunk parsing |

---

## 5. 시트별 추출 함수 walkthrough

### 5.1 시트1 — `_parse_sheet1_bp_summaries` (parser.py:128)

**입력 가정**: `read_only=False` 모드 ws (merged_cells.ranges 필요). 시트명 `1.출력인원 현황`.

**핵심 로직**:
1. col 30 (금일 투입 그룹 Total) merged range 수집 — 값 있는 좌상단만.
2. solo row (merged 가 아니면서 col 30 값 있는 row) 식별.
3. solo + 다음 row 흡수 패턴: 다음 row 가 col 5 채워있고 col 30 None 이면 회사명 단독 row 로 보고 absorb.
4. group range 정렬 후 각 group 안에서 BP 코드 row + 회사명 row 분리, work_text_yesterday/today/tomorrow 합치기 (col 7/8/9).
5. `split_company_and_zone` + `normalize_company` 로 회사명 정규화, `extract_zone(col 6)` 로 zone 결정.
6. `_shift_dict_sum` 으로 4 시간대 그룹 (yesterday_incr col 10 / yesterday_cum col 17 / today_incr col 24 / today_cum col 31) 합산.
7. skip 조건: bp_code None & company None (sub-section 합계), 또는 company None & cum=0 & incr=0 (빈 placeholder).

**핵심 코드** (parser.py:142-174):

```python
# 1. col 30 merged 범위 수집 (값 있는 좌상단만)
ad_merges: dict[int, int] = {}
for mr in ws.merged_cells.ranges:
    if mr.min_col == 30 and mr.max_col == 30:
        top_val = ws.cell(mr.min_row, 30).value
        if top_val is None:
            continue
        ad_merges[mr.min_row] = mr.max_row

# 2. solo row
solo_rows: list[int] = []
for r in range(5, ws.max_row + 1):
    v = ws.cell(r, 30).value
    if v is None: continue
    if not any(s <= r <= e for s, e in ad_merges.items()):
        solo_rows.append(r)

# 3. solo+next 흡수
for r in solo_rows:
    next_r = r + 1
    v5_next = ws.cell(next_r, 5).value
    v30_next = ws.cell(next_r, 30).value
    in_other = any(s <= next_r <= e for s, e in ad_merges.items())
    if v5_next and v30_next is None and not in_other:
        raw_groups.append((r, next_r))
```

**기대 산출량**: 통합 작업일보 1건 ≈ 99 그룹 → 99 BPSummary.

---

### 5.2 시트2 — `_parse_sheet2_job_allocations` (parser.py:256)

**final_flag 조건부 게이트 (`c0699dc`)**: col25 에 `O` 가 하나라도 있으면 통합포맷으로 보고 group 시작·직종 row 둘 다 `col 25=='O'` 게이트 유지. 'O' 가 전혀 없는 업체포맷은 `has_final_flag=False` → 게이트 완화. cross-check 는 수행하되 mismatch 시 silent.

**핵심 로직**:
1. `has_final_flag = any(col25=='O')` — 통합/업체 포맷 감지.
2. group 시작 row 식별: col 4='Mm01' + col 2 (공종) + col 3 채워있음 + col 3 = `_is_bp_code` + (통합포맷이면 col 25='O').
3. starts list 기반으로 group range 결정 (다음 start - 1 까지).
4. 회사명: group 시작 다음 5 row 안의 첫 col 3 한글값 (BP 코드 아닌 것).
5. 각 row 에서 col 4 (코드) — 통합포맷이면 col 25='O' 통과한 것만 — `Mm##` → manager_code, 그 외 → worker_code.
6. `_is_admin_job` (BP소장 / 공사관리자 / 안전관리자 / 품질관리자 / 일반관리자) filter — sub-pipeline 호환.
7. 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19.

**핵심 코드** (parser.py:269-286):

```python
# 업체포맷 감지: col25 에 'O' 가 하나라도 있으면 통합포맷 (final_flag 게이트 유지)
has_final_flag = any(ws.cell(r, 25).value == "O" for r in range(6, ws.max_row + 1))

starts: list[int] = []
for r in range(6, ws.max_row + 1):
    c4 = ws.cell(r, 4).value
    if c4 != "Mm01":
        continue
    c2 = ws.cell(r, 2).value
    c3 = ws.cell(r, 3).value
    c25 = ws.cell(r, 25).value
    if c2 is None or c3 is None:
        continue
    if has_final_flag and c25 != "O":
        continue
    if not _is_bp_code(c3):
        continue
    starts.append(r)
```

---

### 5.3 시트3 — `_parse_sheet3_equipment_allocations` (parser.py:512)

**핵심 로직**:
1. `has_final_flag = any(col25=='O')` — 통합/업체 포맷 감지 (시트2 와 동일 게이트).
2. group 시작 row 식별: col 2 (공종) + col 3 (`_is_bp_code`) + col 4 (장비 대분류) 모두 채워있음.
3. **헤더 reprint row 회피**: col 2 에 "장비 투입" 문자열 포함되면 skip.
4. 회사명: group 안 첫 col 3 한글값 (BP 코드 제외).
5. 장비 row = col 4 채워있음 + (통합포맷이면 col 25='O').
6. 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19.
7. subtotal 없음 → cross-check 불요.

**핵심 코드** (parser.py:526-538):

```python
starts: list[int] = []
for r in range(6, ws.max_row + 1):
    c2 = ws.cell(r, 2).value
    c3 = ws.cell(r, 3).value
    c4 = ws.cell(r, 4).value
    if c2 is None or c3 is None or c4 is None:
        continue
    if not _is_bp_code(c3):
        continue
    # 헤더 reprint row 회피
    if "장비 투입" in str(c2):
        continue
    starts.append(r)
```

---

### 5.4 시트4 — `_parse_sheet4_activities` (parser.py:458)

issue#52 (업체작업일보 컬럼 시프트 garbage) 해소를 위해 컬럼을 **하드코딩 인덱스 → 헤더 텍스트 해석**으로 전환 (`25bb85d`). 통합/업체 두 포맷이 같은 코드로 흡수된다.

**핵심 로직**:
1. `_resolve_sheet4_columns(ws)` (parser.py:357) — 헤더 2-row 스택 (row3 주 라벨 + row4 `[A][B][C][D]`·`F%` 마커) 을 함께 읽어 `{trade, bp, company_col?, scope?, work_content, unit, plan_total?, yesterday_cum?, today_qty, today_cum?, progress?}` 매핑. 필수 5종 (`trade/bp/work_content/unit/today_qty`) 누락 시 `ParseError`.
   - `금일실적` → today_qty (`[C]`), `금일누적` → today_cum (`[D]`) 분리.
   - `F%` 는 row4 전용 마커라 `h3`/`h4` 직접 재테스트 (이 elif 순서/재테스트 방식 바꾸면 통합 progress 누락 → act=1193 회귀 깨짐).
2. `company_col` ("업체명" 헤더) 존재 여부로 통합/업체 분기.
3. **통합포맷** (`has_company_col=True`): trade 만 ffill, company 는 BP행에 종속 (독립 ffill 아님). `bp` 컬럼 채워지면 같은 행 `company_col` 갱신.
4. **업체포맷** (`has_company_col=False`): BP사 컬럼 코드행 ~ 다음 코드행 group, company = group 내 첫 non-bp 값. trade 는 group 시작 직전까지 누적 ffill.
5. Activity row = `work_content` 채워있는 row 만 → `_build_activity` (parser.py:403) 로 dict 생성.
6. `extract_zone(scope)` 옵션 2 보수 매칭 — scope 명시 FAB/CUB 토큰만.

**핵심 코드** (parser.py:468-486, 통합포맷 분기):

```python
cols = _resolve_sheet4_columns(ws)
has_company_col = "company_col" in cols
activities: list[Activity] = []
if has_company_col:
    # 통합포맷: trade ffill + company 는 BP행에 종속(독립 ffill 아님)
    cur_trade = cur_bp = cur_company_raw = None
    for r in range(5, ws.max_row + 1):
        tv = ws.cell(r, cols["trade"]).value
        if tv is not None:
            cur_trade = str(tv)
        bv = ws.cell(r, cols["bp"]).value
        if bv is not None:
            cur_bp = str(bv).strip()
            cv = ws.cell(r, cols["company_col"]).value
            cur_company_raw = str(cv) if cv is not None else None
        wv = ws.cell(r, cols["work_content"]).value
        if wv is None:
            continue
        activities.append(_build_activity(ws, r, cols, cur_trade, cur_bp, cur_company_raw))
```

---

## 6. parser_post.py 함수별 입출력 예시

### 6.1 `split_company_and_zone(raw: str | None) -> str | None`

회사명 끝의 `FAB` / `CUB` suffix 제거. **옵션 2 (scope ≠ wa)**: suffix 는 회사명 정규화에만, zone 정보 반환 X.

| 입력 | 출력 |
|---|---|
| `에스비테크CUB` | `에스비테크` |
| `광건티엔씨FAB(수장2)` | `광건티엔씨` (괄호도 normalize_company 에서 제거) |
| `ABC건설(2공구)` | `ABC건설` |
| `남웅건설` | `남웅건설` |
| `None` | `None` |
| `""` | `None` |

### 6.2 `extract_zone(v6: str | None) -> str | None`

col 6 (Scope) 의 명시적 `FAB` / `CUB` 토큰만 zone 추출 (옵션 2 보수 매칭).

| 입력 | 출력 | 비고 |
|---|---|---|
| `FAB` | `FAB` | 단일 토큰 |
| `CUB` | `CUB` | 단일 토큰 |
| `FAB 전구간` | `FAB` | 시작 토큰 |
| `CUB 1F~7F` | `CUB` | 시작 토큰 |
| `FAB/CUB` | `None` | 양쪽 — 모호 |
| `FAB & CUB` | `None` | 양쪽 |
| `M15X FAB F04` | `None` | 텍스트 중간 — 신뢰 X |
| `None` | `None` | |

### 6.3 `pair_bp_summaries(raw_rows: list[dict]) -> list[dict]`

시트1 의 2-row 페어링 패턴 (BP 코드 row + 한글 회사명 row, 같은 zone+disc_abbrev) → 1 BPSummary 머지. 그 외 single row 유지.

**입력**:
```python
[
    {"is_bp_code": True, "bp_code": "PH_X-001", "zone": "FAB", "disc_abbrev": "건축",
     "today_cum_total": 5, "work_text_today": None},
    {"is_korean_company": True, "company": "남웅건설", "zone": "FAB", "disc_abbrev": "건축",
     "today_cum_total": 10, "work_text_today": "거푸집 설치"},
    {"is_bp_code": True, "bp_code": "PH_X-002", "company": "세보엠이씨"},  # single
]
```

**출력**:
```python
[
    {"bp_code": "PH_X-001", "company": "남웅건설", "zone": "FAB",
     "today_cum_total": 10, "work_text_today": "거푸집 설치"},  # paired
    {"bp_code": "PH_X-002", "company": "세보엠이씨", ...},  # single
]
```

### 6.4 `transform_bp_summaries(raw_rows: list[dict]) -> list[dict]`

4-step 파이프라인: `filter_marker_rows(target_key="col_4_value")` → `pair_bp_summaries` → `normalize_company` → company OR bp_code 있어야 통과.

**주의**: `83b61ec` commit 에서 `today_incr_total` 필드 누락 fix (mapper KeyError 회피).

---

## 7. LLM 검증 wrapper — **제거됨 (2026-06-01 `ac0a8c5`)**

> 2026-05-26 baseline 까지 존재하던 `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` + `_should_verify_llm` (env `CPIA_PARSER_VERIFY_LLM`) 는 **전부 삭제**. parser.py 안에 azure/openai import·호출이 더 이상 없다 (grep 확인: `verify_sheet`/`VERIFY_LLM`/`chat.completions` 0건).

**제거 이유**:
- issues 가 `stderr` 로만 떨어져 DB 적재·운영 알람으로 이어지지 않아 **무력** (실효 0).
- LLM 1~2 호출이 cycle 당 ~$0.55 + 지연만 추가, 결정성 검증 가치는 골든 회귀로 대체 가능.
- 업체포맷 E2E 통합 (`ac0a8c5`) 시 demo_inputs 10개 골든을 정답으로 고정 — rule 추출 정확도는 골든 byte-diff 로 보장.

**현재 동작**: `parse_daily_report` 는 4 시트 추출 후 즉시 `ParsedDailyReport` return. LLM 호출 0. 결정성은 입력 고정 시 자동 보장.

---

## 8. parser_llm.py DEPRECATED 분석 (660 LOC)

### 8.1 DEPRECATED 된 이유

`pipeline/agents/parser_llm.py:1` 파일 헤더 인용:

> 본 모듈은 chunk LLM parsing 으로 ParsedDailyReport 를 생성했으나, 5/20 부터 `pipeline.agents.parser.parse_daily_report` (rule-based + 시트1/4 LLM 검증 hybrid) 로 대체됨. 이 모듈은 본 cycle 의 graph entry 에서 호출되지 않음.

**대체 이유**:
- chunk LLM 270 호출 → **4-5 분 / cycle, ~$3 / cycle** → 시연 마감 (6/5) 압력
- rule + 시트1/4 LLM 검증 hybrid → **~20 초 / cycle, ~$0.55 / cycle**
- 매핑 정확도: mapper `auto_bp_zone_match` (BP-zone deterministic) 와 정합

### 8.2 회귀 path

- caller (`pipeline/agents/collector.py:19`, `scripts/run_one_cycle.py`) 의 import 를 `parser` → `parser_llm` 으로 되돌리면 동작.
- env flag `CPIA_PARSER=llm` graph entry 안에서 분기 — **미구현** (현재 caller 직접 수정으로만 회귀 가능).

### 8.3 잔존 의의

1. **fallback 경로**: rule path 가 새 양식에서 실패하는 비상 경로 (POC 외 사이트 양식 지원 시).
2. **`_sheet_to_payload` 재사용**: parser_post 의 transform_* 함수가 raw → entity 변환을 일원화 — LLM path 도 같은 정제 통과.
3. **chunked LLM call retry 패턴** (`_llm_extract_sync` parser_llm.py:389): 4 retry trigger (JSON parse 실패 / length / content_filter / empty list) — 향후 LLM 보조 parse 재도입 시 참조 가능 (현재 parser.py 의 LLM 검증 wrapper 는 제거됨).

### 8.4 제거 backlog

design_intent_parser.md 표시: issue #N8 — env flag deprecation 후 다음 cycle 제거.

---

## 9. parser_node + collector_node 관계 (D-12)

### 9.1 graph 호출 순서

`pipeline/graph.py:595-646` 발췌 — `parser` 노드는 `_parser_p` async wrapper 로 감싸 `set_current_node` 후 `await _parser(state)` (parser_node 가 async 이므로 await 필수):

```python
async def _parser_p(state: CPIAState) -> dict:
    await set_current_node(pg_url, state["run_id"], "parser")
    # parser_node 는 async (multi-file 병렬 파싱 + merge) — await 필수.
    return await _parser(state)

graph.add_node("collector", _collector_p)
graph.add_node("parser", _parser_p)        # parser_node.parser_node (async)
graph.add_node("mapper", _mapper)
...
graph.add_edge(START, "collector")
graph.add_edge("collector", "parser")
graph.add_edge("parser", "mapper")
graph.add_edge("mapper", "hil_1")
```

진입점이 `collector` — D-12 이전에는 `parser` 가 시작이었으나 listener (idle_worker) 가 박은 `input_files[0]` 검증 + `collector_inbox` UPDATE 책임을 graph 안으로 이전.

### 9.2 collector_node 책임 (collector_node.py:16-63)

1. `state["input_files"]` 존재 검증 → 비어있으면 `RuntimeError`.
2. `Path(input_files[0])` exists 검증 → 없으면 `FileNotFoundError`.
3. `parse_filename(path.name)` (filename_parser.py:25) → 미일치 시 `ValueError`.
4. `state["message_id"]` 와 `state["postgres_url"]` 둘 다 있으면 `update_collector_inbox_status(parse_status="running", run_id)` UPDATE.
5. return `{"bp_name", "date", "project"}` — mapper 가 쓸 메타.

**CLI 진입 (외부 listener 없이 main.py) 시**: `message_id` absent → UPDATE skip. 같은 노드가 IMAP 경로 / CLI 경로 양쪽에서 동작.

### 9.3 parser_node 책임 (parser_node.py:40-64) — async N병렬 multi-file merge

2026-06-01 `a8d17e4` 부터 옛 "1-줄 sync wrapper (`input_files[0]` 1개)" → **`input_files` 전체를 async 병렬 파싱 후 1 통합**으로 확장 (PoC multi-file: 업체별 일보 N개 동시 적재).

```python
_PARSE_CONCURRENCY = 4  # 파일 단위 병렬 (sync parse 를 to_thread 로 wrap — 이벤트 루프 block 회피)


async def parser_node(state: CPIAState) -> dict[str, Any]:
    files = [Path(f) for f in state["input_files"]]
    if not files:
        raise RuntimeError("parser_node: input_files 비어있음")
    sem = asyncio.Semaphore(_PARSE_CONCURRENCY)

    async def _parse_one(p: Path) -> ParsedDailyReport:
        async with sem:
            return await asyncio.to_thread(parse_daily_report, p)

    reports = list(await asyncio.gather(*[_parse_one(p) for p in files]))
    merged = _merge_reports(reports)
    log.info(
        "parser_node: %d개 파일 병렬 병합 (bp_summaries=%d, activities=%d)",
        len(files), len(merged["bp_summaries"]), len(merged["activities"]),
    )
    return {"parsed": merged}
```

단일 책임:
- `input_files` 전체를 `asyncio.Semaphore(4)` + `asyncio.to_thread(parse_daily_report, p)` 로 `gather` — sync parse 를 thread 로 off-load 해 FastAPI 이벤트 루프 block 회피 (mapper~ 진행 중 게이지 polling 응답).
- `_merge_reports` 로 N개 → 1 concat → return `{"parsed": merged}`.
- internal parser.py 변경 0 (1 첨부 = 1 ParsedDailyReport, merge 는 parser_node 책임).

### 9.4 `_merge_reports` concat 규칙 (parser_node.py:18)

```python
def _merge_reports(reports: list[ParsedDailyReport]) -> ParsedDailyReport:
    base = reports[0]
    dates = {r["report_date"] for r in reports if r.get("report_date")}
    if len(dates) > 1:
        log.warning("parser_node merge: report_date 불일치 %s", dates)
    return {
        "report_date": base["report_date"],
        "project": base["project"],
        "bp_summaries": [x for r in reports for x in r["bp_summaries"]],
        "job_allocations": [x for r in reports for x in r["job_allocations"]],
        "equipment_allocations": [x for r in reports for x in r["equipment_allocations"]],
        "activities": [x for r in reports for x in r["activities"]],
        "worker_outputs": [x for r in reports for x in r["worker_outputs"]],
        "report_meta": base["report_meta"],
    }
```

- 각 업체가 서로 다른 작업을 한다는 전제로 5 리스트 (bp_summaries / job_allocations / equipment_allocations / activities / worker_outputs) 를 **단순 이어붙임**.
- `report_date` 는 모든 파일 동일 가정 — 불일치 시 `log.warning` 만 남기고 첫 파일 날짜 사용.
- `report_meta` 는 첫 업체 것 (site 대표).
- 10 업체파일 → 통합 `activities=330` (PoC graph multi-file).

> **이전 state-key drift fix (`6b9db7c`)**: `parser_node` return key 는 `parsed_reports` (list) → `parsed` (single dict) 로, `report_date` → `date` 로 통일된 상태. multi-file 확장 후에도 mapper 는 `state["parsed"]` (단일 merged dict) 로 읽는다.

---

## 10. legacy collector.py vs collector_node.py vs idle_worker.py 정리

세 모듈은 책임이 다름 — 한 cycle 안에서 두 개 이상 같이 안 쓰임.

| 모듈 | 진입 경로 | 동기/비동기 | 책임 | 호출자 |
|---|---|---|---|---|
| `pipeline/agents/collector.py` | CLI 배치 (run_one_cycle) | async | 디렉토리 walk + N xlsx Semaphore 병렬 파싱 → `list[ParsedDailyReport]` | `scripts/run_one_cycle.py` |
| `pipeline/agents/collector_node.py` | graph 안 (D-12) | async | `state.input_files[0]` 검증 + filename 분해 + `collector_inbox` UPDATE | `graph.build_graph()` |
| `pipeline/collector/idle_worker.py` | FastAPI startup task | async | IMAP IDLE listener → 첨부 추출 → `collector_inbox` INSERT → `run_for_attachment` (graph fire-and-forget) | `pipeline/api.py` startup |

**흐름 차이**:

- **Prod (IMAP)**: `idle_worker.idle_loop` → 메일 도착 → `_process_one` 이 첨부 1개당 `create_task(run_for_attachment)` → `graph.ainvoke(state={input_files: [path], message_id, ...})` → graph 안에서 `collector_node` → `parser_node` 차례 실행. 이 경로는 `input_files` 길이 1 — `parser_node` 가 N병렬이어도 단일 파일만 파싱. `legacy collector.py` 는 호출 안 됨.
- **Multi-file PoC**: graph entry 에 `input_files: [p1..pN]` (10 업체 일보) 를 직접 넣으면 `parser_node` 가 N병렬 파싱 → `_merge_reports` 로 1 통합. (collector_node 는 `input_files[0]` 만 검증하므로 multi-file 진입은 collector 우회 또는 첫 파일만 메타 분해.)
- **CLI (batch)**: `scripts/run_one_cycle.py` → `collect_and_parse(input_dir)` 로 `list[ParsedDailyReport]` 받음 → 별도 graph 호출 또는 직접 mapper 호출. `collector_node` / `idle_worker` 둘 다 미호출.

**legacy 잔존 이유**: CLI 진입은 graph 의 메타 분해 + `collector_inbox` UPDATE 가 불요. `discover_daily_reports` 가 정렬 + xlsx 필터 (`~$` lock skip / `작업일보` 포함 substring) 역할로 단독 가치 있음.

---

## 11. 데이터 구조 (pipeline/state.py 발췌)

### TimeShiftCounts (state.py:17)

6 시간대 분포 — 인원/장비 공용. PG 적재 시 jsonb.

| 필드 | 타입 | 의미 |
|---|---|---|
| `morning` | int | 조출 |
| `daytime` | int | 주간 |
| `overtime` | int | 연장 |
| `night` | int | 야간 |
| `all_night` | int | 철야 |
| `total` | int | Total |

### BPSummary (state.py:96)

시트1 BP사 × 공종 × Zone × Scope row.

| 필드 | 타입 | 출처 |
|---|---|---|
| `bp_code` | str \| None | `_is_bp_code` 매칭 |
| `company` | str | split_company_and_zone + normalize_company |
| `disc_abbrev` | str \| None | (현재 시트1 에서는 None, 시트2/3 에서 채움) |
| `zone` | str \| None | extract_zone(col 6) |
| `scope` | str \| None | col 6 원본 |
| `work_text_yesterday` | str \| None | col 7 (group 안 join) |
| `work_text_today` | str \| None | col 8 |
| `work_text_tomorrow` | str \| None | col 9 |
| `workers_yesterday_incr` | TimeShiftCounts \| None | col 10-15 group sum |
| `workers_yesterday_cum` | TimeShiftCounts \| None | col 17-22 group sum |
| `workers_today_incr` | TimeShiftCounts \| None | col 24-29 group sum |
| `workers_today_cum` | TimeShiftCounts \| None | col 31-36 group sum |
| `today_incr_total` | int | col 30 |
| `today_cum_total` | int | col 37 |

### JobAllocation (state.py:122)

시트2 BP사 × 직종 × 시간대.

| 필드 | 타입 | 출처 |
|---|---|---|
| `bp_code` | str \| None | group 시작 col 3 |
| `company` | str | group 시작 다음 5 row 한글 col 3 |
| `disc_abbrev` | str \| None | group 시작 col 2 (`_disc_abbrev_to_kr` 변환) |
| `manager_code` | str \| None | col 4 가 `Mm##` 면 박힘 |
| `worker_code` | str \| None | col 4 가 그 외 (sk## / Wk##) |
| `job_type` | str | col 6 |
| `workers_yesterday_cum` | TimeShiftCounts \| None | col 7-12 |
| `workers_today_incr` | TimeShiftCounts \| None | col 13-18 |
| `workers_today_cum` | TimeShiftCounts \| None | col 19-24 |
| `final_flag` | str \| None | col 25 ("O") |
| `workers_cum_t` | int | workers_today_cum.total (편의) |

### EquipmentAllocation (state.py:146)

시트3 BP사 × 장비 × 시간대.

| 필드 | 타입 | 출처 |
|---|---|---|
| `bp_code` | str \| None | group 시작 col 3 |
| `company` | str | group 안 한글 col 3 |
| `disc_abbrev` | str \| None | group 시작 col 2 |
| `equipment_big` | str | col 4 |
| `equipment_mid` | str | col 5 |
| `equipment_spec` | str \| None | col 6 |
| `count_yesterday_cum` | TimeShiftCounts \| None | col 7-12 |
| `count_today_incr` | TimeShiftCounts \| None | col 13-18 |
| `count_today_cum` | TimeShiftCounts \| None | col 19-24 |
| `final_flag` | str \| None | col 25 ("O") |
| `count_cum_t` | int | count_today_cum.total (편의) |

### Activity (state.py:32)

시트4 1행 = 매핑 단위. **39 필드** — Parser 가 채우는 것 + Mapper 가 채우는 것 + H-i-L 1 플래그.

**Parser 채움 (시트4 원천)** — 컬럼은 `_resolve_sheet4_columns` 가 헤더 텍스트로 해석한 `cols` 인덱스 (아래 col 번호는 **통합포맷** 기준; 업체포맷은 시프트돼도 헤더 매핑으로 흡수). 실제 dict 생성은 `_build_activity` (parser.py:403):

| 필드 | 타입 | cols 키 (통합 col) |
|---|---|---|
| `zone` | str \| None | scope → extract_zone |
| `bp_code` | str \| None | bp (BP행 종속/업체 group) |
| `company` | str | company_col (통합) / group 내 첫 non-bp (업체) normalize |
| `scope` | str \| None | scope 원본 (col 7) |
| `trade` | str | trade ffill (col 4) |
| `work_content` | str | work_content (col 8) |
| `unit` | str | unit normalize (col 9) |
| `plan_total_qty` | float \| None | plan_total (col 10, 헤더 없으면 None) |
| `yesterday_cum_qty` | float \| None | yesterday_cum (col 11) |
| `today_qty` | float | today_qty (col 12, default 0.0) |
| `today_cum_qty` | float \| None | today_cum (col 13) |
| `progress_percent` | float \| None | progress (F%, row4) |
| `remaining_qty` | float \| None | None (PoC) |
| `remaining_percent` | float \| None | None (PoC) |
| `note` | str \| None | None (PoC) |
| `l5_disc` | str | trade (현재 동일) |

**업체별 일보 추가 (통합 일보엔 None)**:
- `work_location_code`, `wbs_mid_name`, `wbs_sub_name`, `wbs_detail_name`

**Mapper 이후 채움**:
- `wbs_activity_id` (PoC: None — 1:N), `l6_main`, `l7_sub` (PoC: None), `l7_5_activity` (PoC: None), `sub_work_area` (PoC: None), `conditions`, `assigned_workers`, `worker_source` (`parsed` / `mh_prorated` / `user_corrected`), `plan_mh`, `wa`, `mapping_conf`, `mapping_source`, `requires_review`.

**Parser 초기값** (`_build_activity` parser.py:447-454):
- `worker_source = "parsed"`, `assigned_workers = 0.0`, `requires_review = False`, mapping 관련 모두 None, `conditions = []`.

### ParsedDailyReport (state.py:207)

1 작업일보 xlsx — 4 시트 통합 + 업체별 시트6/Cover (현재 parser.py 에서는 worker_outputs 빈 list / report_meta None).

| 필드 | 타입 |
|---|---|
| `report_date` | str (ISO YYYY-MM-DD) |
| `project` | str |
| `bp_summaries` | list[BPSummary] |
| `job_allocations` | list[JobAllocation] |
| `equipment_allocations` | list[EquipmentAllocation] |
| `activities` | list[Activity] |
| `worker_outputs` | list[WorkerOutput] (parser.py: 항상 []) |
| `report_meta` | ReportMeta \| None (parser.py: 항상 None) |

### Raw TypedDict (parser_post.py 입력용)

- `BPSummaryRaw` (state.py:268)
- `JobAllocationRaw` (state.py:285)
- `EquipmentAllocationRaw` (state.py:299)

모두 `total=False` — LLM (parser_llm path) 또는 rule 추출 후 raw 단계에서 사용. parser.py (rule path) 는 raw 단계 거치지 않고 직접 entity 생성. parser_post 의 transform_* 는 LLM path 용으로 보존.

### ParserResult / ParserReport

**없음** — 현재 코드베이스에 별도 `ParserResult` 또는 `ParserReport` TypedDict 정의 없음. `ParsedDailyReport` 가 그 자리를 함. (이름이 그렇게 명시된 PG 테이블은 `parser_activities` / `parser_job_allocations` / `parser_equipment_allocations` / `parser_worker_outputs` / `parser_report_meta` — db.py 에서 INSERT.)

---

## 12. 에러 핸들링

### 12.1 Hard fail (`ParseError` raise)

| 위치 | 조건 | 동작 |
|---|---|---|
| parser.py:644 | 4 시트 중 하나라도 누락 | `ParseError(f"시트 누락: {sorted(missing)}")` |
| parser.py:602 | 파일명에서 날짜 추출 실패 | `ParseError(f"파일명에서 날짜 추출 실패: ...")` |
| parser.py:620 | project 추출 실패 | `ParseError(f"project 추출 실패: ...")` |
| parser.py:399 | 시트4 필수 헤더 (`trade/bp/work_content/unit/today_qty`) 매핑 실패 | `ParseError(f"시트4 헤더 매핑 실패: {missing}")` |

상위 caller (`parser_node` / `collect_and_parse`) 가 raise 전파. async parser_node 에서는 `asyncio.gather` 가 첫 예외를 전파. graph 안에서는 `run_for_attachment` (idle_worker.py:130) 가 broad `except Exception` 으로 잡아 `collector_inbox.parse_status="failed", error=str(e)[:1000]` UPDATE.

### 12.2 Soft warning — **LLM 검증 issues 제거됨**

2026-06-01 (`ac0a8c5`) 으로 `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` 가 삭제되어 parse 본문의 soft warning (stderr issue) 경로는 더 이상 없다. 남은 warning 은 `_merge_reports` 의 `report_date` 불일치 `log.warning` (parser_node.py:27) 1건뿐.

### 12.3 ~~LLM 검증 graceful catch (8 종)~~ — 제거됨

LLM 검증 wrapper 자체가 사라져 graceful catch 도 무효. parse 본문은 openpyxl 추출만 하므로 별도 LLM error path 없음.

### 12.4 collector_node 검증 (collector_node.py:30-35)

| 조건 | 예외 |
|---|---|
| `state.input_files` 비어있음 | `RuntimeError("collector_node: state.input_files 비어있음")` |
| `path.exists()` False | `FileNotFoundError(f"collector_node: {path}")` |
| `parse_filename(path.name)` is None | `ValueError(f"collector_node: 파일명 규약 불일치 {path.name}")` |

### 12.5 IMAP listener dead_letter (idle_worker.py:81)

`parse_filename` 미일치 첨부는 `data/input/dead_letter/<stem>_<uuid8>.<ext>` 저장 + `log.warning` — graph 호출 안 함.

---

## 13. LLM 호출 정리

### 13.1 활성 호출 (parse_daily_report 안)

**없음 — 0 호출 / cycle.** 2026-06-01 (`ac0a8c5`) 으로 시트1/4 LLM 검증 wrapper 가 제거되어 `parse_daily_report` 안에 azure/openai 호출이 더 이상 없다. parser 서브시스템은 현재 완전 결정론적 (openpyxl rule + header 매핑만). grep 확인: parser.py 에 `chat.completions` 0건.

### 13.2 DEPRECATED 호출 (parser_llm path)

| 호출 | 모델 | 호출 회수 / cycle | 비용 |
|---|---|---:|---:|
| `_llm_extract_chunked` x 6 시트 x ~45 chunk | gpt-5.1 | ~270 | ~$3 (통합) / ~$0.05 (업체별) |

현재 호출 안 됨 — caller 전부 `parse_daily_report` 로 교체 (commit `888e927`).

### 13.3 비고

- 검증 wrapper 제거 후 parser 의 LLM 의존 0. 추출 정확도는 demo_inputs 10개 골든 byte-diff 회귀로 보장.
- LLM 기반 parse 가 필요하면 DEPRECATED `parser_llm.parse_daily_report_llm` 으로 회귀 가능 (caller import 교체 또는 미구현 env flag `CPIA_PARSER=llm`).

---

## 14. 이슈 표

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| 1 | ~~`parser_warning` PG 영속화~~ — LLM 검증 wrapper 제거로 무효화 | (parser.py) | LLM 검증 issues 자체가 사라짐 | resolved (`ac0a8c5`) |
| 2 | `parser_llm.py` 660 LOC DEPRECATED 잔존 | parser_llm.py | env flag 회귀 path 미구현, 코드만 보존 | backlog (issue #N8) |
| 3 | `BPSummary.disc_abbrev` 시트1 추출 안 됨 | parser.py:231 | 항상 None (시트1 col 에 공종 없음) → mapper 의존 안 함 | by design |
| 4 | `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` 항상 None | parser.py:441-446 | Master List 1:N 제약 | by design (PoC) |
| 5 | `_is_total_row` / `_ffill` 미참조 (dead code) | parser.py:64, 72 | 헤더기반 전환 후 호출처 없음 — 제거 후보 | minor (cleanup) |
| 6 | 시트4 헤더 매핑이 `F%` elif 순서·재테스트에 결합 | parser.py:391-395 | 순서 바꾸면 통합 progress 누락 → act=1193 회귀 깨짐 | by design (주석 경고) |
| 7 | 시트2 raw company suffix (`창원기전CUB(22.9kV)`) zone 활용 미구현 | parser.py:256 | 시트2 group 의 zone 정보 손실 | spec §8 |
| 8 | `BPSummary.work_text_today` BP 별 분리 안 됨 | parser.py:234-236 | group 안 row work_text 통합 (`|` join) | spec §8 |
| 9 | 다른 사이트 일보 양식 (시트명·col 좌표 다름) 미지원 | parser.py 전체 | 시트4 만 헤더기반, 시트1/2/3 은 여전히 col 좌표 hardcoded | spec §8 |
| 10 | `_merge_reports` report_date 불일치 시 warning 만 (첫 파일 날짜 사용) | parser_node.py:25-27 | 서로 다른 날짜 파일 섞이면 잘못된 date 로 적재 | by design (PoC 동일날짜 가정) |
| 11 | `data_only=True` + 시트1 merged_cells.ranges 필요 (read_only 불가) | parser.py:638-639 | 큰 xlsx 메모리 risk | 현재 PoC 양식 OK |
| 12 | `Mm01` 패턴이 시트2/3 group boundary — 다른 코드 체계 호환 X | parser.py:275 | "Mm01" 문자열 hardcoded | by design (POC 양식) |
| 13 | `_extract_meta` 의 project 추출이 시트1 첫 3 row 의 "M15X/IBL/PJT" substring 매칭 | parser.py:605-614 | 다른 사이트명 미지원 (실패 시 파일명 fallback) | spec §8 |
| 14 | `parse_filename` 의 통합/업체별 prefix hardcoded | filename_parser.py:28 | "통합작업일보_" / "업체작업일보_" 외 미지원 | by design |
| 15 | `idle_worker._GRAPH_SEM = Semaphore(2)` — 한 listener 가 동시 graph 2개만 | idle_worker.py:34 | 첨부 N개 동시 도착 시 직렬화 | env `CPIA_COLLECTOR_CONCURRENCY` 로 조정 |

---

## 15. 검증 status (design_intent_parser.md 동기화)

| Phase | 항목 | 상태 |
|---|---|---|
| V1 (5/20) | 4 시트 rule cross-check (시트2 0 warnings) | 완료 |
| V2 (5/20) | Mapper 5 case simulation (auto_bp_zone_match 60% deterministic) | 완료 |
| V3 | 146 case full simulation (POC 3사) | pending |
| V4 | Unit test 12개 (spec §5) | pending |
| V5 | 10 업체 POC 전체 cycle + Reports UI 12 정량 기준 | pending |
| D-12 | collector_node / parser_node 분리 + state-key drift fix | 완료 (`55cad90`, `6b9db7c`) |
| D-12 test | `test_collector_node.py` 70 LOC + `test_parser_node.py` 29 LOC | 완료 |
| 06-01 | header-based 다포맷 7-task (issue#52 컬럼시프트 garbage 해소) | 완료 (`65a8027`~`ac0a8c5`) — 통합 byte-identical + 업체 골든 33/1/76/68 |
| 06-01 | parser_node async N병렬 multi-file merge | 완료 (`a8d17e4`) — 10 업체 → activities 330 |
| 06-01 test | `test_parser_subcon.py` 39 LOC + `test_parser.py` 갱신 | 완료 |

---

## 16. 본 cycle 변경 사항 (1ba783f → d317be9)

parser 헤더기반 다포맷 7-task + parser_node async multi-file merge. parser.py 만 `442 ++++/----` (Merge stat), parser_node.py `61 +/-`.

| Commit | 변경 |
|---|---|
| `65a8027` | fix(parser): `_DATE_PATTERN` 이 8자리 날짜+.xlsm 조합 수용 (업체작업일보) |
| `7d2befc` | feat(parser): BP코드 다중 패턴 (`PH_X-NNN` + `M15X_PHn_NNN`) — `_BP_PATTERNS` 2종 |
| `25bb85d` | feat(parser): 시트4 헤더 기반 컬럼 해석 (`_resolve_sheet4_columns`/`_build_activity`) — column shift 해소 |
| `c0699dc` | feat(parser): 시트2/3 final_flag 조건부 완화 (`has_final_flag` — 'O' 없는 업체포맷만) |
| `ac0a8c5` | feat(parser): 업체포맷 E2E 통합 + **무력 LLM 검증 제거** (demo_inputs 10개 골든) |
| `a8d17e4` | feat(graph): multi-file async parser merge + hil_1 resume falsy-fix |
| `d317be9` | Merge branch 'A_Track' (2026-06-01) |

**골든**: 통합 byte-identical (`act=1193 / bp=99 / job=975 / equip=1111`) + 업체 골든 (`act=33 / bp=1 / job=76 / equip=68`).

baseline 이전 흡수 commit (이미 반영, 참고용):
- D-12: `55cad90` (collector_node + parser_node 분리) / `6b9db7c` (state-key drift)
- 702ac06 / 05426ad / ae144a2 / 83b32f3 (4 시트 refactor)
- 15c58bf (split_company_and_zone / extract_zone)
- 888e927 (caller parser_llm → parse_daily_report)
- 83b61ec (transform_bp_summaries today_incr_total fix)

---

*최종 수정: 2026-06-01 — parser 헤더기반 다포맷 7-task (issue#52 컬럼시프트 garbage 해소, 시트4 `_resolve_sheet4_columns`/`_build_activity`, BP 다중 패턴, 시트2/3 final_flag 조건부 게이트, LLM 검증 wrapper 제거) + parser_node async N병렬 multi-file `_merge_reports` 흡수. baseline `1ba783f → d317be9`.*
*이전 수정: 2026-05-26 — D-12 graph 진입점 분리 (collector_node + parser_node) 흡수, IMAP IDLE listener 구조 추가.*
