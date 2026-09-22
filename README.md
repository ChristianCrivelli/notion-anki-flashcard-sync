# flashcards

![License](https://img.shields.io/badge/license-MIT-blue.svg)

Turns vocabulary words sitting in a Notion database into Anki flashcards, automatically. Gathering (Notion lookup + definition fetch) runs on a schedule in the cloud via GitHub Actions; delivery into Anki happens locally via AnkiConnect, since AnkiConnect only ever listens on `localhost` and can't be reached from a cloud runner.

## How it works

The pipeline is split into two stages that hand off through the repo itself:

1. **Gather (cloud, scheduled)** — `src/gather.py`, run daily by `.github/workflows/gather.yml`. It pulls any new rows from your Notion database, looks up a definition for each word (Free Dictionary API → Merriam-Webster → Gemini, in that order, falling through on failure), records processed words in `local_database.csv` so they're never looked up twice, archives the Notion page once it's been processed, and appends each finished (word, definition) pair to `pending_cards.csv`. All three files are committed and pushed back to the repo automatically (`src/db_sync.py`), so the queue is always waiting for you wherever you next run the delivery step.

2. **Deliver (local, manual)** — `src/push_to_anki.py`, run by hand whenever Anki is open. It drains `pending_cards.csv` into an Anki deck as **"Basic (and reversed card)"** notes — one note per word, which Anki auto-expands into both a word→definition and a definition→word review card. Anki's own duplicate detection is used to skip words already in the deck; anything that genuinely fails to add stays queued for the next run instead of being lost.

If you'd rather not set up GitHub Actions at all, `src/main.py` runs the same gather logic in one local pass and writes straight to `flashcards.csv` for a manual Anki import — no AnkiConnect required.

## Setup

### 1. Notion database

Create a Notion database with one title-type property (any name works) — each row's title is read as the word to look up. That's the entire schema requirement; `src/word_bank.py` finds whichever property is the title column on its own.

### 2. API keys

Copy `config/.env.example` to `.env` **at the repo root** and fill in:

| Variable | Required | Purpose |
|---|---|---|
| `notion_key` | yes | Notion internal integration token, shared with your database |
| `database` | yes | The Notion database ID |
| `gemini_key` | yes | Google Gemini API key — last-resort definition fallback |
| `webster_key` | yes | Merriam-Webster Collegiate Dictionary API key — second fallback, tried before Gemini |
| `anki_deck` | no | Anki deck new cards are pushed into; defaults to `"Word Bank"` if unset |

See `config/README.md` for the same table in place.

### 3. Python environment

```
pip install -r requirements.txt
```

### 4. AnkiConnect

Install the AnkiConnect add-on in Anki: **Tools → Add-ons → Get Add-ons…**, enter code `2055492159`, restart Anki. The default AnkiConnect config (`webBindAddress: 127.0.0.1`, `webBindPort: 8765`) already matches what `src/push_to_anki.py` expects, so no further configuration is needed. Anki has to be open whenever you run `src/push_to_anki.py`; the very first request may trigger a one-time "allow this connection?" prompt inside Anki. The note type used, "Basic (and reversed card)", ships with Anki by default.

### 5. Scheduled cloud gather (optional)

To run the gather step on a schedule instead of by hand:

1. Push this repo to your own GitHub repository.
2. Add repo secrets under **Settings → Secrets and variables → Actions**: `NOTION_KEY`, `NOTION_DATABASE`, `GEMINI_KEY`, `WEBSTER_KEY` — matching your `.env` values.
3. `.github/workflows/gather.yml` runs daily at 13:00 UTC by default (edit the `cron` line to change that) and can also be triggered manually from the repo's Actions tab (`workflow_dispatch`).

### 6. Local delivery

Whenever you want to check for and push queued cards, open Anki and run (from the repo root):

```
python src/push_to_anki.py
```

It's safe to run any time — it no-ops quietly if `pending_cards.csv` is empty or missing.

## Files

```
src/            pipeline code
config/         .env.example + setup notes
.github/workflows/   scheduled gather workflow
requirements.txt
README.md
LICENSE
.gitignore
```

| File | Role |
|---|---|
| `src/pipeline.py` | Shared gather logic (Notion fetch → definition lookup → mark known → archive), used by both `main.py` and `gather.py` |
| `src/main.py` | One-shot local run: gather + write `flashcards.csv` for manual Anki import (no AnkiConnect needed) |
| `src/gather.py` | Headless entry point for the scheduled cloud run: gather + write `pending_cards.csv` |
| `src/push_to_anki.py` | Local AnkiConnect delivery step: drains `pending_cards.csv` into Anki |
| `src/word_bank.py` | Reads word entries from the Notion database |
| `src/definition.py` | Definition lookup chain: Free Dictionary API → Merriam-Webster → Gemini |
| `src/local_database.py` | The persistent known-words database, plus Notion archive-retry logic |
| `src/db_sync.py` | Git-based sync of the database/queue CSVs across machines |
| `src/notion_utils.py` | Shared Notion Data Source API helpers (pagination, data source resolution) |
| `src/clean_notion.py` | Utility to bulk-archive every row in the Notion database — a reset button |
| `config/.env.example` | Template for the `.env` file (copy to the repo root, not here) |
| `config/README.md` | Short note on the required API keys |

All scripts are run from the **repo root** (e.g. `python src/main.py`), not from inside `src/` — that's what lets them find `.env`, `local_database.csv`, `pending_cards.csv`, and the rest of the data files sitting at the root alongside the code.

## Roadmap

Open design/implementation work is tracked in [GitHub Issues](../../issues), including ingesting Readwise highlights as a second card source.

## License

MIT — see [LICENSE](LICENSE).
