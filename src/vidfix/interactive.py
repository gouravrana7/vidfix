"""Interactive wizard: build a vidfix command by answering prompts.

Runs when ``vidfix`` is invoked with no subcommand. Every answer is validated
immediately with the same parsers the flags use, so no syntax mistakes survive.
Each flow returns an argv list; the wizard prints the equivalent command (so
you learn the syntax) and then executes it.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from vidfix.core.capabilities import allowed_codecs, max_channels
from vidfix.core.caption import POSITIONS
from vidfix.core.duration import DROP_FRAME_RATES, parse_duration, parse_fps, parse_resolution
from vidfix.core.formats import IMAGE_EXTS
from vidfix.core.generate import AUDIO_EXTENSIONS, AUDIO_LAYOUTS
from vidfix.core.presets import get_preset, load_presets
from vidfix.exceptions import VidfixError

console = Console()

ACTIONS = ("generate", "convert", "caption", "attach", "format", "verify", "info", "variants")

AUDIO_CHANNEL_CHOICES = ["mono", "stereo", "5.1", "7.1", "left", "right"]

KNOWN_CODECS = ["h264", "h265", "prores", "vp9", "mpeg2", "theora"]

POSITION_CHOICES = list(POSITIONS)


def ask_caption_flags(required: bool = False) -> list[str]:
    """Ask for caption text and, if given, its placement + color. Returns flags."""
    if required:
        text = Prompt.ask("Caption text")
    else:
        text = Prompt.ask(
            "Caption text [dim](enter to skip)[/dim]", default="", show_default=False
        ).strip()
    if not text:
        return []
    position = Prompt.ask("Caption position", choices=POSITION_CHOICES, default="bottom")
    color = Prompt.ask("Caption color (e.g. white, yellow, #ff0000)", default="white")
    flags = ["--text", text]
    if position != "bottom":
        flags += ["--position", position]
    if color != "white":
        flags += ["--color", color]
    return flags


def _layout_choices(output: str) -> list[str]:
    """Channel layouts the output format can actually carry (warns on the rest)."""
    cap = max_channels(output)
    if cap is None:
        return AUDIO_CHANNEL_CHOICES
    fit = [c for c in AUDIO_CHANNEL_CHOICES if AUDIO_LAYOUTS.get(c, 2) <= cap]
    dropped = [c for c in AUDIO_CHANNEL_CHOICES if c not in fit]
    if dropped:
        console.print(
            f"[yellow]{Path(output).suffix} audio can't do {', '.join(dropped)} — "
            "not offering those.[/yellow]"
        )
    return fit


def _codec_choices(output: str) -> list[str]:
    """'auto' plus the codecs the output container can hold (warns which)."""
    allowed = allowed_codecs(output)
    pick = KNOWN_CODECS if allowed is None else [c for c in KNOWN_CODECS if c in allowed]
    if allowed is not None:
        console.print(f"[yellow]{Path(output).suffix} supports: {', '.join(pick)}.[/yellow]")
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


def ask_spec(
    label: str,
    parser: Callable[[str], object],
    default: str = "",
    optional: bool = True,
    preset_value: str | None = None,
    skip_hint: str = "enter to skip",
) -> str | None:
    """Prompt until the answer parses (or is left blank when optional)."""
    if preset_value:
        hint = f" [dim](preset: {preset_value} — enter to keep, type to override)[/dim]"
    elif optional and not default:
        hint = f" [dim]({skip_hint})[/dim]"
    else:
        hint = ""
    while True:
        raw = Prompt.ask(f"{label}{hint}", default=default, show_default=bool(default)).strip()
        if not raw:
            if optional:
                return None
            continue
        try:
            parser(raw)
        except VidfixError as exc:
            console.print(f"[red]{exc}[/red]")
            continue
        return raw


def ask_file(label: str) -> str:
    """Prompt until the answer is an existing file path."""
    while True:
        raw = Prompt.ask(label).strip().strip("'\"")
        if Path(raw).is_file():
            return raw
        console.print(f"[red]File not found: {raw}[/red]")


def ask_output(default: str) -> str:
    return Prompt.ask("Output file", default=default).strip()


def ask_preset() -> str | None:
    presets = load_presets()
    for name in sorted(presets):
        hint = presets[name].get("description") or f"same as {presets[name].get('alias')}"
        console.print(f"  [cyan]{name:16}[/cyan][dim]{hint}[/dim]")
    choice = Prompt.ask("Preset", choices=["none", *sorted(presets)], default="none")
    return None if choice == "none" else choice


def _opt(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def convert_flow() -> list[str]:
    source = ask_file("Which file do you want to convert?")
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_converted")))
    preset = ask_preset()
    pd = get_preset(preset) if preset else {}
    fps = ask_spec(
        "Target fps (e.g. 30, 59.94)",
        _fps_parser(output),
        preset_value=_pretty_fps(str(pd["fps"])) if "fps" in pd else None,
        skip_hint="enter = keep source",
    )
    duration = ask_spec(
        "Target duration (e.g. 30s, 1min, 1:30)",
        parse_duration,
        preset_value=str(pd.get("duration") or "") or None,
        skip_hint="enter = keep source",
    )
    res = ask_spec(
        "Target resolution (e.g. 720p, 1280x720)",
        parse_resolution,
        preset_value=str(pd.get("res") or "") or None,
        skip_hint="enter = keep source",
    )
    codec_choice = (
        "auto" if preset else Prompt.ask("Codec", choices=_codec_choices(output), default="auto")
    )
    codec = None if codec_choice == "auto" else codec_choice
    audio = Prompt.ask("Audio", choices=["keep", "tone", "silence", "none"], default="keep")
    layout = (
        "keep"
        if audio == "none"
        else Prompt.ask(
            "Audio channels", choices=["keep", *_layout_choices(output)], default="keep"
        )
    )
    caption = ask_caption_flags()
    timecode = Confirm.ask("Burn in a running timecode?", default=False)
    return [
        "convert", source,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--res", res), *_opt("--codec", codec),
        *_opt("--audio", None if audio == "keep" else audio),
        *_opt("--audio-layout", None if layout == "keep" else layout),
        *caption, *(["--timecode"] if timecode else []), "-o", output,
    ]  # fmt: skip


def ask_output_ext(default: str, allowed: set[str], kind: str) -> str:
    """Prompt for an output file until its extension fits the generated media kind."""
    while True:
        output = ask_output(default)
        if Path(output).suffix.lower() in allowed:
            return output
        console.print(f"[red]{kind} output needs one of: {', '.join(sorted(allowed))}[/red]")


PATTERN_CHOICES = ["smpte", "color-bars", "testsrc", "gradient", "solid:red"]


def audio_flow() -> list[str]:
    output = ask_output_ext("test.wav", set(AUDIO_EXTENSIONS), "Audio-only")
    audio = Prompt.ask("Audio", choices=["tone", "silence"], default="tone")
    layout = Prompt.ask("Audio channels", choices=_layout_choices(output), default="stereo")
    duration = ask_spec("Duration (e.g. 30s, 1min, 1:30)", parse_duration, default="5s")
    return [
        "generate", *_opt("--audio", None if audio == "tone" else audio),
        *_opt("--audio-layout", layout), *_opt("--duration", duration), "-o", output,
    ]  # fmt: skip


def picture_flow() -> list[str]:
    pattern = Prompt.ask("Pattern", choices=PATTERN_CHOICES, default="smpte")
    res = ask_spec("Resolution (e.g. 720p, 1080p, 1280x720)", parse_resolution, default="720p")
    caption = ask_caption_flags()
    output = ask_output_ext("test.png", IMAGE_EXTS, "Picture")
    return [
        "generate", "--pattern", pattern,
        *_opt("--res", res), *caption, "-o", output,
    ]  # fmt: skip


def generate_flow() -> list[str]:
    kind = Prompt.ask("Generate", choices=["video", "audio-only", "picture"], default="video")
    if kind == "audio-only":
        return audio_flow()
    if kind == "picture":
        return picture_flow()
    output = ask_output("test.mp4")
    pattern = Prompt.ask("Pattern", choices=PATTERN_CHOICES, default="smpte")
    preset = ask_preset()
    pd = get_preset(preset) if preset else {}
    fps = ask_spec(
        "fps (e.g. 30, 29.97, 60)",
        _fps_parser(output),
        default="" if "fps" in pd else "30",
        preset_value=_pretty_fps(str(pd["fps"])) if "fps" in pd else None,
    )
    duration = ask_spec(
        "Duration (e.g. 30s, 1min, 1:30)",
        parse_duration,
        default="" if "duration" in pd else "5s",
        preset_value=str(pd.get("duration") or "") or None,
    )
    res = ask_spec(
        "Resolution (e.g. 720p, 1080p, 1280x720)",
        parse_resolution,
        default="" if "res" in pd else "720p",
        preset_value=str(pd.get("res") or "") or None,
    )
    audio = Prompt.ask("Audio", choices=["tone", "silence", "none"], default="tone")
    layout = (
        None
        if audio == "none"
        else Prompt.ask("Audio channels", choices=_layout_choices(output), default="stereo")
    )
    caption = ask_caption_flags()
    timecode = Confirm.ask("Burn in frame counter/timestamp?", default=False)
    return [
        "generate", "--pattern", pattern,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--audio", None if audio == "tone" else audio), *_opt("--audio-layout", layout),
        *_opt("--res", res), *caption,
        *(["--timecode"] if timecode else []), "-o", output,
    ]  # fmt: skip


def caption_flow() -> list[str]:
    source = ask_file("Which video do you want to caption?")
    caption = ask_caption_flags(required=True)
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_captioned")))
    return ["caption", source, *caption, "-o", output]


def ask_optional_file(label: str) -> str | None:
    """Prompt for an existing file, or None when left blank."""
    while True:
        raw = (
            Prompt.ask(f"{label} [dim](enter to skip)[/dim]", default="", show_default=False)
            .strip()
            .strip("'\"")
        )
        if not raw:
            return None
        if Path(raw).is_file():
            return raw
        console.print(f"[red]File not found: {raw}[/red]")


def attach_flow() -> list[str]:
    source = ask_file("Which video do you want to attach to?")
    audio = ask_optional_file("Audio file to add")
    subs = ask_optional_file("Subtitle file (.srt/.vtt) to add")
    burn = Confirm.ask("Burn subtitles into the picture?", default=False) if subs else False
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_attached")))
    return [
        "attach", source,
        *_opt("--audio", audio), *_opt("--subs", subs),
        *(["--burn"] if burn else []), "-o", output,
    ]  # fmt: skip


def format_flow() -> list[str]:
    source = ask_file("Which file do you want to convert to another format?")
    target = Prompt.ask(
        "Target format",
        choices=["mp4", "mov", "mkv", "webm", "avi", "mxf", "mpg", "ogv", "flv", "wmv",
                 "3gp", "gif", "png", "jpg", "webp", "wav", "mp3", "m4a", "flac"],
    )  # fmt: skip
    output = ask_output(str(Path(source).with_suffix(f".{target}")))
    return ["format", source, "-o", output]


def verify_flow() -> list[str]:
    source = ask_file("Which file do you want to verify?")
    fps = ask_spec("Expected fps", parse_fps)
    duration = ask_spec("Expected duration", parse_duration)
    res = ask_spec("Expected resolution", parse_resolution)
    return [
        "verify", source,
        *_opt("--fps", fps), *_opt("--duration", duration), *_opt("--res", res),
    ]  # fmt: skip


def probe_flow() -> list[str]:
    return ["info", ask_file("Which file do you want to inspect?")]


def matrix_flow() -> list[str]:
    source = ask_file("Which video is the source?")
    console.print(
        "[dim]The values shown are examples — keep them, or list as many as you want.[/dim]"
    )
    fps = Prompt.ask("fps variants — comma-separated, add more if you like", default="30,60")
    res = Prompt.ask(
        "Resolution variants — comma-separated, add more if you like", default="720p,1080p"
    )
    outdir = Prompt.ask("Output directory", default="variants")
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


def wizard() -> list[str]:
    """Collect answers, show the equivalent command, and return its argv."""
    console.print("[bold]vidfix[/bold] — answer a few questions, no syntax needed.\n")
    action = Prompt.ask("What do you want to do?", choices=list(ACTIONS), default="generate")
    argv = FLOWS[action]()
    console.print(f"\n[dim]equivalent command:[/dim] [bold]vidfix {shlex.join(argv)}[/bold]\n")
    return argv
