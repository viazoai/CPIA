# CPIA reports gap + Parser LLM 강화 design

**작성**: 2026-05-19  
**Revision**: r2 (2026-05-19 — reviewer ensemble 11 fix 반영: scope cut 3 + feasibility 4 + design-lens 4)  
**Scope**: reports 페이지 (§ 01 생산성 / § 02 리스크 대안 / § 03 시나리오) 의 빈 화면 root cause + 채움. Parser 강화는 선결 조건으로 한 doc 에 묶음.  
**End-image**: cpia.zoai.uk/home 같은 풍성한 상태.

---

## 1. 배경 + 사용자 보고

사용자 보고 — `https://localhost:5536/reports` 3 섹션 빈 상태:

- § 01 "현장 생산성 진단" — 업체별/공종별 bar 값 0
- § 02 "리스크 및 대안 검토" — 진단/유사사례/권고/상세 4 섹션 모두 빈 칸
- § 03 "공기 단축 시나리오" — 숫자는 보이지만 상세 검토 필요

End-image (`cpia.zoai.uk/home`) 는 모든 차트/카드 채워진 풍성한 상태.

---

## 2. Root cause 측정 결과 (실 PG, 추측 X)

### 2.1 cycle B 발견 (reports gap)

| 문제 | Root cause |
|---|---|
| § 01 업체별 생산성 0 | `mapper_activities.plan_mh` 전체 NULL (Mapper 가 채워 넣지 않음). `AVG(today_qty/plan_mh)` = NULL → pct=0 전파. |
| § 02 4 섹션 빈 | (1) daily 1년 윈도우에 mock site 일자 (DEMO_SITE 2025-09-27) 섞여 default selectedDate 가 빈 일자 → optRow undefined. (2) `details:[]` mock route line 337 hardcode — 영원히 빈 칸. |
| § 03 시나리오 합성 | `lib/diagnosis.ts` PRNG 합성 곡선. delayDays/recoveryDays 만 PG 실값. `_recoveryCurve` 의 `{date,value}` 스키마 가정 vs 실 PG `{date,recovery_days}` 불일치. |

### 2.2 cycle A 발견 (Parser 부실 — § 01 의 선결)

§ 01 의 EVM 산식은 `parser_job_allocations.workers_cum_t` (인원 누계) + `parser_activities.today_cum_qty` (시공 누계) source 의존. Parser 재실행 (`tmp/run_parser_capture.py`, 2026-05-19) stderr log 측정:

| 시트 | xlsx row | filter 통과 | LLM 추출 (재실행 1회) | 빈 list chunk |
|---|---|---|---|---|
| 1. 출력인원 | 379 non-empty | (filter X) | **0 row** ★ | **10/10 (100%)** |
| 2. 직종별 인원 | 15,501 | 1,538 | 118 row | 30/39 (77%) |
| 3. 장비현황 | 12,668 | 933 | 13 row (모두 marker 'M15 PH-X' noise) ★ | 5/24 빈, 23/24 small |
| 4. 물량 | 1,263 | (filter X) 1,256 | 532 row | 18/42 (43%), content_filter 4 |

추가 issue:
- xlsx 시트 1/3 의 **sub-section marker row** (M15 PH-X / FAB / CUB / BP04~BP10) 가 회사로 오인됨. ffill_cols 가 marker 를 다음 row 로 잘못 propagate.
- 시트 2 의 `_SYS_JOB_ALLOCATIONS` schema `manager_code` 가 Mm## (관리자) + Wk## (기능공) 혼재 — LLM 가 raw col 3 그대로 박지 못하고 schema 따름.
- 회사명 시트마다 표기 불일치 (`㈜세보엠이씨` / `세보엠이씨` / `세보`; `창원기전FAB`/`창원기전(고압)`).

---

## 3. Scope — 2 cycle, 한 PR

### Cycle A — Parser LLM 강화 (선행)

Parser 가 4 시트를 정확히 추출하지 못하면 cycle B 의 EVM 산식 source 가 비어있어 산출 불가. cycle A 가 cycle B 의 hard dependency. **단 partial 진입 기준 정의** (§ 6.3): cycle A 의 시트 1 + 시트 4 만 통과해도 cycle B 의 § 01 부분 산출 가능. 시트 2/3 fail 은 그 부분 UI 빈 칸 허용.

### Cycle B — reports gap (cycle A partial 통과 후)

EVM 산식 + Optimizer view builder 흡수 + daily_reports 8 jsonb 컬럼 적재 + FE 4 mock route thin SELECT.

---

## 4. Cycle A — Parser LLM 강화

### 4.1 fix item (B1~B7)

| # | Issue | Fix |
|---|---|---|
| **B1** | bp_summaries 10/10 chunk 빈 list (시트 1 379 row → PG 0) | prompt 재설계 — `_SYS_BP_SUMMARIES` 의 2-row pairing 제거. row 1:1 추출 + Python post-pairing |
| **B2** | job_allocations 30/39 chunk 빈 list + schema 모호 (Mm/Wk 혼재) | prompt 재설계 — row 1:1 추출 + `manager_code` → `disc_code` rename. Python post-process |
| **B3** | equipment 13 row 모두 marker noise ('M15 PH-X' 등) | (a) `_is_equipment_signal_row` filter 강화 — BP 패턴 검증 (`PH_X-\d+` 또는 한글 회사명) (b) row 1:1 추출 후 Python post-filter |
| **B4** | activities 18/42 chunk 빈 + content_filter 4 | chunk_size 30 → 15. 빈 list 응답 시 retry 2회 (현 1회) |
| **B5** | activities 일부 chunk output schema 위반 (str/dict 혼재 → Counter AttributeError) | jsonschema validate. validate fail 시 retry. 끝까지 fail 시 chunk skip + log |
| **B6** | content_filter 7 chunk (Azure 차단) | chunk 축소로 자동 해결 (B4 종속). finish_reason="content_filter" 시 강제 retry |
| **B7** | 비용 (chunk 축소로 호출 수 증가) | 1 회 baseline ~$3.0. **prompt 튜닝 반복 비용 상한 = $10** — 그 이상 fail 시 사용자 합의 후 진행 |

### 4.2 Prompt 재설계 전략 (B1/B2 시뮬레이션 근거)

**결정**: 모든 시트 LLM prompt 를 row 1:1 추출 + Python post-processing 패턴으로 통일.

**근거 (실 LLM 시뮬레이션, 추측 X)**:

`tmp/parser_prompt_simulate.py` (시트 1, 10 row) + `tmp/parser_prompt_simulate_b2.py` (시트 2, 10 row):

| 옵션 | 시트 1 추출 | 시트 2 추출 | 시트 1 output_t | 시트 2 output_t |
|---|---|---|---|---|
| **A** row 1:1 + post-pair | **10/10** | **10/10** | 1,676 | 1,464 |
| B 페어링 prompt + few-shot | 6/10 (정상 머지) | 10/10 | 1,347 | 2,034 |
| C A + few-shot | 10/10 (동일) | 10/10 (동일) | 1,821 | 1,470 |

**시뮬레이션 한계 명시 (feasibility watch 1)**: 본 측정은 첫 chunk 10 row 만. 본 cycle stderr 의 30/39 + 18/42 빈 list 의 chunk 별 row 양식 변동성은 외삽. 다른 일자 작업일보 양식 차이에 robust 한지 미검증. **§ 4.7 검증 단계에서 sample xlsx 2 일자 측정 후 expected range 보정**.

→ brain 보존: `benchmarks/2026-05-19-cpia-parser-bp-summaries-prompt`, `benchmarks/2026-05-19-cpia-parser-job-allocations-prompt`, `decisions/cpia-parser-prompt-strategy-2026-05-19`.

**일반화**: 복잡한 row 간 머지 / 페어링 / 변환을 LLM 에 위임하면 chunk 별 fragile. LLM = raw row → schema field 1:1, Python = row 간 deterministic 로직.

### 4.3 신규 파일 — `pipeline/agents/parser_post.py`

```python
def pair_bp_summaries(raw_rows: list[BPSummaryRaw]) -> list[BPSummary]:
    """시트 1 의 2-row pairing (BP 코드 row + 회사명 row 인접 머지)."""
    ...

def filter_marker_rows(raw_rows: list[dict], target_col: str = "company_or_bp") -> list[dict]:
    """marker row (M15 PH-X / FAB / CUB / BP04~BP10) drop."""
    MARKER_PATTERNS = {"M15 PH-X", "FAB", "CUB", "M15X", "M15 X"}
    BP_RE = re.compile(r"^PH_X-\d+$")
    return [r for r in raw_rows
            if r.get(target_col) and r[target_col] not in MARKER_PATTERNS
            and (BP_RE.match(r[target_col]) or has_korean(r[target_col]))]

def normalize_company(raw: str) -> str:
    """㈜prefix 제거 / FAB·CUB suffix 분리 / sub-context split."""
    ...  # Mapper 가 호출
```

### 4.4 chunk + retry 강화

`pipeline/agents/parser_llm.py`:

```python
def _llm_extract_sync(..., max_completion_tokens=16000, retries=2):
    # 빈 list 응답 시도 retry (현재는 truncate 만 retry)
    # content_filter 발생 시 강제 retry
    ...

# chunk_size: 모든 시트 30/40 → 15
```

### 4.5 jsonschema validate

LLM 응답 list 안 각 item 을 jsonschema 로 validate. fail 시 retry 2회. 모든 retry 후 fail 한 item 만 drop + log.

### 4.6 적재 책임 분담

| Layer | 책임 |
|---|---|
| Parser LLM | raw row → schema field 1:1 (간단 변환만) |
| Parser post (parser_post.py) | row 간 pairing / marker filter / schema 검증 |
| Mapper | company normalize (㈜ / FAB·CUB / sub-context split) |

### 4.7 검증 전략 (2 단계)

`pytest pipeline/tests/test_parser_llm.py`:

**Stage 1 (B1~B6 fix 직후)**: sample xlsx (`docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`) 1 회 LLM 호출 → expected row count 측정 + range 산출. expected range 는 fix 시점 가설치 이므로 **실측값을 expected range 로 보정** (initial expected ±20% 허용).

**Stage 2 (다른 일자 xlsx 1 회)**: 다른 일자 작업일보 (예: 2025-09-26 또는 2025-09-27) 로 동일 측정. 두 일자의 range overlap 확인 → 양식 변동성에 robust 한지 검증.

**최종 expected range (Stage 2 후)**:
- bp_summaries ≈ **280~330** (379 non-empty 中 marker 제외)
- job_allocations ≈ **1,400~1,500** (1,538 filter 통과 中 LLM drop 5% 이내)
- equipment_allocations ≈ **800~900** (893 정상 BP사 中)
- activities ≈ **1,150~1,200** (1,256 non-empty 中)

위 range 는 Stage 1 + Stage 2 측정 후 ±10% 범위로 좁힘. **pytest assertion 은 보정된 range 사용**.

### 4.8 비용 + 시간

- 1 회 baseline 실행: chunk 수 ~250 (chunk_size=15) × 평균 $0.012/chunk ≈ **$3.0**
- prompt 튜닝 반복 비용 상한: **$10** (B7) — 초과 시 사용자 합의 후 진행
- dev 시간 추정: 1.5 ~ 2 일 (prompt 5 개 재작성 + parser_post.py 신설 + chunk/retry/validate 강화 + pytest 2-stage)

---

## 5. Cycle B — reports gap (cycle A partial 통과 후)

### 5.1 § 01 "현장 생산성 진단" 산식 (확정)

PMI EVM (EV/PV/AC/SPI/CPI).

```
일자 d, group g (= site / company / l5 / l6 / wp):

(1) Plan 일별 균등분배 + 누계 (activity_master)
    cum_plan_qty_g = Σ activity_master(g):
                      plan_total_qty × min(1, max(0, (d - plan_start + 1) / span_days))
    cum_plan_mh_g  = 동일 방식 (plan_mh_rev2)

(2) Actual 누계 — 작업일보 누계 컬럼 그대로
    cum_workers_g  = parser_job_allocations(g 매칭, final_flag='O').workers_cum_t SUM
                     ※ l6/wp 단위 = company 전체 plan_mh 분모로 prorate (l5 표기 불일치 회피)
    cum_actual_mh_g  = cum_workers_g × 8h
    cum_actual_qty_g = parser_activities.today_cum_qty (g 매칭 SUM)

(3) EVM
    PV = cum_plan_mh_g
    AC = cum_actual_mh_g
    EV = (cum_actual_qty_g / Σ plan_total_qty_full_g) × Σ plan_mh_full_g
    SPI = EV / PV × 100   (시공 진척률)
    CPI = EV / AC × 100   (mh 효율)
```

**UI 라벨링 (design-lens 1 반영)**: 헤더 큰 % = CPI + 라벨 `"인 1시간당 시공 효율 (CPI)"`. 부가 chip 2 개:
- chip 1: `"SPI 시공 진척률 N%"` — 계획대비 시공량 진척
- chip 2: `"CPI mh 효율 N%"` — 동일 헤더값 chip 으로 재강조

두 chip 동등 표시 — SPI/CPI 의 의미 차이 (진척 vs 효율) 가 사용자에게 명시적으로 전달.

**실 PG 검증** (세보엠이씨 기계소화설비, 2025-09-25):
- plan_qty_full=77,774m / plan_mh_full=744,043MH
- cum_actual_qty=25,252m / cum_actual_mh=470,692MH (prorate)
- **SPI 32.47% / CPI 51.32%** — 진짜 비효율 시그널 잡힘.

### 5.2 § 02 "리스크 및 대안 검토" 매핑 (WP 단위)

| UI 섹션 | source | 산출 |
|---|---|---|
| 진단 🧠 | `optimizer_advice.diagnosis` ((company,l6) 매칭) | view_builder → `by_wp[wp_id].diagnosis` |
| 유사사례 📜 | `optimizer_advice.degradation_cases` | view_builder 자연어 변환 — `{date, description, outcome}` |
| 권고 💡 | `optimizer_advice.recommendations[].text` | view_builder → `recommendations` array |
| 상세 🗄️ (신규) | forecasts + advice 통계 | 6칸 (위험평가/진단대상/유사사례수/평균회복일/회복분포/일정영향) |

**`selectedWpId` 초기값 (design-lens 2)**: 첫 진입 시 우선순위:
1. `risk_level='이상'` + 가장 high `impact` WP
2. (없으면) `risk_level='주의'` + 가장 high impact WP
3. (없으면) `by_wp` dict 첫 row
4. (by_wp 자체 빈) `selectedWpId=null` — 4 섹션 placeholder `"WP 선택 필요 — 산점도에서 점 클릭"`

**4 섹션 NULL fallback (design-lens 5)**:
- `diagnosis` NULL → `"진단 데이터 없음 (Optimizer 미실행 또는 cold_start)"`
- `similar_cases` 빈 array → `"유사 사례 없음 — 데이터 누적 후 갱신"`
- `recommendations` 빈 array → `"권고 미산출 — cold_start"`
- `details` 6칸 각각의 value NULL → `"—"` 단일 dash 표시 (label 은 유지)

**Impact 정규화** (확정 X1): `normMax = site 의 (plan_total_qty × plan_mh_rev2)` P90 percentile.

**Quadrant 임계값 — default + impl 단계 조정**: 
- default Y: `low_prod = CPI < 80`, `high_impact = impact >= 50`
- impl 단계에서 도메인 합의 후 조정 가능. UI 가 default 로 첫 데모 + 사용자 피드백 후 fine-tune.

**유사사례 자연어 변환 default + impl 단계 조정**: 
- default Z: Z1 `"{conditions} — {activities[0]}, 생산성 {productivity:.1f}"`
- 예: `"우천,장비대기 — 기초공사 거푸집, 생산성 14.95"`
- outcome: `recovery.recovery_days != null` → `"{recovery_days}일 후 회복"`, else `"미회복"`

### 5.3 § 03 "공기 단축 시나리오" 산식

- planned curve: activity_master 균등분배 누계 → 100% 정규화
- actual curve: mapped_history 또는 daily_reports rows 의 SPI 시계열
- **forecast curve**: 현 추세 (today_productivity 기반 deterministic linear extrapolation). **`lib/diagnosis.ts` PRNG 제거 — 실 통계 input 만**.
- recovery curve: `optimizer_advice.recovery_pattern` (스키마 정합 `{date, recovery_days}` ← 현재 transforms.ts L568 의 `{date, value}` 가정 fix)

**Narrative 라벨링 (design-lens 4)**: forecast curve 는 deterministic linear extrapolation 이지 LLM 예측이 아님. UI 라벨:
- 기본 곡선 (forecast) = `"현 추세 연장"` (NOT "AI 예측")
- 회복 곡선 (recovery) = `"AI 회복 시나리오"` (Optimizer LLM 산출 — 정직)

이 라벨링으로 PoC 데모 challenge ("이게 AI 예측이냐") 회피 + 신뢰도 확보.

**Forecast curve 단위 정합 default S**: 
- `today_productivity` 은 0..1 비율 → `× 100%` 변환 후 누적 % 그래프
- daily 단위 = `today_productivity × cum_actual_qty 평균`

### 5.4 Optimizer view builder 흡수

Reporter rename (Exporter) 후 view builder 책임자 없음 → **Optimizer 가 cycle 끝에 흡수**.

```python
# pipeline/agents/optimizer/agent.py
async def optimize(...):
    advice_rows = [...]  # 기존
    for row in advice_rows: pg.insert_optimizer_advice(row)
    
    # 신규 흡수 — partial write 가드 (feasibility 3)
    try:
        view = await build_optimizer_views(
            pg=pg, run_id=run_id, site_id=site_id, today=today,
            forecast=forecast, mapped=mapped, advice_rows=advice_rows,
        )
        # 각 jsonb 컬럼 try/except 단위 UPSERT
        for jsonb_key, jsonb_val in view.items():
            try:
                await pg.upsert_daily_report_view_col(
                    run_id, site_id, today, jsonb_key, jsonb_val
                )
            except Exception as e:
                logger.warning(f"view jsonb '{jsonb_key}' upsert fail: {e}. partial write 유지.")
    except Exception as e:
        logger.error(f"build_optimizer_views fail entirely: {e}")
        # fallback: backfill 스크립트 (§ 5.8) 가 다음 cycle 또는 manual run 시 재시도
```

**`pipeline/optimizer/view_builder.py` 신설 — 8 사이드카 함수** (scope cut 1: `_build_stage_progress` 제거):
- `_build_kpi` / `_build_contractor_bars` / `_build_trade_bars` / `_build_quadrant`
- `_build_wp_summary` / `_build_s_curve` / `_build_optimizer_view`
- `_build_productivity_views` — § 01 EVM (today + by_contractor + by_l6 + by_wp snapshot)

90일 시계열은 FE BFF 가 daily_reports rows JOIN 으로 derive (Optimizer 가 산출 X).

**Retry / rollback 정책**:
- view 산출 fail → backfill 스크립트 (§ 5.8) 가 fallback (cron 또는 manual)
- jsonb 컬럼 별 partial write → 일부 view 만 표시되어도 UI 빈 칸 자동 fallback (§ 5.2 의 NULL fallback 적용)
- 명시적 rollback 없음 — 다음 cycle 가 UPSERT 로 덮어씀

### 5.5 PG migration (정정 — scope cut 반영)

```sql
-- daily_reports 8 jsonb 컬럼 (scope cut: stage_progress_jsonb 제거)
ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS kpi_jsonb              JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS contractor_bars_jsonb  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS trade_bars_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS quadrant_jsonb         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS wp_summary_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS s_curve_jsonb          JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS optimizer_view_jsonb   JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS productivity_jsonb     JSONB DEFAULT '{}'::jsonb;

-- (scope cut: sites.wbs_tree_jsonb 제거 — review 페이지는 별 cycle)

-- mapper_activities 의 EVM input source (scope cut: yesterday 2 컬럼 제거)
ALTER TABLE mapper_activities
  ADD COLUMN IF NOT EXISTS cum_workers_today      DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_actual_mh_today    DOUBLE PRECISION;
```

**Lock 안전성 (feasibility 2)**: PG 11+ 의 `ADD COLUMN ... DEFAULT` 은 metadata-only (rewrite 없음) → 본 cycle 마이그레이션 lock contention 없음.

### 5.6 Mapper U1.A + U1.B (prorate fallback 명시)

```python
# pipeline/agents/mapper.py
# U1.A: plan_mh propagate (이미 fetch 중인 l6_mh map 활용)
for a in mapped:
    if a["l6_main"]:
        a["plan_mh"] = l6_mh.get(a["l6_main"], 0)

# U1.B: cum_workers propagate + prorate
#   default: parser_job_allocations.workers_cum_t (company 단위 SUM)
#            × (plan_mh_l6 / SUM plan_mh of that company)
for a in mapped:
    if a["l6_main"]:
        workers_company = job_alloc_company_sum.get(a["company"], 0)
        company_total_mh = company_total_plan_mh.get(a["company"], 0)
        n_active_l6 = len(active_l6_for_company.get(a["company"], []))
        
        if company_total_mh > 0 and a["plan_mh"] > 0:
            # 정상 prorate
            a["cum_workers_today"] = workers_company * (a["plan_mh"] / company_total_mh)
            a["prorate_method"] = "plan_mh"
        elif n_active_l6 > 0:
            # fallback: l6 별 균등 분배
            a["cum_workers_today"] = workers_company / n_active_l6
            a["prorate_method"] = "uniform_fallback"
            logger.warning(f"prorate fallback for {a['company']}/{a['l6_main']} — plan_mh=0")
        else:
            a["cum_workers_today"] = 0
            a["prorate_method"] = "zero"
        
        a["cum_actual_mh_today"] = a["cum_workers_today"] * 8
```

**Prorate 가정 명시 (feasibility 5)**: `plan_mh 비율 ≠ 실 인원 분배 비율`. 한 회사가 다중 l6 동시 진행 시 — 예: 세보엠이씨가 기계소화 (plan_mh 큼) + 배관 (plan_mh 작음) 동시 진행, 오늘 배관에 70% 인원 → prorate 가 기계소화로 몰림.

**가이드 수준**: prorate 결과는 직관 가이드 (medium 신뢰도). CPI 51.32% 결과도 prorate 가정에 종속. UI 의 chip 옆 작은 i 아이콘 — hover 시 `"※ 인원이 plan_mh 비율로 분배되었다는 가정. l6 별 실측 인원 데이터 누적 후 정밀화 예정"`.

**l6 별 실측 인원 추출 cycle (별 trace)**: parser_job_allocations 의 disc_abbrev (l5) 가 아니라 l6 단위 인원 추출 — Parser LLM prompt 강화 + xlsx 양식 분석. 본 cycle 외.

### 5.7 FE 4 mock route thin SELECT (mock site UX 정의)

`/api/mock/{report,dashboard,agent-tasks,review}/route.ts` — 산식 제거 + thin SELECT.

`/api/mock/consolidated` — raw pivot 만, 산식 없음 → **FE 직접 SELECT 유지** (BE 이전 의미 적음).

**Mock site 정책 (design-lens 6)**:
- `daily` 1년 윈도우 SQL 에 `JOIN sites WHERE is_mock = FALSE` 추가 → m15x-ph3-ibl 만 reports/dashboard 의 daily 리스트에 표시.
- Dashboard 의 mock site 카드는 **회색 처리 + "preview" 라벨** 유지 (다른 현장 narrative 위해). 클릭 시 modal `"데이터 준비 중 — Parser 강화 cycle 완료 후 synthetic 데이터 적재 예정"`.
- 본 PR 완료 후 별 cycle (mock site synthetic fill) 로 다른 5 site 채움.

### 5.8 Backfill 스크립트

`scripts/backfill_daily_report_views.py` — 기존 9 cycle 일자에 view jsonb 채움. cycle A 후 1 회 실행. view 산출 실패 시 § 5.4 의 fallback 으로도 작동 (cron 가능).

### 5.9 변경 폭 (정정 — scope cut 3 반영)

| 작업 | LOC (정정) |
|---|---|
| PG migration | +25 (−10) |
| `pipeline/optimizer/view_builder.py` 8 builder (stage_progress 제외) | +440 (−60) |
| `pipeline/agents/optimizer/agent.py` 확장 (partial write 가드 포함) | +40 |
| `pipeline/agents/mapper.py` U1.A + U1.B (prorate fallback 포함) | +75 |
| `pipeline/db.py` (upsert helpers + 컬럼 단위 UPSERT) | +60 |
| `pipeline/agents/parser_llm.py` (5 prompts 재작성 + chunk/retry/validate) | +400 |
| `pipeline/agents/parser_post.py` 신설 | +200 |
| Backfill 스크립트 | +100 |
| FE 4 mock route thin 화 | **-800 / +120** |
| `web/lib/transforms.ts` 정리 | -400 |
| FE type 매핑 | +50 |
| pytest 2-stage + vitest + Playwright | +350 |
| **net** | **약 -900 LOC** |

### 5.10 dev 시간 + 일정

| Cycle | dev 시간 | 의존성 |
|---|---|---|
| **A — Parser 강화** | 1.5 ~ 2 일 | 없음 (선행) |
| **A 검증 2-stage** | 0.5 일 | A impl 후 |
| **B — view builder + FE** | 2 ~ 3 일 | A partial 통과 후 |
| **Backfill + 회귀 + Playwright** | 0.5 일 | B 후 |
| **총** | **4.5 ~ 6 일** | PoC D-17 (2026-06-05) 안 여유 |

---

## 6. 의존성 + 진행 순서

### 6.1 흐름

```
[Cycle A — Parser LLM 강화] ── 선행
   ├─ parser_llm.py 5 prompts 재설계 (row 1:1)
   ├─ parser_post.py 신설 (pairing / marker filter / normalize)
   ├─ chunk_size + retry + jsonschema validate
   └─ pytest Stage 1 (sample xlsx) → expected range 측정
        ↓
   ★ Stage 2 (다른 일자 xlsx 1회) — range 보정
        ↓
   ★ 실 PoC 일보 재파싱 → PG 적재 (~$3, 상한 $10)
        ↓
[Cycle B — reports gap]  ← cycle A partial 통과 후 (§ 6.3 partial 진입 기준)
   ├─ PG migration (daily_reports +8 컬럼 / mapper_activities +2)
   ├─ Mapper U1.A (plan_mh) + U1.B (cum_workers prorate + fallback)
   ├─ Optimizer view_builder 흡수 (8 builder + partial write 가드)
   ├─ Backfill 스크립트 (기존 9 cycle 일자)
   ├─ FE 4 mock route thin SELECT
   ├─ FE type 매핑 + transforms.ts 정리
   └─ pytest + vitest + Playwright UI 캡쳐
```

### 6.2 검증 보정 단계 (feasibility 4)

**Stage 1 — 본 일자 측정** (cycle A impl 직후):
- `pytest pipeline/tests/test_parser_llm.py::test_full_extraction` — sample xlsx 1 회 LLM 호출
- 실측 row count → initial expected range = 실측값 ±20%

**Stage 2 — 다른 일자 측정**:
- 다른 일자 xlsx (예: 2025-09-26 또는 2025-09-27 의 통합 작업일보) 1 회 LLM 호출
- 두 일자 row count overlap 확인
- 양식 변동성 robust → final expected range = 두 측정의 ±10% 범위

**최종 assertion** — Stage 2 후 보정된 range 만 pytest assertion. fail 시 cycle B 진입 보류.

### 6.3 Cycle A partial 진입 기준 (feasibility 6)

- **Full pass**: 4 시트 모두 expected range 통과 → cycle B 시작
- **Partial pass**: 시트 1 (bp_summaries) + 시트 4 (activities) 통과 + 시트 2/3 fail → cycle B § 01 부분 산출 (인원 prorate 의 시트 2 input 부족 → § 01 CPI 일부 NULL 허용. § 02/§ 03 진단/시나리오 그대로)
- **Block**: 시트 1 또는 시트 4 fail → cycle B 진입 보류, Parser 재튜닝

### 6.4 Prompt 튜닝 비용 상한 (B7)

cycle A 의 LLM 호출 누적 비용 상한 = **$10**. 초과 시 사용자 합의 후 진행:
- B1~B6 fix 후 Stage 1 측정 → fail 시 prompt 추가 튜닝
- 각 튜닝 cycle 마다 시뮬레이션 (~$0.15) + Stage 1 측정 (~$3)
- 3회 튜닝 안 통과 시 ($9.5 누적) 사용자 confirm

---

## 7. 결정 미정 — default 값 제공 + impl 단계 조정 가능

| # | 항목 | default | impl 단계 조정 |
|---|---|---|---|
| Y | § 02 quadrant 임계값 | low_prod CPI < 80 / high_impact >= 50 | 도메인 합의 후 fine-tune |
| Z | § 02 유사사례 description | Z1 `"{conditions} — {activities[0]}, 생산성 {productivity:.1f}"` | UI 검증 후 문구 조정 |
| S | § 03 forecast curve 단위 | `today_productivity × 100%` 변환 후 누적 % | 그래프 검증 후 단위 조정 |

본 PR 시 default 적용. PoC 데모 후 사용자 피드백 수렴 후 별 cycle 에서 fine-tune.

---

## 8. brain 보존

- `[[benchmarks/2026-05-19-cpia-parser-bp-summaries-prompt]]` — B1 시뮬레이션 수치
- `[[benchmarks/2026-05-19-cpia-parser-job-allocations-prompt]]` — B2 시뮬레이션 수치
- `[[decisions/cpia-parser-prompt-strategy-2026-05-19]]` — LLM parser prompt 전략 일반화 결정

---

## 9. End-image 검증 — 정량 기준 (design-lens 7)

cycle B 완료 후 `:5536/reports` 페이지 Playwright 캡쳐 + 정량 assertion:

| # | 검증 항목 | 정량 기준 |
|---|---|---|
| 1 | § 01 헤더 CPI % | 0% 가 아닌 실수값 (예: 51.32) 표시 + 색상 chip |
| 2 | § 01 90일 trend | line chart 그어짐 + 최소 7 개 datapoint (1주 이상) |
| 3 | § 01 업체별 bar | bar count ≥ 5 (PoC 3사 + plan 활성 회사) |
| 4 | § 01 공종별 bar | bar count ≥ 8 (PoC 활성 l6) |
| 5 | § 02 4분면 산점도 | 점 count ≥ 10 + 4 quadrant 모두 적어도 1 점 |
| 6 | § 02 WP 표 | row ≥ 10 + status 컬럼 색 표시 |
| 7 | § 02 4 섹션 | 4 섹션 모두 빈 칸 0 (NULL fallback 텍스트 OK) |
| 8 | § 02 상세 6칸 | 6 라벨 모두 표시 + value NULL → `"—"` |
| 9 | § 03 S-curve | planned/actual/forecast/recovery 4 곡선 모두 line 그어짐 |
| 10 | § 03 narrative | `"현 추세 연장"` + `"AI 회복 시나리오"` 라벨 표시 |

end-image `cpia.zoai.uk/home` 풍성한 상태 매치 — 위 10 정량 기준 통과 시 OK.
