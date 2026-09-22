import os
import pandas as pd
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

notion_key = os.getenv("notion_key")
if not notion_key:
    raise RuntimeError("Missing 'notion_key' in .env")

notion = Client(auth=notion_key)
LOCAL_DB_FILE = 'local_database.csv'
NEEDS_CLEANUP_FILE = 'needs_notion_cleanup.csv'

def load_known_words() -> set:
    """
    Load the full set of already-processed words from disk.

    This is the persistent, durable record of "have I already made a
    flashcard for this word" — flashcards.csv is an ephemeral per-run
    export that gets imported into Anki and then deleted, so it can't be
    relied on to survive across runs. This file is what does that job.
    See issue #7.

    Call this once per run and reuse the result (pass it into is_known_word
    and mark_word_known) instead of letting each of them reload the CSV,
    which made processing a word bank O(n^2) in file I/O. See issue #4.
    """
    try:
        df = pd.read_csv(LOCAL_DB_FILE)
        return set(df.iloc[:, 0].astype(str).str.strip().str.lower().dropna())
    except (pd.errors.EmptyDataError, FileNotFoundError):
        return set()

def is_known_word(word: str, known_words: set = None) -> bool:
    """
    Return True if this word has already been processed.

    Pass in a `known_words` set from load_known_words() to check against
    an in-memory set instead of re-reading the CSV; if omitted, it's loaded
    fresh (handy for one-off calls, but avoid this inside a loop).
    """
    if known_words is None:
        known_words = load_known_words()
    return word.strip().lower() in known_words

def _file_ends_with_newline(path: str) -> bool:
    with open(path, 'rb') as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b'\n'

def mark_word_known(word: str, known_words: set = None):
    """
    Record `word` as processed in the persistent local database.

    This used to be bundled with the Notion archive call in a single
    mark_word_done(); it's now split out so the caller can wrap just the
    local-write half (this + the flashcards.csv append) in a critical
    section, and treat Notion archiving as a separate, retryable step.
    See issues #3 and #7.
    """
    word = word.strip()
    normalized = word.lower()

    if known_words is None:
        known_words = load_known_words()

    if normalized in known_words:
        return

    file_exists = os.path.exists(LOCAL_DB_FILE) and os.path.getsize(LOCAL_DB_FILE) > 0
    # Guard against a prior run leaving the file without a trailing
    # newline (e.g. process killed mid-write) — appending straight onto
    # that would silently merge two words into one corrupted row. See
    # issue #2.
    needs_leading_newline = file_exists and not _file_ends_with_newline(LOCAL_DB_FILE)
    with open(LOCAL_DB_FILE, mode='a', newline='', encoding='utf-8') as f:
        if not file_exists:
            f.write('Word\n')
        elif needs_leading_newline:
            f.write('\n')
        f.write(f'{word}\n')
        f.flush()
        os.fsync(f.fileno())
    known_words.add(normalized)

def record_needs_notion_cleanup(word: str, page_id: str):
    """
    Track a Notion page whose archive attempt failed, so the desync is
    visible in a file you can inspect instead of just a warning that
    scrolls off the console — and so it can be retried. See issue #3.
    """
    file_exists = os.path.exists(NEEDS_CLEANUP_FILE) and os.path.getsize(NEEDS_CLEANUP_FILE) > 0
    with open(NEEDS_CLEANUP_FILE, mode='a', newline='', encoding='utf-8') as f:
        if not file_exists:
            f.write('Word,PageID\n')
        f.write(f'{word},{page_id}\n')

def clear_needs_notion_cleanup(page_id: str):
    """Remove `page_id` from the cleanup list once it archives successfully."""
    if not os.path.exists(NEEDS_CLEANUP_FILE) or os.path.getsize(NEEDS_CLEANUP_FILE) == 0:
        return
    df = pd.read_csv(NEEDS_CLEANUP_FILE)
    df = df[df['PageID'].astype(str) != str(page_id)]
    df.to_csv(NEEDS_CLEANUP_FILE, index=False)

def try_archive_notion_page(word: str, page_id: str) -> bool:
    """
    Attempt to archive a Notion page, returning whether it succeeded.

    On failure, records it to needs_notion_cleanup.csv instead of just
    printing a warning, so a page stuck un-archived in Notion is both
    inspectable and gets retried automatically next time this word comes
    up as already-known (see main.py). See issue #3.
    """
    try:
        notion.pages.update(page_id=page_id, archived=True)
        clear_needs_notion_cleanup(page_id)
        return True
    except Exception as e:
        print(f"Warning: could not archive '{word}' from Notion (page_id={page_id}): {e}")
        record_needs_notion_cleanup(word, page_id)
        return False
