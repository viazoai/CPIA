"""ChromaDB 클라이언트 — wbs_master + daily_activities 컬렉션 헬퍼.

Spec: docs/schema/mapping-layer.md §5.2 + §6.1
- wbs_master: 1 doc = 1 (WA, L6) 그룹 (mapping-layer.md §5.2)
- daily_activities: 1 doc = 1 Activity (mapping-layer.md §6.1)
"""

from __future__ import annotations

import chromadb
from chromadb.api.models.Collection import Collection


class ChromaClient:
    """Chroma HTTP server 클라이언트 래퍼."""

    WBS_MASTER = "wbs_master"
    DAILY_ACTIVITIES = "daily_activities"

    def __init__(self, host: str, port: int = 8000, ssl: bool = False) -> None:
        self.client = chromadb.HttpClient(host=host, port=port, ssl=ssl)

    def get_or_create_wbs_master(self) -> Collection:
        """1 doc = 1 (WA, L6) 그룹. doc text = mapping-layer.md §5.2 형식."""
        return self.client.get_or_create_collection(
            name=self.WBS_MASTER,
            metadata={"hnsw:space": "cosine"},
        )

    def get_or_create_daily_activities(self) -> Collection:
        """1 doc = 1 Activity (시트4 line). doc text = work_content."""
        return self.client.get_or_create_collection(
            name=self.DAILY_ACTIVITIES,
            metadata={"hnsw:space": "cosine"},
        )
