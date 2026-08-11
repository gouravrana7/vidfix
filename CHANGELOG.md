# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-08-11

### Fixed

- `attach` into `.mpg`/`.mpeg` wrote a file whose video was unreadable — the
  picture stream was copied in a flavour those containers can't describe, and
  players saw an audio-only file. The stream is now rewrapped on the way in, so
  the video plays.
- `.mxf` output no longer accepts H.264. Those files muxed with broken
  timestamps on every path (`generate`, `convert --codec h264`, `attach`);
  `.mxf` now offers ProRes and MPEG-2, both of which come out clean, and asking
  for H.264 gives a one-line message instead of a damaged file.
- `caption` into `.webm` and `.mxf` failed outright: the audio was copied over
  untouched into a container that can't hold it. Audio is now re-encoded to
  whatever the output accepts, so captions land in every video format.
- `vidfix format` now converts audio to audio (`take.wav` → `take.flac`), which
  it used to refuse.
- `--audio silence` wrote a two-channel track while `--audio tone` wrote one, so
  switching between them quietly changed the channel count. Both are mono now.
- `vidfix format` on a file that isn't there says `File not found`, like every
  other command, instead of dumping a raw error.

## [0.3.0] - 2026-07-20

### Fixed

- `generate` and `convert` now produce every container, not just codecs that
  happen to mux in `.mp4`. The output extension picks a codec that actually
  plays in it — `.webm`→VP9/Opus, `.ogv`→Theora/Vorbis, `.mpg`→MPEG-2/AC-3,
  `.mxf`→MPEG-2/48 kHz PCM — so writing `-o clip.webm`/`.mxf`/`.ogv`/`.mpg`
  succeeds instead of failing with a raw FFmpeg error. Pass `--codec` to
  override.
- Impossible format/spec combinations now fail with a clear message instead of
  a cryptic FFmpeg dump — or, in one case, a silently broken file. Covered:
  a codec the container can't hold (e.g. `--codec h264` into `.webm`, or
  h265/ProRes into `.wmv`, which used to write an undecodable video stream);
  a surround layout past the format's ceiling (`.mp3`/`.mpg` are stereo/5.1
  bound); and a non-broadcast frame rate for `.mxf`.
- An output with no (or an unknown) extension — `-o mxf` — now stops up front
  with one line naming the valid formats, on every write command. In the
  wizard, answering the output prompt with just a format name (`mxf`) names
  the file for you; anything unusable re-prompts on the spot.
- GIF output through `generate`/`convert`/`caption`/`attach` (which would fail
  raw or make a broken file) now points to `vidfix format`, the command that
  does palette-correct GIFs. `caption` also picks the codec that fits the
  output container instead of always h264.
- A missing `--audio`/`--subs` file on `attach` errors as `File not found: …`
  instead of an FFmpeg dump.

### Added

- New `vidfix attach` command — mux existing audio file(s) and/or a subtitle
  file (.srt/.vtt) onto a video. Subtitles go in as a soft (toggle-able) track
  by default, or `--burn` them into the picture. The video is stream-copied
  (no quality loss) unless subtitles are burned in.
- `attach --audio` can be repeated to add several audio tracks at once
  (`--audio en.wav --audio hi.mp3`), one output track per file, on any video —
  your own or a `vidfix generate` clip. Containers that hold a single audio
  track (`.flv`) say so instead of failing cryptically, and `vidfix info` shows
  `… · N tracks` when a file carries more than one.
- `vidfix format` now extracts audio: give it a video input and a `.wav`/`.mp3`/
  `.m4a`/`.flac` output to pull the audio track out.
- Every command that writes a file now prints its full saved location.
- `convert` gained a unified `--audio keep|tone|silence|none`, matching
  `generate`'s audio types (silence-replacement is new). The old
  `--no-audio`/`--audio-tone` flags still work as aliases, and the wizard now
  asks the audio type when converting.
- Captions are no longer locked to the `caption` command: `generate` and
  `convert` gained the full caption suite (`--text`, `--position`, `--size`,
  `--color`, `--start`, `--end`), and `convert` also gained `--timecode`.
- Caption placement is now a 3×3 grid — `top-left`, `top`, `top-right`, `left`,
  `center`, `right`, `bottom-left`, `bottom`, `bottom-right` — everywhere a
  caption can be drawn.
- The wizard asks caption placement and colour whenever you add text, and its
  `variants` prompt now makes clear the shown values are editable examples.
- `mpeg2` and `theora` codecs; `format` accepts `.mxf`, `.mpg`, `.mpeg`,
  `.ogv`, `.flv`, `.wmv`, `.3gp` as targets.
- The wizard now offers only what the chosen output format can make: the codec
  list, audio-channel choices, and frame rate are limited to the container's
  real capabilities (with a note about what's left out), and the convert codec
  prompt gains an `auto` default that lets the container decide.
- The wizard's output-file prompt now lists the formats that fit what you're
  making (`formats: mp4, mov, mkv, mxf, webm, … — pick any`), so every container
  is discoverable instead of looking mp4-only.

## [0.2.1] - 2026-07-20

### Changed

- The wizard's first question now defaults to `generate` (listed first too).
- CI workflow token restricted to read-only contents (code-scanning fix).

## [0.2.0] - 2026-07-19

### Added

- `--audio-layout` on `generate` and `convert`: shape audio channels as `mono`,
  `stereo`, `5.1`, `7.1`, or `left`/`right` (tone in one channel of a stereo
  pair, for channel-identification checks).
- Audio-only generation: `vidfix generate -o tone.wav` (also `.mp3`, `.m4a`,
  `.flac`) produces a sound file with no video stream.
- Picture generation: `vidfix generate -o card.png` (also `.jpg`, `.jpeg`,
  `.webp`, `.bmp`, `.tiff`) produces a single-frame test card, with optional
  `--text` caption.
- `vidfix info` now reads audio-only files (shows `video: none`).
- Friendlier durations everywhere: `30 seconds`, `1min`, `2 hours`, `1:30 mins`.
- Wizard: generate asks video / audio-only / picture, prompts for audio mode and
  channels, lists presets with descriptions, and shows examples in every spec
  question; convert can remix audio channels.
- `vidfix info` reads still images without error (duration shown as 0).
- Wizard prompts always say what enter will do: `(preset: 29.97 — enter to
  keep, type to override)` when a preset sets the value, `(enter = keep
  source)` in convert, and normal visible defaults (`(5s)`, `(720p)`)
  everywhere else — no more ambiguous "skip".

### Changed

- `vidfix info` speaks plain language, technical value in brackets:
  `type: mp4 video` instead of `container`, durations as `5.01 seconds` /
  `1m 30s (90.00 seconds)`, resolutions as `720p (1280x720)`, color formats
  as `standard (yuv420p)`, audio channels as `mono` / `stereo (left+right)` /
  `5.1 surround` / `7.1 surround` instead of `2ch`, and sound quality as
  `normal quality (44100 Hz)` / `high quality` / `low quality`
  (`--json` output unchanged).

### Removed

- The pass/fail table `generate` printed after writing a file; check results
  with `vidfix info` or `vidfix verify` instead.

### Fixed

- Wizard prompts with no default no longer show an empty `()` after the label.
- Explicit `--fps` alongside a drop-frame preset (e.g. `--preset df30 --fps 30
  --timecode`) no longer errors; the timecode counting follows the actual rate.

## [0.1.2] - 2026-07-18

### Changed

- Refreshed README (zero-syntax quick start front and center) and packaging
  keywords.

## [0.1.1] - 2026-07-18

### Changed

- Polished package metadata and README wording.

## [0.1.0] - 2026-07-18

### Added

- `vidfix convert` — transform videos to exact fps/duration/resolution/codec with
  stream-copy fast path for trims, `--smooth` motion interpolation, `--extend-mode
  freeze|loop`, aspect-preserving pad (or `--stretch`), `--no-audio`, `--audio-tone`,
  `--precise`.
- `vidfix generate` — synthetic test videos from FFmpeg lavfi sources: smpte,
  color-bars, testsrc, gradient, solid:COLOR patterns; tone/silence/no audio;
  `--timecode` real SMPTE timecode burn-in (drop-frame `HH:MM:SS;FF` with
  semicolon, non-drop with colon); `--text` caption burn-in.
- `vidfix caption` — burn text onto existing videos: positions top/center/bottom,
  `--start`/`--end` time window.
- `vidfix verify` — assert fps/duration/resolution/codec with tolerances; rich
  pass/fail table or `--json`; exit 0/1 for CI.
- `vidfix info` — metadata via system ffprobe (JSON) or `ffmpeg -i` banner
  fallback; friendly container names ("mp4 (major_brand: isom)").
- `vidfix format` — convert any picture or video to any format (image↔image,
  video→any container, palette-optimized GIFs, first-frame thumbnails).
- `vidfix variants` — parallel cartesian product of fps x resolution variants.
- Interactive wizard — bare `vidfix` walks through action/file/preset/specs
  step-by-step, prints the equivalent command, then runs it.
- Presets: built-in broadcast rate family `df30`, `df60`, `ndf30`, `ndf60`,
  `pal25` (alias `ndf25`), `pal50`, `film24`, `film23976`, plus
  `broadcast-1080i`, `web-720p` (drop-frame rates as exact rationals); user
  presets in `~/.config/vidfix/presets.yaml`; `vidfix preset list|show`.
- Typed Python API: `convert`, `generate`, `verify`, `probe`, `to_format`.
- Bundled FFmpeg via imageio-ffmpeg — no system install needed.

[0.2.1]: https://github.com/gouravrana7/vidfix/releases/tag/v0.2.1
[0.2.0]: https://github.com/gouravrana7/vidfix/releases/tag/v0.2.0
[0.1.2]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.2
[0.1.1]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.1
[0.1.0]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.0
