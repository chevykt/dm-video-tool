from dataclasses import replace
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


def zoom_filter(scene: Scene, cfg: Config) -> str:
    frames = frames_for(scene.duration, cfg.fps)
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


def build_scene_clip_cmd(scene: Scene, cfg: Config, out_path: Path,
                         filter_override: str | None = None) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(cfg.fps),
        "-i", str(scene.image_path),
        "-frames:v", str(frames_for(scene.duration, cfg.fps)),
        "-vf", filter_override if filter_override is not None else scene_filter(scene, cfg),
        "-r", str(cfg.fps),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-crf", str(cfg.crf),
        "-preset", cfg.preset,
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]


def build_clips_for_scene(scene: Scene, cfg: Config, clips_dir: Path) -> list[tuple[list[str], Path]]:
    """Most scenes are one clip. Punch-in zoom is two."""
    if scene.zoom and cfg.zoom_mode == "punch":
        # Split in whole frames so the two clips add up to exactly the frames
        # the audio offsets assume for this scene.
        total = frames_for(scene.duration, cfg.fps)
        head_frames = max(1, round(total * cfg.punch_split))
        tail_frames = max(1, total - head_frames)
        head = replace(scene, duration=head_frames / cfg.fps, zoom=False)
        tail = replace(scene, duration=tail_frames / cfg.fps, zoom=False)
        pa = clips_dir / f"scene_{scene.id:05d}a.mp4"
        pb = clips_dir / f"scene_{scene.id:05d}b.mp4"
        return [
            (build_scene_clip_cmd(head, cfg, pa, filter_override=composite_filter(cfg)), pa),
            (build_scene_clip_cmd(tail, cfg, pb, filter_override=punch_filter(cfg)), pb),
        ]
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
