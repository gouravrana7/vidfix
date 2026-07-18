# vidfix

[![PyPI](https://img.shields.io/pypi/v/vidfix?cacheSeconds=3600)](https://pypi.org/project/vidfix/)
[![CI](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gouravrana7/vidfix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/vidfix?cacheSeconds=3600)](https://pypi.org/project/vidfix/)
[![License](https://img.shields.io/badge/License-PolyForm_Internal_Use-blue.svg)](LICENSE)

**Videos and images, exactly the way you need them.** vidfix is a CLI-first
media toolkit for anyone — developers, testers, creators, or someone who
just wants a file converted: force videos to exact specs (fps, duration,
resolution), generate test clips from nothing, convert any picture or video to
any format, grab thumbnails and GIFs, and verify media specs in CI with proper
exit codes.

FFmpeg is bundled (via imageio-ffmpeg), so `pip install vidfix` just works — no
system FFmpeg required.

## Install

```bash
pip install vidfix        # or: uv tool install vidfix
```

## Quick start

**No syntax needed** — just run `vidfix` and answer the prompts:

```
$ vidfix
What do you want to do? (convert/generate/caption/format/verify/info/variants): convert
Which file do you want to convert?: raw.mov
Preset (none/broadcast-1080i/df30/df60/film24/.../web-720p): df60
Target duration (e.g. 30s, 1:30) (enter to skip): 10s
...
equivalent command: vidfix convert raw.mov --preset df60 --duration 10s --codec h264 -o raw_converted.mov
```

Every answer is validated on the spot, and the equivalent one-liner is printed
so you can script it next time. Or go straight to the flags:

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
| `vidfix` (no args) | Interactive wizard — answer prompts, see the equivalent one-liner, run it |
| `vidfix generate` | Create a synthetic test video to exact specs — patterns, test tone, timecode burn-in, no source file needed |
| `vidfix convert` | Force an existing video to exact fps / duration / resolution / codec (stream-copies when possible) |
| `vidfix caption` | Burn a text caption into a video — position, size, color, optional start/end window |
| `vidfix format` | Convert any picture or video to any other format by output extension (incl. palette-optimized GIF, thumbnails) |
| `vidfix verify` | Assert a file matches specs; exit 0 pass / 1 fail — wire straight into CI |
| `vidfix info` | Pretty-print media metadata: container, duration, fps, resolution, codecs (`--json` for scripts) |
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
```

Trims with an unchanged codec use FFmpeg stream copy (instant, no quality loss).
Resolution changes pad with black bars to preserve aspect ratio (`--stretch` to
disable). Drop-frame rates are passed to FFmpeg as exact rationals
(`30000/1001`), never lossy floats.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--fps` | Target frame rate: `30`, `59.94`, `30000/1001` | keep source |
| `--duration` | Target duration: `30s`, `1:30`, `90` — trims or extends | keep source |
| `--res` | Target resolution: `1280x720`, `720p`, `4k` | keep source |
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9` | `h264` |
| `--preset` | Preset name for defaults (`vidfix preset list`) | — |
| `--smooth` | Motion-interpolate fps changes (minterpolate) | off |
| `--extend-mode` | When target duration > source: `freeze` last frame or `loop` | `freeze` |
| `--stretch` | Stretch to target resolution (no pad bars) | off |
| `--no-audio` | Drop the audio track | off |
| `--audio-tone` | Replace audio with a 440Hz test tone | off |
| `--precise` | Force re-encode for frame-accurate trims | off |

### `vidfix generate` — synthetic fixtures from nothing

```bash
vidfix generate -o bars.mp4 --fps 59.94 --duration 30s --res 1080p
vidfix generate -o count.mp4 --pattern testsrc --timecode    # running timecode overlay
vidfix generate -o df.mp4 --preset df30 --timecode           # drop-frame HH:MM:SS;FF burn-in
vidfix generate -o red.mp4 --pattern solid:red --audio none
```

Patterns: `smpte`, `color-bars`, `testsrc`, `gradient`, `solid:COLOR`.
Audio: 440Hz `tone` (default), `silence`, `none`.

| Option | Meaning | Default |
|---|---|---|
| `-o, --output` | Output file path | required |
| `--fps` | Frame rate: `30`, `59.94`, `30000/1001` | `30` |
| `--duration` | Duration: `30s`, `1:30`, `90` | `5s` |
| `--res` | Resolution: `1280x720`, `720p`, `4k` | `1280x720` |
| `--pattern` | Test pattern: `smpte`, `color-bars`, `testsrc`, `gradient`, `solid:COLOR` | `smpte` |
| `--codec` | Video codec: `h264`, `h265`, `prores`, `vp9` | `h264` |
| `--audio` | Audio track: `tone` (440Hz), `silence`, `none` | `tone` |
| `--timecode` | Burn in running timecode (`HH:MM:SS:FF`; drop-frame `;FF` for NTSC) | off |
| `--text` | Burn a caption into the video | — |
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
 container     mp4
 duration      0:00:30.030 (30.030s)
 resolution    1280x720
 fps           29.970 (df30, 30000/1001)
 video codec   h264
 pixel format  yuv420p
 bitrate       1200 kb/s
 audio         aac 44100 Hz 2ch
```

The container name is resolved from the file's `major_brand` tag (mp4/mov/m4a/3gp)
or the extension — not ffprobe's raw demuxer list (`mov,mp4,m4a,3gp,3g2,mj2`);
`--json` keeps the raw string as `demuxer` and the tag as `major_brand` alongside
the friendly `container`. Broadcast rates get their preset-family label in the fps
line (`df30`, `df60`, `pal25`, `pal50`, `film24`, `film23976`) so QA can read them
at a glance. Uses system `ffprobe` when available, otherwise parses FFmpeg output
directly.

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
| `--jobs` | Parallel FFmpeg processes | `min(4, cpus)` |

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
uv run pytest -m "not integration"        # fast tests only (no FFmpeg)
uv run ruff check . && uv run mypy        # lint + strict types
```

## License

[PolyForm Internal Use 1.0.0](LICENSE) — you may use vidfix freely for personal
and internal business purposes (commercial included). Copying, redistributing,
or building products from this source code is not permitted. Contributions are
welcome via pull request.
