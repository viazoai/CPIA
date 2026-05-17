# Design Intent — parser

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/agents/parser.py` (306 LOC) + `pipeline/tests/test_parser.py`

작업일보 xlsx 1개 → 4시트 (출력인원/직종/장비/물량) 통합 ParsedDailyReport. openpyxl 결정론 (LLM 없음). 시트명 + 셀 인덱스 hardcoding, forward-fill 병합 셀 처리.

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `ParseError` | parser.py:23 | `class ParseError(Exception)` | 작업일보 포맷 위반 예외 | — |
| `_normalize_unit` | parser.py:40 | `(s: str) -> str` | 단위 대소문자 통일 (M2→m2) | ✅ |
| `_disc_abbrev_to_kr` | parser.py:45 | `(abbrev) -> str\|None` | 공종 약자 → 한글 (AR→건축 등) | ✅ |
| `_is_admin_job` | parser.py:52 | `(job_type: str) -> bool` | 관리자 직종 판정 | ✅ |
| `_is_total_row` | parser.py:57 | `(row: tuple) -> bool` | 시트2 합계 row 판정 | ✅ |
| `_ffill` | parser.py:65 | `(rows, header_end, fill_cols) -> list[tuple]` | 헤더 이후 병합 셀 forward-fill | ✅ |
| `_parse_sheet1_bp_summaries` | parser.py:90 | `(ws) -> list[BPSummary]` | 시트1 → BPSummary[] | ✅ |
| `_parse_sheet2_job_allocations` | parser.py:124 | `(ws) -> list[JobAllocation]` | 시트2 → JobAllocation[] | ✅ |
| `_parse_sheet3_equipment_allocations` | parser.py:196 | `(ws) -> list[EquipmentAllocation]` | 시트3 → EquipmentAllocation[] | ✅ |
| `_parse_sheet4_activities` | parser.py:158 | `(ws) -> list[Activity]` | 시트4 → Activity[] | ✅ |
| `_extract_meta` | parser.py:237 | `(xlsx_path, wb) -> tuple[str, str]` | 파일명 → report_date, project | ✅ |
| `parse_daily_report` | parser.py:270 | `(xlsx_path) -> ParsedDailyReport` | xlsx 1개 → 4시트 통합 dict (공개 API) | ✅ |

---

## T2 — Issue Cards

### `parse_daily_report` — 4시트 통합 공개 API

- **위치**: `pipeline/agents/parser.py:270-306` (37 LOC)
- **시그니처**: `def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport`
- **이슈**:
  - docstring (parser.py:270): "작업일보 xlsx 1개 -> 4시트 통합 ParsedDailyReport. Raises ParseError: 시트명 누락, report_date/project 추출 실패."
  - 시트명 hardcoded (parser.py:285): `{"1.출력인원 현황", "2.직종별 인원현황", "3.장비현황", "4.물량"}` — 누락 시 ParseError.
  - 메타: `docs/superpowers/specs/2026-05-15-cpia-parser-design.md §3` (공개 API) / §4 (모듈 내부 분해).
- **설계 의도**:
  - 단일 진입점: pipeline 전체에서 Parser 는 본 함수만 호출. 4 시트 모두 통합 dict 로 반환 (호출자 분기 X).
  - 시트 누락 fail-fast: 4 시트 필수, 하나라도 빠지면 ParseError (호출자 책임).
  - 결정성 보장: 같은 xlsx → 같은 dict (LLM 없음, openpyxl 만).
- **대응 패턴**:
  - 발동: Collector → Parser (Collector 미구현 — 현재는 외부에서 직접 호출)
  - 입력: xlsx 절대 경로 (Path 또는 str)
  - 처리: load_workbook → 4 시트 누락 검증 → 각 시트 파서 호출 → meta 추출 → dict 조립
  - 출력: ParsedDailyReport (BPSummary[] + JobAllocation[] + EquipmentAllocation[] + Activity[] + meta)
- **관련**:
  - 호출 후보: `pipeline/main.py` / `pipeline/api.py` (둘 다 현재 0 byte)
  - 직접 호출: `pipeline/tests/test_parser.py`, `pipeline/graph.py:mapper_node` 전 단계
  - 페어 spec: `docs/superpowers/specs/2026-05-15-cpia-parser-design.md`
  - 테스트: `test_parser.py:263-284` (meta + integration + determinism + missing sheet 4 케이스)
- **Suspected related** (2026-05-17 stale):
  - `agents/collector.py` (0 byte) — 본 함수의 입력 (xlsx 경로) 을 yield 할 후보. drift backlog #5.

---

### `_extract_meta` — 파일명 정규식 + 시트1 헤더 스캔

- **위치**: `pipeline/agents/parser.py:237-268` (32 LOC, 분기 4)
- **시그니처**: `def _extract_meta(xlsx_path: Path, wb) -> tuple[str, str]`
- **이슈**:
  - docstring (parser.py:237): "파일명 -> report_date, 시트1 또는 파일명 -> project. 둘 다 실패 시 ParseError."
  - 정규식 (parser.py 상단): `_DATE_PATTERN = re.compile(r"_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$")` — YYYYMMDD.xlsx 또는 YYMMDD.xlsm 2 패턴.
  - 시트1 hardcoded keyword 스캔 (parser.py:254): `"M15X" in cell or "IBL" in cell or "PJT" in cell` — 현 PoC 프로젝트명.
- **설계 의도**:
  - 파일명 우선: 날짜는 파일명 정규식 (사람 입력보다 시스템 메타 신뢰).
  - 프로젝트명 2 경로: 시트1 상단 3 row 키워드 스캔 → 실패 시 파일명 stem 폴백 (`통합작업일보_` 접두 제거 후 마지막 `_` 토큰 제거).
  - 둘 다 실패 시 ParseError — 자동화 hard fail.
- **대응 패턴**:
  - 발동: `parse_daily_report` 후반부
  - 입력: xlsx_path + 이미 로드된 workbook
  - 처리: 파일명 regex match → 시트1 3 row 스캔 → 폴백 stem 파싱
  - 출력: (report_date "YYYY-MM-DD", project str)
- **관련**:
  - 테스트: `test_parser.py:263-267 test_parse_meta` ("2025-09-25" + project 포함)
- **Suspected related** (2026-05-17 stale):
  - 새 프로젝트명 (M15X/IBL/PJT 외) 추가 시 본 함수 hardcoded keyword 확장 필요 — 의도된 hardcoding 이지만 향후 config 외부화 후보.

---

### `_ffill` — 병합 셀 forward-fill

- **위치**: `pipeline/agents/parser.py:65-88` (24 LOC, 분기 3)
- **시그니처**: `def _ffill(rows, header_end, fill_cols) -> list[tuple[int, list[Any]]]`
- **이슈**:
  - docstring (parser.py:65): "헤더 이후 row 를 forward-fill (병합 셀 직전 값 채움). 사전 조건: fill_cols 의 모든 인덱스는 row 의 열 수 이내여야 한다. 조건 위반 시 해당 컬럼은 조용히 skip (데이터 손실 가능) — 호출부 책임. 반환 row 번호는 1-indexed (header_end + 1 부터)."
  - 메타: `docs/superpowers/specs/2026-05-15-cpia-parser-design.md §4`: "병합 셀 forward-fill. fixture loader 의 `_ffill` 이관."
- **설계 의도**:
  - openpyxl 병합 셀 한계: openpyxl 은 병합 셀의 첫 칸에만 값을 둠. 그 아래 row 는 None → 직전 값 채움 필요.
  - "조용히 skip" 정책: 컬럼 인덱스 over → 호출부 책임 (스펙 명시), 함수는 KeyError 없이 통과.
- **대응 패턴**:
  - 발동: 시트1/2/3/4 모든 파서에서 호출
  - 입력: rows 전체 + header_end + fill_cols 인덱스 list
  - 처리: last 추적 dict → row 순회 → 빈 셀 last 채움
  - 출력: `list[(row_no_1indexed, list[Any])]`
- **관련**:
  - 4개 시트 파서 모두 호출
  - 테스트: `test_parser.py:51-66 test_ffill_basic` (7행 시뮬)
- **Suspected related** (2026-05-17 stale): 없음 (general utility).

---

### `_parse_sheet1_bp_summaries` — BPSummary 추출

- **위치**: `pipeline/agents/parser.py:90-122` (33 LOC, 분기 3)
- **시그니처**: `def _parse_sheet1_bp_summaries(ws) -> list[BPSummary]`
- **이슈**:
  - docstring (parser.py:90): "시트 1 (출력인원 현황) -> BPSummary[]. 시뮬 v3 패턴 기반. Header end = row 4. Forward-fill cols = [1, 2, 3, 4] (병합 셀 패턴). r[2]=zone, r[3]=disc_abbrev, r[4]=company (BP 코드 row 는 mapper 무시), r[6]=work_text_yesterday, r[7]=work_text_today, r[8]=work_text_tomorrow, r[28]=today_incr_total, r[35]=today_cum_total. bp_code / scope: GATE 2 에서 보강 예정 -> None."
- **설계 의도**:
  - 시뮬 v3 검증 패턴 코드화: 실 xlsx 분석으로 셀 인덱스 확정 후 hardcoding (포맷 고정 가정).
  - GATE 2 진입 시 bp_code/scope 컬럼 보강 — 현재는 None (의도된 미구현).
- **대응 패턴**:
  - 발동: `parse_daily_report` 4 시트 순차 호출 중
  - 입력: openpyxl Worksheet (시트1)
  - 처리: `_ffill` → row 순회 → BPSummary dict 생성 (10 필드)
  - 출력: list[BPSummary]
- **관련**:
  - state.py:BPSummary TypedDict
  - 테스트: `test_parser.py:139-182` (남웅 포함, 10 필드 존재, disc_abbrev 한글 변환)
- **Suspected related** (2026-05-17 stale): `_parse_sheet2/3/4` (동일 패턴).

---

### `_parse_sheet2_job_allocations` — 직종 (관리자/합계 필터)

- **위치**: `pipeline/agents/parser.py:124-156` (33 LOC, 분기 4)
- **시그니처**: `def _parse_sheet2_job_allocations(ws) -> list[JobAllocation]`
- **이슈**:
  - docstring (parser.py:124): "시트 2 (직종별 인원현황) -> JobAllocation[]. 관리자 직종/합계 row 필터. cell 인덱스 (Task 0 시뮬 v3 발췌 / 실 파일 row 3 헤더 검증): r[1] = disc_abbrev, r[2] = company (BP 코드 row 와 회사명 row 혼재, mapper 가 회사명으로만 매치하므로 BP 코드 row 는 자연 무시), r[5] = job_type, r[23] = workers_cum_t (col 23 = 금일누계 계 컬럼). header_end = 5, fill_cols = [1, 2] (시뮬과 일치)."
- **설계 의도**:
  - noise 필터 2종: `_is_total_row` (합계 row) + `_is_admin_job` (관리자 직종) — 통계 오염 방지.
  - BP 코드 row 자연 무시: company 컬럼에 BP 코드 row 가 섞여있지만 Mapper 가 회사명으로만 매치 → Parser 단에서 별도 필터 불필요.
- **대응 패턴**:
  - 발동: `parse_daily_report` 중
  - 입력: 시트2 Worksheet
  - 처리: `_ffill` → row 순회 → `_is_total_row` + `_is_admin_job` 필터 → JobAllocation dict 생성
  - 출력: list[JobAllocation]
- **관련**:
  - `_is_admin_job` + `_is_total_row` (parser.py:52, 57)
  - 테스트: `test_parser.py:191-219` (관리자 0건, 총합 0건, workers_cum_t int)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_parse_sheet3_equipment_allocations` — 장비 추출

- **위치**: `pipeline/agents/parser.py:196-235` (40 LOC, 분기 3)
- **시그니처**: `def _parse_sheet3_equipment_allocations(ws) -> list[EquipmentAllocation]`
- **이슈**:
  - docstring (parser.py:196): "시트 3 (장비현황) -> EquipmentAllocation[]. cell 인덱스 ... r[1] = disc_abbrev, r[2] = company, r[3] = equipment_big, r[4] = equipment_mid, r[5] = equipment_spec (None 허용), r[23] = count_cum_t. header_end = 5, fill_cols = [1, 2]."
- **설계 의도**:
  - 시트 3·2 와 동일한 fill_cols 패턴 ([1, 2]) — 일관성. equipment_spec 은 None 허용 (규격 미기입 데이터).
- **대응 패턴**:
  - 발동: `parse_daily_report` 중
  - 입력: 시트3 Worksheet
  - 처리: `_ffill` → row 순회 → EquipmentAllocation dict 생성
  - 출력: list[EquipmentAllocation]
- **관련**:
  - 테스트: `test_parser.py:228-254` (장비 count, big/mid 필수, count_cum_t ≥ 0)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_parse_sheet4_activities` — 시트4 Activity (Mapper 주 입력)

- **위치**: `pipeline/agents/parser.py:158-194` (37 LOC, 분기 3)
- **시그니처**: `def _parse_sheet4_activities(ws) -> list[Activity]`
- **이슈**:
  - docstring (parser.py:158): "시트 4 (물량) -> Activity[]. fixture loader _load_inputs 이관. Header end = row 4. Forward-fill 컬럼 = [1, 2, 3, 4, 5] (병합 셀 패턴). 필수 셀: r[5] (company), r[7] (work_content)."
  - 인라인 (parser.py:187): `"requires_review": False,` — Parser 단계에서는 false, Mapper에서 설정.
- **설계 의도**:
  - 필수 셀 가드: company / work_content 비어있으면 row skip (다른 필드는 비어있어도 통과).
  - `requires_review` 책임 분리: Parser 는 항상 False, Mapper 가 confidence < 0.7 또는 `hil_required` 시 True 로 set (mapper.py:335).
  - state.Activity TypedDict 스키마 따름 (l5_disc/l6_main/wa/unit/today_qty/plan_total_qty/conditions 등).
- **대응 패턴**:
  - 발동: `parse_daily_report` 중
  - 입력: 시트4 Worksheet
  - 처리: `_ffill` → company+work_content 필수 가드 → Activity dict 생성
  - 출력: list[Activity]
- **관련**:
  - state.Activity TypedDict
  - mapper.py 입력
  - 테스트: `test_parser.py:88-131` (79건 이상, 회사명 매칭, unit 정규화, today_qty float)
- **Suspected related** (2026-05-17 stale):
  - `mapper.py:map_activity:208` — 본 함수 출력의 소비자. confidence/requires_review set 책임 분리.

---

### `_normalize_unit` — 단위 대소문자 통일

- **위치**: `pipeline/agents/parser.py:40-43` (4 LOC)
- **시그니처**: `def _normalize_unit(s: str) -> str`
- **이슈**:
  - docstring: "단위 대소문자 통일 (M2->m2, Ton->ton)."
  - 메타: 자료 없음 (단순 lower).
- **설계 의도**:
  - Mapper / Atomizer / Forecaster 가 unit 으로 그룹핑할 때 케이스 차이로 인한 분리 방지.
- **대응 패턴**:
  - 발동: `_parse_sheet4_activities` 중 unit 컬럼 처리
  - 입력: 단위 문자열 (또는 None)
  - 처리: `s.lower() if s else ""`
  - 출력: 소문자 단위
- **관련**:
  - 테스트: `test_parser.py:15-22` (M2/m2/Ton/ton/M3/EA 6 케이스)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_disc_abbrev_to_kr` — 공종 약자 → 한글

- **위치**: `pipeline/agents/parser.py:45-50` (6 LOC)
- **시그니처**: `def _disc_abbrev_to_kr(abbrev: str | None) -> str | None`
- **이슈**:
  - docstring: "공종 약자 -> 한글 (알 수 없으면 원본 보존)."
  - 매핑 dict: `{AR:건축, ME:설비, EL:전기, UT:UT, TE:공통가설, IN:제어, CI:토목}` (7개).
  - 메타: `docs/superpowers/specs/2026-05-15-cpia-parser-design.md §4` ("공종 약자 cross-walk").
- **설계 의도**:
  - 한글 통일: 시트1/2/3 의 disc_abbrev 영문을 한글로 통일 (Mapper 의 l5_disc 매칭 단순화).
  - 미등록 시 원본 보존 (fail-soft) — UT 처럼 한글 매핑 없으면 영문 그대로.
- **대응 패턴**:
  - 발동: 시트1/2/3 파서에서 disc_abbrev 컬럼 처리
  - 입력: 영문 약자 (또는 None)
  - 처리: dict.get 폴백 = 원본
  - 출력: 한글 또는 영문 원본
- **관련**:
  - 테스트: `test_parser.py:25-34` (7 매핑 + 미등록 + None)
- **Suspected related** (2026-05-17 stale): 없음.

---

### `_is_admin_job` — 관리자 직종 판정

- **위치**: `pipeline/agents/parser.py:52-55` (4 LOC)
- **시그니처**: `def _is_admin_job(job_type: str) -> bool`
- **이슈**:
  - docstring: "관리자 직종 noise 판정 (시트2 필터)."
  - 매핑: `_ADMIN_JOBS = frozenset({"BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자"})`.
- **설계 의도**:
  - 직종 통계에서 관리자 제외 (현장 투입 인원 계산 정확도). frozenset → 빠른 in 체크.
- **대응 패턴**:
  - 발동: 시트2 파서
  - 입력: job_type 문자열
  - 처리: frozenset in
  - 출력: True/False
- **관련**:
  - 테스트: `test_parser.py:37-41` (관리자 5종 + 기능공 5종)
- **Suspected related** (2026-05-17 stale):
  - `mapper.py:_is_trade_job` — 비슷한 화이트리스트 패턴 (trade vs admin 반대 방향).

---

### `_is_total_row` — 시트2 합계 row 판정

- **위치**: `pipeline/agents/parser.py:57-63` (7 LOC, 분기 2)
- **시그니처**: `def _is_total_row(row: tuple[Any, ...]) -> bool`
- **이슈**:
  - docstring: "시트2 합계 row 판정 ('투입 Total' 포함)."
  - 키워드: `"투입 Total"` 부분 일치.
- **설계 의도**:
  - 시트2 의 BP사별 / 기능공 / 직종별 합계 row 가 통계 오염 — 본 row 제외 필수.
  - 'Total' 영문 + '투입' 한글 혼용 — 실 xlsx 패턴 그대로.
- **대응 패턴**:
  - 발동: 시트2 파서
  - 입력: 한 row tuple
  - 처리: 모든 cell 순회 → str 이고 '투입 Total' 포함 시 True
  - 출력: True/False
- **관련**:
  - 테스트: `test_parser.py:44-48`
- **Suspected related** (2026-05-17 stale): 없음.

---

## 관찰

- **LLM 호출 없음**: Parser 는 결정론 (openpyxl 만). 한자 사용 0건 (한글 + 영어 + 숫자만).
- **시트명 hardcoding**: 4 시트명 + 시트별 셀 인덱스 모두 hardcoded. 실 xlsx 포맷 변경 시 코드 변경 필요 (config 외부화 미고려 — 현 PoC 가정).
- **`requires_review` 책임 위임**: Parser 는 항상 False, Mapper 가 set. Drift backlog #4 (HIL 1) 진입 시 `requires_review=True` 인 row 가 HIL 1 큐 입력이 됨.
