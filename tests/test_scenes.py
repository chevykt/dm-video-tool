import csv
import pytest
import zipfile
from pathlib import Path
from config import Config
from pipeline.scenes import scene_id_from_filename, build_scenes, extract_zips, Scene, retime

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


def test_extract_zips_flattens_pngs_from_every_zip(tmp_path):
    # Create two zips: one with nested member, one non-PNG member
    zip1_path = tmp_path / "batch1.zip"
    with zipfile.ZipFile(zip1_path, "w") as z:
        z.writestr("conversation_1.png", b"png")
        z.writestr("batch/conversation_2.png", b"png")  # nested

    zip2_path = tmp_path / "batch2.zip"
    with zipfile.ZipFile(zip2_path, "w") as z:
        z.writestr("conversation_3.png", b"png")
        z.writestr("notes.txt", b"not a png")  # non-PNG, should be skipped

    dest = tmp_path / "extracted"
    paths = extract_zips([zip1_path, zip2_path], dest)

    # Check returned paths
    path_names = sorted([p.name for p in paths])
    assert path_names == ["conversation_1.png", "conversation_2.png", "conversation_3.png"]

    # Check all returned paths exist directly under dest (flattened)
    for p in paths:
        assert p.parent == dest
        assert p.exists()

    # Check .txt was not extracted
    assert not (dest / "notes.txt").exists()


def test_duplicate_image_across_zips_fails_loudly(tmp_path):
    # Create two zips that both contain conversation_1.png
    zip1_path = tmp_path / "batch1.zip"
    with zipfile.ZipFile(zip1_path, "w") as z:
        z.writestr("conversation_1.png", b"png")

    zip2_path = tmp_path / "batch2.zip"
    with zipfile.ZipFile(zip2_path, "w") as z:
        z.writestr("conversation_1.png", b"png")

    dest = tmp_path / "extracted"
    extracted = extract_zips([zip1_path, zip2_path], dest)

    # Create CSV with row for id 1
    rows = [{"conversation_id": 1, "name": "Mina", "message": "a", "zoom": "", "shake": ""}]

    # build_scenes should fail loudly on duplicate ids
    with pytest.raises(ValueError, match=r"Duplicate images for ids: \[1\]"):
        build_scenes(extracted, _csv(tmp_path, rows), CFG)


def _raw_csv(tmp_path, header, rows):
    """Write a CSV with an arbitrary header row (bypassing the fixed-column _csv helper)."""
    p = tmp_path / "sheet.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    return p


def test_wrong_tab_csv_names_missing_columns(tmp_path):
    # A CSV exported from the wrong Google Sheet tab: no conversation_id/message at all.
    csv_path = _raw_csv(tmp_path, ["key", "value"], [["a", "b"]])
    with pytest.raises(ValueError, match=r"Sheet CSV is missing required column\(s\):"):
        build_scenes([Path("conversation_1.png")], csv_path, CFG)


def test_empty_csv_reports_missing_columns(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Sheet CSV is missing required column\(s\):"):
        build_scenes([Path("conversation_1.png")], csv_path, CFG)


def test_header_case_and_whitespace_are_tolerated(tmp_path):
    csv_path = _raw_csv(
        tmp_path,
        [" Conversation_ID ", "Name", "Message", "Zoom", "Shake"],
        [[1, "Mina", "hi", "", ""]],
    )
    scenes = build_scenes([Path("conversation_1.png")], csv_path, CFG)
    assert len(scenes) == 1
    assert scenes[0].speaker == "Mina"
    assert scenes[0].text == "hi"


def test_non_numeric_conversation_id_names_value_and_line(tmp_path):
    csv_path = _raw_csv(
        tmp_path,
        ["conversation_id", "name", "message", "zoom", "shake"],
        [["abc", "Mina", "hi", "", ""]],
    )
    with pytest.raises(ValueError, match=r"abc") as exc_info:
        build_scenes([Path("conversation_1.png")], csv_path, CFG)
    assert "line 2" in str(exc_info.value)


def test_macos_resource_fork_entries_are_skipped(tmp_path):
    zip_path = tmp_path / "batch.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("conversation_1.png", b"png")
        z.writestr("__MACOSX/._conversation_1.png", b"resource fork junk")

    dest = tmp_path / "extracted"
    paths = extract_zips([zip_path], dest)

    names = sorted(p.name for p in paths)
    assert names == ["conversation_1.png"]


def test_retime_recomputes_from_the_rule_but_keeps_hand_set_durations():
    scenes = [
        Scene(id=1, image_path=Path("conversation_1.png"), text="coin says no",
              speaker="Mina", duration=9.0),
        Scene(id=2, image_path=Path("conversation_2.png"), text="coin says no",
              speaker="Mina", duration=9.0),
    ]
    retime(scenes, Config(speed=2.0), overrides={2: 4.5})
    assert scenes[0].duration == pytest.approx(1.01)
    assert scenes[1].duration == 4.5
