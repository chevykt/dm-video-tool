# DM Video Renderer

Turns the images from the Instagram DMs Generator sheet into a finished mp4.

## Install once

### 1. Put the folder somewhere sensible

Unzip the app into a folder of its own, for example `C:\DMVideo` on Windows
or your home folder on a Mac. **Do not unzip it into a Desktop or Documents
folder that OneDrive (or iCloud Drive) syncs:** the app keeps a few thousand
setup files next to itself and syncing them causes errors.

### 2. Install Python 3.14

The app works with Python 3.12, 3.13 or 3.14. Get it from
[python.org/downloads](https://www.python.org/downloads/).

- **Windows:** on the Python 3.14 release page, under *Files*, choose
  **Windows installer (64-bit)** and run it. If the installer shows a box
  called **"Add python.exe to PATH"**, tick it. (If you install Python with
  the newer *Python install manager* instead, that works too; there is no
  PATH box to tick.)
- **Mac:** download the **macOS installer** and run it. The `python3` that
  comes with Apple's developer tools is too old and is not used.

### 3. Install FFmpeg

- **Windows:** click **Start**, type `cmd` and open **Command Prompt**. Type
  this and press Enter:

  ```
  winget install Gyan.FFmpeg
  ```

  The first time, it asks you to accept the source agreement terms: type `Y`
  and press Enter. When it has finished, close the Command Prompt window.
- **Mac:** FFmpeg is installed with Homebrew. If you don't have Homebrew yet,
  open **Terminal** (Applications, then Utilities), paste the one-line install
  command from [brew.sh](https://brew.sh), which is

  ```
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

  press Enter, and follow what it prints (at the end it may show "Next steps"
  commands to copy and run). Then run:

  ```
  brew install ffmpeg
  ```

### 4. Add the background music

Rename your music file to `background.mp3` and put it in the `assets/music/`
folder, so it is at `assets/music/background.mp3`. It is not included in this
download; music licensing is your responsibility.

That's it. No `pip install` needed: the first time you double-click the
launcher (below) it sets everything else up for you. That first launch takes
a few minutes and needs an internet connection; every launch after that is
quick.

### Mac only: the first launch of `run.command`

- **macOS 15 (Sequoia) or newer:** double-click `run.command`. When macOS says
  it cannot be opened, click **Done**, then open **System Settings**, go to
  **Privacy & Security**, scroll down to the message about `run.command` and
  click **Open Anyway**, then confirm. You only do this once.
- **Older macOS:** right-click `run.command`, choose **Open**, then **Open**
  again.
- If macOS says you don't have permission to open it, the zip lost the file's
  "can run" setting (this happens when the zip was made on Windows rather
  than downloaded from GitHub). Open Terminal, type `chmod +x ` (with a space
  after it), drag `run.command` into the Terminal window, and press Enter.

## Every time

1. In the sheet, hit **Generate All** and save the zip file(s) it produces.
2. With the conversation's tab open (only the open tab is exported), go to
   **File then Download then Comma Separated Values** to get the CSV.
3. Double-click `run.bat` (Windows) or `run.command` (Mac). A black window
   (Windows) or a Terminal window (Mac) opens, then the app opens in your
   browser.
4. Upload the zip file(s) under **"Image zips from Generate All"** and the
   CSV under **"Sheet exported as CSV"**, then click **Load scenes**.
5. In the table, tick **zoom** or **shake** and choose the sound (**sfx**)
   for each message. You can also type a message's **seconds** by hand.
6. Adjust **Timing** and **Volume** in the sidebar if you want (use
   **Preview audio mix (first 20 messages)** to hear the mix before
   rendering).
7. Click **Render video**. Everything is locked while it renders; wait for
   it to finish (a few minutes for 200 messages).
8. Click **Download mp4**. The video goes to your browser's **Downloads**
   folder, named after the CSV.

**To quit:** close the black window (Windows) or the Terminal window (Mac).
Closing the browser tab alone leaves the app running.

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
| Zoom in on a message, or shake it | Tick its **zoom** or **shake** box in the scene table |
| Change how far the zoom pushes in, every time | `zoom_end` in `config.py` |
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
| "FFmpeg is not installed..." or "...ffprobe was not found..." at startup | Install FFmpeg (see Install once, above) and relaunch. |
| "Could not find a Python this app supports" in the black/Terminal window | Install Python 3.14 (see Install once, above) and double-click the launcher again. |
| "Image and sheet do not line up" | The zip(s) and the CSV are from different runs of Generate All, or a batch of images is missing. Re-export both and try again. |
| "Duplicate images for ids" | The same message image is in more than one zip: usually the same zip uploaded twice, or two batches that overlap. Upload each batch once. |
| "Unexpected image filename" | A zip contains a picture that did not come from Generate All (their names look like `conversation_12.png`). Upload only the zips Generate All produced. |
| "One of the zips is damaged or incomplete" | The zip did not download completely. Download it again from the sheet. |
| "No messages found" | The CSV has no messages or the zips have no images. Check you exported the conversation's tab and uploaded the right zips. |
| "Sheet CSV is missing required column(s)" | The wrong sheet tab was exported. Open the conversation's tab before downloading the CSV. |
| "Background music not found..." | Rename the music to `background.mp3` and put it at `assets/music/background.mp3` (see Install once, above). |
| "Something went wrong — send Keon a screenshot of this" | Something unexpected. Click **Details** under the message and send Keon a screenshot of it. |

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

`requirements.txt` pins the app's direct dependencies and `constraints.txt`
freezes the full tested set (the launchers install with both). For the
tests, install the dev requirements into the project's virtual environment
and run pytest:

```
.venv\Scripts\python -m pip install -r requirements-dev.txt -c constraints.txt    # Windows
.venv\Scripts\python -m pytest tests/

.venv/bin/python -m pip install -r requirements-dev.txt -c constraints.txt        # macOS
.venv/bin/python -m pytest tests/
```
