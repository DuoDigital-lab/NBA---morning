"""Základná päťka = hráči s najviac štartmi v posledných N zápasoch tímu."""
from collections import Counter


def compute_core(lineups, team_id, roster_ids=None, n=5):
    """lineups: zoznam lineup dictov (od najstaršieho), každý {team_id: {"starters": [...]}}.
    roster_ids: ak je zadané, hráči mimo aktuálnej súpisky (trade/waive) sa vynechajú a päťku doplní ďalší.
    Pri rovnosti štartov rozhoduje novší štart.
    Vracia [(player_id, starts)]."""
    starts = Counter()
    last = {}
    for i, lu in enumerate(lineups):
        side = lu.get(team_id) if lu else None
        if not side:
            continue
        for pid in side["starters"]:
            starts[pid] += 1
            last[pid] = i
    ranked = sorted(starts, key=lambda p: (-starts[p], -last[p]))
    if roster_ids is not None:
        ranked = [p for p in ranked if p in roster_ids]
    return [(p, starts[p]) for p in ranked[:n]]


def missing_players(core, lineup_side):
    """Hráči zo základnej päťky, ktorí v zápase nehrali (DNP, neaktívni alebo úplne chýbajú v box score)."""
    played = set(lineup_side["played"])
    return [pid for pid, _ in core if pid not in played]
