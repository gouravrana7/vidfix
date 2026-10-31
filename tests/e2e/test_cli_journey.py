"""End to end: the real CLI binary, real files, no mocks.

The rest of the suite covers this code two other ways -- `test_cli.py` drives
the commands with the FFmpeg layer mocked, and `test_integration.py` calls the
Python functions against real FFmpeg. Neither runs the thing a user runs. If
argument wiring, exit codes or file output broke, both would still pass.

These are the slowest tests in the repo on purpose. Every clip is one second
at 160x120.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from vidfix import probe

pytestmark = pytest.mark.e2e

TIMEOUT = 300


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "vidfix", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        input="",
    )


def ok(*args: str) -> subprocess.CompletedProcess[str]:
    done = cli(*args)
    assert done.returncode == 0, f"vidfix {' '.join(args)} failed:\n{done.stdout}\n{done.stderr}"
    return done


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One generated clip, made through the CLI, reused by the read-only tests."""
    out = tmp_path_factory.mktemp("e2e") / "base.mp4"
    ok("generate", "-o", str(out), "--fps", "30", "--duration", "1", "--res", "160x120")
    return out


class TestGenerate:
    def test_it_writes_a_file_that_matches_the_spec(self, clip: Path) -> None:
        assert clip.exists() and clip.stat().st_size > 0
        info = probe(clip)
        assert (info.width, info.height) == (160, 120)
        assert info.fps_float == pytest.approx(30, abs=0.01)
        assert info.duration == pytest.approx(1.0, abs=0.15)

    def test_a_missing_output_flag_is_a_clean_error(self, tmp_path: Path) -> None:
        done = cli("generate", "--fps", "30")
        assert done.returncode != 0
        assert "Traceback" not in done.stderr
        assert "--output" in done.stdout + done.stderr

    def test_an_impossible_spec_is_refused_without_writing_a_file(self, tmp_path: Path) -> None:
        out = tmp_path / "bad.mp4"
        done = cli("generate", "-o", str(out), "--fps", "0", "--duration", "1")
        assert done.returncode != 0
        assert "Traceback" not in done.stderr
        assert not out.exists(), "a refused spec must not leave a partial file behind"


class TestVerifyExitCode:
    """Verify is documented as a CI gate: exit 0 on pass, 1 on fail.

    Nothing else in the suite runs that contract against a real file, and a
    gate with the wrong exit code fails silently in every pipeline using it.
    """

    def test_it_exits_zero_when_the_file_matches(self, clip: Path) -> None:
        done = cli("verify", str(clip), "--fps", "30", "--res", "160x120")
        assert done.returncode == 0, done.stdout

    def test_it_exits_one_when_the_file_does_not_match(self, clip: Path) -> None:
        done = cli("verify", str(clip), "--fps", "60")
        assert done.returncode == 1, f"expected a failed gate, got {done.returncode}"

    def test_a_wrong_resolution_fails_the_gate(self, clip: Path) -> None:
        assert cli("verify", str(clip), "--res", "1920x1080").returncode == 1

    def test_a_wrong_codec_fails_the_gate(self, clip: Path) -> None:
        assert cli("verify", str(clip), "--codec", "vp9").returncode == 1

    def test_the_json_output_is_machine_readable(self, clip: Path) -> None:
        done = cli("verify", str(clip), "--fps", "30", "--json")
        assert done.returncode == 0, done.stdout
        payload = json.loads(done.stdout)
        assert payload["passed"] is True

    def test_the_json_output_still_parses_when_the_gate_fails(self, clip: Path) -> None:
        done = cli("verify", str(clip), "--fps", "60", "--json")
        assert done.returncode == 1
        assert json.loads(done.stdout)["passed"] is False


class TestConvert:
    def test_it_changes_fps_and_resolution_on_disk(self, clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "converted.mp4"
        ok("convert", str(clip), "-o", str(out), "--fps", "15", "--res", "120x120")
        info = probe(out)
        assert (info.width, info.height) == (120, 120)
        assert info.fps_float == pytest.approx(15, abs=0.01)

    def test_the_result_passes_its_own_verify(self, clip: Path, tmp_path: Path) -> None:
        """The two commands have to agree about the same file."""
        out = tmp_path / "chained.mp4"
        ok("convert", str(clip), "-o", str(out), "--fps", "15", "--res", "120x120")
        done = cli("verify", str(out), "--fps", "15", "--res", "120x120")
        assert done.returncode == 0, done.stdout

    def test_a_missing_input_fails_before_touching_the_output(self, tmp_path: Path) -> None:
        out = tmp_path / "never.mp4"
        done = cli("convert", str(tmp_path / "ghost.mp4"), "-o", str(out), "--fps", "15")
        assert done.returncode != 0
        assert "Traceback" not in done.stderr
        assert not out.exists()


class TestFormat:
    def test_the_extension_picks_the_container(self, clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "repacked.mkv"
        ok("format", str(clip), "-o", str(out))
        assert out.exists()
        assert "matroska" in probe(out).container or probe(out).container == "mkv"


class TestCaption:
    def test_it_burns_text_and_keeps_the_timing(self, clip: Path, tmp_path: Path) -> None:
        out = tmp_path / "captioned.mp4"
        ok("caption", str(clip), "-o", str(out), "--text", "hello")
        before, after = probe(clip), probe(out)
        assert after.duration == pytest.approx(before.duration, abs=0.2)
        assert (after.width, after.height) == (before.width, before.height)


class TestVariants:
    def test_it_writes_one_file_per_combination(self, clip: Path, tmp_path: Path) -> None:
        outdir = tmp_path / "variants"
        ok("variants", str(clip), "-o", str(outdir), "--fps", "15,30", "--res", "120x120")
        written = sorted(outdir.glob("*.mp4"))
        assert len(written) == 2, [p.name for p in written]
        for path in written:
            assert probe(path).width == 120


class TestInfo:
    def test_the_json_output_round_trips(self, clip: Path) -> None:
        done = ok("info", str(clip), "--json")
        payload = json.loads(done.stdout)
        assert payload["width"] == 160
        assert payload["container"]

    def test_the_table_output_names_the_file(self, clip: Path) -> None:
        assert clip.name in ok("info", str(clip)).stdout


class TestTheWholeJourney:
    def test_generate_convert_verify_through_the_cli_only(self, tmp_path: Path) -> None:
        """What a user actually does, with nothing imported but the probe."""
        source = tmp_path / "source.mp4"
        final = tmp_path / "final.mkv"

        ok("generate", "-o", str(source), "--fps", "30", "--duration", "1", "--res", "160x120")
        ok("convert", str(source), "-o", str(final), "--fps", "15", "--res", "80x80")
        gate = cli("verify", str(final), "--fps", "15", "--res", "80x80", "--duration", "1")
        assert gate.returncode == 0, gate.stdout

        info = probe(final)
        assert (info.width, info.height) == (80, 80)
        assert info.fps_float == pytest.approx(15, abs=0.01)
