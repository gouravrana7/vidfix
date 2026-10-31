"""Smoke: does the thing start at all.

No encoding, no fixtures, no mocks. These answer one question -- is the CLI
and the public API intact -- and they answer it in under a second. The rest of
the suite mocks the FFmpeg layer; nothing else checks that the entry point
itself still runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import vidfix

pytestmark = pytest.mark.smoke

# Every command the README and --help promise. A command disappearing from the
# CLI is a breaking change, and this is the only test that would notice.
COMMANDS = (
    "generate",
    "caption",
    "attach",
    "convert",
    "format",
    "verify",
    "info",
    "variants",
    "preset",
)

TIMEOUT = 60


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the CLI the way a user does, through the module entry point.

    stdin is closed: with no arguments the CLI opens an interactive wizard,
    and a test must never sit waiting on a prompt.
    """
    return subprocess.run(
        [sys.executable, "-m", "vidfix", *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        input="",
    )


def test_the_cli_starts_and_prints_help():
    done = cli("--help")
    assert done.returncode == 0, done.stderr
    assert "Usage" in done.stdout


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_is_still_registered(command: str):
    assert command in cli("--help").stdout


@pytest.mark.parametrize("command", COMMANDS)
def test_every_command_explains_itself(command: str):
    done = cli(command, "--help")
    assert done.returncode == 0, f"{command} --help failed: {done.stderr}"
    assert done.stdout.strip(), f"{command} --help printed nothing"


def test_the_version_flag_matches_the_package():
    done = cli("--version")
    assert done.returncode == 0, done.stderr
    assert vidfix.__version__ in done.stdout


def test_the_version_matches_the_project_metadata():
    pyproject = (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text()
    assert f'version = "{vidfix.__version__}"' in pyproject, (
        "pyproject and vidfix.__version__ disagree"
    )


def test_no_arguments_opens_the_wizard_without_crashing():
    """With no arguments the CLI is documented to start an interactive wizard.
    With stdin closed it must bow out cleanly, not traceback."""
    done = cli()
    assert "Traceback" not in done.stderr, done.stderr
    assert done.stdout.strip(), "the wizard printed nothing at all"


def test_an_unknown_command_fails_cleanly():
    done = cli("definitely-not-a-command")
    assert done.returncode != 0
    assert "Traceback" not in done.stderr


def test_the_public_api_is_importable():
    missing = [name for name in vidfix.__all__ if not hasattr(vidfix, name)]
    assert missing == [], f"__all__ promises what the package does not export: {missing}"


def test_the_console_script_is_installed():
    script = Path(sys.executable).parent / "vidfix"
    if not script.exists():
        pytest.skip("console script not installed in this environment")
    done = subprocess.run(
        [str(script), "--version"], capture_output=True, text=True, timeout=TIMEOUT
    )
    assert done.returncode == 0, done.stderr
    assert vidfix.__version__ in done.stdout


def test_the_ffmpeg_binary_can_be_found():
    """Every real command needs this. Without it the CLI is decoration.

    ffprobe is deliberately optional: imageio-ffmpeg does not bundle it and
    vidfix probes through ffmpeg instead, so only ffmpeg is required here.
    """
    from vidfix.core.ffmpeg import find_ffmpeg

    found = find_ffmpeg()
    assert found, "ffmpeg could not be resolved"
    assert Path(found).exists(), f"ffmpeg resolved to a missing path: {found}"


def test_presets_can_be_listed_without_touching_a_file():
    done = cli("preset", "list")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip()


def test_probing_a_missing_file_is_a_clean_error_not_a_crash(tmp_path: Path):
    done = cli("info", str(tmp_path / "nope.mp4"))
    assert done.returncode != 0
    assert "Traceback" not in done.stderr


def test_verify_with_no_expectations_refuses_instead_of_passing(tmp_path: Path):
    """Verify is a CI gate. A gate that passes when asked nothing is a hazard."""
    target = tmp_path / "nope.mp4"
    target.write_bytes(b"not a video")
    done = cli("verify", str(target))
    assert done.returncode != 0
    assert "Traceback" not in done.stderr


def test_json_output_is_valid_json_when_the_input_is_bad(tmp_path: Path):
    """A --json flag that emits a half-written table on error is unusable in CI."""
    done = cli("info", str(tmp_path / "nope.mp4"), "--json")
    assert done.returncode != 0
    if done.stdout.strip():
        json.loads(done.stdout)
