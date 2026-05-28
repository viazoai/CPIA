# Deep Dive — Mapper 서브시스템

- **Generated**: 2026-05-26 (resolve_wa 7단계 + shift-weighted MH + l7.5 컬럼 propagate cycle)
- **Baseline → HEAD**: `ef7c6cd` (2026-05-20) → `1ba783f` (2026-05-26 sync of origin/main into A_Track)
- **Range**: `pipeline/agents/mapper.py` (604 LOC, baseline 571 → +33 LOC) + `infra/postgres/migrations/2026-05-23_mapper_l7_5_columns.sql` (8 LOC) + `pipeline/db.py:insert_mapper_activities_batch` (33 → 37 컬럼)
- **Pair**:
  - `./architecture_overview.md` — 시스템 다이어그램 + 8 서브시스템 요약
  - `./design-intent/design_intent_mapper.md` — T1 함수 인덱스 + T2 이슈 카드 (본 문서는 그 풀 walk-through)

---

## 1. Overview — Mapper 가 하는 일

Parser 가 추출한 시트4 Activity 한 행 (`work_content`, `company`, `trade`, `unit`, `today_qty`, `bp_code`, `zone`...) 을 받아서 사내 WBS 좌표 두 개를 결정한다.

- **`wa`** (Work Area, 예: `FAB` / `CUB` / `OSBL`) — 어느 zone 의 작업인가
- **`l6_main`** (대공종, 예: `철근콘크리트공사` / `전기공사`) — 어떤 공종인가

부가로 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼을 `activity_master` 에서 propagate (2026-05-23 신규, PoC 단계엔 대부분 None — Master List 1:N 제약). `plan_mh` (B.2 prorate 분모) 와 `cum_actual_mh_today` (시간대 가중 누적 MH, EVM AC 분모), `cum_workers_today` (보조 = `mh / 8.0`), `assigned_workers` (그 (company, l6_main) bucket 의 BP 총인원 비례 분배), 그리고 RAG top-K alternatives JSONB (FE Mapper Review dropdown 선택지) 를 함께 채워서 `mapper_activities` 33+4 컬럼 INSERT 까지 한다.

이 결과가 다운스트림 3 노드의 입력이 된다.

- Atomizer → Chroma `daily_activities` 에 1 doc/Activity 적재
- Forecaster → (company, l6_main, wa) bucket 단위로 RAG + Plan fallback 진단
- HIL 1 (Mapper Review) → `requires_review=True` row 만 dashboard modal 로 띄움

---

## 2. 파일 + LOC + 책임

| 파일 | LOC | 역할 |
|---|---:|---|
| `pipeline/agents/mapper.py` | 604 | 6 단계 매핑 흐름 + helper 12 함수 + dataclass 2 (MapperConfig / WAResolution) |
| `pipeline/agents/_concurrency.py` | (별도) | `_MAPPER_CONCURRENCY` 환경 변수 (graph.py 가 Semaphore 로 import) |
| `pipeline/graph.py:50` | 118 (mapper_node 본문) | LangGraph 진입점 — BP cand_pool batch fetch + `asyncio.gather` + PG INSERT 3 종 (parser_reports / parser_activities / mapper_activities) |
| `pipeline/graph.py:170` | 18 | `_build_review_needed` — HIL 1 interrupt payload 빌더 |
| `pipeline/graph.py:191` | 32 | `_apply_corrections` — HIL 1 사용자 응답 → `user_corrected` 라벨 적용 |
| `pipeline/db.py:38` | 33 | `fetch_bp_candidates` — `(company)` → `list[(wa, l6_main)]` |
| `pipeline/db.py:106` | 40 | `fetch_l6_plan_mh_map` — N+1 회피용 단일 GROUP BY |
| `pipeline/db.py:639` | 127 | `insert_mapper_activities_batch` — 37 컬럼 INSERT + ON CONFLICT UPDATE (멱등) |
| `infra/postgres/migrations/2026-05-23_mapper_l7_5_columns.sql` | 8 | mapper_activities + 4 컬럼 ALTER |

mapper.py 본체 구성 (604 LOC):

- L24 ~ L45: `_WBS_MASTER_CACHE` + `_get_wbs_master_coll` (Chroma collection singleton, async Lock)
- L48 ~ L115: shift-weighted MH 산식 — `_SHIFT_WEIGHTS` / `_weighted_mh_from_shift` / `_prorate_workers_with_mh`
- L118 ~ L164: 시트2 직종 noise 필터 — keyword 상수 3종 + `_is_trade_job`
- L167 ~ L180: `WAResolution` dataclass (7 source Literal)
- L183 ~ L269: 4 helper — `build_embedding_input` / `build_bp_context` / `build_llm_input`
- L272 ~ L333: **`resolve_wa` 7단계 ladder** (0~6) — 본 시스템의 핵심
- L336 ~ L344: `_select_top_k_alternatives` (top-K=3 RAG 후보 → FE dropdown)
- L347 ~ L362: `MapperConfig` dataclass
- L365 ~ L526: **`map_activity` 6 단계 통합 흐름** (async, 162 LOC)
- L529 ~ L604: `_prorate_mh` — (company, l6_main) 단위 인원 + plan_mh propagate + cum_actual_mh 산출 (5 phase)

---

## 3. 6 단계 매핑 흐름 다이어그램

```
Parser 결과 ParsedDailyReport (activities: list[Activity])
        │
        ▼
graph.py:mapper_node  (LangGraph 진입점)
        │
        │ ① Pre-flight: normalize_company (㈜/(주) prefix 제거)
        │    for a in parsed["activities"]: a["company"] = normalize_company(...)
        │
        │ ② BP cand_pool batch fetch — 1 PG connection / N company
        │    unique_companies = {a["company"] for a in activities}
        │    for company in unique_companies:
        │        bp_cand_lookup[company] = await pg.fetch_bp_candidates(company)
        │                                = list[(wa, l6_main)]   ← activity_master DISTINCT
        │
        │ ③ asyncio.gather(*[_map_one(a) for a in activities])
        │    sem = asyncio.Semaphore(CPIA_MAPPER_CONCURRENCY, default=4)
        │            │
        │            ▼
        │     mapper.py:map_activity (async, 1 activity)
        │     ┌──────────────────────────────────────────────────────────────────┐
        │     │ Step ①  BP filter (cache lookup or PG fetch)                      │
        │     │         cand_pool = bp_cand_lookup[company]                       │
        │     │         cand_pool_set = set(cand_pool)                            │
        │     │                                                                   │
        │     │ Step ②  Embedding input — build_embedding_input(activity)         │
        │     │         "회사: X / 작업: Y / 단위: Z / 공종: W"                    │
        │     │         숫자 제외 (semantic distance 왜곡 방지)                    │
        │     │         emb = await asyncio.to_thread(                            │
        │     │             client.embeddings.create, model=embedding_model,      │
        │     │             input=[embed_text])                                   │
        │     │                                                                   │
        │     │ Step ③  Chroma Top-K — wbs_master collection (singleton)          │
        │     │         coll = await _get_wbs_master_coll(cfg)  ← async Lock      │
        │     │         result = coll.query(query_embeddings=[emb_vec],           │
        │     │                             n_results=top_k=15,                   │
        │     │                             include=[documents, metadatas,        │
        │     │                                      distances])                  │
        │     │         candidates = [                                            │
        │     │             {"key": (wa, l6_main),                                │
        │     │              "doc_text": ...,                                     │
        │     │              "is_bp_registered": key in cand_pool_set,            │
        │     │              "score": 1.0 - cosine_distance}                      │
        │     │             ... up to max_candidates=8                            │
        │     │         ]                                                         │
        │     │         if not candidates: → hil_required (Chroma 빈 결과 방어)   │
        │     │                                                                   │
        │     │ Step ④  LLM input — build_llm_input(activity, parsed_report)      │
        │     │         "회사: X / BP: PH_X-001 (공종 ...) / 작업: ... / 단위: ..." │
        │     │         + [BP사 단위 컨텍스트] (build_bp_context 호출)              │
        │     │                                                                   │
        │     │ Step ⑤  LLM 분류 — Azure gpt-5.1 (response_format=json_object)    │
        │     │         user_msg = "후보: [0] ★ ... / [1]   ... / ..."             │
        │     │         ★ = is_bp_registered (soft hint, 절대 기준 X)              │
        │     │         JSON 응답: {"choice": 2, "confidence": 0.85, "reason": "..."}│
        │     │         JSON 파싱 실패 / choice 범위 밖 / null → hil_required      │
        │     │         chosen_key = candidates[choice]["key"]  # (wa, l6_main)   │
        │     │                                                                   │
        │     │ Step ⑥  resolve_wa 7단계 ladder (다음 섹션 참조)                   │
        │     │         wa_result = resolve_wa(activity, l6_choice=chosen_key[1], │
        │     │                                cand_pool, parsed_report,          │
        │     │                                chosen_wa=chosen_key[0])           │
        │     │                                                                   │
        │     │ Return enriched Activity:                                         │
        │     │     wa = wa_result.value                                          │
        │     │     l6_main = chosen_key[1]                                       │
        │     │     mapping_source = wa_result.source                             │
        │     │     mapping_conf = confidence (LLM JSON)                          │
        │     │     requires_review = (conf < 0.7) OR (source == hil_required)   │
        │     │     alternatives = _select_top_k_alternatives(candidates, k=3)   │
        │     └──────────────────────────────────────────────────────────────────┘
        │
        │ ④ _prorate_mh(mapped, parsed_report, pg)  ← 다음 섹션 참조
        │     - assigned_workers (BP 총인원 × plan_mh 비율)
        │     - plan_mh propagate (activity_master.plan_mh_rev2)
        │     - cum_actual_mh_today (시간대 가중 MH × plan_mh 비율)
        │     - cum_workers_today (cum_actual_mh / 8.0)
        │
        │ ⑤ Post-prorate: normalize_company 1회 더 (방어)
        │
        │ ⑥ PG INSERT (run_id idempotent):
        │     pg.insert_parser_report(...)
        │     pg.insert_parser_activities_batch(...)
        │     pg.insert_parser_job_allocations_batch(...)       ← G24 (2026-05-19)
        │     pg.insert_parser_equipment_allocations_batch(...) ← G24
        │     pg.insert_mapper_activities_batch(...)            ← 37 컬럼
        │
        │ ⑦ verify SELECT (silent fail 진단):
        │     parser_reports / parser_activities / mapper_activities count print
        │
        ▼
    return {"mapped": mapped, "current_node": "mapper"}
        │
        ▼
graph.py:hil_1_node  (interrupt 발생 또는 AUTO_BYPASS)
```

---

## 4. resolve_wa 7 단계 walk-through (mapper.py:272-333)

`resolve_wa` 의 step 라벨은 `WAResolution.source` Literal 7 종으로 명문화돼있다. 코드 안 순서는 **(0) → 1 → 2 → 3 → 4 → 5 → 6** 으로 한 번 통과하며, 매칭된 첫 step 에서 즉시 return.

### Step 0 — `auto_chroma_top1` (BP master 미등록 BP사) — mapper.py:286-287

```python
# Task 4 — cand_pool 빈 시 (BP master 미등록) — Chroma 선택 결과 그대로
if not cand_pool:
    return WAResolution(value=chosen_wa, source="auto_chroma_top1")
```

- **조건**: `cand_pool` (activity_master 의 `(company)` → `(wa, l6_main)` DISTINCT) 가 비어 있음
- **동작**: LLM 이 선택한 candidate 의 `wa` 그대로 채택 (BP filter ∩ skip)
- **근거**: 사용자 명시 — "work_area + l6 가 주 매칭 키, BP 는 보조 메타데이터일 뿐"
- **신뢰도**: `mapping_conf` 가 `< 0.7` 이면 여전히 `requires_review=True`

### Step 1 — `auto_bp_zone_match` (BP-zone deterministic, fix C 2026-05-20) — mapper.py:294-299

```python
if parsed_report and activity.get("bp_code"):
    cand_wa_set = {wa for wa, _ in cand_pool}
    for s in parsed_report["bp_summaries"]:
        if s.get("bp_code") == activity["bp_code"] and s.get("zone"):
            if s["zone"] in cand_wa_set:
                return WAResolution(value=s["zone"], source="auto_bp_zone_match")
```

- **조건**: `activity.bp_code == BPSummary.bp_code` **AND** `BPSummary.zone in cand_pool 의 wa set`
- **동작**: BPSummary.zone (예: `FAB`) 그대로 채택 — LLM 선택 결과 (`chosen_wa`) 무관
- **예시**: 남웅건설 PH_X-001 (BPSummary.zone=FAB) → `cand_pool={(FAB, 철근콘크리트공사), (CUB, 철근콘크리트공사)}` 의 FAB 채택
- **근거**: 사용자 push back — "시트1 에서 FAB / CUB 알 수 있음"
- **검증 결과**: full cycle 5 (844d4c3) 에서 mapping_source `auto_bp_zone_match` 74% — 가장 흔한 source

### Step 2 — `auto_llm_rerank` (옵션 A 2026-05-20, LLM rerank fallback) — mapper.py:304-305

```python
if chosen_wa and (chosen_wa, l6_choice) in cand_pool:
    return WAResolution(value=chosen_wa, source="auto_llm_rerank")
```

- **조건**: LLM 이 선택한 `(chosen_wa, l6_choice)` 페어가 `cand_pool` 안에 있음
- **동작**: LLM 선택 그대로 채택
- **근거**: 사용자 push back — "scope ≠ wa, 오른쪽 작업으로 wa 판단" (LLM 의 work_content + bp_ctx 기반 판단 신뢰)
- **순서 이유**: BP-zone match 가 실패한 케이스 (한 회사가 여러 zone, bp_code 미상 등) 의 1차 fallback

### Step 3 — `auto_bp_single` (BP scope WA 단일) — mapper.py:308-310

```python
bp_wa = {wa for wa, _ in cand_pool}
if len(bp_wa) == 1:
    return WAResolution(value=next(iter(bp_wa)), source="auto_bp_single")
```

- **조건**: 그 BP사가 단 1개 zone 에서만 작업 (cand_pool 의 wa set 크기 = 1)
- **동작**: 그 단일 wa 채택
- **예시**: 어떤 BP사가 FAB 만 담당 → 모든 activity 의 wa=FAB

### Step 4 — `auto_l6_single` (L6 결정 후 그 L6 의 WA 단일) — mapper.py:313-315

```python
l6_wa = {wa for wa, l6 in cand_pool if l6 == l6_choice}
if len(l6_wa) == 1:
    return WAResolution(value=next(iter(l6_wa)), source="auto_l6_single")
```

- **조건**: LLM 이 선택한 `l6_choice` 의 WA 후보가 1개 (`l6` 고정 후 WA 좁힘)
- **예시**: BP사가 (FAB, 전기공사), (CUB, 전기공사), (FAB, 배관공사) 운영. LLM 이 `l6_choice=배관공사` 선택 → wa=FAB 자동

### Step 5 — `auto_sheet1_text` (회사 단위 zone 교집합) — mapper.py:321-330

```python
if parsed_report is not None:
    zones_in_sheet1 = {
        s["zone"]
        for s in parsed_report["bp_summaries"]
        if s["company"] == activity["company"] and s["zone"]
    }
    cand_wa_at_l6 = {wa for wa, l6 in cand_pool if l6 == l6_choice}
    intersect = zones_in_sheet1 & cand_wa_at_l6
    if len(intersect) == 1:
        return WAResolution(value=next(iter(intersect)), source="auto_sheet1_text")
```

- **조건**: 회사 단위 시트1 BPSummary.zone set ∩ `cand_pool` 의 `l6_choice` 의 wa set = 정확히 1개
- **근거**: 사용자 의도 — "1번 시트 내용에 CUB 인지 FAB 인지 알 수 있으니 매핑에 써야 함"
- **순서 이유**: Step 1 의 BP-zone 정확 매칭이 실패하고 (bp_code 미상 등) Step 4 도 실패 시 회사 단위로 후퇴

### Step 6 — `hil_required` (모든 ladder 실패) — mapper.py:333

```python
return WAResolution(value=None, source="hil_required")
```

- **동작**: `wa=None`, `requires_review=True` 보장 → HIL 1 dashboard modal 로 라우팅
- **목표**: 이 비율을 58% → 25% 이하로 (spec §0.2)
- **검증 결과**: full cycle 5 에서 `hil_required` 1.4% — 목표 25% 대비 양호 (단, POC 3사 데이터 한정)

추가로 `map_activity` 자체가 `requires_review = (confidence < cfg.conf_threshold) OR (wa_result.source == "hil_required")` 로 설정하므로, LLM confidence 가 `< 0.7` 이면 source 가 `auto_*` 여도 HIL 1 으로 라우팅된다.

---

## 5. `_weighted_mh_from_shift` — 시간대 가중 MH (mapper.py:52-69)

이전 8h 고정 prorate 의 root cause = EVM CPI = EV/AC 의 AC 분모 과소산정 → CPI 폭주. 산업안전공단 표준 가중치 적용으로 교체 (2026-05-16 commit 8089e7a).

```python
_SHIFT_WEIGHTS = {
    "morning": 2.0,     # 조출 (06:00~08:00 2h)
    "daytime": 8.0,     # 주간 (표준)
    "overtime": 4.0,    # 연장 (17:00~21:00 4h)
    "night": 8.0,       # 야간 (22:00~06:00 8h)
    "all_night": 12.0,  # 철야 (12h 연속)
}


def _weighted_mh_from_shift(shift_dict: dict | None) -> float:
    if not shift_dict:
        return 0.0
    return sum(float(shift_dict.get(k, 0) or 0) * w for k, w in _SHIFT_WEIGHTS.items())
```

- **Input**: `TimeShiftCounts` jsonb (state.py:17, 6 필드 morning/daytime/overtime/night/all_night/total)
- **Note**: `total` 키는 가중치 sum 에서 무시 — Parser 가 채워둔 sanity check 용
- **None / 빈 dict / 키 누락 → 0.0** (방어)

### 예시

```
shift_dict = {"daytime": 10, "overtime": 5, "night": 0, "all_night": 0, "morning": 2, "total": 17}
→ 10*8 + 5*4 + 0*8 + 0*12 + 2*2 = 80 + 20 + 0 + 0 + 4 = 104.0 MH

vs 이전 (8h 고정):
→ total (17) * 8 = 136 MH (과대 — 연장 4h 를 8h 처럼 카운트)
```

호출자는 `_prorate_workers_with_mh` 단 1곳. 시트2 의 `JobAllocation.workers_today_cum` 을 회사 단위로 합산할 때 사용.

---

## 6. `_prorate_workers_with_mh` — company 단위 가중 MH → l6 비례 분배 (mapper.py:72-115)

`_weighted_mh_from_shift` 의 유일한 caller. company 단위 weighted MH 총합을 그 회사가 활성인 l6_main bucket 들에 plan_mh 비율로 나눠준다.

```python
def _prorate_workers_with_mh(
    mapped: list[dict],
    parsed_report: dict,
    company_total_plan_mh: dict[str, float],
    active_l6_for_company: dict[str, set[str]],
) -> list[dict]:
    # phase A — company 단위 weighted MH 합산 (final_flag='O' 만)
    company_weighted_mh: dict[str, float] = {}
    for ja in parsed_report.get("job_allocations", []):
        if ja.get("final_flag") != "O":
            continue
        c = ja.get("company")
        if c:
            mh = _weighted_mh_from_shift(ja.get("workers_today_cum"))
            company_weighted_mh[c] = company_weighted_mh.get(c, 0.0) + mh

    # phase B — l6 단위 분배 (3 fallback)
    prorated = []
    for a in mapped:
        if a.get("l6_main"):
            c = a["company"]
            weighted_mh_c = company_weighted_mh.get(c, 0.0)
            company_mh = company_total_plan_mh.get(c, 0.0)
            plan_mh_val = float(a.get("plan_mh") or 0)
            n_l6 = len(active_l6_for_company.get(c, set())) if c else 0
            if company_mh > 0 and plan_mh_val > 0:
                cum_actual_mh = weighted_mh_c * (plan_mh_val / company_mh)
                prorate_method = "plan_mh"
            elif n_l6 > 0:
                cum_actual_mh = weighted_mh_c / n_l6
                prorate_method = "uniform_fallback"
            else:
                cum_actual_mh = 0.0
                prorate_method = "zero"
            a = {
                **a,
                "cum_actual_mh_today": cum_actual_mh,
                "cum_workers_today": cum_actual_mh / 8.0,
                "prorate_method": prorate_method,
            }
        prorated.append(a)
    return prorated
```

3 fallback path:

| method | 조건 | 산식 |
|---|---|---|
| `plan_mh` | `company_mh > 0 AND plan_mh > 0` | `weighted_mh_c × (plan_mh / company_mh)` |
| `uniform_fallback` | plan_mh 모름 (master miss) but `n_l6 > 0` | `weighted_mh_c / n_l6` |
| `zero` | `n_l6 = 0` (l6 매핑 자체 실패) | `0.0` |

### 예시

```
company = "남웅건설"
JobAllocation: 3 row (final_flag='O')
  - 형틀공: weighted_mh=104 (위 예시)
  - 철근공: weighted_mh=80  (10명 주간만)
  - 콘크리트공: weighted_mh=120
  → company_weighted_mh["남웅건설"] = 304

mapped 에서 남웅건설 l6 bucket 2개:
  - l6=철근콘크리트공사 (plan_mh=1200)
  - l6=거푸집공사       (plan_mh=800)
  → company_total_plan_mh = 2000

각 activity:
  철근콘크리트공사:  cum_actual_mh = 304 × (1200/2000) = 182.4
                    cum_workers_today = 182.4 / 8 = 22.8
                    prorate_method = "plan_mh"
  거푸집공사:        cum_actual_mh = 304 × (800/2000) = 121.6
                    cum_workers_today = 121.6 / 8 = 15.2
                    prorate_method = "plan_mh"
```

`cum_workers_today` 는 보조 표시 (FE 화면 — "오늘 환산 명-일") 일 뿐이고, EVM AC 의 진짜 source 는 `cum_actual_mh_today`.

---

## 7. `build_bp_context` — BP 코드별 분리 컨텍스트 (mapper.py:196-252)

LLM rerank (Step ⑤) 의 정확도를 좌우하는 가장 큰 helper. 한 회사가 여러 BP site (FAB + CUB 동시 운영) 를 갖고 있을 때, LLM 이 `work_content` 의 텍스트와 zone 을 매칭해 옳은 후보를 고르도록 정보 풍부화.

### 데이터 구조 (3 phase)

```
[시트1] BP 사이트별 작업 (작업 내용 보고 어느 BP 코드인지 판단):
      - PH_X-001 (zone=FAB): FAB F03 4F. PH1 패드천공 + 그라우팅 작업 ... [Incr 56명, Cum 150,565명-일]
      - PH_X-002 (zone=CUB): CUB 9층 엘리베이터 PIT 매트 콘크리트 ...     [Incr 24명, Cum 80,210명-일]

[시트2] 기능공 직종 (금일누계 Cum.T):
      - 형틀목공: 18,341명-일
      - 철근공:   12,103명-일
      - ... up to top-8 (_is_trade_job 필터)

[시트3] 투입 장비 (금일투입누계 Cum.T):
      - 굴착기/06W (PC200): 1,205회-일
      - 펌프카/콘크리트 (42m): 980회-일
      - ... up to top-5
```

### 이전 vs 신규 (dc69f14 2026-05-20)

| 항목 | 이전 (회사 단위 집계) | 신규 (BP 코드별 분리) |
|---|---|---|
| 시트1 출력 | "주요작업 (BP사 기재): FAB F03 / CUB 9층" 한 줄 join | BP code 1개 = 1 라인 + zone 명시 + 인원 |
| LLM 정확도 | FAB / CUB 모호 → wrong wa 선택 흔함 | bp_code + zone 명시 → step 2 (auto_llm_rerank) 정확도 ↑ |

### 시트2 직종 noise 필터 (`_is_trade_job`, mapper.py:158-164)

```python
def _is_trade_job(job: str) -> bool:
    if any(n in job for n in _NOISE_KEYWORDS):  # "기능공 투입 Total"
        return False
    if any(m in job for m in _MGR_KEYWORDS):    # 소장/관리자/감독/감리/안전/Shop/BIM/공무/설계/품질/운영/창고
        return False
    return any(k in job for k in _TRADE_KEYWORDS)
    # _TRADE_KEYWORDS (16개):
    # 형틀/철근/콘크리트/타설/조적/방수/도장/비계/용접/배관/전기공/덕트/단열/내장/타일/미장/양생/철골/보온/케이블
```

관리자 / 합계 row 제거 → top-8 정렬 정확도 보장 → LLM input quality 향상.

---

## 8. alternatives JSONB top-K (mapper.py:336-344, G23)

`_select_top_k_alternatives(candidates, k=3)` 가 `map_activity` Step ⑤ 직후 호출 — Chroma RAG candidates (max 8) 를 score 내림차순 정렬 후 상위 3 개 추출.

```python
def _select_top_k_alternatives(candidates, k=3):
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:k]
    return [{"wa": c["key"][0], "l6_main": c["key"][1], "score": float(c["score"])} for c in ranked]
```

### 출력 형식 (mapper_activities.alternatives jsonb)

```json
[
  {"wa": "FAB", "l6_main": "철근콘크리트공사", "score": 0.87},
  {"wa": "CUB", "l6_main": "철근콘크리트공사", "score": 0.82},
  {"wa": "FAB", "l6_main": "거푸집공사",       "score": 0.74}
]
```

### 어디서 어떻게 만들어지나

- **모델**: `text-embedding-3-small-ai-board-test` (Azure OpenAI, 1536d) — `cfg.embedding_model`
- **Collection**: ChromaDB HTTP `wbs_master` (1 doc = 1 WA + L6 그룹)
- **거리**: `hnsw:space=cosine` 으로 collection 생성됨 → `chroma_result["distances"]` 는 cosine distance → `score = 1.0 - distance` (실용 [0, 1])
- **n_results**: `cfg.top_k = 15` (config default) — Chroma 가 15 개 반환 후 `cfg.max_candidates = 8` 로 자름

### UI 활용

- `web/lib/transforms.ts` 의 BFF transform 이 mapper_activities.alternatives 를 읽어서 `MappingReviewModal.tsx` (HIL 1) 의 dropdown 옵션 source 로 사용
- HIL 1 사용자가 dropdown 에서 선택 → `corrections[idx] = {wa, l6_main}` payload → `_apply_corrections` 로 `mapping_source="user_corrected"`, `requires_review=False`

---

## 9. mapper_activities 37 컬럼 — 누가 어디서 채우나

2026-05-23 (commit d40c84f) 에 4 컬럼 추가 (`l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area`) → 33 → 37.

| 컬럼 그룹 | 컬럼 | 채우는 주체 |
|---|---|---|
| 키 | `run_id`, `report_date`, `idx` | mapper_node (`enumerate(activities)`) |
| 시트4 원천 | `company`, `trade`, `unit`, `today_qty` | Parser (parser.py 4 시트 추출) |
| 시트4 원천 | `plan_total_qty`, `yesterday_cum_qty`, `today_cum_qty`, `progress_percent`, `remaining_qty`, `remaining_percent`, `note` | Parser |
| 시트4 원천 | `zone`, `bp_code`, `scope` | Parser (`parser_post.split_company_and_zone`, `extract_zone`) |
| 업체별 일보 | `work_location_code`, `wbs_mid_name`, `wbs_sub_name`, `wbs_detail_name` | Parser (업체별 일보 시트4) |
| WBS 매핑 결과 | `wa`, `l6_main`, `mapping_conf`, `mapping_source`, `requires_review` | **Mapper** (`map_activity` return) |
| 분배 결과 | `assigned_workers`, `worker_source`, `plan_mh` | **Mapper** (`_prorate_mh`) |
| 분배 결과 | `cum_workers_today`, `cum_actual_mh_today` | **Mapper** (`_prorate_workers_with_mh`) |
| RAG | `alternatives` (jsonb) | **Mapper** (`_select_top_k_alternatives`) |
| Master propagate (2026-05-23) | `l5_disc`, `l7_sub`, `l7_5_activity`, `sub_work_area` | Parser (`l5_disc`) + activity_master propagate (`l7_sub` 외 3개는 PoC 단계 항상 None — Master List 1:N 제약) |
| conditions (시트4 비고 파싱) | `conditions` (jsonb list) | Parser (`atomizer` 도 keyword 파싱 의존) |

읽는 쪽:

- Atomizer: `wa`, `l6_main`, `today_qty`, `conditions`, `assigned_workers`, `cum_actual_mh_today` (Chroma daily_activities doc metadata)
- Forecaster: (`company`, `l6_main`, `wa`) bucket 단위 GROUP BY + RAG
- view_builder: 8 + 1 view jsonb 산출 (kpi/contractor_bars/quadrant 등)
- FE: alternatives, mapping_source, mapping_conf, requires_review (HIL 1 dropdown)

---

## 10. cum_workers_today vs mapped_history

mapper_activities 와 mapped_history 는 다른 목적의 테이블.

| 테이블 | 키 | 의미 | 단위 |
|---|---|---|---|
| `mapper_activities` | (run_id, idx) | 시트4 한 행 = 매핑 단위 row 보존 | 1 일 1 row / activity |
| `mapped_history` | (run_id, wa, l6_main, company) | (company, l6_main, wa) **bucket 단위 누적** | 1 row / bucket |
| Chroma `daily_activities` | doc_id | 1 doc = 1 activity (atomizer 적재) | 1 doc / activity |

`cum_workers_today` / `cum_actual_mh_today` (mapper_activities) 는 1 row 단위 — 같은 bucket 안 여러 row 가 같은 source weighted MH 의 plan_mh 비율 조각을 들고 있다 (sum 하면 그 bucket 의 weighted MH 가 됨).

`mapped_history` 는 atomizer/forecaster 가 (company, l6_main, wa) bucket 단위로 GROUP BY 처리할 때 사용. Mapper 가 직접 INSERT 하지 않고, 후속 노드가 mapper_activities 를 GROUP BY 해서 채운다 (graph.py 의 atomizer / forecaster 노드 책임).

---

## 11. LLM 호출 — 어디서, 어떤 모델

mapper.py 의 LLM 호출 단 2종:

| 호출 | 모델 | 단계 | 호출 조건 |
|---|---|---|---|
| `client.embeddings.create` | `text-embedding-3-small-ai-board-test` (1536d) | Step ② | **모든 activity 마다 1회** (필수) |
| `client.chat.completions.create` | `gpt-5.1-chat-ai-board-test` | Step ⑤ | **모든 activity 마다 1회** (필수, response_format=json_object) |

`resolve_wa` Step 2 (`auto_llm_rerank`) 의 "LLM rerank" 는 별도 LLM 호출이 **아니라** Step ⑤ 의 chat completion 결과 (`chosen_wa`, `l6_choice`) 를 재사용하는 것. 즉 1 activity 당 정확히 1 embedding + 1 chat 호출.

### 동시성 / Rate-limit

- `_concurrency.py` 의 `_MAPPER_CONCURRENCY` env (default 4) → `asyncio.Semaphore` 로 `_map_one` 4 동시 실행
- 모든 sync Azure SDK 호출은 `asyncio.to_thread(...)` 로 wrap — event loop block 회피
- Chroma client 는 `_WBS_MASTER_CACHE` + `asyncio.Lock` singleton — 매 activity 마다 새 conn 만들면 AWS Chroma `user_identity` 인증 timeout 발생 (2026-05-20 hang fix root cause)

---

## 12. HIL 1 까지의 경로

```
map_activity (mapper.py:365)
        │
        │ requires_review = (confidence < cfg.conf_threshold=0.7)
        │                OR (wa_result.source == "hil_required")
        │
        ▼
mapped: list[Activity] (각 a 에 requires_review 플래그 박힘)
        │
        ▼
mapper_node return {"mapped": mapped, "current_node": "mapper"}
        │
        ▼ graph edge: mapper → hil_1
        │
        ▼
graph.py:hil_1_node (graph.py:226)
        │
        │ mapped = state["mapped"]
        │ review_needed = _build_review_needed(mapped)   ← graph.py:170
        │                = [
        │                    {"idx": i,
        │                     "work_content": ..., "company": ..., "trade": ...,
        │                     "wa": ..., "l6_main": ...,
        │                     "mapping_conf": ..., "mapping_source": ...}
        │                    for i, a in enumerate(mapped) if a.get("requires_review")
        │                  ]
        │
        │ if not review_needed: → return {} (interrupt skip)
        │ if CPIA_HIL_AUTO_BYPASS env: → return {} (dev 모드)
        │
        │ corrections_raw = interrupt({"review_needed": review_needed})
        │         ↑ LangGraph interrupt → FastAPI /status 가 waiting_hil_1 반환
        │           → Next.js Dashboard polling 으로 감지
        │           → MappingReviewModal 띄움 → 사용자 선택
        │           → POST /api/hil/resume {corrections: {idx: {wa, l6_main}}}
        │           → FastAPI /api/runs/{id}/hil_1/resume
        │           → graph.invoke(Command(resume=corrections))
        │
        │ corrections = {int(k): v for k, v in corrections_raw.items()}
        │ corrected = _apply_corrections(mapped, corrections)
        │        ↑ graph.py:191 — 답한 row + 답 안 한 row 모두
        │          mapping_source="user_corrected", requires_review=False
        │
        │ (cfg != None && corrections != {}) →
        │     pg.insert_mapping_correction(...) for each corrected idx
        │
        ▼
return {"mapped": corrected, "hil_1_corrections": corrections, "current_node": "hil_1"}
        │
        ▼ atomizer → forecaster → hil_2 (auto-select) → optimizer → reporter
```

`_build_review_needed` (graph.py:170) 가 HIL 1 의 단일 진입 게이트. mapping_source 가 `hil_required` 이거나 `mapping_conf < 0.7` 인 모든 row 가 여기로 모인다.

---

## 13. 이슈 표

| ID | 영역 | 심각도 | 설명 | 다음 행동 |
|---|---|---|---|---|
| M-1 | 매핑 정확도 | M | `hil_required 58% → 25%` 목표는 spec §0.2 — full cycle 5 (POC 3사) 에서 1.4% 로 측정됐으나 데이터 편향 가능. V3 (146 case 전체 simulation) 검증 pending | 다음 cycle |
| M-2 | l7.5 propagate | M | `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 — mapper.py 자체에선 채우지 않음 (Parser + activity_master propagate 의존). PoC 단계 항상 None (Master List 1:N 제약) | activity_master 1:1 제약 정리 후 N+1 회피 fetch 통합 |
| M-3 | LLM null 처리 | L | mapper.py:493 — `choice is None or not (0 <= choice < len(candidates))` → 즉시 hil_required. LLM 이 "choice": null 응답할 때 (`response_format=json_object` 라도) 흔함. 별도 retry 없음 (PoC 의도) | Phase 2 — 1회 retry with same prompt 검토 |
| M-4 | Chroma cache key | L | `_WBS_MASTER_CACHE` key = `(host, port, ssl)` — DB 스왑 / collection 갱신 시 stale 가능. process 단위 cache 라 재시작으로 해결 가능 | 검토 보류 |
| M-5 | `assigned_workers` 와 `cum_workers_today` 의 의미 분기 | L | `assigned_workers` = BP 총인원 × plan_mh 비례 (단순 헤드카운트), `cum_workers_today` = 가중 MH / 8 (환산 명-일). 두 필드를 FE 가 혼동할 위험 | FE BFF transform 에 주석 추가 |
| M-6 | `_prorate_mh` 의 sequential await | L | mapper.py:557 — `for company, l6_set in bp_l6.items(): await pg.fetch_l6_plan_mh_map(...)` N+1. POC 규모 (3 BP사) 에서는 문제 없으나 10+ BP사 확장 시 슬로우 | 단일 GROUP BY 로 통합 가능 |
| M-7 | mapping_source `user_corrected` 의 출처 | L | 라벨이 mapper.py 가 아닌 graph.py `_apply_corrections` 에서만 생성됨. `WAResolution.source` Literal 에는 user_corrected 없음 (코멘트/문서에서만 언급) | 일관성 위해 Literal 확장 검토 |
| M-8 | Forecaster 의존 — wa propagate | M | forecasts.wa 컬럼 (2026-05-18 신규) 이 mapper_activities.wa 에 의존. resolve_wa 가 None 반환하면 forecast bucket 자체가 누락 가능 | full cycle E2E 검증 시 wa NULL row count 모니터링 |

---

## 14. 본 cycle 변경 요약 (ef7c6cd → 1ba783f)

| Commit | 변경 |
|---|---|
| `d40c84f` (2026-05-23) | `mapper_activities` 에 `l5_disc` / `l7_sub` / `l7_5_activity` / `sub_work_area` 4 컬럼 추가 (migration + db.py INSERT) — PoC 단계 대부분 None, Master List 1:N 정리 후 fill 예정 |
| (이전 cycle 흡수) | `8089e7a` `_weighted_mh_from_shift` + `_prorate_workers_with_mh` (8h 고정 → 시간대 가중), `dc69f14` `build_bp_context` BP별 + `resolve_wa` `auto_bp_zone_match` + `auto_llm_rerank`, `787575b` `test_mapper_resolve_wa.py` 10 case, `4cd36e3` `cum_workers prorate` |

mapper.py LOC delta: 571 (baseline) → 604 (HEAD, +33 LOC). 본 cycle 신규 commit `d40c84f` 자체는 mapper.py 가 아닌 db.py 변경. 33 LOC 증분은 baseline 직전 cycle 의 코멘트 정리 + asyncio.to_thread wrap 보강에서 발생.

---

*최종 수정: 2026-05-26 (1ba783f)*
