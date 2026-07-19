# vidfix

[![PyPI](https://img.shields.io/pypi/v/vidfix?cacheSeconds=300)](https://pypi.org/project/vidfix/)
[![CI](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/vidfix?cacheSeconds=300)](https://pypi.org/project/vidfix/)
[![License](https://img.shields.io/badge/License-PolyForm_Internal_Use-blue.svg)](LICENSE)

**vidfix** is a CLI-first media toolkit that creates any video, picture, or
audio from nothing, converts anything to any format, and fixes existing files
to exact specs (fps, duration, resolution, audio channels) — then checks its
own work: every file it creates is verified against what you asked for before
it says done. Built for anyone — developers, testers, creators, or someone
who just wants a file converted.

## No commands to learn. It talks to you.

```bash
uvx vidfix
```

That's it — nothing to install, no setup, no boring syntax to memorize.
vidfix asks what you want step by step in plain words, checks every answer
as you type it, runs the job, verifies the result, and shows you the
equivalent one-liner for next time.

## Install

```bash
uvx vidfix                # try instantly — no install
pip install vidfix        # or install for keeps (or: uv tool install vidfix)
```

Everything vidfix needs is built in — install it and it just works.

## Quick start

**No syntax needed** — just run `vidfix` and answer the prompts:

```
$ vidfix
What do you want to do? (convert/generate/caption/format/verify/info/variants): generate
Generate (video/audio-only/picture): video
Pattern (smpte/color-bars/testsrc/gradient/...): smpte
Duration (e.g. 30s, 1min, 1:30) [5s]: 10 seconds
Resolution (e.g. 720p, 1080p, 1280x720) [720p]:
Audio (tone/silence/none) [tone]: tone
Audio channels (mono/stereo/5.1/7.1/left/right) [stereo]: 5.1
...
Output file [test.mp4]: fixture.mp4
equivalent command: vidfix generate --pattern smpte --duration '10 seconds' --audio-layout 5.1 -o fixture.mp4
✓ wrote fixture.mp4
             verified: fixture.mp4
 property     expected          actual        result
 fps          30.000 (±0.01)    30.000 (30)   PASS
 duration     10.000s (±0.1s)   10.000s       PASS
 resolution   1280x720          1280x720      PASS
 codec        h264              h264          PASS
```

Every answer is validated on the spot, the finished file is verified against
your specs, and the equivalent one-liner is printed so you can script it next
time. Or go straight to the flags:

```bash
# A 60fps, 30s, 720p SMPTE-bars clip with a burned-in timecode
vidfix generate -o fixture.mp4 --fps 60 --duration 30s --res 720p --timecode

# Force real footage to exact specs
vidfix convert raw.mov --fps 29.97 --duration 10s --res 1280x720 -o fixture.mp4

# Assert specs in CI (exit 0 pass / 1 fail)
vidfix verify fixture.mp4 --fps 29.97 --duration 10s --res 1280x720
```

## Commands

Everything vidfix can do, at a glance (details in the sections below):

| Command | What it does |
|---|---|
| `vidfix` (no args) | Interactive wizard — answer plain-word prompts, it runs the job, verifies the result, and shows the equivalent one-liner |
| `vidfix generate` | Create synthetic test media to exact specs — videos, audio-only files, or still pictures; patterns, tones, channel layouts, timecode burn-in, no source file needed |
| `vidfix convert` | Force an existing video to exact fps / duration / resolution / codec (stream-copies when possible) |
| `vidfix caption` | Burn a text caption into a video — position, size, color, optional start/end window |
| `vidfix format` | Convert any picture or video to any other format by output extension (incl. palette-optimized GIF, thumbnails) |
| `vidfix verify` | Assert a file matches specs; exit 0 pass / 1 fail — wire straight into CI |
| `vidfix info` | Show a file's details in plain words: type, duration, fps, resolution, codecs (`--json` for scripts) |
| `vidfix variants` | Generate the fps × resolution cartesian product of variants, in parallel |
| `vidfix preset list` / `preset show` | Inspect built-in + user presets (broadcast rate family, see [Presets](#presets)) |

`info` and `variants` were previously named `probe` and `matrix`; the old names
still work as hidden aliases, so existing scripts keep running.

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
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9` | `h264` |
| `--preset` | Preset name for defaults (`vidfix preset list`) | — |
| `--smooth` | Motion-interpolate fps changes (minterpolate) | off |
| `--extend-mode` | When target duration > source: `freeze` last frame or `loop` | `freeze` |
| `--stretch` | Stretch to target resolution (no pad bars) | off |
| `--no-audio` | Drop the audio track | off |
| `--audio-tone` | Replace audio with a 440Hz test tone | off |
| `--audio-layout` | Reshape audio channels: `mono`, `stereo`, `5.1`, `7.1`, `left`, `right` | keep source |
| `--precise` | Force re-encode for frame-accurate trims | off |

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
audio-only (`.wav`, `.mp3`, `.m4a`, `.flac`), or a still picture
(`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`).

Every generated file is auto-verified against the requested specs — the same
pass/fail table `vidfix verify` prints; a mismatch exits 1.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path; extension picks video / audio-only / picture | required |
| `--fps` | Frame rate: `30`, `59.94`, `30000/1001` | `30` |
| `--duration` | Duration: `30s`, `30 seconds`, `1min`, `1:30`, `90` | `5s` |
| `--res` | Resolution: `1280x720`, `720p`, `4k` | `1280x720` |
| `--pattern` | Test pattern: `smpte`, `color-bars`, `testsrc`, `gradient`, `solid:COLOR` | `smpte` |
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9` | `h264` |
| `--audio` | Audio track: `tone` (440Hz), `silence`, `none` | `tone` |
| `--audio-layout` | Audio channels: `mono`, `stereo`, `5.1`, `7.1`, `left`, `right` | `mono` tone / `stereo` silence |
| `--timecode` | Burn in running timecode (`HH:MM:SS:FF`; drop-frame `;FF` for NTSC) | off |
| `--text` | Burn a caption into the video or picture | — |
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

Everything reads in plain words, with the technical value kept in brackets:
the type says whether the file is video or audio, durations are in seconds
(`1m 30s (90.00 seconds)` for longer files), common resolutions get their
everyday name (`1080p`, `4k`), color formats a plain label (`standard`,
`10-bit`), audio channels show as `mono`/`stereo`/`5.1`/`7.1` instead of a
channel count (`stereo (left+right)`, `5.1 surround`), and sound quality in
everyday words (`normal quality (44100 Hz)`, `high quality`, `low quality`). The file type is resolved from the file's `major_brand` tag
(mp4/mov/m4a/3gp) or the extension — not the raw demuxer list
(`mov,mp4,m4a,3gp,3g2,mj2`); `--json` keeps the raw string as `demuxer` and the
tag as `major_brand` alongside the friendly `container`. Broadcast rates get
their preset-family label in the fps line (`df30`, `df60`, `pal25`, `pal50`,
`film24`, `film23976`) so you can read them at a glance.

### `vidfix caption` — burn text into a video

```bash
vidfix caption in.mp4 --text "Take 42" -o out.mp4
vidfix caption in.mp4 --text "INTRO" --position top --color yellow -o out.mp4
vidfix caption in.mp4 --text "3..2..1" --start 0 --end 3 -o out.mp4
vidfix generate -o clip.mp4 --text "TEST CLIP"      # caption a generated video too
```

Positions: `top`, `center`, `bottom` (default). Audio is stream-copied untouched.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--text` | Caption text to burn in | required |
| `--position` | Placement: `top`, `center`, `bottom` | `bottom` |
| `--size` | Font size (pixels or expression like `h/12`) | `h/12` |
| `--color` | Font color: `white`, `yellow`, `#ff0000` | `white` |
| `--start` | Show caption from this second onward | whole video |
| `--end` | Hide caption after this second | whole video |

### `vidfix format` — any picture or video to any format

```bash
vidfix format clip.mov -o clip.mp4      # container conversion
vidfix format clip.mp4 -o clip.gif      # palette-optimized gif
vidfix format photo.png -o photo.webp   # image conversion
vidfix format clip.mp4 -o thumb.jpg     # first-frame thumbnail
```

The output extension picks the format — the only option is `-o, --output` (required).

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

## Python API

```python
from vidfix import convert, generate, verify, probe

generate("fixture.mp4", fps="59.94", duration="30s", res="720p")
info = probe("fixture.mp4")           # MediaInfo (pydantic)
result = verify("fixture.mp4", duration=30.0)
assert result.passed
```

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

[PolyForm Internal Use 1.0.0](LICENSE) — you may use vidfix freely for personal
and internal business purposes (commercial included). Copying, redistributing,
or building products from this source code is not permitted. Contributions are
welcome via pull request.
