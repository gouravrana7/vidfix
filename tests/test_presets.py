"""Unit tests for preset loading and merging."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from vidfix.core import presets
from vidfix.core.duration import parse_fps
from vidfix.exceptions import PresetError


class TestBuiltins:
    def test_df_presets_are_exact_rationals(self) -> None:
        loaded = presets.load_presets()
        assert parse_fps(loaded["df30"]["fps"]) == Fraction(30000, 1001)
        assert parse_fps(loaded["df60"]["fps"]) == Fraction(60000, 1001)

    def test_expected_builtins_exist(self) -> None:
        loaded = presets.load_presets()
        expected = {
            "df30", "df60", "ndf30", "ndf60", "pal25", "ndf25", "pal50",
            "film24", "film23976", "broadcast-1080i", "web-720p",
        }  # fmt: skip
        assert expected <= set(loaded)

    @pytest.mark.parametrize(
        ("name", "fps"),
        [
            ("pal25", Fraction(25)),
            ("pal50", Fraction(50)),
            ("ndf30", Fraction(30000, 1001)),
            ("ndf60", Fraction(60000, 1001)),
            ("film24", Fraction(24)),
            ("film23976", Fraction(24000, 1001)),
        ],
    )
    def test_broadcast_family_rates(self, name: str, fps: Fraction) -> None:
        assert parse_fps(presets.get_preset(name)["fps"]) == fps

    @pytest.mark.parametrize(
        ("name", "mode"),
        [
            ("df30", "df"),
            ("df60", "df"),
            ("ndf30", "ndf"),
            ("ndf60", "ndf"),
            ("pal25", "ndf"),
            ("pal50", "ndf"),
            ("film24", "ndf"),
            ("film23976", "ndf"),
        ],
    )
    def test_timecode_modes(self, name: str, mode: str) -> None:
        assert presets.get_preset(name)["timecode"] == mode


class TestAliases:
    def test_ndf25_resolves_to_pal25(self) -> None:
        assert presets.get_preset("ndf25") == presets.get_preset("pal25")

    def test_alias_target_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("dangling:\n  alias: nowhere\n")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        with pytest.raises(PresetError, match="Unknown preset"):
            presets.get_preset("dangling")

    def test_alias_cycle_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("a:\n  alias: b\nb:\n  alias: a\n")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        with pytest.raises(PresetError, match="cycle"):
            presets.get_preset("a")

    def test_apply_preset_through_alias(self) -> None:
        merged = presets.apply_preset("ndf25", fps=None, res=None)
        assert merged["fps"] == "25"
        assert merged["timecode"] == "ndf"
        assert "alias" not in merged


class TestUserPresets:
    def test_user_preset_overrides_builtin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("df30:\n  fps: '25'\nmine:\n  res: 720p\n")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        loaded = presets.load_presets()
        assert loaded["df30"]["fps"] == "25"
        assert loaded["mine"]["res"] == "720p"

    def test_unknown_key_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("bad:\n  bitrate: 5000\n")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        with pytest.raises(PresetError, match="unknown keys"):
            presets.load_presets()

    def test_malformed_yaml_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("[not: a mapping")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        with pytest.raises(PresetError, match="Malformed YAML"):
            presets.load_presets()

    def test_invalid_timecode_mode_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_file = tmp_path / "presets.yaml"
        user_file.write_text("bad:\n  timecode: sometimes\n")
        monkeypatch.setattr(presets, "user_presets_path", lambda: user_file)
        with pytest.raises(PresetError, match="timecode"):
            presets.load_presets()


class TestApplyPreset:
    def test_explicit_flags_win(self) -> None:
        merged = presets.apply_preset("web-720p", fps="60", duration=None, res=None, codec=None)
        assert merged["fps"] == "60"
        assert merged["res"] == "720p"
        assert merged["codec"] == "h264"

    def test_no_preset_passthrough(self) -> None:
        merged = presets.apply_preset(None, fps="24", res=None)
        assert merged == {"fps": "24", "res": None}

    def test_unknown_preset(self) -> None:
        with pytest.raises(PresetError, match="Unknown preset"):
            presets.apply_preset("nope", fps=None)


class TestLoadYamlValidation:
    def test_top_level_must_be_mapping(self) -> None:
        with pytest.raises(PresetError):
            presets._load_yaml("- a\n- b\n", "test.yaml")

    def test_each_preset_must_be_mapping(self) -> None:
        with pytest.raises(PresetError):
            presets._load_yaml("df30: 5\n", "test.yaml")
