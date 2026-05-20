# Design Intent — parser

- **Generated**: 2026-05-20 (parser 전면 refactor cycle + parser_post.py + collector.py 신설)
- **Git SHA**: `ef7c6cd` (A_Track HEAD, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**:
  - `pipeline/agents/parser.py` (760 LOC, 이전 306 → 4 시트별 rule-based refactor + LLM 검증 wrapper)
  - `pipeline/agents/parser_llm.py` (658 LOC, **DEPRECATED 2026-05-20** — 코드 보존, env flag `CPIA_PARSER=llm` 회귀)
  - `pipeline/agents/parser_post.py` (201 LOC, NEW — 정규화 + pair + transform)
  - `pipeline/agents/collector.py` (70 LOC, 이전 0 → discover_daily_reports + collect_and_parse)
  - `pipeline/tests/test_parser.py` + `test_parser_post.py` + `test_parser_llm_e2e.py`
- **스펙**:
  - `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`
  - `docs/superpowers/specs/2026-05-19-cpia-reports-parser-mh-design.md`
  - `docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md`
  - `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md`

작업일보 xlsx 1개 → 4시트 (출력인원/직종/장비/물량) 통합 ParsedDailyReport. **openpyxl rule-based 추출 (~5초) + LLM 검증 wrapper (~20초 total, default on, env opt-out)**. parser_llm 의 LLM chunk parsing (4~5분, $3/cycle) 은 deprecated. parser_post 가 LLM/rule output 공통 정제 (normalize_company / split_company_and_zone / extract_zone / pair_bp_summaries / transform_*). collector 는 디렉토리 발견 + asyncio.Semaphore(4) 병렬 호출.

---

## T1 — Function Index

### parser.py (760 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `ParseError` | parser.py:23 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 | — |
| `_normalize_unit` | parser.py:40 | `(s: str) -> str` | 단위 대소문자 통일 | ✅ |
| `_disc_abbrev_to_kr` | parser.py:45 | `(abbrev) -> str\|None` | 공종 약자 → 한글 | ✅ |
| `_is_admin_job` | parser.py:52 | `(job_type: str) -> bool` | 관리자 직종 판정 | ✅ |
| `_is_total_row` | parser.py:57 | `(row: tuple) -> bool` | 시트2 합계 row 판정 | ✅ |
| `_ffill` | parser.py:65 | `(rows, header_end, fill_cols) -> list[tuple]` | 헤더 이후 병합 셀 forward-fill | ✅ |
| `_parse_sheet1_bp_summaries` | parser.py:127 | `(ws) -> list[BPSummary]` | 시트1 rule (col 30 merged group boundary) | ✅ |
| `_parse_sheet2_job_allocations` | parser.py:255 | `(ws) -> list[JobAllocation]` | 시트2 rule (1,597 row) | ✅ |
| `_parse_sheet4_activities` | parser.py:346 | `(ws) -> list[Activity]` | 시트4 rule (1,193 row, ffill 4 컬럼) | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:428 | `(ws) -> list[EquipmentAllocation]` | 시트3 rule (1,111 row) | ✅ |
| `_extract_meta` | parser.py:506 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → report_date, project | ✅ |
| `parse_daily_report` | parser.py:539 | `(xlsx_path: Path \| str) -> ParsedDailyReport` | 4 시트 통합 공개 API (env flag opt-out LLM 검증 포함) | ✅ |
| `_should_verify_llm` | parser.py:591 | `() -> bool` | env `CPIA_PARSER_VERIFY_LLM` 플래그 (default on) | ✅ |
| `_verify_sheet1_via_llm` | parser.py:597 | `(ws, bp_summaries) -> None` | 시트1 LLM 검증 wrapper (8 error path graceful) | ✅ |
| `_verify_sheet4_via_llm` | parser.py:679 | `(ws, activities) -> None` | 시트4 LLM 검증 wrapper | ✅ |

### parser_post.py (201 LOC, NEW)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `filter_marker_rows` | parser_post.py:32 | `(raw_rows, target_key="company_or_bp") -> list[dict]` | 마커 row 제거 (소계/합계) | ✅ |
| `pair_bp_summaries` | parser_post.py:44 | `(raw_rows: list[dict]) -> list[dict]` | 시트1 2-row pairing (BP코드 + 회사명) | ✅ |
| `normalize_company` | parser_post.py:92 | `(raw: str\|None) -> str\|None` | 회사명 정규화 (㈜/괄호 제거) | ✅ |
| `split_company_and_zone` | parser_post.py:108 | `(raw: str\|None) -> str\|None` | 회사명 끝 FAB/CUB suffix 분리 | ✅ |
| `extract_zone` | parser_post.py:120 | `(v6: str\|None) -> str\|None` | col 6 (Scope) → 명시적 FAB/CUB 토큰 | ✅ |
| `transform_job_allocations` | parser_post.py:143 | `(raw_rows: list[dict]) -> list[dict]` | JobAllocationRaw → 최종 JobAllocation | ✅ |
| `transform_equipment_allocations` | parser_post.py:163 | `(raw_rows: list[dict]) -> list[dict]` | EquipmentAllocationRaw → 최종 | ✅ |
| `transform_bp_summaries` | parser_post.py:183 | `(raw_rows: list[dict]) -> list[dict]` | BPSummaryRaw → 최종 (filter+pair+normalize+split) | ✅ |

### parser_llm.py (658 LOC, DEPRECATED 2026-05-20)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `parse_daily_report_llm` | parser_llm.py:501 | `async (xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport` | LLM chunk parsing (DEPRECATED — env flag `CPIA_PARSER=llm` 회귀) | — |

### collector.py (70 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `discover_daily_reports` | collector.py:30 | `(input_dir: Path\|str) -> list[Path]` | input_dir 안 xlsx 재귀 탐색 (sort) | ✅ |
| `collect_and_parse` | collector.py:52 | `async (input_dir, cfg) -> list[ParsedDailyReport]` | N개 xlsx 병렬 파싱 (asyncio.Semaphore(cfg.file_concurrency)) | ✅ |

---

## T2 — Issue Cards

### `parse_daily_report` — 4 시트 통합 공개 API

- **위치**: `pipeline/agents/parser.py:539-589` (51 LOC)
- **시그니처**: `def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport`
- **이슈**:
  - docstring (parser.py:539): "4 시트 rule-based 추출. 기존 11 caller 호환."
  - 시트명 hardcoded — 누락 시 ParseError
  - commit 888e927: "refactor(callers): collector.py + run_one_cycle.py 의 parser_llm → parse_daily_report"
- **설계 의도**:
  - 단일 진입점: pipeline 전체에서 Parser 는 본 함수만 호출
  - LLM 검증 wrapper 통합: `_should_verify_llm()` 결정에 따라 시트1/4 검증 호출
  - 결정성 보장: 같은 xlsx → 같은 dict (검증 LLM 은 issues 만 stderr 로그, 본문 변경 X)
- **대응 패턴**:
  - 발동: Collector → Parser (`collect_and_parse` → `asyncio.to_thread(parse_daily_report, path)`)
  - 입력: xlsx 절대 경로 (Path 또는 str)
  - 처리: load_workbook → 4 시트 누락 검증 → 각 시트 rule 파서 호출 → meta 추출 → optional LLM 검증
  - 출력: ParsedDailyReport (BPSummary[] + JobAllocation[] + EquipmentAllocation[] + Activity[] + meta)
- **관련**:
  - 호출자: `pipeline/agents/collector.py:52`, `scripts/run_one_cycle.py`, `pipeline/tests/test_parser.py`
  - 페어 spec: `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`, `docs/superpowers/specs/2026-05-20-cpia-parser-mapper-refactor-design.md`
  - 사용 후 graph 흐름: collector → parser → [[mapper_node]]
- **Suspected related** (2026-05-20):
  - `_should_verify_llm` (parser.py:591) — LLM 검증 env flag
  - `_verify_sheet1_via_llm` / `_verify_sheet4_via_llm` — LLM 검증 wrapper
  - `parser_post.transform_bp_summaries` — 시트1 결과 정제

---

### `_parse_sheet1_bp_summaries` — col 30 merged group boundary

- **위치**: `pipeline/agents/parser.py:127-244` (118 LOC)
- **시그니처**: `def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]`
- **이슈**:
  - git log: `702ac06 refactor(parser): 시트1 _parse_sheet1_bp_summaries 개선` (2026-05-20)
  - docstring (parser.py:127~):
    - col 30 (금일 투입 그룹 Total) merged range 또는 단독 row 가 group boundary
    - BP 코드 row + 회사명 row 인접 pair (옵션 2)
    - company 정규화 = `split_company_and_zone` + `normalize_company`
    - zone = `extract_zone(col 6)` — 옵션 2 보수 매칭
    - sub-section 합계 row skip + 빈 placeholder skip
    - solo merged + 다음 row 흡수
  - spec §2.2 (2026-05-20 refactor): 99 그룹 예상
  - **주의**: ws 는 `read_only=False` 모드여야 함 (merged_cells.ranges 필요)
- **설계 의도**:
  - 시트1 의 grouping 은 col 30 (그룹 Total) merged 범위 기준 — col 5 (BP 코드/회사명) 자체로는 boundary 불명확
  - 시트1 출력은 mapper 의 `auto_bp_zone_match` deterministic input → zone 정확도 중요
- **대응 패턴**:
  - 입력: openpyxl ws (시트1, read_only=False)
  - 처리: col 30 merged_cells.ranges 수집 → solo row 식별 → group range 결정 (solo+next 흡수) → 각 group → BPSummary 변환 (`extract_zone` + 6 칸 시간대 합)
  - 출력: list[BPSummary] (99건 기대)
- **관련**:
  - 후속: parser.py:550 (parse_daily_report) 안에서 호출 → `transform_bp_summaries` 정제
  - 테스트: test_parser.py 의 시트1 count + 메타 검증
  - mapper 영향: BPSummary.zone → `resolve_wa` step 1 (`auto_bp_zone_match`) input
- **Suspected related** (2026-05-20):
  - `parser_post.transform_bp_summaries` — 본 함수 output 의 정제 pipeline
  - `parser_post.pair_bp_summaries` — 2-row pairing (시트1 raw → 정제)
  - mapper.py `resolve_wa` step 1 — BPSummary.zone 의 deterministic 활용

---

### `_parse_sheet4_activities` — ffill 4 컬럼 + cross-check B+C=D

- **위치**: `pipeline/agents/parser.py:346-426` (81 LOC)
- **시그니처**: `def _parse_sheet4_activities(ws) -> list[Activity]`
- **이슈**:
  - git log: `83b32f3 refactor(parser): 시트4 _parse_sheet4_activities 개선` (2026-05-20)
  - docstring 인용: ffill 4 컬럼 (col 3-6: Zone / 공종 / BP 코드 / 회사명) + cross-check `today_cum_qty == yesterday_cum_qty + today_qty`
  - 검증 LLM 의 sample 선정 logic 입력: 의심 case (cross-check 불일치) + 일반 sample
- **설계 의도**:
  - 시트4 는 mapper 의 LLM rerank 입력 + EVM 의 EV 분자 → work_content 정확도 중요
  - ffill 의 컬럼 4개 결정성: 헤더 이후 병합 셀 = 직전 row 값 전파 (1,193 row → 79+ activities)
- **대응 패턴**:
  - 입력: openpyxl ws (시트4)
  - 처리: `_ffill(rows, header_end, [3,4,5,6])` → 각 row → Activity 변환 (work_content, unit, plan_total_qty, yesterday_cum_qty, today_qty, today_cum_qty, progress_percent, remaining_qty, remaining_percent, note)
  - 출력: list[Activity] (79+건)
- **관련**:
  - 후속: `_verify_sheet4_via_llm` (default on, opt-out env) — 의심 case + sample LLM 검증
  - mapper 영향: Activity → `map_activity` (build_embedding_input + build_llm_input)
- **Suspected related** (2026-05-20):
  - `_verify_sheet4_via_llm` (parser.py:679) — 시트4 LLM 검증 wrapper
  - mapper.py `build_llm_input` — Activity.work_content + activity.bp_code (2026-05-20 fix B)

---

### `_verify_sheet1_via_llm` — 시트1 LLM 검증 wrapper (8 error path)

- **위치**: `pipeline/agents/parser.py:597-678` (82 LOC)
- **시그니처**: `def _verify_sheet1_via_llm(ws, bp_summaries: list[BPSummary]) -> None`
- **이슈**:
  - docstring: "spec §2.6.1 — 시트1 rule 결과 LLM 검증. issues 는 stderr 로그만 (결정성 보존)."
  - 8 종 error path graceful catch (timeout 30s / length / content_filter / JSONDecodeError / Exception broad / 빈 input / API key 없음 / schema 위반)
  - 비용 cap: ~$0.5/cycle (spec §2.6.4)
- **설계 의도**:
  - rule 결과 신뢰성 검증 — 사용자 push back "scope ≠ wa, 오른쪽 작업으로 wa 판단" 정합
  - **결정성 보존**: issues 는 stderr 로그 (DB 적재 X) → rule output 본문은 LLM 결과로 변경 X
  - opt-out: env `CPIA_PARSER_VERIFY_LLM=off` (default 'on')
- **대응 패턴**:
  - 발동: `parse_daily_report` 끝에서 `_should_verify_llm()` true 시
  - 입력: openpyxl ws (시트1) + rule 추출 bp_summaries 리스트
  - 처리: Azure gpt-5.1 호출 (timeout 30s) → JSON `{"issues": [...]}` parse → stderr log
  - 출력: None (side effect = stderr 로그)
- **관련**:
  - 시트4 페어: `_verify_sheet4_via_llm` (parser.py:679) — 같은 패턴, 비용 ~$0.05/cycle
  - 미해결 (parser_warning DB 적재): backlog — `parser_reports.warnings_jsonb` 컬럼 추가 후 적재
- **Suspected related** (2026-05-20):
  - `_should_verify_llm` (parser.py:591) — env flag 판정
  - `_verify_sheet4_via_llm` (parser.py:679) — 시트4 페어 함수

---

### `extract_zone` — col 6 (Scope) 옵션 2 보수 매칭

- **위치**: `pipeline/agents/parser_post.py:120-141` (22 LOC)
- **시그니처**: `def extract_zone(v6: str | None) -> str | None`
- **이슈**:
  - git log: `15c58bf feat(parser_post): split_company_and_zone / extract_zone 신설` (2026-05-20)
  - docstring 인용:
    - 옵션 2 (spec §2.1) 보수 매칭
    - 단일 토큰 'FAB' / 'CUB' → 결정
    - 시작 토큰 ('FAB 전구간') → 결정
    - 양쪽 ('FAB/CUB') → None (모호)
    - 텍스트 중간 ('M15X FAB F04') → None
  - 사용자 push back 정합 (spec §0.3): "scope ≠ wa, 오른쪽 작업으로 wa 판단" → col 6 모호 시 LLM 신뢰
- **설계 의도**:
  - 시트1 BPSummary.zone 의 deterministic 활용 — mapper `auto_bp_zone_match` (step 1) 의 input
  - 모호 케이스에서는 명시적 None 반환 → mapper 의 step 2 (`auto_llm_rerank`) fallback
- **대응 패턴**:
  - 입력: col 6 (Scope) raw 문자열
  - 처리: regex 5단계 (양쪽 / 단일 토큰 / 시작 토큰 / 텍스트 중간 / 기타)
  - 출력: "FAB" / "CUB" / None
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries` (parser.py:127) 내부
  - 페어: `split_company_and_zone` (parser_post.py:108) — 회사명 끝 FAB/CUB suffix 분리, zone 정보는 반환 X (옵션 2 정책)
  - mapper 영향: BPSummary.zone → `resolve_wa` step 1 input
- **Suspected related** (2026-05-20):
  - `split_company_and_zone` — 같은 cycle 신설 (회사명 정규화)
  - mapper.py `resolve_wa` step 1 (`auto_bp_zone_match`) — 본 함수 output 의 직접 소비

---

### `split_company_and_zone` — 회사명 끝 FAB/CUB suffix 분리

- **위치**: `pipeline/agents/parser_post.py:108-118` (11 LOC)
- **시그니처**: `def split_company_and_zone(raw: str | None) -> str | None`
- **이슈**:
  - git log: `15c58bf feat(parser_post): split_company_and_zone / extract_zone 신설` (2026-05-20)
  - docstring 인용:
    - 옵션 2 (scope ≠ wa): suffix 는 회사명 정규화에만 사용, zone 정보 반환 X
    - 예: '에스비테크CUB' → '에스비테크', '광건티엔씨FAB(수장2)' → '광건티엔씨'
- **설계 의도**:
  - 회사명 끝 FAB/CUB suffix 가 mapper 의 정확 일치 SQL (`fetch_bp_candidates`) 에서 mismatch 유발 → 정규화 단계에서 제거
  - zone 정보는 명시적 col 6 (`extract_zone`) 만 신뢰 — 옵션 2 보수 정책
- **대응 패턴**:
  - 입력: raw company 문자열
  - 처리: `normalize_company` (㈜ / 괄호 제거) → TRAILING_FABCUB_RE 제거
  - 출력: str 또는 None
- **관련**:
  - 호출자: `_parse_sheet1_bp_summaries` (parser.py:127) 안에서 BPSummary.company 정규화
  - 페어: `extract_zone` (parser_post.py:120) — zone 추출은 col 6 에서만
  - mapper 영향: fetch_bp_candidates 매칭 정확도 향상
- **Suspected related** (2026-05-20):
  - `normalize_company` (parser_post.py:92) — 같은 cycle 강화 (㈜/괄호)
  - graph.py:67~68 — fetch_bp_candidates 전 일괄 정규화 (정규화 타이밍 fix, e163e1a)

---

### `transform_bp_summaries` — filter + pair + normalize + split 파이프라인

- **위치**: `pipeline/agents/parser_post.py:183-201` (19 LOC)
- **시그니처**: `def transform_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **이슈**:
  - git log: `83b61ec fix(parser_post): transform_bp_summaries 에 today_incr_total 누락 — mapper KeyError fix`
  - 4-step 파이프라인: filter_marker_rows → pair_bp_summaries → normalize_company → split_company_and_zone
- **설계 의도**:
  - LLM/rule output 공통 정제 — rule 추출 본문은 raw 상태로 두고 정제 단계 분리 (단위 테스트 가능성)
  - today_incr_total 컬럼 보존 — mapper 의 `_prorate_workers_with_mh` 가 BP 총 인원으로 사용
- **대응 패턴**:
  - 입력: raw_rows list (시트1 rule 추출)
  - 처리: 4-step 파이프라인
  - 출력: 정제된 BPSummary list
- **관련**:
  - 호출자: parser.py 내부 + parser_llm.py:501 (deprecated path)
  - 후속: mapper.py `_prorate_workers_with_mh` (today_incr_total) + `build_bp_context`
- **Suspected related** (2026-05-20):
  - `pair_bp_summaries` (parser_post.py:44) — 2-row pairing 핵심
  - `filter_marker_rows` (parser_post.py:32) — 소계 row 제거

---

### `pair_bp_summaries` — 2-row pairing (BP 코드 + 회사명)

- **위치**: `pipeline/agents/parser_post.py:44-89` (46 LOC)
- **시그니처**: `def pair_bp_summaries(raw_rows: list[dict]) -> list[dict]`
- **이슈**:
  - docstring: "BP 코드 row (is_bp_code=true) + 다음 회사명 row (is_korean_company=true) + 같은 zone/disc_abbrev → 1 BPSummary 머지. 그 외: each row = 1 BPSummary."
  - git log: 1110e34 "feat(parser): parse_daily_report_llm calls parser_post for pair/filter/normalize"
- **설계 의도**:
  - 시트1 의 2-row 그룹 (BP 코드 + 한글 회사명) 패턴이 LLM/rule 양쪽 output 에서 발생 → 정규화 단계에서 머지
  - 정규성 기준: zone + disc_abbrev 일치 (PoC 3사 데이터 검증 통과)
- **대응 패턴**:
  - 입력: raw_rows list (is_bp_code, is_korean_company flag 포함)
  - 처리: while-i loop, current row + next row 패턴 매칭
  - 출력: 머지된 BPSummary list
- **관련**:
  - 호출자: `transform_bp_summaries` (parser_post.py:183)
  - 페어: `filter_marker_rows` (parser_post.py:32)
- **Suspected related** (2026-05-20):
  - `transform_bp_summaries` — 본 함수 호출 컨테이너

---

### `collect_and_parse` — N xlsx 병렬 파싱

- **위치**: `pipeline/agents/collector.py:52-69` (18 LOC)
- **시그니처**: `async def collect_and_parse(input_dir: Path | str, cfg: CollectorConfig) -> list[ParsedDailyReport]`
- **이슈**:
  - git log: `888e927 refactor(callers): collector.py + run_one_cycle.py 의 parser_llm → parse_daily_report` (2026-05-20)
  - spec `2026-05-19-cpia-collector-exporter-design.md` 의 콜렉터 부분 구현 (IMAP IDLE 푸시 는 backlog)
- **설계 의도**:
  - N개 작업일보 (POC 3사) → asyncio.Semaphore(4) 병렬 → mapper 측 BP cand_pool batch fetch 와 결합 (graph.py:74~79)
  - sync `parse_daily_report` 를 `asyncio.to_thread` 로 비동기 wrap
- **대응 패턴**:
  - 입력: input_dir 경로 + CollectorConfig (file_concurrency=4)
  - 처리: discover_daily_reports → asyncio.gather + Semaphore + to_thread(parse_daily_report)
  - 출력: list[ParsedDailyReport]
- **관련**:
  - 호출자: scripts/run_one_cycle.py
  - 후속: graph.py 의 mapper_node 입력 (state.parsed)
- **Suspected related** (2026-05-20):
  - graph.py `mapper_node` (graph.py:48) — collect_and_parse 의 직접 후속
  - graph.py:74~79 — unique_companies batch fetch_bp_candidates

---

### `parse_daily_report_llm` — DEPRECATED 2026-05-20

- **위치**: `pipeline/agents/parser_llm.py:501` (658 LOC 파일 전체)
- **시그니처**: `async def parse_daily_report_llm(xlsx_path, cfg, max_rows_per_sheet) -> ParsedDailyReport`
- **이슈**:
  - git log: `999bc05 chore(parser_llm): deprecation 주석 추가 (2026-05-20)`
  - 파일 헤더: "LLM 기반 작업일보 parser — DEPRECATED (2026-05-20). 회귀 사용 (rule path 가 실패하는 비상 경로): collector / run_one_cycle 의 import 를 parser_llm 으로 되돌리면 동작."
  - env flag `CPIA_PARSER=llm` graph entry 안에서 분기 — **미구현** (현재 caller 직접 변경으로만 회귀 가능)
- **설계 의도**:
  - PoC 마감 2026-06-05 (D-17) + rule-based 정확도 입증 (V1 시트2 0 warnings) → LLM chunk parsing 의 비용/시간 부담 제거
  - 코드 보존 — env flag 회귀 경로 backlog
- **대응 패턴**:
  - 현재 호출 X — caller (collector.py, run_one_cycle.py) 가 `parse_daily_report` (rule) 로 교체됨
- **관련**:
  - 페어: `parse_daily_report` (parser.py:539) — 현재 진입점
  - 제거 backlog: env flag deprecation 후 다음 cycle 제거 — issue #N8
- **Suspected related** (2026-05-20):
  - parser_post.py 의 transform_* 함수 — LLM/rule output 공통 정제 패턴 사용

---

## 변경 사항 정리 (cf3c143..HEAD)

| Commit | 변경 |
|---|---|
| 702ac06 | refactor(parser): 시트1 _parse_sheet1_bp_summaries 개선 — col 30 merged + group boundary + BP-zone 분리 + solo+next 흡수 |
| 05426ad | refactor(parser): 시트2 _parse_sheet2_job_allocations 개선 |
| ae144a2 | refactor(parser): 시트3 _parse_sheet3_equipment_allocations 개선 |
| 83b32f3 | refactor(parser): 시트4 _parse_sheet4_activities 개선 (ffill 4 컬럼 + cross-check) |
| d3b1418 | feat(parser): 시트1/4 LLM 검증 wrapper (default on, opt-out env) |
| 15c58bf | feat(parser_post): split_company_and_zone / extract_zone 신설 |
| 888e927 | refactor(callers): collector.py + run_one_cycle.py 의 parser_llm → parse_daily_report |
| 999bc05 | chore(parser_llm): deprecation 주석 추가 |
| 43002a8 | test(parser): 4 시트 col 인덱스 헤더 검증 가드 추가 |
| 83b61ec | fix(parser_post): transform_bp_summaries 에 today_incr_total 누락 — mapper KeyError fix |
| ae757fc | fix(parser_llm): _dict_only guard before transform_* — LLM 이 list 안에 str 섞어 출력 |
| fc7e677 | feat(parser_llm): sample mode — max_rows_per_sheet for fast demo cycle |

## 검증 status

| Phase | 항목 | 상태 |
|---|---|---|
| V1 (5/20) | 4 시트 rule cross-check (시트2 0 warnings) | ✅ 완료 |
| V2 (5/20) | Mapper 5 case simulation (auto_bp_zone_match 60% deterministic) | ✅ 완료 |
| V3 | 146 case full simulation (POC 3사) | ⏳ pending |
| V4 | Unit test 12개 (spec §5) | ⏳ pending |
| V5 | 10 업체 POC 전체 cycle + Reports UI 12 정량 기준 | ⏳ pending |

## 미해결 / Backlog

- `parser_warning` PG 영속화 — `parser_reports.warnings_jsonb` 컬럼 추가 후 적재 (issue #N7)
- `parser_llm.py` 658 LOC 제거 — env flag deprecation 후 다음 cycle (issue #N8)
- 시트2 의 raw company suffix (창원기전CUB(22.9kV)) zone 활용 검토 (spec §8)
- BPSummary 의 work_text_today BP 별 분리 (현재 시트1 group 안 row 들 통합) (spec §8)
- 다른 사이트 일보 양식 지원 (spec §8)
- 비용 cap 모니터링 (spec §2.6.4) — 초과 risk 시 `CPIA_PARSER_VERIFY_LLM=off` opt-out 명시만, 자동 차단 미구현
