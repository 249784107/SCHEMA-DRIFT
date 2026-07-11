"""
Pure verification logic, no MongoDB/pymongo dependency, so it can be unit
tested directly. verify.py (the real entrypoint) fetches documents from
Mongo and calls run_checks() with plain Python data.
"""
import json
from collections import defaultdict

try:
    import jsonschema
except ImportError:
    jsonschema = None


def check_schema_validity(docs, schema):
    if jsonschema is None:
        raise RuntimeError("jsonschema package required")
    bad = []
    for d in docs:
        d2 = {k: v for k, v in d.items() if k != "_id"}
        try:
            jsonschema.validate(d2, schema)
        except jsonschema.ValidationError as e:
            bad.append((d.get("order_id", str(d.get("_id")))[:40], str(e.message)[:160]))
    if bad:
        return False, f"{len(bad)} documents failed schema validation, e.g. {bad[:5]}"
    return True, f"all {len(docs)} documents valid"


def check_trap_correctness(docs, ground_truth):
    by_order = {d["order_id"]: d for d in docs if "order_id" in d}
    failures = []
    for order_id, spec in ground_truth.items():
        expected = spec["expected"]
        got = by_order.get(order_id)
        if got is None:
            failures.append((order_id, "missing from migrated collection"))
            continue
        if "status" in expected and got.get("status") != expected["status"]:
            failures.append((order_id, f"status: expected {expected['status']}, got {got.get('status')}"))
        if "price_amount_minor_units" in expected:
            actual_amt = (got.get("price") or {}).get("amount_minor_units")
            if actual_amt != expected["price_amount_minor_units"]:
                failures.append((order_id, f"price: expected {expected['price_amount_minor_units']}, got {actual_amt}"))
        if "line_items_quantity_sku-222" in expected:
            qty = None
            for li in got.get("line_items", []):
                if li.get("product_id") == "sku-222":
                    qty = li.get("quantity")
            if qty != expected["line_items_quantity_sku-222"]:
                failures.append((order_id, f"sku-222 qty: expected {expected['line_items_quantity_sku-222']}, got {qty}"))
    if failures:
        return False, failures
    return True, f"all {len(ground_truth)} trap orders resolved correctly"


def check_data_integrity(docs, pre_snapshot):
    counts = defaultdict(int)
    for d in docs:
        counts[d.get("order_id")] += 1
    dupes = {k: v for k, v in counts.items() if v > 1}
    expected_ids = set(pre_snapshot.keys())
    got_ids = set(counts.keys())
    missing = expected_ids - got_ids
    extra = got_ids - expected_ids
    if dupes or missing or extra:
        return False, {"duplicates": dupes, "missing": sorted(missing)[:10], "unexpected": sorted(extra)[:10]}
    return True, f"{len(got_ids)} orders, 1:1 mapping preserved"


def check_non_destructiveness(docs, pre_snapshot):
    by_order = {d["order_id"]: d for d in docs if "order_id" in d}
    failures = []
    for order_id, controls in pre_snapshot.items():
        got = by_order.get(order_id)
        if got is None:
            continue
        if "customer_id_expected" in controls and got.get("customer_id") != controls["customer_id_expected"]:
            failures.append((order_id, "customer_id mutated"))
    if failures:
        return False, failures[:10]
    return True, "control fields preserved"


def collection_hash(docs):
    import hashlib
    normalized = sorted(
        json.dumps({k: v for k, v in d.items() if k != "_id"}, sort_keys=True, default=str)
        for d in docs
    )
    return hashlib.sha256("\n".join(normalized).encode()).hexdigest()


def run_checks(docs, schema, ground_truth, pre_snapshot):
    """Runs the 4 outcome checks that don't require a second migration run.
    Idempotency (5th check, requires re-invoking migrate.sh) stays in verify.py."""
    report = {}
    report["schema_validity"] = check_schema_validity(docs, schema)
    report["trap_correctness"] = check_trap_correctness(docs, ground_truth)
    report["data_integrity"] = check_data_integrity(docs, pre_snapshot)
    report["non_destructiveness"] = check_non_destructiveness(docs, pre_snapshot)
    return report
