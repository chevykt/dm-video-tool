# tests/test_smoke.py
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from config import Config
from pipeline.render import render_silent
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
