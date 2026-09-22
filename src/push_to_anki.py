"""
Local AnkiConnect push: drain pending_cards.csv into Anki.

This is the local half of the cloud/local split from issue #8: the cloud
gather run (gather.py, on a GitHub Actions schedule) fills
pending_cards.csv with new (word, definition) pairs; this script -- run
on your machine, since AnkiConnect only ever listens on localhost and
can't be reached from a GitHub-hosted runner -- drains that queue into
Anki and pushes the emptied-out queue back to GitHub so the cloud run
(and any other machine) knows those words have been delivered.

Card type: only "Basic (and reversed card)" (Front=word, Back=definition)
-- one note per word, which auto-generates both the word->definition and
definition->word review cards. See issue #9's decision comment for why
this was chosen over adding a separate plain "Basic" note too.

Trigger: manual -- run `python src/push_to_anki.py` (from the repo root)
whenever you have Anki open. See issue #9.

Requires: Anki running locally with the AnkiConnect add-on installed
(listening on http://localhost:8765). The very first run may pop up an
"Allow" permission prompt inside Anki -- accept it once and it's
remembered.
"""
import os
import csv
import requests
from dotenv import load_dotenv
import db_sync

load_dotenv()

PENDING_CARDS_FILE = 'pending_cards.csv'
ANKI_CONNECT_URL = 'http://localhost:8765'
MODEL_NAME = 'Basic (and reversed card)'
DECK_NAME = os.getenv('anki_deck', 'Word Bank')
TAGS = ['flashcards-pipeline']


class AnkiConnectUnavailable(Exception):
    """Couldn't reach AnkiConnect at all (Anki not open, add-on missing, etc)."""


class AnkiConnectError(Exception):
    """AnkiConnect responded, but the request itself failed."""


def _anki_request(action, **params):
    payload = {'action': action, 'version': 6, 'params': params}
    try:
        response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
    except requests.exceptions.RequestException as e:
        raise AnkiConnectUnavailable(
            f"Could not reach AnkiConnect at {ANKI_CONNECT_URL} -- is Anki "
            f"open with the AnkiConnect add-on installed? ({e})"
        ) from e

    body = response.json()
    if not isinstance(body, dict) or 'error' not in body or 'result' not in body:
        raise AnkiConnectError(f"Unexpected AnkiConnect response: {body}")
    if body['error'] is not None:
        raise AnkiConnectError(body['error'])
    return body['result']


def _is_duplicate_error(message: str) -> bool:
    return 'duplicate' in message.lower()


def _ensure_model_exists():
    models = _anki_request('modelNames')
    if MODEL_NAME not in models:
        raise RuntimeError(
            f"Anki note type '{MODEL_NAME}' doesn't exist. This ships with "
            "Anki by default -- if it's been removed, restore it via "
            "Tools > Manage Note Types in Anki before running this again."
        )


def _ensure_deck_exists():
    decks = _anki_request('deckNames')
    if DECK_NAME not in decks:
        print(f"Deck '{DECK_NAME}' doesn't exist yet in Anki -- creating it.")
        _anki_request('createDeck', deck=DECK_NAME)


def _load_pending_rows():
    if not os.path.exists(PENDING_CARDS_FILE) or os.path.getsize(PENDING_CARDS_FILE) == 0:
        return []
    with open(PENDING_CARDS_FILE, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [(row['Word'], row['Definition']) for row in reader]


def _write_remaining_rows(rows):
    """
    Rewrite pending_cards.csv to contain only the given rows -- used to
    drain out everything that was successfully added (or was already a
    duplicate in Anki), leaving only genuine failures queued for retry.
    """
    with open(PENDING_CARDS_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Word', 'Definition'])
        for word, definition in rows:
            writer.writerow([word, definition])
        f.flush()
        os.fsync(f.fileno())


def push_pending_cards():
    """
    Drain pending_cards.csv into Anki, one addNote call per row.

    Rows that succeed OR come back as AnkiConnect duplicates are removed
    from the queue (both mean Anki already has that word); rows that fail
    for any other reason (AnkiConnect error, network hiccup) are left in
    the queue so they're retried on the next run instead of silently lost.

    Returns a dict of counts: added, duplicate, failed, remaining.
    """
    rows = _load_pending_rows()
    if not rows:
        print("pending_cards.csv is empty -- nothing to push.")
        return {'added': 0, 'duplicate': 0, 'failed': 0, 'remaining': 0}

    _ensure_model_exists()
    _ensure_deck_exists()

    added = 0
    duplicate = 0
    failed = 0
    remaining_rows = []

    for word, definition in rows:
        note = {
            'deckName': DECK_NAME,
            'modelName': MODEL_NAME,
            'fields': {'Front': word, 'Back': definition},
            'options': {'allowDuplicate': False, 'duplicateScope': 'deck'},
            'tags': TAGS,
        }
        try:
            _anki_request('addNote', note=note)
            print(f"✓ '{word}' added to Anki")
            added += 1
        except AnkiConnectError as e:
            if _is_duplicate_error(str(e)):
                print(f"Skipping '{word}' (already in Anki)")
                duplicate += 1
            else:
                print(f"✗ Failed to add '{word}': {e}")
                failed += 1
                remaining_rows.append((word, definition))

    _write_remaining_rows(remaining_rows)

    return {
        'added': added,
        'duplicate': duplicate,
        'failed': failed,
        'remaining': len(remaining_rows),
    }


def main():
    # Pull first so we're draining whatever the cloud run (or another
    # machine) most recently queued, not a stale local copy.
    db_sync.pull_latest()

    try:
        results = push_pending_cards()
    except AnkiConnectUnavailable as e:
        print(str(e))
        return
    except RuntimeError as e:
        print(f"Aborting: {e}")
        return

    summary = (f"\nDone. {results['added']} added, {results['duplicate']} already in Anki, "
               f"{results['failed']} failed.")
    if results['remaining']:
        summary += f" {results['remaining']} word(s) left queued for retry."
    print(summary)

    # No-ops quietly if pending_cards.csv didn't actually change (e.g.
    # everything failed, or the queue was already empty).
    db_sync.push_changes(
        commit_message=f"Push {results['added']} card(s) to Anki, {results['remaining']} left pending"
    )


if __name__ == '__main__':
    main()
