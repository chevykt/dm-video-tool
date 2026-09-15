# tests/test_smoke.py
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydub.generators import Sine

from config import Config
from pipeline.render import render, render_silent
from pipeline.scenes import Scene

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="FFmpeg not installed")


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def _make_png(path: Path, width: int, height: int):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c=white:s={width}x{height}", "-frames:v", "1", str(path)],
        capture_output=True, check=True,
    )


def test_silent_render_end_to_end(tmp_path):
    cfg = Config()
    scenes = []
    # deliberately different heights, which is what the real generator produces
    for i, h in enumerate([340, 520, 410], start=1):
        img = tmp_path / f"conversation_{i}.png"
        _make_png(img, 1200, h)
        scenes.append(Scene(id=i, image_path=img, text="x", speaker="Mina",
                            duration=1.5))

    out = render_silent(scenes, cfg, tmp_path / "work", tmp_path / "silent.mp4")

    assert out.exists()
    assert abs(_probe_duration(out) - 4.5) < 0.1


def test_silent_render_survives_apostrophe_in_work_dir(tmp_path):
    cfg = Config()
    root = tmp_path / "O'Brien"
    root.mkdir()
    scenes = []
    for i, h in enumerate([340, 520, 410], start=1):
        img = root / f"conversation_{i}.png"
        _make_png(img, 1200, h)
        scenes.append(Scene(id=i, image_path=img, text="x", speaker="Mina",
                            duration=1.5))

    out = render_silent(scenes, cfg, root / "work", root / "silent.mp4")

    assert out.exists()
    assert abs(_probe_duration(out) - 4.5) < 0.1


def _probe_stream(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,pix_fmt",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)["streams"][0]


def _probe_packet_count(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def test_render_length_is_an_exact_whole_number_of_frames(tmp_path):
    cfg = Config()
    scenes = []
    # 1.51 and 3.34 are where the old `-t` rounding over-counts by a whole
    # frame on FFmpeg 9.0.1 (46 and 101 frames instead of round()'s 45/100),
    # so this set of durations is what actually discriminates old vs new.
    durations = [2.02, 1.51, 3.34]
    for i, (h, dur) in enumerate(zip([340, 520, 410], durations), start=1):
        img = tmp_path / f"conversation_{i}.png"
        _make_png(img, 1200, h)
        scenes.append(Scene(id=i, image_path=img, text="x", speaker="Mina",
                            duration=dur))

    out = render_silent(scenes, cfg, tmp_path / "work", tmp_path / "silent.mp4")

    expected_frames = 61 + 45 + 100
    assert _probe_packet_count(out) == expected_frames
    assert abs(_probe_duration(out) - expected_frames / 30) < 0.01

    stream = _probe_stream(out)
    assert stream["width"] == 1920
    assert stream["height"] == 1080
    assert stream["r_frame_rate"] == "30/1"
    assert stream["pix_fmt"] == "yuv420p"


def _probe_stream_codecs(path: Path) -> list[dict]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)["streams"]


def test_render_muxes_exactly_one_video_and_one_audio_stream(tmp_path):
    durations = [2.02, 1.51, 3.34]
    scenes = []
    for i, (h, dur) in enumerate(zip([340, 520, 410], durations), start=1):
        img = tmp_path / f"conversation_{i}.png"
        _make_png(img, 1200, h)
        scenes.append(Scene(id=i, image_path=img, text="x", speaker="Mina",
                            duration=dur))

    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    Sine(1000).to_audio_segment(duration=50).export(sfx_dir / "pop.wav", format="wav")

    # Shorter than the video, so build_track's loop-to-fill path runs.
    music_path = tmp_path / "music.wav"
    Sine(400).to_audio_segment(duration=2000).export(music_path, format="wav")

    cfg = Config(sfx_dir=sfx_dir, music_path=music_path)

    out = render(scenes, cfg, tmp_path / "work", tmp_path / "final.mp4")

    streams = _probe_stream_codecs(out)
    video_streams = [s for s in streams if s["codec_type"] == "video"]
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    assert len(video_streams) == 1
    assert video_streams[0]["codec_name"] == "h264"
    assert len(audio_streams) == 1
    assert audio_streams[0]["codec_name"] == "aac"

    expected_frames = 61 + 45 + 100
    assert _probe_packet_count(out) == expected_frames
    assert abs(_probe_duration(out) - expected_frames / 30) < 0.05
