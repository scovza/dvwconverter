"""Parse DataVolley .dvw scouting files (format 2.0, Windows-1252)."""

import re
from dataclasses import dataclass, field
from typing import Optional

ENCODING = "windows-1252"


# ── helpers ───────────────────────────────────────────────────────────────────

def _split(line: str) -> list[str]:
    return line.rstrip("\r\n").split(";")


def _str(v: str) -> Optional[str]:
    return v.strip() or None


def _int(v: str) -> Optional[int]:
    try:
        return int(v.strip())
    except (ValueError, AttributeError):
        return None


def _bool(v: str) -> Optional[bool]:
    v = v.strip().lower()
    return True if v == "true" else (False if v == "false" else None)


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class FileHeader:
    """Generator metadata from [3DATAVOLLEYSCOUT]."""
    file_format: Optional[str] = None
    generator_day: Optional[str] = None
    generator_idp: Optional[str] = None
    generator_prg: Optional[str] = None
    generator_rel: Optional[str] = None
    generator_ver: Optional[str] = None
    generator_nam: Optional[str] = None
    lastchange_day: Optional[str] = None
    lastchange_idp: Optional[str] = None
    lastchange_prg: Optional[str] = None
    lastchange_rel: Optional[str] = None
    lastchange_ver: Optional[str] = None
    lastchange_nam: Optional[str] = None


@dataclass
class MatchInfo:
    """Match header from [3MATCH] (two semicolon-delimited lines).

    Line 1 fields (index 0-13):
      0  date, 1 time, 2 season, 3 league, 4 phase,
      5  home_indicator  ("Interno"=home, "Esterno"=away; empty=unset),
      6  match_number,
      7  federation_match_id  (numeric ID from the federation/DV platform),
      8  codepage,
      9  field9  (constant "1" across observed files; meaning unknown),
      10 category_code  (constant "Z" across observed files; competition type),
      11 field11  (constant "0"; unknown boolean flag),
      12 encoded_league  (\x0f2+hex duplicate of league field),
      13 encoded_phase   (\x0f2+hex duplicate of phase field)

    Line 2 fields (index 0-9):
      0  field_l2_0, 1 field_l2_1,
      2  competition_code  (e.g. "46137"; league/competition registration ID –
                            NOT a venue code; identical across all files in the
                            same competition),
      3  field_l2_3, 4 field_l2_4, 5 field_l2_5,
      6  home_away  ("L"=locale/home, "R"=remote/visiting; perspective team),
      7  opponent_home_away  ("L"/"R"; mirror of home_away for the opponent),
      8  field_l2_8,
      9  scout_license_id  (numeric DV software license / operator ID)
    """
    date: Optional[str] = None
    time: Optional[str] = None
    season: Optional[str] = None
    league: Optional[str] = None
    phase: Optional[str] = None
    # line1[5]: "Interno"=home venue, "Esterno"=away, empty=not specified
    home_indicator: Optional[str] = None
    match_number: Optional[int] = None
    # line1[7]: federation or DataVolley platform match ID
    federation_match_id: Optional[int] = None
    codepage: Optional[int] = None
    # line1[9]: constant "1" in all observed files; meaning unknown
    field9: Optional[str] = None
    # line1[10]: constant "Z" in all observed files; competition/category code
    category_code: Optional[str] = None
    # line1[11]: constant "0" in all observed files; unknown flag
    field11: Optional[str] = None
    encoded_league: Optional[str] = None
    encoded_phase: Optional[str] = None
    field_l2_0: Optional[str] = None
    field_l2_1: Optional[str] = None
    # line2[2]: competition/league registration code (was incorrectly named venue_code)
    competition_code: Optional[str] = None
    field_l2_3: Optional[str] = None
    field_l2_4: Optional[str] = None
    field_l2_5: Optional[str] = None
    # line2[6]: "L"=perspective team is home, "R"=perspective team is visiting
    home_away: Optional[str] = None
    # line2[7]: home/away status of the *opponent* team (mirror of home_away)
    opponent_home_away: Optional[str] = None
    field_l2_8: Optional[str] = None
    # line2[9]: numeric DataVolley license/operator ID for the scout who created the file
    scout_license_id: Optional[int] = None
    # Raw source lines — used verbatim on write-back to preserve exact field count
    _raw_line1: Optional[str] = None
    _raw_line2: Optional[str] = None


@dataclass
class Team:
    """Single team record from [3TEAMS]."""
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    sets_won: Optional[int] = None
    coach: Optional[str] = None
    assistant_coach: Optional[str] = None
    team_color: Optional[int] = None    # decimal BGR colour
    encoded_name: Optional[str] = None
    encoded_coach: Optional[str] = None
    encoded_asst_coach: Optional[str] = None


@dataclass
class MoreInfo:
    """Venue/referee data from [3MORE]."""
    field0: Optional[str] = None
    field1: Optional[str] = None
    field2: Optional[str] = None
    city: Optional[str] = None
    venue: Optional[str] = None         # field[4]: venue/arena name
    referee: Optional[str] = None
    encoded_field6: Optional[str] = None
    encoded_city: Optional[str] = None
    encoded_field8: Optional[str] = None
    encoded_referee: Optional[str] = None
    # line2[0]: space-separated DataVolley platform record IDs (observed in one file only)
    internal_ids: Optional[str] = None
    # line2[1-2]: suspected timing data (warm-up / break duration?); semantics unresolved
    duration1: Optional[int] = None
    duration2: Optional[int] = None


@dataclass
class SetScore:
    """Score snapshots for one set from [3SET].

    All score fields are in visiting-first order: "visiting-home"
    (e.g. "25-21" means visiting scored 25, home scored 21).
    This is the *opposite* of the [3TEAMS] ordering where the home
    team is listed first.
    """
    set_number: int = 0
    played: Optional[bool] = None
    # scores are "visiting_score-home_score" (visiting team first)
    score_8: Optional[str] = None
    score_16: Optional[str] = None
    score_21: Optional[str] = None
    final_score: Optional[str] = None
    duration: Optional[int] = None
    _raw: Optional[str] = None  # original source line for verbatim write-back


@dataclass
class Player:
    """Player roster entry from [3PLAYERS-H] or [3PLAYERS-V].

    field[12] (special_role):
      "L" = Libero (team's designated libero)
      "C" = Captain (one per team; orthogonal to role)
      ""  = Standard player (no special designation)

    field[13] (role):
      1=Libero, 2=Outside Hitter, 3=Middle Blocker,
      4=Opposite Hitter, 5=Setter

    fields[17-19] (\x0f2+hex encoded duplicates; redundant with plaintext):
      field[17] = encoded short_name
      field[18] = encoded last_name   (was encoded_last at index 18)
      field[19] = encoded first_name  (was encoded_first at index 19)
    """
    team_index: int = 0             # 0=home, 1=visiting
    number: Optional[int] = None
    player_id: int = 0              # sequential across both rosters
    starting_position_s1: Optional[str] = None
    starting_position_s2: Optional[str] = None
    starting_position_s3: Optional[str] = None
    # Confirmed: starting rotation position for set 4 (empty for 3-set matches)
    starting_position_s4: Optional[str] = None
    # Confirmed: starting rotation position for set 5 (empty for matches < 5 sets)
    starting_position_s5: Optional[str] = None
    short_name: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    field11: Optional[str] = None
    # "L"=Libero, "C"=Captain, ""=standard player
    special_role: Optional[str] = None
    role: Optional[int] = None      # 1=libero 2=OH 3=MB 4=opp 5=setter
    foreign: Optional[bool] = None
    field15: Optional[str] = None
    field16: Optional[str] = None
    # fields[17-19]: \x0f2+hex encoded duplicates of short_name/last/first
    encoded_short: Optional[str] = None
    encoded_last: Optional[str] = None
    encoded_first: Optional[str] = None
    field20: Optional[str] = None
    field21: Optional[str] = None
    field22: Optional[str] = None
    field23: Optional[str] = None
    _raw: Optional[str] = None  # original source line for verbatim write-back


@dataclass
class AttackCombination:
    """Attack play-code definition from [3ATTACKCOMBINATION]."""
    code: Optional[str] = None          # 2-char code e.g. "X1"
    tempo: Optional[int] = None         # 2=quick 3=half 4=high 7=back-C 8=back 9=back-set
    side: Optional[str] = None          # L R C
    height: Optional[str] = None        # Q M T H O U
    description: Optional[str] = None
    field5: Optional[str] = None
    color: Optional[int] = None
    # packed court position: YYXX where YY=depth (34=baseline…50=net),
    # XX=lateral (12=zone4/5 left … 50=center … 88=zone1/2 right)
    position: Optional[int] = None
    attacker_position: Optional[str] = None  # F=front-row, B=back-row, C S P -
    # Confirmed: True when this is a back-row attack (tempo 7/8/9, position P/F/B)
    is_back_row_attack: Optional[bool] = None
    field10: Optional[str] = None
    _raw: Optional[str] = None  # original source line for verbatim write-back


@dataclass
class SetterCall:
    """Setter call code definition from [3SETTERCALL]."""
    code: Optional[str] = None
    field1: Optional[str] = None
    description: Optional[str] = None
    field3: Optional[str] = None
    color: Optional[int] = None
    # coordinate fields share the same YYXX encoding as AttackCombination.position
    x1: Optional[str] = None           # setter's position on canvas (raw string, e.g. '0000')
    y1: Optional[str] = None           # apex/midpoint of the set-arc ball trajectory
    x2: Optional[str] = None           # attack target position
    area_list: Optional[str] = None    # comma-separated area codes
    highlight_color: Optional[int] = None
    _raw: Optional[str] = None  # original source line for verbatim write-back


@dataclass
class VideoFile:
    """Linked video file from [3VIDEO]."""
    camera_id: Optional[int] = None
    file_path: Optional[str] = None


@dataclass
class ScoutEvent:
    """
    Single play-by-play event from [3SCOUT].

    Regular skill line format:
        [*|a]<nn><skill>[type][eval][attack|setter][~zone~target[subzone]]
        ;[point_phase];[attack_cone];;;;;;[video_time];[set];[home_rot_pos];[visiting_rot_pos];[serving];[frame];;[rot_h1..6];[rot_v1..6];

    Prefix: * = visiting team, a = home team.
    Special prefixes: **Nset=set boundary, *z/az=rotation, *p/ap=point,
                      ac/*c=substitution, aT/*T=timeout,
                      $$&/$$D/$$F=rally outcome, *P/aP=lineup declaration.

    IMPORTANT – tail fields 9 and 10 (home_rotation_pos / visiting_rotation_pos):
        These store the current *rotation position* (1–6) of each team,
        NOT the match score. Actual running scores are found in the body
        of *p / ap point lines as "visiting_score:home_score".

    Rotation tail fields 14–25 are 12 individual jersey-number fields:
        positions 14–19 = home team rotation slots 1–6
        positions 20–25 = visiting team rotation slots 1–6

    Set scores in [3SET] and point-line bodies use visiting-first ordering.

    Special-line formats:
        *z3 / az3        — rotation: team rotated to position 3
        *p15:12 / ap…    — point scored; body = "visiting:home" running score
                           (*=visiting scored, a=home scored)
        *c12:17 / ac…    — substitution: jersey 12 out, jersey 17 in
        *P18>LUp / aP…   — lineup declaration at set start (jersey=server)
        a$$&H# / *$$&H=  — rally outcome (hard attack): H=hard, #=kill, ==opponent error
        a$$DH# / *$$DH!  — rally outcome (block/dig consequence)
        a$$FH#           — rally outcome (freeball consequence)
    """
    raw: str = ""

    team: Optional[str] = None          # H or V
    player_number: Optional[int] = None
    skill: Optional[str] = None         # S R E A B D F T O
    skill_type: Optional[str] = None
    evaluation: Optional[str] = None    # + # - / ! =
    attack_code: Optional[str] = None
    setter_code: Optional[str] = None
    start_zone: Optional[str] = None
    end_zone: Optional[str] = None
    # 2–3 char directional suffix after end zone: RC, RS, LC, SC, SS, NRC, NRS, IRS, …
    end_subzone: Optional[str] = None
    # Confirmed: "p"=action won the point (kill/ace/block/error), "s"=in-rally action, empty=non-skill line
    point_phase: Optional[str] = None
    # Confirmed: attack direction cone, Attack events only — "r"=cross/right, "s"=straight/line, "p"=pipe/back-center
    attack_cone: Optional[str] = None
    video_time: Optional[str] = None
    set_number: Optional[int] = None
    # tail[9]: home team current rotation position (1–6), NOT match score
    home_rotation_pos: Optional[int] = None
    # tail[10]: visiting team current rotation position (1–6), NOT match score
    visiting_rotation_pos: Optional[int] = None
    serving_team: Optional[int] = None  # 1=home, 0=visiting
    video_frame: Optional[int] = None
    # Individual rotation jersey fields (tail positions 14–19 and 20–25)
    rotation_home_1: Optional[int] = None
    rotation_home_2: Optional[int] = None
    rotation_home_3: Optional[int] = None
    rotation_home_4: Optional[int] = None
    rotation_home_5: Optional[int] = None
    rotation_home_6: Optional[int] = None
    rotation_visiting_1: Optional[int] = None
    rotation_visiting_2: Optional[int] = None
    rotation_visiting_3: Optional[int] = None
    rotation_visiting_4: Optional[int] = None
    rotation_visiting_5: Optional[int] = None
    rotation_visiting_6: Optional[int] = None

    is_set_start: bool = False
    is_rotation: bool = False
    is_point: bool = False
    is_substitution: bool = False
    is_timeout: bool = False
    is_point_consequence: bool = False
    is_lineup: bool = False

    # Parsed fields for special event types
    # For is_point=True: running score extracted from body (*p / ap lines)
    point_visiting_score: Optional[int] = None
    point_home_score: Optional[int] = None
    # For is_rotation=True: new rotation position
    rotation_new_pos: Optional[int] = None
    # For is_substitution=True: players in/out
    sub_out_jersey: Optional[int] = None
    sub_in_jersey: Optional[int] = None
    # For is_lineup=True: jersey number of the server
    lineup_server_jersey: Optional[int] = None


@dataclass
class DvwFile:
    """Root container for all sections of a parsed .dvw file."""
    source_path: str = ""
    header: FileHeader = field(default_factory=FileHeader)
    match: MatchInfo = field(default_factory=MatchInfo)
    teams: list[Team] = field(default_factory=list)
    more: MoreInfo = field(default_factory=MoreInfo)
    comments: str = ""
    # Per-set comments (up to 5); semicolon-separated in the source file
    set_comments: list[str] = field(default_factory=list)
    sets: list[SetScore] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    attack_combinations: list[AttackCombination] = field(default_factory=list)
    setter_calls: list[SetterCall] = field(default_factory=list)
    winning_symbols: str = ""
    video_files: list[VideoFile] = field(default_factory=list)
    scout_events: list[ScoutEvent] = field(default_factory=list)


# ── section parsers ───────────────────────────────────────────────────────────

def _parse_header(lines: list[str]) -> FileHeader:
    # Map the literal key names in the file to FileHeader field names.
    # Most follow WORD-WORD → word_word via hyphen→underscore, but
    # FILEFORMAT has no hyphen so it needs an explicit alias.
    _ALIASES = {"fileformat": "file_format"}
    h = FileHeader()
    for line in lines:
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower().replace("-", "_")
            key = _ALIASES.get(key, key)
            val = val.strip()
            if hasattr(h, key):
                setattr(h, key, val or None)
    return h


def _parse_match(lines: list[str]) -> MatchInfo:
    m = MatchInfo()
    m._raw_line1 = lines[0].rstrip('\r\n') if lines else None
    m._raw_line2 = lines[1].rstrip('\r\n') if len(lines) >= 2 else None
    if lines:
        p = _split(lines[0])
        fields_l1 = [
            "date", "time", "season", "league", "phase",
            "home_indicator",       # "Interno"=home, "Esterno"=away
            "match_number",
            "federation_match_id",  # numeric federation/DV platform match ID
            "codepage",
            "field9",               # constant "1"; meaning unknown
            "category_code",        # constant "Z"; competition/category code
            "field11",              # constant "0"; unknown flag
            "encoded_league",
            "encoded_phase",
        ]
        int_fields = {"match_number", "federation_match_id", "codepage"}
        for i, name in enumerate(fields_l1):
            if i < len(p):
                val = _int(p[i]) if name in int_fields else _str(p[i])
                setattr(m, name, val)
    if len(lines) >= 2:
        p = _split(lines[1])
        fields_l2 = [
            "field_l2_0", "field_l2_1",
            "competition_code",     # league/competition registration code (was venue_code)
            "field_l2_3", "field_l2_4", "field_l2_5",
            "home_away",            # "L"=perspective team is home, "R"=visiting
            "opponent_home_away",   # mirror of home_away for the opponent
            "field_l2_8",
            "scout_license_id",     # numeric DV license/operator ID
        ]
        for i, name in enumerate(fields_l2):
            if i < len(p):
                if name == "scout_license_id":
                    setattr(m, name, _int(p[i]))
                else:
                    setattr(m, name, _str(p[i]))
    return m


def _parse_team(line: str) -> Team:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return Team(
        team_id=g(0), team_name=g(1), sets_won=g(2, _int),
        coach=g(3), assistant_coach=g(4), team_color=g(5, _int),
        encoded_name=g(6), encoded_coach=g(7), encoded_asst_coach=g(8),
    )


def _parse_more(lines: list[str]) -> MoreInfo:
    m = MoreInfo()
    if lines:
        p = _split(lines[0])
        names = [
            "field0", "field1", "field2", "city",
            "venue",            # field[4]: venue/arena name
            "referee",
            "encoded_field6", "encoded_city", "encoded_field8", "encoded_referee",
        ]
        for i, name in enumerate(names):
            if i < len(p):
                # field0 may be a bare space (' ') used as a placeholder —
                # preserve it as-is so the round-trip reconstructs the same line.
                val = p[i] if name == "field0" else _str(p[i])
                setattr(m, name, val if val != "" else None)
    if len(lines) >= 2:
        p = _split(lines[1])
        # field[0]: space-separated DataVolley platform record IDs (optional)
        m.internal_ids = _str(p[0]) if len(p) > 0 else None
        m.duration1 = _int(p[1]) if len(p) > 1 else None
        m.duration2 = _int(p[2]) if len(p) > 2 else None
    return m


def _parse_sets(lines: list[str]) -> list[SetScore]:
    result = []
    for i, line in enumerate(lines[:5]):
        p = _split(line)
        result.append(SetScore(
            set_number=i + 1,
            played=_bool(p[0]) if p else None,
            # All score fields are "visiting_score-home_score" (visiting first)
            score_8=_str(p[1]) if len(p) > 1 else None,
            score_16=_str(p[2]) if len(p) > 2 else None,
            score_21=_str(p[3]) if len(p) > 3 else None,
            final_score=_str(p[4]) if len(p) > 4 else None,
            duration=_int(p[5]) if len(p) > 5 else None,
            _raw=line.rstrip('\r\n'),
        ))
    return result


def _parse_comments(text: str) -> tuple[str, list[str]]:
    """Parse [3COMMENTS] content.

    Returns (raw_text, per_set_comments).  When the file stores
    per-set comments the raw text contains semicolon-separated entries
    (one per set played).  An empty entry or the literal "no comments"
    means no comment was recorded for that set.
    """
    raw = text.strip()
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        set_comments = [p for p in parts if p.lower() != "no comments"]
    else:
        set_comments = []
    return raw, set_comments


def _parse_player(line: str, team_index: int) -> Player:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return Player(
        team_index=team_index,
        number=g(1, _int), player_id=g(2, _int) or 0,
        starting_position_s1=g(3), starting_position_s2=g(4),
        starting_position_s3=g(5), starting_position_s4=g(6), starting_position_s5=g(7),
        short_name=g(8), last_name=g(9), first_name=g(10),
        field11=g(11),
        # field[12]: "L"=Libero, "C"=Captain, ""=standard player
        special_role=g(12),
        role=g(13, _int),
        foreign=g(14, _bool),
        field15=g(15), field16=g(16),
        # field[17]: encoded short_name (\x0f2+hex)
        encoded_short=g(17),
        # field[18]: encoded last_name (\x0f2+hex)
        encoded_last=g(18),
        # field[19]: encoded first_name (\x0f2+hex)
        encoded_first=g(19),
        field20=g(20), field21=g(21), field22=g(22), field23=g(23),
        _raw=line.rstrip('\r\n'),
    )


def _parse_attack_combination(line: str) -> AttackCombination:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return AttackCombination(
        code=g(0), tempo=g(1, _int), side=g(2), height=g(3),
        description=g(4), field5=g(5), color=g(6, _int),
        position=g(7, _int), attacker_position=g(8),
        is_back_row_attack=(g(9) == "1") if g(9) is not None else None,
        field10=g(10),
        _raw=line.rstrip('\r\n'),
    )


def _parse_setter_call(line: str) -> SetterCall:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return SetterCall(
        code=g(0), field1=g(1), description=g(2), field3=g(3),
        color=g(4, _int), x1=g(5), y1=g(6), x2=g(7),  # preserve '0000' etc. as strings
        area_list=g(8), highlight_color=g(9, _int),
        _raw=line.rstrip('\r\n'),
    )


def _parse_video(lines: list[str]) -> list[VideoFile]:
    result = []
    for line in lines:
        if "=" in line:
            key, _, val = line.partition("=")
            m = re.match(r"Camera(\d+)", key.strip())
            result.append(VideoFile(
                camera_id=int(m.group(1)) if m else None,
                file_path=val.strip() or None,
            ))
    return result


def _parse_scout_event(line: str) -> ScoutEvent:  # noqa: C901
    """Decode one scout line into a ScoutEvent; raw line always preserved."""
    ev = ScoutEvent(raw=line.rstrip("\r\n"))
    raw = ev.raw

    # set boundary marker e.g. "**2set"
    if raw.startswith("**") and "set" in raw.lower():
        ev.is_set_start = True
        p = raw.split(";")
        if len(p) >= 11:
            ev.set_number = _int(p[8])
            # tail[9] and [10] = rotation positions, not scores
            ev.home_rotation_pos = _int(p[9])
            ev.visiting_rotation_pos = _int(p[10])
        return ev

    parts = raw.split(";")
    if len(parts) >= 16:
        ev.point_phase = _str(parts[1])
        ev.attack_cone = _str(parts[2])
        ev.video_time = _str(parts[7])
        ev.set_number = _int(parts[8])
        # tail[9] = home rotation position (1–6), NOT the score
        ev.home_rotation_pos = _int(parts[9])
        # tail[10] = visiting rotation position (1–6), NOT the score
        ev.visiting_rotation_pos = _int(parts[10])
        ev.serving_team = _int(parts[11])
        ev.video_frame = _int(parts[12])
        # tail[13] is always empty (structural separator); skip it
        # tail[14-19] = home rotation jerseys (6 individual fields)
        if len(parts) > 14:
            ev.rotation_home_1 = _int(parts[14])
        if len(parts) > 15:
            ev.rotation_home_2 = _int(parts[15])
        if len(parts) > 16:
            ev.rotation_home_3 = _int(parts[16])
        if len(parts) > 17:
            ev.rotation_home_4 = _int(parts[17])
        if len(parts) > 18:
            ev.rotation_home_5 = _int(parts[18])
        if len(parts) > 19:
            ev.rotation_home_6 = _int(parts[19])
        # tail[20-25] = visiting rotation jerseys (6 individual fields)
        if len(parts) > 20:
            ev.rotation_visiting_1 = _int(parts[20])
        if len(parts) > 21:
            ev.rotation_visiting_2 = _int(parts[21])
        if len(parts) > 22:
            ev.rotation_visiting_3 = _int(parts[22])
        if len(parts) > 23:
            ev.rotation_visiting_4 = _int(parts[23])
        if len(parts) > 24:
            ev.rotation_visiting_5 = _int(parts[24])
        if len(parts) > 25:
            ev.rotation_visiting_6 = _int(parts[25])

    body = parts[0] if parts else raw

    # rotation: *z3 or az3 — team rotated to position N
    if body.startswith(("*z", "az")):
        ev.is_rotation = True
        ev.team = "V" if body[0] == "*" else "H"
        ev.rotation_new_pos = _int(body[2:])
        return ev

    # point: *p or ap — score in body as "visiting:home"
    # *=visiting scored, a=home scored
    if body.startswith(("*p", "ap")):
        ev.is_point = True
        ev.team = "V" if body[0] == "*" else "H"
        score_str = body[2:]
        m = re.match(r"(\d+):(\d+)", score_str)
        if m:
            ev.point_visiting_score = int(m.group(1))
            ev.point_home_score = int(m.group(2))
        return ev

    # substitution: *c12:17 or ac12:17 — jersey out:in
    if body.startswith(("ac", "*c")):
        ev.is_substitution = True
        ev.team = "V" if body[0] == "*" else "H"
        m = re.match(r"[a*]c(\d+):(\d+)", body)
        if m:
            ev.sub_out_jersey = int(m.group(1))
            ev.sub_in_jersey = int(m.group(2))
        return ev

    # timeout
    if body in ("aT", "*T"):
        ev.is_timeout = True
        ev.team = "V" if body[0] == "*" else "H"
        return ev

    # rally outcome: a$$&H# / *$$&H= (hard attack), a$$DH# (block/dig consequence), a$$FH# (freeball consequence)
    # Second char: & = hard attack end, D = block/dig, F = freeball exchange
    # Third char: H = Hard attack skill; fourth char: #=kill, ==error, !=excellent, /=slash
    if "$$" in body and len(body) >= 5 and body[body.index("$$") + 2] in "&DF":
        ev.is_point_consequence = True
        ev.team = "V" if body.startswith("*") else "H"
        m = re.match(r"[a*]\$\$([&DF])([A-Z])([#=!/]?)", body)
        if m:
            ev.skill = m.group(2)       # H = Hard attack skill type
            ev.evaluation = m.group(3)  # # = kill/point, = = opponent error
        return ev

    # lineup declaration: *P18>LUp or aP18>LUp (set start or mid-set change)
    if ">LUp" in body or body.startswith(("aP", "*P")):
        ev.is_lineup = True
        ev.team = "V" if body[0] == "*" else "H"
        m = re.match(r"[a*]P(\d+)", body)
        if m:
            ev.lineup_server_jersey = int(m.group(1))
        return ev

    # regular skill event: [*|a]<nn><skill>[type][eval]...
    if len(body) < 4:
        return ev
    ev.team = "V" if body[0] == "*" else "H"
    if not body[1:3].isdigit():
        return ev
    ev.player_number = int(body[1:3])

    tail = body[3:]

    if not tail:
        return ev
    ev.skill = tail[0]
    tail = tail[1:]

    if tail and tail[0] in "HMQUTOhmuqto":
        ev.skill_type = tail[0]
        tail = tail[1:]

    if tail and tail[0] in "+#-/!=":
        ev.evaluation = tail[0]
        tail = tail[1:]

    # setter call e.g. K1F, K2B, KFF
    sc_m = re.match(r"(K[A-Z0-9]{1,2})", tail)
    if sc_m:
        ev.setter_code = sc_m.group(1)
        tail = tail[len(sc_m.group(1)):]

    # attack combo + zones e.g. V5~45~H2RC  or ~~F  or ~~B
    # end_subzone is 0–3 chars: RC, RS, LC, SC, SS, NRC, NRS, IRS, etc.
    ac_m = re.match(r"([A-Z~]{2})~(\d{2})~([A-Z]\d)([A-Z]{0,3})", tail)
    if ac_m:
        raw_ac = ac_m.group(1).replace("~", "")
        if raw_ac:
            ev.attack_code = raw_ac
        ev.start_zone = ac_m.group(2)
        ev.end_zone = ac_m.group(3)
        ev.end_subzone = ac_m.group(4) or None

    return ev


# ── section dispatch ──────────────────────────────────────────────────────────

_SECTION_RE = re.compile(r"^\[3([A-Z_-]+)\]")


def parse_dvw(path: str) -> DvwFile:
    """Read and parse a .dvw file; return a populated DvwFile."""
    dvw = DvwFile(source_path=path)

    with open(path, "rb") as fh:
        text = fh.read().decode(ENCODING, errors="replace")

    current: str | None = None
    buf: list[str] = []

    def flush(section: str, data: list[str]) -> None:
        data = [ln for ln in data if ln.strip()]
        if section == "DATAVOLLEYSCOUT":
            dvw.header = _parse_header(data)
        elif section == "MATCH":
            dvw.match = _parse_match(data)
        elif section == "TEAMS":
            dvw.teams = [_parse_team(ln) for ln in data]
        elif section == "MORE":
            dvw.more = _parse_more(data)
        elif section == "COMMENTS":
            raw_text = "\n".join(data)
            dvw.comments, dvw.set_comments = _parse_comments(raw_text)
        elif section == "SET":
            dvw.sets = _parse_sets(data)
        elif section == "PLAYERS-H":
            dvw.players += [_parse_player(ln, 0) for ln in data]
        elif section == "PLAYERS-V":
            dvw.players += [_parse_player(ln, 1) for ln in data]
        elif section == "ATTACKCOMBINATION":
            dvw.attack_combinations = [_parse_attack_combination(ln) for ln in data]
        elif section == "SETTERCALL":
            dvw.setter_calls = [_parse_setter_call(ln) for ln in data]
        elif section == "WINNINGSYMBOLS":
            dvw.winning_symbols = "\n".join(data)
        elif section == "VIDEO":
            dvw.video_files = _parse_video(data)
        elif section == "SCOUT":
            dvw.scout_events = [_parse_scout_event(ln) for ln in data]

    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            if current is not None:
                flush(current, buf)
            current = m.group(1)
            buf = []
        elif current is not None:
            buf.append(line)

    if current is not None:
        flush(current, buf)

    return dvw
