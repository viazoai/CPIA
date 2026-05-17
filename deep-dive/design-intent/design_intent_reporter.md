# Design Intent — reporter

- **Generated**: 2026-05-17 (hil1-forecaster-reporter cycle 신규)
- **Git SHA**: `d57b0c5` (A_Track, PR #19 pending)
- **Pair file**: `../architecture_overview.md` §2.reporter
- **Range**: `pipeline/agents/reporter.py` (161 LOC, 본 cycle 신규) + `pipeline/tests/test_reporter.py` (177 LOC, 3건)

Mapper 확정 + Forecaster 진단 + Optimizer 권고 → 마크다운 종합 보고서 1 종 + PG `daily_reports.history_csv_row` JSONB 영속. Azure gpt-5.1 호출 1회 (per run). 의도적 drift = Reporter 위치 = Optimizer 다음 (원안 v2 = Atomizer 다음 병렬). drift #1 (PoC 성공 기준 #1) 해소.

---

## T1 — Function Index

| Function/Class | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `SYSTEM_PROMPT` | reporter.py:24 | str | 3 부 구조 마크다운 schema (작업 통합 / 진단 / 권고) + 한자 금지 + 들여쓰기 룰 | — |
| `ReporterConfig` | reporter.py:51 | `@dataclass` | Azure 크레덴셜 + LLM model + PG URL + timeout/retries | ✅ |
| `_build_llm_input` | reporter.py:62 | `(mapped, forecast_rows, optimizer_advice, today) -> dict[str, Any]` | LLM user message JSON 빌더 (4 키: date + activities + forecast + optimizer_advice) | ✅ |
| `_build_summary` | reporter.py:88 | `(mapped, forecast_rows, optimizer_advice) -> dict` | history_csv_row JSONB summary (total_workers + total_qty_by_trade + risk_counts + advice_count) | ✅ |
| `report` | reporter.py:114 | `async (mapped, forecast_rows, optimizer_advice, run_id, today, cfg) -> tuple[str, dict]` | 종합 보고서 생성 + PG INSERT (공개 API) | ✅ |

**T1 커버리지**: 5 / 5 = 100% (public 함수 + dataclass 모두 인덱스)

---

## T2 — Issue Cards

### `report` — 종합 보고서 생성 + PG INSERT 공개 API

- **위치**: `pipeline/agents/reporter.py:114-161` (48 LOC, 분기 2)
- **시그니처**: `async def report(mapped: list[Activity], forecast_rows: list[dict], optimizer_advice: list[dict], run_id: uuid.UUID, today: _date, cfg: ReporterConfig) -> tuple[str, dict]`
- **이슈**:
  - git log `22d44c2` (feat(reporter): Mapper+Forecaster+Optimizer 종합 보고서 + PG daily_reports) — 최초 + 본 cycle 종결.
  - 컨테이너 spec: `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3` — Reporter 위치 = Optimizer 다음 (의도적 drift, PM 원안 v2 = Atomizer 다음 병렬).
  - 원안 drift 메모 (commit msg `22d44c2`): "위치 결정: Optimizer 다음 (또는 hil_2 selection=[] 분기 합류). PM 원안 v2 의 'Atomizer 다음 병렬' 과 의도적 drift — 사용자 결정으로 Forecaster + Optimizer 결과 모두 포함하는 종합 보고서로 변경."
  - drift backlog: #1 (PoC 성공 기준 #1 직접 미충족 — 본 commit 으로 해소).
- **설계 의도**:
  - 종합 1 종: 사내/발주처 분리 보고서 (원안 2 종) → PoC 시연 단순화 = 종합 1 종 + 3 부 구조 (작업 통합 / 진단 / 권고).
  - Optimizer 다음: Forecaster + Optimizer 결과 모두 포함하여 1 LLM call 로 종합 — Forecaster 와 병렬 산출 시 Optimizer 권고 미포함 우려.
  - empty fallback: `mapped` 빈 list → 짧은 "보고서 생성 실패" MD + PG INSERT skip (FK violation 방지).
  - PG 영속: `daily_reports.history_csv_row` JSONB 컬럼에 summary 박음 (postgres.md §5 spec 의 `summary` 필드명 mismatch — drift #N3, JSONB 의미 동일).
  - `bp_name=None`: 종합 보고서이므로 BP사 단위 없음 (실 schema 의 nullable 활용).
- **대응 패턴**:
  - 발동: `graph.py:reporter_node:311` 가 호출 (hil_2 conditional_edge 의 양쪽 path 모두 — selection=[] 또는 optimizer → reporter)
  - 입력: mapped (Mapper 확정) + forecast_rows (Forecaster 진단) + optimizer_advice (Optimizer 권고, 빈 list 가능) + run_id + today + cfg
  - 처리: empty 검사 → AzureOpenAI client 생성 (timeout 60s, max_retries 3) → `_build_llm_input` JSON → chat.completions.create → response.choices[0].message.content 추출 (None 시 fallback) → `_build_summary` → PGClient connect → `insert_daily_report` (history_csv_row=summary) → close
  - 출력: `(report_md, summary)` tuple
- **관련**:
  - 호출자: `graph.py:reporter_node:311`
  - 내부 헬퍼: `_build_llm_input` + `_build_summary`
  - PG INSERT: `db.py:insert_daily_report:339` (drift #N3 schema mismatch — original/corrected JSONB 안에 합쳐 박는 패턴)
  - 테스트: `tests/test_reporter.py` 3건 (empty fallback + LLM mock 종합 + 3부 생략 prompt)
  - 페어 spec: `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3` + plan §Task 3 + raw `docs/audit/raw/v2-scenario-1-156657ed.md` (시뮬 1 실 호출 검증, report_md 1481 chars + summary 4 키)
- **Suspected related** (2026-05-17 stale):
  - `forecaster/agent.py:_call_azure_llm` — 동일 Azure gpt-5.1 호출 패턴 (timeout + max_retries) — 향후 공통 helper 추출 후보.
  - `optimizer/agent.py:_call_azure_llm` — 동일 패턴.
  - `_build_llm_input` 의 JSON serialization 에서 UUID 처리 = `json.dumps(default=str)` — synthetic_daily_report 호출 시 forecast row 의 UUID 객체 직렬화 정합 (drift backlog 미포함, 본 cycle 내 fix).

---

### `_build_llm_input` — LLM user message JSON 빌더

- **위치**: `pipeline/agents/reporter.py:62-86` (25 LOC, 분기 0 — list comprehension)
- **시그니처**: `def _build_llm_input(mapped: list[Activity], forecast_rows: list[dict], optimizer_advice: list[dict], today: _date) -> dict[str, Any]`
- **이슈**:
  - spec `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md §5.3 few-shot fixture 형식` — input JSON 구조 명시.
  - docstring (reporter.py:62): "LLM user message JSON 빌더 — spec §5.3 few-shot 형식."
  - test (`tests/test_reporter.py::test_reporter_empty_optimizer_advice_skips_3bu`) — empty advice 시 input dict 의 optimizer_advice 가 빈 list 보장.
- **설계 의도**:
  - schema 명시: 4 키 (date + activities + forecast + optimizer_advice) — Reporter LLM 이 3 부 구조 mapping 위해 의도된 layout.
  - 1 부 → activities (mapped 합산용 row 추출, 7 필드: company/trade/l6_main/unit/today_qty/assigned_workers/work_content)
  - 2 부 → forecast (Forecaster row dict 그대로 — risk_level/today_productivity/assessment/reasoning)
  - 3 부 → optimizer_advice (Optimizer row dict 그대로 — diagnosis/recommendations/recovery_distribution). 빈 list 시 LLM 이 3 부 생략 (SYSTEM_PROMPT 명시).
  - `Activity` TypedDict 전체가 아닌 7 필드만 추출 — 본인 의도 외 노이즈 제거 (예: mapping_conf, wbs_activity_id 등 LLM 무관).
- **대응 패턴**:
  - 발동: `report` 내부에서 LLM 호출 직전
  - 입력: mapped + forecast_rows + optimizer_advice + today
  - 처리: dict 빌드 (date isoformat + activities list comprehension + forecast pass-through + optimizer_advice pass-through)
  - 출력: `dict[str, Any]` (4 top-level 키)
- **관련**:
  - 호출자: `report:130`
  - 테스트: `tests/test_reporter.py:test_reporter_empty_optimizer_advice_skips_3bu`
- **Suspected related** (2026-05-17 stale):
  - `optimizer/prompt.py:build_llm_user_input` — 동일 LLM input contract 패턴 (forecast_row + deg_cases).
  - `forecaster/prompt.py:build_llm_user_input` — 동일 패턴.

---

### `_build_summary` — daily_reports.history_csv_row JSONB summary

- **위치**: `pipeline/agents/reporter.py:88-112` (25 LOC, 분기 3 — for loop × 2 + if)
- **시그니처**: `def _build_summary(mapped: list[Activity], forecast_rows: list[dict], optimizer_advice: list[dict]) -> dict`
- **이슈**:
  - spec `§5.3` 의 LLM 산출과 별도 — Dashboard / 운영 감사용 핵심 지표 (machine-readable summary).
  - postgres.md `§5 daily_reports.summary` JSONB 컬럼 (실 schema 는 `history_csv_row` — drift #N3 mismatch).
  - docstring (reporter.py:89): "summary JSONB — daily_reports.history_csv_row 컬럼에 박힘. 운영 감사용 핵심 지표 (Dashboard 카드 소스)."
- **설계 의도**:
  - 4 핵심 지표 (Dashboard Layer 1 카드 소스 의도):
    - `total_workers`: 전 row assigned_workers 합 (BP사 인원 총)
    - `total_qty_by_trade`: trade 별 today_qty 합 (공종별 일일 물량)
    - `risk_counts`: {"정상": N, "주의": N, "이상": N} — Forecaster risk_level 분포
    - `advice_count`: Optimizer advice row 수 (= 0 시 reporter 3 부 생략)
  - 결정성: LLM 비결정성 컬럼 (report_md) 와 별도 — 결정론 코드만 산출 → 결정성 검증 정합.
  - JSONB 합쳐 박음: postgres.md drift #N3 의 경우 schema migration 별 cycle 까지 임시 처리 (의미 동일).
- **대응 패턴**:
  - 발동: `report` 내부에서 PG INSERT 직전
  - 입력: mapped + forecast_rows + optimizer_advice (3 동일 입력)
  - 처리: trade 별 합산 (dict accumulator) + risk_counts (Counter 패턴, 3 키 fix) + 단순 sum/len
  - 출력: `dict` (4 키 명시)
- **관련**:
  - 호출자: `report:139`
  - PG INSERT: `db.py:insert_daily_report:339` (history_csv_row 인자)
  - 테스트: `tests/test_reporter.py::test_reporter_llm_mock_full_flow` (summary 4 키 검증)
- **Suspected related** (2026-05-17 stale):
  - `forecaster/agent.py:insert_forecast` row 의 conditions (CSV) — 비슷한 기계 readable 영속 패턴.
  - 향후 Dashboard 가 SELECT 시 활용 — B_Track 미구현 (drift #5).

---

### `ReporterConfig` — Azure + PG + timeout/retries 묶음

- **위치**: `pipeline/agents/reporter.py:51-60` (10 LOC, dataclass)
- **시그니처**: `@dataclass class ReporterConfig: azure_endpoint, azure_api_key, azure_api_version, llm_model, postgres_url, azure_timeout: float = 60.0, azure_max_retries: int = 3`
- **이슈**:
  - 패턴 = `ForecasterConfig` + `OptimizerConfig` 동일 — Azure 통일 (audit-report §3 명시).
  - default timeout=60 / max_retries=3 = forecaster.agent.py:_call_azure_llm 패턴 차용.
- **설계 의도**:
  - 환경 변수 injection 의도 (`synthetic_daily_report.py:_build_reporter_config` 가 os.environ 에서 추출).
  - GraphConfig.reporter 필드에 박혀서 reporter_node 가 cfg.reporter 로 받음.
  - timeout/max_retries default — fail-fast / retry-3 패턴 (Azure 일시적 429 / timeout 회복).
- **대응 패턴**: dataclass 객체 — 단일 값 객체.
- **관련**:
  - 호출자: `synthetic_daily_report.py:_build_reporter_config` (env injection) + `tests/test_reporter.py:reporter_cfg` (fake creds fixture)
  - GraphConfig: `graph.py:33-40` (reporter 필드)

---

## 의도적 drift 메모 (spec §3 정합)

| 항목 | PM 원안 v2 | 본 cycle | 사유 |
|---|---|---|---|
| Reporter 위치 | Atomizer 다음 (Forecaster 와 병렬) | Optimizer 다음 (hil_2 conditional 분기 합류) | Forecaster + Optimizer 결과 모두 포함하는 종합 보고서로 — 1 LLM call 효율 |
| Reporter 출력 | 사내 + 발주처용 2 종 | 종합 1 종 | PoC 시연 단순화 |
| Reporter LLM | Sonnet 4.6 | Azure gpt-5.1-chat-ai-board-test | audit-report §3 (Azure 통일) |
| daily_reports schema | postgres.md §5 (date / summary) | 실 init.sql (report_date / history_csv_row + bp_name 추가) | drift #N3 — schema migration 별 cycle |

drift backlog 참조: `../../docs/audit/2026-05-17-cpia-drift-backlog.md` (#1 흡수, #N3 신규).

---

## 미해결 핵심 (다음 cycle)

- **drift #N3** schema migration — postgres.md §5 정정 또는 init.sql 정렬 (1 PR 묶음 가능, persistence 카드 + reporter 카드 양쪽 영향)
- **B_Track Dashboard** SELECT 연동 — daily_reports.history_csv_row 활용 (drift #5 와 통합 cycle)
- **공통 _call_azure_llm 추출** — forecaster + optimizer + reporter 의 timeout/max_retries 패턴 중복 (refactor 후보, low)
