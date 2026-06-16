"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""
from __future__ import annotations

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parsing ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description / size / max_price from a natural-language query using
    regex. Chosen over an LLM call here because it's deterministic, free, and
    fast — parsing structured filters out of a short phrase doesn't need a model,
    and keeping it rule-based means the same query always produces the same search.
    """
    text = query or ""
    max_price = None
    size = None

    # max_price: "under $30", "under 30", "less than $40", "$25"
    price_match = re.search(r"(?:under|less than|below|max|<)\s*\$?\s*(\d+(?:\.\d+)?)", text, re.I)
    if not price_match:
        price_match = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if price_match:
        max_price = float(price_match.group(1))

    # size: "size M", "size 8", "in size XL", "sz M"
    size_match = re.search(r"\b(?:size|sz)\s+([a-z0-9/]+)", text, re.I)
    if size_match:
        size = size_match.group(1).upper()

    # description: strip the price/size phrases so they don't pollute keyword search
    description = text
    if price_match:
        description = description.replace(price_match.group(0), " ")
    if size_match:
        description = description.replace(size_match.group(0), " ")
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    interaction and returns the completed session dict.

    The loop is conditional, not a fixed pipeline: after search_listings runs it
    branches on whether the result is empty. On empty it writes an error and
    returns early WITHOUT calling the downstream tools; only on a non-empty result
    does it proceed to suggest_outfit and create_fit_card.
    """
    session = _new_session(query, wardrobe)

    # Step 2 — parse the query into structured search parameters.
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3 — search. This is the decision point for the whole loop.
    session["search_results"] = search_listings(
        description=parsed["description"],
        size=parsed["size"],
        max_price=parsed["max_price"],
    )

    if not session["search_results"]:
        # BRANCH A: nothing matched -> set a specific, actionable error and STOP.
        filters = []
        if parsed["size"]:
            filters.append(f"size {parsed['size']}")
        if parsed["max_price"] is not None:
            filters.append(f"under ${parsed['max_price']:g}")
        filter_note = f" with filters: {', '.join(filters)}" if filters else ""
        session["error"] = (
            f"No listings matched \"{parsed['description'] or query}\"{filter_note}. "
            f"Try loosening the price ceiling, removing the size filter, or using "
            f"broader keywords (e.g. \"tee\" instead of \"graphic band tee\")."
        )
        return session

    # BRANCH B: we have results — continue the loop.
    # Step 4 — select the top-ranked item and store it in session state.
    session["selected_item"] = session["search_results"][0]

    # Step 5 — suggest an outfit. selected_item flows in from session state;
    # the user never re-enters it. suggest_outfit handles an empty wardrobe itself.
    session["outfit_suggestion"] = suggest_outfit(
        new_item=session["selected_item"],
        wardrobe=session["wardrobe"],
    )

    # Step 6 — turn the outfit into a shareable fit card. outfit_suggestion and
    # selected_item both come from session state set in earlier steps.
    session["fit_card"] = create_fit_card(
        outfit=session["outfit_suggestion"],
        new_item=session["selected_item"],
    )

    # Step 7 — return the completed session.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")