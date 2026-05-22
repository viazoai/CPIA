# CPIA Collector — Gmail 계정 설정

> Spec §8.2 의 Gmail 계정 발급 + IMAP IDLE 활성화 절차.
> Spec §10 결정 (env-only): 계정 주소 / App Password 는 `pipeline/.env.local` 에만 박는다 — 본 문서 / spec / plan / `.env.example` 어디에도 박지 않음.

## 1. Gmail 계정 준비

- 기존 데모 계정이 있으면 그대로 재사용. 없으면 임의 주소로 신규 가입 (예: `cpia-collector@gmail.com`, `poc-cpia-mail@gmail.com` 등 — 자유 변경).
- 본 계정은 PoC / 운영 데모 전용. 회사 메일 권한 / 정책 분리.

## 2. 2단계 인증 (2FA) 활성화

Google Account → Security → 2-Step Verification → 활성화.
App Password 발급 전제.

## 3. App Password 발급

Google Account → Security → 2-Step Verification → App passwords
→ "App name" 에 `CPIA Collector` 입력 → Create → 16자 password 생성 (`xxxx xxxx xxxx xxxx` 형태).
이 password 가 `COLLECTOR_IMAP_APP_PASSWORD` 환경 변수 값. 페이지 닫으면 다시 못 봄 — 즉시 안전한 곳에 복사.

## 4. IMAP 활성화

Gmail 설정 (톱니바퀴) → 전달 및 POP/IMAP → "IMAP 사용" 라디오 선택.

## 5. `pipeline/.env.local` 박기

```bash
COLLECTOR_ENABLED=true
COLLECTOR_IMAP_USER=<발급한 Gmail 주소>
COLLECTOR_IMAP_APP_PASSWORD=<3 단계에서 받은 16자, 공백 유무 무관>
```

`.env.local` 은 `.gitignore` 처리됨 (확인: `git check-ignore pipeline/.env.local` → 경로가 출력되면 OK).

## 6. 동작 확인 (smoke)

`pipeline/scripts/smoke_collector_imap.py` 실행:

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
pipeline/.venv/bin/python pipeline/scripts/smoke_collector_imap.py
```

기대 출력:
```
connect imap.gmail.com:993 as <발급한 주소> ...
LOGIN: OK <발급한 주소> authenticated (Success)
SELECT INBOX: typ=OK, count=<수신함 메일 수>
```

실패 시 bootstrap plan (`docs/superpowers/plans/2026-05-21-cpia-collector-env-bootstrap.md`) Task 4 Step 4 의 분류표 참고.

## 7. 데모 시나리오

1. PM 시뮬: 임의 발신 계정에서 `$COLLECTOR_IMAP_USER` (=.env.local 에 박은 주소) 로 첨부 보냄 (파일명 규약 따름)
2. Dashboard 의 `/tasks` 또는 `/dashboard` 페이지에서 새 run 진입 확인
3. `/export` 페이지에서 일자 선택 → "Export 엑셀" 클릭 → 다운로드

## 8. 계정 교체

다른 Gmail 계정 / 다른 IMAP 서버 (사내 메일 등) 로의 swap:
1. 새 계정에서 위 2~4 단계 반복
2. `pipeline/.env.local` 의 `COLLECTOR_IMAP_USER` / `COLLECTOR_IMAP_APP_PASSWORD` (필요 시 `COLLECTOR_IMAP_HOST` / `COLLECTOR_IMAP_PORT`) 수정
3. FastAPI 재기동
4. smoke 재실행 — 코드 / 재빌드 변경 0
