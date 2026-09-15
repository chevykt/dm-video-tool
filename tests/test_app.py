# tests/test_app.py
"""End-to-end tests of app.py's Streamlit UI, driven with AppTest.

These do not touch inputs/: the zip and CSV are built fresh in tmp_path,
the same way test_smoke.py builds its PNGs (ffmpeg lavfi, since Pillow is
not installed).
"""
import csv
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest
import streamlit
from streamlit.testing.v1 import AppTest

from config import Config
from pipeline.runner import FFmpegFailed
from tests.test_smoke import _make_png

APP_PATH = "../app.py"
TIMEOUT = 60


@pytest.fixture(autouse=True)
def temp_root(tmp_path, monkeypatch):
    """app.py makes its work dirs with tempfile. AppTest runs the script in
    this process, so pointing tempfile at tmp_path keeps every dmvideo_* dir
    a test creates out of the real temp folder."""
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    return root


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


def _editor_proto(at):
    """The scene table's element proto (AppTest cannot drive st.data_editor,
    but it can read what app.py asked the browser to show)."""
    frames = at.get("dataframe")
    assert len(frames) == 1
    return frames[0].proto


def test_zoom_shake_and_sfx_cells_cannot_be_cleared(tmp_path):
    # Pressing Delete on a cell sets it to None. For zoom/shake that crashed
    # st.data_editor for the rest of the session; for sfx it became the
    # preset "nan". A required column makes the grid ignore Delete.
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    columns = json.loads(_editor_proto(at).columns)
    for name in ("zoom", "shake"):
        assert columns[name]["type_config"]["type"] == "checkbox"
        assert columns[name]["required"] is True
    assert columns["sfx"]["type_config"]["type"] == "selectbox"
    assert columns["sfx"]["required"] is True


def test_the_choices_come_before_the_message_in_the_table(tmp_path):
    # zoom/shake/sfx used to be the right-most columns, off-screen on a
    # laptop. The word count is shown but cannot be edited.
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    proto = _editor_proto(at)
    order = list(proto.column_order)
    assert order[:5] == ["id", "zoom", "shake", "sfx", "seconds"]
    assert order.index("message") > order.index("seconds")
    assert "words" in order
    assert json.loads(proto.columns)["words"]["disabled"] is True


def test_a_broken_table_state_resets_the_table_instead_of_crashing(tmp_path, monkeypatch):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error
    version = at.session_state["editor_version"]

    # What a bad edit persisted in the editor's widget state does: the
    # editor itself raises on every rerun until that state is dropped.
    real_editor = streamlit.data_editor
    calls = []

    def editor_with_bad_state(*args, **kwargs):
        calls.append(kwargs.get("key"))
        if len(calls) == 1:
            raise TypeError("Invalid value 'nan' for dtype 'bool'")
        return real_editor(*args, **kwargs)

    monkeypatch.setattr(streamlit, "data_editor", editor_with_bad_state)
    at.run()

    assert not at.exception and not at.error
    assert at.session_state["editor_version"] == version + 1
    assert calls[1] != calls[0]  # the retry used a fresh editor key
    assert len(at.get("dataframe")) == 1
    assert any(b.label == "Render video" for b in at.button)


def test_a_table_that_keeps_failing_shows_a_message_instead_of_looping(tmp_path, monkeypatch):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    def broken_editor(*args, **kwargs):
        raise TypeError("still broken")

    monkeypatch.setattr(streamlit, "data_editor", broken_editor)
    at.run()

    assert len(at.error) == 1
    assert "send Keon a screenshot" in at.error[0].value


def _click_render(at):
    next(b for b in at.button if b.label == "Render video").click()
    at.run()


def _fake_render(action):
    """Stand-in for pipeline.render.render. app.py imports it by name at the
    top of every run, so patching the module attribute reaches the app."""
    def fake(scenes, cfg, workdir, out_path, progress=None):
        return action(Path(out_path), progress)
    return fake


def test_every_control_is_disabled_while_a_render_runs(tmp_path, monkeypatch):
    # Streamlit stops a running script at its next call when any control is
    # touched (runner.fastReruns), which silently cancelled renders. The
    # render now runs in a pass where nothing can be touched.
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    def freeze_mid_render(out_path, progress):
        progress(1, 3)
        streamlit.stop()  # end the run here, so the tree shows the render in progress

    monkeypatch.setattr("pipeline.render.render", _fake_render(freeze_mid_render))
    _click_render(at)

    assert any("Rendering" in w.value and "please wait" in w.value for w in at.warning)
    assert at.slider and all(s.disabled for s in at.sidebar.slider)
    assert all(b.disabled for b in at.button)
    assert all(u.proto.disabled for u in at.get("file_uploader"))
    assert _editor_proto(at).disabled is True
    # The flag is cleared even though the run ended mid-render.
    assert at.session_state["rendering"] is False


def test_a_finished_render_gives_the_controls_back_and_a_named_download(tmp_path, monkeypatch):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)
    assert not at.exception and not at.error

    def write_video(out_path, progress):
        progress(3, 3)
        out_path.write_bytes(b"not really an mp4")
        return out_path

    monkeypatch.setattr("pipeline.render.render", _fake_render(write_video))
    real_download_button = streamlit.download_button
    download_kwargs = {}

    def recording_download_button(*args, **kwargs):
        download_kwargs.update(kwargs)
        return real_download_button(*args, **kwargs)

    monkeypatch.setattr(streamlit, "download_button", recording_download_button)
    _click_render(at)

    assert not at.exception and not at.error
    assert at.session_state["rendering"] is False
    assert not at.warning
    assert not any(s.disabled for s in at.sidebar.slider)
    assert not any(b.disabled for b in at.button)
    assert _editor_proto(at).disabled is False
    assert len(at.get("video")) == 1

    download = at.get("download_button")[0].proto
    # Downloading must not rerun the script (on_click="ignore").
    assert download.ignore_rerun is True
    # Named after the uploaded sheet, not a generic conversation.mp4.
    assert download_kwargs["file_name"] == "sheet.mp4"


def test_a_failed_render_keeps_its_message_after_the_controls_come_back(tmp_path, monkeypatch):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)

    def fail(out_path, progress):
        raise FFmpegFailed("FFmpeg exited 1:\nboom went the render")

    monkeypatch.setattr("pipeline.render.render", _fake_render(fail))
    _click_render(at)

    assert not at.exception
    assert len(at.error) == 1
    assert "boom went the render" in at.error[0].value
    assert at.session_state["rendering"] is False
    assert at.session_state["rendered"] is None
    assert not any(s.disabled for s in at.sidebar.slider)
    assert len(at.get("video")) == 0


def test_an_unexpected_render_error_shows_a_plain_message_with_details(tmp_path, monkeypatch):
    zip_path, csv_path = _build_upload(tmp_path)
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    _load_scenes(at, zip_path, csv_path)

    def crash(out_path, progress):
        raise RuntimeError("an error nobody planned for")

    monkeypatch.setattr("pipeline.render.render", _fake_render(crash))
    _click_render(at)

    assert len(at.error) == 1
    assert "send Keon a screenshot" in at.error[0].value
    details = next(e for e in at.expander if e.label == "Details")
    assert "an error nobody planned for" in details.exception[0].message
    assert at.session_state["rendering"] is False


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
    assert at.session_state["rendering"] is False
    assert not any(s.disabled for s in at.sidebar.slider)

    rendered_path = Path(at.session_state["rendered"])
    assert rendered_path.exists()
    mtime_after_render = rendered_path.stat().st_mtime

    # A rerun that is NOT a fresh click of Render video -- what moving a
    # slider or editing the table does. The result must stay on screen,
    # and FFmpeg must not have run again.
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
