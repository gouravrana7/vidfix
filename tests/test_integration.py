"""Integration tests: run the real FFmpeg binary on tiny 1-second clips."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidfix import generate, probe

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
