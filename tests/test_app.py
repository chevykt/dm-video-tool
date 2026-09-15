# tests/test_app.py
"""End-to-end tests of app.py's Streamlit UI, driven with AppTest.

These do not touch inputs/: the zip and CSV are built fresh in tmp_path,
the same way test_smoke.py builds its PNGs (ffmpeg lavfi, since Pillow is
not installed).
"""
import csv
import re
import shutil
import zipfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from config import Config
from tests.test_smoke import _make_png

APP_PATH = "../app.py"
TIMEOUT = 60


def _build_upload(tmp_path):
    """A zip of 3 conversation PNGs (1200px wide, different heights) plus a
    matching CSV, the same shape as what the client uploads."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    heights = [340, 520, 410]
    for i, h in enumerate(heights, start=1):
        _make_png(images_dir / f"conversation_{i}.png", 1200, h)

    zip_path = tmp_path / "batch.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for i in (1, 2, 3):
            z.write(images_dir / f"conversation_{i}.png", f"conversation_{i}.png")

    csv_path = tmp_path / "sheet.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["conversation_id", "name", "message"])
        w.writeheader()
        for i in (1, 2, 3):
            w.writerow({
                "conversation_id": i,
                "name": "Mina",
                "message": f"Hey there, this is a reasonably long test message number {i}",
            })

    return zip_path, csv_path


def _runtime_seconds(caption_text: str) -> int:
    m = re.search(r"(\d+)m (\d+)s", caption_text)
    assert m, f"caption did not contain a runtime: {caption_text!r}"
    return int(m.group(1)) * 60 + int(m.group(2))


def _load_scenes(at, zip_path, csv_path):
    """Upload the zip + CSV and click Load scenes, returning the app after
    the load has been processed (the run whose tree has the scene table)."""
    at.run()  # initial run: uploaders exist, "Load scenes" not registered yet

    at.file_uploader[0].set_value([(zip_path.name, zip_path.read_bytes(), "application/zip")])
    at.file_uploader[1].set_value((csv_path.name, csv_path.read_bytes(), "text/csv"))
    at.run()  # zips/csv now truthy: "Load scenes" button is registered

    at.button[0].click()
    at.run()  # button fires: scenes are built and the scene table appears
    return at


def test_loading_a_conversation_shows_the_scene_table(tmp_path):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)

    assert not at.exception
    assert not at.error

    assert len(at.caption) == 1
    assert "3 scenes" in at.caption[0].value


def test_overall_speed_slider_shortens_the_runtime(tmp_path):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    baseline = _runtime_seconds(at.caption[0].value)

    speed_slider = next(s for s in at.sidebar.slider if s.label == "Overall speed")
    assert speed_slider.value == pytest.approx(Config().speed)
    speed_slider.set_value(1.5)
    at.run()

    assert not at.exception and not at.error
    faster = _runtime_seconds(at.caption[0].value)
    assert faster < baseline


def test_volume_sliders_exist_and_start_at_the_config_defaults(tmp_path):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    defaults = Config()
    sfx_slider = next(s for s in at.sidebar.slider if s.label == "Sound effect volume (dB)")
    music_slider = next(s for s in at.sidebar.slider if s.label == "Music volume (dB)")
    assert sfx_slider.value == pytest.approx(defaults.sfx_gain_db)
    assert music_slider.value == pytest.approx(defaults.music_gain_db)


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not Config().music_path or not Path(Config().music_path).exists(),
    reason="FFmpeg and/or the background music file are not available",
)
def test_render_video_produces_no_error_and_a_video_player(tmp_path):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    render_button = next(b for b in at.button if b.label == "Render video")
    render_button.click()
    at.run()

    assert not at.exception
    assert not at.error
    assert len(at.success) >= 1
    assert len(at.get("video")) >= 1

    rendered_path = Path(at.session_state["rendered"])
    assert rendered_path.exists()
    mtime_after_render = rendered_path.stat().st_mtime

    # A rerun that is NOT a fresh click of Render video -- this is what
    # st.download_button's own click does, and what moving a slider or
    # editing the table does too. The result must stay on screen, and
    # FFmpeg must not have run again.
    at.run()

    assert not at.exception
    assert not at.error
    assert len(at.success) >= 1
    assert len(at.get("video")) >= 1
    assert rendered_path.stat().st_mtime == mtime_after_render


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or not Config().music_path or not Path(Config().music_path).exists(),
    reason="FFmpeg and/or the background music file are not available",
)
def test_loading_scenes_again_clears_the_previous_render(tmp_path):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    render_button = next(b for b in at.button if b.label == "Render video")
    render_button.click()
    at.run()
    assert at.session_state["rendered"]
    assert len(at.get("video")) >= 1

    # Load the same conversation again -- the previous render must not
    # linger and be mistaken for a render of the settings now in effect.
    load_button = next(b for b in at.button if b.label == "Load scenes")
    load_button.click()
    at.run()

    assert not at.exception and not at.error
    assert at.session_state["rendered"] is None
    assert len(at.get("video")) == 0
    assert len(at.success) == 0
