# dvwconverter - PRE-RELEASE

A minimal, dependency-free Python tool that converts DataVolley `.dvw` scouting files to SQLite and back.

> **v0.3.0** — Expanded field decoding, corrected rotation schema, structured special-event parsing.

## Requirements

Python 3.11+. No third-party libraries.

## Installation

```bash
pip install .
# or without installing:
python -m dvwconverter <command> ...
```

## Quick Start

```bash
dvwconverter dvw2db match.dvw              # import one match
dvwconverter dvw2db *.dvw -o season.db    # import a full season
dvwconverter info output/season.db        # list matches
dvwconverter db2dvw output/season.db --id 1  # export back to .dvw
```

## CLI Reference

### `dvw2db` — Import `.dvw` into SQLite

```
dvwconverter dvw2db FILE.dvw [FILE.dvw ...] [-o NAME.db] [--output-dir DIR]
```

Multiple files go into the same database; each becomes one match identified by `file_header_id`. Add `--verbose` for a
per-section diff report.

### `db2dvw` — Export SQLite back to `.dvw`

```
dvwconverter db2dvw DB.db [--id ID] [-o DIR]
```

Reconstructed files are written to `<DIR>/dvw/`. Round-trip accuracy is printed automatically.

### `info` — List matches

```
dvwconverter info DB.db
```

## Python API

```python
from dvwconverter import parse_dvw, dvw_to_db, db_to_dvw, roundtrip_accuracy

dvw = parse_dvw("match.dvw")
fhid = dvw_to_db(dvw, "season.db")
rt = roundtrip_accuracy("match.dvw", "season.db", fhid, "./output/roundtrip/")
print(rt.format_summary())

written = db_to_dvw("season.db", output_dir="./output/dvw/", file_header_id=1)
```

**Key classes:** `DvwFile`, `MatchInfo`, `Team`, `Player`, `SetScore`, `ScoutEvent`, `AccuracyReport`,
`RoundTripReport`.

## Accuracy Index

Computed after every `dvw2db` conversion:

```
Score = 100 × (0.50 × C_skill + 0.20 × C_header + 0.20 × C_score + 0.10 × C_volume)
```

| Range  | Meaning                                                          |
|--------|------------------------------------------------------------------|
| 90–100 | High confidence — all sections present, nearly all events parsed |
| 70–89  | Good — minor gaps                                                |
| 50–69  | Moderate — notable event parsing gaps                            |
| < 50   | Low — likely incomplete or non-standard file                     |

## Round-Trip Accuracy

```
RoundTripScore = 100 × (0.55 × line_match_ratio + 0.25 × section_coverage + 0.20 × scout_match_ratio)
```

Scout lines are always 100% matched (reconstructed verbatim from `raw`). Use `--verbose` to see changed lines.

## DVW File Format

Plain-text, Windows-1252, CRLF line endings, INI-like section structure. Targets DataVolley 4.x format `2.0`.

### Sections

| Section                | Contents                              |
|------------------------|---------------------------------------|
| `[3DATAVOLLEYSCOUT]`   | File metadata (generator, timestamps) |
| `[3MATCH]`             | Date, league, season, scout ID        |
| `[3TEAMS]`             | Team names, coaches, colours          |
| `[3MORE]`              | Venue, city, referee                  |
| `[3COMMENTS]`          | Free-text or per-set comments         |
| `[3SET]`               | Per-set scores (visiting-first order) |
| `[3PLAYERS-H/V]`       | Player rosters                        |
| `[3ATTACKCOMBINATION]` | Attack play-code definitions          |
| `[3SETTERCALL]`        | Setter call definitions               |
| `[3VIDEO]`             | Linked video file path                |
| `[3SCOUT]`             | Play-by-play events                   |

### `[3SCOUT]` event format

```
[prefix][nn][S][T][E][combo][~zones~target][;tail;fields...]
```

| Part   | Description                        |
|--------|------------------------------------|
| prefix | `*`=visiting, `a`=home             |
| nn     | Jersey number (zero-padded)        |
| S      | Skill code (S/R/E/A/B/D/F/T/O)     |
| T      | Skill type (H/M/Q/U/T/O, optional) |
| E      | Evaluation (+/#/-//!/=, optional)  |

**Tail fields** (semicolon-separated): position 7=`video_time`, 8=`set_number`, 9=`home_rotation_pos`, 10=
`visiting_rotation_pos`, 11=`serving_team`, 14–19=`rotation_home_1..6`, 20–25=`rotation_visiting_1..6`.

> Positions 9 and 10 are **rotation positions (1–6)**, not scores. Running score is in `*p`/`ap` point lines.

**Special lines:**

| Line          | Format     | Decoded fields                             |
|---------------|------------|--------------------------------------------|
| Point         | `*p15:12`  | `point_visiting_score`, `point_home_score` |
| Rotation      | `*z3`      | `rotation_new_pos`                         |
| Substitution  | `*c12:17`  | `sub_out_jersey`, `sub_in_jersey`          |
| Lineup        | `*P18>LUp` | `lineup_server_jersey`                     |
| Rally outcome | `a$$&H#`   | `skill`, `evaluation`                      |

> Score ordering: `[3SET]` and point lines use **visiting-first** (`visiting:home`). `[3TEAMS]` lists home first.

## SQLite Schema

All tables carry a `file_header_id` FK. Key tables:

- **`match`** — date, season, league, phase, match_number, home_indicator, competition_code, home_away, scout_license_id
- **`team`** — team_index (0=home, 1=visiting), team_id, team_name, sets_won, coach, team_color
- **`set_score`** — set_number, played, score_8/16/21, final_score, duration (all scores visiting-first)
- **`player`** — number, role (1=Libero … 5=Setter), special_role (L/C/""), starting_position_s1/s2/s3, foreign_player
- **`scout_event`** — full decoded event with `raw` column for lossless reconstruction

## Skill / Evaluation Codes

| Skill | Meaning     | | Eval | Meaning          |
|-------|-------------|-|------|------------------|
| S     | Serve       | | +    | Positive         |
| R     | Reception   | | #    | Point (ace/kill) |
| E     | Set         | | -    | Negative         |
| A     | Attack      | | /    | Slash            |
| B     | Block       | | !    | Excellent        |
| D     | Dig         | | =    | Error            |
| F     | Freeball    | |      |                  |
| T     | Setter dump | |      |                  |

## Court Coordinate System

Attack and setter positions use a packed `YYXX` integer:

```python
depth = position // 100  # YY — distance from baseline toward net (34–50)
lateral = position % 100  # XX — left-to-right (12–88)
```

## Encoding Scheme

Some fields store `\x0f2`+hex encoded duplicates of their plaintext counterparts (generated only by the Professional
edition). Format: `\x0f` + `2` + Windows-1252 bytes as uppercase hex pairs. These are stored for round-trip fidelity but
carry no additional information.

## Known Limitations

- No official specification — format reverse-engineered from real files.
- Targets DataVolley 4.x format `2.0` only; lite edition files have shorter `[3MATCH]` lines.
- Files are Windows-1252 (parser uses `errors="replace"`).
- Non-scout sections may differ from originals in trailing whitespace; scout lines are always lossless.

## Undecoded / Unknown Fields

- `[3MATCH]` `field9` (constant `"1"`) and `field11` (constant `"0"`) — meaning unknown.
- `[3MORE]` `duration1`/`duration2` — suspected warm-up or break timing; unresolved.
- `[3ATTACKCOMBINATION]` `field9` — suspected back-row flag; unconfirmed.
- `[3WINNINGSYMBOLS]` — per-rally symbol string; encoding not decoded.

## Release Notes

### v0.3.0 — 2026-06-01

- Rotation tail fields expanded to 12 individual columns (`rotation_home_1..6`, `rotation_visiting_1..6`).
- `match.venue_code` renamed to `match.competition_code`.
- New decoded fields: `home_indicator`, `federation_match_id`, `category_code`, `opponent_home_away`,
  `scout_license_id`, `more_info.venue`, `more_info.internal_ids`, `player.special_role`, `player.encoded_short`.
- Special-event lines fully decoded into typed fields.
- `[3SET]` visiting-first score ordering documented; `DvwFile.set_comments` added.

Databases from v0.2.x are **not compatible** and must be re-imported.

### v0.2.0 — 2026-05-30

- Automatic round-trip accuracy on every conversion.
- `db2dvw` output to `output/dvw/`; `roundtrip.py` added to public API.
