"""Hlavná poistka: vygenerovaný výstup (JSON + statické HTML/JS) nesmie obsahovať skóre ani spoilerové polia.

Fixtures obsahujú VYMYSLENÉ skóre 131-127, "Final/OT", leaders "45 PTS", titulky, kurzy a win probability.
Ak by sa čokoľvek z toho dostalo do výstupu, test zlyhá.
"""
import datetime as dt
import glob
import json
import os
import re
import shutil
import tempfile
import unittest

from generator import spoilers
from generator.build import Builder
from tests.fake_espn import FixtureEspn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
MARKERS = ["131", "127", "Final/OT", "45 PTS", "erupts", "-3.5", "228.5", "5-1", "winProbability", "homeWinPercentage"]


class GeneratedOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        cls.tmp = tempfile.mkdtemp(prefix="nba-test-")
        cls.data = os.path.join(cls.tmp, "data")
        cls.state = os.path.join(cls.tmp, "state")
        b = Builder(FixtureEspn(), cls.data, cls.state, today_et=dt.date(2026, 10, 31), workers=2)
        cls.status = b.run()
        cls.files = sorted(glob.glob(os.path.join(cls.data, "**", "*.json"), recursive=True))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_ok(self):
        self.assertTrue(self.status["ok"], self.status)
        names = {os.path.relpath(f, self.data) for f in self.files}
        for required in ("teams.json", "injuries.json", "upcoming.json", "index.json", "status.json",
                         os.path.join("days", "2026-10-30.json")):
            self.assertIn(required, names)

    def test_no_forbidden_keys_or_text(self):
        for path in self.files:
            with open(path, encoding="utf-8") as f:
                obj = json.load(f)
            self.assertEqual(spoilers.find_violations(obj), [], path)

    def test_no_fake_score_markers(self):
        for path in self.files:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            for m in MARKERS:
                # čísla kontrolujeme ako samostatné tokeny (nie časť ID)
                pat = r"(?<![\w.])" + re.escape(m) + r"(?![\w.])"
                self.assertIsNone(re.search(pat, raw), f"{m!r} v {path}")

    def test_game_card_content(self):
        with open(os.path.join(self.data, "days", "2026-10-30.json"), encoding="utf-8") as f:
            day = json.load(f)
        self.assertEqual(len(day["games"]), 1)
        g = day["games"][0]
        self.assertEqual(set(g), {"id", "startUTC", "lineupReady", "away", "home", "ytQuery"})
        self.assertEqual(set(g["away"]), {"teamId", "coreGames", "core", "missing"})
        self.assertEqual(g["ytQuery"], "Hornets vs Wizards Oct 30 2026")
        self.assertEqual(len(g["away"]["core"]), 5)
        self.assertTrue(g["lineupReady"])

    def test_recovery_filters_game_sentences(self):
        with open(os.path.join(self.data, "injuries.json"), encoding="utf-8") as f:
            players = json.load(f)["players"]
        test = next(p for p in players if p["id"] == "999001")
        self.assertEqual(test["expectedReturn"], "2–3 týždne")  # nie "6 týždňov" od spoluhráča
        self.assertEqual(test["returnSource"], "Josh Robbins (The Athletic)")
        dump = json.dumps(test, ensure_ascii=False)
        self.assertNotIn("30", dump.replace("2026-10-30", ""))
        self.assertNotIn("quarter", dump)

    def test_calendar_with_absences(self):
        with open(os.path.join(self.data, "upcoming.json"), encoding="utf-8") as f:
            up = json.load(f)
        self.assertTrue(up["games"])
        dates = [g["usDate"] for g in up["games"]]
        self.assertEqual(dates, sorted(dates))
        self.assertTrue(all("2026-10-31" <= d <= "2026-11-13" for d in dates))
        wsh = [g for g in up["games"] if "27" in (g["awayId"], g["homeId"])]
        side = lambda g: g["home"] if g["homeId"] == "27" else g["away"]  # noqa: E731
        first = side(wsh[0])
        self.assertIn("999001", [e["id"] for e in first["out"]])  # Out -> isto nehrá na najbližší zápas
        for g in up["games"]:
            self.assertEqual(set(g), {"id", "startUTC", "state", "awayId", "homeId", "usDate", "away", "home"})


class StaticFrontendTest(unittest.TestCase):
    def test_frontend_never_reads_spoiler_fields(self):
        bad = re.compile(r"\.(score|scores|linescores|winner|records?|leaders|statistics|stats|odds|headlines?|period|standings)\b")
        for path in glob.glob(os.path.join(DOCS, "*.js")) + glob.glob(os.path.join(DOCS, "*.html")):
            with open(path, encoding="utf-8") as f:
                src = f.read()
            self.assertIsNone(bad.search(src), path)

    def test_committed_data_is_clean(self):
        for path in glob.glob(os.path.join(DOCS, "data", "**", "*.json"), recursive=True):
            with open(path, encoding="utf-8") as f:
                self.assertEqual(spoilers.find_violations(json.load(f)), [], path)


class SpoilerPatternTest(unittest.TestCase):
    def test_detects(self):
        for s in ["Final 112-108", "won in OT", "Pacers (5-3)", "scored 32 points", "víťazstvo Bostonu", "2OT thriller",
                  "had a triple-double"]:
            self.assertTrue(spoilers.text_violations(s), s)

    def test_allows(self):
        for s in ["Koleno – operácia (ľavá strana)", "3–4 týždne", "10-14 dní", "2026-10-30", "Hornets vs Wizards Oct 30 2026",
                  "#23", "Mimo hry", "zo dňa na deň", "Andrew Wiggins", "Kawhi Leonard"]:
            self.assertEqual(spoilers.text_violations(s), [], s)

    def test_forbidden_key_blocks_write(self):
        with self.assertRaises(spoilers.SpoilerError):
            spoilers.assert_clean({"games": [{"id": "1", "score": "0"}]})

    def test_filter_injury_text(self):
        txt = ("Edwards underwent surgery Thursday. He was averaging 33.3 points. "
               "He left the game in the third quarter of the win. He could miss up to two months.")
        out = spoilers.filter_injury_text(txt)
        self.assertIn("surgery", out)
        self.assertIn("two months", out)
        self.assertNotIn("33.3", out)
        self.assertNotIn("quarter", out)


if __name__ == "__main__":
    unittest.main()
