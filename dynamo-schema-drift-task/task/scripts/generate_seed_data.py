"""
Generates the raw (pre-migration) order collection for the Schema Drift
Sanitizer task, as a MongoDB collection dump (JSON lines) loaded into
mongod at container build time.

Produces:
  - ~2000 "easy" documents spread across 10 generations, single-version,
    no conflicts (baseline correctness check).
  - A set of TRAP documents: orders with 2-3 competing update documents
    representing out-of-order microservice writes, seeded so that specific
    rules in CONFLICT_RESOLUTION_RULES.md are the ones that must fire.
  - Ground truth for every trap order, written to
    /solution/ground_truth.json (NOT visible to the agent's /app).
"""
import json
import random
import uuid
from datetime import datetime, timedelta, timezone

random.seed(1438858)

CURRENCY = "USD"

def money_gen1(amount):
    # Gen 1-3: raw float dollars
    return round(amount, 2)

def money_gen4(amount):
    # Gen 4-6: string with currency symbol
    return f"${amount:.2f}"

def money_gen7(amount):
    # Gen 7-10: nested object, minor units
    return {"amount": int(round(amount * 100)), "currency": CURRENCY, "minorUnits": True}

def price_field_for_gen(gen, amount):
    if gen <= 3:
        return {"price": money_gen1(amount)}
    elif gen <= 6:
        return {"price": money_gen4(amount)}
    else:
        return {"totalPrice": money_gen7(amount)}

def line_items_for_gen(gen, items):
    # items: list of (product_id, qty, unit_price)
    if gen <= 5:
        # inline embedded details
        return {
            "items": [
                {"sku": pid, "qty": qty, "unitPrice": round(price, 2)}
                for pid, qty, price in items
            ]
        }
    else:
        # normalized references
        return {
            "lineItems": [
                {"productRef": pid, "quantity": qty, "price": round(price, 2)}
                for pid, qty, price in items
            ]
        }

def gen_order_doc(order_id, gen, status, amount, items, ts, lc=None, customer=None):
    doc = {
        "_id": str(uuid.uuid4()),
        "orderId": order_id,
        "schemaGen": gen,  # NOTE: only present because this is a build-time
                            # generator; real legacy docs in the actual
                            # collection loaded into mongod do NOT all carry
                            # this field faithfully -- see note below.
        "custId": customer or f"cust_{random.randint(1000,9999)}",
        "status": status,
        "createdAt": ts.isoformat(),
    }
    doc.update(price_field_for_gen(gen, amount))
    doc.update(line_items_for_gen(gen, items))
    if lc is not None:
        doc["_lc"] = lc
    return doc

def sample_items(n=2):
    return [
        (f"sku-{random.randint(100,999)}", random.randint(1, 3), round(random.uniform(5, 200), 2))
        for _ in range(n)
    ]

docs = []
ground_truth = {}

# ---- Baseline: single-version, single-generation orders across all 10 gens
for i in range(2000):
    gen = random.randint(1, 10)
    order_id = f"ORD-{i:05d}"
    status = random.choice(["pending", "processing", "shipped", "delivered"])
    amount = round(random.uniform(10, 500), 2)
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    docs.append(gen_order_doc(order_id, gen, status, amount, sample_items(), ts))

# ---- IMPORTANT DESIGN NOTE ----
# `schemaGen` above is a convenience for building the generator; the actual
# exported collection strips this field from a large fraction of documents
# (see strip step below) so the agent genuinely must fingerprint structure,
# not read an explicit version tag.

def strip_gen_tag(doc, keep_prob=0.15):
    d = dict(doc)
    if random.random() > keep_prob:
        d.pop("schemaGen", None)
    return d

docs = [strip_gen_tag(d) for d in docs]

# ---- Trap orders: seeded conflicts exercising specific rules ----

def add_trap(name, order_id, updates, expected):
    """updates: list of raw docs (already gen-shaped) representing
    out-of-order competing writes for the same orderId, inserted in
    non-chronological order into the collection.
    expected: the ground-truth resolved unified doc for this order."""
    shuffled = updates[:]
    random.shuffle(shuffled)
    for u in shuffled:
        docs.append(strip_gen_tag(u, keep_prob=0.15))
    ground_truth[order_id] = {"trap": name, "expected": expected}

# TRAP 1: terminal status protection (rule 1)
# Late-arriving "processing" update must NOT overwrite existing "cancelled".
oid = "ORD-TRAP-0001"
items = sample_items()
base_ts = datetime(2024, 3, 1, tzinfo=timezone.utc)
cust = "cust_trap_0001"
u1 = gen_order_doc(oid, 2, "cancelled", 120.00, items, base_ts, lc=5, customer=cust)
u2 = gen_order_doc(oid, 2, "processing", 120.00, items, base_ts - timedelta(hours=3), lc=3, customer=cust)
add_trap("terminal_status_protection", oid, [u1, u2], {
    "status": "cancelled",
    "price_amount_minor_units": 12000,
    "rule_fired": "rule_1_terminal_status"
})

# TRAP 2: logical clock overrides generation/order (rule 2), non-status field
oid = "ORD-TRAP-0002"
items_a = [("sku-501", 1, 99.99)]
items_b = [("sku-501", 1, 149.99)]  # price actually differs -> real conflict
base_ts = datetime(2024, 3, 5, tzinfo=timezone.utc)
cust = "cust_trap_0002"
u1 = gen_order_doc(oid, 4, "processing", 99.99, items_a, base_ts, lc=10, customer=cust)
u2 = gen_order_doc(oid, 6, "processing", 149.99, items_b, base_ts + timedelta(hours=1), lc=7, customer=cust)
# u2 has later timestamp AND higher generation but LOWER logical clock -> u1's price must win
add_trap("logical_clock_overrides_generation", oid, [u1, u2], {
    "status": "processing",
    "price_amount_minor_units": 9999,
    "rule_fired": "rule_2_logical_clock"
})

# TRAP 3: schema-only change -> higher generation representation wins, same value
oid = "ORD-TRAP-0003"
items = [("sku-777", 2, 25.00)]
base_ts = datetime(2024, 3, 10, tzinfo=timezone.utc)
cust = "cust_trap_0003"
u1 = gen_order_doc(oid, 3, "shipped", 50.00, items, base_ts, customer=cust)          # float price
u2 = gen_order_doc(oid, 8, "shipped", 50.00, items, base_ts + timedelta(hours=2), customer=cust)  # nested object price, same value
add_trap("schema_only_generation_precedence", oid, [u1, u2], {
    "status": "shipped",
    "price_amount_minor_units": 5000,
    "rule_fired": "rule_3_schema_only"
})

# TRAP 4: no lc, no terminal status, real value conflict -> fallback highest generation wins
oid = "ORD-TRAP-0004"
items_a = [("sku-222", 1, 40.00)]
items_b = [("sku-222", 2, 40.00)]  # quantity actually differs
base_ts = datetime(2024, 3, 15, tzinfo=timezone.utc)
cust = "cust_trap_0004"
u1 = gen_order_doc(oid, 5, "delivered", 40.00, items_a, base_ts, customer=cust)
u2 = gen_order_doc(oid, 9, "delivered", 80.00, items_b, base_ts - timedelta(hours=5), customer=cust)  # earlier ts, higher gen
add_trap("fallback_highest_generation", oid, [u1, u2], {
    "status": "delivered",
    "line_items_quantity_sku-222": 2,
    "rule_fired": "rule_4_fallback_generation"
})

# TRAP 5: three-way conflict combining rules 1 + 3 (terminal status wins,
# but the surviving doc must still be normalized via schema-only precedence
# against a same-status higher-gen duplicate)
oid = "ORD-TRAP-0005"
items = [("sku-333", 1, 15.00)]
base_ts = datetime(2024, 3, 20, tzinfo=timezone.utc)
cust = "cust_trap_0005"
u1 = gen_order_doc(oid, 2, "refunded", 15.00, items, base_ts, lc=1, customer=cust)
u2 = gen_order_doc(oid, 7, "refunded", 15.00, items, base_ts + timedelta(hours=1), lc=2, customer=cust)  # schema-only dup, higher gen
u3 = gen_order_doc(oid, 2, "delivered", 15.00, items, base_ts - timedelta(hours=10), lc=0, customer=cust)  # stale, must lose
add_trap("terminal_plus_schema_only", oid, [u1, u2, u3], {
    "status": "refunded",
    "price_amount_minor_units": 1500,
    "rule_fired": "rule_1_then_rule_3"
})

random.shuffle(docs)

import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(REPO_ROOT, "app", "data_seed.jsonl"), "w") as f:
    for d in docs:
        f.write(json.dumps(d) + "\n")

with open(os.path.join(REPO_ROOT, "solution", "ground_truth.json"), "w") as f:
    json.dump(ground_truth, f, indent=2)

# Build pre-migration snapshot: one entry per distinct orderId, capturing a
# control field (customer id) that no rule ever touches, so the verifier can
# confirm migration didn't mutate fields outside its mandate.
snapshot = {}
for d in docs:
    oid = d.get("orderId")
    if oid is None:
        continue
    if oid not in snapshot:
        snapshot[oid] = {"customer_id_expected": d.get("custId")}
    # for trap orders with multiple competing docs, all versions share the
    # same custId in this generator, so first-seen is stable and correct.

with open(os.path.join(REPO_ROOT, "solution", "pre_migration_snapshot.json"), "w") as f:
    json.dump(snapshot, f, indent=2)

print(f"Wrote {len(docs)} documents, {len(ground_truth)} trap orders, "
      f"{len(snapshot)} orders in pre-migration snapshot.")
