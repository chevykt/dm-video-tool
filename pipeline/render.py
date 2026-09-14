# pipeline/render.py
from pathlib import Path

from config import Config
from pipeline.ffmpeg_cmd import build_clips_for_scene, build_concat_cmd, concat_list_text
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
