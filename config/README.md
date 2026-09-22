# Config

`.env.example` in this folder is the template for the `.env` file the pipeline scripts load via `python-dotenv`. Copy it to `.env` **at the repo root** (not inside `config/`) and fill in your real values.

| Variable | Required | Purpose |
|---|---|---|
| `notion_key` | yes | Notion internal integration token, shared with your database |
| `database` | yes | The Notion database ID |
| `gemini_key` | yes | Google Gemini API key — last-resort definition fallback |
| `webster_key` | yes | Merriam-Webster Collegiate Dictionary API key — second fallback, tried before Gemini |
| `anki_deck` | no | Anki deck new cards are pushed into; defaults to `"Word Bank"` if unset |

See the main [README](../README.md) for the full setup walkthrough.
