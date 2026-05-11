# CPIA 기획서 v5 서사 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `Design/CPIA_기획서_v4.md`를 `Design/CPIA_기획서_v5.md`로 서사 흐름을 재구성하여 작성한다.

**Architecture:** 기존 데이터·수치는 그대로 유지하되, 섹션을 재배치하고 서사 연결 문장을 보강한다. 솔루션(CPIA)은 Section 04에서 처음 등장하며, 그 전까지는 문제 정의 → 조사 → 분석 → 전환 흐름을 따른다.

**Tech Stack:** Markdown, 기존 CPIA_기획서_v4.md 콘텐츠

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `Design/CPIA_기획서_v4.md` | 소스 파일 (읽기 전용) |
| `Design/CPIA_기획서_v5.md` | 새로 작성할 파일 |
| `docs/superpowers/specs/2026-05-11-cpia-v5-narrative-restructure-design.md` | 설계 스펙 참조 |

---

## 서사 구조 검증 기준

각 섹션 작성 후 다음 기준으로 검토:
- [ ] 솔루션(CPIA) 언급이 Section 04 이전에 없는가?
- [ ] 각 섹션 마지막에 다음 섹션으로 이어지는 훅 문장이 있는가?
- [ ] 수치와 표는 v4와 동일한가? (데이터 변경 없음 원칙)

---

### Task 1: 파일 초기화 + Executive Summary

**Files:**
- Create: `Design/CPIA_기획서_v5.md`

- [ ] **Step 1: v5 파일 생성 — 헤더 + 핵심 지표 작성**

v4의 헤더와 핵심 지표 표를 그대로 복사하되, 버전 표기만 v5로 수정:

```markdown
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
```

- [ ] **Step 2: 검토 — Executive Summary가 완전한가**

v4 핵심 지표 표 5개 행이 모두 포함되어 있는지 확인.

---

### Task 2: Section 00 — 건설 현장의 업무 구조

**목적:** Front/Middle/Back Office 전체 구조 설명 + "AI 대체 가능 영역이 어디인가?" 질문 제기. CPIA·솔루션 언급 없음.

**출처:** v4 Section 00 상단 (3-레이어 다이어그램 + Front/Middle/Back 테이블). "CPIA의 답" 블록은 포함하지 않음.

- [ ] **Step 1: Section 00 작성**

```markdown
## 00 — 건설 현장의 업무 구조

건설 현장에는 수백 개의 협력사가 매일 작업일보를 생성하고, 이를 현장 PM과 발주처가 의사결정에 활용합니다.
그런데 데이터를 만드는 사람과 데이터로 판단하는 사람 사이에,
**데이터를 취합·정리·재작성하는 레이어**가 존재합니다.

[v4의 ASCII 다이어그램 — BP/협력사 → MIDDLE OFFICE → 현장 PM/경영진 — 그대로 복사]

| Layer | 역할 | 건설 현장 예시 |
|-------|------|----------------|
| **Front Office** | 수익 창출·의사결정 | 발주처 협의, 공정 문제 해결, 리스크 판단·실행 |
| **Middle Office** | 데이터 중계·검증·보고 | 작업일보 취합, 보고서 작성, 공기 모니터링 |
| **Back Office** | 기록·정산·시스템 | 기성 정산, 퇴직공제, ERP 관리 |

이 구조에서 우리는 한 가지 질문을 던졌습니다.

> **"세 레이어 중 어느 영역의 어떤 업무를 AI로 대체할 수 있는가?"**

답을 찾기 위해 Hi-tech 사업부 전체 업무를 전수 조사했습니다.

---
```

- [ ] **Step 2: 검토 — 솔루션 미등장 확인**

Section 00에 "CPIA", "Agent", "LangGraph", "대체한다" 선언 등 솔루션 관련 표현이 없는지 확인.
마지막 훅 문장("전수 조사했습니다")이 Section 01로 자연스럽게 이어지는지 확인.

---

### Task 3: Section 01 — 전수 조사: 321개 Activity가 보여준 것

**목적:** 조사 결과를 "발견의 서사"로 제시. 수치 나열이 아닌 조사→발견→놀라움의 흐름.

**출처:** v4 Section 01 전체. 데이터·표는 동일. 도입부와 마무리 문장 재작성.

- [ ] **Step 1: Section 01 작성**

```markdown
## 01 — 전수 조사: 321개 Activity가 보여준 것

> 아래 수치는 현장 담당자들이 직접 제출한 Activity 원본 데이터(321개, Hi-tech 사업부 전체)에서 추출한 실측값입니다.

Hi-tech 사업부 8,133h, 321개 Activity를 전수 분석했습니다.
데이터는 세 가지를 보여주었습니다.

### 발견 ① 규모: 업무의 39.5%가 한 레이어에 집중

[v4의 바 차트 ASCII 그대로 복사]

Hi-tech 사업부 월간 업무의 **39.5%(3,212h)**가 Middle Office 레이어에 집중되어 있었습니다.

### 발견 ② 반복: 6개 현장에서 완전히 동일한 패턴

[v4의 현장별 ✓ 체크 표 그대로 복사]

동일한 작업이 6개 현장에서 중복 실행되고 있었습니다.
한 번 해결하면 6배의 효과가 납니다.

### 발견 ③ 자발성: 담당자들이 스스로 AI 수요를 요청

[v4의 CPIA 기능 vs 담당자 자발 제출 Activity 표 그대로 복사]

현장 담당자들이 AI로 해결하고 싶다고 직접 제출한 수요가,
우리가 발견한 병목과 정확히 일치했습니다.

조사가 보여준 것은 명확합니다. **병목은 Middle Office에 있습니다.**
다음 질문은 "얼마나 심각한가"입니다.

---
```

- [ ] **Step 2: 검토**

발견 ①②③ 구조가 순서대로 전개되는지, 마무리 훅이 Section 02로 연결되는지 확인.

---

### Task 4: Section 02 — 병목 분석: 무엇이 얼마나 막히는가

**목적:** 병목의 실체를 수치로 가시화. FTE 17.9명이라는 수치로 심각성을 체감시킴.

**출처:**
- 4가지 Middle Office 기능 표 → v4 Section 00 하단에서 이동
- 현장별 실측 표 → v4 Section 01 하단에서 이동
- As-is 수작업 7단계 → 이 섹션에서는 간략 요약만 (상세는 Section 03)

- [ ] **Step 1: Section 02 작성**

```markdown
## 02 — 병목 분석: 무엇이 얼마나 막히는가

Middle Office가 수행하는 업무를 기능별로 분해했습니다.

### Middle Office의 4가지 기능

| 기능 | 내용 | 현재 월간 시간 |
|------|------|-------------|
| ① Data Stewardship | BP 작업일보 수집·정합성 검증·표준 DB 적재 | 632h |
| ② P&L Reporting | 공정률·생산성 집계, Daily·Weekly·Monthly 보고서 작성 | 800h |
| ③ Risk Management | 공기 지연 모니터링·잔여 물량 분석·Forecast 산출 | 700h |
| ④ Deal Support | 주간회의 자료 가공·CPI/SPI 산출·만회 시나리오 초안 | 374h |
| **합계** | | **2,506h/월 (6개 현장)** |

이 업무들은 판단이 아니라 **중계**입니다.
현장 엔지니어의 하루 중 상당 시간이 BP 이메일을 열어 복붙하고, 같은 숫자를 PPT에 옮겨 적는 데 쓰입니다.

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

**FTE 17.9명 수준의 업무가 데이터 중계 레이어에 묶여 있습니다.**
이 구조에서 AI를 도입하면 무엇이 달라지는가?

---
```

- [ ] **Step 2: 검토**

4가지 기능 표 수치가 v4와 일치하는지, 현장별 표 수치가 v4와 일치하는지 확인.
마무리 훅("AI를 도입하면")이 Section 03으로 연결되는지 확인.

---

### Task 5: Section 03 — AI가 이 구조를 어떻게 바꾸는가

**목적:** As-is → To-be 전환을 보여주고, "이것을 실현할 Agent가 필요하다"로 CPIA 도입을 연결.

**출처:** v4 Section 02 전체 재편집.

- [ ] **Step 1: Section 03 작성**

```markdown
## 03 — AI가 이 구조를 어떻게 바꾸는가

### AS-IS: 현재 (수작업 7단계, 담당자 전일 투입)

[v4 Section 02 AS-IS 블록 그대로 복사]

결과: **담당자 1~3명 전일 투입 | 보고 D+2~3일 지연 | 지연 후 만회 불가**

### TO-BE: AI Agent 도입 이후

[v4 Section 02 TO-BE 블록 그대로 복사]

결과: **검토·승인 30분/일 | D+0 당일 발송 | D-14 선제 대응**

---

Middle Office의 4가지 기능(Data Stewardship·P&L Reporting·Risk Management·Deal Support)은
각각 하나의 전문 Agent로 대체됩니다.

이 전환을 실현하기 위해, 우리는 5개 전문 Agent로 구성된 **CPIA**를 설계했습니다.

---
```

- [ ] **Step 2: 검토**

AS-IS 7단계와 TO-BE 5단계가 모두 포함되어 있는지 확인.
마지막 문장이 "CPIA를 설계했다"로 끝나며 Section 04로 연결되는지 확인.

---

### Task 6: Section 04 — CPIA: 우리가 설계한 Answer

**목적:** 솔루션 첫 등장. "Middle Office를 AI Agent로 교체한다"는 선언 후 LangGraph 구조 설명.

**출처:**
- 도입 선언: v4 Section 00의 "CPIA의 답: 구조를 바꾼다" 블록
- LangGraph 설명, 아키텍처, 코드, Agent 명세: v4 Section 03 전체

- [ ] **Step 1: Section 04 작성 — 도입부**

```markdown
## 04 — CPIA: 우리가 설계한 Answer

### Middle Office를 AI Agent로 교체한다

CPIA는 보고서를 빠르게 만드는 도구가 아닙니다.

> **Middle Office 레이어 자체를 AI Agent로 대체하여,**
> **Front Office(PM·엔지니어)가 AI와 직접 일하는 구조로 전환합니다.**

```
✅ 올바른 프레이밍: "Front가 AI Agent와 직접 일하는 구조로 전환한다"
   → Middle Office 인력 = Agent 오케스트레이터로 업스킬링
   → PM은 데이터를 취합하는 사람에서 데이터로 판단하는 사람으로
   → 조직 차원의 AX 실현
```
```

- [ ] **Step 2: Section 04 나머지 — LangGraph 이하 전체 복사**

v4 Section 03의 다음 내용을 그대로 복사:
- "프레임워크 선택: LangGraph" (비교 테이블 포함)
- "전체 LangGraph 아키텍처" (ASCII 다이어그램)
- "LangGraph 코드 구조" (Python 코드 블록)
- "Agent 상세 명세" (Node 1~6 테이블)
- "데이터 파이프라인 선순환 구조"

마지막에 `---` 구분선 추가.

- [ ] **Step 3: 검토**

Section 04가 문서에서 "CPIA"라는 단어가 처음 등장하는 섹션인지 확인.
(Section 00~03에서 CPIA가 언급되지 않아야 함)

---

### Task 7: Section 05~08 + 핵심 메시지 복사

**목적:** 변경 없는 섹션을 v4에서 그대로 복사하되, 섹션 번호만 업데이트.

**출처:**
- Section 05 ← v4 Section 04 (정량적 효과)
- Section 06 ← v4 Section 05 (데이터 준비도)
- Section 07 ← v4 Section 06 (실행 계획)
- Section 08 ← v4 Section 07 (향후 확장성)
- 핵심 메시지 ← v4 마지막 (동일)

- [ ] **Step 1: 각 섹션 번호 업데이트 후 복사**

```
v4 Section 04 → ## 05 — 정량적 효과
v4 Section 05 → ## 06 — 데이터 준비도
v4 Section 06 → ## 07 — 실행 계획
v4 Section 07 → ## 08 — 향후 확장성
v4 핵심 메시지 → ## 핵심 메시지 (번호 없음)
```

- [ ] **Step 2: 푸터 작성자 정보 복사**

```markdown
*작성자: 조형준 프로 | SK에코플랜트 AI Board | 2026 FLP Module 2 — AI Design Project*
*데이터 출처: TASK 및 Activity 취합 및 분석_원본자료_1차검토.xlsx (Hi-tech 321개 Activity 실측)*
```

---

### Task 8: 전체 서사 흐름 검증

- [ ] **Step 1: 솔루션 등장 시점 검증**

문서 전체에서 "CPIA"가 처음 등장하는 위치가 Section 04인지 grep으로 확인:

```bash
grep -n "CPIA" "Design/CPIA_기획서_v5.md" | head -5
```

첫 번째 결과가 Section 04 (## 04) 이후 줄 번호여야 함.

- [ ] **Step 2: 훅 문장 존재 검증**

각 섹션 마지막 단락에 다음 표현이 있는지 확인:
- Section 00: "전수 조사했습니다" 또는 이에 준하는 다음 섹션 연결 문장
- Section 01: "병목은 Middle Office에 있습니다" 또는 이에 준하는 문장
- Section 02: "AI를 도입하면" 또는 이에 준하는 문장
- Section 03: "CPIA를 설계했습니다" 또는 이에 준하는 문장

- [ ] **Step 3: 데이터 무결성 확인**

핵심 수치가 v4와 일치하는지 확인:
- 2,506h/월 (합계)
- 86% 절감
- FTE 17.9명
- D-14 선행 탐지
- 연간 약 180억 원

- [ ] **Step 4: git commit**

```bash
git add "Design/CPIA_기획서_v5.md"
git commit -m "docs: CPIA 기획서 v5 — 서사 흐름 재구성 (문제→조사→분석→솔루션 순서)"
```
