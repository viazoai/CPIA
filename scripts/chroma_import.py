"""JSONL snapshot → Chroma collection.

usage: python scripts/chroma_import.py --host HOST --port PORT --collection NAME --in PATH.jsonl
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
    ap.add_argument("--in", dest="inp", required=True)
    args = ap.parse_args()

    chroma = ChromaClient(host=args.host, port=args.port)
    # collection 존재 시 delete + 재생성 (clean import)
    try:
        chroma.client.delete_collection(args.collection)
        print(f"  · 기존 {args.collection} 삭제")
    except Exception:
        pass
    coll = (
        chroma.get_or_create_daily_activities()
        if args.collection == "daily_activities"
        else chroma.client.create_collection(args.collection)
    )

    BATCH = 100
    ids, embs, metas, docs = [], [], [], []
    n_total = 0
    with open(args.inp) as f:
        for line in f:
            row = json.loads(line)
            ids.append(row["id"])
            embs.append(row["embedding"])
            metas.append(row["metadata"])
            docs.append(row["document"])
            if len(ids) >= BATCH:
                coll.upsert(ids=ids, embeddings=embs, metadatas=metas, documents=docs)
                n_total += len(ids)
                print(f"  upsert {n_total}")
                ids, embs, metas, docs = [], [], [], []
        if ids:
            coll.upsert(ids=ids, embeddings=embs, metadatas=metas, documents=docs)
            n_total += len(ids)
            print(f"  upsert {n_total}")
    print(f"✓ import 완료 ({n_total} docs)")


if __name__ == "__main__":
    main()
