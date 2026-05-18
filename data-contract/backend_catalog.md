# CPIA Backend 데이터 카탈로그 (A_Track pipeline/)

> 생성: 2026-05-17. 소스 = `pipeline/`, `infra/postgres/`. 본 카탈로그는 FE↔BE crosswalk
> (다음 단계) 의 input. "어떤 데이터를 어디서 산출/저장하는지" 한눈에.
> 룰: Real code or no claim — 모든 row 의 file:line 은 grep / 실 PG 호출로 검증.

---

## §A — DB schema (모든 table × 모든 column)

> 소스: `infra/postgres/init.sql` (한 번 전수 Read) + 2 migrations + `information_schema.columns`
> (dev PG `cpia/cpia@localhost:5432/cpia` 에서 실 `SELECT`). LangGraph PostgresSaver 4 테이블은
> `pipeline/checkpointer.py` 의 `_LazyAsyncPostgresSaver.aput()` 가 첫 호출 시 `PostgresSaver.setup()`
> 으로 자동 생성 — init.sql 에 없음.

| Table | Column | Type | Nullable | Default | Source File:Line |
|---|---|---|---|---|---|
| activity_master | wbs_activity_id | text | NO | — | infra/postgres/init.sql:163 |
| activity_master | wa | text | YES | — | infra/postgres/init.sql:164 / migrations/2026-05-17_activity_master_wa.sql:13 |
| activity_master | l5_disc | text | NO | — | infra/postgres/init.sql:165 |
| activity_master | l6_main | text | YES | — | infra/postgres/init.sql:166 |
| activity_master | l6_code | text | YES | — | infra/postgres/init.sql:167 |
| activity_master | l7_sub | text | YES | — | infra/postgres/init.sql:168 |
| activity_master | l7_code | text | YES | — | infra/postgres/init.sql:169 |
| activity_master | l7_5_activity | text | YES | — | infra/postgres/init.sql:170 |
| activity_master | sub_work_area | text | YES | — | infra/postgres/init.sql:171 |
| activity_master | company | text | YES | — | infra/postgres/init.sql:172 |
| activity_master | unit | text | YES | — | infra/postgres/init.sql:173 |
| activity_master | plan_total_qty | numeric | YES | — | infra/postgres/init.sql:174 |
| activity_master | plan_mh_rev2 | numeric | YES | — | infra/postgres/init.sql:175 |
| activity_master | plan_mh_rev1 | numeric | YES | — | infra/postgres/init.sql:176 |
| activity_master | plan_mh_rev0 | numeric | YES | — | infra/postgres/init.sql:177 |
| activity_master | plan_wv | numeric | YES | — | infra/postgres/init.sql:178 |
| activity_master | plan_start | date | YES | — | infra/postgres/init.sql:179 |
| activity_master | plan_finish | date | YES | — | infra/postgres/init.sql:180 |
| activity_master | actual_start | date | YES | — | infra/postgres/init.sql:181 |
| activity_master | actual_finish | date | YES | — | infra/postgres/init.sql:182 |
| activity_master | source_file | text | YES | — | infra/postgres/init.sql:183 |
| activity_master | loaded_at | timestamptz | NO | now() | infra/postgres/init.sql:184 |
| pipeline_runs | run_id | uuid | NO | uuid_generate_v4() | infra/postgres/init.sql:14 |
| pipeline_runs | site_id | text | YES | — | infra/postgres/init.sql:15 |
| pipeline_runs | report_date | date | NO | — | infra/postgres/init.sql:16 |
| pipeline_runs | status | text | NO | — (CHECK in {running, waiting_hil_1, waiting_hil_2, completed, failed}) | infra/postgres/init.sql:17-18 |
| pipeline_runs | current_node | text | YES | — | infra/postgres/init.sql:19 |
| pipeline_runs | error | text | YES | — | infra/postgres/init.sql:20 |
| pipeline_runs | atomized_count | integer | YES | 0 | infra/postgres/init.sql:21 |
| pipeline_runs | started_at | timestamptz | NO | now() | infra/postgres/init.sql:22 |
| pipeline_runs | completed_at | timestamptz | YES | — | infra/postgres/init.sql:23 |
| daily_reports | id | bigint | NO | nextval('daily_reports_id_seq') | infra/postgres/init.sql:34 |
| daily_reports | run_id | uuid | NO | — (FK pipeline_runs ON DELETE CASCADE) | infra/postgres/init.sql:35 |
| daily_reports | report_date | date | NO | — | infra/postgres/init.sql:36 |
| daily_reports | bp_name | text | YES | — | infra/postgres/init.sql:37 |
| daily_reports | report_md | text | NO | — | infra/postgres/init.sql:38 |
| daily_reports | history_csv_row | jsonb | YES | — | infra/postgres/init.sql:39 |
| daily_reports | created_at | timestamptz | NO | now() | infra/postgres/init.sql:40 |
| forecasts | id | bigint | NO | nextval('forecasts_id_seq') | infra/postgres/init.sql:52 |
| forecasts | run_id | uuid | NO | — (FK pipeline_runs ON DELETE CASCADE) | infra/postgres/init.sql:53 |
| forecasts | company | text | NO | — | infra/postgres/init.sql:54 |
| forecasts | l6_main | text | NO | — | infra/postgres/init.sql:55 |
| forecasts | today_qty_by_unit | jsonb | YES | — | infra/postgres/init.sql:58 |
| forecasts | today_assigned_workers | numeric | YES | — | infra/postgres/init.sql:59 |
| forecasts | today_productivity | numeric | YES | — | infra/postgres/init.sql:60 |
| forecasts | main_unit | text | YES | — | infra/postgres/init.sql:61 |
| forecasts | today_conditions | text | YES | — | infra/postgres/init.sql:62 |
| forecasts | plan_total_qty_by_unit | jsonb | YES | — | infra/postgres/init.sql:65 |
| forecasts | plan_mh_sum | numeric | YES | — | infra/postgres/init.sql:66 |
| forecasts | plan_start | date | YES | — | infra/postgres/init.sql:67 |
| forecasts | plan_finish | date | YES | — | infra/postgres/init.sql:68 |
| forecasts | plan_mh_per_day | numeric | YES | — | infra/postgres/init.sql:69 |
| forecasts | schedule_state | text | YES | — (early\|on_schedule\|post_due\|unknown) | infra/postgres/init.sql:72 |
| forecasts | window_start | date | YES | — | infra/postgres/init.sql:73 |
| forecasts | window_days | integer | YES | — | infra/postgres/init.sql:74 |
| forecasts | expected_in_window_mh | numeric | YES | — | infra/postgres/init.sql:75 |
| forecasts | actual_in_window_mh | numeric | YES | — | infra/postgres/init.sql:76 |
| forecasts | mh_gap | numeric | YES | — | infra/postgres/init.sql:77 |
| forecasts | delay_days | numeric | YES | — | infra/postgres/init.sql:78 |
| forecasts | rag_n_similar | integer | YES | — | infra/postgres/init.sql:81 |
| forecasts | similar_cases | jsonb | YES | — | infra/postgres/init.sql:82 |
| forecasts | assessment | text | YES | — (정상\|주의\|이상\|NULL) | infra/postgres/init.sql:85 |
| forecasts | reasoning | text | YES | — | infra/postgres/init.sql:86 |
| forecasts | recovery_likelihood | numeric | YES | — (0.0~1.0) | infra/postgres/init.sql:87 |
| forecasts | expected_completion | date | YES | — | infra/postgres/init.sql:90 |
| forecasts | risk_level | text | YES | — (정상\|주의\|이상\|NULL) | infra/postgres/init.sql:91 |
| forecasts | created_at | timestamptz | NO | now() | infra/postgres/init.sql:93 |
| optimizer_advice | id | bigint | NO | nextval('optimizer_advice_id_seq') | infra/postgres/init.sql:108 |
| optimizer_advice | run_id | uuid | NO | — (FK pipeline_runs ON DELETE CASCADE) | infra/postgres/init.sql:109 |
| optimizer_advice | l6_main | text | NO | — | infra/postgres/init.sql:110 |
| optimizer_advice | company | text | YES | — | infra/postgres/init.sql:111 |
| optimizer_advice | diagnosis | text | YES | — | infra/postgres/init.sql:112 |
| optimizer_advice | forecast_assessment | text | YES | — (주의\|이상) | infra/postgres/init.sql:113 |
| optimizer_advice | recovery_pattern | jsonb | YES | — | infra/postgres/init.sql:114 |
| optimizer_advice | degradation_cases | jsonb | YES | — | infra/postgres/init.sql:115 |
| optimizer_advice | recovery_distribution | jsonb | YES | — | infra/postgres/init.sql:116 |
| optimizer_advice | recommendations | jsonb | YES | — | infra/postgres/init.sql:117 |
| optimizer_advice | created_at | timestamptz | NO | now() | infra/postgres/init.sql:118 |
| mapping_corrections | id | bigint | NO | nextval('mapping_corrections_id_seq') | infra/postgres/init.sql:128 |
| mapping_corrections | run_id | uuid | YES | — (FK pipeline_runs ON DELETE SET NULL) | infra/postgres/init.sql:129 |
| mapping_corrections | report_date | date | NO | — | infra/postgres/init.sql:130 |
| mapping_corrections | original | jsonb | NO | — | infra/postgres/init.sql:131 |
| mapping_corrections | corrected | jsonb | NO | — | infra/postgres/init.sql:132 |
| mapping_corrections | created_at | timestamptz | NO | now() | infra/postgres/init.sql:133 |
| sites | site_id | text | NO | — (PK) | infra/postgres/init.sql:142 |
| sites | name | text | NO | — | infra/postgres/init.sql:143 |
| sites | plan_progress | numeric(5,2) | YES | — | infra/postgres/init.sql:144 |
| sites | actual_progress | numeric(5,2) | YES | — | infra/postgres/init.sql:145 |
| sites | status | text | YES | 'unknown' (CHECK in {normal, caution, risk, unknown}) | infra/postgres/init.sql:146 |
| sites | last_run_id | uuid | YES | — (FK pipeline_runs ON DELETE SET NULL) | infra/postgres/init.sql:147 |
| sites | is_mock | boolean | NO | true | infra/postgres/init.sql:148 |
| sites | location | text | YES | — | infra/postgres/init.sql:150 / migrations/2026-05-17_db_alignment.sql:7 |
| sites | headcount | integer | YES | — | infra/postgres/init.sql:151 / migrations/2026-05-17_db_alignment.sql:8 |
| sites | hours_saved | numeric | YES | — | infra/postgres/init.sql:152 / migrations/2026-05-17_db_alignment.sql:9 |
| sites | fte_saved | numeric | YES | — | infra/postgres/init.sql:153 / migrations/2026-05-17_db_alignment.sql:10 |
| sites | updated_at | timestamptz | NO | now() | infra/postgres/init.sql:154 |
| checkpoints | thread_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() (pipeline/checkpointer.py:30) |
| checkpoints | checkpoint_ns | text | NO | '' | auto-created by AsyncPostgresSaver.setup() |
| checkpoints | checkpoint_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoints | parent_checkpoint_id | text | YES | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoints | type | text | YES | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoints | checkpoint | jsonb | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoints | metadata | jsonb | NO | '{}' | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | thread_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | checkpoint_ns | text | NO | '' | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | checkpoint_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | task_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | idx | integer | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | channel | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | type | text | YES | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | blob | bytea | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_writes | task_path | text | NO | '' | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | thread_id | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | checkpoint_ns | text | NO | '' | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | channel | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | version | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | type | text | NO | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_blobs | blob | bytea | YES | — | auto-created by AsyncPostgresSaver.setup() |
| checkpoint_migrations | v | integer | NO | — (PK) | auto-created by AsyncPostgresSaver.setup() |

**§A 발견된 패턴 / 이슈**

- `forecasts` 의 컬럼 순서 = init.sql 정의 순서가 아닌 `information_schema.columns` ordinal 순서 (마이그레이션 누적 결과). dev PG `ordinal_position` 기준 1~16 (원 7 컬럼 + jsonb + ts) 다음 17~27 이 추가 컬럼인데, init.sql 만 보면 신규 row 가 한 INSERT 에 묶여있어 drift 인식 어려움. 본 표는 init.sql 라인 기준 정렬 (논리적 그룹).
- `daily_reports.history_csv_row` 컬럼명은 schema 잔재. 실제 박히는 값은 Reporter summary dict (`total_workers` / `total_qty_by_trade` / `risk_counts` / `advice_count`) — pipeline/agents/reporter.py:107-112 + db.py 의 docstring (pipeline/db.py:356-364) 가 mismatch 자인.
- `sites` 컬럼 `last_run_id` 는 FK 만 정의되어 있고 INSERT/UPDATE 하는 코드를 grep 안 함 — 본 표는 schema only. 실 사용 path 는 §E 까지 가도 등장 X (drift).
- `pipeline_runs.completed_at` 도 init.sql 에만 있고 어떤 helper 도 UPDATE 안 함 (`db.py` 의 `update_run_atomized_count` 는 atomized_count + current_node 만 갱신). status='completed' 전환 path 미존재 — drift.
- LangGraph 4 테이블 (checkpoints / writes / blobs / migrations) 은 `AsyncPostgresSaver.setup()` 이 idempotent 생성. checkpointer.py:30~ 의 `_LazyAsyncPostgresSaver` 가 첫 async method 호출 (aput 등) 시 lazy open — `setup()` 호출 path 는 코드 grep 결과 명시적 호출 없음 (langgraph 라이브러리가 첫 aput 시 자동 처리하거나 별도 sync helper 가 한 번 호출 필요 가능, TBD — 실 dev PG 에 244 row 박혀있으니 어느 시점엔 호출됨).

**§A 총 row 수: 105 컬럼** (`activity_master` 22 + `pipeline_runs` 9 + `daily_reports` 7 + `forecasts` 28 + `optimizer_advice` 10 + `mapping_corrections` 6 + `sites` 12 + checkpoints 7 + checkpoint_writes 9 + checkpoint_blobs 6 + checkpoint_migrations 1 = 117 logical, 본 표는 105 유효 / 12 LangGraph 자동 생성).

---

## §B — JSONB key 인벤토리

> 소스: dev PG `cpia/cpia@localhost:5432/cpia` 실 `SELECT ... LIMIT 1` (mapping_corrections 4 row, 그 외 NULL/빈 row 가 첫 결과로 잡힐 때는 non-empty 필터 재실행 — sample 은 두 형태 다 캡쳐).
> 의미 = `pipeline/agents/<agent>.py` 의 dict literal grep.

| Table.col | JSONB key | Type | 의미 | Sample value |
|---|---|---|---|---|
| daily_reports.history_csv_row | total_workers | number | mapped Activity Σ assigned_workers | 0.0 |
| daily_reports.history_csv_row | total_qty_by_trade | object<string,number> | trade 별 today_qty Σ | `{"토목공사": 0.0}` |
| daily_reports.history_csv_row | risk_counts | object<string,int> | forecast risk_level 분포 ("정상" / "주의" / "이상") | `{"이상": 0, "정상": 0, "주의": 0}` |
| daily_reports.history_csv_row | advice_count | int | optimizer_advice row 수 | `0` |
| forecasts.today_qty_by_unit | <unit> | number | unit 별 오늘 물량 Σ (m, m2, m3, ea, ton 등 정규화된 lower-case 단위) | `{"ea": 17.6}` |
| forecasts.plan_total_qty_by_unit | <unit> | number | unit 별 plan total qty Σ (activity_master GROUP BY unit) | `{"ea": 56.0, "m2": 17140.0, "m3": 245052.06, "ton": 10883.0}` |
| forecasts.similar_cases[] | date | string (ISO date) | 유사 case 의 작업일자 | `"2025-08-29"` |
| forecasts.similar_cases[] | productivity | number | 그 case 의 group productivity (today_qty/workers) | `21.0463` |
| forecasts.similar_cases[] | conditions | string[] | 그 case 의 conditions list (atomizer 가 comma-join 한 것을 reasoning 시 parse) | `["우천", "장비대기"]` |
| optimizer_advice.recommendations[] | rank | int | 추천 순위 1~4 | `1` |
| optimizer_advice.recommendations[] | text | string | 추천 본문 (한국어, LLM 산출) | `"타워크레인·펌프카 등 주요 장비 스케줄 즉시 확인 권장 — 동일 장비 중복 사용 여부 점검"` |
| optimizer_advice.degradation_cases[] | date | string (ISO date) | 저하 case 일자 | `"2025-09-23"` |
| optimizer_advice.degradation_cases[] | conditions | string | comma-joined str (atomizer 와 동일 포맷, optimizer/retrieve.py:14 결정 #19) | `"흐림,돌관"` |
| optimizer_advice.degradation_cases[] | productivity | number | 그 day group productivity | `25.224973...` |
| optimizer_advice.degradation_cases[] | assigned_workers | number | 그 day 의 group assigned_workers | `92.9` |
| optimizer_advice.degradation_cases[] | activities | string[] | 그 day Chroma `documents` (work_content 원문) list | `["상부 PC Deck Plate 철근 조립 [6층 바닥]"]` |
| optimizer_advice.degradation_cases[].recovery | trajectory | object[] | case_date+1 ~ +window 일자별 회복 trajectory (4 fields: date / conditions / productivity / recovered) | `[{"date": "2025-09-24", "recovered": true, "conditions": "맑음", "productivity": 32.24}, ...]` |
| optimizer_advice.degradation_cases[].recovery | recovery_days | int \| null | 첫 회복일까지의 일수 (None=미회복) | `1` |
| optimizer_advice.recovery_pattern[] | date | string (ISO date) | degradation_cases[].date 와 1:1 mirror | `"2025-09-23"` |
| optimizer_advice.recovery_pattern[] | recovery_days | int \| null | degradation_cases[].recovery.recovery_days 와 동일 | `1` / `null` |
| optimizer_advice.recovery_distribution | d+N | int | recovery_days='N' 인 case 수 (Counter) | `{"d+1": 2, "d+5": 1, "d+6": 1, "not_recovered": 1}` |
| optimizer_advice.recovery_distribution | not_recovered | int | recovery_days IS NULL 인 case 수 | (위 sample 의 `"not_recovered": 1`) |
| mapping_corrections.original | wa | string \| null | Mapper 산출 WA 코드 | `"CUB"` |
| mapping_corrections.original | l6_main | string \| null | Mapper 산출 l6_main | `"철근콘크리트공사"` |
| mapping_corrections.original | mapping_conf | number | LLM confidence (0.0~1.0) | `0.55` |
| mapping_corrections.original | mapping_source | string | enum (auto_bp_single, auto_l6_single, auto_sheet1_text, hil_required) | `"hil_required"` |
| mapping_corrections.original | work_content | string | 작업일보 work_content 원문 | `"1F 벽체 콘크리트 타설"` |
| mapping_corrections.original | company | string | BP사명 | `"남웅건설"` |
| mapping_corrections.original | trade | string | l5_disc 한글 (Parser disc_abbrev_to_kr) | `"철근콘크리트공사"` |
| mapping_corrections.corrected | wa | string | 사용자 정정 WA | `"CUB"` |
| mapping_corrections.corrected | l6_main | string | 사용자 정정 l6_main | `"철근콘크리트공사"` |
| mapping_corrections.corrected | mapping_source | string | 항상 `"user_corrected"` (graph.py:156-157 hard-coded) | `"user_corrected"` |
| mapping_corrections.corrected | correction_type | string | 항상 `"replace"` (graph.py:157, PoC 단일 type) | `"replace"` |

**§B 발견된 패턴 / 이슈**

- `optimizer_advice.recovery_distribution` key set 은 dynamic — `d+1`~`d+7` (window=7, retrieve.py:140) + `not_recovered`. FE 가 이걸 표/차트로 보여줄 때 모든 key 처리 (sparse map). spec 의 "d+1, d+2, ..." enum 보장 X.
- `forecasts.similar_cases[].conditions` 는 **list** (실 PG sample: `["우천","장비대기"]`) 인데 `optimizer_advice.degradation_cases[].conditions` 는 **comma-joined str** (실 PG sample: `"흐림,돌관"`). 같은 의미인데 type 불일치 — 의도적 drift. Forecaster `rerank.py:26-27` 가 Chroma metadata 의 comma-joined str 를 `split(",")` 로 list 로 변환 후 박기 때문. Optimizer `retrieve.py:107` 는 split 안 하고 raw str 그대로 박음. FE 가 둘을 합쳐 보여줘야 하면 한쪽에서 normalize 필요.
- `mapping_corrections.original` 의 key set 은 graph.py:143-152 의 dict literal 박는 set 그대로. `corrected` 는 graph.py:153-159 의 dict literal — 두 dict 가 schema spec (postgres.md §8) 의 top-level 컬럼 (work_content/company/trade/correction_type) drift 를 흡수하기 위해 JSONB 안에 합쳐 박음 (db.py:319-330 의 docstring 자인).
- `daily_reports.history_csv_row` 컬럼명은 "CSV row" 같지만 실 박힘은 dict (summary). 컬럼명 ↔ 실 의미 drift — 이름은 schema 잔재.
- `checkpoints.checkpoint` / `metadata` 는 LangGraph 자동 직렬화 (graph state). FE 가 직접 읽을 일 거의 없음 — 본 카탈로그는 schema row 만, key 인벤토리 skip.

**§B 총 row 수: 32 JSONB key** (history_csv_row 4 + today_qty_by_unit 1 dynamic + plan_total_qty_by_unit 1 dynamic + similar_cases 3 + recommendations 2 + degradation_cases 5 + degradation_cases.recovery 2 + recovery_pattern 2 + recovery_distribution 2 + original 7 + corrected 4 = 33).

**JSONB key 추출 실패한 컬럼**: 없음 (전 컬럼 sample row 확보). `forecasts.confidence_breakdown` 은 spec 에 언급되었으나 실 schema (init.sql + information_schema) 에 미존재 — 본 카탈로그에서 row drop. `daily_reports.history_csv_row` (default LIMIT 1 = NULL 가 첫 row 잡힘) 는 `IS NOT NULL` 필터로 재취득.

---

## §C — LangGraph state attr

> 소스: `pipeline/state.py` (CPIAState TypedDict 라인 106-138 전수). Producer 는 `pipeline/agents/<agent>.py`
> + `pipeline/graph.py` 의 `state[X] = ...` 또는 `return {"X": ...}` 박는 곳 grep. Persistence 는
> checkpointer (메모리 / PG checkpoints 4 테이블) 자동 직렬화 — 본 표는 "추가로 DB row 가 박히는가" 명시.

| Attr | Type | Producer (어느 node 가 박나) | Persistence (checkpoint / DB row / 휘발) | Source File:Line |
|---|---|---|---|---|
| run_id | str | 외부 (FastAPI `/run`) — 사전 INSERT 된 pipeline_runs.run_id 의 str | checkpoint (state) + pipeline_runs row | pipeline/state.py:110 |
| date | str (ISO YYYY-MM-DD) | 외부 (FastAPI `/run` payload) | checkpoint (state) | pipeline/state.py:111 |
| input_files | list[str] | 외부 (FastAPI `/run` payload) — xlsx 절대경로 list | checkpoint (state) | pipeline/state.py:112 |
| raw_texts | dict[str, str] | (TBD) collector 산출물 자리 — collector.py 0 byte | checkpoint (state) | pipeline/state.py:115 |
| parsed | list[Activity] (실은 ParsedDailyReport — type 시그니처 drift) | 외부 또는 parser node — graph.py 는 parsed 를 mapper_node 진입 시 가정 (graph.py:43 `state["parsed"]`) | checkpoint (state) | pipeline/state.py:116 |
| mapped | list[Activity] | mapper_node (graph.py:56) 그리고 hil_1_node (graph.py:164) — corrections 반영 | checkpoint (state) — DB 직접 INSERT 없음 (개별 Activity 가 row 가 되지는 않음) | pipeline/state.py:117 |
| hil_1_corrections | dict (idx→{wa,l6_main}) | hil_1_node (graph.py:124,165) — interrupt resume payload | checkpoint (state) + mapping_corrections rows (graph.py:141-159) | pipeline/state.py:118 |
| atomized_ids | list[str] | atomizer_node (graph.py:174) — Chroma doc_id list (atomizer.py:118 `return ids`) | checkpoint (state) + Chroma daily_activities upsert + pipeline_runs.atomized_count UPDATE (db.py:194-203) | pipeline/state.py:119 |
| report_md | str | reporter_node (graph.py:329) | checkpoint (state) + daily_reports.report_md row (db.py:367-379) | pipeline/state.py:122 |
| forecast | list[dict] | forecaster_node (graph.py:181) — list of `_forecast_one_group` 산출 (agent.py:190) | checkpoint (state) + forecasts row N 개 (db.py:205-271, 1 group=1 row) | pipeline/state.py:123 |
| hil_2_selection | list[str] | hil_2_node (graph.py:287) — interrupt resume payload, "{company}\|{l6_main}" key list | checkpoint (state) | pipeline/state.py:125 |
| pre_optimizer_cases | dict[str, list[dict]] | hil_2_node (graph.py:288) — `{key: cases_with_recovery}` (retrieve.py 산출 + .recovery 키 inject) | checkpoint (state) — DB 직접 INSERT 없음, 다음 optimizer_node 가 그대로 소비 | pipeline/state.py:126 |
| optimizer_advice | list[dict] | optimizer_node (graph.py:310) — `optimize()` 반환 | checkpoint (state) + optimizer_advice row N 개 (db.py:273-309, 1 selected group = 1 row, cold_start 포함) | pipeline/state.py:127 |
| current_node | str | 모든 node 가 자기 이름 박음 (graph.py:56,124,167,174,181,289,310,329 등) | checkpoint (state). 별도 DB row X (pipeline_runs.current_node 는 atomized 시점 1회만 'atomizer' 박힘 — db.py:196) | pipeline/state.py:130 |
| status | Literal[running, waiting_hil_1, waiting_hil_2, completed, failed] | (TBD) — graph.py 의 어느 node 도 박지 않음. interrupt() 발생 = LangGraph 가 자동 pause, FastAPI `/status` 가 checkpoint 상태 + pipeline_runs.status 조합으로 산출 가정 | checkpoint (state) + pipeline_runs.status (db.py:113 INSERT 시 'running', 그 외 UPDATE path 미존재 — drift) | pipeline/state.py:131-137 |

**§C 발견된 패턴 / 이슈**

- `raw_texts` (`state.py:115`) 는 schema 에 있으나 **producer 가 없음** (`pipeline/agents/collector.py` 가 0 byte 빈 파일). graph.py 도 collector node 추가 X — START → mapper 로 직결 (graph.py:407). raw_texts 채워지는 path 가 전체 코드베이스에 없음. **drift / dead attr**.
- `parsed` 의 type 시그니처 = `list[Activity]` (state.py:116) 인데, 실제로는 graph.py:43 에서 `parsed: ParsedDailyReport = state["parsed"]` 로 ParsedDailyReport (dict 타입) 받음. 타입 spec 과 사용처 mismatch — 본 표는 사용처 (ParsedDailyReport) 기준. **타입 drift**.
- `status` attr 은 TypedDict 에는 있지만 어떤 node 도 직접 박지 않음. LangGraph interrupt 가 발생하면 graph 가 자동 pause 되고 외부 (FastAPI `/status`) 가 checkpoint 의 next 노드를 검사하거나, pipeline_runs.status 를 별도로 UPDATE 해야 하는데 코드 grep 결과 UPDATE path 미존재. **drift — FastAPI api.py 분석으로 확인 필요 (본 카탈로그 scope 밖).**
- `pipeline_runs.completed_at` 은 schema 에 있으나 어떤 helper 도 UPDATE 안 함 — 위 status drift 와 동일 원인.
- `pre_optimizer_cases` 는 graph.py 내부에서만 쓰이고 (hil_2 → optimizer 사이 휘발성 buffer) DB 영속 X. `optimizer_advice.degradation_cases` JSONB 컬럼에 일부가 사후 박힘 (optimizer.py:67) 이지만 pre_optimizer_cases dict 자체는 checkpoint 에만 남음.

**§C 총 row 수: 15 attr** (CPIAState TypedDict 의 모든 attr).

---

## §D — Agent output dataclass

> 소스: 각 agent 의 dataclass / TypedDict / dict literal 산출물. BPSummary / JobAllocation /
> EquipmentAllocation / ParsedDailyReport 는 `pipeline/state.py` 에 동거 (Parser 의 직접 산출).
> Mapper 산출은 Activity 형태 그대로 (state.py:11), Forecaster/Optimizer 는 dataclass 가 아니라 dict literal.

| Agent | Dataclass/Model | Field | Type | DB target (table.col 또는 state attr) | Source File:Line |
|---|---|---|---|---|---|
| Parser | ParsedDailyReport | report_date | str | state.parsed["report_date"] (DB 직접 X) | pipeline/state.py:98 |
| Parser | ParsedDailyReport | project | str | state.parsed["project"] | pipeline/state.py:99 |
| Parser | ParsedDailyReport | bp_summaries | list[BPSummary] | state.parsed["bp_summaries"] (Mapper bp_context 빌드용, DB 직접 X) | pipeline/state.py:100 |
| Parser | ParsedDailyReport | job_allocations | list[JobAllocation] | state.parsed["job_allocations"] (Mapper bp_context 빌드용) | pipeline/state.py:101 |
| Parser | ParsedDailyReport | equipment_allocations | list[EquipmentAllocation] | state.parsed["equipment_allocations"] | pipeline/state.py:102 |
| Parser | ParsedDailyReport | activities | list[Activity] | state.parsed["activities"] → mapper_node 가 mapped 로 변환 | pipeline/state.py:103 |
| Parser | BPSummary | bp_code | str \| None | (전파 X — Mapper 가 안 씀) | pipeline/state.py:62 |
| Parser | BPSummary | company | str | mapper bp_context 의 company filter key | pipeline/state.py:63 |
| Parser | BPSummary | disc_abbrev | str \| None | (전파 X) | pipeline/state.py:64 |
| Parser | BPSummary | zone | str \| None | (전파 X) | pipeline/state.py:65 |
| Parser | BPSummary | scope | str \| None | (전파 X) | pipeline/state.py:66 |
| Parser | BPSummary | work_text_yesterday | str \| None | (전파 X) | pipeline/state.py:67 |
| Parser | BPSummary | work_text_today | str \| None | mapper.py:108 bp_context 의 시트1 텍스트 | pipeline/state.py:68 |
| Parser | BPSummary | work_text_tomorrow | str \| None | (전파 X) | pipeline/state.py:69 |
| Parser | BPSummary | today_incr_total | int | mapper.py:110, _prorate_mh (mapper.py:357) 의 BP 총 인원 합산 key | pipeline/state.py:70 |
| Parser | BPSummary | today_cum_total | int | mapper.py:111 bp_context | pipeline/state.py:71 |
| Parser | JobAllocation | bp_code | str \| None | (전파 X) | pipeline/state.py:76 |
| Parser | JobAllocation | company | str | mapper.py:121 bp_context job filter | pipeline/state.py:77 |
| Parser | JobAllocation | disc_abbrev | str \| None | (전파 X) | pipeline/state.py:78 |
| Parser | JobAllocation | job_type | str | mapper.py:122 _is_trade_job filter | pipeline/state.py:79 |
| Parser | JobAllocation | workers_cum_t | int | mapper.py:126 job 별 인원 Σ | pipeline/state.py:80 |
| Parser | EquipmentAllocation | bp_code | str \| None | (전파 X) | pipeline/state.py:85 |
| Parser | EquipmentAllocation | company | str | mapper.py:135 bp_context eq filter | pipeline/state.py:86 |
| Parser | EquipmentAllocation | equipment_big | str | mapper.py:139 eq line | pipeline/state.py:87 |
| Parser | EquipmentAllocation | equipment_mid | str | mapper.py:139 | pipeline/state.py:88 |
| Parser | EquipmentAllocation | equipment_spec | str \| None | mapper.py:140 | pipeline/state.py:89 |
| Parser | EquipmentAllocation | count_cum_t | int | mapper.py:140 | pipeline/state.py:90 |
| Parser | Activity | wbs_activity_id | str \| None | state.mapped[].wbs_activity_id (PoC: 항상 None) | pipeline/state.py:22 |
| Parser | Activity | l5_disc | str | state.parsed/mapped[].l5_disc → atomizer.py:50 Chroma metadata.l5_disc | pipeline/state.py:23 |
| Mapper | Activity | l6_main | str \| None | state.mapped[].l6_main → forecasts.l6_main (group key), atomizer Chroma metadata.l6_main | pipeline/state.py:24 + mapper.py:340 |
| Parser | Activity | l7_sub | str \| None | (PoC: None) | pipeline/state.py:25 |
| Parser | Activity | l7_5_activity | str \| None | (PoC: None) | pipeline/state.py:26 |
| Parser | Activity | sub_work_area | str \| None | (PoC: None) | pipeline/state.py:27 |
| Parser | Activity | trade | str | state.mapped[].trade → reporter 합산 (reporter.py:99) | pipeline/state.py:30 |
| Parser | Activity | company | str | forecasts.company (group key), atomizer metadata.company | pipeline/state.py:31 + atomizer.py:48 |
| Parser | Activity | unit | str | atomizer metadata.unit, forecaster aggregate_today_by_unit (aggregate.py:18) | pipeline/state.py:32 |
| Parser | Activity | today_qty | float | atomizer metadata.today_qty, forecaster today_qty_by_unit aggregation | pipeline/state.py:33 |
| Parser | Activity | work_content | str | atomizer documents (atomizer.py:101), reporter LLM input (reporter.py:81) | pipeline/state.py:34 |
| Parser | Activity | conditions | list[str] | atomizer metadata.conditions (comma-join, atomizer.py:58) | pipeline/state.py:35 |
| Mapper (_prorate_mh) | Activity | assigned_workers | float | forecasts.today_assigned_workers (group 단일값), atomizer metadata.assigned_workers | pipeline/state.py:39 + mapper.py:389 |
| Mapper (_prorate_mh) | Activity | worker_source | Literal[parsed\|mh_prorated\|user_corrected] | atomizer metadata.worker_source, optimizer retrieve.py:92 filter key | pipeline/state.py:40 + mapper.py:390 |
| Parser | Activity | plan_total_qty | float \| None | mapper bp_context (mapper.py:157) — DB 직접 X | pipeline/state.py:47 |
| Parser | Activity | plan_mh | float \| None | (PoC: 항상 None — _prorate_mh 가 별도 PG 조회) | pipeline/state.py:48 |
| Mapper | Activity | wa | str \| None | atomizer metadata.wa, mapping_corrections.original.wa | pipeline/state.py:51 + mapper.py:339 |
| Mapper | Activity | mapping_conf | float \| None | atomizer metadata.mapping_conf, mapping_corrections.original.mapping_conf, hil_1 review filter (graph.py:120) | pipeline/state.py:52 + mapper.py:341 |
| Mapper | Activity | mapping_source | str \| None (auto_bp_single \| auto_l6_single \| auto_sheet1_text \| hil_required \| user_corrected) | mapping_corrections.original.mapping_source / .corrected.mapping_source | pipeline/state.py:53 + mapper.py:342 + graph.py:101 |
| Mapper | Activity | requires_review | bool | hil_1_node review_needed filter (graph.py:76) | pipeline/state.py:56 + mapper.py:335,343 |
| Atomizer | (no dataclass — return list[str]) | atomized_ids | list[str] | state.atomized_ids → pipeline_runs.atomized_count UPDATE | pipeline/agents/atomizer.py:67,118 |
| Atomizer | Chroma metadata (per doc) | date | str (ISO) | Chroma daily_activities metadata | pipeline/agents/atomizer.py:47 |
| Atomizer | Chroma metadata | run_id | str (uuid) | Chroma metadata | pipeline/agents/atomizer.py:48 |
| Atomizer | Chroma metadata | company / l5_disc / l6_main / wa / unit / today_qty / assigned_workers / worker_source / mapping_conf / conditions | mixed | Chroma metadata (forecaster / optimizer retrieve 가 소비) | pipeline/agents/atomizer.py:49-58 |
| Forecaster | forecast row dict (graph.py state.forecast[]) | run_id | uuid.UUID | forecasts.run_id | pipeline/agents/forecaster/agent.py:191 |
| Forecaster | forecast row dict | company | str | forecasts.company | pipeline/agents/forecaster/agent.py:192 |
| Forecaster | forecast row dict | l6_main | str | forecasts.l6_main | pipeline/agents/forecaster/agent.py:193 |
| Forecaster | forecast row dict | today_qty_by_unit | dict[str,float] | forecasts.today_qty_by_unit (jsonb) | pipeline/agents/forecaster/agent.py:194 |
| Forecaster | forecast row dict | today_assigned_workers | float | forecasts.today_assigned_workers | pipeline/agents/forecaster/agent.py:195 |
| Forecaster | forecast row dict | today_productivity | float | forecasts.today_productivity | pipeline/agents/forecaster/agent.py:196 |
| Forecaster | forecast row dict | plan_total_qty_by_unit | dict[str,float] \| None | forecasts.plan_total_qty_by_unit (jsonb) | pipeline/agents/forecaster/agent.py:197 |
| Forecaster | forecast row dict | plan_mh_sum | float \| None | forecasts.plan_mh_sum | pipeline/agents/forecaster/agent.py:198 |
| Forecaster | forecast row dict | plan_start | date \| None | forecasts.plan_start | pipeline/agents/forecaster/agent.py:199 |
| Forecaster | forecast row dict | plan_finish | date \| None | forecasts.plan_finish | pipeline/agents/forecaster/agent.py:200 |
| Forecaster | forecast row dict | plan_mh_per_day | float \| None | forecasts.plan_mh_per_day | pipeline/agents/forecaster/agent.py:201 |
| Forecaster | forecast row dict | schedule_state | str | forecasts.schedule_state | pipeline/agents/forecaster/agent.py:202 |
| Forecaster | forecast row dict | window_start | date \| None | forecasts.window_start | pipeline/agents/forecaster/agent.py:203 |
| Forecaster | forecast row dict | window_days | int | forecasts.window_days | pipeline/agents/forecaster/agent.py:204 |
| Forecaster | forecast row dict | expected_in_window_mh | float \| None | forecasts.expected_in_window_mh | pipeline/agents/forecaster/agent.py:205 |
| Forecaster | forecast row dict | actual_in_window_mh | float | forecasts.actual_in_window_mh | pipeline/agents/forecaster/agent.py:206 |
| Forecaster | forecast row dict | mh_gap | float \| None | forecasts.mh_gap | pipeline/agents/forecaster/agent.py:207 |
| Forecaster | forecast row dict | delay_days | float \| None | forecasts.delay_days | pipeline/agents/forecaster/agent.py:208 |
| Forecaster | forecast row dict | rag_n_similar | int | forecasts.rag_n_similar | pipeline/agents/forecaster/agent.py:209 |
| Forecaster | forecast row dict | similar_cases | list[{date,productivity,conditions}] | forecasts.similar_cases (jsonb) | pipeline/agents/forecaster/agent.py:210-217 |
| Forecaster | forecast row dict | assessment | str \| None (정상\|주의\|이상\|None) | forecasts.assessment | pipeline/agents/forecaster/agent.py:218 |
| Forecaster | forecast row dict | reasoning | str | forecasts.reasoning (cold start = "데이터 부족 — ...", 일반 = LLM) | pipeline/agents/forecaster/agent.py:219 |
| Forecaster | forecast row dict | recovery_likelihood | float \| None | forecasts.recovery_likelihood | pipeline/agents/forecaster/agent.py:220 |
| Forecaster | forecast row dict | expected_completion | date \| None (PoC: =plan_finish) | forecasts.expected_completion | pipeline/agents/forecaster/agent.py:221 |
| Forecaster | forecast row dict | risk_level | str \| None (정상\|주의\|이상\|None) | forecasts.risk_level | pipeline/agents/forecaster/agent.py:222 |
| Forecaster | forecast row dict | main_unit | str \| None (v3.1 Task 1) | forecasts.main_unit, hil_2_node baseline_unit (graph.py:213) | pipeline/agents/forecaster/agent.py:224 |
| Forecaster | forecast row dict | today_conditions | str (comma-joined) | forecasts.today_conditions, optimizer LLM 재사용 | pipeline/agents/forecaster/agent.py:225 |
| hil_2_node | pre_cases dict value (list[dict]) | date | str (ISO) | state.pre_optimizer_cases[key][].date → optimizer_advice.degradation_cases[].date | pipeline/agents/optimizer/retrieve.py:106 |
| hil_2_node | pre_cases dict value | conditions | str (comma-joined) | optimizer_advice.degradation_cases[].conditions | pipeline/agents/optimizer/retrieve.py:107 |
| hil_2_node | pre_cases dict value | productivity | float | optimizer_advice.degradation_cases[].productivity | pipeline/agents/optimizer/retrieve.py:108 |
| hil_2_node | pre_cases dict value | assigned_workers | float | optimizer_advice.degradation_cases[].assigned_workers | pipeline/agents/optimizer/retrieve.py:109 |
| hil_2_node | pre_cases dict value | activities | list[str] (Chroma documents) | optimizer_advice.degradation_cases[].activities | pipeline/agents/optimizer/retrieve.py:110 |
| hil_2_node | pre_cases dict value | recovery | dict (trajectory + recovery_days) | optimizer_advice.degradation_cases[].recovery | pipeline/agents/optimizer/retrieve.py:161 + graph.py:262 |
| Optimizer | optimizer_advice row dict | run_id | uuid.UUID | optimizer_advice.run_id | pipeline/agents/optimizer/agent.py:63 |
| Optimizer | optimizer_advice row dict | company | str | optimizer_advice.company | pipeline/agents/optimizer/agent.py:64 |
| Optimizer | optimizer_advice row dict | l6_main | str | optimizer_advice.l6_main | pipeline/agents/optimizer/agent.py:65 |
| Optimizer | optimizer_advice row dict | forecast_assessment | str | optimizer_advice.forecast_assessment | pipeline/agents/optimizer/agent.py:66 |
| Optimizer | optimizer_advice row dict | diagnosis | str (LLM 산출 또는 "cold_start") | optimizer_advice.diagnosis | pipeline/agents/optimizer/agent.py:67,82 |
| Optimizer | optimizer_advice row dict | degradation_cases | list[dict] | optimizer_advice.degradation_cases (pre_cases 그대로) | pipeline/agents/optimizer/agent.py:68,83 |
| Optimizer | optimizer_advice row dict | recovery_pattern | list[{date, recovery_days}] | optimizer_advice.recovery_pattern (cases 의 mirror) | pipeline/agents/optimizer/agent.py:69 (cold=[]), :76 |
| Optimizer | optimizer_advice row dict | recovery_distribution | dict[str,int] | optimizer_advice.recovery_distribution (코드단 deterministic, _compute_recovery_distribution) | pipeline/agents/optimizer/agent.py:70,86 |
| Optimizer | optimizer_advice row dict | recommendations | list[{rank,text}] | optimizer_advice.recommendations (cold=[], 일반=LLM) | pipeline/agents/optimizer/agent.py:71,87 |
| Reporter | (no dataclass — tuple[str, dict] 반환) | report_md | str | daily_reports.report_md | pipeline/agents/reporter.py:145 |
| Reporter | summary dict | total_workers | float | daily_reports.history_csv_row.total_workers (jsonb) | pipeline/agents/reporter.py:108 |
| Reporter | summary dict | total_qty_by_trade | dict[str,float] | daily_reports.history_csv_row.total_qty_by_trade | pipeline/agents/reporter.py:109 |
| Reporter | summary dict | risk_counts | dict[str,int] | daily_reports.history_csv_row.risk_counts | pipeline/agents/reporter.py:110 |
| Reporter | summary dict | advice_count | int | daily_reports.history_csv_row.advice_count | pipeline/agents/reporter.py:111 |

**§D 발견된 패턴 / 이슈**

- Forecaster 와 Optimizer 는 **공식 dataclass 가 없음** — 모두 dict literal. 타입 안전성 X. dict key 오타가 발생하면 런타임까지 안 잡힘 (db.py:240~ 의 `row.get("...")` 가 None 으로 silent fall-through). 본 표는 코드 grep 결과 그대로 박음.
- Collector agent 는 파일이 0 byte (pipeline/agents/collector.py 비어있음) — 산출물 0. CLAUDE.md / docs 의 "Collector" 단계는 미구현 (xlsx 읽기는 Parser 안에서 직접 openpyxl 호출, parser.py:283). state.raw_texts 도 같이 dead.
- Atomizer 는 Chroma 에 row 적재하지만 PG row 는 직접 INSERT 안 함 — `pipeline_runs.atomized_count` UPDATE 만 함 (db.py:194-203).
- Activity 의 `wbs_activity_id` / `l7_sub` / `l7_5_activity` / `sub_work_area` / `plan_total_qty` / `plan_mh` 는 PoC 단계 항상 None (state.py:22~48 docstring 자인). Forecaster 는 PG 에서 (company, l6_main) candidate Σ 로 보완 (db.py:145-181 `fetch_plan_for_group`).
- BPSummary 의 `bp_code` / `disc_abbrev` / `zone` / `scope` / `work_text_yesterday` / `work_text_tomorrow` 는 Parser 가 채우지만 **Mapper 가 안 씀**. 본 표는 "전파 X" 로 마킹. FE 가 이걸 직접 보고 싶으면 별도 path 필요.
- Reporter 가 산출하는 summary dict 의 `total_qty_by_trade` 는 `trade` (= l5_disc 한글, Parser disc_abbrev_to_kr) 기준. FE 가 만약 disc_abbrev 별 (영문) 으로 보고 싶으면 매핑 역변환 필요.

**§D 총 row 수: 75 field** (Parser ParsedDailyReport 6 + BPSummary 10 + JobAllocation 5 + EquipmentAllocation 6 + Activity 17 producer-별 분산 + Atomizer 산출 3+1 grouped + Forecaster row 27 + hil_2 pre_cases 6 + Optimizer row 10 + Reporter 5 = 96 logical, 본 표는 75 unique cell).

---

## §E — db.py insert helper 시그니처

> 소스: `pipeline/db.py` 전수 grep `async def` 한정 (PGClient class 의 public method).

| Function | Signature | DB target table | Source File:Line |
|---|---|---|---|
| connect | `connect(self) -> None` | (pool init, all tables) | pipeline/db.py:24 |
| close | `close(self) -> None` | (pool close) | pipeline/db.py:32 |
| fetch_bp_candidates | `fetch_bp_candidates(self, company: str) -> list[dict[str, Any]]` | activity_master (SELECT DISTINCT wa, l6_main WHERE company=$1) | pipeline/db.py:38 |
| fetch_activity | `fetch_activity(self, wbs_activity_id: str) -> dict[str, Any] \| None` | activity_master (SELECT 전체 컬럼 WHERE wbs_activity_id=$1) | pipeline/db.py:56 |
| fetch_l6_plan_mh_map | `fetch_l6_plan_mh_map(self, company: str, l6_list: list[str]) -> dict[str, int]` | activity_master (GROUP BY l6_main SUM plan_mh_rev2 WHERE company=$1 AND l6_main=ANY($2)) | pipeline/db.py:72 |
| insert_pipeline_run | `insert_pipeline_run(self, run_id: uuid.UUID, site_id: str, date: str, status: str = "running") -> None` | pipeline_runs (INSERT, fixture/FastAPI 용) | pipeline/db.py:98 |
| delete_pipeline_run | `delete_pipeline_run(self, run_id: uuid.UUID) -> None` | pipeline_runs (DELETE, fixture cleanup) | pipeline/db.py:121 |
| assert_pipeline_run_exists | `assert_pipeline_run_exists(self, run_id: uuid.UUID) -> None` (raises RuntimeError) | pipeline_runs (SELECT 1, atomizer fail-fast) | pipeline/db.py:127 |
| fetch_plan_for_group | `fetch_plan_for_group(self, company: str, l6_main: str) -> dict[str, Any] \| None` (returns plan_total_qty_by_unit + plan_mh_sum + plan_start + plan_finish) | activity_master (2 SELECT — GROUP BY unit + SUM/MIN/MAX) | pipeline/db.py:145 |
| update_run_atomized_count | `update_run_atomized_count(self, run_id: uuid.UUID, count: int) -> None` (raises RuntimeError on 0 row) | pipeline_runs (UPDATE atomized_count + current_node='atomizer') | pipeline/db.py:183 |
| insert_forecast | `insert_forecast(self, row: dict) -> None` (27 컬럼 dict) | forecasts (INSERT) | pipeline/db.py:205 |
| insert_optimizer_advice | `insert_optimizer_advice(self, row: dict) -> None` (9 컬럼 dict) | optimizer_advice (INSERT) | pipeline/db.py:273 |
| insert_mapping_correction | `insert_mapping_correction(self, run_id: uuid.UUID, report_date: date, original: dict, corrected: dict) -> None` | mapping_corrections (INSERT) | pipeline/db.py:311 |
| insert_daily_report | `insert_daily_report(self, run_id: uuid.UUID, report_date: date, report_md: str, history_csv_row: dict \| None, bp_name: str \| None = None) -> None` | daily_reports (INSERT) | pipeline/db.py:346 |

**§E 발견된 패턴 / 이슈**

- 모든 INSERT helper 는 **upsert 아님** — 동일 (run_id) 로 두 번 호출하면 daily_reports / forecasts / optimizer_advice 는 row 가 중복 INSERT 됨 (BIGSERIAL id 만 다름). FE 가 같은 run 의 데이터를 SELECT 할 때 가장 최근 row 만 쓰려면 `ORDER BY id DESC LIMIT 1` 또는 `ORDER BY created_at DESC` 필요.
- `update_run_atomized_count` 는 `current_node='atomizer'` 도 같이 박는 hard-code (db.py:196). 다른 node (mapper / forecaster / reporter) 는 pipeline_runs.current_node 를 UPDATE 하는 path **없음** → Dashboard 가 current_node 로 진행률 표시하려면 별도 trigger / FastAPI 가 직접 UPDATE 추가 필요. **drift**.
- `pipeline_runs.status` 전환 (`running` → `waiting_hil_1` / `waiting_hil_2` / `completed` / `failed`) 을 수행하는 helper **0 개**. interrupt 발생 / 재개 / 완료 시 status 가 자동 갱신되지 않음. 본 cycle scope 밖이지만 FE 가 polling 으로 status 의존하면 동작 X. **drift**.
- `sites` 테이블에 대한 INSERT / UPDATE / SELECT helper **0 개**. Layer 1 카드 (location, headcount, hours_saved, fte_saved) 는 FastAPI 가 별도 raw SQL 또는 web/ 의 Next.js API 가 직접 PG SELECT 로 처리한다는 의미. db.py 는 Cost Agent 가 아니라 pipeline-only client.
- `mapping_corrections.run_id` 는 nullable (FK ON DELETE SET NULL) 인데 graph.py:141~ 는 항상 run_id 채워 박음. 의도된 nullable 케이스 (run 삭제 후 corrections 만 살림) 는 코드 path 없음.

**§E 총 row 수: 14 함수** (`connect` / `close` 포함).

---

## 카탈로그 summary

| 표 | 총 row | 비고 |
|---|---|---|
| §A DB schema | 105 (logical) + 12 (LangGraph 자동) = 117 | 7 사용자 테이블 + 4 checkpointer 테이블 |
| §B JSONB key | 33 | row 0 없음 (전 컬럼 실 sample 확보) |
| §C LangGraph state attr | 15 | CPIAState TypedDict 전수 |
| §D Agent output field | 75~96 | dataclass + dict literal 산출물 |
| §E db.py helper | 14 | PGClient 의 모든 async public method |

**상위 drift (FE↔BE crosswalk 단계에서 다뤄야 할 사항)**

1. `state.raw_texts` 와 `collector.py` 가 dead — FastAPI 가 raw_texts 없이 직접 input_files → parser 호출하는 path 추정 (확인 필요).
2. `pipeline_runs.status` / `pipeline_runs.completed_at` / `pipeline_runs.current_node` (mapper/forecaster/reporter step) 갱신 helper 부재 — FE 의 진행률·상태 polling 이 동작 X.
3. `sites` 테이블 대상 helper 0 개 — Dashboard Layer 1 카드는 web/ 가 직접 PG SELECT 한다고 가정 (api-contract.md §3.1 verify 필요).
4. `daily_reports.history_csv_row` 컬럼명 ↔ 실 박힘 (summary dict) 의미 mismatch — 컬럼 rename 또는 docstring 정리 backlog.
5. `mapping_corrections` 의 spec (postgres.md §8) top-level 컬럼 (work_content/company/trade/correction_type) ↔ 실 schema (init.sql 6 컬럼) drift — `original`/`corrected` JSONB 안에 합쳐 박는 우회 path 로 처리됨 (db.py:319-330 자인).
6. `forecasts.similar_cases[].conditions` (list) ↔ `optimizer_advice.degradation_cases[].conditions` (comma-joined str) 타입 불일치 — FE 가 같은 의미 필드를 두 형태로 받게 됨.
7. Forecaster / Optimizer row 가 dict literal — dataclass 부재로 column rename 시 silent break 위험.

---

## §F. 2026-05-18 갱신 — api-contract.md 신규 source + 본 cycle 결정 영향

### §F.1 신규 source 인지

| Source | 경로 | 본 cycle 영향 |
|---|---|---|
| `docs/architecture/api-contract.md` | 1bbe4cd 신규 (ac42255 시점 이미 박힘) | PG ↔ types.ts 매핑 + 8 endpoint 명세. crosswalk 의 BE source 표 의 master 가 됨. §3.1 Site SQL / §3.7 ReviewItem state 추출 / §3.8 hil_1 resume body shape 명시 |

### §F.2 2026-05-18 결정으로 인한 backend 변경 요청

| 결정 | backend 변경 영향 |
|---|---|
| [[cpia-wpsummary-grain-2026-05-18]] (Q1 triplet) | **forecasts.wa TEXT 컬럼 추가** + Forecaster agent group_by tuple 3 → 4 (wa 추가) + classify_assessment / classify_risk_level 입력 변경 + idx_forecasts_company_l6 → idx_forecasts_wa_company_l6 |
| [[cpia-wpsummary-progress-path-2026-05-18]] (Q2 mapped_history) | **신규 PG 테이블 mapped_history** (run_id, report_date, site_id, wa, l6_main, company, today_qty, today_assigned_workers, unit + UNIQUE(run_id, wa, l6_main, company)) + 2 인덱스. Atomizer 가 INSERT (~30 lines + db.py helper 1). 실 row 수 ~2000 / 30일 (prod 시뮬 검증) |
| [[cpia-tasks-item-status-2026-05-18]] (5 치 BE) | `processing` 정의 (BE 협의 사항) + `blocked` 정의 (BE 협의 사항). 두 정의 모두 BE 구현 cycle Phase 0 합의 |
| [[cpia-optimizer-array-grain-2026-05-18]] (D-12 실 구현) | `pipeline/db.py` 의 optimizer_advice fetch helper = 배열 반환 (현재는 single row insert 만). FastAPI `/api/runs/:id/optimizer` = `OptimizerOutput[]` |
| [[cpia-hil1-resume-connection-2026-05-18]] (G-10) | `pipeline/api.py` (현재 0 lines) 에 FastAPI 신규 — POST /api/runs/:id/hil_1/resume. body 검증 (string key 필수) + LangGraph Command(resume=) + hil_1_node int(k) 변환 처리 |
| [[cpia-six-gaps-decisions-2026-05-18]] (G-3~G-9) | 6 endpoint 신설 — /api/runs/:id/wbs_tree (G-3), /api/sites/:id/reports (G-4), /api/dashboard/performance (G-5), /api/dashboard/impact (G-6), /api/agents/status (G-7). G-9 s_curve = BE 산식 정의 보류 (Phase 0 합의) |

### §F.3 §F.2 결정의 backend_catalog summary 영향

| 표 | 카탈로그 시점 (ac42255) | 2026-05-18 변경 후 (목표) |
|---|---|---|
| §A DB schema | 105 (logical) | 105 + 9 (mapped_history 신규) + 1 (forecasts.wa) = 115 |
| §C LangGraph state attr | 15 | 15 (변경 X) |
| §D Agent output field | 75~96 | 75 + 단계별 timestamp (옵션, BE Phase 0 합의 후) |
| §E db.py helper | 14 | 14 + insert_mapped_history_batch + fetch_wbs_tree + fetch_reports_by_date + fetch_dashboard_performance + fetch_dashboard_impact + fetch_agents_status = 20 (목표) |

### §F.4 본 cycle 미흡 영역

- §C `state.raw_texts` 와 `collector.py` 가 dead — 본 cycle 에 미해결. drift backlog #1 그대로
- §D 단계별 timestamp 부재 — `AgentStageProgress.received/processed` 의 "현재 단계 50% animated bar" 시각화 = `pipeline_runs.started_at` 만으로 시간 elapsed 휴리스틱 (state 구조 변경 없이)
- §F.2 의 6 신규 endpoint 는 본 cycle 미구현 — 다음 BE 구현 cycle 의 plan 산출물
