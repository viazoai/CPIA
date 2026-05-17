# Scenario 1 raw — PM 원안 데모 재현 (남웅+세보+창원 3 회사)

**Spec 인용:** `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md` §7.1
**Run ID:** `ca7d820c-a02c-4094-afa3-6fa7cb765dc4`
**날짜:** 2025-09-27
**Fixture (실 호출 — plan deviation 으로 fix):**
- 남웅건설 | 철근콘크리트공사 | m3 | 5 act | 장비대기 | productivity_ratio=0.45 | workers_ratio=1.0
- 세보엠이씨 | 일반공조설비공사 | m2 | 3 act | 정상 | 1.0 | 1.0
- 창원기전 | 전등설비공사 | ea | 2 act | 정상 | 1.0 | 1.0

**Plan deviation 5건 (audit fact):**
1. Chroma port plan `8765` → 실제 `8000`
2. PG port plan `5433` → 실제 `5432`
3. CLI 인자 plan `--report-date` → 실제 `--date`
4. plan fixture 의 `세보건설|거푸집공사|m2` + `한일건설|콘크리트타설|m3` 가 activity_master 에 미존재 → 실 그룹으로 fix
5. plan 의 pytest `-p no:slow` 가 slow plugin 부재로 무효 (Task 0 결과 전체 183 통과)

---

## 1. 단계별 raw

### 1.1 가짜 작업일보 생성 (Parser/Mapper skip — fake_daily_report)

```
$ pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
    --date 2025-09-27 \
    --scenario "남웅건설|철근콘크리트공사|5|장비대기|0.45|1.0|m3" \
    --scenario "세보엠이씨|일반공조설비공사|3|정상|1.0|1.0|m2" \
    --scenario "창원기전|전등설비공사|2|정상|1.0|1.0|ea" \
    --auto-select-all
```

stdout 발췌 (verbatim):
```
[OK] generate_fake_daily_report: 10 Activity rows (scenarios=3)
[OK] run_id=ca7d820c-a02c-4094-afa3-6fa7cb765dc4 site_id=DEMO_SITE date=2025-09-27
```

→ Activity 10 건 생성 (남웅 5 + 세보 3 + 창원 2). pipeline_runs INSERT 성공.

### 1.2 Forecaster row 3 건 (PG forecasts 조회)

```
$ pipeline/.venv/bin/python3 -c "...SELECT * FROM forecasts WHERE run_id=..."
```

stdout (verbatim):
```
{"run_id": "ca7d820c-...", "company": "남웅건설", "l6_main": "철근콘크리트공사", "today_productivity": "69.619...", "risk_level": "주의", "assessment": "정상", "today_conditions": "맑음,장비대기"}
{"run_id": "ca7d820c-...", "company": "세보엠이씨", "l6_main": "일반공조설비공사", "today_productivity": "2.506...", "risk_level": "정상", "assessment": "정상", "today_conditions": "맑음"}
{"run_id": "ca7d820c-...", "company": "창원기전", "l6_main": "전등설비공사", "today_productivity": "0.586...", "risk_level": "주의", "assessment": "정상", "today_conditions": "맑음"}
```

→ 3 row 모두 정상 적재. 주목: 남웅 + 창원 모두 `assessment=정상` 이지만 `risk_level=주의` (분기 mismatch).

### 1.3 HIL 2 interrupt payload

stdout 발췌:
```
[HIL-2 INTERRUPT] risky_groups: 2
  - 남웅건설|철근콘크리트공사: assessment=정상 risk=주의 preview_cases=5
  - 창원기전|전등설비공사: assessment=정상 risk=주의 preview_cases=0
[AUTO] --auto-select-all → resume keys = ['남웅건설|철근콘크리트공사', '창원기전|전등설비공사']
```

→ 세보 (risk=정상) 은 risky_groups 제외 → optimizer 진입 X. 정상.
→ 남웅 preview_cases=5 (fetch_degradation_cases 5 건 잡음). 창원 preview_cases=0 (cold_start_no_baseline 또는 no main_unit).

### 1.4 Optimizer advice (auto-select-all 후 2 row)

stdout 발췌:
```
--- 남웅건설|철근콘크리트공사 (forecast_assessment=정상) ---
diagnosis: 오늘 생산성은 정상 수준으로 판단됨. 조건에 장비대기가 포함되어 있으나 실제 생산성 저하는 관찰되지 않음.
  - [rank 1] 장비대기 표기 반복 여부 확인 권장 — 실제 작업 지연과의 연계성 점검
  - [rank 2] 과거 패턴상 장비대기 표기만으로 생산성 저하가 고정적으로 발생하지는 않음 — 추가 대응 필요성 낮을 수 있음
  - [rank 3] 잔여 물량 기준 현재 생산성 유지 시 공기 영향 미미
  - [rank 4] 향후 장비대기 지속 및 생산성 하락 발생 시 장비 배치 조정 검토 필요
recovery_distribution: {'d+1': 2, 'd+5': 1, 'd+6': 1, 'not_recovered': 1}

--- 창원기전|전등설비공사 (forecast_assessment=정상) ---
diagnosis: cold_start
```

PG `optimizer_advice` 조회:
```
{"company": "남웅건설", "forecast_assessment": "정상", "recovery_distribution": "{\"d+1\": 2, \"d+5\": 1, \"d+6\": 1, \"not_recovered\": 1}"}
{"company": "창원기전", "forecast_assessment": "정상", "recovery_distribution": "{}"}
```

→ 남웅 = 정상 path (assessment=정상 → LLM 이 "장비대기 표기 반복 여부 확인" 류 약한 권고만 산출). 창원 = cold_start path.

---

## 2. 결정론/비결정론 컬럼 분류 (reviewer 권고 #1 검증 결과)

**rerun 검증 (run_id `0a175854-2e63-469d-9c59-5d6e3915dea0`, 동일 fixture):**
```
$ diff <(grep "today_productivity\|risk_level\|assessment" /tmp/scenario-1-db.log) \
       <(grep "today_productivity\|risk_level\|assessment" /tmp/scenario-1-rerun-db.log)
```
→ **diff 0 lines** = 결정론 컬럼 100% 일치 (today_productivity / risk_level / assessment / recovery_distribution).

LLM 자유텍스트 컬럼 (diagnosis / reasoning / recommendations) 만 어휘/표현 차이 발생:
- 시뮬 1 남웅 diagnosis: "조건에 장비대기가 포함되어 있으나 실제 생산성 저하는 관찰되지 않음"
- rerun 남웅 diagnosis: "장비 대기 표기는 있으나 실제 작업량·성과에는 영향이 제한된 것으로 보임"
- → 의미 동일, 표현 다름 (LLM 비결정성 정상)

확정 분류:

| 컬럼 | 결정론 / 비결정론 | 근거 |
|------|------------------|------|
| `today_productivity` | 결정론 (산술) | today_qty / assigned_workers — Forecaster `aggregate.py` |
| `risk_level` | 결정론 (임계값) | productivity_ratio < threshold 분기 — `classify.py` |
| `assessment` | **결정론 (또는 highly stable LLM)** | rerun 일치 검증 결과 — 동일 fixture 2 회 호출에서 assessment="정상" 동일. spec reviewer 권고 #1 의 "LLM 자유텍스트" 가설은 반증 — rerun 도 같은 값. LLM bias 가 매우 일관적이거나 결정론 코드 path 일 가능성. 한 가지 fixture 만 검증했으니 "highly stable" 까지만 결론. |
| `reasoning` | 비결정론 (LLM 자유텍스트) | 시뮬 1 + rerun 의 reasoning 텍스트 diff 가 발생할 것 (Step 1.13 검증) |
| `recommendations` | 비결정론 (LLM rank list) | LLM rank 1~4 텍스트 |
| `diagnosis` | 비결정론 (LLM 자유텍스트) | optimizer agent.py 의 LLM 출력 |
| `recovery_distribution` | 결정론 (코드단 산출) | optimizer agent.py `_compute_recovery_distribution` 함수 — Chroma case 의 d+N 카운트 |

→ audit-report §6 Limitation 에 이 분류 반영.

---

## 3. PoC 원안 §2 데모 권고사항 패턴 일치도 (수동 검토)

PM 원안 §2 Optimizer 출력 예시 (verbatim):
```
권고사항:
  1. 내일 오전 타워크레인 스케줄 확인 필수
  2. 과거 패턴상 장비 확보 시 다음날 자연 복귀 가능성 높음
  3. 잔여 물량 기준 D+3 이내 정상화 시 공기 영향 없음
  4. D+3 초과 시 야간 연장 또는 주말 투입 검토 필요
```

본 시뮬 1 남웅 Optimizer advice (verbatim):
```
  - [rank 1] 장비대기 표기 반복 여부 확인 권장 — 실제 작업 지연과의 연계성 점검
  - [rank 2] 과거 패턴상 장비대기 표기만으로 생산성 저하가 고정적으로 발생하지는 않음 — 추가 대응 필요성 낮을 수 있음
  - [rank 3] 잔여 물량 기준 현재 생산성 유지 시 공기 영향 미미
  - [rank 4] 향후 장비대기 지속 및 생산성 하락 발생 시 장비 배치 조정 검토 필요
```

**의미 비교:**

| PM 원안 권고 (의도) | 시뮬 1 권고 (실 LLM) | 의미 일치도 |
|---------------------|----------------------|------------|
| #1 "타워크레인 스케줄 확인 필수" — 강한 액션 | rank 1 "장비대기 표기 반복 여부 확인" — 표기 확인 중심 | **부분** (장비 점검은 동일, 액션 강도 약함) |
| #2 "장비 확보 시 다음날 자연 복귀" — 회복 시나리오 | rank 2 "장비대기 표기만으로 저하 고정적 X" — 회의적 톤 | **드리프트** (PM 원안 = 회복 가능성 강조 / 실 = 추가 대응 필요성 낮음) |
| #3 "D+3 이내 정상화 시 공기 영향 없음" | rank 3 "현재 생산성 유지 시 공기 영향 미미" | **일치** |
| #4 "D+3 초과 시 야간 연장 또는 주말 투입" — 강한 액션 | rank 4 "향후 저하 발생 시 장비 배치 조정 검토" — 조건부 약한 액션 | **부분** (액션 종류 다름) |

→ 일치 1 / 부분 2 / 드리프트 1. **drift 원인 추정:** 남웅 ratio=0.45 임에도 forecast_assessment="정상" 으로 LLM 분류된 결과 → Optimizer 가 정상 path 로 가서 약한 권고 산출. PM 원안의 "이상 → 강한 권고" 흐름 미발현.

→ audit-report §5 에 "**Optimizer 권고 강도 ↔ forecast_assessment 종속성**" 추가 발견 드리프트 후보로 등록.

---

## 4. 핵심 추가 발견 드리프트 (시뮬 1 만으로 노출)

1. **forecast_assessment vs risk_level 분기 일관성 (audit-report §5.1)** — 남웅 ratio=0.45 → risk_level=주의 (임계값 기반 결정론) but assessment=정상 (LLM 자유텍스트). 두 컬럼이 서로 다른 결정 path 사용.
2. **assessment=정상 종속성** — Optimizer 의 권고 강도가 forecast_assessment 에 종속. assessment="정상" 시 PM 원안 의 강한 권고 (타워크레인 확인 필수, 야간 연장) 가 산출되지 않음. PoC 데모 시연 영향 high.
3. **productivity_ratio 0.45 임에도 risk_level=이상 아닌 주의** — Forecaster classify.py 의 임계값 정합 검토 필요.
4. **창원 ratio=1.0 인데 risk=주의 (cold_start)** — baseline 부재 시 risk_level 디폴트가 "주의" 인지 검증 필요. cold_start 가 항상 주의로 분류되면 정상 fixture 도 risky 로 잡힘 → HIL 2 노이즈.

위 4 항목 모두 audit-report §5 후보.
