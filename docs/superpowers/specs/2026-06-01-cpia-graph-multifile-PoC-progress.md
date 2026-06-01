# CPIA graph multi-file 연결 — 진행 상황 / PoC (2026-06-01)

> compact 대비 영속화. fresh agent 는 이 문서 + `git status` + `git log --oneline -10` 으로 상태 복원.

---
## ★ UPDATE (2026-06-01 오후) — graph multi-file 라이브 검증 + hil_1 resume 버그 fix + FE-BE 승인 배선

**라이브 PoC 성공**: tasks 화면 업로드 경로(`/api/upload`→FastAPI `/run`)로 10개 업체파일 → **parser merge 330 → mapper 330(요검토 80) → hil_1 → (승인) → atomizer→exporter‖forecaster→hil_2→optimizer→reporter 완주(8단계 100%)**. 실 그래프+실 UI 백엔드로 확인. uvicorn pid 가변(현재 86447, `CPIA_MAPPER_CONCURRENCY=8`, AUTO_BYPASS off, `--env-file .env`). 웹 dev 서버 `localhost:5537`(npm dev, HMR). DB 터널 안정(connect 0.05s).

**고친 버그 (커밋 안 함, working tree):**
1. `pipeline/graph.py:_parser_p` — async `parser_node` 를 await 없이 호출하던 것 `return await _parser(state)` 로 수정 (이전 좀비 원인).
2. **hil_1 resume 영구 갇힘 (langgraph 1.2.0)** — `Command(resume=<falsy>)`(빈 보정 `{}`)는 전달 안 돼 interrupt 재발생. fix: `api.py` 가 항상 truthy 래퍼 `{"corrections": {...}}` 로 resume, `graph.py:hil_1_node` 가 언랩(`set(keys)=={"corrections"}`). harness 결정론 검증 그린(빈/non-empty 둘 다 reporter 완주, mapping_source=user_corrected 적용 확인). 재현/검증 스크립트 `/tmp/cpia_test_resume.py`·`/tmp/cpia_test_minimal_resume.py`.

**FE-BE 승인 배선 (web, HMR — 디자인 markup 보존, 핸들러/데이터만):**
- 신설 `web/app/api/hil/resume/route.ts` — waiting_hil_1 run 자동 선택 → FastAPI resume 프록시.
- `web/app/(app)/review/page.tsx` — "모두 AI 추천대로 확정" = **게이트**(미확정 전체 확정 = 하나도 빠짐없이 처리 후 진행) + **수정 반영**(remap 한 카드만 `{idx:{wa,l6_main}}` corrections 전송, 나머지 AI 수용). `wpIdToWaL6` 룩업으로 wp_id→wa/l6_main 역매핑.
- `web/app/api/mock/review/route.ts` — `AND pr.status='waiting_hil_1'` 추가(완료 run stale 카드 제외) + 카드에 `idx/wa/l6_main`.
- `web/lib/types.ts`(ReviewItem +idx/wa/l6_main/remapped, WBSNode +wa/l6_main), `web/lib/transforms.ts`(work_package 노드 +wa/l6_main).

**남은 것 / 주의:**
- exporter `render_xlsx` 가 `MergedCell value read-only`(openpyxl) 로 예외 → exporter 가 catch+silent skip(설계상 multi-end fault isolation 회피). consolidated 미생성. 사용자 "exporter 냅두라" 범위라 보류.
- hil_1_node 가 mapper_activities.requires_review 를 DB 에 false 로 안 박음(state 만). review 화면은 status 필터로 회피 중. 필요 시 hil_1_node 에 upsert 추가(테스트 영향 점검 필요 — test_api_hil1_resume 는 graph mock 이라 무관, test_graph_e2e_hil1 확인).
- web 변경은 전부 미커밋(A_Track 은 pipeline/ 만; web 은 B_Track). 머지/커밋은 사용자 지시 대기.
- 현재 데모용 run: `data/input/20250925/` 10개(동일 템플릿 placeholder, 전부 company=중원엔지니어링 → merge 330). 실데이터 교체 예정.
---

## 1. 완료 — parser 헤더기반 다포맷 7태스크 (A_Track, **origin push 됨**)

커밋 `65a8027`(T1 날짜regex) → `7d2befc`(T2 BP다중패턴) → `25bb85d`(T3 시트4 헤더해석) → `c8032e4`(T4 시트1가드) → `c0699dc`(T5 final_flag 완화) → `ac0a8c5`(T6 LLM제거+업체E2E골든) → `bf72e90`(T7 통합골든) → `5b63e3b`(주석정리). `origin/A_Track` push 완료.

- issue #52(컬럼시프트 garbage) 해소. 통합 byte-identical(1193/99/975/1111), 업체 골든 33/1/76/68.
- 실 업로드 E2E 로 collector→parser→mapper→hil_1 검증 완료(당시 run 들은 삭제됨).
- **머지 보류 중**: 사용자가 "graph multi-file 먼저 연결 후 main 직접 머지" 선택 → 아래 작업 후 머지.

## 2. 진행 중 — graph multi-file 연결 (brainstorming → PoC)

### 설계 (사용자 승인 완료)
- **parser_node 만** `input_files` 전체 N개 파싱 + **concat merge** → 1 통합 `ParsedDailyReport` → 1 run.
- mapper/atomizer/forecaster/optimizer/reporter/exporter, hil_1 **전부 무변경** → optimizer 가 통합 데이터 진단, exporter 가 통합 xlsx(기존 로직 재사용, 재구현 X).
- merge = **concat** (각 업체 다른 데이터, 곧 실데이터 교체 — 현 demo_inputs 10개는 동일 템플릿 placeholder).
- 사용자 핵심 의도: "parser 에 10개 넣으면 optimizer 까지 끝까지 도는지 + optimizer 는 통합 검토". DB 적재됨(mapper insert, 330행).

### PoC 코드 (작업트리, **미커밋**)
- `pipeline/agents/parser_node.py` → **async** `parser_node` + `asyncio.to_thread` gather(Semaphore 4) + `_merge_reports`(concat). 원래는 sync 1줄 래퍼(`input_files[0]`)였음.
- 정식화 시 이 파일 기반으로 spec/plan 작성 → subagent-driven 구현 → 커밋.

### PoC 결과 (실측)
- ✅ parser merge → **330/760/680 DB 적재 확인** (parser_activities 330, job 760, equip 680, mapper_activities 330). run aa7cbb66.
- ✅ collector→parser→mapper→hil_1 도달 (waiting_hil_1, error=None).
- ⚠️ **mapper 330개 ≈ 5분** — `map_activity` 가 activity당 Azure 임베딩1+rerank1(동시성4). 데모 병목. 정식: 동시성↑ 또는 동일 (company,work_content) 매핑 캐싱(동일 데이터면 10배 단축).
- ⚠️ **parser_node sync 가 8000 이벤트루프 블록** — 원래 sync 가 10개 순차 파싱(~30-50초) 동안 FastAPI 전체 hang → web 로딩 멈춤. **PoC 에서 async 로 고침**(위 코드).
- ⚠️ **hil_1 resume 버그** — `/api/runs/{id}/hil_1/resume` 가 `next_node:mapper` 반환 + status 안 풀림(재개 실패). multi-file 무관, 공통. 우회: uvicorn 에 `CPIA_HIL_AUTO_BYPASS=1` (graph.py:239,245,255 — hil_1 interrupt 건너뜀). **review 화면 보려면 off**.
- ⚠️ **route.ts timeout** — `web/app/api/upload/route.ts` 의 `triggerPipeline` `AbortSignal.timeout(5000)` < `/run` 실측 6.4초 → 업로드 시 run_id null(게이지는 DB polling 으로 작동). 정식: timeout 늘리거나 /run 즉시반환 보장.

## 3. 환경 상태 (compact 시점)

- **uvicorn 8000 전부 정리됨(kill)**. 재시작: `cd "/Users/kyungseoplee/Project Agent/CPIA" && nohup pipeline/.venv/bin/uvicorn pipeline.api:app --port 8000 --env-file .env > /tmp/cpia_uvicorn.log 2>&1 &` (AUTO_BYPASS 미설정=hil 활성/review 뜸).
- 🔴 **DB 터널 불안정** — `ssh 7559`(colima ssh mux, 5532 forward → homelab `43.200.85.209:5532/cpia`). TCP 5532 OK 인데 PG 핸드셰이크 간헐 `TimeoutError`. 내 반복 connect 부하(uvicorn 다회 -9 kill + 폴링) 추정. connection 은 5/100(고갈 아님). **compact 후 첫 과제: DB connect 안정화 확인** (`asyncpg.connect` 성공할 때까지). 안 되면 colima/터널 점검(사용자).
- 25일(2025-09-25) run 대부분 삭제(parser_activities 759 등). `e8fbe85a`(parser 중 중단) **잔여 가능** — `/tmp/cleanup_0925.py`(report_date=2025-09-25 전체 삭제, autocommit) 재실행으로 정리.
- `data/input/20250925/` 에 업체 10개 있음(업로드됨). `data/` 는 gitignore.
- `git stash@{0}` = 남의 변경(Makefile + report-ui design/plan, `feature/report-ui-tweaks` worktree `cpia-reports-wt` 에 이미 커밋된 **중복**). drop 가능. `stash@{1}`(wip)은 건드리지 말 것.
- Playwright MCP 브라우저는 다른 세션(cpia-reports-wt)이 점유(`mcp-chrome-for-testing-8237e32`, ssh 29973 alive) → 내 Playwright navigate 막힘. 사용자가 "꺼진 playwright 종료 OK" 했으나 29973 은 active.

## 4. 다음 단계 (순서)

1. **DB 터널 안정화** — `asyncpg.connect` 성공 확인. 안정 후 진행.
2. uvicorn 재시작(async parser_node, AUTO_BYPASS off) + `/tmp/cleanup_0925.py` 로 25일 잔여 정리 + `/api/tasks` 응답 정상(블록 해소) 확인.
3. `/run` 직접 트리거 → async parser merge(330, 블록 없음) → mapper(~5분) → hil_1.
4. 사용자가 web(5537) review 화면에서 **직접 승인** (단 hil_1 resume 버그 가능 — 막히면 그 버그부터).
5. optimizer 까지 완주 확인(= 사용자 질문 "끝까지 도는지").
6. 작동 확인 → graph multi-file 정식 spec/plan → subagent-driven 구현 → 커밋 → main 직접 머지(사용자 지시).
7. 별도 이슈 정리: mapper 동시성/캐싱, hil_1 resume, route.ts timeout.

## 5. 사용자 하드룰 (유지)
한자 금지 / 디자인 불가침(FE layout 변경 X, BE/데이터만) / main 머지는 사용자(조형준 프로 PR이 원칙이나 이번 건 사용자가 직접 머지 지시) / git history 조작(rebase/amend/reset/stash) subagent 금지 / 실 검증 후 "완료".
