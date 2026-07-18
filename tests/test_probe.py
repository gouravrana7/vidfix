"""Unit tests for probe parsers using canned ffprobe/ffmpeg output."""

from __future__ import annotations

import pytest

from vidfix.core.probe import friendly_container, parse_ffmpeg_banner, parse_ffprobe_json
from vidfix.exceptions import ProbeError

FFPROBE_JSON = """
{
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1280,
            "height": 720,
            "pix_fmt": "yuv420p",
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30000/1001"
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "sample_rate": "44100",
            "channels": 2
        }
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "30.030000",
        "bit_rate": "1200000"
    }
}
"""

FFMPEG_BANNER = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'clip.mp4':
  Metadata:
    major_brand     : isom
  Duration: 00:00:30.03, start: 0.000000, bitrate: 1200 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637634), yuv420p(progressive), \
1280x720 [SAR 1:1 DAR 16:9], 1100 kb/s, 29.97 fps, 29.97 tbr, 30k tbn
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6D6134), 44100 Hz, stereo, fltp, 96 kb/s
At least one output file must be specified
"""


class TestParseFfprobeJson:
    def test_full_parse(self) -> None:
        info = parse_ffprobe_json(FFPROBE_JSON, "clip.mp4")
        assert info.width == 1280
        assert info.height == 720
        assert info.fps == "30000/1001"
        assert info.fps_float == pytest.approx(29.97, abs=0.01)
        assert info.duration == pytest.approx(30.03)
        assert info.video_codec == "h264"
        assert info.pix_fmt == "yuv420p"
        assert info.bitrate == 1200000
        assert info.audio is not None
        assert info.audio.codec == "aac"
        assert info.audio.sample_rate == 44100
        assert info.audio.channels == 2

    def test_no_video_stream(self) -> None:
        with pytest.raises(ProbeError, match="No video stream"):
            parse_ffprobe_json('{"streams": [], "format": {}}', "audio.mp3")

    def test_invalid_json(self) -> None:
        with pytest.raises(ProbeError, match="invalid JSON"):
            parse_ffprobe_json("not json", "x.mp4")

    def test_avg_frame_rate_zero_falls_back_to_r(self) -> None:
        payload = FFPROBE_JSON.replace('"avg_frame_rate": "30000/1001"', '"avg_frame_rate": "0/0"')
        info = parse_ffprobe_json(payload, "clip.mp4")
        assert info.fps == "30000/1001"


class TestParseFfmpegBanner:
    def test_full_parse(self) -> None:
        info = parse_ffmpeg_banner(FFMPEG_BANNER, "clip.mp4")
        assert info.width == 1280
        assert info.height == 720
        assert info.fps == "30000/1001"  # 29.97 mapped to the exact NTSC rational
        assert info.duration == pytest.approx(30.03)
        assert info.video_codec == "h264"
        assert info.pix_fmt == "yuv420p"
        assert info.bitrate == 1200000
        assert info.container == "mp4"  # friendly name from major_brand isom
        assert info.demuxer == "mov,mp4,m4a,3gp,3g2,mj2"
        assert info.major_brand == "isom"
        assert info.audio is not None
        assert info.audio.codec == "aac"
        assert info.audio.channels == 2

    def test_no_audio(self) -> None:
        banner = "\n".join(line for line in FFMPEG_BANNER.splitlines() if "Audio" not in line)
        info = parse_ffmpeg_banner(banner, "clip.mp4")
        assert info.audio is None

    def test_pix_fmt_qualifier_with_comma(self) -> None:
        # ffmpeg writes e.g. "yuv420p(tv, progressive)" — comma inside parens
        banner = FFMPEG_BANNER.replace("yuv420p(progressive)", "yuv420p(tv, progressive)")
        info = parse_ffmpeg_banner(banner, "clip.mp4")
        assert info.pix_fmt == "yuv420p"
        assert info.width == 1280

    def test_garbage_input(self) -> None:
        with pytest.raises(ProbeError, match="not a recognizable media file"):
            parse_ffmpeg_banner("clip.txt: Invalid data found", "clip.txt")


def _ffprobe_json(format_name: str, major_brand: str | None = None) -> str:
    """Minimal ffprobe payload with one video stream and the given format block."""
    tags = f', "tags": {{"major_brand": "{major_brand}"}}' if major_brand else ""
    return (
        '{"streams": [{"codec_type": "video", "codec_name": "h264", "width": 160,'
        ' "height": 120, "avg_frame_rate": "30/1"}],'
        f' "format": {{"format_name": "{format_name}", "duration": "1.0"{tags}}}}}'
    )


class TestFriendlyContainer:
    @pytest.mark.parametrize(
        ("demuxer", "brand", "path", "expected"),
        [
            ("mov,mp4,m4a,3gp,3g2,mj2", "isom", "a.mp4", "mp4"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "mp41", "a.mp4", "mp4"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "mp42", "a.mp4", "mp4"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "avc1", "a.mp4", "mp4"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "qt", "a.mov", "mov"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "M4A", "a.m4a", "m4a"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "3gp4", "a.3gp", "3gp"),
            ("mov,mp4,m4a,3gp,3g2,mj2", "3gp6", "a.3gp", "3gp"),
            # no major_brand: extension is the sanity fallback for multi-name demuxers
            ("matroska,webm", None, "a.mkv", "mkv"),
            ("matroska,webm", None, "a.webm", "webm"),
            ("mov,mp4,m4a,3gp,3g2,mj2", None, "a.mp4", "mp4"),
            # single-name demuxers pass through untouched
            ("avi", None, "a.avi", "avi"),
            ("flv", None, "weird.bin", "flv"),
        ],
    )
    def test_mapping(self, demuxer: str, brand: str | None, path: str, expected: str) -> None:
        assert friendly_container(demuxer, brand, path) == expected

    def test_unknown_brand_falls_back_to_extension(self) -> None:
        assert friendly_container("mov,mp4,m4a,3gp,3g2,mj2", "wxyz", "a.mp4") == "mp4"


class TestContainerFromFfprobeJson:
    def test_mp4_major_brand(self) -> None:
        info = parse_ffprobe_json(_ffprobe_json("mov,mp4,m4a,3gp,3g2,mj2", "isom"), "clip.mp4")
        assert info.container == "mp4"
        assert info.major_brand == "isom"
        assert info.demuxer == "mov,mp4,m4a,3gp,3g2,mj2"

    def test_mov_qt_brand_padded(self) -> None:
        # ffprobe pads the qt brand with trailing spaces
        info = parse_ffprobe_json(_ffprobe_json("mov,mp4,m4a,3gp,3g2,mj2", "qt  "), "clip.mov")
        assert info.container == "mov"
        assert info.major_brand == "qt"

    def test_mkv_no_brand(self) -> None:
        info = parse_ffprobe_json(_ffprobe_json("matroska,webm"), "clip.mkv")
        assert info.container == "mkv"
        assert info.major_brand is None

    def test_webm_no_brand(self) -> None:
        info = parse_ffprobe_json(_ffprobe_json("matroska,webm"), "clip.webm")
        assert info.container == "webm"

    @pytest.mark.parametrize(
        ("rate", "expected"),
        [
            ("60000/1001", "59.940 (df60, 60000/1001)"),
            ("30000/1001", "29.970 (df30, 30000/1001)"),
            ("24000/1001", "23.976 (film23976, 24000/1001)"),
            ("25/1", "25.000 (pal25, 25)"),
            ("30/1", "30.000 (30)"),  # non-broadcast rates have no label
        ],
    )
    def test_fps_display_labels(self, rate: str, expected: str) -> None:
        payload = _ffprobe_json("mov,mp4,m4a,3gp,3g2,mj2", "isom").replace("30/1", rate)
        info = parse_ffprobe_json(payload, "clip.mp4")
        assert info.fps_display == expected

    def test_json_dump_has_both_fields(self) -> None:
        info = parse_ffprobe_json(_ffprobe_json("mov,mp4,m4a,3gp,3g2,mj2", "isom"), "clip.mp4")
        dumped = info.model_dump()
        assert dumped["container"] == "mp4"
        assert dumped["demuxer"] == "mov,mp4,m4a,3gp,3g2,mj2"
