# CPIA 09-25 데모 정교화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 09-25 작업일보 7개사(플랜 온고잉)를 prod 파이프라인으로 돌려 Tasks(진행도 실시간+카드 점진)·Reports(7개사 생산성)·Export 에 실데이터로 보이게 한다.

**Architecture:** B1 오프라인 파일 7개 정교화(플랜 역산 물량 + 통합일보 인원/장비) → B3 agent_progress 테이블+노드 emit+FE per-stage 재배선(가짜 애니 제거, 병렬 동시표시, 카드 스트림) → B2 전건 HIL(+resume 후 DB 재persist, LIMIT, resume 백그라운드) → B2.5 wp_summary 날짜 데이터-only 보정 → 업로드 e2e. 디자인 불가침(마크업 무변경, BE/데이터/로직만).

**Tech Stack:** Python3.11(pipeline/.venv, LangGraph, asyncpg, openpyxl) / Next.js(web, TS) / PostgreSQL(43.200.85.209:5532) / ChromaDB. 스펙: docs/superpowers/specs/2026-06-02-cpia-0925-demo-refinement-design.md

---

## 확정 결정 (애매점 26건 해소 — 실행 시 이 결정을 따른다)

플랜 작성 중 드러난 애매점을 실코드 근거로 전부 확정. 실행자는 task 본문과 충돌 시 **이 표를 우선**한다.

**C1 (B1 파일생성)**
1. **산출 경로**: 스크립트는 `data/demo_inputs/20250925/` 만 생성. `data/input/20250925/` 적재는 e2e 업로드(`/api/upload`)가 담당(이중화 금지, DRY).
2. **DB 미도달 테스트**: `built_files` 픽스처에서 `PGClient.connect` 실패 시 `pytest.skip("PG 도달 불가")` (try/except). 정상 환경(43.200.85.209:5532)은 실행.
3. **시트1 boundary**: `today_incr_total = ti['total'] or tc['total']` (incr 0 이어도 누계 total 로 parser group boundary 보장). 가짜 1 주입 금지.
4. **`_pick_diagnosis` wa 인자**: `bp_code`(없으면 `work_content`)를 wa 자리에. hash 결정성만 필요, factor seed 는 별도(행별 다름).
5. **미매칭 활동**: Tasks 만 노출(Reports 누락 허용) — spec §4.4-4 그대로. 실 정합은 mapper+전건 HIL 보정 책임. 잘못된 plan 강제매칭 금지.

**C2 (B3 DB)**
6. **마이그레이션 대상 DB**: `.env` POSTGRES_URL = **AWS PG 43.200.85.209:5532** (테스트·검증·라이브 동일 경로). 거기에 적용. (로컬 컨테이너 병행 시 둘 다.)
7. **마이그레이션 러너**: 신규 추가 안 함. 기존 관례(`docker exec -i … psql … < file` 수동, infra/README §7) 유지 — 25개 기존 마이그레이션 동일.
8. **agent_progress FK**: **FK 없음**(fire-and-forget, 누락/지연 run 에 막히면 안 됨). 테스트는 bare `uuid.uuid4()` 사용(pipeline_runs row 불요). consolidated_reports 관례와 의도적 분기.
9. **standalone 커넥션**: `await asyncpg.connect(postgres_url)` 인라인 — `set_current_node`(db.py:1307)와 동일 패턴. PGClient 풀 재사용 금지.

**C3 (B3 파이프라인 emit)**
10. **mapper 부분행 cleanup**: `api.py` `_bg` 예외 핸들러(set_run_status failed 직전)에 `DELETE FROM mapper_activities WHERE run_id=$1` 추가 — 단일 chokepoint. (C5/api task 로 슬롯; C3 노드는 깨끗하게.)
11. **`_map_one` idx**: 현재 idx 미반환 확정 → `async def _map_one(idx, a) -> tuple[int, Activity]` 로 변경, 청크 insert 는 **원본 idx** 로 `ON CONFLICT (run_id,idx)`, 최종 mapped 는 idx 순 재조립.
12. **optimizer commit 가시성**: gather **전에 pg 1개** 열어 per-task insert + view-build(`agent.py:347`)에 동일 풀 전달(asyncpg execute 자동커밋 → SELECT 전 가시). e2e 에서 `optimizer_advice count == optimizer_view advice count` 검증, 불일치 시 게이지-only fallback.
13. **mapper 청크 K**: `_MAPPER_PROGRESS_CHUNK = int(os.environ.get('CPIA_MAPPER_PROGRESS_CHUNK','20'))` (graph.py:45 옆). ~330활동 → ~17스텝. prorate 후 전량 재INSERT 로 plan_mh/conf 보정(ON CONFLICT 멱등).
14. **깨진 test_parser_node.py**: drive-by 수정(opt B) — `await` + state 에 `run_id`/`postgres_url`/`input_files` 추가(Task 2 가 parser_node 에 이 키 요구). 방치 시 회귀.

**C4 (B3 FE 배선)**
15. **pickCurrentAgent**: `waiting_hil ?? (received>0 && percent<100 && processed!==received) ?? last(done)` (지시문 그대로, 방어적).
16. **Collector/Human Review 카운트**: Collector=input 파일수, Human Review=mapper 수 fallback (agent_progress 미emit). 전건 HIL 이라 부분처리 개념 없음 → waiting_hil_1 분기가 active 처리.
17. **폴링 간격**: 2초 유지(변경 없음). 가짜 애니 제거가 곧 실값 2초 폴링. dbItems 폴링도 2초.
18. **C4 단독 머지**: 가능(빈 agent_progress 맵에서 fallback count 로 동작, -1 안 냄). 단 시연 전 **B3 emit + e2e 1회**로 라이브 게이지 확인 필수(spec §10 'emit 먼저').

**C5 (B2 전건 HIL)**
19. **resume 응답 계약**: `Hil1ResumeAck{ok, run_id}` 즉시 반환(next_node 폐기 — 백그라운드라 다음노드 미상). `/run` 패턴. 실패는 status=failed+로그.
20. **FE resume**: 무변경. 백엔드 즉시반환 → FE `await fetch`(170s timeout) 즉시 resolve → 타임아웃 미도달. (spec '이미 fire-and-forget' 표현은 코드상 부정확하나 결과 정합.)
21. **test_mapper_node 회귀**: 없음(:60 True assert, False assert 부재). 전건 True 회귀 0. 결정론 검증은 신규 `test_mapper_requires_review_all.py`.
22. **재persist 게이트**: `cfg is not None and corrections` → **`cfg is not None`** 로 완화(corrections 빈 dict 여도 재persist). 전건 HIL 은 추천 수용(보정 0건)도 requires_review=False 영속 필요.

**C6 (B2.5 wp 날짜)**
23. **progress_pct**: 변경 안 함(단일일 유지). 본 범위는 start/end_date 2필드만.
24. **plan_start None 가드**: `it.get('plan_start')` None 이면 today fallback(1줄 가드). fallback 쿼리는 ps NOT NULL 보장이나 방어적.
25. **multi-unit plan_start**: head(grp[0]) 대표값 사용(다른 group-level 필드와 동일 패턴). (company,l6) plan CTE MIN/MAX 라 unit 무관 동일.
26. **C6 검증 시점**: 단위(1.1-1.7) 즉시 green. 통합(wp_summary 실 plan기간 확인)은 e2e run_id 에 `_rebuild_views.py` 1회 — e2e 직후로.

---


## CLUSTER C1 — B1 일보 7개 정교화 (spec §4)

전부 `pipeline/scripts/gen_company_files_v2.py` 한 파일 수정. 테스트는 `pipeline/tests/test_gen_company_files_v2.py` 신규(round-trip re-parse 기반 결정론 loop — 진짜 unit 불가 영역은 "생성→재파싱→count assert" 결정론 loop 로 대체). 실행/테스트 환경:
- 생성 실행: `PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python pipeline/scripts/gen_company_files_v2.py [out_company]`
- 테스트: `cd pipeline && PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA .venv/bin/python -m pytest tests/test_gen_company_files_v2.py -v`

**전수조사로 확정한 ground truth (실 호출):**
- 소스 통합일보 재파싱 by_co_* (7개 src): 장평건설 act10/job27/eq45, 남웅건설 48/36/33, 동신패널 24/8/17, 글로벌유명 3/7/13, 광건티엔씨 24/4/13, 태우이엔지 2/4/12, 선보건업 4/2/3.
- 소스 7개사 today_qty 전부 0.0 → 100% 가 역산 path.
- 템플릿 `3.장비현황` max_col=24, **col25 없음**(round-trip 시 set_col25 True/False 둘 다 parser eq=2 동일 통과 — `has_final_flag` 게이트가 col25 부재 시 자동 off). 데이터행 r6 시작: 그룹시작행 col2=공종/col3=BP/col4=장비대분류, 회사명행 col3=회사, count 6교대 col7-12(전일누계)/col13-18(금일투입)/col19-24(금일누계).
- DB activity_master(`m15x-ph3-ibl`)는 **out_company 짧은이름**(광건/태우/선보) 사용 — 7개사 전부 2025-09-25 ongoing 행 존재(광건3/글로벌7/남웅1/동신1/선보25/장평3/태우16). 컬럼: `l5_disc IN ('건축','토목')`, `unit`(m3/m/ton/m2), `l6_main`, `l7_5_activity`, `plan_total_qty`, `plan_start`, `plan_finish`.
- 재사용 함수 실 시그니처 검증됨: `scripts/seed_dummy_year._pick_diagnosis(date_str, wa, company, l6) -> {"tag","diagnosis","recommendations","conditions"}` (`scripts/seed_dummy_year.py:141`); `pipeline/agents/optimizer/_work_content.factor_for(condition, seed_str) -> float` (`_work_content.py:48`). import 시 DB side-effect 없음(확인).

---

### Task 1 — TARGETS 7개사 4-tuple 교체 + src 존재 assert

**Files:**
- Modify `pipeline/scripts/gen_company_files_v2.py:34-45` (TARGETS), `:234-247` (build_one 시그니처/조회), `:250-285` (main 루프 언팩 + assert)
- Create `pipeline/tests/test_gen_company_files_v2.py` (Task 1~4 공용 테스트 모듈)

- [ ] **(1) 실패 테스트 작성** — `pipeline/tests/test_gen_company_files_v2.py` 신규:
```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path("/Users/kyungseoplee/Project Agent/CPIA")
sys.path.insert(0, str(ROOT))

from pipeline.scripts import gen_company_files_v2 as gen  # noqa: E402

EXPECTED = {
    # out_company: (src_company, trade_label, act, job, eq)
    "장평건설": ("장평건설", "토목공사", 10, 27, 45),
    "남웅건설": ("남웅건설", "건축공사", 48, 36, 33),
    "동신패널": ("동신패널", "건축공사", 24, 8, 17),
    "글로벌유명": ("글로벌유명", "건축공사", 3, 7, 13),
    "광건": ("광건티엔씨", "건축공사", 24, 4, 13),
    "태우": ("태우이엔지", "건축공사", 2, 4, 12),
    "선보": ("선보건업", "건축공사", 4, 2, 3),
}


def test_targets_are_seven_4tuples():
    assert len(gen.TARGETS) == 7
    out_names = set()
    for t in gen.TARGETS:
        assert len(t) == 4, f"4-tuple 아님: {t}"
        disp, trade_label, out_company, src_company = t
        assert out_company in EXPECTED, f"미확정 out_company: {out_company}"
        exp_src, exp_trade, *_ = EXPECTED[out_company]
        assert src_company == exp_src
        assert trade_label == exp_trade
        out_names.add(out_company)
    assert out_names == set(EXPECTED)
    # src≠out 3건
    src_neq_out = {t[2] for t in gen.TARGETS if t[2] != t[3]}
    assert src_neq_out == {"광건", "태우", "선보"}
```
- [ ] **(2) FAIL 확인** — `cd pipeline && PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" .venv/bin/python -m pytest tests/test_gen_company_files_v2.py::test_targets_are_seven_4tuples -v`
  기대 출력(원본): `E   AssertionError: 4-tuple 아님: ('(유)성우이엔씨', '건축공사', '성우이엔씨')` 류로 FAIL (현 TARGETS 는 3-tuple 10개).

- [ ] **(3) 구현** — `gen_company_files_v2.py:34-45` TARGETS 를 다음으로 완전 교체:
```python
# (파일표시명, trade_label, out_company, src_company)
# out_company = activity_master 이름(짧은이름 광건/태우/선보), src_company = 통합일보 normalize 결과
TARGETS = [
    ("장평건설", "토목공사", "장평건설", "장평건설"),
    ("남웅건설", "건축공사", "남웅건설", "남웅건설"),
    ("동신패널", "건축공사", "동신패널", "동신패널"),
    ("글로벌유명", "건축공사", "글로벌유명", "글로벌유명"),
    ("광건", "건축공사", "광건", "광건티엔씨"),
    ("태우", "건축공사", "태우", "태우이엔지"),
    ("선보", "건축공사", "선보", "선보건업"),
]
```
- [ ] **(3b)** `build_one`(`:234`) 시그니처를 `norm_co` 단일에서 src/out 분리로 변경:
```python
def build_one(out_company, src_company, raw_name, trade_label, by_co_act, by_co_job, by_co_sum, by_co_eq):
    wb = openpyxl.load_workbook(str(TEMPLATE), keep_vba=True)
    acts = by_co_act.get(src_company, [])
    jobs = by_co_job.get(src_company, [])
    sums = by_co_sum.get(src_company, [])
    eqs = by_co_eq.get(src_company, [])
    trade = acts[0].get("trade") if acts else "건축"
    _fill_sheet4(wb["4.물량"], acts, out_company)
    _fill_sheet1(wb["1.출력인원 현황"], sums, jobs, out_company, trade)
    _fill_sheet2(wb["2.직종별 인원현황"], jobs, out_company, trade)
    _fill_sheet3(wb["3.장비현황"], eqs, out_company, trade)
    fname = f"업체작업일보_M15X_PH3_{raw_name}_{trade_label}_20250925.xlsm"
    out = OUT_DIR / fname
    wb.save(str(out))
    return out, len(acts), len(jobs), len(sums), len(eqs)
```
  주의: `_fill_sheet4`/`_fill_sheet1` 시그니처도 Task 3·4 에서 바뀐다(여기선 호출부만 미리 4-인자/`out_company` 로 맞춰둠). `_fill_sheet4` 의 company 기록은 out_company 로(현재 `acts[0].company`(=src) 사용 → out 으로 교체) — Task 4 에서 본문 수정.
- [ ] **(3c)** `main()`(`:250-285`) 의 by_co_* 빌드 직후, OUT_DIR.mkdir 전에 src 존재 assert 추가:
```python
    src_companies = [t[3] for t in TARGETS]
    for src in src_companies:
        assert by_co_act.get(src), f"src '{src}' act 없음 (by_co_act)"
        assert by_co_job.get(src), f"src '{src}' job 없음 (by_co_job)"
        assert by_co_eq.get(src), f"src '{src}' eq 없음 (by_co_eq)"
```
  그리고 루프 언팩을 4-tuple 로:
```python
    targets = [t for t in TARGETS if (only is None or t[2] == only)]
    ...
    for raw_name, trade_label, out_company, src_company in targets:
        out, na, nj, ns, ne = build_one(
            out_company, src_company, raw_name, trade_label,
            by_co_act, by_co_job, by_co_sum, by_co_eq,
        )
        rp = parse_daily_report(str(out))
        ...
        print(f"     src: act={na} job={nj} sum={ns} eq={ne}")
```
  (filter `t[2] == only` = out_company 매칭 — argv1 은 out_company.)
- [ ] **(4) PASS 확인** — `cd pipeline && PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" .venv/bin/python -m pytest tests/test_gen_company_files_v2.py::test_targets_are_seven_4tuples -v`
  기대(원본): `tests/test_gen_company_files_v2.py::test_targets_are_seven_4tuples PASSED` + `1 passed`.
- [ ] **(5) commit** — `git add pipeline/scripts/gen_company_files_v2.py pipeline/tests/test_gen_company_files_v2.py && git commit -m "C1 Task1: TARGETS 7개 온고잉 4-tuple + src 존재 assert"` (커밋 메시지 끝 Co-Authored-By 라인 포함)

---

### Task 2 — `_fill_sheet3` 구현 (장비, parser sheet3 게이트 미러)

**Files:**
- Modify `pipeline/scripts/gen_company_files_v2.py:226-231` (`_fill_sheet3`)
- Modify `pipeline/tests/test_gen_company_files_v2.py` (round-trip eq count assert)

미러 기준(`parser.py:512-582`): 그룹시작 = col2(공종)+col3(BP, `PH_X-NNN`)+col4(장비대분류) 모두 채움 / 회사명 = 그룹 내 첫 col3 한글값(BP아님) / 장비행 = col4 채움(+`has_final_flag` 면 col25='O') / 6교대 col7-12=전일누계, col13-18=금일투입, col19-24=금일누계 / `equipment_mid`=col5, `equipment_spec`=col6.

- [ ] **(1) 실패 테스트** — `test_gen_company_files_v2.py` 에 round-trip 추가(생성→재파싱→eq count == src):
```python
@pytest.fixture(scope="module")
def built_files(tmp_path_factory):
    """7개사 전부 임시 OUT_DIR 에 생성 후 재파싱 결과 반환 (결정론 loop)."""
    from collections import defaultdict

    from pipeline.agents.parser import parse_daily_report

    tmp = tmp_path_factory.mktemp("gen_out")
    orig_out = gen.OUT_DIR
    gen.OUT_DIR = tmp
    try:
        rep = parse_daily_report(str(gen.SRC))
        by_act, by_job, by_sum, by_eq = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
        for a in rep["activities"]:
            if a.get("trade") in ("건축", "토목"):
                by_act[a.get("company") or ""].append(a)
        for j in rep["job_allocations"]:
            by_job[j.get("company") or ""].append(j)
        for s in rep["bp_summaries"]:
            by_sum[s.get("company") or ""].append(s)
        for e in rep.get("equipment_allocations", []):
            by_eq[e.get("company") or ""].append(e)
        results = {}
        for raw_name, trade_label, out_company, src_company in gen.TARGETS:
            out, na, nj, ns, ne = gen.build_one(
                out_company, src_company, raw_name, trade_label, by_act, by_job, by_sum, by_eq
            )
            results[out_company] = (out, parse_daily_report(str(out)))
        return results
    finally:
        gen.OUT_DIR = orig_out


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet3_equip_count_roundtrip(built_files, out_company):
    exp_eq = EXPECTED[out_company][4]
    _, rp = built_files[out_company]
    eqs = rp.get("equipment_allocations", [])
    assert len(eqs) == exp_eq, f"{out_company} eq {len(eqs)} != {exp_eq}"
    cos = {e.get("company") for e in eqs}
    assert cos == {out_company}, f"{out_company} eq company {cos}"
```
- [ ] **(2) FAIL 확인** — `... -m pytest tests/test_gen_company_files_v2.py::test_sheet3_equip_count_roundtrip -v`
  기대(원본): 각 케이스 `AssertionError: 장평건설 eq 0 != 45` 류 (현 `_fill_sheet3` 가 clear-only).
- [ ] **(3) 구현** — `_fill_sheet3`(`:226-231`) 를 완전 교체:
```python
def _fill_sheet3(ws, equips: list[dict], company: str, trade: str):
    """장비: equipment_allocations 로 채움. parser sheet3 게이트 미러
    (parser.py:512-582): 그룹시작행 col2=공종+col3=BP+col4=장비대분류,
    회사명행 col3=company, 장비행 col4=big/col5=mid/col6=spec,
    6교대 col7-12=전일누계/col13-18=금일투입/col19-24=금일누계, col25='O'."""
    CMAX = 25
    DATA0 = 6
    style_row = 6
    _clear_rows(ws, DATA0, ws.max_row, CMAX)
    if not equips:
        return
    bp = equips[0].get("bp_code") or "PH_X-000"
    # r6: 그룹시작행 (공종 col2 + BP col3 + 첫 장비 col4) — 첫 장비를 함께 기록
    _copy_style_row(ws, style_row, DATA0, CMAX)
    e0 = equips[0]
    _set(ws, DATA0, 2, trade)
    _set(ws, DATA0, 3, bp)
    _write_equip_row(ws, DATA0, e0)
    # r7: 회사명행 (col3=company), 첫 장비는 이미 r6 에 기록됐으므로 r7 은 회사명만
    _copy_style_row(ws, 7, DATA0 + 1, CMAX)
    _set(ws, DATA0 + 1, 3, company)
    # 둘째 장비부터 r8...
    r = DATA0 + 2
    for e in equips[1:]:
        _copy_style_row(ws, style_row, r, CMAX)
        _write_equip_row(ws, r, e)
        r += 1


def _write_equip_row(ws, r, e: dict):
    """장비행 1줄: col4=big col5=mid col6=spec + 6교대 + col25='O'."""
    _set(ws, r, 4, e.get("equipment_big") or "")
    _set(ws, r, 5, e.get("equipment_mid") or "")
    _set(ws, r, 6, e.get("equipment_spec"))
    yc = e.get("count_yesterday_cum") or {}
    ti = e.get("count_today_incr") or {}
    tc = e.get("count_today_cum") or {}
    for i, k in enumerate(SHIFT_KEYS):
        _set(ws, r, 7 + i, int(yc.get(k) or 0) or None)   # 전일누계 c7-12
        _set(ws, r, 13 + i, int(ti.get(k) or 0) or None)  # 금일투입 c13-18
        _set(ws, r, 19 + i, int(tc.get(k) or 0) or None)  # 금일누계 c19-24
    _set(ws, r, 25, "O")
```
  주의: 첫 장비를 그룹시작행(r6)에 기록하면 회사명행(r7)은 장비 없는 순수 회사명행. parser 는 그룹시작행도 `col4` 채워있으면 장비행으로 카운트하므로 첫 장비 손실 없음 (round-trip 프로토타입에서 검증됨 — eq=2 정확). col25='O' 설정 시 `has_final_flag`=True 되어 모든 장비행에 col25='O' 필수(전부 설정함).
- [ ] **(4) PASS 확인** — `... -m pytest tests/test_gen_company_files_v2.py::test_sheet3_equip_count_roundtrip -v`
  기대(원본): 7개 파라미터 케이스 전부 `PASSED` + `7 passed`. (장평 45, 남웅 33, 동신 17, 글로벌 13, 광건 13, 태우 12, 선보 3.)
- [ ] **(5) commit** — `git commit -am "C1 Task2: _fill_sheet3 구현 (parser sheet3 게이트 미러, MergedCell-safe)"`

---

### Task 3 — `_fill_sheet1` job_allocations 회사단위 롤업

**Files:**
- Modify `pipeline/scripts/gen_company_files_v2.py:132-181` (`_fill_sheet1`)
- Modify `pipeline/tests/test_gen_company_files_v2.py`

현 `_fill_sheet1(ws, summaries, company, trade)` 는 bp_summaries 만 사용 → 동신패널(sum=0) 등은 빈 시트. spec §4.3: job_allocations(`by_co_job[src]`) 교대별 workers_incr/cum 합산 → 시트1 BP행. bp_summaries 있으면 우선.

검증 loop: 시트1 자체는 parser 가 bp_summaries 로 재파싱하므로, **시트1 의 금일누계 총계(c37)** 가 job 롤업 total 합과 일치하는지 재파싱 `bp_summaries[0].today_cum_total` 로 확인(결정론).

- [ ] **(1) 실패 테스트** — 추가:
```python
@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet1_rollup_nonzero_when_jobs_present(built_files, out_company):
    """job 이 있으면 시트1 BP행 금일누계 총계 > 0 (롤업 반영)."""
    from collections import defaultdict

    from pipeline.agents.parser import parse_daily_report

    _, rp = built_files[out_company]
    sums = rp.get("bp_summaries", [])
    # 동신패널은 src sum=0 이라 과거엔 빈 시트 → 이제 job 롤업으로 채워져야 함
    if EXPECTED[out_company][3] > 0:  # job count > 0
        assert sums, f"{out_company} 시트1 bp_summaries 비어있음 (job 롤업 실패)"
        total_cum = sum(int(s.get("today_cum_total") or 0) for s in sums)
        assert total_cum > 0, f"{out_company} 시트1 금일누계 총계 0"
```
- [ ] **(2) FAIL 확인** — `... -m pytest tests/test_gen_company_files_v2.py::test_sheet1_rollup_nonzero_when_jobs_present -v`
  기대(원본): `AssertionError: 동신패널 시트1 bp_summaries 비어있음 (job 롤업 실패)` (동신 src sum=0).
- [ ] **(3) 구현** — `_fill_sheet1` 시그니처에 `jobs` 추가하고 롤업 fallback 구현. `build_one`(Task1 에서 `_fill_sheet1(ws, sums, jobs, out_company, trade)` 로 이미 호출) 에 맞춰:
```python
def _fill_sheet1(ws, summaries: list[dict], jobs: list[dict], company: str, trade: str):
    """출력인원 시트1 BP행 롤업. bp_summaries 있으면 우선, 없으면 job_allocations
    교대별 workers_today_incr/cum + yesterday 합산. c24-29=금일투입/c30=총,
    c31-36=금일누계/c37=총, c10-15=전일투입, c17-22=전일누계."""
    CMAX = 37
    DATA0 = 5
    style_row = 5
    _clear_rows(ws, DATA0, ws.max_row, CMAX)

    def _agg_shift(rows, key):
        agg = {k: 0 for k in SHIFT_KEYS}
        for x in rows:
            d = x.get(key) or {}
            for k in SHIFT_KEYS:
                agg[k] += int(d.get(k) or 0)
        return agg

    if summaries:
        src = summaries
        bp = summaries[0].get("bp_code") or "PH_X-000"
        work_today = " | ".join(
            s.get("work_text_today") or "" for s in summaries if s.get("work_text_today")
        )[:200]
        ti = _agg_shift(src, "workers_today_incr")
        tc = _agg_shift(src, "workers_today_cum")
        yi = _agg_shift(src, "workers_yesterday_incr")
        yc = _agg_shift(src, "workers_yesterday_cum")
        today_incr_total = sum(int(s.get("today_incr_total") or 0) for s in summaries) or ti["total"]
        today_cum_total = sum(int(s.get("today_cum_total") or 0) for s in summaries) or tc["total"]
    elif jobs:
        bp = jobs[0].get("bp_code") or "PH_X-000"
        work_today = ""
        ti = _agg_shift(jobs, "workers_today_incr")
        tc = _agg_shift(jobs, "workers_today_cum")
        yi = {k: 0 for k in SHIFT_KEYS}
        yc = _agg_shift(jobs, "workers_yesterday_cum")
        today_incr_total = ti["total"]
        today_cum_total = tc["total"]
    else:
        return

    # r5: BP코드행
    _copy_style_row(ws, style_row, DATA0, CMAX)
    _set(ws, DATA0, 4, trade)
    _set(ws, DATA0, 5, bp)
    _set(ws, DATA0, 7, work_today)
    _set(ws, DATA0, 8, work_today)
    for i, k in enumerate(SHIFT_KEYS):
        _set(ws, DATA0, 10 + i, yi[k] or None)  # 전일투입 c10-15
        _set(ws, DATA0, 17 + i, yc[k] or None)  # 전일누적 c17-22
        _set(ws, DATA0, 24 + i, ti[k] or None)  # 금일투입 c24-29
        _set(ws, DATA0, 31 + i, tc[k] or None)  # 금일누적 c31-36
    _set(ws, DATA0, 30, today_incr_total or None)  # 금일투입 총
    _set(ws, DATA0, 37, today_cum_total or None)  # 금일누적 총
    # r6: 회사명행
    _copy_style_row(ws, 6, DATA0 + 1, CMAX)
    _set(ws, DATA0 + 1, 5, company)
```
  주의: parser `_parse_sheet1_bp_summaries`(`:213-219`) skip 게이트 — `today_incr_total`(c30) 가 0 이면 group boundary 미감지(merged/solo 둘 다 c30 값 필요). 따라서 c30 에 반드시 truthy 값이 들어가야 BP행이 재파싱됨. job 롤업 시 `today_incr_total = ti["total"]` 이 0 이면 행 누락 → fallback 로 `tc["total"]`(금일누계) 사용하도록 `today_incr_total = ti["total"] or tc["total"]` 로 보강 권장(아래 ambiguity 참조).
- [ ] **(4) PASS 확인** — `... -m pytest tests/test_gen_company_files_v2.py::test_sheet1_rollup_nonzero_when_jobs_present -v`
  기대(원본): 7개 케이스 전부 `PASSED`.
- [ ] **(5) commit** — `git commit -am "C1 Task3: _fill_sheet1 job_allocations 회사단위 롤업 (bp_summaries 우선)"`

---

### Task 4 — `_today_qty_fill` 온고잉 plan 역산 (gen-time DB read)

**Files:**
- Modify `pipeline/scripts/gen_company_files_v2.py:50-62` (`_today_qty_fill` → plan 매칭), `:91-129` (`_fill_sheet4` 시그니처+호출), 상단 import 추가, `main()` DB load
- Modify `pipeline/tests/test_gen_company_files_v2.py`

spec §4.4: 원본 today_qty>0 보존. 0/None 만:
1. out_company 의 `l5_disc IN ('건축','토목')` activity_master 중 09-25 ongoing(`plan_start<=date<=plan_finish`) + `unit` 일치 + `work_content`↔(`l6_main`+`l7_5_activity`) 토큰 overlap 최고 → `plan_total`, `total_days=(pf-ps+1)`.
2. `factor = factor_for(diag["conditions"][0], seed)`, seed=`f"2025-09-25|{out_company}|{work_content}"`, `diag=_pick_diagnosis("2025-09-25", bp_code 또는 work_content, out_company, l6_main매칭값)`.
3. `today_qty = max(1, round(factor * plan_total/total_days, 1))`.
4. 미매칭: `today_qty = max(1, round(factor * 파일총물량/nominal, 1))`, nominal = 회사 ongoing plan 기간 중앙값(정수, 최소 1).
5. yesterday_cum 원본 유지.

**gen-time DB access 패턴(seed_dummy_year 미러):** `from pipeline.db import PGClient`; `pg=PGClient(os.environ.get("POSTGRES_URL", DEFAULT_PG_URL)); await pg.connect()`; `await pg._pool.fetch(...)`. gen 스크립트 main 을 async 화하거나 동기 main 안에서 `asyncio.run(_load_am(out_companies))` 1회 호출로 `{out_company: [am_row...]}` dict 빌드 후 `_fill_sheet4` 에 주입(LLM/네트워크는 build_one 루프 밖 1회).

**조회 쿼리(보여줄 것):**
```sql
SELECT company, l6_main, l7_5_activity, unit, plan_total_qty, plan_start, plan_finish
FROM activity_master
WHERE site_id = $1
  AND l5_disc IN ('건축','토목')
  AND company = ANY($2::text[])
  AND plan_start <= $3 AND plan_finish >= $3
ORDER BY company, plan_start
```
($1='m15x-ph3-ibl', $2=out_companies, $3=date(2025,9,25))

- [ ] **(1) 실패 테스트** — 추가(0 today_qty 0건 + factor 정합 결정론):
```python
@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet4_no_zero_today_qty(built_files, out_company):
    """역산 후 today_qty==0 행 0건."""
    _, rp = built_files[out_company]
    zero = [a for a in rp["activities"] if not (a.get("today_qty") and float(a["today_qty"]) > 0)]
    assert not zero, f"{out_company} today_qty 0 행 {len(zero)}건"


@pytest.mark.parametrize("out_company", list(EXPECTED))
def test_sheet4_company_is_out_company(built_files, out_company):
    """파일 파싱 company == out_company (광건/태우/선보 정렬 확인)."""
    _, rp = built_files[out_company]
    cos = {a.get("company") for a in rp["activities"]}
    assert cos == {out_company}, f"{out_company}: {cos}"
```
  ※ `built_files` 픽스처(Task2)가 DB 를 읽으므로 DB 도달 가능해야 함(43.200.85.209:5532). 도달 불가 환경이면 이 클래스 테스트는 `pytest.mark.skipif`(POSTGRES 연결 실패) 처리 — 아래 ambiguity 참조.
- [ ] **(2) FAIL 확인** — `... -m pytest tests/test_gen_company_files_v2.py::test_sheet4_no_zero_today_qty tests/test_gen_company_files_v2.py::test_sheet4_company_is_out_company -v`
  기대(원본): `test_sheet4_company_is_out_company[광건]` → `AssertionError: 광건: {'광건티엔씨'}` (현재 `_fill_sheet4` 가 `acts[0].company`=src 기록). today_qty 는 현 해시팩터로 0 은 아니나 plan 정합 아님.
- [ ] **(3) 구현** —
  - 상단 import 추가(`:18` 이후):
```python
import asyncio
import os
from datetime import date

from pipeline.db import PGClient  # noqa: E402  (sys.path.insert 이후)
from pipeline.agents.optimizer._work_content import factor_for  # noqa: E402
from scripts.seed_dummy_year import _pick_diagnosis  # noqa: E402

SITE_ID = "m15x-ph3-ibl"
ANCHOR_DATE = date(2025, 9, 25)
DEFAULT_PG_URL = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"
```
  - DB load helper + 매칭/역산 함수 신규:
```python
def _tokens(*parts: str) -> set[str]:
    import re
    s = " ".join(p for p in parts if p)
    return set(t for t in re.split(r"[\s/·,()]+", s) if len(t) >= 2)


async def _load_ongoing_am(out_companies: list[str]) -> dict[str, list[dict]]:
    pg = PGClient(os.environ.get("POSTGRES_URL", DEFAULT_PG_URL))
    await pg.connect()
    try:
        rows = await pg._pool.fetch(
            """
            SELECT company, l6_main, l7_5_activity, unit, plan_total_qty, plan_start, plan_finish
            FROM activity_master
            WHERE site_id = $1 AND l5_disc IN ('건축','토목')
              AND company = ANY($2::text[])
              AND plan_start <= $3 AND plan_finish >= $3
            ORDER BY company, plan_start
            """,
            SITE_ID, out_companies, ANCHOR_DATE,
        )
        by = defaultdict(list)
        for r in rows:
            d = dict(r)
            d["total_days"] = (d["plan_finish"] - d["plan_start"]).days + 1
            by[d["company"]].append(d)
        return by
    finally:
        await pg._pool.close()


def _match_plan(a: dict, am_rows: list[dict]) -> dict | None:
    """unit 일치 + work_content↔(l6_main+l7_5_activity) 토큰 overlap 최고."""
    unit = (a.get("unit") or "").strip()
    wc = a.get("work_content") or ""
    wt = _tokens(wc)
    best, best_score = None, 0
    for am in am_rows:
        if (am.get("unit") or "").strip() != unit:
            continue
        score = len(wt & _tokens(am.get("l6_main") or "", am.get("l7_5_activity") or ""))
        if score > best_score:
            best, best_score = am, score
    return best if best_score > 0 else None


def _reverse_fill_today_qty(a: dict, out_company: str, am_rows: list[dict], nominal: int) -> float:
    tq = a.get("today_qty")
    if tq is not None and float(tq) > 0:
        return float(tq)
    wc = a.get("work_content") or "x"
    seed = f"2025-09-25|{out_company}|{wc}"
    am = _match_plan(a, am_rows)
    if am is not None:
        diag = _pick_diagnosis("2025-09-25", a.get("bp_code") or wc, out_company, am.get("l6_main") or "")
        cond = diag["conditions"][0] if diag["conditions"] else "정상"
        factor = factor_for(cond, seed)
        plan_total = float(am.get("plan_total_qty") or 0)
        total_days = max(1, int(am.get("total_days") or 1))
        return max(1.0, round(factor * plan_total / total_days, 1))
    # 미매칭 fallback: nominal 기간 기준
    diag = _pick_diagnosis("2025-09-25", wc, out_company, "")
    cond = diag["conditions"][0] if diag["conditions"] else "정상"
    factor = factor_for(cond, seed)
    plan = float(a.get("plan_total_qty") or 0)
    return max(1.0, round(factor * plan / max(1, nominal), 1))
```
  - `_fill_sheet4` 시그니처에 `out_company`, `am_rows`, `nominal` 주입하고 회사기록·역산 교체. 현 `_today_qty_fill(a)` 호출(`:115`)을 `_reverse_fill_today_qty(a, out_company, am_rows, nominal)` 로, `company = acts[0].get("company")`(`:103`) 를 `company = out_company` 로 교체. 시그니처:
```python
def _fill_sheet4(ws, acts: list[dict], out_company: str, am_rows: list[dict], nominal: int):
    ...
    company = out_company
    ...
        tq = _reverse_fill_today_qty(a, out_company, am_rows, nominal)
```
  - `build_one` 에서 `am_rows = am_by_co.get(out_company, [])`, `nominal` = ongoing plan 기간 중앙값:
```python
    am_rows = am_by_co.get(out_company, [])
    days = sorted(int(r["total_days"]) for r in am_rows) if am_rows else []
    nominal = max(1, days[len(days) // 2]) if days else 1
    _fill_sheet4(wb["4.물량"], acts, out_company, am_rows, nominal)
```
    → `build_one` 에 `am_by_co` 인자 추가.
  - `main()` 에서 by_co_* 빌드 후 1회 DB load:
```python
    out_companies = [t[2] for t in TARGETS]
    am_by_co = asyncio.run(_load_ongoing_am(out_companies))
    for src in (t[3] for t in TARGETS):  # (기존 assert 유지)
        ...
    ...
    for raw_name, trade_label, out_company, src_company in targets:
        out, na, nj, ns, ne = build_one(
            out_company, src_company, raw_name, trade_label,
            by_co_act, by_co_job, by_co_sum, by_co_eq, am_by_co,
        )
```
  - 픽스처(Task2 `built_files`)도 `am_by_co = asyncio.run(gen._load_ongoing_am([t[2] for t in gen.TARGETS]))` 추가 후 `build_one(..., am_by_co)` 로 호출하도록 수정.
- [ ] **(4) PASS 확인** — `... -m pytest tests/test_gen_company_files_v2.py -v`
  기대(원본): `test_sheet4_no_zero_today_qty[*]` 7건 + `test_sheet4_company_is_out_company[*]` 7건 전부 `PASSED`, 전체 `... passed`.
- [ ] **(5) commit** — `git commit -am "C1 Task4: _today_qty_fill 온고잉 plan 역산 (gen-time activity_master read + factor_for/_pick_diagnosis 재사용)"`

---

### Task 5 — 생성 검증 (단건 + 전건) 및 main 검증 assert 강화

**Files:**
- Modify `pipeline/scripts/gen_company_files_v2.py:272-285` (검증 출력 → assert)

- [ ] **(1) loop** — main 의 검증 print 루프를 assert 로 강화(재파싱 카운트 == src + company == out_company + 0 today_qty 0건):
```python
    for raw_name, trade_label, out_company, src_company in targets:
        out, na, nj, ns, ne = build_one(
            out_company, src_company, raw_name, trade_label,
            by_co_act, by_co_job, by_co_sum, by_co_eq, am_by_co,
        )
        rp = parse_daily_report(str(out))
        pa, pj = rp["activities"], rp["job_allocations"]
        pe = rp.get("equipment_allocations", [])
        cos = sorted({x.get("company") for x in pa})
        zero_tq = [a for a in pa if not (a.get("today_qty") and float(a["today_qty"]) > 0)]
        assert len(pa) == na, f"{out_company} act {len(pa)} != src {na}"
        assert len(pe) == ne, f"{out_company} eq {len(pe)} != src {ne}"
        assert cos == [out_company], f"{out_company} company {cos}"
        assert not zero_tq, f"{out_company} today_qty 0행 {len(zero_tq)}건"
        print(f"  OK {out.name}: act={len(pa)}={na} eq={len(pe)}={ne} job={len(pj)} co={cos} zero_tq=0")
```
- [ ] **(2) 단건 실행** — `PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" pipeline/.venv/bin/python pipeline/scripts/gen_company_files_v2.py 광건`
  기대(원본): `OK 업체작업일보_M15X_PH3_광건_건축공사_20250925.xlsm: act=24=24 eq=13=13 job=4 co=['광건'] zero_tq=0` (assert 통과 = 생산성 정합).
- [ ] **(3) 전건 실행** — `PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" pipeline/.venv/bin/python pipeline/scripts/gen_company_files_v2.py`
  기대(원본): 7줄 `OK ...` 출력, AssertionError 없이 종료. 7개 .xlsm 파일이 `data/demo_inputs/20250925/` 에 생성.
- [ ] **(4) 골든 수동대조** — `... pytest tests/test_gen_company_files_v2.py -v` 전체 green + 장평(10/27/45)·남웅(48/36/33) 카운트 EXPECTED 와 일치 확인(테스트가 강제).
- [ ] **(5) commit** — `git commit -am "C1 Task5: 생성 검증 assert 강화 (카운트/company/0-today_qty)"`


## Cluster C2 — B3 DB layer (Spec §6.1–6.2)

Two tasks: (1) new migration `agent_progress` table, (2) `db.py` async `upsert_agent_progress` standalone helper mirroring `set_current_node`. Verified facts:

- `set_current_node` (`pipeline/db.py:1299-1318`) and `set_run_status` (`:1321-1339`) are **module-level** (not `PGClient` methods), use `await asyncpg.connect(postgres_url)` → `try/finally conn.close()` → bare `except Exception: pass`. Signature normalizes `run_id` via `rid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id`.
- `insert_mapper_activities_batch` (`:647-744`) shows the in-repo `ON CONFLICT ... DO UPDATE SET col = EXCLUDED.col` style and is a `PGClient` method (pool-based) — different surface from the standalone helpers; we mirror the **standalone** `set_current_node` per spec §6.2.
- Migration files: `infra/postgres/migrations/`, named `YYYY-MM-DD_<desc>.sql` (latest: `2026-05-27_*.sql`). Style: leading `-- <date>: <desc>` + `-- 참조: <spec>` comments, `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, optional `COMMENT ON TABLE`. Example: `2026-05-27_consolidated_reports.sql`.
- **Migration runner = manual `psql` redirect**, no automated runner. Per `infra/README.md:103-115`: `docker exec -i cpia-postgres psql -U cpia -d cpia < postgres/migrations/<file>.sql`. The DB used by the demo/tests is the AWS PG (verified reachable at `43.200.85.209:5532/cpia` via `.env` `POSTGRES_URL`), not necessarily the `cpia-postgres` container — see Open Ambiguity #1.
- Spec §6.1 table has **NO foreign key** on `run_id` (unlike `consolidated_reports.run_id REFERENCES pipeline_runs`). This is deliberate (fire-and-forget progress, must not block on FK). So the test does **not** need a `pipeline_runs` row — confirmed by reading the spec block at `docs/superpowers/specs/2026-06-02-cpia-0925-demo-refinement-design.md:185-201`.
- Test harness: `pipeline/pyproject.toml:32-35` → `asyncio_mode = "auto"`, `pythonpath = ["."]`, `testpaths = ["tests"]`. `conftest.py:14` `load_dotenv(CPIA_ROOT / ".env")` so `POSTGRES_URL` is available. Existing live-PG test pattern: `test_db_consolidated_reports.py` (`pytestmark = pytest.mark.asyncio`, `POSTGRES_URL = os.environ["POSTGRES_URL"]`, local `pg` fixture that `PGClient(POSTGRES_URL)` → `connect()` → `yield` → `close()`).
- Verified live PG reachable and `agent_progress` does not yet exist (`SELECT to_regclass('public.agent_progress')` → `None`).

Run all pipeline commands as:
`PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -m pytest ...`

---

### Task 1 — Migration: `agent_progress` table

**Files:**
- Create: `/Users/kyungseoplee/Project Agent/CPIA/infra/postgres/migrations/2026-06-02_add_agent_progress.sql`
- Verification: apply SQL to live PG, then `SELECT to_regclass`/column introspection.

This is a `.sql` DDL artifact — a Python unit test cannot drive the migration runner (manual `psql`). The deterministic pass/fail loop = **apply the file, then re-introspect the live schema and assert columns/PK match the spec**.

- [ ] **(1) Write the failing check (schema absent).** Run, expect `agent_progress` missing:
  ```bash
  PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -c "
  import asyncio, asyncpg, os
  from pathlib import Path
  from dotenv import load_dotenv
  load_dotenv(Path('/Users/kyungseoplee/Project Agent/CPIA/.env'))
  async def m():
      c = await asyncpg.connect(os.environ['POSTGRES_URL'])
      print('agent_progress:', await c.fetchval(\"SELECT to_regclass('public.agent_progress')\"))
      await c.close()
  asyncio.run(m())
  "
  ```
  Expected output (FAIL = table not yet created):
  ```
  agent_progress: None
  ```

- [ ] **(2) Create the migration file** at `/Users/kyungseoplee/Project Agent/CPIA/infra/postgres/migrations/2026-06-02_add_agent_progress.sql` with COMPLETE content (matches existing style: leading comments, `IF NOT EXISTS`, index, table comment; **no FK on run_id** per spec §6.1):
  ```sql
  -- 2026-06-02: B3 진행도 per-item 실시간 — agent_progress 신설
  -- 참조: spec 2026-06-02-cpia-0925-demo-refinement-design.md §6.1
  -- 노드별 upsert_agent_progress(db.py) 가 (run_id, agent) UPSERT.
  -- run_id 는 FK 미설정 (fire-and-forget progress write 가 FK 로 막히면 안 됨).

  CREATE TABLE IF NOT EXISTS agent_progress (
    run_id     UUID        NOT NULL,
    agent      TEXT        NOT NULL,   -- 'parser'|'mapper'|'atomizer'|'exporter'|'forecaster'|'optimizer'
    processed  INTEGER     NOT NULL DEFAULT 0,
    total      INTEGER     NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, agent)
  );

  CREATE INDEX IF NOT EXISTS idx_agent_progress_run
    ON agent_progress (run_id);

  COMMENT ON TABLE agent_progress IS
    'B3 진행도 per-(run,agent) 카운터. upsert_agent_progress 가 GREATEST 로 단조 보장. 본 cycle 2026-06-02.';
  ```

- [ ] **(3) Apply the migration to the demo/test PG.** Per Open Ambiguity #1, confirm which PG the demo runs against, then apply. If it is the `cpia-postgres` container (per `infra/README.md:109-113`):
  ```bash
  docker exec -i cpia-postgres psql -U cpia -d cpia \
    < "/Users/kyungseoplee/Project Agent/CPIA/infra/postgres/migrations/2026-06-02_add_agent_progress.sql"
  ```
  If the demo/tests run against the AWS PG (`43.200.85.209:5532`, the `POSTGRES_URL` in `.env`), apply there with `psql "$POSTGRES_URL" -f <file>` instead (recommended — that is the PG the verification + Task 2 test actually connect to). Expected output:
  ```
  CREATE TABLE
  CREATE INDEX
  COMMENT
  ```

- [ ] **(4) Re-introspect the live schema (PASS).** Run, expect table present with the spec's exact columns + PK:
  ```bash
  PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -c "
  import asyncio, asyncpg, os
  from pathlib import Path
  from dotenv import load_dotenv
  load_dotenv(Path('/Users/kyungseoplee/Project Agent/CPIA/.env'))
  async def m():
      c = await asyncpg.connect(os.environ['POSTGRES_URL'])
      print('reg:', await c.fetchval(\"SELECT to_regclass('public.agent_progress')\"))
      cols = await c.fetch(\"\"\"
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_name='agent_progress' ORDER BY ordinal_position
      \"\"\")
      for r in cols: print(dict(r))
      pk = await c.fetch(\"\"\"
        SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
        WHERE i.indrelid='public.agent_progress'::regclass AND i.indisprimary
        ORDER BY a.attname
      \"\"\")
      print('pk:', [r['attname'] for r in pk])
      await c.close()
  asyncio.run(m())
  "
  ```
  Expected output (PASS):
  ```
  reg: agent_progress
  {'column_name': 'run_id', 'data_type': 'uuid', 'column_default': None}
  {'column_name': 'agent', 'data_type': 'text', 'column_default': None}
  {'column_name': 'processed', 'data_type': 'integer', 'column_default': '0'}
  {'column_name': 'total', 'data_type': 'integer', 'column_default': '0'}
  {'column_name': 'updated_at', 'data_type': 'timestamp with time zone', 'column_default': 'now()'}
  pk: ['agent', 'run_id']
  ```

- [ ] **(5) Commit.** (Per project: branch first if on default; CLAUDE.md notes direct-merge precedent `d317be9` is allowed when explicitly told.)
  ```bash
  cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  git add infra/postgres/migrations/2026-06-02_add_agent_progress.sql && \
  git commit -m "$(cat <<'EOF'
  feat(infra): add agent_progress table for B3 per-item progress

  spec 2026-06-02 §6.1. (run_id, agent) PK, no FK (fire-and-forget).

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2 — `db.py` `upsert_agent_progress` (TDD, live PG)

**Files:**
- Modify: `/Users/kyungseoplee/Project Agent/CPIA/pipeline/db.py` (add module-level fn after `set_run_status`, i.e. after `:1339`)
- Create (Test): `/Users/kyungseoplee/Project Agent/CPIA/pipeline/tests/test_db_agent_progress.py`

Test hits the **live PG** (`POSTGRES_URL` from `.env` via `conftest.py:14`), mirroring `test_db_consolidated_reports.py`. No `pipeline_runs` row needed — `agent_progress.run_id` has no FK (Task 1). Each test uses a fresh `uuid.uuid4()` run_id and a `try/finally` cleanup `DELETE` so it is idempotent and leaves no rows.

- [ ] **(1) Write the failing test** at `/Users/kyungseoplee/Project Agent/CPIA/pipeline/tests/test_db_agent_progress.py` with COMPLETE content:
  ```python
  # pipeline/tests/test_db_agent_progress.py
  """(B3) upsert_agent_progress TDD — GREATEST monotonicity + total upsert.

  spec 2026-06-02-cpia-0925-demo-refinement-design.md §6.2.
  실 PG (POSTGRES_URL, conftest load_dotenv) 에 붙는다. agent_progress.run_id 는
  FK 없음 → pipeline_runs row 불필요. fresh run_id + finally DELETE 로 멱등.
  """

  from __future__ import annotations

  import os
  import uuid

  import asyncpg
  import pytest

  from pipeline.db import upsert_agent_progress

  pytestmark = pytest.mark.asyncio

  POSTGRES_URL = os.environ["POSTGRES_URL"]


  async def _row(run_id: uuid.UUID, agent: str) -> asyncpg.Record | None:
      con = await asyncpg.connect(POSTGRES_URL)
      try:
          return await con.fetchrow(
              "SELECT processed, total FROM agent_progress WHERE run_id=$1 AND agent=$2",
              run_id,
              agent,
          )
      finally:
          await con.close()


  async def _cleanup(run_id: uuid.UUID) -> None:
      con = await asyncpg.connect(POSTGRES_URL)
      try:
          await con.execute("DELETE FROM agent_progress WHERE run_id=$1", run_id)
      finally:
          await con.close()


  async def test_insert_then_greatest_keeps_max() -> None:
      """두 번째 upsert 의 processed 가 더 작아도 GREATEST 가 max 유지, total 은 갱신."""
      run_id = uuid.uuid4()
      try:
          # 1차: processed=5, total=10 (INSERT)
          await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 5, 10)
          r1 = await _row(run_id, "mapper")
          assert r1 is not None
          assert r1["processed"] == 5
          assert r1["total"] == 10

          # 2차: processed=3 (작아짐) → GREATEST(5,3)=5 유지. total=12 → 갱신.
          await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 3, 12)
          r2 = await _row(run_id, "mapper")
          assert r2["processed"] == 5, "GREATEST 가 out-of-order 작은 값으로 후퇴시키면 안 됨"
          assert r2["total"] == 12, "total 은 EXCLUDED 로 항상 갱신"

          # 3차: processed=8 (커짐) → GREATEST(5,8)=8 로 전진.
          await upsert_agent_progress(POSTGRES_URL, run_id, "mapper", 8, 12)
          r3 = await _row(run_id, "mapper")
          assert r3["processed"] == 8
          assert r3["total"] == 12
      finally:
          await _cleanup(run_id)


  async def test_str_run_id_accepted() -> None:
      """run_id 가 str 이어도 set_current_node 처럼 정규화되어 동작."""
      run_id = uuid.uuid4()
      try:
          await upsert_agent_progress(POSTGRES_URL, str(run_id), "parser", 1, 7)
          r = await _row(run_id, "parser")
          assert r is not None
          assert r["processed"] == 1
          assert r["total"] == 7
      finally:
          await _cleanup(run_id)


  async def test_swallow_on_bad_url() -> None:
      """connect 실패해도 예외 swallow (fire-and-forget) — raise 하지 않음."""
      # 아무 것도 raise 되지 않으면 통과.
      await upsert_agent_progress(
          "postgresql://nouser:nopass@127.0.0.1:1/nodb", uuid.uuid4(), "mapper", 1, 1
      )
  ```

- [ ] **(2) Run the test, expect FAIL** (import error — `upsert_agent_progress` does not exist yet):
  ```bash
  PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -m pytest pipeline/tests/test_db_agent_progress.py -q
  ```
  Expected output (FAIL):
  ```
  ImportError: cannot import name 'upsert_agent_progress' from 'pipeline.db'
  ...
  ERROR pipeline/tests/test_db_agent_progress.py
  ```

- [ ] **(3) Implement `upsert_agent_progress`** — add immediately after `set_run_status` (after `/Users/kyungseoplee/Project Agent/CPIA/pipeline/db.py:1339`). COMPLETE code, mirrors `set_current_node` exactly (standalone `asyncpg.connect`, `try/finally close`, bare `except Exception: pass`, `rid` normalization):
  ```python


  async def upsert_agent_progress(
      postgres_url: str,
      run_id: str | uuid.UUID,
      agent: str,
      processed: int,
      total: int,
  ) -> None:
      """agent_progress (run_id, agent) UPSERT — B3 per-item 진행도.

      Web UI (tasks/page) 가 polling 으로 processed/total 을 읽어 게이지 표시.
      GREATEST = out-of-order concurrent upsert 에서 processed 단조 보장
      (작은 값이 와도 후퇴 안 함). total 은 항상 EXCLUDED 로 갱신.
      실패 시 silent — pipeline 본 동작 막지 않음 (progress 표시는 secondary).
      """
      rid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
      try:
          conn = await asyncpg.connect(postgres_url)
          try:
              await conn.execute(
                  """
                  INSERT INTO agent_progress (run_id, agent, processed, total, updated_at)
                  VALUES ($1, $2, $3, $4, now())
                  ON CONFLICT (run_id, agent) DO UPDATE SET
                      processed  = GREATEST(agent_progress.processed, EXCLUDED.processed),
                      total      = EXCLUDED.total,
                      updated_at = now()
                  """,
                  rid,
                  agent,
                  processed,
                  total,
              )
          finally:
              await conn.close()
      except Exception:
          # progress write 실패는 본 동작 영향 X.
          pass
  ```

- [ ] **(4) Run the test, expect PASS** (requires Task 1 migration applied to the same PG `POSTGRES_URL` points at):
  ```bash
  PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" "/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -m pytest pipeline/tests/test_db_agent_progress.py -v
  ```
  Expected output (PASS):
  ```
  pipeline/tests/test_db_agent_progress.py::test_insert_then_greatest_keeps_max PASSED
  pipeline/tests/test_db_agent_progress.py::test_str_run_id_accepted PASSED
  pipeline/tests/test_db_agent_progress.py::test_swallow_on_bad_url PASSED
  3 passed in ...s
  ```

- [ ] **(5) Commit.**
  ```bash
  cd "/Users/kyungseoplee/Project Agent/CPIA" && \
  git add pipeline/db.py pipeline/tests/test_db_agent_progress.py && \
  git commit -m "$(cat <<'EOF'
  feat(db): add upsert_agent_progress emit primitive (B3)

  spec 2026-06-02 §6.2. standalone asyncpg, exception-swallow (mirrors
  set_current_node). ON CONFLICT GREATEST keeps processed monotone,
  total always updated. live-PG TDD test.

  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Notes for downstream clusters (not this task's scope)
- Node-level `await upsert_agent_progress(...)` wiring (parser/mapper/atomizer/exporter/forecaster/optimizer, spec §6.3) and the `web/app/api/runs/progress/route.ts` rewrite (§6.5) are separate clusters. This cluster only delivers the table + emit primitive.
- The `parser_node` `run_id`/`postgres_url` wiring gap noted in spec §6.3 (`parser_node.py:47/52-57`) is a §6.3 concern, not C2.


> Scope: pipeline-side only (`pipeline/db.py`, `pipeline/agents/parser_node.py`, `pipeline/graph.py`, `pipeline/agents/atomizer.py`, `pipeline/agents/exporter.py`, `pipeline/agents/forecaster/agent.py`, `pipeline/agents/optimizer/agent.py` + the `agent_progress` migration). The API/FE rewrite of `web/app/api/runs/progress/route.ts` and `tasks/page.tsx` is spec §6.5 and belongs to a different cluster — NOT here. These tasks only produce the `agent_progress` rows + card-streaming inserts that that route will read.
>
> Env for every command below:
> `export PY="/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python"` and `export PP="/Users/kyungseoplee/Project Agent/CPIA"` then run pytest as `PYTHONPATH=$PP $PY -m pytest ...` from any cwd.
> Tests live in `pipeline/tests/`. `asyncio_mode = "auto"` (pipeline/pyproject.toml:33) so async tests need no decorator, but match existing style and add `@pytest.mark.asyncio`.
> All new `.py` start with `from __future__ import annotations`.
> Decided constant: **K = 20** for mapper chunk size (see open_ambiguities #4). Use a module-level `_MAPPER_PROGRESS_CHUNK = int(os.environ.get("CPIA_MAPPER_PROGRESS_CHUNK", "20"))` in graph.py next to `_MAPPER_CONCURRENCY` (graph.py:45).

---

### Task 1 — agent_progress 테이블 + upsert_agent_progress (→ CLUSTER C2 에서 구현)

B3 DB 레이어(마이그레이션 + `upsert_agent_progress` primitive)는 **CLUSTER C2 의 Task 1·2 에서 정의·구현**한다. 본 클러스터(C3)는 그 primitive 를 **사용**만 하므로 여기서 재구현하지 않는다(중복 제거). 실행 순서: C2 Task 1·2(테이블 생성+적용+upsert helper) 완료 → 아래 C3 Task 2~8.

---

### Task 2 — parser_node: thread run_id + postgres_url from state, emit (0, len(files)) then per-file processed

**Files:**
- Modify: `pipeline/agents/parser_node.py` (signature still `(state)`; read `state["run_id"]`/`state["postgres_url"]` exactly like exporter.py:330,332 reads `state["run_id"]`/`state["postgres_url"]`)
- Test: `pipeline/tests/test_parser_node_progress.py` (Create)

Real-code anchors: `parser_node` is `async def parser_node(state)` at parser_node.py:40. Files gathered at parser_node.py:47-56. `state` carries `run_id`/`postgres_url`/`input_files` at runtime (state.py:230,265,232; api.py:282-286 injects them). exporter.py:330-332 is the precedent for reading them: `run_id = _uuid.UUID(state["run_id"])` and `pg = PGClient(state["postgres_url"])`. Counter-sync rule: increment a plain `int` synchronously, capture local, then `await upsert` (no await between read-modify-write).

**REQUIRED (확정결정 #14):** 기존 `pipeline/tests/test_parser_node.py` 는 `parser_node(state)` 를 await 없이 호출하고 state 에 `run_id`/`postgres_url` 가 없다. 본 Task 가 parser_node 에 그 키 읽기를 추가하면 이 테스트가 **하드 FAIL(회귀)** 한다. 신규 progress 테스트와 별개로, 이 깨진 테스트를 drive-by 로 반드시 고친다(방치 금지).

- [ ] **(drive-by, 확정 #14) `pipeline/tests/test_parser_node.py` 수정** — 두 테스트를 `@pytest.mark.asyncio` + `await parser_node(state)` 로 바꾸고 state 에 `"run_id": str(uuid4())`, `"postgres_url": os.environ.get("POSTGRES_URL", "postgresql://x")` 를 추가(`input_files` 는 기존 의도 유지 — 빈-입력 raise 케이스는 input_files=[] 로). 
  - Run: `PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_parser_node.py -q` → 기대 `2 passed` (이전 2 failed/error 에서).

- [ ] **Write the failing test** `pipeline/tests/test_parser_node_progress.py`:
```python
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

import pipeline.agents.parser_node as pn


@pytest.mark.asyncio
async def test_parser_node_emits_monotonic_progress(monkeypatch):
    """parser_node: (0, len(files)) 선기록 후 파일마다 processed 단조 증가 → total."""
    calls: list[tuple[str, int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        calls.append((agent, processed, total))

    # 실 xlsx 파싱은 느리고 LLM 무관 — to_thread parse 를 가짜로 대체.
    def _fake_parse(p):
        return {
            "report_date": "2025-09-25",
            "project": "T",
            "bp_summaries": [{}],
            "job_allocations": [],
            "equipment_allocations": [],
            "activities": [{}],
            "worker_outputs": [],
            "report_meta": None,
        }

    monkeypatch.setattr(pn, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(pn, "parse_daily_report", _fake_parse)

    state = {
        "run_id": str(uuid4()),
        "postgres_url": "postgresql://x",
        "input_files": ["/a.xlsm", "/b.xlsm", "/c.xlsm"],
    }
    out = await pn.parser_node(state)
    assert "parsed" in out

    parser_calls = [c for c in calls if c[0] == "parser"]
    # total 은 항상 3 (= len(files))
    assert all(t == 3 for _, _, t in parser_calls)
    processed_seq = [p for _, p, _ in parser_calls]
    # 0 선기록 + 단조 비감소 + 마지막 == total
    assert processed_seq[0] == 0
    assert processed_seq == sorted(processed_seq)
    assert processed_seq[-1] == 3
```

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_parser_node_progress.py -q
```
Expected: FAIL — `AttributeError: <module 'pipeline.agents.parser_node'> does not have the attribute 'upsert_agent_progress'` (monkeypatch.setattr fails because the name isn't imported yet).

- [ ] **Implement** — edit `pipeline/agents/parser_node.py`. Add import (after parser_node.py:11):
```python
from pipeline.db import upsert_agent_progress
```
Then replace the gather block. Current parser_node.py:50-57 is:
```python
    sem = asyncio.Semaphore(_PARSE_CONCURRENCY)

    async def _parse_one(p: Path) -> ParsedDailyReport:
        async with sem:
            return await asyncio.to_thread(parse_daily_report, p)

    reports = list(await asyncio.gather(*[_parse_one(p) for p in files]))
    merged = _merge_reports(reports)
```
Replace with:
```python
    sem = asyncio.Semaphore(_PARSE_CONCURRENCY)

    # B3 진행도 — run_id/postgres_url 는 exporter.py:330,332 와 동일하게 state 에서 추출.
    run_id = state["run_id"]
    pg_url = state["postgres_url"]
    total = len(files)
    await upsert_agent_progress(pg_url, run_id, "parser", 0, total)

    _done = 0  # plain int — sync 증가 후 local 캡쳐, 그 다음 await upsert (read-modify-write 사이 await X)

    async def _parse_one(p: Path) -> ParsedDailyReport:
        nonlocal _done
        async with sem:
            r = await asyncio.to_thread(parse_daily_report, p)
        _done += 1
        _local = _done
        await upsert_agent_progress(pg_url, run_id, "parser", _local, total)
        return r

    reports = list(await asyncio.gather(*[_parse_one(p) for p in files]))
    merged = _merge_reports(reports)
```

- [ ] **Run it, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_parser_node_progress.py -q
```
Expected: `1 passed`.

- [ ] **Commit:**
```
$ git add pipeline/agents/parser_node.py pipeline/tests/test_parser_node_progress.py && git commit -m "B3: parser_node emits agent_progress (0,len(files)) + per-file processed

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3 — graph.mapper_node: move parser inserts BEFORE gather, chunk mapper insert every K (idx-carrying _map_one), emit mapper progress every K

**Files:**
- Modify: `pipeline/graph.py` (`mapper_node` graph.py:57-178; `_map_one` graph.py:96-105; parser/mapper inserts graph.py:120-165; add `_MAPPER_PROGRESS_CHUNK` next to graph.py:45)
- Test: `pipeline/tests/test_mapper_node_progress.py` (Create — deterministic harness, monkeypatches `map_activity`, `_prorate_mh`, `normalize_company`, and `PGClient` to a fake recorder; monkeypatches `upsert_agent_progress`)

Real-code anchors:
- `_map_one(a)` (graph.py:96-105) currently returns `Activity` only — does NOT carry idx (open_ambiguity #2 → resolved: it returns the awaited activity, idx is not threaded; we add idx threading).
- Parser inserts: `insert_parser_report` (graph.py:120-128) + `insert_parser_activities_batch` (graph.py:130-135) currently run AFTER `await asyncio.gather` (line 105). Spec §6.4 requires moving them BEFORE the gather so the items-page Mapper card (parser LEFT JOIN mapper) gets base rows immediately.
- `insert_mapper_activities_batch` (graph.py:160-164) is one batch at the end; ON CONFLICT (run_id, idx) is idempotent (verified db.py:695). We chunk it every K.
- `_prorate_mh` (graph.py:117) and `normalize_company` loops (graph.py:76-80, 157-158) and the job/equipment allocation inserts (graph.py:140-153) and verify SELECT (graph.py:168-173) stay.
- Constraint: parser inserts need a connected `pg`; currently the function opens `pg` for cand fetch (graph.py:83-92), closes it, then reopens at graph.py:113. Plan: open the second `pg` (graph.py:113) BEFORE the gather, do parser inserts there, run the gather, then prorate+mapper-insert in the same `pg`/try block. `_prorate_mh` needs `mapped` which only exists after gather — keep prorate AFTER gather (it is). Mapper insert must use prorated+normalized `mapped`, so the per-K chunk insert happens after gather/prorate (this is fine — the spec's "stream" goal for mapper cards is satisfied by per-K chunked inserts of the final mapped rows; parser rows up front make the card "received").

- [ ] **Write the failing test** `pipeline/tests/test_mapper_node_progress.py`:
```python
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

import pipeline.graph as G
from pipeline.agents.mapper import MapperConfig


class _FakePG:
    """insert 호출 순서/시점만 기록하는 가짜 PGClient."""

    events: list[tuple] = []

    def __init__(self, url):
        self._url = url

    async def connect(self):
        pass

    async def close(self):
        pass

    async def fetch_bp_candidates(self, company):
        return []

    async def insert_parser_report(self, **kw):
        _FakePG.events.append(("parser_report", None))

    async def insert_parser_activities_batch(self, **kw):
        _FakePG.events.append(("parser_activities", len(kw["activities"])))

    async def insert_parser_job_allocations_batch(self, **kw):
        _FakePG.events.append(("job", len(kw["rows"])))

    async def insert_parser_equipment_allocations_batch(self, **kw):
        _FakePG.events.append(("equip", len(kw["rows"])))

    async def insert_mapper_activities_batch(self, **kw):
        # 청크별 호출 — 각 호출의 활동 수 기록
        _FakePG.events.append(("mapper_chunk", len(kw["activities"])))

    async def fetch_all(self, sql, *a):
        return [{"n": 0}]


def _act(i):
    return {
        "company": f"co{i % 2}",
        "work_content": f"w{i}",
        "trade": "건축",
        "l6_main": None,
        "wa": None,
        "unit": "m3",
        "today_qty": 1,
    }


@pytest.mark.asyncio
async def test_mapper_node_chunks_and_emits(monkeypatch):
    _FakePG.events = []
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "mapper":
            progress.append((processed, total))

    async def _fake_map_one_inner(a, parsed_report, cfg, bp_cand_lookup):
        out = dict(a)
        out["l6_main"] = "L6"
        out["wa"] = "WA"
        return out

    async def _fake_prorate(mapped, parsed, pg):
        return mapped

    monkeypatch.setattr(G, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(G, "map_activity", _fake_map_one_inner)
    monkeypatch.setattr(G, "_prorate_mh", _fake_prorate)
    monkeypatch.setattr(G, "normalize_company", lambda c: c or "")
    monkeypatch.setattr(G, "PGClient", _FakePG)
    monkeypatch.setattr(G, "_MAPPER_PROGRESS_CHUNK", 20)

    n = 45  # 45개 → 청크 20 → 20,20,5 = 3 청크
    parsed = {
        "project": "P",
        "activities": [_act(i) for i in range(n)],
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
    }
    cfg = G.GraphConfig(
        mapper=MapperConfig(
            azure_endpoint="x", azure_api_key="x", azure_api_version="x",
            llm_model="x", embedding_model="x",
            postgres_url="postgresql://x", chroma_host="x", chroma_port=1,
        ),
        atomizer=None, forecaster=None, optimizer=None, reporter=None,
    )
    state = {"parsed": parsed, "run_id": str(uuid4()), "date": "2025-09-25"}

    out = await G.mapper_node(state, cfg)
    assert len(out["mapped"]) == n

    # 1) parser rows BEFORE any mapper chunk
    kinds = [e[0] for e in _FakePG.events]
    first_mapper = kinds.index("mapper_chunk")
    assert "parser_activities" in kinds[:first_mapper]
    assert "parser_report" in kinds[:first_mapper]

    # 2) mapper chunked: 3 chunks summing to n
    chunk_sizes = [e[1] for e in _FakePG.events if e[0] == "mapper_chunk"]
    assert sum(chunk_sizes) == n
    assert len(chunk_sizes) >= 2  # 청크됐다 (단일 batch 아님)

    # 3) progress monotonic 0..n
    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
```

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_mapper_node_progress.py -q
```
Expected: FAIL — `AttributeError: ... does not have the attribute 'upsert_agent_progress'` (not imported into graph yet) or, after import added, an assertion failure on parser-before-mapper ordering / single-batch (sizes == [n]).

- [ ] **Implement step A — imports & constant.** In `pipeline/graph.py`, add `upsert_agent_progress` to the existing db import (graph.py:35-41 imports from `pipeline.db`):
```python
from pipeline.db import (
    PGClient,
    set_current_node,
    set_run_status,
    update_site_hours_saved_cum,
    update_site_last_run,
    upsert_agent_progress,
)
```
And after graph.py:45 (`_MAPPER_CONCURRENCY = ...`) add:
```python
# B3 카드 점진 — mapper 매핑완료 K건마다 mapper_activities chunk INSERT + progress emit.
_MAPPER_PROGRESS_CHUNK = int(os.environ.get("CPIA_MAPPER_PROGRESS_CHUNK", "20"))
```

- [ ] **Implement step B — thread idx into _map_one.** Replace graph.py:94-105 (`sem = ...` through the `_map_one` def and the gather assignment at :105). Current:
```python
    sem = asyncio.Semaphore(_MAPPER_CONCURRENCY)

    async def _map_one(a: Activity) -> Activity:
        async with sem:
            return await map_activity(
                a,
                parsed_report=parsed,
                cfg=cfg.mapper,
                bp_cand_lookup=bp_cand_lookup,
            )

    mapped: list[Activity] = list(await asyncio.gather(*[_map_one(a) for a in parsed["activities"]]))
```
Replace with (idx-carrying, but gather happens AFTER parser inserts — see step C; here just change `_map_one` to return `(idx, Activity)` and DELETE the standalone gather line — it moves into the try block in step C):
```python
    sem = asyncio.Semaphore(_MAPPER_CONCURRENCY)

    async def _map_one(idx: int, a: Activity) -> tuple[int, Activity]:
        async with sem:
            m = await map_activity(
                a,
                parsed_report=parsed,
                cfg=cfg.mapper,
                bp_cand_lookup=bp_cand_lookup,
            )
        return idx, m
```

- [ ] **Implement step C — move parser inserts before gather + chunked mapper insert + progress emit.** Replace the whole block graph.py:107-178 (from `import sys as _sys` through `return {"mapped": mapped, "current_node": "mapper"}`) with:
```python
    import sys as _sys

    def _dbg(msg: str) -> None:
        print(f"[mapper_node:{run_id}] {msg}", file=_sys.stderr, flush=True)

    total = len(parsed["activities"])
    pg_url = cfg.mapper.postgres_url
    await upsert_agent_progress(pg_url, state["run_id"], "mapper", 0, total)

    pg = PGClient(cfg.mapper.postgres_url)
    await pg.connect()
    _dbg(f"PG connected DSN={cfg.mapper.postgres_url[:40]}...")
    try:
        # B3: parser_reports/parser_activities 를 gather BEFORE 적재 — items Mapper 카드
        # (parser LEFT JOIN mapper) 가 매핑 끝나기 전부터 received 표시.
        await pg.insert_parser_report(
            run_id=run_id,
            report_date=today,
            project=parsed["project"],
            bp_summaries=parsed["bp_summaries"],
            job_allocations=parsed["job_allocations"],
            equipment_allocations=parsed["equipment_allocations"],
            activity_count=len(parsed["activities"]),
        )
        _dbg("insert_parser_report OK")
        await pg.insert_parser_activities_batch(
            run_id=run_id,
            report_date=today,
            activities=parsed["activities"],
        )
        _dbg(f"insert_parser_activities_batch OK ({len(parsed['activities'])} rows)")
        await pg.insert_parser_job_allocations_batch(
            run_id=run_id,
            report_date=today,
            rows=parsed.get("job_allocations") or [],
        )
        _dbg(f"insert_parser_job_allocations_batch OK ({len(parsed.get('job_allocations') or [])} rows)")
        await pg.insert_parser_equipment_allocations_batch(
            run_id=run_id,
            report_date=today,
            rows=parsed.get("equipment_allocations") or [],
        )
        _dbg(
            f"insert_parser_equipment_allocations_batch OK ({len(parsed.get('equipment_allocations') or [])} rows)"
        )

        # Mapper LLM 병렬 — idx 동반 반환. as_completed 로 완료순 수집 (스트림 친화).
        results: dict[int, Activity] = {}
        chunk_buf: list[Activity] = []
        _done = 0  # plain int — sync 증가 후 local 캡쳐, 그 다음 await (read-modify-write 사이 await X)
        coros = [_map_one(i, a) for i, a in enumerate(parsed["activities"])]
        for fut in asyncio.as_completed(coros):
            idx, m = await fut
            m["company"] = normalize_company(m.get("company")) or ""
            results[idx] = m
            chunk_buf.append((idx, m))
            _done += 1
            _local = _done
            # K건마다 청크 INSERT (run_id,idx ON CONFLICT 멱등) + progress emit
            if len(chunk_buf) >= _MAPPER_PROGRESS_CHUNK or _local == total:
                # _prorate_mh 는 전체 mapped 기준이라 청크엔 적용 못함 — 청크는 raw mapped INSERT,
                # 최종 prorate 후 전체 재INSERT (ON CONFLICT UPDATE 로 plan_mh 등 보정).
                _chunk_acts = [ca for _, ca in chunk_buf]
                _chunk_idxs = [ci for ci, _ in chunk_buf]
                await pg.insert_mapper_activities_batch(
                    run_id=run_id,
                    report_date=today,
                    activities=_chunk_acts,
                    idxs=_chunk_idxs,
                )
                await upsert_agent_progress(pg_url, state["run_id"], "mapper", _local, total)
                _dbg(f"mapper chunk INSERT ({len(_chunk_acts)}) progress={_local}/{total}")
                chunk_buf = []

        # idx 순서 복원 → 최종 mapped (downstream 은 순서 의존하므로 idx 정렬)
        mapped: list[Activity] = [results[i] for i in range(total)]
        _dbg(f"mapped len={len(mapped)} BEFORE prorate/INSERT")

        mapped = await _prorate_mh(mapped, parsed, pg)
        _dbg(f"prorate done, mapped len={len(mapped)}")

        for a in mapped:
            a["company"] = normalize_company(a.get("company")) or ""

        # 최종 전량 재INSERT — prorate 로 채워진 plan_mh 등 보정 (ON CONFLICT (run_id,idx) UPDATE).
        await pg.insert_mapper_activities_batch(
            run_id=run_id,
            report_date=today,
            activities=mapped,
        )
        _dbg(f"insert_mapper_activities_batch (final) OK ({len(mapped)} rows)")

        n_pr = await pg.fetch_all("SELECT count(*) AS n FROM parser_reports WHERE run_id=$1", run_id)
        n_pa = await pg.fetch_all("SELECT count(*) AS n FROM parser_activities WHERE run_id=$1", run_id)
        n_ma = await pg.fetch_all("SELECT count(*) AS n FROM mapper_activities WHERE run_id=$1", run_id)
        _dbg(
            f"verify SELECT: parser_reports={n_pr[0]['n']} parser_activities={n_pa[0]['n']} mapper_activities={n_ma[0]['n']}"
        )
    finally:
        await pg.close()
        _dbg("PG closed, mapper_node return")

    return {"mapped": mapped, "current_node": "mapper"}
```

- [ ] **Implement step D — `insert_mapper_activities_batch` must accept an optional explicit `idxs`** so a chunk of N activities maps to their ORIGINAL idx (not 0..N-1). Current signature db.py:647-652 enumerates `i` internally (db.py:735 uses `i` from `enumerate`). Modify db.py:647-652 + the row builder (around db.py:731-736). Change signature:
```python
    async def insert_mapper_activities_batch(
        self,
        run_id: uuid.UUID,
        report_date: _date,
        activities: list[dict],
        idxs: list[int] | None = None,
    ) -> None:
```
And change the row-tuple comprehension at db.py:731-732 from `for i, a in enumerate(activities)` to use `idxs` when given. Concretely, replace the `enumerate(activities)` driver so `idx = (idxs[k] if idxs is not None else k)`:
```python
            rows = [
                (
                    run_id,
                    report_date,
                    (idxs[k] if idxs is not None else k),
                    a["company"],
                    ...  # rest UNCHANGED
                )
                for k, a in enumerate(activities)
            ]
```
(Find the existing tuple at db.py:732-... and rename the loop var `i`→`k` and the 3rd element `i`→`(idxs[k] if idxs is not None else k)`. Everything else in the tuple is unchanged.) The final full-list call (no `idxs`) keeps 0..n-1 — identical to today, so existing callers/tests are unaffected.

- [ ] **Run the new test, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_mapper_node_progress.py -q
```
Expected: `1 passed`.

- [ ] **Run mapper-node regression to confirm no break in existing mapper insert path:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_db_new_columns_insert.py pipeline/tests/test_mapper_node.py -q
```
Expected: same pass/skip status as before this task (test_mapper_node.py may skip without Azure env — that is unchanged). Report the raw summary line.

- [ ] **Commit:**
```
$ git add pipeline/graph.py pipeline/db.py pipeline/tests/test_mapper_node_progress.py && git commit -m "B3: mapper_node parser-rows-before-gather + chunked mapper insert (K=20, idx-carrying) + progress emit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4 — atomizer: emit total=len(ids) post-dedup, processed per chroma batch

**Files:**
- Modify: `pipeline/agents/atomizer.py` (`atomize` atomizer.py:95-199; total after dedup at atomizer.py:133; per-batch in the upsert loop atomizer.py:163-169)
- Test: `pipeline/tests/test_atomizer_progress.py` (Create — monkeypatch `upsert_agent_progress`, `AzureOpenAI`, `ChromaClient`, and the `PGClient` calls; reuse pattern but minimal — patch ChromaClient + embeddings to skip network)

Real-code anchors: `atomize(mapped, parsed_report, run_id, cfg)` (atomizer.py:95). dedup produces `ids = list(seen.keys())` at atomizer.py:133. `_CHROMA_UPSERT_BATCH = 100` (atomizer.py:162) and the upsert loop atomizer.py:163-169. `cfg.postgres_url` holds the DSN; `run_id` is a param. Note the upsert loop iterates `range(0, len(ids), 100)`.

- [ ] **Write the failing test** `pipeline/tests/test_atomizer_progress.py`:
```python
from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.agents.atomizer as AT
from pipeline.agents.atomizer import AtomizerConfig


class _FakeColl:
    def upsert(self, **kw):
        pass


class _FakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _FakeColl()


class _FakeResp:
    def __init__(self, n):
        self.data = [type("E", (), {"embedding": [0.0]})() for _ in range(n)]


class _FakeEmb:
    def create(self, model, input):
        return _FakeResp(len(input))


class _FakeAzure:
    def __init__(self, **kw):
        self.embeddings = _FakeEmb()


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def assert_pipeline_run_exists(self, run_id):
        pass

    async def update_run_atomized_count(self, run_id, n):
        pass

    async def get_pipeline_run(self, run_id):
        return {"site_id": "s", "report_date": "2025-09-25"}

    async def insert_mapped_history_batch(self, *a, **k):
        pass


def _act(i):
    return {
        "company": "co",
        "l6_main": "L6",
        "work_content": f"w{i}",  # 모두 distinct → dedup 후 n 유지
        "wa": None,
        "trade": "건축",
        "unit": "m3",
        "today_qty": 1,
        "conditions": [],
        "assigned_workers": 1,
    }


@pytest.mark.asyncio
async def test_atomizer_emits_post_dedup_total(monkeypatch):
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "atomizer":
            progress.append((processed, total))

    monkeypatch.setattr(AT, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(AT, "AzureOpenAI", _FakeAzure)
    monkeypatch.setattr(AT, "ChromaClient", _FakeChroma)
    monkeypatch.setattr(AT, "PGClient", _FakePG)

    n = 250  # batch 100 → 3 배치 (100,100,50)
    mapped = [_act(i) for i in range(n)]
    parsed = {"report_date": "2025-09-25"}
    cfg = AtomizerConfig(
        azure_endpoint="x", azure_api_key="x", azure_api_version="x",
        embedding_model="x", postgres_url="postgresql://x",
        chroma_host="x", chroma_port=1, batch_size=100,
    )
    ids = await AT.atomize(mapped, parsed, uuid4(), cfg)
    assert len(ids) == n

    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
```

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_atomizer_progress.py -q
```
Expected: FAIL — `AttributeError: <module 'pipeline.agents.atomizer'> does not have the attribute 'upsert_agent_progress'`.

- [ ] **Implement** — `pipeline/agents/atomizer.py`. Add to the db import (atomizer.py:20 `from pipeline.db import PGClient`):
```python
from pipeline.db import PGClient, upsert_agent_progress
```
After dedup `ids = list(seen.keys())` (atomizer.py:133), insert:
```python
        # B3 진행도 — total 은 dedup 후 실 적재 doc 수.
        _ap_total = len(ids)
        await upsert_agent_progress(cfg.postgres_url, run_id, "atomizer", 0, _ap_total)
```
Then in the chroma upsert loop (atomizer.py:163-169), after each `coll.upsert(...)` call, add a processed emit. The loop var is `_j`; processed = min(_j + batch, total). Change the loop body to:
```python
        for _j in range(0, len(ids), _CHROMA_UPSERT_BATCH):
            coll.upsert(
                ids=ids[_j : _j + _CHROMA_UPSERT_BATCH],
                embeddings=embeddings[_j : _j + _CHROMA_UPSERT_BATCH],
                documents=documents[_j : _j + _CHROMA_UPSERT_BATCH],
                metadatas=metadatas[_j : _j + _CHROMA_UPSERT_BATCH],
            )
            _ap_done = min(_j + _CHROMA_UPSERT_BATCH, _ap_total)
            await upsert_agent_progress(cfg.postgres_url, run_id, "atomizer", _ap_done, _ap_total)
```
(`_ap_done` is computed synchronously from loop bounds — no read-modify-write across an await.)

- [ ] **Run it, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_atomizer_progress.py -q
```
Expected: `1 passed`.

- [ ] **Commit:**
```
$ git add pipeline/agents/atomizer.py pipeline/tests/test_atomizer_progress.py && git commit -m "B3: atomizer emits agent_progress total=len(ids) post-dedup, processed per chroma batch

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5 — exporter: emit total=1, processed=1 on success

**Files:**
- Modify: `pipeline/agents/exporter.py` (`consolidated_xlsx_node` exporter.py:314-375; total=1 at entry after reading state; processed=1 after successful upsert at exporter.py:348-354)
- Test: `pipeline/tests/test_exporter_progress.py` (Create — monkeypatch `upsert_agent_progress`, `fetch_sheet_data`, `fetch_site_by_id`, `render_xlsx`, `upsert_consolidated_report`, `PGClient`)

Real-code anchors: `consolidated_xlsx_node(state)` reads `state["site_id"]` (exporter.py:328), `state["date"]` (329), `state["run_id"]` (330), `PGClient(state["postgres_url"])` (332). Success path: `fetch_sheet_data` (336) → `render_xlsx` (347) → `upsert_consolidated_report` (348). On `NoDataError` it returns `{}` early (343) WITHOUT progress (correct: nothing exported). Note module-level imports at exporter.py top.

- [ ] **Write the failing test** `pipeline/tests/test_exporter_progress.py`:
```python
from __future__ import annotations

from uuid import uuid4

import pytest

import pipeline.agents.exporter as EX


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_exporter_emits_one_one_on_success(monkeypatch):
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "exporter":
            progress.append((processed, total))

    async def _fake_fetch_sheet(pg, site_id, report_date):
        return {"ok": True}

    async def _fake_site(pg, site_id):
        return {"name": "X"}

    async def _fake_upsert_report(pg, **kw):
        pass

    monkeypatch.setattr(EX, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(EX, "PGClient", _FakePG)
    monkeypatch.setattr(EX, "fetch_sheet_data", _fake_fetch_sheet)
    monkeypatch.setattr(EX, "fetch_site_by_id", _fake_site)
    monkeypatch.setattr(EX, "render_xlsx", lambda data, rd, project: b"xlsx")
    monkeypatch.setattr(EX, "upsert_consolidated_report", _fake_upsert_report)

    state = {
        "site_id": "s",
        "date": "2025-09-25",
        "run_id": str(uuid4()),
        "postgres_url": "postgresql://x",
    }
    out = await EX.consolidated_xlsx_node(state)
    assert "consolidated_xlsx_run_id" in out
    assert (0, 1) in progress
    assert (1, 1) in progress
    procs = [p for p, _ in progress]
    assert procs == sorted(procs) and procs[-1] == 1
```

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_exporter_progress.py -q
```
Expected: FAIL — `AttributeError: ... 'upsert_agent_progress'` (not imported in exporter).

- [ ] **Implement** — `pipeline/agents/exporter.py`. Add import near the other `from pipeline.db import ...` (or add a dedicated line; verify exporter imports PGClient — it constructs `PGClient(state["postgres_url"])` at exporter.py:332, so PGClient is already imported). Add:
```python
from pipeline.db import upsert_agent_progress
```
In `consolidated_xlsx_node`, right after `pg = PGClient(state["postgres_url"]); await pg.connect()` (exporter.py:332-333), emit total:
```python
    await upsert_agent_progress(state["postgres_url"], state["run_id"], "exporter", 0, 1)
```
Then after the successful `await upsert_consolidated_report(...)` (exporter.py:348-354) and BEFORE its `log.info(...)` (or right after it, inside the inner try after upsert), add:
```python
            await upsert_agent_progress(state["postgres_url"], state["run_id"], "exporter", 1, 1)
```
Place it inside the inner `try` after `upsert_consolidated_report` succeeds (so a render/upsert exception, caught at exporter.py:362, leaves processed at 0 — correct: nothing was exported).

- [ ] **Run it, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_exporter_progress.py -q
```
Expected: `1 passed`.

- [ ] **Commit:**
```
$ git add pipeline/agents/exporter.py pipeline/tests/test_exporter_progress.py && git commit -m "B3: exporter emits agent_progress total=1 entry / processed=1 on successful upsert

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6 — forecaster: emit total=len(groups), processed after each insert_forecast

**Files:**
- Modify: `pipeline/agents/forecaster/agent.py` (`forecast` agent.py:349; groups built agent.py:371-378; `_one` agent.py:382-398 already does row-by-row `insert_forecast` at agent.py:397; total emitted right after `groups` built ~agent.py:378-380; processed emit right after agent.py:397 insert)
- Test: `pipeline/tests/forecaster/test_forecaster_progress.py` (Create — monkeypatch `_forecast_one_group`, `insert_forecast` (on a fake PG), `AzureOpenAI`, `ChromaClient`, `get_llm_semaphore` not needed; patch `upsert_agent_progress`)

Real-code anchors: `forecast(mapped, run_id, today, cfg)` (agent.py:349). `cfg.postgres_url` for DSN, `run_id` param. groups dict built agent.py:371-378 inside the `try` (agent.py:368). `_one` closure (agent.py:382) calls `await pg.insert_forecast(row)` (agent.py:397) — already row-by-row "sem 밖". tasks gathered agent.py:400-401. The `pg` is constructed/connected at agent.py:356-357 (outside the snippet I read but referenced); the function body uses `pg`. `Activity` filtering at agent.py:372-377.

- [ ] **Write the failing test** `pipeline/tests/forecaster/test_forecaster_progress.py`:
```python
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

import pipeline.agents.forecaster.agent as FA
from pipeline.agents.forecaster import ForecasterConfig


class _FakePG:
    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def assert_pipeline_run_exists(self, run_id):
        pass

    async def insert_forecast(self, row):
        pass


class _FakeColl:
    def get(self, **kw):
        return {"metadatas": [], "documents": []}


class _FakeChroma:
    def __init__(self, **kw):
        pass

    def get_or_create_daily_activities(self):
        return _FakeColl()


class _FakeAzure:
    def __init__(self, **kw):
        pass


def _act(i):
    return {
        "company": f"co{i}",  # 모두 distinct group
        "l6_main": f"L6_{i}",
        "wa": None,
        "work_content": f"w{i}",
    }


@pytest.mark.asyncio
async def test_forecaster_emits_per_group(monkeypatch):
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "forecaster":
            progress.append((processed, total))

    async def _fake_one_group(company, l6_main, activities, run_id, today, pg, coll, azure, cfg):
        return {"company": company, "l6_main": l6_main}

    monkeypatch.setattr(FA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(FA, "PGClient", _FakePG)
    monkeypatch.setattr(FA, "ChromaClient", _FakeChroma)
    monkeypatch.setattr(FA, "AzureOpenAI", _FakeAzure)
    monkeypatch.setattr(FA, "_forecast_one_group", _fake_one_group)

    n = 6
    mapped = [_act(i) for i in range(n)]
    cfg = ForecasterConfig(
        azure_endpoint="x", azure_api_key="x", azure_api_version="x",
        llm_model="x", embedding_model="x", postgres_url="postgresql://x",
        chroma_host="x", chroma_port=1,
    )
    rows = await FA.forecast(mapped, uuid4(), date(2025, 9, 25), cfg)
    assert len(rows) == n

    procs = [p for p, _ in progress]
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == n
    assert all(t == n for _, t in progress)
```
(If `ForecasterConfig` field names differ, copy them from `pipeline/tests/test_forecaster_concurrency.py` — adapt before running. Confirm the actual `ForecasterConfig` signature by reading `pipeline/agents/forecaster/__init__.py` / config dataclass first.)

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/forecaster/test_forecaster_progress.py -q
```
Expected: FAIL — `AttributeError: ... 'upsert_agent_progress'`.

- [ ] **Implement** — `pipeline/agents/forecaster/agent.py`. Add to the db import (find `from pipeline.db import ...`):
```python
from pipeline.db import PGClient, upsert_agent_progress
```
After groups built (agent.py:378, right after the `for a in mapped:` loop completes building `groups`), add:
```python
        _ap_total = len(groups)
        await upsert_agent_progress(cfg.postgres_url, run_id, "forecaster", 0, _ap_total)
        _ap_done = 0  # plain int — closure 안에서 sync 증가 후 local 캡쳐
```
Inside `_one` (agent.py:382-398), after `await pg.insert_forecast(row)` (agent.py:397) add:
```python
            nonlocal _ap_done
            _ap_done += 1
            _local = _ap_done
            await upsert_agent_progress(cfg.postgres_url, run_id, "forecaster", _local, _ap_total)
```
(`_ap_done` increment is synchronous; `_local` captured before the await. `insert_forecast` and these emits run outside the `sem` block — consistent with agent.py:397's existing "sem 밖" comment.)

- [ ] **Run it, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/forecaster/test_forecaster_progress.py -q
```
Expected: `1 passed`.

- [ ] **Commit:**
```
$ git add pipeline/agents/forecaster/agent.py pipeline/tests/forecaster/test_forecaster_progress.py && git commit -m "B3: forecaster emits agent_progress total=len(groups) / processed after each insert_forecast

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7 — optimizer: per-task insert_optimizer_advice for card streaming + emit; verify view-build still reads all rows from PG

**Files:**
- Modify: `pipeline/agents/optimizer/agent.py` (`optimize` agent.py:253; selected count for total; MOVE `insert_optimizer_advice` from the post-gather loop agent.py:336-337 into `_process_one_v10_with_retry` after `_compose_row` (agent.py:235), sem 밖; emit processed after each insert; KEEP view-build at agent.py:347 reading all PG rows)
- Test: `pipeline/tests/optimizer/test_optimizer_progress.py` (Create — monkeypatch `_process_one_v10_with_retry`'s LLM calls is heavy; instead monkeypatch the V10 LLM call funcs + `PGClient.insert_optimizer_advice` recorder + `upsert_agent_progress`; also assert advice is inserted DURING gather, not only after)

Real-code anchors:
- `optimize(forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id=None, mapped=None)` (agent.py:253-262).
- "selected forecast" = the `tasks` list built by filtering `forecast` against `hil_2_selection` at agent.py:309-318. `len(selected)` = `len(tasks)`. Spec §6.2 says total=len(selected forecast)=len(forecast) (because hil_2 auto-selects all per graph.py:402-407), but the CODE filters by `key in hil_2_selection` (agent.py:311) — so total must be `len(tasks)` to stay correct if selection ever shrinks (open_ambiguity: spec says len(forecast); code-safe is len(tasks)). Use `len(tasks)`.
- `_process_one_v10_with_retry(r, cases, run_id, today, cfg, azure, sem, failed_wps, max_retries=3)` (agent.py:176-186) returns `_compose_row(...)` (agent.py:235) or `None` (agent.py:246,250).
- Current post-gather insert loop: agent.py:333-337 (`pg = PGClient(...); await pg.connect(); for row in advice_rows: await pg.insert_optimizer_advice(row)`).
- View build at agent.py:347 `_build_productivity_views_v2(pg, site_id, today)` reads advice via PG SELECT (comment agent.py:343-344 confirms "v2 가 PG SELECT 로 advice 재조회"). So moving inserts EARLIER (into the gather tasks) keeps them committed before agent.py:347 runs — **commit visibility holds** because each insert uses the SAME pooled `pg` connection that view-build later queries, and asyncpg autocommits each `execute`. VERIFY: there must be a single `pg` available inside `_process_one_v10_with_retry`. Currently that function does NOT receive `pg`. Plan: pass `pg` into it (extend signature), open `pg` ONCE at top of `optimize` (before the gather) and reuse for both per-task inserts AND view-build.

- [ ] **First, read the exact post-gather block + the `pg` lifecycle in `optimize`** to confirm where `pg` is currently opened (it is opened at agent.py:333 AFTER gather). Confirm by:
```
$ PYTHONPATH=$PP $PY -c "import inspect,pipeline.agents.optimizer.agent as a; src=inspect.getsource(a.optimize); print(src[src.index('sem = get_llm_semaphore'):][:1400])"
```
Expected: prints the `_process_one`, `tasks` loop, `gather`, and the `pg = PGClient(cfg.postgres_url); await pg.connect()` block at agent.py:333 — confirming `pg` opens after gather today.

- [ ] **Write the failing test** `pipeline/tests/optimizer/test_optimizer_progress.py`:
```python
from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

import pipeline.agents.optimizer.agent as OA
from pipeline.agents.optimizer.agent import OptimizerConfig


class _FakePG:
    insert_times: list[int] = []  # 각 insert 시점의 누적 emit 수 (스트림 증거)
    _emit_count = 0

    def __init__(self, url):
        pass

    async def connect(self):
        pass

    async def close(self):
        pass

    async def insert_optimizer_advice(self, row):
        # gather 도중 호출되는지 확인 — 호출 시점의 progress emit 수 캡쳐
        _FakePG.insert_times.append(_FakePG._emit_count)

    async def upsert_daily_report_view_col(self, *a, **k):
        pass


@pytest.mark.asyncio
async def test_optimizer_streams_advice_and_emits(monkeypatch):
    _FakePG.insert_times = []
    _FakePG._emit_count = 0
    progress: list[tuple[int, int]] = []

    async def _fake_upsert(url, run_id, agent, processed, total):
        if agent == "optimizer":
            _FakePG._emit_count += 1
            progress.append((processed, total))

    async def _fake_retry(r, cases, run_id, today, cfg, azure, sem, failed_wps, pg, max_retries=3):
        # _compose_row 직후 per-task insert (sem 밖) — 실 구현이 호출.
        row = {"company": r["company"], "l6_main": r["l6_main"]}
        await pg.insert_optimizer_advice(row)
        await OA.upsert_agent_progress(cfg.postgres_url, run_id, "optimizer", len(_FakePG.insert_times), 0)
        return row

    # view-build skip (site_id 전달해도 _build_productivity_views_v2 는 가짜)
    async def _fake_views(pg, site_id, today):
        return {}

    monkeypatch.setattr(OA, "upsert_agent_progress", _fake_upsert)
    monkeypatch.setattr(OA, "PGClient", _FakePG)
    monkeypatch.setattr(OA, "AzureOpenAI", lambda **k: object())
    monkeypatch.setattr(OA, "_process_one_v10_with_retry", _fake_retry)
    monkeypatch.setattr(OA, "_build_productivity_views_v2", _fake_views)

    forecast = [{"company": f"c{i}", "l6_main": f"L{i}"} for i in range(4)]
    selection = [f"{r['company']}|{r['l6_main']}" for r in forecast]
    cfg = OptimizerConfig(
        azure_endpoint="x", azure_api_key="x", azure_api_version="x",
        llm_model="x", embedding_model="x", postgres_url="postgresql://x",
        chroma_host="x", chroma_port=1,
    )
    rows = await OA.optimize(forecast, selection, {}, uuid4(), date(2025, 9, 25), cfg, site_id="s", mapped=[])
    assert len(rows) == 4
    # 4 advice 가 insert 됨
    assert len(_FakePG.insert_times) == 4
    # progress total == 4 (= len(tasks)) for at least one emit; processed reaches 4
    procs = [p for p, _ in progress]
    assert procs and procs[-1] == 4
```
(Adjust `OptimizerConfig` field names to the real dataclass — read it first; mirror `pipeline/tests/test_optimizer_concurrency.py` fixture if present.)

- [ ] **Run it, expect FAIL:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/optimizer/test_optimizer_progress.py -q
```
Expected: FAIL — `TypeError: _process_one_v10_with_retry() got an unexpected keyword argument 'pg'` (signature not yet extended) OR `AttributeError: ... 'upsert_agent_progress'`.

- [ ] **Implement step A — imports & total.** In `pipeline/agents/optimizer/agent.py`, extend the db import (agent.py:48 `from pipeline.db import PGClient`):
```python
from pipeline.db import PGClient, upsert_agent_progress
```

- [ ] **Implement step B — open `pg` ONCE before the gather, thread it into the retry fn, per-task insert + emit, drop the post-gather insert loop.** Rework `optimize` body. Current shape (agent.py:289-370): `sem = get_llm_semaphore()` → `_process_one` (legacy, agent.py:291-303, appears UNUSED by the v10 path — verify) → `_process_one_v10_with_retry` task loop (agent.py:307-318) → gather (agent.py:320) → post-gather `pg` open + insert loop (agent.py:333-337) → view-build (agent.py:345-367) → `return advice_rows`.
  - After the `tasks` loop (agent.py:318) and BEFORE `results = ...gather` (agent.py:320), open pg + emit total:
```python
        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            _ap_total = len(tasks)
            await upsert_agent_progress(cfg.postgres_url, run_id, "optimizer", 0, _ap_total)
            _ap_done = 0
```
  - Change the task construction (agent.py:314-318) to pass `pg` and a shared mutable counter. Simplest: pass `pg` into `_process_one_v10_with_retry`, and do the emit inside it. But the counter must be shared — pass a small closure. Cleanest within existing style: keep the insert+emit inside the retry fn by passing `pg` + a callback. Concretely, extend `_process_one_v10_with_retry` signature (agent.py:176-186) to add `pg` param and do the insert+emit there:
    - Signature add `pg,` before `max_retries`: `..., failed_wps: list, pg, max_retries: int = 3):`
    - At each successful return point (agent.py:235 `return _compose_row(...)`), replace `return _compose_row(r, cases, merged_llm_output, run_id, scenarios=scen_out)` with:
```python
                _row = _compose_row(r, cases, merged_llm_output, run_id, scenarios=scen_out)
                await pg.insert_optimizer_advice(_row)  # PG write sem 밖 (sem 블록 종료 후) — 카드 스트림
                return _row
```
    NOTE: `_compose_row` is currently inside the `async with sem:` block? Re-check: agent.py:213 `async with sem:` opens, the diag/recs calls happen inside, and at agent.py:230 `merged_llm_output` is built, agent.py:235 `return _compose_row(...)`. The `return` at 235 — is it inside or outside the `with sem`? Read the indentation: agent.py:228 `diag_out = await ...` is inside `with sem` (indent 16); agent.py:230-234 `merged_llm_output = {...}` is at indent 12 → OUTSIDE the sem block. So `_compose_row` at agent.py:235 is already sem 밖. GOOD — put the insert there (sem 밖, matches the "PG write 는 sem 밖" convention).
  - Update the task list construction (agent.py:314-318) to pass `pg`:
```python
        tasks.append(
            _process_one_v10_with_retry(
                r, cases, run_id, today, cfg, azure, sem, failed_wps, pg, max_retries=3
            )
        )
```
  - The emit: since the per-task insert is inside the retry fn but the counter must be shared+monotonic, do the emit in the gather-completion loop instead of inside the fn. Replace `results = list(await asyncio.gather(*tasks)) if tasks else []` (agent.py:320) with an as_completed loop:
```python
            results = []
            for fut in asyncio.as_completed(tasks):
                _r = await fut
                results.append(_r)
                _ap_done += 1
                _local = _ap_done
                await upsert_agent_progress(cfg.postgres_url, run_id, "optimizer", _local, _ap_total)
            advice_rows = [row for row in results if row is not None]
```
  - DELETE the old post-gather block agent.py:321 (`advice_rows = [...]`) duplicate and agent.py:333-337 (`pg = PGClient(...); await pg.connect(); try: for row in advice_rows: await pg.insert_optimizer_advice(row)`). The view-build (agent.py:345-367) now runs inside the SAME `try:` opened before the gather, reusing the SAME `pg`. Move the `failed_wps` warning (agent.py:323-331) to before the view-build (still inside the try). Close `pg` in the existing `finally: await pg.close()` (agent.py:368-369) — keep exactly one finally.
  - **VERIFY view-build commit visibility**: view-build at agent.py:347 calls `_build_productivity_views_v2(pg, site_id, today)` which SELECTs advice from PG. Since per-task `insert_optimizer_advice` ran on the same pooled `pg` and asyncpg autocommits each statement, all advice rows are committed before view-build SELECTs. This is the spec §6.4 verification requirement — assert it in the e2e harness (Task 8) by checking `SELECT count(*) FROM optimizer_advice WHERE run_id=$1` equals the optimizer_view advice count.

- [ ] **Run it, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/optimizer/test_optimizer_progress.py -q
```
Expected: `1 passed`.

- [ ] **Run optimizer concurrency regression** (per-task insert must not break the existing gather/retry path):
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_optimizer_concurrency.py pipeline/tests/test_aggregate_v10.py -q
```
Expected: same pass/skip baseline as before (report raw summary).

- [ ] **Commit:**
```
$ git add pipeline/agents/optimizer/agent.py pipeline/tests/optimizer/test_optimizer_progress.py && git commit -m "B3: optimizer per-task insert_optimizer_advice (card streaming) + progress emit, shared pg for view-build commit visibility

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8 — End-to-end deterministic progress harness (monotonic per agent; mapper rows appear before node return)

This is the cluster-level pass/fail loop. A full graph run hits Azure (slow, non-deterministic). Instead, build a deterministic harness that (a) runs each emitting node with a fake state + a monkeypatched `upsert_agent_progress` that records every call, asserting monotonic `processed: 0→total`; and (b) for mapper, asserts `mapper_activities` chunk rows are inserted before the node returns (already covered by Task 3's `_FakePG.events` ordering — promote it into a single harness test that runs all nodes).

**Files:**
- Test: `pipeline/tests/test_agent_progress_e2e.py` (Create — imports the per-node tests' fakes via a shared helper, or simply re-runs each node and asserts the union invariant)

- [ ] **Write the harness test** `pipeline/tests/test_agent_progress_e2e.py` that asserts the cross-cutting invariant for parser, atomizer, exporter, forecaster, optimizer in one file (reuse the fake classes from Tasks 2,4,5,6,7 — copy minimal fakes inline or import them). The single load-bearing assertion per agent:
```python
# 각 agent: 기록된 (processed,total) 시퀀스가 processed 0→total 단조 비감소, 마지막==total.
def assert_monotonic(progress, expected_total):
    procs = [p for p, _ in progress]
    assert procs, "no emit"
    assert procs[0] == 0
    assert procs == sorted(procs)
    assert procs[-1] == expected_total
    assert all(t == expected_total for _, t in progress)
```
Wire one `@pytest.mark.asyncio` test per agent calling the node with its fake state (same monkeypatch setup as Tasks 2/4/5/6/7) and calling `assert_monotonic`. For mapper, additionally assert (from `_FakePG.events`) that `parser_activities` precedes the first `mapper_chunk` AND that `mapper_chunk` events exist before `mapper_node` returns (they do, since inserts happen inside the function body before `return`).

- [ ] **Run the full B3 emit suite, expect PASS:**
```
$ PYTHONPATH=$PP $PY -m pytest pipeline/tests/test_db_agent_progress.py pipeline/tests/test_parser_node_progress.py pipeline/tests/test_mapper_node_progress.py pipeline/tests/test_atomizer_progress.py pipeline/tests/test_exporter_progress.py pipeline/tests/forecaster/test_forecaster_progress.py pipeline/tests/optimizer/test_optimizer_progress.py pipeline/tests/test_agent_progress_e2e.py -q
```
Expected: all passed (e.g. `13 passed`). Paste the raw summary line.

- [ ] **Optional live e2e (manual, after upload cluster lands)** — run the real pipeline against the 7 demo files, then poll `agent_progress` to observe monotonic streaming and confirm exporter‖forecaster both advance concurrently (per-(run,agent) rows resolve the single-current_node race):
```
$ PYTHONPATH=$PP $PY - <<'PYEOF'
import os, asyncio, asyncpg, time
from dotenv import load_dotenv
load_dotenv(os.path.join(os.environ["PP"], ".env"))
RUN_ID = "<run_id from /run>"
async def go():
    c = await asyncpg.connect(os.environ["POSTGRES_URL"])
    rows = await c.fetch("SELECT agent, processed, total FROM agent_progress WHERE run_id=$1 ORDER BY agent", RUN_ID)
    for r in rows: print(dict(r))
    await c.close()
asyncio.run(go())
PYEOF
```
Expected: rows for parser/mapper/atomizer/exporter/forecaster/optimizer with `processed<=total` and, when complete, `processed==total`. exporter and forecaster both non-zero simultaneously mid-run.

- [ ] **Commit:**
```
$ git add pipeline/tests/test_agent_progress_e2e.py && git commit -m "B3: cross-agent progress harness — monotonic 0->total per agent + mapper rows before return

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```


## Cluster C4 — `agent_progress` 기반 per-stage 독립 진행도 (마크업 불변)

> **선행 의존성 (차단)**: C4 는 B3 §6.1~6.4 (`agent_progress` 테이블 + `upsert_agent_progress` emit primitive + 노드별 emit) 가 **먼저 완료**되어야 실데이터로 검증 가능하다. 실 코드 확인 결과 `grep -rn "agent_progress" pipeline/ web/` → **0 hits** (테이블/emit/마이그레이션 전부 미존재). spec §10 작업순서도 "emit 먼저, 배선 나중"을 명시한다 (`:280`). C4 는 emit 이 채운 행을 읽는 SELECT 만 담당하므로, 아래 Task 들은 (a) 테이블이 없어도 동작하는 **순수 함수 단위테스트**(빈 맵·완료·진행중 케이스 합성)로 그린을 만들고, (b) 최종 라이브 curl 검증은 B3 emit + e2e run 이후로 미룬다. 이 분리는 의도적이다 — FE 로직은 빈/부분 `agent_progress` 에서도 fallback count 로 절대 -1 을 내지 않아야 한다.

> **불변 제약 (디자인 불가침, MEMORY feedback_no_design_change)**: `AgentWorkflowList.tsx` / `AgentTaskItemList.tsx` markup·style·className 단 한 줄도 바꾸지 않는다. 두 파일은 `received`/`processed`/`percent`/`waiting_hil` 만 소비하며 (`AgentWorkflowList.tsx:59-60,87,144,154`, `AgentTaskItemList.tsx:29`), JSON shape 이 동일하면 자동 정합한다. Task 4 는 "변경 없음"을 회귀 테스트로 못박는 것이 목적이다.

---

### Task 1 — 순수 함수 `computeProgressStages` 추출 + 단위 테스트 (route 로직의 testable core)

기존 route 의 percent 산출은 `GET` 핸들러 안에 인라인되어 (`progress/route.ts:141-184`) `import sql from "@/lib/pg"` 와 강결합 → 단위 테스트 불가. spec §6.5 의 "각 stage 독립 계산" 로직을 `import sql` 없는 순수 함수로 분리해 vitest 로 검증한다. 기존 추출 선례: `lib/transforms.ts:13 deriveProgressPercent`, `lib/sim-store.ts:134 computeSimStages` (둘 다 `AgentStageProgress[]` 빌더).

**Files:**
- Create: `web/lib/progress-stages.ts`
- Test: `web/tests/progress-stages.test.ts` (신규)

- [ ] **(1) 실패 테스트 작성** — `web/tests/progress-stages.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import {
  computeProgressStages,
  STAGE_ORDER,
  UI_TO_AGENT_KEY,
  type ProgressInputs,
} from "@/lib/progress-stages";
import type { AgentStageProgress } from "@/lib/types";

function base(overrides: Partial<ProgressInputs> = {}): ProgressInputs {
  return {
    status: "running",
    current_node: "parser",
    fileCount: 7,
    parserRows: 0,
    mapperRows: 0,
    atomizedCount: 0,
    agentProgress: {}, // agent-key → {processed,total}
    ...overrides,
  };
}
const by = (st: AgentStageProgress[], a: string) => st.find((s) => s.agent === a)!;

describe("computeProgressStages", () => {
  it("8 stages 고정 순서/step/agent/is_hil (markup 계약)", () => {
    const st = computeProgressStages(base());
    expect(st.map((s) => s.agent)).toEqual([
      "Collector", "Parser", "Mapper", "Human Review",
      "Atomizer", "Exporter", "Forecaster", "Optimizer",
    ]);
    expect(st.map((s) => s.step)).toEqual([1, 2, 3, 3.5, 4, 5, 6, 7]);
    expect(by(st, "Human Review").is_hil).toBe(true);
    expect(st.filter((s) => s.is_hil).length).toBe(1);
  });

  it("절대 percent=-1 을 내지 않는다 (sentinel 폐기)", () => {
    for (const cn of [null, "collector", "parser", "mapper", "atomizer", "forecaster", "optimizer"]) {
      const st = computeProgressStages(base({ current_node: cn }));
      expect(st.every((s) => s.percent !== -1), `cn=${cn}`).toBe(true);
      expect(st.every((s) => s.percent >= 0 && s.percent <= 100)).toBe(true);
    }
  });

  it("자기 agent_progress 행: received=total, processed=processed, percent=round(p/t*100)", () => {
    const st = computeProgressStages(
      base({ current_node: "parser", agentProgress: { parser: { processed: 3, total: 7 } } }),
    );
    const p = by(st, "Parser");
    expect(p.received).toBe(7);
    expect(p.processed).toBe(3);
    expect(p.percent).toBe(43); // round(3/7*100)=43
  });

  it("division 가드: total=0 행이면 percent=0 (NaN/Infinity 금지)", () => {
    const st = computeProgressStages(
      base({ current_node: "exporter", agentProgress: { exporter: { processed: 0, total: 0 } } }),
    );
    const e = by(st, "Exporter");
    expect(e.percent).toBe(0);
    expect(Number.isFinite(e.percent)).toBe(true);
  });

  it("나중 단계 행 존재 → 그 이전 단계는 100% (자기 행 없어도)", () => {
    // forecaster 가 돌고 있으면 parser/mapper 는 끝난 것
    const st = computeProgressStages(
      base({ current_node: "forecaster", agentProgress: { forecaster: { processed: 2, total: 10 } } }),
    );
    expect(by(st, "Parser").percent).toBe(100);
    expect(by(st, "Mapper").percent).toBe(100);
    expect(by(st, "Forecaster").percent).toBe(20);
  });

  it("status=completed → 전 단계 100% + processed===received (isDone 정합)", () => {
    const st = computeProgressStages(
      base({ status: "completed", current_node: "optimizer", fileCount: 7, parserRows: 330, mapperRows: 330 }),
    );
    for (const s of st) {
      expect(s.percent, s.agent).toBe(100);
      expect(s.processed, s.agent).toBe(s.received);
    }
  });

  it("행 없고 active 이전 단계 → fallback count(received=processed=count, percent=100)", () => {
    // mapper 진행중, parser 는 agent_progress 행 없지만 parserRows fallback 으로 완료 표시
    const st = computeProgressStages(
      base({ current_node: "mapper", parserRows: 330, agentProgress: { mapper: { processed: 50, total: 330 } } }),
    );
    const p = by(st, "Parser");
    expect(p.received).toBe(330);
    expect(p.processed).toBe(330);
    expect(p.percent).toBe(100);
  });

  it("행 없고 active 이후 단계 → 0 (received=processed=0)", () => {
    const st = computeProgressStages(
      base({ current_node: "mapper", agentProgress: { mapper: { processed: 5, total: 330 } } }),
    );
    for (const a of ["Atomizer", "Exporter", "Forecaster", "Optimizer"]) {
      const s = by(st, a);
      expect(s.percent, a).toBe(0);
      expect(s.received, a).toBe(0);
      expect(s.processed, a).toBe(0);
    }
  });

  it("Collector=fileCount(파일수), Human Review=mapperRows fallback (agent_progress 미emit)", () => {
    const st = computeProgressStages(
      base({ current_node: "atomizer", fileCount: 7, mapperRows: 330,
             agentProgress: { atomizer: { processed: 1, total: 5 } } }),
    );
    expect(by(st, "Collector").received).toBe(7);
    expect(by(st, "Collector").percent).toBe(100); // atomizer active → collector 이전 단계
    const hr = by(st, "Human Review");
    expect(hr.received).toBe(330); // mapperRows fallback
    expect(hr.percent).toBe(100);  // atomizer active → HIL 이전 단계
  });

  it("waiting_hil_1 분기 유지: Human Review waiting_hil=true, percent=0, received=mapperRows", () => {
    const st = computeProgressStages(
      base({ status: "waiting_hil_1", current_node: "hil_1", mapperRows: 80 }),
    );
    const hr = by(st, "Human Review");
    expect(hr.waiting_hil).toBe(true);
    expect(hr.percent).toBe(0);
    expect(hr.received).toBe(80);
    expect(hr.processed).toBe(0);
  });

  it("UI명→agent키 매핑 테이블 (parser 등 6개 + Collector/Human Review 제외)", () => {
    expect(UI_TO_AGENT_KEY).toEqual({
      Parser: "parser",
      Mapper: "mapper",
      Atomizer: "atomizer",
      Exporter: "exporter",
      Forecaster: "forecaster",
      Optimizer: "optimizer",
    });
  });

  it("결정성: 동일 입력 2회 → 동일 출력", () => {
    const inp = base({ current_node: "mapper", agentProgress: { mapper: { processed: 50, total: 330 } } });
    expect(computeProgressStages(inp)).toEqual(computeProgressStages(inp));
  });
});
```

- [ ] **(2) 테스트 실행 → FAIL 확인**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx vitest run tests/progress-stages.test.ts
```
기대 출력 (모듈 미존재):
```
Error: Failed to resolve import "@/lib/progress-stages" ... Does the file exist?
```

- [ ] **(3) 최소 구현** — `web/lib/progress-stages.ts` (완전 코드):
```ts
// web/lib/progress-stages.ts
// progress/route.ts 의 percent 산출 순수 코어 (import sql 없음 — 단위테스트 가능).
// spec §6.5: agent_progress per-(run,agent) 행 기반, 각 stage 독립 계산.
// -1 sentinel + index 기반 prev/current/after 폐기.
import type { AgentStageProgress } from "@/lib/types";

export const STAGE_ORDER: Array<{
  step: number;
  agent: string;
  currentNode: string;
  is_hil: boolean;
}> = [
  { step: 1, agent: "Collector", currentNode: "collector", is_hil: false },
  { step: 2, agent: "Parser", currentNode: "parser", is_hil: false },
  { step: 3, agent: "Mapper", currentNode: "mapper", is_hil: false },
  { step: 3.5, agent: "Human Review", currentNode: "hil_1", is_hil: true },
  { step: 4, agent: "Atomizer", currentNode: "atomizer", is_hil: false },
  { step: 5, agent: "Exporter", currentNode: "exporter", is_hil: false },
  { step: 6, agent: "Forecaster", currentNode: "forecaster", is_hil: false },
  { step: 7, agent: "Optimizer", currentNode: "optimizer", is_hil: false },
];

// UI 단계명 → agent_progress.agent 키. Collector/Human Review 는 emit 안 함(fallback count).
export const UI_TO_AGENT_KEY: Record<string, string> = {
  Parser: "parser",
  Mapper: "mapper",
  Atomizer: "atomizer",
  Exporter: "exporter",
  Forecaster: "forecaster",
  Optimizer: "optimizer",
};

// hil_2 / reporter / null 도 atomizer 이후 단계로 처리.
const POST_HIL1_NODES = new Set([
  "atomizer", "exporter", "forecaster", "hil_2", "optimizer", "reporter",
]);

export interface ProgressInputs {
  status: string;
  current_node: string | null;
  fileCount: number;     // Collector total
  parserRows: number;    // Parser fallback count
  mapperRows: number;    // Mapper / Human Review fallback count
  atomizedCount: number; // Atomizer fallback count
  agentProgress: Record<string, { processed: number; total: number }>;
}

function pct(processed: number, total: number): number {
  if (total <= 0) return 0; // division 가드
  return Math.round((processed / total) * 100);
}

export function computeProgressStages(inp: ProgressInputs): AgentStageProgress[] {
  const isCompleted = inp.status === "completed";
  const isWaitingHil = inp.status === "waiting_hil_1";

  // 단계별 fallback total (agent_progress 행 없을 때 사용).
  const FALLBACK_TOTAL: Record<string, number> = {
    Collector: inp.fileCount,
    Parser: inp.parserRows,
    Mapper: inp.mapperRows,
    "Human Review": inp.mapperRows,
    Atomizer: inp.atomizedCount,
    Exporter: inp.mapperRows,
    Forecaster: inp.mapperRows,
    Optimizer: inp.mapperRows,
  };

  // active 단계 위치 (fallback 분기에서 이전/이후 판별용).
  const cn = inp.current_node ?? "collector";
  let activeIdx = STAGE_ORDER.findIndex((s) => s.currentNode === cn);
  if (activeIdx < 0) {
    activeIdx = POST_HIL1_NODES.has(cn) ? STAGE_ORDER.length - 1 : 0;
  }

  // 어떤 agent_progress 행이라도 "그 단계 이후"면, 그 이전 단계는 100% 로 본다.
  const maxRowIdx = STAGE_ORDER.reduce((acc, def, i) => {
    const key = UI_TO_AGENT_KEY[def.agent];
    return key && inp.agentProgress[key] ? Math.max(acc, i) : acc;
  }, -1);

  return STAGE_ORDER.map((def, i): AgentStageProgress => {
    const key = UI_TO_AGENT_KEY[def.agent];
    const row = key ? inp.agentProgress[key] : undefined;
    const fallbackTotal = FALLBACK_TOTAL[def.agent] ?? 0;

    let received: number;
    let processed: number;
    let percent: number;
    let waiting_hil = false;

    if (isCompleted) {
      received = row?.total ?? fallbackTotal;
      processed = received;
      percent = 100;
    } else if (def.is_hil && isWaitingHil && i === activeIdx) {
      // HIL 대기 분기 유지.
      received = fallbackTotal;
      processed = 0;
      percent = 0;
      waiting_hil = true;
    } else if (row) {
      // 자기 agent_progress 행 존재 → 독립 계산.
      received = row.total;
      processed = row.processed;
      percent = pct(row.processed, row.total);
    } else if (i < maxRowIdx || i < activeIdx) {
      // 행 없지만 이후 단계 행이 있거나 active 이전 → 완료로 간주, fallback count.
      received = fallbackTotal;
      processed = fallbackTotal;
      percent = 100;
    } else {
      // active 이후 + 행 없음 → 미시작.
      received = 0;
      processed = 0;
      percent = 0;
    }

    return {
      step: def.step,
      agent: def.agent,
      is_hil: def.is_hil,
      received,
      processed,
      percent,
      waiting_hil,
    };
  });
}
```

- [ ] **(4) 테스트 실행 → PASS 확인**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx vitest run tests/progress-stages.test.ts
```
기대 출력 (끝부분):
```
 Test Files  1 passed (1)
      Tests  12 passed (12)
```

- [ ] **(5) 커밋**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add web/lib/progress-stages.ts web/tests/progress-stages.test.ts && git commit -m "$(cat <<'EOF'
feat(tasks): progress per-stage 독립 계산 순수함수 추출 + 단위테스트

agent_progress per-(run,agent) 행 기반 computeProgressStages.
-1 sentinel + index prev/current/after 폐기, division 가드.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2 — `progress/route.ts` 재작성: `agent_progress` SELECT + `computeProgressStages` 호출

route 의 인라인 percent 로직(`progress/route.ts:120-184`)을 Task 1 순수함수 호출로 교체. `STAGE_ORDER`/`POST_HIL1_NODES` 중복 정의(`:41-65`) 제거하고 `progress-stages.ts` 에서 import. `agent_progress` SELECT 추가. JSON shape (`ok/run_id/date/status/current_node/started_at/completed_at/stages`) **불변**.

**Files:**
- Modify: `web/app/api/runs/progress/route.ts`
- Test (deterministic loop): 라이브 curl (Task 5)

- [ ] **(1) 실패 신호 정의** — route 는 `import sql` 강결합이라 단위테스트 불가. **결정론 pass/fail 루프 = `npx tsc --noEmit` + 라이브 curl JSON assert** (Task 5). 먼저 현재 -1 이 나오는지 baseline 캡쳐 (B3 emit 전이라 09-25 run 없으면 404 → e2e 이후 검증). 즉시 신호:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && grep -n "percent = -1\|percent: -1\|activeIdx\|STAGE_ORDER\|POST_HIL1_NODES" app/api/runs/progress/route.ts
```
기대 (수정 전): `-1` sentinel + `activeIdx` + 로컬 `STAGE_ORDER`/`POST_HIL1_NODES` 가 존재 (`:135-184` 라인들 hit).

- [ ] **(3) 구현** — `web/app/api/runs/progress/route.ts` 의 다음 블록들을 교체.

  (a) import 추가 (`:27` `import type { AgentStageProgress }` 옆):
```ts
import type { AgentStageProgress } from "@/lib/types";
import { computeProgressStages } from "@/lib/progress-stages";
```

  (b) 로컬 `STAGE_ORDER`(`:41-55`) + `POST_HIL1_NODES`(`:57-65`) **삭제** (progress-stages.ts 로 이전됨). `AgentStageProgress` import 는 위 (a) 가 유지.

  (c) `:108-184` (Promise.all 의 countRows 이후 ~ `stages` 빌드 전체)를 교체. 기존:
```ts
  const dateCompact = String(run.report_date ?? "").replace(/-/g, "").slice(0, 8);
  const [fileCount, countRows] = await Promise.all([
    countInputFiles(dateCompact),
    (sql as any)`
      SELECT
        (SELECT COUNT(*)::int FROM parser_activities WHERE run_id = ${run.run_id}) AS parser_rows,
        (SELECT COUNT(*)::int FROM mapper_activities WHERE run_id = ${run.run_id}) AS mapper_rows
    ` as Promise<Array<{ parser_rows: number; mapper_rows: number }>>,
  ]);
```
  로 시작하는 블록부터 `:184` 의 `stages` `.map(...)` 닫힘까지 전부를 아래로 교체:
```ts
  const dateCompact = String(run.report_date ?? "").replace(/-/g, "").slice(0, 8);
  const [fileCount, countRows, progressRows] = await Promise.all([
    countInputFiles(dateCompact),
    (sql as any)`
      SELECT
        (SELECT COUNT(*)::int FROM parser_activities WHERE run_id = ${run.run_id}) AS parser_rows,
        (SELECT COUNT(*)::int FROM mapper_activities WHERE run_id = ${run.run_id}) AS mapper_rows
    ` as Promise<Array<{ parser_rows: number; mapper_rows: number }>>,
    (sql as any)`
      SELECT agent, processed, total
      FROM agent_progress
      WHERE run_id = ${run.run_id}
    ` as Promise<Array<{ agent: string; processed: number; total: number }>>,
  ]);
  const parserRows    = countRows[0]?.parser_rows ?? 0;
  const mapperRows    = countRows[0]?.mapper_rows ?? 0;
  const atomizedCount = run.atomized_count ?? 0;

  // agent_progress 행을 agent-key 맵으로. processed/total 음수 방어.
  const agentProgress: Record<string, { processed: number; total: number }> = {};
  for (const r of progressRows) {
    agentProgress[r.agent] = {
      processed: Math.max(0, Number(r.processed) || 0),
      total: Math.max(0, Number(r.total) || 0),
    };
  }

  const stages: AgentStageProgress[] = computeProgressStages({
    status: run.status,
    current_node: run.current_node,
    fileCount,
    parserRows,
    mapperRows,
    atomizedCount,
    agentProgress,
  });
```
  (`isCompleted`/`isWaitingHil` 로컬 변수 `:99-100` 와 `cn`/`activeIdx`/`STAGE_TOTAL` 블록은 순수함수로 이전됐으므로 제거. `:99-100` 두 줄은 더 이상 참조 안 되면 함께 삭제 — `dead code 정리` 범위.)

  (d) 최종 `return NextResponse.json({...stages})` (`:186-195`) 는 **변경 없음** (shape 불변 확인).

- [ ] **(4) 타입체크 PASS**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx tsc --noEmit 2>&1 | grep "progress/route\|progress-stages" || echo "OK: no route/helper type errors"
```
기대: `OK: no route/helper type errors`

- [ ] **(5) 커밋**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add web/app/api/runs/progress/route.ts && git commit -m "$(cat <<'EOF'
feat(api): progress route agent_progress SELECT + computeProgressStages 배선

index 기반 prev=100/current=-1/after=0 폐기. per-stage 독립.
JSON shape 불변. STAGE_ORDER/POST_HIL1_NODES progress-stages.ts 로 이전.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3 — `tasks/page.tsx`: 가짜 애니메이션 제거 + `pickCurrentAgent` -1 비의존 재작성

서버 percent 가 실값이 되었으므로 클라이언트 측 0→90% 가짜 타이머(`ANIM_DURATION_MS`/`stageActiveAtRef`/250ms `animTick`)는 dead. 제거하고 `rawProgressStages` 직접 사용. `pickCurrentAgent` 의 `percent===-1` 분기 제거.

**Files:**
- Modify: `web/app/(app)/tasks/page.tsx`
- Test (deterministic loop): `npx tsc --noEmit` + `next build` (Task 5)

- [ ] **(1) 실패 신호** — 제거 대상이 아직 있는지:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && grep -n "ANIM_DURATION_MS\|stageActiveAtRef\|animTick\|percent === -1\|animatedProgressStages" "app/(app)/tasks/page.tsx"
```
기대 (수정 전): `:59,60,64,72,282,283,284,288,289,291,297` 등에서 hit.

- [ ] **(3-a) `pickCurrentAgent` 재작성** (`tasks/page.tsx:34-42`). 기존:
```ts
function pickCurrentAgent(stages: AgentStageProgress[]): string | null {
  // percent=-1: DB "진행중" sentinel (received=0 이어도 선택)
  const current =
    stages.find((s) => s.waiting_hil) ??
    stages.find((s) => s.percent === -1) ??
    stages.find((s) => s.received > 0 && s.percent > 0 && s.percent < 100) ??
    stages.filter((s) => s.percent === 100).at(-1);
  return current?.agent ?? null;
}
```
교체:
```ts
function pickCurrentAgent(stages: AgentStageProgress[]): string | null {
  // -1 sentinel 폐기. waiting_hil 우선 → 진행중(received>0 && 미완료) → 마지막 done.
  const current =
    stages.find((s) => s.waiting_hil) ??
    stages.find((s) => s.received > 0 && s.percent < 100 && s.processed !== s.received) ??
    stages.filter((s) => s.percent === 100).at(-1);
  return current?.agent ?? null;
}
```
  (근거: `AgentWorkflowList.tsx:59 inflightStage` 와 동일 판정 — `received>0 && percent<100 && !waiting_hil`. `processed!==received` 추가로 `total=0` 등으로 percent=100 못 찍는 엣지에서도 done 오인 방지. active 0% 케이스 = `received>0, percent=0, processed=0≠received` → 진행중으로 잡힘, spec §6.5 `:232` 요구 충족.)

- [ ] **(3-b) 애니메이션 ref/state/effect 제거** (`tasks/page.tsx:57-74`). 기존:
```ts
  // DB progress 게이지 애니메이션 — percent=-1 (진행중) 단계를 0→90% 부드럽게 채움.
  // 각 단계가 "진행중" 으로 처음 감지된 시각을 기록, 60초에 걸쳐 90% 까지 선형 증가.
  const stageActiveAtRef = useRef<Map<string, number>>(new Map());
  const [animTick, setAnimTick] = useState(0);

  // selectedDate 변경 시 stage 타이머 + items 초기화.
  useEffect(() => {
    stageActiveAtRef.current.clear();
    setDbItems([]);
  }, [selectedDate]);

  // progress 가 running 상태일 때만 250ms 틱.
  useEffect(() => {
    const isRunning = progress?.status === "running" || progress?.status === "waiting_hil_1";
    if (!isRunning) return;
    const id = setInterval(() => setAnimTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, [progress?.status]);
```
교체 (타이머/animTick 삭제, `setDbItems([])` 초기화 effect 는 보존):
```ts
  // selectedDate 변경 시 items 초기화.
  useEffect(() => {
    setDbItems([]);
  }, [selectedDate]);
```
  (`useRef`/`useState` import 는 다른 곳에서 계속 쓰이므로 `import` 라인 변경 없음 — `useRef`: `detailCacheRef`/`prevSimPhaseRef`, `useState`: 다수 유지.)

- [ ] **(3-c) `animatedProgressStages` 제거 + `rawProgressStages` 직접 사용** (`tasks/page.tsx:280-298`). 기존:
```ts
  // 화면용 stages 결정 우선순위: DB progress > sim > mock detail.
  // DB progress 의 percent=-1 (진행중) 단계는 로컬 타이머로 0→90% 애니메이션.
  const ANIM_DURATION_MS = 60_000; // 60초에 걸쳐 90% 까지 (실 파이프라인 속도 반영)
  const rawProgressStages = hasProgress ? (progress as ProgressData).stages : null;
  const animatedProgressStages: AgentStageProgress[] | null = rawProgressStages
    ? rawProgressStages.map((s) => {
        if (s.percent !== -1) return s;
        const now = Date.now();
        if (!stageActiveAtRef.current.has(s.agent)) {
          stageActiveAtRef.current.set(s.agent, now);
        }
        const elapsed = now - stageActiveAtRef.current.get(s.agent)!;
        const pct = Math.min(90, Math.round((elapsed / ANIM_DURATION_MS) * 90));
        return { ...s, percent: pct, processed: Math.floor((s.received * pct) / 100) };
      })
    : null;

  const stages: AgentStageProgress[] = animatedProgressStages
    ?? (isSimSelected ? (simStages as AgentStageProgress[]) : detail?.stages ?? []);
```
교체:
```ts
  // 화면용 stages 결정 우선순위: DB progress(서버 percent 직접) > sim > mock detail.
  const rawProgressStages = hasProgress ? (progress as ProgressData).stages : null;

  const stages: AgentStageProgress[] = rawProgressStages
    ?? (isSimSelected ? (simStages as AgentStageProgress[]) : detail?.stages ?? []);
```

- [ ] **(4) 타입체크 + lint PASS**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx tsc --noEmit 2>&1 | grep "tasks/page" || echo "OK: no tasks/page type errors"
```
기대: `OK: no tasks/page type errors` (제거된 `animTick`/`ANIM_DURATION_MS`/`stageActiveAtRef` 미참조 → unused 에러도 없어야 함; 만약 `animTick` unused 경고 나면 그건 이미 제거됨을 의미).

- [ ] **(5) 커밋**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add "web/app/(app)/tasks/page.tsx" && git commit -m "$(cat <<'EOF'
refactor(tasks): 가짜 0->90% 애니메이션 제거, 서버 percent 직접 사용

ANIM_DURATION_MS/stageActiveAtRef/250ms animTick dead 제거.
pickCurrentAgent -1 의존 폐기 → received>0 && percent<100 && processed!==received.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4 — `AgentWorkflowList.tsx` / `AgentTaskItemList.tsx` 마크업 불변 회귀 못박기

spec §6.5 `:233` + MEMORY `feedback_no_design_change`: 두 컴포넌트는 **변경 금지**. `received=agent_progress.total` / `processed=processed` 가 `isDone(processed===received)` (`AgentWorkflowList.tsx:87`) 와 정합하는지 스냅샷으로 고정. (실제로는 컴포넌트 코드 0줄 변경, 테스트만 추가.)

**Files:**
- Create: `web/tests/agent-workflow-isdone.test.ts` (신규, 순수 로직 회귀)
- **No change**: `AgentWorkflowList.tsx`, `AgentTaskItemList.tsx`

- [ ] **(1) 실패 테스트** — `computeProgressStages` 출력이 컴포넌트의 `isDone`/`inflightStage`/`allDone` 판정과 정합함을 검증 (컴포넌트 로직을 복제한 게 아니라, 출력 계약을 못박음):
```ts
import { describe, it, expect } from "vitest";
import { computeProgressStages, type ProgressInputs } from "@/lib/progress-stages";

// AgentWorkflowList.tsx:59-60,87 의 판정 로직 (markup 불변 — 여기 복제는 계약 고정용).
const isDone = (s: { received: number; processed: number; waiting_hil: boolean }) =>
  s.received > 0 && s.processed === s.received && !s.waiting_hil;
const isInflight = (s: { received: number; percent: number; waiting_hil: boolean }) =>
  s.received > 0 && s.percent < 100 && !s.waiting_hil;

function inp(o: Partial<ProgressInputs> = {}): ProgressInputs {
  return { status: "running", current_node: "mapper", fileCount: 7,
    parserRows: 330, mapperRows: 330, atomizedCount: 0, agentProgress: {}, ...o };
}

describe("AgentWorkflowList 계약 — markup 불변", () => {
  it("completed 단계는 isDone=true (processed===received 보장)", () => {
    const st = computeProgressStages(inp({ status: "completed", current_node: "optimizer", atomizedCount: 330 }));
    expect(st.every(isDone)).toBe(true);
  });
  it("진행중 mapper(50/330)는 isInflight=true, isDone=false", () => {
    const st = computeProgressStages(inp({ agentProgress: { mapper: { processed: 50, total: 330 } } }));
    const m = st.find((s) => s.agent === "Mapper")!;
    expect(isInflight(m)).toBe(true);
    expect(isDone(m)).toBe(false);
  });
  it("active 이전 단계(Parser)는 isDone=true", () => {
    const st = computeProgressStages(inp({ agentProgress: { mapper: { processed: 50, total: 330 } } }));
    expect(isDone(st.find((s) => s.agent === "Parser")!)).toBe(true);
  });
  it("width=`${percent}%` 가 항상 0..100 (NaN/-1 금지 — style 깨짐 방지)", () => {
    const st = computeProgressStages(inp({ agentProgress: { exporter: { processed: 0, total: 0 } } }));
    for (const s of st) expect(s.percent).toBeGreaterThanOrEqual(0), expect(s.percent).toBeLessThanOrEqual(100);
  });
});
```

- [ ] **(2) FAIL 확인** (모듈은 Task1 에서 생겼으므로 여기선 로직 미스매치가 있으면 실패. Task1·2·3 후라면 통과해야 함 — 순서상 Task1 직후 실행해도 됨):
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx vitest run tests/agent-workflow-isdone.test.ts
```
초기 작성 시점에 파일만 없으면 resolve 에러 → 작성 후 PASS.

- [ ] **(3) 구현** — 컴포넌트 코드 **변경 없음**. `git diff --stat` 로 두 파일 무변경 증명이 곧 구현 완료:
```
cd "/Users/kyungseoplee/Project Agent/CPIA" && git diff --stat HEAD -- web/app/components/tasks/AgentWorkflowList.tsx web/app/components/tasks/AgentTaskItemList.tsx
```
기대 출력: (빈 출력 — 두 파일 변경 0)

- [ ] **(4) PASS 확인**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx vitest run tests/agent-workflow-isdone.test.ts
```
기대: `Tests  4 passed (4)`

- [ ] **(5) 커밋**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA" && git add web/tests/agent-workflow-isdone.test.ts && git commit -m "$(cat <<'EOF'
test(tasks): AgentWorkflowList isDone/inflight 계약 회귀 (markup 불변)

received=total/processed 가 isDone(processed===received)·width=percent% 와 정합.
컴포넌트 코드 무변경 (design 불가침).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5 — 전체 그린 게이트 + 라이브 결정론 검증 (B3 emit + e2e 이후)

**Files:** (검증 전용, 코드 변경 없음)

- [ ] **(a) 전체 단위 테스트 그린**:
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx vitest run
```
기대: 기존 9 + 신규 2 파일 모두 pass, 회귀 0.

- [ ] **(b) 타입 + 프로덕션 빌드 통과** (FE 결정론 pass/fail 루프 — 단위테스트 불가 영역):
```
cd "/Users/kyungseoplee/Project Agent/CPIA/web" && npx tsc --noEmit && npm run build 2>&1 | tail -15
```
기대: `tsc` 무에러, `next build` 끝에 `✓ Compiled successfully` + `/api/runs/progress` route 가 빌드 목록에 ƒ(Dynamic) 로 표기.

- [ ] **(c) 라이브 curl JSON assert** — **선행: B3 emit + 09-25 e2e run 1회 완주** (spec §7). dev 서버는 5537 에서 이미 가동 중 (확인: `curl 5536` 무응답, `curl 5537` → `{"ok":false,"error":"no run for date"}` = 엔드포인트 도달 + DB 연결 정상, 09-25 run 미존재). e2e 후:
```
curl -s "http://127.0.0.1:5537/api/runs/progress?date=2025-09-25" | python3 -m json.tool
```
assert (수동/스크립트):
  1. 모든 `stages[].percent !== -1` (sentinel 폐기 확인)
  2. 모든 `0 <= percent <= 100`
  3. 모든 `processed <= received`
  4. `status==="running"` 중 폴링 2회 시 동일 agent 의 `processed` **단조 증가** (GREATEST 보장, spec §6.6)
  5. 병렬 구간(exporter‖forecaster): 둘 다 `received>0` 동시 점진

  결정론 스크립트(선택):
```
for i in 1 2 3; do curl -s "http://127.0.0.1:5537/api/runs/progress?date=2025-09-25" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); st=d['stages']; \
assert all(s['percent']!=-1 for s in st), 'sentinel -1 남음'; \
assert all(0<=s['percent']<=100 for s in st), 'percent 범위'; \
assert all(s['processed']<=s['received'] for s in st), 'processed>received'; \
print('OK', [(s['agent'],s['processed'],s['received'],s['percent']) for s in st])"; sleep 2; done
```
기대: 3회 모두 `OK [...]`, processed 단조 증가.

- [ ] **(d) (선택) playwright 스냅샷**: `/tasks` 진입 → 09-25 카드 선택 → AgentWorkflowList 게이지가 0→100 점프 없이 점진, HIL 단계 노랑(`bg-sun`), 나머지 민트(`bg-mint`). spec §6.6 의 "단조+카드 점진" 육안 확인.


## 사전 사실 (실 코드 확인 — file:line)

- `pipeline/agents/mapper.py:515` — `requires_review = confidence < cfg.conf_threshold or wa_result.source == "hil_required"` (high-conf 성공 분기). 이게 유일하게 `True`/`False` 가변. 조기 HIL 반환(:447/:488/:500)은 이미 `True` 하드코딩. `mapping_conf`(:521)는 `confidence` 그대로 반환 — FE 표시용, 불변.
- `pipeline/graph.py:160-165` — mapper_node 가 hil_1(interrupt) **전**에 `insert_mapper_activities_batch(run_id, today, mapped)` 호출 → DB `requires_review` 컬럼은 mapper 산출값으로 적재됨(state-only 아님).
- `pipeline/graph.py:271` — hil_1_node 의 `corrected = _apply_corrections(mapped, corrections)`. 이후 `:273-302` 은 `corrections` 가 있을 때만 `insert_mapping_correction`(mapping_corrections 테이블) row 만 insert. **`mapper_activities` 재persist 없음** → resume 후에도 DB `requires_review=True` 잔존.
- `pipeline/db.py:647-744` — `insert_mapper_activities_batch`. ON CONFLICT `(run_id, idx)` DO UPDATE SET 가 `requires_review = EXCLUDED.requires_review`(:704) + `wa`(:700)/`l6_main`(:701)/`mapping_source`(:703) 포함 → 동일 (run_id, idx) 로 재호출 시 upsert 갱신됨. 멱등.
- `web/app/api/mock/review/route.ts:42` — `LIMIT 300` (cards 쿼리). `WHERE pr.status='waiting_hil_1' AND ma.requires_review=TRUE AND ma.is_mock=${useMock}`(:38-40), `useMock = CPIA_DEMO_FALLBACK==='on'`(:15).
- `web/app/api/mock/agent-tasks/[date]/route.ts` — `LIMIT 200` **2곳**: mapperItems(:32), parserItems(:48). `useMock = CPIA_DEMO_FALLBACK==='on'`(:21).
- `pipeline/api.py:304-363` — `@app.post("/api/runs/{run_id}/hil_1/resume")` (라우트 경로는 `/api/runs/{run_id}/hil_1/resume`, FE proxy `/api/hil/resume` 가 이걸 호출). 현재 `result = await graph.ainvoke(Command(resume=...))`(:335-338) **동기 대기** → atomizer~optimizer 완주까지 블록 → `next_node` 반환.
- `pipeline/api.py:278-301` — `/run` 의 백그라운드 패턴: `async def _bg()` 안에서 `await graph.ainvoke(...)`, 실패 시 `set_run_status(postgres_url, run_id, "failed")`, `asyncio.create_task(_bg())` 후 즉시 `return RunResponse(run_id=...)`. `import asyncio`(:18), `from pipeline.db import PGClient, set_run_status`(:36) 이미 존재.
- `web/app/api/hil/resume/route.ts:43-56` — **fire-and-forget 아님**: `await fetch(.../hil_1/resume, { signal: AbortSignal.timeout(170_000) })` 후 `data.next_node` 읽음 → 170s 타임아웃 위험의 실제 출처. (spec §5.1 #5 의 "FE 이미 fire-and-forget" 서술은 **부정확** — open_ambiguity 로 플래그.)
- `infra/docker-compose.yml` — `pipeline` env(:67-79)·`web` env(:96-103) 어디에도 `CPIA_HIL_AUTO_BYPASS`/`CPIA_DEMO_FALLBACK` 없음. .env 파일 자체 없음(repo). 두 변수 모두 **현재 미설정** = 데모 런타임 기본값. graph.py:251 의 bypass 게이트는 미설정 시 빈 문자열 → `("1","true","on","yes")` 불포함 → bypass off. review route 의 `is_mock=${useMock}` 는 미설정 시 `false` → live(is_mock=FALSE) row 노출. **둘 다 원하는 상태이므로 코드 변경 불요, 검증만**.

검증 환경 (CLAUDE.md):
```
PYTHONPATH=/Users/kyungseoplee/Project Agent/CPIA \
/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python -m pytest ...
```

---

### Task C5-1 — mapper.py:515 전건 HIL 강제 (`requires_review = True`)

**Files:**
- Modify `pipeline/agents/mapper.py:515`
- Create `pipeline/tests/test_mapper_requires_review_all.py` (결정론 단위 — Azure/Chroma/PG 패치)
- Confirm (변경 불요 예상) `pipeline/tests/test_mapper_node.py:60`

전건 HIL: 성공 분기(:515)도 무조건 `True`. live `test_mapper_node.py` 는 Azure 호출이라 CI 비결정 → 결정론 패치 테스트를 신설해 line 515 분기만 고정 검증.

- [ ] **(1) 실패 테스트 작성** — `pipeline/tests/test_mapper_requires_review_all.py`:
```python
"""mapper.map_activity — 전건 HIL (C5-1). high-conf 성공 분기에서도 requires_review=True.

Azure/Chroma/PG 를 모두 패치해 LLM 호출 없이 line 515 분기를 결정론적으로 구동.
Spec 2026-06-02-cpia-0925-demo-refinement-design.md §5.1 #1.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.agents.mapper import MapperConfig, map_activity
from pipeline.state import Activity


def _cfg() -> MapperConfig:
    return MapperConfig(
        azure_endpoint="https://x",
        azure_api_key="k",
        azure_api_version="2024-12-01-preview",
        llm_model="m",
        embedding_model="e",
        postgres_url="postgresql://t:t@localhost:5432/t",
        chroma_host="localhost",
        chroma_port=8000,
    )


def _activity() -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": None,
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": "남웅건설",
        "unit": "M2",
        "today_qty": 320.0,
        "work_content": "기초 거푸집 설치",
        "conditions": [],
        "assigned_workers": 81.0,
        "worker_source": "parsed",
        "plan_total_qty": None,
        "plan_mh": None,
        "requires_review": False,
        "wa": None,
        "mapping_conf": None,
        "mapping_source": None,
    }


def _fake_azure() -> MagicMock:
    """confidence=0.99 (conf_threshold=0.7 초과) → 원래라면 requires_review=False 분기."""
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.0] * 1536)]
    )
    msg = SimpleNamespace(
        content=json.dumps({"choice": 0, "confidence": 0.99, "reason": "ok"})
    )
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)]
    )
    return client


def _fake_coll() -> MagicMock:
    coll = MagicMock()
    # cand_pool_set 에 들어가 resolve_wa 가 hil_required 가 아니라 정상 source 를 내도록
    # (wa, l6_main) 후보 1개.
    coll.query.return_value = {
        "ids": [["d0"]],
        "metadatas": [[{"wa": "CUB", "l6_main": "철근콘크리트공사"}]],
        "documents": [["CUB / 철근콘크리트공사"]],
        "distances": [[0.01]],
    }
    return coll


def test_map_activity_high_conf_still_requires_review() -> None:
    cfg = _cfg()
    fake_pg = MagicMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    # BP 등록된 (wa, l6) 1개 → resolve_wa 가 정상 source (hil_required 아님).
    fake_pg.fetch_bp_candidates = AsyncMock(
        return_value=[{"wa": "CUB", "l6_main": "철근콘크리트공사"}]
    )

    with (
        patch("pipeline.agents.mapper.AzureOpenAI", return_value=_fake_azure()),
        patch("pipeline.agents.mapper._get_wbs_master_coll", new=AsyncMock(return_value=_fake_coll())),
        patch("pipeline.agents.mapper.PGClient", return_value=fake_pg),
    ):
        result = asyncio.run(map_activity(_activity(), parsed_report=None, cfg=cfg))

    # high-conf(0.99 > 0.7) + 정상 source 인데도 전건 HIL → True.
    assert result["requires_review"] is True
    # mapping_conf 는 confidence 원본 그대로 (FE 표시용, 불변).
    assert result["mapping_conf"] == 0.99
    # l6/wa 는 정상 결정 — 전건 HIL 은 review 만 강제, 매핑 자체는 유지.
    assert result["l6_main"] == "철근콘크리트공사"
```
- [ ] **(2) 실패 실행 (RED)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_mapper_requires_review_all.py -q
```
기대(FAIL): `assert False is True` — 현재 :515 가 `confidence(0.99) < 0.7 → False`, `source != hil_required → False` → `requires_review=False`.
- [ ] **(3) 구현** — `pipeline/agents/mapper.py:515` RHS 치환:
```python
    # 2026-06-02 (C5-1): 전건 HIL — 점수 무관 모든 매핑이 review UI 를 거치도록 강제.
    # mapping_conf(:521)는 confidence 원본 그대로 반환(FE 표시). Spec §5.1 #1.
    requires_review = True
```
(주의: `confidence` / `wa_result.source` 는 :522 `mapping_source` 에 여전히 사용되므로 변수 자체는 유지. RHS 만 교체.)
- [ ] **(4) 통과 실행 (GREEN)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_mapper_requires_review_all.py -q
```
기대: `1 passed`.
- [ ] **(5) 회귀 — `test_mapper_node.py` 영향 확인**: 이 파일은 live Azure 테스트. `test_map_activity_namwung`(:60)은 이미 `assert result["requires_review"] is True`(hil_required 분기라 원래 True), `test_map_activity_sebo`(:88)는 `requires_review` 를 **assert 하지 않음**(l6_main/wa/mapping_source 만). → **전건 True 변경으로 깨지는 assert 없음, 수정 불요**. 단 Azure 키 필요해 CI 에선 skip 될 수 있음. 키 보유 시:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_mapper_node.py -q
```
기대: `2 passed` (또는 azure_openai_env fixture 미충족 시 skip). grep 으로 `assert ... requires_review ... False` 부재 사전 확인:
```
grep -n "requires_review" pipeline/tests/test_mapper_node.py
```
기대 출력: `60:    assert result["requires_review"] is True` (False assert 없음 → 회귀 0).
- [ ] **(6) 커밋**:
```
git add pipeline/agents/mapper.py pipeline/tests/test_mapper_requires_review_all.py
git commit -m "$(cat <<'EOF'
C5-1: mapper 전건 HIL — requires_review 무조건 True (mapper.py:515)

점수 무관 모든 매핑이 review UI 를 거쳐 승인 확정해야 atomizer 진행.
mapping_conf(:521)는 confidence 원본 그대로 반환(FE 표시 불변).
결정론 단위 테스트(Azure/Chroma/PG 패치)로 high-conf 분기도 True 검증.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C5-2 — resume 후 mapper_activities 재persist (requires_review=False 반영)

**Files:**
- Modify `pipeline/graph.py` hil_1_node (`:271` 직후, `:304` return 전)
- Create `pipeline/tests/test_hil1_repersist.py` (결정론 — PGClient 패치, insert 인자 검증)

`_apply_corrections` 가 만든 `corrected`(전건 review_needed → 전부 `requires_review=False` + wa/l6/source 갱신)를 `insert_mapper_activities_batch` 로 재호출 → ON CONFLICT (run_id,idx) upsert 로 DB 갱신. `/api/runs/items` Human Review 영구 hil_pending 해소.

- [ ] **(1) 실패 테스트 작성** — `pipeline/tests/test_hil1_repersist.py`:
```python
"""hil_1_node — resume 후 mapper_activities 재persist (C5-2).

_apply_corrections 직후 corrected mapped 로 insert_mapper_activities_batch 재호출
→ DB requires_review=False + wa/l6/source upsert. Spec §5.1 #2.

PGClient 를 패치해 실 PG 없이 insert 호출 인자만 결정론적으로 검증.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.state import Activity


def _activity(idx: int, requires_review: bool) -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": "철근콘크리트공사",
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": f"company_{idx}",
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": f"work_{idx}",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "OLD",
        "mapping_conf": 0.5,
        "mapping_source": "hil_required",
        "requires_review": requires_review,
    }


def test_hil1_resume_repersists_mapper_activities() -> None:
    import pipeline.graph as graph_module
    from pipeline.graph import hil_1_node

    run_id = str(uuid.uuid4())
    mapped = [_activity(0, True), _activity(1, True)]
    state = {"mapped": mapped, "run_id": run_id, "date": "2025-09-25"}

    # cfg.mapper.postgres_url 만 필요.
    cfg = MagicMock()
    cfg.mapper.postgres_url = "postgresql://t:t@localhost:5432/t"

    fake_pg = MagicMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    fake_pg.insert_mapping_correction = AsyncMock()
    fake_pg.insert_mapper_activities_batch = AsyncMock()

    # interrupt() 가 corrections 래퍼 반환하도록 패치 (idx 0 만 보정, idx 1 은 추천 수용).
    resume_payload = {"corrections": {"0": {"wa": "CORRECTED", "l6_main": "철근콘크리트공사"}}}

    with (
        patch.object(graph_module, "PGClient", return_value=fake_pg),
        patch.object(graph_module, "interrupt", return_value=resume_payload),
    ):
        result = asyncio.run(hil_1_node(state, cfg=cfg))

    # 재persist 1회 호출됨.
    fake_pg.insert_mapper_activities_batch.assert_awaited_once()
    call = fake_pg.insert_mapper_activities_batch.await_args
    passed = call.kwargs["activities"] if "activities" in call.kwargs else call.args[2]
    # corrected 전건 requires_review=False.
    assert all(a["requires_review"] is False for a in passed)
    # idx 0 — 사용자 보정 wa.
    assert passed[0]["wa"] == "CORRECTED"
    assert passed[0]["mapping_source"] == "user_corrected"
    # idx 1 — 추천 수용 (wa 유지, source user_corrected).
    assert passed[1]["wa"] == "OLD"
    assert passed[1]["mapping_source"] == "user_corrected"
    # state 반환도 corrected.
    assert all(a["requires_review"] is False for a in result["mapped"])
```
> 주의: `hil_1_node` 시그니처는 `(state, cfg)`. `interrupt` 는 `graph.py` 모듈 전역 import (`from langgraph.types import interrupt` 류) — 실제 import 라인 확인 후 patch 대상 정확히 (`graph_module.interrupt`). insert 호출 keyword(run_id/report_date/activities) 는 기존 mapper_node 호출(graph.py:160-164) 과 동일 keyword 로 맞춤.
- [ ] **(2) 실패 실행 (RED)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_hil1_repersist.py -q
```
기대(FAIL): `AssertionError: Expected 'insert_mapper_activities_batch' to have been awaited once. Awaited 0 times.` — 현재 hil_1_node 는 mapping_corrections 만 insert.
- [ ] **(3) 구현** — `pipeline/graph.py` hil_1_node 의 mapping_corrections insert 블록 직후(현재 `:301 finally: await pg.close()` 와 같은 `try/finally` 안, `for idx, c in corrections.items()` 루프 다음 줄)에 재persist 추가. **`if cfg is not None` 분기 안에서**, corrections 유무와 무관하게(전건 review 라 corrected 전부 False 로 바뀜) 항상 재persist 하도록 `if cfg is not None:` 블록을 분리/확장:

기존(:273):
```python
    if cfg is not None and corrections:
        pg = PGClient(cfg.mapper.postgres_url)
        await pg.connect()
        try:
            run_id_str = state["run_id"]
            run_id = uuid.UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
            today = _date.fromisoformat(state["date"])
            for idx, c in corrections.items():
                original_a = mapped[idx]
                await pg.insert_mapping_correction(
                    ...
                )
        finally:
            await pg.close()
```
교체:
```python
    if cfg is not None:
        pg = PGClient(cfg.mapper.postgres_url)
        await pg.connect()
        try:
            run_id_str = state["run_id"]
            run_id = uuid.UUID(run_id_str) if isinstance(run_id_str, str) else run_id_str
            today = _date.fromisoformat(state["date"])
            # 보정 row 만 mapping_corrections 감사 로그에 기록 (기존 동작).
            for idx, c in corrections.items():
                original_a = mapped[idx]
                await pg.insert_mapping_correction(
                    run_id=run_id,
                    report_date=today,
                    original={
                        "work_content": original_a["work_content"],
                        "company": original_a.get("company"),
                        "trade": original_a.get("trade"),
                        "wa": original_a.get("wa"),
                        "l6_main": original_a.get("l6_main"),
                        "mapping_conf": original_a.get("mapping_conf"),
                        "mapping_source": original_a.get("mapping_source"),
                    },
                    corrected={
                        "wa": c["wa"],
                        "l6_main": c["l6_main"],
                        "mapping_source": "user_corrected",
                        "correction_type": "replace",
                    },
                )
            # 2026-06-02 (C5-2): resume 후 mapper_activities 재persist.
            # corrected 는 전건 requires_review=False + wa/l6/source 갱신.
            # ON CONFLICT (run_id, idx) upsert (db.py:695-729) 로 DB 컬럼 갱신
            # → /api/runs/items Human Review 가 done 표시 (영구 hil_pending 해소).
            await pg.insert_mapper_activities_batch(
                run_id=run_id,
                report_date=today,
                activities=corrected,
            )
        finally:
            await pg.close()
```
(주의: `corrections` 가 빈 dict 여도 — 전건 HIL 이지만 사용자가 보정 0건으로 전부 추천 수용한 경우 — `corrected` 는 전부 `requires_review=False` 이므로 재persist 가 반드시 실행돼야 함. 그래서 게이트를 `cfg is not None and corrections` → `cfg is not None` 으로 완화. 단위 테스트 path 인 `cfg=None`(test_graph_hil1.py:51) 은 여전히 skip → 기존 통과.)
- [ ] **(4) 통과 실행 (GREEN)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_hil1_repersist.py pipeline/tests/test_graph_hil1.py -q
```
기대: `4 passed` (신규 1 + 기존 3). 기존 `test_graph_hil1.py` 는 `cfg=None` path 라 재persist skip → 무영향.
- [ ] **(5) 실 DB 검증 루프 (e2e 시)** — resume 후:
```
PGPASSWORD=<pw> psql -h localhost -p 5532 -U cpia -d cpia -tc \
"SELECT count(*) FROM mapper_activities WHERE run_id='<RUN_ID>' AND requires_review = TRUE;"
```
기대 출력: `0` (전건 False 로 재persist). resume 전엔 전건 True 라 = 전체 행 수.
- [ ] **(6) 커밋**:
```
git add pipeline/graph.py pipeline/tests/test_hil1_repersist.py
git commit -m "$(cat <<'EOF'
C5-2: hil_1 resume 후 mapper_activities 재persist (requires_review=False)

_apply_corrections 직후 corrected mapped 로 insert_mapper_activities_batch 재호출.
ON CONFLICT (run_id,idx) upsert 로 requires_review/wa/l6/source 갱신.
게이트 cfg!=None (corrections 비어도 전건 False 반영). Human Review 영구 hil_pending 해소.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C5-3 — web review LIMIT 300→500 + agent-tasks LIMIT 200→500 (2곳)

**Files:**
- Modify `web/app/api/mock/review/route.ts:42`
- Modify `web/app/api/mock/agent-tasks/[date]/route.ts:32` (mapperItems) + `:48` (parserItems)
- Verify: `tsc`/`next build` + curl 재파싱

마크업 무변경, load-bearing 데이터 변경(전건 HIL 로 review row 증가 → 300 cap 위험 회피, 안전마진 500).

- [ ] **(1) 검증 루프 정의 (FE — 단위 테스트 불가)**: (a) 빌드 통과 + (b) curl 로 endpoint 가 cap 내 전체 행 반환하는지 카운트 비교. 사전 RED 신호: 전건 HIL 후 review 행 > 300 이면 cards 누락. 실 e2e 후 측정.
- [ ] **(2) 변경 전 카운트 기준 확보** (실 run 후):
```
curl -s http://localhost:5535/api/mock/review | python3 -c "import sys,json;print(len(json.load(sys.stdin)['cards']))"
PGPASSWORD=<pw> psql -h localhost -p 5532 -U cpia -d cpia -tc \
"SELECT count(*) FROM mapper_activities ma JOIN pipeline_runs pr USING(run_id) WHERE pr.status='waiting_hil_1' AND ma.requires_review=TRUE AND ma.is_mock=FALSE;"
```
기대: cards 수 == DB 수 (cap 내). 7개사 ~115행이라 300 으로도 충분하나 안전마진 상향.
- [ ] **(3) 구현 — review LIMIT**: `web/app/api/mock/review/route.ts:42`
```
    LIMIT 500
```
(주석 `:25` `LIMIT 50 → 300` 은 history — 손대지 않음. surgical: LIMIT 숫자만.)
- [ ] **(3b) 구현 — agent-tasks LIMIT 2곳**: `web/app/api/mock/agent-tasks/[date]/route.ts`
  - mapperItems(:32) `LIMIT 200` → `LIMIT 500`
  - parserItems(:48) `LIMIT 200` → `LIMIT 500`
- [ ] **(4) 빌드 통과 (GREEN)**:
```
cd /Users/kyungseoplee/Project\ Agent/CPIA/web && npm run build
```
기대: `✓ Compiled successfully` / 타입에러 0. (`/api/mock/review`, `/api/mock/agent-tasks/[date]` 라우트 빌드.)
재파싱 카운트(실 run 후): `curl ... | ... len(cards)` == DB count(<=500).
- [ ] **(5) 커밋**:
```
git add web/app/api/mock/review/route.ts web/app/api/mock/agent-tasks/\[date\]/route.ts
git commit -m "$(cat <<'EOF'
C5-3: review·agent-tasks LIMIT 상향 (300/200 → 500)

전건 HIL 로 review row 증가 — cap 누락 방지 안전마진. 마크업 무변경, 데이터 변경.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C5-4 — hil_1_resume 백그라운드화 (즉시 반환, FE 170s 타임아웃 회피)

**Files:**
- Modify `pipeline/api.py:304-363` (`hil_1_resume` 엔드포인트)
- Modify `pipeline/tests/test_api_hil1_resume.py` (next_node 계약 변경 반영)

`/run`(:278-301) 처럼 `graph.ainvoke(Command(resume=...))` 를 `asyncio.create_task(_bg())` 백그라운드로 옮기고 즉시 반환. 단 현재 `Hil1ResumeResponse.next_node: str` 계약을 **즉시 반환이라 다음 노드 미상** → 응답 shape 변경 필요(open_ambiguity: A안 채택).

- [ ] **(1) 실패 테스트 — 기존 계약 깨짐 확인 + 새 계약 작성**: `test_api_hil1_resume.py` 의 `test_hil1_resume_returns_next_node`(:60-85)는 `next_node=="atomizer"` 를 동기 결과에서 기대. 백그라운드화 시 즉시 반환이라 next_node 미상 → 이 테스트가 새 계약과 충돌. **새 계약(A안)**: 즉시 `{"ok": true, "run_id": "<id>"}` 반환, ainvoke 는 create_task. 기존 검증 테스트들(thread_id 전달, Command 래퍼, 422 bad value)은 유지하되 호출이 백그라운드여도 인자 검증 가능하도록 조정. 신규/수정 테스트:
```python
@pytest.mark.asyncio
async def test_hil1_resume_returns_immediately_and_schedules_bg(
    mock_pg: MagicMock,
) -> None:
    """C5-4: resume 는 즉시 200 + {ok, run_id} 반환, ainvoke 는 백그라운드.

    동기 대기 제거 → FE 170s 타임아웃 회피. next_node 동기 반환 계약 폐기.
    """
    import asyncio as _asyncio

    started = _asyncio.Event()
    finished = _asyncio.Event()

    async def _slow_invoke(*a, **k):
        started.set()
        await _asyncio.sleep(0.2)  # 다운스트림 장시간 모사
        finished.set()
        return {"current_node": "atomizer"}

    slow_graph = MagicMock()
    slow_graph.ainvoke = _slow_invoke

    run_id = str(uuid.uuid4())
    corrections = {"0": {"wa": "WA-A", "l6_main": "구조"}}

    with (
        patch.object(api_module, "PGClient", return_value=mock_pg),
        patch.object(api_module, "build_graph", return_value=slow_graph),
        patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
    ):
        async with api_module.lifespan(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                res = await client.post(
                    f"/api/runs/{run_id}/hil_1/resume",
                    json={"corrections": corrections},
                )
                # 응답이 다운스트림 완료 전에 돌아옴.
                assert res.status_code == 200
                assert finished.is_set() is False
                body = res.json()
                assert body["ok"] is True
                assert body["run_id"] == run_id
                # 백그라운드 task 가 실제로 스케줄·완주하는지 대기.
                await _asyncio.wait_for(finished.wait(), timeout=2.0)
```
또한 `test_hil1_resume_returns_next_node`(:60-85) 는 새 계약에 맞춰 **수정**(next_node assert → ok/run_id assert) 또는 위 테스트로 대체. `test_hil1_resume_passes_thread_id`(:128)·`test_hil1_resume_preserves_string_key_in_command_resume`(:164) 는 백그라운드 task 가 ainvoke 를 호출한 뒤여야 assert 성립 → 각 테스트 끝에 `await asyncio.sleep(0)` 또는 task 완료 대기 추가. 422 테스트(:93)는 Pydantic 검증이 create_task 전이라 무영향.
- [ ] **(2) 실패 실행 (RED)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_api_hil1_resume.py -q
```
기대(FAIL): 신규 `test_hil1_resume_returns_immediately_and_schedules_bg` 가 `KeyError: 'ok'`/`finished.is_set() is True`(현재 동기라 반환 시 이미 완료). 기존 next_node 테스트는 아직 통과.
- [ ] **(3) 구현** — `pipeline/api.py:304-363` 재작성. 응답 모델 `Hil1ResumeResponse`(:62-65)는 동기 next_node 반환 다른 경로에서 안 쓰면 새 모델로 교체(open_ambiguity B 참조 — 여기선 신규 `Hil1ResumeAck` 추가, 기존 모델 보존):
```python
class Hil1ResumeAck(BaseModel):
    """C5-4: resume 는 백그라운드 실행 — 즉시 ack. next_node 동기 반환 폐기."""

    ok: bool
    run_id: str
```
엔드포인트 본문(`:324` graph 추출 ~ `:363`)을 교체:
```python
    graph = app.state.graph
    pg: PGClient = app.state.pg
    postgres_url: str = app.state.cfg.atomizer.postgres_url

    corrections_payload: dict[str, dict] = {
        k: {"wa": v.wa, "l6_main": v.l6_main} for k, v in body.corrections.items()
    }

    async def _bg() -> None:
        try:
            # langgraph 1.2.0 falsy-resume 미전달 회피 — truthy 래퍼 (hil_1_node 언랩).
            await graph.ainvoke(
                Command(resume={"corrections": corrections_payload}),
                config={"configurable": {"thread_id": run_id}},
            )
        except EmptyChannelError:
            # checkpoint 없음 — 백그라운드라 응답엔 반영 못 함. 로그만.
            import traceback as _tb
            print(f"[hil_1_resume bg 404:{run_id}]\n{_tb.format_exc()}",
                  file=__import__("sys").stderr, flush=True)
            await set_run_status(postgres_url, run_id, "failed")
        except Exception:  # noqa: BLE001
            import traceback as _tb
            print(f"[hil_1_resume bg FAILED:{run_id}]\n{_tb.format_exc()}",
                  file=__import__("sys").stderr, flush=True)
            await set_run_status(postgres_url, run_id, "failed")

    asyncio.create_task(_bg())
    return Hil1ResumeAck(ok=True, run_id=run_id)
```
`response_model=Hil1ResumeResponse` → `response_model=Hil1ResumeAck` 로 데코레이터(:304) 변경. (EmptyChannelError/InvalidUpdateError 의 동기 404/409 는 즉시 반환이라 검출 불가 → 백그라운드 로그+status=failed 로 격하. open_ambiguity A 에 트레이드오프 명시.)
- [ ] **(3b) FE proxy 정합** — `web/app/api/hil/resume/route.ts:43-56`: FastAPI 가 이제 즉시 `{ok, run_id}` 반환하므로 170s 타임아웃 불필요. **단 디자인 불가침/surgical 원칙상 FE 동작이 이미 정상이면 변경 최소화**. 실제로 현재 FE 는 `await fetch(..., signal: AbortSignal.timeout(170_000))` 후 `data.next_node` 읽음(:49,56). 백엔드가 즉시 반환하면 이 await 도 즉시 끝나 타임아웃 도달 안 함 → **FE 무변경으로도 동작**. `data.next_node` 는 이제 없지만 `data?.next_node ?? null`(:56) 가드라 null 반환 → 무해. **FE 는 변경하지 않음**(open_ambiguity C 참조). (만약 next_node 를 FE 가 라우팅에 쓴다면 변경 필요 — grep 으로 확인: `grep -rn "next_node" web/`.)
- [ ] **(4) 통과 실행 (GREEN)**:
```
PYTHONPATH=/Users/kyungseoplee/Project\ Agent/CPIA \
/Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -m pytest \
pipeline/tests/test_api_hil1_resume.py -q
```
기대: 전체 passed (신규 1 + 수정된 기존). FE grep 확인:
```
grep -rn "next_node" /Users/kyungseoplee/Project\ Agent/CPIA/web/
```
기대: `app/api/hil/resume/route.ts:56` 1곳만(`?? null` 가드) → FE 무변경 안전.
- [ ] **(5) 커밋**:
```
git add pipeline/api.py pipeline/tests/test_api_hil1_resume.py
git commit -m "$(cat <<'EOF'
C5-4: hil_1_resume 백그라운드화 — 즉시 ack, FE 170s 타임아웃 회피

graph.ainvoke(Command(resume=...)) 를 asyncio.create_task(_bg) 로 (/run 패턴).
응답 Hil1ResumeResponse(next_node) → Hil1ResumeAck(ok, run_id). 실패 시 status=failed.
FE proxy 는 next_node ?? null 가드라 무변경.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task C5-5 — env 점검 (CPIA_HIL_AUTO_BYPASS / CPIA_DEMO_FALLBACK 미설정 확인 — 코드 아님, 검증 체크리스트)

**Files:** (변경 없음 — 검증/문서)
- Verify `infra/docker-compose.yml` pipeline env(:67-79) + web env(:96-103)
- Verify 데모 런타임 컨테이너 실 환경

전건 HIL 이 실제로 interrupt 를 발생시키려면 `CPIA_HIL_AUTO_BYPASS` 미설정(graph.py:251), live row(is_mock=FALSE)가 review 에 뜨려면 `CPIA_DEMO_FALLBACK` 미설정/off(review route.ts:15,40) 여야 함. 둘 다 현재 compose/.env 에 없음 → 변경 불요, **회귀 방지용 assertion**.

- [ ] **(1) compose 정적 확인**:
```
grep -n "CPIA_HIL_AUTO_BYPASS\|CPIA_DEMO_FALLBACK" /Users/kyungseoplee/Project\ Agent/CPIA/infra/docker-compose.yml || echo "UNSET (OK)"
```
기대 출력: `UNSET (OK)` (두 변수 미정의).
- [ ] **(2) 런타임 컨테이너 실 환경 확인** (데모 compose 기동 중일 때):
```
docker exec cpia-pipeline printenv CPIA_HIL_AUTO_BYPASS || echo "pipeline: CPIA_HIL_AUTO_BYPASS UNSET (OK)"
docker exec cpia-web printenv CPIA_DEMO_FALLBACK || echo "web: CPIA_DEMO_FALLBACK UNSET (OK)"
```
기대: 둘 다 `UNSET (OK)` (printenv 가 미설정 변수에 비-0 종료).
- [ ] **(3) 데모 런타임 경로 명시** — compose web 은 `FASTAPI_URL: http://cpia-pipeline:8000`(:102), POSTGRES_URL 은 `cpia-postgres:5432`(:69,99) (compose 내부망). MEMORY 의 AWS PG 5532 는 외부 터널 경로. **데모 = compose 내부망(5432/8000)** — review/agent-tasks 가 보는 PG 와 pipeline 이 쓰는 PG 가 동일 `cpia-postgres` 인지 확인:
```
docker exec cpia-web printenv POSTGRES_URL
docker exec cpia-pipeline printenv POSTGRES_URL
```
기대: 둘 다 `...@cpia-postgres:5432/cpia` 동일 → review 가 pipeline 적재 row 를 봄.
- [ ] **(4) 결과 기록** (커밋 불요 — 검증 로그). 만약 어느 한 변수가 set 이면: bypass set → 전건 HIL 무효(interrupt 우회), DEMO_FALLBACK on → review 가 is_mock=TRUE 만 봐서 live 안 뜸. 둘 다 데모 실패 → unset 강제.

---

## 작업 순서 (cluster C5 내부)
C5-1 (mapper True) → C5-2 (재persist) → C5-4 (resume 백그라운드 + next_node 계약) → C5-3 (LIMIT) → C5-5 (env 검증) → e2e 7파일 풀 run 으로 통합 검증.

### Task C5-6 — /run `_bg` 실패 시 mapper 부분행 cleanup (확정결정 #10)

C3 Task 3 의 mapper 청크 INSERT 는 mapping 도중 실패 시 `mapper_activities` 에 부분행을 남긴다(spec §6.6 risk). run 단위 단일 chokepoint 인 `/run` 의 `_bg` 예외 핸들러에서 정리한다.

**Files:**
- Modify: `pipeline/api.py` (`/run` 의 `_bg` `except Exception` 블록, `set_run_status(..., 'failed')` **직전**; 현재 api.py:278-301 에 cleanup 없음)

- [ ] **실패 재현 테스트** `pipeline/tests/test_run_bg_cleanup.py` (신규): graph.ainvoke 를 monkeypatch 해 mapper row 일부 insert 후 raise → `_bg` 종료 뒤 `SELECT count(*) FROM mapper_activities WHERE run_id=$1` == 0 + `pipeline_runs.status`='failed' assert.
  - Run → 기대 **FAIL** (현재 DELETE 부재 → 부분행 잔존).
- [ ] **구현** — `api.py` `/run` `_bg` 의 `except Exception` 에서 `set_run_status(..., 'failed')` 직전에 standalone cleanup 추가(set_current_node 와 동일 패턴; `run_id` 는 _bg 스코프에 이미 있음, postgres_url 은 `body`/state 에서 — 정확 변수명은 _bg 스코프 확인 후):
```python
        try:
            _c = await asyncpg.connect(postgres_url)
            try:
                await _c.execute("DELETE FROM mapper_activities WHERE run_id=$1", run_id)
            finally:
                await _c.close()
        except Exception:
            pass
```
- [ ] **Run → 기대 PASS** (`2 passed` 또는 해당 케이스) → **commit**.

---

## 통합 e2e 검증 (Tasks 전체 후, spec §5.2 / §7)
1. 7파일 업로드 → POST /run → mapper 후 `status='waiting_hil_1'`.
2. review 화면: cards 수 == mapper_activities (requires_review=TRUE, <=500).
3. "승인 확정" → /api/hil/resume → 즉시 200(백그라운드) → atomizer 이후 완주.
4. resume 후 `SELECT count(*) FROM mapper_activities WHERE run_id=$ AND requires_review=TRUE` = 0.
5. 미승인 시 후속 0 진행(게이트 동작).


## Cluster C6 — B2.5 wp_summary 날짜 데이터-only 보정 (Spec §5.5)

> **목표:** `view_builder.py:1988-1989` 의 placeholder `start_date=str(today.replace(day=1))` / `end_date=str(today)` 를 온고잉 plan 의 실 기간(`it["plan_start"]`/`it["plan_finish"]`)으로 교체. 쿼리/BETWEEN 변경 없음(폐기됨). 데이터-only, markup 불변.
>
> **★ 전수조사로 발견한 spec 의 부정확점 (반드시 먼저 해결):**
> spec §5.5 / 본 클러스터 지시는 "행에 이미 있는 `it["plan_start"]/it["plan_finish"]`(`:1700`)" 라고 적혀 있으나, `:1700` 은 SQL row `r` 의 컬럼이고 wp_summary 가 순회하는 것은 `grouped_items`(`:2029`)의 `it` 이다. 실제 코드를 보면 `items.append(...)`(`view_builder.py:1760-1783`)가 `r["plan_start"]/r["plan_finish"]` 를 **items 에 담지 않는다**(`:1735` 의 `total_days` 계산에만 쓰고 버림). `grouped_items` 는 `**head`(=`grp[0]`, items 파생)로 스프레드(`:1923`)되므로 `it["plan_start"]` 는 **KeyError 를 던진다**. 따라서 Task 1 에서 `items.append` 에 `plan_start`/`plan_finish` 를 먼저 전파한 뒤 Task 2 에서 wp_summary 가 그것을 읽도록 한다. (이 두 변경을 한 Task 로 묶어도 되나, 실패 테스트가 KeyError → 정상값 두 단계를 명확히 잡도록 단일 Task 로 진행.)

---

### Task 1 — wp_summary start_date/end_date 를 실 plan 기간으로 (None 가드 포함)

**Files:**
- Modify `pipeline/agents/optimizer/view_builder.py:1760-1783` (items.append 에 plan_start/plan_finish 전파)
- Modify `pipeline/agents/optimizer/view_builder.py:1988-1989` (placeholder → 실 plan 기간)
- Test (단위 helper) `pipeline/tests/optimizer/test_wp_summary_dates.py` (신규)
- Verify (실 PG 통합) `pipeline/scripts/_rebuild_views.py` 1회 run + 단발 assert 스크립트

**근거 (실 코드 인용):**
- `view_builder.py:1626-1630` — `async def _build_productivity_views_v2(pg, site_id, today: date) -> dict`
- `view_builder.py:1700` — fallback SQL: `p.ps AS plan_start, p.pf AS plan_finish` (SQL row `r` 에만 존재)
- `view_builder.py:1646` — primary SQL: `m.ps AS plan_start, m.pf AS plan_finish`
- `view_builder.py:1735` — `total_days = (r["plan_finish"] - r["plan_start"]).days + 1` (r 에서 읽음, items 로 안 넘어감)
- `view_builder.py:1760-1783` — `items.append({...})` 에 plan_start/plan_finish **없음** ← 전파 추가 지점
- `view_builder.py:1922-1939` — `grouped_items.append({**head, ...})`, `head = grp[0]`(`:1888`) → items 의 키만 상속
- `view_builder.py:1988-1989` — `"start_date": str(today.replace(day=1)),  # placeholder` / `"end_date": str(today),` ← 교체 지점
- `view_builder.py:2029` — wp_summary 가 `for it in grouped_items` 순회

#### 단위 helper 추출 (테스트 가능하게)

- [ ] **1.1 — 실패 단위 테스트 작성.** 신규 파일 `pipeline/tests/optimizer/test_wp_summary_dates.py`:

```python
"""B2.5 (Cluster C6): wp_summary start_date/end_date = 실 plan 기간 (placeholder 아님).

순수 helper _wp_summary_dates 단위 검증 — plan_start/plan_finish None 가드 포함.
실 PG 통합 검증은 scripts/_rebuild_views.py 경로 (plan_markdown verification 참조).
"""

from __future__ import annotations

from datetime import date

from pipeline.agents.optimizer.view_builder import _wp_summary_dates


def test_wp_summary_dates_uses_real_plan_period():
    """plan_start/plan_finish 있으면 그 값을 str 로 반환 (당월1일/오늘 아님)."""
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates(
        {"plan_start": date(2025, 9, 1), "plan_finish": date(2025, 10, 31)}, today
    )
    assert start == "2025-09-01"
    assert end == "2025-10-31"
    # placeholder 였다면 당월1일(2025-09-01) 우연 일치할 수 있으나 end 가 결정적 차이
    assert end != str(today)


def test_wp_summary_dates_none_falls_back_to_today():
    """plan_start/plan_finish None 이면 today 로 fallback (KeyError/None str 방지)."""
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates({"plan_start": None, "plan_finish": None}, today)
    assert start == "2025-09-25"
    assert end == "2025-09-25"


def test_wp_summary_dates_missing_key_falls_back():
    """키 자체가 없어도 today fallback (구 grouped_items 호환)."""
    today = date(2025, 9, 25)
    start, end = _wp_summary_dates({}, today)
    assert start == "2025-09-25"
    assert end == "2025-09-25"
```

- [ ] **1.2 — 실패 확인.** 실행:

```bash
PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" \
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -m pytest \
  "/Users/kyungseoplee/Project Agent/CPIA/pipeline/tests/optimizer/test_wp_summary_dates.py" -q
```

기대 출력 (helper 미존재 → import 실패):
```
ImportError: cannot import name '_wp_summary_dates' from 'pipeline.agents.optimizer.view_builder'
...
3 errors in ...
```

- [ ] **1.3 — helper 구현 (정확 코드).** `pipeline/agents/optimizer/view_builder.py` 에서 `_build_productivity_views_v2`(`:1626`) **위**, 다른 모듈-레벨 helper 옆(예: `_make_display_label` 근처)에 추가. 기존 스타일(한글 docstring, 모듈 함수) 매칭:

```python
def _wp_summary_dates(it: dict, today: date) -> tuple[str, str]:
    """wp_summary 시작/종료일 = 온고잉 plan 의 실 기간 (placeholder 폐기).

    2026-06-02 B2.5(C6): 이전엔 당월1일/오늘 placeholder 라 진단 inconsistent.
    grouped_items 의 plan_start/plan_finish (활동마스터 plan) 사용. 둘 중
    하나라도 None/누락이면 today 로 fallback (디자인 불가침 — 데이터-only).
    """
    ps = it.get("plan_start") or today
    pf = it.get("plan_finish") or today
    return str(ps), str(pf)
```

- [ ] **1.4 — items 로 plan_start/plan_finish 전파.** `view_builder.py:1760-1783` 의 `items.append({...})` dict 에 **두 키 추가**. 현재 마지막 두 줄:

```python
                "productivity": productivity,
                "impact_raw": impact_raw,
            }
        )
```

을 다음으로 교체:

```python
                "productivity": productivity,
                "impact_raw": impact_raw,
                # 2026-06-02 B2.5(C6): wp_summary 실 plan 기간 노출용 (grouped_items
                # **head 로 상속 → _wp_summary_dates 가 소비). primary/fallback 둘 다 r 에 존재.
                "plan_start": r["plan_start"],
                "plan_finish": r["plan_finish"],
            }
        )
```

> 주: `grouped_items.append({**head, ...})`(`:1922-1939`)는 plan_start/plan_finish 키를 **override 하지 않으므로** head(=그룹 첫 row)의 값이 그대로 상속된다. fallback plan CTE 가 `(company,l6_main,unit)` 그룹의 `MIN(plan_start)/MAX(plan_finish)`(`:1690`)라 같은 (company,l6) 그룹 내 row 들은 동일 plan_start 를 공유 → head 대표값으로 충분.

- [ ] **1.5 — wp_summary placeholder 교체.** `view_builder.py:1988-1989`:

```python
                "start_date": str(today.replace(day=1)),  # placeholder
                "end_date": str(today),
```

을 다음으로 교체:

```python
                # 2026-06-02 B2.5(C6): 당월1일/오늘 placeholder → 온고잉 plan 실 기간.
                "start_date": _wp_summary_dates(it, today)[0],
                "end_date": _wp_summary_dates(it, today)[1],
```

> `progress_pct`(`:1990-1992`, 단일일 `today_qty/plan_total`)는 **변경 안 함** — spec §5.5 / Q3 가 날짜만 보정 명시. (ambiguity 로 별도 flag.)

- [ ] **1.6 — 단위 PASS 확인.** 1.2 와 동일 명령 재실행. 기대 출력:

```
test_wp_summary_dates.py::test_wp_summary_dates_uses_real_plan_period PASSED
test_wp_summary_dates.py::test_wp_summary_dates_none_falls_back_to_today PASSED
test_wp_summary_dates.py::test_wp_summary_dates_missing_key_falls_back PASSED
3 passed in ...
```

- [ ] **1.7 — 회귀: 기존 view_builder helper 테스트 통과 확인.** (시그니처 변경 없음 회귀 가드)

```bash
PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" \
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -m pytest \
  "/Users/kyungseoplee/Project Agent/CPIA/pipeline/tests/optimizer/test_view_builder_v2.py" \
  -q -m "not integration"
```
기대: `passed` (integration 마커 제외한 helper 테스트 전부 green, 새 import 깨짐 없음).

#### 실 PG 통합 검증 (단위 테스트로 불가능한 부분 — 결정론적 pass/fail loop)

> 단위 테스트는 helper 의 None 가드만 증명한다. "wp_summary[].start_date == activity_master plan_start for that (company,l6)" 는 실 DB row 가 필요하므로 `_rebuild_views.py` 경로로 검증한다. **LLM bypass — 결정론적**(같은 run/site/date 입력 → 같은 wp_summary).

- [ ] **1.8 — 09-25 실 run_id 확보 + rebuild.** (사전: AWS PG 5532 터널 up, `.env` POSTGRES_URL 설정.)

```bash
PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" \
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -c "
import asyncio, os
from pathlib import Path
ROOT=Path('/Users/kyungseoplee/Project Agent/CPIA')
for l in (ROOT/'.env').read_text().splitlines():
    if '=' in l and not l.strip().startswith('#'):
        k,v=l.split('=',1); os.environ.setdefault(k.strip(), v.strip())
from pipeline.db import PGClient
async def m():
    pg=PGClient(os.environ['POSTGRES_URL']); await pg.connect()
    r=await pg.fetch_all(\"SELECT run_id FROM pipeline_runs WHERE site_id='m15x-ph3-ibl' AND report_date='2025-09-25' ORDER BY created_at DESC LIMIT 1\")
    print(r[0]['run_id'] if r else 'NO_RUN'); await pg.close()
asyncio.run(m())
"
```
기대: 1개 UUID 출력(또는 e2e 후 생성된 run). `NO_RUN` 이면 cluster e2e(7파일 업로드 run) 선행 필요 → ambiguity 참조.

- [ ] **1.9 — rebuild + 직접 assert.** `<RUN_ID>` 를 1.8 출력로 치환:

```bash
PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" \
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" \
  "/Users/kyungseoplee/Project Agent/CPIA/pipeline/scripts/_rebuild_views.py" \
  <RUN_ID> 2025-09-25 m15x-ph3-ibl
```
기대: `wp_summary N건:` 섹션 출력(N>=1).

이어서 결정론 assert (start_date 가 당월1일 placeholder 가 **아니고** activity_master plan_start 와 일치):

```bash
PYTHONPATH="/Users/kyungseoplee/Project Agent/CPIA" \
"/Users/kyungseoplee/Project Agent/CPIA/pipeline/.venv/bin/python" -c "
import asyncio, os
from datetime import date
from pathlib import Path
ROOT=Path('/Users/kyungseoplee/Project Agent/CPIA')
for l in (ROOT/'.env').read_text().splitlines():
    if '=' in l and not l.strip().startswith('#'):
        k,v=l.split('=',1); os.environ.setdefault(k.strip(), v.strip())
from pipeline.db import PGClient
from pipeline.agents.optimizer.view_builder import _build_productivity_views_v2
async def m():
    pg=PGClient(os.environ['POSTGRES_URL']); await pg.connect()
    v=await _build_productivity_views_v2(pg, 'm15x-ph3-ibl', date(2025,9,25))
    ws=v['wp_summary']; assert ws, 'wp_summary empty'
    bad=[w for w in ws if w['start_date']=='2025-09-01' and w['end_date']=='2025-09-25']
    # 당월1일~오늘 placeholder 가 전부면 미반영
    assert not (len(bad)==len(ws)), f'placeholder 그대로: {bad[:2]}'
    # 각 wp 의 start_date == 그 (company,l6) activity_master MIN(plan_start)
    miss=[]
    for w in ws:
        r=await pg.fetch_all('SELECT MIN(plan_start)::text ps, MAX(plan_finish)::text pf FROM activity_master WHERE site_id=\$1 AND company=\$2 AND l6_main=\$3', 'm15x-ph3-ibl', w['bp_name'], w['trade'])
        ps=r[0]['ps']; pf=r[0]['pf']
        if ps is not None and (w['start_date']!=ps or w['end_date']!=pf):
            miss.append((w['bp_name'], w['trade'], w['start_date'], ps, w['end_date'], pf))
    assert not miss, f'plan 기간 불일치: {miss[:3]}'
    print(f'OK wp_summary {len(ws)}건 start/end == activity_master plan 기간')
    await pg.close()
asyncio.run(m())
"
```
기대 출력 (원본 그대로 보고):
```
OK wp_summary N건 start/end == activity_master plan 기간
```
- AssertionError `placeholder 그대로` → 코드 미반영 (Task 1.4/1.5 누락).
- AssertionError `plan 기간 불일치` → head 대표값과 (company,l6) MIN/MAX 가 unit 분할로 어긋남 → ambiguity(아래) 참조.

- [ ] **1.10 — commit.**

```bash
git -C "/Users/kyungseoplee/Project Agent/CPIA" add \
  pipeline/agents/optimizer/view_builder.py \
  pipeline/tests/optimizer/test_wp_summary_dates.py
git -C "/Users/kyungseoplee/Project Agent/CPIA" commit -m "$(cat <<'EOF'
B2.5(C6): wp_summary start/end_date = 온고잉 plan 실 기간 (placeholder 폐기)

view_builder _build_productivity_views_v2 가 wp_summary 의 start_date/end_date 를
당월1일/오늘 placeholder 대신 활동마스터 plan_start/plan_finish 로 노출.
items.append 에 plan_start/plan_finish 전파(grouped_items **head 상속) +
_wp_summary_dates helper(None/누락 시 today fallback). 쿼리/BETWEEN 무변경,
데이터-only(디자인 불가침). progress_pct 단일일 산식 유지.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

> **현재 브랜치 = `main`** (git rev-parse 확인). CLAUDE.md/MEMORY: "본인 명시 지시 시 PR 없이 직접 머지 OK"(선례 d317be9). 그래도 신규 작업은 브랜치 우선 권장 — 사용자 지시 따름. (커밋 단계에서 사용자에게 main 직접 커밋 vs A_Track 확인.)
