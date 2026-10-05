# AWS → homelab 마이그레이션 런북

AWS 서버에서 운영 중인 CPIA 스택을 homelab 서버로 되돌린다.
homelab 에 남아 있는 **구버전 CPIA 는 폐기**한다.

## 원칙 — 2트랙 분리

| 트랙 | 대상 | 경로 |
|------|------|------|
| **코드** | `pipeline/`, `web/`, `infra/`, `scripts/`, 문서 | **GitHub** (push → clone) |
| **데이터·시크릿** | `.env`(AES 암호화), PG 덤프, Chroma 볼륨, `data/` | **번들 tar → 내 PC 중계 → scp** |

`.env` 에는 Azure OpenAI API 키가 들어 있다. **GitHub 에 올리지 않는다** (`.gitignore` 등재됨).
번들 안에서는 `openssl enc -aes-256-cbc` 로 암호화되며, 비밀번호는 별도 경로로 전달한다.

## 사용 스크립트

| 스크립트 | 실행 위치 | 역할 |
|----------|-----------|------|
| `scripts/backup.sh` | AWS | 번들 생성 (PG 덤프 + Chroma 볼륨 + data/ + .env 암호화 + manifest) |
| `scripts/purge_old_stack.sh` | homelab | 구버전 컨테이너·볼륨 제거, 구 코드 디렉토리 rename |
| `scripts/restore.sh` | homelab | 번들 복원 + 스택 기동 + manifest 대조 검증 |
| `scripts/chroma_summary.sh` | 양쪽 | Chroma 컬렉션별 문서 수 출력 (검증용) |

---

## 절차

### ① AWS — 번들 생성

```bash
cd ~/cpia
git push origin main          # 코드는 GitHub 으로 (미푸시 커밋 없도록)

bash scripts/backup.sh --no-code
```

- `--no-code`: 코드 tar 생략 (GitHub 경유). 번들 크기가 크게 줄어든다.
- 기본 동작으로 `cpia-web`·`cpia-pipeline` 을 **잠시 정지**해 DB 쓰기를 멈춘 뒤 덤프한다
  (스크립트 종료 시 자동 재기동). 중단 없이 뜨려면 `--no-freeze` — 단 정합성은 보장되지 않는다.
- `.env` 암호화 비밀번호를 묻는다. **이 비밀번호를 기억할 것** (복원 시 필요).
- 출력: `~/cpia_bundle_<timestamp>.tar.gz` + SHA256.

### ② 내 PC — 중계 전송

PC 디스크에 파일을 남기지 않고 스트리밍으로 넘긴다.

SSH 별칭은 PC 의 `~/.ssh/config` 에 설정돼 있다: **`zoai-aws`**, **`zoai-homelab`**.

```bash
ssh zoai-aws "cat ~/cpia_bundle_<ts>.tar.gz" | ssh zoai-homelab "cat > ~/cpia_bundle_<ts>.tar.gz"
```

전송 후 양쪽 SHA256 이 같은지 확인한다.

```bash
ssh zoai-aws      "sha256sum ~/cpia_bundle_<ts>.tar.gz"
ssh zoai-homelab  "sha256sum ~/cpia_bundle_<ts>.tar.gz"
```

### ③ homelab — 구버전 정리

구버전 코드가 `~/cpia` 에 있으면 clone 대상 경로와 충돌하므로 **clone 보다 먼저** 정리한다.
정리 스크립트는 새 레포에 들어 있으므로 임시 경로에 먼저 clone 한다.

```bash
git clone https://github.com/viazoai/CPIA ~/cpia-new
bash ~/cpia-new/scripts/purge_old_stack.sh
mv ~/cpia-new ~/cpia
```

`purge_old_stack.sh` 는:

- `cpia-*` 컨테이너, `cpia_*` 볼륨을 제거한다 (`npm` 등 다른 컨테이너는 건드리지 않음).
- 삭제 전 구 PostgreSQL 을 `~/cpia_old_safety_<ts>/postgres_old.dump` 로 덤프해 둔다
  (`--no-safety-dump` 로 생략 가능).
- 구 코드 디렉토리는 **삭제가 아니라** `~/cpia.old-<ts>` 로 rename 한다 (`--delete-code` 로 완전 삭제).
- `DELETE` 를 직접 입력해야 진행된다 (`--yes` 로 생략 가능).
- 끝나고 포트 5532~5538 점유 여부를 보고한다.

### ④ homelab — 복원

```bash
docker login ghcr.io        # 이미지가 private. PAT 필요 (생략 시 로컬 빌드로 자동 대체)

bash ~/cpia/scripts/restore.sh --from-git ~/cpia_bundle_<ts>.tar.gz ~/cpia
```

`--from-git` 은 번들에 코드가 없다는 뜻이다. `--no-code` 로 뜬 번들에는 **반드시** 붙인다.

스크립트는 복원 후 **manifest 대조 검증**을 자동 실행한다:

- PostgreSQL 전체 테이블 row count 를 원본과 비교
- Chroma 컬렉션별 문서 수를 원본과 비교

`✓ 전체 테이블 일치` / `✓ 일치` 두 줄이 나와야 성공이다.

### ⑤ 확인

```bash
docker ps --filter "name=^cpia-"
curl -I http://localhost:5535          # 대시보드
curl -s http://localhost:5538/docs     # 파이프라인 API
```

브라우저에서 `http://<homelab-IP>:5535` 접속 → 현장 카드·대시보드가 AWS 와 동일한지 눈으로 확인.

---

## 롤백

**AWS 서버는 ⑤ 확인과 DNS 전환이 끝날 때까지 끄지 않는다.** 문제가 생기면 AWS 쪽 스택을 그대로 계속 쓰면 된다
(`backup.sh` 의 freeze 는 백업 중에만 적용되고 끝나면 자동 재기동된다).

homelab 복원이 꼬였을 때 다시 시도하려면:

```bash
bash ~/cpia/scripts/purge_old_stack.sh --yes --delete-code ~/cpia_dummy  # 컨테이너·볼륨만 정리
bash ~/cpia/scripts/restore.sh --from-git ~/cpia_bundle_<ts>.tar.gz ~/cpia
```

## 실행 기록 (2026-10-01)

번들 `cpia_bundle_20261001_053334` (AWS `ip-172-26-4-250`, commit `186e4e1`) 로 진행.
설치 경로는 `~/cpia` 가 아니라 **`~/Projects/CPIA`**.

| 단계 | 결과 |
|------|------|
| ④ 복원 검증 | PG 25 테이블 row count · Chroma (`daily_activities` 1843, `wbs_master` 204) manifest 와 전부 일치 |
| `.env` 로딩 | compose 가 루트 `.env` 를 못 읽던 문제 → `--env-file .env` 명시 (`ae82e9c`) |
| `/tasks`·`/export` 빈 목록 | 마이그레이션과 무관. 목록 쿼리의 1년 윈도우가 `CURRENT_DATE` 기준이라 마지막 데이터(2025-09-25)가 2026-09-26 부터 밖으로 밀림 → 최신 `report_date` 기준으로 변경 (`aec595d`) |
| 외부 접속 | `cpia-cloudflared` 복구 → 기존 `cpia-tunnel` 재사용. DB·Chroma·Adminer 포트 `127.0.0.1` 바인딩 (`197fa74`) |
| DNS 전환 | `cpia.zoai.uk` 를 AWS A 레코드 → `cpia-tunnel` CNAME 으로 덮어씀. `cpia-pg.zoai.uk` 는 원래 tunnel CNAME |
| GitHub Actions | `build-web.yml` 은 GHCR 이미지 빌드만 하고 배포 대상이 없어 변경 불필요 |
| homelab 정리 | 구버전 이미지(`cpia/web`, `cpia/pipeline`) · 구 DB 안전덤프 · 구 `.env` 삭제 (2026-10-06) |

### 외부 접속 구성

```
cpia.zoai.uk     → Cloudflare → cpia-tunnel → cpia-cloudflared → http://cpia-web:5535
cpia-pg.zoai.uk  → Cloudflare → cpia-tunnel → cpia-cloudflared → tcp://cpia-postgres:5432
```

- tunnel ingress 는 Zero Trust 대시보드에서 관리 (remote-managed). 토큰은 루트 `.env` 의 `CLOUDFLARED_TOKEN`
  (cloudflared 로그인된 호스트에서 `cloudflared tunnel token cpia-tunnel` 로 조회).
- 팀원 DB 접속: `cloudflared access tcp --hostname cpia-pg.zoai.uk --url localhost:5532`. AWS IP 직접 접속은 더 이상 불가.

### DNS 롤백 (AWS 로 되돌릴 때)

Cloudflare DNS 에서 `cpia.zoai.uk` 를 A 레코드 `43.200.85.209` (Proxied) 로 되돌린다.
AWS 스택이 내려가 있으면 먼저 기동해야 하며, 10/1 이후 homelab 에 쌓인 데이터는 AWS 에 없다.

## 남은 작업

- [ ] AWS: 백업 이후 신규 쓰기 여부 대조 → CPIA 컨테이너 down (볼륨 유지) → 유예 후 서버 종료·반납
- [ ] 번들 `~/cpia_bundle_20261001_053334.tar.gz` — AWS 반납 후엔 유일한 사본. 외부 저장소로 이관 후 homelab 에서 삭제
