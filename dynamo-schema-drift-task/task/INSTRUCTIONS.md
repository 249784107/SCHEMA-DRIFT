# Schema Drift Sanitizer & Eventual Consistency Resolver

## Scenario

You are the on-call database engineer for an e-commerce platform. The
`orders_db.orders` collection in the local MongoDB instance (already
running on `localhost:27017`) contains customer order documents written
across **10 generations of schema changes**, plus a set of orders that
received **out-of-order, conflicting updates** from asynchronous
microservices. Multiple raw documents may exist for the same logical
order (`orderId`), representing different partial or superseding updates.

Your job: migrate this collection **in place** into a single, unified
document per order conforming to `/app/target_schema.json`, resolving all
conflicts according to the rules in `/app/CONFLICT_RESOLUTION_RULES.md`.

## What's given to you

- `/app/data_seed.jsonl` — a copy of the raw seed data for reference (the
  live collection in MongoDB is what actually gets graded).
- `/app/target_schema.json` — the exact unified schema every migrated
  document must satisfy.
- `/app/CONFLICT_RESOLUTION_RULES.md` — the **full, disclosed** conflict
  resolution rule set. You do not need to invent or guess a precedence
  order — apply the one given.

## What's NOT given to you

The 10 raw document generation shapes are **not documented**. You must
sample `orders_db.orders` yourself, figure out how each generation
represents `price`, line items, and other fields, and write migration
logic that correctly detects and normalizes all of them.

## Requirements

1. Write your migration as an executable script at `/app/migrate.sh` (it
   may shell out to Python, Node, a Mongo shell script, etc. — your
   choice). It must run against the live `orders_db.orders` collection
   and perform the migration **in place** (no dropping and rebuilding the
   collection from scratch).
2. Your migration must be **idempotent**: running `/app/migrate.sh` a
   second time against the already-migrated collection must be a no-op.
3. Fields not implicated by any conflict or schema mapping must be
   preserved exactly (e.g. `customer_id`).
4. After migration, every document in `orders_db.orders` must validate
   against `/app/target_schema.json` and there must be exactly one
   document per `order_id` (no drops, no duplicates).

## Running your migration

```
bash /app/migrate.sh
```

You can inspect the collection at any point with `mongosh orders_db`.

## Grading

Grading is fully automated and outcome-based — it only inspects the final
state of `orders_db.orders` (plus re-running `/app/migrate.sh` once to
check idempotency). It does not inspect your code or approach. You will
not have access to the grading ground truth.
