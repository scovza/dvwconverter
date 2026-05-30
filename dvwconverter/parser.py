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
    """Match header from [3MATCH] (two semicolon-delimited lines)."""
    date: Optional[str] = None
    time: Optional[str] = None
    season: Optional[str] = None
    league: Optional[str] = None
    phase: Optional[str] = None
    field5: Optional[str] = None
    match_number: Optional[int] = None
    field7: Optional[str] = None
    codepage: Optional[int] = None
    field9: Optional[str] = None
    field10: Optional[str] = None
    field11: Optional[str] = None
    encoded_league: Optional[str] = None
    encoded_phase: Optional[str] = None
    field_l2_0: Optional[str] = None
    field_l2_1: Optional[str] = None
    venue_code: Optional[str] = None
    field_l2_3: Optional[str] = None
    field_l2_4: Optional[str] = None
    field_l2_5: Optional[str] = None
    home_away: Optional[str] = None     # L=local/home, V=visitor
    field_l2_7: Optional[str] = None
    field_l2_8: Optional[str] = None
    scout_code: Optional[str] = None


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
    field4: Optional[str] = None
    referee: Optional[str] = None
    encoded_field6: Optional[str] = None
    encoded_city: Optional[str] = None
    encoded_field8: Optional[str] = None
    encoded_referee: Optional[str] = None
    duration1: Optional[int] = None
    duration2: Optional[int] = None


@dataclass
class SetScore:
    """Score snapshots for one set from [3SET]."""
    set_number: int = 0
    played: Optional[bool] = None
    score_8: Optional[str] = None
    score_16: Optional[str] = None
    score_21: Optional[str] = None
    final_score: Optional[str] = None
    duration: Optional[int] = None


@dataclass
class Player:
    """Player roster entry from [3PLAYERS-H] or [3PLAYERS-V]."""
    team_index: int = 0             # 0=home, 1=visiting
    number: Optional[int] = None
    player_id: int = 0              # sequential across both rosters
    starting_position_s1: Optional[str] = None
    starting_position_s2: Optional[str] = None
    starting_position_s3: Optional[str] = None
    field6: Optional[str] = None
    field7: Optional[str] = None
    short_name: Optional[str] = None
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    field11: Optional[str] = None
    field12: Optional[str] = None
    role: Optional[int] = None      # 1=libero 2=OH 3=MB 4=opp 5=setter
    foreign: Optional[bool] = None
    field15: Optional[str] = None
    field16: Optional[str] = None
    field17: Optional[str] = None
    encoded_last: Optional[str] = None
    encoded_first: Optional[str] = None
    field20: Optional[str] = None
    field21: Optional[str] = None
    field22: Optional[str] = None
    field23: Optional[str] = None


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
    attacker_position: Optional[str] = None  # F B C S P -
    field9: Optional[str] = None
    field10: Optional[str] = None


@dataclass
class SetterCall:
    """Setter call code definition from [3SETTERCALL]."""
    code: Optional[str] = None
    field1: Optional[str] = None
    description: Optional[str] = None
    field3: Optional[str] = None
    color: Optional[int] = None
    # coordinate fields share the same YYXX encoding as AttackCombination.position
    x1: Optional[int] = None           # setter's position on canvas
    y1: Optional[int] = None           # apex/midpoint of the set-arc ball trajectory
    x2: Optional[int] = None           # attack target position
    area_list: Optional[str] = None    # comma-separated area codes
    highlight_color: Optional[int] = None


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
        [*|a]<nn><skill>[type][eval][attack|setter][~zone~target][specials]
        ;[custom1];[custom2];;;;;;[video_time];[set];[score_h];[score_v];[serving];[frame];;[rot_h];[rot_v];

    Prefix: * = visiting team, a = home team.
    Special prefixes: **Nset=set boundary, *z/az=rotation, *p/ap=point,
                      ac/*c=substitution, aT/*T=timeout, $$&=rally outcome,
                      *P/aP=lineup declaration.
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
    end_subzone: Optional[str] = None
    special: Optional[str] = None
    custom1: Optional[str] = None
    custom2: Optional[str] = None
    video_time: Optional[str] = None
    set_number: Optional[int] = None
    home_score: Optional[int] = None
    visiting_score: Optional[int] = None
    serving_team: Optional[int] = None  # 1=home, 0=visiting
    video_frame: Optional[int] = None
    rotation_home: Optional[str] = None
    rotation_visiting: Optional[str] = None

    is_set_start: bool = False
    is_rotation: bool = False
    is_point: bool = False
    is_substitution: bool = False
    is_timeout: bool = False
    is_point_consequence: bool = False
    is_lineup: bool = False


@dataclass
class DvwFile:
    """Root container for all sections of a parsed .dvw file."""
    source_path: str = ""
    header: FileHeader = field(default_factory=FileHeader)
    match: MatchInfo = field(default_factory=MatchInfo)
    teams: list[Team] = field(default_factory=list)
    more: MoreInfo = field(default_factory=MoreInfo)
    comments: str = ""
    sets: list[SetScore] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
    attack_combinations: list[AttackCombination] = field(default_factory=list)
    setter_calls: list[SetterCall] = field(default_factory=list)
    winning_symbols: str = ""
    video_files: list[VideoFile] = field(default_factory=list)
    scout_events: list[ScoutEvent] = field(default_factory=list)


# ── section parsers ───────────────────────────────────────────────────────────

def _parse_header(lines: list[str]) -> FileHeader:
    h = FileHeader()
    for line in lines:
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip().lower().replace("-", "_")
            val = val.strip()
            if hasattr(h, key):
                setattr(h, key, val or None)
    return h


def _parse_match(lines: list[str]) -> MatchInfo:
    m = MatchInfo()
    if lines:
        p = _split(lines[0])
        fields_l1 = [
            "date", "time", "season", "league", "phase", "field5",
            "match_number", "field7", "codepage", "field9", "field10",
            "field11", "encoded_league", "encoded_phase",
        ]
        for i, name in enumerate(fields_l1):
            if i < len(p):
                val = _int(p[i]) if name in ("match_number", "codepage") else _str(p[i])
                setattr(m, name, val)
    if len(lines) >= 2:
        p = _split(lines[1])
        fields_l2 = [
            "field_l2_0", "field_l2_1", "venue_code", "field_l2_3",
            "field_l2_4", "field_l2_5", "home_away", "field_l2_7",
            "field_l2_8", "scout_code",
        ]
        for i, name in enumerate(fields_l2):
            if i < len(p):
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
            "field0", "field1", "field2", "city", "field4", "referee",
            "encoded_field6", "encoded_city", "encoded_field8", "encoded_referee",
        ]
        for i, name in enumerate(names):
            if i < len(p):
                setattr(m, name, _str(p[i]))
    if len(lines) >= 2:
        p = _split(lines[1])
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
            score_8=_str(p[1]) if len(p) > 1 else None,
            score_16=_str(p[2]) if len(p) > 2 else None,
            score_21=_str(p[3]) if len(p) > 3 else None,
            final_score=_str(p[4]) if len(p) > 4 else None,
            duration=_int(p[5]) if len(p) > 5 else None,
        ))
    return result


def _parse_player(line: str, team_index: int) -> Player:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return Player(
        team_index=team_index,
        number=g(1, _int), player_id=g(2, _int) or 0,
        starting_position_s1=g(3), starting_position_s2=g(4),
        starting_position_s3=g(5), field6=g(6), field7=g(7),
        short_name=g(8), last_name=g(9), first_name=g(10),
        field11=g(11), field12=g(12), role=g(13, _int),
        foreign=g(14, _bool), field15=g(15), field16=g(16), field17=g(17),
        encoded_last=g(18), encoded_first=g(19),
        field20=g(20), field21=g(21), field22=g(22), field23=g(23),
    )


def _parse_attack_combination(line: str) -> AttackCombination:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return AttackCombination(
        code=g(0), tempo=g(1, _int), side=g(2), height=g(3),
        description=g(4), field5=g(5), color=g(6, _int),
        position=g(7, _int), attacker_position=g(8),
        field9=g(9), field10=g(10),
    )


def _parse_setter_call(line: str) -> SetterCall:
    p = _split(line)
    g = lambda i, conv=_str: conv(p[i]) if len(p) > i else None
    return SetterCall(
        code=g(0), field1=g(1), description=g(2), field3=g(3),
        color=g(4, _int), x1=g(5, _int), y1=g(6, _int), x2=g(7, _int),
        area_list=g(8), highlight_color=g(9, _int),
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
            ev.home_score = _int(p[9])
            ev.visiting_score = _int(p[10])
        return ev

    parts = raw.split(";")
    if len(parts) >= 16:
        ev.custom1 = _str(parts[1])
        ev.custom2 = _str(parts[2])
        ev.video_time = _str(parts[7])
        ev.set_number = _int(parts[8])
        ev.home_score = _int(parts[9])
        ev.visiting_score = _int(parts[10])
        ev.serving_team = _int(parts[11])
        ev.video_frame = _int(parts[12])
        ev.rotation_home = _str(parts[14])
        ev.rotation_visiting = _str(parts[15]) if len(parts) > 15 else None

    body = parts[0] if parts else raw

    if body.startswith(("*z", "az")):
        ev.is_rotation = True
        return ev
    if body.startswith(("*p", "ap")):
        ev.is_point = True
        return ev
    if body.startswith(("ac", "*c")):
        ev.is_substitution = True
        return ev
    if body in ("aT", "*T"):
        ev.is_timeout = True
        return ev
    if "$$&" in body:
        ev.is_point_consequence = True
        return ev
    if ">LUp" in body or body.startswith(("aP", "*P")):
        ev.is_lineup = True
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

    # attack combo + zones e.g. V5~45~H2  or ~~F  or ~~B
    ac_m = re.match(r"([A-Z~]{2})~(\d{2})~([A-Z]\d)([A-Z]?)", tail)
    if ac_m:
        raw_ac = ac_m.group(1).replace("~", "")
        if raw_ac:
            ev.attack_code = raw_ac
        ev.start_zone = ac_m.group(2)
        ev.end_zone = ac_m.group(3)
        ev.special = ac_m.group(4) or None

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
            dvw.comments = "\n".join(data)
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
