# CPIA 개발 여정 & 아키텍처 결정 가이드

> CPIA가 **기획 → PoC 실행계획 → PRD(아키텍처·폴더구조 포함) → LangGraph 설계 → Phase 0 합의 → 구현 → 감사 → 배포 → 시연 준비**를
> 어떤 순서와 판단으로 거쳐왔는지 정리한 문서입니다. 새 팀원이 코드보다 먼저 이 흐름과 결정의 이유를 파악하도록
> 만들었습니다. 각 단계가 어떤 **일반적인 개발 방법론**에 해당하는지도 괄호로 덧붙였습니다.

| # | 단계명 (일반 개발 방법론 기준) | 이 프로젝트의 산출물 |
|---|---|---|
| 1 | **기획 단계** (Ideation) | 기획서 v1~v8 |
| 2 | **계획 수립 단계** (Planning / Scoping) | PoC 실행계획 v1→v2 |
| 3 | **요구사항 정의 단계** (Requirements Definition, PRD) | 2인 협업 설계 문서 |
| 4 | **아키텍처·상세 설계 단계** (Architecture & Detailed Design) | LangGraph 그래프 구조 |
| 5 | **인터페이스 설계 단계** (Interface Design / Contract Freeze) | state.py·postgres.md·api-contract.md |
| 6 | **개발 프로세스 정의 단계** (Process & Tooling) | superpowers 워크플로우 |
| 7 | **구현·검증 단계** (Implementation & QA) | 파이프라인 구현, E2E 감사, mock 데이터 검증 |
| 8 | **배포 단계** (Deployment / Ops) | homelab → AWS 마이그레이션, Makefile 배포 체계 |

---

## 1. 기획 단계 (기획서)

`design/CPIA_기획서_v1~v8.md` 로 버전이 계속 갱신되며 방향이 잡혔습니다. v5(서사 흐름 재구성) → v6(경영진 피드백 반영, 전략적 AX 관점 재프레이밍) → v7 → v8(랜딩 캡처 통합) 순으로 "왜 이 프로젝트를 하는가"라는 비전이 다듬어졌습니다. 아직 기술적 결정은 거의 없고, 문제 정의와 경영진 설득 논리가 중심입니다.
👉 [`01_기획_단계/CPIA_기획서_v8.md`](01_기획_단계/CPIA_기획서_v8.md)

(일반 방법론: **비전 문서(vision doc)** 단계 — 무엇을 왜 만드는지에 대한 합의 없이 실행계획으로 넘어가면 나중에 범위가 계속 흔들립니다.)

---

## 2. 계획 수립 단계 (PoC 실행계획 — 무엇을 만들지 좁히기)

기획서의 비전을 실제로 구현 가능한 범위로 좁힌 문서입니다(`planning/CPIA_PoC_실행계획_v1→v2.md`). 이 단계에서 결정된 것:

- **핵심 방식 전환**: 품셈(절대 기준) 비교 → Vector DB 기반 유사 이력 비교(상대 판단)
- **Agent 재설계**: Mapper 추가, Validator 제거, H-i-L을 2단계(Mapper 검토 + Trade 선택)로 설계
- **Dashboard 2레이어** 구조(전체 현황 + 상세) 확정
- **최초 기술 스택**: Python + LangGraph, Azure OpenAI, PostgreSQL, ChromaDB — 이 시점에 `CLAUDE.md`가 처음 작성되며 스택이 문서화됐습니다.

👉 [`02_계획수립_단계/CPIA_PoC_실행계획_v2.md`](02_계획수립_단계/CPIA_PoC_실행계획_v2.md)

(일반 방법론: **범위 확정(scoping) / 요구사항 정의** 단계 — 비전을 "이번에 만들 것"과 "안 만들 것"으로 가르는 단계입니다.)

---

## 3. 요구사항 정의 단계 (PRD — 2인 협업 설계, 아키텍처·폴더 구조 포함)

> **여기서부터 문서 제작 방식이 달라집니다.** 1·2번(기획서, PoC 실행계획)은 사람이 직접 작성한 문서였습니다.
> **3번(PRD)부터는 직접 작성이 아니라, Claude Code에 자연어로 요청하면 `superpowers` 플러그인이
> `brainstorming → writing-plans → design` 순서를 자동으로 밟아 도출한 산출물**입니다(6번 "개발 프로세스 정의 단계" 참고).
> 즉 사람은 "무엇을 원하는지"를 대화로 지시했고, 문서 자체는 그 대화의 결과로 생성됐습니다.

PoC 실행계획을 실행 가능한 계약 문서로 구체화한 것이 사실상의 PRD입니다. **아키텍처와 폴더 구조 결정은 이 단계에서 이뤄졌습니다** — 별도 단계가 아니라 PRD 문서 자체에 담겨 있습니다.

**어떤 식으로 지시했는가 (예시 프롬프트 — 실제 원문 그대로는 아니고, 당시 대화 맥락과 결과물을 근거로 재구성한 지시 패턴 예시입니다):**

```
/superpowers:brainstorming

팀이 3명에서 2명으로 줄었어. 나는 프론트+인프라(B), 다른 한 명은 AI/Python 파이프라인(A)을 맡을 거야.
6/13 경영진 시연까지 3주밖에 안 남았는데, 이 조건으로 CPIA를 어떻게 나눠서 진행할지 다시 설계해줘.
H-i-L을 대시보드에서 바로 처리할 수 있어야 하고, 두 사람이 서로 다른 폴더만 건드리도록 역할·폴더 구조·
일정(게이트 포함)을 정리한 계획 문서로 만들어줘.
```

첫 줄 `/superpowers:brainstorming`이 플러그인의 스킬을 명시적으로 호출하는 부분입니다 — Claude Code에서는 `/<스킬 이름>` 형태로 타이핑하면 해당 스킬이 바로 실행됩니다(플러그인이 활성화돼 있어야 하며, `/plugin`으로 `superpowers@claude-plugins-official`이 켜져 있는지 먼저 확인). 이 줄을 생략해도 superpowers의 `using-superpowers` 메타 스킬이 "창작성 작업이면 brainstorming부터"라는 규칙을 강제하기 때문에 자동으로 같은 스킬이 걸리지만, 새 팀원에게는 명시적으로 호출하는 방식이 더 이해하기 쉬워 예시에 포함했습니다.

이렇게 시작하면 Claude가 먼저 `brainstorming` 스킬로 범위·제약을 되묻고(예: "H-i-L 2단계를 유지할지, FastAPI를 새로 추가할지"), 합의된 답을 바탕으로 이후 단계(`writing-plans` 등)는 사람이 다시 명령어를 입력하지 않아도 자동으로 이어져 `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`가 생성되는 식입니다.

- **팀 재설계**: 3인 → 2인(A=AI/Python 파이프라인, B=프론트+인프라)
- **폴더 구조 = 트랙 경계**: `pipeline/`(A) vs `web/`+`infra/`(B)를 정확히 일치시켜, 각자 다른 폴더만 건드리므로 병합 충돌이 자연히 최소화되도록 설계
- **아키텍처 결정 뒤집기**: 원래 "FastAPI 없음" 방침이었으나, H-i-L을 대시보드 모달로 통합하려면 LangGraph의 `interrupt`/`resume`을 외부(Next.js)에서 트리거해야 해서 **FastAPI 얇은 래퍼 추가**로 번복. Next.js API Routes가 FastAPI를 프록시하는 BFF(Backend-for-Frontend) 패턴 채택
- **일정·게이트**: 3주 압축 일정(6/5 코드 동결 → 6/13 시연), GATE 1~4(5/19·5/22·5/29·6/5)와 게이트별 후퇴선(fallback)

👉 [`03_요구사항정의_단계/2026-05-14-cpia-2인-langgraph-협업-design.md`](03_요구사항정의_단계/2026-05-14-cpia-2인-langgraph-협업-design.md)

(일반 방법론: PRD 안에 아키텍처·팀 구조·폴더 경계가 함께 담기는 건 자연스럽습니다 — **"누가 무엇을 어떻게 만들 것인가"를 한 계약으로 묶는 것**이 PRD의 역할이고, 트랙=폴더 일치는 **코드 오너십 경계에 의한 충돌 최소화** 전략입니다.)

---

## 4. 아키텍처·상세 설계 단계 (LangGraph 파이프라인 설계)

*(이 단계 이후 산출물도 3번과 동일하게 Superpowers 방식으로 도출됨 — 아래는 결과 요약)*

**왜 LangGraph였나** (2단계에서 최초 결정): 파이프라인 중간에 사람 검토(H-i-L)가 끼어들고, 검토 후 이어서 실행돼야 합니다. LangGraph의 `interrupt`/checkpoint 기반 재개 기능이 이 요구를 그대로 지원해서 선택했습니다. PostgresSaver로 checkpoint를 저장하는 것도 같은 이유입니다.

**그래프 구조**:
```
Collector → Parser → Mapper ─[interrupt:hil_1]─ Atomizer
                                                   ↓
                                    Exporter ‖ Forecaster
                                                   ↓
                                   [auto-route: 4분면 고위험군]
                                                   ↓
                                               Optimizer
```

**그래프가 단순해진 과정**: 2단계(PoC 실행계획)에서는 H-i-L이 2포인트(Mapper 검토 + Trade 선택)로 설계됐습니다. 이후 5/17 시연 시나리오 확정 시점에 "경영진 시연 흐름을 단축"하기 위해 2차 H-i-L을 **Forecaster 4분면 중 고위험군 자동 라우팅**으로 대체하고 H-i-L을 1단계로 줄였습니다. 백엔드의 `interrupt:hil_2` 노드는 코드상 제거하지 않고 우선순위에서만 뺐습니다(필요 시 재도입 가능).

👉 [`04_아키텍처설계_단계/CLAUDE.md`](04_아키텍처설계_단계/CLAUDE.md) (그래프 구조·H-i-L 단순화 노트 원본)

(일반 방법론: 데드라인 아래 기능을 걷어내되 되살릴 수 있게 남겨두는 것은 **스코프 컷(scope cutting) + 가역적 결정 우선(reversible decisions first)**. 파이프라인을 얇게라도 먼저 끝까지 연결한 뒤 점진적으로 실제 로직으로 교체해간 진행 방식은 **워킹 스켈레톤(Walking Skeleton) / 트레이서 불릿(Tracer Bullet)** 패턴입니다.)

---

## 5. 인터페이스 설계 단계 (Phase 0 합의 — 코드 작성 전 계약 고정)

*(Superpowers 방식으로 도출된 산출물)*

PRD가 정한 아키텍처를 실제 구현 가능한 스키마로 굳힌 3종 문서: `pipeline/state.py`(LangGraph State), `docs/schema/postgres.md`(테이블 7개), `docs/architecture/api-contract.md`(API 계약). 이 3개가 머지되기 전까지는 "노드 코드 작성 금지" 게이트를 뒀습니다.

👉 [`05_인터페이스설계_단계/api-contract.md`](05_인터페이스설계_단계/api-contract.md)

(일반 방법론: **ADR(Architecture Decision Record)** 및 **인터페이스 우선 설계(contract-first design)** — 여러 사람이 동시에 짤 때 인터페이스가 코드보다 먼저 고정돼야 합칠 때 안 깨집니다.)

---

## 6. 개발 프로세스 정의 단계 (Claude Code 워크플로우)

구현 단계부터 `superpowers`, `frontend-design`, `awesome-statusline` 플러그인을 사용했습니다. 핵심은 `superpowers`입니다 — 하나의 플러그인 안에 `brainstorming`, `writing-plans`, `executing-plans`, `requesting-code-review` 등 여러 스킬이 번들로 들어있고, 아래 순서로 이어집니다.

```
① brainstorming        ← 사람이 "이거 만들자"라고 대화를 직접 시작해야 트리거됨
        ↓
② writing-plans (+ 필요시 design 문서)   ┐  ②부터는 Claude가 상황을 판단해
        ↓                                 │  자동으로 다음 스킬을 호출한다
③ executing-plans / subagent-driven-dev  │  (사람이 매번 명령어를 입력하지 않음)
        ↓                                 │
④ requesting-code-review                 ┘
```

이 사이클의 결과물이 `docs/superpowers/plans/`·`docs/superpowers/specs/`에 쌓인 plan(무엇을)↔design(왜) 문서 페어입니다.
👉 [`06_개발프로세스_단계/2026-05-17-cpia-e2e-audit-plan.md`](06_개발프로세스_단계/2026-05-17-cpia-e2e-audit-plan.md) ↔ [`06_개발프로세스_단계/2026-05-17-cpia-e2e-audit-design.md`](06_개발프로세스_단계/2026-05-17-cpia-e2e-audit-design.md)

(일반 방법론: plan/design을 코드와 분리해 남기는 건 구글식 **디자인 독(design doc) 문화** — "왜"를 코드가 아니라 문서에 남겨야 나중에 이유를 재구성할 필요가 없습니다.)

---

## 7. 구현·검증 단계 (구현 로드맵 & 현재 상태)

**7-1. 파이프라인 Agent 구현 순서 (5/17~6/1)**: LangGraph 노드를 한 번에 다 만들지 않고, 그래프 순서를 따라 하나씩 붙였습니다 — `Collector`(파일 수집, 초기엔 스텁) → `Parser`(xlsx 시트 1~4 실제 파싱: BP 인원 현황·작업 배분·장비 배분·물량) → `Mapper`(임베딩 검색 + LLM rerank로 WBS 매핑) → `Atomizer`(Chroma `daily_activities` 적재) → `Exporter`(업체별 → 통합 작업일보) 와 `Forecaster`(집계 → 분류 → rerank 3단계 모듈)를 병렬로 → `Optimizer`(LLM 기반 조언). 각 Agent는 자기 계약(2·5번에서 고정한 스키마)만 지키면 되므로, 앞 Agent가 미완성이어도 mock 데이터로 뒷단을 먼저 개발할 수 있었습니다(4번의 "워킹 스켈레톤" 전략의 실제 적용).

**7-2. 5/17 E2E 감사**: 원안 대비 10단계 매트릭스로 전체 그래프를 검증. `Collector`/`Exporter` 미구현, `H-i-L 1`이 state 필드만 있는 placeholder였던 드리프트를 발견 → 같은 날 대부분 흡수(구현 완료), 회귀 테스트 183→197개로 증가.

**7-3. 5/23 Mock 데이터 재설계 + 검증 (5-phase 단일 스펙)**: "시연에서 보여줄 숫자가 그럴듯한가"를 검증하기 위해 1년치(24-04-11~25-09-24) mock 데이터를 F3 분포(ramp+plateau+late-rise)·작업상황(conditions)·5% outlier 기준으로 재설계 → 로컬 PG/Chroma에 적재 → Mapper 이후 전 단계(atomizer/forecaster/hil_2/optimizer/exporter)를 배치 실행 → **Playwright로 FE 전 페이지를 스크린샷 검증**(콘솔 에러 0건 확인)까지 한 사이클로 처리했습니다. 이 검증 통과가 곧 8번(배포)의 AWS 마이그레이션 트리거였습니다.

**7-4. 6/1~11 폴리싱**: parser 헤더 기반 멀티포맷 대응, export/report 재설계(L7 그룹핑, HIL 리뷰보드), 시트2·3 헤더/유령열 fix로 이어졌습니다.

계획 대비 실제 구현 상태를 주기적으로 재점검하는 것(7-2, 7-3)은 애자일의 **inspect & adapt**에 해당합니다.

6/5 코드 동결 이후 지금은 **기능 구현이 끝나고 6/13(추정) 경영진 시연을 앞둔 용어·카피·수치 정합성 폴리싱 단계**입니다.
👉 [`07_구현검증_단계/2026-05-17-cpia-e2e-audit-report.md`](07_구현검증_단계/2026-05-17-cpia-e2e-audit-report.md)

---

## 8. 배포 단계 (homelab → AWS, Docker Compose 운영)

**8-1. 최초 계획**: 2번(계획 수립) 단계에서부터 인프라는 **homelab Docker Compose**로 잡혔습니다 — `postgres`·`chroma`·`cloudflared`·`adminer`·`web` 5개 컨테이너를 한 묶음(`infra/docker-compose.yml`)으로 띄우고, 팀원 전원이 이 서버 하나를 공유. 외부(경영진) 접속은 서버를 인터넷에 직접 노출하지 않고 **Cloudflare Tunnel**로만 열었습니다 — 모든 컨테이너 포트는 `127.0.0.1`에만 바인딩.

**8-2. 실제로는 로컬 우선 개발**: homelab이 준비되는 동안 A트랙(파이프라인)은 자기 PC의 로컬 Docker로 먼저 PoC를 진행했고("A의 PoC 완료 시점에 데이터 마이그레이션" 방침), homelab은 그동안 대기 상태로 유지했습니다.

**8-3. AWS로 배포처 전환**: 7-3의 mock 데이터 검증이 통과한 뒤(5/23), homelab이 아니라 **AWS 서버로 마이그레이션**했습니다. `scripts/aws_backup_and_migrate.py`(pg_dump/Chroma 스냅샷 → AWS reset → 로컬 dump restore) 오케스트레이터를 만들어 **로컬에서 검증된 상태를 그대로 AWS에 복제**하는 절차를 스크립트화했고, 이 마이그레이션 자체를 별도 phase로 미루지 않고 검증 스펙 안의 마지막 단계(Phase E)로 못 박았습니다 — 사용자 지시: *"페이즈 다른곳으로 넘기는거 절대 안돼 이번 스펙에 모든걸 다룰거야 마이그까지"*. 이후 AWS 환경에서도 동일한 UI 스크린샷 검증(E.4 baseline, E.6 final)을 다시 돌려 로컬과 동일한 결과인지 재확인했습니다.

**8-4. 배포 자동화 (Makefile)**: 반복되는 배포 실수(이미지 안 갱신, 캐시 무한 누적)를 막기 위해 루트 `Makefile`로 명령을 표준화했습니다.

| 명령 | 포트 | 용도 |
|---|---|---|
| `make dev` | 5536 | 개발용 HMR (코드 수정 즉시 반영) |
| `make dev2` | 5537 | 2번째 개발 서버 (병렬 작업용) |
| `make prod` | 5535 | 시연/프로덕션 — 이미지 없으면 자동 빌드 |
| `make build` / `make build-pipeline` | 5535 | web·pipeline 이미지 **캐시 사용** 재빌드 + `up -d --force-recreate` |
| `make rebuild` / `make rebuild-pipeline` | 5535 | 캐시 꼬임 의심 시에만 — `--no-cache` 전체 재빌드 |

`docker-compose restart` 단독 사용은 금지 규칙으로 못 박았습니다(이미지가 갱신되지 않아 옛 코드가 그대로 떠 있는 상태가 됨). 과거 `--no-cache`가 기본값이던 시절 빌드마다 ~1.6GB 레이어가 새로 쌓여 빌드 캐시가 30GB+ 누적된 적이 있어(`docker builder prune`으로 회수), 이후 "캐시 사용이 기본, no-cache는 예외"로 정책을 바꿨습니다.

👉 [`08_배포_단계/README.md`](08_배포_단계/README.md)

(일반 방법론: 백업 후 진행하는 마이그레이션은 **롤백 가능한 배포(reversible deployment)**, Makefile로 배포 명령을 고정하는 것은 **배포 파이프라인 표준화**, dev(5536/5537)·prod(5535) 포트를 분리한 것은 **환경 분리(environment separation)**에 해당합니다. "검증 없이는 배포 없다"는 원칙(7-3 통과 후에만 8-3 진행)은 CI/CD의 **게이트형 배포(gated deployment)**와 같은 발상입니다.)
