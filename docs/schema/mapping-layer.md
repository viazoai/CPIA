# 매핑 레이어 설계 — `pipeline/agents/mapper.py`

> **Phase 0 합의 산출물 (state.md / postgres.md / example-walkthrough.md 보완).** 이 문서가 정의하는 Mapper 의 6단계 흐름·WA 결정 4단계·다운스트림 grain 은 7 에이전트 전체의 매핑 계약. 변경 시 A·B 트랙 둘 다 OK 사인 필요.
>
> 작성: 2026-05-14 (A 트랙 초안) · 기반: brainstorming 결과 + 실 작업일보 79건 시뮬 (v1·v2·v3) + 기존 schema 문서

---

## 0. 한눈에 보기

```
Parser (4시트 통합)
   ↓ ParsedDailyReport
Mapper (안 A v3)
   ① BP filter (PG)
   ② 임베딩 input 텍스트 (단순)
   ③ Chroma wbs_master Top-K=15 → BP filter ∩ → 후보 ≤ 8
   ④ LLM input 텍스트 (풍부)
   ⑤ LLM 분류 (GPT-5.1)
   ⑥ WA 결정 4단계
   ↓ Activity (mapped: wa, l6_main, mapping_conf, mapping_source)
Atomizer → Reporter ‖ Forecaster → Optimizer
```

**매핑 키 = `(WA, L6 Work PKG-1)`** — Master List 102개 그룹. L7 칼럼은 별도 매핑하지 않고 Forecaster RAG 검색이 `work_content` 임베딩 + `unit` 필터로 대체 (L7-C 안).

**시뮬 결과 (PoC 79건):** 안 A v3 자동 98.7% (78/79) + H-i-L 1 보완 후 100%. 토큰 in 84,474 / out 8,112 / 시간 331s. 안 B 대비 입력 토큰 32% 절감.

---

## 1. 매핑 키 = `(WA, L6 Work PKG-1)`

```
매핑 키:           (work_area_code, l6_main)
예시:              (FAB, ACID배기설비공사) / (CUB, 철근콘크리트공사)
전체 카디널리티:    102개 (Master List 3,720 row → 102 그룹)
PoC 후보 풀:       남웅 2 + 세보 19 + 창원 9 + 기타
```

### 1.1 결정 근거 (실 데이터)

| 기준 | 결과 | 근거 |
|---|---|---|
| 압축률 | 3,720 → 102 (36배) | `/tmp/cpia_mapping_probe_2.py` |
| BP filter 효과 | 후보 평균 3, max 19 | 같은 probe |
| 단위 혼재 처리 | MH 통일 (`qty/MH` 또는 진척률 metric) | 사용자 결정 (L6 안에 M2/M3/Ton 섞임 허용) |
| L7 결정 누락 | Forecaster RAG 의 `work_content` 임베딩 + `unit` filter 가 대체 | L7-C 안 |
| WA 결정 | 별도 4단계 알고리즘 (§4) | 작업일보에 WA 단서 부족 |

### 1.2 PoC vs 확장

| 항목 | PoC (5/19) | GATE 2 (5/22) | GATE 3 (5/29) |
|---|---|---|---|
| 후보 풀 | 남웅+세보+창원 + 기타 (자명 매핑 가능 BP사) | 전체 80 BP사 점진 | 전체 102 (WA, L6) |
| 매핑 키 | (WA, L6) | (WA, L6) | (WA, L6) |
| 정확도 목표 | 자동 ≥ 95% + H-i-L 100% | 자동 ≥ 97% | 자동 ≥ 99% |

---

## 2. Parser 통합 스키마 — `ParsedDailyReport`

```python
class ParsedDailyReport(TypedDict):
    """1 작업일보 xlsx — 4시트 통합 파싱 결과."""
    report_date: str
    project: str

    bp_summaries: list[BPSummary]              # 시트1 BP사 × 공종 row
    job_allocations: list[JobAllocation]        # 시트2 BP사 × 직종 row
    equipment_allocations: list[EquipmentAllocation]  # 시트3 BP사 × 장비 row
    activities: list[Activity]                  # 시트4 작업 line (= 매핑 대상)


class BPSummary(TypedDict):
    bp_code: str | None             # 'PH_X-001'
    company: str                    # '남웅건설'
    disc_abbrev: str | None         # 'AR' (영문 약자, → trade 한글로 정규화 후 Activity 에 반영)
    zone: str | None                # 'FAB/CUB' / 'FAB' / 'CUB'
    scope: str | None               # 'A구간'
    work_text_yesterday: str | None # 시트1 C6
    work_text_today: str | None     # 시트1 C7  ★ WA 추론 단서 (GATE 2)
    work_text_tomorrow: str | None  # 시트1 C8
    today_incr_total: int           # 시트1 C28 (금일 신규 투입 Total)
    today_cum_total: int            # 시트1 C35 (금일 누적 인원 Total)


class JobAllocation(TypedDict):
    """시트2 — Cum.T 헤더 라벨 의미: '금일누계 [Cum., 9/03 부터 9/25]'"""
    bp_code: str | None
    company: str
    disc_abbrev: str | None
    job_type: str                   # '배관공' / '덕트공' / '공사관리자' / ...
    workers_cum_t: int              # 시트2 C23 (금일누계)


class EquipmentAllocation(TypedDict):
    """시트3 — Cum.T 헤더 라벨: '금일투입누계 [Cum., 9/03 부터 9/25]'"""
    bp_code: str | None
    company: str
    equipment_big: str              # '굴삭운반기계류'
    equipment_mid: str              # 'Back Hoe'
    equipment_spec: str | None      # '2㎥ 미만'
    count_cum_t: int                # 시트3 C23 (금일투입누계)
```

`Activity` 는 `state.md §1` 그대로. Mapper 결과는 `Activity.l5_disc`/`l6_main`/`sub_work_area`/`wbs_activity_id`/`mapping_conf`/`mapping_source` 채움.

### 2.1 Parser 처리 규칙

1. **시트 분리 X, BP사 단위 합본** — 매핑 대상은 시트4 line 이지만 LLM input 컨텍스트는 4시트 join.
2. **헤더 라벨 의미 적용** — 숫자만 추출 X. 시트2 C23 = "비계공 19,999명-일 (금일누계 Cum.T, 9/3~9/25)" 라벨 명시화.
3. **Noise 제거** (시뮬에서 확인된 패턴):
   - 시트2 `"기능공 투입 Total"` 패턴 row (BP사 합계 noise) 제외
   - 시트2 관리자 직종 (BP소장/공사관리자/안전관리자/품질관리자/일반관리자 등) 매핑 단서 제외
   - 시트4 `today_qty=None` (89.5%) → LLM 이 "작업없음" vs "미입력" 판단
4. **단위 정규화** — `m2`/`M2`, `ton`/`Ton` 대문자 통일
5. **공종 약자 → 한글** — `AR→건축`, `ME→설비`, `EL→전기`, `UT→UT`, `TE→공통가설`, `IN→제어`, `CI→토목` cross-walk 표 LLM 프롬프트 주입 (`state.md §3.3`)

---

## 3. Mapper 6단계 흐름 (안 A v3)

```python
def mapper_node(state: CPIAState) -> dict:
    mapped: list[Activity] = []
    for activity in state["parsed"]:
        # ① BP filter
        cand_pool = pg.query("""
            SELECT DISTINCT wa, l6_main FROM activity_master
            WHERE company = $1
        """, activity["company"])

        # ② 임베딩 input 텍스트 (단순)
        embed_text = build_embedding_input(activity)

        # ③ Chroma wbs_master 검색 → BP filter ∩
        topk = chroma["wbs_master"].query(
            query_embeddings=[embed(embed_text)],
            n_results=15,
        )
        candidates = [t for t in topk if (t.wa, t.l6_main) in cand_pool][:8]

        # ④ LLM input 텍스트 (풍부)
        llm_text = build_llm_input(activity, parsed_report)

        # ⑤ LLM 분류
        result = llm_classify(llm_text, candidates)  # {choice, confidence, reason}

        # ⑥ WA 결정 4단계
        wa = resolve_wa(activity, result, cand_pool)

        # Activity 채움
        activity.update(
            wa=wa.value, l6_main=candidates[result.choice].l6_main,
            l5_disc=..., wbs_activity_id=..., sub_work_area=...,
            plan_total_qty=..., plan_mh=...,
            mapping_conf=result.confidence, mapping_source=wa.source,
            requires_review=(result.confidence < 0.7 or wa.source == 'hil_required'),
        )
        mapped.append(activity)
    return {"mapped": mapped, "current_node": "mapper"}
```

### 3.1 임베딩 input vs LLM input 분리 — 핵심 결정

v2 시뮬에서 동일 input 사용 시 임베딩이 BP사 컨텍스트 큰 숫자 (배관공 165,168 등) 에 휘둘려 정답 누락 발견 (97.5%). v3 분리 적용 후 98.7% 회복.

```python
def build_embedding_input(activity):
    """후보 좁히기용 — 작업line 자체만, BP 컨텍스트·숫자 제외."""
    return (
        f"회사: {activity.company}\n"
        f"작업: {activity.work_content}\n"
        f"단위: {activity.unit}\n"
        f"공종: {activity.trade}"
    )

def build_llm_input(activity, parsed_report):
    """최종 분류용 — BP사 단위 풍부 컨텍스트 (4시트 join)."""
    bp_ctx = build_bp_context(activity.company, parsed_report)
    return (
        build_embedding_input(activity) + "\n"
        f"단위: {activity.unit}  |  금일실적: {activity.today_qty or '-'}  |  계획: {activity.plan_total_qty or '-'}\n"
        f"[BP사 단위 컨텍스트]\n{bp_ctx}"
    )
```

`build_bp_context()` 출력 예시 (R452 세보엠이씨 ACID 배기덕트):
```
  · [시트1] 주요작업 텍스트 (BP사 기재): 미기재
  · [시트1] 금일 신규 투입 인원 (Incr., 09/25): 1,387명
  · [시트1] 금일 누적 인원 (Cum., 09/25): 364,847명-일
  · [시트2] 기능공 직종 (금일누계 Cum.T = 9/3 부터 9/25 누계):
      - 배관공: 165,168명-일
      - 덕트공: 83,295명-일
      - 용접공: 20,903명-일
      ...
  · [시트3] 투입 장비 (금일투입누계 Cum.T = 9/3 부터 9/25):
      - 고소작업장치류/고소작업대 (수직형 7M 이하): 26,044회-일
      ...
```

### 3.2 시뮬 검증 (PoC 79건)

| 버전 | 안 | 자동 정확도 | in 토큰 | 시간 | 핵심 변경 |
|---|---|---|---|---|---|
| v2 | A | 97.5% | 85,923 | 359s | 풍부 input 동일 (숫자 오염) |
| v2 | B | 100% | 124,703 | 360s | LLM 직접 |
| **v3** | **A** | **98.7%** | **84,474** | **331s** | **임베딩·LLM input 분리** |
| v3 | B | 100% | 123,653 | 359s | LLM 직접 |

v3 안 A 오답 1건 (R459 "FA DUCT 설치" → 'CABINET배기설비공사' 잘못, conf 0.55) — H-i-L 1 자동 발동으로 보완.

**채택 = 안 A v3** 이유: ① H-i-L 1 보완 후 100%, ② 토큰 32% 절감, ③ GATE 3 확장성 (후보 풀 커질수록 임베딩 가치 ↑).

---

## 4. WA 결정 4단계 알고리즘

매핑 키 `(WA, L6)` 중 **L6 는 LLM 이 결정**하고 **WA 는 단계적으로 결정**. 이유: 작업일보의 Zone 컬럼이 'FAB/CUB' (둘 다) 표기, BP 코드도 단일 — WA 단서 부족.

```python
def resolve_wa(activity, l6_result, bp_cand_pool):
    # 1단계 — BP scope 단일
    wa_set = {(wa, l6) for wa, l6 in bp_cand_pool}
    bp_wa = {wa for wa, _ in wa_set}
    if len(bp_wa) == 1:
        return WAResolution(value=bp_wa.pop(), source='auto_bp_single')

    # 2단계 — L6 결정 후 그 L6 의 WA 단일
    l6_wa = {wa for wa, l6 in wa_set if l6 == l6_result.l6_main}
    if len(l6_wa) == 1:
        return WAResolution(value=l6_wa.pop(), source='auto_l6_single')

    # 3단계 — 시트1 자연어 LLM 추론 (PoC 비활성, GATE 2 활성)
    if GATE_2_ENABLED and bp_summary.work_text_today:
        wa_inferred = llm_infer_wa(bp_summary.work_text_today, l6_wa)
        if wa_inferred.confidence >= 0.7:
            return WAResolution(value=wa_inferred.wa, source='auto_sheet1_text')

    # 4단계 — H-i-L 1 강제
    return WAResolution(value=None, source='hil_required')
```

### 4.1 80 BP사 분포 (실 데이터, `/tmp/cpia_wa_resolution.py`)

| 단계 | BP사 수 | 비율 | 케이스 |
|---|---|---|---|
| 1단계 자동 (BP scope 단일) | 58 | **72.5%** | CUB 단일 21 + FAB 단일 37 (예: 세보엠이씨 = FAB) |
| 2단계 자동 (L6 후 단일) | — (멀티 WA 중 일부 L6 단일) | — | 예: 창원 전등설비공사 = FAB 만 |
| 3단계 자동 (시트1 자연어) | — | — | GATE 2 부터 활성 — 멀티 WA + 시트1 텍스트 보유 BP사 2곳 |
| 4단계 H-i-L | 멀티 WA + L6 겹침 | 25% | 예: 남웅건설 (CUB+FAB 둘 다 철콘) |

### 4.2 PoC 79건 WA 분포

| 단계 | 건수 | 비율 |
|---|---|---|
| 1단계 자동 (세보엠이씨 24건 모두 FAB) | 24 | 30% |
| 2단계 자동 (창원 전등 5 + 화재/유도 2) | 7 | 9% |
| 4단계 H-i-L 1 (남웅 47 + 창원 CABLE 포설 1) | 48 | **61%** |

PoC 단계 H-i-L 1 부담 ↑ 인 이유 = 남웅건설이 멀티 WA + L6 겹침 + 시트1 자연어 없음. GATE 2 부터 시트1 자연어 보유 BP사 다루며 3단계 활성화로 감소 기대.

---

## 5. Master List 적재 — `scripts/load_master_list.py`

1회 실행으로 PG `activity_master` + Chroma `wbs_master` 동시 채움.

```bash
# PoC 초기 (남웅 + 세보 + 창원 + 자명 매핑 가능 기타)
uv run scripts/load_master_list.py \
  --filter "company IN ('남웅건설', '세보엠이씨', '창원기전')"

# GATE 2 전체 적재
uv run scripts/load_master_list.py --upsert
```

### 5.1 PG `activity_master` (`postgres.md §2` 그대로)

`(wbs_activity_id PK, l5_disc, l6_main, l7_sub, l7_5_activity, company, unit, plan_total_qty, plan_mh_rev2, plan_start, plan_finish, ...)` — Mapper SQL filter + Forecaster Plan 값 조회.

### 5.2 Chroma `wbs_master` 컬렉션

```python
# 1 doc = 1 (WA, L6) 그룹 (전체 102, PoC 부분 적재)
chroma["wbs_master"].add(
    ids=[f"{wa}|{l6_main}"],
    embeddings=[embed(doc_text)],
    metadatas=[{
        "wa": wa,
        "l5_disc": l5_disc,
        "l6_main": l6_main,
        "units": ",".join(units),       # 'M2,Ton,M3' (BP filter 보조)
        "companies": ",".join(companies),
    }],
    documents=[doc_text],
)

# doc_text 구조:
# Work Area: FAB (FAB 명칭)
# Discipline (L5): 설비
# Work PKG-1 (L6): ACID배기설비공사
# Work PKG-2 (L7): ACID배기덕트설치공사, 장비설치공사
# Units: M2, ea
# Activities (L7.5 sample): ...
# Companies: 세보엠이씨, 김앤드이, ...
```

차원: text-embedding-3-small-ai-board-test (1536d).

---

## 6. 다운스트림 영향 (Atomizer / Reporter / Forecaster)

매핑 결과 grain 이 후속 노드에 어떻게 연결되는지 — 매핑 ↔ 생산성 분석 cascade.

### 6.1 Atomizer — Chroma `daily_activities` 적재

```python
chroma["daily_activities"].add(
    embeddings=[embed(activity.work_content)],   # 자연어 임베딩 — L7 칼럼 없이도 변별
    metadatas=[{
        "date": state.date,
        "run_id": state.run_id,
        "company": activity.company,
        "l5_disc": activity.l5_disc,
        "l6_main": activity.l6_main,            # 매핑 결과
        "wa": activity.wa,                       # 매핑 결과
        "unit": activity.unit,                   # 단위 균질 보장용
        "today_qty": activity.today_qty,
        "assigned_workers": activity.assigned_workers,
        "conditions": activity.conditions,
    }],
    documents=[activity.work_content],
)
```

### 6.2 Reporter — `l5_disc` / `l6_main` group by

매핑된 `l5_disc`/`l6_main` 별 group by 해서 일일 보고서 MD 섹션 구성. PG `daily_reports` 저장.

### 6.3 Forecaster RAG 검색 — grain 일치 ★

```python
chroma["daily_activities"].query(
    query_embeddings=[embed(today_activity.work_content)],
    where={
        "company": today_activity.company,
        "l6_main": today_activity.l6_main,      # 매핑 결과 = RAG 검색 키 일치
        "unit":    today_activity.unit,          # 단위 균질 — m² 끼리, Ton 끼리
    },
    n_results=5,
)
```

→ **단위 필터로 평균 metric 의미 보장** (24 m²/인일 평균이 m² 끼리만). L7 칼럼 미사용, work_content 자연어 임베딩이 변별.

Plan + RAG 이중 비교 (`example-walkthrough.md` PART E) 진행. `forecasts.plan_diff_pct`, `forecasts.rag_diff_pct` 컬럼 분리.

### 6.4 Optimizer — `similar_cases` JSONB 재사용

Forecaster 의 `similar_cases` 5건 + 같은 (company, l6_main, unit) 의 회복 패턴 검색.

### 6.5 Cascade 의미

| 매핑 결과 | 다운스트림 영향 |
|---|---|
| 정확 (자동 98.7% + H-i-L 100%) | Atomizer 적재 정확 → 미래 RAG 자산 정합 → Forecaster 진단 의미 |
| 오답 1건 (가령 SP 배관 → 일반공조) | Chroma 영구 적재 → 다음 SP 배관 진입 시 검색 누락 → RAG n_similar ↓ |

→ H-i-L 1 이 cascade 차단의 핵심 안전망. confidence 임계값 0.7 + WA 4단계 H-i-L 강제.

---

## 7. H-i-L 1 트리거 + `mapping_corrections` 자가학습

### 7.1 트리거 조건 (OR)

1. Mapper LLM `confidence < 0.7`
2. WA 결정 4단계 도달 (`mapping_source = 'hil_required'`)
3. BP filter 후 후보 0개 (Master 미등록 BP사 — 운영 단 데이터 통일로 거의 0)

### 7.2 H-i-L 흐름

```
Mapper → Activity.requires_review=True
   ↓
LangGraph interrupt(hil_1)
CPIAState.status='waiting_hil_1'
   ↓
B 트랙 Dashboard 가 /status polling 으로 감지
Mapping Review Modal 표시
   ↓
사용자 선택 → POST /api/hil/resume → FastAPI /resume
   ↓
PG mapping_corrections INSERT:
   {
     run_id, date, work_content, company, trade,
     original:  {wbs_activity_id, l6_main, wa, confidence},
     corrected: {wbs_activity_id, l6_main, wa},
     correction_type: 'replace' | 'split' | 'reject',
   }
   ↓
LangGraph 재개 → Activity 재구성 → Atomizer 진입
```

### 7.3 자가학습 — 다음 run 진입 시

```python
# Mapper 진입 직후
corrections = pg.query("""
    SELECT corrected, count(*) AS n
    FROM mapping_corrections
    WHERE company=$1 AND trade=$2
      AND similarity(work_content, $3) > 0.85
    GROUP BY corrected
    ORDER BY n DESC LIMIT 1
""", activity.company, activity.trade, activity.work_content)

if corrections and corrections[0].n >= K:    # K=3 (GATE 3 결정)
    # 자동 적용 — LLM 호출 생략
    return corrections[0].corrected

# 그렇지 않으면 corrections 컨텍스트를 few-shot 으로 프롬프트 주입
prompt += "\n[과거 정정 사례 — 유사 work_content]\n" + format_corrections(corrections)
```

### 7.4 PoC 시뮬 기준 H-i-L 발동률

- conf < 0.7 트리거: 1건 (R459)
- WA 4단계 트리거: 48건 (남웅 47 + 창원 CABLE 포설 1)
- 합 ~49건 / 79 = **62%** — PoC 단계 사용자 부담 ↑
- GATE 2 시트1 자연어 LLM 추론 활성화 시 감소 기대 (창원기전·중원엔지니어링 등)

---

## 8. 미해결 사안 + 확장 경로

### 8.1 미해결 사안

| # | 사안 | 현재 가설 | 결정 시점 |
|---|---|---|---|
| ① | R459 FA DUCT 같은 임베딩 매칭 실패 | Master `wbs_master` doc 어휘 풍부화 (도메인 약자 풀이: FA→Fresh Air, EHP→Electric Heat Pump). 또는 Top-K 8→15 확대 | GATE 2 (5/22) |
| ② | confidence 임계값 0.7 | PoC 시뮬 기준 적정. H-i-L 1 발동률 보고 조정 | GATE 3 (5/29) |
| ③ | 시트1 자연어 LLM 추론 (WA 3단계) | PoC 비활성. 멀티 WA + 시트1 보유 BP사 (창원기전·중원엔지니어링) 케이스에서 GATE 2 활성 | GATE 2 |
| ④ | `mapping_corrections` 자동 적용 K 값 | 초기 K=3. GATE 3 통합 테스트에서 조정 | GATE 3 |
| ⑤ | 시트2 직종 noise 추가 패턴 | "기능공 투입 Total" 외 BP사별 특이 noise 발견 시 키워드 추가 | GATE 2 모니터링 |
| ⑥ | Master 미등록 BP사 처리 | 운영 단 데이터 통일 정책 (cross-walk 미도입). 발생 시 H-i-L | 운영 진입 시 |
| ⑦ | Plan 일자 필터 Rev 선택 | Master List Rev.0 vs Rev.2 (4~6개월 차이). 활성 판단 기준 | `load_master_list.py` 작성 시 |
| ⑧ | Plan MH outlier (380~4184) | Forecaster 가 Plan 단독으로 진단하면 위험. RAG 결합으로 회피 | Forecaster 구현 시 |

### 8.2 PoC vs GATE 2/3 확장 경로

| 항목 | PoC (5/19) | GATE 2 (5/22) | GATE 3 (5/29) |
|---|---|---|---|
| 매핑 키 | (WA, L6) | (WA, L6) | (WA, L6) |
| 임베딩 input | 단순 (작업line 자체) | 동일 | 동일 |
| LLM input | 풍부 (4시트 join) | 동일 | 동일 |
| 후보 풀 | 남웅+세보+창원 + 자명 BP사 | 전체 80 BP사 점진 | 전체 102 그룹 |
| WA 결정 | 1·2·4단계 | + 3단계 활성 | 동일 |
| H-i-L 1 자가학습 | 수동 누적 | corrections feedback 시작 | 자동 적용 (K=3) |
| 결정성 검증 | 시뮬 79건 | 샘플 5×2회 byte-diff (`state.md §3.4`) | 100건 회귀 |
| 정확도 목표 | 자동 ≥ 95% + H-i-L 100% | 자동 ≥ 97% | 자동 ≥ 99% |

---

## 9. 시뮬 검증 — 골든 79건 (PoC)

### 9.1 골든 정의

| BP사 | 골든 line | L6 정답 분포 |
|---|---|---|
| 남웅건설 | 47 (R99~R146, R125 비계 제외) | 철근콘크리트공사 (100%) |
| 세보엠이씨 | 24 (모호 6건 제외: PFC/FFU/RHW/EBS/FCU/EHP) | ACID배기 2, VOC 2, CABINET배기 2, ALKALI배기 2, H/G배기 1, 비상배기덕트 1, 일반공조 2, DCC 1, 냉동기 2, 위생배관 1, NPW 1, H-VAC 1, 기계소화 6 |
| 창원기전 | 8 (Cable TRAY 5 + Raceway 5 모호 제외) | 전등설비 5, 전력간선 1, 전기소화 2 |
| **합** | **79** | — |

### 9.2 안 A v3 결과

```
정확도: 78/79 = 98.7%
  남웅건설   47/47 (100.0%)
  세보엠이씨  23/24 ( 95.8%)   ← R459 'FA DUCT 설치' 오답
  창원기전    8/8  (100.0%)

토큰: in 84,474 / out 8,112
시간: 331.3s
평균 confidence: 0.776
임베딩 후보 8개 안에 정답 L6 포함률: 78/79 (98.7%)
```

R459 오답: 임베딩이 'FA DUCT' 를 'CABINET 배기덕트' 와 더 유사하다고 판단 → 임베딩 후보 8개에 'CABINET배기설비공사' 포함, '일반공조설비공사' 미포함 → LLM 후보 풀에 정답 없음 → CABINET 선택 (conf 0.55).

confidence 0.55 < 0.7 → **H-i-L 1 자동 발동** → 운영 정확도 100% 보장.

---

## 10. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-14 | 초안 — 매핑 키 (WA, L6) + Mapper 6단계 + WA 4단계 + 다운스트림 grain 일치 + H-i-L 1 자가학습. 실 시뮬 v1·v2·v3 79건 검증. | A 트랙 |
