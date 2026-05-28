# CPIA Data Contract — INDEX

> 생성: 2026-05-17 (cycle: fe-be-bridge brainstorming)
> **2026-05-26 갱신** (cycle: post-mock-redesign-and-site-summary) — Mock 재설계 PR #40 + AWS 마이그 + view_builder MEDIAN + backfill_v2 + ForecastChart catch-up + site_summary LLM cycle 후 전수 재갱신. **70+ commits, 204 files, +30,151 / -3,055 LOC** 흡수.
> baseline = `a83ec7d` (2026-05-22) → HEAD = `1ba783f` (2026-05-26). 본 cycle 전 영역 재카탈로그.
> git SHA: `1ba783f` (A_Track HEAD). main 머지 완료 — `7e9e1a1` 산식 A + site_summary / `1ba783f` Mock 재설계 sync.

본 data-contract/ 디렉토리는 CPIA 의 **FE (web/) ↔ BE (pipeline/) 데이터 계약** 산출. 6 카탈로그 + 결정 사항 + 연결 계획.

사용자 강조 (본 cycle): **"BE↔FE 데이터 연결할 때 서로 어느 적재된 데이터로 연결되는지 어떤 스키마인지 정확한 layer 가 보이게끔"**. 본 INDEX + crosswalk.md §0 layer 표 + §3 ForecastChart 4선 매핑 + gaps.md §D 결정 게이트로 응답.

---

## 헤드라인 (2026-05-26 갱신)

| 분류 | 통계 |
|---|---|
| **FE catalog** | **48 type** (이전 33 → +15) / **~220 field** (이전 190 → +30) / 10 mock fixture (8 PG swap 됨) / 8 page × N component / 5 lib utility (diagnosis-adapter / bar-filters NEW) |
| **BE catalog** | **23 테이블** (17 user + 4 stash + 1 collector_inbox NEW + 3 ckpt) / **316 row** / **9 jsonb view** 산식 변경 / **★ NEW 컬럼**: site_summary_text / mapper_l7.5 4종 / trade / 7 테이블 is_mock |
| **FastAPI endpoint** | **12 + 1 NEW** = 13 — 본 cycle `/export/run` (exporter_routes.py 47 LOC) + lifespan collector idle task |
| **Crosswalk** | **220 FE field 매핑** — high 115 (52%) / medium 38 (17%) / low 26 (12%) / TBD 0 (D-3 EWMA / D-12 optimizer 배열 결정 완료) |
| **본 cycle 마킹** | **★ NEW 23** (FE 직접 6 + BE 신규 산출 ↔ FE 기존 17) / **★ CHG 10** (산식 A 3 + MEDIAN 2 + quadrant 3 + bars + wp_name + delta_completion_days) / **★ DRIFT 6** (productivity v1↔v2 / kpi.productivity_today / contractor·trade bars / quadrant.wp_name / wp_summary 정렬 / mapped_history.trade) |
| **Gaps** | §A FE only **11** (★ NEW 5) / §B BE only **9** (★ NEW 5) / §C Mismatch **16** (★ NEW 11) / §D 결정 게이트 **12** (Critical 시연 6/5 전 **5** / 다음 cycle **7**) |
| **사용자 결정 누계** | 14 (카탈로그 시점 D-1~D-14) + 9 (2026-05-18) + 3 (2026-05-19 D-15~D-17) + 0 (본 cycle 신규 — 모두 backlog) = **26 확정 / 12 pending** |

---

## 본 cycle 핵심 FE↔BE 변경 (사용자 강조 layer 명확화)

### Layer 1 — Raw Source (외부 입력)

| 종류 | 적재처 | 본 cycle 변경 |
|---|---|---|
| 작업일보 xlsx | `pipeline/data/` 또는 Gmail attachment | ★ NEW Gmail IMAP IDLE — `pipeline/collector/idle_worker.py` |
| Master List xlsx | `activity_master` 테이블 | `C_PLAN_WV=32` 추가 (5-23 migration) |
| Gmail IMAP | `collector_inbox` 테이블 (NEW) | ★ NEW dedup `(message_id, attachment_filename) UNIQUE` |

### Layer 2 — LangGraph State (중간)

| State 키 | 채우는 노드 | 읽는 노드 | 영속화 | 본 cycle |
|---|---|---|---|---|
| `parsed` (이전 parsed_reports) | parser_node | mapper_node | parser_reports / parser_activities | ★ CHG state-key drift fix (6b9db7c) |
| `mapped` | mapper_node | hil_1 / atomizer / forecaster | mapper_activities (37 컬럼) | ★ 4 컬럼 추가 (l5_disc/l7_sub/l7_5_activity/sub_work_area) |
| `atomized_ids` | atomizer_node | forecaster / optimizer | Chroma daily_activities | ★ batch 16→64 / metadata 12→15 |
| `forecasts` | forecaster_node | hil_2 / optimizer / reporter | forecasts (28 컬럼) | ★ plan_main_qty atomic distinct SUM |
| `optimizer_advice` | optimizer_node | reporter_node | optimizer_advice + daily_reports.optimizer_view_jsonb | ★ 4섹션 풍부화 + INCIDENT 9종 |
| `daily_report` | reporter_node | (terminal) | daily_reports (9 jsonb + ★ NEW site_summary_text) | ★ site_summary_text 컬럼 (★ migration 없음 #N13) |

### Layer 3 — Persistent Storage (PG / Chroma / Checkpoints)

| 테이블 | 본 cycle 변경 | 읽는 FE 페이지 |
|---|---|---|
| `daily_reports` | ★ +`site_summary_text` (migration 없음 #N13) + 9 jsonb 산식 변경 (산식 A / MEDIAN / scenarios percentile 4) | reports/[date] detail (ForecastChart / WPSummary / Quadrant / Optimizer / **site_summary_text aiSummaryText**) |
| `mapper_activities` | ★ +4 컬럼 (l5_disc / l7_sub / l7_5_activity / sub_work_area, 5-23 migration) | review WBSTree alternatives |
| `mapped_history` | ★ +`trade` 컬럼 (5-19 migration) — **★ atomizer INSERT 누락 #C3, 항상 NULL** | tasks AgentTaskItem.trade (NULL fallback) |
| `collector_inbox` | ★ NEW (5-19 migration) — Gmail IMAP dedup | (없음 — 내부) |
| 7 테이블 | ★ NEW `is_mock` boolean (5-20 migration) — sites/daily_reports/forecasts/optimizer_advice/mapping_corrections/mapper_activities/mapped_history | `/api/mock/*` route `WHERE is_mock = $1` |
| Chroma daily_activities | ★ `_format_document` live/backfill 2 모드 + 15 metadata | (없음 — forecaster/optimizer 가 RAG read) |

### Layer 4 — FE Consumer (web/lib/types.ts → page/component)

★ **ForecastChart 4선 매핑 (사용자가 가장 강조)**:

| Line (FE) | Source (BE) | Derived |
|---|---|---|
| 검정 실선 — actual | `daily_reports.s_curve_jsonb[].actual` | view_builder.py:942 산식 A WV×MH × MIN(1, cum/plan), full_grid + WINDOW SUM 단조 |
| 빨강 dashed — forecast | `daily_reports.s_curve_jsonb[].forecast` | view_builder.py:824 `_extend_forecast` EWMA 7 일 |
| 회색 실선 — planned | `daily_reports.s_curve_jsonb[].planned` | view_builder.py:914 산식 A × linear_progress |
| mint dashed — AI 시나리오 (base) | **FE 산출** — `diagnosis.ts:55 buildScenarioCurve` (catch-up slope → plan 동행) | BE input = `scenarios.site.base_p50.recovery_days` 만 |
| narrative | `daily_reports.site_summary_text` (★ NEW) | Optimizer LLM `site_summary.py:generate_site_summary` (Azure JSON) — **★ live 미연결 #N20, backfill_v2 만 채움** |

---

## 카탈로그 4 + 보조 2

| 파일 | 역할 | 라인 수 | 본 cycle |
|---|---|---:|---|
| [frontend_catalog.md](./frontend_catalog.md) | FE type 인벤토리 + fixture + page→component→field 매핑 + lib utility | **683** (이전 432, +251) | 48 type / 220 field / ★ NEW 5 field / FE 단독 이슈 11 |
| [backend_catalog.md](./backend_catalog.md) | DB schema 23 테이블 + 9 jsonb key + LangGraph state + agent output + db.py 35+ helper + 13 FastAPI endpoint | **1043** (이전 412, +631) | ★ NEW 5+ source / ★ Critical 3 / BE 단독 이슈 21 |
| [crosswalk.md](./crosswalk.md) | 3 면 표 (FE field ↔ BE source ↔ derived rule + confidence) — 220 field | **596** (이전 ~430, +166) | high 115 / medium 38 / low 26 / ★ NEW 23 / ★ CHG 10 / ★ DRIFT 6 / 정합 의문 15 |
| [gaps.md](./gaps.md) | 3 분류 (FE-only 11 / BE-only 9 / Mismatch 16) + 옵션 + 권고 + 결정 게이트 §D 12 | **533** (이전 ~310, +223) | Critical 시연 6/5 전 5 / 다음 cycle 7 |
| [sim_results.md](./sim_results.md) | 정합 시뮬레이션 (이전 cycle, stale 가능) | ~80 | 본 cycle 미갱신 — 다음 cycle backlog |
| [db-runtime-catalog.md](./db-runtime-catalog.md) | 실 PG row sample dump (이전 cycle) | ~290 | 본 cycle 미갱신 — 다음 cycle backlog (collector_inbox + site_summary_text 추가 필요) |

---

## ★ Critical 시연 6/5 전 필수 처리 (3 건)

| # | 영역 | 위치 | 해결 LOC |
|---|---|---|---|
| ✅ **D-1 / C-1 / #N13** | persistence | `daily_reports.site_summary_text` migration sql 부재 → fresh rebuild UndefinedColumnError | **완료** 2026-05-27 `b310f36` — `infra/postgres/migrations/2026-05-27_daily_reports_site_summary_text.sql` (IF NOT EXISTS, 운영 DB skip 확인) |
| ✅ **D-2 / C-3** | atomizer + persistence | `mapped_history.trade` atomizer INSERT 누락 → 60,147 row 전부 NULL (운영 DB SELECT 확인) | **코드 fix 완료** 2026-05-27 `ec0ecce` — atomizer.py mh_rows + db.py SQL ($1~$10 + ON CONFLICT SET) 양쪽. **⚠️ 기존 60K row backfill 잔존 (D-2.1)** |
| **D-3 / C-2** | persistence | `/export/run` ad-hoc PG pool — `exporter_routes.py:23~34` 가 매 요청마다 `PGClient(...).connect()` 신규 풀 생성. 시연 동시 다운로드 시 PG 연결 고갈 | 10 LOC: `Depends(get_pg)` 주입 |

---

## ★ 정합 의문 (시연 영향 — 8 건, crosswalk.md §17)

| # | FE 기대 | BE 실제 | 영향 |
|---|---|---|---|
| 1 | `ReportDetail.site_summary_text` 채워짐 | live optimize() 미연결, backfill_v2 --with-summary 만 (#N14 / #N20) | **시연 핵심 narrative 비어있음** → FE 룰베이스 fallback |
| 2 | (위) | `site_summary_text` 컬럼 migration 부재 (#C1 / #N13) | fresh rebuild UndefinedColumnError |
| 3 | `productivity_jsonb` 단일 산식 | v1 EVM (agent.py:187) ↔ v2 wv-median (backfill) drift | FE 가 어느 버전 박혔는지 분간 불가 |
| 4 | `scenarios_jsonb` percentile 라벨 그대로 | P25/P75 라벨↔값 swap (view_builder.py:1237 자인) | FE diagnosis-adapter 가 inverse 매핑 — 라벨 다중역할 |
| 5 | `AgentTaskItem.trade` 한글 공종 | mapped_history.trade NULL (#C3) → l6_main fallback | ⚠️ 코드 fix 완료 (D-2, ec0ecce) — 기존 60K row backfill 잔존 (D-2.1) |
| 6 | `ForecastChart` ReferenceDot 정확한 today 점 | `firstUndef/lastIdx` 정순 vs `diagnose() todayIdx` 역순 불일치 | sparse hole 시 dot 잘못된 위치 |
| 7 | `ScenarioPoint.catch_up` BE source 있음 | FE 자체 산출, BE 산식 변경이 FE 에 자동 반영 안 됨 | 산식 drift 위험 |
| 8 | `wp_id` 정합 | FE `${kebab(wa)}-${kebab(l6_main)}` 2 컴포넌트 vs BE `_wp_id_of` 3 컴포넌트 triplet | `detail.optimizer.by_wp[selectedWpId]` lookup 빈 카드 |

---

## 사용자 결정 게이트 (★ 다음 cycle 진입 트리거)

12 결정 (gaps.md §D). 우선순위:

### 시연 6/5 전 (Critical 5)
1. ✅ **D-1**: site_summary_text migration sql 신규 — **완료** (2026-05-27 commit `b310f36`). `infra/postgres/migrations/2026-05-27_daily_reports_site_summary_text.sql` 신설. IF NOT EXISTS idempotent — 운영 DB 안전 + fresh rebuild 안전.
2. ✅ **D-2**: mapped_history.trade INSERT path fix — **코드 fix 완료** (2026-05-27 commit `ec0ecce`). atomizer.py:185 mh_rows + db.py:478 insert_mapped_history_batch SQL ($1~$10) + ON CONFLICT SET trade 추가. **⚠️ 기존 60,147 row backfill 미처리** (D-2.1 별도, 아래).
3. **D-3**: /export/run PG pool Depends 주입 — **권고: 즉시 적용**
4. **D-4**: site_summary live `optimize()` 연결 — **옵션** (가) optimize() 안에 호출 추가 — 7 site × 1 LLM call (~$0.5) (나) backfill_v2 only 유지 — fallback 룰베이스 narrative. **권고: 시연 화면이 site_summary 핵심이면 (가)**
5. **D-5**: productivity_jsonb v1 ↔ v2 통일 — **옵션** (가) v1 제거, v2 로 일원화 (나) v1 유지. **권고: v2 로 일원화 (drift 해소)**

### 본 cycle 누적된 backlog (시연 전 결정)
- **D-2.1**: `mapped_history.trade` 기존 60K row backfill — 코드 fix 만으로는 새 row 만 채워짐. 시연 데이터 (이미 backfill 된 5일 + 1년치 dummy) 의 trade 가 NULL 유지 → tasks 페이지 `AgentTaskItem.trade` 가 l6_main fallback. **옵션** (가) `mapper_activities.trade` 또는 `activity_master.trade` JOIN 으로 한 줄 UPDATE — 무비용 (나) 다음 cycle 재실행 — LLM 비용 듬 (다) 시연 직전 재 backfill 때 자연 해소. **권고: (가) — `scripts/backfill_mapped_history_trade.py` 신규 1 파일**.

### 다음 cycle (7)
6. D-6: reporter → exporter 파일명 rename (CLAUDE.md 약속 vs 실 코드)
7. D-7: B_Track exporter FE swap (NEXT_PUBLIC_FASTAPI_BASE)
8. D-8: ForecastChart firstUndef vs todayIdx 정합
9. D-9: wp_id 포맷 통일 (2 vs 3 컴포넌트)
10. D-10: scenarios P25/P75 라벨↔값 swap 명시 또는 fix
11. D-11: AUTO_BYPASS prod 가드
12. D-12: HIL2 AUTO_BYPASS env

---

## Pair Skills 산출물

| 스킬 | 산출물 | 본 cycle |
|---|---|---|
| `deep-dive` | `deep-dive/architecture_overview.md` (415) + `deep_dive_*.md` × 8 (5705) | 2026-05-26 갱신 |
| `design-intent` | `deep-dive/design-intent/INDEX.md` (425) + `design_intent_*.md` × 8 (4048) + `_meta.json` | 2026-05-26 갱신 |
| `data-contract-mapping` | (본 디렉토리) — 4 카탈로그 + 2 보조 | **2026-05-26 본 cycle** |

---

## 다음 cycle 위임 (future)

| 영역 | 사유 |
|---|---|
| sim_results.md 갱신 | 이전 cycle 시뮬레이션 stale — 산식 A + MEDIAN + scenarios percentile 4 정합 재시뮬 |
| db-runtime-catalog.md 갱신 | 실 PG row sample dump — collector_inbox + site_summary_text + 9 jsonb 실 키 + 7 테이블 is_mock 분포 |
| api-contract.md (docs/architecture/) | 본 카탈로그에서 derive — 13 endpoint 응답 shape spec |
| FastAPI swap 완료 후 재 catalog | `/api/mock/*` 9 route 가 모두 `/api/*` (FastAPI) 로 swap 되면 BFF layer 단순화 |

---

*최종 수정: 2026-05-26 (1ba783f) — Mock 재설계 + AWS 마이그 + view_builder MEDIAN + backfill_v2 + ForecastChart catch-up + site_summary LLM cycle 후 전수 재갱신.*
*이전 수정: 2026-05-19 — tasks-scope-G2-verification cycle (a83ec7d).*
*이전 수정: 2026-05-18 — fe-be-bridge-delta-and-decisions cycle (9 결정).*
*이전 수정: 2026-05-17 — fe-be-bridge brainstorming cycle (D-1~D-14 14 결정).*
