"""Unit tests for the interactive wizard flows (prompts stubbed, no FFmpeg)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vidfix import interactive


class Script:
    """Feed canned answers to rich prompts in order."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answers: list[str | bool]) -> None:
        self.answers = list(answers)

        def next_answer(*args: object, default: object = None, **kwargs: object) -> object:
            value = self.answers.pop(0)
            if isinstance(value, bool):
                value = "yes" if value else "no"
            return default if value == "" and default not in (None, "") else value

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(next_answer))


@pytest.fixture()
def media_file(tmp_path: Path) -> str:
    path = tmp_path / "in.mp4"
    path.write_bytes(b"x")
    return str(path)


class Spy:
    """Record what each choose() menu offered, then answer like the real one."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.menus: dict[str, tuple[list[str], dict[str, str]]] = {}
        real = interactive.choose

        def spy(label: str, choices: list[str], **kwargs: object) -> str:
            self.menus[label] = (list(choices), dict(kwargs.get("hints") or {}))  # type: ignore[call-overload]
            return real(label, choices, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(interactive, "choose", spy)


class TestAskSpec:
    def test_menu_offers_common_values_and_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, [""])
        assert (
            interactive.ask_spec("fps", interactive.parse_fps, ["25", "30"], default="30") == "30"
        )
        assert spy.menus["fps"][0] == ["25", "30"]

    def test_own_value_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["23.976"])
        assert interactive.ask_spec("fps", interactive.parse_fps, ["25", "30"]) == "23.976"

    def test_bad_own_value_reprompts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["fast", "2"])
        assert interactive.ask_spec("fps", interactive.parse_fps, ["25", "30"]) == "25"

    def test_skip_entry_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, [""])
        assert interactive.ask_spec("fps", interactive.parse_fps, ["25"], skip="keep") is None
        assert spy.menus["fps"][0][0] == "keep"

    def test_preset_entry_names_its_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, [""])
        got = interactive.ask_spec("fps", interactive.parse_fps, ["25"], preset_value="29.97")
        assert got is None
        choices, hints = spy.menus["fps"]
        assert choices[0] == "preset" and "29.97" in hints["preset"]

    def test_container_limits_filter_options(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, [""])
        interactive.ask_spec("fps", interactive._fps_parser("o.mxf"), ["12", "25"], default="25")
        assert spy.menus["fps"][0] == ["25"]


class TestGenerateFlowPresetHints:
    def test_fps_menu_keeps_preset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(
            monkeypatch,
            ["", "out.mp4", "smpte", "df30", "", "", "", "", "tone", "stereo", "", False],
        )
        interactive.generate_flow()
        choices, hints = spy.menus["fps"]
        assert choices[0] == "preset" and "29.97" in hints["preset"]
        assert spy.menus["Duration"][0][0] != "preset"

    def test_convert_menus_offer_keep_source(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        spy = Spy(monkeypatch)
        Script(
            monkeypatch,
            [media_file, "out.mp4", "none", "", "", "", "h264", "keep", "keep", "", False],
        )
        interactive.convert_flow()
        for label in ("Target fps", "Target duration", "Target resolution"):
            assert spy.menus[label][0][0] == "keep"


class TestConvertFlow:
    def test_full_answers(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(
            monkeypatch,
            [
                media_file,
                "out.mp4",
                "df60",
                "",
                "30s",
                "720p",
                "",
                "",
                "",
                "",
                "keep",
                "5.1",
                "",
                False,
            ],
        )
        argv = interactive.convert_flow()
        assert argv == [
            "convert", media_file, "--preset", "df60", "--duration", "30s",
            "--res", "720p", "--audio-layout", "5.1", "-o", "out.mp4",
        ]  # fmt: skip

    def test_preset_skips_codec_prompt(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "out.mp4", "df60", "", "", "", "", "keep", "", "", False])
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
            [
                "/nope.mp4",
                media_file,
                "out.mp4",
                "none",
                "",
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
        assert argv[1] == media_file


class TestOtherFlows:
    def test_generate_flow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(
            monkeypatch,
            [
                "",
                "bars.mp4",
                "smpte",
                "df30",
                "",
                "10s",
                "1080p",
                "",
                "",
                "",
                "HELLO",
                "",
                "",
                "",
                "",
                True,
            ],
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
        Script(monkeypatch, ["", "out.mp4", "smpte", "df30", "", "", "", "", "", "", "", False])
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

    def test_audio_flow_offers_only_audio_formats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["mp4", "beep.wav", "", "", ""])
        argv = interactive.audio_flow()
        assert argv[-2:] == ["-o", "beep.wav"]

    def test_generate_flow_picture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["picture", "testsrc", "1080p", "SCENE 1", "", "", "", "card.png"])
        argv = interactive.generate_flow()
        assert argv == [
            "generate", "--pattern", "testsrc", "--res", "1080p",
            "--text", "SCENE 1", "-o", "card.png",
        ]  # fmt: skip

    def test_caption_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "Take 42", "top", "", "", "", "cap.mp4"])
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
        Script(monkeypatch, [media_file, str(aud), "", str(srt), True, "out.mkv"])
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
        Script(monkeypatch, [media_file, str(aud), "", "", "out.mp4"])
        argv = interactive.attach_flow()
        assert "--audio" in argv
        assert "--subs" not in argv and "--burn" not in argv

    def test_attach_flow_two_audios(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str, tmp_path: Path
    ) -> None:
        a1, a2 = tmp_path / "en.wav", tmp_path / "hi.mp3"
        a1.write_bytes(b"x")
        a2.write_bytes(b"x")
        Script(monkeypatch, [media_file, str(a1), str(a2), "", "", "out.mkv"])
        argv = interactive.attach_flow()
        assert [argv[i + 1] for i, a in enumerate(argv) if a == "--audio"] == [str(a1), str(a2)]

    def test_attach_flow_subs_only(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str, tmp_path: Path
    ) -> None:
        srt = tmp_path / "s.srt"
        srt.write_text("x")
        Script(monkeypatch, [media_file, "", str(srt), False, "out.mkv"])
        argv = interactive.attach_flow()
        assert "--audio" not in argv
        assert argv[argv.index("--subs") + 1] == str(srt)

    def test_ask_optional_file_reprompts(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(monkeypatch, ["/nope.m4a", media_file])
        assert interactive.ask_optional_file("Audio", {".m4a"}) == media_file

    def test_variants_flow(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "30,60", "720p", "grid"])
        argv = interactive.matrix_flow()
        assert argv == ["variants", media_file, "--fps", "30,60", "--res", "720p", "-o", "grid"]

    def test_wizard_dispatch(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, ["info", media_file, "run"])
        assert interactive.wizard() == ["info", media_file]

    def test_wizard_default_action_is_generate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, object] = {}

        def fake_ask(label: str = "", **kwargs: object) -> str:
            if "· " + "What do you want" in label:
                seen.update(kwargs)
            return str(kwargs.get("default") or "test.mp4")

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
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
            if "· " + "Which file" in label:
                return media_file
            if "· " + "Output file" in label:
                return "out.webm"
            default = kwargs.get("default")
            return default if default is not None else "none"

        real_choose = interactive.choose

        def spy(label: str, choices: list[str], **kwargs: object) -> str:
            if label == "Codec":
                seen.append(choices)
            return real_choose(label, choices, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(interactive, "choose", spy)
        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        interactive.convert_flow()
        assert seen == [["auto", "vp9"]]


class TestCaptionPrompt:
    def test_full_caption_flags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["Hello", "top-left", "yellow", "", ""])
        assert interactive.ask_caption_flags() == [
            "--text", "Hello", "--position", "top-left", "--color", "yellow",
        ]  # fmt: skip

    def test_defaults_omit_position_and_color(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["Hi", "bottom", "white", "", ""])
        assert interactive.ask_caption_flags() == ["--text", "Hi"]

    def test_blank_text_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, [""])
        assert interactive.ask_caption_flags() == []

    def test_nine_positions_offered(self) -> None:
        assert len(interactive.POSITION_CHOICES) == 9


class TestAskSpecRequired:
    def test_blank_reprompts_when_not_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["", "30"])
        assert interactive.ask_spec("fps", interactive.parse_fps, ["25"], optional=False) == "30"


class TestOutputMenu:
    def test_one_menu_of_names_common_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, [""])
        out = interactive.ask_output("test.mp4", suggest=interactive.ENCODE_EXTS)
        assert out == "test.mp4"
        choices, hints = spy.menus["Output file"]
        assert choices[:3] == ["test.mp4", "test.mov", "test.mkv"] and "test.mxf" in choices
        assert hints["test.mov"] == "Apple / editing"

    def test_pick_by_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["3"])
        assert interactive.ask_output("t.mp4", suggest=interactive.ENCODE_EXTS) == "t.mkv"

    def test_bare_format_renames_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["mxf"])
        out = interactive.ask_output("test_converted.mp4", suggest=interactive.ENCODE_EXTS)
        assert out == "test_converted.mxf"

    def test_own_name_gets_default_extension(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["clip"])
        assert interactive.ask_output("t.mov", suggest=interactive.ENCODE_EXTS) == "clip.mov"

    def test_typed_known_extension_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["final.mkv"])
        assert interactive.ask_output("t.mp4", suggest=interactive.ENCODE_EXTS) == "final.mkv"

    def test_unknown_dot_in_name_keeps_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["take.v2"])
        assert interactive.ask_output("t.mp4", suggest=interactive.ENCODE_EXTS) == "take.v2.mp4"

    @pytest.mark.parametrize("bad", ["beep.mp4", "mp4", "  "])
    def test_wrong_format_or_blank_reprompts(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bad: str
    ) -> None:
        Script(monkeypatch, [bad, "beep"])
        assert interactive.ask_output("t.wav", suggest={".wav", ".mp3"}) == "beep.wav"
        out = capsys.readouterr().out
        assert "This step writes" in out or "Give the file a name" in out

    def test_single_format_still_a_menu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, [""])
        assert interactive.ask_output("a/in.gif", suggest={".gif"}) == "a/in.gif"

    def test_gif_not_suggested_for_encode_flows(self) -> None:
        assert ".gif" not in interactive.ENCODE_EXTS
        assert ".mp4" in interactive.ENCODE_EXTS


class TestOutputHintPerFlow:
    """Every wizard flow with an output prompt lists the formats it can write."""

    def test_generate_video(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        Script(monkeypatch, ["", "bars.mp4", "smpte", "df30", "", "", "", "", "", "", "", False])
        interactive.generate_flow()
        out = capsys.readouterr().out
        assert "mkv" in out and "mxf" in out

    def test_audio_only(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        Script(monkeypatch, ["beep.wav", "", "", ""])
        interactive.audio_flow()
        out = capsys.readouterr().out
        assert "flac" in out and "opus" in out

    def test_picture(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        Script(monkeypatch, ["testsrc", "1080p", "", "card.png"])
        interactive.picture_flow()
        out = capsys.readouterr().out
        assert "png" in out and "tiff" in out

    def test_convert(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "out.mp4", "df60", "", "", "", "", "keep", "", "", False])
        interactive.convert_flow()
        assert "mxf" in capsys.readouterr().out

    def test_caption(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], media_file: str
    ) -> None:
        Script(monkeypatch, [media_file, "Take 42", "top", "", "", "", "cap.mp4"])
        interactive.caption_flow()
        assert "mxf" in capsys.readouterr().out

    def test_attach(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        media_file: str,
        tmp_path: Path,
    ) -> None:
        aud = tmp_path / "a.m4a"
        aud.write_bytes(b"x")
        Script(monkeypatch, [media_file, str(aud), "", "", "out.mp4"])
        interactive.attach_flow()
        assert "mxf" in capsys.readouterr().out


class TestAnswersCheckedAtThePrompt:
    """Bad wizard answers are caught at the prompt, not after the last question."""

    def test_caption_color_reprompts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from vidfix.exceptions import InvalidSpecError

        def check(color: str, runner: object) -> None:
            if color == "nope":
                raise InvalidSpecError("Unknown color 'nope'")

        monkeypatch.setattr(interactive, "validate_color", check)
        Script(monkeypatch, ["hi", "top", "nope", "yellow", "", ""])
        assert interactive.ask_caption_flags() == [
            "--text", "hi", "--position", "top", "--color", "yellow",
        ]  # fmt: skip

    @pytest.mark.parametrize(
        ("source", "first", "has_mp4"),
        [("a.png", "png", False), ("a.wav", "wav", False), ("a.mp4", "mp4", True),
         ("a.xyz", "mp4", True)],
    )  # fmt: skip
    def test_format_targets_follow_source(self, source: str, first: str, has_mp4: bool) -> None:
        targets = interactive._format_targets(source)
        assert targets[0] == first
        assert ("mp4" in targets) is has_mp4

    def test_verify_needs_one_spec(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, [media_file, "", "", "", "30", "", ""])
        assert interactive.verify_flow() == ["verify", media_file, "--fps", "30"]

    def test_convert_skips_channels_for_silent_source(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        monkeypatch.setattr(interactive, "_has_audio", lambda source: False)
        Script(monkeypatch, [media_file, "o.mp4", "none", "", "", "", "auto", "keep", "", False])
        assert interactive.convert_flow() == ["convert", media_file, "-o", "o.mp4"]

    def test_has_audio_unreadable_assumes_yes(self, media_file: str) -> None:
        assert interactive._has_audio(media_file) is True


class TestMenus:
    """Arrow-key menu in a terminal, numbered list elsewhere, steps, summary, run/open/cancel."""

    def test_number_picks_choice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["2"])
        assert interactive.choose("Audio", ["tone", "silence", "none"], default="tone") == "silence"

    def test_bad_answer_reprompts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["9", "loud", "none"])
        assert interactive.choose("Audio", ["tone", "silence", "none"]) == "none"

    def test_steps_count_questions_not_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        labels: list[str] = []
        answers = iter(["x", "tone", "stereo"])

        def fake_ask(label: str = "", **kwargs: object) -> str:
            labels.append(label)
            return next(answers)

        monkeypatch.setattr(interactive.Prompt, "ask", staticmethod(fake_ask))
        interactive._STEP[0] = 0
        interactive.choose("Audio", ["tone", "none"])
        interactive.choose("Audio channels", ["mono", "stereo"])
        assert labels == ["Step 1 · Audio", "Step 1 · Audio", "Step 2 · Audio channels"]

    def test_terminal_uses_arrow_menu(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary

        seen: dict[str, object] = {}

        class Menu:
            def ask(self) -> str:
                return "stereo"

        def fake_select(label: str, **kwargs: object) -> Menu:
            seen.update(kwargs, label=label)
            return Menu()

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "select", fake_select)
        assert (
            interactive.choose("Audio channels", ["mono", "stereo"], default="stereo") == "stereo"
        )
        assert seen["default"] == "stereo"
        titles = [c.title for c in seen["choices"]]  # type: ignore[attr-defined]
        assert titles[0][1] == ("class:hint", "one speaker")

    def test_terminal_ctrl_c_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary
        import typer

        class Menu:
            def ask(self) -> None:
                return None

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "select", lambda *a, **k: Menu())
        with pytest.raises(typer.Abort):
            interactive.choose("Audio", ["tone"])

    def test_is_terminal_false_under_pytest(self) -> None:
        assert interactive._is_terminal() is False

    def test_summary_rows(self) -> None:
        from rich.console import Console

        argv = ["attach", "in.mp4", "--audio", "a.wav", "--burn", "-o", "out.mp4"]
        console = Console(record=True, width=80)
        console.print(interactive.summary(argv))
        text = console.export_text()
        for part in (
            "Ready to attach",
            "input",
            "in.mp4",
            "audio",
            "a.wav",
            "burn",
            "yes",
            "output",
            "out.mp4",
        ):
            assert part in text  # fmt: skip

    def test_run_and_open_adds_flag(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        Script(monkeypatch, ["format", media_file, "png", "", "run & open"])
        argv = interactive.wizard()
        assert argv[-1] == "--open" and argv[0] == "format"

    def test_read_only_commands_skip_open(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        offered: list[list[str]] = []
        real_choose = interactive.choose

        def spy(label: str, choices: list[str], **kwargs: object) -> str:
            offered.append(choices)
            return real_choose(label, choices, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(interactive, "choose", spy)
        Script(monkeypatch, ["info", media_file, "run"])
        interactive.wizard()
        assert offered[-1] == ["run", "cancel"]

    def test_cancel_writes_nothing(self, monkeypatch: pytest.MonkeyPatch, media_file: str) -> None:
        import typer

        Script(monkeypatch, ["info", media_file, "cancel"])
        with pytest.raises(typer.Exit):
            interactive.wizard()


class TestOwnValueAndYesNo:
    def test_terminal_other_entry_types_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary

        class Menu:
            def ask(self) -> str:
                return interactive.OTHER

        checks: list[object] = []

        class Text:
            def ask(self) -> str:
                return "45s"

        def fake_text(label: str, **kwargs: object) -> Text:
            validate = kwargs["validate"]
            checks.append((validate("soon"), validate("45s")))  # type: ignore[operator]
            return Text()

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "select", lambda *a, **k: Menu())
        monkeypatch.setattr(questionary, "text", fake_text)
        got = interactive.ask_spec("Duration", interactive.parse_duration, ["5s"], default="5s")
        assert got == "45s"
        bad, good = checks[0]  # type: ignore[misc]
        assert "Cannot parse duration" in bad and good is True

    @pytest.mark.parametrize(
        ("answer", "value"), [("", False), ("2", True), ("y", True), ("N", False)]
    )
    def test_confirm(self, monkeypatch: pytest.MonkeyPatch, answer: str, value: bool) -> None:
        Script(monkeypatch, [answer])
        assert interactive.confirm("Burn in?") is value

    def test_confirm_reprompts_nonsense(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["maybe", "yes"])
        assert interactive.confirm("Burn in?") is True


class TestFileAndColorMenus:
    def test_files_in_folder_listed_newest_first(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import os

        for i, name in enumerate(["old.mp4", "new.mov", "notes.txt", "subs.srt"]):
            (tmp_path / name).write_bytes(b"x" * 1000)
            os.utime(tmp_path / name, (i, i))
        monkeypatch.chdir(tmp_path)
        found = interactive._nearby(interactive.VIDEO_EXTS)
        assert list(found) == ["new.mov", "old.mp4"]
        assert found["new.mov"] == "video · 1 KB"
        assert interactive._size(2_500_000) == "2.5 MB"
        assert interactive._nearby(interactive.SUBTITLE_EXTS)["subs.srt"].startswith("subtitles")

    def test_pick_file_by_number(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "clip.mp4").write_bytes(b"x")
        monkeypatch.chdir(tmp_path)
        Script(monkeypatch, ["1"])
        assert interactive.ask_file("Which file?") == "clip.mp4"

    def test_no_files_nearby_types_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, media_file: str
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.chdir(empty)
        Script(monkeypatch, ["/nope.mp4", media_file])
        assert interactive.ask_file("Which file?") == media_file

    def test_optional_file_skip(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.chdir(tmp_path)
        Script(monkeypatch, [""])
        assert interactive.ask_optional_file("Audio", {".wav"}) is None

    def test_color_menu_and_own_hex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(interactive, "validate_color", lambda color, runner: None)
        Script(monkeypatch, ["hi", "", "#00ff00", "", ""])
        assert interactive.ask_caption_flags() == ["--text", "hi", "--color", "#00ff00"]

    def test_variants_comma_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["", "24,abc", "24,23.976"])
        assert interactive.choose_many("fps", ["24"], ["30"], interactive.parse_fps) == "30"
        assert interactive.choose_many("fps", ["24"], ["30"], interactive.parse_fps) == "24,23.976"

    def test_variants_empty_reprompts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, [" , ", "720p"])
        assert interactive.choose_many("res", [], ["720p"], interactive.parse_resolution) == "720p"

    def test_variants_checkboxes_plus_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary

        seen: dict[str, object] = {}

        class Boxes:
            def ask(self) -> list[str]:
                return ["25"]

        def fake_checkbox(label: str, **kwargs: object) -> Boxes:
            seen.update(kwargs)
            return Boxes()

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "checkbox", fake_checkbox)

        class Extra:
            def ask(self) -> str:
                return "23.976"

        monkeypatch.setattr(questionary, "text", lambda *a, **k: Extra())
        got = interactive.choose_many("fps", ["25", "30"], ["30"], interactive.parse_fps)
        assert got == "25,23.976"
        checked = {c.title: c.checked for c in seen["choices"]}  # type: ignore[attr-defined]
        assert checked == {"25": False, "30": True}

    def test_variants_checkbox_ctrl_c(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary
        import typer

        class Boxes:
            def ask(self) -> None:
                return None

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "checkbox", lambda *a, **k: Boxes())
        with pytest.raises(typer.Abort):
            interactive.choose_many("fps", ["25"], [], interactive.parse_fps)


class TestTerminalLook:
    def test_answer_line_shows_value_only(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import questionary

        seen: dict[str, object] = {}

        class Menu:
            def ask(self) -> str:
                return "mp4"

        def fake_select(label: str, **kwargs: object) -> Menu:
            seen.update(kwargs)
            return Menu()

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "select", fake_select)
        interactive._STEP[0] = 2
        interactive.choose("Output format", ["mp4", "mov"])
        out = capsys.readouterr().out
        assert "✓ Step 3 · Output format  mp4" in out
        assert "plays everywhere" not in out
        assert seen["erase_when_done"] is True

    def test_typed_answer_same_look(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import questionary

        seen: dict[str, object] = {}

        class Text:
            def ask(self) -> str:
                return "fixture"

        def fake_text(label: str, **kwargs: object) -> Text:
            seen.update(kwargs, label=label)
            return Text()

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "text", fake_text)
        got = interactive.ask_text("Caption text [dim](enter to skip)[/dim]", default="x")
        assert got == "fixture"
        assert seen["label"] == "Caption text (enter to skip)" and seen["default"] == "x"
        assert "✓ Caption text  fixture" in capsys.readouterr().out

    def test_typed_ctrl_c_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import questionary
        import typer

        class Text:
            def ask(self) -> None:
                return None

        monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
        monkeypatch.setattr(questionary, "text", lambda *a, **k: Text())
        with pytest.raises(typer.Abort):
            interactive.ask_text("File name")


class TestEveryOptionAsked:
    """The wizard reaches every CLI option, but only asks when it matters."""

    def test_convert_advanced_options(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        Script(
            monkeypatch,
            [media_file, "out.mp4", "none", "50", "10s", "720p",
             "yes", "loop", "yes", "stretch", "auto", "keep", "keep", "", "no"],
        )  # fmt: skip
        argv = interactive.convert_flow()
        for flag in ("--smooth", "--precise", "--stretch"):
            assert flag in argv
        assert argv[argv.index("--extend-mode") + 1] == "loop"

    def test_convert_skips_advanced_when_unchanged(
        self, monkeypatch: pytest.MonkeyPatch, media_file: str
    ) -> None:
        spy = Spy(monkeypatch)
        Script(
            monkeypatch,
            [media_file, "out.mp4", "none", "", "", "", "auto", "keep", "keep", "", ""],
        )
        interactive.convert_flow()
        assert "Fit to the new size" not in spy.menus
        assert "If the new length is longer than the source" not in spy.menus

    def test_generate_asks_codec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["", "o.mkv", "", "none", "", "", "", "h265", "", "", "", ""])
        argv = interactive.generate_flow()
        assert argv[argv.index("--codec") + 1] == "h265"

    def test_preset_with_codec_skips_codec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = Spy(monkeypatch)
        Script(monkeypatch, ["", "o.mp4", "", "web-720p", "", "", "", "", "", "", ""])
        argv = interactive.generate_flow()
        assert "Codec" not in spy.menus and "--codec" not in argv

    def test_caption_size_and_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["hi", "", "", "large", "part of it", "x", "3", "1", "1", "2.5"])
        assert interactive.ask_caption_flags() == [
            "--text", "hi", "--size", "h/8", "--start", "1", "--end", "2.5",
        ]  # fmt: skip

    def test_caption_own_size(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["hi", "", "", "huge", "40", ""])
        assert interactive.ask_caption_flags() == ["--text", "hi", "--size", "40"]

    def test_picture_caption_has_no_timing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        Script(monkeypatch, ["hi", "", "", ""])
        assert interactive.ask_caption_flags(timing=False) == ["--text", "hi"]

    def test_seconds_rejects_negative(self) -> None:
        with pytest.raises(interactive.VidfixError, match="negative"):
            interactive._seconds("-1")


class TestTypeAhead:
    def test_menus_turn_off_cursor_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROMPT_TOOLKIT_NO_CPR", raising=False)
        import os

        interactive._menus()
        assert os.environ["PROMPT_TOOLKIT_NO_CPR"] == "1"

    @pytest.mark.skipif(sys.platform == "win32", reason="termios is POSIX-only")
    def test_posix_flushes_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        import termios

        flushed: list[object] = []

        class In:
            def fileno(self) -> int:
                return 0

        monkeypatch.setattr(sys, "stdin", In())
        monkeypatch.setattr(termios, "tcflush", lambda fd, how: flushed.append((fd, how)))
        interactive._drop_typeahead()
        assert flushed == [(0, termios.TCIFLUSH)]

    def test_windows_drains_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys
        import types

        keys = ["\r", "x"]
        fake = types.SimpleNamespace(kbhit=lambda: bool(keys), getwch=lambda: keys.pop(0))
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setitem(sys.modules, "msvcrt", fake)
        interactive._drop_typeahead()
        assert keys == []


def test_yes_no_menu_has_no_other_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    import questionary

    seen: dict[str, object] = {}

    class Menu:
        def ask(self) -> str:
            return "yes"

    def fake_select(label: str, **kwargs: object) -> Menu:
        seen.update(kwargs)
        return Menu()

    monkeypatch.setattr(interactive, "_is_terminal", lambda: True)
    monkeypatch.setattr(questionary, "select", fake_select)
    assert interactive.confirm("Burn in?") is True
    assert [c.value for c in seen["choices"]] == ["no", "yes"]  # type: ignore[attr-defined]


def test_answered_line_drops_asking_hints(capsys: pytest.CaptureFixture[str]) -> None:
    interactive._answered("Step 8 · Duration — type it", "45s")
    interactive._answered("Step 9 · Smooth motion between frames? (slower)", "no")
    out = capsys.readouterr().out
    assert "✓ Step 8 · Duration  45s" in out
    assert "✓ Step 9 · Smooth motion between frames?  no" in out


def test_summary_uses_plain_names() -> None:
    from rich.console import Console

    console = Console(record=True, width=80)
    console.print(
        interactive.summary(
            ["generate", "--res", "720p", "--text", "hi", "--audio-layout", "5.1", "-o", "a.mp4"]
        )
    )
    text = console.export_text()
    for part in ("resolution", "caption", "audio channels", "output"):
        assert part in text
