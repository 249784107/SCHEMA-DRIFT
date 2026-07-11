"""
Phase 2: conflict resolution, implementing CONFLICT_RESOLUTION_RULES.md's
disclosed, total precedence order:

  1. Terminal status protection (status field only): cancelled/refunded
     beat any non-terminal status, regardless of clock/generation.
  2. Logical clock: when 2+ candidates carry an explicit _lc, the field
     value from the highest _lc wins (never allowed to override rule 1
     for the status field).
  3. Schema-only generation precedence: when candidates agree on a
     field's real value and differ only in representation, the highest-
     generation representation is adopted (a no-op for the value itself).
  4. Fallback: highest generation wins for any remaining real conflict.

For non-status fields, rules 3 and 4 collapse to the same action (take the
highest-rank candidate's value), since a schema-only match by definition
already agrees on value -- so which candidate you take doesn't change the
result. This module still names them separately in comments for clarity
against the rules doc.
"""

STATUS_ORDER = {"pending": 0, "processing": 1, "shipped": 2, "delivered": 3}
TERMINAL = {"cancelled", "refunded"}


def _resolve_status(candidates):
    terminal_candidates = [c for c in candidates if c["status"] in TERMINAL]
    if terminal_candidates:
        # Rule 1: terminal wins outright. If multiple terminal candidates
        # (e.g. a duplicate/schema-only-shaped terminal update), break the
        # tie with logical clock if available, else just take any -- the
        # status value among terminal candidates for the same order is
        # expected to agree in well-formed data.
        with_lc = [c for c in terminal_candidates if c["_lc"] is not None]
        winner = max(with_lc, key=lambda c: c["_lc"]) if len(with_lc) >= 1 else terminal_candidates[0]
        return winner["status"]

    # Rule 2: logical clock, if 2+ non-terminal candidates carry it.
    with_lc = [c for c in candidates if c["_lc"] is not None]
    if len(with_lc) >= 2:
        winner = max(with_lc, key=lambda c: c["_lc"])
        return winner["status"]

    # Fallback within status: state-machine order (further along wins).
    winner = max(candidates, key=lambda c: STATUS_ORDER.get(c["status"], -1))
    return winner["status"]


def _resolve_scalar_field(candidates, field):
    values = {c[field] for c in candidates}
    if len(values) == 1:
        # All candidates agree on the real value -- pick the representation
        # from the highest-ranked (latest) generation (rule 3, schema-only).
        winner = max(candidates, key=lambda c: c["rank"])
        return winner[field]

    # Real disagreement. Rule 2: logical clock if 2+ candidates carry it.
    with_lc = [c for c in candidates if c["_lc"] is not None]
    if len(with_lc) >= 2:
        winner = max(with_lc, key=lambda c: c["_lc"])
        return winner[field]

    # Rule 4: fallback, highest generation wins.
    winner = max(candidates, key=lambda c: c["rank"])
    return winner[field]


def _resolve_line_items(candidates):
    # Business-meaningful equality check: same set of (product_id, quantity)
    # pairs, ignoring unit_price_minor_units representation noise, decides
    # whether this is a schema-only change or a real conflict.
    def signature(li_list):
        return tuple(sorted((li["product_id"], li["quantity"]) for li in li_list))

    sigs = {signature(c["line_items"]) for c in candidates}
    if len(sigs) == 1:
        winner = max(candidates, key=lambda c: c["rank"])
        return winner["line_items"]

    with_lc = [c for c in candidates if c["_lc"] is not None]
    if len(with_lc) >= 2:
        winner = max(with_lc, key=lambda c: c["_lc"])
        return winner["line_items"]

    winner = max(candidates, key=lambda c: c["rank"])
    return winner["line_items"]


def resolve_order(order_id, candidates):
    """candidates: list of normalized docs (see normalize.py) for one order_id."""
    status = _resolve_status(candidates)
    amount_minor_units = _resolve_scalar_field(candidates, "amount_minor_units")
    currency = _resolve_scalar_field(candidates, "currency")
    line_items = _resolve_line_items(candidates)
    customer_id = _resolve_scalar_field(candidates, "customer_id")

    # created_at / schema_generation: representational metadata, not
    # subject to conflict rules -- take from the highest-rank candidate for
    # consistency, since it reflects the most current representation.
    winner_meta = max(candidates, key=lambda c: c["rank"])

    result = {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": status,
        "price": {"amount_minor_units": amount_minor_units, "currency": currency},
        "line_items": line_items,
        "created_at": winner_meta["created_at"],
        "schema_generation": winner_meta["rank"],
    }
    lcs = [c["_lc"] for c in candidates if c["_lc"] is not None]
    if lcs:
        result["_lc"] = max(lcs)
    return result
