"""Unit tests for generate command builders (no FFmpeg execution)."""

from __future__ import annotations

from fractions import Fraction

import pytest

from vidfix.core.duration import Resolution
from vidfix.core.generate import build_generate_args, timecode_filter, video_source
from vidfix.exceptions import InvalidSpecError

FPS30 = Fraction(30)
DF30 = Fraction(30000, 1001)
RES = Resolution(1280, 720)


class TestVideoSource:
    def test_smpte(self) -> None:
        src = video_source("smpte", FPS30, 5.0, RES)
        assert src == "smptebars=size=1280x720:rate=30:duration=5.0"

    def test_drop_frame_rate_is_rational(self) -> None:
        src = video_source("testsrc", DF30, 1.0, RES)
        assert "rate=30000/1001" in src
        assert src.startswith("testsrc2=")

    def test_solid_color(self) -> None:
        src = video_source("solid:red", FPS30, 2.0, RES)
        assert src.startswith("color=color=red:")

    def test_solid_hex(self) -> None:
        assert "color=color=#ff0000" in video_source("solid:#ff0000", FPS30, 2.0, RES)

    @pytest.mark.parametrize("pattern", ["nope", "solid:", "solid:re;d"])
    def test_invalid(self, pattern: str) -> None:
        with pytest.raises(InvalidSpecError):
            video_source(pattern, FPS30, 1.0, RES)


class TestTimecodeFilter:
    def test_with_font(self) -> None:
        f = timecode_filter(FPS30, "/fonts/mono.ttf")
        assert "fontfile='/fonts/mono.ttf':" in f
        # drawtext skips %{...} expansion when timecode= is set, so no text option
        assert "%{" not in f

    def test_without_font(self) -> None:
        assert "fontfile" not in timecode_filter(FPS30, None)

    def test_windows_path_escaped(self) -> None:
        f = timecode_filter(FPS30, "C:\\Windows\\Fonts\\consola.ttf")
        assert "fontfile='C\\:/Windows/Fonts/consola.ttf':" in f

    def test_drop_frame_uses_semicolon(self) -> None:
        f = timecode_filter(DF30, None, drop_frame=True)
        assert "timecode='00\\:00\\:00\\;00'" in f
        assert "rate=30000/1001" in f

    def test_non_drop_uses_colon(self) -> None:
        f = timecode_filter(DF30, None, drop_frame=False)
        assert "timecode='00\\:00\\:00\\:00'" in f

    @pytest.mark.parametrize(
        ("fps", "sep"),
        [
            (Fraction(30000, 1001), "\\;"),  # NTSC 29.97 defaults to drop-frame
            (Fraction(60000, 1001), "\\;"),  # NTSC 59.94 defaults to drop-frame
            (Fraction(25), "\\:"),  # PAL
            (Fraction(30), "\\:"),  # exact integer rates are never drop-frame
            (Fraction(24000, 1001), "\\:"),  # 23.976 has no drop-frame timecode
        ],
    )
    def test_auto_detect(self, fps: Fraction, sep: str) -> None:
        assert f"timecode='00\\:00\\:00{sep}00'" in timecode_filter(fps, None)

    def test_drop_frame_invalid_for_pal(self) -> None:
        with pytest.raises(InvalidSpecError, match=r"[Dd]rop-frame"):
            timecode_filter(Fraction(25), None, drop_frame=True)


class TestBuildGenerateArgs:
    def test_defaults(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES)
        assert args[:3] == ["-f", "lavfi", "-i"]
        assert "sine=frequency=440:sample_rate=44100:duration=5.0" in args
        assert "libx264" in args
        assert args[-1] == "out.mp4"
        assert args[args.index("-t") + 1] == "5.0"

    def test_no_audio(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES, audio="none")
        assert "-an" in args
        assert not any("sine=" in a for a in args)

    def test_silence(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES, audio="silence")
        assert any("anullsrc" in a for a in args)

    def test_webm_uses_opus(self) -> None:
        args = build_generate_args("out.webm", FPS30, 5.0, RES, codec="vp9")
        assert "libopus" in args
        assert "libvpx-vp9" in args

    def test_timecode_adds_drawtext(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES, timecode=True)
        assert any("drawtext" in a for a in args)

    def test_layout_channel_count(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES, layout="5.1")
        assert args[args.index("-ac") + 1] == "6"

    def test_layout_pan_left(self) -> None:
        args = build_generate_args("out.mp4", FPS30, 5.0, RES, layout="left")
        assert args[args.index("-af") + 1] == "pan=stereo|FL=c0"

    def test_bad_layout(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("out.mp4", FPS30, 5.0, RES, layout="quad")

    def test_audio_only_output(self) -> None:
        args = build_generate_args("tone.wav", FPS30, 5.0, RES, layout="right")
        joined = " ".join(args)
        assert "smptebars" not in joined and "-vf" not in args
        assert "sine=frequency=440" in joined
        assert args[args.index("-af") + 1] == "pan=stereo|FR=c0"

    def test_audio_only_rejects_audio_none(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("tone.wav", FPS30, 5.0, RES, audio="none")

    def test_audio_only_rejects_timecode(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("tone.wav", FPS30, 5.0, RES, timecode=True)

    def test_image_output(self) -> None:
        args = build_generate_args("card.jpg", FPS30, 5.0, RES)
        assert args[args.index("-frames:v") + 1] == "1"
        assert args[args.index("-q:v") + 1] == "2"
        assert "-an" in args and "-c:v" not in args and "-t" not in args
        assert "sine=" not in " ".join(args)

    def test_image_rejects_timecode(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("card.png", FPS30, 5.0, RES, timecode=True)

    def test_bad_audio_mode(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("out.mp4", FPS30, 5.0, RES, audio="loud")

    def test_bad_codec(self) -> None:
        with pytest.raises(InvalidSpecError):
            build_generate_args("out.mp4", FPS30, 5.0, RES, codec="divx")
