"""Compute a deterministic Accuracy Index for a converted DvwFile."""

from dataclasses import dataclass
from .parser import DvwFile, ScoutEvent

# Minimum event count considered a valid scouted match.
_MIN_EVENTS = 50


@dataclass
class AccuracyReport:
    """Breakdown of the Accuracy Index score."""
    score: float                    # 0.0 – 100.0
    skill_events: int
    special_events: int
    total_events: int
    parsed_skill_ratio: float       # fraction of skill events fully parsed
    has_teams: bool
    has_players: bool
    has_sets: bool
    has_score_context: bool         # fraction of skill events with score context
    details: dict[str, float]       # per-component weights and values

    def __str__(self) -> str:
        lines = [
            f"Accuracy Index : {self.score:.1f} / 100",
            f"  Skill events parsed     : {self.parsed_skill_ratio * 100:.1f}%"
            f"  ({self.skill_events} skill / {self.total_events} total)",
            f"  Header completeness     : teams={self.has_teams}"
            f"  players={self.has_players}  sets={self.has_sets}",
            f"  Score context coverage  : {self.has_score_context * 100:.1f}%",
        ]
        return "\n".join(lines)


def compute_accuracy(dvw: DvwFile) -> AccuracyReport:
    """
    Compute the Accuracy Index for a converted DvwFile.

    Formula
    -------
    Score = w1*C_skill + w2*C_header + w3*C_score + w4*C_volume

    Where:
      C_skill   = fraction of skill events with (team + player + skill) parsed
      C_header  = (has_teams + has_players + has_sets) / 3
      C_score   = fraction of skill events that carry home_score/visiting_score
      C_volume  = min(total_events / MIN_EVENTS, 1.0)  — penalises near-empty files

    Weights: w1=0.50  w2=0.20  w3=0.20  w4=0.10

    Interpretation
    --------------
    90–100  High confidence; all major sections present, nearly all events parsed.
    70–89   Good; minor gaps (e.g. some events lack score context).
    50–69   Moderate; structural data present but event parsing has notable gaps.
    <50     Low; likely incomplete or non-standard file.

    Limitations
    -----------
    - The index measures parsing completeness, not semantic correctness.
    - Files with only a few events score lower even if perfectly parsed.
    - Undecoded fields (fieldN) are ignored; they do not affect the score.
    - Score context requires DataVolley to embed it; some exports omit it.
    """
    events: list[ScoutEvent] = dvw.scout_events
    total = len(events)

    skill_events = [
        e for e in events
        if not any([e.is_set_start, e.is_rotation, e.is_point,
                    e.is_substitution, e.is_timeout,
                    e.is_point_consequence, e.is_lineup])
        and e.team is not None
    ]
    n_skill = len(skill_events)

    # C_skill: events where team, player number, and skill letter were decoded
    if n_skill:
        fully_parsed = sum(
            1 for e in skill_events
            if e.team and e.player_number is not None and e.skill
        )
        c_skill = fully_parsed / n_skill
    else:
        c_skill = 0.0

    # C_header: structural completeness
    has_teams = len(dvw.teams) >= 2
    has_players = len(dvw.players) >= 2
    has_sets = any(s.played for s in dvw.sets)
    c_header = (has_teams + has_players + has_sets) / 3

    # C_score: fraction of skill events with embedded score context
    if n_skill:
        with_score = sum(
            1 for e in skill_events
            if e.home_score is not None and e.visiting_score is not None
        )
        c_score = with_score / n_skill
    else:
        c_score = 0.0

    # C_volume: penalise near-empty files
    c_volume = min(total / _MIN_EVENTS, 1.0)

    score = 100.0 * (0.50 * c_skill + 0.20 * c_header + 0.20 * c_score + 0.10 * c_volume)

    return AccuracyReport(
        score=round(score, 2),
        skill_events=n_skill,
        special_events=total - n_skill,
        total_events=total,
        parsed_skill_ratio=round(c_skill, 4),
        has_teams=has_teams,
        has_players=has_players,
        has_sets=has_sets,
        has_score_context=round(c_score, 4),
        details={
            "c_skill": round(c_skill, 4),
            "c_header": round(c_header, 4),
            "c_score": round(c_score, 4),
            "c_volume": round(c_volume, 4),
            "w_skill": 0.50,
            "w_header": 0.20,
            "w_score": 0.20,
            "w_volume": 0.10,
        },
    )
