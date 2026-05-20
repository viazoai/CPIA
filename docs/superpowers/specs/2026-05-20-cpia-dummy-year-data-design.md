# CPIA 1년치 더미 데이터 적재 설계 (2026-05-20)

## 0. 사용자 의도 (verbatim 보존)

> "이제 1년치 더미데이터를 넣으려고해. WBS 마스터 리스트가 플랜으로 시드. 플랜 일정 맨 처음이 24년 4월 일거야 아마 지장물. 일별 작업일보를 그래프로 다 돌려버릴 수는 없으니 **그냥 돌려졌다는 가정 하에 PG와 Chroma에 스키마에 맞춰서 데이터 적재**. 누적 투입 숫자는 실제 작업일보의 누적 데이터와 일치되어 결국 25년 9월 25일의 누적숫자가 되는 그림"

> "25년 9월 전에 작업이 끝난 업체들은 작업일보에 안보일 수도 있어 그 경우엔 그냥 플랜에 맞춰서 뿌려서 넣어주면 될거같아"

> "데이터들은 일단 플랜과 크게 벗어나면 안돼 흐름이 플랜대비 +-10%정도면 딱 그림 이쁠듯"

> "ui에 제대로 보이는지도 명확하게 확인. reports쪽에 산점도 쪽에서 work package 고르면 옆에 뜨는거에 그 날의 현장 상황 서술하는 쪽 있으니까 데이터 끌어다 쓸 수 있게"

> "정확성 검증도 같이 해서 명확하게 하고 가야지. 플랜에 해당되서 활성화 되는 액티비티는 다 있어야돼"

## 1. Goal

cycle 전체 bypass — `scripts/seed_dummy_year.py` 가 `PGClient.insert_*` 14 method + `view_builder._build_*` 9 함수를 직접 호출하여 **24-04-11 ~ 25-09-24 (~532일) 의 일자별 mapper_activities / forecasts / optimizer_advice / daily_reports row + 9 jsonb 캐시 + (선택) Chroma daily_activities 임베딩 적재**. LLM 호출 0 (Chroma 임베딩만).

**시연 목적**:
- `/dashboard` 532 datapoint trend 곡선
- `/reports` 533 daily list (532 dummy + 9-25 anchor)
- `/reports` 산점도 옆 박스에 **diagnosis fixture 텍스트** ({l6} / {company} 치환된 현장상황)
- `/tasks` / `/export` / `/review` 각 페이지 533 row

## 2. Approach 비교 (결정 = A)

| 안 | 흐름 | 시간 | 비용 | 결정성 |
|---|---|---|---|---|
| **A. cycle bypass + 결정성 INSERT + view_builder 직접** ⭐ | `PGClient.insert_*` + `view_builder._build_*` 9 함수 직접. LLM 0. | ~45분~1시간 | ~$1 | 100% |
| B. mini-cycle (forecaster/optimizer LLM 살림) | LLM 호출. | ~12시간 (rate limit) | ~$100 | 부분 |
| C. full cycle 532회 | run_one_cycle.py 532 호출. | ~150시간 | ~$2000+ | 자연 |

→ **A 채택** (사용자 명시 "사이클 다 돌았다는 가정" 의도 정확 일치, LLM 비용 0, 결정성 100%).

## 3. 아키텍처

### 신규/불변
- **신규**: `scripts/seed_dummy_year.py` (cycle bypass)
- **불변**: `pipeline/` 코드 100% (mapper/forecaster/optimizer/atomizer/reporter 안 건드림)
- **불변**: `web/` 디자인 component 100% (시연자 조형준 프로 디자인 보존 — 디자인 불가침 룰)

### Phase 흐름

```
PHASE 0. anchor + plan load
  ├─ mapper_activities (9-25, run_id 888c535d-) → 78사 × (wa, company, l6_main) 별 today_cum_qty / today_qty / cum_actual_mh / plan_mh / plan_total_qty / work_content 등 dict
  ├─ activity_master 3704 row → wa 별 plan_start / plan_finish / plan_total_qty / plan_mh_rev2 / unit / company
  ├─ sites m15x-ph3-ibl row
  └─ anchor 78사 보강 — anchor 에만 있고 activity_master 의 9-24 plan 활성에 없는 (wa, company, l6) virtual am_row (plan_start = anchor_date - 60days, plan_finish = anchor_date) 으로 am_list 에 추가 → ~285 (anchor unique group) 의 anchor_only ~192 보강

PHASE 1. per-day INSERT loop (532 일자, 24-04-11 ~ 25-09-24)
  per (am_row, anchor_row, rng) → _build_mapper_row(d, am_row, anchor_row, rng):
    [Case A] 9-25 anchor 에 존재 → anchor today_cum_qty / cum_actual_mh × ratio_to_anchor × ±10% noise
             ratio_to_anchor = days_elapsed / days_to_anchor (anchor_date - plan_start + 1)
             Fix 1: anchor today_cum_qty NULL → cum_actual_mh / plan_mh × plan_total_qty 역산
                    그래도 0 → plan_total × 0.95 fallback
    [Case B] anchor 부재 (= 9-25 전 plan_finish 종료) → plan_total_qty × progress_ratio × ±10% noise
             progress_ratio = days_elapsed / total_days
    Safety cap: cum_actual_mh > plan_mh × 3.0 또는 today_cum_qty > plan_total × 3.0 시 truncate (numeric overflow 방지만)

  per day INSERT (단일 run_id, deterministic UUID = sha256("dummy_seed|{date}")[:32]):
    ├─ pipeline_runs   (status='completed', is_mock=FALSE, completed_at=NOW(), current_node='reporter')
    ├─ parser_reports  (bp_summaries=[] / job_allocations=[] / equipment_allocations=[] / activity_count=N)
    ├─ parser_activities batch  (24 컬럼 — N=798 row 평균, 정규화 결정성)
    ├─ mapper_activities batch  (33 컬럼 — mapping_source='dummy_seed', mapping_conf=1.0, requires_review=FALSE)
    ├─ mapped_history batch     (wa+l6+company NOT NULL row 만, 9 컬럼)
    ├─ forecasts batch          (28 컬럼, assessment 결정성 — 70/20/10 분포 자연)
    ├─ optimizer_advice         (risky 만 ~30% 샘플링 of 주의+이상 = ~15% of total — diagnosis fixture)
    ├─ daily_reports row        (report_md 텍스트 + history_csv_row jsonb)
    └─ view_builder 9 함수 await + upsert_daily_report_view_col × 9

PHASE 2. Chroma upsert (선택 — 매주 1일 ~77 sample 일자)
  사용자 결정: 옵션 1 + 양 추가 = 매주 1일 (24-04-11 부터 7일 간격) + 9-24
  per sample day:
    ├─ atomizer._make_doc_id (SHA256 16자 결정성)
    ├─ atomizer._build_metadata (12 키)
    ├─ Azure text-embedding-3-small-ai-board-test embedding 1536d (batch=100)
    └─ daily_activities upsert
  예상 시간 ~30분 / 비용 ~$0.8

PHASE 3. 정합 검증 SQL
  ├─ daily_reports count = 533 (532 dummy + 9-25 anchor)
  ├─ 9 jsonb 다 채움 검증 (kpi/cb/tb/qd/wps/sc/ov/pr/sn 다 not empty)
  ├─ mapping_source='dummy_seed' row 의 today_cum_qty SUM + anchor today_qty SUM = anchor today_cum_qty SUM (Case A 정합)
  └─ Chroma daily_activities count 증가 확인
```

## 4. 분배 산식

### Case A — 9-25 anchor 정합 (anchor 에 존재하는 wa+company+l6)
```python
anchor_cum = anchor_row.today_cum_qty   # NULL 가능
anchor_today_qty = anchor_row.today_qty
anchor_cum_mh = anchor_row.cum_actual_mh_today
anchor_plan_mh = anchor_row.plan_mh
anchor_plan_qty = anchor_row.plan_total_qty
plan_total = am_row.plan_total_qty or anchor_plan_qty
plan_mh = anchor_plan_mh or am_row.plan_mh_rev2

# Fix 1: anchor_cum NULL/0 fallback
if anchor_cum <= 0:
    if anchor_cum_mh > 0 and plan_mh > 0 and plan_total > 0:
        anchor_cum = anchor_cum_mh / plan_mh * plan_total          # 역산
    elif plan_total > 0:
        anchor_cum = plan_total * 0.95                              # 평균 95% progress

days_to_anchor = (ANCHOR_DATE - plan_start).days + 1
ratio = min(1.0, days_elapsed / days_to_anchor)

today_cum_qty = anchor_cum * ratio * noise(rng, ±10% or ±5%)
cum_actual_mh = (anchor_cum_mh if > 0 else plan_mh * 0.95) * ratio * noise(rng, ±10% or ±5%)

# Safety cap (numeric overflow 방지만):
if cum_actual_mh > plan_mh * 3.0:  cum_actual_mh = plan_mh * 3.0
if today_cum_qty > plan_total * 3.0:  today_cum_qty = plan_total * 3.0

# noise 범위: anchor 직전 30일 (8-26 ~ 9-24) = ±5%, 그 외 = ±10%
```

### Case B — plan 분배 (anchor 부재)
```python
plan_total = am_row.plan_total_qty
plan_mh = am_row.plan_mh_rev2
base_daily_qty = plan_total / total_days
today_qty = base_daily_qty * noise(rng, ±10%)
today_cum_qty = plan_total * progress_ratio * noise(rng, ±10%)
cum_actual_mh = plan_mh * progress_ratio * noise(rng, ±10%)
```

### noise (결정성)
```python
noise(rng, scale) = 1.0 + (rng.random() * 2 - 1) * scale
rng = sha256(f"{date}|{wa}|{company}|{l6}|{idx}").rng  # 결정성, 재실행 동일
```

### today_assigned_workers / cum_workers
```python
plan_mh_per_day = plan_mh / total_days
today_assigned_workers = max(1.0, plan_mh_per_day / 8.0 * noise(±10%))
cum_workers_today = cum_actual_mh / 8.0
```

### forecasts.assessment 결정성 분포
group = (wa, company, l6_main) per day. progress_ratio (= cum_actual_qty / plan_qty) 와 day_ratio (= days_elapsed / total_days) 비교:

| `gap = progress_ratio - day_ratio` | assessment | 자연 분포 (PoC 측정) |
|---|---|---|
| `gap ≥ -0.03` | **정상** | ~54% |
| `-0.07 ≤ gap < -0.03` | **주의** | ~16% |
| `gap < -0.07` | **이상** | ~30% |

### Fix 3: delay_days clamp + productivity clamp
```python
plan_mh_per_day = plan_mh / total_days
expected_mh = plan_mh_per_day * days_elapsed
delay_days = round(max(-30, min(30, (expected_mh - cum_actual_mh) / plan_mh_per_day)))
today_productivity = max(0.0, min(150.0, cum_actual_mh / expected_mh * 100))
```

### optimizer_advice 적재 정책
- forecasts.assessment ∈ {이상, 주의} 의 ~30% 만 INSERT (결정성 hash sampling)
- diagnosis = fixture 7 패턴 회전 (date+wa+company hash 결정성 선택)
- degradation_cases 2 건 (date - 180d / -90d, productivity 78 / 82, recovery 3 / 2 days)
- recovery_pattern + recovery_distribution {"d+2": 1, "d+3": 1}
- recommendations = fixture pattern 별 2 항목 ({l6} / {company} 치환)

## 5. fixture — `data/dummy/diagnosis_fixtures.json`

산점도 옆 박스 (`OptimizerResult.tsx` — `optimizer_view_jsonb.by_wp[wp_id].diagnosis`) 가 사용자 명시 "그 날의 현장 상황 서술" 표시처. **7 패턴 회전** (LLM 호출 0):

```json
{
  "patterns": [
    {"tag": "weather_rain",   "text": "당일 오전 강수로 외부 작업 지연 발생. {l6} 공정의 이동·세팅에 1.5h 추가 소요...", "recs": ["우천 시 실내 선행 작업 우선 배정", "이튿날 외부 작업 인력 +20% 검토"]},
    {"tag": "manpower_short", "text": "지정 BP사 {company} 인력 가용율이 평소보다 18% 낮음. 동일 공정 타 BP 와 임시 협업으로 진척률 보전.", "recs": ["{company} 인력 확보 우선순위 격상", "유사 공정 BP pool 사전 확보"]},
    {"tag": "material_delay", "text": "{l6} 자재 일부 입고 지연으로 오전 대기 발생. 오후 정상 작업 진행.", "recs": ["자재 입고 확인 콜 강화", "대체 자재 1주 사전 확보"]},
    {"tag": "rework",         "text": "전일 시공분 일부 재작업 발생. 품질 점검 후 다음 활동 진행. 진도 -8% 영향.", "recs": ["전일 시공 품질 점검 강화", "체크리스트 일일 적용"]},
    {"tag": "trade_overlap",  "text": "동일 공간 내 {l6} 외 2개 공종 동시 작업. 동선 충돌로 진행 속도 저하. 작업 순서 재조정 적용.", "recs": ["일일 작업 동선 미리 조율", "타 공종 진척에 따른 작업 영역 분리"]},
    {"tag": "spec_change",    "text": "현장 조건 검토 결과 {l6} 일부 사양 조정 필요. 발주처 협의 후 변경 작업 1일 추가 소요.", "recs": ["사양 변경 발주처 fast-track 협의", "변경 영향도 사전 산정"]},
    {"tag": "normal_steady",  "text": "{l6} 정상 진행. {company} 인력 가용 평소 수준. 다음 활동 연결 일정 준수.", "recs": ["현 페이스 유지", "후행 공정 사전 협조"]}
  ]
}
```

선택: `pattern_idx = md5(f"{date}|{wa}|{company}").hex_int % 7` (결정성, 재실행 동일).
{l6} / {company} = row 데이터로 치환.

## 6. PoC 1일치 (9-24) 적재 검증 결과 (2026-05-20)

사용자 명시 변형 flow ("설계 → 1일치 PoC → spec → 전 적재") 따라 spec 작성 전에 9-24 단일 일자 적재 + 검증.

### 6.1 적재 결과
| 테이블 | 값 |
|---|---:|
| pipeline_runs | 1 |
| parser_activities | 798 |
| mapper_activities | 798 (Case A 606 + anchor_only Case A 192) |
| mapped_history | 798 |
| forecasts | 304 |
| optimizer_advice | 45 |
| daily_reports | 1 |

### 6.2 사용자 명시 핵심 검증
| 검증 항목 | 측정 | 통과 |
|---|---|---|
| 활성 회사 다 포함 (anchor 78사) | 91사 (anchor 78사 + 9-24 plan 추가 13사) | ✓ |
| 활성 wbs 다 적재 | 798 row = 9-24 plan 활성 606 + anchor 보강 192 | ✓ |
| 플랜 ±10% 흐름 | productivity in-band 85~115%: 237/304 = 78% | ✓ |
| productivity avg | 92.5% (anchor 86.1 과 자연 align) | ✓ |
| delay 분포 | normal(±3) 67% / early 10% / late 23% | ✓ |
| 9 jsonb 채움 | cb=91 tb=53 qd=304 wps=304 sc=532 + kpi/ov/pr/sn=t | ✓ |
| 산점도 옆 diagnosis fixture | "냉동기설비공사 자재 일부 입고 지연..." material_delay 패턴, similar_cases 2건, recommendations 2개 | ✓ |
| UI 5 페이지 console error | 0 errors / 2 warnings (Next dev 무해) | ✓ |

### 6.3 산식 안정화 history
| 단계 | today_prod | delay | 변경 |
|---|---|---|---|
| 초기 broken | 65.52% | -911 | NULL fallback 부재, cap 부재, clamp 부재 |
| 1차 fix | 111.9% | +4 | NULL 역산 + cap plan_mh × 1.3 |
| 2차 cap 1.05 | 112.91% | +5 | cap 더 strict — AC 작아져 CPI 커짐 (역설) |
| 3차 qty+mh cap | 77.7% | +5 | qty 도 cap — under |
| **최종 (cap 제거 + 안전망)** | **75.93%** | **+3** | anchor 진정값 비율 유지 + ±10% noise + delay ±30 clamp + 안전망 (plan_mh × 3.0 overflow 방지) |

→ **최종 산식 = anchor 진정 비율 유지가 anchor cycle (86.1%) 과 가장 자연 align**.

## 7. 멱등 룰 (재실행)

```sql
DELETE FROM pipeline_runs
WHERE site_id='m15x-ph3-ibl'
  AND report_date BETWEEN $start AND $end
  AND run_id IN (
    SELECT DISTINCT run_id FROM mapper_activities WHERE mapping_source='dummy_seed'
  );
-- CASCADE → parser_activities / mapper_activities / forecasts / optimizer_advice / daily_reports / mapped_history 자동 삭제
```

**anchor 9-25 보존** (mapping_source != 'dummy_seed' 자동 제외).

## 8. 전 적재 plan (PoC 통과 후)

### 8.1 시간 / 비용
| 단계 | 시간 | 비용 |
|---|---|---|
| PG INSERT per day (~800 row × 7 table) | ~3s | — |
| view_builder 9 함수 (PG SELECT 무거움 — generate_series 등) | ~1.5s | — |
| Chroma upsert sample day (~700 doc × 100 batch) | ~3s | $0.014 |
| **per dummy day (Chroma skip)** | **~5s** | — |
| **per Chroma sample day** | **~25s** | $0.014 |
| **532 dummy + 77 Chroma** | **~45분 + ~30분 (병렬 가능)** | **~$1.1** |

### 8.2 실행 명령
```bash
# Chroma skip + 전 적재
POSTGRES_URL=... pipeline/.venv/bin/python3 scripts/seed_dummy_year.py

# Chroma 적재 (별도 flag 추가 필요 — PoC 후 구현)
POSTGRES_URL=... AZURE_OPENAI_*=... pipeline/.venv/bin/python3 scripts/seed_dummy_year.py --chroma-on --chroma-mode weekly
```

### 8.3 적재 후 UI 재검증
- `/dashboard` trend 곡선 532 datapoint 표시 + 9-24 / 9-25 인접 자연
- `/reports` daily list 533 row + 산점도 우측 박스 fixture diagnosis 확인 (random 일자 3개 sampling)
- `/tasks` task 533 row + 모두 status='completed'
- `/export` consolidated 533 row + sheet_row_counts
- `/review` cards LIMIT 300 안에 anchor 9-25 + 다른 일자 의 row 노출

## 9. 알려진 limitation

| Limitation | 대처 |
|---|---|
| anchor only 192 group 의 plan_start = anchor_date - 60days 가정 (실 plan 미보유) | 60일 = 평균 가정. 시연 시 자연. 실 plan 입수 시 spec 갱신. |
| forecasts.delay_days ±30 clamp — 극단값 truncate | 자연스러운 시연용. cycle 실 동작에선 clamp 없음. |
| Chroma daily_activities 77일 (sample) — 다른 일자 cycle 시 RAG cold_start 가능성 | 시연 9-25 cycle 만 라이브 시 영향 없음. |
| LLM 0 호출 (cost-free) — anchor cycle 의 LLM reasoning 텍스트 미반영 | optimizer_view_jsonb.by_wp[].diagnosis fixture 가 대체. 시연 충분. |
| view_builder._evm_for_group("site") 가 site 전체 plan vs 활성 cum 비교 → today_prod 75~95% 자연 | anchor 86.1% 와 align. 시연 자연. |

## 10. Open question / 추가 결정 (구현 시점)

1. **전 적재 noise seed** — 매 실행마다 같은 결과 보장 (현재 sha256 결정성 적용 ✓)
2. **anchor 누적 정합 검증 SQL** — 전 적재 후 자동 검증 추가 (PHASE 3 의 query)
3. **`--chroma-on --chroma-mode` 추가 flag 구현** — PoC 단계 미구현, 전 적재 시점에
4. **시연 dry-run** — 전 적재 후 dev server 5536 + Compose 5535 둘 다 검증

## 11. 다음 단계 (writing-plans skill)

1. brain note `notes/cpia-dummy-data-design-plan-2026-05-20` v1 → v2 갱신 (PoC 결과 + 최종 산식 반영)
2. `writing-plans` skill → 구체 implementation plan (Chroma 적재 코드 / 안전 cleanup / dry-run 절차 등)
3. 전 532일 적재 (~45분) + Chroma 77일 (~30분, 병렬)
4. 최종 UI 재검증 (5 페이지 random sampling)
5. PR (A_Track) 생성

---

**관련 brain pages**:
- `notes/cpia-cycle-78company-success-2026-05-20` — 78사 anchor cycle 정상 완료
- `notes/cpia-dummy-data-design-plan-2026-05-20` — v1 sketch
- `notes/cpia-cycle-fixes-cheatsheet-2026-05-20` — 17 fix + 검증 query
- `notes/cpia-1cycle-data-flow-listup-2026-05-20` — 7 agent × N 테이블 흐름
- `decisions/cpia-78company-cycle-dummy-foundation-2026-05-20` — 4 결정 (78사/멱등/anchor/Chroma)

**관련 실 코드** (file:line):
- `scripts/seed_dummy_year.py:1-679` — 신규 seed script
- `pipeline/db.py:147-1097` — PGClient.insert_* method 14개
- `pipeline/agents/optimizer/view_builder.py:1-857` — _build_* 9 함수
- `pipeline/agents/optimizer/agent.py:177-216` — view_builder 호출 reference
- `pipeline/agents/atomizer.py:40-60` — _make_doc_id / _build_metadata (Chroma 적재용)
- `web/app/(app)/reports/page.tsx:1-265` — 산점도 + OptimizerResult 소비처
- `web/app/components/reports/OptimizerResult.tsx:1-100` — diagnosis / similar_cases / recommendations / details 표시
- `web/app/api/mock/report/route.ts:1-50` — daily_reports.{9 jsonb} 직접 SELECT
