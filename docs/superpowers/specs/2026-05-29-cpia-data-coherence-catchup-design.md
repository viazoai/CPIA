# CPIA 9/24 PoC — 데이터 정합(SSOT) + catch-up 산식 + 리포트 UI 수정 설계

> 작성일: 2026-05-29 | 대상: 9/24 PoC → 확정 후 7~9월 전체 적재
> 전제(절대 제약): 모든 데이터는 실 prod 그래프(`backfill_optimizer_advice_llm` = forecaster→optimizer→reporter) 출력. atomizer 앞단 입력(mapper_activities) 주입만 스크립트 허용. forecaster/optimizer/reporter 출력을 fixture 로 쓰지 않는다. 공종=건축·토목. 6월 이전 DELETE 금지.

---

## 0. 클린업 (완료)

- UI 날짜 목록 = `daily_reports` distinct dates (`/api/mock/report` `DISTINCT ON (report_date)`).
- **`daily_reports` 7/1~9/30 (9/24 제외) 140건 삭제** → UI 에 9/24 만 노출 (확인: API 444일 중 7~9 윈도우=9/24 단 하나).
- substrate(mapper_activities 9030 / mapped_history 3715, 7/1~9/23) **보존** → 9/24 누적·s-curve 깨지지 않음.
- pipeline_runs/forecasts/optimizer_advice 잔재는 재적재 시 backfill `--clean` 이 per-date dedup. Chroma daily_activities(과거 유사사례 ground) 미삭제.

---

## 1. 근본 원인 — 데이터 레벨 SSOT 붕괴 (실측 확인)

9/24 daily_report 실측:
```
S-curve: 실적 27.8% vs 계획 89.12% → gap 61.3%pt
KPI:     delay_days = 0  ⚠️ (실적 61%pt 뒤처졌는데 지연 0)
scen:    base recovery_days = 33 (delta -33)
```

원인: **S-curve 실적과 forecaster delay 가 서로 다른 소스를 본다.**

| 지표 | 소스 | 9/23 표본 |
|---|---|---|
| forecaster delay / 누적 | `mapper_activities` (l7_5 세부활동 전부 SUM) | 60행 sum **533** |
| S-curve 실적% | `mapped_history` | 11행 sum **285** |

`insert_mapped_history_batch` (db.py:489) 의 `ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE SET today_qty = EXCLUDED.today_qty` 가 **마지막값 채택(합산 X)**. 한 (wa,l6,company)에 l7_5 세부활동이 여러 개면 collapse 되며 한 활동 today_qty만 남고 나머지 손실 → S-curve 실적 심각 과소(27.8%). seed 물량 자체(plan progress 추종)는 정상 — **재생성 불필요**.

커버리지도 sparse 아님: 9/24 활성 plan WP 60개 전부(100%) actual 존재. 문제는 collapse 손실뿐.

---

## 2. 수정 (Option A — 전체 체인 정합, 사용자 승인)

### 2-1. S-curve 실적 소스를 mapper_activities 로 통일 (SSOT) — 핵심
- `view_builder._build_s_curve` actual CTE: `mapped_history` → `mapper_activities` (report_date ≤ today, is_mock=false, (wa,l6_main) SUM today_qty). forecaster 누적과 동일 소스.
- 보강: `insert_mapped_history_batch` collapse 손실 방지 — seed/atomizer 에서 (wa,l6,company) 별 today_qty **pre-SUM** 후 insert (idempotent 유지). 또는 mapped_history 의존 제거.
- 기대: 9/24 실적% 27.8% → ~75-80% (plan 89% 대비 현실적 lag). delay·gap·recovery 한 방향.

### 2-2. forecaster delay 정합 검증
- 실적%가 현실화되면 per-WP point-in-time delay(deficit>0)도 site 실적%와 같은 방향. (compute_delay 산식 자체는 2026-05-29 point-in-time 전환 그대로 유지.)
- 검증: 9/24 KPI delay 와 s-curve gap 부호·크기 일관.

### 2-3. recovery_days 를 gap·생산성 기반으로 (optimizer)
- 현재 recovery_days = 과거 유사 저하사례 회복분포(D+N) median → 실제 누적 gap·생산성과 무관.
- 변경: WP 누적 gap(deficit_qty = 계획누적 − 실제누적)을 "일일 만회 가능 물량"으로 나눠 만회일수 산출.
  - 일일 만회물량 = 계획 일일률(plan_per_day_qty) × (회복 생산성 배수 − 1)
  - 회복 생산성 배수 = 과거 회복분포에서 도출(회복 후 생산성이 plan 대비 얼마나 올랐나) → 과거사례 차별점 유지
- site recovery_days = Σ(by_wp) (기존 일원화 유지).

### 2-4. FE catch-up 곡선 (diagnosis.ts buildScenarioCurve)
- 현재: lastActual → plan[today+recoveryDays] 직선(가파름).
- 변경: 오늘부터 "계획 일일률 × 회복배수" rate 로 점진 상승 → plan 합류. catch-up 날짜 = gap ÷ 초과생산률 (recovery_days 와 정합). 저장 데이터 불변, FE 곡선 산식만.

---

## 3. 리포트 UI 수정 (B~G, 지시 확정)

- **B 진단 자연어화**: `DIAG_PROMPT_V10` 의 "risk_level 차원 인용" → 자연어("위험 수준 높음")로. 카드 details 스키마명 노출 제거.
- **C 유사사례 회복요약 상단 + 3건 기준**: `recovery_distribution_text` 를 헤더 바로 밑(목록 위)으로 이동(OptimizerResult.tsx), **표시되는 3건만** 집계(view_builder `_recovery_distribution_text` 3건 slice). 평균 회복일수도 이 요약줄에 편입.
- **D 권고 개조식**: `[키워드]` 괄호 보이게 + 줄바꿈 자연스럽게 + 이유는 흐린 텍스트(`←` 출처) — sample `docs/sample/optimizer-output-design.md` 준용. (OptimizerResult.tsx)
- **E 상세현황**: 회복분포 행 제거, 평균회복일수 → C 요약줄 편입, **계획 생산성 추가**(계획 대비 금일 비교), 산출근거 쉬운 문장. DIAG 도 계획대비 생산성 고려.
- **F status 4사분면 4색**: status = `_quadrant_of(prod,impact)` (risk/caution/watch/safe). 점 위치=색 1:1. 위험(저생산·고임팩 빨강)/주의(저생산 주황)/관찰(고임팩 회색)/정상(고생산·저임팩 초록). 배경 ReferenceArea 임팩트 임계 70→50 일치. 목록칩·카드·KPI 동일 기준. forecaster risk_level 은 LLM 진단 입력으로만.
- **G 시나리오 스크롤**: ForecastChart aiAdvice 카드 `max-h + overflow-y-auto`.

---

## 4. PoC 실행 (9/24 단일, 확정 후 7~9 전체)

1. 코드 수정(2-1~2-4 + B~G).
2. 9/24 실 그래프 재실행: `backfill_optimizer_advice_llm --clean` (9/24 기존 3 run dedup) → `backfill_daily_report_views_v2` 9/24.
3. UI(5537) 직접 확인: 실적%·delay·gap·recovery 정합 + 곡선 점진 + 4색 + 권고 개조식 + 유사사례 3건 요약 상단.
4. 사용자 확정 → 이 문서를 최종 스펙으로 정리 → 7~9 전체 재적재(prod 그래프) + 월별 UI 검증.

## 5. 검증 형식 (각 단계 실측 보고)
- `$ 명령` → 실 출력 원본 → 결론. delay/실적%/gap/recovery 4숫자 한 방향 확인.

---

## 6. 진행 현황 — 2026-05-29 (2차 세션) 종료 시점

### 6-1. 완료·검증 (working tree, 미commit) — 9/24 PoC 실 그래프(run a3425ca9) 출력으로 검증

| 항목 | 파일 | 검증 결과 |
|---|---|---|
| S-curve SSOT (orphan/collapse 회피) | `view_builder._build_s_curve` (mapper_activities, JOIN 없이) | 실적 27.8→**71.3%**, gap 61→**17.8%pt** |
| status 4색 = 분포도 위치 | `view_builder._quadrant_status3` + `QuadrantScatter.tsx`(점·배경 4색, 임팩트 임계 50) | 포장 65.7%→주의, 디럭스 92.1%→정상 |
| KPI delay 정합 | `view_builder` 말미 s-curve "며칠 뒤처짐" 산출 | delay **71**, recovery 33 → "현황 71일 지연·AI 33만회·최종 +38" 일관 |
| B 진단 자연어 | `prompt.DIAG_PROMPT_V10`/`RECS_PROMPT_V10` 스키마명 금지 | placeholder 0, "risk_level" 등 미노출 |
| C 유사사례 요약 상단·3건 | `view_builder _recovery_distribution_text`(3건+평균편입), `OptimizerResult.tsx`(헤더 밑 이동) | "3건 중 0건 회복 \| 미회복 3건" |
| D 권고 개조식 | `OptimizerResult.tsx`([키워드] bold+자연줄바꿈+`←`이유), `page.tsx` §03 간결([키워드] 조치) | — |
| E 상세현황 | `view_builder` details: 위험평가·평균회복·회복분포·**유사사례수 제거**, **계획 생산성**(=금일÷pct) + **공사기간**(l6 plan MIN~MAX) 추가, 산출근거 직관문장 | 공사기간 예 `2024-12-02 ~ 2025-10-24` |
| per-WP 일정영향 정합 | `view_builder` 말미: 일정영향 = 그 WP 공기단축 일수 | Σby_wp=33=site, 카드 "5일 지연↔-5일" |
| G 시나리오 스크롤 | `ForecastChart.tsx` aiAdvice `max-h+overflow` | — |
| 클린업 | daily_reports 7~9(9/24제외) 140건 삭제 | UI 9/24만 |

### 6-2. 남은 결정 (UI 보고) — catch-up 곡선 배수
- AI 시나리오 라인이 아직 계획 페이스의 **5배**(0.69 vs 0.15 %pt/day). recovery_days=33(과거 D+N)이 71→94%(23%pt)를 33일에 닫으라 강제.
- 사용자: "UI 먼저 보고 결정". plan rate × 배수(1.5/2/3x)로 점진 상승 + catch-up = gap÷초과율 재산출 (`diagnosis.ts buildScenarioCurve` + recovery_days). 배수 확정 후 적용.

### 6-3. 알려진 데이터 부채
- `mapper_activities` **93.6%(148,157행) orphaned** (과거 cleanup이 pipeline_runs만 삭제, mapper는 FK cascade 아님). forecaster `fetch_pg_actual_cum_qty`(JOIN 없음)·s-curve 둘 다 orphan 포함 → 일관은 하나 누적이 inflated 가능. **전체 재적재 시 orphan DELETE** 필요.
- per-WP forecaster point-in-time delay 가 orphan-inflated cum 으로 0 → 카드 일정영향은 scenarios.by_wp 우회 사용 중.

---

## 7. 다음 세션 — l6 단위 계산 컨셉 변경 + 2024-04-11 전체 재적재 (사용자 결정, deferred)

> **2026-05-29 (3차) 구체화 → [2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md](./2026-05-29-cpia-reseed-v2-per-unit-seeding-design.md)** 로 이관. 핵심 결정: 계산 grain = (company,wa,l6,**unit**) 단위 스트림 / 표시 = l6 카드, plan 정규분포 + actual 조건변동 ~85% 엔벨로프 + 활동별 총합보존, today_cum_qty=Σ일별(SSOT 근원 수정), 딜레이 분모 actual_rate, 주입점 build_demo_graph, **적재 전 결정론적 숫자검증 게이트 필수**.

### 7-1. 컨셉 변경: 계산 단위 = activity → **l6 (company+l6_main)**
현재: 더미데이터가 마스터플랜 **액티비티 1:1** 매칭(예 거푸집공사)으로 공사기간에 맞춰 일별 물량 분배. forecaster/reporter 도 (wa, company, l6) 또는 활동 단위로 분리 표시.

목표: mapper 가 모든 활동을 l6 로 매핑한다는 전제(예 남웅의 거푸집·철근 → **철근콘크리트공사** l6)에 맞춰, **forecaster 부터 l6(company+l6_main) 단위로 묶어 계산·표시**:
- 리포터/진단: 거푸집·철근 액티비티가 따로가 아니라 **철근콘크리트공사 하나로** 묶여 표시.
- 생산성: 분모 = 그 (company, l6) 의 마스터 물량 **합**, 분자 = 그 l6 에 속한 모든 활동(거푸집+철근) 실적 물량 **합** → 한 개 l6 공종 생산성.
- 일정(공사기간): 그 (company, l6) 에 속한 활동들의 plan_start **MIN** = 시작, plan_finish **MAX** = 종료. (§6-1 의 공사기간 산출이 이미 이 방식 — 선반영됨.)
- 데이터 행 수는 동일(활동별 생성 유지), **집계/계산 그레인만** activity → l6.

영향 파일(예상): `forecaster/agent.py`(group key (wa?,company,l6)→(company,l6)), `forecaster/aggregate.py`(분모 l6 물량합), `optimizer/view_builder._build_productivity_views_v2`(grouped_items wp_id (wa-l6-company)→(l6-company)? — wa 분리 폐기 검토), quadrant/wp_summary 키, `_build_s_curve`(이미 (wa,l6) → (company,l6)?).
※ 결정 필요: `wa`(work area) 분리를 유지할지 완전히 (company,l6) 로 합칠지 — PoC 로 확인.

### 7-2. 2024-04-11 부터 전체 재적재
- 컨셉 변경 + orphan 부채 정리를 위해 seed 부터 다시. `seed_dummy_year.py`(입력 전용 리팩터 — forecasts/advice/daily_report write 제거) → `backfill_optimizer_advice_llm`(실 그래프, --clean) → `backfill_daily_report_views_v2`. 윈도우 2024-04-11 ~ 2025-09-24.
- 재적재 전 **orphan mapper_activities DELETE** (run_id NOT IN pipeline_runs).
- 월별 UI 검증 (사용자 직접 확인 후 다음 달).

### 7-3. 순서
1. catch-up 곡선 배수 확정 (6-2) → buildScenarioCurve + recovery_days 적용 → 9/24 재확인.
2. l6 단위 계산 컨셉 (7-1) 구현 → 9/24 PoC 재확인.
3. orphan 정리 + 2024-04-11~ 전체 재적재 (7-2) → 월별 검증.
