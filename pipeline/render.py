# pipeline/render.py
from pathlib import Path

from config import Config
from pipeline.audio import build_track
from pipeline.ffmpeg_cmd import build_clips_for_scene, build_concat_cmd, build_mux_cmd, concat_list_text
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
    list_file.write_text(concat_list_text(clips), encoding="utf-8")
    run(build_concat_cmd(list_file, out_path))
    return out_path


def render(scenes, cfg: Config, workdir: Path, out_path: Path,
           progress=None) -> Path:
    """Full render: prepared audio track, silent video, muxed together.

    The track is built first: it takes seconds, and a missing music or sound
    effect file then fails at once instead of after every clip has rendered.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    track = build_track(scenes, cfg, workdir / "track.wav")
    silent = render_silent(scenes, cfg, workdir, workdir / "silent.mp4", progress)
    run(build_mux_cmd(silent, track, out_path))
    return out_path
