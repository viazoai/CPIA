"""CollectorConfig — env 로드 + GraphConfig 의존성 wiring.

Spec: docs/superpowers/specs/2026-05-19-cpia-collector-exporter-design.md §8.2
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pipeline.graph import GraphConfig


@dataclass(frozen=True)
class CollectorConfig:
    host: str
    port: int
    user: str
    app_password: str
    default_site_id: str
    input_dir: Path
    dead_letter_dir: Path
    postgres_url: str
    graph_cfg: GraphConfig
    enabled: bool


def _bool(s: str | None, default: bool = False) -> bool:
    if s is None:
        return default
    return s.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_collector_config(graph_cfg: GraphConfig) -> CollectorConfig:
    """환경 변수에서 로드 — Spec §8.2 의 9 env.

    Spec §10 결정 (env-only, fail-fast):
    - 자격증명 (USER / APP_PASSWORD) 은 코드에 default 없음.
    - COLLECTOR_ENABLED=true 인데 USER 또는 APP_PASSWORD 가 비어있으면 RuntimeError.
    - COLLECTOR_ENABLED=false 면 자격증명 누락 허용 (로컬 / 테스트 환경).
    - host / port 는 운영 swap 편의를 위해 default 유지 (secrets 아님).
    """
    enabled = _bool(os.environ.get("COLLECTOR_ENABLED"), default=False)
    user = os.environ.get("COLLECTOR_IMAP_USER", "")
    app_password = os.environ.get("COLLECTOR_IMAP_APP_PASSWORD", "")
    if enabled and not (user and app_password):
        missing = [
            k
            for k, v in [("COLLECTOR_IMAP_USER", user), ("COLLECTOR_IMAP_APP_PASSWORD", app_password)]
            if not v
        ]
        raise RuntimeError(
            f"COLLECTOR_ENABLED=true 인데 자격증명 누락: {missing}. "
            "pipeline/.env.local 확인 (spec §10 결정 — 코드 default 없음)"
        )
    return CollectorConfig(
        host=os.environ.get("COLLECTOR_IMAP_HOST", "imap.gmail.com"),
        port=int(os.environ.get("COLLECTOR_IMAP_PORT", "993")),
        user=user,
        app_password=app_password,
        default_site_id=os.environ.get("COLLECTOR_DEFAULT_SITE_ID", "m15x-ph3-ibl"),
        input_dir=Path(os.environ.get("COLLECTOR_INPUT_DIR", "data/input")),
        dead_letter_dir=Path(os.environ.get("COLLECTOR_DEAD_LETTER_DIR", "data/input/dead_letter")),
        postgres_url=os.environ["POSTGRES_URL"],
        graph_cfg=graph_cfg,
        enabled=enabled,
    )
