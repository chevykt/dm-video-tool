import csv
import pytest
from pathlib import Path
from config import Config
from pipeline.scenes import scene_id_from_filename, build_scenes

CFG = Config()


def _csv(tmp_path, rows):
    p = tmp_path / "sheet.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["conversation_id", "name", "message", "zoom", "shake"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return p


def test_parses_id_from_filename():
    assert scene_id_from_filename("conversation_7.png") == 7
    assert scene_id_from_filename("/tmp/x/conversation_200.png") == 200


def test_rejects_unexpected_filename():
    with pytest.raises(ValueError, match="Unexpected image filename"):
        scene_id_from_filename("screenshot.png")


def test_scenes_are_ordered_numerically_not_lexically(tmp_path):
    rows = [{"conversation_id": i, "name": "Mina", "message": f"line {i}", "zoom": "", "shake": ""}
            for i in (1, 2, 10)]
    images = [Path(f"conversation_{i}.png") for i in (10, 1, 2)]
    scenes = build_scenes(images, _csv(tmp_path, rows), CFG)
    assert [s.id for s in scenes] == [1, 2, 10]


def test_multiple_rows_sharing_an_id_become_one_scene(tmp_path):
    rows = [
        {"conversation_id": 1, "name": "Deku", "message": "hello", "zoom": "", "shake": ""},
        {"conversation_id": 1, "name": "Deku", "message": "again", "zoom": "", "shake": ""},
    ]
    scenes = build_scenes([Path("conversation_1.png")], _csv(tmp_path, rows), CFG)
    assert len(scenes) == 1
    assert scenes[0].text == "hello again"


def test_blank_rows_are_ignored(tmp_path):
    rows = [
        {"conversation_id": 1, "name": "Mina", "message": "real", "zoom": "", "shake": ""},
        {"conversation_id": "", "name": "", "message": "", "zoom": "", "shake": ""},
    ]
    scenes = build_scenes([Path("conversation_1.png")], _csv(tmp_path, rows), CFG)
    assert len(scenes) == 1


def test_mismatch_fails_loudly_naming_both_sides(tmp_path):
    rows = [{"conversation_id": 1, "name": "Mina", "message": "a", "zoom": "", "shake": ""}]
    images = [Path("conversation_1.png"), Path("conversation_2.png")]
    with pytest.raises(ValueError, match=r"Images with no row: \[2\]"):
        build_scenes(images, _csv(tmp_path, rows), CFG)


def test_flags_are_read_from_the_sheet(tmp_path):
    rows = [{"conversation_id": 1, "name": "Mina", "message": "a", "zoom": "TRUE", "shake": "no"}]
    scenes = build_scenes([Path("conversation_1.png")], _csv(tmp_path, rows), CFG)
    assert scenes[0].zoom is True
    assert scenes[0].shake is False
