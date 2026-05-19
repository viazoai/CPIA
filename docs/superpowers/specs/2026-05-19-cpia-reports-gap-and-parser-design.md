# CPIA reports gap + Parser LLM 강화 design

**작성**: 2026-05-19  
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

Parser 가 4 시트를 정확히 추출하지 못하면 cycle B 의 EVM 산식 source 가 비어있어 산출 불가. cycle A 가 cycle B 의 hard dependency.

### Cycle B — reports gap (cycle A 완료 후)

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
| **B7** | 1 회 비용 ~$3.0 (chunk 축소로 호출 수 증가) | trade-off 수용 — 정확성 우선 (PoC 데모 1 회 풀 실행) |

### 4.2 Prompt 재설계 전략 (B1/B2 시뮬레이션 근거)

**결정**: 모든 시트 LLM prompt 를 row 1:1 추출 + Python post-processing 패턴으로 통일.

**근거 (실 LLM 시뮬레이션, 추측 X)**:

`tmp/parser_prompt_simulate.py` (시트 1, 10 row) + `tmp/parser_prompt_simulate_b2.py` (시트 2, 10 row):

| 옵션 | 시트 1 추출 | 시트 2 추출 | 시트 1 output_t | 시트 2 output_t |
|---|---|---|---|---|
| **A** row 1:1 + post-pair | **10/10** | **10/10** | 1,676 | 1,464 |
| B 페어링 prompt + few-shot | 6/10 (정상 머지) | 10/10 | 1,347 | 2,034 |
| C A + few-shot | 10/10 (동일) | 10/10 (동일) | 1,821 | 1,470 |

본 cycle stderr log 의 10/10 (시트 1) + 30/39 (시트 2) 빈 list root cause = 옵션 B 같은 페어링 prompt. LLM 가 복잡한 row 간 로직 만나면 chunk 별 빈 list 로 도망. row 1:1 (옵션 A) 가 chunk 별 row 양식 변동성에 robust.

→ brain 보존: `benchmarks/2026-05-19-cpia-parser-bp-summaries-prompt`, `benchmarks/2026-05-19-cpia-parser-job-allocations-prompt`, `decisions/cpia-parser-prompt-strategy-2026-05-19`.

**일반화**: 복잡한 row 간 머지 / 페어링 / 변환을 LLM 에 위임하면 chunk 별 fragile. LLM = raw row → schema field 1:1, Python = row 간 deterministic 로직.

### 4.3 신규 파일 — `pipeline/agents/parser_post.py`

```python
def pair_bp_summaries(raw_rows: list[BPSummaryRaw]) -> list[BPSummary]:
    """시트 1 의 2-row pairing (BP 코드 row + 회사명 row 인접 머지)."""
    # is_bp_code + 다음 row.is_korean_company + 같은 zone/disc_abbrev → 머지
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

# chunk_size:
#   bp_summaries     40 → 15
#   job_allocations  40 → 15
#   equipment        40 → 15
#   activities       30 → 15
```

### 4.5 jsonschema validate

LLM 응답 list 안 각 item 을 jsonschema 로 validate. fail 시 retry 2회. 모든 retry 후 fail 한 item 만 drop + log.

### 4.6 적재 책임 분담

| Layer | 책임 |
|---|---|
| Parser LLM | raw row → schema field 1:1 (간단 변환만) |
| Parser post (parser_post.py) | row 간 pairing / marker filter / schema 검증 |
| Mapper | company normalize (㈜ / FAB·CUB / sub-context split) — Mapper 가 `mapper_activities.company` 에 정규화 값 저장 |

### 4.7 검증 전략

`pytest pipeline/tests/test_parser_llm.py`:

- sample xlsx (`docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`) → parse_daily_report_llm → expected row count assert
- expected (재실행 후):
  - bp_summaries ≈ **280~330** (379 non-empty 中 marker 제외)
  - job_allocations ≈ **1,400~1,500** (1,538 filter 통과 中 LLM drop 5% 이내)
  - equipment_allocations ≈ **800~900** (893 정상 BP사 中)
  - activities ≈ **1,150~1,200** (1,256 non-empty 中)

### 4.8 비용 + 시간

- 1 회 실행: chunk 수 ~250 (chunk_size=15) × 평균 $0.012/chunk ≈ **$3.0**
- dev 시간 추정: 1 ~ 1.5 일 (prompt 5 개 재작성 + parser_post.py 신설 + chunk/retry/validate 강화 + pytest)

---

## 5. Cycle B — reports gap (cycle A 완료 후)

### 5.1 § 01 "현장 생산성 진단" 산식 (확정)

PMI EVM (EV/PV/AC/SPI/CPI). 단일 표시 = CPI %.

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
    CPI = EV / AC × 100   ← "현장 생산성" 단일 %
```

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

**Impact 정규화** (확정 X1): `normMax = site 의 (plan_total_qty × plan_mh_rev2)` P90 percentile.

**Quadrant 임계값** (미결정 — impl 단계 결정): low_prod CPI < 80? 90? / high_impact >= 50? — 도메인 합의 필요.

**유사사례 자연어 변환** (미결정 — impl 단계): description 후보 Z1 `"{conditions} — {activities[0]}, 생산성 {productivity:.1f}"` vs Z2 `"{activities[0]} (조건: {conditions}, 인원 {assigned_workers}명)"`.

### 5.3 § 03 "공기 단축 시나리오" 산식

- planned curve: activity_master 균등분배 누계 → 100% 정규화
- actual curve: mapped_history 또는 daily_reports rows 의 SPI 시계열
- forecast curve: 현 추세 (today_productivity 기반 linear extrapolation) — `lib/diagnosis.ts` PRNG 제거 + 실 통계 input
- recovery curve: `optimizer_advice.recovery_pattern` (스키마 정합 `{date, recovery_days}` ← 현재 transforms.ts L568 의 `{date, value}` 가정 fix)

미결정 (impl 단계): forecast curve 의 단위 정합 (0..1 productivity vs 0..100 % 누적).

### 5.4 Optimizer view builder 흡수

Reporter rename (Exporter) 후 view builder 책임자 없음 → **Optimizer 가 cycle 끝에 흡수**.

```python
# pipeline/agents/optimizer/agent.py
async def optimize(...):
    advice_rows = [...]  # 기존
    for row in advice_rows: pg.insert_optimizer_advice(row)
    
    # 신규 흡수
    view = await build_optimizer_views(  # pipeline/optimizer/view_builder.py
        pg=pg, run_id=run_id, site_id=site_id, today=today,
        forecast=forecast, mapped=mapped, advice_rows=advice_rows,
    )
    await pg.upsert_daily_report_view(run_id, site_id, today, view)
    await pg.upsert_site_wbs_tree(site_id)
```

`pipeline/optimizer/view_builder.py` 신설 — 9 사이드카 함수:
- `_build_kpi` / `_build_contractor_bars` / `_build_trade_bars` / `_build_quadrant`
- `_build_wp_summary` / `_build_s_curve` / `_build_optimizer_view` / `_build_stage_progress`
- `_build_productivity_views` — § 01 EVM (today + by_contractor + by_l6 + by_wp snapshot)

90일 시계열은 FE BFF 가 daily_reports rows JOIN 으로 derive (Optimizer 가 산출 X).

### 5.5 PG migration

```sql
-- daily_reports 8 jsonb 컬럼 (run_id + site_id + report_date 1 row UPSERT)
ALTER TABLE daily_reports
  ADD COLUMN IF NOT EXISTS kpi_jsonb              JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS contractor_bars_jsonb  JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS trade_bars_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS quadrant_jsonb         JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS wp_summary_jsonb       JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS s_curve_jsonb          JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS optimizer_view_jsonb   JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS productivity_jsonb     JSONB DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS stage_progress_jsonb   JSONB DEFAULT '[]'::jsonb;

-- sites 의 site 단위 wbs tree (cycle 무관, 별도 trigger 또는 Optimizer 호출)
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS wbs_tree_jsonb         JSONB DEFAULT '{}'::jsonb;

-- mapper_activities 의 EVM input source (U1.A + U1.B)
ALTER TABLE mapper_activities
  ADD COLUMN IF NOT EXISTS cum_workers_today      DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_workers_yesterday  DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_actual_mh_today    DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS cum_actual_mh_yesterday DOUBLE PRECISION;
```

### 5.6 Mapper U1.A + U1.B

```python
# pipeline/agents/mapper.py
# U1.A: plan_mh propagate (이미 fetch 중인 l6_mh map 활용)
for a in mapped:
    if a["l6_main"]:
        a["plan_mh"] = l6_mh.get(a["l6_main"], 0)

# U1.B: cum_workers propagate + l6 prorate
#   parser_job_allocations.workers_cum_t (company 단위 SUM)
#   × (plan_mh_l6 / SUM plan_mh of that company)
for a in mapped:
    if a["l6_main"]:
        workers_l5 = job_alloc_company_sum.get(a["company"], 0)
        a["cum_workers_today"] = workers_l5 * (a["plan_mh"] / company_total_plan_mh[a["company"]])
        a["cum_actual_mh_today"] = a["cum_workers_today"] * 8
```

### 5.7 FE 4 mock route thin SELECT

`/api/mock/{report,dashboard,agent-tasks,review}/route.ts` — 산식 제거 + thin SELECT.

`/api/mock/consolidated` — raw pivot 만, 산식 없음 → **FE 직접 SELECT 유지** (BE 이전 의미 적음).

mock site 노출 정책: `daily` 1년 윈도우 SQL 에 `JOIN sites WHERE is_mock = FALSE` 추가 → m15x-ph3-ibl 만.

### 5.8 Backfill 스크립트

`scripts/backfill_daily_report_views.py` — 기존 9 cycle 일자에 view jsonb 채움. cycle A 후 1 회 실행.

### 5.9 변경 폭

| 작업 | LOC |
|---|---|
| PG migration | +35 |
| `pipeline/optimizer/view_builder.py` 신설 (9 builder) | +500 |
| `pipeline/agents/optimizer/agent.py` 확장 | +30 |
| `pipeline/agents/mapper.py` U1.A + U1.B | +60 |
| `pipeline/db.py` (upsert helpers) | +60 |
| `pipeline/agents/parser_llm.py` (5 prompts 재작성 + chunk/retry/validate) | +400 |
| `pipeline/agents/parser_post.py` 신설 | +200 |
| Backfill 스크립트 | +100 |
| FE 4 mock route thin 화 | **-800 / +120** |
| `web/lib/transforms.ts` 정리 | -400 |
| FE type 매핑 | +50 |
| pytest + vitest + Playwright | +300 |
| **net** | **약 -845 LOC** |

### 5.10 dev 시간 + 일정

| Cycle | dev 시간 | 의존성 |
|---|---|---|
| **A — Parser 강화** | 1 ~ 1.5 일 | 없음 (선행) |
| **B — view builder + FE** | 2 ~ 3 일 | A 완료 후 |
| **Backfill + 회귀 + Playwright** | 0.5 일 | B 후 |
| **총** | **3.5 ~ 5 일** | PoC D-17 (2026-06-05) 안 여유 |

---

## 6. 의존성 + 진행 순서

```
[Cycle A — Parser LLM 강화] ── 선행
   ├─ parser_llm.py 5 prompts 재설계 (row 1:1)
   ├─ parser_post.py 신설 (pairing / marker filter / normalize)
   ├─ chunk_size + retry + jsonschema validate
   └─ pytest expected row count assert
        ↓
   ★ 실 PoC 일보 재파싱 → PG 적재 완성 (~$3)
        ↓
[Cycle B — reports gap]
   ├─ PG migration (daily_reports +9 컬럼 / sites +1 / mapper_activities +4)
   ├─ Mapper U1.A (plan_mh) + U1.B (cum_workers prorate)
   ├─ Optimizer view_builder 흡수 (9 builder)
   ├─ Backfill 스크립트 (기존 9 cycle 일자)
   ├─ FE 4 mock route thin SELECT
   ├─ FE type 매핑 + transforms.ts 정리
   └─ pytest + vitest + Playwright UI 캡쳐
```

---

## 7. 결정 미정 (impl 단계 결정)

| # | 항목 | 옵션 |
|---|---|---|
| Y | § 02 quadrant 임계값 | low_prod CPI < 80 vs 90 / high_impact >= 50 vs 도메인 합의 |
| Z | § 02 유사사례 description 자연어 변환 | Z1 `{conditions} — {activities[0]}` vs Z2 `{activities[0]} (조건: ...)` |
| S | § 03 forecast curve 단위 정합 | productivity 0..1 vs 누적 0..100 % 변환 산식 |

---

## 8. brain 보존

- `[[benchmarks/2026-05-19-cpia-parser-bp-summaries-prompt]]` — B1 시뮬레이션 수치
- `[[benchmarks/2026-05-19-cpia-parser-job-allocations-prompt]]` — B2 시뮬레이션 수치
- `[[decisions/cpia-parser-prompt-strategy-2026-05-19]]` — LLM parser prompt 전략 일반화 결정

---

## 9. End-image 검증

cycle B 완료 후 `:5536/reports` 페이지 Playwright 캡쳐:

- § 01: 헤더 큰 CPI %, 90일 trend, 업체별 5~10 bar, 공종별 8~15 bar
- § 02: 4분면 점 ~50 + WP 표 + 진단/유사사례/권고/상세 6칸 다 채움
- § 03: planned/actual/forecast/recovery 4 곡선 모두 그어짐 + 자연어 narrative

end-image `cpia.zoai.uk/home` 풍성한 상태 매치.
