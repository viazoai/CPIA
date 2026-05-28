# CPIA Collector — Credentials Bootstrap Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `kyungseop1902@gmail.com` 의 Gmail App Password 를 발급받아 `pipeline/.env.local` 에 collector 4종 변수 박기 + IMAP 로그인 smoke 테스트로 동작 검증.

**Architecture:** 사용자 노트북 단독 작업. App Password 발급은 Google Account 에서 사용자가 직접 (Claude 대신 발급 불가). 자격증명은 spec/plan/.env.example 에 박지 않고 오직 `pipeline/.env.local` (gitignore 처리됨) 에만 존재. stdlib `imaplib` 로 결정론적 smoke 검증.

**Tech Stack:** Python 3.9.6 stdlib `imaplib`, `python-dotenv`, Gmail IMAP4_SSL `imap.gmail.com:993`.

**관련 spec:** `docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md` (env-only 결정 §3 D-1 + §10 결정 완료)

---

### Task 1: gitignore 안전성 재확인

**Files:**
- Verify: `.gitignore`

- [ ] **Step 1: gitignore 에 `.env.local` + `pipeline/.env` 패턴 모두 있는지 확인**

Run:
```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
grep -E "^\.env\.local|^pipeline/\.env" .gitignore
```
Expected:
```
.env.local
pipeline/.env
```

- [ ] **Step 2: 없으면 추가 후 commit** (현재 확인 결과 둘 다 존재 — 이 step 은 no-op)

> 별 cycle 로 빼야 할 issue: `.env.example` 에 Azure API key / Cloudflared token / Postgres pw 가 평문으로 git 추적 중. 본 bootstrap 범위 밖.

---

### Task 2: Google App Password 발급 (사용자 수동)

**누가:** kyungseoplee 본인. Claude 대신 발급 불가 (Google 보안 정책).

- [ ] **Step 1: Google Account Security 접속**

`kyungseop1902@gmail.com` 로 로그인된 상태로 https://myaccount.google.com/security 열기.

- [ ] **Step 2: 2-Step Verification 활성화**

"How you sign in to Google" 섹션 → "2-Step Verification" 클릭. 이미 켜져 있으면 skip. App Password 는 2FA 가 켜져 있어야 발급 가능.

- [ ] **Step 3: App passwords 페이지 진입**

같은 페이지에서 https://myaccount.google.com/apppasswords 직접 열기 (2FA 활성화 후 노출됨).

- [ ] **Step 4: 새 App password 발급**

"App name" 입력 칸에 `CPIA Collector` 입력 → "Create" 클릭.

- [ ] **Step 5: 16자 코드 복사**

`xxxx xxxx xxxx xxxx` 형태의 16자 (공백 포함 19자) 코드가 노란 박스로 표시됨. **이 페이지 닫으면 다시 못 봄** — 즉시 안전한 곳에 복사 (메모장 등).

- [ ] **Step 6: Gmail IMAP enable**

https://mail.google.com → 설정 (톱니바퀴) → "See all settings" → "Forwarding and POP/IMAP" 탭 → "IMAP access" 섹션에서 "Enable IMAP" 선택 → "Save Changes".

- [ ] **Step 7: 16자 코드를 Claude 에게 전달**

이 채팅에서 다음 형식으로 전달:
```
App Password: xxxx xxxx xxxx xxxx
```
공백 유무는 상관 없음 (imaplib 가 양쪽 다 받음).

---

### Task 3: pipeline/.env.local 에 COLLECTOR_* 변수 추가

**Files:**
- Modify: `pipeline/.env.local` (없으면 .env.example 복사 후 생성)

- [ ] **Step 1: .env.local 존재 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
ls -la pipeline/.env.local 2>/dev/null || cp pipeline/.env.example pipeline/.env.local
```

- [ ] **Step 2: Collector 블록 append**

`pipeline/.env.local` 끝에 다음 블록 추가:

```bash

# === Collector (IMAP IDLE 트리거) ===
# spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §3 D-1 (env-only)
COLLECTOR_ENABLED=true
COLLECTOR_IMAP_HOST=imap.gmail.com
COLLECTOR_IMAP_PORT=993
COLLECTOR_IMAP_USER=kyungseop1902@gmail.com
COLLECTOR_IMAP_APP_PASSWORD=<Task 2 에서 받은 16자 코드, 공백 포함/제거 둘 다 가능>
COLLECTOR_DEFAULT_SITE_ID=m15x-ph3-ibl
COLLECTOR_INPUT_DIR=data/input
COLLECTOR_DEAD_LETTER_DIR=data/input/dead_letter
CPIA_COLLECTOR_CONCURRENCY=2
```

- [ ] **Step 3: gitignore 동작 확인**

```bash
git status --short pipeline/.env.local
```
Expected: **빈 출력** (.env.local 은 추적 대상 아님). 만약 `?? pipeline/.env.local` 나오면 gitignore pattern 재점검.

- [ ] **Step 4: grep 으로 spec/plan/example 에 자격증명 노출 0 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git ls-files | xargs grep -l "kyungseop1902\|<16자 코드 일부 4자>" 2>/dev/null
```
Expected: **빈 출력**. plan.md (본 파일) 에도 박지 않음.

---

### Task 4: stdlib imaplib smoke 테스트

**Files:**
- Create: `pipeline/scripts/smoke_collector_imap.py`

- [ ] **Step 1: smoke 스크립트 작성**

```python
"""IMAP login + SELECT INBOX smoke 테스트.

자격증명은 pipeline/.env.local 에서만 로드. 코드에 박지 않음.
실행 후 OK + 메일 수 출력되면 collector idle_worker 단계로 진행 가능.
"""
from __future__ import annotations

import imaplib
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env.local"
if not ENV_PATH.exists():
    print(f"ERROR: {ENV_PATH} 없음 — Task 3 먼저 실행", file=sys.stderr)
    sys.exit(2)
load_dotenv(ENV_PATH)

REQUIRED = [
    "COLLECTOR_IMAP_HOST",
    "COLLECTOR_IMAP_PORT",
    "COLLECTOR_IMAP_USER",
    "COLLECTOR_IMAP_APP_PASSWORD",
]
missing = [k for k in REQUIRED if not os.environ.get(k)]
if missing:
    print(f"ERROR: env 누락: {missing}", file=sys.stderr)
    sys.exit(2)

host = os.environ["COLLECTOR_IMAP_HOST"]
port = int(os.environ["COLLECTOR_IMAP_PORT"])
user = os.environ["COLLECTOR_IMAP_USER"]
pw = os.environ["COLLECTOR_IMAP_APP_PASSWORD"].replace(" ", "")

print(f"connect {host}:{port} as {user} ...")
with imaplib.IMAP4_SSL(host, port) as imap:
    typ, _ = imap.login(user, pw)
    print(f"LOGIN: {typ}")
    typ, data = imap.select("INBOX")
    count = data[0].decode() if typ == "OK" else "?"
    print(f"SELECT INBOX: typ={typ}, count={count}")
```

- [ ] **Step 2: 의존성 확인**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
source pipeline/venv/bin/activate 2>/dev/null || source pipeline/.venv/bin/activate
python3 -c "import dotenv; print(dotenv.__version__)"
```
Expected: dotenv 버전 (없으면 `pip install python-dotenv`).

- [ ] **Step 3: smoke 실행**

```bash
mkdir -p pipeline/scripts
# Step 1 의 코드를 pipeline/scripts/smoke_collector_imap.py 에 저장
python3 pipeline/scripts/smoke_collector_imap.py
```

Expected:
```
connect imap.gmail.com:993 as kyungseop1902@gmail.com ...
LOGIN: OK
SELECT INBOX: typ=OK, count=<숫자>
```

- [ ] **Step 4: 실패 케이스 분류**

| 출력 | 원인 | 조치 |
|---|---|---|
| `b'[AUTHENTICATIONFAILED] Application-specific password required'` | App Password 미발급, Gmail 일반 비번 사용 | Task 2 재실행 |
| `b'Invalid credentials (Failure)'` | App Password 오타 | .env.local 의 16자 재확인, 공백 제거 |
| `socket.gaierror` / 연결 timeout | 네트워크 / IMAP enable 안 됨 | Task 2 Step 6 재확인 |
| `b'[ALERT] Web login required'` | Google 보안 경고 (수상한 로그인 차단) | https://accounts.google.com/DisplayUnlockCaptcha 접속 + 재시도 |

- [ ] **Step 5: smoke 스크립트 git 추가 여부 결정**

`pipeline/scripts/smoke_*.py` 는 개발자 도구 — 자격증명 안 박혀 있으므로 commit 해도 안전. commit 시:

```bash
git add pipeline/scripts/smoke_collector_imap.py
git commit -m "chore(collector): IMAP login smoke 스크립트 추가"
```

---

## Verification Gate (모두 통과해야 collector idle_worker 구현 진입)

- [ ] **G1**: `git status --short pipeline/.env.local` → 빈 출력 (untracked)
- [ ] **G2**: `python3 pipeline/scripts/smoke_collector_imap.py` → `LOGIN: OK` + `SELECT INBOX: typ=OK`
- [ ] **G3**: spec/plan/.env.example/CLAUDE.md 어디에도 `kyungseop1902@gmail.com` + App Password 16자 노출 0 (grep 확인)
- [ ] **G4**: 본 plan 파일 자체에도 실제 16자 코드가 박혀있지 않음 (Task 3 Step 2 의 placeholder `<...>` 그대로 유지)

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git ls-files | xargs grep -l "kyungseop1902@gmail.com" 2>/dev/null
# 0줄 — 본 plan 의 Task 3 Step 2 placeholder 는 plan 자체에 user 명만 박혀있음.
# Trade-off 수용: dev 머신 식별자라 노출 risk 낮음 (계정 ID 만으로는 접근 불가, App Password 가 진짜 secret).
# 단 App Password 16자는 절대 commit 금지.
```

---

## Open issues (본 cycle 범위 밖)

- `.env.example` 에 박힌 Azure API key / Cloudflared token / Postgres pw — git history 에 노출됨. 별 cycle 로 rotate + git-filter-repo 또는 BFG 로 history 정화 필요.
- Cron / launchd 로 FastAPI auto-start 시 `.env.local` 로드 방식 — 본 bootstrap 은 manual 실행 가정.

---

## Next step (본 plan 완료 후)

→ spec §6 의 `pipeline/collector/idle_worker.py` + `filename_parser.py` 구현 (별 plan: `2026-05-19-cpia-collector-exporter-plan.md`).
