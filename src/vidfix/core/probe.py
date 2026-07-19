"""Media metadata probing.

Prefers system ``ffprobe -print_format json`` when available; falls back to
parsing the banner ``ffmpeg -i`` prints on stderr (imageio-ffmpeg ships no
ffprobe). Parsers are pure functions over captured text.
"""

from __future__ import annotations

import json
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vidfix.core.duration import FPS_LABELS, parse_fps
from vidfix.core.ffmpeg import FFmpegRunner
from vidfix.exceptions import ProbeError

#: ISO base-media major_brand tags mapped to friendly container names.
MAJOR_BRANDS: dict[str, str] = {
    "isom": "mp4",
    "mp41": "mp4",
    "mp42": "mp4",
    "avc1": "mp4",
    "qt": "mov",
    "M4A": "m4a",
}


def friendly_container(demuxer: str, major_brand: str | None, path: str) -> str:
    """Human-friendly container name from the raw demuxer string.

    ffprobe's format_name is the demuxer alias list (e.g.
    "mov,mp4,m4a,3gp,3g2,mj2"); the format tag major_brand pins the real
    container. When the brand is missing (mkv/webm), the file extension is
    the sanity fallback for multi-name demuxers.
    """
    brand = (major_brand or "").strip()
    if brand in MAJOR_BRANDS:
        return MAJOR_BRANDS[brand]
    if brand.startswith("3g"):  # 3gp4/3gp5/3gp6/3ge6/... — the 3GPP brand family
        return "3gp"
    extension = Path(path).suffix.lstrip(".").lower()
    names = demuxer.split(",")
    if extension and (extension in names or len(names) > 1):
        return extension
    return demuxer


class AudioInfo(BaseModel):
    """Audio stream summary."""

    codec: str
    sample_rate: int | None = None
    channels: int | None = None


class MediaInfo(BaseModel):
    """Normalized metadata for one media file."""

    path: str
    container: str  # friendly name, e.g. "mp4"
    demuxer: str | None = None  # raw ffprobe/ffmpeg format name, e.g. "mov,mp4,m4a,3gp,3g2,mj2"
    major_brand: str | None = None  # ISO base-media brand tag, e.g. "isom"
    duration: float
    # Video fields default to zero-values for audio-only files (e.g. wav/mp3),
    # so spec checks against them fail honestly instead of crashing.
    width: int = 0
    height: int = 0
    fps: str = "0"  # exact rational text, e.g. "30000/1001" or "30"
    video_codec: str = "none"
    pix_fmt: str | None = None
    bitrate: int | None = None  # bits per second, container-level
    audio: AudioInfo | None = None

    @property
    def fps_fraction(self) -> Fraction:
        return Fraction(self.fps)

    @property
    def fps_float(self) -> float:
        return float(self.fps_fraction)

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def fps_display(self) -> str:
        """QA-friendly fps text, e.g. ``59.940 (df60, 60000/1001)``."""
        label = FPS_LABELS.get(self.fps_fraction)
        exact = f"{label}, {self.fps}" if label else self.fps
        return f"{self.fps_float:.3f} ({exact})"


def parse_ffprobe_json(payload: str, path: str) -> MediaInfo:
    """Build a :class:`MediaInfo` from ``ffprobe -print_format json`` output."""
    try:
        data: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe returned invalid JSON for {path}") from exc

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None and audio is None:
        raise ProbeError(f"No media streams found in {path}")

    video_fields: dict[str, Any] = {}
    if video is not None:
        rate = video.get("avg_frame_rate") or "0/0"
        if rate in ("0/0", "0"):
            rate = video.get("r_frame_rate") or "0/0"
        try:
            fps = parse_fps(rate)
        except Exception as exc:
            raise ProbeError(f"Cannot determine frame rate of {path} (got {rate!r})") from exc
        video_fields = {
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": str(fps),
            "video_codec": video.get("codec_name", "unknown"),
            "pix_fmt": video.get("pix_fmt"),
        }

    # Still images have no duration; report 0 rather than failing the probe.
    duration = _first_float(fmt.get("duration"), (video or {}).get("duration")) or 0.0

    audio_info = None
    if audio is not None:
        audio_info = AudioInfo(
            codec=audio.get("codec_name", "unknown"),
            sample_rate=_first_int(audio.get("sample_rate")),
            channels=audio.get("channels"),
        )

    demuxer = fmt.get("format_name", "unknown")
    brand = str(fmt.get("tags", {}).get("major_brand", "")).strip() or None

    return MediaInfo(
        path=path,
        container=friendly_container(demuxer, brand, path),
        demuxer=demuxer,
        major_brand=brand,
        duration=duration,
        bitrate=_first_int(fmt.get("bit_rate")),
        audio=audio_info,
        **video_fields,
    )


_BANNER_INPUT_RE = re.compile(r"Input #0, ([^,]+(?:,[^,]+)*?), from ")
_BANNER_BRAND_RE = re.compile(r"major_brand\s*:\s*(\S+)")
_BANNER_DURATION_RE = re.compile(
    r"Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)(?:, start: [\d.-]+)?, bitrate: (\d+|N/A)"
)
_BANNER_VIDEO_RE = re.compile(
    r"Stream #\d+:\d+.*?: Video: (?P<codec>\w+)[^,]*, (?P<pix_fmt>\w+)(?:\([^)]*\))?, "
    r"(?P<width>\d+)x(?P<height>\d+)(?P<rest>.*)"
)
_BANNER_FPS_RE = re.compile(r"(\d+(?:\.\d+)?) fps")
_BANNER_TBR_RE = re.compile(r"(\d+(?:\.\d+)?) tbr")
_BANNER_AUDIO_RE = re.compile(
    r"Stream #\d+:\d+.*?: Audio: (?P<codec>\w+).*?, (?P<rate>\d+) Hz, (?P<layout>[\w.]+)"
)
_CHANNEL_LAYOUTS = {"mono": 1, "stereo": 2, "2.1": 3, "5.1": 6, "7.1": 8}


def parse_ffmpeg_banner(stderr: str, path: str) -> MediaInfo:
    """Build a :class:`MediaInfo` from the ``ffmpeg -i`` stderr banner (fallback path)."""
    video = _BANNER_VIDEO_RE.search(stderr)
    audio_m = _BANNER_AUDIO_RE.search(stderr)
    duration_m = _BANNER_DURATION_RE.search(stderr)
    if video is None and audio_m is None:
        raise ProbeError(
            f"Cannot probe {path}: not a recognizable media file.\n{stderr.strip()[-500:]}"
        )

    # Still images print "Duration: N/A"; report 0 rather than failing the probe.
    duration = 0.0
    bitrate_text = "N/A"
    if duration_m:
        hours, minutes, seconds = (
            int(duration_m.group(1)),
            int(duration_m.group(2)),
            float(duration_m.group(3)),
        )
        duration = hours * 3600 + minutes * 60 + seconds
        bitrate_text = duration_m.group(4)

    video_fields: dict[str, Any] = {}
    if video is not None:
        fps_m = _BANNER_FPS_RE.search(video.group("rest")) or _BANNER_TBR_RE.search(
            video.group("rest")
        )
        if fps_m is None:
            raise ProbeError(f"Cannot determine frame rate of {path} from ffmpeg output.")
        video_fields = {
            "width": int(video.group("width")),
            "height": int(video.group("height")),
            "fps": str(parse_fps(fps_m.group(1))),
            "video_codec": video.group("codec"),
            "pix_fmt": video.group("pix_fmt"),
        }

    container_m = _BANNER_INPUT_RE.search(stderr)
    demuxer = container_m.group(1) if container_m else "unknown"
    brand_m = _BANNER_BRAND_RE.search(stderr)
    brand = brand_m.group(1) if brand_m else None

    audio_info = None
    if audio_m:
        audio_info = AudioInfo(
            codec=audio_m.group("codec"),
            sample_rate=int(audio_m.group("rate")),
            channels=_CHANNEL_LAYOUTS.get(audio_m.group("layout")),
        )

    return MediaInfo(
        path=path,
        container=friendly_container(demuxer, brand, path),
        demuxer=demuxer,
        major_brand=brand,
        duration=duration,
        bitrate=int(bitrate_text) * 1000 if bitrate_text.isdigit() else None,
        audio=audio_info,
        **video_fields,
    )


def probe(input_path: str | Path, runner: FFmpegRunner | None = None) -> MediaInfo:
    """Probe a media file, preferring system ffprobe over the ffmpeg-banner fallback."""
    path = Path(input_path)
    if not path.is_file():
        raise ProbeError(f"File not found: {path}")
    runner = runner or FFmpegRunner()

    ffprobe = runner.ffprobe_path
    if ffprobe:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return parse_ffprobe_json(completed.stdout, str(path))
        # ffprobe failed (corrupt file, odd container) — fall through to ffmpeg banner

    result = runner.run(["-i", str(path)], check=False)  # exits 1: no output file requested
    return parse_ffmpeg_banner(result.stderr, str(path))


def _first_float(*values: Any) -> float | None:
    for value in values:
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return None
