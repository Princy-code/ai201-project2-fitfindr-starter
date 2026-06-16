"""
tests/test_tools.py

One test per failure mode plus happy-path coverage for each tool.
Run with:  pytest tests/

The LLM-backed tools (suggest_outfit, create_fit_card) are tested with their
LLM call monkeypatched so the suite runs offline and deterministically. The
real Groq call is exercised manually via the Milestone 5 terminal commands.
"""

import tools
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(r, dict) for r in results)


def test_search_empty_results():
    # Failure mode: no match -> empty list, not an exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=40)
    assert all(item["price"] <= 40 for item in results)


def test_search_size_filter_case_insensitive():
    results = search_listings("tee", size="m", max_price=None)
    assert all("m" in str(item["size"]).lower() for item in results)


def test_search_sorted_by_relevance():
    # First result should score at least as high as the last.
    results = search_listings("vintage denim jeans", size=None, max_price=None)
    if len(results) >= 2:
        tokens = tools._tokenize("vintage denim jeans")
        assert tools._score_listing(tokens, results[0]) >= tools._score_listing(tokens, results[-1])


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_empty_wardrobe(monkeypatch):
    # Failure mode: empty wardrobe -> general advice string, never empty/exception.
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: "General styling advice here.")
    item = {"title": "Y2K Baby Tee", "category": "tops", "colors": ["pink"], "style_tags": ["y2k"]}
    out = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_with_wardrobe(monkeypatch):
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: "Pair it with your baggy jeans.")
    item = {"title": "Y2K Baby Tee", "category": "tops", "colors": ["pink"], "style_tags": ["y2k"]}
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_llm_failure_is_graceful(monkeypatch):
    # Failure mode: LLM raises -> graceful fallback string, agent does not crash.
    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(tools, "_chat", boom)
    item = {"title": "Y2K Baby Tee", "category": "tops", "colors": ["pink"], "style_tags": ["y2k"]}
    out = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(out, str) and out.strip()


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_fit_card_empty_outfit():
    # Failure mode: empty/whitespace outfit -> descriptive error string, no exception.
    item = {"title": "Y2K Baby Tee", "price": 18.0, "platform": "depop"}
    out = create_fit_card("", item)
    assert isinstance(out, str)
    assert "without an outfit" in out.lower() or "can't" in out.lower()


def test_fit_card_whitespace_outfit():
    item = {"title": "Y2K Baby Tee", "price": 18.0, "platform": "depop"}
    out = create_fit_card("   ", item)
    assert isinstance(out, str) and out.strip()


def test_fit_card_happy_path(monkeypatch):
    monkeypatch.setattr(tools, "_chat", lambda *a, **k: "thrifted this tee for $18 on depop.")
    item = {"title": "Y2K Baby Tee", "price": 18.0, "platform": "depop"}
    out = create_fit_card("Pair with baggy jeans and chunky sneakers.", item)
    assert isinstance(out, str) and out.strip()