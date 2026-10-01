#!/usr/bin/env bash
# ============================================================
# 구버전 CPIA 스택 정리 스크립트 (대상 서버 = homelab 에서 실행)
#
# 목적: 예전에 homelab 에서 돌리던 구버전 CPIA 를 제거해
#       AWS 에서 가져온 최신 스택을 깨끗하게 올릴 수 있게 한다.
#
# 제거 대상:
#   - cpia-* 컨테이너 (cpia-web, cpia-pipeline, cpia-postgres, cpia-chroma, cpia-adminer ...)
#   - cpia_* 볼륨   (cpia_postgres_data, cpia_chroma_data, cpia_web_dev_modules ...)
#   - 구 코드 디렉토리 → 기본은 <경로>.old-<timestamp> 로 rename (삭제 아님)
#
# 건드리지 않는 것: npm(nginx-proxy-manager) 등 cpia 접두사가 아닌 컨테이너·네트워크
#
# 사용법:
#   bash scripts/purge_old_stack.sh [옵션] [구_코드_경로]
#
# 옵션:
#   --delete-code         구 코드 디렉토리를 rename 대신 완전 삭제
#   --no-safety-dump      삭제 전 구 PostgreSQL 안전 덤프를 만들지 않음
#   --yes                 확인 프롬프트 생략 (비대화식)
#   -h, --help            도움말
#
# 기본 구 코드 경로: $HOME/cpia
# ============================================================
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OLD_ROOT=""
DELETE_CODE=0
SAFETY_DUMP=1
ASSUME_YES=0

usage() { sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --delete-code)    DELETE_CODE=1; shift ;;
    --no-safety-dump) SAFETY_DUMP=0; shift ;;
    --yes|-y)         ASSUME_YES=1; shift ;;
    -h|--help)        usage ;;
    -*)               echo "알 수 없는 옵션: $1" >&2; exit 1 ;;
    *)                OLD_ROOT="$1"; shift ;;
  esac
done

OLD_ROOT="${OLD_ROOT:-$HOME/cpia}"
SAFETY_DIR="${HOME}/cpia_old_safety_${TIMESTAMP}"

# ----------------------------------------------------------
# 1. 현황 조사
# ----------------------------------------------------------
echo "======================================"
echo " 구버전 CPIA 스택 정리"
echo " 대상 서버: $(hostname)"
echo "======================================"
echo ""
echo "[조사] 발견된 항목"
echo ""

CONTAINERS=$(docker ps -aq --filter "name=^cpia-" 2>/dev/null || true)
VOLUMES=$(docker volume ls -q --filter "name=^cpia_" 2>/dev/null || true)

echo "— 컨테이너 —"
if [ -n "${CONTAINERS}" ]; then
  docker ps -a --filter "name=^cpia-" --format "   {{.Names}}  ({{.Image}})  {{.Status}}"
else
  echo "   (없음)"
fi

echo ""
echo "— 볼륨 —"
if [ -n "${VOLUMES}" ]; then
  while read -r v; do
    [ -z "$v" ] && continue
    MP=$(docker volume inspect "$v" --format '{{.Mountpoint}}' 2>/dev/null || echo "")
    SZ=$(sudo du -sh "$MP" 2>/dev/null | cut -f1 || echo "?")
    echo "   ${v}  (${SZ})"
  done <<< "${VOLUMES}"
else
  echo "   (없음)"
fi

echo ""
echo "— 코드 디렉토리 —"
if [ -d "${OLD_ROOT}" ]; then
  echo "   ${OLD_ROOT}  ($(du -sh "${OLD_ROOT}" 2>/dev/null | cut -f1))"
  if [ -d "${OLD_ROOT}/.git" ]; then
    echo "     git: $(git -C "${OLD_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')" \
         "@ $(git -C "${OLD_ROOT}" log -1 --format='%h %ad %s' --date=short 2>/dev/null || echo '?')"
  fi
  if [ ${DELETE_CODE} -eq 1 ]; then
    echo "     → 완전 삭제됨 (--delete-code)"
  else
    echo "     → ${OLD_ROOT}.old-${TIMESTAMP} 로 rename (삭제 아님)"
  fi
else
  echo "   (없음: ${OLD_ROOT})"
fi

if [ -z "${CONTAINERS}" ] && [ -z "${VOLUMES}" ] && [ ! -d "${OLD_ROOT}" ]; then
  echo ""
  echo "정리할 구버전이 없습니다. 바로 clone·복원으로 진행하세요."
  exit 0
fi

# ----------------------------------------------------------
# 2. 확인
# ----------------------------------------------------------
echo ""
echo "======================================"
echo " 위 컨테이너와 볼륨이 영구 삭제됩니다."
[ ${SAFETY_DUMP} -eq 1 ] && echo " (삭제 전 구 PostgreSQL 안전 덤프를 ${SAFETY_DIR} 에 남깁니다)"
echo "======================================"

if [ ${ASSUME_YES} -ne 1 ]; then
  read -rp "진행하려면 DELETE 를 그대로 입력하세요: " CONFIRM
  if [ "${CONFIRM}" != "DELETE" ]; then
    echo "취소했습니다. 아무것도 변경되지 않았습니다."
    exit 1
  fi
fi

# ----------------------------------------------------------
# 3. 안전 덤프 (구 PostgreSQL 이 살아있을 때만)
# ----------------------------------------------------------
if [ ${SAFETY_DUMP} -eq 1 ]; then
  echo ""
  echo "[1/4] 구 PostgreSQL 안전 덤프..."
  if [ "$(docker inspect -f '{{.State.Running}}' cpia-postgres 2>/dev/null)" = "true" ]; then
    mkdir -p "${SAFETY_DIR}"
    OLD_PG_USER="${POSTGRES_USER:-cpia}"
    OLD_PG_DB="${POSTGRES_DB:-cpia}"
    if docker exec cpia-postgres pg_dump -U "${OLD_PG_USER}" -d "${OLD_PG_DB}" \
         --format=custom --compress=9 --no-password > "${SAFETY_DIR}/postgres_old.dump" 2>/dev/null; then
      echo "   → ${SAFETY_DIR}/postgres_old.dump ($(du -sh "${SAFETY_DIR}/postgres_old.dump" | cut -f1))"
    else
      rm -f "${SAFETY_DIR}/postgres_old.dump"
      echo "   덤프 실패 (DB명/계정 불일치 가능) — 구버전이므로 그대로 진행합니다."
    fi
  else
    echo "   구 cpia-postgres 가 실행 중이 아님 — 스킵"
  fi
else
  echo ""
  echo "[1/4] 안전 덤프 건너뜀 (--no-safety-dump)"
fi

# ----------------------------------------------------------
# 4. 컨테이너 제거
# ----------------------------------------------------------
echo ""
echo "[2/4] 컨테이너 제거..."
if [ -n "${CONTAINERS}" ]; then
  # shellcheck disable=SC2086
  docker rm -f ${CONTAINERS} >/dev/null
  echo "   → $(echo "${CONTAINERS}" | grep -c '') 개 제거 완료"
else
  echo "   (없음)"
fi

# ----------------------------------------------------------
# 5. 볼륨 제거
# ----------------------------------------------------------
echo ""
echo "[3/4] 볼륨 제거..."
if [ -n "${VOLUMES}" ]; then
  while read -r v; do
    [ -z "$v" ] && continue
    docker volume rm "$v" >/dev/null && echo "   제거: $v"
  done <<< "${VOLUMES}"
else
  echo "   (없음)"
fi

# ----------------------------------------------------------
# 6. 코드 디렉토리 처리
# ----------------------------------------------------------
echo ""
echo "[4/4] 구 코드 디렉토리 처리..."
if [ -d "${OLD_ROOT}" ]; then
  if [ ${DELETE_CODE} -eq 1 ]; then
    rm -rf "${OLD_ROOT:?}"
    echo "   → 삭제 완료: ${OLD_ROOT}"
  else
    mv "${OLD_ROOT}" "${OLD_ROOT}.old-${TIMESTAMP}"
    echo "   → rename: ${OLD_ROOT}.old-${TIMESTAMP}"
    echo "     (복원 검증 끝나면 rm -rf ${OLD_ROOT}.old-${TIMESTAMP})"
  fi
else
  echo "   (없음)"
fi

# ----------------------------------------------------------
# 7. 포트 점유 확인
# ----------------------------------------------------------
echo ""
echo "[확인] CPIA 포트 점유 상태 (5532~5538)"
BUSY=0
for p in 5532 5533 5534 5535 5536 5537 5538; do
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$"; then
    echo "   :${p}  사용 중  ← 확인 필요"
    BUSY=1
  else
    echo "   :${p}  비어 있음"
  fi
done

echo ""
echo "======================================"
echo " 정리 완료"
if [ ${BUSY} -eq 1 ]; then
  echo " ⚠ 아직 사용 중인 포트가 있습니다. 위 목록을 확인하세요."
  echo "   확인: sudo ss -ltnp | grep -E '553[2-8]'"
fi
echo ""
echo " 다음 단계:"
echo "   1) git clone https://github.com/viazoai/CPIA ${OLD_ROOT}"
echo "   2) bash ${OLD_ROOT}/scripts/restore.sh --from-git ~/cpia_bundle_<ts>.tar.gz ${OLD_ROOT}"
echo "======================================"
