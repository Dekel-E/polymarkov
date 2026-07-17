"""Logical relations between markets and the arb basket math they imply.

Relations are classified once by a batched LLM call and stored; each scan then
checks them mechanically. implies(A->B): BUY_YES B + BUY_NO A is a risk-free
basket. excludes(A,B): BUY_NO A + BUY_NO B is.
"""

from __future__ import annotations

import json
import math
from typing import Any, Optional

from backend import config
from backend.agent.pricing import taker_fee

RELATION_SYSTEM_PROMPT = (
    "You classify logical relations between pairs of prediction-market "
    "questions. For each pair decide STRICT LOGICAL relations only — not "
    "correlation, not likelihood:\n"
    '- "a_implies_b": if A resolves YES then B MUST resolve YES (A is a '
    "special case of B).\n"
    '- "b_implies_a": the reverse.\n'
    '- "excludes": A and B cannot both resolve YES.\n'
    '- "none": anything weaker than the above (related topics, likely '
    "co-movement, shared entities) is NONE.\n"
    "Be conservative: when resolution criteria could diverge on technicalities "
    "(different deadlines, different sources), answer none. Return ONLY JSON: "
    '{"pairs": [{"i": <index>, "relation": "a_implies_b|b_implies_a|excludes|none", '
    '"confidence": <0..1>, "rationale": "<one short sentence>"}]}'
)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def candidate_pairs(markets: list[dict], vectors: list[list[float]]) -> list[tuple[dict, dict]]:
    """Similar-question pairs from different events (pure given vectors)."""
    pairs = []
    for i in range(len(markets)):
        for j in range(i + 1, len(markets)):
            if markets[i].get("event_id") and markets[i]["event_id"] == markets[j].get("event_id"):
                continue  # same-event exclusivity is already handled as dutch books
            if _cosine(vectors[i], vectors[j]) >= config.RELATION_SIMILARITY_MIN:
                pairs.append((markets[i], markets[j]))
            if len(pairs) >= config.RELATION_MAX_PAIRS:
                return pairs
    return pairs


def normalize_classification(pairs: list[tuple[dict, dict]], raw: Any) -> list[dict]:
    """LLM output -> relation rows (implies rows store antecedent as A)."""
    rows = []
    for item in (raw.get("pairs") if isinstance(raw, dict) else None) or []:
        try:
            a, b = pairs[int(item["i"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        relation = item.get("relation")
        confidence = float(item.get("confidence") or 0)
        if confidence < config.RELATION_MIN_CONFIDENCE or relation in (None, "none"):
            continue
        if relation == "b_implies_a":
            a, b, relation = b, a, "a_implies_b"
        if relation not in ("a_implies_b", "excludes"):
            continue
        rows.append(
            {
                "relation": "implies" if relation == "a_implies_b" else "excludes",
                "a_slug": a["slug"],
                "b_slug": b["slug"],
                "a_question": a["question"][:200],
                "b_question": b["question"][:200],
                "a_yes_token": a["yes_token_id"],
                "a_no_token": a["no_token_id"],
                "b_yes_token": b["yes_token_id"],
                "b_no_token": b["no_token_id"],
                "confidence": confidence,
                "rationale": str(item.get("rationale") or "")[:200],
            }
        )
    return rows


def _basket(legs: list[dict], question: str, min_edge: float) -> Optional[dict]:
    """Shared basket math: N legs, payout >= $1 guaranteed."""
    cost = sum(l["price"] for l in legs)
    fees = sum(taker_fee("other", l["price"]) for l in legs)
    profit = 1.0 - cost - fees
    if profit < min_edge:
        return None
    shares = min(l["size"] for l in legs)
    shares = min(shares, config.ARB_MAX_SIZE_USD / max(l["price"] for l in legs))
    if shares <= 0:
        return None
    for l in legs:
        l["size_usd"] = round(min(shares * l["price"], config.ARB_MAX_SIZE_USD), 2)
        del l["size"]
    return {
        "type": "correlation",
        "question": question,
        "event_title": "",
        "cost_per_share": round(cost, 4),
        "fees_per_share": round(fees, 4),
        "profit_per_share": round(profit, 4),
        "roi_pct": round(profit / cost * 100, 2),
        "max_shares": round(shares, 2),
        "guaranteed_profit_usd": round(profit * shares, 2),
        "legs": legs,
    }


def implies_opportunity(
    relation: dict,
    b_yes_asks: list[tuple[float, float]],
    a_no_asks: list[tuple[float, float]],
    min_edge: float = config.ARB_MIN_EDGE,
) -> Optional[dict]:
    if not b_yes_asks or not a_no_asks:
        return None
    legs = [
        {"slug": relation["b_slug"], "side": "BUY_YES", "price": b_yes_asks[0][0], "size": b_yes_asks[0][1]},
        {"slug": relation["a_slug"], "side": "BUY_NO", "price": a_no_asks[0][0], "size": a_no_asks[0][1]},
    ]
    if any(l["price"] <= 0 for l in legs):
        return None
    return _basket(
        legs,
        f"implies violation: “{relation['a_question']}” priced above “{relation['b_question']}”",
        min_edge,
    )


def excludes_opportunity(
    relation: dict,
    a_no_asks: list[tuple[float, float]],
    b_no_asks: list[tuple[float, float]],
    min_edge: float = config.ARB_MIN_EDGE,
) -> Optional[dict]:
    if not a_no_asks or not b_no_asks:
        return None
    legs = [
        {"slug": relation["a_slug"], "side": "BUY_NO", "price": a_no_asks[0][0], "size": a_no_asks[0][1]},
        {"slug": relation["b_slug"], "side": "BUY_NO", "price": b_no_asks[0][0], "size": b_no_asks[0][1]},
    ]
    if any(l["price"] <= 0 for l in legs):
        return None
    return _basket(
        legs,
        f"excludes violation: “{relation['a_question']}” + “{relation['b_question']}” overpriced together",
        min_edge,
    )


def build_classification_prompt(pairs: list[tuple[dict, dict]]) -> str:
    payload = [
        {"i": i, "A": a["question"], "B": b["question"]}
        for i, (a, b) in enumerate(pairs)
    ]
    return json.dumps({"pairs": payload}, ensure_ascii=False)
