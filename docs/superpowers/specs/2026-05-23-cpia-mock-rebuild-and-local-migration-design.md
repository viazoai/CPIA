# CPIA Mock 데이터 재설계 + 로컬 검증 + AWS 마이그레이션 — 설계 문서

**작성:** 2026-05-23
**작성자:** Claude (brainstorming skill, 사용자 결정 13건 반영)
**대상 브랜치:** A_Track (CPIA branch)
**연계 문서:** `2026-05-22-cpia-report-optimizer-llm-backfill-design.md` (전 세션 본 plan)

---

## 1. Goal

24-04-11 ~ 25-09-24 전 기간 + 전 공종의 mock 데이터를 **F3 분포 (ramp + plateau + late-rise)** + **작업상황 conditions** + **l7.5 명확 매칭** + **5% outlier** 기준으로 재설계해서 로컬 PG/Chroma 에 적재한 뒤, mapper 이후 전 단계 (atomizer / forecaster / hil_2 / optimizer / reporter) 를 일별 배치 실행해서 FE UI 모든 페이지의 숫자가 의도대로 표시되는지 검증하고, 검증 통과 후 AWS RDS 로 안전 마이그레이션한다.

**시연 마감:** 2026-06-05 (목). 본 작업 = 시연 데이터 품질 확보.

---

**스콥 결정 (재확인)**: 5 phase **전부 본 spec + 본 implementation plan 단일** 진행. Phase E (AWS 마이그) 도 동일 plan 안의 마지막 phase. 사용자 명시: "페이즈 다른곳으로 넘기는거 절대 안돼 이번 스펙에 모든걸 다룰거야 마이그까지". reviewer 권장 (분리) 기각.

## 2. Scope (5 phase)

| Phase | 책임 | 산출물 |
|---|---|---|
| A. 로컬 DB 활성화 | `infra/docker-compose.yml` 가동 + `.env.local` swap (localhost) + FE 5536 가동 | docker compose up + FE 가 로컬 바라봄 |
| B. Mock 재설계 + seed | `scripts/seed_dummy_year.py` in-place 수정 (~60 줄). F3 분포 + conditions + l7.5 + outlier + l5_disc trade + prod target 역산 | 로컬 PG mapper_activities + Chroma daily_activities 적재 완료 |
| C. mapper 이후 배치 | `scripts/backfill_optimizer_advice_llm.py` 전 공종 (7 trade) 일별 호출. atomizer → forecaster → hil_2 → optimizer → reporter | 로컬 PG forecasts / optimizer_advice / daily_reports 적재 완료 |
| D. UI 페이지별 검증 | FE 5536 모든 페이지 (Tasks / Reports / Dashboard / Sites) 숫자 확인. 의도 일치 검증 | Playwright MCP screenshot + console 0 errors |
| E. AWS 마이그 + 머지 | pg_dump 백업 → AWS reset → 로컬 dump restore → 검증 → A_Track → main PR 머지 | AWS RDS 가 로컬과 동일 상태 |

---

## 3. Architecture & Data Flow

```
[activity_master (PG, 3704 row, l5_disc 7종, l7_5 100%)]
        ↓
[seed_dummy_year.py — F3 + conditions + outlier + prod target 역산]
        ├→ mapper_activities (PG, is_mock=true, 24-04-11~25-09-25, ~수십만 row)
        ├→ Chroma daily_activities (metadata.conditions / l7_5_activity)
        ├→ forecasts (PG, is_mock=true, today_conditions union 채움)
        └→ optimizer_advice (PG, is_mock=true, degradation_cases 7 tag)
        ↓
[backfill_optimizer_advice_llm.py --trades 7종 --start ~ --end]
        ├→ atomizer (mapper rows → Chroma upsert, embedding 호출)
        ├→ forecaster (Chroma 유사 case retrieve + LLM 진단)
        ├→ hil_2 (4분면 자동 라우팅)
        ├→ optimizer (LLM 조언 생성, retrieve.py incident kw 9종)
        └→ reporter (FE 보기용 view 갱신, site_summary LLM narrative 포함)
        ↓
[FE web/ port 5536 - Next.js dev]
        Tasks / Reports / Dashboard / Sites
        모든 숫자 = 위 PG/Chroma 소비 결과
```

**변경 코드 위치 (총 ~80 줄)**

| 파일 | 변경 | 줄수 |
|---|---|---|
| `scripts/seed_dummy_year.py` | F3 분포 함수 + conditions list 매핑 + l7.5 채움 + prod target 역산 + l5_disc trade | ~60 |
| `scripts/backfill_optimizer_advice_llm.py:53` | DEFAULT_TRADES → 7종 (`설비,전기,건축,UT,제어,소방,토목`) | 1 |
| `pipeline/agents/optimizer/retrieve.py:95` | incident keyword 5종 → 9종 (인력부족·재작업·병행작업·사양변경 추가) | 1 |
| `.env.local` | POSTGRES_URL + CHROMA_HOST 를 localhost 로 swap (마이그 후 AWS 로 되돌림) | 2 |
| `scripts/local_db_reset.py` (신규) | TRUNCATE all + Chroma delete daily_activities collection | ~30 |
| `scripts/aws_backup_and_migrate.py` (신규) | pg_dump + Chroma snapshot + AWS reset + restore | ~50 |

**변경 X (mapper 로직 불가침 사용자 의도)**: `pipeline/agents/mapper.py`, `atomizer.py`, `forecaster/agent.py`.

---

## 4. F3 분포 함수 (B Phase 핵심)

**의도**: 일일 시공량 (today_qty) 이 plan_start 부터 plan_finish 까지 piecewise 3 단계로 변동.

```python
RAMP_END = 0.15        # 초기 ramp-up: 0~15% of plan duration
PLATEAU_END = 0.85     # plateau: 15~85%
PEAK_MULT = 1.5        # late-rise peak: plateau 의 1.5×
INTEGRAL = 0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + (1 + PEAK_MULT) / 2 * (1 - PLATEAU_END)
P_NORM = 1.0 / INTEGRAL  # ≈ 1.039

def f3_daily_ratio(progress: float) -> float:
    """progress (0~1) → daily ratio (적분 = 1.0)."""
    if progress <= RAMP_END:
        return P_NORM * progress / RAMP_END
    if progress <= PLATEAU_END:
        return P_NORM
    return P_NORM * (1.0 + (progress - PLATEAU_END) / (1.0 - PLATEAU_END) * (PEAK_MULT - 1.0))

def f3_cum_ratio(progress: float) -> float:
    """progress (0~1) → cumulative ratio (0~1)."""
    if progress <= RAMP_END:
        return 0.5 * progress * progress / RAMP_END * P_NORM
    if progress <= PLATEAU_END:
        return (0.5 * RAMP_END + (progress - RAMP_END)) * P_NORM
    u = progress - PLATEAU_END
    late_part = u + 0.5 * (PEAK_MULT - 1.0) * u * u / (1.0 - PLATEAU_END)
    return (0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + late_part) * P_NORM
```

**검증** (POC `scripts/poc_mock_redesign.py` 실 호출):
- `f3_cum_ratio(0.15) = 0.078`
- `f3_cum_ratio(0.50) = 0.442`
- `f3_cum_ratio(0.85) = 0.805`
- `f3_cum_ratio(1.00) = 1.0000` ✓ (적분 정확)

---

## 5. 작업상황 conditions (B Phase)

**Tag → conditions list 매핑** (사용자 결정):

```python
TAG_TO_CONDS = {
    "weather_rain":   ["우천"],
    "manpower_short": ["인력부족"],
    "material_delay": ["자재미입고"],
    "rework":         ["재작업"],
    "trade_overlap": ["병행작업"],
    "spec_change":    ["사양변경"],
    "normal_steady":  ["정상"],     # ← 사용자 결정: 빈 list 아니라 ["정상"]
}
```

**적재 위치**:
1. `mapper_activities.conditions` (in-memory Activity object, atomizer 가 Chroma metadata 변환 시 사용)
2. `Chroma daily_activities.metadata.conditions` (comma-joined str, **SoT for forecaster/optimizer**)
3. `forecasts.today_conditions` (PG, optimizer 재사용용 캐시)
4. `optimizer_advice.degradation_cases[].conditions` (FE 표시용)

**소비 위치** (코드 변경 X, 데이터만 채워지면 자동 발현):
- `forecaster/agent.py:98` activities.conditions union
- `forecaster/agent.py:218` LLM prompt 에 박힘
- `forecaster/agent.py:268` Chroma similar metadata.conditions 도 prompt
- `forecaster/agent.py:279` forecasts.today_conditions 저장
- `optimizer/retrieve.py:95` incident keyword 매칭 (아래 §6)

---

## 6. retrieve.py incident keyword 9종 확장 (C Phase 보강)

**변경** (`pipeline/agents/optimizer/retrieve.py:95`):

```python
# Before: ["장비대기", "자재미입고", "돌관", "우천", "야간연장"]  (5종)
# After:
INCIDENT_KEYWORDS = ["장비대기", "자재미입고", "돌관", "우천", "야간연장",
                     "인력부족", "재작업", "병행작업", "사양변경"]  # 9종
```

**효과**: seed 가 박은 7 tag conditions 가 모두 optimizer degradation_cases 에서 발현됨 (이전엔 weather_rain + material_delay 만 발현 → 다양성 X).

**`normal_steady → ["정상"]`** 는 incident 아니므로 매칭 안 됨 (intentional, baseline 후보).

---

## 7. Productivity 산출 (prod target 역산 방식, B Phase)

**기존 방식** (POC 에서 실패):

```python
cum_actual_mh = today_cum_qty × ANCHOR_SITE_MH_PER_QTY (5.1747) × noise
# 문제: row 별 plan_mh_per_qty 가 0.28~1255 변동 → prod 0.4%~1750% 극단치
```

**새 방식** (사용자 결정 = 옵션 A):

```python
PROD_TARGET = 90.0   # 사용자 명시
if is_outlier:       # 5%
    actual_prod_pct = rng.choice([50.0, 150.0])
else:                # 95%
    actual_prod_pct = PROD_TARGET * (1.0 + rng.uniform(-0.10, 0.10))  # 81~99
cum_actual_mh = plan_mh * progress * actual_prod_pct / 100.0
```

**효과 (POC 실측)**:
- 76 건축 row min 81.7 / median 89.0 / p95 98.8 (목표 90% ± 10% 정확 일치)
- 606 전공종 row outlier 5.45% (목표 5% 정확)

---

## 8. l7.5 매칭 (B Phase)

**`activity_master.l7_5_activity` 100% 채워짐 확인** (3704/3704, distinct 413).

**변경**:

```python
# seed_dummy_year.py _build_mapper_row() return dict 에 추가:
"l7_5_activity": am_row["l7_5_activity"],
# chroma_upsert_day metadata 에 추가:
"l7_5_activity": valid[i]["l7_5_activity"],
```

**mapper 로직 변경 X**. atomizer 의 `_build_metadata()` 가 이미 `l7_5_activity` 필드 지원 (`pipeline/agents/atomizer.py:58`).

---

## 9. l5_disc → trade 매핑 (B Phase)

**현재 seed**: `mapper_activities.trade = am_row.get("trade") or "건축"` (activity_master 에 trade 컬럼 X → 항상 "건축").

**변경**: `trade = am_row["l5_disc"]` (직접 사용).

**`backfill_optimizer_advice_llm.py:53`**:

```python
# Before:
DEFAULT_TRADES = ("건축", "토목")
# After:
DEFAULT_TRADES = ("설비", "전기", "건축", "UT", "제어", "소방", "토목")
```

활성 row 분포 (25-09-24 기준 606 row): 설비 249 / UT 150 / 전기 80 / 제어 59 / 건축 57 / 소방 8 / 토목 3.

---

## 10. anchor 정합 (B Phase)

**사용자 결정**: 유지 (9-25 에는 anchor row 정합).

**핵심 정의 — 모든 일자 (24-04-11 ~ 25-09-25) 가 동일 F3 + prod target 역산 logic 적용**. anchor row 별도 fixture 보존 X. "anchor 정합" 의 정확한 의미는 아래.

**Per-row 산출 식** (mock 일자 d, activity_master row a):

```
total_days = (a.plan_finish - a.plan_start).days + 1
days_elapsed = (d - a.plan_start).days + 1   # 단, plan_start ≤ d ≤ plan_finish 조건 (그 외 row 미적재)
progress = days_elapsed / total_days

today_qty       = a.plan_total_qty / total_days * f3_daily_ratio(progress) * noise_qty
today_cum_qty   = a.plan_total_qty * f3_cum_ratio(progress)
cum_actual_mh   = a.plan_mh_rev2 * progress * actual_prod_pct / 100
```

**anchor row (25-09-25) 의 정합 의미**:
- anchor row = `d == 2025-09-25 AND plan_start ≤ d ≤ plan_finish` 인 activity_master row 들 (seed 가 적재)
- 위 식이 25-09-25 에 적용되면 anchor row 의 today_qty 가 자연스럽게 plan 잔여 진척 일치 (별도 정합 step 불필요)
- progress(2025-09-25) 는 row 마다 다름: plan_finish 가 25-09-25 인 row 는 progress=1.0 → `f3_cum_ratio(1.0)=1.0` → today_cum_qty=plan_total_qty (완공). plan_finish 가 26-03-31 인 row 는 progress<1.0 → today_cum_qty<plan_total (진행 중).
- 모든 row 동일 logic — `seed_dummy_year.py:223` 의 기존 Case A (anchor row 의 today_cum_qty 직접 사용) 분기 **제거**.

**기존 Case A 제거 사유**: 기존 Case A 는 실 9-25 mapper_activities row 에서 today_cum_qty 가져와 cum_actual_mh = today_cum_qty × ANCHOR_SITE_MH_PER_QTY 사용 → POC 에서 prod 극단치 (0.4~1750%) 원인. 새 logic 은 anchor 도 mock 으로 통일 → prod 81~99% (normal) / 50·150% (outlier 5%) 정상 범위.

**검증 케이스 (test_seed_anchor_consistency.py)**:
- 9-25 적재된 row 중 plan_finish=2025-09-25 row 는 today_cum_qty ≈ plan_total_qty × 1.0 ± noise (완공 보장)
- 9-25 row 와 9-24 row 의 cumulative jump 가 1 day 분 + noise 안 (연속성 보장)

---

## 11. Phase A. 로컬 DB 활성화

**Step 1**. `infra/` 에서 docker compose up:

```bash
cd infra
docker compose up -d postgres chroma adminer  # web 은 별도
# verify: docker ps --filter "name=cpia-"
```

**Step 2**. `.env.local` 의 `POSTGRES_URL` / `CHROMA_HOST` 를 localhost 로 swap:

```diff
- POSTGRES_URL=postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia
+ POSTGRES_URL=postgresql://cpia:cpia@localhost:5532/cpia
- CHROMA_HOST=43.200.85.209
+ CHROMA_HOST=localhost
```

**Step 3**. FE 5536 (`npm run dev` in `web/`):

```bash
cd web
npm run dev  # http://localhost:5536
```

**Step 4**. `infra/postgres/migrations/` 마이그레이션 적용 확인 (compose init 시 자동). activity_master 적재 (AWS dump 또는 seed):

```bash
# activity_master 가 비어 있으면 AWS 에서 dump 후 로컬 restore
PGPASSWORD=K7mP2xQ9nR4v pg_dump -h 43.200.85.209 -p 5532 -U cpia -d cpia \
  -t activity_master -t sites > tmp/activity_master.sql
PGPASSWORD=cpia psql -h localhost -p 5532 -U cpia -d cpia -f tmp/activity_master.sql
```

---

## 12. Phase A.1 — `scripts/local_db_reset.py` (신규, ~30 줄)

```python
"""로컬 DB reset — TRUNCATE all mock data + Chroma daily_activities delete."""
async def main():
    pg = await asyncpg.connect("postgresql://cpia:cpia@localhost:5532/cpia")
    # TRUNCATE CASCADE 순서: 자식부터
    for tbl in ["optimizer_advice", "forecasts", "daily_reports",
                "mapper_activities", "parser_activities", "pipeline_runs"]:
        await pg.execute(f"TRUNCATE TABLE {tbl} RESTART IDENTITY CASCADE;")
    await pg.close()
    chroma = ChromaClient(host="localhost", port=5533)
    try: chroma.delete_collection("daily_activities")
    except Exception: pass
    print("✓ 로컬 DB reset 완료")
```

활성 row source (`activity_master`, `sites`) 는 reset 대상 X (다시 적재 부담).

---

## 13. Phase B — seed_dummy_year.py 수정 detail

**변경 항목 (in-place, ~60 줄). 명시되지 않은 기존 logic 은 보존 (surgical edits 룰)**:

### 13.1 상수 추가 (파일 상단)

```python
RAMP_END = 0.15
PLATEAU_END = 0.85
PEAK_MULT = 1.5
INTEGRAL = 0.5*RAMP_END + (PLATEAU_END-RAMP_END) + (1+PEAK_MULT)/2*(1-PLATEAU_END)
P_NORM = 1.0 / INTEGRAL  # ≈ 1.039
PROD_TARGET = 90.0
OUTLIER_PROB = 0.05
TAG_TO_CONDS = {
    "weather_rain":   ["우천"],
    "manpower_short": ["인력부족"],
    "material_delay": ["자재미입고"],
    "rework":         ["재작업"],
    "trade_overlap":  ["병행작업"],
    "spec_change":    ["사양변경"],
    "normal_steady":  ["정상"],
}
```

### 13.2 함수 추가

`f3_daily_ratio(progress)`, `f3_cum_ratio(progress)` — §4 정확 코드 사용 (~15 줄).

### 13.3 `_pick_diagnosis` 변경 (signature 명시)

**기존 return**: `dict[str, Any]` with keys `tag` / `diagnosis` / `recommendations`.
**변경 후 return**: 동일 dict + 새 key `conditions: list[str]` 추가 (backward compatible).

```python
def _pick_diagnosis(date_str: str, wa: str, company: str, l6: str) -> dict[str, Any]:
    idx = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16) % len(DIAGNOSIS_PATTERNS)
    pat = DIAGNOSIS_PATTERNS[idx]
    return {
        "tag": pat["tag"],
        "diagnosis": pat["text"].format(l6=l6, company=company),
        "recommendations": [r.format(l6=l6, company=company) for r in pat["recs"]],
        "conditions": TAG_TO_CONDS[pat["tag"]],   # ← new
    }
```

**Tag 분포**: hash mod 7 → uniform 균등 (1/7 ≈ 14.3%). 단일 일자에서는 sample 작아 비균등 (POC 검증 — 606 row weather_rain 3.14% ~ material_delay 28.05%), 일자 평균하면 균등 근처. **weight 적용 X** (의도된 단순 hash 균등).

### 13.4 `_build_mapper_row` 변경 (in-place 교체 위주)

**보존 항목** (그대로 두기):
- function signature + Case A / Case B 외부 분기 구조 (단 Case A 의 anchor today_cum_qty 직접 사용 부분 §10 명시대로 제거)
- `is_near_anchor`, `qty_noise_scale` 변수 — F3 noise 와 별개 (그대로 사용해도 됨, optional)
- mapping_conf, mapping_source, requires_review, work_content 등 metadata 컬럼 (그대로 박힘)
- parser pass-through 컬럼 (`note`, `work_location_code`, `wbs_*` etc.) — 그대로 빈 값
- 단, return dict 에 `l7_5_activity` (am_row 에서) + `conditions` (tag 매핑) 키 추가

**교체 항목** (~25 줄):
- 선형 분배 (`base_daily_qty = plan_total / total_days`) → F3 분포 (§4)
- cum_actual_mh 산출 (`today_cum_qty × ANCHOR_SITE_MH_PER_QTY × noise`) → prod target 역산 (§7)
- `trade = anchor_row.get("trade") or am_row.get("trade") or "건축"` → `trade = am_row["l5_disc"]`

```python
# 교체 후 핵심 라인 (Case A / Case B 모두 동일)
ratio_today = f3_daily_ratio(progress)
cum_frac = f3_cum_ratio(progress)
rng = _seeded_rng(f"{d}|{am_row['wa']}|{am_row['company']}")
is_outlier = rng.random() < OUTLIER_PROB
actual_prod_pct = rng.choice([50.0, 150.0]) if is_outlier \
    else PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)
today_qty = plan_total / total_days * ratio_today * (1.0 + (rng.random() * 2 - 1) * 0.10)
today_cum_qty = plan_total * cum_frac
cum_actual_mh = plan_mh * progress * actual_prod_pct / 100.0
diag = _pick_diagnosis(str(d), am_row["wa"], am_row["company"], am_row["l6_main"])
conditions = diag["conditions"]
```

### 13.5 `_build_forecast_row` 변경 (~3 줄)

```python
# 기존: "today_conditions": "",
conditions_set = sorted({c for a in activities for c in (a.get("conditions") or [])})
"today_conditions": ",".join(conditions_set) if conditions_set else "",
```

### 13.6 `chroma_upsert_day` 변경 (~3 줄)

`metadatas` dict 에 새 키:

```python
"conditions": ",".join(valid[i].get("conditions") or []),
"l7_5_activity": valid[i].get("l7_5_activity") or "",
```

### 13.7 `_build_optimizer_advice` 변경 (~2 줄)

`degradation_cases[].conditions` 를 tag str → list 로 (`retrieve.py` 의 substring 매칭 호환):

```python
"conditions": ",".join(diag["conditions"]),  # comma-joined str (Chroma 패턴 통일)
```

---

## 14. Phase C — mapper 이후 배치

**기존 `backfill_optimizer_advice_llm.py` 활용**. 변경 점: `DEFAULT_TRADES` 7종.

### 14.1 Default 실행 = 시연 윈도우 우선 (사용자 결정)

```bash
# Step 1 — 시연 윈도우 25일 (9/1 ~ 9/25). UI 검증 우선.
pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2025-09-01 --end-date 2025-09-25 \
  --site m15x-ph3-ibl \
  --trades 설비,전기,건축,UT,제어,소방,토목 \
  --clean
```

**예상 시간**: 25일 × 5분/일 (병렬 4×) ≈ **2시간**. 즉시 UI 검증 가능.

### 14.2 전 기간 batch — Phase D 통과 후 본 plan 내 후속 step

```bash
# Step 2 — Phase D 통과 후 전 기간. 본 plan 의 Phase C 두 번째 step (또는 Phase D 와 E 사이 step) 로 진행.
pipeline/.venv/bin/python3 scripts/backfill_optimizer_advice_llm.py \
  --start-date 2024-04-11 --end-date 2025-08-31 \
  --site m15x-ph3-ibl \
  --trades 설비,전기,건축,UT,제어,소방,토목 \
  --clean
```

**예상 시간**: 505일 × 5분/일 (병렬 4×) ≈ **42시간**. CPIA_LLM_CONCURRENCY 2 로 낮추면 ~84시간 (Azure rate limit 안전).

### 14.3 Azure rate limit 검토

- gpt-5.1-chat-ai-board-test TPM: 사내 AI Board 발급 (정확한 한도 unknown, SK 사내 부서 문의 필요)
- text-embedding-3-small TPM: 동일
- 본 spec 진행 시: 시연 윈도우 (25일) 는 CPIA_LLM_CONCURRENCY=4 안전. 전 기간 (505일) 은 2 권장.
- 5분/일 = 1일 cycle 당 forecaster (1 LLM call × 그룹 수 / 4 병렬) + optimizer (1 LLM call × risky 그룹 수 / 4 병렬) + reporter site_summary (1 LLM call). 평균 LLM call ~40 / 일. 25일 × 40 = 1000 call ≈ 2시간 안 (안전).

**중간 fail 시 재시작**: `--clean` 이 advice / forecasts / daily_reports 만 DELETE (mapper 보호) → 멱등성 보장.

---

## 15. Phase D — UI 검증 항목

**모든 FE 페이지 (5536) 의 숫자 소비 확인**.

| 페이지 | 검증 항목 | 소비 SQL/소스 |
|---|---|---|
| `/` Dashboard | 6 site 카드 (진척률 / 지연 / 인력 등) | `sites`, `pipeline_runs`, `forecasts` 집계 |
| `/tasks` | 일자별 mapper 진행 progress | `/api/mock/agent-tasks` (is_mock=true 90일) |
| `/reports/[date]` | 일자별 forecasts + optimizer_advice (S-curve, 4분면, by_wp, degradation_cases) | `forecasts`, `optimizer_advice`, `daily_report_views_v2` |
| `/sites/[id]` | site KPI (delay MEDIAN, productivity, evm) + ForecastChart aiSummaryText | `daily_report_views_v2.site_summary` |
| `/review` | mapper review (waiting_hil_1) | `pipeline_runs.status` |
| `/consolidated` | 통합 작업일보 출력 | `daily_reports` |

**검증 방식**: Playwright MCP `browser_navigate` + `browser_console_messages` + `browser_take_screenshot`. console 0 errors + SQL assertion.

### 15.1 SQL assertion (자동 검증)

| # | 페이지/source | SQL | 통과 기준 |
|---|---|---|---|
| 1 | site_summary LLM narrative | `SELECT COUNT(*) FROM daily_report_views_v2 WHERE site_summary IS NULL` | = 0 (모든 시연 일자 채워짐) |
| 2 | quadrant ↔ by_wp | `SELECT (1.0 - COUNT(DISTINCT q.wp_id) / NULLIF(COUNT(DISTINCT w.wp_id), 0)) FROM ...` (T17 보강 logic) | ≤ 0.01 (∩ ≥ 99%) |
| 3 | degradation_cases 4 필드 | `SELECT 1.0 * SUM(jsonb_array_length(degradation_cases) FILTER (WHERE ...)) / COUNT(*)` | ≥ 0.90 (4 필드 모두 채워진 비율) |
| 4 | delay 음/양 분포 | `SELECT SUM(CASE WHEN delay_days < 0 THEN 1 ELSE 0 END), SUM(CASE WHEN delay_days > 0 THEN 1 ELSE 0 END)` | 각 ≥ 1 (single skew 아님) |
| 5 | F3 S-curve 적용 | `SELECT MAX(today_cum_qty) / MAX(plan_total_qty) FROM mapper_activities WHERE report_date = (max plan_finish row)` | ≥ 0.95 (완공 row 가 plan_total 의 95% 이상 도달 = F3 적분 정상) |
| 6 | conditions tag 다양성 | `SELECT COUNT(DISTINCT conditions) FROM (chroma 또는 _build_optimizer_advice degradation_cases.conditions)` | ≥ 5 (7 tag 중 5 이상 발현) |
| 7 | productivity 분포 정상 | `SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY today_productivity) FROM forecasts` | 80 ≤ median ≤ 100 |
| 8 | outlier 5% 발현 | `SELECT 1.0 * SUM(CASE WHEN today_productivity < 60 OR today_productivity > 130 THEN 1 ELSE 0 END) / COUNT(*) FROM forecasts` | 0.02 ≤ pct ≤ 0.10 |

### 15.2 시각 검증 (Playwright MCP, screenshot 보존)

- `/` Dashboard 6 site 카드 — 진척률/지연/인력 텍스트 박힘
- `/tasks` 일자별 progress bar 표시
- `/reports/2025-09-25` 4 섹션 (S-curve + 4분면 + by_wp + degradation_cases) 모두 그려짐
- `/sites/m15x-ph3-ibl` 사이트 KPI delay (MEDIAN) + ForecastChart aiSummaryText 자연어 narrative
- 모든 페이지 console 0 errors

---

## 16. Phase E — AWS 마이그 + 머지

**Step 1. AWS 백업** (`scripts/aws_backup_and_migrate.py --mode backup`):

```bash
# pg_dump (mapper_activities, parser_activities, forecasts, optimizer_advice,
#         daily_reports, pipeline_runs, mapped_history, activity_master, sites)
PGPASSWORD=K7mP2xQ9nR4v pg_dump -h 43.200.85.209 -p 5532 -U cpia -d cpia \
  --exclude-table=checkpoints \
  > tmp/aws-backup-$(date +%Y%m%d-%H%M).sql

# Chroma snapshot — daily_activities collection export
python scripts/chroma_export.py --collection daily_activities \
  --host 43.200.85.209 --port 5533 \
  --out tmp/chroma-aws-$(date +%Y%m%d-%H%M).jsonl
```

**Step 2. FE 가 AWS 다시 바라보게 swap** (env 복원) + 화면 reset 확인:
- 모든 페이지 0건 또는 stale 데이터만 (mock 적재 전 상태)

**Step 3. AWS reset** (백업 후 안전):
- `python scripts/local_db_reset.py --target aws` (TRUNCATE 동일)

**Step 4. 로컬 dump → AWS restore**:
```bash
pg_dump -h localhost -p 5532 -U cpia -d cpia --exclude-table=checkpoints \
  > tmp/local-to-aws.sql
PGPASSWORD=K7mP2xQ9nR4v psql -h 43.200.85.209 -p 5532 -U cpia -d cpia \
  < tmp/local-to-aws.sql

# Chroma 도 동일 (export + import)
```

**Step 5. AWS UI 검증**: FE 가 AWS 바라보게 swap → 모든 페이지 재검증 (Phase D 와 동일).

**Step 6. 커밋 + PR + 머지**:
- A_Track → main PR 생성 (PR 본문에 본 plan + Phase D screenshot 첨부)
- 사용자 (조형준 프로님) 가 PR 보고 결정 — main 머지 권한 사용자만

---

## 17. Testing Strategy

| 테스트 | 위치 | 의도 |
|---|---|---|
| `test_f3_distribution.py` | `pipeline/tests/synthetic/` | F3 적분 = 1.0, ramp/plateau/late-rise 경계 값 검증 |
| `test_seed_conditions.py` | `pipeline/tests/synthetic/` | 7 tag → conditions list 매핑, normal_steady = ["정상"] |
| `test_seed_l7_5_propagation.py` | `pipeline/tests/synthetic/` | seed → mapper row → Chroma metadata 까지 l7.5 전파 |
| `test_seed_prod_target.py` | `pipeline/tests/synthetic/` | normal 81~99 / outlier 50 or 150, 5% 빈도 (1000 sample) |
| `test_retrieve_incident_9kw.py` | `pipeline/tests/optimizer/` | 9 keyword 모두 substring 매칭 동작 |
| 회귀 — fast scope | `pipeline/tests/*` | 본 변경이 기존 159 fast pass 유지 |
| 통합 E2E — 1일치 | `tests/e2e/` (수동) | 25-01-15 cycle 통과 + UI Playwright screenshot |

**TDD 룰**: 새 기능 = 실패 테스트 먼저 → 구현 → green.

---

## 18. Risks & Mitigations

| 위험 | 영향 | 완화 |
|---|---|---|
| 530일 backfill 시 Azure rate limit | C Phase 진행 정지 | CPIA_LLM_CONCURRENCY env 조정 (default 4 → 2), chunk 분할 실행 |
| anchor row (25-09-25) 정합 logic 복잡도 | 9-25 cum_qty 불일치 | §10 의 통일 logic 으로 모든 일자 동일 식 적용 (Case A 분기 제거). `test_seed_anchor_consistency.py` 로 9-25 완공 row (plan_finish=25-09-25) today_cum_qty ≈ plan_total_qty 검증 |
| FE 가 AWS bypass 캐시 잡혀 stale | UI 검증 오판 | `rm -rf web/.next` + next-server restart |
| 로컬 PG/Chroma 디스크 부족 | docker volume 가득 | docker volume prune + sites 표만 유지 |
| `activity_master` 변경되면 mock 재seed 필요 | spec 외부 영향 | activity_master 변경 시 `scripts/local_db_reset.py` 재실행 명시 |
| AWS reset 도중 fail | 데이터 손실 | pg_dump 백업 보존 (tmp/aws-backup-*.sql) + 사용자 명시 동의 후만 실행 |
| Chroma snapshot/restore 미완 | 유사사례 검색 깨짐 | `chroma_export.py` / `chroma_import.py` 작성 검증 |

---

## 19. References

- 전 세션 본 plan: `docs/superpowers/specs/2026-05-22-cpia-report-optimizer-llm-backfill-design.md`
- POC 코드: `scripts/poc_mock_redesign.py` (brainstorming 검증용 ad-hoc)
- POC 결과 화면: `.superpowers/brainstorm/89070-1779491542/poc-result-v2.html`
- 기존 seed: `scripts/seed_dummy_year.py:202-322` (`_build_mapper_row`)
- backfill: `scripts/backfill_optimizer_advice_llm.py`
- Conditions flow: `pipeline/agents/forecaster/agent.py:98,218,268,279` + `pipeline/agents/optimizer/retrieve.py:54,95,120,132`
- DB schema: `infra/postgres/init.sql:170` (`l7_5_activity`)
- CPIA CLAUDE.md (A_Track 분담, 시연 마감, FE 디자인 불가침 룰)

---

## 20. Phase 진행 가이드 (요약)

```
A. docker compose up + .env swap + npm run dev → 5536 작동
B. seed_dummy_year.py 수정 + tests TDD → 1일 in-memory POC 통과 → 로컬 PG/Chroma 적재
C. backfill_optimizer_advice_llm.py 호출 (chunk 또는 전 기간)
D. FE 5536 모든 페이지 Playwright 검증 + console 0 errors
E. pg_dump → AWS reset → 로컬 dump 적용 → AWS 검증 → PR → 머지
```

**plan 작성** (writing-plans skill) 은 본 spec 확정 후 별도 단계. 본 spec 의 §11~§16 이 plan 의 phase 입력.
