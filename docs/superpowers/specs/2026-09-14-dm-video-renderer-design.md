# DM Conversation Video Renderer — Design

**Status:** approved for planning
**Date:** 2026-09-14
**Client:** AraAra DMs (youtube.com/@ARAARA-g7k)

---

## 1. Problem

The client produces long-form "text story" videos on roughly 30 YouTube channels. Their existing Google Sheet ("Instagram DMs Generator") holds a script, one message per row, and an Apps Script renders each row into a chat-bubble PNG via Browserless and downloads them as a zip.

Everything downstream of that — sequencing the images, timing them, adding sound, adding motion, and rendering an mp4 — is currently manual. This project automates it.

## 2. Scope

Four features, all explicitly agreed with the client and none droppable:

1. Per-image display duration calculated from message length
2. A transition sound effect on every image change
3. A zoom animation on scenes flagged for it
4. A simple internal web interface

Additions the client requested after the original agreement, absorbed into this build:

5. One background music track under the whole video
6. A "shake" animation alongside zoom
7. Roughly ten selectable SFX presets, overridable per scene
8. Timing controls in the interface: an overall speed slider plus the individual timing-rule values, so the client can tune pacing without editing `config.py` (requested 2026-09-15, after approving the stage 1 pacing)
9. Volume controls in the interface: sound effect and music levels in dB, so the client can balance the mix without editing `config.py` (requested 2026-09-15, during the stage 2 review)

**Out of scope.** Auth, user accounts, hosting, job queues, crossfades or any transition beyond zoom and shake, captions, intro or outro cards, multi-conversation batching, saved or per-channel timing presets, and any change to the Apps Script generator. The Supabase migration the client raised is a separate project with its own quote.

## 3. Verified facts about the existing system

These were confirmed by reading the client's sheet, their Apps Script source, and a published video. They are not assumptions.

| Fact | Source | Consequence |
|---|---|---|
| Output is 16:9 landscape, black bars top and bottom, white strip full width and centred | Published video | Canvas is 1920x1080; the tool composites, the generator does not |
| Generated PNGs share a width (1200px) but have variable height | `.screenshot-wrapper` is `width: 400px` + `min-height: 100px`, screenshotted at `deviceScaleFactor: 3` | Every scene must be scaled and padded to a fixed canvas or concat fails |
| Files are named `conversation_<id>.png` | `imageBlob.setName()` in `runBatchGenerator` | Join images to rows by parsed id, never by sort order |
| Multiple images are delivered as one `Insta_Batch_<timestamp>.zip` | `saveLocally()` | Ingest zips, not loose files |
| `runBatchGenerator` groups rows by `conversation_id` and merges consecutive same-speaker messages | Apps Script grouping block | Scene text is the concatenation of all rows sharing an id |
| Rows with empty `conversation_id` or `message` are skipped by the generator | `generateAll` filter | Mirror that filter when parsing the CSV |
| The script reads only `conversation_id`, `name`, `message`, `avatar_url` | `headMap` usage | Adding `zoom` / `shake` columns to the sheet is safe |
| One message bubble per frame, no accumulation on screen | Published video | One scene per id holds in practice |
| Published videos run 8:30 to 11:00 | Channel listing, 112 videos | Target runtime ~9:30 for a 200-row script |
| A live Browserless API key sits in the sheet's API tab | `getBrowserlessToken()` | Never commit it; `.gitignore` from the first commit |

## 4. Architecture

A pure-logic core with a thin execution layer and a swappable interface.

```
dm-video-tool/
  app.py                  Streamlit interface. The ONLY file that imports streamlit.
  config.py               Config dataclass. Every tunable number lives here.
  pipeline/
    __init__.py
    timing.py             Text -> duration. Pure.
    scenes.py             Zip + CSV -> list[Scene]. Pure apart from file reads.
    ffmpeg_cmd.py         Scene + Config -> list[str] argv. Pure.
    audio.py              Scenes -> a single wav track.
    runner.py             The only module that touches subprocess.
    render.py             Orchestration. No ffmpeg strings, no UI.
  assets/
    sfx/                  SFX presets
    music/                Background track
  tests/
  run.sh / run.bat
  requirements.txt
  README.md
  .gitignore
```

The rule that makes this worth doing: **command construction is separated from command execution**, so the filter strings that are easy to get wrong can be asserted in fast unit tests without FFmpeg being involved. `render.py` must never import streamlit, and `app.py` must never build an FFmpeg argument.

Strategy: render each scene to its own short mp4 with identical encoder settings, concat with `-c copy`, then mux one prepared audio track. Per-scene animation becomes a filter swap rather than a `filter_complex` graph, and every stage is independently inspectable.

## 5. Data model

```python
@dataclass
class Scene:
    id: int                 # parsed from conversation_<id>.png
    image_path: Path
    text: str               # all rows with this id, joined in row order
    speaker: str
    duration: float         # seconds, from timing.duration_for()
    zoom: bool
    shake: bool
    sfx: str                # preset name; defaults to config.default_sfx
```

Scenes are ordered by `id` ascending.

## 6. Timing rule

The client explicitly delegated this: "I don't have the exact numbers. I just want it to look natural and enough for viewers to read."

```
duration(text):
    words   = len(text.split())
    chars   = len(text)
    by_word = base + per_word * words
    by_char = base + chars / chars_per_sec
    return clamp(max(by_word, by_char), min_dur, max_dur) / speed
```

Defaults, calibrated against the client's own published runtime rather than invented: a 200-message script at roughly 9:30 implies about 2.85 seconds per message, and their scripts average around 5.5 words.

| Setting | Value | Why |
|---|---|---|
| `base` | 1.0 | Recognition time before reading starts |
| `per_word` | 0.34 | 1.0 + 0.34 x 5.5 = 2.87s average, matching their norm |
| `chars_per_sec` | 17 | Subtitle-industry reading rate; stops "unbelievable" flashing past |
| `min_duration` | 1.2 | Floor for one-word lines like "obviously" |
| `max_duration` | 7.0 | Ceiling for the long CTA lines |
| `speed` | 1.0 | Overall pace. 1.2 plays every message 20% faster |

Taking the **larger** of the word-based and character-based figures is what stops long words being under-timed.

**Overall speed.** `speed` divides the result *after* the clamp, so every scene scales by the same factor, the floor and ceiling included. The total runtime therefore scales by exactly `1 / speed`, which is what lets the interface show the new runtime while the slider moves. The client approved stage 1 pacing at `speed = 1.0`, so the defaults stay unchanged.

The `(text)` prefix on some rows is deliberate narration: it marks messages sent in a private thread rather than the group chat. It renders on screen, the viewer reads it, so it counts toward duration like any other text. Nothing is stripped and there is no config flag for it.

## 7. Compositing

Source strips share a width and vary in height. Every scene is fitted into the canvas with one chain:

```
scale=1920:1080:force_original_aspect_ratio=decrease,
pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,
setsar=1,format=yuv420p
```

`force_original_aspect_ratio=decrease` handles both the common case (a short strip, scaled to full width) and the rare tall one (a very long message, fitted to height instead) without a branch.

**Note on source resolution.** The source is 1200px wide and the canvas is 1920, so the strip is upscaled about 1.6x. The client reviewed their published videos against this and is happy with how they look, so nothing changes. Worth revisiting only if the stage 3 zoom review shows softness, since a 1.25x push on an already-upscaled frame compounds the two. The lever, if it is ever wanted, is `deviceScaleFactor: 3` to `5` in their Apps Script.

## 8. Animation

Both animations operate on the composited 1920x1080 frame, so the push reads as a camera move rather than the strip growing inside static bars.

**Zoom, animated (default).** Pre-scale 2x before `zoompan`, which is the standard fix for its pixel-jitter on stills:

```
<composite chain>,scale=3840:2160,
zoompan=z='min(zoom+0.0015,1.25)':d=<frames>:
        x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':
        s=1920x1080:fps=30,setsar=1,format=yuv420p
```

**Zoom, punch-in (fallback).** Two clips: 40% of the duration at normal framing, then a hard cut to a centre crop scaled back up. Frame-accurate, no jitter, and it is the standard meme-edit vocabulary for landing a joke. Selected by `config.zoom_mode`.

**Shake.** A time-varying crop offset on the composited frame, scaled back to canvas:

```
<composite chain>,crop=iw-40:ih-40:20+12*sin(2*PI*t*8):20+12*cos(2*PI*t*8),
scale=1920:1080,setsar=1,format=yuv420p
```

Every animated clip must end with identical codec, fps, dimensions and pixel format to a plain clip, because `concat -c copy` depends on it. Any concat failure after animation work means those settings drifted.

## 9. Audio

Built entirely in pydub, then muxed in one pass. `adelay` + `amix` is explicitly rejected: N inputs, a volume-normalisation surprise, and an unreadable command.

```
total_ms = sum of scene durations
track    = silence(total_ms)
track    = overlay(music looped/trimmed to total_ms, gain = music_gain_db)
for each scene: track = overlay(sfx_for(scene), position = cumulative_ms)
```

Offsets accumulate in **integer milliseconds**, not floats. Across 200 scenes float drift is audible by the end. Since 2026-09-15 the offsets also come from the running count of whole frames each clip is cut to, not from summed durations, so sound and picture share one clock.

The SFX fires at the start of every scene including the first. Muxing keeps the video untouched:

```
ffmpeg -y -i silent.mp4 -i track.wav -c:v copy -c:a aac -b:a 192k \
  -shortest -movflags +faststart final.mp4
```

**Levels.** `sfx_gain_db` and `music_gain_db` are dB offsets applied in pydub: 0 dB plays a file at its own level, and negative values turn it down. The `config.py` values are the defaults, and the interface can change both per session (§10). Measured at stage 2 with the client's files at the original defaults (-3 / -18), the music sat about 24 dB under the SFX and read as silent. The music default is raised once the client gives their balance answer.

**Music licensing is a client responsibility and has been raised with them.** One track across 30 monetised channels is a copyright-claim generator if it is not properly cleared.

## 10. Interface

Streamlit, deliberately minimal, and the only replaceable part of the system.

1. Upload one or more `.zip` files (multiple, because a 200-row Generate All likely exceeds Apps Script's six-minute execution cap and is probably already run in batches)
2. Upload the sheet CSV
3. Timing and volume controls in the sidebar (see below)
4. An editable scene table: id, message preview, word count, **duration**, **zoom**, **shake**, **sfx preset**
5. Render, with a spinner
6. Preview and download

Scene state lives in `st.session_state`, or edits are wiped on every rerun. `server.maxUploadSize` must be raised; 200 PNGs run 40 to 100MB.

**Timing controls.**
- **Overall speed** slider, 0.7x to 1.5x, with the total runtime updating live as it moves. This is the control the client will mostly use, to aim for a target length.
- An **Advanced timing rules** section with the five rule values under plain labels: pause before reading (`base`), seconds per word (`per_word`), reading speed (`chars_per_sec`), shortest time on screen (`min_duration`), longest time on screen (`max_duration`).
- **Hand edits win.** Moving any control recalculates every scene's duration from the rule, except scenes whose duration was typed into the table by hand. Those keep their value and are marked as hand-set. A **Reset all to the rule** button clears every hand-set duration.
- Controls start at the `config.py` defaults each session. Nothing is saved; changing the defaults is still an edit to `config.py`.
- Table edits are reconciled by scene id into a canonical state in `st.session_state`, and the editor's key is bumped after each edit. That stops stale editor edits being re-applied over durations the sliders have just recalculated.

**Volume controls.**
- **Sound effect volume** slider, -30 to +6 dB, and **Music volume** slider, -40 to 0 dB. Both are labelled in dB, where 0 dB means the file's own level.
- They start at the `config.py` defaults each session. Like the timing controls, nothing is saved.
- **Preview audio mix** builds the track for the first 20 messages at the current levels and plays it in the page, so the client can balance by ear without a full render. It takes seconds; a full render takes over a minute.
- A missing music file (`music_path` set but absent) shows as an error message in the page, not a stack trace, for both the preview and the render.

## 11. Error handling

Three failures get explicit treatment. Everything else may raise.

| Failure | Handling |
|---|---|
| FFmpeg not on PATH | Caught at app start with an OS-specific install hint, not mid-render |
| Image ids and CSV ids disagree | Hard failure naming the unmatched ids on both sides. Silent misalignment is the worst outcome this tool can produce |
| FFmpeg exits non-zero | Surface the last 20 lines of stderr in the UI, not a stack trace |

## 12. Testing

Chosen depth: real tests on the pure core, one end-to-end smoke test.

**Unit.** Duration rule at the client's stated pairs and both clamps; overall speed scaling every duration including the clamps; recalculating durations while keeping hand-set ones; the SFX and music gains changing the level of the built track; natural sort against the `conversation_10` before `conversation_2` trap; id parsing and the multi-row-per-id join; the count-mismatch failure; SFX offsets accumulating without drift over 200 scenes; and zoom, shake and plain clips producing identical codec, fps and dimension flags.

**Smoke.** Three real PNGs end to end, asserting the mp4 exists, ffprobe duration is within 0.1s of the sum, and exactly one audio stream is present.

`app.py` is verified by hand.

## 13. Delivery stages

Agreed with the client. Each produces something watchable, and pacing is settled first because it is the most subjective and the cheapest to change early.

| Stage | Deliverable | Client reviews |
|---|---|---|
| 1 | mp4 from a real conversation, correct order and timings, silent | Pacing |
| 2 | Same video with transition SFX and music | Balance |
| 3 | Zoom on flagged scenes, plus shake | Movement |
| 4 | The interface, run by them | Usability |
| 5 | Repo, setup instructions, screen recording | Handover |

## 14. Open questions

None block starting. Each has a default that ships if no answer arrives.

| Question | Default if unanswered |
|---|---|
| Confirm upload resolution is 1920x1080 | Assume 1920x1080; it is one config value if wrong |

Resolved: images arrive as multiple zips (batched generation is assumed, and accepting several zips works either way). Test generations run against Keon's own Browserless key, so the client's quota is never touched.
