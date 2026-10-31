"""Jednorazovo vyrobí testovacie fixtures z reálnych ESPN odpovedí (_research/cache).

Všetky skutočné skóre a štatistiky sa nahradia VYMYSLENÝMI hodnotami a pridajú sa umelé spoilery
(titulky, OT, leaders...), aby testy overili, že ich generátor zahodí. Fixtures teda neprezrádzajú
žiadne reálne výsledky.
"""
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "_research", "cache")
TEAMS = {"27", "30"}  # WSH, CHA
GAME = "401909277"

FAKE_SCORE = {"home": "131", "away": "127"}
FAKE_HEADLINE = "Miller erupts for 45 PTS as Hornets beat Wizards 131-127 in OT"


def load(name):
    with open(os.path.join(SRC, name)) as f:
        return json.load(f)


def dump(name, obj):
    with open(os.path.join(HERE, name), "w") as f:
        json.dump(obj, f, ensure_ascii=False)


def fake_competitor(c):
    c = dict(c)
    c["score"] = FAKE_SCORE.get(c.get("homeAway"), "99")
    c["winner"] = c.get("homeAway") == "away"
    c["linescores"] = [{"value": 33}, {"value": 30}, {"value": 29}, {"value": 27}, {"value": 8}]
    c["records"] = [{"summary": "5-1"}]
    c["leaders"] = [{"leaders": [{"displayValue": "45 PTS", "athlete": {"displayName": "Brandon Miller"}}]}]
    c["statistics"] = [{"name": "points", "displayValue": "131"}]
    return c


def fake_status(st):
    st = json.loads(json.dumps(st))
    st.setdefault("type", {})["detail"] = "Final/OT"
    st["type"]["shortDetail"] = "Final/OT"
    st["period"] = 5
    return st


def main():
    teams = load("teams.json")
    lg = teams["sports"][0]["leagues"][0]
    lg["teams"] = [t for t in lg["teams"] if t["team"]["id"] in TEAMS]
    dump("teams.json", teams)

    needed = {GAME}
    for tid in TEAMS:
        s = load(f"sched_{tid}.json")
        evs = []
        for e in s["events"]:
            c = e["competitions"][0]
            if not c["status"]["type"]["completed"]:
                evs.append({  # budúci zápas – len čas a tímy (do kalendára)
                    "id": e["id"], "date": e["date"], "seasonType": e.get("seasonType"),
                    "competitions": [{"status": c["status"], "competitors": [
                        {"homeAway": x["homeAway"], "team": {"id": x["team"]["id"]}} for x in c["competitors"]]}],
                })
                continue
            c["competitors"] = [fake_competitor(x) for x in c["competitors"]]
            evs.append(e)
            needed.add(e["id"])
        s["events"] = evs
        dump(f"schedule_{tid}.json", s)
        dump(f"roster_{tid}.json", load(f"roster_{tid}.json"))

    for path in glob.glob(os.path.join(SRC, "sum_*.json")):
        eid = os.path.basename(path)[4:-5]
        if eid not in needed:
            continue
        d = load(os.path.basename(path))
        for t in d["boxscore"]["players"]:
            for a in t["statistics"][0]["athletes"]:
                if a.get("stats"):
                    a["stats"] = ["12"] + ["45"] * (len(a["stats"]) - 1)
            t["statistics"][0]["totals"] = ["240", "131"]
        d["boxscore"]["teams"] = [{"statistics": [{"name": "points", "displayValue": "131"}]}]
        hdr = d.get("header", {})
        for comp in hdr.get("competitions", []):
            comp["competitors"] = [fake_competitor(c) for c in comp.get("competitors", [])]
            comp["status"] = fake_status(comp.get("status", {}))
        out = {
            "boxscore": d["boxscore"], "header": hdr,
            "leaders": [{"leaders": [{"displayValue": "45 PTS"}]}],
            "winprobability": [{"homeWinPercentage": 0.12}],
            "odds": [{"details": "WSH -3.5", "overUnder": 228.5}],
            "news": {"articles": [{"headline": FAKE_HEADLINE}]},
            "article": {"headline": FAKE_HEADLINE},
            "standings": {"groups": [{"standings": {"entries": [{"stats": [{"displayValue": "5-1"}]}]}}]},
        }
        dump(f"summary_{eid}.json", out)

    sb = load("../sb_20261030.json") if os.path.exists(os.path.join(SRC, "../sb_20261030.json")) else None
    sb = {"events": [e for e in sb["events"] if e["id"] == GAME]}
    for e in sb["events"]:
        c = e["competitions"][0]
        c["competitors"] = [fake_competitor(x) for x in c["competitors"]]
        c["headlines"] = [{"shortLinkText": FAKE_HEADLINE, "description": FAKE_HEADLINE}]
        c["highlights"] = [{"headline": FAKE_HEADLINE}]
        e["status"] = fake_status(e["status"])
    dump("scoreboard_20261030.json", sb)

    inj = load("../injuries.json")
    inj["injuries"] = [t for t in inj["injuries"] if str(t.get("id")) in TEAMS]
    wsh = next(t for t in inj["injuries"] if str(t["id"]) == "27")
    wsh["injuries"].append({
        "status": "Out", "date": "2026-10-30T12:00Z",
        "athlete": {"id": "999001", "displayName": "Test Player"},
        "shortComment": "Player (ankle) will miss two to three weeks, Josh Robbins of The Athletic reports.",
        "longComment": "Player scored 30 points in the 131-127 win before leaving in the third quarter. "
                       "Teammate Somebody is expected to miss six weeks.",
        "details": {"type": "Ankle", "detail": "Sprain", "side": "Left", "returnDate": "2026-11-20",
                    "fantasyStatus": {"abbreviation": "OUT"}},
    })
    dump("injuries.json", inj)
    print("fixtures ok:", sorted(os.listdir(HERE)))


if __name__ == "__main__":
    main()
