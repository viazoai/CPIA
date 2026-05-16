# CPIA 다운스트림 에이전트 — 데이터 흐름 정합 spec + Atomizer 구현 spec

> **본 spec 의 산물**: ① 4 다운스트림 에이전트 (Atomizer / Reporter / Forecaster / Optimizer) 의 데이터 계약 정합 + ② Atomizer 즉시 구현 spec. Reporter / Forecaster / Optimizer 의 구현 spec 은 별도 brainstorming 사이클로 분리.
>
> 작성: 2026-05-16 (A 트랙) · 기반: PM 원안 (`CLAUDE.md`, `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md`), 스키마 3종 (`state.md` / `postgres.md` / `mapping-layer.md`), `example-walkthrough.md`, v1 골든 (`planning/simulation/생산성_시뮬레이션_결과.md`), 9/25 실 작업일보 + PG `activity_master` 실 호출.
>
> **리뷰 반영**: 2026-05-16 coherence-reviewer + feasibility-reviewer 의 13 발견 사항 모두 정정 (Blocker 2 / Critical 4 / Major 4 / Minor 3).

---

## 0. 한눈에 보기 + 결정 사항 13건

본 brainstorming 에서 확정된 결정:

| # | 사안 | 결정 |
|---|---|---|
| 1 | spec 범위 | 통합 흐름 (4 에이전트 데이터 계약) + Atomizer 즉시 구현 |
| 2 | Mapper output 미충 필드 처리 | `wbs_activity_id`/`l7_sub`/`l7_5_activity`/`sub_work_area`/`plan_total_qty`/`plan_mh` = PoC 단계 항상 None (1:N 라 단일값 결정 불가) |
| 3 | MH 분배 알고리즘 | **옵션 X** — (company, l6_main) 단위. BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh) |
| 4 | `_prorate_mh()` 위치 | `pipeline/agents/mapper.py` 안 batch 함수 (graph.py 의 mapper_node 가 호출) |
| 5 | Forecaster grain | **(company, l6_main)** — unit 별 분리 X. unit 별 today_qty / plan_total_qty 는 JSONB 보존 (집계 = `Σ Activity unit별 today_qty`) |
| 6 | 그래프 분기 | Atomizer → Forecaster → Reporter 순차 (Reporter 가 진단 포함 가능) |
| 7 | Atomizer doc_id | `sha256(date|company|l6_main|work_content)[:16]` — 결정성 upsert |
| 8 | Atomizer requires_review 처리 | PoC: 무시 (전부 적재). `mapping_conf` 메타 보존. |
| 9 | atomized_ids 영속화 | state 안 + PG `pipeline_runs.atomized_count` (count 만) |
| 10 | LLM 모델 정합화 | Atomizer 없음 / Reporter gpt-5.1 / **Forecaster TBD (후속 plan)** / **Optimizer TBD (후속 plan)** |
| 11 | postgres.md 정정 | `forecasts.trade` → `l6_main`, `today_qty` → JSONB by_unit, `pipeline_runs.atomized_count` 추가. **`init.sql` + 마이그레이션 + `postgres.md` 3곳 동기화 의무**. |
| 12 | PGClient 확장 | 신규 메서드 `fetch_l6_plan_mh_map(company, l6_list)`, `update_run_atomized_count(run_id, count)` 추가 (B1 해결). Task 0.5 로 분리. |
| 13 | Atomizer integration test 의 pipeline_runs 사전 INSERT | test fixture 가 `INSERT INTO pipeline_runs ...` 사전 실행 (B2 해결). |

핵심 변경 = `mapping-layer.md` 의 매핑 grain `(WA, L6)` 을 다운스트림 grain `(company, l6_main)` 로 일관화. v1 골든 문서 (`planning/simulation/생산성_시뮬레이션_결과.md`) 의 l7_sub 단위 매핑은 본 spec 에서 대체 (v2 mapping-layer 결정 그대로 유지).

---

## 1. 데이터 흐름 정합

```
1. Parser            → parsed: list[Activity]
                       (a.assigned_workers=0, worker_source="parsed")

2. Mapper            → mapped: list[Activity]
                       (a.wa, a.l6_main 결정)

3. Mapper 의 sub-step _prorate_mh()         ← §3
                     → mapped 각 a.assigned_workers = (a.company, a.l6_main) 단위 l6 인원
                       worker_source = "mh_prorated"

──── interrupt:hil_1 (requires_review=True 있을 때만, graph.py) ────

4. Atomizer ★        ← §4 (본 spec 의 즉시 구현 대상). LLM 없음, Chroma 적재만.
                       입력: mapped (분배 완료)
                       출력: atomized_ids = [doc_id, ...] + PG pipeline_runs.atomized_count

5. Forecaster        ← §6. (company, l6_main) grain N row 진단 + PG forecasts INSERT
                       LLM: TBD (후속 plan)

──── interrupt:hil_2 (risk_level ∈ {'주의','이상'} 있을 때만, graph.py) ────

6. Optimizer         ← §7. hil_2_selection 의 (company, l6) 만 + PG optimizer_advice INSERT
                       LLM: TBD (후속 plan)

7. Reporter          ← §5. l5_disc/l6_main group by + 위 결과 종합 → PG daily_reports INSERT
                       LLM: gpt-5.1

→ CPIAState.status = 'completed'
```

### 1.1 그래프 분기 결정 근거 (결정 #6)

PM 원안 `Reporter ‖ Forecaster` 의 `‖` 가 의미적으로 모호. 본 spec 결정:

- 의존성: Reporter / Forecaster 모두 `state["mapped"]` 만 입력 → 병렬 가능
- 그러나 **순차 (Forecaster → Reporter)** 채택:
  - Reporter 가 Forecaster 의 진단 결과를 보고서에 포함 가능 (의미 ↑)
  - LangGraph fan-out/fan-in 패턴 복잡도 회피 (PoC 단순)
  - 시간 비용 30~60s 추가 = 5 분 데모 목표 안 영향

### 1.2 실 데이터 시뮬 결과 (9/25 작업일보)

`/tmp/cpia_flow_sim.py` 실 호출 결과 (2026-05-16):

```
parsed.activities         = 1,193건
parsed.bp_summaries       = 383건

[BP사 별 그 날 총 인원 = 시트1 today_incr 합]
  세종텔레콤    24,095명   세보엠이씨   1,387명   창원기전    372명   남웅건설    88명   …

[BP사 별 시트4 행수 = 매핑 대상]
  남웅건설   48행 | units=m,m2,m3,ton
  세보엠이씨  30행 | units=ea,m,m2
```

→ §3 의 `_prorate_mh()` 가 위 88 / 1387 / 372 명을 각 BP사 매핑 l6 들에 분배. §4 의 Atomizer 가 결과 mapped 를 Chroma 적재.

---

## 2. Activity 스키마 정정 (`pipeline/state.py`)

본 spec 의 결정으로 **필드 추가/제거 X**. 의미 docstring 정정만.

### 2.1 정정 사항 표

| 필드 | 옵션 X 적용 후 의미 | 현재 mapper.py | 변경 |
|---|---|---|---|
| `wbs_activity_id: str \| None` | **PoC 항상 None** (1:N 단일 결정 불가). Phase 2 H-i-L 정정 시 채울 수 있음. | None | docstring |
| `l7_sub: str \| None` | 동일 — PoC 항상 None. | None | docstring |
| `l7_5_activity: str \| None` | 동일. | None | docstring |
| `sub_work_area: str \| None` | 동일. | None | docstring |
| `plan_total_qty: float \| None` | 동일 — 단일 wbs 결정 불가. Forecaster 는 PG 에서 (company, l6_main) candidate Σ 직접 조회. | None | docstring |
| `plan_mh: float \| None` | 동일. | None | docstring |
| `assigned_workers: float` | **(company, l6_main) 단위 단일값**. 같은 (company, l6_main) Activity 들이 모두 동일 reference. | 미충 | `_prorate_mh()` 가 채움 + docstring |
| `worker_source: Literal['parsed','mh_prorated','user_corrected']` | `mh_prorated` = "(company, l6_main) 단위 분배 적용 — BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)" | 미충 | `_prorate_mh()` 가 채움 + docstring |

### 2.2 state.py patch — docstring 정합 보강

```python
class Activity(TypedDict):
    # ── WBS 매핑 (Mapper 이후) ───────────────────────────────────────
    # PoC 단계: 아래 4 필드는 1:N 라 항상 None. Phase 2 H-i-L 정정 시 채울 수 있음.
    # Forecaster / Reporter 는 (company, l6_main) candidate 를 PG 에서 직접 조회.
    wbs_activity_id: str | None       # PoC: None — 1:N 단일 wbs 결정 불가
    l7_sub: str | None                # PoC: None — 동일
    l7_5_activity: str | None         # PoC: None — 동일
    sub_work_area: str | None         # PoC: None — 동일

    # Mapper 가 채움
    l5_disc: str                      # Parser 가 채움 (한글)
    l6_main: str | None               # Mapper LLM 결정
    wa: str | None                    # Mapper WA 결정 4단계
    mapping_conf: float | None        # LLM rerank confidence (0.0~1.0)
    mapping_source: str | None        # 'auto_bp_single'/'auto_l6_single'/'auto_sheet1_text'/'hil_required'
    requires_review: bool             # mapping_conf < 0.7 또는 mapping_source='hil_required'

    # ── 작업일보 원천 (Parser) ───────────────────────────────────────
    trade: str
    company: str
    unit: str
    today_qty: float                  # 9/25 89.5% None → 0.0 표시
    work_content: str
    conditions: list[str]

    # ── (company, l6_main) 단위 분배 결과 (_prorate_mh sub-step) ────
    # 같은 (company, l6_main) Activity 들 = 동일 reference.
    # 분배 공식: BP사 총 인원 × (그 l6 candidate Σplan_mh / 전체 매핑 l6 candidate Σplan_mh)
    assigned_workers: float           # (company, l6_main) 단위 단일값
    worker_source: Literal[           # 분배 상태 표시
        "parsed",                     #   = 작업일보 명시 그대로 (드문 케이스)
        "mh_prorated",                #   = _prorate_mh() 적용됨 (기본)
        "user_corrected",             #   = H-i-L 1 사용자 보정 (Phase 2)
    ]

    # ── Master List 조회값 (PoC: None) ───────────────────────────────
    plan_total_qty: float | None      # PoC: None (Forecaster 가 PG 에서 Σ 조회)
    plan_mh: float | None             # PoC: None (동일)
```

---

## 3. Mapper 확장 — `_prorate_mh()` sub-step

### 3.1 위치 + 호출 패턴

```python
# graph.py 의 mapper_node (Task 분해 §9.3 참조 — Task 5 에서 구현)
async def mapper_node(state: CPIAState) -> dict:
    # 1. 각 Activity 매핑 (LLM 호출)
    mapped: list[Activity] = []
    for activity in state["parsed"]:
        result = await map_activity(activity, parsed_report=state.parsed, cfg=cfg)
        mapped.append(result)

    # 2. _prorate_mh() — BP사 × l6 단위 batch 분배
    mapped = await _prorate_mh(mapped, parsed_report=state.parsed, pg=pg)

    return {"mapped": mapped, "current_node": "mapper"}
```

**Task 1 단계 (mapper_node 미존재):** `_prorate_mh()` 는 mapper.py 의 top-level async 함수로 노출. integration test 는 mapper_node 우회하고 `_prorate_mh()` 직접 호출.

### 3.2 `_prorate_mh()` 의사코드 (PGClient 신규 메서드 호출 + SQL batch 화)

```python
async def _prorate_mh(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    pg: PGClient,
) -> list[Activity]:
    """(company, l6_main) 단위 BP사 총 인원 분배 — 옵션 X 알고리즘.

    공식:
        bp_total_n      = Σ parsed_report.bp_summaries[company].today_incr_total
        l6_set          = mapped 의 company 별 매핑 결과 l6_main 집합
        l6_plan_mh[l6]  = pg.fetch_l6_plan_mh_map(company, list(l6_set))   ← batch 1 query
        sum_mh          = Σ l6_plan_mh.values()
        assigned[l6]    = bp_total_n × l6_plan_mh[l6] / sum_mh   (sum_mh > 0)
                        = bp_total_n / len(l6_set)               (sum_mh = 0 fallback)

    각 mapped Activity 에 (company, l6_main) lookup 으로 동일 assigned_workers 반영.
    """
    # 1. BP사 별 그 날 총 인원
    bp_total: dict[str, int] = defaultdict(int)
    for s in parsed_report["bp_summaries"]:
        bp_total[s["company"]] += s["today_incr_total"]

    # 2. BP사 별 매핑된 l6 set
    bp_l6: dict[str, set[str]] = defaultdict(set)
    for a in mapped:
        if a["l6_main"] is not None:
            bp_l6[a["company"]].add(a["l6_main"])

    # 3. (company, l6) lookup 테이블 구축 — BP사당 1 PG 쿼리 (batch)
    workers_lookup: dict[tuple[str, str], float] = {}
    for company, l6_set in bp_l6.items():
        total_n = bp_total.get(company, 0)
        if total_n == 0 or not l6_set:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = 0.0
            continue

        # PGClient 신규 메서드 — Task 0.5 에서 추가
        l6_mh: dict[str, int] = await pg.fetch_l6_plan_mh_map(company, list(l6_set))

        sum_mh = sum(l6_mh.values())
        if sum_mh == 0:
            # plan_mh 모두 0 → 균등 분배
            for l6 in l6_set:
                workers_lookup[(company, l6)] = total_n / len(l6_set)
        else:
            for l6, mh in l6_mh.items():
                workers_lookup[(company, l6)] = total_n * mh / sum_mh

    # 4. mapped Activity 에 반영
    out: list[Activity] = []
    for a in mapped:
        if a["l6_main"] is not None:
            key = (a["company"], a["l6_main"])
            a = {
                **a,
                "assigned_workers": workers_lookup.get(key, 0.0),
                "worker_source": "mh_prorated",
            }
        out.append(a)
    return out
```

**`pg.fetch_l6_plan_mh_map()` 의 실 SQL** (Task 0.5 에서 PGClient 에 추가):

```python
async def fetch_l6_plan_mh_map(self, company: str, l6_list: list[str]) -> dict[str, int]:
    """단일 GROUP BY 쿼리로 (company) 의 여러 l6 plan_mh 합을 한 번에 조회."""
    rows = await self.conn.fetch(
        """
        SELECT l6_main, sum(plan_mh_rev2) AS s
        FROM activity_master
        WHERE company = $1 AND l6_main = ANY($2::text[])
        GROUP BY l6_main
        """,
        company, l6_list,
    )
    return {r["l6_main"]: int(r["s"] or 0) for r in rows}
```

→ N+1 쿼리 회피. 남웅(1 쿼리) + 세보(1 쿼리) + 창원(1 쿼리) = **총 3 쿼리**.

### 3.3 엣지 케이스

| 케이스 | 처리 |
|---|---|
| `bp_total = 0` | `assigned_workers = 0.0` |
| 매핑된 l6 없음 (전부 None / hil_required) | 그 BP사 skip (assigned_workers 변경 없음) |
| PG `Σplan_mh = 0` | 균등 분배 (BP사 총 인원 / len(l6_set)) |
| `requires_review=True` Activity | 분배 적용 (H-i-L 1 정정 후 graph 재개 시 `_prorate_mh` 재호출) |
| BP사가 Master List 미등록 | bp_l6 dict 에서 누락 → 분배 skip |

### 3.4 실 데이터 분배 결과 (9/25 + golden 79 매핑)

**출처: `/tmp/cpia_flow_sim.py` 실 호출 (Parser + PG `activity_master` 1059 row 조회), 2026-05-16:**

```
[남웅건설] 88명 → 1 l6
  철근콘크리트공사            mh=1,676,807 (100%)  → 88.0명

[세보엠이씨] 1,387명 → 13 l6
  기계소화설비               mh=  744,043 (30.4%) → 421.7명
  일반공조설비공사            mh=  708,154 (28.9%) → 401.4명
  냉동기설비공사              mh=  268,341 (11.0%) → 152.1명
  CABINET배기설비공사        mh=  125,807 ( 5.1%) →  71.3명
  VOC설비공사               mh=  114,287 ( 4.7%) →  64.8명
  ... (+ 8 l6)

[창원기전] 372명 → 3 l6
  전력간선공사               mh=  276,519 (58.3%) → 216.9명
  전등설비공사               mh=  116,413 (24.5%) →  91.3명
  전기소화설비               mh=   81,382 (17.2%) →  63.8명
```

### 3.5 테스트 plan (TDD)

```python
# unit (실 PG 호출 X — mock pg)
test_prorate_single_l6              # 남웅 88명, l6=1 → 88.0
test_prorate_zero_total             # bp_total=0 → 0.0
test_prorate_zero_plan_mh           # Σmh=0 → 균등
test_prorate_unmapped_skip          # l6_main=None → assigned_workers 미변경

# integration (@pytest.mark.slow — 실 PG `activity_master` 호출)
@pytest.mark.slow
test_prorate_multi_l6_plan_mh      # 세보 1387명, l6=13 → §3.4 결과 byte-level 일치

@pytest.mark.slow
test_prorate_golden_79              # 9/25 + golden 매핑 → 3 BP사 분배 결과 = §3.4 표 전체
```

---

## 4. Atomizer 구현 spec (`pipeline/agents/atomizer.py`)

본 spec 의 즉시 구현 대상.

### 4.1 Chroma `daily_activities` 적재 grain

```python
# 1 mapped Activity = 1 Chroma doc (작업일보 행 단위)
chroma.daily_activities.upsert(
    ids=[doc_id],                                       # §4.2
    embeddings=[embed(activity["work_content"])],       # Azure text-embedding-3-small 1536d
    documents=[activity["work_content"]],
    metadatas=[{
        # 시간/식별
        "date":             parsed.report_date,         # "2025-09-25"
        "run_id":           state.run_id,
        # BP사 + 매핑 결과 (Forecaster RAG where 절)
        "company":          activity["company"],
        "l5_disc":          activity["l5_disc"],
        "l6_main":          activity["l6_main"],
        "wa":               activity["wa"] or "",
        # 단위 + 실적 + 인원
        "unit":             activity["unit"],
        "today_qty":        float(activity["today_qty"]),
        "assigned_workers": float(activity["assigned_workers"]),
        "worker_source":    activity["worker_source"],  # Forecaster: user_corrected 가중치
        "mapping_conf":     float(activity["mapping_conf"] or 0.0),  # Forecaster RAG 신뢰도
        # 부수
        "conditions":       ",".join(activity["conditions"]),   # list → CSV
    }],
)
```

**메타 결정 사항:**
- Chroma scalar 한정 → `conditions: list[str]` → CSV string 직렬화
- `wa=None` 일 때 → 빈 string (Chroma null 허용 X)
- `mapping_conf` / `worker_source` 메타 포함 — `mapping-layer.md §6.1` 원안에 없음. Forecaster RAG 시 신뢰도 가중치 (`mapping_conf < 0.7` 후보 제외 또는 가중치 낮춤) + 보정 우대 (`worker_source = 'user_corrected'`) 에 사용. Phase 1 데모에서는 단순 보존, Phase 2 에서 Forecaster 가 활용.

### 4.2 doc id 정책 (결정성 + dedup)

```python
def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str:
    raw = f"{date}|{company}|{l6_main}|{work_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

→ 16자 hex (예: `73ff80435e312c41`). 충돌 확률 무시.

**정책:**
- 같은 작업일보 재실행 → 같은 doc_id → Chroma upsert
- H-i-L 1 정정으로 wa/l6_main 변경 → 새 doc_id (l6 가 hash 입력) → 이전 id 잔류 (orphan)
  - **PoC 회피책**: Forecaster RAG 검색 시 `where {date: today}` filter 로 stale row 가림 (Phase 1 데모 무영향)
  - Phase 2 에서 orphan cleanup job 추가
- work_content 변경 케이스 거의 없음 (H-i-L 1 정정은 wa/l6 만)

### 4.3 requires_review=True Activity 처리

**옵션 분석:**

```
옵션 4.3.a (신중): requires_review=True → Atomizer skip (적재 안 함)
  - 장점: 정정 안 된 mapping 이 Chroma 적재 안 됨 → RAG 신뢰도 ↑
  - 단점: H-i-L 1 UI 미완성 시 Atomizer 가 진행 안 됨 (PoC 마감 위협)

옵션 4.3.b (PoC 채택): requires_review=True → 무시하고 전부 적재
  - 장점: H-i-L 1 미완성 시도 Atomizer 진행. mapping_conf 메타 보존 → Forecaster 가 가중치 활용 가능
  - 단점: 정정 안 된 mapping 이 RAG 풀에 포함 (PoC 단계 무시)
```

**결정: 4.3.b 채택**

이유:
1. H-i-L 1 UI (B_Track) 미완성 시 Atomizer 진행 보장
2. interrupt(hil_1) 발동 자체는 graph.py 책임 → Atomizer 진입 시점에는 정정 완료 또는 PoC skip 둘 다 동일 동작
3. Phase 2 에서 4.3.a 로 강화 가능

### 4.4 atomized_ids 영속화

```
state["atomized_ids"]: list[str] = [doc_id, ...]
  → LangGraph PostgresSaver 가 checkpoint 자동 영속

PG pipeline_runs 컬럼 추가 (운영 모니터링용):
  ALTER TABLE pipeline_runs ADD COLUMN atomized_count INTEGER DEFAULT 0;
  → Atomizer 종료 시 pg.update_run_atomized_count(run_id, count) (PGClient 신규 메서드)
```

**`pipeline_runs` row INSERT 책임 (결정 #13):**

- `graph.py` + FastAPI `api.py` 빈 파일 → `pipeline_runs` INSERT 코드 경로 없음
- 본 spec 의 Task 1~4 단계에서 graph.py 미구현 — Atomizer 의 `UPDATE` 가 silent no-op 위험
- **integration test fixture 가 사전 INSERT 명시**:
  ```python
  @pytest.fixture
  async def run_row(pg):
      run_id = uuid.uuid4()
      await pg.execute(
          "INSERT INTO pipeline_runs (run_id, site_id, date, status) VALUES ($1, 'M15X_PH3_IBL', '2025-09-25', 'running')",
          run_id,
      )
      yield run_id
      await pg.execute("DELETE FROM pipeline_runs WHERE run_id=$1", run_id)
  ```
- Phase 2 graph.py spec 단계에서 FastAPI `/run` 이 자동 INSERT 보장

### 4.5 Atomizer 함수 시그니처 (의사코드)

```python
# pipeline/agents/atomizer.py
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Any, Optional

from openai import AzureOpenAI
from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, ParsedDailyReport


@dataclass
class AtomizerConfig:
    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    embedding_model: str              # "text-embedding-3-small-ai-board-test"
    embedding_dim: int = 1536         # Azure text-embedding-3-small 고정 — Chroma 컬렉션 cold start 시 차원 고정
    postgres_url: str = ""
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    chroma_ssl: bool = False
    batch_size: int = 16              # Azure embedding batch
    azure_timeout: float = 30.0       # 단일 batch timeout (Azure SDK)
    azure_max_retries: int = 3        # Azure SDK 내장 retry


def _make_doc_id(date: str, company: str, l6_main: str, work_content: str) -> str:
    raw = f"{date}|{company}|{l6_main}|{work_content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_metadata(a: Activity, date: str, run_id: str) -> dict[str, Any]:
    return {
        "date": date, "run_id": run_id,
        "company": a["company"],
        "l5_disc": a["l5_disc"],
        "l6_main": a["l6_main"] or "",
        "wa": a["wa"] or "",
        "unit": a["unit"],
        "today_qty": float(a["today_qty"]),
        "assigned_workers": float(a["assigned_workers"]),
        "worker_source": a["worker_source"],
        "mapping_conf": float(a["mapping_conf"] or 0.0),
        "conditions": ",".join(a["conditions"]),
    }


async def atomize(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    run_id: str,
    cfg: AtomizerConfig,
) -> list[str]:
    """mapped → Chroma daily_activities 적재. atomized_ids 반환.

    1. l6_main=None Activity 는 skip.
    2. doc_id = sha256(date|company|l6_main|work_content)[:16] 결정성 upsert.
    3. embedding = AzureOpenAI text-embedding-3-small (batch_size=16, timeout, retry).
    4. Chroma .upsert(ids, embeddings, documents, metadatas).
    5. PG pg.update_run_atomized_count(run_id, len(ids)).
    """
    valid = [a for a in mapped if a["l6_main"] is not None]
    if not valid:
        return []

    date = parsed_report["report_date"]
    azure = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
        timeout=cfg.azure_timeout,
        max_retries=cfg.azure_max_retries,
    )

    ids = [_make_doc_id(date, a["company"], a["l6_main"], a["work_content"]) for a in valid]
    documents = [a["work_content"] for a in valid]
    metadatas = [_build_metadata(a, date, run_id) for a in valid]

    # embedding batch
    embeddings: list[list[float]] = []
    for i in range(0, len(documents), cfg.batch_size):
        chunk = documents[i : i + cfg.batch_size]
        resp = azure.embeddings.create(model=cfg.embedding_model, input=chunk)
        embeddings.extend([d.embedding for d in resp.data])

    # Chroma upsert (chromadb 0.5+ Collection.upsert 지원 확인)
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    coll.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    # PG pipeline_runs UPDATE (PGClient 신규 메서드)
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        await pg.update_run_atomized_count(run_id, len(ids))
    finally:
        await pg.close()

    return ids
```

**`pg.update_run_atomized_count()` 의 실 SQL** (Task 0.5 에서 PGClient 에 추가):

```python
async def update_run_atomized_count(self, run_id: str, count: int) -> None:
    """pipeline_runs row 가 사전 INSERT 되어 있어야 함 (Atomizer 책임 X).
    
    silent no-op 방지를 위해 affected row 검증 — 0 row 면 RuntimeError.
    """
    result = await self.conn.execute(
        "UPDATE pipeline_runs SET atomized_count = $1, current_node = 'atomizer' "
        "WHERE run_id = $2",
        count, run_id,
    )
    # asyncpg result: "UPDATE N" — 0 면 row 미존재
    if result.endswith(" 0"):
        raise RuntimeError(f"pipeline_runs(run_id={run_id}) 미존재 — fixture 설정 확인")
```

### 4.6 테스트 plan (TDD)

```python
# unit (실 호출 X)
test_make_doc_id_determinism        # 같은 입력 → 같은 id (byte-level)
test_make_doc_id_changes            # 다른 work_content → 다른 id
test_build_metadata_scalar_only     # 모든 키 = scalar (Chroma 호환)
test_build_metadata_conditions_csv  # list[str] → CSV string
test_atomize_skip_unmapped          # l6_main=None → skip
test_atomize_empty                  # valid=[] → return []

# integration (@pytest.mark.slow — 실 Chroma + 실 Azure + 실 PG)
@pytest.mark.slow
test_atomize_namwong_48             # 9/25 남웅 48 → Chroma 48 row + 모두 assigned_workers=88

@pytest.mark.slow
test_atomize_upsert_idempotent      # 같은 (date, company, l6, work) 2회 호출 → Chroma row 수 같음

@pytest.mark.slow
test_atomize_pg_count               # fixture 가 pipeline_runs INSERT → atomized_count UPDATE 검증

@pytest.mark.slow
test_atomize_missing_run_raises     # fixture 없이 호출 → RuntimeError ("pipeline_runs 미존재")
```

### 4.7 §1 시뮬 Atomizer 적재 메타 1 샘플 (남웅 R102) — ✓ Verified

**실 호출 검증 (`/tmp/cpia_flow_sim.py`, 2026-05-16):**

```
doc_id    = '73ff80435e312c41'                         # ✓ sha256("2025-09-25|남웅건설|철근콘크리트공사|기초 거푸집 설치")[:16]
document  = '기초 거푸집 설치'
embedding = embed('기초 거푸집 설치')                   # text-embedding-3-small 1536d
metadata  = {
    "date":             "2025-09-25",
    "run_id":           "<run_uuid>",
    "company":          "남웅건설",
    "l5_disc":          "건축",
    "l6_main":          "철근콘크리트공사",
    "wa":               "CUB",
    "unit":             "m2",
    "today_qty":        0.0,
    "assigned_workers": 88.0,                          # ✓ l6 단위 = 88명 그대로 (단일 l6)
    "worker_source":    "mh_prorated",
    "mapping_conf":     0.82,
    "conditions":       ""
}
```

---

## 5. Reporter 데이터 계약 (구현 spec 차후)

**입력**: `state["mapped"]` + `state["forecast"]` + `state["optimizer_advice"]`

**출력**: `state["report_md"]: str` + PG `daily_reports (report_md, summary JSONB)`

**LLM**: gpt-5.1 (Azure)

**grain**: `l5_disc` / `l6_main` group by

**summary JSONB 구조 (안)**:
```json
{
  "total_workers": 30000,
  "by_l5_disc": {"건축": {"workers": 88, "rows": 48}, "설비": {"workers": 1387, "rows": 30, "l6_count": 13}, ...},
  "by_l6_main": [{"company": "남웅건설", "l6": "철근콘크리트공사", "workers": 88,
                  "today_qty_by_unit": {"m": 0, "m2": 0, "m3": 0, "ton": 0}}, ...],
  "forecast_risk_count": {"정상": 12, "주의": 3, "이상": 2}
}
```

**미해결 사안 (차후 brainstorming)**:
- MD 섹션 구조 (현장 개요 → 공종별 → 진단 → 권고)
- LLM prompt — Forecaster/Optimizer 결과 자연어화
- 빈 forecast/optimizer 케이스 fallback

---

## 6. Forecaster 데이터 계약 (구현 spec 차후)

**입력**:
- `state["mapped"]: list[Activity]`
- Chroma `daily_activities` — RAG 검색 `where (company, l6_main)`. **Phase 2 에서 `mapping_conf` 가중치 + `worker_source = 'user_corrected'` 우대** (§4.1 메타 활용).
- PG `activity_master` — Plan 비교

**출력**: `state["forecast"]: list[dict]` (N row) + PG `forecasts` (§8 정정 후 적재)

**LLM**: **TBD — 후속 plan** (CLAUDE.md 갱신 사항 반영)

**grain**: **(company, l6_main)**

**진단 row 1개 구조 (예: 남웅 철콘)**:
```python
{
  "company":                "남웅건설",
  "l6_main":                "철근콘크리트공사",
  # 그 (company, l6_main) 단위 집계 — Σ Activity unit별 today_qty
  "today_qty_by_unit":      {"m": 0, "m2": 0, "m3": 0, "ton": 0},  # 48 Activity 합산
  "today_assigned_workers": 88.0,
  # Plan (PG candidate Σ — fetch_l6_plan_total_qty_by_unit_map() 또는 동일 패턴)
  "plan_total_qty_by_unit": {...},
  "plan_mh_sum":            1676807,
  # RAG (Chroma daily_activities 검색)
  "rag_n_similar":          5,
  "similar_cases":          [...],
  # LLM 진단 (모델 TBD)
  "assessment":             "정상" | "주의" | "이상",
  "reasoning":              "...",
  "expected_completion":    "2026-06-12",
  "risk_level":             "정상" | "주의" | "이상",
}
```

**미해결 사안 (차후 brainstorming)**:
- LLM 모델 선택 (Anthropic Opus 4.7 / Azure gpt-5-mini reasoning / 기타)
- Plan 비교 metric (진척률 vs 단위당 생산성, unit 별 적용 방식)
- RAG 0건 cold start 처리 (synthetic history 의존)
- LLM prompt 디자인 (golden 케이스 예시 주입)
- assessment 임계값 (정상/주의/이상 경계)
- Chroma metadata `mapping_conf` / `worker_source` 활용 정책

---

## 7. Optimizer 데이터 계약 (구현 spec 차후)

**입력**:
- `state["forecast"]`
- `state["hil_2_selection"]: list[str]` — PM 이 선택한 (company, l6_main) 키 리스트
- Chroma `daily_activities` 과거 회복 패턴 검색

**출력**: `state["optimizer_advice"]: list[dict]` + PG `optimizer_advice` (§8 정정 후)

**LLM**: **TBD — 후속 plan**

**grain**: hil_2_selection 항목 단위

**조언 row 1개**:
```python
{
  "company":          "남웅건설",
  "l6_main":          "철근콘크리트공사",
  "diagnosis":        "장비 대기로 인한 저하 추정",
  "recovery_pattern": [{"case_date": "...", "recovered_in_days": 3, "pattern": "..."}, ...],
  "recommendations":  [{"rank": 1, "text": "..."}, ...],
}
```

**미해결 사안 (차후 brainstorming)**:
- LLM 모델 선택
- "회복 패턴" 정의 (Chroma 검색 where + n_similar)
- recommendations actionability
- hil_2_selection=[] 시 Optimizer skip → status='completed'
- **v1 골든 §8 "거푸집 → 철근 재배치" 시나리오 — 옵션 X 채택으로 l7 단위 재배치 불가**. 데모 시나리오 조정은 Phase 1 보류 → §9.1 위임 ("A + B 트랙 공동 결정")

---

## 8. postgres.md 정정 사항

본 spec 의 결정에 따른 **3곳 동기화 의무** (결정 #11):
1. `infra/postgres/init.sql` (cold start)
2. `infra/postgres/migrations/2026-05-16_downstream_agents.sql` (기존 환경 마이그)
3. `docs/schema/postgres.md` (스키마 문서)

### 8.1 `pipeline_runs.atomized_count` 컬럼 추가

```sql
ALTER TABLE pipeline_runs ADD COLUMN atomized_count INTEGER DEFAULT 0;
```

### 8.2 `forecasts` 컬럼 정정 — (company, l6_main) grain

**현재 (init.sql + postgres.md §6)**: `trade TEXT NOT NULL` + 단일 `today_qty NUMERIC` + `plan_unit_productivity NUMERIC`.

**정정 후**:

```sql
-- DROP 현재 (PoC 단계 빈 테이블 — 운영 데이터 없음)
DROP TABLE IF EXISTS forecasts;

-- CREATE 정정
CREATE TABLE forecasts (
    id                       BIGSERIAL PRIMARY KEY,
    run_id                   UUID NOT NULL REFERENCES pipeline_runs(run_id),
    company                  TEXT NOT NULL,
    l6_main                  TEXT NOT NULL,                       -- (변경: trade → l6_main)

    -- 오늘 실측 (그 (company, l6) 단위 집계)
    today_qty_by_unit        JSONB,                               -- (변경: unit 별 dict — Σ Activity unit별 today_qty)
    today_assigned_workers   NUMERIC,

    -- Plan 기준 (PG candidate Σ)
    plan_total_qty_by_unit   JSONB,                               -- (변경)
    plan_mh_sum              NUMERIC,                             -- (변경)

    -- RAG 이력 기준
    rag_n_similar            INT,
    similar_cases            JSONB,

    -- 진단 (LLM TBD)
    assessment               TEXT,
    reasoning                TEXT,
    expected_completion      DATE,
    delay_days               INT,
    risk_level               TEXT,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';
```

**Note**: Forecaster 는 `l6_main != None` Activity 만 진단 row 생성 (Atomizer 가 skip 한 것과 일치). NOT NULL 제약 위반 케이스 없음.

### 8.3 `optimizer_advice.trade` → `l6_main`

```sql
ALTER TABLE optimizer_advice RENAME COLUMN trade TO l6_main;
```

### 8.4 마이그레이션 파일 + 동기화 3곳

```
infra/postgres/migrations/2026-05-16_downstream_agents.sql
  -- §8.1: pipeline_runs.atomized_count
  -- §8.2: forecasts DROP + CREATE 정의
  -- §8.3: optimizer_advice 컬럼 rename

infra/postgres/init.sql (cold start 동기화)
  -- pipeline_runs 정의에 atomized_count 추가
  -- forecasts 정의 위 §8.2 와 일치하게 정정
  -- optimizer_advice 정의 l6_main 으로 정정

docs/schema/postgres.md (문서 동기화)
  -- §3 pipeline_runs 표에 atomized_count 추가
  -- §6 forecasts 표 정정
  -- §7 optimizer_advice 표 정정
  -- §12 변경 이력에 본 spec 적용 한 줄
```

PoC 단계 (forecasts/optimizer_advice 빈 테이블) → DROP + CREATE 가장 단순. 운영 데이터 없으므로 마이그레이션 영향 0.

### 8.5 `mapping_corrections` 변경 없음

`mapping_corrections.trade` = `l5_disc` (예: '건축'). 매핑 키 (WA, L6) 와는 다른 grain. 본 spec 의 옵션 X 와 무관 (mapping_corrections 는 H-i-L 1 feedback, l5_disc level 기록 충분).

---

## 9. 미해결 사안 + Phase 1 vs Phase 2 분리

### 9.1 Phase 1 — 본 PoC (2026-06-05 마감)

| 사안 | 결정 시점 | 결정 주체 |
|---|---|---|
| Task 0 — Parser `bp_summaries.today_incr_total` 의미 사전 검증 (세보 1387명 spot-check) | Task 1 진입 전 | A 트랙 |
| Task 0.5 — PGClient 신규 메서드 (`fetch_l6_plan_mh_map`, `update_run_atomized_count`) | Task 1 진입 전 | A 트랙 |
| Task 1 — state.py docstring 정정 (§2.2) | 본 spec → plan → 구현 | A 트랙 |
| Task 2 — postgres 마이그레이션 + init.sql + postgres.md 3곳 동기화 (§8.4) | 본 spec → plan → 구현 | A 트랙 |
| Task 3 — `_prorate_mh()` + 테스트 (§3) | 본 spec → plan → 구현 | A 트랙 |
| Task 4 — `atomizer.py` + 테스트 (§4) | 본 spec → plan → 구현 | A 트랙 |
| Task 5 — `graph.py` mapper_node + atomizer_node (LangGraph 통합) | Task 4 완료 후 | A 트랙 |
| Reporter 구현 spec | Atomizer 완료 후 brainstorming | A 트랙 |
| Forecaster 구현 spec | Reporter 완료 후 brainstorming | A 트랙 |
| Optimizer 구현 spec | Forecaster 완료 후 brainstorming | A 트랙 |
| graph.py 통합 (LangGraph fan-in / interrupt 2개) | 4 에이전트 완료 후 별도 spec | A 트랙 |
| H-i-L 1 정정 → mapped 재계산 흐름 | graph.py spec 단계 | A 트랙 |
| Synthetic history 30일 (Chroma cold start) | Forecaster spec 단계 | A 트랙 |
| Reporter MD 섹션 구조 | Reporter spec 단계 | A 트랙 |
| Reporter prompt + summary JSONB 디자인 | Reporter spec 단계 | A 트랙 |
| Forecaster Plan vs RAG 가중치 | Forecaster spec 단계 | A 트랙 |
| Forecaster LLM 모델 + prompt | Forecaster spec 단계 | A 트랙 |
| risk_level 임계값 (정상/주의/이상) | Forecaster spec 단계 → GATE 3 (5/29) 조정 | A 트랙 |
| Optimizer LLM 모델 | Optimizer spec 단계 | A 트랙 |
| Optimizer "회복 패턴" 정의 | Optimizer spec 단계 | A 트랙 |
| Optimizer recommendations 구조 | Optimizer spec 단계 | A 트랙 |
| 데모 시나리오 — l7 재배치 시나리오 대체 | Optimizer spec 후 사용자 결정 | A + B 트랙 공동 |

### 9.2 Phase 2 — PoC 이후 (운영 진입)

| 사안 | 비고 |
|---|---|
| H-i-L 1 정정으로 wbs_activity_id / l7_sub 등 채울 가능성 | mapping_corrections 누적으로 패턴 학습 |
| Chroma orphan cleanup (work_content 변경 시 doc_id 변경) | cleanup job 추가. Phase 1 회피책: Forecaster RAG `where {date}` filter |
| Master List 갱신 시 activity_master upsert + plan_mh 변경 추적 | postgres.md §11 ④ |
| BP사가 Master 미등록 시 자동 cross-walk | mapping-layer.md §8 ⑥ |
| `requires_review=True` Atomizer skip (옵션 4.3.a) 로 강화 | H-i-L 1 UI 안정 후 |
| 시트1 today_incr_total 의미 검증 (운영 데이터) | Phase 1 Task 0 에서 1차 검증 후 |
| 직종 분배 (시트2 데이터 활성 시 v1 골든 §11 패턴 재도입) | 9/25 데이터는 시트2 기능공 row 0건 (남웅 시트2 = 공사관리자 2 row 만) |

### 9.3 본 spec 의 다음 단계

```
[즉시]
  1. spec 문서 저장: docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md  ✓ 완료
  2. spec 리뷰 루프 (coherence + feasibility reviewer)                                    ✓ 완료
  3. 사용자 spec 검토 게이트                                                              ← 현재
  4. writing-plans → docs/superpowers/specs/2026-05-16-cpia-downstream-agents-plan.md
     (Task 0:   bp_summaries 의미 검증
      Task 0.5: PGClient 신규 메서드 (fetch_l6_plan_mh_map, update_run_atomized_count)
      Task 1:   state.py docstring 정정 + 테스트
      Task 2:   postgres 마이그레이션 + init.sql + postgres.md 3곳 동기화
      Task 3:   _prorate_mh() + unit/integration 테스트
      Task 4:   atomizer.py + unit/integration 테스트 + fixture
      Task 5:   graph.py mapper_node + atomizer_node + 회귀)
  5. subagent-driven-development 로 Task 0~5 실행

[차후 — 별도 brainstorming 4 사이클]
  Reporter → Forecaster → Optimizer → graph.py 통합 (LangGraph)
```

---

## 10. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-16 | 초안 — 4 다운스트림 에이전트 데이터 계약 정합 (옵션 X (company, l6_main) grain) + Atomizer 구현 spec. 실 9/25 작업일보 + PG activity_master + golden 79 매핑 시뮬 검증. PM 원안 vs mapping-layer.md 모순 (forecasts.trade=l7_sub vs (WA, L6) 매핑) 정합화. v1 골든 (생산성_시뮬레이션_결과.md) 의 직종 분배 패턴은 시트2 기능공 row 0건 발견으로 대체. | A 트랙 |
| 2026-05-16 | 리뷰 정정 — coherence-reviewer + feasibility-reviewer 의 13 발견 사항 반영. 결정 #12~#13 추가 (PGClient 확장 / pipeline_runs fixture INSERT). §3.2 SQL batch 화 + 신규 메서드 호출. §8.4 3곳 동기화 의무 명시. §4.1 metadata 의도 보강. §4.3 옵션 4.3.a/b 정의. §4.5 timeout/retry/embedding_dim 추가. §4.7 doc_id ✓ Verified. §6/§7 미해결 사안 보강. §9.1 Task 분해 (Task 0/0.5 추가). | A 트랙 |
