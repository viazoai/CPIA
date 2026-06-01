# CPIA Parser — 헤더 기반 결정론 추출로 업체작업일보 포맷 지원

- 작성일: 2026-06-01
- 상태: 설계 합의 완료, 구현 대기
- 관련 이슈: [A_Track] Parser 파싱 오류 (#52)
- 관련 코드: `pipeline/agents/parser.py`, `pipeline/agents/parser_node.py`, `pipeline/state.py`
- 대상 데이터: `data/demo_inputs/20250925/` 업체작업일보 10개

---

## 1. 배경

issue #52 — 업체작업일보를 파이프라인에 넣으니 `parser_activities` 33행이 전부
`trade="UT"` / `company="F02 5F"` / `work_content="M"` 같은 오값으로 저장됨.

전수 측정(`data/demo_inputs/20250925/` 10개) 결과:

- **10개 파일은 사실상 단일 양식**이다. 시트 10종 이름·순서, 시트4 헤더 18칸,
  BP코드(`M15X_PH4_041`), 회사명(`중원엔지니어링FAB`), 내부 33행 payload 까지
  바이트 수준으로 동일. 같은 템플릿을 파일명(업체명+공종)만 바꿔 복제한 사본.
- 유일한 변종은 확장자 — `.xlsx` 7개 / `.xlsm` 3개.
- 이 10개는 전부 **업체포맷**이며, 현 파서가 전제하는 **통합포맷**과 다르다.

현 파서 `parse_daily_report`(`parser.py:539`)는 통합작업일보(별도 '업체명' 컬럼 +
`col25` final_flag 'O' 마커 + `PH_X-NNN` BP코드)를 전제로 컬럼 위치를 숫자로
하드코딩한다. 그래서 업체포맷 10개 전부 깨진다:

| 결과 | 파일 | 원인 |
|---|---|---|
| ParseError 즉사 | `.xlsm` 3개 | `_DATE_PATTERN` 이 8자리+`.xlsm` 미지원 |
| 조용히 오염 (act=33 bp=1 **job=0 eq=0**) | `.xlsx` 7개 | 컬럼 시프트 + final_flag 부재 + BP정규식 불일치 |

**정상 추출 0건.**

### 1.1 관측된 7개 깨짐

1. **시트4 컬럼 1칸 시프트** (7개): 업체포맷엔 '업체명' 컬럼이 없어 `col7` 이후가
   1칸 좌측으로 밀림. 파서는 `col6=회사명/col8=work_content/col9=unit/col12=today_qty`
   (`parser.py:362-401`) 를 가정하나, 실헤더는 `col6=Scope/col7=작업내용/col8=단위/col9=총물량/col11=금일실적/col12=금일누적`.
   결과: `company←Scope("F02 5F")`, `work_content←단위("M")`, `unit←총물량("2178")`.
2. **today_qty 가 금일실적[C] 대신 금일누적[D]** (7개): `c12→today_qty`(`parser.py:381`)
   인데 실헤더 `col12=금일누적[D]`. 실측 `금일실적[C]=30`(col11)인데 파서는 `today_qty=120`(누적).
3. **`_DATE_PATTERN` 이 `.xlsm`+8자리 미지원** (3개): 패턴
   `_(\d{4})(\d{2})(\d{2})\.xlsx$|_(\d{6})\.xlsm?$`(`parser.py:503`) — 8자리 분기는 `.xlsx` 만,
   `.xlsm` 분기는 6자리만. `_20250925.xlsm` 은 둘 다 미매칭 → `_extract_meta`(`parser.py:516`)에서 ParseError.
4. **`_BP_RE` 가 `M15X_PH4_041` 미매칭** (10개): `^PH[_\- ]?X[_\- ]?\d+$`(`parser.py:100`)는
   `PH_X-088` 류만 매칭. `M15X_PH4_041` 은 False(실측). 시트2/3 group 검출(`parser.py:278,446`)
   전멸, 시트4 에서 회사명행이 별도 activity 의 bp_code 로 누출.
5. **final_flag 'O' 마커 전무** (10개): 시트2 `col25`(maxrow=89)·시트3 `col25`(maxrow=74) 모두
   nonnull=0. 파서가 `col25=='O'` 를 job/equip row 게이트로 요구(`parser.py:276,472`) → 전부 0건.
6. **파일명 날짜 vs 시트 내부 작업일자 불일치** (10개): 파일명 `20250925`, 시트4 row2
   `금일 작업 현황: 2025-09-17`. 파서는 파일명 우선 추출.
7. **BP코드와 회사명이 같은 `col5` 에 교대** (10개): `M15X_PH4_041`(코드행) 다음
   `중원엔지니어링FAB`(회사명행). 별도 업체명 컬럼 없음. [4]와 결합해 분리 실패.

---

## 2. 스코프

### 2.1 이번 스코프 (데모 기준, LLM 없음)

`data/demo_inputs/20250925/` 의 업체포맷 10개(확장자 2변종)를 **결정론으로 정확히 파싱**한다.
기존에 정상 동작하던 통합포맷도 회귀 없이 유지한다. 한 코드 경로가 두 포맷을 모두 처리한다.

### 2.2 비목표 (다음 브레인스토밍)

- 업체마다 헤더·시트구성이 제각각인 **N종 양식** 대응 → LLM 2-pass 인식 레이어.
  현 표본엔 검증할 변종이 없어 이번엔 만들지 않는다 (speculative abstraction 금지).
- 업체 시트6(출력일보)의 작업자별 WBS 데이터를 mapper 매핑에 보강하는 일.
- `parser_llm.py`(deprecated 6시트 LLM 파서) 부활.

---

## 3. 설계

### 3.1 핵심 전환: 컬럼 인덱스 하드코딩 → 헤더 텍스트 해석

현 파서의 근본 문제는 `ws.cell(r, 8)` 처럼 컬럼 위치를 숫자로 박은 것이다.
업체포맷은 '업체명' 컬럼 부재로 한 칸 밀려 전부 어긋난다.

해결: **각 시트의 헤더 row 를 먼저 읽어 `{스키마 필드 → 실제 컬럼 인덱스}` 매핑을 만든다.**
헤더가 `대표물량_작업 내용` 이면 그 컬럼이 `work_content`, `금일실적` 이면 `today_qty`.
이러면 통합('업체명' 컬럼 있음)이든 업체(없음)든 같은 코드가 자동으로 흡수한다.

합의된 2-pass 구조에서 이번 구현은 **Pass 2(결정론 추출기)** 에 해당한다.
Pass 1(LLM 인식) 자리에는 LLM 대신 **헤더 동의어 룩업 테이블**(`'금일실적' → today_qty`)을
놓는다. 다음 브레인스토밍에서 헤더가 제각각인 N종이 오면, 룩업이 실패하는 지점에
LLM 인식을 끼우면 된다 — 구조는 그대로 두고 확장.

### 3.2 컴포넌트

#### (a) 헤더 해석기 (header resolver)

- 입력: 시트 워크시트 + 해당 시트의 헤더 row 번호.
- **헤더는 2-row 스택 구조** (측정 확인): 시트1/4 = row3(구분/Zone/공종/BP사/Scope/대표물량_작업내용 등 주 라벨) + row4(PJT/Dis/협력업체, `[A][B][C][D]` 수량 마커),
  시트2/3 = row4(공종/BP사/직종 또는 장비명) + row5(Dis/협력업체, 조출/주간/연장/야간/철야 시간대 sub-column).
  필드 일부(특히 `금일실적[C]` vs `금일누적[D]` 구분, 시간대 6칸 블록)는 둘째 헤더 row 에 있으므로
  해석기는 인접 두 헤더 row 를 함께 읽어 `{필드 → 컬럼}` 매핑을 만든다.
- 동작: 헤더 row 의 각 셀 텍스트를 정규화(공백·개행 제거)하여 동의어 룩업 테이블로
  `{필드 → 컬럼 인덱스}` 매핑 생성.
- 동의어 테이블 예 (시트4): `대표물량_작업내용 → work_content`, `단위 → unit`,
  `총물량 → plan_total_qty`, `전일누적 → yesterday_cum_qty`, `금일실적 → today_qty`,
  `금일누적 → today_cum_qty`, `잔여 → remaining_qty`, `공종 → trade`, `BP사 → bp_field`,
  `Scope → scope`, `업체명 → company_col`(있으면 통합포맷).
- 포맷 자동 판정: '업체명' 헤더 발견 시 통합포맷(company = 별도 컬럼),
  미발견 시 업체포맷(company = `col5` 교대행에서 추출).
- 동의어 테이블에 없는 헤더는 무시(이번 스코프). 필수 필드(work_content/today_qty 등)가
  매핑 안 되면 ParseError 로 명확히 실패 (조용한 오염 금지).

#### (b) 포맷 적응 추출 — 시트4 와 시트1/2/3 수정 강도가 다름 (시뮬레이션 검증)

프로토타입 시뮬레이션(2026-06-01)에서 통합포맷 회귀로 확인된 원칙:

- **시트4 (column shift 본체)**: 헤더 기반 컬럼 해석으로 전면 전환. 통합/업체 둘 다 정확.
  검증: 통합 `activities=1193` 으로 기존 baseline 과 정확히 동일, 업체 work_content/unit/today_qty/company 정상.
- **시트1/2/3**: 기존 `_parse_sheet1/2/3` 함수를 **보존**하고 최소 패치만 가한다 —
  `_is_bp_code`(BP 다중패턴) 교체 + final_flag 조건부 완화(§e) + 컬럼 인덱스 헤더 주입.
  **전면 재작성 금지.** 시뮬레이션에서 시트1/2/3 을 단순 재작성하니 통합이
  bp 99→159 / job 975→11836 / eq 1111→12437 로 과다 카운트됐다. 기존 group 경계
  (col30 병합셀), 빈 placeholder skip, admin 직종 필터를 유지해야 회귀가 안전하다.
- **기존 검증 로직은 그대로 재사용**: `_shift_dict_sum`/`_shift_dict_row`(시간대 6칸 집계),
  `normalize_company`·`split_company_and_zone`(`parser_post.py`), `extract_zone`, `_ffill`.
  이들의 인자(컬럼 인덱스)만 하드코딩 → 매핑 주입으로 바꾼다.

#### (c) BP코드 다중 패턴 + 코드/회사명 분리

- `_BP_RE` 를 단일 정규식 → **다중 패턴** 으로 확장: 최소 `PH_X-NNN`(통합) +
  `{라인}_{PHn}_{NNN}`(예 `M15X_PH4_041`, 업체).
- `_is_bp_code` 가 이 다중 패턴으로 판정. 시트1/4 `col5` 의 코드행/회사명행 교대를
  "패턴 매칭되면 bp_code, 아니면 company" 로 정확히 분리(기존 `parser.py:192-200` 구조 유지,
  판별기만 교체).

#### (d) 날짜/메타 일반화

- `_DATE_PATTERN` 을 확장자(xlsx/xlsm)·자리수(6/8) 무관하게 일반화:
  `_(\d{4})(\d{2})(\d{2})\.xls[mx]?$|_(\d{6})\.xls[mx]?$`.
- report_date 출처: **파일명 우선(현행 유지)**. 시트4 row2 내부 작업일자를 추가로 읽어
  파일명 날짜와 다르면 **경고 로그**(stderr, 결정성 보존). report_date 값 자체는 파일명 기준 불변.
- project 추출 fallback 의 `통합작업일보_` prefix 제거(`parser.py:532`)에 `업체작업일보_` 도 추가.

#### (e) final_flag 게이트 완화 — 반드시 조건부 (회귀 위험 실측)

- 시트2/3 의 job/equip row 판정에서 `col25=='O'` 강제를 **조건부로만** 완화:
  final_flag 컬럼에 'O' 값이 하나라도 있으면(통합) **'O' 기준 그대로 유지**,
  컬럼이 없거나 전행 None 이면(업체) 직종코드(`Mm##`/`sk##`)·장비 대분류 존재로 판정.
- **무조건 완화 금지**: 시뮬레이션에서 'O' 게이트를 그냥 제거하니 통합포맷이
  job 975→11836 / eq 1111→12437 로 폭증했다 ('O' 없는 중간 집계행까지 셈).
  완화는 'O' 마커가 실제로 없는 파일에만 적용한다.
- 시트2 group 시작 앵커 `col4=='Mm01'`(`parser.py:269-280`)도 헤더 기반 직종코드 컬럼에서
  첫 관리자코드 행으로 일반화.

### 3.3 데이터 계약 (불변)

출력은 `ParsedDailyReport`(`state.py:207`) 그대로. `Activity`/`BPSummary`/`JobAllocation`/
`EquipmentAllocation` 필드 변경 없음. 따라서 mapper·atomizer·exporter·forecaster 는 무수정.
"여러 업체일보 → 통합 합치기"는 이미 exporter 의 `fetch_sheet_data`(`exporter.py:37-97`)가
수행한다 — `WHERE pr.site_id = $1 AND report_date = $2` 로 같은 현장·같은 날의 모든 run 행을
합집합으로 긁어 1개 통합 산출물로 만든다 (literal SQL UNION 키워드가 아니라 행 단위 합집합).
이번에 손대지 않는다.

### 3.4 LLM 검증 처리

현 `_verify_sheet1/4_via_llm`(`parser.py:597-760`)은 ①시트4 raw 비교축 부재
②stderr-only ③크레덴셜 없으면 silent skip ④결과 보정 안 함 으로 사실상 무력하다.
이번 결정론 헤더 추출이 의미 인식을 대신하므로 **이 사후검증은 제거**한다(또는 비활성 유지).
검증의 책임은 §4 골든 테스트가 진다.

---

## 4. 검증 전략 (dry-test, LLM bypass)

LLM 비결정성을 배제하고 결정론 코드만 검증한다.

### 4.1 업체포맷 골든

- demo_inputs 10개 → 기대값 fixture 고정:
  - `.xlsx` 7개 / `.xlsm` 3개 모두 ParseError 없이 파싱.
  - activities: work_content = 실제 작업내용(`PCW 20 배관 공사` 등, 'M' 아님),
    unit = `M`(단위), today_qty = 금일실적[C](`30`, 누적 120 아님), company = 실제 회사명,
    trade = 공종.
  - bp_summaries / job_allocations / equipment_allocations 가 0 이 아님(final_flag 완화 효과).
- 결과를 결정론 비교(동일 입력 2회 실행 → 동일 출력).

### 4.2 통합포맷 회귀

- 통합작업일보(`docs/sample/...20250925.xlsx`) 파싱 결과를 골든으로 고정 (기존 파서 baseline 실측):
  **activities=1193 / bp_summaries=99 / job_allocations=975 / equipment_allocations=1111**.
- 헤더 기반 리팩터 후 이 4개 건수가 정확히 동일해야 하고, 핵심 필드(work_content='1) 슈퍼데크 설치' 등)도 일치.

### 4.3 통과 기준

업체포맷 골든과 통합포맷 회귀가 **같은 코드 경로**로 둘 다 통과해야 "두 포맷 처리"가 증명된다.

### 4.4 프로토타입 시뮬레이션 결과 (2026-06-01, 설계 사전검증)

헤더 기반 추출 프로토타입을 데모 10개 + 통합 1개에 결정론 실행:

- **업체포맷 10개 (`.xlsm` 3 포함)**: 전부 date=2025-09-25 추출, act=33 bp=1 job=76 eq=68.
  work_content='PCW 20 배관 공사', unit='m', today_qty=30(실적 C), company='중원엔지니어링',
  bp_code='M15X_PH4_041'. issue #52 오값(M / F02 5F / 120) 전부 정상화 ✓.
- **통합포맷 시트4**: act=1193 으로 baseline 정확 일치 — 헤더 기반 column shift 수정이
  통합·업체 양쪽에서 정확함을 실증 ✓.
- **통합포맷 시트1/2/3**: 프로토타입의 단순 재작성 탓에 과다(bp 159 / job 11836 / eq 12437).
  → 본 구현은 §3.2(b)·(e)대로 **기존 로직 보존 + 최소 패치**로 가야 함이 확정됨.

---

## 5. 마이그레이션

- 수정 파일: `pipeline/agents/parser.py` (헤더 해석기 추가 + 시트1/2/3/4 추출 함수
  컬럼 인덱스 주입화 + BP 다중패턴 + 날짜 일반화 + final_flag 완화 + LLM 검증 제거).
- `pipeline/agents/parser_node.py`·`state.py`·다운스트림: 무수정.
- `parser_llm.py`: 이번 손대지 않음(deprecated 유지).
- 기존 테스트(`pipeline/tests/test_parser.py` 등)는 회귀 가드로 유지, 골든 테스트 추가.

---

## 6. 미해결 / 다음 단계

- **N종 제각각 양식 → LLM 2-pass 인식 레이어** (다음 브레인스토밍). 헤더 동의어 룩업이
  실패하는 양식이 들어올 때, Pass 1 LLM 이 헤더→필드 매핑 레시피를 생성·캐시하도록 확장.
- 업체 시트6(출력일보) 작업자별 WBS → mapper 매핑 보강.
- 실제 운영 양식 다양성 측정(demo_inputs 외 실파일 확보).
