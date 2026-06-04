# CPIA Review l7.5 매핑 · 이력기반 HIL · 누적 뷰 설계

> 작성 2026-06-04 · 다중렌즈 리뷰(feasibility/coherence/scope/design) 반영 v2. 브레인스토밍 + 실 DB/코드/UI/PoC 전수조사 기반.
> 구현은 superpowers:writing-plans → subagent-driven-development. **실 코드 작업 첫 단계 = git pull 로 main 싱크.**

**Goal:** 작업일보 활동을 WBS 세부작업(l7.5)까지 매핑·적재하고, 그 l7.5 단위로 (1) review 우측 카드를 일별 나열 → **누적 통합**, (2) HIL 을 전건 → **신규/불확실 l7.5 만** 사람 검토로 전환. forecaster/optimizer/export 불변(l6+wa).

**제약 (디자인 불가침):** review/tasks 화면 layout/style/markup(.tsx 렌더 구조) 변경 금지. BE(파이프라인·SQL·API)·데이터·기존 필드값만. 조형준 프로 의도 보존.

---

## 0. 용어 · 실측 사실 (구현 전제 — 추측 아님)

WBS: `l5_disc(공종) > l6_main(중공종) > l7_sub(소공종) > l7_5_activity(세공종/작업단위) > wbs_activity_id(leaf)`. site=`m15x-ph3-ibl`. 스코프=건축/토목.

**마스터 카디널리티:** leaf 689 · distinct l7_5 **202** · l7_sub 35 · l6 17. l7.5 1종=leaf N개 (경량벽체 설치=101, 무근 콘크리트 타설=60). l7.5=작업단위 종류, leaf=위치 인스턴스(`wbs_activity_id` 코드로만 구분, `sub_work_area` 공백).

**실 DB 상태 (2026-06-04 검증):**
| 항목 | 값 |
|---|---|
| `mapper_activities.l75_conf` 컬럼 | **없음** (mapping_conf=l6 conf, l7_5_activity 텍스트만 존재) |
| requires_review | 시드(≤9/23)=**FALSE 70,719** · 9/24=**FALSE 171** · 9/25 라이브=**TRUE 115** |
| today_qty=0/NULL 행 | **0건** (시드·라이브 전부 >0) |
| mapping_source | 시드/9/24=`dummy_seed` · 9/25=`auto_llm_rerank` 112 + `hil_required` 3 |
| l7_5_activity 채움 | 시드+9/24=채움(clean 작업단위) · 9/25=**전부 NULL** |
| work_content | 시드+9/24=조건문("우천으로…") · 9/25=작업단위("석고벽체 설치") |
| 시드 l7.5 커버리지 | master 202 중 **199** (미수록 3: 레진 몰탈/2차 포장/2차 포장(표층)) |
| l6_main ↔ l5_disc | **1:1** (한 l6 가 건축·토목 양쪽에 안 걸침 — master·mapper 모두 0건 검증). → D8 불변식이 l5 차원 없이 `(wa, l6)` 키로 성립 |

→ **누적 필터 `requires_review=FALSE` 는 시드/9/24(=FALSE)를 모두 포함**, 9/25 미확정(TRUE)만 제외. 날짜기반 보정 불필요(검증됨). **today_qty=0 행이 없어** 좌/우 모집단 today_qty 불일치 문제 비발생(단 WHERE 는 글자단위 동일하게 고정).

---

## 1. 현재 상태 핵심 (코드 위치)

- **mapper l6 까지만:** `pipeline/agents/mapper.py` `map_activity`(L365~), `resolve_wa` 7단계, 반환 wa+l6_main(L524). l7_5_activity 정상경로 미적재. `requires_review=True` 하드코딩(L515-517).
- **INSERT:** `pipeline/db.py` `insert_mapper_activities_batch`(L670-733) 37컬럼 고정 — l75_conf/l7_5_alternatives 자리 없음.
- **state:** `pipeline/state.py` `Activity` TypedDict — l75_conf 필드 없음(mapping_conf=l6).
- **HIL:** `pipeline/graph.py` `hil_1_node`, `_build_review_needed`(L214-232), `_apply_corrections`(L235-267, c['wa']·c['l6_main']만), `insert_mapping_correction`(L313-333).
- **corrections 계약:** `pipeline/api.py` `CorrectionItem`(L45-49, wa·l6_main required, l7.5 없음). resume 프록시 `web/app/api/hil/resume/route.ts`. FE `web/app/(app)/review/page.tsx` handleRemap(L135-146)/handleConfirmAll(L158-163) → `{idx:{wa,l6_main}}`.
- **우측 누적:** `web/app/api/mock/review/registered/route.ts` — 개별행, `work_content` 렌더, `today_qty`(소수 미처리), wa 필수(L17, 400), `deriveWpIdAndPath(wa,l6)`(l6경로), ORDER started_at DESC LIMIT.
- **카드:** `web/app/components/review/ReviewCard.tsx` — `work_content`(L63-65), qty(L58-60), 경로(L69), conf(L74), 대안=**텍스트만 클릭핸들러 없음**(L78-82), `readOnly` 모드(L40-44). 수정=`WPSearchCombobox`(flattenWPs, l6 grain까지).
- **좌측:** `web/lib/transforms.ts` `wbsTreeBuild` — `active_l75`+`activity_agg`(L212-235) = 직전 세션 머지본 **leaf 686 역매핑**(activity_master JOIN, COUNT DISTINCT wbs_activity_id). `review_agg`(L199-211, requires_review=TRUE·today_qty>0·status='waiting_hil_1'). 트리 building>wa>(l5)>l6.
- **루트 빈화면:** `web/lib/review-node.ts` `nodeToQuery` building 분기 없음→null. `RegisteredQuery.wa:string`(non-null).

---

## 2. 핵심 설계 결정 (사용자 확정)

| # | 결정 |
|---|---|
| D1 | grain=l7.5. 누적 행·좌측 숫자 모두 l7.5 종류 기준. |
| D2 | 누적=Model A(읽기시점 SUM, 새 테이블 X). |
| D3 | 이력=시드 포함 과거 (l6,l7.5) EXISTS. |
| D4 | l7.5 매핑 mapper 신규, 적재+review 한정. forecaster/optimizer/export 불변. |
| D5 | mapper best-guess l7.5 항상 배정 + l75_conf 기록. 집 없으면 l7_5=NULL→"미분류". |
| D6 | HIL 게이트 = l7.5 NULL OR l75_conf<THRESHOLD OR NOT has_history. confident+이력→자동승인. |
| D7 | HIL UI = 데이터만. 경로에 l7.5, 대안=l7.5 후보. 확정/수정 기존 버튼. **마크업 0**. |
| D8 | 좌측 = l6 까지만 네비게이션. l6 노드 숫자 = 그 밑 활성 distinct l7.5 = 우측 누적 행 수(동일 WHERE 로 불변식 보장). 직전 686 leaf 지표 **폐기**(되돌림). |
| D9 | l7.5 사람 수정 = corrections 계약에 l7_5_activity 추가(전 경로 배선). l6 재매핑 시 l7_5→미분류. 사람 확정 미분류는 `mapping_source='user_corrected'` 로 재검토 면제. |

---

## 3. PoC 검증 (실 9/25 115건, gpt-5.1) — `tmp/poc_l75_pageindex.py`·`tmp/poc_cumulative_demo.py`

```
자동승인(confident l7.5 + 이력) 68건 59% / HIL(l7.5 못고름) 47건 41% / HIL 신규 0건
```
- 구체 work_content→l7.5 정확(conf 0.92~0.99): 기초 거푸집 설치→기초공사:거푸집 공사(0.99), 벽체 철근 조립→RC Wall:철근 조립(0.98). 순수 semantic(brittle 회피).
- 41% 두 원인: (A)희소·모호(철근 배근/도장/포장 — master에 집 있음) (B)master 미수록(비계/탈형/하지철물). 
- 누적 머지 실증: 매칭분 시드와 합산(기초공사:철근 콘크리트 타설 = 시드 137,161 + 라이브 735.2 = 137,896.2 m³). work_content fallback 은 시드 l7.5와 안 합쳐져 작업 분할 → **채택 안 함**, l7.5 그룹핑 확정.

---

## 4. 변경 (BE/데이터만)

### 4.0 스키마 마이그레이션 (신규 — 게이트의 입력 영속) ★blocker fix

신규 `infra/postgres/migrations/2026-06-04_mapper_l75_conf.sql`:
```sql
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l75_conf double precision;       -- l7.5 선정 신뢰도(0~1). mapping_conf(l6)와 별개.
ALTER TABLE mapper_activities ADD COLUMN IF NOT EXISTS l7_5_alternatives jsonb;          -- HIL 대안: l6 밑 l7.5 후보 top-K [{label, score}]
```
동반 수정 (마이그레이션만으론 미완):
- `pipeline/db.py` `insert_mapper_activities_batch`(L670-733): 컬럼 리스트·VALUES placeholder·`ON CONFLICT DO UPDATE SET`·튜플 바인딩 **4곳 모두**에 `l75_conf`, `l7_5_alternatives` 추가(현 37 → 39 param). `l7_5_alternatives` 는 jsonb → VALUES 에 `$N::jsonb` 캐스트 + 튜플에 `_json.dumps(a.get("l7_5_alternatives") or [], ensure_ascii=False)` (기존 conditions `$17::jsonb`/alternatives `$31::jsonb` 패턴 동일). `l75_conf` 는 double precision → `a.get("l75_conf")` 그대로. **ON CONFLICT SET 절에도 두 컬럼 추가**(resume 재upsert 시 NULL 덮어쓰기 방지 — `_apply_corrections` 의 `{**a}` spread 가 보존하나 SET 절 누락 시 갱신 안 됨).
- `pipeline/state.py` `Activity` TypedDict: `l75_conf: float | None`, `l7_5_alternatives: list[dict] | None` 추가.
- 컬럼 주석으로 mapping_conf(l6) vs l75_conf(l7.5) 구분 고정.

### 4.1 mapper l7.5 매핑 신규 (`pipeline/agents/mapper.py`) ★

`map_activity` 가 (wa, l6_main) 확정 후(L513 직후) 단계 추가:
1. **후보 맵 batch (run 1회):** activity별 l6 가 LLM 후 결정되므로 l6별 lazy fetch 대신 `mapper_node`(graph.py) 진입 시 1회 `SELECT l6_main, ARRAY_AGG(DISTINCT l7_5_activity) FROM activity_master WHERE site_id=? AND l5_disc IN ('건축','토목') AND l7_5_activity IS NOT NULL GROUP BY l6_main` → `{l6: [l7.5...]}` 맵 구성, `map_activity` 에 주입(기존 `bp_cand_lookup` 패턴). PG 활동별 재조회 회피.
2. **LLM 선정:** work_content+company+unit+l6+후보 → `{choice, confidence, reason}`. **★ choice 는 항상 0 이상(프롬프트에서 -1 금지) — D5 "항상 best-guess 배정".** 애매해도 최근접 후보를 고르고 confidence 로 확신도 표현. AzureOpenAI `llm_model`, json_object, `asyncio.to_thread` + Semaphore(기존 패턴).
3. **적재:** 후보 1개+ 면 항상 best-guess 배정 → `l7_5_activity=후보[choice 유효시 그 후보, 아니면 candidates[0]]`, `l75_conf=confidence`(낮으면 게이트가 HIL 로 보냄, 단 best-guess 표시), `l7_5_alternatives`=후보 top-5 `[{label,score}]`. **`l7_5_activity=NULL`(미분류)는 후보 0개(l6 밑 master l7.5 없음)일 때만.** (구 설계의 "choice=-1 → NULL" 은 실측서 미분류 41% 유발·D5 위반 → 폐기. 라이브 9/25: 미분류 0%, 자동 66/HIL 49.)
4. forecaster/optimizer/export/atomizer 쿼리 불변.

**성능:** 활동당 LLM 1→2회. 라이브 115건×2≈230 call, Semaphore(4) 흡수. mapper 소요 ~2배 가능 → §7 에서 실측해 데모 서사 대조. 시드 70k 는 이미 l7.5 보유 → **재매핑 안 함**(신규 run 만).

### 4.2 requires_review 이력 게이트 (`mapper.py` L515-517 교체 + `graph.py` mapper_node) ★

`requires_review=True` 하드코딩 제거 →
```
if mapping_source == "user_corrected":   # 사람이 이미 검토·확정(미분류 포함) → 재검토 면제 (D9)
    requires_review = False
else:
    requires_review = (l7_5_activity IS NULL)              # 미분류
                      OR (l75_conf < cfg.l75_conf_threshold)  # 불확실
                      OR (NOT has_history)                  # 신규 l7.5
```
- **THRESHOLD:** `MapperConfig.l75_conf_threshold: float = 0.7`, env `CPIA_L75_CONF_THRESHOLD` 오버라이드. (PoC 기준 0.7; §7 재측정 후 확정.)
- **has_history batch (run 1회, mapper_node):** `SELECT DISTINCT l6_main, l7_5_activity FROM mapper_activities WHERE site_id=? AND l7_5_activity IS NOT NULL AND l7_5_activity<>''` → set. (시드/9/24 가 requires_review=FALSE·l7.5 채움 → 199조합이 자연히 이력. 별도 시드플래그/날짜컷 불필요 — 실측 검증.) `has_history = (l6_main, l7_5_activity) ∈ set`.
- 자동승인분 requires_review=False, `mapping_source` 는 기존값 유지(예: auto_llm_rerank). HIL 분은 hil_1_node 그대로.

### 4.3 review 누적 뷰 — registered API (`web/app/api/mock/review/registered/route.ts`) ★

개별행 → l7.5 그룹 집계. **WHERE 절은 §4.6 좌측과 글자단위 동일(불변식 D8):**
```sql
-- 공통 WHERE (CANON): pr.site_id=${siteId} AND ma.is_mock=${useMock}
--   AND ma.l6_main IS NOT NULL AND ma.trade IN ('건축','토목') AND ma.requires_review=FALSE
--   AND (${wa}::text IS NULL OR ma.wa=${wa}) AND (${l6}::text IS NULL OR ma.l6_main=${l6})
--   AND (${l5}::text IS NULL OR ma.l5_disc=${l5})
SELECT ma.wa, ma.l6_main,
       COALESCE(NULLIF(ma.l7_5_activity,''),'미분류') AS l75_label,
       ROUND(SUM(ma.today_qty)::numeric,2) AS cum_qty,
       MAX(ma.unit) AS unit, COUNT(DISTINCT ma.company) AS company_n
FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
WHERE <CANON>
GROUP BY ma.wa, ma.l6_main, l75_label
ORDER BY cum_qty DESC
-- LIMIT 완전 제거. 집계 행은 (wa,l6,l75) 그룹수=활성 distinct l7.5(~199~202)라 절단 위험 없음.
-- 기존 route.ts 의 limit 파라미터(?? 500, max 1000) 폐기 — 절단되면 좌측 카운트와 D8 불변식 깨짐.
```
ReviewItem 매핑:
- `id` ← 합성 `reg-${wa}-${l6_main}-${l75_label}` (집계엔 ma.id 없음). `idx` ← -1(집계 무의미).
- `work_content` ← **l75_label** (카드 따옴표 = 작업단위. 시드 조건문 자동 해소).
- `quantity` ← cum_qty(누적합 2자리). `unit` ← unit.
- `bp_name` ← company_n>1 ? `"${company_n}개사"` : 단일 업체명.
- `ai_mapped_path` ← `deriveWpIdAndPath(wa,l6,siteName)` + `" > " + l75_label`.
- `confidence` ← 1.0(readOnly 등록행). `status="confirmed"`, `alternative_wps=[]`.

**합성 id 호환:** readOnly 모드(onlyUnconfirmed=false)에서 selection/connector/groupCardsByWp 가 새 id 로 동작 확인(§7). groupCardsByWp 는 ai_mapped_wp_id(l6) 기준이라 한 l6 의 여러 l7.5 행이 한 WP 그룹에 묶임 — 의도대로.

### 4.4 HIL 카드 l7.5 노출 (HIL 데이터 경로, 데이터만)

requires_review=TRUE 항목 ReviewItem:
- `ai_mapped_path` += best-guess l7.5 또는 "미분류".
- `alternative_wps` ← `mapper_activities.l7_5_alternatives`(§4.0/§4.1, [{label,score}]). **shape rename 필수:** `ReviewCard.tsx:80` 이 `a.path.split(" > ").pop()` 와 `a.score` 를 읽고 `types.ts:153 alternative_wps?:{id,path,score}[]` 이므로, `{label,score}` → `{id:<l7.5 slug>, path:label, score}` 로 변환해 주입(throw 회피, `.pop()` 가 path=label 의 마지막 토큰=label 표시). 카드 마크업(L78-82) 불변.
- 확정 = best-guess l7.5 수락(이미 행에 적재됨 → requires_review=False 만 플립, l7.5 유지). 수정 = §4.7.

### 4.5 루트 노드 전체 표시 (3파일 연쇄) ★

- `web/lib/review-node.ts`: `RegisteredQuery.wa: string | null`. `nodeToQuery` 에 `if(node.type==="building") return {wa:null,l5:null,l6:null};`.
- `web/app/(app)/review/page.tsx`(L62): 현재 코드는 `const params = new URLSearchParams({ wa: q.wa });` — wa null 이면 `"null"` 문자열로 직렬화돼 버그. **이를 `const params=new URLSearchParams(); if(q.wa) params.set("wa",q.wa); if(q.l5) params.set("l5",q.l5); if(q.l6) params.set("l6",q.l6);` 로 교체** (wa null 이면 키 자체 생략 — FE 직렬화 시점에서 'null' 문자열 차단). `RegisteredQuery.wa: string|null` 변경 시 기존 trade/work_package 분기(:11,:16,:18)는 여전히 non-null wa 반환(building 분기만 null) — 타입 호환 OK.
- `registered/route.ts`(L17): `if(!wa) 400` **제거**. `const wa = url.searchParams.get("wa")` 가 없으면 SQL 에 `null` 바인딩 → `(${wa}::text IS NULL OR ma.wa=${wa})` 가 전체집계. 빈문자 가드: `wa===""||wa==="null"` → null 취급.
- 회귀: building 클릭 → 우측 비어있지 않음(§7).

### 4.6 좌측 카드 숫자 = 활성 distinct l7.5 (`web/lib/transforms.ts` wbsTreeBuild) ★

**직전 세션 686 leaf 지표 폐기**(2026-06-03 머지 `b492ac4`, MEMORY `cpia_review_card_leaf_metric` 되돌림 — 조형준 프로 확인 가능하게 명시). `active_l75`+`activity_agg`(L212-235, activity_master JOIN 역매핑) 삭제 → 단순 교체:
```sql
activity_agg AS (
  SELECT ma.wa, ma.l6_main,
         COUNT(DISTINCT COALESCE(NULLIF(ma.l7_5_activity,''),'미분류')) AS total_count
  FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id)
  WHERE <CANON 과 동일: site_id, is_mock, l6_main NOT NULL, trade IN('건축','토목'), requires_review=FALSE>
  GROUP BY ma.wa, ma.l6_main
)
```
- l6 노드 숫자 = distinct 활성 l7.5(미분류 포함 1버킷) = 우측 §4.3 행수와 **정확히 일치**(WHERE 동일·미분류 동일 COALESCE).
- 트리 building>wa>(l5)>l6 그대로(l7.5 레벨 미추가 — 사용자 D8). 자식 합 롤업 유지. `review_agg`(검토대기 AlertCircle) 그대로.
- before/after 카운트 검증(§7): 686 leaf → distinct l7.5(~199~202 활성).

### 4.7 l7.5 사람 수정 계약 (전 경로 배선, descope 아님) ★blocker fix

- `pipeline/api.py` `CorrectionItem`: `l7_5_activity: Optional[str] = None` 추가(back-compat, 기존 {wa,l6_main} 유지).
- `pipeline/graph.py` `_apply_corrections`(L251-263): `c` 에 `l7_5_activity` 있으면 `a["l7_5_activity"]=c["l7_5_activity"]`. **l6 가 바뀌었는데 l7.5 미지정이면 `a["l7_5_activity"]=None`(미분류)** — 옛 l6 의 l7.5 무효화. `requires_review=False`, `mapping_source="user_corrected"`.
- `insert_mapping_correction`(L313-333): l7_5_activity 컬럼 동반 영속(mapping_corrections 스키마 확장).
- FE `page.tsx` handleRemap/handleConfirmAll: corrections payload 타입에 `l7_5_activity?: string|null` 4번째 채널 추가(`handleRemap` 시그니처 확장, 마크업 불변).
- **FE 입력 결정 (디자인 불가침 제약하 확정):** 직접 l7.5 교체(특정 l7.5 지정)는 combobox 에 l7.5 엔트리 추가 또는 대안 클릭핸들러가 필요한데 **둘 다 마크업/상호작용 변경 → 이번 세션 FE 미제공.** 대신 마크업 불변으로 가능한 두 동작만:
  - **확정** = best-guess l7.5 수락. payload 에 l7.5 안 보냄 → 행에 이미 적재된 mapper l7.5 유지, requires_review=False.
  - **수정**(기존 combobox, l6 grain) = l6 재매핑. payload `{wa,l6_main, l7_5_activity:null}` → 옛 l6 의 l7.5 무효화 → **미분류** + `mapping_source="user_corrected"`.
  - **BE 계약은 완비**(CorrectionItem.l7_5_activity, _apply_corrections, insert_mapping_correction) → 추후 마크업 허용 시 l7.5 picker 만 얹으면 즉시 동작. wp_id 인코딩(`safe(wa)-safe(l6)`)과 충돌 않도록 l7_5 는 payload 별도 필드(combobox 의 newWpId 에 인코딩 X).
- **미분류 종결(D9):** 사람이 "미분류 그대로 확정" → requires_review=False + `mapping_source="user_corrected"`. §4.2 게이트의 `l7_5 IS NULL → 검토` 조건에 **`AND mapping_source <> 'user_corrected'` 예외** 추가 → 재검토 무한루프 방지. 미분류는 좌측 distinct·우측 누적에 "미분류" 1버킷으로 계상.

### 4.8 누적 41% 과소표시 인지 신호 (기존 슬롯 재사용, 데이터만) ★design fix

누적은 requires_review=FALSE(자동승인/확정)만 → 검토대기분 누락이 "확정된 사실"로 오인될 수 있음. 마크업 불변 위해 **기존 텍스트 슬롯 재사용**: `page.tsx` 의 기존 "총 X건 중 Y건" 패턴(L251 류)/`registeredTotal` 또는 `review_agg` 검토대기 카운트를 활용해 "확정 N · 검토대기 M" 를 기존 문구 자리에 데이터로 노출. 새 배지/마크업 추가 금지. (정확한 슬롯은 §7 구현 시 page.tsx 기존 분기 확인 후 확정.)

---

## 5. 데이터 흐름 (라이브 run)

```
parser → mapper:
  (wa,l6) [기존] → l7.5 best-guess + l75_conf + l7_5_alternatives [§4.1]
  → requires_review = NULL OR conf<THRESH OR NOT has_history [§4.2]
  → mapper_activities 적재(l7_5_activity, l75_conf, l7_5_alternatives, requires_review) [§4.0 컬럼]
hil_1_node: requires_review=TRUE 만 interrupt → HIL 카드(경로 l7.5, 대안=l7_5_alternatives) [§4.4]
  확정=l7.5 수락(flip False) / 수정=l7.5 또는 l6 재배정(corrections+l7_5) [§4.7] → 재영속
review 화면:
  좌측(l6 노드=활성 distinct l7.5, CANON WHERE) [§4.6]
  노드클릭→registered GROUP BY l7.5 SUM 2자리(CANON WHERE) [§4.3]  루트→wa NULL 전체 [§4.5]
  확정N·검토대기M 신호(기존 슬롯) [§4.8]
forecaster/optimizer/exporter: 불변
```

---

## 6. 엣지 케이스 · 한계

- **누적 collapse=confident만.** 검토대기분은 requires_review=FALSE 필터로 좌/우 제외(§4.8 로 인지신호). 확정 시 합류.
- **(B) master 미수록:** l7_5=NULL→"미분류"+HIL. 사람 확정 시 user_corrected 로 종결(재검토 면제, D9).
- **work_content 변이("철근 배근"vs"철근배근"):** l7.5로 묶이면 해소. 미분류로 빠지면 변이 잔존(소수).
- **l6 오매핑(비계 under 외장판넬):** l6 불변 → l7.5 실패 → HIL → 사람이 l6 재매핑(l7.5→미분류) 또는 미분류 확정.
- **라이브 직후 0건:** 9/25 신규 l7.5 가 전부 requires_review=TRUE 면 그 l6 좌측=0·우측 0행(시드 없는 신규 l7.5). empty-state 문구는 기존 page.tsx 분기 재사용, "활동 없음" vs "전부 검토대기" 구분 표기(§4.8 신호로).
- **THRESHOLD·프롬프트 튜닝:** 자동/HIL 비율 의존 → 구현 후 실 9/25 재측정해 데모 서사("1년 학습→~59% 자동·~41% 검토")에 맞게 조정.

---

## 7. 테스트 (드라이 테스트: LLM 매칭 고정, 결정론 코드 검증)

- **§4.0 마이그레이션:** l75_conf/l7_5_alternatives 컬럼 존재 + db.py INSERT 39-param 라운드트립(적재→재조회 동일).
- **§4.1 l7.5 선정:** golden(work_content→기대 l7.5) 적재 결정성(choice→l7_5_activity, -1→NULL, l75_conf 저장, alternatives top-5). 후보맵 batch 정확성.
- **§4.2 게이트:** 이력 set·l75_conf·null 입력 고정 → 3분기 전수(시드 l7.5=이력O=자동, 미수록=HIL, conf<0.7=HIL, user_corrected 미분류=면제). THRESHOLD parametrize(high=전건자동/low=전건HIL/mid=mixed).
- **§4.3 누적:** 픽스처(동일 l7.5 일별 N행) → SUM·ROUND 2자리·GROUP·미분류 버킷·루트(wa NULL)·합성 id·LIMIT 미절단. 시드 합류(137,161+735.2=137,896.2). **시드 requires_review=FALSE 확인된 값으로 픽스처.**
- **§4.6 좌측:** **D8 불변식 `좌측 l6 distinct == 우측 누적 행수`** (CANON WHERE 동일·미분류 동일). 686 leaf→distinct l7.5 before/after. 롤업(wa=Σl6, root=Σwa). today_qty=0 픽스처 포함(현 0건이나 회귀 방지). **l6↔l5 1:1 검증됨(§0)** 이라 GROUP BY 에 l5 차원 불요 — 단 회귀로 'l6 가 두 l5 에 걸치면 깨짐' 픽스처 1건 추가(미래 데이터 방어).
- **§4.5 루트:** building 클릭 → 우측 비어있지 않음. wa 빈문자/'null'/생략 직렬화 가드.
- **§4.7 수정:** corrections {wa,l6,l7_5} 라운드트립, l6 변경 시 l7.5→미분류, user_corrected 재검토 면제. combobox l7.5 후보 주입(또는 폴백) 동작.
- **불변 회귀:** forecaster/optimizer/exporter 출력 해시 동일(l7.5 추가 영향 0).
- **selection/connector:** readOnly 합성 id 로 카드 선택·연결선 정상.

---

## 8. 디자인 불가침 준수

변경: `infra/postgres/migrations/*`(신규 DDL) · `pipeline/agents/mapper.py`·`pipeline/graph.py`·`pipeline/db.py`·`pipeline/state.py`·`pipeline/api.py`(BE) · `web/app/api/mock/review/registered/route.ts`·HIL 데이터 경로(SQL/필드값) · `web/lib/review-node.ts`·`web/lib/transforms.ts`(SQL/분기) · `web/app/(app)/review/page.tsx`(corrections payload·param·기존 슬롯 텍스트, 마크업 불변) · `WPSearchCombobox` 후보 소스(데이터). **.tsx 렌더 마크업(ReviewCard/WBSTree 구조) 변경 0.** §4.7 combobox 후보 주입이 마크업을 요구하면 폴백(§4.7).

---

## 9. 구현 순서 (writing-plans 입력)

0. **git pull → main 싱크** (실 코드 작업 전 필수). A_Track/B_Track 최신 반영.
1. §4.0 마이그레이션 + db.py + state.py (토대 컬럼).
2. §4.1 mapper l7.5 매핑 적재 + l7_5_alternatives.
3. §4.2 requires_review 이력 게이트 + THRESHOLD config.
4. §4.3+§4.5 registered 누적 API + 루트.
5. §4.6 좌측 distinct l7.5(686 폐기).
6. §4.4 HIL 카드 l7.5 노출.
7. §4.7 l7.5 수정 계약.
8. §4.8 인지 신호.
9. §7 드라이 테스트 + 실 9/25 재측정(자동/HIL 비율, mapper 소요).
