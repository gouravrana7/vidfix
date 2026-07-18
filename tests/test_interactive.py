"""Unit tests for the interactive wizard flows (prompts stubbed, no FFmpeg)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidfix import interactive


class Script:
    """Feed canned answers to rich prompts in order."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: list[str | bool]) -> None:
        self.answers = list(answers)

        def next_answer(*args: object, default: object = None, **kwargs: object) -> object:
            value = self.answers.pop(0)
            return default if value == "" and default not in (None, "") else value

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(next_answer))
        monkeypatch.setattr(interactive.Confirm, "ask", staticmethod(next_answer))


@pytest.fixture()
def media_file(tmp_path: Path) -> str:
    path = tmp_path / "in.mp4"
    path.write_bytes(b"x")
    return str(path)


class TestConvertFlow:
    def test_full_answers(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "df60", "", "30s", "720p", "out.mp4"])
        argv = interactive.convert_flow()
        assert argv == [
            "convert", media_file, "--preset", "df60", "--duration", "30s",
            "--res", "720p", "-o", "out.mp4",
        ]  # fmt: skip

    def test_preset_skips_codec_prompt(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "df60", "", "", "", "out.mp4"])
        argv = interactive.convert_flow()
        assert "--codec" not in argv

    def test_invalid_fps_reprompts(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(
            monkeypatch,
            [media_file, "none", "not-a-rate", "59.94", "", "", "h264", "out.mp4"],
        )
        argv = interactive.convert_flow()
        assert argv[argv.index("--fps") + 1] == "59.94"

    def test_missing_file_reprompts(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, ["/nope.mp4", media_file, "none", "", "", "", "h264", "out.mp4"])
        argv = interactive.convert_flow()
        assert argv[1] == media_file


class TestOtherFlows:
    def test_generate_flow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(
            monkeypatch,
            ["smpte", "df30", "", "10s", "1080p", "HELLO", True, "bars.mp4"],
        )
        argv = interactive.generate_flow()
        assert "--preset" in argv and "df30" in argv
        assert argv[argv.index("--text") + 1] == "HELLO"
        assert "--timecode" in argv
        assert argv[-2:] == ["-o", "bars.mp4"]

    def test_generate_flow_preset_not_overridden_by_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        Script(monkeypatch, ["smpte", "df30", "", "", "", "", False, "out.mp4"])
        argv = interactive.generate_flow()
        assert "--preset" in argv
        assert "--fps" not in argv and "--duration" not in argv and "--res" not in argv

    def test_caption_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "Take 42", "top", "cap.mp4"])
        argv = interactive.caption_flow()
        assert argv == [
            "caption",
            media_file,
            "--text",
            "Take 42",
            "--position",
            "top",
            "-o",
            "cap.mp4",
        ]

    def test_probe_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file])
        assert interactive.probe_flow() == ["info", media_file]

    def test_verify_flow_skips_blanks(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "", "30s", ""])
        assert interactive.verify_flow() == ["verify", media_file, "--duration", "30s"]

    def test_wizard_dispatch(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, ["info", media_file])
        assert interactive.wizard() == ["info", media_file]
