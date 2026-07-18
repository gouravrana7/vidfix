"""Burn text captions into videos (existing files or freshly generated ones).

Caption text goes through drawtext's ``textfile=`` option — writing the text to
a temp file sidesteps every filter-graph escaping rule for user content.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from vidfix.core.ffmpeg import FFmpegRunner, ProgressCallback, video_codec_args
from vidfix.core.generate import drawtext_runner, escape_filter_path, find_font
from vidfix.exceptions import InvalidSpecError

#: Caption placement -> drawtext x/y expressions (centered horizontally).
POSITIONS: dict[str, str] = {
    "top": "x=(w-text_w)/2:y=h/20",
    "center": "x=(w-text_w)/2:y=(h-text_h)/2",
    "bottom": "x=(w-text_w)/2:y=h-text_h-h/20",
}


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
    """Burn a caption into an existing video (audio is stream-copied)."""
    runner = drawtext_runner(runner or FFmpegRunner())
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
        args = ["-i", str(input_path), "-vf", vf, *video_codec_args("h264"), "-c:a", "copy"]
        runner.run([*args, str(output)], on_progress=on_progress)
    finally:
        Path(textfile).unlink(missing_ok=True)
    return Path(output)
