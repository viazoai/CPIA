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

```bash
ssh <AWS> "cat ~/cpia_bundle_<ts>.tar.gz" | ssh <HOMELAB> "cat > ~/cpia_bundle_<ts>.tar.gz"
```

전송 후 양쪽 SHA256 이 같은지 확인한다.

```bash
ssh <AWS>     "sha256sum ~/cpia_bundle_<ts>.tar.gz"
ssh <HOMELAB> "sha256sum ~/cpia_bundle_<ts>.tar.gz"
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

**AWS 서버는 ⑤ 확인이 끝날 때까지 끄지 않는다.** 문제가 생기면 AWS 쪽 스택을 그대로 계속 쓰면 된다
(`backup.sh` 의 freeze 는 백업 중에만 적용되고 끝나면 자동 재기동된다).

homelab 복원이 꼬였을 때 다시 시도하려면:

```bash
bash ~/cpia/scripts/purge_old_stack.sh --yes --delete-code ~/cpia_dummy  # 컨테이너·볼륨만 정리
bash ~/cpia/scripts/restore.sh --from-git ~/cpia_bundle_<ts>.tar.gz ~/cpia
```

## 이번 범위 밖

- 외부 접속 (도메인, nginx-proxy-manager 라우팅, Cloudflare Tunnel) 재설정
- GitHub Actions 배포 워크플로(`.github/workflows/build-web.yml`) 의 배포 대상 변경
- AWS 서버 종료·반납

위 ⑤ 까지 끝나고 내부 IP 접속이 확인된 뒤 별도로 진행한다.
