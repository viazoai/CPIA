# CPIA Data Contract — INDEX

> 생성: 2026-05-17 (cycle: fe-be-bridge brainstorming).
> **2026-05-18 갱신** (cycle: fe-be-bridge-delta-and-decisions) — PR #19/#20/#22 흡수 + 10 gap 명시 + 9 신규 결정 (D-3 EWMA 드랍 / WPSummary grain / mapped_history / wp_id / tasks BE 정합 / item status / optimizer 배열 / hil_1 resume / 6 gap 일괄).
> git SHA: d9eb603 (A_Track HEAD).

본 data-contract/ 디렉토리는 CPIA 의 **FE (web/) ↔ BE (pipeline/) 데이터 계약** 산출. 4 카탈로그 + 결정 사항 + 연결 계획.

---

## 헤드라인 (2026-05-18 갱신)

| 분류 | 통계 |
|---|---|
| **FE catalog** | 33 type (PR #22 신규 5 흡수) / ~190 field / 10 mock fixture / 8 page × N component / 5 lib utility (diagnosis-adapter.ts 신규) |
| **BE catalog** | 7 사용자 테이블 (105 col) + 4 LangGraph 자동 / 33 JSONB key / 17 state attr (PR #19 흡수) / ~90 agent output field / 16 db.py helper (+2 PR #19) |
| **Crosswalk** | 26 type 매핑 / ~190 FE field × BE source |
| **Confidence** | high 80 / medium 50 / low 25 / TBD 35 |
| **Gaps** | §A FE-only 10 / §B BE-only 6 / §C Mismatch 9 |
| **사용자 결정 누계** | 14 (카탈로그 D-1~D-14) + 9 신규 (2026-05-18) = **23 확정** |

---

## 카탈로그 4 파일 + 산출 1

| 파일 | 역할 | 라인 수 |
|---|---|---|
| [frontend_catalog.md](./frontend_catalog.md) | FE type 인벤토리 + fixture + page→component→field 매핑 + lib utility 분류 | 432 |
| [backend_catalog.md](./backend_catalog.md) | DB schema + JSONB key + LangGraph state attr + agent output + db.py helper | 412 |
| [crosswalk.md](./crosswalk.md) | 3 면 표 (FE field ↔ BE source ↔ derived rule + confidence) — 26 type | ~430 |
| [gaps.md](./gaps.md) | 3 분류 (FE-only / BE-only / mismatch) + 옵션 + 권고 + 결정 게이트 §D + **§F 2026-05-18 갱신 (G-1~G-10)** | ~310 |

---

## 사용자 결정 (확정) — 카탈로그 시점 14

### D-1 ~ D-4 핵심 결정

| # | 결정 | 채택 | 영향 |
|---|---|---|---|
| D-1 | sites.last_run_id 갱신 path | **graph END 노드** | `pipeline/graph.py` 의 reporter → END edge 안에 `db.update_site_last_run(site_id, run_id)` 신규 helper 호출 |
| D-2 | pipeline_runs.status 갱신 path | **각 node 진입 시 db helper 호출** | `pipeline/db.py` 에 `update_run_status(run_id, status)` 신규 |
| D-3 | ProductivityDiagnosis 13 필드 | ~~본 cycle scope 밖~~ → **2026-05-18 REVISED: EWMA 드랍, FE adapter mock 영구** | [[decisions/cpia-d3-ewma-drop-2026-05-18]] |
| D-4 | ChatMessage source | **본 cycle mock 유지** + 다음 cycle 연결 (Hybrid) | `mock_chat_sequence.json` 그대로 |

### D-5 ~ D-12 권고 confirm (카탈로그 시점)

| # | 결정 | 채택 |
|---|---|---|
| D-5 | SitesSummary 누적 3 필드 | mock 유지 (hard-code) |
| D-6 | checkpoint state 읽기 path | `graph.aget_state(thread_id=run_id)` |
| D-7 | ai_mapped_path PoC fallback | `f"{l5_disc} > {l6_main} > {wa}"` |
| D-8 | SitesSummary.today_count 단위 | activity 단위 |
| D-9 | AgentStatus 정적 메타 source | BE FastAPI hard-code 반환 |
| D-10 | OptimizerOutput shape adapter | similar_cases / recommendations text 추출 |
| D-11 | RawDataRow.equipment source | API layer 가 EquipmentAllocation join |
| D-12 | ReportDetail.optimizer N rows | ~~FE type 변경 `optimizer: OptimizerOutput[]`~~ → **2026-05-18 실 구현 확정**: [[decisions/cpia-optimizer-array-grain-2026-05-18]] |
| D-13 | SCurvePoint time-series source | plan-only derive |
| D-14 | forecasts assessment vs risk_level | endpoint 응답에 risk_level 만 노출 |

---

## 2026-05-18 신규 결정 (9 건)

본 cycle (fe-be-bridge-delta-and-decisions) 의 사용자 의도 = "FE 시각화 절대 X / BE 가 FE 기획 따라가야 함 / 시연 안 보고 연결 자체 우선".

| # | 결정 | brain slug |
|---|---|---|
| **D-3 REVISED** | ProductivityDiagnosis EWMA 드랍 — BE endpoint 안 만듦, FE diagnosis-adapter.ts mock 영구 | [[decisions/cpia-d3-ewma-drop-2026-05-18]] |
| **G-1 Q1** | WPSummaryRow grain = (wa, l6_main, company) triplet — forecasts.wa 컬럼 추가 + Forecaster 재구조 | [[decisions/cpia-wpsummary-grain-2026-05-18]] |
| **G-1 Q2** | progress_pct 누적 today_qty path = mapped_history 신규 PG 테이블 (Atomizer INSERT + FastAPI SELECT) | [[decisions/cpia-wpsummary-progress-path-2026-05-18]] |
| **G-1 Q3** | wp_id 산식 = `f"{wa}-{slug(l6_main)}-{slug(company)}"` triplet 명시 | [[decisions/cpia-wpsummary-wpid-formula-2026-05-18]] |
| **G-2 통합** | /tasks 페이지 BE 정합 — DailyTask + AgentStageProgress 둘 다 BE 산출 (mapped_history 활용 + LangGraph state 단계별 binary + FE 시각화 단순화) | [[decisions/cpia-tasks-page-be-formulas-2026-05-18]] |
| **G-2 item** | AgentTaskItem.status 5 치 — BE 가 5 치 다 산출 (FE 시각화 chip/색상/아이콘 그대로). processing / blocked 정의 BE 협의 사항 | [[decisions/cpia-tasks-item-status-2026-05-18]] |
| **G-8 (D-12 실 구현)** | OptimizerOutput 배열 — BE 배열 응답 + FE OptimizerOutput[] 수신. PG row grain 그대로 흐름 | [[decisions/cpia-optimizer-array-grain-2026-05-18]] |
| **G-10** | hil_1 resume = api-contract §3.8 그대로 + FE 가 corrections 객체 변환 산식 추가 (~30 lines). BE FastAPI 구현 0 → 신규 | [[decisions/cpia-hil1-resume-connection-2026-05-18]] |
| **G-3~G-9 일괄** | G-3 WBSNode (활동 마스터 → 트리 derive) + G-4 ReportDaily + G-5 fleet_kpi + G-6 site_distribution + G-7 AgentStatus 동적 = BE 연결. G-9 s_curve 산식 정의 다음 cycle 보류 | [[decisions/cpia-six-gaps-decisions-2026-05-18]] |

---

## 다음 cycle 위임 (future)

| 영역 | 사유 | 트리거 |
|---|---|---|
| ChatMessage Hybrid (DB derive) | 본 cycle 산출 (FastAPI + BFF) 완결 후 | 본 cycle 종료 + 시연 후 |
| G-9 s_curve BE 가공 산식 정의 | 데이터 있지만 FE 형식 가공 단계 미정의 | BE 구현 cycle Phase 0 합의 |
| ProductivityDiagnosis BE adapter | ~~Phase 2~~ → **DROPPED 2026-05-18** | (D-3 EWMA 드랍 결정으로 폐기) |
| processing / blocked status BE 정의 | AgentTaskItem.status 5 치 산식 | BE 구현 cycle Phase 0 합의 |
| `/dashboard/diagnosis-preview` 라우트 제거 | dead route | D-3 EWMA 드랍 확정 후 |
| `mock_simulation.json` shape 정정 또는 삭제 | dead fixture | scope 정리 cycle |
| ReviewItem.alternative_wps Phase 2 | Mapper LLM 이 top-3 후보 반환 확장 | Mapper 개선 cycle |
| SCurvePoint time-series historical 누적 | daily_reports row 누적으로 actual 곡선 | 30 일 + 운영 후 |

---

## mock 유지 (BE 신규 산식 안 만듦)

- MiddleOfficeAutomation 4 row (정적 메타)
- ImpactTrendPoint 월별 cumulative_fte (historical 미보유)
- FE 하드코딩 mock 3 종: AgentWorkflow.COUNTS / NotificationBell.MOCK_NOTIFS / UserMenu.USERS
- daily_reports.report_md (906 chars markdown)
- **ProductivityDiagnosis 13 field — D-3 EWMA 드랍 (2026-05-18), FE diagnosis-adapter.ts 영구 mock**
- **ForecastChart 예측 / 회복 곡선 — FE adapter mock 영구 (D-3 정합)**

---

## 본 cycle 산출 (2026-05-17 + 2026-05-18)

### Catalog (data-contract/, 6 파일)
1. `data-contract/INDEX.md` (이 파일, 2026-05-18 갱신)
2. `data-contract/frontend_catalog.md` (~432 lines, PR #22 갱신 예정)
3. `data-contract/backend_catalog.md` (~412 lines, PR #19 갱신 예정)
4. `data-contract/crosswalk.md` (~430 lines)
5. `data-contract/gaps.md` (~310 lines, §F 2026-05-18 갱신 예정)
6. `data-contract/_meta.json` (2026-05-18 갱신 완료)

### Design spec (1 파일)
7. `docs/superpowers/specs/2026-05-17-cpia-fe-be-bridge-design.md`

### Brain decisions (9 신규 — 2026-05-18)
- `decisions/cpia-d3-ewma-drop-2026-05-18`
- `decisions/cpia-wpsummary-grain-2026-05-18`
- `decisions/cpia-wpsummary-progress-path-2026-05-18`
- `decisions/cpia-wpsummary-wpid-formula-2026-05-18`
- `decisions/cpia-tasks-page-be-formulas-2026-05-18` + (REVISED) `decisions/cpia-tasks-total-count-mock-2026-05-18`
- `decisions/cpia-tasks-item-status-2026-05-18`
- `decisions/cpia-optimizer-array-grain-2026-05-18`
- `decisions/cpia-hil1-resume-connection-2026-05-18`
- `decisions/cpia-six-gaps-decisions-2026-05-18`

### Feedback memory (2 신규 — 2026-05-18)
- `feedback_natural_lang_explain.md` — 함수명/코드 형식만 X. UI + 의도 + BE 산식 자연어 풀어 설명 의무
- `feedback_unify_fe_be_formula.md` — FE↔BE 공식 차이 시 한 쪽으로 일원화 (5단계 분석)

---

## 사용자 의도 (2026-05-18 명시)

1. **FE 가 기획 source of truth** — BE 가 따라가야 함
2. **FE 시각화 / 디자인 요소 절대 X** — chip / 색상 / 아이콘 / 라벨 그대로 유지
3. **억지 매핑 금지** — FE↔BE 공식 차이 시 한 쪽으로 일원화
4. **시연 안 보고 순수 연결 우선** — BE↔FE 통신이 깨끗하면 OK, 시연 가시화는 후속
5. **자연어 설명 의무** — 함수명/코드 형식만 X

---

## 다음 단계

본 cycle 종결 후:

1. **frontend_catalog + backend_catalog + crosswalk + gaps 본격 갱신** — PR #22 component / type / 5 섹션 매핑 + PR #19 BE 변경 + 10 gap 표 (~290 line incremental)
2. **BE 구현 cycle plan 작성** — Forecaster wa 재구조 + mapped_history schema + Atomizer 변경 + Optimizer 배열 + tasks BE + hil_1 resume + 5 BE 연결 endpoint. superpowers writing-plans 형식
3. **조형준 프로님 PR + main 머지** — main 머지 결정은 조형준 프로 권한

전역 룰:
- PoC 마감 = 2026-06-05 (D-18 남음, 2026-05-18 기준)
- pipeline/.venv/bin/python3 절대경로 (uv 관리)
- POSTGRES_URL=prod (5532 cloudflared tunnel cpia-pg.zoai.uk)
- 한자 0 / 한국어 작성
