"""CLI entry point; run via `python -m dvwconverter` or `dvwconverter`."""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from .parser import parse_dvw
from .db import dvw_to_db, db_to_dvw
from .accuracy import compute_accuracy

DEFAULT_OUTPUT_DIR = "output"
DEFAULT_INPUT_DIR = "input"


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


def cmd_dvw2db(args: argparse.Namespace) -> int:
    """Import one or more .dvw files into a single SQLite database."""
    db_path = str(Path(_output_dir(args)) / args.db)
    errors = 0
    for src in [_resolve_input(f) for f in args.input]:
        try:
            print(f"  parsing  {Path(src).name} ...", end=" ", flush=True)
            dvw = parse_dvw(src)
            fhid = dvw_to_db(dvw, db_path)
            home = dvw.teams[0].team_name if dvw.teams else "?"
            away = dvw.teams[1].team_name if len(dvw.teams) > 1 else "?"
            report = compute_accuracy(dvw)
            print(
                f"ok  [id={fhid}  {home} vs {away}"
                f"  events={len(dvw.scout_events)}"
                f"  accuracy={report.score:.1f}]"
            )
        except Exception as exc:
            print(f"FAILED – {exc}", file=sys.stderr)
            errors += 1
    print(f"\nDatabase: {db_path}")
    return errors


def cmd_db2dvw(args: argparse.Namespace) -> int:
    """Export one or all matches from a database back to .dvw files."""
    out_dir = str(Path(_output_dir(args)) / "dvw")
    fhid = getattr(args, "id", None)
    try:
        written = db_to_dvw(_resolve_input(args.input), out_dir, file_header_id=fhid)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for p in written:
        print(f"  written: {p}")
    return 0


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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dvwconverter",
        description="Convert DataVolley .dvw scouting files to/from SQLite.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("dvw2db", help="Import .dvw file(s) into a SQLite database")
    p1.add_argument("input", nargs="+", metavar="FILE.dvw")
    p1.add_argument("-o", "--db", default="matches.db", metavar="NAME.db",
                    help="Output database filename (default: matches.db)")
    p1.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")

    p2 = sub.add_parser("db2dvw", help="Export match(es) from SQLite to .dvw")
    p2.add_argument("input", metavar="DB.db")
    p2.add_argument("--id", type=int, default=None,
                    help="Export only the match with this file_header_id")
    p2.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, metavar="DIR",
                    help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})")

    p3 = sub.add_parser("info", help="List matches stored in a database")
    p3.add_argument("input", metavar="DB.db")

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    dispatch = {"dvw2db": cmd_dvw2db, "db2dvw": cmd_db2dvw, "info": cmd_info}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
