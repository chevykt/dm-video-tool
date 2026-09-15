# tests/test_workdirs.py
import os
import tempfile
import time
from pathlib import Path

import pytest

import workdirs

DAY = 24 * 60 * 60


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_new_work_dir_is_a_prefixed_folder_in_the_temp_dir(temp_root):
    work = workdirs.new_work_dir()
    assert work.is_dir()
    assert work.parent == temp_root
    assert work.name.startswith("dmvideo_")


def test_sweep_removes_only_old_work_dirs(temp_root):
    old = temp_root / "dmvideo_old"
    (old / "images").mkdir(parents=True)
    (old / "images" / "conversation_1.png").write_bytes(b"png")
    _age(old / "images", 2 * DAY)
    _age(old, 2 * DAY)
    fresh = temp_root / "dmvideo_fresh"
    fresh.mkdir()
    other = temp_root / "someone_elses_dir"
    other.mkdir()
    _age(other, 2 * DAY)

    removed = workdirs.sweep_stale()

    assert removed == [old]
    assert not old.exists()
    assert fresh.exists()
    assert other.exists()


def test_sweep_never_touches_the_folder_it_is_told_to_keep(temp_root):
    mine = temp_root / "dmvideo_mine"
    mine.mkdir()
    _age(mine, 2 * DAY)

    workdirs.sweep_stale(keep=mine)

    assert mine.exists()


def test_a_recent_render_inside_an_old_folder_keeps_it(temp_root):
    # final.mp4 is rewritten in place by each render, which does not change
    # the folder's own timestamp.
    work = temp_root / "dmvideo_busy"
    work.mkdir()
    (work / "final.mp4").write_bytes(b"mp4")
    _age(work, 2 * DAY)

    workdirs.sweep_stale()

    assert work.exists()


def test_remove_ignores_missing_folders_and_none(tmp_path):
    workdirs.remove(None)
    workdirs.remove(tmp_path / "never_existed")
    target = tmp_path / "dmvideo_x"
    (target / "render").mkdir(parents=True)
    workdirs.remove(target)
    assert not target.exists()
