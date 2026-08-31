# CPIA PoC 실행계획 v2

> **개인과제 | 2026년 5~6월 | 조형준 프로**
> v1 대비 핵심 변경: 품셈 기준값 제거 → Vector RAG 기반 컨텍스트 생산성 판단으로 전환

---

## v1 → v2 변경 요약

| 구분 | v1 | v2 |
|------|----|----|
| 생산성 기준 | 품셈 표준 생산성 (외부 기준) | 현장 실적 누적 이력 (내부 기준) |
| Forecaster 판단 방식 | 실측 ÷ 품셈 = 달성률 | 오늘 실적 vs 유사 과거 상황 비교 |
| Optimizer 역할 | 최적 인원 역산 + 재배치 수치 계산 | 상황 진단 + 맥락 기반 조언 생성 |
| 추가 파이프라인 단계 | — | Atomizer (Vector DB 적재) |
| 추가 기술 스택 | — | ChromaDB (Vector DB) + 임베딩 |
| 현장 범위 | Y-1 Ph-1 OBL 단일 현장 | 현장 구분 없는 범용 구조 |
| 데모용 이력 데이터 | 불필요 (품셈이 기준) | Synthetic history 30일치 생성 필요 |

---

## 이 문서의 목적

한 달 안에 "**Collector → Parser → Mapper → Atomizer → Reporter → Forecaster → Optimizer → Dashboard, 전체 파이프라인이 실제로 돌아간다**"는 것을 경영진 앞에서 라이브로 보여주는 것.

> **핵심 전략:** 공종 범위를 좁히되 전체 스토리를 완성한다.
> "모든 공종을 처리하지만 보고서 생성까지만" 보다
> "2~3개 공종이지만 생산성 진단 + 맥락 기반 조언 + 대시보드까지 전부" 가 경영진에게 훨씬 강하게 전달됩니다.

---

## 1. PoC 범위 결정

### 포함 범위

| 구분 | 내용 |
|------|------|
| **대상 현장** | 범용 설계 — 특정 현장 고정 없이 작업일보 양식이 맞으면 어떤 현장이든 투입 가능한 구조 |
| **대상 공종** | **2~3개 공종 선택 집중** (철근·거푸집·콘크리트 등 물량 단위가 명확한 공종) |
| **구현 Agent** | **7개:** Collector → Parser → Mapper [H-i-L 1] → Atomizer → Reporter ‖ Forecaster [H-i-L 2] → Optimizer |
| **입력 데이터** | 샘플 작업일보 5~10개 + **Synthetic history 30일치** (Vector DB 초기화용) + 잔여 계획 물량·완료일 (공정표) |
| **출력물** | 자동 생성 통합 Daily Report + **경영진 대시보드 (Streamlit)** |
| **Human-in-the-Loop** | **H-i-L 1 (Mapper):** 매핑 검증 + 수정 피드백 루프 / **H-i-L 2 (Forecaster):** 진단 결과 검토 + 조언 대상 선택 |

### 제외 범위

| 제외 항목 | 이유 |
|----------|------|
| 6개 현장 확산 | 1개 현장 완성 후 확산은 반복 작업 — PoC 이후 |
| 이메일·카카오톡 실제 연동 | 보안 승인 절차 시간 소요 — 파일 드롭 방식으로 대체 |
| CPI 기반 비용 분석 | AC(실제 비용) 데이터가 작업일보에 없음 — Phase 2에서 비용 데이터 연동 후 추가 |
| 품셈 기준 생산성 비교 | 품셈은 공사비 견적 도구 — 현장 생산성 KPI로 부적합. 현장 실적 기반 판단으로 대체 |
| 인원 재배치 수치 자동 계산 | 직종 호환성·공간 제약·CPM 데이터 없이는 계산 근거 없음 — Optimizer는 판단 재료 제공에 집중 |
| 전체 공종 처리 | 2~3개 공종만으로도 파이프라인 전체를 보여줄 수 있음 |

### 핵심 증명 명제

> "선택한 공종의 작업일보를 넣으면, AI가 공정표에 자동으로 매핑하고(Mapper),
> 오늘 작업 내용을 과거 이력 DB에 적재하며(Atomizer),
> 전체 협력사의 작업일보를 통합 보고서로 생성하고(Reporter),
> 오늘의 생산성이 과거 유사 상황 대비 적정한지 여부를 날씨·작업 여건·패턴으로 진단하며(Forecaster),
> PM이 선택한 공종에 한해 과거 유사 저하 상황의 원인과 회복 패턴을 기반으로 구체적 조언을 제시한다(Optimizer).
> 경영진은 6개 현장 현황 대시보드에서 현재 상태와 근거 있는 액션을 한 화면으로 본다."

---

## 2. 제작 방식

### 기본 방침

**"단순하게, 동작하게, 경영진이 이해하게"**

- 로컬 Python 환경에서 실행 가능한 수준으로 구현 (복잡한 인프라 불필요)
- Forecaster는 절대 기준(품셈)이 아닌 **현장 실적 이력 기반 상대 비교**로 판단
- Optimizer는 수치 계산기가 아닌 **맥락 기반 조언자** — 과거 패턴을 근거로 PM에게 선택지 제시
- 대시보드는 코드보다 **화면이 설득**한다는 원칙으로 설계

### 기술 선택

| 결정 사항 | 선택 | 이유 |
|----------|------|------|
| Agent 프레임워크 | LangGraph | H-i-L interrupt·조건 분기·병렬 실행이 핵심 |
| LLM 모델 | Claude Sonnet 4.6 (Parser·Mapper·Reporter) / Opus 4.7 (Forecaster·Optimizer) | 판단·추론이 필요한 단계에서 Opus 사용 |
| **Vector DB** | **ChromaDB (로컬)** | 설치·운용 간단, 로컬 Python 환경에서 서버 불필요, 임베딩 저장·유사도 검색 지원 |
| **임베딩 모델** | **OpenAI text-embedding-3-small** 또는 **Anthropic Claude 임베딩** | 한국어 건설 도메인 텍스트 처리 |
| 입력 방식 | 지정 폴더에 파일 드롭 | 이메일 연동 대신 — 개념 증명에 충분 |
| 대시보드 | Streamlit | Python만으로 빠르게 웹 UI 구성 가능, 데모용으로 최적 |
| **Forecaster 데이터** | **Vector DB 유사 이력 + WBS 계획값 (cold start fallback)** | 품셈 대신 현장 실적 기반 |
| **Optimizer 데이터** | **Vector DB 과거 저하 상황·회복 패턴** | LLM이 유사 사례 종합 → 조언 생성 |
| 실행 환경 | 개인 PC (로컬) | 사내 인프라 승인 전 단계에서 빠르게 검증 |

### 핵심 개념: 컨텍스트 기반 생산성 판단

```
[기존 v1 판단 방식]
실측 생산성 ÷ 품셈 기준 = 달성률 → 임계값 이하면 경고

[v2 판단 방식]
"오늘 거푸집 생산성이 22.9 m²/인이다.
 이게 낮은 건가, 아니면 오늘 조건을 감안하면 정상인가?"
         ↓
Vector DB 조회: 과거 30일 중 유사 조건 (우천 + 병행작업 있는 날)
         ↓
"우천일 평균 생산성: 21.3 m²/인 → 오늘은 정상 범위"
또는
"우천 없는 날임에도 불구하고 -25% → 다른 원인 있음"
         ↓
LLM이 작업 내용 텍스트 분석: "호이스트 운행으로 인원 분산 확인"
```

절대 기준이 없어도 **현장 실정에 맞는 판단**이 가능합니다.

### 데모 시나리오 (경영진 시연 기준)

```
[화면 1: 대시보드 초기 상태]
  ┌──────────────────────────────────────────────────────┐
  │  CPIA 현장 현황 — Demo Site                2026.06.01│
  │                                                      │
  │  공정률:  계획 38.5%  |  실적 34.2%  ⚠️ -4.3%p 지연  │
  │  생산성 이상 공종: 철근 (원인 분석 필요)               │
  │  마지막 보고: 어제 D+2 지연 수동 발송                  │
  └──────────────────────────────────────────────────────┘

[시연: 작업일보 파일 5개 드롭 → CPIA 실행]
  Collector:  5개 파일 수집 완료 (12초)
  Parser:     구조화 완료 — 인원 42명, 거푸집 320m², 철근 18ton (23초)
  Mapper:     공정표 의미 기반 매핑 완료 — 확신도 낮은 항목 2건 플래그
  → [H-i-L 1] 매핑 검증: 담당자가 2건 확인·수정 (corrections.json 저장)
  Atomizer:   오늘 작업 기록 Vector DB 적재 완료
              (날짜·업체·공종·인원·물량·작업내용 임베딩)
  Reporter:   통합 Daily Report 자동 생성 완료 (사내 + 발주처용)
  Forecaster: 공종별 생산성 진단 완료
              ┌─────────────────────────────────────────────┐
              │ 거푸집: 22.9 m²/인 — 우천일 과거 평균 대비 정상 범위 ✓
              │ 철근:   1.8 ton/인 — 조건 보정 후에도 -28% ⚠️ 원인 불명
              │ 콘크리트: 68.3 m³/인 — 정상 ✓
              └─────────────────────────────────────────────┘
              원인 분석: 철근 — 과거 유사 패턴 없음, 작업내용에 '장비 대기' 기재
  → [H-i-L 2] 조언 대상 선택: PM이 [철근] 선택
  Optimizer:  ██ 과거 유사 저하 상황 분석 ██
              과거 장비 대기 관련 3건 조회:
              → 3건 모두 다음날 정상 복귀, 장비 투입 확인 후 회복
              → 권고: 내일 오전 장비 스케줄 확인 필요
                      잔여물량 기준 D+4 이내 정상화 시 공기 영향 없음

[화면 2: 대시보드 자동 갱신]
  ┌──────────────────────────────────────────────────────┐
  │  생산성 진단 완료 | 이상 공종: 철근 (장비 대기 추정)   │
  │  오늘 보고: D+0 자동 발송 완료 (처리 시간: 5분 10초)   │
  └──────────────────────────────────────────────────────┘

[비교 메시지]
  AS-IS: 담당자 2명이 3시간 → TO-BE: AI가 5분 이내
```

---

## 3. 사전 준비 사항

### A. 데이터 준비

| 필요 데이터 | 형태 | 확보 방법 | 비고 |
|------------|------|----------|------|
| 작업일보 샘플 5~10개 | Excel 또는 텍스트 | 현장 담당자 요청 (비식별화) | 못 받으면 가상 데이터로 대체 가능 |
| WBS 구조표 (공종 목록) | Excel | 현장 PM에게 공종·Activity 목록 요청 | 2~3개 공종만 선택하면 충분 |
| **Synthetic history 30일치** | Python 생성 스크립트 | Week 1에서 직접 생성 | Vector DB cold start 해소용. 날씨·요일·인원 변동 반영한 현실적 가상 데이터 |
| **잔여 계획 물량 + 계획 완료일** | Excel | 현장 PM 또는 공정 담당자 | Forecaster 완료일 예측에 필요 |
| Plan 공정률 기준값 | Excel | 공정 담당자에게 마일스톤 진도율 요청 | S-curve 표시용 |

> **v1과의 차이:** 품셈 데이터는 더 이상 필요하지 않습니다.
> 대신 **Synthetic history 30일치**가 핵심 선행 과제입니다.
> Vector DB에 아무 데이터도 없으면 Forecaster·Optimizer가 비교 대상 없이 작동하기 때문에
> Week 1에서 반드시 생성해야 합니다.

### B. Synthetic History 생성 기준

```python
# Synthetic history 레코드 구조 (30일 × 업체 수 × 공종 수)
{
  "date": "2026-05-01",
  "contractor": "A건설",
  "trade": "거푸집",
  "area": "FAB-2F",
  "headcount": 14,
  "output": 324,
  "unit": "m²",
  "productivity": 23.1,
  "conditions": ["맑음", "정규작업"],
  "work_content": "FAB 2층 벽체 거푸집 설치 / 정상 작업"
}
```

**변동 요소 반영:** 우천일 -15~25%, 야간 연장 비율 50% 초과 시 익일 -10%, 장비 대기 시 -20~35%, 병행작업 겹침 시 -10~20%. 이 패턴이 있어야 Forecaster가 "오늘이 비정상인지 정상인지"를 판단할 수 있습니다.

### C. API 및 개발환경

| 항목 | 확인 사항 | 예상 비용 |
|------|----------|---------|
| Claude API Key | Anthropic 계정 발급 | PoC 기간 $30~60 예상 (Opus 4.7 Forecaster·Optimizer 포함) |
| OpenAI API Key (임베딩용) | text-embedding-3-small | PoC 기간 $5 이하 예상 |
| Python 환경 | 3.11+ / LangGraph·anthropic·streamlit·chromadb·openpyxl 설치 | 무료 |

### D. 현장 협조 요청

| 대상 | 요청 내용 | 소요 시간 |
|------|----------|---------|
| 현장 담당자 1명 | 작업일보 양식 확인, 보고서 샘플 검토 | 미팅 1~2회 (각 30분) |
| 공정 담당자 (선택) | 공종 선택 + 공정률 산출 기준 확인 | 미팅 1회 (30분) |

---

## 4. 단계별 진행 계획 (4주)

### 전체 데이터 흐름 개요

```
[Week 2] 작업일보 파일 드롭
              ↓
         Collector  — 파일 감지, 텍스트 추출
              ↓  (원본 텍스트)
          Parser   — 비정형 텍스트 → 구조화 JSON  (Claude Sonnet 4.6)
              ↓

[Week 3]   Mapper  — 작업 내용 → WBS 의미 기반 매핑 (Claude Sonnet 4.6)
              ↓
          [H-i-L 1] — 매핑 검증 + 사용자 수정 (LangGraph interrupt)
              ↓  확정 매핑
         Atomizer  — 오늘 작업 기록 Vector DB 적재
              ↓         (Sheet4 수치 + Sheet1 텍스트 JOIN → 임베딩)
        ┌────┴──────────────────────────┐
     Reporter                      Forecaster
   통합 보고서 생성 (Sonnet)          유사 이력 조회 + 생산성 진단 (Opus)
   사내 + 발주처용                    오늘 실적이 적정한지 판단
   history.csv 업데이트              이상 원인 추론 + 리스크 공종 목록
                                          ↓
                                     [H-i-L 2] — PM이 조언 대상 공종 선택
                                          ↓  선택 공종만
                                     Optimizer
                                   과거 유사 저하 패턴 검색 (Vector RAG)
                                   원인 진단 + 회복 시나리오 조언 (Opus)
                                          ↓
                                   [실행 의사결정] — PM 검토·승인
        └────────────────────────────────┘
              ↓

[Week 4]  Dashboard — 전체 현황(6개 현장) + 현장 상세 + H-i-L 버튼  (Streamlit)
```

**공유 데이터 저장소**

```
data/
  vector_db/           ← ChromaDB 저장소 (Atomizer가 매일 적재, Forecaster·Optimizer가 조회)
  synthetic_history/   ← Week 1에서 생성하는 30일치 가상 이력 (Vector DB 초기화용)
  history.csv          ← Reporter가 매일 쌓는 실적 누적 (Dashboard S-curve용)
  corrections.json     ← Mapper H-i-L 수정 내역 누적 (Mapper 피드백 루프)
  forecast.json        ← Forecaster 출력 저장 (Optimizer·Dashboard가 읽음)
  optimizer.json       ← Optimizer 출력 저장 (Dashboard가 읽음)
  mock_sites.json      ← 나머지 5개 현장 더미 데이터 (Dashboard Layer 1용)
output/
  reports/YYYYMMDD.md  ← Reporter가 생성하는 일일 보고서
input/
  YYYYMMDD/            ← Collector가 감시하는 작업일보 드롭 폴더
```

---

### Week 1 — 기반 구축

**목표:** 개발 환경 + 데이터 구조 설계 + Synthetic history 생성 + Vector DB 초기화

#### 이번 주에 결정해야 할 것들

**① 대상 공종 선정 기준**

물량 단위가 숫자로 명확히 나오는 공종을 우선 선택합니다.
예: 철근(ton), 거푸집(m²), 콘크리트(m³). 현장 담당자에게 "작업일보에서 물량을 가장 많이 적는 공종 2~3개"를 물어보는 게 가장 빠릅니다.

**② JSON 데이터 스키마 확정**

Parser 출력, Vector DB 적재, Dashboard 표시까지 모든 단계가 이 구조를 공유합니다.

```json
// Parser 출력 JSON 스키마
{
  "date": "2026-06-01",
  "bp_code": "PH_X-001",
  "bp_name": "협력사명",
  "activities": [
    {
      "wbs_code": "RC-001",
      "trade": "철근",
      "workers": 14,
      "quantity": 18.0,
      "unit": "ton",
      "work_content": "FAB 2층 벽체 철근 조립 / 장비 대기로 오전 작업 지연",
      "conditions": ["맑음", "야간연장없음"]
    }
  ]
}
```

**③ Vector DB 레코드 스키마 확정**

Atomizer가 적재하는 각 레코드의 구조를 사전에 결정해야 Forecaster 조회 쿼리가 일관성 있게 작동합니다.

```python
# Vector DB 레코드 구조
{
  # 메타데이터 (필터·조회용)
  "id": "20260601_PH_X001_거푸집",
  "date": "2026-06-01",
  "contractor": "A건설",
  "trade": "거푸집",
  "headcount": 14,
  "output": 320.0,
  "unit": "m²",
  "productivity": 22.9,        # output / headcount
  "spi": 0.88,                 # 오늘 실적WV / 계획WV
  "conditions": ["우천", "병행작업"],

  # 임베딩 대상 (의미 검색용)
  "content": "FAB 2층 기초 거푸집 설치 / 우천 대응 작업 병행 / 호이스트 운행으로 일부 인원 분산"
}
```

**④ Synthetic History 생성**

30일치 가상 이력은 Vector DB의 cold start 문제를 해소하기 위한 핵심 사전 작업입니다.

```python
# synthetic_history_generator.py
# 생성 기준:
# - 대상 공종 2~3개 × 업체 2~3개 × 30일 = 180~270개 레코드
# - 변동 패턴 반영:
#   우천일 (-15~25%), 야간 연장 비율 50% 초과 시 익일 (-10%)
#   장비 대기 (-20~35%), 병행작업 겹침 (-10~20%), 정상일 (±5%)
# - 회복 패턴 반영:
#   장비 대기 → 다음날 정상 복귀 (80% 확률)
#   우천 연속 2일 → 3일차 +10% 만회 패턴
```

**Week 1 체크포인트:** Synthetic history 180개+ 레코드 → ChromaDB 적재 완료. 빈 파이프라인이 오류 없이 실행된다.

#### 진행 체크리스트

- [ ] 개발 환경 구성 (Python 3.11, LangGraph, anthropic, streamlit, chromadb, openpyxl 설치·동작 확인)
- [ ] 현장 담당자에게 작업일보 샘플 요청 (못 받으면 양식 구조 파악 후 가상 데이터 생성)
- [ ] 대상 공종 2~3개 확정 + JSON 스키마 확정
- [ ] 가상 작업일보 샘플 5개 생성 (확정된 공종·양식 기준)
- [ ] **Synthetic history 생성 스크립트 작성 + 30일치 데이터 생성**
- [ ] **ChromaDB 초기화 + Synthetic history 전량 임베딩·적재**
- [ ] 잔여 계획 물량·계획 완료일 확보 (공종별, 공정표에서 추출)
- [ ] **6개 현장 더미 데이터 JSON 생성** (`data/mock_sites.json`) — 대시보드 전체 현황 뷰 용도
- [ ] 폴더 구조 및 LangGraph 파이프라인 뼈대 구성
- [ ] WBS 구조표 정리 — Mapper 프롬프트에 포함할 공종 목록 확정

---

### Week 2 — Collector + Parser

**목표:** "파일을 넣으면 구조화 JSON이 나온다"

#### Collector 작동 방식

| 항목 | 내용 |
|------|------|
| 기능 | 지정 폴더(`input/YYYYMMDD/`)를 감시하여 새 파일을 감지하고 텍스트를 추출 |
| 입력 | 작업일보 파일 (Excel `.xlsx` 또는 텍스트 `.txt`) |
| 처리 | Excel: `openpyxl`로 시트 전체 셀 텍스트 추출 / 텍스트: 직접 읽기 |
| 출력 | 파일별 원본 텍스트 문자열 → Parser로 전달 |

#### Parser 작동 방식

| 항목 | 내용 |
|------|------|
| 기능 | 비정형 텍스트에서 공종별 [인원·물량·작업내용·조건]을 추출하여 JSON으로 변환 |
| 입력 | Collector의 원본 텍스트 + WBS 구조표 (프롬프트에 포함) |
| 처리 | Claude Sonnet 4.6 호출. **작업내용(work_content) 텍스트 보존 필수** — Atomizer 임베딩의 핵심 원천 |
| 출력 | 구조화 JSON (Week 1에서 확정한 스키마 기준) |

**Parser 프롬프트 핵심 구조:**
```
당신은 건설 현장 공정 데이터 추출 전문가입니다.
아래 WBS 공종 목록을 참고하여, 작업일보 원문에서
각 공종의 [투입 인원, 당일 물량, 작업 내용 전문, 날씨·여건 정보]를 JSON으로 추출하세요.

특히 work_content 필드에는 작업 내용 기술을 원문 그대로 보존하세요.
(이 텍스트는 이후 AI가 생산성 원인 분석에 활용합니다)

[WBS 공종 목록] ...
[작업일보 원문] {raw_text}
[출력 형식] {"bp_name": ..., "activities": [...]}
```

**Week 2 체크포인트:** 샘플 5개 드롭 → 구조화 JSON 5개 자동 생성. work_content 필드 누락 없음.

#### 진행 체크리스트

- [ ] Collector 구현: 폴더 감시 + Excel/텍스트 텍스트 추출
- [ ] Parser 구현: WBS 구조 프롬프트 작성 + Claude Sonnet 4.6 호출 (work_content 필드 포함)
- [ ] 샘플 5개로 Parser 정확도 확인 (목표: 4개 이상 정상 매핑)
- [ ] 프롬프트 튜닝: 오매핑·누락 케이스 분석 후 보완

---

### Week 3 — Mapper + H-i-L 1 + Atomizer + Reporter + Forecaster + H-i-L 2 + Optimizer

**목표:** "매핑 검증 → Vector DB 적재 → 통합 보고서 → 생산성 진단 → 조언 제안, 전 Agent가 한 번에 돌아간다"

#### Mapper 작동 방식

| 항목 | 내용 |
|------|------|
| 기능 | 작업일보의 작업 내용 기술을 공정표 WBS 코드에 의미 기반으로 매핑 |
| 입력 | Parser의 구조화 JSON + WBS 구조표 |
| 처리 | Claude Sonnet 4.6. 확신도 낮은 항목은 `requires_review: true` 플래그 |
| 출력 | 매핑 완료 JSON + 불확실 항목 목록 (H-i-L 대상) |

#### H-i-L 1 (Mapper) 작동 방식

v1과 동일. LangGraph `interrupt()` → 담당자 수정 → `corrections.json` 누적.

#### Atomizer 작동 방식 (신규)

| 항목 | 내용 |
|------|------|
| 기능 | 오늘 작업 기록을 Vector DB에 임베딩·적재 — 이후 Forecaster·Optimizer의 검색 대상 |
| 입력 | Mapper 확정 JSON (공종·인원·물량) + Parser의 work_content 텍스트 + 날씨·조건 정보 |
| 처리 | 공종별 레코드 생성 (메타데이터 + content 텍스트) → 임베딩 → ChromaDB 저장 |
| 출력 | ChromaDB 적재 완료 (오늘 날짜 레코드 추가) |
| 특이사항 | Sheet4(수치)와 Sheet1(텍스트)를 날짜+업체 키로 JOIN하여 하나의 레코드로 구성 |

```python
# Atomizer 핵심 로직
def atomize_and_store(mapper_output, parser_output, vector_db):
    for activity in mapper_output["activities"]:
        record = {
            "metadata": {
                "date": mapper_output["date"],
                "contractor": mapper_output["bp_name"],
                "trade": activity["trade"],
                "headcount": activity["workers"],
                "output": activity["quantity"],
                "productivity": activity["quantity"] / activity["workers"],
                "conditions": activity.get("conditions", [])
            },
            "content": activity["work_content"]  # 임베딩 대상
        }
        vector_db.add(record)
```

#### Reporter 작동 방식

v1과 동일. Mapper 확정 JSON → Claude Sonnet 4.6 → 통합 Daily Report 생성 + history.csv 업데이트.

#### Forecaster 작동 방식 (Vector RAG 기반으로 전면 재설계)

| 항목 | 내용 |
|------|------|
| 기능 | 오늘 생산성이 과거 유사 상황 대비 적정한지 진단하고 리스크 공종 목록 생성 |
| 입력 | 오늘 Mapper 확정 JSON (인원·물량·work_content) + ChromaDB |
| 처리 | **Step 1:** 오늘 공종별 생산성 계산. **Step 2:** ChromaDB에서 유사 조건 과거 기록 5건 조회. **Step 3:** Claude Opus 4.7에게 오늘 실적 + 유사 이력을 주고 "이 생산성이 오늘 조건을 감안했을 때 적정한지" 판단 요청 |
| 출력 | `data/forecast.json` — 공종별 {생산성 적정 여부, 판단 근거, 유사 과거 사례, 예상 완료일, 리스크 등급} + 리스크 공종 목록 |
| Cold Start | Vector DB에 유사 기록이 3건 미만이면 WBS Man-Hour 기반 계획 생산성을 fallback으로 사용 |

**Forecaster 프롬프트 핵심 구조:**
```
당신은 건설 현장 생산성 분석 전문가입니다.

오늘 [공종]의 생산성: [오늘 실적] [단위]/인
오늘 작업 내용: [work_content]
오늘 조건: [weather, conditions]

유사 과거 상황 5건:
[Vector DB 검색 결과 — 유사한 조건의 과거 기록]

위 정보를 바탕으로 판단하세요:
1. 오늘 생산성이 오늘 조건을 감안했을 때 정상 범위인가?
2. 정상 범위 이탈 시 작업 내용 텍스트에서 원인을 추론하라
3. 잔여 물량 [N] [단위], 계획 완료일 [날짜] 기준 예상 완료일을 계산하라
```

**Forecaster 출력 예시:**
```json
{
  "trade": "철근",
  "today_productivity": 1.8,
  "unit": "ton/인",
  "assessment": "이상",
  "reasoning": "오늘 날씨는 맑음이고 병행작업 없음. 유사 조건 과거 5건 평균 2.6 ton/인 대비 -31%. 작업내용에 '장비 대기' 기재 — 타워크레인 스케줄 충돌 가능성.",
  "similar_cases": ["2026-05-15 장비 대기, 다음날 정상 복귀", "2026-05-03 장비 대기, 2일 후 만회"],
  "expected_completion": "2026-06-18",
  "delay_days": 3,
  "risk_level": "주의"
}
```

#### H-i-L 2 (Forecaster → Optimizer)

v1과 동일하되 역할 변경: 리스크 공종 목록 표시 + PM이 **조언 대상 공종** 선택 (최적화 의뢰 공종 선택).

#### Optimizer 작동 방식 (Vector RAG 기반으로 전면 재설계)

| 항목 | 내용 |
|------|------|
| 기능 | PM이 선택한 공종의 저하 원인을 과거 패턴 기반으로 진단하고, 회복 시나리오와 구체적 조언을 제시 |
| 입력 | `data/forecast.json` + H-i-L 2 확정 공종 목록 + ChromaDB |
| 처리 | **Step 1:** ChromaDB에서 "이 공종이 비슷하게 저하됐던 과거 상황" 검색. **Step 2:** 해당 상황에서 다음날 어떻게 됐는지 검색. **Step 3:** Claude Opus 4.7이 원인·회복 패턴·권고사항 종합 |
| 출력 | `data/optimizer.json` — {진단 결과, 유사 과거 사례 요약, 회복 시나리오, PM 검토 필요 사항} |

**Optimizer 출력 예시:**
```
[PM 선택 공종: 철근]

진단: 장비 대기로 인한 생산성 저하 (추정)
      오늘 작업내용: "타워크레인 대기로 오전 작업 지연"

과거 유사 상황 (장비 대기 3건):
  ✓ 05-15: 장비 스케줄 충돌 → 다음날 정상 복귀 (100%)
  ✓ 05-03: 크레인 대기 → 2일 후 정상 복귀 (만회 없음)
  ✓ 04-22: 장비 대기 → 인원 재집중 투입으로 당일 만회

권고사항:
  1. 내일 오전 타워크레인 스케줄 확인 필수
  2. 과거 패턴상 장비 확보 시 다음날 자연 복귀 가능성 높음
  3. 잔여 물량 기준 D+3 이내 정상화 시 공기 영향 없음
  4. D+3 초과 시 야간 연장 또는 주말 투입 검토 필요

※ 최종 판단 및 실행은 PM 결정 사항입니다.
```

**Week 3 체크포인트:** 파일 드롭 → Mapper H-i-L 1 → Atomizer Vector DB 적재 → Reporter + Forecaster 병렬 → H-i-L 2 → Optimizer 조언이 터미널에 출력된다.

#### 진행 체크리스트

- [ ] Mapper 구현: WBS 의미 기반 매핑 + 확신도 플래그 + corrections.json 참조
- [ ] H-i-L 1 구현: LangGraph interrupt + 매핑 결과 표시 + 수정 입력 + corrections.json 누적
- [ ] **Atomizer 구현:** 레코드 생성 → 임베딩 → ChromaDB 적재 (오늘 날짜 레코드 추가)
- [ ] Reporter 구현: Sonnet 4.6 통합 보고서 생성 + history.csv 업데이트
- [ ] **Forecaster 구현:** ChromaDB 유사 이력 조회 + Opus 4.7 생산성 적정 여부 판단 + forecast.json 저장
- [ ] H-i-L 2 구현: LangGraph interrupt + 리스크 공종 목록 표시 + PM 선택
- [ ] **Optimizer 구현:** ChromaDB 과거 저하 패턴 검색 + Opus 4.7 원인 진단 + 회복 시나리오 조언
- [ ] Reporter ‖ Forecaster 병렬 실행 구조 (Mapper 완료 후 분기, Forecaster → H-i-L 2 → Optimizer 순차)
- [ ] End-to-End 테스트: 파일 드롭 → Atomizer DB 적재 → Forecaster 진단 → Optimizer 조언 출력 확인

---

### Week 4 — Dashboard + 경영진 데모 완성

v1과 동일한 2레이어 구조. 변경사항은 Layer 2 D-14 상세 화면에서 표시 내용이 달라집니다.

**Layer 2 변경사항:**

| 화면 영역 | v1 | v2 |
|----------|----|----|
| D-14 상세 | 품셈 달성률 + 예상 완료일 | 생산성 적정 여부 판단 + 원인 추론 + 회복 시나리오 |
| Optimizer 패널 | 인원 이동 수치 계산 | 과거 유사 사례 + 맥락 기반 조언 |

**Dashboard ↔ Pipeline 연결 방식** (v1과 동일):
```
Atomizer  → vector_db/ 업데이트
Reporter  → history.csv 업데이트
Forecaster → forecast.json 저장
Optimizer → optimizer.json 저장
    ↓
Dashboard → 파일 재읽기 → Layer 1 + Layer 2 자동 갱신
```

#### 진행 체크리스트

- [ ] **Layer 1 구현:** 6개 현장 현황 카드 (공정률·생산성 이상 공종·보고 상태)
- [ ] **Layer 2 구현:** 현장 상세 (S-curve·생산성 진단 결과·Optimizer 조언·보고서 링크)
- [ ] H-i-L 승인 버튼 구현 (터미널 방식 → Layer 2 화면 내 버튼)
- [ ] 파이프라인 실행 결과 → Layer 1·2 자동 갱신 연결 확인
- [ ] End-to-End 통합 테스트: 파일 드롭 → Layer 1 카드 갱신까지 전체 흐름 확인
- [ ] 데모 시나리오 리허설 5분 (Layer 1 → 파이프라인 실행 → Layer 2 갱신)
- [ ] AS-IS vs TO-BE 비교 슬라이드 1장
- [ ] 결과 문서화

**Week 4 체크포인트:** Layer 1(6개 현장 전체 현황) + Layer 2(실데이터 상세 + Optimizer 조언)가 경영진 앞에서 라이브 시연 가능한 상태.

---

## 5. PoC 성공 기준

| # | 성공 기준 | 검증 방법 |
|---|----------|---------|
| 1 | 작업일보 파일 투입 → 통합 Daily Report 자동 생성 | 라이브 실행 |
| 2 | Mapper: 의미 기반 자동 매핑 + H-i-L 1 검증·수정 피드백 루프 | 매핑 결과 + corrections.json 저장 데모 |
| 3 | Atomizer: 오늘 작업 기록이 Vector DB에 정상 적재됨 | ChromaDB 조회 화면 |
| 4 | Forecaster: "오늘 생산성이 오늘 조건 감안 시 적정한지" 판단 + 원인 추론 | Forecaster 출력 + 유사 사례 매칭 데모 |
| 5 | Optimizer: 과거 유사 저하 패턴 기반 구체적 조언 생성 | Optimizer 조언 화면 (수치 계산 아닌 맥락 기반 문장) |
| 6 | 6개 현장 전체 현황(Layer 1) → 현장 상세·파이프라인 연동(Layer 2) 대시보드 시연 | Streamlit 화면 시연 |

**처리 시간 목표:** 전체 파이프라인 5분 이내 (vs. 수작업 2~3시간)

> **PoC에서 검증하지 않아도 되는 것:**
> Forecaster 예측 정확도, Optimizer 조언의 현장 실효성, 시스템 운영 안정성 — 이는 Phase 2 과제입니다.
> "이런 흐름으로 작동한다"는 것만 보여주면 됩니다.

---

## 6. 리스크 및 대응

| 리스크 | 발생 가능성 | 대응 방안 |
|--------|-----------|---------|
| 현장 데이터 수령 지연 | 높음 | Week 1부터 요청 시작, 안 오면 가상 데이터로 선행 개발 |
| Synthetic history 품질 부족 | 중간 | 변동 패턴(우천·장비 대기·병행작업)을 충분히 반영. 패턴이 단조로우면 Forecaster 판단력이 약해짐 — Week 1에서 다양한 시나리오 설계 필요 |
| Parser work_content 텍스트 품질 저하 | 중간 | 작업일보에 작업 내용이 너무 짧게 기재되면 임베딩 의미가 옅어짐. 이 경우 Parser가 공종·날씨·인원 정보를 조합해 content를 재구성하도록 프롬프트 설계 |
| Vector DB 유사도 검색 오검색 | 중간 | 동일 공종·유사 조건 필터를 메타데이터로 먼저 거른 후 의미 검색. 필터 없는 전체 검색은 노이즈 많음 |
| Forecaster 판단이 단순 평균 비교와 차별화 안 됨 | 중간 | 프롬프트에 "날씨·조건 필터 적용 후 비교", "작업내용 텍스트에서 원인 추론" 명시. 조건 보정 없이 비교하면 DT와 차별화 안 됨 |
| Cold start (Synthetic history 부족) | 낮음 | Synthetic history 생성이 Week 1 완료 조건. WBS Man-Hour fallback 로직 병행 구현 |
| 대시보드 개발 시간 부족 | 중간 | Week 4 초반부터 집중. 문서화·리허설은 뒤로 밀고 대시보드 우선 |
| 라이브 시연 중 API 오류 | 중간 | 핵심 구간 사전 실행 결과 캡처 보유 |

---

## 7. PoC 이후 — Phase 2 진입 조건

| 항목 | 내용 |
|------|------|
| 실 데이터 누적 | Synthetic history 대신 실제 현장 이력 30일+ 축적 후 Forecaster 판단 정합도 검증 |
| 직종 호환성 테이블 | Optimizer가 "재배치 가능 여부"까지 판단하려면 직종 호환성 + 계약 범위 데이터 추가 필요 |
| CPM 선후행 관계 | Primavera 또는 공정 담당자 입력으로 의존관계 확보 → Optimizer 공기 영향 계산 정확도 향상 |
| 데이터 파이프라인 | 실제 이메일·카카오톡 연동 (IT 보안 승인 필요) |
| 현장 참여 | 현장 담당자 정기 H-i-L 참여 (주 1회 30분) + Optimizer 조언 실효성 피드백 수집 |
| 확산 준비 | 다른 현장 양식 수집 + Parser 범용화 (범용 설계로 진입 장벽 낮음) |

---

*작성: 조형준 프로 | 2026.05*
*v1 → v2 주요 변경: 품셈 기반 → Vector RAG 기반 컨텍스트 생산성 판단으로 전환*
*참조: `design/CPIA_기획서_v6.md` / `planning/CPIA_PoC_실행계획_v1.md`*
