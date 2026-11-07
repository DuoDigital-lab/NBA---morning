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
