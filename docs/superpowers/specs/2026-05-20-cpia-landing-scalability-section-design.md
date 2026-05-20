# CPIA 랜딩페이지 § 04 — Roadmap → Scalability 재구성

작성일: 2026-05-20
대상 파일: `web/app/components/landing/ScalabilitySection.tsx`

## 배경

경영진 시연용 랜딩페이지의 마지막 섹션 (`/ 04 — Roadmap`) 이 **시간축 기반 4-Horizon 카드** (0~6 / 6~12 / 18 개월+) 로 구성되어 있고, 마지막 카드가 "AI Solution 상품화 (SaaS · 외부 수익화)" 였다. 본 PoC 의 메시지는 외부 상품화가 아니라 **Agent 의 확장성** 에 무게가 있다.

## 변경 목표

- **메시지 전환** — 시간축 / 상품화 → **확장축 / 영역 확장**
- **섹션 라벨 변경** — "Roadmap" → **"Scalability · 확장성"** (anchor `id="roadmap"` 은 유지)
- **LangGraph 노드 모듈성**을 가장 작은 스케일의 enabler 로 전면 배치
- **MPRS 관점**에서 현재 위치 (P-Construction) 와 확장 가능 영역 (R-Engineering · P-Procurement · M / PM) 명시

## 새 구조

3-카드 grid (기존 4-카드 → 3-카드).
배치 순서는 **스케일 small → large** :

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ AXIS 01      │  │ AXIS 02      │  │ AXIS 03      │
│ Foundation   │  │ Breadth      │  │ Depth        │
│ LangGraph    │  │ 현장 수평    │  │ MPRS 영역    │
│ 노드 모듈성  │  │ 확장          │  │ 수직 확장    │
└──────────────┘  └──────────────┘  └──────────────┘
   기술 토대      → 같은 베이스로   → 다른 도메인
                  다른 현장 확산      (R·P-Procure·M)
```

### Axis 01 — LangGraph 노드 모듈성 (Foundation · 강조 카드)

| 필드 | 값 |
|---|---|
| 라벨 | `AXIS 01 · FOUNDATION` |
| 아이콘 | `Cpu` |
| 제목 | LangGraph 기반 — 쉽게 교체할 수 있도록 설계 |
| 본문 | 7 개 Agent 가 독립 모듈로 구성되어, 현장 특성에 맞춰 일부 노드만 교체하면 동작. 새 현장·새 영역으로 옮길 때 코어 재학습 없이 빠르게 적용할 수 있도록 **LangGraph 기술**로 설계. |
| 효과 | 노드 교체 only · 코어 재학습 불요 |
| `active: true` | 강조 카드 (gradient 배경 유지) |

### Axis 02 — 현장 · 사업부 수평 확장 (Breadth)

| 필드 | 값 |
|---|---|
| 라벨 | `AXIS 02 · HORIZONTAL SCALE-OUT` |
| 아이콘 | `Globe` |
| 제목 | Hi-tech 6 개 → SK ecosystem 전체 |
| 본문 | Hi-tech 사업부 6 개 현장 내재화 후, AI Solution · 글로벌 사업부로 동일 LangGraph 베이스 확산. 발주처 포맷 · 언어 모듈만 교체하여 신규 현장 적용. |
| 효과 | 월 **4,200 h+** 통합 절감 (사업부 누적) |

### Axis 03 — MPRS 영역 수직 확장 (Depth)

| 필드 | 값 |
|---|---|
| 라벨 | `AXIS 03 · MPRS DOMAIN EXPANSION` |
| 아이콘 | `Layers` |
| 제목 | P-Construction → R-Engineering · P-Procurement · M / PM |
| 본문 | 현재 P-Construction 한정. 동일 패턴으로 R-Engineering (VE · Clash Detection · 예상공기 검토), P-Procurement (자재 수급 예측), M / PM 까지 확장하여 전 EPC 단계 공기 단축에 기여. |
| 효과 | 예상공기 검토시간 **50 % 절감** (R-Engineering 확장 사례, Hi-tech 사업본부 정보화 과제 요청서 기준) |

## Hero 카피

- 라벨: `/ 04 — Scalability · 확장성`
- 제목: **하나의 현장 패턴이, 다른 현장·다른 영역의 출발점이 된다**
- 서브: LangGraph 기반 노드 모듈 구조로 — 현장 다양성과 MPRS 전 영역을 같은 베이스에서 흡수. Hi-tech P-Construction 의 학습을 SK ecosystem 전체로 전이.

## 구현 노트

- 파일: `web/app/components/landing/ScalabilitySection.tsx`
- 기존 `HORIZONS` 배열 → `AXES` 배열로 rename
- 데이터 필드 변경:
  - `phase` → `axis` (예: `"AXIS 01"`)
  - `period` → `category` (예: `"FOUNDATION"`, `"HORIZONTAL SCALE-OUT"`, `"MPRS DOMAIN EXPANSION"`)
  - 나머지 (`icon`, `title`, `body`, `target`, `active`) 유지
- 카드 수 4 → 3 → 그리드 `xl:grid-cols-4` → `md:grid-cols-3` 로 변경
- `id="roadmap"` anchor 는 **유지** (헤더 메뉴 호환)
- 섹션 라벨 텍스트만 "Roadmap" → "Scalability · 확장성"
- 기존 서브카피 "Hi-tech 사업부 내재화 후 SK ecosystem · 글로벌 · 상품화로 단계 확장." → 새 서브카피로 교체
- 아이콘 import 변경: 기존 `Building2, Cpu, Globe, Package` → 새 `Cpu, Globe, Layers` (3개로 축소)

## Out of Scope

- 다른 랜딩 섹션 (Hero · Impact 등) 변경 없음
- 메뉴 / 네비게이션 변경 없음 (anchor id `roadmap` 유지)
- A_Track 파이프라인 코드 변경 없음
