"""Integration tests: run the real FFmpeg binary on tiny 1-second clips."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidfix import generate, probe
from vidfix.core.capabilities import CONTAINER_ALLOWED_CODECS

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def tiny_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("media") / "tiny.mp4"
    generate(out, fps="30", duration="1", res="160x120", pattern="testsrc")
    return out


class TestGenerateProbe:
    def test_roundtrip_specs(self, tiny_clip: Path) -> None:
        info = probe(tiny_clip)
        assert info.width == 160
        assert info.height == 120
        assert info.fps_float == pytest.approx(30, abs=0.01)
        assert info.duration == pytest.approx(1.0, abs=0.1)
        assert info.video_codec == "h264"
        assert info.audio is not None

    def test_generate_no_audio(self, tmp_path: Path) -> None:
        out = tmp_path / "mute.mp4"
        generate(out, fps="30", duration="1", res="160x120", audio="none")
        assert probe(out).audio is None

    def test_generate_drop_frame(self, tmp_path: Path) -> None:
        out = tmp_path / "df.mp4"
        generate(out, fps="29.97", duration="1", res="160x120", audio="none")
        assert probe(out).fps == "30000/1001"

    def test_convert_fps_and_res(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import convert

        out = tmp_path / "conv.mp4"
        plan = convert(tiny_clip, out, fps="15", res="120x120")
        assert not plan.stream_copy
        info = probe(out)
        assert info.fps_float == pytest.approx(15, abs=0.01)
        assert (info.width, info.height) == (120, 120)

    def test_convert_stream_copy_trim(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import convert

        out = tmp_path / "trim.mp4"
        plan = convert(tiny_clip, out, duration="0.5")
        assert plan.stream_copy
        assert probe(out).duration <= 1.0

    def test_convert_extend_freeze(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import convert

        out = tmp_path / "ext.mp4"
        convert(tiny_clip, out, duration="2")
        assert probe(out).duration == pytest.approx(2.0, abs=0.15)

    def test_generate_timecode(self, tmp_path: Path) -> None:
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        out = tmp_path / "tc.mp4"
        generate(out, fps="30", duration="1", res="160x120", timecode=True, audio="none")
        assert probe(out).duration == pytest.approx(1.0, abs=0.1)

    @pytest.mark.parametrize(
        ("fps", "drop_frame"),
        [("29.97", True), ("29.97", False), ("25", False), ("23.976", None)],
    )
    def test_generate_timecode_df_ndf(
        self, tmp_path: Path, fps: str, drop_frame: bool | None
    ) -> None:
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        out = tmp_path / "tc.mp4"
        generate(
            out, fps=fps, duration="1", res="160x120",
            timecode=True, drop_frame=drop_frame, audio="none",
        )  # fmt: skip
        assert probe(out).duration == pytest.approx(1.0, abs=0.1)


class TestCaption:
    def test_caption_existing_video(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import caption
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        out = tmp_path / "cap.mp4"
        caption(tiny_clip, out, "hello: it's 100% 'fine'", start=0.2, end=0.8)
        info = probe(out)
        assert (info.width, info.height) == (160, 120)
        assert info.duration == pytest.approx(1.0, abs=0.1)

    @pytest.mark.parametrize("ext", ["webm", "mkv", "mxf", "mov"])
    def test_caption_into_any_container(self, tiny_clip: Path, tmp_path: Path, ext: str) -> None:
        """The audio must be re-encoded for the box: webm needs opus, mxf 48 kHz pcm."""
        from vidfix import caption
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        out = tmp_path / f"cap.{ext}"
        caption(tiny_clip, out, "boxed")
        assert probe(out).audio is not None

    def test_generate_with_text(self, tmp_path: Path) -> None:
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        out = tmp_path / "txt.mp4"
        generate(out, fps="30", duration="1", res="160x120", audio="none", text="TEST CLIP")
        assert probe(out).duration == pytest.approx(1.0, abs=0.1)


class TestFormats:
    def test_video_to_thumbnail_to_webp(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import to_format

        thumb = to_format(tiny_clip, tmp_path / "thumb.png")
        assert thumb.stat().st_size > 0
        webp = to_format(thumb, tmp_path / "thumb.webp")
        assert webp.stat().st_size > 0

    def test_video_to_gif(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import to_format

        gif = to_format(tiny_clip, tmp_path / "out.gif")
        assert gif.stat().st_size > 0


class TestProgressStreaming:
    def test_progress_events_reach_callback(self, tmp_path: Path) -> None:
        from vidfix.core.ffmpeg import ProgressEvent

        events: list[ProgressEvent] = []
        generate(
            tmp_path / "p.mp4",
            fps="30",
            duration="1",
            res="160x120",
            audio="none",
            on_progress=events.append,
        )
        assert events
        assert events[-1].done

    def test_version_reports_ffmpeg(self) -> None:
        from vidfix.core.ffmpeg import FFmpegRunner

        assert "ffmpeg" in FFmpegRunner().version()


class TestMatrix:
    def test_two_variants(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix.core.matrix import run_matrix

        results = run_matrix(tiny_clip, tmp_path, ["15", "20"], ["120x120"], jobs=2)
        assert all(r.ok for r in results)
        fps_seen = sorted(probe(r.job.output).fps for r in results)
        assert fps_seen == ["15", "20"]


class TestCliPipeline:
    def test_generate_probe_verify(self, tmp_path: Path) -> None:
        """Full real-FFmpeg pipeline through the actual CLI: generate → probe → verify."""
        from typer.testing import CliRunner

        from vidfix.cli import app
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")
        runner = CliRunner()
        clip = tmp_path / "pal.mp4"

        generated = runner.invoke(
            app,
            ["generate", "-o", str(clip), "--preset", "pal25", "--duration", "1",
             "--res", "160x120", "--timecode", "--audio", "none"],
        )  # fmt: skip
        assert generated.exit_code == 0
        assert "wrote" in generated.output
        assert clip.stat().st_size > 0

        probed = runner.invoke(app, ["probe", str(clip), "--json"])
        assert probed.exit_code == 0
        assert '"fps": "25"' in probed.output

        verified = runner.invoke(app, ["verify", str(clip), "--fps", "25", "--duration", "1"])
        assert verified.exit_code == 0
        assert "PASS" in verified.output


class TestVerifyCli:
    def test_exit_codes(self, tiny_clip: Path) -> None:
        from typer.testing import CliRunner

        from vidfix.cli import app

        runner = CliRunner()
        passing = runner.invoke(
            app, ["verify", str(tiny_clip), "--fps", "30", "--res", "160x120", "--codec", "h264"]
        )
        assert passing.exit_code == 0

        failing = runner.invoke(app, ["verify", str(tiny_clip), "--fps", "60"])
        assert failing.exit_code == 1

    def test_nothing_to_verify_errors(self, tiny_clip: Path) -> None:
        from typer.testing import CliRunner

        from vidfix.cli import app

        result = CliRunner().invoke(app, ["verify", str(tiny_clip)])
        assert result.exit_code == 1


VIDEO_CONTAINERS = ["mp4", "mov", "mkv", "avi", "webm", "mxf", "mpg", "ogv", "flv", "wmv", "3gp"]
EXPECTED_VIDEO_CODEC = {
    "mp4": "h264", "mov": "h264", "mkv": "h264", "avi": "h264",
    "flv": "h264", "wmv": "h264", "3gp": "h264",
    "webm": "vp9", "mxf": "mpeg2video", "mpg": "mpeg2video", "ogv": "theora",
}  # fmt: skip

PICTURE_FORMATS = ["png", "jpg", "jpeg", "webp", "bmp", "tiff"]
EXPECTED_IMAGE_CODEC = {
    "png": "png", "jpg": "mjpeg", "jpeg": "mjpeg", "webp": "webp", "bmp": "bmp", "tiff": "tiff",
}  # fmt: skip


def _run_cli(args: list[str]) -> None:
    """Invoke the real ``vidfix`` CLI command (real FFmpeg); assert it succeeds."""
    from typer.testing import CliRunner

    from vidfix.cli import app

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, f"{' '.join(args)} failed:\n{result.output}"


@pytest.fixture(scope="module")
def video_sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One tiny real clip per container, generated once for the convert matrix."""
    root = tmp_path_factory.mktemp("vsrc")
    clips: dict[str, Path] = {}
    for ext in VIDEO_CONTAINERS:
        out = root / f"src.{ext}"
        _run_cli(["generate", "-o", str(out), "--duration", "0.5", "--res", "160x120"])
        clips[ext] = out
    return clips


@pytest.fixture(scope="module")
def picture_sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One real still per picture format, generated once for the format matrix."""
    root = tmp_path_factory.mktemp("psrc")
    pics: dict[str, Path] = {}
    for ext in PICTURE_FORMATS:
        out = root / f"src.{ext}"
        _run_cli(["generate", "-o", str(out), "--res", "160x120"])
        pics[ext] = out
    return pics


class TestGenerateEveryFileType:
    """`vidfix generate` writes every container and picture format, with a valid codec."""

    @pytest.mark.parametrize("ext", VIDEO_CONTAINERS)
    def test_generate_video_container(self, tmp_path: Path, ext: str) -> None:
        out = tmp_path / f"gen.{ext}"
        _run_cli(["generate", "-o", str(out), "--duration", "0.5", "--res", "160x120"])
        info = probe(out)
        assert (info.width, info.height) == (160, 120)
        assert info.video_codec == EXPECTED_VIDEO_CODEC[ext]
        assert info.audio is not None

    @pytest.mark.parametrize("ext", PICTURE_FORMATS)
    def test_generate_picture(self, tmp_path: Path, ext: str) -> None:
        out = tmp_path / f"pic.{ext}"
        _run_cli(["generate", "-o", str(out), "--res", "160x120"])
        info = probe(out)
        assert (info.width, info.height) == (160, 120)
        assert info.video_codec == EXPECTED_IMAGE_CODEC[ext]
        assert info.duration == 0.0


class TestConvertEveryCombination:
    """`vidfix convert` from every container to every container: the full matrix.

    The target container must always get a codec that plays in it, regardless of
    what the source was.
    """

    @pytest.mark.parametrize("dst", VIDEO_CONTAINERS)
    @pytest.mark.parametrize("src", VIDEO_CONTAINERS)
    def test_convert_container_matrix(
        self, video_sources: dict[str, Path], tmp_path: Path, src: str, dst: str
    ) -> None:
        out = tmp_path / f"{src}_to.{dst}"
        _run_cli(["convert", str(video_sources[src]), "-o", str(out)])
        info = probe(out)
        assert info.video_codec == EXPECTED_VIDEO_CODEC[dst]
        assert (info.width, info.height) == (160, 120)


class TestFormatEveryPictureCombination:
    """`vidfix format` from every picture format to every picture format."""

    @pytest.mark.parametrize("dst", PICTURE_FORMATS)
    @pytest.mark.parametrize("src", PICTURE_FORMATS)
    def test_format_picture_matrix(
        self, picture_sources: dict[str, Path], tmp_path: Path, src: str, dst: str
    ) -> None:
        out = tmp_path / f"{src}_to.{dst}"
        _run_cli(["format", str(picture_sources[src]), "-o", str(out)])
        info = probe(out)
        assert (info.width, info.height) == (160, 120)
        assert info.video_codec == EXPECTED_IMAGE_CODEC[dst]


ALL_CODECS = ["h264", "h265", "prores", "vp9", "mpeg2", "theora"]
LAYOUTS = ["mono", "stereo", "5.1", "7.1", "left", "right"]


def _expected_channels(layout: str) -> int:
    from vidfix.core.generate import AUDIO_LAYOUTS

    return AUDIO_LAYOUTS.get(layout, 2)


class TestGenerateContainerCodecMatrix:
    """Every container x every codec: a compatible pair yields a real decodable
    stream; an incompatible one fails cleanly (friendly error) — never exit 0
    with a broken file, never a raw FFmpeg dump."""

    @pytest.mark.parametrize("codec", ALL_CODECS)
    @pytest.mark.parametrize("ext", VIDEO_CONTAINERS)
    def test_codec_in_container(self, tmp_path: Path, ext: str, codec: str) -> None:
        from vidfix.core.capabilities import allowed_codecs
        from vidfix.core.ffmpeg import CODEC_PROBE_NAMES
        from vidfix.exceptions import InvalidSpecError

        out = tmp_path / f"{codec}.{ext}"
        allowed = allowed_codecs(str(out))
        if allowed is not None and codec not in allowed:
            with pytest.raises(InvalidSpecError, match="can't hold"):
                generate(out, duration="0.5", res="160x120", codec=codec, audio="none")
            return
        generate(out, duration="0.5", res="160x120", codec=codec, audio="none")
        assert probe(out).video_codec == CODEC_PROBE_NAMES[codec]


class TestGenerateContainerLayoutMatrix:
    """Every container x every audio layout: layouts that fit produce the right
    channel count; layouts past the container's cap fail cleanly."""

    @pytest.mark.parametrize("layout", LAYOUTS)
    @pytest.mark.parametrize("ext", VIDEO_CONTAINERS)
    def test_layout_in_container(self, tmp_path: Path, ext: str, layout: str) -> None:
        from vidfix.core.capabilities import max_channels
        from vidfix.exceptions import InvalidSpecError

        out = tmp_path / f"{layout}.{ext}"
        want = _expected_channels(layout)
        cap = max_channels(str(out))
        if cap is not None and want > cap:
            with pytest.raises(InvalidSpecError, match="at most"):
                generate(out, duration="0.5", res="160x120", layout=layout)
            return
        generate(out, duration="0.5", res="160x120", layout=layout)
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == want


class TestAudioOnlyLayoutCaps:
    """Audio-only outputs honour their codec's channel ceiling."""

    @pytest.mark.parametrize("layout", LAYOUTS)
    @pytest.mark.parametrize("ext", ["wav", "mp3", "m4a", "flac"])
    def test_audio_only_layout(self, tmp_path: Path, ext: str, layout: str) -> None:
        from vidfix.core.capabilities import max_channels
        from vidfix.exceptions import InvalidSpecError

        out = tmp_path / f"tone.{ext}"
        want = _expected_channels(layout)
        cap = max_channels(str(out))
        if cap is not None and want > cap:
            with pytest.raises(InvalidSpecError, match="at most"):
                generate(out, duration="0.5", layout=layout)
            return
        generate(out, duration="0.5", layout=layout)
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == want


class TestCaptionAcrossCommands:
    """Captions and timecode work in generate AND convert, at any grid position."""

    def _need_drawtext(self) -> None:
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext-capable FFmpeg on this machine")

    @pytest.mark.parametrize("position", ["top-left", "center", "bottom-right"])
    def test_generate_caption_position(self, tmp_path: Path, position: str) -> None:
        self._need_drawtext()
        out = tmp_path / "cap.mp4"
        _run_cli(
            ["generate", "-o", str(out), "--duration", "0.6", "--res", "160x120",
             "--audio", "none", "--text", "HI", "--position", position, "--color", "yellow"],
        )  # fmt: skip
        assert probe(out).duration == pytest.approx(0.6, abs=0.2)

    def test_convert_caption(self, tiny_clip: Path, tmp_path: Path) -> None:
        self._need_drawtext()
        out = tmp_path / "c.mp4"
        _run_cli(
            ["convert", str(tiny_clip), "-o", str(out), "--text", "SUB",
             "--position", "top", "--start", "0.1", "--end", "0.5"],
        )  # fmt: skip
        assert probe(out).duration == pytest.approx(1.0, abs=0.2)

    def test_convert_timecode_uses_source_fps(self, tiny_clip: Path, tmp_path: Path) -> None:
        self._need_drawtext()
        out = tmp_path / "tc.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--timecode"])
        assert probe(out).duration == pytest.approx(1.0, abs=0.2)

    def test_convert_caption_and_timecode_with_fps(self, tiny_clip: Path, tmp_path: Path) -> None:
        self._need_drawtext()
        out = tmp_path / "both.mp4"
        _run_cli(
            ["convert", str(tiny_clip), "-o", str(out), "--text", "T",
             "--position", "top-right", "--timecode", "--fps", "25"],
        )  # fmt: skip
        assert probe(out).fps == "25"


class TestConvertAudioTypes:
    """`convert --audio` mirrors generate's audio types on an existing clip."""

    def test_keep_source_audio(self, tiny_clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "keep.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--audio", "keep", "--fps", "20"])
        assert probe(out).audio is not None

    def test_replace_with_tone(self, tiny_clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "tone.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--audio", "tone"])
        assert probe(out).audio is not None

    def test_replace_with_silence(self, tiny_clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "sil.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--audio", "silence"])
        info = probe(out)
        assert info.audio is not None
        assert info.duration == pytest.approx(1.0, abs=0.2)

    def test_drop_audio(self, tiny_clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "none.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--audio", "none"])
        assert probe(out).audio is None

    def test_legacy_no_audio_alias(self, tiny_clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "legacy.mp4"
        _run_cli(["convert", str(tiny_clip), "-o", str(out), "--no-audio"])
        assert probe(out).audio is None


EXTRACT_VIDEO = ["mp4", "mkv", "webm", "mov", "avi", "mxf", "mpg", "ogv", "flv", "3gp"]
AUDIO_OUT = ["wav", "mp3", "m4a", "flac"]
H264_BOXES = sorted(
    ext.lstrip(".")
    for ext, codecs in CONTAINER_ALLOWED_CODECS.items()
    if "h264" in codecs and ext != ".m4v"
)


def _has_subtitle(path: Path) -> bool:
    from vidfix.core.ffmpeg import FFmpegRunner

    return "Subtitle" in FFmpegRunner().run(["-i", str(path)], check=False).stderr


def _decodes(path: Path) -> bool:
    """True when every stream in the file decodes without error (no silent corruption)."""
    from vidfix.core.ffmpeg import FFmpegRunner

    result = FFmpegRunner().run(["-v", "error", "-i", str(path), "-f", "null", "-"], check=False)
    return result.returncode == 0


SOFT_SUB_BOXES = ["mp4", "mov", "mkv"]


@pytest.fixture(scope="module")
def extract_sources(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("extract")
    out: dict[str, Path] = {}
    for ext in EXTRACT_VIDEO:
        p = root / f"s.{ext}"
        generate(p, duration="0.6", res="160x120")
        out[ext] = p
    return out


class TestExtractAudioMatrix:
    """`format` extracts audio from every video container into every audio format."""

    @pytest.mark.parametrize("aext", AUDIO_OUT)
    @pytest.mark.parametrize("vext", EXTRACT_VIDEO)
    def test_extract(
        self, extract_sources: dict[str, Path], tmp_path: Path, vext: str, aext: str
    ) -> None:
        from vidfix import to_format

        out = tmp_path / f"{vext}.{aext}"
        to_format(extract_sources[vext], out)
        assert probe(out).audio is not None

    def test_no_audio_source_friendly(self, tmp_path: Path) -> None:
        from vidfix import to_format
        from vidfix.exceptions import InvalidSpecError

        mute = tmp_path / "mute.mp4"
        generate(mute, duration="0.5", res="160x120", audio="none")
        with pytest.raises(InvalidSpecError, match="no audio track"):
            to_format(mute, tmp_path / "out.mp3")

    @pytest.mark.parametrize("target", AUDIO_OUT)
    def test_audio_to_audio(self, tmp_path: Path, target: str) -> None:
        from vidfix import to_format

        src = tmp_path / "song.wav"
        generate(src, duration="1")
        out = to_format(src, tmp_path / f"out.{target}")
        assert probe(out).audio is not None


class TestAttach:
    """Mux external audio / subtitles onto a video, across combinations."""

    def _srt(self, tmp_path: Path) -> Path:
        srt = tmp_path / "s.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:00,800\nHello\n", encoding="utf-8")
        return srt

    @pytest.mark.parametrize("ext", H264_BOXES)
    def test_attach_audio_matrix(self, tmp_path: Path, ext: str) -> None:
        from vidfix import attach

        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120", audio="none")
        aud = tmp_path / "a.m4a"
        generate(aud, duration="1")
        out = tmp_path / f"o.{ext}"
        attach(base, out, audio=aud)
        info = probe(out)
        assert info.audio is not None
        assert info.video_codec != "none"
        assert _decodes(out)

    def test_attach_audio_incompatible_container(self, tmp_path: Path) -> None:
        from vidfix import attach
        from vidfix.exceptions import InvalidSpecError

        base = tmp_path / "base.mp4"  # h264
        generate(base, duration="1", res="160x120")
        aud = tmp_path / "a.m4a"
        generate(aud, duration="1")
        with pytest.raises(InvalidSpecError, match="can't hold"):
            attach(base, tmp_path / "o.webm", audio=aud)  # h264 can't be copied into webm

    @pytest.mark.parametrize("ext", ["mp4", "mov", "mkv"])
    def test_soft_subs(self, tmp_path: Path, ext: str) -> None:
        from vidfix import attach

        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120")
        out = tmp_path / f"o.{ext}"
        attach(base, out, subs=self._srt(tmp_path))
        assert _has_subtitle(out)

    def test_soft_subs_unsupported_container(self, tmp_path: Path) -> None:
        from vidfix import attach
        from vidfix.exceptions import InvalidSpecError

        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120")
        with pytest.raises(InvalidSpecError, match="soft subtitle"):
            attach(base, tmp_path / "o.avi", subs=self._srt(tmp_path))

    def test_burn_subs(self, tmp_path: Path) -> None:
        from vidfix import attach
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext/subtitles-capable FFmpeg on this machine")
        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120")
        out = tmp_path / "burn.mp4"
        attach(base, out, subs=self._srt(tmp_path), burn=True)
        assert probe(out).duration == pytest.approx(1.0, abs=0.2)

    def test_audio_and_soft_subs(self, tmp_path: Path) -> None:
        from vidfix import attach

        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120", audio="none")
        aud = tmp_path / "a.m4a"
        generate(aud, duration="1")
        out = tmp_path / "both.mkv"
        attach(base, out, audio=aud, subs=self._srt(tmp_path))
        assert probe(out).audio is not None
        assert _has_subtitle(out)

    def test_cli_attach_and_extract(self, tmp_path: Path) -> None:
        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120")
        aud = tmp_path / "a.m4a"
        generate(aud, duration="1")
        out = tmp_path / "o.mp4"
        _run_cli(["attach", str(base), "--audio", str(aud), "-o", str(out)])
        assert probe(out).audio is not None
        song = tmp_path / "song.mp3"
        _run_cli(["format", str(base), "-o", str(song)])
        assert probe(song).audio is not None

    def _two_audios(self, tmp_path: Path) -> tuple[Path, Path]:
        a1, a2 = tmp_path / "en.wav", tmp_path / "hi.mp3"
        generate(a1, duration="1", audio="tone")
        generate(a2, duration="1", audio="silence")
        return a1, a2

    def _base(self, tmp_path: Path, audio: str = "none") -> Path:
        base = tmp_path / "base.mp4"
        generate(base, duration="1", res="160x120", audio=audio)
        return base

    @pytest.mark.parametrize("ext", H264_BOXES)
    def test_two_audio_across_every_container(self, tmp_path: Path, ext: str) -> None:
        """Every h264 box: two-audio attach either errors friendly or keeps both tracks."""
        from vidfix import attach
        from vidfix.exceptions import InvalidSpecError

        a1, a2 = self._two_audios(tmp_path)
        out = tmp_path / f"multi.{ext}"
        try:
            attach(self._base(tmp_path), out, audio=[a1, a2])
        except InvalidSpecError as exc:
            assert "audio track" in str(exc)
            return
        assert probe(out).audio_track_count >= 2
        assert _decodes(out)

    @pytest.mark.parametrize("ext", ["mp4", "mkv", "mov"])
    def test_three_audio_tracks(self, tmp_path: Path, ext: str) -> None:
        from vidfix import attach

        a1, a2 = self._two_audios(tmp_path)
        a3 = tmp_path / "fr.wav"
        generate(a3, duration="1", audio="tone")
        out = tmp_path / f"three.{ext}"
        attach(self._base(tmp_path), out, audio=[a1, a2, a3])
        assert probe(out).audio_track_count >= 3
        assert _decodes(out)

    def test_two_audios_onto_generated_clip_with_audio(self, tmp_path: Path) -> None:
        from vidfix import attach

        a1, a2 = self._two_audios(tmp_path)
        out = tmp_path / "multi.mkv"
        attach(self._base(tmp_path, audio="tone"), out, audio=[a1, a2])  # source track replaced
        assert probe(out).audio_track_count == 2

    @pytest.mark.parametrize("ext", SOFT_SUB_BOXES)
    def test_two_audios_and_soft_subs(self, tmp_path: Path, ext: str) -> None:
        from vidfix import attach

        a1, a2 = self._two_audios(tmp_path)
        out = tmp_path / f"both.{ext}"
        attach(self._base(tmp_path), out, audio=[a1, a2], subs=self._srt(tmp_path))
        assert probe(out).audio_track_count >= 2
        assert _has_subtitle(out)

    def test_two_audios_and_burn_subs(self, tmp_path: Path) -> None:
        from vidfix import attach
        from vidfix.core.generate import drawtext_available

        if not drawtext_available():
            pytest.skip("no drawtext/subtitles-capable FFmpeg on this machine")
        a1, a2 = self._two_audios(tmp_path)
        out = tmp_path / "burn.mkv"
        attach(self._base(tmp_path), out, audio=[a1, a2], subs=self._srt(tmp_path), burn=True)
        assert probe(out).audio_track_count >= 2

    def test_missing_attach_files_friendly(self, tmp_path: Path) -> None:
        from vidfix import attach
        from vidfix.exceptions import InvalidSpecError

        base = self._base(tmp_path)
        with pytest.raises(InvalidSpecError, match="File not found"):
            attach(base, tmp_path / "o.mp4", audio=tmp_path / "nope.wav")
        with pytest.raises(InvalidSpecError, match="File not found"):
            attach(base, tmp_path / "o.mkv", subs=tmp_path / "nope.srt")

    def test_cli_two_audios(self, tmp_path: Path) -> None:
        a1, a2 = self._two_audios(tmp_path)
        out = tmp_path / "cli.mkv"
        _run_cli(
            ["attach", str(self._base(tmp_path)),
             "--audio", str(a1), "--audio", str(a2), "-o", str(out)]
        )  # fmt: skip
        assert probe(out).audio_track_count >= 2


class TestMxfFrameRate:
    """MXF is broadcast-only: non-standard rates fail cleanly, standard ones work."""

    @pytest.mark.parametrize("fps", ["15", "12", "20"])
    def test_non_broadcast_rejected(self, tmp_path: Path, fps: str) -> None:
        from vidfix.exceptions import InvalidSpecError

        with pytest.raises(InvalidSpecError, match="broadcast frame rate"):
            generate(tmp_path / "bad.mxf", fps=fps, duration="0.5", res="160x120", audio="none")

    @pytest.mark.parametrize("fps", ["25", "30", "50"])
    def test_broadcast_accepted(self, tmp_path: Path, fps: str) -> None:
        out = tmp_path / "ok.mxf"
        generate(out, fps=fps, duration="0.5", res="160x120", audio="none")
        assert probe(out).video_codec == "mpeg2video"


class TestAudioAndPictureGeneration:
    def test_audio_only_wav(self, tmp_path: Path) -> None:
        out = tmp_path / "tone.wav"
        generate(out, duration="1")
        info = probe(out)
        assert info.video_codec == "none"
        assert info.duration == pytest.approx(1.0, abs=0.1)
        assert info.audio is not None

    def test_audio_layout_5_1(self, tmp_path: Path) -> None:
        out = tmp_path / "surround.mp4"
        generate(out, duration="1", res="160x120", layout="5.1")
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == 6

    def test_audio_layout_left_is_stereo_pair(self, tmp_path: Path) -> None:
        out = tmp_path / "left.wav"
        generate(out, duration="1", layout="left")
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == 2

    def test_picture_png(self, tmp_path: Path) -> None:
        out = tmp_path / "card.png"
        generate(out, res="160x120")
        info = probe(out)
        assert (info.width, info.height) == (160, 120)
        assert info.duration == 0.0

    def test_convert_audio_layout_mono(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import convert

        out = tmp_path / "mono.mp4"
        convert(tiny_clip, out, layout="mono")
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == 1


def _mean_volume_db(path: Path) -> float:
    """Average loudness of a file's audio track, straight from FFmpeg."""
    import subprocess

    from vidfix.core.ffmpeg import FFmpegRunner

    result = subprocess.run(
        [FFmpegRunner().ffmpeg_path, "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    line = next(line for line in result.stderr.splitlines() if "mean_volume" in line)
    return float(line.split("mean_volume:")[1].split("dB")[0])


class TestSilentAudio:
    """`--audio silence` must write a real track that carries no sound."""

    def test_generate_silence_is_inaudible(self, tmp_path: Path) -> None:
        out = tmp_path / "mute.mp4"
        generate(out, duration="1", res="160x120", audio="silence")
        info = probe(out)
        assert info.audio is not None
        assert _mean_volume_db(out) < -80

    def test_generate_silence_matches_tone_channels(self, tmp_path: Path) -> None:
        tone, silence = tmp_path / "tone.mp4", tmp_path / "silence.mp4"
        generate(tone, duration="1", res="160x120", audio="tone")
        generate(silence, duration="1", res="160x120", audio="silence")
        assert probe(tone).audio.channels == probe(silence).audio.channels  # type: ignore[union-attr]

    def test_convert_silence_is_inaudible(self, tiny_clip: Path, tmp_path: Path) -> None:
        from vidfix import convert

        out = tmp_path / "mute_convert.mp4"
        convert(tiny_clip, out, audio="silence")
        assert probe(out).audio is not None
        assert _mean_volume_db(out) < -80

    @pytest.mark.parametrize("layout", ["mono", "stereo", "5.1"])
    def test_silence_honours_layout(self, tmp_path: Path, layout: str) -> None:
        out = tmp_path / f"mute_{layout}.mp4"
        generate(out, duration="1", res="160x120", audio="silence", layout=layout)
        info = probe(out)
        assert info.audio is not None
        assert info.audio.channels == {"mono": 1, "stereo": 2, "5.1": 6}[layout]
        assert _mean_volume_db(out) < -80


class TestCliOptionSweep:
    """Options that only the CLI exposes, exercised end to end with real FFmpeg."""

    @pytest.mark.parametrize(
        "pattern", ["smpte", "color-bars", "testsrc", "gradient", "solid:red", "solid:#00ff00"]
    )
    def test_generate_pattern(self, tmp_path: Path, pattern: str) -> None:
        out = tmp_path / "pat.mp4"
        _run_cli(["generate", "-o", str(out), "--duration", "0.5", "--res", "160x120",
                  "--pattern", pattern, "--audio", "none"])  # fmt: skip
        assert probe(out).video_codec == "h264"

    @pytest.mark.parametrize(
        ("preset", "fps"),
        [
            ("df30", 29.97),
            ("df60", 59.94),
            ("pal25", 25.0),
            ("pal50", 50.0),
            ("ndf25", 25.0),
            ("ndf30", 29.97),
            ("ndf60", 59.94),
            ("film24", 24.0),
            ("film23976", 23.976),
        ],
    )
    def test_generate_preset_rate(self, tmp_path: Path, preset: str, fps: float) -> None:
        out = tmp_path / f"{preset}.mp4"
        _run_cli(["generate", "-o", str(out), "--duration", "0.5", "--res", "160x120",
                  "--preset", preset, "--audio", "none"])  # fmt: skip
        assert probe(out).fps_float == pytest.approx(fps, abs=0.01)

    def test_variants_codec_and_jobs(self, tiny_clip: Path, tmp_path: Path) -> None:
        outdir = tmp_path / "variants"
        _run_cli(["variants", str(tiny_clip), "-o", str(outdir), "--fps", "25,30",
                  "--res", "160x120", "--codec", "h265", "--jobs", "2"])  # fmt: skip
        made = sorted(outdir.glob("*.mp4"))
        assert len(made) == 2
        assert all(probe(path).video_codec == "hevc" for path in made)

    def test_verify_json_and_tolerances(self, tiny_clip: Path) -> None:
        import json

        from typer.testing import CliRunner

        from vidfix.cli import app

        runner = CliRunner()
        loose = runner.invoke(
            app, ["verify", str(tiny_clip), "--duration", "1.2", "--duration-tolerance", "0.5"]
        )
        assert loose.exit_code == 0
        strict = runner.invoke(
            app, ["verify", str(tiny_clip), "--duration", "1.2", "--duration-tolerance", "0.05"]
        )
        assert strict.exit_code == 1
        as_json = runner.invoke(app, ["verify", str(tiny_clip), "--fps", "30", "--json"])
        assert json.loads(as_json.output)["passed"] is True

    def test_info_json_and_track_count(self, tiny_clip: Path, tmp_path: Path) -> None:
        import json

        from typer.testing import CliRunner

        from vidfix import attach
        from vidfix.cli import app

        runner = CliRunner()
        payload = json.loads(runner.invoke(app, ["info", str(tiny_clip), "--json"]).output)
        assert payload["video_codec"] == "h264"
        assert payload["audio"]["channels"] == 1

        extra = tmp_path / "extra.m4a"
        generate(extra, duration="1")
        dual = tmp_path / "dual.mkv"
        attach(tiny_clip, dual, audio=[extra, extra])
        table = runner.invoke(app, ["info", str(dual)])
        assert "2 tracks" in table.output

    def test_format_missing_input_is_friendly(self, tmp_path: Path) -> None:
        from typer.testing import CliRunner

        from vidfix.cli import app

        result = CliRunner().invoke(app, ["format", str(tmp_path / "ghost.mp4"), "-o",
                                          str(tmp_path / "out.png")])  # fmt: skip
        assert result.exit_code == 1
        assert "File not found" in result.output


class TestWizardEndToEnd:
    """The bare-`vidfix` wizard, driven by real answers on stdin, with real FFmpeg."""

    def _wizard(self, answers: list[str], cwd: Path):
        import os

        from typer.testing import CliRunner

        from vidfix.cli import app

        here = os.getcwd()
        os.chdir(cwd)
        try:
            return CliRunner().invoke(app, [], input="\n".join(answers) + "\n")
        finally:
            os.chdir(here)

    def test_generate_flow_writes_the_file(self, tmp_path: Path) -> None:
        result = self._wizard(
            ["generate", "video", "wiz.mkv", "smpte", "none", "25", "1", "160x120",
             "silence", "mono", "", "n"],
            tmp_path,
        )  # fmt: skip
        assert result.exit_code == 0, result.output
        assert "equivalent command:" in result.output
        info = probe(tmp_path / "wiz.mkv")
        assert info.fps == "25"
        assert info.audio is not None and info.audio.channels == 1

    def test_bad_answer_reprompts_then_succeeds(self, tmp_path: Path) -> None:
        result = self._wizard(
            ["generate", "video", "retry.mp4", "smpte", "none", "quick", "25", "1", "160x120",
             "none", "", "n"],
            tmp_path,
        )  # fmt: skip
        assert result.exit_code == 0, result.output
        assert "Cannot parse" in result.output
        assert probe(tmp_path / "retry.mp4").fps == "25"
