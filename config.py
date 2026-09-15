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
    speed: float = 1.0               # overall pace; 1.2 plays every message 20% faster

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
    music_path: Path | None = Path("assets/music/background.mp3")
    music_gain_db: float = -10.0  # client approved the stage 3 sample at -10 dB

    def sfx_path(self, name: str) -> Path:
        return self.sfx_dir / f"{name}.wav"
