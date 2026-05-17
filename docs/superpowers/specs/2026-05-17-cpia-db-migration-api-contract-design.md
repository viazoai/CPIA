# CPIA DB Migration + API Contract — Design Spec

- **작성일**: 2026-05-17
- **저자**: A_Track (kyungseoplee)
- **상태**: draft (사용자 게이트 대기)
- **연관 PR (선행)**: #19 (HIL 1 + Forecaster fix + Reporter + PostgresSaver 통합 cycle, main 머지 완료)
- **연관 issue**: viazoai/CPIA#21 (homelab PG 비밀번호 sync 완료)
- **PoC 데모 마감**: 2026-06-05 (목) — 본 cycle 후 ~2.5주 여유

---

## §1. 목표 (한 줄)

본인이 A 로컬에서 작성/검증한 pipeline 산출 (init.sql + PR #19 schema/코드 + 더미 시드) 을 **homelab prod PG/Chroma 에 단방향 반영**해서, prod 에서 시뮬 1건 end-to-end 호출이 작동하는 상태로 만든다. 동시에 B_Track (조형준 web/) 가 prod 에서 데이터를 가져갈 수 있도록 PG↔types.ts 매핑과 endpoint 8건을 `docs/architecture/api-contract.md` 에 spec 으로 박는다. **FastAPI 구현 자체는 다음 cycle**.

---

## §2. 의도된 변경 (9 산출)

| # | 산출 | 변경 종류 |
|---|---|---|
| 1 | `infra/postgres/init.sql` | 갱신 — sites +4 컬럼 통합 (재 init 시 final schema 1회 적용) |
| 2 | `infra/postgres/migrations/2026-05-17_db_alignment.sql` | 신규 — sites +4 컬럼 멱등 ALTER (운영 중 PG 에 sequence apply 용) |
| 3 | `docs/schema/postgres.md` | 정정 — mapping_corrections / daily_reports / sites 실 schema 정합 (drift #N2, #N3 흡수) |
| 4 | `docs/architecture/api-contract.md` | 신규 (0 → ~500 lines) — PG↔types.ts 매핑 + 8 endpoint 명세 + sample JSON + 환경 분리 정책 |
| 5 | prod schema sync 실행 | 4 기존 migrations + 본 cycle 1 = 5 sql sequence apply 또는 prod docker volume 재생성 |
| 6 | prod `activity_master` + Chroma `wbs_master` 적재 | `scripts/load_master_list.py --filter-companies 남웅건설 세보엠이씨 창원기전` POSTGRES_URL/CHROMA_HOST = prod 로 1회 호출 (PG activity_master 1059 row + Chroma wbs_master 30 groups, A_LOCAL 실측 기준) |
| 7 | prod Chroma `synthetic_v2` 적재 | `python -m pipeline.agents.optimizer.synthetic_v2 --reference-date 2025-09-25 --days 90 --seed 42` (POSTGRES_URL+CHROMA_HOST=prod). Chroma `daily_activities` collection 에 worker_source="synthetic_v2" 90일 더미 적재 |
| 8 | prod `sites` 6 mock seed | fixture `data/mock_sites.json` 의 6 Site → `scripts/seed_sites.sql` INSERT (5 mock + 1 real M15X PoC). fixture 와 1:1 정합 (id/name/location/status/headcount/hours_saved/fte_saved 전사) |
| 9 | prod 시뮬 1건 end-to-end 검증 | A 머신에서 .env=prod swap 후 `python -m pipeline.agents.optimizer.synthetic_daily_report --site-id m15x-ph3-ibl --date 2025-09-25` → 7 agent 통과 + PG/Chroma row 생성 확인. HIL 1 우회 (synthetic_daily_report 의 mapped 가 `requires_review=False` 고정, synthetic_daily_report.py:97), HIL 2 는 script 가 명시 auto-resume |

---

## §3. 의도된 비변경 (drift — 본 cycle 명시 제외)

| # | 항목 | 사유 |
|---|---|---|
| D-1 | `mapping_corrections` schema 변경 (work_content / company / trade / correction_type top-level + GIN index) | YAGNI — 본 cycle 의 API 계약 8 endpoint 어디에도 `mapping_corrections SELECT` 없음. postgres.md §11 ② 의 Mapper 자가학습 기능 (= 실 호출 path 0) 은 별 cycle 의 의도된 묶음. 그 cycle 때 schema migration + 백필 + INSERT 변경 + SELECT 신규 + 로직 + 테스트 한 PR 로. (검증: `grep -rn mapping_corrections pipeline/ web/ --include="*.py" --include="*.ts" --include="*.tsx" | grep -v INSERT` = 0 hit, `grep -rn to_tsvector` = 0 hit) |
| D-2 | `daily_reports` 의 `history_csv_row` → `summary` RENAME | 사용자 결정 = `history_csv_row` 컬럼명 유지 (CSV 누적 의도 의미 있음), spec 만 정정. reporter.py docstring 의 `summary` 변수명은 컬럼명과 별도 (history_csv_row 컬럼에 박힌 summary dict). |
| D-3 | atomizer 적재 방식 변경 (PG 신규 atomized_activities 테이블) | 사용자 결정 = 현 상태 유지 (Chroma daily_activities 가 결정성 hash doc_id 로 영속, PG 는 atomized_count 카운트만). |
| D-4 | FastAPI `pipeline/api.py` 구현 | 다음 cycle. 본 cycle 은 `docs/architecture/api-contract.md` 계약 spec 만. (drift backlog D-7) |
| D-5 | `web/lib/fixtures.ts` → 실 API swap | FastAPI 구현 cycle 의 점진 swap. 본 cycle 동안 web/ 은 fixture 모드 계속. |
| D-6 | 시뮬 run 결과 (pipeline_runs / forecasts / optimizer_advice / daily_reports / Chroma daily_activities) 이관 | 휘발성 데이터. prod 시뮬 새 호출 (본 cycle 9 단계) 으로 자동 재생성. |
| D-7 | Mapper 자가학습 기능 (corrections 검색 → 자동 적용) | 별 의도된 cycle. D-1 schema 와 한 묶음. |

---

## §4. 현 schema 상태 (A_LOCAL vs PROD 실측)

본 cycle 검증 일시: 2026-05-17 16:30 KST. tunnel = `cloudflared access tcp --hostname cpia-pg.zoai.uk --url localhost:5532`.

| 테이블 | A_LOCAL | PROD | 격차 |
|---|---|---|---|
| `sites` | 8 cols | 8 cols | ✓ same |
| `mapping_corrections` | 6 cols | 6 cols | ✓ same |
| `daily_reports` | 7 cols | 7 cols | ✓ same |
| `pipeline_runs` | 9 (atomized_count 있음) | 8 (없음) | ⚠️ `2026-05-16_downstream_agents.sql` 미적용 |
| `activity_master` | 22 (wa 있음) | 21 (없음) | ⚠️ `20260516_add_activity_master.sql` 의 wa 컬럼 추가 미적용 (또는 활성 컬럼 차이) |
| `forecasts` | 29 cols | **9 cols** | ⚠️ `2026-05-16_downstream_agents.sql` + `2026-05-16_forecaster.sql` + `2026-05-16_optimizer_hil2.sql` 모두 미적용 (큰 격차) |
| `optimizer_advice` | 11 cols | **7 cols** | ⚠️ `2026-05-16_downstream_agents.sql` + `2026-05-16_optimizer_hil2.sql` 미적용 |

**해석** — prod docker volume 첫 init = 2026-05-14 시점의 `init.sql` 만 적용. 그 후 A 가 commit 한 4 migration sql 은 prod 에 한 번도 apply 안 됨. 이유 = docker postgres entrypoint 가 `/docker-entrypoint-initdb.d/*.sql` 만 알파벳 순 실행. `migrations/` 디렉토리 안의 sql 은 재귀 처리 X.

**prod = empty (모든 테이블 0 rows)** → schema 갱신이 안전 (데이터 손실 0).

---

## §5. Schema 변경 상세 — sites +4 컬럼

### 5.1 변경 사유

`web/lib/types.ts` 의 `Site` interface (19 필드) 와 실 `sites` 테이블 (8 cols) 간 gap:

- **Derived 8개** (gap_percent / spi / total_hours / ai_replacement_rate / productivity_today / abnormal_trades / delay_days / expected_completion) = API layer 계산 (sites + forecasts/optimizer_advice JOIN). 컬럼 추가 X.
- **Pipeline 산출 (집계)** (productivity_today / abnormal_trades / delay_days / expected_completion / recovered_completion / recovery_days) = forecasts LEFT JOIN.
- **진짜 새 데이터 4개** = `location`, `headcount`, `hours_saved`, `fte_saved` → sites 테이블에 컬럼 추가 필요.

### 5.2 마이그레이션 SQL

`infra/postgres/migrations/2026-05-17_db_alignment.sql`:

```sql
-- 2026-05-17 — sites +4 컬럼 (B_Track Dashboard Layer 1 카드)
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §5

BEGIN;
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS location    TEXT,
  ADD COLUMN IF NOT EXISTS headcount   INT,
  ADD COLUMN IF NOT EXISTS hours_saved NUMERIC,
  ADD COLUMN IF NOT EXISTS fte_saved   NUMERIC;
COMMIT;
```

멱등 (`IF NOT EXISTS`) — 두 번 돌려도 무방. 본 cycle 의 prod sync 또는 dev 회귀에서 둘 다 안전.

### 5.3 init.sql 갱신

`infra/postgres/init.sql` 의 `CREATE TABLE sites` 블록에 같은 4 컬럼 추가 (재 init 시 final schema 1회 적용 보장):

```sql
CREATE TABLE IF NOT EXISTS sites (
    site_id           TEXT         PRIMARY KEY,
    name              TEXT         NOT NULL,
    plan_progress     NUMERIC(5,2),
    actual_progress   NUMERIC(5,2),
    status            TEXT         CHECK (status IN ('normal','caution','risk','unknown')) DEFAULT 'unknown',
    last_run_id       UUID         REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,
    is_mock           BOOLEAN      NOT NULL DEFAULT TRUE,
    -- 2026-05-17: B_Track Dashboard Layer 1 카드 필드 (api-contract.md §3.1)
    location          TEXT,
    headcount         INT,
    hours_saved       NUMERIC,
    fte_saved         NUMERIC,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

---

## §6. prod schema sync 절차

prod 가 **2026-05-14 시점의 init.sql** 만 적용된 상태 → 5 sql 갱신 필요.

### 6.1 옵션 A — sequence apply (운영 중 PG 에 점진)

```bash
# A 머신에서 cloudflared tunnel 활성 상태로
TUNNEL=postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia

# 4 기존 migrations 순서대로
for f in \
  infra/postgres/migrations/2026-05-16_downstream_agents.sql \
  infra/postgres/migrations/2026-05-16_forecaster.sql \
  infra/postgres/migrations/2026-05-16_optimizer_hil2.sql \
  infra/postgres/migrations/20260516_add_activity_master.sql \
  infra/postgres/migrations/2026-05-17_db_alignment.sql; do
  echo "=== $f ==="
  psql "$TUNNEL" -f "$f"
done

# 검증
psql "$TUNNEL" -c "\dt+"
```

**주의** — `2026-05-16_downstream_agents.sql` 는 `DROP TABLE IF EXISTS forecasts` + recreate 패턴. prod 가 empty 라 안전 (데이터 손실 0).

### 6.2 옵션 B (권고) — docker volume 재생성

prod empty 가 확인된 시점이라 volume 통째 재 init 이 가장 깔끔:

```bash
# 조형준 측 prod 머신에서
cd /path/to/CPIA/infra
docker compose down -v          # postgres_data + chroma_data volume 통째 삭제
docker compose up -d            # init.sql (본 cycle 갱신 버전) 자동 적용
```

→ 단 1번에 final schema. migration sql 도 historical 보관 (재 init 시 무관). **이후 데이터 시드는 §7**.

**선택**: 옵션 B 권고. 옵션 A 는 prod 가 비어있지 않을 때 (다음부터) 만 사용.

### 6.3 검증

```bash
# A 머신에서 prod schema dump → A_LOCAL 와 diff
pipeline/.venv/bin/python3 scripts/dump_schema_diff.py  # 신규 또는 ad-hoc psql
# 기대: 모든 7 테이블 컬럼 = A_LOCAL 와 100% 일치
```

---

## §7. 데이터 시드 절차

prod schema sync 후 4 시드 (Master List + Chroma wbs_master + Chroma synthetic_v2 + sites 5 mock).

### 7.1 activity_master + Chroma wbs_master

A_LOCAL 실측 (2026-05-17 17:00 KST, `--filter-companies 남웅건설 세보엠이씨 창원기전`):
- PG `activity_master` row = **1059** (UPSERT)
- Chroma `wbs_master` group = **30** ((WA, L6) 그룹 단위 임베딩)

```bash
# .env.prod 또는 inline env override
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
PYTHONPATH="$(pwd)" \
  uv run --project pipeline scripts/load_master_list.py \
  --filter-companies 남웅건설 세보엠이씨 창원기전

# 기대 출력 (A_LOCAL 실측 정합):
#   [load] 전체 (WA, L6) 그룹: 102
#   [load] filter 적용 후 그룹: 30
#   [load] 적재 row: 1059
#   [load] PG activity_master upsert: 1059 rows
#   [load] Chroma wbs_master upsert: 30 groups
```

### 7.2 Chroma synthetic_v2 (Forecaster RAG 더미)

entry point 실측 (`pipeline/agents/optimizer/synthetic_v2.py:360`):
- 모듈 = `pipeline.agents.optimizer.synthetic_v2` 의 `_main_cli`
- argparse 인자 (line 193): `--reference-date 2025-09-25` (기본), `--days 90` (기본), `--seed 42` (기본)
- 적재 대상: Chroma `daily_activities` collection 에 `metadata.worker_source="synthetic_v2"` 로 누적. (별 collection 아님 — daily_activities 와 공존, source 로 분리)

```bash
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
PYTHONPATH="$(pwd)" \
  pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_v2 \
  --reference-date 2025-09-25 --days 90 --seed 42

# 기대 출력 (synthetic_v2.py 의 print):
#   OK upserted N rows to Chroma daily_activities. worker_source="synthetic_v2".
# (N = 30 groups × 90일 ≈ 2700, 실측은 group skip 룰에 따라 변동)
```

### 7.3 sites 6 mock seed

fixture `data/mock_sites.json` 실측 (2026-05-17): **6 site** (5 mock + 1 real M15X PoC). 본 spec §2 #8 의 "5 mock" 표기는 fixture 6건 (5 mock + 1 real) 의 mock 부분만 의미. seed sql 은 6 row INSERT.

`scripts/seed_sites.sql` (신규):

```sql
-- 2026-05-17 — sites 6 mock seed (fixture data/mock_sites.json → PG)
-- 5 mock + 1 real (m15x-ph3-ibl PoC). is_mock 으로 구분.
-- fixture 와 1:1 정합 (id/name/location/status/plan_progress/actual_progress/headcount/hours_saved/fte_saved).

INSERT INTO sites (site_id, name, location, status, plan_progress, actual_progress, headcount, hours_saved, fte_saved, is_mock)
VALUES
  ('m15x-ph3-ibl',   'M15X Ph-3 IBL',   '청주', 'risk',    38.5, 34.2,  65, 221, 1.6, FALSE),
  ('y1-ph1-obl',     'Y-1 Ph-1 OBL',    '평택', 'normal',  62.1, 62.5, 130, 832, 5.9, TRUE),
  ('indiana-hac',    'Indiana Fab HAC', '미국', 'normal',  48.7, 48.6,  60, 353, 2.5, TRUE),
  ('pt3-extension',  'P&T 3 증축',       '이천', 'normal',  71.4, 72.6,  50, 255, 1.8, TRUE),
  ('m15x-obl-pt7',   'M15X OBL & PT7',  '청주', 'normal',  22.8, 22.5,  50, 246, 1.7, TRUE),
  ('y1-ph1-ibl',     'Y-1 Ph-1 IBL',    '평택', 'normal',  55.6, 55.8,  90, 248, 1.8, TRUE)
ON CONFLICT (site_id) DO UPDATE SET
  name = EXCLUDED.name,
  location = EXCLUDED.location,
  status = EXCLUDED.status,
  plan_progress = EXCLUDED.plan_progress,
  actual_progress = EXCLUDED.actual_progress,
  headcount = EXCLUDED.headcount,
  hours_saved = EXCLUDED.hours_saved,
  fte_saved = EXCLUDED.fte_saved,
  is_mock = EXCLUDED.is_mock,
  updated_at = NOW();
```

검증: `SELECT count(*) FROM sites` = 6, `SELECT site_id FROM sites WHERE is_mock = FALSE` = `m15x-ph3-ibl` 1행.

(추가 fixture 컬럼 — progress_planned 의 fixture 표기 `plan_progress` vs PG `plan_progress` 매핑 동일. fixture 의 derived 컬럼 — gap_percent / spi / productivity_today / abnormal_trades / total_hours / ai_replacement_rate / expected_completion / recovered_completion / delay_days / recovery_days — API layer 가 계산, sites 컬럼 아님. §8.3 derived 계산식 참조.)

### 7.4 의도된 비시드

- **Chroma daily_activities** = 시뮬 호출 (§9) 시 Atomizer 가 자동 적재 → 시드 불필요
- **PG pipeline_runs / forecasts / optimizer_advice / daily_reports / mapping_corrections** = 시뮬 호출 시 자동 INSERT
- **PG checkpoints / checkpoint_writes / checkpoint_blobs / checkpoint_migrations** = PostgresSaver 가 첫 ainvoke 시 자동 create + insert

---

## §8. API 계약 (`docs/architecture/api-contract.md`)

본 cycle 의 최대 산출 — B_Track 의 `web/lib/types.ts` 와 PG schema 간 매핑 + 8 endpoint 명세. **FastAPI 구현 자체는 다음 cycle**, 본 cycle 은 계약 spec.

### 8.1 PG↔types.ts 매핑 표 (요지)

| types.ts type | PG 소스 | 산출 로직 |
|---|---|---|
| `Site[]` | `sites` + `forecasts` LEFT JOIN | id=site_id, derived 계산 (gap_percent / spi / total_hours / ai_replacement_rate), 집계 (productivity_today=MAX(forecasts.today_productivity), abnormal_trades=COUNT(forecasts WHERE risk_level<>'정상'), expected_completion=MAX(forecasts.expected_completion), delay_days=MAX(forecasts.delay_days)) |
| `SitesSummary` | sites Σ + dashboard 집계 | total_hours_saved=Σhours_saved, total_fte_saved=Σfte_saved, today_count=COUNT(today's pipeline_runs), review_pending=COUNT(WHERE status='waiting_hil_1'), abnormal_count=COUNT(forecasts WHERE risk_level<>'정상') |
| `AgentStatus[]` | (정적 7개) | 코드 상수 — 7 agent 메타데이터 (이름, 모델, group) |
| `ReviewItem[]` | LangGraph checkpoint state.mapped (interrupt 시점) | mapped Activity 중 `requires_review=True` row → ReviewItem shape |
| `ReportDetail` | `daily_reports` + `forecasts` + `optimizer_advice` | kpi=history_csv_row 집계, s_curve=forecasts/optimizer_advice 기반, contractor_bars / trade_bars / quadrant = Pipeline 산출 |
| `OptimizerOutput[]` | `optimizer_advice` | diagnosis / recommendations / similar_cases (degradation_cases JSONB) |
| `WBSNode` (tree) | `activity_master` 그루핑 | (building, trade, work_package) 계층 |

### 8.2 Endpoint 8건

| Method | Path | 데이터 소스 | Response type |
|---|---|---|---|
| GET | `/api/sites` | sites + forecasts LEFT JOIN 집계 | `Site[]` |
| GET | `/api/sites/:site_id` | sites + forecasts + optimizer_advice 집계 | `Site & {forecasts, advice}` |
| GET | `/api/runs/:run_id` | pipeline_runs | `RunStatus` (신규 type — pipeline_runs row + 진행상태) |
| GET | `/api/runs/:run_id/report` | daily_reports | `{report_md, history_csv_row}` |
| GET | `/api/runs/:run_id/forecasts` | forecasts | `ForecastRow[]` (신규 type) |
| GET | `/api/runs/:run_id/optimizer` | optimizer_advice | `OptimizerOutput[]` |
| GET | `/api/runs/:run_id/review` | LangGraph checkpoint state.mapped | `ReviewItem[]` |
| POST | `/api/runs/:run_id/hil_1/resume` | LangGraph `Command(resume=)` | `{corrections: {idx: {wa, l6_main}}}` |

### 8.3 Derived 계산식 (API layer 가 채움)

```python
# /api/sites response 시 sites + forecasts 집계로 derived 채움
gap_percent          = actual_progress - plan_progress
spi                  = actual_progress / plan_progress if plan_progress > 0 else None
total_hours          = headcount * 140
ai_replacement_rate  = hours_saved / total_hours * 100 if total_hours > 0 else 0
productivity_today   = max(f.today_productivity for f in forecasts)
abnormal_trades      = sum(1 for f in forecasts if f.risk_level != '정상')
delay_days           = max(f.delay_days for f in forecasts)
expected_completion  = max(f.expected_completion for f in forecasts)
```

### 8.4 환경 분리 정책

| 환경 | 용도 | POSTGRES_URL | CHROMA_HOST |
|---|---|---|---|
| dev | 본인 개발 + 회귀 197 PASS + 빠른 iteration | `localhost:5432` (A 로컬 docker) | `localhost:8000` |
| prod | 데모 + 서비스 + B_Track fetch | `127.0.0.1:5532` (cloudflared access tcp tunnel) | `cpia-chroma.zoai.uk:443 SSL` |

**전환 방식** = `.env.local` 한 줄 swap 또는 inline env override (`POSTGRES_URL=... CHROMA_HOST=... uv run ...`). **코드 변경 0** — agents 가 GraphConfig (DI) 받고, config 가 환경변수 읽음.

dev 가 prod 가리키지 않는 사유:
- Azure 비용 매 회귀마다 (~$0.5/시뮬, 197 회귀 = $100+)
- Chroma upsert 가 prod 데이터 오염
- cloudflared tunnel latency 로 회귀 느림
- 동시 작업 충돌 (B_Track 도 같은 prod 봄)

---

## §9. prod 시뮬 1건 end-to-end 검증 (= Done 정의)

본 cycle 의 "Done" 정의 = prod 시뮬 1건이 7 agent 다 통과.

### 9.1 호출 명령

synthetic_daily_report.py 의 실측 argparse (line 366):
- `--site-id` (기본 `DEMO_SITE`) — 본 cycle 검증 시 `m15x-ph3-ibl` (real PoC) 명시
- `--site-name` (기본 `Demo Site`) — `'M15X Ph-3 IBL'` 명시
- `--date` — 필수 (시뮬 일자)
- 기타 scenario 인자는 plan 단계 grep 으로 확정

```bash
# A 머신에서 .env 일시 swap (.env.prod 활용 또는 inline override)
POSTGRES_URL="postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia" \
CHROMA_HOST=cpia-chroma.zoai.uk \
CHROMA_PORT=443 \
CHROMA_SSL=true \
CPIA_CHECKPOINTER=postgres \
PYTHONPATH="$(pwd)" \
  pipeline/.venv/bin/python3 -m pipeline.agents.optimizer.synthetic_daily_report \
  --site-id m15x-ph3-ibl \
  --site-name "M15X Ph-3 IBL" \
  --date 2025-09-25
```

### 9.2 기대 산출 (prod 측 row count delta)

`synthetic_daily_report` 의 HIL path:
- **HIL 1 우회** — synthetic_daily_report:97 에서 mapped activity 마다 `"requires_review": False` 고정. graph.py:124 의 `if not review_needed: return {"hil_1_corrections": {}, ...}` 분기로 자동 통과. mapping_corrections INSERT 0건.
- **HIL 2 명시 auto-resume** — script line 430 의 `if "__interrupt__" not in first: ... 종료` 검증 + line 445~ 의 `interrupts[0].value` 추출 후 자동 Command(resume=...) 호출. Optimizer → Reporter → END 자연 진행.

| 적재 | 기대 delta |
|---|---|
| PG `pipeline_runs` | +1 (status='completed') |
| PG `forecasts` | +N (N = 시뮬의 (company, l6_main) 그루핑 개수, fixture 47 row 기준 ~3-5건) |
| PG `optimizer_advice` | +M (M = forecasts 중 risk_level<>'정상' 개수, 0 ≤ M ≤ N) |
| PG `daily_reports` | +1 (Reporter 종합보고서, bp_name=NULL) |
| PG `mapping_corrections` | 0 (HIL 1 우회 path) |
| PG `checkpoints` / `checkpoint_writes` / `checkpoint_blobs` / `checkpoint_migrations` | 자동 create + insert (PostgresSaver 첫 호출, CPIA_CHECKPOINTER=postgres 필수) |
| Chroma `daily_activities` | +K (K = Atomizer 적재 doc 개수, fixture 47 row 의 unique 매핑 ~11-15건) |

### 9.3 검증 쿼리 (사람이 본인 확인)

```sql
-- prod 에 cloudflared tunnel 활성 후
psql postgresql://cpia:K7mP2xQ9nR4v@127.0.0.1:5532/cpia <<EOF
SELECT 'pipeline_runs'      AS t, count(*) FROM pipeline_runs
UNION ALL SELECT 'forecasts',        count(*) FROM forecasts
UNION ALL SELECT 'optimizer_advice', count(*) FROM optimizer_advice
UNION ALL SELECT 'daily_reports',    count(*) FROM daily_reports
UNION ALL SELECT 'checkpoints',      count(*) FROM checkpoints;
EOF
```

기대: 모든 count ≥ 1.

### 9.4 회귀 영향 (dev)

- pipeline 코드 변경 0 → 회귀 197 PASS + 1 xfailed 그대로 (dev 환경 그대로)
- sites seed sql 은 dev 에선 무관 (test 가 sites SELECT 안 함)
- 새 migration sql `2026-05-17_db_alignment.sql` 멱등 → dev PG 에 적용해도 안전 (검증 권장)

---

## §10. 사전 필요 (사용자/조형준 측 조치)

| 상태 | 항목 | 본 spec 의 어느 단계 에 필요 |
|---|---|---|
| ✅ 완료 | prod PG tunnel (`cpia-pg.zoai.uk:5532`) — issue #21 sync 완료, cpia/K7mP2xQ9nR4v 통과 (본인 검증 2026-05-17 16:30) | §5, §6, §7, §9 모두 |
| ⚠️ 본 cycle Task 6/7/9 진입 전 (=Hard Gate) | **prod Chroma tunnel hostname 확정 + 활성** — `.env.example:19` 명시 `cpia-chroma.<your-domain>` 패턴 + PG 가 `cpia-pg.zoai.uk` (zoai.uk) 이므로 **추정 = `cpia-chroma.zoai.uk`** (TBD 조형준 확정). cloudflared HTTP 모드 (CHROMA_PORT=443 SSL) 권장. **조형준 확인 후 본 spec §7.1/§7.2/§9.1 의 hostname 값 마지막 검증 후 실 호출.** | §7.1, §7.2, §9.1 |
| ⚠️ 본 cycle Task 5 (옵션 B 채택 시) | **prod 머신에서 git pull (본 cycle commit 후) + docker compose down -v && up -d** — 조형준 측 실행. prod 가 본 cycle 의 갱신된 init.sql 을 git fetch 필요. **옵션 A fallback** (본인 cloudflared tunnel 통해 5 sql sequence psql) 은 prod 머신 git pull 무관, A 측만으로 가능 — 옵션 B 가 조형준 측 응답 지연 시 fallback. | §6 (Task 5) |

---

## §11. Task 순서 (plan 도식)

```
Task 0  환경 점검 + 회귀 baseline (dev)
        ├ pipeline/.venv/bin/python3 -m pytest pipeline/ → 197 passed + 1 xfailed 재확인
        ├ A_LOCAL ↔ PROD schema diff dump 재확인 (2026-05-17 16:30 본인 검증 완료, plan 시점 재확인 권장)
        └ cloudflared tunnel 활성 확인 (PG cpia-pg.zoai.uk:5532 + Chroma cpia-chroma.zoai.uk Hard Gate)

Task 1  init.sql 갱신 + migration sql 신규
        ├ infra/postgres/init.sql 의 sites 블록 +4 컬럼
        ├ infra/postgres/migrations/2026-05-17_db_alignment.sql 신규 (멱등 ALTER)
        ├ dev 회귀 — sites 4 컬럼 추가 후 197 PASS 유지 확인
        └ commit: feat(schema): sites +4 컬럼 (location/headcount/hours_saved/fte_saved)

Task 2  docs/schema/postgres.md 정정 (drift #N2 + #N3 흡수)
        ├ mapping_corrections §8 = 실 init.sql 정합 (4 컬럼만, drift D-1 미래 의도 별 섹션 명시)
        ├ daily_reports §5 = report_date/history_csv_row/bp_name 정합 (summary → history_csv_row)
        ├ sites §1 = 12 cols (8 + 4 신규) 반영
        └ commit: docs(schema): postgres.md 실 init.sql 정합 정정 (drift #N2+#N3 흡수)

Task 3  docs/architecture/api-contract.md 신규
        ├ §1 환경 분리 정책 (dev/prod)
        ├ §2 PG↔types.ts 매핑 표 (4 type: Site, ReviewItem, ReportDetail, OptimizerOutput)
        ├ §3 endpoint 8건 명세 (path, method, query params, response shape, sample JSON)
        ├ §4 derived 계산식 (gap_percent / spi / total_hours / ai_replacement_rate / 집계)
        └ commit: docs(architecture): api-contract.md 신규 (PG↔types.ts + 8 endpoint)

Task 4  scripts/seed_sites.sql 신규
        ├ data/mock_sites.json 6건 (실측, 5 mock + 1 real) → INSERT ... ON CONFLICT DO UPDATE
        ├ dev 적용 + SELECT 검증 (count=6, is_mock=FALSE 1행=m15x-ph3-ibl)
        └ commit: feat(seed): sites 6 seed (5 mock + 1 real, data/mock_sites.json 정합)

Task 5  prod schema sync (의존: Task 1 commit. 옵션 B 추가 의존: 조형준 측 git pull + docker)
        ├ 옵션 B 권고: prod 머신에서 git pull A_Track (또는 본 cycle branch) + docker compose down -v && up -d (조형준 실행)
        │   → 본 cycle init.sql 1회 적용, 5 sql sequence 생략
        ├ 옵션 A fallback: A 머신에서 cloudflared tunnel 통해 5 sql sequence psql 호출 (§6.1)
        │   → prod 머신 git pull 불필요. 조형준 측 응답 지연 시 또는 A 단독 진행 시
        ├ 옵션 A 의 4 기존 migrations 는 git A_Track 의 infra/postgres/migrations/ 그대로
        ├ 검증: A_LOCAL ↔ PROD schema diff = 0 격차 (각 테이블 컬럼 수/이름/타입 동일)
        └ (코드 commit 없음 — prod 머신 작업, 옵션 B 또는 본인 tunnel)

Task 6  prod activity_master + Chroma wbs_master 적재
        ├ scripts/load_master_list.py --filter-companies 남웅건설 세보엠이씨 창원기전 (POSTGRES_URL/CHROMA_HOST=prod)
        ├ 검증: PROD activity_master row=1059 + Chroma wbs_master group=30 (A_LOCAL 실측 정합)
        └ (코드 commit 없음 — 데이터 적재만)

Task 7  prod Chroma synthetic_v2 적재
        ├ build script 호출 (CHROMA_HOST=prod)
        ├ 검증: PROD Chroma synthetic_v2 doc count > 0
        └ (코드 commit 없음 — 데이터 적재만)

Task 8  prod sites 6 seed (5 mock + 1 real)
        ├ psql 로 scripts/seed_sites.sql 실행 (POSTGRES_URL=prod)
        ├ 검증: PROD sites row=6, is_mock=FALSE 1행=m15x-ph3-ibl
        └ (코드 commit 없음 — 데이터 적재만)

Task 9  prod 시뮬 1건 end-to-end 검증 (= Done)
        ├ python -m pipeline.agents.optimizer.synthetic_daily_report --site-id m15x-ph3-ibl --site-name "M15X Ph-3 IBL" --date 2025-09-25 (POSTGRES_URL/CHROMA_HOST=prod, CPIA_CHECKPOINTER=postgres)
        ├ 검증: PROD pipeline_runs/forecasts/optimizer_advice/daily_reports/checkpoints 각 row ≥ 1, mapping_corrections=0 (HIL 1 우회)
        ├ Azure 비용 ~$0.1 (시뮬 1건)
        └ commit: chore(verify): prod 시뮬 1건 end-to-end 통과 (raw 검증 결과 docs/audit/raw/)

Task 10 PR 작성
        ├ 본 cycle 의 commit 5건 (Task 1~4 + Task 9 raw) 묶음
        ├ PR body: scope (9 산출) + drift (7 D-* 항목) + 성공 기준 + 검증 raw
        └ PR # → 조형준 리뷰 → main 머지 (본인 권한 X)
```

---

## §12. 비용 / 리스크

| 항목 | 추정 |
|---|---|
| Azure 비용 (시뮬 1건) | ~$0.1 (Mapper + Forecaster reasoning + Optimizer + Reporter LLM) |
| 시뮬 호출 시간 | ~3분 (PoC fixture 47 row) |
| 회귀 영향 (dev) | 197 PASS + 1 xfailed 유지 (코드 변경 0, sql 변경 만) |
| prod 망쳤을 때 복구 | docker compose down -v && up -d (prod empty 라 데이터 손실 0) |
| cloudflared tunnel 끊김 | 시뮬 호출 timeout (Azure 호출은 직접, tunnel 영향 X — PG/Chroma 호출만 영향) |

---

## §13. 회귀 영향

- **pipeline 코드 변경 0** → 회귀 197 PASS + 1 xfailed 그대로
- **sql 변경** = `2026-05-17_db_alignment.sql` 신규 + `init.sql` 의 sites 블록 갱신. dev PG 에 적용 → sites 컬럼 추가만, 기존 test 가 sites SELECT 안 함 (검증 권장)
- **새 테스트 추가 0** (본 cycle 은 schema + spec + 데이터 시드)

---

## §14. 다음 cycle 권고 (본 cycle 후)

| 우선순위 | cycle | scope |
|---|---|---|
| #1 | **FastAPI 구현** | `pipeline/api.py` 신규 (0 → ~400 lines) — api-contract.md 의 8 endpoint 구현. uvicorn 띄움. dev/prod 환경변수 분기. web/ 가 fetch 가능. drift D-7 흡수. |
| #2 | web/ fixture → 실 API swap (점진) | web/app/api/mock/* route → fetch FastAPI. 8 endpoint 별 1개씩 PR. drift D-5 흡수. |
| #3 | Mapper 자가학습 기능 | mapping_corrections schema 변경 (work_content/company/trade/correction_type top-level + GIN) + 백필 + INSERT 변경 + SELECT 신규 (fetch_similar_corrections) + Mapper 로직 + 테스트. drift D-1 + D-7 흡수. |
| #4 | RAG 정합 (synthetic_v2 적재 분포 정렬) | drift #N1 (xfail test_fixture_rag_alignment) — Forecaster RAG ≥3 보장 후 시뮬 3 "정상" 분류 오류 해소 |

---

## §15. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-17 | 초안 — brainstorming 결정 (B 안 + 데이터 시드 + 환경 분리) | A_Track (kyungseoplee) |
