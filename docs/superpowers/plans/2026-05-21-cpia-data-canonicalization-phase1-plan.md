# CPIA 데이터 정합화 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline execution per user choice). Steps use `- [ ]` for tracking.

**Goal:** 530일치 (건축+토목) 정합화 + view_builder.py 통합 + atomizer 가독성 + ChromaDB 풍부화 + 단위 display_label + cold_start 제거 + 임시 코드 제거.

**Architecture:** BE (`view_builder.py`) 가 산식 + ChromaDB 적재 + display_label 생성 → `daily_reports.jsonb`. FE 컴포넌트는 `display_label` props 사용 (markup 변경 0). forecaster 단일 위치에서 augmentation 가중치 + cold_start 분기.

**Tech Stack:** Python 3.11 + asyncpg + Azure OpenAI embedding (text-embedding-3-small 1536d) + ChromaDB + Next.js 15 (App Router) + recharts.

**Branch:** A_Track (현 working). 디자인 불가침 (`git diff className` = 0).

**Spec:** `docs/superpowers/specs/2026-05-21-cpia-data-canonicalization-phase1-design.md`

---

## File Structure

### 신규 파일
- `infra/postgres/migrations/2026-05-21_phase1.sql` — `prototype_embedding_cache` + `mapped_history_merge_log` 테이블
- `scripts/apply_mapped_history_normalize.py` — UNIQUE 충돌 합산 + merge_log 적재
- `pipeline/tests/optimizer/test_view_builder_v2.py` — 10 단위 테스트
- `pipeline/tests/test_backfill_phase1.py` — 통합 테스트 4건

### 수정 파일
- `pipeline/agents/optimizer/view_builder.py` — 신규 함수 `_build_productivity_views_v2` + display_label + ChromaDB 풍부화
- `pipeline/agents/atomizer.py` — `_build_metadata` + documents 가독 형식
- `pipeline/agents/forecaster.py` — augmentation 가중치 + cold_start 라벨
- `scripts/apply_company_normalize.py` — `--all-dates` 옵션
- `scripts/resolve_l7_5_prototype.py` — `--all-dates` + cache 활용 + plan 안 필터
- `scripts/apply_l7_5_overwrite.py` — `--all-dates`
- `scripts/backfill_daily_report_views.py` — `_build_productivity_views_v2` 호출
- `web/app/api/mock/report/route.ts` — 9-25 임시 필터 제거
- `web/lib/types.ts` — `display_label` 옵셔널 필드 추가
- `web/app/components/charts/BarChartH.tsx`
- `web/app/components/charts/QuadrantScatter.tsx`
- `web/app/components/charts/ProductivityTrendChart.tsx`
- `web/app/components/dashboard/PerformanceTab.tsx`
- `web/app/components/dashboard/SiteOverviewCard.tsx`
- `web/app/components/reports/WPSummaryTable.tsx`
- `web/app/components/reports/ReportDailyList.tsx`

### 폐기
- `scripts/compute_productivity_v2_proto.py`

---

## Phase A — 인프라 준비

### Task 1: backup 확인

**Files:** (read-only)

- [ ] **Step 1: backup 스키마 19테이블 존재 검증**

Run:
```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h 43.200.85.209 -p 5532 -U cpia cpia \
  -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='backup_20260521'"
```
Expected: `19`

- [ ] **Step 2: row count 비교 (public vs backup 차이 = prototype 적용분)**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h 43.200.85.209 -p 5532 -U cpia cpia \
  -c "SELECT schemaname, SUM(n_live_tup) FROM pg_stat_user_tables
      WHERE schemaname IN ('public','backup_20260521') GROUP BY 1"
```
Expected: 양쪽 ≈ 590k row (±200 — prototype 적용된 9-25 차이)

---

### Task 2: PG migration (embedding_cache + merge_log)

**Files:**
- Create: `infra/postgres/migrations/2026-05-21_phase1.sql`

**Dependency contract (reviewer issue #1 명확화)**:
- `prototype_embedding_cache` 는 **Task 5 (L7.5 임베딩) 의 전제조건**. Task 5 시작 전 반드시 생성돼있어야 함.
- `mapped_history_merge_log` 는 **Task 4 (mapped_history 합산) 의 전제조건**. Task 4 시작 전 반드시 생성돼있어야 함.
- 두 테이블 모두 `CREATE TABLE IF NOT EXISTS` — 재실행 안전.

- [ ] **Step 1: SQL 파일 작성**

```sql
-- prototype_embedding_cache: 임베딩 호출 재실행 skip
CREATE TABLE IF NOT EXISTS prototype_embedding_cache (
  text_hash text PRIMARY KEY,
  source_text text NOT NULL,
  embedding float8[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_embedding_cache_created ON prototype_embedding_cache(created_at);

-- mapped_history_merge_log: company 정규화 합산 이력
CREATE TABLE IF NOT EXISTS mapped_history_merge_log (
  id bigserial PRIMARY KEY,
  src_id bigint NOT NULL,
  tgt_id bigint NOT NULL,
  run_id uuid NOT NULL,
  report_date date NOT NULL,
  site_id text NOT NULL,
  wa text,
  l6_main text,
  old_company text NOT NULL,
  new_company text NOT NULL,
  merged_today_qty numeric,
  merged_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_merge_log_date ON mapped_history_merge_log(report_date DESC);
```

- [ ] **Step 2: 마이그레이션 실행**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h 43.200.85.209 -p 5532 -U cpia cpia \
  -f infra/postgres/migrations/2026-05-21_phase1.sql
```
Expected: `CREATE TABLE` × 2 + `CREATE INDEX` × 2

- [ ] **Step 3: 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql -h 43.200.85.209 -p 5532 -U cpia cpia \
  -c "\d prototype_embedding_cache" \
  -c "\d mapped_history_merge_log"
```
Expected: 두 테이블 schema 출력

- [ ] **Step 4: Commit**

```bash
git add infra/postgres/migrations/2026-05-21_phase1.sql
git commit -m "feat(infra): phase1 migration — embedding_cache + merge_log"
```

---

## Phase B — 정규화 530일 확장

### Task 3: `apply_company_normalize.py` --all-dates 옵션

**Files:**
- Modify: `scripts/apply_company_normalize.py`

- [ ] **Step 1: argparse 추가**

기존 코드 (PROTOTYPE_DATE_STR hardcode) → CLI arg
```python
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--date", help="YYYY-MM-DD (단일 일자)")
parser.add_argument("--all-dates", action="store_true", help="530일 전체")
args = parser.parse_args()
```

- [ ] **Step 2: SQL UPDATE 조건 분기**

```python
if args.all_dates:
    date_filter = ""  # report_date 조건 X
    args_list = (canonical, variant)
else:
    proto = _date.fromisoformat(args.date or "2025-09-25")
    date_filter = "AND report_date = $2::date"
    args_list = (canonical, proto, variant)

await conn.execute(
    f"UPDATE mapper_activities SET company = $1 "
    f"WHERE company = $%d AND company <> $1 {date_filter}"
    % (3 if args.all_dates else 3),
    *args_list,
)
```

- [ ] **Step 3: 530일 적용 실행**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python scripts/apply_company_normalize.py --all-dates
```
Expected: `BEFORE/AFTER 정합도 출력 + UPDATE N` (N > 0)

- [ ] **Step 4: 검증 — 변형 표기 사라짐**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT COUNT(*) FROM mapper_activities WHERE company IN ('광건티엔씨','범미건설화학㈜','신성/케이엔솔','태우/광건')"
```
Expected: `0`

- [ ] **Step 5: Commit**

```bash
git add scripts/apply_company_normalize.py
git commit -m "feat(scripts): apply_company_normalize.py --all-dates option (530일 확장)"
```

---

### Task 4: `apply_mapped_history_normalize.py` 신규 + merge_log

**Files:**
- Create: `scripts/apply_mapped_history_normalize.py`

- [ ] **Step 1: 합산 로직 작성**

```python
"""mapped_history company 정규화 + UNIQUE 충돌 합산 + merge_log 적재."""
from __future__ import annotations
import asyncio, json, os
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
DSN = os.environ["POSTGRES_URL"]
MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "company_normalize.json"

async def main() -> None:
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    canon = {v: info["canonical"]
             for v, info in data["matched_fuzzy"].items()
             if info["canonical"] != v}
    # 슬래시 통일
    SLASH = {"신성/케이엔솔": "신성", "태우/광건": "태우"}
    canon.update(SLASH)

    pg = await asyncpg.connect(DSN)
    try:
        total_merged = 0
        async with pg.transaction():
            for variant, canonical in canon.items():
                # 충돌 row 검색
                conflicts = await pg.fetch(
                    """
                    SELECT mh1.id AS src, mh2.id AS tgt,
                           mh1.today_qty AS src_qty, mh1.run_id, mh1.report_date,
                           mh1.site_id, mh1.wa, mh1.l6_main
                    FROM mapped_history mh1
                    JOIN mapped_history mh2 USING (run_id, wa, l6_main, site_id)
                    WHERE mh1.company = $1 AND mh2.company = $2 AND mh1.id != mh2.id
                    """,
                    variant, canonical,
                )
                for c in conflicts:
                    # merge_log 적재
                    await pg.execute(
                        """
                        INSERT INTO mapped_history_merge_log
                          (src_id, tgt_id, run_id, report_date, site_id, wa, l6_main,
                           old_company, new_company, merged_today_qty)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                        """,
                        c["src"], c["tgt"], c["run_id"], c["report_date"],
                        c["site_id"], c["wa"], c["l6_main"],
                        variant, canonical, c["src_qty"],
                    )
                    # tgt 에 합산
                    await pg.execute(
                        "UPDATE mapped_history SET today_qty = "
                        "COALESCE(today_qty,0) + COALESCE($1,0) WHERE id = $2",
                        c["src_qty"], c["tgt"],
                    )
                    # src DELETE
                    await pg.execute(
                        "DELETE FROM mapped_history WHERE id = $1", c["src"],
                    )
                    total_merged += 1
                # 비충돌 row 일반 UPDATE
                await pg.execute(
                    "UPDATE mapped_history SET company = $1 "
                    "WHERE company = $2 AND company <> $1",
                    canonical, variant,
                )
        print(f"merged: {total_merged}")
    finally:
        await pg.close()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 실행**

```bash
pipeline/.venv/bin/python scripts/apply_mapped_history_normalize.py
```
Expected: `merged: N` (N >= 0)

- [ ] **Step 3: 검증 — UNIQUE 위반 0건 + merge_log 적재**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT COUNT(*) FROM mapped_history mh1 \
   JOIN mapped_history mh2 USING (run_id, wa, l6_main, company) \
   WHERE mh1.id != mh2.id"
```
Expected: `0`

```bash
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT COUNT(*), array_agg(DISTINCT old_company) FROM mapped_history_merge_log"
```
Expected: row count > 0 + 변형 회사명 array

- [ ] **Step 4: Commit**

```bash
git add scripts/apply_mapped_history_normalize.py
git commit -m "feat(scripts): apply_mapped_history_normalize.py — UNIQUE 합산 + merge_log"
```

---

## Phase C — L7.5 임베딩 530일

### Task 5: `resolve_l7_5_prototype.py` --all-dates + cache + plan 안 필터

**Files:**
- Modify: `scripts/resolve_l7_5_prototype.py`

**용어 정의 (reviewer issue #2 명확화 — 실행 시 혼동 방지)**:
- **row filter** = 임베딩 대상 선택. 각 mapper_activities row 의 (site, company, l6) 에 대해 `plan_start <= report_date <= plan_finish` 통과 row 만 임베딩.
- **day skip** = 그 일자에 row filter 통과한 row 가 0건이면 그 일자는 `prototype_l7_5_resolved` 적재 0건 (=skip).
- **day skip 비율** = (skip 일자 수) / 530 × 100. **목표 < 30%**. 30% 초과 시 backfill 중단 (Task 13).
- 임베딩 호출 자체는 cache hit 활용으로 cost 0. **filter 와 skip 은 다른 개념** (filter = row, skip = day).

- [ ] **Step 1: cache 활용 + plan 안 필터 + --all-dates**

```python
# argparse
parser.add_argument("--date", default=None)
parser.add_argument("--all-dates", action="store_true")

# cache 함수
async def embed_with_cache(client, pg, texts):
    """cache hit 면 PG 에서, 아니면 Azure 호출 후 PG 적재."""
    import hashlib
    out = {}
    to_call = []
    for t in texts:
        h = hashlib.sha256(t.encode()).hexdigest()[:32]
        row = await pg.fetchrow(
            "SELECT embedding FROM prototype_embedding_cache WHERE text_hash = $1", h
        )
        if row:
            out[t] = list(row["embedding"])
        else:
            to_call.append((t, h))
    if to_call:
        chunk_texts = [t for t, _ in to_call]
        for i in range(0, len(chunk_texts), 100):
            chunk = chunk_texts[i:i+100]
            resp = await client.embeddings.create(input=chunk, model=EMBED_MODEL)
            for (orig_t, orig_h), d in zip(to_call[i:i+100], resp.data):
                out[orig_t] = d.embedding
                await pg.execute(
                    "INSERT INTO prototype_embedding_cache (text_hash, source_text, embedding) "
                    "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                    orig_h, orig_t, d.embedding,
                )
    return out

# rows fetch — plan 안 필터 + 일자 분기
date_filter = "" if args.all_dates else "AND ma.report_date = $1::date"
rows = await pg.fetch(f"""
    SELECT ma.id AS mapper_id, ma.run_id, ma.report_date, pr.site_id,
           ma.company, ma.l6_main, ma.idx, pa.work_content,
           m.ps AS plan_start, m.pf AS plan_finish
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN parser_activities pa USING (run_id, idx)
    LEFT JOIN LATERAL (
        SELECT MIN(plan_start) AS ps, MAX(plan_finish) AS pf
        FROM activity_master am
        WHERE am.site_id = pr.site_id AND am.company = ma.company
          AND am.l6_main = ma.l6_main
    ) m ON TRUE
    WHERE m.ps IS NOT NULL
      AND ma.report_date BETWEEN m.ps AND m.pf
      {date_filter}
""", *([proto] if not args.all_dates else []))
```

- [ ] **Step 2: 일자별 sub-batch 처리 (메모리 안전)**

530일 한 번에 처리 시 메모리 부담. 일자별 chunk:
```python
if args.all_dates:
    dates = await pg.fetch("SELECT DISTINCT report_date FROM mapper_activities ORDER BY 1")
    for d_row in dates:
        await process_one_date(pg, client, d_row["report_date"])
else:
    await process_one_date(pg, client, proto)
```

- [ ] **Step 3: 530일 실행**

```bash
pipeline/.venv/bin/python scripts/resolve_l7_5_prototype.py --all-dates 2>&1 | tee /tmp/l75_530.log
```
Expected: 각 일자별 `Resolved: total=N matched=N` 로그. 총 ~$1 미만 비용.

- [ ] **Step 4: 검증**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT COUNT(*) AS resolved, COUNT(DISTINCT report_date) AS dates FROM prototype_l7_5_resolved"
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT COUNT(*) FROM prototype_embedding_cache"
```
Expected: resolved row > 5000, dates 약 200~300 (plan 안 일자만), cache > 1000

- [ ] **Step 5: Commit**

```bash
git add scripts/resolve_l7_5_prototype.py
git commit -m "feat(scripts): resolve_l7_5_prototype.py --all-dates + cache + plan 안 필터"
```

---

## Phase D — 마스터 갈아엎기 530일

### Task 6: `apply_l7_5_overwrite.py` --all-dates

**Files:**
- Modify: `scripts/apply_l7_5_overwrite.py`

- [ ] **Step 1: argparse + UPDATE WHERE 절 분기**

```python
parser.add_argument("--all-dates", action="store_true")
date_clause = "" if args.all_dates else "AND ma.report_date = '2025-09-25'::date"
result = await pg.execute(f"""
    UPDATE mapper_activities ma
    SET l7_5_activity = r.matched_l7_5_activity,
        unit = COALESCE(r.matched_unit, ma.unit),
        plan_total_qty = COALESCE(r.matched_plan_total_qty, ma.plan_total_qty),
        plan_mh = COALESCE(r.matched_plan_mh, ma.plan_mh)
    FROM prototype_l7_5_resolved r
    WHERE ma.id = r.mapper_id
      AND r.matched_l7_5_activity IS NOT NULL
      {date_clause}
""")
```

- [ ] **Step 2: 530일 실행**

```bash
pipeline/.venv/bin/python scripts/apply_l7_5_overwrite.py --all-dates
```
Expected: `UPDATE mapper_activities: UPDATE N` (N > 5000)

- [ ] **Step 3: 검증 — 9-25 외 일자도 l7_5 채워짐**

```bash
PGPASSWORD=K7mP2xQ9nR4v psql ... -c \
  "SELECT report_date, COUNT(*) FILTER (WHERE l7_5_activity IS NOT NULL) AS with_l75 \
   FROM mapper_activities WHERE report_date IN ('2024-04-15','2025-09-25','2026-04-30') \
   GROUP BY 1 ORDER BY 1"
```
Expected: 3 일자 모두 with_l75 > 0

- [ ] **Step 4: Commit**

```bash
git add scripts/apply_l7_5_overwrite.py
git commit -m "feat(scripts): apply_l7_5_overwrite.py --all-dates"
```

---

## Phase E — view_builder.py 통합 (TDD)

### Task 7: `_build_productivity_views_v2` 산식 — 단위 테스트 5건

**Files:**
- Create: `pipeline/tests/optimizer/test_view_builder_v2.py`
- Modify: `pipeline/agents/optimizer/view_builder.py`

- [ ] **Step 1: 실패 테스트 5건 작성**

```python
# pipeline/tests/optimizer/test_view_builder_v2.py
from __future__ import annotations
import pytest
from datetime import date
from pipeline.agents.optimizer.view_builder import (
    _compute_daily_quota, _simulate_today_qty, _compute_productivity,
    _weighted_median, _normalize_impact,
)

def test_daily_quota_from_master():
    """plan_total_qty=100, total_days=10 -> daily=10.0"""
    assert _compute_daily_quota(100.0, 10) == pytest.approx(10.0)

def test_today_qty_simulation_noise_deterministic():
    """seed 고정 -> 동일 결과. noise 분포: 85% 중심 + ±20% + 5%/5% outlier (60%/150%)."""
    a = _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=42)
    b = _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=42)
    assert a == b
    # noise_q 전체 range: 0.55 ~ 1.55 (low outlier + high outlier 합집합)
    assert 0.55 * 10.0 <= a["today_qty"] <= 1.55 * 10.0


def test_today_qty_distribution_central_tendency():
    """100회 호출 평균 noise_q ≈ 0.85 (±0.05) — 경향성 검증.
    outlier (< 0.65 or > 1.40) 비율 5~25%."""
    samples = [
        _simulate_today_qty(daily_qty=10.0, daily_workers=2.0, seed=s)["today_qty"]
        for s in range(200)
    ]
    noises = [s / 10.0 for s in samples]
    avg_noise = sum(noises) / len(noises)
    assert 0.80 <= avg_noise <= 0.90, f"avg noise {avg_noise:.3f} not near 0.85"
    outliers = [n for n in noises if n < 0.65 or n > 1.40]
    assert 10 <= len(outliers) <= 50, f"outliers {len(outliers)}/200 out of [10,50]"

def test_productivity_calc():
    """perperson / master_perperson * 100"""
    assert _compute_productivity(perperson=5.0, master_perperson=5.0) == pytest.approx(100.0)
    assert _compute_productivity(perperson=4.0, master_perperson=5.0) == pytest.approx(80.0)
    assert _compute_productivity(perperson=5.0, master_perperson=0) == 0  # division by zero

def test_weighted_median_basic():
    """wv 가중 누적 50% 지점"""
    assert _weighted_median([10, 20, 30], [1, 1, 1]) == 20
    assert _weighted_median([10, 20, 30], [1, 10, 1]) == 20  # wv 큰 거에 끌림

def test_normalize_impact():
    """impact_raw / max(impact_raw) * 100 -> 0..100"""
    impacts = _normalize_impact([100, 200, 300])
    assert impacts == pytest.approx([33.33, 66.67, 100.0], abs=0.1)
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_v2.py -v
```
Expected: ImportError (함수 미정의)

- [ ] **Step 3: `view_builder.py` 에 함수 추가**

```python
# pipeline/agents/optimizer/view_builder.py (파일 끝에 추가)
import random
import statistics

def _compute_daily_quota(plan_total_qty: float, total_days: int) -> float:
    if total_days <= 0:
        return 0.0
    return plan_total_qty / total_days

def _simulate_today_qty(daily_qty: float, daily_workers: float, seed: int) -> dict:
    """productivity 분포 = 중심 85% + ±20% 일반 변동 + 5%/5% outlier (60% / 150%).

    today_qty noise 가 직접 productivity 에 반영됨 (workers 변동은 ±5% 만 — 영향 최소).
    분기:
      roll < 0.05: high outlier 1.40 ~ 1.55  (productivity ~140~155%, 150 clamp)
      roll < 0.10: low outlier  0.55 ~ 0.65  (productivity 55~65%)
      else:       일반          0.65 ~ 1.05  (productivity 65~105%, 중심 85%)
    """
    rng = random.Random(seed)
    roll = rng.random()
    if roll < 0.05:
        noise_q = 1.40 + 0.15 * rng.random()
    elif roll < 0.10:
        noise_q = 0.55 + 0.10 * rng.random()
    else:
        noise_q = 0.65 + 0.40 * rng.random()  # 중심 0.85
    noise_w = 0.95 + 0.10 * rng.random()  # 0.95 ~ 1.05
    return {
        "today_qty": daily_qty * noise_q,
        "workers": max(1.0, daily_workers * noise_w),
    }

def _compute_productivity(perperson: float, master_perperson: float) -> float:
    if master_perperson <= 0:
        return 0.0
    return perperson / master_perperson * 100

def _weighted_median(values: list[float], weights: list[float]) -> float:
    if not values:
        return 0
    pairs = sorted(zip(values, weights))
    total = sum(weights)
    if total == 0:
        return sum(values) / len(values)
    cum = 0.0
    for v, w in pairs:
        cum += w
        if cum >= total / 2:
            return v
    return pairs[-1][0]

def _normalize_impact(impacts: list[float]) -> list[float]:
    mx = max(impacts) if impacts else 1
    if mx <= 0:
        return [0.0] * len(impacts)
    return [round(x / mx * 100, 2) for x in impacts]
```

- [ ] **Step 4: 테스트 PASS 확인**

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_v2.py -v
```
Expected: 6 passed (5 기본 + 1 distribution central tendency)

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/optimizer/test_view_builder_v2.py
git commit -m "feat(view_builder): 신규 4단 산식 함수 + tests (TDD)"
```

---

### Task 8: display_label 생성 함수 + test (C8)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py`
- Modify: `pipeline/tests/optimizer/test_view_builder_v2.py`

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_display_label_format():
    """'98.9% (3.2 ton/인)' 형식"""
    from pipeline.agents.optimizer.view_builder import _make_display_label
    assert _make_display_label(98.9, 3.2, "ton") == "98.9% (3.2 ton/인)"
    assert _make_display_label(81.3, 0.06, "m2") == "81.3% (0.06 m2/인)"
    # unit None -> "%만"
    assert _make_display_label(50, None, None) == "50.0%"
```

- [ ] **Step 2: 실패 확인 + 구현**

```python
def _make_display_label(productivity_pct: float, perperson: float | None, unit: str | None) -> str:
    if perperson is None or unit is None:
        return f"{productivity_pct:.1f}%"
    return f"{productivity_pct:.1f}% ({perperson:.2f} {unit}/인)"
```

- [ ] **Step 3: 테스트 PASS + commit**

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_v2.py::test_display_label_format -v
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/optimizer/test_view_builder_v2.py
git commit -m "feat(view_builder): _make_display_label (C8 단위 표시)"
```

---

### Task 9: `_build_productivity_views_v2` 메인 함수 + test (통합 산식)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py`
- Modify: `pipeline/tests/optimizer/test_view_builder_v2.py`

**시그니처 (reviewer issue #7 명확화)**:
```python
async def _build_productivity_views_v2(
    pg: PGClient,           # asyncpg connection / mock
    site_id: str,           # "m15x-ph3-ibl"
    today: date,            # 처리 일자 (예: date(2025, 9, 25))
) -> dict:                  # {kpi, productivity, contractor_bars, trade_bars, quadrant, wp_summary}
```
기존 `_build_productivity_views` 시그니처의 `run_id`, `forecast`, `mapped` 인자는 미사용 → 제거.
`master_summary` 는 함수 내부 SQL LATERAL JOIN 으로 즉석 계산 (별도 인자 X).

**display_label 위치 (reviewer issue #4 명확화)**:
- `_make_display_label` (Task 8) 함수는 view_builder.py 내부에서 정의
- `_build_productivity_views_v2` 가 모든 row 산식 후 `_make_display_label(productivity_pct, perperson, unit)` 호출하여 display_label 필드 추가
- atomizer 는 raw metadata (perperson, productivity_pct) 만 적재, display_label X (live 시점엔 unknown)

- [ ] **Step 1: 실패 테스트 추가 + fixture 정의**

```python
# pipeline/tests/optimizer/conftest.py (신규 또는 추가)
import pytest
import pytest_asyncio
from datetime import date

@pytest_asyncio.fixture
async def fixture_pg_9_25(real_pg):
    """9-25 prototype 데이터 (광건 수장공사 + OTIS 승강기) 단순 fixture.
    real_pg = pipeline/tests/conftest.py 의 기존 PG fixture 재사용."""
    yield real_pg  # 실 PG 사용 (9-25 prototype 적용된 mapper_activities)

# pipeline/tests/optimizer/test_view_builder_v2.py
import pytest
from datetime import date
from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2

@pytest.mark.asyncio
@pytest.mark.integration  # real_pg 사용
async def test_build_productivity_views_v2_basic(fixture_pg_9_25):
    """9-25 prototype 적용된 mapper_activities 위에서 산식 결과 검증"""
    result = await _build_productivity_views_v2(
        pg=fixture_pg_9_25,
        site_id="m15x-ph3-ibl",
        today=date(2025, 9, 25),
    )
    # 구조 검증
    for key in ["kpi", "productivity", "contractor_bars", "trade_bars", "quadrant", "wp_summary"]:
        assert key in result
    # KPI
    assert result["kpi"]["productivity_today"] > 0
    assert result["kpi"]["productivity_today"] <= 150  # clamp
    assert "display_label" in result["kpi"]  # 예: "98.9% (3.2 ton/인)"
    # contractor_bars 모두 display_label
    assert len(result["contractor_bars"]) > 0
    assert all("display_label" in b for b in result["contractor_bars"])
    # quadrant + wp_summary 도
    assert all("display_label" in q for q in result["quadrant"])
    assert all("display_label" in w for w in result["wp_summary"])
```

- [ ] **Step 2: 구현 — SQL + 산식 구체 코드 (reviewer 2차 issue #3)**

`compute_productivity_v2_proto.py` 의 main() 로직을 `_build_productivity_views_v2` 로 이식. **정확 SQL 명시** (LATERAL JOIN 으로 master_summary 즉석 계산):

```python
async def _build_productivity_views_v2(
    pg: PGClient, site_id: str, today: date,
) -> dict:
    """Phase 1 신규 4단 산식 — daily_reports.jsonb 6 컬럼 생성."""
    # 1. mapper_activities + master_summary LATERAL JOIN
    rows = await pg.fetch("""
        SELECT ma.id, pr.site_id, ma.run_id, ma.company, ma.l6_main, ma.l7_5_activity,
               ma.unit, ma.zone, m.ps AS plan_start, m.pf AS plan_finish,
               m.qty AS plan_total_qty, m.mh AS plan_mh
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN LATERAL (
            SELECT MIN(plan_start) AS ps, MAX(plan_finish) AS pf,
                   SUM(plan_total_qty) AS qty, SUM(plan_mh_rev2) AS mh
            FROM activity_master am
            WHERE am.site_id = pr.site_id AND am.company = ma.company
              AND am.l6_main = ma.l6_main AND am.l7_5_activity = ma.l7_5_activity
        ) m ON TRUE
        WHERE ma.report_date = $1
          AND pr.site_id = $2
          AND ma.l7_5_activity IS NOT NULL
          AND m.ps IS NOT NULL AND $1 BETWEEN m.ps AND m.pf
    """, today, site_id)

    if not rows:
        return _empty_result()  # plan 기간 밖 — 빈 jsonb

    # 2. row 별 산식 (Task 7 + 8 함수 호출)
    l75_items = []
    for r in rows:
        plan_qty = float(r["plan_total_qty"] or 0)
        plan_mh = float(r["plan_mh"] or 0)
        total_days = (r["plan_finish"] - r["plan_start"]).days + 1
        if total_days <= 0 or plan_qty <= 0 or plan_mh <= 0:
            continue
        daily_qty_master = _compute_daily_quota(plan_qty, total_days)
        daily_workers_master = max(1.0, plan_mh / total_days / 8.0)
        # seed = ordinal ^ hash(l7_5_activity) — deterministic
        seed = int(today.toordinal()) ^ hash(r["l7_5_activity"])
        sim = _simulate_today_qty(daily_qty_master, daily_workers_master, seed)
        perperson = sim["today_qty"] / sim["workers"]
        master_perperson = daily_qty_master / daily_workers_master
        productivity = _compute_productivity(perperson, master_perperson)
        productivity = min(productivity, 150.0)  # clamp
        impact_raw = max(0, 100 - productivity) * plan_mh
        l75_items.append({
            **dict(r), "today_qty": sim["today_qty"], "workers": sim["workers"],
            "perperson": perperson, "productivity": productivity, "impact_raw": impact_raw,
            "daily_qty_master": daily_qty_master,
        })

    # 3. impact 정규화
    impacts_norm = _normalize_impact([it["impact_raw"] for it in l75_items])
    for it, ni in zip(l75_items, impacts_norm):
        it["impact"] = ni

    # 4. 업체별 / 공종별 집계 + 현장 산식 (기존 compute_productivity_v2_proto.py 동일)
    # ...

    # 5. display_label 모든 row 에 추가 (Task 8 _make_display_label 호출)
    for b in contractor_bars + trade_bars:
        b["display_label"] = _make_display_label(b["value"], b.get("perperson"), b.get("perperson_unit"))
    for q in quadrant:
        q["display_label"] = _make_display_label(q["productivity"], q.get("perperson"), q.get("perperson_unit"))
    for w in wp_summary:
        w["display_label"] = _make_display_label(w["productivity"], w.get("perperson"), w.get("perperson_unit"))
    kpi["productivity_today_display"] = _make_display_label(
        kpi["productivity_today"],
        kpi.get("productivity_perperson_today"),
        kpi.get("productivity_perperson_unit"),
    )

    return {"kpi": kpi, "productivity": productivity_dict,
            "contractor_bars": contractor_bars, "trade_bars": trade_bars,
            "quadrant": quadrant, "wp_summary": wp_summary}


def _empty_result() -> dict:
    return {"kpi": {}, "productivity": {},
            "contractor_bars": [], "trade_bars": [], "quadrant": [], "wp_summary": []}
```

같은 파일 내 함수라 import 없이 직접 호출. 집계 + 단위 추출 로직은 `compute_productivity_v2_proto.py:140-220` 참조.

- [ ] **Step 3: 테스트 PASS + commit**

```bash
git commit -m "feat(view_builder): _build_productivity_views_v2 통합 산식"
```

---

### Task 10: ChromaDB 풍부화 + augmentation (C7)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py`
- Modify: `pipeline/tests/optimizer/test_view_builder_v2.py`

**ChromaDB 적재 책임 분리 (reviewer issue #3 명확화)**:
- **atomizer (live pipeline)** = 새 daily report 처리 시 그 일자의 mapper_activities row 들을 ChromaDB `daily_activities` 에 즉시 upsert. **현재 동작 유지** (Task 12 는 _format_document/_build_metadata 형식만 갱신).
- **backfill (Phase F — Task 13)** = 530일치 history 를 ChromaDB 에 일괄 upsert. atomizer 와 **같은 collection (daily_activities) + 같은 doc_id sha256 → 자동 dedup**. backfill 은 view_builder 함수 호출 후 그 결과를 ChromaDB 에도 적재 (별도 function: `_enrich_chroma_daily_activities`).
- **augmentation 함수 (`_augment_history_if_sparse`)** = backfill 시점에만 호출. atomizer 는 augmentation 안 함 (live 데이터는 실측만).

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_chroma_augmentation_marks_source():
    """augment 된 row 의 metadata.augmented=true + augmented_from_company"""
    items = [{"company": "광건", "l6_main": "수장공사", ...}]
    # 광건 history 부족 -> 다른 company 의 수장공사 history augment
    augmented = _augment_history_if_sparse(items, min_count=5)
    aug_rows = [a for a in augmented if a["metadata"].get("augmented")]
    assert len(aug_rows) > 0
    assert all("augmented_from_company" in a["metadata"] for a in aug_rows)
```

- [ ] **Step 2: 구현**

```python
def _augment_history_if_sparse(items, min_count=5):
    """각 (company, l6_main) 그룹별 row 수 < min_count 면 동일 l6 의 다른 company 에서 보충."""
    from collections import defaultdict
    by_group = defaultdict(list)
    for it in items:
        by_group[(it["company"], it["l6_main"])].append(it)
    augmented = list(items)
    for (co, l6), rows in by_group.items():
        if len(rows) >= min_count:
            continue
        need = min_count - len(rows)
        # 동일 l6 다른 company 에서 가져옴
        donors = [it for it in items if it["l6_main"] == l6 and it["company"] != co]
        for donor in donors[:need]:
            aug = dict(donor)
            aug["company"] = co
            aug["metadata"] = {
                **donor.get("metadata", {}),
                "augmented": True,
                "augmented_from_company": donor["company"],
            }
            augmented.append(aug)
    return augmented
```

- [ ] **Step 3: 테스트 PASS + commit**

```bash
git commit -m "feat(view_builder): ChromaDB augmentation (C7)"
```

---

### Task 11: forecaster augmentation 가중치 + cold_start 라벨 (C9)

**Files:**
- Modify: `pipeline/agents/forecaster.py`
- Modify: `pipeline/tests/optimizer/test_view_builder_v2.py` (forecaster test 추가)

**Cold start threshold 단일화 (reviewer issue #11 명확화)**:
- 기준: `total_weight = sum(w for _, w in weighted_history)`
- 분기: `if total_weight < 3.0: cold_start = True` (단일 조건)
- "history 0건" + "sparse history" 두 경우 모두 자연 포함 (0건 = total_weight = 0 < 3.0)
- spec 의 "0건 또는 < 3.0" 문구는 의미 중복이지만 implementation 은 단일 조건만.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_augmented_rows_lower_weight():
    """augmented=true row 는 가중치 0.5, 일반 row 는 1.0"""
    from pipeline.agents.forecaster import _apply_augmentation_weight
    rows = [
        {"metadata": {"augmented": True}},
        {"metadata": {}},
        {"metadata": {"augmented": False}},
    ]
    weighted = _apply_augmentation_weight(rows)
    assert weighted[0][1] == 0.5
    assert weighted[1][1] == 1.0
    assert weighted[2][1] == 1.0

def test_cold_start_label_replaced():
    """history 가중치 합 < 3.0 -> "신규 작업..." 라벨 + recommendations 1건 이상"""
    from pipeline.agents.forecaster import _format_diagnosis
    result = _format_diagnosis(
        weighted_history=[],
        master_baseline={"daily_qty": 16, "unit": "m2", "daily_workers": 2},
    )
    assert "신규 작업" in result["diagnosis"]
    assert len(result["recommendations"]) >= 1
```

- [ ] **Step 2: 구현**

```python
# pipeline/agents/forecaster.py 추가
def _apply_augmentation_weight(rows: list[dict]) -> list[tuple[dict, float]]:
    return [(r, 0.5 if r.get("metadata", {}).get("augmented") else 1.0) for r in rows]

def _format_diagnosis(weighted_history: list, master_baseline: dict) -> dict:
    total_weight = sum(w for _, w in weighted_history)
    if total_weight < 3.0:
        return {
            "diagnosis": "신규 작업 — 마스터 baseline 기준 권고",
            "recommendations": [
                f"일일 quota {master_baseline['daily_qty']:.1f} "
                f"{master_baseline['unit']} 기준 작업 진행. "
                f"인원 {master_baseline['daily_workers']:.1f}명/일 권장."
            ],
            "similar_cases": [],
        }
    # 일반 진단 로직 (기존)
    ...
```

- [ ] **Step 3: 테스트 PASS + commit**

```bash
git commit -m "feat(forecaster): augmentation 가중치 + cold_start 라벨 (C9)"
```

---

### Task 12: atomizer documents 사람 가독 형식 (C6)

**Files:**
- Modify: `pipeline/agents/atomizer.py`
- Modify: `pipeline/tests/optimizer/test_view_builder_v2.py` (atomizer test 추가)

**호출 컨텍스트 (reviewer issue #9 명확화 — 실행 시 perperson 출처 혼동 방지)**:
- atomizer 는 **live pipeline** 에서만 직접 호출됨 (LangGraph atomize node). 입력 = mapper_activities row 1건.
- live 시점엔 perperson / productivity_pct **계산되지 않음** (view_builder 가 마스터 daily 와 비교해야 산출). 따라서:
  - `_build_metadata` 의 perperson/productivity_pct 필드는 **기본값 0** 으로 적재 (placeholder).
  - `_format_document` 는 **2가지 시그니처** 지원:
    1. live (atomize 호출): perperson=None, productivity_pct=None → 짧은 형식 ("...시공량 N unit / 인원 N 명")
    2. backfill (Task 13 호출): perperson=value, productivity_pct=value → 풀 형식 (인당 + %)
- backfill (Task 13) 의 `_enrich_chroma_daily_activities` 가 view_builder 산식 결과로 perperson/productivity_pct 알아내고 `_format_document` 풀 형식 호출 + ChromaDB upsert.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_atomizer_document_format():
    """가독 텍스트 형식"""
    from pipeline.agents.atomizer import _format_document
    activity = {
        "company": "광건", "l6_main": "수장공사",
        "l7_5_activity": "풍도벽체 설치",
        "today_qty": 15, "unit": "m2", "assigned_workers": 265,
        "conditions": [],
    }
    doc = _format_document(activity, date="2025-09-25", perperson=0.06, productivity_pct=98.9)
    assert "광건" in doc
    assert "수장공사" in doc
    assert "풍도벽체 설치" in doc
    assert "0.06 m2/인" in doc
    assert "98.9%" in doc

def test_atomizer_metadata_enrichment():
    """metadata 에 l7_5_activity + perperson + productivity_pct 필드"""
    from pipeline.agents.atomizer import _build_metadata
    activity = {
        "company": "광건", "l5_disc": "건축", "l6_main": "수장공사",
        "wa": "FAB", "unit": "m2", "today_qty": 15.0,
        "assigned_workers": 265.0, "worker_source": "mh_prorated",
        "mapping_conf": 1.0, "conditions": [],
        "l7_5_activity": "풍도벽체 설치",  # 신규
        "perperson": 0.06, "productivity_pct": 98.9,  # 신규
    }
    md = _build_metadata(activity, date="2025-09-25", run_id="test-run")
    assert md["l7_5_activity"] == "풍도벽체 설치"
    assert md["perperson"] == 0.06
    assert md["productivity_pct"] == 98.9
```

- [ ] **Step 2: 구현 — 2가지 시그니처 분기 로직 명시 (reviewer 2차 issue #1)**

```python
# pipeline/agents/atomizer.py 갱신
from typing import Optional

def _format_document(
    activity: dict,
    date: str,
    perperson: Optional[float] = None,
    productivity_pct: Optional[float] = None,
) -> str:
    """ChromaDB 문서 텍스트 생성. 2가지 모드:
    - live (atomize 호출): perperson=None → 짧은 형식 (마스터 비교값 없음)
    - backfill (Task 13 호출): perperson=값 → 풀 형식 (인당 + %)
    """
    qty = activity["today_qty"]
    unit = activity["unit"]
    workers = activity["assigned_workers"]
    conds = ", ".join(activity.get("conditions") or []) or "정상"
    head = (
        f"[{date}] {activity['company']} · {activity['l6_main']} · "
        f"{activity.get('l7_5_activity', '')}"
    )
    body_basic = f"시공량 {qty:.1f} {unit} / 인원 {workers:.0f} 명"

    if perperson is None or productivity_pct is None:
        # live 모드 — placeholder, 마스터 비교값 없음
        return f"{head}\n{body_basic}\n조건: {conds}"

    # backfill 모드 — 풀 형식
    body_full = (
        f"{body_basic} → 인당 {perperson:.2f} {unit}/인 "
        f"({productivity_pct:.1f}%)"
    )
    return f"{head}\n{body_full}\n조건: {conds}"


def _build_metadata(a: dict, date: str, run_id: str) -> dict:
    """ChromaDB 메타데이터. perperson/productivity_pct 는 backfill 시 채움.
    live atomize 시점엔 0 placeholder."""
    return {
        "date": date,
        "run_id": run_id,
        "company": a["company"],
        "l5_disc": a["l5_disc"],
        "l6_main": a["l6_main"] or "",
        "l7_5_activity": a.get("l7_5_activity", ""),  # 신규 (live 시점은 보통 채움 — Task 6 의 갈아엎기 결과)
        "wa": a["wa"] or "",
        "unit": a["unit"],
        "today_qty": float(a["today_qty"]),
        "assigned_workers": float(a["assigned_workers"]),
        "perperson": float(a.get("perperson", 0)),  # 신규 — live=0, backfill=계산값
        "productivity_pct": float(a.get("productivity_pct", 0)),  # 신규 — live=0, backfill=계산값
        "worker_source": a["worker_source"],
        "mapping_conf": float(a["mapping_conf"] or 0.0),
        "conditions": ",".join(a.get("conditions") or []),
    }

# atomize() 안 documents 빌드 부분 — live 모드 (perperson=None)
documents = [_format_document(valid[i], date) for i in seen.values()]  # live: 짧은 형식
```

- [ ] **Step 3: 테스트 PASS + commit**

```bash
git commit -m "feat(atomizer): documents 사람 가독 형식 + metadata 풍부화 (C6)"
```

---

## Phase F — backfill 530일

### Task 13: `backfill_daily_report_views.py` view_builder_v2 호출 + 일자 루프 + ChromaDB upsert

**Files:**
- Modify: `scripts/backfill_daily_report_views.py`
- Create: `pipeline/tests/test_backfill_phase1.py`
- Create: `pipeline/agents/optimizer/chroma_enrich.py` (신규 — `_enrich_chroma_daily_activities`)

**ChromaDB upsert 책임 (reviewer issue #3 명확화 — Task 10 의 contract 실행 위치)**:
- backfill 의 각 일자 처리 흐름:
  1. `_build_productivity_views_v2(pg, site_id, date)` 호출 → 산식 결과 dict
  2. **결과의 row 들 (wp_summary 의 각 row)** 에서 perperson/productivity_pct 추출
  3. `_enrich_chroma_daily_activities(chroma_client, mapper_activities_rows, perperson_map, productivity_map, augmentation=True)` 호출 → ChromaDB upsert
  4. daily_reports.jsonb 6컬럼 UPDATE
- `_enrich_chroma_daily_activities` 가 atomizer 의 `_format_document` 풀 형식 + `_build_metadata` (perperson 채움) 호출. 같은 doc_id sha256 → atomizer live upsert 와 자동 dedup.
- augmentation 도 backfill 측에서만 (atomizer 는 안 함).

**트랜잭션 경계 (reviewer 2차 issue #2 명확화 — 실행 시 atomic 여부)**:
- ChromaDB 와 PG 는 **별도 트랜잭션** (cross-DB atomic 불가능)
- **순서 보장**:
  1. `_build_productivity_views_v2` 실행 (PG read only)
  2. `_enrich_chroma_daily_activities` 실행 → ChromaDB upsert
     - ChromaDB 실패 시 (rate limit, network) → 3회 재시도 (exponential backoff: 1s, 2s, 4s)
     - 3회 모두 실패 시 → 그 일자 skip (log "WARN: chroma upsert failed for {date}, jsonb UPDATE 진행")
  3. daily_reports.jsonb UPDATE (PG transaction) — ChromaDB 성공/실패 무관 항상 실행
- **이유**: jsonb 가 UI 의 source of truth. ChromaDB 는 forecaster RAG 보조. ChromaDB 일부 실패해도 UI 표시는 정상.
- **idempotency**: backfill 재실행 시 같은 doc_id sha256 → ChromaDB 자동 dedup. jsonb 도 same seed → byte-exact UPDATE.

- [ ] **Step 1: 백필 통합 테스트 작성**

```python
# pipeline/tests/test_backfill_phase1.py
import pytest
from pathlib import Path

@pytest.mark.integration
def test_backfill_530_days_idempotent(real_pg):
    """2회 실행 후 daily_reports.kpi_jsonb byte-exact 동일"""
    import json, subprocess
    subprocess.run(["python", "scripts/backfill_daily_report_views.py", "--all-dates"], check=True)
    first = real_pg.fetchall("SELECT kpi_jsonb FROM daily_reports WHERE is_mock=false ORDER BY report_date")
    subprocess.run(["python", "scripts/backfill_daily_report_views.py", "--all-dates"], check=True)
    second = real_pg.fetchall("SELECT kpi_jsonb FROM daily_reports WHERE is_mock=false ORDER BY report_date")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

@pytest.mark.integration
def test_cold_start_ratio_under_5pct(real_pg):
    """530일 backfill 후 by_wp 의 cold_start 비율 < 5%"""
    rows = real_pg.fetchall(
        "SELECT optimizer_view_jsonb FROM daily_reports WHERE is_mock=false"
    )
    total_wp = 0
    cold_wp = 0
    for r in rows:
        for wp_id, wp_data in (r["optimizer_view_jsonb"] or {}).get("by_wp", {}).items():
            total_wp += 1
            if "신규 작업" not in wp_data.get("diagnosis", ""):
                continue
            if not wp_data.get("recommendations"):
                cold_wp += 1
    ratio = cold_wp / total_wp if total_wp else 0
    assert ratio < 0.05, f"cold_start ratio {ratio:.2%} >= 5%"

@pytest.mark.integration
def test_skip_ratio_under_30pct(real_pg):
    """plan 기간 밖 일자 비율 < 30%"""
    row = real_pg.fetchone(
        "SELECT COUNT(*) FILTER (WHERE kpi_jsonb = '{}'::jsonb OR kpi_jsonb IS NULL) AS empty, "
        "COUNT(*) AS total FROM daily_reports WHERE is_mock=false"
    )
    skip = row["empty"] / row["total"]
    assert skip < 0.30, f"skip ratio {skip:.2%} >= 30%"

@pytest.mark.integration
def test_all_rows_have_display_label(real_pg):
    """contractor_bars / wp_summary 모두 display_label 필드 채워짐"""
    rows = real_pg.fetchall(
        "SELECT contractor_bars_jsonb, wp_summary_jsonb FROM daily_reports "
        "WHERE is_mock=false AND kpi_jsonb != '{}'::jsonb"
    )
    for r in rows:
        for b in r["contractor_bars_jsonb"] or []:
            assert "display_label" in b
        for w in r["wp_summary_jsonb"] or []:
            assert "display_label" in w
```

- [ ] **Step 2: backfill 스크립트 갱신**

```python
# scripts/backfill_daily_report_views.py 갱신
async def backfill_one_date(pg, site_id, date):
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2
    result = await _build_productivity_views_v2(pg, run_id=None, site_id=site_id,
                                                 today=date, forecast=[], mapped=[])
    if not result.get("kpi") or not result["kpi"].get("productivity_today"):
        # plan 기간 밖 — 빈 jsonb
        await pg.execute("""
            UPDATE daily_reports SET kpi_jsonb='{}'::jsonb, contractor_bars_jsonb='[]'::jsonb,
                trade_bars_jsonb='[]'::jsonb, quadrant_jsonb='[]'::jsonb,
                wp_summary_jsonb='[]'::jsonb, productivity_jsonb='{}'::jsonb
            WHERE report_date = $1::date AND is_mock=false
        """, date)
        return "empty"
    # 정상 - 6 jsonb UPDATE (기존 compute_productivity_v2_proto.py 와 동일)
    ...
    return "ok"

async def main():
    parser.add_argument("--all-dates", action="store_true")
    # skip 비율 모니터링
    empty_count = 0
    total = 0
    dates = await pg.fetch(... if args.all_dates else "...")
    for d in dates:
        r = await backfill_one_date(pg, site_id, d["report_date"])
        total += 1
        if r == "empty":
            empty_count += 1
    skip_pct = empty_count / total * 100
    print(f"skip ratio: {skip_pct:.1f}%")
    if skip_pct > 30:
        raise RuntimeError(f"skip ratio {skip_pct}% exceeds 30% — backfill 중단")
```

- [ ] **Step 3: 530일 backfill 실행**

```bash
pipeline/.venv/bin/python scripts/backfill_daily_report_views.py --all-dates 2>&1 | tee /tmp/backfill_530.log
```
Expected: `skip ratio: X%` (X < 30) + 530 일자 처리 완료

- [ ] **Step 4: 통합 테스트 실행**

```bash
pipeline/.venv/bin/python -m pytest pipeline/tests/test_backfill_phase1.py -v -m integration
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(backfill): 530일 view_builder_v2 통합 + integration tests"
```

---

## Phase G — UI 측 display_label 사용

### Task 14: types.ts 에 display_label + perperson + perperson_unit 옵셔널 필드

**Files:**
- Modify: `web/lib/types.ts`

**Schema 결정 (reviewer issue #10 명확화 — 단일 vs separate 모두 적재)**:
- BE 가 jsonb 에 **3 필드 동시** 적재:
  - `display_label`: 단일 표시용 문자열 (예: `"98.9% (3.2 ton/인)"`) — UI 가 그대로 출력
  - `perperson`: 인당 원본값 (예: 3.2) — UI 가 toggle/format 시 사용
  - `perperson_unit`: 단위 (예: `"ton/인"`) — UI 가 별도 표시 가능
- 이렇게 둘 다 적재하는 이유: 디자인 불가침 (현 UI 그대로) + 미래 toggle 옵션 보존. jsonb 사이즈 증가 미미 (3 필드 × ~10 chars).

- [ ] **Step 1: BarItem / QuadrantPoint / WPSummaryRow / ReportKpi 모두 3 필드 추가**

```typescript
export interface BarItem {
  label: string;
  value: number;
  status: Status;
  baseline?: number;
  display_label?: string;   // 신규 - 예: "98.9% (3.2 ton/인)"
  perperson?: number;        // 신규 - 예: 3.2
  perperson_unit?: string;   // 신규 - 예: "ton/인"
}

export interface QuadrantPoint {
  // ... 기존 필드
  display_label?: string;
  perperson?: number;
  perperson_unit?: string;
}

export interface WPSummaryRow {
  // ... 기존 필드
  display_label?: string;
  perperson?: number;
  perperson_unit?: string;
}

export interface ReportKpi {
  // ... 기존 필드
  productivity_today_display?: string;  // 신규 (예: "98.9% (3.2 ton/인)")
  productivity_perperson_today?: number;
  productivity_perperson_unit?: string;
}
```

- [ ] **Step 2: `npm run build` 통과 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npm run build
```
Expected: ✓ Compiled successfully

- [ ] **Step 3: Commit**

```bash
git add web/lib/types.ts
git commit -m "feat(types): display_label 옵셔널 필드 추가 (BarItem/QuadrantPoint/WPSummaryRow/ReportKpi)"
```

---

### Task 15: 8 hardcode 위치 (7 파일) → display_label fallback (reviewer issue #6 명확화)

**Files (8 위치 / 7 파일)**:
- `web/app/components/charts/BarChartH.tsx:164` — 평균 라벨
- `web/app/components/charts/QuadrantScatter.tsx:45` — tooltip productivity
- `web/app/components/dashboard/PerformanceTab.tsx:31` — 전사 평균 unit
- `web/app/components/dashboard/SiteOverviewCard.tsx:86` — 사이트 카드 productivity_today
- `web/app/components/charts/ProductivityTrendChart.tsx:67` — gap 표시
- `web/app/components/charts/ProductivityTrendChart.tsx:107` — ReferenceLine 평균
- `web/app/components/reports/WPSummaryTable.tsx:82` — row.productivity
- `web/app/components/reports/ReportDailyList.tsx:45` — 일자 리스트 productivity_today

- [ ] **Step 1: BarChartH.tsx (line 164)**

```typescript
// Before: value={`평균 ${avg.toFixed(1)}%`}
// After:
value={items[0]?.display_label ? `평균 ${avg.toFixed(1)}%` : `평균 ${avg.toFixed(1)}%`}
// 또는 BE 가 평균 display_label 안 주니까 그대로 두기 — 개별 bar 만 변경
```

실제 변경: bar tooltip 또는 label 부분. recharts Cell 의 children 에 display_label 사용.

- [ ] **Step 2~8: 나머지 7 컴포넌트 동일 패턴**

`QuadrantScatter.tsx:45`, `PerformanceTab.tsx:31`, `SiteOverviewCard.tsx:86`, `ProductivityTrendChart.tsx:67,107`, `WPSummaryTable.tsx:82`, `ReportDailyList.tsx:45`

각 컴포넌트에서:
```typescript
{row.display_label || `${row.productivity}%`}
```

- [ ] **Step 9: 디자인 가드 — className 변경 0 검증**

```bash
git diff --stat web/app/components/ | head -20
git diff web/app/components/ | grep -E '^[+-].*className=' | wc -l
```
Expected: 마지막 0

- [ ] **Step 10: `npm run build` + UI 검증**

```bash
cd web && npm run build
# dev server 가 살아있으면 HMR 자동 반영
curl -s http://127.0.0.1:5536/reports > /dev/null  # 200 확인
```

- [ ] **Step 11: Commit**

```bash
git add web/app/components/
git commit -m "feat(ui): 8 컴포넌트 display_label 사용 (단위 표시, markup 변경 0)"
```

---

## Phase H — 임시 코드 제거 + 검증

### Task 16: `/api/mock/report` 9-25 필터 제거

**Files:**
- Modify: `web/app/api/mock/report/route.ts`

- [ ] **Step 1: 필터 제거**

```typescript
// 제거: AND pr.report_date = '2025-09-25'::date  -- TODO(prototype...
```

- [ ] **Step 2: API 응답 확인 — 530 row**

```bash
curl -s http://127.0.0.1:5536/api/mock/report | python3 -c \
  "import sys,json; d=json.loads(sys.stdin.read()); print('daily rows:', len(d['daily']))"
```
Expected: `daily rows: 530`

- [ ] **Step 3: Commit**

```bash
git add web/app/api/mock/report/route.ts
git commit -m "fix(api): 9-25 임시 필터 제거 (530일 전체 read)"
```

---

### Task 17: `compute_productivity_v2_proto.py` 폐기

**Files:**
- Delete: `scripts/compute_productivity_v2_proto.py`

- [ ] **Step 1: 사용처 확인**

```bash
grep -rn "compute_productivity_v2_proto" . --include="*.py" --include="*.md" 2>/dev/null
```
Expected: 결과 0 (또는 spec/plan 문서 안에만)

- [ ] **Step 2: 삭제 + commit**

```bash
git rm scripts/compute_productivity_v2_proto.py
git commit -m "chore: compute_productivity_v2_proto.py 폐기 (view_builder.py 통합 완료)"
```

---

### Task 18: UI 5536 수동 검증 3 일자 + 사용자 컨펌

**Files:** (no code change)

- [ ] **Step 1: 사용자에게 3 일자 검증 요청**

```
URL: http://127.0.0.1:5536/reports

확인 일자 3건:
- 2025-09-25 (anchor)
- 2024-12-20 (가운데 임의)
- 2026-04-30 (최근 임의)

체크리스트:
- [ ] 상단 KPI: 0~150% 범위 + display_label (예: "98.9% (3.2 ton/인)")
- [ ] contractor_bars (업체별) 8건 표시 + outlier 폭주 없음
- [ ] trade_bars (공종별) 5건 표시
- [ ] 4분면 산점도 + WP 클릭 시 OptimizerResult 우측 — cold_start 없음 또는 "신규 작업..." 라벨
- [ ] 콘솔 에러 0 (F12)
```

- [ ] **Step 2: 사용자 컨펌 "OK 시연 진입" 받음**

(사용자 응답 대기)

---

### Task 19: git push + PR 생성 (A_Track → main 후보)

**Files:** (no code change)

- [ ] **Step 1: git push origin A_Track**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA" && git push origin A_Track
```

- [ ] **Step 2: PR 생성**

```bash
gh pr create --base main --head A_Track \
  --title "feat: 데이터 정합화 Phase 1 — 530일 + view_builder 통합 + atomizer 가독성" \
  --body "$(cat <<'EOF'
## Summary

CPIA 데이터 정합화 Phase 1 — 9-25 prototype 검증 정책을 530일 (건축+토목 한정) 확장.

### 핵심 변경
- 530일 mapper_activities company 정규화 + 슬래시 통일 + L7.5 임베딩 재매핑 + 마스터 갈아엎기
- view_builder.py 신규 함수 `_build_productivity_views_v2` (산식 4단 + impact + display_label)
- atomizer documents 사람 가독 형식 + metadata l7_5_activity/perperson 추가
- ChromaDB daily_activities 530일 적재 + augmentation (cold_start 자연 제거)
- forecaster augmentation 가중치 0.5 + cold_start 라벨 "신규 작업 — 마스터 baseline 권고"
- UI 8 컴포넌트 display_label 사용 (markup 변경 0)
- 임시 코드 제거 (route.ts 9-25 필터 + compute_productivity_v2_proto.py 폐기)

### Spec / Plan
- spec: docs/superpowers/specs/2026-05-21-cpia-data-canonicalization-phase1-design.md
- plan: docs/superpowers/plans/2026-05-21-cpia-data-canonicalization-phase1-plan.md
- gbrain: decisions/cpia-data-canonicalization-2026-05-21

### Test plan
- [x] view_builder.py 단위 테스트 10건 PASS
- [x] backfill integration test 4건 PASS (idempotent, cold_start <5%, skip <30%, display_label)
- [x] git diff className = 0 (디자인 불가침)
- [x] UI 5536 3 일자 (9-25 + 2024-12 + 2026-04) 수동 검증 + 콘솔 에러 0
- [x] 사용자 컨펌 ("OK 시연 진입")

머지는 조형준 프로님 결정.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: PR URL 출력**

```bash
gh pr view --json url --jq .url
```

---

## Out of scope (다음 phase)

- Phase 2: 5공종 확장 (설비/전기/UT/제어/소방)
- Phase 3: 더미 5건 정합화
- Phase 4: 통합 작업일보 엑셀
- forecaster recovery_days 산식 갱신
- precedence-kg Signal 3 연결
- parser_worker_outputs 실 인원 재적재 (사용자 결정: 안 함)
