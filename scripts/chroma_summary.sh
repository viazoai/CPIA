#!/usr/bin/env bash
# ============================================================
# ChromaDB 컬렉션별 문서 수를 "name=count" 형태로 출력.
# 마이그레이션 전/후 데이터 대조(manifest)에 사용한다.
#
# 사용법: bash scripts/chroma_summary.sh [포트]   # 기본 5533
# ============================================================
set -euo pipefail

PORT="${1:-5533}"
BASE="http://localhost:${PORT}/api/v1"

COLLECTIONS=$(curl -fsS --max-time 10 "${BASE}/collections") || {
  echo "(chroma 응답 없음: ${BASE})"
  exit 0
}

# id, name 추출 (python3 로 JSON 파싱 — jq 미설치 환경 대비)
echo "${COLLECTIONS}" | python3 -c '
import json, sys
for c in json.load(sys.stdin):
    print(c["id"] + "\t" + c["name"])
' | while IFS=$'\t' read -r cid cname; do
  cnt=$(curl -fsS --max-time 10 "${BASE}/collections/${cid}/count" 2>/dev/null || echo "?")
  echo "${cname}=${cnt}"
done | sort
