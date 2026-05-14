# LangGraph State 스키마 — `pipeline/state.py`

> **Phase 0 합의 산출물.** 이 문서가 정의하는 `Activity` / `CPIAState` 는 7 에이전트 전체의 공유 데이터 계약. 변경 시 A·B 트랙 둘 다 OK 사인 필요.
>
> 작성: 2026-05-14 (A 트랙 초안) · 기반: `planning/CPIA_PoC_실행계획_v2.md`, `planning/review/데이터_분석_Mapper_가능성_검토.md`, `planning/simulation/PoC_구현가능성_시뮬레이션_v2.md`, 협업 spec `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`

---

## 0. 한눈에 보기

```
작업일보 1행 (시트1 인원 + 시트4 물량)
       ↓ Parser
Activity (parsed)  ─── trade='건축', company='남웅건설', work_content='기초 거푸집 설치'
       ↓ Mapper (Chroma wbs_master RAG → Sonnet rerank)
Activity (mapped)  ─── + wbs_activity_id, plan_total_qty, plan_mh
       ↓ MH 비율 분배
Activity (mapped)  ─── + assigned_workers, worker_source='mh_prorated'
       ↓ Atomizer (Chroma daily_activities 적재)
       ↓ Reporter ‖ Forecaster (Plan 기준 + RAG 이력 이중 비교)
       ↓ Optimizer
CPIAState.status = 'completed'
```

---

## 1. `Activity` — 작업일보 1행을 표현하는 공유 단위

```python
from __future__ import annotations
from typing import TypedDict, Literal


class Activity(TypedDict):
    # ── WBS 매핑 (Mapper 이후에 채워짐, 그 전엔 None) ──────────────────
    wbs_activity_id: str | None       # 예: 'TNMCB1F6501A03030034'
    l5_disc: str                      # '건축' / '설비' / '전기' / 'UT' / '제어' / '토목' / '공통가설'
    l6_main: str | None               # 예: '철근콘크리트공사'
    l7_sub: str | None                # 예: '거푸집공사'
    l7_5_activity: str | None         # 예: '기초공사 : 거푸집 공사'
    sub_work_area: str | None         # 예: 'B1F 연결공동구 FAB-WWT'

    # ── 작업일보 원천 (Parser 가 채움) ────────────────────────────────
    trade: str                        # 한글 정규화된 공종명 (= l5_disc)
    company: str                      # '남웅건설' (자연어 업체명)
    unit: str                         # 'M2' / 'Ton' / 'M3' / 'm' / 'PCS'
    today_qty: float                  # 320.0 (시트4 금일실적)
    work_content: str                 # '기초 거푸집 설치 / 우천 대응' (임베딩 원천)
    conditions: list[str]             # ['우천', '병행작업', '장비대기'] 등

    # ── MH 비율 분배 결과 (Mapper 이후) ──────────────────────────────
    assigned_workers: float           # 5.6 (소수 허용, 분배 결과는 float)
    worker_source: Literal['parsed', 'mh_prorated', 'user_corrected']

    # ── Master List 조회값 (Plan 기준 진단용) ────────────────────────
    plan_total_qty: float | None      # 500.0
    plan_mh: float | None             # 456.0 (Rev.2 최신 채택)

    # ── H-i-L 1 플래그 ──────────────────────────────────────────────
    requires_review: bool             # Mapper 확신도 < 0.7 이면 True
```

### 1.1 필드별 결정 근거

| 필드 | 왜 이 형태인가 |
|---|---|
| `wbs_activity_id` | Master List 4,228 행의 PK. `TNM(L1) C(?) B1F(L3) 6501(L4) A(L5) 03(L6) 03(L7) 0034(L7.5)` 합성 코드. Mapper 결과를 단일 string 으로 보존 |
| `l5_disc` ~ `l7_5_activity` | Master List 의 계층 라벨을 그대로 평탄화. Reporter / Forecaster 가 그루핑할 때 lookup 비용 0 |
| `trade` (=`l5_disc`) | 작업일보 시트4 (한글: 건축/설비/...) ↔ 시트1 (영문 약자: AR/ME/...) 매핑 후 **항상 한글 표기로 통일**. Parser LLM 이 §3 의 검증된 매핑 표를 프롬프트로 받아 정규화 |
| `company` | 자연어 업체명. 시트1 의 `BP` 컬럼이 `PH_X-001` (코드) ↔ `남웅건설` (자연어) 혼재라 Parser LLM 이 둘을 같은 회사로 묶고 자연어로 통일. 시트4 `업체명` 컬럼이 자연어이므로 join 키 일관성 ↑ |
| `unit` | Master List 원본 표기 그대로 (`M2`/`Ton`/`M3`). 작업일보가 소문자 (`m2`/`ton`) 일 경우 Parser 가 대문자 정규화 |
| `today_qty` | 시트4 `금일실적[C]` 컬럼. **None 인 행이 1,193행 중 1,068행 (89.5%)** — Parser LLM 이 문맥 (작업내용·총물량·전일누적) 으로 "작업없음 0" 인지 "미입력 → state 제외" 인지 판단 (§3.2 ⑤) |
| `work_content` | 임베딩 입력의 핵심 원천. **절대 누락 금지** (v2 spec 의 핵심 룰). 시트1 의 `금일 작업사항` + 시트4 의 `대표물량_작업 내용` 을 join 한 결과 |
| `assigned_workers: float` | MH 비율 분배는 정수로 안 떨어짐 (예: 11.6%). Forecaster 입력 정밀도를 위해 float. H-i-L 정정 시 사용자가 정수로 보정 가능 |
| `worker_source` | 세 출처를 구분: `parsed` = 작업일보에 명시된 그대로 (드문 케이스), `mh_prorated` = Mapper 후 MH 비율로 추정 (기본), `user_corrected` = H-i-L 1 에서 사용자 보정 |
| `plan_total_qty`, `plan_mh` | Master List Rev.2 값. Forecaster 의 Plan 기준 단위당 생산성 = `plan_total_qty / plan_mh` |
| `requires_review` | Mapper 의 Sonnet rerank confidence < 0.7 이면 True → LangGraph `interrupt(hil_1)` 트리거 |

### 1.2 결정 근거 — 실 데이터 인용

#### MH 비율 분배가 정당한 이유 — `WV ≡ MH × 4.9`

Master List 의 `WV.` 컬럼 (Work Volume) 의 정체를 실 데이터로 확인:

```
$ uv run --with openpyxl /tmp/cpia_wv_probe.py
[Master List 3,720 데이터 행]
WV/MH 비율: min=4.8592, max=5.0000, median=4.9020, mean=4.9038
전체 WV 합 86,774,566 / MH 합 17,705,347 = 4.9010

공종별 median:
  UT     4.9026  / 건축   4.9018  / 설비   4.9018
  소방   4.9018  / 전기   4.9021  / 제어   4.9022  / 토목   4.9017
```

→ 공종 무관 거의 일정한 단일 환산 계수. CPRS (Construction Progress Reporting Schedule) 의 가중 단위 환산. **"WV 비율 분배 = MH 비율 분배" 와 수학적으로 동치**. 새 개념 도입 없이 MH 만 사용.

#### 분배 분포 예시 — 남웅건설 B1F 연결공동구 10개 Activity

```
Activity                              | 단위 | qty   | MH   | share
거푸집공사 > 1층 바닥 Slab            | M2  | 1,500 | 456  |  4.1%
거푸집공사 > RC Wall & Column         | M2  | 3,200 | 380  |  3.4%
거푸집공사 > 기초                     | M2  | 500   | 456  |  4.1%
철근공사 > 1층 바닥                   | Ton | 100   | 623  |  5.6%
철근공사 > RC Wall & Column           | Ton | 150   | 1215 | 10.9%  ← 최대
철근공사 > 기초                       | Ton | 200   | 623  |  5.6%
콘크리트 > 1층 바닥                   | M3  | 400   | 456  |  4.1%
콘크리트 > RC Wall & Column           | M3  | 700   | 456  |  4.1%
콘크리트 > 기초 (철근)                | M3  | 1,600 | 456  |  4.1%
콘크리트 > 기초 (버림)                | M3  | 130   | 456  |  4.1%
Σ MH = 11,154
```

자잘한 활동 (3.4%) ~ 대형 활동 (10.9%) 까지 합리적 분포. 0 근처 outlier 없음.

---

## 2. `CPIAState` — LangGraph 그래프 전체가 들고 다니는 상태

```python
class CPIAState(TypedDict):
    # ── 입력 ───────────────────────────────────────────────
    run_id: str                       # UUID, FastAPI /run 응답
    date: str                         # 'YYYYMMDD' (= 작업일보 일자)
    input_files: list[str]            # data/input/YYYYMMDD/*.xlsx 경로

    # ── 파이프라인 누적 ────────────────────────────────────
    raw_texts: dict[str, str]         # filename → 시트별 텍스트 dump
    parsed: list[Activity]            # Parser 완료 후
    mapped: list[Activity]            # Mapper + MH 분배 완료 후
    hil_1_corrections: dict           # H-i-L 1 사용자 입력 (Dashboard → /resume)
    atomized_ids: list[str]           # Chroma daily_activities 에 적재된 record ID

    # ── 분기 결과 (Mapper 이후 Reporter ‖ Forecaster) ───────
    report_md: str                    # Reporter 출력 (통합 일일 보고서)
    forecast: list[dict]              # Forecaster 출력 (공종별 진단)
    hil_2_selection: list[str]        # H-i-L 2: PM 이 고른 trade (Optimizer 대상)
    optimizer_advice: list[dict]      # Optimizer 출력 (조언)

    # ── 상태 추적 ──────────────────────────────────────────
    current_node: str                 # 'collector' / 'parser' / ... / 'optimizer'
    status: Literal[
        'running',
        'waiting_hil_1',              # Mapper 이후 인터럽트
        'waiting_hil_2',              # Forecaster 이후 인터럽트
        'completed',
        'failed',
    ]
```

### 2.1 LangGraph 그래프 트리거 — interrupt 위치

```
Collector → Parser → Mapper ──┬── [interrupt:hil_1] ── Atomizer
                              │   (requires_review=True 있을 때만)
                              │
                              └── Reporter
                                       ‖
                                  Forecaster ── [interrupt:hil_2] ── Optimizer
                                                (risk_level='이상' 있을 때만)
```

- `interrupt(hil_1)`: `mapped` 중 `requires_review=True` 인 항목 있으면. `status = 'waiting_hil_1'`. Dashboard 가 `/resume` 호출 → `hil_1_corrections` 채움 → `mapped` 재구성 → Atomizer 진입.
- `interrupt(hil_2)`: `forecast` 중 `risk_level in ('주의','이상')` 인 항목 있으면. `status = 'waiting_hil_2'`. PM 이 Optimizer 의뢰 공종 선택 → `hil_2_selection` 채움 → Optimizer 진입.

---

## 3. Parser — LangGraph 노드로 LLM 단일 호출 (정규식·sealed dict 없음)

작업일보 양식은 시트 간 일관성이 낮다 — 시트1 의 `공종(Dis)` 는 영문 약자 (`AR`/`ME`/`EL`/...), 시트4 는 한글, `BP` 컬럼은 PH 코드 (`PH_X-001`) 와 자연어 (`남웅건설`) 가 혼재. 정규식이나 sealed dict 로 처리하면 엣지 케이스가 계속 새어나오므로 **정규화 전체를 Sonnet 4.6 의 structured output 한 번에 위임**.

### 3.1 LangGraph 노드 골격

```python
from __future__ import annotations
from typing import TypedDict
from langchain_anthropic import ChatAnthropic

class ParserOutput(TypedDict):
    activities: list[Activity]      # state.py 의 Activity 그대로 재사용 (Pydantic 별도 X)

_parser_llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)\
    .with_structured_output(ParserOutput)

def parser_node(state: CPIAState) -> dict:
    prompt = _build_parser_prompt(state["raw_texts"])
    out: ParserOutput = _parser_llm.invoke(prompt)
    return {"parsed": out["activities"], "current_node": "parser"}
```

- `with_structured_output(TypedDict)` — LangChain 표준 패턴. 응답 schema 강제 + JSON 파싱 자동.
- 노드 함수는 dict 부분 반환 → LangGraph 가 state 자동 merge.

### 3.2 프롬프트가 책임지는 정규화 5가지

| # | 입력 패턴 (실 데이터) | 출력 (`Activity` 필드) |
|---|---|---|
| ① | `시트1.공종='AR'` ↔ `시트4.공종='건축'` (동일 BP사 기준 정합) | `trade='건축'`, `l5_disc='건축'` |
| ② | `시트1.BP='PH_X-001'` (R67) + `시트1.BP='남웅건설'` (R68, 같은 회사 두번째 줄) | `company='남웅건설'` 하나로 합치고 인원 합산 |
| ③ | `시트1.인원 = 조출+주간+연장+야간+철야 = Total` | 업체 일별 총 인원 (이후 MH 비율 분배의 분자) |
| ④ | `시트4.대표물량_작업내용 = '기초 거푸집 설치'` + `시트1.금일작업 = '기초 콘크리트 + 거푸집 병행'` | `work_content` 에 두 텍스트 자연어 join (임베딩 원천 보존) |
| ⑤ | `시트4.금일실적 = None` (1,193행 중 1,068행 = 89.5%) | LLM 이 문맥 (작업내용·총물량·전일누적) 으로 "작업없음 0" 인지 "미입력 → state 제외" 인지 판단 |

### 3.3 프롬프트에 주입하는 검증된 매핑 예시 (cross-walk 실 데이터)

LLM 이 약자 매핑을 환각하지 않도록 실 데이터 정합도를 예시 표로 직접 주입:

```
[검증된 약자 ↔ 한글 매핑] (M15X PH-3 실 작업일보, 동일 BP사 기준 cross-walk)
  AR  →  건축      (19 / 19, 100%)
  ME  →  설비      (20 / 21, 95%; 'ME'가 '전기' 1건은 작성 오타로 보정)
  EL  →  전기      (10 / 11, 91%; 'EL'이 '제어' 1건은 작성 오타로 보정)
  UT  →  UT        (22 / 22, 100%)
  IN  →  제어      (3 / 3)
  CI  →  토목      (1 / 1)
  TE  →  공통가설  (8 / 8)
  소방설비 → 소방설비, 소방전기 → 소방전기 (한글 그대로)
```

### 3.4 결정성 보장 — 안전장치 3개

1. **`with_structured_output(ParserOutput)`** — 자유 텍스트 응답 금지, schema 강제.
2. **`temperature=0`** — 동일 입력 동일 출력 유도.
3. **GATE 2 (5/22) 검증 게이트** — 샘플 5개 작업일보 × 2회 연속 실행, `parsed` 결과 byte-level diff 9/10 일치. 회귀 테스트로 영속화 (`tests/test_parser_determinism.py`).

---

## 4. PoC 범위 한정

| 항목 | PoC 적재 범위 | 확장 시점 |
|---|---|---|
| `Activity` 인스턴스 (state 안) | 남웅건설 + 건축 (`l5_disc='건축'` ∩ `company='남웅건설'`) | Phase 2 시 인덱스 안 바꾸고 확장 가능 |
| Chroma `wbs_master` 임베딩 | 남웅건설 + 건축 = **189 row** | Phase 2 시 incremental upsert |
| Chroma `daily_activities` | PoC 기간 동안 남웅건설 건축 작업일보만 | 동일 |
| Synthetic history | 남웅건설 + (철근 / 거푸집 / 콘크리트) × 30일 = 약 90 레코드 | 동일 |
| Master List → PG `activity_master` | 남웅건설 + 건축 189 row + 메타 위해 다른 업체 일부 (Mapper 가 잘못 골라도 PoC 범위 밖이면 H-i-L 정정으로 회피) | Phase 2 시 점진 |

근거: `planning/review/데이터_분석_Mapper_가능성_검토.md` R3 의 권고. 작업일보 4.물량 건축 152개 유니크 텍스트 중 30~40% 가 FAB 특화 (System Ceiling / CMP / S/C) 라 Master List 매칭 불가. **남웅건설 RC 3공종 (철근·거푸집·콘크리트) 은 매칭 6/7 자명** — 실 데이터로 검증됨.

---

## 5. 미해결 사안 (구현·운영 단계 결정)

| # | 사안 | 가설 | 결정 시점 |
|---|---|---|---|
| ① | Parser LLM 결정성 검증 | §3.4 의 게이트 (샘플 5 × 2회 연속, 9/10 byte-level diff 일치) 가 충분한지. 불충분 시 schema 더 좁히거나 few-shot 보강 | GATE 2 (5/22) |
| ② | Master List MH outlier (`1500 M²/MH 3200` 같은 비현실값) | Plan 기준은 Forecaster 가 사용하지만 **참고용**. RAG 이력 기준이 메인 (이중 비교 §6 forecast). 공종 단위 Trim mean 보정은 Phase 2 | Forecaster 구현 시 (5/30~) |
| ③ | `requires_review` 임계값 (Sonnet rerank confidence < 0.7) | 초기 0.7, GATE 3 (5/29) 통합 테스트에서 H-i-L 1 발동률 보고 조정 | GATE 3 |
| ④ | LLM 호출 비용 vs 응답 지연 | Parser/Mapper/Reporter 각 1회 Sonnet + Forecaster/Optimizer 각 1회 Opus = run 당 ~5회. 5분 데모 목표 안에 들어오는지 GATE 2 측정 | GATE 2 |

---

## 6. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-14 | 초안 — brainstorming 결과 통합 (RAG 매핑 + MH 분배 + Plan/RAG 이중 비교 + PoC 범위 한정) | A 트랙 |
