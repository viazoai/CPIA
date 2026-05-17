# CPIA Frontend 화면 설계 — Design Spec

> **B_Track / 화면 구성 · 정보 구조 · 데이터 의존성 합의안**
> 인터뷰 기반 브레인스토밍의 출력. A_Track 협업·점진 연결 전략 포함.

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-05-16 |
| 트랙 | B_Track (`web/`) |
| 대상 | Frontend 5 화면 + 네비게이션 + 데이터 연결 전략 |
| 참조 입력 | `design/CPIA_기획서_v7.md`, `design/CPIA_기획서_v7.1.html`, `design/CPIA_시연 시나리오 (화면 구성 포함)_v1.md`, `planning/CPIA_PoC_실행계획_v2.md`, `docs/ui/design-system.md` |
| 다음 단계 | spec 사용자 검토 → implementation plan (`writing-plans` 스킬) |

---

## 1. 개요 · 전제

### 1-1. 시연 형식 · 운영 모드

**영상 시연**으로 진행. 라이브 실행이 아닌 사전 촬영된 영상이라:
- 실시간 polling / WebSocket 등 백엔드 연동 불필요
- 모든 데이터는 **PoC 정적 fixture** + **클라이언트 사이드 scripted simulation** (살아있는 인상)
- 모든 변화는 frontend `setInterval` / `setTimeout` + 미리 정의된 시퀀스로 구현

### 1-2. 청중 · 시연 시나리오

청중: **경영진 / 임원 / FLP 리더** (시연 시나리오 문서 §1~§4 외부 슬라이드).
화면 시연 흐름은 시나리오 문서 §5~§6 기준:

```
[외부 슬라이드 1~4]
   §1 현 상황 → §2 문제점 → §3 해결책 (CPIA) → §4 기대효과
        ↓
[화면 시연 §5 — 구성원/현장관리자]
   Home → Agent Tasks → Human Review → Report
        ↓
[화면 시연 §6 — 관리자/Top Mgmt]
   Dashboard 전사 → 현장 드릴다운 (Performance → Impact)
```

### 1-3. 페르소나 · 권한

| 페르소나 | 의미 | 접근 메뉴 |
|---|---|---|
| **구성원** | 현장관리자 (Site PM·엔지니어) | Home / Agent Tasks / Human Review / Report (4) |
| **관리자** | Top Mgmt (Superuser) | 위 4 + **Dashboard** (5) |

- 상단 `구성원 / 관리자` 토글로 페르소나 전환 → 사이드바 메뉴가 변경
- 영상 컷에서 토글 클릭 = 페르소나 전환 시각 신호 (예: Dashboard 항목이 페이드인)

---

## 2. 네비게이션 · 페이지 인벤토리

### 2-1. 구조

```
┌─[Top Bar]─────────────────────────────────────────────────────────────────┐
│  CPIA · 로고                  [구성원 ◐ 관리자] 토글       ●live · v0.1   │
├─[Sidebar]─┬─[Main Content]──────────────────────────────────────────────────┤
│           │                                                                │
│  Home     │                                                                │
│  Agent    │                                                                │
│  Tasks    │            (선택한 메뉴의 화면 렌더링)                          │
│  Human    │                                                                │
│  Review   │                                                                │
│  Report   │                                                                │
│  ─────    │                                                                │
│  Dashboard│  ← 관리자 모드에서만 노출                                       │
│           │                                                                │
└───────────┴────────────────────────────────────────────────────────────────┘
```

### 2-2. 메뉴 5개 (영문 통일)

| 메뉴 | 역할 | 페어 관계 |
|---|---|---|
| **Home** | 시연 진입점 · Agent 시스템 소개 + 현재 운영 인상 | — |
| **Agent Tasks** | Daily Run 큐 · AI Agent가 처리하는 작업 흐름 시각화 | ↔ Human Review (AI ↔ Human) |
| **Human Review** | Mapper 결과 검토 (H-i-L 1, 단순화) | ↔ Agent Tasks |
| **Report** | 일자별 결과 분석 (Forecast / Optimize / Raw Data) | — |
| **Dashboard** | 경영진 모니터링 (Performance / Impact 2 탭, 전사→현장 드릴다운) | 관리자 전용 |

**페어 의도:** Agent Tasks/Human Review는 "Agent가 하는 일 / 사람이 하는 일"을 메뉴명으로 호명하여 CPIA의 핵심 메시지(AI 자동화 + 사람 검토)를 메뉴만 봐도 전달.

### 2-3. 토글 동작

| 모드 | 사이드바 메뉴 | 시각 차이 |
|---|---|---|
| **구성원** | Home · Agent Tasks · Human Review · Report (4) | Dashboard 미노출 |
| **관리자** | + Dashboard (5) | Dashboard 페이드인 |

---

## 3. 화면 정보 구성

각 화면은 다음 5요소로 명시:
1. **목적 / 영상에서의 역할**
2. **레이아웃 텍스트 와이어프레임**
3. **컴포넌트 분해**
4. **데이터 소스 (A_Track / B_Track / 정적)**
5. **시뮬레이션 동작**

화면별 구현 시 `docs/ui/design-system.md`의 토큰·컴포넌트·STATUS 매핑 준수.

---

### 3-1. Home

#### 목적
- 영상 첫 컷 — 시청자가 "CPIA가 무엇이다"를 한 화면에서 파악
- 정적인 소개 + 살아있는 인상 ("지금도 시스템이 일하고 있다")

#### 레이아웃

```
┌────────────────────────────────────────────────────────────────────────┐
│ ① HERO  (v7.1 발췌)                                                     │
│   ● System Active · Hi-tech Division · 6 Sites · 2026.05               │
│   "현장 공정 데이터 자동화 및 공기 리스크 선행 탐지 Agent"                │
│   7개 전문 Agent + Vector RAG 기반 현장 실적 이력 판단 체계               │
│   ┌────────────┬────────────┬────────────┬────────────┐                │
│   │ 2,155h/월   │ FTE 15.4명 │ D-14 선행  │ 3~7일 단축 │                │
│   │ 절감        │ 대체 규모  │ 탐지       │ 공기       │                │
│   └────────────┴────────────┴────────────┴────────────┘                │
│                                                                        │
│ ② NOW · 현재 운영 현황 (live strip)                                     │
│   [오늘 처리 87건] [Review 대기 2건] [이상 1건] [09:12 갱신]             │
│                                                                        │
│ ③ 7-Agent 파이프라인 + HIL Review                                       │
│   ┌────────────┬────────────┬────────────┬────────────┐               │
│   │ STEP 01    │ STEP 02    │ STEP 03    │ STEP 04    │ ← 수집 (sky)  │
│   │ Collector  │ Parser     │ Mapper     │ Atomizer   │               │
│   │ 작업일보   │ 비정형     │ WBS Work   │ Vector DB  │               │
│   │ 자동 수집  │ 텍스트 →   │ Package에  │ 임베딩     │               │
│   │            │ 구조화JSON │ 의미기반   │ 적재       │               │
│   │            │            │ 매핑       │            │               │
│   │ 규칙 기반  │ Sonnet 4.6 │ Sonnet 4.6 │ 임베딩 모델│               │
│   │ ●3 처리중  │ ●2 대기    │ ●1 대기    │ idle       │ ← 시뮬 status │
│   └────────────┴────────────┴────────────┴────────────┘               │
│            ↓                                                           │
│   ┌──────────────────────────────────────┐                            │
│   │ ⏸ HIL Review (사람 개입)             │ ← 단순화 1단계 (peach)      │
│   │ 확신도 낮은 매핑 항목을 담당자가 검토│                            │
│   │ 후 확정 — Human Review 화면으로 전환 │                            │
│   └──────────────────────────────────────┘                            │
│            ↓                                                           │
│   ┌────────────┬────────────┬────────────┐                            │
│   │ STEP 05    │ STEP 06    │ STEP 07    │ ← 진단·최적화 (lavender)   │
│   │ Reporter   │ Forecaster │ Optimizer  │                            │
│   │ Daily 보고 │ 과거 이력  │ Vector RAG │                            │
│   │ 자동 생성· │ 대비 생산  │ 기반 만회  │                            │
│   │ 발송       │ 성 진단    │ 시나리오·  │                            │
│   │            │ 이상 원인  │ 권고       │                            │
│   │ Sonnet 4.6 │ Opus 4.7   │ Opus 4.7   │                            │
│   └────────────┴────────────┴────────────┘                            │
│                                                                        │
│ ④ CTA — "Agent Tasks 로 들어가기" 큰 버튼                               │
└────────────────────────────────────────────────────────────────────────┘
```

#### 컴포넌트

| 영역 | 컴포넌트 | 참조 |
|---|---|---|
| ① Hero | `<HeroPill>` `<HeroTitle>` `<HeroStat>×4` | v7.1 `#hero` section |
| ② NOW strip | `<NowStrip>` (4 칸, 시뮬 카운터) | 신규 |
| ③ Agent 카드 | `<AgentCard>×7` (sky/lavender 그룹 분리) | v7.1 `#pipeline` section |
| ④ CTA | `<Button variant="default">` (shadcn) | design-system.md §3-1 |

#### 데이터 소스

| 항목 | 출처 | 의존도 |
|---|---|---|
| Hero stats (2,155h / 15.4명 / D-14 / 3~7일) | 정적 (v7.1 박힌 값) | 정적 |
| NOW strip ("오늘 87건" 등) | mock fixture | B 자체 |
| 7-Agent 카드 status 변동 | scripted simulation | B 자체 |

#### 시뮬레이션
- pill `live` dot — 항상 CSS 점멸
- NOW strip "오늘 87건" — 5초마다 ±1 변동, "09:12 갱신" 시간 1분마다 +1초
- Agent 카드 status — 8초 주기로 각 카드의 "처리 N건" 변동, 활성 카드는 살짝 펄스

---

### 3-2. Agent Tasks

#### 목적
- AI Agent가 매일 100여건의 작업일보를 어떻게 처리하는지 운영자 관점에서 시각화
- "Agent가 사람처럼 일하고 보고한다" 메시지를 chat log로 전달
- 시연 시 핵심 메시지: *"AI Agent들이 실제로 어떻게 협력하는지 보세요"*

#### 레이아웃 (3-column)

```
┌────────────────┬──────────────────────┬────────────────────────────┐
│ ① Daily List   │ ② Process별 진행      │ ③ Agent 대화형 Chat Log    │
│ + bar chart    │ (선택한 daily run)   │ (시간순, 자동 스크롤)       │
│                │                       │                            │
│ ▶ 2026-05-15  │ Collector  ████ 87/87 │ ┌─[09:00 · Collector]──┐ │
│   87건 ■■■■  │ Parser     ████ 87/87 │ │ 87건 작업일보 수집…   │ │
│   2026-05-14  │ Mapper     ████ 87/87 │ └────────────────────────┘ │
│   95건 ■■■■■ │ HIL Review ███▒ 12/12⏸│ ┌─[09:00 · Parser]─────┐ │
│   2026-05-13  │ Atomizer   ████ 87/87 │ │ JSON 변환 완료…       │ │
│   82건 ■■■■  │ Reporter   ████  1/1  │ └────────────────────────┘ │
│   ...          │ Forecaster ████  1/1  │ ┌─[09:01 · Mapper]─────┐ │
│                │ Optimizer  ████  1/1  │ │ 87건 매핑 완료, 12건…│ │
│                │                       │ │ 12건 확신도 낮음 ⏸    │   │
│                │                       │ └────────────────────────┘   │
│                │                       │ ...                         │
└────────────────┴──────────────────────┴────────────────────────────┘
```

#### 컴포넌트

| 영역 | 컴포넌트 | 비고 |
|---|---|---|
| ① Daily List | `<DailyRunList>` (각 row: 날짜·처리 건수·미니 bar·상태 뱃지) | 신규 |
| ② Process Progress | `<AgentProgressList>` (7행, 가로 progress bar) | 신규 |
| ③ Chat Log | `<AgentChatLog>` + `<ChatMessage>` | 신규 |

#### 데이터 소스

| 항목 | 출처 | 의존도 |
|---|---|---|
| Daily run 목록 | `pipeline_runs` 테이블 | **A_Track** |
| Process별 진행 (87/87) | `pipeline_runs.node_status` JSON | **A_Track** |
| Chat log 메시지 | A_Track Agent 실행 로그 (정상화) | **A_Track** |
| 화면 fallback (PoC) | `data/mock_agent_tasks.json` | B 자체 |

#### 처리 단위 (Agent별 다름)

| Agent | 처리 단위 | 표기 |
|---|---|---|
| Collector / Parser / Mapper | **작업일보 건 단위** | `N건/87건` |
| HIL Review | **검토 항목 단위** | `12건/12건` (검토 대상 카드 수) |
| Atomizer | **작업일보 건 단위** | `N건/87건` |
| **Reporter / Forecaster / Optimizer** | **Daily run 단위 (1회만 실행)** | `1/1` |

이유: Reporter는 87건을 합산해 1개 통합 일일 보고서를 생성, Forecaster는 1개 진단을 산출, Optimizer는 1개 조언 세트를 생성. 따라서 1 daily run 당 1번 실행.

#### Chat log 톤 (확정 — 하이브리드)

헤더는 기계적(시간 · Agent 이름), 본문은 자연어:

```
[09:01 · Mapper]
87건 매핑 완료. 12건은 확신도가 낮아 직접 확인이 필요해 보입니다.
특히 '방수 시트 정리작업'은 두 공종에 걸쳐 있어요.
→ Human Review 요청 ⏸
```

A_Track Agent가 출력해야 할 데이터 구조 (B_Track이 받는 것):
```json
{
  "run_id": "2026-05-15",
  "events": [
    { "ts": "09:00:12", "agent": "Collector", "type": "info",
      "summary": "87건 작업일보 수집", "detail": "Excel 75건 · 텍스트 12건" },
    { "ts": "09:01:18", "agent": "Mapper", "type": "hil_request",
      "summary": "87건 매핑 완료. 12건 확신도 낮음",
      "detail": "특히 '방수 시트 정리작업'은 두 공종에 걸쳐 있어요." }
  ]
}
```

#### 시뮬레이션
- 우측 chat log — 1~2초 간격으로 새 메시지 페이드인 push, 자동 스크롤
- 중앙 progress bar — Mapper 75/87 → 76/87 → 78/87 점진
- 좌측 list — 오늘 row 처리 건수 ±1 변동, 미니 bar 길이 변화

---

### 3-3. Human Review

#### 목적
- Mapper의 매핑 결과 중 확신도가 낮은 항목을 사람이 검토·확정
- 시나리오 문서 §5-3 핵심: 단순화된 **1단계** H-i-L, WBS 트리 좌측 + 검토 카드 우측, 검색 입력 + 트리 드래그앤드롭 두 가지 수정 UX 지원

#### 레이아웃

```
┌─────────────────────────┬──────────────────────────────────────────────┐
│ ① WBS 트리              │ ② 작업 물량 Mapping (우측)                    │
│   건물 > 공종 > WP 3단   │                                              │
│                         │ [✓ 신규 확정 필요만]  ▢ 전체     12 / 87    │
│ [필터 검색]              │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ ▼ M15X Ph-3 IBL         │ ┌──────────────────────────────────────────┐ │
│  ▼ 토공사 ⚠2            │ │ ⚠ 미확정  A건설           320㎡           │ │
│   ⚠ WP-1-1 터파기 ⚠1   │ │ "FAB 2층 벽체 거푸집 / 우천 대응"          │ │
│  ▼ 골조 ⚠5              │ │ 매핑: M15X > 골조 > WP-3-2 거푸집  87%   │ │
│   ⚠ WP-3-2 거푸집 ⚠3   │ │ ┌─ 수정: [   철근 검색...    🔍] ──┐    │ │
│   ⚠ WP-3-3 철근 ⚠2     │ │ │   (또는 카드를 트리로 드래그)      │   │ │
│   ✓ WP-3-4 콘크리트     │ │ └────────────────────────────────────┘   │ │
│  ▶ 마감 ⚠5              │ │                       [✓ 확정] [✎ 수정] │ │
│                         │ └──────────────────────────────────────────┘ │
│                         │ ┌──────────────────────────────────────────┐ │
│                         │ │ ✓ 확정    B건설           18 t            │ │
│                         │ │ "FAB 2층 철근 조립"                       │ │
│                         │ │ 매핑: M15X > 골조 > WP-3-3 철근  92%     │ │
│                         │ │                              [✎ 수정만]  │ │
│                         │ └──────────────────────────────────────────┘ │
│                         │ ┌─ (그 외 카드들) ...                          │
│                         │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                         │     [모두 AI 추천대로 확정 (확신도 ≥0.8만)]  │
└─────────────────────────┴──────────────────────────────────────────────┘
```

#### 컴포넌트

| 영역 | 컴포넌트 | 비고 |
|---|---|---|
| ① WBS 트리 | `<WBSTree>` (3단 트리, 노드별 검토 건수 뱃지) | 신규 |
| ② 카드 list | `<ReviewCard>×N` (BP명·작업내용·물량·매핑·액션) | 신규. 상태별 액션 분리 — **미확정**=`[✓ 확정][✎ 수정]` / **확정**=`[✎ 수정]`만 |
| ② 검색 입력 | `<WPSearchCombobox>` (autocomplete) | 신규 |
| ② 드래그앤드롭 | `<DraggableCard>` + `<DroppableTreeNode>` | dnd-kit 또는 native |
| 상단 토글 | `<Switch>` (신규 확정 필요만 ↔ 전체) | shadcn `<Switch>` add 필요 |
| 일괄 확정 버튼 | `<Button variant="default">` | shadcn |

#### 데이터 소스

| 항목 | 출처 | 의존도 |
|---|---|---|
| WBS 트리 구조 (건물>공종>WP) | `wbs_master` (ChromaDB 189건) + 트리 변환 | **A_Track** (이미 구축됨) |
| 검토 대상 매핑 항목 | Mapper 출력 (`mapping_results.requires_review=true`) | **A_Track** |
| 작업내용 원문 (work_content) | Parser 출력 | **A_Track** |
| 확정 액션 저장 | `mapping_corrections` 테이블 INSERT | **A_Track** (스키마 합의됨) |
| 화면 fallback (PoC) | `data/mock_review_cards.json` | B 자체 |

#### 시뮬레이션
- **시뮬레이션 없음** — 사람 입력 중심 화면이라 안정감 우선
- 단, 카드 확정/수정 후 부드러운 transition (페이드아웃 + 다음 카드 이동)

---

### 3-4. Report

#### 목적
- 시나리오 문서 §5-4: Impact 높고 Productivity 저하 영역의 WP 진단 + Optimizer 결과 (진단 / 유사 사례 / 권고 / 상세)
- H-i-L 2 폐기, **4분면 중 좌상단 위험군 자동 선택**으로 대체
- 정보가 많아 **3 탭(Forecast / Optimize / Raw Data)** 분리

#### 레이아웃

```
┌──────────────────┬─────────────────────────────────────────────────────┐
│ 좌측 (Daily 목록) │ 우측 (선택 일자의 Report)                            │
│                  │                                                     │
│ [필터 ▼]         │ ━━ KPI strip (흐름형 4지표) ━━━━━━━━━━━━━━━━━━━━━ │
│                  │ [현재 생산성 88%][현 추세 D+14][회복 가능 +9%p]      │
│ ▶ 2026-05-15 ⚠  │ [최적화 후 -9일]                                    │
│   2026-05-14 ✓  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│   2026-05-13 ✓  │ [▣ Forecast]   Optimize    Raw Data                │
│   2026-05-12 ⚠  │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│   ...            │                                                     │
│                  │ ┌── Forecast 탭 ──────────────────────────────────┐ │
│                  │ │ S-curve (계획 vs 실적)                          │ │
│                  │ │ ── 상단 요약: [공정률 38.5%][SPI 0.89][잔여 65.8%]│ │
│                  │ │ ────────────────────────────────────────────── │ │
│                  │ │  업체별 막대 (생산성)  │  공종별 막대 (생산성)   │ │
│                  │ └──────────────────────────────────────────────────┘ │
│                  │                                                     │
│                  │ ┌── Optimize 탭 ──────────────────────────────────┐ │
│                  │ │                       │ [위험 12][경고 8][안전 67]│
│                  │ │                       │  (분면 카운트 — 클릭 시   │
│                  │ │                       │   해당 분면만 필터)        │
│                  │ │ 4분면 산점도 (좌 1/2) │ ━━━━━━━━━━━━━━━━━━━━━━━│
│                  │ │ X: Productivity       │ Optimizer 4요소 (자동 선택 │
│                  │ │ Y: Impact             │ 된 위험 WP 기준)         │
│                  │ │ 진입 시 좌상단        │   - 진단                  │
│                  │ │ 위험군 자동 선택      │   - 유사 과거 사례 (3건)  │
│                  │ │                       │   - 권고사항               │
│                  │ │                       │   - 상세 현황              │
│                  │ └──────────────────────────────────────────────────┘ │
│                  │                                                     │
│                  │ ┌── Raw Data 탭 ──────────────────────────────────┐ │
│                  │ │ 매핑 결과 기준 전체 작업일보 테이블               │ │
│                  │ │ 컬럼 순서:                                       │ │
│                  │ │  ① 건물 > ② 공종 > ③ Work Package                │ │
│                  │ │  ④ BP사 > ⑤ 작업내용 > ⑥ 물량 > ⑦ 인원 > ⑧ 장비  │ │
│                  │ │ (정확한 컬럼은 Parser/Mapper 산출물 확인 후 확정)│ │
│                  │ │ 기능: 검색·필터·정렬·CSV 내보내기                 │ │
│                  │ └──────────────────────────────────────────────────┘ │
└──────────────────┴─────────────────────────────────────────────────────┘
```

#### 컴포넌트

| 영역 | 컴포넌트 | 비고 |
|---|---|---|
| 좌 Daily 목록 | `<ReportDailyList>` | 신규 |
| KPI strip | `<KpiStrip>` (Kpi 4개, design-system §5-8 패턴) | 기존 `<Kpi>` 재사용 |
| 탭 | shadcn `<Tabs>` | add 필요 |
| Forecast: S-curve | `<SCurveChart>` (recharts) | 신규 |
| Forecast: 업체/공종 막대 | `<BarChart>` (recharts) | 신규 |
| Optimize: 4분면 산점도 | `<QuadrantScatter>` (recharts ScatterChart) | 신규 |
| Optimize: 분면 카운트 KPI | `<QuadrantCountKpi>` (위험·경고·안전 3 chip, 클릭 시 분면 필터) | 신규 |
| Optimize: 4요소 카드 | `<OptimizerResult>` (진단·사례·권고·상세) | 신규 |
| Raw Data 테이블 | `<DataTable>` (검색·필터·정렬, TanStack Table) | 신규 — 컬럼: 건물·공종·WP·BP사·작업내용·물량·인원·장비 |

#### 데이터 소스

| 항목 | 출처 | 의존도 |
|---|---|---|
| Daily 목록 | `daily_reports` 테이블 | **A_Track** |
| KPI strip 4지표 | `forecasts` + `optimizer_advice` 테이블 | **A_Track** |
| Forecast S-curve | `daily_reports` 시계열 (계획·실적 누적) | **A_Track** |
| Forecast 업체/공종 막대 | Parser/Atomizer 출력 집계 | **A_Track** |
| Optimize 4분면 점 | `forecasts` (WP별 Impact·Productivity) | **A_Track** |
| Optimize Optimizer 결과 | `optimizer_advice` 테이블 | **A_Track** |
| Raw Data 테이블 | Parser 출력 (작업일보 87건 정상화) | **A_Track** |
| 화면 fallback (PoC) | `data/mock_report.json` | B 자체 |

#### KPI strip 흐름 (확정)

```
[현재 생산성]   [현 추세 공기]    [회복 가능 생산성]   [최적화 후 공기]
   88%          D+14일 지연        +9%p              -9일 회복
   (이력 -12%)  2026-08-12        (97% 도달)         2026-08-03
```

영상 narration: *"오늘 생산성 88% → 이대로면 14일 지연 → AI 만회 시나리오 9%p 회복 → 9일 단축"*

#### Optimize 탭 — 4분면 + 자동 선택

| 분면 | 의미 | 처리 |
|---|---|---|
| 좌상 (고 Impact · 저 Productivity) | **고위험군** | **화면 진입 시 자동 선택 점이 강조됨**, 우측 Optimizer 결과 즉시 노출 |
| 우상 (고 Impact · 정상) | 모니터링 | 선택 시 진단 |
| 좌하 (저 Impact · 저 Productivity) | 추후 검토 | 선택 시 진단 |
| 우하 (저 Impact · 정상) | 안전 | 회색 표시 |

각 점 = 1 Work Package. 점 크기 = 잔여 물량, 색 = STATUS 매핑.

#### 시뮬레이션
- Optimize 탭 진입 시 좌상단 위험군 점이 0.5초 뒤 자동 선택되며 우측 Optimizer 카드 페이드인 ("AI가 자동으로 위험을 골랐다" 시각 효과)
- Forecast 탭 S-curve의 마지막 점이 미세하게 갱신 (데이터 흐름 인상)

---

### 3-5. Dashboard

#### 목적
- 관리자(Top Mgmt) 전용 모니터링
- 영상 클라이맥스 — *"이렇게 만들어진 데이터를 경영진은 이렇게 본다"*
- 2 탭 분리: **Performance**(현장 생산성·공기) ↔ **Impact**(Agent ROI·FTE)
- 디폴트 전사 → 현장 카드 클릭 → 현장 드릴다운 (URL: `/dashboard` → `/dashboard/sites/[id]`)

#### 3-5-A. Performance 탭 · 전사 레벨

```
┌────────────────────────────────────────────────────────────────────┐
│ [▣ Performance]   Impact                                            │
│ ━━ KPI strip (전사 평균) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ [전사 평균 생산성]  [평균 공기 격차]  [이상 공종 총합]  [회복 가능 공기]│
│  86% (-14%)        +9일 평균 지연    8건                -6일 평균   │
│                                                                    │
│ ━━ 6 현장 카드 그리드 (3×2) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ ┌─────────────┬─────────────┬─────────────┐                       │
│ │ M15X Ph-3 ⚠ │ Y-1 OBL     │ Indiana     │                       │
│ │ 생산성 88%  │ 생산성 92%  │ 생산성 95%  │                       │
│ │ 공기 +14d   │ 공기 +2d    │ 공기 -1d    │                       │
│ │ ▁▂▁▂▃▄▅    │ ▁▂▃▃▄▄▅    │ ▂▃▄▄▄▅▅    │  ← 미니 S-curve     │
│ │ 이상 1건    │ 정상         │ 정상         │                       │
│ └─────────────┴─────────────┴─────────────┘                       │
│ ┌─ (3 more) ─────────────────────────────────────────────────┐    │
└────────────────────────────────────────────────────────────────────┘
```

#### 3-5-B. Performance 탭 · 현장 레벨 (드릴다운)

```
┌────────────────────────────────────────────────────────────────────┐
│ ← 전사로  │  M15X Ph-3 IBL                  [▣ Performance] Impact  │
│ ━━ KPI strip (Report와 동일 4지표) ━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ [현재 생산성 88%][현 추세 +14일][회복 가능 +9%p][최적화 후 -9일]    │
│                                                                    │
│ ━━ S-curve Hero (4선 시나리오) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│   100% ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄                            │
│        계획선  ─────────                                            │
│        실적선  ────● (오늘)                                         │
│        예측선  ── (이대로면 D+14 지연)                               │
│        만회선  ━━ (만회 시나리오 적용 시 D+5)  ← 점선·dimmed         │
│                                                                    │
│ ━━ 업체별·공종별 막대 (2 column) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ ┌──────────────────────────┬──────────────────────────┐           │
│ │ 업체별 생산성 (이력 평균)  │ 공종별 생산성 (이력 평균) │           │
│ │ A건설   ███████  92%     │ 거푸집  █████    68%     │           │
│ │ ...                       │ 철근    ███      54%⚠   │           │
│ └──────────────────────────┴──────────────────────────┘           │
└────────────────────────────────────────────────────────────────────┘
```

#### 3-5-C. Impact 탭 · 전사 레벨

```
┌────────────────────────────────────────────────────────────────────┐
│ Performance | [▣ Impact]                                            │
│ ━━ KPI strip (전체 근무량 기준 흐름) ━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ [전체 근무량]            [월 절감 시간]  [FTE 환산]  [AI 업무 대체율]│
│  480명 · 67,200 h/월     2,155 h        15.4명       3.2%          │
│                                                                    │
│ ★ 연간 환산 효과: 충원 비용 절감 약 203억 (15.4명 × 1.5억 + 직접) │
│                                                                    │
│ ━━ 현장별 절감 분포 (수평 막대) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ Y-1 Ph-1 OBL    ████████████████████ 832h │ FTE 5.9               │
│ Indiana Fab HAC ████████████ 353h          │ FTE 2.5               │
│ ... (6 sites total)                                                │
│                                                                    │
│ ━━ 월별 누적 FTE 환산 추세 (선그래프) ━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  도입 0개월 → 1개월 → 2개월 → 3개월 ──> 현재 15.4명                 │
└────────────────────────────────────────────────────────────────────┘
```

#### 3-5-D. Impact 탭 · 현장 레벨

```
┌────────────────────────────────────────────────────────────────────┐
│ ← 전사로  │  M15X Ph-3 IBL          Performance | [▣ Impact]      │
│ ━━ KPI strip (이 현장 ROI · 전체 근무량 기준 흐름) ━━━━━━━━━━━━━ │
│ [현장 근무량]         [월 절감 시간]  [FTE 환산]  [AI 업무 대체율] │
│  65명 · 9,100 h/월    221 h          1.6명        2.4%            │
│                                                                    │
│ ━━ Middle Office 4기능별 자동화율 (수평 막대) ━━━━━━━━━━━━━━━━━━ │
│ Data Stewardship   ████████ 88% (28h → 3.4h)                      │
│ P&L Reporting      ████████ 86% (35h → 4.9h)                      │
│ Risk Management    ███████  71% (31h → 9h)                        │
│ Deal Support       ████     47% (17h → 9h)  ⚠ 자동화 여지 큼       │
│                                                                    │
│ ━━ 도입 후 자동화율 추세 (선그래프) ━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│  0% → 35% → 58% → 74% ...                                          │
└────────────────────────────────────────────────────────────────────┘
```

#### 컴포넌트 (Dashboard 공통)

| 영역 | 컴포넌트 | 비고 |
|---|---|---|
| 상단 탭 (Performance ↔ Impact) | shadcn `<Tabs>` | add 필요 |
| KPI strip | `<KpiStrip>` (위치별 다른 4지표) | 기존 `<Kpi>` 재사용 |
| 6 현장 카드 | `<SiteCard>` 확장형 (미니 S-curve 포함) | 기존 컴포넌트 확장 |
| 4선 S-curve | `<SCurveChart>` (Report와 공유, prop으로 만회선 표시) | 신규 |
| 수평 막대 | `<HorizontalBarList>` | 신규 |
| 추세 선그래프 | `<TrendLineChart>` (recharts LineChart) | 신규 |

#### 데이터 소스 (Dashboard 전체)

| 항목 | 출처 | 의존도 |
|---|---|---|
| 6 현장 카드 데이터 | `sites` 테이블 + 시계열 집계 | A_Track (1 현장) + B_Track mock (5 현장) |
| 현장 KPI strip (Performance) | Report와 동일 (`forecasts`, `optimizer_advice`) | **A_Track** |
| 4선 S-curve | `daily_reports` + Forecaster 예측 + Optimizer 만회 시나리오 | **A_Track** |
| 업체별·공종별 막대 | Parser/Atomizer 누적 | **A_Track** |
| Impact KPI strip | 집계 fixture (절감 시간·FTE·비용·가용률) | **B_Track 자체 (PoC fixture)** |
| Middle Office 4기능 자동화율 | 정량 fixture (기획서 v7 §03 참조) | **B_Track 자체 (PoC fixture)** |
| 화면 fallback (PoC) | `data/mock_dashboard.json` | B 자체 |

> **Impact 탭의 모든 데이터는 PoC fixture로 박는다.** 실제 측정에는 HR 데이터·실 운영 데이터가 필요하지만 PoC 영상 시연 단계에서는 fixture만으로 충분.

#### 시뮬레이션
- KPI strip 숫자 미세 변동 (예: 2,155 → 2,156 → 2,155)
- 현장 카드 미니 S-curve 마지막 포인트 미세 갱신
- 4선 S-curve의 "실적선" 끝점이 1분에 한 번 미세 갱신
- 4분면 산점도 점들 미세하게 움찔거림 (살아있는 인상)

---

## 4. 데이터 의존성 매트릭스 (A_Track ↔ B_Track)

### 4-1. 의존도 분류

| 분류 | 의미 | 비율 |
|---|---|---|
| 🟢 **B 자체** | B_Track 자체 fixture로 즉시 가능 | ~25% |
| 🟡 **A 의존 (필수)** | A_Track 산출물 없으면 시연 불가 | ~60% |
| 🔵 **A 의존 (보강)** | A_Track 산출물 있으면 더 강하지만 fixture로 대체 가능 | ~15% |

### 4-2. 화면별 의존성 표

| 화면 | 컴포넌트 | 분류 | 데이터 정의 위치 |
|---|---|---|---|
| Home | Hero stats (정적 박힘) | 🟢 | v7.1 html 발췌 |
| Home | NOW strip | 🔵 | `mock_sites_summary.json` |
| Home | 7-Agent 카드 status | 🔵 | `mock_agent_status.json` |
| Agent Tasks | Daily run 목록 | 🟡 | `pipeline_runs` 테이블 (A) |
| Agent Tasks | Process progress | 🟡 | `pipeline_runs.node_status` (A) |
| Agent Tasks | Chat log | 🟡 | A_Track 이벤트 정상화 |
| Human Review | WBS 트리 | 🟡 | `wbs_master` (A — 이미 구축) |
| Human Review | 검토 카드 | 🟡 | Mapper 출력 (A) |
| Human Review | 확정/수정 저장 | 🟡 | `mapping_corrections` (A 스키마 합의됨) |
| Report | Daily 목록 | 🟡 | `daily_reports` (A) |
| Report | KPI strip | 🟡 | `forecasts` + `optimizer_advice` (A) |
| Report | Forecast 탭 차트 | 🟡 | A 시계열 집계 |
| Report | Optimize 탭 4분면 | 🟡 | `forecasts.wp_quadrant` (A) |
| Report | Optimize Optimizer 결과 | 🟡 | `optimizer_advice` (A) |
| Report | Raw Data | 🟡 | Parser 출력 (A) |
| Dashboard | 6 현장 카드 | 🟡+🟢 | A(1) + B mock(5) |
| Dashboard Performance 차트 | S-curve · 막대 | 🟡 | A 시계열 |
| Dashboard Impact 모든 데이터 | KPI · 분포 · 추세 | 🟢 | **B 자체 fixture (HR 측정 불가)** |

---

## 5. 점진 연결 전략

### 5-1. 3 Phase 모델

```
[Phase 1] B 단독 mock         [Phase 2] 점진 연결          [Phase 3] 시연 snapshot 고정
   ▔▔▔▔▔▔▔▔▔▔▔▔▔             ▔▔▔▔▔▔▔▔▔▔▔▔▔               ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔
   - 모든 화면 mock fixture     - A_Track GATE 통과 시      - A_Track 최종 산출물
   - A_Track 대기 없이 작업     - 화면별 fetch 레이어를     - B가 snapshot 받아
   - mock = 실 API shape 동일   - fixture → 실 DB 전환      - JSON fixture로 박음
                                                            - 영상 촬영 (안정성)
   B 자체 1주차~2주차         B+A 통합 3주차              시연 1주 전 ~ 촬영
```

### 5-2. Mock fixture 설계 원칙

B_Track이 작성하는 mock fixture는 **A_Track API/스키마와 동일 shape**을 따라야 함. 그래야 Phase 2 전환 시 fetch URL만 바꾸면 transparent swap.

예시:

```ts
// mock fixture (Phase 1)
const dailyRuns = await fetch('/api/mock/runs').then(r => r.json())

// 실 API 전환 (Phase 2) — shape 동일하므로 fetch URL만 변경
const dailyRuns = await fetch('/api/runs').then(r => r.json())
```

API 응답 shape은 **`docs/architecture/api-contract.md`에 정의된 계약**을 따른다. mock fixture는 그 계약을 그대로 mock한 것.

### 5-3. 화면별 작업 시작 가능 시점 (B_Track 입장)

| 화면 | Phase 1 (mock 단독) 가능? | A_Track 의존 시점 |
|---|---|---|
| Home | ✅ 즉시 가능 | (Phase 2에서 NOW strip 일부 실 데이터화 가능, 영상엔 mock으로 충분) |
| Agent Tasks | ✅ 가능 (mock 시퀀스 작성 필요) | Phase 2에서 실 chat log 가능, 영상엔 mock으로 충분 |
| Human Review | ✅ 가능 (mock WBS·검토 카드) | Phase 2에서 실 WBS 트리·Mapper 결과 연결 |
| Report | ✅ 가능 (mock daily/KPI/차트) | Phase 2에서 실 forecasts/optimizer_advice 연결 |
| Dashboard Performance | ✅ 가능 (mock sites·시계열) | Phase 2에서 1 현장 실 데이터, 5 현장 mock 유지 |
| Dashboard Impact | ✅ **Phase 3까지 전부 fixture** (HR 데이터 없음) | A_Track 무관 |

**결론: B_Track은 A_Track 대기 없이 5 화면 모두 작업 가능.** Phase 2 전환은 fetch URL 교체 + API shape 검증 정도.

### 5-4. 시연 snapshot 고정 (Phase 3)

영상 촬영 직전 안정성을 위해:
1. A_Track이 최종 데이터 적재 완료한 시점에 Postgres·Chroma 데이터를 **JSON snapshot으로 추출**
2. B_Track의 `data/snapshot_*.json` 파일로 박음
3. 영상 촬영 중 모든 화면은 snapshot에서 fetch (실 DB 의존성 제거)
4. 영상 안정성·재촬영 가능성 보장

---

## 6. Scripted Simulation 시퀀스

### 6-1. 원칙

- 모든 시뮬레이션은 **클라이언트 사이드** (frontend `setInterval` / `setTimeout`)
- 백엔드 polling / WebSocket 없음
- 시뮬레이션 시퀀스는 페이지별 fixture에 함께 정의
- 새로고침 시 처음부터 재생 (영상 컷마다 일관성)

### 6-2. 페이지별 시뮬레이션 정의

| 페이지 | 변화 요소 | 주기 | 시퀀스 파일 |
|---|---|---|---|
| 공통 (Top Bar) | `live` dot 점멸 | CSS animation 무한 | — |
| Home | NOW strip "오늘 N건" ±1 변동 | 5s | `data/mock_simulation.json` |
| Home | "09:12 갱신" 시간 +1초 | 60s | 동상 |
| Home | 7-Agent 카드 status 변동 | 8s | 동상 |
| Agent Tasks | Daily list 오늘 row 건수 ±1 | 5s | 동상 |
| Agent Tasks | Process progress bar 점진 | 2s | 동상 |
| Agent Tasks | Chat log 새 메시지 push | 1~2s | `data/mock_chat_sequence.json` |
| Human Review | (없음 — 사람 입력 중심) | — | — |
| Report | Forecast S-curve 끝점 갱신 | 60s | 동상 |
| Report | Optimize 4분면 점 미세 움직임 | 10s | 동상 |
| Dashboard | KPI strip 숫자 미세 변동 | 30s | 동상 |
| Dashboard | 현장 카드 mini S-curve 끝점 | 60s | 동상 |

### 6-3. 시뮬레이션 구현 패턴

```tsx
// hooks/useSimulation.ts
export function useSimulation<T>(seed: T, updater: (prev: T) => T, intervalMs: number) {
  const [value, setValue] = useState(seed)
  useEffect(() => {
    const id = setInterval(() => setValue(updater), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return value
}

// 사용 예: Home NOW strip
const todayCount = useSimulation(
  87,
  (prev) => prev + (Math.random() > 0.5 ? 1 : -1),
  5000
)
```

---

## 7. 영상 시연 스토리보드

### 7-1. 전체 흐름 (예상 5~7분)

```
[외부 슬라이드 0~2분]
   §1 현 상황 (Hi-tech 인력 부족, T2Y) → §2 문제점 (Middle Office)
   → §3 해결책 (CPIA 제안) → §4 기대효과 (203억 / 15.4명)

[화면 시연 §5: 구성원 흐름 3~4분]
   ① Home 진입 — pill 점멸 · NOW strip · 7-Agent 카드 (Agent 시스템 소개)
       narration: "7개 AI Agent가 매일 100건의 작업일보를 처리합니다"
   ② Agent Tasks — Daily list에서 오늘 클릭 → 3-column 흐름
       narration: "Mapper가 작업하다가 확신도 낮은 12건에 멈춥니다 → Human Review 요청"
   ③ Human Review — 카드 검토 → 검색 입력 또는 트리 드래그로 수정 → ✓ 확정
       narration: "사람은 AI가 헷갈리는 부분만 빠르게 검토하면 됩니다"
   ④ Report — Forecast 탭 (S-curve) → Optimize 탭 (4분면 자동 선택) → Optimizer 결과
       narration: "AI가 자동으로 위험을 찾고, 과거 사례 기반 권고를 제시합니다"

[화면 시연 §6: 관리자 흐름 1~2분]
   토글 클릭 (구성원 → 관리자) — Dashboard 메뉴 페이드인
   ⑤ Dashboard 전사 (Performance 탭) — 6 현장 카드, 이상 현장 식별
   ⑥ M15X 클릭 → 현장 Performance — 4선 S-curve (만회선 강조)
       narration: "현 추세 14일 지연, 만회 시나리오로 9일 회복"
   ⑦ Impact 탭 전환 — 누적 ROI 강조 (영상 클라이맥스)
       narration: "전체 480명이 67,200시간 근무하는 가운데, AI가 2,155시간을
                   대체했습니다 → FTE 15.4명 → 업무 대체율 3.2% → 연 환산 203억 절감"

[외부 마무리 1분]
   요약 + 다음 단계 (ABI 추진 · 확장)
```

### 7-2. 화면 전환 컷

| 전환 | 시각 효과 |
|---|---|
| Home → Agent Tasks | 사이드바 메뉴 클릭 강조 |
| Agent Tasks → Human Review | Chat log의 ⏸ Review 요청 메시지 강조 → Human Review 메뉴로 이동 |
| Human Review → Report | "12건 검토 완료" 메시지 후 Report 메뉴 |
| Report → Dashboard (토글) | **페르소나 토글 클릭** = 영상의 중요 컷 (페이드 + 사이드바 변경) |
| 전사 Dashboard → 현장 | 6 카드 중 M15X 클릭 → 화면 전환 |
| Performance 탭 → Impact 탭 | 탭 전환 후 KPI strip 숫자 페이드인 (강조) |

---

## 8. 디자인 시스템 적용

### 8-1. 단일 출처

모든 화면은 **`docs/ui/design-system.md` 의 토큰·컴포넌트·STATUS 매핑**을 단일 출처로 따른다. 본 spec은 정보 구성에 집중하고, 시각 디테일(색·여백·폰트)은 design-system 따름.

### 8-2. STATUS 매핑 (불변)

| 의미 | 색 | 사용 위치 |
|---|---|---|
| normal | `mint` | 정상 현장·확정 카드·녹색 막대 |
| caution | `sun` | H-i-L 대기 · 검토 필요 · 노란 막대 |
| risk | `rose` | 이상 현장 · 위험 분면 · 빨간 강조 |
| primary | `lavender` | CTA 버튼·focus ring |
| info | `sky` | 데이터 KPI · 정보 chip |
| event | `peach` | H-i-L 뱃지 · 진단 결과 카드 |

### 8-3. 신규 컴포넌트 등록 필요

본 spec에 등장한 신규 컴포넌트는 design-system.md §3-2 (추가 add) 또는 §3-3 (도메인 컴포넌트)에 등록:

```bash
# shadcn primitive 추가
cd web
npx shadcn@latest add dialog sheet tabs switch sonner
```

| 신규 도메인 컴포넌트 | 위치 |
|---|---|
| `<NowStrip>` | `web/app/components/NowStrip.tsx` |
| `<AgentCard>` | `web/app/components/AgentCard.tsx` |
| `<DailyRunList>` | `web/app/components/DailyRunList.tsx` |
| `<AgentProgressList>` | `web/app/components/AgentProgressList.tsx` |
| `<AgentChatLog>` `<ChatMessage>` | `web/app/components/AgentChatLog.tsx` |
| `<WBSTree>` | `web/app/components/WBSTree.tsx` |
| `<ReviewCard>` | `web/app/components/ReviewCard.tsx` |
| `<WPSearchCombobox>` | `web/app/components/WPSearchCombobox.tsx` |
| `<ReportDailyList>` | `web/app/components/ReportDailyList.tsx` |
| `<KpiStrip>` | `web/app/components/KpiStrip.tsx` |
| `<SCurveChart>` | `web/app/components/charts/SCurveChart.tsx` (recharts) |
| `<BarChartH>` | `web/app/components/charts/BarChartH.tsx` |
| `<QuadrantScatter>` | `web/app/components/charts/QuadrantScatter.tsx` |
| `<OptimizerResult>` | `web/app/components/OptimizerResult.tsx` |
| `<DataTable>` | `web/app/components/DataTable.tsx` (TanStack Table) |
| `<HorizontalBarList>` | `web/app/components/HorizontalBarList.tsx` |
| `<TrendLineChart>` | `web/app/components/charts/TrendLineChart.tsx` |
| `<SiteCard>` 확장 (미니 S-curve) | 기존 컴포넌트 확장 |

신규 토큰·차트 패턴 결정은 design-system.md에 추가 등록.

---

## 9. PoC Fixture 데이터 정의

### 9-1. Fixture 파일 인벤토리

```
data/
├── mock_sites.json                ← 6 현장 메타 (기존)
├── mock_sites_summary.json        ← Home NOW strip + Dashboard 전사 KPI (신규)
├── mock_agent_status.json         ← 7-Agent 카드 status (신규)
├── mock_agent_tasks.json          ← Daily run 목록 + Process progress (신규)
├── mock_chat_sequence.json        ← Agent chat log 시퀀스 (신규)
├── mock_review_cards.json         ← Human Review 검토 카드 (신규)
├── mock_wbs_tree.json             ← WBS 트리 구조 (3단) (신규)
├── mock_report.json               ← Report 일별 KPI/차트 (신규)
├── mock_dashboard.json            ← Dashboard Performance/Impact 데이터 (신규)
└── mock_simulation.json           ← 시뮬레이션 시퀀스 (변화 패턴) (신규)
```

### 9-2. Fixture 작성 원칙

1. **shape이 실 API와 동일** — `docs/architecture/api-contract.md` 기준
2. **수치 일관성** — 한 fixture 세트 안에서 산수 맞물림 (예: 절감 시간 ÷ 140h = FTE)
3. **현실감 있는 텍스트** — work_content, BP사명, 공종명 등은 기획서·시연 시나리오의 실제 표현 활용
4. **시뮬레이션과 정합** — 시뮬 변동치도 fixture의 base 값에서 ±%

### 9-3. Impact 탭 KPI 분모 가정치 (PoC)

KPI 흐름: **전체 근무량 → 절감 시간 → FTE → AI 업무 대체율**.

- **전체 근무량** = `현장 전체 근무 인원 × 인당 월 평균 근무시간(140h 가정)`
- **AI 업무 대체율** = `월 절감 시간 ÷ 전체 근무 시간` (= 추가 인력 가용률과 같은 비율)

PoC 시연용 fixture (실 운영 시 HR 데이터로 갱신):

| 현장 | 근무 인원 (가정) | 전체 근무 h/월 | 절감 시간/월 | 확보 FTE | AI 대체율 |
|---|---:|---:|---:|---:|---:|
| Y-1 Ph-1 OBL | 130명 | 18,200h | 832h | 5.9 | 4.6% |
| Indiana Fab HAC | 60명 | 8,400h | 353h | 2.5 | 4.2% |
| P&T 3 증축 | 50명 | 7,000h | 255h | 1.8 | 3.6% |
| M15X OBL & PT7 | 50명 | 7,000h | 246h | 1.7 | 3.5% |
| Y-1 Ph-1 IBL | 90명 | 12,600h | 248h | 1.8 | 2.0% |
| 청주 M15X IBL | 65명 | 9,100h | 221h | 1.6 | 2.4% |
| **전사 합산** | **약 480명** | **약 67,200h** | **2,155h** | **15.4** | **3.2%** |

연간 환산:
- 충원 비용 절감 = 15.4명 × 1.5억 = **약 23억**
- 직접 시간 환산 = 2,155h × 12개월 × 70,000원 = **약 180억**
- **합계 ≈ 203억** (기획서 v7 §06 그대로)

> 가정치는 `data/mock_dashboard.json`의 `site.headcount` 필드로 박힌다. 실 운영 시 HR 시스템에서 가져올 자리.

---

## 10. 결정 이력

### 10-1. 인터뷰에서 풀린 핵심 결정

| # | 결정 | 사유 |
|---|---|---|
| Q1 | 화면 6→5개로 통합 (Dashboard 안에 전사·현장 드릴다운) | 메뉴 단순화 |
| Q2 | 좌측 사이드바 + 상단 페르소나 토글 | 표준 SaaS UX, 영상에서 토글 컷 임팩트 강 |
| Q3 | 관리자 = superuser (모든 메뉴 노출) | 영상 narrative + 권한 모델 일관 |
| Q4 | Work Process → Agent Tasks ↔ Human Review 페어 | "AI ↔ 사람" 메시지를 메뉴명에 호명 |
| Q5 | Home = Hero(v7.1) + NOW strip + 7-Agent 카드 + CTA | Agent 소개 + 살아있는 인상 |
| Q6 | PoC 정적 + 클라이언트 scripted simulation | 영상 안정성 + 라이브 인상 |
| Q7 | Agent Tasks = 3-column (Daily list / Process progress / Chat) | 시나리오 문서 v2+v4 의도 반영 |
| Q8 | Chat log = 하이브리드 톤 (헤더 기계적 + 본문 자연어) | "사람처럼"의 시나리오 의도 반영 |
| Q9 | Daily Run 단위 작업목록 | 시나리오 문서 "Daily 단위 표기" 그대로 |
| Q10 | Human Review = 좌 WBS 트리 + 우 카드 list (inline) | 검토 1건 = 카드 1개의 명확함 |
| Q11 | 카드 수정 UX = 검색 입력 + 트리 드래그앤드롭 (병행) | 키보드·시각 두 흐름 모두 지원 |
| Q12 | Report 3 탭 (Forecast / Optimize / Raw Data) | 정보 위계 분리 (자동화 통계 / AI 조언 / 원본) |
| Q13 | Report KPI strip = 흐름형 4지표 (생산성·공기·회복·만회) | CPIA 가치(Forecaster+Optimizer)를 한 줄로 |
| Q14 | SPI·공정률은 Forecast 탭 S-curve로 이동 | KPI strip은 productivity·공기 흐름 일관 유지 |
| Q15 | Dashboard 2 탭 (Performance ↔ Impact) | 운영 효과 ↔ 조직 효과 메시지 분리 |
| Q16 | Impact 4번째 KPI = 추가 인력 가용률 (현장 전체 인원 기준) | "재배치 진행률"의 정직한 측정 가능 변형 |
| Q17 | S-curve 4선 (계획·실적·예측·만회) | 만회 시나리오의 시각 임팩트 |
| Q18 | Daily Report 화면 제거 (엑셀 산출물만) | 시연 청중에 엑셀로 충분 |
| Q19 | H-i-L 2단계 → 1단계 (4분면 자동 선택) | 시연 시나리오 §5-4 단순화 |
| Q20 | A_Track 대기 없이 mock으로 시작 → 점진 연결 (3 Phase) | A/B 트랙 병행 작업 |
| Q21 | Home 7-Agent 카드에 단계별 설명 + Mapper 뒤 HIL Review 단계 시각화 | 시청자가 한 화면에서 파이프라인 + 사람 개입 위치까지 파악 |
| Q22 | Agent Tasks Process progress — Reporter·Forecaster·Optimizer는 daily run 단위(1/1) 표기, Mapper 뒤 HIL Review 단계 별도 행 | 87건 합산 후 1번 실행되는 Agent들은 건 단위가 아님 — 정확성 |
| Q23 | Human Review 카드 동작 분리 — 미확정 카드 = [확정][수정] / 확정 카드 = [수정만] | 이미 확정된 항목에 다시 확정 버튼 노출 불필요 |
| Q24 | Report Optimize 탭에 분면 카운트 KPI (위험·경고·안전, 클릭 시 분면 필터) + Raw Data 컬럼 순서 (건물>공종>WP>BP사>작업내용>물량>인원>장비) | 위험 WP 개수 즉시 파악 + 원본 데이터 검증성 강화 |
| Q25 | Dashboard Impact KPI strip을 전체 근무량 기준 흐름으로 재구성 (480명 · 67,200h → 2,155h 절감 → FTE 15.4 → AI 업무 대체율 3.2%) | "총 N명 중 몇 명 분량 대체"라는 정직한 분모 명시로 의사결정 직결성 향상 |

### 10-2. 보류·후속 결정

| 항목 | 보류 이유 | 후속 시점 |
|---|---|---|
| Daily Report 풀스크린 페이지 (Reporter 출력 웹) | 엑셀로 충분, 영상에 불필요 | 사용자가 필요해지면 추가 |
| Performance 탭 14일 히트맵 | 정보 과다, 현 4선 S-curve로 충분 | 필요 시 wireframe v2 |
| 일괄 확정 임계값 (확신도 ≥ 0.X) | 0.8로 가정, 실 운영에서 튜닝 | A_Track 데이터 누적 후 |
| 시뮬레이션 시퀀스 세부값 | fixture 작성 단계에서 결정 | implementation plan |

---

## 11. 다음 단계

1. **사용자 검토** — 본 spec 검토 (placeholder · 모순 · 모호함 확인)
2. **Implementation plan 작성** — `writing-plans` 스킬로 작업 분해
3. **B_Track 구현 시작 — Mock fixture 1순위 작업**
   - §9-1의 10개 fixture JSON 파일을 *그럴듯한 데이터*로 먼저 박는다 (사용자가 빠르게 시각 피드백할 수 있도록)
   - 그 위에 5 화면 골격을 Phase 1 (mock 단독) 모드로 작성
   - 각 화면 wireframe → 실 화면 → 사용자 피드백 → 수정 사이클을 빠르게 회전
4. **A_Track 연결 시점 조율** — A_Track GATE 통과 시점에 fetch 레이어 swap
5. **시연 snapshot 고정** — 촬영 1주 전 데이터 고정 처리

---

## 12. 참조 파일

```
design/
├── CPIA_기획서_v7.md                      ← 본 문서의 메시지 출처
├── CPIA_기획서_v7.1.html                  ← Hero·Pipeline 섹션 발췌 출처
└── CPIA_시연 시나리오 (화면 구성 포함)_v1.md  ← 시연 흐름 / 5 화면 구조의 출처

planning/
└── CPIA_PoC_실행계획_v2.md                ← PoC 범위 정의

docs/
├── ui/design-system.md                    ← 시각 시스템 단일 출처
├── architecture/api-contract.md           ← A↔B API 계약
├── architecture/stack.md                  ← 기술 스택
├── schema/postgres.md                     ← Postgres 테이블 스키마
├── schema/state.md                        ← LangGraph CPIAState 스키마
└── schema/mapping-layer.md                ← Mapper 레이어 (A_Track)
```

---

*작성: 조형준 프로 · B_Track · 2026-05-16*
*입력 인터뷰: superpowers brainstorming skill 기반 / 화면 5개 + 페르소나 + 시뮬레이션 + 데이터 의존성 모두 합의*
