"""Chroma collection → JSONL snapshot.

usage: python scripts/chroma_export.py --host HOST --port PORT --collection NAME --out PATH.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, "/Users/kyungseoplee/Project Agent/CPIA")
from pipeline.chroma_client import ChromaClient


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=5533)
    ap.add_argument("--collection", default="daily_activities")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    chroma = ChromaClient(host=args.host, port=args.port)
    coll = chroma.client.get_collection(args.collection)
    total = coll.count()
    print(
        f"export {args.collection} from {args.host}:{args.port} → {args.out} ({total} docs)"
    )

    BATCH = 500
    with open(args.out, "w") as f:
        for offset in range(0, total, BATCH):
            data = coll.get(
                limit=BATCH,
                offset=offset,
                include=["embeddings", "metadatas", "documents"],
            )
            for i in range(len(data["ids"])):
                emb = data["embeddings"][i]
                f.write(
                    json.dumps(
                        {
                            "id": data["ids"][i],
                            "embedding": emb.tolist()
                            if hasattr(emb, "tolist")
                            else emb,
                            "metadata": data["metadatas"][i],
                            "document": data["documents"][i],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            print(f"  offset={offset}+{len(data['ids'])}")
    print(f"✓ export 완료 ({total} lines)")


if __name__ == "__main__":
    main()
