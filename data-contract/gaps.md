# CPIA FE↔BE Gaps — 2026-05-27 cycle

> **전수 재작성.** 이전 cycle 의 §A~§G 누적본 (310 줄, 2026-05-18 ~ 05-19) 폐기. 본 cycle 입력 =
> - `data-contract/frontend_catalog.md` (683 줄, 2026-05-27 cycle, FE 단독 이슈 11건)
> - `data-contract/backend_catalog.md` (1043 줄, 2026-05-26 cycle, BE 단독 이슈 21건)
> - `deep-dive/architecture_overview.md` (32 이슈 표)
> - 이전 `gaps.md` (~310 줄, 2026-05-22) 의 carried 결정 흡수.
>
> 마킹: ★ NEW = 본 cycle 신규 발견, ★ CHG = 이전 cycle 의 산식/의미 변경, (carried) = 이전 cycle 부터 미해소.
>
> 목적: 시연 마감 (2026-06-05 목) 이전에 **결정 게이트 §D** 의 사용자 결정 → BE/FE 구현 cycle 진입.
>
> 분류: **§A FE only** / **§B BE only** / **§C Mismatch** / **§D 결정 게이트** / **§E 본 cycle 핵심 변경 trace** / **§F mock 유지 영역** / **§G 메인 반환 요약**.

---

## §A. FE only — UI 가 쓰는데 BE 에 source 없음

> FE catalog §A.1 / §C 의 mock 하드코딩 / FE 단독 산출 / BE 가 채울 의도 없음 / 이전 cycle 결정으로 mock 영구. 합계 = **11 건** (★ NEW = 5, ★ CHG = 1, carried = 5).

### A-1. `ScenarioPoint.catch_up: {date, percent}` (★ NEW)

- **위치**: `web/lib/types.ts:293` (type 신규), `web/lib/diagnosis.ts:55~87 buildScenarioCurve` (FE 산출).
- **UI 영향**: ForecastChart 의 mint dashed catch-up 라인 + `baseCatchUp` ReferenceDot (`web/app/components/charts/ForecastChart.tsx:241~292`). plan 따라잡는 시점 시각화.
- **현재 동작**: FE diagnosis.ts 가 `buildScenarioCurve(s_curve, todayIdx, lastActual, recoveryDays)` 안에서 lastActual → plan[catchUpEndIdx] 직선 slope 산출. BE 산식 없음.
- **옵션**:
  - (1) FE 자체 산출 영구 유지 — FE-side 시각화 보조로 설계됨.
  - (2) BE 가 `scenarios.site.base_p50` 안에 catch-up 좌표 (date, percent) 같이 박기.
- **권고**: (1) — FE 시각화 보조 의도. 단 spec 명문화 필요 ("`catch_up` 은 FE diagnose() 가 채우는 derived field").
- **trade-off**: PoC 마감 vs 본질: (1) 0 LOC vs (2) BE +10 LOC. 본질 영향 없음.

### A-2. `ProductivityDiagnosis` 13 필드 (carried, D-3 REVISED)

- **위치**: `web/lib/types.ts:380~403` (13 field), `web/lib/diagnosis-adapter.ts:16 toDiagnosisInput()`.
- **UI 영향**: Reports `/reports` 전 진단 모델 — KPI strip, ForecastChart base line, recovery 표.
- **필드**: history_mean / history_std / sample_size / today_progress / productivity_score / gap_pct / z_score / status / s_curve / band_p25 / band_p75 / ewma_trend / recovery / scenarios (BE 가 적극 채우지 않음).
- **옵션**:
  - (1) FE diagnose() + diagnosis-adapter mock 영구 — D-3 REVISED 결정 (이전 cycle 권고).
  - (2) BE adapter — `forecasts.{rag_n_similar, today_productivity, similar_cases, ...} + optimizer_advice.{recovery_distribution} + sites.actual_progress` 를 ProductivityDiagnosis shape 으로 변환. ~150 LOC.
  - (3) BE 신규 Diagnosis agent — pipeline 단계 신설.
- **권고**: (1) — 이전 D-3 REVISED 유효. 6/5 마감 비용 (옵션 2 = ~150 LOC, 옵션 3 = ~300 LOC) > 효익. PoC 후 phase 2.
- **trade-off**: PoC 마감 vs 본질: (1) FE 가 진단 narrative 의 source-of-truth. 단 사용자가 "옵티마이저/포어케스터 연결" 강조 시 재논의 필요.

### A-3. `ChatMessage[]` (mock_chat_sequence.json + deriveChatSequence) (carried, D-4)

- **위치**: `web/lib/types.ts:104~108` (type), `data/mock_chat_sequence.json` (fixture 1 date × 8 msg), `web/lib/transforms.ts:326~411 deriveChatSequence(runId)` (PG 기반 derive).
- **UI 영향**: Home + Tasks 우측 chat 패널 (`AgentChatLog` h-720px, `useSequence` reveal 효과).
- **현재 동작**: `loadReal("chat_sequence")` (fixtures.ts:230) 가 최근 completed run → 8-msg ChatMessage 시퀀스 derive (Collector~Optimizer, off=0/30/60/.../210s). hil_count>0 면 Mapper type=hil_request + Human Review type=human_action 자동 추가.
- **옵션**:
  - (1) `deriveChatSequence(run_id)` PG 기반 8-msg 유지 — 현재 동작.
  - (2) BE event_log 테이블 + FastAPI stream (SSE) — 실 pipeline 이벤트 실시간 transport.
  - (3) Hybrid — DB INSERT trigger 기반 derive.
- **권고**: (1) — 이미 PG 기반 동작. 단 사용자 push back 시 (2/3) 으로 phase 2.
- **trade-off**: PoC 마감 vs 본질: (1) 0 LOC vs (2) BE +200 LOC + FE +50 LOC. 시연 시 chat narrative 의 신뢰도가 핵심 demo 이라 (1) 로도 충분.

### A-4. `AgentStatus` 정적 메타 6 필드 (carried, D-9)

- **위치**: `web/lib/types.ts:50~57`, `web/lib/fixtures.ts:178~215 loadReal("agent_status")` AGENT_META.
- **UI 영향**: Home AgentWorkflow 7 카드.
- **필드**: step (1..7) / name (Collector..Optimizer) / korean_name (수집..조언) / description / model ("gpt-5.1" / "Sonnet 4.6" / ...) / group ("collect" / "analyze").
- **현재 동작**: AGENT_META 7 종을 FE `loadReal()` 안에서 hardcode + PG `pipeline_runs.current_node` 매칭으로 active_count 만 PG 에서.
- **옵션**:
  - (1) FE hardcode + BE 가 active_count 만 (현재).
  - (2) BE FastAPI hardcode 반환 (D-9 권고 — 단일 source).
  - (3) DB `agent_meta` 테이블 신설.
- **권고**: (1) — 현재 동작. D-9 의 (2) 권고가 본질이지만 PoC 마감 후 phase 2.
- **trade-off**: PoC: 0 LOC vs (2) BE +50 LOC + FE -20 LOC. agent 추가 시 양쪽 동시 수정 필요는 5/5 마감 후 정리.

### A-5. `RecoveryEtaCard` dead 확정 — `delta_completion_days` 항상 0 (★ CHG)

- **위치**: `web/app/components/reports/RecoveryEtaCard.tsx:48 formatDelta` — 호출처 grep 0 건.
- **UI 영향**: (예전 의도) "+N 일 지연 / -N 일 단축" 표시 — 현재 의미 없음.
- **이유**: `web/lib/diagnosis.ts:138/145/152` 가 모든 시나리오 `delta_completion_days: 0` 고정 (catch-up + plan 동행 모델 도입). 산식 자체가 0 으로 fix 되면서 component 의 분기 (delta>0 → "지연", delta<0 → "단축") 가 무의미.
- **옵션**:
  - (1) component 삭제 + type field 도 제거.
  - (2) `delta_completion_days` 의미 복원 (catch-up 후에도 추가 지연 표시).
  - (3) component dead 표시 유지 (DEPRECATED 주석만).
- **권고**: (1) — catch-up + plan 동행 모델이 본 cycle 핵심 변경. 의미 손실로 dead.
- **trade-off**: dead code 가 코드베이스에 잔존하면 다음 cycle 에서 헷갈림. PoC 후 즉시 정리.

### A-6. HIL 단계 — 3 곳 하드코딩 (★ NEW HIL 부분 연결 미충족)

- **위치**:
  - `web/app/components/home/AgentWorkflow.tsx:54~62 HILS[0]` (afterStep:3, waiting:3, title "Mapping Review").
  - `web/app/components/NotificationBell.tsx:16 MOCK_NOTIFS` (3 건 — warning/danger/info).
  - `web/app/components/UserMenu.tsx:8 USERS` (2 명 — 김 현장 / 이 본부).
- **UI 영향**: Home AgentWorkflow HIL 카드 + 상단 알림 + 사용자 메뉴.
- **현재 동작**: BE 가 `sites_summary.review_pending` (이미 PG 에서 옴 — `loadReal("sites_summary")` 내부 line 119) 으로 HIL waiting 카운트 갖고 있으나 HILS[0] 가 `waiting: 3` 으로 hardcode.
- **옵션**:
  - (1) FE hardcode 영구 (PoC 단순).
  - (2) HIL 만 `summary.review_pending` 으로 동적 연결 (~5 LOC), notif/users 는 hardcode 유지.
  - (3) BE 신규 endpoint (`/api/notifications`, `/api/users`) 전체 연결.
- **권고**: (2) HIL 만 — BE 데이터가 이미 있는데 FE 가 안 씀 = 명백한 누락. notif/users 는 PoC scope 밖.
- **trade-off**: PoC: 5 LOC vs (3) ~100 LOC. HIL waiting 의 실 수치 노출이 demo narrative 강화.

### A-7. `ai_replacement_rate` 단위 미확정 — % vs 분수 (★ NEW)

- **위치**: `web/lib/types.ts:25` (Site.ai_replacement_rate), `web/lib/types.ts:42` (SitesSummary.ai_replacement_rate), `web/lib/fixtures.ts:160` (PG 분기 산식 `Math.round(... × 10000) / 100`), `pipeline/api.py:288` (`s.hours_saved / (s.headcount × 140) × 100`).
- **UI 영향**: Home OpsKpiCard "AI 대체율" + ImpactTab.
- **현재 산식**: BE = `(hours_saved / (headcount × 140)) × 100` → % 단위. FE = `${summary.ai_replacement_rate}` + `unit: "%"` → 일관.
- **위험**: BE 가 미래에 분수 (0.0346) 보내면 "0.0346%" 로 표시될 위험. contract 명문 없음.
- **옵션**:
  - (1) BE 가 % (3.46) 단위로 보장 (현재) + spec 명문화.
  - (2) BE 가 분수 (0.0346) 로 보내고 FE 가 × 100.
  - (3) UI assertion (FE 가 받은 값 < 2 면 × 100 정규화).
- **권고**: (1) + spec 명문화 — contract 부재가 본질 원인.
- **trade-off**: PoC: 1 줄 spec 추가 vs 본질: 향후 BE 산식 변경 시 사고 방지.

### A-8. `yearly_saving` PG=0 vs fixture=203 (억) — 토글 시 점프 (★ NEW)

- **위치**: `web/lib/fixtures.ts:172` (PG 분기, `yearly_saving: 0` hard-fix), `data/mock_sites_summary.json` (`yearly_saving: 203`), `web/lib/transforms.ts:30~36 deriveYearlySaving(fte, hours, hourlyRate=50000)` (G-11 산식, 호출처 0).
- **UI 영향**: Home OpsKpiCard "연간 환산 효과" 배너 — `CPIA_DEMO_FALLBACK` 토글 시 0 → 203 점프.
- **현재 동작**: PG 분기에서 `yearly_saving: 0` 으로 fix, fixture 는 203. `deriveYearlySaving` 산식이 transforms.ts 에 이미 존재하지만 호출 안 함.
- **옵션**:
  - (1) `loadReal("sites_summary")` 안에서 `deriveYearlySaving(total_fte_saved, total_hours_saved, 50000)` 호출 — 3 LOC.
  - (2) `sites.yearly_saving` 신규 컬럼.
  - (3) mock 값 fixture 와 동일하게 직접 박기 (`yearly_saving: 203`).
  - (4) UI 에서 0 이면 hide.
- **권고**: (1) — 산식 이미 존재, 호출만 추가.
- **trade-off**: PoC: 3 LOC. 단 단가 (50000 원/h) 가 G-11 spec 기본값 — 사용자 단가 결정 필요.

### A-9. `mock_simulation.json` shape ≠ `SimulationSequence` type (carried)

- **위치**: `data/mock_simulation.json` (key: home/tasks/report/dashboard) vs `web/lib/types.ts:259~261` (key: home_now_strip/agent_card_status/chat_log).
- **UI 영향**: 없음 — dead. `loadFixture("simulation")` 호출처 grep 0 건.
- **옵션**:
  - (1) fixture 삭제 + type 삭제 (둘 다 dead).
  - (2) shape 정합 후 부활 (의도된 컴포넌트가 없으면 의미 없음).
- **권고**: (1) — 다음 cycle 정리.
- **trade-off**: dead fixture 가 코드베이스에 잔존하면 헷갈림.

### A-10. `mock_dashboard.json` `impact.fleet_kpi` — required 필드 누락 (★ NEW)

- **위치**: `web/lib/types.ts:34~45` (SitesSummary required `total_processed` / `total_hours_saved_cum`), `data/mock_dashboard.json` impact.fleet_kpi (두 필드 누락).
- **UI 영향**: ImpactTab 가 직접 사용하지 않으나 (`yearly_saving` / `total_fte_saved` / `total_headcount` / `total_hours` / `total_hours_saved` / `ai_replacement_rate` 만 사용), 다른 곳에서 spread 시 undefined 가능 + TS strict 위반.
- **옵션**:
  - (1) fixture 에 두 필드 추가 (`total_processed: 0`, `total_hours_saved_cum: 0`).
  - (2) type 을 `Partial<SitesSummary>` 로 약화.
  - (3) ImpactTab 가 받는 type 분리 (`ImpactFleetKpi` 신설, 실 사용 필드만).
- **권고**: (3) — type 분리해서 실 사용 필드만 명시. 다른 곳에서 spread 위험 차단.
- **trade-off**: PoC: type 1 개 +5 LOC. 본질 해결.

### A-11. `dashboard/page.tsx` `endDate` prop 미전달 → 오늘 fallback (★ NEW)

- **위치**: `web/app/(app)/dashboard/page.tsx:41~48` (prop 안 보냄), `web/app/components/dashboard/PerformanceTab.tsx:18` (default `new Date().toISOString().slice(0,10)`).
- **UI 영향**: FleetProductivityTrendChart 의 시계열 마지막 5 일이 empty 가능 (PoC 데이터는 2026-05-22 까지, 오늘 2026-05-27 → 5 일 gap).
- **옵션**:
  - (1) page.tsx 에서 `dashboard.performance.fleet_trend[-1].date` 또는 최신 PG row 의 report_date 전달.
  - (2) PerformanceTab default 를 fleet_trend last date 로 변경.
- **권고**: (1) — page level 에서 명시 (~3 LOC).
- **trade-off**: PoC: 3 LOC. 시연 시 trend chart 가 비어있으면 demo 신뢰도 손상.

---

## §B. BE only — DB / agent 가 산출하는데 UI 가 안 씀

> backend_catalog §I (21 이슈) / §A.18 (실험) / §B (jsonb key) 에서 추출. 합계 = **9 건** (★ NEW = 5, carried = 4).

### B-1. `daily_reports.history_csv_row` — legacy summary (carried)

- **위치**: `infra/postgres/init.sql:39`, `pipeline/agents/reporter.py:107~112`.
- **의도**: (legacy) 4 키 dict (`total_workers / total_qty_by_trade / risk_counts / advice_count`). 컬럼명 ↔ 실 박힘 mismatch (이슈 #M-history_csv_row).
- **옵션**: (1) drop column (위험 — 다른 backfill 사용 가능성) (2) rename + spec 정리 (3) FE 노출 (markdown viewer 컴포넌트 신규).
- **권고**: (2) — drop 위험, rename + docstring 정리 backlog.

### B-2. `mapped_history_merge_log` (10 컬럼, debug) (★ NEW)

- **위치**: `infra/postgres/migrations/2026-05-21_phase1.sql:558`.
- **의도**: Phase 1 atomizer 합산 감사 로그 — FE 무관.
- **옵션**: (1) BE only 유지 (2) 운영자 페이지 (`/admin/merge-log`) 추가.
- **권고**: (1) — debug only.

### B-3. `prototype_embedding_cache` (4 컬럼, 실험) (★ NEW)

- **위치**: `infra/postgres/migrations/2026-05-21_phase1.sql:549`.
- **의도**: L7.5 임베딩 캐시 (외부 script `scripts/cache_*.py`) — FE 무관.
- **옵션**: (1) BE only 유지 (2) 실험 종료 후 drop.
- **권고**: (1) — 실험 cycle 중 유지.

### B-4. `parser_warning` stderr only, PG 미적재 (carried, #N25 backlog)

- **위치**: `pipeline/agents/parser.py` (stderr emit, PG INSERT 부재).
- **의도**: parser 가 cell off 발견 시 경고 — FE 무관.
- **옵션**: (1) PG `parser_warnings` 테이블 신설 + FE 운영자 페이지 (2) stderr only 유지.
- **권고**: (2) — 본 cycle scope 밖, backlog 유지.

### B-5. `mapper_activities.alternatives` JSONB 일부 키 (carried)

- **위치**: `infra/postgres/migrations/2026-05-19_mapper_alternatives.sql:352`, `web/app/components/review/ReviewCard.tsx:15` (FE dropdown 한정 사용).
- **의도**: mapper 가 rerank top-3 후보 저장 (`{wa, l6_main, score}`). FE 의 `alternative_wps` dropdown 한정 사용.
- **옵션**: (1) BE 전수 노출, FE 일부만 사용 (현재) (2) FE 가 dropdown 에 rerank score 노출 추가.
- **권고**: (1) — 현재 동작 OK. (2) 는 phase 2.

### B-6. `collector_inbox` 내부 dedup (10 컬럼) (★ NEW)

- **위치**: `infra/postgres/migrations/2026-05-19_collector_inbox.sql`, `pipeline/db.py:1149 insert_collector_inbox`.
- **의도**: Gmail IMAP IDLE 메시지 dedup — FE 무관.
- **옵션**: (1) BE only 유지 (2) FE 운영자 페이지 (메일 수집 상태).
- **권고**: (1) — internal infra.

### B-7. `daily_reports` 9 jsonb 중 일부 빈 dict — cold_start 시 (carried, #N4)

- **위치**: `pipeline/agents/optimizer/view_builder.py` (산식 부재 시 `{}`).
- **의도**: view_builder 가 cold_start 또는 데이터 부족 시 빈 dict 박음 — FE 가 OptimizerResult EMPTY fallback.
- **옵션**: (1) BE 가 빈 dict 대신 명시 `{source: "cold_start"}` (이미 부분 적용 — `optimizer_view_jsonb.by_wp[*].source` `view_builder.py:589`) (2) FE 가 EMPTY shape 강제.
- **권고**: (1) — 다른 jsonb (kpi/wp_summary/quadrant) 에도 source 키 확장.

### B-8. `forecasts` 잔여 19 컬럼 FE 미사용 (carried)

- **위치**: `infra/postgres/migrations/2026-05-16_*.sql` (28 컬럼 INSERT), FE 5 만 노출 (today_productivity / risk_level / expected_completion / delay_days / similar_cases).
- **의도**: forecaster 가 28 컬럼 INSERT 하지만 FE 는 5 만 노출.
- **옵션**: (1) endpoint 응답에서 미사용 19 drop (band-width 절약) (2) `/api/runs/:id/forecasts/raw` debug endpoint 분리 (3) 노출 유지.
- **권고**: (1) — endpoint 응답 drop.

### B-9. `optimizer_advice` 잔여 4 컬럼 FE 미사용 (carried)

- **위치**: `infra/postgres/init.sql:108~118` (9 컬럼), FE OptimizerOutput 은 5 만 노출 (wp_id / diagnosis / similar_cases / recommendations / details).
- **의도**: forecast_assessment 는 details 에 포함 가능, recovery_pattern 은 degradation_cases.recovery 와 중복.
- **옵션**: (1) forecast_assessment → details 포함 (2) recovery_pattern drop.
- **권고**: (1) + (2) — view_builder 가 이미 details 에 박음.

---

## §C. Mismatch — shape / 산식 / 단위 / 의미 다름

> 양쪽 다 있는데 정합 X. backend_catalog §I + frontend_catalog §A.1 enum/type + §E 의문점 결합. 합계 = **16 건** (★ NEW = 11, ★ CHG = 1, carried = 4).

### ★★ C-1. `daily_reports.site_summary_text` migration 부재 (Critical, #C1 / #N13)

- **FE 기대**: `ReportDetail.site_summary_text?: string \| null` (`web/lib/fixtures.ts:60`) — ForecastChart 의 `aiSummaryText` narrative (LLM 산출 200~300자 한국어 사이트 요약).
- **BE 실제**: commit `21c10f7` 가 runtime ALTER 만 적용 — **migration sql 파일 부재**. fresh DB rebuild 시 `UndefinedColumnError: site_summary_text`. AWS dump 만으로 살아남는 상태.
- **확인**: `git show 21c10f7 --stat` 에 sql 파일 없음 (backend_catalog §I #C1 자인).
- **해소 옵션**:
  - (1) migration sql 신규 생성 (`infra/postgres/migrations/2026-05-2x_daily_reports_site_summary_text.sql` 5 LOC: `ALTER TABLE daily_reports ADD COLUMN IF NOT EXISTS site_summary_text TEXT;`).
  - (2) init.sql 에 컬럼 추가 (fresh dev 시 작동, 단 기존 운영 DB 는 migration 필요).
  - (3) 현재 상태 유지 — AWS dump 만으로 살아남기 도박.
- **권고**: (1) — migration sql 추가, 다음 fresh rebuild 사고 방지.
- **trade-off**: PoC: 5 LOC + 1 파일 vs 본질: 시연 환경 rebuild 시 사고 100%.

### ★★ C-2. `/export/run` ad-hoc PG pool — `app.state.pg` 재사용 X (Critical, #C2)

- **FE 기대**: 없음 — FE 는 단순 xlsx 다운로드 호출.
- **BE 실제**: `pipeline/exporter_routes.py:23~34` 가 매 요청마다 `PGClient(os.environ["POSTGRES_URL"]).connect()` 신규 풀 생성 + `await pg.close()` — `app.state.pg` 재사용 안 함.
- **위험**: 요청당 handshake / TLS overhead, 동시 N 요청 시 pool 폭증. 시연 시 경영진 동시 다운로드 시 PG 연결 고갈.
- **해소 옵션**:
  - (1) `Depends(get_pg)` 주입 패턴 — `app.state.pg` 재사용 (~10 LOC).
  - (2) module-level lazy singleton.
- **권고**: (1) — FastAPI 표준 패턴.
- **trade-off**: PoC: 10 LOC vs 본질: 시연 시 PG 연결 고갈.

### ★★ C-3. `mapped_history.trade` 컬럼 — atomizer INSERT 누락 (Critical, #C3)

- **FE 기대**: `AgentTaskItem.trade` 가 한글 공종 표시 (`mapped_history.trade` 의도 — D-16 결정).
- **BE 실제**: `infra/postgres/migrations/2026-05-19_mapped_history_trade.sql` 으로 컬럼 신설. 단:
  - `pipeline/db.py:478~487 insert_mapped_history_batch` ON CONFLICT SET 절에 `trade` 없음 (today_qty / today_assigned_workers / unit 만 갱신).
  - `pipeline/agents/atomizer.py:130` INSERT path 도 trade 미박힘 의심.
  - FE `/api/mock/agent-tasks` 가 `mh.l6_main` 으로 fallback (`pipeline/api.py:916`) — 한글 공종 의도 위반 (l6_main = WBS 매핑 카테고리, trade = 원본 한글 공종).
- **해소 옵션**:
  - (1) `db.py:478~487` SET 절에 trade 추가 + `atomizer.py:130` mh_rows 생성 시 Activity.trade 확인 (~5 LOC).
  - (2) `mh.l6_main` 으로 영구 fallback (사용자 D-16 결정 직접 위반).
- **권고**: (1) — D-16 이행.
- **trade-off**: PoC: 5 LOC vs 본질: 사용자 "억지 매핑 금지" feedback 직접 위반.

### ★ C-4. `view_builder.py:1447` working tree 미커밋 (★ NEW, #N17)

- **위치**: `pipeline/agents/optimizer/view_builder.py:1447` 의 `AND ma.trade IN ('건축', '토목')` 1 줄 제거가 다른 세션 working tree 에서 진행 중.
- **FE 영향**: 미커밋 시 v2 산출 대상이 건축+토목 한정 → 설비/전기 공종이 quadrant/wp_summary 에서 누락.
- **해소 옵션**:
  - (1) 다른 세션 commit 대기.
  - (2) 본 cycle 에서 직접 제거 + commit (다른 세션 충돌 위험).
- **권고**: (1) — 세션 충돌 회피.

### ★ C-5. `daily_reports.productivity_jsonb` v1 ↔ v2 drift (★ NEW, #M-v1v2)

- **FE 기대**: FE 가 productivity_jsonb 직접 SELECT 안 함 (kpi_jsonb 만 사용) — 어느 산식 기대하는지 명시 부재. 단 v1 vs v2 shape 다른 점 미인지 시 향후 사고 위험.
- **BE 실제**:
  - v1 `_build_productivity_views` (`view_builder.py:48`): `{today: EVM dict, by_contractor, by_l6, by_wp}` (EVM = `{spi, cpi, ev, pv, ac, cum_actual_qty, plan_qty_full}`).
  - v2 `_build_productivity_views_v2` (`view_builder.py:1410`): `{site: {wv_median, simple_mean, n_companies, n_l75}, by_company, by_l6}`.
  - `pipeline/agents/optimizer/agent.py:187` 가 v1 호출, `scripts/backfill_daily_report_views_v2.py` 가 v2 호출 → 같은 컬럼 다른 shape 박힘. 어느 row 가 어느 산식인지 컬럼에서 분간 불가.
- **해소 옵션**:
  - (1) `productivity_jsonb` 에 `version` 키 추가 (`{"version": "v2", ...}`).
  - (2) v1 폐기 — agent.py 도 v2 호출 통일.
  - (3) 컬럼 분리 (`productivity_jsonb_v2` 신규).
- **권고**: (2) — agent.py 1 줄 변경. v1 dead 시 코드 삭제.
- **trade-off**: PoC: 1 LOC vs 본질: 같은 컬럼 다른 의미 = 다음 cycle 사고 100%.

### ★ C-6. `daily_reports.scenarios_jsonb` P25 ↔ P75 라벨↔값 swap (★ NEW, #M-scenarios-swap)

- **FE 기대**: `ScenarioSet` 4 키 (`no_action / optimistic_p25 / base_p50 / pessimistic_p75`) — FE 가 percentile 키 그대로 차트 라벨로 사용 시 헷갈림.
- **BE 실제**: `pipeline/agents/optimizer/view_builder.py:1237~1241` 자인:
  - `optimistic_p25` 의 recovery_days = P75 값 (큰 recovery 큰 만회 = 낙관).
  - `pessimistic_p75` 의 recovery_days = P25 값 (작은 recovery 적은 만회 = 비관).
  - 라벨 ↔ 값 mismatch 의도적 swap.
- **현재 동작**: `web/lib/diagnosis-adapter.ts:29~31` 가 swap 인지하고 inverse 매핑 — `optimistic_p25.recovery_days → recovery_days_p75`, `pessimistic_p75.recovery_days → recovery_days_p25`. 정합은 되지만 spec 부재 시 다음 cycle 사고.
- **해소 옵션**:
  - (1) 키 그대로 + view_builder 가 의미 docstring 으로 명시.
  - (2) 키를 `optimistic_p75 / pessimistic_p25` 로 rename (호출처 깨짐).
  - (3) FE 가 매핑 변환 (현재).
- **권고**: (3) 현재 유지 + (1) spec 명문화 — rename 은 호출처 깨짐 위험.

### ★ C-7. `ForecastChart` firstUndef 정순 vs `diagnose()` todayIdx 역순 — sparse hole (★ NEW)

- **FE 위치 1 (ForecastChart 정순)**: `web/app/components/charts/ForecastChart.tsx:88~89` `data.findIndex(actual===undefined)` 정순 → `lastPoint` 가 ReferenceDot 위치 결정 (line 226~234).
- **FE 위치 2 (diagnose 역순)**: `web/lib/diagnosis.ts:104~109` `todayIdx` 가 **역순 탐색** (sparse hole 있어도 마지막 실 actual 찾음).
- **위험**: sparse hole 있는 경우 두 산출 불일치 → ReferenceDot 가 잘못된 점에 찍힘.
- **해소 옵션**:
  - (1) ForecastChart 도 역순 탐색으로 통일 (~2 LOC).
  - (2) `diagnose()` 가 todayIdx 를 반환해서 ForecastChart 재사용 (~10 LOC).
  - (3) sparse hole 입력 차단 (BE 가 actual 항상 채움 — 현재 view_builder.py:962~973 의 WINDOW SUM 으로 단조 보장하지만 PoC 데이터 한정).
- **권고**: (1) — 2 LOC, diagnose() 와 산출 통일.

### ★ C-8. `RawDataTab` 신규 props 미연결 + BE `raw_data: []` 빈 배열 (★ NEW)

- **FE 위치**:
  - `web/app/components/reports/RawDataTab.tsx:18~112` 가 `filterWpId?` / `wpNameById?` props 신설.
  - `web/app/(app)/reports/page.tsx` 가 props 미전달 + RawDataTab 호출 자체 없음 (현재 dead).
- **BE 위치**: `web/app/api/mock/report/[date]/route.ts:50` 가 `raw_data: []` 빈 배열 반환.
- **해소 옵션**:
  - (1) BE 가 mapper_activities 에서 RawDataRow shape 산출 (~30 LOC) + reports/page 에서 RawDataTab 호출 + props 전달 (~20 LOC).
  - (2) RawDataTab 영구 dead 처리 (component + props 삭제).
- **권고**: (1) — 컴포넌트 준비됐는데 dead 는 자원 낭비. demo 시 raw data tab 추가 narrative.

### ★ C-9. `wp_id` 정합 — FE deriveWpIdAndPath vs BE jsonb keys (★ NEW)

- **FE 위치**: `web/lib/transforms.ts:61~71 deriveWpIdAndPath(wa, l6_main, site_name)` = `${kebab(wa)}-${kebab(l6_main)}` — review/route.ts cards.ai_mapped_wp_id + wbsTreeBuild 의 WP 노드 id.
- **BE 위치**: `daily_reports.quadrant_jsonb[].wp_id` / `wp_summary_jsonb[].wp_id` / `optimizer_view_jsonb.by_wp` keys — `pipeline/agents/optimizer/view_builder.py:750 _wp_id_of` = kebab `wa-l6_main-company` (★ company 포함 vs FE 미포함).
- **위험**: `detail.optimizer.by_wp[selectedWpId]` lookup 시 빈 카드. FE 가 BE 산식 매칭 안 함.
- **해소 옵션**:
  - (1) FE deriveWpIdAndPath 도 triplet (`${wa}-${l6_main}-${company}`).
  - (2) BE 가 wa-l6_main 만 산출 (동일 wa/l6 다른 company 충돌 위험).
  - (3) endpoint contract 에 wp_id 산식 명문화 + 양쪽 통일.
- **권고**: (1) + (3) — BE 의 triplet 이 동일 wa/l6 다른 company 분리 의도. FE 정합.

### C-10. `Site.status` enum CHECK 제약 (정합)

- **FE**: `Status = "normal" \| "caution" \| "risk" \| "unknown"` (`web/lib/types.ts:5`).
- **BE**: `sites.status TEXT CHECK ('normal'/'caution'/'risk'/'unknown') DEFAULT 'unknown'` (`infra/postgres/init.sql:146`) — CHECK 제약 있음.
- **상태**: 정합. 행동 불필요.

### ★ C-11. `ReviewItem.confidence` 단위 명문 부재 (★ NEW)

- **FE 기대**: `confidence: number` (0.0~1.0) (`web/lib/types.ts:131`) — ReviewCard 에서 `Math.round(confidence × 100)` 으로 % 표시.
- **BE 실제**: `mapper_activities.mapping_conf DOUBLE PRECISION` (`infra/postgres/migrations/2026-05-18_parser_mapper_outputs.sql:266`) — 산출 = rerank confidence. spec 부재로 0~1 또는 0~100 분간 불가.
- **위험**: BE 산식 변경 시 BE 가 1~100 보내면 FE 가 1.0~100.0 으로 cast → "10000%" 표시.
- **해소 옵션**:
  - (1) BE assertion `assert 0 <= mapping_conf <= 1.0` + spec 명문화.
  - (2) FE auto-normalize (>= 2 면 / 100).
  - (3) contract 명문화 only.
- **권고**: (1) + (3) — assertion + spec 둘 다.

### ★ C-12. `/api/mock/dashboard` `fleet_trend` min/max placeholder (★ NEW)

- **FE 기대**: `FleetTrendPoint.{mean, min, max}` 3 값 (`web/lib/types.ts:231~234`) — 분포 밴드 면적.
- **BE 실제**: `web/lib/fixtures.ts:269` 주석 "실 site 1 개라 동일 값" — min=mean=max 동일. 분포 밴드 면적 0.
- **해소 옵션**:
  - (1) BE 가 일별 산식 차이 없으면 min/max 같은 값 유지 (현재).
  - (2) FE 가 single-site 케이스에서 분포 밴드 conditionally hide.
  - (3) mock site 의 perturbation 사용해서 min/max 합성.
- **권고**: (1) + (2) — single-site 가 PoC 의도, FE 가 분포 밴드 conditionally hide.

### C-13. `pipeline_runs.status` UPDATE helper 부재 (carried, #M-status)

- **FE 기대**: FE `DailyTask.status` (`/api/mock/agent-tasks`) 가 `status='waiting_hil_1'` 시 `review_pending` 표시 의도.
- **BE 실제**: `pipeline/db.py` 전수 grep — `pipeline_runs.status` UPDATE helper **0 개**. `current_node` 도 atomizer 만 박힘 (`db.py:251` hard-code).
- **결과**: FE polling status / current_node 의존 동작 X. agent_status active_count 도 부정확.
- **해소 옵션**:
  - (1) D-2 / D-17 결정 이행 — `db.py` 신규 `update_run_status(run_id, status)` + `update_run_current_node` helper, graph.py 모든 노드 진입 시 호출 (~50 LOC).
  - (2) FastAPI 가 graph state polling 으로 derive (`graph.aget_state(thread_id).next`).
  - (3) LangGraph stream 모드 hook.
- **권고**: (1) — 이전 D-2 / D-17 결정 이행 (4 cycle 째 carried).

### C-14. `mapping_corrections` spec drift (carried, #M-mapping-corrections-spec)

- **FE 기대**: 호출처 없음 — BE 만 INSERT.
- **BE 실제**: `docs/schema/postgres.md §8` spec top-level 컬럼 (work_content/company/trade/correction_type) ↔ 실 schema 6 컬럼만 (`infra/postgres/init.sql:127~133`). JSONB 안에 합쳐서 박는 우회 path.
- **해소 옵션**: (1) spec 정리 (postgres.md 갱신) (2) schema 분리 (top-level 컬럼화).
- **권고**: (1) — spec 정리 backlog.

### C-15. `conditions` 타입 — list vs comma-joined str (carried, #M-conditions-type)

- **FE 기대**: 양쪽 다 받음 — type 불일치 인지.
- **BE 실제**: `pipeline/agents/forecaster/rerank.py:26` (list) vs `pipeline/agents/optimizer/retrieve.py:107` (str).
- **해소 옵션**: (1) optimizer 도 list 통일 (2) forecaster 도 str 통일 (3) FE 가 양쪽 처리.
- **권고**: (1) — list 가 의미상 맞음.

### ★ C-16. 9 endpoint 응답 shape 스펙 부재 (★ NEW)

- **FE 기대**: FE 가 각 endpoint 마다 type assertion 없음 (`fetch(...).then(r=>r.json())` 직접 cast).
- **BE 실제**: backend §E 13 endpoint + frontend §C-0 9 fetch — 각 endpoint 응답 shape 명문 spec 부재.
- **해소 옵션**:
  - (1) endpoint 마다 `pydantic` BaseModel 응답 typing + FastAPI auto-doc.
  - (2) FE 도 `zod` schema validation.
- **권고**: (1) — BE 가 BaseModel 으로 응답 shape 명시 (PoC 후 phase 2).

---

## §D. 결정 게이트 (사용자 결정 필요)

> 각 결정 = 권고 1 개 + 옵션 2~4 개 + trade-off. ★ Critical = 시연 마감 6/5 전 처리 필수. 합계 = **12 결정** (★ Critical = 5, 다음 cycle = 7).

### ★ Critical (시연 6/5 전 처리 필수)

#### D-1 (= C-1, #N13) — `daily_reports.site_summary_text` migration 추가

- **옵션**: (1) migration sql 신규 (5 LOC) (2) init.sql 직접 추가 (3) 현재 상태 유지 (AWS dump 의존 도박).
- **권고**: (1).
- **trade-off**: PoC: 5 LOC + 1 파일 vs 본질: fresh DB rebuild 안전성. 시연 환경 rebuild 시 사고 100%.

#### D-2 (= C-3) — `mapped_history.trade` INSERT 누락 fix

- **옵션**: (1) `db.py:478~487` SET 절 + `atomizer.py:130` INSERT 양쪽 fix (~5 LOC) (2) `mh.l6_main` 영구 fallback (D-16 결정 위반).
- **권고**: (1).
- **trade-off**: PoC: 5 LOC vs 본질: 사용자 "억지 매핑 금지" 직접 위반.

#### D-3 (= C-2) — `/export/run` PG pool 재사용

- **옵션**: (1) `Depends(get_pg)` 주입 (~10 LOC) (2) module singleton (3) 현재 상태 유지.
- **권고**: (1).
- **trade-off**: PoC: 10 LOC vs 본질: 시연 동시 다운로드 시 PG 연결 고갈.

#### D-4 (= C-8) — `RawDataTab` BE raw_data 채우기 + reports/page 연결

- **옵션**: (1) BE mapper_activities → RawDataRow shape + page 호출 + props 전달 (~50 LOC 합산) (2) RawDataTab 영구 dead 처리 (component 삭제).
- **권고**: (1) 또는 (2).
- **trade-off**: PoC: 50 LOC vs 본질: 컴포넌트 준비됐는데 dead 면 dead 표시 명확화. 사용자 결정 필요.

#### D-5 (= A-6) — HIL waiting `sites_summary.review_pending` 연결

- **옵션**: (1) HILS[0].waiting 자리에 `summary.review_pending` 꽂아 넣기 (~5 LOC) (2) 현재 하드코딩 유지.
- **권고**: (1).
- **trade-off**: PoC: 5 LOC vs 본질: BE 데이터 이미 있는데 FE 미사용.

### 다음 cycle 결정 (시연 후 가능)

#### D-6 (= C-4, #N17) — `view_builder.py:1447` working tree commit

- **옵션**: (1) 다른 세션 commit 대기 (2) 본 cycle 직접 제거 + commit (세션 충돌 위험).
- **권고**: (1).

#### D-7 (= C-5, #M-v1v2) — `productivity_jsonb` v1 ↔ v2 통일

- **옵션**: (1) `version` 키 추가 (2) v1 폐기 — agent.py 도 v2 호출 (3) 컬럼 분리.
- **권고**: (2) — agent.py 1 줄. v1 dead 시 코드 삭제.

#### D-8 (= C-6, #M-scenarios-swap) — `scenarios_jsonb` P25/P75 swap spec 명문

- **옵션**: (1) 키 그대로 + view_builder docstring 명시 (2) `optimistic_p75 / pessimistic_p25` rename (호출처 깨짐) (3) FE 매핑 변환 (현재).
- **권고**: (3) 유지 + (1) spec 명문화.

#### D-9 (= C-9) — `wp_id` 산식 통일

- **옵션**: (1) FE 도 triplet (`wa-l6_main-company`) (2) BE 가 wa-l6_main 만 (3) endpoint contract 명문.
- **권고**: (1) + (3) — BE triplet 이 의도, FE 정합.

#### D-10 (= C-11) — `ReviewItem.confidence` 단위

- **옵션**: (1) BE assertion (0~1.0) (2) FE auto-normalize (3) contract 명문화.
- **권고**: (1) + (3).

#### D-11 (= C-13, #M-status) — `pipeline_runs.status` UPDATE path

- **옵션**: (1) D-2 / D-17 이행 — db.py helper + graph.py 전 노드 호출 (2) FastAPI graph state polling derive (3) LangGraph stream hook.
- **권고**: (1) — 4 cycle 째 carried, ~50 LOC.

#### D-12 (= A-7) — `ai_replacement_rate` 단위 contract 명문

- **옵션**: (1) % 단위 보장 (현재) + spec 명문 (2) 분수 단위 변경 + FE × 100 (3) UI assertion.
- **권고**: (1).

---

## §E. 본 cycle 핵심 변경 trace (★ NEW 와 ★ CHG 의 출처)

> 본 cycle 의 산식 / shape 변경이 §A/§B/§C 에 어떻게 흘러갔는지 trace.

| commit / 변경 | 변경 내용 | 영향 받은 gap |
|---|---|---|
| `21c10f7` (runtime ALTER) | `daily_reports.site_summary_text TEXT` 추가, migration 파일 부재 | C-1 (Critical), D-1 |
| `7e9e1a1` (merge) | `pipeline/agents/optimizer/site_summary.py` 141 LOC 신규, Azure JSON response_format → daily_reports.site_summary_text | C-1, B-7 (cold_start source 키), 신규 FE `ReportDetail.site_summary_text` → ForecastChart `aiSummaryText` |
| `a7e2465` | `pipeline/exporter_routes.py` 47 LOC 신규, `/export/run` ad-hoc PGClient | C-2 (Critical), D-3 |
| `migrations/2026-05-19_mapped_history_trade.sql` | `mapped_history.trade TEXT` 컬럼 신설 — atomizer INSERT 누락 | C-3 (Critical), D-2 |
| `view_builder.py 752 → 1,882 LOC` (+1,130) | 산식 A (s_curve WV×MH) + scenarios percentile + `_v2` 분기 + MEDIAN fix + quadrant↔by_wp Jaccard 11→100% | C-5 (productivity v1↔v2), C-6 (scenarios swap), C-4 (#N17 미커밋) |
| `web/lib/diagnosis.ts 55~87 buildScenarioCurve` (★ NEW 함수) | catch-up + plan 동행 모델 도입, `delta_completion_days: 0` 고정 | A-1 (catch_up), A-5 (RecoveryEtaCard dead, ★ CHG) |
| `web/lib/bar-filters.ts` 12 LOC 신규 | 150% 초과 제거 + top3+bot7 | (FE 단독, gap 없음) |
| `/api/mock/report/[date]` 분리 + list-only | 2-stage fetch — list 50KB + per-date 9 jsonb + site_summary_text | C-8 (raw_data: []) |
| `web/lib/fixtures.ts:99 loadReal()` PG SELECT | sites_summary / agent_status / chat_sequence / dashboard_performance 4 종 PG | A-3 / A-4 carried (fixture → PG swap 거의 완료) |
| `4b8a955` (lifespan, +23 LOC) | api.py:147 collector idle task spawn + `app.include_router(exporter_router)` | B-6 (collector_inbox internal) |
| `migrations/2026-05-21_phase1.sql` | `prototype_embedding_cache` + `mapped_history_merge_log` 2 테이블 | B-2, B-3 |
| `migrations/2026-05-23_mapper_l7_5_columns.sql` | mapper_activities 4 컬럼 (l5_disc / l7_sub / l7_5_activity / sub_work_area) | view_builder.py:1445 v2 필터 의존 (C-4 트리거) |
| `migrations/2026-05-20_add_is_mock.sql` | 7 테이블 × `is_mock BOOL NOT NULL DEFAULT FALSE` backfill | (FE/BE 정합, `CPIA_DEMO_FALLBACK` 토글 분기 — A-8 yearly_saving 점프 트리거) |
| `migrations/2026-05-19_collector_inbox.sql` + db.py:1145~1217 | collector_inbox 11 row + 4 module helper | B-6 |
| `migrations/2026-05-19_scenarios_jsonb.sql` | daily_reports.scenarios_jsonb (4 시나리오) | C-6 (P25/P75 swap), 신규 ForecastChart `scenarios` prop |
| Reporter / Optimizer view_builder 9 jsonb 산식 변경 | s_curve 산식 A, MEDIAN fix, scenarios 4 percentile | C-5, C-6, A-1 (catch-up 모델 base_p50 의존) |

---

## §F. mock 유지 영역 (BE 신규 산식/source 안 만듦)

> 본 cycle 에서 BE 산식 추가 없이 mock / FE hardcode 유지. 6/5 마감 비용 < 효익.

| 영역 | 위치 | 사유 |
|---|---|---|
| `MiddleOfficeAutomation` 4 row | `web/lib/types.ts:251~254`, `data/mock_dashboard.json` impact.per_site_automation | Middle Office 자동화율은 BE pipeline scope 밖 — 정적 메타 |
| `ImpactTrendPoint` 월별 cumulative_fte | `web/lib/types.ts:246~247` | historical 누적 데이터 미보유 |
| FE 하드코딩 mock 2 종 (NotificationBell / UserMenu) | `NotificationBell.tsx:16 MOCK_NOTIFS` (3건), `UserMenu.tsx:8 USERS` (2명) | 실 auth/notification 시스템 도입 X. HIL 만 D-5 로 부분 연결 |
| `AgentWorkflow.tsx:30 COUNTS` step → 대기/오늘/누적 | `web/app/components/home/AgentWorkflow.tsx:30` | BE 전환 시 별도 endpoint 필요 (D-11 #M-status 의존) |
| `SimulationSequence` dead fixture | `web/lib/types.ts:259~261`, `data/mock_simulation.json` | 호출처 0, A-9 로 다음 cycle 정리 |
| `DiagnosisInput` preview-only | `web/lib/types.ts:268~279` | A-2 (D-3 REVISED) — FE diagnose() prod, BE 산식 추가 X |
| `daily_reports.report_md` (906 chars markdown) | `infra/postgres/init.sql:38` | 본 cycle FE 노출 X, markdown viewer 컴포넌트 추가 시 노출 |
| `mock_dashboard.json` `impact.fleet_kpi` partial | `web/lib/fixtures.ts:79` | dashboard.impact 만 fixture, performance 는 PG swap. A-10 로 다음 cycle 정리 |
| `daily_reports.history_csv_row` legacy summary | `infra/postgres/init.sql:39`, `pipeline/agents/reporter.py:107~112` | B-1 — legacy, docstring 정리 backlog |
| `forecasts` 19 컬럼 / `optimizer_advice` 4 컬럼 미사용 | `infra/postgres/migrations/2026-05-16_*.sql` | B-8 / B-9 — endpoint 응답 drop 또는 raw debug endpoint 분리 phase 2 |
| `parser_warning` stderr only | `pipeline/agents/parser.py` | B-4 (#N25) — PG INSERT path 신설 backlog |
| `prototype_embedding_cache` / `mapped_history_merge_log` / `collector_inbox` | `migrations/2026-05-21_phase1.sql` / `2026-05-19_collector_inbox.sql` | B-2 / B-3 / B-6 — BE internal infra, FE 무관 |

---

## §G. 메인 반환 요약

- **§A FE only** = 11 건 (★ NEW = 5, ★ CHG = 1, carried = 5)
- **§B BE only** = 9 건 (★ NEW = 5, carried = 4)
- **§C Mismatch** = 16 건 (★ NEW = 11, ★ CHG = 1, carried = 4)
- **§D 결정 게이트** = 12 결정 (★ Critical 시연 6/5 전 = 5, 다음 cycle = 7)

### 가장 critical 3 건 (시연 6/5 전 처리 필수)

1. **D-1 / C-1 / #N13 — `daily_reports.site_summary_text` migration sql 부재**. fresh DB rebuild 시 UndefinedColumnError. 1 파일 5 LOC 해결.
2. **D-2 / C-3 — `mapped_history.trade` atomizer INSERT 누락**. 사용자 "억지 매핑 금지" feedback 직접 위반. `db.py:478~487` + `atomizer.py:130` 양쪽 5 LOC fix.
3. **D-3 / C-2 — `/export/run` ad-hoc PG pool**. 시연 동시 다운로드 시 PG 연결 고갈. `Depends(get_pg)` 주입 10 LOC.

---

> 출처: `data-contract/frontend_catalog.md` (683 줄), `data-contract/backend_catalog.md` (1043 줄), `deep-dive/architecture_overview.md` (32 이슈 표). 본 cycle = 2026-05-27. 다음 cycle = 사용자 §D 결정 후 BE 구현 cycle (writing-plans 형식) 작성.
