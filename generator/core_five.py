"""Základná päťka = hráči, ktorí v posledných N zápasoch tímu štartujú, KEĎ HRAJÚ.

Zápasy, ktoré hráč vynechal (zranenie, odpočinok), sa mu nepočítajú proti nemu. Hviezda, ktorá
odštartovala 2 zápasy a potom sa zranila (2 štarty z 2 odohraných), ostáva v základnej päťke a jej
dočasná náhrada (napr. 3 štarty z 5) nie. Hráč, ktorého tréner posunul na lavičku, hrá ďalej bez štartov,
takže jeho podiel štartov klesá a z päťky prirodzene vypadne.

Poradie: podiel štartov = štarty / (odohrané + 1). To "+1" tlmí náhodné jednorazové štarty
(1 z 1 = 0,5, kým pravidelný štartér 9 z 9 = 0,9). Pri rovnosti rozhoduje viac štartov, potom novší štart.
"""
from collections import Counter


def compute_core(lineups, team_id, roster_ids=None, n=5):
    """lineups: zoznam lineup dictov (od najstaršieho), každý {team_id: {"starters": [...], "played": [...]}}.
    roster_ids: ak je zadané, hráči mimo aktuálnej súpisky (trade/waive) sa vynechajú.
    Vracia [(player_id, starts, played)]."""
    starts, played = Counter(), Counter()
    last = {}
    for i, lu in enumerate(lineups):
        side = lu.get(team_id) if lu else None
        if not side:
            continue
        on_court = set(side.get("played") or []) | set(side["starters"])
        for pid in on_court:
            played[pid] += 1
        for pid in side["starters"]:
            starts[pid] += 1
            last[pid] = i
    candidates = [p for p in starts if roster_ids is None or p in roster_ids]
    ranked = sorted(candidates, key=lambda p: (-starts[p] / (played[p] + 1), -starts[p], -last[p]))
    return [(p, starts[p], played[p]) for p in ranked[:n]]


def missing_players(core, lineup_side):
    """Hráči zo základnej päťky, ktorí v zápase nehrali (DNP, neaktívni alebo úplne chýbajú v box score)."""
    played = set(lineup_side["played"])
    return [c[0] for c in core if c[0] not in played]
