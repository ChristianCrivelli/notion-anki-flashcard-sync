"""
Shared "gather" pipeline: fetch words from Notion, look up definitions,
mark them known, and archive processed Notion pages.

This is the part that's identical whether it's run locally by hand
(main.py, writing straight to flashcards.csv for a manual Anki import) or
headlessly on a schedule in GitHub Actions (gather.py, writing to
pending_cards.csv for the local AnkiConnect push in issue #9). The only
thing that differs between those two run modes is *where the finished
(word, definition) pairs get written* — so that part is passed in as a
callback instead of living here. See issue #8.
"""
from local_database import load_known_words, is_known_word, mark_word_known, try_archive_notion_page
from definition import get_definition
from word_bank import get_words
import signal


def run_gather(write_card):
    """
    Run one full gather pass: pull new words from Notion, look up a
    definition for anything not already known, and hand each finished
    (word, definition) pair to `write_card(word, definition)`.

    `write_card` runs inside the same critical section as
    mark_word_known() (SIGINT deferred around both, same as the original
    main.py — see issue #7) so a Ctrl+C can't land between "written to
    the output file" and "recorded as known locally" and silently
    duplicate or drop a word. If `write_card` raises, the word is NOT
    marked known or archived, so it will be retried on the next run.

    Returns a dict of counts: succeeded, skipped, failed, cleaned_up.
    """
    word_bank = get_words()
    print(f"Words fetched from Notion: {len(word_bank)}")

    # local_database.csv (not the per-run output file) is the persistent
    # source of truth for "already processed" words. See issues #4 and #7.
    known_words = load_known_words()

    succeeded = 0
    skipped = 0
    failed = 0
    cleaned_up = 0

    for page_id, word in word_bank:
        if is_known_word(word, known_words):
            # Already known locally, but Notion still has this page
            # un-archived — almost certainly a previous run's archive
            # attempt failed and only printed a warning. Retry it now
            # instead of leaving it stuck in Notion forever. See issue #3.
            if try_archive_notion_page(word, page_id):
                cleaned_up += 1
            print(f"Skipping '{word}' (already processed)")
            skipped += 1
            continue

        try:
            definition = get_definition(word)

            old_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
            try:
                write_card(word, definition)
                mark_word_known(word, known_words)
            finally:
                signal.signal(signal.SIGINT, old_handler)

            try_archive_notion_page(word, page_id)
            print(f"✓ '{word}' saved")
            succeeded += 1
        except Exception as e:
            print(f"✗ Failed on '{word}': {e}")
            failed += 1

    return {
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "cleaned_up": cleaned_up,
    }
