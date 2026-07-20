"""Pure parsers for duration, frame-rate, and resolution specs.

These functions never touch FFmpeg; they only turn user-facing strings into
exact values. Frame rates are ``fractions.Fraction`` so drop-frame rates like
29.97 stay the exact rational 30000/1001 all the way to the FFmpeg command line.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import NamedTuple

from vidfix.exceptions import InvalidSpecError


class Resolution(NamedTuple):
    """A video frame size in pixels."""

    width: int
    height: int

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


NAMED_RESOLUTIONS: dict[str, Resolution] = {
    "240p": Resolution(426, 240),
    "360p": Resolution(640, 360),
    "480p": Resolution(854, 480),
    "720p": Resolution(1280, 720),
    "1080p": Resolution(1920, 1080),
    "1440p": Resolution(2560, 1440),
    "2160p": Resolution(3840, 2160),
    "2k": Resolution(2560, 1440),
    "4k": Resolution(3840, 2160),
    "8k": Resolution(7680, 4320),
}

FPS_LABELS: dict[Fraction, str] = {
    Fraction(24000, 1001): "film23976",
    Fraction(24): "film24",
    Fraction(25): "pal25",
    Fraction(50): "pal50",
    Fraction(30000, 1001): "df30",
    Fraction(60000, 1001): "df60",
}

DROP_FRAME_RATES: dict[str, Fraction] = {
    "23.976": Fraction(24000, 1001),
    "29.97": Fraction(30000, 1001),
    "59.94": Fraction(60000, 1001),
    "119.88": Fraction(120000, 1001),
}

_CLOCK_RE = re.compile(r"^(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):(?P<seconds>\d{1,2}(?:\.\d+)?)$")
_SECONDS_RE = re.compile(
    r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?)?$"
)
_RESOLUTION_RE = re.compile(r"^(?P<width>\d+)\s*[xX]\s*(?P<height>\d+)$")
_FRACTION_RE = re.compile(r"^(?P<num>\d+)\s*/\s*(?P<den>\d+)$")


def parse_duration(spec: str | int | float) -> float:
    """Parse a duration spec into seconds.

    Accepted forms: ``90``, ``2.5``, ``30s``, ``30 seconds``, ``1min``,
    ``2 hours``, ``1:30``, ``1:30 mins``, ``01:02:03.5``.
    """
    if isinstance(spec, (int, float)):
        return _validate_duration(float(spec), spec)

    text = spec.strip().lower()
    if not text:
        raise InvalidSpecError("Duration is empty; expected e.g. '30s', '1:30', or '90'.")
    if ":" in text:
        text = re.sub(r"\s*(m|mins?|minutes?)$", "", text)

    clock = _CLOCK_RE.match(text)
    if clock:
        hours = int(clock.group("hours") or 0)
        minutes = int(clock.group("minutes"))
        seconds = float(clock.group("seconds"))
        if minutes >= 60 and hours:
            raise InvalidSpecError(f"Invalid duration {spec!r}: minutes must be < 60.")
        return _validate_duration(hours * 3600 + minutes * 60 + seconds, spec)

    simple = _SECONDS_RE.match(text)
    if simple:
        value = float(simple.group("value"))
        unit = simple.group("unit")
        if unit and unit.startswith("m"):
            value *= 60
        elif unit and unit.startswith("h"):
            value *= 3600
        return _validate_duration(value, spec)

    raise InvalidSpecError(
        f"Cannot parse duration {spec!r}; expected e.g. '30s', '1:30', '01:02:03', or '90'."
    )


def _validate_duration(seconds: float, original: object) -> float:
    if seconds <= 0:
        raise InvalidSpecError(f"Duration must be positive, got {original!r}.")
    return seconds


def parse_fps(spec: str | int | float | Fraction) -> Fraction:
    """Parse a frame-rate spec into an exact :class:`~fractions.Fraction`.

    Accepted forms: ``60``, ``29.97`` (mapped to 30000/1001), ``30000/1001``.
    """
    if isinstance(spec, Fraction):
        return _validate_fps(spec, spec)
    if isinstance(spec, int):
        return _validate_fps(Fraction(spec), spec)
    if isinstance(spec, float):
        return parse_fps(repr(spec))

    text = spec.strip()
    if not text:
        raise InvalidSpecError("FPS is empty; expected e.g. '30', '59.94', or '30000/1001'.")

    if text in DROP_FRAME_RATES:
        return DROP_FRAME_RATES[text]

    fraction = _FRACTION_RE.match(text)
    if fraction:
        num, den = int(fraction.group("num")), int(fraction.group("den"))
        if den == 0:
            raise InvalidSpecError(f"Invalid fps {spec!r}: denominator cannot be zero.")
        return _validate_fps(Fraction(num, den), spec)

    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidSpecError(
            f"Cannot parse fps {spec!r}; expected e.g. '30', '59.94', or '30000/1001'."
        ) from exc
    return _validate_fps(value, spec)


def _validate_fps(fps: Fraction, original: object) -> Fraction:
    if fps <= 0:
        raise InvalidSpecError(f"FPS must be positive, got {original!r}.")
    if fps > 1000:
        raise InvalidSpecError(f"FPS {original!r} is out of range (max 1000).")
    return fps


def fps_to_ffmpeg(fps: Fraction) -> str:
    """Render a frame rate for an FFmpeg command line, keeping rationals exact."""
    if fps.denominator == 1:
        return str(fps.numerator)
    return f"{fps.numerator}/{fps.denominator}"


def parse_resolution(spec: str) -> Resolution:
    """Parse a resolution spec into a :class:`Resolution`.

    Accepted forms: ``1280x720`` and named shortcuts like ``720p``, ``1080p``, ``4k``.
    """
    text = spec.strip().lower()
    if not text:
        raise InvalidSpecError("Resolution is empty; expected e.g. '1280x720' or '720p'.")

    if text in NAMED_RESOLUTIONS:
        return NAMED_RESOLUTIONS[text]

    match = _RESOLUTION_RE.match(text)
    if match:
        width, height = int(match.group("width")), int(match.group("height"))
        if width <= 0 or height <= 0:
            raise InvalidSpecError(f"Resolution {spec!r} must have positive dimensions.")
        if width % 2 or height % 2:
            raise InvalidSpecError(
                f"Resolution {spec!r} must have even dimensions (required by most codecs)."
            )
        return Resolution(width, height)

    names = ", ".join(sorted(NAMED_RESOLUTIONS))
    raise InvalidSpecError(f"Cannot parse resolution {spec!r}; expected 'WxH' or one of: {names}.")


def format_seconds(seconds: float) -> str:
    """Format seconds as ``H:MM:SS.mmm`` for display."""
    whole = int(seconds)
    millis = round((seconds - whole) * 1000)
    if millis == 1000:
        whole, millis = whole + 1, 0
    hours, rem = divmod(whole, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}.{millis:03d}"
