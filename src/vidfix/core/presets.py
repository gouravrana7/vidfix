"""Preset loading and merging.

Built-in presets ship in ``vidfix/data/presets.yaml``; user presets live in
``~/.config/vidfix/presets.yaml`` and win on name clashes. A preset only sets
defaults — explicit flags always override.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from vidfix.exceptions import PresetError

#: Keys a preset may set (the same strings the CLI flags accept), plus
#: ``timecode`` (df/ndf counting for burn-in) and ``alias`` (points at
#: another preset).
PRESET_KEYS = frozenset({"description", "fps", "duration", "res", "codec", "timecode", "alias"})

#: Timecode counting modes: drop-frame (semicolon notation) vs non-drop-frame.
TIMECODE_MODES = ("df", "ndf")

Preset = dict[str, str]


def user_presets_path() -> Path:
    return Path.home() / ".config" / "vidfix" / "presets.yaml"


def _load_yaml(text: str, origin: str) -> dict[str, Preset]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise PresetError(f"Malformed YAML in {origin}: {exc}") from exc
    if not isinstance(data, dict):
        raise PresetError(f"Presets in {origin} must be a mapping of name -> settings.")

    presets: dict[str, Preset] = {}
    for name, settings in data.items():
        if not isinstance(settings, dict):
            raise PresetError(f"Preset {name!r} in {origin} must be a mapping.")
        unknown = set(settings) - PRESET_KEYS
        if unknown:
            allowed = ", ".join(sorted(PRESET_KEYS))
            raise PresetError(
                f"Preset {name!r} in {origin} has unknown keys {sorted(unknown)}; "
                f"allowed: {allowed}."
            )
        mode = settings.get("timecode")
        if mode is not None and str(mode) not in TIMECODE_MODES:
            raise PresetError(
                f"Preset {name!r} in {origin} has timecode {mode!r}; expected 'df' or 'ndf'."
            )
        presets[str(name)] = {k: str(v) for k, v in settings.items()}
    return presets


def load_presets() -> dict[str, Preset]:
    """All available presets: built-ins overlaid by user presets."""
    builtin_text = files("vidfix").joinpath("data/presets.yaml").read_text(encoding="utf-8")
    presets = _load_yaml(builtin_text, "built-in presets")

    user_path = user_presets_path()
    if user_path.is_file():
        presets = {
            **presets,
            **_load_yaml(user_path.read_text(encoding="utf-8"), str(user_path)),
        }
    return presets


def get_preset(name: str) -> Preset:
    """Look up a preset by name, following ``alias`` entries."""
    presets = load_presets()
    seen: set[str] = set()
    while True:
        if name not in presets:
            available = ", ".join(sorted(presets))
            raise PresetError(f"Unknown preset {name!r}; available: {available}.")
        target = presets[name].get("alias")
        if target is None:
            return presets[name]
        seen.add(name)
        if target in seen:
            raise PresetError(f"Preset alias cycle detected at {name!r} -> {target!r}.")
        name = target


def apply_preset(name: str | None, **explicit: Any) -> dict[str, Any]:
    """Merge preset defaults with explicit values; explicit non-None values win."""
    merged: dict[str, Any] = dict(explicit)
    if name is not None:
        preset = get_preset(name)
        for key, value in preset.items():
            if key != "description" and merged.get(key) is None:
                merged[key] = value
    return merged
