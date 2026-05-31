# Layout · 16:9 Slide Grid

CPIA presentation 의 그리드·여백·정렬 가이드. 단위는 cm (PowerPoint 표준) 와 px (1920×1080 기준) 병기.

---

## 1. 슬라이드 캔버스

| 항목 | 값 |
|---|---|
| 슬라이드 너비 | 33.867 cm · 1920 px |
| 슬라이드 높이 | 19.05 cm · 1080 px |
| 비율 | 16:9 |

---

## 2. 안전 여백 (Safe Margin)

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ←─ 1.7cm (96px) ─→  컨텐츠 영역                ←─ 1.7cm ─→ │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Section chip · 좌상단                              │    │
│  │                                                     │    │
│  │  [Eyebrow]                                          │    │
│  │  ┃ Headline · 헤드라인                              │    │
│  │  Lead text                                          │    │
│  │                                                     │    │
│  │  ─────────────────────────────────────────────────  │    │
│  │  Content cards                                      │    │
│  │                                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                       ← 1.0cm (56px) →                       │
│  ░░░░░░░░░░░ wave dots strip (배경 자산) ░░░░░░░░░░░          │
└─────────────────────────────────────────────────────────────┘
```

| 영역 | 여백 |
|---|---|
| 좌·우 마진 | **1.7 cm** (96 px) — 모든 슬라이드 동일 |
| 상단 마진 | **2.0 cm** (112 px) — 섹션 chip 아래 |
| 하단 마진 | **1.0 cm** (56 px) — wave dots 영역 |
| 최대 컨텐츠 너비 | **22.6 cm** (1280 px) — 중앙 정렬 |

---

## 3. 섹션 chip (좌상단)

| 요소 | 값 |
|---|---|
| 위치 | 좌상단 (1.7cm, 0.9cm) |
| 크기 | 자동 (chip 형태, padding 6px 14px) |
| 폰트 | JetBrains Mono Bold 11pt |
| 색 | Mint Soft 배경 + Mint Accent 글자 |
| 자간 | letter-spacing 0.14em (PPT: 넓게 2pt) |

> 예: `00 STRATEGIC CONTEXT`, `01 APPROACH`, `04 IMPACT`

---

## 4. 슬라이드 본문 구성 패턴

### Hero (표지)

```
            CPIA · CONSTRUCTION PRODUCTIVITY INTELLIGENCE AGENT
                              (badge · 중앙)

            현장 Bottleneck을              ← Pretendard ExtraBold 80pt
            AI Agent로 재설계하다           ← .accent 부분은 Mint Accent

      현장 운영 구조 전환을 위한, 생산성 최적화 AI Agent
                  (subtitle · Secondary)

      ┌──────────┐  ┌──────────┐  ┌──────────┐
      │ 2,155h   │  │ 15.4명   │  │ 3~7일    │       ← KPI 카드 3종
      │ Saving   │  │ FTE      │  │ Schedule │
      └──────────┘  └──────────┘  └──────────┘
                                                       SK에코플랜트 조형준 `26.06
```

### 일반 섹션 (Context · Approach 등)

```
[00] Strategic Context                      ← 섹션 chip (좌상단)

EYEBROW · 전략적 배경                       ← Mint mono eyebrow

단순 건설사를 넘어 'AI Infra Solution        ← h2 헤드라인
Provider'로의 근본적 체질 개선을 추진 中

(lead text · 본문 1~2문장)

┌─────────────┐  →  ┌─────────────┐  →  ┌─────────────┐
│  Card 1     │     │  Card 2     │     │  Card 3     │
└─────────────┘     └─────────────┘     └─────────────┘
                                                       ░░░ wave dots ░░░
```

### Impact (4 KPI)

```
[04] Impact

EYEBROW · Hi-tech 현장을 최적화 하다

Middle Office 자동화 → 가용 시간 확보 →
Front Office 실행력 강화 → 공기 지연 예방

┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ 01       │  │ 02       │  │ 03       │  │ 04       │
│ D+0      │  │ 3~7일    │  │ 2,155h   │  │ 15.4명   │   ← KPI 4종
└──────────┘  └──────────┘  └──────────┘  └──────────┘

[ 6 sites 테이블 ]
[ 23억원 reframe strip ]
```

---

## 5. 카드 구성

### KPI 카드

| 요소 | 위치 (카드 내부) |
|---|---|
| Top stripe (mint) | 2px, 카드 상단 |
| Label (eyebrow) | 상단 padding 36px |
| Value (큰 숫자) | 중앙 |
| Unit | Value 옆 0.4em 작게 |
| Description | 하단, divider 위 |

```
┌─────────────────────────┐
│ ━━━━━━━━━━━━━━━━━━━━━━ │ ← mint top stripe
│ MONTHLY SAVING          │ ← mono 11pt
│                         │
│ 2,155 h / 월            │ ← Pretendard ExtraBold 64pt
│                         │
│ ───────────────────     │
│ 2,506h → 351h           │ ← 13pt secondary
│ 대체율 86%              │
└─────────────────────────┘
```

크기: 권장 **5.5 × 6 cm** (KPI 4종 가로 배치 시)

### Section card (Reframing 등)

| 요소 | 위치 |
|---|---|
| 좌측 border (3px) | 카드 좌 (강조 시) |
| Eyebrow chip | 카드 상단 |
| Title | 큰 글씨 (Pretendard Bold 22pt) |
| Sub | mono small |
| Body | list 또는 paragraph |
| Footer note | 하단 mono 12pt |

---

## 6. 간격 (Spacing) 시스템

| 단계 | 값 | 사용처 |
|---|---|---|
| xs | 0.2cm · 8px | 인라인 요소 간 |
| s  | 0.4cm · 16px | 카드 내부 padding |
| m  | 0.7cm · 24px | 카드 간 gap |
| l  | 1.0cm · 40px | 섹션 내부 구분 |
| xl | 1.7cm · 64px | 좌우 마진 |

---

## 7. 정렬 규칙

- 모든 텍스트는 **왼쪽 정렬**이 기본
- Hero / Closing 의 메인 메시지만 **중앙 정렬** (전체 화면 사용)
- KPI 카드 내부도 왼쪽 정렬 (label-value-desc 의 좌측 정렬이 시선 흐름에 자연스러움)
- 표는 텍스트는 좌, 숫자는 우 정렬

---

## 8. PPT 작성 팁

### 마스터 슬라이드 활용
**보기 → 슬라이드 마스터** 에서:
1. 배경: `backgrounds/01_bg_base.png` 삽입 (전체 채우기)
2. 좌상단에 chip 자리 placeholder
3. 헤드라인 영역 placeholder (Pretendard ExtraBold 48pt)
4. 모든 슬라이드에 동일 마진 자동 적용

### 자동 정렬
PowerPoint → **홈 → 정렬 → 가운데 정렬** / **좌측 정렬** 적극 활용. Shift + 화살표로 1px 단위 미세 조정.

### 가이드 라인
**보기 → 안내선** 켜기. 좌우 1.7cm, 상하 2.0cm/1.0cm 위치에 안내선 추가하면 일관성 유지 쉬움.

### 숫자 강조 (KPI count-up 대체)
PPT 의 count-up 모션은 **애니메이션 → 강조 → 펄스** 또는 **나타나기** 사용. 더 자연스러운 효과는 PowerPoint 365 의 **모핑 (Morph)** — 빈 슬라이드 → 숫자 표시 슬라이드를 morph 로 연결.
