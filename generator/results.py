"""JEDINÉ miesto, kde generátor číta skóre.

Výsledky idú výhradne do docs/data/scores/<US deň>.json. Appka ich načíta až po výslovnom
(dvojitom) ťuknutí na „Zobraziť výsledok“ pri konkrétnom zápase. Všetky ostatné dáta ostávajú bez skóre
a kontrola spoilerov ich naďalej stráži.
"""


def _pts(v):
    if isinstance(v, dict):
        v = v.get("value", v.get("displayValue"))
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def scores_from_events(events):
    """{event_id: {"away": int, "home": int, "ot": počet predĺžení alebo None}} pre dohrané zápasy."""
    out = {}
    for e in events or []:
        comp = (e.get("competitions") or [{}])[0]
        status = comp.get("status") or e.get("status") or {}
        st = status.get("type") or {}
        if not (st.get("completed") and st.get("state") == "post"):
            continue
        sides = {c.get("homeAway"): _pts(c.get("score")) for c in comp.get("competitors") or []}
        if sides.get("home") is None or sides.get("away") is None:
            continue
        periods = [s.get("period") for s in (comp.get("status"), e.get("status")) if s and isinstance(s.get("period"), int)]
        period = max(periods) if periods else None
        out[str(e.get("id"))] = {
            "away": sides["away"], "home": sides["home"],
            "ot": max(0, int(period) - 4) if isinstance(period, int) else None,
        }
    return out


def boxscore_from_summary(summary):
    """Box score zápasu (rovnako ako skóre ide len do oddeleného súboru docs/data/boxscores/<deň>.json).
    {team_id: {"labels": [...], "players": [{"id","name","pos","st","s": [...]}], "dnp": [...], "totals": [...]}}"""
    out = {}
    for t in ((summary or {}).get("boxscore") or {}).get("players") or []:
        tid = str((t.get("team") or {}).get("id"))
        blocks = t.get("statistics") or []
        if not blocks:
            continue
        b = blocks[0]
        players, dnp = [], []
        for a in b.get("athletes") or []:
            ath = a.get("athlete") or {}
            row = {"id": str(ath.get("id")), "name": ath.get("displayName"),
                   "pos": (ath.get("position") or {}).get("abbreviation")}
            if a.get("didNotPlay") or not a.get("stats"):
                reason = (a.get("reason") or "").strip()
                reason = "rozhodnutie trénera" if reason.upper() == "COACH'S DECISION" else (reason.capitalize() or None)
                dnp.append(dict(row, reason=reason))
            else:
                players.append(dict(row, st=bool(a.get("starter")), s=a.get("stats")))
        out[tid] = {"labels": b.get("labels") or [], "players": players, "dnp": dnp, "totals": b.get("totals") or []}
    return out or None
