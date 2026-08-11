"""Unit tests for the attach/mux argument builder (no FFmpeg)."""

from __future__ import annotations

import pytest

from vidfix.core.attach import annexb_args, build_attach_args, subtitle_codec
from vidfix.exceptions import InvalidSpecError


class TestBuildAttachArgs:
    def test_audio_only(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audios=["a.m4a"])
        assert args[:2] == ["-i", "v.mp4"]
        assert "a.m4a" in args
        assert "0:v:0" in args and "1:a:0" in args
        assert args[args.index("-c:v") + 1] == "copy"
        assert "-shortest" in args
        assert args[-1] == "out.mp4"

    def test_two_audios_map_in_order(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audios=["en.wav", "hi.mp3"])
        assert args.index("en.wav") < args.index("hi.mp3")
        assert "1:a:0" in args and "2:a:0" in args
        assert args.index("1:a:0") < args.index("2:a:0")

    def test_three_audios(self) -> None:
        args = build_attach_args("v.mkv", "out.mkv", audios=["a.wav", "b.wav", "c.wav"])
        assert "1:a:0" in args and "2:a:0" in args and "3:a:0" in args

    def test_two_audios_then_subs_index(self) -> None:
        args = build_attach_args("v.mp4", "out.mkv", audios=["a.wav", "b.wav"], subs="s.srt")
        assert "1:a:0" in args and "2:a:0" in args
        assert "3:s:0" in args  # subs is the input after the two audios

    def test_empty_audio_list_is_nothing(self) -> None:
        with pytest.raises(InvalidSpecError, match="Nothing to attach"):
            build_attach_args("v.mp4", "out.mp4", audios=[])

    def test_two_audios_into_single_track_container(self) -> None:
        with pytest.raises(InvalidSpecError, match="audio track"):
            build_attach_args("v.mp4", "out.flv", audios=["a.wav", "b.wav"])

    def test_gif_output_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="GIF"):
            build_attach_args("v.mp4", "out.gif", audios=["a.wav"])

    def test_no_extension_output_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="no extension"):
            build_attach_args("v.mp4", "mxf", audios=["a.wav"])

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
        args = build_attach_args("v.mp4", "out.mkv", audios=["a.m4a"], subs="s.srt")
        assert "1:a:0" in args and "2:s:0" in args

    def test_audio_and_burn_subs(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audios=["a.m4a"], subs="s.srt", burn=True)
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
        assert any("subtitles=" in a for a in args)


class TestAnnexbArgs:
    @pytest.mark.parametrize("output", ["out.mpg", "out.mpeg"])
    def test_h264_copy_into_program_stream(self, output: str) -> None:
        assert annexb_args(output, "h264") == ["-bsf:v", "h264_mp4toannexb"]

    def test_h265_copy_into_program_stream(self) -> None:
        assert annexb_args("out.mpg", "h265") == ["-bsf:v", "hevc_mp4toannexb"]

    @pytest.mark.parametrize("codec", ["mpeg2", None])
    def test_other_codecs_need_nothing(self, codec: str | None) -> None:
        assert annexb_args("out.mpg", codec) == []

    @pytest.mark.parametrize("output", ["out.mp4", "out.mkv", "out.ts"])
    def test_other_containers_need_nothing(self, output: str) -> None:
        assert annexb_args(output, "h264") == []

    def test_builder_adds_filter_for_mpg(self) -> None:
        args = build_attach_args("v.mp4", "out.mpg", audios=["a.wav"], video_codec="h264")
        assert args[args.index("-c:v") + 1] == "copy"
        assert args[args.index("-bsf:v") + 1] == "h264_mp4toannexb"

    def test_builder_skips_filter_when_burning(self) -> None:
        args = build_attach_args("v.mp4", "out.mpg", subs="s.srt", burn=True, video_codec="h264")
        assert "-bsf:v" not in args


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
