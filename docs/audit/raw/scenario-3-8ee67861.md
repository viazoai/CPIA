# Scenario 3 raw — 이상 (돌관 -45% + workers ×1.3)

**Spec 인용:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` §7.3
**Run ID:** `8ee67861-d627-4c88-ac4f-62208539726b`
**날짜:** 2025-09-29 (CLI 입력) — but stdout date=2025-09-28 (off-by-one 잠재 이슈)
**Fixture:** 남웅건설 | 철근콘크리트공사 | m3 | 3 act | 돌관 | productivity_ratio=0.45 | workers_ratio=1.3

---

## 1. 단계별 raw

### 1.1 호출

```
$ pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-29 --scenario "남웅건설|철근콘크리트공사|3|돌관|0.45|1.3|m3" --auto-select-all
```

stdout 발췌:
```
[OK] generate_fake_daily_report: 3 Activity rows (scenarios=1)
[OK] run_id=8ee67861-d627-4c88-ac4f-62208539726b site_id=DEMO_SITE date=2025-09-28
```

→ **stdout date=2025-09-28** 인데 CLI 입력은 `--date 2025-09-29`. **off-by-one date drift 가능성** (date 파싱 또는 sites/pipeline_runs INSERT 시점 timezone 이슈?). audit fact.

stdout 계속:
```
[HIL-2 INTERRUPT] risky_groups: 1
  - 남웅건설|철근콘크리트공사: assessment=정상 risk=주의 preview_cases=5
```

### 1.2 Forecaster row (PG)

verbatim:
```
{"run_id": "8ee67861-...", "company": "남웅건설", "l6_main": "철근콘크리트공사", "today_productivity": "32.1319...", "risk_level": "주의", "assessment": "정상", "today_conditions": "돌관,맑음", "reasoning": "맑음·돌관 조건에서 여러 부위 동시 타설·조립 진행. 유사 4건 평균 23.25 m3/인 대비 +38%로 상향 변동이며 작업 내용상 돌관 투입 효과로 정상 범주."}
```

→ today_productivity = **32.13** m3/인 (baseline v2 = 31.07 의 **+3.4%** = 거의 baseline 수준)
→ risk_level=주의 (시뮬 1+2 와 동일 분기)
→ assessment=정상 (LLM bias 지속)
→ LLM reasoning: "유사 4건 평균 23.25 대비 +38%" — Forecaster RAG 가 conditions=["돌관","맑음"] 필터로 매칭한 4건 평균 23.25 vs 오늘 32.13 = +38% → "돌관 투입 효과로 정상 범주" 해석

### 1.3 Optimizer advice

stdout verbatim:
```
diagnosis: 오늘 생산성은 정상 범위이며, 돌관 작업으로 인해 평시 대비 높은 실적이 나타난 상황으로 판단됨.
  - [rank 1] 돌관 투입 인원·장비 사용 기록 확인 권장 — 향후 기준치 보정 참고용
  - [rank 2] 과거 패턴상 돌관 이후 D+1 생산성은 평시 수준으로 자연 회귀 가능성 있음
  - [rank 3] 잔여 물량 기준으로 보면 오늘 실적 반영 시 단기 공기 여유 확보 가능
  - [rank 4] 돌관 패턴이 반복될 경우 주간 계획 대비 과투입 여부 검토 필요
recovery_distribution: {'d+1': 2, 'd+5': 1, 'd+6': 1, 'not_recovered': 1}
```

→ LLM diagnosis = "**돌관 작업으로 평시 대비 높은 실적**" — 의도 (저하/이상) 와 **정반대 해석**
→ recovery_distribution 시뮬 1+2 와 동일 → 결정론

---

## 2. 검증 포인트 충족 (spec §7.3)

| 검증 포인트 | spec 의도 | 실 결과 |
|------------|----------|--------|
| risk_level=이상 트리거 | 이상 | **주의** ✗ (이상 미발현) |
| recovery_distribution JSONB 산출 | 정상복귀/부분복귀/미복귀 분포 | `{d+1:2, d+5:1, d+6:1, not_recovered:1}` ✓ |
| today_prod = baseline × 0.346 추정 (= 31.07 × 0.346 ≈ 10.75) | 강한 저하 productivity | **32.13** ✗ (baseline 의 +3.4%, 거의 동일) |

→ 시뮬 3 의 핵심 검증 포인트 (이상 발현) **미충족**. fixture 의 (productivity_ratio=0.45, workers_ratio=1.3) 조합이 의도된 productivity 저하를 산출하지 못함.

---

## 3. 추가 발견 드리프트

1. **시뮬 3 today_productivity 32.13 ≈ baseline 31.07** — productivity_ratio=0.45 인데도 today_prod 가 baseline 수준. fixture bug.
2. **date off-by-one** — CLI `--date 2025-09-29` 인데 stdout `date=2025-09-28`. timezone 또는 파싱 이슈.
3. **LLM diagnosis 의도 반전** — 돌관 0.45 ratio (저하 의도) 를 LLM 이 "**평시 대비 높은 실적**" 으로 해석. assessment+diagnosis 모두 의도와 정반대.
4. **recovery_distribution 동일 결과 (시뮬 1+2+3)** — 같은 (company, l6_main, today_conditions 의 fetch_degradation_cases 결과) 가 시나리오 conditions 가 달라져도 동일하게 매칭된 5건 (동일 case set) → fetch_degradation_cases 가 conditions 필터 적용 X 가능성. 또는 case 의 conditions 분포가 충분히 균일해서 동일 5건이 매번 잡힘.
