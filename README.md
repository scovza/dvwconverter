# dvwconverter

A minimal, dependency-free Python tool that converts DataVolley `.dvw` scouting files to SQLite and back.

> **v0.1.0 — First public release.**

---

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [CLI Reference](#cli-reference)
5. [Python API](#python-api)
6. [Accuracy Index](#accuracy-index)
7. [Architecture Overview](#architecture-overview)
8. [DVW File Format](#dvw-file-format)
9. [SQLite Schema](#sqlite-schema)
10. [Skill / Evaluation Codes](#skill--evaluation-codes)
11. [Court Coordinate System](#court-coordinate-system)
12. [Undecoded Fields](#undecoded-fields)
13. [Known Limitations](#known-limitations)
14. [Release Notes](#release-notes)

---

## Requirements

- Python 3.11 or newer
- No third-party libraries required

---

## Installation

```bash
pip install .
```

Or without installing:

```bash
python -m dvwconverter <command> ...
```

---

## Quick Start

```bash
# Import one match
dvwconverter dvw2db match.dvw

# Import a full season
dvwconverter dvw2db *.dvw -o season.db

# List matches in a database
dvwconverter info output/season.db

# Export a match back to .dvw
dvwconverter db2dvw output/season.db --id 1
```

---

## CLI Reference

### `dvw2db` — Import `.dvw` into SQLite

```
dvwconverter dvw2db FILE.dvw [FILE.dvw ...] [-o NAME.db] [--output-dir DIR]
```

| Argument       | Description                                      |
|----------------|--------------------------------------------------|
| `FILE.dvw`     | One or more DataVolley source files              |
| `-o NAME.db`   | Output database filename (default: `matches.db`) |
| `--output-dir` | Root output directory (default: `output/`)       |

Multiple files are imported into the **same** database; each becomes one match identified by `file_header_id`.

```bash
dvwconverter dvw2db match_01.dvw match_02.dvw -o season.db
```

Output:

```
  parsing  match_01.dvw ... ok  [id=1  Home Team vs Away Team  events=1154  accuracy=94.3]
  parsing  match_02.dvw ... ok  [id=2  Home Team vs Away Team  events=1172  accuracy=91.8]

Database: output/season.db
```

---

### `db2dvw` — Export SQLite back to `.dvw`

```
dvwconverter db2dvw DB.db [--id ID] [-o DIR]
```

| Argument  | Description                                      |
|-----------|--------------------------------------------------|
| `DB.db`   | Source SQLite database                           |
| `--id ID` | Export only the match with this `file_header_id` |
| `-o DIR`  | Output directory (default: `output/`)            |

```bash
dvwconverter db2dvw season.db -o ./dvw_export/
dvwconverter db2dvw season.db --id 2 -o ./dvw_export/
```

---

### `info` — List matches in a database

```
dvwconverter info DB.db
```

```
  ID  Date          Season      League                          Events  Players  Source
-----------------------------------------------------------------------------------------------
   1  05/01/2026    2025/2026   League A                          1154       25  match_01.dvw
   2  12/01/2026    2025/2026   League A                          1172       24  match_02.dvw
```

---

## Python API

```python
from dvwconverter import parse_dvw, dvw_to_db, db_to_dvw, compute_accuracy

dvw = parse_dvw("match.dvw")
print(dvw.match.date)  # "05/01/2026"
print(dvw.teams[0].team_name)  # "Home Team"
print(len(dvw.scout_events))  # 1154

report = compute_accuracy(dvw)
print(report)
# Accuracy Index : 94.3 / 100
# ...

dvw_to_db(dvw, "season.db")
db_to_dvw("season.db", output_dir="./output/")
db_to_dvw("season.db", output_dir="./output/", file_header_id=1)
```

### Key classes

| Class               | Description                           |
|---------------------|---------------------------------------|
| `DvwFile`           | Root container; holds all sections    |
| `FileHeader`        | Generator metadata                    |
| `MatchInfo`         | Match header (date, league, season …) |
| `Team`              | Team record                           |
| `MoreInfo`          | Venue, referee                        |
| `SetScore`          | Per-set score snapshots               |
| `Player`            | Player roster entry                   |
| `AttackCombination` | Attack play-code definition           |
| `SetterCall`        | Setter call code definition           |
| `VideoFile`         | Linked video file path                |
| `ScoutEvent`        | Single play-by-play event             |
| `AccuracyReport`    | Accuracy Index result and breakdown   |

---

## Accuracy Index

After each conversion, dvwconverter computes a **deterministic Accuracy Index** (0–100) that estimates how completely
the file was parsed. It is a weighted sum of four measurable components.

### Formula

```
Score = 100 × (0.50 × C_skill + 0.20 × C_header + 0.20 × C_score + 0.10 × C_volume)
```

### Components

| Component  | Weight | Definition                                                                            |
|------------|--------|---------------------------------------------------------------------------------------|
| `C_skill`  | 0.50   | Fraction of skill events where team, player number, and skill letter were all decoded |
| `C_header` | 0.20   | Structural completeness: `(has_teams + has_players + has_sets) / 3`                   |
| `C_score`  | 0.20   | Fraction of skill events carrying embedded `home_score` and `visiting_score`          |
| `C_volume` | 0.10   | `min(total_events / 50, 1.0)` — penalises near-empty files                            |

### Score interpretation

| Range  | Meaning                                                                |
|--------|------------------------------------------------------------------------|
| 90–100 | High confidence. All major sections present; nearly all events parsed. |
| 70–89  | Good. Minor gaps, e.g. some events lack score context.                 |
| 50–69  | Moderate. Structural data present but event parsing has notable gaps.  |
| < 50   | Low. Likely incomplete or non-standard file.                           |

### Limitations

- The index measures **parsing completeness**, not semantic correctness. A file can score 100 and still contain
  encoding artefacts or misidentified field positions.
- `C_score` depends on DataVolley embedding score context in the export; some versions omit it, reducing the score
  without affecting parse quality.
- `C_volume` uses a fixed minimum of 50 events. Very short scrimmage files will score lower even if perfectly parsed.
- Undecoded fields (`fieldN`) are ignored — they do not affect the score.

---

## Architecture Overview

```
dvwconverter/
├── parser.py     — Read .dvw text → DvwFile dataclasses
├── db.py         — DvwFile ↔ SQLite (schema, insert, reconstruct, serialise)
├── accuracy.py   — Compute Accuracy Index from a DvwFile
└── __main__.py   — CLI (dvw2db / db2dvw / info)
```

**Data flow:**

```
.dvw file
   │
   ▼  parse_dvw()          parser.py
DvwFile ──────────────────────────────►  in-memory dataclasses
   │
   │  dvw_to_db()          db.py
   ▼
SQLite .db ◄──────────────────────────  db_to_dvw()  →  .dvw file
```

The parser is a single-pass line scanner. It detects `[3SECTION]` markers, accumulates lines into a buffer, and
dispatches to a dedicated parser function when the section ends. No third-party libraries are used.

The database layer uses only the Python standard library (`sqlite3`). Schema creation is idempotent (`CREATE TABLE IF
NOT EXISTS`), so multiple imports into the same database are safe. The `raw` column in `scout_event` preserves the
original unmodified scout line, making round-trips lossless regardless of how much the skill body was decoded.

---

## DVW File Format

DataVolley `.dvw` files are plain-text, **Windows-1252** encoded, with **CRLF** line endings and an INI-like section
structure.

### File structure overview

```
[3DATAVOLLEYSCOUT]
FILEFORMAT: 2.0
GENERATOR-DAY: 05/01/2026 18:16:39
...

[3MATCH]
05/01/2026;;2025/2026;League A;Leg 2;;22;;1252;...
;;10001;;;;L;R;;20202;

[3TEAMS]
HMT;Home Team;3;Coach Name;Assistant Name;16016139;...
VMT;Away Team;0;Coach Name;...

[3MORE]
;;;City Name;;Referee Name;...
;0;0;

[3COMMENTS]
no comments

[3SET]
True;8-4;16-8;21-11;25-14;22;
...

[3PLAYERS-H]
0;1;1;;;*;;;Smith J;Smith;Jane;;;2;False;;;...

[3PLAYERS-V]
...

[3ATTACKCOMBINATION]
X1;3;R;Q;Quick right;;65280;4956;C;;

[3SETTERCALL]
K1;;Quick right;;16711680;3949;4454;4958;;;

[3WINNINGSYMBOLS]
=~~~#~~~=~~~~~~~=...

[3VIDEO]
Camera0=C:\path\to\video.MP4

[3SCOUT]
*P07>LUp...
a14SA!~~~11...
```

---

### Section reference

#### `[3DATAVOLLEYSCOUT]`

Key-value pairs: `FILEFORMAT`, `GENERATOR-DAY/IDP/PRG/REL/VER/NAM`, and equivalent `LASTCHANGE-*` fields.

---

#### `[3MATCH]`

Two semicolon-delimited lines.

**Line 1:**

| # | Field          | Example      | Notes            |
|---|----------------|--------------|------------------|
| 0 | `date`         | `05/01/2026` | DD/MM/YYYY       |
| 1 | `time`         | _(empty)_    | HH:MM if present |
| 2 | `season`       | `2025/2026`  |                  |
| 3 | `league`       | `League A`   |                  |
| 4 | `phase`        | `Leg 2`      |                  |
| 6 | `match_number` | `22`         |                  |
| 8 | `codepage`     | `1252`       | Windows codepage |

**Line 2:**

| # | Field        | Example | Notes                 |
|---|--------------|---------|-----------------------|
| 2 | `venue_code` | `10001` |                       |
| 6 | `home_away`  | `L`     | `L`=home, `V`=visitor |
| 9 | `scout_code` | `20202` |                       |

---

#### `[3TEAMS]`

One line per team (home first):

| #   | Field           | Notes                  |
|-----|-----------------|------------------------|
| 0   | `team_id`       | Short code, e.g. `HMT` |
| 1   | `team_name`     | Full name              |
| 2   | `sets_won`      | Sets won this match    |
| 3   | `coach`         | Head coach name        |
| 5   | `team_color`    | Decimal BGR integer    |
| 6–8 | encoded strings | Internal hex strings   |

---

#### `[3SET]`

Up to 5 lines (one per set):

| # | Field         | Example |
|---|---------------|---------|
| 0 | `played`      | `True`  |
| 1 | `score_8`     | `8-4`   |
| 2 | `score_16`    | `16-8`  |
| 3 | `score_21`    | `21-11` |
| 4 | `final_score` | `25-14` |
| 5 | `duration`    | `22`    |

---

#### `[3PLAYERS-H]` / `[3PLAYERS-V]`

One line per player:

| #   | Field                        | Notes                                                              |
|-----|------------------------------|--------------------------------------------------------------------|
| 1   | `number`                     | Jersey number                                                      |
| 2   | `player_id`                  | Sequential across both rosters                                     |
| 3–5 | `starting_position_s1/s2/s3` | Rotation in sets 1–3 (1–6, `*`=serves, blank=not starting)         |
| 8   | `short_name`                 | Abbreviated display name                                           |
| 9   | `last_name`                  |                                                                    |
| 10  | `first_name`                 |                                                                    |
| 13  | `role`                       | 1=libero, 2=outside hitter, 3=middle blocker, 4=opposite, 5=setter |
| 14  | `foreign`                    | `True` = foreign player                                            |

---

#### `[3ATTACKCOMBINATION]`

| # | Field               | Notes                                                                                  |
|---|---------------------|----------------------------------------------------------------------------------------|
| 0 | `code`              | 2-char code used in scout lines (e.g. `X1`)                                            |
| 1 | `tempo`             | 2=quick, 3=half-speed, 4=high, 7=back-row centre, 8=back-row, 9=back-set               |
| 2 | `side`              | `L`=left, `R`=right, `C`=centre                                                        |
| 3 | `height`            | `Q`=quick, `M`=medium, `T`=high, `H`=high-ball, `O`=dump, `U`=super                    |
| 4 | `description`       | Human-readable label                                                                   |
| 6 | `color`             | Decimal BGR colour                                                                     |
| 7 | `position`          | Packed court position `YYXX` — see [Court Coordinate System](#court-coordinate-system) |
| 8 | `attacker_position` | `F`=front row, `B`=back row, `C`=centre, `S`=setter, `P`=pipe, `-`=none                |

---

#### `[3SETTERCALL]`

| # | Field             | Notes                                                                                    |
|---|-------------------|------------------------------------------------------------------------------------------|
| 0 | `code`            | 2-char code, e.g. `K1`                                                                   |
| 2 | `description`     | Human-readable label                                                                     |
| 4 | `color`           | Decimal BGR colour                                                                       |
| 5 | `x1`              | Setter's position (YYXX packed; same encoding as `attack_combination.position`)          |
| 6 | `y1`              | Apex of the set-arc ball trajectory (YYXX packed)                                        |
| 7 | `x2`              | Attack target position (YYXX packed; matches `attack_combination.position` to within ±2) |
| 8 | `area_list`       | Comma-separated area codes (used when x1/y1/x2 are 0)                                    |
| 9 | `highlight_color` | Decimal BGR colour                                                                       |

---

#### `[3SCOUT]`

Core play-by-play log. Each line is one event.

**Line prefixes:**

| Prefix      | Meaning                             |
|-------------|-------------------------------------|
| `*`         | Visiting team action                |
| `a`         | Home team action                    |
| `**Nset`    | Set transition (N = new set number) |
| `*z` / `az` | Rotation change                     |
| `*p` / `ap` | Point scored                        |
| `ac` / `*c` | Substitution                        |
| `aT` / `*T` | Timeout                             |
| `$$&`       | Rally outcome                       |
| `*P` / `aP` | Starting lineup declaration         |

**Regular skill event format:**

```
[prefix][nn][S][T][E][attack/setter_code][~zones~target][specials]
```

| Part     | Width | Description                      |
|----------|-------|----------------------------------|
| prefix   | 1     | `*`=visitor, `a`=home            |
| nn       | 2     | Jersey number, zero-padded       |
| S        | 1     | Skill code                       |
| T        | 0–1   | Skill type modifier (optional)   |
| E        | 0–1   | Evaluation code (optional)       |
| combo    | 2     | Attack code or `Kxx` setter call |
| `~ZZ~TT` | 5     | Start zone ~ end zone + subzone  |

**Tail fields** (semicolon-separated after the skill body):

| Position | Field                              |
|----------|------------------------------------|
| 7        | `video_time` — HH.MM.SS            |
| 8        | `set_number`                       |
| 9        | `home_score`                       |
| 10       | `visiting_score`                   |
| 11       | `serving_team` (1=home, 0=visitor) |
| 12       | `video_frame`                      |
| 14       | `rotation_home` — 6 jersey numbers |
| 15       | `rotation_visiting`                |

---

## Skill / Evaluation Codes

### Skill codes

| Code | Skill            |
|------|------------------|
| `S`  | Serve            |
| `R`  | Reception        |
| `E`  | Set              |
| `A`  | Attack           |
| `B`  | Block            |
| `D`  | Dig / defence    |
| `F`  | Freeball         |
| `T`  | Setter dump      |
| `O`  | Other / overpass |

### Skill type codes

| Code | Meaning       |
|------|---------------|
| `H`  | Jump / hard   |
| `M`  | Medium        |
| `Q`  | Quick         |
| `U`  | Super (high)  |
| `T`  | High ball     |
| `O`  | Overhand/dump |

### Evaluation codes

| Code | Meaning                           |
|------|-----------------------------------|
| `+`  | Positive                          |
| `#`  | Point (ace / kill / direct block) |
| `-`  | Negative                          |
| `/`  | Half-positive                     |
| `!`  | Excellent                         |
| `=`  | Error                             |

---

## SQLite Schema

All tables except `file_header` carry a `file_header_id` foreign key, allowing multiple matches in one `.db` file.

### `file_header`

One row per imported `.dvw` file.

| Column          | Type       | Description                       |
|-----------------|------------|-----------------------------------|
| `id`            | INTEGER PK | Auto-assigned                     |
| `source_path`   | TEXT       | Original file path                |
| `file_format`   | TEXT       | DVW format version (e.g. `2.0`)   |
| `generator_day` | TEXT       | File creation timestamp           |
| `generator_prg` | TEXT       | Generating software name          |
| `generator_ver` | TEXT       | Software edition                  |
| `generator_nam` | TEXT       | Club / user name                  |
| `lastchange_*`  | TEXT       | Same fields for last modification |

### `match`

| Column         | Type    | Description                       |
|----------------|---------|-----------------------------------|
| `date`         | TEXT    | DD/MM/YYYY                        |
| `season`       | TEXT    | e.g. `2025/2026`                  |
| `league`       | TEXT    | Competition name                  |
| `phase`        | TEXT    | e.g. `Leg 2`                      |
| `match_number` | INTEGER | Official match number             |
| `codepage`     | INTEGER | File character set (usually 1252) |
| `venue_code`   | TEXT    | Venue identifier                  |
| `home_away`    | TEXT    | `L`=home, `V`=visitor             |

### `team`

| Column       | Type    | Description            |
|--------------|---------|------------------------|
| `team_index` | INTEGER | 0=home, 1=visiting     |
| `team_id`    | TEXT    | Short code             |
| `team_name`  | TEXT    | Full name              |
| `sets_won`   | INTEGER | Sets won in this match |
| `coach`      | TEXT    | Head coach             |
| `team_color` | INTEGER | BGR colour integer     |

### `set_score`

| Column        | Type    | Description                   |
|---------------|---------|-------------------------------|
| `set_number`  | INTEGER | 1–5                           |
| `played`      | INTEGER | 1=played                      |
| `score_8`     | TEXT    | Score at 8 points             |
| `score_16`    | TEXT    | Score at 16 points            |
| `score_21`    | TEXT    | Score at 21 points            |
| `final_score` | TEXT    | Final set score               |
| `duration`    | INTEGER | Duration in minutes (approx.) |

### `player`

| Column                       | Type    | Description                                                        |
|------------------------------|---------|--------------------------------------------------------------------|
| `team_index`                 | INTEGER | 0=home, 1=visiting                                                 |
| `number`                     | INTEGER | Jersey number                                                      |
| `player_id`                  | INTEGER | Sequential id                                                      |
| `starting_position_s1/s2/s3` | TEXT    | Starting rotation (1–6, `*`=serving)                               |
| `short_name`                 | TEXT    | Abbreviated name                                                   |
| `last_name` / `first_name`   | TEXT    |                                                                    |
| `role`                       | INTEGER | 1=libero, 2=outside hitter, 3=middle blocker, 4=opposite, 5=setter |
| `foreign_player`             | INTEGER | 1=foreign                                                          |

### `attack_combination`

| Column              | Type    | Description                                                                            |
|---------------------|---------|----------------------------------------------------------------------------------------|
| `code`              | TEXT    | 2-char identifier (e.g. `X1`)                                                          |
| `tempo`             | INTEGER | Speed/tempo                                                                            |
| `side`              | TEXT    | L/R/C                                                                                  |
| `height`            | TEXT    | Q/M/T/H/O/U                                                                            |
| `description`       | TEXT    | Human-readable label                                                                   |
| `color`             | INTEGER | BGR colour                                                                             |
| `position`          | INTEGER | Packed court position `YYXX` — see [Court Coordinate System](#court-coordinate-system) |
| `attacker_position` | TEXT    | F/B/C/S/P/-                                                                            |

### `setter_call`

| Column        | Type    | Description                                                        |
|---------------|---------|--------------------------------------------------------------------|
| `code`        | TEXT    | 2-char identifier (e.g. `K1`)                                      |
| `description` | TEXT    | Human-readable label                                               |
| `x1`          | INTEGER | Setter's position (YYXX packed)                                    |
| `y1`          | INTEGER | Set arc apex (YYXX packed)                                         |
| `x2`          | INTEGER | Attack target (YYXX packed; matches `attack_combination.position`) |
| `area_list`   | TEXT    | Comma-separated area codes                                         |
| `color`       | INTEGER | BGR colour                                                         |

### `scout_event`

| Column                 | Type    | Description                                    |
|------------------------|---------|------------------------------------------------|
| `event_order`          | INTEGER | Original line order                            |
| `raw`                  | TEXT    | Original unmodified line (lossless round-trip) |
| `team`                 | TEXT    | `H`=home, `V`=visiting                         |
| `player_number`        | INTEGER | Jersey number                                  |
| `skill`                | TEXT    | S/R/E/A/B/D/F/T/O                              |
| `skill_type`           | TEXT    | H/M/Q/U/T/O                                    |
| `evaluation`           | TEXT    | +/#/-//!/=                                     |
| `attack_code`          | TEXT    | Attack combination code                        |
| `setter_code`          | TEXT    | Setter call code                               |
| `start_zone`           | TEXT    | Ball origin zone                               |
| `end_zone`             | TEXT    | Ball destination zone                          |
| `video_time`           | TEXT    | HH.MM.SS                                       |
| `set_number`           | INTEGER | Set (1–5)                                      |
| `home_score`           | INTEGER |                                                |
| `visiting_score`       | INTEGER |                                                |
| `serving_team`         | INTEGER | 1=home, 0=visitor                              |
| `video_frame`          | INTEGER |                                                |
| `rotation_home`        | TEXT    | 6 jersey numbers                               |
| `rotation_visiting`    | TEXT    | 6 jersey numbers                               |
| `is_set_start`         | INTEGER | Set transition marker                          |
| `is_rotation`          | INTEGER | Rotation change                                |
| `is_point`             | INTEGER | Point scored                                   |
| `is_substitution`      | INTEGER | Substitution                                   |
| `is_timeout`           | INTEGER | Timeout                                        |
| `is_point_consequence` | INTEGER | Rally outcome                                  |
| `is_lineup`            | INTEGER | Starting lineup declaration                    |

### Other tables

| Table             | Description                     |
|-------------------|---------------------------------|
| `more_info`       | Venue city and referee name     |
| `comments`        | Free-text match comments        |
| `winning_symbols` | Opaque DataVolley symbol string |
| `video_file`      | Linked video file paths         |

---

## Court Coordinate System

All four-digit integers in `attack_combination.position` and `setter_call.x1/y1/x2` use the same **packed `YYXX`
encoding**, representing positions on DataVolley's half-court canvas (attacking team's half, viewed from behind the
baseline toward the net).

```python
depth = position // 100  # YY — distance from baseline toward net
lateral = position % 100  # XX — left-to-right across court width
```

### Axis ranges

| Axis           | Range | Meaning                                        |
|----------------|-------|------------------------------------------------|
| `YY` (depth)   | ~34   | Own baseline / back-set zone                   |
|                | 37–42 | Back row (pipe / zone 5-6-1, setter positions) |
|                | 44–48 | Mid-court (set arc midpoints)                  |
|                | 49–50 | Front row near net (zone 2-3-4 attacks)        |
| `XX` (lateral) | 12–14 | Zone 4/5 side — left facing the net            |
|                | 38–63 | Centre — zone 3 (front) / zone 6 (back)        |
|                | 75–88 | Zone 1/2 side — right facing the net           |

### Landmark values

| Position | YY | XX | Description                              |
|----------|----|----|------------------------------------------|
| 4114     | 41 | 14 | Back row, zone 5 (back-row left attack)  |
| 4150     | 41 | 50 | Back row centre — pipe attack            |
| 4186     | 41 | 86 | Back row, zone 1 (back-row right attack) |
| 4912     | 49 | 12 | Front left — zone 4                      |
| 4949     | 49 | 49 | Front centre — zone 3                    |
| 4988     | 49 | 88 | Front right — zone 2                     |

### `setter_call` arc semantics

`x1`, `y1`, `x2` together describe the ball-flight arc of the set:

| Field | Meaning                                                            |
|-------|--------------------------------------------------------------------|
| `x1`  | Setter's starting position                                         |
| `y1`  | Apex of the set arc                                                |
| `x2`  | Attack target — matches `attack_combination.position` to within ±2 |

When `x1 = y1 = x2 = 0`, the setter call uses `area_list` (a zone polygon) instead.

---

## Undecoded Fields

The following fields are stored under generic names (`field5`, `field_l2_1`, etc.) because their meaning could not be
determined from available data. Decoding them would require official DataVolley documentation or a larger file corpus.

### `[3MATCH]` — line 1

Fields 5, 7, 9, 10, 11 appear to carry internal match identifiers or flags.

### `[3MATCH]` — line 2

Fields 0, 1, 3, 4, 5, 7, 8 are unnamed. Only `home_away` (field 6) and `scout_code` (field 9) were identified.

### `[3ATTACKCOMBINATION]`

| Field   | Observed values | Best guess    | Why unconfirmed                                    |
|---------|-----------------|---------------|----------------------------------------------------|
| field5  | always empty    | unknown       | No variation to analyse                            |
| field9  | `1` or empty    | back-row flag | Correlates with back-row attacks but not confirmed |
| field10 | always empty    | unknown       | No variation to analyse                            |

### `[3SETTERCALL]`

| Field  | Observed values | Note                                |
|--------|-----------------|-------------------------------------|
| field1 | always empty    | Position 1 in the raw line; no data |
| field3 | always empty    | Position 3 in the raw line; no data |

### `[3PLAYERS]`

| Field(s)   | Notes                                                                        |
|------------|------------------------------------------------------------------------------|
| 6, 7       | Consistently empty                                                           |
| 11         | Occasionally populated with short strings                                    |
| 12         | Suspected `L`=libero / `C`=captain flag; not confirmed across enough players |
| 15, 16, 17 | Mostly empty                                                                 |
| 20–23      | Appear to be additional encoded or metadata fields                           |

### `[3MORE]`

Line 1 fields 0, 1, 2, 4 are unnamed. `duration1`/`duration2` on line 2 are likely set durations in minutes, but the
unit is unconfirmed.

### `[3SCOUT]` — parsed but not stored

| Attribute     | Reason not stored                               |
|---------------|-------------------------------------------------|
| `end_subzone` | Sub-zone suffix after end zone; meaning unclear |
| `special`     | Character after zone block; purpose unknown     |
| `custom1/2`   | Scouter-defined free-text fields                |

### `[3SCOUT]` — special lines partially decoded

| Line type            | Decoded        | Not decoded                         |
|----------------------|----------------|-------------------------------------|
| `$$&` rally outcome  | Line type only | Content after prefix (rally result) |
| `*c` / `ac` sub      | Line type only | Player numbers being swapped        |
| `*z` / `az` rotation | Line type only | New rotation state                  |

### `[3WINNINGSYMBOLS]`

Stored as an opaque string. The per-character encoding is unknown.

### `[3RESERVE]`

Present in the file but not read. No content observed.

---

## Known Limitations

- **No official specification.** The format was reverse-engineered from real files. Field positions and meanings are
  empirically derived and may not hold across all DataVolley versions.
- **Format version.** Targets DataVolley 4.x format `2.0`. Earlier versions may have different field counts.
- **Encoding.** Files are Windows-1252. The parser uses `errors="replace"` for robustness; replacement characters
  may appear in names containing unusual characters.
- **Round-trip fidelity.** Scout lines are reconstructed from `raw`, not from parsed fields, so the scout section is
  always lossless. Other sections are reconstructed from parsed fields and may differ in trailing whitespace or empty
  field representation.
- **Set limit.** Only up to 5 sets are parsed from `[3SET]`.
- **Special scout events.** Substitution, rotation, and rally-outcome lines are classified but their payload is not
  decoded into structured fields.

---

## Release Notes

### v0.1.0 — 2026-05-30

First public release.

**Features**

- Parse DataVolley `.dvw` format 2.0 (Windows-1252) into typed Python dataclasses.
- Import one or more `.dvw` files into a single SQLite database.
- Export SQLite database back to `.dvw` with lossless scout-section round-trips.
- CLI commands: `dvw2db`, `db2dvw`, `info`.
- Accuracy Index: deterministic 0–100 conversion confidence score.
- All output written to `output/` by default.
- No third-party dependencies.

**Known gaps (tracked for future releases)**

- Substitution, rotation, and rally-outcome scout lines are classified but not fully decoded.
- Several `[3MATCH]`, `[3MORE]`, `[3PLAYERS]`, and `[3ATTACKCOMBINATION]` fields remain unnamed.
- No test suite yet.
