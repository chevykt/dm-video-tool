from pathlib import Path
from config import Config
from pipeline.scenes import Scene
from pipeline.ffmpeg_cmd import (
    composite_filter, build_scene_clip_cmd, build_concat_cmd, build_mux_cmd,
    concat_list_text,
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
    assert cmd[:7] == ["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i"]
    assert "-t" not in cmd
    assert cmd[cmd.index("-frames:v") + 1] == "60"
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


def test_concat_list_text_formats_plain_paths():
    clips = [Path("clips/scene_00001.mp4"), Path("clips/scene_00002.mp4")]
    text = concat_list_text(clips)
    lines = text.splitlines()
    assert len(lines) == 2
    for c, line in zip(clips, lines):
        assert line == f"file '{c.resolve().as_posix()}'"
    assert text.endswith("\n")


def test_concat_list_text_escapes_apostrophes():
    clip = Path("work/O'Brien/clips/scene_00001.mp4")
    text = concat_list_text([clip])
    resolved = clip.resolve().as_posix()
    escaped = resolved.replace("'", "'\\''")
    assert text == f"file '{escaped}'\n"
