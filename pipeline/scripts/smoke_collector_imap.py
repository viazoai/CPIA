"""IMAP login + SELECT INBOX smoke 테스트.

자격증명은 pipeline/.env.local 에서만 로드 (stdlib parser, dotenv 의존성 0).
실행 후 LOGIN: OK + SELECT INBOX: typ=OK 나오면 collector idle_worker 단계 진입 가능.
"""

from __future__ import annotations

import imaplib
import sys
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if val.startswith(("'", '"')) and val.endswith(val[0]):
            val = val[1:-1]
        env[key] = val
    return env


ENV_PATH = Path(__file__).resolve().parents[1] / ".env.local"
if not ENV_PATH.exists():
    print(f"ERROR: {ENV_PATH} 없음 — Task 3 먼저", file=sys.stderr)
    sys.exit(2)
env = load_env(ENV_PATH)

REQUIRED = [
    "COLLECTOR_IMAP_HOST",
    "COLLECTOR_IMAP_PORT",
    "COLLECTOR_IMAP_USER",
    "COLLECTOR_IMAP_APP_PASSWORD",
]
missing = [k for k in REQUIRED if not env.get(k)]
if missing:
    print(f"ERROR: env 누락: {missing}", file=sys.stderr)
    sys.exit(2)

host = env["COLLECTOR_IMAP_HOST"]
port = int(env["COLLECTOR_IMAP_PORT"])
user = env["COLLECTOR_IMAP_USER"]
pw = env["COLLECTOR_IMAP_APP_PASSWORD"].replace(" ", "")

print(f"connect {host}:{port} as {user} ...")
with imaplib.IMAP4_SSL(host, port) as imap:
    typ, resp = imap.login(user, pw)
    print(f"LOGIN: {typ} {resp[0].decode() if resp else ''}")
    typ, data = imap.select("INBOX")
    count = data[0].decode() if typ == "OK" else "?"
    print(f"SELECT INBOX: typ={typ}, count={count}")
