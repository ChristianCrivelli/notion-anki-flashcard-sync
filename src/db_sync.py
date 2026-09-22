"""
Sync the persistent word database with GitHub, so local_database.csv,
needs_notion_cleanup.csv, and pending_cards.csv act as a lightweight
"hosted database" that stays consistent across machines: pull the latest
before a run starts, push whatever changed after it finishes.

This is deliberately the simple version — the data files are just committed
straight into the same git repo as the code, no separate hosting/infra. It
relies on git already being configured with push access on this machine
(the same setup you use to commit from VSCode, or the GitHub Actions
runner's own token for the scheduled gather.py run — see issue #8).

Everything here is best-effort: a sync failure (offline, merge conflict, no
push access) prints a warning and lets the run continue rather than
crashing it. Your words are always safe on local disk regardless of whether
the sync step succeeds.
"""
import os
import subprocess

# This file lives in src/, but the git repo root -- and the data files in
# SYNCED_FILES -- are one level up. See issue #12.
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNCED_FILES = ["local_database.csv", "needs_notion_cleanup.csv", "pending_cards.csv"]


def _run_git(*args):
    return subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )


def _is_git_repo() -> bool:
    return os.path.isdir(os.path.join(REPO_DIR, ".git"))


def _working_tree_is_clean() -> bool:
    result = _run_git("status", "--porcelain")
    return result.returncode == 0 and not result.stdout.strip()


def _has_unfinished_operation() -> bool:
    """
    True if the repo is already mid-rebase/merge/cherry-pick from some
    earlier interrupted operation. We must never pull, commit, or push on
    top of that — it's how you end up with literal `<<<<<<< HEAD` conflict
    markers silently committed into local_database.csv and parsed as
    "words" the next time it's read.
    """
    git_dir = os.path.join(REPO_DIR, ".git")
    return any(
        os.path.exists(os.path.join(git_dir, marker))
        for marker in ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD")
    )


def pull_latest():
    """
    Pull the latest database files from GitHub before this run starts, so
    two machines don't independently decide the same word is "new".

    Skips (with a warning) rather than forcing a sync if: this isn't a git
    repo, the repo is already mid-rebase/merge from something else, or the
    working tree has uncommitted changes — running `git pull` on a dirty
    tree could tangle up unrelated in-progress code edits, which isn't this
    script's business to touch.

    If two machines appended different words without syncing in between,
    the rebase itself can conflict (git can't always tell whose append goes
    first). Rather than leave that conflict sitting in the file as literal
    `<<<<<<<`/`=======`/`>>>>>>>` markers — which load_known_words() would
    then happily parse as garbage "words" — this aborts the rebase and
    reverts to the pre-pull state. Worst case you reprocess a couple of
    words this run; that's a far cheaper mistake than corrupting the file.
    """
    if not _is_git_repo():
        return False

    if _has_unfinished_operation():
        print("Note: skipping database sync — this repo has an unfinished "
              "git rebase/merge sitting from something else. Resolve that "
              "manually (or `git rebase --abort`) before running again.")
        return False

    if not _working_tree_is_clean():
        print("Note: skipping database sync — you have uncommitted changes "
              "in this repo, so I won't risk touching your working tree. "
              "Pull/push manually when convenient.")
        return False

    result = _run_git("pull", "--rebase")
    if result.returncode != 0:
        if _has_unfinished_operation():
            abort = _run_git("rebase", "--abort")
            if abort.returncode != 0:
                print("Warning: git pull failed AND could not automatically "
                      "clean up afterwards. Please check this repo's git "
                      f"state manually before running again: {abort.stderr.strip()}")
                return False
        last_line = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ""
        print(f"Warning: could not pull the latest known-words database from "
              f"GitHub (likely two machines edited it at once): {last_line}")
        print("Reverted to the local copy so nothing gets corrupted — you may "
              "reprocess a few words this run. Run `git pull` by hand later to "
              "merge both machines' words together.")
        return False

    return True


def push_changes(commit_message: str = "Update known-words database"):
    """
    Commit and push any changes to the tracked database files (only those
    files — this never touches code you may be mid-editing).

    No-ops quietly if nothing changed. A push failure is a warning, not a
    crash: the commit still exists locally either way, so nothing is lost —
    it just goes up next time this succeeds, or whenever you push manually.
    """
    if not _is_git_repo():
        return

    if _has_unfinished_operation():
        print("Note: skipping database push — this repo has an unfinished "
              "git rebase/merge sitting from something else. Resolve that "
              "manually before this can commit/push safely.")
        return

    existing = [f for f in SYNCED_FILES if os.path.exists(os.path.join(REPO_DIR, f))]
    if not existing:
        return

    status = _run_git("status", "--porcelain", "--", *existing)
    if status.returncode != 0 or not status.stdout.strip():
        return  # nothing changed in the tracked database files

    add = _run_git("add", "--", *existing)
    if add.returncode != 0:
        print(f"Warning: could not stage database changes: {add.stderr.strip()}")
        return

    commit = _run_git("commit", "-m", commit_message)
    if commit.returncode != 0:
        print(f"Warning: could not commit database changes: {commit.stderr.strip()}")
        return

    push = _run_git("push")
    if push.returncode != 0:
        print(f"Warning: could not push database changes to GitHub: {push.stderr.strip()}")
        print("Your words are saved and committed locally — push manually "
              "when you get a chance, or it'll go up next successful run.")
