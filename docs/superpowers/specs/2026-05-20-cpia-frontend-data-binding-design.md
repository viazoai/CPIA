# CPIA Frontend 정교화 — 데이터 연결성 + Mock 백업 설계

> 작성일: 2026-05-20 · 브랜치: A_Track · D-16 (마감 2026-06-05)
>
> **절대 규칙 — 디자인 불가침.** 시연은 조형준 프로님이 진행. 본 spec 의 어떤 task 도 `web/app/components/**/*.tsx` 의 JSX / Tailwind class / 색상 / 간격 / 컴포넌트 신설을 **포함하지 않는다**. 허용 범위는 ① PG 스키마 마이그레이션, ② `pipeline/agents/optimizer/view_builder.py` 등 BE 함수, ③ `web/app/api/mock/*/route.ts` 데이터 변환, ④ `web/lib/transforms.ts` / `web/lib/fixtures.ts` 의 SELECT 로직, ⑤ 표시값 case 변환 만.

---

## § 1. 배경

PR #33 머지 직후 cycle 자체는 atomizer → forecaster → optimizer → reporter 까지 통과 (Cycle5: mapper 146 / forecast 27 / opt 13 / report_md 3993). 그러나 사용자 (B 트랙) 가 6 탭 직접 점검한 결과 **11 area 데이터 연결성 결함** 이 발견됨. 시연 fallback 도 부재.

이 spec 은 각 area 마다 **현재 데이터가 어디 있는지 → 어디서 매핑이 끊겼는지 → 무엇과 무엇을 매칭해서 채울 건지 → BE 에 무엇을 추가하는지** 를 자연어로 풀어 설명한다.

## § 2. 목표

1. **5 탭 데이터 연결성 11 area fix.**
2. **Mock 백업 + 시연 fallback** — `CPIA_DEMO_FALLBACK=on` 시 사이클 안 돌아도 mock_*.json 원본대로 표시.
3. **디자인 불가침 보장.**

## § 3. 비목표

- Dashboard 페이지 (사이드바 메뉴에 없는 dead route).
- 새 페이지 / 새 컴포넌트.
- pipeline cycle 로직 변경 (이미 PR #33 + ef7c6cd 로 정리).

---

## § 4. Phase 0 — Mock 백업 인프라

### 4.1 현재 데이터 위치

`data/mock_*.json` 10개 파일. git HEAD 에 모두 있음. 각 파일의 역할:

| 파일 | shape | FE 어디서 쓰임 | PG 적재 필요? |
|---|---|---|---|
| `mock_sites.json` | list[6] (site_id/name/headcount 등) | 이미 `sites` 테이블에 적재됨 (is_mock=true 6 row) | ✅ 이미 완료 |
| `mock_sites_summary.json` | dict (4 KPI) | `loadReal:sites_summary` 가 PG SUM 으로 산출 | ❌ 산출 함수가 대체 |
| `mock_agent_status.json` | list[7] (Agent 메타 + active_count) | `loadReal:agent_status` 가 PG `pipeline_runs` 에서 산출 | ❌ |
| `mock_chat_sequence.json` | dict (date → ChatMessage[]) | `deriveChatSequence` 가 PG run 통계로 산출 | ❌ |
| `mock_agent_tasks.json` | dict (tasks/progress/items) | `/api/mock/agent-tasks` 가 PG 4 테이블 SELECT 로 산출 | ❌ |
| `mock_review_cards.json` | **list[13]** (id/bp_name/work_content/quantity/wp_id/...) | `/api/mock/review` 의 cards 가 `mapper_activities WHERE requires_review` SELECT | ✅ row 변환 필요 |
| `mock_wbs_tree.json` | dict (wbs tree) | `/api/mock/review` 의 wbs 가 `wbsTreeBuild` 로 산출 | ❌ |
| `mock_report.json` | **dict {daily, details}** (kpi/contractor_bars/quadrant/optimizer/wp_summary 등) | `/api/mock/report` 가 `daily_reports.*_jsonb` SELECT | ✅ row 변환 필요 |
| `mock_dashboard.json` | dict (fleet/sites) | dashboard 페이지 dead route | ❌ 제외 |
| `mock_simulation.json` | dict (home/tasks/report/dashboard 시퀀스) | 현재 import 없음 | ❌ 제외 |

→ **실 row 적재 대상 = 2 파일 (mock_review_cards + mock_report)** + 이미 적재된 sites.

### 4.2 매핑 끊긴 지점

현재 FE 데이터 소스가 모두 PG SELECT 로 변환 완료 (5945844 커밋). 그러나:
- PG 의 mock site 6 row 와 PoC site 1 row 가 한 테이블에서 SUM 됨 → mock 섞임 (§9 별도).
- 사이클이 데모 직전에 깨지면 mock fallback path 가 없음 → 빈 화면.

### 4.3 해결 — is_mock 컬럼 + 적재 스크립트 + env flag

**Step A — 마이그레이션** (`infra/postgres/migrations/<n>_add_is_mock.sql`):

7 테이블에 `is_mock BOOL NOT NULL DEFAULT FALSE` 추가. 기존 row 는 자동 false → 실 cycle 데이터 영향 0. partial unique index 의 컬럼 set 에 is_mock 미포함 → ON CONFLICT 영향 0.

```sql
ALTER TABLE pipeline_runs       ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_reports      ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE parser_activities   ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE mapper_activities   ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE forecasts           ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE optimizer_advice    ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
ALTER TABLE daily_reports       ADD COLUMN is_mock BOOL NOT NULL DEFAULT FALSE;
-- sites.is_mock 은 이미 존재.
```

**Step B — Mock row 적재 스크립트** (`tmp/backfill_mock_rows.py`, one-shot):

`mock_review_cards.json` (list[13]) 의 각 카드를 1 mapper_activity + 1 parser_activity row 로 변환. 한 가짜 run_id (UUID 고정, is_mock=true pipeline_run) 에 모두 묶음. 카드 field → mapper_activity column 매핑:

| mock card | mapper_activities 컬럼 |
|---|---|
| `bp_name` | `company` |
| `work_content` | parser_activities.work_content (join 시 표시) |
| `quantity` | `today_qty` |
| `unit` | `unit` |
| `ai_mapped_wp_id` (kebab `wa-l6`) | split → `wa` + `l6_main` (역변환) |
| `confidence` | `mapping_conf` |
| `status='unconfirmed'` | `requires_review=TRUE` |
| `alternative_wps` | `alternatives` jsonb |

`mock_report.json` (daily + details) 는 daily_reports 1 row (date=2025-09-25, run_id=가짜) 로 변환 — `details` 의 kpi/contractor_bars/trade_bars/quadrant/wp_summary/optimizer/scenarios/raw_data → 동일 이름 jsonb 컬럼 (existing daily_reports schema). productivity 컬럼만 빈 dict.

스크립트 실패 시 `git show HEAD:data/mock_*.json` 으로 복원 후 재실행.

**Step C — route.ts 의 env 분기**:

5 route.ts (`/api/mock/agent-tasks`, `/review`, `/consolidated`, `/report`, `/dashboard`) + `lib/fixtures.ts:loadReal` 의 모든 SELECT 에 `WHERE ... is_mock = ${useMock}` 추가. `useMock = process.env.CPIA_DEMO_FALLBACK === "on"`. 기본 false → 실 cycle 데이터.

```ts
// 예: review/route.ts
const useMock = process.env.CPIA_DEMO_FALLBACK === "on";
const cardRows = await sql`
  SELECT ... FROM mapper_activities ma ...
  WHERE ma.requires_review = TRUE AND ma.is_mock = ${useMock}
  ORDER BY ma.mapping_conf ASC NULLS FIRST
`;
```

**BE 추가 명세:**
- migration 파일 1개 (위)
- `tmp/backfill_mock_rows.py` 1개
- route.ts 5개 + fixtures.ts 1개 — 각 SQL 에 `is_mock` 조건 추가 (한 줄씩)

### 4.4 인수 기준

- `unset CPIA_DEMO_FALLBACK` (default): 실 cycle 데이터만 표시 (mock 6 site 제외)
- `CPIA_DEMO_FALLBACK=on`: 5 탭 모두 mock_*.json 원본대로 표시. 사이클 안 돌아도 OK
- `CREATE INDEX ... WHERE site_id IS NOT NULL` partial unique index 가 영향 받지 않음 확인 (cycle 1 회 재실행 후 daily_reports INSERT 정상)

---

## § 5. Tasks 탭 fix (3 area)

### 5.1 Parser items 빈 목록

**현재 데이터 위치:**
- `parser_activities` (PG): parser 가 시트4 (물량) 파싱한 결과. (run_id, idx, zone, trade, bp_code, company, scope, work_content, unit, plan_total_qty, yesterday_cum_qty, today_qty). 한 cycle 당 292 row 적재됨.
- FE 의 Tasks 페이지 (`app/(app)/tasks/page.tsx`): 좌측 Daily 목록 → 중앙 Agent 단계 → 우측 단계별 건 목록. 우측은 `AgentTaskItemList` 컴포넌트가 `items[selectedAgent]` 배열을 그대로 렌더.
- `agent-tasks/route.ts:82` 가 `items["Parser"] = []` 빈 배열로 초기화.

**매핑 끊긴 지점:**
사용자가 중앙에서 "02 Parser" 클릭하면 우측이 selectedAgent="Parser" 가 되고 `items["Parser"]` 를 렌더. 그게 빈 배열이라 "표시할 건이 없습니다" 메시지만 나옴. BE 는 parser_activities 에 292 row 가 있는데도 SELECT 안 함.

**해결:**
agent-tasks/route.ts 의 dStr loop 안에서 parser_activities SELECT 한 번 추가. 한 row → 한 AgentTaskItem (`{id, trade, contractor, status}`) 변환.

`trade` 필드는 parser_activities 의 어떤 컬럼을 쓸지: `trade` 컬럼이 가장 자연스럽지만 빈 값 가능 → `trade || work_content` fallback. `contractor` = `company`. `status` = 모든 parser row 는 mapper 로 넘어갔으므로 "done" 고정.

**BE 추가:**
- agent-tasks/route.ts 에 SQL 1개 + map 한 줄. 신규 함수/마이그레이션 없음.

**같은 패턴으로 다른 agent items 도 보강** (시간 허락 시):
- Collector items = parser_reports 1 row (전체 일보 = 1 건)
- HIL Review items = mapper_activities WHERE requires_review (이미 있는 SELECT 재사용)
- Atomizer/Exporter/Forecaster/Optimizer items = 각 테이블 SELECT
- 시연 우선순위는 **Parser + Mapper** 만 — 다른 agent 클릭 빈도 낮음

**인수 기준:**
- Parser 클릭 → 292 건 (혹은 cap 후 N 건) 표시
- 첫 item 의 contractor 가 "창원기전" 등 실 BP명

### 5.2 Mapper 12 cap

**현재 데이터 위치:**
- mapper_activities: 한 cycle 의 모든 매핑 row (146-292). 사용자 신고 "292/292 인데 보이는건 50개" — 실측은 12개 (사용자 인지 오류).
- `agent-tasks/route.ts:56` 에 `LIMIT 12` 하드코딩.

**매핑 끊긴 지점:**
LIMIT 12 가 의도적이었으나 (UI 성능) 시연 시 "292 중 12만 보임" 이 부자연스러움.

**해결:**
LIMIT 200 으로 상향. 200 미만이면 다 보임. 200 초과 시연 가능성 낮음. ORDER BY (mapping_conf ASC NULLS FIRST) 는 유지 — 낮은 신뢰도부터 노출.

**BE 추가:**
- SQL 한 줄 변경. 없음.

**인수 기준:**
- Mapper 클릭 → 200 건 (또는 전체) 표시

### 5.3 헤더 "접수 0건 · 처리 0건 · 완료율 0%"

**현재 데이터 위치:**
- Daily 목록 좌측 (`DailyTaskList`) 에 표시되는 헤더는 컴포넌트 props 의 `tasks[selectedDate]` 의 카운트.
- `DailyTask` type: `{date, total_count, progress_percent, status, has_anomaly}`.
- `agent-tasks/route.ts:46`: `total_count: 0` 하드코딩.

**매핑 끊긴 지점:**
total_count 가 항상 0 → 헤더 "접수 0건". progress_percent 는 deriveProgressPercent 산출됨 (60% 등 표시) — 이 함수는 OK. 처리 0건 / 완료율 0% 는 헤더 텍스트가 "{processed}건 / {percent}%" 로 보임. processed 가 어디서 오는지 컴포넌트 확인 필요. 일단 total_count 만 0 → 사용자 신고 메시지의 "접수 0건" 부분.

**해결:**
total_count = parser_activities 의 한 dStr count (= 일일 활동 건수). 같은 deriveStageProgress 의 `parser_acts` 값 재사용 가능 → SQL 1번만 호출.

processed 도 컴포넌트가 표시한다면 progress 의 `processed` 필드 (= `mapper_acts` count) 가져와야 함. DailyTask type 에 processed 없다면 컴포넌트가 별도로 progress 에서 derive 중 — `DailyTaskList` 컴포넌트 소스 확인하여 데이터 path 확정.

**BE 추가:**
- agent-tasks/route.ts 에서 deriveStageProgress 결과의 parser_acts 를 total_count 로 전달. SQL 추가 없음.

**인수 기준:**
- 헤더 "접수 292건 · 처리 292건 · 완료율 100%" (mapper 완주 시)

---

## § 6. Review 탭 fix (3 area)

### 6.1 wbs root 소문자

**현재 데이터 위치:**
- `wbsTreeBuild` (`web/lib/transforms.ts:162`) 가 PG `activity_master` 그룹화 후 트리 빌드. root.name = `siteId` (= "m15x-ph3-ibl" 그대로).
- 사이트 식별자는 PG `sites.site_id` 컬럼 (kebab lower).
- `sites.name` 컬럼 = "M15X Ph-3 IBL" (사람 친화 이름).

**매핑 끊긴 지점:**
root.name 이 PG sites.name 아닌 siteId 그대로. 트리 표시에 식별자가 노출되어 어색.

**해결:**
review/route.ts 가 siteRow 로 PG sites.name 을 이미 가져오니, wbsTreeBuild 시그니처에 siteName 인자 추가 → root.name = siteName. 또는 wbsTreeBuild 가 sites 테이블 자체에서 SELECT.

sites.name 컬럼 우선 — "M15X Ph-3 IBL" 같이 케이스 보존된 이름. siteId.toUpperCase() 단순 변환보다 자연스러움.

**BE 추가:**
- wbsTreeBuild 시그니처: `(siteId: string)` → `(siteId: string, siteName: string)`. route.ts:18 의 호출부에서 siteName 전달. 신규 SQL 없음.

**인수 기준:**
- 트리 root = "M15X Ph-3 IBL"

### 6.2 wbs 알림 14736 → 63 (cartesian product fix)

**현재 데이터 위치:**
- `mapper_activities WHERE requires_review = TRUE AND pr.site_id = 'm15x-ph3-ibl'` 의 실 row 수 = **63 건**.
- `wbsTreeBuild` 의 SQL (`transforms.ts:165`):
  ```sql
  FROM activity_master am
  LEFT JOIN mapper_activities ma ON ma.wa = am.wa AND ma.l6_main = am.l6_main
  LEFT JOIN forecasts f ON f.run_id = ma.run_id AND f.l6_main = ma.l6_main AND f.company = ma.company
  ```
  → COUNT(*) FILTER (WHERE ma.requires_review) 가 **14736** (233배 폭발).
- 폭발 원인: ma JOIN 에 `pr.site_id` 제약 없음 (다른 site 의 ma 까지 포함) + forecasts 다중 row JOIN 으로 row 곱.

**매핑 끊긴 지점:**
사용자 신고 "14736 알림". 실제 63 이어야 함.

**해결 — 별도 CTE 로 review_count 와 worst_risk 를 미리 집계 후 LEFT JOIN:**

```sql
WITH review_agg AS (
  SELECT ma.wa, ma.l6_main, COUNT(*) AS review_count
  FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
  WHERE pr.site_id = $1 AND ma.requires_review = TRUE AND ma.is_mock = $2
  GROUP BY ma.wa, ma.l6_main
),
forecast_agg AS (
  SELECT f.l6_main, f.company,
         MIN(CASE f.risk_level WHEN '이상' THEN 1 WHEN '주의' THEN 2 ELSE 3 END) AS worst_risk
  FROM forecasts f JOIN pipeline_runs pr USING(run_id)
  WHERE pr.site_id = $1 AND f.is_mock = $2
  GROUP BY f.l6_main, f.company
)
SELECT am.site_id, am.wa, am.l5_disc, am.l6_main,
       COALESCE(ra.review_count, 0) AS review_count,
       fa.worst_risk
FROM activity_master am
LEFT JOIN review_agg ra USING (wa, l6_main)
LEFT JOIN forecast_agg fa ON fa.l6_main = am.l6_main AND fa.company = am.company
WHERE am.site_id = $1
```

**검증 호출 결과 (이 spec 작성 중 실측):**
- 위 CTE의 `SUM(review_count)` = **63** ← 정확.
- 현재 코드의 cartesian sum = 14736.

**BE 추가:**
- wbsTreeBuild 의 SQL 통째로 교체. 함수 시그니처 그대로 (return WBSNode). 신규 함수 없음.

**인수 기준:**
- root review_count = 63
- 부모 노드 (FAB / CUB 등) 의 review_count = 자식 leaf 합과 일치
- 다른 site 의 mapper 데이터 영향 없음

### 6.3 wbs 노드 클릭 → 카드 0/50

**현재 데이터 위치:**
- wbsTreeBuild leaf node id = `${wa}::${l5_disc}::${l6_main}` (3 segment, `::` separator)
  - 예: `FAB::전기::CABLE TRAY공사`
- review_cards 의 `ai_mapped_wp_id` = `deriveWpIdAndPath(wa, l6_main)` 결과 = `${safe(wa)}-${safe(l6_main)}` (2 segment, `-`, lowercase)
  - 예: `fab-cable-tray공사`
- review/page.tsx:28 의 `collect` 함수: 선택된 노드 하위에서 `type === "work_package"` leaf 의 id 들 모음
- review/page.tsx:43: `wpIds.includes(c.ai_mapped_wp_id)` 비교

**매핑 끊긴 지점:**
leaf id 와 card wp_id 의 format 이 완전히 다름 (segment 수 + separator + case). 100% 매칭 실패 → 모든 wbs 클릭이 "0개 표시".

**해결 — leaf id 만 deriveWpIdAndPath 의 wp_id 로 통일:**

`wbsTreeBuild` 의 leaf 노드 생성 부분 (`transforms.ts:220` 부근):
```ts
const l6Node: WBSNode = {
  id: deriveWpIdAndPath(r.wa, r.l6_main, siteName).wp_id,  // ← 통일
  type: "work_package",
  name: r.l6_main,
  ...
};
```

**왜 page.tsx 무변경으로 충분한가:**
- page.tsx:30 collect 는 leaf id 만 모음 (trade/building node id 는 무관)
- page.tsx:33 find 는 selectedId 와 모든 node id 비교. selectedId 는 사용자 클릭 시 onSelect(node.id) 로 받음 → trade/building 클릭 시 그 node 의 children leaf 들 collect → wpIds 채워짐
- trade/building node id 는 그대로 (`${wa}::${l5_disc}` 등) → find/select 흐름 영향 X
- 카드 ai_mapped_wp_id 는 review/route.ts:84 의 `deriveWpIdAndPath` 가 만듦 → 같은 함수, 같은 출력 → 완전 일치

**BE 추가:**
- wbsTreeBuild 의 leaf 생성 한 줄 변경. deriveWpIdAndPath import 추가. 신규 함수 없음.

**인수 기준:**
- CUB > 전기 > CABLE TRAY공사 클릭 → "창원기전 카드" 표시
- 다른 leaf 클릭 시도 해당 wp_id 의 카드만 표시
- review_count 정확히 일치 (예: "5 / 50" → 5건 표시)

---

## § 7. Export 탭 fix (1 area)

### 7.1 시트 1-3 = 0 (시트 4 만 292)

**현재 데이터 위치:**
- `parser_reports` (PG): 한 cycle 의 통합 일보 raw. 3 jsonb 컬럼 (`bp_summaries`, `job_allocations`, `equipment_allocations`).
- PG 실측: report_date=2025-09-25 의 6 row 중 5 row 가 `[9, 108, 95]` (이번 cycle 들), 1 row (`da0c7e42`, 2026-05-19 oldest) 가 `[0, 0, 0]`.
- `consolidated/route.ts:117` SQL: `WHERE report_date = ${date} LIMIT 1` — **ORDER BY 없음**.

**매핑 끊긴 지점:**
ORDER BY 없는 LIMIT 1 → PG 가 임의 row 선택. 우연히 oldest empty row 가 선택됨 → bp_summaries.length = 0 → output_manpower / occupation_manpower / equipment 모두 빈 배열. 시트4 (parser_activities) 는 별도 SELECT 라 영향 X.

같은 패턴이 dates loop path (`route.ts:53` `!date`) 의 jsonb_array_length subquery 에도 있음 (`SELECT jsonb_array_length(bp_summaries) FROM parser_reports WHERE report_date = ${dStr} LIMIT 1`) — 마찬가지 결함.

**해결:**
두 path 모두 `ORDER BY created_at DESC LIMIT 1` 추가. 가장 최신 cycle 의 jsonb 가 선택됨.

같이 `AND is_mock = ${useMock}` 도 추가 (§4 호환).

**BE 추가:**
- consolidated/route.ts 의 SQL 2개 보강. 신규 SELECT/함수 없음.

**인수 기준:**
- ?date=2025-09-25 호출 → output_manpower=9, occupation_manpower=108, equipment=95, quantity=292
- list path 의 sheet_row_counts 도 동일

---

## § 8. Reports 탭 fix (3 area)

### 8.1 "매핑된 업체만 표시" — contractor_bars 80 → 3

**현재 데이터 위치:**
- `activity_master` (PG): 마스터플랜의 모든 (site, wa, l6, company) 행. POC 외 업체 (세아그린텍 / 서림공영 등) 도 포함.
- `mapper_activities` (PG): 이번 cycle 의 실제 매핑 결과. POC 3사 (창원기전 / 세보엠이씨 / 남웅건설) 만.
- `view_builder._evm_by_group` (`pipeline/agents/optimizer/view_builder.py:128`) 가 plan_agg (activity_master) FULL OUTER JOIN actual_agg (mapper_activities) → 둘 다 합집합. plan 측에만 있는 company 도 결과에 포함 (CPI=0).

**매핑 끊긴 지점:**
실제로 일을 한 업체 = mapper_activities 의 company DISTINCT 만. activity_master 의 모든 company 까지 bars 에 노출 → contractor_bars 80 건 (POC 외 77 건). 사용자 신고 "다른 업체까지 쭉 보이는데 매핑된 업체만 표시하게".

**해결 — anchor 를 actual_agg 로 변경:**

`_evm_by_group` 의 company / l6_main path 만 변경. `FROM plan_agg p FULL OUTER JOIN actual_agg a USING (gkey)` → `FROM actual_agg a LEFT JOIN plan_agg p USING (gkey)`. wa_l6_company path 는 이미 mapper anchor 라 영향 X. site 전체 EVM (`_evm_for_group`) 도 그대로 (분모 = 마스터플랜 전체 유지).

같은 변경이 `_build_trade_bars` 의 by_l6 에도 자동 적용 (by_l6 가 같은 함수로 생성).

**왜 site EVM 은 안 바꿔도 되나:**
사용자 신고는 contractor_bars/trade_bars 의 "표시" 만 — 매핑 안 된 공종/업체가 노출되는 게 문제. site 전체 SPI/CPI 의 분모는 마스터플랜 (계획) 이어야 정확. 두 산출 분리.

**BE 추가:**
- view_builder.py 의 _evm_by_group SQL 한 줄 (`FROM ... FULL OUTER JOIN` → `FROM actual_agg a LEFT JOIN plan_agg p`). 함수 시그니처 그대로.
- 이번 cycle 의 daily_reports.jsonb 는 backfill 필요 (`tmp/backfill_daily_reports.py` 가 view_builder 다시 호출 → 정정). 또는 다음 cycle 1 회.

**인수 기준:**
- contractor_bars 3건 (POC 3사)
- trade_bars 는 mapper_activities 에 등장한 l6_main 만 (현재 58 → POC 3사 가 일한 l6 만)

### 8.2 "0개사 평균 미만"

**현재 데이터 위치:**
- `ProductivityBarToggle` (`web/app/components/reports/ProductivityBarToggle.tsx:60`) 의 `underCount`:
  ```ts
  items.filter(it => typeof it.baseline === "number" && it.value < it.baseline).length
  ```
- `_build_contractor_bars` (`view_builder.py:291`) 의 bar item: `{label, value, status}`. **baseline 키 없음.**

**매핑 끊긴 지점:**
baseline 이 undefined → typeof check 실패 → underCount = 0. 표시 텍스트 "0개 BP사 평균 미만".

**해결:**
bar item 에 baseline 키 추가. `_bar_status` 의 threshold (90 = normal/caution 경계) 와 일치시켜 baseline=90 으로 통일.

```python
def _build_contractor_bars(productivity):
    by_c = productivity.get("by_contractor", {}) or {}
    return sorted([
        {
            "label": c,
            "value": round(d.get("cpi") or 0, 1),
            "baseline": 90,             # ← 추가
            "status": _bar_status(d.get("cpi") or 0),
        }
        for c, d in by_c.items()
    ], key=lambda x: -x["value"])
```

`_build_trade_bars` 도 동일 보강.

**왜 90 인가:**
view_builder 의 `_bar_status` 가 cpi >= 90 → normal, >= 80 → caution, < 80 → risk. baseline = "정상 / 주의 경계" = 90. 사용자 직관 ("90% 미만이면 평균 미달") 과 일치.

**BE 추가:**
- view_builder.py 의 두 함수 각 1 줄. backfill 필요 (§8.1 와 함께).

**인수 기준:**
- 표시 "{N}개 BP사 평균 미만" 의 N > 0 (CPI < 90 인 BP 수)
- 같은 패턴 공종별 "{N}개 공종 평균 미만"

### 8.3 WP 클릭 시 진단/상세현황 안 보임

**현재 데이터 위치:**
- `forecasts` (PG): forecaster 가 (run_id, company, l6_main) 단위로 row. 11 컬럼. **wa 컬럼 없음.**
- `optimizer_advice` (PG): optimizer 가 (run_id, company, l6_main) 단위. diagnosis/recovery_pattern/recommendations/similar_cases jsonb.
- `mapper_activities` (PG): (run_id, wa, l6_main, company) 4 키.
- `daily_reports.quadrant_jsonb` (산점도 dot): view_builder._build_quadrant 가 mapper_activities 그룹 → dot wp_id = `{wa}-{l6}-{company}` (lowercase kebab).
- `daily_reports.optimizer_view_jsonb.by_wp` (진단 dict): view_builder._build_optimizer_view 가 optimizer_advice 변환 → key = `{forecasts.wa}-{l6}-{company}`. **forecasts.wa = None → 모든 key 가 `unknown-` prefix.**

**매핑 끊긴 지점 (`web/app/(app)/reports/page.tsx:201`):**
```ts
detail.optimizer.by_wp[selectedWpId] ?? detail.optimizer.by_wp[default_wp_id] ?? EMPTY_OPTIMIZER
```
- selectedWpId = `fab-냉동기설비공사-세보엠이씨` (quadrant 의 실 wa)
- by_wp keys = `unknown-cable-tray공사-창원기전` ...
- default_wp_id 도 `unknown-` prefix
- 100% fallback to EMPTY_OPTIMIZER

**복잡성 (PG 실측):**
mapper_activities 에서 `(l6_main, company) → DISTINCT wa` 가 **1:1 이 아님**:
- CABLE TRAY공사 / 창원기전 → wa = {CUB, FAB}
- 부스덕트공사 / 창원기전 → wa = {CUB, FAB}
- 전력간선공사 / 창원기전 → wa = {CUB, FAB}
- 철근콘크리트공사 / 남웅건설 → wa = {CUB, FAB, NULL}

→ 한 forecasts/optimizer_advice row 가 quadrant 의 2~3 dot 에 대응. 단순히 forecasts 에 wa 한 컬럼 추가만으론 한 wa 만 매칭 → 다른 wa 의 quadrant dot 클릭 시 여전히 빈 화면.

**해결 옵션 비교:**

| 옵션 | BE 변경 | 트레이드오프 |
|---|---|---|
| A — forecaster 자체를 (run_id, wa, company, l6_main) 단위로 변경 | forecaster + optimizer 둘 다 그룹 키 변경. forecaster 의 SELECT/INSERT 다 수정 | 데이터 모델 자연스러움. 큰 변경. cycle 재실행 필수. risk |
| **B — forecasts.wa 컬럼 추가 (NULL 허용) + view_builder._build_optimizer_view 가 wa 별 fan-out (★)** | migration 1 + view_builder 함수 1 보강 | forecaster/FE 무변경. 같은 advice 가 2~3 key 에 중복 적재 (메모리 영향 미미) |
| C — FE 에서 wp_id 매칭 시 wa 무시 | page.tsx 매칭 로직 변경 | **디자인 불가침 위반 가능** → 탈락 |

→ **(B) 선택**.

**해결 — Step-by-step:**

1. **Migration** (`infra/postgres/migrations/<n>_forecasts_add_wa.sql`):
   ```sql
   ALTER TABLE forecasts ADD COLUMN wa TEXT;
   ```
   NULLABLE. 기존 row 영향 0. forecaster INSERT 코드 변경 X (이번 scope).

2. **view_builder._build_optimizer_view fan-out 로직** (`view_builder.py:549`):
   현재: advice 마다 forecasts matched_f 1 row → 1 wp_id key.
   변경: advice 마다 mapper_activities 에서 (run_id, l6_main, company) 매칭 row 들의 DISTINCT wa list 를 lookup → 각 wa 마다 같은 advice 를 by_wp[wa-l6-company] 에 복사 (fan-out).
   
   lookup 방법 2 가지:
   - **(i) view_builder 함수 내부에서 PG SELECT** — pg 인스턴스 이미 인자로 받음. 한 번 SELECT 로 모든 advice 의 lookup 결과 cache.
   - (ii) agent.py 가 mapped (mapper_activities row list) 인자로 전달 + view_builder 가 in-memory dict 빌드.
   
   → (i) 가 깔끔. 별도 메모리 패스 불필요.

3. **forecaster INSERT 에 wa 적재 — 이번 scope 제외:**
   forecaster 노드 자체는 그대로. forecasts.wa 컬럼은 향후 보강용으로 NULL 유지. view_builder 의 fan-out 만으로 충분.

4. **backfill 불필요:**
   view_builder 가 매 cycle 마다 daily_reports.optimizer_view_jsonb 재산출. 다음 cycle 1 회 또는 `tmp/backfill_daily_reports.py` 재실행 1 회면 자동 정정.

**BE 추가:**
- migration 1 파일
- view_builder.py 의 _build_optimizer_view 보강 + 새 helper `_lookup_wa_by_l6_company(pg, run_id)` 추가 (PG SELECT 1번)

**인수 기준:**
- 다음 cycle (또는 backfill) 후 `daily_reports.optimizer_view_jsonb->'by_wp'` 의 keys 가 `quadrant_jsonb` 의 wp_id superset
- Playwright reports 페이지 첫 WP 클릭 → OptimizerResult 의 6 칸 (위험평가 / 진단대상 / 유사사례수 / 평균회복일수 / 회복분포 / 일정영향) 모두 표시
- CUB 의 CABLE TRAY공사 (창원기전) 와 FAB 의 CABLE TRAY공사 (창원기전) 클릭 시 둘 다 같은 advice 표시 (fan-out 확인)

---

## § 9. Home 탭 fix (1 area)

### 9.1 sites SUM 에 mock 섞임

**현재 데이터 위치:**
- `sites` 테이블 (PG): 7 row. PoC (m15x-ph3-ibl) 1 + mock 6 (DEMO_SITE / indiana-hac / m15x-obl-pt7 / pt3-extension / y1-ph1-ibl / y1-ph1-obl).
- 컬럼: headcount / hours_saved / fte_saved / hours_saved_cum.
- 실측: m15x 65/221/1.6/253. mock 합 380/1934/13.7/0. 전체 SUM = 445/2155/15.3/253.
- `loadReal:sites_summary` (`web/lib/fixtures.ts:108`): SUM 시 WHERE 없음 → 7 site 합산.
- Home OpsKpiCard 4 KPI: 누적 처리 / 오늘 처리 / 누적 절감 / 현재 처리 중.

**매핑 끊긴 지점:**
"누적 절감" = `total_hours_saved_cum` = SUM(sites.hours_saved_cum) = 253 (mock 6 site = 0). 우연히 표시값 정상.
"AI 대체율" = hours_saved / total_hours. total_hours = SUM(headcount) × 140 = 445 × 140 = 62300. mock 영향 큼.
"누적 처리" = pipeline_runs.atomized_count SUM → mock pipeline_runs row 가 새로 추가될 경우 영향. 현재는 영향 0.

사용자 신고 "mock 데이터가 좀 섞인거 같아" → 직접 보이는 영향은 미미하지만 데이터 무결성 관점에서 분리 필요.

**해결:**
`loadReal:sites_summary` 의 siteAgg SQL 에 WHERE 추가:
```ts
const [siteAgg] = await sql`
  SELECT SUM(...), SUM(...) FROM sites WHERE is_mock = ${useMock}
`;
```

다른 SQL (pipeline_runs 의 atomized_count SUM, mapper_activities count 등) 도 같이 is_mock 분기 추가 — § 4 useMock 패턴 일관성.

`abnormal_count` (forecasts) 도 동일. `review_pending` (mapper_activities) 도 동일.

**BE 추가:**
- fixtures.ts 의 5~6개 SQL 각 WHERE 한 줄. 신규 함수 없음.

**인수 기준:**
- default (useMock=false): m15x 단일 site SUM 만 표시 (headcount 65)
- CPIA_DEMO_FALLBACK=on: mock 6 site SUM 만 표시 (headcount 380)

---

## § 10. 작업 순서 + 의존성

```
Phase 0 — Mock 백업 인프라 (§4)
  ├─ migration: ALTER TABLE ... ADD COLUMN is_mock (7 테이블)
  ├─ tmp/backfill_mock_rows.py 작성 + 실행 (mock_review_cards + mock_report)
  └─ 5 route.ts + lib/fixtures.ts 에 useMock 분기

Phase 1 — view_builder + forecasts.wa (§8.3, §8.1, §8.2)
  ├─ migration: forecasts.wa 추가
  ├─ view_builder._build_optimizer_view fan-out
  ├─ view_builder._evm_by_group actual anchor
  ├─ view_builder._build_*_bars baseline
  └─ tmp/backfill_daily_reports.py 재실행 → daily_reports.*_jsonb 정정

Phase 2 — Review 탭 (§6)
  ├─ 6.1 wbsTreeBuild siteName 인자 추가 + root.name
  ├─ 6.2 wbsTreeBuild SQL CTE 재작성
  └─ 6.3 wbsTreeBuild leaf id = deriveWpIdAndPath

Phase 3 — Export 탭 (§7)
  └─ 7.1 consolidated/route.ts SQL 2개에 ORDER BY

Phase 4 — Tasks 탭 (§5)
  ├─ 5.1 agent-tasks/route.ts Parser items SELECT
  ├─ 5.2 mapper LIMIT 12 → 200
  └─ 5.3 total_count = parser_acts

Phase 5 — Home 탭 (§9)
  └─ 9.1 fixtures.ts SUM 에 is_mock 분기

Phase 6 — Cycle 재실행 + Playwright 5 탭 인수
```

각 Phase 마다 atomic commit. PR 미생성 (사용자 명시 — pr은 올리지 말 것).

## § 11. 검증

각 area 인수 기준 (§4~§9 의 "인수 기준") 을 Playwright + curl 로 직접 검증. `tmp/verify_fe_data_binding.py` (one-shot) 가 5 탭 자동 점검 — curl 로 API 호출 후 jq 로 expected count/key 비교.

`CPIA_DEMO_FALLBACK=on` 토글 후 같은 스크립트 재실행 — mock fallback path 검증.

Playwright 로는 사용자가 직접 본 6 area (Parser 빈 / wbs 14736 / wbs 클릭 0/50 / export 시트1-3 / "0개사" / WP 진단) 모두 fix 확인 — snapshot 비교.

## § 12. 리스크

| 리스크 | 완화 |
|---|---|
| forecasts.wa 마이그레이션이 기존 cycle 깨뜨림 | NULLABLE + default NULL → 기존 SELECT 영향 X. forecaster INSERT 코드 변경 X (이번 scope) |
| review/page.tsx wp_id format 변경 → confirm/remap state 깨짐 | onConfirm/onRemap 콜백은 card id ('r-{id}') 기반. wp_id 와 무관 → 영향 X |
| is_mock 컬럼 추가가 partial unique index 영향 | partial index 컬럼 set (run_id, site_id, report_date) 에 is_mock 미포함 → 영향 X |
| route.ts 의 useMock parameter 가 SQL parameter count 변경 | postgres.js tagged template 이 자동 추적 → 영향 X |
| backfill 스크립트가 mock_*.json 없을 때 fail | git show HEAD:data/mock_*.json 으로 복원 후 재실행 |
| _evm_by_group actual anchor 변경 → site EVM 분모 영향 | site EVM 은 `_evm_for_group` 별도 함수 → 영향 X. wa_l6_company path 도 별도 → 영향 X |
| view_builder fan-out 시 메모리 폭발 | wa lookup 의 cardinality ≤ 3 (실측) → advice N 개에 대해 by_wp 최대 3N row → 무시 가능 |

## § 13. 디자인 불가침 확인 체크리스트

- ☑ `web/app/components/**/*.tsx` 의 JSX / className / 색상 / 간격 변경 없음
- ☑ 컴포넌트 prop 시그니처 변경 없음 (DailyTask / AgentTaskItem / WBSNode / ReviewItem / BarItem / ReportDetail / OptimizerOutput 모든 type 그대로)
- ☑ 새 페이지 / 새 컴포넌트 신설 없음
- ☑ Tailwind config 변경 없음
- ☑ wbsTreeBuild siteName 인자 추가는 BE 함수 시그니처 — 컴포넌트 prop 아님 (예외 통과)

---

*최종 수정: 2026-05-20*
