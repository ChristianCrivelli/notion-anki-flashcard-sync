"""
Headless entry point for the scheduled GitHub Actions run — see issue #8
and .github/workflows/gather.yml.

Same gather logic as main.py (via pipeline.run_gather), but instead of
writing to flashcards.csv — the ephemeral file you import into Anki by
hand and then delete — it appends to pending_cards.csv, a queue that
accumulates new cards across runs until the local AnkiConnect push step
(issue #9) drains it into Anki and clears it. pending_cards.csv is
git-synced like the rest of the database (see db_sync.py), so it
survives the gap between the cloud run that fills it and the local run
that empties it.

Run manually with `python src/gather.py` (from the repo root); it needs
the same .env / secrets as main.py (notion_key, database, gemini_key,
webster_key).
"""
from pipeline import run_gather
import db_sync
import os
import csv
import sys

PENDING_CARDS_FILE = 'pending_cards.csv'


def append_to_pending(word, definition):
    file_exists = os.path.exists(PENDING_CARDS_FILE) and os.path.getsize(PENDING_CARDS_FILE) > 0
    with open(PENDING_CARDS_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Word', 'Definition'])
        writer.writerow([word, definition])
        f.flush()
        os.fsync(f.fileno())


def main():
    db_sync.pull_latest()

    results = run_gather(append_to_pending)

    summary = f"\nDone. {results['succeeded']} saved, {results['skipped']} skipped, {results['failed']} failed."
    if results['cleaned_up']:
        summary += f" ({results['cleaned_up']} stray Notion page(s) cleaned up.)"
    print(summary)

    db_sync.push_changes(
        commit_message=f"Gather run: {results['succeeded']} new word(s) queued for Anki"
    )

    if results['failed']:
        # Non-zero exit so a run with failures shows up red in the Actions
        # tab instead of silently looking green.
        sys.exit(1)


if __name__ == '__main__':
    main()
