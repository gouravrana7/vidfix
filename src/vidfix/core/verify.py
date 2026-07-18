"""Assert that a media file matches expected specs (CI-friendly)."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel

from vidfix.core.duration import Resolution
from vidfix.core.ffmpeg import CODEC_PROBE_NAMES, FFmpegRunner
from vidfix.core.probe import MediaInfo, probe

DEFAULT_FPS_TOLERANCE = 0.01
DEFAULT_DURATION_TOLERANCE = 0.1


class PropertyCheck(BaseModel):
    """One verified property: expected vs actual."""

    name: str
    expected: str
    actual: str
    passed: bool


class VerifyResult(BaseModel):
    """Outcome of verifying a file against expected specs."""

    path: str
    passed: bool
    checks: list[PropertyCheck]


def check_specs(
    info: MediaInfo,
    fps: Fraction | None = None,
    duration: float | None = None,
    res: Resolution | None = None,
    codec: str | None = None,
    fps_tolerance: float = DEFAULT_FPS_TOLERANCE,
    duration_tolerance: float = DEFAULT_DURATION_TOLERANCE,
) -> VerifyResult:
    """Pure comparison of probed metadata against expected specs."""
    checks: list[PropertyCheck] = []

    if fps is not None:
        delta = abs(info.fps_float - float(fps))
        checks.append(
            PropertyCheck(
                name="fps",
                expected=f"{float(fps):.3f} (±{fps_tolerance})",
                actual=f"{info.fps_float:.3f} ({info.fps})",
                passed=delta <= fps_tolerance,
            )
        )
    if duration is not None:
        delta = abs(info.duration - duration)
        checks.append(
            PropertyCheck(
                name="duration",
                expected=f"{duration:.3f}s (±{duration_tolerance}s)",
                actual=f"{info.duration:.3f}s",
                passed=delta <= duration_tolerance,
            )
        )
    if res is not None:
        checks.append(
            PropertyCheck(
                name="resolution",
                expected=str(res),
                actual=info.resolution,
                passed=(info.width, info.height) == (res.width, res.height),
            )
        )
    if codec is not None:
        expected_name = CODEC_PROBE_NAMES.get(codec, codec)
        checks.append(
            PropertyCheck(
                name="codec",
                expected=expected_name,
                actual=info.video_codec,
                passed=info.video_codec == expected_name,
            )
        )

    return VerifyResult(path=info.path, passed=all(c.passed for c in checks), checks=checks)


def verify(
    input_path: str | Path,
    fps: Fraction | None = None,
    duration: float | None = None,
    res: Resolution | None = None,
    codec: str | None = None,
    fps_tolerance: float = DEFAULT_FPS_TOLERANCE,
    duration_tolerance: float = DEFAULT_DURATION_TOLERANCE,
    runner: FFmpegRunner | None = None,
) -> VerifyResult:
    """Probe a file and check it against the given specs."""
    info = probe(input_path, runner=runner)
    return check_specs(
        info,
        fps=fps,
        duration=duration,
        res=res,
        codec=codec,
        fps_tolerance=fps_tolerance,
        duration_tolerance=duration_tolerance,
    )
