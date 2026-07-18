"""Synthetic test-video generation from FFmpeg lavfi sources (no input file)."""

from __future__ import annotations

import re
import shutil
import subprocess
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from vidfix.core.duration import (
    Resolution,
    fps_to_ffmpeg,
    parse_duration,
    parse_fps,
    parse_resolution,
)
from vidfix.core.ffmpeg import (
    FFmpegRunner,
    ProgressCallback,
    audio_codec_args,
    video_codec_args,
)
from vidfix.exceptions import ConversionError, FFmpegNotFoundError, InvalidSpecError

#: Pattern names mapped to lavfi source names. ``solid:COLOR`` is handled separately.
PATTERN_SOURCES: dict[str, str] = {
    "smpte": "smptebars",
    "color-bars": "smptehdbars",
    "testsrc": "testsrc2",
    "gradient": "gradients",
}

AUDIO_MODES = ("tone", "silence", "none")

_COLOR_RE = re.compile(r"^[0-9a-zA-Z#]+$")

#: Common monospace/system fonts checked for drawtext; FFmpeg's fontconfig
#: default is used when none exist (typical on Linux with fontconfig built in).
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Courier New.ttf",  # macOS
    "/System/Library/Fonts/Helvetica.ttc",  # macOS fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",  # Debian/Ubuntu
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",  # Fedora
    "C:\\Windows\\Fonts\\consola.ttf",  # Windows
    "C:\\Windows\\Fonts\\arial.ttf",  # Windows fallback
)


def find_font() -> str | None:
    """First available system font for drawtext, or None to rely on fontconfig."""
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


@lru_cache(maxsize=8)
def _has_drawtext(ffmpeg_path: str) -> bool:
    out = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-filters"], capture_output=True, text=True, check=False
    )
    return "drawtext" in out.stdout


def drawtext_runner(runner: FFmpegRunner) -> FFmpegRunner:
    """A runner whose binary has drawtext; imageio-ffmpeg's Linux/Windows static
    builds lack freetype, so fall back to a system ffmpeg when needed."""
    if _has_drawtext(runner.ffmpeg_path):
        return runner
    system = shutil.which("ffmpeg")
    if system and _has_drawtext(system):
        return FFmpegRunner(ffmpeg_path=system)
    raise ConversionError(
        "--timecode needs FFmpeg's drawtext filter, which the bundled FFmpeg build "
        "lacks on this platform; install a full ffmpeg on your PATH and retry."
    )


def drawtext_available() -> bool:
    """Whether any usable FFmpeg on this machine supports drawtext."""
    try:
        drawtext_runner(FFmpegRunner())
    except (ConversionError, FFmpegNotFoundError):
        return False
    return True


def video_source(pattern: str, fps: Fraction, duration: float, res: Resolution) -> str:
    """Build the lavfi video source spec for a pattern name."""
    options = f"size={res.width}x{res.height}:rate={fps_to_ffmpeg(fps)}:duration={duration}"
    if pattern.startswith("solid:"):
        color = pattern.split(":", 1)[1]
        if not color or not _COLOR_RE.match(color):
            raise InvalidSpecError(
                f"Invalid solid color {color!r}; expected e.g. 'red' or '#ff0000'."
            )
        return f"color=color={color}:{options}"
    if pattern in PATTERN_SOURCES:
        return f"{PATTERN_SOURCES[pattern]}={options}"
    supported = ", ".join([*sorted(PATTERN_SOURCES), "solid:COLOR"])
    raise InvalidSpecError(f"Unknown pattern {pattern!r}; expected one of: {supported}.")


def escape_filter_path(path: str) -> str:
    """Escape a file path for use inside a quoted drawtext option value.

    Windows drive colons need BOTH the option-level escape and graph-level quotes.
    """
    return path.replace("\\", "/").replace(":", "\\:")


#: Rates where broadcast drop-frame timecode is defined (NTSC 29.97/59.94).
DROP_FRAME_TC_RATES = frozenset({Fraction(30000, 1001), Fraction(60000, 1001)})


def timecode_filter(fps: Fraction, font: str | None, drop_frame: bool | None = None) -> str:
    """drawtext filter burning in a running broadcast timecode.

    Drop-frame timecode renders semicolon notation (HH:MM:SS;FF), non-drop
    colon notation (HH:MM:SS:FF). When ``drop_frame`` is None, NTSC 29.97 and
    59.94 default to drop-frame per broadcast convention. No ``text`` option:
    drawtext skips %{...} expansion when ``timecode`` is set, so a frame
    counter would print literally (the timecode's FF field counts frames).
    """
    if drop_frame is None:
        drop_frame = fps in DROP_FRAME_TC_RATES
    elif drop_frame and fps not in DROP_FRAME_TC_RATES:
        raise InvalidSpecError(
            f"Drop-frame timecode is only defined for 29.97/59.94 fps, not {fps_to_ffmpeg(fps)}."
        )
    separator = "\\;" if drop_frame else "\\:"
    fontfile = f"fontfile='{escape_filter_path(font)}':" if font else ""
    return (
        f"drawtext={fontfile}"
        f"timecode='00\\:00\\:00{separator}00':rate={fps_to_ffmpeg(fps)}:"
        "fontsize=h/8:fontcolor=white:box=1:boxcolor=black@0.6:x=10:y=h-th-10"
    )


def build_generate_args(
    output: str,
    fps: Fraction,
    duration: float,
    res: Resolution,
    pattern: str = "smpte",
    codec: str = "h264",
    audio: str = "tone",
    timecode: bool = False,
    drop_frame: bool | None = None,
    font: str | None = None,
    caption_vf: str | None = None,
) -> list[str]:
    """Pure builder for the FFmpeg argument list (after base flags)."""
    if audio not in AUDIO_MODES:
        raise InvalidSpecError(f"Unknown audio mode {audio!r}; expected one of: {AUDIO_MODES}.")

    args = ["-f", "lavfi", "-i", video_source(pattern, fps, duration, res)]
    if audio == "tone":
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={duration}"]
    elif audio == "silence":
        args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

    vf = []
    if timecode:
        vf.append(timecode_filter(fps, font, drop_frame))
    if caption_vf:
        vf.append(caption_vf)
    if vf:
        args += ["-vf", ",".join(vf)]

    args += video_codec_args(codec, output)
    if audio == "none":
        args += ["-an"]
    else:
        args += audio_codec_args(output)
    args += ["-t", f"{duration}", output]
    return args


def generate(
    output: str | Path,
    fps: str | float | Fraction = "30",
    duration: str | float = "5s",
    res: str = "1280x720",
    pattern: str = "smpte",
    codec: str = "h264",
    audio: str = "tone",
    timecode: bool = False,
    drop_frame: bool | None = None,
    text: str | None = None,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Generate a synthetic test video matching the given specs exactly."""
    from vidfix.core.caption import caption_filter, write_caption_file

    out = Path(output)
    runner = runner or FFmpegRunner()
    if timecode or text:
        runner = drawtext_runner(runner)

    textfile = write_caption_file(text) if text else None
    try:
        caption_vf = caption_filter(textfile, font=find_font()) if textfile is not None else None
        args = build_generate_args(
            output=str(out),
            fps=parse_fps(fps),
            duration=parse_duration(duration),
            res=parse_resolution(res),
            pattern=pattern,
            codec=codec,
            audio=audio,
            timecode=timecode,
            drop_frame=drop_frame,
            font=find_font() if timecode else None,
            caption_vf=caption_vf,
        )
        runner.run(args, on_progress=on_progress)
    finally:
        if textfile is not None:
            Path(textfile).unlink(missing_ok=True)
    return out
