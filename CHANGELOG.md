# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.1]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.1
[0.1.0]: https://github.com/gouravrana7/vidfix/releases/tag/v0.1.0
