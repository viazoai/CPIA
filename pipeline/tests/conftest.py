"""공용 pytest fixtures — DB·Chroma 연결, Master List 로드."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

CPIA_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(CPIA_ROOT / ".env")

# scripts/ 모듈 import 를 위해 project root 를 sys.path 에 추가.
if str(CPIA_ROOT) not in sys.path:
    sys.path.insert(0, str(CPIA_ROOT))


@pytest.fixture(scope="session")
def cpia_root() -> Path:
    return CPIA_ROOT


@pytest.fixture(scope="session")
def sample_wbs_path(cpia_root) -> Path:
    return cpia_root / "docs/sample/WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx"


@pytest.fixture(scope="session")
def sample_tong_path(cpia_root) -> Path:
    return cpia_root / "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"


@pytest.fixture(scope="session")
def azure_openai_env() -> dict[str, str]:
    """Azure OpenAI 환경 변수. 누락 시 테스트 skip."""
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "LLM_MODEL",
        "EMBEDDING_MODEL",
    ]
    env = {k: os.environ.get(k, "") for k in keys}
    if not all(env.values()):
        pytest.skip(f"Azure OpenAI env 누락: {[k for k, v in env.items() if not v]}")
    return env
