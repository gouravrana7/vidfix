"""Unit tests for the attach/mux argument builder (no FFmpeg)."""

from __future__ import annotations

import pytest

from vidfix.core.attach import build_attach_args, subtitle_codec
from vidfix.exceptions import InvalidSpecError


class TestBuildAttachArgs:
    def test_audio_only(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audio="a.m4a")
        assert args[:2] == ["-i", "v.mp4"]
        assert "a.m4a" in args
        assert "0:v:0" in args and "1:a:0" in args
        assert args[args.index("-c:v") + 1] == "copy"
        assert "-shortest" in args
        assert args[-1] == "out.mp4"

    def test_soft_subs_mp4(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", subs="s.srt")
        assert "s.srt" in args
        assert args[args.index("-c:s") + 1] == "mov_text"
        assert args[args.index("-c:v") + 1] == "copy"

    def test_soft_subs_mkv(self) -> None:
        args = build_attach_args("v.mp4", "out.mkv", subs="s.srt")
        assert args[args.index("-c:s") + 1] == "srt"

    def test_burn_reencodes_video(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", subs="s.srt", burn=True)
        assert any("subtitles=" in a for a in args)
        assert "libx264" in args  # re-encoded, not copied
        assert "-c:s" not in args  # subs go through the filter, not a stream

    def test_audio_and_soft_subs(self) -> None:
        args = build_attach_args("v.mp4", "out.mkv", audio="a.m4a", subs="s.srt")
        assert "1:a:0" in args and "2:s:0" in args

    def test_audio_and_burn_subs(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audio="a.m4a", subs="s.srt", burn=True)
        assert "1:a:0" in args
        assert any("subtitles=" in a for a in args)
        assert "-shortest" in args

    def test_nothing_to_attach(self) -> None:
        with pytest.raises(InvalidSpecError, match="Nothing to attach"):
            build_attach_args("v.mp4", "out.mp4")

    def test_soft_subs_unsupported_container(self) -> None:
        with pytest.raises(InvalidSpecError, match="soft subtitle"):
            build_attach_args("v.mp4", "out.avi", subs="s.srt")

    def test_burn_into_any_container(self) -> None:
        args = build_attach_args("v.mp4", "out.avi", subs="s.srt", burn=True)
        assert any("subtitles=" in a for a in args)  # burn bypasses the soft-sub limit


class TestSubtitleCodec:
    @pytest.mark.parametrize(
        ("output", "codec"),
        [
            ("o.mp4", "mov_text"),
            ("o.mov", "mov_text"),
            ("o.m4v", "mov_text"),
            ("o.mkv", "srt"),
            ("o.webm", "webvtt"),
            ("o.avi", "copy"),
        ],
    )
    def test_map(self, output: str, codec: str) -> None:
        assert subtitle_codec(output) == codec
