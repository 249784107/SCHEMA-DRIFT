# Conflict Resolution Rules (Disclosed)

These rules are given to you in full. The only thing you must reverse-engineer
yourself is the set of 10 document generation shapes (see `data/orders/`).
Applying these rules correctly and consistently is what the verifier checks.

## 1. Order status state machine

Each order document has a `status` field. Valid values and their allowed
forward transitions are:

```
pending -> processing -> shipped -> delivered
pending -> cancelled
processing -> cancelled
```

`cancelled` and `refunded` are **terminal states**. A terminal state can
never be overwritten by an update carrying any other status, regardless of
timestamp or logical clock value. `refunded` can only be reached from
`delivered` or `cancelled` (a refund implies the order previously existed in
one of those states).

If two competing updates for the same order both carry non-terminal
statuses, the update further along the forward chain
(`pending < processing < shipped < delivered`) wins, **unless** rule 2 below
applies.

## 2. Logical clock field

Some (not all) update documents carry an explicit `_lc` field: a
non-negative integer logical (Lamport-style) clock, monotonically
increasing per order across the microservices that touch it.

- If **both** competing updates for a field have an `_lc` value, the update
  with the strictly higher `_lc` wins for that field, **except** where doing
  so would overwrite a terminal status (rule 1 always wins for `status`).
- If only one competing update has `_lc`, or neither does, fall through to
  rule 3.

## 3. Schema-only change / generation precedence

A "schema-only change" is a pair of update documents for the same order
where every business-meaningful field (status, price, quantity, customer
id, line items' product ids and quantities) has the **same logical value**
across both documents, and the only difference is representation: field
naming, nesting, or type encoding introduced by a later generation's schema
(e.g. `price: 19.99` vs `price: {amount: 1999, currency: "USD",
minorUnits: true}` representing the same $19.99).

For a schema-only change, the document belonging to the **higher-numbered
generation** wins (its representation is adopted in the unified output; the
underlying value does not change).

If the change is not schema-only (i.e., some business-meaningful field
actually differs) and rules 1–2 do not resolve it, proceed to rule 4.

## 4. Fallback: highest generation wins

For any remaining field-level conflict not resolved by rules 1–3, the value
from the document with the highest generation number wins.

## Full precedence order (summary)

For every field on every order, apply in this order and stop at the first
rule that resolves it:

1. **Terminal status protection** — `status` only, cancelled/refunded win over all.
2. **Logical clock** — when `_lc` present on both competing updates.
3. **Schema-only generation precedence** — when the conflict is representational only.
4. **Highest generation wins** — final fallback.

## Non-destructiveness requirement

Migration must not modify any field of any document except fields directly
involved in a resolved schema-mapping or conflict. All other fields must be
byte-identical pre- and post-migration. Re-running the migration against an
already-migrated collection must be a no-op.
