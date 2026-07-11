"""
End-to-end proof that the task is solvable: runs the reference migration
(solution_reference/) against the real seed data and scores the result
with the actual verifier core logic (verify_core.py) -- the same code
path the real verify.py uses, minus the pymongo plumbing.

This is the test that matters most: it's the only one that proves the
task is solvable as specified, not just that the grading logic is
internally consistent.
"""
import json
import sys

sys.path.insert(0, "/home/claude/task/solution_reference")
sys.path.insert(0, "/home/claude/task/verifier")
sys.path.insert(0, "/home/claude/task/tests")
import _fake_jsonschema as jsonschema
sys.modules["jsonschema"] = jsonschema

from migrate_core import migrate_collection
from verify_core import run_checks, collection_hash

ROOT = "/home/claude/task"


def load():
    raw_docs = [json.loads(l) for l in open(f"{ROOT}/app/data_seed.jsonl")]
    schema = json.load(open(f"{ROOT}/app/target_schema.json"))
    ground_truth = json.load(open(f"{ROOT}/solution/ground_truth.json"))
    pre_snapshot = json.load(open(f"{ROOT}/solution/pre_migration_snapshot.json"))
    return raw_docs, schema, ground_truth, pre_snapshot


def test_reference_solution_passes_all_core_checks():
    raw_docs, schema, ground_truth, pre_snapshot = load()
    unified = migrate_collection(raw_docs)
    assert len(unified) == len(pre_snapshot), (
        f"expected {len(pre_snapshot)} unified orders, got {len(unified)}"
    )
    results = run_checks(unified, schema, ground_truth, pre_snapshot)
    failures = {k: v for k, v in results.items() if not v[0]}
    assert not failures, f"reference solution failed checks: {failures}"
    print("PASS: reference solution passes schema_validity, trap_correctness, "
          "data_integrity, non_destructiveness against real seed data")


def test_reference_solution_is_idempotent():
    raw_docs, *_ = load()
    pass1 = migrate_collection(raw_docs)
    pass2 = migrate_collection(pass1)
    pass3 = migrate_collection(pass2)
    h1, h2, h3 = collection_hash(pass1), collection_hash(pass2), collection_hash(pass3)
    assert h1 == h2 == h3, "reference solution is not idempotent across repeated runs"
    print("PASS: reference solution is idempotent across 3 repeated runs")


if __name__ == "__main__":
    test_reference_solution_passes_all_core_checks()
    test_reference_solution_is_idempotent()
    print("\nEND-TO-END SOLVABILITY PROOF: PASSED")
