"""vidfix: exact-spec media toolkit."""

from vidfix.core.attach import attach
from vidfix.core.caption import caption
from vidfix.core.convert import ConvertPlan, convert
from vidfix.core.formats import to_format
from vidfix.core.generate import generate
from vidfix.core.probe import AudioInfo, MediaInfo, probe
from vidfix.core.verify import PropertyCheck, VerifyResult, verify
from vidfix.exceptions import (
    ConversionError,
    FFmpegNotFoundError,
    InvalidSpecError,
    PresetError,
    ProbeError,
    VidfixError,
)

__version__ = "0.3.2"

__all__ = [
    "AudioInfo",
    "ConversionError",
    "ConvertPlan",
    "FFmpegNotFoundError",
    "InvalidSpecError",
    "MediaInfo",
    "PresetError",
    "ProbeError",
    "PropertyCheck",
    "VerifyResult",
    "VidfixError",
    "attach",
    "caption",
    "convert",
    "generate",
    "probe",
    "to_format",
    "verify",
]
