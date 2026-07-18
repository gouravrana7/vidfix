"""Unit tests for the convert planner (no FFmpeg execution)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from vidfix.core.convert import build_convert_plan
from vidfix.core.duration import Resolution
from vidfix.core.probe import AudioInfo, MediaInfo
from vidfix.exceptions import InvalidSpecError


def source(duration: float = 10.0, codec: str = "h264", audio: bool = True) -> MediaInfo:
    return MediaInfo(
        path="in.mp4",
        container="mp4",
        duration=duration,
        width=1920,
        height=1080,
        fps="30",
        video_codec=codec,
        audio=AudioInfo(codec="aac") if audio else None,
    )


class TestStreamCopyFastPath:
    def test_trim_same_codec_copies(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), duration=5.0)
        assert p.stream_copy
        assert "-c" in p.args and "copy" in p.args
        assert p.warnings  # keyframe accuracy warning

    def test_precise_forces_reencode(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), duration=5.0, precise=True)
        assert not p.stream_copy
        assert "libx264" in p.args

    def test_different_codec_reencodes(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(codec="hevc"), duration=5.0)
        assert not p.stream_copy

    def test_fps_change_reencodes(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), duration=5.0, fps=Fraction(60))
        assert not p.stream_copy


class TestFilters:
    def test_fps_filter_exact_rational(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), fps=Fraction(30000, 1001))
        vf = p.args[p.args.index("-vf") + 1]
        assert "fps=fps=30000/1001" in vf

    def test_smooth_uses_minterpolate(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), fps=Fraction(60), smooth=True)
        vf = p.args[p.args.index("-vf") + 1]
        assert "minterpolate=fps=60:mi_mode=mci" in vf

    def test_res_pads_by_default(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), res=Resolution(1280, 720))
        vf = p.args[p.args.index("-vf") + 1]
        assert "force_original_aspect_ratio=decrease" in vf
        assert "pad=1280:720" in vf

    def test_stretch_skips_pad(self) -> None:
        p = build_convert_plan(
            "in.mp4", "out.mp4", source(), res=Resolution(1280, 720), stretch=True
        )
        vf = p.args[p.args.index("-vf") + 1]
        assert "pad=" not in vf
        assert "scale=1280:720" in vf


class TestExtend:
    def test_freeze_adds_tpad_and_apad(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(duration=10.0), duration=15.0)
        vf = p.args[p.args.index("-vf") + 1]
        assert "tpad=stop_mode=clone:stop_duration=5.0" in vf
        assert "apad" in p.args[p.args.index("-af") + 1]

    def test_loop_uses_stream_loop(self) -> None:
        p = build_convert_plan(
            "in.mp4", "out.mp4", source(duration=10.0), duration=25.0, extend_mode="loop"
        )
        assert p.args[p.args.index("-stream_loop") + 1] == "-1"
        assert p.args[p.args.index("-t") + 1] == "25.0"

    def test_bad_extend_mode(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_convert_plan("in.mp4", "out.mp4", source(), extend_mode="stretch")


class TestAudio:
    def test_no_audio_flag(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), fps=Fraction(60), no_audio=True)
        assert "-an" in p.args

    def test_audio_tone_maps_sine(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(), audio_tone=True)
        assert any("sine=frequency=440" in a for a in p.args)
        assert "0:v" in p.args and "1:a" in p.args

    def test_source_without_audio_gets_no_audio_args(self) -> None:
        p = build_convert_plan("in.mp4", "out.mp4", source(audio=False), fps=Fraction(60))
        assert "-c:a" not in p.args
        assert "-an" not in p.args

    def test_bad_codec(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_convert_plan("in.mp4", "out.mp4", source(), codec="divx")
