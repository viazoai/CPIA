# CPIA Review l7.5 매핑 · 이력기반 HIL · 누적 뷰 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** mapper 가 작업일보 활동을 WBS l7.5(작업단위)까지 매핑·적재하고, 그 l7.5 단위로 review 우측 카드를 누적 통합·좌측 숫자 정합·HIL 을 신규/불확실 l7.5 만으로 전환한다.

**Architecture:** 파이프라인(Python LangGraph): mapper 에 l7.5 선정 단계 신규 + requires_review 이력 게이트. 영속: mapper_activities 에 `l75_conf`/`l7_5_alternatives` 컬럼 추가. 웹(Next.js): registered API 를 l7.5 GROUP BY 누적으로, 좌측 트리 숫자를 distinct l7.5 로, 루트 전체집계 버그 수정 — 전부 SQL/데이터, **.tsx 마크업 불변(디자인 불가침)**. forecaster/optimizer/export 불변.

**Tech Stack:** Python 3.11(`pipeline/.venv`), asyncpg, AzureOpenAI(`LLM_MODEL`), LangGraph, PostgreSQL(43.200.85.209:5532), Next.js 14/TypeScript, postgres.js(`web/lib/pg`). 테스트: `pipeline/.venv/bin/python -m pytest` (pipeline), `cd web && npm test` (web).

**스펙:** `docs/superpowers/specs/2026-06-04-cpia-review-l75-hil-design.md` — 전체 결정(D1~D9)·CANON WHERE·실측 사실은 스펙 참조. 본 플랜은 그 스펙의 §9 구현순서를 bite-sized TDD 로 분해.

**검증된 실측 전제 (구현 중 재확인 불필요):** mapper_activities 에 `l75_conf` 없음(추가 대상). 시드/9-24 `requires_review=FALSE`(70,719+171), 9-25 라이브 `TRUE`(115). `today_qty=0/NULL` 0건. `l6_main↔l5_disc` 1:1. 시드 l7.5 커버 199/202.

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql` | l75_conf·l7_5_alternatives 컬럼 추가 | **신규** |
| `pipeline/state.py` | Activity TypedDict | l75_conf·l7_5_alternatives 필드 추가 |
| `pipeline/db.py` | insert_mapper_activities_batch (L668-777) | 37→39 param |
| `pipeline/agents/mapper.py` | map_activity l7.5 선정 + requires_review 게이트 | 신규 helper + L515-528 교체 + MapperConfig threshold |
| `pipeline/graph.py` | mapper_node batch(L86-108) + _apply_corrections(L235-267) | l7.5 후보맵·이력set batch + l7_5 보정 |
| `pipeline/api.py` | CorrectionItem(L45-49) | l7_5_activity 필드 |
| `web/app/api/mock/review/registered/route.ts` | 누적 API | GROUP BY l7.5 SUM, wa NULL |
| `web/lib/review-node.ts` | nodeToQuery, RegisteredQuery | building 분기, wa nullable |
| `web/app/(app)/review/page.tsx` | param 직렬화(L62), corrections payload, 인지신호 | wa 조건부 set, l7_5 채널 |
| `web/lib/transforms.ts` | wbsTreeBuild activity_agg(L212-235) | 686 leaf 폐기 → distinct l7.5 |

테스트: `pipeline/tests/test_mapper_l75.py`(신규), `pipeline/tests/test_requires_review_gate.py`(신규), `web/` 기존 테스트 패턴 따름.

---

## Task 0: git pull → main 싱크 (실 코드 작업 전 필수)

**Files:** (없음 — 환경 준비)

- [ ] **Step 1: 현재 브랜치·상태 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && git status && git branch --show-current && git log --oneline -3`
Expected: 작업트리 상태·현재 브랜치 표시.

- [ ] **Step 2: origin/main fetch + 싱크**

Run: `git fetch origin && git log --oneline origin/main -3`
Expected: 원격 main 최신 커밋 표시. 로컬이 뒤처졌으면 `git pull --ff-only origin main` (또는 작업 브랜치면 `git merge origin/main`). 충돌 시 멈추고 보고.

- [ ] **Step 3: DB 마이그레이션 적용 상태 확인 (싱크 후)**

Run: `ls infra/postgres/migrations/ | tail -5`
Expected: 최신 마이그레이션 목록. (l75_conf 마이그레이션은 Task 1 에서 신규 생성.)

> 머지 전략: 스펙대로 PoC. 사용자가 "직접 머지 OK" 선례(d317be9) 있으나, **이 플랜의 커밋은 작업 브랜치에 쌓고 머지 시점은 사용자 확인.** main 직접 푸시 금지(명시 지시 전).

---

## Task 1: 스키마 — l75_conf · l7_5_alternatives 컬럼

**Files:**
- Create: `infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql`
- Modify: `pipeline/state.py:32-95` (Activity TypedDict)
- Modify: `pipeline/db.py:668-777` (insert_mapper_activities_batch)
- Test: `pipeline/tests/test_mapper_l75.py` (신규)

- [ ] **Step 1: 마이그레이션 파일 작성**

```sql
-- infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql
-- l7.5 선정 신뢰도(0~1). mapping_conf(l6 conf)와 별개.
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l75_conf double precision;
-- HIL 대안: l6 밑 l7.5 후보 top-K [{label, score}]
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l7_5_alternatives jsonb;
```

- [ ] **Step 2: 마이그레이션 적용 + 컬럼 확인**

Run:
```bash
export PGPASSWORD='K7mP2xQ9nR4v'
/opt/homebrew/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia -f infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql
/opt/homebrew/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia -At -c "SELECT column_name FROM information_schema.columns WHERE table_name='mapper_activities' AND column_name IN ('l75_conf','l7_5_alternatives');"
```
Expected: `l75_conf` 와 `l7_5_alternatives` 두 줄 출력.

- [ ] **Step 3: Activity TypedDict 필드 추가**

`pipeline/state.py` Activity 에 (l7_5_activity 근처 L73 뒤):
```python
    l75_conf: float | None  # l7.5 선정 신뢰도 (mapping_conf 는 l6 conf — 별개)
    l7_5_alternatives: list[dict] | None  # HIL 대안 [{label, score}]
```

- [ ] **Step 4: db.py INSERT 37→39 param (4곳)**

`pipeline/db.py:668-777` 의 `insert_mapper_activities_batch`:
1. 컬럼 리스트(L684 끝)에 `, l75_conf, l7_5_alternatives` 추가.
2. VALUES(L698 `$37` 뒤)에 `, $38, $39::jsonb` 추가.
3. ON CONFLICT SET(L733 `sub_work_area` 뒤)에:
```sql
                    ,
                    l75_conf           = EXCLUDED.l75_conf,
                    l7_5_alternatives  = EXCLUDED.l7_5_alternatives
```
4. 튜플(L773 `a.get("sub_work_area")` 뒤)에:
```python
                        a.get("l75_conf"),
                        _json.dumps(a.get("l7_5_alternatives") or [], ensure_ascii=False),
```

- [ ] **Step 5: 라운드트립 테스트 작성 (실패 확인)**

`pipeline/tests/test_mapper_l75.py`:
```python
from __future__ import annotations
import pytest, uuid, datetime
from pipeline.db import PGClient
import os

PG = os.environ["POSTGRES_URL"]

@pytest.mark.asyncio
async def test_l75_columns_roundtrip():
    pg = PGClient(PG); await pg.connect()
    run_id = uuid.uuid4()
    try:
        await pg.insert_pipeline_run(run_id, "m15x-ph3-ibl", datetime.date(2025,9,25), "test")  # 인자 순서는 db.py:147 시그니처 확인
        act = {"company":"T","trade":"건축","unit":"m2","today_qty":1.0,
               "wa":"FAB","l6_main":"수장공사","l7_5_activity":"경량벽체 설치",
               "l75_conf":0.92,"l7_5_alternatives":[{"label":"경량벽체 설치","score":0.92}],
               "requires_review":False}
        await pg.insert_mapper_activities_batch(run_id, datetime.date(2025,9,25), [act])
        rows = await pg.fetch_all("SELECT l75_conf, l7_5_alternatives FROM mapper_activities WHERE run_id=$1", run_id)
        assert rows, "row not inserted"
        assert float(rows[0]["l75_conf"]) == 0.92
        import json as _j
        alts = rows[0]["l7_5_alternatives"]
        alts = _j.loads(alts) if isinstance(alts, str) else alts
        assert alts[0]["label"] == "경량벽체 설치"
    finally:
        await pg.fetch_all("DELETE FROM mapper_activities WHERE run_id=$1", run_id)  # asyncpg: RETURNING 없는 DELETE → []
        await pg.delete_pipeline_run(run_id)
        await pg.close()
```
> PGClient 실 메서드: `fetch_one`/`fetch_all`(db.py:1040,1051)·`insert_pipeline_run`(:147)·`delete_pipeline_run`(:170). `fetch`/`con_execute` 없음. hasattr 가드 제거 — 실 메서드 직접 호출(침묵 PASS 방지).

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && set -a; source .env; set +a; pipeline/.venv/bin/python -m pytest pipeline/tests/test_mapper_l75.py::test_l75_columns_roundtrip -v`
Expected: 컬럼 추가 전이면 FAIL(컬럼 없음) → Step 2 적용 후 재실행.

- [ ] **Step 6: 테스트 통과 확인**

Run: 위 동일.
Expected: PASS (l75_conf=0.92, alternatives label 일치).

- [ ] **Step 7: Commit**

```bash
git add infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql pipeline/state.py pipeline/db.py pipeline/tests/test_mapper_l75.py
git commit -m "feat(mapper): add l75_conf, l7_5_alternatives columns + INSERT 39-param"
```

---

## Task 2: mapper l7.5 매핑 신규 (적재 전용)

**Files:**
- Modify: `pipeline/agents/mapper.py` (신규 helper `pick_l75` + map_activity 반환 L519-528 + MapperConfig L348-362)
- Modify: `pipeline/graph.py:86-108` (mapper_node 에 l7.5 후보맵 batch)
- Test: `pipeline/tests/test_mapper_l75.py`

- [ ] **Step 1: MapperConfig 에 threshold 추가**

`pipeline/agents/mapper.py` MapperConfig(L360 `conf_threshold` 근처):
```python
    l75_conf_threshold: float = 0.7  # l7.5 선정 신뢰도 게이트 (env CPIA_L75_CONF_THRESHOLD)
```
그리고 `pipeline/api.py` MapperConfig 빌드처(L113)에 `l75_conf_threshold=float(os.environ.get("CPIA_L75_CONF_THRESHOLD","0.7"))` 추가.

- [ ] **Step 2: l7.5 후보맵 batch fetch (mapper_node)**

`pipeline/graph.py:86-96` bp_cand_lookup batch 블록에 이어 (같은 pg 연결 재사용):
```python
        # l7.5 후보맵: site+l5_disc(건축/토목) 의 l6 → [l7.5...] (activity별 l6 가 LLM 후 결정되므로 전체 1회 fetch)
        # activity_master 는 site_id 컬럼 보유. site_id 는 state["site_id"](CPIAState L233)에서.
        _site_id = state.get("site_id") or "m15x-ph3-ibl"
        l75_cand_rows = await pg.fetch_all(
            """SELECT l6_main, ARRAY_AGG(DISTINCT l7_5_activity) AS l75s
               FROM activity_master WHERE site_id=$1 AND l5_disc IN ('건축','토목')
                 AND l7_5_activity IS NOT NULL GROUP BY l6_main""",
            _site_id)
        l75_cand_map: dict[str, list[str]] = {r["l6_main"]: list(r["l75s"]) for r in l75_cand_rows}
```
그리고 `map_activity(... , l75_cand_map=l75_cand_map)` 로 전달(시그니처에 kwarg 추가, 기본 None).

- [ ] **Step 3: pick_l75 helper + map_activity 통합 (실패 테스트 먼저)**

`pipeline/tests/test_mapper_l75.py` 추가:
```python
@pytest.mark.asyncio
async def test_pick_l75_specific(monkeypatch):
    # LLM 고정(드라이): "기초 거푸집 설치" + 후보 → 기초공사:거푸집 공사
    from pipeline.agents import mapper as M
    cands = ["기초공사 : 거푸집 공사", "기초공사 : 철근 콘크리트 타설", "RC Wall & Column 공사 : 거푸집 공사"]
    monkeypatch.setattr(M, "_call_l75_llm", lambda *a, **k: {"choice":0,"confidence":0.99,"reason":"x"})
    out = await M.pick_l75("기초 거푸집 설치", "철근콘크리트공사", "광건", "m2", cands, cfg=None)
    assert out["l7_5_activity"] == "기초공사 : 거푸집 공사"
    assert out["l75_conf"] == 0.99
    assert out["l7_5_alternatives"][0]["label"] in cands

@pytest.mark.asyncio
async def test_pick_l75_none(monkeypatch):
    from pipeline.agents import mapper as M
    monkeypatch.setattr(M, "_call_l75_llm", lambda *a, **k: {"choice":-1,"confidence":0.2,"reason":"no fit"})
    out = await M.pick_l75("비계 설치", "외장판넬공사", "남웅", "m2", ["Glass Wool Panel 설치","Wind Column 설치"], cfg=None)
    assert out["l7_5_activity"] is None  # 미분류
    assert out["l75_conf"] == 0.0
    assert len(out["l7_5_alternatives"]) >= 1  # 후보는 채워둠
```

Run: `... pytest pipeline/tests/test_mapper_l75.py -v -k pick_l75`
Expected: FAIL (pick_l75 미정의).

- [ ] **Step 4: pick_l75 구현**

`pipeline/agents/mapper.py` 에 (PoC `tmp/poc_l75_pageindex.py` 의 검증된 프롬프트 재사용):
```python
def _call_l75_llm(client, model, work_content, l6, company, unit, candidates) -> dict:
    cand_str = "\n".join(f"[{i}] {c}" for i, c in enumerate(candidates))
    user_msg = (
        f"건설 작업일보 1행을, 같은 공종(L6) 밑 세부작업(L7.5) 후보 중 가장 맞는 1개로 분류.\n"
        f"맞는 후보가 없거나 애매하면 choice=-1.\n\n"
        f"### 작업일보\n작업내용: {work_content}\n업체: {company}\n단위: {unit}\n공종(L6): {l6}\n\n"
        f"### L7.5 후보\n{cand_str}\n\n"
        f'### 응답 (JSON only)\n{{"choice": <int 또는 -1>, "confidence": <0.0~1.0>, "reason": "<짧게>"}}')
    resp = client.chat.completions.create(model=model,
        messages=[{"role":"system","content":"건설 작업일보 ↔ WBS L7.5 분류기. 한국어."},
                  {"role":"user","content":user_msg}],
        response_format={"type":"json_object"})
    return json.loads(resp.choices[0].message.content)

async def pick_l75(work_content, l6, company, unit, candidates, cfg) -> dict:
    """l6 밑 master l7.5 후보 중 best 선정. 반환 {l7_5_activity, l75_conf, l7_5_alternatives}."""
    if not candidates:
        return {"l7_5_activity": None, "l75_conf": 0.0, "l7_5_alternatives": []}
    client = AzureOpenAI(api_key=cfg.azure_api_key, api_version=cfg.azure_api_version, azure_endpoint=cfg.azure_endpoint)
    try:
        out = await asyncio.to_thread(_call_l75_llm, client, cfg.llm_model, work_content, l6, company, unit, candidates)
    except Exception:
        out = {"choice": -1, "confidence": 0.0}
    ch = out.get("choice", -1)
    alts = [{"label": c, "score": 0.0} for c in candidates[:5]]
    if isinstance(ch, int) and 0 <= ch < len(candidates):
        return {"l7_5_activity": candidates[ch], "l75_conf": float(out.get("confidence", 0.0)),
                "l7_5_alternatives": alts}
    return {"l7_5_activity": None, "l75_conf": 0.0, "l7_5_alternatives": alts}
```
> test 의 monkeypatch 가 `_call_l75_llm` 를 갈아끼우므로 cfg=None 에서도 client 생성 전에 LLM 호출이 대체됨 — 구현 시 cfg None 가드(테스트용) 또는 client 생성을 _call 안으로 이동. 드라이 테스트(LLM bypass) 원칙 준수.

- [ ] **Step 5: map_activity 에서 pick_l75 호출 + 반환 병합**

`pipeline/agents/mapper.py` map_activity 반환(L519-528) 직전에:
```python
    l75 = await pick_l75(activity.get("work_content",""), chosen_key[1],
                         activity["company"], activity.get("unit",""),
                         (l75_cand_map or {}).get(chosen_key[1], []), cfg)
```
반환 dict 에 병합: `"l7_5_activity": l75["l7_5_activity"], "l75_conf": l75["l75_conf"], "l7_5_alternatives": l75["l7_5_alternatives"],`

- [ ] **Step 6: 테스트 통과**

Run: `... pytest pipeline/tests/test_mapper_l75.py -v -k pick_l75`
Expected: PASS (specific→기초공사:거푸집 공사/0.99, none→None/미분류).

- [ ] **Step 7: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/graph.py pipeline/api.py pipeline/tests/test_mapper_l75.py
git commit -m "feat(mapper): l7.5 pageindex selection (pick_l75) + candidate batch, store l75_conf/alternatives"
```

---

## Task 3: requires_review 이력 게이트

**Files:**
- Modify: `pipeline/agents/mapper.py:515-525` (requires_review 교체)
- Modify: `pipeline/graph.py:86-108` (has_history set batch + map_activity 전달)
- Test: `pipeline/tests/test_requires_review_gate.py` (신규)

- [ ] **Step 1: 게이트 단위 테스트 (실패 먼저)**

`pipeline/tests/test_requires_review_gate.py`:
```python
from __future__ import annotations
from pipeline.agents.mapper import compute_requires_review

HIST = {("철근콘크리트공사","기초공사 : 거푸집 공사")}  # 시드 이력

def test_confident_with_history_auto():
    assert compute_requires_review("기초공사 : 거푸집 공사","철근콘크리트공사",0.99,HIST,0.7,"auto_llm_rerank") is False
def test_low_conf_hil():
    assert compute_requires_review("기초공사 : 거푸집 공사","철근콘크리트공사",0.5,HIST,0.7,"auto_llm_rerank") is True
def test_novel_l75_hil():
    assert compute_requires_review("2차 포장","포장공사",0.95,HIST,0.7,"auto_llm_rerank") is True
def test_unclassified_hil():
    assert compute_requires_review(None,"외장판넬공사",0.0,HIST,0.7,"auto_llm_rerank") is True
def test_user_corrected_exempt():
    assert compute_requires_review(None,"외장판넬공사",0.0,HIST,0.7,"user_corrected") is False
```
Run: `... pytest pipeline/tests/test_requires_review_gate.py -v`
Expected: FAIL (compute_requires_review 미정의).

- [ ] **Step 2: compute_requires_review 구현 + map_activity 적용**

`pipeline/agents/mapper.py`:
```python
def compute_requires_review(l7_5, l6, l75_conf, history_set, threshold, mapping_source) -> bool:
    if mapping_source == "user_corrected":   # 사람이 이미 검토·확정(미분류 포함) → 면제 (D9)
        return False
    if l7_5 is None or l7_5 == "":
        return True                          # 미분류
    if l75_conf is None or l75_conf < threshold:
        return True                          # 불확실
    if (l6, l7_5) not in history_set:
        return True                          # 신규 l7.5
    return False
```
map_activity 반환에서 `requires_review = True` 하드코딩(L517) 제거 →
```python
    requires_review = compute_requires_review(
        l75["l7_5_activity"], chosen_key[1], l75["l75_conf"],
        (history_set or set()), cfg.l75_conf_threshold, wa_result.source)
```
(map_activity 시그니처에 `history_set: set | None = None` kwarg 추가.)

- [ ] **Step 3: has_history set batch (mapper_node)**

`pipeline/graph.py` l75_cand_map batch 옆 (★ mapper_activities 에는 site_id 컬럼 **없음** → pipeline_runs JOIN 필수):
```python
        hist_rows = await pg.fetch_all(
            """SELECT DISTINCT ma.l6_main, ma.l7_5_activity
               FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
               WHERE pr.site_id=$1 AND ma.l7_5_activity IS NOT NULL AND ma.l7_5_activity<>''""",
            _site_id)
        history_set = {(r["l6_main"], r["l7_5_activity"]) for r in hist_rows}
```
> `_site_id = state.get("site_id") or "m15x-ph3-ibl"` (Step2 에서 이미 정의). `_map_one` → `map_activity(..., history_set=history_set, l75_cand_map=l75_cand_map)` 로 두 인자 전달. (mapper_activities.site_id 컬럼 부재 검증됨 — 반드시 JOIN.)

- [ ] **Step 4: 테스트 통과**

Run: `... pytest pipeline/tests/test_requires_review_gate.py -v`
Expected: PASS (5건: auto/low_conf/novel/unclassified/user_corrected).

- [ ] **Step 4b: 기존 회귀 테스트 갱신 (★ requires_review=True 하드코딩 폐기로 깨짐)**

`pipeline/tests/test_mapper_requires_review_all.py` 는 "모든 매핑 requires_review=True" 를 단언 — Task3 후 깨진다. 새 게이트 동작(이력 l7.5=자동승인, 신규/저conf/미분류=HIL)으로 단언 갱신하거나, compute_requires_review 단위테스트(test_requires_review_gate.py)로 대체했으면 폐기.
Run: `... pytest pipeline/tests/test_mapper_requires_review_all.py -v`
Expected: 갱신 후 PASS (옛 "전건 True" 단언 제거됨).

- [ ] **Step 5: Commit**

```bash
git add pipeline/agents/mapper.py pipeline/graph.py pipeline/tests/test_requires_review_gate.py pipeline/tests/test_mapper_requires_review_all.py
git commit -m "feat(mapper): history-based requires_review gate (novel OR low-conf OR null, user_corrected exempt)"
```

---

## Task 4: review 누적 API + 루트 전체집계

**Files:**
- Modify: `web/app/api/mock/review/registered/route.ts` (전체 SQL/매핑)
- Modify: `web/lib/review-node.ts` (building 분기, wa nullable)
- Modify: `web/app/(app)/review/page.tsx:62` (param 직렬화)
- Test: web 기존 테스트 패턴(있으면) + 수동 curl 검증

- [ ] **Step 1: review-node.ts — wa nullable + building 분기**

`web/lib/review-node.ts`: `RegisteredQuery.wa: string | null;` 로. nodeToQuery 마지막 `return null;` 앞에:
```ts
  if (node.type === "building") return { wa: null, l5: null, l6: null };
```

- [ ] **Step 2: page.tsx param 직렬화 교체 (L62)**

현재 `const params = new URLSearchParams({ wa: q.wa });` 를:
```ts
  const params = new URLSearchParams();
  if (q.wa) params.set("wa", q.wa);
  if (q.l5) params.set("l5", q.l5);
  if (q.l6) params.set("l6", q.l6);
```
(기존 `if(q.l5)... if(q.l6)...` 가 이미 있으면 wa 만 조건부로.)

- [ ] **Step 3: registered route — 누적 GROUP BY + wa NULL**

`web/app/api/mock/review/registered/route.ts`:
- L17 `if(!wa) return 400` **제거**. `const wa = url.searchParams.get("wa"); const waParam = (wa && wa !== "null") ? wa : null;`
- SQL 교체(스펙 §4.3 CANON WHERE):
```ts
const rows = (await (sql as any)`
  SELECT ma.wa, ma.l6_main,
         COALESCE(NULLIF(ma.l7_5_activity,''),'미분류') AS l75_label,
         ROUND(SUM(ma.today_qty)::numeric,2) AS cum_qty,
         MAX(ma.unit) AS unit, COUNT(DISTINCT ma.company) AS company_n
  FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
  WHERE pr.site_id=${siteId} AND ma.is_mock=${useMock}
    AND ma.l6_main IS NOT NULL AND ma.trade IN ('건축','토목') AND ma.requires_review=FALSE
    AND (${waParam}::text IS NULL OR ma.wa=${waParam})
    AND (${l6}::text IS NULL OR ma.l6_main=${l6})
    AND (${l5}::text IS NULL OR ma.l5_disc=${l5})
  GROUP BY ma.wa, ma.l6_main, l75_label
  ORDER BY cum_qty DESC`) as Array<any>;
```
(LIMIT 제거.)
- ReviewItem 매핑(스펙 §4.3):
```ts
const items: ReviewItem[] = rows.map((r) => {
  const m = deriveWpIdAndPath(r.wa, r.l6_main, siteName);
  return {
    id: `reg-${r.wa}-${r.l6_main}-${r.l75_label}`, idx: -1,
    bp_name: Number(r.company_n) > 1 ? `${r.company_n}개사` : (r.company ?? ""),
    work_content: r.l75_label, quantity: Number(r.cum_qty), unit: r.unit ?? "",
    ai_mapped_wp_id: m.wp_id, ai_mapped_path: `${m.path} > ${r.l75_label}`,
    wa: r.wa, l6_main: r.l6_main, confidence: 1.0,
    status: "confirmed", alternative_wps: [],
  };
});
const total = items.length;
```

- [ ] **Step 4: 수동 검증 (dev 5537 + 실 DB)**

Run: dev 서버 떠있는 상태에서
```bash
curl -s 'http://127.0.0.1:5537/api/mock/review/registered?wa=FAB&l6=철근콘크리트공사' | python3 -c "import sys,json; d=json.load(sys.stdin); print('rows',len(d['items'])); [print(i['work_content'], i['quantity'], i['unit']) for i in d['items'][:6]]"
```
Expected: l7.5 라벨 행들 + 누적물량(2자리, 예 기초공사:거푸집 공사 5741.6 m2). work_content 가 조건문이 아니라 l7.5.
```bash
curl -s 'http://127.0.0.1:5537/api/mock/review/registered' | python3 -c "import sys,json; d=json.load(sys.stdin); print('root rows', len(d['items']))"
```
Expected: 루트(wa 없음) → 전체집계 비어있지 않음(>0). (기존 버그면 400/빈배열.)

- [ ] **Step 5: Commit**

```bash
git add web/app/api/mock/review/registered/route.ts web/lib/review-node.ts "web/app/(app)/review/page.tsx"
git commit -m "feat(review): cumulative l7.5 GROUP BY + SUM(2dp) + root(wa NULL) aggregation"
```

---

## Task 5: 좌측 카드 숫자 = 활성 distinct l7.5 (686 leaf 폐기)

**Files:**
- Modify: `web/lib/transforms.ts:212-235` (active_l75 + activity_agg 교체)

- [ ] **Step 1: activity_agg CTE 교체**

`web/lib/transforms.ts` 의 `active_l75`+`activity_agg`(686 leaf 역매핑, activity_master JOIN) **삭제** → 단일 CTE(스펙 §4.6, CANON WHERE 동일):
```sql
activity_agg AS (
  SELECT ma.wa, ma.l6_main,
         COUNT(DISTINCT COALESCE(NULLIF(ma.l7_5_activity,''),'미분류')) AS total_count
  FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
  WHERE pr.site_id = ${siteId} AND ma.is_mock = ${useMock}
    AND ma.l6_main IS NOT NULL AND ma.trade IN ('건축','토목') AND ma.requires_review = FALSE
  GROUP BY ma.wa, ma.l6_main
)
```
이후 JS 롤업(node.total_count, wa=Σl6, root=Σwa)은 그대로. `review_agg`(AlertCircle) 불변.

- [ ] **Step 2: D8 불변식 수동 검증 (dev UI)**

Run: dev 5537 review 에서 좌측 l6 노드 숫자 추출 + 그 l6 클릭 시 우측 행수 비교:
```bash
curl -s 'http://127.0.0.1:5537/api/mock/review/registered?wa=FAB&l6=철근콘크리트공사' | python3 -c "import sys,json;print('우측행수',len(json.load(sys.stdin)['items']))"
```
좌측 숫자(트리 API 또는 DOM)와 동일해야 함. 또는 직접 SQL 로 좌(distinct)·우(group rows) 둘 다 세어 일치 확인:
```bash
export PGPASSWORD='K7mP2xQ9nR4v'
/opt/homebrew/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia -At -c "SELECT COUNT(DISTINCT COALESCE(NULLIF(l7_5_activity,''),'미분류')) FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id) WHERE pr.site_id='m15x-ph3-ibl' AND ma.trade IN ('건축','토목') AND ma.l6_main='철근콘크리트공사' AND ma.requires_review=FALSE AND ma.wa='FAB';"
```
Expected: 좌측 숫자 == 우측 행수 (동일 CANON WHERE).

- [ ] **Step 3: Commit**

```bash
git add web/lib/transforms.ts
git commit -m "refactor(review): left card = distinct active l7.5 (revert 686 leaf metric, D8 invariant)"
```

---

## Task 6: HIL 카드 l7.5 노출 (경로 + 대안 shape)

**Files:**
- Modify: HIL 항목 ReviewItem 생성 경로 (스펙 §1: `web/app/api/mock/review/route.ts` 또는 hil payload 빌더 — 구현 시 grep 으로 확정)

- [ ] **Step 1: HIL ReviewItem 에 l7.5 경로 + 대안 주입**

requires_review=TRUE 항목 매핑 시:
- `ai_mapped_path` = `deriveWpIdAndPath(wa,l6).path` + `" > " + (l7_5_activity ?? "미분류")`.
- `alternative_wps` = `l7_5_alternatives` 를 **shape rename**(스펙 §4.4): `(l7_5_alternatives ?? []).map((x,i)=>({id:`l75-${i}`, path:x.label, score:x.score}))`. (ReviewCard L80 이 `a.path.split(" > ").pop()`·`a.score` 읽음 → throw 회피.)

- [ ] **Step 2: 수동 검증**

Run: dev 5537 review "신규 확정 필요만 보기" 카드의 경로에 l7.5(또는 미분류) 표시 + 대안에 l7.5 후보 텍스트 확인 (Playwright DOM 추출 또는 육안).
Expected: 경로 "…> C/R 조성공사 > 에폭시페인트 도장" 류, 대안 l7.5 텍스트.

- [ ] **Step 3: Commit**

```bash
git add web/app/api/mock/review/route.ts
git commit -m "feat(review/hil): expose l7.5 in mapping path + l7.5 alternatives (shape-mapped)"
```

---

## Task 7: l7.5 사람 수정 계약 (BE 완비 + FE 마크업 불변)

**Files:**
- Modify: `pipeline/api.py:45-49` (CorrectionItem)
- Modify: `pipeline/graph.py:235-267` (_apply_corrections)
- Modify: `pipeline/db.py` (insert_mapping_correction — l7_5 컬럼)
- Modify: `web/app/(app)/review/page.tsx` (corrections payload), `web/app/api/hil/resume/route.ts`
- Test: `pipeline/tests/test_requires_review_gate.py` 에 _apply_corrections 케이스 추가

- [ ] **Step 1: _apply_corrections 테스트 (실패 먼저)**

```python
from pipeline.graph import _apply_corrections
def test_apply_l75_remap_to_unclassified():
    mapped=[{"company":"A","l6_main":"외장판넬공사","l7_5_activity":"Glass Wool Panel 설치","requires_review":True}]
    out=_apply_corrections(mapped, {0:{"wa":"FAB","l6_main":"수장공사"}})  # l6 변경, l7.5 미지정
    assert out[0]["l7_5_activity"] is None  # → 미분류
    assert out[0]["mapping_source"]=="user_corrected" and out[0]["requires_review"] is False
def test_apply_l75_explicit():
    mapped=[{"company":"A","l6_main":"수장공사","l7_5_activity":None,"requires_review":True}]
    out=_apply_corrections(mapped, {0:{"wa":"CUB","l6_main":"수장공사","l7_5_activity":"경량벽체 설치"}})
    assert out[0]["l7_5_activity"]=="경량벽체 설치"
```
Run: `... pytest pipeline/tests/test_requires_review_gate.py -v -k apply`
Expected: FAIL.

- [ ] **Step 2: CorrectionItem + _apply_corrections + insert_mapping_correction**

`pipeline/api.py` CorrectionItem 에:
```python
    l7_5_activity: Optional[str] = None  # 사람이 l7.5 지정. None+l6 변경 시 미분류.
```
`pipeline/graph.py` _apply_corrections(L250-257) `c` 처리:
```python
            if c:
                l6_changed = c["l6_main"] != a.get("l6_main")
                new_l75 = c.get("l7_5_activity") if "l7_5_activity" in c else (None if l6_changed else a.get("l7_5_activity"))
                new_a = {**a, "wa": c["wa"], "l6_main": c["l6_main"],
                         "l7_5_activity": new_l75,
                         "mapping_source": "user_corrected", "requires_review": False}
```
`insert_mapping_correction`(실제 db.py:374-407 — `original`/`corrected` **JSONB 2컬럼**만 사용)에 l7_5_activity 영속: **ALTER TABLE 불요.** `corrected` JSONB dict 안에 `l7_5_activity` 키를 포함시키면 됨(스키마 변경 없음). graph.py 가 corrected dict 구성 시 `{"wa":..., "l6_main":..., "l7_5_activity":...}` 로 넣을 것. (Task1 마이그레이션에 mapping_corrections 변경 추가 금지 — 불필요 컬럼/NOT NULL 위반 위험.)

- [ ] **Step 3: FE payload + resume 프록시**

`web/app/(app)/review/page.tsx` handleConfirmAll/handleRemap 의 corrections 페이로드 타입에 `l7_5_activity?: string|null` 추가. 현재 FE 는 직접 l7.5 picker 미제공(디자인 불가침) → **l6 재매핑 시 `l7_5_activity:null`(미분류), 단순 확정 시 생략**(best-guess 유지). `web/app/api/hil/resume/route.ts` 가 corrections 를 그대로 전달하는지 확인(필드 통과).

- [ ] **Step 4: 테스트 통과**

Run: `... pytest pipeline/tests/test_requires_review_gate.py -v -k apply`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/api.py pipeline/graph.py pipeline/db.py "web/app/(app)/review/page.tsx" web/app/api/hil/resume/route.ts pipeline/tests/test_requires_review_gate.py
git commit -m "feat(hil): l7.5 in corrections contract (l6 remap -> unclassified, BE wired, FE markup-neutral)"
```

---

## Task 8: 누적 41% 과소표시 인지 신호 (기존 슬롯)

**Files:**
- Modify: `web/app/(app)/review/page.tsx` (기존 "총 X건 중 Y" 류 텍스트 슬롯)

- [ ] **Step 1: 기존 슬롯 확인**

Run: `grep -n "총\|건 중\|registeredTotal\|검토대기\|requires_review" web/app/(app)/review/page.tsx | head`
Expected: 기존 카운트 표시 슬롯 위치.

- [ ] **Step 2: 확정 N · 검토대기 M 텍스트 주입 (마크업 불변)**

기존 텍스트 슬롯에 review_agg 검토대기 카운트 + 누적(확정) 카운트를 데이터로 노출. 새 배지/엘리먼트 추가 금지 — 기존 문구 자리 재사용. 정확 슬롯은 Step1 결과로 확정.

- [ ] **Step 3: 수동 검증 + Commit**

Run: dev 5537 에서 "확정 N · 검토대기 M" 노출 확인.
```bash
git add "web/app/(app)/review/page.tsx"
git commit -m "feat(review): surface confirmed/pending counts in existing slot (undercount awareness)"
```

---

## Task 9: 드라이 테스트 스위트 + 실 9/25 재측정

**Files:**
- Test: `pipeline/tests/test_mapper_l75.py`, `pipeline/tests/test_requires_review_gate.py` 보강
- Modify: (회귀 확인만)

- [ ] **Step 1: 불변 회귀 — forecaster/optimizer/exporter 출력 불변**

Run: 기존 e2e/golden 테스트 (있으면) 실행.
```bash
... pipeline/.venv/bin/python -m pytest pipeline/tests/ -v -k "forecast or optimizer or export or golden" 2>&1 | tail -20
```
Expected: PASS (l7.5 추가가 l6+wa 경로에 영향 0).

- [ ] **Step 2: D8 불변식 테스트 (좌==우, today_qty=0·l6걸침 픽스처)**

`web/` 또는 pipeline 통합 테스트로 좌측 distinct == 우측 group rows 픽스처 검증(스펙 §7). today_qty=0 행, l6 가 2 l5 에 걸치는 행(현 0건이나 회귀 방어) 포함.

- [ ] **Step 3: 실 9/25 재측정 (자동/HIL 비율 + mapper 소요)**

Run: 라이브 파이프라인 9/25 run 1회 + 측정:
```bash
export PGPASSWORD='K7mP2xQ9nR4v'
/opt/homebrew/bin/psql -h 43.200.85.209 -p 5532 -U cpia -d cpia -At -c "SELECT requires_review, COUNT(*) FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id) WHERE pr.report_date='2025-09-25' AND ma.trade IN ('건축','토목') GROUP BY 1;"
```
Expected: 자동승인(FALSE) ~59% / HIL(TRUE) ~41% (PoC 대조). THRESHOLD 0.7 로 서사 안 맞으면 `CPIA_L75_CONF_THRESHOLD` 조정 후 재측정. mapper 소요(LLM 2배) 실측해 데모 5분 서사 대조.

- [ ] **Step 4: 최종 Commit**

```bash
git add pipeline/tests/
git commit -m "test(l75): dry-test suite + D8 invariant + invariance regression"
```

---

## 구현 후

- 전체 e2e 라이브(parser→mapper l7.5→HIL→review 누적) 1회 통과 확인.
- 머지: 작업 브랜치 → 사용자 확인 후 main (직접 머지 지시 있으면 PR 생략 가능, 선례 d317be9).
- Compose 데모(:5535)면 `make build` 1회.
