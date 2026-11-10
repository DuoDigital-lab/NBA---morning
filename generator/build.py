"""Hlavný skript: stiahne dáta z ESPN, spracuje ich bez spoilerov a zapíše statické JSON do docs/data.

Použitie:
    python3 -m generator.build                       # bežný beh (posledné 3 US dni + dnešok)
    python3 -m generator.build --backfill-from 2026-10-20
"""
import argparse
import datetime as dt
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from . import availability, parse, recovery, results, spoilers
from .config import CALENDAR_DAYS, CORE_WINDOW, DATA_DIR, REBUILD_DAYS, STATE_DIR, US_TZ
from .core_five import compute_core, missing_players
from .espn import Espn, EspnError

MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def season_year(d):
    return d.year + 1 if d.month >= 8 else d.year


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj, label=None, check=True):
    """Atomický zápis. Výstup pre appku musí prejsť kontrolou spoilerov, inak sa nezapíše."""
    if check:
        spoilers.assert_clean(obj, label or os.path.basename(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


class Builder:
    def __init__(self, espn, data_dir=DATA_DIR, state_dir=STATE_DIR, today_et=None, workers=6):
        self.espn = espn
        self.data_dir = data_dir
        self.state_dir = state_dir
        self.workers = workers
        self.generated_at = now_utc()
        self.today_et = today_et or self.generated_at.astimezone(ZoneInfo(US_TZ)).date()
        self.errors = []
        self.warnings = []
        self.lineup_dir = os.path.join(state_dir, "lineups")
        self.names = {}

    # ---------- pomocné ----------
    def _pmap(self, fn, items, workers=None):
        with ThreadPoolExecutor(workers or self.workers) as ex:
            return list(ex.map(fn, items))

    def lineup(self, event_id):
        """Zostava zápasu (len ID hráčov a príznaky starter/hral). Hotové zápasy sa cachujú natrvalo."""
        path = os.path.join(self.lineup_dir, f"{event_id}.json")
        cached = load_json(path)
        if cached is None:
            try:
                cached = parse.lineup_from_summary(self.espn.summary(event_id))
            except EspnError as e:
                self.warnings.append(f"Box score {event_id} sa nepodarilo načítať: {e}")
                return None
            if cached is None:
                return None
            write_json(path, cached, check=False)
        for side in cached.values():
            self.names.update(side.get("names") or {})
        return cached

    def _team_window(self, team_id, before_utc=None, exclude=None):
        events = self.completed.get(team_id) or []
        if before_utc:
            events = [e for e in events if (e[1] or "") < before_utc and e[0] != exclude]
        return [e[0] for e in events[-CORE_WINDOW:]]

    def core_for(self, team_id, before_utc=None, exclude=None):
        eids = self._team_window(team_id, before_utc, exclude)
        lineups = [self.lineups.get(e) for e in eids]
        lineups = [lu for lu in lineups if lu]
        roster_ids = self.roster_ids.get(team_id)
        return compute_core(lineups, team_id, roster_ids), len(lineups)

    def pname(self, pid):
        return self.names.get(pid) or self.roster_names.get(pid) or f"#{pid}"

    # ---------- kroky ----------
    def load_teams(self):
        self.teams = parse.teams_list(self.espn.teams())
        self.team_by_id = {t["id"]: t for t in self.teams}
        season = season_year(self.today_et)
        self.season = season

        def load(t):
            out = {"id": t["id"]}
            try:
                sched = self.espn.schedule(t["id"], season)
                out["completed"] = parse.completed_events_from_schedule(sched)
                out["games"] = parse.games_from_schedule(sched)
                out["scores"] = results.scores_from_events(sched.get("events"))
            except EspnError as e:
                out["error"] = f"Rozpis {t['abbr']}: {e}"
            try:
                out["roster"] = parse.roster_from_api(self.espn.roster(t["id"]))
            except EspnError as e:
                out["error"] = (out.get("error", "") + f" Súpiska {t['abbr']}: {e}").strip()
            try:  # presné pozície PG/SG/SF/PF/C (súpiska má len G/F/C)
                pos = parse.positions_from_depthchart(self.espn.depthchart(t["id"], season))
                for p in out.get("roster") or []:
                    p["pos"] = pos.get(p["id"], p["pos"])
            except EspnError:
                pass
            return out

        prev_teams = {t["id"]: t for t in (load_json(os.path.join(self.data_dir, "teams.json"), {}) or {}).get("teams", [])}
        self.completed, self.rosters, self.season_games, self.scores = {}, {}, {}, {}
        for res in self._pmap(load, self.teams):
            if res.get("error"):
                self.warnings.append(res["error"])
            self.completed[res["id"]] = res.get("completed") or []
            for g in res.get("games") or []:
                self.season_games[g["id"]] = g
            self.scores.update(res.get("scores") or {})
            roster = res.get("roster")
            if roster is None and res["id"] in prev_teams:
                roster = [{k: v for k, v in p.items() if k != "isCore"} for p in prev_teams[res["id"]].get("roster", [])]
                self.warnings.append(f"Súpiska {self.team_by_id[res['id']]['abbr']}: použitá posledná platná verzia.")
            self.rosters[res["id"]] = roster or []
        self.roster_ids = {tid: {p["id"] for p in r} for tid, r in self.rosters.items() if r}
        self.roster_names = {p["id"]: p["name"] for r in self.rosters.values() for p in r}

    def target_dates(self, backfill_from=None):
        if backfill_from:
            d, out = backfill_from, []
            while d <= self.today_et:
                out.append(d)
                d += dt.timedelta(days=1)
            return out
        return [self.today_et - dt.timedelta(days=k) for k in range(REBUILD_DAYS, -1, -1)]

    def games_on(self, us_date):
        """Zápasy daného US dňa z rozpisov tímov (bez scoreboardu)."""
        et = ZoneInfo(US_TZ)
        return [g for g in self.season_games.values() if g["startUTC"] and
                dt.datetime.fromisoformat(g["startUTC"].replace("Z", "+00:00")).astimezone(et).date() == us_date]

    def build_days(self, dates):
        boards = {}

        def fetch(d):
            try:
                sb = self.espn.scoreboard(d.strftime("%Y%m%d"))
                self.scores.update(results.scores_from_events(sb.get("events")))  # scoreboard má prednosť
                return d, parse.games_from_scoreboard(sb)
            except EspnError as e:
                # Záloha: tie isté zápasy sú aj v rozpisoch tímov (ESPN scoreboard občas pre niektorý deň zlyháva).
                fallback = self.games_on(d)
                if fallback:
                    self.warnings.append(f"Scoreboard {d} nedostupný, zápasy z rozpisov tímov ({e}).")
                    return d, fallback
                self.errors.append(f"Rozpis zápasov {d}: {e}")
                return d, None

        for d, games in self._pmap(fetch, dates, workers=3):  # scoreboard je citlivejší na nápor
            boards[d] = games

        # Všetky zostavy, ktoré budeme potrebovať (zápasy dňa + okno pred nimi + aktuálne okno tímov).
        needed = set()
        for games in boards.values():
            for g in games or []:
                if g["state"] != "final":
                    continue
                needed.add(g["id"])
                for tid in (g["awayId"], g["homeId"]):
                    needed.update(self._team_window(tid, g["startUTC"], g["id"]))
        for tid in self.completed:
            needed.update(self._team_window(tid))
        self.lineups = dict(zip(sorted(needed), self._pmap(self.lineup, sorted(needed))))

        written = []
        for d in sorted(boards):
            games = boards[d]
            if games is None:
                continue
            day = {"date": d.isoformat(), "generatedAt": iso(self.generated_at), "games": []}
            for g in sorted((g for g in games if g["state"] == "final"), key=lambda g: (g["startUTC"] or "", g["id"])):
                day["games"].append(self._game_entry(d, g))
            path = os.path.join(self.data_dir, "days", f"{d.isoformat()}.json")
            if not day["games"] and not os.path.exists(path):
                continue
            try:
                write_json(path, day)
                written.append(d.isoformat())
            except spoilers.SpoilerError as e:
                self.errors.append(str(e))
            # Skutočné výsledky – samostatný súbor, appka ho načíta až na výslovné ťuknutie.
            day_scores = {g["id"]: self.scores[g["id"]] for g in day["games"] if g["id"] in self.scores}
            if day_scores:
                write_json(os.path.join(self.data_dir, "scores", f"{d.isoformat()}.json"), day_scores, check=False)
        self.latest_day = written[-1] if written else None
        return boards

    def _game_entry(self, d, g):
        lu = self.lineups.get(g["id"])
        entry = {"id": g["id"], "startUTC": g["startUTC"], "lineupReady": lu is not None}
        for side, tid in (("away", g["awayId"]), ("home", g["homeId"])):
            core, n = self.core_for(tid, g["startUTC"], g["id"])
            info = {"teamId": tid, "coreGames": n, "core": [c[0] for c in core], "missing": []}
            if lu and tid in lu and core:
                info["missing"] = [{"id": p, "name": self.pname(p)} for p in missing_players(core, lu[tid])]
            entry[side] = info
        away, home = self.team_by_id.get(g["awayId"], {}), self.team_by_id.get(g["homeId"], {})
        date_en = f"{MONTHS_EN[d.month - 1]} {d.day} {d.year}"
        entry["ytQuery"] = f"{away.get('short', '')} vs {home.get('short', '')} {date_en}".strip()
        return entry

    def build_teams(self):
        out = []
        self.current_core = {}
        for t in self.teams:
            core, n = self.core_for(t["id"])
            core_ids = [c[0] for c in core]
            self.current_core[t["id"]] = set(core_ids)
            roster = [dict(p, isCore=p["id"] in core_ids) for p in self.rosters.get(t["id"], [])]
            notes = []
            if roster and not 13 <= len(roster) <= 18:
                notes.append(f"Súpiska má {len(roster)} hráčov (bežne 15 + 3 two-way).")
            if len(core) < 5:
                notes.append("Málo odohraných zápasov na spoľahlivú základnú päťku.")
            out.append(dict(t, coreGames=n, gamesPlayed=len(self.completed.get(t["id"]) or []),
                            core=[{"id": p, "name": self.pname(p), "starts": s, "played": g} for p, s, g in core],
                            roster=roster, notes=notes))
        write_json(os.path.join(self.data_dir, "teams.json"),
                   {"generatedAt": iso(self.generated_at), "season": self.season, "window": CORE_WINDOW, "teams": out})

    def build_recovery(self):
        path = os.path.join(self.data_dir, "injuries.json")
        try:
            items = parse.injuries_from_api(self.espn.injuries())
        except EspnError as e:
            self.errors.append(f"Injuries: {e} – zobrazujem poslednú platnú verziu.")
            return
        cache_path = os.path.join(self.state_dir, "recovery_cache.json")
        cache = load_json(cache_path, {}) or {}
        notes = recovery.build_recovery(items, cache, self.warnings)
        write_json(cache_path, cache, check=False)
        heads = {p["id"]: p.get("headshot") for r in self.rosters.values() for p in r}
        today = self.generated_at.astimezone(ZoneInfo("Europe/Bratislava")).date()
        players = []
        for pid, it in items.items():
            n = notes[pid]
            sev, basis = recovery.severity(it, n, today)
            players.append({
                "severity": sev, "severityLabel": recovery.SEVERITY_LABELS[sev], "severityBasis": basis,
                "returnEstimate": recovery.return_estimate(it, n)[0],
                "id": pid, "name": it["name"], "teamId": it["teamId"],
                "status": it["status"], "statusSk": recovery.status_sk(it),
                "reason": n["reason"], "expectedReturn": n["expectedReturn"], "returnSource": n["returnSource"],
                "method": n["method"], "reportDate": (it["date"] or "")[:10] or None,
                "espnReturnDate": it.get("returnDate"),
                "isCore": pid in self.current_core.get(it["teamId"], set()),
                "headshot": heads.get(pid),
            })
        # Hráči zo základnej päťky, ktorí v poslednom zápase nehrali a ESPN pri nich žiadne zranenie neuvádza.
        listed = set(items)
        latest = load_json(os.path.join(self.data_dir, "days", f"{self.latest_day}.json")) if self.latest_day else None
        for g in (latest or {}).get("games", []):
            for side in ("away", "home"):
                for m in g[side]["missing"]:
                    if m["id"] not in listed:
                        listed.add(m["id"])
                        players.append({
                            "severity": "none", "severityLabel": recovery.SEVERITY_LABELS["none"], "severityBasis": None,
                            "returnEstimate": None,
                            "id": m["id"], "name": m["name"], "teamId": g[side]["teamId"], "status": None,
                            "statusSk": "Bez záznamu v injury reporte", "reason": "ESPN neuvádza dôvod",
                            "expectedReturn": recovery.UNKNOWN, "returnSource": "", "method": "rules",
                            "reportDate": None, "espnReturnDate": None,
                            "isCore": True, "headshot": heads.get(m["id"]),
                        })
        players.sort(key=lambda p: (p["teamId"] or "", not p["isCore"], p["name"] or ""))
        self.injury_players = players
        try:
            write_json(path, {"generatedAt": iso(self.generated_at), "players": players})
        except spoilers.SpoilerError as e:
            self.errors.append(str(e))

    def build_upcoming(self, boards):
        """Kalendár na CALENDAR_DAYS US dní dopredu z rozpisov tímov + kto isto / možno nenastúpi."""
        et = ZoneInfo(US_TZ)
        last_day = self.today_et + dt.timedelta(days=CALENDAR_DAYS - 1)
        candidates = list(self.season_games.values())
        if not candidates:  # rozpisy tímov zlyhali -> aspoň dnešok a zajtrajšok zo scoreboardu
            for d in (self.today_et, self.today_et + dt.timedelta(days=1)):
                try:
                    candidates += boards.get(d) or parse.games_from_scoreboard(self.espn.scoreboard(d.strftime("%Y%m%d")))
                except EspnError as e:
                    self.warnings.append(f"Nadchádzajúce zápasy {d}: {e}")
        games = []
        for g in candidates:
            if g["state"] not in ("pre", "live") or not g["startUTC"]:
                continue
            us_date = dt.datetime.fromisoformat(g["startUTC"].replace("Z", "+00:00")).astimezone(et).date()
            if self.today_et <= us_date <= last_day:
                games.append(dict(g, usDate=us_date.isoformat()))
        games.sort(key=lambda g: (g["startUTC"], g["id"]))

        players = getattr(self, "injury_players", None)
        if players is None:  # injuries zlyhali -> posledná platná verzia
            players = (load_json(os.path.join(self.data_dir, "injuries.json"), {}) or {}).get("players", [])
        by_team = {}
        for p in players:
            by_team.setdefault(p["teamId"], []).append(p)
        seen = set()
        for g in games:
            for side, tid in (("away", g["awayId"]), ("home", g["homeId"])):
                out, doubt = availability.absences(by_team.get(tid, []), g["usDate"], tid not in seen)
                g[side] = {"out": out, "doubtful": doubt}
                seen.add(tid)
        write_json(os.path.join(self.data_dir, "upcoming.json"),
                   {"generatedAt": iso(self.generated_at), "days": CALENDAR_DAYS, "games": games})

    def build_index(self):
        days = []
        for path in sorted(glob.glob(os.path.join(self.data_dir, "days", "*.json")), reverse=True):
            d = load_json(path, {}) or {}
            if d.get("games"):
                days.append({"date": d["date"], "games": len(d["games"])})
        write_json(os.path.join(self.data_dir, "index.json"), {"generatedAt": iso(self.generated_at), "days": days})

    def write_status(self, ok):
        path = os.path.join(self.data_dir, "status.json")
        prev = load_json(path, {}) or {}
        status = {
            "generatedAt": iso(self.generated_at),
            "ok": ok and not self.errors,
            "lastSuccessAt": iso(self.generated_at) if ok and not self.errors else prev.get("lastSuccessAt"),
            "errors": self.errors[:20],
            "warnings": self.warnings[:30],
        }
        write_json(path, status)
        return status

    def run(self, backfill_from=None):
        try:
            self.load_teams()
        except EspnError as e:
            self.errors.append(f"ESPN API nedostupné ({e}). Appka ukazuje poslednú platnú verziu.")
            return self.write_status(False)
        boards = self.build_days(self.target_dates(backfill_from))
        steps = [self.build_teams, self.build_recovery, lambda: self.build_upcoming(boards), self.build_index]
        for step in steps:
            try:
                step()
            except Exception as e:  # jeden pokazený krok nesmie zhodiť ostatné
                self.errors.append(f"{getattr(step, '__name__', 'krok')}: {type(e).__name__}: {e}")
        return self.write_status(True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill-from", type=dt.date.fromisoformat)
    ap.add_argument("--today", type=dt.date.fromisoformat, help="US (ET) dátum 'dnes' – na testovanie")
    ap.add_argument("--data-dir", default=DATA_DIR)
    ap.add_argument("--state-dir", default=STATE_DIR)
    args = ap.parse_args(argv)
    b = Builder(Espn(), args.data_dir, args.state_dir, today_et=args.today)
    status = b.run(args.backfill_from)
    print(json.dumps(status, ensure_ascii=False, indent=1))
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
