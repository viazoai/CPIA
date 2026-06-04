# CPIA 통합작업일보 Export 양식 정합 — 설계 (Design)

> brainstorming 산출물. 다음 단계는 writing-plans 로 구현 플랜 작성.
> 대상 파일: `pipeline/agents/exporter.py` (단일 파일). 브랜치: `feature/review-l75-hil`.
> 기준 데이터: DB run (`site_id='m15x-ph3-ibl'`, `report_date=2025-09-25`), `fetch_sheet_data` → `render_xlsx` 실 경로.

## 1. 배경

UI "Excel 출력" 버튼 → FastAPI `/export/run` → `exporter.render_xlsx` → 통합작업일보 xlsx (4시트: `1.출력인원 현황`/`2.직종별 인원현황`/`3.장비현황`/`4.물량`). 현재 `render_xlsx` 는 템플릿(`exporter_templates/consolidated_template.xlsx`)에 값만 박고, 업체 구분·중복정리·숨김해제·구분(PJT)칸이 없어 가독성이 낮고 UI 화면과 불일치한다.

## 2. 문제 (전부 실측 — 추측 아님)

| # | 증상 | 실측 근거 |
|---|------|-----------|
| P1 | 시트2·3 데이터/양식이 숨겨져 안 보임 | 템플릿 `2.직종별`: `auto_filter.ref='B5:Y15685'` + row hidden(데이터 인근 다수) + **row outlineLevel=2(접힘)** + **column D·Y hidden** + `freeze='F26'`. `3.장비`: row hidden 다수 + column Y hidden + `freeze='D6'`. (템플릿이 ~15000행까지 hidden·outline 을 보유 — 실제 데이터는 r5~, 아래 빈 행 hidden 은 출력 무관.) |
| P2 | 구분(col2, PJT/현장)이 전 시트 빈칸 | `render_xlsx` 가 `project` 인자를 받지만 `_fill_output_manpower`/`_fill_quantity` 에 전달 안 함 → col2 = None. UI route 는 `pjt='M15X Ph-3 IBL'` 제공. |
| P3 | 시트1 공종(col4) 빈칸 | `bp_summaries` 에 `disc_abbrev` 없음(7/7 None). UI(`/api/mock/consolidated`)도 `trade=''` 로 동일하게 빈칸. |
| P4 | 회색 fill | exporter 가 아니라 **PoC 아티팩트** — PoC 의 `capture_col_styles` 가 샘플의 노랑/회색 fill(`FFFFFF00`)을 데이터행에 복제했음. 템플릿 시트2·3 데이터셀 fill 은 없음(흰색). |
| P5 | 업체 그룹 시각 구분 없음 | dedup(중복 셀 비우기)·그룹 경계 테두리 미적용. 샘플 통합일보는 같은 (Zone~업체명) 연속 행을 맨 위만 남기고 비우며, 업체 경계에 진한 가로선을 둔다. |

### 2.1 UI ↔ exporter 데이터 소스 대조 (실측)

`fetch_sheet_data` 와 UI route `/api/mock/consolidated` 는 같은 DB·동일 zone 산식(`mapper_activities.wa` 회사별 최빈, 시트4는 활동별 `mapper_wa`)을 쓴다. 9/25 기준 차이는 **구분(col2)뿐**:

| 필드 | UI route | exporter | 판정 |
|------|----------|----------|------|
| 구분/PJT(col2) | `pjt='M15X Ph-3 IBL'` | None | ❌ 채워야 함 (P2) |
| zone(col3) | CUB/FAB | CUB/FAB | ✅ 일치 |
| 업체(시트4 col6) | `bp_name='광건'` | 광건 | ✅ 일치 |
| 공종(시트4·2·3) | 건축/토목 | 건축/토목 | ✅ 일치 |
| 공종(시트1 col4) | `''` (0/7) | None | ⚠️ 양쪽 빈칸 → 보강(아래 D2) |

DB: `mapper_activities.wa` 115건 중 113건(98%) 채워짐. `sites.name='M15X Ph-3 IBL'`.

## 3. 목표

`render_xlsx` 출력이 다음을 만족한다 (DB run 데이터 기준):
1. 업체별로 사람이 구분해 읽을 수 있다 — dedup + 그룹 경계 테두리.
2. 시트2·3 의 숨김(autofilter·row/col hidden·outline·freeze)이 완전히 풀리고 흰색이다.
3. 시트1 이 "작업사항" 으로 재정의된다 — 주요작업(col9)까지만 보이고 인원(col10~37) 숨김, 구분·공종이 채워진다.
4. 구분(col2)이 UI(`pjt`)와 동일하게 채워진다.

## 4. 확정 결정 (사용자 승인)

- **테두리: 옵션1 (샘플 동일)** — 업체 경계 행 위선 = `thin`(진한 실선), 같은 업체 내부 행 위선 = `hair`(흐린 선), 모든 행 아래선 = `hair`, 좌우 = `thin`.
- **구분(col2) 값 = `project` (= `sites.name` = `M15X Ph-3 IBL`)**, 표의 **첫 데이터 행 1회만** 표기(샘플 양식; 이후 행은 비움).
- **시트1 공종(col4) = 업체 공종으로 채움** — 시트4(물량)의 업체별 `trade`(건축/토목) 대표값을 업체→공종 맵으로 만들어 시트1 공종 칸 채움.

## 5. 설계

### 5.1 `render_xlsx` 흐름

```
wb = load_workbook(TEMPLATE_PATH)
_fill_output_manpower(ws1, output_manpower, report_date, company_wa=, company_trade=, project=)  # 공종·구분 추가
_fill_occupation(ws2, ...)
_fill_equipment(ws3, ...)
_fill_quantity(ws4, quantity, report_date, project=)                                              # 구분 추가
_finalize_layout(wb, sheet_data)   # 신규: 숨김해제 + dedup + 그룹테두리 + 시트1 재정의
return bytes
```

> capture_col_styles(샘플 스타일 복제)는 **이식하지 않는다** — 회색의 원인(P4)이며, exporter 는 템플릿 기본 스타일을 그대로 쓴다. `_finalize_layout` 은 테두리만 그룹 규칙으로 덮어쓴다.

### 5.2 데이터 보강 (`fetch_sheet_data` / `SheetData`)

- **D1 구분**: `render_xlsx(project=...)` 를 `_fill_output_manpower`·`_fill_quantity` 로 전달. 두 함수는 **첫 데이터 행(i==0)에만** `COL_*["project"]`(=col2)에 `project` 기입.
- **D2 시트1 공종**: `SheetData` 에 `company_trade: dict[str,str]` 추가. `fetch_sheet_data` 가 `mapper_activities` 에서 `company → trade` 대표값(최빈, 동률 시 사전순)으로 채움. `_fill_output_manpower` 는 `row.get("disc_abbrev") or company_trade.get(company)` 로 col4 기입.

### 5.3 `_finalize_layout(wb, sheet_data)` (신규)

시트별 데이터 행 수 `n` = `len(sheet_data.<list>)`. `DATA_START_ROW=5` 고정(템플릿 헤더는 r4까지 — 전 시트 데이터 r5 시작, 실측 확인).

**(a) 숨김 완전 해제** — 모든 시트:
- `ws.auto_filter.ref = None`
- `r in [1 .. DATA_START_ROW+n+3]`: `row_dimensions[r].hidden=False`, `.outlineLevel=0` (데이터 영역 한정 — 그 아래 빈 행의 잔존 hidden 은 출력에 무관하므로 둔다)
- 모든 `column_dimensions`: `.hidden=False`, `.outlineLevel=0`
- `ws.sheet_view.showOutlineSymbols=False`
- `ws.freeze_panes="A5"` (이상한 F26/D6 교정, 헤더 r1~4 고정)

**(b) dedup (중복 셀 비우기)** — 시트별 그룹 키:

| 시트 | 그룹 키 컬럼 (1-indexed) | 의미 |
|------|--------------------------|------|
| 1.작업사항 | [3, 4, 5] | Zone·공종·BP사(업체) |
| 2.직종별 | [2, 3] | 공종·BP사 |
| 3.장비 | [2, 3] | 공종·BP사 |
| 4.물량 | [3, 4, 5, 6] | Zone·공종·BP사·업체명 |

규칙: 위에서 아래로, **현재 데이터 행의 키 튜플이 직전 데이터 행과 전부 같을 때만** 그 키 컬럼들의 값을 `None` 으로 비운다. 하나라도 다르면(특히 Zone) 비우지 않는다. (`MergedCell` 은 건너뜀.)

**(c) 그룹 테두리 (옵션1)** — 데이터 행 `c0..c1` (시트1·2·3 = 2..각자, 시트4 = 2..17):
- 새 그룹(키 ≠ 직전) 행: top = `thin`
- 같은 그룹 행: top = `hair`
- 모든 행: bottom = `hair`, left = `thin`, right = `thin`

**(d) 시트1 재정의**:
- 작업사항 col7·8·9: 값에 `" | "` 있으면 `"\n"` 치환(DB는 이미 `\n`), `Alignment(wrap_text=True, vertical="top")`, 행높이 = `max(15, min(줄수,12)*14)`.
- col10~37(인원 timeshift) `column_dimensions[..].hidden=True`.
- `ws.title = "1.작업사항"` (마지막에).

### 5.4 컬럼 매핑 (기존 `COL_*` 재사용, 변경 없음)

`COL_OUTPUT_MANPOWER`(시트1) project=2, zone=3, trade=4, bp_code=5 / `COL_QUANTITY`(시트4) project=2, zone=3, trade=4, bp_code=5, company=6. 시트2·3 은 col2=공종(trade), col3=BP사 — **구분 칸 없음**(구분 채움은 시트1·4만).

## 6. 비범위 (YAGNI)

- **인원 '주간 몰림'**(조출/연장/야간/철야 0): v2 데모 데이터 특성. 양식 작업에서 건드리지 않음. (원본은 분포하나 우리 데모 생성기 한계)
- **`capture_col_styles`**: PoC 전용. exporter 에 이식 안 함.
- `exporter.py` 외 파일 변경 없음. 템플릿 파일 자체도 수정 안 함(런타임 후처리만).
- forecaster/optimizer/생산성 산식 무관.

## 7. 검증 (구현 후)

`fetch_sheet_data(pg, 'm15x-ph3-ibl', 2025-09-25)` → `render_xlsx(..., project='M15X Ph-3 IBL')` 결과 xlsx 로 결정론적 확인:

1. **숨김**: 4시트 데이터행 hidden=0 · row outlineLevel=0 · `auto_filter.ref=None` · `freeze='A5'`. column hidden=0 (시트2·3·4) — 단 시트1 은 col10~37 만 hidden(의도).
2. **시트1**: 탭명 `1.작업사항`, col10~37 hidden=True / col9 hidden=False, r5 구분=`M15X Ph-3 IBL`(이후 행 None), 공종 7/7 채워짐(건축/토목), 작업사항 wrap.
3. **시트4**: dedup — 광건 첫 행만 Zone~업체명, 다음 행 None; Zone 다른 그룹은 안 비움. 테두리 — 새 그룹 top=thin, 내부 top=hair.
4. **시트2·3**: 데이터행 fill patternType=None(흰색), 88·136행 전부 보임.
5. **UI 정합**: `/api/mock/consolidated?date=2025-09-25` 의 zone·공종·업체·pjt 와 엑셀 동일.
6. **회귀**: 기존 exporter 테스트(`pipeline/tests`) 통과.

## 8. 리스크

- `_finalize_layout` 이 `SheetData` 리스트 길이(=데이터 행수)에 의존 → 길이 정확해야 dedup/테두리 범위가 맞음.
- 템플릿 기본 스타일만으로 시트4 가독성이 충분한지 1차 구현 후 육안 확인(샘플 대비). 부족하면 별도 논의(현 spec 범위 밖).
- `company_trade` 대표값: 한 업체가 복수 공종이면 최빈 1개만 — 시트1은 업체당 1행이라 허용 가능.
