# 시뮬 2 — 남웅 우천 0.8 (단일 그룹)

- **date**: 2026-05-17
- **run_id**: `e739277e-c4bd-4798-a217-d73b7cf4bba8`
- **scenario**: `남웅건설|철근콘크리트공사|3|우천|0.8|1.0|m3`
- **의도**: ratio=0.8 → today_prod ≈ baseline × 0.8 → assessment delta 약함, 단 우천 conditions → risk_level="주의" 발현 확인

## 1. 호출

```bash
$ PYTHONPATH=. pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|3|우천|0.8|1.0|m3" \
    --auto-select-all
```

## 2. CLI 출력

```
[OK] generate_fake_daily_report: 3 Activity rows (scenarios=1)
[OK] run_id=e739277e-c4bd-4798-a217-d73b7cf4bba8 site_id=DEMO_SITE date=2025-09-27

[HIL-2 INTERRUPT] risky_groups: 1
  - 남웅건설|철근콘크리트공사: assessment=정상 risk=주의 preview_cases=5
[AUTO] --auto-select-all → resume keys = ['남웅건설|철근콘크리트공사']

[OPTIMIZER] advice rows: 1

--- 남웅건설|철근콘크리트공사 (forecast_assessment=정상) ---
diagnosis: 오늘 생산성은 정상 범위로 판단됨. 우천 흔적이 있으나 실제 작업 진행에는 큰 제약이 없었던 것으로 추정.
  - [rank 1] 우천 영향 재발 가능성에 대비해 금주 장비 운영 현황 점검 확인 권장
  - [rank 2] 과거 패턴상 날씨 안정 시 자연 유지·상승 경향 — 추가 조치 필요성 낮을 수 있음
  - [rank 3] 잔여 물량 기준 향후 2~3일 동안 현재 수준 유지 시 공기 영향 미미
  - [rank 4] 우천 반복으로 장비 대기 발생 시 대체 작업 전환 또는 작업 시간 조정 검토 필요
recovery_distribution: {'d+1': 2, 'd+5': 1, 'd+6': 1, 'not_recovered': 1}
```

## 3. PG forecasts row

```
company   | l6_main          | assessment | risk_level | today_prod | rag_n_similar | conditions    | reasoning_head
----------+------------------+------------+------------+------------+---------------+---------------+-----------------------------------
남웅건설  | 철근콘크리트공사 | 정상       | 주의       | 24.75      | 1             | 맑음,우천     | 유사 1건 평균 24.583 m3/인 대비 약 +1%로 정상 범위 내
```

→ today_prod=24.75 (= 31.07 × 0.8 ≈ 24.86, fixture 정합). RAG 평균 24.58 대비 delta +1% → assessment="정상". 단 conditions 에 "우천" 있어 `classify_risk_level` 가 risk_level="주의" 부여.

## 4. PG optimizer_advice row

```
company  | l6_main          | forecast_assessment | diagnosis (head)
---------+------------------+---------------------+------------------------------------------
남웅건설 | 철근콘크리트공사 | 정상                | 오늘 생산성은 정상 범위로 판단됨. 우천 흔적이 있으나 ...
```

recovery_distribution = {"d+1": 2, "d+5": 1, "d+6": 1, "not_recovered": 1} (Counter 결정론).

## 5. PG daily_reports row

- md_len = **788 chars** (시뮬 1 의 1481 vs ~절반 — 그룹 1개만)
- summary = {risk_counts: 이상0/정상0/주의1, advice_count: 1, total_workers: 264.0, total_qty_by_trade: {철근콘크리트공사: 2178.3}}

## 6. 핵심 fact

- **Forecaster fix 확인**: ratio=0.8 fixture → today_prod = 24.75 (= baseline × 0.8 정합).
- **risk_level "주의" 발현**: assessment="정상" 이라도 conditions="우천" 으로 인한 위험도 분류. spec §3 의 `classify_risk_level` 하이브리드 룰 정합.
- **rag_n_similar=1** = synthetic_v2 적재 그룹 부족 — drift #N1 (RAG 분포 정렬 별 cycle) 와 연관.

[[v2-scenario-1-156657ed]] [[v2-scenario-3]] [[v2-scenario-4]]
