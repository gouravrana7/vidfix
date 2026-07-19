"""CLI-level tests: every command runs via CliRunner with the FFmpeg layer mocked."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from vidfix import cli
from vidfix.core.convert import ConvertPlan
from vidfix.core.matrix import MatrixJob, MatrixResult
from vidfix.core.probe import AudioInfo, MediaInfo
from vidfix.core.verify import PropertyCheck, VerifyResult
from vidfix.exceptions import ConversionError

runner = CliRunner()

INFO = MediaInfo(
    path="in.mp4",
    container="mp4",
    duration=1.0,
    width=160,
    height=120,
    fps="30",
    video_codec="h264",
    audio=AudioInfo(codec="aac", sample_rate=44100, channels=2),
)


class Recorder:
    """Stand-in for a core function; records the call and returns a canned result."""

    def __init__(self, result: Any = None) -> None:
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}
        self.result = result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.args, self.kwargs = args, kwargs
        return self.result


def combined_output(result: Any) -> str:
    """stdout + stderr regardless of click version's capture split."""
    try:
        return str(result.output) + str(result.stderr)
    except ValueError:  # stderr not separately captured
        return str(result.output)


@pytest.fixture()
def fake_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.probe_mod, "probe", lambda _: INFO)


class TestGenerateCli:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = Recorder()
        monkeypatch.setattr(cli.generate_mod, "generate", rec)
        result = runner.invoke(cli.app, ["generate", "-o", "out.mp4"])
        assert result.exit_code == 0
        assert "wrote out.mp4" in result.output
        assert rec.kwargs["fps"] == "30"
        assert rec.kwargs["drop_frame"] is None

    @pytest.mark.parametrize(
        ("preset", "fps", "drop_frame"),
        [
            ("df30", "30000/1001", True),
            ("ndf30", "30000/1001", False),
            ("pal25", "25", False),
            ("ndf25", "25", False),
            ("film23976", "24000/1001", False),
        ],
    )
    def test_preset_sets_fps_and_drop_frame(
        self, monkeypatch: pytest.MonkeyPatch, preset: str, fps: str, drop_frame: bool
    ) -> None:
        rec = Recorder()
        monkeypatch.setattr(cli.generate_mod, "generate", rec)
        result = runner.invoke(cli.app, ["generate", "-o", "o.mp4", "--preset", preset])
        assert result.exit_code == 0
        assert rec.kwargs["fps"] == fps
        assert rec.kwargs["drop_frame"] is drop_frame

    @pytest.mark.parametrize(
        ("preset", "fps", "expected_fps"),
        [
            ("df30", "30", "30"),  # user overrides DF preset with an exact rate
            ("df30", "29.97", "29.97"),  # override to the same DF rate
            ("ndf30", "25", "25"),
            ("pal25", "30", "30"),
            (None, "29.97", "29.97"),  # no preset at all
        ],
    )
    def test_explicit_fps_drops_preset_timecode_hint(
        self,
        monkeypatch: pytest.MonkeyPatch,
        preset: str | None,
        fps: str,
        expected_fps: str,
    ) -> None:
        """Explicit --fps wins; timecode counting then follows the real rate (no error)."""
        rec = Recorder()
        monkeypatch.setattr(cli.generate_mod, "generate", rec)
        args = ["generate", "-o", "o.mp4", "--fps", fps, "--timecode"]
        if preset:
            args += ["--preset", preset]
        result = runner.invoke(cli.app, args)
        assert result.exit_code == 0
        assert rec.kwargs["fps"] == expected_fps
        assert rec.kwargs["drop_frame"] is None

    def test_error_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*args: Any, **kwargs: Any) -> None:
            raise ConversionError("ffmpeg exploded")

        monkeypatch.setattr(cli.generate_mod, "generate", boom)
        result = runner.invoke(cli.app, ["generate", "-o", "o.mp4"])
        assert result.exit_code == 1
        assert "ffmpeg exploded" in combined_output(result)


class TestConvertCli:
    def test_stream_copy(self, monkeypatch: pytest.MonkeyPatch, fake_probe: None) -> None:
        rec = Recorder(ConvertPlan(args=[], stream_copy=True, warnings=["lossy trim"]))
        monkeypatch.setattr(cli.convert_mod, "convert", rec)
        result = runner.invoke(cli.app, ["convert", "in.mp4", "-o", "out.mp4", "--preset", "pal25"])
        assert result.exit_code == 0
        assert "stream copy" in result.output
        assert "lossy trim" in combined_output(result)
        assert rec.kwargs["fps"] == "25"

    def test_reencode(self, monkeypatch: pytest.MonkeyPatch, fake_probe: None) -> None:
        rec = Recorder(ConvertPlan(args=[], stream_copy=False))
        monkeypatch.setattr(cli.convert_mod, "convert", rec)
        result = runner.invoke(cli.app, ["convert", "in.mp4", "-o", "out.mp4", "--fps", "60"])
        assert result.exit_code == 0
        assert "re-encode" in result.output
        assert rec.kwargs["fps"] == "60"


class TestCaptionCli:
    def test_passthrough(self, monkeypatch: pytest.MonkeyPatch, fake_probe: None) -> None:
        rec = Recorder()
        monkeypatch.setattr(cli.caption_mod, "caption", rec)
        result = runner.invoke(
            cli.app,
            ["caption", "in.mp4", "-o", "out.mp4", "--text", "Take 42",
             "--position", "top", "--start", "1", "--end", "3"],
        )  # fmt: skip
        assert result.exit_code == 0
        assert "wrote out.mp4" in result.output
        assert rec.args[2] == "Take 42"
        assert rec.kwargs["position"] == "top"
        assert rec.kwargs["start"] == 1.0
        assert rec.kwargs["end"] == 3.0


class TestFormatCli:
    def test_image_to_image(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = Recorder()
        monkeypatch.setattr(cli.formats_mod, "to_format", rec)
        result = runner.invoke(cli.app, ["format", "photo.png", "-o", "photo.webp"])
        assert result.exit_code == 0
        assert "wrote photo.webp" in result.output

    def test_video_to_video(self, monkeypatch: pytest.MonkeyPatch, fake_probe: None) -> None:
        rec = Recorder()
        monkeypatch.setattr(cli.formats_mod, "to_format", rec)
        result = runner.invoke(cli.app, ["format", "clip.mov", "-o", "clip.mp4"])
        assert result.exit_code == 0
        assert "wrote clip.mp4" in result.output


class TestVerifyCli:
    @staticmethod
    def _result(passed: bool) -> VerifyResult:
        check = PropertyCheck(name="fps", expected="25.000", actual="25.000", passed=passed)
        return VerifyResult(path="f.mp4", passed=passed, checks=[check])

    def test_pass_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.verify_mod, "verify", Recorder(self._result(True)))
        result = runner.invoke(cli.app, ["verify", "f.mp4", "--fps", "25"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_fail_table_and_exit_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.verify_mod, "verify", Recorder(self._result(False)))
        result = runner.invoke(cli.app, ["verify", "f.mp4", "--fps", "25"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.verify_mod, "verify", Recorder(self._result(True)))
        result = runner.invoke(cli.app, ["verify", "f.mp4", "--fps", "25", "--json"])
        assert result.exit_code == 0
        assert '"passed"' in result.output

    def test_nothing_to_verify(self) -> None:
        result = runner.invoke(cli.app, ["verify", "f.mp4"])
        assert result.exit_code == 1
        assert "Nothing to verify" in combined_output(result)


class TestInfoCli:
    def test_table(self, fake_probe: None) -> None:
        result = runner.invoke(cli.app, ["info", "in.mp4"])
        assert result.exit_code == 0
        for expected in ("type", "mp4 video", "1.00 seconds", "160x120", "h264"):
            assert expected in result.output
        assert "stereo (left+right)" in result.output
        assert "normal quality (44100 Hz)" in result.output
        assert "container" not in result.output
        assert "2ch" not in result.output

    def test_table_friendly_long_duration_and_layout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        info = INFO.model_copy(
            update={
                "duration": 90.0,
                "width": 1280,
                "height": 720,
                "pix_fmt": "yuv420p",
                "audio": AudioInfo(codec="aac", sample_rate=48000, channels=6),
            }
        )
        monkeypatch.setattr(cli.probe_mod, "probe", lambda _: info)
        result = runner.invoke(cli.app, ["info", "in.mp4"])
        assert "1m 30s (90.00 seconds)" in result.output
        assert "720p (1280x720)" in result.output
        assert "standard (yuv420p)" in result.output
        assert "normal quality (48000 Hz)" in result.output
        assert "5.1 surround" in result.output

    def test_json(self, fake_probe: None) -> None:
        result = runner.invoke(cli.app, ["info", "in.mp4", "--json"])
        assert result.exit_code == 0
        assert '"container"' in result.output

    def test_probe_alias_still_works(self, fake_probe: None) -> None:
        result = runner.invoke(cli.app, ["probe", "in.mp4"])
        assert result.exit_code == 0
        assert "mp4" in result.output

    def test_help_shows_new_names_hides_old(self) -> None:
        result = runner.invoke(cli.app, ["--help"])
        assert "info" in result.output and "variants" in result.output
        assert "probe" not in result.output and "matrix" not in result.output


class TestVariantsCli:
    @staticmethod
    def _results(all_ok: bool) -> list[MatrixResult]:
        ok_job = MatrixJob(fps="30", res="720p", output=Path("out/in_30fps_720p.mp4"))
        bad_job = MatrixJob(fps="60", res="720p", output=Path("out/in_60fps_720p.mp4"))
        results = [MatrixResult(job=ok_job, ok=True)]
        if not all_ok:
            results.append(MatrixResult(job=bad_job, ok=False, error="boom"))
        return results

    def test_all_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.matrix_mod, "run_matrix", Recorder(self._results(True)))
        result = runner.invoke(
            cli.app, ["variants", "in.mp4", "-o", "out", "--fps", "30", "--res", "720p"]
        )
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_any_failure_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.matrix_mod, "run_matrix", Recorder(self._results(False)))
        result = runner.invoke(
            cli.app, ["variants", "in.mp4", "-o", "out", "--fps", "30,60", "--res", "720p"]
        )
        assert result.exit_code == 1
        assert "FAIL" in result.output
        assert "boom" in result.output

    def test_matrix_alias_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli.matrix_mod, "run_matrix", Recorder(self._results(True)))
        result = runner.invoke(
            cli.app, ["matrix", "in.mp4", "-o", "out", "--fps", "30", "--res", "720p"]
        )
        assert result.exit_code == 0


class TestPresetCli:
    def test_list_shows_broadcast_family(self) -> None:
        result = runner.invoke(cli.app, ["preset", "list"])
        assert result.exit_code == 0
        for name in ("pal25", "pal50", "ndf25", "ndf30", "ndf60", "film24", "film23976"):
            assert name in result.output
        assert "alias" in result.output

    def test_show_resolves_alias(self) -> None:
        result = runner.invoke(cli.app, ["preset", "show", "ndf25"])
        assert result.exit_code == 0
        assert "25" in result.output
        assert "ndf" in result.output

    def test_show_unknown(self) -> None:
        result = runner.invoke(cli.app, ["preset", "show", "nope"])
        assert result.exit_code == 1
        assert "Unknown preset" in combined_output(result)
