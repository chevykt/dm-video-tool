from pathlib import Path

from config import Config
from pipeline.scenes import Scene
from pipeline.timing import frames_for


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
        "-framerate", str(cfg.fps),
        "-i", str(scene.image_path),
        "-frames:v", str(frames_for(scene.duration, cfg.fps)),
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


def concat_list_text(clips: list[Path]) -> str:
    """Build the concat-demuxer list file contents, escaping apostrophes
    per the demuxer's single-quote quoting rule (' -> '\\'')."""
    lines = []
    for c in clips:
        escaped = c.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'\n")
    return "".join(lines)


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
