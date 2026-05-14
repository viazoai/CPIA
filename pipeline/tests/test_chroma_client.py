from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add pipeline root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
from chroma_client import ChromaClient


@pytest.fixture(scope="module")
def chroma() -> ChromaClient:
    host = os.environ.get("CHROMA_HOST")
    port = os.environ.get("CHROMA_PORT", "8000")
    if not host:
        pytest.skip("CHROMA_HOST 환경변수 없음")
    return ChromaClient(host=host, port=int(port))


def test_get_wbs_master(chroma: ChromaClient):
    coll = chroma.get_or_create_wbs_master()
    assert coll.name == "wbs_master"


def test_get_daily_activities(chroma: ChromaClient):
    coll = chroma.get_or_create_daily_activities()
    assert coll.name == "daily_activities"
