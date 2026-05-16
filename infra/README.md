# CPIA Infra — homelab 배포 가이드

PostgreSQL + ChromaDB + Cloudflare Tunnel 3 컨테이너. 팀원 A·B 모두 이 한 서버를 바라본다.

## 1. 최초 셋업 (homelab 호스트에서 1회)

```bash
# repo 클론 (없으면)
git clone git@github.com:viazoai/CPIA.git
cd CPIA

# .env 셋업 (.env.example 가 실 값 포함 — viazoai org 내부 공유)
cp .env.example .env

# 인프라 가동
cd infra
docker compose up -d
docker compose ps   # postgres / chroma / cloudflared 3개 모두 healthy 확인
```

`postgres/init.sql` 이 첫 부팅 시 자동 실행되어 **7개 테이블** 생성:

| 테이블 | 용도 |
|---|---|
| `activity_master` | WBS Master List (load_master_list.py 가 적재) |
| `pipeline_runs` | LangGraph run 메타 |
| `daily_reports` | Reporter 결과 |
| `forecasts` | Forecaster 결과 |
| `optimizer_advice` | Optimizer 결과 |
| `mapping_corrections` | H-i-L 1 보정 |
| `sites` | Dashboard Layer 1 (6 mock + 1 real) |

LangGraph 의 `checkpoints` 는 첫 실행 시 PostgresSaver 가 자체 생성.

## 2. 접속 정보

| 서비스 | 호스트 포트 (default) | 컨테이너 포트 |
|---|---|---|
| PostgreSQL | **5532** | 5432 |
| ChromaDB | **5533** | 8000 |
| Cloudflare Tunnel | — | (외부 노출은 Zero Trust 대시보드 설정) |

`.env` 로 포트 override 가능 (`POSTGRES_PORT=5532 / CHROMA_PORT=5533`).
`127.0.0.1` bind 라 호스트 외부 직접 접근 불가 → Cloudflare Tunnel 경유.

## 3. Master List 적재 (호스트 또는 원격에서 1회)

```bash
# Python 3.11 + uv 필요. CPIA 루트에서:
PYTHONPATH="$(pwd)" uv run --project pipeline scripts/load_master_list.py \
    --filter-companies 남웅건설 세보엠이씨 창원기전

# 기대 출력:
#   [load] 전체 (WA, L6) 그룹: 102
#   [load] filter 적용 후 그룹: 30
#   [load] 적재 row: 1059
#   [load] PG activity_master upsert: 1059 rows
#   [load] Chroma wbs_master upsert: 30 groups
```

원격에서 적재할 때는 `.env` 의 `POSTGRES_URL` / `CHROMA_HOST` 를 homelab hostname (또는 Cloudflared tunnel 도메인) 으로 변경.

## 4. 스키마 변경 절차

직접 `ALTER TABLE` 금지. 대신:

1. `infra/postgres/migrations/YYYYMMDD_<설명>.sql` 추가
2. PR 머지
3. homelab 호스트에서 수동 적용:
   ```bash
   docker exec -i cpia-postgres psql -U cpia -d cpia < postgres/migrations/YYYYMMDD_<설명>.sql
   ```

`docs/schema/postgres.md` 도 같은 PR 안에서 업데이트.

## 5. 데이터 보존

명명된 볼륨:

| 볼륨 | 내용 |
|---|---|
| `cpia_postgres_data` | Postgres data dir |
| `cpia_chroma_data` | Chroma 임베딩 + 인덱스 |

전체 리셋 (데이터 전부 날아감):

```bash
docker compose down -v
```

## 6. 점검 명령

```bash
# Postgres 테이블 확인 (activity_master 1059 row 기대)
docker exec -it cpia-postgres psql -U cpia -d cpia -c "\dt"
docker exec -it cpia-postgres psql -U cpia -d cpia -c "SELECT COUNT(*) FROM activity_master;"

# Chroma heartbeat + 컬렉션 (wbs_master 30 items 기대)
curl -s http://localhost:5533/api/v2/heartbeat
docker exec cpia-chroma curl -s http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections

# Cloudflared tunnel 상태
docker logs cpia-cloudflared --tail 20
```

## 7. 두 환경 분리 (로컬 dev vs homelab)

- **로컬 dev**: `infra/local/docker-compose.local.yml` — 포트 5432/8000, init 은 `activity_master` 만
- **homelab**: `infra/docker-compose.yml` (이 README) — 포트 5532/5533, init 은 7 테이블 + cloudflared

`.env.local` 의 두 블록 (line 13-15 로컬 / line 24-28 homelab) 중 한 환경만 활성화 — dotenv 가 후순위 덮어쓰기.
