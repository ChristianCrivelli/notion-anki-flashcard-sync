from pipeline import run_gather
import db_sync
import os
import csv

FLASHCARDS_FILE = 'flashcards.csv'

def append_to_csv(word, definition):
    file_exists = os.path.exists(FLASHCARDS_FILE) and os.path.getsize(FLASHCARDS_FILE) > 0
    with open(FLASHCARDS_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Word', 'Definition'])
        writer.writerow([word, definition])
        f.flush()
        os.fsync(f.fileno())

# Pull the latest known-words database from GitHub before we decide what's
# already known, so two machines running this independently stay in sync.
# Now that gather.py also runs this same pull/push on a schedule in GitHub
# Actions (see issue #8), this also picks up anything the cloud run
# already processed since you last ran this by hand.
db_sync.pull_latest()

results = run_gather(append_to_csv)

summary = f"\nDone. {results['succeeded']} saved, {results['skipped']} skipped, {results['failed']} failed."
if results['cleaned_up']:
    summary += f" ({results['cleaned_up']} stray Notion page(s) cleaned up.)"
print(summary)

# Push any database changes (new known words, cleaned-up cleanup entries)
# back to GitHub so other machines — including the next scheduled Actions
# run — see them next time they pull.
db_sync.push_changes(commit_message=f"Add {results['succeeded']} new word(s) to known-words database")
