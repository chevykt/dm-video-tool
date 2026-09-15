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


def test_punch_mode_emits_two_clips_that_sum_to_the_scene_frames():
    cfg = Config(zoom_mode="punch")
    clips = build_clips_for_scene(_scene(zoom=True), cfg, Path("/tmp"))
    assert len(clips) == 2
    frames = [int(cmd[cmd.index("-frames:v") + 1]) for cmd, _ in clips]
    assert frames == [24, 36]     # 2.0s = 60 frames, split 40% / 60%


def test_punch_split_never_loses_or_gains_a_frame():
    cfg = Config(zoom_mode="punch")
    clips = build_clips_for_scene(_scene(zoom=True, duration=2.02), cfg, Path("/tmp"))
    frames = [int(cmd[cmd.index("-frames:v") + 1]) for cmd, _ in clips]
    assert sum(frames) == 61      # frames_for(2.02, 30)


def test_punch_split_of_a_two_frame_scene_is_one_and_one():
    cfg = Config(zoom_mode="punch")
    clips = build_clips_for_scene(_scene(zoom=True, duration=2 / 30), cfg, Path("/tmp"))
    frames = [int(cmd[cmd.index("-frames:v") + 1]) for cmd, _ in clips]
    assert frames == [1, 1]


def test_punch_mode_leaves_a_one_frame_scene_as_a_single_clip():
    cfg = Config(zoom_mode="punch")
    clips = build_clips_for_scene(_scene(zoom=True, duration=1 / 30), cfg, Path("/tmp"))
    assert len(clips) == 1
    cmd, _ = clips[0]
    assert cmd[cmd.index("-frames:v") + 1] == "1"
