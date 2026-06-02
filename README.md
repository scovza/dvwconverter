# dvwconverter

A minimal, dependency-free Python tool that converts DataVolley `.dvw` scouting files to SQLite and back.

> **v0.4.0** — Confirmed field renames, extended rally consequence parsing, widened end-subzone capture.

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
dvwconverter dvw2db match.dvw                        # import one match
dvwconverter dvw2db *.dvw -o season.db               # import a full season
dvwconverter dvw2db match.dvw --rt                   # import + round-trip check
dvwconverter info output/season.db                   # list matches
dvwconverter db2dvw output/season.db --id 1          # export one match to .dvw
dvwconverter db2dvw output/season.db --id 1 --rt     # export + round-trip check
```

## Output Layout

```
output/
  matches.db               ← database (dvw2db)
  dvw/
    match_A.dvw/
      match_A.dvw          ← reconstructed file (db2dvw)
    match_B.dvw/
      match_B.dvw
  roundtrip/
    rt_match_A.dvw         ← round-trip reconstruction (--rt)
```

## CLI Reference

### `dvw2db` — Import `.dvw` into SQLite

```
dvwconverter dvw2db FILE.dvw [FILE.dvw ...] [-o NAME.db] [--output-dir DIR] [--rt] [--verbose]
```

Multiple files go into the same database. Each becomes one match identified by `file_header_id`.

```
  importing  match_01.dvw ... ok  id=1  Home vs Away  events=1154  accuracy=94.3
  importing  match_02.dvw ... ok  id=2  Home vs Away  events=1172  accuracy=91.8

Database : output/matches.db
```

With `--rt`, a round-trip check runs after each import and the result is appended to the status line:

```
  importing  match_01.dvw ... ok  id=1  Home vs Away  events=1154  accuracy=94.3  roundtrip score=97.4  loss=0.31%  scout=100%

Database : output/matches.db
Roundtrip: output/roundtrip/
```

Add `--verbose` for a full per-section diff report after each file. `--verbose` automatically enables `--rt`, so there is no need to pass both flags.

### `db2dvw` — Export SQLite back to `.dvw`

```
dvwconverter db2dvw DB.db [--id ID] [-o DIR] [--rt] [--verbose]
```

Each match is written as `<name>.dvw/<name>.dvw` inside `<output_dir>/dvw/`.

```
  written: output/dvw/match_01.dvw/

Output: output/dvw/
```

With `--rt`:

```
  written: output/dvw/match_01.dvw/
    [rt] roundtrip score=97.4  loss=0.31%  scout=100%

Output: output/dvw/
```

### `info` — List matches

```
dvwconverter info DB.db
```

## Python API

```python
from dvwconverter import (
    parse_dvw, dvw_to_db, db_to_dvw,
    compute_accuracy, roundtrip_accuracy, roundtrip_from_recon,
)

dvw  = parse_dvw("match.dvw")
acc  = compute_accuracy(dvw)
fhid = dvw_to_db(dvw, "season.db")

# optional round-trip check (dvw2db side)
rt = roundtrip_accuracy("match.dvw", "season.db", fhid, "./output/roundtrip/")
print(rt.format_summary())

# export
written = db_to_dvw("season.db", output_dir="./output/dvw/", file_header_id=1)

# optional round-trip check (db2dvw side)
rt2 = roundtrip_from_recon(written[0], "season.db", fhid=1)
if rt2:
    print(rt2.format_summary())
```

**Key classes:** `DvwFile`, `FileHeader`, `MatchInfo`, `Team`, `MoreInfo`, `SetScore`, `Player`,
`AttackCombination`, `SetterCall`, `VideoFile`, `ScoutEvent`, `AccuracyReport`, `RoundTripReport`, `SectionDiff`.

## Accuracy Index

```
Score = 100 × (0.50 × C_skill + 0.20 × C_header + 0.20 × C_score + 0.10 × C_volume)
```

| Component  | Weight | Definition |
|------------|--------|------------|
| `C_skill`  | 0.50   | Fraction of skill events with team, player number, and skill letter decoded |
| `C_header` | 0.20   | `(has_teams + has_players + has_sets) / 3` |
| `C_score`  | 0.20   | Fraction of point events with a decoded running score |
| `C_volume` | 0.10   | `min(total_events / 50, 1.0)` — penalises near-empty files |

| Range  | Meaning |
|--------|---------|
| 90–100 | High confidence — all sections present, nearly all events parsed |
| 70–89  | Good — minor gaps |
| 50–69  | Moderate — notable event parsing gaps |
| < 50   | Low — likely incomplete or non-standard file |

## Round-Trip Score

```
RTS = 100 × (0.55 × line_match_ratio + 0.25 × section_coverage + 0.20 × scout_match_ratio)
```

Scout lines are always 100% matched (stored and replayed verbatim from `raw`). Use `--verbose` to see changed lines (round-trip check is implied automatically).

## DVW File Format

Plain-text, Windows-1252, CRLF line endings. Targets DataVolley 4.x format `2.0`.

| Section                | Contents |
|------------------------|----------|
| `[3DATAVOLLEYSCOUT]`   | Generator metadata, timestamps |
| `[3MATCH]`             | Date, league, season, scout ID |
| `[3TEAMS]`             | Team names, coaches, colours |
| `[3MORE]`              | Venue, city, referee |
| `[3COMMENTS]`          | Free-text or per-set comments |
| `[3SET]`               | Per-set scores (visiting-first order) |
| `[3PLAYERS-H/V]`       | Player rosters |
| `[3ATTACKCOMBINATION]` | Attack play-code definitions |
| `[3SETTERCALL]`        | Setter call definitions |
| `[3WINNINGSYMBOLS]`    | Per-rally symbol string (opaque) |
| `[3VIDEO]`             | Linked video file path |
| `[3SCOUT]`             | Play-by-play events |

### `[3SCOUT]` event format

```
[prefix][nn][S][T][E][combo][~zones~target[subzone]][;tail;fields...]
```

| Part   | Description |
|--------|-------------|
| prefix | `*`=visiting, `a`=home |
| nn     | Jersey number (zero-padded) |
| S      | Skill code (S/R/E/A/B/D/F/T/O) |
| T      | Skill type (H/M/Q/U/T/O, optional) |
| E      | Evaluation (+/#/-//!/=, optional) |

**Tail fields** (semicolon-separated): 1=`point_phase`, 2=`attack_cone`, 7=`video_time`, 8=`set_number`,
9=`home_rotation_pos`, 10=`visiting_rotation_pos`, 11=`serving_team`, 12=`video_frame`,
14–19=`rotation_home_1..6`, 20–25=`rotation_visiting_1..6`.

> Tail positions 9 and 10 are **rotation positions (1–6)**, not scores. Running score is in `*p`/`ap` point lines.

**Special lines:**

| Line          | Format      | Decoded fields |
|---------------|-------------|----------------|
| Point         | `*p15:12`   | `point_visiting_score`, `point_home_score` |
| Rotation      | `*z3`       | `rotation_new_pos` |
| Substitution  | `*c12:17`   | `sub_out_jersey`, `sub_in_jersey` |
| Lineup        | `*P18>LUp`  | `lineup_server_jersey` |
| Rally outcome | `a$$&H#`    | `skill`, `evaluation`; `$$&`=hard attack, `$$D`=block/dig, `$$F`=freeball |

> Score ordering: `[3SET]` and point lines use **visiting-first** (`visiting:home`). `[3TEAMS]` lists home first.

## SQLite Schema

All tables carry a `file_header_id` FK. Key tables:

- **`match`** — date, season, league, phase, match_number, home_indicator, competition_code, home_away, opponent_home_away, federation_match_id, category_code, scout_license_id
- **`team`** — team_index (0=home, 1=visiting), team_id, team_name, sets_won, coach, assistant_coach, team_color
- **`set_score`** — set_number, played, score_8/16/21, final_score, duration (all scores visiting-first)
- **`player`** — number, role (1=Libero…5=Setter), special_role (L/C/""), starting_position_s1–s5, foreign_player
- **`scout_event`** — full decoded event with `raw` column for lossless reconstruction; includes `end_subzone`, `point_phase`, `attack_cone`, all special-event fields, and 12 rotation jersey columns

## Known Limitations

- No official specification — format reverse-engineered from real files.
- Targets DataVolley 4.x format `2.0` only; lite edition files have shorter `[3MATCH]` lines.
- Files are Windows-1252 (`errors="replace"`).
- Non-scout sections may differ from originals in trailing whitespace; scout lines are always lossless.

## Undecoded Fields

- `[3MATCH]` `field9` (constant `"1"`) and `field11` (constant `"0"`) — meaning unknown.
- `[3MORE]` `duration1`/`duration2` — suspected warm-up or break timing; semantics unresolved.
- `[3WINNINGSYMBOLS]` — per-rally symbol string; encoding not decoded.

## Release Notes

### v0.4.0 — 2026-06-02

- `Player.field6`/`field7` renamed to `starting_position_s4`/`starting_position_s5`.
- `AttackCombination.field9` renamed to `is_back_row_attack: bool`.
- `ScoutEvent.custom1` renamed to `point_phase` (`"p"`=won the point, `"s"`=in-rally).
- `ScoutEvent.custom2` renamed to `attack_cone` (`"r"`=cross, `"s"`=line, `"p"`=pipe).
- End-subzone regex widened to `([A-Z]{0,3})` — correctly captures RC, RS, NRC, NRS, IRS, etc.
- Rally consequence parsing extended to `$$D` (block/dig) and `$$F` (freeball).
- Round-trip check made optional (`--rt`); reconstructed files named `rt_<name>.dvw`.
- `db2dvw` output written as `<name>.dvw/<name>.dvw` (each match in its own directory).

Databases from v0.3.x are **not compatible** and must be re-imported.

### v0.3.0 — 2026-06-01

- Rotation tail fields expanded to 12 individual columns.
- `match.venue_code` renamed to `match.competition_code`.
- New decoded fields: `home_indicator`, `federation_match_id`, `category_code`, `opponent_home_away`, `scout_license_id`, `more_info.venue`, `more_info.internal_ids`, `player.special_role`, `player.encoded_short`.
- Special-event lines fully decoded into typed fields.
- `[3SET]` visiting-first score ordering documented; `DvwFile.set_comments` added.

Databases from v0.2.x are **not compatible** and must be re-imported.

### v0.2.0 — 2026-05-30

- Round-trip accuracy introduced.
- `db2dvw` output to `output/dvw/`.
- `roundtrip.py` added to public API.
