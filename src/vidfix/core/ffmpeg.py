"""FFmpeg binary discovery and subprocess execution.

Command *construction* lives in the feature modules as pure functions returning
``list[str]``; this module only discovers binaries and runs commands, streaming
``-progress`` output to an optional callback.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from vidfix.exceptions import ConversionError, FFmpegNotFoundError, InvalidSpecError

#: Flags prepended to every FFmpeg invocation.
BASE_FLAGS: tuple[str, ...] = ("-hide_banner", "-nostdin", "-y")

#: Supported video codecs mapped to their encoder arguments.
VIDEO_CODECS: dict[str, tuple[str, ...]] = {
    "h264": ("-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "23"),
    "h265": (
        "-c:v", "libx265", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "28",
        "-tag:v", "hvc1",
    ),
    "prores": ("-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"),
    "vp9": ("-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-pix_fmt", "yuv420p"),
}  # fmt: skip

#: Encoder names as they appear in probe output, keyed by vidfix codec name.
CODEC_PROBE_NAMES: dict[str, str] = {
    "h264": "h264",
    "h265": "hevc",
    "prores": "prores",
    "vp9": "vp9",
}


def video_codec_args(codec: str, output: str | None = None) -> list[str]:
    """Encoder arguments for a supported codec name.

    When ``output`` is given, codec/container mismatches FFmpeg would reject
    (prores has no mp4 tag) fail early with a friendly message.
    """
    if codec not in VIDEO_CODECS:
        supported = ", ".join(sorted(VIDEO_CODECS))
        raise InvalidSpecError(f"Unsupported codec {codec!r}; expected one of: {supported}.")
    if codec == "prores" and output and output.lower().endswith(".mp4"):
        raise InvalidSpecError("prores cannot go in an .mp4 file; use a .mov or .mkv output.")
    return list(VIDEO_CODECS[codec])


def audio_codec_args(output: str) -> list[str]:
    """Audio encoder arguments picked by output container extension."""
    if output.lower().endswith(".webm"):
        return ["-c:a", "libopus"]
    return ["-c:a", "aac", "-b:a", "128k"]


_STDERR_LIMIT = 64_000  # keep only the newest chunk of stderr for error reporting


@dataclass(frozen=True)
class ProgressEvent:
    """A snapshot of FFmpeg's ``-progress`` output."""

    seconds: float
    frame: int | None = None
    speed: float | None = None
    done: bool = False


@dataclass(frozen=True)
class FFmpegResult:
    """Outcome of a completed FFmpeg run."""

    args: tuple[str, ...]
    returncode: int
    stderr: str


ProgressCallback = Callable[[ProgressEvent], None]


def find_ffmpeg() -> str:
    """Locate an FFmpeg binary: bundled imageio-ffmpeg first, then system PATH."""
    try:
        import imageio_ffmpeg

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # any failure (import, download, permissions) falls through to PATH
        system = shutil.which("ffmpeg")
        if system:
            return system
    raise FFmpegNotFoundError(
        "No FFmpeg binary found. Install vidfix with its dependencies "
        "(imageio-ffmpeg bundles FFmpeg) or install ffmpeg on your PATH."
    )


def find_ffprobe() -> str | None:
    """Locate a system ffprobe, or None (imageio-ffmpeg does not bundle it)."""
    return shutil.which("ffprobe")


def parse_progress_line(line: str) -> tuple[str, str] | None:
    """Parse one ``key=value`` line from FFmpeg ``-progress`` output."""
    line = line.strip()
    if not line or "=" not in line:
        return None
    key, _, value = line.partition("=")
    return key.strip(), value.strip()


def progress_events(lines: Iterable[str]) -> Iterable[ProgressEvent]:
    """Convert a stream of ``-progress`` lines into :class:`ProgressEvent`s.

    FFmpeg emits blocks of key=value pairs terminated by a ``progress=`` line.
    """
    seconds = 0.0
    frame: int | None = None
    speed: float | None = None
    for raw in lines:
        parsed = parse_progress_line(raw)
        if parsed is None:
            continue
        key, value = parsed
        if key == "out_time_us" and value.lstrip("-").isdigit():
            seconds = max(0.0, int(value) / 1_000_000)
        elif key == "frame" and value.isdigit():
            frame = int(value)
        elif key == "speed" and value.endswith("x"):
            try:
                speed = float(value[:-1])
            except ValueError:
                speed = None
        elif key == "progress":
            yield ProgressEvent(seconds=seconds, frame=frame, speed=speed, done=value == "end")


class FFmpegRunner:
    """Runs FFmpeg commands with captured stderr and optional progress reporting."""

    def __init__(self, ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path
        self._ffprobe_resolved = ffprobe_path is not None

    @property
    def ffmpeg_path(self) -> str:
        if self._ffmpeg_path is None:
            self._ffmpeg_path = find_ffmpeg()
        return self._ffmpeg_path

    @property
    def ffprobe_path(self) -> str | None:
        if not self._ffprobe_resolved:
            self._ffprobe_path = find_ffprobe()
            self._ffprobe_resolved = True
        return self._ffprobe_path

    def build_command(self, args: list[str], with_progress: bool = False) -> list[str]:
        """Prepend the binary path and base flags to feature-built arguments."""
        command = [self.ffmpeg_path, *BASE_FLAGS]
        if with_progress:
            command += ["-progress", "pipe:1", "-nostats"]
        return command + args

    def run(
        self,
        args: list[str],
        on_progress: ProgressCallback | None = None,
        check: bool = True,
    ) -> FFmpegResult:
        """Execute FFmpeg with ``args`` (everything after the base flags).

        Raises :class:`ConversionError` (with the stderr tail) on a non-zero
        exit when ``check`` is true.
        """
        command = self.build_command(args, with_progress=on_progress is not None)
        try:
            if on_progress is None:
                completed = subprocess.run(command, capture_output=True, text=True, check=False)
                result = FFmpegResult(
                    args=tuple(command),
                    returncode=completed.returncode,
                    stderr=completed.stderr[-_STDERR_LIMIT:],
                )
            else:
                result = self._run_with_progress(command, on_progress)
        except FileNotFoundError as exc:
            raise FFmpegNotFoundError(f"FFmpeg binary vanished: {command[0]}") from exc

        if check and result.returncode != 0:
            raise ConversionError(
                f"FFmpeg exited with code {result.returncode}",
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return result

    def _run_with_progress(self, command: list[str], on_progress: ProgressCallback) -> FFmpegResult:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stderr_chunks: list[str] = []

        def drain_stderr() -> None:
            if process.stderr is not None:
                for chunk in process.stderr:
                    stderr_chunks.append(chunk)

        drain = threading.Thread(target=drain_stderr, daemon=True)
        drain.start()

        if process.stdout is not None:
            for event in progress_events(iter(process.stdout.readline, "")):
                on_progress(event)

        returncode = process.wait()
        drain.join(timeout=5)
        stderr = "".join(stderr_chunks)
        return FFmpegResult(
            args=tuple(command), returncode=returncode, stderr=stderr[-_STDERR_LIMIT:]
        )

    def version(self) -> str:
        """Return the first line of ``ffmpeg -version`` output."""
        completed = subprocess.run(
            [self.ffmpeg_path, "-version"], capture_output=True, text=True, check=False
        )
        first_line = completed.stdout.splitlines()[0] if completed.stdout else ""
        return first_line or "unknown"
