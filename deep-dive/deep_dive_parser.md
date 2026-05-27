# Deep Dive — Parser Subsystem

- **Generated**: 2026-05-26 (D-12 graph entry split — collector_node + parser_node 신설 후 갱신)
- **Git baseline → HEAD**: `ef7c6cd` (2026-05-20 origin sync) → `1ba783f` (2026-05-26 A_Track)
- **Pair docs**:
  - `./architecture_overview.md` (시스템 다이어그램)
  - `./design-intent/design_intent_parser.md` (T1/T2 카드)
- **Range**:
  - `pipeline/agents/parser.py` (760 LOC)
  - `pipeline/agents/parser_post.py` (201 LOC)
  - `pipeline/agents/parser_llm.py` (660 LOC, **DEPRECATED 2026-05-20**)
  - `pipeline/agents/parser_node.py` (25 LOC, D-12 신규)
  - `pipeline/agents/collector.py` (70 LOC, legacy)
  - `pipeline/agents/collector_node.py` (63 LOC, D-12 신규)
  - `pipeline/collector/filename_parser.py` (64 LOC)
  - `pipeline/collector/idle_worker.py` (260 LOC)
  - `pipeline/collector/config.py` (68 LOC)

---

## 1. Overview

Parser 서브시스템은 작업일보 xlsx 1개를 **4 시트** (`1.출력인원 현황` / `2.직종별 인원현황` / `3.장비현황` / `4.물량`) 통합 `ParsedDailyReport` (TypedDict) 로 변환한다. 핵심 entry 는 `parse_daily_report(xlsx_path)` 1개 — 동기 함수, openpyxl rule-based 추출 ~5초 + 선택적 LLM 검증 wrapper ~15초 = total ~20초 / cycle / 첨부 1건.

핵심 아이디어 4 가지:

1. **rule-based 우선**: openpyxl 으로 셀 좌표 + 정규식 + merged range 분석. 결정성 보장. 같은 xlsx → 같은 output.
2. **LLM 검증 wrapper** (`_verify_sheet1_via_llm` / `_verify_sheet4_via_llm`): rule 추출 결과를 Azure gpt-5.1 에게 보여주고 "명확한 mis-parse" 만 보고 받음. issues 는 **stderr 로그만** — DB 적재 X, rule 본문 변경 X. 결정성 보존.
3. **env opt-out** `CPIA_PARSER_VERIFY_LLM=off` → LLM 검증 skip. default on.
4. **parser_post 공통 정제** (`split_company_and_zone` / `extract_zone` / `pair_bp_summaries` / `transform_bp_summaries`): rule path 와 deprecated LLM path 양쪽이 같은 정제 pipeline 통과.

`parse_daily_report` 는 graph 의 `parser_node` (D-12 신규, 1-line wrapper) 가 호출. 그 앞 단계는 `collector_node` (D-12 신규) — `state["input_files"][0]` 경로 검증 + `parse_filename` 으로 (bp_name / date / project) 분해 + `collector_inbox` UPDATE.

본 cycle 의 주요 변경 (baseline `ef7c6cd` → HEAD `1ba783f`) 는 **parser 자체 코드보다 graph 진입점 분리**:
- `55cad90 feat(graph): D-12 collector_node + parser_node — graph 진입점이 collector`
- `6b9db7c fix(graph): D-12 state-key drift — parsed_reports→parsed, report_date→date`
- 5/20 이전 5 commit (702ac06 / 05426ad / ae144a2 / 83b32f3 / d3b1418 — 4 시트 refactor + LLM 검증) 은 이미 design_intent_parser.md 에 흡수됨.

---

## 2. 파일 목록 + LOC

| 파일 | LOC | 역할 | 상태 |
|---|---:|---|---|
| `pipeline/agents/parser.py` | 760 | 4 시트 rule-based 추출 + 공개 API `parse_daily_report` + 시트1/4 LLM 검증 wrapper | active |
| `pipeline/agents/parser_post.py` | 201 | 회사명/zone 정규화 + BP 코드 pair + raw → entity transform | active |
| `pipeline/agents/parser_llm.py` | 660 | LLM chunk parsing 기반 `parse_daily_report_llm` (async) | **DEPRECATED 2026-05-20** — 코드 보존 |
| `pipeline/agents/parser_node.py` | 25 | graph 노드 wrapper — `parse_daily_report` 1-줄 호출 + log | active (D-12) |
| `pipeline/agents/collector.py` | 70 | legacy: `discover_daily_reports` + `collect_and_parse` (asyncio.Semaphore 4 병렬) | active (CLI / run_one_cycle 만) |
| `pipeline/agents/collector_node.py` | 63 | graph 진입 노드 — `input_files[0]` 검증 + filename_parser + collector_inbox UPDATE | active (D-12) |
| `pipeline/collector/filename_parser.py` | 64 | 첨부 파일명 → `ParsedFilename(kind/project/bp_name/trade/zone/date)` | active |
| `pipeline/collector/idle_worker.py` | 260 | IMAP IDLE listener — UNSEEN fetch → 첨부 추출 → `collector_inbox` INSERT → `run_for_attachment` fire-and-forget | active (FastAPI startup task) |
| `pipeline/collector/config.py` | 68 | `CollectorConfig` env 로드 + fail-fast 자격증명 검증 | active |

**합계**: 9 파일 / 2,171 LOC.

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
                        |  state.input_files = [path]   |
                        +--------------+----------------+
                                       | START -> collector
                                       v
+--------------------------------+   +--------------------------------+
|  collector_node                |   |  parser_node (1-line wrapper)  |
|  (collector_node.py:16)        |-->|  (parser_node.py:15)           |
|  - path exists 검증            |   |  - parse_daily_report(path)    |
|  - parse_filename(name)        |   |  - log bp_summaries / activities|
|  - collector_inbox UPDATE(run) |   |  - return {"parsed": report}   |
|  - return {bp_name,date,project}|  +--------------+----------------+
+--------------------------------+                  |
                                                    v
                                  +-----------------+-----------------+
                                  |  parse_daily_report (parser.py:539)|
                                  |  openpyxl.load_workbook(data_only) |
                                  |  required_sheets 4종 검증           |
                                  |  _extract_meta -> (date, project)  |
                                  +-----------------+------------------+
                                                    |
              +-------------------+-----------------+-----------------+-------------------+
              v                   v                                   v                   v
   +----------+-----+   +--------+--------+                   +------+-------+   +------+------+
   | 시트1 BPSummary |   | 시트2 JobAlloc  |                   | 시트3 EqAlloc |   | 시트4 Act    |
   | parser.py:127  |   | parser.py:255   |                   | parser.py:428|   | parser.py:346|
   | col 30 merged  |   | col 4='Mm01' +  |                   | col 2+3+4 +  |   | ffill 4 cols |
   | group boundary |   | col 25='O' grp  |                   | col 25='O'   |   | (3,4,5,6)    |
   | + BP/회사 pair |   | (관리자 filter) |                   |              |   | col 8=work   |
   +-------+--------+   +--------+--------+                   +------+-------+   +------+------+
           |                     |                                   |                  |
           v                     v                                   v                  v
   +-------+--------+   +--------+--------+                   +------+-------+   +------+------+
   |split_company_  |   | _shift_dict_row|                   |_shift_dict_  |   | extract_zone |
   |  and_zone +    |   |  yest/incr/cum |                   |  row x3      |   | + normalize_ |
   |extract_zone +  |   |  (3 시간대)    |                   |              |   |   company    |
   |normalize_      |   |                |                   |              |   |              |
   |  company       |   |                |                   |              |   |              |
   +-------+--------+   +--------+--------+                   +------+-------+   +------+------+
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
                                          |
                       _should_verify_llm() ? (env CPIA_PARSER_VERIFY_LLM)
                                          |
                          +---------------+---------------+
                          | yes (default)                 | no
                          v                               |
              +-----------+------------+                  |
              |_verify_sheet1_via_llm  |                  |
              |  - Azure gpt-5.1       |                  |
              |  - JSON {"issues":[]}  |                  |
              |  - stderr 로그만       |                  |
              +-----------+------------+                  |
              +-----------+------------+                  |
              |_verify_sheet4_via_llm  |                  |
              |  - sample 선정 logic   |                  |
              |  - stderr 로그만       |                  |
              +-----------+------------+                  |
                          |                               |
                          +---------------+---------------+
                                          |
                                          v
                              +-----------+------------+
                              | return ParsedDailyReport|
                              | (parsed → state["parsed"])
                              +-----------+------------+
                                          |
                                          v   (D-12 state-key fix `6b9db7c`)
                              +-----------+------------+
                              |  mapper_node           |
                              |  state["parsed"] 사용  |
                              +------------------------+
```

---

## 4. Public + Private 함수 전수 표

### parser.py (760 LOC)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `ParseError` | parser.py:33 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 |
| `_normalize_unit` | parser.py:50 | `(s: str) -> str` | 단위 대소문자 통일 (M2→m2) |
| `_disc_abbrev_to_kr` | parser.py:55 | `(abbrev: str\|None) -> str\|None` | 공종 약자 → 한글 (AR→건축 등) |
| `_is_admin_job` | parser.py:62 | `(job_type: str) -> bool` | 관리자 직종 noise 판정 (BP소장 등) |
| `_is_total_row` | parser.py:67 | `(row: tuple) -> bool` | 시트2 합계 row 판정 |
| `_ffill` | parser.py:75 | `(rows, header_end, fill_cols) -> list[tuple[int, list]]` | 헤더 이후 row forward-fill (병합 셀) |
| `_is_bp_code` | parser.py:103 | `(v: object) -> bool` | `^PH[_\- ]?X[_\- ]?\d+$` 정규식 |
| `_safe_int` | parser.py:109 | `(v: object) -> int` | None / 비정수 → 0 |
| `_shift_dict_sum` | parser.py:118 | `(ws, start, end, col_start) -> TimeShiftCounts` | 6 칸 시간대 group 합 (시트1) |
| `_parse_sheet1_bp_summaries` | parser.py:127 | `(ws) -> list[BPSummary]` | 시트1 — col 30 merged group boundary |
| `_shift_dict_row` | parser.py:247 | `(ws, r, col_start) -> TimeShiftCounts` | 6 칸 시간대 단일 row (시트2/3) |
| `_parse_sheet2_job_allocations` | parser.py:255 | `(ws) -> list[JobAllocation]` | 시트2 — Mm01 + col 25='O' group |
| `_safe_num` | parser.py:335 | `(v: object) -> float\|None` | None / 비수치 → None |
| `_parse_sheet4_activities` | parser.py:346 | `(ws) -> list[Activity]` | 시트4 — ffill 4 columns + col 8=work |
| `_parse_sheet3_equipment_allocations` | parser.py:428 | `(ws) -> list[EquipmentAllocation]` | 시트3 — col 2+3+4 + col 25='O' |
| `_extract_meta` | parser.py:506 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → (report_date ISO, project) |
| `parse_daily_report` | parser.py:539 | `(xlsx_path: Path\|str) -> ParsedDailyReport` | **공개 API** 4 시트 통합 + LLM 검증 |
| `_should_verify_llm` | parser.py:591 | `() -> bool` | env `CPIA_PARSER_VERIFY_LLM` 판정 (default on) |
| `_verify_sheet1_via_llm` | parser.py:597 | `(ws, bp_summaries) -> None` | 시트1 LLM 검증 (8 error path graceful) |
| `_verify_sheet4_via_llm` | parser.py:679 | `(ws, activities) -> None` | 시트4 sample LLM 검증 (8 error path) |

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

### parser_node.py (25 LOC, D-12)

| Function | file:line | Signature | 한 줄 역할 |
|---|---|---|---|
| `parser_node` | parser_node.py:15 | `(state: CPIAState) -> dict[str, Any]` | `parse_daily_report(state.input_files[0])` 1-줄 wrapper + log |

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

### 5.1 시트1 — `_parse_sheet1_bp_summaries` (parser.py:127)

**입력 가정**: `read_only=False` 모드 ws (merged_cells.ranges 필요). 시트명 `1.출력인원 현황`.

**핵심 로직**:
1. col 30 (금일 투입 그룹 Total) merged range 수집 — 값 있는 좌상단만.
2. solo row (merged 가 아니면서 col 30 값 있는 row) 식별.
3. solo + 다음 row 흡수 패턴: 다음 row 가 col 5 채워있고 col 30 None 이면 회사명 단독 row 로 보고 absorb.
4. group range 정렬 후 각 group 안에서 BP 코드 row + 회사명 row 분리, work_text_yesterday/today/tomorrow 합치기 (col 7/8/9).
5. `split_company_and_zone` + `normalize_company` 로 회사명 정규화, `extract_zone(col 6)` 로 zone 결정.
6. `_shift_dict_sum` 으로 4 시간대 그룹 (yesterday_incr col 10 / yesterday_cum col 17 / today_incr col 24 / today_cum col 31) 합산.
7. skip 조건: bp_code None & company None (sub-section 합계), 또는 company None & cum=0 & incr=0 (빈 placeholder).

**핵심 코드** (parser.py:141-173):

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

### 5.2 시트2 — `_parse_sheet2_job_allocations` (parser.py:255)

**G24 fix**: 이전 버전은 grand_total col 24 cross-check 를 강제했으나, 현재는 cross-check 만 수행하고 mismatch 시 silent (불일치 시 미사용).

**핵심 로직**:
1. group 시작 row 식별: col 4='Mm01' + col 25='O' + col 2 (공종) 채워있음 + col 3 = PH_X-NNN 패턴.
2. starts list 기반으로 group range 결정 (다음 start - 1 까지).
3. 회사명: group 시작 다음 5 row 안의 첫 col 3 한글값 (BP 코드 아닌 것).
4. 각 row 에서 col 4 (코드) 와 col 25='O' 통과한 것만 — `Mm##` → manager_code, 그 외 → worker_code.
5. `_is_admin_job` (BP소장 / 공사관리자 / 안전관리자 / 품질관리자 / 일반관리자) filter — sub-pipeline 호환.
6. 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19.

**핵심 코드** (parser.py:267-280):

```python
starts: list[int] = []
for r in range(6, ws.max_row + 1):
    c4 = ws.cell(r, 4).value
    if c4 != "Mm01":
        continue
    c2 = ws.cell(r, 2).value
    c3 = ws.cell(r, 3).value
    c25 = ws.cell(r, 25).value
    if c25 != "O" or c2 is None or c3 is None:
        continue
    if not _BP_RE.match(str(c3).strip()):
        continue
    starts.append(r)
```

---

### 5.3 시트3 — `_parse_sheet3_equipment_allocations` (parser.py:428)

**핵심 로직**:
1. group 시작 row 식별: col 2 (공종) + col 3 (PH_X-NNN) + col 4 (장비 대분류) 모두 채워있음.
2. **헤더 reprint row 회피**: col 2 에 "장비 투입" 문자열 포함되면 skip.
3. 회사명: group 안 첫 col 3 한글값 (BP 코드 제외).
4. 장비 row = col 25='O' + col 4 채워있음.
5. 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19.
6. subtotal 없음 → cross-check 불요.

**핵심 코드** (parser.py:440-455):

```python
starts: list[int] = []
for r in range(6, ws.max_row + 1):
    c2 = ws.cell(r, 2).value
    c3 = ws.cell(r, 3).value
    c4 = ws.cell(r, 4).value
    if c2 is None or c3 is None or c4 is None:
        continue
    if not _BP_RE.match(str(c3).strip()):
        continue
    if "장비 투입" in str(c2):  # 헤더 reprint row 회피
        continue
    starts.append(r)
```

---

### 5.4 시트4 — `_parse_sheet4_activities` (parser.py:346)

**핵심 로직**:
1. row 단위 stream — current_trade / current_bp_code / current_company_raw 3 state forward-fill.
2. col 4 (공종) 채워있으면 current_trade 갱신.
3. col 5 (BP 코드) 채워있으면 current_bp_code 갱신 + col 6 회사명 갱신.
4. Activity row = col 8 (work_content) 채워있는 row 만.
5. `extract_zone(col 7)` 옵션 2 보수 매칭 — scope 텍스트의 명시적 FAB/CUB 토큰만.
6. 수치 컬럼: col 10 plan_total_qty / col 11 yesterday_cum_qty / col 12 today_qty / col 13 today_cum_qty / col 14 progress_percent.

**핵심 코드** (parser.py:362-396):

```python
for r in range(5, ws.max_row + 1):
    c4 = ws.cell(r, 4).value
    c5 = ws.cell(r, 5).value
    c6 = ws.cell(r, 6).value

    if c4 is not None:
        current_trade = str(c4)
    if c5 is not None:
        current_bp_code = str(c5).strip()
        current_company_raw = str(c6) if c6 is not None else None

    c8 = ws.cell(r, 8).value
    if c8 is None:
        continue  # Activity row 아님

    c7 = ws.cell(r, 7).value   # Scope
    c10 = _safe_num(ws.cell(r, 10).value)  # plan_total
    ...
    activities.append({...})
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

## 7. LLM 검증 wrapper

### 7.1 env flag 및 default

- env var: `CPIA_PARSER_VERIFY_LLM`
- default: **on**
- opt-out: `off` / `false` / `0` / `no` (case-insensitive, parser.py:593)
- 판정 함수: `_should_verify_llm()` parser.py:591

```python
def _should_verify_llm() -> bool:
    v = os.environ.get("CPIA_PARSER_VERIFY_LLM", "on").lower().strip()
    return v not in ("off", "false", "0", "no")
```

### 7.2 검증 대상 시트

| 시트 | 함수 | 호출 시점 | sample 크기 | max_tokens | timeout |
|---|---|---|---|---:|---:|
| 시트1 (BPSummary) | `_verify_sheet1_via_llm` (parser.py:597) | parse 끝, return 전 | 전체 raw_rows (col 5 있는 모든 row + bp_summaries 전체) | 2000 | 30s |
| 시트4 (Activity) | `_verify_sheet4_via_llm` (parser.py:679) | parse 끝, return 전 | 첫 10 + 의심 (zone None / plan None / work≤3 글자) 각 5 + 마지막 5 | 1500 | 30s |

시트2 (Job) / 시트3 (Equipment) 는 검증 X — rule 추출 정확도 입증됨 (V1 시트2 0 warnings).

### 7.3 LLM 모델 및 호출 형태

- **endpoint**: env `AZURE_OPENAI_ENDPOINT` (skep-ai-board-for-test-foundry)
- **api_key**: env `AZURE_OPENAI_API_KEY`
- **api_version**: env `AZURE_OPENAI_API_VERSION`
- **model**: env `LLM_MODEL` (기본 `gpt-5.1-chat-ai-board-test`)
- **호출**: `client.chat.completions.create(response_format={"type": "json_object"})`
- **payload**: system prompt (rule 결과 검증 지시) + user (JSON `{"rule_results": [...], "raw_rows": [...]}`)
- **응답**: `{"issues": [{"row": N, "field": "...", "current": "...", "expected": "...", "why": "..."}]}`
- **side effect**: issues 를 `stderr` 로 print — **DB 적재 X / rule 본문 변경 X** (결정성 보존)

### 7.4 8 종 error path graceful catch

`_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` 모두 spec §2.6.4 따라 cycle block 방지 broad catch:

1. 빈 input (`bp_summaries` / `activities` 가 비어있으면 early return)
2. API key 없음 (`os.environ["AZURE_OPENAI_ENDPOINT"]` KeyError → 외부 except 잡힘)
3. timeout 30s
4. `finish_reason == "length"` → stderr 로그 후 return
5. `finish_reason == "content_filter"` → stderr 로그 후 return
6. `JSONDecodeError` → stderr 로그 후 return
7. broad `Exception` (`noqa: BLE001`) → stderr 로그
8. schema 위반 (issues 키 없음) → `.get("issues", [])` 으로 silent

### 7.5 비용 cap (spec §2.6.4)

- 시트1 검증: ~$0.5/cycle (raw_rows 전체 + bp_summaries 전체 input)
- 시트4 검증: ~$0.05/cycle (sample 약 25건만)
- 자동 차단 미구현 — 초과 risk 시 `CPIA_PARSER_VERIFY_LLM=off` 수동 opt-out

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
3. **chunked LLM call retry 패턴** (`_llm_extract_sync` parser_llm.py:389): 4 retry trigger (JSON parse 실패 / length / content_filter / empty list) — 향후 검증 wrapper 강화 시 참조 가능.

### 8.4 제거 backlog

design_intent_parser.md 표시: issue #N8 — env flag deprecation 후 다음 cycle 제거.

---

## 9. parser_node + collector_node 관계 (D-12)

### 9.1 graph 호출 순서

`pipeline/graph.py:605-627` 발췌:

```python
graph.add_node("collector", _collector)   # collector_node.collector_node
graph.add_node("parser", _parser)         # parser_node.parser_node
graph.add_node("mapper", _mapper)
graph.add_node("hil_1", _hil_1)
graph.add_node("atomizer", _atomizer)
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

### 9.3 parser_node 책임 (parser_node.py:15-25)

```python
def parser_node(state: CPIAState) -> dict[str, Any]:
    path = Path(state["input_files"][0])
    report = parse_daily_report(path)
    log.info("parser_node: %s 파싱 완료 (bp_summaries=%d, activities=%d)",
             path.name, len(report["bp_summaries"]), len(report["activities"]))
    return {"parsed": report}
```

**1-줄 wrapper** — 단일 책임:
- `parse_daily_report(path)` 호출 (sync)
- log + return `{"parsed": report}`
- internal parser.py 변경 0 (D-3 spec: 1 첨부 = 1 ParsedDailyReport)

### 9.4 state-key drift fix (6b9db7c)

`parser_node` return key 가 `parsed_reports` (list) → `parsed` (single dict) 로, `report_date` → `date` 로 통일. mapper 가 `state["parsed"]` 로 읽음.

---

## 10. legacy collector.py vs collector_node.py vs idle_worker.py 정리

세 모듈은 책임이 다름 — 한 cycle 안에서 두 개 이상 같이 안 쓰임.

| 모듈 | 진입 경로 | 동기/비동기 | 책임 | 호출자 |
|---|---|---|---|---|
| `pipeline/agents/collector.py` | CLI 배치 (run_one_cycle) | async | 디렉토리 walk + N xlsx Semaphore 병렬 파싱 → `list[ParsedDailyReport]` | `scripts/run_one_cycle.py` |
| `pipeline/agents/collector_node.py` | graph 안 (D-12) | async | `state.input_files[0]` 검증 + filename 분해 + `collector_inbox` UPDATE | `graph.build_graph()` |
| `pipeline/collector/idle_worker.py` | FastAPI startup task | async | IMAP IDLE listener → 첨부 추출 → `collector_inbox` INSERT → `run_for_attachment` (graph fire-and-forget) | `pipeline/api.py` startup |

**흐름 차이**:

- **Prod (IMAP)**: `idle_worker.idle_loop` → 메일 도착 → `_process_one` 이 첨부 1개당 `create_task(run_for_attachment)` → `graph.ainvoke(state={input_files: [path], message_id, ...})` → graph 안에서 `collector_node` → `parser_node` 차례 실행. `legacy collector.py` 는 호출 안 됨.
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

**Parser 채움 (시트4 원천)**:

| 필드 | 타입 | col |
|---|---|---|
| `zone` | str \| None | col 7 extract_zone |
| `bp_code` | str \| None | ffill col 5 |
| `company` | str | ffill col 6 normalize |
| `scope` | str \| None | col 7 원본 |
| `trade` | str | ffill col 4 |
| `work_content` | str | col 8 |
| `unit` | str | col 9 normalize |
| `plan_total_qty` | float \| None | col 10 |
| `yesterday_cum_qty` | float \| None | col 11 |
| `today_qty` | float | col 12 (default 0.0) |
| `today_cum_qty` | float \| None | col 13 |
| `progress_percent` | float \| None | col 14 |
| `remaining_qty` | float \| None | None (PoC) |
| `remaining_percent` | float \| None | None (PoC) |
| `note` | str \| None | None (PoC) |
| `l5_disc` | str | trade (현재 동일) |

**업체별 일보 추가 (통합 일보엔 None)**:
- `work_location_code`, `wbs_mid_name`, `wbs_sub_name`, `wbs_detail_name`

**Mapper 이후 채움**:
- `wbs_activity_id` (PoC: None — 1:N), `l6_main`, `l7_sub` (PoC: None), `l7_5_activity` (PoC: None), `sub_work_area` (PoC: None), `conditions`, `assigned_workers`, `worker_source` (`parsed` / `mh_prorated` / `user_corrected`), `plan_mh`, `wa`, `mapping_conf`, `mapping_source`, `requires_review`.

**Parser 초기값** (parser.py:388-423):
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
| parser.py:557 | 4 시트 중 하나라도 누락 | `ParseError(f"시트 누락: {missing}")` |
| parser.py:516 | 파일명에서 날짜 추출 실패 | `ParseError(f"파일명에서 날짜 추출 실패: ...")` |
| parser.py:534 | project 추출 실패 | `ParseError(f"project 추출 실패: ...")` |

상위 caller (`parser_node` / `collect_and_parse`) 가 raise 전파. graph 안에서는 `run_for_attachment` (idle_worker.py:130) 가 broad `except Exception` 으로 잡아 `collector_inbox.parse_status="failed", error=str(e)[:1000]` UPDATE.

### 12.2 Soft warning (LLM 검증 issues)

- 위치: `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` 의 모든 issues
- 동작: **`stderr` 로 print** (parser.py:665-670, 748-753)
- DB 적재: **미구현** — backlog (issue #N7, `parser_reports.warnings_jsonb` 컬럼 추가 후 적재 예정)
- 형식:
  ```
  [parser:sheet1] LLM 검증 issue: row=42 field=zone current=FAB expected=null reason=...
  [parser:sheet4] LLM 검증 issue: work=거푸집 설치 field=plan_total_qty current=None expected=120 reason=...
  ```

### 12.3 LLM 검증 graceful catch (8 종)

§7.4 참조. 모든 error path 가 stderr 로그만 남기고 `parse_daily_report` 본문은 계속 진행 — **cycle block 방지** spec §2.6.4.

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

| 호출 | 모델 | 호출 회수 / cycle | 비용 | trigger |
|---|---|---:|---:|---|
| `_verify_sheet1_via_llm` | `LLM_MODEL` (gpt-5.1) | 1 | ~$0.5 | `_should_verify_llm() and bp_summaries 비어있지 않음` |
| `_verify_sheet4_via_llm` | `LLM_MODEL` (gpt-5.1) | 1 | ~$0.05 | `_should_verify_llm() and activities 비어있지 않음` |

**Total: 2 호출 / cycle / xlsx 1건, ~$0.55**.

env `CPIA_PARSER_VERIFY_LLM=off` 시 0 호출.

### 13.2 DEPRECATED 호출 (parser_llm path)

| 호출 | 모델 | 호출 회수 / cycle | 비용 |
|---|---|---:|---:|
| `_llm_extract_chunked` x 6 시트 x ~45 chunk | gpt-5.1 | ~270 | ~$3 (통합) / ~$0.05 (업체별) |

현재 호출 안 됨 — caller 전부 `parse_daily_report` 로 교체 (commit `888e927`).

### 13.3 호출 형태 공통 사양

- async / sync: 검증 wrapper 는 **동기** (`client.chat.completions.create` 직접 호출, 그러나 `parse_daily_report` 자체가 sync)
- `response_format={"type": "json_object"}` 강제
- `timeout=30` (초)
- `max_completion_tokens=2000` (시트1) / `1500` (시트4)
- retry 없음 — graceful catch 만 (parser_llm 의 `_llm_extract_sync` 는 retry 3, 본 검증 wrapper 는 spec §2.6.4 단순 catch 정책)

---

## 14. 이슈 표

| # | 이슈 | 위치 | 영향 | 상태 |
|---|---|---|---|---|
| 1 | `parser_warning` PG 영속화 미구현 | parser.py:665, 748 | LLM 검증 issues 가 stderr 만 — 운영 환경 알람 X | backlog (issue #N7) |
| 2 | `parser_llm.py` 660 LOC DEPRECATED 잔존 | parser_llm.py | env flag 회귀 path 미구현, 코드만 보존 | backlog (issue #N8) |
| 3 | `BPSummary.disc_abbrev` 시트1 추출 안 됨 | parser.py:230 | 항상 None (시트1 col 에 공종 없음) → mapper 의존 안 함 | by design |
| 4 | `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` 항상 None | parser.py:408-413 | Master List 1:N 제약 | by design (PoC) |
| 5 | `_should_verify_llm` env flag 단일 — 시트1/4 따로 못 끔 | parser.py:591 | 비용 분리 제어 불가 | minor |
| 6 | LLM 검증 비용 cap 자동 차단 없음 | parser.py:597, 679 | $/cycle 초과 risk 시 수동 opt-out 만 | spec §2.6.4 명시 |
| 7 | 시트2 raw company suffix (`창원기전CUB(22.9kV)`) zone 활용 미구현 | parser.py:255 | 시트2 group 의 zone 정보 손실 | spec §8 |
| 8 | `BPSummary.work_text_today` BP 별 분리 안 됨 | parser.py:202-207 | group 안 row work_text 통합 (`|` join) | spec §8 |
| 9 | 다른 사이트 일보 양식 (col 좌표 다름) 미지원 | parser.py 전체 | M15X 양식 hardcoded | spec §8 |
| 10 | LLM 검증 retry 없음 (timeout/rate-limit 1회 실패) | parser.py:637, 720 | issues 한 cycle 손실 — 결정성/단순성 우선 | by design (spec §2.6.4) |
| 11 | `read_only=False` 모드 (메모리 부하) — 시트1 merged_cells.ranges 필요 | parser.py:553 | 큰 xlsx 메모리 risk | 현재 PoC 양식 OK |
| 12 | `Mm##` 패턴이 시트2/3 group boundary — 다른 코드 체계 호환 X | parser.py:271 | "Mm01" 문자열 hardcoded | by design (POC 양식) |
| 13 | `_extract_meta` 의 project 추출이 시트1 첫 3 row 의 "M15X/IBL/PJT" substring 매칭 | parser.py:521-526 | 다른 사이트명 미지원 | spec §8 |
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

---

## 16. 본 cycle 변경 사항 (ef7c6cd → 1ba783f)

| Commit | 변경 |
|---|---|
| `5347966` | chore(collector): add aioimaplib + namespace dirs |
| `973fa66` | feat(collector): filename_parser — 첨부 파일명 정규식 (업체별 + 통합) |
| `85155eb` | feat(collector): IDLE loop + run_for_attachment + helpers (no tests yet) |
| `c1cba0f` | test(collector): idle_worker 단위 테스트 + str→date / dead import 픽스 |
| `55cad90` | feat(graph): D-12 collector_node + parser_node — graph 진입점이 collector |
| `6b9db7c` | fix(graph): D-12 state-key drift — parsed_reports→parsed, report_date→date |

**Parser 자체 (parser.py / parser_post.py / parser_llm.py) 코드 변경 0** — 모든 변경이 graph 진입점 및 listener 인프라.

baseline 이전 흡수 commit (design_intent_parser.md 에 이미 반영):
- 702ac06 / 05426ad / ae144a2 / 83b32f3 (4 시트 refactor)
- d3b1418 (LLM 검증 wrapper)
- 15c58bf (split_company_and_zone / extract_zone)
- 888e927 (caller parser_llm → parse_daily_report)
- 999bc05 (parser_llm DEPRECATED 주석)
- 83b61ec (transform_bp_summaries today_incr_total fix)

---

*최종 수정: 2026-05-26 — D-12 graph 진입점 분리 (collector_node + parser_node) 흡수, IMAP IDLE listener 구조 추가.*
