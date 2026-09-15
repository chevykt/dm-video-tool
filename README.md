# DM Video Renderer

Turns the images from the Instagram DMs Generator sheet into a finished mp4.

## Install once

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/).
   - Windows: during install, tick **"Add python.exe to PATH"**.
2. Install FFmpeg.
   - Windows: `winget install Gyan.FFmpeg`
   - macOS: `brew install ffmpeg`
3. Put the background music file at `assets/music/background.mp3`. It is not
   included in this download — music licensing is your responsibility.

That's it. No `pip install` needed: the first time you double-click the
launcher (below) it sets everything else up for you. That first launch takes
a few minutes and needs an internet connection; every launch after that is
quick.

**macOS note:** if Finder refuses to open `run.command` the first time
("unidentified developer"), right-click it and choose **Open** instead of
double-clicking.

## Every time

1. In the sheet, hit **Generate All** and save the zip file(s) it produces.
2. With the conversation's tab open (only the open tab is exported), go to
   **File then Download then Comma Separated Values** to get the CSV.
3. Double-click `run.bat` (Windows) or `run.command` (Mac). The app opens in
   your browser.
4. Upload the zip file(s) under **"Image zips from Generate All"** and the
   CSV under **"Sheet exported as CSV"**, then click **Load scenes**.
5. In the table, choose the zoom, shake and sound effect for each message.
6. Adjust **Timing** and **Volume** in the sidebar if you want (use
   **Preview audio mix (first 20 messages)** to hear the mix before
   rendering).
7. Click **Render video**, wait for it to finish, then click **Download mp4**.

## Changing how it feels

Timing can be tuned in the app's sidebar every session: the **Overall speed**
slider, or the finer rules under **Advanced timing rules**. Durations typed
into the scene table by hand always win; **Reset all to the rule** clears
them. The sidebar starts from the defaults in `config.py` each time, and
everything else adjustable lives there too.

| To do this | Change |
|---|---|
| Speed the whole video up or down, this once | The **Overall speed** slider |
| Change the speed it starts at every time | `speed` in `config.py` (or `base` and `per_word`) |
| Change how far the zoom pushes in, this once | The **zoom** column in the scene table |
| Change how far the zoom pushes in every time | `zoom_end` in `config.py` |
| Change the zoom style every time | `zoom_mode` in `config.py` (`"animated"`, or `"punch"` for a hard cut, which is also the fallback) |
| Change how strong the shake is every time | `shake_amplitude` in `config.py` |
| Change music or sound effect volume, this once | The **Volume** sliders, with **Preview audio mix** to hear it |
| Change the volume it starts at every time | `music_gain_db`, `sfx_gain_db` in `config.py` |

## Adding sound effects

Drop `.wav` or `.mp3` files into `assets/sfx/`. The filename (without the
extension) becomes the name in the **sfx** dropdown in the scene table. The
default is `pop`.

## Troubleshooting

| Message | What it means |
|---|---|
| "FFmpeg is not installed..." at startup | Install FFmpeg (see Install once, above) and relaunch. |
| "Image and sheet do not line up" | The zip(s) and the CSV are from different runs of Generate All, or a batch of images is missing. Re-export both and try again. |
| "Sheet CSV is missing required column(s)" | The wrong sheet tab was exported. Open the conversation's tab before downloading the CSV. |
| "Background music not found..." | Put the music file at `assets/music/background.mp3` (see Install once, above). |

## For whoever builds the centralised app later

`pipeline/` is the engine and has no interface code in it. `app.py` is the
only file that imports Streamlit and never builds FFmpeg arguments;
`pipeline/runner.py` is the only module of this code that starts a
subprocess (pydub also calls FFmpeg internally, for audio decoding). To plug
this into a web app, replace `app.py` and call the entry point
`pipeline.render.render(scenes, cfg, workdir, out_path)`.

The image generator is Apps Script and calls Browserless
(`POST /screenshot`, body `{html, selector: ".screenshot-wrapper", viewport:
{width: 450, height: 812, deviceScaleFactor: 3}}`), returning a PNG named
`conversation_<id>.png`. Rebuilding it outside Apps Script means reproducing
that call and the HTML in `buildHtml()`.

## Developers

Run the tests with the project's virtual environment:

```
.venv\Scripts\python -m pytest tests/     # Windows
.venv/bin/python -m pytest tests/         # macOS
```
