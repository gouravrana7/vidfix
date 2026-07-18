"""Universal format conversion: any picture or video to any other format.

Routing is by file extension: image↔image, video→any container (codec picked
per container), video→gif (two-pass palette in one filter graph), and
video→image (first-frame grab).
"""

from __future__ import annotations

from pathlib import Path

from vidfix.core.ffmpeg import FFmpegRunner, ProgressCallback, audio_codec_args, video_codec_args
from vidfix.exceptions import InvalidSpecError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts", ".gif"}

#: Container extensions mapped to the vidfix codec that plays everywhere in them.
CONTAINER_CODECS = {".webm": "vp9"}

_GIF_FILTER = (
    "fps=12,scale='min(480,iw)':-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
)


def media_kind(path: str) -> str:
    """Classify a path as 'image' or 'video' by extension."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    supported = ", ".join(sorted(IMAGE_EXTS | VIDEO_EXTS))
    raise InvalidSpecError(f"Unsupported format {ext!r} for {path}; supported: {supported}.")


def build_format_args(input_path: str, output: str) -> list[str]:
    """Pure builder for a format-conversion FFmpeg argument list."""
    src, dst = media_kind(input_path), media_kind(output)
    out_ext = Path(output).suffix.lower()
    args = ["-i", input_path]

    if dst == "image":
        if src == "video":
            args += ["-frames:v", "1"]  # first-frame grab / thumbnail
        if out_ext in (".jpg", ".jpeg"):
            args += ["-q:v", "2"]
        return [*args, output]

    if src == "image":
        raise InvalidSpecError(
            "Image → video is not a format conversion; use 'vidfix generate' for test videos."
        )

    if out_ext == ".gif":
        return [*args, "-filter_complex", _GIF_FILTER, "-an", output]

    codec = CONTAINER_CODECS.get(out_ext, "h264")
    return [*args, *video_codec_args(codec, output), *audio_codec_args(output), output]


def to_format(
    input_path: str | Path,
    output: str | Path,
    runner: FFmpegRunner | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Convert any picture or video to the format implied by ``output``'s extension."""
    args = build_format_args(str(input_path), str(output))
    (runner or FFmpegRunner()).run(args, on_progress=on_progress)
    return Path(output)
