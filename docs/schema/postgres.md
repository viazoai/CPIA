# PostgreSQL 스키마 — `infra/postgres/init.sql`

> **Phase 0 합의 산출물.** 이 문서가 정의하는 8 테이블은 파이프라인 영속화 + Dashboard 데이터 소스의 계약. 변경 시 A·B 트랙 둘 다 OK 사인 필요.
>
> 작성: 2026-05-14 (A 트랙 초안) · 기반: `docs/schema/state.md`, 협업 spec `docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md` §3-2
>
> **DB**: PostgreSQL 16+ (homelab Docker). LangGraph PostgresSaver 가 `checkpoints` / `checkpoint_writes` 자동 생성하므로 그 스키마는 손대지 않음.

---

## 0. 테이블 한눈에 보기

| # | 테이블 | 쓰기 주체 | 읽기 주체 | 핵심 역할 |
|---|---|---|---|---|
| 1 | `sites` | 수동 seed | Dashboard | 6 현장 메타 (5 mock + 1 실 PoC) |
| 2 | `activity_master` | `scripts/load_master_list.py` | Mapper, Forecaster | Master List 적재 (Plan 기준값) — **신규 (협업 spec 기준 +1 테이블)** |
| 3 | `pipeline_runs` | FastAPI `/run` | Dashboard, `/status` | run_id 생성 + 상태 추적 |
| 4 | `checkpoints` | LangGraph PostgresSaver (auto) | LangGraph 내부 | interrupt/resume 시 state snapshot |
| 5 | `daily_reports` | Reporter | Dashboard Layer 2 | 통합 일일 보고서 markdown |
| 6 | `forecasts` | Forecaster | Dashboard Layer 2, Optimizer | 공종별 진단 (Plan + RAG 이중 비교 결과) |
| 7 | `optimizer_advice` | Optimizer | Dashboard Layer 2 | PM 선택 공종에 대한 조언 |
| 8 | `mapping_corrections` | H-i-L 1 resume | Mapper (다음 run 의 feedback) | 매핑 보정 누적 |

협업 spec 의 7 테이블 + **`activity_master` 1개 추가**. 추가 근거: Mapper 가 Chroma `wbs_master` 검색 후 메타데이터 (plan_total_qty, plan_mh, plan_start/finish) 가 필요한데 Chroma metadata 만으로 부족 (날짜 비교 / 페어 lookup / 인덱스 활용). PG 에 정규화 적재해 SQL JOIN 가능하게.

---

## 1. `sites` — 현장 메타

```sql
CREATE TABLE sites (
    site_id          TEXT PRIMARY KEY,         -- 'M15X_PH3_IBL'
    name             TEXT NOT NULL,            -- 'M15X Ph-3 IBL'
    plan_progress    NUMERIC,                  -- 계획 공정률 (Dashboard Layer 1)
    actual_progress  NUMERIC,                  -- 실적 공정률
    last_run_id      UUID,                     -- 최근 pipeline run
    status           TEXT,                     -- 'normal' / 'attention' / 'risk'
    is_mock          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- PoC 시연용: 5 mock site (Dashboard Layer 1 카드용) + 1 real site (`M15X_PH3_IBL`).
- `last_run_id` 는 forward reference. FK 안 거는 이유: 첫 run 전에는 NULL.

---

## 2. `activity_master` — Master List 적재 (신규)

```sql
CREATE TABLE activity_master (
    wbs_activity_id   TEXT PRIMARY KEY,        -- 'TNMCB1F6501A03030034'

    -- 계층 라벨 (Master List col 14~22)
    l5_disc           TEXT NOT NULL,           -- '건축' / '설비' / ...
    l6_main           TEXT,                    -- '철근콘크리트공사'
    l6_code           TEXT,                    -- '03'
    l7_sub            TEXT,                    -- '거푸집공사'
    l7_code           TEXT,                    -- '030'
    l7_5_activity     TEXT,                    -- '기초공사 : 거푸집 공사'
    sub_work_area     TEXT,                    -- 'B1F 연결공동구 FAB-WWT'

    -- 업체·단위
    company           TEXT,                    -- '남웅건설'
    unit              TEXT,                    -- 'M2' / 'Ton' / 'M3'

    -- Plan 값 (Rev.2 채택 + 이력)
    plan_total_qty    NUMERIC,                 -- 500.0
    plan_mh_rev2      NUMERIC,                 -- 456.0  (분배 + 진단 사용)
    plan_mh_rev1      NUMERIC,
    plan_mh_rev0      NUMERIC,
    plan_wv           NUMERIC,                 -- = plan_mh_rev2 * 4.9 (참고용)

    -- 일정 (Rev.2)
    plan_start        DATE,
    plan_finish       DATE,

    -- 실적 (Master List 자체 컬럼, 작업일보와는 별개)
    actual_start      DATE,
    actual_finish     DATE,

    -- 적재 메타
    source_file       TEXT,                    -- 'WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx'
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_actmaster_lookup ON activity_master (l5_disc, company, unit);
CREATE INDEX idx_actmaster_period ON activity_master (plan_start, plan_finish);
```

### 적재 흐름

```
WBS공정표_*.xlsx (Master List 시트)
       ↓ scripts/load_master_list.py --filter "l5_disc=건축,company=남웅건설"
PG activity_master  (189 row, PoC 범위)
       ↓ 같은 데이터 임베딩
Chroma wbs_master  (189 record)
```

- 1회 적재. 추후 공정표 갱신 시 `--upsert` 옵션으로 incremental.
- PoC 범위 확장 시 filter 만 풀면 됨.

### Mapper 가 사용하는 쿼리 예

```sql
-- 일자 필터 + 메타 매칭으로 후보 좁힘 (Chroma 검색 전후처리에 활용)
SELECT wbs_activity_id, l7_sub, l7_5_activity, plan_total_qty, plan_mh_rev2
FROM activity_master
WHERE company = '남웅건설'
  AND l5_disc = '건축'
  AND unit    = 'M2'
  AND plan_start <= '2026-06-01'
  AND plan_finish >= '2026-06-01' - INTERVAL '7 days';
```

---

## 3. `pipeline_runs` — run 단위 추적

```sql
CREATE TABLE pipeline_runs (
    run_id           UUID PRIMARY KEY,
    site_id          TEXT NOT NULL REFERENCES sites(site_id),
    date             DATE NOT NULL,            -- 작업일보 일자
    status           TEXT NOT NULL,            -- state.py CPIAState.status 와 동일
    current_node     TEXT,                     -- 'collector' / 'parser' / ...
    atomized_count   INTEGER DEFAULT 0,        -- Atomizer 가 Chroma 적재한 row 수 (downstream-agents §8.1)
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    error_message    TEXT,
    input_files      JSONB                     -- list[str] of file paths
);

CREATE INDEX idx_runs_site_date ON pipeline_runs (site_id, date);
CREATE INDEX idx_runs_status    ON pipeline_runs (status) WHERE status NOT IN ('completed','failed');
```

- FastAPI `/run` 진입 시 INSERT, 노드 진행마다 UPDATE.
- `/status/{run_id}` 가 이 테이블을 SELECT.

---

## 4. `checkpoints` (+ `checkpoint_writes`)

LangGraph 의 `PostgresSaver` 가 자동 생성·관리. 손대지 않음. 참고: <https://langchain-ai.github.io/langgraph/reference/checkpoints/>

```sql
-- LangGraph 가 생성하는 스키마 (참고용, 직접 정의하지 않음)
-- checkpoints        (thread_id, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata, ...)
-- checkpoint_writes  (thread_id, checkpoint_id, task_id, idx, channel, type, value, ...)
```

- `thread_id` = `pipeline_runs.run_id` 와 동일하게 셋업 (FastAPI 가 LangGraph 호출 시 `config={"configurable": {"thread_id": run_id}}`).

---

## 5. `daily_reports` — Reporter 출력

```sql
CREATE TABLE daily_reports (
    id               BIGSERIAL PRIMARY KEY,
    run_id           UUID NOT NULL REFERENCES pipeline_runs(run_id),
    date             DATE NOT NULL,
    report_md        TEXT NOT NULL,            -- 마크다운 본문
    summary          JSONB,                    -- {total_workers, total_qty_by_trade, ...}
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_run ON daily_reports (run_id);
```

---

## 6. `forecasts` — (company, l6_main) grain 진단

```sql
CREATE TABLE forecasts (
    id                       BIGSERIAL PRIMARY KEY,
    run_id                   UUID NOT NULL REFERENCES pipeline_runs(run_id),
    company                  TEXT NOT NULL,             -- '남웅건설'
    l6_main                  TEXT NOT NULL,             -- '철근콘크리트공사' (Master List l6_main)

    -- 오늘 실측 (단위가 섞이므로 JSONB by_unit)
    today_qty_by_unit        JSONB,                     -- {"M2": 120.0, "Ton": 3.4}
    today_assigned_workers   NUMERIC,                   -- MH 분배 결과

    -- Plan 기준 (단위 혼합 → JSONB, MH 는 합산)
    plan_total_qty_by_unit   JSONB,                     -- {"M2": 500.0, "Ton": 12.0}
    plan_mh_sum              NUMERIC,                   -- = SUM(plan_mh_rev2)

    -- RAG 이력 기준
    rag_n_similar            INT,                       -- 0~5 (cold start 시 0~2)
    similar_cases            JSONB,                     -- [{date, productivity, conditions, ...}, ...]

    -- LLM 진단
    assessment               TEXT,                      -- '정상' / '주의' / '이상'
    reasoning                TEXT,
    expected_completion      DATE,
    delay_days               INT,
    risk_level               TEXT,                      -- '정상' / '주의' / '이상'

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_forecasts_run         ON forecasts (run_id);
CREATE INDEX idx_forecasts_company_l6  ON forecasts (company, l6_main);
CREATE INDEX idx_forecasts_risk        ON forecasts (risk_level) WHERE risk_level <> '정상';
```

- Grain: `(run_id, company, l6_main)` — downstream-agents spec §8.2 결정. l7_sub 가 아닌 l6_main 으로 올린 이유는 작업일보가 l6 수준에서 보고되기 때문.
- 단위가 섞이면 (M2/Ton/M3) `today_qty_by_unit` / `plan_total_qty_by_unit` JSONB 로 분리 보관.
- `similar_cases` JSONB 에 RAG 검색된 5건의 메타 + 짧은 work_content 보존 → Optimizer 도 재사용.

---

## 7. `optimizer_advice` — H-i-L 2 이후 조언

```sql
CREATE TABLE optimizer_advice (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL REFERENCES pipeline_runs(run_id),
    l6_main             TEXT NOT NULL,                 -- (downstream-agents §8.3 rename: trade → l6_main)
    company             TEXT NOT NULL,
    diagnosis           TEXT,                          -- '장비 대기로 인한 저하 추정'
    recovery_pattern    JSONB,                         -- [{case_date, recovered_in_days, pattern}, ...]
    recommendations     JSONB,                         -- [{rank, text}, ...]
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_optimizer_run ON optimizer_advice (run_id);
```

---

## 8. `mapping_corrections` — H-i-L 1 누적

```sql
CREATE TABLE mapping_corrections (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES pipeline_runs(run_id),
    date            DATE NOT NULL,
    work_content    TEXT NOT NULL,                     -- 원천 텍스트 (Parser 출력)
    company         TEXT,
    trade           TEXT,                              -- l5_disc

    original        JSONB NOT NULL,                    -- {wbs_activity_id, confidence, ...} (Mapper 가 추천)
    corrected       JSONB NOT NULL,                    -- {wbs_activity_id, ...} (사용자 정정)
    correction_type TEXT,                              -- 'replace' / 'split' / 'reject'

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_corr_workcontent ON mapping_corrections USING GIN (to_tsvector('simple', work_content));
CREATE INDEX idx_corr_run         ON mapping_corrections (run_id);
```

- Mapper 가 다음 run 진입 시 동일 `work_content` 패턴 검색 → corrections 우선 적용. 시간 지나면서 Mapper 정확도 자가 학습.

---

## 9. ERD (텍스트)

```
sites ────────────────────────┐
   │                          │
   ▼                          │
pipeline_runs ────────────────┼─────────────┐
   │                          │             │
   ├──► daily_reports          │             │
   ├──► forecasts              │             │
   ├──► optimizer_advice       │             │
   ├──► mapping_corrections    │             │
   └──► checkpoints (LangGraph 자동)         │
                                             │
activity_master  ◄── Mapper 가 SELECT / Forecaster 가 plan 값 조회
   ▲
   └── scripts/load_master_list.py  (1회 적재 + Chroma 임베딩 동시)
```

- `pipeline_runs` 가 허브. 모든 결과 테이블이 `run_id` FK.
- `activity_master` 는 standalone (run 과 무관, 1회 적재 후 read-only).

---

## 10. 초기 적재 / 마이그레이션

| 시점 | 작업 | 파일 |
|---|---|---|
| Phase 0 (5/14~16) | `infra/postgres/init.sql` 작성 (위 8 테이블 + LangGraph 자동 생성 영역 제외) | B 트랙 담당 |
| GATE 1 직전 (5/19) | `scripts/load_master_list.py --filter "l5_disc=건축,company=남웅건설"` 실행 → `activity_master` 189 행 + `sites` 1 row seed | A 트랙 담당 |
| 이후 스키마 변경 | `infra/postgres/migrations/YYYYMMDD_*.sql` 추가, 직접 `ALTER` 금지 | 공동 |

---

## 11. 미해결 사안 (구현 시 결정)

| # | 사안 | 가설 |
|---|---|---|
| ① | `forecasts.similar_cases` JSONB 크기 | 5건 × 짧은 work_content (200자 한도) ≈ 1~2 KB. 무난 |
| ② | `mapping_corrections` 누적 시 정책 | 동일 `(work_content, company, trade)` 가 K 번 이상 동일 정정이면 Mapper 가 자동 적용 (현재는 LLM 컨텍스트에 주입). K 결정은 GATE 3 |
| ③ | `pipeline_runs.input_files` JSONB vs 별도 테이블 | PoC 는 JSONB. 다중 입력 파일이 표준이 되면 별도 테이블 분리 |
| ④ | `activity_master` 의 Master List 갱신 | Master List xlsx 가 매주 갱신될 가능성. `--upsert` 시 plan_mh 변경 추적은 Phase 2 |

---

## 12. 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-14 | 초안 — brainstorming 결과 통합 (활성 8 테이블 = 협업 spec 7 + `activity_master` 1, `forecasts` 에 Plan/RAG 이중 비교 컬럼 분리, PoC 적재 범위 한정) | A 트랙 |
| 2026-05-16 | downstream-agents spec §8 적용 — forecasts (company, l6_main) grain 정정 + pipeline_runs.atomized_count + optimizer_advice rename | A 트랙 |
