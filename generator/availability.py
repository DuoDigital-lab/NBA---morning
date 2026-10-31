"""Kto isto / možno nenastúpi v nadchádzajúcom zápase – zo stavu ESPN injury reportu a odhadu návratu.

Pravidlá:
* Najbližší zápas tímu: stav "Out" = isto nehrá; "Day-To-Day" / "Questionable" / "Doubtful" = otázny.
  (ESPN stav sa vzťahuje na najbližší zápas, preto mu tu veríme bez ohľadu na odhad návratu.)
* Neskoršie zápasy: "Out" hráč isto nehrá, kým zápas nie je na/po očakávanom návrate.
  Od dátumu odhadu je "otázny – možný návrat". Bez akéhokoľvek odhadu je "otázny – bez termínu".
  Day-To-Day hráči sa pri neskorších zápasoch neuvádzajú (zrejme už budú v poriadku).
"""

OUT_STATUSES = {"Out", "Suspension"}
DOUBT_STATUSES = {"Day-To-Day", "Questionable", "Doubtful"}


def _entry(p, note=None):
    e = {"id": p["id"], "name": p["name"], "isCore": bool(p.get("isCore")), "severity": p.get("severity") or "unknown"}
    if note:
        e["note"] = note
    return e


def absences(players, game_date, is_next_game):
    """players: hráči jedného tímu z injuries.json; game_date: ISO US dátum zápasu.
    Vracia (isto_nehrajú, otázni), základná päťka vždy prvá."""
    out, doubt = [], []
    for p in players:
        status = p.get("status")
        est = p.get("returnEstimate")
        if status in OUT_STATUSES:
            if is_next_game:
                out.append(_entry(p))
            elif est and game_date >= est:
                doubt.append(_entry(p, "možný návrat"))
            elif est:
                out.append(_entry(p))
            else:
                doubt.append(_entry(p, "bez termínu návratu"))
        elif status in DOUBT_STATUSES and is_next_game:
            doubt.append(_entry(p))
    key = lambda e: (not e["isCore"], e["name"] or "")  # noqa: E731
    return sorted(out, key=key), sorted(doubt, key=key)
