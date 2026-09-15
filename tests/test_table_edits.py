# tests/test_table_edits.py
from pathlib import Path

from pipeline.scenes import Scene
from table_edits import apply_table_edits, scene_table


def _scenes():
    return [
        Scene(id=1, image_path=Path("conversation_1.png"), text="hello",
              speaker="Mina", duration=2.0),
        Scene(id=2, image_path=Path("conversation_2.png"), text="world",
              speaker="Deku", duration=3.0),
    ]


def test_scene_table_has_one_row_per_scene_with_a_word_count():
    scenes = _scenes()
    scenes[1].text = "three whole words"
    table = scene_table(scenes, {2: 3.0})

    assert list(table["id"]) == [1, 2]
    assert list(table["words"]) == [1, 3]
    assert list(table["seconds"]) == [2.0, 3.0]
    assert list(table["hand-set"]) == [False, True]
    assert set(table.columns) == {"id", "speaker", "message", "words", "seconds",
                                  "hand-set", "zoom", "shake", "sfx"}


def test_seconds_edit_becomes_an_override():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "seconds"] = 5.5

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert changes.durations is True
    assert changes.flags is False
    assert overrides == {1: 5.5}


def test_zoom_toggle_and_sfx_change_are_written_to_the_scene():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 2, "zoom"] = True
    edited.loc[edited["id"] == 2, "sfx"] = "whoosh"

    changes = apply_table_edits(scenes, overrides, before, edited)

    # A tick or a preset is not a duration change, so app.py keeps the same
    # editor (no remount, no jump back to the top-left of the table).
    assert changes.flags is True
    assert changes.durations is False
    assert scenes[1].zoom is True
    assert scenes[1].sfx == "whoosh"
    # untouched scene/fields stay as they were
    assert scenes[0].zoom is False
    assert scenes[1].shake is False


def test_shake_toggle_is_written_to_the_scene():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "shake"] = True

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert changes.flags is True
    assert changes.durations is False
    assert scenes[0].shake is True


def test_nan_seconds_is_ignored():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 1, "seconds"] = float("nan")

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert not changes
    assert overrides == {}


def test_cleared_zoom_shake_and_sfx_cells_are_ignored():
    # What st.data_editor hands back for a cell cleared with Delete: None,
    # which pandas stores as a missing value. It must never become a
    # scene's zoom/shake (bool) or the sfx preset "nan".
    scenes = _scenes()
    scenes[0].zoom = True
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.astype({"zoom": object, "shake": object, "sfx": object})
    edited.loc[edited["id"] == 1, "zoom"] = None
    edited.loc[edited["id"] == 1, "shake"] = None
    edited.loc[edited["id"] == 1, "sfx"] = None

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert not changes
    assert scenes[0].zoom is True
    assert scenes[0].shake is False
    assert scenes[0].sfx == "pop"


def test_rows_returned_in_a_different_order_are_still_matched_by_id():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()
    edited.loc[edited["id"] == 2, "seconds"] = 9.0
    edited.loc[edited["id"] == 2, "shake"] = True
    # Simulate the UI returning rows sorted differently than `before`.
    edited = edited.sort_values("id", ascending=False).reset_index(drop=True)

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert changes.durations is True
    assert overrides == {2: 9.0}
    assert scenes[1].shake is True
    assert scenes[0].shake is False


def test_no_change_returns_false_and_nothing_is_mutated():
    scenes = _scenes()
    overrides: dict[int, float] = {}
    before = scene_table(scenes, overrides)
    edited = before.copy()

    changes = apply_table_edits(scenes, overrides, before, edited)

    assert not changes
    assert changes.durations is False and changes.flags is False
    assert overrides == {}
    assert scenes[0].zoom is False
    assert scenes[0].shake is False
    assert scenes[0].sfx == "pop"
