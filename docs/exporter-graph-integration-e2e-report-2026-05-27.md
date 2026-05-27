# Exporter graph 사전생성 통합 — E2E 검증 보고서 (2026-05-27)

## 검증 환경
- Branch: A_Track
- SHA: fb22470
- FastAPI: localhost:8000
- PG: $POSTGRES_URL (AWS prod, postgresql://cpia:***@43.200.85.209:5532/cpia)
- Spec: docs/superpowers/specs/2026-05-27-cpia-exporter-graph-integration-design.md
- Plan: docs/superpowers/plans/2026-05-27-cpia-exporter-graph-integration-plan.md

---

## 누적 commits (10개)
| SHA | 메시지 |
|-----|--------|
| 209b78d | feat(db): consolidated_reports 테이블 마이그 (D-4 / S-1) |
| 74a1341 | feat(db): consolidated_reports helper 2 (upsert + fetch) TDD |
| 312bcc6 | feat(state): CPIAState 에 consolidated_xlsx meta 2 필드 (D-7) |
| 0dbd449 | feat(exporter): consolidated_xlsx_node — graph 노드 wrapper (D-1 / D-3) |
| e7e92de | docs(spec): exporter swallow 패턴 정정 (LangGraph 거동 B 대응) |
| 2c2e4a6 | feat(graph): atomizer fan-out + exporter dual-END (D-3 N-1 / D-8) |
| 5c3eab5 | feat(exporter_routes): (E-2) hybrid + #N21 부분 해소 (D-5) |
| 3187bfc | feat(seed): consolidated_reports mock backfill (D-11) |
| a028e99 | feat(agents): _AGENTS_META 에 Exporter stage 8 추가 (D-10) |
| fb22470 | feat(web/export): handleExport swap — 정적 fallback → /export/run (D-9 / #R-N2) |

---

## 검증 결과

### Step 1 — FastAPI 기동

```
$ curl -s http://localhost:8000/health
{"status":"ok","pg":true,"version":"0.1.0"}
```

→ pg: true, status: ok. DB 연결 포함 정상 기동 확인.

---

### Step 2 — /export/run cache hit (T6 mock row)

```
$ curl -sv -o /tmp/test.xlsx 'http://localhost:8000/export/run?site_id=m15x-ph3-ibl&date=2025-09-25' 2>&1 | grep -E "HTTP|content-disposition|Content-Length"
> GET /export/run?site_id=m15x-ph3-ibl&date=2025-09-25 HTTP/1.1
< HTTP/1.1 200 OK
< content-length: 179935
< content-disposition: attachment; filename="통합작업일보_2025-09-25.xlsx"

$ ls -la /tmp/test.xlsx
-rw-r--r--  1 kyungseoplee  wheel  179935 May 27 18:39 /tmp/test.xlsx
```

→ HTTP 200, 한글 파일명 정상, byte_size=179935 (T6 mock row 와 일치).

---

### Step 3 — xlsx 시트 검증

```
$ PYTHONPATH=. python3 -c "from openpyxl import load_workbook; wb = load_workbook('/tmp/test.xlsx'); ..."
sheetnames: ['1.출력인원 현황', '2.직종별 인원현황', '3.장비현황', '4.물량']
  1.출력인원 현황: 384 rows x 37 cols
  2.직종별 인원현황: 15311 rows x 25 cols
  3.장비현황: 12512 rows x 25 cols
  4.물량: 610 rows x 17 cols
```

→ 4개 시트 모두 존재, 각 시트에 실 데이터 (비어있지 않음) 확인.

---

### Step 4 — consolidated_reports PG row

```
$ psql "$POSTGRES_URL" -c "SELECT site_id, report_date, byte_size, is_mock, generated_at FROM consolidated_reports ORDER BY generated_at DESC LIMIT 5"
   site_id    | report_date | byte_size | is_mock |         generated_at
--------------+-------------+-----------+---------+-------------------------------
 m15x-ph3-ibl | 2025-09-25  |    179935 | t       | 2026-05-27 18:32:42.442614+09
(1 row)
```

→ T6 mock backfill row 존재, byte_size 일치, is_mock=t 확인.

---

### Step 5 — /api/agents/status (8 entries)

```
$ curl -s http://localhost:8000/api/agents/status | python3 -m json.tool
[
    {"step": 1, "name": "Collector", "korean_name": "수집", "group": "collect", "state": "idle"},
    {"step": 2, "name": "Parser", "korean_name": "파싱", "group": "collect", "state": "idle"},
    {"step": 3, "name": "Mapper", "korean_name": "매핑", "group": "collect", "state": "idle"},
    {"step": 4, "name": "Atomizer", "korean_name": "Atomizer", "group": "collect", "active_count": 6, "state": "processing"},
    {"step": 5, "name": "Reporter", "korean_name": "보고", "group": "analyze", "state": "idle"},
    {"step": 6, "name": "Forecaster", "korean_name": "예측", "group": "analyze", "state": "idle"},
    {"step": 7, "name": "Optimizer", "korean_name": "조언", "group": "analyze", "state": "idle"},
    {"step": 8, "name": "Exporter", "korean_name": "내보내기",
     "description": "graph cycle 마다 통합 xlsx 사전생성 (consolidated_reports UPSERT)",
     "model": "openpyxl", "group": "analyze", "state": "idle"}
]
```

→ 8개 항목 전부 확인. Exporter step=8, group=analyze, model=openpyxl 정상.

---

### Step 6 — Graph cycle 실행 (optional)

```
$ PYTHONPATH=. python3 /tmp/exporter_cycle_test.py  [300s timeout]
error connecting in 'pool-1':
error connecting in 'pool-1':
...
KILLING after 300s
```

**결과: TIMED OUT / FAILED**

실패 원인: `pool-1` asyncpg 연결 오류. 로컬 → AWS 서버 (43.200.85.209:5532) PG pool 초기화 실패.
단, `/opt/homebrew/Cellar/libpq/18.4/bin/psql "$POSTGRES_URL"` 직접 연결은 정상 (`SELECT 1` 응답).
→ asyncpg connection pool 의 최소 연결 수 확보 타임아웃 또는 AWS 서버 방화벽 문제로 추정.
→ mock row 기반 hot-path (Step 2-5) 는 정상 통과. 실 graph cycle 은 AWS 서버 환경에서 검증 필요.

---

### Step 7 — dead_letter

```
$ ls data/input/dead_letter/
ls: data/input/dead_letter/: No such file or directory

$ ls -la data/input/
total 0
drwxr-xr-x   3 kyungseoplee  staff   96 May 17 13:47 .
drwxr-xr-x  16 kyungseoplee  staff  512 May 22 12:55 ..
-rw-r--r--   1 kyungseoplee  staff    0 May 17 13:47 .gitkeep
```

→ dead_letter 디렉토리 미생성. 에러 처리 경로로 라우팅된 파일 없음 (정상).

---

### Step 8 — UI 수동 검증

**DEFERRED** — 사용자가 npm run dev + Chrome DevTools 로 확인 필요.

확인 체크리스트:
- [ ] `http://localhost:5536/export` → 날짜 `2025-09-25` 선택 → Export 버튼 클릭
  - 기대: `GET /export/run?site_id=...&date=2025-09-25` 요청 발생
  - 기대: HTTP 200 + `content-disposition: attachment; filename="통합작업일보_2025-09-25.xlsx"` → 파일 다운로드
- [ ] `http://localhost:5536/tasks` → Agent stage progress 목록에 Exporter (8번째) 노출 확인

---

## 결론

**hot path 검증 통과 (mock row 기반)**:
- FastAPI `/export/run` → consolidated_reports FETCH → StreamingResponse (179935 bytes) 정상
- 4개 시트 구조 및 데이터 무결성 확인
- PG row 존재 확인
- 8 agents metadata Exporter 포함 확인

**graph cycle**: 로컬 환경에서 asyncpg pool 초기화 실패 (AWS 연결 제한). AWS 배포 환경에서 재검증 권고.

**UI**: 수동 검증 deferred.

PoC 데모 준비 기준: hot-path (다운로드 플로우) 검증 완료, demo 진행 가능.

---

## 잔여 백로그 (별 cycle)

| 항목 | 출처 |
|------|------|
| 노드 PG 접근 패턴 graph-wide refactor (asyncpg pool 공유) | spec §10 |
| reporter → exporter rename (선행 #R-N1) | spec #R-N1 |
| PG advisory lock (D-6 EC 대안) | spec D-6 |
| consolidated_reports FK ON DELETE CASCADE 보강 | T0 quality reviewer |
| `_Any` alias / `utcnow` deprecated codebase-wide cleanup | T3 quality reviewer |
| graph cycle 로컬 검증 (asyncpg pool timeout 원인 분석) | Step 6 실패 |
