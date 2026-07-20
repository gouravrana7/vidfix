"""Attach existing streams onto a video: external audio and/or a subtitle file.

Subtitles go in as a soft (toggle-able) track by default, or burned into the
picture with ``burn=True``. Pure FFmpeg muxing — no re-encode of the video
unless subtitles are burned in.
"""

from __future__ import annotations

from pathlib import Path

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


def subtitle_codec(output: str) -> str:
    """The soft-subtitle codec the output container wants (mov_text/srt/…)."""
    return SUBTITLE_CODECS.get(Path(output).suffix.lower(), "copy")


def build_attach_args(
    video: str,
    output: str,
    audio: str | None = None,
    subs: str | None = None,
    burn: bool = False,
) -> list[str]:
    """Pure builder for the attach/mux FFmpeg argument list."""
    from vidfix.core.generate import escape_filter_path

    if audio is None and subs is None:
        raise InvalidSpecError("Nothing to attach: pass an audio file, a subtitle file, or both.")

    out_ext = Path(output).suffix.lower()
    if subs is not None and not burn and out_ext not in SUBTITLE_CODECS:
        raise InvalidSpecError(
            f"{out_ext} can't hold a soft subtitle track; use .mp4/.mov/.mkv/.webm, "
            "or add --burn to burn the subtitles into the picture."
        )

    args = ["-i", video]
    idx = 1
    audio_idx = subs_idx = None
    if audio is not None:
        args += ["-i", audio]
        audio_idx = idx
        idx += 1
    if subs is not None and not burn:
        args += ["-i", subs]
        subs_idx = idx
        idx += 1

    args += ["-map", "0:v:0"]
    args += ["-map", f"{audio_idx}:a:0"] if audio_idx is not None else ["-map", "0:a:0?"]
    if subs_idx is not None:
        args += ["-map", f"{subs_idx}:s:0"]

    if burn:
        assert subs is not None
        args += ["-vf", f"subtitles='{escape_filter_path(subs)}'"]
        args += video_codec_args(default_codec_for(output), output)
    else:
        args += ["-c:v", "copy"]

    if audio_idx is not None:
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
    audio: str | Path | None = None,
    subs: str | Path | None = None,
    burn: bool = False,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Mux an audio file and/or subtitle onto a video (burn subs when ``burn``)."""
    runner = runner or FFmpegRunner()
    if burn:
        from vidfix.core.generate import drawtext_runner

        runner = drawtext_runner(runner)
    else:
        # The video is stream-copied, so the source codec must fit the output box.
        from vidfix.core.capabilities import validate_codec
        from vidfix.core.ffmpeg import CODEC_PROBE_NAMES
        from vidfix.core.probe import probe

        source = probe(video, runner=runner)
        by_probe_name = {probed: name for name, probed in CODEC_PROBE_NAMES.items()}
        vidfix_codec = by_probe_name.get(source.video_codec)
        if vidfix_codec is not None:
            validate_codec(vidfix_codec, str(output))
    args = build_attach_args(
        str(video),
        str(output),
        audio=str(audio) if audio is not None else None,
        subs=str(subs) if subs is not None else None,
        burn=burn,
    )
    runner.run(args, on_progress=on_progress)
    return Path(output)
