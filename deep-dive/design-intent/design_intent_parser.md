# Design Intent — parser

- **Generated**: 2026-05-26 (D-12 graph 진입점 분리 — `collector_node` + `parser_node` 신설 후 갱신)
- **Git baseline → HEAD**: `ef7c6cd` (2026-05-20 origin sync) → `1ba783f` (2026-05-26 A_Track)
- **Pair files**:
  - `../deep_dive_parser.md` (900 줄, 본 갱신의 raw grounding)
  - `../architecture_overview.md` (시스템 다이어그램)
- **Range** (9 파일 / 2,171 LOC):
  - `pipeline/agents/parser.py` (760 LOC) — **본 cycle 코드 변경 0**
  - `pipeline/agents/parser_post.py` (201 LOC) — **본 cycle 코드 변경 0**
  - `pipeline/agents/parser_llm.py` (658 LOC) — **DEPRECATED 2026-05-20**, 코드 보존
  - `pipeline/agents/parser_node.py` (25 LOC) — **NEW D-12** (`55cad90`, state-key drift fix `6b9db7c`)
  - `pipeline/agents/collector.py` (70 LOC) — legacy CLI 경로 (run_one_cycle 전용)
  - `pipeline/agents/collector_node.py` (63 LOC) — **NEW D-12** graph 진입 노드
  - `pipeline/collector/filename_parser.py` (64 LOC) — **NEW** YYMMDD/YYYYMMDD 파일명 분해
  - `pipeline/collector/idle_worker.py` (260 LOC) — **NEW** IMAP IDLE listener
  - `pipeline/collector/config.py` (68 LOC) — **NEW** env 로드 + fail-fast 자격증명
- **스펙**:
  - `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`
  - `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md`
  - `docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md`

**한 줄 요약**: 작업일보 xlsx 1개 → 4 시트 (출력인원/직종/장비/물량) 통합 `ParsedDailyReport`. 본 cycle 의 핵심 변화는 **parser 본체 코드 변경 0** + **graph 진입점이 `collector_node` → `parser_node` 로 분리** + IMAP IDLE 푸시 listener (`idle_worker`) 신설로 prod 흐름이 "메일 도착 → graph 호출" 완전 자동화된 점. parser 내부 결정성 보장 정책 (rule-based + 시트1/4 LLM 검증, issues 는 stderr 만, DB 적재 X) 유지.

---

## 1. 7 필수 섹션 — Overview

Parser 서브시스템 진입점은 **여전히 `parse_daily_report(xlsx_path)`** (`pipeline/agents/parser.py:539`) 1개. 동기 함수, openpyxl rule-based 추출 ~5초 + 시트1/4 LLM 검증 wrapper ~15초 = total ~20초/cycle/첨부 1건.

본 cycle (`ef7c6cd` → `1ba783f`) 의 6 commit 은 전부 **graph 진입점 + listener 인프라**:

| Commit | 변경 |
|---|---|
| `5347966` | `chore(collector)`: aioimaplib + namespace dirs |
| `973fa66` | `feat(collector)`: filename_parser — 첨부 파일명 정규식 (업체별 + 통합) |
| `85155eb` | `feat(collector)`: IDLE loop + run_for_attachment + helpers |
| `c1cba0f` | `test(collector)`: idle_worker 단위 테스트 + str→date / dead import 픽스 |
| `55cad90` | `feat(graph)`: D-12 `collector_node` + `parser_node` — graph 진입점이 collector |
| `6b9db7c` | `fix(graph)`: D-12 state-key drift — `parsed_reports`→`parsed`, `report_date`→`date` |

`parser.py` / `parser_post.py` / `parser_llm.py` 본문 diff = 0 lines. 모든 변경은 **그 위 레이어** (graph 진입, 메일 listener) 에만.

---

## 2. T1 — Function Index

### 2.1 parser.py (760 LOC) — 본 cycle 코드 변경 0

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `ParseError` | parser.py:33 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 | — |
| `_normalize_unit` | parser.py:50 | `(s: str) -> str` | 단위 대소문자 통일 (M2→m2) | — |
| `_disc_abbrev_to_kr` | parser.py:55 | `(abbrev: str\|None) -> str\|None` | 공종 약자 → 한글 (AR→건축 등) | — |
| `_is_admin_job` | parser.py:62 | `(job_type: str) -> bool` | 관리자 직종 noise 판정 | — |
| `_is_total_row` | parser.py:67 | `(row: tuple) -> bool` | 시트2 합계 row 판정 | — |
| `_ffill` | parser.py:75 | `(rows, header_end, fill_cols) -> list[tuple]` | 헤더 이후 row forward-fill | — |
| `_is_bp_code` | parser.py:103 | `(v: object) -> bool` | `^PH[_\- ]?X[_\- ]?\d+$` 정규식 | — |
| `_safe_int` / `_safe_num` | parser.py:109, 335 | scalar coerce | None/비수치 → 0 또는 None | — |
| `_shift_dict_sum` | parser.py:118 | `(ws, start, end, col_start) -> TimeShiftCounts` | 6 칸 시간대 group 합 (시트1) | — |
| `_shift_dict_row` | parser.py:247 | `(ws, r, col_start) -> TimeShiftCounts` | 6 칸 시간대 단일 row (시트2/3) | — |
| `_parse_sheet1_bp_summaries` | parser.py:127 | `(ws) -> list[BPSummary]` | 시트1 rule — col 30 merged group boundary | ✅ |
| `_parse_sheet2_job_allocations` | parser.py:255 | `(ws) -> list[JobAllocation]` | 시트2 rule — `Mm01` + col 25='O' group | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:428 | `(ws) -> list[EquipmentAllocation]` | 시트3 rule — col 2+3+4 + col 25='O' | ✅ |
| `_parse_sheet4_activities` | parser.py:346 | `(ws) -> list[Activity]` | 시트4 rule — ffill 4 cols + col 8=work | ✅ |
| `_extract_meta` | parser.py:506 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → (report_date ISO, project) | — |
| `parse_daily_report` | parser.py:539 | `(xlsx_path: Path\|str) -> ParsedDailyReport` | **공개 API** 4 시트 통합 + LLM 검증 | ✅ |
| `_should_verify_llm` | parser.py:591 | `() -> bool` | env `CPIA_PARSER_VERIFY_LLM` 판정 (default on) | — |
| `_verify_sheet1_via_llm` | parser.py:597 | `(ws, bp_summaries) -> None` | 시트1 LLM 검증 wrapper (8 error path) | ✅ |
| `_verify_sheet4_via_llm` | parser.py:679 | `(ws, activities) -> None` | 시트4 LLM 검증 wrapper (sample) | — |

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

### 2.3 parser_llm.py (658 LOC) — DEPRECATED 2026-05-20

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `parse_daily_report_llm` | parser_llm.py:503 | `async (xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport` | DEPRECATED chunk LLM path | ✅ |

### 2.4 parser_node.py (25 LOC, NEW D-12)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `parser_node` | parser_node.py:15 | `(state: CPIAState) -> dict[str, Any]` | `parse_daily_report(state.input_files[0])` 1-줄 wrapper | ✅ NEW |

### 2.5 collector.py (70 LOC, legacy CLI)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `CollectorConfig` | collector.py:23 | `dataclass(file_concurrency: int = 4)` | 파일 단위 병렬 환경 | — |
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | 디렉토리 xlsx sorted list | — |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | N xlsx Semaphore 병렬 파싱 | — |

### 2.6 collector_node.py (63 LOC, NEW D-12) + filename_parser.py (64 LOC, NEW)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `collector_node` | collector_node.py:16 | `async (state: CPIAState) -> dict[str, Any]` | input_files[0] 검증 + filename_parser + collector_inbox UPDATE | — |
| `ParsedFilename` | filename_parser.py:15 | `frozen dataclass(kind/project/bp_name/trade/zone/date)` | 첨부 파일명 분해 결과 | — |
| `parse_filename` | filename_parser.py:25 | `(name: str) -> ParsedFilename\|None` | `업체작업일보_` / `통합작업일보_` 정규식 분해 | ✅ NEW |

### 2.7 collector/idle_worker.py (260 LOC, NEW) + config.py (68 LOC, NEW)

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

### 3.1 `parse_daily_report` — 4 시트 통합 공개 API

- **위치**: `pipeline/agents/parser.py:539-583` (45 LOC)
- **시그니처**: `def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport`
- **본 cycle 변경**: **코드 변경 없음**. 단, 호출자 분리 — graph 안에서는 `parser_node` 1-줄 wrapper (`pipeline/agents/parser_node.py:15`) 가 호출, CLI 에서는 `collect_and_parse` (`pipeline/agents/collector.py:52`) 가 `asyncio.to_thread` 로 wrap 호출.
- **설계 의도**:
  - 단일 진입점: pipeline 전체에서 Parser 는 본 함수만 호출 (graph + CLI 양쪽)
  - 결정성 보장: 같은 xlsx → 같은 dict (검증 LLM 은 issues 만 stderr 로그, 본문 변경 X)
  - `_should_verify_llm()` 결정에 따라 시트1/4 검증 호출 (`parser.py:568`)
- **대응 패턴**:
  - 입력: xlsx 절대 경로 (Path 또는 str)
  - 처리: `load_workbook(data_only=True)` → 4 시트 누락 검증 → 각 시트 rule 파서 호출 → meta 추출 → optional LLM 검증
  - 출력: `ParsedDailyReport` (BPSummary[] + JobAllocation[] + EquipmentAllocation[] + Activity[] + worker_outputs=[] + report_meta=None)
- **관련**:
  - graph 호출: `pipeline/agents/parser_node.py:18` (`return {"parsed": report}`)
  - CLI 호출: `pipeline/agents/collector.py:68` (`await asyncio.to_thread(parse_daily_report, path)`)
  - 후속: `mapper_node` 가 `state["parsed"]` 로 읽음 (D-12 state-key drift fix `6b9db7c`)
- **Suspected related**: `_should_verify_llm`, `_verify_sheet1_via_llm`, `_verify_sheet4_via_llm`, `parser_node`

---

### 3.2 `_parse_sheet1_bp_summaries` — col 30 merged group boundary

- **위치**: `pipeline/agents/parser.py:127-244` (118 LOC)
- **시그니처**: `def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]`
- **본 cycle 변경**: **코드 변경 없음** — graph 진입 분리만.
- **이슈** (deep_dive §5.1):
  - col 30 (금일 투입 그룹 Total) merged range 또는 단독 row 가 group boundary
  - BP 코드 row + 회사명 row 인접 pair (옵션 2)
  - company 정규화 = `split_company_and_zone` + `normalize_company`
  - zone = `extract_zone(col 6)` — 옵션 2 보수 매칭
  - sub-section 합계 row skip + 빈 placeholder skip
  - solo merged + 다음 row 흡수
  - **주의**: ws 는 `read_only=False` 모드여야 함 (`merged_cells.ranges` 필요)
  - 기대 산출량: 통합 작업일보 1건 ≈ 99 그룹 → 99 BPSummary
- **설계 의도**:
  - 시트1 의 grouping 은 col 30 (그룹 Total) merged 범위 기준 — col 5 (BP 코드/회사명) 자체로는 boundary 불명확
  - 시트1 출력은 mapper 의 `auto_bp_zone_match` deterministic input → zone 정확도 중요
- **대응 패턴**:
  - 입력: openpyxl ws (시트1, read_only=False)
  - 처리: col 30 merged_cells.ranges 수집 → solo row 식별 → group range 결정 (solo+next 흡수) → 각 group → BPSummary 변환 (`extract_zone` + 6 칸 시간대 합)
  - 출력: `list[BPSummary]` (99건 기대)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:562) 안에서 호출
  - mapper 영향: BPSummary.zone → `resolve_wa` step 1 (`auto_bp_zone_match`) input
- **Suspected related**: `extract_zone`, `split_company_and_zone`, `normalize_company`, mapper `auto_bp_zone_match`

---

### 3.3 `_parse_sheet2_job_allocations` — Mm01 + col 25='O' group boundary

- **위치**: `pipeline/agents/parser.py:255-332` (78 LOC)
- **시그니처**: `def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈** (deep_dive §5.2):
  - group 시작 row 식별: col 4='Mm01' + col 25='O' + col 2 (공종) + col 3 = PH_X-NNN
  - 회사명: group 시작 다음 5 row 안의 첫 col 3 한글값 (BP 코드 아닌 것)
  - 각 row 에서 col 4 (코드) 와 col 25='O' 통과한 것만 — `Mm##` → manager_code, 그 외 → worker_code
  - `_is_admin_job` (BP소장 / 공사관리자 / 안전관리자 / 품질관리자 / 일반관리자) filter — sub-pipeline 호환
  - 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19
  - **G24 fix**: 이전 버전은 grand_total col 24 cross-check 를 강제했으나, 현재는 cross-check 만 수행하고 mismatch 시 silent
- **설계 의도**:
  - `Mm01` 패턴 = 매 group 의 첫 번째 직종 코드 (관리자 코드 시작) → group boundary 의 결정론적 marker
  - col 25='O' = "최종 확정" 표시 — draft row 자동 skip
- **대응 패턴**:
  - 입력: openpyxl ws (시트2)
  - 처리: starts list 식별 → group range 결정 → 회사명 추출 → 각 row 변환
  - 출력: `list[JobAllocation]` (1,597 row 처리 → admin filter 후 600~800건 기대)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:563)
  - mapper 영향: JobAllocation.workers_cum_t → `_prorate_workers_with_mh` 분모
- **Suspected related**: `_is_admin_job`, `_disc_abbrev_to_kr`, `_shift_dict_row`

---

### 3.4 `_parse_sheet3_equipment_allocations` — col 2+3+4 + col 25='O'

- **위치**: `pipeline/agents/parser.py:428-496` (69 LOC)
- **시그니처**: `def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈** (deep_dive §5.3):
  - group 시작 row 식별: col 2 (공종) + col 3 (PH_X-NNN) + col 4 (장비 대분류) 모두 채워있음
  - **헤더 reprint row 회피**: col 2 에 "장비 투입" 문자열 포함되면 skip
  - 회사명: group 안 첫 col 3 한글값 (BP 코드 제외)
  - 장비 row = col 25='O' + col 4 채워있음
  - 3 시간대 group: yesterday_cum col 7 / today_incr col 13 / today_cum col 19
  - subtotal 없음 → cross-check 불요
- **설계 의도**:
  - 시트3 는 시트2 와 같은 group 구조이나 boundary 가 (공종+BP+장비 대분류) 3-key — `Mm##` 같은 단일 marker 없음
  - 헤더가 시트 중간에 재출력되는 경우 ("장비 투입") 가 있어 명시 substring filter 필요
- **대응 패턴**:
  - 입력: openpyxl ws (시트3)
  - 처리: starts → group → 장비 row 변환 (equipment_big/mid/spec + 3 시간대)
  - 출력: `list[EquipmentAllocation]` (1,111 row 기대)
- **관련**:
  - 후속: `parse_daily_report` (parser.py:564)
  - 호출자: 없음 — mapper 는 현재 EquipmentAllocation 미사용 (PoC 1차)
- **Suspected related**: `_shift_dict_row`, `_BP_RE`

---

### 3.5 `_parse_sheet4_activities` — ffill 4 컬럼 + col 8=work

- **위치**: `pipeline/agents/parser.py:346-425` (80 LOC)
- **시그니처**: `def _parse_sheet4_activities(ws) -> list[Activity]`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈** (deep_dive §5.4):
  - row 단위 stream — current_trade / current_bp_code / current_company_raw 3 state forward-fill
  - col 4 (공종) 채워있으면 current_trade 갱신
  - col 5 (BP 코드) 채워있으면 current_bp_code 갱신 + col 6 회사명 갱신
  - Activity row = col 8 (work_content) 채워있는 row 만
  - `extract_zone(col 7)` 옵션 2 보수 매칭 — scope 텍스트의 명시적 FAB/CUB 토큰만
  - 수치 컬럼: col 10 plan_total_qty / col 11 yesterday_cum_qty / col 12 today_qty / col 13 today_cum_qty / col 14 progress_percent
- **설계 의도**:
  - 시트4 는 mapper 의 LLM rerank 입력 + EVM 의 EV 분자 → work_content 정확도 중요
  - ffill 의 컬럼 4개 결정성: 헤더 이후 병합 셀 = 직전 row 값 전파 (1,193 row → 79+ activities)
  - `worker_source = "parsed"` 초기값 (parser.py:417) — mapper 가 `mh_prorated` / `user_corrected` 로 덮어씀
- **대응 패턴**:
  - 입력: openpyxl ws (시트4)
  - 처리: row 단위 ffill stream → col 8 None 이면 skip → Activity dict 생성 (39 필드 중 16개 채움, 나머지 None/default)
  - 출력: `list[Activity]` (79+건)
- **관련**:
  - 후속: `_verify_sheet4_via_llm` (default on) — 의심 case + sample LLM 검증
  - mapper 영향: Activity → `map_activity` (`build_embedding_input` + `build_llm_input`)
- **Suspected related**: `_verify_sheet4_via_llm`, `extract_zone`, `normalize_company`, `_safe_num`

---

### 3.6 `_verify_sheet1_via_llm` — 시트1 LLM 검증 wrapper (8 error path)

- **위치**: `pipeline/agents/parser.py:597-676` (80 LOC)
- **시그니처**: `def _verify_sheet1_via_llm(ws, bp_summaries: list[BPSummary]) -> None`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈**:
  - docstring (parser.py:598): "spec §2.6.1 — 시트1 rule 결과 LLM 검증. issues 는 stderr 로그만 (결정성 보존)."
  - 8 종 error path graceful catch (timeout 30s / length / content_filter / JSONDecodeError / Exception broad / 빈 input / API key 없음 / schema 위반)
  - 비용 cap: ~$0.5/cycle (spec §2.6.4) — **자동 차단 미구현** (issue #6)
  - max_completion_tokens=2000, timeout=30, `response_format={"type": "json_object"}`
- **설계 의도**:
  - rule 결과 신뢰성 검증 — 사용자 push back "scope ≠ wa, 오른쪽 작업으로 wa 판단" 정합
  - **결정성 보존**: issues 는 stderr 로그 (DB 적재 X) → rule output 본문은 LLM 결과로 변경 X
  - opt-out: env `CPIA_PARSER_VERIFY_LLM=off` (default 'on')
- **대응 패턴**:
  - 발동: `parse_daily_report` 끝에서 `_should_verify_llm()` true 시
  - 입력: openpyxl ws (시트1) + rule 추출 bp_summaries 리스트
  - 처리: Azure gpt-5.1 호출 (timeout 30s) → JSON `{"issues": [...]}` parse → stderr log (parser.py:665-670)
  - 출력: None (side effect = stderr 로그)
- **관련**:
  - 시트4 페어: `_verify_sheet4_via_llm` (parser.py:679) — 같은 패턴, 비용 ~$0.05/cycle
  - 미해결 (parser_warning DB 적재): backlog issue #1 — `parser_reports.warnings_jsonb` 컬럼 추가 후 적재
- **Suspected related**: `_should_verify_llm`, `_verify_sheet4_via_llm`

---

### 3.7 `extract_zone` — col 6 (Scope) 옵션 2 보수 매칭

- **위치**: `pipeline/agents/parser_post.py:120-140` (21 LOC)
- **시그니처**: `def extract_zone(v6: str | None) -> str | None`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈** (deep_dive §6.2):
  - 옵션 2 (spec §2.1) 보수 매칭
  - 단일 토큰 'FAB' / 'CUB' → 결정
  - 시작 토큰 ('FAB 전구간', 'CUB 1F~7F') → 결정
  - 양쪽 ('FAB/CUB', 'FAB & CUB') → None (모호)
  - 텍스트 중간 ('M15X FAB F04') → None
- **설계 의도**:
  - 시트1 BPSummary.zone 의 deterministic 활용 — mapper `auto_bp_zone_match` (step 1) 의 input
  - 모호 케이스에서는 명시적 None 반환 → mapper 의 step 2 (`auto_llm_rerank`) fallback
- **대응 패턴**:
  - 입력: col 6 (Scope) raw 문자열
  - 처리: regex 5단계 (양쪽 / 단일 토큰 / 시작 토큰 / 텍스트 중간 / 기타)
  - 출력: "FAB" / "CUB" / None
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries` (parser.py:210), `_parse_sheet4_activities` (parser.py:386)
  - 페어: `split_company_and_zone` (parser_post.py:108) — 회사명 끝 FAB/CUB suffix 분리, zone 정보는 반환 X (옵션 2 정책)
- **Suspected related**: `split_company_and_zone`, mapper `auto_bp_zone_match`

---

### 3.8 `split_company_and_zone` — 회사명 끝 FAB/CUB suffix 분리

- **위치**: `pipeline/agents/parser_post.py:108-117` (10 LOC)
- **시그니처**: `def split_company_and_zone(raw: str | None) -> str | None`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈** (deep_dive §6.1):
  - 옵션 2 (scope ≠ wa): suffix 는 회사명 정규화에만 사용, zone 정보 반환 X
  - 예: '에스비테크CUB' → '에스비테크', '광건티엔씨FAB(수장2)' → '광건티엔씨' (괄호도 normalize 에서 제거)
- **설계 의도**:
  - 회사명 끝 FAB/CUB suffix 가 mapper 의 정확 일치 SQL (`fetch_bp_candidates`) 에서 mismatch 유발 → 정규화 단계에서 제거
  - zone 정보는 명시적 col 6 (`extract_zone`) 만 신뢰 — 옵션 2 보수 정책
- **대응 패턴**:
  - 입력: raw company 문자열
  - 처리: `normalize_company` (㈜ / 괄호 제거) → `_TRAILING_FABCUB_RE` 제거
  - 출력: str 또는 None
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries`, `_parse_sheet2_job_allocations`, `_parse_sheet3_equipment_allocations`, `_parse_sheet4_activities`
  - 페어: `extract_zone` (parser_post.py:120)
- **Suspected related**: `normalize_company`, mapper `fetch_bp_candidates`

---

### 3.9 `transform_bp_summaries` — filter + pair + normalize 4-step (LLM path 정제)

- **위치**: `pipeline/agents/parser_post.py:183-201` (19 LOC)
- **시그니처**: `def transform_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈**:
  - 4-step 파이프라인: `filter_marker_rows(target_key="col_4_value")` → `pair_bp_summaries` → `normalize_company` → company OR bp_code 있어야 통과
  - `83b61ec` commit 에서 `today_incr_total` 필드 누락 fix (mapper KeyError 회피) — 이전 cycle
  - 현재 rule path 는 raw 단계 거치지 않고 직접 entity 생성 (parser.py:226-243) — 본 함수는 **deprecated LLM path 잔존용**
- **설계 의도**:
  - LLM/rule output 공통 정제 — rule 추출 본문은 raw 상태로 두고 정제 단계 분리 (단위 테스트 가능성)
  - LLM path 회귀 시 재활용 가능
- **대응 패턴**:
  - 입력: raw_rows list (BPSummaryRaw, LLM 추출 형식)
  - 처리: 4-step 파이프라인
  - 출력: 정제된 BPSummary list
- **관련**:
  - 현재 호출자: `parser_llm.py` 만 (DEPRECATED)
  - 후속: mapper.py `_prorate_workers_with_mh` (`today_incr_total`) + `build_bp_context`
- **Suspected related**: `pair_bp_summaries`, `filter_marker_rows`

---

### 3.10 `pair_bp_summaries` — 2-row pairing (BP 코드 + 회사명)

- **위치**: `pipeline/agents/parser_post.py:44-89` (46 LOC)
- **시그니처**: `def pair_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **본 cycle 변경**: **코드 변경 없음**.
- **이슈**:
  - docstring: "BP 코드 row (is_bp_code=true) + 다음 회사명 row (is_korean_company=true) + 같은 zone/disc_abbrev → 1 BPSummary 머지. 그 외: each row = 1 BPSummary."
  - rule path 는 이미 group 안에서 직접 처리 (parser.py:185-207) — 본 함수는 LLM path 만 사용
- **설계 의도**:
  - 시트1 의 2-row 그룹 (BP 코드 + 한글 회사명) 패턴이 LLM output 에서 발생 → 정규화 단계에서 머지
  - 정규성 기준: zone + disc_abbrev 일치 (PoC 3사 데이터 검증 통과)
- **대응 패턴**: while-i loop, current row + next row 패턴 매칭 → 머지 또는 single 유지
- **관련**: 호출자 `transform_bp_summaries`
- **Suspected related**: `transform_bp_summaries`, `filter_marker_rows`

---

### 3.11 `parse_daily_report_llm` — DEPRECATED 2026-05-20 (현 cycle 잔존)

- **위치**: `pipeline/agents/parser_llm.py:503` (658 LOC 파일 전체)
- **시그니처**: `async def parse_daily_report_llm(xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport`
- **본 cycle 변경**: **코드 변경 없음**. 본 cycle 의 graph entry (`parser_node`) 에서 호출되지 않음.
- **이슈** (deep_dive §8):
  - 파일 헤더: "본 모듈은 chunk LLM parsing 으로 ParsedDailyReport 를 생성했으나, 5/20 부터 `pipeline.agents.parser.parse_daily_report` (rule-based + 시트1/4 LLM 검증 hybrid) 로 대체됨."
  - 대체 이유: chunk LLM 270 호출 → 4-5 분 / cycle, ~$3 / cycle vs rule + 검증 hybrid → ~20 초 / cycle, ~$0.55 / cycle
  - env flag `CPIA_PARSER=llm` graph entry 안에서 분기 — **미구현** (issue #2, 현재 caller 직접 수정으로만 회귀 가능)
- **설계 의도 (잔존)**:
  - **fallback 경로**: rule path 가 새 양식에서 실패하는 비상 경로 (POC 외 사이트 양식 지원 시)
  - `_sheet_to_payload` 재사용: parser_post 의 transform_* 와 정합
  - chunked LLM call retry 패턴 (`_llm_extract_sync` parser_llm.py:389): 4 retry trigger 향후 검증 wrapper 강화 시 참조 가능
- **대응 패턴**: 현재 호출 X — caller (collector.py, run_one_cycle.py) 가 `parse_daily_report` (rule) 로 교체됨
- **관련**: 페어 `parse_daily_report` (parser.py:539)
- **제거 backlog**: issue #2 — env flag deprecation 후 다음 cycle 제거
- **Suspected related**: `transform_bp_summaries`, `transform_job_allocations`, `transform_equipment_allocations`

---

### 3.12 ★ NEW `parser_node` — D-12 graph 노드 wrapper (state-key drift fix)

- **위치**: `pipeline/agents/parser_node.py:15-25` (11 LOC)
- **시그니처**: `def parser_node(state: CPIAState) -> dict[str, Any]`
- **본 cycle 변경**: **신규 NEW** (`55cad90`, state-key drift fix `6b9db7c`).
- **이슈**:
  - `parse_daily_report(state.input_files[0])` 1-줄 wrapper + log
  - log 형식: `parser_node: <name> 파싱 완료 (bp_summaries=N, activities=M)` (parser_node.py:19-24)
  - 단일 책임: parser.py 내부 변경 0 + graph 진입점만 분리
  - **state-key drift fix `6b9db7c`**: return key 가 `parsed_reports` (list) → `parsed` (single dict) 로 통일. mapper 가 `state["parsed"]` 로 읽음. `report_date` → `date` 도 같이 통일.
- **설계 의도**:
  - D-3 spec 유지 (1 첨부 = 1 ParsedDailyReport)
  - parser.py 의 내부 결정성을 graph 레이어에서 깨지 않게 thin wrapper
  - listener (idle_worker) 가 path 만 박고 메타 분해는 collector_node 가 담당 — parser_node 는 순수 변환만
- **대응 패턴**:
  - 입력: `state["input_files"]` (List[str], first 만 사용)
  - 처리: Path 변환 → `parse_daily_report(path)` (sync, asyncio loop 안에서는 LangGraph 가 thread executor 로 wrap)
  - 출력: `{"parsed": report}` — partial state update
- **관련**:
  - 호출자: `pipeline/graph.py` `graph.add_node("parser", _parser)` (D-12)
  - 직전 노드: `collector_node` (collector_node.py:16)
  - 직후 노드: `mapper_node` — `state["parsed"]` 소비
- **Suspected related**: `parse_daily_report`, `collector_node`, `mapper_node`

---

### 3.13 ★ NEW `filename_parser.parse_filename` — YYYYMMDD/YYMMDD 정규식 분해

- **위치**: `pipeline/collector/filename_parser.py:25-64` (40 LOC)
- **시그니처**: `def parse_filename(name: str) -> ParsedFilename | None`
- **본 cycle 변경**: **신규 NEW** (`973fa66`).
- **이슈**:
  - prefix 2종 hardcoded: `업체작업일보_` 또는 `통합작업일보_` (filename_parser.py:28) — 그 외 모두 None
  - date 토큰: 6자리 (`YYMMDD` → `20YY-MM-DD`) 또는 8자리 (`YYYYMMDD` → `YYYY-MM-DD`), 그 외 None (filename_parser.py:36-41)
  - 통합 모드: `통합작업일보_<project tokens>_<date>.xlsx` — bp_name/trade/zone 모두 None
  - 업체별 모드: `업체작업일보_<project tokens>_<bp_name>_<trade>_<zone>_<date>.xlsx` — 끝 4 토큰 분해, project 는 중간 tokens join
  - 미일치 시 None 반환 → 호출자 (`idle_worker._process_one` line 190) 가 `_to_dead_letter` 로 격리
- **설계 의도**:
  - 메일 첨부의 파일명 규약을 **graph 진입 전** 검증 — 잘못된 파일이 graph 안으로 들어가지 않게 게이트
  - dataclass(frozen=True) — 결정적 hashable 결과 (caching 후보)
  - kind Literal["bp", "integrated"] — 통합/업체별 분기를 caller 에서 명시 if 로 처리 가능
- **대응 패턴**:
  - 입력: 파일 basename (예: `업체작업일보_M15X_PH3_IBL_광건티엔씨_AR_FAB_250925.xlsx`)
  - 처리: stem split('_') → prefix 검증 → date 형식 검증 → kind 별 토큰 분해
  - 출력: `ParsedFilename(kind, project, bp_name, trade, zone, date)` 또는 None
- **관련**:
  - 호출자: `collector_node` (collector_node.py 안에서 검증), `idle_worker._process_one` (idle_worker.py:189)
  - 후속: `_save_to_input_dir` 가 date 로 `data/input/<YYYYMMDD>/` 디렉토리 생성
- **Suspected related**: `collector_node`, `_to_dead_letter`, `_save_to_input_dir`

---

## 4. 변경 사항 정리 (ef7c6cd → 1ba783f, 본 cycle)

| Commit | 변경 | 영향 파일 |
|---|---|---|
| `5347966` | chore(collector): add aioimaplib + namespace dirs | `pipeline/collector/__init__.py`, deps |
| `973fa66` | feat(collector): filename_parser — 첨부 파일명 정규식 (업체별 + 통합) | `pipeline/collector/filename_parser.py` (NEW) |
| `85155eb` | feat(collector): IDLE loop + run_for_attachment + helpers (no tests yet) | `pipeline/collector/idle_worker.py` (NEW), `pipeline/collector/config.py` (NEW) |
| `c1cba0f` | test(collector): idle_worker 단위 테스트 + str→date / dead import 픽스 | `pipeline/tests/test_idle_worker.py` |
| `55cad90` | **feat(graph): D-12 collector_node + parser_node — graph 진입점이 collector** | `pipeline/agents/parser_node.py` (NEW), `pipeline/agents/collector_node.py` (NEW), `pipeline/graph.py` |
| `6b9db7c` | **fix(graph): D-12 state-key drift — parsed_reports→parsed, report_date→date** | `pipeline/agents/parser_node.py`, mapper consumer |

**parser.py / parser_post.py / parser_llm.py 본문 diff = 0 lines.**

baseline 이전 흡수 commit (이전 design_intent_parser.md 에 이미 반영, 본 cycle 변경 아님):
- `702ac06`, `05426ad`, `ae144a2`, `83b32f3` (4 시트 refactor)
- `d3b1418` (LLM 검증 wrapper 신설)
- `15c58bf` (`split_company_and_zone` / `extract_zone` 신설)
- `888e927` (caller `parser_llm` → `parse_daily_report` 교체)
- `999bc05` (parser_llm DEPRECATED 주석)
- `83b61ec` (`transform_bp_summaries` `today_incr_total` fix)

---

## 5. 이슈 표 — 15 이슈 (deep_dive 발견 기반 갱신)

| # | 이슈 | 위치 | 영향 | 상태 |
|---:|---|---|---|---|
| 1 | `parser_warning` PG 영속화 미구현 | parser.py:665, 748 | LLM 검증 issues 가 stderr 만 — 운영 환경 알람 X | backlog (`parser_reports.warnings_jsonb` 컬럼 추가 후 적재) |
| 2 | `parser_llm.py` 660 LOC DEPRECATED 잔존 — env flag 회귀 path 미구현 | parser_llm.py | env flag `CPIA_PARSER=llm` graph entry 분기 없음, caller 직접 수정으로만 회귀 가능 | backlog (다음 cycle 제거 후보) |
| 3 | `BPSummary.disc_abbrev` 시트1 추출 안 됨 | parser.py:230 | 항상 None (시트1 col 에 공종 없음) → mapper 의존 안 함 | by design |
| 4 | `Activity.{wbs_activity_id, l7_sub, l7_5_activity, sub_work_area}` 항상 None | parser.py:408-413 | Master List 1:N 제약 — Mapper 가 채워야 함 | by design (PoC) |
| 5 | `_should_verify_llm` env flag 단일 — 시트1/4 따로 못 끔 | parser.py:591 | 비용 분리 제어 불가 | minor |
| 6 | LLM 검증 비용 cap 자동 차단 없음 | parser.py:597, 679 | $/cycle 초과 risk 시 수동 opt-out 만 (`CPIA_PARSER_VERIFY_LLM=off`) | spec §2.6.4 명시 |
| 7 | 시트2 raw company suffix (`창원기전CUB(22.9kV)`) zone 활용 미구현 | parser.py:255 | 시트2 group 의 zone 정보 손실 | spec §8 |
| 8 | `BPSummary.work_text_today` BP 별 분리 안 됨 — group 안 `\|` join | parser.py:202-207, 233-235 | BP-zone 분리 후에도 work_text 통합 | spec §8 |
| 9 | 다른 사이트 일보 양식 (col 좌표 다름) 미지원 | parser.py 전체 | M15X 양식 hardcoded | spec §8 |
| 10 | LLM 검증 retry 없음 (timeout/rate-limit 1회 실패) | parser.py:637, 720 | issues 한 cycle 손실 — 결정성/단순성 우선 | by design (spec §2.6.4) |
| 11 | `read_only=False` 모드 (시트1 merged_cells.ranges 필요) — 큰 xlsx 메모리 부하 | parser.py:553 | 큰 xlsx 메모리 risk | 현재 PoC 양식 OK |
| 12 | `Mm##` 패턴이 시트2/3 group boundary — 다른 코드 체계 호환 X | parser.py:271, 311 | "Mm01" 문자열 hardcoded | by design (POC 양식) |
| 13 | `_extract_meta` project 추출 — 시트1 첫 3 row 의 "M15X/IBL/PJT" substring 매칭 | parser.py:521-526 | 다른 사이트명 미지원 | spec §8 |
| 14 | `parse_filename` 의 `업체작업일보_` / `통합작업일보_` prefix hardcoded | filename_parser.py:28 | 그 외 파일명 dead_letter 행 | by design |
| 15 | `idle_worker._GRAPH_SEM = Semaphore(2)` — 한 listener 가 동시 graph 2개만 | idle_worker.py:34 | 첨부 N개 동시 도착 시 직렬화 | env `CPIA_COLLECTOR_CONCURRENCY` 로 조정 가능 |

---

## 6. 검증 status (deep_dive §15 동기화)

| Phase | 항목 | 상태 |
|---|---|---|
| V1 (5/20) | 4 시트 rule cross-check (시트2 0 warnings) | 완료 |
| V2 (5/20) | Mapper 5 case simulation (`auto_bp_zone_match` 60% deterministic) | 완료 |
| V3 | 146 case full simulation (POC 3사) | pending |
| V4 | Unit test 12개 (spec §5) | pending |
| V5 | 10 업체 POC 전체 cycle + Reports UI 12 정량 기준 | pending |
| D-12 | `collector_node` / `parser_node` 분리 + state-key drift fix | 완료 (`55cad90`, `6b9db7c`) |
| D-12 test | `test_collector_node.py` 70 LOC + `test_parser_node.py` 29 LOC | 완료 |

---

## 7. 미해결 / Backlog (issue # 매핑)

- **issue #1**: `parser_warning` PG 영속화 — `parser_reports.warnings_jsonb` 컬럼 추가 후 적재
- **issue #2**: `parser_llm.py` 660 LOC 제거 — env flag `CPIA_PARSER=llm` 회귀 path 구현 또는 완전 제거
- **issue #4**: `Activity` 의 `wbs_activity_id` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 필드 Parser 단계에서 항상 None — Mapper Master List 1:N 제약 해소 후 채우기
- **issue #6**: LLM 검증 비용 cap 자동 차단 (현재 spec 명시만, 자동 차단 미구현)
- **issue #7**: 시트2 raw company suffix (`창원기전CUB(22.9kV)`) zone 활용
- **issue #8**: `BPSummary.work_text_today` BP-zone 분리 후에도 group 안 work_text 통합 (`|` join) — BP 단위 분리 검토
- **issue #9**: 다른 사이트 일보 양식 지원 (col 좌표 hardcoded)
- **issue #12**: `Mm##` 패턴 hardcoded — 다른 코드 체계 일보 호환
- **issue #15**: `Semaphore(2)` bottleneck — 첨부 N개 동시 도착 시 throughput 한계 (env tuning 가능)

---

*최종 수정: 2026-05-26 — D-12 graph 진입점 분리 (`collector_node` + `parser_node`) + IMAP IDLE listener (`idle_worker`) 구조 흡수. parser 본체 코드 변경 0, T2 카드 5개 신규 (parser_node, parse_filename) + 기존 카드 "본 cycle 변경 없음" 표기. 이슈 표 15건으로 확장.*
