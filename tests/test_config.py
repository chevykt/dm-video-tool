# tests/test_config.py
from pathlib import Path

from config import Config


def test_sfx_path_finds_mp3_when_only_mp3_present(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    (sfx_dir / "x.mp3").write_bytes(b"")
    cfg = Config(sfx_dir=sfx_dir)
    assert cfg.sfx_path("x") == sfx_dir / "x.mp3"


def test_sfx_path_prefers_wav_when_both_present(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    (sfx_dir / "x.wav").write_bytes(b"")
    (sfx_dir / "x.mp3").write_bytes(b"")
    cfg = Config(sfx_dir=sfx_dir)
    assert cfg.sfx_path("x") == sfx_dir / "x.wav"


def test_sfx_path_falls_back_to_wav_path_when_neither_present(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    cfg = Config(sfx_dir=sfx_dir)
    assert cfg.sfx_path("missing") == sfx_dir / "missing.wav"


def test_sfx_choices_lists_wav_and_mp3_stems_once_each_sorted(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    (sfx_dir / "pop.wav").write_bytes(b"")
    (sfx_dir / "whoosh.mp3").write_bytes(b"")
    (sfx_dir / "ding.WAV").write_bytes(b"")
    (sfx_dir / "notes.txt").write_bytes(b"")
    cfg = Config(sfx_dir=sfx_dir)
    assert cfg.sfx_choices() == ["ding", "pop", "whoosh"]


def test_sfx_choices_falls_back_to_default_for_empty_dir(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    cfg = Config(sfx_dir=sfx_dir)
    assert cfg.sfx_choices() == [cfg.default_sfx]
