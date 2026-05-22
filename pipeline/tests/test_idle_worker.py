"""idle_worker 단위 테스트 — graph 호출은 stub. aioimaplib mock.

Spec: §6, §8.1.
"""

from __future__ import annotations

import email
import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from pipeline.collector.config import CollectorConfig
from pipeline.collector.idle_worker import (
    _extract_attachments,
    _process_one,
    _save_to_input_dir,
    _to_dead_letter,
)

pytestmark = pytest.mark.asyncio


def _fake_cfg(tmp_path: Path) -> CollectorConfig:
    return CollectorConfig(
        host="imap.gmail.com",
        port=993,
        user="x@gmail.com",
        app_password="x",
        default_site_id="m15x-ph3-ibl",
        input_dir=tmp_path / "input",
        dead_letter_dir=tmp_path / "dead_letter",
        postgres_url=os.environ.get("POSTGRES_URL", "postgresql://x"),
        graph_cfg=MagicMock(),  # 본 테스트에선 graph 호출 stub
        enabled=False,
    )


def _build_email_with_attachment(
    filename: str,
    payload: bytes = b"PK\x03\x04xxxxxx",
    message_id: str | None = None,
) -> bytes:
    """multipart 메일 raw bytes — RFC822."""
    from email.mime.application import MIMEApplication
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart()
    msg["From"] = "pm@example.com"
    msg["To"] = "collector@example.com"
    msg["Subject"] = "작업일보"
    msg["Message-ID"] = message_id or f"<{uuid.uuid4()}@example.com>"
    msg.attach(MIMEText("본문"))
    att = MIMEApplication(payload)
    att.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(att)
    return msg.as_bytes()


def test_extract_attachments_basic() -> None:
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_a_b_c_250917.xlsx",
        payload=b"abc",
    )
    msg = email.message_from_bytes(raw)
    out = _extract_attachments(msg)
    assert len(out) == 1
    assert out[0][0] == "업체작업일보_M15X_a_b_c_250917.xlsx"
    assert out[0][1] == b"abc"


def test_extract_attachments_skips_non_xlsx() -> None:
    raw = _build_email_with_attachment("readme.txt", payload=b"x")
    msg = email.message_from_bytes(raw)
    assert _extract_attachments(msg) == []


def test_save_to_input_dir_collision(tmp_path: Path) -> None:
    cfg = _fake_cfg(tmp_path)
    p1 = _save_to_input_dir("x.xlsx", b"a", "2025-09-26", cfg)
    p2 = _save_to_input_dir("x.xlsx", b"b", "2025-09-26", cfg)
    assert p1.exists() and p2.exists()
    assert p1 != p2  # suffix 로 충돌 회피
    assert p1.parent.name == "20250926"


def test_to_dead_letter(tmp_path: Path) -> None:
    cfg = _fake_cfg(tmp_path)
    _to_dead_letter("garbage.xlsx", b"x", cfg)
    files = list(cfg.dead_letter_dir.glob("garbage_*.xlsx"))
    assert len(files) == 1


async def test_process_one_dedup(tmp_path: Path, monkeypatch) -> None:
    """이미 collector_inbox 에 있는 message_id 는 skip."""
    cfg = _fake_cfg(tmp_path)
    mid = f"<dup-{uuid.uuid4()}@example.com>"
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_a_b_c_250917.xlsx",
        message_id=mid,
    )

    async def fake_fetch(_pg, _mid):
        return {"message_id": _mid, "parse_status": "completed"}

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.fetch_collector_inbox_by_message_id",
        fake_fetch,
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.insert_collector_inbox",
        AsyncMock(),  # 호출 안 되어야 함
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.PGClient",
        MagicMock(return_value=AsyncMock(connect=AsyncMock(), close=AsyncMock())),
    )

    create_task_mock = MagicMock()
    monkeypatch.setattr("pipeline.collector.idle_worker.create_task", create_task_mock)

    fake_imap = AsyncMock()
    fake_imap.fetch.return_value = ("OK", [b"1", raw, b")"])
    fake_imap.store = AsyncMock()

    await _process_one(fake_imap, "1", cfg)

    # graph 호출 안 일어남
    assert create_task_mock.call_count == 0
    fake_imap.store.assert_called_with("1", "+FLAGS", "\\Seen")
    # dedup 시 disk 저장도 안 일어나야 함 (regression: dispatch 만 막고 save 누수 방지)
    assert not list(cfg.input_dir.rglob("*.xlsx"))


async def test_process_one_dispatches_graph(tmp_path: Path, monkeypatch) -> None:
    """첨부 valid + dedup miss 면 asyncio.create_task 로 graph 호출 dispatch."""
    cfg = _fake_cfg(tmp_path)
    mid = f"<new-{uuid.uuid4()}@example.com>"
    raw = _build_email_with_attachment(
        "업체작업일보_M15X_PH4_041_M15X_PH4_UT_acme_콘크리트_FAB_250917.xlsx",
        message_id=mid,
    )

    async def fake_fetch(_pg, _mid):
        return None  # dedup miss

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.fetch_collector_inbox_by_message_id",
        fake_fetch,
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.insert_collector_inbox",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "pipeline.collector.idle_worker.PGClient",
        MagicMock(return_value=AsyncMock(connect=AsyncMock(), close=AsyncMock())),
    )

    dispatched: list = []

    def fake_create_task(coro):
        dispatched.append(coro)
        coro.close()  # 실행 안 함 — graph 호출 차단

    monkeypatch.setattr(
        "pipeline.collector.idle_worker.create_task",
        fake_create_task,
    )

    fake_imap = AsyncMock()
    fake_imap.fetch.return_value = ("OK", [b"1", raw, b")"])
    fake_imap.store = AsyncMock()

    await _process_one(fake_imap, "1", cfg)

    assert len(dispatched) == 1  # graph 호출 task 1개 dispatch
    saved = list((cfg.input_dir / "20250917").glob("*.xlsx"))
    assert len(saved) == 1
