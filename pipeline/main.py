"""CPIA pipeline CLI — `python main.py YYYYMMDD` 로 단일 batch 실행.

graph.py 의 `build_graph` + `graph.ainvoke` 호출 패턴은 tests/test_graph_dual_end.py
참고. 시연 harness 의 step 1 검증용 — 실제 처리시간 측정 + DB write 확인 용도.

사용:
    cd pipeline
    uv run python main.py 20250925
        → data/input/20250925/*.xls(m|x) 를 모아 graph 실행
        → pipeline_runs 에 새 row 생성 (status=running → completed)
        → 각 단계 (Collector → Parser → Mapper → Atomizer → Exporter+Forecaster
          → Optimizer) 가 DB·Chroma 에 결과 적재

종료 시: run_id + 소요시간 출력.

NOTE: A_Track 미완 상태 — Collector/Parser/Mapper/Exporter/Forecaster/Optimizer
agent 들이 `current_node` 컬럼을 update 안 함 (atomizer 만 함). 본 batch 실행으로
어디까지 도는지·끝까지 가는지·각 단계 소요시간을 파악하는 게 목적.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

# pipeline 패키지 import 가능하도록 sys.path 셋업.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # repo 루트

from pipeline.agents.atomizer import AtomizerConfig
from pipeline.agents.forecaster.agent import ForecasterConfig
from pipeline.agents.mapper import MapperConfig
from pipeline.agents.optimizer.agent import OptimizerConfig
from pipeline.agents.reporter import ReporterConfig
from pipeline.db import PGClient
from pipeline.graph import GraphConfig, build_graph

DEFAULT_SITE_ID = "m15x-ph3-ibl"


def _build_graph_config() -> GraphConfig:
    """env 변수로부터 5개 sub-config 조립."""
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ["AZURE_OPENAI_API_VERSION"]
    llm_model = os.environ["LLM_MODEL"]
    embedding_model = os.environ["EMBEDDING_MODEL"]
    postgres_url = os.environ["POSTGRES_URL"]
    chroma_host = os.environ["CHROMA_HOST"]
    chroma_port = int(os.environ["CHROMA_PORT"])
    chroma_ssl = os.environ.get("CHROMA_SSL", "false").lower() == "true"

    return GraphConfig(
        mapper=MapperConfig(
            azure_endpoint=endpoint, azure_api_key=api_key, azure_api_version=api_version,
            llm_model=llm_model, embedding_model=embedding_model, postgres_url=postgres_url,
            chroma_host=chroma_host, chroma_port=chroma_port, chroma_ssl=chroma_ssl,
        ),
        atomizer=AtomizerConfig(
            azure_endpoint=endpoint, azure_api_key=api_key, azure_api_version=api_version,
            embedding_model=embedding_model, postgres_url=postgres_url,
            chroma_host=chroma_host, chroma_port=chroma_port, chroma_ssl=chroma_ssl,
        ),
        forecaster=ForecasterConfig(
            azure_endpoint=endpoint, azure_api_key=api_key, azure_api_version=api_version,
            llm_model=llm_model, embedding_model=embedding_model, postgres_url=postgres_url,
            chroma_host=chroma_host, chroma_port=chroma_port, chroma_ssl=chroma_ssl,
        ),
        optimizer=OptimizerConfig(
            azure_endpoint=endpoint, azure_api_key=api_key, azure_api_version=api_version,
            llm_model=llm_model, postgres_url=postgres_url,
            chroma_host=chroma_host, chroma_port=chroma_port, chroma_ssl=chroma_ssl,
        ),
        reporter=ReporterConfig(
            azure_endpoint=endpoint, azure_api_key=api_key, azure_api_version=api_version,
            llm_model=llm_model, postgres_url=postgres_url,
        ),
    )


def _collect_input_files(date: str) -> list[str]:
    """data/input/YYYYMMDD/ 하위의 .xlsx / .xlsm 절대경로 리스트."""
    root = HERE.parent / "data" / "input" / date
    if not root.is_dir():
        raise FileNotFoundError(f"입력 디렉토리 없음: {root}")
    files = sorted(
        str(p.resolve())
        for p in root.iterdir()
        if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm")
    )
    if not files:
        raise FileNotFoundError(f"{root} 에 .xlsx/.xlsm 파일 없음")
    return files


async def run_pipeline(date: str, site_id: str = DEFAULT_SITE_ID) -> None:
    """단일 batch 실행 — pipeline_runs INSERT 후 graph.ainvoke."""
    input_files = _collect_input_files(date)
    print(f"[main] 입력 파일 {len(input_files)} 개:")
    for f in input_files:
        print(f"  - {Path(f).name}")

    cfg = _build_graph_config()
    pg = PGClient(cfg.atomizer.postgres_url)
    await pg.connect()

    run_id = uuid.uuid4()
    await pg.insert_pipeline_run(run_id=run_id, site_id=site_id, date=date)
    print(f"[main] run_id={run_id}  site_id={site_id}  date={date}")

    graph = build_graph(cfg)

    t0 = time.monotonic()
    try:
        result = await graph.ainvoke(
            {
                "run_id": str(run_id),
                "site_id": site_id,
                "date": date,
                "input_files": input_files,
                "postgres_url": cfg.atomizer.postgres_url,
            },
            config={"configurable": {"thread_id": str(run_id)}},
        )
        elapsed = time.monotonic() - t0
        print(f"\n[main] ✅ 완료 — {elapsed:.1f}s")
        if isinstance(result, dict):
            print(f"[main] result keys: {sorted(result.keys())}")
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"\n[main] ❌ 실패 (after {elapsed:.1f}s): {type(e).__name__}: {e}")
        raise
    finally:
        await pg.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python main.py YYYYMMDD [site_id]", file=sys.stderr)
        sys.exit(2)
    date = sys.argv[1]
    site_id = sys.argv[2] if len(sys.argv) >= 3 else DEFAULT_SITE_ID

    load_dotenv(HERE / ".env")
    asyncio.run(run_pipeline(date, site_id))


if __name__ == "__main__":
    main()
