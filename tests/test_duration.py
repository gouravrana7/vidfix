"""Unit tests for the pure spec parsers (no FFmpeg required)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from vidfix.core.duration import (
    Resolution,
    format_seconds,
    fps_to_ffmpeg,
    parse_duration,
    parse_fps,
    parse_resolution,
)
from vidfix.exceptions import InvalidSpecError


class TestParseDuration:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("90", 90.0),
            ("2.5", 2.5),
            ("30s", 30.0),
            ("30 s", 30.0),
            ("5m", 300.0),
            ("1:30", 90.0),
            ("01:30", 90.0),
            ("1:02:03", 3723.0),
            ("1:02:03.5", 3723.5),
            ("0:05", 5.0),
            (90, 90.0),
            (2.5, 2.5),
        ],
    )
    def test_valid(self, spec: str | int | float, expected: float) -> None:
        assert parse_duration(spec) == pytest.approx(expected)

    @pytest.mark.parametrize("spec", ["", "abc", "-5", "0", "1:99:00", "30x", ":30"])
    def test_invalid(self, spec: str) -> None:
        with pytest.raises(InvalidSpecError):
            parse_duration(spec)


class TestParseFps:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("60", Fraction(60)),
            ("24", Fraction(24)),
            ("29.97", Fraction(30000, 1001)),
            ("59.94", Fraction(60000, 1001)),
            ("23.976", Fraction(24000, 1001)),
            ("119.88", Fraction(120000, 1001)),
            ("30000/1001", Fraction(30000, 1001)),
            ("25/1", Fraction(25)),
            ("12.5", Fraction(25, 2)),
            (30, Fraction(30)),
            (29.97, Fraction(30000, 1001)),
            (Fraction(24000, 1001), Fraction(24000, 1001)),
        ],
    )
    def test_valid(self, spec: object, expected: Fraction) -> None:
        result = parse_fps(spec)  # type: ignore[arg-type]
        assert result == expected
        assert isinstance(result, Fraction)

    @pytest.mark.parametrize("spec", ["", "fast", "-30", "0", "30/0", "1001"])
    def test_invalid(self, spec: str) -> None:
        with pytest.raises(InvalidSpecError):
            parse_fps(spec)

    def test_drop_frame_stays_exact(self) -> None:
        # 29.97 must become the exact NTSC rational, not Fraction(2997, 100).
        assert parse_fps("29.97") == Fraction(30000, 1001)
        assert float(parse_fps("29.97")) != 29.97


class TestFpsToFFmpeg:
    def test_integer_rate(self) -> None:
        assert fps_to_ffmpeg(Fraction(60)) == "60"

    def test_rational_rate(self) -> None:
        assert fps_to_ffmpeg(Fraction(30000, 1001)) == "30000/1001"


class TestParseResolution:
    @pytest.mark.parametrize(
        ("spec", "expected"),
        [
            ("1280x720", Resolution(1280, 720)),
            ("1280X720", Resolution(1280, 720)),
            ("720p", Resolution(1280, 720)),
            ("1080P", Resolution(1920, 1080)),
            ("4k", Resolution(3840, 2160)),
            ("4K", Resolution(3840, 2160)),
            ("160x120", Resolution(160, 120)),
        ],
    )
    def test_valid(self, spec: str, expected: Resolution) -> None:
        assert parse_resolution(spec) == expected

    @pytest.mark.parametrize("spec", ["", "way too big", "0x0", "-1x720", "1281x720", "5p"])
    def test_invalid(self, spec: str) -> None:
        with pytest.raises(InvalidSpecError):
            parse_resolution(spec)

    def test_str(self) -> None:
        assert str(Resolution(1280, 720)) == "1280x720"


class TestFormatSeconds:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (0.0, "0:00:00.000"),
            (90.0, "0:01:30.000"),
            (3723.5, "1:02:03.500"),
            (59.9999, "0:01:00.000"),
        ],
    )
    def test_format(self, seconds: float, expected: str) -> None:
        assert format_seconds(seconds) == expected
