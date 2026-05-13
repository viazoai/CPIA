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

---

## 확정 기술 스택

| 레이어 | 기술 | 선택 이유 |
|--------|------|---------|
| AI 파이프라인 | Python + LangGraph | H-i-L interrupt·조건 분기 지원 |
| LLM (파싱·매핑·보고서) | Claude Sonnet 4.6 | 구조화 추출에 충분한 성능 |
| LLM (진단·조언) | Claude Opus 4.7 | 맥락 판단·추론 필요 구간 |
| 임베딩 | OpenAI text-embedding-3-small | 한국어 건설 도메인 텍스트 처리 |
| Vector DB | ChromaDB (서버 모드) | 유사도 검색, homelab Docker로 팀 공유 |
| 관계형 DB | PostgreSQL | 파이프라인 결과 저장, 대시보드 데이터 소스 |
| 프론트엔드 | Next.js (React) | AI 코드 생성 품질, API Routes로 별도 API 서버 불필요 |
| 인프라 | homelab Docker Compose | 팀원 공유 DB 서버, Cloudflare Tunnel로 외부 접속 |

**FastAPI 없음:** Python 파이프라인은 "실행해서 PostgreSQL에 결과를 쓰는 스크립트". Next.js API Routes가 DB를 읽어 React에 데이터를 제공.

---

## 아키텍처

```
[작업일보 파일 드롭]
        ↓
[Python LangGraph 파이프라인]
  Collector → Parser → Mapper ─[H-i-L 1]─ Atomizer
                                               ↓
                                    Reporter ─ Forecaster ─[H-i-L 2]─ Optimizer
        ↓ 결과 저장
[PostgreSQL]  +  [ChromaDB]
        ↓ 데이터 조회
[Next.js API Routes]
        ↓
[React 대시보드]
  Layer 1: 6개 현장 전체 현황 카드
  Layer 2: 현장 상세 + 생산성 진단 + Optimizer 조언
```

---

## 폴더 구조

```
01_AI Design Project/
│
├── CLAUDE.md                   ← 이 파일
│
├── pipeline/                   ← Python 파이프라인 (LangGraph)
│   ├── agents/
│   │   ├── collector.py
│   │   ├── parser.py
│   │   ├── mapper.py
│   │   ├── atomizer.py
│   │   ├── reporter.py
│   │   ├── forecaster.py
│   │   └── optimizer.py
│   ├── state.py                ← 팀 합의 필요: Agent 간 공유 데이터 구조
│   ├── graph.py                ← LangGraph 파이프라인 조립
│   ├── main.py                 ← 파이프라인 실행 진입점
│   └── requirements.txt
│
├── web/                        ← Next.js 프론트엔드
│   ├── app/
│   │   ├── page.tsx            ← Layer 1: 전체 현장 현황
│   │   ├── sites/[id]/
│   │   │   └── page.tsx        ← Layer 2: 현장 상세
│   │   └── api/
│   │       ├── sites/route.ts  ← 현장 목록 API
│   │       ├── forecast/route.ts
│   │       └── pipeline/route.ts ← 파이프라인 실행 트리거
│   └── package.json
│
├── infra/                      ← homelab 인프라 설정
│   └── docker-compose.yml      ← PostgreSQL + ChromaDB
│
├── data/
│   ├── synthetic_history/      ← Vector DB cold start용 가상 이력
│   ├── mock_sites.json         ← Dashboard Layer 1용 5개 더미 현장
│   └── input/YYYYMMDD/         ← 작업일보 드롭 폴더
│
├── docs/
│   ├── architecture/
│   │   ├── stack.md
│   │   └── api.md              ← TODO: Next.js API 엔드포인트 계약
│   └── schema/
│       └── db.md               ← TODO: PostgreSQL 테이블 스키마
│
└── planning/                   ← 기획 문서 (참고용)
    └── CPIA_PoC_실행계획_v2.md
```

---

## Agent 역할 요약

| Agent | 입력 | 출력 | LLM |
|-------|------|------|-----|
| Collector | 파일 경로 | 시트별 원문 텍스트 | 없음 |
| Parser | 원문 텍스트 + WBS 공종 목록 | 구조화 JSON | Sonnet 4.6 |
| Mapper | Parser JSON + WBS 코드 목록 | WBS 매핑 완료 JSON | Sonnet 4.6 |
| Atomizer | Mapper JSON | ChromaDB 적재 | 없음 (임베딩만) |
| Reporter | Mapper JSON | 통합 Daily Report (MD) + PostgreSQL 저장 | Sonnet 4.6 |
| Forecaster | Mapper JSON + ChromaDB 유사 이력 | 공종별 생산성 진단 + PostgreSQL 저장 | Opus 4.7 |
| Optimizer | Forecaster 결과 + ChromaDB 과거 패턴 | 맥락 기반 조언 + PostgreSQL 저장 | Opus 4.7 |

**H-i-L 포인트 2개:**
- H-i-L 1 (Mapper 이후): 확신도 낮은 매핑 항목 담당자 검토·수정
- H-i-L 2 (Forecaster 이후): PM이 Optimizer 조언 받을 공종 선택

---

## 협업 방식

### 코드 — GitHub

**레포:** https://github.com/viazoai/CPIA

```
main          ← 동작하는 것만 머지
feat/parser   ← 각자 에이전트별 브랜치
feat/mapper
feat/forecaster
feat/dashboard
```

각자 브랜치에서 개발 → PR → 리뷰 후 main 머지. 에이전트 하나 완성될 때마다 PR.

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
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
POSTGRES_URL=postgresql://user:password@homelab-host:5432/cpia
CHROMA_HOST=homelab-host
CHROMA_PORT=8000
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

## 협업 분담 (잠정안)

```
팀원 A: Collector + Parser + Mapper
팀원 B: Atomizer + Forecaster + Optimizer
팀원 C: Next.js 대시보드 + infra Docker Compose
공통:   state.py 스키마 합의 + DB 스키마 합의 + API 계약
```

---

## Phase 0 — 코드 전에 팀이 함께 결정해야 할 것

아래 세 가지는 병렬 개발 시작 전에 반드시 합의해야 합니다. 합의 없이 각자 개발하면 합칠 때 충돌합니다.

### 1. `pipeline/state.py` — Agent 간 데이터 인터페이스
각 Agent가 주고받는 데이터 구조. 팀 전원이 리뷰하고 확정.

### 2. `docs/schema/db.md` — PostgreSQL 테이블 구조
Reporter·Forecaster·Optimizer가 저장하는 결과와 Next.js가 읽는 데이터의 테이블·컬럼 정의.

### 3. `docs/architecture/api.md` — Next.js API 엔드포인트 계약
React 화면이 언제 어떤 데이터를 요청하는지. 프론트엔드가 mock으로 먼저 개발할 수 있게 해줌.

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

*최종 수정: 2026-05-13*
