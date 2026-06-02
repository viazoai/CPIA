# CPIA Agent Tasks — 단계별 카드 스키마 설계

> 작성: 2026-06-01 · 대상 화면: `/tasks` (Agent Tasks) 맨 오른쪽 "단계별 건 목록" 카드
> 스코프: 8개 Agent 단계별 카드 컬럼 스키마 확정 → 구현 → UI 검증.
> 근거: 실 DB 스키마 + `view_builder.py` 실 코드 전수 확인 (목업 5회 반복으로 사용자 확정).

---

## 1. 문제

맨 오른쪽 카드(`web/app/components/tasks/AgentTaskItemList.tsx:48-78`)가 **8개 Agent 단계 전부를 동일한 4컬럼**(ID · 공종 · BP사 · 상태)으로 렌더한다. 타입도 고정(`web/lib/types.ts:96` `AgentTaskItem = {id, trade, contractor, status}`).

그 결과 단계별로 의미가 안 맞는 값이 컬럼에 들어간다 (`web/app/api/runs/items/route.ts`):

| 단계 | 현재 컬럼에 들어가는 실제 값 | 문제 |
|---|---|---|
| Collector | 공종=글자 `"파일"`, BP사=파일명 | 라벨이 거짓말 |
| Parser | BP사=`work_content`(작업내용) | 업체·물량·L6 안 보임 |
| Mapper | BP사=`wa`(=Work Area FAB/CUB) | wa 를 BP사로 오표기 |
| 나머지 | l6_main + wa 를 공종/BP사 칸에 | 단계 고유 정보 소실 |

**근본 원인**: "행(row)의 단위"가 단계마다 다른데(파일/활동/업체/공종) 단일 스키마를 강제. → 단계별 고유 스키마로 분리.

---

## 2. 확정 결정

### 결정 1 — 행의 단위: **단계별 고유 단위** (A안 확정)
각 단계가 진짜 처리 단위로 행을 보여주고, 컬럼도 단계마다 다르게 구성한다.

### 결정 2 — 단계별 컬럼 (8단계 확정)

| # | 단계 | 단위 | 컬럼 |
|---|------|------|------|
| 01 | Collector 수집 | 파일 | 공종 · 업체명 · 파일명 · 상태 |
| 02 | Parser 파싱 | 업체 × 시트카테고리 | 공종 · 업체명 · 카테고리 · 건수 · 상태 |
| 03 | Mapper 매핑 | 활동(앵커=물량시트) | 공종 · 업체명 · 작업내용 · WBS · 상태 |
| HIL | Human Review 검토 | 저확신 매핑 | 공종 · 업체명 · 작업내용 · WBS · 확신도 · 상태 |
| 04 | Atomizer 적재 | 활동 적재 | 공종 · 업체명 · 작업내용 · 작업사항 · 상태 |
| 05 | Exporter 출력 | 통합 1건 | 일자 · 통합작업일보 · 활동건수 · 상태 |
| 06 | Forecaster 진단 | WP (wa, l6_main, company) | Work Area · WBS · 업체명 · 지연일 · 진단 · 상태 |
| 07 | Optimizer 조언 | 고위험 WP | Work Area · WBS · 업체명 · 지연일 · 단축가능일 · 진단 · 상태 |

**용어 통일**: `공종` = 건축/토목 레벨(`l5_disc`), `WBS` = L6(`l6_main`), `Work Area` = `wa`(FAB/CUB).

---

## 3. 단계별 데이터 출처 (실 코드/스키마 검증)

### 01 Collector (파일 단위)
- 파일명·상태: `data/input/YYYYMMDD/` 디렉토리 (`web/app/api/runs/items/route.ts` Collector 분기)
- 업체명: 파일명 또는 `parser_report_meta.bp_name`
- ⚠ **공종(건축/토목)**: 파일/업체 → 공종 매핑이 현재 DB에 직접 없음. 업체-공종 매핑 테이블 또는 `parser_activities.l5_disc` 의 업체별 대표값 집계 필요. **유일한 데이터 갭.**

### 02 Parser (업체 × 시트카테고리)
- 카테고리 = 시트별 4꼭지: 작업내용(시트1) · 인원(시트2) · 장비(시트3) · 물량(시트4)
- 건수 = 각 시트 처리행수 (`COUNT`)
  - 시트1 작업내용 → `parser_reports.bp_summaries` (BPSummary, `state.py` `work_text_today`)
  - 시트2 인원 → `parser_job_allocations`
  - 시트3 장비 → `parser_equipment_allocations`
  - 시트4 물량 → `parser_activities`
- 공종 = `l5_disc`, 업체명 = `company`

### 03 Mapper (활동 단위, 앵커=물량시트)
- `mapper_activities`: 공종=`l5_disc`, 업체명=`company`, 작업내용=`work_content`(시트4 액티비티), WBS=`l6_main`, 상태=매핑완료
- (`wa` 도 여기서 결정되나 Mapper 카드엔 미표시)

### HIL Human Review (저확신 매핑)
- Mapper 와 동일 + WBS 옆 확신도
- `mapper_activities.requires_review = true`, 확신도=`mapping_conf`, 대안=`alternatives`(top-K)

### 04 Atomizer (활동 적재)
- 공종=`l5_disc`, 업체명=`company`
- **작업내용 = 시트1** (`parser_reports.bp_summaries` work_text_today)
- **작업사항 = 시트4** (`mapper_activities` work_content/물량)
- 상태=적재완료 (Chroma `daily_activities`)

### 05 Exporter (통합 1건)
- 그날 통합 작업일보 1행만. `daily_reports` 에서 `bp_name IS NULL`(=종합)
- 컬럼: 일자 · 통합작업일보명 · 활동건수 · 상태

### 06 Forecaster (WP grain) — **report 경로 검증 완료**
- **출처: `pipeline/agents/optimizer/view_builder.py`** (report 사전집계 jsonb, `daily_reports.wp_summary_jsonb`/`quadrant_jsonb`)
- WP grain = **(wa, l6_main, company)** — `view_builder.py:260` `GROUP BY ma.wa, ma.l6_main, ma.company`, `:406` `_wp_id_of(wa,l6_main,company)`
- Work Area = `wa`. **현재 `:749` 에서 `wp_name = "{wa} {l6_main}"` (예: "FAB 철근콘크리트공사")로 붙어 보임 → 컬럼으로 분리만 하면 됨. grain 변경 불필요.**
- WBS = `l6_main`, 업체명 = `company`
- 지연일 = WA별 `delay_days` (`view_builder.py:1247` `wa_delay`)
- 진단 = status (`normal`/`caution`/`risk` = 정상/주의/이상)
- 상태 = 처리완료 여부(진단과 별개)

### 07 Optimizer (고위험 WP)
- Forecaster 와 동일 + 지연일 옆 **단축가능일**
- 단축가능일 = `recovery_days` (`scenarios.by_wp` base_p50, report "공기 단축" 컬럼과 동일 source — `WPSummaryTable.tsx:75-83`, `WPSummaryRow.recovery_days`). **실 산출, 추가 계산 불필요.**

---

## 4. 구현 접근 (제안)

단계별 컬럼이 다르므로 고정 4필드 타입을 **per-step 컬럼 config + generic row** 로 교체.

**4.1 타입 (`web/lib/types.ts`)**
```ts
export interface AgentColumn { key: string; label: string; align?: "left" | "right"; mono?: boolean; }
export type AgentItemTone =
  | "done" | "processing" | "received" | "hil_pending" | "blocked"  // 기존 상태
  | "normal" | "caution" | "risk";                                  // 진단 톤
export interface AgentTaskRow {
  id: string;
  values: Record<string, string>;   // column.key → 표시값
  statusLabel: string;
  statusTone: AgentItemTone;
}
```

**4.2 컬럼 정의 단일 source (`web/lib/agent-task-schema.ts` 신규)**
- `AGENT_COLUMNS: Record<AgentName, AgentColumn[]>` — §2 표 그대로.
- API 두 곳과 컴포넌트가 공통 참조 → 헤더/키 불일치 방지.

**4.3 렌더 (`AgentTaskItemList.tsx`)**
- props 를 `{ agent, columns, rows }` 로 변경. 고정 `<th>공종/BP사</th>` 제거, `columns.map` 으로 동적 헤더 + `row.values[col.key]` 렌더. 상태칩은 `statusTone`/`statusLabel` 기반.

**4.4 데이터 produce (단계별 SQL → AgentTaskRow)**
- 실 데이터: `web/app/api/runs/items/route.ts` — 단계별 분기에서 §3 출처대로 `values` 채움.
- mock: `web/app/api/mock/agent-tasks/[date]/route.ts` — 동일 shape.
- Forecaster/Optimizer 는 `daily_reports.wp_summary_jsonb`/`optimizer_view_jsonb`(report 경로) 에서 가져와 `wa` 를 분리 컬럼으로.

**4.5 페이지 (`tasks/page.tsx`)**
- `DetailData.items` 및 `itemsForAgent` 타입을 새 shape 로. 선택 agent 의 `{columns, rows}` 를 카드에 전달.

---

## 5. 디자인 불가침
FE 정교화 시 layout/style/markup 변경 금지 규칙(시연자 의도 보존)에 따라, **카드 외형/그리드/색은 유지**하고 컬럼 구성과 데이터 매핑만 바꾼다. 표 셀 추가(가변 컬럼)는 기존 카드 골격 안에서 처리.

---

## 6. 검증 계획 (Done 정의)
1. `npm run build` — 타입/빌드 통과 (결정론).
2. `npm run dev` (port 5536) → `/tasks` 진입 → 단계 클릭하며 8단계 카드가 §2 컬럼대로 바뀌는지 Playwright 스크린샷.
3. 단계별 1건 이상 실 값 확인 (Collector=파일행, Parser=시트카테고리, Forecaster=FAB/CUB 분리 등).
- DB 도달 불가 시: mock 경로(`CPIA_DEMO_FALLBACK`) 또는 fixture 로 대체하고 그 사실을 보고.

---

## 7. 스코프 밖
- BE 신규 테이블(Collector 공종 매핑)은 이번 스코프에서 **갭으로 명시만**. 임시로 `l5_disc` 업체 대표값 또는 "—" 로 표시.
- pipeline/ (A_Track) 코드 변경 없음 — 본 작업은 web/ (B_Track) 한정.

---

## 8. 진행/디버그 메모 (compaction 대비, 2026-06-01)

**FE 상태**: 8단계 카드 스키마 구현+검증 완료. 09-24 run 풀 데이터 렌더 확인(Forecaster 13행 FAB/CUB 분리, Optimizer 단축가능일). 변경: `web/lib/types.ts`, `web/lib/agent-task-schema.ts`(신규), `AgentTaskItemList.tsx`, `api/runs/items/route.ts`, `api/mock/agent-tasks/[date]/route.ts`. **main 워킹트리 미커밋.** 폴백/wa재구성 안 함(사용자 지시) — 카드는 실행된 report 뷰(wp_summary)만 표시.

**미해결 (pipeline/A_Track)**: 09-25 run(`235ff35d`, 오늘 15:37 completed)에서 Forecaster/Optimizer 카드가 빔.
- 원인 funnel: mapper 330행 → **단 2개 (company,l6) 그룹**(중원엔지니어링 NPW배관공사/PCW배관공사)로만 매핑 → forecasts=2(그룹수와 일치, 정상) → BUT `daily_reports.wp_summary_jsonb = 0`.
- 입력 정상 확인: is_mock=false, plan(`activity_master` 중원 NPW13/PCW15) 존재, site=m15x-ph3-ibl 일치, run_id 일치(매칭버그 아님).
- 대조 09-24: forecast 그룹 29 → wp_summary 13(정상).
- wp_summary 쓰기경로 = `optimizer/agent.py:354` `v2_result.get("wp_summary")` (v2 builder). `_build_wp_summary`(view_builder.py:760)는 quadrant 전수 append(필터 없음)이므로 quadrant=0이면 wp_summary=0. `_build_quadrant`(:726 impact_rows GROUP BY site+date)는 2그룹 반환해야 정상 → **v2 view build 가 이 run 에 0 산출(런타임 에러 catch→backfill, agent.py:367 의심)**.
- 다음: pipeline venv 에서 optimizer v2 view build 를 run `235ff35d` 로 재현 → 예외/0산출 지점 확인. (FE 아님, A_Track. 그래프 완주 시 report 자동 표시가 목표 = prod 레벨.)
