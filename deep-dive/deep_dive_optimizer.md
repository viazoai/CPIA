# Deep Dive — Optimizer Subsystem

- **Generated**: 2026-05-26
- **Baseline**: `ef7c6cd` (이전 design-intent cycle)
- **HEAD**: `1ba783f` (A_Track, "Merge origin/main into A_Track — Mock 재설계 PR #40 머지 전 sync")
- **Pair**: `./architecture_overview.md`, `./design-intent/design_intent_optimizer.md`
- **Working tree**: 1 줄 변경 잔존 — `view_builder.py:1447` `AND ma.trade IN ('건축', '토목')` 1 줄 삭제 (다른 세션). 미커밋.
- **파일 인벤토리 (절대경로)**:
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/agent.py` — 227 LOC
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/prompt.py` — 316 LOC
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/retrieve.py` — 206 LOC
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/site_summary.py` — **141 LOC (신규 21c10f7)**
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/synthetic_v2.py` — 363 LOC
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/synthetic_daily_report.py` — 498 LOC
  - `/Users/kyungseoplee/Project Agent/CPIA/pipeline/agents/optimizer/view_builder.py` — **1882 LOC (이전 752 → +1130)**
  - `__init__.py` 8 LOC
- **합계** ~3,641 LOC (이전 ~2,449 → +1,192)

---

## 1. Overview — Optimizer 의 3 책임

이번 cycle 에서 Optimizer 서브시스템은 단일 LLM 조언 산출기에서 **종합 대시보드 백엔드** 로 성장. 단일 LangGraph 노드 `optimize()` 가 **세 가지 결정론적 산출물** 을 1 호출에 모두 만든다:

```
                       ┌────────────────────────────────────────┐
                       │      optimize()  (agent.py:121)         │
                       │                                          │
   forecast (Forecaster)│   (a) LLM advice  (4× asyncio.gather)    │   optimizer_advice
   hil_2_selection ────▶│       prompt.py + retrieve.py             │──▶  (PG INSERT)
   pre_optimizer_cases │                                          │
                       │   (b) view_builder 9 jsonb               │   daily_reports
   site_id (state)    │       view_builder.py 1882 LOC           │──▶  (.{9 cols} jsonb)
   mapped (Mapper)    │       _build_kpi / contractor / trade /  │   UPSERT (UPDATE-first)
                       │       quadrant / wp_summary / s_curve /  │
                       │       optimizer_view / productivity /    │
                       │       scenarios                          │
                       │                                          │
                       │   (c) site narrative (별도 호출자 backfill)│   daily_reports
                       │       site_summary.py (LLM, JSON mode)   │──▶  .site_summary_text
                       └────────────────────────────────────────┘
```

세 산출물은 **시연 화면 1단 (KPI 카드 + 진척 narrative)**, **2단 (4분면 + WP 표)**, **3단 (LLM 진단/권고)** 을 모두 채운다. UI 라우트 (`/sites/{id}`, `/dashboard`) 는 daily_reports 1 row + optimizer_advice N row 만 SELECT 하면 완성.

본 cycle 의 사용자 핵심 결정 (c0a0641): **`_build_s_curve` 의 공정률 산식 재설계 — WV × MH 가중 + activity 단위 매칭 + progress cap (산식 A)** — 시연 핵심 지표(현장 진척률)의 의미가 바뀜.

---

## 2. 파일 + LOC + 책임

| 파일 | LOC | 책임 | 본 cycle 변경 |
|---|---|---|---|
| `agent.py` | 227 | optimize() — LLM 호출 + 9 jsonb orchestration + PG write | `690c305` perf: 4× asyncio.gather + to_thread |
| `prompt.py` | 316 | SYSTEM_PROMPT + FEW_SHOT_MESSAGES 3 + `build_llm_user_input` | (변경 없음) |
| `retrieve.py` | 206 | 2-step degradation case 검색 + recovery trajectory + `_group_baseline` | `d79a438` INCIDENT_KEYWORDS 5→9종, `82bb8af` degradation 정의 완화 (OR), worker_source 화이트리스트 제거 |
| `site_summary.py` | 141 | **신규 (21c10f7)** — kpi+scenarios+wp_summary+optimizer_view+s_curve → 1~2단락 narrative (Azure JSON mode) | 파일 신설 |
| `synthetic_v2.py` | 363 | 27 그룹 × 90일 backfill (state machine, 회복 룰 7건) | (논리 변경 없음) |
| `synthetic_daily_report.py` | 498 | 가짜 작업일보 + `build_demo_graph` CLI (Parser/Mapper skip) | (변경 없음) |
| `view_builder.py` | 1882 | 9 jsonb 산출 + EVM + cold_start + scenarios + s_curve + v2 통합 산식 | `c0a0641` s_curve 산식 A, `e9b66d4` delay AVG→MEDIAN, `2c2ba75` T17 quadrant↔by_wp, `ba505da` dead code 제거, 다수 phase2 commits |

---

## 3. agent.py `optimize()` walkthrough

진입점: `pipeline/agents/optimizer/agent.py:121`. 호출자는 `pipeline/graph.py` 의 optimizer 노드 (production) 또는 `synthetic_daily_report.py` 의 CLI demo.

```python
async def optimize(
    forecast: list[dict],
    hil_2_selection: list[str],
    pre_optimizer_cases: dict[str, list[dict]],
    run_id: uuid.UUID,
    today: date,
    cfg: OptimizerConfig,
    site_id: Optional[str] = None,
    mapped: Optional[list] = None,
) -> list[dict]:
```

흐름:

1. `AzureOpenAI` client 1 회 init (agent.py:149).
2. `sem = get_llm_semaphore()` — closure 로 공유 (agent.py:157).
3. **`_process_one(r, cases)`** 정의 (agent.py:159) — `sem` 안에서만 `await _call_azure_llm_async(...)` 호출 → PG write 는 sem 밖.
4. forecast 루프 (agent.py:166) — `key = f"{r['company']}|{r['l6_main']}"` 가 hil_2_selection 안에 있는 row 만 task 등록. cold_start (cases<3) 도 LLM 호출 (`SYSTEM_PROMPT` 의 "degradation_cases 빈 array" 분기 사용 — 이전 `_compose_cold_start_row` placeholder 폐기, `ba505da`).
5. **`advice_rows = list(await asyncio.gather(*tasks))`** (agent.py:176) — **본 cycle `690c305` 핵심 perf 변경**. 이전 순차 루프 (forecast 행마다 sync 호출) 대비 4× 단축.
6. `PGClient` connect (agent.py:178) → 각 advice row 마다 `pg.insert_optimizer_advice(row)` (agent.py:182).
7. **view_builder 9 jsonb 산출 블록** (agent.py:185~222):
   - `_build_productivity_views` (EVM site/by_contractor/by_l6/by_wp 4 segment)
   - `_build_quadrant` (productivity 결과 + impact P90)
   - **`wa_lookup` 산출** — `mapper_activities` 에서 `(l6_main, company) → DISTINCT wa list`. `_build_optimizer_view` 의 fan-out 용 (spec §8.3, quadrant dot 의 wp_id 와 by_wp key 매칭 보장).
   - 9 jsonb dict 생성 후 `pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)` (agent.py:220) 9 회 — 각 컬럼별 try/except 로 **partial write 보장**.
8. `pg.close()` (finally) — return advice_rows.

`_compute_recovery_distribution` (agent.py:64) 은 결정 #20 — `Counter([c["recovery"]["recovery_days"] for c in cases])` 로 코드단 deterministic 산출. LLM 응답에 `recovery_distribution` 박혀 있어도 `_compose_row` (agent.py:85) 에서 override.

`_call_azure_llm` (agent.py:101) 은 **fail-fast** — `azure.chat.completions.create(response_format={"type": "json_object"})` 실패 시 exception 그대로 raise (결정 #10). retry 없음.

---

## 4. view_builder.py 1882 LOC — 함수 전수표

`_build_*` (uppercase: 9 jsonb 산출의 entry-point) 와 `_*` helper 구분. 모든 line 은 `view_builder.py:N` 기준.

### Phase 1 — EVM 산출 (`_build_productivity_views` + sub)

| Func | Line | Signature (단축) | 의도 |
|---|---|---|---|
| `_sanitize_case_pp` | 14 | `(raw_pp, master_pp, seed_key) -> float` | ChromaDB perperson 이 master 의 30~200% 밖이면 master ±10% deterministic stub (mh 단위 적재 오류 대응) |
| `_sanitize_workers` | 33 | `(raw_w, master_w, seed_key) -> int` | assigned_workers > 50 이면 master ±10% 또는 raw/8 fallback |
| **`_build_productivity_views`** | 48 | `async (pg, run_id, site_id, today, forecast, mapped) -> dict` | EVM 4 segment: today + by_contractor + by_l6 + by_wp |
| `_evm_for_group` | 79 | `async (pg, site_id, today, group_key) -> dict` | site 전체 EVM — 분모=마스터플랜 전체, 분자=mapper_activities 전체 |
| `_compose_evm` | 125 | `(plan_row, actual_row) -> dict` | EV/PV/AC/SPI/CPI 산식 |
| `_evm_by_group` | 161 | `async (pg, site_id, today, group_key) -> dict[str, dict]` | company / l6_main 별 EVM. **actual anchor** (2026-05-20 spec §8.1) — 매핑된 group 만 표시 |
| `_evm_by_wa_l6_company` | 238 | `async (pg, site_id, today) -> dict[str, dict]` | (wa, l6, company) WP 단위 EVM — wa 가 mapper 전용 키이므로 mapper anchor |

EVM 산식 (`_compose_evm` view_builder.py:125):
```
progress = cum_actual_qty / plan_qty_full
EV       = progress × plan_mh_full
PV       = cum_plan_mh
AC       = cum_actual_mh
SPI      = EV / PV × 100
CPI      = EV / AC × 100
```

### Phase 2 — KPI / 4분면 / WP 표

| Func | Line | Signature | 의도 |
|---|---|---|---|
| **`_build_kpi`** | 284 | `async (pg, site_id, today, productivity) -> dict` | 헤더 KPI — productivity_today / spi / cpi / target / delay_days / expected_completion. **2026-05-23 `e9b66d4` AVG → MEDIAN** |
| `_bar_status` | 322 | `(cpi: float) -> str` | CPI 분기 normal(≥90) / caution(≥80) / risk |
| `_build_contractor_bars` | 331 | `(productivity) -> list[dict]` | by_contractor → BarItem[] CPI desc sorted, baseline=90 |
| `_build_trade_bars` | 352 | `(productivity) -> list[dict]` | by_l6 → BarItem[] |
| `_compute_impact_p90` | 369 | `(raw_impacts) -> float` | P90 percentile (len≥10) 또는 max fallback |
| `_normalize_impact` | 378 | `(raw, p90) -> float` | raw → 0~100 cap |
| `_quadrant_label` | 385 | `(productivity, impact) -> str` | risk / caution / watch / safe |
| `_wp_id_of` | 398 | `(wa, l6_main, company) -> str` | kebab-case wp_id (예: `cub-철근콘크리트공사-남웅건설`) |
| `_build_wa_lookup` | 409 | `(items) -> dict[(l6_main,company), list[wa]]` | `_build_optimizer_view` fan-out 입력 |

### Phase 3 — Cold start 진단 (LLM advice 없는 WP)

| Func | Line | Signature | 의도 |
|---|---|---|---|
| `_pick_cause` | 423 | `(pct, impact, delay_days, trade) -> str` | 8 cause 분기 — productivity × impact × delay × trade |
| `_pick_recommendations` | 442 | `(pct, impact, delay_days, workers, trade) -> list[str]` | 5 rule 조합형 (인력 +1 / 후속 영향 / 인터페이스 / 장비·자재 / 정상페이스) |
| `_compose_diagnosis` | 460 | `(pp_master, pp_today, pct, unit, cause) -> str` | "이 작업은 보통 인당 X.XX 단위..." 한 단락 (≤140자) |
| `_compose_diagnosis_no_master` | 472 | `(pp_today, unit) -> str` | master 없음 단순 진단 |
| **`_build_deterministic_cold_start`** | 480 | `(q, master, chroma_cases, *, workers, risk_level, delay_days) -> dict` | advice 없는 WP 마다 deterministic 4 슬롯 (diagnosis / similar_cases / recommendations / details) — LLM 호출 0 |

### Phase 4 — ChromaDB lookup + Quadrant + WP summary

| Func | Line | Signature | 의도 |
|---|---|---|---|
| `_get_chroma_collection` | 597 | `() -> Collection` | ChromaClient 모듈 캐시 (`_chroma_singleton`) — 530일 backfill socket 누적 timeout 회피 |
| `_get_all_backfill_metas` | 611 | `() -> list[dict]` | backfill_v2 전체 metadata 1회 fetch + 모듈 캐시 (`_chroma_metas_cache`) |
| **`_fetch_chroma_cases_lookup`** | 627 | `async (items, today) -> dict[wp_id, list[dict]]` | 3단 fallback: (company, l6, l7_5) → (company, l6) → (l6, l7_5) → []. 메모리 bucket lookup |
| `_fetch_chroma_cases_lookup_legacy` | 670 | `async (items, today) -> dict` | 개별 wp 별 col.get — backfill 시 timeout. deprecated |
| **`_build_quadrant`** | 719 | `async (pg, site_id, today, productivity) -> list[dict]` | 4분면 산점도 — (wa, l6, company) per WP. raw_impact = SUM(plan_total_qty) × AVG(plan_mh), P90 normalize |
| **`_build_wp_summary`** | 762 | `async (pg, site_id, today, productivity, quadrant_jsonb) -> list[dict]` | WP 표 — quadrant + baseline + status (placeholder 4 필드는 v2 가 채움) |

### Phase 5 — S-curve (산식 A — **본 cycle 핵심 변경**)

| Func | Line | Signature | 의도 |
|---|---|---|---|
| `_merge_curves` | 792 | `(planned, actual, recovery=None) -> list[dict]` | date 단위 datapoint 합성 (actual delta → cumulative 변환) |
| `_extend_forecast` | 824 | `(merged, days_ahead=30) -> list[dict]` | 직전 7일 평균 rate × remaining_days. rate≤0 면 planned 일평균의 70% fallback. dedup |
| **`_build_s_curve`** | 880 | `async (pg, site_id, today) -> list[dict]` | **산식 A — WV × MH 가중 + activity 단위 매칭 + progress cap** (§6 상세) |

### Phase 6 — Optimizer view (LLM advice 매칭) + 4 시나리오

| Func | Line | Signature | 의도 |
|---|---|---|---|
| **`_build_optimizer_view`** | 1024 | `(advice_rows, forecast, mapped, wa_lookup=None) -> dict` | 4 섹션 진단 by_wp — `wa_lookup` fan-out (한 advice → 여러 wp_id 복사) |
| `_coerce_date` | 1137 | `(v) -> date \| None` | asyncpg date vs jsonb str 둘 다 허용 |
| `_expand_recovery_to_days` | 1154 | `(dist: dict) -> list[int]` | recovery_distribution → 분위수 산출 가능 list (not_recovered +30 cap) |
| `_percentile` | 1172 | `(days, q) -> int` | q ∈ [0,1]. len<4 면 단순 idx, 그 외 `statistics.quantiles(n=100, method="inclusive")` |
| `_match_forecast_by_company_l6` | 1184 | `(advice, forecast) -> dict \| None` | (company, l6_main) lookup |
| `_scenario` | 1197 | `(no_action_date, recovery_days, case_count) -> dict` | 단일 시나리오 dict (recovery 0 → no_action pass) |
| **`_build_scenarios`** | 1215 | `(advice_rows, forecast) -> dict` | site + by_wp 4 시나리오 (no_action / optimistic_p25 / base_p50 / pessimistic_p75) |

### Phase 7 — v2 통합 산식 (`_build_productivity_views_v2`)

| Func | Line | Signature | 의도 |
|---|---|---|---|
| `_compute_daily_quota` | 1275 | `(plan_total_qty, total_days) -> float` | 일일 quota = qty / days |
| `_simulate_today_qty` | 1282 | `(daily_qty, daily_workers, seed) -> dict` | productivity 분포 = 중심 85% + ±20% 일반 + 5%/5% outlier (60%/150%) |
| `_compute_productivity` | 1308 | `(perperson, master_perperson) -> float` | (인당 / 마스터 인당) × 100 |
| `_weighted_median` | 1315 | `(values, weights) -> float` | 가중 누적 50% 지점 |
| `_normalize_impact_share` | 1331 | `(impacts) -> list[float]` | share-of-total (일별 합 = 100%) — `_normalize_impact` 와 이름 충돌 주의 |
| `_make_display_label` | 1348 | `(productivity_pct, perperson, unit) -> str` | "98.9% (3.20 ton/인)" 라벨 |
| `_status_of` | 1362 | `(pct) -> str` | normal(≥90) / caution(≥70) / risk |
| `_quadrant_of` | 1371 | `(prod, impact) -> str` | risk / caution / watch / safe |
| `_group_perperson_unit` | 1381 | `(items) -> (avg, unit)` | wv-mean perperson + 단위 일관성 검증 (섞이면 None,None) |
| **`_build_productivity_views_v2`** | 1410 | `async (pg, site_id, today) -> dict` | Phase 1 신규 4단 산식 — daily_reports 9 jsonb 통합 산출 + cold_start fan-out + scenarios + s_curve |
| `_augment_history_if_sparse` | 1854 | `(items, min_count=5) -> list[dict]` | (company, l6) row < 5 면 동일 l6 다른 company 에서 보충 (augmented=True 메타) |

---

## 5. 9 jsonb View Schema (`daily_reports.*_jsonb`)

`pipeline/db.py:1050` `_VIEW_JSONB_COLS` 화이트리스트 (SQL injection 방어 — `upsert_daily_report_view_col` `pipeline/db.py:1062` 가 enforce):

```python
_VIEW_JSONB_COLS: tuple[str, ...] = (
    "kpi_jsonb", "contractor_bars_jsonb", "trade_bars_jsonb",
    "quadrant_jsonb", "wp_summary_jsonb", "s_curve_jsonb",
    "optimizer_view_jsonb", "productivity_jsonb", "scenarios_jsonb",
)
```

각 컬럼 schema:

### (1) `kpi_jsonb` (`_build_kpi`, view_builder.py:284)

```jsonc
{
  "productivity_today": 87.3,       // round(CPI)
  "spi": 92.1,
  "cpi": 87.3,
  "target_productivity": 100,
  "delay_days": 11,                 // MEDIAN(forecasts.delay_days), 2026-05-23
  "expected_completion": "2025-11-12"  // MEDIAN(expected_completion)
}
```

v2 는 추가로 `productivity_today_simple_mean`, `productivity_today_perperson`, `productivity_today_unit`, `productivity_today_display`, `recoverable_productivity`, `recovery_days`, `recovered_completion` 박음 (view_builder.py:1709~1727).

### (2) `contractor_bars_jsonb` (`_build_contractor_bars`, view_builder.py:331)

```jsonc
[
  {"label": "남웅건설", "value": 96.3, "baseline": 90, "status": "normal"},
  {"label": "세보엠이씨", "value": 78.1, "baseline": 90, "status": "risk"}
]
```
v2 는 `perperson`, `perperson_unit`, `display_label` 추가.

### (3) `trade_bars_jsonb` (`_build_trade_bars`) — `contractor_bars_jsonb` 와 동일 shape, label 이 l6_main.

### (4) `quadrant_jsonb` (`_build_quadrant`, view_builder.py:719 — v2 는 1642)

```jsonc
[
  {
    "wp_id": "cub-철근콘크리트공사-남웅건설",
    "wp_name": "CUB 철근콘크리트공사",
    "trade": "철근콘크리트공사",
    "productivity": 87.3,
    "impact": 64.1,                  // 0~100 P90 normalize (v1) / share (v2)
    "quadrant": "watch",             // risk / caution / watch / safe
    "size": 64                       // max(30, min(120, int(impact))) v1 / qty/10 v2
  }
]
```

### (5) `wp_summary_jsonb` (`_build_wp_summary` view_builder.py:762, v2 는 1665) — quadrant + status + baseline + (v1 placeholder, v2 채움) bp_name / progress_pct / start_date / end_date / perperson / display_label.

### (6) `s_curve_jsonb` (`_build_s_curve` view_builder.py:880)

```jsonc
[
  {"date": "2025-05-01", "planned": 12.3, "actual": 10.1},
  {"date": "2025-09-25", "planned": 64.2, "actual": 56.7},
  {"date": "2025-09-26", "forecast": 56.9},
  {"date": "2025-10-15", "forecast": 71.4, "recovery_days": 3}
]
```
4 곡선 unified — planned / actual / forecast / recovery 키가 같은 date 안에 합쳐짐.

### (7) `optimizer_view_jsonb` (`_build_optimizer_view` view_builder.py:1024) — 4 섹션 진단

```jsonc
{
  "by_wp": {
    "cub-철근콘크리트공사-남웅건설": {
      "diagnosis": "장비 대기로 인한 저하 (추정)...",
      "similar_cases": [
        {"date": "2025-09-22", "description": "맑음,장비대기 - 기초공사 : 거푸집 공사, 생산성 12.47 m3/인 (인원 8명)", "outcome": "1일 후 회복"}
      ],
      "recommendations": ["내일 오전 타워크레인 스케줄 확인 권장", ...],
      "details": [
        {"label": "위험 평가", "value": "고위험"},
        {"label": "진단 대상", "value": "남웅건설 · 철근콘크리트공사"},
        {"label": "유사 사례 수", "value": "5건"},
        {"label": "평균 회복 일수", "value": "1.4일"},
        {"label": "회복 분포", "value": "1일 후 정상 회복 3건 / 2일 후 정상 회복 1건 / 미회복 1건"},
        {"label": "일정 영향", "value": "11일 지연"}
      ]
    }
  },
  "default_wp_id": "cub-철근콘크리트공사-남웅건설"
}
```

v2 는 cold_start fallback (`_build_deterministic_cold_start`) 으로 advice 없는 quadrant wp_id 도 채움 → `by_wp` ⊇ quadrant wp_id (T17 fix `2c2ba75`).

### (8) `productivity_jsonb` (`_build_productivity_views_v2` 의 `productivity_dict`, view_builder.py:1728)

```jsonc
{
  "site":        {"wv_median": 87.3, "simple_mean": 84.1, "n_companies": 3, "n_l75": 47},
  "by_company":  {"남웅건설": {"wv_median": 96.3, "simple_mean": 92.1, "n_l75": 18, "sum_wv": 12340.5}, ...},
  "by_l6":       {"철근콘크리트공사": {"wv_median": 91.7, ...}, ...}
}
```

### (9) `scenarios_jsonb` (`_build_scenarios` view_builder.py:1215) — 4 시나리오

```jsonc
{
  "site": {
    "no_action":       {"expected_completion": "2025-11-12", "recovery_days": 0, "delta_days": 0, "case_count": 47},
    "optimistic_p25":  {"expected_completion": "2025-11-07", "recovery_days": 5, "delta_days": -5, "case_count": 47},
    "base_p50":        {"expected_completion": "2025-11-10", "recovery_days": 2, "delta_days": -2, "case_count": 47},
    "pessimistic_p75": {"expected_completion": "2025-11-11", "recovery_days": 1, "delta_days": -1, "case_count": 47}
  },
  "by_wp": { /* same shape per wp_id */ }
}
```

**주의** (view_builder.py:1239) — 이름과 분위수는 라벨↔값 swap 의도: `optimistic_p25` 가 P75 (큰 recovery_days) 를, `pessimistic_p75` 가 P25 (작은 recovery_days) 를 사용 → "낙관 시나리오 = 만회 큰 값" 의미 정확화.

---

## 6. 산식 A 상세 — `_build_s_curve` (commit `c0a0641`)

본 cycle 의 사용자 핵심 결정. `view_builder.py:880~1021`.

**의도**: 이전 단순 `SUM(today_qty) / SUM(plan_total_qty)` 는 단위 일관성 부재 (m³+ton+개 혼합 합산 → 무의미). 산식 A 는 단위 무관 가중 진척률.

```
분모 site_total_weight = SUM(plan_wv × plan_mh_rev2)
planned[t] = SUM(plan_wv × plan_mh_rev2 × LEAST(1, (t - plan_start + 1) / (plan_finish - plan_start + 1)))
                                                                          (per activity)
actual[t]  = SUM(weight × MIN(1, cum_qty(t) / plan_qty))
              where weight = SUM(plan_wv × plan_mh_rev2) per (wa, l6_main)
                    cum_qty(t) = full_grid cross join 으로 매일 직전 누적값 보존
```

### 6.1 분모 (view_builder.py:897~905)

```sql
SELECT SUM(plan_wv * plan_mh_rev2)::float AS total
FROM activity_master
WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL
```

### 6.2 Planned 곡선 (view_builder.py:914~936)

```sql
SELECT gs.date::date AS date,
       SUM(am.plan_wv * am.plan_mh_rev2 * LEAST(1.0, GREATEST(0.0,
           (gs.date::date - am.plan_start + 1)::float
           / NULLIF((am.plan_finish - am.plan_start + 1)::float, 0)
       )))::float AS cum_plan_qty
FROM activity_master am
CROSS JOIN LATERAL (
    SELECT d AS date
    FROM generate_series(
        (SELECT MIN(plan_start) FROM activity_master WHERE site_id = $1),
        $2::date, '1 day'::interval
    ) AS d
) gs
WHERE am.site_id = $1 AND am.plan_wv IS NOT NULL AND am.plan_mh_rev2 IS NOT NULL
GROUP BY gs.date ORDER BY gs.date
```

activity 단위 linear progress × `plan_wv × plan_mh_rev2` 가중. site 전체 SUM.

### 6.3 Actual 곡선 (view_builder.py:942~981) — **`full_grid` cross join 으로 단조 누적 보장**

```sql
WITH am_agg AS (
    SELECT wa, l6_main,
           SUM(plan_total_qty)::float AS plan_qty,
           SUM(plan_wv * plan_mh_rev2)::float AS weight
    FROM activity_master
    WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL
    GROUP BY wa, l6_main
),
day_qty AS (
    SELECT report_date, wa, l6_main, SUM(today_qty)::float AS day_qty
    FROM mapped_history
    WHERE site_id = $1 AND report_date <= $2
    GROUP BY report_date, wa, l6_main
),
dates AS (SELECT DISTINCT report_date FROM day_qty),
full_grid AS (
    SELECT d.report_date, m.wa, m.l6_main, m.plan_qty, m.weight
    FROM dates d CROSS JOIN am_agg m       -- 모든 (date × wa × l6) 조합 보장
),
cum_actual AS (
    SELECT g.report_date, g.wa, g.l6_main, g.plan_qty, g.weight,
           SUM(COALESCE(dq.day_qty, 0)) OVER (
               PARTITION BY g.wa, g.l6_main ORDER BY g.report_date
           )::float AS cum_qty
    FROM full_grid g
    LEFT JOIN day_qty dq USING (report_date, wa, l6_main)
)
SELECT report_date,
       SUM(weight * LEAST(1.0, cum_qty / NULLIF(plan_qty, 0)))::float AS cum_weighted
FROM cum_actual
GROUP BY report_date ORDER BY report_date
```

핵심:
- **(wa, l6_main) 매칭**, company 매칭은 일부러 제외 — 시연 mock 정합성 (wa,l6) 단위 매칭률 100%.
- **`full_grid` cross join** — 그날 작업 안 한 (wa, l6) 도 직전 cum 유지. 미보정 시 그 일자 가중 sum 에서 빠져 actual % 가 dip (V 자 모양 결함).
- **`LEAST(1.0, cum_qty / plan_qty)`** — activity 단위 progress cap. 마스터 초과 작업 시 100% 로 clamp.

### 6.4 환산 + forecast 연장 (view_builder.py:1012~1021)

```python
forecast_days = max(30, (plan_end - today).days + 30) if plan_end else 30
extended = _extend_forecast(merged, days_ahead=forecast_days)
for p in extended:
    for k in ("planned", "actual", "forecast"):
        if p.get(k) is not None:
            p[k] = round(min(100.0, p[k] / site_total_weight * 100), 2)
```

`_extend_forecast` (view_builder.py:824) — 직전 7일 평균 rate × remaining_days. outlier (mock 9-25 today_qty=6608) 흔들림 방지.

---

## 7. `delay_days` AVG → MEDIAN fix (commit `e9b66d4`)

`view_builder.py:295~309` 와 `view_builder.py:1693~1706` 두 곳 동일 SQL.

```sql
-- 2026-05-23: AVG -> MEDIAN. AVG 는 outlier 1건에 끌려가 site KPI 가
-- 비현실 (예: 동신패널 외장판넬 atomic 1행 dummy anomaly = 167,871일
-- -> AVG=2,398). MEDIAN 은 "일반적 그룹 delay" 의미.
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days)::float AS delay,
       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY expected_completion) AS expected_completion
FROM forecasts f JOIN pipeline_runs pr USING (run_id)
WHERE pr.site_id = $1 AND pr.report_date = $2
  AND delay_days IS NOT NULL
```

차이:
- AVG 산식 outlier 영향: `AVG(167871, 11, 8, 14, ...)` = 약 2,398 일. KPI "지연 2,398일" 화면 표시.
- MEDIAN 효과: 정상 군집 (≈ 11일) 중심값으로 수렴. outlier 1건은 max 로만 영향.
- `PERCENTILE_CONT` (연속, delay_days) + `PERCENTILE_DISC` (이산, expected_completion 은 date 라 정수 아님) 구분 사용.

---

## 8. Scenarios 4 시나리오 — `_build_scenarios` (view_builder.py:1215)

```python
site_days: list[int] = []
for advice in advice_rows:
    site_days.extend(_expand_recovery_to_days(advice.get("recovery_distribution") or {}))

site_no_action = max([_coerce_date(f.get("expected_completion")) for f in forecast]) if forecast else None

site_scenarios = {
    "no_action":       {"expected_completion": ..., "recovery_days": 0,  "delta_days": 0,   "case_count": len(site_days)},
    "optimistic_p25":  _scenario(site_no_action, _percentile(site_days, 0.75), len(site_days)),
    "base_p50":        _scenario(site_no_action, _percentile(site_days, 0.50), len(site_days)),
    "pessimistic_p75": _scenario(site_no_action, _percentile(site_days, 0.25), len(site_days)),
}
```

`_expand_recovery_to_days` (view_builder.py:1154) — `{"d+1": 3, "d+2": 1, "not_recovered": 1}` → `[1, 1, 1, 2, 30]` (not_recovered = +30일 cap).

`_scenario` (view_builder.py:1197):
```python
def _scenario(no_action_date, recovery_days: int, case_count: int) -> dict:
    if no_action_date is None or recovery_days <= 0:
        return {"expected_completion": no_action_date.isoformat() if no_action_date else None,
                "recovery_days": recovery_days, "delta_days": 0, "case_count": case_count}
    new_date = no_action_date - timedelta(days=recovery_days)
    return {"expected_completion": new_date.isoformat(),
            "recovery_days": recovery_days, "delta_days": -recovery_days, "case_count": case_count}
```

**라벨 ↔ 분위수 swap 의도 (view_builder.py:1237~1241)**:
- `optimistic_p25` ← `_percentile(site_days, 0.75)` (P75 = 큰 recovery_days = 회복 길게)
- `pessimistic_p75` ← `_percentile(site_days, 0.25)` (P25 = 작은 recovery_days = 회복 짧게)
- 의미: "낙관 시나리오 = 만회 큰 값", "비관 = 만회 작은 값" — 화면 표시값이 실제 최대 만회를 반영.

by_wp 도 동일 산식, no_action_date = `_coerce_date(f.get("expected_completion"))` (forecast row 매칭).

---

## 9. site_summary.py 141 LOC 전수 — 신규 (`21c10f7`)

```
                 ┌──────────────────────────────────────┐
                 │   build_site_summary_payload (line 46)│
                 │                                        │
   kpi          │   - s_curve report_date 시점 planned/actual                  │
   scenarios   ──▶│   - top 3 wp_summary by impact desc                         │
   wp_summary   │   - by_wp.diagnosis (cold_start 제외) + recommendations[0]   │
   optimizer_view│   - no_action_ec / base_p50_ec / plan_ec                    │
   s_curve     │                                        │
                 └──────────────────┬───────────────────┘
                                    ▼
                 ┌──────────────────────────────────────┐
                 │   generate_site_summary (line 117)    │
                 │   Azure OpenAI gpt-5.1, JSON mode      │
                 │   SYSTEM_PROMPT (line 25, 19 line)    │
                 └──────────────────┬───────────────────┘
                                    ▼
                          daily_reports.site_summary_text (UPDATE)
```

### 9.1 `build_site_summary_payload` (site_summary.py:46)

LLM 입력 payload 를 **결정론적** dict 로 build (LLM 출력 변동성 차단):

```python
{
    "report_date": "2025-09-25",
    "site_id": "DEMO_SITE",
    "progress_pct": {"planned": 64.2, "actual": 56.7},  // s_curve report_date 시점
    "gap_pct": 7.5,
    "delay_days": 11,
    "ai_recovery_days": 2,                              // scenarios.site.base_p50.recovery_days
    "expected_completion": {
        "if_no_action": "2025-11-12", "ai_scenario": "2025-11-10", "plan": "2025-10-30"
    },
    "top_risk_wps": [
        {"wp_name": "CUB 철근콘크리트공사", "trade": "철근콘크리트공사",
         "diagnosis": "장비 대기...", "top_recommendation": "타워크레인 스케줄 확인 권장"},
        ...
    ]
}
```

`top_risk_wps` 산출 (site_summary.py:71~99):
- `wp_summary` 에서 `impact > 0` filter → impact desc top 3.
- 각각 `optimizer_view.by_wp[wp_id].diagnosis` (cold_start 면 None 처리) + `recommendations[0]` 추출.

### 9.2 SYSTEM_PROMPT (site_summary.py:25)

```
당신은 건설 현장의 진척 상황을 경영진에게 보고하는 분석가입니다.

입력 JSON 데이터를 받아 현재 진척 상황과 AI 권고 적용 시 만회 가능성을
1~2 단락 (총 200~300자) 의 한국어 경영진 문체로 자연스럽게 정리하세요.

출력 형식 (반드시 JSON):
{"summary": "..."}

작성 원칙:
- 숫자는 입력값 그대로 인용 (소수점 1자리 이내).
- 1단락: 오늘 진척 상황 — "기준일 시점 진척률 X% 로 계획 (Y%) 대비 Z%p 뒤처짐.
  이대로 가면 D+N 일 지연 완공 예상." 형식.
- 2단락: AI 권고 적용 시 효과 — "위험 공종 A, B, C 의 [핵심 권고 액션] 시 N일 만에
  계획 따라잡고 동일 완공일 유지 가능." 형식.
- 위험 공종은 입력 top_risk_wps 에서 1~3개만 자연스럽게 언급.
- 통계 용어 (P25/P50/P75, MH 가중, EVM 등) 사용 금지. 경영진 자연어만.
- 추측/과장/입력에 없는 사실 추가 금지.
- 한자 사용 금지 — 한글 또는 영어 고유명사만.
```

### 9.3 `generate_site_summary` (site_summary.py:117)

```python
def generate_site_summary(payload, *, azure=None, model=None) -> str:
    if azure is None:
        azure = AzureOpenAI(api_key=..., api_version=..., azure_endpoint=...)
    model = model or os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=model, messages=messages, response_format={"type": "json_object"},
    )
    parsed = json.loads(resp.choices[0].message.content)
    return str(parsed.get("summary", "")).strip()
```

**fail-fast** — exception 그대로 raise. 호출자가 try/except.

### 9.4 호출 지점

LangGraph 노드 본체 (`agent.py optimize()`) 는 site_summary 호출 **안 함**. 별도 호출:

- `scripts/backfill_daily_report_views_v2.py:141~172` — `--with-summary` flag 시:
  ```python
  payload = build_site_summary_payload(report_date=..., site_id=..., kpi=..., scenarios=..., wp_summary=..., optimizer_view=..., s_curve=...)
  summary = await asyncio.to_thread(generate_site_summary, payload)
  await raw.execute("UPDATE daily_reports SET site_summary_text = $1 WHERE site_id = $2 AND report_date = $3::date AND is_mock = false", summary, site, d)
  ```

production 그래프 path 에 아직 통합 안 됨 — backfill 전용. **이슈로 표기.**

---

## 10. prompt.py / retrieve.py

### 10.1 prompt.py (316 LOC)

3 부분:

1. **SYSTEM_PROMPT** (prompt.py:21~55) — 한글+영어, 명령형 회피 (선택지 제시 톤). "권장 / 권고 / 검토 권장". cold_start (degradation_cases 빈 array) 분기 명시:
   ```
   degradation_cases 가 빈 array 인 경우 (신규 작업 — 과거 유사 저하 사례 없음):
   today 의 assessment / today_productivity / today_conditions / main_unit / company / l6_main
   만으로 진단. "과거 유사 사례 없음" 사실을 진단에 명시하고, 일반적 baseline 관리
   권고 3~4건 (모니터링·조기 신호 감지·기록 누적·후행 공정 영향 점검 류) 을 작성.
   추측성 회복 패턴 언급은 금지.
   ```
   recovery_distribution 은 코드단 산출 — LLM 참고만.
2. **FEW_SHOT_MESSAGES** (prompt.py:62~278) — 3 회복 패턴 sample (user/assistant 6 messages):
   - 장비대기 D+1 우세 회복 (남웅건설 철근콘크리트)
   - 자재미입고 D+2 우세 회복 (대한건설 철근콘크리트)
   - 미회복 우세 (장기 지연 — 돌관 검토)
3. **`build_llm_user_input`** (prompt.py:287~316) — forecast_row + degradation_cases (recovery merge 포함) → LLM user message JSON.

### 10.2 retrieve.py (206 LOC, commits `d79a438` + `82bb8af`)

```python
INCIDENT_KEYWORDS: tuple[str, ...] = (
    "장비대기", "자재미입고", "돌관", "우천", "야간연장",   # 기존 5
    "인력부족", "재작업", "병행작업", "사양변경",          # 신규 4 (d79a438)
)
_DEGRADATION_INCIDENTS = INCIDENT_KEYWORDS              # backward compat
_ALL_INCIDENTS = INCIDENT_KEYWORDS                       # 통일 (이전 3 + 5 → 9)
_DEGRADATION_RATIO = 0.85
_RECOVERY_RATIO = 0.95
```

**본 cycle 변경 핵심** (`82bb8af`):

1. **degradation 정의 완화 OR** (retrieve.py:136~140):
   - 이전: `conditions ∋ incident AND prod < baseline×0.85` (AND) → backfill_v2 의 `conditions='[]'` 빈 string row 가 모두 차단됨.
   - 변경: `conditions ∋ incident OR prod < baseline×0.85` (OR) → prod 저하만으로도 충분.
2. **worker_source 화이트리스트 제거** (retrieve.py:125~127):
   - 이전: `('synthetic_v2','mh_prorated')` 만 허용 → backfill_v2/dummy_seed 차단 → 합성 3사 외 75사가 case=0 cold_start.
   - 변경: 모든 source 인정.

세 함수:

- `_group_baseline` (retrieve.py:58~88) — 같은 (l6, unit[, company][, l7_5]) 의 incident 없는 row productivity 평균. cold_start 신호.
- `fetch_degradation_cases` (retrieve.py:91~151) — Step 1: 저하 case top-N recency. company is None → 동종 공사 cross-company.
- `fetch_recovery_trajectory` (retrieve.py:154~206) — Step 2: case_date+1 ~ +7 의 group productivity. `recovery_days = first ✓` (or None).

`l7_5_activity` arg 추가 (phase 2 `f74cdd3`) — 동일 activity 만 매칭하여 case 정합도 상승.

---

## 11. synthetic_v2.py 363 LOC — 회복 룰 7건 state machine

`generate_synthetic_v2_group(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days=90, seed=42, reference_date=None)` (synthetic_v2.py:35).

`_BP_TOTAL` (synthetic_v2.py:28) — 9/25 작업일보 BP사 총 인원:
```python
{"남웅건설": 88, "세보엠이씨": 1387, "창원기전": 372}
```

매일 결정 흐름 (룰 enumerate spec §4.1):
- 룰 1: 장비대기 1일차 — `productivity × (1 - random[0.20, 0.35])`
- 룰 2: 장비대기 1일차 익일 — 80% 정상 / 20% 2일차 지속 (synthetic_v2.py:75~82)
- 룰 3: 장비대기 2일차 익일 — 정상 100%, 만회 30% × 1.10 (synthetic_v2.py:83~87)
- 룰 4: 우천 연속 2일 후 3일차 — × 1.10 만회 (rain_streak_compensation)
- 룰 5: 자재미입고 익일 — 50% 정상 / 50% 지속 (synthetic_v2.py:88~90)
- 룰 6: 야간연장 익일 — 새 random + fatigue × 0.90 (synthetic_v2.py:91~97)
- 룰 7: 돌관 당일 — productivity × 0.85 (-10~20%) + assigned_workers × 1.3 spike (synthetic_v2.py:120, 133)

각 day row schema (synthetic_v2.py:148~159):
```python
{"date": ISO, "company": ..., "l6_main": ..., "unit": ...,
 "today_qty": float, "assigned_workers": float,
 "conditions": "맑음,장비대기",  # comma-joined str (결정 #19)
 "work_content": str,             # 단순 활동명 (결정 #22)
 "worker_source": "synthetic_v2"}
```

CLI (synthetic_v2.py:169~363):
1. PG `activity_master` → 27 그룹 main_unit + activity_pool + total_qty + total_mh.
2. baseline_workers = `bp_total × (l6_mh / sum_mh_per_co)` (proration).
3. baseline_qty_per_day = `total_qty / days`.
4. 27 그룹 × 90일 = ~2,430 row generate.
5. Chroma `daily_activities` 에서 `worker_source="synthetic"` DROP (mh_prorated + synthetic_v2 보존).
6. Azure embedding `text-embedding-3-small` batch=16, upsert.

### seed_dummy_year.py 와의 관계

seed_dummy_year (이 deep-dive 범위 밖, `scripts/seed_dummy_year.py`) 가 안에서 같은 산식 사용:
- F3 piecewise 분포 (`e166a00`)
- prod target 90% 역산 (`8a6c136`)
- l5_disc trade (건축/토목 자동 판정)
- l7.5 activity 정합
- today_conditions metadata 전파 (`b24589a`)
- chroma metadata + degradation_cases (`b24589a`)

synthetic_v2 는 9 그룹 × 90 일 PoC backfill, seed_dummy_year 는 530 일 모든 site 전체 — 산식 공유, 적용 범위 다름.

---

## 12. synthetic_daily_report.py — demo CLI

본 cycle 변경 없음. 핵심 (Parser/Mapper skip, Activity 직접 주입):

- `generate_fake_daily_report` (synthetic_daily_report.py:50~110) — scenarios + baseline → Activity list (mapper output 형식).
- `_parse_scenario` (synthetic_daily_report.py:118) — `"company|l6_main|n|incident|prod_ratio|workers_ratio|unit"` 파싱.
- `_check_synthetic_v2_loaded` (synthetic_daily_report.py:140) — `worker_source=synthetic_v2` row 0 이면 abort.
- `_initial_state` (synthetic_daily_report.py:242) — `build_demo_graph` 진입 state.
- `_main_cli` (synthetic_daily_report.py:355~493) — 9 step CLI:
  1. synthetic v2 적재 확인
  2. sites + pipeline_runs INSERT
  3. baseline inputs 로드
  4. fake activities 생성
  5. `build_demo_graph(cfg).ainvoke(...)`
  6. `__interrupt__` payload 출력
  7. `--auto-select-all` flag 자동 resume / interactive input
  8. `Command(resume=selection)` 재개
  9. advice 출력

---

## 13. LLM 호출 표

| 호출 지점 | 모델 | 모드 | 호출 회수 | 동시성 | 변경 |
|---|---|---|---|---|---|
| `_call_azure_llm` (agent.py:101) | gpt-5.1-chat-ai-board-test | JSON, no retry | 선택된 forecast row 마다 1회 | **asyncio.gather + to_thread (`690c305`, 4×)** | 본 cycle 핵심 perf |
| cold_start LLM (`82bb8af`) | 동일 | 동일 | cases<3 도 LLM (이전 placeholder) | gather 안 | 4섹션 풍부화 |
| `generate_site_summary` (site_summary.py:117) | 동일 | JSON | site 1회 | (backfill `asyncio.to_thread`) | 신규 (`21c10f7`) |

cold_start 분기 (agent.py:171~174 코멘트): "UI 4분면 점 클릭 시 풍부한 진단 보장 (사용자 검증 9/22 광건 fab cold_start placeholder 화면)" — 이전 placeholder 화면 보고 user push back → LLM 호출로 전환.

semaphore: `pipeline.agents._concurrency.get_llm_semaphore()` — Azure rate limit 가드 (LLM 호출 부분만, PG write 는 밖).

---

## 14. View Orchestration — 9 jsonb 산출

```
optimize()  agent.py:121
   │
   ├─ asyncio.gather(*_process_one(r, cases))     ──▶  advice_rows
   │     └─ _call_azure_llm_async (gpt-5.1, JSON)
   │
   ├─ pg.insert_optimizer_advice(row) × N         ──▶  PG optimizer_advice
   │
   └─ if site_id:                                  view_builder 9 jsonb 산출
        │
        ├─ _build_productivity_views (EVM 4 segment)
        │    ├─ _evm_for_group   (today  / site)
        │    ├─ _evm_by_group    (by_contractor)
        │    ├─ _evm_by_group    (by_l6)
        │    └─ _evm_by_wa_l6_company (by_wp)
        │
        ├─ _build_quadrant (raw_impact + P90 normalize)
        ├─ wa_lookup = SELECT FROM mapper_activities GROUP BY (l6_main,company)
        │
        ├─ view_jsonbs = {
        │    productivity_jsonb,     ← productivity
        │    kpi_jsonb,              ← _build_kpi (delay MEDIAN)
        │    contractor_bars_jsonb,  ← _build_contractor_bars(productivity)
        │    trade_bars_jsonb,       ← _build_trade_bars(productivity)
        │    quadrant_jsonb,         ← quadrant
        │    wp_summary_jsonb,       ← _build_wp_summary(productivity, quadrant)
        │    s_curve_jsonb,          ← _build_s_curve (산식 A)
        │    optimizer_view_jsonb,   ← _build_optimizer_view(advice, forecast, mapped, wa_lookup)
        │    scenarios_jsonb,        ← _build_scenarios(advice, forecast)
        │  }
        │
        └─ for col, val in view_jsonbs.items():
             try:
                 await pg.upsert_daily_report_view_col(run_id, site_id, today, col, val)
             except: warn (partial write 유지)
```

`upsert_daily_report_view_col` (db.py:1062~1106):
- 9 컬럼 화이트리스트 검증 (`if col not in self._VIEW_JSONB_COLS: raise`).
- **UPDATE-first** — partial unique index `(run_id, site_id, report_date) WHERE site_id IS NOT NULL` 가 ON CONFLICT 와 안정 매칭 안 됨. row 이미 존재 (reporter INSERT) 보장 → UPDATE 만.
- fallback: row 없으면 INSERT (신규).

---

## 15. 이슈 표

| # | 이슈 | 위치 | 영향 | 우선순위 |
|---|---|---|---|---|
| 1 | **working tree 미커밋 1 줄** — `AND ma.trade IN ('건축', '토목')` 제거 (다른 세션) | view_builder.py:1447 | v2 산출 대상 확장 (설비/전기 등 포함). 9 jsonb 산식 변동 가능 | 즉시 — 다른 세션 작업과 충돌 가능 |
| 2 | **`Optional` 미 import** | view_builder.py:399/481/594/1028/1093, agent.py:128/129 | `from __future__ import annotations` 덕에 런타임 OK. `typing.get_type_hints()` 사용 시 NameError | 낮음 — 잠재 latent |
| 3 | **site_summary 가 production 그래프 미연결** | site_summary.py + scripts/backfill_daily_report_views_v2.py:141 만 호출 | live optimize() 실행 시 `daily_reports.site_summary_text` 비어있음. FE narrative 미표시 | 중간 — backfill 의존 |
| 4 | **`_normalize_impact` vs `_normalize_impact_share` 이름 충돌** | view_builder.py:378 vs 1331 | shadowing 위험. v2 가 share 산식이지만 v1 호출 라인 743 은 P90 normalize 의도. 함수 시그니처 (1 arg vs 2 arg) 로 분리됨 | 코멘트 (view_builder.py:1337) 박혀 있음 — 모니터 |
| 5 | **v1 `_build_productivity_views` ↔ v2 `_build_productivity_views_v2` 병행** | view_builder.py:48 vs 1410 | `agent.py:187` 은 v1 호출, `backfill_daily_report_views_v2.py:125` 는 v2 호출. 산식·schema 다름 → 같은 컬럼 다른 값 가능 | 중간 — 통합 또는 deprecation 결정 필요 |
| 6 | **RAG fixture vs synthetic_v2 baseline ±10% drift** | retrieve.py 매칭 + synthetic_v2 generation seed 변경 | recovery_distribution 수치 변동 → scenarios percentile 변동 → KPI recovery_days 변동 | 모니터 |
| 7 | **v1 cold_start (`_build_deterministic_cold_start`) 의 `productivity` 키** | view_builder.py:489 `q.get("productivity")` | quadrant item 의 productivity (CPI) 와 v2 productivity_pct (인당/마스터) scale 다름. v2 는 cold_start 에서 q["productivity"] 가 0~150 (v2 산식) | 모니터 — v1/v2 혼용 시 |
| 8 | **`_evm_by_wa_l6_company` 의 LEFT JOIN am** | view_builder.py:254~257 | mapper anchor — wa 가 plan side 에 없으면 plan 0. EVM CPI NaN 가능 | 표시 fallback ("—") 처리 |
| 9 | **`_get_all_backfill_metas` 캐시 무효화 없음** | view_builder.py:611 | 모듈 캐시 (`_chroma_metas_cache`) 가 process lifetime. backfill 도중 새 row 적재해도 미반영 | 낮음 — 단일 실행 가정 |
| 10 | **`build_demo_graph` 와 production `build_graph` 의 mapped state 차이** | synthetic_daily_report.py:411 mapped 직접 주입 vs production Mapper 노드 산출 | mapped 형식 drift 시 view_builder 산식 (특히 `_build_optimizer_view` wa fan-out) 깨질 수 있음 | 컨트랙트 테스트 권장 |

---

## 16. Appendix — 본 cycle commit timeline (optimizer 관련, baseline → HEAD)

```
ef7c6cd  ← baseline
  ↓
  ... (mapper/parser refactor 중간 생략)
  ↓
38127ff  feat: _build_productivity_views_v2 통합 산식 (Task 9)
adac813  feat: _augment_history_if_sparse (C7, Task 10)
f46e47e  feat(optimizer): cold_start 라벨 + augmentation weight (C9, Task 11)
556d4da  feat(backfill): 530일 view_builder_v2 + idempotent seed (Task 13/14)
... (phase2 C1~C9 일련 작업)
a8081b2  feat: view_builder wp_id 통일 + quadrant 키 4개 + SELECT wa/today_qty (C2)
3271378  feat: view_builder return 9 key stub (C3)
2d98a08  feat: _build_wa_lookup (C4)
c67f341  feat: _build_deterministic_cold_start + 8 cause + 5 rule (C5)
3029653  feat: _fetch_chroma_cases_lookup 3단 fallback (C6)
5d69a2f  feat: _build_optimizer_view 통합 + cold_start 채움 + jsonb inflate (C7)
450c9a7  feat: scenarios + s_curve 기존 함수 호출 + integration test (C8)
f74cdd3  feat: retrieve.py 3 함수 l7_5_activity arg (C9)
186042c  feat: D2 컨펌 fix — similar_cases schema + actual_trade + today_qty>0
98d844d  feat: chroma_cases_lookup 에 worker_source='backfill_v2' filter
bcbdae0  feat: similar_cases description 단순화 (perperson 만)
739b2cd  feat: _pick_recommendations R5 단순화 (pct >= 90 → 정상 페이스)
8fe28b2  fix: WBS 트리 am_combos l5_disc 필터 + chroma sort by date
d8ad216  fix: chroma_cases_lookup col.get limit 50 (httpx timeout 회피)
c9c64b8  fix: review 트리 마스터 전체 + WP 중복 group by
72dd7f2  fix: ChromaClient module-level singleton (530일 socket 누적 timeout)
9176b8d  fix: 사용자 4 fix — 라벨 + perperson normalize + review today_qty>0
4b67340  fix: dashboard 자릿수 + 유사사례 0 exclude + 공기단축 라벨 통일
ccefd30  fix: WP 목록 impact desc 정렬
2074fd6  fix: UI ↔ BE 숫자 매핑 정합화 7건
10b4176  feat(forecast): 공기 단축 시나리오 catch-up 시각화 + LLM 권고 narrative
c0a0641  ★★ feat(view-builder): 공정률 산식 재설계 — WV × MH 가중 + activity 매칭
21c10f7  ★★ feat(site-summary): Optimizer LLM 산출 site 수준 narrative + FE 룰베이스 교체
82bb8af  feat(report): 4섹션 풍부화 — retrieve 완화 + delay qty 산식 + cold_start LLM
ba505da  refactor: remove _compose_cold_start_row dead code + dead test
811a408  test(t1.5): review fix-up
690c305  ★ perf(optimizer): optimize() forecast 루프 asyncio.gather + to_thread (4×)
2c2ba75  fix: T17 quadrant ↔ by_wp wp_id 매칭 보강
e9b66d4  ★ fix(view_builder): site KPI delay_days AVG -> MEDIAN (outlier robust)
d79a438  feat(retrieve): incident keyword 9종 보강
ffcef7b  feat: backfill_optimizer_advice_llm.py 일반화
  ↓
1ba783f  ← HEAD (Merge origin/main into A_Track)
```

본 cycle 7 핵심: `c0a0641` (산식 A) · `21c10f7` (site_summary) · `82bb8af` (4섹션 풍부화) · `690c305` (4× perf) · `e9b66d4` (MEDIAN fix) · `2c2ba75` (T17 quadrant matching) · `d79a438` (9 keyword retrieve).
