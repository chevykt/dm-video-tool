# tests/test_table_edits.py
from pathlib import Path

import pandas as pd
import pytest

from pipeline.scenes import Scene
from table_edits import apply_table_edits


def _scenes():
    return [
        Scene(id=1, image_path=Path("conversation_1.png"), text="hello",
              speaker="Mina", duration=2.0),
        Scene(id=2, image_path=Path("conversation_2.png"), text="world",
              speaker="Deku", duration=3.0),
    ]


def _table(scenes, overrides):
    return pd.DataFrame([
        {"id": s.id, "speaker": s.speaker, "message": s.text[:60],
         "seconds": round(s.duration, 2), "hand-set": s.id in overrides,
         "zoom": s.zoom, "shake": s.shake, "sfx": s.sfx}
        for s in scenes
    ])


def test_seconds_edit_becomes_an_override():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "seconds"] = 5.5

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is True
    assert overrides == {1: 5.5}


def test_zoom_toggle_and_sfx_change_are_written_to_the_scene():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 2, "zoom"] = True
    edited.loc[edited["id"] == 2, "sfx"] = "whoosh"

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is True
    assert scenes[1].zoom is True
    assert scenes[1].sfx == "whoosh"
    # untouched scene/fields stay as they were
    assert scenes[0].zoom is False
    assert scenes[1].shake is False


def test_shake_toggle_is_written_to_the_scene():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "shake"] = True

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is True
    assert scenes[0].shake is True


def test_nan_seconds_is_ignored():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "seconds"] = float("nan")

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is False
    assert overrides == {}


def test_rows_returned_in_a_different_order_are_still_matched_by_id():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 2, "seconds"] = 9.0
    # Simulate the UI returning rows sorted differently than `before`.
    edited = edited.sort_values("id", ascending=False).reset_index(drop=True)

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is True
    assert overrides == {2: 9.0}


def test_no_change_returns_false_and_nothing_is_mutated():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = _table(scenes, overrides)
    edited = before.copy()

    changed = apply_table_edits(scenes, overrides, before, edited)

    assert changed is False
    assert overrides == {}
    assert scenes[0].zoom is False
    assert scenes[0].shake is False
    assert scenes[0].sfx == "pop"
