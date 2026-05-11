# CPIA — Construction Progress Intelligence Agent
## 현장 공정 데이터 자동화 및 공기 리스크 선행 탐지 Agent

> **AI Design Project | SK에코플랜트 AI Board | 조형준 프로 | 2026.05**

---

## 핵심 지표 (Executive Summary)

| 지표 | 현재 | 목표 |
|------|------|------|
| Middle Office 월간 업무량 | **2,506h/월** (6개 현장 실측) | → **351h/월** (86% 절감, 2,155h 제거) |
| 보고 리드타임 | D+2~3일 | **D+0 당일** |
| 공기 리스크 탐지 | 지연 발생 후 사후 인지 | **D-14 선행 탐지** |
| 연간 비용 절감 환산 | — | **약 180억 원** + LD 리스크 회피 |
| 현장 공기 단축 | — | **3~7일 / 현장** |

---

## 00 — 핵심 컨셉: Middle Office를 AI Agent로 교체한다

### 건설 현장의 구조적 문제

현장에는 데이터를 만드는 사람과 데이터로 판단하는 사람 사이에,
**데이터를 취합·정리·재작성하는 레이어**가 존재합니다.

```
┌────────────────────────────────────────────────────────────────┐
│  BP / 협력사 (작업일보 생성)                                      │
│       ↓                                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │            MIDDLE OFFICE                                  │  │
│  │  데이터 취합 → 집계 → 검증 → 보고서 작성 → 리스크 모니터링  │  │
│  │                                                           │  │
│  │  ← 지금 현장 엔지니어가 하고 있는 일 ←                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│       ↓                                                        │
│  현장 PM / 경영진 (의사결정)                                      │
└────────────────────────────────────────────────────────────────┘
```

| Layer | 역할 | 건설 현장 예시 | CPIA 관계 |
|-------|------|----------------|-----------|
| **Front Office** | 수익 창출·의사결정 | 발주처 협의, 공정 문제 해결, 리스크 판단·실행 | 인력 집중 영역 (유지) |
| **Middle Office** | 데이터 중계·검증·보고 | 작업일보 취합, 보고서 작성, 공기 모니터링 | **★ CPIA 대체 대상** |
| **Back Office** | 기록·정산·시스템 | 기성 정산, 퇴직공제, ERP 관리 | 현행 유지 (범위 외) |

이 Middle Office는 판단이 아니라 **중계**입니다.
현장 엔지니어의 하루 중 상당 시간이 BP 이메일을 열어 복붙하고, 같은 숫자를 PPT에 옮겨 적는 데 쓰입니다.
그리고 이 구조가 6개 현장에서 완전히 동일하게 반복됩니다.

### CPIA의 답: 구조를 바꾼다

CPIA는 보고서를 빠르게 만드는 도구가 아닙니다.

> **Middle Office 레이어 자체를 AI Agent로 대체하여,**
> **Front Office(PM·엔지니어)가 AI와 직접 일하는 구조로 전환합니다.**

```
❌ 잘못된 프레이밍: "Middle Office를 없앤다"
   → 인력 감축 논란, 조직 저항

✅ 올바른 프레이밍: "Front가 AI Agent와 직접 일하는 구조로 전환한다"
   → Middle Office 인력 = Agent 오케스트레이터로 업스킬링
   → PM은 데이터를 취합하는 사람에서 데이터로 판단하는 사람으로
   → 조직 차원의 AX 실현
```

### Middle Office가 하는 4가지 기능 → CPIA가 대체

| 기능 | 내용 | 현재 월간 시간 |
|------|------|-------------|
| ① Data Stewardship | BP 작업일보 수집·정합성 검증·표준 DB 적재 | 632h |
| ② P&L Reporting | 공정률·생산성 집계, Daily·Weekly·Monthly 보고서 작성 | 800h |
| ③ Risk Management | 공기 지연 모니터링·잔여 물량 분석·Forecast 산출 | 700h |
| ④ Deal Support | 주간회의 자료 가공·CPI/SPI 산출·만회 시나리오 초안 | 374h |
| **합계** | | **2,506h/월 (6개 현장)** |

---

## 01 — 현황 진단: 데이터가 말하는 것

> 아래 수치는 현장 담당자들이 직접 제출한 Activity 원본 데이터(321개, Hi-tech 사업부 전체)에서 추출한 실측값입니다. 기획자의 추정이 아닌, 현장의 목소리입니다.

### Activity 데이터로 실증된 Pain Point

**① 규모:** Hi-tech 사업부 전체 업무의 39.5%가 CPIA 대체 범위

```
Hi-tech 사업부 월간 업무 (8,133h / 321개 Activity)

  CPIA 대체 가능 (Middle Office 레이어)  ████████████████  3,212h  39.5%
  설계·계약·안전·법무 등 나머지 업무     ████████████████████  4,921h  60.5%
```

**② 반복:** 동일 패턴이 6개 현장에서 완전 중복

| 업무 패턴 | Y-1 OBL | Indiana HAC | P&T3 | M15X | Y-1 IBL | 청주 IBL |
|---------|:-------:|:----------:|:----:|:----:|:-------:|:-------:|
| 작업일보 BP 취합 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Weekly 보고서 작성 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 공정률·생산성 산출 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 잔여공기·리스크 예측 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

→ 한 번 해결하면 6배의 효과

**③ 자발성:** 담당자들이 스스로 CPIA 기능을 요청

현장 담당자들이 직접 제출한 AI 수요가 CPIA 설계와 정확히 일치합니다.

| CPIA 기능 | 담당자 자발 제출 Activity (원문) | 현장 수 |
|----------|-------------------------------|--------|
| 작업일보 자동 수집 | "BP별 작업일보 취합 및 Summary 자동 작성" | 6/6 |
| 이상치 감지 | "이상치(Outlier) 감지 및 검출" | 4/6 |
| 공정률 자동 산출 | "일일 실적 기반 생산성 추세 분석" | 6/6 |
| D-14 리스크 탐지 | "공기 미달 리스크 선행 탐지 자동화" | 5/6 |
| 보고서 자동 생성 | "Weekly/Monthly Report 자동 작성" | 6/6 |

CPIA는 기획자가 구상한 것이 아니라, **현장이 원하는 것을 집약**한 것입니다.

### 현장별 Middle Office 업무 현황

| 현장 | 월간 시간 (실측) | 전체 대비 비중 | 대표 Pain |
|------|-------------|------------|---------|
| Y-1 Ph-1 OBL | **967h** | 60.4% | 작업일보 400h + QSR 200h + PSR 160h |
| Indiana Fab HAC | **410h** | 66.8% | CWP Forecast 96h + Risk 50h + 자재예측 70h |
| P&T 3 증축 | **296h** | 59.7% | W/M Report 100h + 작업일보 88h |
| M15X OBL & PT7 | **286h** | 80.1% | Weekly Progress 100h + 공정 계획 60h |
| Y-1 Ph-1 IBL | **288h** | 36.5% | 공정·원가 관리 40h + PJT 현황 60h |
| 청주 M15X IBL | **259h** | 74.2% | 공정률 관리 75h + Daily 취합 50h |
| **합계** | **2,506h/월** | — | FTE **17.9명** 수준 |

---

## 02 — As-is vs To-be

### AS-IS: 현재 (수작업 7단계, 담당자 전일 투입)

```
① BP 이메일·카카오톡 수동 열람    1~2h/일   100개사+ 개별 확인
② 엑셀 복붙·집계 (수작업)         2~3h/일   인원·물량·장비 수기 합산
③ 이상치 발견 시 업체 유선 확인   1h/일     전화·문자 개별 협의
④ 공정표 항목 수작업 매핑         —         Actual → Plan 수기 대조
⑤ PPT·엑셀 보고서 수기 작성       2h/일     S-Curve·공정률 표·시각화
⑥ 발주처 이메일 수동 발송         —         D+2~3일 지연 발송
⑦ PM 경험칙으로 공정 이상 판단    —         주간 회의 후 인지 → 이미 늦음
```

결과: **담당자 1~3명 전일 투입 | 보고 D+2~3일 지연 | 지연 후 만회 불가**

### TO-BE: CPIA 이후 (담당자 역할 전환)

```
① 이메일·카카오톡 자동 수집·파싱      Collector Agent  →  0분
② 이상치 자동 감지 → 담당자 알림      Validator Agent  →  확인 10분
③ Semantic Mapping 자동 분류          Parser Agent     →  0분
④ CPI/SPI 산출 + 보고서 자동 생성     Reporter Agent   →  검토 20분
⑤ D-14 리스크 + 만회 시나리오         Forecaster Agent →  의사결정 집중
───────────────────────────────────────────────────────────────
★ PM: AI 제안 검토 → 발주처 협상 → 현장 조치 (본연의 역할)
```

결과: **검토·승인 30분/일 | D+0 당일 발송 | D-14 선제 대응**

---

## 03 — CPIA Agent 구성 (LangGraph 기반)

### 프레임워크 선택: LangGraph

CPIA는 단순 자동화 스크립트가 아닙니다. 5개 전문 Agent가 순서와 조건에 따라 협력하는 **멀티에이전트 워크플로우**입니다. 이를 위해 **LangGraph**를 채택합니다.

| 비교 항목 | LangChain | **LangGraph** |
|---------|-----------|--------------|
| 구조 | 순차 체인 (A → B → C) | **그래프 State Machine** |
| 멀티에이전트 | 단일 에이전트 권장 | **다수 에이전트 조율 내장** |
| 조건 분기 | 수동 구현 필요 | **Conditional Edge 기본 지원** |
| Human-in-the-Loop | 별도 구현 | **interrupt 체크포인트 내장** |
| 상태 관리 | 없음 | **CPIAState 공유 — 노드 간 데이터 자동 전달** |
| 중단·재개 | 불가 | **Checkpointer로 파이프라인 재개** |
| 병렬 실행 | 불가 | **Send() API로 Reporter·Forecaster 동시 실행** |

> CPIA에서 LangGraph가 결정적인 이유: **담당자 "20분 검토" 단계**가 파이프라인 중간에 존재합니다. LangGraph의 `interrupt_before`는 이 Human-in-the-Loop 지점을 코드 한 줄로 구현하고, 승인 후 중단 지점부터 재개합니다.

---

### 전체 LangGraph 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CPIA LangGraph State Machine                         │
│                                                                         │
│   CPIAState                                                             │
│   { date, raw_reports, structured_data, anomalies,                      │
│     human_approved, daily_report, forecast, alerts }                    │
│                                                                         │
│   START                                                                 │
│     │                                                                   │
│     ▼                                                                   │
│  ┌──────────┐                                                           │
│  │Collector │  이메일·카카오톡 자동 수신, 원시 파일 저장                    │
│  └────┬─────┘                                                           │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────┐                                                           │
│  │  Parser  │  비정형 텍스트 → WBS 구조화 JSON  (Claude Sonnet 4.6)      │
│  └────┬─────┘                                                           │
│       │                                                                 │
│       ▼                                                                 │
│  ┌───────────┐                                                          │
│  │ Validator │  이상치 감지 (규칙·통계 기반), 정합성 검증                  │
│  └────┬──────┘                                                          │
│       │                                                                 │
│       ▼  [Conditional Edge]                                             │
│   이상치 있음? ──YES──→ ┌──────────────┐ ◀─── interrupt_before          │
│       │                │ human_review │  담당자 10분 확인 후 승인         │
│       NO               └──────┬───────┘                                │
│       │                       │                                         │
│       └───────────────────────┤                                         │
│                               ▼                                         │
│                         ┌──────────┐  ┌────────────┐                   │
│                         │ Reporter │  │ Forecaster │  ← 병렬 실행        │
│                         │ (Sonnet) │  │  (Opus)    │                   │
│                         └────┬─────┘  └─────┬──────┘                   │
│                              │              │                           │
│                    D+0 보고 발송      D-14 Push 알림 + 시나리오 3안        │
│                              │              │                           │
│                              └──────┬───────┘                           │
│                                     ▼                                   │
│                                    END                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### LangGraph 코드 구조

```python
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import interrupt

# ── 공유 State 정의 ──────────────────────────────────────────────────────
class CPIAState(TypedDict):
    date: str                        # 처리 날짜
    raw_reports: list[dict]          # Collector 출력: 원시 작업일보
    structured_data: list[dict]      # Parser 출력: WBS 매핑 완료 JSON
    anomalies: list[dict]            # Validator 출력: 이상 항목 목록
    human_approved: bool             # Human-in-the-Loop 승인 여부
    daily_report: str                # Reporter 출력: 보고서 본문
    forecast: dict                   # Forecaster 출력: 예측 + 시나리오
    alerts: list[str]                # 발송된 알림 목록

# ── Node 함수 ────────────────────────────────────────────────────────────
def collector_node(state: CPIAState) -> CPIAState:
    """이메일·카카오톡에서 BP 작업일보 자동 수집 및 파싱"""
    ...

def parser_node(state: CPIAState) -> CPIAState:
    """Claude Sonnet: 비정형 텍스트 → WBS 코드 매핑 구조화"""
    ...

def validator_node(state: CPIAState) -> CPIAState:
    """전일 대비 ±30% 이상치 탐지, 정합성 검증"""
    ...

def human_review_node(state: CPIAState) -> CPIAState:
    """이상치 확인 요청 발송 후 담당자 승인 대기 (interrupt)"""
    result = interrupt({"anomalies": state["anomalies"]})   # 파이프라인 일시 중단
    return {"human_approved": result["approved"]}           # 승인 후 재개

def reporter_node(state: CPIAState) -> CPIAState:
    """Claude Sonnet: Daily·Weekly·Monthly 보고서 자동 생성 및 발주처 발송"""
    ...

def forecaster_node(state: CPIAState) -> CPIAState:
    """Claude Opus: 잔여공기 예측, D-14 리스크 탐지, 만회 시나리오 3안"""
    ...

# ── 조건부 라우팅 ─────────────────────────────────────────────────────────
def route_after_validation(
    state: CPIAState,
) -> Literal["human_review", "reporter"]:
    if state["anomalies"]:
        return "human_review"   # 이상치 발견 → 담당자 검토
    return "reporter"           # 정상 → 자동 진행

# ── Graph 구성 ────────────────────────────────────────────────────────────
builder = StateGraph(CPIAState)

builder.add_node("collector",     collector_node)
builder.add_node("parser",        parser_node)
builder.add_node("validator",     validator_node)
builder.add_node("human_review",  human_review_node)
builder.add_node("reporter",      reporter_node)
builder.add_node("forecaster",    forecaster_node)

builder.add_edge(START,            "collector")
builder.add_edge("collector",      "parser")
builder.add_edge("parser",         "validator")
builder.add_conditional_edges("validator", route_after_validation)
builder.add_edge("human_review",   "reporter")
builder.add_edge("reporter",       "forecaster")   # 순차 또는 Send()로 병렬 전환
builder.add_edge("forecaster",     END)

# Checkpoint: 파이프라인 상태 영구 저장 (human_review 중단/재개 지원)
checkpointer = PostgresSaver.from_conn_string("postgresql://cpia-db/state")
graph = builder.compile(checkpointer=checkpointer)
```

---

### Agent 상세 명세

#### Node 1 — Collector (데이터 수집)

| 항목 | 내용 |
|------|------|
| **역할** | BP 협력사 작업일보 자동 수집·채널 통합 |
| **트리거** | 매일 06:00 cron / 실시간 이메일 웹훅 |
| **Input** | 이메일 서버, 카카오 API, BP사 포털 |
| **Output** | `raw_reports: list[dict]` — 채널·BP사·날짜 태깅 |
| **구현** | 규칙 기반 파서 (LLM 불필요 — 비용 최소화) |
| **처리 규모** | Y-1 OBL 기준 BP 100개사+ / 전 채널 통합 |

#### Node 2 — Parser (Semantic Mapping)

| 항목 | 내용 |
|------|------|
| **역할** | 비정형 작업일보 → 공정표·WBS 항목 자동 분류 |
| **Input** | `raw_reports` (비정형 텍스트 + Excel 혼합) |
| **Output** | `structured_data` — `{wbs_code, 공종, 인원, 물량, 장비, 날짜, bp_id}` |
| **Model** | **Claude Sonnet 4.6** — 문맥 기반 Semantic Mapping |
| **참조 데이터** | WBS 코드 체계, 실행내역서, 현장 공정표 |

```
입력 예시: "철근 D25 오늘 120본 설치, 인원 15명, 크레인 1대"
출력 예시: { wbs_code: "C-03-02-01", work_type: "RC구조/철근",
             quantity: 120, unit: "본", manpower: 15,
             equipment: [{type:"크레인", count:1}] }
```

#### Node 3 — Validator (이상치 감지)

| 항목 | 내용 |
|------|------|
| **역할** | 데이터 정합성 검증 + 이상치 탐지 + 담당자 알림 준비 |
| **Input** | `structured_data` + 전일 DB |
| **Output** | `anomalies: list[dict]` (이상 항목 목록, 없으면 빈 리스트) |
| **탐지 로직** | 규칙: 전일 대비 물량 ±30% / 통계: 공종별 생산성 σ 2.0 이상 이탈 / 교차: BP 인원 vs 타각 기록 불일치 |

#### Node 4 — human_review (Human-in-the-Loop)

| 항목 | 내용 |
|------|------|
| **역할** | 이상치 발생 시 담당자에게 확인 요청 후 승인 대기 |
| **구현** | `interrupt()` — LangGraph 체크포인터가 상태 저장 후 파이프라인 일시 중단 |
| **UX** | 담당자 카카오·Slack 알림 수신 → 10분 내 확인·승인 → 파이프라인 자동 재개 |
| **Output** | `human_approved: bool` |

#### Node 5 — Reporter (보고서 자동 생성)

| 항목 | 내용 |
|------|------|
| **역할** | Daily·Weekly·Monthly 보고서 자동 생성 및 발주처 발송 |
| **Input** | 검증 완료 `structured_data` + 발주처별 템플릿 |
| **Output** | Daily Summary, QSR, PSR, S-Curve PPT, 이메일 자동 발송 |
| **Model** | **Claude Sonnet 4.6** — 보고서 문장·코멘트 생성 |
| **스케줄** | Daily 07:00 / Weekly 월요일 / Monthly 말일 |

#### Node 6 — Forecaster (공기 예측·시나리오)

| 항목 | 내용 |
|------|------|
| **역할** | 잔여공기 예측, D-14 리스크 탐지, 만회 시나리오 3안 생성 |
| **Input** | 누적 구조화 DB (Plan·Actual·생산성 추세) + 마스터 공정표 |
| **Output** | 공기 위험도 점수, D-14 Push 알림, 만회 시나리오 A·B·C |
| **Model** | **Claude Opus 4.7** — 복잡한 추론·불확실성 처리·시나리오 생성 |

```
만회 시나리오 자동 생성 예시
  시나리오 A: 인원 20명 증가  →  만회 가능 기간 12일 단축
  시나리오 B: 야간작업 주 3회  →  만회 가능 기간 8일 단축
  시나리오 C: 공종 순서 조정   →  Critical Path 5일 단축 + 비용 절감
```

### 데이터 파이프라인 선순환 구조

```
Reporter가 만드는 구조화 DB
        ↓
Forecaster 시계열 모델 학습 데이터
        ↓
예측 정확도 향상 → D-14 탐지 신뢰도 향상
        ↓
현장 신뢰 증가 → 데이터 품질 향상 (선순환)

A(데이터 수집·보고)와 B(공기 예측)는 동일 파이프라인에서 출발합니다.
A가 B의 학습 데이터를 만들고, A의 보고 속도가 B의 탐지 가치를 결정합니다.
```

---

## 04 — 정량적 효과

### 시간 절감 (Activity 실측 기반)

| 현장 | 현재 (실측) | 86% 절감 후 | FTE 절감 |
|------|-----------|-----------|---------|
| Y-1 Ph-1 OBL | 967h/월 | 135h | **5.9명** |
| Indiana Fab HAC | 410h/월 | 57h | **2.5명** |
| P&T 3 증축 | 296h/월 | 41h | **1.8명** |
| M15X OBL & PT7 | 286h/월 | 40h | **1.7명** |
| Y-1 Ph-1 IBL | 288h/월 | 40h | **1.8명** |
| 청주 M15X IBL | 259h/월 | 36h | **1.6명** |
| **합계** | **2,506h/월** | **351h/월** | **FTE 15.4명** |

### 공기 단축 4가지 경로

| 경로 | 현재 → CPIA 이후 | 공기 기여 |
|------|---------------|---------|
| 보고 사이클 단축 | D+2~3일 → D+0 (이슈 의사결정 2~3일 가속) | **3~5일** |
| D-14 선행 탐지 | 사후 인지 → 만회 가능 구간 확보 (지연의 50~70% 예방) | **간접** |
| 자재 수급 선제 | 긴급 발주 대기 3~5일 → D-21 예측 발주 | **2~3일** |
| 보고 해방 인력 | PM 80% 보고 → 공정 판단·협상 집중 | **간접** |

### 비용 절감 환산

```
직접 절감
  절감 시간: 2,155h/월
  시간당 비용: 70,000원 (인건비 + 간접비)
  월간: 약 1억 5,000만 원 → 연간 약 180억 원

간접 절감 (LD 리스크 회피)
  공기 지연 1일 손실: 수억~수십억 원 (현장 규모별)
  공기 단축: 3~7일 × 6개 현장 → 수백억 원 규모 LD 리스크 제거
```

---

## 05 — 데이터 준비도

AI 학습 및 추론에 필요한 3종 데이터가 **이미 확보**되어 있습니다. 별도 인프라 구축 없이 즉시 시작 가능합니다.

| 구분 | 데이터 | 형태 | 준비도 |
|------|--------|------|-------|
| **Plan** | 실행내역서·마스터 공정표·WBS·CBS·Staffing Norm | Excel, P6, CPMS | ✅ 즉시 활용 |
| **Actual** | BP 일일 작업일보 (비정형 텍스트 + Excel 혼합)·타각 기록 | 이메일·카카오·Excel | ✅ 즉시 활용 |
| **Knowledge** | 표준 품셈·CPMS 표준단가·과거 PJT 실적 DB·생산성 기준 | 공개·사내 시스템 | ⚠️ 조건부 활용 |

> 보안: 실행내역·작업일보 대외비 등급 → 전사 AI 인프라(사내 승인 환경) 사용 전제. 고객 개인정보 미포함으로 규제 리스크 없음.

---

## 06 — 실행 계획

파일럿 현장: **Y-1 Ph-1 OBL** — 6개 현장 중 CPIA 범위 967h/월로 최대 규모, BP 100개사·데이터 다양성에서 범용 모델 훈련 최적.

### Phase 1 — LangGraph 파이프라인 구축 (Month 1~2)

- [ ] Collector Node: 이메일·카카오 자동 수집 모듈 개발
- [ ] Parser Node: Claude Sonnet Semantic Mapping 프롬프트 설계·WBS 매핑 검증
- [ ] Validator Node: 이상치 탐지 로직 (±30% 임계값)
- [ ] Human-in-the-Loop: interrupt 체크포인트 + 담당자 알림 UX 구현
- [ ] Reporter Node: Daily Summary 자동 생성 템플릿 1종
- [ ] PostgresSaver 체크포인터 세팅 (상태 영구 저장)
- [ ] 전사 AI 인프라 승인·보안 검토 완료

> **KPI:** 작업일보 취합 400h → 40h (-90%) | 보고 D+0 달성

### Phase 2 — Forecaster 연동·KPI 검증 (Month 3~4)

- [ ] Phase 1 누적 데이터(2개월치)로 생산성 추세 모델 구축
- [ ] Forecaster Node: 잔여공기 예측·D-14 탐지 로직 구현 (Claude Opus)
- [ ] 만회 시나리오 3안 자동 생성 모듈
- [ ] Reporter 확장: Weekly·Monthly·S-Curve 자동화
- [ ] AI CPI/SPI vs 수작업 정합성 검증

> **KPI:** D-14 탐지율 검증 | CPI·SPI 정합도 90%+

### Phase 3 — 전 현장 확산·경영진 대시보드 (Month 5~6)

- [ ] M15X·P&T3·Indiana Fab 순차 확산 (공정표·템플릿 현장별 커스터마이징)
- [ ] 전현장 통합 대시보드 구축 (경영진용: CPI·SPI·공기 위험도)
- [ ] 현장간 생산성 벤치마크 기능
- [ ] 발주처(하이닉스 등) 보고 포맷 자동 연동
- [ ] 운영 매뉴얼·현장 담당자 온보딩

> **KPI:** 6개 현장 2,155h/월 절감 확인 | 현장당 공기 3~7일 단축

### KPI 요약

| KPI | As-is | To-be | 측정 시점 |
|-----|-------|-------|---------|
| 작업일보 취합 시간 | 400h/월 | 40h/월 | Phase 1 |
| 보고 리드타임 | D+2~3일 | D+0 | Phase 1 |
| CPI·SPI 정합도 | — | 90%+ | Phase 2 |
| 공기 리스크 탐지 | 사후 | D-14 선제 | Phase 2 |
| 6개 현장 절감 | 2,506h/월 | 351h/월 | Phase 3 |
| 공기 단축 | — | 3~7일/현장 | Phase 3 |

---

## 07 — 향후 확장성

Hi-tech 현장 검증 후 사업부 확산, 나아가 외부 수익화까지 동일 구조로 복제 가능합니다.

```
HORIZON 1 (0~6개월)           HORIZON 2 (6~18개월)        HORIZON 3 (18개월+)
Hi-tech 전 현장 검증  ──→     전사 사업부 확산         ──→  AI Solution 상품화

6개 현장 순차 확산             AI Solution 사업부 적용       CPIA SaaS 제품화
발주처 연동 표준화              에너지·배터리 현장 확장         타 건설사 파일럿 영업
경영진 대시보드 오픈            글로벌(Indiana) 영문 지원       발주처 직접 서비스

2,155h/월 절감                 4,200h+/월 절감 추정           외부 수익화
```

---

## 핵심 메시지

```
이 과제는 보고서를 빠르게 만드는 것이 아닙니다.

  현재 구조                        CPIA 이후
  ─────────────────────            ──────────────────────────
  엔지니어 = 데이터 취합자  ──→    엔지니어 = 데이터 기반 판단자
  Middle Office 존재        ──→    AI Agent가 Middle Office
  6개 현장 개별 중복 수행   ──→    단일 플랫폼으로 전 현장 처리
  지연 후 사후 대응         ──→    D-14 선행 탐지·만회 실행
```

Hi-tech 현장 공기 지연 1일의 LD 리스크는 수억~수십억 원 규모입니다.
CPIA는 연간 180억 원 직접 절감과 함께 그 이상의 리스크를 제거하며,
무엇보다 **Hi-tech 사업부가 일하는 방식 자체를 바꾸는 조직 차원의 AX**입니다.

---

*작성자: 조형준 프로 | SK에코플랜트 AI Board | 2026 FLP Module 2 — AI Design Project*
*데이터 출처: TASK 및 Activity 취합 및 분석_원본자료_1차검토.xlsx (Hi-tech 321개 Activity 실측)*
