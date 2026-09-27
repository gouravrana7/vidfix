<div align="center">

# vidfix

**Make, convert, fix, and verify media — to exact spec, in one command.**

[![PyPI](https://img.shields.io/pypi/v/vidfix?cacheSeconds=240)](https://pypi.org/project/vidfix/)
[![CI](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/vidfix?cacheSeconds=240)](https://pypi.org/project/vidfix/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

*videos, pictures & audio from nothing · any format to any format ·
multi-track audio · captions & timecode burn-in · pass/fail checks for CI*

[What it does](#what-it-does) · [Wizard](#no-commands-to-learn) · [Python](#use-it-from-python) · [Install](#install) · [Commands](#commands) · [CI](#ci-usage)

</div>

**vidfix** is a CLI-first media toolkit for developers, testers, creators — or
anyone who just needs a file in the right shape. Tell it the fps, length, size,
codec or format you want; it makes the file, then proves it.

## What it does

| You want to… | Run |
|---|---|
| Make a test video, sound or picture from nothing | `vidfix generate -o clip.mp4 --fps 60 --duration 30s --res 1080p` |
| Force a video to exact fps / length / size / codec | `vidfix convert in.mov --fps 29.97 --res 720p -o out.mp4` |
| Turn any file into any other format | `vidfix format clip.mov -o clip.gif` |
| Burn text or a running timecode onto video | `vidfix caption in.mp4 --text "Take 42" -o out.mp4` |
| Add audio tracks or subtitles to a video | `vidfix attach in.mp4 --audio en.wav --subs en.srt -o out.mkv` |
| Read what's inside a file, in plain words | `vidfix info clip.mp4` |
| Check a file in CI (exit 0 pass / 1 fail) | `vidfix verify out.mp4 --fps 60 --res 1080p` |
| Make every fps × size combination at once | `vidfix variants in.mp4 --fps 30,60 --res 720p,1080p -o out/` |

## No commands to learn

```bash
uvx vidfix
```

Run it with no arguments and vidfix asks what you want — no install, no syntax:

- **Arrow keys, not typing.** Every question is a menu, and every choice says
  what it means. Need something not listed? Pick **other…** and type it.
- **Mistakes are caught on the spot.** A bad answer is re-asked right there;
  the wizard never offers a choice the chosen format can't make.
- **You see it before it runs.** A summary box, then run, run & open, or cancel.
- **You learn the one-liner.** The equivalent command is printed for next time,
  and the full path of the saved file when it's done.

```
$ vidfix
╭─ vidfix ────────────────────────────╮
│ exact-spec media · no syntax needed │
╰─────────────────────────────────────╯
✓ Step 1 · What do you want to do?  generate
✓ Step 2 · Generate  video
? Step 3 · Output file (↑↓ to move, enter to pick)
 ❯ test.mp4    plays everywhere
   test.mov    Apple / editing
   test.mkv    holds anything
   test.webm   web video
   ...
   other…      type your own value
```

```
✓ Step 3 · Output file  fixture.mp4
✓ Step 6 · fps  30
✓ Step 7 · Duration  10s
✓ Step 8 · Resolution  1080p
✓ Step 11 · Audio channels  5.1
...
╭─ Ready to generate ───────────╮
│ pattern         smpte         │
│ fps             30            │
│ duration        10s           │
│ audio channels  5.1           │
│ resolution      1080p         │
│ output          fixture.mp4   │
╰───────────────────────────────╯
equivalent command: vidfix generate --pattern smpte --fps 30 --duration 10s --audio-layout 5.1 --res 1080p -o fixture.mp4

✓ Step 18 · Go ahead?  run & open
✓ wrote fixture.mp4
  location: /Users/you/clips/fixture.mp4
```

No arrow keys (a pipe, CI, a basic terminal)? The same questions come as a
numbered list — answer `2`, the name, or your own value.

## Use it from Python

Same features, one import, the same spec forms as the command line:

```python
from vidfix import convert, generate, verify, probe

generate("fixture.mp4", fps="59.94", duration="30s", res="720p")
info = probe("fixture.mp4")           # MediaInfo (pydantic)
result = verify("fixture.mp4", duration=30.0)
assert result.passed
```

Every function takes `str` or `Path`, frame rates as `"29.97"`, `29.97` or
`Fraction(30000, 1001)`, and raises `vidfix.VidfixError` with a readable
message when something can't be done.

## Install

```bash
uvx vidfix                  # run instantly, nothing to install
pip install vidfix          # or keep it (or: uv tool install vidfix)

uvx vidfix@latest           # newest release with uvx
pip install -U vidfix       # upgrade with pip (or: uv tool upgrade vidfix)
vidfix --version            # which version you have
```

Everything vidfix needs is built in. Plain `uvx vidfix` may reuse a copy it
downloaded earlier — add `@latest` to be sure you're on the newest release.
What changed: [CHANGELOG.md](CHANGELOG.md).

## It refuses to write a broken file

Every output format has real limits — codecs it can hold, channel counts,
frame rates, how many audio tracks fit. vidfix knows them. Impossible
combinations stop **before** anything runs, with one plain sentence instead of
a wall of log:

```
$ vidfix generate -o clip.webm --codec h264
error: .webm files can't hold h264; use one of: vp9.

$ vidfix attach clip.mp4 --audio en.wav --audio hi.mp3 -o out.flv
error: .flv holds at most 1 audio track(s); you attached 2. Use .mkv/.mp4/.mov.

$ vidfix generate -o surround.mp3 --audio-layout 5.1
error: .mp3 audio holds at most 2 channels; you asked for 6.
```

The wizard goes one step further: it simply never offers a choice the chosen
format can't make.

## Commands

Every command has `--help`. The same options are in the wizard.

| Command | What it does |
|---|---|
| `vidfix` (no args) | Interactive wizard — answer plain-word prompts, it runs the job and shows the equivalent one-liner |
| `vidfix generate` | Create synthetic test media to exact specs — videos, audio-only files, or still pictures; patterns, tones, channel layouts, timecode burn-in, no source file needed |
| `vidfix convert` | Force an existing video to exact fps / duration / resolution / codec (stream-copies when possible) |
| `vidfix caption` | Burn a text caption into a video — position, size, color, optional start/end window |
| `vidfix attach` | Add audio tracks and/or a subtitle (.srt/.vtt/.ass/.ssa) to a video — soft track or `--burn`-ed in |
| `vidfix format` | Convert any picture or video to any other format by output extension (incl. palette-optimized GIF, thumbnails, audio extraction) |
| `vidfix verify` | Assert a file matches specs; exit 0 pass / 1 fail — wire straight into CI |
| `vidfix info` | Show a file's details in plain words: type, duration, fps, resolution, codecs (`--json` for scripts) |
| `vidfix variants` | Generate the fps × resolution cartesian product of variants, in parallel |
| `vidfix preset list` / `preset show` | Inspect built-in + user presets (broadcast rate family, see [Presets](#presets)) |

Handy on every command that writes a file: `--open` opens the result when
it's done. `python -m vidfix` works too. (`probe` and `matrix` still work as
old names for `info` and `variants`.)

### `vidfix convert` — exact-spec transforms

```bash
vidfix convert in.mp4 --fps 60 --res 1080p -o out.mp4
vidfix convert in.mp4 --fps 60 --smooth -o out.mp4          # motion-interpolated 30→60
vidfix convert in.mp4 --duration 10s -o out.mp4             # trim: instant stream copy
vidfix convert in.mp4 --duration 10s --precise -o out.mp4   # frame-accurate re-encode
vidfix convert in.mp4 --duration 60s --extend-mode loop -o out.mp4
vidfix convert in.mp4 --preset df60 -o out.mp4              # 59.94 = exact 60000/1001
vidfix convert in.mp4 --audio-layout 5.1 -o out.mp4         # remix audio to 5.1
```

Trims with an unchanged codec are stream-copied (instant, no quality loss).
Resolution changes pad with black bars to preserve aspect ratio (`--stretch` to
disable). Drop-frame rates are handled as exact rationals
(`30000/1001`), never lossy floats.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--fps` | Target frame rate: `30`, `59.94`, `30000/1001` | keep source |
| `--duration` | Target duration: `30s`, `1min`, `1:30`, `90` — trims or extends | keep source |
| `--res` | Target resolution: `1280x720`, `720p`, `4k` | keep source |
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9`, `mpeg2`, `theora` | fits the output container |
| `--preset` | Preset name for defaults (`vidfix preset list`) | — |
| `--smooth` | Motion-interpolate fps changes (minterpolate) | off |
| `--extend-mode` | When target duration > source: `freeze` last frame or `loop` | `freeze` |
| `--stretch` | Stretch to target resolution (no pad bars) | off |
| `--audio` | Audio track: `keep` source, `tone` (440Hz), `silence`, `none` (drop) — matches `generate` (`--no-audio`/`--audio-tone` still work as aliases) | `keep` |
| `--audio-layout` | Reshape audio channels: `mono`, `stereo`, `5.1`, `7.1`, `left`, `right` | keep source |
| `--precise` | Force re-encode for frame-accurate trims | off |
| `--text` + `--position`/`--size`/`--color`/`--start`/`--end` | Burn a caption while converting (same options as `caption`) | — |
| `--timecode` | Burn in a running timecode | off |

### `vidfix generate` — synthetic fixtures from nothing

```bash
vidfix generate -o bars.mp4 --fps 59.94 --duration 30s --res 1080p
vidfix generate -o count.mp4 --pattern testsrc --timecode    # running timecode overlay
vidfix generate -o df.mp4 --preset df30 --timecode           # drop-frame HH:MM:SS;FF burn-in
vidfix generate -o red.mp4 --pattern solid:red --audio none
vidfix generate -o surround.mp4 --audio-layout 5.1           # 6-channel audio
vidfix generate -o tone.wav --duration 3s --audio-layout left  # audio-only file
vidfix generate -o card.png --res 1080p --text "SCENE 1"     # still test card
```

Patterns: `smpte`, `color-bars`, `testsrc`, `gradient`, `solid:COLOR`.
Audio: 440Hz `tone` (default), `silence`, `none` — any layout from `mono` to
`7.1`, or `left`/`right` for channel-identification checks.

The output extension picks the media kind: video (`.mp4`, `.mov`, …),
audio-only (`.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.opus`, `.aac`), or a still picture
(`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`).

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path; extension picks video / audio-only / picture | required |
| `--fps` | Frame rate: `30`, `59.94`, `30000/1001` | `30` |
| `--duration` | Duration: `30s`, `30 seconds`, `1min`, `1:30`, `90` | `5s` |
| `--res` | Resolution: `1280x720`, `720p`, `4k` | `1280x720` |
| `--pattern` | Test pattern: `smpte`, `color-bars`, `testsrc`, `gradient`, `solid:COLOR` | `smpte` |
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9`, `mpeg2`, `theora` | fits the output container |
| `--audio` | Audio track: `tone` (440Hz), `silence`, `none` | `tone` |
| `--audio-layout` | Audio channels: `mono`, `stereo`, `5.1`, `7.1`, `left`, `right` | `mono` tone / `stereo` silence |
| `--timecode` | Burn in running timecode (`HH:MM:SS:FF`; drop-frame `;FF` for NTSC) | off |
| `--text` | Burn a caption into the video or picture | — |
| `--position` | Caption placement: `top`/`center`/`bottom`, optionally `-left`/`-right` (9-point grid) | `bottom` |
| `--size` / `--color` | Caption font size (`h/12`, pixels) and color (`white`, `yellow`, `#ff0000`) | `h/12` / `white` |
| `--start` / `--end` | Show the caption only within this second window | full clip |
| `--preset` | Preset name for defaults (`vidfix preset list`) | — |

### `vidfix verify` — spec assertions for CI

```bash
vidfix verify out.mp4 --fps 60 --duration 30s --res 1280x720 --codec h264
vidfix verify out.mp4 --fps 29.97 --json | jq .passed
```

Prints a pass/fail table per property; exit code 0/1.

| Option | Meaning | Default |
|---|---|---|
| `--fps` | Expected frame rate | not checked |
| `--duration` | Expected duration | not checked |
| `--res` | Expected resolution | not checked |
| `--codec` | Expected video codec | not checked |
| `--fps-tolerance` | Allowed fps deviation | `0.01` |
| `--duration-tolerance` | Allowed duration deviation in seconds | `0.1` |
| `--json` | Machine-readable JSON instead of a table | off |

### `vidfix info` — metadata at a glance

```bash
vidfix info clip.mp4             # rich table
vidfix info clip.mp4 --json      # jq-friendly
```

```
$ vidfix info clip.mp4
 type          mp4 video
 duration      30.03 seconds
 resolution    1080p (1920x1080)
 fps           29.970 (df30, 30000/1001)
 video codec   h264
 color format  standard (yuv420p)
 bitrate       1200 kb/s
 audio         aac · stereo (left+right) · normal quality (44100 Hz)
```

Everything reads in plain words, with the technical value kept in brackets —
`1080p (1920x1080)`, `stereo (left+right)`, `normal quality (44100 Hz)`.
Broadcast rates get their preset name (`df30`, `pal25`, `film24`, …). `--json`
gives every raw value for scripts.

### `vidfix caption` — burn text into a video

```bash
vidfix caption in.mp4 --text "Take 42" -o out.mp4
vidfix caption in.mp4 --text "INTRO" --position top --color yellow -o out.mp4
vidfix caption in.mp4 --text "3..2..1" --start 0 --end 3 -o out.mp4
vidfix caption in.mp4 --text "corner" --position top-right -o out.mp4
vidfix generate -o clip.mp4 --text "TEST CLIP"      # caption a generated video too
vidfix convert in.mp4 --text "SUBTITLE" --position bottom -o out.mp4   # or while converting
```

Positions form a 3×3 grid: `top-left`, `top`, `top-right`, `left`, `center`,
`right`, `bottom-left`, `bottom` (default), `bottom-right`. The same caption
options are available on `caption`, `generate`, and `convert`. In `caption`,
audio is re-encoded to whatever the output container accepts.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--text` | Caption text to burn in | required |
| `--position` | Placement (9-point grid, see above) | `bottom` |
| `--size` | Font size (pixels or expression like `h/12`) | `h/12` |
| `--color` | Font color: `white`, `yellow`, `#ff0000` | `white` |
| `--start` | Show caption from this second onward | whole video |
| `--end` | Hide caption after this second | whole video |

### `vidfix attach` — mux audio and/or subtitles onto a video

```bash
vidfix attach clip.mp4 --audio track.m4a -o out.mp4                 # add an audio track
vidfix attach clip.mp4 --audio en.wav --audio hi.mp3 -o out.mkv     # two audio tracks
vidfix attach clip.mp4 --subs subs.srt -o out.mkv                   # soft subtitle track
vidfix attach clip.mp4 --subs subs.srt --burn -o out.mp4           # burn subtitles into the picture
vidfix attach clip.mp4 --audio track.m4a --subs subs.srt -o out.mkv # all at once
```

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--audio` | Audio file to add as a track (repeat for multiple tracks) | — |
| `--subs` | Subtitle file (.srt/.vtt/.ass/.ssa) to add | — |
| `--burn` | Burn subtitles into the picture (else a soft, toggle-able track) | off |

The video is stream-copied (no re-encode, no quality loss) whenever the output
can hold it cleanly; otherwise — burned subtitles, a codec the output can't hold,
or `.avi`/`.mpg` on either side — it is re-encoded so the file always plays.
Repeat `--audio` to add several tracks (one per file, in order) — it works on
any video, including a `vidfix generate` clip. `.flv` holds only one
audio track; use `.mkv`/`.mp4`/`.mov` for more. Soft subtitles need a
`.mp4`/`.mov`/`.mkv`/`.webm` output — for other containers use `--burn`.

### `vidfix format` — any picture or video to any format

```bash
vidfix format clip.mov -o clip.mp4      # container conversion
vidfix format clip.mp4 -o clip.gif      # palette-optimized gif
vidfix format photo.png -o photo.webp   # image conversion
vidfix format clip.mp4 -o thumb.jpg     # first-frame thumbnail
vidfix format clip.mp4 -o audio.mp3     # extract the audio track
vidfix format take.wav -o take.flac     # audio to another audio format
```

The output extension picks the format — the only option is `-o, --output` (required).
Video targets: `mp4`, `mov`, `mkv`, `webm`, `avi`, `m4v`, `ts`, `mxf`, `mpg`, `ogv`,
`flv`, `wmv`, `3gp`, `gif`. Picture targets: `png`, `jpg`, `webp`, `bmp`, `tiff`.
Audio targets (from a video or another audio file): `wav`, `mp3`, `m4a`, `flac`,
`ogg`, `opus`, `aac`.
`generate` and `convert` write the same video containers, each with a codec that plays in it.

### `vidfix variants` — variant grids in parallel

```bash
vidfix variants in.mp4 --fps 30,60 --res 720p,1080p -o out/
# → variants/in_30fps_720p.mp4, in_30fps_1080p.mp4, in_60fps_720p.mp4, ...
```

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output directory | required |
| `--fps` | Comma-separated frame rates, e.g. `30,60` | required |
| `--res` | Comma-separated resolutions, e.g. `720p,1080p` | required |
| `--codec` | Video codec for all variants | `h264` |
| `--jobs` | Parallel worker processes | `min(4, cpus)` |

Exit code is 1 if any variant fails. `vidfix info` takes just the file and
`--json`; `vidfix preset list` / `preset show NAME` take no options.

### Presets

```bash
vidfix preset list
vidfix preset show df30
vidfix generate -o pal.mp4 --preset pal25 --timecode
```

Built-in broadcast rate family:

| Preset | fps | Timecode counting |
|---|---|---|
| `df30` | 29.97 (30000/1001) | drop-frame (`HH:MM:SS;FF`) |
| `df60` | 59.94 (60000/1001) | drop-frame (`HH:MM:SS;FF`) |
| `ndf30` | 29.97 (30000/1001) | non-drop (`HH:MM:SS:FF`) |
| `ndf60` | 59.94 (60000/1001) | non-drop (`HH:MM:SS:FF`) |
| `pal25` (alias `ndf25`) | exact 25 | non-drop (`HH:MM:SS:FF`) |
| `pal50` | exact 50 | non-drop (`HH:MM:SS:FF`) |
| `film24` | exact 24 | non-drop (`HH:MM:SS:FF`) |
| `film23976` | 23.976 (24000/1001) | non-drop (`HH:MM:SS:FF`) |

Plus `broadcast-1080i` (25 fps, 1920x1080) and `web-720p` (30 fps, 720p, h264).
With `--timecode`, DF presets burn semicolon drop-frame notation and NDF/PAL/film
presets colon notation, matching broadcast convention. Aliases (`alias: pal25`)
work in user presets too. Add your own in `~/.config/vidfix/presets.yaml`;
explicit flags always override.

## vidfix vs moviepy vs raw FFmpeg

| | vidfix | moviepy | raw ffmpeg |
|---|---|---|---|
| Exact-spec test fixtures | ✅ one command | ⚠️ manual | ⚠️ long filter incantations |
| Spec verification + exit codes | ✅ built in | ❌ | ⚠️ ffprobe + shell glue |
| Install without system FFmpeg | ✅ bundled | ✅ bundled | ❌ |
| Editing/compositing/effects | ❌ not the goal | ✅ | ✅ |
| Programmatic frame access | ❌ | ✅ numpy frames | ⚠️ |
| Speed | ✅ direct filters, stream copy | ⚠️ python frame loop | ✅ |

Use **moviepy** to *edit* videos, **raw ffmpeg** for full control, **vidfix**
for exact-spec media, quick conversions, and CI checks with zero setup.

## CI usage

```yaml
- name: Verify rendered output specs
  run: |
    pip install vidfix
    vidfix verify build/output.mp4 --fps 60 --duration 30s --res 1280x720
```

## Development

```bash
uv sync                                   # install with dev deps
uv run pytest                             # unit + integration tests
uv run pytest -m "not integration"        # fast tests only
uv run ruff check . && uv run mypy        # lint + strict types
```

## License

[MIT](LICENSE) — free to use, modify and distribute for any purpose, including
commercial use and client work. Keep the copyright notice with any copy you
pass on. Contributions are welcome via pull request.
