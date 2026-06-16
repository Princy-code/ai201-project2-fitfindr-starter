# FitFindr 🛍️

A multi-tool AI agent that helps you find secondhand pieces and figure out how to wear them. Describe what you want in plain language; FitFindr searches mock listings, suggests an outfit using your wardrobe, and writes a shareable fit card — and handles the cases where a tool returns nothing.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: source .venv/Scripts/activate
pip install -r requirements.txt
```

Create a `.env` in the repo root (already gitignored):
```
GROQ_API_KEY=your_key_here
```
Free key at [console.groq.com](https://console.groq.com). LLM: Groq `llama-3.3-70b-versatile`.

Run the app:
```bash
python app.py        # opens the URL printed in the terminal (usually http://localhost:7860)
```
Run the tests:
```bash
pytest tests/
```

## Tool Inventory

Documented signatures match `tools.py` exactly.

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings(description, size, max_price)` | `description: str`, `size: str \| None`, `max_price: float \| None` | `list[dict]` of listings sorted by relevance (empty list on no match) | Find listings matching keywords, with optional size + price filters. |
| `suggest_outfit(new_item, wardrobe)` | `new_item: dict`, `wardrobe: dict` | `str` outfit suggestion | Pair the found item with the user's owned pieces (or give general advice if the wardrobe is empty). |
| `create_fit_card(outfit, new_item)` | `outfit: str`, `new_item: dict` | `str` caption | Turn the outfit into a casual, shareable OOTD caption. |

## Planning Loop

The loop is **conditional on the search result**, not a fixed pipeline. `run_agent` (`agent.py`):

1. `_parse_query` extracts `description`, `size`, `max_price` from the natural-language query via regex (deterministic and free — no LLM needed to pull structured filters out of a short phrase).
2. Calls `search_listings`.
3. **Branches:** if the result is empty, it writes `session["error"]` and returns early — it does **not** call `suggest_outfit` or `create_fit_card`. If non-empty, it sets `selected_item = results[0]` and proceeds.
4. Calls `suggest_outfit`, then `create_fit_card`, then returns the session.

So an impossible query runs one tool and returns a message; a matchable query runs all three.

## State Management

One `session` dict per interaction is the single source of truth. Each step writes its result into the session and later steps read from it — the user never re-enters anything:

- `search_results` → top item copied to `selected_item`
- `selected_item` → passed into `suggest_outfit` → `outfit_suggestion`
- `outfit_suggestion` + `selected_item` → passed into `create_fit_card` → `fit_card`
- `error` is `None` on success, a string when the run ended early.

`run_agent` returns the whole session so the UI can read every value.

## Interaction Walkthrough

**User query:** "looking for a vintage graphic tee under $30" (Example wardrobe)

**Step 1 — Tool called:** `search_listings`
- Input: `description="looking for a vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why this tool: every interaction starts by finding candidate items; nothing downstream can run without a selected item.
- Output: a ranked list of matching tees; the top one (`selected_item`) is the bootleg-style graphic tee at $24.

**Step 2 — Tool called:** `suggest_outfit`
- Input: `new_item=selected_item`, `wardrobe=example_wardrobe`
- Why this tool: results were non-empty, so the loop proceeds to styling. `selected_item` flows from session state.
- Output: a concrete outfit pairing the tee with named wardrobe pieces (e.g. baggy jeans, chunky sneakers).

**Step 3 — Tool called:** `create_fit_card`
- Input: `outfit=outfit_suggestion`, `new_item=selected_item`
- Why this tool: the styled outfit exists, so the agent produces the shareable caption.
- Output: a 2–4 sentence OOTD caption naming the tee, its price, and platform.

**Final output to user:** three panels — top listing, outfit idea, fit card.

## Error Handling and Fail Points

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the query/filters | Returns `[]`; the loop sets `session["error"]` naming the query + active filters and suggesting fixes, then stops without calling the other tools. |
| `suggest_outfit` | Empty wardrobe (and LLM errors) | Empty wardrobe → general styling advice (normal branch). LLM exception → caught, returns a short fallback string; never raises. |
| `create_fit_card` | Empty / whitespace `outfit` string | Returns a descriptive error string before any LLM call; never raises. |

Concrete example from testing: running `search_listings('designer ballgown', size='XXS', max_price=5)` returns `[]`, and the full agent then returns `error = "No listings matched \"designer ballgown\" with filters: size XXS, under $5. Try loosening the price ceiling, removing the size filter, or using broader keywords."` — and `selected_item`, `outfit_suggestion`, and `fit_card` all stay `None`.

## Spec Reflection

<!-- TODO (your words, 2-3 sentences each): -->

**One way planning.md helped during implementation:**
<!-- e.g. having the Error Handling table written first meant the no-results branch and the empty-outfit guard were decided before I wrote run_agent, so I didn't have to retrofit them. -->

**One divergence from your spec, and why:**
<!-- e.g. I added a weighted relevance score (title/style_tags worth more than description) rather than plain keyword count, because plain count ranked off-topic items too high. -->

## AI Usage

<!-- TODO (your words): describe at least 2 specific instances — which planning.md section/diagram you gave the AI, what it produced, and what you changed or overrode before using it. -->

1.
2.

## Project Structure

```
.
├── agent.py            # run_agent: planning loop + state
├── app.py              # Gradio UI; handle_query maps session → panels
├── tools.py            # search_listings, suggest_outfit, create_fit_card
├── tests/test_tools.py # one test per failure mode + happy paths
├── utils/data_loader.py
├── data/listings.json, data/wardrobe_schema.json
├── planning.md
└── requirements.txt
```