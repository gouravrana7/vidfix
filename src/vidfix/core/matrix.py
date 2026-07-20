"""Generate the cartesian product of fps x resolution variants of a video."""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import product
from pathlib import Path

from vidfix.core.convert import convert
from vidfix.core.ffmpeg import FFmpegRunner
from vidfix.exceptions import InvalidSpecError, VidfixError


@dataclass(frozen=True)
class MatrixJob:
    """One planned variant."""

    fps: str
    res: str
    output: Path


@dataclass(frozen=True)
class MatrixResult:
    """Outcome of one variant conversion."""

    job: MatrixJob
    ok: bool
    error: str | None = None


def default_jobs() -> int:
    return min(4, os.cpu_count() or 1)


def parse_list(spec: str, what: str) -> list[str]:
    """Split a comma-separated CLI list like '30,60' or '720p,1080p'."""
    items = [item.strip() for item in spec.split(",") if item.strip()]
    if not items:
        raise InvalidSpecError(f"Empty {what} list; expected e.g. '30,60'.")
    return items


def plan_matrix(
    input_path: str, outdir: str, fps_list: list[str], res_list: list[str]
) -> list[MatrixJob]:
    """Cartesian product of variants with ``{stem}_{fps}fps_{res}.mp4`` naming."""
    stem = Path(input_path).stem
    out = Path(outdir)
    return [
        MatrixJob(fps=fps, res=res, output=out / f"{stem}_{fps.replace('/', '-')}fps_{res}.mp4")
        for fps, res in product(fps_list, res_list)
    ]


def run_matrix(
    input_path: str | Path,
    outdir: str | Path,
    fps_list: list[str],
    res_list: list[str],
    codec: str = "h264",
    jobs: int | None = None,
    on_result: Callable[[MatrixResult], None] | None = None,
) -> list[MatrixResult]:
    """Convert all variants in parallel FFmpeg processes; never raises per-variant."""
    planned = plan_matrix(str(input_path), str(outdir), fps_list, res_list)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    runner = FFmpegRunner()

    def run_one(job: MatrixJob) -> MatrixResult:
        try:
            convert(input_path, job.output, fps=job.fps, res=job.res, codec=codec, runner=runner)
            return MatrixResult(job=job, ok=True)
        except VidfixError as exc:
            return MatrixResult(job=job, ok=False, error=str(exc))

    results: list[MatrixResult] = []
    with ThreadPoolExecutor(max_workers=jobs or default_jobs()) as pool:
        futures = [pool.submit(run_one, job) for job in planned]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            if on_result is not None:
                on_result(result)

    order = {job.output: i for i, job in enumerate(planned)}
    return sorted(results, key=lambda r: order[r.job.output])
