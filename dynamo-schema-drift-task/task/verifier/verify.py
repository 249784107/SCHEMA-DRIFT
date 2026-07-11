"""
Verifier entrypoint for the Schema Drift Sanitizer & Eventual Consistency
Resolver task. Thin wrapper: fetches state from the live MongoDB instance
the agent migrated in place, then delegates all logic to verify_core.py
(kept pymongo-free so it's independently unit-testable).

Checks, all outcome-based (never inspects agent's code/method):
  1. Schema validity
  2. Trap correctness (exact match against disclosed-rule ground truth)
  3. Data integrity (no drops/dupes)
  4. Non-destructiveness (untouched control fields survive unchanged)
  5. Idempotency (re-running /app/migrate.sh is a no-op)

Exit code 0 = PASS, 1 = FAIL. Prints a JSON report to stdout either way.
"""
import json
import subprocess
import sys

sys.path.insert(0, "/verifier")
from verify_core import run_checks, collection_hash

from pymongo import MongoClient

MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "orders_db"
COLL_NAME = "orders"


def main():
    client = MongoClient(MONGO_URI)
    coll = client[DB_NAME][COLL_NAME]

    with open("/app/target_schema.json") as f:
        schema = json.load(f)
    with open("/solution/ground_truth.json") as f:
        ground_truth = json.load(f)
    with open("/solution/pre_migration_snapshot.json") as f:
        pre_snapshot = json.load(f)

    docs = list(coll.find({}))
    report = {"checks": {}, "pass": False}

    if not docs:
        report["checks"]["schema_validity"] = {"pass": False, "detail": "collection is empty post-migration"}
        print(json.dumps(report, indent=2))
        sys.exit(1)

    core_results = run_checks(docs, schema, ground_truth, pre_snapshot)
    for name, (passed, detail) in core_results.items():
        report["checks"][name] = {"pass": passed, "detail": detail}

    # ---- Check 5: idempotency (agent's migration script re-run = no-op) ----
    before_hash = collection_hash(docs)
    try:
        subprocess.run(["bash", "/app/migrate.sh"], check=True, timeout=600)
    except Exception as e:
        report["checks"]["idempotency"] = {"pass": False, "detail": f"second run of migrate.sh failed: {e}"}
    else:
        after_docs = list(coll.find({}))
        after_hash = collection_hash(after_docs)
        if before_hash != after_hash:
            report["checks"]["idempotency"] = {"pass": False, "detail": "re-running migration changed the collection"}
        else:
            report["checks"]["idempotency"] = {"pass": True, "detail": "re-run produced no-op diff"}

    report["pass"] = all(c["pass"] for c in report["checks"].values())
    print(json.dumps(report, indent=2))
    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()
