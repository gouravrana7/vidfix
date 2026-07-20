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

from vidfix.core.duration import DROP_FRAME_RATES, parse_duration, parse_fps, parse_resolution
from vidfix.core.formats import IMAGE_EXTS
from vidfix.core.generate import AUDIO_EXTENSIONS
from vidfix.core.presets import get_preset, load_presets
from vidfix.exceptions import VidfixError

console = Console()

ACTIONS = ("generate", "convert", "caption", "format", "verify", "info", "variants")

AUDIO_CHANNEL_CHOICES = ["mono", "stereo", "5.1", "7.1", "left", "right"]


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
    preset = ask_preset()
    pd = get_preset(preset) if preset else {}
    fps = ask_spec(
        "Target fps (e.g. 30, 59.94)",
        parse_fps,
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
    # A chosen preset must win: only send flags the user actually typed.
    codec = (
        None
        if preset
        else Prompt.ask("Codec", choices=["h264", "h265", "prores", "vp9"], default="h264")
    )
    layout = Prompt.ask("Audio channels", choices=["keep", *AUDIO_CHANNEL_CHOICES], default="keep")
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_converted")))
    return [
        "convert", source,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--res", res), *_opt("--codec", codec),
        *_opt("--audio-layout", None if layout == "keep" else layout), "-o", output,
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
    audio = Prompt.ask("Audio", choices=["tone", "silence"], default="tone")
    layout = Prompt.ask("Audio channels", choices=AUDIO_CHANNEL_CHOICES, default="stereo")
    duration = ask_spec("Duration (e.g. 30s, 1min, 1:30)", parse_duration, default="5s")
    output = ask_output_ext("test.wav", set(AUDIO_EXTENSIONS), "Audio-only")
    return [
        "generate", *_opt("--audio", None if audio == "tone" else audio),
        *_opt("--audio-layout", layout), *_opt("--duration", duration), "-o", output,
    ]  # fmt: skip


def picture_flow() -> list[str]:
    pattern = Prompt.ask("Pattern", choices=PATTERN_CHOICES, default="smpte")
    res = ask_spec("Resolution (e.g. 720p, 1080p, 1280x720)", parse_resolution, default="720p")
    text = Prompt.ask(
        "Caption text [dim](enter to skip)[/dim]", default="", show_default=False
    ).strip()
    output = ask_output_ext("test.png", IMAGE_EXTS, "Picture")
    return [
        "generate", "--pattern", pattern,
        *_opt("--res", res), *_opt("--text", text or None), "-o", output,
    ]  # fmt: skip


def generate_flow() -> list[str]:
    kind = Prompt.ask("Generate", choices=["video", "audio-only", "picture"], default="video")
    if kind == "audio-only":
        return audio_flow()
    if kind == "picture":
        return picture_flow()
    pattern = Prompt.ask("Pattern", choices=PATTERN_CHOICES, default="smpte")
    preset = ask_preset()
    # A chosen preset must win: defaults would be sent as explicit flags and
    # override it, so blank-to-skip when a preset is picked — and the hint
    # names the preset's value so typing an override is a conscious choice.
    pd = get_preset(preset) if preset else {}
    # Fields the preset sets stay blank (preset wins; hint names its value);
    # fields it does not set keep their normal visible defaults.
    fps = ask_spec(
        "fps (e.g. 30, 29.97, 60)",
        parse_fps,
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
        else Prompt.ask("Audio channels", choices=AUDIO_CHANNEL_CHOICES, default="stereo")
    )
    text = Prompt.ask(
        "Caption text [dim](enter to skip)[/dim]", default="", show_default=False
    ).strip()
    timecode = Confirm.ask("Burn in frame counter/timestamp?", default=False)
    output = ask_output("test.mp4")
    return [
        "generate", "--pattern", pattern,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--audio", None if audio == "tone" else audio), *_opt("--audio-layout", layout),
        *_opt("--res", res), *_opt("--text", text or None),
        *(["--timecode"] if timecode else []), "-o", output,
    ]  # fmt: skip


def caption_flow() -> list[str]:
    source = ask_file("Which video do you want to caption?")
    text = Prompt.ask("Caption text")
    position = Prompt.ask("Position", choices=["top", "center", "bottom"], default="bottom")
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_captioned")))
    return ["caption", source, "--text", text, "--position", position, "-o", output]


def format_flow() -> list[str]:
    source = ask_file("Which file do you want to convert to another format?")
    target = Prompt.ask(
        "Target format", choices=["mp4", "mov", "mkv", "webm", "gif", "png", "jpg", "webp"]
    )
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
    fps = Prompt.ask("fps variants (comma-separated)", default="30,60")
    res = Prompt.ask("Resolution variants (comma-separated)", default="720p,1080p")
    outdir = Prompt.ask("Output directory", default="variants")
    return ["variants", source, "--fps", fps, "--res", res, "-o", outdir]


FLOWS: dict[str, Callable[[], list[str]]] = {
    "convert": convert_flow,
    "generate": generate_flow,
    "caption": caption_flow,
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
