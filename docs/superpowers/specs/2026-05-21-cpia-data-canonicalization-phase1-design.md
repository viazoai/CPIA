# CPIA 데이터 정합화 Phase 1 — 530일치 확장 + 산식 BE 통합

**작성일**: 2026-05-21
**시연 마감**: 2026-06-05 (D-15)
**Status**: design (brainstorming 완료, prototype 9-25 검증 OK)
**연관**: [[decisions/cpia-data-canonicalization-2026-05-21]] (gbrain)

---

## Goal

9-25 prototype 검증 완료한 정합화 정책을 **530일치 × 건축+토목 한정 (689 마스터 row + 8 업체 + 5 L6공종)** 확장 + `view_builder.py` 본 파이프라인 통합 + 임시 코드 제거. UI `/reports` 가 530일 전체에서 새 4단 산식 (인당/공종별/업체별/현장) 으로 정상 표시 + **RAG/atomizer 가독성 + WP cold_start 제거 + 인당 단위 직관 표시**.

**사용자 추가 요구 (2026-05-21 spec 검토 중)**:
1. atomizer 가 ChromaDB 에 적재하는 RAG 데이터 사람이 읽기 쉽게
2. WP 클릭 시 OptimizerResult 의 cold_start 케이스 없게 (ChromaDB 풍부화)
3. 인당 생산성 단위 직관 표시 (예: "3.2 ton/인" — 단순 "3.2" 가 % 인지 단위 무엇인지 모름)

## Architecture

```
┌─── PG (AWS 43.200.85.209:5532) ───────────────────────────────┐
│                                                                │
│  activity_master       — 마스터 (anchor). 갈아엎기 영구 적용  │
│  mapper_activities     — 일보. company 정규화 + L7.5 + 갈아엎기 │
│  daily_reports.jsonb   — 산식 결과 캐시 (530일치)             │
│  prototype_l7_5_resolved — 임시 (Phase 1 후 view 로 대체)     │
│  backup_20260521.*     — 9-25 prototype 진입 전 백업          │
│                                                                │
└────────────────────────────────────────────────────────────────┘
              ↑                                  ↓
         backfill 갱신                       Next.js BFF
   pipeline/agents/optimizer/             web/app/api/mock/report
        view_builder.py
   (새 산식 4단 통합)                      web/app/(app)/reports
                                          (기존 컴포넌트 그대로)
```

**Layer 책임**:
- **PG**: 모든 산식 결과 캐시 (`daily_reports.jsonb`), prototype 테이블 → view 로 대체
- **`view_builder.py` BE**: 새 4단 산식 + impact 정규화 + 마스터 daily 기반 today/workers 시뮬레이션
- **`/api/mock/report` BFF**: 9-25 필터 제거, 530일 전부 read
- **FE 컴포넌트**: 변경 없음 (같은 jsonb 컬럼)

## Components

### 1. `view_builder.py` 산식 통합 (`pipeline/agents/optimizer/view_builder.py`)

**기존 함수 (EVM 산식)**:
- `_build_productivity_views` / `_evm_for_group` / `_evm_by_group` — **신규 함수와 공존, 기본 산식 호출 교체**

**신규 함수**:
- `_build_productivity_views_v2(pg, run_id, site_id, today, mapped, master_summary)` — 새 4단 + impact 산식. dict 반환 (기존과 동일 시그니처).

**산식 (사용자 확정)**:
```python
# 1. 마스터 daily quota (같은 (site, company, l6, l7_5) row 합산)
total_days = (plan_finish - plan_start).days + 1
daily_qty_master = sum_plan_total_qty / total_days
daily_workers_master = max(1.0, sum_plan_mh_rev2 / total_days / 8.0)

# 2. today_qty / workers 시뮬레이션 (사용자 결정 — PLAN 기반 더미)
today_qty_sim = daily_qty_master * noise(0.85, 1.15)
workers_sim = max(1.0, daily_workers_master * noise(0.90, 1.10))

# 3. 인당 생산성
perperson = today_qty_sim / workers_sim
master_perperson = daily_qty_master / daily_workers_master

# 4. 공종별 (L7.5 단위) 생산성
productivity = perperson / master_perperson * 100  # 자연스럽게 100±15% 근처

# 5. 업체별 / 현장
company_wv_median = weighted_median(productivities, plan_mh_weights)
company_simple_mean = mean(productivities)
site_wv_median = weighted_median(company_wv_medians, sum_plan_mh_per_company)
site_simple_mean = mean(company_simple_means)

# 6. impact (Quadrant Y축)
impact_raw = max(0, 100 - productivity) * plan_mh
impact_normalized = impact_raw / max(impact_raw) * 100  # 0-100
```

**적용 조건**: `plan_start ≤ report_date ≤ plan_finish` 인 row 만. 작업기간 밖 row 는 skip.

**Plan 기간 밖 일자 정책 (reviewer issue #1 HIGH)**:
- 일자별 산식 적용 row 가 **0건** 이면 해당 `daily_reports` row 의 jsonb 컬럼들은 빈 객체 (`{}` / `[]`) 로 UPDATE.
- UI 측 (`web/app/(app)/reports/page.tsx`) 은 이미 빈 상태 처리 (Loading 표시 + EMPTY_OPTIMIZER fallback) — 추가 변경 X.
- backfill 결과 보고서에 "산식 적용 일자 N / 빈 일자 M / skip 비율 X%" 명시. **skip 비율 30% 초과 시 backfill 중단 + 사용자 컨펌** (이상 신호).

**Seed (reviewer issue #2 MODERATE)**:
- deterministic: `random.Random(int(date.toordinal()) ^ hash(l7_5_activity))`
- 같은 일자 + 같은 L7.5 → 항상 동일 today_qty/workers
- backfill 재실행 = 동일 결과 (UPDATE 시 noise 재계산하지만 값 같음)
- `test_backfill_idempotent` 가 두 번 실행 후 `daily_reports.kpi_jsonb` JSON 동일 확인 (byte-exact 비교)

### 2. backfill 스크립트 (`scripts/backfill_daily_report_views.py` 갱신)

**기존**: EVM 산식 기반 daily_reports.jsonb 백필.
**갱신**: `view_builder._build_productivity_views_v2` 호출. 530일 × 1 site 루프. 각 일자별 `daily_reports.kpi_jsonb` 등 6개 컬럼 덮어쓰기. `is_mock = FALSE` row 만.

**Idempotent**: 같은 일자 재실행 시 UPDATE 만 (INSERT 충돌 X).

### 3. company 정규화 + L7.5 매핑 영구화

**Prototype 산출물**:
- `data/company_normalize.json` (38 매핑) — 그대로 사용
- `prototype_l7_5_resolved` 테이블 (9-25, 207 row) — Phase 1 에선 **530일치로 확장 적재**

**Phase 1 확장**:
- `scripts/apply_company_normalize.py` — 9-25 한정 → 530일 전체 (UPDATE WHERE 절에서 report_date 조건 제거)
- `scripts/resolve_l7_5_prototype.py` — 9-25 한정 → 530일 전체. **단 plan 기간 안 row 만 임베딩** (Data Flow 와 일치, reviewer issue #5)
- `scripts/apply_l7_5_overwrite.py` — 9-25 한정 → 530일 전체 (UPDATE WHERE 절 조정)

**비용 예상 (reviewer issue #3 MODERATE)**:
- prototype 9-25 실측: work_content 89 unique + l7_5 171 unique = **260 임베딩 호출**, ~$0.01 (small 모델)
- 530일 확장 예상:
  - work_content: 일자별 평균 ~60 unique (9-25 89 * 변동성). 530 × 60 = ~32k 호출. 다만 같은 텍스트 dedup -> 실제 ~5k unique 추정
  - l7_5 후보: 마스터 변경 없음, 1회 임베딩 후 캐시 -> ~700 호출
  - 총 ~6k 호출 × small 모델 ($0.02/1k tokens) = **~$1 미만**
- **재실행 skip 로직**: 신규 테이블 `prototype_embedding_cache (text PK, embedding vector, created_at)` -> 같은 text 재호출 skip. backfill 중단 후 재실행 = 처음부터 X (cache hit).

### 4. mapped_history 정합화 (UNIQUE 충돌 처리)

**문제**: `(run_id, wa, l6_main, company)` UNIQUE. company 정규화 시 광건티엔씨 + 광건 동시 존재 → 충돌.

**해결**: 합산 + DELETE 트랜잭션
```python
# 충돌 row 검색
conflict = SELECT mh1.id AS src, mh2.id AS tgt, mh1.today_qty AS src_qty
           FROM mapped_history mh1
           JOIN mapped_history mh2 USING (run_id, wa, l6_main, site_id)
           WHERE mh1.company = '광건티엔씨' AND mh2.company = '광건' AND mh1.id != mh2.id

# tgt 에 합산 + src DELETE
for src, tgt, src_qty in conflicts:
    UPDATE mapped_history SET today_qty = COALESCE(today_qty,0) + src_qty WHERE id = tgt
    DELETE FROM mapped_history WHERE id = src

# 비충돌 row 일반 UPDATE
UPDATE mapped_history SET company = '광건' WHERE company = '광건티엔씨'
```

신규 스크립트: `scripts/apply_mapped_history_normalize.py`.

**합산 로그 (reviewer issue #4 MODERATE)**:
신규 테이블 `mapped_history_merge_log` 에 모든 합산 이력 기록:
```sql
CREATE TABLE mapped_history_merge_log (
  id bigserial PRIMARY KEY,
  src_id bigint NOT NULL,        -- 삭제된 row
  tgt_id bigint NOT NULL,        -- 합산받은 row
  run_id uuid NOT NULL,
  report_date date NOT NULL,
  site_id text NOT NULL,
  wa text,
  l6_main text,
  old_company text NOT NULL,     -- 정규화 전 (광건티엔씨)
  new_company text NOT NULL,     -- 정규화 후 (광건)
  merged_today_qty numeric,
  merged_at timestamptz DEFAULT now()
);
```
시연 후 history 분석 시 어떤 row 가 어떤 row 에 합산됐는지 정확 추적 가능. Rollback 시 reverse 가능.

### 5. 임시 코드 제거

| 위치 | 임시 코드 | 제거 후 |
|---|---|---|
| `web/app/api/mock/report/route.ts` | `AND pr.report_date = '2025-09-25'::date` | 제거 (530일 전체 read) |
| `scripts/compute_productivity_v2_proto.py` | clamp 150 + 별도 스크립트 | 폐기 (view_builder.py 통합 후) |
| `scripts/compute_productivity_v2_proto.py` | 9-25 hardcode | 폐기 |

### 6. Atomizer RAG 적재 형식 가독성 향상 (사용자 추가 요구)

**현황** (`pipeline/agents/atomizer.py`):
- `documents = [work_content]` (예: "Deck Plate", "계단 논슬립 미장작업") — 짧은 텍스트
- `metadatas` 12 필드 (date, company, l5_disc, l6_main, wa, unit, today_qty, assigned_workers 등) — l7_5_activity 누락

**문제**: Optimizer 가 ChromaDB RAG 검색 결과 사용 시 사람 읽기 어려움. UI 의 similar_cases 표시도 빈약.

**변경**:
- `_build_metadata` 추가 필드: `l7_5_activity` (Phase 1 의 mapper_activities.l7_5_activity), `perperson` (m3/인 산정값), `productivity_pct`, `daily_qty_master`, `total_days`
- `documents` 텍스트 변경 — 사람 가독 형식:
  ```
  [2025-09-25] 광건 · 수장공사 · 풍도벽체 설치
  시공량 15 m2 / 인원 265 명 → 인당 0.06 m2/인 (마스터 daily 16 m2/265명 대비 100%)
  조건: 정상
  ```
- ChromaDB upsert 시 같은 doc_id 재생성 (sha256 — 자동 dedup)

### 7. ChromaDB daily_activities 풍부화 (Phase 1 backfill 시 같이)

**현황**: ChromaDB daily_activities 에 산발적 history 적재 (mapper_activities 실시간 처리만). WP 클릭 시 forecaster 가 history 검색 → sample size 0 → cold_start.

**변경**:
- Phase 1 backfill (`view_builder._build_productivity_views_v2`) 시 같은 일자의 mapper_activities row 들을 ChromaDB daily_activities 에도 같이 upsert (Component 6 의 새 documents/metadata 형식)
- 530일 × 평균 ~60 unique work_content = ~32k row 적재 (dedup 후 ~5k)
- 각 (company, l6) 그룹마다 최소 5건 history 보장 — 부족하면 동일 (l6_main) 다른 company 의 history 도 augment (Augment 후 metadata.augmented=true 명시)

**비용**: 이미 임베딩 cache (Component 3) 활용 — 신규 호출 ~$1 미만.

### 8. 인당 생산성 단위 직관 표시 (사용자 추가 요구)

**현황**:
- UI 8건 hardcode "%" (BarChartH/QuadrantScatter/PerformanceTab/SiteOverviewCard/ProductivityTrendChart/WPSummaryTable/ReportDailyList)
- 사용자 보는 화면 어딘가에 "생산성 3.2" 가 % 인지 단위 무엇인지 모름 (특히 WP 클릭 시 OptimizerResult.details, similar_cases)

**변경 (BE — jsonb 에 perperson + unit 동시 적재)**:
- `kpi_jsonb` 신규 필드:
  - `productivity_perperson_today: 3.2`
  - `productivity_perperson_unit: "ton/인"` (마스터 unit + "/인")
- `contractor_bars` 각 item:
  - `perperson: 0.85, perperson_unit: "m2/인"` (해당 업체 wv_median 기준 perperson)
- `wp_summary` 각 row:
  - `perperson: 0.06, perperson_unit: "m2/인"`
- `quadrant` 각 row 동일
- Optimizer details 의 "value" 도 단위 명시 (예: "0.06 m2/인 (마스터 0.06 대비 100%)")

**변경 (FE — 컴포넌트 라벨)**:
디자인 불가침 룰 (markup/className 변경 X) 준수. 텍스트 라벨만 변경 OK (사용자 직접 요청).
- **표시 형식 확정**: `"98.9% (3.2 ton/인)"` — % 가 메인, perperson 이 보조 (reviewer issue #3)
- 8 컴포넌트의 hardcode `"%"` → `{row.display_label || `${value}%`}` (BE 가 `display_label` 미제공 시 기존 동작 유지 = 안전)
- BE 가 jsonb 의 모든 값에 `display_label` 동반 (kpi / contractor_bars / trade_bars / quadrant / wp_summary 각 row)

### 9. WP cold_start 케이스 제거 정책

**현황**: by_wp 에 cold_start (similar_cases: [], diagnosis: "cold_start") 다수. UI 우측 OptimizerResult 비어보임.

**목표 (C7 와 정합 — reviewer issue #4)**:
- C7 augmentation + 최소 5건 보장 → cold_start 비율 **<5%** 로 감소 (검증 가능)
- 극소수 잔여 cold_start 는 C9 의 fallback 라벨 표시

**구현 위치 (단일 — reviewer issue #2/#4)**:
- `pipeline/agents/forecaster.py` 의 history search 결과 분기에서 한 곳만 처리
- `view_builder` 는 forecaster 결과 그대로 사용 (cold_start 분기 X)

**변경**:
- `forecaster.py` 신규 함수 `_search_daily_activities_with_weight(...)`:
  ```python
  results = chroma.query(...)
  # augmented row 가중치 0.5 (reviewer issue #2)
  return [(r, 0.5 if r.metadata.get("augmented") else 1.0) for r in results]
  ```
- cold_start 분기 (history 0건 또는 가중치 합 < 3.0):
  - 기존: `diagnosis="cold_start", recommendations=[]`
  - 신규: `diagnosis="신규 작업 — 마스터 baseline 기준 권고"` + recommendations 1건 이상 (마스터 plan 기반 default — 예: "일일 quota {daily_qty} {unit} 기준 작업 진행. 인원 {daily_workers}명/일 권장.")

## Data Flow

```
        backfill 진입
              ↓
   ┌─ for date in 530일 (2024-04-11 ~ 2026-05-15) ─┐
   │                                                │
   │   1. activity_master 합산 (l7_5 단위)         │
   │      → plan_start/finish/qty/mh 가져옴        │
   │                                                │
   │   2. mapper_activities (date) row 가져옴      │
   │      WHERE l7_5_activity IS NOT NULL          │
   │        AND date BETWEEN plan_start AND plan_finish │
   │                                                │
   │   3. 각 row 마스터 daily × noise 산정         │
   │      → today_qty_sim, workers_sim            │
   │                                                │
   │   4. 산식 4단 + impact + perperson + unit_label │
   │                                                │
   │   4b. ChromaDB daily_activities upsert        │
   │      (가독성 documents + 풍부 metadata)       │
   │      augment (l6 동일 다른 company history)  │
   │                                                │
   │   4c. by_wp (Optimizer view) 산정             │
   │      forecaster history search (>=5건 보장)  │
   │      cold_start 분기 — "신규 작업" 라벨      │
   │                                                │
   │   5. daily_reports (date) jsonb 6개 UPDATE + │
   │      optimizer_view_jsonb (by_wp 풍부화)     │
   │      kpi, productivity, contractor_bars,     │
   │      trade_bars, quadrant, wp_summary        │
   │                                                │
   └───────────────────────────────────────────────┘
              ↓
       UI /reports (530일 dropdown)
              ↓
       각 일자 선택 시 정상 산식 표시
```

## Testing

### 단위 (`pipeline/tests/optimizer/test_view_builder_v2.py`)
- `test_daily_quota_from_master` — plan_total_qty=100, total_days=10 → daily=10
- `test_today_qty_simulation_noise` — seed 고정, 동일 결과
- `test_productivity_calc` — perperson / master_perperson × 100
- `test_skip_outside_plan_range` — 9-25 가 plan_finish 후 → skip
- `test_company_wv_median` — wv 가중 누적 50% 지점
- `test_impact_normalize` — 0-100 범위
- `test_display_label_format` — `"98.9% (3.2 ton/인)"` 형식 (C8)
- `test_cold_start_label_replaced` — 빈 history → "신규 작업 — 마스터 baseline 권고" 라벨 + recommendations 1건 이상 (C9)
- `test_atomizer_document_format` — 사람 가독 텍스트 형식 (C6)
- `test_atomizer_metadata_enrichment` — metadata 에 l7_5_activity + perperson + productivity_pct 필드 (C6, reviewer issue #7)
- `test_chroma_augmentation_marks_source` — augmented=true + augmented_from_company metadata (C7)
- `test_augmented_rows_lower_weight` — forecaster search 결과 augmented row 가중치 0.5 (C7+C9 정합, reviewer issue #2)
- `test_cold_start_ratio_under_5pct` — 530일 backfill 후 cold_start 비율 < 5% (C7 목표 검증, reviewer issue #4)

### 통합 (`pipeline/tests/test_backfill_daily_report_views.py`)
- `test_backfill_530_days_idempotent` — 2회 실행 후 `daily_reports.kpi_jsonb` JSON byte-exact 동일 (seed deterministic 검증)
- `test_no_unique_conflict` — mapped_history UNIQUE 위반 없음 + merge_log 적재 확인
- `test_skip_ratio_under_30pct` — 530일 중 산식 적용 row 0건 일자 비율 < 30% (reviewer issue #1)
- `test_empty_jsonb_for_outside_plan_dates` — plan 기간 밖 일자 jsonb 빈 객체 적재 + UI 측 처리

### 회귀 (수동)
- 사용자가 UI 5536 에서 3 일자 (9-25 anchor + 2024-12 임의 + 2026-05 임의) 검증
- 콘솔 에러 0
- KPI / bar / 4분면 / WP 표 모두 렌더링

## Migration / Rollback

### Migration 순서 (실행)
1. backup 확인 (`backup_20260521` 19테이블 존재 확인)
2. company 정규화 530일 적용 (`scripts/apply_company_normalize.py --all-dates`)
3. mapped_history UNIQUE 합산 처리 + merge_log 적재 (`scripts/apply_mapped_history_normalize.py`)
4. 임베딩 cache 테이블 생성 (`prototype_embedding_cache`)
5. L7.5 임베딩 재매핑 530일 (`scripts/resolve_l7_5_prototype.py --all-dates`) — cache 활용, plan 기간 안 row 만
6. mapper_activities 마스터 갈아엎기 (`scripts/apply_l7_5_overwrite.py --all-dates`)
7. view_builder.py 통합 + 신규 4 component (atomizer 가독성 / chroma 풍부화 / 단위 표시 / cold_start 라벨)
8. backfill 실행 (`scripts/backfill_daily_report_views.py --all-dates`) — daily_reports.jsonb + ChromaDB daily_activities 동시 적재
9. forecaster cold_start 분기 갱신 + by_wp 풍부화 검증
10. UI 컴포넌트 단위 라벨 변경 (8 hardcode → `display_label` props 사용)
11. 임시 코드 제거 (route.ts 필터 + compute_productivity_v2_proto.py 폐기)
12. UI 검증 3 일자 + WP 클릭 cold_start 0 건 확인 + 단위 표시 확인 + 사용자 컨펌
13. git commit + PR (A_Track → main 후보)

### Rollback
- 단순: PG 백업 복원 — `DROP TABLE public.X; CREATE TABLE public.X AS SELECT * FROM backup_20260521.X;` 19테이블 (10분 이내)
- 부분: 특정 일자만 `UPDATE daily_reports SET ... FROM backup_20260521.daily_reports WHERE id = ...`

## Decision Log (Phase 1 추가)

| # | 결정 | Why |
|---|---|---|
| P1-1 | 530일치 확장 우선, 5공종/더미/엑셀은 다음 사이클 | 사용자 명시 — "전체 일수 보고 흐름 OK 면 공종 확장" |
| P1-2 | 인원 = PLAN 기반 더미 (parser_worker_outputs 매핑 X) | 사용자 명시 — "더미 설계한거처럼" |
| P1-3 | today_qty 도 마스터 daily × noise 시뮬레이션 (실 일보 today_qty 보존 X) | 사용자 명시 — "시연 시점 데이터는 시뮬레이션 초점" |
| P1-4 | EVM 함수 보존 + 새 함수 추가 (호출만 교체) | 안전 — rollback 시 한 줄 |
| P1-5 | impact 정규화 0-100 (UI 호환) | QuadrantPoint.impact: number 0-100 (web/lib/types.ts) |
| P1-6 | clamp 150 제거 (마스터 daily 시뮬이라 자연 정상값) | prototype 9-25 검증 — 단위 미스매치 0건 |
| P1-7 | `prototype_l7_5_resolved` 테이블은 Phase 1 후 view 로 대체 | spec 단계 — `CREATE VIEW v_l7_5_resolved AS SELECT ...` |
| P1-8 | atomizer documents 사람 가독 형식 | 사용자 추가 요구 — Optimizer RAG 결과 UI 가독성 |
| P1-9 | ChromaDB 풍부화 + augmentation (l6 동일 다른 company history) | 사용자 추가 요구 — cold_start 자연 제거 |
| P1-10 | 인당 생산성 단위 표시 — BE 가 `display_label` 직접 생성 | UI 컴포넌트 최소 변경 + 디자인 불가침 |
| P1-11 | cold_start 라벨 변경 "신규 작업 — 마스터 baseline 권고" + 기본 recommendations | 시연 시 빈 OptimizerResult 0건 |

## Out of scope (다음 사이클)

| Phase | 작업 | 예상 spec |
|---|---|---|
| Phase 2 | 5공종 확장 (설비/전기/UT/제어/소방) | 2026-05-22~ |
| Phase 3 | 더미 5건 정합화 | Phase 2 후 |
| Phase 4 | 통합 작업일보 엑셀 | Phase 3 후 |
| 별도 | parser_worker_outputs 실 인원 재적재 | 시연 후 후속 (사용자 결정 — 안 함) |
| 별도 | forecaster recovery_days 산식 갱신 | impact 와 연동 시 |
| 별도 | precedence-kg Signal 3 연결 | 별 spec |
| 별도 | HIL Review anchor 462 시연 매크로 | 별 spec |

## Risks

| Risk | 영향 | 완화 |
|---|---|---|
| 530일 임베딩 호출 실패 (Azure rate limit) | backfill 중단 | batch 100 + 재시도 로직 + 결과 PG 저장 (재실행 시 skip) |
| mapped_history UNIQUE 합산 시 today_qty 데이터 손실 | 시연 후 history 분석 시 오차 | backup_20260521 보존 + spec 에 합산 로그 명시 |
| view_builder.py 통합 시 기존 forecaster/optimizer 영향 | downstream agent 깨짐 | EVM 함수 보존, 호출 위치만 교체. unit test 통과 보장 |
| 9-25 외 일자에서 plan 기간 밖 row 비율 큼 (산식 적용 row 적음) | UI 빈 일자 발생 가능 | backfill 전 sample 5 일자 확인 |
| 임시 코드 제거 후 데이터 섞임 재발 | 사용자 컨펌 단계 깨짐 | 임시 코드 제거 직전 530일 전체 backfill 검증 |
| ChromaDB 적재 시 doc_id 충돌 (같은 sha256) | 일부 row 적재 누락 | sha256 = date|company|l6|work_content — 가독성 documents 변경해도 hash 입력은 work_content 만 유지 (P1-8) → dedup 안전 |
| augmentation 후 forecaster 가 다른 company history 를 자기 거로 오인 | similar_cases 결과 부정확 | metadata.augmented=true + augmented_from_company 명시 → forecaster 가 가중치 낮춤 (예: 0.5) |
| UI 컴포넌트 단위 라벨 변경 시 디자인 불가침 룰 위반 우려 | 시연 reject 가능 | markup/className 변경 X — 텍스트 라벨만 (BE 가 `display_label` 생성, UI 는 그대로 표시). git diff className=0 검증 |

## 정의 완료 기준 (Definition of Done)

**자동 검증 (DoD — CI/test 통과 시 OK, reviewer issue #6)**:
- [ ] 530일 중 plan 기간 안 일자는 `daily_reports.kpi_jsonb.productivity_today` 가 0~150 범위 값 (skip 비율 < 30%)
- [ ] Plan 기간 밖 일자는 jsonb 빈 객체 (`{}` / `[]`)
- [ ] `view_builder.py` 단위 테스트 10건 PASS (기존 6 + 신규 4)
- [ ] 백필 idempotent 테스트 PASS (byte-exact 비교)
- [ ] mapped_history_merge_log 적재 + rollback 시나리오 1회 검증
- [ ] 임베딩 cache 테이블 적재 + 재실행 cache hit 검증
- [ ] ChromaDB daily_activities 530일 적재 + 각 (company, l6) 최소 5건 보장 (augment 포함, SQL 검증 query 통과)
- [ ] `test_cold_start_ratio_under_5pct` PASS (cold_start row 비율 < 5%)
- [ ] `test_atomizer_metadata_enrichment` PASS (metadata l7_5_activity + perperson + productivity_pct 필드)
- [ ] `test_augmented_rows_lower_weight` PASS (forecaster augmented 0.5 가중치)
- [ ] 모든 daily_reports.jsonb 의 productivity 관련 row 에 `display_label` 필드 채워짐 (SQL 검증)
- [ ] git diff `className` 변경 0 line (디자인 불가침 검증)
- [ ] 임시 코드 제거 (route.ts 필터 + compute_productivity_v2_proto.py 폐기, grep 검증)

**시연 체크리스트 (수동 — 사용자, reviewer issue #6)**:
- [ ] UI 5536 에서 3 일자 (9-25 + 2024-12 임의 + 2026-05 임의) 정상 렌더링 + 콘솔 에러 0
- [ ] atomizer documents 10건 읽어보기 (가독성 직관 확인)
- [ ] WP 클릭 시 OptimizerResult 다이얼로그 — cold_start 보이지 않거나, 보여도 "신규 작업 — 마스터 baseline 권고" 라벨 + recommendations 1건 이상 표시
- [ ] 인당 생산성 단위 표시 — KPI/bar/WP 표 모두 `"%(perperson unit/인)"` 형식
- [ ] 사용자 컨펌 ("OK 시연 진입")

**Git/PR**:
- [ ] git commit + PR (A_Track → main 후보) — 머지는 조형준 프로 결정
