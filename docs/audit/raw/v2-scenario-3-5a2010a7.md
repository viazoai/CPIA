# 시뮬 3 — 남웅 돌관 0.45 × workers 1.3 (단일 그룹)

- **date**: 2026-05-17
- **run_id**: `5a2010a7-5a01-42eb-8fea-6b19b97b7e4d`
- **scenario**: `남웅건설|철근콘크리트공사|3|돌관|0.45|1.3|m3`
- **의도**: ratio=0.45 + workers_ratio=1.3 → today_prod = baseline × 0.45 / 1.3 (인원 증가로 인당 생산성 더 저하)

## 1. 호출

```bash
$ PYTHONPATH=. pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|3|돌관|0.45|1.3|m3" \
    --auto-select-all
```

## 2. CLI 출력

```
[OK] generate_fake_daily_report: 3 Activity rows (scenarios=1)
[OK] run_id=5a2010a7-5a01-42eb-8fea-6b19b97b7e4d site_id=DEMO_SITE date=2025-09-27

[HIL-2 INTERRUPT] risky_groups: 1
  - 남웅건설|철근콘크리트공사: assessment=정상 risk=주의 preview_cases=5
[AUTO] --auto-select-all → resume keys = ['남웅건설|철근콘크리트공사']

[OPTIMIZER] advice rows: 1

--- 남웅건설|철근콘크리트공사 (forecast_assessment=정상) ---
diagnosis: 오늘 생산성은 정상 범위로 판단되며, 돌관 작업 조건에서도 특이 저하 근거는 확인되지 않음.
  - [rank 1] 돌관 작업 후 장비·인력 피로도 점검 확인 권장
  - [rank 2] 과거 패턴상 돌관 다음날 생산성은 대체로 자연 유지되므로 추가 개입 필요성은 낮을 수 있음
  - [rank 3] 잔여 물량 기준 향후 이틀간 정상 흐름 지속 시 공기 영향은 제한적
  - [rank 4] 돌관 반복 시 장비 가용성 불안정 가능성 있어 일정 간격 조정 검토 필요
recovery_distribution: {'d+1': 2, 'd+5': 1, 'd+6': 1, 'not_recovered': 1}
```

## 3. PG forecasts row

```
company  | l6_main          | assessment | risk_level | today_prod | workers | rag_n_similar | conditions  | reasoning_head
---------+------------------+------------+------------+------------+---------+---------------+-------------+--------------------------------------
남웅건설 | 철근콘크리트공사 | 정상       | 주의       | 10.71      | 114.4   | 1             | 돌관,맑음   | 유사 1건 (24.58 m3/인) 대비 -56%, 공정 혼재 영향으로 정상 범위
```

**workers 검증**: baseline_workers=88 × workers_ratio=1.3 = 114.4 (정합).

**today_prod 검증**: baseline_q=baseline_q × ratio = ? × 0.45, /workers (114.4). today_prod=10.71 → today_qty_total ≈ 10.71 × 114.4 ≈ 1225 m3. fixture 정합 (group total = baseline_q × ratio).

## 4. 흥미로운 발견 — assessment="정상" 임에도 RAG delta -56%

- `classify_assessment_rag` 룰: delta < -0.25 → "이상" / -0.25~-0.15 → "주의" / >= -0.15 → "정상"
- 본 case delta = -56% → 룰 상 "이상" 이어야 함
- 단 `classify_assessment` (classify.py:65) 의 라우팅: **rag_n_similar < 3 → Plan fallback** (RAG 신뢰 부족)
- Plan fallback (`classify_assessment_plan`) 산식: PLAN_NORMAL_RATIO=0.85
- 시뮬 3 의 today_prod=10.71 vs plan_prod (activity_master plan_mh 기반) — Plan ratio 0.85+ 라 "정상"

→ **drift #N1 의 영향**: synthetic_v2 적재 분포 부족 (rag_n_similar=1) → RAG 모드 진입 안 됨 → Plan fallback → 의도된 -55% 저하가 "정상" 분류로 빠짐. 별 cycle 의 synthetic_v2 분포 정렬 cycle 필수.

## 5. PG optimizer_advice row

```
company  | forecast_assessment | diagnosis (head)
---------+---------------------+------------------------------------------
남웅건설 | 정상                | 오늘 생산성은 정상 범위로 판단되며, 돌관 작업 조건에서도 특이 저하 근거는 확인되지 않음
```

recovery_distribution = {"d+1": 2, "d+5": 1, "d+6": 1, "not_recovered": 1} (시뮬 1/2/3 모두 동일 — Chroma 의 동일 그룹 cases 5건 검색 결과).

## 6. PG daily_reports row

- md_len = **755 chars** (시뮬 2 와 유사 — 1 그룹만)
- summary = {risk_counts: 이상0/정상0/주의1, advice_count: 1, total_workers: 343.2, total_qty_by_trade: {철근콘크리트공사: 1225.2}}

## 7. 핵심 fact

- **workers_ratio fixture 정합** = 88 × 1.3 = 114.4 ✓
- **drift #N1 효과**: synthetic_v2 적재 부족으로 RAG 신뢰 못 함 → Plan fallback → 의도된 저하 미발현
- **권고 quality**: LLM 이 "돌관 작업 조건에서도 특이 저하 근거 확인 X" 라고 (실 데이터는 -56% 인데도) 판단 — RAG 부족 + Plan 정상 신호로 오분류된 결과

[[v2-scenario-1-156657ed]] [[v2-scenario-2]] [[v2-scenario-4]]
