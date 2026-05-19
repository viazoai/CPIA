# CPIA Parser Rule-Based + Mapper BP-Zone Match Design

> 작성: 2026-05-20.
> Brainstorming cycle 산출 — superpowers:brainstorming + 4 시트 rule cross-check + 5 case mapper simulation 거쳐 확정.
> PoC 데모 마감 2026-06-05 (목) 안 cycle.

---

## §0 Problem statement

### §0.1 parser_llm.py 의 한계

| 항목 | 현재 (`parser_llm.py`) | 영향 |
|---|---|---|
| chunk_size | 15 (4 시트 모두) | 호출 수 ~270 chunk × 시도 |
| retries | 3 + exponential backoff | content_filter / 빈 list 시 재호출 |
| 실측 시간 (sample mode) | 4~5 분 | PoC 데모 시 일보 1 회 cycle 다수 부담 |
| 실측 비용 | ~$3 / cycle | 데모 반복 시 누적 |
| 결정성 | LLM 응답 chunk 별 fragile | 같은 일보 재실행 시 row 수 변동 가능 (spec `2026-05-19-cpia-reports-gap-and-parser-design.md` §2.2 의 측정값 30/39 빈 list, 18/42 빈 list 등) |

### §0.2 mapper.py 의 hil_required 폭주

`docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` 의 POC 3 사 (남웅 / 세보 / 창원기전) 146 activity simulation (5/20):

- wa 결정: 61 / 146 (42%)
- **hil_required: 85 / 146 (58%)**

원인 (실 sample 추적):

| Case | 회사 / BP | work | cand_pool | 결과 (전) |
|---|---|---|---|---|
| 남웅건설 PH_X-001 | 버림틀 설치 | `(FAB, 철근콘크리트공사), (CUB, 철근콘크리트공사)` | wa=None (resolve_wa 1/2/3 단계 모두 fail) |
| 남웅건설 PH_X-009 | 거푸집 탈형 | 동일 | wa=None |

**구 `resolve_wa` (변경 전, 5 단계 = 0+1+2+3+4)**:
- 0단계 cand_pool 빈 시 → `auto_chroma_top1`
- 1단계 cand_pool wa 단일 — fail (FAB+CUB 둘 다)
- 2단계 l6 결정 후 wa 단일 — fail (l6 동일이라 wa set 다수)
- 3단계 zones_in_sheet1 set 매칭 — fail (옵션 2 보수화로 회사 단위 set 매칭 fail 다수)
- 4단계 `hil_required`

**신 `resolve_wa` (본 spec §3.3, 7 단계 = 0~6)** 에서는 위 fail 흐름이 다음과 같이 해소됨:
- **0단계** cand_pool 빈 시 → `auto_chroma_top1` (기존 그대로)
- **1단계 `auto_bp_zone_match` (신규 fix C)** — `activity.bp_code` 와 일치하는 BPSummary 의 zone 이 cand_pool wa set 안에 있으면 즉시 채택 (deterministic). 예: 남웅건설 PH_X-001 → BPSummary.zone=FAB → cand_pool={(FAB, 철근), (CUB, 철근)} 의 FAB 채택
- **2단계 `auto_llm_rerank` (신규 옵션 A)** — BP-zone 매칭 fail 시 LLM 의 (chosen_wa, l6_choice) ∈ cand_pool 채택
- **3단계** `auto_bp_single` = 구 1단계
- **4단계** `auto_l6_single` = 구 2단계
- **5단계** `auto_sheet1_text` = 구 3단계 (회사 단위 set 매칭, legacy)
- **6단계** `hil_required` = 구 4단계

5/20 simulation V2 의 case 1/2/3 = 1단계 (auto_bp_zone_match) 통과, case 4/5 = 2단계 fallback 후 conf<0.7 → review 안전망.

### §0.3 사용자 본인 push back 정합

- "soft hint = 1번 시트에서 FAB / CUB 알 수 있음" — BPSummary.zone 의 deterministic 활용 의도
- "scope ≠ wa, 오른쪽 작업으로 wa 판단" — col 6 (Scope) 모호 시 LLM 의 work_text 기반 판단 신뢰
- "mapper 도 잘 못 잡는 게 있으면 명확하게 고치고" — root cause fix 의무

### §0.4 본 spec 목표

1. **parser 단독 시간** (rule-only, LLM 0): 4~5 분 → **5 초 이내**
2. **parser + 시트1/4 LLM 검증 (default on)**: ~15~20 초 (사용자 결정 옵션 B 의 hybrid 비용)
3. **mapper hil_required**: 58% → V3 통과 기준 **25% 이내**. 산식 (보수 외삽):
   - V2 5 case 의 deterministic 비율 = 60% (case 1/2/3 = auto_bp_zone_match)
   - 보수 계수 K = 1.5 적용 (POC 3 사 → 146 case 전체 일반화 불확실성 반영)
   - hil 상한 = (1 − 60%) × K ÷ (1 + K × 0.5) ≈ 24~25%
   - 즉 deterministic 통과율 hard 보장 어려우니 "75%+ wa 결정 + 25%- hil" 의 보수치 채택
   - V3 측정 후 실제 비율 명확화 (예: 70% 외삽 시 hil 30% — V5 진입 보류)
4. **parser 출력 결정성**: rule 추출 100% (LLM 검증의 issues 출력은 stderr 로그 only, DB 적재 X — 결정성 영향 없음)
5. **마지막 검증**: 10 업체 POC 전체 로직 cycle + reports UI 매칭 (§5 V5)

---

## §1 Scope / Non-scope

### Pre-existing 코드 사용 (iter 2 reviewer feasibility A 반영)

본 spec 작성 시 `pipeline/agents/parser.py` (306 line, 5/17 spec 산출, 4 시트 rule-based parser) 가 **이미 존재** 하는 사실을 5/20 brainstorming 초기에 인지 못 했음. 기존 parser.py 의 4 시트별 함수:
- `_parse_sheet1_bp_summaries(ws)` (line 90)
- `_parse_sheet2_job_allocations(ws)` (line 124)
- `_parse_sheet3_equipment_allocations(ws)` (line 196)
- `_parse_sheet4_activities(ws)` (line 158)
- `parse_daily_report(xlsx_path) -> ParsedDailyReport` (line 270, sync, no cfg)

기존 caller (5 test + 1 script + collector + 1 demo 등 ≥11 곳):
- `pipeline/tests/test_parser.py` (6 import)
- `pipeline/tests/test_graph_e2e.py`, `test_mapper_golden.py`, `test_atomizer.py`
- `pipeline/tests/forecaster/test_forecaster_e2e.py`
- `scripts/parser_e2e_demo.py`

→ **본 spec 의 변경은 신설이 아니라 `parser.py` 의 4 시트 함수 개선 + LLM 검증 추가**. tmp/sheet*_v*.py 의 5/20 prototype 은 기존 parser.py 의 rule 과 cross-check 후 차이점 만 patch 하는 형태.

기존 parser.py 의 `parse_daily_report(xlsx_path)` signature 는 **그대로 유지** (sync, no cfg) — 11 caller 호환. LLM 검증은 신규 wrapper `parse_daily_report_with_verify(xlsx_path, cfg)` 또는 env flag (`CPIA_PARSER_VERIFY_LLM=on/off`) 로 opt-in.

### Scope (본 cycle 변경)

| Layer | 변경 | 책임 |
|---|---|---|
| Parser | `parser.py` 의 `_parse_sheet1_bp_summaries` 개선 — BP 별 zone 분리 + skip 로직 (sub-section 합계 / solo+next 흡수) | A_Track |
| Parser | `parser.py` 의 `_parse_sheet2_job_allocations` 개선 — UT/제어 keyword fix + subtotal skip + cross-check | A_Track |
| Parser | `parser.py` 의 `_parse_sheet3_equipment_allocations` 개선 — group boundary 보강 | A_Track |
| Parser | `parser.py` 의 `_parse_sheet4_activities` 개선 — ffill 4 컬럼 + zone 옵션 2 + cross-check (B+C=D) | A_Track |
| Parser | `parser_post.py` 의 `normalize_company` 강화 + `split_company_and_zone` / `extract_zone` 신설 | A_Track |
| Parser | `parser.py` 에 LLM 검증 wrapper 추가 (시트1/4, opt-in env, default on) | A_Track |
| Parser | `parser_llm.py` deprecation (코드 보존, env flag `CPIA_PARSER=llm` 으로 회귀 가능) | A_Track |
| Mapper | `build_bp_context` BP 코드별 분리 + zone 명시 (5/20 working tree 적용됨) | A_Track |
| Mapper | `build_llm_input` activity.bp_code 명시 (5/20 적용됨) | A_Track |
| Mapper | `resolve_wa` 7 단계 (0=auto_chroma_top1 / 1=auto_bp_zone_match / 2=auto_llm_rerank / 3=auto_bp_single / 4=auto_l6_single / 5=auto_sheet1_text / 6=hil_required) (5/20 적용됨) | A_Track |
| Graph | parser entry — 기존 `parse_daily_report(xlsx_path)` 호출 그대로 (signature 유지, env flag 는 parser.py 내부에서 분기) | A_Track |
| Test | 4 시트 unit test (`test_parser.py` 확장) + mapper resolve_wa 7 단계 unit test | A_Track |
| E2E | **10 업체 POC 전체 cycle + reports UI 검증 (사용자 명시)** | A + B Track |

### Non-scope (의도적 drift)

- atomizer / forecaster / optimizer 변경 X (mapper_activities 의 6 컬럼 schema 보존)
- reports UI 컴포넌트 변경 X (mock route 변경 X)
- ChromaDB 적재 변경 X
- 시트2 / 시트3 LLM 검증 (시트2 cross-check 0 warnings + 시트3 row 1:1 단순 추출 — 규칙성 강해 LLM 불요. 사용자 결정 2026-05-20)

---

## §2 Parser Rule-Based 설계

### §2.1 공통 헬퍼 (`parser_post.py` 확장)

```python
def normalize_company(raw: str | None) -> str | None:
    """㈜prefix / (주) / 모든 괄호 부속 제거.

    예: '㈜남웅건설' → '남웅건설'
        '창원기전(6.6kV)' → '창원기전'
        '(주)캠파트너스' → '캠파트너스'
    """
    if raw is None:
        return None
    s = str(raw).replace("㈜", "")
    s = re.sub(r"\(주\)", "", s)
    s = re.sub(r"\([^)]+\)", "", s)  # 괄호 부속
    return s.strip() or None


def split_company_and_zone(raw: str | None) -> str | None:
    """회사명 끝의 FAB/CUB suffix 떼고 회사명만 반환.

    옵션 2 (scope ≠ wa) 정책상 zone_hint 는 반환 X — 회사명 정규화에만 사용.
    예: '에스비테크CUB' → '에스비테크'
        '광건티엔씨FAB(수장2)' → '광건티엔씨' (괄호도 제거)
        '남웅건설' → '남웅건설'
    """
    s = normalize_company(raw) or ""
    s = re.sub(r"\s*(FAB|CUB)\s*$", "", s, flags=re.IGNORECASE)
    return s.strip() or None


def extract_zone(v6: str | None) -> str | None:
    """col 6 (Scope) 의 명시적 'FAB' / 'CUB' 토큰만 zone 추출.

    옵션 2 채택: 텍스트 중간 / company suffix 의 FAB/CUB 는 무시. 모호 시 None.
    예: 'FAB' → 'FAB'
        'FAB 전구간' → 'FAB' (시작 토큰)
        'CUB 1F~7F' → 'CUB'
        'FAB/CUB' → None (양쪽 모호)
        'M15X FAB F04' → None (텍스트 중간)
        '클라이머 설치 ... FAB X48' → None
    """
    if v6 is None:
        return None
    s = str(v6).strip().upper()
    if re.search(r"FAB\s*[/&,]\s*CUB|CUB\s*[/&,]\s*FAB", s):
        return None
    if s in ("FAB", "CUB"):
        return s
    if re.match(r"^FAB[\s,/\-_]", s):
        return "FAB"
    if re.match(r"^CUB[\s,/\-_]", s):
        return "CUB"
    return None
```

### §2.2 시트1 (출력인원 현황) — 99 그룹 추정

**col 인덱스 (openpyxl `cell(row, column)` 의 1-base)** — 실 xlsx (`docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx`) 의 r5 header dump (5/20 검증):
- col 3 = `Zone` (header value 'FAB/CUB')
- col 4 = `Dis` (공종 header, 데이터 row 는 None)
- col 5 = `BP사/협력업체` — **BP 코드 row 와 회사명 row 모두 col 5 에 박힘** (r27 col 5='PH_X-093', r28 col 5='두인에스앤디')
- col 6 = `Scope` (zone 추출 source)
- col 7-9 = 전일/금일/명일 작업사항
- col 10-15 = 전일 투입 시간대 6 칸, col 16 = 전일 투입 그룹 Total
- col 17-22 = 전일 누적 6 칸, col 23 = 전일 누적 그룹 Total
- col 24-29 = 금일 투입 6 칸, col 30 = 금일 투입 그룹 Total ← merged 2-row 좌상단에 박힘
- col 31-36 = 금일 누적 6 칸, col 37 = 금일 누적 그룹 Total

**구조**:
- group boundary = col 30 (금일투입 그룹 Total) 의 merged 2-row 또는 단독 row (값 not None)
- 그룹 안 row 들: BP 코드 row (col 5='PH_X-NNN') + 회사명 row (col 5 한글) — 인접 2 row pair (col 5 의 같은 col 에 두 의미)

**추출 필드 (`BPSummary`)**:
```python
{
    "bp_code": "PH_X-001",                       # col 5 의 PH_X 패턴 row
    "company": "남웅건설",                        # col 5 한글 row → normalize_company
    "zone": "FAB" | "CUB" | None,                # col 6 → extract_zone
    "scope": None,                               # col 6 raw 보존은 별도 컬럼 (선택)
    "work_text_today": "FAB F03 4F. PH1 패드천공 및 조립",  # col 8 group 내 모든 row join
    "today_incr_total": 102,                     # col 30 (merged 좌상단)
    "today_cum_total": 150565,                   # col 37
    "workers_today_incr": {6 칸 시간대 합},      # col 24-29 group row 합
    "workers_today_cum": {6 칸 시간대 합},       # col 31-36 group row 합
    # ...
}
```

**skip 조건**:
- bp_code=None AND company=None → sub-section 합계 row (예: r33-34 cum=176,665)
- company=None AND today_cum_total=0 AND today_incr_total=0 → 빈 placeholder
- col 30 merged 의 좌상단 값이 None → 빈 그룹

**solo+next row 흡수**:
- col 30 merged 가 1-row 짜리 (solo) + 다음 row 의 col 5 한글 채워있고 col 30=None → 흡수 (예: r149 PH_X-044 + r150 중원엔지니어링)

### §2.3 시트2 (직종별 인원) — 1,597 row 추정

**구조** (시트 row 1:1 → JobAllocation):
- group 시작 = col 4='Mm01' + col 25='O' + col 3=PH_X-NNN + col 2 채워있음
- group 끝 = 다음 group 시작 직전 또는 시트 끝

**추출 필드 (`JobAllocation`)**:
```python
{
    "bp_code": "PH_X-001",                     # group 시작 row col 3
    "company": "남웅건설",                     # group 시작 +1 row col 3 → normalize
    "disc_abbrev": "건축",                     # group 시작 col 2
    "manager_code": "Mm01" | None,             # col 4 (Mm## 만)
    "worker_code": "Wk24" | None,              # col 4 (Wk## 만)
    "job_type": "비계공",                      # col 6
    "workers_yesterday_cum": {6 칸 dict},      # col 7-12
    "workers_today_incr": {6 칸 dict},         # col 13-18
    "workers_today_cum": {6 칸 dict},          # col 19-24
    "final_flag": "O",                         # col 25
    "workers_cum_t": 16848,                    # workers_today_cum.total (mapper 편의)
}
```

**Skip — subtotal/grand total row (이중계상 방지)**:
- col 4 = None + col 25 = 'O' → group 끝의 subtotal/total row
  - col 2='관리자' → Mm subtotal
  - col 2='근로자' → Wk subtotal
  - col 6 안에 'Total' → grand total

**Cross-check (DB schema 변경 X, in-memory warning 만)**:
- 각 group 의 직종 row workers_today_cum.total 합 = grand total row 의 col 24
- 불일치 시 `parser_warning` stderr 로그
- 옵션: warning 을 `parser_reports.warnings_jsonb` 같은 필드에 적재 (별 cycle, 본 cycle scope 외)

### §2.4 시트3 (장비현황) — 1,111 row 추정

**구조** (row 1:1):
- group 시작 = col 2 채워있음 + col 3=PH_X-NNN + col 4 (대분류) 채워있음
- group 안 row 들: 회사명 row 1 개 + 장비 row 들

**추출 필드 (`EquipmentAllocation`)**:
```python
{
    "bp_code": "PH_X-001",
    "company": "남웅건설",
    "disc_abbrev": "건축",
    "equipment_big": "크레인류",              # col 4
    "equipment_mid": "Crane",                  # col 5
    "equipment_spec": "30 Ton > 70 Ton",       # col 6
    "count_yesterday_cum": {6 칸 dict},        # col 7-12
    "count_today_incr": {6 칸 dict},           # col 13-18
    "count_today_cum": {6 칸 dict},            # col 19-24
    "final_flag": "O",
    "count_cum_t": 922,                        # mapper 편의
}
```

**필터**:
- col 25='O' + col 4 채워있음 만 통과
- subtotal row 없음 (cross-check 불요)

### §2.5 시트4 (물량) — 1,193 activity 추정

**ffill 패턴 (4 컬럼 propagation)**:
- col 3 (zone header `FAB/CUB`) — 1 회만 박힘, 위로 거슬러 채움
- col 4 (공종) — 8 회 instance, 변경 시만 박힘
- col 5 (BP 코드 `PH_X-NNN`) — 회사 그룹 시작 row
- col 6 (회사명) — col 5 와 동일 row

**Activity row** = col 8 (work_content) 채워있음.

**추출 필드 (`Activity`)**:
```python
{
    "zone": "FAB" | "CUB" | None,              # extract_zone(col 7 Scope) 우선, fallback col 3
    "bp_code": "PH_X-001",                     # ffill col 5
    "company": "남웅건설",                     # ffill col 6 → normalize
    "scope": "M15-Ph-X FAB (X30~Y12)",         # col 7 raw 보존
    "trade": "건축",                           # ffill col 4
    "work_content": "버림틀 설치",             # col 8
    "unit": "m",                               # col 9
    "plan_total_qty": 315.0,                   # col 10 [A]
    "yesterday_cum_qty": 315.0,                # col 11 [B]
    "today_qty": 0.0,                          # col 12 [C]
    "today_cum_qty": 315.0,                    # col 13 [D = B+C]
    # ... 나머지 Activity TypedDict 필드 None
}
```

**Cross-check**:
- col 11 + col 12 = col 13 (B+C=D 산술 정합)
- col 13 / col 10 = col 14 (D/A=F%)
- 불일치 시 warning (예: r828 SPOOL Piping diff=-2 = raw 입력 오류)

### §2.6 LLM 검증 — 시트1 + 시트4 default on (사용자 결정 옵션 B, 2026-05-20)

사용자 의도 (verbatim): "기존 비결정성 방식 규칙처럼 ... 그 시트를 통으로 llm한테 그냥 주는거야 여기까지가 llm parser인거지" — rule-based 추출 후 LLM 가 한 번 검증/보완 하는 hybrid 패턴.

**시트2 / 시트3 LLM 불요** (사용자 결정): row 1:1 단순 추출 + 강한 cross-check (시트2 의 직종 합 = grand total, 시트3 subtotal 없음).

**시트1 + 시트4 LLM 검증** (default on):
- 시트1 = BPSummary (zone / work_text / 인원) — mapper 의 `auto_bp_zone_match` 의 input
- 시트4 = Activity (work_content / 수량) — mapper 의 LLM rerank input + EVM 의 EV 분자

#### §2.6.1 호출 방식

각 시트별 1 회 호출. 입력 = rule 추출 결과 + 핵심 col raw dump. 출력 = `{"issues": [...]}` 만 (raw 와 어긋난 경우만).

| 시트 | 입력 chars (전체) | 입력 tokens | 출력 tokens | 비용 |
|---|---|---|---|---|
| 시트1 | ~191k (raw 99 그룹 + rule 결과) | ~91k | ~200 (issues 1 건 정도) | ~$0.5 |
| 시트4 | ~20k (sample 39 row + 의심 case) | ~9k | ~400 (issues 2 건 정도) | ~$0.05 |

총 약 $0.55 / cycle. PoC 데모 마감 안 부담 미미.

#### §2.6.2 응답 처리

```python
verify = json.loads(resp.choices[0].message.content)
issues = verify.get("issues", [])
for it in issues:
    logger.warning(
        f"[parser_rule:{sheet_name}] LLM 검증 issue: "
        f"row={it['row']} field={it['field']} current={it['current']} "
        f"expected={it['expected']} reason={it['why']}"
    )
```

- DB 적재 X (별 cycle 에서 `parser_reports.warnings_jsonb` 컬럼 추가 검토)
- issue 1 건이라도 발견 시 stderr 로그 + cycle 계속 진행 (block X)
- env `CPIA_PARSER_VERIFY_LLM=off` 로 opt-out 가능 (테스트 / 비용 절감 시)

#### §2.6.3 사용자 입증 효과 (5/20 prototype)

| 시트 | LLM 검증 결과 |
|---|---|
| 시트1 | input 91k / output 197 tokens / issue 1 건 (work_text 구분자 차이 — 사소) |
| 시트4 | input 9k / output 392 tokens / issue 2 건 (r183 zone='CUB' vs null / r828 zone='FAB' vs null) — **fix C (`auto_bp_zone_match`) 도입 trigger** |

→ 시트4 LLM 검증이 mapper 변경의 root cause 도출에 기여.

#### §2.6.4 Error path / 안전망 (Azure OpenAI 의존성)

LLM 검증 default on 이지만 cycle block 안 함. 다음 shadow path 모두 graceful degrade:

| 시나리오 | 처리 |
|---|---|
| Azure OpenAI down / 5xx / timeout (30s cap) | `try/except` 로 catch → stderr warning + cycle 계속. parser_rule 결과만 사용 |
| 401 / API key invalid | 동일 catch → stderr warning. env 설정 issue 알림 |
| rate-limit (429) | retries=2 + exponential backoff (1s, 2s). 그래도 fail 시 catch |
| content_filter (`finish_reason='content_filter'`) | stderr warning, issues=[] 로 처리 |
| Malformed JSON (LLM 응답 parsing fail) | `try: json.loads(...) except json.JSONDecodeError:` → issues=[] |
| 빈 input (rule 추출 결과 빈 list) | LLM 호출 skip (불필요한 비용 0) |
| 응답 schema 위반 (`issues` 키 missing) | `verify.get("issues", [])` 로 안전 처리 |
| **truncated response** (`finish_reason='length'`) | max_completion_tokens 충분히 크게 (시트1=2k, 시트4=1k). finish_reason 명시 체크 — 'length' 시 issues=[] + stderr warning (silent failure 회피) |
| **APIConnectionError / 중간 reset / 기타 Exception** | `except Exception as e:` broad catch (cycle block 안 함). parser_llm.py 의 stderr 로그 형식 (`[parser_llm] key=... attempt=... EXCEPTION ...`) 과 일관 |

**비용 cap**: 시트1+4 합쳐 한 cycle 당 최대 ~$1 (retries 포함 worst case). 초과 risk 시 `CPIA_PARSER_VERIFY_LLM=off` opt-out.

**결정성 영향**: LLM 검증 issues 는 stderr 로그만 — DB 적재 X. 따라서 같은 일보 재실행 시 ParsedDailyReport / mapper_activities 결과는 결정론적 (LLM 응답이 매번 달라도 영향 없음). 단 stderr 로그는 변동 가능 — unit test 시 issues 갯수 assertion 금지.

---

## §3 Mapper 변경

### §3.1 `build_bp_context` — BP 별 분리 + zone 명시

**기존**:
```
· [시트1] 주요작업 텍스트 (BP사 기재): FAB F03 4F. PH1 패드천공 및 조립 / CUB 9층 단열재 설치
· [시트1] 금일 신규 투입 인원 (Incr.): 102명
· [시트1] 금일 누적 인원 (Cum.): 210,362명-일
```

**신규**:
```
· [시트1] BP 사이트별 작업 (작업 내용 보고 어느 BP 코드인지 판단):
    - PH_X-001 (zone=FAB): FAB F03 4F. PH1 패드천공 및 조립 [Incr 56명, Cum 150,565명-일]
    - PH_X-009 (zone=CUB): CUB 9층 단열재 설치 [Incr 46명, Cum 59,797명-일]
```

### §3.2 `build_llm_input` — activity.bp_code 명시

```diff
- 회사: 남웅건설 (공종 건축)
+ 회사: 남웅건설 / BP: PH_X-001 (공종 건축)
```

### §3.3 `resolve_wa` 6 단계 (재정렬)

```python
def resolve_wa(activity, l6_choice, cand_pool, parsed_report, chosen_wa=None) -> WAResolution:
    # 0. cand_pool 빈 시 (BP master 미등록) → Chroma top-1 채택
    if not cand_pool:
        return WAResolution(value=chosen_wa, source="auto_chroma_top1")

    # 1. (신규 fix C) — activity.bp_code 와 일치하는 BPSummary.zone 채택 (deterministic)
    #    사용자 push back ("시트1 에서 FAB/CUB 알 수 있음") + 옛 POC 회상 정합
    if parsed_report and activity.get("bp_code"):
        cand_wa_set = {wa for wa, _ in cand_pool}
        for s in parsed_report["bp_summaries"]:
            if s.get("bp_code") == activity["bp_code"] and s.get("zone"):
                if s["zone"] in cand_wa_set:
                    return WAResolution(value=s["zone"], source="auto_bp_zone_match")

    # 2. (신규 옵션 A) — LLM rerank 의 (chosen_wa, l6_choice) 가 cand_pool 안에 있으면 채택
    #    BP-zone 매칭 fail 시 LLM 의 work_text 기반 판단 fallback
    if chosen_wa and (chosen_wa, l6_choice) in cand_pool:
        return WAResolution(value=chosen_wa, source="auto_llm_rerank")

    # 3. cand_pool wa 단일 → auto_bp_single
    bp_wa = {wa for wa, _ in cand_pool}
    if len(bp_wa) == 1:
        return WAResolution(value=next(iter(bp_wa)), source="auto_bp_single")

    # 4. L6 결정 후 wa 단일 → auto_l6_single
    l6_wa = {wa for wa, l6 in cand_pool if l6 == l6_choice}
    if len(l6_wa) == 1:
        return WAResolution(value=next(iter(l6_wa)), source="auto_l6_single")

    # 5. 시트1 zones_in_sheet1 (회사 단위) ∩ cand_wa_at_l6 → auto_sheet1_text (legacy)
    if parsed_report is not None:
        zones_in_sheet1 = {s["zone"] for s in parsed_report["bp_summaries"]
                           if s["company"] == activity["company"] and s["zone"]}
        cand_wa_at_l6 = {wa for wa, l6 in cand_pool if l6 == l6_choice}
        intersect = zones_in_sheet1 & cand_wa_at_l6
        if len(intersect) == 1:
            return WAResolution(value=next(iter(intersect)), source="auto_sheet1_text")

    # 6. H-i-L 강제
    return WAResolution(value=None, source="hil_required")
```

### §3.4 `requires_review` 조건

```python
requires_review = (confidence < cfg.conf_threshold) or (wa_result.source == "hil_required")
```

`conf_threshold = 0.7` (기존).

**source 별 conf 처리 매트릭스**:

| source | conf 평가 | review 트리거 |
|---|---|---|
| `auto_bp_zone_match` (1단계) | **skip** (deterministic) | source ≠ 'hil_required' → False (conf 무관) |
| `auto_llm_rerank` (2단계) | LLM rerank conf | conf<0.7 → True |
| `auto_bp_single` (3단계) | LLM rerank conf | conf<0.7 → True |
| `auto_l6_single` (4단계) | LLM rerank conf | conf<0.7 → True |
| `auto_sheet1_text` (5단계) | LLM rerank conf | conf<0.7 → True |
| `auto_chroma_top1` (0단계, 빈 pool) | LLM rerank conf | conf<0.7 → True |
| `hil_required` (6단계) | 무관 | **항상 True** |

→ `auto_bp_zone_match` 의 deterministic 통과는 V2 case 1/2 (남웅) 의 LLM conf 0.83/0.97 모두 정답 입증으로 정합. 단 false positive risk (BPSummary.zone 이 잘못 박힌 case) 는 §5 V5 에서 빈도 측정 (mitigation §7 참고).

---

## §4 통합 흐름

### §4.1 Graph 의 parser entry — 기존 `parse_daily_report(xlsx_path)` 활용

iter 2 reviewer feasibility A 반영: pre-existing `pipeline/agents/parser.py:270` 의 `def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport` (sync, no cfg) signature 를 **그대로 유지**. 본 spec 의 4 시트 함수 개선은 같은 모듈 안의 `_parse_sheet1_bp_summaries` ~ `_parse_sheet4_activities` 본문 patch 만.

```python
# pipeline/agents/parser.py — 기존 entry 유지 + 내부 LLM 검증 추가

def parse_daily_report(xlsx_path: Path | str) -> ParsedDailyReport:
    """4 시트 rule-based 추출. 기존 caller (11 곳) signature 호환."""
    wb = openpyxl.load_workbook(str(xlsx_path), data_only=True)
    parsed: ParsedDailyReport = {
        "report_date": _extract_meta(...)[0],
        "project": _extract_meta(...)[1],
        "bp_summaries": _parse_sheet1_bp_summaries(wb["1.출력인원 현황"]),
        "job_allocations": _parse_sheet2_job_allocations(wb["2.직종별 인원현황"]),
        "equipment_allocations": _parse_sheet3_equipment_allocations(wb["3.장비현황"]),
        "activities": _parse_sheet4_activities(wb["4.물량"]),
        "worker_outputs": [],
        "report_meta": None,
    }
    # LLM 검증 (시트1/4 default on, env CPIA_PARSER_VERIFY_LLM=off 로 opt-out)
    if os.environ.get("CPIA_PARSER_VERIFY_LLM", "on").lower() != "off":
        _verify_sheet1_via_llm(wb["1.출력인원 현황"], parsed["bp_summaries"])
        _verify_sheet4_via_llm(wb["4.물량"], parsed["activities"])
    return parsed
```

**parser_llm.py 의 위치**: deprecation. `CPIA_PARSER=llm` env flag 로 회귀 사용 가능. 단 기본 path 는 `parser.py` (rule-based).

**Caller 변경**: 위 entry signature 유지로 **기존 11 caller 변경 X**. 단:
- `pipeline/agents/collector.py:19` 가 `parse_daily_report_llm` 을 import 중 — **`parse_daily_report` 로 교체** 필요 (parser_llm path 제거)
- `scripts/run_one_cycle.py:29,70` — 동일 (현재 `parse_daily_report_llm` 호출)
- `pipeline/api.py` — graph 통과라 직접 영향 없음 (검증만)
- `scripts/parser_e2e_demo.py:27` — 이미 `parse_daily_report` 호출 (변경 X)
- 5 test 파일 — 이미 `parse_daily_report` 호출 (변경 X)

→ 2 곳 (collector + run_one_cycle) 만 변경. §6 commit 7 의 영향 범위에 명시.

**`ParserConfig`**: parser.py 안의 LLM 검증은 Azure OpenAI client 를 env 변수에서 직접 읽음 — caller 에서 cfg 전달 안 함 (signature 단순 유지).

### §4.2 결정성 보장

- parser_rule 의 출력은 openpyxl read + rule 적용 → **결정론적**
- 동일 xlsx 입력 → 동일 ParsedDailyReport (LLM 응답 변동 없음)
- 단 `extract_zone` / `split_company_and_zone` 의 regex 가 결정론적이라 보장

### §4.3 Schema 호환

- 출력 schema = `pipeline/state.py` 의 `ParsedDailyReport` (BPSummary / JobAllocation / EquipmentAllocation / Activity)
- mapper / atomizer / forecaster / optimizer / reporter 의 input schema 변경 X
- mapper_activities PG 컬럼 변경 X
- daily_reports view jsonb 변경 X

---

## §5 검증 plan (Iron Law — Real code 만 인정)

### V1 — 4 시트 rule cross-check (이미 검증됨, 5/20)

| 시트 | row | cross-check | 비고 |
|---|---|---|---|
| 시트1 (출력인원) | 99 그룹 | LLM 검증 1 issue (구분자) | soft hint zone 정합 |
| 시트2 (직종별) | 1,597 row | **0 warnings** | UT/제어 keyword fix 후 통과 |
| 시트3 (장비) | 1,111 row | subtotal 없음 (불요) | raw 그대로 |
| 시트4 (물량) | 1,193 row | **1 warning** (r828 raw 결함) | zone 63% mapper LLM 로 판단 |

### V2 — Mapper 5 case simulation (이미 검증됨, 5/20)

| Case | BP | wa (전) | wa (후) | 정답 | source | conf |
|---|---|---|---|---|---|---|
| 1 | PH_X-001 (남웅) | hil | **FAB** | FAB | auto_bp_zone_match | 0.83 |
| 2 | PH_X-009 (남웅) | hil | **CUB** | CUB | auto_bp_zone_match | 0.97 |
| 3 | PH_X-041 (세보) | FAB | FAB | FAB | auto_bp_zone_match | 0.97 |
| 4 | PH_X-039 (창원) | hil | FAB | FAB? | auto_llm_rerank | 0.63 (review) |
| 5 | PH_X-073 (창원) | hil | FAB | CUB | auto_llm_rerank | 0.63 (review) |

case 4/5 = BPSummary.zone=None (옵션 2 보수화 결과) → LLM fallback, conf<0.7 → HIL 안전망 작동.

### V3 — Mapper 146 case full simulation (POC 3사)

```bash
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 tmp/sim_3sa.py --prod-pg
```

기대 (V2 5 case 의 deterministic 비율 60% 를 보수 외삽, 146 case 에 정확한 비율 추산 불가):
- wa 결정 (전체): 42% → **목표 70%+** (auto_bp_zone_match + auto_llm_rerank + 기존 1/2/3 단계 합)
- hil_required: 58% → **목표 ≤25%**
- auto_bp_zone_match 비율: **≥40%** (deterministic source 가 다수)

**통과 기준 (V3)**:
1. hil_required ≤ 25%
2. `mapping_source` 분포: auto_bp_zone_match ≥ 40%
3. auto_bp_zone_match 채택 case 의 LLM rerank chosen_wa 와 어긋난 비율 ≤ 5% (false positive 측정 — Reviewer feasibility issue 3 mitigation)

→ §7 risk 와 연동. 통과 못 하면 V5 진입 보류, mapper resolve_wa 순서 재검토.

### V4 — 단위 test

`pipeline/tests/test_parser_rule.py` (신설):
- 시트1: `test_sheet1_extract_99_groups()`, `test_sheet1_subtotal_skip()`, `test_sheet1_solo_next_absorb()`
- 시트2: `test_sheet2_subtotal_skip_no_double_count()`, `test_sheet2_cross_check_zero_warnings()`
- 시트3: `test_sheet3_extract_1111_rows()`
- 시트4: `test_sheet4_ffill_4cols()`, `test_sheet4_cross_check_BC_eq_D()`

`pipeline/tests/test_mapper_resolve_wa.py` (신설):
- `test_auto_chroma_top1_when_empty_pool()`
- `test_auto_bp_zone_match_deterministic()`
- `test_auto_llm_rerank_fallback()`
- `test_auto_bp_single()`
- `test_auto_l6_single()`
- `test_auto_sheet1_text_legacy()`
- `test_hil_required_when_all_fail()`

### V5 — 10 업체 POC 전체 cycle + Reports UI 검증 (사용자 명시 마지막 단계)

**Sample 선정 절차 (Reviewer feasibility issue 2 반영)** — 추측 sample 대신 실측 기반:

```bash
# A. BP master 의 회사별 cand_pool size 실측
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 -c "
import asyncio
from pipeline.db import PGClient
async def main():
    pg = PGClient('<POSTGRES_URL>'); await pg.connect()
    rows = await pg._pool.fetch(\"\"\"
      SELECT company, COUNT(*) as pool_size,
             COUNT(DISTINCT wa) as wa_kinds
      FROM activity_master GROUP BY company
      ORDER BY 2 DESC
    \"\"\")
    for r in rows: print(r)
    await pg.close()
asyncio.run(main())
"

# B. 해당 일보의 시트4 활동 row count per company (parser_rule 결과 dump)
pipeline/.venv/bin/python3 tmp/sheet4_v1.py --no-llm | grep -oE "company='[^']+'" | sort | uniq -c | sort -rn
```

**Sample 선정 기준** (실측 후 확정):
- cand_pool size 다양: 1 / 2 / 5 / 10 / 20 커버
- 시트4 activity row ≥ 3 (통계적 유효성)
- wa 분포 다양: FAB 단일 / CUB 단일 / FAB+CUB 혼합 / 미등록 (cand_pool=0) 각 ≥ 1

**예시 sample 후보** (5/20 dump 기준, V5 실행 직전 재확정):
1. 남웅건설 (cand_pool=2, FAB+CUB, sheet4 ~146 row)
2. 세보엠이씨 (cand_pool=19, FAB 단일)
3. 창원기전 (cand_pool=9, FAB+CUB 혼합)
4. 두인에스앤디 (cand_pool=? 실측 필요)
5. 장평건설 (FAB+CUB 분리)
6~10. 위 A/B 의 출력에서 선정 (cand_pool=1 / 미등록 / suffix 분리 회사 등)

**실행**:
```bash
# 1. PG cleanup (seed 보존, cycle 결과만)
POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 scripts/cleanup_cycle_results.py

# 2. parser_rule 로 cycle 실행 (POC_KEYWORDS 10 업체 으로 확장)
CPIA_PARSER=rule \
  POSTGRES_URL='postgresql://cpia:K7mP2xQ9nR4v@localhost:5532/cpia' \
  pipeline/.venv/bin/python3 scripts/run_one_cycle.py \
  'docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx' \
  m15x-ph3-ibl 2025-09-25

# 3. HIL 1 interrupt resume (자동 또는 web UI Modal)
# 4. atomizer / forecaster / optimizer / reporter 끝까지 진행
# 5. daily_reports.{kpi,contractor_bars,trade_bars,quadrant,wp_summary,s_curve,
#    optimizer_view,productivity,scenarios}_jsonb UPSERT 완료 확인
```

**UI 검증** (`http://localhost:3000/reports` 또는 dev server):

10 정량 기준 (spec `2026-05-19-cpia-reports-parser-mh-design.md` §9 와 정합):

| # | 검증 항목 | 정량 기준 |
|---|---|---|
| 1 | § 01 헤더 CPI % | 0% 가 아닌 실수값 + 색상 chip |
| 2 | § 01 90일 trend | line chart 그어짐 + 최소 7 datapoint |
| 3 | § 01 업체별 bar | bar count ≥ 8 (10 업체 중 plan_mh 활성 회사) |
| 4 | § 01 공종별 bar | bar count ≥ 5 (10 업체 활성 l6) |
| 5 | § 02 4분면 산점도 | 점 count ≥ 8 + 4 quadrant 모두 적어도 1 점 |
| 6 | § 02 WP 표 | row ≥ 10 |
| 7 | § 02 4 섹션 (WP 클릭 시) | 진단/유사사례/권고/상세 모두 비어있지 않음 |
| 8 | § 02 WP 진단 NULL fallback 작동 | (Optimizer 미실행 그룹) "데이터 없음" 텍스트 표시 |
| 9 | § 03 S-curve | planned/actual/forecast/recovery 4 곡선 그어짐 |
| 10 | § 03 narrative 라벨 | "현 추세 연장" + "AI 회복 시나리오" 표시 |
| 11 | **mapping_source 분포** | `mapper_activities.mapping_source` 그룹 by 결과 — auto_bp_zone_match ≥ 40%, hil_required ≤ 25% (V3 통과 기준 일관성) |
| 12 | **zone false positive 빈도** | auto_bp_zone_match 채택 case 중 LLM rerank chosen_wa 와 어긋난 비율 ≤ 5% (parser zone false positive risk 측정) |

**Playwright e2e**: `web/e2e/reports-10-companies.spec.ts` (신설) — 위 10 기준 자동 검증.

**사람 시각 확인** (사용자 본인 행동 규칙 메모리):
- `npm run dev` 띄움 → `http://localhost:3000/reports` 접속
- 10 업체 별 매핑 결과 (mapper_activities) UI 표시 확인
- WP 클릭 시 4 섹션 모두 데이터 노출 확인

---

## §6 마이그레이션 순서 (atomic commits)

| # | Commit | 영향 |
|---|---|---|
| 1 | `feat(parser_post): normalize_company 강화 + split_company_and_zone / extract_zone 신설` | 헬퍼만, 기존 caller 변경 X |
| 2 | `refactor(parser): 시트1 _parse_sheet1_bp_summaries 개선 — BP-zone 분리, sub-section skip, solo+next 흡수` | 기존 11 caller 의 BPSummary schema 호환 |
| 3 | `refactor(parser): 시트2 _parse_sheet2_job_allocations 개선 — UT/제어 keyword + subtotal skip + cross-check` | 동일 |
| 4 | `refactor(parser): 시트3 _parse_sheet3_equipment_allocations 개선` | 동일 |
| 5 | `refactor(parser): 시트4 _parse_sheet4_activities 개선 — ffill 4 컬럼 + zone 옵션 2 + cross-check B+C=D` | 동일 |
| 6 | `feat(parser): 시트1/4 LLM 검증 wrapper (default on, env opt-out) + error path 8 종` | parse_daily_report() entry 안 통합 |
| 7 | `refactor(callers): collector.py + run_one_cycle.py 의 parser_llm 호출 → parse_daily_report() 로 교체` | parser_llm path 제거 (split-brain 방지) |
| 8 | `feat(mapper): build_bp_context BP 별 분리 + resolve_wa 7 단계 (auto_bp_zone_match / auto_llm_rerank 추가)` (5/20 working tree 변경 commit) | mapper 변경 |
| 9 | `test(parser): 4 시트 unit test 확장 — sub-section skip / solo+next / cross-check / col 인덱스 검증` | test_parser.py 의 6 import caller 모두 통과 |
| 10 | `test(mapper): resolve_wa 7 단계 unit test (각 source 케이스)` | regression 방지 |
| 11 | `chore(parser_llm): deprecation 주석 + env flag CPIA_PARSER=llm 으로 회귀 가능` | parser_llm.py 코드 보존 |
| 12 | **`test(e2e): 10 업체 POC cycle + reports UI 12 정량 기준` (V5)** | **사용자 명시 마지막 단계** |

각 commit 은 단독으로 빌드/테스트 통과. 12 까지 끝나면 reports 페이지가 10 업체 실 데이터로 표시.

---

## §7 위험 / 가정

| 위험 | 가정 | 검증 |
|---|---|---|
| 다른 일보 양식 (다른 사이트) 시트 구조 다름 | 통합 작업일보 양식 동일 (M15X Ph-3 IBL 기준) | V5 의 10 업체 cycle — 일부 fallback case 검출 |
| parser_rule 의 raw 결함 대응 한계 | cross-check warning 으로 검출 | parser_warning stderr — V4 unit test |
| `auto_bp_zone_match` 의 BPSummary.zone=None 빈도 (옵션 2 보수화 결과) | LLM rerank fallback (conf 0.7+) | V2/V3 simulation |
| `auto_llm_rerank` 의 chosen_wa 무작위 (work_content generic 시) | conf<0.7 → HIL 안전망 | V2 case 4/5 입증 |
| 시트2 의 회사명 suffix (창원기전CUB(22.9kV)) zone 활용 안 함 | 본 cycle scope 외 — BPSummary 의 zone 으로 충분 | 향후 cycle |
| PG / Chroma down 시 mapper fail | infra 검증 (CLAUDE.md 메모리 cpia_project.md) | cycle 시작 전 점검 |

---

## §8 향후 cycle 위임

- 시트2 의 raw company suffix (창원기전CUB(22.9kV)) 의 zone 활용 검토 (옵션 2 정신 위배 risk 있음)
- BPSummary 의 work_text_today bp 별 분리 (현재 시트1 group 안 row 들 통합)
- parser_llm.py 코드 제거 (env flag deprecation 후)
- parser_warning 의 PG 영속화 (parser_reports.warnings_jsonb 컬럼 추가)
- 다른 사이트 일보 양식 지원 (M15X Ph-3 IBL 외)

---

*spec 끝. 본 cycle 의 implementation plan 은 별도 `docs/superpowers/plans/2026-05-20-cpia-parser-mapper-refactor-plan.md` 에 후속 작성.*
