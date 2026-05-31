# CPIA Presentation · 16:9 Resource Pack

`cpia_presentation.html` (메인 Dark 버전) 의 시각 자산을 PowerPoint 16:9 와이드스크린 용으로 추출한 패키지.

---

## 1. PowerPoint 16:9 슬라이드 크기 설정

PowerPoint → **디자인 → 슬라이드 크기 → 사용자 지정 슬라이드 크기...**

| 옵션 | 값 |
|---|---|
| 너비 | **33.867 cm** (13.333 inch) |
| 높이 | **19.05 cm** (7.5 inch) |
| 방향 | 가로 |

→ 1920 × 1080 (144dpi) 자산이 정확히 맞습니다.

---

## 2. 폴더 구조

```
resource/
├── README.md             ← 이 파일 (전체 가이드)
├── COLORS.md             ← 컬러 팔레트 hex 코드 + 사용처
├── FONTS.md              ← 폰트 정보 + 다운로드 + 임베드
├── LAYOUT.md             ← 16:9 슬라이드 그리드·여백
│
├── backgrounds/          ← 슬라이드 배경 (1920×1080 PNG)
│   ├── 01_bg_base.png         일반 슬라이드 (다크 네이비 단색 + grain)
│   ├── 02_bg_hero.png         표지·Closing (상단 radial gradient + 하단 dot)
│   ├── 03_bg_section.png      섹션 슬라이드 (다크 + 하단 dot wave)
│   └── 04_bg_section_deep.png Impact 등 강조 (하단 deep glow)
│
├── elements/             ← 투명 PNG overlay 자산
│   ├── wave_dots_strip.png    하단 점 패턴 strip (1920×240, 투명)
│   ├── grain_overlay.png      미세 grain 노이즈 (1920×1080, 투명)
│   ├── mint_glow.png          KPI 강조용 mint glow (800×800, 투명)
│   ├── divider.png            가로 hairline divider (1600×32, 투명)
│   ├── arrow_mint.png         → 화살표 아이콘 (96×96, 투명)
│   └── kpi_card_mockup.png    KPI 카드 디자인 참고용 (1200×360)
│
└── palette/
    └── palette.png            전체 컬러 팔레트 swatch
```

---

## 3. 슬라이드별 배경 권장 매핑

| 슬라이드 | 배경 | 비고 |
|---|---|---|
| 1. 표지 (Hero) | `02_bg_hero.png` | 상단 radial gradient 로 제목 영역 분위기 강화 |
| 2. Context | `03_bg_section.png` | 일반 섹션 |
| 3. Approach (Bottleneck) | `03_bg_section.png` | |
| 4. Reframing | `03_bg_section.png` | |
| 5. Process (As-is/To-be) | `04_bg_section_deep.png` | 하단 glow 로 비교 메시지 강화 |
| 6. Core AI | `01_bg_base.png` | 깔끔한 배경 (시각화 카드가 정보 밀도 높음) |
| 7. Impact (4 KPI) | `04_bg_section_deep.png` | 성과 강조 |
| 8. Scalability | `03_bg_section.png` | |
| 9. Closing | `02_bg_hero.png` | 표지와 시각 대칭 |

> 모든 배경은 1920×1080 입니다. PPT 슬라이드에 100% 크기로 삽입 (오른쪽 클릭 → 도형 서식 → 크기에서 너비 33.867cm).

---

## 4. 추가 활용 (선택)

### KPI 강조 효과
`elements/mint_glow.png` 를 KPI 숫자 뒤에 깔면 mint glow 효과. 투명도 30~50% 권장.

### 섹션 구분선
`elements/divider.png` 를 슬라이드 전환 시 시각적 호흡 포인트로 사용.

### 화살표
`elements/arrow_mint.png` 를 As-is → To-be, 흐름도에 사용. PPT 기본 화살표보다 톤이 맞음.

### 빈 슬라이드에 추가 dot 패턴
`elements/wave_dots_strip.png` 를 슬라이드 하단에 깔면 PDF 양식의 통일감 유지.

---

## 5. 자세한 가이드

- 컬러 사용 규칙 → [COLORS.md](./COLORS.md)
- 폰트 다운로드·임베드 → [FONTS.md](./FONTS.md)
- 그리드·여백·정렬 → [LAYOUT.md](./LAYOUT.md)

---

*자동 생성 · 원본: `docs/presentation/cpia_presentation.html`*
