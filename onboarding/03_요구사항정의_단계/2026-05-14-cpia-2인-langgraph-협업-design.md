# CPIA — 2인 LangGraph 협업 구현 설계

> 3주(2026-05-14 → 2026-06-05) 안에 CPIA 파이프라인 + Dashboard를 두 명이 동시에 만들어 시연 가능 상태로 동결한다. 이후 1주(6/6~6/12)는 보고자료 작성 기간, 6/13 시연(추정).
>
> 작성: 2026-05-14 · 기반: `CLAUDE.md`, `planning/CPIA_PoC_실행계획_v2.md`

---

## 0. 핵심 결정사항 요약

| 항목 | 결정 | 비고 |
|------|------|------|
| 구현 마감 | **2026-06-05(목)** — 코드/UI 동결 | 3주 압축, 이후 보고자료 작성 1주 확보 |
| 시연(추정) | 2026-06-13(금) | 보고자료 완성 후 |
| 인원 | 2명 — A(AI/Python), B(프론트/인프라) | CLAUDE.md 3인안 → 2인 재설계 |
| 브랜치 | **`A_Track`, `B_Track` 두 개만** | 영역별 단순 분리, 노드/화면 단위 브랜치 안 만듦 |
| Dashboard 스택 | Next.js (CLAUDE.md 확정안 유지) | v7.1 디자인 시안 활용 |
| 인프라 | homelab Docker (Postgres + ChromaDB) | Cloudflare Tunnel 외부 노출 |
| 뼈대 접근 | **E2E mock-first** — Week 1 초반에 모든 노드 stub 통과, 이후 우선순위대로 real 교체 | |
| Python ↔ Next.js 통신 | **얇은 FastAPI 1개** — `/run`, `/resume`, `/status` 3개 엔드포인트 | CLAUDE.md "FastAPI 없음" 결정 뒤집음 |
| H-i-L UI | Dashboard 통합 (Modal) | 데모 임팩트 우선 |
| 노드 우선순위 | P1 Collector·Parser·Synthetic / P2 Mapper·Atomizer·Reporter / **P3 Forecaster·Optimizer (데모 임팩트 1순위)** | |

---

## 1. 아키텍처 뼈대 (E2E mock-first)

```
┌─────────────────────────────────────────────────────────────┐
│  Browser (경영진)                                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Next.js Dashboard                                  │    │
│  │  Layer1: 현장 카드  /  Layer2: 상세 + H-i-L 버튼    │    │
│  └─────────────────┬───────────────────────────────────┘    │
└───────────────────│─────────────────────────────────────────┘
                    │  HTTP (fetch)
┌───────────────────▼─────────────────────────────────────────┐
│  Next.js API Routes (web/)                                   │
│  • GET /api/sites          ← 6개 현장 카드 (mock + 실데이터) │
│  • POST /api/pipeline/run  → FastAPI proxy                   │
│  • POST /api/hil/resume    → FastAPI proxy                   │
│  • GET /api/forecast/[id]  ← Postgres 직접 SELECT            │
└───────────────────┬─────────────────────────────────────────┘
                    │  HTTP (proxy)
┌───────────────────▼─────────────────────────────────────────┐
│  Python FastAPI (pipeline/api.py) — 얇은 래퍼                │
│  • POST /run        { date } → graph.invoke()  (백그라운드)  │
│  • POST /resume     { run_id, user_input }                   │
│  • GET  /status/{run_id}                                     │
└───────────────────┬─────────────────────────────────────────┘
                    │  in-process
┌───────────────────▼─────────────────────────────────────────┐
│  LangGraph (pipeline/graph.py)                               │
│  Collector → Parser → Mapper ─[interrupt:hil_1]─ Atomizer    │
│                                       ↓                       │
│              ┌──────── Reporter ‖ Forecaster                 │
│              │              [interrupt:hil_2] → Optimizer    │
│              └→ checkpoint 저장 (PostgreSQL)                  │
└───────────────────┬──────────────┬──────────────────────────┘
                    │              │
┌───────────────────▼───┐   ┌──────▼──────────────┐
│  PostgreSQL (homelab) │   │  ChromaDB (homelab)  │
│  - pipeline_runs      │   │  - daily_activities  │
│  - daily_reports      │   │    (synthetic + 실)  │
│  - forecasts          │   └──────────────────────┘
│  - optimizer_advice   │
│  - hil_checkpoints    │
└───────────────────────┘
```

**E2E mock-first 핵심**
- Week 1 종료 시점에 모든 박스가 "더미 데이터를 통과시키며 실행"되는 상태가 된다.
- 7개 에이전트는 첫 주에 입력 → 다음 노드로 mock 출력 전달 (LLM 호출 없음).
- Dashboard도 mock_sites.json만으로 풀 화면 렌더링 (파이프라인 결과 없이도).
- 이후 주차에 노드 하나씩 "real LLM 호출"로 교체하는 점진 확장 방식.

---

## 2. 폴더 구조

```
01_AI Design Project/
├── CLAUDE.md
├── README.md                       ← 신규: 2인 협업 가이드 + setup
│
├── pipeline/                       ← [담당: A]
│   ├── agents/
│   │   ├── collector.py            ← Week 1 stub → Week 2 real
│   │   ├── parser.py               ← Week 1 stub → Week 2 real
│   │   ├── mapper.py               ← Week 1 stub → Week 3 real
│   │   ├── atomizer.py             ← Week 1 stub → Week 3 real
│   │   ├── reporter.py             ← Week 1 stub → Week 2 real
│   │   ├── forecaster.py           ← Week 1 stub → Week 3 real
│   │   └── optimizer.py            ← Week 1 stub → Week 3 real
│   ├── state.py                    ← Phase 0 합의 (둘이 함께)
│   ├── graph.py                    ← LangGraph 조립 + interrupt 정의
│   ├── api.py                      ← FastAPI: /run, /resume, /status
│   ├── checkpointer.py             ← PostgresSaver 설정
│   ├── db.py                       ← Postgres ORM (SQLAlchemy 또는 asyncpg)
│   ├── chroma_client.py            ← Chroma 연결
│   ├── synthetic/
│   │   └── generate_history.py     ← 30일 가상 이력 생성
│   ├── tests/
│   │   ├── test_stubs_e2e.py       ← Week 1: stub 전체 통과 검증
│   │   └── test_each_agent.py
│   ├── main.py                     ← CLI 진입점 (개발자용)
│   ├── pyproject.toml              ← uv 또는 poetry
│   └── .env.example
│
├── web/                            ← [담당: B]
│   ├── app/
│   │   ├── page.tsx                ← Layer 1: 전체 현장 현황
│   │   ├── sites/[id]/page.tsx     ← Layer 2: 현장 상세 + H-i-L
│   │   ├── api/
│   │   │   ├── sites/route.ts
│   │   │   ├── pipeline/run/route.ts      ← FastAPI proxy
│   │   │   ├── hil/resume/route.ts        ← FastAPI proxy
│   │   │   └── forecast/[id]/route.ts     ← Postgres 직접
│   │   └── components/
│   │       ├── SiteCard.tsx
│   │       ├── ProductivityChart.tsx
│   │       ├── MappingReviewModal.tsx     ← H-i-L 1
│   │       └── TradeSelectorModal.tsx     ← H-i-L 2
│   ├── lib/
│   │   ├── db.ts                          ← Postgres client
│   │   └── fastapi.ts                     ← FastAPI fetch wrapper
│   ├── .env.local.example
│   └── package.json
│
├── infra/                          ← [담당: B]
│   ├── docker-compose.yml          ← Postgres + Chroma
│   ├── postgres/init.sql           ← 테이블 생성
│   ├── postgres/migrations/        ← 스키마 변경은 마이그레이션 파일로
│   └── README.md                   ← homelab 배포 절차
│
├── data/                           ← [공유, git ignore]
│   ├── input/YYYYMMDD/             ← 작업일보 드롭
│   ├── output/reports/YYYYMMDD.md  ← Reporter 출력
│   └── mock_sites.json             ← 6개 현장 더미 (Layer 1용)
│
├── docs/
│   ├── architecture/
│   │   ├── stack.md                ← 기술 결정 근거
│   │   └── api-contract.md         ← Phase 0 합의
│   ├── schema/
│   │   ├── postgres.md             ← Phase 0 합의
│   │   └── state.md                ← Phase 0 합의
│   └── superpowers/specs/          ← 본 spec 저장 위치
│
└── planning/                       ← 기존 v1/v2 plan (참고용)
```

**핵심 포인트**
- `pipeline/api.py` (FastAPI 얇은 래퍼) — CLAUDE.md "FastAPI 없음" 결정을 명시적으로 뒤집음.
- `docs/architecture/`, `docs/schema/` 3개 문서가 Phase 0 합의 산출물.
- `tests/test_stubs_e2e.py` — Week 1 종료 게이트 (통과해야 Week 2 진입).

---

## 3. Phase 0 — 둘이 함께 결정할 3가지

> 시작 전 2~3일(5/14~5/16) 통합 작업. 이 합의 없이 병렬 개발 시작하면 Week 2에 충돌.

### 3-1. `pipeline/state.py` — LangGraph State 스키마

```python
from typing import TypedDict, Literal

class Activity(TypedDict):
    wbs_code: str | None      # Mapper 이후 채워짐
    trade: str                 # 철근/거푸집/콘크리트
    workers: int
    quantity: float
    unit: str                  # ton, m², m³
    work_content: str          # Atomizer 임베딩 원천 — 절대 누락 금지
    conditions: list[str]      # 우천/병행작업/장비대기
    requires_review: bool      # Mapper 확신도 낮음 플래그

class CPIAState(TypedDict):
    # 입력
    run_id: str                # UUID
    date: str                  # YYYYMMDD
    input_files: list[str]

    # 파이프라인 누적
    raw_texts: dict[str, str]              # filename → text
    parsed: list[Activity]
    mapped: list[Activity]
    hil_1_corrections: dict                 # H-i-L 1 결과 (Dashboard 입력)
    atomized_ids: list[str]                 # Chroma 적재 ID

    # 분기 결과
    report_md: str
    forecast: list[dict]
    hil_2_selection: list[str]              # 선택된 trade
    optimizer_advice: list[dict]

    # 상태
    current_node: str
    status: Literal["running", "waiting_hil_1", "waiting_hil_2", "completed", "failed"]
```

### 3-2. `docs/schema/postgres.md` — 7개 테이블

```sql
pipeline_runs       (run_id PK, date, status, started_at, completed_at, current_node)
checkpoints         -- LangGraph PostgresSaver 기본 스키마
daily_reports       (run_id FK, date, bp_name, report_md, history_csv_row JSONB)
forecasts           (run_id FK, trade, assessment, reasoning, similar_cases JSONB,
                     expected_completion, risk_level)
optimizer_advice    (run_id FK, trade, diagnosis, recovery_pattern JSONB, recommendations)
mapping_corrections (id, date, original JSONB, corrected JSONB, created_at)
                    -- H-i-L 1 누적 — Mapper 프롬프트 feedback
sites               (site_id PK, name, plan_progress, actual_progress,
                     last_run_id FK, status)  -- 5개는 mock, 1개는 실 PoC 현장
```

### 3-3. `docs/architecture/api-contract.md` — 양방향 API 계약

```
[FastAPI (pipeline/api.py) — Next.js가 호출]
  POST /run         { date: "20260601" }
        → { run_id: "uuid" } (즉시 반환, 백그라운드 실행)
  POST /resume      { run_id, hil_step: 1|2, payload: ... }
        → { status: "running" | "waiting" | "completed" }
  GET  /status/{run_id}
        → { status, current_node, error? }

[Next.js API Routes — Browser가 호출]
  GET    /api/sites                    → SiteCard[]  (Layer 1)
  GET    /api/sites/[id]               → SiteDetail  (Layer 2 통합 데이터)
  POST   /api/pipeline/run             → FastAPI /run proxy
  POST   /api/hil/resume               → FastAPI /resume proxy
  GET    /api/runs/[id]/forecast       → Forecast[]
  GET    /api/runs/[id]/optimizer      → Advice[]
```

**완료 게이트:** 이 3개 문서가 git에 머지되고 둘 다 OK 사인할 때까지 노드 코드 작성 금지.

---

## 4. 2인 분담 + 노드 우선순위

### 분담 매트릭스

| 영역 | A (AI/Python) | B (프론트/인프라) |
|------|----|----|
| Phase 0 합의 | state.py 초안 | postgres schema 초안 |
| api-contract | 둘이 함께 작성 | 둘이 함께 작성 |
| Infra | – | docker-compose, postgres init, Cloudflare Tunnel |
| LangGraph 코어 | graph.py, checkpointer, FastAPI | – |
| 노드 7개 | 전부 | – |
| Synthetic history | generator + Chroma 적재 | – |
| Dashboard Layer 1 | – | mock_sites.json + 카드 UI |
| Dashboard Layer 2 | – | 상세 화면 + 차트 |
| H-i-L Modal | – | UI 컴포넌트 + 데이터 연결 |
| Next.js API Routes | – | 전부 |
| 데모 리허설 | 파이프라인 측 | UI 측 |

### 노드 우선순위 (P0 → P3)

기준: **데모 임팩트 × 의존성**. Forecaster/Optimizer가 LLM으로 "진짜 진단·조언"하는 게 임팩트 1순위. Mapper는 H-i-L 게이팅. Reporter는 양식 채우기에 가까워 최후순위.

| 우선순위 | 노드 | 이유 | 완성 목표 |
|----|------|------|--------|
| P0 | 모든 노드 stub + graph.py + FastAPI + Docker | E2E 통과 게이트 | Week 1 전반 (~5/19) |
| P1 | Collector (real) + Parser (real, Sonnet) | 입력이 진짜여야 데모 시작 가능 | Week 1 후반 (~5/22) |
| P1 | Synthetic history 30일 + Chroma 적재 | Forecaster prereq | Week 1 후반 (~5/22) |
| P2 | Mapper (real, Sonnet) + H-i-L 1 | 매핑 H-i-L이 데모 핵심 장면 | Week 2 (~5/29) |
| P2 | Atomizer (임베딩만) | Mapper 결과 → Chroma | Week 2 (~5/29) |
| P2 | Reporter (real, Sonnet) | 양식 채우기 — 미완성 시 stub로도 데모 가능 | Week 2 (~5/29) |
| P3 | **Forecaster (real, Opus) + H-i-L 2** | **데모 임팩트 1순위** | Week 3 (~6/5) |
| P3 | **Optimizer (real, Opus)** | **데모 임팩트 1순위** | Week 3 (~6/5) |

### B 트랙 우선순위 (병렬)

| 우선순위 | 작업 | 완성 목표 |
|----|------|--------|
| P0 | docker-compose (Postgres+Chroma) + Cloudflare Tunnel | Week 1 전반 (~5/19) |
| P0 | postgres init.sql + Next.js scaffolding | Week 1 전반 (~5/19) |
| P1 | Layer 1 카드 UI + mock_sites.json + /api/sites | Week 1 후반 (~5/22) |
| P2 | Layer 2 상세 + 차트 + /api/runs/[id]/* | Week 2 (~5/29) |
| P2 | H-i-L 1 Modal (매핑 검토·수정) | Week 2 (~5/29) |
| P3 | H-i-L 2 Modal + Optimizer 결과 화면 | Week 3 (~6/5) |
| P3 | 데모 시나리오 폴리싱 + 사전 캡처 | Week 3 (~6/5) |

### 병렬 가능성

- **A는 B를 기다리지 않는다.** A는 `python main.py 20260601`로 CLI에서 모든 노드 검증 가능. Postgres·Chroma만 띄워져 있으면 됨(Week 1에 B가 띄움).
- **B는 A를 기다리지 않는다.** B는 Phase 0 합의(API 계약 + DB 스키마)만 있으면 mock 데이터로 풀 화면 개발. A의 노드가 실제 동작하지 않아도 Dashboard 완성도 100%까지 가능.
- **합류 시점:** Week 2 말(H-i-L 1 통합, ~5/29), Week 3 중반(전체 통합 리허설, ~6/3~6/5).

---

## 5. 주차별 진행 (3주 압축 — 6/5 마감)

전체 흐름: **3주에 구현 완전 동결 → 1주 보고자료 작성 → 시연**. 원래 4주 일정에서 Week 4(임팩트 노드)는 그대로 두되 Week 1·2·3 내용을 2주로 압축해 5/22까지 끝낸다.

### Week 1 (5/14 수 → 5/22 금, 9일) — "뼈대 + 입력 real까지"

원래 Week 1(뼈대 stub)과 Week 2(입력 real)를 합쳐 한 주(실제로는 9일)에 진행. 이번 주는 코드량이 많아 보이지만 둘이 완전히 병렬로 일하므로 가능.

**5/14~16 (수목금) — Phase 0 합의 (둘이 함께)**

state.py · postgres.md · api-contract.md 3종 문서를 git에 머지하고 둘 다 OK 사인. 이 합의 없이 각자 코딩 시작하면 합칠 때 며칠을 날린다.

**5/17~19 (토일월) — 뼈대 stub**

- **A**: 7개 에이전트 함수 stub(입력 받아 mock 출력 넘김) + LangGraph 그래프 조립 + interrupt 2개 정의 + PostgresSaver + FastAPI 3개 엔드포인트.
- **B**: homelab Postgres+ChromaDB Docker + Cloudflare Tunnel 외부 노출 + Next.js 14 scaffolding + mock_sites.json 6개 현장 더미.

**🔒 GATE 1 (5/19 월 종료):** A는 `curl FastAPI/run`으로 파이프라인이 끝까지 통과하는 걸 보여주고, B는 `npm run dev`로 현장 카드 6개가 그려진 첫 화면을 보여준다.

**5/20~22 (화수목금) — 입력을 진짜로**

- **A**: 작업일보 xlsx를 진짜로 읽는 Collector, Sonnet에 텍스트를 줘서 공종별 인원·물량·작업내용을 JSON으로 뽑는 Parser. 동시에 가장 중요한 사전 작업 — **30일치 가상 이력**을 만들어 ChromaDB에 적재(없으면 Forecaster 비교 대상 없음).
- **B**: Layer 1 화면(6개 현장 카드 그리드)을 v7.1 디자인 시안 기반으로 실제 컴포넌트화, /api/sites 라우트로 mock 데이터 연결. H-i-L Modal 껍데기까지 그려둠.

**🔒 GATE 2 (5/22 금 종료):** 실제 작업일보 파일을 input 폴더에 떨어뜨리면 Parser가 JSON을 뽑아 터미널에 출력. Dashboard Layer 1은 화면만 보면 데모 가능한 수준.

---

### Week 2 (5/23 토 → 5/29 금, 7일) — "중간 노드 + H-i-L 1 통합"

원래 Week 3 내용. 이번 주의 산물은 **PoC에서 가장 까다로운 통합 지점**(LangGraph interrupt ↔ Dashboard Modal)을 실동작시키는 것.

**5/23~26 (토일월화)**

- **A**: Parser 결과를 공정표 WBS에 매핑하는 Mapper(Sonnet, 확신도 낮은 항목엔 `requires_review` 플래그), Mapper 결과를 ChromaDB에 적재하는 Atomizer(임베딩만, LLM 없음), 통합 보고서 MD를 만드는 Reporter(Sonnet). Mapper에서 LangGraph `interrupt(hil_1)`가 처음 등장 — 확신도 낮은 매핑을 만나면 파이프라인이 멈추고 Dashboard에서 사람 입력을 기다린다.
- **B**: Layer 2 사이트 상세 화면(S-curve · 공종별 카드) + H-i-L 1 Modal 진짜 연결 + /api/runs/[id]/* 라우트들.

**5/27~29 (수목금) — 통합**

매핑이 멈추면 모달이 뜨고, 수정 후 "재개" 누르면 Next.js → FastAPI /resume이 호출돼 Python 쪽 그래프가 다시 돈다. 둘이 같이 디버깅하며 흐름 안정화.

**🔒 GATE 3 (5/29 금 종료):** 파일 드롭 → Parser → Mapper까지 진행되다 멈추고 → **Dashboard에 모달이 뜨고, 거기서 수정하면 Atomizer + Reporter까지 자동으로 진행되는 흐름**이 실동작. 통과되면 데모 스토리 절반은 검증된 셈.

---

### Week 3 (5/30 토 → 6/5 목, 7일) — "임팩트 노드 + 마감 동결"

원래 Week 4 내용. **데모의 클라이맥스 두 노드**(Forecaster, Optimizer)에 집중. Opus 4.7로 돌리는 두 노드, ChromaDB에서 유사 과거 상황을 5건씩 뽑아 프롬프트에 주입하는 RAG 패턴이라 프롬프트 튜닝에 시간이 든다.

**5/30~6/2 (토일월화)**

- **A**: Forecaster(Opus 4.7, RAG, 진단 결과 `forecasts` 테이블 저장) + LangGraph `interrupt(hil_2)` + Optimizer(Opus 4.7, RAG, 조언 `optimizer_advice` 테이블 저장).
- **B**: 진단 결과 카드(정상/주의/위험) + H-i-L 2 Modal(리스크 공종 표시 → PM 선택) + Optimizer 조언 패널(과거 사례 + 권고사항).

**6/3~6/5 (수목금) — 통합 리허설 + 동결**

둘이 같이 End-to-End 통합 테스트(파일 드롭부터 Layer 2 갱신까지 5분 안에 완주). 데모 시나리오 리허설 3회. 핵심 화면은 사전 캡처를 떠둔다(라이브 실패 시 5초 안에 전환).

**🔒 마감 (6/5 목 종료):** 시연 가능 상태로 코드/UI **동결**. 이후 기능 변경 금지(긴급 버그픽스만 허용).

---

### 6/6 → 시연 — 보고자료 작성 (사용자)

- 6/6~6/12: 사용자가 보고자료 작성. 구현 동결 상태라 화면·캡처가 안정적이라 작성 효율 ↑.
- 6/13(추정): 경영진 시연.

---

### 마감 위협 시 후퇴선 (앞당겨진 마감이라 더 빠듯)

| 동결 시점 | 후퇴 항목 |
|---------|----------|
| 6/2(월) 위협 감지 | Reporter stub 유지 (보고서 자동생성 멘트만, 화면 비활성화) |
| 6/3(화) 위협 | Forecaster·Optimizer 중 하나는 사전 캡처 결과로 시연 전환 |
| 6/4(수) 위협 | H-i-L 2를 CLI fallback, Dashboard는 결과만 표시 |
| 6/5(목) 종료 시 미완 | 5/22 GATE 2 + 5/29 GATE 3까지의 산물만으로 시연 (Forecaster·Optimizer 캡처) |

핵심 원칙:
- **GATE 1~3은 절대 미루지 않는다.** GATE 3까지 통과되면 데모 스토리 80%는 굴러간다.
- **Forecaster·Optimizer는 어떻게든 살린다.** 이 둘이 죽으면 데모 자체가 약해진다.
- Mapper 정확도가 낮으면 오히려 "AI가 완벽하지 않아서 H-i-L 검증이 필요하다"는 스토리로 역이용한다.

---

## 6. 둘이 부딪히지 않는 협업 규칙

### 1. 코드는 GitHub, 데이터는 homelab
코드는 무조건 git을 거친다. 각자 로컬에서 클론받아 일하고, PR로 머지. 반대로 데이터(Postgres·ChromaDB)는 homelab 서버 하나만 바라본다 — A가 파이프라인 돌리면 B의 Dashboard에서 바로 결과를 본다. **절대 하지 않는 것:** 서버에 SSH 들어가서 직접 코드 수정.

### 2. 브랜치는 `A_Track`·`B_Track` 두 개만
```
main      ← 동작하는 것만 머지 (GATE 통과 시점에 PR 머지)
A_Track   ← 팀원 A 작업 브랜치 (pipeline/ 전체)
B_Track   ← 팀원 B 작업 브랜치 (web/ + infra/ 전체)
```

각자 자기 트랙에 직접 커밋. 노드별·화면별 세부 브랜치는 만들지 않는다(2인이라 충돌 가능성 낮음). 두 트랙은 서로 다른 폴더만 만지므로 main 머지 시 충돌이 거의 없다.

머지 시점:
- **GATE 1 (5/19)**: 양쪽 모두 main에 머지 — Phase 0 결과 + 뼈대
- **GATE 2 (5/22)**: 양쪽 모두 main에 머지 — 입력 real + Layer 1
- **GATE 3 (5/29)**: 양쪽 모두 main에 머지 — H-i-L 1 통합 완료
- **마감 (6/5)**: 최종 머지, 이후 동결

머지 사이에는 각자 자기 트랙에 자유롭게 커밋. 다른 트랙 코드는 건드리지 않는다(긴급 시 PR로 요청).

### 3. Phase 0 합의 문서는 함부로 못 바꾼다
state.py·postgres 스키마·api 계약 — 셋 중 하나라도 바꾸려면 **상대방 OK 받기 전 머지 금지**. A가 "state 필드 추가해야겠다" 싶으면 한 줄 던지고 B 확인받는다. 일방적 변경 금지.

### 4. DB 스키마 변경은 마이그레이션 파일로
Postgres를 직접 `ALTER TABLE`로 만지지 말고 `infra/postgres/migrations/`에 SQL 파일을 날짜순으로 쌓는다. 상대방도 동일하게 반영 가능.

### 5. 환경 변수는 .env.example로만 공유
API 키·비밀번호가 들어가는 `.env`는 git에 절대 안 올린다. `.env.example`에 항목명만 나열, 실제 값은 안전한 채널(1Password·슬랙 DM)로 주고받는다.

### 6. 데일리 동기화 15분
매일 정해진 시간(예: 오전 10시) 15분만 — 어제 한 것, 오늘 할 것, 막힌 것. 30분 넘어가면 회의가 일을 잡아먹는다.

### 7. "1시간 룰" — 막히면 빨리 공유
혼자 1시간 이상 같은 곳에서 막히면 무조건 공유. 자존심 부리며 반나절 날리지 않는다.

### 8. 데모 시연 책임 분리
시연 당일 — A는 파이프라인 모니터링, B는 화면 조작·멘트. 둘 다 똑같이 책임지지 말고 영역을 나눈다. 핵심 구간은 6/5 동결 직전에 사전 화면 녹화를 떠두고, 라이브 실패 시 5초 안에 녹화로 전환할 수 있게 셋업.

### 9. "안 만드는 것" 목록을 지킨다
v2 plan PoC 제외 항목(품셈 비교, 인원 재배치 수치 계산, 이메일 연동, 6개 현장 확산)은 3주 내내 손대지 않는다. 데모 보면서 "이것도 있으면 좋겠는데" 싶은 게 보여도 메모만 하고 Phase 2로 넘긴다. 3주 압축이라 스코프 부풀리기는 즉시 마감 위협으로 이어진다.

---

## 7. 리스크 및 대응

| 리스크 | 발생 가능성 | 대응 |
|--------|-----------|----|
| Phase 0 합의 지연 | 높음 | 5/16(금)까지 미합의면 주말까지 끌고 가서 5/19 GATE 1 사수 |
| FastAPI ↔ LangGraph interrupt 통합 난항 | 중간 | Week 2 GATE 3 (5/29) 통과 안 되면 H-i-L을 CLI fallback (섹션 5 후퇴선) |
| Forecaster 프롬프트 튜닝 시간 부족 | **높음** | Week 3 초반 4일(5/30~6/2) 전부 투자, Reporter는 Week 2에 완료해두기 |
| Synthetic history 패턴 단조로움 | 중간 | Week 1 GATE 2 (5/22)에 다양성 검증 항목 추가 |
| homelab Cloudflare Tunnel 불안정 | 낮음 | A는 SSH 터널 fallback 미리 셋업 |
| 시연 중 API 오류 | 중간 | 6/5 동결 직전 핵심 구간 사전 캡처 보유 |
| 3주 압축 자체의 부담 | **높음** | 마감 위협 시 후퇴선(섹션 5)을 망설이지 말고 즉시 적용 |

---

## 8. 성공 기준 (6/5 마감 검증)

| # | 기준 | 검증 방법 |
|---|------|--------|
| 1 | 작업일보 파일 드롭 → 5분 내 Dashboard 결과 갱신 | 라이브 |
| 2 | Dashboard에서 H-i-L 1 매핑 수정 → 파이프라인 자동 재개 | 라이브 |
| 3 | Forecaster: 과거 유사 이력 인용한 진단 출력 | 라이브 또는 캡처 |
| 4 | H-i-L 2: PM이 공종 선택 → Optimizer 조언 생성 | 라이브 또는 캡처 |
| 5 | Layer 1 6개 현장 → Layer 2 상세 전환 시연 | 라이브 |
| 6 | AS-IS 수작업 2~3시간 vs TO-BE AI 5분 비교 1장 | 슬라이드 (보고자료 작성 기간) |

**마감 동결 체크리스트 (6/5 목 종료 시):**
- [ ] 위 1~5번 시연 흐름이 5분 안에 완주됨
- [ ] 핵심 화면 사전 캡처 보유 (라이브 실패 fallback)
- [ ] `main` 브랜치 머지 완료, A_Track / B_Track 추가 커밋 금지
- [ ] 보고자료 작성에 필요한 화면·수치·시나리오가 모두 안정적으로 재현됨

---

*작성: 2026-05-14*
*기반 문서: `CLAUDE.md`, `planning/CPIA_PoC_실행계획_v2.md`, `design/CPIA_기획서_v7.1.html`*
