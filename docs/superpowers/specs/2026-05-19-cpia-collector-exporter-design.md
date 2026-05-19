# CPIA Collector + Exporter — Design Spec

> Cycle: 2026-05-19 brainstorming (`superpowers:brainstorming`)
> Status: design 단계. Implementation plan 은 별 cycle (writing-plans 산출).
> Input:
> - 사용자 의도 (본 대화): 이메일 트리거 collector + 통합 작업일보 xlsx exporter 구현
> - 현 코드: `pipeline/agents/collector.py` (디렉토리 walk 만, 메일 통합 stub 명시) / `pipeline/agents/reporter.py` (forecast+optimizer MD 종합 보고서)
> - 현 UI: `web/app/(app)/export/page.tsx` + `ConsolidatedReportCard.tsx` (A_Track FastAPI endpoint 대기 중)
> - 현 BFF: `web/app/api/mock/consolidated/route.ts` (parser_reports jsonb + parser_activities PG SELECT 완료, 4 시트 schema 확정)
> - 통합 양식: `docs/sample/통합작업일보_DUMMY_20250926.xlsx` (4 시트: 출력인원/직종/장비/물량)
> - state.py: `BPSummary` / `JobAllocation` / `EquipmentAllocation` / `Activity` / `ParsedDailyReport` 4 시트와 1:1
> Branch: A_Track, git SHA: 105ee6a
> 다른 세션: parser~optimizer 테스트 진행 중 → 충돌 회피 룰 §9 명시

---

## 1. Context

CPIA 7-agent pipeline 의 양 끝 (입력 Collector / 출력 Exporter) 가 본 cycle 의 범위:

- **Collector 현 상태** (`pipeline/agents/collector.py`, 72 줄): `discover_daily_reports(input_dir)` + `collect_and_parse(input_dir, cfg)` 두 함수만. 디렉토리 walk + 병렬 Parser 호출. 코드 주석 (collector.py:9~10) 명시: **"메일 통합 (IMAP/API 폴링 + 첨부 추출) 은 별 cycle 후속."** 본 cycle 이 정확히 그 후속.

- **Exporter 현 상태**: `pipeline/agents/reporter.py` 162 줄이 forecast + optimizer 종합 마크다운 (= `daily_reports.report_md`) 생성. CLAUDE.md (2026-05-18 footer): **"Agent rename: Reporter → Exporter. 기능 재정의: 업체별 작업일보 → 통합 작업일보 출력. 이번 변경은 B_Track 만, A_Track 파일 rename 은 후속 PR."** ← 본 cycle 이 그 후속 PR. 단 `reports` 페이지가 살아있어 (`web/app/(app)/reports/page.tsx` + `/api/mock/report` + `daily_reports.report_md`) **reporter.py MD 기능은 폐기 X — 그대로 유지** (Section 2 결정).

- **UI 가 기다리는 endpoint**: `ConsolidatedReportCard.tsx:37~38` 주석 정확 인용: *"PoC: Exporter 에이전트 호출은 A_Track 구현 대기. ... 추후 A_Track FastAPI POST /export/run?date= 가 준비되면 a.href 를 그 응답 URL 로 swap."* B_Track 은 데이터 fetch (`/api/mock/consolidated`) + 다운로드 흐름 모두 깔아둠. 본 cycle = A_Track endpoint 채우기.

- **데이터 schema 도 확정**: `/api/mock/consolidated/route.ts` 가 이미 `parser_reports.bp_summaries` jsonb + `parser_activities` + 정규화 2종 SELECT 로 4 시트 row 반환. Python BE Exporter 는 같은 SQL 의미론 + openpyxl 렌더링만 추가.

PoC 데모 마감 = 2026-06-05 (목), D-17.

---

## 2. Goal + Non-goal

**Goal (본 cycle)**:
- Gmail IMAP IDLE 푸시 트리거 Collector — 메일 도착 시 첨부 추출 → 파일명 식별 → graph 1회 실행
- 통합 작업일보 xlsx Exporter — `parser_*` PG SELECT → 4 시트 dummy 템플릿 fill → FastAPI `GET /export/run` binary stream
- `collector_inbox` PG 테이블 신규 (Message-ID dedup + run 추적)
- 데모용 별도 Gmail 계정 (cpia-collector@gmail.com 류) 신규
- 단위 / 통합 테스트 (LLM bypass, 결정론적 검증)

**Non-goal (후속 cycle)**:
- 자동 회신 (PM 에게 처리 결과 메일) — PoC dead_letter 폴더 + Gmail label 로 충분
- SK 사내 메일 (Outlook/Office 365) 연동 — 권한 / endpoint 부담
- xlsx 캐싱 / Pre-render (PoC 사용량 분당 1~2 클릭, PG SELECT 100ms 이내 예상)
- Multi-site 동적 site_id 매핑 (PoC 단일 site `m15x-ph3-ibl`)
- Mapper 결과 반영 시트4 (dummy 양식엔 WBS 컬럼 없음 — Parser raw 만으로 충분)
- 현 `reporter.py` MD 종합보고서 폐기 / rename (reports 페이지 살아있음 — 그대로 유지)

---

## 3. Decisions (사용자 confirm — 본 cycle brainstorming)

| # | 결정 | 선택 | 사유 |
|---|---|---|---|
| D-1 | 메일 채널 | Gmail (데모용 별도 계정 신규) | SK 사내 메일 권한 부담 회피, IMAP IDLE 지원, PoC D-17 일정 가장 안전 |
| D-2 | 트리거 | **IMAP IDLE (push)** | zero-latency. 외부 endpoint / Pub/Sub / 도메인 불필요 (IDLE 은 IMAP 표준 push) |
| D-3 | Run 단위 | 첨부 1개 = 1 graph run 즉시 (1 메일 N 첨부 = N run) | PM 이 여러 업체 일보 일괄 전송 케이스 자연 지원 |
| D-4 | 식별 규약 | 첨부 파일명 정규식 (업체별 / 통합 2 패턴) | 샘플 파일명 규약 이미 운영 중. subject 규약 강제 (PM 운영 부담) 회피 |
| D-5 | Collector 운영 모델 | FastAPI startup background task (`asyncio.create_task(idle_loop())`) | docker-compose 변경 0, 프로세스 1개, PoC 가장 단순 |
| D-6 | Exporter 위치 | graph 밖 별 service (FastAPI `GET /export/run?site_id&date`) | UI 가 명시한 endpoint (ConsolidatedReportCard 주석). graph.py 변경 0 |
| D-7 | Exporter xlsx 생성 | Python BE openpyxl + dummy 템플릿 fill | A_Track 분담 (CLAUDE.md). 헤더 / 셀 병합 / 스타일 보존 |
| D-8 | Exporter 데이터 소스 | `parser_*` PG SELECT (= `/api/mock/consolidated` 와 같은 SQL 의미론) | dummy 양식 4 시트와 1:1, mapper 정보 불필요 |
| D-9 | `reporter.py` 운명 | **그대로 유지** | reports 페이지 + daily_reports.report_md 가 살아있음. CLAUDE.md 의 "rename" 은 reports 페이지 간과한 표현 — 정확한 의도는 "신규 Exporter 추가" |
| D-10 | graph 호출 방식 | in-process `graph.ainvoke()` (HTTP self-call 안 함) | 같은 프로세스 안 self-loopback HTTP 는 오버킬 |

---

## 4. Architecture (Section 1)

```
[PM 들의 메일 클라이언트]
    │ 작업일보 xlsx 첨부 보냄
    ▼
[Gmail IMAP 서버 (imap.gmail.com:993)]
    │ IDLE EXISTS notification (push, zero-latency)
    ▼
┌──────────────────── pipeline/api.py (FastAPI, 1 프로세스) ────────────────────┐
│                                                                                │
│  startup event:                                                                │
│    if COLLECTOR_ENABLED:                                                       │
│      _idle_task = asyncio.create_task(idle_loop(cfg))                          │
│                                                                                │
│  shutdown event:                                                               │
│    _shutdown.set(); _idle_task.cancel()                                        │
│                                                                                │
│  기존 endpoints (변경 0):                                                       │
│    POST /run   POST /resume   GET /status/{run_id}                             │
│                                                                                │
│  신규 endpoint (별 module, include_router 1줄):                                 │
│    GET /export/run?site_id=&date=  →  통합 xlsx binary stream                  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
    │
    │ in-process: idle_worker → build_graph(cfg).ainvoke({...})
    ▼
[LangGraph 기존 — 변경 0]
   mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter(MD)
    │
    │ PG 적재
    ▼
[PostgreSQL]
  parser_reports / parser_activities / parser_job_allocations /
  parser_equipment_allocations / mapper_activities / daily_reports / ...
  + collector_inbox (신규)
    │
    │ Exporter SELECT
    ▼
[Next.js Dashboard]
  /reports   ← daily_reports.report_md (변경 0)
  /export    ← /api/mock/consolidated (변경 0) + Export 버튼이 FastAPI /export/run 호출
              (B_Track swap: ConsolidatedReportCard.tsx:48 의 a.href 만 한 줄 변경)
```

### 4.1 컴포넌트 5개

| 파일 | 신규/기존 | 책임 | 주 의존 |
|---|---|---|---|
| `pipeline/collector/idle_worker.py` | 신규 | IMAP IDLE 루프 + 첨부 추출 + dedup + in-process graph 호출 | aioimaplib, db.py (collector_inbox), graph.py |
| `pipeline/collector/filename_parser.py` | 신규 | 첨부 파일명 정규식 → (site_id, date, bp_name, project) | 없음 (순수 함수) |
| `pipeline/agents/exporter.py` | 신규 | PG SELECT → 4 시트 row → openpyxl 템플릿 fill → bytes | db.py, openpyxl |
| `pipeline/exporter_routes.py` | 신규 | FastAPI APIRouter — `GET /export/run` | exporter.py |
| `pipeline/api.py` | 수정 (3줄) | startup hook + shutdown hook + `include_router` | — |

**기존 `collector.py` 운명**: `discover_daily_reports()` / `collect_and_parse()` 그대로 유지 (테스트 / CLI 진입점용). idle_worker 가 같은 `discover_daily_reports` 시그니처는 재사용 안 함 (메일 첨부는 in-memory bytes 라 path 추상화 다름).

### 4.2 다른 세션 충돌 회피 — 명시

**Read-only (절대 안 건드림)**:
`parser.py`, `parser_llm.py`, `parser_post.py`, `mapper.py`, `atomizer.py`, `forecaster/`, `optimizer/`, `reporter.py`, `state.py`, `graph.py`, `checkpointer.py`, `chroma_client.py`

**신규 only (충돌 0)**: §4.1 의 4개 신규 파일 + 템플릿 xlsx + 마이그레이션 SQL + 테스트 4 종

**충돌 가능 (변경 라인 최소)**:
- `pipeline/api.py` — startup hook 1줄 + shutdown hook 1줄 + `include_router(...)` 1줄 = **총 3줄 추가**, 기존 endpoint 변경 0
- `pipeline/db.py` — 신규 helper 3 개 (`insert_collector_inbox`, `update_collector_inbox_status`, `fetch_collector_inbox_by_message_id`) 추가만. 기존 helper 변경 0

---

## 5. Data flow + Error handling (Section 2)

### 5.1 성공 path 시퀀스

```
PM 메일 (첨부 N)
  ── IMAP IDLE EXISTS notify ──▶ aioimaplib wait_server_push
                                       │
                                       ▼
                          fetch UNSEEN 메일 (RFC822 raw bytes)
                                       │
                                       ▼
                          Message-ID 추출 + collector_inbox dedup
                                       │
              ┌────────────────────────┴───────────────────────┐
              ▼ (첨부 1: regex match)               ▼ (첨부 2: regex 미일치)
   data/input/<YYMMDD>/<bp>.xlsx 저장        data/input/dead_letter/ 이동
   collector_inbox INSERT (pending)         Gmail label "cpia-dead-letter"
              │                                 + log
              ▼
   asyncio.create_task(run_for_attachment(...))   ← fire-and-forget
   semaphore(CPIA_COLLECTOR_CONCURRENCY=2)
              │
              ▼
   build_graph(cfg).ainvoke({run_id, date, input_files, site_id, ...})
              │
              ▼
   graph 실행: parser → mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter
              │
              ▼
   PG 적재: parser_reports / parser_activities / mapper_activities / daily_reports.report_md
   collector_inbox UPDATE (parse_status=completed)
              │
              ▼ (별 시점 — 사용자가 UI 에서 Export 버튼 클릭)
   GET /export/run?site_id=m15x-ph3-ibl&date=2025-09-26
              │
              ▼
   exporter.fetch_sheet_data(pg, site_id, report_date)
              │
              ▼
   exporter.render_xlsx(sheet_data, ...) — openpyxl 템플릿 fill
              │
              ▼
   Response(bytes, media_type=xlsx)
              │
              ▼
   ConsolidatedReportCard.handleExport → a.click() 다운로드
```

### 5.2 실패 path 매트릭스

| 시나리오 | Collector / Exporter 동작 | 사용자 가시성 |
|---|---|---|
| IMAP 연결 끊김 | exponential backoff reconnect (1→2→4→…→max 60s) | log only |
| Gmail IDLE timeout (~29분) | DONE + IDLE 재진입 (정상 동작) | (invisible) |
| Message-ID 중복 | skip (collector_inbox PRIMARY KEY 위반) | log only |
| 첨부 0개 메일 | skip + log "no attachment" | log only |
| 파일명 regex 미일치 | dead_letter 폴더 + Gmail label "cpia-dead-letter" | log only (PoC) — 자동 회신 후속 |
| `project` → `site_id` lookup miss | 위와 동일 (dead_letter) | log only |
| graph 실행 실패 | `pipeline_runs.status='failed'` + `collector_inbox.parse_status='failed'` + error 메시지 박힘 | Dashboard run 상태에 노출 |
| Exporter PG 0건 | HTTP 400 + `{"detail":"해당 ({site_id}, {date}) 데이터 없음"}` | UI 토스트 에러 |
| Exporter 템플릿 누락 | startup-time 체크로 사전 차단 (FastAPI 기동 실패) | 운영자만 |
| Exporter openpyxl 렌더 예외 | HTTP 500 + log full traceback | UI 토스트 에러 |

### 5.3 `collector_inbox` PG 테이블 (신규)

```sql
-- infra/postgres/migrations/<next>_collector_inbox.sql

CREATE TABLE collector_inbox (
  message_id TEXT PRIMARY KEY,                  -- IMAP RFC822 Message-ID 헤더
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  site_id TEXT NOT NULL,
  report_date DATE NOT NULL,
  bp_name TEXT NOT NULL,                        -- 통합 첨부의 경우 '_integrated'
  attachment_filename TEXT NOT NULL,
  attachment_path TEXT NOT NULL,                -- data/input/<date>/<...> 절대경로
  run_id UUID REFERENCES pipeline_runs(run_id), -- self-call 후 채워짐
  parse_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (parse_status IN ('pending','running','completed','failed','dead_letter')),
  error TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX collector_inbox_site_date_idx
  ON collector_inbox (site_id, report_date);

CREATE INDEX collector_inbox_status_idx
  ON collector_inbox (parse_status)
  WHERE parse_status IN ('pending','running','failed');
```

`run_id` 양방향 추적 — 메일 → run, run → 원본 메일 모두 가능 (감사용).

`UPDATE collector_inbox SET parse_status='running', run_id=$1 WHERE message_id=$2` 가 graph 호출 직전. 종료 후 completed/failed 갱신.

---

## 6. Collector 내부 구현 (Section 3)

### 6.1 IDLE 루프 lifecycle

```python
# pipeline/collector/idle_worker.py
import asyncio, logging
import aioimaplib

_shutdown = asyncio.Event()
log = logging.getLogger("cpia.collector")

async def idle_loop(cfg: "CollectorConfig") -> None:
    backoff = 1.0
    while not _shutdown.is_set():
        try:
            imap = aioimaplib.IMAP4_SSL(host=cfg.host, port=cfg.port)
            await imap.wait_hello_from_server()
            await imap.login(cfg.user, cfg.app_password)
            await imap.select("INBOX")
            backoff = 1.0  # 성공 시 reset
            await _drain_initial_unseen(imap, cfg)   # 시작 시 누적 메일 처리
            while not _shutdown.is_set():
                idle_task = await imap.idle_start(timeout=29 * 60)  # Gmail 30분 cutoff 대비
                try:
                    msg = await imap.wait_server_push()
                finally:
                    imap.idle_done()
                    try:
                        await asyncio.wait_for(idle_task, timeout=5)
                    except asyncio.TimeoutError:
                        pass
                if msg and any("EXISTS" in str(m) for m in msg):
                    await _drain_new(imap, cfg)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("IDLE loop error, reconnect in %.1fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
```

`FastAPI` startup/shutdown hook:

```python
# pipeline/api.py — 신규 3줄
from pipeline.collector.idle_worker import idle_loop, request_shutdown
from pipeline.exporter_routes import router as exporter_router

@app.on_event("startup")
async def _start_collector():
    if os.environ.get("COLLECTOR_ENABLED", "false").lower() == "true":
        app.state._idle_task = asyncio.create_task(idle_loop(_collector_cfg()))

@app.on_event("shutdown")
async def _stop_collector():
    request_shutdown()
    task = getattr(app.state, "_idle_task", None)
    if task:
        task.cancel()

app.include_router(exporter_router)
```

`COLLECTOR_ENABLED=false` 면 IDLE 루프 안 띄움 → 로컬 개발 / 테스트 환경에서 Gmail 인증 없이 FastAPI 기동 가능.

### 6.2 첨부 추출 + 파일명 식별

`pipeline/collector/filename_parser.py` — **순수 함수, 의존성 0**:

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

@dataclass(frozen=True)
class ParsedFilename:
    kind: Literal["bp", "integrated"]
    project: str
    bp_name: Optional[str]
    trade: Optional[str]
    zone: Optional[str]
    date: str  # YYYY-MM-DD


def parse_filename(name: str) -> Optional[ParsedFilename]:
    """업체작업일보_<project>_..._<bp>_<trade>_<zone>_<YYMMDD>.xlsx
       통합작업일보_<project>_<YYMMDD>.xlsx
    매치 실패 시 None.
    """
    stem = Path(name).stem
    if not (stem.startswith("업체작업일보_") or stem.startswith("통합작업일보_")):
        return None
    parts = stem.split("_")
    yymmdd = parts[-1]
    if not (len(yymmdd) == 6 and yymmdd.isdigit()):
        return None
    date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    if stem.startswith("통합작업일보_"):
        return ParsedFilename(
            kind="integrated",
            project="_".join(parts[1:-1]),
            bp_name=None, trade=None, zone=None, date=date,
        )
    # 업체별: 끝에서 4 토큰 = bp, trade, zone, date
    if len(parts) < 5:
        return None
    return ParsedFilename(
        kind="bp",
        project="_".join(parts[1:-4]),
        bp_name=parts[-4].strip(),  # 공백 가능 (`_ 중원엔지니어링_` 류 → ' 중원엔지니어링')
        trade=parts[-3],
        zone=parts[-2],
        date=date,
    )
```

테스트 케이스 (parametrize):

| 입력 | 기대 |
|---|---|
| `업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsm` | kind=bp, project=`M15X_PH4_041_M15X_PH4_UT`, bp=`중원엔지니어링`, trade=`UT배관공사`, zone=`FAB`, date=`2025-09-17` |
| `통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` | kind=integrated, project=`M15X Ph-3 IBL PJT 작업일보`, date=`2025-09-25` |
| `random.xlsx` | None |
| `업체작업일보_x.xlsx` | None (토큰 부족) |
| `업체작업일보_a_b_c_d_99999.xlsx` | None (date 5자리) |

`project → site_id` 매핑: `db.fetch_site_by_project_code(project) → site_id | None`. 미일치 = dead_letter.

### 6.3 메일 → graph 호출

`asyncio.create_task` fire-and-forget + semaphore N 제한:

```python
_GRAPH_SEM = asyncio.Semaphore(int(os.environ.get("CPIA_COLLECTOR_CONCURRENCY", "2")))

async def run_for_attachment(
    attachment_path: Path,
    meta: ParsedFilename,
    message_id: str,
    cfg: "CollectorConfig",
) -> None:
    async with _GRAPH_SEM:
        run_id = uuid.uuid4()
        async with PGClient(cfg.postgres_url) as pg:
            await pg.update_collector_inbox_status(
                message_id, run_id=run_id, parse_status="running",
            )
        try:
            await build_graph(cfg.graph_cfg).ainvoke(
                {
                    "run_id": str(run_id),
                    "date": meta.date,
                    "input_files": [str(attachment_path)],
                    "site_id": meta_site_id,  # project → site_id lookup 결과
                    # ... (CPIAState 의 다른 필드는 graph 내부 default)
                },
                config={"configurable": {"thread_id": str(run_id)}},
            )
            async with PGClient(cfg.postgres_url) as pg:
                await pg.update_collector_inbox_status(message_id, parse_status="completed")
        except Exception as e:
            log.exception("graph failed for %s", attachment_path)
            async with PGClient(cfg.postgres_url) as pg:
                await pg.update_collector_inbox_status(
                    message_id, parse_status="failed", error=str(e)[:1000],
                )
            raise
```

`_GRAPH_SEM` 으로 동시 graph N=2 제한 — Azure OpenAI rate-limit 회피.

### 6.4 dedup + 메일 처리

```python
async def _drain_new(imap: aioimaplib.IMAP4_SSL, cfg: CollectorConfig) -> None:
    typ, data = await imap.search("UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return
    for uid_bytes in data[0].split():
        await _process_one(imap, uid_bytes.decode(), cfg)

async def _process_one(imap, uid: str, cfg: CollectorConfig) -> None:
    typ, data = await imap.fetch(uid, "(RFC822)")
    if typ != "OK":
        return
    raw = data[1]
    msg = email.message_from_bytes(raw)
    message_id = msg.get("Message-ID")
    if not message_id:
        log.warning("uid=%s 헤더 Message-ID 없음, skip", uid); return
    # dedup PG 체크 (PRIMARY KEY 위반은 INSERT 시점에 잡아도 됨)
    async with PGClient(cfg.postgres_url) as pg:
        if await pg.fetch_collector_inbox_by_message_id(message_id):
            log.info("dedup skip: %s", message_id)
            await imap.store(uid, "+FLAGS", "\\Seen")
            return
    attachments = _extract_attachments(msg)
    if not attachments:
        log.info("no attachment: %s", message_id)
        await imap.store(uid, "+FLAGS", "\\Seen")
        return
    for att_name, att_bytes in attachments:
        meta = parse_filename(att_name)
        if meta is None:
            await _to_dead_letter(att_name, att_bytes, cfg)
            continue
        site_id = await _resolve_site_id(meta.project, cfg)
        if site_id is None:
            await _to_dead_letter(att_name, att_bytes, cfg)
            continue
        path = _save_to_input_dir(att_name, att_bytes, meta.date, cfg)
        async with PGClient(cfg.postgres_url) as pg:
            await pg.insert_collector_inbox(
                message_id=f"{message_id}#{att_name}",  # 1 메일 N 첨부 dedup
                site_id=site_id, report_date=meta.date,
                bp_name=meta.bp_name or "_integrated",
                attachment_filename=att_name, attachment_path=str(path),
            )
        asyncio.create_task(
            run_for_attachment(path, meta._replace_site(site_id), f"{message_id}#{att_name}", cfg)
        )
    await imap.store(uid, "+FLAGS", "\\Seen")
    await _add_gmail_label(imap, uid, "cpia-processed")
```

핵심 룰:
- **dedup key = `Message-ID#attachment_filename`** (1 메일 N 첨부에서 각 첨부 독립 추적)
- IDLE 가 재연결 후 같은 메일 재알릴 가능성 → `UNSEEN` + collector_inbox dedup 2중 보호
- `\Seen` flag + `cpia-processed` label 부여 — 운영 가시성

---

## 7. Exporter 내부 구현 (Section 4)

### 7.1 PG SELECT (web BFF 와 동일 의미론)

```python
# pipeline/agents/exporter.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date as _date
from io import BytesIO
from pathlib import Path
from openpyxl import load_workbook

@dataclass
class SheetData:
    output_manpower: list[dict]      # 시트1: BPSummary jsonb 누적
    occupation_manpower: list[dict]  # 시트2: parser_job_allocations
    equipment: list[dict]             # 시트3: parser_equipment_allocations
    quantity: list[dict]              # 시트4: parser_activities

class NoDataError(Exception): pass


async def fetch_sheet_data(
    pg: PGClient,
    site_id: str,
    report_date: _date,
) -> SheetData:
    """같은 (site_id, report_date) 의 모든 run = 모든 업체 메일을 합집합."""
    bp_rows = await pg.fetch_all(
        """
        SELECT jsonb_array_elements(bp_summaries) AS row
        FROM parser_reports
        WHERE site_id = $1 AND report_date = $2
        """,
        site_id, report_date,
    )
    job_rows = await pg.fetch_all(
        """
        SELECT * FROM parser_job_allocations
        WHERE site_id = $1 AND report_date = $2
        ORDER BY id
        """,
        site_id, report_date,
    )
    eq_rows = await pg.fetch_all(
        "SELECT * FROM parser_equipment_allocations WHERE site_id=$1 AND report_date=$2 ORDER BY id",
        site_id, report_date,
    )
    act_rows = await pg.fetch_all(
        "SELECT * FROM parser_activities WHERE site_id=$1 AND report_date=$2 ORDER BY id",
        site_id, report_date,
    )
    if not (bp_rows or job_rows or eq_rows or act_rows):
        raise NoDataError(f"({site_id}, {report_date}) 데이터 없음")
    return SheetData(
        output_manpower=[r["row"] for r in bp_rows],
        occupation_manpower=[dict(r) for r in job_rows],
        equipment=[dict(r) for r in eq_rows],
        quantity=[dict(r) for r in act_rows],
    )
```

### 7.2 템플릿 fill (openpyxl)

`docs/sample/통합작업일보_DUMMY_20250926.xlsx` 를 `pipeline/agents/exporter_templates/consolidated_template.xlsx` 로 복사 + git add. 헤더 (r1~r4) / 셀 병합 / 스타일 보존, 데이터 r5 부터 채움:

```python
TEMPLATE_PATH = Path(__file__).parent / "exporter_templates" / "consolidated_template.xlsx"
DATA_START_ROW = 5

def render_xlsx(sheet_data: SheetData, report_date: _date, project: str) -> bytes:
    wb = load_workbook(TEMPLATE_PATH)
    _fill_output_manpower(wb["1.출력인원 현황"], sheet_data.output_manpower, report_date)
    _fill_occupation(wb["2.직종별 인원현황"], sheet_data.occupation_manpower, report_date)
    _fill_equipment(wb["3.장비현황"], sheet_data.equipment, report_date)
    _fill_quantity(wb["4.물량"], sheet_data.quantity, report_date)
    buf = BytesIO(); wb.save(buf); return buf.getvalue()


def _fill_output_manpower(ws, rows: list[dict], report_date: _date) -> None:
    # B2 헤더: 금일 작업 현황 : {report_date}, 요일
    ws["B2"].value = f"금일 작업 현황 : {report_date.isoformat()}, {_korean_weekday(report_date)}"
    # r5 부터 BPSummary row 매핑
    # 컬럼 (1-based): B=Zone, C=공종, D=BP, E=Scope, F=전일작업, G=금일, H=명일,
    #                 I~N = 전일투입 6 (조출/주간/연장/야간/철야/Total),
    #                 P~U = 전일누적 6, W~AB = 금일투입 6, AD~AI = 금일누적 6
    for offset, bp in enumerate(rows):
        r = DATA_START_ROW + offset
        ws.cell(row=r, column=2, value=bp.get("zone"))
        ws.cell(row=r, column=3, value=bp.get("disc_abbrev"))
        ws.cell(row=r, column=4, value=bp.get("bp_code"))
        ws.cell(row=r, column=5, value=bp.get("company"))
        ws.cell(row=r, column=6, value=bp.get("scope"))
        ws.cell(row=r, column=7, value=bp.get("work_text_yesterday"))
        ws.cell(row=r, column=8, value=bp.get("work_text_today"))
        ws.cell(row=r, column=9, value=bp.get("work_text_tomorrow"))
        _fill_timeshift(ws, r, 10, bp.get("workers_yesterday_incr"))  # I~N
        _fill_timeshift(ws, r, 17, bp.get("workers_yesterday_cum"))   # P~U
        _fill_timeshift(ws, r, 24, bp.get("workers_today_incr"))      # W~AB
        _fill_timeshift(ws, r, 31, bp.get("workers_today_cum"))       # AD~AI

def _fill_timeshift(ws, row: int, col_start: int, ts: dict | None) -> None:
    if not ts: return
    for i, key in enumerate(["morning", "daytime", "overtime", "night", "all_night", "total"]):
        ws.cell(row=row, column=col_start + i, value=ts.get(key, 0))

# _fill_occupation / _fill_equipment / _fill_quantity 동일 패턴
```

**정확한 컬럼 매핑** (시트2/3/4) 은 implementation 단계 (writing-plans) 에서 dummy xlsx 의 r3~r5 헤더를 한 셀 한 셀 확인 후 dict 로 fix. 본 spec 에선 의도만 명시.

### 7.3 FastAPI endpoint

```python
# pipeline/exporter_routes.py
from __future__ import annotations
import os
from datetime import date as _date
from fastapi import APIRouter, HTTPException, Response

from pipeline.agents.exporter import fetch_sheet_data, render_xlsx, NoDataError
from pipeline.db import PGClient, fetch_site_by_id

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/run")
async def export_consolidated(site_id: str, date: str) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    async with PGClient(os.environ["POSTGRES_URL"]) as pg:
        site = await fetch_site_by_id(pg, site_id)
        if not site:
            raise HTTPException(404, f"site_id={site_id} 없음")
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError as e:
            raise HTTPException(400, str(e))

    xlsx_bytes = render_xlsx(data, report_date, project=site["project_code"])
    filename = f"통합작업일보_{date}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

### 7.4 UI swap (B_Track 1 줄)

`web/app/components/export/ConsolidatedReportCard.tsx:46~50` 의 fallback (setTimeout + a.href = "/sample/...") 을 다음으로 교체 (B_Track 작업):

```typescript
const res = await fetch(
  `${process.env.NEXT_PUBLIC_FASTAPI_BASE}/export/run?site_id=${siteId}&date=${report.date}`
);
if (!res.ok) throw new Error(await res.text());
const blob = await res.blob();
const a = document.createElement("a");
a.href = URL.createObjectURL(blob);
a.download = `통합작업일보_${report.date}.xlsx`;
a.click();
```

(BFF proxy 옵션: Next.js `/api/export/[date]/route.ts` 가 FastAPI fetch + stream pipe. CORS / 인증 통일에 유리. PoC 에선 직접 fetch 도 가능.)

### 7.5 캐싱 정책

PoC 단순화: **캐싱 안 함**. 매 호출 PG SELECT + render. xlsx ~150KB 양식이라 100ms 이내 응답 예상. 데모 사용량 분당 1~2 클릭 수준에 cache 불필요.

---

## 8. 테스트 + 환경 (Section 5)

### 8.1 테스트 전략

| 컴포넌트 | 단위 테스트 | 통합 테스트 |
|---|---|---|
| `filename_parser.py` | parametrize: 업체별 5종 + 통합 2종 + 깨진 5종 (bp 공백 / 이상 date / 확장자 / 토큰 부족 등) | — |
| `idle_worker.py` | aioimaplib `IMAP4` mock 으로 `EXISTS` 시그널 주입 → fetch + dedup 동작 검증 | `tests/test_collector_e2e.py`: 임시 mailbox fake → 첨부 보냄 → graph stub 호출 검증 (LLM mock) |
| `exporter.render_xlsx` | 가짜 SheetData → openpyxl load 결과 시트별 cell 값 + 헤더 보존 검증 | — |
| `exporter.fetch_sheet_data` | — | PG fixture (testcontainers) → parser_* row INSERT → SELECT 결과 row 수 + 필드 검증 |
| `/export/run` endpoint | `httpx.AsyncClient` + FastAPI app → 200 + Content-Type xlsx + BytesIO 로 재 load + 시트 검증 | — |

**드라이 테스트 룰** (사용자 memory `feedback_dry_test.md` 적용): Exporter 통합 테스트는 LLM bypass — PG 의 `parser_*` row 를 fixture 로 박고 결정론적 렌더링만 검증. Collector E2E 도 graph 호출은 stub.

### 8.2 환경 변수 (`.env` 추가)

```bash
# Collector
COLLECTOR_ENABLED=true                       # 로컬 / 테스트 환경은 false 로 끄기
COLLECTOR_IMAP_HOST=imap.gmail.com
COLLECTOR_IMAP_PORT=993
COLLECTOR_IMAP_USER=cpia-collector@gmail.com
COLLECTOR_IMAP_APP_PASSWORD=<16자 Gmail app password>
COLLECTOR_DEFAULT_SITE_ID=m15x-ph3-ibl       # PoC 단일 site fallback
COLLECTOR_INPUT_DIR=data/input
COLLECTOR_DEAD_LETTER_DIR=data/input/dead_letter
CPIA_COLLECTOR_CONCURRENCY=2

# Exporter
EXPORTER_TEMPLATE_PATH=pipeline/agents/exporter_templates/consolidated_template.xlsx
```

데모용 Gmail 계정 발급 절차:
1. cpia-collector@gmail.com (또는 유사) 신규 가입
2. 2FA 활성화
3. App Password 발급 (Google Account → Security → 2-Step Verification → App passwords → "Mail" 16자)
4. IMAP enable (Gmail 설정 → 전달 및 POP/IMAP → IMAP 사용)
5. `.env.local` 에 `COLLECTOR_IMAP_APP_PASSWORD=<16자>` 박기

### 8.3 PoC 일정 (D-17, 5/19~6/5)

| 주차 | 작업 |
|---|---|
| W1 (5/19~5/25) | filename_parser 단위 테스트 → idle_worker 골조 + Gmail 데모 계정 생성 → `collector_inbox` 마이그레이션 + db.py helper 3종 |
| W2 (5/26~6/1) | exporter render + SELECT + endpoint + 통합 테스트. B_Track UI swap (BFF proxy 또는 직접 fetch) 협업 |
| W3 (6/2~6/5) | 데모 시나리오 리허설 — PM → 메일 → 즉시 처리 → Export 다운로드 풀 사이클. dead_letter / 에러 케이스 확인. |

---

## 9. 다른 세션 충돌 회피 — Final

본 cycle 작성 시점 (5/19 19:00) 에 다른 세션이 진행 중인 영역: parser_llm / parser_post / mapper / atomizer / forecaster / optimizer / reporter (테스트 + 미세 fix).

### 9.1 절대 안 건드림 (read-only)

- `pipeline/state.py`
- `pipeline/graph.py`
- `pipeline/checkpointer.py`
- `pipeline/chroma_client.py`
- `pipeline/agents/parser.py`
- `pipeline/agents/parser_llm.py`
- `pipeline/agents/parser_post.py`
- `pipeline/agents/mapper.py`
- `pipeline/agents/atomizer.py`
- `pipeline/agents/forecaster/` (디렉토리 전체)
- `pipeline/agents/optimizer/` (디렉토리 전체)
- `pipeline/agents/reporter.py`

### 9.2 신규 only (충돌 0)

- `pipeline/collector/__init__.py`
- `pipeline/collector/idle_worker.py`
- `pipeline/collector/filename_parser.py`
- `pipeline/agents/exporter.py`
- `pipeline/agents/exporter_templates/consolidated_template.xlsx`
- `pipeline/exporter_routes.py`
- `infra/postgres/migrations/<next>_collector_inbox.sql`
- `pipeline/tests/test_filename_parser.py`
- `pipeline/tests/test_idle_worker.py`
- `pipeline/tests/test_exporter_render.py`
- `pipeline/tests/test_exporter_endpoint.py`
- `pipeline/tests/test_collector_e2e.py`

### 9.3 충돌 가능 (변경 라인 최소)

- `pipeline/api.py` — startup hook + shutdown hook + `include_router` = **총 3줄 추가**, 기존 endpoint 변경 0
- `pipeline/db.py` — 신규 helper 4개 (`insert_collector_inbox`, `update_collector_inbox_status`, `fetch_collector_inbox_by_message_id`, `fetch_site_by_project_code`) 추가만. 기존 helper 변경 0

### 9.4 머지 순서

1. 다른 세션의 parser~optimizer 작업 PR 머지 대기
2. 본 cycle PR rebase
3. `api.py` 충돌은 끼워넣기로 수동 해결 (3줄)
4. CI green 후 머지

---

## 10. Open questions (implementation 단계에서 결정)

- 데모용 Gmail 계정의 정확한 주소 (cpia-collector@gmail.com 가용 여부)
- B_Track 의 UI swap 방식: Next.js BFF proxy vs FastAPI 직접 fetch (CORS / NEXT_PUBLIC_FASTAPI_BASE 환경 변수 노출 정책)
- `project → site_id` lookup: `sites.project_code` 컬럼 신설 필요 여부 (현 schema 확인 후 결정)
- dead_letter 누적 시 운영자 알림 — 후속 cycle (PoC 외)

---

## 11. Next step

1. spec-document-reviewer subagent 디스패치 → 이슈 반영 (max 3 iter)
2. 사용자 spec 리뷰 게이트
3. `superpowers:writing-plans` 스킬 전환 → implementation plan 산출 (`docs/superpowers/specs/2026-05-19-cpia-collector-exporter-plan.md`)
4. plan 실행 — W1 작업부터 (filename_parser → collector_inbox 마이그레이션 → idle_worker → exporter)
