# CPIA Exporter — graph 사전생성 통합 (Design Spec)

> Cycle: 2026-05-27 brainstorming (`superpowers:brainstorming`)
> Status: design 단계. Implementation plan 은 별 cycle (`writing-plans` 산출).
> 선행 cycle: `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md` (D-6 graph 밖 라우트 결정 → 본 cycle 이 그 결정을 retract 하고 graph 안으로 편입)
> 선행 commit: A_Track HEAD `0f4e3f7` — 백엔드 (`pipeline/agents/exporter.py` 301L + `pipeline/exporter_routes.py` 47L + 4 시트 template) + UI (`web/app/(app)/export/page.tsx` + ConsolidatedReportCard / ExportDailyList / SheetTable) 모두 완성. 본 cycle 은 그 위에 graph 사전생성 layer 추가.
> Branch: `A_Track`, git SHA: `0f4e3f7` 기준
> 다른 세션: deep-dive / data-contract / `view_builder.py` / `chroma_client.py` 등 working tree 변경 중 — 본 cycle 의 변경 영역 (graph.py / state.py / db.py / exporter.py 신 fn / exporter_routes.py / 신 PG migration / 테스트) 과 직접 충돌 0.

---

## 1. Context

### 1.1 현 시스템 상태 (선행 cycle 산출)

이전 cycle (`2026-05-19-cpia-collector-exporter-design.md`) 의 18 commit 으로 다음이 완성됨:

- **백엔드**:
  - `pipeline/agents/exporter.py:34` `fetch_sheet_data` — 한 site × date 의 모든 run jsonb 합집합 (N업체 통합)
  - `pipeline/agents/exporter.py:290` `render_xlsx` — openpyxl 4 시트 (`1.출력인원 현황` / `2.직종별 인원현황` / `3.장비현황` / `4.물량`) + COL dict 4종
  - `pipeline/agents/exporter_templates/consolidated_template.xlsx` — 시연자 디자인 보존 binary
  - `pipeline/exporter_routes.py:16` `GET /export/run?site_id&date` — FastAPI 라우트, Content-Disposition UTF-8 raw_headers 패치
- **UI**:
  - `web/app/(app)/export/page.tsx` — 좌측 일자 list + 우측 4 시트 탭 화면
  - `web/app/components/export/ConsolidatedReportCard.tsx` — 4 시트 탭 + Export 다운로드 버튼
- **미시행 (선행 cycle 의 backlog #R-N2)**: `ConsolidatedReportCard.handleExport` 가 여전히 정적 `/sample/cpia-consolidated-report.xlsx` fallback. FastAPI `/export/run` 호출 swap 안 됨.
- **선행 Medium 이슈 #N21** (deep-dive #N21, Medium 등급): `/export/run` 매 요청마다 PGClient 새로 만듦 (`os.environ["POSTGRES_URL"]`) — lifespan pool 미재사용.

### 1.2 선행 cycle 의 D-6 / D-9 결정 — 본 cycle 의 변경 의도

- **D-6 (선행)**: Exporter = graph 밖 별 FastAPI 라우트. 사유 = on-demand 다운로드 / read-only / graph cycle 영향 격리.
- **D-9 (선행)**: `pipeline/agents/reporter.py` 는 그대로 유지 (MD 종합보고서, daily_reports.report_md). `exporter.py` 는 신규 추가, rename 아님. CLAUDE.md (2026-05-18) 의 "rename" 표현은 reports 페이지 간과한 표기.

본 cycle (2026-05-27) 의 의도:
- **D-6 retract**: Exporter 를 LangGraph 노드로 편입. CLAUDE.md 원안 (`Atomizer → Exporter ‖ Forecaster`) 토폴로지 회귀.
- **D-9 유지**: `reporter.py` 그대로. exporter 는 별 노드 / 별 PATH.
- **선행 #R-N2 해소**: B_Track 의 `handleExport` swap 본 cycle 에 포함.
- **선행 #N21 부분 해소**: `/export/run` 핸들러의 `request.app.state.pg` 사용 (E-2 변경의 부수 효과) — **HTTP path 만** 해소. exporter 그래프 노드 자체는 다른 graph 노드 (`collector_node` / `mapper_node` 등) 와 동일하게 `state["postgres_url"]` 로 PGClient 매 cycle 생성 (graph 노드는 FastAPI Request 못 받음). 노드측 pool 공유는 별 cycle 의 graph-wide refactor 사안.

### 1.3 사용자 의도 (본 brainstorming)

"여러 업체에서 작업일보를 메일로 보내면 collector가 모으고 parser와 mapper를 통해 파싱해서 스키마별로 매칭하면 export 쪽에서 보이거든 그러면 이제 이걸 다운 받으면 하나의 통합 작업일보로 받을수 있는거야"

→ 시연 임팩트 = "AI Agent 가 자동으로 통합 작업일보를 만들어 둠". 사용자가 (B-1) graph 사전생성을 선택한 동기.

PoC 데모 마감 = 2026-06-05 (목), D-9.

---

## 2. Goal + Non-goal

**Goal (본 cycle)**:
- graph cycle 마다 통합 xlsx 사전생성 → `consolidated_reports` PG BYTEA 테이블 UPSERT
- `Atomizer → Exporter ‖ Forecaster` fan-out 토폴로지 (CLAUDE.md 원안)
- `/export/run` 의 hybrid 동작: cache hit → 즉시 응답, miss → live render fallback (E-2)
- 선행 cycle 의 #N21 (Medium, lifespan PG pool 미재사용) 의 **HTTP path 만** 자연 해소 — `request.app.state.pg`. 노드측은 선행 collector_node 패턴 유지
- 선행 cycle 의 #R-N2 (B_Track UI swap) 본 cycle 에 포함
- 시연 임팩트: tasks 페이지의 Agent stage progress 에 Exporter stage 노출
- 단위 / 통합 테스트 (LLM bypass, 결정론적)

**Non-goal (후속 cycle)**:
- `reporter.py` 폐기 / rename — D-9 그대로 유지
- PG advisory lock 으로 race 직렬화 — eventual consistency (EC) 정책으로 PoC 충분
- xlsx 캐싱 / pre-render — graph 사전생성이 사실상 캐싱, 별도 작업 불필요
- S3-like blob storage — overkill PoC
- Multi-site 동적 site_id 매핑 — 선행 cycle D-11 그대로 (`COLLECTOR_DEFAULT_SITE_ID` env)
- 4 시트 산식 회귀 테스트 (선행 cycle #2 backlog) — 본 cycle 범위 밖
- reporter→exporter rename (선행 #N23 / #R-N1) — D-9 와 충돌, 후속 cycle

---

## 3. Decisions (사용자 confirm — 본 brainstorming)

| # | 결정 | 선택 | 사유 |
|---|---|---|---|
| **D-1** | xlsx 생성 위치 | **graph 노드 안** (선행 cycle D-6 retract) | CLAUDE.md 원안 회귀. 시연 임팩트 "AI Agent 가 자동으로 통합 빌드 완료" 의 가시화. |
| **D-2** | 생성 트리거 | **매 graph cycle 안에서 1번 (T-A)** | 매 첨부 도착 시 누적 합집합 재생성. last write wins. debounce / cron 은 시연 라이브 흐름 부적합. |
| **D-3** | graph 노드 위치 | **Atomizer 와 병렬 fan-out (N-1)** | CLAUDE.md 원안 `Atomizer → Exporter ‖ Forecaster` 토폴로지. |
| **D-4** | 저장소 | **PG BYTEA — `consolidated_reports` 신 테이블 (S-1)** | atomic UPSERT 자연, AWS 마이그 자동 (`pg_dump` 그대로), 정리 단순. ~330MB/년 누적 — PG 부담 작음. |
| **D-5** | `/export/run` 동작 | **(E-2) hybrid — hit 우선, miss 시 live render fallback** | 시연 안전. graph 가 어떤 이유로 exporter 노드 실패해도 UI 다운로드 보장. miss 시 UPSERT 안 함 — 다음 cycle 이 만들어줌. |
| **D-6** | race 처리 | **Eventual Consistency (EC)** — advisory lock 없이 last write wins | PoC 단순. 시연 시 PM 이 메일 순차 보내면 race 발현 가능성 낮음. race 시 1~2 cycle stale 후 자동 회복. |
| **D-7** | State 폭증 방지 | **bytes 안 박음, meta 2 필드만** (`consolidated_xlsx_run_id`, `consolidated_xlsx_generated_at`) | PostgresSaver checkpoint 폭증 방지. bytes 는 `consolidated_reports` 테이블에만. |
| **D-8** | dual-END 정책 | **multi-end** — exporter 와 reporter 양 path 모두 END 도달 시 cycle 'completed' | LangGraph 1.2.0 은 native multi-end fault isolation 미지원 (issue #6170 open) — exporter 노드 안에서 `try/except Exception` swallow 패턴 (NoDataError 외 모든 예외 catch + log.exception + return {}) 으로 application level 격리. 그래서 exporter 가 LangGraph 입장에서 항상 'completed' (silent skip 포함) → reporter path 영향 0. |
| **D-9** | UI swap (#R-N2) | **본 cycle 에 포함** | (B-1) 선택의 결실 — UI 가 mock fallback 이면 사전생성 의의 없음. |
| **D-10** | Agent stage UI | **본 cycle 에 Exporter stage 추가** | 시연 임팩트. tasks 페이지의 Agent stage progress 에 Exporter 노출. |
| **D-11** | seed mock backfill | **본 cycle 에 포함** | 시연 site×date 가 cycle 0번 실행 시 cache miss → UI 가 NoData 400 보면 시연 risk. `scripts/seed_dummy_year.py` 에 `consolidated_reports` mock UPSERT 추가. |

---

## 4. Architecture

### 4.1 graph 토폴로지 변경

**Before** (선행 cycle 산출):
```
START → collector → parser → mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter → END
```

**After (D-3)**:
```
START → collector → parser → mapper → hil_1 → atomizer ─┬─→ forecaster → hil_2 → optimizer → reporter ─→ END
                                                        └─→ exporter ★ ──────────────────────────────→ END
```

- atomizer 끝나면 LangGraph 가 forecaster + exporter 두 path 를 동시 실행
- forecaster path: ~2분 (LLM 호출 많음)
- exporter path: ~수백 ms (PG SELECT 4 + openpyxl render + PG UPSERT)
- dual-END (D-8): 양 path END 도달 시 cycle 'completed'

### 4.2 컴포넌트 인벤토리 (변경 영역)

| 파일 | 종류 | 변경 라인 | 책임 |
|---|---|---|---|
| `infra/postgres/migrations/2026-05-27_consolidated_reports.sql` | 신규 | ~30 | PG 테이블 + 2 index + FK + GENERATED column |
| `pipeline/state.py` | 변경 | +2 | CPIAState 에 `consolidated_xlsx_run_id`, `consolidated_xlsx_generated_at` 추가 |
| `pipeline/db.py` | 변경 | +~40 | `upsert_consolidated_report` + `fetch_consolidated_report` 2 helper append |
| `pipeline/agents/exporter.py` | 변경 | +~40 | `consolidated_xlsx_node` async fn append. 기존 `fetch_sheet_data` / `render_xlsx` / `_fill_*` 변경 0 |
| `pipeline/graph.py` | 변경 | +4 | import 1 + add_node 1 + add_edge 2 |
| `pipeline/exporter_routes.py` | 변경 | ~30 | (E-2) hybrid + `request.app.state.pg` + `_build_xlsx_response` helper 분리 |
| `pipeline/api.py` | 변경 | +1 (lifespan `app.state.pg` 보장 확인) | lifespan 안에서 PGClient pool 을 `app.state.pg` 로 보관 |
| `scripts/seed_dummy_year.py` | 변경 | +~30 | `consolidated_reports` mock UPSERT 함수 추가, 시연 site×date 보장 |
| `pipeline/api.py:/api/agents/status` 핸들러 | 변경 | +~5 | `_AGENTS_META` 에 Exporter stage 추가 (D-10) |
| `web/lib/transforms.ts` | 변경 | +~5 | Agent stage mapping 에 Exporter 추가 (D-10) |
| `web/app/components/export/ConsolidatedReportCard.tsx` | 변경 | ~10 | `handleExport` swap: 정적 fallback → `/export/run` 호출 (D-9 / 선행 #R-N2) |
| `web/.env.local.example` | 변경 | +1 | `NEXT_PUBLIC_FASTAPI_BASE` 추가 |

**총 변경 라인 ≈ 200**. 기존 함수 변경 0 (`fetch_sheet_data` / `render_xlsx` / `_fill_*` 모두 그대로 재사용).

### 4.3 신규 / 변경 / 회귀 테스트

| 파일 | 종류 | 검증 |
|---|---|---|
| `pipeline/tests/test_db_consolidated_reports.py` | 신규 단위 | upsert (INSERT + UPDATE 양 path) + fetch (hit + miss) + FK 정합 |
| `pipeline/tests/test_exporter_node.py` | 신규 단위 | `consolidated_xlsx_node` — fetch_sheet_data mock + render mock + upsert assert + NoDataError skip path |
| `pipeline/tests/test_exporter_endpoint.py` | 변경 | (E-2) hit path + miss path 양 assertion. `request.app.state.pg` 사용 검증 |
| `pipeline/tests/test_graph_dual_end.py` | 신규 통합 | dual-END topology — 양 path 모두 END 도달 시 cycle 'completed', 한 path 실패 시 다른 path 동작 |

---

## 5. Data flow + 동시성

### 5.1 정상 path 시퀀스 (1 첨부)

```
T0     PM 메일 도착 (첨부 1 = 업체 A 작업일보)
T0+1s  idle_worker IDLE EXISTS → fetch UNSEEN → save → graph.ainvoke(thread_id=run_id)
T0+1s  collector_node (filename 분해 → state.bp_name / state.date / state.project)
T0+3s  parser_node (parser_reports A INSERT + parser_activities A INSERT)
T0+5s  mapper_node → hil_1 (AUTO_BYPASS) → atomizer (Chroma + mapped_history)
T0+15s atomizer END → fan-out:
         ┌── forecaster (LLM RAG + asyncio.gather + Semaphore 4×, ~2min)
         └── exporter_node ★:
              1) fetch_sheet_data(pg, state.site_id, state.date)
                 → 자기 run + 이전 run 합집합 (parser_reports JOIN pipeline_runs, 4 SELECT)
              2) render_xlsx(SheetData, ...) → bytes (~150KB)
              3) upsert_consolidated_reports(pg, site, date, bytes, run_id)
                 → PG ON CONFLICT (site_id, report_date) DO UPDATE (atomic)
              4) return {"consolidated_xlsx_run_id": run_id,
                         "consolidated_xlsx_generated_at": NOW().isoformat()+"Z"}
              → END (exporter path)
T0+2min forecaster → hil_2 (AUTO_BYPASS) → optimizer → reporter → END (reporter path)
T0+2min reporter_node 의 update_run_status('completed') 호출로 cycle 종료 마크
```

### 5.2 N 첨부 동시 도착 — race + EC

```
PM 메일 1 통에 첨부 3 (업체 A/B/C) 동시 도착:
  idle_worker → 3 ainvoke fire-and-forget (semaphore CPIA_COLLECTOR_CONCURRENCY=2)

Cycle A ─┬─ parser INSERT(A) ─ atomizer ─ exporter_node fetch+render+UPSERT ─┐
Cycle B ─┴─ parser INSERT(B) ─ atomizer ─ exporter_node fetch+render+UPSERT ┐│
                                                                            ▼▼
                                          consolidated_reports (site,date) UPSERT race
```

**race 결과**:
- A 의 `fetch_sheet_data` 시점에 B parser INSERT 끝났는지 시점 의존 — 끝났으면 A+B 합집합, 안 끝났으면 A 만
- B 도 마찬가지 (A 누락 가능)
- 둘 다 UPSERT 시도 → last write wins. last write 가 합집합 정확하다는 보장 X
- **C 가 그 뒤 진행되면 A+B+C 합집합 자동 회복** (eventual consistency)

**완화책 (D-6)**: EC 정책 채택. PoC 단순 + 시연 라이브 호환. AL (PG advisory lock) 은 1줄이라 보험이지만 cycle latency 1~2초 추가 → 미채택.

### 5.3 `/export/run` (D-5 E-2 hybrid) 동작

```
GET /export/run?site_id=...&date=...
  → pg = request.app.state.pg           ★ #N21 자연 해소 (lifespan pool 재사용)
  → cached = fetch_consolidated_report(pg, site_id, date)
  → if cached is not None:
        return Response(cached, ...)     ★ cache hit (정상 시연 path)
  → miss fallback:
       site = fetch_site_by_id(pg, site_id)
       if not site: raise HTTPException(404)
       try:
           data = fetch_sheet_data(pg, site_id, date)
       except NoDataError: raise HTTPException(400)
       xlsx_bytes = render_xlsx(data, date, project=site["name"])
       return Response(xlsx_bytes, ...)  ★ (E-2 는 UPSERT 안 함 — 다음 cycle 이 만들어줌)
```

### 5.4 dual-END 정책 (D-8)

- LangGraph multi-end 자연 지원 — state values 가 양 path update merge
- cycle 완료 판단 = 양 path 모두 END 도달
- `update_run_status='completed'` 마크 책임 = reporter_node (보통 더 늦게 끝남)
- exporter 노드 안에서 모든 예외 swallow (try/except Exception + log.exception + return {}) — LangGraph 1.2.0 multi-end fault isolation 미지원 회피. exporter path 는 LangGraph 입장에서 항상 'completed' (NoDataError / render / PG 예외 모두 silent skip) → reporter path 정상 진행 → cycle 'completed'
- 그 경우 `consolidated_reports` row 없음 → `/export/run` 의 (E-2) fallback live render 가 보장

---

## 6. Schema + helpers

### 6.1 PG migration — `consolidated_reports`

`infra/postgres/migrations/2026-05-27_consolidated_reports.sql`:

```sql
CREATE TABLE IF NOT EXISTS consolidated_reports (
  site_id       TEXT        NOT NULL REFERENCES sites(site_id),
  report_date   DATE        NOT NULL,
  xlsx_bytes    BYTEA       NOT NULL,
  run_id        UUID        NOT NULL REFERENCES pipeline_runs(run_id),
  generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  byte_size     INTEGER     GENERATED ALWAYS AS (length(xlsx_bytes)) STORED,
  is_mock       BOOLEAN     NOT NULL DEFAULT FALSE,
  PRIMARY KEY (site_id, report_date)
);

CREATE INDEX IF NOT EXISTS idx_consolidated_reports_date
  ON consolidated_reports (report_date DESC);
CREATE INDEX IF NOT EXISTS idx_consolidated_reports_run
  ON consolidated_reports (run_id);

COMMENT ON TABLE consolidated_reports IS
  '(B-1 / T-A / N-1 / S-1) graph cycle 마다 1번 UPSERT — site×date 합집합 xlsx 사전생성. 본 cycle 2026-05-27 spec.';
```

설계 디테일:
- `(site_id, report_date)` PK → `ON CONFLICT` UPSERT 자연
- `byte_size` GENERATED COLUMN — 운영 모니터링 (비정상 row 탐지)
- `is_mock` — 선행 8 테이블 (sites 선행 존재 + 2026-05-20 마이그로 추가된 7개: `pipeline_runs` / `parser_reports` / `parser_activities` / `mapper_activities` / `forecasts` / `optimizer_advice` / `daily_reports` — `infra/postgres/migrations/2026-05-20_add_is_mock.sql` 참조) 일관성 + seed mock backfill (D-11) 식별
- `run_id` FK pipeline_runs — 마지막 write cycle audit
- index 2 (date DESC + run_id) — UI list / audit 양 path 커버

### 6.2 `pipeline/state.py` 변경

```python
# pipeline/state.py:226 — class CPIAState(TypedDict):  (total=True, 기본값)
# 선행 cycle 의 D-12 4 필드 (bp_name / project / message_id / postgres_url) 가 이미
# 같은 total=True 에 끼워넣어진 패턴. 본 cycle 도 동일 패턴.
class CPIAState(TypedDict):
    # ... 기존 필드 유지 (선행 D-12 의 4 필드 포함) ...

    # (D-7) exporter_node 산출 meta — bytes 는 박지 않음 (PostgresSaver checkpoint 폭증 방지)
    consolidated_xlsx_run_id: str          # str(uuid.UUID)
    consolidated_xlsx_generated_at: str    # ISO 8601 (datetime.utcnow().isoformat()+"Z")
```

`TypedDict` 는 정적 타입 관점에선 `total=True` 가 모든 키 필수지만, **런타임은 dict** 라 absent 키 안전 (선행 D-12 의 `message_id` / `postgres_url` 도 CLI 진입 시 absent 패턴으로 사용). 본 cycle 의 신 필드 2개도 CLI / 회귀 테스트 진입에서 absent 호환.

### 6.3 `pipeline/db.py` helper 추가

선행 cycle 의 `insert_collector_inbox` / `update_collector_inbox_status` 와 동일 패턴 (module-level free function, PGClient 인스턴스 받음).

```python
async def upsert_consolidated_report(
    pg: PGClient,
    *,
    site_id: str,
    report_date: _date,
    xlsx_bytes: bytes,
    run_id: uuid.UUID,
) -> None:
    """ON CONFLICT (site_id, report_date) — last write wins. (D-2 / D-4 / D-6 EC)"""
    async with pg._pool.acquire() as con:
        await con.execute(
            """
            INSERT INTO consolidated_reports
              (site_id, report_date, xlsx_bytes, run_id, generated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (site_id, report_date) DO UPDATE
              SET xlsx_bytes   = EXCLUDED.xlsx_bytes,
                  run_id       = EXCLUDED.run_id,
                  generated_at = EXCLUDED.generated_at
            """,
            site_id, report_date, xlsx_bytes, run_id,
        )


async def fetch_consolidated_report(
    pg: PGClient,
    *,
    site_id: str,
    report_date: _date,
) -> Optional[bytes]:
    """(D-5 E-2) hit → bytes, miss → None."""
    async with pg._pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT xlsx_bytes FROM consolidated_reports WHERE site_id=$1 AND report_date=$2",
            site_id, report_date,
        )
    return row["xlsx_bytes"] if row else None
```

### 6.4 `pipeline/agents/exporter.py` — 노드 fn append

```python
# 기존 fetch_sheet_data / render_xlsx / _fill_* / COL dict / NoDataError / SheetData 그대로.
# 아래는 신규 append only.

import uuid
from datetime import datetime as _dt
from typing import Any

from pipeline.db import (
    PGClient, fetch_site_by_id,
    upsert_consolidated_report,  # ★ 신규
)
from pipeline.state import CPIAState

import logging
log = logging.getLogger("cpia.exporter_node")


async def consolidated_xlsx_node(state: CPIAState) -> dict[str, Any]:
    """graph 노드 — Atomizer 끝나면 fan-out 으로 호출 (D-3 N-1).

    1) fetch_sheet_data → 자기 run + 이전 run 합집합 (D-12 / D-3 invariant 유지)
    2) render_xlsx → bytes
    3) upsert_consolidated_reports → PG UPSERT (D-2 last write wins)
    4) state 에 meta 만 박음 (D-7 bytes 는 안 박음 — checkpoint 폭증 방지)

    예외 처리:
      - NoDataError: log + skip UPSERT, return {}
        발현 조건 = site×date 의 cold-start (seed 미적용 + 그 어떤 run 도 진입 안 함).
        graph 흐름상 자기 cycle 의 parser_reports INSERT 는 atomizer 도달 전에 끝나므로
        (graph.py:594~597 collector → parser → mapper → hil_1 → atomizer 순서) 자기 run 데이터는
        항상 존재. NoDataError 는 D-11 seed backfill 이 누락된 site×date 의 첫 cycle 에서만 가능.
      - render_xlsx / fetch_site_by_id / upsert 예외: log.exception + return {} (silent skip) — D-8 / 거동 B 대응 (LangGraph 1.2.0 multi-end fault isolation 미지원).
    """
    site_id = state["site_id"]
    report_date = _date.fromisoformat(state["date"])
    run_id = uuid.UUID(state["run_id"])

    pg = PGClient(state["postgres_url"])
    await pg.connect()
    try:
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError:
            log.warning(
                "consolidated_xlsx_node: NoData site=%s date=%s — skip UPSERT",
                site_id, report_date,
            )
            return {}
        site_row = await fetch_site_by_id(pg, site_id)
        project = (site_row or {}).get("name") or state.get("project") or "CPIA"
        xlsx_bytes = render_xlsx(data, report_date, project=project)
        await upsert_consolidated_report(
            pg, site_id=site_id, report_date=report_date,
            xlsx_bytes=xlsx_bytes, run_id=run_id,
        )
        log.info(
            "consolidated_xlsx_node: UPSERT site=%s date=%s bytes=%d run=%s",
            site_id, report_date, len(xlsx_bytes), run_id,
        )
    finally:
        await pg.close()

    return {
        "consolidated_xlsx_run_id": str(run_id),
        "consolidated_xlsx_generated_at": _dt.utcnow().isoformat() + "Z",
    }
```

### 6.5 `pipeline/graph.py` 변경 (4 줄)

```python
# 신규 import 1
from pipeline.agents.exporter import consolidated_xlsx_node

# build_graph 안에서, 기존 atomizer add_node 다음 위치에:
graph.add_node("exporter", consolidated_xlsx_node)        # ★ 신규 노드 (D-3 N-1)
graph.add_edge("atomizer", "exporter")                     # ★ fan-out edge
graph.add_edge("exporter", END)                            # ★ dual-END (D-8)
# 기존 atomizer → forecaster edge 는 그대로 유지 — fan-out 의 다른 가지
```

### 6.6 `pipeline/exporter_routes.py` 변경 ((E-2) + #N21)

```python
from fastapi import APIRouter, HTTPException, Request, Response

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx
from pipeline.db import fetch_consolidated_report, fetch_site_by_id  # ★ fetch_consolidated_report 신규

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/run")
async def export_consolidated(
    request: Request,                                       # ★ Request 의존성 (lifespan pool)
    site_id: str,
    date: str,
) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = request.app.state.pg                                # ★ #N21 자연 해소

    # (D-5 E-2) hit 우선
    cached = await fetch_consolidated_report(
        pg, site_id=site_id, report_date=report_date,
    )
    if cached is not None:
        return _build_xlsx_response(cached, date)

    # miss → live render fallback
    site = await fetch_site_by_id(pg, site_id)
    if not site:
        raise HTTPException(404, f"site_id={site_id} 없음")
    try:
        data = await fetch_sheet_data(pg, site_id, report_date)
    except NoDataError as e:
        raise HTTPException(400, str(e))
    xlsx_bytes = render_xlsx(
        data, report_date, project=site.get("name") or "CPIA",
    )
    return _build_xlsx_response(xlsx_bytes, date)


def _build_xlsx_response(xlsx_bytes: bytes, date: str) -> Response:
    """Content-Disposition UTF-8 raw_headers 패치 (한글 파일명, 선행 cycle 의 a7e2465 패치 유지)."""
    filename = f"통합작업일보_{date}.xlsx"
    resp = Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.raw_headers.append((
        b"content-disposition",
        f'attachment; filename="{filename}"'.encode("utf-8"),
    ))
    return resp
```

### 6.7 `pipeline/api.py` lifespan 의 `app.state.pg` 보장

`request.app.state.pg` 사용 위해 lifespan 에서 PGClient pool 을 `app.state.pg` 로 보관. 이미 되어 있으면 변경 0, 안 되어 있으면 1줄 추가:

```python
# pipeline/api.py:lifespan 안
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 기존:
    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    app.state.pg = pg                                       # ★ 이게 보장 — exporter_routes 가 사용
    # ... (collector idle_worker task spawn 등 기존 로직)
    yield
    await pg.close()
```

본 spec 작성 시점 (2026-05-27) 에 `app.state.pg` 가 이미 설정되어 있는지 implementation 단계에서 확인 — 안 되어 있으면 위 1줄 보장.

---

## 7. Error / edge case / 회귀 영향

### 7.1 cycle path 에러 매트릭스

| 시나리오 | exporter 노드 | cycle | UI |
|---|---|---|---|
| site×date 의 cold-start (seed 미적용 + 어떤 run 도 진입 안 함) | NoDataError catch → log.warning + return {} | exporter path END (skip UPSERT), reporter 정상 → 'completed' | `/export/run` cache miss → live render도 NoData → 400 |
| `render_xlsx` openpyxl 예외 | except Exception swallow → log.exception + return {} | exporter path END (skip UPSERT), reporter 정상 → 'completed' | cache miss → fallback 도 예외 → 500 |
| PG drop on UPSERT | except Exception swallow → log.exception + return {} | exporter path END (skip UPSERT), reporter 정상 → 'completed' | cache miss → fallback OK |
| race (자기 fetch 시점 다른 cycle parser 진행 중) | 부분 합집합 → stale row | UPSERT atomic, last write wins | 다음 cycle 자동 회복 (D-6 EC) |
| forecaster LLM 실패 | exporter path 영향 0 (별 path) | reporter path 가 forecaster 실패 전파 받음 가능 → 'failed' | exporter 결과 PG 저장됨 → 다운로드 정상 |
| collector_node 파일명 regex 미일치 | exporter path 도달 안 함 | cycle 'failed', collector_inbox.parse_status='dead_letter' | 기존 row 있으면 그대로, 없으면 cache miss → 400 |

### 7.2 `/export/run` 응답 매트릭스

| 시나리오 | HTTP | 내용 |
|---|---|---|
| Cache hit | 200 | xlsx bytes (PG SELECT row) |
| Cache miss + parser_reports 있음 | 200 | xlsx bytes (live render) |
| Cache miss + site 없음 | 404 | `site_id={...} 없음` |
| Cache miss + parser_reports 0건 | 400 | `NoDataError(...) 데이터 없음` |
| Cache miss + render 예외 | 500 | traceback log |
| date 형식 위반 | 400 | `date must be YYYY-MM-DD` |

### 7.3 회귀 영향 — 기존 기능 8개

**영향 0 (안 건드림)**:
- `reports` 페이지 — `daily_reports.report_md` 그대로, `reporter.py` 변경 0
- `dashboard` / `home` — site KPI / 대시보드 기존 그대로
- `review` 페이지 — hil_1 + mapping_corrections 그대로
- `forecaster` / `optimizer` / `atomizer` — graph state 의 신 필드 2개 안 봄
- `collector idle_worker` — graph.ainvoke 호출만 함, 노드 구성 무관
- `AWS 마이그` — `scripts/aws_backup_and_migrate.py` 가 pg_dump 자동, `consolidated_reports` 도 같이 dump/restore

**영향 검증 필요 (테스트로 보장)**:
- **PostgresSaver checkpoint** — state 신 필드 2개 (TypedDict total=True 지만 런타임 dict 라 absent 키 안전 — §6.2 참조), checkpoint resume 시 신 필드 None — 안전. 회귀: 새 graph cycle 실행 + interrupt + resume + 끝까지
- **graph dual-END** — LangGraph multi-end 시 cycle 'completed' 판단. `tests/test_graph_dual_end.py` 신규 — fan-out 양 path 모두 END 도달 + 한 path 실패 시 cycle 거동

**잠재 영향 (선택적 작업, 본 cycle 권장)**:
- **tasks 페이지의 Agent stage progress** — 현 `_AGENTS_META` 7 agent hard-code. Exporter stage 추가 (D-10). 시연 임팩트 (B-1 선택 동기) 와 직결.
- **`pipeline/api.py:lifespan` 의 `app.state.pg`** — `/export/run` 이 `request.app.state.pg` 사용. lifespan 에서 보장 (§6.7)

### 7.4 시연 risk 표

| Risk | 발현 가능성 | 시연 영향 | 완화책 |
|---|---|---|---|
| 첨부 도착 후 exporter cache 적재 ~15초 안에 사용자 클릭 | 낮음 | (E-2) fallback ~100ms 응답 — 사용자는 "정상" 인식 | (E-2) 자체가 완화책 |
| LangGraph 1.2.0 multi-end fault isolation 미지원 (issue #6170 open) | 확정 (B 거동) | 단일 노드 예외 시 cycle 전체 fail | exporter 노드 안에서 except Exception swallow 패턴 (T3 commit `0dbd449`) + `tests/test_graph_dual_end.py` 거동 capture |
| 시연 site×date 의 cycle 0번 실행 (row 없음 + UI 가 list 노출) | 중 | UI list 에 보이지만 다운로드 시 NoData 400 | `scripts/seed_dummy_year.py` 에 `consolidated_reports` mock UPSERT (D-11) |
| PG pool 고갈 (대량 동시 cycle) | 낮음 | exporter UPSERT 지연 | 기존 semaphore `CPIA_COLLECTOR_CONCURRENCY=2` 직렬화 |
| AWS 마이그 시 pg_dump 크기 폭증 | 낮음 | dump 시간 증가 ~수십 초 | 365일 × 6 site × 150KB ≈ 330MB/년 — 무시 가능 |
| race 발현 — 다음 cycle 까지 stale row | 낮음 | UI 에서 다운로드 시 1개 업체 누락 가능 | D-6 EC + 시연 라이브 (순차 메일) 흐름 |

---

## 8. 구현 순서 + 작업 분리 + 일정

### 8.1 Task 인벤토리 (실행 순서)

| Task | 분량 | 종류 | TDD | 의존 |
|---|---|---|---|---|
| 0 | 30분 | PG migration `consolidated_reports` + 회귀 idempotent | ✅ | — |
| 1 | 1시간 | `db.py` helper 2 (`upsert` + `fetch`) + 단위 테스트 | ✅ | T0 |
| 2 | 5분 | `state.py` 2 필드 | (수반) | — |
| 3 | 2시간 | `exporter.py` `consolidated_xlsx_node` 신규 fn + 단위 (mock fetch / mock upsert / NoDataError skip) | ✅ | T1, T2 |
| 4 | 3시간 | `graph.py` 3 줄 + dual-END 통합 테스트 (LangGraph multi-end 거동 — 가장 위험) | ✅ | T3 |
| 5 | 2시간 | `exporter_routes.py` (E-2) hybrid + #N21 해소 + 테스트 변경 | ✅ | T1 |
| 6 | 1시간 | `scripts/seed_dummy_year.py` 에 `consolidated_reports` mock UPSERT | ✅ | T0 |
| 7 | 1-2시간 | `_AGENTS_META` 에 Exporter stage 추가 + `web/lib/transforms.ts` mapping | (수반) | — |
| 8 | 1시간 | B_Track `ConsolidatedReportCard.handleExport` swap (#R-N2) + `.env.local.example` 에 `NEXT_PUBLIC_FASTAPI_BASE` | (수반) | T5 |
| 9 | 2시간 | e2e 시연 시나리오 검증 + 이전 cycle Task #14 통합 마무리 | (수반) | T4, T5, T8 |

**합계 13~14 시간 ≈ 1.5 작업일**.

### 8.2 일정 (PoC D-9 = 2026-06-05)

| 일자 | 작업 | 게이트 |
|---|---|---|
| **5/27 (오늘)** | spec 작성 + spec-document-reviewer + 사용자 승인 + writing-plans 진입 | spec 머지 |
| **5/28** | T0-T1-T2-T3 (PG migration + db helper + state + node fn) | 단위 테스트 green |
| **5/29** | T4 (graph dual-END 통합 테스트 — 가장 위험) + T5 (E-2 endpoint) | 통합 테스트 green |
| **5/30** | T6 (seed backfill) + T7 (Agent stage UI) | 시연 데이터 준비 |
| 6/2 | T8 (B_Track swap) + T9 (e2e 검증) | e2e 시연 통과 |
| 6/3~6/4 | 시연 리허설 + 잔여 fix | 시연 안정성 |
| 6/5 | 시연 | |

**buffer 2-3일** 확보.

### 8.3 TDD 디시플린 (Iron Law "Verification before done")

각 Task 의 "done" 정의 = (a) 실 명령 실행 + (b) 실 출력 원본 인용 + (c) 의미적 검증.

- **T0**: `psql -f migrations/2026-05-27_consolidated_reports.sql; psql -c '\d consolidated_reports'` 출력으로 컬럼 7개 + index 2개 + FK 2개 확인
- **T1**: `pytest tests/test_db_consolidated_reports.py -v` — 실 PG fixture, INSERT path / UPDATE path / SELECT hit / SELECT miss / FK 위반 5건 PASS
- **T3**: `pytest tests/test_exporter_node.py -v` — fetch_sheet_data mock + render_xlsx mock + upsert assert + NoDataError skip path 4건 PASS
- **T4**: `pytest tests/test_graph_dual_end.py -v` — fan-out + 양 path END + cycle 'completed' + exporter 실패 시 reporter 'completed' 4건 PASS
- **T5**: `pytest tests/test_exporter_endpoint.py -v` — hit path + miss path + 404 + 400 + 500 5건 PASS. `request.app.state.pg` 호출 검증
- **T7** (수반 — UI): `curl http://localhost:8000/api/agents/status` 응답에 Exporter stage entry 존재 + tasks 페이지 visual 확인 — Agent stage progress 에 Exporter 가 시각적으로 노출
- **T8** (수반 — B_Track swap): `npm run dev` (port 5536) → export 페이지 진입 → 다운로드 버튼 클릭 → Chrome DevTools Network 탭에서 `/export/run?site_id=...&date=...` 요청 보임 + 200 응답 + `통합작업일보_2025-09-25.xlsx` 파일명 다운로드 + openpyxl 로 열어 4 시트 검증
- **T9**: 실 메일 도착 → graph cycle 'completed' → `psql -c "SELECT site_id, report_date, byte_size, generated_at FROM consolidated_reports ORDER BY generated_at DESC LIMIT 5"` 으로 row 존재 검증 → `curl -o /tmp/test.xlsx 'http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25'` cache hit 응답 검증 (X-Cache 헤더 등 없으니 raw_headers 의 content-disposition 한글 + bytes 200 확인) → UI 다운로드 정상 + Agent stage progress 7단계 확인

---

## 9. 다른 세션 충돌 회피

본 spec 작성 시점 (2026-05-27 10:30) 의 working tree:
- 다른 세션이 `data-contract/`, `deep-dive/`, `pipeline/agents/optimizer/view_builder.py`, `pipeline/chroma_client.py` 갱신 중
- 본 cycle 의 변경 영역 (`graph.py` / `state.py` / `db.py` / `exporter.py` 신 fn / `exporter_routes.py` / 신 PG migration / 테스트) 과 **직접 충돌 0**

### 9.1 절대 안 건드림 (read-only)

- `pipeline/agents/parser.py` / `parser_node.py` / `collector_node.py`
- `pipeline/agents/mapper.py`
- `pipeline/agents/atomizer.py`
- `pipeline/agents/forecaster/` (디렉토리 전체)
- `pipeline/agents/optimizer/` (디렉토리 전체 — 다른 세션 작업 중)
- `pipeline/agents/reporter.py` (D-9 그대로)
- `pipeline/chroma_client.py` (다른 세션)
- `pipeline/checkpointer.py`
- `pipeline/collector/` (디렉토리 전체 — 선행 cycle 완성)
- `pipeline/agents/exporter.py` 의 **기존 함수** (`fetch_sheet_data`, `render_xlsx`, `_fill_*` 4종, COL dict 4종, `NoDataError`, `SheetData`, `_coerce`, `_korean_weekday`, `_fill_timeshift`, `TEMPLATE_PATH`, `DATA_START_ROW`) — **변경 0**. 신 fn `consolidated_xlsx_node` 만 append

### 9.2 신규 only (충돌 0)

- `infra/postgres/migrations/2026-05-27_consolidated_reports.sql`
- `pipeline/tests/test_db_consolidated_reports.py`
- `pipeline/tests/test_exporter_node.py`
- `pipeline/tests/test_graph_dual_end.py`

### 9.3 변경 라인 최소 (충돌 가능)

- `pipeline/graph.py` — 4 줄 추가 (import + add_node + add_edge × 2). 기존 노드 / edge 0 수정
- `pipeline/state.py` — 2 줄 추가 (CPIAState 신 필드). 기존 필드 0 수정
- `pipeline/db.py` — ~40 줄 append (2 helper). 기존 helper 0 수정
- `pipeline/agents/exporter.py` — ~40 줄 append (`consolidated_xlsx_node`). 기존 함수 0 수정
- `pipeline/exporter_routes.py` — 30 줄 변경 (기존 핸들러 본문 + `_build_xlsx_response` helper 분리)
- `pipeline/api.py` — 1 줄 (lifespan `app.state.pg` 보장, 이미 되어 있으면 0)
- `pipeline/api.py` — `_AGENTS_META` 5 줄 (Exporter stage 추가)
- `scripts/seed_dummy_year.py` — ~30 줄 append (mock backfill)
- `web/lib/transforms.ts` — ~5 줄 (Agent stage mapping)
- `web/app/components/export/ConsolidatedReportCard.tsx` — ~10 줄 (handleExport swap)
- `web/.env.local.example` — 1 줄 (`NEXT_PUBLIC_FASTAPI_BASE`)

### 9.4 머지 순서

1. 다른 세션의 `data-contract/`, `deep-dive/`, `view_builder.py`, `chroma_client.py` 작업 PR 머지 대기
2. 본 cycle PR rebase
3. graph.py / state.py / db.py 충돌 시 끼워넣기 수동 해결
4. CI green 후 머지

---

## 10. Open questions (implementation 단계에서 결정)

- **PG advisory lock 추가 여부**: D-6 의 EC 정책이 PoC 충분 — 하지만 1줄이라 보험으로 추가할 가치 평가. implementation 단계에서 `tests/test_graph_dual_end.py` 의 race 시나리오 실행 후 stale 발생 빈도 측정 → 빈번 시 보험 추가
- **`_AGENTS_META` 의 Exporter stage 표시 위치**: tasks 페이지에서 Forecaster 와 같은 row 의 다른 칸 (병렬 표시) vs Reporter 다음 row (linear 표시). 시연자 의도 확인 — 본 cycle 의 시각화 폴리시 결정
- **UI 가 노출할 timestamp 선택**: PG 컬럼 `consolidated_reports.generated_at` (NOW() — PG 시각) vs state meta `consolidated_xlsx_generated_at` (Python `_dt.utcnow()` — graph 노드 시각). 두 값 둘 다 보존됨 (drift ~수십 ms 무관). 단순 표시 선택 사항.
- **노드 PG 접근 패턴 graph-wide refactor (별 cycle)**: 현재 `collector_node` / `consolidated_xlsx_node` 등 일부 노드가 `state["postgres_url"]` 로 PGClient 매 cycle 새로 생성. `mapper_node` / `atomizer_node` 등은 `build_graph(cfg)` 의 cfg 클로저 패턴. 두 패턴 공존 — graph 전체 일관성 위해 cfg 클로저 또는 lifespan pool 공유 (예: cfg 안에 pool 핸들 박기) 로 통일 검토. **본 cycle 범위 밖 — 신 노드 (`consolidated_xlsx_node`) 는 선행 `collector_node` 와 동일 패턴 (state[postgres_url]) 채택**.

---

## 11. Next step

1. spec-document-reviewer subagent 디스패치 → 이슈 반영 (max 3 iter)
2. 사용자 spec 리뷰 게이트
3. `superpowers:writing-plans` 스킬 전환 → implementation plan 산출 (`docs/superpowers/specs/2026-05-27-cpia-exporter-graph-integration-plan.md`)
4. plan 실행 (`superpowers:subagent-driven-development`) — T0 → T9 순서

---

## 핵심 결정 요약 (한 줄)

**(D-1 / D-2 / D-3 / D-4 / D-5 / D-6 / D-7 / D-8 / D-9 / D-10 / D-11)**
graph 사전생성 / 매 cycle 1번 / Atomizer 와 병렬 fan-out / PG BYTEA `consolidated_reports` UPSERT / `/export/run` hybrid (hit→serve, miss→live render) / Eventual Consistency / state 는 meta 만 / multi-end / 본 cycle 에 B_Track UI swap 포함 / Exporter stage UI 추가 / seed mock backfill.

선행 cycle (`2026-05-19`) 의 D-6 retract + D-9 유지 + #R-N2 해소 + #N21 자연 해소.
