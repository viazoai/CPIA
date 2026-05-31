# CPIA 리포트 숫자 일원화 — design (v3, 단일 진실 SSOT)

- 작성일: 2026-05-29
- 트랙: A_Track(pipeline view_builder/forecaster) + B_Track(web)
- 상태: 설계 (미commit). 사용자 승인 = "WP 당 단일 진실(single source of truth) 일원화".
- 선행: 본 문서 → TDD 구현 → clean+재적재 → 월별 UI 검증
- 변경 이력: v1(오진) → v2(baseline 정정) → **v3(전면 UI 재검토 후 SSOT 일원화로 재정의)**

---

## 0. 이미 done (git diff) — 다시 만들지 말 것
risk_level productivity_ratio(`forecaster/agent.py:236-256`,`classify.py`), wp_summary.status=risk_level(`view_builder:769-794,1851`), site recovery=Σby_wp(`_site_slot:1375`), actual_cum=PG(`aggregate.py:14-40`), point-in-time delay 산식 존재(`aggregate.py:158-168`, UI 미연결).

## 1. 증상 (사용자, verbatim)
① 분포도-목록-카드 status 불일치 ② wp목록 공기단축 합 ≠ 시뮬레이션 최적화 ③ delay 비현실 ④ 시뮬 5일인데 카드 제각각(1+2+2=5 분해 원함) ⑤ 일정영향 산출근거 안 보임 ⑥ 같은 숫자가 컴포넌트마다 다름 → 일원화 요구.

## 2. 진단 — 전 컴포넌트 숫자 감사 (실측, `scripts/_audit_ui_consistency.py`)

한 WP 가 컴포넌트마다 다른 값. 예 도장공사-선보 2025-09-24:

| 컴포넌트 | status | 생산성 | 공기단축/지연 |
|---|---|---|---|
| 카드 optimizer.by_wp | 이상 | details 44.65 / 진단본문 2.02 | 30일 지연 / 미회복 5건 |
| 목록 wp_summary | normal | — | recovery 5 |
| 시뮬 scenarios.by_wp | — | — | recovery 5 |
| 상단 KPI | None | 91.6 | delay 2 |

전 날짜 패턴: 8/15·9/09 `Σwp_summary recovery=0` vs `site=30/40`; KPI recov 159 vs site 30; 카드 일정영향 -108·195일(비현실·부호혼란); prod raw 0.00·26.83.

**구조적 원인**: 한 WP 진단을 **5개 독립 경로**가 따로 계산·매칭:
- status: `forecasts.risk_level`(목록 lookup, 종종 None) vs `_quadrant_of(cpi,impact)`(분포도) vs advice `위험 평가`(카드)
- prod: `cpi`(분포도/KPI) vs `perperson`(카드 details) vs `today_productivity`(진단 본문) — 단위·스케일 다름
- delay: `forecasts.delay_days`(forward, ±cap) — 카드 일정영향, 비현실
- recovery: `scenarios.by_wp`(시뮬) vs `wp_summary.recovery_days`(목록, 미채움 잦음) vs RAG 회복분포(카드)
- 각 builder(`_build_optimizer_view:1080`, `_build_scenarios:1301`, `_build_productivity_views_v2`)가 forecast 를 **독립 매칭** → 발산. + 데이터 오염(run 혼재, §아래 R0).

## 3. 결정 (사용자 승인)
| D1 | WP 당 단일 truth record. 목록·분포도·카드·시뮬 전부 이 record 만 소비 |
| D2 | delay = point-in-time(qty), 일 단위, window 독립, **산출근거 문자열 동봉** |
| D3 | status = risk_level 단일 |
| D4 | prod = 계획대비 정규화 %, 진단 본문도 같은 값 |
| D5 | recovery: by_wp=목록=카드 동일, site=Σ |

## 4. 설계 — 단일 진실(SSOT) 아키텍처

### 4.1 per-WP truth record
`_build_productivity_views_v2` 안에서 WP(=`_wp_id_of(wa,l6,company)`)당 **1개** 계산:

```python
WpTruth = {
  "wp_id", "wa", "l6_main", "company", "trade_frame_category",
  "status":            str,    # 'normal|caution|risk' ← risk_level (단일)
  "risk_level":        str,    # '정상|주의|이상'
  "productivity_pct":  float,  # 계획대비 % (단일, clamp[0,200])
  "perperson", "unit",         # 표시 보조 (라벨 "98% (3.2 ton/인)")
  "impact":            float,  # 분포도 y (영향도)
  "delay_days":        int,    # point-in-time (단일)
  "delay_basis":       str,    # 산출근거 "계획누적 1038 − 실제 928 = 110 부족 ÷ 일평균 2.8 → 39일"
  "recovery_days":     int,    # 단일 (시뮬 base_p50 와 동일)
  "condition", "diagnosis", "similar_cases", "recommendations",  # narrative (LLM)
}
```

### 4.2 출력 매핑 (전부 truth 에서 파생)
| 출력 jsonb | 소비 필드 |
|---|---|
| wp_summary[] | status, productivity_pct, recovery_days, delay_days |
| quadrant[] (분포도) | x=productivity_pct, y=impact, **색=status** (≠ _quadrant_of), recovery_days |
| scenarios.by_wp[wp_id].base_p50 | recovery_days; site = Σ |
| optimizer_view.by_wp[wp_id].details | 위험평가=risk_level, 금일생산성=productivity_pct(+perperson), 일정영향=delay_days **+ delay_basis**, 회복=recovery_days |
| optimizer_view diagnosis 본문 | productivity_pct 같은 값 인용 (별도 prod 금지) |
| kpi (site) | delay=대표값(중앙값 or 최악), prod=median(productivity_pct), recovery=Σ, risk=worst |

→ 카드·목록·분포도·시뮬·KPI 가 **같은 truth[wp_id]** 를 읽으므로 정의상 일치.

### 4.3 delay = point-in-time + 산출근거 (D2)
`forecaster/aggregate.py`: `actual_cum`·`plan_total` **동일 activity 집합 기준**(Σ-vs-distinct 제거). `plan_cum_to_today = plan_per_day_qty × min(elapsed,total_days)`; `deficit = plan_cum_to_today − actual_cum_to_today`; `delay_days = round(deficit/plan_per_day_qty)`. window 폐기. `delay_basis` 문자열 동봉. UI(`view_builder` kpi_delay + truth.delay_days)가 이 값 사용.

### 4.4 prod 정규화 (D4)
`productivity_pct = today_qty당 실제 인당생산 / 계획 정상 인당생산 × 100`, clamp[0,200]. raw qty/worker(0.003·26.83) 폐기. 분포도 x·목록·카드·진단 본문 전부 이 값.

## 5. 실제 작업 + 순서 (TDD)

- **R0 (선행)**: clean+dedup 재적재 준비 — `clean_window.py` + (site,date) run 1개 강제. (산식 fix 후 일괄 실행)
- **R1**: `forecaster/aggregate.py` delay = point-in-time + Σ/distinct 정합 + delay_basis. UI 연결(kpi_delay). [게이트 A: 1wp 재seed → delay 부호·크기·근거 실측]
- **R2**: `view_builder` per-WP truth record 도입 + 5개 출력 매핑 통일. prod 정규화. status=risk_level(분포도 포함). [게이트 B: 1일 재적재 → 한 WP 가 4컴포넌트에서 동일값]
- **R3**: FE — `QuadrantScatter.tsx` 색·필터 → truth.status; 카드 일정영향 옆 delay_basis 표시(사용자 요청, 디자인 불가침 예외 최소 추가). [디자인: layout 유지, 색/근거텍스트만]
- **R4**: R0 재적재 7→8→9월 순차. [게이트 C: 월별 Playwright — 한 WP 전 컴포넌트 일치 + site=Σwp + delay 현실+근거 + 저하 wp 주의·이상]

### 게이트 (실호출 필수, LLM bypass 드라이)
- A: delay 부호=prod 방향, 크기 현실(±수십, -37·195 금지), basis 산식 검산.
- B: `truth[wp_id]` == wp_summary == quadrant == scenarios.by_wp == card.details (전 필드 동일). Σwp recovery == site.
- C: 월별 UI 직접 확인(사용자 goal) — 분포도=목록=카드 status, 공기단축 합=시뮬, delay+근거, prod 의미값.

## 6. 드롭 / 리스크
- 드롭(오진): `'d+N'/'D+N'`, `page.tsx:309` 제거, seed today_cum_qty(#158).
- delay 곡선: plan_cum·actual_cum 둘 다 linear 통일(window 무관). 음수(앞당김) max() 제거 여부 게이트 A 결정.
- LLM 스콥: 코드매칭·할증만. 숫자는 결정론 → 드라이 회귀.
- FE 디자인 불가침: layout/markup 유지. status 색매핑 + delay_basis 텍스트만 추가(후자 사용자 명시 요청).
- 6월 이전 DELETE 금지. 재적재 2025-07~09. main 머지=조형준 프로. commit=요청 시만.
