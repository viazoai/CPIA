#!/usr/bin/env bash
# ============================================================
# CPIA 마이그레이션 백업 스크립트 (소스 서버에서 실행)
#
# 생성 파일:
#   cpia_backup_YYYYMMDD_HHMMSS/
#     ├── manifest.txt       — git 커밋·테이블 row count 등 검증용 메타데이터
#     ├── code.tar.gz        — 소스 코드 (--no-code 시 생략)
#     ├── postgres.dump      — pg_dump (custom format, 압축 포함)
#     ├── chroma.tar.gz      — ChromaDB 볼륨 데이터
#     ├── data.tar.gz        — data/ 디렉토리 (업로드·합성 이력)
#     └── env.enc            — .env AES-256 암호화 (비밀번호 별도 전달)
#
# 사용법:
#   cd /home/ubuntu/cpia
#   bash scripts/backup.sh [옵션] [출력_디렉토리]
#
# 옵션:
#   --no-code        소스 코드 tar 생략 (코드는 GitHub 경유로 옮길 때)
#   --no-freeze      백업 중 web/pipeline 컨테이너를 멈추지 않음
#                    (기본은 freeze — 쓰기 중 덤프로 인한 불일치 방지)
#   --pass <비번>    .env 암호화 비밀번호 (생략 시 프롬프트)
#   -h, --help       도움말
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

INCLUDE_CODE=1
FREEZE=1
ENC_PASS=""
OUT_DIR=""

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --no-code)   INCLUDE_CODE=0; shift ;;
    --no-freeze) FREEZE=0; shift ;;
    --pass)      ENC_PASS="${2:-}"; shift 2 ;;
    -h|--help)   usage ;;
    -*)          echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
    *)           OUT_DIR="$1"; shift ;;
  esac
done

OUT_DIR="${OUT_DIR:-$HOME/cpia_backup_${TIMESTAMP}}"

# .env 에서 접속 정보 읽기
# shellcheck disable=SC1091
source "${REPO_ROOT}/.env" 2>/dev/null || true
PG_USER="${POSTGRES_USER:-cpia}"
PG_DB="${POSTGRES_DB:-cpia}"
CHROMA_LOCAL_PORT="${CHROMA_PORT:-5533}"

echo "======================================"
echo " CPIA 백업 시작: ${TIMESTAMP}"
echo " 출력 경로: ${OUT_DIR}"
echo " 코드 포함: $([ ${INCLUDE_CODE} -eq 1 ] && echo 'yes' || echo 'no (GitHub 경유)')"
echo " 쓰기 freeze: $([ ${FREEZE} -eq 1 ] && echo 'yes' || echo 'no')"
echo "======================================"

# 필수 컨테이너 확인
for c in cpia-postgres cpia-chroma; do
  docker inspect "$c" >/dev/null 2>&1 || { echo "ERROR: 컨테이너 ${c} 가 없습니다." >&2; exit 1; }
done

mkdir -p "${OUT_DIR}"

# ----------------------------------------------------------
# 0. 앱 컨테이너 freeze (DB 쓰기 중지)
# ----------------------------------------------------------
FROZEN=()
CHROMA_STOPPED=0
cleanup_restart() {
  # 스크립트가 중간에 죽어도 멈춰둔 컨테이너는 반드시 되살린다.
  if [ ${CHROMA_STOPPED} -eq 1 ]; then
    echo ""
    echo "[~] cpia-chroma 재기동"
    docker start cpia-chroma >/dev/null 2>&1 || true
    CHROMA_STOPPED=0
  fi
  if [ ${#FROZEN[@]} -gt 0 ]; then
    echo ""
    echo "[~] 앱 컨테이너 재기동: ${FROZEN[*]}"
    docker start "${FROZEN[@]}" >/dev/null 2>&1 || true
    FROZEN=()
  fi
}
trap cleanup_restart EXIT

if [ ${FREEZE} -eq 1 ]; then
  echo ""
  echo "[0] 앱 컨테이너 일시 중지 (DB 쓰기 차단)..."
  for c in cpia-web cpia-pipeline; do
    if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
      docker stop "$c" >/dev/null
      FROZEN+=("$c")
      echo "   중지: $c"
    fi
  done
  [ ${#FROZEN[@]} -eq 0 ] && echo "   (중지할 컨테이너 없음)"
fi

# ----------------------------------------------------------
# 1. 소스 코드 tar
# ----------------------------------------------------------
echo ""
if [ ${INCLUDE_CODE} -eq 1 ]; then
  echo "[1] 소스 코드 압축 중..."
  tar -czf "${OUT_DIR}/code.tar.gz" \
    -C "${REPO_ROOT}/.." \
    --exclude="cpia/web/node_modules" \
    --exclude="cpia/web/.next" \
    --exclude="cpia/pipeline/.venv" \
    --exclude="cpia/pipeline/__pycache__" \
    --exclude="cpia/pipeline/**/__pycache__" \
    --exclude="cpia/.git" \
    --exclude="cpia/data/synthetic_history" \
    "$(basename "${REPO_ROOT}")"
  echo "   → code.tar.gz ($(du -sh "${OUT_DIR}/code.tar.gz" | cut -f1))"
else
  echo "[1] 소스 코드 압축 건너뜀 (--no-code) — GitHub 에서 clone 할 것"
fi

# ----------------------------------------------------------
# 2. PostgreSQL 덤프 (컨테이너 내부 pg_dump)
# ----------------------------------------------------------
echo ""
echo "[2] PostgreSQL 덤프 중..."
docker exec cpia-postgres pg_dump \
  -U "${PG_USER}" \
  -d "${PG_DB}" \
  --format=custom \
  --compress=9 \
  --no-password \
  > "${OUT_DIR}/postgres.dump"
echo "   → postgres.dump ($(du -sh "${OUT_DIR}/postgres.dump" | cut -f1))"

# ----------------------------------------------------------
# 3. ChromaDB 볼륨 스냅샷
#    Chroma 는 SQLite 기반 → 쓰기 중에 tar 하면 corruption 위험.
#    컨테이너를 잠깐 멈추고 tar → 재기동.
# ----------------------------------------------------------
echo ""
echo "[3] ChromaDB 볼륨 백업 중..."

# 백업 전에 컬렉션 현황을 기록 (복원 후 대조용)
CHROMA_SUMMARY=$("${REPO_ROOT}/scripts/chroma_summary.sh" "${CHROMA_LOCAL_PORT}" 2>/dev/null || echo "(수집 실패)")

echo "   Chroma 컨테이너 일시 중지..."
docker stop cpia-chroma >/dev/null
CHROMA_STOPPED=1

CHROMA_VOLUME_PATH=$(docker volume inspect cpia_chroma_data --format '{{ .Mountpoint }}')
sudo tar -czf "${OUT_DIR}/chroma.tar.gz" -C "${CHROMA_VOLUME_PATH}" . 2>/dev/null \
  || tar -czf "${OUT_DIR}/chroma.tar.gz" -C "${CHROMA_VOLUME_PATH}" .
sudo chown "$(id -u):$(id -g)" "${OUT_DIR}/chroma.tar.gz" 2>/dev/null || true

echo "   Chroma 컨테이너 재기동..."
docker start cpia-chroma >/dev/null
CHROMA_STOPPED=0
echo "   → chroma.tar.gz ($(du -sh "${OUT_DIR}/chroma.tar.gz" | cut -f1))"

# ----------------------------------------------------------
# 4. data/ 디렉토리 (업로드 파일 · synthetic 이력)
# ----------------------------------------------------------
echo ""
echo "[4] data/ 디렉토리 압축 중..."
if [ -d "${REPO_ROOT}/data" ]; then
  tar -czf "${OUT_DIR}/data.tar.gz" -C "${REPO_ROOT}" data
  echo "   → data.tar.gz ($(du -sh "${OUT_DIR}/data.tar.gz" | cut -f1))"
else
  echo "   data/ 디렉토리 없음, 스킵"
  : > "${OUT_DIR}/data.tar.gz"
fi

# ----------------------------------------------------------
# 5. manifest — 복원 후 대조용 메타데이터
# ----------------------------------------------------------
echo ""
echo "[5] manifest 생성 중..."
{
  echo "# CPIA 마이그레이션 manifest"
  echo "timestamp=${TIMESTAMP}"
  echo "source_host=$(hostname)"
  echo "include_code=${INCLUDE_CODE}"
  echo "git_branch=$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  echo "git_commit=$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo '?')"
  echo "pg_user=${PG_USER}"
  echo "pg_db=${PG_DB}"
  echo ""
  echo "## postgres row counts"
  docker exec cpia-postgres psql -U "${PG_USER}" -d "${PG_DB}" -At -F'=' -c "
    SELECT table_name, (xpath('/row/cnt/text()', xml_count))[1]::text::bigint
    FROM (
      SELECT table_name,
             query_to_xml(format('SELECT count(*) AS cnt FROM %I.%I', table_schema, table_name),
                          false, true, '') AS xml_count
      FROM information_schema.tables
      WHERE table_schema='public' AND table_type='BASE TABLE'
    ) t ORDER BY table_name;" 2>/dev/null || echo "(수집 실패)"
  echo ""
  echo "## chroma collections"
  echo "${CHROMA_SUMMARY}"
} > "${OUT_DIR}/manifest.txt"
echo "   → manifest.txt ($(grep -c '' "${OUT_DIR}/manifest.txt") 줄)"

# ----------------------------------------------------------
# 6. .env 암호화 저장
# ----------------------------------------------------------
echo ""
echo "[6] .env 암호화 저장..."
if [ -f "${REPO_ROOT}/.env" ]; then
  if [ -z "${ENC_PASS}" ]; then
    read -rsp "  .env 암호화 비밀번호 (복원 시 필요): " ENC_PASS
    echo ""
  fi
  openssl enc -aes-256-cbc -pbkdf2 -pass "pass:${ENC_PASS}" \
    -in "${REPO_ROOT}/.env" \
    -out "${OUT_DIR}/env.enc"
  echo "   → env.enc 저장 완료 (비밀번호를 별도 경로로 전달하세요)"
else
  echo "   .env 없음, 스킵"
fi

# ----------------------------------------------------------
# 최종 단일 tar 묶음
# ----------------------------------------------------------
echo ""
echo "[+] 전체 묶음 tar 생성 중..."
BUNDLE="${HOME}/cpia_bundle_${TIMESTAMP}.tar.gz"
tar -czf "${BUNDLE}" -C "$(dirname "${OUT_DIR}")" "$(basename "${OUT_DIR}")"

echo ""
echo "======================================"
echo " 백업 완료!"
echo " 단일 번들: ${BUNDLE}"
echo " 크기: $(du -sh "${BUNDLE}" | cut -f1)"
echo " SHA256: $(sha256sum "${BUNDLE}" | cut -d' ' -f1)"
echo ""
echo " 내 PC 에서 homelab 으로 중계 (디스크에 남기지 않음):"
echo "   ssh <AWS> \"cat ${BUNDLE}\" | ssh <HOMELAB> \"cat > ~/$(basename "${BUNDLE}")\""
echo "======================================"
