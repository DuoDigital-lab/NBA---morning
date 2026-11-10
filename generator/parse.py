"""Whitelist parsovanie ESPN odpovedí.

Pravidlo: každá funkcia tu skladá NOVÝ objekt iba z explicitne vymenovaných polí.
Skóre, štatistiky, víťaz, bilancie, štvrtiny, OT, titulky ani kurzy sa sem nikdy nedostanú –
ani do medzivýsledkov. Štatistiky hráča sa použijú len na boolean "hral / nehral" a hneď sa zahodia.
"""
import re

from .config import SEASON_TYPES


def _s(v):
    return None if v is None else str(v)


def _color(c):
    if c and re.fullmatch(r"[0-9a-fA-F]{6}", c):
        return "#" + c.lower()
    return None


def _dark_logo(team):
    for logo in team.get("logos") or []:
        rel = logo.get("rel") or []
        if "dark" in rel and "scoreboard" not in rel and logo.get("href"):
            return logo["href"]
    for logo in team.get("logos") or []:
        if logo.get("href"):
            return logo["href"]
    return team.get("logo")


def team_info(team):
    return {
        "id": _s(team.get("id")),
        "abbr": team.get("abbreviation"),
        "name": team.get("displayName"),
        "short": team.get("shortDisplayName") or team.get("name"),
        "logo": _dark_logo(team),
        "color": _color(team.get("color")),
        "altColor": _color(team.get("alternateColor")),
    }


def teams_list(teams_json):
    out = []
    for league in teams_json["sports"][0]["leagues"]:
        for t in league["teams"]:
            out.append(team_info(t["team"]))
    return out


def game_state(status_type):
    """'final' | 'live' | 'pre' | 'off' (odložený/zrušený). Žiadny detail (\"Final/OT\") sa neprenáša."""
    state = status_type.get("state")
    if state == "post":
        return "final" if status_type.get("completed") else "off"
    if state == "in":
        return "live"
    if state == "pre":
        name = status_type.get("name") or ""
        return "off" if ("POSTPONED" in name or "CANCELED" in name) else "pre"
    return "off"


def _game(e):
    comp = (e.get("competitions") or [{}])[0]
    sides = {}
    for c in comp.get("competitors") or []:
        sides[c.get("homeAway")] = _s((c.get("team") or {}).get("id"))
    if not sides.get("home") or not sides.get("away"):
        return None
    status = comp.get("status") or e.get("status") or {}
    return {
        "id": _s(e.get("id")),
        "startUTC": e.get("date"),
        "state": game_state(status.get("type") or {}),
        "awayId": sides["away"],
        "homeId": sides["home"],
    }


def games_from_scoreboard(sb):
    return [g for g in (_game(e) for e in sb.get("events") or []) if g]


def games_from_schedule(sched):
    """Všetky zápasy tímu v sezóne (aj budúce) – len čas, stav a tímy."""
    out = []
    for e in sched.get("events") or []:
        stype = (e.get("seasonType") or {}).get("type")
        if stype is not None and int(stype) not in SEASON_TYPES:
            continue
        g = _game(e)
        if g:
            out.append(g)
    return out


def completed_events_from_schedule(sched):
    """[(event_id, startUTC)] dokončených zápasov (základná časť / play-in / playoff), od najstaršieho."""
    out = []
    for e in sched.get("events") or []:
        comp = (e.get("competitions") or [{}])[0]
        st = (comp.get("status") or e.get("status") or {}).get("type") or {}
        stype = (e.get("seasonType") or {}).get("type")
        if stype is not None and int(stype) not in SEASON_TYPES:
            continue
        if st.get("completed"):
            out.append((_s(e["id"]), e.get("date")))
    out.sort(key=lambda x: x[1] or "")
    return out


def lineup_from_summary(summary):
    """{team_id: {"starters": [ids], "played": [ids], "listed": [ids], "names": {id: name}}}

    "played" = hráč má v box score riadok so štatistikami a nie je označený didNotPlay
    (ak má v štatistikách čokoľvek, na ihrisku bol – aj keď len pár sekúnd).
    Vráti None, ak box score ešte nie je kompletné.
    """
    box = (summary or {}).get("boxscore") or {}
    teams = box.get("players") or []
    if len(teams) != 2:
        return None
    out = {}
    for t in teams:
        tid = _s((t.get("team") or {}).get("id"))
        blocks = t.get("statistics") or []
        athletes = blocks[0].get("athletes") if blocks else []
        starters, played, listed, names = [], [], [], {}
        for a in athletes or []:
            ath = a.get("athlete") or {}
            pid = _s(ath.get("id"))
            if not pid:
                continue
            names[pid] = ath.get("displayName")
            listed.append(pid)
            if a.get("starter"):
                starters.append(pid)
            has_stats = bool(a.get("stats"))
            if has_stats and not a.get("didNotPlay"):
                played.append(pid)
        if len(starters) != 5:
            return None
        out[tid] = {"starters": starters, "played": played, "listed": listed, "names": names}
    return out


def roster_from_api(roster_json):
    out = []
    for a in roster_json.get("athletes") or []:
        inj = (a.get("injuries") or [])
        out.append({
            "id": _s(a.get("id")),
            "name": a.get("displayName"),
            "pos": (a.get("position") or {}).get("abbreviation"),
            "jersey": a.get("jersey"),
            "headshot": (a.get("headshot") or {}).get("href"),
            "injuryStatus": inj[0].get("status") if inj else None,
        })
    return out


def positions_from_depthchart(dc):
    """{player_id: 'PG'|'SG'|'SF'|'PF'|'C'} z ESPN depth chartu (pri viacerých pozíciách tá s najlepším poradím)."""
    best = {}
    for item in (dc or {}).get("items") or []:
        for key, v in (item.get("positions") or {}).items():
            for a in v.get("athletes") or []:
                m = re.search(r"/athletes/(\d+)", (a.get("athlete") or {}).get("$ref") or "")
                if not m:
                    continue
                pid, rank = m.group(1), a.get("rank") or 99
                if pid not in best or rank < best[pid][1]:
                    best[pid] = (key.upper(), rank)
    return {pid: pos for pid, (pos, _) in best.items()}


def _athlete_id(ath):
    if ath.get("id"):
        return _s(ath["id"])
    for link in ath.get("links") or []:
        m = re.search(r"/id/(\d+)", link.get("href") or "")
        if m:
            return m.group(1)
    return None


def injuries_from_api(inj_json):
    """Surové texty (short/longComment) idú iba do modulu recovery, ktorý ich prefiltruje.
    Do výstupu sa nikdy nekopírujú priamo."""
    out = {}
    for team in inj_json.get("injuries") or []:
        tid = _s(team.get("id"))
        for i in team.get("injuries") or []:
            ath = i.get("athlete") or {}
            pid = _athlete_id(ath)
            if not pid:
                continue
            d = i.get("details") or {}
            out[pid] = {
                "id": pid,
                "name": ath.get("displayName"),
                "teamId": tid,
                "status": i.get("status"),
                "date": i.get("date"),
                "type": d.get("type"),
                "location": d.get("location"),
                "detail": d.get("detail"),
                "side": d.get("side"),
                "returnDate": d.get("returnDate"),
                "fantasy": ((d.get("fantasyStatus") or {}).get("abbreviation")),
                "_short": i.get("shortComment") or "",
                "_long": i.get("longComment") or "",
            }
    return out
