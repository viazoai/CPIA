# CPIA 경영진 시연 시나리오 v1

> 작성일: 2026-05-31 · 작성자: B_Track · 시연 D-Day: **2026-06-13(추정)** · 코드 동결: **2026-06-05(목)**
>
> 본 문서는 **시연 흐름(Storyboard)** 과 **그를 뒷받침할 테스트 환경(Test Harness)** 의 두 축으로 구성된다. 시연은 두 개의 굵직한 데모로 나뉜다.
>
> 1. **Demo A — 자동화 시연 (작업일보 → 통합 작업일보)**: AS-IS 수작업 2~3시간을 TO-BE 5분으로 압축하는 파이프라인.
> 2. **Demo B — 분석·예측 시연 (Report + Dashboard)**: 누적된 작업일보를 기반으로 진단·예측·최적화하는 의사결정 화면.

---

## 0. 메타: 시연 환경·페르소나·시간 배분

| 항목 | 내용 |
|------|------|
| 청중 | SK ecoplant 경영진(임원~본부장 급), 7~12명 추정 |
| 발표 시간 | 본 발표 **15분** + Q&A 10분 (조정 가능) |
| 데모 환경 | 노트북 1대 → 외부 프로젝터 / 공유 화면. Cloudflare Tunnel 경유 homelab `cpia.<도메인>` (포트 5535) |
| 발표자 | B (화면 시연·진행) + A (질문 대응) |
| 백업 | (1) 로컬 `npm run dev` (5536) 로 fallback (2) 사전 녹화 1~2분 클립 |
| 상태 토글 | `?demo=replay` query 로 fixture 모드 강제 — 실 파이프라인 장애 시 즉시 전환 |

**시연 흐름 (15분 슬롯 기준 — 화면 시연은 2분 압축, 나머지는 슬라이드·멘트·Q&A):**

| 분 | 단계 | 화면 |
|---|------|------|
| 0:00 ~ 4:00 | 인트로 (문제 정의·아키텍처·차별점) | 발표 슬라이드 3장 |
| 4:00 ~ 5:00 | **Demo A — 업로드·자동화 (≤ 60초)** | `/tasks` → 업로드 Modal → 진행 게이지 → `/review` → 확정 → `/tasks` 복귀 → 완료 → `/export` → Excel |
| 5:00 ~ 6:00 | **Demo B — 분석·의사결정 (≤ 60초)** | `/reports` (3섹션 빠른 훑기) → `/dashboard` (Performance → Impact) |
| 6:00 ~ 13:00 | 정량 효과·로드맵·확장 계획 | 발표 슬라이드 |
| 13:00 ~ 15:00 | Q&A 도입 | — |

> **압축 원칙**: 화면 시연은 "AI 가 진짜 5분 안에 끝낸다" 의 증명만 짧고 강하게. 디테일 설명은 시연 전후 슬라이드로 분리. 시연 중 멘트는 1문장 단위로 짧게.

---

## 1. Demo A — 자동화 시연 (작업일보 → 통합 작업일보)

### 1-1. 시연 목적
- "AS-IS PM 1인이 2~3시간 들여 엑셀 짜깁기 → TO-BE 드롭 한 번에 5분" 을 **눈앞에서** 보여준다.
- H-i-L 1 (Mapper Review) 한 번만 노출해 "AI 와 사람이 같이 만든다"는 메시지를 각인.

### 1-2. 발표자 동작 시퀀스 (Storyboard) — **≤ 60초 압축 확정안**

화면 구성: `/tasks` 는 좌(일자별 처리) · 중(Agent Workflow 8단계 게이지) · 우(단계별 건 목록) 3-컬럼.

| # | 시각 | 동작 | 화면·UI 변화 | 발표 멘트(1문장) |
|---|------|------|--------------|------------------|
| A-1 | 0:00 | `/tasks` 접속 (이미 열어둠) | 좌측에 최근 일자 카드, 중앙에 8단계 게이지 | "여기가 작업 현황 화면입니다." |
| A-2 | 0:02 | 우상단 **`작업일보 업로드`** 클릭 | Upload Modal 오픈 | (무언) |
| A-3 | 0:04 | 사전 준비된 폴더에서 **10개 파일 드래그** | 파일 리스트 + 용량 | "오늘 받은 10개." |
| A-4 | 0:08 | **제출** 클릭 | data/upload 저장 → Modal 닫힘 → 좌측 새 카드 자동 선택 | (무언) |
| A-5 | 0:10 | 게이지 자동 진행 (Collector 2s → Parser 2.5s → Mapper 3s) | 중앙 게이지 순차 차오름 | "읽고, 정형화하고, WBS 매핑." |
| A-6 | 0:18 | HIL Review 에서 정지 | HIL 블록 점멸, 우측 "확정 필요 N건" | "애매한 건 사람에게." |
| A-7 | 0:21 | HIL 블록 클릭 | `/review` 라우팅 | (무언) |
| A-8 | 0:23 | `/review` 화면 진입 | 우측에 미확정 카드 N장 | "AI 추천 매핑이 카드로." |
| A-9 | 0:26 | **`모두 AI 추천대로 확정`** 클릭 | "매핑이 완료되었습니다" Modal 1.0초 → `/tasks` 자동 복귀 | "일괄 확정." |
| A-10 | 0:30 | Phase 2 자동 진행 (Atomizer 2s → Exporter 2.5s → Forecaster 2s → Optimizer 2s) | 게이지 4개 순차 차오름 | "적재, 통합본, 진단, 최적화." |
| A-11 | 0:39 | 모든 게이지 완료 | 좌측 카드 status: completed | "끝." |
| A-12 | 0:42 | 상단 네비 → `/export` | 통합 작업일보 카드 + `Excel 출력` 버튼 | "통합본 결과." |
| A-13 | 0:48 | **`Excel 출력`** 클릭 | xlsx 다운로드 | "그대로 결재. PM 3시간 → 1분." |
| 종료 | 0:55 | — | — | — |

**시퀀스 총 소요: 약 55초 (목표 ≤ 60초).** 압축 keys:
- HIL 모달은 1.0초만 (기존 1.5초에서 단축)
- 각 Agent stage 진행 2~3초 (기존 5~12초에서 대폭 단축)
- 멘트는 1문장만 — 디테일은 시연 전후 슬라이드

### 1-3. 핵심 시연 포인트 (절대 빠지면 안 되는 것)
1. **드래그 → 제출** 의 단순함 (마우스 동선 최소)
2. **HIL Review 블록 → 정정 → 복귀** 의 매끄러운 전환 — Modal 트랜지션과 라우팅이 끊김 없어야 함
3. **게이지 차오름 → 정지 → 재개** 가 시각적으로 자연스러워야 함 (각 단계 5~12초)
4. **Excel 다운로드** 가 실제 파일로 열려야 함 (빈 파일·404 절대 금지)
5. **5분 타이머** 를 화면 한 켠에 띄울지 검토 (시간 압축의 시각화 — 보류)

### 1-4. 잠재 리스크
| 리스크 | 대응 |
|--------|------|
| 실 파이프라인이 H-i-L Interrupt 발생 안 함 / Modal 안 뜸 | fixture review_cards 로 강제 시뮬레이션 (이미 `/api/mock/review` 존재) |
| Parser LLM 타임아웃 (Azure OpenAI 5~30s) | `?demo=replay` 로 progress 시뮬레이션 fallback |
| 업로드 폴더 권한 (uid 1001) | 이미 `chmod 777` 적용 완료 |
| Excel 다운로드가 빈 파일 | `docs/sample/통합작업일보_M15X*xlsx` 를 정적 서빙 (실제 파이프라인 출력 대기 중일 때) |

---

## 2. Demo B — 분석·예측 시연 (Report → 관리자 Dashboard)

### 2-1. 시연 목적
- **앞 절반 (`/reports`)**: 단일 현장(M15X Ph-3 IBL) 의 생산성 진단 → 리스크/대안 → 공기예측 시나리오를 순차로 설명.
- **뒷 절반 (`/dashboard`)**: 관리자만 접근 가능한 전사 분석 화면 — 현장 생산성과 Agent 가 만든 정량 Impact 를 클로저로 제시.
- 메시지: "절대 기준(품셈) 이 아니라 우리 현장 이력 대비 상대 판단" + "Agent 도입의 정량 효과는 이미 측정 가능".

### 2-2. 발표자 동작 시퀀스 (Storyboard) — **≤ 60초 압축 확정안**

#### Phase 1: `/reports` — 단일 현장 분석 (≤ 35초)

| # | 시각 | 동작 | 화면·UI | 발표 멘트(1문장) |
|---|------|------|--------|------------------|
| B-1 | 0:00 | 상단 네비 → `/reports` 접속 | M15X Ph-3 IBL 자동 선택 | "방금 그 현장의 리포트." |
| B-2 | 0:03 | **§ 01 생산성 진단** | 공종별 생산성 % + 진단 텍스트 | "UT 배관, 우리 현장 이력 대비 18% 저하." |
| B-3 | 0:10 | **§ 02 리스크/대안** + 빨간 분면 WP 1건 클릭 | 4분면 + Optimizer 결과 (진단·유사사례·권고) | "Impact 큰 위험 WP, AI 가 유사 과거 3건 가져와 권고." |
| B-4 | 0:22 | **§ 03 공기단축 시나리오** 스크롤 | 회복 vs 미회복 곡선 | "액션 하면 9일 회복 — 8/12 → 8/3." |

#### Phase 2: `/dashboard` — 관리자용 전사 분석 (≤ 25초)

| # | 시각 | 동작 | 화면·UI | 발표 멘트(1문장) |
|---|------|------|--------|------------------|
| B-5 | 0:32 | 상단 네비 → `/dashboard` | Performance 탭 (기본) — Fleet KPI + 6개 sparkline | "관리자 전사 화면 — 6개 현장 동시 모니터링, 빨간 줄 하나가 그 현장." |
| B-6 | 0:42 | **Impact 탭** 클릭 | Agent 누적 효과 KPI (FTE·시간·AI 대체율) | "Agent 도입 30일 — FTE N명, M시간 절감." |
| B-7 | 0:55 | 종료 멘트 | (화면 유지) | "이게 CPIA 가 만드는 변화입니다." |

**시퀀스 총 소요: 약 60초 (목표 ≤ 60초).** 압축 keys:
- § 01·§ 02·§ 03 각 7~12초 (긴 설명 X — 한 문장씩만)
- Dashboard 는 Performance·Impact 두 탭만 — hover·세부 클릭은 생략
- 멘트가 화면보다 약간 앞서거나 같이 진행 (멈춤 없음)

### 2-3. 핵심 시연 포인트
1. **빨간 → 빨간 → 빨간 일관성**: § 01 진단(저생산성 공종) → § 02 빨간 분면 WP → § 03 9일 차이 → Dashboard Performance 의 빨간 sparkline 이 모두 같은 현장(M15X Ph-3 IBL)을 가리켜야 함
2. **유사 과거 사례** 가 보일 것 (벡터 DB 차별점 — 절대 빠지면 안 되는 1슬라이드)
3. **회복 일수(9일)** / **FTE 절감** 같은 정량 숫자를 멘트에 박을 것
4. Dashboard Impact 탭의 숫자가 클로저 — KPI 카드가 빈약하면 임팩트 절반

### 2-4. 잠재 리스크
| 리스크 | 대응 |
|--------|------|
| Forecaster·Optimizer LLM 미정 (CLAUDE.md TBD) | mock_report.json fixture 로 안정 시연. 실모델은 PoC v2 로 미루기 |
| 4분면 산점도 데이터가 단조로움 | mock_review_cards / mock_report 의 분면 분포 사전 점검 (H5) |
| Optimizer 결과 카드가 너무 김 | 이미 overflow-y-auto 적용됨 (이번 세션 fix) |
| Dashboard Impact KPI 숫자가 빈약 | mock_dashboard.json 의 Impact KPI 사전 튜닝 (H11) |
| `/reports` 진입 시 현장 미선택 상태 | M15X Ph-3 IBL 사전 자동 선택 (H10) |

---

## 3. 테스트 환경 (Test Harness) 설계 옵션

> **확정안 (2026-05-31): 옵션 2 — Hybrid.** 업로드는 실제 동작, 진행 막대·H-i-L Modal·Exporter 결과는 fixture. Demo B 전체 fixture.

### 옵션 1 — **Full Mock** (안전 100%, 임팩트 60%)
- 모든 화면이 `/api/mock/*` fixture 만 호출. 업로드도 시뮬레이션 (파일 저장 X, 진행 막대만 가짜로 흐름).
- 장점: 네트워크·LLM 장애 zero. 리허설 그대로 본방 보장.
- 단점: "정말 동작하는가?" 의심 받기 쉬움. 업로드 라이브감 X.

### 옵션 2 — **Hybrid ✅ 확정** (안전 85%, 임팩트 85%)
- **Demo A 업로드 단계만 실제 동작** (파일 저장 → `data/upload/`).
- 파이프라인 진행 표시는 시간차 시뮬레이션 (Collector~Exporter 를 6~8초 간격으로 단계 점등).
- H-i-L Modal 은 fixture review_cards 로 띄움 (발표자가 1건 클릭 정정 → 다음 단계).
- Exporter 결과물은 `docs/sample/통합작업일보_*xlsx` 를 정적 서빙.
- Demo B 는 100% fixture (mock_sites.json + mock_report.json + mock_review_cards.json).
- 장점: "실제로 파일이 저장됐다" 를 보여줄 수 있음 + 안정성 확보.
- 단점: 진행 막대가 가짜라는 점은 비공개 (발표자가 "평균 60초" 멘트로 자연스럽게 봉합).

### 옵션 3 — **Full E2E** (안전 40%, 임팩트 100%)
- 업로드 → Collector → Parser(Azure GPT-5.1) → Mapper → Atomizer → Exporter 모두 실제 호출.
- Forecaster/Optimizer 는 fixture (모델 미정 상태).
- 장점: 진짜 5분, 진짜 H-i-L Interrupt. 가장 강력.
- 단점: Azure 타임아웃·rate limit·H-i-L 미발화 등 실패 변수 다수. 본방 사고 위험.

### 결정 변수
| 변수 | 옵션 1 | 옵션 2 | 옵션 3 |
|------|--------|--------|--------|
| Demo A 업로드 실제 저장 | X | O | O |
| H-i-L Modal | 가짜 | 가짜 (fixture) | 실제 interrupt |
| Parser/Mapper LLM 호출 | X | X | O |
| Exporter 산출물 | 정적 | 정적 | 실제 생성 |
| Forecaster/Optimizer | fixture | fixture | fixture (어차피 미구현) |
| 본방 실패 확률 (체감) | 5% | 15% | 50% |
| 리허설 횟수 권장 | 2회 | 4회 | 8회+ |

---

## 4. 시연 데이터 준비 체크리스트

### Demo A 용
- [ ] 업로드할 샘플 파일 세트 (5~10개) — `docs/sample/` 기반 변형본
  - 업체명·날짜만 바꿔 N개 사본 생성 (예: 중원ENG / 한신중공업 / 대림 등)
- [ ] H-i-L Modal 에 띄울 review_cards 2~3건 (확신도 낮음 시뮬레이션)
- [ ] Exporter 결과로 보여줄 **통합 작업일보 Excel 견본** 1장 (docs/sample 그대로 또는 데이트 셔플)
- [ ] 진행 막대 단계 간격 (Collector 5s / Parser 8s / Mapper 12s / Atomizer 5s / Exporter 10s) 튜닝

### Demo B 용
- [ ] `mock_sites.json` 의 M15X Ph-3 IBL 진단 수치(productivity 88, SPI 0.89, 지연 14d) 가 § 01 진단 텍스트와 일치하는지 검증
- [ ] `mock_report.json` 의 4분면 산점도 분포가 "빨간 분면에 WP 4개" 시나리오와 일치하는지 검증
- [ ] Optimizer 권고 카드 1건의 정량 숫자(공기 9일 회복) 가 사이트 카드의 `recovery_days` 와 일치하는지 검증
- [ ] § 03 공기단축 시나리오 곡선 데이터 유무 확인

### 환경
- [ ] `?demo=replay` query 토글 동작 확인 (없으면 추가 필요)
- [ ] homelab `cpia.<도메인>` Cloudflare Tunnel 정상 동작 확인
- [ ] 본방 1시간 전 컨테이너 재빌드·재기동 1회
- [ ] 백업 노트북 (5536 npm dev) 동기화

### 발표 준비
- [ ] 위 시퀀스 표를 기반으로 발표 대본 작성 (B 담당)
- [ ] D-Day 1주 전 리허설 (옵션 1 → 옵션 2 순서로 단계 상향)
- [ ] Q&A 예상 질문 10개 (정확도·비용·확장성·H-i-L 부하 등)

---

## 5. 결정 사항 (2026-05-31 확정)

| # | 항목 | 결정 |
|---|------|------|
| 1 | 시연 환경 | **옵션 2 — Hybrid** |
| 2 | Demo B § 03 공기단축 시나리오 | **포함** (회복 vs 미회복 곡선) |
| 3 | 백업 시연 영상 | **사전 녹화** (D-Day 3일 전) |
| 4 | 5분 타이머 화면 | 보류 — 리허설 후 재논의 |
| 5 | Q&A 화면 (청중 직접 조작) | 보류 — 본방 반응 보고 결정 |

---

## 6. Hybrid Harness — 구현 워크 아이템

> 옵션 2 확정에 따라 시연 직전까지 만들어야 할 코드·데이터·운영 작업. 우선순위 P0(필수)·P1(권장).
>
> Demo A 의 묘사된 시퀀스(A-1 ~ A-13)에서 도출된 갭이 H1~H4 의 정의 근거.

| ID | 우선순위 | 작업 | 관련 시퀀스 | 담당 | 비고 |
|----|---------|------|------------|------|------|
| H1 | P0 | **2-페이즈 진행 시뮬 엔진 (압축 cycle)** — 업로드 제출(A-4) 시점에 해당 일자의 stages 진행도를 클라이언트 상태로 override. **Phase 1**: Collector(2s)→Parser(2.5s)→Mapper(3s) 까지 채운 뒤 **HIL Review 에서 정지** (`waiting_hil:true`) — 총 7.5s. **Phase 2**: `/review` 확정 후 `/tasks` 복귀하면 Atomizer(2s)→Exporter(2.5s)→Forecaster(2s)→Optimizer(2s) 진행 재개 → 완료 — 총 8.5s. **두 phase 합 16초** 가 1분 압축 storyboard 의 핵심 예산. | A-4 ~ A-6, A-10 ~ A-11 | B | localStorage 또는 zustand. `/api/mock/agent-tasks/{date}` 응답을 시뮬 상태로 덮어쓰기. cycle time 을 const 로 빼서 리허설 중 조정 용이하게 |
| H2 | P0 | **Workflow 블록 클릭 → `/review` 라우팅** + **확정 후 1.0초 Modal → `/tasks` 자동 복귀** — (a) `AgentWorkflowList` 의 HIL Review 블록 클릭 시 `router.push("/review?from=tasks&date=...")` (b) `/review` "모두 AI 추천대로 확정" 클릭 시 **1.0초** "매핑이 완료되었습니다" Modal/Toast → 자동 `router.push("/tasks")` (c) 복귀 시 H1 시뮬 Phase 2 자동 트리거 | A-7, A-9, A-10 | B | 기존 컴포넌트 재활용. 라우팅·토스트만 추가. Modal 표시 시간 1.0초로 압축 |
| H3 | P0 | **Excel 정적 다운로드 라우트** — `/api/export/download?date=...` → `docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` 그대로 서빙 (Content-Disposition attachment) | A-13 | B | Node runtime, fs.readFile |
| H4 | P0 | **시연용 샘플 작업일보 10개 폴더 준비** — `docs/sample/업체작업일보_*.xlsm/xlsx` 를 업체명·날짜만 셔플해 N장. 데모용 디렉토리는 `planning/demo_inputs/YYYYMMDD/` | A-3 | B | 시연 당일 데스크탑에서 즉시 드래그 가능한 위치에 복사 |
| H5 | P0 | **Demo B `/reports` 데이터 일관성 점검** — § 01 진단(저생산성 공종) ↔ § 02 4분면 빨간 분면 WP ↔ Optimizer 권고의 정량 숫자(공기 9일 회복) ↔ § 03 곡선의 회복일이 모두 같은 현장(M15X Ph-3 IBL)·같은 수치를 가리키는지 검증 | B-2 ~ B-6 | B | mock_report.json·mock_sites.json·mock_simulation.json 정합성. 코드 수정 가능성 낮음, 데이터만 |
| H6 | P0 | **§ 03 공기단축 시나리오 컴포넌트** 데이터·렌더링 확인. 미존재 시 mock_simulation.json + 회복/미회복 라인 차트 추가 | B-6 | B | 현 reports/page.tsx 에 § 03 섹션 유무 확인부터 |
| H10 | P0 | **`/reports` 진입 시 M15X Ph-3 IBL 자동 선택** — 사이트 selector 가 있다면 default, 없다면 query param `?site=m15x-ph3-ibl` 으로 진입하도록 발표 매뉴얼화 | B-1 | B | 현 page.tsx 가 어떻게 사이트를 선택하는지 확인 후 결정 |
| H11 | P0 | **Dashboard Impact 탭 KPI 사전 튜닝** — mock_dashboard.json 의 Impact 누적 KPI (FTE 절감·시간 절감·AI 대체율) 가 클로저 메시지("FTE N명 절감, M시간 절감") 에 박힐 만큼 임팩트 있는 숫자인지 검증. 빈약하면 mock 수치 상향 | B-9 ~ B-10 | B | 6개 현장 합산 기준 — 현 mock_sites.json fte_saved 합 15.3, hours_saved 합 2155 |
| H7 | P1 | `?demo=replay` query 토글 — 실 API 실패 시 즉시 fixture 강제 | (전체) | B | 발표자 비상 스위치 |
| H8 | P1 | **백업 영상 사전 녹화** (Demo A 2분 + Demo B 1분) | (전체) | B | D-Day 3일 전 |
| H9 | P1 | 리허설 4회 (D-7, D-3, D-1, D-Day 아침) | (전체) | A+B | 매 회차 시나리오·멘트 폴리시 |

---

*최종 수정: 2026-05-31 — Demo A·B 각 ≤ 60초로 압축. Section 0 시간 배분 재할당(시연 2분 + 슬라이드 13분), Demo A 시퀀스 시각 표기·stage cycle 2~3초로 단축, Demo B § 01~§ 03 7~12초씩·Dashboard 2탭만, H1 cycle time 16초 총량·H2 Modal 1.0초로 동기화*
*이전 수정: 2026-05-31 — Demo A·B 스토리보드를 사용자 묘사대로 재작성 (HIL 블록 클릭→`/review`→확정→복귀 시퀀스 / `/reports` 3섹션→관리자 `/dashboard` 클로저). 워크 아이템 H1~H2 정의 정밀화, H10·H11 추가*
*이전 수정: 2026-05-31 — Hybrid 확정 + 워크 아이템 H1~H9 추가*
*이전 수정: 2026-05-31 — v1 초안 (B_Track 작성)*
