# CPIA `/home` 구성원 운영 홈 재설계 — Design

> 작성일: 2026-06-01 · 트랙: B_Track · 후속: `frontend-design` 스킬로 구현 (writing-plans 생략)

---

## 1. 배경 / 문제

현재 `/home`(`web/app/(app)/home/page.tsx`)은 누구에게나 동일하게 다음을 보여준다:

- KPI 4개: 누적 처리 / 오늘 처리 / 누적 절감 / 현재 처리 중(7-Agent active 합)
- `AgentWorkflow` (7-Agent 세로 워크플로우)
- `AgentChatLog` (챗 로그)

이 숫자·현황은 **경영진 인상용**이지, 실제로 매일 화면을 쓸 **현장 구성원**의 "오늘 할 일/오늘 상태"에는 닿지 않는다. 누적 처리량·Agent active 합산은 구성원에게 의미가 약하다.

## 2. 목표

`/home`을 **현장 구성원 관점의 단일 현장 운영 홈**으로 전면 교체한다. 네 가지 콘텐츠 블록으로 구성:

1. **인삿말 + 현장 헤더**
2. **처리현황 KPI 스트립** (+ 오늘 절감 시간, + 미제출 업체 칩)
3. **작업내용 카드** (협력업체별 작업 + 총 투입 인원·장비)

> 페르소나 토글(구성원/관리자)과 무관하게 **모두에게 새 구성으로 교체**한다. 관리자는 전체 현장 집계가 필요하면 `/dashboard`를 사용한다. `/home`은 구성원의 단일 현장(데모 = M15X Ph-3 IBL) 일일 운영 랜딩이다.

## 3. 범위 / 비범위

**범위(In)**
- `/home` 페이지 전면 교체 (단일 현장 = M15X, 시연 날짜 = 2025-09-25 고정)
- 신규 home 섹션 컴포넌트 3종
- 신규 fixture `mock_home.json` + `fixtures.ts` 로더/타입 추가
- 작업내용은 기존 `mock_report.json` 의 `details[date].raw_data` 재사용

**비범위(Out)**
- 실제 로그인/사용자-현장 매핑 (PoC 고정값 사용)
- 실제 날씨 API (mock 값)
- 현장 선택/전환 UI (단일 현장 고정)
- A_Track(파이프라인) 변경 없음. Postgres 실 API swap은 Phase 2 후속.
- 기존 home 컴포넌트(`OpsKpiCard·AgentWorkflow·StatusHeader·NowStrip·Hero·AgentCard·HilReviewStage`) 파일은 **삭제하지 않고 보존** — 타 화면 참조 여부 확인 후 별도 정리.

## 4. 화면 구조

위 → 아래 수직 흐름 (레이아웃 = "KPI 스트립 압축 + 작업내용 메인"):

```
┌─ [1] 인삿말 + 현장 헤더 밴드 ─────────────────────────────┐
│ (좌) 김현장님, 안녕하세요   오늘도 안전하세요 🦺            │
│ (우) M15X Ph-3 IBL · 2025-09-25(목) · ☀ 맑음 23°          │
└──────────────────────────────────────────────────────────┘
┌─ [2] 처리현황 KPI 스트립 ─────────────────────────────────┐
│  제출      처리완료   처리중    미제출    오늘 절감          │
│  9 / 12     7         2 ●       3         ~18h             │
├───────────────────────────────────────────────────────────┤
│  미제출 ▸  [철근 한신산업] [전기 파인텍] [도장 해광]        │
└──────────────────────────────────────────────────────────┘
┌─ [3] 작업내용 카드 ───────────────────────────────────────┐
│ 오늘 작업내용 · 총 투입 인원 69명 · 장비 6대               │
│ ┌────────┬──────┬───────────────────────────┬──────┐    │
│ │ 업체    │ 공종 │ 작업내용                   │ 인원 │    │
│ │ A건설   │ 골조 │ FAB 2층 벽체 거푸집 설치   │ 14명 │    │
│ │ …      │ …   │ …                         │ …   │    │
│ └────────┴──────┴───────────────────────────┴──────┘    │
└──────────────────────────────────────────────────────────┘
```

## 5. 섹션별 상세

### 5.1 인삿말 + 현장 헤더 (`HomeGreetingHeader`)

- **좌 (개인)**: `{userName}님, 안녕하세요` (큰 글씨) + 작은 글씨 `오늘도 안전하세요 🦺`
- **우 (현장 정보)**: `{siteName}` · `{date}({요일})` · `{weatherIcon} {weatherLabel} {temp}°`
- `userName`은 데모 고정값(예: "김현장"). 날씨는 mock 값. 현장명은 단일 현장 고정.

### 5.2 처리현황 KPI 스트립 (`HomeProcessingStrip`)

깔때기 모델 (협력업체별 일보 단위):

| 지표 | 값(데모) | 정의 |
|------|---------|------|
| 제출 | 9 / 12 | 예정 12개 업체 중 일보 제출 9건 |
| 처리완료 | 7 | 제출분 중 파이프라인 처리완료 |
| 처리중 | 2 | 처리 진행 중 (라이브 인상용 `●` 점) |
| 미제출 | 3 | 아직 일보 미제출 업체 수 |
| **오늘 절감** | **~18h** | **처리완료 7건 × 수작업 ~2.5h/건** (AS-IS 2~3h/건 → AI 5분, CLAUDE.md 근거). **누적 아닌 "오늘" 절감.** |

- 깔때기 정합성: 예정 12 = 제출 9 (처리완료 7 + 처리중 2) + 미제출 3.
- **미제출 칩** (`HomeProcessingStrip` 내부 또는 인접): 스트립 바로 아래 한 줄. 업체명을 칩으로 노출 — 클릭 없이 "누구한테 독촉할지" 보이게 한다. 행동 정보이므로 숨기지 않는다.
  - 예: `[철근 한신산업] [전기 파인텍] [도장 해광]` (공종 prefix + 업체명)
  - **업체명**: `company_normalize.json` 의 등록(matched_exact) 실명 사용 — 한신산업·파인텍·해광. 작업내용 테이블은 `raw_data`의 익명 bp_name(A건설~G건설)을 그대로 표시하나, 미제출(예정만 하고 미제출)과 제출 업체는 **서로 다른 집합**이라 같은 업체가 양쪽에 동시에 나오지 않는다.

### 5.3 작업내용 카드 (`HomeWorkSummaryCard`)

- 기존 `web/app/components/reports/RawDataTab.tsx` 의 **"카드 + 테이블"** 패턴을 따와 홈용으로 슬림화 (검색·CSV 등 부가 기능은 제외, export `ConsolidatedReportCard`와 톤 일관).
- **요약 바** (카드 헤더): `오늘 작업내용 · 총 투입 인원 {totalWorkers}명 · 장비 {totalEquipment}대`
  - `totalWorkers` = Σ `raw_data[].workers` = **69** (2025-09-25 데모 기준)
  - `totalEquipment` = home fixture에 명시값 = **6** (raw_data의 equipment는 문자열 "타워크레인 1호기/펌프카 2대/토치/-" 등이라 대수 파싱이 불안정 → 데모 안정성 위해 fixture에 정수로 둔다. 토치 같은 공구·"-"·대기 장비 제외한 중장비 기준)
- **테이블 컬럼** (raw_data 매핑): **업체(`bp_name`) · 공종(`trade`) · 작업내용(`work_content`) · 인원(`workers`)**
  - **장비 컬럼 제거** — 총 대수만 요약 바에 표기.
  - 테이블 행 = `raw_data` 7행 = 처리완료 7건. **처리중 2건은 아직 작업내용이 생성되지 않아 테이블에 나오지 않는다** (스트립의 "처리완료 7"과 테이블 행 수가 일치).

## 6. 데이터 설계

### 6.1 신규 fixture `data/mock_home.json`

shape는 실 API와 일치시켜 Phase 2 swap만으로 전환되게 한다. 예시:

```json
{
  "site": {
    "id": "m15x-ph3-ibl",
    "name": "M15X Ph-3 IBL",
    "date": "2025-09-25",
    "weather": { "icon": "sun", "label": "맑음", "temp_c": 23 }
  },
  "user": { "name": "김현장" },
  "processing": {
    "expected": 12,
    "submitted": 9,
    "completed": 7,
    "in_progress": 2,
    "unsubmitted": 3,
    "hours_saved_today": 18
  },
  "unsubmitted_companies": [
    { "trade": "철근", "name": "한신산업" },
    { "trade": "전기", "name": "파인텍" },
    { "trade": "도장", "name": "해광" }
  ],
  "work_summary": {
    "total_workers": 69,
    "total_equipment": 6
  }
}
```

> `unsubmitted_companies`의 업체명은 `company_normalize.json` 의 등록 실명(한신산업·파인텍·해광)을 사용한다. `total_workers`(69)는 raw_data Σworkers와 일치, `total_equipment`(6)는 중장비 기준 명시값.

### 6.2 작업내용 데이터

- 기존 `mock_report.json` → `details["2025-09-25"].raw_data` (7행) 재사용. 추가 데이터 불필요.
- `RawDataRow` 타입: `{ building, trade, wp, bp_name, work_content, quantity, unit, workers, equipment }` — 이 중 `bp_name·trade·work_content·workers` 사용.

### 6.3 `web/lib/fixtures.ts`

- `FixtureMap`에 `home: HomeFixture` 추가, `HomeFixture` 타입을 `web/lib/types.ts`에 정의.
- 로더는 기존 `loadReal`/`loadFixture` 규약을 따른다 (현 home은 `loadReal` 사용 중 — Phase 2 PG swap 대상). 데모 단계에서는 fixture 로딩으로 충분.

## 7. 컴포넌트 / 파일 변경

| 파일 | 변경 |
|------|------|
| `web/app/(app)/home/page.tsx` | 전면 교체 — 3개 신규 섹션 조립, `mock_home` + `report.raw_data` 로드 |
| `web/app/components/home/HomeGreetingHeader.tsx` | 신규 (5.1) |
| `web/app/components/home/HomeProcessingStrip.tsx` | 신규 (5.2, 미제출 칩 포함) |
| `web/app/components/home/HomeWorkSummaryCard.tsx` | 신규 (5.3, RawDataTab 패턴 재사용) |
| `data/mock_home.json` | 신규 fixture (6.1) |
| `web/lib/fixtures.ts` / `web/lib/types.ts` | `home` fixture 로더 + `HomeFixture` 타입 추가 |
| `OpsKpiCard·AgentWorkflow·StatusHeader·NowStrip` | home에서 참조 제거 (파일 보존) |

## 8. 디자인 가이드

- 타입 스케일: `docs/ui/sample/font.png` 단일 출처, `text-h1..h6 / body / btn` 토큰만 사용 (프로젝트 규칙).
- 카드/박스 헤더·외형은 기존 `reports`/`export` 컴포넌트와 통일 (`rounded-card`, `border-border-soft`, `bg-card`, `shadow-xs`, `font-display`).
- 색 톤: KPI 스트립은 기존 `OpsKpiCard` tone(brand/mint/sun/sky) 팔레트 재사용 가능.
- 구현은 `frontend-design` 스킬로 진행.

## 9. 수용 기준 (Acceptance)

- [ ] `/home` 진입 시 4블록(인삿말·처리 스트립·미제출 칩·작업내용)이 위→아래로 렌더된다.
- [ ] 인삿말에 사용자명 + "오늘도 안전하세요" + 현장명·날짜·날씨가 보인다.
- [ ] KPI 스트립에 제출·처리완료·처리중·미제출·**오늘 절감(h)** 5지표가 보이고 깔때기 숫자가 정합한다.
- [ ] 미제출 업체명이 칩으로 클릭 없이 노출된다.
- [ ] 작업내용 카드에 총 인원·총 장비 대수 요약 + 협력업체별(업체·공종·작업내용·인원) 테이블이 보인다 (장비 컬럼 없음).
- [ ] 기존 KPI4 / AgentWorkflow / AgentChatLog 가 `/home`에서 사라진다.
- [ ] `npm run build` 통과, `tsc` clean.
