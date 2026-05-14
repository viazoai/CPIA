# CPIA Infra — homelab 배포 가이드

PostgreSQL + ChromaDB 두 컨테이너만 띄운다. 팀원 A·B 모두 이 한 서버를 바라본다.

## 1. 최초 셋업 (homelab 호스트에서 1회)

```bash
cd infra
cp .env.example .env
# .env 의 POSTGRES_PASSWORD 등을 실제 값으로 변경

docker compose up -d
docker compose ps          # postgres, chroma 모두 healthy 확인
```

`postgres/init.sql` 은 컨테이너 첫 부팅 시 자동 실행되어 6개 테이블을 만든다.
LangGraph 의 `checkpoints` 테이블은 파이프라인 첫 실행 시 PostgresSaver 가 자체 생성한다.

## 2. 접속 정보

| 서비스      | 포트 | 용도                          |
|-------------|------|-------------------------------|
| PostgreSQL  | 5432 | 파이프라인 결과 + LangGraph checkpoint |
| ChromaDB    | 8000 | Vector DB (daily_activities)  |

팀원이 `.env` 에 적을 값 (예시):

```env
POSTGRES_URL=postgresql://cpia:<password>@<homelab-host>:5432/cpia
CHROMA_HOST=<homelab-host>
CHROMA_PORT=8000
```

외부 접속은 Cloudflare Tunnel 을 통해 노출한다 (별도 셋업, 본 compose 에는 미포함).

## 3. 스키마 변경 절차

직접 `ALTER TABLE` 을 치지 않는다. 대신:

1. `infra/postgres/migrations/YYYYMMDD_<설명>.sql` 파일 추가
2. PR 로 머지
3. homelab 호스트에서 수동 적용:
   ```bash
   docker exec -i cpia-postgres psql -U cpia -d cpia < postgres/migrations/YYYYMMDD_<설명>.sql
   ```

`docs/schema/postgres.md` 도 같은 PR 안에서 업데이트한다 (Phase 0 합의 문서).

## 4. 데이터 보존

명명된 볼륨에 영속화된다:

| 볼륨             | 내용                  |
|------------------|-----------------------|
| `cpia_postgres_data` | Postgres data dir |
| `cpia_chroma_data`   | Chroma 임베딩 + 인덱스 |

전체 리셋이 필요할 때만:

```bash
docker compose down -v   # 모든 볼륨 삭제 — 데이터 전부 날아감
```

## 5. 점검 명령

```bash
# Postgres 테이블 확인
docker exec -it cpia-postgres psql -U cpia -d cpia -c "\dt"

# Chroma heartbeat
curl -s http://localhost:8000/api/v1/heartbeat
```
