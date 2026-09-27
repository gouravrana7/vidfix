"""Friendly-error guards: bad inputs are stopped before FFmpeg runs."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vidfix import attach, caption, convert, generate, to_format, verify
from vidfix.cli import app
from vidfix.core.caption import caption_filter, validate_color
from vidfix.core.ffmpeg import FFmpegRunner, video_codec_args
from vidfix.core.formats import prepare_output
from vidfix.core.matrix import run_matrix
from vidfix.exceptions import InvalidSpecError


class TestCaptionStyle:
    @pytest.mark.parametrize("size", ["huge", "h/12;x", "w*text_foo"])
    def test_bad_size(self, size: str) -> None:
        with pytest.raises(InvalidSpecError, match="caption size"):
            caption_filter("t.txt", size=size)

    @pytest.mark.parametrize("size", ["48", "h/12", "(main_h-text_h)/10", "w/30"])
    def test_good_size(self, size: str) -> None:
        assert f"fontsize={size}" in caption_filter("t.txt", size=size)

    def test_color_with_filter_syntax_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="Unknown color"):
            caption_filter("t.txt", color="white:text=x")

    @pytest.mark.parametrize(("start", "end"), [(-1.0, None), (None, 0.0), (2.0, 1.0), (1.0, 1.0)])
    def test_bad_window(self, start: float | None, end: float | None) -> None:
        with pytest.raises(InvalidSpecError, match="--start"):
            caption_filter("t.txt", start=start, end=end)


@pytest.mark.integration
class TestColorCheck:
    def test_known_color_passes(self) -> None:
        validate_color("yellow", FFmpegRunner())
        validate_color("#ff0000", FFmpegRunner())

    def test_unknown_color_is_friendly(self) -> None:
        with pytest.raises(InvalidSpecError, match="Unknown color 'notacolor'"):
            validate_color("notacolor", FFmpegRunner())


class TestPrepareOutput:
    def test_refuses_to_overwrite_input(self, tmp_path: Path) -> None:
        src = tmp_path / "a.mp4"
        with pytest.raises(InvalidSpecError, match="one of the input files"):
            prepare_output(tmp_path / "." / "a.mp4", src)

    def test_creates_missing_folders(self, tmp_path: Path) -> None:
        prepare_output(tmp_path / "x" / "y" / "o.mp4")
        assert (tmp_path / "x" / "y").is_dir()

    def test_unusable_folder_is_friendly(self, tmp_path: Path) -> None:
        (tmp_path / "file").write_text("")
        with pytest.raises(InvalidSpecError, match="Can't create the folder"):
            prepare_output(tmp_path / "file" / "o.mp4")


class TestFastEncoding:
    def test_generate_flags_replace_and_extend(self) -> None:
        h264 = video_codec_args("h264", fast=True)
        assert h264[h264.index("-preset") + 1] == "veryfast"
        vp9 = video_codec_args("vp9", fast=True)
        assert vp9[vp9.index("-deadline") + 1] == "realtime"
        assert video_codec_args("prores", fast=True) == video_codec_args("prores")

    def test_default_keeps_quality_settings(self) -> None:
        args = video_codec_args("h264")
        assert args[args.index("-preset") + 1] == "fast"
        assert video_codec_args("mpeg2", fast=True) == video_codec_args("mpeg2")


class TestMatrixUpFront:
    def test_missing_source(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidSpecError, match="File not found"):
            run_matrix(tmp_path / "ghost.mp4", tmp_path / "o", ["30"], ["720p"])

    def test_negative_jobs(self, tmp_path: Path) -> None:
        (tmp_path / "in.mp4").touch()
        with pytest.raises(InvalidSpecError, match="--jobs"):
            run_matrix(tmp_path / "in.mp4", tmp_path / "o", ["30"], ["720p"], jobs=-1)

    def test_bad_entry_fails_before_any_run(self, tmp_path: Path) -> None:
        (tmp_path / "in.mp4").touch()
        with pytest.raises(InvalidSpecError, match="fps 'abc'"):
            run_matrix(tmp_path / "in.mp4", tmp_path / "o", ["30", "abc"], ["720p"])

    def test_outdir_is_a_file(self, tmp_path: Path) -> None:
        (tmp_path / "in.mp4").touch()
        with pytest.raises(InvalidSpecError, match="output folder"):
            run_matrix(tmp_path / "in.mp4", tmp_path / "in.mp4", ["30"], ["720p"])


class TestOpenAndModule:
    def test_python_dash_m(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import runpy
        import sys

        monkeypatch.setattr(sys, "argv", ["vidfix", "--version"])
        with pytest.raises(SystemExit) as done:
            runpy.run_module("vidfix", run_name="__main__")
        assert done.value.code == 0


@pytest.mark.integration
class TestOpenFlag:
    def test_open_launches_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        import typer

        opened: list[str] = []
        monkeypatch.setattr(typer, "launch", lambda target: opened.append(target) or 0)
        out = tmp_path / "o.wav"
        result = CliRunner().invoke(app, ["generate", "-o", str(out), "--duration", "1", "--open"])
        assert result.exit_code == 0, result.output
        assert opened == [str(out.resolve())]

    def test_open_launches_variants_folder(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import typer

        opened: list[str] = []
        monkeypatch.setattr(typer, "launch", lambda target: opened.append(target) or 0)
        src = generate(tmp_path / "s.mp4", duration="1", res="160x120")
        outdir = tmp_path / "v"
        result = CliRunner().invoke(
            app, ["variants", str(src), "-o", str(outdir), "--fps", "25", "--res", "240p", "--open"]
        )
        assert result.exit_code == 0, result.output
        assert opened == [str(outdir.resolve())]

    @pytest.mark.parametrize("ext", ["ogg", "opus", "aac"])
    def test_new_audio_outputs(self, tmp_path: Path, ext: str) -> None:
        from vidfix import probe

        out = generate(tmp_path / f"a.{ext}", duration="1", layout="5.1")
        info = probe(out)
        assert info.audio is not None and info.audio.channels == 6
        back = to_format(out, tmp_path / "b.wav")
        assert probe(back).audio is not None

    def test_extracted_ogg_is_named_ogg(self, tmp_path: Path) -> None:
        from vidfix import probe

        src = generate(tmp_path / "s.mp4", duration="1", res="160x120")
        assert probe(to_format(src, tmp_path / "a.ogg")).container == "ogg"


class TestVersion:
    def test_version_flag(self) -> None:
        from vidfix import __version__

        result = CliRunner().invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("guards")
    paths = {
        "video": d / "v.mp4",
        "silent": d / "s.mp4",
        "wav": d / "a.wav",
        "png": d / "p.png",
    }
    generate(paths["video"], duration="1", res="160x120")
    generate(paths["silent"], duration="1", res="160x120", audio="none")
    generate(paths["wav"], duration="1")
    generate(paths["png"], res="160x120")
    return paths


@pytest.mark.integration
class TestRealGuards:
    def test_attach_onto_audio_only(self, clips: dict[str, Path], tmp_path: Path) -> None:
        with pytest.raises(InvalidSpecError, match="has no video"):
            attach(clips["wav"], tmp_path / "o.mp4", audio=clips["wav"])

    @pytest.mark.parametrize("track", ["png", "silent"])
    def test_attach_track_without_audio(
        self, clips: dict[str, Path], tmp_path: Path, track: str
    ) -> None:
        with pytest.raises(InvalidSpecError, match="no audio track to attach"):
            attach(clips["video"], tmp_path / "o.mp4", audio=clips[track])

    def test_caption_audio_only(self, clips: dict[str, Path], tmp_path: Path) -> None:
        with pytest.raises(InvalidSpecError, match="no video to caption"):
            caption(clips["wav"], tmp_path / "o.mp4", "hi")

    def test_convert_audio_only(self, clips: dict[str, Path], tmp_path: Path) -> None:
        with pytest.raises(InvalidSpecError, match="has no video"):
            convert(clips["wav"], tmp_path / "o.mp4")

    def test_format_audio_to_picture(self, clips: dict[str, Path], tmp_path: Path) -> None:
        with pytest.raises(InvalidSpecError, match="no picture"):
            to_format(clips["wav"], tmp_path / "o.png")

    def test_convert_in_place(self, clips: dict[str, Path]) -> None:
        with pytest.raises(InvalidSpecError, match="one of the input files"):
            convert(clips["video"], clips["video"], fps="25")

    def test_generate_into_new_folder(self, tmp_path: Path) -> None:
        out = generate(tmp_path / "new" / "deep" / "o.mp4", duration="1", res="160x120")
        assert out.is_file()

    def test_verify_takes_cli_style_specs(self, clips: dict[str, Path]) -> None:
        result = verify(clips["video"], fps="30", duration="1s", res="160x120")
        assert result.passed

    def test_verify_negative_tolerance(self, clips: dict[str, Path]) -> None:
        with pytest.raises(InvalidSpecError, match="negative"):
            verify(clips["video"], fps="30", fps_tolerance=-1)
