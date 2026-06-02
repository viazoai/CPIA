# CPIA 09-25 데모 정교화 — Export WA · 최적화 공기 정합 · 진단/만회방안 재설계

- 날짜: 2026-06-02
- 브랜치: A_Track
- 상태: 설계 승인 완료, 구현 플랜 대기
- 관련: [[cpia_report_ssot_decision]] (WP당 단일진실), `2026-06-02-cpia-ui-review-report-refinement-design.md` (직전 보고서 UI 작업)

## 배경 / 목표

09-25 작업일보 7개를 파이프라인에 넣어 export·report 를 점검하던 중 3가지 정교화 포인트가 나옴. 전부 **실데이터(09-24 완주 run, 원격 43.200.85.209:5532)로 근본원인 검증** 완료.

1. **Export WA 빈칸** — 통합 export 시트에 work area(Zone) 빈칸 행이 자주 보임.
2. **최적화 공기 ≠ WP목록 AI단축 합** — 공기단축 시뮬레이션 headline 과 WP목록의 단축일 합이 안 맞음.
3. **진단/만회방안 재설계** — 진단을 "그 날의 현황+현장여건"으로, 권고사항→만회방안 워딩, 유사사례·만회방안 각 2건, 괄호에 지연일수/AI단축일수.

**비목표 / 불가침**: [[feedback_no_design_change]] 디자인 불가침 — layout/style/markup 구조 변경 금지. **컬럼 내용·데이터 소스·라벨·LLM 프롬프트만** 변경. 시연자(조형준 프로) 디자인 의도 보존.

---

## Part A — Export WA 빈칸 (BE exporter + web)

### 근본원인 (실데이터 검증)
- Export 시트의 "Zone"(=work area, FAB/CUB) 컬럼은 parser 의 보수적 `extract_zone()`(`pipeline/agents/parser_post.py:120`) 결과인 `parser_activities.zone` 을 그대로 표시.
- 그런데 mapper 의 7단계 `resolve_wa`(`pipeline/agents/mapper.py:507`)가 채운 `mapper_activities.wa` 를 **export 가 전혀 안 읽음**.
- 09-24 완주 run 실측: `parser_activities.zone` **171건 전부 빈칸**, `mapper_activities.wa` **171건 전부 FAB(127)/CUB(44)**. 즉 데이터는 mapper 에 정확히 있는데 export 가 빈 parser.zone 을 봄.
- (09-25 처럼 HIL 미확정 run 은 mapper.wa 도 아직 빈칸 → UI 에서 Mapper 확정하면 채워짐. fix 효과는 **완주 run 에서** 발현.)

### 변경
1. **시트4 (물량)** — `pipeline/agents/exporter.py` 의 `fetch_sheet_data`(:37 부근, 시트4 = `parser_activities` SELECT) 가 `mapper_activities` 를 `(run_id, idx)` LEFT JOIN 해서 `wa` 를 함께 가져오고, `_fill_quantity`(:285 부근)의 Zone 셀을 `mapper.wa` 로 채움. `mapper.wa` 가 빈 경우만 `parser.zone` fallback.
2. **시트1 (출력인원)** — `parser_reports.bp_summaries`(jsonb, BP 단위 집계)라 per-activity wa 가 없음. `mapper_activities.wa` 를 `(company)` 기준 최빈값/대표값으로 집계해 `_fill_output_manpower`(:224 부근) Zone 에 주입. **[플랜 필수 결정]** BP 가 FAB·CUB 양쪽 걸치면 대표 1개(최빈) vs 콤마 병기 — 플랜에서 확정(silent drop 금지).
3. **web `/export` 그리드** — `web/app/api/mock/consolidated/route.ts` 의 zone 매핑을 동일 소스(`mapper.wa` 우선)로 정렬.

### 검증 (Done 정의)
- 09-24 run 으로 export 생성 → 시트4 Zone 빈칸 **0건** (171/171 FAB/CUB). 실 SQL + 실 export 출력 대조.
- web `/export` 그리드도 동일.

---

## Part B — 최적화 공기 = WP목록 AI단축 합 (BE view_builder + FE)

### 근본원인 (실데이터 검증)
09-24 `daily_reports` 실측: `scenarios.site.base_p50.recovery_days`=**31**, `Σ(scenarios.by_wp 23개)`=**66**, `Σ(wp_summary 13개)`=**21** — 세 숫자가 전부 다름.
- (a) `_site_slot`(`pipeline/agents/optimizer/view_builder.py:1428`)은 코드상 `site = Σ(by_wp)` 인데 저장값 31 ≠ Σby_wp 66 → 쓰기 순서 race/stale 잔재.
- (b) `scenarios.by_wp`(23, advice_rows 전체)는 `wp_summary`(13, quadrant 집합)의 상위집합 → 모집단 불일치.
- (c) FE WP목록은 추가로 `visibleTrades`(상위 trade) + `impact>0||productivity>0` 필터(`web/app/(app)/reports/page.tsx:145` 부근)로 더 줄여 표시.

### 결정: 전체 WP 고정합
**`wp_summary[*].recovery_days` 를 단일 진실(SSOT)** 로 삼고, "최적화 공기" headline = `Σ(wp_summary recovery_days)`. status 4분면 필터 클릭과 무관하게 고정.

### 변경
1. **BE** — `view_builder.py` 에서 `site.base_p50.recovery_days` 를 `Σ(wp_summary[*].recovery_days)` 로 명시 산출. **주의: 새 source 추가가 아니라 집계 모집단 교체** — `wp_summary[*].recovery_days` 는 이미 `scenarios.by_wp[wp].base_p50` 에서 파생됨(`:2255`). 현재 `_site_slot`/`kpi.recovery_days`(`:2216`)는 by_wp **23 집합**을 합산 → 이를 wp_summary **13 집합** 합산으로 swap. 쓰기 순서 보장으로 stale 제거. (redundant 산식 신규 추가 금지)
2. **FE** — `ForecastChart` 의 "최적화 공기"(`recoveryDays` prop, `reports/page.tsx:275` 부근) = 위 SSOT 값(= `detail.wp_summary` 의 recovery_days 합과 동일). WP목록은 **전체 wp_summary 노출** — `reports/page.tsx:146` 의 `filteredWpRowsBase` 에서 `visibleTrades.has(w.trade)` **와** `(w.impact>0||w.productivity>0)` **두 predicate 모두 제거**(표가 trade 를 숨기면 headline 과 재차 어긋남). status 4분면 필터만 강조용 유지(합산 모집단 불변).

### 검증 (Done 정의)
- 결정론: `site.base_p50.recovery_days == Σ(wp_summary recovery_days)` (실 daily_report JSON).
- FE: ForecastChart headline 숫자 == WP목록 AI단축 컬럼 합 (4분면 필터 클릭해도 headline 불변).

---

## Part C — 진단/만회방안 재설계 (BE optimizer + FE OptimizerResult)

### 현재
`web/app/components/reports/OptimizerResult.tsx` 가 `detail.optimizer.by_wp[wp_id]`(optimizer_view_jsonb)를 렌더. 진단=`DIAG_PROMPT_V10`("회복패턴+분기점")+결정론 prefix, 유사사례 3건, "권고사항" 3건.

### POC 로 확정된 프레임 (실 LLM 출력 검증, 09-24 3 WP)
진단 2줄:
1. **현황 (결정론, 물량 기준)** — `{조건} 조건 · 금일 {today_qty} {unit} (계획 일평균 {plan_daily} {unit})`. 숫자 소수 1자리, 아라비아 숫자.
   - `plan_daily = plan_total_qty[main_unit] / (plan_mh_sum / plan_mh_per_day)`. **단 이 값은 forecaster 의 기존 `plan_per_day_qty`(`pipeline/agents/forecaster/aggregate.py:183`)와 동일** — mh round-trip 재계산 말고 기존 값 재사용/노출 우선.
   - **per-person "정상 대비 %" 는 사용 금지** — 실측 결과 forecast 생산성(today 17.5)이 과거 baseline(1.6)·계획과 다른 basis 라 "정상 대비 1061%" 같은 헛값이 나옴(아래 caveat). 그래서 물량 페이스로 표기.
2. **현장여건 (LLM 1줄)** — 새 진단 프롬프트. "회복패턴/분기점" 폐기, "그 날 진척을 만든/막은 현장 조건(자재·인력·기상·간섭·양중)을 trade_frame 제약과 연결한 1가지 신호". 조건="정상"이면 없는 장애 지어내기 금지. 아라비아 숫자만, 인시 절대수치(mh_gap) 금지, 한자·영어약어 금지, 위험도 "이상"이면 "정상범주" 금지.

유사 과거사례: **3 → 2건** (`OptimizerResult.tsx:26` slice(0,3)→(0,2), `view_builder.py` recovery 분포 텍스트도 [:2]).
만회방안: **"권고사항" → "만회방안" 워딩 변경**, **3 → 2건**. 구조(keyword/action/reason)는 유지(POC 품질 확인됨).
괄호: **진단 옆 `(지연 +N일)`** = `wp_summary.delay_days`(forecasts.delay_days, point-in-time), **만회방안 옆 `(AI 단축 -N일)`** = `wp_summary.recovery_days`. → `OptimizerResult` 에 두 값 prop 배선(현재 `OptimizerOutput` 타입엔 없음; 부모 `reports/page.tsx` 가 `wpRow.delay_days`/`recovery_days` 보유).

### 변경
1. **BE 프롬프트** — `pipeline/agents/optimizer/prompt.py` 의 `DIAG_PROMPT_V10` 을 "현장여건 1줄" 버전으로 교체(또는 신규). 진단 1줄(물량 현황)은 코드가 결정론으로 작성(prefix 자리 대체) — `view_builder.py:1210` 부근 prefix 합성부에서 `plan_daily` 기반 물량 현황줄 생성. 유사사례/만회방안 trim 은 view_builder + OptimizerResult.
2. **FE** — `OptimizerResult.tsx`: "권고사항"→"만회방안" 라벨, slice 3→2(유사·만회), 진단/만회방안 헤더 괄호에 prop(delay_days/recovery_days) 표시. `web/lib/types.ts` `OptimizerOutput` 에 delay_days/recovery_days optional 추가 또는 부모에서 별도 prop.

### 검증 (Done 정의)
- 진단 1줄 숫자 결정론 일치(동일 입력 2회 동일), 한글 숫자·인시 절대수치 없음.
- 진단 2줄째(여건) non-empty, trade_frame 신호 포함.
- 유사 2건/만회방안 2건, 괄호값 = `wp_summary.delay_days`/`recovery_days`.
- LLM 스콥은 "여건 1줄 + 만회방안 텍스트"만 — 그 외 비결정성 의심([[feedback_dry_test]]).

---

## 데이터 Caveat (수정 범위 밖, 별도 이슈로 문서화)

1. **forecast 생산성 vs 이력/계획 basis 불일치** — `forecasts.today_productivity`(예: 글로벌유명 17.5 m2/인)가 Chroma `daily_activities` 이력(09-24 row 1.84)·`_group_baseline`(1.6)과 다른 qty basis. 그래서 per-person "정상 대비 %"가 1061% 같은 헛값. Part C 가 물량 페이스로 우회. 근본 SSOT 정합은 별도 작업.
2. **일부 `degradation_cases.work_content` narrative 깨짐** — 한국 C/R 등에서 저하 사례인데 "계획 물량 달성" 회복문구가 박힘. retrieve/atomizer 데이터 품질 이슈. (한국 C/R 은 wp_summary 13건에 없어 화면 표시 WP 는 아님)
3. **C/R 조성공사 = 마감 frame** — `data/trade_frames.json` 의 의도된 분류(클린룸 조성=마감성). 환각 아님.

---

## 검증 전략 (공통)

- 모든 산식 변경은 **실 daily_report JSON + 실 export 출력**으로 결정론 검증(동일 입력 2회 동일).
- LLM 부분(여건 1줄·만회방안)은 프롬프트로 락, 텍스트는 런마다 자연 변동 — 구조/가드(숫자 규칙·금지어) 충족 여부로 검증.
- 09-24 완주 run 을 기준 데이터로 사용(09-25 는 HIL 확정 후 동일 로직 발현).
