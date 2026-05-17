# CPIA Drift Backlog (2026-05-17)

> Spec: `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md`
> Report: `docs/audit/2026-05-17-cpia-e2e-audit-report.md`
> 우선순위 산출 기준: 영향도 (high/med/low) × 의존성 × PoC 데모 시연 영향

---

## 우선순위 #1 — Reporter 구현

- **출처:** audit-report §1.6
- **영향도:** high (PoC 성공 기준 #1 직접 미충족)
- **원안 §:** `planning/CPIA_PoC_실행계획_v2.md` §4 Week 3 + §5 성공 기준 #1
- **의존성:** 없음 (단독 진입 가능, Mapper/Atomizer 산출물 활용)
- **권고 다음 cycle:** brainstorming → spec → plan
- **산출 추정:**
  - Azure gpt-5.1 호출 (Mapper 확정 JSON → 통합 Daily Report)
  - 사내 + 발주처용 2 종 보고서 또는 1 종 통합
  - PG `reports` 테이블 (또는 `data/output/reports/YYYYMMDD.md` — Persistence 의도된 변경 §3 에 맞춰 PG 권장)
  - Next.js Dashboard 연동 (B_Track 협업 필요)

---

## 우선순위 #2 — Forecaster assessment 결정 path 정정

§5.1 + §5.3 + §5.5 통합. assessment "정상" highly stable bias 가 Optimizer 약한 권고로 전파되는 핵심 사슬.

- **출처:** audit-report §5.1, §5.3, §5.5
- **영향도:** high (시뮬 결과 다양성 0, PM 원안 강한 권고 미발현)
- **원안 §:** §4 Week 3 Forecaster 출력 형식 + §5 성공 기준 #4
- **의존성:** 없음
- **권고 다음 cycle:** debugging (loop first — fixture 다양성 입력 vs assessment 출력 비교)
- **산출 추정:**
  - `pipeline/agents/forecaster/agent.py` 의 assessment 결정 path grep + traceback
  - 가설 A: LLM prompt 가 "정상" 선호 → prompt 수정
  - 가설 B: 결정론 코드 path 가 항상 "정상" → 임계값 정합
  - 가설 C: input 자체 (productivity_ratio 가 baseline 대비 항상 +) → §3 종속

---

## 우선순위 #3 — 시뮬 fixture productivity_ratio 산출 bug

- **출처:** audit-report §5.2
- **영향도:** high (Forecaster 정확도 검증 신뢰성, 본 audit raw 진위)
- **원안 §:** §3.B Synthetic (변동 패턴)
- **의존성:** 없음 (synthetic_daily_report 단독)
- **권고 다음 cycle:** debugging (실 호출 + 산술 trace)
- **산출 추정:**
  - `synthetic_daily_report.py:generate_fake_daily_report` 의 today_qty 계산 라인 검토
  - `_load_baseline_inputs` 의 baseline_qty 산출 (`Σplan_total_qty / days`) 정합 확인
  - 시뮬 1/2/3 의 today_prod (69.62 / 74.26 / 32.13) 가 baseline 31.07 와 어떻게 매핑되는지 산술 재현

---

## 우선순위 #4 — HIL 1 구현 (Mapper interrupt + corrections)

- **출처:** audit-report §1.4 (drift 1호, PoC 성공 기준 #2 직접 미충족)
- **영향도:** high
- **원안 §:** §4 Week 3 + §5 성공 기준 #2
- **의존성:** 없음 (state 자리 이미 있음 — `state.py:118 hil_1_corrections` + `state.py:133 waiting_hil_1`)
- **권고 다음 cycle:** brainstorming → spec → plan
- **산출 추정:**
  - `pipeline/graph.py` build_graph 에 hil_1_node 추가 (mapper → hil_1 → atomizer)
  - `pipeline/agents/mapper.py` 의 `requires_review=True` row 만 interrupt payload 박기
  - resume payload → corrections.json (또는 PG corrections 테이블 — §3 의도된 변경에 맞춰 PG 권장)
  - HIL 2 (이미 구현됨) 와 같은 InMemorySaver / Command(resume=) 패턴

---

## 우선순위 #5 — Collector + 파일 드롭 입력

- **출처:** audit-report §1.1 + §4 + §1 표 입력 데이터
- **영향도:** high (PoC 데모 첫 단계)
- **원안 §:** §4 Week 2 + §1 표
- **의존성:** Parser (이미 구현됨), main.py / api.py entry point 동시 필요
- **권고 다음 cycle:** brainstorming → spec → plan
- **산출 추정:**
  - `pipeline/agents/collector.py` (현 0 byte) — `openpyxl` 으로 .xlsx 시트 텍스트 추출 + .txt 직접 읽기
  - `data/input/YYYYMMDD/` 폴더 watcher 또는 CLI argument 진입
  - `pipeline/main.py` (현 0 byte) — `python -m pipeline.main --input data/input/2025-09-27/` 류 진입점
  - `pipeline/api.py` (현 0 byte) — FastAPI `/run` 엔드포인트 (Dashboard 연동 시)

---

## defer 항목 (별 cycle 우선 정해진 후 처리)

| # | 항목 | 출처 | 영향도 | defer 사유 |
|---|------|------|--------|-----------|
| D-1 | 병행작업 룰 (synthetic_v2 부재) | §2.7 | med | synthetic_v2 7 룰이 5 종 incident 만 다룸, 병행작업 추가는 별 cycle Optimizer 사례 확장 |
| D-2 | cold_start 2 path 통합 | §5.4 | med | 개념 정합성 영향, 시연 직접 영향 작음. #2 와 함께 처리 가능 |
| D-3 | PM 원안 §2 권고사항 vs LLM advice 의미 일치 정성화 | §5.6 | low | LLM 비결정성 + 의미 일부 일치, #2 해소 시 자연 개선 |
| D-4 | date off-by-one 잠재 (시뮬 3 stdout) | §5.7 | med | 재현율 1/4, 추가 시뮬 호출로 격리 가능 |
| D-5 | plan deviation 5건 자체 정정 | §5.8 | low | audit 가 self-correct, plan 사후 수정 X (Real research 룰 강화로 다음 plan 부터 예방) |
| D-6 | recovery_distribution conditions 필터 검증 | §5.9 | med | fetch_degradation_cases conditions 인자 적용 path grep, #2 와 함께 처리 가능 |
| D-7 | `pipeline/main.py` / `api.py` entry point | §1.6 의 footnote | med | #5 Collector 와 통합 cycle |
| D-8 | Parser 통합 테스트 (시뮬에서 우회되므로 실 호출 미검증) | §1.2 | low | Parser 코드 존재, 통합 테스트는 #1 또는 #5 cycle 함께 |

---

## 우선순위 요약

| 우선순위 | 이름 | 영향도 | PoC 성공 기준 | 의존성 |
|---------|------|--------|--------------|--------|
| #1 | Reporter 구현 | high | #1 ✓ | 없음 |
| #2 | Forecaster assessment 결정 path | high | #4 | 없음 |
| #3 | 시뮬 fixture productivity_ratio bug | high | (#4 신뢰성 직결) | 없음 |
| #4 | HIL 1 구현 | high | #2 ✓ | state 이미 있음 |
| #5 | Collector + 파일 드롭 + main.py | high | (전체 흐름) | Parser ✓ |
| defer | D-1 ~ D-8 (8 건) | med/low | — | — |

**다음 cycle 진입 권고:** #2 또는 #3 먼저 (현 audit 의 raw 신뢰성 향상 → 다른 cycle 진단 정확도 ↑). #1 Reporter 는 PoC 시연 단독 산출물이라 #2/#3 와 병렬 가능.

---

## 2026-05-17 hil1-forecaster-reporter cycle 흡수 + 신규 drift

### 흡수 완료 (PR pending — 본 cycle commit 5건 + raw 1)

| 우선순위 | 흡수 commit | 산출물 |
|---------|------------|--------|
| #1 Reporter 구현 | 22d44c2 feat(reporter) | pipeline/agents/reporter.py + reporter_node + graph edges + insert_daily_report + Reporter unit 3 + db 1 |
| #2 Forecaster assessment | (classify.py:34 수정 X — PM 원안 v2 정합) | spec §2.3 명시. root cause = input 의 #3 오버산출. #3 fix 로 자동 해결 |
| #3 시뮬 fixture bug | c093631 fix(synthetic_daily_report) | synthetic_daily_report.py:78 n_activities 분배 + :118 ValueError 가드 + fixture 재현/픽스/RAG 정합 3건 |
| #4 HIL 1 구현 | 1bb78fb feat(hil_1) | graph.py hil_1_node + _build_review_needed + _apply_corrections + insert_mapping_correction + HIL 1 unit 3 + e2e 2 |
| 추가 | 41908f6 feat(checkpointer) | InMemorySaver → AsyncPostgresSaver + memory fallback + checkpointer 3건 (design-intent O-6 권고) |
| 추가 | 86c3ad3 test (통합 검증) | docs/audit/raw/v2-scenario-1-156657ed.md raw (Forecaster fix 효과 + Reporter 영속 + 결정성 diff 0) |

**검증:** 회귀 baseline 183 → 197 passed + 1 xfailed in 412s. 본 cycle 7 성공 기준 모두 충족 (1 xfail = #N1).

### 신규 drift (본 cycle 발견)

| ID | 항목 | 출처 | 영향도 | 권고 처리 |
|----|------|------|--------|----------|
| #N1 | RAG fixture_prod vs synthetic_v2 분포 ±10% mismatch (delta=10.7%) | Task 1 Step 1.8 raw | med | 별 cycle — synthetic_v2 적재 분포 vs 90일 baseline 정렬. test_fixture_rag_alignment 가 xfail strict=False |
| #N2 | postgres.md §8 mapping_corrections schema 와 init.sql 어긋남 (work_content/company/trade/correction_type 컬럼 누락) | Task 2 Step 2.4 발견 | low | 별 cycle — schema migration. 현재 original/corrected JSONB 안에 합쳐 박음 (work_content GIN index 의도 충족 X) |
| #N3 | postgres.md §5 daily_reports schema 와 init.sql 어긋남 (date→report_date / summary→history_csv_row / bp_name 추가) | Task 3 Step 3.3 발견 | low | 별 cycle — postgres.md 정정 또는 init.sql 정렬. 현재 history_csv_row 컬럼 사용 |
| #N4 | 시뮬 2 (우천 0.8) + 시뮬 3 (돌관) + 시뮬 4 (cold_start) 추가 검증 | Task 5 Step 5.2 skip | low | 별 cycle — 본 cycle 의 시뮬 1 + rerun 으로 7 성공 기준 충족, 추가 path 검증은 시간/Azure 비용 trade-off |
| #N5 | LangGraph Command(resume=dict) 의 dict key 가 int 일 때 TypeError (is_xxh3_128_hexdigest re.fullmatch) | Task 2 Step 2.12 발견 | low | API 사용 룰 — str key 필수. hil_1_node 가 int(k) 변환 처리. 문서화 정도 충분 |
| #N6 | pipeline/.env.local 경로 spec 명시 어긋남 (실제 = root /.env.local) | Task 0 Step 0.2 발견 | low | spec/plan 의 경로 명시 정정 (cosmetic) |
| #N7 | synthetic_daily_report.py main_cli 의 final 출력에 report_md 미 print | Task 5 Step 5.4 plan 명시 | low | 가독성 개선 — 시뮬 결과 한눈에 확인. 본 cycle scope 외 |
