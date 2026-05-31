"""dvwconverter__main__ – DataVolley .dvw ↔ SQLite converter."""

from .parser import parse_dvw, DvwFile
from .db import dvw_to_db, db_to_dvw
from .accuracy import compute_accuracy, AccuracyReport
from .roundtrip import roundtrip_accuracy, roundtrip_from_recon, RoundTripReport, SectionDiff

__all__ = [
    "parse_dvw", "DvwFile",
    "dvw_to_db", "db_to_dvw",
    "compute_accuracy", "AccuracyReport",
    "roundtrip_accuracy", "roundtrip_from_recon", "RoundTripReport", "SectionDiff",
]
__version__ = "0.2.0"
