# CPIA UI Data Integrity Phase 2 Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Spec at `docs/superpowers/specs/2026-05-21-cpia-ui-data-integrity-phase2-design.md`. **Plan v2 (2026-05-21) reflects plan-document-reviewer feedback** — all ambiguities resolved in plan (no implementation-time decisions).

**Goal:** 530일 더미 적재 후 dev server 5536 에서 발견된 6 RC 일괄 정합화 — BE WHERE 필터 + view_builder 통합 + ChromaDB 530일 backfill + UI textContent fix.

**Architecture:** PG row 변경 0 (사용자 명시 "백업 안 건드림 = 플래그 방식"). BE/route SQL 에 `WHERE ma.trade IN ('건축', '토목')` 추가하여 화면에서 가림. view_builder.`_build_productivity_views_v2` 가 wp_id 통일 + 9 jsonb key 반환 (optimizer_view/scenarios/s_curve 추가) + advice 없는 WP 는 deterministic cold_start (8 cause × 5 recommendations 룰, LLM 호출 0). ChromaDB daily_activities 27,484 row 적재 (l7_5_activity metadata). UI 4 컴포넌트 textContent 만 변경 (디자인 가드 markup/className 0). Dashboard fixture JSON → 실 PG 530일 집계.

**Tech Stack:** Python 3.11 + asyncpg + Azure OpenAI text-embedding-3-small (1536d) + ChromaDB HttpClient + Next.js 15 + TypeScript

---

## File Structure (변경 / 신규 파일 매핑)

**BE (Python)**
- Modify `pipeline/agents/optimizer/view_builder.py:928, 1087-1126` — wp_id 통일, ma.wa SELECT, quadrant dict 확장, 9 key return, 4 신규 헬퍼 + `_build_deterministic_cold_start`
- Modify `pipeline/agents/optimizer/retrieve.py:34, 49, 73, 120` — 4 함수 시그니처에 `l7_5_activity: Optional[str] = None` 추가
- Create `pipeline/tests/optimizer/test_view_builder_phase2.py` — 신규 11개 test
- Modify `scripts/backfill_daily_report_views_v2.py:40-47` — `_JSONB_COLS` 9 컬럼 확장 (update_one 은 dynamic, 별도 변경 없음 — 검증 step 포함)
- Create `scripts/backfill_chroma_daily_activities.py` — 530일 ChromaDB upsert (atomizer 의 `_format_document` re-export)
- Create `scripts/audit_phase2_snapshot.py` — backup_20260521 snapshot 검증
- Create `scripts/audit_phase2_where_filter.sh` — WHERE 절 grep guard
- Create `scripts/rollback_phase2_jsonb.sh` — L2 rollback (UPDATE daily_reports FROM backup)

**BE Routes / Lib (TypeScript) — 9 위치 정확한 line**
- Modify `web/lib/transforms.ts:92, 93, 199, 309, 310` — mapper SQL 5 곳 WHERE
- Modify `web/app/api/mock/agent-tasks/route.ts:62` — JOIN mapper WHERE
- Modify `web/app/api/mock/review/route.ts:33` — mapper SELECT WHERE
- Modify `web/app/api/mock/consolidated/route.ts:40-130` — SQL refactor (site_id 하드코딩 + bp_summaries disc_abbrev jsonb filter + LEFT JOIN mapper_activities for ZONE fallback)
- Modify `web/lib/fixtures.ts:134` — sites_summary review_pending SQL WHERE

**FE Component Modifications (textContent 만 — 디자인 가드)**
- Modify `web/app/components/reports/WPSummaryTable.tsx:82` — `{row.productivity.toFixed(1)}%`
- Modify `web/app/components/charts/QuadrantScatter.tsx:45` — 동일 형식
- Modify `web/app/components/export/ConsolidatedReportCard.tsx:21` — 탭 라벨 "1. 작업사항"
- Modify `web/app/components/export/SheetTable.tsx:86-98` — OUTPUT_MANPOWER_COLS 의 `early/day/overtime` const 제거

**Dashboard swap**
- Modify `web/app/api/mock/dashboard/route.ts` — loadFixture → loadReal
- Modify `web/lib/fixtures.ts` — loadReal 시그니처에 `dashboard_performance` / `dashboard_impact` 추가

---

## ⚠ 명시적 결정 사항 (구현 시 의사결정 0)

이 plan 안에 결정된 사항. 구현자는 임의 선택 금지.

| 결정 | 명시 위치 |
|---|---|
| `_format_document` import = `from pipeline.agents.atomizer import _format_document` | Task C11 |
| `_format_document` 의 `date` 인자 = `r["report_date"].isoformat()` (str) | Task C11 |
| ChromaDB backfill 시 `perperson` / `productivity_pct` 전달하여 full body 사용 | Task C11 |
| quadrant dict 에 `company`, `l7_5_activity`, `workers` 키 추가 | Task C2 |
| `_build_deterministic_cold_start` 의 `master is None` 시 fallback diagnosis | Task C5 |
| `_build_deterministic_cold_start` 의 `unit is None` 시 fallback unit text | Task C5 |
| `_build_optimizer_view` 통합 lookup keys | Task C7 |
| `_build_scenarios` schema = placeholder (FE 미사용, 시연 critical path 아님) | Task C8 |
| `_build_s_curve` schema = `{date, planned, actual}` (recovery 키 생략) | Task C8 |
| `update_one` 은 이미 dynamic — `_JSONB_COLS` 만 확장 → grep 검증 step 포함 | Task C10 |
| `types.ts` 의 `OutputManpowerRow` 은 **건드리지 않음** — BE 가 emit 해도 FE 가 안 render | Task F1 |
| consolidated route SQL = before/after 전체 diff 명시 | Task B3 |
| Phase D 4번째 iteration fallback = `_build_deterministic_cold_start` 의 templates 그대로 유지하고 UI 가드는 "v1 형식" 으로 ship | Task D2 |
| L2 rollback task = R1 (Phase H 이후 별도 trigger) | Task R1 |

---

## Phase A — 안전망 setup (30분)

### Task A1: backup_20260521 snapshot audit script

**Files:**
- Create: `scripts/audit_phase2_snapshot.py`

- [ ] **Step 1: 신규 script 작성**

```python
"""Phase 2 안전망 — backup_20260521 6 테이블 row count snapshot 저장/검증."""
from __future__ import annotations
import argparse, asyncio, json, os
from datetime import datetime
from pathlib import Path
import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
DSN = os.environ["POSTGRES_URL"]
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "docs/superpowers/audit/phase2_backup_snapshot.json"
TABLES = ["mapper_activities", "parser_activities", "pipeline_runs",
          "parser_reports", "daily_reports", "forecasts"]


async def collect() -> dict[str, int]:
    conn = await asyncpg.connect(DSN)
    try:
        return {t: await conn.fetchval(f"SELECT COUNT(*) FROM backup_20260521.{t}") for t in TABLES}
    finally:
        await conn.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    current = await collect()
    if args.save:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(
            {"taken_at": datetime.now().isoformat(), "counts": current},
            ensure_ascii=False, indent=2))
        print(f"saved: {SNAPSHOT_PATH}")
        for t, n in current.items():
            print(f"  {t}: {n}")
    elif args.verify:
        if not SNAPSHOT_PATH.exists():
            raise SystemExit("snapshot 없음 — --save 먼저")
        saved = json.loads(SNAPSHOT_PATH.read_text())["counts"]
        diff = [(t, saved[t], current[t]) for t in TABLES if saved[t] != current[t]]
        if diff:
            for t, a, b in diff:
                print(f"  MISMATCH {t}: saved={a} now={b}")
            raise SystemExit(f"backup_20260521 변경 감지 {len(diff)}건")
        print("verified: backup_20260521 6 테이블 byte-exact 일치")
    else:
        raise SystemExit("--save 또는 --verify 지정")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: snapshot 저장**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/audit_phase2_snapshot.py --save`
Expected: 6 테이블 count 출력 (mapper_activities: 239344 / parser_activities: 239344 / pipeline_runs: 535 / parser_reports: 530 / daily_reports: 535 / forecasts: 48992)

- [ ] **Step 3: verify sanity (작업 전 1회)**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/audit_phase2_snapshot.py --verify`
Expected: `verified: backup_20260521 6 테이블 byte-exact 일치`

- [ ] **Step 4: Commit**

```bash
git add scripts/audit_phase2_snapshot.py docs/superpowers/audit/phase2_backup_snapshot.json
git commit -m "feat(phase2): backup_20260521 snapshot audit (Task A1)"
```

### Task A2: WHERE 절 grep guard script (tightened regex)

**Files:**
- Create: `scripts/audit_phase2_where_filter.sh`

- [ ] **Step 1: 신규 shell script — deterministic substring 검증 (regex 회피)**

```bash
#!/usr/bin/env bash
# Phase 2 — `WHERE ... ma.trade IN ('건축', '토목')` 또는 `AND ma.trade IN ('건축','토목')`
# 가 9 위치 모두에 적용됐는지 deterministic 검증 (regex glob 회피).
set -euo pipefail
cd "$(dirname "$0")/.."

declare -A EXPECTED=(
  ["web/lib/transforms.ts"]=5
  ["web/app/api/mock/agent-tasks/route.ts"]=1
  ["web/app/api/mock/review/route.ts"]=1
  ["web/app/api/mock/consolidated/route.ts"]=1
  ["web/lib/fixtures.ts"]=1
  ["pipeline/agents/optimizer/view_builder.py"]=1
  ["scripts/backfill_chroma_daily_activities.py"]=1
)

fail=0
for f in "${!EXPECTED[@]}"; do
  # substring check — 따옴표 단/이중, 공백 유무 모두 매칭. `tradeXIN` 같은 false positive 방지 위해 단어 경계 grep.
  hits=$(grep -cE "(ma\.trade|^[[:space:]]*trade|, ?ma\.trade) IN[[:space:]]*\((['\"])건축\\2,[[:space:]]*(['\"])토목\\3\)" "$f" 2>/dev/null || true)
  need="${EXPECTED[$f]}"
  if [ "${hits:-0}" -lt "$need" ]; then
    echo "FAIL $f: hits=${hits} need=$need"
    fail=1
  else
    echo "OK   $f: hits=${hits}"
  fi
done

[ $fail -eq 0 ] || exit 1
echo "verified: 9 위치 모두 'trade IN' 필터 적용"
```

- [ ] **Step 2: 권한 부여 + 즉시 실행 (Phase B 전 — 모두 FAIL 기대)**

Run: `chmod +x scripts/audit_phase2_where_filter.sh && ./scripts/audit_phase2_where_filter.sh`
Expected: 모든 9 위치 FAIL hits=0

- [ ] **Step 3: Commit**

```bash
git add scripts/audit_phase2_where_filter.sh
git commit -m "feat(phase2): WHERE filter grep guard (Task A2)"
```

---

## Phase B — BE WHERE 필터 (1시간)

### Task B1: transforms.ts 5 위치 WHERE 추가

**Files:**
- Modify: `web/lib/transforms.ts:92, 93, 199, 309, 310`

- [ ] **Step 1: 5 곳 각각에 `AND ma.trade IN ('건축', '토목')` 추가**

각 SQL 의 정확한 변경:

```diff
# line 92 (deriveStageProgress mapper_acts count)
-      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date}) AS mapper_acts,
+      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND ma.trade IN ('건축', '토목')) AS mapper_acts,

# line 93 (hil_received)
-      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND ma.requires_review) AS hil_received,
+      (SELECT COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id) WHERE pr.report_date = ${date} AND ma.requires_review AND ma.trade IN ('건축', '토목')) AS hil_received,

# line 199 (wbsTreeBuild FROM mapper_activities ma) — 같은 SELECT 의 WHERE 절 끝에 추가
-      WHERE pr.site_id = ${siteId}
+      WHERE pr.site_id = ${siteId} AND ma.trade IN ('건축', '토목')

# line 309 (deriveChatSequence mapper_count)
-      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id) AS mapper_count,
+      (SELECT COUNT(*) FROM mapper_activities ma WHERE ma.run_id = pr.run_id AND ma.trade IN ('건축', '토목')) AS mapper_count,

# line 310 (hil_count)
-      (SELECT COUNT(*) FROM mapper_activities WHERE run_id = pr.run_id AND requires_review) AS hil_count,
+      (SELECT COUNT(*) FROM mapper_activities ma WHERE ma.run_id = pr.run_id AND ma.requires_review AND ma.trade IN ('건축', '토목')) AS hil_count,
```

- [ ] **Step 2: grep guard 부분 검증**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: transforms.ts: hits=5 (다른 8 파일 아직 0)

- [ ] **Step 3: Commit**

```bash
git add web/lib/transforms.ts
git commit -m "feat(phase2): transforms.ts 5 위치 WHERE trade IN (Task B1)"
```

### Task B2: agent-tasks / review / fixtures 3 위치

**Files:**
- Modify: `web/app/api/mock/agent-tasks/route.ts:62`
- Modify: `web/app/api/mock/review/route.ts:33`
- Modify: `web/lib/fixtures.ts:134`

- [ ] **Step 1: agent-tasks/route.ts:62 — `FROM mapper_activities ma` 의 WHERE 절 끝에 추가**

```diff
-      WHERE pr.report_date = ${dStr} AND ma.is_mock = ${useMock}
+      WHERE pr.report_date = ${dStr} AND ma.is_mock = ${useMock} AND ma.trade IN ('건축', '토목')
```

- [ ] **Step 2: review/route.ts:33 — `FROM mapper_activities ma` 의 WHERE 절 끝**

```diff
-      AND ma.requires_review = TRUE
-      AND ma.is_mock = ${useMock}
+      AND ma.requires_review = TRUE
+      AND ma.is_mock = ${useMock}
+      AND ma.trade IN ('건축', '토목')
```

- [ ] **Step 3: fixtures.ts:134 — `FROM mapper_activities` (alias 없음) 의 WHERE 절**

```diff
-        FROM mapper_activities
-        WHERE requires_review = true
-          AND is_mock = ${useMock}
+        FROM mapper_activities ma
+        WHERE ma.requires_review = true
+          AND ma.is_mock = ${useMock}
+          AND ma.trade IN ('건축', '토목')
```

- [ ] **Step 4: grep guard**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: transforms 5 / agent-tasks 1 / review 1 / fixtures 1 — 8 hit (consolidated/view_builder/backfill_chroma 아직 0)

- [ ] **Step 5: Commit**

```bash
git add web/app/api/mock/agent-tasks/route.ts web/app/api/mock/review/route.ts web/lib/fixtures.ts
git commit -m "feat(phase2): agent-tasks/review/fixtures WHERE trade IN (Task B2)"
```

### Task B3: consolidated route SQL refactor — site_id 하드코딩 + disc_abbrev jsonb filter + ZONE LEFT JOIN

**Files:**
- Modify: `web/app/api/mock/consolidated/route.ts:40-150`

**중요**: 단순 WHERE 추가 아님 — SQL refactor 임. before/after 명시.

- [ ] **Step 1: dates 리스트 SQL (line ~48) — site_id 하드코딩 추가**

```diff
-    const dates = (await (sql as any)`
-      SELECT DISTINCT pr.report_date
-      FROM pipeline_runs pr
-      WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
-        AND pr.is_mock = ${useMock}
+    const dates = (await (sql as any)`
+      SELECT DISTINCT pr.report_date
+      FROM pipeline_runs pr
+      WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
+        AND pr.is_mock = ${useMock}
+        AND pr.site_id = 'm15x-ph3-ibl'
```

- [ ] **Step 2: sheet_row_counts SQL (line ~60-87) — jsonb_array_length 에 disc_abbrev filter**

```diff
-          COALESCE((
-            SELECT jsonb_array_length(bp_summaries)
-            FROM parser_reports WHERE report_date = ${dStr} AND is_mock = ${useMock}
-            ORDER BY created_at DESC LIMIT 1
-          ), 0) AS output_count,
+          COALESCE((
+            SELECT jsonb_array_length(jsonb_path_query_array(bp_summaries, '$[*] ? (@.disc_abbrev == "건축" || @.disc_abbrev == "토목")'))
+            FROM parser_reports WHERE report_date = ${dStr} AND is_mock = ${useMock}
+            ORDER BY created_at DESC LIMIT 1
+          ), 0) AS output_count,
```

(occupation_count, equipment_count 도 동일 패턴 — `job_allocations`, `equipment_allocations`)

```diff
-          (
-            SELECT COUNT(*)
-            FROM parser_activities pa
-            JOIN pipeline_runs pr USING (run_id)
-            WHERE pr.report_date = ${dStr}
-              AND pa.is_mock = ${useMock}
-          ) AS quantity_count
+          (
+            SELECT COUNT(*)
+            FROM parser_activities pa
+            JOIN pipeline_runs pr USING (run_id)
+            JOIN mapper_activities ma ON ma.run_id = pa.run_id AND ma.idx = pa.idx
+            WHERE pr.report_date = ${dStr}
+              AND pa.is_mock = ${useMock}
+              AND ma.trade IN ('건축', '토목')
+          ) AS quantity_count
```

- [ ] **Step 3: detail SQL bp_summaries fetch (line ~106-115) — disc_abbrev jsonb filter**

```diff
-  const reportRows = (await (sql as any)`
-    SELECT bp_summaries, job_allocations, equipment_allocations
-    FROM parser_reports
-    WHERE report_date = ${date}
-      AND is_mock = ${useMock}
-    ORDER BY created_at DESC
-    LIMIT 1
-  `) as Array<{
+  const reportRows = (await (sql as any)`
+    SELECT
+      jsonb_path_query_array(bp_summaries,           '$[*] ? (@.disc_abbrev == "건축" || @.disc_abbrev == "토목")') AS bp_summaries,
+      jsonb_path_query_array(job_allocations,        '$[*] ? (@.disc_abbrev == "건축" || @.disc_abbrev == "토목")') AS job_allocations,
+      jsonb_path_query_array(equipment_allocations,  '$[*] ? (@.disc_abbrev == "건축" || @.disc_abbrev == "토목")') AS equipment_allocations
+    FROM parser_reports
+    WHERE report_date = ${date}
+      AND is_mock = ${useMock}
+    ORDER BY created_at DESC
+    LIMIT 1
+  `) as Array<{
```

- [ ] **Step 4: parser_activities SELECT (acts) — LEFT JOIN mapper + WHERE trade**

```diff
-  const acts = (await (sql as any)`
-    SELECT pa.zone, pa.trade, pa.bp_code, pa.company, pa.scope,
-           pa.work_content, pa.unit, pa.plan_total_qty, pa.yesterday_cum_qty, pa.today_qty
-    FROM parser_activities pa
-    JOIN pipeline_runs pr USING (run_id)
-    WHERE pr.report_date = ${date}
-      AND pa.is_mock = ${useMock}
+  const acts = (await (sql as any)`
+    SELECT COALESCE(NULLIF(pa.zone, ''), split_part(ma.wa, '-', 1), '—') AS zone,
+           pa.trade, pa.bp_code, pa.company, pa.scope,
+           pa.work_content, pa.unit, pa.plan_total_qty, pa.yesterday_cum_qty, pa.today_qty
+    FROM parser_activities pa
+    JOIN pipeline_runs pr USING (run_id)
+    JOIN mapper_activities ma ON ma.run_id = pa.run_id AND ma.idx = pa.idx
+    WHERE pr.report_date = ${date}
+      AND pa.is_mock = ${useMock}
+      AND ma.trade IN ('건축', '토목')
+      AND pr.site_id = 'm15x-ph3-ibl'
```

- [ ] **Step 5: 5536 dev server reload → /export 페이지에서 9-25 일자 클릭 sanity**

수동 — 1번 탭 ZONE 컬럼이 'FAB' / 'CUB' 등 채워지는지, 비건축·비토목 row 가 사라졌는지 확인 (commit 후 검증).

- [ ] **Step 6: grep guard**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: consolidated 1 hit (9 hit 누적)

- [ ] **Step 7: Commit**

```bash
git add web/app/api/mock/consolidated/route.ts
git commit -m "feat(phase2): consolidated route — site_id + disc_abbrev jsonb filter + ZONE fallback (Task B3)"
```

### Task B4: view_builder.py:928 mapper SELECT WHERE 추가

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:928`

- [ ] **Step 1: WHERE 절 끝에 `AND ma.trade IN ('건축', '토목')` 추가**

```diff
          WHERE ma.report_date = $1
            AND pr.site_id = $2
            AND ma.l7_5_activity IS NOT NULL
            AND m.ps IS NOT NULL AND $1 BETWEEN m.ps AND m.pf
+           AND ma.trade IN ('건축', '토목')
```

- [ ] **Step 2: 기존 pytest 통과 (view_builder 회귀 0)**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_v2.py -v`
Expected: 16 test 모두 PASS

- [ ] **Step 3: grep guard**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: view_builder 1 hit. 누적 10 hit (backfill_chroma 아직 신규 작성 전이라 0)

- [ ] **Step 4: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py
git commit -m "feat(phase2): view_builder SQL WHERE trade IN (Task B4)"
```

### Task B5: backup_20260521 무변화 검증 (Phase B 끝)

- [ ] **Step 1: snapshot verify**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/audit_phase2_snapshot.py --verify`
Expected: `verified: backup_20260521 6 테이블 byte-exact 일치`

- [ ] **Step 2: public schema row 수 무변화**

Run: `psql -At "$POSTGRES_URL" -c "SELECT 'mapper', COUNT(*) FROM public.mapper_activities WHERE is_mock=FALSE UNION ALL SELECT 'parser', COUNT(*) FROM public.parser_activities"`
Expected: `mapper|239344` `parser|239344` (그대로)

---

## Phase C — BE 코드 변경 (6~8h)

### Task C1: 신규 test 파일 — _wp_id_of import sanity

**Files:**
- Create: `pipeline/tests/optimizer/test_view_builder_phase2.py`

- [ ] **Step 1: 신규 test 파일 작성**

```python
"""Phase 2 view_builder + retrieve + backfill 변경 검증."""
from __future__ import annotations
import pytest
from pipeline.agents.optimizer.view_builder import _wp_id_of


def test_wp_id_of_kebab_format():
    """_wp_id_of 가 kebab-case + lowercase 반환."""
    assert _wp_id_of("FAB-A02", "철근콘크리트공사", "남웅건설") == "fab-a02-철근콘크리트공사-남웅건설"
    assert _wp_id_of(None, "방수공사", "동성건업") == "unknown-방수공사-동성건업"
    assert _wp_id_of("CUB", "방수공사", None) == "cub-방수공사-unknown"
```

- [ ] **Step 2: Run PASS (이미 _wp_id_of 존재)**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_phase2.py::test_wp_id_of_kebab_format -v`
Expected: PASS

### Task C2: view_builder wp_id 통일 + ma.wa SELECT + quadrant dict 확장

**중요**: quadrant 에 `company`, `l7_5_activity`, `workers` 키 추가 → C7 의 lookup 가능.

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:928-930` (SELECT 컬럼 추가)
- Modify: `pipeline/agents/optimizer/view_builder.py:1087-1103` (quadrant dict)
- Modify: `pipeline/agents/optimizer/view_builder.py:1104-1126` (wp_summary dict)

- [ ] **Step 1: SELECT 에 ma.wa + ma.today_qty + ma.assigned_workers 추가**

view_builder.py:929-932 의 SELECT list 변경 — 정확히 12 → 15 컬럼:

```diff
-        SELECT ma.id, pr.site_id, ma.run_id, ma.company, ma.l6_main, ma.l7_5_activity,
-               ma.unit, ma.zone, m.ps AS plan_start, m.pf AS plan_finish,
-               m.qty AS plan_total_qty, m.mh AS plan_mh
+        SELECT ma.id, pr.site_id, ma.run_id, ma.company, ma.l6_main, ma.l7_5_activity,
+               ma.unit, ma.zone, ma.wa, ma.today_qty, ma.assigned_workers,
+               m.ps AS plan_start, m.pf AS plan_finish,
+               m.qty AS plan_total_qty, m.mh AS plan_mh
```

(items[] downstream 에서 `it["today_qty"]`, `it["assigned_workers"]`, `it["wa"]` 접근 가능)

- [ ] **Step 2: quadrant dict 에 company / l7_5_activity / workers / l6_main 키 추가**

view_builder.py:1087-1103:

```diff
  quadrant = [
      {
          "wp_id": f"WP-{it['id']}",
          "wp_name": it["l7_5_activity"],
+         "l7_5_activity": it["l7_5_activity"],
+         "company": it["company"],
+         "l6_main": it["l6_main"],
+         "workers": int(it.get("assigned_workers") or 1),
          "trade": it["l6_main"],
          "productivity": round(it["productivity"], 1),
          "impact": round(it["impact"], 1),
          "quadrant": _quadrant_of(it["productivity"], it["impact"]),
          "size": round((it["plan_total_qty"] or 1) / 10, 1),
          "perperson": round(it["perperson"], 2),
          "perperson_unit": f"{it['unit']}/인" if it["unit"] else None,
          "display_label": _make_display_label(
              it["productivity"], it["perperson"], it["unit"]
          ),
      }
      for it in items
  ]
```

- [ ] **Step 3: quadrant 의 wp_id 를 `_wp_id_of` 로 변경**

```diff
-         "wp_id": f"WP-{it['id']}",
+         "wp_id": _wp_id_of(it["wa"], it["l6_main"], it["company"]),
```

- [ ] **Step 4: wp_summary 의 wp_id 변경 (view_builder.py:1106)**

```diff
-         "wp_id": f"WP-{it['id']}",
+         "wp_id": _wp_id_of(it["wa"], it["l6_main"], it["company"]),
```

- [ ] **Step 5: failing test 추가 (quadrant 새 키 확인)**

`test_view_builder_phase2.py` 에 추가:

```python
@pytest.mark.asyncio
async def test_quadrant_has_new_keys(real_pg):
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2
    result = await _build_productivity_views_v2(real_pg, "m15x-ph3-ibl", date(2025, 9, 25))
    for q in result["quadrant"]:
        assert "l7_5_activity" in q
        assert "company" in q
        assert "l6_main" in q
        assert "workers" in q
        assert isinstance(q["workers"], int)
        # wp_id 가 kebab format (정수 아님)
        assert not q["wp_id"].startswith("WP-")
```

- [ ] **Step 6: Run pytest — PASS (실제 PG 호출)**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_phase2.py::test_quadrant_has_new_keys -v -s`
Expected: PASS

- [ ] **Step 7: 기존 16 test 회귀 0 확인**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_v2.py -v`
Expected: 16 PASS

- [ ] **Step 8: Commit**

```bash
git add pipeline/agents/optimizer/view_builder.py pipeline/tests/optimizer/test_view_builder_phase2.py
git commit -m "feat(phase2): view_builder wp_id 통일 + quadrant 키 4개 추가 (Task C2)"
```

### Task C3: _build_productivity_views_v2 return 9 key (stub)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1171-1178`

- [ ] **Step 1: failing test 추가**

```python
@pytest.mark.asyncio
async def test_returns_9_keys(real_pg):
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2
    result = await _build_productivity_views_v2(real_pg, "m15x-ph3-ibl", date(2025, 9, 25))
    expected = {"kpi", "productivity", "contractor_bars", "trade_bars",
                "quadrant", "wp_summary", "optimizer_view", "scenarios", "s_curve"}
    assert set(result.keys()) >= expected
```

- [ ] **Step 2: FAIL (6 key 만)**

Run: `pytest test_returns_9_keys -v`
Expected: FAIL

- [ ] **Step 3: stub 3 key 추가**

view_builder.py:1171 return dict 끝:

```diff
  return {
      "kpi": kpi, "productivity": productivity_dict,
      "contractor_bars": contractor_bars, "trade_bars": trade_bars,
      "quadrant": quadrant, "wp_summary": wp_summary,
+     "optimizer_view": {"by_wp": {}, "default_wp_id": None},
+     "scenarios": {"site": {}, "by_wp": {}},
+     "s_curve": [],
  }
```

- [ ] **Step 4: PASS**

Run: `pytest test_returns_9_keys -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(phase2): view_builder return 9 key (stub) (Task C3)"
```

### Task C4: _build_wa_lookup 헬퍼

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` (신규 함수)

- [ ] **Step 1: failing test**

```python
def test_build_wa_lookup():
    from pipeline.agents.optimizer.view_builder import _build_wa_lookup
    items = [
        {"wa": "FAB", "l6_main": "철근콘크리트공사", "company": "남웅건설"},
        {"wa": "CUB", "l6_main": "철근콘크리트공사", "company": "남웅건설"},
        {"wa": "FAB", "l6_main": "방수공사", "company": "동성건업"},
        {"wa": None, "l6_main": "방수공사", "company": "동성건업"},
    ]
    lookup = _build_wa_lookup(items)
    assert lookup[("철근콘크리트공사", "남웅건설")] == ["FAB", "CUB"]
    assert lookup[("방수공사", "동성건업")] == ["FAB"]
```

- [ ] **Step 2: FAIL**

Run: `pytest test_build_wa_lookup -v`
Expected: FAIL ImportError

- [ ] **Step 3: 구현 (view_builder.py 의 _wp_id_of 함수 아래 추가)**

```python
def _build_wa_lookup(items: list[dict]) -> dict[tuple[str, str], list[str]]:
    """(l6_main, company) → DISTINCT wa list — _build_optimizer_view fan-out 용."""
    out: dict[tuple[str, str], list[str]] = {}
    for it in items:
        wa = it.get("wa")
        if not wa:
            continue
        key = (it["l6_main"], it["company"])
        out.setdefault(key, [])
        if wa not in out[key]:
            out[key].append(wa)
    return out
```

- [ ] **Step 4: PASS + Commit**

Run: `pytest test_build_wa_lookup -v`
Expected: PASS

```bash
git commit -am "feat(phase2): _build_wa_lookup (Task C4)"
```

### Task C5: _build_deterministic_cold_start — 8 cause 분기 + 5 rule + edge case

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` (신규 함수 4개: `_pick_cause`, `_pick_recommendations`, `_compose_diagnosis`, `_build_deterministic_cold_start`)

- [ ] **Step 1: failing test — 정상 케이스**

```python
def test_deterministic_cold_start_diagnosis_format_and_length():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start
    q = {"wp_id": "fab-x-y", "perperson": 1.70, "perperson_unit": "m³/인",
         "impact": 65.0, "trade": "건축", "workers": 3, "company": "남웅건설",
         "l7_5_activity": "무근 콘크리트 타설", "l6_main": "철근콘크리트공사"}
    master = {"daily_qty": 25.0, "daily_workers": 10, "unit": "m³"}
    result = _build_deterministic_cold_start(q, master, [], workers=3, risk_level="이상", delay_days=2)
    assert "보통 인당 2.50 m³" in result["diagnosis"]
    assert "오늘은 인당 1.70 m³ (68.0%)" in result["diagnosis"]
    assert len(result["diagnosis"]) <= 140
    assert result["source"] == "deterministic_cold_start"
```

- [ ] **Step 2: failing test — `master is None` 케이스 (edge)**

```python
def test_deterministic_cold_start_master_none_fallback():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start
    q = {"wp_id": "fab-x", "perperson": 1.70, "perperson_unit": "m³/인",
         "impact": 50.0, "trade": "건축", "workers": 3, "company": "남웅", "l7_5_activity": "X", "l6_main": "Y"}
    result = _build_deterministic_cold_start(q, None, [], workers=3, risk_level="—", delay_days=0)
    # master is None — diagnosis 는 "마스터 baseline 없음" 명시
    assert "마스터 데이터 없음" in result["diagnosis"]
    assert "1.70 m³/인" in result["diagnosis"]
    assert result["source"] == "deterministic_cold_start_no_master"
```

- [ ] **Step 3: failing test — `unit is None` (edge)**

```python
def test_deterministic_cold_start_unit_none_safe():
    from pipeline.agents.optimizer.view_builder import _build_deterministic_cold_start
    q = {"wp_id": "x", "perperson": 1.0, "perperson_unit": None,
         "impact": 30.0, "trade": "건축", "workers": 2, "company": "X", "l7_5_activity": "Y", "l6_main": "Z"}
    master = {"daily_qty": 10, "daily_workers": 10, "unit": None}
    # crash 없이 정상 반환 — unit fallback 으로 "단위미상" 사용
    result = _build_deterministic_cold_start(q, master, [], workers=2, risk_level="정상", delay_days=0)
    assert "단위미상" in result["diagnosis"]
    assert result["source"] in ("deterministic_cold_start", "deterministic_cold_start_no_master")
```

- [ ] **Step 4: failing test — cause 8 분기 parametrize**

```python
@pytest.mark.parametrize("pct,impact,delay,trade,expected_substr", [
    (45, 90, 6, "건축", "후속 양생 의존성"),    # pct<50 impact>80
    (50, 70, 3, "건축", "장비 가용성"),         # pct<60 impact>60
    (65, 40, 5, "토목", "선행 작업 지연"),      # pct<70 delay>2
    (65, 60, 0, "건축", "인력 분산"),           # pct<70 impact>50
    (75, 30, 0, "토목", "기상 영향"),           # 70<=pct<80 토목
    (75, 30, 0, "건축", "동시 작업 간섭"),      # 70<=pct<80 건축
    (85, 20, 0, "건축", "자재 대기"),           # 80<=pct<90
    (95, 10, 0, "건축", ""),                    # pct>=90 cause 없음
])
def test_pick_cause_8_branches(pct, impact, delay, trade, expected_substr):
    from pipeline.agents.optimizer.view_builder import _pick_cause
    cause = _pick_cause(pct, impact, delay, trade)
    if expected_substr:
        assert expected_substr in cause, f"({pct},{impact},{delay},{trade}) → {cause!r}"
    else:
        assert cause == ""
```

- [ ] **Step 5: failing test — recommendations rule 매트릭스 (5 rule, 조합형)**

각 룰이 **독립적으로** trigger 되는 조합형. spec §2.4 의 "R1+R2 동시 hit" 가능.

```python
@pytest.mark.parametrize("pct,impact,delay,workers,trade,expected_count,expected_substrs", [
    (65, 60, 0, 3, "건축", 1, ["인력 +1"]),                          # R1 only
    (65, 60, 3, 3, "건축", 2, ["인력 +1", "후속 작업"]),             # R1 + R2
    (75, 20, 0, 3, "건축", 1, ["선행 토목"]),                        # R3 (건축 + pct<80)
    (50, 25, 0, 3, "건축", 1, ["장비 가용성"]),                      # R4
    (95, 5,  0, 3, "건축", 1, ["현 페이스 유지"]),                   # R5
    (40, 90, 5, 2, "건축", 4, ["인력 +1", "후속 작업", "선행 토목", "장비"]),  # R1+R2+R3+R4
])
def test_pick_recommendations_combinations(pct, impact, delay, workers, trade, expected_count, expected_substrs):
    from pipeline.agents.optimizer.view_builder import _pick_recommendations
    recs = _pick_recommendations(pct, impact, delay, workers, trade)
    assert len(recs) == expected_count, f"got {recs}"
    for sub in expected_substrs:
        assert any(sub in r for r in recs), f"missing {sub!r} in {recs}"
```

- [ ] **Step 6: All FAIL**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_phase2.py -v`
Expected: 위 5 신규 test 모두 FAIL

- [ ] **Step 7: 구현 (view_builder.py 의 _build_wa_lookup 아래 추가)**

```python
def _pick_cause(pct: float, impact: float, delay_days: int, trade: str) -> str:
    """8 cause 분기 — productivity × impact × delay × trade."""
    if pct < 50 and impact > 80:
        return "인력 분산 + 후속 양생 의존성"
    if pct < 60 and impact > 60:
        return "장비 가용성 저하 + 후속 작업 영향"
    if pct < 70 and delay_days > 2:
        return "선행 작업 지연 파급"
    if pct < 70 and impact > 50:
        return "인력 분산 또는 후속 작업 의존성에 따른 페이스 저하 가능성"
    if 70 <= pct < 80 and trade == "토목":
        return "기상 영향 또는 토공 진행 조건 저하"
    if 70 <= pct < 80:
        return "동시 작업 간섭 또는 자재 대기에 따른 일시적 감소 가능성"
    if 80 <= pct < 90:
        return "자재 대기 또는 양생 sequence 영향"
    return ""  # pct >= 90 정상 범위


def _pick_recommendations(pct, impact, delay_days, workers, trade):
    """5 rule 조합형 — 각 룰 독립 평가 (R3/R4/R5 guard 제거)."""
    recs = []
    if pct < 70 and impact > 50:
        recs.append(f"인력 +1명 검토 (현 {workers}명 → {workers + 1}명, 회복 단축 기대)")
    if delay_days > 2:
        recs.append("후속 작업 일정 영향 확인")
    if trade == "건축" and pct < 80:
        recs.append("선행 토목 인터페이스 점검")
    if pct < 60 and impact >= 20:
        recs.append("장비 가용성 / 자재 수급 확인")
    if 90 <= pct < 100 and delay_days == 0:
        recs.append("현 페이스 유지 — 검증 완료")
    return recs


def _compose_diagnosis(pp_master, pp_today, pct, unit, cause):
    """최대 140자 보장 — 초과 시 cause 절 trim."""
    base = (f"이 작업은 보통 인당 {pp_master:.2f} {unit} 작업하는데, "
            f"오늘은 인당 {pp_today:.2f} {unit} ({pct:.1f}%) 로 작업했습니다.")
    full = base + (f" {cause}" if cause else "")
    return full if len(full) <= 140 else base


def _compose_diagnosis_no_master(pp_today, unit):
    """master 없음 시 단순 진단 (140자 보장)."""
    return f"마스터 데이터 없음. 오늘 인당 {pp_today:.2f} {unit} 작업. 비교 기준 미생성 — 후속 마스터 적재 후 진단 재산출."


def _build_deterministic_cold_start(q, master, chroma_cases, *, workers, risk_level, delay_days):
    pp_today = float(q.get("perperson") or 0)
    unit_full = q.get("perperson_unit") or "단위미상/인"
    unit = unit_full.split("/")[0] if "/" in unit_full else "단위미상"
    impact = float(q.get("impact", 0))
    trade = q.get("trade", "")

    if master is None or not master.get("daily_workers"):
        diagnosis = _compose_diagnosis_no_master(pp_today, unit)
        pp_master = 0.0
        pct = 0.0
        source = "deterministic_cold_start_no_master"
        cause = ""
    else:
        pp_master = master["daily_qty"] / max(master["daily_workers"], 1)
        pct = (pp_today / pp_master * 100) if pp_master else 0
        cause = _pick_cause(pct, impact, delay_days, trade)
        diagnosis = _compose_diagnosis(pp_master, pp_today, pct, unit, cause)
        source = "deterministic_cold_start"

    similar_cases = [
        {
            "date": c.get("date") or "",
            "description": f"{c.get('company') or ''} · {c.get('l7_5_activity') or ''} · "
                           f"{(c.get('pp_then') or 0):.2f} {unit} ({(c.get('pct_then') or 0):.0f}%)",
            "outcome": (f"{c.get('recovery_days')}일 후 {(c.get('pp_recovered') or 0):.2f} {unit} "
                        f"({(c.get('pct_recovered') or 0):.0f}%) 회복") if c.get("recovery_days") else "미회복",
        }
        for c in (chroma_cases or [])[:3]
    ]

    recommendations = _pick_recommendations(pct, impact, delay_days, workers, trade)

    details = [
        {"label": "위험 평가", "value": risk_level or "—"},
        {"label": "마스터 인당", "value": f"{pp_master:.2f} {unit}" if pp_master else "—"},
        {"label": "오늘 인당", "value": f"{pp_today:.2f} {unit} ({pct:.1f}%)" if pp_master else f"{pp_today:.2f} {unit}"},
        {"label": "유사 사례", "value": f"{len(chroma_cases or [])}건"},
        {"label": "평균 회복 일수",
         "value": (f"{sum((c.get('recovery_days') or 0) for c in (chroma_cases or []))/max(len(chroma_cases or []),1):.1f}일"
                   if chroma_cases else "—")},
        {"label": "일정 영향", "value": f"+{delay_days}일"},
    ]
    return {"diagnosis": diagnosis, "similar_cases": similar_cases,
            "recommendations": recommendations, "details": details,
            "source": source}
```

- [ ] **Step 8: All PASS**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/test_view_builder_phase2.py -v`
Expected: 모두 PASS

- [ ] **Step 9: Commit**

```bash
git commit -am "feat(phase2): _build_deterministic_cold_start + 8 cause + 5 rule + edge cases (Task C5)"
```

### Task C6: _fetch_chroma_cases_lookup

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` (신규 함수)

- [ ] **Step 1: failing test (ChromaDB sanity, 빈 list OK)**

```python
@pytest.mark.asyncio
async def test_fetch_chroma_cases_lookup_returns_dict():
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _fetch_chroma_cases_lookup
    items = [{"wp_id": "fab-x-방수-남웅", "l7_5_activity": "방수 시공",
              "l6_main": "방수공사", "company": "남웅건설"}]
    lookup = await _fetch_chroma_cases_lookup(items, date(2025, 9, 25))
    assert "fab-x-방수-남웅" in lookup
    assert isinstance(lookup["fab-x-방수-남웅"], list)
```

- [ ] **Step 2: 구현 (3단 fallback chain)**

```python
async def _fetch_chroma_cases_lookup(
    items: list[dict], today: date,
) -> dict[str, list[dict]]:
    """quadrant items 의 wp_id 별 ChromaDB daily_activities 검색.
    Fallback chain: (company, l6, l7_5) → (company, l6) → (l6, l7_5) → 빈 list."""
    from pipeline.chroma_client import ChromaClient
    import os
    chroma = ChromaClient(host=os.environ["CHROMA_HOST"], port=int(os.environ["CHROMA_PORT"]))
    col = chroma.client.get_or_create_collection("daily_activities")
    out: dict[str, list[dict]] = {}
    for it in items:
        wp_id = it["wp_id"]
        l7_5 = it.get("l7_5_activity")
        l6 = it.get("l6_main")
        company = it.get("company")
        cases: list[dict] = []
        for where in (
            ({"$and": [{"company": company}, {"l6_main": l6}, {"l7_5_activity": l7_5}]} if l7_5 else None),
            {"$and": [{"company": company}, {"l6_main": l6}]},
            ({"$and": [{"l6_main": l6}, {"l7_5_activity": l7_5}]} if l7_5 else None),
        ):
            if where is None:
                continue
            try:
                r = col.get(where=where, limit=5, include=["metadatas"])
            except Exception:
                continue
            if r.get("metadatas"):
                cases = r["metadatas"]
                break
        out[wp_id] = cases
    return out
```

- [ ] **Step 3: PASS + Commit**

```bash
git commit -am "feat(phase2): _fetch_chroma_cases_lookup 3단 fallback (Task C6)"
```

### Task C7: _build_optimizer_view 통합 + cold_start 채움

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py:1171` (return dict 직전 통합)

- [ ] **Step 1: failing test (cold_start 비율 = advice 없는 WP)**

```python
@pytest.mark.asyncio
async def test_optimizer_view_all_quadrant_filled(real_pg, real_chroma):
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2
    result = await _build_productivity_views_v2(real_pg, "m15x-ph3-ibl", date(2025, 9, 25))
    q_ids = {q["wp_id"] for q in result["quadrant"]}
    bw_keys = set(result["optimizer_view"]["by_wp"].keys())
    assert q_ids <= bw_keys, f"누락 WP: {q_ids - bw_keys}"
    # 모든 WP 의 diagnosis 비어있지 않음
    for k, v in result["optimizer_view"]["by_wp"].items():
        assert v.get("diagnosis"), f"diagnosis 빔: {k}"
```

- [ ] **Step 2: 통합 코드 추가 — view_builder.py:1171 return 직전**

```python
# Phase 2 — optimizer_view 통합 (advice 매칭 + cold_start fallback)
advice_rows = await pg.fetch_all(
    "SELECT * FROM optimizer_advice WHERE run_id IN "
    "(SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today)
forecast_rows = await pg.fetch_all(
    "SELECT * FROM forecasts WHERE run_id IN "
    "(SELECT run_id FROM pipeline_runs WHERE site_id=$1 AND report_date=$2)",
    site_id, today)

wa_lookup = _build_wa_lookup(items)
optimizer_view = _build_optimizer_view(
    [dict(r) for r in advice_rows],
    [dict(r) for r in forecast_rows],
    items,
    wa_lookup,
)

# cold_start fallback — advice 없는 WP 마다 deterministic 채움
# Lookup keys 명시:
#   master_lookup: (l7_5_activity, company) — items 의 activity_master 그룹
#   forecast_by_wp: (company, l6_main) — forecasts 의 row
master_lookup = {(it["l7_5_activity"], it["company"]): it for it in items}
forecast_by_wp = {(f.get("company"), f.get("l6_main")): dict(f) for f in forecast_rows}
chroma_cases_lookup = await _fetch_chroma_cases_lookup(quadrant, today)

for q in quadrant:
    if q["wp_id"] in optimizer_view["by_wp"]:
        continue
    master = master_lookup.get((q["l7_5_activity"], q["company"]))
    f = forecast_by_wp.get((q["company"], q["l6_main"]), {})
    optimizer_view["by_wp"][q["wp_id"]] = _build_deterministic_cold_start(
        q, master, chroma_cases_lookup.get(q["wp_id"], []),
        workers=int(q.get("workers") or 1),
        risk_level=f.get("risk_level"),
        delay_days=int(f.get("delay_days") or 0),
    )

# return dict 의 stub 값들 교체
```

- [ ] **Step 3: return dict 의 stub 교체 — view_builder.py:1173 영역**

```diff
-     "optimizer_view": {"by_wp": {}, "default_wp_id": None},
+     "optimizer_view": optimizer_view,
```

- [ ] **Step 4: PASS + 회귀 0**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/optimizer/ -v`
Expected: 신규 + 기존 모두 PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(phase2): _build_optimizer_view 통합 + cold_start 채움 (Task C7)"
```

### Task C8: _build_scenarios + _build_s_curve (placeholder schema 명시)

**Files:**
- Modify: `pipeline/agents/optimizer/view_builder.py` (신규 함수 2)

**중요**: FE 가 현재 `scenarios_jsonb` / `s_curve_jsonb` 를 활용하지 않음 (시연 critical path 외 — 검증: `grep -rn "scenarios_jsonb\|s_curve_jsonb" web/` 0 hit). 그래서 placeholder schema 만 채워서 jsonb null 회피.

- [ ] **Step 1: FE 미사용 검증 (placeholder 정당화)**

Run: `grep -rn "scenarios_jsonb\|s_curve_jsonb" web/ 2>/dev/null | head`
Expected: 0 hit (또는 type 정의만 / 실 render 없음)

- [ ] **Step 2: failing test (schema sanity)**

```python
def test_build_scenarios_schema():
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _build_scenarios
    items = [{"wp_id": "x", "company": "남웅", "l6_main": "철근콘크리트공사",
              "wa": "FAB", "productivity": 75, "impact": 50, "plan_total_qty": 100}]
    s = _build_scenarios(items, {"by_wp": {}}, date(2025, 9, 25))
    assert "site" in s and "by_wp" in s
    for k in ("no_action", "optimistic_p25", "base_p50", "pessimistic_p75"):
        assert k in s["site"]
        assert s["site"][k]["case_count"] == 1


def test_build_s_curve_60_points():
    from datetime import date
    from pipeline.agents.optimizer.view_builder import _build_s_curve
    items = [{"plan_total_qty": 100}]
    s = _build_s_curve(items, date(2025, 9, 25))
    assert len(s) == 61    # 60 일 + 종료 포인트
    assert {"date", "planned", "actual"} <= set(s[0].keys())
```

- [ ] **Step 3: 구현**

```python
def _build_scenarios(items: list[dict], optimizer_view: dict, today: date) -> dict:
    """4 scenario placeholder — FE 미사용 (시연 critical path 외)."""
    def _scen(items_subset, ratio):
        delay_sum = sum(max(0, (100 - it.get("productivity", 100)) / 100 * it.get("impact", 0) * ratio)
                        for it in items_subset)
        return {
            "expected_completion": today.isoformat(),
            "recovery_days": int(delay_sum),
            "delta_days": int(delay_sum * 0.1),
            "case_count": len(items_subset),
        }
    ratios = [("no_action", 1.0), ("optimistic_p25", 0.5),
              ("base_p50", 0.7), ("pessimistic_p75", 1.3)]
    site = {k: _scen(items, r) for k, r in ratios}
    by_wp = {it["wp_id"] if "wp_id" in it else _wp_id_of(it.get("wa"), it["l6_main"], it["company"]):
             {k: _scen([it], r) for k, r in ratios} for it in items}
    return {"site": site, "by_wp": by_wp}


def _build_s_curve(items: list[dict], today: date) -> list[dict]:
    """S-curve 60일 시계열 placeholder. FE 미사용."""
    from datetime import timedelta
    days = 60
    start = today - timedelta(days=days)
    total_plan = sum((it.get("plan_total_qty") or 100) for it in items) or 100
    out = []
    for i in range(days + 1):
        d = start + timedelta(days=i)
        progress = i / days
        out.append({
            "date": d.isoformat(),
            "planned": round(total_plan * progress, 1),
            "actual": round(total_plan * progress * 0.85, 1),
        })
    return out
```

- [ ] **Step 4: return dict stub 교체**

```diff
-     "scenarios": {"site": {}, "by_wp": {}},
-     "s_curve": [],
+     "scenarios": _build_scenarios(items, optimizer_view, today),
+     "s_curve": _build_s_curve(items, today),
```

- [ ] **Step 5: PASS + 회귀 0 + Commit**

Run: `pytest pipeline/tests/optimizer/ -v`
Expected: 모두 PASS

```bash
git commit -am "feat(phase2): _build_scenarios + _build_s_curve placeholder (Task C8)"
```

### Task C9: retrieve.py 4 함수 l7_5_activity arg

**Files:**
- Modify: `pipeline/agents/optimizer/retrieve.py:34, 49, 73, 120`

- [ ] **Step 1: failing test**

```python
def test_retrieve_with_l7_5_activity_filter():
    from datetime import date
    from pipeline.agents.optimizer.retrieve import fetch_degradation_cases
    metadatas = [
        {"company": "남웅", "l6_main": "방수공사", "l7_5_activity": "방수 시공",
         "unit": "m2", "today_qty": 10, "assigned_workers": 5, "conditions": "강수"},
        {"company": "남웅", "l6_main": "방수공사", "l7_5_activity": "방수 보수",
         "unit": "m2", "today_qty": 8, "assigned_workers": 4, "conditions": "정상"},
    ]
    cases = fetch_degradation_cases(metadatas, ["d1", "d2"], "남웅", "방수공사",
                                     date(2025, 9, 25), l7_5_activity="방수 시공", top_n=3)
    assert all(c.get("l7_5_activity") == "방수 시공" for c in cases)
```

- [ ] **Step 2: FAIL — TypeError (unexpected kwarg)**

Run: `pytest test_retrieve_with_l7_5_activity_filter -v`
Expected: FAIL

- [ ] **Step 3: 4 함수 시그니처 추가 + 내부 필터**

`pipeline/agents/optimizer/retrieve.py` 의 4 함수:
- `fetch_degradation_cases` (line 34 영역)
- `fetch_recovery_trajectory` (line 73)
- `_group_baseline` (line 49)
- `_group_average_perperson` (line 120)

각 함수 시그니처에 `*, l7_5_activity: Optional[str] = None` 추가. 본문에서 `if m["company"] != company or m["l6_main"] != l6_main: continue` 직후:

```python
if l7_5_activity and m.get("l7_5_activity") != l7_5_activity:
    continue
```

- [ ] **Step 4: PASS + 회귀 0**

Run: `pytest pipeline/tests/ -v`
Expected: 모두 PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(phase2): retrieve.py 4 함수 l7_5_activity arg (Task C9)"
```

### Task C10: backfill_v2 _JSONB_COLS 9 확장 + update_one dynamic 검증

**Files:**
- Modify: `scripts/backfill_daily_report_views_v2.py:40-47`

- [ ] **Step 1: update_one dynamic 검증 (grep)**

Run: `grep -nE "set_clause|for c in _JSONB_COLS|enumerate\\(_JSONB_COLS\\)" scripts/backfill_daily_report_views_v2.py`
Expected:
```
54:    set_clause = ", ".join(f"{c} = ${i + 1}::jsonb" for i, c in enumerate(_JSONB_COLS))
56:    args = [
60:        for k in _JSONB_COLS
```

→ dynamic 확인 — `_JSONB_COLS` 확장만으로 9 컬럼 자동 SET.

- [ ] **Step 2: failing test**

새 test 파일 `pipeline/tests/test_backfill_views_v2_phase2.py`:

```python
def test_jsonb_cols_has_9():
    from scripts.backfill_daily_report_views_v2 import _JSONB_COLS
    expected = {"kpi_jsonb", "productivity_jsonb", "contractor_bars_jsonb",
                "trade_bars_jsonb", "quadrant_jsonb", "wp_summary_jsonb",
                "optimizer_view_jsonb", "scenarios_jsonb", "s_curve_jsonb"}
    assert set(_JSONB_COLS) == expected
```

- [ ] **Step 3: FAIL → 확장**

```diff
  _JSONB_COLS = (
      "kpi_jsonb", "productivity_jsonb", "contractor_bars_jsonb",
      "trade_bars_jsonb", "quadrant_jsonb", "wp_summary_jsonb",
+     "optimizer_view_jsonb", "scenarios_jsonb", "s_curve_jsonb",
  )
```

- [ ] **Step 4: PASS + Commit**

```bash
git commit -am "feat(phase2): backfill_v2 _JSONB_COLS 9 (Task C10)"
```

### Task C11: backfill_chroma_daily_activities.py 신규

**Files:**
- Create: `scripts/backfill_chroma_daily_activities.py`

**중요**: import path = `from pipeline.agents.atomizer import _format_document`. `date` 인자 = `r["report_date"].isoformat()` (str). backfill 모드 → `perperson` / `productivity_pct` 계산해서 전달 (full body).

- [ ] **Step 1: 신규 script 작성**

```python
"""Phase 2 — mapper_activities 530일 (건축+토목) → ChromaDB daily_activities upsert.

import path (검증됨): pipeline.agents.atomizer._format_document
- 시그니처: (a: dict, date: str, perperson: float|None, productivity_pct: float|None) -> str
- backfill 모드 = perperson + productivity_pct 전달 → full body 텍스트
"""
from __future__ import annotations
import argparse, asyncio, hashlib, os
from datetime import date as _date
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

from pipeline.agents.atomizer import _format_document  # 검증됨: atomizer.py:69
from pipeline.chroma_client import ChromaClient
from openai import AzureOpenAI

DSN = os.environ["POSTGRES_URL"]
CHROMA_HOST = os.environ["CHROMA_HOST"]
CHROMA_PORT = int(os.environ["CHROMA_PORT"])
AZ = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
)
EMBED_MODEL = "text-embedding-3-small-ai-board-test"
RUN_ID = "backfill_v2"


def _id_of(r) -> str:
    key = f"{r['report_date']}|{r['l7_5_activity']}|{r['l6_main']}|{r['company']}|{RUN_ID}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


async def fetch_rows(conn, the_date) -> list[dict]:
    """건축+토목 만, distinct (date, l7_5, l6, company) — WHERE filter 적용."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (pr.report_date, ma.l7_5_activity, ma.l6_main, ma.company)
               pr.report_date, ma.l7_5_activity, ma.l6_main, ma.company,
               ma.today_qty, ma.assigned_workers, ma.unit, ma.conditions,
               am.daily_qty AS master_daily_qty, am.daily_workers AS master_daily_workers
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN activity_master am
               ON am.site_id = pr.site_id AND am.company = ma.company
              AND am.l6_main = ma.l6_main AND am.l7_5_activity = ma.l7_5_activity
        WHERE ma.is_mock = false
          AND ma.l7_5_activity IS NOT NULL
          AND ma.trade IN ('건축', '토목')
          AND ($1::date IS NULL OR pr.report_date = $1::date)
        """, the_date)
    return [dict(r) for r in rows]


def _compute_perperson(r) -> tuple[float | None, float | None]:
    qty = float(r["today_qty"] or 0)
    workers = float(r["assigned_workers"] or 0)
    if workers == 0:
        return None, None
    pp_today = qty / workers
    m_qty = float(r["master_daily_qty"] or 0)
    m_workers = float(r["master_daily_workers"] or 0)
    if m_workers == 0 or m_qty == 0:
        return pp_today, None
    pp_master = m_qty / m_workers
    pct = pp_today / pp_master * 100 if pp_master else None
    return pp_today, pct


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--all-dates", action="store_true")
    args = ap.parse_args()
    the_date = None if args.all_dates else _date.fromisoformat(args.date or "2025-09-25")

    conn = await asyncpg.connect(DSN)
    try:
        rows = await fetch_rows(conn, the_date)
        print(f"fetched {len(rows)} row")
    finally:
        await conn.close()

    chroma = ChromaClient(host=CHROMA_HOST, port=CHROMA_PORT)
    col = chroma.client.get_or_create_collection("daily_activities")

    BATCH = 64
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        ids = [_id_of(r) for r in chunk]
        docs = []
        metas = []
        for r in chunk:
            date_str = r["report_date"].isoformat()
            pp_today, pct = _compute_perperson(r)
            # full body (backfill 모드) — pp + pct 전달
            doc = _format_document(
                {"company": r["company"], "l6_main": r["l6_main"],
                 "l7_5_activity": r["l7_5_activity"], "today_qty": r["today_qty"],
                 "unit": r["unit"], "assigned_workers": r["assigned_workers"],
                 "conditions": (r["conditions"] or "").split(",") if r["conditions"] else []},
                date_str, perperson=pp_today, productivity_pct=pct,
            )
            docs.append(doc)
            metas.append({
                "l7_5_activity": r["l7_5_activity"], "l6_main": r["l6_main"],
                "company": r["company"], "date": date_str,
                "today_qty": float(r["today_qty"] or 0),
                "assigned_workers": float(r["assigned_workers"] or 0),
                "unit": r["unit"] or "", "conditions": r["conditions"] or "",
                "perperson": float(pp_today or 0),
                "productivity_pct": float(pct or 0),
                "run_id": RUN_ID,
            })
        embeds = AZ.embeddings.create(model=EMBED_MODEL, input=docs).data
        embeddings = [e.embedding for e in embeds]
        col.upsert(ids=ids, embeddings=embeddings, documents=docs, metadatas=metas)
        print(f"  upserted {i + len(chunk)} / {len(rows)}")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 9-25 단일 일자 sanity 실행**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_chroma_daily_activities.py --date 2025-09-25`
Expected: `fetched ~50 row` → `upserted N / N`

- [ ] **Step 3: grep guard — backfill_chroma 안 trade IN 검증**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: 9 위치 모두 hit (`verified: 9 위치 모두 'trade IN' 필터 적용`)

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_chroma_daily_activities.py
git commit -m "feat(phase2): backfill_chroma_daily_activities.py + full body (Task C11)"
```

---

## Phase D — 9-25 dry-run + 사용자 컨펌 (블로커)

### Task D1: 9-25 PG + ChromaDB backfill

- [ ] **Step 1: 9-25 PG backfill**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_daily_report_views_v2.py --date 2025-09-25`
Expected: `ok=1 empty=0 no_target=0`

- [ ] **Step 2: 9-25 ChromaDB backfill (idempotent 재실행)**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_chroma_daily_activities.py --date 2025-09-25`
Expected: idempotent (count 변화 0)

- [ ] **Step 3: 9-25 검증 SQL (wp_id 100% 매칭)**

Run:
```bash
psql -At "$POSTGRES_URL" -c "
WITH d AS (
  SELECT dr.wp_summary_jsonb, dr.optimizer_view_jsonb->'by_wp' AS by_wp
  FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
  WHERE dr.is_mock=FALSE AND pr.report_date = '2025-09-25'
)
SELECT (SELECT COUNT(*) FILTER (WHERE d.by_wp ? (elem->>'wp_id'))
        FROM jsonb_array_elements(d.wp_summary_jsonb) elem)::text || '/' ||
       jsonb_array_length(d.wp_summary_jsonb)::text
FROM d
"
```
Expected: `N/N` (100%)

### Task D2: Playwright screenshot + 사용자 컨펌 (블로커)

- [ ] **Step 1: dev server reload + Playwright screenshot 5 WP**

수동 (5536 reload → /reports 9-25 클릭 → WP 5개 클릭) 또는 Playwright MCP:
- `mcp__plugin_playwright_playwright__browser_navigate` `http://localhost:5536/reports`
- 9-25 일자 클릭 → quadrant 5 점 클릭 → 각 카드 screenshot

- [ ] **Step 2: 컨펌 5 기준 사용자에게 제시**

```
(a) 4 슬롯 모두 비어있지 않음                          ☐
(b) WP 5개 의 diagnosis 문장 골격이 3가지 이상         ☐
(c) recommendations 가 WP 마다 다름 (0~4)              ☐
(d) similar_cases 3건 자연어로 읽힘                    ☐
(e) "경영진 앞에서 부끄럽지 않은가" yes/no             ☐
```

- [ ] **Step 3: 분기 처리**

- 컨펌 OK → Phase E 진행
- (b)/(c) 부족 → Task C5 의 `_pick_cause` / `_pick_recommendations` 룰 조정 → 9-25 backfill 재실행 → 다시 검토 (30분 단위 iteration, 최대 3회)
- 3회 후에도 컨펌 못 받음 → **명시적 fallback (블로커 해제)**: deterministic 템플릿 v1 그대로 ship + 사용자에게 "v1 가드 우선 — 추후 LLM 호출 통한 다양성 보강 후속 plan" 명시 합의. UI 변경 0, code 변경 0.

---

## Phase E — 530일 전체 backfill (30~45분)

### Task E1: 530일 PG + ChromaDB backfill + idempotency 검증

- [ ] **Step 1: 530일 PG backfill**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_daily_report_views_v2.py --all-dates 2>&1 | tee docs/superpowers/audit/phase2_pg_backfill.log`
Expected: `ok=530 empty=0 no_target=0`

- [ ] **Step 2: 530일 ChromaDB backfill**

Run: `PYTHONPATH=. pipeline/.venv/bin/python scripts/backfill_chroma_daily_activities.py --all-dates 2>&1 | tee docs/superpowers/audit/phase2_chroma_backfill.log`
Expected: `fetched ~27484 row` → 모두 upserted

- [ ] **Step 3: Idempotency md5 1회**

Run:
```bash
psql -At "$POSTGRES_URL" -c "SELECT md5(string_agg(dr.optimizer_view_jsonb::text, '' ORDER BY pr.report_date)) FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) WHERE dr.is_mock=FALSE" | tee docs/superpowers/audit/phase2_md5_run1.txt
```
Expected: hex 32자

- [ ] **Step 4: 2회 재실행 후 md5 비교**

Run: backfill 2회 → SQL 다시 → `docs/superpowers/audit/phase2_md5_run2.txt`
Expected: `diff phase2_md5_run1.txt phase2_md5_run2.txt` → 변화 0

- [ ] **Step 5: §5.2 wp_id 530일 100% 매칭률 검증**

Run:
```bash
psql -At "$POSTGRES_URL" -c "
WITH d AS (
  SELECT pr.report_date, dr.wp_summary_jsonb, dr.optimizer_view_jsonb->'by_wp' AS by_wp
  FROM daily_reports dr JOIN pipeline_runs pr USING (run_id) WHERE dr.is_mock=FALSE
)
SELECT pr.report_date::text,
  (SELECT COUNT(*) FILTER (WHERE d.by_wp ? (elem->>'wp_id'))
   FROM jsonb_array_elements(d.wp_summary_jsonb) elem)::text || '/' ||
   jsonb_array_length(d.wp_summary_jsonb)::text AS matched
FROM d
WHERE jsonb_array_length(d.wp_summary_jsonb) <> (SELECT COUNT(*) FILTER (WHERE d.by_wp ? (elem->>'wp_id'))
                                                  FROM jsonb_array_elements(d.wp_summary_jsonb) elem)
LIMIT 5
"
```
Expected: 빈 결과 (모든 일자 100% 매칭)

- [ ] **Step 6: Commit audit log**

```bash
git add docs/superpowers/audit/
git commit -m "chore(phase2): 530일 backfill audit 완료 + idempotency md5 (Task E1)"
```

---

## Phase F — UI textContent fix (1h)

### Task F1: 4 컴포넌트 textContent 변경

**Files:**
- Modify: `web/app/components/reports/WPSummaryTable.tsx:82`
- Modify: `web/app/components/charts/QuadrantScatter.tsx:45`
- Modify: `web/app/components/export/ConsolidatedReportCard.tsx:21`
- Modify: `web/app/components/export/SheetTable.tsx:86-98`

**중요**: `web/lib/types.ts:305-318` 의 `OutputManpowerRow` interface 는 **건드리지 않음**. BE 가 early/day/overtime emit 계속해도 FE 가 column 정의 안 가져서 render 0. type/data contract 그대로.

- [ ] **Step 1: WPSummaryTable.tsx:82**

```diff
- {row.display_label ?? `${row.productivity}%`}
+ {`${row.productivity.toFixed(1)}%`}
```

- [ ] **Step 2: QuadrantScatter.tsx:45**

```diff
- <b>{p.display_label ?? `${p.productivity}%`}</b>
+ <b>{`${p.productivity.toFixed(1)}%`}</b>
```

- [ ] **Step 3: ConsolidatedReportCard.tsx:21**

```diff
- output_manpower:     "1. 출력인원 현황",
+ output_manpower:     "1. 작업사항",
```

- [ ] **Step 4: SheetTable.tsx:86-98 OUTPUT_MANPOWER_COLS 3 항목 제거**

```diff
  export const OUTPUT_MANPOWER_COLS = [
    { key: "pjt",        label: "PJT" },
    { key: "zone",       label: "Zone" },
    { key: "trade",      label: "공종" },
    { key: "bp_code",    label: "BP사", cellClass: "font-mono text-[11px]" },
    { key: "scope",      label: "Scope" },
    { key: "prev_work",  label: "전일 작업사항", cellClass: "max-w-[160px] truncate" },
    { key: "today_work", label: "금일 작업사항", cellClass: "max-w-[200px] whitespace-normal text-ink" },
    { key: "next_work",  label: "명일 작업사항", cellClass: "max-w-[160px] truncate" },
-   { key: "early",      label: "조출", align: "right", format: num },
-   { key: "day",        label: "주간", align: "right", format: num },
-   { key: "overtime",   label: "연장", align: "right", format: num },
  ] as const;
```

- [ ] **Step 5: className/markup 변경 0 가드 검증**

Run: `git diff web/app/components/ | grep -E "^[+-][^/+-]" | grep -E "className=|<[A-Za-z]+ " | head`
Expected: 빈 결과 (className 추가/삭제 없음, JSX 태그 변경 없음 — textContent 와 const 배열 항목만 변경)

- [ ] **Step 6: types.ts 무변경 확인**

Run: `git diff web/lib/types.ts`
Expected: 빈 결과 (사용자 결정 — type 유지)

- [ ] **Step 7: 5536 dev server reload + 4 화면 시각 검증**

수동 또는 Playwright:
- /reports — WP 목록 productivity `80.1%` 형식
- /reports — quadrant tooltip 일관성
- /export — 1번 탭 라벨 "작업사항", 4번 "물량" 유지, 컬럼 8개 (조출/주간/연장 없음)

- [ ] **Step 8: Commit**

```bash
git add web/app/components/
git commit -m "feat(phase2): UI textContent fix 4 컴포넌트 (Task F1)"
```

---

## Phase G — Dashboard fixture swap (2.5h)

### Task G1: Spike — fixture vs PG 530일 비교

**Files:**
- Create: `docs/superpowers/audit/phase2_dashboard_spike.md`

- [ ] **Step 1: fixture 값 캡쳐**

Run: `cat data/mock_dashboard.json | jq '.performance.fleet_kpi'` → 결과 저장

- [ ] **Step 2: PG 530일 SQL 캡쳐**

Run:
```bash
psql -At "$POSTGRES_URL" -c "
SELECT
  ROUND(AVG((kpi_jsonb->>'productivity_today')::numeric), 1) AS avg_productivity,
  ROUND(AVG((kpi_jsonb->>'delay_days')::numeric), 1)         AS avg_delay,
  COUNT(*) FILTER (WHERE kpi_jsonb->>'risk_level' <> '정상') AS abnormal_total,
  SUM((kpi_jsonb->>'recovery_days')::numeric)::int          AS recoverable_days
FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
WHERE dr.is_mock = FALSE"
```

- [ ] **Step 3: 비교표 작성 + 사용자 컨펌**

`docs/superpowers/audit/phase2_dashboard_spike.md` 에:

```
| KPI | fixture | PG 530일 | 자릿수 차이 | 표시 형식 결정 |
|---|---|---|---|---|
| avg_productivity | 85.0 | (실측) | … | …  |
| avg_delay | 1.2 | (실측) | … | … |
| abnormal_total | 42 | (실측) | … | round/K |
| recoverable_days | 18 | (실측) | … | … |
```

사용자 확인 후 표시 형식 결정 (자릿수 / K 단위 / round). 결정 못 받으면 raw 그대로 + 후속 plan 으로 처리.

- [ ] **Step 4: Commit spike**

```bash
git add docs/superpowers/audit/phase2_dashboard_spike.md
git commit -m "chore(phase2): dashboard fixture vs PG spike 비교표 (Task G1)"
```

### Task G2: loadReal("dashboard_performance") + ("dashboard_impact") + dashboard route swap

**Files:**
- Modify: `web/lib/fixtures.ts` (loadReal switch 에 2 case 추가)
- Modify: `web/app/api/mock/dashboard/route.ts`

- [ ] **Step 1: loadReal overload 시그니처 + dashboard_performance case**

```typescript
// fixtures.ts:108 영역 (loadReal overload)
export async function loadReal(name: "dashboard_performance"): Promise<DashboardFixture["performance"]>;
export async function loadReal(name: "dashboard_impact"): Promise<DashboardFixture["impact"]>;
// switch case (line 135 직전):
case "dashboard_performance": {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
  const [agg] = (await (sql as any)`
    SELECT
      AVG((dr.kpi_jsonb->>'productivity_today')::numeric)::float AS avg_productivity,
      AVG((dr.kpi_jsonb->>'delay_days')::numeric)::float          AS avg_delay,
      COUNT(*) FILTER (WHERE dr.kpi_jsonb->>'risk_level' <> '정상')::int AS abnormal_total,
      COALESCE(SUM((dr.kpi_jsonb->>'recovery_days')::numeric), 0)::int AS recoverable_days
    FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
    WHERE dr.is_mock = ${useMock}
  `) as Array<{ avg_productivity: number; avg_delay: number; abnormal_total: number; recoverable_days: number }>;

  const trendRows = (await (sql as any)`
    SELECT pr.report_date,
           (dr.kpi_jsonb->>'productivity_today')::numeric AS productivity,
           (dr.kpi_jsonb->>'delay_days')::numeric          AS delay_days
    FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
    WHERE dr.is_mock = ${useMock}
    ORDER BY pr.report_date DESC LIMIT 60
  `) as Array<{ report_date: Date; productivity: number; delay_days: number }>;

  const sparkRows = (await (sql as any)`
    SELECT pr.report_date,
           (dr.kpi_jsonb->>'productivity_today')::numeric AS productivity
    FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
    WHERE dr.is_mock = ${useMock}
      AND pr.site_id = 'm15x-ph3-ibl'
    ORDER BY pr.report_date DESC LIMIT 30
  `) as Array<{ report_date: Date; productivity: number }>;

  return {
    fleet_kpi: agg,
    fleet_trend: trendRows.reverse().map(r => ({
      date: (r.report_date instanceof Date ? r.report_date.toISOString() : String(r.report_date)).slice(0, 10),
      productivity: Number(r.productivity ?? 0),
      delay_days: Number(r.delay_days ?? 0),
    })),
    site_sparklines: { "m15x-ph3-ibl": sparkRows.reverse().map(r => Number(r.productivity ?? 0)) },
  };
}
```

- [ ] **Step 2: dashboard_impact case — site_distribution / monthly_trend 실 SQL**

```typescript
case "dashboard_impact": {
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
  const summary = await loadReal("sites_summary");   // type compat — DashboardFixture.impact.fleet_kpi = SitesSummary

  const distRows = (await (sql as any)`
    SELECT pr.site_id, s.name,
           AVG((dr.kpi_jsonb->>'productivity_today')::numeric)::float AS avg_p,
           COUNT(*) FILTER (WHERE dr.kpi_jsonb->>'risk_level' <> '정상')::int AS abnormal_n
    FROM daily_reports dr
    JOIN pipeline_runs pr USING (run_id)
    JOIN sites s ON s.site_id = pr.site_id
    WHERE dr.is_mock = ${useMock}
    GROUP BY pr.site_id, s.name
  `) as Array<{ site_id: string; name: string; avg_p: number; abnormal_n: number }>;

  const monthRows = (await (sql as any)`
    SELECT to_char(pr.report_date, 'YYYY-MM') AS ym,
           AVG((dr.kpi_jsonb->>'productivity_today')::numeric)::float AS avg_p
    FROM daily_reports dr JOIN pipeline_runs pr USING (run_id)
    WHERE dr.is_mock = ${useMock}
    GROUP BY ym ORDER BY ym
  `) as Array<{ ym: string; avg_p: number }>;

  return {
    fleet_kpi: summary,
    site_distribution: distRows.map(r => ({
      site_id: r.site_id, name: r.name,
      avg_productivity: Number(r.avg_p ?? 0),
      abnormal_count: Number(r.abnormal_n ?? 0),
    })),
    monthly_trend: monthRows.map(r => ({ month: r.ym, productivity: Number(r.avg_p ?? 0) })),
    per_site_automation: {},   // 후속 plan
  };
}
```

- [ ] **Step 3: dashboard route swap**

`web/app/api/mock/dashboard/route.ts`:

```diff
-  const dashboard = await loadFixture("dashboard");
-  const sites = await loadFixture("sites");
+  const performance = await loadReal("dashboard_performance");
+  const impact = await loadReal("dashboard_impact");
+  const sites = await loadFixture("sites");
+  const dashboard = { performance, impact };
```

- [ ] **Step 4: Playwright /dashboard screenshot 검증**

수동 5536 dev server reload → /dashboard 4 KPI 카드 + fleet_trend 차트 + site sparklines 가 PG 데이터로 채워짐.

- [ ] **Step 5: Commit**

```bash
git add web/lib/fixtures.ts web/app/api/mock/dashboard/route.ts
git commit -m "feat(phase2): dashboard loadFixture → loadReal swap (Task G2)"
```

---

## Phase H — 전 검증 + PR (1h)

### Task H1: 전 검증

- [ ] **Step 1: WHERE filter grep guard (9 위치)**

Run: `./scripts/audit_phase2_where_filter.sh`
Expected: `verified: 9 위치 모두 'trade IN' 필터 적용`

- [ ] **Step 2: backup_20260521 snapshot verify**

Run: `python scripts/audit_phase2_snapshot.py --verify`
Expected: byte-exact 일치

- [ ] **Step 3: wp_id 100% 매칭률 (530일)**

Phase E Step 5 SQL 재실행. 빈 결과.

- [ ] **Step 4: 카드 채움률 (deterministic source sentinel)**

Run:
```bash
psql -At "$POSTGRES_URL" -c "
SELECT pr.report_date::text,
  COUNT(*) FILTER (WHERE wp.value->>'diagnosis' = '' OR wp.value->>'diagnosis' IS NULL)::text || '/' || COUNT(*)::text AS empty_ratio
FROM daily_reports dr JOIN pipeline_runs pr USING (run_id),
     jsonb_each(dr.optimizer_view_jsonb->'by_wp') wp
WHERE dr.is_mock=FALSE GROUP BY pr.report_date ORDER BY 1 DESC LIMIT 10"
```
Expected: 모든 일자 0/N

- [ ] **Step 5: unit pytest 전체 통과**

Run: `PYTHONPATH=. pipeline/.venv/bin/python -m pytest pipeline/tests/ -v`
Expected: 모두 PASS

- [ ] **Step 6: Idempotency md5 동일**

Run: backfill 1회 + SQL → `phase2_md5_run3.txt`. diff phase2_md5_run1.txt → 빈 결과.

- [ ] **Step 7: Playwright 5 화면 screenshot**

수동 또는 자동 — review / tasks / export / reports / dashboard.

### Task H2: PR push + body 작성

- [ ] **Step 1: push**

```bash
git push origin A_Track
```

- [ ] **Step 2: gh pr edit body**

```bash
gh pr edit 38 --body "$(cat <<'EOF'
# CPIA UI Data Integrity Phase 2

5-reviewer 피드백 반영 spec v2 + plan v2 구현. 530일 더미 적재 후 dev server 5536 에서 발견된 6 RC 일괄 정합화.

## 변경 요약
- **격리 방식**: DB DELETE → BE WHERE 필터 (사용자 명시 "백업 안 건드림"). DB row / backup_20260521 byte-exact 보존.
- **WP 카드 4 슬롯 채움**: wp_id 통일 + 9 jsonb key (optimizer_view/scenarios/s_curve 추가) + deterministic cold_start (8 cause × 5 rule, LLM 호출 0).
- **ChromaDB**: 530일 27,484 row 적재 (l7_5_activity metadata, run_id="backfill_v2").
- **UI**: 4 컴포넌트 textContent 만 (markup/className 0): WP 목록 productivity `${productivity}%`, Export 1번 탭 "작업사항" + 컬럼 정리.
- **Dashboard**: fixture JSON → PG 530일 집계 swap.

## 검증
- BE WHERE 필터 9 위치 (grep guard)
- wp_id 매칭률 530일 100%
- 카드 empty_ratio 0/N (deterministic source sentinel)
- Idempotency md5 byte-exact
- 5 화면 Playwright screenshot

Spec: docs/superpowers/specs/2026-05-21-cpia-ui-data-integrity-phase2-design.md
Plan: docs/superpowers/plans/2026-05-21-cpia-ui-data-integrity-phase2-plan.md
EOF
)"
```

- [ ] **Step 3: 최종 commit**

```bash
git commit --allow-empty -m "chore(phase2): Phase H 전 검증 + PR body 업데이트 (Task H2)"
git push origin A_Track
```

---

## Task R1: L2 rollback (별도 trigger — Phase H 후 또는 시연 장애 시)

**Files:**
- Create: `scripts/rollback_phase2_jsonb.sh`

**중요**: 정상 흐름에선 호출 안 함. 시연 직전 장애 / Phase E 산출물 거부 시 사용.

- [ ] **Step 1: 신규 script**

```bash
#!/usr/bin/env bash
# Phase 2 L2 rollback — daily_reports.jsonb 9 컬럼만 backup_20260521 에서 복사.
# DB row count 무변경 (UPDATE 만, TRUNCATE 없음).
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. snapshot verify — backup_20260521 무변화 확인
python scripts/audit_phase2_snapshot.py --verify

# 2. confirm
read -p "rollback 진행? (yes/no): " ans
[ "$ans" = "yes" ] || { echo "취소"; exit 1; }

# 3. UPDATE (FK 위반 0)
psql "$POSTGRES_URL" -c "
UPDATE public.daily_reports dr SET
  kpi_jsonb            = b.kpi_jsonb,
  productivity_jsonb   = b.productivity_jsonb,
  contractor_bars_jsonb= b.contractor_bars_jsonb,
  trade_bars_jsonb     = b.trade_bars_jsonb,
  quadrant_jsonb       = b.quadrant_jsonb,
  wp_summary_jsonb     = b.wp_summary_jsonb,
  optimizer_view_jsonb = b.optimizer_view_jsonb,
  scenarios_jsonb      = b.scenarios_jsonb,
  s_curve_jsonb        = b.s_curve_jsonb
FROM backup_20260521.daily_reports b
WHERE dr.run_id = b.run_id;
"

# 4. ChromaDB rollback — backfill_v2 만 삭제 (synthetic_v2 보존)
PYTHONPATH=. pipeline/.venv/bin/python -c "
import os
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ['CHROMA_PORT']))
col = c.client.get_collection('daily_activities')
col.delete(where={'run_id': 'backfill_v2'})
print('chroma backfill_v2 삭제 완료')
"

echo "rollback 완료"
```

- [ ] **Step 2: 권한 부여 + Commit (실행 안 함, ship 만)**

```bash
chmod +x scripts/rollback_phase2_jsonb.sh
git add scripts/rollback_phase2_jsonb.sh
git commit -m "feat(phase2): L2 rollback script (Task R1)"
```

---

## Remember

- **Iron Law (CLAUDE.md §1)**: 실 호출 / 실 출력 / 의도 일치. Phase D/E/H 의 모든 검증은 SQL/pytest/Playwright 실 출력 인용.
- **TDD (CLAUDE.md §3.2)**: 새 기능은 실패 test → 구현 → green. Task C1~C10 모두 TDD.
- **디자인 가드**: `web/app/components/**` markup/className 변경 0. Task F1 Step 5 grep 검증. types.ts 무변경.
- **Verification Before Done (CLAUDE.md §3.4)**: `$ command / 실 출력 / → 결론` 형식 강제.
- **9-25 dry-run = 블로커**: Phase D 사용자 컨펌 못 받으면 Phase E 진행 금지. 3회 후 명시적 fallback (Task D2 Step 3).
- **L2 rollback**: DB DELETE 없음. UPDATE 만. `scripts/rollback_phase2_jsonb.sh`.
- **명시적 결정 사항 (구현 시 의사결정 0)**: 본 plan 의 ⚠ 결정 사항 표 참조.
