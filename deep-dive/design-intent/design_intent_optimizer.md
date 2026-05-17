# Design Intent — optimizer

- **Generated**: 2026-05-17 (git SHA: f9a695f5315eba97b2686f55a72bc91ef6cae6b2, branch A_Track)
- **Pair file**: `../architecture_overview.md`
- **Range**: `pipeline/agents/optimizer/` 6 파일 (agent / prompt / retrieve / synthetic_daily_report / synthetic_v2 / __init__) — 합계 ~1,485 LOC

Forecaster 가 진단한 risky 공종 중 HIL 2 에서 PM 이 선택한 그룹에 대해 Chroma 과거 유사 패턴 retrieve → LLM 으로 맥락 기반 조언. **결정 #20 (recovery_distribution 코드단 deterministic 산출 — LLM override)** + **결정 #8 (retrieve 책임은 hil_2_node 에, optimizer 는 LLM 만)**. PoC 시뮬 fixture (`synthetic_daily_report.py` + `synthetic_v2.py`) 동봉.

---

## T1 — Function Index

### agent.py
| Function/Class | File:Line | Signature | T2? |
|---|---|---|---|
| `OptimizerConfig` | agent.py:35 | `@dataclass` | — |
| `_compute_recovery_distribution` | agent.py:48 | `(cases: list) -> dict` | ✅ |
| `_compose_cold_start_row` | agent.py:61 | `(r, cases, run_id) -> dict` | — |
| `_compose_row` | agent.py:75 | `(r, cases, llm_output, run_id) -> dict` | — |
| `_call_azure_llm` | agent.py:91 | `(llm_input, cfg, azure) -> dict` | — |
| `optimize` | agent.py:106 | `async (forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg) -> list` | ✅ |

### prompt.py
| Object | File:Line | T2? |
|---|---|---|
| `SYSTEM_PROMPT` | prompt.py:21 | ✅ |
| `FEW_SHOT_MESSAGES` | prompt.py:61 | — |
| `build_llm_user_input` | prompt.py:286 | ✅ |

### retrieve.py
| Function | File:Line | T2? |
|---|---|---|
| `_group_day_productivity` | retrieve.py:33 | — |
| `_group_baseline` | retrieve.py:46 | ✅ |
| `fetch_degradation_cases` | retrieve.py:69 | ✅ |
| `fetch_recovery_trajectory` | retrieve.py:117 | — |

### synthetic_daily_report.py
| Function | File:Line | T2? |
|---|---|---|
| `generate_fake_daily_report` | synthetic_daily_report.py:50 | ✅ |
| `_parse_scenario` | synthetic_daily_report.py:118 | — |
| `_check_synthetic_v2_loaded` | synthetic_daily_report.py:137 | — |
| `_ensure_site` | synthetic_daily_report.py:144 | — |
| `_load_baseline_inputs` | synthetic_daily_report.py:155 | — |
| `_initial_state` | synthetic_daily_report.py:239 | — |
| `_build_optimizer_config` | synthetic_daily_report.py:267 | — |
| `_build_forecaster_config` | synthetic_daily_report.py:282 | — |
| `build_demo_graph_config` | synthetic_daily_report.py:298 | — |
| `_main_cli` | synthetic_daily_report.py:339 | — |

### synthetic_v2.py
| Function | File:Line | T2? |
|---|---|---|
| `generate_synthetic_v2_group` | synthetic_v2.py:35 | ✅ |
| `_main_cli` | synthetic_v2.py:169 | — |

### __init__.py
- `__all__ = ["OptimizerConfig", "generate_synthetic_v2_group", "optimize"]`

---

## T2 — Issue Cards

### `optimize` — Selected group 별 advice 생성 + PG insert

- **위치**: `pipeline/agents/optimizer/agent.py:106-157` (52 LOC, 분기 3)
- **시그니처**: `async def optimize(forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg) -> list[dict]`
- **이슈**:
  - git log `36e24e9` (optimizer/Task 6: agent.py optimize + cold_start + _compute_recovery_distribution + PG insert_optimizer_advice (TDD 4 신규))
  - git log `ba5d274` (optimizer/Task 11: synthetic_daily_report + build_demo_graph + CLI (E2E demo, slow))
  - 파일 docstring (agent.py:1-14): "원칙: retrieve import X — pre_optimizer_cases (state 사전 영속) 만 사용 (결정 #8 + F5). _compute_recovery_distribution 은 코드단 deterministic 산출 (결정 #20). LLM 응답이 recovery_distribution 박았으면 override X (코드 값이 정답). cold_start (len(cases) < 3): LLM skip. fail-fast: LLM crash 시 exception 그대로 raise (결정 #10). temperature 박지 않음 (gpt-5 family 미지원 — 결정 #9)."
  - 메타: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §7` (optimize() 스펙).
- **설계 의도**:
  - 책임 분리 (결정 #8): retrieve 는 hil_2_node 에서 끝. optimizer 는 받은 `pre_optimizer_cases` 만 소비 → 결정론 보장 (resume 후 retrieve 재호출 시 분포 변동 risk 회피).
  - LLM override (결정 #20): recovery_distribution 은 Counter 기반 코드 산출이 정답. LLM 이 박았어도 덮어씀.
  - cold_start 영속: cases<3 이어도 PG INSERT (signal 보존, drift 추적용).
  - fail-fast (결정 #10): LLM crash 시 retry 없이 raise — 운영에서 silent miss 방지.
  - gpt-5.1 호환 (결정 #9): temperature 인자 미사용 (gpt-5 family unsupported).
- **대응 패턴**:
  - 발동: `graph.py:optimizer_node` 가 hil_2_selection 비어있지 않을 때
  - 입력: forecast list + hil_2_selection (group keys) + pre_optimizer_cases (사전 영속) + run_id + today + cfg
  - 처리: selected 그룹 순회 → cases<3 cold_start path / cases>=3 LLM path → recovery_distribution override → PG insert
  - 출력: optimizer_advice list
- **관련**:
  - `graph.py:optimizer_node:180`
  - `_compute_recovery_distribution / _compose_cold_start_row / _compose_row / _call_azure_llm` (내부 헬퍼)
  - `db.py:insert_optimizer_advice:273`
  - `build_llm_user_input` (prompt.py:286)
  - 테스트: `test_agent.py` (4 케이스 — skip / cold_start / LLM / mock), `test_integration.py:156 test_optimize_namwong_e2e`
- **Suspected related** (2026-05-17 stale):
  - audit drift #2 (Optimizer 약한 권고) — 본 함수의 LLM 출력 품질 검증 대상.
  - HIL 2 4 path test (test_graph_e2e_hil2.py) — 본 함수의 진입 경로.

---

### `_compute_recovery_distribution` — Counter 기반 결정론 산출

- **위치**: `pipeline/agents/optimizer/agent.py:48-58` (11 LOC)
- **시그니처**: `def _compute_recovery_distribution(cases: list[dict]) -> dict[str, int]`
- **이슈**:
  - docstring (agent.py:48-52): "결정 #20 — 코드단 deterministic 산출. LLM 출력 override. Counter([c.recovery.recovery_days for c in cases]) → {'d+1': N, 'd+2': N, ..., 'not_recovered': N}"
  - 메타: spec §7 + 결정 #20 명시. test_compute_recovery_distribution_deterministic (test_agent.py:211).
- **설계 의도**:
  - LLM 비결정성 회피: 회복 일수 분포는 산술적 사실. LLM 추론이 아닌 Counter 로 산출 → 같은 cases 입력 → 같은 분포.
  - 라벨 통일: `d+N` 또는 `not_recovered` — 다운스트림 시각화 일관성.
- **대응 패턴**:
  - 발동: `_compose_cold_start_row` + `_compose_row` 모두 호출
  - 입력: degradation cases list (각 case 에 `recovery.recovery_days` 박힘)
  - 처리: Counter
  - 출력: 분포 dict
- **관련**:
  - `optimize` (호출자)
  - `fetch_recovery_trajectory` (retrieve.py:117 — recovery_days 산출 source)
  - 테스트: `test_agent.py:211-212` (4건 counter 검증), `test_integration.py:246` (sum == len(deg_cases))
- **Suspected related** (2026-05-17 stale):
  - audit drift D-6 (recovery_distribution conditions 필터 검증) — 본 함수의 입력 cases 의 conditions 필터링 path.

---

### `_group_baseline` — incident 5종 제외 정상 productivity 평균

- **위치**: `pipeline/agents/optimizer/retrieve.py:46-66` (21 LOC, 분기 3)
- **시그니처**: `def _group_baseline(metadatas, company, l6_main, baseline_unit) -> Optional[float]`
- **이슈**:
  - git log `22c2104` (optimizer/Task 4: retrieve.py 2 함수 + 헬퍼 2개 (TDD 12 신규))
  - git log `a1d3336` (optimizer/Task 4 fix: degradation/recovery threshold 모듈 상수 추출 (일관성))
  - docstring (retrieve.py:46-56): "같은 (company, l6_main, unit) 의 conditions 에 incident 없는 row productivity 평균. 0 row → None (cold_start 신호 — 호출자가 pre_cases[key]=[] 분기). incident 키워드: 장비대기 / 자재미입고 / 우천 / 돌관 / 야간연장."
  - 상수 (retrieve.py:20-26): `_DEGRADATION_INCIDENTS = ("장비대기","자재미입고","돌관")`, `_ALL_INCIDENTS = ("장비대기","자재미입고","우천","돌관","야간연장")`, `_DEGRADATION_RATIO=0.85`, `_RECOVERY_RATIO=0.95`.
- **설계 의도**:
  - baseline 정의 명확화: incident 5종 제외 = "정상 상황" → 그 평균이 baseline. 저하 cases 판정 (`< baseline × 0.85`) 의 기준점.
  - cold_start 신호 (None): hil_2_node 가 본 결과 None 일 때 `pre_cases[key]=[]` 박음 (graph.py:124 F7 정정).
- **대응 패턴**:
  - 발동: `hil_2_node` 그룹별 호출 (graph.py:124)
  - 입력: 그룹 metadatas + company + l6_main + baseline_unit
  - 처리: 5종 incident 모두 제외 → productivity 평균
  - 출력: float | None
- **관련**:
  - `hil_2_node:graph.py:71` (호출자)
  - `fetch_degradation_cases:retrieve.py:69` (baseline × 0.85 사용)
  - 테스트: `test_retrieve.py` (group_baseline_normal_only_excludes_all_incidents_inc_dolgwan / none_when_no_normal_rows 등)
- **Suspected related** (2026-05-17 stale):
  - audit drift backlog §5.2 (synthetic baseline_qty 산출 bug) — 본 baseline 산출과 별개. CLI 시뮬 시 today_prod 와 baseline 의 산술 정합 의심.

---

### `fetch_degradation_cases` — 저하 case top-N (incident 3종)

- **위치**: `pipeline/agents/optimizer/retrieve.py:69-114` (46 LOC, 분기 2)
- **시그니처**: `def fetch_degradation_cases(metadatas, documents, company, l6_main, today, ..., n=5) -> list[dict]`
- **이슈**:
  - git log `22c2104` / `1e35b17` (degradation/recovery threshold 모듈 상수 추출)
  - docstring (retrieve.py:69-84): "Step 1 — 같은 (company, l6_main) 의 저하 case top-N recency. 저하 정의: conditions ∋ {장비대기, 자재미입고, 돌관} AND group productivity < baseline*0.85. worker_source ∈ {synthetic_v2, mh_prorated} 만 허용 (단순 synthetic 노이즈 회피). date < today (미래 행 제외). conditions 는 comma-joined str → substring in 검사."
- **설계 의도**:
  - 저하 trigger 3종 명시: 장비대기/자재미입고/돌관 (우천/야간연장 제외 — baseline 제외 5종 중 일부).
  - worker_source 필터: legacy "synthetic" 제외 (synthetic_v2 와 실 mh_prorated 만) — 데이터 품질 보호.
  - in-memory filter: Chroma where 가 substring in 미지원, Python 단 substring check.
- **대응 패턴**:
  - 발동: `hil_2_node` 그룹별 호출
  - 입력: 그룹 metadatas + documents + filter args
  - 처리: 6 단계 filter (company/l6/date/worker_source/conditions/baseline ratio) → recency sort → top-n
  - 출력: cases list
- **관련**:
  - `hil_2_node:graph.py` (호출자 — coll.get(...) 1회 후 전달)
  - `_group_baseline:retrieve.py:46`
  - 테스트: `test_retrieve.py:fetch_degradation_cases_*` (incident_str_substring / excludes_legacy_synthetic / includes_dolgwan 등)
- **Suspected related** (2026-05-17 stale):
  - `fetch_recovery_trajectory:retrieve.py:117` — 본 함수의 cases 각각에 대해 trajectory 산출.
  - audit drift D-6: conditions 필터 적용 path 검증.

---

### `SYSTEM_PROMPT` — 명령형 회피 진단+권고 tone

- **위치**: `pipeline/agents/optimizer/prompt.py:21-54` (한글 34 줄)
- **시그니처**: `SYSTEM_PROMPT: str` (상수)
- **이슈**:
  - git log `1e35b17` (optimizer/Task 5: prompt.py SYSTEM_PROMPT + FEW_SHOT 3 + build_llm_user_input (TDD 3 신규)).
  - 파일 docstring (prompt.py:1-10): "Optimizer prompt — SYSTEM_PROMPT + FEW_SHOT_MESSAGES + build_llm_user_input. 원칙: SYSTEM_PROMPT 는 한글 + 영어만 (한자 0건). 명령형 tone ('확인 필수' / '반드시' / '해야 합니다') 회피 — 선택지 제시 형식 ('권장' / '권고' / '검토 권장')."
  - 본문 (prompt.py:33-37): `권고사항 tone: "확인 권장" / "검토 권고" / "고려 필요" — 선택지 제시 / 단정형 / 강제형 표현 회피 (선택지 제시 형식 유지)`.
  - 본문 (prompt.py:51-53): `최종 판단 및 실행은 PM 결정 사항. 권고는 근거 기반 선택지 제시. ... 한자 사용 금지 (한글 + 영어).`
- **설계 의도**:
  - 의사결정 권한 분리: PM 이 최종 결정 → LLM 은 근거 + 선택지 제공. 단정형 회피로 권한 침범 방지.
  - tone 검증 (test_system_prompt_korean_no_command_tone): CJK 한자 (U+4E00~U+9FFF) 0건 + 명령형 단어 회피 검증.
  - few-shot 3 pair (장비대기/자재미입고/미회복) — 의도된 응답 형식 학습.
- **대응 패턴**:
  - 발동: `_call_azure_llm` 호출 시 system message
  - 입력: 없음 (상수)
  - 처리: LLM messages 의 system role
  - 출력: prompt str
- **관련**:
  - `FEW_SHOT_MESSAGES` (prompt.py:61-278)
  - `build_llm_user_input` (prompt.py:286)
  - 테스트: `test_prompt.py:test_system_prompt_korean_no_command_tone / test_few_shot_messages_count_3`
  - 페어 spec: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §6.1` (tone), §6.2 (권고사항 rank 4단계)
- **Suspected related** (2026-05-17 stale):
  - audit drift D-3 (PM 원안 §2 권고사항 vs LLM advice 의미 일치 정성화) — 본 prompt 의 권고 출력이 그 검증 대상.

---

### `build_llm_user_input` — Forecaster row + degradation cases 합쳐 LLM input

- **위치**: `pipeline/agents/optimizer/prompt.py:286-315` (30 LOC)
- **시그니처**: `def build_llm_user_input(forecast_row: dict, degradation_cases: list[dict]) -> dict`
- **이슈**:
  - docstring (prompt.py:286-294): "forecast_row 는 §2.2 의 ForecastRow schema 가정 — main_unit / today_productivity / today_conditions 박힘. Input contract for degradation_cases: each case must be a dict containing keys from fetch_degradation_cases output (date / conditions / productivity / activities / assigned_workers) PLUS a 'recovery' key with fetch_recovery_trajectory output ({'trajectory': [...], 'recovery_days': int|None}). Caller (agent.py optimize()) is responsible for merging the two retrieve results."
- **설계 의도**:
  - input contract 명시: caller (optimize) 가 fetch_degradation_cases + fetch_recovery_trajectory 두 결과를 merge 한 cases 전달.
  - v3.1 신규 필드 박힘: main_unit + today_conditions (Forecaster row schema 변화 흡수).
- **대응 패턴**:
  - 발동: `optimize` 가 cases 준비 후 호출
  - 입력: forecast row + degradation cases (recovery 포함)
  - 처리: dict 재구성 (today / 과거 / plan 정리)
  - 출력: LLM user message dict
- **관련**:
  - `optimize` (호출자)
  - 테스트: `test_prompt.py:test_build_llm_user_input_includes_today_conditions / test_build_llm_user_input_empty_degradation_cases`
  - 페어 spec: §2.2 (ForecastRow schema), §6.3 (build_llm_user_input)
- **Suspected related** (2026-05-17 stale):
  - drift backlog §1.6 footnote (Forecaster row 2 필드 추가 — main_unit, today_conditions Task 0) — 본 함수가 그 변경의 소비처.

---

### `generate_synthetic_v2_group` — 90일 시계열 상태기계 (7 룰)

- **위치**: `pipeline/agents/optimizer/synthetic_v2.py:35-166` (132 LOC, 분기 8+)
- **시그니처**: `def generate_synthetic_v2_group(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days=90, seed=42, reference_date=None) -> list[dict]`
- **이슈**:
  - git log `cb497fc` (optimizer/Task 2: synthetic_v2.py state machine 7 룰 + work_content 단순 활동명 + workers prorate (TDD 10 신규))
  - git log `8546596` (optimizer/Task 3: synthetic_v2 CLI + 현 synthetic 810 DROP + v2 적재 + baseline 재산출)
  - 파일 docstring (synthetic_v2.py:1-18): "synthetic v2 state machine — 시계열 회복 룰 7건 (spec §4.1 + §4.2). 룰: 1. 장비대기 1일차 × (1 - random[0.20, 0.35]) / 2. 장비대기 → 익일 80% 정상 / 20% 2일차 지속 / 3. 장비대기 2일차 → 30% 만회 ×1.10 / 70% 정상 / 4. 우천 연속 2일 → 3일차 ×1.10 만회 / 5. 자재미입고 → 50% 정상 / 50% 2일차 / 6. 야간연장 → 익일 ×0.90 fatigue / 7. 돌관 당일 productivity ×0.85 + workers ×1.3 spike."
  - state machine: last_incident, rain_streak, equip_wait_streak 3 state (synthetic_v2.py 의사코드).
  - 인라인 (synthetic_v2.py:26-32): `# spec §3.4 — 9/25 작업일보 BP사별 총 인원 (시트1 today_incr 합). 출처: /tmp/cpia_flow_sim.py 실 호출 결과. _BP_TOTAL = {남웅건설:88, 세보엠이씨:1387, 창원기전:372}`.
  - 가중치 (synthetic_v2.py:93-102): `incident = rng.choices(["정상","장비대기","자재미입고","야간연장","돌관"], weights=[6, 1.5, 1.5, 0.5, 0.5])` — 정상 60%, 장비대기/자재미입고 15% 각, 야간연장/돌관 5% 각.
- **설계 의도**:
  - 시계열 회복 패턴 시뮬: 단순 random 변동이 아닌 state machine 으로 incident → recovery sequence 모델링 (Optimizer 가 "과거 패턴" 추출 가능하게).
  - 5종 incident 정의: 장비대기/자재미입고/우천/야간연장/돌관 — **병행작업 (병행 incident) 미포함** (drift backlog D-1).
  - 돌관 특이성: 인원 spike (×1.3) + productivity 저하 (×0.85) 동시 — 혼잡 효과 모델링.
- **대응 패턴**:
  - 발동: `_main_cli` 가 27 그룹 × 90일 = 2,430 row batch 생성
  - 입력: 그룹 메타 + activity_pool + baseline_workers/qty + days + seed
  - 처리: day 순회 → state 갱신 → incident 결정 → productivity delta 산출
  - 출력: list[atomizer schema dict]
- **관련**:
  - `_main_cli` (synthetic_v2.py:169) — Chroma upsert + baseline 재산출
  - 테스트: `test_synthetic_v2.py` (8 케이스 — 룰 1~7 통계 검증), `test_integration.py test_synthetic_v2_chroma_upsert_distribution`
  - 페어 spec: `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md §3-§4.8`
- **Suspected related** (2026-05-17 stale):
  - audit drift D-1 (병행작업 룰 부재) — 본 함수의 incident enum 확장 후보.

---

### `generate_fake_daily_report` — Activity list 직접 생성 (drift #3 후보)

- **위치**: `pipeline/agents/optimizer/synthetic_daily_report.py:50-110` (61 LOC, 분기 2)
- **시그니처**: `def generate_fake_daily_report(report_date, scenarios, activity_pools, baseline_workers, baseline_qty, seed=42) -> list[Activity]`
- **이슈**:
  - git log `ba5d274` (optimizer/Task 11: synthetic_daily_report + build_demo_graph + CLI (E2E demo, slow))
  - docstring (synthetic_daily_report.py:50-66): "Activity list 직접 생성 (§10.2 그대로). scenarios 예: {company, l6_main, n_activities, incident, productivity_ratio, workers_ratio, unit}. 반환: list[Activity] — mapper output 형식. atomizer/forecaster 호환."
  - 인라인 (synthetic_daily_report.py:78): `today_qty = round(baseline_q * sc["productivity_ratio"], 1)` — drift #3 의심 라인.
  - 인라인 (synthetic_daily_report.py:77-81): `# conditions list[str] (state.Activity 계약 — forecaster:92 iterate) / conditions_list = ["맑음"] + ([cond] if cond != "정상" else [])`.
  - 메타: `docs/audit/2026-05-17-cpia-drift-backlog.md §3` — 시뮬 1/2/3 today_prod (69.62/74.26/32.13) 과 baseline 31.07 의 산술 정합 의심.
- **설계 의도**:
  - Mapper 우회: 실 xlsx + LLM 매핑 비용 회피하고 mapper output Activity 직접 주입 → demo_graph 진입.
  - state.Activity 계약 준수: `conditions: list[str]` 형식 (atomizer/forecaster 가 iterate).
  - productivity_ratio 명시: 시나리오마다 baseline 대비 비율을 받아 today_qty 결정.
- **대응 패턴**:
  - 발동: `_main_cli` (Task 11) E2E demo
  - 입력: report_date + scenarios + baseline dicts + seed
  - 처리: 각 scenario 마다 n_activities 만큼 Activity dict 생성 (baseline × productivity_ratio)
  - 출력: list[Activity]
- **관련**:
  - `build_demo_graph` (graph.py:200)
  - `_load_baseline_inputs` (synthetic_daily_report.py:155) — baseline_qty 산출 (drift §5.2 의심)
  - 테스트: `test_synthetic_daily_report.py` (Activity dict 형식 / 돌관 시나리오 실 LLM)
- **Suspected related** (2026-05-17 stale):
  - **audit drift #3 (productivity_ratio bug)**: 본 함수의 today_qty 계산 라인 + `_load_baseline_inputs` 의 baseline_qty 산출 (`Σplan_total_qty / days`) 산술 재현 필요.

---

## 관찰

- **한자 사용 0건** (test_system_prompt_korean_no_command_tone 으로 자동 검증).
- **TODO/FIXME/NotImplementedError 0건**.
- **synthetic 두 path 통합 미진**:
  - `synthetic_v2.py` (90일 시계열, 27 그룹) — Chroma 적재용 cold start.
  - `synthetic_daily_report.py` (E2E demo 입력) — 1일 fixture.
  - drift D-2: cold_start 2 path 통합 권고.
- **audit drift 주요 진입점**:
  - #2 (Optimizer 약한 권고): `optimize` + SYSTEM_PROMPT 검증.
  - #3 (synthetic productivity_ratio bug): `generate_fake_daily_report` + `_load_baseline_inputs` 산술 재현.
  - D-1 (병행작업 룰): `generate_synthetic_v2_group` incident enum 확장.
  - D-3 (LLM advice 의미 일치): `SYSTEM_PROMPT` + few-shot 정성화.
- **결정 #8/#20 핵심**: retrieve 책임 hil_2_node 단일화 + recovery_distribution 코드 deterministic → resume 후 결정론 보장.
- **gpt-5.1 호환 (결정 #9)**: temperature 미사용, fail-fast (결정 #10).

---

## 2026-05-17 hil1-forecaster-reporter cycle 변경 (Git SHA d57b0c5)

### `generate_fake_daily_report` — drift #3 해소 (line 78 산식 정정)

- **변경**: `pipeline/agents/optimizer/synthetic_daily_report.py:78`
  - 이전 (bug): `today_qty = round(baseline_q * sc["productivity_ratio"], 1)` — N row 가 모두 같은 group total 값을 가짐 → group total = N × baseline × ratio 오버산출
  - 신: `today_qty = round(baseline_q * sc["productivity_ratio"] / sc["n_activities"], 1)` — row 당 분배 → group total = baseline × ratio (의도 부합)
- **영향**: ratio=0.45, n=5 시 today_prod = baseline_prod × 0.45 = 13.98 (이전 = 69.91) → Forecaster `classify_assessment_rag` 가 -55% delta 인식 → assessment="이상" 발현 (이전 = "정상" bias).
- **drift #2 연관**: classify.py:34 수정 X (PM 원안 v2 정합). #2 root cause = #3 input 의 over-산출 → #3 fix 로 자동 해소.
- **commit**: `c093631` fix(synthetic_daily_report): n_activities 오버산출 버그 + RAG 정합 가드
- **테스트**: `tests/optimizer/test_synthetic_daily_report_fixture.py` (재현 + 가드 + RAG 정합 3건). `tests/optimizer/test_synthetic_daily_report.py:90` 기존 unit assertion 정정 (row 당 + group total 양쪽 검증).

### `_parse_scenario` — n_activities ValueError 가드 추가

- **변경**: `pipeline/agents/optimizer/synthetic_daily_report.py:118`
  - 추가: `n_act = int(parts[2]); if n_act <= 0: raise ValueError("n_activities > 0 필요 — 입력: {n_act} ({raw})")`
- **이슈**: 산식이 `/ n_activities` 분배로 변경됨 → n=0 시 ZeroDivisionError 회피 fail-fast.
- **테스트**: `test_fixture_n_activities_zero_raises` 검증.

### T1 신규 함수 1

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_build_reporter_config` | synthetic_daily_report.py:285 | `() -> ReporterConfig` | env injection — `build_demo_graph_config` 확장 위해 신규 | — |

`build_demo_graph_config` (synthetic_daily_report.py:303) 에 `reporter=_build_reporter_config()` 추가 — build_demo_graph 가 reporter_node 진입 시 필수.

### 신규 drift

- **#N1**: RAG fixture_prod vs synthetic_v2 분포 ±10% mismatch (delta=10.7%). `tests/optimizer/test_synthetic_daily_report_fixture.py::test_fixture_rag_alignment` xfail strict=False 마킹. synthetic_v2 적재 분포 vs 90일 baseline 정렬은 별 cycle.
- **#N4**: 시뮬 2 (우천 0.8) + 시뮬 3 (돌관 0.45 ×1.3) + 시뮬 4 (cold_start) 추가 검증 skip. 시뮬 1 + rerun 으로 7 성공 기준 충족, 추가 path 별 cycle.
- **#N7**: `synthetic_daily_report._main_cli` final 출력에 `final.get("report_md")` print 미추가 — 가독성 개선 별 cycle.

### 시뮬 1 실 검증 결과

- raw: `docs/audit/raw/v2-scenario-1-156657ed.md`
- 결정성: 시뮬 1 vs rerun 결정론 컬럼 diff 0 (assessment + risk + recovery_distribution 100% 일치)
- Reporter 영속: PG daily_reports row 1건 (md_len=1481, summary 4 키)
- Azure 비용 ~$0.20 (시뮬 1 + rerun)
