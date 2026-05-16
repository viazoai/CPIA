# CPIA — Construction Productivity Intelligence Agent

> AI가 건설 현장 작업일보를 자동 분석하여 생산성을 진단하고, 경영진에게 근거 있는 액션을 제시한다.

---

## 무엇을 만드는가

작업일보 파일을 드롭하면 AI 파이프라인이 자동 실행되어:

1. 파일을 읽고 구조화한다 (Collector → Parser)
2. 공정표(WBS)에 매핑하고 담당자가 검토한다 (Mapper + H-i-L 1)
3. 오늘 작업 기록을 Vector DB에 적재한다 (Atomizer)
4. 통합 보고서를 생성한다 (Reporter)
5. 오늘 생산성이 과거 유사 상황 대비 적정한지 진단한다 (Forecaster)
6. PM이 이상 공종을 선택하면 맥락 기반 조언을 생성한다 (Optimizer + H-i-L 2)
7. 경영진 대시보드에서 전체 현황과 결과를 확인한다 (Dashboard)

**핵심 차별점:** 절대 기준(품셈) 없이, 현장 실적 이력을 Vector DB에 쌓아 유사 과거 상황과 비교하는 상대적 판단.

**데모 목표:** AS-IS 수작업 2~3시간 → TO-BE AI 5분 이내, 경영진 앞 라이브 시연.

**구현 마감:** 2026-06-05(목) 동결 — 3주 압축 일정(시작 2026-05-14). 이후 6/6~6/12 보고자료 작성, 6/13(추정) 시연.

**상세 계획:** `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`

---

## 확정 기술 스택

| 레이어 | 기술 | 선택 이유 |
|--------|------|---------|
| AI 파이프라인 | Python + LangGraph | H-i-L interrupt·조건 분기 지원 |
| LLM (파싱·매핑·보고서) | **Azure OpenAI `gpt-5.1-chat-ai-board-test`** | A_Track 매핑 레이어 plan 확정 (SK 사내 AI Board) |
| LLM (진단·조언) | TBD — 후속 plan | Forecaster·Optimizer LLM 은 다음 plan 에서 결정 |
| 임베딩 | **Azure OpenAI `text-embedding-3-small-ai-board-test`** (1536d) | 한국어 건설 도메인, Azure 동일 endpoint |
| Vector DB | ChromaDB (서버 모드) — `wbs_master` 189 + `daily_activities` 두 컬렉션 | RAG 검색(wbs_master) + 유사 이력(daily_activities) 의도 분리 |
| 관계형 DB | PostgreSQL | 파이프라인 결과 저장 + LangGraph checkpoint, 대시보드 데이터 소스 |
| **파이프라인 API** | **FastAPI (얇은 래퍼)** | **H-i-L Dashboard 통합을 위해 `/run`·`/resume`·`/status` 3개 엔드포인트만 노출** |
| 프론트엔드 | Next.js (React) | AI 코드 생성 품질, API Routes로 BFF 패턴 |
| 인프라 | homelab Docker Compose | 팀원 공유 DB 서버, Cloudflare Tunnel로 외부 접속 (PoC 1차에서 A는 로컬 Docker 사용, 완료 후 homelab 마이그레이션) |

**FastAPI 추가 (CLAUDE.md v1 결정 뒤집음):** H-i-L 1·2를 Dashboard에 통합하기로 하면서 LangGraph `interrupt`/`resume`을 외부에서 트리거할 양방향 통신이 필요해짐. Next.js API Routes는 BFF(Backend-for-Frontend)로 FastAPI를 proxy하며 Postgres 직접 SELECT도 병행한다.

---

## 아키텍처

```
[Browser — 경영진]
        ↓
[Next.js Dashboard]
   Layer 1: 6개 현장 전체 현황 카드
   Layer 2: 현장 상세 + H-i-L Modal + 생산성 진단 + Optimizer 조언
        ↓ fetch
[Next.js API Routes — BFF]
   • GET  /api/sites              ← Postgres 직접 SELECT
   • POST /api/pipeline/run       → FastAPI /run     (proxy)
   • POST /api/hil/resume         → FastAPI /resume  (proxy)
   • GET  /api/runs/[id]/...      ← Postgres 직접 SELECT
        ↓ HTTP
[FastAPI — pipeline/api.py]
   • POST /run        → graph.invoke()  (백그라운드 실행, run_id 즉시 반환)
   • POST /resume     → checkpoint에서 graph 재개 (H-i-L 1/2)
   • GET  /status/{run_id}
        ↓ in-process
[LangGraph]
   Collector → Parser → Mapper ─[interrupt:hil_1]─ Atomizer
                                                       ↓
                                        Reporter ‖ Forecaster
                                                       ↓
                                              [interrupt:hil_2]
                                                       ↓
                                                   Optimizer
        ↓ 결과 저장
[PostgreSQL — homelab]              [ChromaDB — homelab]
   • pipeline_runs                     • daily_activities
   • checkpoints                         (synthetic 30일 + 실제 누적)
   • daily_reports
   • forecasts
   • optimizer_advice
   • mapping_corrections (H-i-L 1)
   • sites (5개 mock + 1개 실 PoC)
```

**H-i-L 통합 흐름:** Mapper 또는 Forecaster에서 LangGraph `interrupt` 발생 → FastAPI `/status`가 `waiting_hil_*` 반환 → Dashboard가 polling으로 감지 후 Modal 띄움 → 사용자 입력 → Next.js API `/hil/resume` → FastAPI `/resume` → checkpoint에서 graph 재개.

---

## 폴더 구조

```
01_AI Design Project/
│
├── CLAUDE.md                   ← 이 파일
│
├── pipeline/                   ← [담당: A] Python 파이프라인 (LangGraph)
│   ├── agents/
│   │   ├── collector.py
│   │   ├── parser.py
│   │   ├── mapper.py
│   │   ├── atomizer.py
│   │   ├── reporter.py
│   │   ├── forecaster.py
│   │   └── optimizer.py
│   ├── state.py                ← Phase 0 합의: Agent 간 공유 데이터 구조
│   ├── graph.py                ← LangGraph 조립 + interrupt 2개 정의
│   ├── api.py                  ← FastAPI: /run, /resume, /status
│   ├── checkpointer.py         ← PostgresSaver 설정
│   ├── db.py                   ← Postgres ORM
│   ├── chroma_client.py        ← Chroma 연결
│   ├── synthetic/
│   │   └── generate_history.py ← 30일 가상 이력 생성
│   ├── tests/
│   │   ├── test_stubs_e2e.py   ← Week 1 게이트: stub 전체 통과
│   │   └── test_each_agent.py
│   ├── main.py                 ← CLI 진입점 (개발자용)
│   ├── pyproject.toml
│   └── .env.example
│
├── web/                        ← [담당: B] Next.js 프론트엔드
│   ├── app/
│   │   ├── page.tsx            ← Layer 1: 전체 현장 현황
│   │   ├── sites/[id]/page.tsx ← Layer 2: 현장 상세 + H-i-L Modal
│   │   ├── api/
│   │   │   ├── sites/route.ts
│   │   │   ├── pipeline/run/route.ts      ← FastAPI proxy
│   │   │   ├── hil/resume/route.ts        ← FastAPI proxy
│   │   │   └── runs/[id]/forecast/route.ts
│   │   └── components/
│   │       ├── SiteCard.tsx
│   │       ├── ProductivityChart.tsx
│   │       ├── MappingReviewModal.tsx     ← H-i-L 1
│   │       └── TradeSelectorModal.tsx     ← H-i-L 2
│   ├── lib/
│   │   ├── db.ts
│   │   └── fastapi.ts
│   ├── .env.local.example
│   └── package.json
│
├── infra/                      ← [담당: B] homelab 인프라
│   ├── docker-compose.yml      ← PostgreSQL + ChromaDB
│   ├── postgres/init.sql       ← 초기 테이블 생성
│   ├── postgres/migrations/    ← 스키마 변경은 마이그레이션 파일로
│   └── README.md               ← homelab 배포 절차
│
├── data/                       ← git ignore (homelab 공유 데이터만 사용)
│   ├── synthetic_history/      ← Vector DB cold start용 가상 이력 (생성 후 Chroma 적재)
│   ├── mock_sites.json         ← Dashboard Layer 1용 6개 더미 현장
│   ├── input/YYYYMMDD/         ← 작업일보 드롭 폴더
│   └── output/reports/YYYYMMDD.md  ← Reporter 출력
│
├── docs/
│   ├── architecture/
│   │   ├── stack.md
│   │   └── api-contract.md     ← Phase 0 합의: FastAPI + Next.js API 계약
│   ├── schema/
│   │   ├── postgres.md         ← Phase 0 합의: 7개 테이블 정의
│   │   └── state.md            ← Phase 0 합의: LangGraph CPIAState 스키마
│   └── superpowers/specs/
│       └── 2026-05-14-cpia-2인-langgraph-협업-design.md ← 본 4주 실행계획
│
└── planning/                   ← 기획 문서 (참고용)
    └── CPIA_PoC_실행계획_v2.md
```

---

## Agent 역할 요약

| Agent | 입력 | 출력 | LLM |
|-------|------|------|-----|
| Collector | 파일 경로 | 시트별 원문 텍스트 | 없음 |
| Parser | 원문 텍스트 + WBS 공종 목록 | 구조화 JSON | Azure OpenAI gpt-5.1 |
| Mapper | Parser JSON + `wbs_master` Chroma RAG + `activity_master` PG | WBS 매핑 완료 JSON | Azure OpenAI gpt-5.1 (rerank) |
| Atomizer | Mapper JSON | ChromaDB `daily_activities` 적재 | Azure OpenAI 임베딩만 |
| Reporter | Mapper JSON | 통합 Daily Report (MD) + PostgreSQL 저장 | Azure OpenAI gpt-5.1 |
| Forecaster | Mapper JSON + ChromaDB 유사 이력 | 공종별 생산성 진단 + PostgreSQL 저장 | TBD (후속 plan) |
| Optimizer | Forecaster 결과 + ChromaDB 과거 패턴 | 맥락 기반 조언 + PostgreSQL 저장 | TBD (후속 plan) |

**H-i-L 포인트 2개:**
- H-i-L 1 (Mapper 이후): 확신도 낮은 매핑 항목 담당자 검토·수정
- H-i-L 2 (Forecaster 이후): PM이 Optimizer 조언 받을 공종 선택

---

## 협업 방식

### 코드 — GitHub

**레포:** https://github.com/viazoai/CPIA

```
main      ← 동작하는 것만 머지 (GATE 통과 시점에 PR 머지)
A_Track   ← 팀원 A 작업 브랜치 (pipeline/ 전체)
B_Track   ← 팀원 B 작업 브랜치 (web/ + infra/ 전체)
```

**브랜치 정책:** 2인 협업이라 노드별·화면별 세부 브랜치는 만들지 않는다. 각자 자기 트랙에 직접 커밋하고, GATE 통과 시점(5/19·5/22·5/29·6/5)에 PR을 만들어 main에 머지. 두 트랙은 서로 다른 폴더(pipeline/ vs web/+infra/)만 만지므로 충돌이 거의 없다. 다른 트랙 코드는 건드리지 않는다(긴급 시 PR로 요청).

### 데이터 — homelab 공유 서버

```
GitHub (코드)                homelab (데이터만)
     ↓                              ↓
각자 로컬 클론    →    PostgreSQL + ChromaDB 동일 서버 접속
```

코드는 Git으로 각자 관리, DB는 homelab 서버 하나를 팀 전원이 바라본다. `.env`에 접속 정보를 공유하면 로컬에 DB 설치 없이 바로 개발 시작 가능.

**서버에 직접 붙어서 작업하지 않는다.** 여러 명이 같은 파일을 동시에 수정하면 덮어씌워지고 이력 추적이 불가능하다.

---

## 개발 환경 설정

### 필수 환경 변수 (`.env`)
```
# Azure OpenAI (LLM + 임베딩 한 묶음)
AZURE_OPENAI_ENDPOINT=https://skep-ai-board-for-test-foundry.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_MODEL=gpt-5.1-chat-ai-board-test
EMBEDDING_MODEL=text-embedding-3-small-ai-board-test

# DB (homelab 의 경우 cpia-pg.<도메인> Cloudflare Tunnel 통해 접속, 자세한 절차는 README)
POSTGRES_URL=postgresql://cpia:<password>@localhost:5532/cpia
CHROMA_HOST=localhost
CHROMA_PORT=5533
```

### homelab Docker Compose 실행 (인프라 담당자)
```bash
cd infra
docker-compose up -d
# PostgreSQL :5432, ChromaDB :8000 오픈 확인
```

### Python 파이프라인 로컬 실행
```bash
cd pipeline
pip install -r requirements.txt
cp .env.example .env  # DB 접속 정보 입력
python main.py 20250925
```

### Next.js 로컬 실행
```bash
cd web
npm install
cp .env.local.example .env.local  # DB 접속 정보 입력
npm run dev  # http://localhost:3000
```

---

## 협업 분담 (2인 확정안)

```
팀원 A (AI/Python):
  - pipeline/ 전체 (7개 Agent + graph.py + FastAPI + synthetic + checkpointer)
  - LLM 프롬프트 튜닝 (Azure OpenAI gpt-5.1, 후속 plan 에서 Forecaster·Optimizer 모델 결정)
  - ChromaDB 적재·검색 로직

팀원 B (프론트/인프라):
  - web/ 전체 (Next.js Dashboard + API Routes + H-i-L Modal)
  - infra/ 전체 (docker-compose + Postgres init/migration + Cloudflare Tunnel)
  - 디자인 시안 적용 (design/CPIA_기획서_v7.1.html 기반)
  - 데모 시연 화면·전환 폴리싱

공통:
  - Phase 0 합의 3종 문서 (state.py / postgres.md / api-contract.md)
  - 데모 시나리오 리허설 (D-Day 1주 전 시작)
```

**상세 분담·우선순위·주차별 마일스톤:** `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`

---

## Phase 0 — 코드 전에 둘이 함께 결정할 것 (5/14~5/16)

아래 세 가지는 병렬 개발 시작 전에 반드시 합의해야 합니다. 합의 없이 각자 개발하면 합칠 때 충돌합니다.

### 1. `pipeline/state.py` — LangGraph State 스키마
Agent 간 공유 데이터 구조. `CPIAState` TypedDict 형태. work_content·conditions·requires_review 등 핵심 필드를 사전 확정.

### 2. `docs/schema/postgres.md` — PostgreSQL 테이블 구조
7개 테이블: `pipeline_runs`, `checkpoints`(LangGraph PostgresSaver), `daily_reports`, `forecasts`, `optimizer_advice`, `mapping_corrections`, `sites`.

### 3. `docs/architecture/api-contract.md` — 양방향 API 계약
- FastAPI (Next.js가 호출): `POST /run`, `POST /resume`, `GET /status/{run_id}`
- Next.js API Routes (Browser가 호출): `/api/sites`, `/api/pipeline/run`, `/api/hil/resume`, `/api/runs/[id]/*`

**완료 게이트:** 이 3개 문서가 git에 머지되고 둘 다 OK 사인할 때까지 노드 코드 작성 금지.

---

## 참고 데이터 파일

실제 샘플 (구조 파악용):
```
docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx
  ├── [1.출력인원 현황]  — 공종·BP사·금일 작업내용 텍스트 (work_content 원천)
  └── [4.물량]           — 공종·BP사·금일 물량 수치 (quantity 원천)

docs/sample/WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx
  ├── [Activity List(입력)] — WBS Activity ID 목록
  └── [잔여물량]            — 공종별 계획 완료일 + 잔여물량
```

---

*최종 수정: 2026-05-16 — A_Track 매핑 레이어 plan 반영 (Azure OpenAI gpt-5.1 + text-embedding-3-small 전환, ChromaDB `wbs_master`+`daily_activities` 두 컬렉션, PG `activity_master` 추가, A 는 로컬 Docker 로 PoC 진행 중 — homelab 은 대기·마이그레이션 예정)*
*이전 수정: 2026-05-14 — 2인 협업 확정안 (FastAPI 추가, H-i-L Dashboard 통합, 3주 압축 / 마감 2026-06-05, 브랜치 A_Track·B_Track 2개)*
