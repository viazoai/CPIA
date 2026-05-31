# Fonts · CPIA Presentation

`cpia_presentation.html` 에서 사용한 폰트 페어링 + PowerPoint 적용 가이드.

---

## 1. 폰트 페어링

| 용도 | 폰트 | 무게 |
|---|---|---|
| **한국어 본문·헤드라인** | **Pretendard Variable** | 400 / 500 / 700 / **800 ExtraBold** |
| **영문 라벨·숫자·메타** | **JetBrains Mono** | 400 / 500 / **700 Bold** |

### 사용 규칙

| 요소 | 폰트 | 무게 | 크기 (PPT 기준) |
|---|---|---|---|
| 슬라이드 제목 (h2) | Pretendard | ExtraBold 800 | 40~52pt |
| Hero 메인 제목 | Pretendard | ExtraBold 800 | 64~80pt |
| KPI 숫자 | Pretendard | ExtraBold 800 | 60~80pt |
| 본문 (lead) | Pretendard | Regular 400 | 16~18pt |
| 카드 제목 | Pretendard | Bold 700 | 20~24pt |
| 카드 본문 | Pretendard | Regular 400 | 13~14pt |
| **Eyebrow / 라벨** (영문) | JetBrains Mono | Bold 700 | 11~12pt · **letter-spacing 0.14em** · uppercase |
| **단위 (h, 명, 일)** | JetBrains Mono | Regular/Bold | 0.4~0.5 × KPI 숫자 크기 |
| 섹션 번호 (00, 01) | JetBrains Mono | Bold 700 | 11~13pt |
| 표 데이터 (숫자) | JetBrains Mono | Medium 500 | 14pt |

> **핵심 규칙**: 한국어는 Pretendard, 영문/숫자/대문자 라벨은 JetBrains Mono. 섞어 쓸 때 같은 줄 안에서 sans+mono 대비가 정보 hierarchy 를 명확하게 만듭니다.

---

## 2. 다운로드

### Pretendard

- **공식**: https://github.com/orioncactus/pretendard/releases
- **권장 패키지**: `Pretendard-1.3.9.zip` (또는 최신)
- 설치할 파일: `public/static/Pretendard-Regular.otf`, `Pretendard-Medium.otf`, `Pretendard-Bold.otf`, `Pretendard-ExtraBold.otf`

설치 (Windows):
1. ZIP 압축 해제
2. `.otf` 파일들을 모두 선택 → 우클릭 → **모든 사용자용으로 설치**

설치 (macOS):
1. ZIP 압축 해제
2. `.otf` 파일들을 모두 선택 → 더블클릭 → **글꼴 설치**

### JetBrains Mono

- **공식**: https://www.jetbrains.com/lp/mono/
- 또는: https://github.com/JetBrains/JetBrainsMono/releases
- 권장: `JetBrainsMono-2.304.zip`
- 설치할 파일: `fonts/ttf/JetBrainsMono-Regular.ttf`, `JetBrainsMono-Medium.ttf`, `JetBrainsMono-Bold.ttf`

---

## 3. PowerPoint 글꼴 임베드 (필수)

발표 PC 에 폰트가 설치 안 되어 있을 수 있으니 **PPT 파일에 글꼴 임베드**:

### Windows
PowerPoint → **파일 → 옵션 → 저장**
- ☑ **파일에 글꼴 포함**
- ⦿ **모든 문자 포함** 선택 (편집용)
- 또는 ⦿ **표시에 사용된 문자만 포함** (배포용, 파일 크기 작음)

### macOS
PowerPoint → **PowerPoint → 환경 설정 → 저장**
- ☑ 파일에 글꼴 포함

> ⚠️ macOS PowerPoint 는 `.otf` 임베드 제한이 있을 수 있음. 가능하면 `.ttf` 버전 사용 권장.

### 임베드 확인
저장 후 다른 PC 에서 열어보거나, 파일 정보에서 임베드된 글꼴 확인.

---

## 4. PowerPoint 테마 글꼴 설정 (권장)

매번 폰트 선택 안 해도 되도록 **테마 글꼴** 등록:

PowerPoint → **디자인 → 글꼴 → 글꼴 사용자 지정**

| 슬롯 | 글꼴 |
|---|---|
| 머리글 글꼴 (한글) | **Pretendard ExtraBold** |
| 머리글 글꼴 (영어) | **JetBrains Mono** |
| 본문 글꼴 (한글) | **Pretendard** |
| 본문 글꼴 (영어) | **JetBrains Mono** |

이름: `CPIA Dark` 로 저장.

---

## 5. 대체 폰트 (폰트 미설치 환경)

발표 환경 제약으로 위 폰트 사용 불가 시:

| 원본 | 대체 (한국 PC 표준) |
|---|---|
| Pretendard | **맑은 고딕** (Bold/ExtraBold) — 굵기 충분 |
| JetBrains Mono | **Consolas** 또는 **D2Coding** |

> 단, 대체 폰트는 자간(letter-spacing) 이 다르므로 영문 eyebrow 라벨의 시각적 톤이 약화됩니다. 가능한 한 원본 폰트 임베드 권장.

---

## 6. 한글 자간 (PowerPoint 한글 자간 권장)

Pretendard 헤드라인은 letter-spacing **-0.025em** 으로 설정되어 있음 (살짝 좁힘).
PowerPoint 에서는:

- 헤드라인 선택 → **글꼴 → 문자 간격 → 좁게** (또는 사용자 지정 `-0.5pt`)
- 본문은 기본 자간 유지

영문 eyebrow (mono) 는 반대로 **letter-spacing 0.14em** (넓힘):
- PowerPoint → 글꼴 → 문자 간격 → **넓게** → `2pt`

이 자간 조정이 PDF·HTML 양식의 시각 톤을 결정합니다.
