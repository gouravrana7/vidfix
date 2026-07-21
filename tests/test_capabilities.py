"""Unit tests for per-container capability validation (no FFmpeg)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from vidfix.core.capabilities import (
    allowed_codecs,
    allowed_fps,
    max_audio_streams,
    max_channels,
    validate_audio_stream_count,
    validate_channels,
    validate_codec,
    validate_fps,
)
from vidfix.exceptions import InvalidSpecError


class TestValidateCodec:
    @pytest.mark.parametrize(
        ("codec", "output"),
        [
            ("h264", "out.webm"),
            ("prores", "out.mp4"),
            ("h265", "out.wmv"),
            ("vp9", "out.mov"),
            ("theora", "out.3gp"),
        ],
    )
    def test_rejects_incompatible(self, codec: str, output: str) -> None:
        with pytest.raises(InvalidSpecError, match="can't hold"):
            validate_codec(codec, output)

    @pytest.mark.parametrize(
        ("codec", "output"),
        [("vp9", "out.webm"), ("theora", "out.ogv"), ("prores", "out.mov"), ("h264", "out.mp4")],
    )
    def test_allows_compatible(self, codec: str, output: str) -> None:
        validate_codec(codec, output)

    def test_unknown_container_unrestricted(self) -> None:
        validate_codec("h264", "out.exotic")
        assert allowed_codecs("out.exotic") is None


class TestValidateFps:
    @pytest.mark.parametrize("fps", [Fraction(15), Fraction(12), Fraction(20)])
    def test_mxf_rejects_non_broadcast(self, fps: Fraction) -> None:
        with pytest.raises(InvalidSpecError, match="broadcast frame rate"):
            validate_fps(fps, "out.mxf")

    @pytest.mark.parametrize("fps", [Fraction(30), Fraction(25), Fraction(30000, 1001)])
    def test_mxf_allows_broadcast(self, fps: Fraction) -> None:
        validate_fps(fps, "out.mxf")

    def test_other_containers_allow_any_rate(self) -> None:
        validate_fps(Fraction(15), "out.mp4")
        assert allowed_fps("out.mp4") is None


class TestValidateChannels:
    @pytest.mark.parametrize(("output", "channels"), [("out.mp3", 6), ("out.mpg", 8)])
    def test_rejects_over_cap(self, output: str, channels: int) -> None:
        with pytest.raises(InvalidSpecError, match="at most"):
            validate_channels(channels, output)

    @pytest.mark.parametrize(
        ("output", "channels"), [("out.mp3", 2), ("out.mpg", 6), ("out.mp4", 8)]
    )
    def test_allows_within_cap(self, output: str, channels: int) -> None:
        validate_channels(channels, output)

    def test_caps(self) -> None:
        assert max_channels("out.mp3") == 2
        assert max_channels("out.mpg") == 6
        assert max_channels("out.mp4") is None


class TestValidateAudioStreamCount:
    def test_flv_rejects_second_track(self) -> None:
        with pytest.raises(InvalidSpecError, match="audio track"):
            validate_audio_stream_count(2, "out.flv")

    @pytest.mark.parametrize("output", ["out.mp4", "out.mkv", "out.mov", "out.mxf"])
    def test_multi_track_containers_allow_two(self, output: str) -> None:
        validate_audio_stream_count(2, output)

    def test_flv_allows_one(self) -> None:
        validate_audio_stream_count(1, "out.flv")

    def test_caps(self) -> None:
        assert max_audio_streams("out.flv") == 1
        assert max_audio_streams("out.mp4") is None
