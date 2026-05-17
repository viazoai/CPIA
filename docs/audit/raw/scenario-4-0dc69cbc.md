# Scenario 4 raw — cold_start (신규 회사 + 신규 l6_main)

**Spec 인용:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` §7.4
**Run ID:** `0dc69cbc-ed64-4a27-9f9b-adec01a24093`
**날짜:** 2025-09-30 (CLI) → stdout date=2025-09-30 (시뮬 3 의 off-by-one drift 가 일관 X)
**Fixture:** 신규건설 | 토목공사 | m3 | 2 act | 정상 | productivity_ratio=1.0 | workers_ratio=1.0

---

## 1. 단계별 raw

### 1.1 호출

```
$ pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-30 --scenario "신규건설|토목공사|2|정상|1.0|1.0|m3" --auto-select-all
```

stdout 발췌:
```
[OK] generate_fake_daily_report: 2 Activity rows (scenarios=1)
[OK] run_id=0dc69cbc-ed64-4a27-9f9b-adec01a24093 site_id=DEMO_SITE date=2025-09-30
[INFO] __interrupt__ 미발생 — risky 0건 (Forecaster 가 모든 그룹 risk_level=정상). Optimizer 미진입.
  forecast: 신규건설|토목공사 assessment=None risk=None reasoning=데이터 부족 — 오늘 물량 모든 unit 0 (인원만 투입). 판단 보류.
```

### 1.2 Forecaster row (PG)

verbatim:
```
{"run_id": "0dc69cbc-...", "company": "신규건설", "l6_main": "토목공사", "today_productivity": "0", "risk_level": null, "assessment": null, "reasoning": "데이터 부족 — 오늘 물량 모든 unit 0 (인원만 투입). 판단 보류."}
```

→ today_productivity=0 (today_qty=0, activity_master 에 신규건설|토목 그룹 부재 → baseline_qty=0 → today_qty = 0 × 1.0 = 0)
→ risk_level=null, assessment=null (Forecaster 가 null path 로 처리 — "판단 보류")

### 1.3 Optimizer advice

PG `optimizer_advice` 조회 결과 = **0 rows** (Optimizer 미진입, advice 미생성).

---

## 2. 검증 포인트 충족 (spec §7.4)

| 검증 포인트 | spec 의도 | 실 결과 |
|------------|----------|--------|
| baseline=None 분기 발현 | hil_2_node:122 `baseline_value is None` | **다른 분기 발현** — hil_2_node 진입 전 Forecaster 가 today_qty=0 으로 risk=null 처리 → risky 0건 → hil_2 가 interrupt 미발생. spec 가정한 hil_2_node baseline=None 분기는 본 fixture 에서 미발현 |
| cold_start payload note: "no_main_unit" 또는 "cold_start_no_baseline" | 그 중 하나 | **payload 자체 미생성** (interrupt 미발생) |
| Optimizer cold_start path | advice = cold_start 메시지 | **Optimizer 미진입** (advice 0건) |

**spec §7.4 검증 포인트 모두 다른 분기로 발현.** cold_start 의 실 동작은 spec 가정과 다른 경로:
- spec 가정: 신규 그룹 → baseline 부재 → hil_2 에서 cold_start payload → Optimizer cold_start path
- 실 동작: 신규 그룹 → today_qty=0 (baseline_qty=0 × ratio=1.0) → Forecaster "판단 보류" → risk=null → risky 제외 → Optimizer 미진입

---

## 3. spec §7.4 와의 실 cold_start path 비교 (audit 발견)

본 audit 가 잡은 cold_start 실 path:

| Path | trigger | 실 시뮬 | 결과 |
|------|---------|---------|------|
| **A. 신규 회사** (activity_master 에 없음) | baseline_qty=0 → today_qty=0 | 시뮬 4 | Forecaster "판단 보류", risky 0건, Optimizer 미진입 |
| **B. 기존 회사 + cold_start_no_baseline** | baseline_value=None (Chroma) | 시뮬 1 창원기전 (preview_cases=0) | hil_2 가 cold_start payload 박음, Optimizer cold_start path |

→ spec §7.4 가 정의한 분기는 **B** 인데, fixture 가 정의한 "신규 회사 + 신규 l6_main" 은 **A**. spec 정정 또는 fixture 정정 필요.

→ audit-report §5 에 "**cold_start 가 2 경로로 분기 — spec 가정과 실 fixture 불일치**" 추가 발견.

---

## 4. 추가 발견 드리프트

1. **cold_start 2 경로 발견** (위 §3) — spec §7.4 와 실 fixture 행위 불일치.
2. **신규 그룹 baseline 부재 시 risk=null** — Forecaster 의 null 분기 (판단 보류) 가 정상 동작. cold_start 와 별개 path 로 처리됨.
3. **Optimizer advice 미생성 시 PG 빈 응답** — 시뮬 4 의 optimizer_advice 0 row 는 spec 가정 (cold_start advice 라도 생성) 과 다름.
