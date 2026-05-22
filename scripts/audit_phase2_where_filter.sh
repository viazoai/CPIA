#!/usr/bin/env bash
# Phase 2 — `ma.trade IN ('건축', '토목')` 패턴이 7 파일 / 11 hit 모두 적용됐는지 검증.
# plan 원안의 backreference regex 는 BSD grep 에서 invalid escape — 단순 substring 으로 변경.
# macOS bash 3.2 호환 (associative array X) — parallel array 사용.
# 모든 매칭 위치가 alias `ma` 사용 (plan B1~B5 가 alias 통일), false positive 없음.
set -eo pipefail
cd "$(dirname "$0")/.."

FILES=(
  "web/lib/transforms.ts"
  "web/app/api/mock/agent-tasks/route.ts"
  "web/app/api/mock/review/route.ts"
  "web/app/api/mock/consolidated/route.ts"
  "web/lib/fixtures.ts"
  "pipeline/agents/optimizer/view_builder.py"
  "scripts/backfill_chroma_daily_activities.py"
)
NEEDS=(5 1 1 1 1 1 1)

fail=0
total=0
for i in "${!FILES[@]}"; do
  f="${FILES[$i]}"
  need="${NEEDS[$i]}"
  if [ ! -f "$f" ]; then
    hits=0
  else
    hits=$(grep -cE "ma\.trade IN[[:space:]]*\(" "$f" 2>/dev/null || true)
    hits="${hits:-0}"
  fi
  if [ "${hits:-0}" -lt "$need" ]; then
    echo "FAIL $f: hits=${hits} need=$need"
    fail=1
  else
    echo "OK   $f: hits=${hits} (need=${need})"
  fi
  total=$((total + ${hits:-0}))
done

[ $fail -eq 0 ] || exit 1
echo "verified: ${total} hit (7 파일) 모두 'ma.trade IN' 필터 적용"
