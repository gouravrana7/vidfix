"""Unit tests for the attach/mux argument builder (no FFmpeg)."""

from __future__ import annotations

import pytest

from vidfix.core.attach import build_attach_args, subtitle_codec
from vidfix.core.capabilities import can_copy_video
from vidfix.exceptions import InvalidSpecError


class TestBuildAttachArgs:
    def test_audio_only(self) -> None:
        args = build_attach_args("v.mp4", "out.mp4", audios=["a.m4a"], video_codec="h264")
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
        args = build_attach_args("v.mp4", "out.mp4", subs="s.srt", video_codec="h264")
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


class TestCopyDecision:
    @pytest.mark.parametrize(
        ("src", "out"), [("v.mp4", "o.mkv"), ("v.mkv", "o.mp4"), ("v.mov", "o.ts")]
    )
    def test_clean_pairs_copy(self, src: str, out: str) -> None:
        assert can_copy_video(src, out, "h264")

    @pytest.mark.parametrize("out", ["o.mpg", "o.mpeg", "o.avi"])
    def test_start_code_targets_reencode(self, out: str) -> None:
        assert not can_copy_video("v.mp4", out, "h265")

    @pytest.mark.parametrize("src", ["v.avi", "v.wmv", "v.mpg", "v.mpeg"])
    def test_timestampless_sources_reencode(self, src: str) -> None:
        assert not can_copy_video(src, "o.mp4", "h264")

    def test_codec_the_box_cannot_hold_reencodes(self) -> None:
        assert not can_copy_video("v.webm", "o.mov", "vp9")

    def test_unknown_codec_reencodes(self) -> None:
        assert not can_copy_video("v.mp4", "o.mkv", None)

    def test_builder_copies_when_clean(self) -> None:
        args = build_attach_args("v.mp4", "out.mkv", audios=["a.wav"], video_codec="h264")
        assert args[args.index("-c:v") + 1] == "copy"

    def test_builder_reencodes_for_mpg(self) -> None:
        args = build_attach_args("v.mp4", "out.mpg", audios=["a.wav"], video_codec="h264")
        assert args[args.index("-c:v") + 1] == "mpeg2video"

    def test_builder_reencodes_incompatible_codec(self) -> None:
        args = build_attach_args("v.webm", "out.mov", audios=["a.wav"], video_codec="vp9")
        assert args[args.index("-c:v") + 1] == "libx264"

    def test_kept_source_audio_is_encoded_for_the_box(self) -> None:
        args = build_attach_args("v.mp4", "out.webm", subs="s.vtt", burn=True)
        assert args[args.index("-c:a") + 1] == "libopus"

    def test_subs_must_be_a_subtitle_file(self) -> None:
        with pytest.raises(InvalidSpecError, match="isn't a subtitle file"):
            build_attach_args("v.mp4", "out.mkv", subs="a.wav")


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
