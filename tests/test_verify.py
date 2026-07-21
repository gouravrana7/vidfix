"""Unit tests for verify tolerance logic (no FFmpeg execution)."""

from __future__ import annotations

from fractions import Fraction

from vidfix.core.duration import Resolution
from vidfix.core.probe import MediaInfo
from vidfix.core.verify import check_specs

INFO = MediaInfo(
    path="clip.mp4",
    container="mp4",
    duration=30.03,
    width=1280,
    height=720,
    fps="30000/1001",
    video_codec="h264",
)


class TestFpsTolerance:
    def test_within_default_tolerance(self) -> None:
        result = check_specs(INFO, fps=Fraction(2997, 100))
        assert result.passed

    def test_outside_tolerance(self) -> None:
        result = check_specs(INFO, fps=Fraction(30))
        assert not result.passed

    def test_custom_tolerance(self) -> None:
        result = check_specs(INFO, fps=Fraction(30), fps_tolerance=0.05)
        assert result.passed


class TestDurationTolerance:
    def test_within_default(self) -> None:
        assert check_specs(INFO, duration=30.0).passed

    def test_outside_default(self) -> None:
        assert not check_specs(INFO, duration=29.0).passed

    def test_custom(self) -> None:
        assert check_specs(INFO, duration=29.0, duration_tolerance=2.0).passed


class TestResolutionAndCodec:
    def test_resolution_exact(self) -> None:
        assert check_specs(INFO, res=Resolution(1280, 720)).passed
        assert not check_specs(INFO, res=Resolution(1920, 1080)).passed

    def test_codec_name_mapping(self) -> None:
        assert check_specs(INFO, codec="h264").passed
        hevc = INFO.model_copy(update={"video_codec": "hevc"})
        assert check_specs(hevc, codec="h265").passed
        assert not check_specs(INFO, codec="vp9").passed


class TestCombined:
    def test_one_failure_fails_all(self) -> None:
        result = check_specs(INFO, duration=30.0, res=Resolution(640, 480))
        assert not result.passed
        by_name = {c.name: c.passed for c in result.checks}
        assert by_name == {"duration": True, "resolution": False}

    def test_no_specs_passes_vacuously(self) -> None:
        result = check_specs(INFO)
        assert result.passed
        assert result.checks == []
