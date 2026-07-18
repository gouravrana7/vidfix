"""Custom exception hierarchy for vidfix."""

from __future__ import annotations


class VidfixError(Exception):
    """Base class for all vidfix errors."""


class InvalidSpecError(VidfixError, ValueError):
    """Raised when a user-supplied spec (fps, duration, resolution, ...) cannot be parsed."""


class FFmpegNotFoundError(VidfixError):
    """Raised when no usable FFmpeg binary can be located."""


class ProbeError(VidfixError):
    """Raised when media metadata cannot be extracted from a file."""


class ConversionError(VidfixError):
    """Raised when an FFmpeg invocation fails.

    The message includes the tail of FFmpeg's stderr so CI logs show the
    actual encoder error without needing verbose mode.
    """

    def __init__(self, message: str, stderr: str = "", returncode: int | None = None) -> None:
        self.stderr = stderr
        self.returncode = returncode
        tail = stderr_tail(stderr)
        full = message if not tail else f"{message}\n--- ffmpeg stderr (tail) ---\n{tail}"
        super().__init__(full)


class PresetError(VidfixError):
    """Raised when a preset is missing or malformed."""


def stderr_tail(stderr: str, max_lines: int = 15) -> str:
    """Return the last ``max_lines`` non-empty lines of an stderr capture."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])
