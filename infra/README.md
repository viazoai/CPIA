# CPIA Infra — homelab 배포 가이드

PoC 1차 단계의 homelab 셋업. 4개 컨테이너 (`postgres`·`chroma`·`cloudflared`·`adminer`)
를 `infra/docker-compose.yml` 한 묶음으로 운영.
PostgreSQL + ChromaDB + Cloudflare Tunnel 3 컨테이너. 팀원 A·B 모두 이 한 서버를 바라본다.

> **현재 상태:** A 트랙은 자기 PC 의 로컬 Docker 에서 PoC 진행 중
> (`docs/superpowers/plans/2026-05-14-cpia-mapping-layer-implementation.md` Task 10).
> homelab 인프라는 그동안 대기 상태로 유지하다가, A 의 PoC 완료 시점에
> 별도 plan 으로 데이터 마이그레이션 (pg_dump + Chroma export/import).

## 1. 최초 셋업 (homelab 에서 1회)

```bash
# repo 클론 (없으면)
git clone git@github.com:viazoai/CPIA.git
cd CPIA

# .env 셋업 (.env.example 가 실 값 포함 — viazoai org 내부 공유)
cp .env.example .env
# .env 의 POSTGRES_PASSWORD, CLOUDFLARED_TOKEN 채우기

# 인프라 가동
cd infra
docker compose up -d
docker compose ps          # 4 개 컨테이너 Up
```

- `postgres/init.sql` 은 컨테이너 첫 부팅 시 자동 실행 → 6 개 테이블 생성
- LangGraph 의 `checkpoints` 테이블은 파이프라인 첫 실행 시 PostgresSaver 가 자체 생성
- A_Track 결정으로 추가된 `activity_master` 테이블은 마이그레이션 시 `infra/postgres/migrations/` 로 보정
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

## 2. 컨테이너 구성

| 서비스 | 이미지 | 호스트 포트 (127.0.0.1) | 컨테이너 내부 | 용도 |
|---|---|---|---|---|
| `cpia-postgres`    | postgres:16-alpine          | 5532 | 5432 | 파이프라인 결과 + LangGraph checkpoint |
| `cpia-chroma`      | chromadb/chroma:0.5.20      | 5533 | 8000 | Vector DB — `wbs_master` + `daily_activities` 두 컬렉션 |
| `cpia-adminer`     | adminer:4.8.1-standalone    | 5534 | 8080 | Postgres web UI (B 본인용) |
| `cpia-cloudflared` | cloudflare/cloudflared:latest | —    | —    | A 측 외부 접근용 Tunnel (token 방식) |

모든 호스트 포트는 `127.0.0.1` 만 바인딩 — LAN/외부 직접 노출 없음.

## 3. ChromaDB 컬렉션 (A_Track 합의)

| 컬렉션 | 적재 시점 | 용도 |
|---|---|---|
| `wbs_master`        | 1회 (`scripts/load_master_list.py`) | Mapper 의 WBS 매핑 RAG 검색 — 189 records |
| `daily_activities`  | 매일 누적 (Atomizer) | Forecaster 의 유사 과거 이력 검색 |

PG 짝 테이블: `activity_master` — Chroma metadata 만으로는 SQL JOIN·날짜 필터링이
부족해 정규화 적재. 상세는 [`docs/schema/postgres.md`](../docs/schema/postgres.md) 참조.

## 4. 외부 접근 (Cloudflare Tunnel TCP)

A 트랙이 자기 PC 에서 homelab Postgres 에 접근할 때 사용 (PoC 마이그레이션 후 활용).

- homelab 측: `cpia-cloudflared` 컨테이너가 `CLOUDFLARED_TOKEN` 으로 Cloudflare 에
  outbound QUIC 연결. inbound 포트 0.
- Cloudflare Public Hostname: **TCP** 타입으로 `cpia-postgres:5432` 매핑 (호스트명은 사내 메신저)
- A 측: `cloudflared access tcp --hostname <호스트명> --url localhost:5532` 한 줄
  → A 의 PC localhost:5532 로 자동 forward

> Chroma 는 PoC 1차에 외부 노출하지 않는다. 통합 GATE 시점에 별도 hostname 추가.

## 5. 스키마 변경 절차

직접 `ALTER TABLE` 금지. 대신:

1. `infra/postgres/migrations/YYYYMMDD_<설명>.sql` 파일 추가
2. PR 로 머지
3. homelab 에서 수동 적용:
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
   docker exec -i cpia-postgres psql -U cpia -d cpia \
     < postgres/migrations/YYYYMMDD_<설명>.sql
   ```

[`docs/schema/postgres.md`](../docs/schema/postgres.md) 도 같은 PR 안에서 업데이트.

## 6. 데이터 보존
`docs/schema/postgres.md` 도 같은 PR 안에서 업데이트.

## 5. 데이터 보존

명명된 볼륨:

| 볼륨 | 내용 |
|---|---|
| `cpia_postgres_data` | Postgres data dir |
| `cpia_chroma_data`   | Chroma 임베딩 + 메타데이터 |

전체 리셋:

```bash
docker compose down -v   # 모든 볼륨 삭제 — 데이터 전부 날아감 (주의)
```

## 7. 점검 명령

```bash
# 한 줄 상태
docker compose ps

# Postgres 테이블
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

# Chroma heartbeat
curl -s http://localhost:5533/api/v1/heartbeat

# Cloudflared 연결 (Registered tunnel connection 4 줄 + ERR 없으면 OK)
docker logs --tail 30 cpia-cloudflared

# Adminer (브라우저)
# 자기 노트북에서: ssh -L 5534:localhost:5534 -p <port> zoai@<homelab> -N
# 그 다음 http://localhost:5534
# Cloudflared tunnel 상태
docker logs cpia-cloudflared --tail 20
```

## 7. 두 환경 분리 (로컬 dev vs homelab)

- **로컬 dev**: `infra/local/docker-compose.local.yml` — 포트 5432/8000, init 은 `activity_master` 만
- **homelab**: `infra/docker-compose.yml` (이 README) — 포트 5532/5533, init 은 7 테이블 + cloudflared

`.env.local` 의 두 블록 (line 13-15 로컬 / line 24-28 homelab) 중 한 환경만 활성화 — dotenv 가 후순위 덮어쓰기.
