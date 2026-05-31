# Colors · CPIA Presentation Palette

전체 swatch: `palette/palette.png`

---

## 1. Background

| Hex | RGB | 이름 | 사용처 |
|---|---|---|---|
| `#0a1628` | `10, 22, 40` | **BG Base** | 모든 슬라이드의 기본 배경 |
| `#060e1d` | `6, 14, 29` | BG Deep | 하단 fade / 강조 그라데이션의 끝 |
| `#15233a` | `21, 35, 58` | BG Card | 카드 배경 (KPI, Pain card 등) |
| `#1c2d47` | `28, 45, 71` | BG Card-2 | 카드 hover / 강조 카드 |
| `#16294a` | `22, 41, 74` | Hero Top | 표지 상단 radial gradient 시작점 |

## 2. Accent · Mint

| Hex | RGB | 이름 | 사용처 |
|---|---|---|---|
| `#5cc4d9` | `92, 196, 217` | **Mint Accent** | 모든 강조 (KPI 숫자, chip 글자, accent line) |
| `#87e0eb` | `135, 224, 235` | Mint Deep | 그라데이션 끝점, hover 상태 |

**Mint Soft (반투명)** — chip 배경·border 에 사용:
- 배경: `rgba(92, 196, 217, 0.10)` ~ `0.16`
- 테두리: `rgba(92, 196, 217, 0.35)`
- Glow: `rgba(92, 196, 217, 0.40)`

## 3. Status (Forecaster 4분면)

| Hex | RGB | 의미 |
|---|---|---|
| `#4ade80` | `74, 222, 128` | 정상 (Green) |
| `#f5a623` | `245, 166, 35` | 주의 (Warm) |
| `#ef5365` | `239, 83, 101` | 위험 (Red) |
| `#6b7a8f` | `107, 122, 143` | No Data (Muted) |

## 4. Text

| Hex | RGB | 사용처 |
|---|---|---|
| `#ffffff` | `255, 255, 255` | 헤드라인, 핵심 정보 |
| `#a8b5c7` | `168, 181, 199` | 본문, lead text |
| `#6b7a8f` | `107, 122, 143` | 캡션, 메타 정보, 비활성 |

## 5. Border

| RGB | 사용처 |
|---|---|
| `rgba(255, 255, 255, 0.06)` | 카드 일반 border |
| `rgba(255, 255, 255, 0.12)` | 카드 강조 border |

---

## PowerPoint 색상 설정

### 빠른 입력 (RGB)

PowerPoint → 도형 클릭 → **도형 서식 → 채우기 → 다른 채우기 색 → 사용자 지정 탭** → RGB 또는 HEX 직접 입력

### 테마 색 등록 (권장)

PowerPoint → **디자인 → 색 → 색 사용자 지정**

| 슬롯 | 권장 색 | Hex |
|---|---|---|
| 텍스트/배경 - 어두운 색 1 | BG Base | `#0a1628` |
| 텍스트/배경 - 밝은 색 1 | White | `#ffffff` |
| 텍스트/배경 - 어두운 색 2 | BG Card | `#15233a` |
| 텍스트/배경 - 밝은 색 2 | Secondary | `#a8b5c7` |
| 강조 1 | **Mint Accent** | `#5cc4d9` |
| 강조 2 | Mint Deep | `#87e0eb` |
| 강조 3 | Green | `#4ade80` |
| 강조 4 | Warm | `#f5a623` |
| 강조 5 | Red | `#ef5365` |
| 강조 6 | Muted | `#6b7a8f` |
| 하이퍼링크 | Mint Accent | `#5cc4d9` |
| 사용된 하이퍼링크 | Mint Deep | `#87e0eb` |

이렇게 등록하면 모든 슬라이드에서 동일 톤 유지 가능.

---

## 사용 규칙 (Do / Don't)

### ✅ Do

- KPI 숫자에는 **반드시 Mint Accent (`#5cc4d9`)** 사용
- 본문 텍스트는 흰색 또는 Secondary (`#a8b5c7`) — 가독성 확보
- 카드 배경은 BG Card (`#15233a`) — BG Base 와 명도 차이로 구분
- 비활성/메타 정보는 Muted (`#6b7a8f`)
- Status (정상/주의/위험) 는 의미 그대로 사용 — 색을 섞지 말 것

### ⛔ Don't

- 흰 배경 사용 금지 (전체 톤 깨짐)
- Mint 외의 강조색 (보라, 분홍 등) 추가 금지
- 본문에 채도 높은 색 사용 금지 — KPI 와 같은 강조 영역에만
- 그라데이션 무리해서 쓰지 말 것 (Mint Accent → Mint Deep 만 OK)
