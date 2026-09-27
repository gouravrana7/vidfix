"""Interactive wizard: build a vidfix command by answering prompts.

Runs when ``vidfix`` is invoked with no subcommand. Every answer is validated
immediately with the same parsers the flags use, so no syntax mistakes survive.
Each flow returns an argv list; the wizard shows a summary and the equivalent
command (so you learn the syntax) and then executes it.

In a real terminal, lists are arrow-key menus; elsewhere (pipes, CI) they fall
back to numbered choices that accept the number or the name.
"""

from __future__ import annotations

import contextlib
import os
import re
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from vidfix.core.attach import SUBTITLE_EXTS
from vidfix.core.capabilities import allowed_codecs, max_channels
from vidfix.core.caption import POSITIONS, validate_color
from vidfix.core.duration import DROP_FRAME_RATES, parse_duration, parse_fps, parse_resolution
from vidfix.core.ffmpeg import FFmpegRunner
from vidfix.core.formats import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS, media_kind
from vidfix.core.generate import AUDIO_EXTENSIONS, AUDIO_LAYOUTS
from vidfix.core.presets import get_preset, load_presets
from vidfix.core.probe import probe
from vidfix.exceptions import InvalidSpecError, VidfixError

console = Console()

ACTIONS = ("generate", "convert", "caption", "attach", "format", "verify", "info", "variants")

ENCODE_EXTS = VIDEO_EXTS - {".gif"}

AUDIO_CHANNEL_CHOICES = ["mono", "stereo", "5.1", "7.1", "left", "right"]

KNOWN_CODECS = ["h264", "h265", "prores", "vp9", "mpeg2", "theora"]

POSITION_CHOICES = list(POSITIONS)

COLOR_CHOICES = ["white", "yellow", "black", "red", "green", "blue", "orange"]

MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS | AUDIO_EXTS

HINTS: dict[str, str] = {
    "generate": "make a test video, audio or picture",
    "convert": "change fps / length / size of a video",
    "caption": "burn text onto a video",
    "attach": "add audio tracks or subtitles",
    "format": "turn a file into another format",
    "verify": "check a file matches specs",
    "info": "show what's inside a file",
    "variants": "many fps x size copies at once",
    "video": "moving picture with sound",
    "audio-only": "just sound (wav, mp3, …)",
    "picture": "one still image (png, jpg, …)",
    "smpte": "classic TV color bars",
    "color-bars": "HD color bars",
    "testsrc": "moving pattern with a counter",
    "gradient": "smooth moving colors",
    "solid:red": "plain red screen",
    "keep": "leave it as it is in the source",
    "tone": "a steady beep (440 Hz)",
    "silence": "a silent track",
    "none": "no audio at all",
    "mono": "one speaker",
    "stereo": "left + right",
    "5.1": "surround",
    "7.1": "big surround",
    "left": "sound only on the left",
    "right": "sound only on the right",
    "center": "middle of the picture",
    "auto": "best fit for the chosen format",
    "h264": "plays everywhere",
    "h265": "smaller files, newer devices",
    "prores": "editing / pro video",
    "vp9": "web video",
    "mpeg2": "broadcast / DVD",
    "theora": "open web video (ogv)",
    "mp4": "plays everywhere",
    "mov": "Apple / editing",
    "mkv": "holds anything",
    "webm": "web video",
    "avi": "older Windows video",
    "mxf": "broadcast",
    "mpg": "DVD-style video",
    "ogv": "open web video",
    "flv": "old Flash video",
    "wmv": "Windows Media",
    "3gp": "old phones",
    "gif": "animated picture, no sound",
    "png": "sharp picture, no loss",
    "jpg": "small picture",
    "webp": "modern web picture",
    "bmp": "uncompressed picture",
    "tiff": "print / archive picture",
    "wav": "uncompressed sound",
    "mp3": "plays everywhere",
    "m4a": "Apple sound",
    "flac": "sound, no loss",
    "ogg": "open sound format",
    "opus": "small, high-quality sound",
    "aac": "plain AAC sound",
    "run": "make it now",
    "run & open": "make it, then open the result",
    "cancel": "stop — nothing is written",
    "freeze": "hold the last frame",
    "loop": "play it again from the start",
    "pad": "keep the shape, add black bars",
    "stretch": "fill the frame, may squash",
    "small": "h/18 of the picture height",
    "medium": "h/12 of the picture height",
    "large": "h/8 of the picture height",
    "whole video": "show it the whole time",
    "part of it": "pick when it starts and ends",
    "no": "",
    "yes": "",
    "mpeg": "DVD-style video",
    "ts": "TV / streaming",
    "m4v": "Apple video",
    "jpeg": "small picture",
    "tif": "print / archive picture",
}

_STEP = [0]


def _step(label: str) -> str:
    """Number each question: 'Step 3 · Audio'. Call once per question, not per retry."""
    _STEP[0] += 1
    return f"Step {_STEP[0]} · {label}"


def _is_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _drop_typeahead() -> None:
    """Throw away keys pressed before a question showed.

    A stray Enter left in the terminal (some terminals leave one after launching
    vidfix, or a quick double Enter) would otherwise pick the default unseen.
    """
    if sys.platform == "win32":
        import msvcrt

        while msvcrt.kbhit():
            msvcrt.getwch()
        return
    import termios

    with contextlib.suppress(termios.error, OSError, ValueError):
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)


def _menus() -> ModuleType:
    """questionary, ready for a question: stray keys dropped, cursor-position checks off.

    prompt_toolkit asks the terminal where the cursor is and gives up after 2 s;
    on some terminals that timeout picked the highlighted choice by itself.
    These menus don't need the answer, so the check is switched off.
    """
    os.environ.setdefault("PROMPT_TOOLKIT_NO_CPR", "1")
    _drop_typeahead()
    import questionary

    return questionary


def _answered(label: str, answer: str) -> None:
    """One clean line per answered question: ✓, the question, the answer.

    Asking-time hints ("(enter to skip)", "— type it") are dropped from it.
    """
    plain = re.sub(r"\s*(\([^)]*\)|— type it)$", "", Text.from_markup(label).plain)
    console.print(
        Text.assemble(("✓ ", "bold green"), (plain, "bold"), "  ", (answer, "bold #FF9D00"))
    )


def _problem(check: Callable[[str], object] | None, raw: str) -> str | None:
    """The error message for ``raw``, or None when ``check`` accepts it."""
    if check is None:
        return None
    try:
        check(raw.strip())
    except VidfixError as exc:
        return str(exc)
    return None


def ask_text(label: str, default: str = "", check: Callable[[str], object] | None = None) -> str:
    """Typed answer, re-asked until ``check`` accepts it; ✓ only for an accepted one.

    In a terminal the error shows right under the box and the box stays open.
    """
    if _is_terminal():
        questionary = _menus()
        answer = questionary.text(
            Text.from_markup(label).plain,
            default=default,
            validate=lambda raw: _problem(check, raw) or True,
            erase_when_done=True,
        ).ask()
        if answer is None:
            raise typer.Abort()
        _answered(label, answer)
        return str(answer)
    while True:
        raw = Prompt.ask(label, default=default, show_default=bool(default))
        problem = _problem(check, raw)
        if problem is None:
            return raw
        console.print(f"[red]{problem}[/red]")


OTHER = "other…"


def _typed(label: str, parser: Callable[[str], object]) -> str:
    """Free-text answer, re-asked until ``parser`` accepts it."""
    return ask_text(f"{label} — type it", check=parser).strip()


def choose(
    label: str,
    choices: list[str],
    default: str | None = None,
    hints: dict[str, str] | None = None,
    other: Callable[[str], object] | None = None,
) -> str:
    """Pick one of ``choices``: arrow-key menu in a terminal, numbered list otherwise.

    With ``other`` (a parser), the user may also give their own value: an
    "other…" menu entry in a terminal, or any answer the parser accepts.
    """
    label = _step(label)
    meaning = {**HINTS, **(hints or {}), OTHER: "type your own value"}
    shown = [*choices, OTHER] if other else choices
    width = max(len(c) for c in shown) + 3
    if _is_terminal():
        questionary = _menus()
        menu = [
            questionary.Choice(
                title=[("", c.ljust(width)), ("class:hint", meaning.get(c, ""))], value=c
            )
            for c in shown
        ]
        answer = questionary.select(
            label,
            choices=menu,
            default=default,
            instruction="(↑↓ to move, enter to pick)",
            pointer="\u276f",
            style=questionary.Style([("hint", "fg:#888888")]),
            erase_when_done=True,
        ).ask()
        if answer is None:
            raise typer.Abort()
        if answer == OTHER and other is not None:
            return _typed(label, other)
        _answered(label, str(answer))
        return str(answer)
    if other is not None:
        console.print("  [dim]…or type your own value[/dim]")
    for number, choice in enumerate(choices, 1):
        console.print(
            f"  [cyan]{number})[/cyan] {choice.ljust(width)}[dim]{meaning.get(choice, '')}[/dim]"
        )
    while True:
        raw = Prompt.ask(label, default=default).strip() if default else Prompt.ask(label).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return choices[int(raw) - 1]
        if raw in choices:
            return raw
        if other is None:
            console.print("[red]Pick a number or a name from the list.[/red]")
            continue
        try:
            other(raw)
            return raw
        except VidfixError as exc:
            console.print(f"[red]{exc}[/red]")


SIZES = {"small": "h/18", "medium": "h/12", "large": "h/8"}


def _seconds(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        raise InvalidSpecError(f"Give seconds as a number, e.g. 2 or 1.5 (got {raw!r}).") from None
    if value < 0:
        raise InvalidSpecError("Seconds can't be negative.")
    return value


def _ask_seconds(label: str) -> str:
    return ask_text(_step(label), check=_seconds).strip()


def _size_ok(value: str) -> None:
    from vidfix.core.caption import caption_filter

    caption_filter("t.txt", size=value)


def ask_caption_flags(required: bool = False, timing: bool = True) -> list[str]:
    """Ask for caption text and, if given, placement, color, size and timing. Returns flags."""
    if required:
        text = ask_text(_step("Caption text"))
    else:
        text = ask_text(_step("Caption text [dim](enter to skip)[/dim]")).strip()
    if not text:
        return []
    position = choose("Caption position", POSITION_CHOICES, default="bottom")
    color = choose(
        "Caption color",
        COLOR_CHOICES,
        default="white",
        other=lambda value: validate_color(value, FFmpegRunner()),
    )
    size = choose("Caption size", list(SIZES), default="medium", other=_size_ok)
    flags = ["--text", text]
    if position != "bottom":
        flags += ["--position", position]
    if color != "white":
        flags += ["--color", color]
    if size != "medium":
        flags += ["--size", SIZES.get(size, size)]
    if timing and choose("Show caption", ["whole video", "part of it"], default="whole video") == (
        "part of it"
    ):
        while True:
            start, end = _ask_seconds("Caption starts at (seconds)"), _ask_seconds("…and ends at")
            if float(start) < float(end):
                break
            console.print("[red]The end has to come after the start.[/red]")
        flags += ["--start", start, "--end", end]
    return flags


def _layout_choices(output: str) -> list[str]:
    """Channel layouts the output format can actually carry."""
    cap = max_channels(output)
    if cap is None:
        return AUDIO_CHANNEL_CHOICES
    return [c for c in AUDIO_CHANNEL_CHOICES if AUDIO_LAYOUTS.get(c, 2) <= cap]


def _codec_choices(output: str) -> list[str]:
    """'auto' plus the codecs the output container can hold."""
    allowed = allowed_codecs(output)
    pick = KNOWN_CODECS if allowed is None else [c for c in KNOWN_CODECS if c in allowed]
    return ["auto", *pick]


def _fps_parser(output: str) -> Callable[[str], object]:
    """parse_fps plus the output format's frame-rate limit, so bad rates re-prompt."""
    from vidfix.core.capabilities import validate_fps

    def parse(raw: str) -> object:
        fps = parse_fps(raw)
        validate_fps(fps, output)
        return fps

    return parse


def _pretty_fps(value: str) -> str:
    """Rationals get their everyday name: 30000/1001 -> 29.97."""
    names = {str(v): k for k, v in DROP_FRAME_RATES.items()}
    return names.get(value, value)


FPS_OPTIONS = ["24", "25", "29.97", "30", "50", "59.94", "60"]

DURATION_OPTIONS = ["5s", "10s", "30s", "1min", "5min"]

RES_OPTIONS = ["480p", "720p", "1080p", "4k"]


def choose_many(
    label: str, options: list[str], defaults: list[str], parser: Callable[[str], object]
) -> str:
    """Several values: tick boxes (+ extra typed ones) in a terminal, a comma list otherwise."""
    label = _step(label)
    while True:
        if _is_terminal():
            questionary = _menus()
            picked = questionary.checkbox(
                label,
                choices=[questionary.Choice(o, checked=o in defaults) for o in options],
                instruction="(space to tick, enter when done)",
                pointer="\u276f",
                erase_when_done=True,
            ).ask()
            if picked is None:
                raise typer.Abort()
            _answered(label, ", ".join(picked) or "none")
            extra = ask_text("  any other values? comma-separated [dim](enter to skip)[/dim]")
            values = [*picked, *(v.strip() for v in extra.split(",") if v.strip())]
        else:
            raw = ask_text(f"{label} — comma-separated", default=",".join(defaults))
            values = [v.strip() for v in raw.split(",") if v.strip()]
        try:
            if not values:
                raise InvalidSpecError("Pick at least one value.")
            for value in values:
                parser(value)
            return ",".join(values)
        except VidfixError as exc:
            console.print(f"[red]{exc}[/red]")


def _accepts(parser: Callable[[str], object], value: str) -> bool:
    try:
        parser(value)
        return True
    except VidfixError:
        return False


def ask_spec(
    label: str,
    parser: Callable[[str], object],
    options: list[str],
    default: str = "",
    optional: bool = True,
    preset_value: str | None = None,
    skip: str = "skip",
) -> str | None:
    """Menu of common values (+ type-your-own); None when skipped / preset kept.

    ``skip`` names the leave-it-out entry: "skip" (verify) or "keep" (convert).
    Options the parser rejects (e.g. fps a container can't do) aren't offered.
    """
    valid = [o for o in options if _accepts(parser, o)]
    hints = {"skip": "leave this out"}
    leave_out: str | None = None
    if preset_value:
        leave_out = "preset"
        hints["preset"] = f"use the preset's value ({preset_value})"
    elif optional and not default:
        leave_out = skip
    choices = [leave_out, *valid] if leave_out else valid
    start = leave_out or (default if default in valid else None)
    answer = choose(label, choices, default=start, hints=hints, other=parser)
    return None if answer == leave_out else answer


def _yes_no(raw: str) -> bool:
    if raw.lower() in ("y", "yes", "n", "no"):
        return raw.lower().startswith("y")
    raise InvalidSpecError("Answer yes or no.")


def confirm(label: str) -> bool:
    """Yes/no as a menu (default no); y/n typed still works without a terminal."""
    typed = None if _is_terminal() else _yes_no
    return _yes_no(choose(label, ["no", "yes"], default="no", other=typed))


def _existing(raw: str) -> str:
    path = raw.strip().strip("'\"")
    if not Path(path).is_file():
        raise InvalidSpecError(f"File not found: {path}")
    return path


def _size(num_bytes: int) -> str:
    if num_bytes >= 1_000_000:
        return f"{num_bytes / 1_000_000:.1f} MB"
    return f"{max(1, round(num_bytes / 1000))} KB"


def _nearby(exts: set[str] | frozenset[str]) -> dict[str, str]:
    """Up to 12 matching files in the current folder, newest first -> 'video · 2.1 MB'."""
    files = [p for p in Path.cwd().iterdir() if p.is_file() and p.suffix.lower() in exts]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    found = {}
    for path in files[:12]:
        try:
            kind = media_kind(path.name)
        except VidfixError:
            kind = "subtitles"
        found[path.name] = f"{kind} · {_size(path.stat().st_size)}"
    return found


def ask_file(label: str, exts: set[str] | frozenset[str] = MEDIA_EXTS) -> str:
    """Pick a file from the current folder, or type any path."""
    files = _nearby(exts)
    if not files:
        return _existing(ask_text(_step(label), check=_existing))
    return _existing(choose(label, list(files), hints=files, other=_existing))


FORMAT_ORDER = [
    "mp4", "mov", "mkv", "webm", "avi", "mxf", "mpg", "mpeg", "ts", "m4v", "ogv", "flv",
    "wmv", "3gp", "gif", "png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif",
    "wav", "mp3", "m4a", "flac", "ogg", "opus", "aac",
]  # fmt: skip


def ask_output(default: str, suggest: set[str]) -> str:
    """One menu: the default name in every format this step can write, or type your own.

    A typed name keeps a known extension, gets the default one otherwise; a bare
    format ("mxf") renames the default.
    """
    exts = [f".{e}" for e in FORMAT_ORDER if f".{e}" in suggest]
    exts += sorted(suggest - set(exts))
    base = Path(default).with_suffix("")
    names = [f"{base}{e}" for e in exts]
    hints = {name: HINTS.get(ext.lstrip("."), "") for name, ext in zip(names, exts, strict=True)}
    start = default if default in names else names[0]

    def name_ok(raw: str) -> None:
        name = raw.strip().strip("'\"")
        if not name:
            raise InvalidSpecError("Give the file a name.")
        ext = Path(name).suffix.lower() or f".{name.lower()}"
        if ext in MEDIA_EXTS and ext not in suggest:
            raise InvalidSpecError(f"This step writes: {', '.join(e.lstrip('.') for e in exts)}.")

    raw = choose("Output file", names, default=start, hints=hints, other=name_ok)
    raw = raw.strip().strip("'\"")
    if f".{raw.lower()}" in suggest:
        return f"{base}.{raw.lower()}"
    return raw if Path(raw).suffix.lower() in suggest else f"{raw}{Path(start).suffix}"


def ask_preset() -> str | None:
    presets = load_presets()
    hints = {
        name: presets[name].get("description") or f"same as {presets[name].get('alias')}"
        for name in presets
    }
    hints["none"] = "pick the values yourself"
    choice = choose("Preset", ["none", *sorted(presets)], default="none", hints=hints)
    return None if choice == "none" else choice


def _opt(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def _has_audio(source: str) -> bool:
    """Whether the source carries audio (unreadable files: assume yes, convert reports)."""
    try:
        return probe(source).audio is not None
    except VidfixError:
        return True


def convert_flow() -> list[str]:
    source = ask_file("Which file do you want to convert?", ENCODE_EXTS)
    output = ask_output(
        str(Path(source).with_stem(Path(source).stem + "_converted")), suggest=ENCODE_EXTS
    )
    preset = ask_preset()
    pd = get_preset(preset) if preset else {}
    fps = ask_spec(
        "Target fps",
        _fps_parser(output),
        FPS_OPTIONS,
        preset_value=_pretty_fps(str(pd["fps"])) if "fps" in pd else None,
        skip="keep",
    )
    duration = ask_spec(
        "Target duration",
        parse_duration,
        DURATION_OPTIONS,
        preset_value=str(pd.get("duration") or "") or None,
        skip="keep",
    )
    res = ask_spec(
        "Target resolution",
        parse_resolution,
        RES_OPTIONS,
        preset_value=str(pd.get("res") or "") or None,
        skip="keep",
    )
    smooth = bool(fps or pd.get("fps")) and confirm("Smooth motion between frames? (slower)")
    extend = (
        choose("If the new length is longer than the source", ["freeze", "loop"], default="freeze")
        if duration or pd.get("duration")
        else "freeze"
    )
    precise = bool(duration or pd.get("duration")) and confirm(
        "Frame-exact cut when shortening? (slower)"
    )
    fit = (
        choose("Fit to the new size", ["pad", "stretch"], default="pad")
        if res or pd.get("res")
        else "pad"
    )
    codec_choice = "auto" if preset else choose("Codec", _codec_choices(output), default="auto")
    codec = None if codec_choice == "auto" else codec_choice
    audio = choose("Audio", ["keep", "tone", "silence", "none"], default="keep")
    layout = (
        "keep"
        if audio == "none" or (audio == "keep" and not _has_audio(source))
        else choose("Audio channels", ["keep", *_layout_choices(output)], default="keep")
    )
    caption = ask_caption_flags()
    timecode = confirm("Burn in a running timecode?")
    return [
        "convert", source,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--res", res), *_opt("--codec", codec),
        *(["--smooth"] if smooth else []),
        *_opt("--extend-mode", None if extend == "freeze" else extend),
        *(["--precise"] if precise else []), *(["--stretch"] if fit == "stretch" else []),
        *_opt("--audio", None if audio == "keep" else audio),
        *_opt("--audio-layout", None if layout == "keep" else layout),
        *caption, *(["--timecode"] if timecode else []), "-o", output,
    ]  # fmt: skip


PATTERN_CHOICES = ["smpte", "color-bars", "testsrc", "gradient", "solid:red"]


def audio_flow() -> list[str]:
    output = ask_output("test.wav", suggest=set(AUDIO_EXTENSIONS))
    audio = choose("Audio", ["tone", "silence"], default="tone")
    layout = choose("Audio channels", _layout_choices(output), default="stereo")
    duration = ask_spec("Duration", parse_duration, DURATION_OPTIONS, default="5s")
    return [
        "generate", *_opt("--audio", None if audio == "tone" else audio),
        *_opt("--audio-layout", layout), *_opt("--duration", duration), "-o", output,
    ]  # fmt: skip


def picture_flow() -> list[str]:
    pattern = choose("Pattern", PATTERN_CHOICES, default="smpte")
    res = ask_spec("Resolution", parse_resolution, RES_OPTIONS, default="720p")
    caption = ask_caption_flags(timing=False)
    output = ask_output("test.png", suggest=IMAGE_EXTS)
    return [
        "generate", "--pattern", pattern,
        *_opt("--res", res), *caption, "-o", output,
    ]  # fmt: skip


def generate_flow() -> list[str]:
    kind = choose("Generate", ["video", "audio-only", "picture"], default="video")
    if kind == "audio-only":
        return audio_flow()
    if kind == "picture":
        return picture_flow()
    output = ask_output("test.mp4", suggest=ENCODE_EXTS)
    pattern = choose("Pattern", PATTERN_CHOICES, default="smpte")
    preset = ask_preset()
    pd = get_preset(preset) if preset else {}
    fps = ask_spec(
        "fps",
        _fps_parser(output),
        FPS_OPTIONS,
        default="" if "fps" in pd else "30",
        preset_value=_pretty_fps(str(pd["fps"])) if "fps" in pd else None,
    )
    duration = ask_spec(
        "Duration",
        parse_duration,
        DURATION_OPTIONS,
        default="" if "duration" in pd else "5s",
        preset_value=str(pd.get("duration") or "") or None,
    )
    res = ask_spec(
        "Resolution",
        parse_resolution,
        RES_OPTIONS,
        default="" if "res" in pd else "720p",
        preset_value=str(pd.get("res") or "") or None,
    )
    codec_choice = (
        "auto" if "codec" in pd else choose("Codec", _codec_choices(output), default="auto")
    )
    codec = None if codec_choice == "auto" else codec_choice
    audio = choose("Audio", ["tone", "silence", "none"], default="tone")
    layout = (
        None
        if audio == "none"
        else choose("Audio channels", _layout_choices(output), default="stereo")
    )
    caption = ask_caption_flags()
    timecode = confirm("Burn in frame counter/timestamp?")
    return [
        "generate", "--pattern", pattern,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--codec", codec),
        *_opt("--audio", None if audio == "tone" else audio), *_opt("--audio-layout", layout),
        *_opt("--res", res), *caption,
        *(["--timecode"] if timecode else []), "-o", output,
    ]  # fmt: skip


def caption_flow() -> list[str]:
    source = ask_file("Which video do you want to caption?", ENCODE_EXTS)
    caption = ask_caption_flags(required=True)
    output = ask_output(
        str(Path(source).with_stem(Path(source).stem + "_captioned")), suggest=ENCODE_EXTS
    )
    return ["caption", source, *caption, "-o", output]


def ask_optional_file(label: str, exts: set[str] | frozenset[str]) -> str | None:
    """Pick a file from the current folder, type any path, or skip (None)."""
    files = _nearby(exts)
    hints = {**files, "skip": "don't add one"}
    answer = choose(label, ["skip", *files], default="skip", hints=hints, other=_existing)
    return None if answer == "skip" else _existing(answer)


def attach_flow() -> list[str]:
    source = ask_file("Which video do you want to attach to?", ENCODE_EXTS)
    audios: list[str] = []
    track = ask_optional_file("Audio file to add", AUDIO_EXTS | VIDEO_EXTS)
    while track:
        audios.append(track)
        track = ask_optional_file("Another audio file to add", AUDIO_EXTS | VIDEO_EXTS)
    subs = ask_optional_file("Subtitle file to add", SUBTITLE_EXTS)
    burn = confirm("Burn subtitles into the picture?") if subs else False
    output = ask_output(
        str(Path(source).with_stem(Path(source).stem + "_attached")), suggest=ENCODE_EXTS
    )
    audio_flags = [f for a in audios for f in ("--audio", a)]
    return [
        "attach", source,
        *audio_flags, *_opt("--subs", subs),
        *(["--burn"] if burn else []), "-o", output,
    ]  # fmt: skip


FORMAT_TARGETS = {
    "video": ["mp4", "mov", "mkv", "webm", "avi", "mxf", "mpg", "ogv", "flv", "wmv", "3gp", "gif"],
    "image": ["png", "jpg", "webp", "bmp", "tiff"],
    "audio": ["wav", "mp3", "m4a", "flac", "ogg", "opus", "aac"],
}


def _format_targets(source: str) -> list[str]:
    """Targets that make sense for the source: pictures stay pictures, audio stays audio."""
    try:
        kind = media_kind(source)
    except VidfixError:
        kind = "video"
    if kind == "video":
        return [*FORMAT_TARGETS["video"], *FORMAT_TARGETS["image"], *FORMAT_TARGETS["audio"]]
    return FORMAT_TARGETS[kind]


def format_flow() -> list[str]:
    source = ask_file("Which file do you want to convert to another format?")
    target = choose("Target format", _format_targets(source))
    output = ask_output(str(Path(source).with_suffix(f".{target}")), suggest={f".{target}"})
    return ["format", source, "-o", output]


def verify_flow() -> list[str]:
    source = ask_file("Which file do you want to verify?")
    while True:
        fps = ask_spec("Expected fps", parse_fps, FPS_OPTIONS)
        duration = ask_spec("Expected duration", parse_duration, DURATION_OPTIONS)
        res = ask_spec("Expected resolution", parse_resolution, RES_OPTIONS)
        if fps or duration or res:
            break
        console.print("[red]Give at least one thing to check (fps, duration, or resolution).[/red]")
    return [
        "verify", source,
        *_opt("--fps", fps), *_opt("--duration", duration), *_opt("--res", res),
    ]  # fmt: skip


def probe_flow() -> list[str]:
    return ["info", ask_file("Which file do you want to inspect?")]


def matrix_flow() -> list[str]:
    source = ask_file("Which video is the source?", ENCODE_EXTS)
    fps = choose_many("fps variants", FPS_OPTIONS, ["30", "60"], parse_fps)
    res = choose_many("Resolution variants", RES_OPTIONS, ["720p", "1080p"], parse_resolution)
    outdir = ask_text(_step("Output directory"), default="variants")
    return ["variants", source, "--fps", fps, "--res", res, "-o", outdir]


FLOWS: dict[str, Callable[[], list[str]]] = {
    "convert": convert_flow,
    "generate": generate_flow,
    "caption": caption_flow,
    "attach": attach_flow,
    "format": format_flow,
    "verify": verify_flow,
    "info": probe_flow,
    "variants": matrix_flow,
}


SWITCHES = frozenset({"--timecode", "--burn", "--smooth", "--precise", "--stretch"})

READ_ONLY = frozenset({"verify", "info"})

SUMMARY_NAMES = {
    "o": "output",
    "output": "output",
    "res": "resolution",
    "text": "caption",
    "position": "caption position",
    "color": "caption color",
    "size": "caption size",
    "start": "caption from (s)",
    "end": "caption until (s)",
    "audio layout": "audio channels",
    "extend mode": "if longer",
}


def summary(argv: list[str]) -> Panel:
    """What the command will do, one plain row per option."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column()
    rest = argv[1:]
    i = 0
    while i < len(rest):
        token = rest[i]
        if token in SWITCHES:
            table.add_row(token.lstrip("-"), "yes")
        elif token.startswith("-"):
            name = token.lstrip("-").replace("-", " ")
            name = SUMMARY_NAMES.get(name, name)
            table.add_row(name, rest[i + 1])
            i += 1
        else:
            table.add_row("input", token)
        i += 1
    return Panel(table, title=f"Ready to {argv[0]}", title_align="left", expand=False)


def wizard() -> list[str]:
    """Collect answers, show a summary + the equivalent command, and return its argv."""
    _STEP[0] = 0
    console.print(
        Panel(
            "exact-spec media · no syntax needed", title="vidfix", title_align="left", expand=False
        )
    )
    action = choose("What do you want to do?", list(ACTIONS), default="generate")
    argv = FLOWS[action]()
    console.print()
    console.print(summary(argv))
    console.print(f"[dim]equivalent command:[/dim] [bold]vidfix {shlex.join(argv)}[/bold]\n")
    finish = ["run", "cancel"] if action in READ_ONLY else ["run", "run & open", "cancel"]
    decision = choose("Go ahead?", finish, default="run")
    if decision == "cancel":
        console.print("Cancelled — nothing was written.")
        raise typer.Exit()
    return [*argv, "--open"] if decision == "run & open" else argv
