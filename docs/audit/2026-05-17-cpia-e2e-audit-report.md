# CPIA E2E Audit Report (2026-05-17)

> Spec: `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md`
> Plan: `docs/superpowers/plans/2026-05-17-cpia-e2e-audit-plan.md`
> Branch: A_Track HEAD `1acf71e`
> 회귀 baseline (Task 0 Step 0.2): 183 passed in 569.85s — `pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -p no:slow --tb=no -q`. 직전 cycle (PR #15 머지 시점) 의 183 과 동일 — 본 audit 가 시작될 때 회귀 0 건. (참고: `-p no:slow` 는 slow plugin 부재로 무효, 실제로는 unit + slow + integration + E2E 전부 통과)
> PM 원안: `planning/CPIA_PoC_실행계획_v2.md`

---

## 0. Executive Summary

### 일치도 분포 (10 단계 매트릭스 §1)

| 라벨 | 단계 수 | 단계 |
|------|---------|------|
| 일치 | 4 | Mapper / Atomizer / HIL 2 / (Forecaster 부분) |
| 일치 (skip) | 1 | Parser (시뮬에서 우회, 코드 존재) |
| 부분 일치 | 1 | Optimizer (advice 강도 PM 원안 대비 약함) |
| 미구현 | 2 | Collector (0 byte) / Reporter (0 byte) |
| 드리프트 | 1 | HIL 1 (state placeholder only) |
| 의도된 변경 | 1 | Dashboard (Streamlit → Next.js, §3 marked) |

### 컨셉 v1→v2 cross-cutting (§2)

6 변경 모두 일치 또는 의도된 확대. **품셈 → Vector RAG 전환 = 완전 발현**.

### Synthetic 변동/회복 패턴 (§2.7)

원안 4 변동 중 3 일치 (우천/야간/장비대기/정상) + 1 드리프트 (병행작업 부재). 회복 2 패턴 모두 일치. 추가 룰 3 (자재미입고/돌관/장비대기 2일차).

### 시뮬 4 건 결과 (§4)

- 시나리오 1 (PM 데모 재현): risky 2 → Optimizer 2 row. PM 원안 권고 vs LLM = 일치 1 / 부분 2 / 드리프트 1
- 시나리오 2 (우천): risk=주의 ✓
- 시나리오 3 (돌관): risk=이상 ✗ (주의 발현, today_prod ≈ baseline → fixture bug §5.2)
- 시나리오 4 (cold_start): spec §7.4 가정과 다른 path 발현 (§5.4)
- 결정성 검증: 결정론 컬럼 100% 일치 (rerun)

### 추가 발견 드리프트 9건 (§5)

assessment vs risk 분기 / fixture productivity_ratio bug / assessment "정상" bias / cold_start 2 path / Optimizer 권고 강도 종속 / PM 원안 의미 일치도 / date off-by-one / plan deviation 5건 / recovery_distribution conditions 필터

### 우선순위 #1~#5 후속 cycle 후보 (drift-backlog)

1. **Reporter 구현** (PoC 성공 기준 #1)
2. **Forecaster assessment 결정 path 정정** (§5.1+5.3+5.5 통합)
3. **시뮬 fixture productivity_ratio bug** (§5.2)
4. **HIL 1 구현** (PoC 성공 기준 #2)
5. **Collector + 파일 드롭 + main.py**

defer: 8건 (D-1 ~ D-8)

상세: `docs/audit/2026-05-17-cpia-drift-backlog.md`

### 회귀 baseline

`183 passed in 569.85s` (audit 시작 시점 = 직전 cycle PR #15 머지 직후와 동일).

### Azure 비용 실측 추정

$0.10~$0.20 (시뮬 4 + rerun 1 = 약 13 LLM 호출, gpt-5.1 단가 추정). spec §7 예상 ~$0.3 대비 -33~67%.

---

## 1. 단계별 매트릭스

### 1.1 Collector

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "지정 폴더(`input/YYYYMMDD/`)를 감시하여 새 파일을 감지하고 텍스트를 추출 ... Excel: `openpyxl`로 시트 전체 셀 텍스트 추출 / 텍스트: 직접 읽기" (`planning/CPIA_PoC_실행계획_v2.md` §4 Week 2) |
| 실 구현 fact | `$ wc -l pipeline/agents/collector.py` → `0 pipeline/agents/collector.py` |
| 일치도 | **미구현** |
| 영향도 | high (PoC 데모 입력 진입점 부재 — 파일 드롭 → Parser 흐름 불가, 시뮬에서 `synthetic_daily_report` CLI 로 우회 중) |
| 우선순위 권고 | Task 4 에서 확정 (예상 #3 또는 #4) |

### 1.2 Parser

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "비정형 텍스트에서 공종별 [인원·물량·작업내용·조건]을 추출하여 JSON으로 변환 ... Claude Sonnet 4.6 호출. **작업내용(work_content) 텍스트 보존 필수** — Atomizer 임베딩의 핵심 원천" (§4 Week 2) |
| 실 구현 fact | `$ wc -l pipeline/agents/parser.py` → `306 pipeline/agents/parser.py`. `pipeline/state.py:30 Activity.work_content: str` 정의. (LLM = Azure gpt-5.1 — 의도된 변경 §3 marked) |
| 일치도 | 일치 (skip) — 코드 존재 + work_content 필드 보존. 본 audit 시뮬은 `synthetic_daily_report` 가 Parser 우회하여 Activity 직접 주입 → 실 호출 검증 X |
| 영향도 | high |
| 우선순위 권고 | defer (코드 존재, 별도 통합 테스트 필요) |

### 1.3 Mapper

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "작업일보의 작업 내용 기술을 공정표 WBS 코드에 의미 기반으로 매핑 ... 확신도 낮은 항목은 `requires_review: true` 플래그" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/mapper.py` → `393`. `map_activity` (line 208) + `_prorate_mh` 헬퍼 + `requires_review: True` (line 241) + Chroma WBS query (line 251) 모두 존재. |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer |

### 1.4 HIL 1 (Mapper 직후) — drift 1호

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일. LangGraph `interrupt()` → 담당자 수정 → `corrections.json` 누적" (§4 Week 3). PoC 성공 기준 #2: "Mapper: 의미 기반 자동 매핑 + H-i-L 1 검증·수정 피드백 루프" (§5). |
| 실 구현 fact | `$ grep -n "hil_1\|interrupt\|waiting_hil" pipeline/state.py pipeline/graph.py pipeline/agents/mapper.py`<br>→ `pipeline/state.py:118 hil_1_corrections: dict` / `pipeline/state.py:133 "waiting_hil_1"` (state 자리만 정의)<br>→ `pipeline/graph.py:15 interrupt import` / `graph.py:172 selected = interrupt({"risky_groups": payload_groups})` (hil_2 만)<br>→ `pipeline/agents/mapper.py` 의 interrupt 호출 = 0 건<br>→ `pipeline/graph.py` build_graph 에 hil_1_node 부재, mapper → atomizer 로 직접 연결 |
| 일치도 | **드리프트 (placeholder)** — state 자리만 있고 노드/interrupt 미구현 |
| 영향도 | high (PoC 성공 기준 #2 미충족, 데모 시연 단계 누락, 사용자 인식 ↔ 실 코드 mismatch) |
| 우선순위 권고 | Task 4 #1 또는 #2 후보 |

### 1.5 Atomizer

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "오늘 작업 기록을 Vector DB에 임베딩·적재 — 이후 Forecaster·Optimizer의 검색 대상 ... Sheet4(수치)와 Sheet1(텍스트)를 날짜+업체 키로 JOIN하여 하나의 레코드로 구성" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/atomizer.py` → `118`. `atomize` 함수 (line 62) + `_make_doc_id` sha256 (line 39) + ChromaClient (line 110~111) 적재. 시뮬 1~3 raw 의 Activity → Chroma row 적재 정상 확인. |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer |

### 1.6 Reporter — drift

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일. Mapper 확정 JSON → Claude Sonnet 4.6 → 통합 Daily Report 생성 + history.csv 업데이트" (§4 Week 3). PoC 성공 기준 #1: "작업일보 파일 투입 → 통합 Daily Report 자동 생성" (§5). |
| 실 구현 fact | `$ wc -l pipeline/agents/reporter.py` → `0 pipeline/agents/reporter.py` |
| 일치도 | **미구현** |
| 영향도 | high (PoC 성공 기준 #1 미충족, 경영진 데모의 핵심 산출물 부재) |
| 우선순위 권고 | Task 4 #1 후보 (PoC 성공 기준 직접 영향) |

### 1.7 Forecaster

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "오늘 생산성이 과거 유사 상황 대비 적정한지 진단하고 리스크 공종 목록 생성 ... ChromaDB에서 유사 조건 과거 기록 5건 조회 ... Claude Opus 4.7 ... Cold Start: Vector DB에 유사 기록이 3건 미만이면 WBS Man-Hour 기반 계획 생산성을 fallback" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/forecaster/*.py` → agent.py 276, aggregate.py 119, classify.py 114, prompt.py 134, rerank.py 50, synthetic.py 189, constants.py 8, `__init__.py` 8. 시뮬 1~4 raw §1.2 의 forecast row 결과: ratio 와 today_productivity 비례 깨짐 (시뮬 2 ratio=0.8 → today_prod=74.26 vs 시뮬 1 ratio=0.45 → 69.62 — 0.45 가 더 낮은 값이어야 정상이나 거꾸로). |
| 일치도 | 부분 — RAG path 동작 (시뮬 결과 reasoning 에 "유사 4건 평균" 인용 ✓). 단 productivity_ratio fixture 의도 vs today_prod 불일치 = §5 추가 발견 |
| 영향도 | high |
| 우선순위 권고 | defer 코드 / Task 4 후보 (시나리오 fine-tuning 별 cycle) |

### 1.8 HIL 2 (Forecaster → Optimizer)

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "v1과 동일하되 역할 변경: 리스크 공종 목록 표시 + PM이 **조언 대상 공종** 선택 (최적화 의뢰 공종 선택)" (§4 Week 3) |
| 실 구현 fact | `$ grep -n "hil_2_node\|interrupt" pipeline/graph.py` → graph.py:71 hil_2_node + graph.py:172 `selected = interrupt({"risky_groups": payload_groups})`. 시뮬 1 raw §1.3 의 `[HIL-2 INTERRUPT] risky_groups: 2` 확인. `[AUTO] --auto-select-all → resume keys` 정상 작동. |
| 일치도 | 일치 |
| 영향도 | high |
| 우선순위 권고 | defer |

### 1.9 Optimizer

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "PM이 선택한 공종의 저하 원인을 과거 패턴 기반으로 진단하고, 회복 시나리오와 구체적 조언을 제시 ... ChromaDB에서 '이 공종이 비슷하게 저하됐던 과거 상황' 검색 ... Claude Opus 4.7이 원인·회복 패턴·권고사항 종합" (§4 Week 3) |
| 실 구현 fact | `$ wc -l pipeline/agents/optimizer/*.py` → agent.py 156, prompt.py 315, retrieve.py 161. 시뮬 1 raw §1.4 의 advice 2 row + rank 1~4 + recovery_distribution = 정상 동작. 단 PM 원안 §2 권고사항 예시 ("타워크레인 스케줄 확인 필수" 등 강한 액션) vs 실 LLM advice ("표기 반복 여부 확인" 등 약한 점검) **부분 일치 + 일부 드리프트** (시뮬 1 raw §3 의 의미 비교 표 참조). |
| 일치도 | 부분 — 코드 흐름 일치, advice 강도 PM 원안 대비 약함 |
| 영향도 | high (경영진 시연 시 LLM 권고 강도가 약하면 데모 임팩트 저하) |
| 우선순위 권고 | Task 4 후보 (assessment="정상" bias 해소 시 자동 개선 가능성) |

### 1.10 Dashboard

| 컬럼 | 내용 |
|------|------|
| 원안 의도 | "Layer 1: 6개 현장 현황 카드 (공정률·생산성 이상 공종·보고 상태) / Layer 2: 현장 상세 (S-curve·생산성 진단 결과·Optimizer 조언·보고서 링크) ... Streamlit" (§4 Week 4) |
| 실 구현 fact | `$ ls web/app/components/` → home/ landing/ reports/ review/ tasks/ dashboard/ charts/ + 공통 (NotificationBell / Sidebar / TopBar / PersonaToggle 등). web/ = Next.js + TypeScript (의도된 변경 §3 marked). B_Track 진행 중. |
| 일치도 | **의도된 변경** (Streamlit → Next.js, §3 marked) — 구현 중 (B_Track 활발) |
| 영향도 | med (B_Track 트랙 별도 진행, audit 범위 외) |
| 우선순위 권고 | defer (B_Track 별도 audit cycle 필요) |

---

## 2. 컨셉 v1→v2 cross-cutting

PM 원안 §0 표의 6 변경이 현 구현에 반영됐는지.

| # | v1→v2 변경 | 검증 명령 + 결과 | 일치도 |
|---|------------|------------------|--------|
| 1 | 품셈 → 현장 실적 누적 | `$ grep -rn "품셈\|pumssem" pipeline/` → **0 hits** | 일치 (완전 제거) |
| 2 | Forecaster 판단: 실측÷품셈 → 오늘 vs 유사 과거 비교 | `pipeline/agents/forecaster/agent.py:16 from pipeline.chroma_client import ChromaClient`<br>+ `agent.py:23 fetch_chroma_actual`<br>+ `agent.py:113 similar_cases_raw = _format_chroma_result(rag_result)` | 일치 (RAG path 동작) |
| 3 | Optimizer: 인원 재배치 수치 → 맥락 조언 | `pipeline/agents/optimizer/prompt.py:39` 시스템 프롬프트: `"수치 계산 (인원 재배치 명령 등) 금지. 맥락 기반 조언만."` | 일치 (prompt level 명시 금지) |
| 4 | Atomizer 추가 (Vector DB 적재) | `pipeline/agents/atomizer.py` 118 lines, `atomize` 함수 (line 62) + ChromaClient (line 110) | 일치 |
| 5 | ChromaDB + 임베딩 추가 | `pipeline/chroma_client.py` HttpClient (line 21), Azure `text-embedding-3-small` 1536d (의도된 변경 §3) | 일치 (인프라만 Azure 로 변경 = §3 marked) |
| 6 | Synthetic history 30일 (v1 = 불필요) | Task 1 Step 1.2 결과: `synthetic_v2 row 수: 2430` (90일 × 27 그룹 — 의도된 확장 §3) | 의도된 변경 (확대) |

→ 컨셉 v1→v2 6 변경 모두 일치 또는 의도된 확대. v1→v2 본 의도 = "품셈 → Vector RAG" 전환 = 완전 발현.

### 2.7 Synthetic 변동/회복 패턴 매트릭스 (drift 후보 #7 + #8)

`pipeline/agents/optimizer/synthetic_v2.py:108~140` 의 룰 vs PM 원안 §3.B 4 변동 + 2 회복 패턴.

| 원안 패턴 (§3.B) | synthetic_v2.py 룰 | 일치도 |
|------------------|--------------------|--------|
| 우천일 -15~25% | line 115: `delta -= rng.uniform(0.15, 0.25)` | **일치** ✓ |
| 야간 연장 50% 초과 시 익일 -10% | 룰 6 (line 91~): `last_incident="야간연장"` → 익일 fatigue_factor ×0.90 | 일치 (피로 +10% 적용, 50% 임계값은 미구현 — PoC 단순화) |
| 장비 대기 -20~35% | 룰 1 (line 116~117): `delta -= rng.uniform(0.20, 0.35)` | **일치** ✓ |
| 병행작업 겹침 -10~20% | `$ grep "병행\|parallel\|동시" synthetic_v2.py` → **0 hits** | **드리프트** (룰 부재) |
| 정상일 ±5% | line 121: `delta += rng.uniform(-0.05, 0.05)` | **일치** ✓ |
| 장비 대기 → 다음날 80% 정상 복귀 | 룰 2 (line 76~78): `if rng.random() < 0.8: incident="정상"` | **일치** ✓ |
| 우천 연속 2일 → 3일차 +10% 만회 | 룰 4 (line 110): `rain_streak_compensation = 1.10 if state["rain_streak"] >= 2` | **일치** ✓ |

**원안 부재 / synthetic_v2 추가 룰 (의도된 확장 가능성):**
- 자재미입고 -10~20% + 익일 50% 복귀 (룰 5)
- 돌관 -10~20% + workers ×1.3 (룰 7)
- 장비 대기 2일차 → 익일 30% 만회 (룰 3)

→ 원안 4 변동 패턴 중 **3 일치 + 1 드리프트 (병행작업)**, 2 회복 패턴 모두 일치, 추가 룰 3 건. drift 후보 #7 #8 검증 결과 = 거의 일치 + 병행작업 1건 누락.

---

## 3. 의도된 변경 (drift 제외, marked)

본 audit 에서 다음 4 항목은 의도된 변경으로 marked, 매트릭스 일치도 컬럼에 "의도된 변경" 표기, drift backlog 에 포함 X.

| # | 변경 | 원안 | 현 구현 | 의도 |
|---|------|------|---------|------|
| 1 | LLM 인프라 | Claude Sonnet 4.6 + Opus 4.7 | Azure OpenAI `gpt-5.1-chat-ai-board-test` + `gpt-5-mini` | 사용자/회사 Azure 계정 제약 |
| 2 | Dashboard 스택 | Streamlit | Next.js + TypeScript (`web/` = B_Track 트랙) | 디자인 시스템 / UI 정밀도 |
| 3 | Persistence | JSON 파일 (corrections / history / forecast / optimizer / mock_sites) | PostgreSQL 16 + Chroma (port 8000) | 확장성 / 동시성 / 운영 안정성 |
| 4 | Synthetic 스케일 | 30일치 (180~270 row) | 90일 × 27 그룹 = 2,430 row | baseline 통계 의미 확보 (n ≥ 30 per 그룹) |

→ 의도된 변경 4 건 marked 완료. drift backlog 에 포함 X.

---

## 4. 시뮬 시나리오 4 건 결과

각 시나리오 raw = `docs/audit/raw/scenario-<N>-<run_id>.md`. Azure 비용 실측 추정 = $0.10~$0.20 (stdout token 카운트 미노출, 호출 회수 × gpt-5.1 단가 추정).

### 4.1 시나리오 1 — PM 원안 데모 재현 (3 회사)

- **run_id:** `ca7d820c-a02c-4094-afa3-6fa7cb765dc4`
- **fixture (plan deviation 5건 fix 적용):** 남웅건설 철콘 m3 0.45 / 세보엠이씨 일반공조 m2 1.0 / 창원기전 전등 ea 1.0
- **결과:**
  - forecast row 3 (남웅 today_prod=69.62 / 세보 2.51 / 창원 0.59)
  - risk: 남웅 주의 / 세보 정상 / 창원 주의
  - assessment: 모두 정상 (LLM bias)
  - HIL 2 risky_groups=2 (남웅 + 창원)
  - Optimizer advice 2 row (남웅 정상 path + 창원 cold_start)
  - recovery_distribution (남웅): `{d+1:2, d+5:1, d+6:1, not_recovered:1}`
- **검증 포인트 충족:** PM 원안 §2 권고사항 패턴 vs 실 LLM advice = 일치 1 / 부분 2 / 드리프트 1 (raw §3)
- **결정성 검증 (rerun run_id `0a175854`):** 결정론 컬럼 100% 일치, 비결정론은 diagnosis/reasoning 어휘만 차이

### 4.2 시나리오 2 — 주의 (우천 -20%)

- **run_id:** `c88e103d-058c-40f8-a3a1-9810f0047ac9`
- **fixture:** 남웅건설 철콘 m3 0.8 우천 1.0
- **결과:** today_prod=74.26 / risk=주의 / assessment=정상 / Optimizer 정상 path / recovery 시뮬 1 과 동일
- **검증 포인트 충족:** risk=주의 ✓ / conditions=["맑음","우천"] ✓ / Optimizer 정상 path ✓
- **추가 발견:** today_prod 74.26 = baseline 의 2.39× → §5.2

### 4.3 시나리오 3 — 이상 (돌관 -45% × 1.3)

- **run_id:** `8ee67861-d627-4c88-ac4f-62208539726b`
- **fixture:** 남웅건설 철콘 m3 0.45 돌관 1.3
- **결과:** today_prod=32.13 / risk=**주의** (이상 미발현) / assessment=정상 / LLM diagnosis "돌관 작업으로 평시 대비 높은 실적" (의도 반대)
- **검증 포인트 충족:** risk=이상 ✗ (주의 발현) / recovery_distribution JSONB ✓
- **추가 발견:** today_prod ≈ baseline 31.07 → §5.2, date off-by-one (CLI 9/29 → stdout 9/28) → §5.7

### 4.4 시나리오 4 — cold_start (신규 회사)

- **run_id:** `0dc69cbc-ed64-4a27-9f9b-adec01a24093`
- **fixture:** 신규건설 토목공사 m3 1.0 정상
- **결과:** today_qty=0 / today_prod=0 / risk=null / assessment=null / reasoning="데이터 부족 — 판단 보류" / Optimizer 미진입
- **검증 포인트 충족:** spec §7.4 가정 (baseline=None hil_2 분기) 미발현. 다른 path (Forecaster today_qty=0 → risk=null) 발현 → §5.4 cold_start 2 path 발견

---

## 5. 추가 발견 드리프트

spec §4 의 사전 식별 8건 외에 시뮬 4건 raw + 매트릭스 작성 중 새로 드러난 9건.

### 5.1 forecast_assessment vs risk_level 분기 일관성

- 원안 의도: Forecaster 가 단일 판단 결과 산출 (§4 Week 3 "오늘 생산성이 ... 적정한지 판단")
- 시뮬 fact: 시뮬 1/2/3 모두 `assessment=정상` 인데 `risk_level=주의` (시뮬 1 raw §1.2). 두 컬럼이 서로 다른 결정 path 사용 — risk_level=임계값 결정론, assessment=LLM 자유텍스트 (또는 highly stable bias).
- 영향도: high (PM 원안의 "정상이 아닌 게 정상" 의 분기 의도가 모호)
- 우선순위 권고: #2 (Forecaster 코드 검토)

### 5.2 시뮬 fixture productivity_ratio ↔ today_productivity 불일치

- 시뮬 1 (남웅 ratio=0.45, workers=1.0): today_prod=69.62 (baseline 31.07 의 **2.24배**)
- 시뮬 2 (남웅 ratio=0.80, workers=1.0): today_prod=74.26 (baseline 의 **2.39배**)
- 시뮬 3 (남웅 ratio=0.45, workers=1.3): today_prod=32.13 (baseline 의 **+3.4%**, 거의 동일)
- → ratio 가 작을수록 today_prod 가 낮아져야 하는데 시뮬 1/2 비교 시 0.45 가 0.80 보다 today_prod 낮음 (반대). 시뮬 3 는 baseline 과 거의 동일. fixture 의 today_qty 산출 또는 baseline_qty 산출 로직 잠재 bug.
- 영향도: high (Forecaster 정확도 검증 신뢰성 직결, 본 audit 시뮬 raw 의 진위 의문)
- 우선순위 권고: #3 (시뮬 fine-tuning cycle 별도)

### 5.3 assessment "정상" highly stable bias

- 시뮬 1/2/3 + rerun 모두 assessment="정상" — fixture 다양성 (0.45 / 0.80 / 돌관) 무관.
- 가설 A: LLM (gpt-5.1) 의 systematic "정상" bias
- 가설 B: Forecaster 의 결정론 코드 path 가 항상 "정상" 산출 (assessment 컬럼 자체 무력)
- 검증 필요 (코드 grep: forecaster agent.py 의 assessment 결정 path)
- 영향도: high (assessment 컬럼이 모든 시나리오에서 동일하면 의미 X)
- 우선순위 권고: #2 (Forecaster 코드 검토)

### 5.4 cold_start 2 path 발견

- Path A (신규 회사): 시뮬 4 = 신규건설|토목공사 → activity_master 미존재 → baseline_qty=0 → today_qty=0 → risk=null → risky 0건 → Optimizer 미진입
- Path B (기존 회사 + baseline=None): 시뮬 1 창원기전 → activity_master 존재 but Chroma 의 baseline_value=None → hil_2_node:122 cold_start_no_baseline → risky 주의 → Optimizer cold_start path
- → spec §7.4 가 정의한 cold_start 는 Path B 인데, fixture "신규 회사" 는 Path A 발현. spec 정정 또는 fixture 정정 필요.
- 영향도: med (개념 정합성 영향, 시연 영향 작음)
- 우선순위 권고: defer (Forecaster 코드 검토 시 함께)

### 5.5 Optimizer 권고 강도 ↔ forecast_assessment 종속

- 시뮬 1 남웅 (assessment=정상): Optimizer advice = "장비대기 표기 반복 여부 확인" 류 약한 점검 권고
- 시뮬 2 우천: "우천 표기 영향 제한적" + 약한 권고
- PM 원안 §2 예시 (의도): "타워크레인 스케줄 확인 필수" + "야간 연장 검토" 강한 액션
- → assessment="정상" 으로 LLM 입력되면 약한 권고 산출. PM 원안의 "이상 → 강한 권고" 흐름 미발현.
- 영향도: high (경영진 시연 임팩트 직결)
- 우선순위 권고: #2 종속 (assessment 결정 path 정정 시 자연 해소)

### 5.6 PM 원안 §2 권고사항 패턴 vs 실 LLM advice 의미 일치도

- 시뮬 1 raw §3 의미 비교 표: 일치 1 / 부분 2 / 드리프트 1 (4 권고 중)
- 영향도: low (LLM 비결정 + 의미는 일부 일치)
- 우선순위 권고: defer

### 5.7 date off-by-one 잠재 이슈

- 시뮬 3: CLI `--date 2025-09-29` 입력, stdout `date=2025-09-28` 출력
- 시뮬 1/2/4: CLI 입력 = stdout 일치 (off-by-one 미발현)
- 일관성 X — date 파싱 or sites/pipeline_runs INSERT timezone 이슈 가능
- 영향도: med (PG row 의 report_date 정확성)
- 우선순위 권고: defer (재현 시 확인)

### 5.8 plan deviation 5건 (본 audit 가 발견)

| # | plan 표기 | 실제 | 분류 |
|---|----------|------|------|
| 1 | Chroma port 8765 | 8000 | plan 작성 시 grep 부족 |
| 2 | PG port 5433 | 5432 | plan 작성 시 .env 미확인 |
| 3 | CLI `--report-date` | `--date` | plan 작성 시 CLI argparse 미확인 |
| 4 | fixture `세보건설/거푸집공사`, `한일건설/콘크리트타설` | activity_master 미존재 | plan 작성 시 PG 데이터 미확인 |
| 5 | pytest `-p no:slow` | slow plugin 부재로 무효 | pytest marker 와 plugin 옵션 혼동 |

- 영향도: low (audit 실 진행에 영향, fix 후 재현 가능)
- 우선순위 권고: defer (audit 가 self-correct, plan 자체 정정 X)

### 5.9 recovery_distribution 동일 (시뮬 1/2/3) — case retrieval conditions 필터 검증 필요

- 시뮬 1 (장비대기), 시뮬 2 (우천), 시뮬 3 (돌관) 모두 동일 recovery_distribution `{d+1:2, d+5:1, d+6:1, not_recovered:1}`
- 가설: `fetch_degradation_cases` 가 conditions 필터 적용 X 가능성. 또는 남웅 철콘 그룹의 case 분포가 conditions 와 무관하게 균일.
- 영향도: med (Forecaster RAG 매칭 정확도 영향)
- 우선순위 권고: defer

---



---

## 6. Limitation

### 6.1 LLM 비결정성 컬럼

시나리오 1 결정성 검증 (Task 1 Step 1.13, rerun run_id `0a175854`) 결과:

| 분류 | 컬럼 | 근거 |
|------|------|------|
| 결정론 | `today_productivity` | 산술 |
| 결정론 | `risk_level` | 임계값 분기 (forecaster classify.py) |
| 결정론 (또는 highly stable LLM) | `assessment` | rerun 100% 일치 — LLM bias 매우 일관 or 결정론 코드 path. 단일 fixture 만 검증, 일반화 한계 |
| 결정론 | `recovery_distribution` | optimizer agent.py `_compute_recovery_distribution` 코드단 산출 |
| 비결정론 | `reasoning` / `diagnosis` / `recommendations` | LLM 자유텍스트 |

비결정론 컬럼의 audit 평가는 "의미적 일치" 기준 — 동일 fixture 의 다회 호출 어휘/순서 차이는 normal, 의미 차이는 anomaly.

### 6.2 시뮬 1 회 한계

시나리오 1 만 rerun 으로 결정성 검증 (2 회), 시나리오 2/3/4 는 단일 호출. 비결정 컬럼의 통계적 신뢰는 미확보 — 정성 평가만.

### 6.3 audit 범위 외 (별 cycle)

- 갭 자체의 구현 (Reporter / HIL 1 / Collector 등) — drift-backlog 의 #1, #4, #5
- B_Track Next.js Dashboard 의 internal audit — 별 cycle (의도된 변경 §3 marked 만)
- 코드 스타일 / 한자 / cosmetic — 별 채널
- 시나리오 fine-tuning (drift-backlog #3) — 별 cycle, fix 후 시뮬 재현 가능

### 6.4 본 audit 자체의 plan deviation 5건 (audit fact, §5.8)

본 audit 의 plan (`docs/superpowers/plans/2026-05-17-cpia-e2e-audit-plan.md`) 작성 시 grep / .env / argparse / PG 데이터 확인 부족으로 발생한 deviation 이 5건 (port / CLI / fixture / pytest). audit 실행자 (본 sessions) 가 self-correct 로 진행했으나, plan 의 "Real research before guess" 룰 강화 필요 — 다음 plan 부터 사전 grep + .env 확인 step 명시.
