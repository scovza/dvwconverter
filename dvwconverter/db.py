"""Convert DvwFile objects to/from an SQLite database."""

import sqlite3
from pathlib import Path
from .parser import (
    DvwFile, FileHeader, MatchInfo, Team, MoreInfo, SetScore,
    Player, AttackCombination, SetterCall, VideoFile, ScoutEvent,
    ENCODING,
)

# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS file_header (
    id                INTEGER PRIMARY KEY,
    source_path       TEXT,
    file_format       TEXT,
    generator_day     TEXT,
    generator_idp     TEXT,
    generator_prg     TEXT,
    generator_rel     TEXT,
    generator_ver     TEXT,
    generator_nam     TEXT,
    lastchange_day    TEXT,
    lastchange_idp    TEXT,
    lastchange_prg    TEXT,
    lastchange_rel    TEXT,
    lastchange_ver    TEXT,
    lastchange_nam    TEXT
);

CREATE TABLE IF NOT EXISTS match (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    date              TEXT,
    time              TEXT,
    season            TEXT,
    league            TEXT,
    phase             TEXT,
    match_number      INTEGER,
    codepage          INTEGER,
    -- "Interno"=home venue, "Esterno"=away, empty=not specified
    home_indicator    TEXT,
    -- Numeric ID assigned by the federation or DataVolley platform
    federation_match_id INTEGER,
    -- Constant "1" across all observed files; meaning unknown
    field9            TEXT,
    -- Constant "Z" across all observed files; competition/category code
    category_code     TEXT,
    -- Constant "0"; unknown flag
    field11           TEXT,
    encoded_league    TEXT,
    encoded_phase     TEXT,
    field_l2_0        TEXT,
    field_l2_1        TEXT,
    -- League/competition registration code (was incorrectly named venue_code)
    competition_code  TEXT,
    field_l2_3        TEXT,
    field_l2_4        TEXT,
    field_l2_5        TEXT,
    -- "L"=perspective team is home, "R"=visiting
    home_away         TEXT,
    -- Mirror of home_away for the opponent team
    opponent_home_away TEXT,
    field_l2_8        TEXT,
    -- Numeric DataVolley software license / operator ID for the scout
    scout_license_id  INTEGER
);

CREATE TABLE IF NOT EXISTS more_info (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    city              TEXT,
    venue             TEXT,
    referee           TEXT,
    internal_ids      TEXT,
    duration1         INTEGER,
    duration2         INTEGER,
    field0            TEXT,
    field1            TEXT,
    field2            TEXT,
    encoded_field6    TEXT,
    encoded_city      TEXT,
    encoded_field8    TEXT,
    encoded_referee   TEXT
);

CREATE TABLE IF NOT EXISTS comments (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    text              TEXT
);

CREATE TABLE IF NOT EXISTS team (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    team_index        INTEGER,
    team_id           TEXT,
    team_name         TEXT,
    sets_won          INTEGER,
    coach             TEXT,
    assistant_coach   TEXT,
    team_color        INTEGER,
    encoded_name      TEXT,
    encoded_coach     TEXT,
    encoded_asst_coach TEXT
);

CREATE TABLE IF NOT EXISTS set_score (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    set_number        INTEGER,
    played            INTEGER,
    score_8           TEXT,
    score_16          TEXT,
    score_21          TEXT,
    final_score       TEXT,
    duration          INTEGER
);

CREATE TABLE IF NOT EXISTS player (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    team_index        INTEGER,
    number            INTEGER,
    player_id         INTEGER,
    starting_position_s1 TEXT,
    starting_position_s2 TEXT,
    starting_position_s3 TEXT,
    short_name        TEXT,
    last_name         TEXT,
    first_name        TEXT,
    role              INTEGER,
    foreign_player    INTEGER,
    field6            TEXT,
    field7            TEXT,
    field11           TEXT,
    -- "L"=Libero, "C"=Captain, ""=standard player
    special_role      TEXT,
    field15           TEXT,
    field16           TEXT,
    -- \x0f2+hex encoded duplicates (redundant with plaintext name fields)
    encoded_short     TEXT,
    encoded_last      TEXT,
    encoded_first     TEXT,
    field20           TEXT,
    field21           TEXT,
    field22           TEXT,
    field23           TEXT
);

-- NOTE: All score fields in set_score are "visiting_score-home_score" (visiting first).
-- This is the OPPOSITE of [3TEAMS] ordering where home is listed first.
-- e.g. final_score "25-21" means visiting scored 25, home scored 21.

CREATE TABLE IF NOT EXISTS attack_combination (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    code              TEXT,
    tempo             INTEGER,
    side              TEXT,
    height            TEXT,
    description       TEXT,
    color             INTEGER,
    position          INTEGER,
    attacker_position TEXT,
    field5            TEXT,
    field9            TEXT,
    field10           TEXT
);

CREATE TABLE IF NOT EXISTS setter_call (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    code              TEXT,
    description       TEXT,
    color             INTEGER,
    x1                INTEGER,
    y1                INTEGER,
    x2                INTEGER,
    area_list         TEXT,
    highlight_color   INTEGER,
    field1            TEXT,
    field3            TEXT
);

CREATE TABLE IF NOT EXISTS winning_symbols (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    symbols           TEXT
);

CREATE TABLE IF NOT EXISTS video_file (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    camera_id         INTEGER,
    file_path         TEXT
);

CREATE TABLE IF NOT EXISTS scout_event (
    id                INTEGER PRIMARY KEY,
    file_header_id    INTEGER REFERENCES file_header(id),
    event_order       INTEGER,
    raw               TEXT,
    team              TEXT,
    player_number     INTEGER,
    skill             TEXT,
    skill_type        TEXT,
    evaluation        TEXT,
    attack_code       TEXT,
    setter_code       TEXT,
    start_zone        TEXT,
    end_zone          TEXT,
    end_subzone       TEXT,
    special           TEXT,
    custom1           TEXT,
    custom2           TEXT,
    video_time        TEXT,
    set_number        INTEGER,
    -- IMPORTANT: these are rotation positions (1-6), NOT match scores
    -- Actual running scores are in point_visiting_score / point_home_score (parsed from *p/ap lines)
    home_rotation_pos   INTEGER,
    visiting_rotation_pos INTEGER,
    serving_team        INTEGER,
    video_frame         INTEGER,
    -- 12 individual jersey fields: home slots 1-6, visiting slots 1-6
    rotation_home_1     INTEGER,
    rotation_home_2     INTEGER,
    rotation_home_3     INTEGER,
    rotation_home_4     INTEGER,
    rotation_home_5     INTEGER,
    rotation_home_6     INTEGER,
    rotation_visiting_1 INTEGER,
    rotation_visiting_2 INTEGER,
    rotation_visiting_3 INTEGER,
    rotation_visiting_4 INTEGER,
    rotation_visiting_5 INTEGER,
    rotation_visiting_6 INTEGER,
    -- Parsed from *p/ap body: running score at time of point (visiting:home ordering)
    point_visiting_score INTEGER,
    point_home_score     INTEGER,
    -- Parsed from *z/az: new rotation position after rotation
    rotation_new_pos     INTEGER,
    -- Parsed from *c/ac: substitution jerseys
    sub_out_jersey       INTEGER,
    sub_in_jersey        INTEGER,
    -- Parsed from *P/aP: jersey of the server in lineup
    lineup_server_jersey INTEGER,
    is_set_start        INTEGER,
    is_rotation       INTEGER,
    is_point          INTEGER,
    is_substitution   INTEGER,
    is_timeout        INTEGER,
    is_point_consequence INTEGER,
    is_lineup         INTEGER
);
"""


# ── DVW → SQLite ──────────────────────────────────────────────────────────────

def dvw_to_db(dvw: DvwFile, db_path: str) -> int:
    """Insert one DvwFile into the database; return the new file_header_id."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(SCHEMA)
        cur = con.cursor()

        cur.execute("""
            INSERT INTO file_header
            (source_path,file_format,generator_day,generator_idp,
             generator_prg,generator_rel,generator_ver,generator_nam,
             lastchange_day,lastchange_idp,lastchange_prg,
             lastchange_rel,lastchange_ver,lastchange_nam)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            dvw.source_path,
            dvw.header.file_format, dvw.header.generator_day,
            dvw.header.generator_idp, dvw.header.generator_prg,
            dvw.header.generator_rel, dvw.header.generator_ver,
            dvw.header.generator_nam, dvw.header.lastchange_day,
            dvw.header.lastchange_idp, dvw.header.lastchange_prg,
            dvw.header.lastchange_rel, dvw.header.lastchange_ver,
            dvw.header.lastchange_nam,
        ))
        fhid = cur.lastrowid

        m = dvw.match
        cur.execute("""
            INSERT INTO match
            (file_header_id,date,time,season,league,phase,
             match_number,codepage,home_indicator,federation_match_id,
             field9,category_code,field11,
             encoded_league,encoded_phase,
             field_l2_0,field_l2_1,competition_code,
             field_l2_3,field_l2_4,field_l2_5,
             home_away,opponent_home_away,field_l2_8,scout_license_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            fhid, m.date, m.time, m.season, m.league, m.phase,
            m.match_number, m.codepage, m.home_indicator, m.federation_match_id,
            m.field9, m.category_code, m.field11,
            m.encoded_league, m.encoded_phase,
            m.field_l2_0, m.field_l2_1, m.competition_code,
            m.field_l2_3, m.field_l2_4, m.field_l2_5,
            m.home_away, m.opponent_home_away, m.field_l2_8, m.scout_license_id,
        ))

        mi = dvw.more
        cur.execute("""
            INSERT INTO more_info
            (file_header_id,city,venue,referee,internal_ids,duration1,duration2,
             field0,field1,field2,
             encoded_field6,encoded_city,encoded_field8,encoded_referee)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            fhid, mi.city, mi.venue, mi.referee, mi.internal_ids,
            mi.duration1, mi.duration2,
            mi.field0, mi.field1, mi.field2,
            mi.encoded_field6, mi.encoded_city, mi.encoded_field8, mi.encoded_referee,
        ))

        cur.execute("INSERT INTO comments (file_header_id,text) VALUES (?,?)",
                    (fhid, dvw.comments))

        for idx, t in enumerate(dvw.teams):
            cur.execute("""
                INSERT INTO team
                (file_header_id,team_index,team_id,team_name,sets_won,
                 coach,assistant_coach,team_color,
                 encoded_name,encoded_coach,encoded_asst_coach)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                fhid, idx, t.team_id, t.team_name, t.sets_won,
                t.coach, t.assistant_coach, t.team_color,
                t.encoded_name, t.encoded_coach, t.encoded_asst_coach,
            ))

        for s in dvw.sets:
            cur.execute("""
                INSERT INTO set_score
                (file_header_id,set_number,played,score_8,score_16,
                 score_21,final_score,duration)
                VALUES (?,?,?,?,?,?,?,?)""", (
                fhid, s.set_number,
                int(s.played) if s.played is not None else None,
                s.score_8, s.score_16, s.score_21, s.final_score, s.duration,
            ))

        for p in dvw.players:
            cur.execute("""
                INSERT INTO player
                (file_header_id,team_index,number,player_id,
                 starting_position_s1,starting_position_s2,starting_position_s3,
                 short_name,last_name,first_name,role,foreign_player,
                 field6,field7,field11,special_role,field15,field16,
                 encoded_short,encoded_last,encoded_first,
                 field20,field21,field22,field23)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                fhid, p.team_index, p.number, p.player_id,
                p.starting_position_s1, p.starting_position_s2, p.starting_position_s3,
                p.short_name, p.last_name, p.first_name, p.role,
                int(p.foreign) if p.foreign is not None else None,
                p.field6, p.field7, p.field11, p.special_role,
                p.field15, p.field16,
                p.encoded_short, p.encoded_last, p.encoded_first,
                p.field20, p.field21, p.field22, p.field23,
            ))

        for ac in dvw.attack_combinations:
            cur.execute("""
                INSERT INTO attack_combination
                (file_header_id,code,tempo,side,height,description,
                 color,position,attacker_position,field5,field9,field10)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                fhid, ac.code, ac.tempo, ac.side, ac.height, ac.description,
                ac.color, ac.position, ac.attacker_position,
                ac.field5, ac.field9, ac.field10,
            ))

        for sc in dvw.setter_calls:
            cur.execute("""
                INSERT INTO setter_call
                (file_header_id,code,description,color,
                 x1,y1,x2,area_list,highlight_color,field1,field3)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                fhid, sc.code, sc.description, sc.color,
                sc.x1, sc.y1, sc.x2, sc.area_list, sc.highlight_color,
                sc.field1, sc.field3,
            ))

        cur.execute("INSERT INTO winning_symbols (file_header_id,symbols) VALUES (?,?)",
                    (fhid, dvw.winning_symbols))

        for vf in dvw.video_files:
            cur.execute("""
                INSERT INTO video_file (file_header_id,camera_id,file_path)
                VALUES (?,?,?)""", (fhid, vf.camera_id, vf.file_path))

        for i, ev in enumerate(dvw.scout_events):
            cur.execute("""
                INSERT INTO scout_event
                (file_header_id,event_order,raw,
                 team,player_number,skill,skill_type,evaluation,
                 attack_code,setter_code,start_zone,end_zone,end_subzone,
                 special,custom1,custom2,video_time,
                 set_number,home_rotation_pos,visiting_rotation_pos,
                 serving_team,video_frame,
                 rotation_home_1,rotation_home_2,rotation_home_3,
                 rotation_home_4,rotation_home_5,rotation_home_6,
                 rotation_visiting_1,rotation_visiting_2,rotation_visiting_3,
                 rotation_visiting_4,rotation_visiting_5,rotation_visiting_6,
                 point_visiting_score,point_home_score,
                 rotation_new_pos,sub_out_jersey,sub_in_jersey,lineup_server_jersey,
                 is_set_start,is_rotation,is_point,is_substitution,
                 is_timeout,is_point_consequence,is_lineup)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                fhid, i, ev.raw,
                ev.team, ev.player_number, ev.skill, ev.skill_type, ev.evaluation,
                ev.attack_code, ev.setter_code, ev.start_zone, ev.end_zone,
                ev.end_subzone, ev.special, ev.custom1, ev.custom2, ev.video_time,
                ev.set_number, ev.home_rotation_pos, ev.visiting_rotation_pos,
                ev.serving_team, ev.video_frame,
                ev.rotation_home_1, ev.rotation_home_2, ev.rotation_home_3,
                ev.rotation_home_4, ev.rotation_home_5, ev.rotation_home_6,
                ev.rotation_visiting_1, ev.rotation_visiting_2, ev.rotation_visiting_3,
                ev.rotation_visiting_4, ev.rotation_visiting_5, ev.rotation_visiting_6,
                ev.point_visiting_score, ev.point_home_score,
                ev.rotation_new_pos, ev.sub_out_jersey, ev.sub_in_jersey,
                ev.lineup_server_jersey,
                int(ev.is_set_start), int(ev.is_rotation), int(ev.is_point),
                int(ev.is_substitution), int(ev.is_timeout),
                int(ev.is_point_consequence), int(ev.is_lineup),
            ))

        con.commit()
        return fhid
    finally:
        con.close()


# ── SQLite → DVW ──────────────────────────────────────────────────────────────

def db_to_dvw(db_path: str, output_dir: str, file_header_id: int | None = None) -> list[str]:
    """Reconstruct .dvw file(s) from the database; return list of written paths."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if file_header_id is not None:
            fhids = [file_header_id]
        else:
            fhids = [r[0] for r in con.execute(
                "SELECT id FROM file_header ORDER BY id").fetchall()]
        written = []
        for fhid in fhids:
            dvw = _load_from_db(con, fhid)
            written.append(_write_dvw(dvw, output_dir, fhid))
        return written
    finally:
        con.close()


def _load_from_db(con: sqlite3.Connection, fhid: int) -> DvwFile:
    """Reconstruct a DvwFile from a single file_header_id."""
    dvw = DvwFile()
    row = con.execute("SELECT * FROM file_header WHERE id=?", (fhid,)).fetchone()
    if not row:
        raise ValueError(f"file_header_id {fhid} not found")
    dvw.source_path = row["source_path"] or ""
    dvw.header = FileHeader(
        file_format=row["file_format"], generator_day=row["generator_day"],
        generator_idp=row["generator_idp"], generator_prg=row["generator_prg"],
        generator_rel=row["generator_rel"], generator_ver=row["generator_ver"],
        generator_nam=row["generator_nam"], lastchange_day=row["lastchange_day"],
        lastchange_idp=row["lastchange_idp"], lastchange_prg=row["lastchange_prg"],
        lastchange_rel=row["lastchange_rel"], lastchange_ver=row["lastchange_ver"],
        lastchange_nam=row["lastchange_nam"],
    )

    row = con.execute("SELECT * FROM match WHERE file_header_id=?", (fhid,)).fetchone()
    if row:
        dvw.match = MatchInfo(
            date=row["date"], time=row["time"], season=row["season"],
            league=row["league"], phase=row["phase"],
            match_number=row["match_number"], codepage=row["codepage"],
            home_indicator=row["home_indicator"],
            federation_match_id=row["federation_match_id"],
            field9=row["field9"], category_code=row["category_code"], field11=row["field11"],
            encoded_league=row["encoded_league"], encoded_phase=row["encoded_phase"],
            field_l2_0=row["field_l2_0"], field_l2_1=row["field_l2_1"],
            competition_code=row["competition_code"],
            field_l2_3=row["field_l2_3"], field_l2_4=row["field_l2_4"],
            field_l2_5=row["field_l2_5"],
            home_away=row["home_away"],
            opponent_home_away=row["opponent_home_away"],
            field_l2_8=row["field_l2_8"],
            scout_license_id=row["scout_license_id"],
        )

    row = con.execute("SELECT * FROM more_info WHERE file_header_id=?", (fhid,)).fetchone()
    if row:
        dvw.more = MoreInfo(
            city=row["city"], venue=row["venue"], referee=row["referee"],
            internal_ids=row["internal_ids"],
            duration1=row["duration1"], duration2=row["duration2"],
            field0=row["field0"], field1=row["field1"], field2=row["field2"],
            encoded_field6=row["encoded_field6"],
            encoded_city=row["encoded_city"], encoded_field8=row["encoded_field8"],
            encoded_referee=row["encoded_referee"],
        )

    row = con.execute("SELECT text FROM comments WHERE file_header_id=?", (fhid,)).fetchone()
    dvw.comments = row["text"] if row else ""

    for row in con.execute(
            "SELECT * FROM team WHERE file_header_id=? ORDER BY team_index", (fhid,)):
        dvw.teams.append(Team(
            team_id=row["team_id"], team_name=row["team_name"],
            sets_won=row["sets_won"], coach=row["coach"],
            assistant_coach=row["assistant_coach"], team_color=row["team_color"],
            encoded_name=row["encoded_name"], encoded_coach=row["encoded_coach"],
            encoded_asst_coach=row["encoded_asst_coach"],
        ))

    for row in con.execute(
            "SELECT * FROM set_score WHERE file_header_id=? ORDER BY set_number", (fhid,)):
        dvw.sets.append(SetScore(
            set_number=row["set_number"],
            played=bool(row["played"]) if row["played"] is not None else None,
            score_8=row["score_8"], score_16=row["score_16"],
            score_21=row["score_21"], final_score=row["final_score"],
            duration=row["duration"],
        ))

    for row in con.execute(
            "SELECT * FROM player WHERE file_header_id=? ORDER BY team_index,player_id",
            (fhid,)):
        dvw.players.append(Player(
            team_index=row["team_index"], number=row["number"],
            player_id=row["player_id"],
            starting_position_s1=row["starting_position_s1"],
            starting_position_s2=row["starting_position_s2"],
            starting_position_s3=row["starting_position_s3"],
            short_name=row["short_name"], last_name=row["last_name"],
            first_name=row["first_name"], role=row["role"],
            foreign=bool(row["foreign_player"]) if row["foreign_player"] is not None else None,
            field6=row["field6"], field7=row["field7"],
            field11=row["field11"], special_role=row["special_role"],
            field15=row["field15"], field16=row["field16"],
            encoded_short=row["encoded_short"],
            encoded_last=row["encoded_last"], encoded_first=row["encoded_first"],
            field20=row["field20"], field21=row["field21"],
            field22=row["field22"], field23=row["field23"],
        ))

    for row in con.execute(
            "SELECT * FROM attack_combination WHERE file_header_id=?", (fhid,)):
        dvw.attack_combinations.append(AttackCombination(
            code=row["code"], tempo=row["tempo"], side=row["side"],
            height=row["height"], description=row["description"],
            color=row["color"], position=row["position"],
            attacker_position=row["attacker_position"],
            field5=row["field5"], field9=row["field9"], field10=row["field10"],
        ))

    for row in con.execute("SELECT * FROM setter_call WHERE file_header_id=?", (fhid,)):
        dvw.setter_calls.append(SetterCall(
            code=row["code"], description=row["description"], color=row["color"],
            x1=row["x1"], y1=row["y1"], x2=row["x2"],
            area_list=row["area_list"], highlight_color=row["highlight_color"],
            field1=row["field1"], field3=row["field3"],
        ))

    row = con.execute(
        "SELECT symbols FROM winning_symbols WHERE file_header_id=?", (fhid,)).fetchone()
    dvw.winning_symbols = row["symbols"] if row else ""

    for row in con.execute("SELECT * FROM video_file WHERE file_header_id=?", (fhid,)):
        dvw.video_files.append(VideoFile(camera_id=row["camera_id"], file_path=row["file_path"]))

    for row in con.execute(
            "SELECT * FROM scout_event WHERE file_header_id=? ORDER BY event_order", (fhid,)):
        dvw.scout_events.append(ScoutEvent(
            raw=row["raw"] or "",
            team=row["team"], player_number=row["player_number"],
            skill=row["skill"], skill_type=row["skill_type"],
            evaluation=row["evaluation"], attack_code=row["attack_code"],
            setter_code=row["setter_code"], start_zone=row["start_zone"],
            end_zone=row["end_zone"], end_subzone=row["end_subzone"],
            special=row["special"], custom1=row["custom1"], custom2=row["custom2"],
            video_time=row["video_time"], set_number=row["set_number"],
            home_rotation_pos=row["home_rotation_pos"],
            visiting_rotation_pos=row["visiting_rotation_pos"],
            serving_team=row["serving_team"], video_frame=row["video_frame"],
            rotation_home_1=row["rotation_home_1"], rotation_home_2=row["rotation_home_2"],
            rotation_home_3=row["rotation_home_3"], rotation_home_4=row["rotation_home_4"],
            rotation_home_5=row["rotation_home_5"], rotation_home_6=row["rotation_home_6"],
            rotation_visiting_1=row["rotation_visiting_1"],
            rotation_visiting_2=row["rotation_visiting_2"],
            rotation_visiting_3=row["rotation_visiting_3"],
            rotation_visiting_4=row["rotation_visiting_4"],
            rotation_visiting_5=row["rotation_visiting_5"],
            rotation_visiting_6=row["rotation_visiting_6"],
            point_visiting_score=row["point_visiting_score"],
            point_home_score=row["point_home_score"],
            rotation_new_pos=row["rotation_new_pos"],
            sub_out_jersey=row["sub_out_jersey"], sub_in_jersey=row["sub_in_jersey"],
            lineup_server_jersey=row["lineup_server_jersey"],
            is_set_start=bool(row["is_set_start"]),
            is_rotation=bool(row["is_rotation"]),
            is_point=bool(row["is_point"]),
            is_substitution=bool(row["is_substitution"]),
            is_timeout=bool(row["is_timeout"]),
            is_point_consequence=bool(row["is_point_consequence"]),
            is_lineup=bool(row["is_lineup"]),
        ))

    return dvw


# ── serialiser ────────────────────────────────────────────────────────────────

def _v(val) -> str:
    """Format a value for DVW output (None → empty string)."""
    return "" if val is None else str(val)


def _join(fields: list, trailing_semi: bool = True, min_fields: int = 0) -> str:
    """Join fields with semicolons, stripping trailing None/empty fields first.

    Preserves the original file's field count: lines end at the last non-empty
    field (plus one trailing semicolon). min_fields ensures structural empty
    fields that the format always writes are not trimmed away even when None.

    Args:
        fields:        Values to join (None → "").
        trailing_semi: Append a final ";" after the last field.
        min_fields:    Always emit at least this many fields, padding with ""
                       when the last non-empty value falls short.
    """
    last = max(
        (i for i, f in enumerate(fields) if f is not None and str(f) != ""),
        default=-1,
    )
    last = max(last, min_fields - 1)
    trimmed = [_v(f) for f in fields[:last + 1]]
    result = ";".join(trimmed)
    if trailing_semi:
        result += ";"
    return result


def _player_line(p: Player) -> str:
    return _join([
        p.team_index, p.number, p.player_id,
        p.starting_position_s1, p.starting_position_s2,
        p.starting_position_s3, p.field6, p.field7,
        p.short_name, p.last_name, p.first_name,
        p.field11, p.special_role, p.role,
        "False" if not p.foreign else "True",
        p.field15, p.field16,
        p.encoded_short, p.encoded_last, p.encoded_first,
        p.field20, p.field21, p.field22, p.field23,
    ], min_fields=17)


def _write_dvw(dvw: DvwFile, output_dir: str, fhid: int) -> str:
    """Serialise DvwFile back to .dvw text; return written path."""
    lines: list[str] = []
    L = lines.append

    h = dvw.header
    L("[3DATAVOLLEYSCOUT]")
    # Only emit key-value lines that were present in the original file
    for key, val in [
        ("FILEFORMAT",     h.file_format),
        ("GENERATOR-DAY",  h.generator_day),
        ("GENERATOR-IDP",  h.generator_idp),
        ("GENERATOR-PRG",  h.generator_prg),
        ("GENERATOR-REL",  h.generator_rel),
        ("GENERATOR-VER",  h.generator_ver),
        ("GENERATOR-NAM",  h.generator_nam),
        ("LASTCHANGE-DAY", h.lastchange_day),
        ("LASTCHANGE-IDP", h.lastchange_idp),
        ("LASTCHANGE-PRG", h.lastchange_prg),
        ("LASTCHANGE-REL", h.lastchange_rel),
        ("LASTCHANGE-VER", h.lastchange_ver),
        ("LASTCHANGE-NAM", h.lastchange_nam),
    ]:
        if val is not None:
            L(f"{key}: {val}")

    m = dvw.match
    L("[3MATCH]")
    L(_join([m.date,m.time,m.season,m.league,m.phase,
             m.home_indicator,m.match_number,m.federation_match_id,
             m.codepage,m.field9,m.category_code,m.field11,
             m.encoded_league,m.encoded_phase]))
    L(_join([m.field_l2_0,m.field_l2_1,m.competition_code,
             m.field_l2_3,m.field_l2_4,m.field_l2_5,
             m.home_away,m.opponent_home_away,m.field_l2_8,
             m.scout_license_id], min_fields=6))

    L("[3TEAMS]")
    for t in dvw.teams:
        L(_join([t.team_id,t.team_name,t.sets_won,
                 t.coach,t.assistant_coach,t.team_color,
                 t.encoded_name,t.encoded_coach,t.encoded_asst_coach]))

    mi = dvw.more
    L("[3MORE]")
    L(_join([mi.field0,mi.field1,mi.field2,mi.city,
             mi.venue,mi.referee,mi.encoded_field6,
             mi.encoded_city,mi.encoded_field8,mi.encoded_referee], min_fields=6))
    L(_join([mi.internal_ids,mi.duration1,mi.duration2]))

    L("[3COMMENTS]")
    L(dvw.comments or "no comments")

    L("[3SET]")
    for s in dvw.sets:
        L(";".join([_v(s.played) if s.played is not None else "True",
                    _v(s.score_8),_v(s.score_16),_v(s.score_21),
                    _v(s.final_score),_v(s.duration),"",]))

    L("[3PLAYERS-H]")
    for p in [x for x in dvw.players if x.team_index == 0]:
        L(_player_line(p))

    L("[3PLAYERS-V]")
    for p in [x for x in dvw.players if x.team_index == 1]:
        L(_player_line(p))

    L("[3ATTACKCOMBINATION]")
    for ac in dvw.attack_combinations:
        L(";".join([_v(ac.code),_v(ac.tempo),_v(ac.side),_v(ac.height),
                    _v(ac.description),_v(ac.field5),_v(ac.color),
                    _v(ac.position),_v(ac.attacker_position),
                    _v(ac.field9),_v(ac.field10),"",]))

    L("[3SETTERCALL]")
    for sc in dvw.setter_calls:
        L(";".join([_v(sc.code),_v(sc.field1),_v(sc.description),_v(sc.field3),
                    _v(sc.color),_v(sc.x1),_v(sc.y1),_v(sc.x2),
                    _v(sc.area_list),_v(sc.highlight_color),"",]))

    L("[3WINNINGSYMBOLS]")
    if dvw.winning_symbols:
        L(dvw.winning_symbols)

    L("[3RESERVE]")

    L("[3VIDEO]")
    for vf in dvw.video_files:
        L(f"Camera{_v(vf.camera_id)}={_v(vf.file_path)}")

    L("[3SCOUT]")
    for ev in dvw.scout_events:
        L(ev.raw)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(dvw.source_path).stem if dvw.source_path else f"match_{fhid}"
    out_path = str(out_dir / f"{stem}.dvw")

    with open(out_path, "wb") as fh:
        fh.write(("\r\n".join(lines) + "\r\n").encode(ENCODING, errors="replace"))
    return out_path
