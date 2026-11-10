"""Základná päťka = hráči, ktorí v posledných N zápasoch tímu štartujú, KEĎ HRAJÚ.

Poradie hráčov A a B:
1. Priamy súboj: v zápasoch, ktoré odohrali OBAJA, kto štartoval, keď ten druhý nie. Tak zranená hviezda
   (Kawhi: 2 zápasy, 2 štarty, náhradník vtedy z lavičky) ostane pred svojou náhradou, aj keď náhrada
   medzitým nazbiera viac štartov. A hráča, ktorého tréner posunul na lavičku, predbehne ten, kto ho nahradil.
2. Podiel štartov v odohraných zápasoch (vynechané zápasy sa nepočítajú proti nemu).
3. Viac štartov, potom novší štart.
Jednorazové štarty (1 štart, keď má tím aspoň 3 zápasy) sa nepočítajú – sú to zvyčajne náhrady za zranených.
"""
from collections import Counter
from functools import cmp_to_key


def compute_core(lineups, team_id, roster_ids=None, n=5):
    """lineups: zoznam lineup dictov (od najstaršieho), každý {team_id: {"starters": [...], "played": [...]}}.
    roster_ids: ak je zadané, hráči mimo aktuálnej súpisky (trade/waive) sa vynechajú.
    Vracia [(player_id, starts, played)]."""
    starts, played = Counter(), Counter()
    last = {}
    games = []  # (množina hrajúcich, množina štartérov)
    for i, lu in enumerate(lineups):
        side = lu.get(team_id) if lu else None
        if not side:
            continue
        starters = set(side["starters"])
        on_court = set(side.get("played") or []) | starters
        games.append((on_court, starters))
        for pid in on_court:
            played[pid] += 1
        for pid in starters:
            starts[pid] += 1
            last[pid] = i
    min_starts = 2 if len(games) >= 3 else 1
    candidates = [p for p in starts if starts[p] >= min_starts and (roster_ids is None or p in roster_ids)]
    if len(candidates) < n:  # málo dát (začiatok sezóny) – doplň aj jednorazovými štartérmi
        candidates += [p for p in starts if p not in candidates and (roster_ids is None or p in roster_ids)]

    def head_to_head(a, b):
        a_over = b_over = 0
        for on_court, starters in games:
            if a in on_court and b in on_court:
                if a in starters and b not in starters:
                    a_over += 1
                elif b in starters and a not in starters:
                    b_over += 1
        return a_over - b_over

    def compare(a, b):
        h = head_to_head(a, b)
        if h:
            return -h
        ka = (starts[a] / played[a], starts[a], last[a])
        kb = (starts[b] / played[b], starts[b], last[b])
        if ka != kb:
            return -1 if ka > kb else 1
        return -1 if a < b else (1 if a > b else 0)  # stabilné poradie pri úplnej zhode

    ranked = sorted(candidates, key=cmp_to_key(compare))
    return [(p, starts[p], played[p]) for p in ranked[:n]]


def missing_players(core, lineup_side):
    """Hráči zo základnej päťky, ktorí v zápase nehrali (DNP, neaktívni alebo úplne chýbajú v box score)."""
    played = set(lineup_side["played"])
    return [c[0] for c in core if c[0] not in played]
