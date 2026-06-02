# CPIA Agent Tasks — 단계별 카드 스키마 v2 (실 테이블 직독 + 데이터 유무 분기)

> 작성: 2026-06-02 · 대상 화면: `/tasks` (Agent Tasks) 맨 오른쪽 "단계별 건 목록" 카드
> 2026-06-01 스펙(`2026-06-01-cpia-agent-tasks-step-schema-design.md`)을 **대체**한다 — 데이터 출처를 `wp_summary` 파생뷰에서 각 단계 실 출력 테이블 직독으로 교정하고, 데이터 유무 자동 분기를 추가.
> 근거: 실 DB(run `f57e8ae0` = 09-24 시드) 전수 검증 + `pipeline/agents/atomizer.py`·`web/app/api/runs/items/route.ts`·`web/app/api/runs/progress/route.ts` 실 코드 정독.

---

## 1. 배경 — 왜 다시 설계하나

### 1.1 구현 유실
2026-06-01 스펙의 구현(커밋 `e632e55`)이 **직후 머지 `6b591a2`("Merge origin/main")에서 origin/main 구버전에 통째로 덮여 유실**됐다. `web/lib/agent-task-schema.ts`는 69줄 삭제, `web/lib/types.ts`는 91줄 회귀, `AgentTaskItemList.tsx`·`runs/items/route.ts`도 고정 4컬럼(`AgentTaskItem`)으로 롤백. 현재 main 워킹트리는 구버전 상태다(스펙 문서만 남음).

### 1.2 스펙의 데이터 출처 전제가 틀림
2026-06-01 스펙은 Forecaster/Optimizer 카드 데이터를 `daily_reports.wp_summary_jsonb`(report 파생뷰)에서 가져온다고 전제했다. 그러나:
- `wp_summary`는 `pipeline/agents/optimizer/view_builder.py`가 `l7_5_activity IS NOT NULL` 조건으로 `activity_master`를 `(company, l6, l7_5)` JOIN해 만든다.
- 실 prod run은 `pipeline/agents/parser.py:445`에서 `l7_5_activity=None` 하드코딩 → JOIN 전량 탈락 → `wp_summary`가 **빈다**.
- 실 DB 검증: `wp_summary`가 채워진 row는 **전부 `mapping_source='dummy_seed'`**(콜드스타트 시드). 즉 `wp_summary` 경로는 dummy 전용이다.

### 1.3 UI 데이터 흐름 (실 코드 확인)
```
/tasks 좌측 목록 = /api/mock/agent-tasks
    → pipeline_runs.report_date별 최신 run (is_mock 필터). 살아있는 run = 09-10~09-24 dummy_seed 시드
날짜 선택
    → /api/runs/progress?date=YYYY-MM-DD
        → SELECT ... FROM pipeline_runs WHERE report_date = date ORDER BY started_at DESC LIMIT 1  (run_id 확보)
    → /api/runs/items?run_id=&agent=
        → 단계별 카드 (본 스펙의 대상)
```
축은 `report_date`다. 카드는 그 날짜 run의 적재 데이터를 단계별로 보여준다.

### 1.4 시드 데이터의 성격
9월 24일 이전 run은 **"파서·매퍼까지 됐다"는 가정으로 `mapper_activities`/`parser_activities`를 직접 insert한 시드**다(엑셀을 매번 풀 파이프라인으로 돌리면 느려서, UI에서 실데이터를 보여주려고 적재). 따라서 시트1/2/3 부속테이블(`parser_reports.bp_summaries`/`parser_job_allocations`/`parser_equipment_allocations`)이 **없다**. 25일부터는 실 엑셀을 새로 파싱하지만, **이미 적재된 데이터를 읽어오는 방안이 최우선**이다.

---

## 2. 핵심 결정

### 결정 1 — 데이터 소스: 각 단계 실 출력 테이블 직독 ("Tasks 카드 기준")
Tasks 카드는 각 단계의 실 출력 테이블을 직독한다. reports 화면이 쓰는 `wp_summary` 파생뷰에 맞추지 않는다.
- Forecaster → `forecasts`, Optimizer → `optimizer_advice`(+`forecasts` JOIN), Atomizer/Mapper → `mapper_activities`(+`parser_activities` JOIN), Exporter → `daily_reports`.
- **진단 = `forecasts.risk_level`** (Tasks 기준).

> **트레이드오프 (명시):** reports 화면의 진단 SSOT는 `wp_summary.status`(4사분면 `_quadrant_of`, productivity×impact)이고 `risk_level`은 LLM 입력으로만 쓴다(2026-05-29 SSOT 결정). 본 스펙은 Tasks 카드를 `risk_level` 직독으로 가므로, reports의 `wp_summary.status`와 진단 축이 다를 수 있다(같은 WP에서 `status=caution`인데 `risk_level=정상`인 사례 존재). reports와의 진단 일원화는 **본 스코프 밖**(별도 작업)으로 둔다 — 사용자 결정 "Task 카드 기준으로 간다".

### 결정 2 — 가변 컬럼 골격 부활 (e632e55)
단계마다 행의 단위·컬럼이 다르므로 고정 4필드(`AgentTaskItem`)를 폐기하고 per-step 컬럼 정의(`AgentColumn`) + generic row(`AgentTaskRow`)로 표현한다. e632e55에서 유실된 골격을 되살린다.

### 결정 3 — 데이터 유무 자동 분기 (Collector / Parser)
적재 시드(부속테이블 없음)와 실 파싱 run(부속 있음)을 **날짜가 아니라 데이터 유무로 자동 분기**한다.
- **Parser**: 시트1/2/3 부속(`parser_reports.bp_summaries` + `parser_job_allocations` + `parser_equipment_allocations`) 합계 > 0이면 원안(4카테고리×건수), 0이면 업체별 활동건수 집계.
- **Collector**: `data/input/YYYYMMDD/` 디스크 파일이 있으면 실제 파일명, 없으면 "업체 작업일보" 폴백.

---

## 3. 8단계 컬럼 스키마 (실데이터 검증 — run `f57e8ae0`, 09-24)

용어: `공종`=`l5_disc`/`trade`(건축·토목 대분류), `WBS`=`l6_main`, `Work Area`=`wa`(FAB/CUB).

### 3.1 Collector (수집 단위)
- 컬럼: **공종 · 업체 · 파일명**
- 소스: `parser_activities` 업체별 + `data/input/YYYYMMDD/` 디스크.
- 분기: 디스크 파일 有 → `파일명=실제 파일`; 無(시드) → `파일명="{업체} 작업일보"`.
- 09-24 예시(파일 없음 → 폴백): `건축 · 선보 · 선보 작업일보` … (20개 업체)

### 3.2 Parser (데이터 유무 분기)
**(a) 부속 데이터 有 — 실 파싱 run**
- 컬럼: **공종 · 업체 · 카테고리 · 건수**
- 카테고리 4꼭지 = 작업내용(시트1 `parser_reports.bp_summaries`) · 인원(시트2 `parser_job_allocations`) · 장비(시트3 `parser_equipment_allocations`) · 물량(시트4 `parser_activities`). 각 처리행수 `COUNT`.

**(b) 부속 데이터 無 — 적재 시드 (09-24 이전)**
- 컬럼: **공종 · 업체 · 활동건수**
- `parser_activities` 업체별 `COUNT(*)`. 한 행 = 개별 활동(물량 항목). 09-24 예시: `건축 · 선보 · 48`, `건축 · OTIS · 8`(승강기 8호기), … 20개 업체 / 합계 171.
- (활동 행별 나열은 채택 안 함 — Parser 단계엔 `l7_5_activity`가 없어 `work_content`만 보이는데 업체 내 중복이 많아 카드가 도배됨. `l7_5` 세부활동 구분은 Mapper 이후에만 가능.)

### 3.3 Mapper (활동 단위)
- 컬럼: **공종(l5_disc) · 업체 · 작업내용 · WBS(l6_main)**
- 소스: `mapper_activities` + `parser_activities` JOIN(`pa.work_content`). 매핑 완료=`done`, `l6_main` NULL=`hil_pending`.
- 09-24 예시: `건축 · 삼표 피엔씨 · 계획 물량 달성, 다음 층 적층 연결 · PC공사`

### 3.4 Human Review (저확신 매핑)
- 컬럼: **공종 · 업체 · 작업내용 · WBS · 확신도**
- 소스: `mapper_activities`. `requires_review=true`=`hil_pending`, 확신도=`mapping_conf`(%).
- ⚠ 09-24 시드는 `requires_review=0`, `mapping_conf=1.0` 전부 → 요검토 0건(카드가 전부 검토완료로 뜸). 실 파싱 run에서 채워진다.

### 3.5 Atomizer (Chroma 적재 단위)
- 컬럼: **공종 · 업체 · WBS · 작업내용 · 조건**
- 소스: `mapper_activities` + `parser_activities` JOIN. `조건`=`mapper_activities.conditions`(`atomizer.py:67`이 적재 문서에 임베딩하는 narrative — 유사사례 검색의 핵심).
- 근거: `atomizer.py`는 1 활동=1 Chroma doc으로 적재하며 문서에 `작업내용 + 시공량 + 조건`을 넣는다. `조건`이 Mapper엔 없는, 적재 단계가 더하는 정보다.
- 09-24 예시: `건축 · 삼표 피엔씨 · PC공사 · 계획 물량 달성… · 정상` / `토목 · 장평건설 · 배수 공사 · 가시설 자재 미입고… · 자재미입고`
- 참고: doc_id=`sha256(date|company|l6|work_content)`로 dedup되어 실제 적재 doc은 171 활동 → 29개. 카드는 `mapper_activities` 활동 행(171) 기준으로 표시한다(적재 dedup 단위가 아니라).

### 3.6 Exporter (통합 1건)
- 컬럼: **일자 · 통합 작업일보 · 활동건수**
- 소스: `daily_reports`에서 `bp_name IS NULL`(종합) 1행. 활동건수=`pipeline_runs.atomized_count` 또는 `mapper_activities` 행수.

### 3.7 Forecaster (WP grain) — forecasts 직독
- 컬럼: **Work Area · WBS · 업체 · 지연일 · 진단**
- 소스: `forecasts` 직독.
  ```sql
  SELECT wa, l6_main, company, delay_days, risk_level
  FROM forecasts WHERE run_id = $1
  ORDER BY (risk_level='이상') DESC, (risk_level='주의') DESC, delay_days DESC NULLS LAST
  ```
- 진단=`risk_level`(이상→`risk`, 주의→`caution`, 정상→`normal` 톤). 지연일=`delay_days`(반올림, 0이면 그대로 0).
- ⚠ 09-24 검증: `delay_days`는 29행 전부 non-null이나 양수는 7건, 22건은 0. `risk_level='이상'`(16)과 지연일>0(7)이 불일치 — 지연일 컬럼은 0이 많다(forecaster 집계 특성, 본 스코프에서 표시만 함).
- 09-24 실 예시(정렬 상위, 지연 양수가 위로): `FAB · C/R 조성공사 · 해광 · 195일 · 이상`, `FAB · C/R 조성공사 · 신성 · 134일 · 이상`, `FAB · C/R 조성공사 · 한국 · 42일 · 이상` (나머지 22행은 0일)

### 3.8 Optimizer (고위험 WP) — optimizer_advice 직독
- 컬럼: **Work Area · WBS · 업체 · 지연일 · 단축가능일 · 진단**
- 소스: `optimizer_advice` + `forecasts` JOIN(wa/delay/risk 동기).
  ```sql
  SELECT oa.company, oa.l6_main, oa.recovery_distribution, f.wa, f.delay_days, f.risk_level
  FROM optimizer_advice oa
  LEFT JOIN forecasts f ON f.run_id=oa.run_id AND f.company=oa.company AND f.l6_main=oa.l6_main
  WHERE oa.run_id = $1
  ORDER BY (f.risk_level='이상') DESC, (f.risk_level='주의') DESC, oa.l6_main
  ```
- **단축가능일 = 대표 D+N**: `recovery_distribution`(예 `{"d+1":4,"not_recovered":1}`)에서 `not_recovered` 제외한 `d+N` 키 중 **카운트 최다**의 N → `"D+N"`. 동률이면 작은 N(빠른 회복) 우선. `d+N` 키가 없으면(전부 미회복) `"—"`.
  - `optimizer_advice`엔 `recovery_days` 스칼라가 없고 `recovery_distribution`(JSONB)만 있어 분포에서 대표값을 도출한다.
- 진단=`forecasts.risk_level`(JOIN). `optimizer_advice.forecast_assessment`는 쓰지 않는다 — 그 컬럼은 `forecasts.assessment`(코드 중간평가, 거의 "정상") 복사라 종합 진단과 다르다.
- 09-24 실 예시:
  - 회복분포 있음 → 대표 D+N: `FAB · 배수 공사 · 장평건설 · 30일 · D+1 · 주의` (`recovery_distribution={"d+1":3,"not_recovered":2}` → `d+1` 최다 → `D+1`)
  - 전부 미회복 → `—`: `CUB · PC공사 · 삼표 피엔씨 · 0일 · — · 이상` (`{"not_recovered":5}` → `d+N` 키 없음 → `—`)

---

## 4. 구현 접근

### 4.1 타입 (`web/lib/types.ts`) — e632e55 부활
```ts
export type AgentItemTone =
  | "done" | "processing" | "received" | "hil_pending" | "blocked"  // 처리 상태
  | "normal" | "caution" | "risk";                                  // 진단 톤
export interface AgentColumn { key: string; label: string; align?: "left" | "right"; mono?: boolean; }
export interface AgentTaskRow {
  id: string;
  values: Record<string, string>;   // column.key → 표시값
  statusLabel: string;
  statusTone: AgentItemTone;
}
```
구 `AgentTaskItem`(고정 4필드)은 제거. 사용처 5개 파일(types.ts / tasks/page.tsx / AgentTaskItemList.tsx / api/runs/items/route.ts / api/mock/agent-tasks/[date]/route.ts) 모두 신 타입으로 전환.

### 4.2 컬럼 정의 (`web/lib/agent-task-schema.ts` 신규)
- `AGENT_COLUMNS: Record<string, AgentColumn[]>` — Collector/Mapper/"Human Review"/Atomizer/Exporter/Forecaster/Optimizer 정적 정의.
- Parser는 분기로 컬럼 수가 달라지므로 두 변형을 둔다: `PARSER_COLUMNS_FULL`(공종·업체·카테고리·건수), `PARSER_COLUMNS_AGG`(공종·업체·활동건수).

### 4.3 데이터 produce (`web/app/api/runs/items/route.ts`)
- 응답 형태를 `{ ok, agent, columns, items }`로 확장 — **API가 `columns`도 반환**한다(Parser 분기로 컬럼이 동적이므로 FE 정적 참조 대신 API가 결정).
- 단계별 분기에서 §3 소스대로 `AgentTaskRow.values`를 채운다.
- **Parser 분기**: 먼저 `parser_reports.bp_summaries`+`parser_job_allocations`+`parser_equipment_allocations` 합계를 센다 → >0이면 `PARSER_COLUMNS_FULL`+4카테고리 rows, 0이면 `PARSER_COLUMNS_AGG`+업체별 활동건수 rows. 부분 채움(셋 중 일부 시트만 있는 run)이면 FULL 컬럼을 유지하되 빈 카테고리는 건수 `0`으로 표시한다(행 생략하지 않음).
- **Collector 분기**: 디스크 파일 유무로 `file` 값만 분기(컬럼은 동일).
- Forecaster/Optimizer는 §3.7·3.8 SQL 직독. 단축가능일은 `recovery_distribution` 파싱 헬퍼로 대표 D+N 산출.

### 4.4 mock (`web/app/api/mock/agent-tasks/[date]/route.ts`)
동일 `{columns, items}` shape로 맞춘다.

### 4.5 렌더 (`web/app/components/tasks/AgentTaskItemList.tsx`)
- props를 `{ agent, columns, rows }`로. 고정 `<th>` 제거, `columns.map`으로 동적 헤더 + `row.values[col.key]`. 상태칩은 `statusTone`/`statusLabel` 기반(`AgentItemTone` 9종 색).

### 4.6 페이지 (`web/app/(app)/tasks/page.tsx`)
- `DetailData.items` 및 `itemsForAgent`를 `AgentTaskRow[]`로, 선택 agent의 `{columns, rows}`를 카드에 전달. progress polling·sim 분기 로직은 유지.

---

## 5. 디자인 불가침
FE 정교화 시 layout/style/markup 변경 금지(시연자 의도 보존, `feedback_no_design_change`). 카드 외형·그리드·색은 유지하고 **컬럼 구성과 데이터 매핑만** 바꾼다. 가변 컬럼은 기존 카드 골격 안에서 `<th>`/`<td>` 가감으로 처리.

---

## 6. 검증 계획 (Done 정의 — CLAUDE.md §3.1)
1. `cd web && npm run build` — 타입/빌드 통과(결정론).
2. `npm run dev`(5537) → `/tasks` → **09-24** 선택 → 8단계 클릭하며 Playwright 스크린샷. 확인 포인트:
   - Parser = 업체별 활동건수(부속 0 → 집계 분기), Atomizer = 조건 컬럼, Forecaster = CUB/FAB·지연일·이상, Optimizer = 단축가능일 `D+N`/`—`.
3. 실 run `f57e8ae0`로 각 단계 1건 이상 실값 대조(본 스펙 §3 예시와 일치).
4. Parser FULL 분기 — **현 DB엔 부속테이블이 채워진 run이 없다**(전 run `bp_summaries`=0·`parser_job/equipment_allocations`=0행). 따라서 **목 데이터 단위 테스트(부속 있는 입력 → 4카테고리 컬럼·건수 고정 비교)를 우선 배치**하고, 첫 실 파싱 run 적재 시 e2e로 재확인한다.

---

## 7. 스코프 밖
- **reports 화면과의 진단 일원화**(`wp_summary.status` SSOT 통일) — 별도 작업. 본 스펙은 Tasks 카드 한정.
- `wp_summary`가 실 prod run에서 비는 근본 원인(`parser.py:445` `l7_5_activity=None`) — A_Track(pipeline) 작업.
- pipeline/(A_Track) 코드 변경 없음 — 본 작업은 `web/`(B_Track) 한정.

---

## 8. 실데이터 근거 (run `f57e8ae0`, 09-24, `mapping_source=dummy_seed` 171행)
- Collector: 디스크 파일 0 → 업체목록 20개.
- Parser: 부속 합계 0(작업내용 0·인원 0·장비 0), `parser_activities` 171 → 업체별 활동건수(선보 48 … 동신패널 1, 합 171).
- Mapper/Atomizer: `l5_disc`·`l6_main`·`wa`·`conditions`·`mapping_conf`(=1.0) 채워짐, `work_content`는 `parser_activities` JOIN.
- Human Review: `requires_review` true 0건.
- Forecaster: `forecasts` 29행, `risk_level` 이상16/주의4/정상9, `delay_days` 양수 7건.
- Optimizer: `optimizer_advice` 29행, `recovery_distribution` 29 채워짐(`{"d+1":N,"not_recovered":M}`), `wa`/`recovery_days` 스칼라 없음.
- Exporter: `daily_reports` 1행(`bp_name` NULL).
