"""Universal format conversion: any picture or video to any other format.

Routing is by file extension: image↔image, video→any container (codec picked
per container), video→gif (two-pass palette in one filter graph), video→image
(first-frame grab), and video→audio (extract the audio track).
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

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac"}
VIDEO_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts", ".gif",
    ".mxf", ".mpg", ".mpeg", ".ogv", ".flv", ".wmv", ".3gp",
}  # fmt: skip

_GIF_FILTER = (
    "fps=12,scale='min(480,iw)':-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
)


def validate_output_ext(output: str, allowed: set[str], what: str = "output") -> None:
    """Reject an output whose extension isn't one the command can write."""
    ext = Path(output).suffix.lower()
    if ext not in allowed:
        got = f"extension {ext!r}" if ext else "no extension"
        raise InvalidSpecError(
            f"Can't tell the {what} format of {output!r} ({got}); "
            f"use one of: {', '.join(sorted(e.lstrip('.') for e in allowed))}."
        )


def media_kind(path: str) -> str:
    """Classify a path as 'image', 'audio', or 'video' by extension."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    supported = ", ".join(sorted(IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS))
    raise InvalidSpecError(f"Unsupported format {ext!r} for {path}; supported: {supported}.")


def build_format_args(input_path: str, output: str) -> list[str]:
    """Pure builder for a format-conversion FFmpeg argument list."""
    src, dst = media_kind(input_path), media_kind(output)
    out_ext = Path(output).suffix.lower()
    args = ["-i", input_path]

    if dst == "image":
        if src == "video":
            args += ["-frames:v", "1"]
        if out_ext in (".jpg", ".jpeg"):
            args += ["-q:v", "2"]
        return [*args, output]

    if dst == "audio":
        if src != "video":
            raise InvalidSpecError(
                f"Can only extract audio from a video, not from {src}; give a video input."
            )
        return [*args, "-vn", output]

    if src in ("image", "audio"):
        raise InvalidSpecError(
            f"{src.capitalize()} → video is not a format conversion; "
            "use 'vidfix generate' for test videos."
        )

    if out_ext == ".gif":
        return [*args, "-filter_complex", _GIF_FILTER, "-an", output]

    codec = default_codec_for(output)
    return [*args, *video_codec_args(codec, output), *audio_codec_args(output), output]


def to_format(
    input_path: str | Path,
    output: str | Path,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Convert any picture or video to the format implied by ``output``'s extension."""
    runner = runner or FFmpegRunner()
    args = build_format_args(str(input_path), str(output))
    if media_kind(str(output)) == "audio":
        from vidfix.core.probe import probe

        if probe(input_path, runner=runner).audio is None:
            raise InvalidSpecError(f"{input_path} has no audio track to extract.")
    runner.run(args, on_progress=on_progress)
    return Path(output)
