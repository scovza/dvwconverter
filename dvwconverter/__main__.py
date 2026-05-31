"""CLI entry point; run via `python -m dvwconverter__main__` or `dvwconverter__main__`."""

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from .parser import parse_dvw
from .db import dvw_to_db, db_to_dvw
from .accuracy import compute_accuracy
from .roundtrip import roundtrip_accuracy, roundtrip_from_recon

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_INPUT_DIR  = "input"


def _ensure_input_dir() -> Path:
    p = Path(DEFAULT_INPUT_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_input(raw: str) -> str:
    """
    Locate an input file, copying it into the input folder if needed.

    Resolution order:
      1. Path exists and is already the input-folder copy → use as-is.
      2. Path exists elsewhere → copy into input folder and use the copy.
      3. Not found at given path, but same name exists in input folder → use that.
      4. Not found anywhere → return as-is so the caller raises a clear error.
    """
    input_dir = _ensure_input_dir()
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


def _output_dir(args: argparse.Namespace) -> str:
    return getattr(args, "output_dir", None) or DEFAULT_OUTPUT_DIR


# ── dvw2db ────────────────────────────────────────────────────────────────────

def cmd_dvw2db(args: argparse.Namespace) -> int:
    """
    Import one or more .dvw files into a single SQLite database.

    After each import a round-trip check is performed automatically:
      dvw (original) → db → dvw (reconstructed) → diff → accuracy report
    The reconstructed .dvw is saved to <output_dir>/roundtrip/.
    """
    out_root  = Path(_output_dir(args))
    db_path   = str(out_root / args.db)
    recon_dir = str(out_root / "roundtrip")
    errors    = 0

    for src in [_resolve_input(f) for f in args.input]:
        src_path = Path(src)
        try:
            # ── forward: dvw → db ──────────────────────────────────────────
            print(f"  parsing  {src_path.name} ...", end=" ", flush=True)
            dvw   = parse_dvw(src)
            fhid  = dvw_to_db(dvw, db_path)
            home  = dvw.teams[0].team_name if dvw.teams else "?"
            away  = dvw.teams[1].team_name if len(dvw.teams) > 1 else "?"
            acc   = compute_accuracy(dvw)

            # ── backward: db → dvw, then diff ─────────────────────────────
            try:
                rt = roundtrip_accuracy(src, db_path, fhid, recon_dir)
                rt_str = rt.format_summary()
            except Exception as rt_exc:
                rt_str = f"roundtrip-error={rt_exc}"

            print(
                f"ok  [id={fhid}  {home} vs {away}"
                f"  events={len(dvw.scout_events)}"
                f"  accuracy={acc.score:.1f}"
                f"  {rt_str}]"
            )

            # Full round-trip report on its own line if verbose
            if getattr(args, "verbose", False):
                print(rt.format_report())

        except FileNotFoundError as exc:
            print(f"FAILED – file not found: {exc.filename}", file=sys.stderr)
            errors += 1
        except sqlite3.OperationalError as exc:
            msg = str(exc)
            # Diagnose the common placeholder/column mismatch
            import re as _re
            m = _re.search(r'(\d+) values for (\d+) columns', msg)
            if m:
                vals, cols = int(m.group(1)), int(m.group(2))
                print(
                    f"FAILED – database schema mismatch: INSERT supplies {vals} values "
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
            exc_type = type(exc).__name__
            print(f"FAILED – {exc_type}: {exc}", file=sys.stderr)
            if getattr(args, 'verbose', False):
                import traceback
                traceback.print_exc()
            errors += 1

    print(f"\nDatabase     : {db_path}")
    print(f"Reconstructed: {recon_dir}/")
    return errors


# ── db2dvw ────────────────────────────────────────────────────────────────────

def cmd_db2dvw(args: argparse.Namespace) -> int:
    """
    Export one or all matches from a database back to .dvw files.

    After each export a round-trip accuracy report is printed by comparing
    the reconstructed .dvw against the original source file stored in the DB
    (if the original path is still accessible on disk).
    """
    out_root   = Path(_output_dir(args))
    out_dvw_dir = str(out_root / "dvw")
    fhid        = getattr(args, "id", None)
    db_path     = _resolve_input(args.input)

    try:
        written = db_to_dvw(db_path, out_dvw_dir, file_header_id=fhid)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    errors = 0
    for recon_path in written:
        # Determine the fhid for this file (needed for roundtrip_from_recon)
        stem = Path(recon_path).stem
        try:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            row = con.execute(
                "SELECT id FROM file_header WHERE source_path LIKE ?",
                (f"%{stem}%",)
            ).fetchone()
            con.close()
            file_fhid = row["id"] if row else fhid
        except Exception:
            file_fhid = fhid

        print(f"  written: {recon_path}")

        # Round-trip: diff reconstructed vs original
        try:
            rt = roundtrip_from_recon(recon_path, db_path, file_fhid)
            if rt is None:
                print("    [roundtrip] original file not accessible – skipped")
            else:
                print(f"    [roundtrip] {rt.format_summary()}")
                if getattr(args, "verbose", False):
                    print(rt.format_report())
        except Exception as rt_exc:
            print(f"    [roundtrip] error – {rt_exc}")

    print(f"\nOutput directory: {out_dvw_dir}")
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


# ── parser ────────────────────────────────────────────────────────────────────

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
        help="Import .dvw file(s) into a SQLite database (includes round-trip accuracy)",
    )
    p1.add_argument("input", nargs="+", metavar="FILE.dvw")
    p1.add_argument("-o", "--db", default="matches.db", metavar="NAME.db",
                    help="Output database filename (default: matches.db)")
    p1.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")
    p1.add_argument("--verbose", action="store_true",
                    help="Print full round-trip diff report for each file")

    p2 = sub.add_parser(
        "db2dvw",
        help="Export match(es) from SQLite to .dvw (includes round-trip accuracy)",
    )
    p2.add_argument("input", metavar="DB.db")
    p2.add_argument("--id", type=int, default=None,
                    help="Export only the match with this file_header_id")
    p2.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")
    p2.add_argument("--verbose", action="store_true",
                    help="Print full round-trip diff report for each file")

    p3 = sub.add_parser("info", help="List matches stored in a database")
    p3.add_argument("input", metavar="DB.db")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    dispatch = {"dvw2db": cmd_dvw2db, "db2dvw": cmd_db2dvw, "info": cmd_info}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
