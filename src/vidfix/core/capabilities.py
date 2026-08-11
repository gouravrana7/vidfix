"""Per-container capability limits.

Each output format can only hold certain codecs, frame rates, channel counts,
and pixel dimensions. FFmpeg rejects invalid combinations with cryptic errors —
or, for a few containers, writes a silently broken file (exit 0, no decodable
stream). vidfix validates against these tables up front and explains the limit,
and the wizard uses them to offer only the choices a format can actually make.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from vidfix.exceptions import InvalidSpecError

CONTAINER_ALLOWED_CODECS: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"h264", "h265", "vp9", "mpeg2"}),
    ".m4v": frozenset({"h264"}),
    ".mov": frozenset({"h264", "h265", "prores", "mpeg2", "theora"}),
    ".mkv": frozenset({"h264", "h265", "vp9", "prores", "mpeg2", "theora"}),
    ".webm": frozenset({"vp9"}),
    ".avi": frozenset({"h264", "h265", "vp9", "prores", "mpeg2", "theora"}),
    ".ts": frozenset({"h264", "h265", "mpeg2"}),
    ".mxf": frozenset({"prores", "mpeg2"}),
    ".mpg": frozenset({"h264", "h265", "mpeg2"}),
    ".mpeg": frozenset({"h264", "h265", "mpeg2"}),
    ".ogv": frozenset({"theora"}),
    ".flv": frozenset({"h264", "vp9"}),
    ".wmv": frozenset({"h264", "vp9", "mpeg2", "theora"}),
    ".3gp": frozenset({"h264"}),
}

CONTAINER_MAX_CHANNELS: dict[str, int] = {
    ".mpg": 6,
    ".mpeg": 6,
    ".mp3": 2,
}

_MXF_FPS = frozenset({23.976, 24.0, 25.0, 29.97, 30.0, 48.0, 50.0, 59.94, 60.0})
CONTAINER_FPS: dict[str, frozenset[float]] = {".mxf": _MXF_FPS}

CONTAINER_MAX_AUDIO_STREAMS: dict[str, int] = {
    ".flv": 1,
}


def _ext(output: str) -> str:
    return Path(output).suffix.lower()


def allowed_codecs(output: str) -> frozenset[str] | None:
    """Codecs the container can hold, or None if it imposes no restriction."""
    return CONTAINER_ALLOWED_CODECS.get(_ext(output))


def allowed_fps(output: str) -> frozenset[float] | None:
    """Frame rates (as floats) the container restricts to, or None if any go."""
    return CONTAINER_FPS.get(_ext(output))


def max_channels(output: str) -> int | None:
    """Highest channel count the container's audio can carry, or None."""
    return CONTAINER_MAX_CHANNELS.get(_ext(output))


def validate_codec(codec: str, output: str) -> None:
    """Reject a codec the output container can't hold, naming the ones it can."""
    allowed = allowed_codecs(output)
    if allowed is not None and codec not in allowed:
        raise InvalidSpecError(
            f"{_ext(output)} files can't hold {codec}; use one of: {', '.join(sorted(allowed))}."
        )


def validate_fps(fps: Fraction, output: str) -> None:
    """Reject a frame rate a broadcast container (MXF) won't accept."""
    allowed = allowed_fps(output)
    if allowed is not None and not any(abs(float(fps) - rate) < 0.05 for rate in allowed):
        nice = ", ".join(f"{rate:g}" for rate in sorted(allowed))
        raise InvalidSpecError(
            f"{_ext(output)} needs a standard broadcast frame rate ({nice}); "
            f"{float(fps):g} isn't one."
        )


def max_audio_streams(output: str) -> int | None:
    """Highest number of audio tracks the container can hold, or None."""
    return CONTAINER_MAX_AUDIO_STREAMS.get(_ext(output))


def validate_audio_stream_count(count: int, output: str) -> None:
    """Reject attaching more audio tracks than the container can hold."""
    cap = max_audio_streams(output)
    if cap is not None and count > cap:
        raise InvalidSpecError(
            f"{_ext(output)} holds at most {cap} audio track(s); you attached {count}. "
            "Use .mkv/.mp4/.mov."
        )


def validate_channels(channels: int, output: str) -> None:
    """Reject a channel count above what the container's audio codec allows."""
    cap = max_channels(output)
    if cap is not None and channels > cap:
        raise InvalidSpecError(
            f"{_ext(output)} audio holds at most {cap} channels; you asked for {channels}."
        )
