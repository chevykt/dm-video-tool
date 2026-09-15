# app.py
import tempfile
from dataclasses import replace
from pathlib import Path

import streamlit as st

from config import Config
from pipeline.audio import build_track
from pipeline.render import render
from pipeline.runner import FFmpegFailed, FFmpegMissing, ensure_ffmpeg
from pipeline.scenes import build_scenes, extract_zips, retime
from pipeline.timing import frames_for
from table_edits import apply_table_edits, scene_table

st.set_page_config(page_title="DM Video Renderer", layout="wide")
st.title("DM Video Renderer")

try:
    ensure_ffmpeg()
except FFmpegMissing as e:
    st.error(str(e))
    st.stop()

DEFAULTS = Config()
SFX_CHOICES = DEFAULTS.sfx_choices()
TABLE_ORDER = ["id", "zoom", "shake", "sfx", "seconds", "hand-set", "words",
               "speaker", "message"]


def _runtime(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}m {s % 60:02d}s"


def _show_unexpected(e: BaseException) -> None:
    """Anything without its own message: a plain line for the client, and
    the details folded away for whoever debugs it."""
    st.error("Something went wrong — send Keon a screenshot of this.")
    with st.expander("Details"):
        st.exception(e)


def _video_name(csv_name: str, zip_names: list[str]) -> str:
    """The download's file name: the uploaded sheet's, else the first zip's."""
    for name in (csv_name, *zip_names):
        stem = Path(name).stem.strip()
        if stem:
            return f"{stem}.mp4"
    return "conversation.mp4"


def _start_render() -> None:
    # Runs before the rerun the click causes. That whole run then draws every
    # control disabled and does the render at the bottom of the script:
    # touching any control mid-render would otherwise stop the script at its
    # next Streamlit call (runner.fastReruns) and silently cancel the render.
    st.session_state.rendering = True
    st.session_state.rendered = None  # never show a stale video as this attempt's
    st.session_state.render_error = None


st.session_state.setdefault("rendering", False)
st.session_state.setdefault("rendered", None)
st.session_state.setdefault("render_error", None)
busy = st.session_state.rendering

# Timing controls. Slider values live only for this session; config.py holds
# the defaults they start from. app.py builds a Config, never an FFmpeg arg.
with st.sidebar:
    st.header("Timing")
    speed = st.slider("Overall speed", 0.7, 1.5, DEFAULTS.speed, 0.05, format="%.2fx",
                      help="1.20x plays every message 20% faster. "
                           "Durations you typed into the table are not changed.",
                      disabled=busy)
    with st.expander("Advanced timing rules"):
        base = st.slider("Pause before reading (s)", 0.0, 3.0, DEFAULTS.base, 0.05,
                         disabled=busy)
        per_word = st.slider("Seconds per word", 0.10, 1.00, DEFAULTS.per_word, 0.01,
                             disabled=busy)
        chars_per_sec = st.slider("Reading speed (characters per second)",
                                  8.0, 30.0, DEFAULTS.chars_per_sec, 0.5, disabled=busy)
        # Fixed ranges that meet at 3.0, so the floor can never exceed the ceiling.
        min_duration = st.slider("Shortest time on screen (s)",
                                 0.5, 3.0, DEFAULTS.min_duration, 0.1, disabled=busy)
        max_duration = st.slider("Longest time on screen (s)",
                                 3.0, 15.0, DEFAULTS.max_duration, 0.5, disabled=busy)

    st.header("Volume")
    sfx_gain_db = st.slider("Sound effect volume (dB)", -30.0, 6.0, DEFAULTS.sfx_gain_db, 0.5,
                            help="0 dB plays the sound file at its own level.",
                            disabled=busy)
    music_gain_db = st.slider("Music volume (dB)", -40.0, 0.0, DEFAULTS.music_gain_db, 0.5,
                              help="0 dB plays the music file at its own level.",
                              disabled=busy)

cfg = replace(DEFAULTS, speed=speed, base=base, per_word=per_word,
              chars_per_sec=chars_per_sec, min_duration=min_duration,
              max_duration=max_duration,
              sfx_gain_db=sfx_gain_db, music_gain_db=music_gain_db)

zips = st.file_uploader("Image zips from Generate All", type="zip",
                        accept_multiple_files=True, disabled=busy)
csv_file = st.file_uploader("Sheet exported as CSV", type="csv", disabled=busy)

if zips and csv_file and st.button("Load scenes", disabled=busy):
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
    st.session_state.overrides = {}
    st.session_state.editor_version = st.session_state.get("editor_version", 0) + 1
    st.session_state.rendered = None  # a freshly loaded conversation has no render yet
    st.session_state.render_error = None
    st.session_state.video_name = _video_name(csv_file.name, [z.name for z in zips])

if "scenes" in st.session_state:
    scenes = st.session_state.scenes
    overrides: dict[int, float] = st.session_state.overrides
    retime(scenes, cfg, overrides)  # sliders apply to every scene not set by hand

    # The exact video length: clips are cut to whole frames.
    total = sum(frames_for(s.duration, cfg.fps) for s in scenes) / cfg.fps
    st.caption(f"{len(scenes)} scenes, {_runtime(total)}"
               + (f", {len(overrides)} set by hand" if overrides else ""))

    table = scene_table(scenes, overrides)
    try:
        edited = st.data_editor(
            table,
            # Nothing is editable while a render runs (see _start_render).
            disabled=True if busy else ["id", "speaker", "message", "words", "hand-set"],
            # The choices first, so they are on screen at laptop widths.
            column_order=TABLE_ORDER,
            column_config={
                "seconds": st.column_config.NumberColumn(min_value=0.2, max_value=30.0,
                                                         step=0.05, format="%.2f"),
                # required: the grid ignores Delete on these cells. A cleared
                # tick box crashes st.data_editor under pandas 3, and a cleared
                # preset would become a sound called "nan".
                "zoom": st.column_config.CheckboxColumn(required=True),
                "shake": st.column_config.CheckboxColumn(required=True),
                "sfx": st.column_config.SelectboxColumn(options=SFX_CHOICES, required=True),
            },
            hide_index=True,
            width="stretch",
            key=f"editor_{st.session_state.editor_version}",
        )
    except Exception as e:
        # A bad edit is kept in the editor's widget state under its key and
        # raises again on every rerun. Drop it with a fresh editor, once; if
        # the fresh one fails too, say so rather than retrying forever.
        if st.session_state.get("editor_reset") == st.session_state.editor_version:
            _show_unexpected(e)
            st.stop()
        st.session_state.editor_version += 1
        st.session_state.editor_reset = st.session_state.editor_version
        st.rerun()

    # Fold edits into the canonical state. Match by id, never by row position:
    # the table can be sorted in the UI. The comparison logic itself lives in
    # table_edits.py so it can be unit tested without a Streamlit runtime.
    changes = apply_table_edits(scenes, overrides, table, edited)
    if changes.durations:
        # A typed duration gets a fresh editor key, so the editor never
        # re-applies it on top of durations the sliders recalculate later.
        # Ticks and presets keep the same editor: remounting it would jump
        # the grid back to the top-left after every click.
        st.session_state.editor_version += 1
        st.rerun()

    if overrides and st.button("Reset all to the rule", disabled=busy):
        overrides.clear()
        st.session_state.editor_version += 1
        st.rerun()

    # Balance by ear in seconds instead of a full render.
    if st.button("Preview audio mix (first 20 messages)", disabled=busy):
        preview = Path(st.session_state.work) / "preview.wav"
        try:
            build_track(scenes[:20], cfg, preview)
        except FileNotFoundError as e:  # music_path set but the file is missing
            st.error(str(e))
        else:
            st.audio(str(preview))

    st.button("Render video", type="primary", on_click=_start_render, disabled=busy)

    if busy:
        # The controls above are already drawn disabled for this run, so the
        # flag is cleared now, before the render starts. Not in a `finally`:
        # once a run is stopped (the Stop button, a closed tab) every
        # session-state write raises again, so a flag cleared there would
        # stay set and the next run would start rendering all over again.
        st.session_state.rendering = False
        st.warning("Rendering — please wait, don't change anything until it finishes.")
        work = Path(st.session_state.work)
        out = work / "final.mp4"
        bar = st.progress(0.0, text="Preparing the audio")
        try:
            with st.spinner("Rendering"):
                render(scenes, cfg, work / "render", out,
                       progress=lambda i, n: bar.progress(i / n,
                                                          text=f"Scene {i} of {n}"))
        except Exception as e:  # shown after the rerun below, by type
            st.session_state.render_error = e
        else:
            st.session_state.rendered = str(out)
        st.rerun()  # redraw with every control enabled again

    render_error = st.session_state.render_error
    if isinstance(render_error, (FFmpegFailed, FileNotFoundError)):
        st.error(str(render_error))
    elif render_error is not None:
        _show_unexpected(render_error)

    # Rendered outside the render block so it survives reruns that aren't a
    # render: moving a slider or editing the table. It stays on screen until
    # the next successful render replaces it or Load scenes clears it.
    rendered = st.session_state.rendered
    if rendered and Path(rendered).exists():
        st.success("Done")
        st.caption("Last render. Press Render video again after changing settings.")
        st.video(rendered)
        # on_click="ignore": downloading does not rerun the script.
        st.download_button("Download mp4", Path(rendered).read_bytes(),
                           file_name=st.session_state.get("video_name", "conversation.mp4"),
                           mime="video/mp4", on_click="ignore")
