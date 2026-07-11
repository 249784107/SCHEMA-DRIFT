"""
Phase 1: structural fingerprinting + normalization.

Detects which raw representation a document uses (purely from structure,
never from an explicit version tag, since the task states those aren't
reliably present) and converts it into a common internal shape:

    {
        "order_id": str,
        "customer_id": str,
        "status": str,
        "amount_minor_units": int,
        "currency": str,
        "line_items": [ {"product_id": str, "quantity": int, "unit_price_minor_units": int}, ... ],
        "created_at": str,
        "_lc": int | None,
        "rank": int,           # structural generation rank, higher = later generation
        "already_unified": bool,
    }

The `rank` is derived purely from which representation each field uses,
not from any hidden version number. It only needs to preserve the correct
*relative order* between any two representations for the fallback
"highest generation wins" rule to behave correctly -- and it does, because
each later generation strictly upgrades either the price encoding or the
line-item encoding (never regresses).
"""

def _price_rank_and_value(doc):
    """Returns (rank_contribution, amount_minor_units, currency)."""
    if "totalPrice" in doc and isinstance(doc["totalPrice"], dict):
        tp = doc["totalPrice"]
        return 3, int(tp["amount"]), tp.get("currency", "USD")
    if "price" in doc:
        p = doc["price"]
        if isinstance(p, str):
            # e.g. "$234.16"
            cleaned = p.replace("$", "").replace(",", "").strip()
            return 2, round(float(cleaned) * 100), "USD"
        if isinstance(p, (int, float)):
            return 1, round(float(p) * 100), "USD"
    # already-unified shape
    if "price" in doc and isinstance(doc["price"], dict) and "amount_minor_units" in doc["price"]:
        return 3, int(doc["price"]["amount_minor_units"]), doc["price"].get("currency", "USD")
    raise ValueError(f"unrecognized price representation: {doc.keys()}")


def _line_items_rank_and_value(doc):
    """Returns (rank_contribution, normalized_line_items)."""
    if "items" in doc:
        out = []
        for it in doc["items"]:
            out.append({
                "product_id": it["sku"],
                "quantity": int(it["qty"]),
                "unit_price_minor_units": round(float(it["unitPrice"]) * 100),
            })
        return 0, out
    if "lineItems" in doc:
        out = []
        for it in doc["lineItems"]:
            # supports both the "productRef/quantity/price" generator shape
            # and a defensive fallback for a sku-keyed variant, in case a
            # generation encodes it that way too.
            pid = it.get("productRef", it.get("sku"))
            qty = it.get("quantity", it.get("qty"))
            price = it.get("price", it.get("unitPrice"))
            out.append({
                "product_id": pid,
                "quantity": int(qty),
                "unit_price_minor_units": round(float(price) * 100),
            })
        return 1, out
    if "line_items" in doc:
        # already-unified shape
        return 1, [
            {
                "product_id": li["product_id"],
                "quantity": int(li["quantity"]),
                "unit_price_minor_units": int(li["unit_price_minor_units"]),
            }
            for li in doc["line_items"]
        ]
    raise ValueError(f"unrecognized line-items representation: {doc.keys()}")


def is_already_unified(doc):
    return (
        "order_id" in doc
        and isinstance(doc.get("price"), dict)
        and "amount_minor_units" in doc.get("price", {})
        and "line_items" in doc
    )


def normalize(raw_doc):
    already = is_already_unified(raw_doc)
    price_rank, amount_minor, currency = _price_rank_and_value(raw_doc)
    items_rank, line_items = _line_items_rank_and_value(raw_doc)

    if already:
        # This document is already in unified form from a prior migration
        # run. Its rank must come from the stored schema_generation field,
        # not be recomputed structurally -- recomputing would always yield
        # the "latest representation" rank (totalPrice+lineItems shape),
        # silently discarding which raw generation it actually originated
        # from and breaking idempotency across repeated migration runs.
        rank = raw_doc.get("schema_generation", price_rank * 2 + items_rank)
    else:
        rank = price_rank * 2 + items_rank  # monotonic w.r.t. generation, see module docstring

    order_id = raw_doc.get("order_id") or raw_doc.get("orderId")
    customer_id = raw_doc.get("customer_id") or raw_doc.get("custId")
    created_at = raw_doc.get("created_at") or raw_doc.get("createdAt")

    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "status": raw_doc["status"],
        "amount_minor_units": amount_minor,
        "currency": currency,
        "line_items": line_items,
        "created_at": created_at,
        "_lc": raw_doc.get("_lc"),
        "rank": rank,
        "already_unified": already,
    }
