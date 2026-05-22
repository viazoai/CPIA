# Collector + Exporter Follow-ups

> 2026-05-22 — 본 사이클 (Task 0~11, commit `5347966..56bcaee`) 의 reviewer 들이 발견한 비차단 issue 모음. 별 cycle / 별 PR 로 처리 후보.

본 문서는 **PR 본문 / 다음 cycle 기획 시 참조용**. 코드 변경은 포함하지 않음.

---

## FU-1 (Task 1): `parse_filename` token strip 일관성 + 날짜 의미론 검증

**현 상태:** `pipeline/collector/filename_parser.py:parse_filename` 은 `bp_name` 만 `.strip()` 호출 (실 sample `_ 중원엔지니어링_` 선행 공백 처리용). 나머지 `trade`, `zone`, `project` 토큰은 raw 그대로. 또한 6/8-digit 숫자 검증만 — `99-99` 같이 의미론적으로 잘못된 날짜도 통과.

**위험:** 
- 다른 업체가 ` UT배관공사_FAB ` 류 공백 박힌 파일명 보내면 trade/zone 매칭 실패. 사용자가 인지 못함.
- `99999_99` (6-digit 통과 후 `2099-99-99`) 가 PG date 컬럼 INSERT 시 invalid 일 가능성 (실 데이터 들어와 봐야 확인).

**제안 fix (별 PR):**
1. 모든 token 에 `.strip()` 적용 (또는 정규식으로 surrounding whitespace 한 번 제거)
2. `date.fromisoformat(...)` try/except 로 의미론 검증 — invalid 시 None 반환 (호출자 dead_letter 처리)

**우선순위:** 낮음 (실 데이터에서 발생 시 dead_letter 로 가서 알아챌 수 있음). PoC 데모 후 처리.

---

## FU-2 (Task 1): `CPIAState.parsed` 타입 어노테이션 drift

**현 상태:** `pipeline/state.py:237` 는 `parsed: list[Activity]` 어노테이션. 그러나 mapper (`pipeline/graph.py:62`) 는 `parsed: ParsedDailyReport = state["parsed"]` 로 사용 — 실제 runtime 은 `ParsedDailyReport` (dict). 어노테이션과 실 사용 간 type drift.

**원인:** D-12 이전 외부 invoke 가 직접 `state["parsed"]` 에 ParsedDailyReport dict 박았던 흔적. 어노테이션이 갱신 안 됨.

**제안 fix:** state.py:237 의 `parsed: list[Activity]` → `parsed: ParsedDailyReport` 로 갱신. mapper / atomizer 의 type cast 코드도 정리 가능.

**우선순위:** 낮음 (runtime 동작 무관 — 단지 mypy / pyright hint 정확도). 사용 가능한 type 검사 도구 도입 시 함께 처리.

---

## FU-3 (Task 7): 시트 1 의 unlabeled "final-total" cells

**현 상태:** `pipeline/agents/exporter.py:_fill_output_manpower` 가 시트 1 의 시간대별 인원 timeshift 블록 6 cells (morning..total at col_start..col_start+5) 만 채움. 실 sample 의 r5 에는 col 16/23/30/37 위치에 추가 final-total 값이 박혀있으나 r4 헤더 라벨이 없음.

**위험:** Exporter 산출 xlsx 의 시트 1 r5 의 final-total 열들이 비어있는 채로 다운로드. PM 이 합산 셀 비었다고 인지할 가능성.

**제안 fix (별 PR):**
1. 실 sample 의 col 16/23/30/37 의 의미 파악 (parser 와 협의)
2. ParsedDailyReport.bp_summaries 에 해당 키 (e.g., `workers_*_total_final`) 추가
3. `_fill_output_manpower` 에 7번째 cell 채우기

**우선순위:** 중간 (시각적으로 비어 보이지만 합산 셀 자체는 수식 또는 후속 fill 로 가능 — 일단 demo 시점 확인 후 결정).

---

## FU-4 (Task 8): `/export/run` Content-Disposition RFC 5987

**현 상태:** `pipeline/exporter_routes.py:45-46` 가 raw_headers 에 UTF-8 bytes 로 `content-disposition` 박음. Starlette 의 latin-1 enforcement 우회. httpx 0.28 + 현대 브라우저 (Chrome / Firefox) 는 raw UTF-8 받아 한글 파일명 디코딩 OK.

**위험:**
- Starlette 가 향후 버전에서 `raw_headers` 도 latin-1 validation 도입 시 silent breakage
- RFC 7230 표준상 ISO-8859-1 — 비표준 클라이언트는 깨질 수 있음

**제안 fix (별 PR):**
1. RFC 5987 표준 형식 사용: `filename="report_2025-09-25.xlsx"; filename*=UTF-8''%ED%86%B5%ED%95%A9%EC%9E%91%EC%97%85%EC%9D%BC%EB%B3%B4_2025-09-25.xlsx`
2. `pipeline/tests/test_exporter_endpoint.py::test_export_run_returns_xlsx` 의 assertion 갱신 — `urllib.parse.unquote(cd)` 후 한글 substring 검증

**우선순위:** 낮음 (PoC 데모 OK). main 머지 전 정리 권장.

---

## FU-5 (Task 8 / 환경): `.env.example` 의 기존 secret 노출

**현 상태:** `pipeline/.env.example` (git 추적) 에 Azure API key / Cloudflared token / Postgres password 가 평문으로 박힘. git history 에도 노출.

**위험:** 공개 fork 시 즉시 누출.

**제안 fix (별 cycle, urgent):**
1. 위 3개 secret 즉시 rotate
2. `.env.example` 의 모든 secret line 을 empty placeholder 로 교체
3. git history 정화: `git-filter-repo` 또는 `BFG` 로 노출된 commit 정리 (repo 재배포 필요)

**우선순위:** 보안상 즉시 처리해야 함. 본 cycle 범위 밖이지만 PR 머지 전 별 cycle 권장.

---

## FU-6 (Task 3): `_GRAPH_SEM` module-global concurrency limit

**현 상태:** `pipeline/collector/idle_worker.py:34` 의 `_GRAPH_SEM = asyncio.Semaphore(int(os.environ.get("CPIA_COLLECTOR_CONCURRENCY", "2")))` 가 모듈 import 시점에 평가. 이후 env 변경 무시.

**위험:** 단일 FastAPI 프로세스 운영 가정 깨질 시 (multi-worker uvicorn 등) 의도한 concurrency cap 미작동.

**제안 fix:** `_GRAPH_SEM` 을 `CollectorConfig` 에 옮기고 lifespan 에서 생성. multi-worker 면 Redis-backed semaphore 검토.

**우선순위:** 낮음 (PoC 는 single-worker FastAPI).

---

## FU-7 (Task 3): fire-and-forget 예외 안전망

**현 상태:** `idle_worker._process_one` 의 `create_task(run_for_attachment(...))` 이 fire-and-forget. `run_for_attachment` 내부에 try/except 있으나 향후 refactor 시 예외가 escape 하면 silent task 사망.

**제안 fix:** `task.add_done_callback(lambda t: t.exception() and log.exception("graph dispatch task failed", exc_info=t.exception()))` 한 줄 추가.

**우선순위:** 낮음.

---

## FU-8 (Task 5): consolidated_template.xlsx 의 style-marked empty rows

**현 상태:** openpyxl `delete_rows` 가 데이터 값은 제거했으나 styling metadata 가 r5+ 까지 그대로 — sheet 1/2/3 의 `max_row` 가 384/15311/12512.

**위험:** Exporter 의 render 로직은 `DATA_START_ROW = 5` 명시 인덱스 사용이라 영향 없음. 단 향후 누가 `for row in ws.iter_rows():` 패턴 도입 시 수 천 row scan.

**제안 fix:** 템플릿을 처음부터 재구성 (헤더만 있는 새 xlsx 만들기) — file size 도 117KB → 더 작아짐.

**우선순위:** 낮음.

---

## FU-9 (Task 9): 호스트 명 / IP unify

**현 상태:** Spec 본문에는 `cpia-pg.zoai.uk` 호스트명, 실 `.env` 의 POSTGRES_URL 은 IP `43.200.85.209:5532`. Cloudflare Tunnel 패턴이라 같은 인스턴스지만 docs 일관성 떨어짐.

**제안 fix:** Spec 의 호스트 표기를 `<POSTGRES_URL host>` 같은 placeholder 로 통일 — 또는 둘 다 명시 + "둘 다 동일 인스턴스" 주석.

**우선순위:** 낮음.

---

## 정리

| ID | 영역 | 우선순위 | 본 cycle 영향 |
|---|---|---|---|
| FU-1 | filename_parser | 낮음 | X — dead_letter 안전망 작동 중 |
| FU-2 | state.py type drift | 낮음 | X — runtime 무관 |
| FU-3 | exporter sheet1 final-total | 중간 | 데모 시각 확인 후 결정 |
| FU-4 | RFC 5987 Content-Disposition | 낮음 | X — 현 브라우저 호환 |
| FU-5 | .env.example secret | **보안 urgent** | 별 cycle 권장 |
| FU-6 | _GRAPH_SEM module-global | 낮음 | X — single worker |
| FU-7 | fire-and-forget exception | 낮음 | X — internal try/except 있음 |
| FU-8 | template empty rows | 낮음 | X — render 영향 0 |
| FU-9 | host/IP unify | 낮음 | X — docs 만 |

PoC 데모 (2026-06-05) 진행에 차단 issue 없음. FU-3 의 시트 1 final-total 만 데모 직전 시각 확인 권장.
