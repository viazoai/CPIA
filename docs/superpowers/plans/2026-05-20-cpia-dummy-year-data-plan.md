# CPIA 1년치 더미 데이터 적재 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 532일 (24-04-11 ~ 25-09-24) PG 적재 + 77일 Chroma 임베딩 + UI 5 페이지 재검증 + brain 갱신 + PR.

**Architecture:** seed_dummy_year.py cycle bypass — `PGClient.insert_*` 14 method + `view_builder._build_*` 9 함수 직접 호출. Chroma 는 atomizer 의 `_make_doc_id` + `_build_metadata` import 하여 매주 1일 sample 적재.

**Tech Stack:** Python asyncpg + ChromaDB 0.5.20 + Azure OpenAI text-embedding-3-small-ai-board-test (1536d) + Next.js + playwright MCP.

**Spec:** `docs/superpowers/specs/2026-05-20-cpia-dummy-year-data-design.md`

**Branch:** A_Track (PR #36 머지 대기 중, 이번 PR 별도 — 조형준 프로 결정)

**환경:** macOS Apple Silicon, `pipeline/.venv/bin/python3`, AWS PG `43.200.85.209:5532`, AWS Chroma `43.200.85.209:5533`

---

## File Structure

| 파일 | 작업 |
|---|---|
| `scripts/seed_dummy_year.py` | Modify — `--chroma-on --chroma-mode weekly` flag + `chroma_upsert_day()` helper 추가 (현재 679 LOC) |
| (PG) `pipeline_runs / parser_* / mapper_* / mapped_history / forecasts / optimizer_advice / daily_reports` | Insert — 532 일자 row + 9 jsonb |
| (Chroma) `daily_activities` collection | Upsert — 77 sample 일자 × ~700 doc |
| `docs/superpowers/plans/2026-05-20-cpia-dummy-year-data-plan.md` | This file |
| (brain) `notes/cpia-dummy-data-design-plan-2026-05-20` | put_page v2 갱신 |
| (brain) `notes/cpia-dummy-poc-success-2026-05-20` | put_page 신규 |
| (git) `A_Track` branch | commit + push |
| (gh) PR `A_Track → main` | 생성, 머지 보류 |

**디자인 불가침:** `web/app/components/**` markup 변경 0.

---

## Task 1: `--chroma-on` flag + Chroma upsert helper 추가

**Files:**
- Modify: `scripts/seed_dummy_year.py`

- [ ] **Step 1: argparse `--chroma-on` / `--chroma-mode` flag 추가**

`amain()` 의 argparse 블록 (~line 628-640) 에 추가:

```python
p.add_argument("--chroma-on", action="store_true", default=False, help="Chroma daily_activities upsert (default off — PoC)")
p.add_argument("--chroma-mode", type=str, default="weekly", choices=["weekly", "all", "anchor_only"], help="weekly = 매주 1일 + 9-24, all = 전 일자, anchor_only = 9-24 만")
```

`--chroma-skip` 은 deprecated — `--chroma-on` 의 negation 으로 충분.

- [ ] **Step 2: chroma_should_seed(d) helper 추가**

`PHASE 1` 위쪽 (~line 165) 에:

```python
def _chroma_should_seed(d: date, mode: str, start: date) -> bool:
    if mode == "all":
        return True
    if mode == "anchor_only":
        return d == ANCHOR_DATE - timedelta(days=1)  # 9-24
    # weekly — 매주 1일 (start + 7n) + 9-24 anchor 인접
    if d == ANCHOR_DATE - timedelta(days=1):
        return True
    return (d - start).days % 7 == 0
```

- [ ] **Step 3: chroma_upsert_day() 함수 추가**

`per-day INSERT loop` 위쪽에 (~line 425):

```python
async def chroma_upsert_day(
    d: date,
    run_id: uuid.UUID,
    mapper_rows: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> int:
    """매주 1일 sample 일자 의 mapper_activities → Chroma daily_activities upsert.
    
    atomizer._make_doc_id / _build_metadata 재사용. fail-fast (Chroma 또는 Azure fail 시 raise).
    """
    from pipeline.agents.atomizer import _make_doc_id  # late import
    from pipeline.chroma_client import ChromaClient
    from openai import AzureOpenAI

    # valid filter: work_content + l6_main not empty
    valid = [r for r in mapper_rows if r.get("l6_main") and r.get("work_content")]
    if not valid:
        return 0
    
    date_str = d.isoformat()
    # dedup by doc_id (Chroma upsert within-call duplicate 금지)
    seen: dict[str, int] = {}
    for i, r in enumerate(valid):
        doc_id = _make_doc_id(date_str, r["company"], r["l6_main"], r["work_content"])
        seen[doc_id] = i
    
    ids = list(seen.keys())
    documents = [valid[i]["work_content"] for i in seen.values()]
    metadatas = [{
        "date": date_str,
        "run_id": str(run_id),
        "company": valid[i]["company"],
        "l5_disc": "",
        "l6_main": valid[i]["l6_main"],
        "wa": valid[i]["wa"],
        "unit": valid[i]["unit"],
        "today_qty": float(valid[i]["today_qty"]),
        "assigned_workers": float(valid[i]["assigned_workers"]),
        "worker_source": "dummy_seed",
        "mapping_conf": 1.0,
        "conditions": "",
    } for i in seen.values()]
    
    # Azure embedding batch=100
    azure = AzureOpenAI(
        api_key=cfg["AZURE_OPENAI_API_KEY"],
        api_version=cfg["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=cfg["AZURE_OPENAI_ENDPOINT"],
        timeout=30.0,
        max_retries=3,
    )
    embeddings: list[list[float]] = []
    BATCH = 100
    for i in range(0, len(documents), BATCH):
        chunk = documents[i : i + BATCH]
        resp = azure.embeddings.create(model=cfg["EMBEDDING_MODEL"], input=chunk)
        embeddings.extend([d.embedding for d in resp.data])
    
    # Chroma upsert batch=100
    chroma = ChromaClient(host=cfg["CHROMA_HOST"], port=int(cfg["CHROMA_PORT"]))
    coll = chroma.get_or_create_daily_activities()
    for j in range(0, len(ids), BATCH):
        coll.upsert(
            ids=ids[j : j + BATCH],
            embeddings=embeddings[j : j + BATCH],
            documents=documents[j : j + BATCH],
            metadatas=metadatas[j : j + BATCH],
        )
    return len(ids)
```

- [ ] **Step 4: seed_day() 에 Chroma 호출 통합**

`seed_day()` 마지막에 (return counts 직전):

```python
# Chroma upsert (조건 충족 시)
if cfg and _chroma_should_seed(d, cfg.get("chroma_mode", "weekly"), cfg.get("seed_start", d)):
    n_chroma = await chroma_upsert_day(d, run_id, mapper_rows, cfg)
    counts["chroma_upserts"] = n_chroma
```

`seed_day` 시그니처에 `cfg` arg 추가 (default None).

- [ ] **Step 5: amain() 에서 env 로드 + cfg 전달**

```python
chroma_cfg = None
if args.chroma_on:
    required = ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_VERSION",
                "EMBEDDING_MODEL", "CHROMA_HOST", "CHROMA_PORT"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"--chroma-on requires env: {missing}")
    chroma_cfg = {k: os.environ[k] for k in required}
    chroma_cfg["chroma_mode"] = args.chroma_mode
    chroma_cfg["seed_start"] = start
```

`seed_day(pg, d, anchor, am_list, chroma_cfg)` 으로 전달.

- [ ] **Step 6: 9-24 단일 일자 + --chroma-on smoke test**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
set -a; source .env.local; set +a
pipeline/.venv/bin/python3 scripts/seed_dummy_year.py --start 2025-09-24 --end 2025-09-24 --chroma-on --chroma-mode anchor_only
```

Expected: `chroma_upserts: ~700` (현 mapper_rows count 798 중 valid filter 후 ~700).

Verify:
```bash
curl -s http://43.200.85.209:5533/api/v1/collections | grep -o "daily_activities" | head -1
PG="postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"
# 이전 anchor 만 있던 시점 의 doc count vs 현재 +700 확인 (Chroma API)
```

- [ ] **Step 7: commit (Task 1 종료)**

```bash
git add scripts/seed_dummy_year.py docs/superpowers/specs/2026-05-20-cpia-dummy-year-data-design.md docs/superpowers/plans/2026-05-20-cpia-dummy-year-data-plan.md
git commit -m "feat(seed): --chroma-on flag + chroma_upsert_day helper + spec + plan"
```

---

## Task 2: 전 532일 PG 적재 dry-run (1주차 — 24-04-11 ~ 24-04-17)

**Files:** (no code change — script 만 실행)

- [ ] **Step 1: cleanup dummy_seed (전 범위)**

```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia" \
  pipeline/.venv/bin/python3 scripts/seed_dummy_year.py --cleanup-only \
  --start 2024-04-11 --end 2025-09-24
```

Expected: `cleanup: N pipeline_runs (dummy_seed) DELETE` (N ≥ 1, 이전 9-24 dummy 포함).

- [ ] **Step 2: 1주차 적재 (24-04-11 ~ 24-04-17)**

```bash
POSTGRES_URL="..." pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start 2024-04-11 --end 2024-04-17
```

Expected:
- `7 days, ~10-50 active per day (24-04-11 plan_start 직후 활성 wbs 적음)`
- `pipeline_runs: 7, daily_reports: 7`

- [ ] **Step 3: 1주차 PG 검증 SQL**

```sql
SELECT report_date, jsonb_array_length(quadrant_jsonb) AS qd,
       kpi_jsonb ->> 'productivity_today' AS prod
FROM daily_reports
WHERE report_date BETWEEN '2024-04-11' AND '2024-04-17' AND is_mock=FALSE
ORDER BY report_date;
```

Expected: 7 row, 각 qd ≥ 1, prod 0 ~ 110 사이.

- [ ] **Step 4: dev server (5536) /reports navigate**

playwright_mcp 로 navigate. 좌측 daily list 에 24-04-11 ~ 24-04-17 row 7 개 추가됐는지 확인.

- [ ] **Step 5: 1주차 PoC 성공 확정 → 전 적재 진입**

---

## Task 3: 전 532일 PG 적재 (Chroma skip)

- [ ] **Step 1: 전 적재 실행 (background)**

```bash
POSTGRES_URL="..." pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start 2024-04-11 --end 2025-09-24 2>&1 | tee /tmp/seed_full_log.txt
```

- 옵션: `run_in_background=true`. 시간 ~45분~1시간.
- 진행 log: 매 10일마다 `[YYYY-MM-DD] day#N active=M` 출력.

- [ ] **Step 2: 진행 모니터링 (Monitor or tail)**

`tail -f /tmp/seed_full_log.txt` 또는 `BashOutput` 으로 진행률 확인.

- [ ] **Step 3: 적재 완료 후 row count 검증**

```sql
SELECT 'daily_reports' AS tbl, count(*) FROM daily_reports WHERE is_mock=FALSE
UNION ALL SELECT 'mapper_activities (dummy_seed)', count(*) FROM mapper_activities WHERE mapping_source='dummy_seed'
UNION ALL SELECT 'forecasts dummy', count(*) FROM forecasts f JOIN pipeline_runs pr USING(run_id)
   WHERE pr.report_date < '2025-09-25' AND f.is_mock=FALSE
UNION ALL SELECT 'optimizer_advice dummy', count(*) FROM optimizer_advice oa JOIN pipeline_runs pr USING(run_id)
   WHERE pr.report_date < '2025-09-25' AND oa.is_mock=FALSE;
```

Expected:
- daily_reports: 533 (532 dummy + 1 anchor)
- mapper_activities dummy_seed: ~430K (532 일자 × 평균 ~800 active)
- forecasts dummy: ~160K (532 × 평균 ~300 group)
- optimizer_advice dummy: ~24K (532 × 평균 ~45 risky)

---

## Task 4: 77일 Chroma 적재 (매주 1일 + 9-24 anchor 인접)

- [ ] **Step 1: env 로드 + --chroma-on 으로 weekly 모드 실행**

```bash
set -a; source .env.local; set +a
POSTGRES_URL="..." pipeline/.venv/bin/python3 scripts/seed_dummy_year.py \
  --start 2024-04-11 --end 2025-09-24 --chroma-on --chroma-mode weekly 2>&1 | tee /tmp/seed_chroma_log.txt
```

⚠️ **주의**: 이 명령은 PG 도 재적재 → 시간 ~70분 (45분 PG + 30분 Chroma). 또는 cleanup 없이 Chroma 만 따로 적재하는 옵션 추가 필요.

대안: `--chroma-only` flag 추가 (PG INSERT skip, Chroma 만):

```python
p.add_argument("--chroma-only", action="store_true", default=False)
# seed_day 에서 args.chroma_only 면 PG INSERT skip, mapper_rows 만 build 해서 Chroma upsert
```

- [ ] **Step 2: Chroma upsert 진행 모니터링**

매 sample 일자 (~7일 간격) 마다 `chroma_upserts: N` 출력.

- [ ] **Step 3: Chroma daily_activities count 확인**

```python
# scripts/verify_chroma.py 간단 script
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host="43.200.85.209", port=5533)
coll = c.get_or_create_daily_activities()
print(f"daily_activities count: {coll.count()}")
```

Expected: 이전 ~3180 (9-25 anchor 시점) + 77 × ~700 = **~57,000 doc**.

---

## Task 5: 정합 검증 SQL (anchor today_cum_qty 매칭)

- [ ] **Step 1: Case A 정합 검증 — anchor 누계 = dummy 누계 + anchor today_qty**

```sql
WITH per_group AS (
  SELECT ma.wa, ma.company, ma.l6_main,
         SUM(ma.today_qty) AS dummy_cum_to_9_24
  FROM mapper_activities ma
  WHERE ma.mapping_source = 'dummy_seed'
  GROUP BY ma.wa, ma.company, ma.l6_main
),
anchor_row AS (
  SELECT ma.wa, ma.company, ma.l6_main, ma.today_qty AS anchor_today, ma.today_cum_qty AS anchor_cum
  FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
  WHERE pr.report_date = '2025-09-25' AND ma.mapping_source != 'dummy_seed'
)
SELECT 
  COUNT(*) AS total_groups,
  COUNT(*) FILTER (WHERE ABS(COALESCE(p.dummy_cum_to_9_24, 0) + COALESCE(a.anchor_today, 0) - COALESCE(a.anchor_cum, 0)) <= a.anchor_cum * 0.10) AS within_10pct,
  COUNT(*) FILTER (WHERE a.anchor_cum IS NULL OR a.anchor_cum = 0) AS anchor_cum_null
FROM per_group p
FULL OUTER JOIN anchor_row a ON a.wa = p.wa AND a.company = p.company AND a.l6_main = p.l6_main;
```

Expected: `within_10pct / total_groups ≥ 0.7` (사용자 명시 ±10%).

- [ ] **Step 2: 9 jsonb 533 row 다 채움**

```sql
SELECT COUNT(*) FILTER (WHERE jsonb_array_length(quadrant_jsonb) > 0) AS qd_ok,
       COUNT(*) FILTER (WHERE kpi_jsonb ? 'cpi') AS kpi_ok,
       COUNT(*) FILTER (WHERE optimizer_view_jsonb ? 'by_wp') AS ov_ok,
       COUNT(*) AS total
FROM daily_reports WHERE is_mock = FALSE;
```

Expected: qd_ok / kpi_ok / ov_ok 모두 ≥ 533.

- [ ] **Step 3: forecasts assessment 분포**

```sql
SELECT assessment, COUNT(*), ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM forecasts f JOIN pipeline_runs pr USING(run_id)
WHERE f.is_mock = FALSE
GROUP BY assessment ORDER BY 2 DESC;
```

Expected: 정상 ~55% / 이상 ~30% / 주의 ~15% (PoC 측정 분포 ±5%).

- [ ] **Step 4: diagnosis fixture 7 패턴 회전 확인**

```sql
WITH parsed AS (
  SELECT
    CASE 
      WHEN diagnosis LIKE '%당일 오전 강수%' THEN 'weather_rain'
      WHEN diagnosis LIKE '%인력 가용율%' THEN 'manpower_short'
      WHEN diagnosis LIKE '%자재 일부 입고 지연%' THEN 'material_delay'
      WHEN diagnosis LIKE '%재작업 발생%' THEN 'rework'
      WHEN diagnosis LIKE '%동선 충돌%' THEN 'trade_overlap'
      WHEN diagnosis LIKE '%사양 조정 필요%' THEN 'spec_change'
      WHEN diagnosis LIKE '%정상 진행%' THEN 'normal_steady'
      ELSE 'OTHER'
    END AS pattern
  FROM optimizer_advice WHERE is_mock = FALSE
)
SELECT pattern, COUNT(*) FROM parsed GROUP BY 1 ORDER BY 2 DESC;
```

Expected: 7 패턴 다 등장, OTHER 0.

---

## Task 6: UI 5 페이지 playwright 재검증

- [ ] **Step 1: /dashboard navigate + trend 곡선 확인**

```
playwright navigate http://127.0.0.1:5536/dashboard
playwright snapshot
```

확인: console error 0, 6 sites 카드, performance 탭 fleet_kpi 표시.

- [ ] **Step 2: /reports navigate + daily list 533 row + random 3 일자 산점도 + diagnosis**

```
playwright navigate http://127.0.0.1:5536/reports
playwright snapshot
```

확인:
- daily list 좌측에 533 row 표시 (스크롤)
- 첫 row = 2025-09-25 anchor, 마지막 row = 2024-04-11
- random 3 일자 (예: 2024-08-15, 2024-12-25, 2025-05-01) 클릭:
  - 산점도 + WP 테이블 갱신
  - 산점도 wp 클릭 → 우측 박스 diagnosis fixture 텍스트 표시 (7 패턴 중 하나)
  - similar_cases 2건 + recommendations 2개

- [ ] **Step 3: /tasks 533 row + 모두 completed**

```
playwright navigate http://127.0.0.1:5536/tasks
playwright snapshot
```

확인: tasks count ≥ 533, status 모두 completed, progress 100.

- [ ] **Step 4: /export 533 ready**

```
playwright navigate http://127.0.0.1:5536/export
playwright snapshot
```

확인: row 533, status="ready", sheet_row_counts 표시.

- [ ] **Step 5: /review cards 300 + wbs root 2**

```
playwright navigate http://127.0.0.1:5536/review
playwright snapshot
```

확인: cards 300 (LIMIT), wbs root = 2 (FAB + CUB), 회사명 + work_content 표시.

- [ ] **Step 6: console error 0 across all pages 보장**

5 페이지 각각 console_messages level=error 호출 → 모두 0.

---

## Task 7: brain note 갱신 + git commit

- [ ] **Step 1: brain `notes/cpia-dummy-data-design-plan-2026-05-20` v2 갱신**

put_page slug = `notes/cpia-dummy-data-design-plan-2026-05-20`, type = note, 내용 = 적재 완료 fact + 정확성 검증 통과 + 최종 산식 anchor 비율 유지 + 5 페이지 UI 통과.

- [ ] **Step 2: brain `notes/cpia-dummy-poc-success-2026-05-20` 신규**

put_page slug = `notes/cpia-dummy-poc-success-2026-05-20`. 1 cycle dummy 적재 완료 + 532일 + 9-25 anchor 정합 + UI 검증 결과 link.

- [ ] **Step 3: brain `decisions/cpia-dummy-data-formula-stabilize-2026-05-20` 신규**

put_page slug = `decisions/cpia-dummy-data-formula-stabilize-2026-05-20`, type = decision. 산식 안정화 history (broken → 최종) + 4 fix 결정.

- [ ] **Step 4: git status + diff**

```bash
git status
git diff --stat
```

확인: scripts/seed_dummy_year.py + spec + plan 변경.

- [ ] **Step 5: git add + commit**

```bash
git add scripts/seed_dummy_year.py docs/superpowers/specs/2026-05-20-cpia-dummy-year-data-design.md docs/superpowers/plans/2026-05-20-cpia-dummy-year-data-plan.md
git commit -m "$(cat <<'EOF'
feat(dummy): 1년치 더미 데이터 적재 + spec + plan

- scripts/seed_dummy_year.py: cycle bypass + view_builder 직접 호출 + Chroma weekly sample
- 산식 안정화: anchor 진정값 비율 유지 + ±10% noise + delay ±30 clamp + NULL 역산
- 78사 anchor 보강 (anchor only 192 group 가상 plan 적재)
- diagnosis fixture 7 패턴 (LLM 호출 0)
- PoC 1일치 (9-24) UI 검증 통과 + 전 532일 적재 + 77일 Chroma 임베딩
- 9-25 anchor today_cum_qty 정합 ±10% 안에서 ≥70%

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: git push origin A_Track**

```bash
git push origin A_Track
```

---

## Task 8: PR 생성 (A_Track → main, 머지 보류)

- [ ] **Step 1: gh pr create**

```bash
gh pr create --title "feat(dummy): 1년치 더미 데이터 적재 (532일 PG + 77일 Chroma)" --body "$(cat <<'EOF'
## Summary
- `scripts/seed_dummy_year.py` cycle bypass — 24-04-11 ~ 25-09-24 (532일) 더미 적재
- 78사 anchor (9-25 mapper_activities) 와 누계 정합 ±10% 안 ≥70%
- 산점도 옆 diagnosis fixture 7 패턴 회전 (LLM 호출 0)
- UI 5 페이지 (dashboard / reports / tasks / export / review) console error 0
- 9 jsonb (kpi/cb/tb/qd/wps/sc/ov/pr/sn) 533 row 다 채움

## Test plan
- [x] PoC 1일치 (9-24) — 798 row + diagnosis fixture UI 표시
- [x] 전 532일 PG 적재 + 정합 검증 SQL (±10% within ≥70%)
- [x] 77일 Chroma daily_activities 임베딩 (~57K doc)
- [x] UI 5 페이지 playwright 재검증 (console error 0)
- [x] 디자인 불가침 룰 — web/ 컴포넌트 markup 변경 0

## Verification queries
- `psql ... -c "SELECT count(*) FROM daily_reports WHERE is_mock=FALSE"` → 533
- `psql ... -c "..."` (정합 검증, plan §11)

## 머지
조형준 프로님 결정 후. main 머지 시 시연 (5535) Compose 재빌드 필요: `docker compose build --no-cache web && docker compose up -d --force-recreate web`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 2: PR URL 확인 + 사용자 보고**

PR URL 출력. 사용자 명시 변형 flow 종료.

---

## Risks & Mitigation

| Risk | Mitigation |
|---|---|
| 전 적재 시 PG connection pool 고갈 (532일 × 8 테이블 × 800 row 평균) | PGClient pool max_size=5, 일자별 sequential. async semaphore 불필요. |
| Chroma upsert hang (이전 153bfa17 cycle 4시간 stuck 사례) | 이미 atomizer.py:113-122 의 batch=100 split 적용. |
| Azure embedding rate limit (77일 × 700 doc = 54K 호출) | text-embedding-3-small batch=100 → 540 batch. Azure tier 4 = 350 RPM → ~1.5분. |
| PG row count 너무 많아 일부 view_builder SQL 느려짐 (s_curve 의 generate_series) | PoC 검증 시 sc=532 정상. 만약 전 적재 시 30s+ 걸리면 view_builder Per-day 호출 X, 마지막 일자만 호출 + 이전 일자 cache. |
| anchor 인접 일자 (9-24) 의 cum 누계가 anchor today_cum_qty 보다 클 가능 (over) | safety cap plan_total × 3.0 적용 (현재 산식). |
| 시연 시 9-25 anchor cycle 다시 돌릴 시 dummy 충돌 | cleanup_by_companies.py 의 (site, date, company) 룰 활용. 별도 issue. |

---

## Next After This Plan

1. 머지 후 5535 Compose 재빌드 (조형준 프로 또는 본인)
2. 시연 dry-run (data freshness 검증)
3. 6/13 시연 리허설

---

**Plan complete.** Spec: `docs/superpowers/specs/2026-05-20-cpia-dummy-year-data-design.md`. 실행 시 `superpowers:executing-plans` skill (inline) 호출 또는 직접 task-by-task 진행.
