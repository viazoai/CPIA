# End-to-End 예시 시뮬레이션 — 남웅건설 거푸집 케이스

> **목적**: `state.md` 의 스키마 결정 (Parser LLM 단일 호출 / Mapper RAG + MH 분배 / Forecaster Plan+RAG 이중 비교) 이 실 작업일보·실 Master List 에서 어떻게 동작하는지 한 행 사이클 통과시켜 보여줌. 검토·합의용.
>
> **방법**: 결정론 부분 (xlsx 파싱·Master List lookup·MH 비율 계산·Plan 생산성 계산) 은 실 코드로 실행해 출력 그대로 인용. LLM 응답 (Parser structured output / Mapper rerank / Opus 진단) 은 **`[가정]`** 라벨로 구분.
>
> **재현**: `uv run --with openpyxl /tmp/cpia_walkthrough.py` (스크립트는 같은 출력 보장. 인용은 그 출력 그대로)

---

## 시나리오

| 항목 | 값 | 출처 |
|---|---|---|
| 가상 오늘 (`state.date`) | `2025-01-10` | 시뮬용 (실 작업일보가 2025-09-25 라서 그 날짜로 잡으면 Master List 거푸집 Plan 이 모두 종료된 상태 — 시연용으로 1월로 이동) |
| 대상 업체 | 남웅건설 | PoC 범위 — `state.md` §4 |
| 대상 공종 | 건축 / 거푸집공사 / M2 | PoC 범위 |
| 가상 `today_qty` | 320 m² | 실 작업일보 R102 `금일실적=None` 이라 가상값 (9/25 실데이터는 99.8% 완료 상태로 today=None) |
| 가상 활성 후보 (Plan 일자 필터 적용 시) | 13개 모두 (필터 미적용) | `state.md` §5 의 Plan 일자 필터 미해결 → 일단 모든 거푸집 후보 표시 |

---

## PART A. INPUT — 실 작업일보 9/25 (남웅건설 행 추출)

스크립트가 `통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx` 의 시트1·4 에서 남웅건설 행만 forward-fill + 필터링한 결과:

### [시트1 — 1.출력인원 현황]

```
R68 | Dis='AR' | BP='남웅건설' | 조출=0  주간=11 연장= 0 야간=0 철야=0 | Total=11
R70 | Dis='AR' | BP='남웅건설' | 조출=0  주간=35 연장=23 야간=6 철야=6 | Total=70
```

→ 같은 회사가 두 줄로 분리 (FAB / CUB 사이트 또는 본사·하청 분리로 추정). **Parser LLM 이 처리해야 할 것**:
- `Dis='AR'` → `trade='건축'` 정규화 (state.md §3.3 의 검증된 매핑 표 활용)
- `BP='남웅건설'` (자연어, PH 코드 아님) → `company='남웅건설'`
- 두 행 인원 합산 → **Total = 81 명** (실값, Parser LLM 출력의 분모)

### [시트4 — 4.물량] (남웅건설 행 앞 8개)

```
R99  | Dis='건축' | BP='PH_X-001' | 업체='남웅건설' | work='버림틀 설치'     | unit=m   | total=315  | 오늘=None
R100 | Dis='건축' | BP='PH_X-001' | 업체='남웅건설' | work='버림 타설'       | unit=m3  | total=326  | 오늘=None
R101 | Dis='건축' | BP='PH_X-001' | 업체='남웅건설' | work='철근 배근'       | unit=ton | total=1350 | 오늘=None
R102 | Dis='건축' | BP='PH_X-001' | 업체='남웅건설' | work='기초 거푸집 설치' | unit=m2  | total=2135 | 오늘=None
R103 | Dis='건축' | BP='PH_X-001' | 업체='남웅건설' | work='기초 타설'       | unit=m3  | total=6024 | 오늘=None
...
```

→ 9/25 작업일보의 today 컬럼은 모두 `None` (1,193행 중 89.5% 가 None — `state.md` §1.1 today_qty 행 참조).
→ 시뮬 진행을 위해 R102 `기초 거푸집 설치` 행에 **`today_qty=320 m²` 라고 가정**.

---

## PART B. Parser — Sonnet 4.6 `with_structured_output(ParserOutput)`

### 입력 (LLM 프롬프트)

```
[검증된 약자 ↔ 한글 매핑]
  AR→건축 (19/19), ME→설비 (20/21), EL→전기 (10/11),
  UT→UT, IN→제어, CI→토목, TE→공통가설, 소방설비/소방전기 동일

[작업일보 원문 — raw_texts dict]
시트1 R68/R70 → 위 PART A 시트1 dump
시트4 R102    → 위 PART A 시트4 R102 dump

[지시] 각 작업일보 행을 Activity TypedDict 로 추출. trade 는 한글로,
       company 는 자연어 업체명으로, today_qty=None 행은 결과에서 제외.
       두 시트의 같은 업체 인원·물량 정보를 join.
```

### [가정] Parser LLM 출력 — `ParserOutput.activities[0]`

```python
{
    "wbs_activity_id": None,           # Mapper 전이라 비어있음
    "l5_disc":         None,
    "l6_main":         None,
    "l7_sub":          None,
    "l7_5_activity":   None,
    "sub_work_area":   None,
    "trade":           "건축",
    "company":         "남웅건설",
    "unit":            "M2",
    "today_qty":       320.0,                                       # 시뮬 가정값
    "work_content":    "기초 거푸집 설치",                          # 시트4 작업내용
    "conditions":      [],                                          # 9/25 명시 X
    "assigned_workers": 81.0,                                       # 시트1 합산값 (실)
    "worker_source":   "parsed",                                    # Parser 가 채움
    "plan_total_qty":  None,                                        # Mapper 전
    "plan_mh":         None,
    "requires_review": False,                                       # Mapper 전
}
```

→ 결정성 검증: `temperature=0` + structured output 이므로 동일 입력 반복 시 byte-level 동일해야 함 (`state.md` §3.4 게이트).

---

## PART C. Mapper — ChromaDB `wbs_master` RAG + Sonnet rerank

### Step 1. ChromaDB 검색 (실 후보 13개)

`scripts/load_master_list.py` 가 미리 적재한 `wbs_master` 컬렉션에서 메타 필터 + 의미 검색:

```python
chroma["wbs_master"].query(
    query_text="건축 | 거푸집공사 | 기초 거푸집 설치 | M2 | 남웅건설",
    where={"company": "남웅건설", "l5_disc": "건축", "l7_sub": "거푸집공사", "unit": "M2"},
    n_results=5,   # PoC 는 13개 전체 표시 (Plan 일자 필터 §5 미해결로 제외)
)
```

**실 출력 (Master List 직접 조회 — 동일 결과):**

```
필터 통과 Activity: 13 개 (중복 제거 후 13개)

· TNMCB1F6501A03030034 | 1층 바닥 Slab 공사 : 거푸집 공사   | M2 | plan_qty=1500 plan_MH= 456 | Rev.0 2025-01-02~01-20
· TNMCB1F6501A03030033 | RC Wall & Column : 거푸집         | M2 | plan_qty=3200 plan_MH= 380 | Rev.0 2024-12-16~12-24
· TNMCB1F6501A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty= 500 plan_MH= 456 | Rev.0 2024-11-15~11-25
· TNMCB1F6500A03030034 | 1층 바닥 Slab : 거푸집            | M2 | plan_qty=1300 plan_MH= 456 | Rev.0 2025-01-02~01-20
· TNMCB1F6500A03030033 | RC Wall & Column : 거푸집         | M2 | plan_qty=3200 plan_MH= 380 | Rev.0 2024-12-16~12-24
· TNMCB1F6500A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty= 100 plan_MH= 456 | Rev.0 2024-11-15~11-25
· F03C01F0000A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty=1300 plan_MH=2092 | Rev.0 2024-06-21~06-28
· F02CB1F0000A03030034 | 1층 바닥 Slab : 거푸집            | M2 | plan_qty= 800 plan_MH=4184 | Rev.0 2024-09-11~09-30
· F02CB1F0000A03030033 | RC Wall & Column : 거푸집         | M2 | plan_qty=1500 plan_MH=4184 | Rev.0 2024-09-02~11-11
· F02CB1F0000A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty= 940 plan_MH=4184 | Rev.0 2024-06-26~09-20
· F02C01F0000A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty=1300 plan_MH=4184 | Rev.0 2024-06-28~09-25
· C01C02F0000A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty= 750 plan_MH= 456 | Rev.0 2024-10-14~11-08
· C01C01F0000A03030032 | 기초공사 : 거푸집 공사            | M2 | plan_qty= 750 plan_MH= 456 | Rev.0 2024-08-13~09-20
```

### [가정] Step 2. Sonnet rerank

```
프롬프트: "다음 작업일보 행에 가장 적합한 ActivityID 1개를 골라라.
         후보 13개와 confidence 점수를 반환.
         work_content: '기초 거푸집 설치' / sub_work_area 힌트: 'B1F'"

응답:
  top-1: TNMCB1F6501A03030032 (기초 거푸집, L1=TNM L3=3 L4=B1F)  conf=0.82
  top-2: TNMCB1F6500A03030032 (기초 거푸집, L1=TNM L3=3 L4=B1F)  conf=0.78
  top-3: F02CB1F0000A03030032 (기초 거푸집, L1=F02 L3=3 L4=B1F)  conf=0.61
  ...
```

→ confidence 0.82 ≥ 0.7 임계값이라 `requires_review=False` (H-i-L 1 생략). 만약 conf=0.65 였다면 `requires_review=True` → LangGraph `interrupt(hil_1)`.

### Activity 업데이트 (Mapper 출력)

```python
{
    "wbs_activity_id": "TNMCB1F6501A03030032",
    "l5_disc":         "건축",
    "l6_main":         "철근콘크리트공사",
    "l7_sub":          "거푸집공사",
    "l7_5_activity":   "기초공사 : 거푸집 공사",
    "sub_work_area":   "B1F 연결공동구",
    "trade":           "건축",
    "company":         "남웅건설",
    "unit":            "M2",
    "today_qty":       320.0,
    "work_content":    "기초 거푸집 설치",
    "conditions":      [],
    "assigned_workers": ...,                  # 다음 단계에서 결정
    "worker_source":   ...,
    "plan_total_qty":  500.0,                 # Master List lookup
    "plan_mh":         456.0,                 # Master List lookup (Rev.2 채택)
    "requires_review": False,
}
```

---

## PART D. MH 비율 분배 — 두 시나리오 비교 (실 계산)

### D-1. 단일 매핑 시 (top-1 만 채택)

```
assigned_workers       = 81 명  (Parser 단계의 시트1 합산 그대로)
worker_source          = 'parsed'  (Mapper 가 단일 매핑이면 분배 없음, parsed 유지)
plan_unit_productivity = 500 / 456 = 1.096 m²/MH
today_unit_productivity = 320 / (81명 × 8h = 648 MH) = 0.494 m²/MH
plan_diff_pct          = (0.494 - 1.096) / 1.096 × 100 = -54.9 %
```

→ Plan 대비 -55%. 단순 매핑이면 81명이 한 Activity 만 했다고 가정 → 비현실적 (남웅이 9/25 에 RC 5종 다 시공 중).

### D-2. 다중 매핑 시 (후보 13개 전부 활성, LLM 이 분배)

```
Σ plan_mh = 22,324
```

| Activity (요약) | Plan MH | share | workers | today_qty 분배 |
|---|---:|---:|---:|---:|
| TNM B1F · 1층 바닥 Slab | 456 | 2.0% | 1.66 | 6.5 m² |
| TNM B1F · RC Wall | 380 | 1.7% | 1.38 | 5.4 m² |
| TNM B1F · 기초 | 456 | 2.0% | 1.66 | 6.5 m² |
| TNM B1F (6500) · 1층 바닥 | 456 | 2.0% | 1.66 | 6.5 m² |
| TNM B1F (6500) · RC Wall | 380 | 1.7% | 1.38 | 5.4 m² |
| TNM B1F (6500) · 기초 | 456 | 2.0% | 1.66 | 6.5 m² |
| F03 01F · 기초 | 2,092 | 9.4% | 7.61 | 30.0 m² |
| F02 B1F · 1층 바닥 | 4,184 | 18.7% | 15.16 | 60.0 m² |
| F02 B1F · RC Wall | 4,184 | 18.7% | 15.16 | 60.0 m² |
| F02 B1F · 기초 | 4,184 | 18.7% | 15.16 | 60.0 m² |
| F02 01F · 기초 | 4,184 | 18.7% | 15.16 | 60.0 m² |
| C01 02F · 기초 | 456 | 2.0% | 1.66 | 6.5 m² |
| C01 01F · 기초 | 456 | 2.0% | 1.66 | 6.5 m² |
| **합** | **22,324** | **100.0%** | **81.00** | **320.0 m²** |

→ workers 가 0.29 ~ 2.62 의 소수값으로 분포. `Activity.assigned_workers: float` 결정이 정당함 (정수 강제 시 0 으로 떨어지는 작은 share 가 손실됨).

→ **현실에서는** PoC 진입 시 Plan 일자 필터로 13개 → 활성 3~4개 정도로 좁힘 → 각 share 20~30% 의미있는 분배. `state.md` §5 ① Plan 일자 필터 의미 확정이 중요한 이유.

---

## PART E. Forecaster — Plan + RAG 이중 비교

### 입력 (top-1 단일 매핑 가정, D-1 결과 사용)

```
Activity:               TNMCB1F6501A03030032 (기초 거푸집)
today_qty:              320 m²
assigned_workers:       81 명 (잠정 — 다중 매핑이면 1.66 명만 받음)
today_unit_productivity: 320 / (81×8) = 0.494 m²/MH = 3.95 m²/인일

plan_total_qty:         500 m²
plan_mh:                456 MH
plan_unit_productivity: 500 / 456 = 1.096 m²/MH = 8.77 m²/인일
plan_diff_pct:          -55%   (today 가 Plan 대비 절반 수준)
```

### [가정] Chroma `daily_activities` 검색 결과 — 유사 이력 5건

```
조건 매칭: company='남웅건설' ∩ l7_sub='거푸집공사' ∩ unit='M2'

· 2025-01-08  맑음, 정상   workers=12  qty=288  → 24.0 m²/인일
· 2025-01-07  우천, 병행   workers=14  qty=224  → 16.0 m²/인일
· 2025-01-06  맑음, 정상   workers=15  qty=345  → 23.0 m²/인일
· 2025-01-03  맑음, 정상   workers=13  qty=312  → 24.0 m²/인일
· 2024-12-30  맑음, 정상   workers=12  qty=290  → 24.2 m²/인일

RAG 5건 평균 = 22.24 m²/인일
RAG 우천 제외 4건 평균 = 23.80 m²/인일
```

### [가정] Opus 4.7 응답 (이중 비교)

```yaml
assessment: '주의'
reasoning: |
  - Plan 기준 today_unit (3.95 m²/인일) vs Plan (8.77 m²/인일) = -55%. 
    그러나 Plan MH=456 / qty=500 의 비율이 Master List 다른 거푸집 Activity
    (380 ~ 4184 범위) 와 비교했을 때 일관성이 낮아 Plan 자체 신뢰도 보통.
  - RAG 기준이 더 신뢰. RAG 5건 평균 22.24 m²/인일 vs today 3.95 = -82%.
    우천일 1건 빼도 평균 23.80 → today 가 RAG 대비도 큰 폭 미달.
  - 가능한 원인: (i) today 81명이 다중 Activity 에 분산됐을 가능성 — 
    다중 매핑으로 재계산 권고. (ii) 작업내용에 명시 안된 장비대기·전일 야간 후유증 등.
risk_level: '주의'
similar_cases:
  - {date: '2025-01-07', conditions: ['우천','병행'], prod: 16.0,
     note: '우천일 -33% → 익일 복귀 (12-29 패턴)'}
expected_completion: '2025-01-19'  # 잔여 180 m² ÷ 23.8 m²/인일 × 81명 → 0.1일 (단일매핑 가정 시 비현실, 다중매핑 재계산 필요)
```

→ 이 케이스가 **이중 비교의 가치를 보여줌**: Plan 만 봤다면 "-55% 주의" 로 끝났을 것을, RAG 비교로 "Plan 신뢰도 낮음, 실제는 RAG 대비 -82% 더 심각, 다중 매핑 재계산 필요" 로 더 정확한 진단. `state.md` §6 의 이중 비교 필드 분리 (`plan_diff_pct` + `rag_diff_pct`) 설계가 정당화됨.

---

## 발견된 검증 포인트 (검토 시 짚을 사항)

### ✓ 정당화된 결정

| 결정 (state.md / postgres.md) | 실 데이터 검증 |
|---|---|
| `Activity.assigned_workers: float` | D-2 의 0.29 ~ 2.62 분포 — 정수 강제 시 작은 share 손실 |
| MH 비율 분배 (= WV 비율 동치) | D-2 의 share 2.0~18.7% 합리적 분포 |
| Plan + RAG 이중 비교 | E 의 Opus 진단에서 Plan 단독은 -55%, RAG 결합 시 -82% 더 정확한 진단 |
| Parser LLM 단일 호출 (구 정규식·sealed dict 대체) | A 의 시트1 BP 컬럼 `남웅건설` (자연어) ↔ 시트4 `PH_X-001` 코드 매칭 — LLM 이 의미적으로 같은 회사로 인식해야 |
| `Activity.l5_disc` 한글 통일 | A 의 시트1 `AR` ↔ 시트4 `건축` 약자→한글 정규화 |
| `worker_source` 3 enum | D-1 의 'parsed' vs D-2 의 'mh_prorated' 구분 필요 |
| ChromaDB 2 컬렉션 분리 | C (wbs_master) vs E (daily_activities) 검색 의도 명확히 다름 |

### ⚠️ 미해결 사안 (state.md §5 / postgres.md §11)

| # | 사안 | 본 walkthrough 가 드러낸 문제 |
|---|---|---|
| ① | Plan 일자 필터의 Rev 선택 | Master List Rev.0 일정 (2025-01-02 ~) 과 Rev.2 일정 (2024-09 ~) 가 동일 Activity 에서 4~6 개월 차이. 어느 Rev 를 활성 판단 기준으로 쓸지 — `scripts/load_master_list.py` 작성 시 결정 |
| ② | 다중 매핑 시 활성 후보 좁힘 | D-2 에서 13개 모두 활성으로 두면 share 가 너무 분산됨 (작은 활동 ~2%). Plan 일자 필터로 3~4개로 좁혀야 의미있는 분배 가능. ①과 직결 |
| ③ | `today_qty=None` 처리 | A 에서 9/25 작업일보의 89.5% 행이 today=None. Parser LLM 이 "작업없음 0" vs "미입력 → state 제외" 판단 — GATE 2 검증 시 oracle 케이스 필요 |
| ④ | Plan MH outlier | Master List 거푸집 13개의 plan_MH 가 380 ~ 4184 (배수 11배). Forecaster 가 Plan 단독으로 진단하면 위험 — E 의 RAG 결합 진단으로 회피되지만 임계값 정책 정의 필요 |

---

## 변경 이력

| 일자 | 변경 | 작성 |
|---|---|---|
| 2026-05-14 | 초안 — `state.md` 검토용 end-to-end 시뮬레이션. 실 코드 출력 `/tmp/cpia_walkthrough.py` 기반. | A 트랙 |
