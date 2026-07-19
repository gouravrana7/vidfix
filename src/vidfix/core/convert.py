"""Convert an existing video to exact specs (fps, duration, resolution, codec)."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from vidfix.core.duration import (
    Resolution,
    fps_to_ffmpeg,
    parse_duration,
    parse_fps,
    parse_resolution,
)
from vidfix.core.ffmpeg import (
    CODEC_PROBE_NAMES,
    FFmpegRunner,
    ProgressCallback,
    audio_codec_args,
    video_codec_args,
)
from vidfix.core.generate import AUDIO_LAYOUTS, PAN_LAYOUTS, validate_layout
from vidfix.core.probe import MediaInfo, probe
from vidfix.exceptions import InvalidSpecError

EXTEND_MODES = ("freeze", "loop")


@dataclass(frozen=True)
class ConvertPlan:
    """A fully-built FFmpeg invocation plus how it was decided."""

    args: list[str]
    stream_copy: bool
    warnings: list[str] = field(default_factory=list)


def build_convert_plan(
    input_path: str,
    output: str,
    source: MediaInfo,
    fps: Fraction | None = None,
    duration: float | None = None,
    res: Resolution | None = None,
    codec: str = "h264",
    smooth: bool = False,
    extend_mode: str = "freeze",
    stretch: bool = False,
    no_audio: bool = False,
    audio_tone: bool = False,
    layout: str | None = None,
    precise: bool = False,
) -> ConvertPlan:
    """Pure planner: decide stream-copy vs re-encode and build the argument list."""
    if extend_mode not in EXTEND_MODES:
        raise InvalidSpecError(
            f"Unknown extend mode {extend_mode!r}; expected one of: {EXTEND_MODES}."
        )
    video_codec_args(codec, output)  # validate codec/container early
    validate_layout(layout)
    if layout and no_audio:
        raise InvalidSpecError("--audio-layout conflicts with --no-audio.")
    if layout and source.audio is None and not audio_tone:
        raise InvalidSpecError(
            f"{input_path} has no audio track to reshape; add one with --audio-tone."
        )

    same_codec = CODEC_PROBE_NAMES[codec] == source.video_codec
    only_trim = (
        fps is None
        and res is None
        and not smooth
        and not audio_tone
        and layout is None
        and duration is not None
        and duration < source.duration
    )
    if only_trim and same_codec and not precise:
        assert duration is not None
        args = ["-i", input_path, "-t", f"{duration}", "-c", "copy"]
        if no_audio:
            args.append("-an")
        args.append(output)
        return ConvertPlan(
            args=args,
            stream_copy=True,
            warnings=[
                "stream-copy trim cuts on keyframes, so the cut point may be off by up to "
                "one GOP; use --precise for a frame-accurate re-encode."
            ],
        )

    extending = duration is not None and duration > source.duration
    args = []
    if extending and extend_mode == "loop":
        args += ["-stream_loop", "-1"]
    args += ["-i", input_path]

    if audio_tone:
        tone_duration = duration if duration is not None else source.duration
        args += [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=44100:duration={tone_duration}",
        ]
        args += ["-map", "0:v", "-map", "1:a"]

    vf: list[str] = []
    if res is not None:
        if stretch:
            vf.append(f"scale={res.width}:{res.height},setsar=1")
        else:
            vf.append(
                f"scale={res.width}:{res.height}:force_original_aspect_ratio=decrease,"
                f"pad={res.width}:{res.height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
            )
    if fps is not None:
        rate = fps_to_ffmpeg(fps)
        if smooth:
            vf.append(f"minterpolate=fps={rate}:mi_mode=mci")
        else:
            vf.append(f"fps=fps={rate}")
    if duration is not None and duration > source.duration and extend_mode == "freeze":
        vf.append(f"tpad=stop_mode=clone:stop_duration={duration - source.duration}")
    if vf:
        args += ["-vf", ",".join(vf)]

    args += video_codec_args(codec)

    if no_audio:
        args.append("-an")
    elif source.audio is not None or audio_tone:
        args += audio_codec_args(output)
        if layout in AUDIO_LAYOUTS:
            args += ["-ac", str(AUDIO_LAYOUTS[layout])]
        af: list[str] = []
        if layout in PAN_LAYOUTS:
            af.append(PAN_LAYOUTS[layout])
        if extending and extend_mode == "freeze" and not audio_tone:
            af.append("apad")  # pad audio with silence to match the frozen video
        if af:
            args += ["-af", ",".join(af)]

    if duration is not None:
        args += ["-t", f"{duration}"]
    args.append(output)
    return ConvertPlan(args=args, stream_copy=False)


def convert(
    input_path: str | Path,
    output: str | Path,
    fps: str | float | Fraction | None = None,
    duration: str | float | None = None,
    res: str | None = None,
    codec: str = "h264",
    smooth: bool = False,
    extend_mode: str = "freeze",
    stretch: bool = False,
    no_audio: bool = False,
    audio_tone: bool = False,
    layout: str | None = None,
    precise: bool = False,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> ConvertPlan:
    """Convert a video to exact specs; returns the executed plan (with warnings)."""
    runner = runner or FFmpegRunner()
    source = probe(input_path, runner=runner)
    plan = build_convert_plan(
        input_path=str(input_path),
        output=str(output),
        source=source,
        fps=parse_fps(fps) if fps is not None else None,
        duration=parse_duration(duration) if duration is not None else None,
        res=parse_resolution(res) if res is not None else None,
        codec=codec,
        smooth=smooth,
        extend_mode=extend_mode,
        stretch=stretch,
        no_audio=no_audio,
        audio_tone=audio_tone,
        layout=layout,
        precise=precise,
    )
    runner.run(plan.args, on_progress=on_progress)
    return plan
