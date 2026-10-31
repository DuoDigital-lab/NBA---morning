"""Player recovery: stručný dôvod výpadku + očakávaný návrat (slovensky).

Postup: ESPN injuries -> filter viet (priebeh zápasu, štatistiky) -> Claude (ak je ANTHROPIC_API_KEY)
alebo pravidlá -> kontrola spoilerov. Výsledky sa cachujú podľa obsahu správy, takže Claude sa volá
iba pri novej / zmenenej správe. Odhad si nikdy nevymýšľame: bez zdroja = "termín neznámy".
"""
import datetime as dt
import hashlib
import json
import os
import re

from . import spoilers
from .config import CLAUDE_EFFORT, CLAUDE_MODEL

UNKNOWN = "termín neznámy"

TYPE_SK = {
    "Knee": "koleno", "Ankle": "členok", "Hamstring": "hamstring", "Foot": "chodidlo", "Back": "chrbát",
    "Hip": "bedro", "Calf": "lýtko", "Shoulder": "rameno", "Illness": "choroba", "Achilles": "Achillova šľacha",
    "Quadriceps": "štvorhlavý sval", "Wrist": "zápästie", "Hand": "ruka", "Finger": "prst", "Thumb": "palec",
    "Elbow": "lakeť", "Groin": "slabiny", "Concussion": "otras mozgu", "Head": "hlava", "Neck": "krk",
    "Toe": "prst na nohe", "Heel": "päta", "Leg": "noha", "Shin": "holeň", "Personal": "osobné dôvody",
    "Rest": "odpočinok", "Abdomen": "brucho", "Oblique": "šikmý brušný sval", "Rib": "rebrá",
    "Chest": "hrudník", "Eye": "oko", "Face": "tvár", "Nose": "nos", "Thigh": "stehno", "Glute": "sedací sval",
    "Pelvis": "panva", "Forearm": "predlaktie", "Arm": "ruka", "Lower Leg": "predkolenie", "Jaw": "čeľusť",
    "Mouth": "ústa", "Not Injury Related": "nesúvisí so zranením", "Suspension": "suspendácia",
    "Undisclosed": "nešpecifikované", "Lumbar": "driek", "Spine": "chrbtica", "Adductor": "adduktor",
}
DETAIL_SK = {
    "Surgery": "operácia", "Sprain": "vyvrtnutie", "Strain": "natiahnutie", "Soreness": "bolesť",
    "Fracture": "zlomenina", "Inflammation": "zápal", "Tear": "natrhnutie", "Contusion": "pomliaždenie",
    "Tendinitis": "zápal šľachy", "Tendinopathy": "tendinopatia", "Rupture": "ruptúra",
    "Dislocation": "vykĺbenie", "Bruise": "modrina", "Spasms": "kŕče", "Tightness": "stuhnutosť",
    "Injury": "zranenie", "Bone Bruise": "pomliaždenie kosti", "Stress Reaction": "únavová reakcia kosti",
    "Torn": "natrhnutie", "Impingement": "impingement", "Laceration": "tržná rana", "Infection": "infekcia",
    "Recovery": "rekonvalescencia", "Discomfort": "nepríjemnosť", "Irritation": "podráždenie",
    "Plantar Fasciitis": "zápal plantárnej fascie", "Dislocated": "vykĺbenie", "Pinched Nerve": "priškripnutý nerv",
    "Not Specified": None, "Other": None,
}
_NO_SIDE = {"Illness", "Personal", "Rest", "Not Injury Related", "Suspension", "Concussion"}
SIDE_SK = {"Left": "ľavá strana", "Right": "pravá strana"}
STATUS_SK = {
    "Out": "Mimo hry", "Day-To-Day": "Zo dňa na deň", "Questionable": "Otázny", "Doubtful": "Nepravdepodobný",
    "Probable": "Pravdepodobne hrá", "Suspension": "Suspendovaný", "Out For Season": "Mimo do konca sezóny",
}

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a": 1, "a couple": 2, "several": None}
_UNIT_SK = {
    "day": ("deň", "dni", "dní"), "week": ("týždeň", "týždne", "týždňov"), "month": ("mesiac", "mesiace", "mesiacov"),
}
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
_MONTHS_SK = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august", "september",
              "október", "november", "december"]


def _plural(unit, n):
    one, few, many = _UNIT_SK[unit]
    if n == 1:
        return one
    return few if 2 <= n <= 4 else many


def status_sk(item):
    if item.get("fantasy") == "OFS":
        return "Mimo do konca sezóny"
    return STATUS_SK.get(item.get("status") or "", item.get("status") or "Neznámy stav")


def reason_rule(item):
    t = TYPE_SK.get(item.get("type") or "", (item.get("type") or "").lower() or None)
    det = item.get("detail") or ""
    d = DETAIL_SK[det] if det in DETAIL_SK else (det.lower() or None)
    s = None if item.get("type") in _NO_SIDE else SIDE_SK.get(item.get("side") or "")
    if not t:
        return "bez bližších informácií"
    txt = t[0].upper() + t[1:]
    if d:
        txt += " – " + d
    if s:
        txt += f" ({s})"
    return txt


_RANGE_RE = re.compile(
    r"\b(at least |a minimum of |up to |another |roughly |approximately |about )?(?:the )?(?:next |additional )?"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a couple)"
    r"(?:\s*(?:to|-|–|or)\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve))?"
    r"(?:\s+of)?\s+(day|week|month)s?\b",
    re.I,
)
_BETWEEN_MONTHS = re.compile(r"between (" + "|".join(_MONTHS_EN) + r") and (" + "|".join(_MONTHS_EN) + r")")


def _n(word):
    if word.isdigit():
        return int(word)
    return _NUM.get(word.lower())


_TIMELINE_WORDS = re.compile(
    r"\b(miss|missing|sidelined|out|return|back|timetable|timeline|recover\w*|absence|window|expected|"
    r"week-to-week|day-to-day|re-evaluated|reevaluated)\b", re.I)


def _relevant_sentences(item, text):
    """Len vety o tomto hráčovi (priezvisko), ktoré hovoria o výpadku/návrate.
    Poznámky často spomínajú aj iných hráčov ("With Haliburton expected to miss two weeks...")."""
    last = (item.get("name") or "").replace(" Jr.", "").replace(" III", "").replace(" II", "").split(" ")[-1]
    sents = spoilers.split_sentences(text)
    own = [s for s in sents if last and last in s]
    if not own and sents:
        own = sents[:1]
    return " ".join(s for s in own if _TIMELINE_WORDS.search(s))


_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}
SEASON_DAYS = 365


def _report_date(item):
    try:
        return dt.date.fromisoformat((item.get("date") or "")[:10])
    except ValueError:
        return None


def _days_until_month_end(item, month_en):
    """Dni od dátumu správy do konca uvedeného mesiaca (najbližší taký mesiac po správe)."""
    rep = _report_date(item)
    if not rep:
        return None
    month = _MONTHS_EN.index(month_en) + 1
    year = rep.year if month >= rep.month else rep.year + 1
    end = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return (end - rep).days


def return_rule(item, text):
    """Vracia (text pre appku, odhad dní od dátumu správy alebo None). Pri rozsahu sa berie horná hranica."""
    if item.get("fantasy") == "OFS" or re.search(r"season-ending|remainder of the season|rest of the season", text, re.I):
        return "do konca sezóny", SEASON_DAYS
    text = _relevant_sentences(item, text)
    if re.search(r"\ba week or two\b", text, re.I):
        return "1–2 týždne", 14
    m = _RANGE_RE.search(text)
    if m:
        a, b, unit = _n(m.group(2)), (_n(m.group(3)) if m.group(3) else None), m.group(4).lower()
        if a:
            prefix = {"at least ": "najmenej ", "a minimum of ": "najmenej ", "up to ": "až ",
                      "another ": "ďalšie "}.get((m.group(1) or "").lower(), "")
            days = (b or a) * _UNIT_DAYS[unit]
            if b:
                return f"{prefix}{a}–{b} {_plural(unit, b)}", days
            return f"{prefix}{a} {_plural(unit, a)}", days
    m = _BETWEEN_MONTHS.search(text)
    if m:
        label = f"{_MONTHS_SK[_MONTHS_EN.index(m.group(1))]} – {_MONTHS_SK[_MONTHS_EN.index(m.group(2))]}"
        return label, _days_until_month_end(item, m.group(2))
    if (item.get("status") or "") == "Day-To-Day" or re.search(r"day-to-day", text, re.I):
        return "zo dňa na deň", 1
    if re.search(r"week-to-week", text, re.I):
        return "z týždňa na týždeň", 14
    if re.search(r"miss \W?months\b", text, re.I):
        return "niekoľko mesiacov", None
    if re.search(r"\bindefinitely\b", text, re.I):
        return "na neurčito", None
    return UNKNOWN, None


# Vážnosť výpadku podľa zostávajúcich dní do očakávaného návratu.
SEVERITY_LABELS = {
    "dtd": "zo dňa na deň",
    "short": "do mesiaca",
    "month": "1–3 mesiace",
    "long": "3–6 mesiacov",
    "season": "viac ako pol roka",
    "unknown": "termín neznámy",
    "none": "bez záznamu o zranení",
}


def return_estimate(item, note):
    """(ISO dátum očakávaného návratu, základ): zo správy (dátum správy + dni), inak automatický ESPN dátum."""
    rep = _report_date(item)
    if note.get("days") is not None and rep:
        return (rep + dt.timedelta(days=int(note["days"]))).isoformat(), "source"
    try:
        if item.get("returnDate"):
            return dt.date.fromisoformat(item["returnDate"][:10]).isoformat(), "espn"
    except ValueError:
        pass
    return None, None


def severity(item, note, today):
    """Vracia (vážnosť, základ): dtd (zelená) / short (žltá) / month (oranžová) / long (červená) /
    season (čierna) / unknown (sivá); základ = "source" (správa) alebo "espn" (automatický ESPN dátum).
    Zostávajúce dni = dátum správy + odhad zo zdroja − dnes. Ak zdroj termín neuvádza, použije sa
    automatický ESPN dátum návratu ako hrubý orientačný odhad."""
    if item.get("fantasy") == "OFS" or note.get("expectedReturn") == "do konca sezóny":
        return "season", "source"
    if (item.get("status") or "") == "Day-To-Day":
        return "dtd", "source"
    est, basis = return_estimate(item, note)
    if est is None:
        return "unknown", None
    left = (dt.date.fromisoformat(est) - today).days
    if left < 30:
        return "short", basis
    if left < 90:
        return "month", basis
    if left < 180:
        return "long", basis
    return "season", basis


_SOURCE_RE = re.compile(
    r"(?:per |according to |, )?([A-Z][\w.'’-]+(?: [A-Z][\w.'’-]+){1,2}) of ([A-Z][\w.&' ]+?)(?: reports| reported|[.,])"
)


def source_rule(text):
    m = _SOURCE_RE.search(text)
    if m:
        return f"{m.group(1)} ({m.group(2).strip()})"
    return ""


def rule_based(item, text):
    label, days = return_rule(item, text)
    return {"reason": reason_rule(item), "expectedReturn": label, "days": days, "returnSource": source_rule(text)}


# ---------------------------- Claude ----------------------------

SYSTEM_PROMPT = """You prepare injury notes for a spoiler-free NBA app whose user watches games later as highlights.
Write in Slovak. Use ONLY the facts given in the input. Never guess or estimate on your own.

Fields:
- reason: max ~90 characters, what the injury is and why the player is out (body part, diagnosis, surgery, illness, personal reasons). No game events.
- expected_return: a short Slovak phrase ONLY if the input text explicitly states a timeline or return window, e.g. "3–4 týždne", "najmenej 2 týždne", "cca koniec novembra", "december – január", "do konca sezóny". Keep relative timelines relative; the app shows the date of the report separately. If the status is Day-To-Day and no other timeline is stated, use "zo dňa na deň". If nothing explicit is stated, use exactly "termín neznámy". Ignore the field espn_return_date, it is an automated estimate.
- return_source: the named reporter and outlet the timeline comes from, e.g. "Chris Haynes (NBA TV)", or "" if not named.
- return_days: whole number of days from report_date until the expected return, based ONLY on the explicit timeline above (use the upper end of a range, e.g. "3-4 weeks" = 28, "out until late November" = days until Nov 25, "season-ending" = 365, Day-To-Day = 1). null if expected_return is "termín neznámy" or the timeline is vague.

Never mention scores, results, who won or lost, statistics, averages, minutes, quarters, overtime, game events, performance, fantasy advice or betting."""

SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string"},
        "expected_return": {"type": "string"},
        "return_source": {"type": "string"},
        "return_days": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
    },
    "required": ["reason", "expected_return", "return_source", "return_days"],
    "additionalProperties": False,
}


def _claude_client():
    """Vracia (klient alebo None, dôvod pre status.json)."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None, "Claude API kľúč chýba (GitHub secret ANTHROPIC_API_KEY nie je nastavený) – recovery poznámky sú len z pravidiel."
    if not key.startswith("sk-ant-"):
        return None, "Claude API kľúč má nesprávny tvar (má začínať sk-ant-) – recovery poznámky sú len z pravidiel."
    try:
        import anthropic  # noqa: WPS433 – voliteľná závislosť (GitHub Actions)
    except ImportError:
        return None, "Knižnica anthropic nie je nainštalovaná – recovery poznámky sú len z pravidiel."
    return anthropic.Anthropic(api_key=key), None


def _claude_summarize(client, item, text):
    import anthropic

    payload = {
        "player": item.get("name"),
        "status": item.get("status"),
        "injury_type": item.get("type"),
        "injury_detail": item.get("detail"),
        "side": item.get("side"),
        "report_date": (item.get("date") or "")[:10],
        "espn_return_date": item.get("returnDate"),
        "notes": text,
    }
    kwargs = dict(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={"effort": CLAUDE_EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    try:
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None
    text_out = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text_out)
    days = data.get("return_days")
    expected = data["expected_return"].strip()[:60] or UNKNOWN
    return {
        "reason": data["reason"].strip()[:140],
        "expectedReturn": expected,
        "days": int(days) if isinstance(days, int) and 0 <= days <= 800 and expected != UNKNOWN else None,
        "returnSource": data["return_source"].strip()[:80],
    }


# ---------------------------- verejné API ----------------------------

def _key(item):
    raw = json.dumps(["v2"] + [item.get(k) for k in ("status", "date", "type", "detail", "side", "fantasy", "_short", "_long")])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_recovery(items, cache, warnings):
    """items: {pid: injury item z parse.injuries_from_api}; cache: dict (mení sa na mieste).
    Vracia {pid: {"reason","expectedReturn","returnSource","method"}}."""
    client, why = _claude_client()
    if client is None:
        warnings.append(why)
    out = {}
    claude_failures = 0
    for pid, item in items.items():
        key = _key(item)
        cached = cache.get(pid)
        if cached and cached.get("key") == key and (cached.get("method") == "claude" or client is None):
            out[pid] = cached["result"]
            continue
        text = spoilers.filter_injury_text(item["_short"] + " " + item["_long"])
        result, method = None, "rules"
        if client is not None and claude_failures < 5:
            try:
                result = _claude_summarize(client, item, text)
                method = "claude"
            except Exception as e:  # sieť, limit, zlý kľúč, kredit, zlý JSON – spadneme na pravidlá
                claude_failures += 1
                msg = " ".join(str(getattr(e, "message", "") or e).split())[:160]
                warnings.append(f"Claude zhrnutie zlyhalo pre {item.get('name')}: {type(e).__name__}: {msg}")
                if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError", "NotFoundError"):
                    claude_failures = 99  # nemá zmysel skúšať ďalších hráčov
                result = None
        if result is None or spoilers.find_violations(result):
            result, method = rule_based(item, text), "rules"
        if spoilers.find_violations(result):
            result = {"reason": reason_rule(item), "expectedReturn": UNKNOWN, "days": None, "returnSource": ""}
        result["method"] = method
        cache[pid] = {"key": key, "method": method, "result": result}
        out[pid] = result
    for pid in list(cache):
        if pid not in items:
            del cache[pid]
    return out
