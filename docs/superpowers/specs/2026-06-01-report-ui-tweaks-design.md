# Reports UI 정밀화 + recovery_days SSOT 일치 설계

> 2026-06-01. CPIA reports 화면 3개 변경. A_Track @ 38616d2 기준. 데모 마감 2026-06-05.

**Goal:** reports 화면에서 (1) WP목록 라벨을 Work Area(FAB/CUB)로, (2) 공기단축 시나리오의 장문 AI 권고 카드를 숨겨 그래프+요약만, (3) WP목록 "공기 단축"과 §03 "최적화공기"를 AI 추천 기준으로 일치시킨다.

**Architecture:** 변경1·2는 FE 전용(재적재 0). 변경3은 BE(`view_builder.py`) 매칭·집계 수정 + 데모 날짜 jsonb 재생성(views-only, LLM 재호출 없음).

**Tech Stack:** Next.js(web/), Python LangGraph(pipeline/), PostgreSQL(AWS 43.200.85.209:5532), `backfill_daily_report_views_v2`.

---

## 실 데이터 근거 (9/24, is_mock=FALSE 최신 daily_reports)

- WP목록(`wp_summary_jsonb`) 13행, "공기 단축" 칼럼 합 = **−21일**. 그중 4행이 `—`(철근FAB·도장FAB·포장FAB·승강기CUB).
- §03 최적화공기(`scenarios_jsonb.site.base_p50.recovery_days`) = **−66일** = `sum(recovery_days for all 23 by_wp)` (`view_builder.py:1440`).
- 발산 66 vs 21 = ① 집합 차이(by_wp 23 = 옵티마이저 만회분석 전체, wp_summary 13 = 오늘 활동) ② 회사명 정규화(`남웅` vs `남웅건설`) ③ WA 매칭(`_match_forecast_by_company_l6`가 wa 무시, `view_builder.py:1414`).
- `66`은 시간 누적이 아니라 **WP 가로 합**(오늘 활동 없는 철골·C/R조성·방수·지붕·PC공사 등 ~10개 포함, 45일분).

## 결정 (사용자 승인)

| # | 결정 | 근거 |
|---|------|------|
| dev | 호스트용 make 타겟 `web`/`web2` 추가 (B_Track Docker `dev`/`dev2`와 공존) | `make dev2`(Docker)는 로컬 빈 DB → AWS 재적재 데이터 안 보임. 호스트 npm은 `.env.local`로 AWS를 봄. **(이미 적용·검증 완료)** |
| 1 | WP목록 "WP명" 칼럼 → "Work Area"(FAB/CUB). 공종 칼럼 유지. 목록만(상세카드·분포도 제외) | FE 파싱, 재적재 불필요 |
| 2 | §03 ForecastChart "AI 권고 카드"만 숨김(플래그, 기본 off). 그래프·KPI·3선표·LLM요약 유지 | 권고 정보는 §02 OptimizerResult에 잔존 → 손실 0 |
| 3 | **B**: §03 최적화공기 = "목록에 보이는 WP들의 공기단축 합". 4개 `—` 버그 수정. D+99 누적 지연 불변 | 사용자: "AI 추천(공기단축↔최적화공기)은 맞아야지, 누적(D+99)은 달라도 됨". 오늘 활동 없는 WP는 비노출 |

---

## 변경 1 — WP목록 라벨 (Work Area)

**Files:** `web/app/components/reports/WPSummaryTable.tsx`

- 헤더 `:37` `"WP명"` → `"Work Area"`.
- 셀 `:65` `row.wp_name` → Work Area 라벨. 파생: `row.wp_id.split("-")[0].toUpperCase()` (→ `FAB`/`CUB`). `wp_id`는 항상 `{wa}-{l6}-{company}` kebab(`view_builder.py:406`)이라 앞토큰이 wa. 빈/누락 시 fallback `row.wp_name.split("·")[1]?.trim()`.
- 공종 칼럼 `:67` `row.trade` 불변.
- 범위: `WPSummaryTable`만. `page.tsx:233`(상세카드 wp_name)·`QuadrantScatter`(툴팁)는 손대지 않음.
- 작은 헬퍼 `workAreaOf(wpId, wpName)` 를 컴포넌트 파일 상단 또는 `web/lib/` 에 둔다. (`ProductivityBarToggle.tsx:39`의 `split("·")[0]`은 별개 포맷이라 재사용 금지.)
- **재적재 0.**

## 변경 2 — §03 AI 권고 카드 숨김

**Files:** `web/app/components/charts/ForecastChart.tsx`, `web/app/(app)/reports/page.tsx`

- `ForecastChart.tsx:390-433`(AI 권고 `<ul>` 블록 + `:426-431` 캡션)을 `showAdvice` prop(`boolean`, 기본 `false`)으로 게이트: `{showAdvice && aiAdvice && aiAdvice.length > 0 && (...)}`.
- 유지: KPI헤더(`:108-172`), 그래프(`:194-297`), 3선표(`:300-374`), LLM요약(`:376-387`).
- `page.tsx`는 `showAdvice`를 넘기지 않음(기본 off) → 카드 미렌더. `aiAdvice` IIFE(`page.tsx:281-325`)는 보존(복구 가능, 무해).
- 코드 삭제 아님 → 추후 복구 용이.
- e2e: `reports.spec.ts:75`(`만회 시나리오 (AI)`)는 이미 stale(현 코드에 없음). 권고 카드를 단언하는 e2e 없음 → 숨김으로 깨질 유효 테스트 없음.
- **재적재 0.**

## 변경 3 — recovery_days SSOT 일치 (B)

**Files:** `pipeline/agents/optimizer/view_builder.py` (+ pipeline 테스트). FE 변경 없음(렌더값만 바뀜).

### 3a. 회사명 정규화
- `_wp_id_of`(`:398-406`)에 들어가는 company를 정준화하는 `_normalize_company()` 도입, advice 경로(`:1417`)와 wp_summary 경로 양쪽에 동일 적용 → `남웅` ≡ `남웅건설`. (정규화 규칙은 9/24 실 데이터로 plan에서 확정 — 단순 접미사 절단은 과병합 위험, master company 매핑 우선 검토.)

### 3b. WA 매칭
- `_match_forecast_by_company_l6`(`:1414`)가 wa를 무시 → advice가 엉뚱한 wa로 by_wp 키 생성(otis 승강기 fab/cub, 장평 포장 fab/cub). 매칭을 `(wa, company, l6)` 우선, 없을 때만 `(company, l6)` fallback으로. advice를 **오늘 활동이 일어난 wa**에 귀속.
- genuinely-no-advice 케이스(예: 도장 FAB 선보 — advice는 서림공영)는 plan에서 실 데이터로 판정. `—`가 정당하면 그대로 둔다(B는 "보이는 것 합"이라 무관).

### 3c. §03 site 집계 재정의 (핵심)
- 현재: `scenarios.site.base_p50.recovery_days = Σ(all 23 by_wp)` (`_site_slot`, `:1428-1446`).
- 변경: **site 집계를 `wp_summary`에 실제 표시되는 WP들의 recovery_days 합으로** (`:2182-2185`에서 wp_summary에 귀속된 값의 합). 구현상 by_wp 전체 합이 아니라 wp_summary 교집합 합. → §03 최적화공기 = WP목록 "공기 단축" 칼럼 합. tie-out by construction.
- 파급: ForecastChart의 AI 시나리오 곡선·3선표 완공예정일도 같은 site recovery 기반이라 함께 재계산(작은 단축폭으로 일관). FE 코드 변경 없음.
- D+99(`kpi.delay_days`, `:2177` s_curve 누적 기반)는 **불변**.

### 3d. 재생성
- advice는 `optimizer_advice` 테이블에 이미 존재 → `backfill_daily_report_views_v2.py --date <d> --with-summary` (views-only, **LLM 재호출 없음**)로 `wp_summary_jsonb`·`scenarios_jsonb` 재생성.
- 범위: **데모 날짜만**(9/24 + 시연 시 띄울 날짜). 전체 530일 불필요.
- plan에서 9/24 재생성 후 실측 검증: WP목록 공기단축 합 == §03 최적화공기, `—` 4개 처리 확인.

---

## 테스트 (TDD)

- **변경3 (BE)**: `pipeline/tests/optimizer/` — 픽스처(남웅/남웅건설 + fab/cub 스패닝 company + 오늘활동없는 behind WP) 입력 → ① wp_summary 각 행 recovery_days가 정규화·wa 매칭으로 정확, ② `scenarios.site.base_p50 == Σ(wp_summary recovery_days)`, ③ 오늘활동없는 WP는 site 합에 미포함. 실패 테스트 먼저.
- **변경1 (FE)**: vitest — `workAreaOf` 가 `fab-철근-남웅` → `FAB`, `cub-도장-선보` → `CUB`, 누락 시 fallback. + Playwright로 WPSummaryTable 헤더 "Work Area"·셀 FAB/CUB 렌더.
- **변경2 (FE)**: Playwright — §03에 "AI 권고" 헤더 미존재, 그래프·LLM요약 존재 확인.
- **검증 게이트**: 9/24 재생성 후 실 DOM에서 목록 공기단축 합 == §03 최적화공기 (Playwright `browser_evaluate`).

## Out of scope / 후속

- 전체 530일 재생성(데모 후 일괄).
- `kpi.expected_completion` median→정합(기존 known-minor).
- 상세카드·분포도 라벨 FAB/CUB 통일(이번엔 목록만).
- fab/cub 스패닝 company의 advice 분할(1 advice → 2 wa) 필요 시 — plan에서 실 데이터로 판정.
