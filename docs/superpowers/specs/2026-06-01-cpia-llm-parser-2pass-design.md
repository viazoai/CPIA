# CPIA LLM Parser — 헤더 recipe 2-pass 로 N종 업체양식 흡수 (독립 모듈, 데모 후 prod 융합)

- 작성일: 2026-06-01
- 상태: 설계 합의 완료, 구현 대기
- 관련 세션: 다른 세션의 `2026-06-01-cpia-parser-header-based-multiformat-design.md` (데모용 결정론 단일양식) 의 §2.2 비목표 "N종 제각각 양식 → LLM 2-pass 인식 레이어" 를 본 문서가 이어받음
- 대상: post-demo 프로덕션 하드닝 (데모 6/5 동결 이후 prod 융합)
- 산출 모듈(예정): `pipeline/agents/parser_recipe.py` (독립), `data/parser_recipes/` (캐시), `scripts/synth_formats.py` (합성 corpus), `pipeline/tests/test_parser_recipe.py`
- 데이터 계약(불변): `pipeline/state.py:207` `ParsedDailyReport`

---

## 1. 배경 — 왜 다시 LLM parser 인가

워크플로: 여러 업체가 각자 양식의 작업일보를 제출 → parser 가 각 파일을 **통합 작업일보 스키마(`ParsedDailyReport`)** 로 정규화 → exporter 가 같은 현장·같은 날의 모든 run 을 행 단위 합집합으로 묶어 1개 통합 작업일보 출력. 즉 parser 의 임무는 **"a, b, c... 업체양식 → 단일 스키마"** 정규화이며, "여러 업체 → 1 통합" 합치기는 이미 exporter(`exporter.py:37-97`, `WHERE site_id AND report_date`)가 수행한다.

### 1.1 실측으로 확정한 현실 (추측 아님)

- **디스크상 양식은 2종뿐**: 통합 1 + 업체 1(중원엔지니어링, `docs/sample/`). 데모 `data/demo_inputs/20250925/` 10개는 전부 중원 템플릿의 바이트 동일 복제본(확장자 .xlsx 7 / .xlsm 3, 파일명만 다름). "다른 업체양식"은 디스크에 없다.
- **이미 full-LLM parser 를 만들었다 폐기**: `parser_llm.py` (660 LOC, 2026-05-19 신설 → 2026-05-20 DEPRECATED). 시트당 chunk LLM = 270 호출 × 4~5분 × ~$3/cycle → 6/5 시연 마감 압력에 못 버텨 rule+검증 hybrid(~20초/$0.55)로 교체. **"비싸고 검증 안 되는 LLM"이 본 설계가 피해야 할 함정**이다.
- **업체양식은 자기서술적**: 업체파일 10시트에 `Code`(직종/장비/공종 마스터), `WBS`(대/중/소/세공종), `작성 방법`(양식 설명) 시트를 품는다. 헤더가 풍부(`구분/Zone/공종/BP사/Scope/대표물량_작업 내용/금일실적` 등)해 recipe 를 대부분 결정론으로 만들 수 있다.

### 1.2 타깃은 P1 (같은 시스템 내 변이)

근시일 들어올 "다른 업체양식"은 주로 **P1 = 같은 발주처(M15X IBL) 표준 양식을 쓰되 업체마다 컬럼 시프트·헤더 표현·시트명이 약간 다른** 경우다. 전혀 다른 건설사의 자체 엑셀(**P2 = 외래 템플릿**, 시트 구성·행 의미가 근본적으로 다름)은 검증할 실샘플이 없어 본 설계의 빌드 대상이 아니다(speculative abstraction 금지). P2 는 안전망(loud-fail + 리뷰)으로만 처리한다.

---

## 2. 스코프

### 2.1 이번 스코프
- 통합 양식 + 업체 양식(P1 변이 포함)을 **같은 코드 경로**로 `ParsedDailyReport` 로 정규화하는 **독립 모듈**.
- 헤더 텍스트 해석 기반 **recipe(Pass 1)** + 결정론 추출(Pass 2) + 안전망.
- P1 변이를 검증할 **합성 adversarial corpus** + 결정성 검증 하네스.
- 데모 후 prod 융합을 위한 feature-flag 진입점 (`ParsedDailyReport` 계약 동일).

### 2.2 비목표 (speculative abstraction 금지)
- **P2 외래 템플릿용 구조 recipe DSL** (행 시작·그룹 경계·게이트까지 LLM 이 declarative 로 기술). 검증할 실샘플 없음 → 만들지 않는다. P2 는 안전망으로만.
- **full-LLM 셀 추출**(`parser_llm.py` 부활). 폐기 이유 그대로 유효.
- **데모 기간 prod 경로 수정**. 본 모듈은 데모 동안 live graph/`parser_node`/`parser.py` 와 완전 격리.
- ② 작업사항 줄바꿈 → N행 분리: 불필요(아래 §4.2).
- ③ 인원·장비 activity 단위 재분배: parser 책임 아님(아래 §4.3).
- sheet1 zero-today 업체 누락(통합 99/159) 수정: by-design, 안 건드림(아래 §4.4).

---

## 3. 설계 — 헤더 recipe 2-pass

### 3.1 핵심 원리

양식이 어긋나는 층위는 실측상 4가지다:

| 층위 | 예시 | 현 결정론이 잡나 |
|---|---|---|
| ① 컬럼 위치 | '업체명' 컬럼 유무로 1칸 시프트 | sheet4 만(`_resolve_sheet4_columns`) |
| ② 헤더 동의어 | `금일실적` vs `당일실적` vs `Today Actual` | 동의어 테이블에 있으면 |
| ③ 시트 정체/순서 | 물량을 2번 시트에 "수량집계"로 | ❌ 시트명 하드코딩(`wb["4.물량"]`, `parser.py:648-651`) |
| ④ 행 구조 의미 | `Mm01` 앵커, col30 병합 경계, `final_flag='O'` 게이트, 2단 헤더, 시간대 6칸 블록 | ❌ 절대 컬럼 하드코딩 |

LLM 의 야망은 **②③(의미 매핑)만**. ④ 행 구조 휴리스틱은 결정론으로 유지하되 "어느 컬럼/신호로 잡나"만 recipe 가 결정. P2 외래 행구조는 안전망.

### 3.2 `FormatRecipe` (Pass 1 산출물 = 캐시 단위)

```
FormatRecipe
  fingerprint      sha256(정렬 시트명 + 시트별 정규화 헤더텍스트)
  format_class     "통합" | "업체" | "unknown"
  sheets           { role -> SheetRecipe }     role in {bp_summary, job, equip, activity, worker, meta}
  generated_by     "deterministic" | "llm" | "human"
  confidence       float (0~1)

SheetRecipe
  sheet_name       실제 워크북 시트명
  columns          { schema_field -> col_index }      # 헤더텍스트 해석 결과
  timeshift_blocks { block_name -> col_start }         # 조출/주간/연장/야간/철야/Total 6칸 블록 시작
  group_boundary   "mm01_anchor" | "col30_merge" | "bp_company_pair"
  header_rows      [int, int]                          # 2단 스택 헤더 (예: 통합 sheet4 = row3+row4)
  final_flag_col   int | None                          # 'O' 게이트 컬럼(있으면), 없으면 None -> 게이트 우회
```

### 3.3 Pass 1 — 3-tier ladder (결정론 우선, LLM 최소)

- **Tier 1 결정론**: 시트명 alias + 헤더 동의어 테이블로 `SheetRecipe` 채움. P1 same-family 는 헤더가 풍부해 **대부분 LLM 0콜·$0**. `_resolve_sheet4_columns`(`parser.py:357`)의 헤더해석 패턴을 sheet1/2/3 + 시간대 6칸 블록(조출/주간/.../Total 라벨로 block_start 발견)으로 확장.
- **Tier 2 LLM fallback (miss 시에만)**: 못 푼 시트역할 / 헤더필드만 — **시트명 + 헤더 row 만(~수백 토큰)** 을 Azure `gpt-5.1-chat-ai-board-test` 에 보내 빈칸 채움 → `data/parser_recipes/<fingerprint>.json` 캐시. 같은 양식 2번째 파일부터 캐시 hit → 다시 $0. (전체 셀이 아니라 헤더만 보내므로 `parser_llm.py` 의 150K 토큰/270콜 함정 구조적 회피.)
- **Tier 3 안전망**: `confidence < θ` or 필수필드 미매핑 or `group_boundary=unknown` → `ParseError`(명확한 진단 메시지) + 부분 recipe 방출 + 리뷰 큐. **조용한 오염 0** (issue #52 의 act=33 bp=1 job=0 같은 silent corruption 금지).
  - **`confidence` 산식(결정론·테스트 가능)**: `confidence = (매핑된 필수필드 수 / 전체 필수필드 수)`. Tier 1 결정론이 모든 필수필드를 동의어 테이블로 채우면 `1.0`(LLM 0콜). LLM 이 채운 필드는 `min(1.0, 모델 보고 confidence)` 로 가중. `θ` 초기값 = `1.0`(필수필드 1개라도 미매핑이면 즉시 안전망) — PoC 보수값, 합성 corpus 통과 후 완화 검토. 필수필드 집합 = 각 role 별 최소 추출 필드(예 activity: work_content/unit/today_qty/trade/bp/company). 같은 입력 2회 → 동일 confidence(§5.3).

### 3.4 Pass 2 — 결정론 추출 (LLM 없음, 매 파일)

기존 `parser.py` 의 `_parse_sheet1/2/3/4` 휴리스틱을 **recipe 파라미터화로 포팅**. 하드코딩된 컬럼·시트핸들·시간대 오프셋·group_boundary 신호를 `SheetRecipe` 주입으로 교체. **④ 행 휴리스틱 자체(col30 병합 경계, Mm01 앵커, BP·회사 교대행, final_flag 조건부 게이트, admin 직종 filter, placeholder skip)는 보존**.

> **재작성 금지 (hard lesson)**: 다른 세션 spec §3.2b/§4.4 — 시트1/2/3 을 단순 재작성하니 통합이 bp 99→159 / job 975→11836 / eq 1111→12437 로 폭증. 기존 group 경계·placeholder skip·admin filter 를 보존해야 회귀가 안전. 본 모듈은 "포팅(컬럼 주입)"이지 "재작성"이 아니다.

### 3.5 데이터 계약 (불변)

산출은 `ParsedDailyReport`(`state.py:207`) 그대로. `Activity`/`BPSummary`/`JobAllocation`/`EquipmentAllocation`/`WorkerOutput`/`ReportMeta` 필드 변경 0. mapper·atomizer·exporter·forecaster 무수정. 따라서 데모 후 융합이 feature-flag 한 줄로 가능.

---

## 4. 사용자 제기 4 이슈 — 실데이터 판정과 착지

(전수 프로브 2026-06-01: `docs/sample/` 실파일 + `parser.py` 교차참조로 검증)

### 4.1 ① BP코드 ↔ 업체명 분리·통일

- **실측**: 현 파일(통합·업체)은 코드↔회사 분리 정상(`bp_code='M15X_PH4_041'`, `company='중원엔지니어링'`). 누출은 **코드 변종에서만**: `M15X-PH4-041`(dash)·`M15X_PH4_041A`(suffix)·`ABC-2025-001`(외래) → `_is_bp_code`(`parser.py:103`) miss → `elif v5: company_raw=v5`(`parser.py:197`) 폴스루로 코드가 회사명 누출.
- **company SSOT = 셀(`협력업체` 컬럼)** — 프로덕션 정답(업체가 자기 회사명을 채우는 칸). 파일명은 신뢰 불가.
- **파일명 ≠ 셀 company → `requires_review=True`** — 묵살 금지. 클론 실패모드(데모 10개: 파일명 10업체 distinct vs 셀 전부 중원)와 "남 템플릿 재사용"을 둘 다 잡는 신호.
- **착지(결정론)**: BP regex 를 dash/공백 구분자 + 선택적 trailing suffix 흡수로 확장(과확장 금지, 변종 fixture 동반). **누출 가드**: `elif v5` 에서 company 배정 전, "코드처럼 보이는데 한글 0글자"(전부 ASCII+숫자+구분자)면 company 금지·`requires_review` 격리.
- **착지(좁은 LLM, 옵션)**: 리뷰 큐에서 (i) 한글 없는 토큰이 코드냐 영문회사명(`Hyundai E&C`)이냐, (ii) 파일명/셀 불일치 진실 판정. 격리된 토큰만 넘겨 비용 최소.
- **데모 데이터(demo-prep, parser 밖) — 추적 대상 외부 의존성**: 10 클론의 셀 `협력업체` 를 실제 업체명으로 교정해야 forecaster/atomizer(company-key)에서 10업체가 distinct. 본 모듈은 "셀이 진실" 가정. **이 교정은 본 모듈 산출물이 아니므로 plan 의 외부 의존성 항목으로 명시 추적**(데모-prep 과 본 모듈 사이에서 누락 방지). 미교정 시 셀-SSOT 로 10업체가 중원 1개로 붕괴.

### 4.2 ② 작업사항 줄바꿈 → N행 분리 — **무작업**

- **실측**: 수량 있는 작업은 sheet4(물량)에 이미 1행=1작업=1수량으로 분해(PCW20/PCW20(SCR)/NPW/RO..., 업체 33 Activity, 개행 0건). 줄바꿈은 sheet1(작업사항) 텍스트에만 존재하고 거기엔 **수량이 없다**.
- **사용자 확인(2026-06-01)**: "sheet4 기준 — 이미 충족". → sheet4 현행 1행=1Activity 유지, 추가 split 로직 불필요. sheet1 멀티라인은 수량 귀속 불가라 행 분리 안 함(가짜 행·중복 양산 방지). 필요 시 결정론 `split('\n')`+strip+dedup 파생필드만(LLM 불필요), 단 이번 스코프 아님.

### 4.3 ③ 인원·장비 = 업체 일일 총투입 → WV 재분배 — **downstream 불변**

- **실측**: sheet2(직종)·sheet3(장비)는 (업체×직종/장비×시간대) **총투입**, activity 연결 컬럼 물리적으로 없음. parser 는 `assigned_workers=0.0`·`worker_source='parsed'`·`plan_mh=None`(`parser.py:448-450`)로 캡쳐만.
- **재분배는 mapper** `_prorate_mh`(`graph.py:114` → `mapper.py:529-604`): `BP사 총 인원 × (l6 candidate Σplan_mh / company Σplan_mh)`(`state.py:78`). **WV = `plan_mh`(WBS l6 계획 man-hour), `today_qty`(실적물량) 아님**.
- **착지**: parser 책임 = 총투입 손실 없이 3 entity 캡쳐. 설계 변경 0. 본 모듈 검증 invariant = **캡쳐 정확성**(recipe 경로의 job/bp/eq 집계 == `parse_daily_report` 골든).
  - **주의(실측 정정 2026-06-01)**: `Σ JobAllocation.workers_today_incr.total`(업체=191) 과 `Σ BPSummary.today_incr_total`(업체=212)는 **등가 아님** — 차이 21 = `_is_admin_job` 로 job_allocations 에서 제외된 관리자. 두 시트 집계 모집단 차이라 정상. 따라서 cross-sheet 등식은 assert 하지 않는다.
  - 분배 보존(`Σ activity.assigned_workers (distinct (company,l6)) == BP사 총 인원`)은 mapper `_prorate_mh` **downstream 영역** — 본 parser 모듈 밖.
- **주의(이중경로 리스크)**: `_prorate_mh` 는 sheet1 `today_incr_total`(191)을 분자로, `_prorate_workers_with_mh` 는 sheet2 누계(3561)를 분모로 — 投入 vs 累計 라 두 경로 불일치 시 activity 인원 갈림. 메모리 `cpia_report_ssot_decision` 의 delay -37 = Σ/distinct 집계 불일치 오진과 동류. recipe 검증에서 합산 규칙 못박을 것.
- **장비 activity 단위 분배는 미구현**(총투입 캡쳐만) — 본 스코프 밖, recipe 에 "장비는 분배 안 함" 명시해 누락 오해 방지.

### 4.4 ④ 협력업체 ditto 공란 (위 중복) 분간

- **실측**: ditto 해소는 **이미 결정론 정상**. `_ffill`(`parser.py:72`)은 테스트에서만 쓰이고, 실제 메커니즘은 "그룹 경계 검출 → 그룹당 회사명 1회 lookup → 그룹 전 행 broadcast"(sheet2/3: Mm01 앵커 + 첫 non-BP; sheet1: col30 병합 경계). 업체파일은 `final_flag` 'O' 부재라 `has_final_flag=False` 로 게이트 자동 우회 → 정상.
- **착지(결정론 계약)**: recipe 에 2단계 명시 — Pass1=그룹 경계 + 앵커 회사명 확정, Pass2=경계 **내부 한정** ditto-broadcast(경계 밖 누출 금지). raw `_ffill` 전역 채움 금지(다른 업체 오염).
- **side-discovery — sheet1 60/159 누락은 by-design(수정 안 함)**: 통합 sheet1 col5 에 BP 159개인데 `_parse_sheet1_bp_summaries` 는 99개만 산출(60 누락). 누락 60개는 전부 **금일투입=0**(누적만 nonzero, 예 PH_X-004 성우이엔씨 금일누적 2499/15644). `design_intent_parser.md:165-168`: "기대 산출량 ≈ 99", "grouping 은 col30 merged 기준 — col5 자체로는 boundary 불명확"(의도적). 즉 "출력인원 현황 = 금일 투입 인원, 0명 업체는 당일 요약 제외"가 설계 의도. **버그 아님 → 통합 sheet1 거동 유지, 골든 99 안 건드림**(다른 세션 territory).
- **잠재 경계(YAGNI, 기록만)**: 업체가 제출했는데 금일투입 0 이면 그 업체 sheet1 BPSummary 가 비어 통합 보고서 인력 섹션에서 사라짐. "제출했으나 0명" 표시 필요 시 recipe zero-input 정책으로 다룸 — 지금은 안 만듦.
- **착지(좁은 LLM, P2 한정)**: 외래양식에서 "협력업체 컬럼이 어디·그룹 경계 신호가 무엇"인지 1회 식별 + `' '`(공백 1칸) placeholder 를 실 업체명 아님으로 판정. ditto broadcast 자체는 결정론 유지.

---

## 5. 검증 전략 (dry-test, LLM bypass)

LLM 비결정성을 배제하고 결정론 코드만 검증. (메모리 `feedback_dry_test`: LLM 스콥은 ①코드매칭 ②할증판단뿐, 그 외 비결정성은 의심.)

### 5.1 실 2종 회귀 (baseline 등가 = 융합 게이트)
- 통합(`docs/sample/...20250925.xlsx`): **activities=1193 / bp_summaries=99 / job_allocations=975 / equipment_allocations=1111**.
- 업체(중원): issue #52 오값(work_content='M', company='F02 5F', today_qty=120) 전부 정상화 — work_content 실작업내용, unit='M', today_qty=금일실적[C]=30, company=실회사명, bp_code='M15X_PH4_041'.
- recipe 기반 모듈이 **같은 코드 경로**로 이 두 건수·핵심필드를 정확 재현해야 prod 융합 안전.

### 5.2 합성 adversarial corpus (P1 변이 = LLM 경로 검증)
중원 업체파일을 변이시켜 N종 가짜양식 생성(`scripts/synth_formats.py`):
- V1 시트명 rename (`4.물량`→`물량집계`)
- V2 헤더 동의어 (`금일실적`→`당일실적`, `대표물량_작업 내용`→`작업내용`)
- V3 컬럼 순서 shuffle
- V4 ±업체명 컬럼 (통합↔업체 축)
- V5 영문 헤더
- **골든(오라클)**: 각 변이 → canonical 업체 `ParsedDailyReport` 와 **의미 등가**(동일 산출). 의미 동일한 양식을 라벨만 바꾼 것이므로 recipe+Pass2 가 동일 출력을 복원해야 함. **오라클은 이미 A_Track 에 머지된 결정론 골든(`ac0a8c5` demo_inputs 10개 업체 골든 = act 33 등, 통합 1193)을 재사용** — 재유도 금지. `synth_formats.py` 는 그 골든 입력을 변이시키고, 기대 출력은 머지된 골든 그대로.

### 5.3 결정성
- recipe 생성 동일 입력 2회 → 동일 recipe(field→column 맵 안정) assert. 이후 Pass2 는 순수 결정론 → 2회 실행 동일.
- 캐시 hit 경로(2번째 파일부터 LLM 0콜)도 동일 출력 assert.

### 5.4 invariant (캡쳐 정확성, 본 모듈 범위)
- 캡쳐 정확성: recipe 경로의 `Σ job/bp/eq` 집계 == `parse_daily_report` 골든 집계 (Tasks 6-9 dict 등가 + Task16 집계 가드).
- cross-sheet 등식(`Σ job incr == Σ bp today_incr_total`)은 §4.3 주의대로 **성립 안 함**(admin 제외분) — assert 금지.
- 분배 보존(distinct (company,l6))은 mapper downstream — 본 모듈 밖.

### 5.5 통과 기준
실 2종 baseline 등가 + 합성 등가 + 결정성 + invariant 4개가 **같은 코드 경로**로 모두 통과해야 "N종 흡수 + prod 융합 안전"이 증명된다.

---

## 6. 배포 & 통합 (독립 모듈 → 데모 후 prod 융합)

- **브랜치**: `A_Track` 에서 worktree 분기(구현 단계). 완성 시 `A_Track` 머지.
- **데모 기간 격리**: 본 모듈은 live graph/`parser_node`/`parser.py` 미수정. 자체 entrypoint(`python -m pipeline.agents.parser_recipe <xlsx>` 류)로 독립 실행·검증. 기존 순수 헬퍼(`parser_post.normalize_company`/`split_company_and_zone`/`extract_zone`, `state` 타입)는 import 재사용.
- **충돌/선행의존 0 (의존이 이미 안정)**: 다른 세션의 결정론 작업은 **이미 A_Track 에 머지됨** — `25bb85d`(sheet4 헤더 컬럼 해석 `_resolve_sheet4_columns`), `7d2befc`(BP 다중패턴 `_BP_PATTERNS`), `c0699dc`(final_flag 조건부 `has_final_flag`), `65a8027`(date pattern), `ac0a8c5`(업체포맷 E2E + demo_inputs 골든). 즉 §3.4 "포팅 원천"은 racing 중인 게 아니라 `parser.py` 에 박혀 있는 고정 소스(`_BP_PATTERNS` L97, `has_final_flag` L269, `_resolve_sheet4_columns` L357). 본 모듈은 그걸 import/참조로 포팅하고 live 경로는 미수정 → 파일 충돌 0.
- **데모 후 융합**: feature flag `CPIA_PARSER=recipe` 를 `parser_node` 에 추가(현재 `parser_llm.py` 의 미구현 `CPIA_PARSER=llm` 분기 자리, design_intent issue #2 와 정합). 융합 전 §5.1 baseline 등가로 제로-리스크 확인 후 스위치.
- **모듈 구성(예정)**:
  - `pipeline/agents/parser_recipe.py` — `recognize_format(wb)->FormatRecipe`, `extract_with_recipe(wb,recipe)->ParsedDailyReport`, `parse_with_recipe(xlsx_path)->ParsedDailyReport`(공개, `parse_daily_report` 시그니처 미러).
  - `data/parser_recipes/<fingerprint>.json` — recipe 캐시(인스펙터블, H-i-L 편집 가능).
  - `scripts/synth_formats.py` — 합성 corpus 생성기.
  - `pipeline/tests/test_parser_recipe.py` — §5 골든.

---

## 7. 미해결 / 다음 단계

- **실 P2 외래양식 샘플 확보** — 들어오면 안전망 발동률 측정 + Tier 2 LLM 의 실 효용 검증(production-trust 게이트). 그 전엔 합성으로만 design/verify.
- **③ 이중경로 proration 일관성** — `_prorate_mh`(sheet1 투입) vs `_prorate_workers_with_mh`(sheet2 누계) 분모 불일치 정리(mapper 측, 본 모듈 밖이나 invariant 로 감지).
- **장비 activity 단위 분배** — 현재 미구현(총투입 캡쳐만). 필요 시 별도.
- **sheet1↔sheet2 zero-today 비대칭** — sheet1 은 0명 제외(99), sheet2 는 누계로 유지. 의도 비대칭인지 별도 확인(본 모듈 스코프 밖).
- **융합 시 sheet1 boundary 정책** — 우리 모듈이 159(BP-pair 경계)로 갈지 99(col30) 유지할지는 융합 시점 결정. 기본은 baseline 등가(99) 재현 후 개선 opt-in.
