# Deep Dive — atomizer

- **Generated**: 2026-05-26 (cycle HEAD `1ba783f`, baseline `ef7c6cd` 대비 80+ commits 중 atomizer 직접 변경 3건 + 인접 PG migration 1건)
- **Range**: `pipeline/agents/atomizer.py` (196 LOC, 이전 141 → +55) + `pipeline/db.py` (insert_mapped_history_batch / assert_pipeline_run_exists / update_run_atomized_count / get_pipeline_run 4 메서드) + `pipeline/chroma_client.py` (get_or_create_daily_activities) + PG migrations `2026-05-18_mapped_history.sql` + `2026-05-19_mapped_history_trade.sql` + `pipeline/tests/test_atomizer*.py` (3 파일, 588 LOC, 15 케이스)
- **Pair**: `architecture_overview.md` §2 #5 (atomizer 카드) + `design-intent/design_intent_atomizer.md` (T1/T2 stale 라벨, 본 문서가 갱신)
- **Git context**: 본 cycle atomizer 직접 commit 3건:
  - `a3db32a` (2026-05-20) fix(pipeline): 78사 통합일보 1 cycle — atomizer.py 부분 = ChromaClient init 3 retry + upsert batch=100 split (HNSW hang 방어)
  - `9252ac7` (2026-05-21) feat(atomizer): documents 가독 형식 + metadata 풍부화 (C6, Task 12) — `_format_document` 신규 + `_build_metadata` 3 필드 추가
  - `b560dd4` (2026-05-22) perf(atomizer): batch_size default 16 → 64
  - 인접: `16f1b88` (data-contract G-2 검증) — `mapped_history.trade` 컬럼 신설, atomizer.py 코드 자체엔 trade 박힘 미시행 (이슈)

---

## 1. Overview

Atomizer 는 Mapper 가 산출한 `state["mapped"]` (list[Activity]) 1 일치 작업 row 들을 받아 **2 개의 영속 저장소** 에 동시 적재한다.

1. **ChromaDB `daily_activities`** — 1 mapped Activity = 1 Chroma doc.
   - `doc_id = sha256(date|company|l6_main|work_content)[:16]` (결정성 upsert).
   - `documents` = `_format_document` 가 사람이 읽을 수 있는 자연어 헤더 + 본문 (시공량 / 인원 / 조건) 으로 포맷한 텍스트 (work_content 단독 임베딩 폐지, 2026-05-21 변경).
   - `metadatas` = 15 필드 평탄화 dict (Phase 1: `l7_5_activity` / `perperson` / `productivity_pct` 추가).
   - 임베딩은 Azure `text-embedding-3-small` (1536d).
2. **PostgreSQL `mapped_history`** — 1 mapped Activity = 1 row (조건: `wa is not None AND l6_main is not None`).
   - 멱등 키 = `(run_id, wa, l6_main, company)` UNIQUE.
   - 후속 view_builder (WP summary / S-curve / EVM AC) 와 Optimizer / Forecaster 의 누적 진행률 계산 source.

추가 책임:
- **fail-fast**: Azure embedding 호출 (과금) 전 `pipeline_runs(run_id)` row 존재 확인 → orphan Chroma row 방지.
- **resource 일관성**: PG connection 1개를 `assert_pipeline_run_exists` → Chroma upsert → `insert_mapped_history_batch` → `update_run_atomized_count` 까지 단일 try/finally 로 묶음 (asyncpg pool leak 방지).
- **within-call dedup**: 같은 (date, company, l6_main, work_content) 4-tuple 이 한 호출 안에 중복 등장 가능 (남웅 47 row → 11 unique) → Chroma 0.5.20 의 batch upsert 가 중복 id 거부 → Python 단에서 마지막 등장 metadata 채택.
- **HNSW hang 방어**: 1000+ doc 통째 upsert 시 Chroma 0.5.20 의 HNSW 인덱스 build 가 hang (이전 cycle 153bfa17/d38605f9 4시간 stuck 사례) → 100 doc 단위 batch split.

**LLM 호출 0건**. Azure embeddings.create 만 호출.

---

## 2. 파일 + LOC + 책임

| 파일 | LOC | 책임 |
|---|---:|---|
| `pipeline/agents/atomizer.py` | 196 | 공개 API `atomize()` + helper 3개 (`_make_doc_id` / `_build_metadata` / `_format_document`) + `AtomizerConfig` dataclass |
| `pipeline/chroma_client.py` | 35 | `ChromaClient.get_or_create_daily_activities()` (HNSW cosine 컬렉션 lazy create) — atomizer 의 유일한 Chroma 진입점 |
| `pipeline/db.py` (관련 메서드) | — | `assert_pipeline_run_exists` (`db.py:176`) / `update_run_atomized_count` (`db.py:238`) / `insert_mapped_history_batch` (`db.py:458`) / `get_pipeline_run` (`db.py:504`) — atomizer 의 PG 진입점 4 종 |
| `pipeline/state.py` (관련 TypedDict) | — | `Activity` (44 필드, atomize input) + `ParsedDailyReport` (`report_date` 추출용) |
| `pipeline/graph.py:atomizer_node` | 5 | LangGraph node 래퍼 — state 에서 mapped/parsed/run_id 추출 → `atomize()` 호출 → `{atomized_ids, current_node}` patch |
| `infra/postgres/migrations/2026-05-18_mapped_history.sql` | 19 | `mapped_history` 9 컬럼 + UNIQUE (run_id, wa, l6_main, company) + 2 index 신설 |
| `infra/postgres/migrations/2026-05-19_mapped_history_trade.sql` | 11 | `mapped_history.trade TEXT` 컬럼 신설 (의도: Activity.trade 박기, 단 atomizer 코드 미반영 — 이슈) |
| `pipeline/tests/test_atomizer.py` | 271 | unit: doc_id 결정성 / metadata scalar / dedup / fail-fast / namwong_47 / idempotent / missing_run |
| `pipeline/tests/test_atomizer_atomized_count.py` | 29 | update_run_atomized_count 직접 검증 |
| `pipeline/tests/test_atomizer_mapped_history.py` | 288 | mapped_history INSERT 4 케이스: valid 인 row 만 / wa None skip / l6 None skip / grouping (run_id 기준) |

**atomizer.py LOC 추이**:
- `ef7c6cd` (baseline 2026-05-20 직전): 141 LOC
- `a3db32a` 적용 후: 약 164 LOC (Chroma init retry + batch split + asyncio import)
- `9252ac7` 적용 후: 약 195 LOC (`_format_document` 30 LOC + `_build_metadata` 4 필드)
- `b560dd4` 적용 후: 196 LOC (한 줄 변경 — batch_size default + docstring)
- **현재 HEAD `1ba783f`**: 196 LOC

---

## 3. 흐름 다이어그램

```
[graph.py:atomizer_node (state, GraphConfig.atomizer)]
   state["mapped"] (list[Activity])
   state["parsed"] (ParsedDailyReport — report_date 추출)
   state["run_id"] (str → uuid.UUID coerce)
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│   atomize(mapped, parsed_report, run_id, cfg: AtomizerConfig)           │
│                                                                          │
│  ① valid filter (atomizer.py:100)                                        │
│     valid = [a for a in mapped                                           │
│              if a["l6_main"] is not None                                 │
│              and a.get("work_content")]                                  │
│     if not valid: return []                                              │
│                                                                          │
│  ② date = parsed_report["report_date"]                                   │
│                                                                          │
│  ③ PG fail-fast (assert_pipeline_run_exists)                             │
│     SELECT 1 FROM pipeline_runs WHERE run_id=$1                          │
│     None → raise RuntimeError                                            │
│                                                                          │
│  ④ Azure SDK init (AzureOpenAI, timeout=30s, max_retries=3)              │
│                                                                          │
│  ⑤ doc_id dedup (within-call)                                            │
│     seen: dict[str, int] = {}                                            │
│     for i, a in enumerate(valid):                                        │
│         doc_id = _make_doc_id(date, company, l6_main, work_content)      │
│         seen[doc_id] = i   # 마지막 등장 idx 채택                          │
│                                                                          │
│  ⑥ payload 3종 빌드                                                       │
│     ids       = list(seen.keys())                                        │
│     documents = [_format_document(dict(valid[i]), date)                  │
│                   for i in seen.values()]                                │
│     metadatas = [_build_metadata(valid[i], date, str(run_id))            │
│                   for i in seen.values()]                                │
│                                                                          │
│  ⑦ Azure embedding batch (batch_size=64)                                 │
│     for i in range(0, len(documents), 64):                               │
│         chunk = documents[i:i+64]                                        │
│         resp = azure.embeddings.create(model, input=chunk)               │
│         embeddings.extend([d.embedding for d in resp.data])              │
│                                                                          │
│  ⑧ Chroma client init (3 retry + exponential backoff)                    │
│     for _attempt in range(3):                                            │
│         try: ChromaClient.get_or_create_daily_activities() → coll        │
│         except: asyncio.sleep(2**attempt)                                │
│                                                                          │
│  ⑨ Chroma upsert (100 doc 단위 split — HNSW hang 방어)                    │
│     for _j in range(0, len(ids), 100):                                   │
│         coll.upsert(ids[..], embeddings[..], documents[..], metadatas[..]) │
│                                                                          │
│  ⑩ mapped_history INSERT (조건: wa AND l6_main 둘 다 not None)            │
│     mh_valid = [a for a in mapped                                        │
│                 if a["l6_main"] is not None and a["wa"] is not None]     │
│     if mh_valid:                                                         │
│        run_info = await pg.get_pipeline_run(run_id)                      │
│        site_id = run_info["site_id"]; rd = run_info["report_date"]       │
│        mh_rows = [{wa, l6_main, company, today_qty,                      │
│                    today_assigned_workers, unit} for a in mh_valid]      │
│        await pg.insert_mapped_history_batch(run_id, rd, site_id, mh_rows)│
│                                                                          │
│  ⑪ update_run_atomized_count(run_id, len(ids))                           │
│     UPDATE pipeline_runs SET atomized_count=$1, current_node='atomizer'  │
│                                                                          │
│  finally: pg.close()                                                     │
│                                                                          │
│  return ids                                                              │
└─────────────────────────────────────────────────────────────────────────┘
                │
                ▼
[graph.py:atomizer_node] → return {"atomized_ids": ids, "current_node": "atomizer"}
```

**입력 / 출력 단언**:
- 입력 mapped 가 empty 이거나 valid 가 비면 즉시 `[]` 반환, PG / Chroma / Azure 호출 0건.
- 단일 PG connection (`pg = PGClient(...); await pg.connect()`) 가 ③ ~ ⑪ 까지 재사용되며 try/finally 로 항상 close 보장.
- ⑦ embedding 결과 길이 = ids 길이 (1:1). ⑨ upsert chunk 단위로 동기화.

---

## 4. Public 함수 전수 표

| Function / Class | File:Line | Sync/Async | Signature | 역할 |
|---|---|---|---|---|
| `AtomizerConfig` | atomizer.py:24 | dataclass | `@dataclass` (12 필드) | Azure + Chroma + PG 연결 + batch/timeout/dim 설정 |
| `_make_doc_id` | atomizer.py:42 | sync | `(date, company, l6_main, work_content) -> str` | SHA256 16자 prefix — 결정성 doc id |
| `_build_metadata` | atomizer.py:48 | sync | `(a: Activity, date: str, run_id: str) -> dict[str, Any]` | Activity → Chroma metadata 15 필드 평탄화 dict |
| `_format_document` | atomizer.py:71 | sync | `(a: dict, date, perperson=None, productivity_pct=None) -> str` | 사람이 읽을 수 있는 doc 텍스트 (live / backfill 2 모드) |
| `atomize` | atomizer.py:93 | async | `(mapped, parsed_report, run_id, cfg) -> list[str]` | 공개 API — Chroma upsert + mapped_history INSERT + count UPDATE |

private helper 외 외부 호출자가 있는 함수는 `atomize` 1 개 (graph.py:atomizer_node 가 유일 호출자).

---

## 5. 각 함수 walkthrough

### 5.1 `atomize` (entry, atomizer.py:93-196)

`atomizer_node` 가 호출하는 유일한 진입점. 위 §3 흐름 그대로. 주요 분기:

- **Empty-short-circuit** (atomizer.py:100-102): `valid = [a for a in mapped if a["l6_main"] is not None and a.get("work_content")]` 가 비면 `[]` 즉시 return, 어떤 외부 호출도 없음. `work_content` truthy 가드는 cf3c143 cycle (2026-05-19, PR #28) 에 도입 — Azure embedding API 가 빈 input 에 HTTP 400 을 던지는 케이스 차단.
- **PG fail-fast** (atomizer.py:112): `await pg.assert_pipeline_run_exists(run_id)` — 미존재 시 RuntimeError. Azure 호출 (과금) 이전이라는 점이 핵심.
- **Azure 호출 단계 1: embedding batch** (atomizer.py:136-140): `range(0, len(documents), cfg.batch_size)` — batch_size=64 (이전 16). 1일 cycle ~200 doc 이라 4 batch → 1 batch.
- **Chroma init retry** (atomizer.py:145-157): `for _attempt in range(3)` + `asyncio.sleep(2**_attempt)`. `ChromaClient.__init__` 가 user_identity HTTP 호출을 내부에서 수행, 첫 cold start 에서 Errno 60 timeout 가능 → 1s / 2s backoff. 3 회 모두 실패 시 RuntimeError 에 `_last_err` 타입 + 메시지 포함.
- **Chroma upsert split** (atomizer.py:160-167): `_CHROMA_UPSERT_BATCH = 100`. 1000+ doc 통째 upsert 가 HNSW build 단계에서 4시간 hang 한 이전 사례 (153bfa17/d38605f9) 가 commit 메시지에 명시.
- **mapped_history 조건부 INSERT** (atomizer.py:171-190): Chroma 적재 대상 (valid) 과 다른 filter — `wa is not None AND l6_main is not None` 동시 충족. wa 가 None 인 row 는 WBS 매핑 미완 → mapped_history INSERT 대상 아님. `get_pipeline_run(run_id)` 으로 `site_id` + `report_date` 를 PG 에서 lookup 해야 함 (state 에는 site_id 가 없음). asyncpg 는 PG DATE 컬럼을 datetime.date 로 반환하므로 `_rd` 가 그대로 INSERT params 로 들어감.
- **count UPDATE** (atomizer.py:192): `update_run_atomized_count(run_id, len(ids))` — `pipeline_runs.atomized_count` 와 `current_node='atomizer'` 동시 갱신. 0 row affected 면 RuntimeError (silent no-op 방지).
- **finally pg.close()** (atomizer.py:193-194): 어떤 분기로든 connection 반환.

### 5.2 `_make_doc_id` (atomizer.py:42-45)

4-tuple → 결정성 16자 hex.

```python
raw = f"{date}|{company}|{l6_main}|{work_content}"
return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
```

테스트 (`test_atomizer.py:48-52`) 가 "남웅건설 + 철근콘크리트공사 + 기초 거푸집 설치 + 2025-09-25 → 73ff80435e312c41" 을 hardcoded 검증. 같은 사이트의 동일 작업이 다른 cycle 에서 들어와도 같은 doc_id 라 자동 upsert (덮어쓰기) semantics 가 보장됨. site_id 가 입력에 없는 점은 multi-site 운영 진입 시 ID schema 변경 후보 (design-intent 카드의 stale "Suspected related" 그대로 유효).

### 5.3 `_build_metadata` (atomizer.py:48-68)

Activity → Chroma metadata dict. Chroma 0.5.20 은 metadata 값이 scalar (str/int/float/bool) 만 허용, list/dict 금지. 따라서 `conditions` 는 `",".join(a.get("conditions") or [])` 로 CSV 평탄화 (역정규화는 `forecaster/rerank.py:_normalize_chroma_metadata`).

**15 필드** (2026-05-21 `9252ac7` cycle 에 12 → 15 확장):
- 기본: `date, run_id, company, l5_disc, l6_main, wa, unit, today_qty, assigned_workers, worker_source, mapping_conf, conditions` (12)
- Phase 1 추가: `l7_5_activity` (live atomize 시점에 Mapper Task 6 결과로 채워짐), `perperson` (live=0 placeholder, backfill Task 13 에서 view_builder 산식 결과 적재), `productivity_pct` (동일) (+3)

None 안전 캐스트:
- `l6_main or ""` / `l7_5_activity or ""` / `wa or ""` — 빈 문자열로 fallback
- `mapping_conf or 0.0` / `today_qty` / `assigned_workers` / `perperson` / `productivity_pct` — float 강제, None 은 0.0 fallback (atomizer.py:63-64 의 `a.get("perperson", 0) or 0` 이중 가드)

### 5.4 `_format_document` (atomizer.py:71-90, 2026-05-21 신규)

`9252ac7` 에 신설. 이전엔 `documents = [valid[i]["work_content"] for i in seen.values()]` (work_content 만 임베딩) → 도메인 의미 유사도가 work_content 단어에만 의존해 일반화 부족 → 사람이 읽을 수 있는 헤더 + 본문 형식으로 변경.

2 모드 분기:
- **live (atomize 호출, perperson=None)**:
  ```
  [2025-09-25] 남웅건설 · 철근콘크리트공사 · 기초 거푸집 설치
  시공량 12.5 ㎥ / 인원 8 명
  조건: 정상
  ```
- **backfill (Task 13 호출, perperson + productivity_pct 값)**:
  ```
  [2025-09-25] 남웅건설 · 철근콘크리트공사 · 기초 거푸집 설치
  시공량 12.5 ㎥ / 인원 8 명 -> 인당 1.56 ㎥/인 (78.0%)
  조건: 장비대기, 자재미입고
  ```

**중요한 invariant**: doc_id 는 `_make_doc_id` 가 `work_content` 만 hashing 에 사용 (date|company|l6_main|work_content) → documents 형식이 바뀌어도 doc_id 는 idempotent. backfill 이 풀 형식으로 upsert 해도 같은 row 가 갱신된다.

`conds` 가 빈 list 면 "정상" 으로 fallback (atomizer.py:84). `unit` 이 빈 str 이면 backfill 모드여도 short form 으로 fallback (atomizer.py:87).

### 5.5 `AtomizerConfig` (atomizer.py:24-39)

dataclass. `cfg.batch_size = 64` (이전 16) 는 `b560dd4` 변경. 인라인 주석: "Azure embedding input limit 2048, 64 안전. 1일 cycle ~200 doc 이 1 batch."

`embedding_dim=1536` 필드는 코드 내 직접 소비처 grep 결과 없음 — Chroma cold start 시 참고용 dead field 가능성 (design-intent 카드의 stale 의심, 본 cycle 검증 미실시).

---

## 6. Chroma `daily_activities` 컬렉션 schema

`pipeline/chroma_client.py:30-35`:

```python
def get_or_create_daily_activities(self) -> Collection:
    """1 doc = 1 Activity (시트4 line). doc text = work_content."""
    return self.client.get_or_create_collection(
        name=self.DAILY_ACTIVITIES,
        metadata={"hnsw:space": "cosine"},
    )
```

(docstring 의 "doc text = work_content" 는 `9252ac7` 이전 잔존 주석 — 실제론 `_format_document` 결과)

### 6.1 doc id 규칙

- 16자 hex (SHA256 prefix). 입력: `date | company | l6_main | work_content`.
- site_id 미포함 — multi-site 동작 시 동일 (date, company, l6_main, work_content) 조합이 다른 현장에서 충돌 가능. PoC 단계는 1 site 가정.

### 6.2 metadata 키 (15)

| 키 | 타입 | source | 비고 |
|---|---|---|---|
| `date` | str | `parsed_report["report_date"]` | YYYY-MM-DD |
| `run_id` | str | UUID str(run_id) | 운영 감사용 |
| `company` | str | `Activity.company` | 업체명 |
| `l5_disc` | str | `Activity.l5_disc` | 공종 (한글) |
| `l6_main` | str | `Activity.l6_main or ""` | Mapper 결정 |
| `l7_5_activity` | str | `Activity.l7_5_activity or ""` | 2026-05-21 추가, Task 6 결과 |
| `wa` | str | `Activity.wa or ""` | Mapper WA 결정 (None 가능) |
| `unit` | str | `Activity.unit` | 단위 |
| `today_qty` | float | `Activity.today_qty` | float 강제 |
| `assigned_workers` | float | `Activity.assigned_workers` | float 강제 |
| `perperson` | float | `Activity.perperson` or 0 | 2026-05-21 추가, live=0 |
| `productivity_pct` | float | `Activity.productivity_pct` or 0 | 2026-05-21 추가, live=0 |
| `worker_source` | str | `Activity.worker_source` | parsed / mh_prorated / user_corrected |
| `mapping_conf` | float | `Activity.mapping_conf or 0.0` | 0.0~1.0 |
| `conditions` | str | `",".join(a.get("conditions") or [])` | CSV 평탄화 |

### 6.3 document 본문

`_format_document` 가 생성한 다국어 자연어 텍스트. 한 doc 당 3 줄 (또는 2 줄 + 빈 조건 라인). 형식 §5.4 참조.

### 6.4 다운스트림 소비

- `pipeline/agents/forecaster/agent.py` — `_forecast_one_group` 이 동일 컬렉션 query.
- `pipeline/agents/optimizer/retrieve.py:13` — "conditions 는 atomizer 와 동일 comma-joined str (결정 #19) — `substring in` 검사" (atomizer 의 CSV 평탄화 표현에 직접 의존).

---

## 7. `mapped_history` INSERT

### 7.1 테이블 schema (migration `2026-05-18_mapped_history.sql`)

```sql
CREATE TABLE IF NOT EXISTS mapped_history (
  id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
  report_date DATE NOT NULL,
  site_id TEXT NOT NULL REFERENCES sites(site_id),
  wa TEXT NOT NULL,
  l6_main TEXT NOT NULL,
  company TEXT NOT NULL,
  today_qty NUMERIC,
  today_assigned_workers NUMERIC,
  unit TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, wa, l6_main, company)
);
CREATE INDEX idx_mapped_history_site_date ON mapped_history (site_id, report_date DESC);
CREATE INDEX idx_mapped_history_triplet  ON mapped_history (wa, l6_main, company, report_date DESC);
```

이후 `2026-05-19_mapped_history_trade.sql` 가 `trade TEXT` 컬럼 추가 (의도: Activity.trade 박기). **단 atomizer.py 의 `mh_rows` dict 는 trade 키를 포함하지 않음** (atomizer.py:179-189) → 현재 trade 컬럼은 NULL 로만 들어감. → 이슈 #A-N3 참조.

### 7.2 입력 조건

```python
mh_valid = [a for a in mapped
            if a["l6_main"] is not None and a["wa"] is not None]
```

Chroma valid (`l6_main is not None AND work_content truthy`) 와 **다른 필터**. mapped_history 는 wa 미매핑 row 를 제외 (WBS 매핑 완료된 것만 누적). Phase 3 결정.

### 7.3 batch INSERT 로직 (`db.py:458-502`)

```sql
INSERT INTO mapped_history
    (run_id, report_date, site_id, wa, l6_main, company,
     today_qty, today_assigned_workers, unit)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (run_id, wa, l6_main, company) DO UPDATE SET
    today_qty              = EXCLUDED.today_qty,
    today_assigned_workers = EXCLUDED.today_assigned_workers,
    unit                   = EXCLUDED.unit
```

`con.executemany` 로 일괄 — 동일 connection 의 prepared statement reuse. ON CONFLICT 의도:
- **동일 (run_id, wa, l6_main, company) 재호출** 시 today_qty / today_assigned_workers / unit 을 EXCLUDED 값으로 갱신. **마지막 등장 값 채택** (합계 아님 — Phase 0 합의).
- `trade` 컬럼은 UPDATE SET 절에도 없음 → 향후 trade 박힘 활성화 시 SET 절도 같이 추가 필요.

### 7.4 site_id / report_date 조달

atomizer 는 state 에서 site_id 를 받지 않으므로 PG 에서 lookup (atomizer.py:174-178):

```python
run_info = await pg.get_pipeline_run(run_id)
if run_info is None:
    raise RuntimeError(...)
_site_id = run_info["site_id"]
_rd = run_info["report_date"]  # datetime.date
```

`get_pipeline_run` (`db.py:504`) 가 SELECT 1 row 후 dict 반환. asyncpg DATE → datetime.date 매핑이 mapped_history.report_date (PG DATE) 에 그대로 들어간다 (`_rd` 변환 없음).

### 7.5 batch size

mapped_history INSERT 자체는 batch size 제한 없이 `executemany` 1 회. Chroma upsert (100) 와 다름. mh_valid 는 보통 100~300 row 수준 (1162 row 검증 cycle `888c535d` 에서 mh=285).

---

## 8. `batch_size 16 → 64` 변경 (`b560dd4`)

### 8.1 어디서 쓰이는가

`atomizer.py:34-36`:

```python
batch_size: int = (
    64  # 2026-05-22: Azure embedding input limit 2048, 64 안전. 1일 cycle ~200 doc 이 1 batch.
)
```

소비처는 1 곳 — Azure embedding 호출 (atomizer.py:137-140):

```python
for i in range(0, len(documents), cfg.batch_size):
    chunk = documents[i : i + cfg.batch_size]
    resp = azure.embeddings.create(model=cfg.embedding_model, input=chunk)
    embeddings.extend([d.embedding for d in resp.data])
```

**Chroma upsert 의 batch size 와 별개**. Chroma 는 `_CHROMA_UPSERT_BATCH = 100` (atomizer.py:160) 으로 hardcoded.

### 8.2 성능 변화

- 1일 cycle ~200 doc 기준: 13 batch (16) → 4 batch (64) → **호출 ¼**.
- 실 검증 cycle `888c535d` (a3db32a commit msg): 1162 mapped_activities → mh=285 row → atomized=64 (dedup 후) → 19분 1초 cycle. 본 batch 변경 적용 이후 호출 횟수 절감.
- Azure embedding input array limit 2048 (Azure docs) — 64 는 안전 margin. 1000 doc 도 4 batch 만에 처리 가능 (`b560dd4` commit msg: "3~4 batch → 1 batch (호출 ¼)").
- 단일 batch 가 커지면 HTTP timeout (30s) 위험 증가하지만 doc 본문이 짧아 (3 줄 자연어) 64 는 안전. cfg.azure_timeout=30.0 + max_retries=3 가 backup.

### 8.3 호환 영향

- Chroma upsert split (100) 보다 작아도 무관 — embedding 단계와 upsert 단계는 독립적으로 batch.
- backfill (Task 13) 가 같은 cfg 를 공유 → backfill 시에도 동일하게 4× 호출 절감.

---

## 9. embedding 모델

- 모델: Azure `text-embedding-3-small-ai-board-test` (`AZURE_OPENAI_API_VERSION=2024-12-01-preview`).
- 차원: 1536 (`AtomizerConfig.embedding_dim=1536` 명시, 단 코드에서 실 소비처 없음 — dead field 의심).
- 호출 경로: `AzureOpenAI(api_key, api_version, azure_endpoint, timeout=30, max_retries=3).embeddings.create(model, input=chunk)` (atomizer.py:114-120 + 139).
- `resp.data` 는 OpenAI SDK 의 `list[Embedding]` — `d.embedding` 이 `list[float]` (1536d).
- Azure 가 timeout / 5xx 던질 시 SDK 가 자동 max_retries=3 적용.
- 임베딩 source 텍스트 = `_format_document` 결과 (이전엔 work_content 단독). 사람이 읽을 수 있는 자연어 → 유사도 검색이 단어 수준이 아닌 문장 수준에서 작동.

---

## 10. fail-fast PG 정책

세 가지 fail-fast 지점.

### 10.1 진입 직후 (assert_pipeline_run_exists)

`db.py:176-192`. SELECT 1 → row 없으면 RuntimeError. **Azure embedding (과금) 호출 이전** 에 위치 → integration test 가 fixture 의 pipeline_runs INSERT 누락 시 즉시 fail. orphan Chroma row 도 차단.

### 10.2 mapped_history 단계 (get_pipeline_run)

`atomizer.py:174-176`. mh_valid 가 있을 때만 호출 — get_pipeline_run 가 None 반환 시 RuntimeError. (assert 단계와 중복되어 보이지만 site_id/report_date 를 동시에 가져오는 부수 효과가 있어 같은 SELECT 다른 컬럼.)

### 10.3 atomized_count UPDATE (update_run_atomized_count)

`db.py:238-258`. `result.endswith(" 0")` 검사 — UPDATE 가 0 row 면 RuntimeError. silent no-op 방지.

### 10.4 무엇을 raise 하지 않는가

- **Chroma init 3 retry 실패** → RuntimeError (전파). 인접 fail-fast 와 통일.
- **Azure embedding API 실패** → SDK max_retries=3 후 raise (RateLimit / Timeout / 5xx). atomize 가 catch 안 함 → graph node 가 받아 LangGraph error 처리.
- **valid empty** → fail 아닌 정상 return `[]`. 빈 작업일보 시나리오.
- **mh_valid empty** → mapped_history INSERT skip, 단 Chroma upsert + count UPDATE 는 계속. log 없이 조용히 진행.
- **conditions / l7_5_activity None** → 안전 fallback (`""` 또는 0) — `_build_metadata` 내부 처리, raise 없음.

전반적으로 "Azure 호출 / Chroma 호출 / PG INSERT 전에 가능한 검증을 모두 수행, 실패는 raise 로 명시" 원칙.

---

## 11. 데이터 흐름 통합 표 (Activity → 출력)

| `Activity` 필드 | Chroma metadata | Chroma document | mapped_history 컬럼 | 변환 |
|---|---|---|---|---|
| `company` | `company` | `[date] {company} · ...` | `company` | as-is |
| `l5_disc` | `l5_disc` | — | — | as-is |
| `l6_main` | `l6_main` | `... · {l6_main} · ...` | `l6_main` | None→"" (Chroma), filter (mh) |
| `l7_5_activity` | `l7_5_activity` | `... · {l7_5_activity}` | — | None→"" |
| `wa` | `wa` | — | `wa` | None→"" (Chroma), filter (mh) |
| `unit` | `unit` | `시공량 N {unit}` | `unit` | as-is |
| `today_qty` | `today_qty` | `시공량 {N}` | `today_qty` | float() 강제 |
| `assigned_workers` | `assigned_workers` | `인원 {N} 명` | — | float() 강제 |
| `today_assigned_workers` | — | — | `today_assigned_workers` | `.get(...)` (오타 가능 — 본 cycle 코드는 `today_assigned_workers` 키 직접 lookup, Activity TypedDict 정의에는 이 키 없음 — §13 이슈) |
| `worker_source` | `worker_source` | — | — | as-is |
| `mapping_conf` | `mapping_conf` | — | — | float, None→0.0 |
| `conditions` | `conditions` (CSV) | `조건: {a, b, c}` 또는 `정상` | — | `",".join(... or [])` |
| `work_content` | — | doc_id input 만 | — | hashed |
| `perperson` | `perperson` | (backfill 시) `인당 {N}` | — | float, None→0 |
| `productivity_pct` | `productivity_pct` | (backfill 시) `({N}%)` | — | float, None→0 |
| `trade` | — | — | (미박힘 — 이슈) | trade 컬럼은 NULL |
| (외부) `parsed_report["report_date"]` | `date` | `[{date}]` | (PG에서 lookup) `report_date` | str / asyncpg DATE |
| (외부) `run_id` | `run_id` | — | `run_id` | str(UUID) (Chroma), UUID (PG) |
| (PG) `pipeline_runs.site_id` | — | — | `site_id` | get_pipeline_run lookup |

**없는 곳**:
- mapper_activities 의 `cum_workers_today` / `cum_actual_mh_today` 는 atomizer 가 안 쓰임 (forecaster / view_builder 만 소비).
- Chroma 의 `assigned_workers` 와 mapped_history 의 `today_assigned_workers` 는 다른 필드 — atomizer 가 양쪽을 각각 직접 매핑.

---

## 12. 호출 source

### 12.1 `graph.py:atomizer_node` (atomizer 의 유일 호출자)

`pipeline/graph.py:294-298`:

```python
async def atomizer_node(state: CPIAState, cfg: GraphConfig) -> dict:
    run_id = uuid.UUID(state["run_id"]) if isinstance(state["run_id"], str) else state["run_id"]
    parsed: ParsedDailyReport = state["parsed"]
    atomized_ids = await atomize(state["mapped"], parsed, run_id, cfg.atomizer)
    return {"atomized_ids": atomized_ids, "current_node": "atomizer"}
```

`GraphConfig.atomizer: AtomizerConfig` (graph.py:44). LangGraph 가 build_graph (production) + build_atomized_demo_graph (graph.py:531, b560dd4 cycle 신규 — atomizer→forecaster→...→reporter chain) 양쪽에서 동일 노드 사용 (graph.py:543, 591).

`state["run_id"]` 는 str 또는 UUID — 명시적 isinstance 캐스트. `state["mapped"]` 는 Mapper / HIL 1 가 마지막 갱신. `state["parsed"]` 의 `report_date` 가 doc_id 의 date 컴포넌트.

### 12.2 build_graph 위치 (production)

mapper → hil_1 → atomizer → forecaster → hil_2 → optimizer → reporter (architecture_overview §1 다이어그램). atomizer 의 출력 `atomized_ids` 는 후속 노드에서 직접 소비 안 됨 — Chroma 컬렉션 자체가 query source.

### 12.3 build_atomized_demo_graph (b560dd4 직후 신규)

mapped 입력 단계부터 reporter 까지 모두 실행하는 fixture chain — atomizer 부터 시작. mapper 우회 (mapper output 을 fixture 로 주입).

---

## 13. LLM 호출

**0건**. Azure LLM (`gpt-5.1-chat-ai-board-test`) 미호출.

**Azure embedding 만 호출** — `text-embedding-3-small-ai-board-test` (1536d). LLM 비용 0, embedding 비용만 발생.

cycle `888c535d` (1162 mapped row, mh=285) 기준 dedup 후 atomized=64 → embedding 호출 1 batch (batch_size=64 적용 후) → Azure embedding API HTTP 1 회. 이전 batch_size=16 이면 4 회.

---

## 14. 이슈 표

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| A-N3 | atomizer / mapped_history | M | `2026-05-19_mapped_history_trade.sql` 가 trade 컬럼 신설 + commit msg "atomizer.py:130 mh_rows 생성 시 Activity.trade (state.py:30) 박기" 의도 명시했으나 atomizer.py 의 mh_rows dict (atomizer.py:179-189) 에 trade 키 없음 → 현재 trade 컬럼은 항상 NULL | mh_rows dict 에 `"trade": a["trade"]` 추가 + insert_mapped_history_batch SQL 의 컬럼 / VALUES / ON CONFLICT SET 모두 trade 포함하도록 수정 |
| A-N4 | atomizer | L | `mh_rows` 에서 `a.get("today_assigned_workers")` 키 lookup — `Activity` TypedDict (state.py:32-94) 에는 `today_assigned_workers` 정의 없음 (`assigned_workers` 만 존재). PG mapped_history.today_assigned_workers 는 항상 NULL 일 가능성 | mh_rows 빌드 시 `a.get("assigned_workers")` 로 교체 검토. 단 mh 가 실제 채워지는지 (e.g. mapper 가 today_assigned_workers 키 별도 set 하는지) 실 DB query 로 검증 우선 |
| A-N5 | atomizer | M | `_format_document` (live) 가 `unit` 빈 str 일 때 short form 으로 fallback (`if not unit`) — backfill 시점에 perperson 값이 있어도 unit None 이면 풀 form 못 만듦. unit None 인 Activity 비율이 있다면 backfill 효과 일부 손실 | unit None 인 mapped row 비율 측정 + backfill cycle test |
| A-N6 | atomizer / config | L | `AtomizerConfig.embedding_dim=1536` 필드 코드 내 소비처 grep 결과 없음 (design-intent 카드의 stale 의심 그대로 유효) | 다음 cycle 삭제 또는 Chroma init 시 차원 검증에 사용 |
| A-N7 | atomizer / chroma_client | L | `chroma_client.py:31` docstring "doc text = work_content" 가 `9252ac7` 이후 stale (`_format_document` 결과로 변경됨) | docstring 1줄 갱신 |
| A-N8 | atomizer | L | `_CHROMA_UPSERT_BATCH = 100` 이 함수 내부 hardcoded — env / config 외부화 안 됨. HNSW hang 재현 시 즉시 조정 어려움 | AtomizerConfig 에 `chroma_upsert_batch: int = 100` 필드 추가 검토 |
| A-N9 | atomizer | L | Chroma init retry 3 회 + exponential backoff (1s, 2s) 이 dataclass 외부 설정 아님 — Azure SDK 의 max_retries=3 (cfg) 과 일관성 떨어짐 | AtomizerConfig 에 `chroma_init_max_retries` 필드 추가 검토 |
| A-N10 | atomizer | L | `assert_pipeline_run_exists` + `get_pipeline_run` 가 같은 pipeline_runs row 를 두 번 SELECT (한 cycle 안) — fail-fast 와 site_id/report_date lookup 통합 가능 | get_pipeline_run 호출 한 번으로 양쪽 책임 통합, assert 는 None 분기로 대체 |
| A-N11 | atomizer / state | L | atomizer 가 `state["site_id"]` 미신뢰 (PG lookup) — state.py 의 CPIAState 가 site_id 를 가지면 PG 라운드트립 1 회 절감 가능 | state 스키마 확장 검토 (graph orchestration 결정 필요) |

design-intent 의 기존 카드 (A-N1: work_content 빈 activity skip, A-N2: conditions None 안전 처리) 는 본 cycle 에도 그대로 유효 (코드 보존).

---

## 15. 검증 / 테스트 상태

- `pipeline/tests/test_atomizer.py` (271 LOC, 11 케이스): doc_id 결정성 (hardcoded `73ff80435e312c41`) / metadata scalar / conditions CSV / dedup / fail-fast / namwong_47 / upsert idempotent / missing_run RuntimeError.
- `pipeline/tests/test_atomizer_atomized_count.py` (29 LOC): update_run_atomized_count 직접 호출 + UPDATE 성공 검증.
- `pipeline/tests/test_atomizer_mapped_history.py` (288 LOC, 4 케이스): valid mapped → mh INSERT / wa None skip / l6 None skip / grouping (run_id 별 분리).
- 실 cycle 검증 (a3db32a commit msg): run_id `888c535d` (78사 통합 1 cycle, 19분 1초) — pa=ma=1162, mh=285, fc=293, opt=25, dr=1, 9 jsonb 다 채움.
- 본 cycle 신규 build_atomized_demo_graph (graph.py:531, `ef95e02`) 가 atomizer → reporter chain fixture 검증.

**Pending**:
- A-N3 (trade 컬럼 NULL) 의 실 DB 상태 검증 미실시. `SELECT COUNT(*) FILTER (WHERE trade IS NOT NULL) FROM mapped_history` 로 즉시 확인 가능.
- A-N4 (today_assigned_workers 키) 의 PG 컬럼 실측 검증 미실시.

---

*최종 수정: 2026-05-26 (HEAD `1ba783f`). 이전 design-intent 카드 (2026-05-17 generated / 2026-05-20 last-checked, `ef7c6cd`) 가 "코드 변경 없음" 으로 표시했던 라벨이 본 cycle 에 무효화 — atomizer 직접 commit 3건 (`a3db32a` Chroma retry+batch, `9252ac7` documents format + metadata 풍부화, `b560dd4` batch_size 64) + 인접 migration 1건 (`16f1b88` mapped_history.trade) 누적.*
