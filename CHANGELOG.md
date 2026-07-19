# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- `generate` auto-verifies its output (fps/duration/resolution/codec for video,
  duration for audio-only, resolution for pictures), prints the same pass/fail
  table as `vidfix verify`, and exits 1 on mismatch.
- `vidfix info` reads still images without error (duration shown as 0).

### Changed

- `vidfix info` speaks plain language, technical value in brackets:
  `type: mp4 video` instead of `container`, durations as `5.01 seconds` /
  `1m 30s (90.00 seconds)`, resolutions as `720p (1280x720)`, color formats
  as `standard (yuv420p)`, audio channels as `mono` / `stereo (left+right)` /
  `5.1 surround` / `7.1 surround` instead of `2ch`, and sound quality as
  `normal quality (44100 Hz)` / `high quality` / `low quality`
  (`--json` output unchanged).

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

[0.1.2]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.2
[0.1.1]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.1
[0.1.0]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.0
