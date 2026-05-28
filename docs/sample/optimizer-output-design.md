# Optimizer 출력 콘텐츠 설계 — 진단·유사사례·권고사항

> Track A 전달용 | 작성일: 2026-05-28  
> 목적: 리스크 및 대안 검토 화면의 진단·유사사례·권고사항 콘텐츠 품질 개선 방향 확정

---

## 1. 문제 인식

현재 세 섹션은 각자 독립 생성되어 논리적 연결이 없다.

| 섹션 | 현재 생성 방식 | 문제 |
|------|--------------|------|
| 진단 | view_builder 결정론 또는 Optimizer LLM | 유사사례를 인용하지 않음 |
| 유사사례 | trajectory 수치 + conditions 태그만 | "왜 회복됐는지" 서술 없음 |
| 권고사항 | Optimizer LLM 또는 `_pick_recommendations()` | 어느 사례에서 도출됐는지 근거 없음 |

PM이 이 화면을 볼 때 기대하는 흐름:

```
"오늘 이 공종에 문제가 생겼다"  →  진단
"이런 일이 전에도 있었나?"       →  유사사례
"그래서 내가 뭘 해야 하나?"      →  권고사항
```

세 섹션이 **하나의 논리 실로 꿰어져야** 한다.

---

## 2. 핵심 설계 원칙

### 2-1. 회복 맥락 = D+1 work_content

"어떻게 회복됐는가"를 알 수 있는 유일한 단서는 **회복일(D+1, D+2)의 work_content 텍스트**다.

```
D+0 (저하일) work_content: "자재 미입고로 오전 대기"
D+1 (회복일) work_content: "자재 입고 후 정상 시공"
                                  ↑
                       이것이 회복 맥락의 증거
```

현재 `fetch_recovery_trajectory`는 trajectory에서 **productivity + conditions만** 가져온다.  
**D+1 work_content(documents)를 함께 가져오도록 확장**하면 아래 모든 개선이 가능해진다.

### 2-2. 유사사례 1건의 구조

```
날짜  [조건 태그]
  저하: "D+0 work_content 기반 — 무슨 일이 있었나"
  회복: "D+1 work_content 기반 — 어떻게 해결됐나"
  → N일 후 회복
```

### 2-3. 권고사항 = 회복 방법의 패턴 집계

유사사례들의 "회복 방법"에서 공통 액션을 추출 → 1순위 권고로 사용.

```
유사 5건 회복 방법:
  - 건조 완료 구획 집중 배치 (3건)
  - 인접 구획 선이동 (1건)
  - 자연 회복 (1건)
              ↓
권고 1순위: "건조 완료 구획 우선 배치 확인" ← 3건 패턴 기반
```

### 2-4. 진단 = 수치 요약 + 패턴 판단

진단 마지막 문장은 반드시 유사사례 패턴을 인용한 판단으로 끝난다.

```
진단 = [수치 요약] + [원인 추론] + [패턴 판단]
         ↑                              ↑
    Forecaster 기존 출력         유사사례에서 가져온 근거
```

---

## 3. UI 출력 예시

> 아래 세 케이스는 확정된 콘텐츠 구조의 목표 출력이다.  
> 현재 화면과 비교하여 어떤 정보가 추가/변경되어야 하는지 파악하는 기준으로 사용한다.

---

### 케이스 A — 경량벽체 설치·FAB (수장공사) · 인력부족

```
🧠 진단

인력부족 조건에서 생산성 34.88 m²/인 — 유사 평균(45.2 m²/인) 대비 -23%.
과거 5건의 회복 패턴을 보면, 인원 추가 없이 건조 완료 구획으로 작업
순서를 재배치한 날 D+1 회복이 집중됨. 오늘도 마감 면 확보 여부가
내일 생산성을 결정할 가능성 높음.


🕐 유사 과거 사례

2025-09-22  [인력부족]
  저하: "전 구획 균등 배치로 건조 대기 면에 인력 낭비 발생"
  회복: "건조 완료 구획만 추려 집중 시공 — 인원 그대로 정상화"
  → 1일 후 회복

2025-09-20  [인력부족]
  저하: "작업 가능 면 부족, 오전 2시간 대기"
  회복: "인접 구획 선이동 후 오후 집중 투입"
  → 1일 후 회복

2025-09-19  [병행작업]
  저하: "타 공종 병행으로 작업 공간 분산, 이동 동선 증가"
  회복: "병행 공종 철수 후 단독 점유 — 별도 조치 없이 정상화"
  → 1일 후 회복

2025-09-18  [자재미입고]
  저하: "함수율 미달 자재 혼재로 검측 거부, 오전 중단"
  회복: "적합 자재 구획 선별 후 재개 — 불량 자재 후순위 배치"
  → 1일 후 회복

2025-09-17  [인력부족]
  저하: "인력 부족, 작업량 분산"
  회복: "조건 변화 없이 자연 정상화 — 전날 저하가 일시 변동"
  → 1일 후 회복

📊 5건 중 5건 D+1 회복 | 전략 전환 4건 · 자연 회복 1건


💡 권고사항

1.  건조 완료 구획 우선 배치 확인 (반장 확인 요청)
    ← 09-22, 09-20 패턴 — 인원 추가 없이 면 배분만으로 D+1 회복

2.  D+1 오전 생산성 확인 후 추가 대응 판단
    ← 5건 전수 D+1 회복 — 즉시 추가 개입 불필요할 수 있음

3.  함수율 높은 자재 구획 후순위 배치 유지
    ← 09-18 패턴 — 자재 선별만으로 당일 부분 회복 확인

4.  D+2 이상 지속 시 야간 연장 또는 인원 +1명 검토
    ← 현재까지 해당 사례 없음 — 대비 시나리오
```

---

### 케이스 B — 일반공조설비공사 (덕트) · 자재미입고

```
🧠 진단

자재 미입고 조건에서 생산성 0.14 m/인 — 유사 평균(0.21 m/인) 대비 -33%.
과거 4건 모두 자재 입고 확인 당일 또는 다음날 정상화 패턴.
오늘 work_content에 "일부 미입고"로 기재 — 전량 미입고가 아니라면
입고 완료 구간부터 선행 시공 가능성 있음.


🕐 유사 과거 사례

2025-09-24  [자재미입고]
  저하: "AHU 덕트 플랜지 미입고 — 연결 작업 전면 중단"
  회복: "오전 입고 확인 후 즉시 연결 작업 재개, 오후 정상 페이스"
  → 1일 후 회복

2025-09-21  [자재미입고]
  저하: "덕트 소재 일부 미입고, 가용 구간만 시공"
  회복: "잔여 입고 전 기시공 구간 검측 선행 — 물량 보전"
  → 1일 후 회복

2025-09-15  [자재미입고]
  저하: "자재 전량 미입고, 오전 대기 후 철수"
  회복: "D+2 입고 확인 후 집중 시공으로 2일 물량 회수"
  → 2일 후 회복

2025-09-10  [자재미입고]
  저하: "덕트 자재 미입고, 보조 작업으로 대체"
  회복: "다음날 자재 확보 + 보조 작업 선완료 상태로 집중 투입"
  → 1일 후 회복

📊 4건 중 4건 회복 | D+1 회복 3건 · D+2 회복 1건 (전량 미입고 시)


💡 권고사항

1.  금일 오후 자재 입고 일정 확인 (협력사 컨택)
    ← 09-24 패턴 — 오전 입고 확인만으로 오후 정상 페이스 회복

2.  미입고 구간 우회 — 기시공 구간 검측 선행 진행 가능
    ← 09-21 패턴 — 자재 없이도 검측 선행으로 물량 일부 보전

3.  D+1 오전 생산성 확인. 자재 확보 시 자연 정상화 가능성 높음
    ← 4건 전수 자재 확보 후 정상화

4.  D+2 이상 지속 시 대체 자재 확보 또는 후속 공정 선행 검토
    ← 09-15 패턴 — 전량 미입고는 D+2 소요 선례 있음
```

---

### 케이스 C — 철근콘크리트공사 (RC Wall) · 장비대기

```
🧠 진단

장비대기 조건에서 생산성 1.8 ton/인 — 유사 평균(2.6 ton/인) 대비 -31%.
과거 5건의 회복 패턴을 보면, 타워크레인 스케줄 조정이 이루어진 날
D+1 회복이 집중됨. 단, 스케줄 미조정 시 D+3까지 지속된 선례 있음 —
오늘 오후 TC 스케줄 확인이 분기점.


🕐 유사 과거 사례

2025-09-22  [장비대기]
  저하: "TC 타 공종 선점, 오전 4시간 철근 반입 대기"
  회복: "오후 TC 재배정 협의 완료 — 다음날 오전부터 정상 반입"
  → 1일 후 회복

2025-09-17  [장비대기]
  저하: "TC 점검으로 오전 전면 중단, 오후 수작업 일부 진행"
  회복: "점검 완료 후 D+1 오전 정상 가동"
  → 1일 후 회복

2025-09-14  [장비대기]
  저하: "TC 스케줄 조정 없이 대기 지속"
  회복: "D+3 시점 공정 관리자 개입 후 TC 전용 시간 배정"
  → 3일 후 회복

2025-09-08  [장비대기]
  저하: "TC 타 공종 선점, 당일 철근 조립만 진행"
  회복: "다음날 TC 우선 배정으로 반입 재개"
  → 1일 후 회복

2025-09-03  [장비대기]
  저하: "TC 대기 + 우천 병행, 오전 전면 중단"
  회복: "기상 회복 + TC 확보 동시에 이루어져 D+1 집중 시공"
  → 1일 후 회복

📊 5건 중 5건 회복 | D+1 회복 4건 · D+3 회복 1건 (스케줄 미조정 시)


💡 권고사항

1.  오늘 오후 TC 스케줄 조정 협의 (공정 관리자 컨택)
    ← 09-22, 09-08 패턴 — 당일 협의 완료 시 D+1 정상화

2.  TC 확보 전 철근 조립 등 비TC 작업 선행 배치
    ← 09-17 패턴 — 대기 중 수작업 병행으로 일부 물량 보전

3.  D+1 오전 TC 가용 여부 확인 후 추가 대응 판단
    ← 4건이 D+1 자연 정상화 — 협의만 완료되면 즉시 개입 불필요

4.  D+2 이상 지속 시 공정 관리자 에스컬레이션 필요
    ← 09-14 패턴 — 조정 없이 방치 시 D+3까지 지속된 선례 있음
```

---

## 4. 현재 vs 목표 데이터 구조

### 4-1. `fetch_recovery_trajectory` 확장 필요

현재 trajectory 1건이 담는 것:

```python
# 현재
{
    "date": "2025-09-23",
    "conditions": "맑음",
    "productivity": 45.2,
    "recovered": True,
}
```

목표 trajectory 1건:

```python
# 목표 — work_content 추가
{
    "date": "2025-09-23",
    "conditions": "맑음",
    "productivity": 45.2,
    "recovered": True,
    "work_content": "건조 완료 구획 집중 시공",  # ← 신규: D+N work_content
}
```

ChromaDB `daily_activities` 컬렉션의 documents 필드에 work_content가 이미 저장되어 있으므로,  
`fetch_recovery_trajectory` 내부의 `by_date` 구성 시 documents도 함께 수집하면 된다.

### 4-2. degradation_case 구조 확장

```python
# 현재
{
    "date": "2025-09-22",
    "conditions": "인력부족",
    "productivity": 34.88,
    "activities": ["광건·수장공사 시공량 19.4 m2"],
    "recovery": {
        "trajectory": [...],
        "recovery_days": 1,
    }
}

# 목표 — 저하일 work_content + 회복일 work_content 추가
{
    "date": "2025-09-22",
    "conditions": "인력부족",
    "productivity": 34.88,
    "work_content": "전 구획 균등 배치로 건조 대기 면에 인력 낭비",  # ← 신규
    "activities": ["광건·수장공사 시공량 19.4 m2"],
    "recovery": {
        "trajectory": [
            {
                "date": "2025-09-23",
                "conditions": "맑음",
                "productivity": 45.2,
                "recovered": True,
                "work_content": "건조 완료 구획만 추려 집중 시공",  # ← 신규
            }
        ],
        "recovery_days": 1,
    }
}
```

---

## 5. 개선 전략

### 전략 방향: view_builder 결정론 + Optimizer LLM narrative 조합

단계를 나눠 안전하게 접근한다.

```
Phase 1 — view_builder 결정론 강화 (LLM 변경 없음, 안전)
  ├── fetch_recovery_trajectory에 work_content 추가
  ├── _build_optimizer_view: 저하/회복 work_content → 서사 조립
  ├── 진단 앞에 회복 통계 prefix 주입
  │     예: "유사 5건 중 5건 D+1 회복 (100%)"
  └── 권고사항에 케이스 날짜 출처 태그 추가
        예: "← 09-22, 09-08 패턴 기반"

Phase 2 — Optimizer LLM narrative 확장 (Phase 1 완료 후)
  ├── Optimizer 출력 스키마에 case_narratives[] 필드 추가
  │     LLM이 각 케이스를 한 문장으로 서술 생성
  ├── FEW_SHOT 3건 업데이트 (work_content 포함 입력 예시)
  └── view_builder: LLM narrative 우선, 실패 시 Phase 1 결정론 fallback
```

### 각 Phase 작업 범위

**Phase 1 — 수정 대상 파일**

| 파일 | 변경 내용 |
|------|---------|
| `pipeline/agents/optimizer/retrieve.py` | `fetch_recovery_trajectory`: documents(work_content) 수집 추가 |
| `pipeline/agents/optimizer/retrieve.py` | `fetch_degradation_cases`: 저하일 work_content 포함 |
| `pipeline/agents/optimizer/view_builder.py` | `_build_optimizer_view`: 저하/회복 work_content로 description/outcome 조립 |
| `pipeline/agents/optimizer/view_builder.py` | `_build_deterministic_cold_start`: 회복 통계 prefix + 권고 출처 태그 |

**Phase 2 — 수정 대상 파일**

| 파일 | 변경 내용 |
|------|---------|
| `pipeline/agents/optimizer/prompt.py` | SYSTEM_PROMPT: case_narratives[] 출력 필드 추가 지시 |
| `pipeline/agents/optimizer/prompt.py` | FEW_SHOT_MESSAGES: work_content 포함 입력/출력 예시로 교체 |
| `pipeline/agents/optimizer/view_builder.py` | LLM case_narratives 우선 사용, fallback 처리 |

### 회복 서사 조립 로직 (Phase 1 결정론 규칙)

work_content 비교로 회복 맥락을 분류하는 규칙:

```python
def _classify_recovery_context(
    degradation_work_content: str,
    recovery_work_content: str,
    degradation_conditions: str,
    recovery_conditions: str,
) -> str:
    """
    반환값 예시:
      "건조 완료 구획 집중 시공 — 인원 그대로 정상화"
      "자재 확보 후 정상 시공"
      "조건 변화 없이 자연 정상화"
      "회복 맥락 미확인"
    """
    # 1. 조건 태그가 사라졌으면 "조건 해소 후 회복"
    # 2. recovery work_content에 degradation 원인어가 사라졌으면 "X 해소 후 회복"
    # 3. recovery work_content에 새로운 키워드(집중/선행/우선)가 등장하면 "전략 전환 회복"
    # 4. 조건/내용 변화 없으면 "자연 정상화"
```

---

## 6. 우선순위 및 일정 제안

| 단계 | 내용 | 예상 소요 | 시연 영향 |
|------|------|---------|---------|
| Phase 1 | retrieve + view_builder 결정론 강화 | 1~2일 | 시연 전 반영 가능 |
| Phase 2 | Optimizer LLM narrative 확장 | 2~3일 | 여유 시 추가 |

시연(6/13) 기준 Phase 1만으로도 목표 콘텐츠 구조의 80%를 달성할 수 있다.  
Phase 2는 시연 후 품질 고도화로 진행 권장.

---

## 7. 참고 — 현재 데이터 가용성

| 항목 | 위치 | 가용 여부 |
|------|------|---------|
| 저하일 productivity, conditions | ChromaDB metadata | ✅ |
| 저하일 work_content | ChromaDB documents | ✅ (fetch_degradation_cases의 `activities` 필드) |
| 회복일 productivity, conditions | trajectory metadata | ✅ |
| 회복일 work_content | ChromaDB documents | ⚠️ 수집은 가능하나 현재 미포함 |
| 유사사례 패턴 통계 | recovery_distribution | ✅ (코드단 산출 중) |
| 권고 케이스 출처 | 없음 | ❌ 신규 생성 필요 |
