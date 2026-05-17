# CPIA Optimizer + hil_2 + synthetic v2 — 데이터 계약 정합 + 구현 spec

> **본 spec 의 산물**: ① Optimizer 5 모듈 패키지 (`pipeline/agents/optimizer/`) + ② hil_2 LangGraph interrupt 노드 + ③ synthetic v2 보강 (work_content 풍성화 + 시계열 회복 패턴 7 룰) + ④ 가짜 작업일보 + 데모 graph + ⑤ Forecaster 권고 4건 정합. 본 cycle = **13 Task**.
>
> 작성: 2026-05-16 (A 트랙, Phase 1) · 기반: PM 원안 v2 (`CPIA_PoC_실행계획_v2.md` §3 Week 3 Optimizer + H-i-L 2), `2026-05-16-cpia-downstream-agents-design.md` §7 (Optimizer 데이터 계약 — 본 spec 으로 supersede), `2026-05-16-cpia-forecaster-design.md` (Forecaster Phase 1 종결), 9/25 남웅 실 trace + chroma 821 row 시뮬 (2026-05-16).
>
> **본 cycle 진입 confirm**: brainstorming cycle 의 시뮬 5 단계 (결정 누적 18건 + 기존↔본 cycle 연결 매트릭스 + 9/25 남웅 1 그룹 실 trace + Gap 12건 + Task 13개 분해) 완료, 사용자 OK.
>
> **리뷰 반영**: 2026-05-16 coherence-reviewer (6 발견) + feasibility-reviewer (9 발견) 통합 12건 정정 (Blocker 1 / Critical 4 / Major 5 / Minor 2). 사용자 결정 2건 — rule 7 (야간연장 + 돌관 인원 spike) state machine 포함, build_demo_graph 의 risk_level 보장 = synthetic v2 적재 선행 + scenario 두 파라미터.

---

## 0. 한눈에 보기 + 결정 사항 21건

| # | 사안 | 결정 |
|---|---|---|
| 1 | scope | Optimizer + hil_2 + synthetic v2 + 가짜 작업일보 + Forecaster 권고 4건 한 spec (Task 13개) |
| 2 | hil_2 입력 메커니즘 | LangGraph `interrupt()` + `Command(resume=)` + InMemorySaver (PoC). prod PostgresSaver 별 cycle. |
| 3 | synthetic v2 풍성도 | 시계열 회복 룰 **7** + 90일 + work_content 카테고리별 활동 풀 (l7_5_activity from PG) |
| 4 | Optimizer 회복 패턴 검색 | case-by-case (저하 5건 + 각 +1~+7일 trajectory) — PM v2 sample 형식 정확 일치 |
| 5 | work_content 생성 | `f"{l7_5_activity from PG} / {condition_text}"` 조합 |
| 6 | assigned_workers (synthetic v2) | 9/25 `_prorate_mh` 결과 base + ±10% gauss noise (50 고정 X). **돌관 incident 시 ×1.3 spike** |
| 7 | 현 synthetic 810 row | DROP 후 v2 적재 (단순 work_content 노이즈 제거) |
| 8 | hil_2 preview | retrieve 호출 + interrupt payload 에 `preview_cases` 첨부 + `state["pre_optimizer_cases"]` 영속화 (Optimizer 재호출 회피) |
| 9 | LLM model | Azure `gpt-5.1-chat-ai-board-test` (Forecaster 동일, temperature 박지 않음) |
| 10 | fail mode | fail-fast (Forecaster 결정 #13 동일, PoC) |
| 11 | cold start | `degradation_cases < 3` → LLM skip + `diagnosis="cold_start"`. `_group_baseline None` → `pre_cases[key]=[]` 분기 |
| 12 | graph 패턴 | `forecaster → hil_2 → (selection? optimizer : END) → END` (conditional edge) |
| 13 | 회복 정의 | `productivity ≥ baseline_value × 0.95` |
| 14 | 저하 정의 | `conditions ∋ {장비대기, 자재미입고, 돌관}` **and** `productivity < baseline_value × 0.85` |
| 15 | baseline_value | 같은 (company, l6_main, unit) 의 conditions 에 incident 없는 row productivity 평균 (실 검증: 남웅 철콘 v2 = **31.072**, n=54. 구 placeholder 15.981/n=18 대비 +94% — assigned_workers prorated 분포가 만든 구조적 차이, 사용자 결정 = 의도) |
| 16 | productivity 단위 | main_unit (Forecaster 재사용). **Forecaster row 에 2 필드 추가** (v3.1 정정): `main_unit` + `today_conditions`. `today_productivity` 는 Forecaster Phase 1 시점에 이미 박혀있음 (agent.py:163,196 + db.py:218 + PG forecasts 컬럼 확인). |
| 17 | Forecaster 권고 통합 | Important #1 (§6/§10 main_unit drift) + #2 (WORK_HOURS_PER_DAY → `pipeline/constants.py` 승격) + Minor 4건 본 cycle Task 0/1/10 |
| 18 | 가짜 작업일보 | `synthetic_daily_report.py` — 9/26 or 9/27 1~3건 + `build_demo_graph()` (Parser/Mapper skip, Activity 직접 주입). **synthetic v2 적재 선행 + pipeline_runs INSERT + productivity_ratio/assigned_workers 두 파라미터로 자연 trigger** |
| 19 | conditions 정합 | **comma-joined str 통일** (atomizer 패턴, `",".join(list)`). retrieve/prompt/payload 모두 str. fake_daily_report 도 join 후 적재. **work_content 안에 조건 텍스트 박지 않고 conditions 메타로만 박음 (v3 정정)** |
| 20 | recovery_distribution | **코드단 산출** (`Counter([c.recovery.recovery_days for c in cases])`) → LLM 출력 override. LLM 은 diagnosis + recommendations 만 책임 |
| 21 | recommendations tone | "선택지 제시" — "확인 필수" 같은 명령형 회피, "확인 권장" / "검토 권고" 형식. 최종 판단 = PM. |
| 22 | **work_content 형식 (v3)** | `f"{l7_5_activity}"` **단순 활동명** (실 9/25 작업일보 정합 검증 — col7~9 텍스트에 야간/연장/돌관 키워드 거의 없음, 단순 작업명). 조건/야간/돌관 정보는 conditions 메타로만 박음. `WORK_CONTENT_TEMPLATES` 삭제 (Phase 2 실 작업일보 풀 정밀화) |
| 23 | **인원 5분류 ground truth (v3)** | 실 9/25 작업일보 [1.출력인원 현황] 시트 = **조출 / 주간 / 연장 / 야간 / 철야 / Total** 5분류 × 4 grouping (전일Incr/전일Cum/금일Incr/금일Cum). Phase 1 PoC = Total 만 사용 (현 mapper `_prorate_mh()` 그대로). 5분류 metric 자체 = Phase 2 미해결 (parser/atomizer/state.py 변경 큼) |

---

## 1. 데이터 흐름 정합

```
[Forecaster Phase 1 종결 시점 그대로 유지]
   START → mapper → atomizer → forecaster
                                   ↓
                              state["forecast"]: list[dict]  (N row)

──── 본 cycle 추가 흐름 ────

6. hil_2_node (graph.py 신규 노드)
   - risky = [r for r in state["forecast"] if r["risk_level"] ∈ {"주의", "이상"}]
   - risky 0건 → {hil_2_selection: [], pre_optimizer_cases: {}, current_node: "hil_2"}
                 → conditional edge END
   - risky 있음:
     a. coll.get(where={"$and": [{company}, {l6_main}]}) — **그룹당 1회만** (F5 정정)
     b. baseline_value 계산 (_group_baseline). None → pre_cases[key]=[] (F7 정정)
     c. retrieve.fetch_degradation_cases(metadatas, ..., n=5)
        + 각 case 의 fetch_recovery_trajectory(metadatas, ..., window=7)
     d. state["pre_optimizer_cases"][key] 영속화
     e. interrupt({"risky_groups": [{key, ..., preview_cases}, ...]})

──── interrupt → 외부 Command(resume=[selected keys]) 대기 ────

7. optimizer_node (graph.py 신규 노드)
   - hil_2_selection 빈 list → {optimizer_advice: []} → END
   - 선택된 (company, l6_main) 만 진입
   - state["pre_optimizer_cases"][key] 사용 (retrieve 재호출 X)
   - recovery_distribution = 코드단 산출 (Counter)
   - LLM 호출 (Azure gpt-5.1) → diagnosis + recommendations 만 (fail-fast)
   - PG insert_optimizer_advice
   - state["optimizer_advice"]: list[dict]
   → conditional edge END

8. END (state.status = 'completed')
```

### 1.1 graph 분기 결정 근거

- PM 원안 v2 §3 Week 3: `Forecaster → [H-i-L 2] → Optimizer` 순차 + interrupt 패턴 명시
- 한 노드 안에서 retrieve preview + interrupt 처리 (hil_2_node 가 외부 LLM 호출 X)
- conditional edge 는 hil_2_selection 여부만 (선택 없으면 Optimizer skip)
- Forecaster cycle 의 graph 마지막 edge (forecaster → END) 만 정정

### 1.2 9/25 실 trace 결과 (시뮬, 2026-05-16, 현 단순 schema 기준)

`/Users/kyungseoplee/Project Agent/CPIA` 의 PG + Chroma 실 호출 결과:

```
[1. Forecaster output] PG forecasts.row WHERE company='남웅건설' = 0건
                       — integration test fixture cleanup. state["forecast"] in-memory 흐름 OK.

[2. Chroma 남웅 철콘 incident dates]
  8건 (단순 work_content "철근콘크리트공사 작업" 동일 — embedding 무의미)

[3. baseline_value 실값 — Task 3 v2 적재 후 재산출 결과 (n=54, 2026-05-16)]
  conditions 에 incident 없는 row 54건 productivity 평균 = 31.072
  회복 threshold (× 0.95) = 29.518
  저하 threshold (× 0.85) = 26.411
  ※ 구 placeholder 15.981 (n=18, 단순 schema) 대비 +94% shift — synthetic v2 의
    assigned_workers prorated 분포 (50.0 hardcode → 88 prorated) 가 만든 구조적 차이.
    사용자 결정 = 의도된 차이 (룰 조정 X, baseline 자체가 v2 분포 반영).

[4. case 2025-09-22 (장비대기, prod=12.47) recovery trajectory]
  +1 (9/23) 정상 prod=15.42 → ✓ RECOVERED  recovery_days = 1
  +2 (9/24) 정상 prod=16.39 → ✓

[5. case 2025-09-06 (장비대기, prod=10.51) recovery trajectory]
  +1 (9/07) 정상 prod=16.17 → ✓ RECOVERED  recovery_days = 1
  +2 (9/08) 우천 prod=13.11 → ✗ (일시 재저하)
  +3 (9/09) 정상 prod=15.81 → ✓ (재회복)
```

→ Optimizer 의 case-by-case 검색이 의미. **synthetic v2 적재 후 (§5.4) baseline_value 재검증 필수** — 룰 7 활성화 시 baseline 분포 shift.

---

## 2. state.py 정정

### 2.1 CPIAState 추가 필드 3

```python
class CPIAState(TypedDict):
    # ... 기존 ...
    hil_2_selection: list[str]                  # PM 선택 (e.g., ["남웅건설|철근콘크리트공사"])
    pre_optimizer_cases: dict[str, list[dict]]  # key="company|l6_main" → degradation_cases (recovery 첨부)
    optimizer_advice: list[dict]                # Optimizer 출력 row list
```

### 2.2 Forecaster row schema 완전 명시 (Blocker 1 + F3 정정)

```python
# Forecaster agent.py 의 _forecast_one_group() return dict — 본 cycle 에서 2 필드 추가 (v3.1 정정: today_productivity 는 Phase 1 시점에 이미 박힘)
class ForecastRow(TypedDict):
    # ── 기존 필드 (Forecaster Phase 1) ──
    company: str
    l6_main: str
    today_qty_by_unit: dict[str, float]
    today_assigned_workers: float
    plan_total_qty_by_unit: dict[str, float] | None
    plan_mh_sum: float | None
    plan_start: str | None              # ISO date
    plan_finish: str | None
    plan_mh_per_day: float | None
    schedule_state: Literal["early", "on_schedule", "post_due", "unknown"]
    window_start: str | None
    window_days: int
    expected_in_window_mh: float | None
    actual_in_window_mh: float
    mh_gap: float | None
    delay_days: float | None
    rag_n_similar: int
    similar_cases: list[dict]
    assessment: Literal["정상", "주의", "이상", "cold_start"]
    reasoning: str
    recovery_likelihood: float | None
    expected_completion: str | None
    risk_level: Literal["정상", "주의", "이상"]

    # ── 본 cycle 추가 2 필드 (v3.1 정정 — today_productivity 는 Phase 1 시점 이미 박힘) ──
    main_unit: str | None               # ★ 신규 — positive_units (qty=0 제외) 의 max qty unit
    today_productivity: float | None    # (already in Phase 1) today_qty[main_unit] / today_assigned_workers
    today_conditions: str               # ★ 신규 — comma-joined str (예: "맑음,장비대기"). 빈 str 가능
```

영향:
- PG `forecasts` **2 컬럼 추가**: `main_unit TEXT` + `today_conditions TEXT` (Task 0). `today_productivity NUMERIC` 은 이미 있음.
- Forecaster `insert_forecast()` 25 → **27 컬럼** (v3.1 정정)
- **Forecaster spec design.md §6 row 정의 + §10 _forecast_one_group() 코드 블록 동기화** (drift 해소 — Important #1)
- hil_2 의 `_resolve_baseline_unit(r)` = `r["main_unit"]` 단순 lookup
- Optimizer `build_llm_user_input` 의 `forecast_row.get("today_conditions", "")` 가 실제 값 받음

### 2.3 WORK_HOURS_PER_DAY 승격 (Important #2)

```
pipeline/agents/forecaster/constants.py  ← 현 위치
                  ↓ (Task 0)
pipeline/constants.py                     ← 신 위치
```

**작업 순서** (F6 정정):
1. `pipeline/constants.py` 생성 — `WORK_HOURS_PER_DAY = 8`
2. `pipeline/agents/forecaster/constants.py` → `from pipeline.constants import WORK_HOURS_PER_DAY` (1-liner re-export)
3. `pipeline/agents/forecaster/__init__.py` re-export 유지 (backward compat)
4. `forecaster/aggregate.py` + `classify.py` 의 import 정정 (또는 .constants 경유 유지)
5. 회귀 `pytest pipeline/tests/` 0 회귀 확인

---

## 3. PG schema 정정

### 3.1 optimizer_advice 5 컬럼 추가 + recommendations type 변경

**현 schema** (`infra/postgres/init.sql:101-111`, downstream §8.3 적용 후):
```
id BIGSERIAL PK, run_id UUID, l6_main TEXT, diagnosis TEXT,
recovery_pattern JSONB, recommendations TEXT, created_at TIMESTAMPTZ
```

**문제**: `company` 컬럼 없음 (downstream §8.3 rename 만 했음). `recommendations` TEXT — ranked list 박을 수 없음.

**Task 0 마이그레이션**:
```sql
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS company TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS forecast_assessment TEXT;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS degradation_cases JSONB;
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS recovery_distribution JSONB;
ALTER TABLE optimizer_advice ALTER COLUMN recommendations TYPE JSONB
    USING (CASE WHEN recommendations IS NULL THEN NULL ELSE recommendations::JSONB END);
CREATE INDEX IF NOT EXISTS idx_optimizer_advice_company_l6 ON optimizer_advice (company, l6_main);
CREATE INDEX IF NOT EXISTS idx_optimizer_advice_run ON optimizer_advice (run_id);
```

현 row 0건이라 type 변경 안전.

### 3.1.1 JSONB 컬럼 구조 명시 (C-Major 2 정정)

```python
# recovery_pattern JSONB structure
[
    {"date": "2025-09-22", "recovery_days": 1},
    {"date": "2025-09-06", "recovery_days": 1},
    {"date": "2025-08-15", "recovery_days": None},  # 미회복
    ...  # degradation_cases 와 1:1 대응
]

# recovery_distribution JSONB structure (코드단 산출, 결정 #20)
{"d+1": 3, "d+2": 1, "d+3": 0, "not_recovered": 1}

# degradation_cases JSONB structure (감사 추적용 — retrieve.fetch_degradation_cases 결과 그대로)
[
    {
        "date": "2025-09-22",
        "conditions": "맑음,장비대기",                 # ★ comma-joined str (결정 #19)
        "productivity": 12.47,
        "assigned_workers": 88.0,
        "activities": ["기초공사 : 거푸집 공사"],
        "recovery": {
            "recovery_days": 1,
            "trajectory": [
                {"date": "2025-09-23", "conditions": "맑음",
                 "productivity": 15.42, "recovered": true},
                ...
            ]
        }
    },
    ...
]

# recommendations JSONB structure
[
    {"rank": 1, "text": "타워크레인 스케줄 확인 권장"},
    {"rank": 2, "text": "..."},
    ...
]
```

### 3.2 forecasts 2 컬럼 추가 (v3.1 — today_productivity 는 Phase 1 시점 이미 박힘)

```sql
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS main_unit TEXT;
ALTER TABLE forecasts ADD COLUMN IF NOT EXISTS today_conditions TEXT;
-- today_productivity 는 Phase 1 시점에 이미 추가됨 (v3.1 정정 — IF NOT EXISTS 라 본 spec 의 ALTER 도 무해, 단 의도 명확화 위해 제거)
```

### 3.3 3곳 동기화 의무 (Forecaster Task 0 패턴 동일)

```
infra/postgres/migrations/2026-05-16_optimizer_hil2.sql     ← 신규
infra/postgres/init.sql                                      ← cold start 동기화
docs/schema/postgres.md                                      ← 문서 §6 forecasts + §7 optimizer_advice 동기화
```

---

## 4. synthetic v2 데이터 룰 (Task 2~3)

### 4.1 state machine 시계열 회복 룰 **7건** (PM v2 §2.B + 야간연장/돌관 — 반도체 현장 핵심)

| # | 트리거 | 효과 |
|---|---|---|
| 1 | 장비대기 (1일차) | productivity × (1 - random[0.20, 0.35]) |
| 2 | 장비대기 1일차 → 익일 | 80% 정상 복귀 (productivity ≥ baseline) / 20% 2일차 지속 |
| 3 | 장비대기 2일차 → 익일 | 30% 만회 (productivity ≥ baseline × 1.10) / 70% 정상 |
| 4 | 우천 연속 2일 → 3일차 | productivity × 1.10 만회 |
| 5 | 자재미입고 → 익일 | 50% 정상 복귀 / 50% 2일차 지속 |
| 6 | **야간연장 → 익일** | productivity × 0.90 (인원 피로 누적) |
| 7 | **돌관 (인원 spike) — 당일** | 당일 효과: productivity × 0.85 (혼잡) + assigned_workers × 1.3 spike. 익일 효과 없음 (state machine 의 `last_incident="돌관"` 다음 turn 은 정상 random 분기로 흐름) |

**반도체 현장 특화 (사용자 결정)**: 야간 + 돌관 (주말/야간/추가 인원) 관리가 현장 핵심. 단순 주간 작업 가정 X. state machine 의 incident enum 에 `"야간연장"` + `"돌관"` 추가.

### 4.2 state machine 의사코드 (rule 6/7 incident 생성 추가)

```python
def generate_synthetic_v2_group(
    company: str, l6_main: str,
    activity_pool: list[str],         # l7_5_activity from PG
    baseline_workers: float,           # 9/25 _prorate_mh 결과
    baseline_qty_per_day: float,       # plan_total_qty / 90
    unit: str,
    days: int = 90,
    reference_date: date = date(2025, 9, 25),
    seed: int = 42,
) -> list[dict]:
    rng = random.Random(seed)
    state = {"last_incident": None, "rain_streak": 0, "equip_wait_streak": 0}
    rows = []
    for day_offset in range(days, 0, -1):
        target_date = reference_date - timedelta(days=day_offset)

        # ── incident 결정 (룰 2/3/5 + 신규 룰 6/7) ──
        if state["last_incident"] == "장비대기" and state["equip_wait_streak"] == 1:
            # 룰 2: 익일 80% 복귀
            if rng.random() < 0.8:
                incident = "정상"
                state["equip_wait_streak"] = 0
            else:
                incident = "장비대기"  # 2일차 지속
                state["equip_wait_streak"] = 2
        elif state["last_incident"] == "장비대기" and state["equip_wait_streak"] == 2:
            # 룰 3: 2일차 → 익일 정상 (만회 30% / 정상 70%)
            incident = "정상"
            state["equip_wait_streak"] = 0
            compensation = 1.10 if rng.random() < 0.3 else 1.0
        elif state["last_incident"] == "자재미입고":
            # 룰 5
            incident = "정상" if rng.random() < 0.5 else "자재미입고"
        elif state["last_incident"] == "야간연장":
            # 룰 6 익일 피로 — 단 incident 자체는 새 random
            incident = rng.choices(
                ["정상", "장비대기", "자재미입고", "야간연장", "돌관"],
                weights=[6, 1.5, 1.5, 0.5, 0.5],
            )[0]
            fatigue_factor = 0.90
        else:
            incident = rng.choices(
                ["정상", "장비대기", "자재미입고", "야간연장", "돌관"],
                weights=[6, 1.5, 1.5, 0.5, 0.5],
            )[0]
            fatigue_factor = 1.0

        # 장비대기 신규 시작
        if incident == "장비대기" and state["last_incident"] != "장비대기":
            state["equip_wait_streak"] = 1

        # ── weather + rain streak ──
        weather = rng.choices(["맑음", "우천", "흐림"], weights=[6, 2, 2])[0]
        rain_streak_compensation = 1.10 if (state["rain_streak"] >= 2 and weather != "우천") else 1.0

        # ── productivity delta 계산 ──
        delta = 0.0
        if weather == "우천":
            delta -= rng.uniform(0.15, 0.25)
        if incident == "장비대기":
            delta -= rng.uniform(0.20, 0.35)  # 룰 1
        elif incident == "자재미입고":
            delta -= rng.uniform(0.10, 0.20)
        elif incident == "돌관":
            delta -= rng.uniform(0.10, 0.20)   # 룰 7: 혼잡 효과 -10~20%
        delta += rng.uniform(-0.05, 0.05)

        today_qty = round(
            baseline_qty_per_day * (1 + delta) * rain_streak_compensation
            * (compensation if 'compensation' in locals() else 1.0)
            * fatigue_factor,
            1,
        )

        # ── assigned_workers (룰 7 spike 적용) ──
        worker_multiplier = 1.3 if incident == "돌관" else 1.0
        assigned_workers = round(baseline_workers * worker_multiplier * rng.gauss(1.0, 0.1), 1)

        # ── work_content = 활동명만 (v3 정정 — 실 작업일보 정합) ──
        # 결정 #22: 조건/야간/돌관 정보는 conditions 메타로만 박음.
        # 실 9/25 작업일보 col7~9 (전일/금일/명일 작업사항) 텍스트에 야간/연장/돌관/장비 키워드 거의 X.
        # WORK_CONTENT_TEMPLATES 삭제 — Phase 2 정밀화 시 실 작업일보 텍스트 풀에서 추출.
        work_content = rng.choice(activity_pool)

        # ── conditions list → comma-joined str (결정 #19, atomizer 패턴) ──
        conditions_list = [weather] + ([incident] if incident != "정상" else [])
        conditions_str = ",".join(conditions_list)

        rows.append({
            "date": target_date.isoformat(),
            "company": company, "l6_main": l6_main,
            "unit": unit,
            "today_qty": today_qty,
            "assigned_workers": assigned_workers,
            "conditions": conditions_str,           # ★ str (atomizer 호환)
            "work_content": work_content,
            "worker_source": "synthetic_v2",
        })

        # ── state 업데이트 ──
        state["last_incident"] = incident
        state["rain_streak"] = state["rain_streak"] + 1 if weather == "우천" else 0
    return rows
```

### 4.3 work_content 활동 풀 source

```sql
SELECT DISTINCT l7_5_activity
FROM activity_master
WHERE company = $1 AND l6_main = $2 AND l7_5_activity IS NOT NULL
```

실 분포 (`/tmp/cpia_act_diversity.py`, 2026-05-16):
- 남웅 철콘 = 56개 (예: `"기초공사 : 거푸집 공사"`, `"RC Wall & Column 공사 : 철근 조립"`)
- 세보 일반공조 = 22개 / 위생배관 = 6개 / 창원 방송설비 = 1개 (단조 — 단조성도 의미)

### 4.4 work_content 형식 (v3 정정 — 결정 #22)

**삭제**: `WORK_CONTENT_TEMPLATES` 카테고리별 풀 정의. v1/v2 spec 의 추측 텍스트 풀 (5 카테고리 × 5 텍스트 = 25개) 은 본 정정으로 폐기.

**근거**: 실 9/25 작업일보 col7~9 (전일/금일/명일 작업사항) 텍스트 grep 결과 (`/tmp/cpia_worklog_pattern.py`, 2026-05-16) — 남웅/세보/창원 3 BP사 의 작업사항 텍스트에 야간/연장/돌관/장비대기/자재미입고/우천 키워드 hit = **0건** (false positive 3건만). 실 텍스트는 단순 작업명 (예: `"비상 스피커 설치 작업 / 작업위치 ... 작업내용 ..."`, `"기초공사 : 거푸집 공사"`).

**Phase 1 PoC (본 cycle)**: `work_content = rng.choice(activity_pool)` — 단순 활동명 (l7_5_activity from PG). 조건/야간/돌관 정보는 `conditions` 메타 enum 으로만 박음 (룰 1~7 의 state machine 결과).

**Phase 2 정밀화 (PoC 이후)**:
- `WORK_CONTENT_TEMPLATES` 실 작업일보 텍스트 풀에서 추출 (9/25 + 누적 데이터 grep) → 활동명 + 조건 텍스트 자연 결합
- 인원 5분류 (조출/주간/연장/야간/철야) metric 자체 메타 추가 (parser/atomizer/state.py 정정)
- Optimizer LLM 가 5분류 비율 보고 야간/돌관 패턴 정밀 진단

### 4.5 assigned_workers prorate base (downstream §3.4 그대로)

```python
BASELINE_WORKERS = {
    ("남웅건설", "철근콘크리트공사"): 88.0,
    ("세보엠이씨", "기계소화설비"): 421.7,
    ("세보엠이씨", "일반공조설비공사"): 401.4,
    ("세보엠이씨", "냉동기설비공사"): 152.1,
    ("창원기전", "전력간선공사"): 216.9,
    ("창원기전", "전등설비공사"): 91.3,
    ("창원기전", "전기소화설비"): 63.8,
    # ... downstream §3.4 표 그대로 (27 그룹)
}
```

일별 ±10% gauss noise + 돌관 incident 시 ×1.3 spike (룰 7).

### 4.6 적재 결과 예상

- 27 그룹 × 일별 1 활동 × 90일 ≈ **2,430 row** (현 810 의 3배)
- 그룹당 incident 빈도: 장비대기 ~9건, 자재미입고 ~9건, 우천 ~12건, 야간연장 ~3건, 돌관 ~3건
- → Optimizer step 1 검색 N=5 안정 보장 (장비대기+자재미입고+돌관 합 ~21건)
- worker_source = `"synthetic_v2"` 메타 enum 추가

### 4.7 현 synthetic 810 row 처리

```python
# Task 3 CLI 의 첫 단계
coll.delete(where={"worker_source": "synthetic"})  # 단순 텍스트 노이즈 제거
# 그 후 v2 적재
coll.upsert(ids=..., embeddings=..., documents=..., metadatas=...)
```

→ atomizer 적재 row (`worker_source="mh_prorated"` 11건) 는 보존.

### 4.8 baseline_value 재검증 (C-Critical 1 정정)

**Task 3 step 6 (적재 직후 의무)**:
```python
# 적재 직후 baseline 재계산 (synthetic v2 영향 측정)
for (company, l6_main), unit in MASTER_GROUPS:
    baseline_v2 = _group_baseline(metadatas, company, l6_main, unit)
    print(f"{company}|{l6_main}|{unit} baseline_v2 = {baseline_v2:.3f}")

# 남웅 철콘 m3 (현 baseline=15.981) 의 v2 적재 후 값 → spec §1.2 [3] 업데이트
# 큰 shift (>20%) 시 룰 가중치 또는 baseline_qty_per_day 재조정
```

---

## 5. retrieve.py 2-step 검색 (Task 4)

### 5.1 fetch_degradation_cases (F1 + F5 정정 — metadatas/documents 받음, conditions str 통일)

```python
def fetch_degradation_cases(
    metadatas: list[dict],          # ★ F5: 외부에서 coll.get 1회 호출 후 전달
    documents: list[str],            # ★ F5
    company: str,
    l6_main: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    n: int = 5,
) -> list[dict]:
    """Step 1 — 같은 (company, l6_main) 의 저하 case top-N recency.
    
    저하 정의: conditions ∋ {장비대기, 자재미입고, 돌관} AND group productivity < baseline*0.85.
    conditions 는 comma-joined str (결정 #19) — `substring in` 검사.
    """
    by_date: dict[str, list] = defaultdict(list)
    for m, d in zip(metadatas, documents):
        if m["company"] != company or m["l6_main"] != l6_main:
            continue
        if m["date"] >= today.isoformat():
            continue
        # 단순 synthetic 노이즈 회피 — synthetic_v2 + atomizer 의 mh_prorated 만
        if m.get("worker_source") not in ("synthetic_v2", "mh_prorated"):
            continue
        by_date[m["date"]].append((m, d))

    cases = []
    for d, rows in by_date.items():
        raw = rows[0][0].get("conditions") or ""  # ★ str
        if not any(c in raw for c in ("장비대기", "자재미입고", "돌관")):
            continue
        prod = _group_day_productivity([m for m, _ in rows], baseline_unit)
        if prod >= baseline_value * 0.85:
            continue
        cases.append({
            "date": d,
            "conditions": raw,                     # ★ str
            "productivity": prod,
            "assigned_workers": rows[0][0]["assigned_workers"],
            "activities": [doc for _, doc in rows],
        })
    cases.sort(key=lambda c: c["date"], reverse=True)
    return cases[:n]
```

### 5.2 fetch_recovery_trajectory

```python
def fetch_recovery_trajectory(
    metadatas: list[dict],
    company: str,
    l6_main: str,
    case_date: str,
    today: date,
    baseline_unit: str,
    baseline_value: float,
    window: int = 7,
) -> dict:
    """Step 2 — case_date+1 ~ +window 의 group productivity trajectory.
    
    회복 정의: productivity >= baseline_value * 0.95.
    recovery_days = 첫 ✓ 까지의 일수 (None 이면 미회복).
    """
    by_date: dict[str, list] = defaultdict(list)
    for m in metadatas:
        if m["company"] == company and m["l6_main"] == l6_main:
            by_date[m["date"]].append(m)

    case_d = date.fromisoformat(case_date)
    trajectory = []
    for d_offset in range(1, window + 1):
        target_d = case_d + timedelta(days=d_offset)
        if target_d >= today:
            break
        target_iso = target_d.isoformat()
        if target_iso not in by_date:
            continue
        rows = by_date[target_iso]
        prod = _group_day_productivity(rows, baseline_unit)
        trajectory.append({
            "date": target_iso,
            "conditions": rows[0]["conditions"],   # ★ str
            "productivity": prod,
            "recovered": prod >= baseline_value * 0.95,
        })
    recovery_days = next((i + 1 for i, t in enumerate(trajectory) if t["recovered"]), None)
    return {"trajectory": trajectory, "recovery_days": recovery_days}
```

### 5.3 헬퍼 함수 (F7 정정 — None 분기 명시)

```python
def _group_baseline(
    metadatas: list[dict],
    company: str,
    l6_main: str,
    baseline_unit: str,
) -> Optional[float]:
    """같은 (company, l6_main, unit) 의 conditions 에 incident 없는 row productivity 평균.
    
    0 row → None (cold_start 신호 — 호출자가 pre_cases[key]=[] 분기).
    incident 키워드: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장.
    """
    prods = []
    for m in metadatas:
        if m["company"] != company or m["l6_main"] != l6_main or m["unit"] != baseline_unit:
            continue
        raw = m.get("conditions") or ""        # ★ str
        if any(c in raw for c in ("장비대기", "자재미입고", "우천", "돌관", "야간연장")):
            continue
        if m["assigned_workers"] > 0 and m["today_qty"] > 0:
            prods.append(m["today_qty"] / m["assigned_workers"])
    return sum(prods) / len(prods) if prods else None


def _group_day_productivity(metas_of_day: list[dict], baseline_unit: str) -> float:
    """그 날 (company, l6_main) 의 baseline_unit Σ today_qty / assigned_workers.
    
    같은 그룹 = assigned_workers 동일 reference (downstream §3 옵션 X). 0 → 0.0.
    """
    qty = sum(m["today_qty"] for m in metas_of_day if m["unit"] == baseline_unit)
    workers = metas_of_day[0]["assigned_workers"] if metas_of_day else 0
    return qty / workers if workers > 0 else 0.0
```

### 5.4 실 검증 결과 + 재검증 의무

**현 chroma (단순 synthetic 기준, 2026-05-16)**:
```
baseline_value (정상 row 18건 평균) = 15.981
회복 threshold (× 0.95)             = 15.182
저하 threshold (× 0.85)             = 13.584
```

**synthetic v2 적재 후 (Task 3 step 6)** — 본 값 재검증 후 spec §1.2 [3] 업데이트:
- 룰 1 (장비대기 -20~35%) + 룰 7 (돌관 -10~20%) → baseline 분포 shift 가능
- 룰 6 (야간연장 익일 -10%) → 정상 row 의 일부도 영향 → baseline 자체 ↓ 가능
- 큰 shift (>20%) 시 룰 가중치 또는 baseline_qty_per_day 재조정

---

## 6. prompt.py (Task 5)

### 6.1 SYSTEM_PROMPT (C-Major 1 정정 — tone softening)

```
당신은 건설 현장 생산성 진단 + 회복 패턴 분석 전문가입니다.

PM 이 선택한 공종에 대해, 과거 유사 저하 케이스 5건 + 각 case 의 회복 trajectory 를 받습니다.

임무:
1. 오늘 저하 원인 진단 (1~2 문장, 작업 내용 텍스트에서 근거 추론)
2. PM 에게 제시할 권고사항 (ranked list 3~4건, 선택지 제시 형식)

권고사항 tone:
  - "확인 권장" / "검토 권고" / "고려 필요" — 선택지 제시
  - "확인 필수" / "반드시" / "해야 합니다" 같은 명령형 회피
  - 1순위 = 즉시 검토 권장 (예: "타워크레인 스케줄 확인 권장")
  - 2순위 = 과거 회복 패턴 기반 예상 (예: "D+1 60% 자연 복귀 가능성 — 즉시 대응 불필요할 수 있음")
  - 3순위 = 잔여 물량 기준 만회 예상 (예: "D+3 이내 정상화 시 공기 영향 미미")
  - 4순위 = D+N 초과 시 대안 검토 (예: "D+3 초과 시 야간 연장 또는 주말 투입 검토 권고")

원칙:
- 최종 판단 및 실행은 PM 결정 사항. 권고는 근거 기반 선택지 제시.
- 수치 계산 (인원 재배치 명령 등) 금지. 맥락 기반 조언만.
- 한자 사용 금지 (한글 + 영어).
- `recovery_distribution` 은 코드단에서 산출되어 제공됨 — 참고만, 본인이 직접 세지 말 것.
- **v3 정정**: `activities` (degradation_cases.activities) 는 **단순 활동명** (예: "기초공사 : 거푸집 공사"). 조건/야간/돌관 정보는 `today.today_conditions` + 각 case 의 `conditions` 메타 (예: "맑음,장비대기") 에 박혀 있음. 둘 다 보고 진단.

출력 형식 (반드시 JSON):
{
  "diagnosis": "...",
  "recommendations": [
    {"rank": 1, "text": "..."},
    {"rank": 2, "text": "..."},
    ...
  ]
}

(recovery_distribution 은 코드단 추가, 본 응답에 포함 불필요.)
```

### 6.2 FEW_SHOT_MESSAGES 3건 (conditions str 통일)

```python
FEW_SHOT_MESSAGES = [
    # 1: 장비대기 D+1 우세 회복
    {"role": "user", "content": json.dumps({
        "today": {"company": "남웅건설", "l6_main": "철근콘크리트공사",
                  "main_unit": "m3", "assessment": "이상",
                  "today_productivity": 0.45, "today_conditions": "맑음,장비대기"},
        "degradation_cases": [
            {"date": "2025-09-22", "conditions": "맑음,장비대기", "productivity": 12.47,
             "activities": ["기초공사 : 거푸집 공사"],
             "recovery_days": 1,
             "trajectory": [{"date": "2025-09-23", "conditions": "맑음",
                             "productivity": 15.42, "recovered": True}]},
            {"date": "2025-09-06", "conditions": "맑음,장비대기", "productivity": 10.51,
             "activities": ["RC Wall & Column 공사 : 철근 조립"],
             "recovery_days": 1,
             "trajectory": [{"date": "2025-09-07", "conditions": "맑음",
                             "productivity": 16.17, "recovered": True},
                            {"date": "2025-09-08", "conditions": "우천",
                             "productivity": 13.11, "recovered": False}]},
            # ... 5건
        ],
    }, ensure_ascii=False)},
    {"role": "assistant", "content": json.dumps({
        "diagnosis": "장비 대기로 인한 저하 (추정). 타워크레인 스케줄 충돌 가능성. 과거 5건 중 4건이 D+1 자연 복귀.",
        "recommendations": [
            {"rank": 1, "text": "내일 오전 타워크레인 스케줄 확인 권장"},
            {"rank": 2, "text": "과거 패턴상 장비 확보 시 D+1 80% 자연 복귀 가능성 — 즉시 추가 조치 불필요할 수 있음"},
            {"rank": 3, "text": "잔여 물량 기준 D+3 이내 정상화 시 공기 영향 미미"},
            {"rank": 4, "text": "D+3 초과 시 야간 연장 또는 주말 돌관 투입 검토 권고"},
        ],
    }, ensure_ascii=False)},

    # 2: 자재미입고 D+2 우세
    # ... (위와 유사한 패턴)

    # 3: 미회복 우세 (장기 지연 — 돌관 검토 시나리오)
    # ...
]
```

### 6.3 build_llm_user_input

```python
def build_llm_user_input(forecast_row: dict, degradation_cases: list[dict]) -> dict:
    """forecast_row 는 §2.2 의 ForecastRow schema 가정 — main_unit / today_productivity / today_conditions 박힘."""
    return {
        "today": {
            "company": forecast_row["company"],
            "l6_main": forecast_row["l6_main"],
            "main_unit": forecast_row.get("main_unit"),
            "assessment": forecast_row["assessment"],
            "today_productivity": forecast_row.get("today_productivity"),
            "today_conditions": forecast_row.get("today_conditions", ""),
        },
        "degradation_cases": [
            {
                "date": c["date"],
                "conditions": c["conditions"],                     # str
                "productivity": c["productivity"],
                "activities": c["activities"],
                "recovery_days": c["recovery"]["recovery_days"],
                "trajectory": c["recovery"]["trajectory"],
            }
            for c in degradation_cases
        ],
    }
```

---

## 7. agent.py — optimize() + cold_start (Task 6)

```python
from __future__ import annotations
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional

from openai import AzureOpenAI

from pipeline.db import PGClient
from pipeline.agents.optimizer.prompt import SYSTEM_PROMPT, FEW_SHOT_MESSAGES, build_llm_user_input


@dataclass
class OptimizerConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str                          # "gpt-5.1-chat-ai-board-test"
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    azure_timeout: float = 60.0
    azure_max_retries: int = 3


async def optimize(
    forecast: list[dict],
    hil_2_selection: list[str],
    pre_optimizer_cases: dict[str, list[dict]],
    run_id: uuid.UUID,
    today: date,
    cfg: OptimizerConfig,
) -> list[dict]:
    """선택된 그룹 별 advice row 생성 + PG insert. fail-fast (LLM crash = 전체 fail)."""
    advice_rows: list[dict] = []
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key, api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout, max_retries=cfg.azure_max_retries,
    )
    for r in forecast:
        key = f"{r['company']}|{r['l6_main']}"
        if key not in hil_2_selection:
            continue
        cases = pre_optimizer_cases.get(key, [])
        if len(cases) < 3:
            advice_rows.append(_compose_cold_start_row(r, cases, run_id))
            continue
        llm_input = build_llm_user_input(r, cases)
        llm_output = await _call_azure_llm(llm_input, cfg, azure)  # fail-fast
        advice_rows.append(_compose_row(r, cases, llm_output, run_id))

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        for row in advice_rows:
            await pg.insert_optimizer_advice(row)
    finally:
        await pg.close()
    return advice_rows


async def _call_azure_llm(llm_input: dict, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict:
    import json as _json
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *FEW_SHOT_MESSAGES,
        {"role": "user", "content": _json.dumps(llm_input, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=cfg.llm_model, messages=messages,
        response_format={"type": "json_object"},
    )
    return _json.loads(resp.choices[0].message.content)


def _compute_recovery_distribution(cases: list[dict]) -> dict[str, int]:
    """결정 #20 — 코드단 deterministic 산출. LLM 출력 override.
    
    Counter([c.recovery.recovery_days for c in cases]) → {"d+1": N, "d+2": N, ..., "not_recovered": N}
    """
    counter = Counter()
    for c in cases:
        rd = c["recovery"]["recovery_days"]
        key = f"d+{rd}" if rd is not None else "not_recovered"
        counter[key] += 1
    return dict(counter)


def _compose_cold_start_row(r: dict, cases: list[dict], run_id: uuid.UUID) -> dict:
    return {
        "run_id": run_id,
        "company": r["company"],
        "l6_main": r["l6_main"],
        "forecast_assessment": r["assessment"],
        "diagnosis": "cold_start",
        "degradation_cases": cases,
        "recovery_pattern": [],
        "recovery_distribution": _compute_recovery_distribution(cases),
        "recommendations": [],
    }


def _compose_row(r: dict, cases: list[dict], llm_output: dict, run_id: uuid.UUID) -> dict:
    recovery_pattern = [
        {"date": c["date"], "recovery_days": c["recovery"]["recovery_days"]}
        for c in cases
    ]
    return {
        "run_id": run_id,
        "company": r["company"],
        "l6_main": r["l6_main"],
        "forecast_assessment": r["assessment"],
        "diagnosis": llm_output["diagnosis"],
        "degradation_cases": cases,
        "recovery_pattern": recovery_pattern,
        "recovery_distribution": _compute_recovery_distribution(cases),  # ★ LLM 출력 override
        "recommendations": llm_output["recommendations"],
    }
```

---

## 8. hil_2 LangGraph interrupt + checkpointer (Task 8)

### 8.1 checkpointer.py 신규

```python
"""LangGraph checkpoint — Phase 1 PoC: InMemorySaver.

prod (Reporter cycle 또는 통합 cycle): PostgresSaver 전환.
"""
from __future__ import annotations
from langgraph.checkpoint.memory import InMemorySaver


def build_checkpointer():
    return InMemorySaver()
```

### 8.2 graph.py hil_2_node + optimizer_node + conditional edge (F5 정정 — coll.get 1회)

```python
from langgraph.types import interrupt, Command
from pipeline.checkpointer import build_checkpointer
from pipeline.agents.optimizer.retrieve import (
    fetch_degradation_cases, fetch_recovery_trajectory, _group_baseline,
)
from pipeline.agents.optimizer.agent import OptimizerConfig, optimize


@dataclass
class GraphConfig:
    mapper: MapperConfig
    atomizer: AtomizerConfig
    forecaster: ForecasterConfig
    optimizer: OptimizerConfig  # ← 본 cycle 추가


async def hil_2_node(state: CPIAState, cfg: GraphConfig) -> dict:
    risky = [r for r in state["forecast"] if r["risk_level"] in {"주의", "이상"}]
    if not risky:
        return {"hil_2_selection": [], "pre_optimizer_cases": {}, "current_node": "hil_2"}

    chroma = ChromaClient(
        host=cfg.optimizer.chroma_host, port=cfg.optimizer.chroma_port, ssl=cfg.optimizer.chroma_ssl,
    )
    coll = chroma.get_or_create_daily_activities()
    today = _date.fromisoformat(state["date"])

    pre_cases: dict[str, list[dict]] = {}
    payload_groups = []
    for r in risky:
        key = f"{r['company']}|{r['l6_main']}"
        baseline_unit = r.get("main_unit")
        if baseline_unit is None:
            pre_cases[key] = []
            payload_groups.append({
                "key": key, "assessment": r["assessment"], "risk_level": r["risk_level"],
                "reasoning": r["reasoning"], "preview_cases": [], "note": "no_main_unit",
            })
            continue

        # ★ F5: coll.get 1회만 호출 후 metadatas/documents 두 함수에 전달
        result = coll.get(
            where={"$and": [{"company": r["company"]}, {"l6_main": r["l6_main"]}]},
            include=["metadatas", "documents"],
        )
        metas, docs = result["metadatas"], result["documents"]

        baseline_value = _group_baseline(metas, r["company"], r["l6_main"], baseline_unit)
        if baseline_value is None:
            # ★ F7: None 분기 명시 — pre_cases[key]=[] 후 다음 그룹
            pre_cases[key] = []
            payload_groups.append({
                "key": key, "assessment": r["assessment"], "risk_level": r["risk_level"],
                "reasoning": r["reasoning"], "preview_cases": [], "note": "cold_start_no_baseline",
            })
            continue

        cases = fetch_degradation_cases(
            metas, docs, r["company"], r["l6_main"], today, baseline_unit, baseline_value, n=5,
        )
        for c in cases:
            c["recovery"] = fetch_recovery_trajectory(
                metas, r["company"], r["l6_main"], c["date"], today,
                baseline_unit, baseline_value, window=7,
            )
        pre_cases[key] = cases
        payload_groups.append({
            "key": key, "assessment": r["assessment"], "risk_level": r["risk_level"],
            "reasoning": r["reasoning"], "today_productivity": r.get("today_productivity"),
            "today_conditions": r.get("today_conditions", ""),
            "preview_cases": cases,
        })

    selected = interrupt({"risky_groups": payload_groups})
    return {
        "hil_2_selection": selected or [],
        "pre_optimizer_cases": pre_cases,
        "current_node": "hil_2",
    }


async def optimizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    if not state.get("hil_2_selection"):
        return {"optimizer_advice": [], "current_node": "optimizer"}
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    today = _date.fromisoformat(state["date"])
    advice = await optimize(
        state["forecast"], state["hil_2_selection"], state["pre_optimizer_cases"],
        run_id, today, cfg.optimizer,
    )
    return {"optimizer_advice": advice, "current_node": "optimizer"}


def build_graph(cfg: GraphConfig):
    graph = StateGraph(CPIAState)
    graph.add_node("mapper", lambda s: mapper_node(s, cfg))
    graph.add_node("atomizer", lambda s: atomizer_node(s, cfg))
    graph.add_node("forecaster", lambda s: forecaster_node(s, cfg))
    graph.add_node("hil_2", lambda s: hil_2_node(s, cfg))
    graph.add_node("optimizer", lambda s: optimizer_node(s, cfg))
    graph.add_edge(START, "mapper")
    graph.add_edge("mapper", "atomizer")
    graph.add_edge("atomizer", "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else END,
        {"optimizer": "optimizer", END: END},
    )
    graph.add_edge("optimizer", END)
    return graph.compile(checkpointer=build_checkpointer())
```

### 8.3 호출 패턴 (pytest 검증)

```python
config = {"configurable": {"thread_id": str(run_id)}}
result = await compiled.ainvoke(initial_state, config=config)
# → interrupt 발생 → result["__interrupt__"] = [{"value": {"risky_groups": [...with preview_cases...]}}]
result = await compiled.ainvoke(Command(resume=["남웅건설|철근콘크리트공사"]), config=config)
# → hil_2_node 가 resume 받음 → conditional edge → optimizer → END
# result["optimizer_advice"] = [...advice row 1건...]
```

---

## 9. PG insert_optimizer_advice (Task 6)

```python
async def insert_optimizer_advice(self, row: dict) -> None:
    """9 컬럼 INSERT (id/created_at auto). JSONB falsy 회피 (is not None).
    
    JSONB structure: §3.1.1 참조.
    """
    import json as _json
    assert self._pool is not None
    async with self._pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO optimizer_advice (
                run_id, company, l6_main, forecast_assessment,
                diagnosis, degradation_cases, recovery_pattern,
                recovery_distribution, recommendations
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6::jsonb, $7::jsonb,
                $8::jsonb, $9::jsonb
            )
            """,
            row["run_id"], row["company"], row["l6_main"], row.get("forecast_assessment"),
            row.get("diagnosis"),
            _json.dumps(row["degradation_cases"], ensure_ascii=False)
                if row.get("degradation_cases") is not None else None,
            _json.dumps(row["recovery_pattern"])
                if row.get("recovery_pattern") is not None else None,
            _json.dumps(row["recovery_distribution"])
                if row.get("recovery_distribution") is not None else None,
            _json.dumps(row["recommendations"], ensure_ascii=False)
                if row.get("recommendations") is not None else None,
        )
```

---

## 10. 가짜 작업일보 + 데모 graph (Task 11)

### 10.1 동기

9/25 남웅 작업일보 sheet4 의 `today_qty` 가 거의 0 (89.5% None → 0.0 표시). Forecaster 가 `today_qty=0` → main_unit=None → cold_start 분기 → `risk_level="정상"`. 즉 9/25 실 데이터로는 hil_2 risky=[], Optimizer 진입 X → 데모 시연 불가.

해소: 가짜 작업일보 1~3건 생성 (9/26 or 9/27) — synthetic v2 의 마지막 1일 row 와 byte-level 유사 schema, `today_qty>0` + 장비대기/돌관 conditions trigger + assigned_workers 조정.

### 10.2 synthetic_daily_report.py (F1 정정 — conditions list[str] / F2 정정 — pipeline_runs INSERT + risk 보장)

```python
def generate_fake_daily_report(
    report_date: str,
    scenarios: list[dict],
    activity_pools: dict[tuple[str, str], list[str]],   # PG l7_5_activity 풀
    baseline_workers: dict[tuple[str, str], float],     # downstream §3.4
    baseline_qty: dict[tuple[str, str, str], float],    # plan_total_qty / 90
) -> list[Activity]:
    """Activity list 직접 생성 — Parser/Mapper skip. atomizer schema 호환.
    
    scenarios = [
        {"company": "남웅건설", "l6_main": "철근콘크리트공사",
         "n_activities": 5, "incident": "장비대기",
         "productivity_ratio": 0.45,                 # baseline 의 45% → 저하 threshold 0.85 미달
         "workers_ratio": 1.0,                       # assigned_workers 배수 (돌관 시 1.3)
         "unit": "m3"},
        {"company": "세보엠이씨", "l6_main": "기계소화설비",
         "n_activities": 3, "incident": "정상", "productivity_ratio": 1.0, "workers_ratio": 1.0, "unit": "m"},
        {"company": "창원기전", "l6_main": "전등설비공사",
         "n_activities": 2, "incident": "돌관",
         "productivity_ratio": 0.70, "workers_ratio": 1.3, "unit": "ea"},
    ]
    """
    activities: list[Activity] = []
    rng = random.Random(42)
    for sc in scenarios:
        key = (sc["company"], sc["l6_main"])
        pool = activity_pools[key]
        base_workers = baseline_workers[key]
        for _ in range(sc["n_activities"]):
            activity_name = rng.choice(pool)
            cond = sc["incident"]
            baseline_q = baseline_qty[(sc["company"], sc["l6_main"], sc["unit"])]
            today_qty = round(baseline_q * sc["productivity_ratio"], 1)

            # ★ F1 정정: conditions list[str] (state.Activity.conditions 계약 —
            #   forecaster.py:92 `for c in a["conditions"]` iterate + atomizer.py:58 ",".join 입력)
            conditions_list = ["맑음"] + ([cond] if cond != "정상" else [])

            # ★ F2: workers_ratio scenario 파라미터 (돌관 spike)
            assigned_workers = round(base_workers * sc["workers_ratio"], 1)

            activities.append({
                "wbs_activity_id": None, "l7_sub": None, "l7_5_activity": None,
                "sub_work_area": None,
                "l5_disc": "건축" if "철근" in sc["l6_main"] else "설비",
                "l6_main": sc["l6_main"],
                "wa": "CUB", "mapping_conf": 0.85,
                "mapping_source": "fake_daily_report",
                "requires_review": False,
                "trade": sc["l6_main"],
                "company": sc["company"],
                "unit": sc["unit"],
                "today_qty": today_qty,
                "work_content": activity_name,          # ★ v3 정정 — 단순 활동명 (실 작업일보 정합)
                "conditions": conditions_list,          # ★ list[str] (state.Activity 계약)
                "assigned_workers": assigned_workers,
                "worker_source": "mh_prorated",
                "plan_total_qty": None, "plan_mh": None,
            })
    return activities
```

### 10.3 build_demo_graph

```python
def build_demo_graph(cfg: GraphConfig):
    """START → forecaster → hil_2 → (optimizer | END) — mapper/atomizer skip.
    
    state["mapped"] = 가짜 Activity list 사전 주입 (LLM 비용 회피).
    """
    graph = StateGraph(CPIAState)
    graph.add_node("forecaster", lambda s: forecaster_node(s, cfg))
    graph.add_node("hil_2", lambda s: hil_2_node(s, cfg))
    graph.add_node("optimizer", lambda s: optimizer_node(s, cfg))
    graph.add_edge(START, "forecaster")
    graph.add_edge("forecaster", "hil_2")
    graph.add_conditional_edges(
        "hil_2",
        lambda s: "optimizer" if s.get("hil_2_selection") else END,
        {"optimizer": "optimizer", END: END},
    )
    graph.add_edge("optimizer", END)
    return graph.compile(checkpointer=build_checkpointer())
```

### 10.4 CLI (F2 정정 — pipeline_runs INSERT + synthetic v2 적재 의무 확인)

```bash
python -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
    --scenario "세보엠이씨|기계소화설비|3|정상|1.0|1.0|m" \
    --scenario "창원기전|전등설비공사|2|돌관|0.70|1.3|ea"

# CLI 내부 흐름:
# 1. ★ synthetic v2 적재 확인 — `coll.get(where={"worker_source": "synthetic_v2"}, limit=1)` 결과 0 이면 abort + 안내
# 2. ★ PGClient.insert_pipeline_run(run_id, site_id, date='2025-09-27', status='running')
# 3. generate_fake_daily_report → mapped Activity list
# 4. initial_state = {"run_id": run_id, "date": "2025-09-27", "mapped": mapped, "current_node": "demo_start"}
# 5. compiled = build_demo_graph(cfg)
# 6. result = await compiled.ainvoke(initial_state, config={"configurable": {"thread_id": str(run_id)}})
# 7. interrupt 발생 → result["__interrupt__"] 의 risky_groups + preview_cases 출력
# 8. PM 결정 시뮬: Command(resume=["남웅건설|철근콘크리트공사"]) → optimizer → END
# 9. result["optimizer_advice"] 출력
```

scenario 파라미터 (productivity_ratio=0.45, workers_ratio=1.0) → today_productivity ≈ baseline × 0.45 → Forecaster assessment="이상" + risk_level="이상" 자연 trigger (가정: synthetic v2 의 baseline 적재 완료 후).

---

## 11. Forecaster 권고 4건 정합 (Important #1/#2 + Minor)

### 11.1 Important #1 (Task 1) — Forecaster spec drift 동기화

- `docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md` **§3 row 구조** (actual location, NOT §6 = classify) 에 본 spec §2.2 의 **2 필드 추가** (`main_unit` + `today_conditions`). today_productivity 는 Phase 1 시점 이미 박힘.
- **§10 agent.py 명세** `_forecast_one_group()` 코드 블록 정정:
  - main_unit positive_units 필터 (qty=0 제외)
  - reasoning 4 분기 (main_unit None / plan None / plan_main_qty None / 기본)
  - return dict 에 main_unit + today_conditions 박음 (today_productivity 는 이미 있음)
- §18 변경 이력에 한 줄 ("2 필드 추가 + drift 동기화, optimizer cycle 동반")

### 11.2 Important #2 (Task 0) — WORK_HOURS_PER_DAY 승격

```
pipeline/agents/forecaster/constants.py  → pipeline/constants.py
```

- `pipeline/constants.py` 신규 — `WORK_HOURS_PER_DAY = 8`
- `pipeline/agents/forecaster/constants.py` — `from pipeline.constants import WORK_HOURS_PER_DAY` (1-liner re-export)
- `pipeline/agents/forecaster/__init__.py` — re-export 유지
- 회귀 `pytest pipeline/tests/forecaster/` 0 회귀 후 다음 Task

### 11.3 Minor (Task 10)

| 항목 | 정정 |
|---|---|
| `aggregate.py` docstring `× 8` 잔존 | `× WORK_HOURS_PER_DAY` 로 정정 |
| `test_aggregate.py:216` literal `8` | `from pipeline.constants import WORK_HOURS_PER_DAY` import |
| `classify.py` 임계값 inline (-0.15, -0.25, 0.85, 0.65, 5, 0.7) | `RAG_NORMAL_BOUND = 0.15` 등 모듈 상수화 |
| classify boundary 1px epsilon test 누락 | `eps=1e-9` 보호 회귀 신호 1 test 추가 |

---

## 12. 테스트 plan (TDD)

### 12.1 unit (mock chroma / azure, ~26 test)

```
retrieve.py (10):
  test_fetch_degradation_cases_filters_incident_str_substring  # F1 conditions str
  test_fetch_degradation_cases_excludes_future_date
  test_fetch_degradation_cases_excludes_recovered             # baseline*0.85 이상 제외
  test_fetch_degradation_cases_excludes_legacy_synthetic      # worker_source != "synthetic_v2"
  test_fetch_degradation_cases_top_n_recency
  test_fetch_degradation_cases_includes_dolgwan                # ★ 돌관 incident 포함
  test_fetch_recovery_trajectory_window_clipped_by_today
  test_fetch_recovery_trajectory_recovery_days_first_recovered
  test_fetch_recovery_trajectory_no_recovery                  # recovery_days = None
  test_group_baseline_normal_only_excludes_all_incidents_inc_dolgwan
  test_group_baseline_none_when_no_normal_rows
  test_group_day_productivity_baseline_unit_zero_workers

synthetic_v2.py (10):
  test_state_machine_equip_wait_recovery_d1                    # 룰 2 (80% 익일)
  test_state_machine_equip_wait_d2_compensation                # 룰 3 (2일차 30% 만회)
  test_state_machine_rain_streak_compensation                  # 룰 4 (우천 2일 +10%)
  test_state_machine_material_shortage_recovery                # 룰 5 (50% 익일)
  test_state_machine_night_overtime_fatigue                    # 룰 6 (익일 ×0.90)
  test_state_machine_dolgwan_workers_spike_and_drop            # ★ 룰 7 (assigned_workers ×1.3 + prod ×0.85)
  test_seed_reproducibility                                     # 같은 seed → 같은 sequence
  test_work_content_template_pool_distribution_includes_dolgwan
  test_assigned_workers_prorate_with_noise                     # 9/25 base ± 10%
  test_conditions_comma_joined_str                              # F1 통일

prompt.py (3):
  test_system_prompt_korean_no_command_tone                    # ★ C-Major 1 — "필수" 없음 검수
  test_few_shot_messages_count_3
  test_build_llm_user_input_includes_today_conditions          # F3

agent.py (4):
  test_optimize_skip_when_not_in_selection
  test_optimize_cold_start_when_cases_less_than_3
  test_optimize_uses_pre_cases_no_retrieve_recall              # ★ retrieve 재호출 회피 검증
  test_compute_recovery_distribution_deterministic             # ★ 결정 #20 코드단 산출
```

### 12.2 integration (`@pytest.mark.slow`, 실 PG + Chroma + Azure)

```
test_synthetic_v2_chroma_upsert_distribution    # 90일 × 27 그룹 적재 분포 검증
test_synthetic_v2_baseline_recheck_after_load   # ★ §4.8 baseline 재검증
test_optimize_namwong_e2e                       # 남웅 철콘 1 그룹 실 LLM → advice row
test_insert_optimizer_advice_byte_level         # 9 컬럼 JSONB 정합
```

### 12.3 graph E2E (5 path)

```
test_graph_e2e_hil2_interrupt_payload           # __interrupt__ 의 risky_groups + preview_cases
test_graph_e2e_hil2_resume_optimizer            # Command(resume=[key]) → optimizer → END
test_graph_e2e_hil2_skip_no_risky               # risky 0건 → conditional edge END 직행
test_graph_e2e_hil2_resume_empty_selection      # PM 빈 선택 → optimizer skip → END
test_demo_graph_e2e_namwong_dolgwan             # ★ 가짜 작업일보 (돌관) → build_demo_graph → advice
```

### 12.4 회귀 + Forecaster 권고 정합

기존 141 passed + 신규 **~34 test** → **~175 expected** (F9 정정). 0 회귀 expected (state.py / db.py / graph.py append only, atomizer/forecaster 코드 path 0 변경).

---

## 13. Phase 1 vs Phase 2

### 13.1 Phase 1 — 본 cycle (마감 2026-06-05)

| Task | 내용 |
|---|---|
| 0 | PG migration (optimizer_advice 5 컬럼 + forecasts **2 컬럼** v3.1) + 3곳 동기화 + WORK_HOURS_PER_DAY `pipeline/constants.py` 승격 + 환경 smoke test |
| 1 | state.py 정정 (CPIAState 3 필드) + Forecaster row **2 필드** (`main_unit` + `today_conditions`. today_productivity 이미 박힘) + Forecaster agent.py row dict + Forecaster spec design.md **§3 row 구조 + §10 agent.py 명세** drift 동기화 |
| 2 | synthetic_v2.py state machine **7 룰** (장비대기 1~3 + 우천 4 + 자재미입고 5 + 야간연장 6 + 돌관 7) + work_content 활동 풀 (l7_5_activity from PG) + assigned_workers prorate±10% + 돌관 spike ×1.3 (TDD) |
| 3 | synthetic_v2 CLI + 현 synthetic 810 row DROP + v2 적재 (90일 × 27 그룹) + **baseline 재검증 step 6** |
| 4 | retrieve.py 2 함수 (metadatas/documents 받음) + `_group_baseline` (None 분기 명시) + `_group_day_productivity` (TDD) |
| 5 | prompt.py system + few-shot 3 + `build_llm_user_input` (tone softening, conditions str) (TDD) |
| 6 | agent.py `optimize()` + `_compute_recovery_distribution` (코드단 산출) + `PGClient.insert_optimizer_advice` + cold_start (TDD) |
| 7 | optimizer integration tests (실 PG + 실 Chroma + 실 Azure, 남웅 1건) |
| 8 | checkpointer.py InMemorySaver + graph.py hil_2/optimizer node (coll.get 1회 통일) + conditional edge |
| 9 | graph E2E (interrupt + Command(resume=) + 5 path) |
| 10 | Forecaster Minor 권고 정리 (docstring/literal/임계값 상수화/boundary epsilon) |
| 11 | synthetic_daily_report.py 가짜 작업일보 1~3건 + build_demo_graph() + CLI (pipeline_runs INSERT + synthetic v2 적재 의무 확인) |
| 12 | 회귀 + 0 한자 검수 |

### 13.2 Phase 2 — PoC 이후 (운영 진입)

| 사안 | 비고 |
|---|---|
| PostgresSaver 전환 | InMemorySaver → PostgresSaver. Reporter cycle 또는 통합 cycle |
| FastAPI `/resume` 엔드포인트 | `api.py` 신규 — Dashboard 통합 |
| Optimizer LLM 결정성 검증 | response_format=json_object + 출력 schema validation 강화 |
| Chroma orphan cleanup | 가짜 작업일보 / synthetic_v2 reseeding 시 stale row 누적 |
| recommendations actionability 학습 | 실 PM 피드백 누적 후 prompt 강화 |
| 가짜 작업일보 → 실 작업일보 | Parser/Mapper LLM 통과한 실 데이터로 교체 |
| `recovery_pattern` 의미 정밀화 | 단순 dict list → 통계 metric |

---

## 14. 본 cycle 의 다음 단계

```
[즉시]
  1. spec doc 저장 (정정 v2)  ✓ 본 단계
  2. spec-document-reviewer 재 dispatch (coherence + feasibility 1 회)
  3. 사용자 spec review gate
  4. writing-plans → docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-plan.md
  5. subagent-driven-development 로 Task 0~12 실행
```

---

## 15. 미해결 사안 (Phase 1 전부 결정 + Phase 2 미해결 2건)

### 15.1 Phase 1 결정 완료 (5건)

| # | 사안 | 결정 |
|---|---|---|
| 1 | Forecaster row 의 `today_conditions` 필드 (today_productivity 는 Phase 1 시점 이미 박힘) | **본 spec §2.2 박음 (Task 1 동반 — 2 필드 추가)** |
| 2 | `_group_baseline()` 의 None 처리 | **§5.3 + §8.2 — `pre_cases[key]=[]` 분기 (F7 정정)** |
| 3 | 가짜 작업일보 scenario 의 BP사 수 | **§10.2 — 3 BP사 (남웅 + 세보 + 창원) default scenario** |
| 4 | LLM `recovery_distribution` 정합도 | **결정 #20 — 코드단 산출 + LLM 출력 override (§7 `_compute_recovery_distribution`)** |
| 5 | recommendations maxlen | **§6.1 SYSTEM_PROMPT — 3~4건 ranked** |

### 15.2 Phase 2 미해결 (v3 정정으로 명시 — PoC 이후)

| # | 사안 | 비고 |
|---|---|---|
| 6 | **인원 5분류 metric (조출/주간/연장/야간/철야) parser → atomizer → Chroma meta 전수** | 실 9/25 작업일보 [1.출력인원 현황] 시트 = 5분류 ground truth. parser.py:172-191 + atomizer schema + state.py 정정 큼. 본 cycle = Total 만 사용 (현 mapper `_prorate_mh()` 그대로). Phase 2 = 5분류 비율 (night_ratio 등) Optimizer 가 활용 |
| 7 | **`WORK_CONTENT_TEMPLATES` 실 작업일보 텍스트 풀** | 본 spec v3 정정으로 추측 풀 삭제. Phase 2 = 9/25 + 누적 작업일보 col7~9 (전일/금일/명일 작업사항) 텍스트에서 grep → 활동명 + 조건 텍스트 자연 결합. embedding 검색 의미 ↑ |

---

## 16. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-16 | 초안 v1 — Optimizer + hil_2 + synthetic v2 + 가짜 작업일보 + Forecaster 권고 4건 통합 spec. PM 원안 v2 §3 Week 3 Optimizer + H-i-L 2 정의 보존. downstream §7 supersede. 9/25 남웅 실 trace 시뮬 검증. 결정 사항 18건. Task 13개. | A 트랙 |
| 2026-05-16 | v2 정정 — coherence-reviewer (6 발견) + feasibility-reviewer (9 발견) 통합 12건 정정 + 사용자 결정 2건 반영. 주요 변경: ① conditions str 통일 (atomizer 패턴) ② Forecaster row schema 3 필드 박음 (main_unit + today_productivity + today_conditions) ③ baseline_value synthetic v2 적재 후 재검증 ④ state machine **7 룰** (rule 6 야간연장 + rule 7 돌관 인원 spike — 반도체 현장 핵심) ⑤ SYSTEM_PROMPT tone softening ⑥ recovery_pattern JSONB schema 명시 ⑦ `recovery_distribution` 코드단 산출 + LLM override ⑧ hil_2_node `coll.get` 1회 통일 (F5) ⑨ `_group_baseline` None 분기 명시 (F7) ⑩ build_demo_graph CLI 에 pipeline_runs INSERT + synthetic v2 적재 의무 ⑪ 회귀 expected 175 ⑫ §15 미해결 5건 전부 결정. 결정 사항 18 → **21건**. | A 트랙 |
| 2026-05-16 | v3.1 정정 — plan v1 feasibility-reviewer Blocker #1 + coherence-reviewer F1 반영. ① Forecaster row "3 필드 추가" → **"2 필드"** (main_unit + today_conditions). today_productivity 는 Phase 1 시점에 이미 박힘 (agent.py:163,196 + db.py:218 + PG forecasts 컬럼 실 검증). ② §3.2 ALTER 의 today_productivity 줄 제거. ③ §11.1 Forecaster spec drift 참조 정정 — "§6 row 정의" → "**§3 row 구조 + §10 agent.py 명세**" (§6 = classify, §3 = row 구조). ④ §13.1 Task 1 + §15.1 #1 동시 정정. PG forecasts 컬럼 수 25→27. | A 트랙 |
| 2026-05-16 | v3 정정 — 실 통합작업일보 (9/25) ground truth 검증 후 정정. 발견: ① 인원 분류는 시트1 의 **5분류** (조출/주간/연장/야간/철야 + Total) × 4 grouping (전일Incr/전일Cum/금일Incr/금일Cum) — 단순 주야 X. ② col7~9 작업사항 텍스트에 야간/연장/돌관/장비대기/자재미입고/우천 키워드 hit = **0건** (false positive 3건만). 실 텍스트는 단순 작업명. 정정 (사용자 결정 옵션 C): work_content = `f"{l7_5_activity}"` 단순 활동명 (조건 텍스트 제거), `WORK_CONTENT_TEMPLATES` 삭제 (Phase 2 정밀화 — 실 작업일보 풀에서 grep), conditions 메타 enum 그대로 유지, 5분류 metric 자체 = Phase 2 미해결 (parser/atomizer/state.py 정정 본 cycle scope 외). 결정 사항 21 → **23건**. §15 Phase 1/2 분리. | A 트랙 |
| 2026-05-17 | 본 cycle 종결 — Task 12 완료. ① §1.2 [3] baseline placeholder 15.981 (n=18) → **31.072 (n=54)** 갱신 (Task 3 실 적재 결과, 구 대비 +94% — assigned_workers prorated 분포가 만든 구조적 차이, 사용자 결정 = 의도). §0 결정 사항 row 15 동시 갱신. ② §10.2 conditions: comma-joined str → **list[str]** 정정 (state.Activity.conditions:list[str] 계약 + forecaster.py:92 iterate + atomizer.py:58 ",".join 입력 패턴과 정합, Task 11 implementer 발견). header + 본문 conditions_str 제거 + dict assign list 로 변경. ③ 회귀 183 passed (175~185 band, plan expected 182 = +1 from T5 fix boundary). ④ 0 한자 검수 통과. 본 cycle commit 16건 (T0~T11 + T0/T4/T5 fix 3건 + T12). spec v3.1 + plan v3 reviewer 3 round PASS. | A 트랙 |
