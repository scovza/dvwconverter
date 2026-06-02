"""
Round-trip accuracy: compare an original .dvw with its DB-reconstructed twin.

Every conversion runs this automatically:
  - dvw2db: original file is on disk; we reconstruct from the freshly-populated DB.
  - db2dvw: reconstructed file is on disk; we load the original source_path from DB
            and diff against it (if the original is still accessible).

Public API
----------
  roundtrip_accuracy(original_path, db_path, fhid, recon_dir) -> RoundTripReport
      Core function.  Reconstructs the .dvw from the DB into *recon_dir*, then diffs
      it against *original_path*.  Returns a RoundTripReport.

  roundtrip_from_recon(recon_path, db_path, fhid) -> RoundTripReport | None
      Used by db2dvw.  Looks up the original source_path stored in the DB and
      calls roundtrip_accuracy if the original file is still accessible.

Round-Trip Score (0-100)
------------------------
  RTS = 100 × (0.55 × line_match + 0.25 × section_coverage + 0.20 × scout_match)

Data loss %
-----------
  Fraction of original non-empty lines absent from the reconstruction
  (multiset-sensitive, order-insensitive).

Score symbols in report: ✓ ≥99%  ~  80-98%  ✗ <80%

Score interpretation
--------------------
  95-100  Lossless or near-lossless.
  80-94   Minor cosmetic differences (whitespace, undecoded fields).
  60-79   Some structural data lost; scout events intact.
  <60     Significant data loss; investigate undecoded fields.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .parser import ENCODING
from .db import db_to_dvw

_EXPECTED_SECTIONS: frozenset[str] = frozenset({
    "[3DATAVOLLEYSCOUT]",
    "[3MATCH]",
    "[3TEAMS]",
    "[3MORE]",
    "[3COMMENTS]",
    "[3SET]",
    "[3PLAYERS-H]",
    "[3PLAYERS-V]",
    "[3ATTACKCOMBINATION]",
    "[3SETTERCALL]",
    "[3WINNINGSYMBOLS]",
    "[3RESERVE]",
    "[3VIDEO]",
    "[3SCOUT]",
})


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class SectionDiff:
    """Line-level diff statistics for one DVW section."""
    name: str
    original_lines: int = 0
    reconstructed_lines: int = 0
    matching_lines: int = 0

    @property
    def match_ratio(self) -> float:
        if self.original_lines == 0:
            return 1.0 if self.reconstructed_lines == 0 else 0.0
        return self.matching_lines / self.original_lines


@dataclass
class RoundTripReport:
    """Full round-trip accuracy report for one dvw→db→dvw cycle."""

    source_path: str
    reconstructed_path: str

    # Overall
    roundtrip_score: float       # 0–100
    data_loss_pct: float         # 0–100

    # Line-level
    total_original_lines: int
    total_reconstructed_lines: int
    identical_lines: int
    line_match_ratio: float

    # Section-level
    sections_present: set[str]
    sections_missing: set[str]
    section_coverage: float
    section_diffs: dict[str, SectionDiff]

    # Scout-event
    scout_events_original: int
    scout_events_reconstructed: int
    scout_events_matching: int
    scout_match_ratio: float

    # Optional verbose detail
    changed_lines: list[tuple[int, str, str]] = field(default_factory=list)

    # ── formatting ────────────────────────────────────────────────────────────

    def format_summary(self) -> str:
        """One-liner for inline use inside dvw2db / db2dvw output."""
        return (
            f"roundtrip score={self.roundtrip_score:.1f}  "
            f"loss={self.data_loss_pct:.2f}%  "
            f"scout={self.scout_match_ratio * 100:.0f}%"
        )

    def format_report(self, verbose: bool = False) -> str:
        """Full multi-line report."""
        sep = "-" * 60
        lines = [
            sep,
            f"  Source        : {Path(self.source_path).name}",
            f"  Reconstructed : {Path(self.reconstructed_path).name}",
            sep,
            f"  Round-trip score : {self.roundtrip_score:.1f} / 100",
            f"  Data loss        : {self.data_loss_pct:.2f}%",
            sep,
            "  Line metrics",
            f"    Original lines       : {self.total_original_lines}",
            f"    Reconstructed lines  : {self.total_reconstructed_lines}",
            f"    Identical lines      : {self.identical_lines}",
            f"    Match ratio          : {self.line_match_ratio * 100:.1f}%",
            sep,
            "  Section coverage",
            f"    Present : {len(self.sections_present)} / {len(_EXPECTED_SECTIONS)}",
        ]
        if self.sections_missing:
            lines.append(f"    Missing : {', '.join(sorted(self.sections_missing))}")
        lines += [
            sep,
            "  Scout events",
            f"    Original      : {self.scout_events_original}",
            f"    Reconstructed : {self.scout_events_reconstructed}",
            f"    Matching      : {self.scout_events_matching}",
            f"    Match ratio   : {self.scout_match_ratio * 100:.1f}%",
            sep,
            "  Per-section breakdown",
        ]
        for sec_name in sorted(self.section_diffs):
            sd = self.section_diffs[sec_name]
            tag = "✓" if sd.match_ratio >= 0.99 else ("~" if sd.match_ratio >= 0.80 else "✗")
            lines.append(
                f"    {tag}  {sec_name:<28}  "
                f"orig={sd.original_lines:>4}  recon={sd.reconstructed_lines:>4}  "
                f"match={sd.match_ratio * 100:.0f}%"
            )
        if verbose and self.changed_lines:
            lines += [sep, "  Changed lines (line#  original → reconstructed)"]
            for lineno, orig, recon in self.changed_lines[:100]:
                lines.append(f"    {lineno:>5}  - {orig[:80]}")
                lines.append(f"           + {recon[:80]}")
            if len(self.changed_lines) > 100:
                lines.append(f"    … {len(self.changed_lines) - 100} more changes not shown")
        lines.append(sep)
        return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_lines(path: str) -> list[str]:
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode(ENCODING, errors="replace")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _split_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for ln in lines:
        if ln.startswith("[") and ln.endswith("]"):
            current = ln
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(ln)
    return sections


def _multiset_match(a: list[str], b: list[str]) -> int:
    """Count lines common to both lists (multiset intersection size)."""
    ca, cb = Counter(a), Counter(b)
    return sum((ca & cb).values())


def _compute_report(
    orig_path: str,
    recon_path: str,
) -> RoundTripReport:
    """
    Diff *orig_path* against *recon_path* and return a RoundTripReport.

    This is the single place where all diff maths live; both
    roundtrip_accuracy and roundtrip_from_recon delegate here.
    """
    orig_lines  = _read_lines(orig_path)
    recon_lines = _read_lines(recon_path)

    orig_secs  = _split_sections(orig_lines)
    recon_secs = _split_sections(recon_lines)

    # Section coverage
    secs_present = _EXPECTED_SECTIONS & set(recon_secs)
    secs_missing = _EXPECTED_SECTIONS - secs_present
    section_coverage = len(secs_present) / len(_EXPECTED_SECTIONS)

    # Per-section diff
    section_diffs: dict[str, SectionDiff] = {
        sec: SectionDiff(
            name=sec,
            original_lines=len(orig_secs.get(sec, [])),
            reconstructed_lines=len(recon_secs.get(sec, [])),
            matching_lines=_multiset_match(orig_secs.get(sec, []), recon_secs.get(sec, [])),
        )
        for sec in set(orig_secs) | set(recon_secs)
    }

    # Overall line match
    total_match      = _multiset_match(orig_lines, recon_lines)
    line_match_ratio = total_match / len(orig_lines) if orig_lines else 1.0

    # Scout-event match
    scout_orig        = orig_secs.get("[3SCOUT]", [])
    scout_recon       = recon_secs.get("[3SCOUT]", [])
    scout_match       = _multiset_match(scout_orig, scout_recon)
    scout_match_ratio = scout_match / len(scout_orig) if scout_orig else 1.0

    # Data loss
    c_orig  = Counter(orig_lines)
    c_recon = Counter(recon_lines)
    lost         = sum((c_orig - c_recon).values())
    data_loss_pct = (lost / len(orig_lines) * 100) if orig_lines else 0.0

    # Changed-line detail (positional, for --verbose)
    changed: list[tuple[int, str, str]] = [
        (i + 1, o, r)
        for i, (o, r) in enumerate(zip(orig_lines, recon_lines))
        if o != r
    ]

    roundtrip_score = 100.0 * (
        0.55 * line_match_ratio
        + 0.25 * section_coverage
        + 0.20 * scout_match_ratio
    )

    return RoundTripReport(
        source_path=orig_path,
        reconstructed_path=recon_path,
        roundtrip_score=round(roundtrip_score, 2),
        data_loss_pct=round(data_loss_pct, 2),
        total_original_lines=len(orig_lines),
        total_reconstructed_lines=len(recon_lines),
        identical_lines=total_match,
        line_match_ratio=round(line_match_ratio, 4),
        sections_present=secs_present,
        sections_missing=secs_missing,
        section_coverage=round(section_coverage, 4),
        section_diffs=section_diffs,
        scout_events_original=len(scout_orig),
        scout_events_reconstructed=len(scout_recon),
        scout_events_matching=scout_match,
        scout_match_ratio=round(scout_match_ratio, 4),
        changed_lines=changed,
    )


# ── public API ────────────────────────────────────────────────────────────────

def roundtrip_accuracy(
    original_path: str,
    db_path: str,
    fhid: int,
    recon_dir: str,
) -> RoundTripReport:
    """Reconstruct the .dvw for *fhid* from *db_path* into *recon_dir*, diff
    against *original_path*, and return a RoundTripReport.

    The reconstructed file is written as ``rt_<stem>.dvw`` directly inside
    *recon_dir* (no sub-directory).  This is the entry point used by dvw2db.
    """
    # Pre-clean any leftover temp subdir from a previous run.
    # db_to_dvw creates <recon_dir>/<stem>.dvw/<stem>.dvw; on Windows,
    # mkdir raises [WinError 183] if <stem>.dvw already exists as a file,
    # and the intermediate directory may survive if a prior run failed mid-way.
    orig_stem = Path(original_path).stem
    temp_subdir = Path(recon_dir) / f"{orig_stem}.dvw"
    if temp_subdir.is_file():
        temp_subdir.unlink()
    elif temp_subdir.is_dir():
        import shutil as _shutil
        _shutil.rmtree(temp_subdir)

    written = db_to_dvw(db_path, recon_dir, file_header_id=fhid)
    if not written:
        raise RuntimeError(f"db_to_dvw produced no output for fhid={fhid}")

    # db_to_dvw writes into <recon_dir>/<stem>.dvw/<stem>.dvw; extract the
    # file, rename it to rt_<stem>.dvw directly under recon_dir, then remove
    # the now-empty sub-directory.
    src = Path(written[0])
    rt_path = src.parent.parent / f"rt_{src.stem}.dvw"
    if rt_path.exists():
        rt_path.unlink()
    src.rename(rt_path)
    try:
        src.parent.rmdir()
    except OSError:
        pass  # not empty — leave it

    return _compute_report(original_path, str(rt_path))


def roundtrip_from_recon(
    recon_path: str,
    db_path: str,
    fhid: int,
) -> RoundTripReport | None:
    """
    Used after db2dvw: look up the original source_path in the DB and diff
    against it.  Returns None if the original file is no longer accessible.
    """
    try:
        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT source_path FROM file_header WHERE id=?", (fhid,)
        ).fetchone()
        con.close()
    except Exception:
        return None

    if not row or not row[0]:
        return None

    orig_path = row[0]
    if not Path(orig_path).exists():
        return None

    return _compute_report(orig_path, recon_path)
