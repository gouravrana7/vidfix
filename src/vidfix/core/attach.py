"""Attach existing streams onto a video: external audio and/or a subtitle file.

Subtitles go in as a soft (toggle-able) track by default, or burned into the
picture with ``burn=True``. Pure FFmpeg muxing — no re-encode of the video
unless subtitles are burned in.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from vidfix.core.capabilities import validate_audio_stream_count
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


ANNEXB_FILTERS = {"h264": "h264_mp4toannexb", "h265": "hevc_mp4toannexb"}

ANNEXB_CONTAINERS = frozenset({".mpg", ".mpeg", ".ts"})


def subtitle_codec(output: str) -> str:
    """The soft-subtitle codec the output container wants (mov_text/srt/…)."""
    return SUBTITLE_CODECS.get(Path(output).suffix.lower(), "copy")


def annexb_args(output: str, video_codec: str | None) -> list[str]:
    """Bitstream filter needed to stream-copy h264/h265 into MPEG program streams.

    The muxer writes whatever bytes it is handed; length-prefixed h264 (the mp4
    and mkv flavour) goes in without start codes and the video reads back as
    nothing at all. Some FFmpeg builds insert the filter for .ts on their own
    and some do not, so it is always passed explicitly.
    """
    if Path(output).suffix.lower() not in ANNEXB_CONTAINERS:
        return []
    bsf = ANNEXB_FILTERS.get(video_codec or "")
    return ["-bsf:v", bsf] if bsf else []


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
        args += video_codec_args(default_codec_for(output), output)
    else:
        args += ["-c:v", "copy", *annexb_args(output, video_codec)]

    if audio_indices:
        args += audio_codec_args(output)
        args += ["-shortest"]
    else:
        args += ["-c:a", "copy"]

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
    runner = runner or FFmpegRunner()
    vidfix_codec = None
    if burn:
        from vidfix.core.generate import drawtext_runner

        runner = drawtext_runner(runner)
    else:
        from vidfix.core.capabilities import validate_codec
        from vidfix.core.ffmpeg import CODEC_PROBE_NAMES
        from vidfix.core.probe import probe

        source = probe(video, runner=runner)
        by_probe_name = {probed: name for name, probed in CODEC_PROBE_NAMES.items()}
        vidfix_codec = by_probe_name.get(source.video_codec)
        if vidfix_codec is not None:
            validate_codec(vidfix_codec, str(output))
    if audio is None:
        audios = None
    elif isinstance(audio, (str, Path)):
        audios = [str(audio)]
    else:
        audios = [str(a) for a in audio]
    for extra in [*(audios or []), *([str(subs)] if subs is not None else [])]:
        if not Path(extra).is_file():
            raise InvalidSpecError(f"File not found: {extra}")
    args = build_attach_args(
        str(video),
        str(output),
        audios=audios,
        subs=str(subs) if subs is not None else None,
        burn=burn,
        video_codec=vidfix_codec,
    )
    runner.run(args, on_progress=on_progress)
    return Path(output)
