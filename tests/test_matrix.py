"""Unit tests for matrix planning (no FFmpeg execution)."""

from __future__ import annotations

import pytest

from vidfix.core.matrix import default_jobs, parse_list, plan_matrix
from vidfix.exceptions import InvalidSpecError


class TestParseList:
    def test_basic(self) -> None:
        assert parse_list("30,60", "fps") == ["30", "60"]

    def test_whitespace_and_blanks(self) -> None:
        assert parse_list(" 30 , 60 ,", "fps") == ["30", "60"]

    def test_empty(self) -> None:
        with pytest.raises(InvalidSpecError, match="Empty fps"):
            parse_list(" , ", "fps")


class TestPlanMatrix:
    def test_cartesian_product_and_naming(self) -> None:
        jobs = plan_matrix("clip.mp4", "out", ["30", "60"], ["720p", "1080p"])
        names = [job.output.name for job in jobs]
        assert names == [
            "clip_30fps_720p.mp4",
            "clip_30fps_1080p.mp4",
            "clip_60fps_720p.mp4",
            "clip_60fps_1080p.mp4",
        ]

    def test_rational_fps_filename_safe(self) -> None:
        jobs = plan_matrix("clip.mp4", "out", ["30000/1001"], ["720p"])
        assert jobs[0].output.name == "clip_30000-1001fps_720p.mp4"


def test_default_jobs_capped() -> None:
    assert 1 <= default_jobs() <= 4
