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

from vidfix.core.duration import parse_duration, parse_fps, parse_resolution
from vidfix.core.presets import load_presets
from vidfix.exceptions import VidfixError

console = Console()

ACTIONS = ("convert", "generate", "caption", "format", "verify", "info", "variants")


def ask_spec(
    label: str, parser: Callable[[str], object], default: str = "", optional: bool = True
) -> str | None:
    """Prompt until the answer parses (or is left blank when optional)."""
    hint = " [dim](enter to skip)[/dim]" if optional and not default else ""
    while True:
        raw = Prompt.ask(f"{label}{hint}", default=default).strip()
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
    names = sorted(load_presets())
    choice = Prompt.ask("Preset", choices=["none", *names], default="none")
    return None if choice == "none" else choice


def _opt(flag: str, value: str | None) -> list[str]:
    return [flag, value] if value else []


def convert_flow() -> list[str]:
    source = ask_file("Which file do you want to convert?")
    preset = ask_preset()
    fps = ask_spec("Target fps (e.g. 30, 59.94)", parse_fps)
    duration = ask_spec("Target duration (e.g. 30s, 1:30)", parse_duration)
    res = ask_spec("Target resolution (e.g. 720p, 1280x720)", parse_resolution)
    # A chosen preset must win: only send flags the user actually typed.
    codec = (
        None
        if preset
        else Prompt.ask("Codec", choices=["h264", "h265", "prores", "vp9"], default="h264")
    )
    output = ask_output(str(Path(source).with_stem(Path(source).stem + "_converted")))
    return [
        "convert", source,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
        *_opt("--res", res), *_opt("--codec", codec), "-o", output,
    ]  # fmt: skip


def generate_flow() -> list[str]:
    pattern = Prompt.ask(
        "Pattern",
        choices=["smpte", "color-bars", "testsrc", "gradient", "solid:red"],
        default="smpte",
    )
    preset = ask_preset()
    # A chosen preset must win: defaults would be sent as explicit flags and
    # override it, so blank-to-skip when a preset is picked.
    fps = ask_spec("fps", parse_fps, default="" if preset else "30")
    duration = ask_spec("Duration", parse_duration, default="" if preset else "5s")
    res = ask_spec("Resolution", parse_resolution, default="" if preset else "720p")
    text = Prompt.ask("Caption text [dim](enter to skip)[/dim]", default="").strip()
    timecode = Confirm.ask("Burn in frame counter/timestamp?", default=False)
    output = ask_output("test.mp4")
    return [
        "generate", "--pattern", pattern,
        *_opt("--preset", preset), *_opt("--fps", fps), *_opt("--duration", duration),
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
    action = Prompt.ask("What do you want to do?", choices=list(ACTIONS), default="convert")
    argv = FLOWS[action]()
    console.print(f"\n[dim]equivalent command:[/dim] [bold]vidfix {shlex.join(argv)}[/bold]\n")
    return argv
