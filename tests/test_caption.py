"""Unit tests for caption filter building (no FFmpeg execution)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidfix.core.caption import caption_filter, write_caption_file
from vidfix.exceptions import InvalidSpecError


class TestCaptionFilter:
    def test_defaults(self) -> None:
        f = caption_filter("/tmp/c.txt")
        assert f.startswith("drawtext=textfile='/tmp/c.txt'")
        assert "fontsize=h/12" in f
        assert "fontcolor=white" in f
        assert "y=h-text_h-h/20" in f
        assert "enable=" not in f

    @pytest.mark.parametrize(
        ("position", "fragment"),
        [
            ("top", "x=(w-text_w)/2:y=h/20"),
            ("center", "x=(w-text_w)/2:y=(h-text_h)/2"),
            ("bottom", "x=(w-text_w)/2:y=h-text_h-h/20"),
            ("top-left", "x=w/20:y=h/20"),
            ("top-right", "x=w-text_w-w/20:y=h/20"),
            ("left", "x=w/20:y=(h-text_h)/2"),
            ("right", "x=w-text_w-w/20:y=(h-text_h)/2"),
            ("bottom-left", "x=w/20:y=h-text_h-h/20"),
            ("bottom-right", "x=w-text_w-w/20:y=h-text_h-h/20"),
        ],
    )
    def test_positions(self, position: str, fragment: str) -> None:
        assert fragment in caption_filter("/tmp/c.txt", position=position)

    def test_nine_positions_available(self) -> None:
        from vidfix.core.caption import POSITIONS

        assert len(POSITIONS) == 9

    def test_bad_position(self) -> None:
        with pytest.raises(InvalidSpecError, match="Unknown position"):
            caption_filter("/tmp/c.txt", position="middle")

    def test_timing_window(self) -> None:
        f = caption_filter("/tmp/c.txt", start=1.5, end=4.0)
        assert "enable='between(t,1.5,4.0)'" in f

    def test_start_only(self) -> None:
        assert "between(t,2.0," in caption_filter("/tmp/c.txt", start=2.0)

    def test_windows_textfile_path_escaped(self) -> None:
        f = caption_filter("C:\\Temp\\c.txt")
        assert "textfile='C\\:/Temp/c.txt'" in f

    def test_font_included(self) -> None:
        assert "fontfile='/f/mono.ttf'" in caption_filter("/tmp/c.txt", font="/f/mono.ttf")


class TestWriteCaptionFile:
    def test_roundtrip(self) -> None:
        path = write_caption_file("hello: it's 100% 'fine'\\n")
        try:
            assert Path(path).read_text(encoding="utf-8") == "hello: it's 100% 'fine'\\n"
        finally:
            Path(path).unlink()

    def test_empty_rejected(self) -> None:
        with pytest.raises(InvalidSpecError, match="empty"):
            write_caption_file("   ")
