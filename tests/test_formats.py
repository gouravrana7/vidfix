"""Unit tests for universal format conversion routing (no FFmpeg execution)."""

from __future__ import annotations

import pytest

from vidfix.core.formats import build_format_args, media_kind
from vidfix.exceptions import InvalidSpecError


class TestMediaKind:
    @pytest.mark.parametrize("path", ["a.png", "b.JPG", "c.webp", "d.tiff"])
    def test_images(self, path: str) -> None:
        assert media_kind(path) == "image"

    @pytest.mark.parametrize("path", ["a.mp4", "b.MOV", "c.webm", "d.gif"])
    def test_videos(self, path: str) -> None:
        assert media_kind(path) == "video"

    def test_unsupported(self) -> None:
        with pytest.raises(InvalidSpecError, match="Unsupported format"):
            media_kind("doc.pdf")


class TestBuildFormatArgs:
    def test_image_to_image(self) -> None:
        assert build_format_args("in.png", "out.webp") == ["-i", "in.png", "out.webp"]

    def test_image_to_jpg_sets_quality(self) -> None:
        args = build_format_args("in.png", "out.jpg")
        assert args[args.index("-q:v") + 1] == "2"

    def test_video_to_image_grabs_first_frame(self) -> None:
        args = build_format_args("in.mp4", "thumb.png")
        assert args[args.index("-frames:v") + 1] == "1"

    def test_video_to_gif_uses_palette(self) -> None:
        args = build_format_args("in.mp4", "out.gif")
        graph = args[args.index("-filter_complex") + 1]
        assert "palettegen" in graph and "paletteuse" in graph
        assert "-an" in args

    def test_video_to_webm_uses_vp9_opus(self) -> None:
        args = build_format_args("in.mp4", "out.webm")
        assert "libvpx-vp9" in args and "libopus" in args

    def test_video_to_mov_uses_h264(self) -> None:
        assert "libx264" in build_format_args("in.webm", "out.mov")

    def test_image_to_video_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="generate"):
            build_format_args("in.png", "out.mp4")
