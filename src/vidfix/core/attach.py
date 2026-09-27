"""Attach existing streams onto a video: external audio and/or a subtitle file.

Subtitles go in as a soft (toggle-able) track by default, or burned into the
picture with ``burn=True``. The video is stream-copied when the source codec and
both containers allow it cleanly; otherwise (or when burning) it is re-encoded.
Audio is always encoded for the output container.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from vidfix.core.capabilities import (
    can_copy_video,
    validate_audio_stream_count,
    validate_channels,
    validate_fps,
)
from vidfix.core.ffmpeg import (
    FFmpegRunner,
    ProgressCallback,
    audio_codec_args,
    default_codec_for,
    video_codec_args,
)
from vidfix.exceptions import InvalidSpecError

SUBTITLE_CODECS = {
    ".mp4": "mov_text",
    ".mov": "mov_text",
    ".m4v": "mov_text",
    ".mkv": "srt",
    ".webm": "webvtt",
}


SUBTITLE_EXTS = frozenset({".srt", ".vtt", ".ass", ".ssa"})


def subtitle_codec(output: str) -> str:
    """The soft-subtitle codec the output container wants (mov_text/srt/…)."""
    return SUBTITLE_CODECS.get(Path(output).suffix.lower(), "copy")


def build_attach_args(
    video: str,
    output: str,
    audios: list[str] | None = None,
    subs: str | None = None,
    burn: bool = False,
    video_codec: str | None = None,
) -> list[str]:
    """Pure builder for the attach/mux FFmpeg argument list.

    ``audios`` maps to one output audio track per file, in the order given.
    ``video_codec`` is the source video codec (vidfix name) when known.
    """
    from vidfix.core.formats import VIDEO_EXTS, validate_output_ext
    from vidfix.core.generate import escape_filter_path

    audios = audios or None
    if audios is None and subs is None:
        raise InvalidSpecError("Nothing to attach: pass an audio file, a subtitle file, or both.")

    validate_output_ext(output, VIDEO_EXTS)
    out_ext = Path(output).suffix.lower()
    if out_ext == ".gif":
        raise InvalidSpecError(
            "GIF can't hold audio or subtitle tracks; attach to a video container "
            "like .mp4/.mkv/.mov instead."
        )
    if subs is not None and Path(subs).suffix.lower() not in SUBTITLE_EXTS:
        raise InvalidSpecError(
            f"{subs} isn't a subtitle file; use one of: "
            f"{', '.join(sorted(e.lstrip('.') for e in SUBTITLE_EXTS))}."
        )
    if subs is not None and not burn and out_ext not in SUBTITLE_CODECS:
        raise InvalidSpecError(
            f"{out_ext} can't hold a soft subtitle track; use .mp4/.mov/.mkv/.webm, "
            "or add --burn to burn the subtitles into the picture."
        )
    if audios is not None and len(audios) > 1:
        validate_audio_stream_count(len(audios), output)

    args = ["-i", video]
    idx = 1
    audio_indices: list[int] = []
    subs_idx = None
    if audios is not None:
        for track in audios:
            args += ["-i", track]
            audio_indices.append(idx)
            idx += 1
    if subs is not None and not burn:
        args += ["-i", subs]
        subs_idx = idx
        idx += 1

    args += ["-map", "0:v:0"]
    if audio_indices:
        for ai in audio_indices:
            args += ["-map", f"{ai}:a:0"]
    else:
        args += ["-map", "0:a:0?"]
    if subs_idx is not None:
        args += ["-map", f"{subs_idx}:s:0"]

    if burn:
        assert subs is not None
        args += ["-vf", f"subtitles='{escape_filter_path(subs)}'"]
    if burn or not can_copy_video(video, output, video_codec):
        args += video_codec_args(default_codec_for(output), output)
    else:
        args += ["-c:v", "copy"]

    args += audio_codec_args(output)
    if audio_indices:
        args += ["-shortest"]

    if subs_idx is not None:
        args += ["-c:s", subtitle_codec(output)]

    args.append(output)
    return args


def attach(
    video: str | Path,
    output: str | Path,
    audio: Sequence[str | Path] | str | Path | None = None,
    subs: str | Path | None = None,
    burn: bool = False,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Mux audio file(s) and/or a subtitle onto a video (burn subs when ``burn``).

    ``audio`` may be a single path or a list of paths (one output track each).
    """
    from vidfix.core.ffmpeg import CODEC_PROBE_NAMES
    from vidfix.core.formats import prepare_output
    from vidfix.core.probe import probe

    runner = runner or FFmpegRunner()
    if audio is None:
        audios = None
    elif isinstance(audio, (str, Path)):
        audios = [str(audio)]
    else:
        audios = [str(a) for a in audio]
    for extra in [*(audios or []), *([str(subs)] if subs is not None else [])]:
        if not Path(extra).is_file():
            raise InvalidSpecError(f"File not found: {extra}")
    source = probe(video, runner=runner)
    if source.video_codec == "none":
        raise InvalidSpecError(f"{video} has no video to attach onto.")
    validate_fps(Fraction(source.fps), str(output))
    kept = [source.audio] if not audios and source.audio is not None else []
    for track in audios or []:
        track_audio = probe(track, runner=runner).audio
        if track_audio is None:
            raise InvalidSpecError(f"{track} has no audio track to attach.")
        kept.append(track_audio)
    for info in kept:
        validate_channels(info.channels or 0, str(output))
    by_probe_name = {probed: name for name, probed in CODEC_PROBE_NAMES.items()}
    args = build_attach_args(
        str(video),
        str(output),
        audios=audios,
        subs=str(subs) if subs is not None else None,
        burn=burn,
        video_codec=by_probe_name.get(source.video_codec),
    )
    prepare_output(output, video, *(audios or []), *([subs] if subs is not None else []))
    if burn:
        from vidfix.core.generate import drawtext_runner

        runner = drawtext_runner(runner)
    runner.run(args, on_progress=on_progress)
    return Path(output)
