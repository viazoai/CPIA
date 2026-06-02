# CPIA `/home` 구성원 운영 홈 재설계 — Design

> 작성일: 2026-06-01 · 트랙: B_Track · 구현: `frontend-design` 스킬 (writing-plans 생략)
> **갱신: 2026-06-01 — 최종 구현 반영** (사진 컬러 히어로 · 공용 KpiStrip 재사용 · 외부 헤더 · DATA_DIR 버그fix · 구 컴포넌트 7종 삭제). 초기 설계(서브헤더 밴드·처리 strip)에서 시연 피드백으로 발전한 최종본.

---

## 1. 배경 / 문제

기존 `/home`(`web/app/(app)/home/page.tsx`)은 누구에게나 동일하게 보여줬다:

- KPI 4개: 누적 처리 / 오늘 처리 / 누적 절감 / 현재 처리 중(7-Agent active 합)
- `AgentWorkflow` (7-Agent 세로 워크플로우) + `AgentChatLog` (챗 로그)

이 숫자·현황은 **경영진 인상용**이지, 매일 화면을 쓸 **현장 구성원**의 "오늘 할 일/오늘 상태"에는 닿지 않는다. 누적 처리량·Agent active 합산은 구성원에게 의미가 약하다.

## 2. 목표

`/home`을 **현장 구성원 관점의 단일 현장 운영 홈**으로 전면 교체한다. 세 블록:

1. **인삿말 + 현장 헤더** — 현장 항공사진 컬러 히어로 밴드
2. **처리 현황** — 공용 `KpiStrip` 5블록 + 미제출 업체 칩
3. **작업내용** — 외부 헤더(총 인원·장비) + 협력업체별 테이블

> 페르소나 토글(구성원/관리자)과 무관하게 **모두에게 새 구성으로 교체**. 관리자는 전체 현장 집계가 필요하면 `/dashboard`. `/home`은 구성원의 단일 현장(데모 = M15X Ph-3 IBL) 일일 운영 랜딩이다.

## 3. 범위 / 비범위

**범위(In)**
- `/home` 페이지 전면 교체 (단일 현장 = M15X, 시연 날짜 = 2025-09-25 고정)
- 신규 home 섹션 컴포넌트 3종 (`HomeGreetingHeader` / `HomeProcessingSection` / `HomeWorkSummaryCard`)
- 신규 fixture `data/mock_home.json` + `fixtures.ts` 로더/타입 추가
- 히어로 이미지 정적 자산 `web/public/site-hero-m15x.jpg`
- 작업내용은 기존 `mock_report.json` 의 `details[date].raw_data` 재사용
- **버그fix**: `fixtures.ts` `DATA_DIR` 가 commit e93cc65 의 env 대응에서 누락됐던 것을 정렬 (아래 §6.3)
- **정리**: 구 home 전용 컴포넌트 7종 삭제 (orphaned 확인 — §7)

**비범위(Out)**
- 실제 로그인/사용자-현장 매핑 (PoC 고정값 "김현장")
- 실제 날씨 API (mock 값)
- 현장 선택/전환 UI (M15X 단일 고정)
- A_Track(파이프라인) 변경 없음. Postgres 실 API swap은 Phase 2 후속 (SSR `loadFixture` → PG 쿼리 자리만 교체).

## 4. 화면 구조

위 → 아래. 레이아웃 리듬은 Dashboard/Reports 와 동일 (`max-w-screen-2xl` 래퍼). 단 **헤더만 컬러 히어로**(브리핑 랜딩 성격), 하단 콘텐츠는 흰 카드로 통일 — "컬러 히어로 + 일관 콘텐츠" 패턴.

```
╔══ [1] 컬러 히어로 밴드 (현장 항공사진 + 블루 그라데이션) ══════════╗
║ 오늘의 현장 브리핑                                  📍 청주          ║
║ M15X Ph-3 IBL  (현장명 prominent)        2025. 09. 25 (목) · ☀ 23° ║
║ 🦺 김현장님, 안녕하세요 — 오늘도 안전 작업 되세요                    ║
╚════════ (하단으로 갈수록 page-bg 로 밝아져 콘텐츠와 이어짐) ════════╝

┌─ 오늘 처리 현황 · 협력업체 일보 단위 ────────────────────────────┐
│ [제출]   [처리완료] [처리중]  [미제출]  [오늘 절감]   ← 공용 KpiStrip│
│ 9/12     7건        2건 ●     3업체     ~18h          5블록 그리드  │
│ ⚠ 미제출 업체 │ [철근 한신산업] [전기 파인텍] [도장 해광]          │
└──────────────────────────────────────────────────────────────────┘

오늘 작업내용 · 처리완료 7건           총 투입 인원 69명 · 투입 장비 6대   ← 외부 헤더
┌──────────────────────────────────────────────────────────────────┐
│ 업체     │ 공종  │ 작업내용                          │ 인원         │
│ A건설    │ 골조  │ FAB 2층 벽체 거푸집 설치 / 우천대응 │ 14명         │
│ …       │ …    │ …                                │ …           │
└──────────────────────────────────────────────────────────────────┘
```

## 5. 섹션별 상세

### 5.1 인삿말 + 현장 헤더 (`HomeGreetingHeader`)

**컬러 히어로 밴드** (s.con 모바일 참고). 다른 화면의 흰 헤더와 달리 home(브리핑 랜딩)만 컬러.

- **배경 (CSS 다중 레이어, 위→아래 스택)**:
  1. 좌측 텍스트 가독성 스크림 — `linear-gradient(90deg, rgba(7,15,38,.64) → 투명 64%)` (좌상단 텍스트만 진하게, 우측 건물·로고 보존)
  2. 블루 오버레이 — `linear-gradient(180deg, 상단 진한 네이비 → 하단 page-bg(#f9fafc) 불투명 1.0)` 완만한 6스톱. **마지막 스톱 불투명도 1.0** 으로 사진이 비치는 경계 띠 제거.
  3. 현장 항공사진 `url(/site-hero-m15x.jpg)`, `background-position: 64% 58%` (SK하이닉스 로고가 보이도록 우측·상향 시프트)
- **좌**: eyebrow "오늘의 현장 브리핑" → **현장명 `{site.name}` (h2, prominent)** → 인삿말 `🦺 {user.name}님, 안녕하세요 — 오늘도 안전 작업 되세요` (amber 액센트)
- **우**: 위치 pill `📍 {site.location}` (청주) · 날짜 `{date}({요일})` · 날씨 `{weatherIcon} {label} {temp}°`
- `user.name`·날씨·위치는 fixture 고정값. 날짜는 SSR/CSR 일치 위해 UTC 기준 포맷.

### 5.2 처리 현황 (`HomeProcessingSection`)

**Dashboard/Reports 와 동일한 공용 `reports/KpiStrip` 재사용** → 화면 간 통일성 확보. 5개 KPI가 각각 독립 카드 블록.

깔때기 모델 (협력업체별 일보 단위):

| 지표 | 값(데모) | KpiStrip tone | 정의 |
|------|---------|---------------|------|
| 제출 | 9 / 12 업체 | normal | 예정 12개 업체 중 일보 제출 9 |
| 처리완료 | 7 건 | primary | 제출분 중 파이프라인 처리완료 |
| 처리중 | 2 건 | caution | 처리 진행 중 |
| 미제출 | 3 업체 | risk (적색) | 아직 일보 미제출 |
| 오늘 절감 | ~18 h | primary | 처리완료 7건 × 수작업 ~2.5h/건 (AS-IS 2~3h/건 → AI 5분). **누적 아닌 "오늘" 절감** |

- 깔때기 정합성: 예정 12 = 제출 9 (완료 7 + 처리중 2) + 미제출 3.
- 섹션 헤더(외부): h5 "오늘 처리 현황" + mono "협력업체 일보 단위".
- **미제출 칩**: KpiStrip 아래 슬림 행(흰 카드, `rose` 톤). 클릭 없이 업체명 노출 — "누구한테 독촉할지" 행동 정보. `[공종 업체명]` 칩. 업체명은 `company_normalize.json` 등록 실명(한신산업·파인텍·해광). 미제출 집합 ≠ 제출(raw_data) 집합이라 양쪽 동시 등장 없음.

### 5.3 작업내용 (`HomeWorkSummaryCard`)

처리현황과 동일하게 **헤더를 블록 밖으로**.

- **외부 헤더**: 좌 `h5 "오늘 작업내용" + mono "처리완료 {n}건"`, 우 `총 투입 인원 {totalWorkers}명 · 투입 장비 {totalEquipment}대` (아이콘 Stat).
  - `totalWorkers` = Σ `raw_data[].workers` = **69** (2025-09-25 데모)
  - `totalEquipment` = fixture 명시값 **6** (equipment 문자열 "타워크레인 1호기/펌프카 2대/토치/-" 등 대수 파싱 불안정 → 중장비 기준 정수)
- **테이블 카드** (reports/RawDataTab 패턴 차용, 검색·CSV 제외): 컬럼 **업체(`bp_name`) · 공종(`trade`, 톤별 배지) · 작업내용(`work_content`) · 인원(`workers`)**. **장비 컬럼 없음** (총 대수만 헤더).
  - 공종 배지 톤: 골조=brand · 마감=sun · 토공사=peach · MEP=sky · 그 외 fallback(muted).
  - 행 = `raw_data` 7행 = 처리완료 7건. 처리중 2건은 내용 미생성이라 미표시 (스트립 "처리완료 7"과 행 수 일치).

## 6. 데이터 설계

### 6.1 신규 fixture `data/mock_home.json`

shape는 실 API와 일치 → Phase 2 swap만으로 전환.

```json
{
  "site": {
    "id": "m15x-ph3-ibl",
    "name": "M15X Ph-3 IBL",
    "location": "청주",
    "date": "2025-09-25",
    "weather": { "icon": "sun", "label": "맑음", "temp_c": 23 }
  },
  "user": { "name": "김현장" },
  "processing": { "expected": 12, "submitted": 9, "completed": 7, "in_progress": 2, "unsubmitted": 3, "hours_saved_today": 18 },
  "unsubmitted_companies": [
    { "trade": "철근", "name": "한신산업" },
    { "trade": "전기", "name": "파인텍" },
    { "trade": "도장", "name": "해광" }
  ],
  "work_summary": { "total_workers": 69, "total_equipment": 6 }
}
```

### 6.2 작업내용 데이터 + 날짜 가드

- `mock_report.json` → `details[home.site.date].raw_data` (7행) 재사용. 추가 데이터 불필요.
- **날짜 fallback 가드**: `details[home.site.date]` 가 없으면 가장 최근 날짜(`Object.keys(details).sort().pop()`) 의 raw_data 로 fallback → 두 fixture 날짜가 어긋나도 라이브 시연 중 테이블이 조용히 비지 않게.

### 6.3 `web/lib/fixtures.ts` (+ DATA_DIR 버그fix)

- `FixtureMap` 에 `home: HomeFixture`, `HomeFixture` 타입은 `web/lib/types.ts`.
- 로딩: home 은 **서버 컴포넌트에서 `loadFixture` 직접(SSR)** — 로딩 플래시 없음, Phase 2 는 이 자리를 PG 쿼리로 swap.
- **DATA_DIR 정렬 (잠복 버그fix)**: 기존 `path.join(cwd, "..", "data")` 가 commit e93cc65(4개 API route 만 `process.env.DATA_DIR ?? cwd/data` 로 수정) 에서 누락돼 있었다. home 이 `loadFixture` 를 서버에서 처음 직접 호출하며 컨테이너(cwd=/app)에서 `/data` ENOENT 노출. `resolveDataDir()` 로 ① `DATA_DIR` env ② `<cwd>/data`(실 fixture `mock_sites.json` 존재 확인) ③ `<cwd>/../data` 순서 해석 — 컨테이너·repo루트·web/ cwd 3종 모두 견딤.

## 7. 컴포넌트 / 파일 변경

| 파일 | 변경 |
|------|------|
| `web/app/(app)/home/page.tsx` | 전면 교체 — 3 섹션 조립, `loadFixture(home/report)` + 날짜 가드 |
| `web/app/components/home/HomeGreetingHeader.tsx` | 신규 — 사진 컬러 히어로 (5.1) |
| `web/app/components/home/HomeProcessingSection.tsx` | 신규 — 공용 KpiStrip 재사용 + 미제출 칩 (5.2) |
| `web/app/components/home/HomeWorkSummaryCard.tsx` | 신규 — 외부 헤더 + 테이블 (5.3) |
| `data/mock_home.json` | 신규 fixture (6.1) |
| `web/public/site-hero-m15x.jpg` | 신규 — 현장 항공사진 (SK하이닉스 M15 청주) |
| `web/lib/fixtures.ts` / `web/lib/types.ts` | `home` 로더 + `HomeFixture` + DATA_DIR fix |
| **삭제** `OpsKpiCard·AgentWorkflow·StatusHeader·NowStrip·Hero·AgentCard·HilReviewStage·HomeProcessingStrip` | 구 home 전용 — orphaned(외부 import 0) 확인 후 제거 |

## 8. 디자인 가이드

- 타입 스케일: `docs/ui/sample/font.png` 단일 출처, `text-h1..h6 / body / btn` 토큰만.
- 콘텐츠 카드/테이블·KPI 는 기존 `reports`/`dashboard` 와 동일 (`rounded-card`, `border-border-soft`, `bg-card`, `shadow-xs`, `font-display`, 공용 `KpiStrip`).
- 히어로 밴드만 예외적 컬러 — 브랜드 네이비/블루 그라데이션 + 현장 사진, white-on-dark. amber 안전/날씨 액센트.

## 9. 수용 기준 (Acceptance)

- [x] `/home` 진입 시 [히어로 · 처리현황 · 미제출 칩 · 작업내용]이 위→아래로 렌더.
- [x] 히어로: 현장 사진 + 현장명 prominent + 인삿말("안전") + 위치(청주)·날짜·날씨, 하단 page-bg 로 자연스럽게 연결.
- [x] 처리현황: 공용 KpiStrip 5블록(제출·처리완료·처리중·미제출·오늘 절감), 깔때기 숫자 정합.
- [x] 미제출 업체명 칩 클릭 없이 노출.
- [x] 작업내용: 외부 헤더(총 인원 69·장비 6) + 업체·공종·작업내용·인원 테이블 (장비 컬럼 없음).
- [x] 구 KPI4 / AgentWorkflow / AgentChatLog 가 `/home`에서 제거, orphaned 컴포넌트 7종 삭제.
- [x] `tsc` clean, 컨테이너(5537) `/home` 200 렌더.
