# CPIA 09-25 데모 정교화 설계 (B1 일보정교화 + B2 전건HIL + B3 진행도 실시간)

> 작성 2026-06-02. 대상 마감 2026-06-05 시연. brainstorming 산출 design spec.
> v2 (2026-06-02): B2/B3 실코드 감사(4-agent) 반영 + "플랜 온고잉 7개사" 재구성으로 전면 개정.
> 후속: writing-plans 로 구현 계획 분해.

---

## 1. 배경 & 불변 제약

09-25(2025-09-25) 작업일보를 prod 파이프라인으로 돌렸을 때 UI(Tasks + Reports + Export)에서
forecaster/optimizer 가 **회사별 건축/토목 실데이터**로 보이게 한다.

**불변 제약 (엄수):**
- 콜드스타트/룰베이스/정규화-복원 우회 금지. prod 가 DB 에 실제 적재한 값만 UI 가 바라본다.
  (forecasts/optimizer_advice = LLM 실출력, daily_reports jsonb = optimizer view-build 산출)
- **디자인 불가침** (시연자 조형준 프로 의도): FE layout/style/markup 변경 금지. BE/데이터 변환 + 로직만 허용.
- **입력 파일 정교화는 허용** — 작업일보(.xlsm)는 파이프라인 입력이므로, 실 plan 기반으로 현실적 actuals
  를 채우는 것은 우회가 아니다. 채운 파일을 prod 가 정상 처리 → DB 적재 → UI 가 그 DB 를 본다.

**범위:** 3개 워크스트림 — B1(오프라인 파일 정교화) → B2(전건 HIL) + B3(진행도 실시간) → 업로드 e2e 검증.

---

## 2. 전수조사 핵심 발견 (실 코드 / 실 DB, v2 갱신)

1. **생성 스크립트 현재** (`pipeline/scripts/gen_company_files_v2.py`): 시트4·2 채움, 시트1 희소,
   **시트3(장비) `_fill_sheet3`(:226-231) clear만**, `_today_qty_fill`(:50-62) plan 무관 해시팩터(0.015~0.04×총물량, `max(1.0,…)` — plan 대비 임의라 view-build productivity 가 150 clamp 에 걸림).

2. **9/24 이전 역산 레시피 재사용 가능**: `daily_quota = plan_total/total_days`,
   `_work_content.factor_for(condition)` ∈ CONDITION_PROD_FACTOR, `productivity = perperson/master_perperson×100`(150 clamp).
   단일일(09-25)은 시계열 bell/conserve 불필요 — `daily_quota × factor` 만.

3. **★ Reports 커버리지의 진짜 게이트 = WBS plan 진행여부** (trade 필터 아님). 실 DB:
   통합일보 건축/토목 회사 중 **09-25 plan 진행중(plan_start ≤ 09-25 ≤ plan_finish)은 8개사뿐**,
   그중 통합일보에 인원/장비 소스 보유 = **7개사**(OTIS 제외). 나머지(서림/철우/센코어/대주/동성/에스비 등)는
   계획이 21~318일 전 종료 → 09-25 생산성 진단 예시로 부자연 → **제외**.

4. **이름 매칭 이슈**: `normalize_company`(`parser_post.py:92-99`)는 ㈜·괄호만 제거. activity_master 는 짧은 이름
   (광건/선보/태우), 통합일보는 풀네임(광건티엔씨/선보건업/태우이엔지) → normalize 후에도 불일치 →
   그대로면 view_builder `(company,l6,unit)` JOIN 깨짐. **파일 생성 시 company 를 activity_master 이름으로 정렬** 필요.

5. **B2 — requires_review 는 DB 영속됨**(`db.py:744` 값 bind, `:704` ON CONFLICT). mapper_node 가 hil_1(`graph.py:651`)
   **전에** insert(`graph.py:160`) → `mapper.py:515` True 변경이 FE 가 읽는 DB 컬럼에 반영됨. (초기 우려 "state-only" 는 해당 없음.)
   - 단 **resume 후 mapper_activities.requires_review 를 False 로 되돌리지 않음**(`graph.py:271-308` 은 mapping_corrections 만 insert).
     `/api/runs/items` Human Review 탭(`route.ts:116-135`, status필터 없음)이 영구 hil_pending 표시.
   - FE review 쿼리(`web/app/api/mock/review/route.ts:37-42`)는 `requires_review=TRUE` 외에 `status='waiting_hil_1'`,
     `is_mock=${useMock}`(=`CPIA_DEMO_FALLBACK==='on'`), `LIMIT 300`. agent-tasks `[date]` route 는 `LIMIT 200`.
   - bypass = env `CPIA_HIL_AUTO_BYPASS`(`graph.py:251`), 현재 미설정. resume(`api.py:326-338`)는 atomizer~optimizer 를 **동기 실행**.

6. **B2.5 — view_builder**: 실 run 은 `parser.py:445` `l7_5_activity=None` 으로 primary(`:1659-1663`, l7_5 기반) 0행 →
   fallback(`:1673-1708`) 사용. fallback 게이트 = `WHERE p.ps IS NOT NULL AND $1 BETWEEN p.ps AND p.pf`(`:1704`),
   plan↔actual INNER JOIN `(company,l6_main,unit)`(`:1703`), actual CTE `trade IN 건축/토목 + unit NOT NULL + site_id`(`:1681-1685`).
   행에 `plan_start/plan_finish` 이미 포함(`:1700`).
   - `kpi.delay_days` 는 **최종적으로 site s-curve cross**(`:2204-2225`)로 산출(forecasts median `:2049` 은 덮어써짐).
     s-curve(`:935-1024`)는 **전 건축/토목 plan**(BETWEEN 게이트 없음, linear cap) + actual 은 `(wa,l6,unit)` 회사무시 매칭
     → **site 전역**. wp_summary 회사 subset 과 무관 → "kpi/wp 회사군 정합" 은 풀 대상 없음.
   - `wp_summary.start/end_date`(`:1988-1989`)는 `당월1일~오늘` **placeholder**, `progress_pct`(`:1990-1992`)는 단일일 `today_qty/plan_total`.

7. **B3 — 진행도 현재**: `pipeline_runs.current_node`(노드 진입 1회, `set_current_node` `db.py:1299`) + `atomized_count` 만.
   `/api/runs/progress`(route.ts)는 이전=100 / 현재=`-1` sentinel / 이후=0, FE `tasks/page.tsx:282-294` 가 60초 가짜 애니메이션.
   - 에이전트 실루프: parser `parser_node.py:52-57`(파일 N병렬, run_id/postgres_url 미배선),
     mapper `graph.py:96-105`(`_map_one` gather, total=`len(parsed['activities'])`),
     atomizer `atomizer.py:102/133/163-169`(dedup 후 chroma 배치100, 단일 count),
     exporter `exporter.py:314-375`(단일 xlsx blob, 회사 루프 아님),
     forecaster `agent.py:382-401`(그룹당 `insert_forecast` **row-by-row** ✓, total=`len(groups)`),
     optimizer `agent.py:308-337`(gather **후 일괄** insert ✗, total=`len(forecast)` 전체, 고위험 필터 없음).
   - mapper_activities/parser_activities 둘 다 mapper_node **끝** 일괄 insert(`graph.py:130,160`). 카드 점진 노출하려면 둘 다 손봐야.
   - 병렬 exporter‖forecaster(`graph.py:653-654`)가 단일 current_node 덮어씀(race) → 선형 게이지로 동시 2단계 표현 불가.
   - FE markup(`AgentWorkflowList.tsx:59,87,135,138,154`)은 width/접수/처리/isDone 데이터 소비만 — **데이터/로직만 바꾸면 markup 무변경**.

---

## 3. 확정 결정 (사용자 승인)

| # | 결정 | 선택 |
|---|---|---|
| Q1 | 시트4 today_qty 역산 | dummy_seed 방식 — **온고잉 plan** daily_quota×factor (매칭) |
| Q2 | Reports/데모셋 | **플랜 온고잉 7개사** (전부 09-25 진행중). **BETWEEN 완화 폐기**(원래 게이트 통과) |
| Q3 | 과거plan 표시 | 해당 없음(전부 온고잉). wp_summary 날짜 placeholder→실 plan기간(데이터-only) |
| Q4 | 시트1 출력인원 | 시트2 직종 워커 롤업 |
| 카드 스트림 | 점진 노출 범위 | **최대** — forecaster(자연)+mapper(청크)+optimizer(per-task insert로 전환) |
| 접수/처리 단위 | 게이지 카운트 | **에이전트별 실단위** (parser=파일, mapper=활동, atomizer=적재, exporter=회사/1, forecaster=그룹, optimizer=전 forecast) |

**확정 데모 7개사** (파일 company = activity_master 이름, 인원/장비/활동 = 통합일보 소스):

```
파일company  통합일보소스   공종   (통합일보 인원/장비/활동)
장평건설      장평건설      토목    27/45/10
남웅건설      남웅건설      건축    36/33/48
동신패널      동신패널      건축    8/17/24
글로벌유명    글로벌유명    건축    7/13/3
광건         광건티엔씨    건축    4/13/24    ← company명 정렬
태우         태우이엔지    건축    4/12/2     ← company명 정렬
선보         선보건업      건축    2/3/4      ← company명 정렬
```

---

## 4. 설계 — B1: 일보 7개 정교화 (`gen_company_files_v2.py`)

오프라인 생성. 산출 → `data/demo_inputs/20250925/` + `data/input/20250925/` 7개 .xlsm.

### 4.1 TARGETS 교체 (company명 정렬 포함)
`TARGETS`(:34-45)를 7개사로. 각 entry = (파일표시명, trade_label, **out_company**, **src_company**):
```
("장평건설",  "토목공사", "장평건설",   "장평건설")
("남웅건설",  "건축공사", "남웅건설",   "남웅건설")
("동신패널",  "건축공사", "동신패널",   "동신패널")
("글로벌유명","건축공사", "글로벌유명", "글로벌유명")
("광건",      "건축공사", "광건",      "광건티엔씨")   # src≠out
("태우",      "건축공사", "태우",      "태우이엔지")   # src≠out
("선보",      "건축공사", "선보",      "선보건업")     # src≠out
```
`by_co_*` 조회는 **src_company**(통합일보 normalize 결과), 파일에 기록하는 company 는 **out_company**(activity_master 명).
생성 전 각 src_company 가 `by_co_act/job/eq` 에 존재하는지 assert. (out_company 가 `mapper_activities.company` 로 흘러
view_builder `(company,l6,unit)` JOIN 에 매칭됨.)

### 4.2 시트3(장비) — `_fill_sheet3` 구현
clear-only → equipment_allocations(`by_co_eq[src]`)로 채움. parser sheet3 게이트(`parser.py:512+`)에 맞춰:
그룹시작행 col2=공종 + col3=BP코드(PH_X-NNN) + col4=장비 대분류; 회사명행 col3=out_company;
장비행 col4=equipment_big, col5=equipment_mid, col6=equipment_spec, count 6교대 col7~12(yest)/13~18(today_incr)/19~24(today_cum), col25='O'.
MergedCell-safe. **검증: re-parse equipment 수 = by_co_eq[src] 수.**

### 4.3 시트1(출력인원) — `_fill_sheet1` 변경
원본 희소 → **job_allocations(`by_co_job[src]`) 회사단위 롤업**: 교대별 workers_incr/cum 합산 → 시트1 BP행
c24~29/c31~36 + 총계 c30/c37. bp_summaries 있으면 우선, 없으면 job 롤업.

### 4.4 시트4 today_qty — `_today_qty_fill` 교체 (온고잉 plan 역산)
원본 today_qty>0 보존. 0/None 만 역산:
1. **온고잉 plan 매칭** (gen-time): out_company 의 건축/토목 activity_master 행 중 09-25 진행중
   (`plan_start ≤ 09-25 ≤ plan_finish`) + `unit` 일치 + `work_content`↔(`l6_main`+`l7_5_activity`) 토큰 overlap 최고 → `plan_total_qty`, `total_days=(pf-ps+1)`.
2. `factor = factor_for(condition, seed)` (seed=`"2025-09-25|{out_company}|{work_content}"`), `_pick_diagnosis` 재사용.
3. `today_qty = max(1, round(factor × plan_total/total_days, 1))` → view-build daily_quota_master 와 정합 → productivity ≈ factor×100.
4. 미매칭 행: `today_qty = max(1, factor × 파일총물량/nominal)` (nominal=회사 plan 기간 중앙값). Reports 미노출, Tasks 노출.
5. yesterday_cum 원본 유지(없으면 0). today_cum=yest+today. F%=today_cum/총물량.

### 4.5 검증 (B1)
re-parse 4시트 카운트 = 원본 by_co_* (act/job/eq). 골든 수동대조 ≥2개사(남웅 48/36/33, 장평 10/27/45).
out_company 가 파일 파싱 결과 company 와 일치 확인(광건/선보/태우). today_qty 0행 0건.

---

## 5. 설계 — B2: Mapper 전건 HIL (+ 감사 수정)

목표: 점수 무관 **모든** 매핑이 review UI 를 거쳐 "승인 확정" 눌러야 atomizer 진행. + resume 후 DB 정합.

### 5.1 변경점 (모두 검증된 file:line)
1. **전건 강제**: `pipeline/agents/mapper.py:515` → `requires_review = True` (RHS 치환). `mapping_conf`(:521)는 그대로 반환(FE 표시).
   edge 반환(:447/:488/:500)은 이미 True. → `graph.py:160` insert 로 DB 반영(hil_1 전).
2. **★ resume 후 DB 재persist** (감사 D1): `pipeline/graph.py:271-308` hil_1_node 의 `_apply_corrections` 직후,
   corrected `mapped` 로 `insert_mapper_activities_batch` **재호출**(ON CONFLICT `(run_id,idx)` 가 requires_review/wa/l6/source upsert, `db.py:695-729`).
   → resume 후 mapper_activities.requires_review=False 반영 → `/api/runs/items` Human Review 가 done 표시(영구 hil_pending 해소).
3. **LIMIT 상향** (감사 D2): `web/app/api/mock/review/route.ts:42` `LIMIT 300`→`500`,
   `web/app/api/mock/agent-tasks/[date]/route.ts` `LIMIT 200`→`500`. (7개사면 ~115행이라 300 으로도 충분하나, 안전마진.)
   ※ "FE 무변경"이 아니라 **load-bearing 데이터 변경**임을 명시(마크업은 불변).
4. **env 점검**: 데모 런타임에서 `CPIA_HIL_AUTO_BYPASS` 미설정 + `CPIA_DEMO_FALLBACK` 미설정/off
   (후자 set 이면 review 가 is_mock=TRUE 만 봐서 live(is_mock=FALSE) 안 뜸). 데모 런타임 명시(AWS PG 5532 vs compose 5432 중 실제 경로).
5. **resume 백그라운드화** (감사 risk): `api.py:326-338` hil_1_resume 가 atomizer~optimizer 동기 실행 → FE 170s 타임아웃 위험.
   `/run` 처럼 `asyncio.create_task` 로 백그라운드 전환, 즉시 반환. FE 는 Tasks 폴링으로 진행 관찰(이미 fire-and-forget). B3 게이지와 정합.

### 5.2 검증 (B2)
라이브 run: mapper 후 status=`waiting_hil_1`, review 화면 전체 항목(=mapper_activities 수, LIMIT 내) 노출.
"승인 확정" → resume(백그라운드) → atomizer 이후 완주. **resume 후 `SELECT count(*) FROM mapper_activities WHERE run_id=$ AND requires_review` = 0 확인**(재persist 동작). 미승인 시 후속 0 진행.

---

## 5.5 설계 — Reports 커버리지 (BETWEEN 완화 **폐기**, 최소 데이터 보정)

7개사 전부 온고잉 → 원래 게이트가 통과하므로 **view_builder 쿼리 변경 없음**.

- **`view_builder.py:1704` 변경 안 함** — `$1 BETWEEN p.ps AND p.pf` 유지. 온고잉이라 통과. (v1 의 `p.ps<=$1` 완화 **폐기**.)
- **커버리지 보장은 B1 의 company명 정렬**(§4.1)으로 — out_company=activity_master 명이라 `(company,l6,unit)` JOIN(`:1703`) 매칭.
  단 `(l6,unit)` 도 일치해야 함 → mapper l6 배정 + unit 이 온고잉 plan 과 맞아야 매칭(미스 시 그 행만 Reports 누락, Tasks 무관). B2 전건 HIL 에서 보정.
- **wp_summary 날짜 보정** (데이터-only, 감사 D2): `view_builder.py:1988-1989` placeholder(`today.replace(day=1)`/`today`)를
  행에 이미 있는 `it["plan_start"]/it["plan_finish"]`(`:1700`)로 교체 → 온고잉 plan 의 실 기간 표시. 디자인 불가침 OK(데이터).
- **누설**: 원래 BETWEEN 유지 + 업로드 7파일 통제 → 비-데모 회사 plan 안 샘. (코드 화이트리스트 불요 — PoC 단일 site.)
- kpi.delay/s_curve 는 이미 site 전역(`:2204-2225`/`:935-1024`) → 손대지 않음.

---

## 6. 설계 — B3: 진행도 per-item 실시간 (`agent_progress` 신설, 마크업 불변)

### 6.1 스키마 (신규)
`infra/postgres/migrations/<date>_add_agent_progress.sql`:
```sql
CREATE TABLE agent_progress (
  run_id     UUID NOT NULL,
  agent      TEXT NOT NULL,   -- 'parser'|'mapper'|'atomizer'|'exporter'|'forecaster'|'optimizer'
  processed  INTEGER NOT NULL DEFAULT 0,
  total      INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, agent)
);
```

### 6.2 emit primitive
`pipeline/db.py` (set_current_node `:1299` 옆): `upsert_agent_progress(postgres_url, run_id, agent, processed, total)` —
**standalone asyncpg.connect, 예외 swallow(fire-and-forget)**, `INSERT … ON CONFLICT (run_id,agent) DO UPDATE SET
processed=GREATEST(agent_progress.processed, EXCLUDED.processed), total=EXCLUDED.total, updated_at=now()`.
(GREATEST = out-of-order concurrent upsert 단조 보장.)

### 6.3 노드별 emit (단위 고정 — 감사 D2/GD1)
진입 시 `(0, total)` 선기록(접수 즉시), 처리 루프에서 processed upsert. 카운터는 **동기 증가 후 local 값으로 await upsert**(non-monotonic 방지).
| agent | total | processed | emit 위치 |
|---|---|---|---|
| parser | len(files) | 파싱완료 파일수 | `parser_node.py:47`(total)/`:52-57`(per-file). **run_id+postgres_url 를 state 에서 추출 배선** |
| mapper | len(parsed['activities']) | 매핑완료 활동수 | `graph.py:96-105` `_map_one` 완료 콜백, 매 K건 |
| atomizer | len(ids) **post-dedup** | chroma 배치 적재수 | `atomizer.py:~133`(dedup 후 total)/`:163-169`(배치100마다) |
| exporter | 1 (또는 회사수) | 성공 시 total | `exporter.py:348` upsert 성공 후 |
| forecaster | len(groups) | 완료 그룹수 | `agent.py:378`(total)/`:397` insert_forecast 후 (이미 row-by-row) |
| optimizer | len(selected forecast)=len(forecast) | 완료 advice수 | `agent.py` `_process_one_v10_with_retry` 내 |

### 6.4 카드 점진 노출 (Q1=최대)
- **forecaster**: 이미 그룹당 insert(`agent.py:397`) → 자연 스트림. 추가작업 없음.
- **mapper**: `graph.py:130` `insert_parser_report`+`insert_parser_activities_batch` 를 mapper_node **진입(gather 전)**으로 이동
  → items Mapper 카드(parser LEFT JOIN mapper)가 즉시 received 표시. `graph.py:160` mapper_activities 를 **청크 INSERT**(매 K건,
  `_map_one` 이 idx 동반 반환하도록 수정, ON CONFLICT `(run_id,idx)` 멱등). → l6 채워지는 행부터 done 전환.
- **optimizer** (Q1=최대): `agent.py:336-337` 일괄 insert 를 `_process_one_v10_with_retry` 내부(`_compose_row` 직후, **sem 밖** — 기존
  "PG write 는 sem 밖" 패턴 따름)로 이동 → advice 행이 완료 즉시 적재 → optimizer 카드 스트림. **단 view-build `agent.py:347` 이 이후 PG 에서 advice 전량 읽는지 검증**(commit 가시성). 미검증 시 게이지만(카드 burst) fallback.
- atomizer/exporter: 카드 스트림 불가(배치/단일) → 게이지만. 카드는 단계 완료 시 노출.

### 6.5 API/FE 배선 (마크업 불변, 데이터/로직만)
- **`web/app/api/runs/progress/route.ts:108-184` 재작성** (감사 GD2): index 기반 prev=100/current=`-1`/after=0 폐기 →
  `SELECT agent,processed,total FROM agent_progress WHERE run_id=$1` 맵 빌드. **각 stage 독립 계산**:
  자기 행 있으면 received=total, processed=processed, `percent = total>0 ? round(processed/total*100) : 0`;
  나중 단계 행 존재 or completed → 100; 행 없고 이전이면 fallback count, 이후면 0. **division 가드 명시.**
  Collector=input 파일수, Human Review=mapper 수 fallback(agent_progress 미emit). hil_1 waiting 분기 유지.
  JSON shape(step/agent/is_hil/received/processed/percent/waiting_hil) **불변**. UI명→agent키 매핑 테이블.
  → 병렬 exporter‖forecaster 가 **둘 다 동시 점진**(per-(run,agent) 행이라 race 해소).
- **`web/app/(app)/tasks/page.tsx:282-298` 가짜 애니메이션 제거**: `ANIM_DURATION_MS`/`stageActiveAtRef`/250ms `animTick`(`:69-74`) dead 제거,
  서버 percent 직접 사용. `pickCurrentAgent`(`:34-42`)를 `-1` 의존 대신 `received>0 && !done && percent<100` 으로(active 0% 케이스 포함).
- **AgentWorkflowList.tsx 등 markup 무변경** — width=`${percent}%`, 접수/처리 표기 그대로. received=agent_progress.total, processed=processed 로 isDone(`:87` processed===received) 정합.

### 6.6 검증 (B3)
라이브 폴링 스냅샷: 각 에이전트 processed 0→total **단조 증가**(GREATEST 보장). exporter‖forecaster 동시 점진.
mapper/forecaster/optimizer 카드 점진 노출. **결정성**: 2회 run 시 **최종 processed==total 동일**(중간 스냅샷은 완료순서로 변동 — 단조만 보장).
run 실패 시 mapper 청크 부분행 cleanup(`DELETE FROM mapper_activities WHERE run_id=$1`).

---

## 7. 통합 e2e

```
7파일 업로드(/api/upload → data/input/20250925)
  → POST /run → collector → parser(진행도) → mapper(진행도+청크, 전건 requires_review)
  → [waiting_hil_1] review UI 전체 표시 → "승인 확정" → /api/hil/resume(백그라운드) → (resume 후 requires_review=False 재persist)
  → atomizer → exporter ‖ forecaster → optimizer(per-task insert)
  → Tasks 게이지 단조+카드 점진 / Reports 7개사 온고잉 생산성 / Export 09-25 통합일보
```

---

## 8. 검증 계획 (TDD / feedback loop)

- **B1**: re-parse 카운트 일치 + 골든 2개사 수동대조 + company명 정렬(광건/선보/태우) + today_qty 0행 0건. (결정론, LLM bypass)
- **B2**: status 전이 + 게이트(미승인 시 후속 0) + **resume 후 requires_review=0**.
- **B2.5**: e2e 후 `SELECT DISTINCT company FROM mapper_activities WHERE report_date='2025-09-25' AND is_mock=false` = 7개사;
  `_rebuild_views.py` 로 wp_summary distinct company 확인(온고잉 7 매칭 수).
- **B3**: progress 폴링 단조증가 + 병렬 동시 + 카드 점진 + 결정성(2회 최종 동일).
- **e2e**: 1회 완주 후 Tasks/Reports/Export 09-25 캡쳐. **검증 후 "시연 데이터 초기화" 금지**
  (`/api/upload/reset` DEMO_DATE=2025-09-25 가 09-25 전삭제). 현재 09-25 DB 0행이라 all-HIL 첫 실행 = 이 e2e.

---

## 9. 리스크 & 미해결

- **gen-time 매칭 부정확**: work_content↔l6 fuzzy 가 mapper 실제 l6 와 다르면 view-build (l6,unit) JOIN 미스 → 그 행 Reports 누락(Tasks 무관). 완화: B2 전건 HIL 보정 + e2e 후 7개사 각 wp_summary 등장 확인.
- **mapper 청크 부분행**: 실패 시 잔존 → run-error cleanup(DELETE WHERE run_id). ON CONFLICT (run_id,idx) 멱등.
- **optimizer per-task insert**: commit 가시성 — view-build(`agent.py:347`)가 전량 읽는지 검증. 미검증 시 게이지만(카드 burst) fallback.
- **resume 백그라운드**: FE 가 즉시 응답 받고 폴링 — 기존 fire-and-forget 와 정합 확인.
- **company명 정렬 누락**: 광건/선보/태우 src≠out 매핑 빠뜨리면 빈 시트 or Reports 누락 → §4.1 assert.
- mapper ~5분 병목(N병렬 LLM)은 범위 밖(진행도/카드 점진으로 체감 개선).

---

## 10. 작업 순서

1. **B1** (오프라인, UI 무관) — 7파일 생성+검증. 가장 독립적.
2. **B3 emit primitive + 노드 emit** → **progress route/FE 배선**. (emit 먼저, 배선 나중 — 감사: 배선만 하면 mapper 게이지 0→100 점프.)
3. **B2** (전건 True + resume 재persist + LIMIT + resume 백그라운드 + env).
4. **B2.5** (wp 날짜 데이터-only 보정만, 쿼리 변경 없음).
5. **업로드 e2e 검증** — 7파일 풀 run.

> pipeline/ + web/ + infra/ 교차. 사용자 직접 머지 선례(d317be9) 기준 PR 없이 진행 가능.
