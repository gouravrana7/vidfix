"""The public Python API (`import vidfix`) the way a script would use it.

Every exported function is called with the input types people naturally pass
(str paths, Path objects, Fraction / float / int frame rates, numeric or text
durations), checked for what it returns, and fed bad input to make sure the
failure is always a VidfixError with a readable message — never a raw
TypeError / AttributeError / FFmpeg dump.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

import vidfix
from vidfix import VidfixError

pytestmark = pytest.mark.integration


def _needs_drawtext() -> None:
    from vidfix.core.generate import drawtext_available

    if not drawtext_available():
        pytest.skip("this FFmpeg build has no drawtext filter")


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("api")
    clips = {
        "video": d / "v.mp4",
        "silent": d / "s.mp4",
        "wav": d / "a.wav",
        "png": d / "p.png",
        "srt": d / "t.srt",
    }
    vidfix.generate(clips["video"], fps="30", duration="2s", res="320x240")
    vidfix.generate(clips["silent"], duration=1, res="160x120", audio="none")
    vidfix.generate(clips["wav"], duration=1)
    vidfix.generate(clips["png"], res="320x240")
    clips["srt"].write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    return clips


class TestExports:
    def test_everything_in_all_is_importable(self) -> None:
        for name in vidfix.__all__:
            assert getattr(vidfix, name) is not None

    def test_version_matches_the_installed_package(self) -> None:
        from importlib.metadata import version

        assert vidfix.__version__ == version("vidfix")

    @pytest.mark.parametrize(
        "error",
        ["ConversionError", "FFmpegNotFoundError", "InvalidSpecError", "PresetError", "ProbeError"],
    )
    def test_every_error_is_a_vidfix_error(self, error: str) -> None:
        assert issubclass(getattr(vidfix, error), VidfixError)


class TestGenerate:
    @pytest.mark.parametrize(
        ("fps", "exact"),
        [("30", "30"), (25, "25"), (29.97, "30000/1001"), (Fraction(60000, 1001), "60000/1001")],
    )
    def test_fps_forms(self, tmp_path: Path, fps: object, exact: str) -> None:
        out = vidfix.generate(tmp_path / "o.mp4", fps=fps, duration=1, res="160x120")  # type: ignore[arg-type]
        assert vidfix.probe(out).fps == exact

    @pytest.mark.parametrize("duration", [2, 2.0, "2s", "0:02", "2 seconds"])
    def test_duration_forms(self, tmp_path: Path, duration: object) -> None:
        out = vidfix.generate(tmp_path / "o.mp4", duration=duration, res="160x120")  # type: ignore[arg-type]
        assert abs(vidfix.probe(out).duration - 2.0) < 0.1

    @pytest.mark.parametrize("res", ["320x240", "240p"])
    def test_res_forms(self, tmp_path: Path, res: str) -> None:
        info = vidfix.probe(vidfix.generate(tmp_path / "o.mp4", duration=1, res=res))
        assert info.height == 240

    def test_str_and_path_outputs_return_a_path(self, tmp_path: Path) -> None:
        a = vidfix.generate(str(tmp_path / "a.mp4"), duration=1, res="160x120")
        b = vidfix.generate(tmp_path / "b.mp4", duration=1, res="160x120")
        assert isinstance(a, Path) and isinstance(b, Path) and a.is_file() and b.is_file()

    def test_audio_only_and_picture_by_extension(self, tmp_path: Path) -> None:
        wav = vidfix.probe(vidfix.generate(tmp_path / "a.wav", duration=1, layout="5.1"))
        png = vidfix.probe(vidfix.generate(tmp_path / "p.png", res="320x240"))
        assert wav.video_codec == "none" and wav.audio is not None and wav.audio.channels == 6
        assert (png.width, png.height) == (320, 240)

    def test_progress_callback_is_called(self, tmp_path: Path) -> None:
        events: list[object] = []
        vidfix.generate(tmp_path / "o.mp4", duration=1, res="160x120", on_progress=events.append)
        assert events

    def test_caption_and_timecode(self, tmp_path: Path) -> None:
        _needs_drawtext()
        out = vidfix.generate(
            tmp_path / "o.mp4",
            fps="29.97",
            duration=1,
            res="160x120",
            text="hi: it's 100%",
            position="top-left",
            start=0.1,
            end=0.8,
            timecode=True,
            drop_frame=True,
        )
        assert out.is_file()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"fps": -1},
            {"fps": "fast"},
            {"duration": -2},
            {"duration": "soon"},
            {"res": "abc"},
            {"res": "321x241"},
            {"codec": "bogus"},
            {"audio": "loud"},
            {"layout": "9.1"},
            {"pattern": "nope"},
        ],
    )
    def test_bad_input_is_a_vidfix_error(self, tmp_path: Path, kwargs: dict[str, object]) -> None:
        with pytest.raises(VidfixError):
            vidfix.generate(tmp_path / "o.mp4", **{"duration": 1, **kwargs})  # type: ignore[arg-type]


class TestConvert:
    def test_returns_a_plan(self, media: dict[str, Path], tmp_path: Path) -> None:
        plan = vidfix.convert(str(media["video"]), str(tmp_path / "o.mp4"), fps="25")
        assert isinstance(plan, vidfix.ConvertPlan) and plan.stream_copy is False

    @pytest.mark.parametrize(
        ("fps", "exact"), [(Fraction(24), "24"), (50, "50"), ("29.97", "30000/1001")]
    )
    def test_fps_forms(
        self, media: dict[str, Path], tmp_path: Path, fps: object, exact: str
    ) -> None:
        vidfix.convert(media["video"], tmp_path / "o.mp4", fps=fps)  # type: ignore[arg-type]
        assert vidfix.probe(tmp_path / "o.mp4").fps == exact

    def test_float_duration(self, media: dict[str, Path], tmp_path: Path) -> None:
        vidfix.convert(media["video"], tmp_path / "o.mp4", duration=1.25, precise=True)
        assert abs(vidfix.probe(tmp_path / "o.mp4").duration - 1.25) < 0.1

    def test_same_container_trim_is_a_stream_copy(
        self, media: dict[str, Path], tmp_path: Path
    ) -> None:
        plan = vidfix.convert(media["video"], tmp_path / "o.mp4", duration=1)
        assert plan.stream_copy is True and plan.warnings

    @pytest.mark.parametrize(
        ("kwargs", "check"),
        [
            ({"audio": "none"}, lambda i: i.audio is None),
            ({"no_audio": True}, lambda i: i.audio is None),
            ({"audio": "silence"}, lambda i: i.audio is not None),
            ({"layout": "stereo"}, lambda i: i.audio.channels == 2),
            ({"res": "480x480", "stretch": True}, lambda i: (i.width, i.height) == (480, 480)),
            ({"duration": 4, "extend_mode": "loop"}, lambda i: abs(i.duration - 4) < 0.15),
        ],
    )
    def test_options(
        self, media: dict[str, Path], tmp_path: Path, kwargs: dict[str, object], check: object
    ) -> None:
        vidfix.convert(media["video"], tmp_path / "o.mkv", **kwargs)  # type: ignore[arg-type]
        assert check(vidfix.probe(tmp_path / "o.mkv"))  # type: ignore[operator]

    def test_caption_and_timecode(self, media: dict[str, Path], tmp_path: Path) -> None:
        _needs_drawtext()
        vidfix.convert(media["video"], tmp_path / "o.mp4", text="x", timecode=True)
        assert (tmp_path / "o.mp4").is_file()

    @pytest.mark.parametrize(
        ("src", "kwargs"),
        [
            ("ghost", {}),
            ("video", {"audio": "loud"}),
            ("video", {"duration": 5, "extend_mode": "bounce"}),
            ("video", {"layout": "5.1", "audio": "none"}),
            ("silent", {"layout": "5.1"}),
            ("wav", {}),
        ],
    )
    def test_bad_input_is_a_vidfix_error(
        self, media: dict[str, Path], tmp_path: Path, src: str, kwargs: dict[str, object]
    ) -> None:
        source = media.get(src, tmp_path / "ghost.mp4")
        with pytest.raises(VidfixError):
            vidfix.convert(source, tmp_path / "o.mp4", **kwargs)  # type: ignore[arg-type]

    def test_refuses_to_overwrite_its_input(self, media: dict[str, Path]) -> None:
        with pytest.raises(VidfixError, match="input files"):
            vidfix.convert(media["video"], media["video"], fps="25")


class TestCaption:
    @pytest.mark.parametrize("output", ["o.mp4", "o.webm", "o.mkv"])
    def test_str_and_path(self, media: dict[str, Path], tmp_path: Path, output: str) -> None:
        _needs_drawtext()
        out = vidfix.caption(str(media["video"]), tmp_path / output, "line1\nline2 : ' \\ %")
        assert isinstance(out, Path) and vidfix.probe(out).video_codec != "none"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"text": ""},
            {"text": "x", "size": "huge"},
            {"text": "x", "start": 1.5, "end": 0.5},
            {"text": "x", "start": -1},
            {"text": "x", "position": "middle"},
        ],
    )
    def test_bad_input_is_a_vidfix_error(
        self, media: dict[str, Path], tmp_path: Path, kwargs: dict[str, object]
    ) -> None:
        with pytest.raises(VidfixError):
            vidfix.caption(media["video"], tmp_path / "o.mp4", **kwargs)  # type: ignore[arg-type]

    def test_unknown_color(self, media: dict[str, Path], tmp_path: Path) -> None:
        _needs_drawtext()
        with pytest.raises(VidfixError, match="Unknown color"):
            vidfix.caption(media["video"], tmp_path / "o.mp4", "x", color="nocolor")

    def test_audio_file_has_nothing_to_caption(
        self, media: dict[str, Path], tmp_path: Path
    ) -> None:
        with pytest.raises(VidfixError, match="no video"):
            vidfix.caption(media["wav"], tmp_path / "o.mp4", "x")


class TestToFormat:
    @pytest.mark.parametrize(
        ("src", "out", "kind"),
        [
            ("video", "o.gif", "video"),
            ("video", "o.wav", "audio"),
            ("video", "o.ogg", "audio"),
            ("video", "o.jpg", "image"),
            ("png", "o.webp", "image"),
            ("wav", "o.flac", "audio"),
            ("wav", "o.opus", "audio"),
        ],
    )
    def test_conversions(
        self, media: dict[str, Path], tmp_path: Path, src: str, out: str, kind: str
    ) -> None:
        result = vidfix.to_format(media[src], tmp_path / out)
        info = vidfix.probe(result)
        assert (info.audio is not None) if kind == "audio" else info.width > 0

    @pytest.mark.parametrize(
        ("src", "out"),
        [
            ("wav", "o.png"),
            ("png", "o.wav"),
            ("png", "o.mp4"),
            ("silent", "o.wav"),
            ("video", "o.xyz"),
        ],
    )
    def test_impossible_conversions(
        self, media: dict[str, Path], tmp_path: Path, src: str, out: str
    ) -> None:
        with pytest.raises(VidfixError):
            vidfix.to_format(media[src], tmp_path / out)

    def test_missing_input(self, tmp_path: Path) -> None:
        with pytest.raises(VidfixError, match="File not found"):
            vidfix.to_format(tmp_path / "ghost.mp4", tmp_path / "o.png")


class TestAttach:
    @pytest.mark.parametrize(
        "audio",
        [
            lambda m: str(m["wav"]),
            lambda m: m["wav"],
            lambda m: [m["wav"], str(m["wav"])],
            lambda m: (m["wav"],),
        ],
    )
    def test_audio_forms(self, media: dict[str, Path], tmp_path: Path, audio: object) -> None:
        tracks = audio(media)  # type: ignore[operator]
        out = vidfix.attach(media["video"], tmp_path / "o.mkv", audio=tracks)
        count = len(tracks) if isinstance(tracks, (list, tuple)) else 1
        assert vidfix.probe(out).audio_track_count == count

    def test_soft_subtitles(self, media: dict[str, Path], tmp_path: Path) -> None:
        out = vidfix.attach(media["video"], tmp_path / "o.mp4", subs=media["srt"])
        assert out.is_file()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"audio": []},
            {},
            {"subs": "WAV"},
            {"audio": "PNG"},
            {"audio": "SILENT"},
            {"audio": "ghost.wav"},
        ],
    )
    def test_bad_input_is_a_vidfix_error(
        self, media: dict[str, Path], tmp_path: Path, kwargs: dict[str, object]
    ) -> None:
        resolved = {
            k: media[v.lower()] if isinstance(v, str) and v.isupper() else v
            for k, v in kwargs.items()
        }
        with pytest.raises(VidfixError):
            vidfix.attach(media["video"], tmp_path / "o.mp4", **resolved)  # type: ignore[arg-type]

    def test_audio_file_is_not_a_base_video(self, media: dict[str, Path], tmp_path: Path) -> None:
        with pytest.raises(VidfixError, match="no video"):
            vidfix.attach(media["wav"], tmp_path / "o.mp4", audio=media["wav"])


class TestProbeAndVerify:
    @pytest.mark.parametrize("as_path", [True, False])
    def test_probe_str_or_path(self, media: dict[str, Path], as_path: bool) -> None:
        info = vidfix.probe(media["video"] if as_path else str(media["video"]))
        assert isinstance(info, vidfix.MediaInfo)
        assert (info.width, info.height, info.fps) == (320, 240, "30")

    def test_probe_audio_and_picture(self, media: dict[str, Path]) -> None:
        wav = vidfix.probe(media["wav"])
        assert isinstance(wav.audio, vidfix.AudioInfo) and wav.video_codec == "none"
        assert vidfix.probe(media["png"]).width == 320

    @pytest.mark.parametrize("path", ["ghost.mp4", "."])
    def test_probe_missing(self, path: str) -> None:
        with pytest.raises(VidfixError, match="File not found"):
            vidfix.probe(path)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"fps": Fraction(30)},
            {"fps": "30"},
            {"fps": 30},
            {"fps": 30.0},
            {"duration": "2s"},
            {"duration": 2.0},
            {"duration": 2},
            {"res": "320x240"},
            {"codec": "h264"},
            {"fps": "30", "duration": "2s", "res": "320x240", "codec": "h264"},
        ],
    )
    def test_verify_accepts_every_spec_form(
        self, media: dict[str, Path], kwargs: dict[str, object]
    ) -> None:
        result = vidfix.verify(media["video"], **kwargs)  # type: ignore[arg-type]
        assert isinstance(result, vidfix.VerifyResult) and result.passed
        assert all(isinstance(c, vidfix.PropertyCheck) and c.passed for c in result.checks)

    def test_verify_reports_a_mismatch(self, media: dict[str, Path]) -> None:
        result = vidfix.verify(media["video"], fps=25, res="720p")
        assert not result.passed and [c.passed for c in result.checks] == [False, False]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"fps": "fast"},
            {"duration": "soon"},
            {"res": "big"},
            {"fps": 30, "fps_tolerance": -1},
            {"duration": 2, "duration_tolerance": -0.1},
        ],
    )
    def test_verify_bad_input(self, media: dict[str, Path], kwargs: dict[str, object]) -> None:
        with pytest.raises(VidfixError):
            vidfix.verify(media["video"], **kwargs)  # type: ignore[arg-type]


class TestReadmeExample:
    """The README's Python example, verbatim and across every input-form combination."""

    def test_verbatim(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        from vidfix import generate, probe, verify

        generate("fixture.mp4", fps="59.94", duration="30s", res="720p")
        info = probe("fixture.mp4")
        result = verify("fixture.mp4", duration=30.0)
        assert result.passed
        assert isinstance(info, vidfix.MediaInfo)
        assert (info.width, info.height, info.fps) == (1280, 720, "60000/1001")

    FPS = (
        ("59.94", Fraction(60000, 1001)),
        (59.94, Fraction(60000, 1001)),
        (Fraction(60000, 1001), Fraction(60000, 1001)),
        ("25", Fraction(25)),
        (25, Fraction(25)),
        ("30000/1001", Fraction(30000, 1001)),
    )
    DURATION = (("1.5s", 1.5), (1.5, 1.5), ("0:02", 2.0), (2, 2.0), ("2 seconds", 2.0))
    RES = (("240p", (426, 240)), ("320x240", (320, 240)), ("160x120", (160, 120)))

    @pytest.mark.parametrize(("fps", "fps_exact"), FPS)
    @pytest.mark.parametrize(("duration", "seconds"), DURATION)
    @pytest.mark.parametrize(("res", "size"), RES)
    def test_every_combination(
        self,
        tmp_path: Path,
        fps: object,
        fps_exact: Fraction,
        duration: object,
        seconds: float,
        res: str,
        size: tuple[int, int],
    ) -> None:
        out = vidfix.generate(tmp_path / "fixture.mp4", fps=fps, duration=duration, res=res)  # type: ignore[arg-type]
        info = vidfix.probe(out)
        assert (info.width, info.height) == size
        assert Fraction(info.fps) == fps_exact
        assert abs(info.duration - seconds) < 0.1
        for spec in (fps, str(fps_exact), float(fps_exact), fps_exact):
            assert vidfix.verify(out, fps=spec).passed  # type: ignore[arg-type]
        for spec in (duration, seconds, f"{seconds}s"):
            assert vidfix.verify(out, duration=spec).passed  # type: ignore[arg-type]
        assert vidfix.verify(out, res=res).passed
        assert vidfix.verify(out, res=f"{size[0]}x{size[1]}").passed
        assert vidfix.verify(out, fps=fps, duration=duration, res=res, codec="h264").passed  # type: ignore[arg-type]
        assert not vidfix.verify(out, fps=fps_exact + 1).passed
        assert not vidfix.verify(out, duration=seconds + 1).passed
