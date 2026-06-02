"""CLI entry point; run via `python -m dvwconverter` or `dvwconverter`."""

import argparse
import re
import shutil
import sqlite3
import sys
import traceback
from pathlib import Path

from .parser import parse_dvw
from .db import dvw_to_db, db_to_dvw
from .accuracy import compute_accuracy
from .roundtrip import roundtrip_accuracy, roundtrip_from_recon, RoundTripReport

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_INPUT_DIR  = "input"


def _resolve_input(raw: str) -> str:
    """Locate an input file, copying it into the input folder if needed.

    Resolution order:
      1. Path exists and is already the input-folder copy → use as-is.
      2. Path exists elsewhere → copy into input folder and use the copy.
      3. Not found at given path, but same name exists in input folder → use that.
      4. Not found anywhere → return as-is so the caller raises a clear error.
    """
    input_dir = Path(DEFAULT_INPUT_DIR)
    input_dir.mkdir(parents=True, exist_ok=True)

    p = Path(raw).expanduser().resolve()
    if p.exists():
        dest = input_dir / p.name
        if p != dest.resolve():
            shutil.copy2(p, dest)
            print(f"  [input] copied '{p.name}' → '{dest}'")
        return str(dest)

    fallback = input_dir / Path(raw).name
    if fallback.exists():
        print(f"  [input] '{raw}' not found – using '{fallback}' instead")
        return str(fallback)

    return raw


# ── dvw2db ────────────────────────────────────────────────────────────────────

def cmd_dvw2db(args: argparse.Namespace) -> int:
    """Import one or more .dvw files into a single SQLite database.

    With --rt: after each import a round-trip check is performed:
      dvw (original) → db → dvw (reconstructed) → diff → accuracy report
    The reconstructed file is saved as rt_<name>.dvw in <output_dir>/roundtrip/.
    """
    out_root  = Path(args.output_dir)
    db_path   = str(out_root / args.db)
    recon_dir = str(out_root / "roundtrip")
    errors    = 0

    for src in [_resolve_input(f) for f in args.input]:
        src_path = Path(src)
        try:
            print(f"  importing  {src_path.name} ...", end=" ", flush=True)
            dvw  = parse_dvw(src)
            fhid = dvw_to_db(dvw, db_path)
            home = dvw.teams[0].team_name if dvw.teams else "?"
            away = dvw.teams[1].team_name if len(dvw.teams) > 1 else "?"
            acc  = compute_accuracy(dvw)

            rt_str = ""
            rt = None
            if args.rt:
                try:
                    rt = roundtrip_accuracy(src, db_path, fhid, recon_dir)
                    rt_str = f"  {rt.format_summary()}"
                except Exception as rt_exc:
                    rt_str = f"  roundtrip-error={rt_exc}"

            print(
                f"ok  id={fhid}  {home} vs {away}"
                f"  events={len(dvw.scout_events)}"
                f"  accuracy={acc.score:.1f}"
                f"{rt_str}"
            )

            if args.verbose and isinstance(rt, RoundTripReport):
                print(rt.format_report())

        except FileNotFoundError as exc:
            print(f"FAILED – file not found: {exc.filename}", file=sys.stderr)
            errors += 1
        except sqlite3.OperationalError as exc:
            msg = str(exc)
            m = re.search(r'(\d+) values for (\d+) columns', msg)
            if m:
                vals, cols = int(m.group(1)), int(m.group(2))
                print(
                    f"FAILED – schema mismatch: INSERT supplies {vals} values "
                    f"for {cols} columns (schema/code out of sync; try re-importing)",
                    file=sys.stderr,
                )
            else:
                print(f"FAILED – database error: {msg}", file=sys.stderr)
            errors += 1
        except UnicodeDecodeError as exc:
            print(
                f"FAILED – encoding error in {src_path.name}: "
                f"unexpected byte at position {exc.start} "
                f"(file may not be Windows-1252)",
                file=sys.stderr,
            )
            errors += 1
        except Exception as exc:
            print(f"FAILED – {type(exc).__name__}: {exc}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            errors += 1

    print(f"\nDatabase : {db_path}")
    if args.rt:
        print(f"Roundtrip: {recon_dir}/")
    return errors


# ── db2dvw ────────────────────────────────────────────────────────────────────

def cmd_db2dvw(args: argparse.Namespace) -> int:
    """Export one or all matches from a database back to .dvw files.

    Each match is written as <name>.dvw/<name>.dvw inside <output_dir>/dvw/.
    With --rt: also diffs the reconstructed file against the original source
    stored in the DB (if it is still accessible on disk).
    """
    out_dvw_dir = str(Path(args.output_dir) / "dvw")
    fhid        = getattr(args, "id", None)
    db_path     = _resolve_input(args.input)

    try:
        written = db_to_dvw(db_path, out_dvw_dir, file_header_id=fhid)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors = 0
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for recon_path in written:
            stem = Path(recon_path).stem
            try:
                row = con.execute(
                    "SELECT id FROM file_header WHERE source_path LIKE ?",
                    (f"%{stem}%",)
                ).fetchone()
                file_fhid = row["id"] if row else fhid
            except Exception:
                file_fhid = fhid

            # recon_path is <out_dvw_dir>/<stem>.dvw/<stem>.dvw
            dvw_dir = Path(recon_path).parent
            print(f"  written: {dvw_dir}/")

            if args.rt:
                try:
                    rt = roundtrip_from_recon(recon_path, db_path, file_fhid)
                    if rt is None:
                        print("    [rt] original file not accessible – skipped")
                    else:
                        print(f"    [rt] {rt.format_summary()}")
                        if args.verbose:
                            print(rt.format_report())
                except Exception as rt_exc:
                    print(f"    [rt] error – {rt_exc}")
    finally:
        con.close()

    print(f"\nOutput: {out_dvw_dir}/")
    return errors


# ── info ──────────────────────────────────────────────────────────────────────

def cmd_info(args: argparse.Namespace) -> int:
    """Print a summary table of all matches stored in a database."""
    con = sqlite3.connect(_resolve_input(args.input))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT fh.id, fh.source_path,
                   m.date, m.season, m.league,
                   (SELECT COUNT(*) FROM scout_event se WHERE se.file_header_id=fh.id) AS events,
                   (SELECT COUNT(*) FROM player p WHERE p.file_header_id=fh.id) AS players
            FROM file_header fh
            LEFT JOIN match m ON m.file_header_id=fh.id
            ORDER BY fh.id
        """).fetchall()
        if not rows:
            print("No matches found.")
            return 0
        print(f"{'ID':>4}  {'Date':<12}  {'Season':<10}  {'League':<30}  {'Events':>7}  {'Players':>7}  Source")
        print("-" * 95)
        for r in rows:
            print(
                f"{r['id']:>4}  {r['date'] or '':12}  {r['season'] or '':10}  "
                f"{r['league'] or '':30}  {r['events']:>7}  {r['players']:>7}  "
                f"{Path(r['source_path'] or '').name}"
            )
    finally:
        con.close()
    return 0


# ── argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    from . import __version__
    p = argparse.ArgumentParser(
        prog="dvwconverter",
        description="Convert DataVolley .dvw scouting files to/from SQLite.",
    )
    p.add_argument("--version", action="version", version=f"dvwconverter {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser(
        "dvw2db",
        help="Import .dvw file(s) into a SQLite database",
    )
    p1.add_argument("input", nargs="+", metavar="FILE.dvw")
    p1.add_argument("-o", "--db", default="matches.db", metavar="NAME.db",
                    help="Output database filename (default: matches.db)")
    p1.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")
    p1.add_argument("--rt", action="store_true",
                    help="Run round-trip check after each import (writes rt_<name>.dvw to roundtrip/)")
    p1.add_argument("--verbose", action="store_true",
                    help="Print full round-trip diff report (implies --rt)")

    p2 = sub.add_parser(
        "db2dvw",
        help="Export match(es) from SQLite to .dvw",
    )
    p2.add_argument("input", metavar="DB.db")
    p2.add_argument("--id", type=int, default=None,
                    help="Export only the match with this file_header_id")
    p2.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")
    p2.add_argument("--rt", action="store_true",
                    help="Run round-trip check after each export")
    p2.add_argument("--verbose", action="store_true",
                    help="Print full round-trip diff report (implies --rt)")

    p3 = sub.add_parser("info", help="List matches stored in a database")
    p3.add_argument("input", metavar="DB.db")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # --verbose implies --rt: no need to specify both flags
    if getattr(args, "verbose", False):
        args.rt = True
    dispatch = {"dvw2db": cmd_dvw2db, "db2dvw": cmd_db2dvw, "info": cmd_info}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
