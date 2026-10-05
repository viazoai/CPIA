# CPIA Infra — homelab 배포 가이드

homelab 운영 셋업. 6 개 컨테이너 (`postgres` · `chroma` · `adminer` · `cloudflared` · `pipeline` · `web`) 를 `infra/docker-compose.yml` 한 묶음으로 운영. 팀원 A·B 모두 이 한 서버를 바라본다.

> **현재 상태 (2026-10-01~):** AWS(2026-05-20~09-30 운영) 에서 homelab 으로 복귀 완료.
> 외부 접속은 `cpia-tunnel` (Cloudflare Tunnel) 경유 — `cpia.zoai.uk`(web), `cpia-pg.zoai.uk`(postgres TCP).
> 이전 절차·롤백은 [`docs/migration-homelab.md`](../docs/migration-homelab.md) 참조.

## 1. 최초 셋업 (homelab 에서 1회)

```bash
# repo 클론 (없으면)
git clone git@github.com:viazoai/CPIA.git
cd CPIA

# .env 셋업 — 루트 .env 가 단일 출처
cp .env.example .env
# .env 의 POSTGRES_PASSWORD, AZURE_OPENAI_API_KEY, CLOUDFLARED_TOKEN 채우기
#   CLOUDFLARED_TOKEN: cloudflared 로그인된 호스트에서 `cloudflared tunnel token cpia-tunnel`

# 전체 가동 — 반드시 레포 루트에서 make 사용
make prod
docker ps --filter "name=^cpia-"   # 6 개 컨테이너 Up
```

> **`cd infra && docker compose up` 금지.** compose 는 `.env` 를 compose 파일 폴더(`infra/`)에서 찾기 때문에
> 루트 `.env` 를 못 읽고 키가 빈 값·비밀번호가 기본값(`cpia`)으로 들어간다. `make` 타깃은 모두
> `--env-file .env` 를 명시한다 (ae82e9c). 직접 호출할 때도 루트에서
> `docker compose --env-file .env -f infra/docker-compose.yml ...` 형태로 쓴다.

- `postgres/init.sql` 은 컨테이너 첫 부팅 시 자동 실행 → 6 개 테이블 생성
- `activity_master` 테이블은 `postgres/migrations/20260516_add_activity_master.sql` 로 적용
- LangGraph 의 `checkpoints` 테이블은 파이프라인 첫 실행 시 PostgresSaver 가 자체 생성
- `cpia-web` · `cpia-pipeline` 은 레포 루트를 컨텍스트로 빌드 (`web/Dockerfile`, `pipeline/Dockerfile`). 코드 갱신 시 `make build` / `make build-pipeline`.

## 2. PostgreSQL 7 테이블

| 테이블 | 출처 | 용도 |
|---|---|---|
| `activity_master` | migration 20260516 + `load_master_list.py` | WBS Master List |
| `pipeline_runs` | init.sql | LangGraph run 메타 |
| `daily_reports` | init.sql | Reporter 결과 |
| `forecasts` | init.sql | Forecaster 결과 |
| `optimizer_advice` | init.sql | Optimizer 결과 |
| `mapping_corrections` | init.sql | H-i-L 1 보정 |
| `sites` | init.sql | Dashboard Layer 1 (5 mock + 1 real) |

## 3. 컨테이너 구성

| 서비스 | 이미지 | 호스트 포트 | 바인딩 | 컨테이너 내부 | 용도 |
|---|---|---|---|---|---|
| `cpia-postgres`    | postgres:16-alpine                     | 5532 | 127.0.0.1 | 5432 | 파이프라인 결과 + LangGraph checkpoint |
| `cpia-chroma`      | chromadb/chroma:0.5.20                 | 5533 | 127.0.0.1 | 8000 | Vector DB — `wbs_master` + `daily_activities` |
| `cpia-adminer`     | adminer:4.8.1-standalone               | 5534 | 127.0.0.1 | 8080 | Postgres web UI |
| `cpia-web`         | ghcr.io/viazoai/cpia-web (로컬 build)      | 5535 | 0.0.0.0 | 5535 | Next.js Dashboard |
| `cpia-pipeline`    | ghcr.io/viazoai/cpia-pipeline (로컬 build) | 5538 | 0.0.0.0 | 8000 | FastAPI + LangGraph |
| `cpia-cloudflared` | cloudflare/cloudflared:latest          |  —   |  —   |  —   | 외부 접근용 Tunnel (`cpia-tunnel`, token) |

DB·Chroma·Adminer 는 `127.0.0.1` 만 바인딩 (Chroma 는 무인증). web·pipeline 은 LAN 확인용으로 `0.0.0.0` — pipeline API 도 무인증이므로 LAN 신뢰 전제. 외부 접속은 `cloudflared` Tunnel 경유만.

## 4. ChromaDB 컬렉션 (A_Track 합의)

| 컬렉션 | 적재 시점 | 용도 |
|---|---|---|
| `wbs_master`        | 1회 (`scripts/load_master_list.py`)  | Mapper 의 WBS 매핑 RAG 검색 |
| `daily_activities`  | 매일 누적 (Atomizer)                  | Forecaster 의 유사 과거 이력 검색 |

PG 짝 테이블: `activity_master` — Chroma metadata 만으로는 SQL JOIN·날짜 필터링이 부족해 정규화 적재. 상세는 [`docs/schema/postgres.md`](../docs/schema/postgres.md) 참조.

## 5. Master List 적재 (호스트 또는 원격에서 1회)

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

## 6. 외부 접근 (Cloudflare Tunnel)

`cpia-cloudflared` 한 컨테이너가 token 으로 Cloudflare 에 outbound QUIC 연결을 맺고, **Zero Trust 대시보드에서 등록한 Public Hostname** 으로 inbound 요청을 라우팅한다. 호스트 측 inbound 포트는 열지 않는다.

### 6-1. Postgres TCP (A_Track 용)

- Public Hostname `cpia-pg.zoai.uk` → **TCP** `cpia-postgres:5432`
- 팀원 PC: `cloudflared access tcp --hostname cpia-pg.zoai.uk --url localhost:5532` 한 줄 → PC 의 localhost:5532 로 forward
  (`.env` 는 `POSTGRES_URL=postgresql://cpia:<password>@localhost:5532/cpia`)

### 6-2. Web HTTP (경영진 시연 / 외부 데모용)

- Public Hostname `cpia.zoai.uk` → **HTTP** `cpia-web:5535` → `https://cpia.zoai.uk`
- ingress 는 Zero Trust 대시보드(Tunnels → `cpia-tunnel`)에서 관리 (remote-managed). 컨테이너 기동 로그의
  `Updated to new configuration` 줄에서 현재 ingress 를 확인할 수 있다.
- DNS 는 두 호스트 모두 `cpia-tunnel` CNAME. 재지정: `cloudflared tunnel route dns --overwrite-dns cpia-tunnel <호스트>`
- (선택) Zero Trust → Access → Application 으로 보안 정책 추가 — 사내 이메일 도메인 제한, 1회용 PIN 등.

> Chroma 는 PoC 1차에 외부 노출하지 않는다. 통합 GATE 시점에 별도 hostname 추가.

## 7. 스키마 변경 절차

직접 `ALTER TABLE` 금지. 대신:

1. `infra/postgres/migrations/YYYYMMDD_<설명>.sql` 추가
2. PR 머지
3. homelab 호스트에서 수동 적용:
   ```bash
   docker exec -i cpia-postgres psql -U cpia -d cpia \
     < postgres/migrations/YYYYMMDD_<설명>.sql
   ```

[`docs/schema/postgres.md`](../docs/schema/postgres.md) 도 같은 PR 안에서 업데이트.

## 8. 데이터 보존

| 볼륨 | 내용 |
|---|---|
| `cpia_postgres_data` | Postgres data dir |
| `cpia_chroma_data`   | Chroma 임베딩 + 인덱스 |

전체 리셋 (데이터 전부 날아감, 주의):

```bash
docker compose --env-file .env -f infra/docker-compose.yml down -v   # 레포 루트에서
```

## 9. 점검 명령

```bash
# 한 줄 상태
docker compose ps

# Postgres 테이블 + activity_master count (1059 row 기대)
docker exec -it cpia-postgres psql -U cpia -d cpia -c "\dt"
docker exec -it cpia-postgres psql -U cpia -d cpia -c "SELECT COUNT(*) FROM activity_master;"

# Chroma heartbeat + 컬렉션 (wbs_master 30 items 기대)
curl -s http://localhost:5533/api/v2/heartbeat
docker exec cpia-chroma curl -s \
  http://localhost:8000/api/v2/tenants/default_tenant/databases/default_database/collections

# Cloudflared 연결 (Registered tunnel connection 4 줄 + ERR 없으면 OK)
docker logs --tail 30 cpia-cloudflared

# Web 헬스 (200 OK 기대) + 컨테이너 내 mock data mount 확인 (10 파일 기대)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5535/
docker exec cpia-web ls /app/data | head -20

# Adminer (브라우저) — 자기 노트북에서 SSH 포트포워딩 후 http://localhost:5534
ssh -L 5534:localhost:5534 -p <port> zoai@<homelab> -N
```

### Web 코드 재배포

```bash
# B_Track 코드 수정 후 — homelab 호스트에서
cd ~/Projects/CPIA
git pull
make build                         # web 만 재빌드 + force-recreate (pipeline 은 make build-pipeline)
docker logs --tail 10 cpia-web     # 부팅 로그 확인 (Ready 출력)
```

## 10. 두 환경 분리 (로컬 dev vs homelab)

- **로컬 dev**: `infra/local/docker-compose.local.yml` — 포트 5432/8000, init 은 `activity_master` 만
- **homelab**: `infra/docker-compose.yml` (이 README) — 포트 5532/5533, init 은 7 테이블 + cloudflared

`.env.example` 의 두 블록 (로컬 dev / Homelab) 중 한 환경만 활성화 — dotenv 가 후순위 덮어쓰기.
