# 시뮬 4 — 신규건설 토목 정상 1.0 (cold_start path)

- **date**: 2026-05-17
- **run_id**: `b6924645-2004-4fff-a902-cc92052f1a2d`
- **scenario**: `신규건설|토목공사|2|정상|1.0|1.0|m3`
- **의도**: activity_master 미등록 그룹 → baseline 0 → today_qty 0 → assessment=None (cold_start path) → risky 0건 → Optimizer 미진입 → Reporter fallback

## 1. 호출

```bash
$ PYTHONPATH=. pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "신규건설|토목공사|2|정상|1.0|1.0|m3" \
    --auto-select-all
```

## 2. CLI 출력

```
[OK] generate_fake_daily_report: 2 Activity rows (scenarios=1)
[OK] run_id=b6924645-2004-4fff-a902-cc92052f1a2d site_id=DEMO_SITE date=2025-09-27
[INFO] __interrupt__ 미발생 — risky 0건 (Forecaster 가 모든 그룹 risk_level=정상). Optimizer 미진입.
  forecast: 신규건설|토목공사 assessment=None risk=None reasoning=데이터 부족 — 오늘 물량 모든 unit 0 (인원만 투입). 판단 보류.
```

## 3. PG forecasts row

```
company   | l6_main   | assessment | risk_level | today_prod | workers | rag_n_similar | conditions | reasoning
----------+-----------+------------+------------+------------+---------+---------------+------------+----------------------------------------------------
신규건설  | 토목공사  | (null)     | (null)     | 0.00       | 0       | 0             | 맑음       | 데이터 부족 — 오늘 물량 모든 unit 0 (인원만 투입). 판단 보류.
```

**가공 흐름:**
- `_load_baseline_inputs` (synthetic_daily_report.py:155): activity_master WHERE company='신규건설' AND l6_main='토목공사' → 0 row → baseline_workers={}, baseline_qty={}.
- `generate_fake_daily_report`: baseline_q=0.0 → today_qty = 0.0 × 1.0 / 2 = 0.0 (모든 row).
- assigned_workers = base_workers (0) × 1.0 = 0.0.
- Forecaster 의 `aggregate_today_by_unit`: 모든 today_qty=0 → 빈 dict → main_unit=None → assessment=None.

## 4. PG optimizer_advice — 0 row

risky 0건 → hil_2_node 의 interrupt 미발생 → hil_2_selection=[] → conditional_edge → **reporter 직행** (이전 cycle = END 직행, 본 cycle = reporter 분기 추가).

→ Optimizer 미진입, optimizer_advice 적재 0 row.

## 5. PG daily_reports row (Reporter 진입)

- md_len = **586 chars** (시뮬 1~3 중 가장 짧음)
- summary = {risk_counts: 이상0/정상0/주의0, advice_count: 0, total_workers: 0.0, total_qty_by_trade: {토목공사: 0.0}}

mapped 가 빈 list 가 아니라 2 row 가 있어서 (assigned_workers=0, today_qty=0 이라도) Reporter LLM 호출 진행. SYSTEM_PROMPT 의 "데이터 부족 — 판단 보류" 룰 적용 → 짧은 보고서 산출.

## 6. 핵심 fact

- **cold_start path 정확히 작동** — 모든 산식이 0 으로 propagation + assessment=None 명시.
- **conditional_edge 신 분기 검증** — hil_2_selection=[] → reporter 직행. 본 cycle Task 3 의 의도적 drift (Reporter 위치) 정합.
- **Reporter mapped empty fallback X** — mapped=2 row 라 LLM 호출. 단 LLM 이 "데이터 부족" 인지하고 짧은 보고서 산출.
- **운영 의미**: 신규 BP사/공종 진입 시 activity_master 등록 + synthetic_v2 적재 cycle 필수 → drift backlog #5 (Collector + main.py) 통합 cycle 에서 master 등록 자동화 권고.

[[v2-scenario-1-156657ed]] [[v2-scenario-2]] [[v2-scenario-3]]
