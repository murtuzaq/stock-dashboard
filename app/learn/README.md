# The teaching library

Each topic that the Info Wizard can explain is **one Markdown file** under `topics/<category>/`. The folder name is the
default category. Images go in `assets/`.

## Writing a topic

```
+++
id = "stop-loss"
title = "Stop-loss"
category = "Strategy"                       # optional: defaults to the folder name
aliases = ["stop loss", "stop-loss order"]  # other names for it; also what auto-linking looks for
related = ["take-profit", "atr-stop"]       # topics offered under "Related topics"
summary = "One or two sentences."           # shown in listings and usable as a tooltip
autolink = true                             # false for ambiguous words (e.g. "range")
+++
The body, in Markdown. Link another topic with [take-profit](topic:take-profit).
Show a picture from assets/ with ![Candle anatomy](candle-anatomy.png).
```

- `id` and `title` are required. `id`: lowercase letters, digits and `-`.
- The header is TOML between the two `+++` lines; the rest is Markdown (headings, lists, bold, tables, images).
- **Writing for a beginner:** start with one plain sentence, then "why it matters", then how it appears in this
  dashboard. Say what it *cannot* tell you.

## What happens when you add a file
- Anywhere the dashboard shows generated text (indicator legends, strategy summaries, rule descriptions), the
  topic's **title and aliases** become clickable while View > Info Wizard is on. Nothing else to edit.
- To make a *fixed* piece of the UI (an Explorer row, a table column title, a label) open the topic, add it to
  `app/core/learn/ui_terms.py`.
- Set `autolink = false` if the word is too common to link everywhere; it then only opens where `ui_terms.py`
  points to it.

## Checking your work
`pytest tests/test_learn.py` validates the whole library: bad TOML, duplicate ids or aliases, links to topics that
do not exist, missing images, empty bodies, and that every id in `ui_terms.py` exists.

## Requests from users
Users right-click a word and choose *Request info on...*; each request is saved in `info_requests.json` at the repo
root (or sent to you from their copy):

```json
{"version": 1, "requests": [{"text": "Sharpe ratio", "normalized": "sharpe ratio", "count": 3,
  "first_requested": "...", "last_requested": "...",
  "contexts": [{"symbol": "IBM", "view": "price,macd", "where": "strategy summary"}], "note": ""}]}
```

`count` is how many times it was asked for, and `contexts` shows where. To list what is still open:

```python
from learn import load_library, requests
for r in requests.pending(load_library()):
    print(r.count, r.text, r.contexts)
```

Once you add a topic whose title or alias matches a request, it moves to `requests.answered(...)` automatically.
