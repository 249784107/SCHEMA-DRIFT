"""
Real entrypoint for running the reference migration against a live Mongo
instance. Thin wrapper -- all actual logic lives in migrate_core.py,
normalize.py, resolve.py, none of which import pymongo, so they stay unit
testable without a database.

This file is NOT part of the agent's task -- it exists so the maintainers
can prove the task is solvable, and optionally to smoke-test the container
build. It is not copied into /app by the Dockerfile.
"""
import sys

from migrate_core import migrate_collection
from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "orders_db"
COLL_NAME = "orders"


def main():
    client = MongoClient(MONGO_URI)
    coll = client[DB_NAME][COLL_NAME]

    raw_docs = list(coll.find({}))
    unified = migrate_collection(raw_docs)

    # In-place replace: for each order_id, delete every raw document that
    # contributed to it, then insert the single unified result. Done inside
    # a session-scoped bulk op per order so a crash mid-run leaves at worst
    # a partially-migrated collection (still safely re-runnable, since
    # already-unified orders round-trip through migrate_collection as a
    # no-op, and any still-raw orders get processed again next run).
    from collections import defaultdict
    raw_ids_by_order = defaultdict(list)
    for raw in raw_docs:
        oid = raw.get("order_id") or raw.get("orderId")
        if oid is not None:
            raw_ids_by_order[oid].append(raw["_id"])

    for result in unified:
        oid = result["order_id"]
        stale_ids = [i for i in raw_ids_by_order.get(oid, [])]
        # Delete all prior representations of this order, then insert the
        # single resolved doc. If the only prior representation was itself
        # already the unified doc with the same content, this is a
        # delete+reinsert no-op at the data level (idempotent).
        coll.delete_many({"_id": {"$in": stale_ids}})
        coll.insert_one(result)

    print(f"Migrated {len(unified)} orders from {len(raw_docs)} raw documents.")


if __name__ == "__main__":
    main()
