"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  -> list[dict]
    suggest_outfit(new_item, wardrobe)             -> str
    create_fit_card(outfit, new_item)              -> str
"""
from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _chat(system: str, user: str, temperature: float = 0.7, max_tokens: int = 350) -> str:
    """
    Single point of contact with the LLM. Every tool that needs the model goes
    through here so error handling and config live in one place.

    Raises on API/network failure — the calling tool is responsible for catching
    and returning a graceful message so the agent never crashes.
    """
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

_STOPWORDS = {
    "a", "an", "the", "for", "with", "and", "in", "on", "of", "to", "i", "im",
    "looking", "want", "wanna", "need", "some", "something", "find", "me", "my",
    "under", "less", "than", "around", "about", "size", "is", "are",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, drop stopwords -> list of search tokens."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 1]


def _score_listing(tokens: list[str], listing: dict) -> int:
    """
    Weighted keyword-overlap score. Matches in the title or style_tags count for
    more than matches buried in the free-text description, so the most on-topic
    items float to the top.
    """
    title = listing.get("title", "").lower()
    tags = " ".join(listing.get("style_tags", [])).lower()
    category = listing.get("category", "").lower()
    colors = " ".join(listing.get("colors", [])).lower()
    brand = (listing.get("brand") or "").lower()
    desc = listing.get("description", "").lower()

    score = 0
    for tok in tokens:
        if tok in title:
            score += 3
        if tok in tags:
            score += 2
        if tok in category:
            score += 2
        if tok in colors or tok in brand:
            score += 1
        if tok in desc:
            score += 1
    return score


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive substring (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    listings = load_listings()
    tokens = _tokenize(description or "")

    results = []
    for listing in listings:
        # Hard filters first — these are non-negotiable constraints.
        if max_price is not None and listing.get("price", 0) > max_price:
            continue
        if size is not None and size.strip():
            if size.strip().lower() not in str(listing.get("size", "")).lower():
                continue

        # Relevance scoring — keep only listings that actually match a keyword.
        score = _score_listing(tokens, listing) if tokens else 1
        if score > 0:
            results.append((score, listing))

    results.sort(key=lambda pair: pair[0], reverse=True)
    return [listing for _, listing in results]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def _format_wardrobe(wardrobe: dict) -> str:
    """Render wardrobe items into a readable list for the prompt."""
    lines = []
    for item in wardrobe.get("items", []):
        colors = ", ".join(item.get("colors", []))
        tags = ", ".join(item.get("style_tags", []))
        lines.append(f"- {item.get('name')} ({item.get('category')}; {colors}; {tags})")
    return "\n".join(lines)


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1-2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key. May be empty.

    Returns:
        A non-empty string with outfit suggestions. If the wardrobe is empty,
        offers general styling advice instead of raising or returning empty.
    """
    item_desc = (
        f"{new_item.get('title', 'an item')} "
        f"(category: {new_item.get('category')}, "
        f"colors: {', '.join(new_item.get('colors', []))}, "
        f"style: {', '.join(new_item.get('style_tags', []))})"
    )

    has_items = bool(wardrobe and wardrobe.get("items"))

    if not has_items:
        # Empty-wardrobe failure mode: don't crash, give useful general advice.
        system = (
            "You are a thoughtful personal stylist. The user has not entered any "
            "wardrobe items yet, so give general styling ideas for the piece: what "
            "kinds of items pair well with it, what vibe it suits, and how to dress "
            "it up or down. Keep it to 3-4 sentences. Do not invent items the user owns."
        )
        user = f"Give general styling advice for this thrifted find: {item_desc}"
    else:
        system = (
            "You are a thoughtful personal stylist. Suggest 1-2 complete, specific "
            "outfits that combine the new item with pieces the user already owns. "
            "Reference the user's pieces by name. Keep it to 3-5 sentences and make "
            "the combinations concrete (mention fit, layering, or styling tweaks)."
        )
        user = (
            f"New item: {item_desc}\n\n"
            f"The user's wardrobe:\n{_format_wardrobe(wardrobe)}\n\n"
            f"Suggest outfits using the new item and named pieces above."
        )

    try:
        return _chat(system, user, temperature=0.7)
    except Exception as exc:
        # LLM/network failure mode: degrade gracefully, never raise to the agent.
        return (
            f"Couldn't generate a styled outfit right now ({type(exc).__name__}). "
            f"As a starting point, {new_item.get('title', 'this piece')} works well "
            f"with neutral basics in {', '.join(new_item.get('colors', ['similar'])) or 'similar'} tones."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2-4 sentence caption string. If outfit is empty/missing, returns a
        descriptive error message string — does NOT raise an exception.
    """
    # Incomplete-input failure mode: guard before spending an LLM call.
    if not outfit or not outfit.strip():
        return (
            "Can't build a fit card without an outfit suggestion. "
            "Run suggest_outfit first and pass its result in as `outfit`."
        )

    title = new_item.get("title", "this piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "secondhand")
    price_str = f"${price:g}" if isinstance(price, (int, float)) else "a steal"

    system = (
        "You write casual, authentic OOTD captions for thrift finds — the kind "
        "someone actually posts to Instagram or TikTok, not a product description. "
        "Write 2-4 sentences. Mention the item, its price, and the platform once each, "
        "naturally. Capture the outfit vibe in specific terms. A tasteful emoji or two "
        "is fine. Do not use hashtag spam."
    )
    user = (
        f"Item: {title} — {price_str} on {platform}\n"
        f"Outfit: {outfit}\n\n"
        f"Write the caption."
    )

    try:
        # Higher temperature so repeated calls on the same input read differently.
        return _chat(system, user, temperature=0.95)
    except Exception as exc:
        return (
            f"Couldn't generate a fit card right now ({type(exc).__name__}). "
            f"Snagged {title} for {price_str} on {platform} — styled it per the look above."
        )