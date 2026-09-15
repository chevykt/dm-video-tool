# tests/test_audio.py
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from config import Config
from pipeline.scenes import Scene
from pipeline.audio import build_track, sfx_offsets_ms, total_ms

CFG = Config()


def _scenes(*durations):
    return [Scene(id=i, image_path=Path(f"conversation_{i}.png"), text="x",
                  speaker="Mina", duration=d) for i, d in enumerate(durations, start=1)]


def test_first_sfx_fires_at_zero():
    assert sfx_offsets_ms(_scenes(2.0, 2.0, 2.0), CFG)[0] == 0


def test_offsets_land_on_the_frame_each_clip_starts():
    # 2.02s = 61 frames, 1.51s = 45 frames: clips start at frames 0, 61, 106
    assert sfx_offsets_ms(_scenes(2.02, 1.51, 3.34), CFG) == [0, 2033, 3533]


def test_offsets_are_integers_and_do_not_drift_over_200_scenes():
    offsets = sfx_offsets_ms(_scenes(*[2.333] * 200), CFG)
    assert all(isinstance(o, int) for o in offsets)
    # 2.333s is 70 whole frames, so scene 200 starts at frame 199 * 70 = 13930,
    # which is 464333ms. Summing 2333ms per scene would say 464267ms: 66ms early.
    assert offsets[-1] == 464333


def test_total_covers_the_whole_picture():
    assert total_ms(_scenes(1.5, 1.5, 1.5), CFG) == 4500
    # 61 frames is 2033.3ms: rounded up, so the track is never shorter than the video
    assert total_ms(_scenes(2.02), CFG) == 2034


def test_sfx_lands_on_every_scene_start_and_is_silent_between(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    Sine(1000).to_audio_segment(duration=50).export(sfx_dir / "pop.wav", format="wav")

    scenes = _scenes(2.02, 1.51, 3.34)
    cfg = Config(sfx_dir=sfx_dir, music_path=None)
    out = build_track(scenes, cfg, tmp_path / "track.wav")

    track = AudioSegment.from_file(out)
    assert len(track) == total_ms(scenes, cfg) == 6867

    for start, end in [(0, 50), (2033, 2083), (3533, 3583)]:
        assert track[start:end].dBFS > -20

    for start, end in [(100, 2000), (2100, 3500)]:
        assert track[start:end].dBFS == float("-inf")


def test_missing_music_file_raises_instead_of_silently_skipping(tmp_path):
    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    Sine(1000).to_audio_segment(duration=50).export(sfx_dir / "pop.wav", format="wav")

    missing = tmp_path / "missing.mp3"
    cfg = Config(sfx_dir=sfx_dir, music_path=missing)

    with pytest.raises(FileNotFoundError, match="missing.mp3"):
        build_track(_scenes(2.0, 2.0), cfg, tmp_path / "track.wav")


def test_gains_change_the_level_of_their_own_layer(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import Sine
    from pipeline.audio import build_track

    sfx_dir = tmp_path / "sfx"
    sfx_dir.mkdir()
    Sine(1000).to_audio_segment(duration=200).export(sfx_dir / "pop.wav", format="wav")
    music = tmp_path / "music.wav"
    Sine(300).to_audio_segment(duration=3000).export(music, format="wav")
    scenes = [Scene(id=i, image_path=Path(f"conversation_{i}.png"), text="x",
                    speaker="Mina", duration=1.0) for i in (1, 2)]

    def track(sfx_db, music_db, with_music):
        out = tmp_path / f"track_{sfx_db}_{music_db}_{with_music}.wav"
        cfg = Config(sfx_dir=sfx_dir, music_path=music if with_music else None,
                     sfx_gain_db=sfx_db, music_gain_db=music_db)
        return AudioSegment.from_file(build_track(scenes, cfg, out))

    # SFX on its own (no music): the second SFX plays at 1000-1200ms
    sfx_drop = track(0.0, -18.0, False)[1000:1200].dBFS - track(-12.0, -18.0, False)[1000:1200].dBFS
    assert sfx_drop == pytest.approx(12.0, abs=0.5)
    # music on its own, between the SFX (which play at 0-200ms and 1000-1200ms)
    music_rise = track(-3.0, -10.0, True)[400:900].dBFS - track(-3.0, -30.0, True)[400:900].dBFS
    assert music_rise == pytest.approx(20.0, abs=0.5)
