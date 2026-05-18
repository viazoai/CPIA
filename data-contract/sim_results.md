# CPIA FE↔BE Bridge — 시뮬 결과 (writing-plans 진입 전 sanity check)

> 실행: 2026-05-17 19:55. spec §7 Phase 1~3 의 핵심 SQL + path 를 prod PG (127.0.0.1:5532 cloudflared tunnel) 에서 실 호출 검증. UPDATE 는 BEGIN/ROLLBACK 으로 데이터 변경 0.
>
> 산출: 발견된 risk 7 항목 → spec 정정 또는 backlog 마킹.

---

## §1. 시뮬 결과 요약

| # | 시뮬 | 결과 | 영향 |
|---|---|---|---|
| 1 | uv add fastapi / uvicorn | **이미 설치됨** (fastapi 0.136.1 / uvicorn 0.46.0) — but pyproject.toml dependencies 에 박힘 X | Phase 1 Task 1-1 단순화 — `uv add` 대신 pyproject.toml 명시 추가 |
| 2 | 포트 8000 가용성 | **ssh tunnel 점유 중** | spec 의 `--port 8000` → **`--port 8001`** 정정 |
| 3 | fetch_sites_with_forecasts SQL | ✅ 6 row + 19 field 다 채워짐 | OK |
| 4 | NUMERIC casting | ⚠️ asyncpg → `decimal.Decimal` 반환 (string 형태로 JSON 직렬화) | API layer 가 **`float()` 변환 필수** — spec §3 명시 |
| 5 | sites.last_run_id | ⚠️ **모든 6 site = NULL** (기존 시뮬 1 건이 D-1 결정 전이라 미반영) | **별 backfill task 필요** (시뮬 b826e4d9 → m15x-ph3-ibl 매핑 UPDATE) |
| 6 | update_run_status SQL CHECK | ✅ 5 status 통과 + invalid 거부 | OK |
| 7 | update_site_last_run SQL | ✅ UPDATE 1 row 정상 | OK |
| 8 | checkpoints thread_id | ⚠️ **`demo-{run_id}` prefix** (synthetic_daily_report.py:424 hard-code) | spec D-6 정정 — "thread_id = run_id 그대로 (FastAPI), demo-prefix 는 시뮬 전용" |
| 9 | activity_master 4 trade only | ⚠️ 설비/전기/건축/소방만, 토목/구조/통신/기계 0 | WBSNode 빌드 시 PoC 데이터 한계 명시 (본 cycle scope 밖) |
| 10 | forecasts.risk_level vs assessment | ⚠️ 같은 row 의 두 값 mismatch ("주의" vs "정상") | D-14 결정 정합 (risk_level 만 노출) — root cause 는 별 backlog |
| 11 | AGENT_META 7 agent (D-9) | ✅ CLAUDE.md "Agent 역할 요약" 표 정합 | BE FastAPI hard-code 가능 |

---

## §2. 발견된 7 risk → spec 반영

### R-1. 포트 8000 → 8001
spec §7 Phase 1 의 `uvicorn ... --port 8000` → `--port 8001` 정정. .env / docker-compose 도 같이.

### R-2. NUMERIC casting (FE 가 `number` 받아야)
spec §3 architecture 에 한 줄 추가: "API layer 는 asyncpg 가 반환하는 `decimal.Decimal` 을 `float()` 으로 변환 후 JSON 직렬화 (FE TS 의 `number` 타입 정합)".

### R-3. sites.last_run_id backfill
spec §7 Phase 2 또는 별 Phase 0 에 task 추가:
```sql
-- 본 cycle 시뮬 1 건 (run_id b826e4d9) 을 sites 에 backfill
UPDATE sites SET last_run_id='b826e4d9-5b36-41fd-99fa-f989817c6122', updated_at=NOW()
WHERE site_id='m15x-ph3-ibl';
```
이게 안 박히면 D-1 graph END 패치 후에도 historical run 데이터가 API 응답에 안 잡힘.

### R-4. thread_id prefix
spec D-6 결정 정정:
```
D-6 채택: graph.aget_state(thread_id=run_id) 사용. 단 thread_id 형식은 호출자가 결정 —
- FastAPI 의 /run endpoint = thread_id = run_id 그대로 (uuid 문자열)
- synthetic_daily_report.py 시뮬 = `demo-{run_id}` prefix (현 hard-code 유지)
- FastAPI 의 /status / /resume / GET 읽기 endpoint = `request.run_id` 인자 그대로 thread_id 로 사용
```

### R-5. activity_master 데이터 한계
spec §4.6 WBSNode 빌드에 한 줄: "현 prod 데이터 = 4 trade (설비/전기/건축/소방) 1059 row. 토목/구조/통신/기계 0. PoC 데모는 4 trade 만 트리 표시. 전 trade 확장은 별 cycle."

### R-6. risk_level vs assessment mismatch
spec §6 D-14 옆에 한 줄: "Forecaster 코드의 두 컬럼 (risk_level / assessment) 정합 mismatch 는 별 backlog. 본 endpoint 는 risk_level 만 노출."

### R-7. fastapi 이미 설치
spec Phase 1 Task 1-1 정정: `uv add fastapi 'uvicorn[standard]'` → "이미 .venv 설치됨 (import 가능). pyproject.toml `[project] dependencies` 에 `fastapi>=0.115.0` + `uvicorn[standard]>=0.32.0` 명시 추가 (lock 정합)".

---

## §3. 검증 명령 (재현 가능)

```bash
# prod tunnel + asyncpg 시뮬
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python3 /tmp/cpia_sim_phase2_3.py
```

(스크립트 = `/tmp/cpia_sim_phase2_3.py`, 본 시뮬 종료 후 보존)

---

## §4. 시뮬 종결 결론

- **차단 risk 0** — 모든 SQL / FastAPI / graph path 가 prod PG 에서 작동 가능
- **spec 정정 7 항목** — 위 R-1~R-7 모두 spec md 에 반영 후 writing-plans 진입
- **별 backlog 2 항목** — risk_level/assessment mismatch (Forecaster) + activity_master trade 확장 (데이터)

→ **writing-plans 진입 ready**.
