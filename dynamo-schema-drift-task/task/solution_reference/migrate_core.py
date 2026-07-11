"""
Orchestrates phase 1 (normalize) + phase 2 (resolve) over a full collection
dump (a plain list of dicts). Kept free of any pymongo dependency so it can
be dry-run and unit tested without a live database -- migrate.py is the
thin wrapper that actually talks to Mongo.
"""
from collections import defaultdict

from normalize import normalize
from resolve import resolve_order


def migrate_collection(raw_docs):
    """raw_docs: list of dicts, possibly multiple per order_id (conflicting
    updates) and possibly already-unified docs from a prior run (idempotency).

    Returns: list of unified docs, one per order_id.
    """
    groups = defaultdict(list)
    for raw in raw_docs:
        norm = normalize(raw)
        if norm["order_id"] is None:
            continue
        groups[norm["order_id"]].append(norm)

    results = []
    for order_id, candidates in groups.items():
        results.append(resolve_order(order_id, candidates))
    return results
