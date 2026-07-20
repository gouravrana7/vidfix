"""vidfix command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from vidfix.core import attach as attach_mod
from vidfix.core import caption as caption_mod
from vidfix.core import convert as convert_mod
from vidfix.core import formats as formats_mod
from vidfix.core import generate as generate_mod
from vidfix.core import matrix as matrix_mod
from vidfix.core import presets as presets_mod
from vidfix.core import probe as probe_mod
from vidfix.core import verify as verify_mod
from vidfix.core.duration import NAMED_RESOLUTIONS, parse_duration, parse_fps, parse_resolution
from vidfix.core.ffmpeg import ProgressCallback, ProgressEvent
from vidfix.exceptions import VidfixError

app = typer.Typer(
    name="vidfix",
    help=(
        "Media toolkit: convert, generate, and verify videos and images to exact specs. "
        "Run with no arguments for an interactive wizard."
    ),
    rich_markup_mode="rich",
)
console = Console()
err_console = Console(stderr=True)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """vidfix — exact-spec media, no syntax required (just run `vidfix`)."""
    if ctx.invoked_subcommand is None:
        from vidfix.interactive import wizard

        app(wizard())


def _fail(error: Exception) -> NoReturn:
    err_console.print(f"[red]error:[/red] {error}")
    raise typer.Exit(code=1)


def _wrote(path: Path, note: str = "") -> None:
    console.print(f"[green]✓[/green] wrote {path}{note}")
    console.print(f"  [dim]location:[/dim] {path.resolve()}")


_PIX_FMT_NAMES = {
    "yuv420p": "standard",
    "yuv420p10le": "10-bit",
    "yuv422p": "high color",
    "yuv444p": "full color",
}

_SAMPLE_RATE_NAMES = {
    8000: "low quality",
    22050: "low quality",
    44100: "normal quality",
    48000: "normal quality",
    96000: "high quality",
    192000: "high quality",
}

_CHANNEL_NAMES = {
    1: "mono",
    2: "stereo (left+right)",
    6: "5.1 surround",
    8: "7.1 surround",
}


def _verify_table(title: str, result: verify_mod.VerifyResult) -> Table:
    table = Table(title=title)
    table.add_column("property", style="bold cyan")
    table.add_column("expected")
    table.add_column("actual")
    table.add_column("result")
    for check in result.checks:
        mark = "[green]PASS[/green]" if check.passed else "[red]FAIL[/red]"
        table.add_row(check.name, check.expected, check.actual, mark)
    return table


def _friendly_duration(seconds: float) -> str:
    """Plain-language duration: '5.01 seconds', '1m 30s (90.00 seconds)'."""
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    minutes, secs = divmod(round(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    clock = f"{hours}h {minutes}m {secs}s" if hours else f"{minutes}m {secs}s"
    return f"{clock} ({seconds:.2f} seconds)"


class _ProgressBar:
    """Rich progress bar driven by FFmpeg ``-progress`` events."""

    def __init__(self, label: str, total_seconds: float) -> None:
        from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn

        self._progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        )
        self._task = self._progress.add_task(label, total=total_seconds)

    def __enter__(self) -> ProgressCallback:
        self._progress.start()

        def on_progress(event: ProgressEvent) -> None:
            self._progress.update(self._task, completed=event.seconds)
            if event.done:
                self._progress.update(self._task, completed=self._progress.tasks[0].total or 0)

        return on_progress

    def __exit__(self, *exc: object) -> None:
        self._progress.stop()


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vidfix generate -o bars.mp4 --fps 60 --duration 30s --res 720p\n\n"
        "  vidfix generate -o df.mp4 --fps 29.97 --pattern testsrc --timecode\n\n"
        "  vidfix generate -o red.mp4 --pattern solid:red --audio none\n\n"
        "  vidfix generate -o tone.wav --duration 3s --audio-layout left\n\n"
        "  vidfix generate -o card.png --res 1080p --text 'SCENE 1'"
    )
)
def generate(
    output: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="Output file path (.wav/.mp3/… → audio-only; .png/.jpg/… → picture).",
        ),
    ],
    fps: Annotated[
        str | None, typer.Option(help="Frame rate: 30, 59.94, or 30000/1001. Default 30.")
    ] = None,
    duration: Annotated[
        str | None, typer.Option(help="Duration: '30s', '1:30', or '90'. Default 5s.")
    ] = None,
    res: Annotated[
        str | None, typer.Option(help="Resolution: '1280x720', '720p', '4k'. Default 1280x720.")
    ] = None,
    pattern: Annotated[
        str,
        typer.Option(help="Test pattern: smpte, color-bars, testsrc, gradient, or solid:COLOR."),
    ] = "smpte",
    codec: Annotated[
        str | None,
        typer.Option(
            help="Video codec: h264, h265, prores, vp9, mpeg2, theora. Default fits the container."
        ),
    ] = None,
    audio: Annotated[str, typer.Option(help="Audio track: tone (440Hz), silence, none.")] = "tone",
    audio_layout: Annotated[
        str | None,
        typer.Option("--audio-layout", help="Audio channels: mono, stereo, 5.1, 7.1, left, right."),
    ] = None,
    timecode: Annotated[
        bool,
        typer.Option(
            "--timecode",
            help="Burn in running timecode (HH:MM:SS:FF; drop-frame ';FF' for NTSC 29.97/59.94).",
        ),
    ] = False,
    text: Annotated[
        str | None, typer.Option("--text", help="Burn a caption into the video.")
    ] = None,
    position: Annotated[
        str,
        typer.Option(help="Caption placement: top/center/bottom, optionally -left/-right."),
    ] = "bottom",
    size: Annotated[
        str, typer.Option(help="Caption font size (pixels or expression like 'h/12').")
    ] = "h/12",
    color: Annotated[
        str, typer.Option(help="Caption font color, e.g. white, yellow, #ff0000.")
    ] = "white",
    start: Annotated[
        float | None, typer.Option(help="Show caption from this second onward.")
    ] = None,
    end: Annotated[float | None, typer.Option(help="Hide caption after this second.")] = None,
    preset: Annotated[
        str | None, typer.Option(help="Preset name for defaults ('vidfix preset list').")
    ] = None,
) -> None:
    """Create a synthetic test video with exact specs — no source file needed."""
    try:
        merged = presets_mod.apply_preset(preset, fps=fps, duration=duration, res=res, codec=codec)
        total = parse_duration(merged.get("duration") or "5s")
        drop_frame = {"df": True, "ndf": False}.get(merged.get("timecode") or "")
        if fps is not None:
            drop_frame = None
        with _ProgressBar(f"generate {output.name}", total) as on_progress:
            generate_mod.generate(
                output,
                fps=merged.get("fps") or "30",
                duration=merged.get("duration") or "5s",
                res=merged.get("res") or "1280x720",
                pattern=pattern,
                codec=merged.get("codec"),
                audio=audio,
                layout=audio_layout,
                timecode=timecode,
                drop_frame=drop_frame,
                text=text,
                position=position,
                size=size,
                color=color,
                start=start,
                end=end,
                on_progress=on_progress,
            )
    except VidfixError as exc:
        _fail(exc)
    _wrote(output)


@app.command(
    epilog=(
        "Examples:\n\n"
        '  vidfix caption in.mp4 --text "Take 42" -o out.mp4\n\n'
        '  vidfix caption in.mp4 --text "INTRO" --position top --color yellow -o out.mp4\n\n'
        '  vidfix caption in.mp4 --text "3..2..1" --start 0 --end 3 -o out.mp4'
    )
)
def caption(
    input: Annotated[Path, typer.Argument(help="Source video file.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output file path.")],
    text: Annotated[str, typer.Option("--text", help="Caption text to burn in.")],
    position: Annotated[
        str,
        typer.Option(help="Caption placement: top/center/bottom, optionally -left/-right."),
    ] = "bottom",
    size: Annotated[
        str, typer.Option(help="Font size (pixels or expression like 'h/12').")
    ] = "h/12",
    color: Annotated[str, typer.Option(help="Font color, e.g. white, yellow, #ff0000.")] = "white",
    start: Annotated[
        float | None, typer.Option(help="Show caption from this second onward.")
    ] = None,
    end: Annotated[float | None, typer.Option(help="Hide caption after this second.")] = None,
) -> None:
    """Burn a text caption into a video (audio untouched)."""
    try:
        total = probe_mod.probe(input).duration
        with _ProgressBar(f"caption {output.name}", total) as on_progress:
            caption_mod.caption(
                input,
                output,
                text,
                position=position,
                size=size,
                color=color,
                start=start,
                end=end,
                on_progress=on_progress,
            )
    except VidfixError as exc:
        _fail(exc)
    _wrote(output)


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vidfix attach clip.mp4 --audio track.m4a -o out.mp4        (mux in an audio track)\n\n"
        "  vidfix attach clip.mp4 --subs subs.srt -o out.mkv          (soft subtitle track)\n\n"
        "  vidfix attach clip.mp4 --subs subs.srt --burn -o out.mp4   (burn subs in)\n\n"
        "  vidfix attach clip.mp4 --audio track.m4a --subs subs.srt -o out.mkv"
    )
)
def attach(
    input: Annotated[Path, typer.Argument(help="Base video file.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output file path.")],
    audio: Annotated[
        Path | None, typer.Option("--audio", help="Audio file to mux onto the video.")
    ] = None,
    subs: Annotated[
        Path | None, typer.Option("--subs", help="Subtitle file (.srt/.vtt) to add.")
    ] = None,
    burn: Annotated[
        bool, typer.Option("--burn", help="Burn subtitles into the picture (else a soft track).")
    ] = False,
) -> None:
    """Attach an existing audio track and/or subtitle onto a video."""
    try:
        total = probe_mod.probe(input).duration
        with _ProgressBar(f"attach {output.name}", total) as on_progress:
            attach_mod.attach(
                input, output, audio=audio, subs=subs, burn=burn, on_progress=on_progress
            )
    except VidfixError as exc:
        _fail(exc)
    _wrote(output)


@app.command(
    epilog=(
        "Examples:\n\n"
        "  vidfix convert in.mp4 --fps 60 --duration 30s --res 1280x720 -o out.mp4\n\n"
        "  vidfix convert in.mp4 --preset df60 -o out.mp4    (preset defaults)\n\n"
        "  vidfix convert in.mp4 --fps 60 --smooth -o out.mp4   (motion-interpolated 30→60)\n\n"
        "  vidfix convert in.mp4 --duration 10s -o out.mp4      (stream-copy trim, instant)\n\n"
        "  vidfix convert in.mp4 --duration 60s --extend-mode loop -o out.mp4"
    )
)
def convert(
    input: Annotated[Path, typer.Argument(help="Source video file.")],
    output: Annotated[Path, typer.Option("-o", "--output", help="Output file path.")],
    fps: Annotated[
        str | None, typer.Option(help="Target frame rate: 30, 59.94, or 30000/1001.")
    ] = None,
    duration: Annotated[
        str | None,
        typer.Option(help="Target duration: '30s', '1:30', or '90'. Trims or extends."),
    ] = None,
    res: Annotated[
        str | None, typer.Option(help="Target resolution: '1280x720', '720p', '4k'.")
    ] = None,
    codec: Annotated[
        str | None,
        typer.Option(
            help="Video codec: h264, h265, prores, vp9, mpeg2, theora. Default fits the container."
        ),
    ] = None,
    preset: Annotated[
        str | None, typer.Option(help="Preset name for defaults ('vidfix preset list').")
    ] = None,
    smooth: Annotated[
        bool, typer.Option("--smooth", help="Motion-interpolate fps changes (minterpolate).")
    ] = False,
    extend_mode: Annotated[
        str,
        typer.Option(help="When target duration > source: 'freeze' last frame or 'loop'."),
    ] = "freeze",
    stretch: Annotated[
        bool, typer.Option("--stretch", help="Stretch to target resolution (no pad bars).")
    ] = False,
    audio: Annotated[
        str,
        typer.Option(
            help="Audio track: keep (source), tone (440Hz), silence, none.",
        ),
    ] = "keep",
    no_audio: Annotated[
        bool, typer.Option("--no-audio", hidden=True, help="Alias for --audio none.")
    ] = False,
    audio_tone: Annotated[
        bool, typer.Option("--audio-tone", hidden=True, help="Alias for --audio tone.")
    ] = False,
    audio_layout: Annotated[
        str | None,
        typer.Option(
            "--audio-layout",
            help="Reshape audio channels: mono, stereo, 5.1, 7.1, left, right.",
        ),
    ] = None,
    precise: Annotated[
        bool, typer.Option("--precise", help="Force re-encode for frame-accurate trims.")
    ] = False,
    text: Annotated[
        str | None, typer.Option("--text", help="Burn a caption into the video.")
    ] = None,
    position: Annotated[
        str,
        typer.Option(help="Caption placement: top/center/bottom, optionally -left/-right."),
    ] = "bottom",
    size: Annotated[
        str, typer.Option(help="Caption font size (pixels or expression like 'h/12').")
    ] = "h/12",
    color: Annotated[
        str, typer.Option(help="Caption font color, e.g. white, yellow, #ff0000.")
    ] = "white",
    start: Annotated[
        float | None, typer.Option(help="Show caption from this second onward.")
    ] = None,
    end: Annotated[float | None, typer.Option(help="Hide caption after this second.")] = None,
    timecode: Annotated[
        bool, typer.Option("--timecode", help="Burn in a running timecode.")
    ] = False,
) -> None:
    """Transform an existing video to exact specs (stream-copies when possible)."""
    try:
        if audio == "keep":
            audio = "tone" if audio_tone else "none" if no_audio else "keep"
        merged = presets_mod.apply_preset(preset, fps=fps, duration=duration, res=res, codec=codec)
        target_duration = merged.get("duration")
        label = f"convert {output.name}"
        total = (
            parse_duration(target_duration) if target_duration else probe_mod.probe(input).duration
        )
        with _ProgressBar(label, total) as on_progress:
            plan = convert_mod.convert(
                input,
                output,
                fps=merged.get("fps"),
                duration=target_duration,
                res=merged.get("res"),
                codec=merged.get("codec"),
                smooth=smooth,
                extend_mode=extend_mode,
                stretch=stretch,
                audio=audio,
                layout=audio_layout,
                precise=precise,
                text=text,
                position=position,
                size=size,
                color=color,
                start=start,
                end=end,
                timecode=timecode,
                on_progress=on_progress,
            )
    except VidfixError as exc:
        _fail(exc)
    for warning in plan.warnings:
        err_console.print(f"[yellow]warning:[/yellow] {warning}")
    mode = "stream copy" if plan.stream_copy else "re-encode"
    _wrote(output, f" ({mode})")


@app.command(
    name="format",
    epilog=(
        "Examples:\n\n"
        "  vidfix format clip.mov -o clip.mp4      (any container → any container)\n\n"
        "  vidfix format clip.mp4 -o clip.gif      (palette-optimized gif)\n\n"
        "  vidfix format photo.png -o photo.webp   (image → image)\n\n"
        "  vidfix format clip.mp4 -o thumb.jpg     (first-frame grab)"
    ),
)
def format_cmd(
    input: Annotated[Path, typer.Argument(help="Source picture or video.")],
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output path; extension picks the format.")
    ],
) -> None:
    """Convert any picture or video to any other format (by output extension)."""
    try:
        if (
            formats_mod.media_kind(str(input)) == "video"
            and formats_mod.media_kind(str(output)) == "video"
        ):
            total = probe_mod.probe(input).duration
            with _ProgressBar(f"format {output.name}", total) as on_progress:
                formats_mod.to_format(input, output, on_progress=on_progress)
        else:
            formats_mod.to_format(input, output)
    except VidfixError as exc:
        _fail(exc)
    _wrote(output)


@app.command(
    epilog=(
        "Exit code 0 when all checks pass, 1 otherwise — wire it straight into CI.\n\n"
        "Examples:\n\n"
        "  vidfix verify out.mp4 --fps 60 --duration 30s --res 1280x720\n\n"
        "  vidfix verify out.mp4 --fps 29.97 --codec h264 --json"
    )
)
def verify(
    input: Annotated[Path, typer.Argument(help="Media file to verify.")],
    fps: Annotated[
        str | None, typer.Option(help="Expected frame rate: 30, 59.94, or 30000/1001.")
    ] = None,
    duration: Annotated[
        str | None, typer.Option(help="Expected duration: '30s', '1:30', or '90'.")
    ] = None,
    res: Annotated[
        str | None, typer.Option(help="Expected resolution: '1280x720', '720p', '4k'.")
    ] = None,
    codec: Annotated[
        str | None, typer.Option(help="Expected video codec: h264, h265, prores, vp9.")
    ] = None,
    fps_tolerance: Annotated[
        float, typer.Option(help="Allowed fps deviation.")
    ] = verify_mod.DEFAULT_FPS_TOLERANCE,
    duration_tolerance: Annotated[
        float, typer.Option(help="Allowed duration deviation in seconds.")
    ] = verify_mod.DEFAULT_DURATION_TOLERANCE,
    json_out: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON instead of a table.")
    ] = False,
) -> None:
    """Assert a file matches specs; exit 0 on pass, 1 on fail (designed for CI)."""
    if fps is None and duration is None and res is None and codec is None:
        _fail(ValueError("Nothing to verify: pass at least one of --fps/--duration/--res/--codec."))
    try:
        result = verify_mod.verify(
            input,
            fps=parse_fps(fps) if fps else None,
            duration=parse_duration(duration) if duration else None,
            res=parse_resolution(res) if res else None,
            codec=codec,
            fps_tolerance=fps_tolerance,
            duration_tolerance=duration_tolerance,
        )
    except VidfixError as exc:
        _fail(exc)

    if json_out:
        console.print_json(result.model_dump_json())
    else:
        console.print(_verify_table(str(input), result))
    raise typer.Exit(code=0 if result.passed else 1)


@app.command(
    name="info",
    epilog="Examples:\n\n  vidfix info clip.mp4\n\n  vidfix info clip.mp4 --json | jq .fps",
)
def probe(
    input: Annotated[Path, typer.Argument(help="Media file to inspect.")],
    json_out: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON (jq-friendly).")
    ] = False,
) -> None:
    """Pretty-print media details in plain words: type, duration, fps, resolution, codecs."""
    try:
        info = probe_mod.probe(input)
    except VidfixError as exc:
        _fail(exc)

    if json_out:
        console.print_json(info.model_dump_json())
        return

    table = Table(title=str(input), show_header=False)
    table.add_column(style="bold cyan")
    table.add_column()
    kind = "audio" if info.video_codec == "none" else "video"
    table.add_row("type", f"{info.container} {kind}")
    table.add_row("duration", _friendly_duration(info.duration))
    if info.video_codec == "none":
        table.add_row("video", "none")
    else:
        res_names = {str(v): k for k, v in NAMED_RESOLUTIONS.items()}
        res_name = res_names.get(info.resolution)
        table.add_row(
            "resolution", f"{res_name} ({info.resolution})" if res_name else info.resolution
        )
        table.add_row("fps", info.fps_display)
        table.add_row("video codec", info.video_codec)
        pix_name = _PIX_FMT_NAMES.get(info.pix_fmt or "")
        table.add_row(
            "color format", f"{pix_name} ({info.pix_fmt})" if pix_name else info.pix_fmt or "-"
        )
    table.add_row("bitrate", f"{info.bitrate // 1000} kb/s" if info.bitrate else "-")
    if info.audio:
        if info.audio.sample_rate:
            rate_name = _SAMPLE_RATE_NAMES.get(info.audio.sample_rate)
            rate = (
                f"{rate_name} ({info.audio.sample_rate} Hz)"
                if rate_name
                else f"{info.audio.sample_rate} Hz"
            )
        else:
            rate = "?"
        channels = (
            _CHANNEL_NAMES.get(info.audio.channels, f"{info.audio.channels} channels")
            if info.audio.channels
            else "?"
        )
        table.add_row("audio", f"{info.audio.codec} · {channels} · {rate}")
    else:
        table.add_row("audio", "none")
    console.print(table)


app.command(name="probe", hidden=True)(probe)


@app.command(
    name="variants",
    epilog=(
        "Examples:\n\n"
        "  vidfix variants in.mp4 --fps 30,60 --res 720p,1080p -o variants/\n\n"
        "  vidfix variants in.mp4 --fps 29.97,59.94 --res 480p -o out/ --jobs 8"
    ),
)
def matrix(
    input: Annotated[Path, typer.Argument(help="Source video file.")],
    outdir: Annotated[Path, typer.Option("-o", "--output", help="Output directory.")],
    fps: Annotated[str, typer.Option(help="Comma-separated frame rates, e.g. '30,60'.")],
    res: Annotated[str, typer.Option(help="Comma-separated resolutions, e.g. '720p,1080p'.")],
    codec: Annotated[str, typer.Option(help="Video codec for all variants.")] = "h264",
    jobs: Annotated[
        int | None, typer.Option(help="Parallel FFmpeg processes (default: min(4, cpus)).")
    ] = None,
) -> None:
    """Generate the cartesian product of fps x resolution variants."""
    from rich.progress import BarColumn, Progress, TextColumn

    try:
        fps_list = matrix_mod.parse_list(fps, "fps")
        res_list = matrix_mod.parse_list(res, "resolution")
        total = len(fps_list) * len(res_list)
        progress = Progress(
            TextColumn("[bold blue]matrix"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        )
        with progress:
            task = progress.add_task("matrix", total=total)
            results = matrix_mod.run_matrix(
                input,
                outdir,
                fps_list,
                res_list,
                codec=codec,
                jobs=jobs,
                on_result=lambda _: progress.advance(task),
            )
    except VidfixError as exc:
        _fail(exc)

    table = Table(title=f"{input} → {outdir}")
    table.add_column("fps", style="bold cyan")
    table.add_column("res")
    table.add_column("output")
    table.add_column("result")
    for r in results:
        mark = "[green]OK[/green]" if r.ok else f"[red]FAIL[/red] {r.error}"
        table.add_row(r.job.fps, r.job.res, r.job.output.name, mark)
    console.print(table)
    console.print(f"  [dim]location:[/dim] {outdir.resolve()}")
    if not all(r.ok for r in results):
        raise typer.Exit(code=1)


app.command(name="matrix", hidden=True)(matrix)


preset_app = typer.Typer(help="Inspect built-in and user presets.", no_args_is_help=True)
app.add_typer(preset_app, name="preset")


@preset_app.command("list")
def preset_list() -> None:
    """List all presets (built-in + ~/.config/vidfix/presets.yaml)."""
    try:
        presets = presets_mod.load_presets()
    except VidfixError as exc:
        _fail(exc)
    table = Table()
    table.add_column("name", style="bold cyan")
    table.add_column("description")
    table.add_column("settings")
    for name, settings in sorted(presets.items()):
        description = settings.get("description", "")
        rest = ", ".join(f"{k}={v}" for k, v in settings.items() if k != "description")
        table.add_row(name, description, rest)
    console.print(table)


@preset_app.command("show")
def preset_show(name: Annotated[str, typer.Argument(help="Preset name.")]) -> None:
    """Show one preset's settings."""
    try:
        settings = presets_mod.get_preset(name)
    except VidfixError as exc:
        _fail(exc)
    table = Table(title=name, show_header=False)
    table.add_column(style="bold cyan")
    table.add_column()
    for key, value in settings.items():
        table.add_row(key, value)
    console.print(table)
