# DM Conversation Video Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a batch of pre-generated chat-bubble PNGs plus a sheet CSV into one finished 16:9 mp4 with word-count timing, transition SFX, background music, and per-scene zoom or shake, driven from a minimal local web interface.

**Architecture:** Pure-logic core, thin execution layer, swappable interface. Every FFmpeg command is produced by a pure function returning an argv list, so filter strings are unit-testable without FFmpeg. Each scene renders to its own short mp4 with identical encoder settings; clips concat with `-c copy`; one prepared audio track is muxed at the end.

**Tech Stack:** Python 3.11+, FFmpeg (system binary), pydub, Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-dm-video-renderer-design.md`

## Global Constraints

- Output canvas is **1920x1080 at 30fps**. Source strips are 1200px wide with variable height.
- Every clip, animated or not, must end with identical codec, fps, dimensions and pixel format, or `concat -c copy` fails.
- `render.py` must never import streamlit. `app.py` must never build an FFmpeg argument. This separation was promised to the client in writing.
- Audio offsets accumulate in **integer milliseconds**, never floats.
- Images join to CSV rows by the id parsed from `conversation_<id>.png`, never by sort order.
- Timing defaults: `base=1.0`, `per_word=0.34`, `chars_per_sec=17`, `min=1.2`, `max=7.0`.
- `.env` and `outputs/` are gitignored from the first commit. No API key ever reaches the repo.
- Commit after every task.

---

### Task 1: Project scaffold and config

**Files:**
- Create: `config.py`, `pipeline/__init__.py`, `requirements.txt`, `.gitignore`, `tests/__init__.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Config` dataclass with every tunable used by all later tasks

- [ ] **Step 1: Initialise the repo**

```bash
mkdir -p dm-video-tool/pipeline dm-video-tool/tests dm-video-tool/assets/sfx dm-video-tool/assets/music
cd dm-video-tool && git init
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
outputs/
work/
assets/music/*
!assets/music/.gitkeep
```

- [ ] **Step 3: Write `requirements.txt`**

```
streamlit>=1.36
pydub>=0.25.1
pytest>=8.0
```

- [ ] **Step 4: Write `config.py`**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    # canvas
    width: int = 1920
    height: int = 1080
    fps: int = 30
    crf: int = 20
    preset: str = "veryfast"

    # timing
    base: float = 1.0
    per_word: float = 0.34
    chars_per_sec: float = 17.0
    min_duration: float = 1.2
    max_duration: float = 7.0

    # zoom
    zoom_mode: str = "animated"      # "animated" or "punch"
    zoom_end: float = 1.25
    zoom_speed: float = 0.0015
    punch_crop: float = 0.85
    punch_split: float = 0.4

    # shake
    shake_amplitude: int = 12
    shake_frequency: int = 8

    # audio
    sfx_dir: Path = Path("assets/sfx")
    default_sfx: str = "pop"
    sfx_gain_db: float = -3.0
    music_path: Path | None = None
    music_gain_db: float = -18.0

    def sfx_path(self, name: str) -> Path:
        return self.sfx_dir / f"{name}.wav"
```

- [ ] **Step 5: Create empty package files and commit**

```bash
touch pipeline/__init__.py tests/__init__.py assets/music/.gitkeep
git add -A && git commit -m "chore: scaffold project, config and gitignore"
```

---

### Task 2: Timing rule

**Files:**
- Create: `pipeline/timing.py`
- Test: `tests/test_timing.py`

**Interfaces:**
- Consumes: `Config` from Task 1
- Produces: `duration_for(text: str, cfg: Config) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_timing.py
import pytest
from config import Config
from pipeline.timing import duration_for

CFG = Config()


def test_short_message_uses_word_rule():
    # "coin says no" = 3 words, 12 chars
    # by_word = 1.0 + 0.34*3 = 2.02 ; by_char = 1.0 + 12/17 = 1.706
    assert round(duration_for("coin says no", CFG), 2) == 2.02


def test_long_word_is_rescued_by_char_rule():
    # "obviously" = 1 word, 9 chars
    # by_word = 1.34 ; by_char = 1.0 + 9/17 = 1.529 -> char rule wins
    assert round(duration_for("obviously", CFG), 2) == 1.53


def test_very_long_message_hits_the_ceiling():
    text = ("like this video, subscribe for more mha text stories, and comment "
            "if you think deku and uraraka make a good couple")
    assert duration_for(text, CFG) == CFG.max_duration


def test_floor_applies_when_config_is_tuned_down():
    cfg = Config(base=0.2, per_word=0.1)
    assert duration_for("hi", cfg) == cfg.min_duration
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_timing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.timing'`

- [ ] **Step 3: Write the implementation**

```python
# pipeline/timing.py
from config import Config


def duration_for(text: str, cfg: Config) -> float:
    """Seconds this message should stay on screen.

    Takes the larger of a word-based and a character-based estimate so that
    a short line of long words is not under-timed, then clamps.
    """
    words = len(text.split())
    chars = len(text)
    by_word = cfg.base + cfg.per_word * words
    by_char = cfg.base + chars / cfg.chars_per_sec
    return min(max(by_word, by_char, cfg.min_duration), cfg.max_duration)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/test_timing.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/timing.py tests/test_timing.py
git commit -m "feat: word and character based scene duration rule"
```

---

### Task 3: Scene assembly

**Files:**
- Create: `pipeline/scenes.py`
- Test: `tests/test_scenes.py`

**Interfaces:**
- Consumes: `duration_for` (Task 2), `Config` (Task 1)
- Produces:
  - `Scene` dataclass with fields `id, image_path, text, speaker, duration, zoom, shake, sfx`
  - `scene_id_from_filename(name: str) -> int`
  - `extract_zips(zip_paths: list[Path], dest: Path) -> list[Path]`
  - `build_scenes(image_paths: list[Path], csv_path: Path, cfg: Config) -> list[Scene]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scenes.py
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_scenes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.scenes'`

- [ ] **Step 3: Write the implementation**

```python
# pipeline/scenes.py
import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from config import Config
from pipeline.timing import duration_for

SCENE_FILENAME = re.compile(r"^conversation_(\d+)\.png$", re.IGNORECASE)
TRUTHY = {"true", "yes", "1", "x", "y"}


@dataclass
class Scene:
    id: int
    image_path: Path
    text: str
    speaker: str
    duration: float
    zoom: bool = False
    shake: bool = False
    sfx: str = "pop"


def scene_id_from_filename(name: str) -> int:
    m = SCENE_FILENAME.match(Path(name).name)
    if not m:
        raise ValueError(
            f"Unexpected image filename: {Path(name).name!r}. "
            "Expected conversation_<id>.png as produced by the sheet."
        )
    return int(m.group(1))


def extract_zips(zip_paths, dest: Path) -> list[Path]:
    """Flatten every PNG from every zip into dest. Returns the extracted paths."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for zp in zip_paths:
        with zipfile.ZipFile(zp) as z:
            for member in z.namelist():
                if not member.lower().endswith(".png"):
                    continue
                target = dest / Path(member).name
                with z.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                out.append(target)
    return out


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def _rows_by_id(csv_path: Path) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_id = (row.get("conversation_id") or "").strip()
            message = (row.get("message") or "").strip()
            if not raw_id or not message:
                continue
            groups.setdefault(int(raw_id), []).append(row)
    return groups


def build_scenes(image_paths, csv_path: Path, cfg: Config) -> list[Scene]:
    groups = _rows_by_id(csv_path)
    images = {scene_id_from_filename(p.name): Path(p) for p in image_paths}

    orphan_images = sorted(set(images) - set(groups))
    orphan_rows = sorted(set(groups) - set(images))
    if orphan_images or orphan_rows:
        raise ValueError(
            f"Image and sheet do not line up. "
            f"Images with no row: {orphan_images}. Rows with no image: {orphan_rows}."
        )

    scenes = []
    for sid in sorted(images):
        rows = groups[sid]
        text = " ".join((r.get("message") or "").strip() for r in rows)
        scenes.append(
            Scene(
                id=sid,
                image_path=images[sid],
                text=text,
                speaker=(rows[0].get("name") or "").strip(),
                duration=duration_for(text, cfg),
                zoom=_truthy(rows[0].get("zoom")),
                shake=_truthy(rows[0].get("shake")),
                sfx=cfg.default_sfx,
            )
        )
    return scenes
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/ -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/scenes.py tests/test_scenes.py
git commit -m "feat: build scenes from zipped images and sheet CSV, joined by id"
```

---

### Task 4: FFmpeg command builders

**Files:**
- Create: `pipeline/ffmpeg_cmd.py`
- Test: `tests/test_ffmpeg_cmd.py`

**Interfaces:**
- Consumes: `Scene` (Task 3), `Config` (Task 1)
- Produces:
  - `composite_filter(cfg) -> str`
  - `scene_filter(scene, cfg) -> str`
  - `build_scene_clip_cmd(scene, cfg, out_path, filter_override=None) -> list[str]`
  - `build_clips_for_scene(scene, cfg, clips_dir) -> list[tuple[list[str], Path]]`
  - `build_concat_cmd(list_file, out_path) -> list[str]`
  - `build_mux_cmd(video, audio, out_path) -> list[str]`

Animation filters arrive in Task 7; this task ships the plain path and the dispatch point.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ffmpeg_cmd.py
from pathlib import Path
from config import Config
from pipeline.scenes import Scene
from pipeline.ffmpeg_cmd import (
    composite_filter, build_scene_clip_cmd, build_concat_cmd, build_mux_cmd,
)

CFG = Config()


def _scene(**kw):
    base = dict(id=1, image_path=Path("conversation_1.png"), text="hello",
                speaker="Mina", duration=2.0)
    base.update(kw)
    return Scene(**base)


def test_composite_fits_then_pads_to_canvas():
    f = composite_filter(CFG)
    assert "scale=1920:1080:force_original_aspect_ratio=decrease" in f
    assert "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black" in f
    assert f.endswith("setsar=1,format=yuv420p")


def test_scene_clip_command_shape():
    cmd = build_scene_clip_cmd(_scene(), CFG, Path("out.mp4"))
    assert cmd[:5] == ["ffmpeg", "-y", "-loop", "1", "-i"]
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "2.000"
    assert cmd[cmd.index("-r") + 1] == "30"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-tune" in cmd and cmd[cmd.index("-tune") + 1] == "stillimage"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[-1] == "out.mp4"


def test_concat_copies_streams():
    cmd = build_concat_cmd(Path("list.txt"), Path("silent.mp4"))
    assert cmd == ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                   "-i", "list.txt", "-c", "copy", "silent.mp4"]


def test_mux_keeps_video_untouched():
    cmd = build_mux_cmd(Path("silent.mp4"), Path("track.wav"), Path("final.mp4"))
    assert cmd[cmd.index("-c:v") + 1] == "copy"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-movflags" in cmd and cmd[cmd.index("-movflags") + 1] == "+faststart"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_ffmpeg_cmd.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.ffmpeg_cmd'`

- [ ] **Step 3: Write the implementation**

```python
# pipeline/ffmpeg_cmd.py
from pathlib import Path

from config import Config
from pipeline.scenes import Scene


def composite_filter(cfg: Config) -> str:
    """Fit a variable-height strip onto the fixed canvas with black bars."""
    return (
        f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,"
        f"pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1,format=yuv420p"
    )


def scene_filter(scene: Scene, cfg: Config) -> str:
    return composite_filter(cfg)


def build_scene_clip_cmd(scene: Scene, cfg: Config, out_path: Path,
                         filter_override: str | None = None) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(scene.image_path),
        "-t", f"{scene.duration:.3f}",
        "-vf", filter_override or scene_filter(scene, cfg),
        "-r", str(cfg.fps),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-crf", str(cfg.crf),
        "-preset", cfg.preset,
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]


def build_clips_for_scene(scene: Scene, cfg: Config, clips_dir: Path):
    """Most scenes are one clip. Punch-in zoom is two."""
    out = clips_dir / f"scene_{scene.id:05d}.mp4"
    return [(build_scene_clip_cmd(scene, cfg, out), out)]


def build_concat_cmd(list_file: Path, out_path: Path) -> list[str]:
    return ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file), "-c", "copy", str(out_path)]


def build_mux_cmd(video: Path, audio: Path, out_path: Path) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/ -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/ffmpeg_cmd.py tests/test_ffmpeg_cmd.py
git commit -m "feat: pure ffmpeg command builders for composite, clip, concat and mux"
```

---

### Task 5: Runner and silent render — STAGE 1 DELIVERABLE

**Files:**
- Create: `pipeline/runner.py`, `pipeline/render.py`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: everything from Tasks 1 to 4
- Produces:
  - `ensure_ffmpeg() -> None`, raises `FFmpegMissing`
  - `run(cmd) -> subprocess.CompletedProcess`, raises `FFmpegFailed`
  - `render_silent(scenes, cfg, workdir, out_path, progress=None) -> Path`

- [ ] **Step 1: Write `pipeline/runner.py`**

```python
# pipeline/runner.py
import shutil
import subprocess


class FFmpegMissing(RuntimeError):
    pass


class FFmpegFailed(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegMissing(
            "FFmpeg is not installed or not on PATH.\n"
            "  macOS:   brew install ffmpeg\n"
            "  Windows: winget install Gyan.FFmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        )


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
        raise FFmpegFailed(f"FFmpeg exited {proc.returncode}:\n{tail}")
    return proc
```

- [ ] **Step 2: Write `pipeline/render.py`**

```python
# pipeline/render.py
from pathlib import Path

from config import Config
from pipeline.ffmpeg_cmd import build_clips_for_scene, build_concat_cmd
from pipeline.runner import ensure_ffmpeg, run


def render_silent(scenes, cfg: Config, workdir: Path, out_path: Path,
                  progress=None) -> Path:
    """Render every scene to its own clip, then concat without re-encoding."""
    ensure_ffmpeg()
    clips_dir = workdir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    for i, scene in enumerate(scenes, start=1):
        for cmd, path in build_clips_for_scene(scene, cfg, clips_dir):
            run(cmd)
            clips.append(path)
        if progress:
            progress(i, len(scenes))

    list_file = workdir / "list.txt"
    list_file.write_text(
        "".join(f"file '{c.resolve().as_posix()}'\n" for c in clips),
        encoding="utf-8",
    )
    run(build_concat_cmd(list_file, out_path))
    return out_path
```

- [ ] **Step 3: Write the smoke test**

```python
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
```

- [ ] **Step 4: Run the whole suite**

Run: `pytest tests/ -v`
Expected: 16 passed (or 15 passed, 1 skipped if FFmpeg is absent)

- [ ] **Step 5: Commit**

```bash
git add pipeline/runner.py pipeline/render.py tests/test_smoke.py
git commit -m "feat: silent render pipeline, clips concatenated without re-encode"
```

- [ ] **Step 6: Produce the stage 1 video and request code review**

Render a real conversation end to end. Watch the whole thing: order correct, timings visibly varying, black bars even, no stretched or squashed strips.

Then dispatch a reviewer per superpowers:requesting-code-review with `BASE_SHA` = the Task 1 commit and `HEAD_SHA` = this one.

**This is the stage 1 deliverable. Send the silent mp4 to the client and wait for pacing feedback before Task 6.** If they want it faster or slower, that is `base` and `per_word` in `config.py` and nothing else.

---

### Task 6: Audio track and mux — STAGE 2 DELIVERABLE

**Files:**
- Create: `pipeline/audio.py`
- Modify: `pipeline/render.py` (add `render`)
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: `Scene` (Task 3), `Config` (Task 1), `build_mux_cmd` (Task 4), `render_silent` (Task 5)
- Produces:
  - `sfx_offsets_ms(scenes) -> list[int]`
  - `total_ms(scenes) -> int`
  - `build_track(scenes, cfg, out_path) -> Path`
  - `render(scenes, cfg, workdir, out_path, progress=None) -> Path`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio.py
from pathlib import Path
from config import Config
from pipeline.scenes import Scene
from pipeline.audio import sfx_offsets_ms, total_ms


def _scenes(n, duration):
    return [Scene(id=i, image_path=Path(f"conversation_{i}.png"), text="x",
                  speaker="Mina", duration=duration) for i in range(1, n + 1)]


def test_first_sfx_fires_at_zero():
    assert sfx_offsets_ms(_scenes(3, 2.0))[0] == 0


def test_offsets_are_integers_and_do_not_drift_over_200_scenes():
    offsets = sfx_offsets_ms(_scenes(200, 2.333))
    assert all(isinstance(o, int) for o in offsets)
    # 2.333s -> 2333ms exactly, so scene 200 starts at 199 * 2333
    assert offsets[-1] == 199 * 2333


def test_total_is_the_last_offset_plus_the_last_scene():
    scenes = _scenes(3, 1.5)
    assert total_ms(scenes) == 4500
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_audio.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.audio'`

- [ ] **Step 3: Write `pipeline/audio.py`**

```python
# pipeline/audio.py
from pathlib import Path

from pydub import AudioSegment

from config import Config


def _ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def sfx_offsets_ms(scenes) -> list[int]:
    """Start time of every scene in whole milliseconds. Integers only: float
    accumulation is audible as drift by the end of a 200 scene video."""
    offsets, cursor = [], 0
    for scene in scenes:
        offsets.append(cursor)
        cursor += _ms(scene.duration)
    return offsets


def total_ms(scenes) -> int:
    return sum(_ms(s.duration) for s in scenes)


def build_track(scenes, cfg: Config, out_path: Path) -> Path:
    total = total_ms(scenes)
    track = AudioSegment.silent(duration=total)

    if cfg.music_path and Path(cfg.music_path).exists():
        music = AudioSegment.from_file(cfg.music_path) + cfg.music_gain_db
        bed = music
        while len(bed) < total:
            bed += music
        track = track.overlay(bed[:total])

    cache: dict[str, AudioSegment] = {}
    for scene, offset in zip(scenes, sfx_offsets_ms(scenes)):
        if scene.sfx not in cache:
            cache[scene.sfx] = AudioSegment.from_file(cfg.sfx_path(scene.sfx)) + cfg.sfx_gain_db
        track = track.overlay(cache[scene.sfx], position=offset)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    track.export(out_path, format="wav")
    return out_path
```

- [ ] **Step 4: Add `render` to `pipeline/render.py`**

```python
# append to pipeline/render.py
from pipeline.audio import build_track
from pipeline.ffmpeg_cmd import build_mux_cmd


def render(scenes, cfg: Config, workdir: Path, out_path: Path,
           progress=None) -> Path:
    """Full render: silent video, prepared audio track, muxed together."""
    workdir.mkdir(parents=True, exist_ok=True)
    silent = render_silent(scenes, cfg, workdir, workdir / "silent.mp4", progress)
    track = build_track(scenes, cfg, workdir / "track.wav")
    run(build_mux_cmd(silent, track, out_path))
    return out_path
```

- [ ] **Step 5: Run the suite and commit**

Run: `pytest tests/ -v`
Expected: 19 passed

```bash
git add pipeline/audio.py pipeline/render.py tests/test_audio.py
git commit -m "feat: sfx and music track built in pydub, muxed without re-encoding video"
```

- [ ] **Step 6: Produce the stage 2 video**

Drop the client's SFX into `assets/sfx/pop.wav` and their music into `assets/music/`, set `music_path` in config, render the same conversation. Listen to the **final transition** specifically, that is where drift would show.

**Send to the client and wait for balance feedback.** Volume complaints are `sfx_gain_db` and `music_gain_db`.

---

### Task 7: Zoom and shake — STAGE 3 DELIVERABLE

**Files:**
- Modify: `pipeline/ffmpeg_cmd.py`
- Test: `tests/test_animation.py`

**Interfaces:**
- Consumes: `composite_filter` (Task 4)
- Produces: `zoom_filter`, `punch_filter`, `shake_filter`, and updated `scene_filter` / `build_clips_for_scene`

⏱ **Timebox the animated zoom to 45 minutes.** If it still jitters, set `zoom_mode = "punch"` and move on. The punch-in cut is a complete delivery of the promised feature, not a downgrade.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_animation.py
from pathlib import Path
from config import Config
from pipeline.scenes import Scene
from pipeline.ffmpeg_cmd import (
    scene_filter, build_clips_for_scene, build_scene_clip_cmd,
)

CFG = Config()


def _scene(**kw):
    base = dict(id=1, image_path=Path("conversation_1.png"), text="hello",
                speaker="Mina", duration=2.0)
    base.update(kw)
    return Scene(**base)


def test_zoom_prescales_before_zoompan():
    f = scene_filter(_scene(zoom=True), CFG)
    assert "scale=3840:2160" in f
    assert f.index("scale=3840:2160") < f.index("zoompan")
    assert "s=1920x1080" in f
    assert "d=60" in f            # 2.0s at 30fps


def test_shake_crops_with_a_time_varying_offset():
    f = scene_filter(_scene(shake=True), CFG)
    assert "crop=iw-24:ih-24:12+12*sin(2*PI*t*8):12+12*cos(2*PI*t*8)" in f
    assert f.endswith("setsar=1,format=yuv420p")


def _encoder_args_only(cmd):
    """Everything except the -vf pair and the trailing output path."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == "-vf":
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out[:-1]


def test_animated_clips_keep_the_same_encoder_settings_as_plain_ones():
    plain = _encoder_args_only(build_scene_clip_cmd(_scene(), CFG, Path("a.mp4")))
    zoomed = _encoder_args_only(build_scene_clip_cmd(_scene(zoom=True), CFG, Path("b.mp4")))
    shaken = _encoder_args_only(build_scene_clip_cmd(_scene(shake=True), CFG, Path("c.mp4")))
    assert plain == zoomed == shaken


def test_punch_mode_emits_two_clips_that_sum_to_the_duration():
    cfg = Config(zoom_mode="punch")
    clips = build_clips_for_scene(_scene(zoom=True), cfg, Path("/tmp"))
    assert len(clips) == 2
    durations = [float(c[0][c[0].index("-t") + 1]) for c in clips]
    assert abs(sum(durations) - 2.0) < 0.001
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `pytest tests/test_animation.py -v`
Expected: FAIL, `scene_filter` currently ignores the flags

- [ ] **Step 3: Replace `scene_filter` and `build_clips_for_scene` in `pipeline/ffmpeg_cmd.py`**

```python
from dataclasses import replace


def zoom_filter(scene: Scene, cfg: Config) -> str:
    frames = max(1, round(scene.duration * cfg.fps))
    return (
        f"{composite_filter(cfg)},"
        f"scale={cfg.width * 2}:{cfg.height * 2},"
        f"zoompan=z='min(zoom+{cfg.zoom_speed},{cfg.zoom_end})':d={frames}:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={cfg.width}x{cfg.height}:fps={cfg.fps},setsar=1,format=yuv420p"
    )


def punch_filter(cfg: Config) -> str:
    c = cfg.punch_crop
    return (
        f"{composite_filter(cfg)},"
        f"crop=iw*{c}:ih*{c},"
        f"scale={cfg.width}:{cfg.height},setsar=1,format=yuv420p"
    )


def shake_filter(cfg: Config) -> str:
    a, f = cfg.shake_amplitude, cfg.shake_frequency
    return (
        f"{composite_filter(cfg)},"
        f"crop=iw-{2 * a}:ih-{2 * a}:{a}+{a}*sin(2*PI*t*{f}):{a}+{a}*cos(2*PI*t*{f}),"
        f"scale={cfg.width}:{cfg.height},setsar=1,format=yuv420p"
    )


def scene_filter(scene: Scene, cfg: Config) -> str:
    if scene.zoom and cfg.zoom_mode == "animated":
        return zoom_filter(scene, cfg)
    if scene.shake:
        return shake_filter(cfg)
    return composite_filter(cfg)


def build_clips_for_scene(scene: Scene, cfg: Config, clips_dir: Path):
    if scene.zoom and cfg.zoom_mode == "punch":
        head = replace(scene, duration=scene.duration * cfg.punch_split, zoom=False)
        tail = replace(scene, duration=scene.duration * (1 - cfg.punch_split), zoom=False)
        pa = clips_dir / f"scene_{scene.id:05d}a.mp4"
        pb = clips_dir / f"scene_{scene.id:05d}b.mp4"
        return [
            (build_scene_clip_cmd(head, cfg, pa, filter_override=composite_filter(cfg)), pa),
            (build_scene_clip_cmd(tail, cfg, pb, filter_override=punch_filter(cfg)), pb),
        ]
    out = clips_dir / f"scene_{scene.id:05d}.mp4"
    return [(build_scene_clip_cmd(scene, cfg, out), out)]
```

- [ ] **Step 4: Run the suite and confirm concat still works**

Run: `pytest tests/ -v`
Expected: 23 passed

Then render a real conversation with two or three scenes flagged. **If concat starts failing here, the animated clip settings drifted from the plain ones. Fix the settings, never the concat.**

- [ ] **Step 5: Commit**

```bash
git add pipeline/ffmpeg_cmd.py tests/test_animation.py
git commit -m "feat: animated zoom, punch-in fallback and shake as per-scene filters"
```

- [ ] **Step 6: Send the stage 3 video and wait for movement feedback**

Render both `zoom_mode` values and show the client each. Too much or too little movement is `zoom_end`, `zoom_speed` and `shake_amplitude`.

---

### Task 8: Streamlit interface — STAGE 4 DELIVERABLE

**Files:**
- Create: `app.py`, `.streamlit/config.toml`

**Interfaces:**
- Consumes: `extract_zips`, `build_scenes` (Task 3), `render` (Task 6), `Config` (Task 1)
- Produces: nothing consumed by later tasks

- [ ] **Step 1: Raise the upload limit**

```toml
# .streamlit/config.toml
[server]
maxUploadSize = 500
```

- [ ] **Step 2: Write `app.py`**

```python
# app.py
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from config import Config
from pipeline.render import render
from pipeline.runner import FFmpegFailed, FFmpegMissing, ensure_ffmpeg
from pipeline.scenes import build_scenes, extract_zips

st.set_page_config(page_title="DM Video Renderer", layout="wide")
st.title("DM Video Renderer")

try:
    ensure_ffmpeg()
except FFmpegMissing as e:
    st.error(str(e))
    st.stop()

cfg = Config()
SFX_CHOICES = sorted(p.stem for p in cfg.sfx_dir.glob("*.wav")) or [cfg.default_sfx]

zips = st.file_uploader("Image zips from Generate All", type="zip",
                        accept_multiple_files=True)
csv_file = st.file_uploader("Sheet exported as CSV", type="csv")

if zips and csv_file and st.button("Load scenes"):
    work = Path(tempfile.mkdtemp(prefix="dmvideo_"))
    zip_paths = []
    for z in zips:
        p = work / z.name
        p.write_bytes(z.getbuffer())
        zip_paths.append(p)
    csv_path = work / "sheet.csv"
    csv_path.write_bytes(csv_file.getbuffer())

    try:
        images = extract_zips(zip_paths, work / "images")
        scenes = build_scenes(images, csv_path, cfg)
    except ValueError as e:
        st.error(str(e))
        st.stop()

    st.session_state.work = str(work)
    st.session_state.scenes = scenes
    st.session_state.table = pd.DataFrame([
        {"id": s.id, "speaker": s.speaker, "message": s.text[:60],
         "seconds": round(s.duration, 2), "zoom": s.zoom, "shake": s.shake,
         "sfx": s.sfx}
        for s in scenes
    ])

if "table" in st.session_state:
    total = st.session_state.table["seconds"].sum()
    st.caption(f"{len(st.session_state.table)} scenes, "
               f"{int(total // 60)}m {int(total % 60)}s")

    edited = st.data_editor(
        st.session_state.table,
        disabled=["id", "speaker", "message"],
        column_config={"sfx": st.column_config.SelectboxColumn(options=SFX_CHOICES)},
        hide_index=True,
        use_container_width=True,
        key="editor",
    )

    if st.button("Render video", type="primary"):
        scenes = st.session_state.scenes
        # Match by id, never by row position: the table can be sorted in the UI.
        by_id = {s.id: s for s in scenes}
        for _, row in edited.iterrows():
            scene = by_id[int(row["id"])]
            scene.duration = float(row["seconds"])
            scene.zoom = bool(row["zoom"])
            scene.shake = bool(row["shake"])
            scene.sfx = str(row["sfx"])

        work = Path(st.session_state.work)
        out = work / "final.mp4"
        bar = st.progress(0.0, text="Rendering scenes")
        try:
            with st.spinner("Rendering"):
                render(scenes, cfg, work / "render", out,
                       progress=lambda i, n: bar.progress(i / n,
                                                          text=f"Scene {i} of {n}"))
        except FFmpegFailed as e:
            st.error(str(e))
            st.stop()

        bar.empty()
        st.success("Done")
        st.video(str(out))
        st.download_button("Download mp4", out.read_bytes(), file_name="conversation.mp4",
                           mime="video/mp4")
```

- [ ] **Step 3: Add pandas to requirements and install**

```bash
echo "pandas>=2.2" >> requirements.txt
pip install -r requirements.txt
```

- [ ] **Step 4: Run it and verify by hand**

Run: `streamlit run app.py`

Check: upload two zips plus a CSV, edit a duration, tick a zoom, change one sfx, render, download. Confirm the edits survive ticking a second checkbox, which is the `st.session_state` trap.

- [ ] **Step 5: Commit**

```bash
git add app.py .streamlit/config.toml requirements.txt
git commit -m "feat: streamlit interface with editable scene table"
```

**Send to the client to run themselves and collect usability feedback.**

---

### Task 9: Packaging and handoff — STAGE 5 DELIVERABLE

**Files:**
- Create: `run.sh`, `run.bat`, `README.md`

- [ ] **Step 1: Write the launchers**

```bash
# run.sh
#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
python -m streamlit run app.py
```

```bat
REM run.bat
@echo off
cd /d "%~dp0"
python -m streamlit run app.py
pause
```

```bash
chmod +x run.sh
```

- [ ] **Step 2: Write `README.md`**

````markdown
# DM Video Renderer

Turns the images from the Instagram DMs Generator sheet into a finished mp4.

## Install once

1. Install Python 3.11 or newer.
2. Install FFmpeg.
   - macOS: `brew install ffmpeg`
   - Windows: `winget install Gyan.FFmpeg`
3. In this folder: `pip install -r requirements.txt`

## Every time

1. In the sheet, hit Generate All and save the zip or zips.
2. File then Download then Comma Separated Values, to get the CSV.
3. Double click `run.sh` (Mac) or `run.bat` (Windows).
4. Upload the zips and the CSV, review the scene list, hit Render, download.

## Changing how it feels

Everything adjustable lives in `config.py`.

| To do this | Change |
|---|---|
| Speed the whole video up or down | `base` and `per_word` |
| Change how far the zoom pushes in | `zoom_end` |
| Swap animated zoom for a hard cut | `zoom_mode` to `"punch"` |
| Change how violent the shake is | `shake_amplitude` |
| Change music or sfx volume | `music_gain_db`, `sfx_gain_db` |

## Adding sound effects

Drop `.wav` files into `assets/sfx/`. The filename becomes the name in the dropdown.

## For whoever builds the centralised app later

`pipeline/` is the engine and has no interface code in it. `app.py` is the only
file that imports Streamlit, and `pipeline/runner.py` is the only one that runs
a subprocess. To plug this into a web app, replace `app.py` and call
`pipeline.render.render(scenes, cfg, workdir, out_path)`.

The image generator is Apps Script and calls Browserless
(`POST /screenshot`, body `{html, selector: ".screenshot-wrapper", viewport:
{width: 450, height: 812, deviceScaleFactor: 3}}`), returning a PNG named
`conversation_<id>.png`. Rebuilding it outside Apps Script means reproducing
that call and the HTML in `buildHtml()`.
````

- [ ] **Step 3: Verify the repo is clean of secrets**

Run: `git log -p | grep -iE "token|api[_-]?key" || echo "clean"`
Expected: `clean`

- [ ] **Step 4: Full end-to-end run on a real 200 scene conversation**

Watch the whole output. Order, pacing, audio sync at the final transition, zoom on the right scenes, no temp files left in the client's folders.

- [ ] **Step 5: Record a 60 second screen capture of the full flow**

- [ ] **Step 6: Commit and request final code review**

```bash
git add run.sh run.bat README.md
git commit -m "docs: launchers, readme and handoff notes"
```

Dispatch a reviewer per superpowers:requesting-code-review with `BASE_SHA` = the Task 5 review commit and `HEAD_SHA` = this one.

---

## Verification checklist

- [ ] `pytest tests/ -v` passes with no skips on a machine with FFmpeg
- [ ] Images appear in correct order across a 200 scene conversation
- [ ] Short messages are visibly shorter on screen than long ones
- [ ] A transition sound fires on every scene change, including the first
- [ ] Audio is still in sync at the final transition
- [ ] Flagged scenes zoom or shake; unflagged scenes are static
- [ ] Output plays in VLC and QuickTime and uploads to YouTube without a re-encode warning
- [ ] A non-technical person completes the flow from the `run` file unaided
- [ ] `git log -p` contains no API key
