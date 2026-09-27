"""Burn text captions into videos (existing files or freshly generated ones).

Caption text goes through drawtext's ``textfile=`` option — writing the text to
a temp file sidesteps every filter-graph escaping rule for user content.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from vidfix.core.ffmpeg import (
    FFmpegRunner,
    ProgressCallback,
    audio_codec_args,
    default_codec_for,
    video_codec_args,
)
from vidfix.core.generate import drawtext_runner, escape_filter_path, find_font
from vidfix.exceptions import InvalidSpecError

_X = {"left": "w/20", "center": "(w-text_w)/2", "right": "w-text_w-w/20"}
_Y = {"top": "h/20", "center": "(h-text_h)/2", "bottom": "h-text_h-h/20"}


def _grid() -> dict[str, str]:
    grid = {}
    for vname, ye in _Y.items():
        for hname, xe in _X.items():
            parts = [p for p in (vname, hname) if p != "center"]
            name = "-".join(parts) or "center"
            grid[name] = f"x={xe}:y={ye}"
    return grid


POSITIONS: dict[str, str] = _grid()

_SIZE_NAMES = frozenset({"w", "h", "W", "H", "main_w", "main_h", "text_w", "text_h", "tw", "th"})

_COLOR_RE = re.compile(r"[A-Za-z0-9#.@]+")


def _check_style(size: str, color: str, start: float | None, end: float | None) -> None:
    names = set(re.findall(r"[A-Za-z_]+", size))
    if not re.fullmatch(r"[\w.+\-*/() ]+", size) or not names <= _SIZE_NAMES:
        raise InvalidSpecError(
            f"Can't use caption size {size!r}; give pixels like 48 or an expression like h/12."
        )
    if not _COLOR_RE.fullmatch(color):
        raise InvalidSpecError(_color_hint(color))
    if (start is not None and start < 0) or (end is not None and end <= 0):
        raise InvalidSpecError("Caption --start/--end must be positive seconds.")
    if start is not None and end is not None and start >= end:
        raise InvalidSpecError(f"Caption --start ({start}) must come before --end ({end}).")


def _color_hint(color: str) -> str:
    return f"Unknown color {color!r}; use a name like white or yellow, or hex like #ff0000."


def validate_color(color: str, runner: FFmpegRunner) -> None:
    """Ask FFmpeg itself whether it knows the color name (the list is FFmpeg's)."""
    if color == "white":
        return
    probe = ["-f", "lavfi", "-i", f"color=c={color}:s=16x16:d=0.04", "-f", "null", "-"]
    if runner.run(probe, check=False).returncode != 0:
        raise InvalidSpecError(_color_hint(color))


def caption_filter(
    textfile: str,
    position: str = "bottom",
    size: str = "h/12",
    color: str = "white",
    font: str | None = None,
    start: float | None = None,
    end: float | None = None,
) -> str:
    """Pure builder for a caption drawtext filter."""
    _check_style(str(size), color, start, end)
    if position not in POSITIONS:
        raise InvalidSpecError(
            f"Unknown position {position!r}; expected one of: {', '.join(POSITIONS)}."
        )
    parts = [f"textfile='{escape_filter_path(textfile)}'"]
    if font:
        parts.append(f"fontfile='{escape_filter_path(font)}'")
    parts += [
        f"fontsize={size}",
        f"fontcolor={color}",
        "box=1",
        "boxcolor=black@0.5",
        "boxborderw=8",
        POSITIONS[position],
    ]
    if start is not None or end is not None:
        lo = start if start is not None else 0
        hi = end if end is not None else 10**9
        parts.append(f"enable='between(t,{lo},{hi})'")
    return "drawtext=" + ":".join(parts)


def write_caption_file(text: str) -> str:
    """Write caption text to a temp file and return its path."""
    if not text.strip():
        raise InvalidSpecError("Caption text is empty.")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", prefix="vidfix-caption-", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(text)
        return handle.name


def caption(
    input_path: str | Path,
    output: str | Path,
    text: str,
    position: str = "bottom",
    size: str = "h/12",
    color: str = "white",
    start: float | None = None,
    end: float | None = None,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Burn a caption into an existing video (audio is re-encoded for the output box)."""
    from vidfix.core.formats import VIDEO_EXTS, prepare_output, validate_output_ext
    from vidfix.core.probe import probe

    validate_output_ext(str(output), VIDEO_EXTS)
    runner = runner or FFmpegRunner()
    if probe(input_path, runner=runner).video_codec == "none":
        raise InvalidSpecError(f"{input_path} has no video to caption.")
    runner = drawtext_runner(runner)
    textfile = write_caption_file(text)
    try:
        vf = caption_filter(
            textfile,
            position=position,
            size=size,
            color=color,
            font=find_font(),
            start=start,
            end=end,
        )
        validate_color(color, runner)
        prepare_output(output, input_path)
        codec = default_codec_for(str(output))
        args = [
            "-i",
            str(input_path),
            "-vf",
            vf,
            *video_codec_args(codec, str(output)),
            *audio_codec_args(str(output)),
        ]
        runner.run([*args, str(output)], on_progress=on_progress)
    finally:
        Path(textfile).unlink(missing_ok=True)
    return Path(output)
