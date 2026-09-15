# pipeline/audio.py
from pathlib import Path

from pydub import AudioSegment

from config import Config
from pipeline.timing import frames_for


def sfx_offsets_ms(scenes, cfg: Config) -> list[int]:
    """Start time of every scene in whole milliseconds.

    Taken from the running total of whole frames, the same number each video
    clip is cut to, so the sound cannot drift from the picture. Each offset is
    within half a millisecond of its frame and the error never accumulates.
    """
    offsets, frames = [], 0
    for scene in scenes:
        offsets.append(round(frames * 1000 / cfg.fps))
        frames += frames_for(scene.duration, cfg.fps)
    return offsets


def total_ms(scenes, cfg: Config) -> int:
    """Video length in whole milliseconds, rounded up so the track is never
    shorter than the picture (the mux uses -shortest)."""
    frames = sum(frames_for(s.duration, cfg.fps) for s in scenes)
    return -(-frames * 1000 // cfg.fps)


def build_track(scenes, cfg: Config, out_path: Path) -> Path:
    total = total_ms(scenes, cfg)
    track = AudioSegment.silent(duration=total)

    if cfg.music_path is not None:
        music_path = Path(cfg.music_path)
        if not music_path.exists():
            raise FileNotFoundError(
                f"Background music not found at {music_path}. "
                "Put the track there, or set music_path = None in config.py for no music."
            )
        music = AudioSegment.from_file(music_path) + cfg.music_gain_db
        bed = music
        while len(bed) < total:
            bed += music
        track = track.overlay(bed[:total])

    cache: dict[str, AudioSegment] = {}
    for scene, offset in zip(scenes, sfx_offsets_ms(scenes, cfg)):
        if scene.sfx not in cache:
            cache[scene.sfx] = AudioSegment.from_file(cfg.sfx_path(scene.sfx)) + cfg.sfx_gain_db
        track = track.overlay(cache[scene.sfx], position=offset)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    track.export(out_path, format="wav")
    return out_path
