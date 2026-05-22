#!/usr/bin/env bash
# Phase 2 L2 rollback — daily_reports.jsonb 9 컬럼만 backup_20260521 에서 복사.
# DB row count 무변경 (UPDATE 만, TRUNCATE 없음).
# 정상 흐름에선 호출 안 함. 시연 직전 장애 / Phase E 산출물 거부 시 사용.
set -eo pipefail
cd "$(dirname "$0")/.."

# 1. snapshot verify — backup_20260521 무변화 확인
PYTHONPATH=. pipeline/.venv/bin/python scripts/audit_phase2_snapshot.py --verify

# 2. confirm
read -p "rollback 진행? (yes/no): " ans
[ "$ans" = "yes" ] || { echo "취소"; exit 1; }

# .env.local 의 POSTGRES_URL 로드
set -a
. .env.local
set +a

# 3. UPDATE daily_reports.jsonb 9 컬럼 (FK 위반 0)
psql "$POSTGRES_URL" -c "
UPDATE public.daily_reports dr SET
  kpi_jsonb            = b.kpi_jsonb,
  productivity_jsonb   = b.productivity_jsonb,
  contractor_bars_jsonb= b.contractor_bars_jsonb,
  trade_bars_jsonb     = b.trade_bars_jsonb,
  quadrant_jsonb       = b.quadrant_jsonb,
  wp_summary_jsonb     = b.wp_summary_jsonb,
  optimizer_view_jsonb = b.optimizer_view_jsonb,
  scenarios_jsonb      = b.scenarios_jsonb,
  s_curve_jsonb        = b.s_curve_jsonb
FROM backup_20260521.daily_reports b
WHERE dr.run_id = b.run_id;
"

# 4. ChromaDB rollback — backfill_v2 만 삭제 (synthetic_v2 보존)
PYTHONPATH=. pipeline/.venv/bin/python -c "
import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path('.env.local'))
from pipeline.chroma_client import ChromaClient
c = ChromaClient(host=os.environ['CHROMA_HOST'], port=int(os.environ['CHROMA_PORT']))
col = c.client.get_collection('daily_activities')
col.delete(where={'run_id': 'backfill_v2'})
print('chroma backfill_v2 삭제 완료')
"

echo "rollback 완료"
