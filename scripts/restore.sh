#!/usr/bin/env bash
# ============================================================
# CPIA 마이그레이션 복원 스크립트 (대상 서버에서 실행)
#
# 사전 준비 (대상 서버):
#   - Docker + Docker Compose v2, git 설치
#   - 구버전 스택 정리 완료:  bash scripts/purge_old_stack.sh
#   - 번들 파일 전송 완료:    ~/cpia_bundle_YYYYMMDD_HHMMSS.tar.gz
#
# 사용법:
#   bash restore.sh [옵션] <bundle.tar.gz> [설치_경로]
#
# 옵션:
#   --from-git       코드는 이미 git clone 돼 있다고 보고 코드 복원을 건너뜀
#                    (번들을 --no-code 로 떴을 때 반드시 사용)
#   --pass <비번>    .env 복호화 비밀번호 (생략 시 프롬프트)
#   --no-build       이미지 pull 실패해도 로컬 빌드를 시도하지 않음
#   -h, --help       도움말
#
# 기본 설치 경로: $HOME/cpia
# ============================================================
set -euo pipefail

BUNDLE=""
INSTALL_ROOT=""
FROM_GIT=0
DEC_PASS=""
ALLOW_BUILD=1

usage() { sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --from-git)  FROM_GIT=1; shift ;;
    --pass)      DEC_PASS="${2:-}"; shift 2 ;;
    --no-build)  ALLOW_BUILD=0; shift ;;
    -h|--help)   usage ;;
    -*)          echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
    *)           if [ -z "${BUNDLE}" ]; then BUNDLE="$1"; else INSTALL_ROOT="$1"; fi; shift ;;
  esac
done

INSTALL_ROOT="${INSTALL_ROOT:-$HOME/cpia}"

if [ -z "${BUNDLE}" ] || [ ! -f "${BUNDLE}" ]; then
  echo "ERROR: 번들 파일을 찾을 수 없습니다." >&2
  echo "사용법: $0 [--from-git] <bundle.tar.gz> [설치_경로]" >&2
  exit 1
fi

echo "======================================"
echo " CPIA 복원 시작"
echo " 번들: ${BUNDLE}"
echo " 설치 경로: ${INSTALL_ROOT}"
echo " 코드 출처: $([ ${FROM_GIT} -eq 1 ] && echo 'git clone (이미 준비됨)' || echo '번들 내 code.tar.gz')"
echo "======================================"

# ----------------------------------------------------------
# 0. 번들 압축 해제
# ----------------------------------------------------------
echo ""
echo "[0/7] 번들 압축 해제..."
WORK_DIR=$(mktemp -d)
trap 'rm -rf "${WORK_DIR}"' EXIT
tar -xzf "${BUNDLE}" -C "${WORK_DIR}"
BACKUP_DIR=$(find "${WORK_DIR}" -mindepth 1 -maxdepth 1 -type d | head -1)
echo "   백업 디렉토리: ${BACKUP_DIR}"

if [ -f "${BACKUP_DIR}/manifest.txt" ]; then
  echo "   원본: $(grep '^source_host=' "${BACKUP_DIR}/manifest.txt" | cut -d= -f2)" \
       "@ $(grep '^git_commit=' "${BACKUP_DIR}/manifest.txt" | cut -d= -f2 | cut -c1-8)"
fi

# ----------------------------------------------------------
# 1. 소스 코드 준비
# ----------------------------------------------------------
echo ""
echo "[1/7] 소스 코드 준비..."
if [ ${FROM_GIT} -eq 1 ]; then
  if [ ! -f "${INSTALL_ROOT}/infra/docker-compose.yml" ]; then
    echo "   ERROR: ${INSTALL_ROOT} 가 CPIA 레포가 아닙니다 (infra/docker-compose.yml 없음)." >&2
    echo "          먼저 clone 하세요: git clone https://github.com/viazoai/CPIA ${INSTALL_ROOT}" >&2
    exit 1
  fi
  echo "   git clone 사용 — 코드 복원 생략"
  echo "   현재 커밋: $(git -C "${INSTALL_ROOT}" log -1 --format='%h %s' 2>/dev/null || echo '?')"

  # 번들을 뜬 시점의 커밋과 다르면 경고
  if [ -f "${BACKUP_DIR}/manifest.txt" ]; then
    SRC_COMMIT=$(grep '^git_commit=' "${BACKUP_DIR}/manifest.txt" | cut -d= -f2)
    DST_COMMIT=$(git -C "${INSTALL_ROOT}" rev-parse HEAD 2>/dev/null || echo "?")
    if [ "${SRC_COMMIT}" != "${DST_COMMIT}" ] && [ "${SRC_COMMIT}" != "?" ]; then
      echo "   ⚠ 백업 시점 커밋(${SRC_COMMIT:0:8})과 다릅니다 → git pull 로 맞추는 것을 권장"
    fi
  fi
elif [ -s "${BACKUP_DIR}/code.tar.gz" ]; then
  PARENT_DIR=$(dirname "${INSTALL_ROOT}")
  mkdir -p "${PARENT_DIR}"
  tar -xzf "${BACKUP_DIR}/code.tar.gz" -C "${PARENT_DIR}"
  EXTRACTED="${PARENT_DIR}/cpia"
  if [ -d "${EXTRACTED}" ] && [ "${EXTRACTED}" != "${INSTALL_ROOT}" ]; then
    mv "${EXTRACTED}" "${INSTALL_ROOT}"
  fi
  echo "   → ${INSTALL_ROOT}"
else
  echo "   ERROR: 번들에 code.tar.gz 가 없습니다. --from-git 로 실행하세요." >&2
  exit 1
fi

# ----------------------------------------------------------
# 2. .env 복원 (암호화된 경우 복호화)
# ----------------------------------------------------------
echo ""
echo "[2/7] .env 복원..."
if [ -f "${BACKUP_DIR}/env.enc" ]; then
  if [ -z "${DEC_PASS}" ]; then
    read -rsp "  .env 복호화 비밀번호 입력: " DEC_PASS
    echo ""
  fi
  openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:${DEC_PASS}" \
    -in "${BACKUP_DIR}/env.enc" \
    -out "${INSTALL_ROOT}/.env"
  chmod 600 "${INSTALL_ROOT}/.env"
  echo "   → .env 복호화 완료"
else
  echo "   env.enc 없음 — .env 를 직접 준비해야 합니다."
  cp "${INSTALL_ROOT}/.env.example" "${INSTALL_ROOT}/.env" 2>/dev/null || true
fi

# compose 는 .env 를 '현재 작업 디렉토리'가 아니라 compose 파일이 있는 폴더(infra/)에서
# 찾는다. AWS 는 infra/.env -> ../.env 심볼릭 링크로 우회했지만 그 링크는 .gitignore 에
# 걸려 clone 에 포함되지 않는다 → --env-file 로 명시해 링크 의존을 없앤다.
cd "${INSTALL_ROOT}"
compose() { docker compose --env-file "${INSTALL_ROOT}/.env" -f infra/docker-compose.yml "$@"; }

# make 를 쓸 때도 동작하도록 심볼릭 링크를 보강해 둔다 (이미 있으면 건너뜀).
[ -e "${INSTALL_ROOT}/infra/.env" ] || ln -s ../.env "${INSTALL_ROOT}/infra/.env"

# shellcheck disable=SC1091
source "${INSTALL_ROOT}/.env" 2>/dev/null || true
PG_USER="${POSTGRES_USER:-cpia}"
PG_DB="${POSTGRES_DB:-cpia}"
CHROMA_LOCAL_PORT="${CHROMA_PORT:-5533}"

# ----------------------------------------------------------
# 3. DB 컨테이너 기동
# ----------------------------------------------------------
echo ""
echo "[3/7] DB 컨테이너 기동..."
docker network inspect npm >/dev/null 2>&1 || docker network create npm >/dev/null

compose up -d postgres chroma
echo "   PostgreSQL · ChromaDB healthcheck 대기 중..."

for i in $(seq 1 24); do
  PG_OK=$(docker inspect --format='{{.State.Health.Status}}' cpia-postgres 2>/dev/null || echo "missing")
  CH_OK=$(docker inspect --format='{{.State.Health.Status}}' cpia-chroma   2>/dev/null || echo "missing")
  if [ "${PG_OK}" = "healthy" ] && [ "${CH_OK}" = "healthy" ]; then
    echo "   DB 준비 완료"
    break
  fi
  [ "$i" = "24" ] && { echo "   ERROR: DB 기동 실패 (PG=${PG_OK} Chroma=${CH_OK})" >&2; exit 1; }
  echo "   대기 중... (${i}/24) PG=${PG_OK} Chroma=${CH_OK}"
  sleep 5
done

# ----------------------------------------------------------
# 4. PostgreSQL 데이터 복원
#    DROP DATABASE 는 자기 자신에 접속한 상태라 실패한다 → 스키마 단위로 초기화.
# ----------------------------------------------------------
echo ""
echo "[4/7] PostgreSQL 데이터 복원..."
docker exec -i cpia-postgres psql -U "${PG_USER}" -d "${PG_DB}" -v ON_ERROR_STOP=1 -q -c \
  "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO ${PG_USER};"

docker exec -i cpia-postgres pg_restore \
  -U "${PG_USER}" \
  -d "${PG_DB}" \
  --no-owner \
  --role="${PG_USER}" \
  < "${BACKUP_DIR}/postgres.dump"
echo "   → PostgreSQL 복원 완료"

# ----------------------------------------------------------
# 5. ChromaDB 데이터 복원
# ----------------------------------------------------------
echo ""
echo "[5/7] ChromaDB 데이터 복원..."
docker stop cpia-chroma >/dev/null 2>&1 || true

# 볼륨은 root 소유라 호스트에서 직접 건드리면 sudo 가 필요하다.
# 임시 컨테이너 안에서 처리해 sudo 의존을 없앤다 (비밀번호 프롬프트로 멈추는 것 방지).
docker run --rm \
  -v cpia_chroma_data:/vol \
  -v "${BACKUP_DIR}":/backup:ro \
  alpine:3.20 sh -c 'rm -rf /vol/..?* /vol/.[!.]* /vol/* 2>/dev/null; tar -xzf /backup/chroma.tar.gz -C /vol'

docker start cpia-chroma >/dev/null
echo "   Chroma 재기동 대기..."
for i in $(seq 1 12); do
  CH_OK=$(docker inspect --format='{{.State.Health.Status}}' cpia-chroma 2>/dev/null || echo "missing")
  [ "${CH_OK}" = "healthy" ] && break
  sleep 5
done
echo "   → ChromaDB 복원 완료 (${CH_OK})"

# ----------------------------------------------------------
# 6. data/ 디렉토리 복원
# ----------------------------------------------------------
echo ""
echo "[6/7] data/ 디렉토리 복원..."
if [ -s "${BACKUP_DIR}/data.tar.gz" ]; then
  tar -xzf "${BACKUP_DIR}/data.tar.gz" -C "${INSTALL_ROOT}"
  echo "   → data/ 복원 완료"
else
  mkdir -p "${INSTALL_ROOT}/data"
  echo "   data.tar.gz 비어있음 — 빈 data/ 생성"
fi

# ----------------------------------------------------------
# 7. 앱 이미지 준비 + 전체 스택 기동
# ----------------------------------------------------------
echo ""
echo "[7/7] 앱 이미지 준비..."
if compose pull web pipeline 2>/dev/null; then
  echo "   → GHCR pull 성공"
elif [ ${ALLOW_BUILD} -eq 1 ]; then
  echo "   GHCR pull 실패 (private 레지스트리 — docker login ghcr.io 미실행?)"
  echo "   → 로컬 빌드로 대체합니다. 몇 분 걸립니다."
  compose build web pipeline
else
  echo "   ERROR: 이미지 준비 실패. docker login ghcr.io 후 재시도하세요." >&2
  exit 1
fi

echo ""
echo "[+] 전체 스택 기동..."
compose up -d
sleep 8
docker ps --filter "name=^cpia-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# ----------------------------------------------------------
# 검증 — manifest 대조
# ----------------------------------------------------------
echo ""
echo "======================================"
echo " 검증: 원본 대비 데이터 일치 여부"
echo "======================================"

if [ -f "${BACKUP_DIR}/manifest.txt" ]; then
  NOW_PG=$(docker exec cpia-postgres psql -U "${PG_USER}" -d "${PG_DB}" -At -F'=' -c "
    SELECT table_name, (xpath('/row/cnt/text()', xml_count))[1]::text::bigint
    FROM (
      SELECT table_name,
             query_to_xml(format('SELECT count(*) AS cnt FROM %I.%I', table_schema, table_name),
                          false, true, '') AS xml_count
      FROM information_schema.tables
      WHERE table_schema='public' AND table_type='BASE TABLE'
    ) t ORDER BY table_name;" 2>/dev/null || echo "")

  SRC_PG=$(sed -n '/^## postgres row counts$/,/^$/p' "${BACKUP_DIR}/manifest.txt" | grep '=' || true)

  echo ""
  echo "— PostgreSQL row count —"
  if diff <(echo "${SRC_PG}" | sort) <(echo "${NOW_PG}" | sort) >/dev/null; then
    echo "   ✓ 전체 테이블 일치 ($(echo "${SRC_PG}" | grep -c '') 개 테이블)"
  else
    echo "   ⚠ 불일치 (좌: 원본 / 우: 복원본)"
    diff --side-by-side --suppress-common-lines \
      <(echo "${SRC_PG}" | sort) <(echo "${NOW_PG}" | sort) | sed 's/^/     /' || true
  fi

  echo ""
  echo "— ChromaDB 컬렉션 —"
  NOW_CH=$(bash "${INSTALL_ROOT}/scripts/chroma_summary.sh" "${CHROMA_LOCAL_PORT}" 2>/dev/null || echo "(수집 실패)")
  SRC_CH=$(sed -n '/^## chroma collections$/,$p' "${BACKUP_DIR}/manifest.txt" | grep '=' || true)
  if [ "$(echo "${SRC_CH}" | sort)" = "$(echo "${NOW_CH}" | sort)" ]; then
    echo "   ✓ 일치"
    echo "${NOW_CH}" | sed 's/^/     /'
  else
    echo "   ⚠ 불일치"
    echo "     원본  : $(echo "${SRC_CH}" | tr '\n' ' ')"
    echo "     복원본: $(echo "${NOW_CH}" | tr '\n' ' ')"
  fi
else
  echo "   manifest.txt 없음 — 자동 검증 생략 (구버전 번들)"
fi

echo ""
echo "======================================"
echo " 복원 완료!"
echo ""
echo " 접속 확인:"
echo "   대시보드:   http://<homelab-IP>:${WEB_PORT:-5535}"
echo "   파이프라인: http://<homelab-IP>:${PIPELINE_PORT:-5538}/docs"
echo "   Adminer:    http://<homelab-IP>:${ADMINER_PORT:-5534}"
echo ""
echo " 코드 변경 시 재배포: cd ${INSTALL_ROOT} && make build"
echo "======================================"
