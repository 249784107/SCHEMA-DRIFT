import json
import sys
import copy
sys.path.insert(0, "/home/claude/task/verifier")
from verify_core import run_checks

SCHEMA = json.load(open("/home/claude/task/app/target_schema.json"))
GROUND_TRUTH = json.load(open("/home/claude/task/solution/ground_truth.json"))
PRE_SNAPSHOT = json.load(open("/home/claude/task/solution/pre_migration_snapshot.json"))

def build_correct_doc(order_id, status, amount_minor, customer_id, gen=5):
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": status,
        "price": {"amount_minor_units": amount_minor, "currency": "USD"},
        "line_items": [{"product_id": "sku-222", "quantity": 2, "unit_price_minor_units": 4000}],
        "created_at": "2024-03-01T00:00:00+00:00",
        "schema_generation": gen,
    }

def build_full_correct_collection():
    docs = []
    for order_id, controls in PRE_SNAPSHOT.items():
        cust = controls["customer_id_expected"]
        if order_id in GROUND_TRUTH:
            exp = GROUND_TRUTH[order_id]["expected"]
            status = exp.get("status", "pending")
            amt = exp.get("price_amount_minor_units", 1000)
            docs.append(build_correct_doc(order_id, status, amt, cust))
        else:
            docs.append(build_correct_doc(order_id, "pending", 1000, cust))
    return docs

def test_correct_migration_passes_all_four():
    docs = build_full_correct_collection()
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    failures = {k: v for k, v in results.items() if not v[0]}
    assert not failures, f"expected all checks to pass, got failures: {failures}"
    print("PASS: correct migration passes all 4 core checks")

def test_schema_violation_caught():
    docs = build_full_correct_collection()
    docs[0].pop("status")  # required field missing
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["schema_validity"][0] is False
    print("PASS: missing required field correctly fails schema_validity")

def test_terminal_status_violation_caught():
    docs = build_full_correct_collection()
    for d in docs:
        if d["order_id"] == "ORD-TRAP-0001":
            d["status"] = "processing"  # should be cancelled per rule 1
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["trap_correctness"][0] is False
    assert any("ORD-TRAP-0001" in str(f) for f in results["trap_correctness"][1])
    print("PASS: terminal-status trap violation correctly fails trap_correctness")

def test_logical_clock_violation_caught():
    docs = build_full_correct_collection()
    for d in docs:
        if d["order_id"] == "ORD-TRAP-0002":
            d["price"]["amount_minor_units"] = 14999  # wrong: took higher-gen value, ignoring lc
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["trap_correctness"][0] is False
    print("PASS: logical-clock trap violation correctly fails trap_correctness")

def test_duplicate_order_caught():
    docs = build_full_correct_collection()
    docs.append(copy.deepcopy(docs[0]))  # duplicate order_id
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["data_integrity"][0] is False
    print("PASS: duplicated order correctly fails data_integrity")

def test_dropped_order_caught():
    docs = build_full_correct_collection()
    docs.pop()  # drop one order
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["data_integrity"][0] is False
    print("PASS: dropped order correctly fails data_integrity")

def test_mutated_untouched_field_caught():
    docs = build_full_correct_collection()
    docs[0]["customer_id"] = "someone-else"
    results = run_checks(docs, SCHEMA, GROUND_TRUTH, PRE_SNAPSHOT)
    assert results["non_destructiveness"][0] is False
    print("PASS: mutated control field correctly fails non_destructiveness")

if __name__ == "__main__":
    test_correct_migration_passes_all_four()
    test_schema_violation_caught()
    test_terminal_status_violation_caught()
    test_logical_clock_violation_caught()
    test_duplicate_order_caught()
    test_dropped_order_caught()
    test_mutated_untouched_field_caught()
    print("\nALL VERIFIER SELF-TESTS PASSED")
