"""Profily hráčov (spúšťa sa ručne cca raz za pol roka, nie v dennej synchronizácii).

    python3 tools/update_profiles.py            # všetky súpisky (~530 hráčov, pár minút)
    python3 tools/update_profiles.py --team 28  # len jeden tím (ESPN team id)

Výstup: docs/data/players/<team id>.json

* Osobné údaje a kariéra: ESPN (súpiska, profil hráča, štatistiky po sezónach).
* Štatistiky len z UKONČENÝCH sezón (aktuálna sezóna by mohla prezradiť včerajší zápas).
* Ocenenia sa zobrazia IBA ak sa zhodujú dva nezávislé zdroje:
    - MVP, Finals MVP, All-NBA, All-Defensive, ROY, DPOY, 6MOY, MIP, All-Star MVP, All-Rookie, Clutch, NBA Cup MVP:
      ESPN ocenenia == infobox článku na anglickej Wikipédii (počet musí sedieť),
    - All-Star výbery: infobox == počet ročníkov "<rok> NBA All-Star Game", kde je hráč uvedený,
    - Tituly NBA: infobox roky, ktoré sedia s ESPN (tím hráča v danej sezóne) a s tabuľkou "List of NBA champions".
  Čo sa nezhoduje, sa vynechá a vypíše na konci ako nesúlad.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from generator import parse  # noqa: E402
from generator.config import DATA_DIR  # noqa: E402
from generator.espn import CORE, SITE, Espn, EspnError  # noqa: E402

UA = "nba-rano-profiles/1.0 (personal, non-commercial)"
V3 = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes"
OUT_DIR = os.path.join(DATA_DIR, "players")

# kanonický kľúč -> (slovenský názov, poradie)
ACCOLADES = {
    "champion": ("NBA šampión", 1), "finals_mvp": ("MVP finále", 2), "mvp": ("MVP sezóny", 3),
    "all_star": ("All-Star výber", 4), "asg_mvp": ("MVP All-Star zápasu", 5),
    "all_nba_1": ("All-NBA 1. tím", 6), "all_nba_2": ("All-NBA 2. tím", 7), "all_nba_3": ("All-NBA 3. tím", 8),
    "dpoy": ("Obranca roka", 9), "all_def_1": ("All-Defensive 1. tím", 10), "all_def_2": ("All-Defensive 2. tím", 11),
    "roy": ("Nováčik roka", 12), "all_rookie": ("All-Rookie tím", 13), "sixth": ("6. muž roka", 14),
    "mip": ("Hráč s najväčším zlepšením", 15), "clutch": ("Clutch hráč roka", 16), "cup_mvp": ("MVP NBA Cupu", 17),
}
ESPN_AWARD = {
    "MVP": "mvp", "Finals MVP": "finals_mvp", "All-Star MVP": "asg_mvp", "Rookie of the Year": "roy",
    "All-NBA 1st Team": "all_nba_1", "All-NBA 2nd Team": "all_nba_2", "All-NBA 3rd Team": "all_nba_3",
    "All-Defensive 1st Team": "all_def_1", "All-Defensive 2nd Team": "all_def_2",
    "All-Rookie 1st Team": "all_rookie", "All-Rookie 2nd Team": "all_rookie",
    "Defensive Player of the Year": "dpoy", "Sixth Man of the Year": "sixth", "Most Improved Player": "mip",
    "Clutch Player of the Year": "clutch", "NBA Cup MVP": "cup_mvp",
}
WIKI_AWARD = [  # (regex na cieľ/text odkazu v infoboxe, kľúč)
    (r"^NBA champion$", "champion"), (r"Finals Most Valuable|Finals MVP", "finals_mvp"),
    (r"^NBA Most Valuable Player", "mvp"), (r"^NBA All-Star Game.*(MVP|Most Valuable)", "asg_mvp"),
    (r"^NBA All-Star$", "all_star"), (r"^All-NBA First Team", "all_nba_1"), (r"^All-NBA Second Team", "all_nba_2"),
    (r"^All-NBA Third Team", "all_nba_3"), (r"^NBA All-Defensive First Team", "all_def_1"),
    (r"^NBA All-Defensive Second Team", "all_def_2"), (r"^NBA Rookie of the Year", "roy"),
    (r"^NBA All-Rookie (First|Second) Team", "all_rookie"), (r"^NBA Defensive Player of the Year", "dpoy"),
    (r"^NBA Sixth Man of the Year", "sixth"), (r"^NBA Most Improved Player", "mip"),
    (r"^NBA Clutch Player of the Year", "clutch"), (r"^NBA Cup MVP$", "cup_mvp"),
]


def http_json(url, data=None, tries=6):
    """GET/POST s opakovaním pri 429/5xx (Wikidata pri preťažení obmedzuje na 1 požiadavku/min)."""
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * (attempt + 1)
            print(f"  {e.code} – čakám {wait} s…", flush=True)
            time.sleep(min(wait, 120))


def season_year(d):
    return d.year + 1 if d.month >= 8 else d.year


# ---------------------------- ESPN ----------------------------

class Profiles:
    def __init__(self, espn):
        self.espn = espn
        self.award_names = {}

    def award_name(self, ref):
        m = re.search(r"/awards/(\d+)", ref)
        key = m.group(1) if m else ref
        if key not in self.award_names:
            self.award_names[key] = self.espn._get(ref.replace("http://", "https://")).get("name")
        return self.award_names[key]

    def player(self, ath, team_id, current_season):
        pid = str(ath["id"])
        out = {
            "id": pid, "name": ath.get("displayName"), "teamId": team_id, "jersey": ath.get("jersey"),
            "pos": (ath.get("position") or {}).get("displayName"),
            "headshot": (ath.get("headshot") or {}).get("href"),
            "born": (ath.get("dateOfBirth") or "")[:10] or None, "age": ath.get("age"),
            "birthPlace": ", ".join(x for x in ((ath.get("birthPlace") or {}).get(k) for k in ("city", "state", "country")) if x) or None,
            "heightCm": round(ath["height"] * 2.54) if ath.get("height") else None, "heightFt": ath.get("displayHeight"),
            "weightKg": round(ath["weight"] * 0.4536) if ath.get("weight") else None, "weightLbs": ath.get("displayWeight"),
            "college": (ath.get("college") or {}).get("name"),
            "experience": (ath.get("experience") or {}).get("years"),
        }
        try:
            v3 = self.espn._get(f"{V3}/{pid}").get("athlete") or {}
            out["draft"] = v3.get("displayDraft")
            out["debutYear"] = v3.get("debutYear")
            m = re.search(r"(\d+)", v3.get("displayExperience") or "")  # "24th Season" / "Rookie"
            out["seasonNo"] = int(m.group(1)) if m else (1 if "Rookie" in (v3.get("displayExperience") or "") else None)
        except EspnError:
            out["draft"] = None
        out.update(self.career(pid, current_season))
        out["espnAwards"] = self.awards(pid)
        return out

    def career(self, pid, current_season):
        try:
            d = self.espn._get(f"{V3}/{pid}/stats")
        except EspnError:
            return {"career": [], "seasons": [], "totals": None}
        names = {str(t.get("id")): (t.get("displayName"), t.get("abbreviation")) for t in (d.get("teams") or {}).values()}
        cats = {c.get("name"): c for c in d.get("categories") or []}
        avg, tot = cats.get("averages") or {}, cats.get("totals") or {}
        al, tl = avg.get("labels") or [], tot.get("labels") or []
        tot_rows = {(r["season"]["year"], r.get("teamId")): r["stats"] for r in tot.get("statistics") or []}
        seasons, gp_sum, sums = [], 0, Counter()
        stints = []
        for r in avg.get("statistics") or []:
            year, tid = r["season"]["year"], str(r.get("teamId"))
            name, abbr = names.get(tid, (None, None))
            if not stints or stints[-1]["teamId"] != tid:
                stints.append({"teamId": tid, "team": name, "abbr": abbr, "from": r["season"]["displayName"], "to": r["season"]["displayName"]})
            else:
                stints[-1]["to"] = r["season"]["displayName"]
            if year >= current_season:  # aktuálna sezóna = možný spoiler
                continue
            s = dict(zip(al, r["stats"]))
            gp = int(float(s.get("GP") or 0))
            seasons.append({"season": r["season"]["displayName"], "abbr": abbr, "gp": gp,
                            "ppg": s.get("PTS"), "rpg": s.get("REB"), "apg": s.get("AST")})
            t = dict(zip(tl, tot_rows.get((year, r.get("teamId")), [])))
            gp_sum += gp
            for k in ("PTS", "REB", "AST"):
                try:
                    sums[k] += int(float(t.get(k) or 0))
                except ValueError:
                    pass
        totals = None
        if gp_sum:
            totals = {"seasons": len({x["season"] for x in seasons}), "gp": gp_sum,
                      "pts": sums["PTS"], "reb": sums["REB"], "ast": sums["AST"],
                      "ppg": round(sums["PTS"] / gp_sum, 1), "rpg": round(sums["REB"] / gp_sum, 1),
                      "apg": round(sums["AST"] / gp_sum, 1),
                      "through": seasons[-1]["season"] if seasons else None}
        return {"career": stints, "seasons": seasons, "totals": totals}

    def awards(self, pid):
        try:
            d = self.espn._get(f"{CORE}/athletes/{pid}/awards?limit=200")
        except EspnError:
            return {}
        counts = Counter()
        for it in d.get("items") or []:
            key = ESPN_AWARD.get(self.award_name(it["$ref"]) or "")
            if key:
                counts[key] += 1
        return dict(counts)


# ---------------------------- Wikipédia ----------------------------

TITLES_CACHE = os.path.join(os.path.dirname(OUT_DIR), "..", "..", "state", "wiki_titles.json")


def wiki_titles(espn_ids):
    """ESPN id -> názov článku na en.wikipedia (Wikidata vlastnosť P3685 = ESPN NBA ID). Pamätá sa v state/wiki_titles.json."""
    path = os.path.normpath(TITLES_CACHE)
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    out = {k: v for k, v in cache.items() if k in espn_ids and v}
    ids = sorted(i for i in espn_ids if i not in cache)
    # Wikidata vyhľadávanie (haswbstatement) – nepodlieha obmedzeniam SPARQL služby.
    for i in range(0, len(ids), 40):
        chunk = ids[i:i + 40]
        q = "haswbstatement:" + "|".join(f"P3685={x}" for x in chunk)
        res = http_json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "query", "list": "search", "srsearch": q, "srlimit": 50, "format": "json"}))
        qids = [h["title"] for h in res["query"]["search"]]
        if qids:
            ent = http_json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "wbgetentities", "ids": "|".join(qids), "props": "claims|sitelinks",
                 "sitefilter": "enwiki", "format": "json"}))
            for e in ent.get("entities", {}).values():
                title = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title")
                for c in (e.get("claims") or {}).get("P3685", []):
                    val = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                    if val in chunk and title:
                        out[val] = title
        for x in chunk:
            cache[x] = out.get(x)  # None = hráč nemá článok (nehľadať znova)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, sort_keys=True)
    return out


def wiki_texts(titles):
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 50):
        params = {"action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "redirects": 1,
                  "format": "json", "formatversion": 2, "titles": "|".join(titles[i:i + 50])}
        res = http_json("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params))
        redirects = {r["to"]: r["from"] for r in res["query"].get("redirects") or []}
        for p in res["query"]["pages"]:
            if p.get("revisions"):
                out[redirects.get(p["title"], p["title"])] = p["revisions"][0]["slots"]["main"]["content"]
    return out


def infobox_awards(text):
    """{kľúč: (počet, [roky])} z riadkov '* 4× [[NBA champion]] (2012, 2013, ...)' v infoboxe."""
    m = re.search(r"\|\s*highlights\s*=(.*?)(?:\n\s*\|\s*[a-z_]+\s*=|\n\}\})", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        lm = re.match(r"\s*\*\s*(?:(\d+)\s*×\s*)?\[\[([^\]|]+)(?:\|([^\]]+))?\]\](.*)", line)
        if not lm:
            continue
        count = int(lm.group(1) or 1)
        target, label = lm.group(2).strip(), (lm.group(3) or "").strip()
        rest = lm.group(4)
        years = _years(rest)
        for pattern, key in WIKI_AWARD:
            if re.search(pattern, target) or (label and re.search(pattern, label)):
                c, ys = out.get(key, (0, []))
                out[key] = (c + count, ys + years)
                break
    return out


def _years(rest):
    """Roky z '{{nasg|2005}}–{{nasg|2026}}', '[[2012 NBA Finals|2012]]', '{{nbay|2008|end}}' – rozsahy rozbalí."""
    toks = []
    for m in re.finditer(r"\{\{nasg\|(\d{4})\}\}|\[\[\d{4} [^\]|]*\|(\d{4})\]\]|\{\{nbay\|(\d{4})[^}]*\}\}", rest):
        y = int(m.group(1) or m.group(2) or m.group(3))
        if m.group(3):  # {{nbay|2008|end}} = sezóna 2008-09 -> rok 2009
            y += 1
        toks.append((y, m.start(), m.end()))
    years = []
    for i, (y, start, _end) in enumerate(toks):
        if i and years and re.fullmatch(r"\s*[–-]\s*", rest[toks[i - 1][2]:start]):
            years.extend(range(years[-1] + 1, y + 1))
        else:
            years.append(y)
    return sorted(set(years))


def champions_by_year(text):
    """{koncový rok sezóny: názov šampióna} z tabuľky 'List of NBA champions'."""
    out = {}
    for row in text.split("\n|-"):
        y = re.search(r"\{\{nbafy\|(\d{4})\}\}", row)
        w = re.search(r"'''\s*\[\[[^\]|]*\|([^\]]+)\]\]", row)
        if y and w:
            out[int(y.group(1))] = w.group(1).strip()
    return out


def link_pattern(title):
    t = re.escape(title).replace(r"\ ", "[ _]")
    first = re.escape(title[0])
    return re.compile(r"\[\[\s*[" + first.upper() + first.lower() + "]" + t[len(first):] + r"\s*(\||\]\])")


# ---------------------------- hlavný beh ----------------------------

def verify(profile, wiki, allstar_pages, champions):
    """Do profilu doplní len ocenenia potvrdené dvoma zdrojmi. Vracia zoznam nesúladov."""
    espn = profile.pop("espnAwards", {}) or {}
    accolades, issues = [], []
    title = profile.pop("_wiki", None)
    for key, (label, order) in ACCOLADES.items():
        w = wiki.get(key)
        e = espn.get(key)
        if key == "all_star":
            if not w or not title:
                continue
            pat = link_pattern(title)
            found = [y for y in w[1] if pat.search(allstar_pages.get(f"{y} NBA All-Star Game", ""))]
            if w[1] and len(found) == len(w[1]) == w[0]:
                accolades.append({"key": key, "label": label, "count": w[0], "years": found,
                                  "sources": "Wikipédia + články o All-Star zápasoch"})
            else:
                issues.append(f"{profile['name']}: All-Star {w[0]} (infobox, roky {len(w[1])}) vs {len(found)} potvrdených")
        elif key == "champion":
            if not w:
                continue
            ok = 0
            teams_by_year = {}
            for s in profile.get("seasons") or []:
                teams_by_year[int(s["season"][:4]) + 1] = s["abbr"]
            stints = profile.get("career") or []
            for y in w[1]:
                champ = champions.get(y)
                team = next((st["team"] for st in stints if st["team"] and
                             int(st["from"][:4]) + 1 <= y <= int(st["to"][:4]) + 1), None)
                if champ and team and champ.split()[-1] == team.split()[-1]:
                    ok += 1
            if w[1] and ok == w[0] == len(w[1]):
                accolades.append({"key": key, "label": label, "count": ok, "years": sorted(w[1]),
                                  "sources": "Wikipédia + ESPN kariéra + zoznam šampiónov"})
            else:
                issues.append(f"{profile['name']}: tituly {w[0]} (infobox) vs {ok} overených")
        else:
            if not w and not e:
                continue
            if w and e and w[0] == e:
                accolades.append({"key": key, "label": label, "count": e, "sources": "ESPN + Wikipédia"})
            else:
                issues.append(f"{profile['name']}: {label} ESPN {e or 0} vs Wikipédia {w[0] if w else 0}")
    accolades.sort(key=lambda a: ACCOLADES[a["key"]][1])
    profile["accolades"] = accolades
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", help="len jeden tím (ESPN team id)")
    args = ap.parse_args(argv)
    espn = Espn()
    today = dt.date.today()
    current = season_year(today)
    teams = parse.teams_list(espn.teams())
    if args.team:
        teams = [t for t in teams if t["id"] == args.team]
    rosters = {t["id"]: espn._get(f"{SITE}/teams/{t['id']}/roster").get("athletes") or [] for t in teams}
    prof = Profiles(espn)
    jobs = [(a, tid) for tid, r in rosters.items() for a in r]
    print(f"{len(jobs)} hráčov…", flush=True)
    with ThreadPoolExecutor(6) as ex:
        players = list(ex.map(lambda j: prof.player(j[0], j[1], current), jobs))

    print("Wikipédia…", flush=True)
    titles = wiki_titles({p["id"] for p in players})
    texts = wiki_texts(set(titles.values()))
    allstar = wiki_texts([f"{y} NBA All-Star Game" for y in range(1951, current)])
    champs = champions_by_year(wiki_texts(["List of NBA champions"]).get("List of NBA champions", ""))
    issues = []
    for p in players:
        title = titles.get(p["id"])
        p["_wiki"] = title
        p["wiki"] = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}" if title else None
        issues += verify(p, infobox_awards(texts.get(title, "")) if title else {}, allstar, champs)

    os.makedirs(OUT_DIR, exist_ok=True)
    by_team = defaultdict(dict)
    for p in players:
        by_team[p["teamId"]][p["id"]] = p
    stamp = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for tid, ps in by_team.items():
        with open(os.path.join(OUT_DIR, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump({"generatedAt": stamp, "currentSeason": current, "players": ps}, f, ensure_ascii=False, separators=(",", ":"))
    with_acc = sum(1 for p in players if p["accolades"])
    print(f"Hotovo: {len(players)} profilov, {with_acc} s overenými oceneniami, {len(titles)} článkov na Wikipédii.")
    if issues:
        print(f"Nesúlad zdrojov ({len(issues)}), tieto ocenenia sa nezobrazia:")
        for i in issues:
            print("  -", i)


if __name__ == "__main__":
    main()
