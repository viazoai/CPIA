# Parser 설계 — `pipeline/agents/parser.py`

> **A 트랙 Parser 에이전트 설계.** 작업일보 xlsx 1개를 4시트 통합 `ParsedDailyReport` dict 로 변환. 결정론 (openpyxl 단독), LLM 호출 0회. `pipeline/agents/mapper.py` 의 `build_bp_context` 가 이미 시뮬 v3 패턴으로 작성돼 있어 Parser 가 채우는 dict 를 그대로 받음 — 즉 Parser 는 Mapper 의 input 공급자이고, mapper 와의 인터페이스는 `pipeline/state.py` 의 TypedDict 4종으로 이미 합의돼 있음.
>
> 작성: 2026-05-15 (A 트랙) · 기반: `docs/schema/mapping-layer.md §2` Parser 통합 스키마 + `pipeline/tests/test_mapper_golden.py` 베이스라인 측정 + `/tmp/cpia_full_sim_v3.py` 시뮬 코드 검토

---

## 0. 한눈에 보기

```
Collector (파일 경로 yield)
   ↓
Parser (이 문서)
   ├─ 시트 1 (출력인원 현황)    → BPSummary[]
   ├─ 시트 2 (직종별 인원현황)   → JobAllocation[]
   ├─ 시트 3 (장비현황)         → EquipmentAllocation[]
   ├─ 시트 4 (물량)            → Activity[]
   └─ 메타 (파일명 / 시트1)     → report_date / project
   ↓ ParsedDailyReport
Mapper (이미 완성) — build_bp_context 가 시트1+2+3 join, build_llm_input 이 시트4 line + BP 컨텍스트 결합
```

- **LLM 호출 0회.** 작업일보 포맷이 고정 (시트명·헤더 위치 동일) 이라 openpyxl 결정론적 추출 충분. LLM 은 Mapper 단계가 전담.
- **공개 API 단일:** `parse_daily_report(xlsx_path: Path) -> ParsedDailyReport`.
- **fixture loader 이관:** `pipeline/tests/test_mapper_golden.py:_load_inputs` 의 시트4 추출 로직을 `_parse_sheet4_activities` 로 이관. 골든 테스트는 `parse_daily_report` 호출로 교체.

---

## 1. Background — 베이스라인 결과와 motivation 재정렬

### 1.1 베이스라인 측정 (2026-05-15 실측)

```
$ uv run pytest tests/test_mapper_golden.py -m golden -s -v
[golden] 정확도: 78/79 = 98.7%
  X R459 'FA DUCT 설치' -> 골든=일반공조설비공사 vs 결과=CABINET배기설비공사 (conf 0.83)
PASSED   (in 284.86s = 4분 44초)
```

prod 골든 테스트는 `map_activity(activity, parsed_report=None, cfg=cfg)` 즉 BP 컨텍스트 ablation 상태로 호출 중. 그 상태에서도 시뮬 v3 (시트1+2+3 통합 컨텍스트) 와 **동일하게 78/79 = 98.7%** 달성.

### 1.2 motivation 재정렬

| 가설 | 검증 결과 | 비중 |
|---|---|---|
| 시뮬 v3 패턴 복원으로 정확도 ↑ | ❌ 79건 표본에서 0 개선 (시뮬 v3 와 동일 78/79) | 낮음 |
| 다운스트림 (Reporter / Forecaster / Atomizer) 의 시트1/2/3 데이터 의존 | ✅ Reporter 가 BP사별 인원·장비 수치 필요, Atomizer 가 BPSummary 통째 적재 | **높음** |
| prod 자동화 (Collector → Parser → Mapper 흐름) | ✅ 지금은 fixture loader 가 시트4 만 임시 처리, Collector 가 던지는 파일을 받을 코드 없음 | **높음** |
| WA 결정 4단계 중 3단계 (시트1 work_text_today LLM 추론, mapper.py:182 TODO) 활성화 | ✅ GATE 2 (5/22) 에서 활성화 예정, 시트1 자연어 필요 | 중간 |
| 표본 다양성 ↑ 시 정확도 기여 가능성 | ⏳ 미검증, GATE 2 / GATE 3 에서 추가 작업일보로 측정 | 중간 |

**핵심:** Parser 의 가치는 정확도가 아니라 **(a) 다운스트림 데이터 공급, (b) prod 자동화 흐름 완성, (c) GATE 2 WA 3단계 활성화 기반** 셋. 정확도 기여는 79건 표본에서는 미관측이고 GATE 2/3 에서 재측정 대상.

### 1.3 흥미로운 패턴 — 오답 conf 변화

| 시점 | R459 'FA DUCT 설치' 의 conf |
|---|---|
| 시뮬 v3 (시트1+2+3 컨텍스트 포함) | 0.55 |
| prod 골든 (parsed_report=None) | 0.83 |

같은 오답이 컨텍스트 ablation 후 더 자신 있는 오답이 됨. 시트1~3 컨텍스트가 정답을 못 끌어내도 LLM 의 자신감을 적절히 누른 효과는 있었음. H-i-L 1 임계값 (`mapping_conf < 0.7`) 발동률 비교 시 의미 있는 차이일 수 있음 — GATE 2 에서 검증 대상.

---

## 2. 책임 경계 — Parser / Mapper / Collector

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Collector                                                                │
│   책임: 파일 경로 yield + 검증 (확장자, 파일명 패턴, 중복 처리)              │
│   출력: list[Path]                                                       │
│   LLM:  ❌                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│ Parser  (이 문서)                                                         │
│   책임: xlsx 1개 → 4시트 통합 dict (셀 위치 → TypedDict 필드 매핑)          │
│   출력: ParsedDailyReport                                                 │
│   LLM:  ❌                                                                │
├─────────────────────────────────────────────────────────────────────────┤
│ Mapper  (완성)                                                            │
│   책임: Activity dict 1개 → WBS 코드 분류 (l6_main / wa / mapping_conf)    │
│   입력: Activity + ParsedDailyReport (BP 컨텍스트용, optional)             │
│   LLM:  ✅ 임베딩 + GPT-5.1 chat                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**겹치는 부분 없음.** mapper.py 는 dict key 접근만 함 (`parsed_report["bp_summaries"]`), openpyxl import 도 `iter_rows` 호출도 없음. Parser 는 셀 → dict 변환만, WBS 분류 로직은 일체 없음.

---

## 3. 공개 API

```python
# pipeline/agents/parser.py
from pathlib import Path
from pipeline.state import ParsedDailyReport


def parse_daily_report(xlsx_path: Path) -> ParsedDailyReport:
    """작업일보 xlsx 1개 → 4시트 통합 ParsedDailyReport.

    Args:
        xlsx_path: 통합작업일보 xlsx 절대 경로.

    Returns:
        ParsedDailyReport — report_date / project / bp_summaries / job_allocations
        / equipment_allocations / activities.

    Raises:
        ParseError: 시트명 누락, 필수 메타 (report_date / project) 추출 실패,
            xlsx 가 작업일보 포맷 위반.
    """
```

- **동기 함수.** I/O 가 디스크 read 만이라 async 불필요. Mapper 만 async (LLM / DB / Chroma I/O).
- **인자 1개.** Collector 가 파일 경로 yield → Parser 에 1대1 호출. 다중 파일은 호출부 (graph) 의 책임.
- **순수 함수.** 외부 상태 변경 없음, 같은 xlsx → 같은 출력 (결정성 검증 가능).

### 3.1 예외 클래스

```python
class ParseError(Exception):
    """작업일보 포맷 위반."""
```

prod 작업일보 포맷이 고정이므로 처음엔 strict (raise). PoC 후 새 포맷 발견 시 relax 검토.

---

## 4. 모듈 내부 분해

```
parse_daily_report(xlsx_path)
  │
  ├─ wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
  │
  ├─ report_date, project = _extract_meta(xlsx_path, wb)
  │     ├─ report_date  ← 파일명 정규식 (`_YYYYMMDD\.xlsx$`) 또는 시트1 메타 셀
  │     └─ project       ← 시트1 헤더 셀 (실 파일에서 확인 후 확정)
  │
  ├─ bp_summaries = _parse_sheet1_bp_summaries(wb["1.출력인원 현황"])
  ├─ job_allocations = _parse_sheet2_job_allocations(wb["2.직종별 인원현황"])
  ├─ equipment_allocations = _parse_sheet3_equipment_allocations(wb["3.장비현황"])
  ├─ activities = _parse_sheet4_activities(wb["4.물량"])
  │
  ├─ wb.close()
  └─ return {report_date, project, bp_summaries, job_allocations,
             equipment_allocations, activities}
```

**모듈 private 헬퍼:**

| 함수 | 책임 |
|---|---|
| `_ffill(rows, header_end, fill_cols)` | 병합 셀 forward-fill. fixture loader 의 `_ffill` 이관. |
| `_normalize_unit(s)` | `M2`→`m2`, `Ton`→`ton` 통일 (mapping-layer.md §2.1 (4)) |
| `_disc_abbrev_to_kr(abbrev)` | `AR`→`건축`, `ME`→`설비`, `EL`→`전기`, `UT`→`UT`, `TE`→`공통가설`, `IN`→`제어`, `CI`→`토목` cross-walk (state.md §3.3) |
| `_is_admin_job(job_type)` | 관리자 직종 (BP소장 / 공사관리자 / 안전관리자 / 품질관리자 / 일반관리자) noise 필터 (mapping-layer.md §2.1 (3)) |
| `_is_total_row(row)` | 시트2 `"기능공 투입 Total"` 같은 BP사 합계 row 제거 (mapping-layer.md §2.1 (3)) |

---

## 5. 시트별 셀 위치

> **출처:** `docs/schema/mapping-layer.md §2` BPSummary / JobAllocation / EquipmentAllocation 정의 + 실 작업일보 파일 (`docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`) 검증.

### 5.1 시트 1 — `1.출력인원 현황` (rows=387, cols=37)

BP사별 row blocks 이 누적. 각 BP사 block 에서 다음 셀 추출.

| 셀 | 필드 |
|---|---|
| (BP사 행, B) | `company` |
| (BP사 행, A) 또는 코드 셀 | `bp_code` (예: `PH_X-001`) |
| C-disc 셀 | `disc_abbrev` → `_disc_abbrev_to_kr` 적용 |
| zone 셀 | `zone` (`FAB` / `CUB` / `FAB/CUB`) |
| scope 셀 | `scope` (`A구간` 등) |
| C6 | `work_text_yesterday` |
| C7 | `work_text_today` ★ WA 3단계 추론 단서 |
| C8 | `work_text_tomorrow` |
| C28 | `today_incr_total` (금일 신규 투입 Total) |
| C35 | `today_cum_total` (금일 누적 인원 Total) |

**미확정 (실 파일 추가 탐색 후 확정):** 각 BP사 block 의 행 시작 위치 / block 길이 / 다음 BP사로 이동 규칙. 시뮬 시점 `/tmp/cpia_full_sim_v3.py:118` 의 추출 패턴 재활용.

### 5.2 시트 2 — `2.직종별 인원현황` (rows=15501, cols=25)

BP사 × 직종 row.

| 셀 | 필드 |
|---|---|
| BP사 셀 | `company`, `bp_code` |
| C-disc | `disc_abbrev` → 한글 변환 |
| 직종 셀 | `job_type` |
| C23 | `workers_cum_t` (금일누계 Cum.T) |

**필터링 (mapping-layer.md §2.1 (3)):**
- `_is_total_row` 매치 row 제거 (`"기능공 투입 Total"` 등)
- `_is_admin_job` 매치 직종 제거 (BP소장 / 공사관리자 / 안전관리자 / 품질관리자 / 일반관리자)

### 5.3 시트 3 — `3.장비현황` (rows=12668, cols=25)

BP사 × 장비.

| 셀 | 필드 |
|---|---|
| BP사 셀 | `company`, `bp_code` |
| 장비 대분류 셀 | `equipment_big` (`굴삭운반기계류` 등) |
| 장비 중분류 셀 | `equipment_mid` (`Back Hoe` 등) |
| 장비 규격 셀 | `equipment_spec` (`2㎥ 미만` 등, None 허용) |
| C23 | `count_cum_t` (금일투입누계 Cum.T) |

### 5.4 시트 4 — `4.물량` (rows=1263, cols=17)

**fixture loader `_load_inputs` 의 추출 로직 그대로 이관.**

| 컬럼 인덱스 | 필드 |
|---|---|
| r[3] | `trade` / `l5_disc` |
| r[5] | `company` |
| r[7] | `work_content` |
| r[8] | `unit` (`_normalize_unit` 적용) |
| r[9] | `plan_total_qty` (숫자 아니면 None) |
| r[11] | `today_qty` (숫자 아니면 0.0) |

**forward-fill:** header 끝 = row 4. fill_cols = [1, 2, 3, 4, 5]. fixture loader 의 `_ffill` 이관.

**필수 셀 검증:** `r[5]` (company), `r[7]` (work_content) 둘 다 채워진 row 만 Activity 로 만듦. 그 외 row 는 skip + 로그.

**`today_qty` None 처리:** float 변환 실패 시 0.0 (fixture loader 현 동작 유지). mapping-layer.md §2.1 (3) 의 "LLM 이 작업없음 vs 미입력 판단" 은 Mapper 의 `build_llm_input` 이 `today_qty=0` 을 `"-"` 로 표시해서 LLM 에게 컨텍스트로 제공 (mapper.py:155). Parser 단계에서는 0.0 으로 보존.

---

## 6. fixture loader 이관

### 6.1 이관 대상

`pipeline/tests/test_mapper_golden.py:63-118` 의 `_ffill` + `_load_inputs` 의 시트4 추출 로직.

### 6.2 이관 후 구조

```python
# pipeline/agents/parser.py
def _parse_sheet4_activities(ws) -> list[Activity]:
    """시트 4 → Activity[]. fixture loader 의 _load_inputs 시트4 부분 이관."""
    rows = _ffill(list(ws.iter_rows(values_only=True)), header_end=4, fill_cols=[1, 2, 3, 4, 5])
    activities = []
    for i, r in rows:
        if not (r[5] and r[7]):
            continue
        activities.append({
            "wbs_activity_id": None,
            "l5_disc": str(r[3]) if r[3] else "",
            "l6_main": None,
            "l7_sub": None,
            "l7_5_activity": None,
            "sub_work_area": None,
            "trade": str(r[3]) if r[3] else "",
            "company": str(r[5]).strip(),
            "unit": _normalize_unit(str(r[8] or "").strip()),
            "today_qty": float(r[11]) if isinstance(r[11], (int, float)) else 0.0,
            "work_content": str(r[7]).strip(),
            "conditions": [],
            "assigned_workers": 0.0,
            "worker_source": "parsed",
            "plan_total_qty": float(r[9]) if isinstance(r[9], (int, float)) else None,
            "plan_mh": None,
            "requires_review": False,
            "wa": None,
            "mapping_conf": None,
            "mapping_source": None,
        })
    return activities
```

### 6.3 골든 테스트 수정

```python
# pipeline/tests/test_mapper_golden.py (수정 후)
from pipeline.agents.parser import parse_daily_report


async def test_golden_accuracy(sample_tong_path: Path, azure_openai_env):
    cfg = MapperConfig(...)
    parsed = parse_daily_report(sample_tong_path)

    # Parser 출력 Activity[] 의 row index 는 잃어버리므로 GOLDEN 매핑은
    # (company, work_content) 키 또는 별도 row tracking 헬퍼로 복원.
    inputs = _match_golden(parsed.activities)  # thin helper, 골든 테스트 전용
    assert len(inputs) == 79

    for row, activity in inputs:
        result = await map_activity(activity, parsed_report=parsed, cfg=cfg)
        ...
```

**row 추적 결정:** `Activity` TypedDict 에 `row` 필드 추가는 prod 흐름에 불필요한 noise. 골든 테스트가 자체 thin 헬퍼 (`_match_golden`) 로 row 복원하는 게 깔끔. 또는 `_parse_sheet4_activities` 가 `list[tuple[int, Activity]]` 반환하도록 변경 — Parser API 가 노출하지 않고 모듈 private 만 유지하면 prod 흐름에 영향 없음.

**시뮬 v3 패턴 복원:** 위 수정으로 `parsed_report=parsed` 가 들어가면 mapper 의 `build_bp_context` 가 본 경로로 작동. 정확도가 98.7% 에서 변할지 (베이스라인 동등 / 개선 / 후퇴) 가 PoC 다음 측정 항목.

---

## 7. 정규화 규칙 (mapping-layer.md §2.1 반영)

| 규칙 | 대상 | 구현 |
|---|---|---|
| 단위 정규화 | 시트4 `r[8]` | `_normalize_unit`: `M2`→`m2`, `Ton`→`ton` (대소문자 통일) |
| 공종 약자 → 한글 | 시트1/2/3 의 `disc_abbrev` | `_disc_abbrev_to_kr`: AR→건축, ME→설비, EL→전기, UT→UT, TE→공통가설, IN→제어, CI→토목 |
| 시트2 noise — 합계 row | `_is_total_row` | row text 에 `"투입 Total"` 포함 시 제외 |
| 시트2 noise — 관리자 직종 | `_is_admin_job` | job_type ∈ {BP소장, 공사관리자, 안전관리자, 품질관리자, 일반관리자} 제외 |
| 시트4 `today_qty=None` (89.5%) | Parser 단계에서 0.0 보존 | Mapper 의 `build_llm_input` 이 `0` 을 `"-"` 로 표시. LLM 판단 (작업없음 / 미입력) 은 Mapper 가 통합 컨텍스트로 결정. |

---

## 8. 에러 처리 — strict

| 상황 | 처리 |
|---|---|
| 시트명 4개 중 누락 (`1.출력인원 현황` / `2.직종별 인원현황` / `3.장비현황` / `4.물량`) | `ParseError` raise |
| `report_date` 추출 실패 (파일명 + 시트1 메타 둘 다 실패) | `ParseError` raise |
| `project` 추출 실패 | `ParseError` raise |
| 시트4 row 의 `company` / `work_content` 빈 셀 | skip + 로그 (fixture loader 현 패턴 유지) |
| 시트1/2/3 BP사 block 0개 | 빈 list 반환 + 로그 (raise X — 작업일보가 그날 데이터 없을 수도) |
| 시트별 cell 타입 mismatch (예: 숫자 셀에 문자열) | type 변환 시도 → 실패 시 해당 필드 None 또는 0.0, row 는 보존 |

**근거:** prod 작업일보 포맷이 고정이라 시트명·메타 누락은 포맷 위반 신호. 개별 row 누락은 운영 중 흔한 경우 (BP사 그날 미가동) 라 skip 이 합리적.

---

## 9. 테스트 전략

### 9.1 신규 — `pipeline/tests/test_parser.py`

| 테스트 | 검증 |
|---|---|
| `test_parse_meta` | `report_date='2025-09-25'`, `project` 추출 (실 값 확인 후 확정) |
| `test_parse_sheet1_bp_summaries` | bp_summaries 길이 = N (실 파일에서 확인), 첫 BP사 의 company/work_text_today/today_cum_total |
| `test_parse_sheet2_job_allocations` | `_is_admin_job` 필터 적용 후 관리자 직종 0건, `_is_total_row` 필터 적용 후 Total row 0건 |
| `test_parse_sheet3_equipment_allocations` | equipment_allocations 길이 = N, 첫 row 의 equipment_big/mid |
| `test_parse_sheet4_activities` | activities 길이 = fixture loader 결과와 동일 (= 골든 79건 포함 전체 추출 N건). 단위 정규화 적용 확인. |
| `test_normalize_unit` | `M2`→`m2`, `Ton`→`ton`, 빈 문자열 → 빈 문자열 |
| `test_disc_abbrev_to_kr` | 7가지 약자 변환 + 알 수 없는 약자는 원본 보존 |
| `test_parse_error_missing_sheet` | 시트 1개 누락된 fixture → ParseError raise |
| `test_parse_determinism` | 같은 xlsx 2회 호출 → 같은 dict (결정성 — `state.md §3.4`) |

### 9.2 기존 회귀 — `pipeline/tests/test_mapper_golden.py` 수정

| 변경 | |
|---|---|
| import | `_load_inputs` 삭제 → `parse_daily_report` import |
| 호출 | `inputs = _load_inputs(path)` → `parsed = parse_daily_report(path); inputs = _match_golden(parsed.activities)` |
| Mapper 호출 | `parsed_report=None` → `parsed_report=parsed` (시뮬 v3 패턴 복원) |
| 결과 검증 | 78/79 ≥ 95% (베이스라인 동등) — 개선 시 spec 갱신 |
| 회귀 안전망 | 정확도 < 95% 면 fail. conf 분포 / H-i-L 1 발동률 print 추가 (개선 폭 측정) |

### 9.3 결정성 검증

`state.md §3.4` 의 byte-diff 회귀: 같은 xlsx 2회 parse → dict 동등성 비교 (Python `==` 가 list/dict 재귀 비교). 단위 테스트에 포함.

### 9.4 실증 검증 — Parser → Mapper E2E 실 출력 dump

> **목적:** pytest assert 만으로는 "Parser 가 진짜로 시트1~3 dict 채우는가, Mapper 가 그걸 받아 어떤 컨텍스트로 LLM 호출하는가, 어떤 결과가 나오는가" 를 사람이 못 봄. 자동 회귀와 별도로 **실 출력 dump 검증 단계** 를 마지막 게이트로 둠. Iron Law (Real code or no claim — 실 명령어 + 실 출력 + 의도 일치) 의 "실 출력" 요건을 spec 안에 박는다.

#### 9.4.1 실행 스크립트

```bash
# 신규 스크립트 — scripts/parser_e2e_demo.py
$ uv run python3 scripts/parser_e2e_demo.py \
    docs/sample/통합작업일보_M15X\ Ph-3\ IBL\ PJT\ 작업일보_20250925.xlsx \
    --sample-rows 99,452,892,1207,1230
```

- 인자 1: 작업일보 xlsx 경로
- `--sample-rows`: Mapper 호출까지 보여줄 골든 row 5개 (남웅 1 + 세보 2 + 창원 2). 미지정 시 random 5건.
- 환경 변수 (`AZURE_OPENAI_*`, `POSTGRES_URL`, `CHROMA_HOST` 등) 는 `.env` 자동 로드.

#### 9.4.2 출력 형식 (사람이 읽도록 — pytest 가 아닌 stdout)

```
=== Parser 출력 ===
파일:        docs/sample/통합작업일보_..._20250925.xlsx
report_date: 2025-09-25
project:     M15X Ph-3 IBL PJT

bp_summaries: N건
  [0] 남웅건설 (PH_X-001) / 건축(AR) / FAB / A구간
        work_text_today: '...' (앞 80자)
        today_incr: ..., today_cum: ...
  ... (앞 5개만 print)

job_allocations: N건 (관리자 직종 필터 후, 합계 row 필터 후)
  [0] 남웅건설 / 철근공 / cum_t=...
  ... (앞 5개)

equipment_allocations: N건
  [0] 남웅건설 / 굴삭운반기계류 / Back Hoe / 2㎥미만 / cum_t=...
  ... (앞 5개)

activities: N건 (필수 셀 검증 후)
  [0] 남웅건설 / 철근배근 / m2 / today_qty=...
  ... (앞 5개)

=== Mapper 호출 (sample 5건 — 시뮬 v3 패턴 복원) ===

[R99] 남웅건설 / "철근배근" / m2 / today_qty=...
  → 골든:    철근콘크리트공사
  → 결과:    철근콘크리트공사 / conf 0.95 / source: llm_top1
  → BP 컨텍스트 (mapper.build_bp_context 그대로):
    [시트1] 주요작업 텍스트 (BP사 기재): ...
    [시트1] 금일 신규 투입 인원 (Incr.): ...명
    [시트1] 금일 누적 인원 (Cum.): ...명-일
    [시트2] 기능공 직종 (금일누계 Cum.T):
      - 철근공: ...명-일
      - 형틀공: ...명-일
      ...
    [시트3] 투입 장비 (금일투입누계 Cum.T):
      - 굴삭운반기계류/Back Hoe (2㎥미만): ...회-일
      ...

[R452] 세보엠이씨 / "ACID DUCT 설치" / m / today_qty=...
  → 골든:    ACID배기설비공사
  → 결과:    ACID배기설비공사 / conf 0.91 / source: llm_top1
  ...

(5건 출력)

=== 베이스라인 대비 ===
Parser 도입 전 (parsed_report=None, baseline 2026-05-15): 78/79 = 98.7%
Parser 도입 후 (parsed_report=parsed, 5건 sample): X/5
  (전체 79건 회귀는 test_golden_accuracy 에서 별도 측정)
```

#### 9.4.3 사람이 검증할 체크포인트

| # | 항목 | 합격 기준 |
|---|---|---|
| C1 | `bp_summaries` 비어있지 않음 | len ≥ 1 |
| C2 | `job_allocations` 의 관리자 직종 0건 | 'BP소장' / '공사관리자' / '안전관리자' / '품질관리자' / '일반관리자' 매치 0건 |
| C3 | `job_allocations` 의 합계 row 0건 | '투입 Total' 매치 0건 |
| C4 | `equipment_allocations` 의 big/mid/spec 채워짐 | 첫 5건의 equipment_big 모두 None 아님 |
| C5 | `activities` 길이 = fixture loader 와 동일 | `_load_inputs` 호출 결과와 len 비교 |
| C6 | Mapper 의 build_bp_context 가 fallback 안 탐 | "(parsed_report 미제공 — BP 컨텍스트 없이 진행)" 문구 0건 |
| C7 | 5건 sample 의 매핑 결과 출력 | 골든과 일치 / 불일치 표시 + conf 노출 |
| C8 | 결정성 — 2회 호출 시 dict 동일 | Python `==` 로 비교 |

#### 9.4.4 보고 형식 (Iron Law 3요소)

구현 완료 보고 시 다음 셋이 모두 포함돼야 함 (CLAUDE.md §3.4):

```
$ uv run python3 scripts/parser_e2e_demo.py docs/sample/통합작업일보_...xlsx \
    --sample-rows 99,452,892,1207,1230   ← (a) 실 명령어

<위 9.4.2 형식의 stdout 원본 그대로>     ← (b) 실 출력 (수정·생략 금지)

→ 체크포인트 C1~C8 모두 합격. 베이스라인 동등 유지. ← (c) 의도 일치 결론
```

(b) 누락 시 미실시로 간주. "다 통과했다" 만 적는 보고는 거부.

---

## 10. Open question — GATE 2 / GATE 3 측정 항목

| # | 질문 | 측정 시점 | 측정 방법 |
|---|---|---|---|
| Q1 | 시뮬 v3 패턴 복원 시 (parsed_report=parsed) 정확도가 변하는가? | Parser 구현 후 즉시 (5/16) | 골든 79건 재실행. baseline 78/79 와 비교. |
| Q2 | conf 분포가 변하는가? (특히 R459 의 0.83 → ?) | 위와 동시 | 모든 79건의 conf 출력 후 분포 비교. |
| Q3 | H-i-L 1 발동률이 변하는가? (`mapping_conf < 0.7` 비율) | 위와 동시 | 발동률 print 추가. |
| Q4 | 다른 작업일보 (다른 현장 / BP사) 에서 정확도 패턴은? | GATE 2 (5/22) | 추가 작업일보 fixture 확보 후 동일 측정. |
| Q5 | WA 3단계 (시트1 work_text_today LLM 추론) 활성화 시 효과? | GATE 2 (5/22), mapper.py:182 TODO 해소 | 시트1 BP사별 work_text_today 가 채워진 후 측정. |
| Q6 | `_DATE_PATTERN` 의 `.xlsm` 8자리 미매칭 — `작업일보_20250925.xlsm` 거부됨 | 첫 .xlsm 작업일보 투입 시 | regex 를 `_(\d{4})(\d{2})(\d{2})\.xlsm?$` 통합 패턴으로 변경 |
| Q7 | `_extract_meta` 의 project 키워드 (`M15X` / `IBL` / `PJT`) 하드코딩 — 다른 현장 적용 시 fallback 강제 | GATE 2 (5/22) 새 현장 파일 투입 시 | 시트1 row 1~3 의 첫 비어있지 않은 셀 또는 파일명 깨끗한 stem 추출 로직으로 교체 |
| Q8 | `_parse_sheet2/3` 의 `list(ws.iter_rows())` 전체 materialization — 시트2 15K rows 메모리 점유 | 동시 워커 20개 이상 시나리오 (PoC scope 외) | `_ffill` 을 iterator-based 로 리팩터, peak RSS O(1)/시트 |

---

## 11. 비결정 / GATE 별 결정 보류

| 항목 | 현재 결정 | 보류 사유 |
|---|---|---|
| 시트1 BP사 block 정확한 행 범위 | `/tmp/cpia_full_sim_v3.py:118` 패턴 재활용 | 실 파일 행 위치 코드 작성 단계 확정 — 시뮬 코드 발췌해서 검증 |
| 시트1 메타 (`project` 셀 위치) | 파일명 1차 / 시트1 헤더 2차 | 실 파일 확인 단계 확정 |
| `_match_golden` 헬퍼 위치 | 골든 테스트 파일 내부 | 다른 테스트가 row index 필요해지면 conftest 로 이동 |
| 시트3 `equipment_spec` 컬럼 인덱스 | 시뮬 코드 발췌 | 실 파일 검증 시점 확정 |

---

## 12. 변경 이력

| 날짜 | 내용 | 작성자 |
|---|---|---|
| 2026-05-15 | 초안 — 베이스라인 측정 (78/79=98.7%) + motivation 재정렬 + 책임 경계 + 공개 API + 시트별 셀 위치 + fixture loader 이관 + 테스트 전략 + GATE 2/3 open question | A 트랙 |
| 2026-05-15 | §9.4 실증 검증 단계 추가 — scripts/parser_e2e_demo.py 로 Parser → Mapper 실 출력 dump (Iron Law 3요소 강제) + 체크포인트 C1~C8 명시 | A 트랙 |
| 2026-05-15 | Task 7 회귀 실측 갱신 — v3 패턴 복원 후 77/79=97.5% (베이스라인 78/79=98.7%), R459/R469 conf 0.55 → H-i-L 1 발동 → 보완 후 100%. §1.3 흥미로운 패턴 (R459 conf 0.83→0.55) 데이터 근거 확보. §10 Q6~Q8 추가 (.xlsm 8자리 / project 키워드 하드코딩 / 시트 materialization). | A 트랙 |
