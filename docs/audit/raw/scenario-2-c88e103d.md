# Scenario 2 raw — 주의 (우천 -20%)

**Spec 인용:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` §7.2
**Run ID:** `c88e103d-058c-40f8-a3a1-9810f0047ac9`
**날짜:** 2025-09-28
**Fixture:** 남웅건설 | 철근콘크리트공사 | m3 | 3 act | 우천 | productivity_ratio=0.8 | workers_ratio=1.0

---

## 1. 단계별 raw

### 1.1 호출

```
$ pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-28 --scenario "남웅건설|철근콘크리트공사|3|우천|0.8|1.0|m3" --auto-select-all
```

stdout 발췌:
```
[OK] generate_fake_daily_report: 3 Activity rows (scenarios=1)
[OK] run_id=c88e103d-058c-40f8-a3a1-9810f0047ac9 site_id=DEMO_SITE date=2025-09-28
[HIL-2 INTERRUPT] risky_groups: 1
  - 남웅건설|철근콘크리트공사: assessment=정상 risk=주의 preview_cases=5
[AUTO] --auto-select-all → resume keys = ['남웅건설|철근콘크리트공사']
[OPTIMIZER] advice rows: 1
```

### 1.2 Forecaster row (PG)

verbatim:
```
{"run_id": "c88e103d-...", "company": "남웅건설", "l6_main": "철근콘크리트공사", "today_productivity": "74.2568...", "risk_level": "주의", "assessment": "정상", "today_conditions": "맑음,우천"}
```

→ today_productivity = 74.26 m3/인 (baseline v2 = 31.07 의 **2.39배**)
→ risk_level=주의 (시뮬 1 의 0.45 ratio 와 동일 분기)
→ assessment=정상 (LLM 자유텍스트, 시뮬 1 과 동일 bias)
→ today_conditions = 맑음+우천

### 1.3 Optimizer advice

stdout verbatim:
```
diagnosis: 오늘 생산성은 정상 범위로 판단되며, 작업 조건 중 '우천' 표기는 실제 영향이 제한적이었던 것으로 추정됨. 과거 사례 대비 생산성 수준이 높아 현재 저하 징후는 크지 않음.
  - [rank 1] 우천 표기 관련 현장 실측 조건 재확인 권장 — 기상 영향 여부만 점검
  - [rank 2] 과거 패턴상 돌관·장비대기 등 변동 요인 발생 시에도 D+1 회복 비율 높음 — 추가 대응 필요성 낮을 수 있음
  - [rank 3] 잔여 물량 기준 현 수준 유지 시 공기 영향 미미 — 단기 변동은 모니터링 정도만 고려
  - [rank 4] 향후 우천 지속 또는 장비대기 동반 시 D+2 이상 누적 가능성 있어 대체 장비나 공정 조정 검토 필요
recovery_distribution: {'d+1': 2, 'd+5': 1, 'd+6': 1, 'not_recovered': 1}
```

→ recovery_distribution = **시뮬 1 과 동일** (남웅 철콘 그룹의 동일 case retrieval, 결정론 확인)
→ LLM diagnosis = "우천 표기 영향 제한적, 생산성 수준 높음" — 의미상 conditions 와 정반대 해석

---

## 2. 검증 포인트 충족 (spec §7.2)

| 검증 포인트 | spec 의도 | 실 결과 |
|------------|----------|--------|
| risk_level 분기 | 주의 또는 이상 | **주의** ✓ |
| conditions | ["맑음", "우천"] | "맑음,우천" ✓ |
| Optimizer cold_start vs 정상 advice 분기 | 정상 path | **정상 path** (preview_cases=5, 정상 advice 산출) ✓ |

---

## 3. 추가 발견 드리프트 (시뮬 2 만으로 노출)

1. **today_productivity 74.26 = baseline 의 2.39배** — productivity_ratio=0.8 의도 (저하) 와 정반대. 시뮬 1 의 ratio=0.45 (today_prod 69.62) 와 비교해도 **0.8 ratio 가 0.45 ratio 보다 더 높은 productivity** → ratio 값과 today_prod 비례 깨짐. 잠재 fixture bug.
2. **assessment=정상 동일 bias** — 시뮬 1 + 2 모두 LLM 이 assessment 를 "정상" 으로 결정. systematic bias 확인.
3. **recovery_distribution 시뮬 1 과 동일** → 결정론 확정. 같은 (company, l6_main) 그룹의 case retrieval 결과가 변하지 않음. 본 audit 의 결정론 컬럼 분류 근거.
