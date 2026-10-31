import datetime as dt
import json
import os
import unittest

from generator import availability, parse, recovery
from generator.core_five import compute_core, missing_players

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def lu(tid, starters, played=None):
    return {tid: {"starters": starters, "played": played if played is not None else starters, "names": {}}}


class CoreFiveTest(unittest.TestCase):
    def test_most_starts_wins_and_recent_breaks_ties(self):
        games = [lu("1", ["a", "b", "c", "d", "e"]), lu("1", ["a", "b", "c", "d", "f"]), lu("1", ["a", "b", "c", "e", "g"])]
        core = compute_core(games, "1")
        self.assertEqual([p for p, _ in core][:3], ["a", "b", "c"])
        # d aj e majú 2 štarty; e štartoval naposledy -> vyššie
        self.assertEqual([p for p, _ in core][3:], ["e", "d"])

    def test_traded_player_replaced(self):
        games = [lu("1", ["a", "b", "c", "d", "e"]), lu("1", ["a", "b", "c", "d", "f"])]
        core = compute_core(games, "1", roster_ids={"a", "b", "c", "d", "f", "g"})
        self.assertEqual(sorted(p for p, _ in core), ["a", "b", "c", "d", "f"])

    def test_missing_includes_absent_and_dnp(self):
        core = [("a", 3), ("b", 3), ("c", 3), ("d", 3), ("e", 3)]
        side = {"starters": ["a", "b", "c", "x", "y"], "played": ["a", "b", "c", "x", "y"]}
        self.assertEqual(missing_players(core, side), ["d", "e"])

    def test_lineup_from_real_box_score(self):
        with open(os.path.join(FIX, "summary_401909277.json")) as f:
            lineup = parse.lineup_from_summary(json.load(f))
        self.assertEqual(set(lineup), {"27", "30"})
        for side in lineup.values():
            self.assertEqual(len(side["starters"]), 5)
            self.assertEqual(set(side), {"starters", "played", "listed", "names"})
        # Anthony Gill (WSH) mal DNP – nehral
        self.assertNotIn("2581184", lineup["27"]["played"])
        self.assertIn("2581184", lineup["27"]["listed"])


class AvailabilityTest(unittest.TestCase):
    P = [
        {"id": "1", "name": "Long Out", "status": "Out", "returnEstimate": "2026-11-11", "isCore": True, "severity": "short"},
        {"id": "2", "name": "Day To Day", "status": "Day-To-Day", "returnEstimate": "2026-10-31", "isCore": True, "severity": "dtd"},
        {"id": "3", "name": "No Date", "status": "Out", "returnEstimate": None, "isCore": False, "severity": "unknown"},
        {"id": "4", "name": "Bench Out", "status": "Out", "returnEstimate": "2027-02-01", "isCore": False, "severity": "long"},
    ]

    def names(self, entries):
        return [(e["name"], e.get("note")) for e in entries]

    def test_next_game_trusts_espn_status(self):
        out, doubt = availability.absences(self.P, "2026-11-01", True)
        self.assertEqual(self.names(out), [("Long Out", None), ("Bench Out", None), ("No Date", None)])
        self.assertEqual(self.names(doubt), [("Day To Day", None)])

    def test_later_game_uses_return_estimate(self):
        out, doubt = availability.absences(self.P, "2026-11-04", False)
        self.assertEqual(self.names(out), [("Long Out", None), ("Bench Out", None)])
        self.assertEqual(self.names(doubt), [("No Date", "bez termínu návratu")])  # DTD sa pri neskorších neuvádza
        out, doubt = availability.absences(self.P, "2026-11-11", False)
        self.assertIn(("Long Out", "možný návrat"), self.names(doubt))


class RecoveryRulesTest(unittest.TestCase):
    def item(self, name, short="", long="", status="Out", **kw):
        d = {"name": name, "status": status, "_short": short, "_long": long}
        d.update(kw)
        return d

    def ret(self, it):
        return recovery.return_rule(it, it["_short"] + " " + it["_long"])[0]

    def test_days_use_upper_bound(self):
        it = self.item("Kawhi Leonard", "Leonard is expected to be sidelined for at least three to four weeks.")
        self.assertEqual(recovery.return_rule(it, it["_short"]), ("najmenej 3–4 týždne", 28))
        it = self.item("Jimmy Butler", "Butler could return sometime between January and February.", date="2026-10-16T00:00Z")
        label, days = recovery.return_rule(it, it["_short"])
        self.assertEqual(label, "január – február")
        self.assertEqual(days, (dt.date(2027, 2, 28) - dt.date(2026, 10, 16)).days)

    def test_timeline_only_from_own_sentences(self):
        it = self.item("Ben Sheppard", 'Head coach confirmed Sheppard will miss "months" after surgery.',
                       "With Tyrese Haliburton (hamstring) expected to miss at least two weeks, Jackson plays more.")
        self.assertEqual(self.ret(it), "niekoľko mesiacov")

    def test_elapsed_time_is_not_a_timeline(self):
        it = self.item("Donte DiVincenzo", "DiVincenzo remains confident he'll return this season.",
                       "DiVincenzo is approaching six months since tearing his Achilles.")
        self.assertEqual(self.ret(it), recovery.UNKNOWN)

    def test_ranges(self):
        self.assertEqual(self.ret(self.item("Kawhi Leonard", "Leonard is expected to be sidelined for at least three to four weeks.")),
                         "najmenej 3–4 týždne")
        self.assertEqual(self.ret(self.item("Tyrese Haliburton", "Haliburton will miss at least the next two weeks.")),
                         "najmenej 2 týždne")
        self.assertEqual(self.ret(self.item("Steven Adams", 'Udoka said Adams could be out "a week or two".')), "1–2 týždne")
        self.assertEqual(self.ret(self.item("X Y", "", status="Day-To-Day")), "zo dňa na deň")
        self.assertEqual(self.ret(self.item("A B", "", fantasy="OFS")), "do konca sezóny")

    def test_severity_scale(self):
        today = dt.date(2026, 10, 31)
        rep = "2026-10-29T12:00Z"

        def sev(days=None, status="Out", **kw):
            it = dict(status=status, date=rep, **kw)
            return recovery.severity(it, {"days": days, "expectedReturn": "x"}, today)

        self.assertEqual(sev(1, status="Day-To-Day"), ("dtd", "source"))
        self.assertEqual(sev(14), ("short", "source"))           # 2 týždne -> žltá
        self.assertEqual(sev(60), ("month", "source"))           # 2 mesiace -> oranžová
        self.assertEqual(sev(120), ("long", "source"))           # 4 mesiace -> červená
        self.assertEqual(sev(200), ("season", "source"))         # > pol roka -> čierna
        self.assertEqual(sev(fantasy="OFS"), ("season", "source"))
        self.assertEqual(sev(), ("unknown", None))               # bez zdroja a bez ESPN dátumu
        self.assertEqual(sev(returnDate="2027-01-15"), ("month", "espn"))  # záložný ESPN odhad

    def test_reason_and_source(self):
        it = self.item("A B", type="Knee", detail="Surgery", side="Right")
        self.assertEqual(recovery.reason_rule(it), "Koleno – operácia (pravá strana)")
        self.assertEqual(recovery.reason_rule(self.item("A B", type="Illness", side="Right")), "Choroba")
        self.assertEqual(recovery.source_rule("Leonard will miss time, Chris Haynes of NBA TV reports."), "Chris Haynes (NBA TV)")


if __name__ == "__main__":
    unittest.main()
