# workdirs.py
"""The per-conversation work folders app.py keeps in the system temp dir.

A 200-message load plus render holds about 140 MB, so folders are deleted
when they are replaced, and ones left behind (a closed tab, a crash) are
swept a day later. No streamlit import here: app.py is the only module that
imports streamlit, so this can be unit tested on its own.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path

PREFIX = "dmvideo_"
STALE_AFTER_S = 24 * 60 * 60


def new_work_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix=PREFIX))


def remove(path) -> None:
    """Delete a folder and everything in it. Never raises: a file can be
    locked on Windows, and a folder left behind is swept later."""
    if path:
        shutil.rmtree(path, ignore_errors=True)


def touch(path) -> None:
    """Mark a work folder as used just now, so a tab left open only for
    editing (no load, preview or render touches its files) is not mistaken
    by sweep_stale for one left behind by a session that ended. Never
    raises: the folder may no longer exist."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _last_used(folder: Path) -> float:
    """Newest timestamp of the folder and what is directly inside it.
    final.mp4 and preview.wav are rewritten in place, which does not change
    the folder's own timestamp."""
    newest = folder.stat().st_mtime
    for child in folder.iterdir():
        newest = max(newest, child.stat().st_mtime)
    return newest


def sweep_stale(keep=None, max_age_s: float = STALE_AFTER_S) -> list[Path]:
    """Delete work folders in the temp dir unused for `max_age_s` seconds,
    except `keep`. Returns the folders removed. Never raises."""
    keep_path = Path(keep).resolve() if keep else None
    cutoff = time.time() - max_age_s
    removed = []
    for folder in sorted(Path(tempfile.gettempdir()).glob(PREFIX + "*")):
        try:
            if not folder.is_dir() or folder.resolve() == keep_path:
                continue
            if _last_used(folder) > cutoff:
                continue
        except OSError:
            continue
        remove(folder)
        removed.append(folder)
    return removed
