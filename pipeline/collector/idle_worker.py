"""IMAP IDLE 푸시 트리거 — Spec §6.

핵심:
- FastAPI startup 시 asyncio.create_task(idle_loop(cfg)) 호출.
- IDLE EXISTS notification 받으면 UNSEEN fetch → 첨부 추출 → 파일명 식별
  → collector_inbox INSERT → asyncio.create_task(run_for_attachment) fire-and-forget.
- shutdown 시 request_shutdown() + task.cancel().
"""

from __future__ import annotations

import asyncio
import email
import logging
import os
import uuid
from asyncio import create_task  # monkeypatch target 분리 — 테스트 patch 안정성
from email.message import Message
from pathlib import Path

from pipeline.collector.config import CollectorConfig
from pipeline.collector.filename_parser import ParsedFilename, parse_filename
from pipeline.db import (
    PGClient,
    fetch_collector_inbox_by_message_id,
    insert_collector_inbox,
    update_collector_inbox_status,
)

log = logging.getLogger("cpia.collector")

_shutdown = asyncio.Event()
_GRAPH_SEM = asyncio.Semaphore(int(os.environ.get("CPIA_COLLECTOR_CONCURRENCY", "2")))


def request_shutdown() -> None:
    _shutdown.set()


def _extract_attachments(msg: Message) -> list[tuple[str, bytes]]:
    """email.Message → [(filename, bytes), ...]. inline / multipart 처리."""
    out: list[tuple[str, bytes]] = []
    if not msg.is_multipart():
        return out
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        # RFC 2047 디코딩
        decoded = email.header.decode_header(filename)
        decoded_str = "".join((s.decode(enc or "utf-8") if isinstance(s, bytes) else s) for s, enc in decoded)
        if not decoded_str.lower().endswith((".xlsx", ".xlsm")):
            continue
        payload = part.get_payload(decode=True)
        if isinstance(payload, bytes):
            out.append((decoded_str, payload))
    return out


def _save_to_input_dir(
    att_name: str,
    att_bytes: bytes,
    date_iso: str,
    cfg: CollectorConfig,
) -> Path:
    """data/input/<YYYYMMDD>/<att_name> 저장. 같은 이름 충돌 시 timestamp suffix."""
    yyyymmdd = date_iso.replace("-", "")
    dir_ = cfg.input_dir / yyyymmdd
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / att_name
    if path.exists():
        stem = path.stem
        path = dir_ / f"{stem}_{uuid.uuid4().hex[:8]}{path.suffix}"
    path.write_bytes(att_bytes)
    return path


def _to_dead_letter(att_name: str, att_bytes: bytes, cfg: CollectorConfig) -> None:
    """파일명 미일치 / 식별 실패 시 dead_letter 폴더로 이동 + log."""
    cfg.dead_letter_dir.mkdir(parents=True, exist_ok=True)
    suffix = uuid.uuid4().hex[:8]
    path = cfg.dead_letter_dir / f"{Path(att_name).stem}_{suffix}{Path(att_name).suffix}"
    path.write_bytes(att_bytes)
    log.warning("dead_letter: %s → %s", att_name, path)


async def run_for_attachment(
    attachment_path: Path,
    meta: ParsedFilename,
    site_id: str,
    message_id: str,
    cfg: CollectorConfig,
) -> None:
    """semaphore 보호 + graph 1회 호출. 실패 시 collector_inbox.failed 박음."""
    from pipeline.graph import build_graph  # circular import 회피 — 지연 로드

    async with _GRAPH_SEM:
        run_id = uuid.uuid4()
        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(
                pg,
                message_id,
                run_id=run_id,
                parse_status="running",
            )
        finally:
            await pg.close()

        try:
            # D-12: graph 진입점이 collector_node — listener 는 path/메타-trigger 만 박고
            # date/bp_name/project 분해는 collector_node 가 담당 (single source of truth).
            # collector_inbox UPDATE(running) 도 collector_node 가 하므로 위쪽 명시적 UPDATE 는
            # listener 측 안전망 (graph 진입 전 사고 대비) — 중복 UPDATE 는 idempotent.
            graph = build_graph(cfg.graph_cfg)
            await graph.ainvoke(
                {
                    "run_id": str(run_id),
                    "input_files": [str(attachment_path)],
                    "site_id": site_id,  # D-11
                    "message_id": message_id,  # collector_node 가 collector_inbox UPDATE 용
                    "postgres_url": cfg.postgres_url,  # collector_node PG 접근
                },
                config={"configurable": {"thread_id": str(run_id)}},
            )
        except Exception as e:
            log.exception("graph failed for %s", attachment_path)
            pg = PGClient(cfg.postgres_url)
            await pg.connect()
            try:
                await update_collector_inbox_status(
                    pg,
                    message_id,
                    parse_status="failed",
                    error=str(e)[:1000],
                )
            finally:
                await pg.close()
            return

        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            await update_collector_inbox_status(pg, message_id, parse_status="completed")
        finally:
            await pg.close()


async def _process_one(imap, uid: str, cfg: CollectorConfig) -> None:
    """UNSEEN 메일 1통 처리: fetch → dedup → 첨부 추출 → graph 호출 fire-and-forget."""
    import aioimaplib  # noqa: F401

    typ, data = await imap.fetch(uid, "(RFC822)")
    if typ != "OK" or len(data) < 2:
        log.warning("fetch uid=%s 실패: %s", uid, typ)
        return
    raw = data[1] if isinstance(data[1], (bytes, bytearray)) else b"".join(data[1])
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    msg = email.message_from_bytes(raw)
    message_id = msg.get("Message-ID")
    if not message_id:
        log.warning("uid=%s Message-ID 없음, skip", uid)
        await imap.store(uid, "+FLAGS", "\\Seen")
        return

    # dedup PG 체크
    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        existing = await fetch_collector_inbox_by_message_id(pg, message_id)
    finally:
        await pg.close()
    if existing:
        log.info("dedup skip: %s", message_id)
        await imap.store(uid, "+FLAGS", "\\Seen")
        return

    attachments = _extract_attachments(msg)
    if not attachments:
        log.info("no attachment: %s", message_id)
        await imap.store(uid, "+FLAGS", "\\Seen")
        return

    site_id = cfg.default_site_id  # D-11
    for att_name, att_bytes in attachments:
        meta = parse_filename(att_name)
        if meta is None:
            _to_dead_letter(att_name, att_bytes, cfg)
            continue
        path = _save_to_input_dir(att_name, att_bytes, meta.date, cfg)
        sub_message_id = f"{message_id}#{att_name}"
        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            await insert_collector_inbox(
                pg,
                message_id=sub_message_id,
                site_id=site_id,
                report_date=meta.date,
                bp_name=meta.bp_name or "_integrated",
                attachment_filename=att_name,
                attachment_path=str(path),
            )
        finally:
            await pg.close()
        create_task(run_for_attachment(path, meta, site_id, sub_message_id, cfg))

    await imap.store(uid, "+FLAGS", "\\Seen")


async def _drain_new(imap, cfg: CollectorConfig) -> None:
    """UNSEEN 메일 전부 처리. IDLE EXISTS 직후 + startup 시 호출."""
    typ, data = await imap.search("UNSEEN")
    if typ != "OK" or not data or not data[0]:
        return
    uids = data[0].split() if isinstance(data[0], bytes) else data[0].encode().split()
    for uid_bytes in uids:
        uid = uid_bytes.decode() if isinstance(uid_bytes, bytes) else uid_bytes
        try:
            await _process_one(imap, uid, cfg)
        except Exception:
            log.exception("uid=%s 처리 실패", uid)


async def idle_loop(cfg: CollectorConfig) -> None:
    """FastAPI startup background task. shutdown 까지 IDLE 유지 + reconnect."""
    import aioimaplib

    backoff = 1.0
    while not _shutdown.is_set():
        try:
            imap = aioimaplib.IMAP4_SSL(host=cfg.host, port=cfg.port)
            await imap.wait_hello_from_server()
            await imap.login(cfg.user, cfg.app_password)
            await imap.select("INBOX")
            backoff = 1.0
            await _drain_new(imap, cfg)  # 시작 시 누적 UNSEEN 처리
            while not _shutdown.is_set():
                idle_task = await imap.idle_start(timeout=29 * 60)
                try:
                    push_msg = await imap.wait_server_push()
                finally:
                    imap.idle_done()
                    try:
                        await asyncio.wait_for(idle_task, timeout=5)
                    except asyncio.TimeoutError:
                        pass
                # EXISTS notification 이 있으면 새 메일 처리
                if push_msg and any("EXISTS" in str(m) for m in push_msg):
                    await _drain_new(imap, cfg)
        except asyncio.CancelledError:
            log.info("idle_loop cancelled — graceful exit")
            return
        except Exception:
            log.exception("IDLE loop error, reconnect in %.1fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
