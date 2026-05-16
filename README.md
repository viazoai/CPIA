# CPIA — Construction Productivity Intelligence Agent

> 작업일보 → AI 7-Agent 파이프라인 (LangGraph) → 생산성 진단 + 경영진 액션 추천

## Team

| 트랙 | 영역 | 담당 |
|---|---|---|
| A | AI/Python (`pipeline/`) | [@leekyungseop](https://github.com/leekyungseop) |
| B | 프론트/인프라 (`web/`, `infra/`) | [@viazoai](https://github.com/viazoai) |

자세한 설계는 [협업 spec](docs/superpowers/specs/2026-05-14-cpia-2인-langgraph-협업-design.md) 참조.

---

## Quick start — 인프라 (homelab)

```bash
cd infra
cp .env.example .env       # POSTGRES_PASSWORD / CLOUDFLARED_TOKEN 채우기
docker compose up -d
docker compose ps          # postgres·chroma·cloudflared·adminer 모두 Up
```

| 서비스 | 호스트 포트 | 역할 |
|---|---|---|
| `cpia-postgres` | `127.0.0.1:5532` | 파이프라인 결과 + LangGraph checkpoint (+ A_Track 결정의 `activity_master`) |
| `cpia-chroma`   | `127.0.0.1:5533` | Vector DB — `wbs_master` (RAG) + `daily_activities` (유사 이력) 두 컬렉션 |
| `cpia-adminer`  | `127.0.0.1:5534` | Postgres web UI |
| `cpia-cloudflared` | — | A 측 외부 접근용 Tunnel (Postgres TCP) |

모든 호스트 포트는 `127.0.0.1` 만 바인딩 — LAN/외부 직접 노출 없음.

> **현재 상태:** A 트랙은 로컬 Docker 에서 PoC 진행 중
> ([매핑 레이어 plan](docs/superpowers/plans/2026-05-14-cpia-mapping-layer-implementation.md)).
> homelab 은 대기 상태이며, A 의 PoC 완료 시점에 별도 plan 으로 데이터 마이그레이션.

---

## DB 접근

### B (이 homelab 머신 안)

직통 — 외부 도메인·터널 안 거침.

**psql CLI**
```bash
docker exec -it cpia-postgres psql -U cpia -d cpia
# \dt  로 테이블 목록
```

**Adminer (web UI)**
```bash
# 자기 노트북에서 SSH 포트포워딩 띄움
ssh -L 5534:localhost:5534 -p <port> zoai@<homelab>  -N
# 그 다음 자기 노트북 브라우저
open http://localhost:5534
```

로그인:
```
System:   PostgreSQL
Server:   cpia-postgres
Username: cpia
Password: <infra/.env 의 POSTGRES_PASSWORD 값>
Database: cpia
```

### A (외부 PC)

Cloudflare Tunnel TCP — Postgres 만 노출, Chroma 는 PoC 1차에 외부 노출 X.

```bash
# cloudflared 설치 (brew / apt / .exe)
cloudflared access tcp \
  --hostname <별도전달호스트> \
  --url localhost:5532 &

# 자기 PC pipeline/.env
POSTGRES_URL=postgresql://cpia:<별도전달비번>@localhost:5532/cpia
ANTHROPIC_API_KEY=<본인 발급>
OPENAI_API_KEY=<본인 발급>
```

> 호스트명·비번은 사내 메신저 DM 으로 별도 전달.
> Chroma 접근이 필요한 GATE 시점에 추가 가이드 제공.

---

## 운영 메모

| 항목 | 정책 |
|---|---|
| 데이터 보존 | `cpia_postgres_data`·`cpia_chroma_data` named volume |
| 스키마 변경 | `infra/postgres/migrations/YYYYMMDD_*.sql` 누적, 직접 ALTER 금지 |
| 비번·토큰 | `.env.example` 로만 git 공유, 실값은 사내 메신저 |
| 전체 리셋 | `docker compose down -v` — 모든 데이터 삭제 (주의) |

상세 절차: [`infra/README.md`](infra/README.md)
