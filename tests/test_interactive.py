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


class TestAskSpec:
    """Blank defaults must not render as an empty '()' after the label."""

    @pytest.mark.parametrize(("default", "shown"), [("", False), ("30", True)])
    def test_show_default_only_when_set(
        self, monkeypatch: pytest.MonkeyPatch, default: str, shown: bool
    ) -> None:
        seen: dict[str, object] = {}

        def fake_ask(*args: object, **kwargs: object) -> str:
            seen.update(kwargs)
            return "25"

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        interactive.ask_spec("fps", interactive.parse_fps, default=default)
        assert seen["show_default"] is shown

    def test_preset_value_shown_in_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        labels: list[str] = []

        def fake_ask(label: str, **kwargs: object) -> str:
            labels.append(label)
            return ""

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        interactive.ask_spec("fps", interactive.parse_fps, preset_value="29.97")
        assert "preset: 29.97" in labels[0]
        assert "type to override" in labels[0]
        assert "enter to skip" not in labels[0]


class TestGenerateFlowPresetHints:
    def test_fps_prompt_names_preset_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        labels: list[str] = []
        answers = iter(["", "out.mp4", "smpte", "df30", "", "", "", "tone", "stereo", "", False])

        def fake_ask(label: str = "", **kwargs: object) -> object:
            labels.append(label)
            value = next(answers)
            default = kwargs.get("default")
            return default if value == "" and default not in (None, "") else value

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        monkeypatch.setattr(interactive.Confirm, "ask", staticmethod(fake_ask))
        interactive.generate_flow()
        fps_label = next(lb for lb in labels if lb.startswith("fps"))
        assert "preset: 29.97" in fps_label
        assert "type to override" in fps_label
        duration_label = next(lb for lb in labels if lb.startswith("Duration"))
        assert "enter to skip" not in duration_label

    def test_convert_prompts_say_keep_source(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        labels: list[str] = []
        answers = iter([media_file, "out.mp4", "none", "", "", "", "h264", "keep", "keep", ""])

        def fake_ask(label: str = "", **kwargs: object) -> object:
            labels.append(label)
            value = next(answers)
            default = kwargs.get("default")
            return default if value == "" and default not in (None, "") else value

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        monkeypatch.setattr(interactive.Confirm, "ask", staticmethod(lambda *a, **k: False))
        interactive.convert_flow()
        for start in ("Target fps", "Target duration", "Target resolution"):
            label = next(lb for lb in labels if lb.startswith(start))
            assert "enter = keep source" in label
            assert "enter to skip" not in label


class TestConvertFlow:
    def test_full_answers(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(
            monkeypatch,
            [media_file, "out.mp4", "df60", "", "30s", "720p", "keep", "5.1", "", False],
        )
        argv = interactive.convert_flow()
        assert argv == [
            "convert", media_file, "--preset", "df60", "--duration", "30s",
            "--res", "720p", "--audio-layout", "5.1", "-o", "out.mp4",
        ]  # fmt: skip

    def test_preset_skips_codec_prompt(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "out.mp4", "df60", "", "", "", "keep", "", "", False])
        argv = interactive.convert_flow()
        assert "--codec" not in argv
        assert "--audio" not in argv
        assert "--audio-layout" not in argv

    def test_invalid_fps_reprompts(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(
            monkeypatch,
            [
                media_file,
                "out.mp4",
                "none",
                "not-a-rate",
                "59.94",
                "",
                "",
                "h264",
                "keep",
                "",
                "",
                False,
            ],
        )
        argv = interactive.convert_flow()
        assert argv[argv.index("--fps") + 1] == "59.94"

    def test_missing_file_reprompts(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(
            monkeypatch,
            ["/nope.mp4", media_file, "out.mp4", "none", "", "", "", "h264", "keep", "", "", False],
        )
        argv = interactive.convert_flow()
        assert argv[1] == media_file


class TestOtherFlows:
    def test_generate_flow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(
            monkeypatch,
            ["", "bars.mp4", "smpte", "df30", "", "10s", "1080p", "", "", "HELLO", "", "", True],
        )
        argv = interactive.generate_flow()
        assert "--preset" in argv and "df30" in argv
        assert argv[argv.index("--audio-layout") + 1] == "stereo"
        assert argv[argv.index("--text") + 1] == "HELLO"
        assert "--timecode" in argv
        assert argv[-2:] == ["-o", "bars.mp4"]

    def test_generate_flow_preset_not_overridden_by_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        Script(monkeypatch, ["", "out.mp4", "smpte", "df30", "", "", "", "", "", "", False])
        argv = interactive.generate_flow()
        assert "--preset" in argv
        assert "--fps" not in argv
        assert argv[argv.index("--duration") + 1] == "5s"
        assert argv[argv.index("--res") + 1] == "720p"

    def test_generate_flow_audio_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["audio-only", "beep.wav", "silence", "left", "2s"])
        argv = interactive.generate_flow()
        assert argv == [
            "generate", "--audio", "silence", "--audio-layout", "left",
            "--duration", "2s", "-o", "beep.wav",
        ]  # fmt: skip

    def test_audio_flow_rejects_video_extension(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["beep.mp4", "beep.wav", "", "", ""])
        argv = interactive.audio_flow()
        assert argv[-2:] == ["-o", "beep.wav"]

    def test_generate_flow_picture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["picture", "testsrc", "1080p", "SCENE 1", "", "", "card.png"])
        argv = interactive.generate_flow()
        assert argv == [
            "generate", "--pattern", "testsrc", "--res", "1080p",
            "--text", "SCENE 1", "-o", "card.png",
        ]  # fmt: skip

    def test_caption_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "Take 42", "top", "", "cap.mp4"])
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

    def test_format_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "gif", "out.gif"])
        assert interactive.format_flow() == ["format", media_file, "-o", "out.gif"]

    def test_format_flow_audio_extract(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "mp3", "out.mp3"])
        assert interactive.format_flow() == ["format", media_file, "-o", "out.mp3"]

    def test_attach_flow_all(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str, tmp_path: Path
    ) -> None:
        aud = tmp_path / "a.m4a"
        aud.write_bytes(b"x")
        srt = tmp_path / "s.srt"
        srt.write_text("x")
        Script(monkeypatch, [media_file, str(aud), str(srt), True, "out.mkv"])
        argv = interactive.attach_flow()
        assert argv[:2] == ["attach", media_file]
        assert argv[argv.index("--audio") + 1] == str(aud)
        assert argv[argv.index("--subs") + 1] == str(srt)
        assert "--burn" in argv
        assert argv[-2:] == ["-o", "out.mkv"]

    def test_attach_flow_skips_optional(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str, tmp_path: Path
    ) -> None:
        aud = tmp_path / "a.m4a"
        aud.write_bytes(b"x")
        Script(monkeypatch, [media_file, str(aud), "", "out.mp4"])
        argv = interactive.attach_flow()
        assert "--audio" in argv
        assert "--subs" not in argv and "--burn" not in argv

    def test_ask_optional_file_reprompts(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, ["/nope.m4a", media_file])
        assert interactive.ask_optional_file("Audio") == media_file

    def test_variants_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "30,60", "720p", "grid"])
        argv = interactive.matrix_flow()
        assert argv == ["variants", media_file, "--fps", "30,60", "--res", "720p", "-o", "grid"]

    def test_wizard_dispatch(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, ["info", media_file])
        assert interactive.wizard() == ["info", media_file]

    def test_wizard_default_action_is_generate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def fake_ask(label: str = "", **kwargs: object) -> str:
            if label.startswith("What do you want"):
                seen.update(kwargs)
            return str(kwargs.get("default") or "test.mp4")

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        monkeypatch.setattr(interactive.Confirm, "ask", staticmethod(lambda *a, **k: False))
        interactive.wizard()
        assert seen["default"] == "generate"
        assert interactive.ACTIONS[0] == "generate"


class TestContainerConstraints:
    """The wizard offers only what the chosen output format can make."""

    def test_codec_choices_limited_to_container(self) -> None:
        assert interactive._codec_choices("out.webm") == ["auto", "vp9"]
        assert interactive._codec_choices("out.ogv") == ["auto", "theora"]
        mp4 = interactive._codec_choices("out.mp4")
        assert "prores" not in mp4 and "h264" in mp4

    def test_codec_choices_unrestricted_container(self) -> None:
        assert interactive._codec_choices("out.mkv") == ["auto", *interactive.KNOWN_CODECS]

    def test_layout_choices_drops_over_cap(self) -> None:
        assert interactive._layout_choices("out.mp3") == ["mono", "stereo", "left", "right"]
        assert "7.1" not in interactive._layout_choices("out.mpg")
        assert interactive._layout_choices("out.mp4") == interactive.AUDIO_CHANNEL_CHOICES

    def test_fps_parser_enforces_container_limit(self) -> None:
        parse = interactive._fps_parser("out.mxf")
        with pytest.raises(interactive.VidfixError):
            parse("15")
        parse("30")

    def test_convert_to_webm_offers_only_vp9(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        seen: list[object] = []

        def fake_ask(label: str = "", **kwargs: object) -> object:
            if label.startswith("Which file"):
                return media_file
            if label.startswith("Output"):
                return "out.webm"
            if label == "Codec":
                seen.append(kwargs.get("choices"))
                return "auto"
            default = kwargs.get("default")
            return default if default is not None else "none"

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        monkeypatch.setattr(interactive.Confirm, "ask", staticmethod(lambda *a, **k: False))
        interactive.convert_flow()
        assert seen == [["auto", "vp9"]]


class TestCaptionPrompt:
    def test_full_caption_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["Hello", "top-left", "yellow"])
        assert interactive.ask_caption_flags() == [
            "--text", "Hello", "--position", "top-left", "--color", "yellow",
        ]  # fmt: skip

    def test_defaults_omit_position_and_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["Hi", "bottom", "white"])
        assert interactive.ask_caption_flags() == ["--text", "Hi"]

    def test_blank_text_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, [""])
        assert interactive.ask_caption_flags() == []

    def test_nine_positions_offered(self) -> None:
        assert len(interactive.POSITION_CHOICES) == 9


class TestAskSpecRequired:
    def test_blank_reprompts_when_not_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["", "30"])
        assert interactive.ask_spec("fps", interactive.parse_fps, optional=False) == "30"
