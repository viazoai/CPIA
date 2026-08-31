# CPIA E2E Audit Design

> **목적:** CPIA 현 구현이 PM 조형준 원안 v2 (`planning/CPIA_PoC_실행계획_v2.md`) 의 컨셉/단계/데이터 흐름과 단계별로 얼마나 일치하는지, 실 호출 시뮬레이션 + 코드 grep + spec 인용을 결합해 면밀히 검증하고 드리프트 우선순위를 합의한다. 이번 cycle 의 범위는 **검증 + 우선순위 산출까지** 이며, 갭 자체의 구현은 별 cycle.

---

## 0. 메타

| 항목 | 값 |
|------|-----|
| 작성일 | 2026-05-17 |
| 브랜치 | `A_Track` HEAD `c40c0be` (origin/main `c71241f` merged, A_Track 16 commit + cleanup commit) |
| 원안 참조 | `planning/CPIA_PoC_실행계획_v2.md` (PM 조형준, v2 변경 = 품셈 → Vector RAG 기반 상대 비교) |
| 기획서 참조 | `design/CPIA_기획서_v7.md` / `design/CPIA_기획서_v7.html` |
| 본 cycle 범위 | audit + drift 우선순위 backlog (구현 X) |
| 산출물 | `docs/audit/2026-05-17-cpia-e2e-audit-report.md` + `docs/audit/2026-05-17-cpia-drift-backlog.md` + `docs/audit/raw/<scenario>-<id>.md` |

---

## 1. 목적

### 1.1 왜 audit 가 지금 필요한가

- 직전 cycle 까지 5 agent (Parser / Mapper / Atomizer / Forecaster / Optimizer) + HIL 2 가 구현되어 E2E demo 1회 통과했지만, "어떤 부분이 PM 원안과 일치하고 어떤 부분이 드리프트인지" 가 단계별로 검증된 적이 없다.
- 직전 brainstorming 중 사용자가 "HIL 1 은 Mapper 뒤에 해놨었는데" 라고 인식했으나, 실 grep 결과 `pipeline/state.py:118` 의 `hil_1_corrections` 필드와 `pipeline/state.py:133` 의 `"waiting_hil_1"` 상태값만 정의되어 있고 `pipeline/graph.py` 의 어떤 빌더도 HIL 1 노드를 부르지 않음이 확인됨. 사용자 인식과 실 코드 사이의 갭이 audit 가 잡아야 할 1호 드리프트.
- 동시에 본 audit 가 **드리프트가 아닌 항목** (의도된 변경) 도 명확히 marked 해야 매트릭스가 정합. 의도된 변경 4 건은 §6 에 명시.

### 1.2 본 audit 의 산출 가치

- **단계별 일치도 매트릭스** — Collector → … → Dashboard 각 단계의 [원안 quote → 실 fact → 일치도 → 영향도 → 우선순위] 표.
- **드리프트 backlog** — 우선순위 기반 후속 cycle 진입 근거.
- **실 시뮬 raw 출력 부록** — Iron Law 3 요소 ($ 명령어 + 실 출력 + 결론) 준수, 재현 가능.

### 1.3 비목적

- 갭 자체의 구현 (Reporter / HIL 1 / Collector / 파일 드롭 / main.py 등) — 별 cycle.
- 코드 스타일 / 한자 / 코멘트 등 cosmetic 검토 — `feedback_no_chinese_chars.md` 등 별 채널에서 처리.
- 시나리오 fine-tuning (productivity_ratio 임계값 vs baseline 정합) — 별 cycle.

---

## 2. 스코프

### 2.1 포함

| 검증 대상 | 출처 (원안 §) |
|-----------|----------------|
| 7 agent 단계 (Collector / Parser / Mapper / Atomizer / Reporter / Forecaster / Optimizer) | §1 표 + §4 Week 2~3 |
| 2 HIL (HIL 1 Mapper / HIL 2 Forecaster) | §1 표 + §4 Week 3 |
| 컨셉 v1→v2 4 변경 (품셈 제거 / RAG 도입 / Forecaster 상대 비교 / Optimizer 맥락 조언) | §0 표 + §2 핵심 개념 |
| 데이터 흐름 (input 파일 드롭 / vector_db / synthetic_history / output reports) | §4 Week 1 공유 저장소 |
| Synthetic history 변동 패턴 (우천 -15~25%, 야간 익일 -10%, 장비 대기 -20~35%, 병행 -10~20%, 회복 패턴) | §3.B + §4 Week 1 |
| 데모 시나리오 7 단계 (Collector 5개 → Parser → Mapper → HIL 1 → Atomizer → Reporter → Forecaster → HIL 2 → Optimizer) | §2 데모 시나리오 |
| Dashboard 2 layer (Layer 1 전체 6 현장 + Layer 2 상세) | §4 Week 4 |

### 2.2 제외

- 갭 구현 자체
- 갭 backlog 외 cycle planning
- 의도된 변경의 사후 합리화 (이미 §6 에 marked, audit 매트릭스에서는 "의도된 변경" 컬럼으로 표시)

---

## 3. 검증 매트릭스 구조

### 3.1 단계별 흐름 (PM 원안 §4 전체 데이터 흐름 도식)

```
[Week 2]  Collector  → Parser
[Week 3]  Mapper → [HIL 1] → Atomizer → ┬─ Reporter
                                         └─ Forecaster → [HIL 2] → Optimizer
[Week 4]  Dashboard (Layer 1 + Layer 2)
```

### 3.2 단계별 매트릭스 컬럼

각 단계마다 다음 5 컬럼을 채운다.

| 컬럼 | 내용 |
|------|------|
| 원안 의도 (§quote) | `planning/CPIA_PoC_실행계획_v2.md` 인용 (verbatim, 줄 인용 포함) |
| 실 구현 fact | `$ grep ...` 또는 `$ pipeline/.venv/bin/python3 ...` 실 출력 quote |
| 일치도 | `일치` / `부분` / `미구현` / `드리프트` 중 하나 |
| 영향도 | `high` (PoC 데모 직접 영향) / `med` (Phase 2 영향) / `low` (cosmetic) |
| 우선순위 권고 | 후속 cycle 1~N 순위 또는 `defer` (별 cycle 으로 미루기 OK) |

### 3.3 일치도 정의

| 라벨 | 정의 |
|------|------|
| 일치 | 원안 의도와 실 구현이 의미적으로 동일. fact 가 직접 증거. |
| 부분 | 핵심 의도는 일치하나 일부 컴포넌트 누락 / placeholder. 예: hil_1_corrections state 필드만 정의됨. |
| 미구현 | 0 byte 또는 stub (TODO 만 있는 함수). 예: `pipeline/agents/collector.py` (0 byte). |
| 드리프트 | 의도된 변경 (§6 marked) 이 아닌 의도 외 차이. 예: PM 원안 = "Mapper 뒤 HIL 1" / 실 = "Mapper → Atomizer 로 바로 jump". |

`의도된 변경` 4 건 (§6) 은 일치도 컬럼에 `의도된 변경` 으로 별도 표기, 드리프트 분류 X.

---

## 4. 사전 식별 드리프트 후보 (audit 가 검증)

직전 grep 으로 이미 식별된 후보 8 건. audit 실행 시 fact + 영향도 + 우선순위 채워서 매트릭스 + backlog 에 반영.

| # | 후보 | 원안 § | 사전 grep fact | 예상 영향 |
|---|------|--------|---------------|----------|
| 1 | HIL 1 미아 (state 자리만, 노드/interrupt 미구현) | §1 표 + §4 Week 3 | `pipeline/state.py:118 hil_1_corrections` / `pipeline/state.py:133 waiting_hil_1` 존재. `grep "interrupt" pipeline/agents/mapper.py` = 0 hits. `pipeline/graph.py` 의 `build_graph` 가 `mapper → atomizer` 로 바로 연결. | high (PoC 데모 흐름 직접 영향, PM 원안 핵심 의사결정 포인트) |
| 2 | Collector 0 byte | §4 Week 2 | `wc -l pipeline/agents/collector.py` = 0 | high (입력 진입점 부재) |
| 3 | Reporter 0 byte | §4 Week 3 + §5 성공 기준 #1 | `wc -l pipeline/agents/reporter.py` = 0 | high (PoC 성공 기준 #1 "통합 Daily Report 자동 생성" 미충족) |
| 4 | `pipeline/main.py` 0 byte | (entry point 묵시적) | `wc -l pipeline/main.py` = 0 | med (현재 `synthetic_daily_report` CLI 로 우회 가능, 그러나 PM 원안 의 파일 드롭 흐름 미지원) |
| 5 | `pipeline/api.py` 0 byte | (FastAPI 묵시적) | `wc -l pipeline/api.py` = 0 | med (web/ Next.js 의 HIL 1/2 resume 연동 미정) |
| 6 | 파일 드롭 입력 방식 미구현 | §1 표 "입력 데이터" + §4 Week 2 Collector | input/YYYYMMDD/ 감시 로직 없음 | high (PoC 시연 시나리오 첫 단계) |
| 7 | Synthetic 변동 패턴 일치도 | §3.B | `pipeline/agents/optimizer/synthetic_v2.py` 7 룰 (state machine) — 원안 4 패턴 (우천 / 야간 / 장비대기 / 병행) 일치도 검증 필요 | med (Forecaster RAG 정확도 영향) |
| 8 | 회복 패턴 (PM 원안 "다음날 정상 복귀 80%, 우천 연속 2일 → 3일차 +10% 만회") | §3.B | `fetch_recovery_trajectory` 함수 존재 but 원안 회복 시나리오 패턴 fixture 검증 미실시 | med |

**audit 실행 시 추가 발견 가능성** — 시뮬 4 건 실 호출 중에 사전 식별되지 않은 드리프트가 더 드러날 수 있음. 매트릭스에 동등 컬럼으로 추가.

---

## 5. 컨셉 v1→v2 일치도 검증 (cross-cutting)

PM 원안 §0 표 의 6 변경이 현 구현에 반영됐는지. 단계별 매트릭스와 별도로 1 섹션.

| v1→v2 변경 | 원안 § | 현 구현 검증 방법 |
|-----------|--------|-------------------|
| 생산성 기준: 품셈 → 현장 실적 누적 | §0 표 | `grep -rn "품셈\|pumssem" pipeline/` = 0 hits 확인 |
| Forecaster 판단: 실측÷품셈 → 오늘 vs 유사 과거 비교 | §0 + §4 Week 3 | `pipeline/agents/forecaster/agent.py` 의 RAG 흐름 + Chroma 조회 path 확인 |
| Optimizer 역할: 인원 재배치 수치 → 맥락 조언 | §0 + §4 Week 3 | `pipeline/agents/optimizer/prompt.py` 시스템 프롬프트 + 출력 형식 확인 |
| Atomizer 추가 (Vector DB 적재) | §0 표 | `pipeline/agents/atomizer.py` 존재 + Chroma 적재 path 확인 |
| ChromaDB + 임베딩 추가 | §0 표 | `pipeline/chroma_client.py` + Azure embedding `text-embedding-3-small` 확인 |
| Synthetic history 30일 (v1 = 불필요) | §0 표 | synthetic_v2 2,430 row 적재 확인 (90일 × 27 그룹, 의도된 확대) |

---

## 6. 의도된 변경 (drift 제외, marked)

본 audit 에서 다음 4 항목은 **의도된 변경** 으로 marked, 일치도 매트릭스에서 `의도된 변경` 컬럼 표기. 드리프트 backlog 에 포함 X.

| # | 변경 | 원안 | 현 구현 | 의도 |
|---|------|------|---------|------|
| 1 | LLM 인프라 | Claude Sonnet 4.6 + Opus 4.7 | Azure OpenAI `gpt-5.1-chat-ai-board-test` + `gpt-5-mini` | 사용자/회사 Azure 계정 제약 |
| 2 | Dashboard 스택 | Streamlit | Next.js + TypeScript (`web/`) | B_Track 의 디자인 시스템 / UI 정밀도 |
| 3 | Persistence | JSON 파일 (corrections / history / forecast / optimizer / mock_sites) | PostgreSQL + Chroma | 확장성 / 동시성 / 운영 안정성 |
| 4 | Synthetic 스케일 | 30일치 (180~270 row) | 90일 × 27 그룹 = 2,430 row | baseline 통계 의미 확보 (n ≥ 30 그룹별) |

---

## 7. 시뮬 시나리오 4 건 (실 호출)

`synthetic_daily_report.py` CLI + `build_demo_graph` 를 통한 실 호출. Azure 비용 예상 ~$0.3.

### 7.1 시나리오 1 — PM 원안 데모 재현

- **목적:** PM 원안 §2 의 데모 시나리오 (철근 이상 + 장비대기 / 거푸집 정상 / 콘크리트 정상) 정확 재현
- **fixture:** 3 회사 × 3 공종 (남웅=철근 productivity_ratio=0.45, 세보=거푸집 ratio=1.0, 다른업체=콘크리트 ratio=1.0)
- **단계별 캡쳐:** Parser → Mapper → (HIL 1 placeholder 검증 = 미실행) → Atomizer chroma row → Forecaster row (assessment / risk_level / reasoning) → HIL 2 interrupt payload → Optimizer advice
- **검증 포인트:**
  - Forecaster reasoning 에 "장비 대기" 텍스트 detect 여부
  - Optimizer advice 에 "다음날 정상 복귀" / "내일 오전 장비 스케줄 확인" 등 PM 원안 권고사항 패턴 일치 여부
  - HIL 1 미아 fact 확정 (interrupt 호출 0회)

### 7.2 시나리오 2 — 주의 (우천 -20%)

- **fixture:** 1 회사 1 공종, productivity_ratio=0.8 + conditions=["우천"]
- **검증 포인트:** Forecaster 의 risk_level=주의 분기 + Optimizer cold_start vs 정상 advice 분기

### 7.3 시나리오 3 — 이상 (돌관 -45%)

- **fixture:** 1 회사 1 공종, productivity_ratio=0.45 + conditions=["돌관"]
- **검증 포인트:** Forecaster risk_level=이상 분기 + Optimizer recovery_distribution 산출

### 7.4 시나리오 4 — cold_start (baseline=None)

- **fixture:** 신규 회사 (DB 에 history 없음) + 신규 l6_main
- **검증 포인트:** Forecaster 의 cold_start path + Optimizer 의 cold_start 분기 + hil_2_node 의 `no_main_unit` payload

### 7.5 결정론 확보

- 동일 fixture 2 회 실행 후 동일 결과 (LLM 비결정성 제외 컬럼: today_productivity / risk_level / assessment) 검증
- LLM 컬럼 (reasoning / recommendations) 은 의미적 일치만 평가 (수동 또는 LLM judge)

---

## 8. 산출물 구조

### 8.1 `docs/audit/2026-05-17-cpia-e2e-audit-report.md`

```markdown
# CPIA E2E Audit Report (2026-05-17)

## 0. Executive Summary
- 일치 N건 / 부분 N건 / 미구현 N건 / 드리프트 N건
- 의도된 변경 marked N건
- 우선순위 #1~3 후속 cycle 후보

## 1. 단계별 매트릭스
### 1.1 Collector
| 컬럼 | 내용 |
| 원안 의도 | "지정 폴더(input/YYYYMMDD/) 를 감시하여 새 파일을 감지하고 텍스트를 추출" (§4 Week 2) |
| 실 구현 fact | `$ wc -l pipeline/agents/collector.py` → `0 pipeline/agents/collector.py` |
| 일치도 | 미구현 |
| 영향도 | high |
| 우선순위 | #N |
### 1.2 Parser
...(이하 9 단계: Mapper, HIL 1, Atomizer, Reporter, Forecaster, HIL 2, Optimizer, Dashboard)

## 2. 컨셉 v1→v2 cross-cutting
(§5 6 변경 검증)

## 3. 의도된 변경 (drift 제외, marked)
(§6 4 변경)

## 4. 시뮬 시나리오 4 건 결과 요약
시나리오 1~4 각각: 단계별 raw 출력 위치 (raw/<id>.md) + 핵심 fact + 검증 포인트 충족 여부

## 5. 추가 발견 드리프트
시뮬 중 새로 드러난 드리프트
```

### 8.2 `docs/audit/2026-05-17-cpia-drift-backlog.md`

```markdown
# CPIA Drift Backlog (2026-05-17)

## 우선순위 #1 — <이름>
- 출처: audit-report §1.N
- 영향도: high
- 원안 §: ...
- 권고 다음 cycle: brainstorming or 직접 plan

## 우선순위 #2 — ...
...

## defer 항목
- 영향도 low or 별 cycle 우선 도착 후 처리
```

### 8.3 `docs/audit/raw/<scenario>-<run_id>.md`

각 시뮬 시나리오의 단계별 raw 출력 (PG row + Chroma row + interrupt payload + LLM response). Iron Law 3 요소 ($ 명령어 + 실 출력 + 결론) 형식.

---

## 9. 실행 절차 (audit 자체의 단계별 step)

| Step | 작업 | 출력 | 종료 조건 |
|------|------|------|----------|
| 1 | 단계별 fact 수집 (grep + spec 인용) | 매트릭스 임시 표 | 9 단계 모두 fact 박힘 |
| 2 | 시뮬 4 건 사전 fixture 작성 | `docs/audit/fixtures/scenario_<N>.json` 또는 inline | 4 fixture 준비 |
| 3 | 시뮬 4 건 실 호출 (Azure ~$0.3) | `docs/audit/raw/<scenario>-<run_id>.md` × 4 | 4 raw 캡쳐 완료 |
| 4 | 단계별 매트릭스 작성 | `audit-report.md` §1 | 9 단계 모두 5 컬럼 채움 |
| 5 | 컨셉 v1→v2 cross-cutting 작성 | §2 | 6 변경 모두 검증 |
| 6 | 추가 발견 드리프트 정리 | §5 | 시뮬 raw 에서 추출 |
| 7 | 우선순위 backlog 작성 | `drift-backlog.md` | 드리프트별 우선순위 + defer 분류 |
| 8 | review 게이트 | (사용자 검토) | 사용자 OK |

---

## 10. 성공 기준

| # | 기준 | 검증 방법 |
|---|------|----------|
| 1 | 9 단계 매트릭스 5 컬럼 모두 fact 박힘 (placeholder 0) | audit-report.md grep `TODO\|TBD` = 0 |
| 2 | 시뮬 4 건 모두 raw 캡쳐 (Iron Law 3 요소 형식) | `docs/audit/raw/` 4 파일 존재 + `$` `→` 패턴 확인 |
| 3 | PM 원안 §quote 가 원문 verbatim 일치 (paraphrase X) | 매트릭스 행마다 `planning/CPIA_PoC_실행계획_v2.md:line` 박힘 |
| 4 | 의도된 변경 4 건 모두 marked (audit-report §3) | §3 4 행 모두 존재 |
| 5 | 드리프트 후보 8 건 + 추가 발견 모두 backlog 에 배치 | backlog 항목 수 ≥ 8 |
| 6 | LLM 비결정성 노출 컬럼 (reasoning) 은 "의미적 일치" 라고 명시 | audit-report 에 limitation 섹션 |

---

## 11. 전역 CLAUDE.md 하드룰 적용 (audit 자체)

- **Real code or no claim** — 모든 fact 는 `$ grep` 또는 `$ python3 ...` 실 출력 quote. 코드 읽고 추정한 동작은 fact 가 아님.
- **No fabrication** — 함수/파일/시그니처 추측 금지. spec 인용 시 line 번호 포함.
- **Iron Law 3 요소** — raw 부록 (`docs/audit/raw/<scenario>.md`) 형식: `$ <명령어>` + `<실 출력 원본>` + `→ <도출한 결론>`. (b) 가 빠지면 미실시.
- **No 한자** — audit-report.md + backlog.md + raw 부록 모두 한글 + 영어만.
- **응답 언어 한국어** — 코드/CLI/식별자/외래어 고유명사만 영어.
- **TDD as default** — audit 는 코드 변경 없으므로 TDD 외 절차 적용 X. 단 시뮬 시나리오 fixture 는 "동일 입력 2 회 → 동일 결정론 출력" 검증.
- **Surgical edits** — audit 중 발견된 cosmetic 이슈는 코드 수정 X, backlog 의 `defer` 로 분류.

---

## 12. 후속 cycle 핸드오프

본 spec 통과 후:

1. `writing-plans` skill 진입 → audit 실행 plan 작성 (`docs/superpowers/plans/2026-05-17-cpia-e2e-audit-plan.md`)
2. Plan = Step 1~8 (§9) 의 bite-sized task 분해 (TDD 적용 X, fact 수집 + 시뮬 + 문서 작성)
3. 실행 후 산출물 review 게이트
4. Backlog 우선순위 #1 → 별 cycle brainstorming or 직접 plan

후속 cycle 후보 (drift backlog 작성 전 사전 예상):

| 후보 | 원안 § | 예상 영향 |
|------|--------|----------|
| Reporter 구현 (PoC 성공 기준 #1) | §4 Week 3 + §5 #1 | high |
| HIL 1 구현 (Mapper interrupt + corrections 저장) | §4 Week 3 + §5 #2 | high |
| Collector + 파일 드롭 입력 | §4 Week 2 | high |
| main.py + api.py entry point | (묵시적) | med |
| Synthetic 변동 패턴 정합 (우천 -15~25% / 야간 / 장비대기 / 병행) | §3.B | med |
| 회복 패턴 fixture (다음날 정상 복귀 80% / 우천 +10% 만회) | §3.B | med |

실 우선순위는 audit 실행 후 영향도 + 의존성 분석으로 확정.

---

*작성: Claude Opus 4.7 (1M context) | 2026-05-17 | 사용자 = evan@sk.com*
*참조: `planning/CPIA_PoC_실행계획_v2.md` (PM 조형준) / `design/CPIA_기획서_v7.md`*
