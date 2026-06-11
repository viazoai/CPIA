# Export 시트2·3 헤더 복원 + 유령열 제거 + 전 날짜 re-bake — 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 통합작업일보 xlsx 시트2·3의 r5 서브헤더(조출/주간/.../누계)를 복원하고 빈 테두리 유령열(Y/25)을 제거하며, 캐시된 전 날짜를 수정 코드로 re-bake 해 스키마를 통일한다.

**Architecture:** 익스포터(`exporter.py`)는 시트별 데이터 시작행(시트1·4=r5, 시트2·3=r6)을 갖고, render 시 시트2·3 r5에 서브헤더를 코드로 작성하며 테두리 우측 경계를 col24로 줄인다. 이미 PoC로 워킹트리에 구현·검증·사용자 승인 완료. 출력은 `consolidated_reports`(homelab PG)에 캐시되어 UI가 그대로 반환하므로, 코드 수정 후 별도 re-bake 스크립트로 전 캐시 날짜를 재생성(is_mock 보존)한다.

**Tech Stack:** Python 3.11 (`pipeline/.venv`), openpyxl 3.1.5, asyncpg, pytest. PG: homelab `consolidated_reports` (POSTGRES_URL in `web/.env.local`). site_id=`m15x-ph3-ibl`.

**Spec:** `docs/superpowers/specs/2026-06-11-cpia-export-sheet23-header-fix-design.md`

---

## ⚠️ 실행자 필독 — 현재 상태

`pipeline/agents/exporter.py` 에는 **이미 승인된 PoC 수정이 워킹트리에 미커밋 상태로 존재**한다. 다시 작성하지 말 것. 변경 내용:
- `_GROUP_SHEETS`: 시트2·3 `c1` 25→**24**.
- `_DATA_START={"2.직종별 인원현황":6,"3.장비현황":6}` + `_data_start(title)` 헬퍼.
- `_unhide_and_clean(ws,n,start)` / `_dedup_and_border(ws,n,c0,c1,key_cols,start)` 시작행 파라미터화.
- `_unmerge_data_region` 시트별 `_data_start(title)` 사용.
- `_fill_occupation(...,*,start)` / `_fill_equipment(...,*,start)` 시작행.
- 신규 `_write_subheaders(wb)` (시트2·3 r5 서브헤더, 최종/Y 미작성) + `render_xlsx` 가 호출.

작업 시작 전 `git diff --stat pipeline/agents/exporter.py` 로 변경 존재를 확인하고, 코드를 읽어 위 항목과 일치하는지만 검증한다. Task 1·2 의 테스트는 이 구현이 spec 을 만족함을 고정·증명하는 acceptance·regression 테스트다.

**병행 세션 주의(공유 워킹트리):** `git add` 는 이 플랜이 명시한 파일만. 미추적 `data/`·`parser_recipes/`·`data/upload/`·`data/demo_inputs/`·`web/public/poc_*.xlsx` 등 절대 건드리지 말 것. `git checkout main` 등 브랜치 전환 금지.

**시트2·3 r5 컬럼 맵 (1-indexed):** B2=Dis, C3=협력업체, D4·E5·F6=좌측라벨(시트별), G7=조출 H8=주간 I9=연장 J10=야간 K11=철야 L12=`Cum. T` · M13~R18(R18=`Incr. T`) · S19~X24(X24=`Cum. T`). **Y25(최종)=미작성.**

---

## Task 1: 익스포터 변경을 테스트로 고정 + 커밋

**Files:**
- Verify (수정 금지, 읽기만): `pipeline/agents/exporter.py`
- Modify: `pipeline/tests/test_exporter_format.py`

- [ ] **Step 1: 워킹트리 PoC 상태 확인**

Run: `cd "/Users/kyungseoplee/Project Agent/CPIA" && git diff --stat pipeline/agents/exporter.py`
Expected: `exporter.py` 가 변경됨(+50줄 내외). 변경 없으면 STOP 하고 보고(PoC 유실 — 컨트롤러에게 escalate).

- [ ] **Step 2: 기존 stale 테스트 갱신 (freeze A5→A6)**

`pipeline/tests/test_exporter_format.py` 의 `test_finalize_sheet2_no_hidden_no_filter_white` 에서:
```python
    assert ws2.freeze_panes == "A5"
```
를 아래로 교체(시트2 헤더 3행 → freeze A6):
```python
    assert ws2.freeze_panes == "A6"  # 시트2 헤더 3행(r3+r4+r5 서브헤더) → 데이터 r6
```

- [ ] **Step 3: 갱신 테스트가 통과하는지 확인**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_format.py::test_finalize_sheet2_no_hidden_no_filter_white -q`
Expected: PASS (PoC 구현이 freeze A6 를 만듦).

- [ ] **Step 4: 신규 acceptance 테스트 추가**

`pipeline/tests/test_exporter_format.py` 끝에 추가. `_sd_two_occ_eq()` 헬퍼는 시트2·3에 데이터를 채워 r6 시작·유령열을 검증할 수 있게 한다.
```python
# ── 2026-06-11 시트2·3 r5 서브헤더 복원 + 유령열(Y/25) 제거 ──
def _sd_two_occ_eq():
    """시트2·3 데이터 2행씩 — r6 시작·서브헤더·유령열 검증용."""
    sd = _sd_one_company()
    sd.occupation_manpower = [
        {"disc_abbrev": "건축", "company": "광건", "job_type": "비계공", "workers_cum_t": 3},
        {"disc_abbrev": "건축", "company": "광건", "job_type": "형틀목공", "workers_cum_t": 5},
    ]
    sd.equipment = [
        {"disc_abbrev": "건축", "company": "광건", "equipment_big": "굴삭운반기계류",
         "equipment_mid": "Back Hoe", "equipment_spec": "2㎥ 미만", "count_cum_t": 1},
    ]
    return sd


def _rendered_two():
    return load_workbook(BytesIO(render_xlsx(_sd_two_occ_eq(), date(2025, 9, 25), project="M15X Ph-3 IBL")))


def test_sheet23_r5_subheader_restored():
    """시트2·3 r5 = 좌측라벨 + 조출/주간/연장/야간/철야/누계(×3). 최종(Y/25) 없음."""
    wb = _rendered_two()
    ws2 = wb["2.직종별 인원현황"]
    assert ws2.cell(5, 2).value == "Dis"
    assert ws2.cell(5, 3).value == "협력업체"
    assert ws2.cell(5, 8).value == "주간"      # H5
    assert ws2.cell(5, 10).value == "야간"     # J5
    assert ws2.cell(5, 12).value == "Cum. T"   # L5 전일누계 합
    assert ws2.cell(5, 18).value == "Incr. T"  # R5 금일투입 합
    assert ws2.cell(5, 24).value == "Cum. T"   # X5 금일누계 합
    assert ws2.cell(5, 25).value is None        # Y5 최종 = 미작성
    ws3 = wb["3.장비현황"]
    assert ws3.cell(5, 4).value == "대분류"     # 시트3 좌측 라벨 차이
    assert ws3.cell(5, 8).value == "주간"


def test_sheet23_data_starts_row6():
    """시트2·3 데이터는 r6 부터 (r5 는 서브헤더)."""
    wb = _rendered_two()
    ws2 = wb["2.직종별 인원현황"]
    assert ws2.cell(6, 2).value == "건축"       # 첫 데이터 행 = 공종(disc_abbrev)
    assert ws2.cell(6, 3).value == "광건"
    ws3 = wb["3.장비현황"]
    assert ws3.cell(6, 4).value == "굴삭운반기계류"  # 첫 데이터 = 대분류


def test_sheet23_no_ghost_column_25():
    """유령열 제거: 시트2·3 Y열(25) 데이터행에 값·테두리 모두 없음."""
    from openpyxl.cell.cell import MergedCell
    wb = _rendered_two()
    for sname, ndata in (("2.직종별 인원현황", 2), ("3.장비현황", 1)):
        ws = wb[sname]
        for i in range(ndata):
            cell = ws.cell(6 + i, 25)
            assert cell.value is None
            if not isinstance(cell, MergedCell):
                b = cell.border
                assert not any(s and s.style for s in (b.left, b.right, b.top, b.bottom)), \
                    f"{sname} Y{6+i} 에 테두리 잔존(유령열)"


def test_sheet14_data_still_row5_no_regression():
    """시트1·4 는 종전대로 r5 시작 (회귀 방지)."""
    from pipeline.agents.exporter import COL_OUTPUT_MANPOWER, COL_QUANTITY
    wb = _rendered_two()
    assert wb["1.작업사항"].cell(5, COL_OUTPUT_MANPOWER["project"]).value == "M15X Ph-3 IBL"
    assert wb["4.물량"].cell(5, COL_QUANTITY["project"]).value == "M15X Ph-3 IBL"
```

- [ ] **Step 5: 신규 테스트 실행 — 통과 확인**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_format.py -q`
Expected: 모두 PASS (구현 존재). 실패 시 exporter.py 구현과 컬럼 맵을 재대조(추측 금지 — 실제 셀 덤프로 확인).

- [ ] **Step 6: 전체 exporter 테스트 스위트 회귀 확인**

Run: `pipeline/.venv/bin/python -m pytest pipeline/tests/test_exporter_render.py pipeline/tests/test_exporter_format.py pipeline/tests/test_exporter_merged_cell.py pipeline/tests/test_exporter_wa_source.py pipeline/tests/test_exporter_node.py -q`
Expected: all PASS, 0 failed. (PG 필요한 `test_exporter_endpoint.py`·`test_exporter_progress.py` 는 Task 3 에서.)

- [ ] **Step 7: 커밋 (exporter.py + 테스트)**

```bash
git add pipeline/agents/exporter.py pipeline/tests/test_exporter_format.py
git commit -m "fix(export): 시트2·3 r5 서브헤더 복원 + 유령열(Y) 제거 + 시트별 데이터 시작행

원본 통합작업일보 시트2·3은 헤더 3행(r3+r4+r5 서브헤더)인데 템플릿이 r5 서브헤더를 누락
+ 전역 DATA_START_ROW=5 라 데이터가 서브헤더 자리를 덮음. 시트별 시작행(2·3=r6) 도입,
_write_subheaders 로 조출/주간/연장/야간/철야/누계(×3) r5 작성(최종/Y 제외), dedup 테두리
우측 c1=24 로 빈 테두리 유령열 제거. 시트1·4 는 r5 유지(무회귀).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: re-bake 스크립트 작성 + 전 날짜 재생성 + 검증

**Files:**
- Create: `scripts/rebake_consolidated_reports.py`

`consolidated_reports` 의 모든 (site_id, report_date) 를 수정된 `render_xlsx` 로 재생성하고 UPSERT 한다. **핵심 제약: `upsert_consolidated_report` 는 INSERT 시 `is_mock` 을 FALSE 로 넣으므로, 재생성 전에 기존 `is_mock` 을 읽어 두고 UPSERT 후 그 값으로 `UPDATE` 복원한다.** 결정론(LLM 없음)이라 idempotent.

- [ ] **Step 1: 스크립트 작성**

```python
"""consolidated_reports 전 캐시 날짜를 현재 exporter 로 재생성 (스키마 통일).

upsert_consolidated_report 는 INSERT 시 is_mock=FALSE 기본 → 재생성 전 기존 is_mock 을
읽어 두고 UPSERT 후 복원한다. 결정론(LLM 없음) → idempotent, 재실행 안전.

  python scripts/rebake_consolidated_reports.py --dry-run        # 렌더만(쓰기 X)
  python scripts/rebake_consolidated_reports.py                  # 전체 재생성
  python scripts/rebake_consolidated_reports.py --site m15x-ph3-ibl --start 2025-09-24 --end 2025-09-25
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx  # noqa: E402
from pipeline.db import PGClient, fetch_site_by_id, upsert_consolidated_report  # noqa: E402

log = logging.getLogger("rebake")


async def _targets(pg, site, start, end):
    # run_id 필수(NOT NULL UUID FK) → 기존 행 run_id 를 그대로 재사용해 UPSERT.
    q = "SELECT site_id, report_date, is_mock, run_id FROM consolidated_reports WHERE TRUE"
    args = []
    if site:
        args.append(site); q += f" AND site_id = ${len(args)}"
    if start:
        args.append(start); q += f" AND report_date >= ${len(args)}"
    if end:
        args.append(end); q += f" AND report_date <= ${len(args)}"
    q += " ORDER BY site_id, report_date"
    async with pg._pool.acquire() as con:
        return await con.fetch(q, *args)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site"); ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url = os.environ["POSTGRES_URL"]
    start = date.fromisoformat(a.start) if a.start else None
    end = date.fromisoformat(a.end) if a.end else None

    pg = PGClient(url); await pg.connect()
    rows = await _targets(pg, a.site, start, end)
    log.info("대상 %d건 (dry_run=%s)", len(rows), a.dry_run)
    ok = skip = err = 0
    proj_cache = {}
    for r in rows:
        sid, d, was_mock, rid = r["site_id"], r["report_date"], r["is_mock"], r["run_id"]
        try:
            data = await fetch_sheet_data(pg, sid, d)
        except NoDataError:
            skip += 1; log.info("skip(NoData) %s %s", sid, d); continue
        if sid not in proj_cache:
            site = await fetch_site_by_id(pg, sid)
            proj_cache[sid] = (site or {}).get("name") or "CPIA"
        try:
            b = render_xlsx(data, d, project=proj_cache[sid])
        except Exception:
            err += 1; log.exception("render 실패 %s %s", sid, d); continue
        if a.dry_run:
            ok += 1; log.info("[dry] %s %s -> %d bytes (is_mock=%s 유지예정)", sid, d, len(b), was_mock); continue
        # run_id 는 기존 행 값 그대로 재사용(NOT NULL UUID FK).
        await upsert_consolidated_report(pg, site_id=sid, report_date=d, xlsx_bytes=b, run_id=rid)
        # is_mock 복원 (upsert 가 INSERT 시 FALSE 로 넣을 수 있음)
        async with pg._pool.acquire() as con:
            await con.execute(
                "UPDATE consolidated_reports SET is_mock=$3 WHERE site_id=$1 AND report_date=$2",
                sid, d, was_mock,
            )
        ok += 1; log.info("rebake %s %s -> %d bytes (is_mock=%s)", sid, d, len(b), was_mock)
    await pg.close()
    log.info("완료: ok=%d skip=%d err=%d / 대상=%d", ok, skip, err, len(rows))
    if err:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

> **확정 사실 (db.py:1256 + migration `2026-05-27_consolidated_reports.sql` 검증됨):**
> - `consolidated_reports.run_id` 은 `UUID NOT NULL REFERENCES pipeline_runs`. → `run_id=None` UPSERT 는 **제약 위반으로 반드시 실패**. 위 스크립트처럼 기존 행 run_id 를 SELECT(`_targets`)해 그대로 전달해야 한다.
> - `upsert_consolidated_report` 에는 **`is_mock` 파라미터가 없다**(INSERT 시 기본 FALSE). → is_mock 보존은 UPSERT 후 별도 `UPDATE` 가 유일한 방법(위 스크립트대로). "is_mock 파라미터로 단순화" 경로는 존재하지 않음.
> - `byte_size` 는 `GENERATED ALWAYS AS (length(xlsx_bytes)) STORED` → UPSERT 시 자동 갱신.
> - 참고: spec §3.3 이 언급한 `seed_dummy_year._backfill_consolidated_reports` 는 이 플랜 범위 밖(이 스크립트는 독립). 그걸 찾거나 고치지 말 것.

- [ ] **Step 2: db.py 시그니처 최종 확인 (인자명 정합)**

Run: `sed -n '1256,1300p' pipeline/db.py` (또는 Read). `upsert_consolidated_report` 의 kwarg 명(`site_id`/`report_date`/`xlsx_bytes`/`run_id`)이 위 스크립트 호출과 일치하는지 확인. 불일치 시 스크립트 호출부만 맞춘다(위 확정 사실은 변경 금지).

- [ ] **Step 3: dry-run — 전 날짜 렌더 무에러 확인**

Run:
```bash
set -a; . web/.env.local; set +a            # POSTGRES_URL 등 환경 적재
echo "PG host: ${POSTGRES_URL##*@}"          # 파싱 확인(1회)
pipeline/.venv/bin/python scripts/rebake_consolidated_reports.py --dry-run
```
Expected: `대상 N건`, 각 날짜 `[dry] ... bytes`, `완료: ok=N skip=? err=0`. err>0 이면 STOP·조사.

- [ ] **Step 4: 실 재생성 (전 날짜)**

Run (앞서 `set -a; . web/.env.local; set +a` 로 env 적재된 셸에서):
```bash
pipeline/.venv/bin/python scripts/rebake_consolidated_reports.py
```
Expected: `완료: ok=N skip=? err=0`. (N = dry-run 과 동일, 누락 0.) 첫 행에서 run_id NOT NULL 위반이 나면 STOP — `_targets` 가 run_id 를 SELECT/전달하는지 재확인.

- [ ] **Step 5: is_mock 보존 + 누락 0 검증**

Run (POSTGRES_URL export 후):
```bash
pipeline/.venv/bin/python - "$POSTGRES_URL" <<'PY'
import sys, asyncio, asyncpg
async def main():
    con=await asyncpg.connect(sys.argv[1])
    r=await con.fetch("""SELECT report_date,is_mock,byte_size FROM consolidated_reports
                         WHERE site_id='m15x-ph3-ibl' AND report_date>='2025-09-23' ORDER BY report_date DESC""")
    for x in r: print(x['report_date'],'is_mock=',x['is_mock'],'bytes=',x['byte_size'])
    await con.close()
asyncio.run(main())
PY
```
Expected: 9/25 `is_mock=False`, 9/24·9/23 `is_mock=True` (보존됨). byte_size 갱신됨.

- [ ] **Step 6: 9/25·9/24 캐시 재추출 → 구조 검증 (실 출력 인용)**

Run (POSTGRES_URL export 후):
```bash
pipeline/.venv/bin/python - "$POSTGRES_URL" <<'PY'
import sys, asyncio, asyncpg
from datetime import date
from openpyxl import load_workbook
from io import BytesIO
async def main():
    con=await asyncpg.connect(sys.argv[1])
    for d in (date(2025,9,25), date(2025,9,24)):
        row=await con.fetchrow("SELECT xlsx_bytes FROM consolidated_reports WHERE site_id='m15x-ph3-ibl' AND report_date=$1", d)
        wb=load_workbook(BytesIO(row['xlsx_bytes']))
        ws=wb['2.직종별 인원현황']
        print(d, '시트명:', wb.sheetnames[0], '| r5 H/J/L:', ws.cell(5,8).value, ws.cell(5,10).value, ws.cell(5,12).value,
              '| Y5:', ws.cell(5,25).value)
    await con.close()
asyncio.run(main())
PY
```
Expected: 두 날짜 모두 시트명='1.작업사항', r5 = `주간 야간 Cum. T`, Y5=None.

- [ ] **Step 7: 커밋 (스크립트)**

```bash
git add scripts/rebake_consolidated_reports.py
git commit -m "feat(scripts): consolidated_reports 전 날짜 re-bake (is_mock 보존)

캐시된 통합작업일보를 수정 exporter 로 재생성해 스키마 통일(시트2·3 헤더·유령열).
upsert 후 기존 is_mock 복원, 결정론 idempotent. dry-run/site/날짜 필터 지원.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 라이브 엔드포인트 e2e 검증 + FastAPI 갱신

**Files:** (코드 변경 없음 — 검증 전용)

- [ ] **Step 1: FastAPI 재기동 (신규 업로드 fresh-render 가 새 코드 쓰도록)**

현 uvicorn pid 확인: `ps aux | grep '[u]vicorn pipeline.api' `. 자격증명은 기동 셸 env 에만 있으므로 `ps eww -p <pid>` 로 추출해 temp env 작성 후 재기동:
```bash
PID=$(pgrep -f 'uvicorn pipeline.api'); ps eww -p $PID | tr ' ' '\n' | grep -E '^(POSTGRES_URL|CHROMA_HOST|CHROMA_PORT|AZURE_OPENAI_|EMBEDDING_MODEL|LLM_MODEL)' > /tmp/cpia_fa.env
kill $PID; sleep 1
( set -a; . /tmp/cpia_fa.env; set +a; cd "/Users/kyungseoplee/Project Agent/CPIA"; nohup pipeline/.venv/bin/uvicorn pipeline.api:app --port 8000 >/tmp/cpia_fa.log 2>&1 & )
sleep 4; curl -s -m3 localhost:8000/docs -o /dev/null -w "FastAPI HTTP %{http_code}\n"; rm -f /tmp/cpia_fa.env
```
Expected: `FastAPI HTTP 200`. (캐시는 Task 2 에서 이미 정상화 — 이 단계는 향후 신규 업로드 대비.)

- [ ] **Step 2: 엔드포인트로 9/25·9/24 다운로드 → 구조 검증**

```bash
for D in 2025-09-25 2025-09-24; do
  curl -s "localhost:8000/export/run?site_id=m15x-ph3-ibl&date=$D" -o /tmp/ep_$D.xlsx
  echo "$D $(wc -c < /tmp/ep_$D.xlsx) bytes"
done
pipeline/.venv/bin/python - <<'PY'
from openpyxl import load_workbook
for d in ('2025-09-25','2025-09-24'):
    wb=load_workbook(f'/tmp/ep_{d}.xlsx'); ws=wb['2.직종별 인원현황']
    print(d, wb.sheetnames[0], '| r5:', ws.cell(5,8).value, ws.cell(5,12).value, '| Y5:', ws.cell(5,25).value)
PY
```
Expected: 두 날짜 시트명='1.작업사항', r5=`주간 ... Cum. T`, Y5=None. (= Task 2 재추출과 동일 = 캐시 정상 + 프록시 정상.)

- [ ] **Step 3: 최종 보고**

진단 3건(P1·P2·P3) 해소, 단위 테스트 green, 전 날짜 re-bake 완료(is_mock 보존), 라이브 다운로드 검증을 실 명령·실 출력으로 보고. PoC 산출물(`~/Downloads/PoC_*.xlsx`) 정리(삭제) 여부 사용자 확인.

---

## 완료 게이트 (Done 정의 — 3요소 모두)
1. `pytest` exporter 스위트 green (실 출력 인용).
2. re-bake 후 PG 재추출 + 엔드포인트 다운로드에서 시트2·3 r5 서브헤더 + Y5 공백 + 시트1='1.작업사항' (실 openpyxl 덤프 인용).
3. 전 캐시 날짜 재생성 누락 0 + is_mock 보존 확인.
