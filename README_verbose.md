# dvwconverter

A minimal, dependency-free Python tool that converts DataVolley `.dvw` scouting files to SQLite and back.

> **v0.4.0** — Confirmed field renames, extended rally consequence parsing, widened end-subzone capture.

## Table of Contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [Output Layout](#output-layout)
5. [CLI Reference](#cli-reference)
6. [Python API](#python-api)
7. [Accuracy Index](#accuracy-index)
8. [Round-Trip Accuracy](#round-trip-accuracy)
9. [Architecture Overview](#architecture-overview)
10. [DVW File Format](#dvw-file-format)
11. [SQLite Schema](#sqlite-schema)
12. [Skill / Evaluation Codes](#skill--evaluation-codes)
13. [Court Coordinate System](#court-coordinate-system)
14. [Encoding Scheme](#encoding-scheme)
15. [Undecoded Fields](#undecoded-fields)
16. [Known Limitations](#known-limitations)
17. [To Do](#to-do)
18. [Release Notes](#release-notes)

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

# Import with round-trip check
dvwconverter dvw2db match.dvw --rt

# Import with full per-section diff report
dvwconverter dvw2db match.dvw --rt --verbose

# List matches in a database
dvwconverter info output/season.db

# Export one match back to .dvw
dvwconverter db2dvw output/season.db --id 1

# Export with round-trip check
dvwconverter db2dvw output/season.db --id 1 --rt
```

---

## Output Layout

All output lands under a single root directory (default: `output/`).

```
output/
  matches.db                 ← SQLite database (dvw2db)
  dvw/
    match_A.dvw/
      match_A.dvw            ← reconstructed file (db2dvw)
    match_B.dvw/
      match_B.dvw
  roundtrip/
    rt_match_A.dvw           ← round-trip reconstruction (dvw2db --rt)
    rt_match_B.dvw
```

- Each `db2dvw` export gets its own directory named `<stem>.dvw/`, containing the `.dvw` file with the same stem.
- Round-trip reconstructions (produced by `dvw2db --rt`) are written flat into `roundtrip/`, named `rt_<stem>.dvw`.

---

## CLI Reference

### `dvw2db` — Import `.dvw` into SQLite

```
dvwconverter dvw2db FILE.dvw [FILE.dvw ...] [-o NAME.db] [--output-dir DIR] [--rt] [--verbose]
```

| Argument       | Description                                          |
|----------------|------------------------------------------------------|
| `FILE.dvw`     | One or more DataVolley source files                  |
| `-o NAME.db`   | Output database filename (default: `matches.db`)     |
| `--output-dir` | Root output directory (default: `output/`)           |
| `--rt`         | Run a round-trip check after each import             |
| `--verbose`    | Print full per-section diff report (requires `--rt`) |

Multiple files are imported into the **same** database; each becomes one match identified by `file_header_id`.

**Example — import two files without round-trip:**

```bash
dvwconverter dvw2db match_01.dvw match_02.dvw -o season.db
```

```
  importing  match_01.dvw ... ok  id=1  Home Team vs Away Team  events=1154  accuracy=94.3
  importing  match_02.dvw ... ok  id=2  Home Team vs Away Team  events=1172  accuracy=91.8

Database : output/season.db
```

**Example — with `--rt`:**

```bash
dvwconverter dvw2db match_01.dvw --rt
```

```
  importing  match_01.dvw ... ok  id=1  Home Team vs Away Team  events=1154  accuracy=94.3  roundtrip score=97.4  loss=0.31%  scout=100%

Database : output/matches.db
Roundtrip: output/roundtrip/
```

---

### `db2dvw` — Export SQLite back to `.dvw`

```
dvwconverter db2dvw DB.db [--id ID] [-o DIR] [--rt] [--verbose]
```

| Argument    | Description                                          |
|-------------|------------------------------------------------------|
| `DB.db`     | Source SQLite database                               |
| `--id ID`   | Export only the match with this `file_header_id`     |
| `-o DIR`    | Root output directory (default: `output/`)           |
| `--rt`      | Run a round-trip check after each export             |
| `--verbose` | Print full per-section diff report (requires `--rt`) |

Each exported match is written as `<name>.dvw/<name>.dvw` inside `<output_dir>/dvw/`.

**Example — export all matches:**

```bash
dvwconverter db2dvw output/season.db
```

```
  written: output/dvw/match_01.dvw/
  written: output/dvw/match_02.dvw/

Output: output/dvw/
```

**Example — export one match with round-trip check:**

```bash
dvwconverter db2dvw output/season.db --id 1 --rt
```

```
  written: output/dvw/match_01.dvw/
    [rt] roundtrip score=97.4  loss=0.31%  scout=100%

Output: output/dvw/
```

If the original `.dvw` file has been moved or deleted, the round-trip step is skipped with a notice.

---

### `info` — List matches in a database

```
dvwconverter info DB.db
```

```
  ID  Date          Season      League                           Events  Players  Source
-----------------------------------------------------------------------------------------------
   1  05/01/2026    2025/2026   League A                           1154       25  match_01.dvw
   2  12/01/2026    2025/2026   League A                           1172       24  match_02.dvw
```

---

## Python API

```python
from dvwconverter import (
    parse_dvw, dvw_to_db, db_to_dvw,
    compute_accuracy, AccuracyReport,
    roundtrip_accuracy, roundtrip_from_recon, RoundTripReport, SectionDiff,
)

# Parse and import
dvw = parse_dvw("match.dvw")
acc = compute_accuracy(dvw)
fhid = dvw_to_db(dvw, "season.db")

# Optional round-trip check (dvw2db side)
# Writes rt_match.dvw into recon_dir/
rt: RoundTripReport = roundtrip_accuracy(
    original_path="match.dvw",
    db_path="season.db",
    fhid=fhid,
    recon_dir="./output/roundtrip/",
)
print(rt.format_summary())
print(rt.format_report(verbose=True))

# Export
# Writes output/dvw/match.dvw/match.dvw
written = db_to_dvw("season.db", output_dir="./output/dvw/", file_header_id=1)

# Optional round-trip check (db2dvw side)
rt2 = roundtrip_from_recon(recon_path=written[0], db_path="season.db", fhid=1)
if rt2:
    print(rt2.format_summary())
```

### Key classes

| Class               | Description                                             |
|---------------------|---------------------------------------------------------|
| `DvwFile`           | Root container; holds all sections                      |
| `FileHeader`        | Generator metadata                                      |
| `MatchInfo`         | Match header (date, league, season, scout ID, …)        |
| `Team`              | Team record                                             |
| `MoreInfo`          | Venue, referee, internal IDs                            |
| `SetScore`          | Per-set score snapshots (visiting-first ordering)       |
| `Player`            | Player roster entry (with `special_role`)               |
| `AttackCombination` | Attack play-code definition                             |
| `SetterCall`        | Setter call code definition                             |
| `VideoFile`         | Linked video file path                                  |
| `ScoutEvent`        | Single play-by-play event (with decoded special fields) |
| `AccuracyReport`    | Accuracy Index result and breakdown                     |
| `RoundTripReport`   | Full round-trip diff report and metrics                 |
| `SectionDiff`       | Per-section line-level diff statistics                  |

---

## Accuracy Index

After each `dvw2db` conversion, dvwconverter computes a deterministic **Accuracy Index** (0–100) that estimates
how completely the file was parsed.

### Formula

```
Score = 100 × (0.50 × C_skill + 0.20 × C_header + 0.20 × C_score + 0.10 × C_volume)
```

### Components

| Component  | Weight | Definition                                                                            |
|------------|--------|---------------------------------------------------------------------------------------|
| `C_skill`  | 0.50   | Fraction of skill events where team, player number, and skill letter were all decoded |
| `C_header` | 0.20   | Structural completeness: `(has_teams + has_players + has_sets) / 3`                   |
| `C_score`  | 0.20   | Fraction of point events (`is_point=True`) with a decoded running score               |
| `C_volume` | 0.10   | `min(total_events / 50, 1.0)` — penalises near-empty files                            |

### Interpretation

| Range  | Meaning                                                                |
|--------|------------------------------------------------------------------------|
| 90–100 | High confidence. All major sections present; nearly all events parsed. |
| 70–89  | Good. Minor gaps.                                                      |
| 50–69  | Moderate. Structural data present but event parsing has notable gaps.  |
| < 50   | Low. Likely incomplete or non-standard file.                           |

---

## Round-Trip Accuracy

Run with `--rt` on either command. Reconstructs the `.dvw` from the database and diffs it against the original.

### Score formula

```
RoundTripScore = 100 × (0.55 × line_match_ratio
                       + 0.25 × section_coverage
                       + 0.20 × scout_match_ratio)
```

| Component           | Weight | Definition                                                                  |
|---------------------|--------|-----------------------------------------------------------------------------|
| `line_match_ratio`  | 0.55   | Fraction of original lines present in the reconstruction (multiset)         |
| `section_coverage`  | 0.25   | Fraction of the 14 expected DVW sections present in the reconstruction      |
| `scout_match_ratio` | 0.20   | Fraction of `[3SCOUT]` events identical between original and reconstruction |

### Interpretation

| Range  | Meaning                                                                         |
|--------|---------------------------------------------------------------------------------|
| 95–100 | Lossless or near-lossless. Only cosmetic differences (whitespace, field order). |
| 80–94  | Minor structural data lost; scout events typically intact.                      |
| 60–79  | Moderate loss in header sections; check undecoded fields.                       |
| < 60   | Significant data loss. Likely undecoded fields or format mismatch.              |

Scout events are always 100% matched because the `raw` column is preserved verbatim. Add `--verbose` to print all
changed lines.

### Output files

| Command       | Reconstruction location                                                                         |
|---------------|-------------------------------------------------------------------------------------------------|
| `dvw2db --rt` | `<output_dir>/roundtrip/rt_<stem>.dvw` (flat, no sub-directory)                                 |
| `db2dvw --rt` | Diffs the already-written `<output_dir>/dvw/<stem>.dvw/<stem>.dvw` against the original on disk |

---

## Architecture Overview

```
dvwconverter/
├── parser.py     — Read .dvw text → DvwFile dataclasses
├── db.py         — DvwFile ↔ SQLite (schema, insert, reconstruct, serialise)
├── accuracy.py   — Compute Accuracy Index from a DvwFile
├── roundtrip.py  — Round-trip diff engine (roundtrip_accuracy / roundtrip_from_recon)
└── __main__.py   — CLI (dvw2db / db2dvw / info)
```

---

## DVW File Format

DataVolley `.dvw` files are plain-text, **Windows-1252** encoded, with **CRLF** line endings.

### File structure overview

```
[3DATAVOLLEYSCOUT]
FILEFORMAT: 2.0
GENERATOR-DAY: 05/01/2026 18:16:39
...

[3MATCH]
05/01/2026;;2025/2026;League A;Leg 2;;22;;1252;1;Z;0;...
;;46137;;;;L;R;;52515;

[3TEAMS]
HMT;Home Team;3;Coach Name;Assistant Name;16016139;...
VMT;Away Team;0;Coach Name;...

[3MORE]
;;;City Name;Arena Name;Referee Name;...
;0;0;

[3COMMENTS]
no comments

[3SET]
True;8-4;16-8;21-11;25-14;22;
...

[3PLAYERS-H]
0;1;1;;;*;;;Smith J;Smith;Jane;;C;2;False;;;...

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
*P07>LUp;;;;;;;;1;0;0;;;;9;15;18;10;1;6;7;21;18;11;10;24;
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

| #  | Field                 | Example      | Notes                                                 |
|----|-----------------------|--------------|-------------------------------------------------------|
| 0  | `date`                | `05/01/2026` | DD/MM/YYYY                                            |
| 1  | `time`                | _(empty)_    | HH:MM if present                                      |
| 2  | `season`              | `2025/2026`  |                                                       |
| 3  | `league`              | `League A`   |                                                       |
| 4  | `phase`               | `Leg 2`      |                                                       |
| 5  | `home_indicator`      | `Interno`    | `"Interno"`=home venue, `"Esterno"`=away, empty=unset |
| 6  | `match_number`        | `22`         | Official match number                                 |
| 7  | `federation_match_id` | `11162`      | Numeric ID from the federation or DataVolley platform |
| 8  | `codepage`            | `1252`       | Windows codepage                                      |
| 9  | `field9`              | `1`          | Constant across all observed files; meaning unknown   |
| 10 | `category_code`       | `Z`          | Constant across observed files; competition type code |
| 11 | `field11`             | `0`          | Constant across observed files; unknown flag          |
| 12 | `encoded_league`      |              | `\x0f2`+hex duplicate of `league`                     |
| 13 | `encoded_phase`       |              | `\x0f2`+hex duplicate of `phase`                      |

**Line 2:**

| # | Field                | Example | Notes                                                              |
|---|----------------------|---------|--------------------------------------------------------------------|
| 0 | `field_l2_0`         |         | Unknown                                                            |
| 1 | `field_l2_1`         |         | Unknown                                                            |
| 2 | `competition_code`   | `46137` | League/competition registration code (shared within a competition) |
| 3 | `field_l2_3`         |         | Unknown                                                            |
| 4 | `field_l2_4`         |         | Unknown                                                            |
| 5 | `field_l2_5`         |         | Unknown                                                            |
| 6 | `home_away`          | `L`     | `"L"`=perspective team is home, `"R"`=visiting                     |
| 7 | `opponent_home_away` | `R`     | Mirror of `home_away` for the opponent                             |
| 8 | `field_l2_8`         |         | Unknown                                                            |
| 9 | `scout_license_id`   | `52515` | Numeric DataVolley software license/operator ID                    |

> `home_away` reflects the perspective of the *first team listed in `[3TEAMS]`*, not a global home/away designation.
> A file scouted by the visiting team has `home_away = "R"`.

---

#### `[3TEAMS]`

One line per team (home first, index 0):

| #   | Field              | Notes                                                                          |
|-----|--------------------|--------------------------------------------------------------------------------|
| 0   | `team_id`          | Short code, e.g. `HMT`                                                         |
| 1   | `team_name`        | Full name                                                                      |
| 2   | `sets_won`         | Sets won this match                                                            |
| 3   | `coach`            | Head coach name                                                                |
| 4   | `assistant_coach`  |                                                                                |
| 5   | `team_color`       | Decimal BGR integer                                                            |
| 6–8 | encoded duplicates | `\x0f2`+hex copies of fields 1, 3, 4 — see [Encoding Scheme](#encoding-scheme) |

---

#### `[3MORE]`

Two lines.

**Line 1:**

| #   | Field              | Notes                                      |
|-----|--------------------|--------------------------------------------|
| 0–2 | `field0`–`field2`  | Unknown                                    |
| 3   | `city`             | City where the match was played            |
| 4   | `venue`            | Venue/arena name                           |
| 5   | `referee`          | Referee abbreviation or name               |
| 6–9 | encoded duplicates | `\x0f2`+hex copies of venue/referee fields |

**Line 2:**

| # | Field          | Notes                                                                     |
|---|----------------|---------------------------------------------------------------------------|
| 0 | `internal_ids` | Space-separated DataVolley platform record IDs (optional; rarely present) |
| 1 | `duration1`    | Suspected timing data (warm-up or break duration); semantics unresolved   |
| 2 | `duration2`    | As above                                                                  |

---

#### `[3COMMENTS]`

Free-text match comments. When the file stores per-set comments, entries are semicolon-separated (one per set played).
`DvwFile.set_comments` contains the parsed list; entries reading `"no comments"` are excluded.

---

#### `[3SET]`

Up to 5 lines (one per set). **All score fields use visiting-first order: `visiting_score-home_score`.**
This is the opposite of `[3TEAMS]` where the home team is listed first.

| # | Field         | Example | Notes                             |
|---|---------------|---------|-----------------------------------|
| 0 | `played`      | `True`  |                                   |
| 1 | `score_8`     | `8-4`   | Score at 8 points (visiting-home) |
| 2 | `score_16`    | `16-8`  | Score at 16 points                |
| 3 | `score_21`    | `21-11` | Score at 21 points                |
| 4 | `final_score` | `25-14` | Final set score                   |
| 5 | `duration`    | `22`    | Duration in minutes               |

> `final_score = "25-21"` means the visiting team scored 25 and the home team 21.

---

#### `[3PLAYERS-H]` / `[3PLAYERS-V]`

One line per player:

| #     | Field                        | Notes                                                                               |
|-------|------------------------------|-------------------------------------------------------------------------------------|
| 1     | `number`                     | Jersey number                                                                       |
| 2     | `player_id`                  | Sequential across both rosters                                                      |
| 3–5   | `starting_position_s1/s2/s3` | Rotation slot in sets 1–3 (`1`–`6`, `*`=serves first, blank=not in starting lineup) |
| 6–7   | `starting_position_s4/s5`    | Rotation slot in sets 4–5; empty for ≤3-set matches                                 |
| 8     | `short_name`                 | Abbreviated display name                                                            |
| 9     | `last_name`                  |                                                                                     |
| 10    | `first_name`                 |                                                                                     |
| 11    | `field11`                    | Occasionally populated; meaning unknown                                             |
| 12    | `special_role`               | `"L"`=Libero, `"C"`=Captain, `""`=standard player. Orthogonal to `role`.            |
| 13    | `role`                       | 1=Libero, 2=Outside Hitter, 3=Middle Blocker, 4=Opposite Hitter, 5=Setter           |
| 14    | `foreign`                    | `True`=foreign/non-national player                                                  |
| 15–16 | `field15`, `field16`         | Mostly empty; unknown                                                               |
| 17    | `encoded_short`              | `\x0f2`+hex duplicate of `short_name`                                               |
| 18    | `encoded_last`               | `\x0f2`+hex duplicate of `last_name`                                                |
| 19    | `encoded_first`              | `\x0f2`+hex duplicate of `first_name`                                               |
| 20–23 | `field20`–`field23`          | Additional metadata fields; mostly empty                                            |

> A libero has `special_role="L"` **and** `role=1`. A captain has `special_role="C"` with any `role` value.

---

#### `[3ATTACKCOMBINATION]`

| #  | Field                | Notes                                                                                  |
|----|----------------------|----------------------------------------------------------------------------------------|
| 0  | `code`               | 2-char code used in scout lines (e.g. `X1`)                                            |
| 1  | `tempo`              | 2=quick, 3=half-speed, 4=high, 7=back-row centre, 8=back-row, 9=back-set               |
| 2  | `side`               | `L`=left, `R`=right, `C`=centre                                                        |
| 3  | `height`             | `Q`=quick, `M`=medium, `T`=high, `H`=high-ball, `O`=dump, `U`=super                    |
| 4  | `description`        | Human-readable label                                                                   |
| 5  | `field5`             | Always empty in observed files                                                         |
| 6  | `color`              | Decimal BGR colour                                                                     |
| 7  | `position`           | Packed court position `YYXX` — see [Court Coordinate System](#court-coordinate-system) |
| 8  | `attacker_position`  | `F`=front row, `B`=back row, `C`=centre, `S`=setter, `P`=pipe, `-`=none                |
| 9  | `is_back_row_attack` | Confirmed: `1`=back-row attack (tempo 7/8/9, attacker_position P/F/B)                  |
| 10 | `field10`            | Always empty in observed files                                                         |

---

#### `[3SETTERCALL]`

| # | Field             | Notes                                             |
|---|-------------------|---------------------------------------------------|
| 0 | `code`            | 2-char code, e.g. `K1`                            |
| 1 | `field1`          | Always empty in observed files                    |
| 2 | `description`     | Human-readable label                              |
| 3 | `field3`          | Always empty in observed files                    |
| 4 | `color`           | Decimal BGR colour                                |
| 5 | `x1`              | Setter's position (YYXX packed)                   |
| 6 | `y1`              | Apex of the set-arc ball trajectory (YYXX packed) |
| 7 | `x2`              | Attack target position (YYXX packed)              |
| 8 | `area_list`       | Comma-separated area codes                        |
| 9 | `highlight_color` | Decimal BGR colour                                |

---

#### `[3SCOUT]`

Core play-by-play log. Each line is one event.

**Line prefixes:**

| Prefix          | Meaning                                     |
|-----------------|---------------------------------------------|
| `*`             | Visiting team action                        |
| `a`             | Home team action                            |
| `**Nset`        | Set transition (N = new set number)         |
| `*z` / `az`     | Rotation change                             |
| `*p` / `ap`     | Point scored                                |
| `ac` / `*c`     | Substitution                                |
| `aT` / `*T`     | Timeout                                     |
| `a$$&` / `*$$&` | Rally outcome — hard attack ended the rally |
| `a$$D` / `*$$D` | Rally outcome — block/dig ended the rally   |
| `a$$F` / `*$$F` | Rally outcome — freeball ended the rally    |
| `*P` / `aP`     | Lineup declaration                          |

**Regular skill event format:**

```
[prefix][nn][S][T][E][attack/setter_code][~zones~target[subzone]]
```

| Part     | Width | Description                                                                                                                                      |
|----------|-------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| prefix   | 1     | `*`=visitor, `a`=home                                                                                                                            |
| nn       | 2     | Jersey number, zero-padded                                                                                                                       |
| S        | 1     | Skill code                                                                                                                                       |
| T        | 0–1   | Skill type modifier (optional)                                                                                                                   |
| E        | 0–1   | Evaluation code (optional)                                                                                                                       |
| combo    | 2     | Attack code or `Kxx` setter call                                                                                                                 |
| `~ZZ~TT` | 5     | Start zone ~ end zone                                                                                                                            |
| subzone  | 0–3   | End-subzone suffix: 2–3 char directional code (RC, RS, LC, SC, SS, NRC, NRS, IRS, …). Present on ~94% of attack events. Stored as `end_subzone`. |

**Tail fields** (semicolon-separated after the skill body):

| Position | Field                    | Notes                                                                              |
|----------|--------------------------|------------------------------------------------------------------------------------|
| 1        | `point_phase`            | `"p"`=action won the point; `"s"`=in-rally action; empty=non-skill line            |
| 2        | `attack_cone`            | Attack events only: `"r"`=cross/right, `"s"`=straight/line, `"p"`=pipe/back-center |
| 7        | `video_time`             | `HH.MM.SS`                                                                         |
| 8        | `set_number`             |                                                                                    |
| 9        | `home_rotation_pos`      | Current rotation position (1–6) of the home team — **not the score**               |
| 10       | `visiting_rotation_pos`  | Current rotation position (1–6) of the visiting team — **not the score**           |
| 11       | `serving_team`           | `1`=home serving, `0`=visitor serving                                              |
| 12       | `video_frame`            |                                                                                    |
| 13       | _(empty)_                | Structural separator                                                               |
| 14–19    | `rotation_home_1..6`     | Jersey numbers in each home rotation slot                                          |
| 20–25    | `rotation_visiting_1..6` | Jersey numbers in each visiting rotation slot                                      |

**Special-event line formats:**

| Line type     | Format                         | Parsed fields                                                                                                                                                  |
|---------------|--------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Point         | `*p15:12` / `ap15:12`          | `point_visiting_score=15`, `point_home_score=12`; `*`=visiting scored, `a`=home scored                                                                         |
| Rotation      | `*z3` / `az3`                  | `rotation_new_pos=3`                                                                                                                                           |
| Substitution  | `*c12:17` / `ac12:17`          | `sub_out_jersey=12`, `sub_in_jersey=17`                                                                                                                        |
| Lineup        | `*P18>LUp` / `aP18>LUp`        | `lineup_server_jersey=18`                                                                                                                                      |
| Rally outcome | `a$$&H#` / `a$$DH#` / `a$$FH#` | `skill="H"`, `evaluation="#"` (kill) / `"="` (error) / `"!"` / `"/"`. `$$` char 3: `&`=hard, `D`=block/dig, `F`=freeball. All set `is_point_consequence=True`. |

> **Score ordering:** Both `*p`/`ap` bodies and `[3SET]` score fields use **visiting-first** order
> (`visiting:home` or `visiting-home`). This is the opposite of `[3TEAMS]` where the home team is index 0.

---

## SQLite Schema

All tables except `file_header` carry a `file_header_id` foreign key, allowing multiple matches in one `.db` file.

### `file_header`

| Column          | Type       | Description                       |
|-----------------|------------|-----------------------------------|
| `id`            | INTEGER PK | Auto-assigned                     |
| `source_path`   | TEXT       | Original file path                |
| `file_format`   | TEXT       | DVW format version (e.g. `2.0`)   |
| `generator_day` | TEXT       | File creation timestamp           |
| `generator_prg` | TEXT       | Generating software name          |
| `generator_ver` | TEXT       | Software edition                  |
| `generator_nam` | TEXT       | Club / user / operator name       |
| `lastchange_*`  | TEXT       | Same fields for last modification |

### `match`

| Column                | Type    | Description                                                        |
|-----------------------|---------|--------------------------------------------------------------------|
| `date`                | TEXT    | DD/MM/YYYY                                                         |
| `season`              | TEXT    | e.g. `2025/2026`                                                   |
| `league`              | TEXT    | Competition name                                                   |
| `phase`               | TEXT    | e.g. `Leg 2`                                                       |
| `match_number`        | INTEGER | Official match number                                              |
| `codepage`            | INTEGER | File character set (usually `1252`)                                |
| `home_indicator`      | TEXT    | `"Interno"`=home venue, `"Esterno"`=away, empty=not specified      |
| `federation_match_id` | INTEGER | ID from the federation or DataVolley platform (nullable)           |
| `category_code`       | TEXT    | Competition/category code (constant `"Z"` in observed files)       |
| `competition_code`    | TEXT    | League/competition registration code (shared within a competition) |
| `home_away`           | TEXT    | `"L"`=perspective team is home, `"R"`=visiting                     |
| `opponent_home_away`  | TEXT    | Mirror of `home_away` for the opponent team                        |
| `scout_license_id`    | INTEGER | DataVolley software license/operator ID (nullable)                 |

### `team`

| Column            | Type    | Description            |
|-------------------|---------|------------------------|
| `team_index`      | INTEGER | 0=home, 1=visiting     |
| `team_id`         | TEXT    | Short code             |
| `team_name`       | TEXT    | Full name              |
| `sets_won`        | INTEGER | Sets won in this match |
| `coach`           | TEXT    | Head coach             |
| `assistant_coach` | TEXT    |                        |
| `team_color`      | INTEGER | BGR colour integer     |

### `set_score`

All score columns are in **`visiting_score-home_score`** format.

| Column        | Type    | Description                     |
|---------------|---------|---------------------------------|
| `set_number`  | INTEGER | 1–5                             |
| `played`      | INTEGER | 1=played                        |
| `score_8`     | TEXT    | Score at 8 points, e.g. `"5-8"` |
| `score_16`    | TEXT    | Score at 16 points              |
| `score_21`    | TEXT    | Score at 21 points              |
| `final_score` | TEXT    | Final set score                 |
| `duration`    | INTEGER | Duration in minutes             |

### `player`

| Column                       | Type    | Description                                                                 |
|------------------------------|---------|-----------------------------------------------------------------------------|
| `team_index`                 | INTEGER | 0=home, 1=visiting                                                          |
| `number`                     | INTEGER | Jersey number                                                               |
| `player_id`                  | INTEGER | Sequential id across both rosters                                           |
| `starting_position_s1/s2/s3` | TEXT    | Starting rotation in sets 1–3 (`1`–`6`, `*`=serving)                        |
| `starting_position_s4/s5`    | TEXT    | Starting rotation in sets 4–5; NULL for matches that did not reach that set |
| `short_name`                 | TEXT    | Abbreviated name                                                            |
| `last_name` / `first_name`   | TEXT    |                                                                             |
| `special_role`               | TEXT    | `"L"`=Libero, `"C"`=Captain, `""`=standard player                           |
| `role`                       | INTEGER | 1=Libero, 2=Outside Hitter, 3=Middle Blocker, 4=Opposite Hitter, 5=Setter   |
| `foreign_player`             | INTEGER | 1=foreign/non-national                                                      |

### `more_info`

| Column         | Type    | Description                                                           |
|----------------|---------|-----------------------------------------------------------------------|
| `city`         | TEXT    | City where the match was played                                       |
| `venue`        | TEXT    | Venue/arena name                                                      |
| `referee`      | TEXT    | Referee abbreviation or name                                          |
| `internal_ids` | TEXT    | Space-separated DataVolley platform record IDs (nullable; rarely set) |
| `duration1`    | INTEGER | Timing data; semantics unresolved                                     |
| `duration2`    | INTEGER | As above                                                              |

### `attack_combination`

| Column               | Type    | Description                                          |
|----------------------|---------|------------------------------------------------------|
| `code`               | TEXT    | 2-char identifier (e.g. `X1`)                        |
| `tempo`              | INTEGER | Speed/tempo code                                     |
| `side`               | TEXT    | L/R/C                                                |
| `height`             | TEXT    | Q/M/T/H/O/U                                          |
| `description`        | TEXT    | Human-readable label                                 |
| `color`              | INTEGER | BGR colour                                           |
| `position`           | INTEGER | Packed court position `YYXX`                         |
| `attacker_position`  | TEXT    | F/B/C/S/P/-                                          |
| `is_back_row_attack` | INTEGER | 1 for back-row attacks (tempo 7/8/9, position P/F/B) |

### `setter_call`

| Column        | Type    | Description                     |
|---------------|---------|---------------------------------|
| `code`        | TEXT    | 2-char identifier (e.g. `K1`)   |
| `description` | TEXT    | Human-readable label            |
| `x1`          | TEXT    | Setter's position (YYXX packed) |
| `y1`          | TEXT    | Set arc apex (YYXX packed)      |
| `x2`          | TEXT    | Attack target (YYXX packed)     |
| `area_list`   | TEXT    | Comma-separated area codes      |
| `color`       | INTEGER | BGR colour                      |

### `scout_event`

| Column                   | Type    | Description                                                        |
|--------------------------|---------|--------------------------------------------------------------------|
| `event_order`            | INTEGER | Original line order                                                |
| `raw`                    | TEXT    | Original unmodified line (guarantees lossless round-trip)          |
| `team`                   | TEXT    | `H`=home, `V`=visiting                                             |
| `player_number`          | INTEGER | Jersey number                                                      |
| `skill`                  | TEXT    | S/R/E/A/B/D/F/T/O                                                  |
| `skill_type`             | TEXT    | H/M/Q/U/T/O                                                        |
| `evaluation`             | TEXT    | +/#/-//!/=                                                         |
| `attack_code`            | TEXT    | Attack combination code                                            |
| `setter_code`            | TEXT    | Setter call code                                                   |
| `start_zone`             | TEXT    | Ball origin zone                                                   |
| `end_zone`               | TEXT    | Ball destination zone                                              |
| `end_subzone`            | TEXT    | 2–3 char directional suffix (RC, RS, LC, SC, SS, NRC, NRS, IRS, …) |
| `point_phase`            | TEXT    | `"p"`=action won the point, `"s"`=in-rally, NULL=non-skill line    |
| `attack_cone`            | TEXT    | `"r"`=cross, `"s"`=line, `"p"`=pipe (Attack events only)           |
| `video_time`             | TEXT    | HH.MM.SS                                                           |
| `set_number`             | INTEGER | Set (1–5)                                                          |
| `home_rotation_pos`      | INTEGER | Home team rotation position (1–6); NOT match score                 |
| `visiting_rotation_pos`  | INTEGER | Visiting team rotation position (1–6); NOT match score             |
| `serving_team`           | INTEGER | 1=home serving, 0=visitor serving                                  |
| `video_frame`            | INTEGER |                                                                    |
| `rotation_home_1..6`     | INTEGER | Jersey numbers in each home rotation slot                          |
| `rotation_visiting_1..6` | INTEGER | Jersey numbers in each visiting rotation slot                      |
| `point_visiting_score`   | INTEGER | Running visiting score at time of point                            |
| `point_home_score`       | INTEGER | Running home score at time of point                                |
| `rotation_new_pos`       | INTEGER | New rotation position after `*z`/`az`                              |
| `sub_out_jersey`         | INTEGER | Jersey leaving the court                                           |
| `sub_in_jersey`          | INTEGER | Jersey entering the court                                          |
| `lineup_server_jersey`   | INTEGER | Server jersey in lineup declaration                                |
| `is_set_start`           | INTEGER | Set transition marker                                              |
| `is_rotation`            | INTEGER | Rotation change                                                    |
| `is_point`               | INTEGER | Point scored                                                       |
| `is_substitution`        | INTEGER | Substitution                                                       |
| `is_timeout`             | INTEGER | Timeout                                                            |
| `is_point_consequence`   | INTEGER | Rally outcome (`$$&`, `$$D`, or `$$F`)                             |
| `is_lineup`              | INTEGER | Lineup declaration                                                 |

### Other tables

| Table             | Description                     |
|-------------------|---------------------------------|
| `comments`        | Free-text match comments        |
| `winning_symbols` | Opaque DataVolley symbol string |
| `video_file`      | Linked video file paths         |

---

## Skill / Evaluation Codes

### Skill codes

| Code | Skill         |
|------|---------------|
| `S`  | Serve         |
| `R`  | Reception     |
| `E`  | Set           |
| `A`  | Attack        |
| `B`  | Block         |
| `D`  | Dig / defence |
| `F`  | Freeball      |
| `T`  | Setter dump   |
| `O`  | Other         |

### Skill type codes

| Code | Meaning         |
|------|-----------------|
| `H`  | Jump / hard     |
| `M`  | Medium          |
| `Q`  | Quick           |
| `U`  | Super (high)    |
| `T`  | High ball       |
| `O`  | Overhand / dump |

### Evaluation codes

| Code | Meaning                           |
|------|-----------------------------------|
| `+`  | Positive                          |
| `#`  | Point (ace / kill / direct block) |
| `-`  | Negative                          |
| `/`  | Slash                             |
| `!`  | Excellent                         |
| `=`  | Error                             |

---

## Court Coordinate System

All four-digit integers in `attack_combination.position` and `setter_call.x1/y1/x2` use **packed `YYXX`
encoding**, representing positions on DataVolley's half-court canvas.

```python
depth = position // 100  # YY — distance from baseline toward net
lateral = position % 100  # XX — left-to-right across court width
```

### Axis ranges

| Axis           | Range | Meaning                                       |
|----------------|-------|-----------------------------------------------|
| `YY` (depth)   | ~34   | Own baseline / back-set zone                  |
|                | 37–42 | Back row (pipe, zone 5-6-1, setter positions) |
|                | 44–48 | Mid-court (set arc midpoints)                 |
|                | 49–50 | Front row near net (zone 2-3-4 attacks)       |
| `XX` (lateral) | 12–14 | Zone 4/5 side — left facing the net           |
|                | 38–63 | Centre — zone 3 (front) / zone 6 (back)       |
|                | 75–88 | Zone 1/2 side — right facing the net          |

### Landmark values

| Position | YY | XX | Description                              |
|----------|----|----|------------------------------------------|
| 4114     | 41 | 14 | Back row, zone 5 (back-row left attack)  |
| 4150     | 41 | 50 | Back row centre — pipe attack            |
| 4186     | 41 | 86 | Back row, zone 1 (back-row right attack) |
| 4912     | 49 | 12 | Front left — zone 4                      |
| 4949     | 49 | 49 | Front centre — zone 3                    |
| 4988     | 49 | 88 | Front right — zone 2                     |

---

## Encoding Scheme

Several sections store `\x0f2`+hex encoded duplicates of their plaintext fields. These are generated only by the
full Professional edition of DataVolley; the lite edition leaves them empty.

**Format:**

```
\x0f  +  '2'  +  <Windows-1252 string encoded as uppercase ASCII hex pairs>
```

**Example:** `\x0f24641525345545449` decodes to `FARSETTI`.

The `\x0f` byte acts as an encoding marker; `2` is a version/type prefix; the remaining pairs are the string
bytes as hex. An empty encoded field appears as `\x0f2` alone.

**Affected fields:**

- `[3TEAMS]` fields 6–8: encoded copies of `team_name`, `coach`, `assistant_coach`
- `[3PLAYERS]` fields 17–19: encoded copies of `short_name`, `last_name`, `first_name`
- `[3MORE]` fields 6–9: encoded copies of venue/referee fields

These columns are stored in the database for round-trip fidelity but carry no additional information.

---

## Undecoded Fields

### `[3MATCH]` — line 1

| Field     | Observed          | Status                                    |
|-----------|-------------------|-------------------------------------------|
| `field9`  | `"1"` (all files) | Constant; meaning unknown — possible flag |
| `field11` | `"0"` (all files) | Constant; unknown boolean flag            |

### `[3MATCH]` — line 2

Fields `field_l2_0`, `field_l2_1`, `field_l2_3`, `field_l2_4`, `field_l2_5`, `field_l2_8` are unnamed.

### `[3MORE]` — line 2

| Field       | Observed values | Status                                                         |
|-------------|-----------------|----------------------------------------------------------------|
| `duration1` | `13` / `0`      | Semantics unresolved — possible warm-up time or break duration |
| `duration2` | `7` / `0`       | As above                                                       |

### `[3ATTACKCOMBINATION]`

| Field     | Observed     | Status                  |
|-----------|--------------|-------------------------|
| `field5`  | always empty | No variation to analyse |
| `field10` | always empty | No variation to analyse |

### `[3SETTERCALL]`

| Field    | Observed | Note                            |
|----------|----------|---------------------------------|
| `field1` | empty    | Position 1 in raw line; no data |
| `field3` | empty    | Position 3 in raw line; no data |

### `[3PLAYERS]`

| Field(s) | Notes                                   |
|----------|-----------------------------------------|
| 11       | Occasionally populated; meaning unknown |
| 15, 16   | Mostly empty                            |
| 20–23    | Appear to be additional metadata fields |

### `[3WINNINGSYMBOLS]`

Stored as an opaque string (e.g. `=~~~#~~~=~~~~~~~=...`). Each character likely maps to a per-rally outcome
(`=`=error, `#`=ace, `~`=neutral, `/`=slash), but the exact correspondence to the `[3SCOUT]` sequence has
not been confirmed.

### `[3RESERVE]`

Present in the file structure but not read. No content observed.

---

## Known Limitations

- **No official specification.** The format was reverse-engineered from real files.
- **Format version.** Targets DataVolley 4.x format `2.0`. The lite edition produces shorter `[3MATCH]` lines
  and omits encoded duplicate fields.
- **Encoding.** Files are Windows-1252. The parser uses `errors="replace"` for robustness.
- **Round-trip fidelity.** Scout lines are lossless (replayed from `raw`). Other sections are reconstructed from
  parsed fields and may differ in trailing whitespace or empty field representation.
- **Set limit.** Only up to 5 sets are parsed from `[3SET]`.
- **Score ordering.** `[3SET]` and point-line scores are visiting-first (`visiting-home`), the inverse of
  `[3TEAMS]` ordering. Queries joining these tables must account for this inversion.

---

## To Do

- Decode `[3WINNINGSYMBOLS]` — replay scout events in order and compare symbol sequence to serve evaluations.
- Confirm `[3MATCH]` `field9`/`field11` meaning using files from a different league or gender category.
- Resolve `[3MORE]` `duration1`/`duration2` semantics using files with known warm-up times.
- Add a test suite with sample `.dvw` files.
- Support DataVolley format versions other than `2.0`.

---

## Release Notes

### v0.4.0 — 2026-06-03

**Behavior changes**

- Round-trip check is now **opt-in** (`--rt` flag). Without `--rt`, no reconstruction is performed and no
  roundtrip output is written.
- `db2dvw` output structure changed: each match is written as `<name>.dvw/<name>.dvw` (its own directory)
  rather than a flat `<name>.dvw` file.
- Round-trip reconstructions are now named `rt_<stem>.dvw` (flat inside `roundtrip/`, no sub-directory).
- `dvw2db` status line reformatted: roundtrip fields only appear when `--rt` is active.
- `[rt]` replaces `[roundtrip]` in `db2dvw` output.

**Schema corrections (breaking)**

- `Player.field6`/`field7` renamed to `starting_position_s4`/`starting_position_s5` — confirmed as starting
  rotation positions for sets 4 and 5, parallel to `s1/s2/s3`. Empty for 3-set matches.
- `AttackCombination.field9` renamed to `is_back_row_attack` (bool) — every combination with value `"1"`
  has tempo 7, 8, or 9 and attacker_position `"P"`, `"F"`, or `"B"`.
- `ScoutEvent.custom1` renamed to `point_phase` — `"p"`=action won the point, `"s"`=in-rally action.
- `ScoutEvent.custom2` renamed to `attack_cone` — `"r"`=cross/right, `"s"`=straight/line, `"p"`=pipe/back-center.
- `ScoutEvent.special` field removed — was capturing only the first character of the end-subzone suffix (parser bug).

**Parser bug fixes**

- End-subzone regex widened from `([A-Z]?)` to `([A-Z]{0,3})` — the suffix is 2–3 chars (RC, RS, NRC, NRS,
  IRS, …), not 1. The old regex silently truncated it. Stored as `end_subzone`.
- Rally consequence parsing extended to `$$D` (block/dig) and `$$F` (freeball). Previously only `$$&` was handled.

**Documentation**

- `SetScore.duration` confirmed as set duration in minutes.

Databases from v0.3.x are **not compatible** and must be re-imported.

---

### v0.3.0 — 2026-06-01

**Schema corrections (breaking)**

- `home_score`/`visiting_score` renamed to `home_rotation_pos`/`visiting_rotation_pos` — these tail fields
  hold rotation position (1–6), not match scores.
- Rotation tail fields expanded from 2 blob columns to 12 individual integer columns
  (`rotation_home_1..6`, `rotation_visiting_1..6`).
- `match.venue_code` renamed to `match.competition_code` — the value is shared across all matches in the
  same competition, not per-venue.

**New fields decoded**

- `match.home_indicator` — `"Interno"`=home venue, `"Esterno"`=away.
- `match.federation_match_id` — numeric ID from the federation or DataVolley platform.
- `match.category_code` — constant `"Z"` in observed files.
- `match.opponent_home_away` — mirror of `home_away` for the opponent team.
- `match.scout_license_id` — DataVolley software license/operator ID.
- `more_info.venue` — venue/arena name.
- `more_info.internal_ids` — space-separated DataVolley platform record IDs.
- `player.special_role` — `"L"`=Libero, `"C"`=Captain, `""`=standard player.
- `player.encoded_short` — `\x0f2`+hex duplicate of `short_name`.

**New structured fields on `ScoutEvent`**

- `point_visiting_score`/`point_home_score` — running score from `*p`/`ap` body.
- `rotation_new_pos` — new rotation position from `*z`/`az`.
- `sub_out_jersey`/`sub_in_jersey` — jersey numbers from `*c`/`ac`.
- `lineup_server_jersey` — server jersey from `*P`/`aP`.

**Documentation**

- `[3SET]` score fields documented as visiting-first (`visiting-home`).
- `[3COMMENTS]` per-set format decoded; `DvwFile.set_comments` list added.
- `\x0f2`+hex encoding scheme documented.

Databases from v0.2.x are **not compatible** and must be re-imported.

---

### v0.2.0 — 2026-05-30

- Round-trip accuracy introduced.
- `db2dvw` output to `output/dvw/`.
- `roundtrip.py` module added to public API.
