# Task 26 Azure Quota Dry-run (2026-05-28)

**측정 대상:** 7/1 1일 backfill chain (seed → optimizer LLM → views_v2)

## Timing

| Stage | Time (s) | Note |
|---|---:|---|
| seed_dummy_year (`--start 2025-07-01 --end 2025-07-01 --trades 건축 토목`) | 5 | mapper_activities 82건, forecasts 21건 |
| backfill_optimizer_advice_llm (`--start-date 2025-07-01 --end-date 2025-07-01`) | 191 | mapped 149 rows, LLM-driven advice 21건 (cold_start 0) |
| backfill_daily_report_views_v2 (`--start-date 2025-07-01 --end-date 2025-07-01 --with-summary`) | 8 | site_summary_text LLM 1회 |
| **1일 총합** | **~204 (3.4 분)** | |
| **86일 추정** | **~17,500s ≈ 4.9 시간** | |

## Verdict

**녹색 (< 15 분 / 일) → 풀 86일 backfill 진행.** Task 27-29 plan 그대로.

시연 마감 D-8 (2026-06-05 목) buffer 충분.

## V10 결과 품질 검증

`scripts/verify_backfill_passing.py` (polymorphic fix 후) 6/6 PASS:

| Check | Result |
|---|---|
| diagnosis 평균 ≥ 50자 + placeholder 0% | n=29, avg=235.1자, placeholder 0건 |
| degradation_cases 4필드 ≥ 90% | total=121, complete 100% |
| recommendations text empty 0% | total=100, empty 0건 |
| details 6칸 non-'-' ≥ 80% | total=294, non_dash 100% |
| quadrant ↔ by_wp wp_id 교집합 ≥ 80% | union=42, intersect 100% |
| delay_days 분포 (음수+양수+0) | neg=15, pos=26, zero=1 |

## V10 sample 산출물

**광건 · 수장공사 (마감 카테고리):**

- **diagnosis (235자)**: "현재 공정은 91일 앞서 있으며 누적 진척 지연도 없지만, MH 부족이 156,003시간으로 크게 벌어져 있어 오늘 자재 미입고로 드러난 생산성 저하는 단순 정체 여부를 별도로 판단해야 합니다. 마감 특성상 선행 면의 건조·함수율 제약이 실제 병목인지, 아니면 자재 지연으로 한 면에 인원이 몰려 단위 생산성이 눌린 상황인지 즉시 가르는 것이 핵심입니다."
  - → mh_gap 인용 + 마감 trade_frame 인용 (G6/G8 가드 작동)

- **rec[0]**: `{"rank": 1, "keyword": "건조대기 판별", "action": "자재 입고 직후 반장에게 선행 면의 건조 여부를 바로 대조하도록 지시하세요.", "reason": "마감은 선행 공종 건조 대기와 자체 생산성의 구분이 핵심이라는 trade_frame 내용이 있어 입고 즉시 면 상태를 가르면 지연 원인을 바로 잡을 수 있습니다."}`
  - → V10 keyword/action/reason 3 필드 schema 완벽 작동
  - → keyword 5~10자 ("건조대기 판별" 7자)
  - → 조건 trigger ("자재 입고 직후") G1 가드
  - → trade_frame 인용 reason G8 가드

- **site_summary_text**: "기준일 시점 진척률은 26.3%로 계획 67.3% 대비 40.9%p 뒤처져 현 흐름이면 완공이 계획 대비 D+10일 지연될 전망입니다. AI 권..."
  - → 1단락 진척 + 2단락 AI 권고 효과 형식 (G8 카테고리 고유 액션 인용)

## 다음

- Task 27: 7월 풀 backfill (7/1~7/31, 31일) + gate_month(7)
- Task 28: 8월 풀 backfill (8/1~8/31)
- Task 29: 9월 풀 backfill (9/1~9/24, 24일)
- Task 30: 종합 retry + 시연 D-1 검증
