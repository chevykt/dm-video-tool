# app.py
import tempfile
from dataclasses import replace
from pathlib import Path

import pandas as pd
import streamlit as st

from config import Config
from pipeline.audio import build_track
from pipeline.render import render
from pipeline.runner import FFmpegFailed, FFmpegMissing, ensure_ffmpeg
from pipeline.scenes import build_scenes, extract_zips, retime
from pipeline.timing import frames_for
from table_edits import apply_table_edits

st.set_page_config(page_title="DM Video Renderer", layout="wide")
st.title("DM Video Renderer")

try:
    ensure_ffmpeg()
except FFmpegMissing as e:
    st.error(str(e))
    st.stop()

DEFAULTS = Config()
SFX_CHOICES = sorted(p.stem for p in DEFAULTS.sfx_dir.glob("*.wav")) or [DEFAULTS.default_sfx]


def _runtime(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 60}m {s % 60:02d}s"


# Timing controls. Slider values live only for this session; config.py holds
# the defaults they start from. app.py builds a Config, never an FFmpeg arg.
with st.sidebar:
    st.header("Timing")
    speed = st.slider("Overall speed", 0.7, 1.5, DEFAULTS.speed, 0.05, format="%.2fx",
                      help="1.20x plays every message 20% faster. "
                           "Durations you typed into the table are not changed.")
    with st.expander("Advanced timing rules"):
        base = st.slider("Pause before reading (s)", 0.0, 3.0, DEFAULTS.base, 0.05)
        per_word = st.slider("Seconds per word", 0.10, 1.00, DEFAULTS.per_word, 0.01)
        chars_per_sec = st.slider("Reading speed (characters per second)",
                                  8.0, 30.0, DEFAULTS.chars_per_sec, 0.5)
        # Fixed ranges that meet at 3.0, so the floor can never exceed the ceiling.
        min_duration = st.slider("Shortest time on screen (s)",
                                 0.5, 3.0, DEFAULTS.min_duration, 0.1)
        max_duration = st.slider("Longest time on screen (s)",
                                 3.0, 15.0, DEFAULTS.max_duration, 0.5)

    st.header("Volume")
    sfx_gain_db = st.slider("Sound effect volume (dB)", -30.0, 6.0, DEFAULTS.sfx_gain_db, 0.5,
                            help="0 dB plays the sound file at its own level.")
    music_gain_db = st.slider("Music volume (dB)", -40.0, 0.0, DEFAULTS.music_gain_db, 0.5,
                              help="0 dB plays the music file at its own level.")

cfg = replace(DEFAULTS, speed=speed, base=base, per_word=per_word,
              chars_per_sec=chars_per_sec, min_duration=min_duration,
              max_duration=max_duration,
              sfx_gain_db=sfx_gain_db, music_gain_db=music_gain_db)

zips = st.file_uploader("Image zips from Generate All", type="zip",
                        accept_multiple_files=True)
csv_file = st.file_uploader("Sheet exported as CSV", type="csv")

if zips and csv_file and st.button("Load scenes"):
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

if "scenes" in st.session_state:
    scenes = st.session_state.scenes
    overrides: dict[int, float] = st.session_state.overrides
    retime(scenes, cfg, overrides)  # sliders apply to every scene not set by hand

    # The exact video length: clips are cut to whole frames.
    total = sum(frames_for(s.duration, cfg.fps) for s in scenes) / cfg.fps
    st.caption(f"{len(scenes)} scenes, {_runtime(total)}"
               + (f", {len(overrides)} set by hand" if overrides else ""))

    table = pd.DataFrame([
        {"id": s.id, "speaker": s.speaker, "message": s.text[:60],
         "seconds": round(s.duration, 2), "hand-set": s.id in overrides,
         "zoom": s.zoom, "shake": s.shake, "sfx": s.sfx}
        for s in scenes
    ])
    edited = st.data_editor(
        table,
        disabled=["id", "speaker", "message", "hand-set"],
        column_config={
            "seconds": st.column_config.NumberColumn(min_value=0.2, max_value=30.0,
                                                     step=0.05, format="%.2f"),
            "sfx": st.column_config.SelectboxColumn(options=SFX_CHOICES),
        },
        hide_index=True,
        width="stretch",
        # A fresh key after every reconciled edit, so the editor never re-applies
        # a stale edit on top of durations the sliders have just recalculated.
        key=f"editor_{st.session_state.editor_version}",
    )

    # Fold edits into the canonical state. Match by id, never by row position:
    # the table can be sorted in the UI. The comparison logic itself lives in
    # table_edits.py so it can be unit tested without a Streamlit runtime.
    if apply_table_edits(scenes, overrides, table, edited):
        st.session_state.editor_version += 1
        st.rerun()

    if overrides and st.button("Reset all to the rule"):
        overrides.clear()
        st.session_state.editor_version += 1
        st.rerun()

    # Balance by ear in seconds instead of a full render.
    if st.button("Preview audio mix (first 20 messages)"):
        preview = Path(st.session_state.work) / "preview.wav"
        try:
            build_track(scenes[:20], cfg, preview)
        except FileNotFoundError as e:  # music_path set but the file is missing
            st.error(str(e))
        else:
            st.audio(str(preview))

    if st.button("Render video", type="primary"):
        work = Path(st.session_state.work)
        out = work / "final.mp4"
        # Clear any previous result now, so a failed render never leaves a
        # stale video on screen looking like it belongs to this attempt.
        st.session_state.rendered = None
        bar = st.progress(0.0, text="Rendering scenes")
        try:
            with st.spinner("Rendering"):
                render(scenes, cfg, work / "render", out,
                       progress=lambda i, n: bar.progress(i / n,
                                                          text=f"Scene {i} of {n}"))
        except (FFmpegFailed, FileNotFoundError) as e:
            st.error(str(e))
            st.stop()

        bar.empty()
        st.session_state.rendered = str(out)

    # Rendered outside the button block so it survives reruns that aren't a
    # fresh click of Render video: st.download_button itself triggers a
    # rerun, and so do the sliders and table edits above. It stays on screen
    # until the next successful render replaces it or Load scenes clears it.
    rendered = st.session_state.get("rendered")
    if rendered and Path(rendered).exists():
        st.success("Done")
        st.caption("Last render. Press Render video again after changing settings.")
        st.video(rendered)
        st.download_button("Download mp4", Path(rendered).read_bytes(),
                           file_name="conversation.mp4", mime="video/mp4")
