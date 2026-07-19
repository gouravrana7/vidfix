"""Unit tests for FFmpeg runner plumbing (no real FFmpeg invocation)."""

from __future__ import annotations

import pytest

from vidfix.core.ffmpeg import (
    BASE_FLAGS,
    FFmpegRunner,
    ProgressEvent,
    parse_progress_line,
    progress_events,
    video_codec_args,
)
from vidfix.exceptions import ConversionError, InvalidSpecError, stderr_tail


class TestVideoCodecArgs:
    def test_prores_rejected_in_mp4(self) -> None:
        with pytest.raises(InvalidSpecError, match="mov"):
            video_codec_args("prores", "out.mp4")

    def test_prores_allowed_in_mov(self) -> None:
        assert "prores_ks" in video_codec_args("prores", "out.mov")

    def test_output_optional(self) -> None:
        assert "libx264" in video_codec_args("h264")


class TestParseProgressLine:
    def test_key_value(self) -> None:
        assert parse_progress_line("frame=42\n") == ("frame", "42")

    def test_blank_and_garbage(self) -> None:
        assert parse_progress_line("") is None
        assert parse_progress_line("no equals here") is None


class TestProgressEvents:
    def test_block_yields_event(self) -> None:
        lines = [
            "frame=120",
            "out_time_us=4000000",
            "speed=2.5x",
            "progress=continue",
            "frame=240",
            "out_time_us=8000000",
            "speed=3.0x",
            "progress=end",
        ]
        events = list(progress_events(lines))
        assert events == [
            ProgressEvent(seconds=4.0, frame=120, speed=2.5, done=False),
            ProgressEvent(seconds=8.0, frame=240, speed=3.0, done=True),
        ]

    def test_negative_out_time_clamped(self) -> None:
        events = list(progress_events(["out_time_us=-100", "progress=continue"]))
        assert events[0].seconds == 0.0

    def test_bad_speed_ignored(self) -> None:
        events = list(progress_events(["speed=N/Ax", "progress=end"]))
        assert events[0].speed is None


class TestBuildCommand:
    def test_base_flags_prepended(self) -> None:
        runner = FFmpegRunner(ffmpeg_path="/fake/ffmpeg")
        command = runner.build_command(["-i", "in.mp4", "out.mp4"])
        assert command[0] == "/fake/ffmpeg"
        assert tuple(command[1 : 1 + len(BASE_FLAGS)]) == BASE_FLAGS
        assert command[-3:] == ["-i", "in.mp4", "out.mp4"]

    def test_progress_flags(self) -> None:
        runner = FFmpegRunner(ffmpeg_path="/fake/ffmpeg")
        command = runner.build_command(["out.mp4"], with_progress=True)
        assert "-progress" in command
        assert command[command.index("-progress") + 1] == "pipe:1"


class TestStderrTail:
    def test_keeps_last_lines(self) -> None:
        stderr = "\n".join(f"line {i}" for i in range(40))
        tail = stderr_tail(stderr, max_lines=5)
        assert tail.splitlines() == [f"line {i}" for i in range(35, 40)]

    def test_skips_blank_lines(self) -> None:
        assert stderr_tail("a\n\n\nb\n", max_lines=5) == "a\nb"


class TestConversionError:
    def test_includes_stderr_tail(self) -> None:
        err = ConversionError("boom", stderr="x\nencoder failed\n", returncode=1)
        assert "encoder failed" in str(err)
        assert err.returncode == 1

    def test_no_stderr(self) -> None:
        assert str(ConversionError("boom")) == "boom"


class TestRunnerDiscovery:
    def test_explicit_paths_used(self) -> None:
        runner = FFmpegRunner(ffmpeg_path="/a/ffmpeg", ffprobe_path="/a/ffprobe")
        assert runner.ffmpeg_path == "/a/ffmpeg"
        assert runner.ffprobe_path == "/a/ffprobe"

    def test_run_missing_binary_raises(self) -> None:
        runner = FFmpegRunner(ffmpeg_path="/definitely/not/here/ffmpeg")
        with pytest.raises(Exception) as excinfo:
            runner.run(["-i", "in.mp4", "out.mp4"])
        assert "ffmpeg" in str(excinfo.value).lower()


class TestFindFfmpegFallback:
    def test_imageio_failure_falls_back_to_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import imageio_ffmpeg

        import vidfix.core.ffmpeg as fm

        monkeypatch.setattr(
            imageio_ffmpeg, "get_ffmpeg_exe", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        monkeypatch.setattr(fm.shutil, "which", lambda _: "/usr/local/bin/ffmpeg")
        assert fm.find_ffmpeg() == "/usr/local/bin/ffmpeg"

    def test_nothing_found_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import imageio_ffmpeg

        import vidfix.core.ffmpeg as fm
        from vidfix.exceptions import FFmpegNotFoundError

        monkeypatch.setattr(
            imageio_ffmpeg, "get_ffmpeg_exe", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        monkeypatch.setattr(fm.shutil, "which", lambda _: None)
        with pytest.raises(FFmpegNotFoundError):
            fm.find_ffmpeg()


class TestProgressEventsSkipsUnparseable:
    def test_junk_lines_ignored(self) -> None:
        events = list(progress_events(["garbage", "out_time_us=1000000", "progress=end"]))
        assert events[-1].done is True


class TestRunFailure:
    def test_nonzero_exit_raises_conversion_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import subprocess

        import vidfix.core.ffmpeg as fm

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, returncode=3, stdout="", stderr="boom")

        monkeypatch.setattr(fm.subprocess, "run", fake_run)
        runner = FFmpegRunner(ffmpeg_path="/fake/ffmpeg")
        with pytest.raises(ConversionError) as excinfo:
            runner.run(["-i", "nope"])
        assert "boom" in (excinfo.value.stderr or "")
