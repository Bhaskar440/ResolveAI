"""Ingest the policy corpus into PostgreSQL/pgvector and optionally search it.

Usage (from apps/api):
  uv run python -m scripts.ingest_knowledge
  uv run python -m scripts.ingest_knowledge --force
  uv run python -m scripts.ingest_knowledge --query "lost parcel refund" --reason MERCHANDISE_OR_SERVICE_NOT_RECEIVED
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal
from app.services.knowledge import (
    ingest_knowledge,
    knowledge_status,
    retrieve_policy_citations,
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-chunk and re-embed every document")
    parser.add_argument("--query")
    parser.add_argument("--reason")
    args = parser.parse_args()

    async with SessionLocal() as session:
        result = await ingest_knowledge(session, force=args.force)
        print("ingest:", json.dumps(result, indent=2))
        print("status:", json.dumps(await knowledge_status(session), indent=2))
        if args.query:
            retrieval = await retrieve_policy_citations(
                session,
                {"reason_code": args.reason or "", "reason_detail": args.query},
                query=args.query,
                reason_code=args.reason,
            )
            print("retrieval:", json.dumps(retrieval.meta(), indent=2))
            for citation in retrieval.citations:
                print(
                    f"- {citation.document} :: {citation.section} "
                    f"[{citation.source}] score={citation.score} mode={citation.retrieval_mode}"
                )


if __name__ == "__main__":
    asyncio.run(main())
